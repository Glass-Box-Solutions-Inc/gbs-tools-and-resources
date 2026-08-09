"""Reusable paper-to-ledger money coherence sweep.

This module contains no tests.  It only finds governed figures and reports
whether each printed surface agrees with its published ledger value.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass(frozen=True, slots=True)
class Surface:
    """One place one governed figure was found on paper."""

    fact: str
    subtype: str
    printed: Decimal
    expected: Decimal

    @property
    def agrees(self) -> bool:
        """Whether paper and ledger publish the same exact decimal."""
        return self.printed == self.expected


@dataclass(frozen=True, slots=True)
class SweepResult:
    """Every surface found during one paper-to-ledger sweep."""

    surfaces: tuple[Surface, ...]

    @property
    def disagreements(self) -> tuple[Surface, ...]:
        """Return only surfaces whose paper and ledger values differ."""
        return tuple(surface for surface in self.surfaces if not surface.agrees)

    @property
    def facts_found(self) -> frozenset[str]:
        """Return the governed rule labels that matched at least one surface."""
        return frozenset(surface.fact for surface in self.surfaces)

    def describe(self) -> str:
        """Describe each disagreement on one human-readable line."""
        return "\n".join(
            f"{surface.subtype}: {surface.fact} prints {surface.printed}, "
            f"the ledger publishes {surface.expected}"
            for surface in self.disagreements
        )


def ledger_value(money: Mapping[str, Any], path: str) -> Decimal:
    """Resolve one dotted path into the published money block."""
    node: Any = money
    parts = path.split(".")
    if parts[0] == "money":
        parts = parts[1:]
    for part in parts:
        if isinstance(node, Mapping):
            node = node[part]
        elif isinstance(node, list) and part.isdigit():
            node = node[int(part)]
        else:
            raise TypeError(f"{'.'.join(parts)} crosses a non-container at {part!r}")
    return Decimal(node)


def sweep(
    texts: Mapping[str, str],
    money: Mapping[str, Any],
    rules: Mapping[str, tuple[re.Pattern[str], str]],
) -> SweepResult:
    """Find every governed paper surface without making an assertion."""
    expected_by_fact: dict[str, Decimal] = {}
    for fact, (_pattern, path) in rules.items():
        try:
            expected_by_fact[fact] = ledger_value(money, path)
        except (IndexError, KeyError):
            # Optional governed groups are absent, never null. A rule for such a
            # group applies only to the opted-in cases that publish its ledger.
            continue
    surfaces: list[Surface] = []
    for subtype, page in sorted(texts.items()):
        for fact, (pattern, _path) in rules.items():
            if fact not in expected_by_fact:
                continue
            expected = expected_by_fact[fact]
            surfaces.extend(
                Surface(
                    fact=fact,
                    subtype=subtype,
                    printed=Decimal(found.group(1).replace(",", "")),
                    expected=expected,
                )
                for found in pattern.finditer(page)
            )
    return SweepResult(tuple(surfaces))


#: fact -> (pattern, how to read the ledger). Every pattern is anchored to the
#: words around the figure, because an unanchored money regex matches the next
#: number along and asserts nothing.
GOVERNED_ON_THE_PAGE: dict[str, tuple[re.Pattern[str], str]] = {
    "aww": (
        re.compile(r"Average Weekly Wage \(AWW\): \$([\d,]+\.\d\d)"),
        "money.wage.averageWeeklyWage",
    ),
    "td_rate_statement": (
        re.compile(r"Temporary Disability Rate: \$([\d,]+\.\d\d)/week"),
        "money.rate.tdWeeklyRate",
    ),
    "pd_rate_statement": (
        re.compile(r"Permanent Disability Rate: \$([\d,]+\.\d\d)/week"),
        "money.rate.pdWeeklyRate",
    ),
    "td_rate_memo": (
        re.compile(r"weeks @ \$([\d,]+\.\d\d)/week"),
        "money.rate.tdWeeklyRate",
    ),
    "td_total_memo": (
        re.compile(r"Temporary Total Disability \(TTD\): \$([\d,]+\.\d\d)"),
        "money.benefits.tdTotal",
    ),
    "td_total_ledger": (
        re.compile(r"Temporary Disability Paid To Date \$([\d,]+\.\d\d)"),
        "money.benefits.tdTotal",
    ),
    "pd_rate_memo": (
        re.compile(r"Weekly Rate: \$([\d,]+\.\d\d)"),
        "money.rate.pdWeeklyRate",
    ),
    "gross_terms": (
        re.compile(r"Settlement Gross: \$([\d,]+\.\d\d)"),
        "money.settlement.grossAmount",
    ),
    "gross_release": (
        re.compile(r"Gross Settlement Amount \$([\d,]+\.\d\d)"),
        "money.settlement.grossAmount",
    ),
    "gross_target": (
        re.compile(r"Recommended Settlement Target: \$([\d,]+)"),
        "money.settlement.grossAmount",
    ),
    "penalty_principal": (
        re.compile(r"§4650\(d\) Principal Assessed:? \$([\d,]+\.\d\d)"),
        "money.penalties.principalAssessed",
    ),
    "penalty_assessment_1": (
        re.compile(
            r"§4650\(d\) (?:TD period|PD advance) 1 Increase:? \$([\d,]+\.\d\d)"
        ),
        "money.penalties.assessments.0.amount",
    ),
    "penalty_assessment_2": (
        re.compile(
            r"§4650\(d\) (?:TD period|PD advance) 2 Increase:? \$([\d,]+\.\d\d)"
        ),
        "money.penalties.assessments.1.amount",
    ),
    "penalty_fraction": (
        re.compile(r"§4650\(d\) Increase Fraction:? ([\d]+(?:\.\d+)?)"),
        "money.penalties.increaseFraction",
    ),
    "penalty_total": (
        re.compile(r"§4650\(d\) Total Increase:? \$([\d,]+\.\d\d)"),
        "money.penalties.totalIncrease",
    ),
}

#: The hourly rate is swept differently: a pay-rate *history* legitimately holds
#: earlier, lower figures, so equality on every occurrence would be the wrong
#: assertion. What it must not do is print a rate above the one the file says the
#: applicant was earning when they were hurt.
HOURLY_RATE = re.compile(
    # Two shapes, and the second is why `align_employer_wage` exists rather than
    # a template override: the deposition has the applicant *say* the figure,
    # from the same `employer.hourly_rate` the personnel file tabulates. A fix
    # that only rewrote the table would have left the transcript contradicting
    # it — this program's oldest defect class, one more time.
    r"\$([\d,]+\.\d\d)(?:/hr| per hour)"
)


__all__ = [
    "GOVERNED_ON_THE_PAGE",
    "HOURLY_RATE",
    "Surface",
    "SweepResult",
    "ledger_value",
    "sweep",
]
