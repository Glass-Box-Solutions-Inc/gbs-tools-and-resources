"""
SSE (Server-Sent Events) progress streaming helper.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator


class ProgressEmitter:
    """Collects progress events and streams them via SSE."""

    def __init__(self):
        self._queue: asyncio.Queue = asyncio.Queue()
        self._done = False

    def emit(self, event: str, data: dict) -> None:
        """Emit a progress event (called from sync code)."""
        self._queue.put_nowait({"event": event, "data": data})

    def complete(self, data: dict | None = None) -> None:
        """Signal generation complete."""
        self._queue.put_nowait({"event": "complete", "data": data or {}})
        self._done = True

    def error(self, message: str) -> None:
        """Signal an error."""
        self._queue.put_nowait({"event": "error", "data": {"message": message}})
        self._done = True

    async def stream(self) -> AsyncGenerator[str, None]:
        """Yield SSE-formatted events."""
        while not self._done:
            try:
                item = await asyncio.wait_for(self._queue.get(), timeout=30.0)
                yield f"event: {item['event']}\ndata: {json.dumps(item['data'])}\n\n"
                if item["event"] in ("complete", "error"):
                    break
            except asyncio.TimeoutError:
                yield f"event: heartbeat\ndata: {{}}\n\n"
