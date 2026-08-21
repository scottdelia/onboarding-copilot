"""Where the days go, and which of them software can remove.

WHY THIS MODULE EXISTS BEFORE ANY MODEL CALL
--------------------------------------------
The obvious build for "onboarding takes days, what if it took hours" is a model
that reads the licensing paperwork. This module exists to test that idea before
anyone builds it, because the arithmetic is cheap and the build is not.

Every step in the pipeline is split into two quantities that get conflated
constantly and behave nothing alike:

  touch time  -- somebody is actively working. Software can compress this.
  wait time   -- the work is sitting in a queue. A state department of
                 insurance, a background vendor, a carrier's appointment desk.
                 Nothing built here shortens it.

Sum those separately across a cohort and the question stops being rhetorical.
If wait time dominates, "days to hours" is not available at any level of
extraction accuracy, and a project promising it will fail for reasons that have
nothing to do with the model.

THE THREE LEVERS, MODELLED SEPARATELY
-------------------------------------
Rather than one "with AI" number, each lever is modelled on its own so the
comparison between them is visible:

  extraction   -- reads the documents, cutting touch minutes on the steps where
                  transcription is most of the work.
  rule_engine  -- checks the packet against every target carrier's requirements
                  at submission, so a defect is caught before it enters a
                  carrier queue rather than after.
  nudge        -- chases work that is actionable and untouched, recovering idle
                  time that belongs to nobody.

The first is the one everybody builds. Whether it is the one that matters is an
empirical question, and this is the instrument that answers it.

UNITS AND THE ONE ASSUMPTION THAT MATTERS
-----------------------------------------
Everything is calendar hours. Carrier queues are quoted in business days and
converted at `BUSINESS_TO_CALENDAR`, because an agent waiting on an appointment
experiences the weekend.

The step durations are plausible, not observed -- they are stated as assumptions
and are the first thing a reader should push on. The finding does not rest on
their precision: it rests on an order-of-magnitude gap, and `sensitivity()`
reports whether the conclusion survives halving or doubling them rather than
asserting that it does.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

# A queue quoted in business days is experienced in calendar days. Five business
# days is seven calendar days, so business-day figures are scaled by 7/5.
BUSINESS_TO_CALENDAR = 7 / 5

# What each lever is assumed to remove. These are the model's second set of
# assumptions and they are deliberately generous to the lever most likely to be
# overrated -- if extraction still does not move the total when handed a 70%
# cut, it will not move it at a realistic one.
EXTRACTION_TOUCH_REDUCTION = 0.70
NUDGE_IDLE_REDUCTION = 0.80


@dataclass(frozen=True)
class StepTiming:
    """One step of one agent's pipeline, decomposed."""

    step_id: str
    name: str
    owner: str
    touch_hours: float
    wait_hours: float
    idle_hours: float
    automatable_by: str
    depends_on: tuple[str, ...]

    @property
    def duration_hours(self) -> float:
        """Elapsed time this step contributes when it is on the critical path."""
        return self.touch_hours + self.wait_hours + self.idle_hours

    @property
    def is_external(self) -> bool:
        """True when the elapsed time belongs to somebody outside the business."""
        return self.owner in {"carrier", "state_doi", "vendor"}


@dataclass(frozen=True)
class AgentCycleTime:
    """One agent's timeline, baseline and under each lever."""

    agent_id: str
    display_name: str
    steps: tuple[StepTiming, ...]
    baseline_hours: float
    # The part of the baseline nobody here can touch.
    external_wait_hours: float
    internal_touch_hours: float
    # Queue time inside our own process -- a packet sitting in an ops backlog.
    # Distinct from external wait because it is ours to shorten, and distinct
    # from idle because idle is time a step was actionable and nobody had picked
    # it up at all. Splitting them out was not cosmetic: lumped together they
    # left 2.2% of the critical path unattributed, and a decomposition that does
    # not sum to its own total invites the reader to distrust the rest of it.
    internal_queue_hours: float
    internal_idle_hours: float
    # Elapsed time lost to a packet rejected and resubmitted.
    rework_hours: float
    # The steps that actually set the timeline. Everything else finished while
    # these were running and could be made instant without moving the total.
    critical_chain: tuple[str, ...]
    # Critical-path total under each lever, applied on its own.
    with_extraction_hours: float
    with_rule_engine_hours: float
    with_nudge_hours: float
    # All three at once. Not the sum of the individual savings, because they
    # overlap on the critical path.
    with_all_hours: float


