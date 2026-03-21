"""
FastAPI application factory.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from service.config import CORS_ORIGINS


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup/shutdown."""
    yield


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="MerusCase WC Test Data Generator API",
        description="REST API for generating Workers' Compensation test case data with PDFs",
        version="2.0.0",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routes
    from service.routes.health import router as health_router
    from service.routes.taxonomy import router as taxonomy_router
    from service.routes.generation import router as generation_router
    from service.routes.runs import router as runs_router
    from service.routes.preview import router as preview_router
    from service.routes.download import router as download_router
    from service.routes.meruscase import router as meruscase_router

    app.include_router(health_router)
    app.include_router(taxonomy_router)
    app.include_router(generation_router)
    app.include_router(runs_router)
    app.include_router(preview_router)
    app.include_router(download_router)
    app.include_router(meruscase_router)

    return app
