"""
GET /api/v1/health — service health check.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from claims_generator.api.job_store import JobStore, get_job_store
from claims_generator.api.schemas import HealthResponse
from claims_generator.scenarios.registry import list_scenarios

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["meta"])
async def health(store: JobStore = Depends(get_job_store)) -> HealthResponse:
    """Return service health, version, and basic counters."""
    from claims_generator import __version__

    return HealthResponse(
        status="ok",
        version=__version__,
        scenario_count=len(list_scenarios()),
        active_jobs=len(store),
    )
