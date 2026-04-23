"""
Unit tests for the timeline builder.

Verifies regulatory deadline enforcement for all 3 scenarios.

Deadlines tested:
  - 10 CCR 2695.5(b): Initial contact within 15 days
  - LC 4650: First TD payment within 14 days
  - 10 CCR 2695.7(b): Accept/deny within 40/90 days

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from claims_generator.core.claim_state import ClaimState
from claims_generator.core.lifecycle_engine import walk_lifecycle
from claims_generator.core.timeline_builder import build_timeline
from claims_generator.models.claim import DocumentEvent
from claims_generator.scenarios.registry import get_scenario


def _make_timeline(scenario_slug: str, seed: int = 42) -> tuple[list[DocumentEvent], date]:
    """Build a timeline for a scenario. Returns (events, doi)."""
    preset = get_scenario(scenario_slug)
    state = ClaimState(
        litigated=preset.litigated,
        attorney_represented=preset.attorney_represented,
        denied_scenario=preset.denied_scenario,
        investigation_active=preset.investigation_active,
        seed=seed,
    )
    path = walk_lifecycle(state)

    doi = date.today() - timedelta(days=365)
    events = build_timeline(stage_path=path, state=state, date_of_injury=doi)
    return events, doi


@pytest.mark.parametrize("scenario_slug", ["standard_claim", "litigated_qme", "denied_claim"])
def test_timeline_nonempty(scenario_slug: str) -> None:
    """Every scenario must produce at least 1 document event."""
    events, _ = _make_timeline(scenario_slug)
    assert len(events) >= 1, f"{scenario_slug} produced no document events"


@pytest.mark.parametrize("scenario_slug", ["standard_claim", "litigated_qme", "denied_claim"])
def test_dates_are_ascending(scenario_slug: str) -> None:
    """Document events must be sorted in ascending date order."""
    events, _ = _make_timeline(scenario_slug)
    dates = [e.event_date for e in events]
    assert dates == sorted(dates), (
        f"{scenario_slug}: document events are not in ascending date order"
    )


@pytest.mark.parametrize("scenario_slug", ["standard_claim", "litigated_qme", "denied_claim"])
def test_all_events_after_doi(scenario_slug: str) -> None:
    """All document event dates must be on or after the date of injury."""
    events, doi = _make_timeline(scenario_slug)
    for e in events:
        assert e.event_date >= doi, (
            f"{scenario_slug}: event {e.subtype_slug!r} date {e.event_date} is before DOI {doi}"
        )


@pytest.mark.parametrize("scenario_slug", ["standard_claim", "litigated_qme", "denied_claim"])
def test_deadline_events_within_deadline(scenario_slug: str) -> None:
    """Any event with a deadline_date must have event_date <= deadline_date."""
    events, _ = _make_timeline(scenario_slug)
    violations = [
        e for e in events
        if e.deadline_date is not None and e.event_date > e.deadline_date
    ]
    assert not violations, (
        f"{scenario_slug}: deadline violations found: "
        + ", ".join(f"{e.subtype_slug}({e.event_date} > {e.deadline_date})" for e in violations)
    )


def test_initial_contact_within_15_days_standard() -> None:
    """Standard claim: initial contact deadline must be claim_filed + 15 days."""
    events, doi = _make_timeline("standard_claim", seed=42)
    contact_events = [
        e for e in events
        if e.deadline_statute and "2695.5" in e.deadline_statute
    ]
    claim_filed = doi + timedelta(days=7)
    expected_deadline = claim_filed + timedelta(days=15)

    for e in contact_events:
        assert e.deadline_date == expected_deadline, (
            f"Initial contact deadline should be {expected_deadline}, got {e.deadline_date}"
        )
        assert e.event_date <= expected_deadline, (
            f"Initial contact event date {e.event_date} exceeds deadline {expected_deadline}"
        )


def test_td_payment_within_14_days_standard() -> None:
    """Standard claim: first TD payment must be within 14 days of DOI."""
    events, doi = _make_timeline("standard_claim", seed=42)
    td_events = [
        e for e in events
        if e.deadline_statute and "4650" in e.deadline_statute
    ]
    # Not all runs will have a TD payment (depends on stage path)
    for e in td_events:
        expected_deadline = doi + timedelta(days=14)
        assert e.deadline_date == expected_deadline, (
            f"TD deadline should be DOI+14={expected_deadline}, got {e.deadline_date}"
        )
        assert e.event_date <= expected_deadline, (
            f"TD payment {e.event_date} exceeds LC 4650 deadline {expected_deadline}"
        )


def test_acceptance_deadline_40_days_standard() -> None:
    """Standard claim: acceptance notice deadline must be claim_filed + 40 days."""
    events, doi = _make_timeline("standard_claim", seed=42)
    acceptance_events = [
        e for e in events
        if e.subtype_slug == "benefit_notice_acceptance" and e.deadline_date is not None
    ]
    claim_filed = doi + timedelta(days=7)
    expected_deadline = claim_filed + timedelta(days=40)

    for e in acceptance_events:
        assert e.deadline_date == expected_deadline, (
            f"Acceptance deadline should be {expected_deadline}, got {e.deadline_date}"
        )


def test_denial_deadline_90_days_denied() -> None:
    """Denied claim: denial notice deadline must be claim_filed + 90 days."""
    events, doi = _make_timeline("denied_claim", seed=42)
    denial_events = [
        e for e in events
        if e.subtype_slug == "benefit_notice_denial" and e.deadline_date is not None
    ]
    claim_filed = doi + timedelta(days=7)
    expected_deadline = claim_filed + timedelta(days=90)

    for e in denial_events:
        assert e.deadline_date == expected_deadline, (
            f"Denial deadline should be {expected_deadline}, got {e.deadline_date}"
        )
        assert e.event_date <= expected_deadline, (
            f"Denial event {e.event_date} exceeds 90-day deadline {expected_deadline}"
        )


@pytest.mark.parametrize("scenario_slug", ["standard_claim", "litigated_qme", "denied_claim"])
def test_document_types_are_valid_enum_values(scenario_slug: str) -> None:
    """All document_type values must be valid DocumentType enum members."""
    from claims_generator.models.enums import DocumentType

    events, _ = _make_timeline(scenario_slug)
    for e in events:
        assert e.document_type in DocumentType, (
            f"{scenario_slug}: invalid document_type {e.document_type!r}"
        )


def test_litigated_doc_count_in_range() -> None:
    """litigated_qme should produce 18-30 documents across multiple seeds."""
    in_range = 0
    for seed in range(10):
        events, _ = _make_timeline("litigated_qme", seed=seed)
        if 18 <= len(events) <= 30:
            in_range += 1
    # At least 50% of runs should be in the expected range
    assert in_range >= 5, (
        f"litigated_qme: only {in_range}/10 seeds produced 18-30 docs"
    )
