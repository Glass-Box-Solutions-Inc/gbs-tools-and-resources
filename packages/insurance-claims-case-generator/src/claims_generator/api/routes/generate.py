"""
POST /api/v1/generate — synchronous single-case generation.

Returns a JSON manifest + the ZIP exported in memory.
The ZIP is embedded as base64 in the response for small cases; large cases should
use the batch endpoint instead.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from claims_generator.api.schemas import DocumentEventSummary, GenerateRequest, GenerateResponse
from claims_generator.case_builder import build_case
from claims_generator.exporter import export_case_to_zip

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/generate", response_model=GenerateResponse, tags=["generate"])
async def generate_case(req: GenerateRequest) -> GenerateResponse:
    """
    Generate a single claim case synchronously.

    Returns the case manifest and exports a ZIP.  The ZIP size is reported in
    ``zip_size_bytes``; callers that need the actual bytes should use the batch
    endpoint and retrieve via GET /api/v1/export/{job_id}.
    """
    try:
        case = build_case(
            scenario_slug=req.scenario,
            seed=req.seed,
            generate_pdfs=req.generate_pdfs,
        )
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception(
            "Unexpected error generating case scenario=%s seed=%d",
            req.scenario, req.seed,
        )
        raise HTTPException(status_code=500, detail=f"Case generation failed: {exc}") from exc

    # Export to ZIP (in memory)
    try:
        zip_bytes = export_case_to_zip(case)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    events = [
        DocumentEventSummary(
            event_id=e.event_id,
            document_type=e.document_type.value,
            subtype_slug=e.subtype_slug,
            title=e.title,
            event_date=e.event_date.isoformat(),
            stage=e.stage,
            access_level=e.access_level,
            deadline_date=e.deadline_date.isoformat() if e.deadline_date else None,
            deadline_statute=e.deadline_statute,
            metadata=e.metadata,
        )
        for e in case.document_events
    ]

    return GenerateResponse(
        case_id=case.case_id,
        scenario_slug=case.scenario_slug,
        seed=case.seed,
        document_count=len(case.document_events),
        stages_visited=case.stages_visited,
        document_events=events,
        zip_size_bytes=len(zip_bytes),
    )
