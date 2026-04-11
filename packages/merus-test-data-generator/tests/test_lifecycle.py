"""
Tests for the lifecycle engine document-emission rules (data/lifecycle_engine.py).

Verifies that all subtype references in LIFECYCLE_DOCUMENT_RULES are valid
canonical DocumentSubtype values, and that all probability / count values are
within legal ranges.
"""

from __future__ import annotations

from data.lifecycle_engine import LIFECYCLE_DOCUMENT_RULES, NodeDocumentRule
from data.taxonomy import DocumentSubtype

_VALID_SUBTYPES: frozenset[str] = frozenset(s.value for s in DocumentSubtype)


def test_all_lifecycle_subtypes_are_valid() -> None:
    """Every NodeDocumentRule.subtype string must be a valid DocumentSubtype value."""
    invalid: list[str] = []
    for stage, rules in LIFECYCLE_DOCUMENT_RULES.items():
        for rule in rules:
            if rule.subtype not in _VALID_SUBTYPES:
                invalid.append(
                    f"Stage {stage!r}: subtype {rule.subtype!r} is not a valid "
                    "DocumentSubtype"
                )
    assert not invalid, "\n".join(invalid)


def test_probability_ranges_valid() -> None:
    """Every NodeDocumentRule.probability must be between 0.0 and 1.0 inclusive."""
    out_of_range: list[str] = []
    for stage, rules in LIFECYCLE_DOCUMENT_RULES.items():
        for rule in rules:
            if not (0.0 <= rule.probability <= 1.0):
                out_of_range.append(
                    f"Stage {stage!r} / subtype {rule.subtype!r}: "
                    f"probability={rule.probability} is out of [0.0, 1.0]"
                )
    assert not out_of_range, "\n".join(out_of_range)


def test_count_ranges_valid() -> None:
    """Every NodeDocumentRule.count tuple must have min <= max and both >= 0."""
    bad_counts: list[str] = []
    for stage, rules in LIFECYCLE_DOCUMENT_RULES.items():
        for rule in rules:
            min_count, max_count = rule.count
            if min_count < 0 or max_count < 0 or min_count > max_count:
                bad_counts.append(
                    f"Stage {stage!r} / subtype {rule.subtype!r}: "
                    f"count={rule.count!r} is invalid (must have 0 <= min <= max)"
                )
    assert not bad_counts, "\n".join(bad_counts)


def test_all_lifecycle_stages_have_rules() -> None:
    """Every key in LIFECYCLE_DOCUMENT_RULES must map to a non-empty list of rules."""
    empty_stages = [
        stage
        for stage, rules in LIFECYCLE_DOCUMENT_RULES.items()
        if not rules
    ]
    assert not empty_stages, (
        f"These lifecycle stages have empty rule lists: {empty_stages}"
    )


def test_standard_global_cap_enforced() -> None:
    """collect_documents_for_case() must not return more than 110% of STANDARD_GLOBAL_CAP."""
    import random
    from data.lifecycle_engine import (
        CaseParameters, collect_documents_for_case,
        STANDARD_GLOBAL_CAP,
    )

    rng = random.Random(42)
    # Worst-case standard case: all optional features enabled, resolved stage
    params = CaseParameters(
        claim_response="accepted",
        has_attorney=True,
        has_ur_dispute=True,
        ur_decision="denied",
        imr_filed=True,
        imr_outcome="overturned",
        eval_type="qme",
        resolution_type="stipulations",
        has_surgery=True,
        has_psych_component=True,
        has_liens=True,
        target_stage="resolved",
        complexity="standard",
    ).resolve_random(rng)

    docs = collect_documents_for_case(params, rng)
    hard_cap = int(STANDARD_GLOBAL_CAP * 1.10)
    assert len(docs) <= hard_cap, (
        f"Standard case produced {len(docs)} documents, "
        f"exceeding hard cap of {hard_cap} (110% of {STANDARD_GLOBAL_CAP})"
    )


def test_complex_global_cap_enforced() -> None:
    """collect_documents_for_case() must not return more than 110% of COMPLEX_GLOBAL_CAP."""
    import random
    from data.lifecycle_engine import (
        CaseParameters, collect_documents_for_case,
        COMPLEX_GLOBAL_CAP,
    )

    rng = random.Random(99)
    params = CaseParameters(
        claim_response="accepted",
        has_attorney=True,
        has_ur_dispute=True,
        ur_decision="denied",
        imr_filed=True,
        imr_outcome="overturned",
        eval_type="qme",
        resolution_type="c_and_r",
        has_surgery=True,
        has_psych_component=True,
        has_liens=True,
        target_stage="resolved",
        complexity="complex",
    ).resolve_random(rng)

    docs = collect_documents_for_case(params, rng)
    hard_cap = int(COMPLEX_GLOBAL_CAP * 1.10)
    assert len(docs) <= hard_cap, (
        f"Complex case produced {len(docs)} documents, "
        f"exceeding hard cap of {hard_cap} (110% of {COMPLEX_GLOBAL_CAP})"
    )
