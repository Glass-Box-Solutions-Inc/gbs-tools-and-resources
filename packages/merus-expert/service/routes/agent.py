"""
Agent route — Claude AI agent with SSE streaming.
# @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import json
import logging
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from service.auth import verify_api_key
from service.dependencies import get_claude_agent
from service.models.requests import ChatRequest
from merus_expert.agent.claude_agent import ClaudeAgent

router = APIRouter(prefix="/api/agent", tags=["agent"])
logger = logging.getLogger(__name__)


@router.post("/chat")
async def agent_chat(
    request: ChatRequest,
    _: str = Depends(verify_api_key),
    agent: ClaudeAgent = Depends(get_claude_agent),
):
    """
    Chat with Claude AI agent via Server-Sent Events (SSE).

    Stream events:
    - text: {"type": "text", "content": "..."}
    - tool_call: {"type": "tool_call", "name": "...", "input": {...}}
    - tool_result: {"type": "tool_result", "name": "...", "result": {...}}
    - done: {"type": "done"}
    - error: {"type": "error", "message": "..."}
    """

    async def event_stream():
        try:
            async for event in agent.chat_stream(
                messages=request.messages,
                max_iterations=request.max_iterations,
            ):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            logger.error(f"Agent stream error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
