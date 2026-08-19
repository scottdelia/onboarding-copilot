"""Precompute everything the site displays.

WHY THERE IS NO SERVER
----------------------
The sibling Underwriting Copilot needs a backend because it answers free text: a
reader types a prospect and a model reads carrier guides. This app answers
nothing. It shows a fixed cohort, a decomposition of that cohort's elapsed time,
and the gaps a deterministic engine finds in it -- all of which are functions of
data that does not change between page loads.

So the "backend" runs once, here, and the site is static by construction rather
than by fixture. That is not a shortcut around deployment; it is the correct
shape for an application with no query. The one component that does call a model
-- licence extraction -- ships its recorded eval output, and the page says so.

Writes frontend/public/data/site.json.

Run after the cohort exists:
    python tools/generate_cohort.py && python tools/build_site_data.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "tools"))

from app.onboarding.cycle_time import (  # noqa: E402
    agent_cycle_time,
    cohort_cycle_time,
    sensitivity,
)
from app.onboarding.rules import ENGINE_VERSION, evaluate  # noqa: E402
from onboarding_data import CARRIERS  # noqa: E402

OUT = ROOT / "frontend" / "public" / "data"
COHORT = ROOT / "backend" / "data" / "cohort.json"
RESULTS = ROOT / "backend" / "eval" / "results"

# Must match eval/cycle_time_report.py. The threshold appears on the page, so it
# is carried through rather than restated in the UI where it could drift.
KILL_THRESHOLD_PCT = 10.0


def carrier_table() -> dict[str, dict]:
    """Carrier requirements in the shape the engine and the UI both use."""
    return {
        carrier.carrier_id: {
            "carrier_id": carrier.carrier_id,
            "name": carrier.name,
            "appointment_states": sorted(carrier.appointment_states),
            "required_lines": sorted(carrier.required_lines),
            "aml_required": carrier.aml_required,
            "eo_minimum_usd": carrier.eo_minimum_usd,
            "name_match_strict": carrier.name_match_strict,
            "appointment_queue_days": carrier.appointment_queue_days,
        }
        for carrier in CARRIERS
    }


def latest_extraction() -> dict | None:
    """The most recent full extraction sweep, if one has been run."""
    files = sorted(RESULTS.glob("extraction_*.json"))
    if not files:
        return None
    result = json.loads(files[-1].read_text(encoding="utf-8"))
    return {
        "model": result["model"],
        "documents": result["documents"],
        "accuracy_pct": result["accuracy_pct"],
        "null_pct": result["null_pct"],
        "wrong_pct": result["wrong_pct"],
        "danger_confident_wrong_pct": result["danger_confident_wrong_pct"],
        "criterion_threshold_pct": result["criterion_threshold_pct"],
        "criterion_fires": result["criterion_fires"],
        "cost_usd": result["cost_usd"],
        "per_field": result["per_field"],
    }


def main() -> int:
    """Compute the site payload and write it."""
    if not COHORT.exists():
        raise SystemExit(
            f"{COHORT} not found. Run tools/generate_cohort.py first."
        )

    blob = json.loads(COHORT.read_text(encoding="utf-8"))
    cohort = blob["agents"]
    as_of = datetime.fromisoformat(blob["anchor"].replace("Z", "+00:00")).replace(
        tzinfo=None
    )
    carriers = carrier_table()

    agents = []
    for record in cohort:
        timing = agent_cycle_time(record)
        gaps = evaluate(record, carriers, as_of=as_of)
        on_path = set(timing.critical_chain)

        agents.append(
            {
                "agent_id": record["agent_id"],
                "display_name": record["display_name"],
                "resident_state": record["resident_state"],
                "npn": record["npn"],
                "target_carriers": record["target_carriers"],
                "demonstrates": record["demonstrates"],
                "days_elapsed": round(timing.baseline_hours / 24, 1),
                "rework_hours": timing.rework_hours,
                "external_wait_hours": round(timing.external_wait_hours, 1),
                "internal_touch_hours": round(timing.internal_touch_hours, 2),
                "internal_idle_hours": round(timing.internal_idle_hours, 1),
                "critical_chain": list(timing.critical_chain),
                "steps": [
                    {
                        "step_id": step["step_id"],
                        "name": step["name"],
                        "owner": step["owner"],
                        "status": step["status"],
                        "blocker": step["blocker"],
                        "blocker_detail": step["blocker_detail"],
                        "touch_minutes": step["touch_minutes"],
                        "wait_hours": round(step["wait_hours"], 1),
                        "idle_hours": round(step["idle_hours"], 1),
                        "automatable_by": step["automatable_by"],
                        "on_critical_path": step["step_id"] in on_path,
                        "note": step["note"],
                    }
                    for step in record["steps"]
                ],
                "gaps": [
                    {
                        "key": gap.key,
                        "rule_id": gap.rule_id,
                        "carrier_id": gap.carrier_id,
                        "carrier_name": (
                            carriers[gap.carrier_id]["name"] if gap.carrier_id else None
                        ),
                        "severity": gap.severity,
                        "summary": gap.summary,
                        "expected": gap.expected,
                        "observed": gap.observed,
                        "owner": gap.owner,
                        "source": gap.source,
                    }
                    for gap in gaps
                ],
            }
        )

    report = cohort_cycle_time(cohort)
    payload = {
        "generated_from": "tools/build_site_data.py",
        "anchor": blob["anchor"],
        "engine_version": ENGINE_VERSION,
        "kill_threshold_pct": KILL_THRESHOLD_PCT,
        "cycle_time": report,
        "sensitivity": sensitivity(cohort),
        "carriers": list(carriers.values()),
        "agents": agents,
        "extraction": latest_extraction(),
    }

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "site.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    gaps_total = sum(len(agent["gaps"]) for agent in agents)
    print(f"  agents          {len(agents)}")
    print(f"  gaps found      {gaps_total}")
    print(f"  baseline mean   {report['baseline']['mean_days']} days")
    print(f"  extraction      {report['levers']['extraction']['percent_removed']}%")
    print(f"\nwrote {OUT / 'site.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
