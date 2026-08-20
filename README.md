# Onboarding Copilot

> **Illustrative demonstration only.** Every agent, carrier, licence, producer
> number, and duration in this repository is **fictional and generated**. Not
> affiliated with any insurance carrier. Nothing here is a licence, evidence of
> one, or advice.

A bet on the role brief's question, *"an agent onboarding workflow that takes
days and involves too many manual handoffs. What if it took hours?"*, and the
instrument built to test it before building the obvious answer.

**The obvious answer is a model that reads the licensing paperwork. It does not
work, and this repository is the measurement that says so.**

---

## The result

Across a twelve-agent cohort with a 15.2-day mean, decomposed along the critical
path:

| Where the elapsed time goes | Hours | Share |
|---|---:|---:|
| External queues (carrier / state / vendor) | 343.3 | **93.9%** |
| Internal queue (our own backlog) | 8.0 | 2.2% |
| Rework (defect caught by a carrier) | 8.0 | 2.2% |
| Internal idle (actionable, untouched) | 5.2 | 1.4% |
| **Internal touch (someone actively working)** | **1.0** | **0.3%** |

Someone actively working is 0.3% of onboarding. Handed a generous 70% cut in
transcription time, extraction removes **0.1%** of the total. The kill criterion
registered before the build was 10%. It fires, and it still fires with carrier
queues cut to a quarter.

The deterministic rule engine removes **22× more**, by catching a packet defect
before it enters a carrier queue instead of after. It has no model in it.

Extraction was built anyway, against a second criterion, and scores **100% on 96
field values with zero confident-wrong**, which answers a different question
(can it auto-populate?) and is a ceiling rather than a forecast.

Full write-up, including the five defects the evals caught and the limits of
each number: **[docs/FINDINGS.md](docs/FINDINGS.md)**.

**Live demo:** https://scottdelia.github.io/onboarding-copilot/

Part of an [applied-AI portfolio](https://scottdelia.github.io/innovation-office/).

---

## Quickstart

Requires Python 3.11+.

```bash
python -m venv .venv && ./.venv/Scripts/activate   # Windows
pip install -r backend/requirements.txt
```

Generate the cohort and the licence documents (neither is committed):

```bash
python tools/generate_cohort.py
python tools/generate_licenses.py
```

Run the two measurements that decided the bet. Neither calls a model, so both
are free and instant:

```bash
cd backend
python -m eval.cycle_time_report
python -m eval.run_gap_eval
```

Run the extraction sweep. This one costs about $0.40 and needs
`ANTHROPIC_API_KEY` in `backend/.env`:

```bash
python -m eval.run_extraction_eval
python -m eval.negative_control
```

---

## Layout

```
tools/
  onboarding_data.py        the structured source: carriers, steps, 12 agent seeds
  generate_cohort.py        seeds -> backend/data/cohort.json + ground truth
  generate_licenses.py      seeds -> rendered PDFs, verified against their text layer
backend/app/
  onboarding/cycle_time.py  touch/wait split, critical path, the three levers
  onboarding/rules.py       deterministic gap engine (no model)
  onboarding/extract.py     vision extraction with per-field provenance
  prompts/extraction.py     every prompt, versioned, with clause rationale
backend/eval/
  cycle_time_report.py      the kill criterion and its sensitivity
  run_gap_eval.py           rule engine vs planted defects
  run_extraction_eval.py    field accuracy and the null-vs-wrong ratio
  negative_control.py       proves the scorer can fail
  ground_truth/             planted defects and exact printed field values
docs/FINDINGS.md            the write-up
```

---

## Why the data is generated

Real onboarding records are personnel files. Generating the cohort removes that
problem and buys something the real records could not: because each licence is
rendered *from* the structured values, ground truth is exact, and the generator
re-reads every rendered PDF to confirm each value survived the layout engine.

The corpus carries deliberate hazards. A leading-zero NPN under a watermark, a
`DD-MMM-YYYY` date among `MM/DD/YYYY` ones, states printed in full where the rest
abbreviate, because twelve identical clean licences would not test an extractor
at all.

The tradeoff is stated rather than hidden: these are clean vector PDFs, so the
evaluation measures transcription logic, not robustness to a scan.
