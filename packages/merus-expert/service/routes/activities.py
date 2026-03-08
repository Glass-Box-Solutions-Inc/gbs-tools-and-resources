"""
Activity routes — non-billable notes.
# @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import logging
from fastapi import APIRouter, Depends
from merus_expert.core.agent import MerusAgent
from service.auth import verify_api_key
from service.dependencies import get_merus_agent
from service.models.requests import AddNoteRequest
from service.models.responses import AddNoteResponse

router = APIRouter(prefix="/api/activities", tags=["activities"])
logger = logging.getLogger(__name__)


@router.post("/note", response_model=AddNoteResponse)
async def add_note(
    request: AddNoteRequest,
    _: str = Depends(verify_api_key),
    agent: MerusAgent = Depends(get_merus_agent),
):
    """Add a non-billable note/activity to a case."""
    result = await agent.add_note(
        case_search=request.case_search,
        subject=request.subject,
        description=request.description,
        activity_type_id=request.activity_type_id,
    )
    return AddNoteResponse(**result)
