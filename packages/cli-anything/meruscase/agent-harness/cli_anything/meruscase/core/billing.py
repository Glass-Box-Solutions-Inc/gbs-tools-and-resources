"""
Billing operations: bill time, add costs, get ledger entries, get summary.
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

LEDGER_TYPE_MAP = {"fee": 1, "cost": 2, "expense": 3}


def _normalize_ledger_entries(response: dict) -> list[dict]:
    """Extract a flat list of ledger entries from a MerusCase API response.

    The MerusCase ledger API (/caseLedgersOpen/index) returns a nested shape:
      {"data": {"meta": {"success": True, ...}, "data": [entry, ...]}}

    The outer ``data`` key holds an inner dict with ``meta`` and ``data`` keys,
    where the inner ``data`` contains the actual ledger entry list.

    This function also handles the simpler shapes that may be returned by other
    endpoints:
      - Flat list:   {"data": [{...}, ...]}
      - Flat dict keyed by ID: {"data": {"123": {...}, ...}}

    Args:
        response: Raw dict from MerusCaseAPIClient.get_ledger().

    Returns:
        Flat list of ledger entry dicts.
    """
    outer_data = response.get("data", response)

    # Shape 1: Nested envelope — {"meta": {...}, "data": [...]}
    if isinstance(outer_data, dict) and "data" in outer_data:
        inner = outer_data["data"]
        if isinstance(inner, list):
            return [e for e in inner if isinstance(e, dict)]
        if isinstance(inner, dict):
            return [v for v in inner.values() if isinstance(v, dict)]

    # Shape 2: Flat list
    if isinstance(outer_data, list):
        return [e for e in outer_data if isinstance(e, dict)]

    # Shape 3: Flat dict keyed by string ID
    if isinstance(outer_data, dict):
        return [v for v in outer_data.values() if isinstance(v, dict)]

    logger.warning(
        "_normalize_ledger_entries: unexpected type %s", type(outer_data)
    )
    return []


async def get_billing(
    client,
    case_id: int,
    date_gte: Optional[str] = None,
    date_lte: Optional[str] = None,
) -> list[dict]:
    """Fetch ledger entries for a case.

    Args:
        client: MerusCaseAPIClient.
        case_id: MerusCase case ID.
        date_gte: Start date filter YYYY-MM-DD.
        date_lte: End date filter YYYY-MM-DD.

    Returns:
        List of ledger entry dicts.
    """
    response = await client.get_ledger(case_id, date_gte=date_gte, date_lte=date_lte)
    return _normalize_ledger_entries(response)


async def bill_time(
    client,
    case_id: int,
    hours: float,
    description: str,
    subject: Optional[str] = None,
    activity_type_id: Optional[int] = None,
    billing_code_id: Optional[int] = None,
) -> dict:
    """Bill attorney time to a case.

    Converts hours to minutes (hours × 60) and creates a billable Activity.

    Args:
        client: MerusCaseAPIClient.
        case_id: MerusCase case ID.
        hours: Time in hours (e.g. 0.5 = 30 min).
        description: Detailed description of work.
        subject: Short subject line (auto-generated from description if omitted).
        activity_type_id: Optional activity type.
        billing_code_id: Optional billing code.

    Returns:
        dict: {success, activity_id, case_id, hours, minutes, description}
    """
    minutes = round(hours * 60)

    # Auto-generate subject from the first 60 characters of description when
    # the caller did not provide an explicit one.
    if subject is None:
        subject = description[:60]

    data: dict = {
        "case_file_id": case_id,
        "subject": subject,
        "description": description,
        "duration_minutes": minutes,
        "billable": True,
    }
    if activity_type_id is not None:
        data["activity_type_id"] = activity_type_id
    if billing_code_id is not None:
        data["billing_code_id"] = billing_code_id

    response = await client.add_activity(data)

    # The API wraps the saved record under {"Activity": {...}}; fall back to
    # the top-level response if that key is absent.
    activity_record = response.get("Activity", response.get("data", response))
    activity_id = (
        activity_record.get("id")
        if isinstance(activity_record, dict)
        else None
    )

    logger.info(
        "bill_time: %s hours (%s min) billed to case %s (activity_id=%s)",
        hours,
        minutes,
        case_id,
        activity_id,
    )

    return {
        "success": True,
        "activity_id": activity_id,
        "case_id": case_id,
        "hours": hours,
        "minutes": minutes,
        "description": description,
    }


async def add_cost(
    client,
    case_id: int,
    amount: float,
    description: str,
    ledger_type: str = "cost",
) -> dict:
    """Add a direct cost/fee/expense to a case (not for time billing).

    Args:
        client: MerusCaseAPIClient.
        case_id: MerusCase case ID.
        amount: Dollar amount.
        description: Description of cost.
        ledger_type: "fee", "cost", or "expense".

    Returns:
        dict: {success, ledger_id, case_id, amount, description, type}
    """
    ledger_type_id = LEDGER_TYPE_MAP.get(ledger_type.lower(), LEDGER_TYPE_MAP["cost"])

    data = {
        "case_file_id": case_id,
        "amount": amount,
        "description": description,
        "ledger_type_id": ledger_type_id,
    }

    response = await client.add_ledger(data)

    # The API wraps the saved record under {"CaseLedger": {...}}
    ledger_record = response.get("CaseLedger", response.get("data", response))
    if isinstance(ledger_record, dict):
        ledger_id = ledger_record.get("id")
    else:
        ledger_id = None

    logger.info(
        "add_cost: $%.2f %s added to case %s (ledger_id=%s)",
        amount,
        ledger_type,
        case_id,
        ledger_id,
    )

    return {
        "success": True,
        "ledger_id": ledger_id,
        "case_id": case_id,
        "amount": amount,
        "description": description,
        "type": ledger_type,
    }


async def get_billing_summary(
    client,
    case_id: int,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> dict:
    """Get billing summary with totals for a case.

    Args:
        client: MerusCaseAPIClient.
        case_id: MerusCase case ID.
        start_date: Optional start date YYYY-MM-DD.
        end_date: Optional end date YYYY-MM-DD.

    Returns:
        dict: {case_id, total_amount, total_entries, entries, date_range}
    """
    entries = await get_billing(
        client, case_id, date_gte=start_date, date_lte=end_date
    )

    total_amount = sum(float(e.get("amount", 0)) for e in entries)

    return {
        "case_id": case_id,
        "total_amount": total_amount,
        "total_entries": len(entries),
        "entries": entries,
        "date_range": {"start": start_date, "end": end_date},
    }


async def get_billing_codes(client) -> dict:
    """Fetch available billing codes (cached 1 hour by the API client).

    Args:
        client: MerusCaseAPIClient.

    Returns:
        Dict of billing codes keyed by ID.
    """
    return await client.get_billing_codes()