def _critical_path(
    steps: Iterable[StepTiming],
    *,
    touch_scale: float = 1.0,
    idle_scale: float = 1.0,
) -> tuple[float, tuple[str, ...]]:
    """Longest dependency chain through the pipeline, and which steps are on it.

    Summing every step would overstate the total badly: a background check and a
    state licence lookup both depend only on the application and run at the same
    time, so the pipeline pays the longer of the two, not both.

    Returning the chain as well as the total is what lets the decomposition add
    up. An earlier version summed external wait across *every* step and reported
    103.7% of the baseline -- true as a sum, meaningless as a share, and
    obviously wrong to any reader. Only the steps actually on the path
    contribute elapsed time, so only those get decomposed.

    Args:
        steps: The agent's decomposed steps.
        touch_scale: Multiplier on touch time, for modelling extraction.
        idle_scale: Multiplier on idle time, for modelling a nudge queue.

    Returns:
        Calendar hours along the critical path, and the step ids on it in order.
    """
    by_id = {step.step_id: step for step in steps}
    finish: dict[str, float] = {}
    # The dependency each step actually waited on -- the one that finished last.
    predecessor: dict[str, str | None] = {}

    def finish_of(step_id: str) -> float:
        if step_id in finish:
            return finish[step_id]
        step = by_id[step_id]

        deps = [dep for dep in step.depends_on if dep in by_id]
        if deps:
            latest = max(deps, key=finish_of)
            start = finish_of(latest)
            predecessor[step_id] = latest
        else:
            start = 0.0
            predecessor[step_id] = None

        duration = (
            step.touch_hours * touch_scale
            + step.wait_hours
            + step.idle_hours * idle_scale
        )
        finish[step_id] = start + duration
        return finish[step_id]

    for step_id in by_id:
        finish_of(step_id)

    if not finish:
        return 0.0, ()

    last = max(finish, key=lambda step_id: finish[step_id])
    chain: list[str] = []
    cursor: str | None = last
    while cursor is not None:
        chain.append(cursor)
        cursor = predecessor.get(cursor)
    chain.reverse()

    return finish[last], tuple(chain)


def _critical_path_hours(
    steps: Iterable[StepTiming],
    *,
    touch_scale: float = 1.0,
    idle_scale: float = 1.0,
) -> float:
    """Total along the critical path. See `_critical_path`."""
    return _critical_path(steps, touch_scale=touch_scale, idle_scale=idle_scale)[0]


def build_agent_timings(agent: dict) -> tuple[StepTiming, ...]:
    """Decompose one cohort record into per-step timings.

    Reads the cohort record rather than the seed definitions, so the model is
    computing from the same data the API serves rather than from a private view
    of it.
    """
    timings: list[StepTiming] = []
    for step in agent["steps"]:
        timings.append(
            StepTiming(
                step_id=step["step_id"],
                name=step["name"],
                owner=step["owner"],
                touch_hours=step["touch_minutes"] / 60,
                wait_hours=step["wait_hours"],
                idle_hours=step.get("idle_hours", 0.0),
                automatable_by=step["automatable_by"],
                depends_on=tuple(step.get("depends_on", ())),
            )
        )
    return tuple(timings)


def agent_cycle_time(agent: dict) -> AgentCycleTime:
    """Compute one agent's baseline and per-lever timelines."""
    steps = build_agent_timings(agent)
    rework_hours = float(agent.get("rework_days", 0.0)) * 24

    baseline_path_hours, critical_chain = _critical_path(steps)
    baseline = baseline_path_hours + rework_hours
    # Only steps on the critical path contribute elapsed time, so only those are
    # decomposed. Summing across all steps double-counts the parallel branches.
    on_path = tuple(step for step in steps if step.step_id in set(critical_chain))

    # Extraction cuts touch time on the steps where reading a document is most
    # of the work. It cannot touch a queue.
    extraction_steps = tuple(
        StepTiming(
            **{
                **step.__dict__,
                "touch_hours": step.touch_hours
                * (
                    1 - EXTRACTION_TOUCH_REDUCTION
                    if step.automatable_by == "extraction"
                    else 1
                ),
            }
        )
        for step in steps
    )
    with_extraction = _critical_path_hours(extraction_steps) + rework_hours

    # The rule engine does not make any step faster. It removes the rework loop
    # entirely, by catching the defect on the near side of the carrier queue.
    with_rule_engine = _critical_path_hours(steps)

    # A nudge queue recovers time that was actionable and untouched.
    nudge_steps = tuple(
        StepTiming(
            **{
                **step.__dict__,
                "idle_hours": step.idle_hours * (1 - NUDGE_IDLE_REDUCTION),
            }
        )
        for step in steps
    )
    with_nudge = _critical_path_hours(nudge_steps) + rework_hours

    all_steps = tuple(
        StepTiming(
            **{
                **step.__dict__,
                "touch_hours": step.touch_hours
                * (
                    1 - EXTRACTION_TOUCH_REDUCTION
                    if step.automatable_by == "extraction"
                    else 1
                ),
                "idle_hours": step.idle_hours * (1 - NUDGE_IDLE_REDUCTION),
            }
        )
        for step in steps
    )
    with_all = _critical_path_hours(all_steps)

    return AgentCycleTime(
        agent_id=agent["agent_id"],
        display_name=agent["display_name"],
        steps=steps,
        baseline_hours=baseline,
        # Bucketed by whose time it is, so the four figures account for the
        # whole critical path rather than most of it. An external step's own
        # touch minutes are somebody else's minutes and belong in their bucket:
        # leaving them out left 2.2% of the baseline unattributed, which invites
        # exactly the question the decomposition exists to answer.
        # Bucketed by whose time it is, so the figures account for the whole
        # critical path rather than most of it. An external step's own touch
        # minutes are somebody else's minutes and belong in their bucket.
        external_wait_hours=sum(s.duration_hours for s in on_path if s.is_external),
        internal_touch_hours=sum(
            s.touch_hours for s in on_path if not s.is_external
        ),
        internal_queue_hours=sum(
            s.wait_hours for s in on_path if not s.is_external
        ),
        internal_idle_hours=sum(
            s.idle_hours for s in on_path if not s.is_external
        ),
        rework_hours=rework_hours,
        critical_chain=critical_chain,
        with_extraction_hours=with_extraction,
        with_rule_engine_hours=with_rule_engine,
        with_nudge_hours=with_nudge,
        with_all_hours=with_all,
    )


