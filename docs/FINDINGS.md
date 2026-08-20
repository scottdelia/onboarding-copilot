# Findings

What this bet set out to test, what the numbers said, and what I would do next.

> Every agent, carrier, licence, and duration in this project is **synthetic**.
> See [The cohort](#the-cohort).

---

## The question, and the criterion registered before building

The role brief names it directly:

> An agent onboarding workflow that takes days and involves too many manual
> handoffs. What if it took hours?

The obvious build is a model that reads the licensing paperwork. I thought that
build was close to worthless, and the interesting version of this bet was
proving it rather than asserting it. So before writing any of it, one criterion
went down in writing:

> Build the cycle-time model first, from a cohort with per-step touch time and
> wait time separated. **If extraction accounts for under 10% of total elapsed
> time, the "AI reads the documents and onboarding takes hours" framing is
> dead**, and the bet narrows to a deterministic completeness check at
> submission plus an ownership queue.

Registering it in advance is the whole point. A threshold picked after seeing a
number is an opinion; picked before, it is a decision, and it is what stops a
disappointing result being quietly reinterpreted as an encouraging one.

---

## Finding 1: the framing is dead

Every step is split into two quantities that get conflated constantly and behave
nothing alike. **Touch time** is somebody actively working, software can
compress it. **Wait time** is the work sitting in somebody else's queue: a state
department of insurance, a background vendor, a carrier's appointment desk.
Nothing built here shortens it.

Summed across the cohort *along the critical path*, not as a naive total, since
a background check and a licence lookup run at the same time and adding both
overstates the timeline badly:

| Where a 15.2-day onboarding actually goes | Hours | Share |
|---|---:|---:|
| External queues (carrier / state / vendor) | 343.3 | **93.9%** |
| Internal queue (our own backlog) | 8.0 | 2.2% |
| Rework (defect caught by a carrier) | 8.0 | 2.2% |
| Internal idle (actionable, untouched) | 5.2 | 1.4% |
| **Internal touch (someone actively working)** | **1.0** | **0.3%** |

**Someone actively working is 0.3% of onboarding.** That is the finding. Every
lever modelled separately, against the same baseline:

| Lever | Removes | Share of total |
|---|---:|---:|
| Extraction (reads the documents) | 0.5h | **0.1%** |
| Rule engine (catches defects at submission) | 8.0h | 2.2% |
| Nudge queue (chases idle work) | 4.2h | 1.1% |
| All three | 12.7h | 3.5% |

The extraction figure is generous on purpose: the model hands it a 70% cut in
transcription time. If that does not move the total, a realistic reduction will
not either.

**Criterion fires at 0.1% against a 10% threshold.** And it is not close, nor
fragile:

| Scenario | External share | Extraction | Rule engine |
|---|---:|---:|---:|
| As modelled | 93.9% | 0.1% | 2.2% |
| Carrier queues halved | 88.5% | 0.3% | 4.1% |
| Carrier queues at 25% | 71.5% | 0.5% | 7.2% |

Extraction never overtakes the rule engine, at any assumption I can defend.

Reproduce with `cd backend && python -m eval.cycle_time_report`.

### What replaces it

The same data names the alternative. The deterministic rule engine removes
**22× more elapsed time** than extraction, by catching a packet defect *before*
it enters a carrier queue rather than after. One agent in the cohort carries the
whole argument: a nickname on the application against a legal name on the
licence, bounced by a carrier that matches strictly. That single rejected packet
is **96 of that agent's 493 hours**, 19% of their onboarding, lost to a
one-line defect that a check at submission catches in milliseconds.

The engine that catches it is plain code. `Gap.source` is a one-value `Literal`,
so the schema itself records that nothing here was model-produced. It scores
**100% precision and 100% recall** on 8 planted defects across 12 agents, with
variance reported as an explicit `0.00 (deterministic)`.

That 100% is not a boast. These are set comparisons and date arithmetic, and
anything less would be a bug. It is reported next to the model numbers precisely
because the contrast is the argument: the highest-value component in this bet is
the one with no model in it.

---

## Finding 2: extraction is trustworthy, which is a different question

The cycle-time criterion settles whether extraction makes onboarding *faster*.
It does not settle whether extraction can be trusted to *auto-populate a carrier
submission*. That is a data-quality question with its own answer, and I built
the extractor to get it. A kill is more credible when you built the thing than
when you only modelled it.

A second criterion, registered before running:

> Accuracy alone cannot decide this, because the same accuracy figure means
> opposite things depending on how it fails. A field returned **null** is a
> cheap failure. A person reviews it. A field returned as a **confident wrong
> value** is an expensive one. It posts to a carrier and the packet comes back
> days later. **If confident-wrong on the danger fields (NPN, licence number,
> expiration date) exceeds 2%, auto-population is dead** and extraction ships as
> a review accelerator with every field surfaced for confirmation.

Result on 12 documents, 96 field values, `claude-opus-5`:

| | |
|---|---:|
| Accuracy | **100%** |
| Nulls (safe failure) | 0 |
| Confident wrong (costly failure) | **0** |
| Excerpts dropped in verification | 0 |
| Confident-wrong on danger fields | **0 / 36 (0.0%)** |
| Cost | $0.3938 |
| Latency | ~7s per document |

Every planted hazard survived: the leading-zero NPN under a low-contrast
watermark, the `DD-MMM-YYYY` date among `MM/DD/YYYY` ones, the states printed in
full where the rest abbreviate. The leading zero is the one I expected to lose, a reader that treats an NPN as a number drops it silently and produces a value
that still *looks* valid.

**The criterion holds.** Auto-population is viable for these fields, with the
rest surfaced for review.

### Why every field is optional

`LicenseExtraction` declares every field as `str | None`. That is not defensive
typing. It is the schema encoding of the prompt's most important instruction. A
model with no legal way to say "I cannot read this" produces a confident value
instead. Making null representable is what makes the ratio measurable at all.

Each returned field also carries a verbatim excerpt, checked afterwards against
the document's own text layer read independently through PyMuPDF. An excerpt
that is not in the document was composed rather than read, and the field
carrying it is nulled and counted.

---

## What broke

**Five defects, all found by the evals rather than by reading the code.** Every
one produced a wrong number rather than a crash, which is the category that
survives code review.

1. **`_parse_date` upper-cased its format string as well as its value.**
   `"%m/%d/%Y".upper()` is `"%M/%D/%Y"`, `%M` is minutes and `%D` is not a
   directive. Every licence in the corpus parsed as unreadable, and all twelve
   agents were reported with an unreadable expiry. Recall looked fine; precision
   was 29%.
2. **Four seeds targeted a carrier whose E&O minimum they did not meet.** The
   engine was right and my cohort was wrong.
3. **One seed targeted a carrier whose required lines it did not hold.** Same
   shape.
4. **The extraction scorer compared `lines_of_authority` against internal codes**
   while the model correctly returned the printed labels, marking every correct
   extraction wrong. The printed labels now live in the shared source that the
   renderer and the ground truth both read.
5. **The negative control caught a flaw in itself.** Its leading-zero case ran
   against an NPN with no leading zero, so it compared a correct value with
   itself and reported a scorer failure that was really a test bug.

**The scorer is verified by a negative control.** A perfect score is exactly
when a scorer deserves least trust: one that always returns 100% and one that is
correct produce identical output on a clean run. Seven planted errors must be
caught. A wrong NPN, a stripped leading zero, a normalised state, a reformatted
date, a null, a dropped line of authority, and an unchanged value must still
pass. Run it with `python -m eval.negative_control`.

---

## The cohort

Twelve agents, four carriers, ten pipeline steps, all generated from
`tools/onboarding_data.py`. Real onboarding records are personnel files, names, producer numbers, background results, banking details, and no amount of
masking makes them safe for a public demo.

Generating them buys what the real records could not: because each licence is
*rendered from* the structured values, ground truth is exact, and the generator
re-reads every rendered PDF to confirm each value survived the layout engine
rather than assuming it did.

**The limits, stated plainly.**

- **The durations are plausible, not observed.** They are the single input the
  headline rests on, and the first thing a reader should push on. The sensitivity
  table is there because the conclusion should not depend on my getting them
  right, and it does not.
- **The extraction result is a ceiling, not a forecast.** These are clean vector
  PDFs this repository generated. The eval measures transcription logic under
  planted hazards, not robustness to a photocopy shot on a phone at an angle.
  100% here should be read as "no *logic* failure was found", not as an expected
  field rate on real documents.
- **The rules and the seeds share an author.** A misunderstood carrier
  requirement would be misunderstood identically in both, and the score would
  still be 100%. The number says the engine does what it was specified to do,
  not that the specification is right.

---

## What I would need before this touches a real cohort

- **The real touch/wait split**, from the actual workflow system. Everything
  above is a model. It is a model whose conclusion survives large errors in its
  inputs, but it is still a model, and the first move is to replace the assumed
  durations with measured ones.
- **The real rework rate.** The rule engine's value is entirely a function of
  how often packets bounce and how long a bounce costs. One agent in twelve here
  is my assumption, not an observation.
- **Carrier requirements from the carriers**, versioned and dated. A requirement
  that changed last quarter against a rule written this quarter produces a
  confidently wrong "complete". The same failure mode as a stale underwriting
  guide in the sibling project.
- **A human in front of extraction regardless of the number.** 100% on twelve
  clean documents does not license unattended posting to a carrier system. The
  build that follows from this is review-accelerating, with every field showing
  its source.

---

## What this cost

| | |
|---|---:|
| Extraction sweep, 12 documents | **$0.3938** |
| Cycle-time model and rule engine | **$0.00**. No model calls |
| Build hours | Not instrumented |

The two components that produced the finding cost nothing to run, which is the
economic version of the same point: the cheapest thing in this project is the
thing that decided it.

Build hours are not reconstructed here. A figure recalled after the fact is not
a measurement, and this document should not contain one.
