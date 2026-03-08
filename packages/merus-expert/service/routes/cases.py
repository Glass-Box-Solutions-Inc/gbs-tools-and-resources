"""
Case management routes.
# @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, Query
from merus_expert.core.agent import MerusAgent
from service.auth import verify_api_key
from service.dependencies import get_merus_agent
from service.models.responses import CaseResponse, BillingResponse, PartiesResponse, BillingSummaryResponse

router = APIRouter(prefix="/api", tags=["cases"])
logger = logging.getLogger(__name__)


@router.get("/cases/search", response_model=CaseResponse)
async def search_case(
    query: str = Query(..., description="Case file number or party name"),
    limit: int = Query(50, ge=1, le=200),
    _: str = Depends(verify_api_key),
    agent: MerusAgent = Depends(get_merus_agent),
):
    """Find a case by file number or party name (fuzzy search)."""
    case = await agent.find_case(query, limit=limit)
    return CaseResponse(
        id=str(case["id"]),
        file_number=case.get("file_number"),
        primary_party_name=case.get("primary_party_name"),
        case_status=case.get("case_status"),
        case_type=case.get("case_type"),
        data=case,
    )


@router.get("/cases", tags=["cases"])
async def list_cases(
    status: Optional[str] = Query(None, description="Filter by status"),
    type: Optional[str] = Query(None, description="Filter by type"),
    limit: int = Query(100, ge=1, le=500),
    _: str = Depends(verify_api_key),
    agent: MerusAgent = Depends(get_merus_agent),
):
    """List all cases with optional filters."""
    cases = await agent.list_all_cases(case_status=status, case_type=type, limit=limit)
    return {"cases": cases, "count": len(cases)}


@router.get("/cases/{case_id}", response_model=CaseResponse)
async def get_case(
    case_id: int,
    _: str = Depends(verify_api_key),
    agent: MerusAgent = Depends(get_merus_agent),
):
    """Get full case details by ID."""
    details = await agent.get_case_details(case_id)
    return CaseResponse(
        id=str(case_id),
        file_number=details.get("file_number"),
        primary_party_name=details.get("primary_party_name"),
        case_status=details.get("case_status"),
        case_type=details.get("case_type"),
        data=details,
    )


@router.get("/cases/{case_id}/billing", response_model=BillingResponse)
async def get_case_billing(
    case_id: int,
    date_gte: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_lte: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    _: str = Depends(verify_api_key),
    agent: MerusAgent = Depends(get_merus_agent),
):
    """Get billing/ledger entries for a case."""
    billing = await agent.get_case_billing(case_id, date_gte=date_gte, date_lte=date_lte)
    entries = billing.get("data", {})
    return BillingResponse(case_id=str(case_id), entries=entries, total_entries=len(entries))


@router.get("/cases/{case_id}/activities")
async def get_case_activities(
    case_id: int,
    limit: int = Query(100, ge=1, le=500),
    _: str = Depends(verify_api_key),
    agent: MerusAgent = Depends(get_merus_agent),
):
    """Get activities/notes for a case."""
    activities = await agent.get_case_activities(case_id, limit=limit)
    return {"case_id": str(case_id), "activities": activities, "count": len(activities)}


@router.get("/cases/{case_id}/parties", response_model=PartiesResponse)
async def get_case_parties(
    case_id: int,
    _: str = Depends(verify_api_key),
    agent: MerusAgent = Depends(get_merus_agent),
):
    """Get parties/contacts for a case."""
    parties = await agent.get_case_parties(case_id)
    return PartiesResponse(case_id=str(case_id), parties=parties)


@router.get("/cases/{case_id}/summary", response_model=BillingSummaryResponse)
async def get_billing_summary(
    case_id: int,
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    _: str = Depends(verify_api_key),
    agent: MerusAgent = Depends(get_merus_agent),
):
    """Get billing summary for a case."""
    case = await agent.get_case_details(case_id)
    case_search = case.get("file_number") or str(case_id)
    summary = await agent.get_billing_summary(case_search, start_date=start_date, end_date=end_date)
    return BillingSummaryResponse(**summary)
