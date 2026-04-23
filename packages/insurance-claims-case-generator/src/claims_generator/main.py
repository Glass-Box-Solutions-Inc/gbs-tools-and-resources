"""
FastAPI application factory + lifespan.

Entry point: uvicorn claims_generator.main:app --reload --port 8001

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware

from claims_generator.api.job_store import get_job_store, reset_job_store
from claims_generator.api.middleware import add_cors, request_id_middleware
from claims_generator.api.routes import batch, export, generate, health, jobs, scenarios

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lifespan — startup / shutdown
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Initialize shared resources on startup; tear down on shutdown."""
    # Ensure the job store is initialized
    get_job_store()
    logger.info("Claims Generator API starting. Job store initialized.")

    # Pre-warm scenario registry on startup
    from claims_generator.scenarios.registry import list_scenarios

    count = len(list_scenarios())
    logger.info("%d scenario presets registered.", count)

    yield  # app is live

    # On shutdown: discard in-memory job store
    reset_job_store()
    logger.info("Claims Generator API shut down. Job store cleared.")


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app(allow_origins: list[str] | None = None) -> FastAPI:
    """
    Create and configure the FastAPI application.

    Args:
        allow_origins: CORS allowed origins. Defaults to ``["*"]`` (development).

    Returns:
        Configured FastAPI instance.
    """
    app = FastAPI(
        title="Insurance Claims Case Generator",
        description=(
            "Lifecycle-aware synthetic CA Workers' Compensation claim case generator. "
            "Generates realistic PDF document sets for pipeline testing and staging seeding."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS
    add_cors(app, allow_origins=allow_origins)

    # Request ID + structured logging middleware
    app.add_middleware(BaseHTTPMiddleware, dispatch=request_id_middleware)

    # Routes
    prefix = "/api/v1"
    app.include_router(health.router, prefix=prefix)
    app.include_router(scenarios.router, prefix=prefix)
    app.include_router(generate.router, prefix=prefix)
    app.include_router(batch.router, prefix=prefix)
    app.include_router(jobs.router, prefix=prefix)
    app.include_router(export.router, prefix=prefix)

    return app


# Module-level app instance used by uvicorn
app = create_app()
