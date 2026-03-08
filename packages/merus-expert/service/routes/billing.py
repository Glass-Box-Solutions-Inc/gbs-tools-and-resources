"""
Billing routes — time billing and cost entries.
# @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import logging
from fastapi import APIRouter, Depends
from merus_expert.core.agent import MerusAgent
from service.auth import verify_api_key
from service.dependencies import get_merus_agent
from service.models.requests import BillTimeRequest, AddCostRequest, BulkBillTimeRequest
from service.models.responses import BillTimeResponse, AddCostResponse, BulkBillTimeResponse

router = APIRouter(prefix="/api", tags=["billing"])
logger = logging.getLogger(__name__)


@router.post("/billing/time", response_model=BillTimeResponse)
async def bill_time(
    request: BillTimeRequest,
    _: str = Depends(verify_api_key),
    agent: MerusAgent = Depends(get_merus_agent),
):
    """Bill time to a case (natural language search)."""
    result = await agent.bill_time(
        case_search=request.case_search,
        hours=request.hours,
        description=request.description,
        subject=request.subject,
        activity_type_id=request.activity_type_id,
        billing_code_id=request.billing_code_id,
    )
    return BillTimeResponse(**result)


@router.post("/billing/cost", response_model=AddCostResponse)
async def add_cost(
    request: AddCostRequest,
    _: str = Depends(verify_api_key),
    agent: MerusAgent = Depends(get_merus_agent),
):
    """Add a direct cost/fee to a case."""
    result = await agent.add_cost(
        case_search=request.case_search,
        amount=request.amount,
        description=request.description,
        ledger_type=request.ledger_type,
    )
    return AddCostResponse(**result)


@router.post("/billing/time/bulk", response_model=BulkBillTimeResponse)
async def bulk_bill_time(
    request: BulkBillTimeRequest,
    _: str = Depends(verify_api_key),
    agent: MerusAgent = Depends(get_merus_agent),
):
    """Bill time to multiple cases in batch."""
    entries = [entry.model_dump() for entry in request.entries]
    results = await agent.bulk_bill_time(entries)
    successful = sum(1 for r in results if r.get("success"))
    failed = len(results) - successful
    return BulkBillTimeResponse(results=results, successful=successful, failed=failed)
