"""
Smoke tests for case_builder.py — one case per scenario, valid JSON.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import json

import pytest

from claims_generator.case_builder import build_case
from claims_generator.models.claim import ClaimCase
from claims_generator.models.enums import DocumentType


@pytest.mark.parametrize("scenario_slug", ["standard_claim", "litigated_qme", "denied_claim"])
def test_build_case_returns_claim_case(scenario_slug: str) -> None:
    """build_case must return a ClaimCase instance."""
    case = build_case(scenario_slug=scenario_slug, seed=42)
    assert isinstance(case, ClaimCase)


@pytest.mark.parametrize("scenario_slug", ["standard_claim", "litigated_qme", "denied_claim"])
def test_case_has_expected_fields(scenario_slug: str) -> None:
    """ClaimCase must have all required fields populated."""
    case = build_case(scenario_slug=scenario_slug, seed=42)
    assert case.case_id
    assert case.scenario_slug == scenario_slug
    assert case.seed == 42
    assert case.profile is not None
    assert len(case.document_events) > 0
    assert len(case.stages_visited) > 0


@pytest.mark.parametrize("scenario_slug", ["standard_claim", "litigated_qme", "denied_claim"])
def test_case_serializes_to_valid_json(scenario_slug: str) -> None:
    """ClaimCase must produce valid JSON output (no pdf_bytes, no unserializable types)."""
    case = build_case(scenario_slug=scenario_slug, seed=42)
    data = case.model_dump_json_safe()
    # Round-trip through json.dumps / json.loads
    json_str = json.dumps(data, default=str)
    parsed = json.loads(json_str)
    assert parsed["case_id"] == case.case_id
    assert parsed["scenario_slug"] == scenario_slug
    assert len(parsed["document_events"]) == len(case.document_events)


@pytest.mark.parametrize("scenario_slug", ["standard_claim", "litigated_qme", "denied_claim"])
def test_case_pdf_bytes_are_empty_phase1(scenario_slug: str) -> None:
    """In Phase 1, all pdf_bytes must be empty (b'')."""
    case = build_case(scenario_slug=scenario_slug, seed=42)
    for event in case.document_events:
        assert event.pdf_bytes == b"", (
            f"{scenario_slug}: event {event.subtype_slug} has non-empty pdf_bytes in Phase 1"
        )


@pytest.mark.parametrize("scenario_slug", ["standard_claim", "litigated_qme", "denied_claim"])
def test_case_document_types_valid(scenario_slug: str) -> None:
    """All document_type values must be valid DocumentType enum members."""
    case = build_case(scenario_slug=scenario_slug, seed=42)
    valid_types = {dt for dt in DocumentType}
    for event in case.document_events:
        assert event.document_type in valid_types, (
            f"{scenario_slug}: unknown document_type {event.document_type!r}"
        )


@pytest.mark.parametrize("scenario_slug", ["standard_claim", "litigated_qme", "denied_claim"])
def test_case_dates_ascending(scenario_slug: str) -> None:
    """Document events must be in ascending date order."""
    case = build_case(scenario_slug=scenario_slug, seed=42)
    dates = [e.event_date for e in case.document_events]
    assert dates == sorted(dates), (
        f"{scenario_slug}: document events are not sorted by date"
    )


def test_case_reproducible() -> None:
    """Same scenario + seed must produce identical output."""
    case1 = build_case(scenario_slug="standard_claim", seed=123)
    case2 = build_case(scenario_slug="standard_claim", seed=123)
    assert case1.stages_visited == case2.stages_visited
    assert len(case1.document_events) == len(case2.document_events)
    for e1, e2 in zip(case1.document_events, case2.document_events):
        assert e1.document_type == e2.document_type
        assert e1.event_date == e2.event_date


def test_different_seeds_produce_different_cases() -> None:
    """Different seeds should (very likely) produce different event counts or dates."""
    results: set[int] = set()
    for seed in range(5):
        case = build_case(scenario_slug="standard_claim", seed=seed)
        results.add(len(case.document_events))
    # At least 2 different doc counts across 5 seeds
    assert len(results) >= 2


def test_invalid_scenario_raises_key_error() -> None:
    """Unknown scenario slug must raise KeyError."""
    with pytest.raises(KeyError, match="Unknown scenario slug"):
        build_case(scenario_slug="nonexistent_scenario", seed=42)


def test_litigated_case_scenario_slug(litigated_case: ClaimCase) -> None:
    """Fixture-based smoke test: litigated case has correct slug."""
    assert litigated_case.scenario_slug == "litigated_qme"


def test_denied_case_has_denial_event(denied_case: ClaimCase) -> None:
    """Denied case should contain at least one BENEFIT_NOTICE event."""
    notice_events = [
        e for e in denied_case.document_events
        if e.document_type == DocumentType.BENEFIT_NOTICE
    ]
    assert len(notice_events) >= 1, "denied_claim should contain BENEFIT_NOTICE events"


def test_profile_fields_populated(standard_case: ClaimCase) -> None:
    """Profile must have all required fields populated."""
    p = standard_case.profile
    assert p.claimant.first_name
    assert p.claimant.last_name
    assert p.claimant.address_county
    assert p.employer.company_name
    assert p.insurer.carrier_name
    assert p.insurer.claim_number
    assert p.medical.date_of_injury
    assert len(p.medical.body_parts) >= 1
    assert p.financial.td_weekly_rate > 0
    assert p.financial.average_weekly_wage > 0


def test_financial_td_rate_within_bounds(standard_case: ClaimCase) -> None:
    """TD rate must be within statutory min/max bounds."""
    fin = standard_case.profile.financial
    assert fin.td_min_rate <= fin.td_weekly_rate <= fin.td_max_rate
