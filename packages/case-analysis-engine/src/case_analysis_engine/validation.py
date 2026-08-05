"""Integrity checks over the normalized ledger, with cautious chronology diagnostics."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date
from typing import Any

from case_analysis_engine.models import Fact, Finding
from case_analysis_engine.text import canonical_field, stable_value

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_STAGES = (
    ("injury", ("date_of_injury", "injury_date", "doi")),
    ("claim", ("claim_date", "application_date", "filing_date")),
    ("treatment", ("treatment_date", "visit_date", "diagnostic_date", "surgery_date")),
    ("mmi", ("mmi_date",)),
    ("resolution", ("settlement_date", "resolution_date", "award_date")),
)


def validate_facts(facts: tuple[Fact, ...] | list[Fact]) -> tuple[Finding, ...]:
    """Find data defects while keeping mere ambiguity distinct from a hard conflict.

    Conflict and duplicate grouping covers ``claim`` and ``case`` scoped facts;
    ``entity`` facts — attributes of one element of a repeated collection, such
    as ``documents[1].subtype`` — describe distinct entities and are never
    compared against their siblings. Within a group sharing one canonical field,
    two facts are the same property only when their qualifier chains are
    suffix-compatible: ``caseFacts.money.averageWeeklyWage`` matches
    ``money.averageWeeklyWage`` and bare ``employer`` matches ``case.employer``,
    while ``applicant.phone_number`` never merges with
    ``adjuster.phone_number``. An explicit claim record names its field
    directly, so it carries an empty chain and compares everywhere its field
    appears.
    """
    findings: list[Finding] = []
    comparable: dict[tuple[str, str], list[Fact]] = defaultdict(list)
    for fact in facts:
        if fact.scope in ("claim", "case"):
            comparable[(fact.category, canonical_field(fact.field))].append(fact)
        if not fact.evidence:
            findings.append(
                Finding(
                    code="missing_evidence",
                    severity="warning",
                    message=f"{fact.field} has no provenance record.",
                    fact_ids=(fact.id,),
                    category="evidence_quality",
                )
            )
        elif fact.confidence is None:
            findings.append(
                Finding(
                    code="limited_evidence",
                    severity="warning",
                    message=(
                        f"{fact.field} carries no usable supplied confidence; "
                        "it should be treated as unscored."
                    ),
                    fact_ids=(fact.id,),
                    category="evidence_quality",
                )
            )
        elif fact.confidence < 0.5:
            findings.append(
                Finding(
                    code="low_confidence",
                    severity="warning",
                    message=f"{fact.field} is extracted at low confidence ({fact.confidence:.2f}).",
                    fact_ids=(fact.id,),
                    category="evidence_quality",
                )
            )

    for (_, field), group in sorted(comparable.items()):
        conflicting_ids, duplicate_ids_by_value = _compare_group(group)
        for value, ids in sorted(duplicate_ids_by_value.items()):
            findings.append(
                Finding(
                    code="duplicate_fact",
                    severity="info",
                    message=(
                        f"{field} is repeated with the same normalized value in {len(ids)} sources."
                    ),
                    fact_ids=tuple(sorted(ids)),
                    category=group[0].category,
                )
            )
        if conflicting_ids:
            distinct = {stable_value(item.value) for item in group if item.id in conflicting_ids}
            findings.append(
                Finding(
                    code="conflicting_fact",
                    severity="error",
                    message=(
                        f"{field} has {len(distinct)} incompatible asserted values; "
                        "resolve against source evidence."
                    ),
                    fact_ids=tuple(sorted(conflicting_ids)),
                    category=group[0].category,
                )
            )
    findings.extend(_chronology_findings(tuple(facts)))
    return tuple(sorted(findings, key=lambda item: (item.severity, item.code, item.fact_ids)))


def _compare_group(group: list[Fact]) -> tuple[set[str], dict[str, set[str]]]:
    """Pairwise comparison under chain compatibility: conflicts and per-value duplicates."""
    conflicting: set[str] = set()
    duplicates: dict[str, set[str]] = defaultdict(set)
    chains = [_qualifier_chain(fact) for fact in group]
    for index, first in enumerate(group):
        for offset, second in enumerate(group[index + 1 :], start=index + 1):
            if not _chains_compatible(chains[index], chains[offset]):
                continue
            if stable_value(first.value) == stable_value(second.value):
                duplicates[stable_value(first.value)].update((first.id, second.id))
            else:
                conflicting.update((first.id, second.id))
    return conflicting, duplicates


def _qualifier_chain(fact: Fact) -> tuple[str, ...]:
    """The canonicalized parent segments that qualify a fact's leaf field.

    A ``claim`` names its field directly and carries no chain. For flattened
    scalars the chain is every dotted segment above the leaf, index-stripped and
    canonicalized, with the root marker removed.
    """
    if fact.scope == "claim":
        return ()
    parts = [part for part in fact.source_path.split(".") if part and part != "$"]
    segments = (canonical_field(part.split("[", 1)[0]) for part in parts[:-1])
    return tuple(segment for segment in segments if segment)


def _chains_compatible(first: tuple[str, ...], second: tuple[str, ...]) -> bool:
    shorter, longer = (first, second) if len(first) <= len(second) else (second, first)
    return longer[len(longer) - len(shorter) :] == shorter


def chronology(facts: tuple[Fact, ...] | list[Fact]) -> tuple[dict[str, Any], ...]:
    """Return every parseable date claim in chronological order with no inferred events."""
    events: list[dict[str, Any]] = []
    for fact in facts:
        parsed = _date_value(fact.value)
        if parsed is not None and (
            "date" in canonical_field(fact.field) or fact.field.lower() == "doi"
        ):
            events.append(
                {
                    "date": parsed.isoformat(),
                    "field": fact.field,
                    "category": fact.category,
                    "factId": fact.id,
                    "confidence": fact.confidence,
                }
            )
    return tuple(sorted(events, key=lambda item: (item["date"], item["field"], item["factId"])))


def _chronology_findings(facts: tuple[Fact, ...]) -> list[Finding]:
    staged: dict[str, list[tuple[date, Fact]]] = defaultdict(list)
    for fact in facts:
        parsed = _date_value(fact.value)
        stage = _stage_for(fact.field)
        if parsed is not None and stage is not None:
            staged[stage].append((parsed, fact))
    findings: list[Finding] = []
    present = [stage for stage in _STAGES if staged.get(stage[0])]
    for index, earlier in enumerate(present):
        for later in present[index + 1 :]:
            early_events, late_events = staged[earlier[0]], staged[later[0]]
            if min(date_value for date_value, _ in early_events) > min(
                date_value for date_value, _ in late_events
            ):
                paired = (
                    min(early_events, key=lambda item: item[0])[1],
                    min(late_events, key=lambda item: item[0])[1],
                )
                findings.append(
                    Finding(
                        code="chronology_question",
                        severity="warning",
                        message=(
                            f"{later[0]} is dated before {earlier[0]}; "
                            "this may be valid but needs source review."
                        ),
                        fact_ids=tuple(item.id for item in paired),
                        category="procedure",
                    )
                )
    return findings


def _date_value(value: Any) -> date | None:
    if isinstance(value, str) and _DATE_RE.match(value):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def _stage_for(field: str) -> str | None:
    normalized = canonical_field(field)
    return next((stage for stage, fields in _STAGES if normalized in fields), None)
