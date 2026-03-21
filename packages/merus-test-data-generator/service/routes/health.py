"""Health check route."""

from fastapi import APIRouter

from service.models.responses import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse()
