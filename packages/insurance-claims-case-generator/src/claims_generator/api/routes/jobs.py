"""
GET /api/v1/jobs/{job_id} — poll batch job status and progress.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from claims_generator.api.job_store import JobStore, get_job_store
from claims_generator.api.schemas import JobStatusResponse

router = APIRouter()


@router.get("/jobs/{job_id}", response_model=JobStatusResponse, tags=["batch"])
async def get_job_status(
    job_id: str,
    store: JobStore = Depends(get_job_store),
) -> JobStatusResponse:
    """
    Poll the status of a batch job.

    Returns progress (0–100), status, and any error message.
    When status is ``done``, download the ZIP via GET /api/v1/export/{job_id}.
    """
    record = await store.get(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id!r}")

    return JobStatusResponse(
        job_id=record.job_id,
        status=record.status,
        progress=record.progress,
        total=record.total,
        completed=record.completed,
        error=record.error,
    )
