"""
Spectacles Health Routes
Health check and diagnostic endpoints
"""

import logging
from typing import Dict, Any
from datetime import datetime
from fastapi import APIRouter

from api.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """
    Basic health check endpoint.

    Returns service status and basic configuration info.
    """
    return {
        "status": "healthy",
        "service": "spectacles",
        "timestamp": datetime.now().isoformat(),
        "environment": settings.ENVIRONMENT,
    }


@router.get("/health/detailed")
async def detailed_health_check() -> Dict[str, Any]:
    """
    Detailed health check with dependency status.

    Checks:
    - Database connectivity
    - Slack configuration
    - Browserless configuration
    - VLM configuration
    """
    checks = {}

    # Check database
    try:
        from persistence.task_store import TaskStore
        store = TaskStore()
        # Just instantiating should work if DB is accessible
        checks["database"] = {"status": "ok", "path": store.db_path}
    except Exception as e:
        checks["database"] = {"status": "error", "error": str(e)}

    # Check Slack
    if settings.has_slack:
        checks["slack"] = {"status": "configured", "channel": settings.SLACK_APPROVAL_CHANNEL}
    else:
        checks["slack"] = {"status": "not_configured"}

    # Check Browserless
    if settings.has_browserless:
        checks["browserless"] = {"status": "configured", "endpoint": settings.BROWSERLESS_ENDPOINT}
    elif settings.USE_LOCAL_BROWSER:
        checks["browserless"] = {"status": "local_mode"}
    else:
        checks["browserless"] = {"status": "not_configured"}

    # Check VLM
    if settings.has_vlm:
        checks["vlm"] = {"status": "configured", "model": settings.VLM_MODEL}
    else:
        checks["vlm"] = {"status": "not_configured"}

    # Check GCP
    if settings.GCP_PROJECT_ID:
        checks["gcp"] = {"status": "configured", "project": settings.GCP_PROJECT_ID}
    else:
        checks["gcp"] = {"status": "not_configured"}

    # Overall status
    all_ok = all(
        c.get("status") in ["ok", "configured", "local_mode"]
        for c in checks.values()
    )

    return {
        "status": "healthy" if all_ok else "degraded",
        "service": "spectacles",
        "timestamp": datetime.now().isoformat(),
        "checks": checks,
    }


@router.get("/health/ready")
async def readiness_check() -> Dict[str, Any]:
    """
    Readiness check for Kubernetes/Cloud Run.

    Returns 200 if service is ready to accept traffic.
    """
    # Check minimum requirements
    missing = settings.validate_required_for_production()

    if missing and settings.is_production:
        return {
            "ready": False,
            "missing": missing
        }

    return {
        "ready": True,
        "environment": settings.ENVIRONMENT
    }


@router.get("/health/live")
async def liveness_check() -> Dict[str, Any]:
    """
    Liveness check for Kubernetes/Cloud Run.

    Returns 200 if service is alive.
    """
    return {"alive": True}
