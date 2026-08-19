"""Score licence extraction, and measure the ratio the decision rests on.

THE SECOND CRITERION, REGISTERED BEFORE RUNNING
-----------------------------------------------
The first criterion for this bet is already settled: the cycle-time model showed
extraction removes 0.1% of elapsed onboarding time against a 10% threshold, so
"AI reads the documents and onboarding takes hours" is dead.

That does not settle a separate question with a separate answer: can extraction
be trusted to auto-populate a carrier submission? Registered before this ran:

    Accuracy alone cannot decide it. What decides it is how extraction fails.
    A field returned as null is a cheap failure -- a person reviews it. A field
    returned as a confident wrong value is an expensive one -- it posts to a
    carrier, and the packet comes back days later. So:

    If the confident-wrong rate on the danger fields (NPN, licence number,
    expiration date) exceeds 2%, auto-population is dead and extraction ships
    as a review accelerator with every field surfaced for confirmation.
    If confident-wrong is at or near zero and the failures are nulls,
    auto-population is viable for the fields that pass.

This is why the eval reports a ratio and not just a percentage. Two runs with
identical accuracy can land on opposite sides of that line.

Run with:
    cd backend && python -m eval.run_extraction_eval [--limit N]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from app.onboarding.extract import DANGER_FIELDS, extract  # noqa: E402

CORPUS = ROOT / "corpus" / "onboarding"
TRUTH_PATH = BACKEND / "eval" / "ground_truth" / "cohort_truth.json"
RESULTS = BACKEND / "eval" / "results"

# The threshold above. Changing it after seeing a result is the specific failure
# writing it down was meant to prevent.
CONFIDENT_WRONG_THRESHOLD_PCT = 2.0

# Scored fields, and which ground-truth key each is compared against. Note that
# `resident_state` is compared to what was *printed*, not to the canonical code:
# a licence that prints "North Carolina" and an extractor that returns "NC" has
# normalised, and normalisation is the failure this corpus exists to catch.
FIELD_MAP = {
    "full_name": "full_name",
    "npn": "npn",
    "license_number": "license_number",
    "resident_state": "state_printed_as",
    "license_type": "license_type",
    "issue_date": "issue_date",
    "expiration_date": "expiration_date",
}


def classify(extracted, expected) -> str:
    """How this field turned out: correct, a null, or a confident wrong value."""
    if extracted is None:
        return "null"
    if isinstance(expected, list):
        return "correct" if sorted(extracted) == sorted(expected) else "wrong"
    return "correct" if str(extracted).strip() == str(expected).strip() else "wrong"


def main() -> int:
    """Run the eval and report the accuracy and the failure mode."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="First N documents.")
    parser.add_argument("--model", default="claude-opus-5")
    args = parser.parse_args()

    import anthropic

    # Load backend/.env if present, so `python -m eval.run_extraction_eval`
    # works without the caller exporting the key first. Only fills variables
    # that are not already set, so a real environment always wins over a file.
    env_file = BACKEND / ".env"
    if env_file.exists():
        import os

        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, _, value = line.partition("=")
            os.environ.setdefault(name.strip(), value.strip().strip('"').strip("'"))

    truth = json.loads(TRUTH_PATH.read_text(encoding="utf-8"))
    documents = sorted(CORPUS.glob("*_license.pdf"))[: args.limit]
    if not documents:
        raise SystemExit(
            f"no licences in {CORPUS}. Run tools/generate_licenses.py first."
        )

    client = anthropic.Anthropic()

    per_field: dict[str, dict[str, int]] = {
        name: {"correct": 0, "null": 0, "wrong": 0} for name in FIELD_MAP
    }
    per_field["lines_of_authority"] = {"correct": 0, "null": 0, "wrong": 0}
    rows: list[dict] = []
    cost = 0.0
    dropped_total = 0

    print(f"model {args.model}   documents {len(documents)}\n")

    for path in documents:
        agent_id = path.stem.split("_")[0]
        expected = truth[agent_id]["license_fields"]
        result = extract(client, path, model=args.model)
        cost += result.cost_usd
        dropped_total += len(result.evidence_dropped)

        outcomes: dict[str, str] = {}
        for field_name, truth_key in FIELD_MAP.items():
            outcome = classify(
                getattr(result.extraction, field_name), expected[truth_key]
            )
            per_field[field_name][outcome] += 1
            outcomes[field_name] = outcome

        # Against the printed labels, not the internal codes. Scoring the codes
        # marked every correct extraction wrong -- a scorer bug, and exactly the
        # kind an eval catches only when the model is right and the score is not.
        outcome = classify(
            result.extraction.lines_of_authority or None,
            expected["lines_printed_as"],
        )
        per_field["lines_of_authority"][outcome] += 1
        outcomes["lines_of_authority"] = outcome

        wrong = [f for f, o in outcomes.items() if o == "wrong"]
        nulls = [f for f, o in outcomes.items() if o == "null"]
        hazards = [k for k, v in truth[agent_id]["hazards"].items() if v]

        rows.append(
            {
                "agent_id": agent_id,
                "outcomes": outcomes,
                "evidence_dropped": result.evidence_dropped,
                "latency_ms": result.latency_ms,
                "hazards": hazards,
            }
        )
        flag = "XX " if wrong else ("~~ " if nulls else "ok ")
        detail = ""
        if wrong:
            detail += f"  WRONG={wrong}"
        if nulls:
            detail += f"  null={nulls}"
        if hazards:
            detail += f"  hazards={hazards}"
        print(f"  {flag}{agent_id}  {result.latency_ms:>6}ms{detail}")

    total = sum(sum(counts.values()) for counts in per_field.values())
    correct = sum(counts["correct"] for counts in per_field.values())
    nulls = sum(counts["null"] for counts in per_field.values())
    wrong = sum(counts["wrong"] for counts in per_field.values())

    print(f"\nper field ({len(documents)} documents)")
    print(f"  {'field':<20}{'correct':>9}{'null':>7}{'wrong':>7}")
    for name, counts in per_field.items():
        print(
            f"  {name:<20}{counts['correct']:>9}{counts['null']:>7}{counts['wrong']:>7}"
        )

    print(f"\n  field values scored      {total}")
    print(f"  accuracy                 {correct / total:.1%}")
    print(f"  nulls (safe failure)     {nulls}  ({nulls / total:.1%})")
    print(f"  wrong (costly failure)   {wrong}  ({wrong / total:.1%})")
    if nulls + wrong:
        print(f"  of all failures, {nulls / (nulls + wrong):.0%} were nulls")
    else:
        print("  no failures")
    print(f"  excerpts dropped in verification  {dropped_total}")

    danger_total = sum(sum(per_field[f].values()) for f in DANGER_FIELDS if f in per_field)
    danger_wrong = sum(per_field[f]["wrong"] for f in DANGER_FIELDS if f in per_field)
    danger_pct = 100 * danger_wrong / danger_total if danger_total else 0.0

    print(f"\ndanger fields ({', '.join(DANGER_FIELDS)})")
    print(f"  confident wrong  {danger_wrong}/{danger_total}  ({danger_pct:.1f}%)")
    print(
        f"\nCRITERION (registered before running): confident-wrong on the danger "
        f"fields must stay at or under {CONFIDENT_WRONG_THRESHOLD_PCT:.0f}%"
    )
    if danger_pct > CONFIDENT_WRONG_THRESHOLD_PCT:
        print("  -> FIRES. Auto-population is dead; extraction ships as a review")
        print("     accelerator with every field surfaced for confirmation.")
    else:
        print("  -> holds. Auto-population is viable for the fields that pass,")
        print("     with the rest surfaced for review.")

    print(f"\ncost  ${cost:.4f}  for {len(documents)} documents")

    RESULTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out = RESULTS / f"extraction_{stamp}.json"
    out.write_text(
        json.dumps(
            {
                "model": args.model,
                "documents": len(documents),
                "per_field": per_field,
                "accuracy_pct": round(100 * correct / total, 2),
                "null_pct": round(100 * nulls / total, 2),
                "wrong_pct": round(100 * wrong / total, 2),
                "danger_confident_wrong_pct": round(danger_pct, 2),
                "criterion_threshold_pct": CONFIDENT_WRONG_THRESHOLD_PCT,
                "criterion_fires": danger_pct > CONFIDENT_WRONG_THRESHOLD_PCT,
                "evidence_dropped": dropped_total,
                "cost_usd": round(cost, 4),
                "rows": rows,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"written to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
