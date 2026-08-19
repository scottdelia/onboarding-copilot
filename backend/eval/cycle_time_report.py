"""The cycle-time report, and the kill criterion it tests.

This is the instrument the whole bet was registered against. The criterion,
written down before any of this was built:

    If AI-assisted document extraction accounts for under 10% of total elapsed
    onboarding time, the "AI reads the documents and onboarding takes hours"
    framing is dead, and the bet narrows to a deterministic completeness check
    at submission plus an ownership queue.

Registering it in advance is the point. A threshold chosen after seeing the
number is an opinion; chosen before, it is a decision, and it stops a
disappointing result being reinterpreted as an encouraging one.

Run with:
    cd backend && python -m eval.cycle_time_report
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app.onboarding.cycle_time import (  # noqa: E402
    agent_cycle_time,
    cohort_cycle_time,
    sensitivity,
)

# The pre-registered threshold. Changing this number after seeing a result is
# the specific failure this file exists to prevent.
KILL_THRESHOLD_PCT = 10.0


def main() -> int:
    """Print the decomposition, the levers, and the criterion outcome."""
    blob = json.loads((BACKEND / "data" / "cohort.json").read_text(encoding="utf-8"))
    cohort = blob["agents"]
    report = cohort_cycle_time(cohort)

    baseline = report["baseline"]
    decomposition = report["decomposition"]

    print(
        f"cohort of {report['cohort_size']}   "
        f"baseline mean {baseline['mean_hours']}h ({baseline['mean_days']} days)\n"
    )

    print("where the elapsed time sits, along the critical path")
    rows = (
        (
            "external queues (carrier / state / vendor)",
            "external_wait_hours",
            "external_wait_share_pct",
        ),
        ("internal queue (our own backlog)", "internal_queue_hours", "internal_queue_share_pct"),
        ("rework (defect caught by a carrier)", "rework_hours", "rework_share_pct"),
        ("internal idle (actionable, untouched)", "internal_idle_hours", "internal_idle_share_pct"),
        ("internal touch (someone actively working)", "internal_touch_hours", "internal_touch_share_pct"),
    )
    total = 0.0
    for label, hours_key, share_key in rows:
        print(
            f"  {label:<44}{decomposition[hours_key]:>7.1f}h "
            f"{decomposition[share_key]:>5.1f}%"
        )
        total += decomposition[share_key]
    print(f"  {'':<44}{'':>8} {total:>5.1f}%")

    print("\nwhat each lever removes from the total")
    for name, lever in report["levers"].items():
        print(
            f"  {name:<12} -{lever['hours_removed']:>6.1f}h  "
            f"{lever['percent_removed']:>5.1f}%"
        )

    extraction_pct = report["levers"]["extraction"]["percent_removed"]
    fired = extraction_pct < KILL_THRESHOLD_PCT

    print(
        f"\nKILL CRITERION (registered before the build): extraction must remove "
        f"at least {KILL_THRESHOLD_PCT:.0f}% of elapsed time"
    )
    print(f"  extraction removes {extraction_pct}%")
    print(
        "  -> CRITERION FIRES. The days-to-hours framing is dead."
        if fired
        else "  -> criterion survives."
    )

    print("\nsensitivity -- does the conclusion hold if the assumptions are wrong?")
    for row in sensitivity(cohort):
        print(
            f"  {row['scenario']:<24} external {row['external_wait_share_pct']:>5.1f}%   "
            f"extraction {row['extraction_pct']:>4.1f}%   "
            f"rule engine {row['rule_engine_pct']:>4.1f}%   "
            f"extraction wins: {row['extraction_wins']}"
        )

    # The single agent that carries the alternative finding. A one-line defect
    # caught by a carrier instead of at submission is worth more elapsed time
    # than every document in the cohort being read perfectly.
    bounced = next((a for a in cohort if a.get("rework_days", 0) > 0), None)
    if bounced is not None:
        timing = agent_cycle_time(bounced)
        print(
            f"\n{timing.agent_id} ({bounced['display_name']}) -- packet returned by a carrier"
        )
        print(f"  critical chain: {' -> '.join(timing.critical_chain)}")
        print(
            f"  {timing.baseline_hours:.0f}h total, of which "
            f"{timing.rework_hours:.0f}h ({timing.rework_hours / timing.baseline_hours:.0%}) "
            f"is one rejected packet"
        )

    print(
        "\nassumptions: "
        + json.dumps(report["assumptions"], indent=2).replace("\n", "\n  ")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
