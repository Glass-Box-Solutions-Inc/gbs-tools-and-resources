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

    Conflict and duplicate grouping covers case-level claims only — facts whose
    source path holds no list index. A field repeated across list records
    (``documents[0].subtype`` vs ``documents[1].subtype``) describes distinct
    entities, not two assertions about one thing, and is not compared. A generic
    single-word leaf (``status``, ``name``) is qualified by its parent segment,
    so ``treatment.status`` and ``surgery.status`` are different properties;
    self-descriptive multi-word fields (``date_of_injury``) compare across
    sources regardless of nesting.
    """
    findings: list[Finding] = []
    by_key: dict[tuple[str, str], list[Fact]] = defaultdict(list)
    by_exact: dict[tuple[str, str, str], list[Fact]] = defaultdict(list)
    for fact in facts:
        if _is_case_level(fact):
            by_key[(fact.category, _comparison_field(fact))].append(fact)
            by_exact[(fact.category, _comparison_field(fact), stable_value(fact.value))].append(
                fact
            )
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
                        f"{fact.field} carries no supplied confidence; its provenance is the "
                        "input record only and it should be treated as unscored."
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

    for (_, field, _), group in sorted(by_exact.items()):
        if len(group) > 1:
            findings.append(
                Finding(
                    code="duplicate_fact",
                    severity="info",
                    message=(
                        f"{field} is repeated with the same normalized value "
                        f"in {len(group)} sources."
                    ),
                    fact_ids=tuple(sorted(item.id for item in group)),
                    category=group[0].category,
                )
            )
    for (_, field), group in sorted(by_key.items()):
        values = {stable_value(item.value) for item in group}
        if len(values) > 1:
            findings.append(
                Finding(
                    code="conflicting_fact",
                    severity="error",
                    message=(
                        f"{field} has {len(values)} incompatible asserted values; "
                        "resolve against source evidence."
                    ),
                    fact_ids=tuple(sorted(item.id for item in group)),
                    category=group[0].category,
                )
            )
    findings.extend(_chronology_findings(tuple(facts)))
    return tuple(sorted(findings, key=lambda item: (item.severity, item.code, item.fact_ids)))


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


def _is_case_level(fact: Fact) -> bool:
    return "[" not in fact.source_path


def _comparison_field(fact: Fact) -> str:
    """The identity under which two case-level claims count as the same property."""
    leaf = canonical_field(fact.field)
    if "_" in leaf:
        return leaf
    parent = _parent_segment(fact.source_path)
    return canonical_field(f"{parent}_{leaf}") if parent else leaf


def _parent_segment(path: str) -> str:
    parts = [part for part in path.split(".") if part and part != "$"]
    return parts[-2] if len(parts) >= 2 else ""


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
