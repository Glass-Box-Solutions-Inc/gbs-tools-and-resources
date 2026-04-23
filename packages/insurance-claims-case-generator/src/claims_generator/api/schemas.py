"""
Pydantic request/response schemas for the FastAPI routes.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

from claims_generator.api.job_store import JobStatus
from claims_generator.models.scenario import ScenarioPreset  # noqa: TCH001

# ---------------------------------------------------------------------------
# Generate endpoint
# ---------------------------------------------------------------------------


class GenerateRequest(BaseModel):
    """POST /api/v1/generate — single case request."""

    scenario: str = Field(
        default="standard_claim",
        description="Scenario slug (e.g. 'standard_claim', 'litigated_qme')",
    )
    seed: int = Field(
        default=42,
        ge=0,
        description="Random seed for reproducibility",
    )
    generate_pdfs: bool = Field(
        default=True,
        description="Whether to include PDFs in the export ZIP. Set False for JSON-only.",
    )


class DocumentEventSummary(BaseModel):
    """Lightweight representation of a DocumentEvent (no pdf_bytes)."""

    event_id: str
    document_type: str
    subtype_slug: str
    title: str
    event_date: str
    stage: str
    access_level: str
    deadline_date: Optional[str] = None
    deadline_statute: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class GenerateResponse(BaseModel):
    """POST /api/v1/generate — single case response."""

    case_id: str
    scenario_slug: str
    seed: int
    document_count: int
    stages_visited: list[str]
    document_events: list[DocumentEventSummary]
    zip_size_bytes: int = Field(description="Size of the exported ZIP archive in bytes")


# ---------------------------------------------------------------------------
# Batch endpoint
# ---------------------------------------------------------------------------


class BatchJobSpec(BaseModel):
    """A single job within a batch request."""

    scenario: str = Field(description="Scenario slug for this job")
    seed: int = Field(ge=0, description="Random seed")


class BatchRequest(BaseModel):
    """POST /api/v1/batch — async batch generation request."""

    jobs: list[BatchJobSpec] = Field(
        min_length=1,
        max_length=500,
        description="List of 1–500 individual generation jobs",
    )
    generate_pdfs: bool = Field(
        default=True,
        description="Whether to generate PDFs for each case",
    )
    max_workers: int = Field(
        default=4,
        ge=1,
        le=16,
        description="Maximum parallel worker threads",
    )

    @field_validator("jobs")
    @classmethod
    def jobs_not_empty(cls, v: list[BatchJobSpec]) -> list[BatchJobSpec]:
        if not v:
            raise ValueError("jobs must contain at least one entry")
        return v


class BatchResponse(BaseModel):
    """POST /api/v1/batch — immediate response with job_id for polling."""

    job_id: str
    status: JobStatus
    total: int
    message: str


# ---------------------------------------------------------------------------
# Job status endpoint
# ---------------------------------------------------------------------------


class JobStatusResponse(BaseModel):
    """GET /api/v1/jobs/{job_id} — job status + progress."""

    job_id: str
    status: JobStatus
    progress: int = Field(ge=0, le=100, description="Completion percentage 0–100")
    total: int
    completed: int
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Scenarios endpoint
# ---------------------------------------------------------------------------


class ScenarioResponse(BaseModel):
    """A single scenario preset as returned by the API."""

    slug: str
    display_name: str
    description: str
    litigated: bool
    attorney_represented: bool
    ct: bool
    denied_scenario: bool
    death_claim: bool
    ptd_claim: bool
    psych_overlay: bool
    multi_employer: bool
    split_carrier: bool
    high_liens: bool
    sjdb_dispute: bool
    expedited: bool
    investigation_active: bool
    expected_doc_min: int
    expected_doc_max: int

    @classmethod
    def from_preset(cls, preset: ScenarioPreset) -> "ScenarioResponse":
        return cls(**preset.model_dump(
            include={
                "slug", "display_name", "description",
                "litigated", "attorney_represented", "ct", "denied_scenario",
                "death_claim", "ptd_claim", "psych_overlay", "multi_employer",
                "split_carrier", "high_liens", "sjdb_dispute", "expedited",
                "investigation_active", "expected_doc_min", "expected_doc_max",
            }
        ))


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    """GET /api/v1/health — service health."""

    status: str = "ok"
    version: str
    scenario_count: int
    active_jobs: int
