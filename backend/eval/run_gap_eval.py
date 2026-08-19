"""Score the deterministic gap engine against the planted defects.

WHAT AGREEMENT HERE MEANS, AND WHAT IT DOES NOT
-----------------------------------------------
The engine reads `backend/data/cohort.json`. The plants live in
`backend/eval/ground_truth/cohort_truth.json`. Neither file is read by the
other's producer, so agreement means the engine recovered each defect from the
record rather than looking up an answer.

What it does not establish is that the *requirements* are right. The rules and
the seeds were written by the same person from the same idea of how carrier
contracting works, so a misunderstood requirement would be misunderstood
identically in both and the score would still be 100%. That is a real and
unmeasured risk, and it is the reason this number is reported as "the engine
does what it was specified to do" rather than "the engine is correct".

The score being 100% is expected and is not a boast: these are set comparisons
and date arithmetic. It is reported next to the extraction number precisely
because the contrast is the argument -- a deterministic check that cannot drift
against a model that can.

Run with:
    cd backend && python -m eval.run_gap_eval
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(ROOT / "tools"))

from app.onboarding.rules import ENGINE_VERSION, evaluate  # noqa: E402
from onboarding_data import CARRIERS  # noqa: E402


def carrier_table() -> dict[str, dict]:
    """Carrier requirements in the shape the engine expects."""
    return {
        carrier.carrier_id: {
            "carrier_id": carrier.carrier_id,
            "name": carrier.name,
            "appointment_states": sorted(carrier.appointment_states),
            "required_lines": sorted(carrier.required_lines),
            "aml_required": carrier.aml_required,
            "eo_minimum_usd": carrier.eo_minimum_usd,
            "name_match_strict": carrier.name_match_strict,
        }
        for carrier in CARRIERS
    }


def main() -> int:
    """Score the engine and return a process exit code."""
    blob = json.loads((BACKEND / "data" / "cohort.json").read_text(encoding="utf-8"))
    truth = json.loads(
        (BACKEND / "eval" / "ground_truth" / "cohort_truth.json").read_text(
            encoding="utf-8"
        )
    )
    as_of = datetime.fromisoformat(blob["anchor"].replace("Z", "+00:00")).replace(
        tzinfo=None
    )
    carriers = carrier_table()

    true_positive = false_positive = false_negative = 0
    disagreements: list[str] = []

    print(f"gap engine {ENGINE_VERSION}   cohort anchor {as_of:%d %b %Y}\n")

    for agent in blob["agents"]:
        found = {gap.key for gap in evaluate(agent, carriers, as_of=as_of)}
        planted = set(truth[agent["agent_id"]]["planted_gaps"])

        true_positive += len(found & planted)
        false_positive += len(found - planted)
        false_negative += len(planted - found)

        agrees = found == planted
        if not agrees:
            disagreements.append(
                f"{agent['agent_id']}: missed={sorted(planted - found)} "
                f"spurious={sorted(found - planted)}"
            )
        print(
            f"  {'ok ' if agrees else 'XX '}{agent['agent_id']}  "
            f"planted={len(planted)}  found={len(found)}"
        )

    precision = (
        true_positive / (true_positive + false_positive)
        if true_positive + false_positive
        else 1.0
    )
    recall = (
        true_positive / (true_positive + false_negative)
        if true_positive + false_negative
        else 1.0
    )
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    print(
        f"\n  true positives {true_positive}   "
        f"false positives {false_positive}   "
        f"false negatives {false_negative}"
    )
    print(f"  precision {precision:.1%}   recall {recall:.1%}   F1 {f1:.1%}")
    # Variance is printed as an explicit zero rather than omitted. The engine is
    # deterministic, and saying so next to a model-produced number that is not
    # is the entire reason both appear in the same write-up.
    print("  variance across runs: 0.00 (deterministic)")

    if disagreements:
        print("\ndisagreements:")
        for line in disagreements:
            print(f"  {line}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
