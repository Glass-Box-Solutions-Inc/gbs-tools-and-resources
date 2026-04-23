"""
ClaimCase and DocumentEvent — root output models.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

from pydantic import BaseModel, Field

from claims_generator.models.enums import DocumentType
from claims_generator.models.profile import ClaimProfile


class DocumentEvent(BaseModel):
    """A single document event in the claim timeline."""

    event_id: str
    document_type: DocumentType
    subtype_slug: str = Field(description="e.g. 'benefit_notice_acceptance'")
    title: str
    event_date: date
    deadline_date: Optional[date] = Field(
        default=None, description="Regulatory deadline if applicable"
    )
    deadline_statute: Optional[str] = Field(
        default=None, description="e.g. 'LC 4650', '10 CCR 2695.7(b)'"
    )
    stage: str = Field(description="Lifecycle stage that emitted this event")
    access_level: str = "EXAMINER_ONLY"  # EXAMINER_ONLY / DUAL_ACCESS / ATTORNEY_ONLY
    pdf_bytes: bytes = Field(default=b"", description="Empty in Phase 1; populated in Phase 2+")
    metadata: dict[str, Any] = Field(default_factory=dict)


class ClaimCase(BaseModel):
    """A complete generated claim case — profile + ordered document timeline."""

    case_id: str
    scenario_slug: str
    seed: int
    profile: ClaimProfile
    document_events: list[DocumentEvent]
    stages_visited: list[str]

    class Config:
        json_encoders = {bytes: lambda b: ""}  # Never serialize PDF bytes to JSON

    def model_dump_json_safe(self) -> dict[str, Any]:
        """Return JSON-serializable dict with pdf_bytes excluded."""
        d = self.model_dump()
        for event in d.get("document_events", []):
            event.pop("pdf_bytes", None)
        return d
