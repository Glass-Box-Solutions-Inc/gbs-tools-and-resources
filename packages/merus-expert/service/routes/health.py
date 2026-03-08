"""
Health check route.
# @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from datetime import datetime
from fastapi import APIRouter
from service.models.responses import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint — no auth required."""
    return HealthResponse(
        status="healthy",
        timestamp=datetime.now().isoformat(),
        service="merus-expert",
        version="2.0.0",
    )