def cohort_cycle_time(cohort: list[dict]) -> dict:
    """The headline arithmetic across the whole cohort.

    Returns a dict rather than a dataclass because this is what the API serves
    and what the write-up quotes; keeping one shape avoids a translation layer
    that could disagree with itself.
    """
    per_agent = [agent_cycle_time(agent) for agent in cohort]
    n = len(per_agent)
    if n == 0:
        raise ValueError("cohort is empty")

    mean = lambda values: sum(values) / n  # noqa: E731 - local, single use

    baseline = mean([a.baseline_hours for a in per_agent])
    external = mean([a.external_wait_hours for a in per_agent])
    touch = mean([a.internal_touch_hours for a in per_agent])
    queue = mean([a.internal_queue_hours for a in per_agent])
    idle = mean([a.internal_idle_hours for a in per_agent])
    rework = mean([a.rework_hours for a in per_agent])

    def saving(attr: str) -> dict:
        after = mean([getattr(a, attr) for a in per_agent])
        removed = baseline - after
        return {
            "after_hours": round(after, 1),
            "hours_removed": round(removed, 1),
            "percent_removed": round(100 * removed / baseline, 1) if baseline else 0.0,
        }

    return {
        "cohort_size": n,
        "baseline": {
            "mean_hours": round(baseline, 1),
            "mean_days": round(baseline / 24, 1),
        },
        "decomposition": {
            # The floor. No accuracy figure moves this.
            "external_wait_hours": round(external, 1),
            "external_wait_share_pct": round(100 * external / baseline, 1),
            "internal_touch_hours": round(touch, 1),
            "internal_touch_share_pct": round(100 * touch / baseline, 1),
            "internal_queue_hours": round(queue, 1),
            "internal_queue_share_pct": round(100 * queue / baseline, 1),
            "internal_idle_hours": round(idle, 1),
            "internal_idle_share_pct": round(100 * idle / baseline, 1),
            "rework_hours": round(rework, 1),
            "rework_share_pct": round(100 * rework / baseline, 1),
        },
        "levers": {
            "extraction": saving("with_extraction_hours"),
            "rule_engine": saving("with_rule_engine_hours"),
            "nudge": saving("with_nudge_hours"),
            "all_three": saving("with_all_hours"),
        },
        "assumptions": {
            "extraction_touch_reduction_pct": round(
                100 * EXTRACTION_TOUCH_REDUCTION, 0
            ),
            "nudge_idle_reduction_pct": round(100 * NUDGE_IDLE_REDUCTION, 0),
            "business_to_calendar_factor": BUSINESS_TO_CALENDAR,
            "note": (
                "Step durations are plausible, not observed. The extraction "
                "reduction is deliberately generous: if a 70% cut in "
                "transcription time still does not move the total, a realistic "
                "one will not either."
            ),
        },
    }


def sensitivity(cohort: list[dict]) -> list[dict]:
    """Does the conclusion survive being wrong about the inputs?

    A finding that only holds at one set of assumed durations is not a finding.
    This re-runs the comparison with each assumption pushed hard in the
    direction that would most favour extraction, and reports whether extraction
    overtakes the rule engine at any of them.
    """
    results: list[dict] = []

    for label, scale in (
        ("my timings are right", 1.0),
        ("carriers were twice as fast", 0.5),
        ("carriers were four times as fast", 0.25),
    ):
        scaled = []
        for agent in cohort:
            copy = {**agent, "steps": [dict(step) for step in agent["steps"]]}
            for step in copy["steps"]:
                if step["owner"] in {"carrier", "state_doi", "vendor"}:
                    step["wait_hours"] = step["wait_hours"] * scale
            scaled.append(copy)

        summary = cohort_cycle_time(scaled)
        extraction = summary["levers"]["extraction"]["percent_removed"]
        rule_engine = summary["levers"]["rule_engine"]["percent_removed"]
        results.append(
            {
                "scenario": label,
                "external_wait_share_pct": summary["decomposition"][
                    "external_wait_share_pct"
                ],
                "extraction_pct": extraction,
                "rule_engine_pct": rule_engine,
                "extraction_wins": extraction > rule_engine,
            }
        )

    return results
