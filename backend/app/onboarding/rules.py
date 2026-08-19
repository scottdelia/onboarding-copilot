"""Packet completeness, checked against every target carrier's requirements.

WHY THIS IS NOT A MODEL, AND WHY THAT IS THE POINT
--------------------------------------------------
"Does this agent's licence carry the lines of authority Northstar requires" is a
set comparison. "Is the E&O limit above two million" is a numeric comparison.
Asking a language model either question buys nothing and costs three things: a
number that might be right instead of a number that is right, a latency budget,
and an answer nobody can reproduce.

So the gap engine is plain code, and `Gap.source` is a one-value `Literal` --
the schema itself records that no gap here was produced by a model. Routing a
deterministic question away from the model is the same judgement the sibling
project's router makes when it answers a published build limit from a table, and
it is the difference between a tool and a demo.

The cycle-time model says this engine is where the value is. Of a 15-day mean,
someone actively working accounts for 0.3%; a packet rejected by a carrier for a
single-line defect costs four days. Catching that defect on the near side of the
carrier queue is worth roughly an order of magnitude more than reading the
document faster, and it is the cheaper build.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

Severity = Literal["blocking", "advisory"]

# Bumped whenever a check changes. The eval records it, so a result can be tied
# to the rules that produced it.
ENGINE_VERSION = "1.0.0"


@dataclass(frozen=True)
class Gap:
    """One unmet requirement.

    `source` is a single-value Literal rather than a free string. A gap produced
    by a model would need a different type, which makes "was this checked or
    guessed" a question the type system answers rather than a comment.
    """

    rule_id: str
    carrier_id: str | None
    severity: Severity
    summary: str
    expected: str
    observed: str
    # Who has to act. Drives the owner colouring in the pipeline view, and makes
    # the point that most gaps are not ops problems.
    owner: str
    source: Literal["deterministic"] = "deterministic"

    @property
    def key(self) -> str:
        """Stable identifier, matching the ground-truth plant format."""
        return self.rule_id if self.carrier_id is None else f"{self.rule_id}:{self.carrier_id}"


def _parse_date(value: str) -> datetime | None:
    """Parse either licence date format, or return None.

    Two formats appear in the corpus on purpose, and a licence that fails to
    parse is a finding rather than a crash: an unreadable expiry cannot be
    confirmed valid, so the caller treats it as unverified rather than assuming
    the best.
    """
    for pattern in ("%m/%d/%Y", "%d-%b-%Y"):
        try:
            # The value is upper-cased so "%b" matches "FEB"; the *pattern* must
            # not be, because "%m".upper() is "%M" -- minutes -- and "%d".upper()
            # is not a directive at all. Upper-casing both silently turned every
            # licence in the corpus into an unreadable date, which the gap eval
            # caught as a false positive on all twelve agents.
            return datetime.strptime(value.strip().upper(), pattern)
        except ValueError:
            continue
    return None


def _normalize_name(name: str) -> set[str]:
    """Reduce a name to comparable parts.

    Middle initials and punctuation are dropped because they are not what a
    carrier rejects on. A nickname against a legal first name is, which is why
    the comparison is on the set of multi-character tokens: "Trish Okonkwo" and
    "Patricia N Okonkwo" share a surname and disagree on a given name, and that
    is exactly the mismatch a strict carrier bounces.
    """
    cleaned = re.sub(r"[^a-z ]", " ", name.lower())
    return {token for token in cleaned.split() if len(token) > 1}


def evaluate(agent: dict, carriers: dict[str, dict], *, as_of: datetime) -> list[Gap]:
    """Return every unmet requirement for one agent, across all target carriers.

    Args:
        agent: The cohort record.
        carriers: Carrier requirements, keyed by carrier id.
        as_of: The date expiry is judged against. Passed in rather than read
            from the clock so the result is reproducible in a test.

    Returns:
        Gaps, blocking first, then by carrier.
    """
    gaps: list[Gap] = []
    targets = [carriers[c] for c in agent["target_carriers"] if c in carriers]

    # --- Agent-level checks. These do not depend on a carrier. ---------------

    expiry = _parse_date(agent["expiration_date"])
    if expiry is None:
        gaps.append(
            Gap(
                rule_id="license_unreadable_expiry",
                carrier_id=None,
                severity="blocking",
                summary="Licence expiry date could not be read",
                expected="A parseable expiry date",
                observed=agent["expiration_date"],
                owner="ops",
            )
        )
    elif expiry < as_of:
        gaps.append(
            Gap(
                rule_id="license_expired",
                carrier_id=None,
                severity="blocking",
                summary="Resident licence has expired",
                expected=f"Expiry after {as_of:%d %b %Y}",
                observed=f"Expired {expiry:%d %b %Y}",
                owner="agent",
            )
        )

    # Name match is carrier-dependent in principle -- only some carriers reject
    # outright -- but it is reported once per agent rather than once per carrier.
    # The defect is in the packet, not in the relationship, and repeating it for
    # every strict carrier would bury the other gaps under duplicates.
    strict = [c for c in targets if c["name_match_strict"]]
    if strict and _normalize_name(agent["display_name"]) != _normalize_name(
        agent["license_full_name"]
    ):
        gaps.append(
            Gap(
                rule_id="name_match",
                carrier_id=None,
                severity="blocking",
                summary="Application name does not match the name on the licence",
                expected=f"Legal name as licensed: {agent['license_full_name']}",
                observed=f"Application name: {agent['display_name']}",
                owner="ops",
            )
        )

    # --- Per-carrier checks. -------------------------------------------------

    held_lines = set(agent["lines_of_authority"])

    for carrier in targets:
        cid = carrier["carrier_id"]

        if agent["resident_state"] not in set(carrier["appointment_states"]):
            gaps.append(
                Gap(
                    rule_id="appointment_state",
                    carrier_id=cid,
                    severity="blocking",
                    summary=f"{carrier['name']} does not appoint in {agent['resident_state']}",
                    expected="Resident state on the carrier's appointment list",
                    observed=agent["resident_state"],
                    owner="ops",
                )
            )

        missing_lines = set(carrier["required_lines"]) - held_lines
        if missing_lines:
            gaps.append(
                Gap(
                    rule_id="line_of_authority",
                    carrier_id=cid,
                    severity="blocking",
                    summary=(
                        f"Licence is missing the "
                        f"{', '.join(sorted(missing_lines))} line "
                        f"{carrier['name']} requires"
                    ),
                    expected=", ".join(sorted(carrier["required_lines"])),
                    observed=", ".join(sorted(held_lines)) or "none",
                    owner="agent",
                )
            )

        if carrier["aml_required"] and not agent["aml_completed"]:
            gaps.append(
                Gap(
                    rule_id="aml",
                    carrier_id=cid,
                    severity="blocking",
                    summary=f"{carrier['name']} requires AML certification",
                    expected="AML certification complete",
                    observed="Not complete",
                    owner="agent",
                )
            )

        if agent["eo_coverage_usd"] < carrier["eo_minimum_usd"]:
            gaps.append(
                Gap(
                    rule_id="eo_minimum",
                    carrier_id=cid,
                    severity="blocking",
                    summary=f"E&O coverage is below {carrier['name']}'s minimum",
                    expected=f"${carrier['eo_minimum_usd']:,}",
                    observed=f"${agent['eo_coverage_usd']:,}",
                    owner="agent",
                )
            )

    gaps.sort(key=lambda gap: (gap.severity != "blocking", gap.carrier_id or "", gap.rule_id))
    return gaps
