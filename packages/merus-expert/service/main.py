"""
merus-expert FastAPI Service — unified entrypoint.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import logging
import os
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from merus_expert.core.agent import CaseNotFoundError, BillingError, MerusAgentError
from service.dependencies import get_merus_agent, get_claude_agent
from service.routes import health, cases, billing, reference, agent, activities, chat, matter

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS", "http://localhost:3000,http://localhost:3001"
).split(",")

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _init_database():
    """Initialize SQLite database from schema.sql if tables don't exist."""
    db_path = os.getenv("DB_PATH", "./knowledge/db/merus_knowledge.db")
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    schema_file = Path(__file__).parent.parent / "setup" / "schema.sql"
    if schema_file.exists():
        conn = sqlite3.connect(db_path)
        try:
            conn.executescript(schema_file.read_text())
            logger.info(f"Database initialized at {db_path}")
        finally:
            conn.close()
    else:
        logger.warning(f"Schema file not found: {schema_file}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Pre-warm singletons and initialize database at startup."""
    logger.info("Starting merus-expert service...")

    _init_database()

    try:
        get_merus_agent()
        logger.info("MerusAgent initialized")
    except Exception as e:
        logger.warning(f"MerusAgent init deferred (token not available): {e}")

    try:
        get_claude_agent()
        logger.info("ClaudeAgent initialized")
    except Exception as e:
        logger.warning(f"ClaudeAgent init deferred: {e}")

    yield

    logger.info("Shutting down merus-expert service...")
    merus = get_merus_agent.__wrapped__() if hasattr(get_merus_agent, "__wrapped__") else None
    if merus:
        await merus.close()


app = FastAPI(
    title="merus-expert",
    description="Production MerusCase integration: REST API client, browser automation, Claude AI agent",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────────────
# Exception handlers
# ─────────────────────────────────────────────────────

@app.exception_handler(CaseNotFoundError)
async def case_not_found_handler(request, exc: CaseNotFoundError):
    return JSONResponse(
        status_code=404,
        content={"error": "Case not found", "detail": str(exc), "status_code": 404},
    )


@app.exception_handler(BillingError)
async def billing_error_handler(request, exc: BillingError):
    return JSONResponse(
        status_code=400,
        content={"error": "Billing error", "detail": str(exc), "status_code": 400},
    )


@app.exception_handler(MerusAgentError)
async def merus_agent_error_handler(request, exc: MerusAgentError):
    return JSONResponse(
        status_code=500,
        content={"error": "MerusAgent error", "detail": str(exc), "status_code": 500},
    )


# ─────────────────────────────────────────────────────
# Routers
# ─────────────────────────────────────────────────────

app.include_router(health.router)
app.include_router(cases.router)
app.include_router(billing.router)
app.include_router(activities.router)
app.include_router(reference.router)
app.include_router(agent.router)
app.include_router(chat.router)
app.include_router(matter.router)


# ─────────────────────────────────────────────────────
# Static frontend (served from Docker build)
# ─────────────────────────────────────────────────────

_static_dir = Path(__file__).parent.parent / "static"
if _static_dir.is_dir():
    # Serve static assets (JS, CSS, images)
    app.mount("/assets", StaticFiles(directory=_static_dir / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(request: Request, full_path: str):
        """SPA catch-all: serve index.html for any non-API route."""
        # Don't intercept API or docs routes
        if full_path.startswith(("api/", "docs", "openapi.json", "health")):
            return JSONResponse(status_code=404, content={"detail": "Not found"})
        return FileResponse(_static_dir / "index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("service.main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)), reload=False)
