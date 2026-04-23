"""
FastAPI middleware — CORS, request ID injection, structured request logging.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)


def add_cors(app: FastAPI, allow_origins: list[str] | None = None) -> None:
    """
    Add CORS middleware to the app.

    Defaults to allowing all origins in development. Pass explicit origins for
    production hardening.
    """
    origins = allow_origins or ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )


async def request_id_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """
    Inject a unique X-Request-ID header into every request/response pair.

    Generates a new UUID if the client did not supply one.
    """
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id

    start = time.monotonic()
    response: Response = await call_next(request)
    elapsed_ms = (time.monotonic() - start) * 1000

    response.headers["X-Request-ID"] = request_id

    logger.info(
        "%s %s %d %.1fms req=%s",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
        request_id,
    )
    return response
