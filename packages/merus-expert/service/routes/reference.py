"""
Reference data routes — billing codes and activity types.
# @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import logging
from fastapi import APIRouter, Depends
from merus_expert.core.agent import MerusAgent
from service.auth import verify_api_key
from service.dependencies import get_merus_agent
from service.models.responses import ReferenceDataResponse

router = APIRouter(prefix="/api/reference", tags=["reference"])
logger = logging.getLogger(__name__)


@router.get("/billing-codes", response_model=ReferenceDataResponse)
async def get_billing_codes(
    _: str = Depends(verify_api_key),
    agent: MerusAgent = Depends(get_merus_agent),
):
    """Get billing codes (cached 1 hour)."""
    codes = await agent.get_billing_codes()
    return ReferenceDataResponse(data=codes, count=len(codes))


@router.get("/activity-types", response_model=ReferenceDataResponse)
async def get_activity_types(
    _: str = Depends(verify_api_key),
    agent: MerusAgent = Depends(get_merus_agent),
):
    """Get activity types (cached 1 hour)."""
    types = await agent.get_activity_types()
    return ReferenceDataResponse(data=types, count=len(types))
