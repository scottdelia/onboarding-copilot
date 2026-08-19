"""The structured source everything in this project is generated from.

WHY THE DATA IS SYNTHETIC AND WHY THAT IS AN ADVANTAGE
------------------------------------------------------
Real agent onboarding records are personnel files: names, national producer
numbers, background-check results, banking details. None of that can appear in a
public demo, and no amount of masking makes it safe to try.

Generating the cohort removes that problem and buys something the real records
could not: because every licence document is *rendered from* the values in this
file, the ground truth for extraction is known exactly -- the string that was
printed, and the page it printed on. Extraction accuracy becomes measurable
rather than spot-checked.

The same trick applies to the rule engine. `planted_gaps` on each seed is the
list of requirement ids that must fire for that agent. The engine never reads
this file; it reads the cohort record. So agreement means the engine recovered
the planted defect through the whole chain, which is the thing worth measuring.

WHAT THE NUMBERS ARE AND ARE NOT
--------------------------------
The step durations below are plausible, not observed. They are stated as
assumptions in the write-up and they are the single input the headline finding
rests on, so they are the first thing a reader should push back on. What the
model does *not* depend on is their precision: the finding is that external
queue time dominates by roughly an order of magnitude, and that conclusion
survives halving or doubling any individual figure. `docs/FINDINGS.md` shows the
sensitivity rather than asserting it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

# Who is holding the work. This is the load-bearing distinction in the whole
# project: "us" is ops and the agent, and everything else is somebody else's
# queue that no software of ours shortens.
Owner = Literal["agent", "ops", "carrier", "state_doi", "vendor"]

# Ops and the agent are the only owners a tool of ours can act on. Splitting the
# cohort by this is what turns "onboarding takes days" into "which days".
INTERNAL_OWNERS: frozenset[str] = frozenset({"agent", "ops"})

StepStatus = Literal[
    "not_started",
    "in_progress",
    "waiting_external",
    "blocked",
    "complete",
    "not_applicable",
]

BlockerReason = Literal[
    "awaiting_state_doi",
    "awaiting_carrier_queue",
    "awaiting_agent_document",
    "awaiting_background_vendor",
    "data_mismatch",
    "missing_prerequisite",
    "none",
]

LineOfAuthority = Literal["life", "health", "variable_life", "property", "casualty"]


@dataclass(frozen=True)
class StepDefinition:
    """One stage of onboarding, with touch time and wait time kept apart.

    The separation is the entire instrument. `touch_minutes` is time somebody is
    actively working; `wait_hours` is elapsed time while nothing happens because
    the work sits in a queue. Software can compress the first. Only a different
    agreement with a third party compresses the second, and conflating them is
    how "we automated onboarding" ends up meaning "we saved twenty minutes of a
    nine-day process".
    """

    step_id: str
    name: str
    owner: Owner
    order: int
    # Active work by a person, in minutes.
    touch_minutes: int
    # Elapsed queue time, in hours. Zero for steps that are pure work.
    wait_hours: float
    # Steps that must complete first. Used to compute what is actually on the
    # critical path rather than assuming the list order is the timeline.
    depends_on: tuple[str, ...] = ()
    # True when this step repeats per carrier rather than once per agent.
    per_carrier: bool = False
    # What a tool of ours could plausibly remove, and how. `none` means the step
    # is somebody else's queue and is immovable from here.
    automatable_by: Literal["extraction", "rule_engine", "nudge", "none"] = "none"
    note: str = ""


# The pipeline. Ordering reflects the usual sequence; `depends_on` carries the
# real constraints, because several of these genuinely run in parallel and a
# model that summed them in list order would overstate the total badly.
STEPS: tuple[StepDefinition, ...] = (
    StepDefinition(
        step_id="application",
        name="Agent application submitted",
        owner="agent",
        order=1,
        touch_minutes=25,
        wait_hours=0,
        automatable_by="extraction",
        note="Form fill. The only step where reading a document end to end is most of the work.",
    ),
    StepDefinition(
        step_id="packet_review",
        name="Contracting packet reviewed for completeness",
        owner="ops",
        order=2,
        touch_minutes=18,
        wait_hours=4,
        depends_on=("application",),
        automatable_by="rule_engine",
        note=(
            "The highest-leverage step in the pipeline and the least glamorous. "
            "A defect caught here costs minutes; the same defect caught by a "
            "carrier costs a full round trip through their queue."
        ),
    ),
    StepDefinition(
        step_id="background_check",
        name="Background screening",
        owner="vendor",
        order=3,
        touch_minutes=5,
        wait_hours=36,
        depends_on=("application",),
        automatable_by="none",
        note="Third-party vendor SLA. Runs in parallel with licence verification.",
    ),
    StepDefinition(
        step_id="license_verification",
        name="Resident licence verified with the state",
        owner="state_doi",
        order=4,
        touch_minutes=8,
        wait_hours=52,
        depends_on=("application",),
        automatable_by="none",
        note=(
            "State department of insurance lookup. Nothing built here changes "
            "how long a state takes to answer."
        ),
    ),
    StepDefinition(
        step_id="aml_certification",
        name="AML certification completed",
        owner="agent",
        order=5,
        touch_minutes=95,
        wait_hours=0,
        automatable_by="nudge",
        note=(
            "A self-paced course. The elapsed time is dominated by when the "
            "agent gets round to it, not by the 95 minutes it takes."
        ),
    ),
    StepDefinition(
        step_id="eo_coverage",
        name="Errors and omissions coverage evidenced",
        owner="agent",
        order=6,
        touch_minutes=20,
        wait_hours=8,
        automatable_by="nudge",
    ),
    StepDefinition(
        step_id="carrier_submission",
        name="Carrier appointment packet submitted",
        owner="ops",
        order=7,
        touch_minutes=22,
        wait_hours=2,
        depends_on=("packet_review", "license_verification"),
        per_carrier=True,
        automatable_by="extraction",
    ),
    StepDefinition(
        step_id="carrier_appointment",
        name="Carrier appointment approved",
        owner="carrier",
        order=8,
        touch_minutes=0,
        wait_hours=132,
        depends_on=("carrier_submission", "background_check"),
        per_carrier=True,
        automatable_by="none",
        note=(
            "The single largest block of elapsed time in the pipeline, and "
            "entirely inside a carrier's queue. This is the number that decides "
            "the bet."
        ),
    ),
    StepDefinition(
        step_id="banking_setup",
        name="Commission banking and EFT set up",
        owner="ops",
        order=9,
        touch_minutes=15,
        wait_hours=6,
        depends_on=("carrier_appointment",),
        automatable_by="none",
    ),
    StepDefinition(
        step_id="crm_provisioning",
        name="CRM and agent portal provisioned",
        owner="ops",
        order=10,
        touch_minutes=12,
        wait_hours=3,
        depends_on=("carrier_appointment",),
        automatable_by="none",
    ),
)

STEPS_BY_ID: dict[str, StepDefinition] = {step.step_id: step for step in STEPS}


@dataclass(frozen=True)
class CarrierRequirements:
    """What one carrier demands before it will appoint an agent.

    Deliberately inconsistent between carriers, because that inconsistency is
    the actual problem. A packet that satisfies one carrier and fails another on
    a single line is the defect this project is built to catch, and a set of
    carriers that all wanted the same thing would not test the engine at all.
    """

    carrier_id: str
    name: str
    # States the carrier will appoint in. A resident licence outside this set is
    # a blocking gap.
    appointment_states: frozenset[str]
    required_lines: frozenset[LineOfAuthority]
    aml_required: bool
    # Minimum errors-and-omissions coverage, in dollars.
    eo_minimum_usd: int
    # Whether the carrier rejects a legal-name mismatch outright or queries it.
    name_match_strict: bool
    # Typical business days sitting in this carrier's appointment queue.
    appointment_queue_days: int


CARRIERS: tuple[CarrierRequirements, ...] = (
    CarrierRequirements(
        carrier_id="northstar",
        name="Northstar Mutual Life",
        appointment_states=frozenset({"NC", "SC", "GA", "TN", "VA", "FL", "TX"}),
        required_lines=frozenset({"life"}),
        aml_required=True,
        eo_minimum_usd=1_000_000,
        name_match_strict=True,
        appointment_queue_days=7,
    ),
    CarrierRequirements(
        carrier_id="cardinal",
        name="Cardinal Assurance Company",
        appointment_states=frozenset({"NC", "SC", "GA", "TN", "VA", "FL", "TX", "OH"}),
        required_lines=frozenset({"life", "health"}),
        aml_required=True,
        eo_minimum_usd=1_000_000,
        name_match_strict=False,
        appointment_queue_days=5,
    ),
    CarrierRequirements(
        carrier_id="meridian",
        name="Meridian Life & Annuity",
        appointment_states=frozenset({"NC", "GA", "TN", "FL"}),
        required_lines=frozenset({"life"}),
        aml_required=False,
        eo_minimum_usd=500_000,
        name_match_strict=True,
        appointment_queue_days=10,
    ),
    CarrierRequirements(
        carrier_id="granite",
        name="Granite Peak Financial Group",
        appointment_states=frozenset({"NC", "SC", "VA", "TX", "OH"}),
        required_lines=frozenset({"life"}),
        aml_required=True,
        eo_minimum_usd=2_000_000,
        name_match_strict=True,
        appointment_queue_days=8,
    ),
)

CARRIERS_BY_ID: dict[str, CarrierRequirements] = {c.carrier_id: c for c in CARRIERS}


@dataclass(frozen=True)
class StepState:
    """Where one agent stands on one step, and how long it has taken."""

    step_id: str
    status: StepStatus
    blocker: BlockerReason = "none"
    blocker_detail: str = ""
    # Hours since this step became actionable. For a completed step this is how
    # long it took; for an open one, how long it has been sitting.
    elapsed_hours: float = 0.0
    # Hours the step sat actionable before anyone touched it. This is the number
    # that exposes idle handoffs -- time nobody is waiting on a third party for,
    # and nobody is working on either.
    idle_hours: float = 0.0
    carrier_id: str | None = None


@dataclass(frozen=True)
class AgentSeed:
    """One in-flight onboarding, and the exact values printed on its licence.

    The `license_*` fields are the ground truth for extraction: the generator
    prints these strings onto the PDF and records where each one landed, so a
    field the model reads back can be compared to the character that was
    rendered rather than to somebody's transcription of it.
    """

    agent_id: str
    display_name: str
    # The name as it appears on the licence. Differs from display_name for the
    # agents carrying a legal-name mismatch, which is the point.
    license_full_name: str
    npn: str
    license_number: str
    resident_state: str
    # How the state is printed on this licence. Two carriers of the same data
    # print "NC" and "North Carolina"; an extractor that normalises silently
    # hides which one it saw.
    state_printed_as: str
    license_type: str
    lines_of_authority: tuple[LineOfAuthority, ...]
    issue_date: str
    expiration_date: str
    # Date format used on this licence, so the generator can render the awkward
    # ones without the extractor being told which to expect.
    date_format: Literal["mm/dd/yyyy", "dd-mmm-yyyy"]
    aml_completed: bool
    eo_coverage_usd: int
    target_carriers: tuple[str, ...]
    steps: tuple[StepState, ...]
    # Requirement ids that must fire for this agent. The engine never reads this.
    planted_gaps: tuple[str, ...]
    # Rendering hazards, so the extraction eval has something to fail on.
    watermark_over_npn: bool = False
    # A short note explaining what this seed exists to demonstrate.
    demonstrates: str = ""
    # Days lost to a packet that was rejected and resubmitted. Nonzero only for
    # the seeds carrying a defect a completeness check would have caught.
    rework_days: float = 0.0


def _clean_steps(
    complete_through: int,
    *,
    carriers: tuple[str, ...],
    open_step: str | None = None,
    open_status: StepStatus = "waiting_external",
    blocker: BlockerReason = "none",
    blocker_detail: str = "",
    open_elapsed: float = 0.0,
    idle_hours: float = 0.0,
) -> tuple[StepState, ...]:
    """Build a step list where everything up to `complete_through` is done.

    A helper rather than twelve hand-written lists: the interesting variation
    between seeds is which step is open and why, and hand-writing the completed
    prefix ten times would bury that in noise.
    """
    states: list[StepState] = []
    for step in STEPS:
        if step.order <= complete_through:
            states.append(
                StepState(
                    step_id=step.step_id,
                    status="complete",
                    elapsed_hours=step.wait_hours + step.touch_minutes / 60,
                )
            )
        elif step.step_id == open_step:
            states.append(
                StepState(
                    step_id=step.step_id,
                    status=open_status,
                    blocker=blocker,
                    blocker_detail=blocker_detail,
                    elapsed_hours=open_elapsed,
                    idle_hours=idle_hours,
                    carrier_id=carriers[0] if step.per_carrier and carriers else None,
                )
            )
        else:
            states.append(StepState(step_id=step.step_id, status="not_started"))
    return tuple(states)


# ---------------------------------------------------------------------------
# The cohort.
#
# Twelve agents chosen to cover the shapes that matter, not to look busy. Four
# carry a packet defect that a completeness check at submission would have
# caught before it reached a carrier queue -- those are the seeds that produce
# the project's actual finding. Three carry a rendering hazard so the extraction
# eval has something to be wrong about. The rest are the ordinary distribution
# a cohort needs to have for an average to mean anything.
# ---------------------------------------------------------------------------

AGENT_SEEDS: tuple[AgentSeed, ...] = (
    AgentSeed(
        agent_id="a01",
        display_name="Dana Whitfield",
        license_full_name="Dana R Whitfield",
        npn="20418877",
        license_number="NC-1884233",
        resident_state="NC",
        state_printed_as="NC",
        license_type="Resident Producer",
        lines_of_authority=("life", "health"),
        issue_date="03/14/2024",
        expiration_date="03/31/2027",
        date_format="mm/dd/yyyy",
        aml_completed=True,
        eo_coverage_usd=1_000_000,
        target_carriers=("northstar", "cardinal"),
        steps=_clean_steps(
            8,
            carriers=("northstar", "cardinal"),
            open_step="banking_setup",
            open_status="in_progress",
            open_elapsed=3.0,
        ),
        planted_gaps=(),
        demonstrates="The clean path. Everything correct, nearly finished.",
    ),
    AgentSeed(
        agent_id="a02",
        display_name="Marcus Bell",
        license_full_name="Marcus A Bell",
        npn="20455310",
        license_number="SC-9920145",
        resident_state="SC",
        state_printed_as="SC",
        license_type="Resident Producer",
        lines_of_authority=("life",),
        issue_date="01/09/2025",
        expiration_date="01/31/2028",
        date_format="mm/dd/yyyy",
        aml_completed=True,
        # Granite Peak requires $2M; a $1M limit here would be a real gap,
        # and these agents exist to demonstrate something else.
        eo_coverage_usd=2_000_000,
        target_carriers=("northstar", "granite"),
        steps=_clean_steps(
            7,
            carriers=("granite",),
            open_step="carrier_appointment",
            blocker="awaiting_carrier_queue",
            blocker_detail="Granite Peak appointment queue, day 6 of a typical 8.",
            open_elapsed=146.0,
        ),
        planted_gaps=(),
        demonstrates=(
            "Nothing is wrong and nothing is moving. Six days of elapsed time "
            "with zero defects and zero work available to anyone here."
        ),
    ),
    AgentSeed(
        agent_id="a03",
        display_name="Trish Okonkwo",
        # The licence says Patricia; the application said Trish. Northstar
        # rejects on a strict name match, so this packet bounced.
        license_full_name="Patricia N Okonkwo",
        npn="20461902",
        license_number="NC-1902871",
        resident_state="NC",
        state_printed_as="North Carolina",
        license_type="Resident Producer",
        lines_of_authority=("life", "health"),
        issue_date="06/02/2024",
        expiration_date="06/30/2027",
        date_format="mm/dd/yyyy",
        aml_completed=True,
        eo_coverage_usd=1_000_000,
        target_carriers=("northstar", "meridian"),
        steps=_clean_steps(
            7,
            carriers=("northstar",),
            open_step="carrier_appointment",
            blocker="data_mismatch",
            blocker_detail=(
                "Northstar returned the packet: application name 'Trish Okonkwo' "
                "does not match licence name 'Patricia N Okonkwo'."
            ),
            open_elapsed=171.0,
        ),
        planted_gaps=("name_match",),
        rework_days=4.0,
        demonstrates=(
            "The finding, in one agent. A one-line defect that a check at "
            "submission catches in seconds cost four days because a carrier "
            "caught it instead. Also prints its state in full, which the "
            "extractor is not told to expect."
        ),
    ),
    AgentSeed(
        agent_id="a04",
        display_name="Devon Park",
        license_full_name="Devon Park",
        npn="20470044",
        license_number="GA-4410882",
        resident_state="GA",
        state_printed_as="GA",
        license_type="Resident Producer",
        # No life line. Every target carrier requires it.
        lines_of_authority=("health",),
        issue_date="09/18/2024",
        expiration_date="09/30/2027",
        date_format="mm/dd/yyyy",
        aml_completed=True,
        eo_coverage_usd=1_000_000,
        target_carriers=("northstar", "cardinal"),
        steps=_clean_steps(
            6,
            carriers=("northstar", "cardinal"),
            open_step="carrier_submission",
            open_status="blocked",
            blocker="missing_prerequisite",
            blocker_detail="Licence carries no life line of authority.",
            open_elapsed=58.0,
            idle_hours=41.0,
        ),
        planted_gaps=("line_of_authority:northstar", "line_of_authority:cardinal"),
        rework_days=0.0,
        demonstrates=(
            "A blocking defect caught before submission. Compare with a03: the "
            "same class of problem, found on the right side of the carrier "
            "queue, costs hours instead of days."
        ),
    ),
    AgentSeed(
        agent_id="a05",
        display_name="Renata Alvarez",
        license_full_name="Renata M Alvarez",
        npn="20483115",
        license_number="FL-7781204",
        resident_state="FL",
        state_printed_as="FL",
        license_type="Resident Producer",
        lines_of_authority=("life", "health"),
        # Already expired against the cohort anchor date.
        issue_date="11/05/2021",
        expiration_date="11/30/2024",
        date_format="mm/dd/yyyy",
        aml_completed=True,
        eo_coverage_usd=1_000_000,
        target_carriers=("meridian", "cardinal"),
        steps=_clean_steps(
            2,
            carriers=("meridian", "cardinal"),
            open_step="license_verification",
            blocker="data_mismatch",
            blocker_detail="State returned the licence as expired.",
            open_elapsed=64.0,
        ),
        planted_gaps=("license_expired",),
        demonstrates="An expired licence, which no downstream step can proceed past.",
    ),
    AgentSeed(
        agent_id="a06",
        display_name="Jerome Baptiste",
        license_full_name="Jerome Baptiste",
        # Leading zero. A reader that treats an NPN as a number drops it, and the
        # packet then fails a carrier match on a value that looks correct.
        npn="0204910",
        license_number="TN-3320981",
        resident_state="TN",
        state_printed_as="TN",
        license_type="Resident Producer",
        lines_of_authority=("life",),
        issue_date="14-FEB-2025",
        expiration_date="28-FEB-2028",
        date_format="dd-mmm-yyyy",
        aml_completed=True,
        eo_coverage_usd=1_000_000,
        target_carriers=("northstar", "meridian"),
        steps=_clean_steps(
            6,
            carriers=("northstar",),
            open_step="carrier_submission",
            open_status="in_progress",
            open_elapsed=9.0,
        ),
        planted_gaps=(),
        watermark_over_npn=True,
        demonstrates=(
            "Three extraction hazards on one document: a leading-zero NPN, a "
            "DD-MMM-YYYY date where every other licence uses MM/DD/YYYY, and a "
            "watermark across the NPN block."
        ),
    ),
    AgentSeed(
        agent_id="a07",
        display_name="Lindsey Corbin",
        license_full_name="Lindsey Corbin",
        npn="20492260",
        license_number="VA-6650117",
        resident_state="VA",
        state_printed_as="VA",
        license_type="Resident Producer",
        lines_of_authority=("life",),
        issue_date="04/22/2024",
        expiration_date="04/30/2027",
        date_format="mm/dd/yyyy",
        aml_completed=True,
        # Granite Peak requires $2M; a $1M limit here would be a real gap,
        # and these agents exist to demonstrate something else.
        eo_coverage_usd=2_000_000,
        target_carriers=("northstar", "granite"),
        steps=_clean_steps(
            5,
            carriers=("northstar", "granite"),
            open_step="eo_coverage",
            open_status="waiting_external",
            blocker="awaiting_agent_document",
            blocker_detail="E&O certificate requested. No reply.",
            open_elapsed=117.0,
            # Nearly five days actionable with nobody chasing it.
            idle_hours=112.0,
        ),
        planted_gaps=(),
        demonstrates=(
            "The idle handoff. Not blocked by a third party and not being "
            "worked -- just sitting, because nobody was assigned to chase it."
        ),
    ),
    AgentSeed(
        agent_id="a08",
        display_name="Aaron Whitlock",
        license_full_name="Aaron Whitlock",
        npn="20501773",
        license_number="TX-2214665",
        resident_state="TX",
        state_printed_as="TX",
        license_type="Resident Producer",
        lines_of_authority=("life",),
        issue_date="02/08/2025",
        expiration_date="02/28/2028",
        date_format="mm/dd/yyyy",
        # AML not done. Northstar and Granite both require it.
        aml_completed=False,
        # Granite Peak requires $2M; a $1M limit here would be a real gap,
        # and these agents exist to demonstrate something else.
        eo_coverage_usd=2_000_000,
        target_carriers=("northstar", "granite"),
        steps=_clean_steps(
            4,
            carriers=("northstar", "granite"),
            open_step="aml_certification",
            open_status="waiting_external",
            blocker="awaiting_agent_document",
            blocker_detail="AML course not started.",
            open_elapsed=88.0,
            idle_hours=72.0,
        ),
        planted_gaps=("aml:northstar", "aml:granite"),
        demonstrates="An agent-owned task nobody nudged, blocking two carriers.",
    ),
    AgentSeed(
        agent_id="a09",
        display_name="Priya Raman",
        license_full_name="Priya Raman",
        npn="20511008",
        license_number="NC-1955402",
        resident_state="NC",
        state_printed_as="NC",
        license_type="Resident Producer",
        lines_of_authority=("life", "health"),
        issue_date="07/30/2024",
        expiration_date="07/31/2027",
        date_format="mm/dd/yyyy",
        aml_completed=True,
        # Below Granite's two-million minimum, above everyone else's.
        eo_coverage_usd=1_000_000,
        target_carriers=("granite", "cardinal"),
        steps=_clean_steps(
            6,
            carriers=("granite", "cardinal"),
            open_step="carrier_submission",
            open_status="blocked",
            blocker="missing_prerequisite",
            blocker_detail="E&O limit is below Granite Peak's minimum.",
            open_elapsed=31.0,
            idle_hours=22.0,
        ),
        planted_gaps=("eo_minimum:granite",),
        demonstrates=(
            "A defect against one carrier and not another, from identical "
            "paperwork. This is why the check has to be per carrier."
        ),
    ),
    AgentSeed(
        agent_id="a10",
        display_name="Curtis Nwosu",
        license_full_name="Curtis Nwosu",
        npn="20523641",
        license_number="OH-8810339",
        resident_state="OH",
        state_printed_as="OH",
        license_type="Resident Producer",
        # Cardinal requires life + health; a life-only licence would be a real
        # gap, and a10 exists to demonstrate the appointment-state check.
        lines_of_authority=("life", "health"),
        issue_date="10/11/2024",
        expiration_date="10/31/2027",
        date_format="mm/dd/yyyy",
        aml_completed=True,
        eo_coverage_usd=2_000_000,
        # Meridian does not appoint in Ohio.
        target_carriers=("cardinal", "meridian", "granite"),
        steps=_clean_steps(
            6,
            carriers=("cardinal", "granite"),
            open_step="carrier_submission",
            open_status="in_progress",
            open_elapsed=12.0,
        ),
        planted_gaps=("appointment_state:meridian",),
        demonstrates=(
            "A carrier that does not appoint in the agent's resident state -- "
            "knowable before submission and frequently discovered after."
        ),
    ),
    AgentSeed(
        agent_id="a11",
        display_name="Sofia Marchetti",
        license_full_name="Sofia Marchetti",
        npn="20530092",
        license_number="NC-1971558",
        resident_state="NC",
        state_printed_as="NC",
        license_type="Resident Producer",
        lines_of_authority=("life", "health", "variable_life"),
        issue_date="05/16/2024",
        expiration_date="05/31/2027",
        date_format="mm/dd/yyyy",
        aml_completed=True,
        eo_coverage_usd=2_000_000,
        target_carriers=("northstar", "cardinal", "meridian", "granite"),
        steps=_clean_steps(
            7,
            carriers=("meridian",),
            open_step="carrier_appointment",
            blocker="awaiting_carrier_queue",
            blocker_detail=(
                "Three of four carriers appointed. Meridian queue, day 8 of a "
                "typical 10."
            ),
            open_elapsed=194.0,
        ),
        planted_gaps=(),
        demonstrates=(
            "Four carriers, no defects, and still waiting -- because the total "
            "is set by the slowest queue, not by the average one."
        ),
    ),
    AgentSeed(
        agent_id="a12",
        display_name="Hector Delacroix",
        license_full_name="Hector Delacroix",
        npn="20544817",
        license_number="SC-9971230",
        resident_state="SC",
        state_printed_as="South Carolina",
        license_type="Resident Producer",
        lines_of_authority=("life",),
        issue_date="12/03/2024",
        expiration_date="12/31/2027",
        date_format="mm/dd/yyyy",
        aml_completed=True,
        # Granite Peak requires $2M; a $1M limit here would be a real gap,
        # and these agents exist to demonstrate something else.
        eo_coverage_usd=2_000_000,
        target_carriers=("northstar", "granite"),
        steps=_clean_steps(
            2,
            carriers=("northstar", "granite"),
            open_step="background_check",
            blocker="awaiting_background_vendor",
            blocker_detail="Vendor screening, day 2 of a typical 1 to 3.",
            open_elapsed=44.0,
        ),
        planted_gaps=(),
        demonstrates="Early in the pipeline, waiting on a vendor. Prints its state in full.",
    ),
)

AGENTS_BY_ID: dict[str, AgentSeed] = {seed.agent_id: seed for seed in AGENT_SEEDS}


# The cohort is described relative to an anchor rather than to real dates, so the
# board reads as live whenever it is opened and the tests stay reproducible.
# Expiry checks resolve against this, which is what makes a05's licence expired.
COHORT_ANCHOR_ISO = "2026-08-19T00:00:00Z"


def summary() -> dict[str, int]:
    """Counts used by the generator's console output and by the tests."""
    return {
        "agents": len(AGENT_SEEDS),
        "carriers": len(CARRIERS),
        "steps": len(STEPS),
        "agents_with_planted_gaps": sum(
            1 for seed in AGENT_SEEDS if seed.planted_gaps
        ),
        "planted_gaps": sum(len(seed.planted_gaps) for seed in AGENT_SEEDS),
        "agents_with_rework": sum(1 for seed in AGENT_SEEDS if seed.rework_days > 0),
    }


if __name__ == "__main__":
    for key, value in summary().items():
        print(f"{key:28} {value}")
