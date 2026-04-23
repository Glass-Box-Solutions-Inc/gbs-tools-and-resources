"""
GET /api/v1/export/{job_id} — download batch ZIP via StreamingResponse.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from claims_generator.api.job_store import JobStatus, JobStore, get_job_store

router = APIRouter()


@router.get("/export/{job_id}", tags=["batch"])
async def export_job_zip(
    job_id: str,
    store: JobStore = Depends(get_job_store),
) -> StreamingResponse:
    """
    Download the ZIP archive for a completed batch job.

    Returns 404 if the job does not exist.
    Returns 409 if the job has not yet completed (status != ``done``).
    Returns 500 if the job failed.
    """
    record = await store.get(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id!r}")

    if record.status == JobStatus.FAILED:
        raise HTTPException(
            status_code=500,
            detail=f"Job failed: {record.error or 'unknown error'}",
        )

    if record.status != JobStatus.DONE:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Job not yet complete (status={record.status.value}, "
                f"progress={record.progress}%)"
            ),
        )

    if record.result_zip is None:
        raise HTTPException(status_code=500, detail="Job marked done but ZIP is missing")

    zip_data = record.result_zip

    def _iter_zip():
        yield zip_data

    return StreamingResponse(
        _iter_zip(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="batch_{job_id[:8]}.zip"',
            "Content-Length": str(len(zip_data)),
        },
    )
