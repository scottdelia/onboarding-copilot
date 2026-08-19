"""Render the structured seeds into the cohort record the API serves.

Separating this from `onboarding_data.py` is the same discipline the corpus
generator uses in the sibling project: the seeds are the source, the generated
record is what the application reads, and nothing in the application imports the
seeds. That keeps the evaluation honest -- the rule engine agreeing with
`planted_gaps` means it recovered the defect from the record, not that it read
the answer key.

Writes:
    backend/data/cohort.json   the record the API serves
    backend/eval/ground_truth/cohort_truth.json   planted gaps and licence
                                                  field values, for scoring
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from onboarding_data import (  # noqa: E402
    AGENT_SEEDS,
    CARRIERS_BY_ID,
    COHORT_ANCHOR_ISO,
    STEPS,
    STEPS_BY_ID,
    summary,
)

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "backend" / "data"
TRUTH = ROOT / "backend" / "eval" / "ground_truth"

# Must match cycle_time.BUSINESS_TO_CALENDAR. Duplicated rather than imported
# because tools/ does not depend on backend/ -- the generator has to run before
# the application does.
BUSINESS_TO_CALENDAR = 7 / 5


def carrier_wait_hours(step_id: str, target_carriers: tuple[str, ...]) -> float:
    """Elapsed hours a per-carrier step contributes to the critical path.

    Carrier packets are submitted in parallel, so the pipeline pays the slowest
    carrier's queue rather than the sum of all of them. Taking the max is the
    difference between a model that says nine days and one that says thirty.
    """
    step = STEPS_BY_ID[step_id]
    if step_id != "carrier_appointment":
        return step.wait_hours
    queues = [
        CARRIERS_BY_ID[c].appointment_queue_days
        for c in target_carriers
        if c in CARRIERS_BY_ID
    ]
    if not queues:
        return step.wait_hours
    return max(queues) * 24 * BUSINESS_TO_CALENDAR


def main() -> None:
    """Write the cohort record and its ground truth."""
    DATA.mkdir(parents=True, exist_ok=True)
    TRUTH.mkdir(parents=True, exist_ok=True)

    cohort = []
    truth = {}

    for seed in AGENT_SEEDS:
        states = {state.step_id: state for state in seed.steps}
        steps = []
        for definition in STEPS:
            state = states.get(definition.step_id)
            steps.append(
                {
                    "step_id": definition.step_id,
                    "name": definition.name,
                    "owner": definition.owner,
                    "order": definition.order,
                    "touch_minutes": definition.touch_minutes,
                    "wait_hours": carrier_wait_hours(
                        definition.step_id, seed.target_carriers
                    ),
                    "idle_hours": state.idle_hours if state else 0.0,
                    "automatable_by": definition.automatable_by,
                    "depends_on": list(definition.depends_on),
                    "per_carrier": definition.per_carrier,
                    "note": definition.note,
                    "status": state.status if state else "not_started",
                    "blocker": state.blocker if state else "none",
                    "blocker_detail": state.blocker_detail if state else "",
                    "elapsed_hours": state.elapsed_hours if state else 0.0,
                    "carrier_id": state.carrier_id if state else None,
                }
            )

        cohort.append(
            {
                "agent_id": seed.agent_id,
                "display_name": seed.display_name,
                "npn": seed.npn,
                "resident_state": seed.resident_state,
                "license_full_name": seed.license_full_name,
                "license_number": seed.license_number,
                "license_type": seed.license_type,
                "lines_of_authority": list(seed.lines_of_authority),
                "issue_date": seed.issue_date,
                "expiration_date": seed.expiration_date,
                "aml_completed": seed.aml_completed,
                "eo_coverage_usd": seed.eo_coverage_usd,
                "target_carriers": list(seed.target_carriers),
                "rework_days": seed.rework_days,
                "demonstrates": seed.demonstrates,
                "steps": steps,
            }
        )

        truth[seed.agent_id] = {
            "planted_gaps": list(seed.planted_gaps),
            "license_fields": {
                "full_name": seed.license_full_name,
                "npn": seed.npn,
                "license_number": seed.license_number,
                "resident_state": seed.resident_state,
                "state_printed_as": seed.state_printed_as,
                "license_type": seed.license_type,
                "lines_of_authority": list(seed.lines_of_authority),
                "issue_date": seed.issue_date,
                "expiration_date": seed.expiration_date,
            },
            "hazards": {
                "watermark_over_npn": seed.watermark_over_npn,
                "date_format": seed.date_format,
                "state_written_in_full": len(seed.state_printed_as) > 2,
                "npn_leading_zero": seed.npn.startswith("0"),
            },
        }

    (DATA / "cohort.json").write_text(
        json.dumps(
            {"anchor": COHORT_ANCHOR_ISO, "agents": cohort}, indent=2
        ),
        encoding="utf-8",
    )
    (TRUTH / "cohort_truth.json").write_text(
        json.dumps(truth, indent=2), encoding="utf-8"
    )

    for key, value in summary().items():
        print(f"  {key:28} {value}")
    print(f"\nwrote {DATA / 'cohort.json'}")
    print(f"wrote {TRUTH / 'cohort_truth.json'}")


if __name__ == "__main__":
    main()
