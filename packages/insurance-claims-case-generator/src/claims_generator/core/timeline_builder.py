"""
Timeline builder — converts ordered stages + profile into DocumentEvents with
regulatory deadline enforcement.

Deadlines enforced:
  - 10 CCR 2695.5(b): Initial contact within 15 days of claim receipt
  - LC 4650: First TD payment within 14 days of knowledge of disability
  - 10 CCR 2695.7(b): Accept (40 days) or deny (90 days) from claim receipt

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from claims_generator.core.claim_state import ClaimState
from claims_generator.core.dag_nodes import ALL_STAGES, DocumentEmission
from claims_generator.models.claim import DocumentEvent
from claims_generator.models.enums import DocumentType


def build_timeline(
    stage_path: list[str],
    state: ClaimState,
    date_of_injury: date,
    date_claim_filed: date | None = None,
) -> list[DocumentEvent]:
    """
    Build an ordered list of DocumentEvents from the stage path.

    Args:
        stage_path: Ordered list of stage IDs from lifecycle_engine.walk_lifecycle()
        state: ClaimState with flags and RNG
        date_of_injury: Date of the injury
        date_claim_filed: Date DWC-1 was filed (defaults to DOI + 7 days)

    Returns:
        Ordered list of DocumentEvents sorted by event_date.
    """
    if date_claim_filed is None:
        date_claim_filed = date_of_injury + timedelta(days=7)

    events: list[DocumentEvent] = []
    current_anchor = date_claim_filed

    # Track key dates for deadline enforcement
    claim_receipt_date = date_claim_filed

    for stage_id in stage_path:
        node = ALL_STAGES.get(stage_id)
        if node is None:
            continue

        # Advance the anchor date based on stage duration
        if stage_id == "DWC1_FILED":
            stage_date = date_claim_filed
        else:
            days_forward = state.rng.randint(
                node.duration_min_days, node.duration_max_days
            )
            current_anchor = current_anchor + timedelta(days=days_forward)
            stage_date = current_anchor

        # Emit documents for this stage
        for emission in node.emissions:
            # Apply psych_overlay probability boost for QME_EXAM psychiatric eval
            effective_prob = _effective_probability(emission, stage_id, state)

            if state.rng.random() > effective_prob:
                continue  # Skip this document

            event_date = stage_date + timedelta(
                days=state.rng.randint(0, max(0, node.duration_max_days // 4))
            )

            # Compute deadline if applicable
            deadline_date: date | None = None
            if emission.deadline_days is not None:
                deadline_date = _compute_deadline(
                    emission, stage_id, claim_receipt_date, date_of_injury
                )
                # Enforce: event_date must not exceed deadline_date
                if deadline_date is not None and event_date > deadline_date:
                    event_date = deadline_date

            event = DocumentEvent(
                event_id=str(uuid.uuid4()),
                document_type=emission.document_type,
                subtype_slug=emission.subtype_slug,
                title=emission.title_template,
                event_date=event_date,
                deadline_date=deadline_date,
                deadline_statute=emission.deadline_statute,
                stage=stage_id,
                access_level=emission.access_level,
                pdf_bytes=b"",
                metadata={"stage_anchor": stage_date.isoformat()},
            )
            events.append(event)

    # Sort by event_date (ascending) — critical for timeline validity
    events.sort(key=lambda e: e.event_date)
    return events


def _effective_probability(
    emission: DocumentEmission,
    stage_id: str,
    state: ClaimState,
) -> float:
    """Apply state-based probability adjustments."""
    p = emission.probability

    # Psych overlay boosts psychiatric QME probability to near-certain
    if (
        stage_id == "QME_EXAM"
        and emission.subtype_slug == "qme_report_psychiatric"
        and state.psych_overlay
    ):
        p = 0.95

    # Attorney-represented: boost legal correspondence probability
    if (
        emission.document_type == DocumentType.LEGAL_CORRESPONDENCE
        and state.attorney_represented
    ):
        p = min(1.0, p + 0.30)

    # High liens: boost lien claim probability
    if emission.document_type == DocumentType.LIEN_CLAIM and state.high_liens:
        p = min(1.0, p + 0.50)

    # Litigated: boost WCAB filing probability
    if emission.document_type == DocumentType.WCAB_FILING and state.litigated:
        p = min(1.0, p + 0.30)

    # Investigation active: boost investigation report probability
    if (
        emission.document_type == DocumentType.INVESTIGATION_REPORT
        and state.investigation_active
    ):
        p = min(1.0, p + 0.25)

    return p


def _compute_deadline(
    emission: DocumentEmission,
    stage_id: str,
    claim_receipt_date: date,
    date_of_injury: date,
) -> date | None:
    """
    Compute the regulatory deadline date for an emission.

    Deadlines are anchored to:
    - claim_receipt_date for most claim administration deadlines
    - date_of_injury for TD payment deadlines
    """
    if emission.deadline_days is None:
        return None

    statute = emission.deadline_statute or ""

    # LC 4650: 14-day TD payment deadline anchors to date of injury/knowledge
    if "4650" in statute:
        return date_of_injury + timedelta(days=emission.deadline_days)

    # All other deadlines anchor to claim receipt date
    return claim_receipt_date + timedelta(days=emission.deadline_days)
