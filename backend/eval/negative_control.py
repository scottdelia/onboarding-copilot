"""Prove the extraction scorer can fail.

WHY THIS EXISTS
---------------
The extraction eval reports 100% across 96 field values. A perfect score is
exactly when a scorer deserves the least trust, because a scorer that always
returns 100% and a scorer that is correct produce identical output on a clean
run. The only way to tell them apart is to feed it something wrong and check
that it notices.

This is not hypothetical here. The first version of the eval compared
`lines_of_authority` against the internal codes while the model returned the
printed labels, and scored every correct extraction as wrong. That bug was
caught because the failure was visible. The opposite bug -- a comparison that
always passes -- would have been invisible, and would have produced the same
100% this file exists to defend.

It runs against the saved result file, so it needs no API calls and costs
nothing.

Run with:
    cd backend && python -m eval.negative_control
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from eval.run_extraction_eval import classify  # noqa: E402

TRUTH_PATH = BACKEND / "eval" / "ground_truth" / "cohort_truth.json"
RESULTS = BACKEND / "eval" / "results"


def latest_result() -> dict:
    """The most recent extraction run."""
    files = sorted(RESULTS.glob("extraction_*.json"))
    if not files:
        raise SystemExit(
            "no extraction results found. Run `python -m eval.run_extraction_eval` first."
        )
    return json.loads(files[-1].read_text(encoding="utf-8"))


def main() -> int:
    """Plant errors and confirm every corresponding check fails."""
    truth = json.loads(TRUTH_PATH.read_text(encoding="utf-8"))
    result = latest_result()
    agent_id = result["rows"][0]["agent_id"]
    fields = truth[agent_id]["license_fields"]

    # The leading-zero case has to run against the document that carries the
    # hazard. Run against an ordinary NPN, `lstrip("0")` returns the value
    # unchanged and the case compares a correct value with itself -- which is
    # how the first version of this file reported a scorer failure that was
    # really a flaw in the test. The negative control caught its own bug, which
    # is the argument for having one.
    zero_id = next(
        (
            aid
            for aid, entry in truth.items()
            if entry["hazards"].get("npn_leading_zero")
        ),
        None,
    )
    if zero_id is None:
        raise SystemExit(
            "no document carries a leading-zero NPN, so the normalisation case "
            "cannot be exercised."
        )
    zero_npn = truth[zero_id]["license_fields"]["npn"]

    # Each case is (name, what the extractor returned, what the truth says, the
    # verdict the scorer must reach). A scorer that cannot produce the expected
    # verdict for any of these is not measuring what it claims to.
    cases = [
        (
            "a wrong NPN is caught",
            "99999999",
            fields["npn"],
            "wrong",
        ),
        (
            f"an NPN with the leading zero stripped is caught ({zero_id})",
            zero_npn.lstrip("0"),
            zero_npn,
            "wrong",
        ),
        (
            "a normalised state is caught",
            "NC" if len(fields["state_printed_as"]) > 2 else "North Carolina",
            fields["state_printed_as"],
            "wrong",
        ),
        (
            "a reformatted date is caught",
            "2027-03-31",
            fields["expiration_date"],
            "wrong",
        ),
        (
            "a null is scored as a null, not as correct",
            None,
            fields["npn"],
            "null",
        ),
        (
            "a dropped line of authority is caught",
            fields["lines_printed_as"][:-1] or ["Nothing"],
            fields["lines_printed_as"],
            "wrong",
        ),
        (
            "an unchanged value still scores correct",
            fields["npn"],
            fields["npn"],
            "correct",
        ),
    ]

    print(f"negative control against agent {agent_id}\n")
    failures = 0
    for name, extracted, expected, want in cases:
        got = classify(extracted, expected)
        ok = got == want
        failures += not ok
        print(f"  {'ok ' if ok else 'XX '}{name:<52} expected={want:<8} got={got}")

    # The last case is the control on the control: if a correct value scored as
    # anything other than correct, the scorer is broken in the other direction
    # and every reported failure would be suspect too.
    if failures:
        print(f"\n{failures} case(s) failed. The scorer is not measuring what it reports.")
        return 1

    print("\nevery planted error was caught and the unchanged value still passed.")
    print("the 100% in the extraction eval is a measurement, not a tautology.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
