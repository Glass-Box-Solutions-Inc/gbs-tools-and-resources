"""
Case operations: list, find (fuzzy), get details, create (via browser).
"""
from __future__ import annotations

import logging
from typing import Optional

from cli_anything.meruscase.utils import browser_backend

logger = logging.getLogger(__name__)


class CaseNotFoundError(Exception):
    """Raised when a case cannot be found by the given search term."""


def _normalize_cases(response: dict) -> list[dict]:
    """Extract a flat list of case dicts from a MerusCase API response.

    The MerusCase CakePHP API returns cases in two shapes:

    Shape A — Dict keyed by string case ID (from /caseFiles/index with no
    query params). Each value is a positional dict with numeric string keys:
      {"data": {"4703360": {"0": "1", "1": "Smith v. Employer", "3": 163543, ...}}}

    Shape B — List (from filtered or paginated endpoints):
      {"data": [{...}, {...}]}

    In Shape A the positional fields map as follows (confirmed from live API):
      "1" → primary_party_name / case display name
      "3" → case_status_id
      "4" → case_type_id

    Both shapes are normalised to a flat list with named ``id`` and
    ``primary_party_name`` fields so the rest of the CLI can be field-name
    agnostic.

    Args:
        response: Raw dict returned by MerusCaseAPIClient.list_cases().

    Returns:
        Flat list of case dicts.
    """
    cases_data = response.get("data", response)

    if isinstance(cases_data, list):
        # Shape B — already a list; ensure each item has an 'id' field.
        return [
            {**case, "id": case.get("id", case.get("case_id"))}
            for case in cases_data
        ]

    if isinstance(cases_data, dict):
        # Shape A — dict keyed by string case IDs with positional field names.
        result = []
        for case_id, case_data in cases_data.items():
            # Map known positional keys to named fields.
            # Field "1" is the display name (e.g. "Smith, John v. Employer")
            # Keep the raw positional fields as well for forward compatibility.
            named: dict = {
                "id": case_id,
                "primary_party_name": case_data.get("1", ""),
                "case_status_id": case_data.get("3"),
                "case_type_id": case_data.get("0"),
                **case_data,  # preserve raw positional fields too
            }
            result.append(named)
        return result

    logger.warning("_normalize_cases: unexpected cases_data type %s", type(cases_data))
    return []


async def list_cases(
    client,
    case_status: Optional[str] = None,
    case_type: Optional[str] = None,
    limit: int = 100,
) -> list[dict]:
    """List cases, optionally filtered by status and/or type.

    The MerusCase API does not support server-side filtering or limit for
    /caseFiles/index — all filtering and slicing is performed in Python after
    fetching the full case list.

    Args:
        client: MerusCaseAPIClient instance.
        case_status: e.g. "Active", "Closed" — matched case-insensitively
            against the ``case_status_id`` field name (status names require a
            separate lookup; this filter is best-effort).
        case_type: e.g. "Workers Compensation" — matched case-insensitively.
        limit: Max results to return.

    Returns:
        List of case dicts (up to ``limit``).
    """
    response = await client.list_cases()
    all_cases = _normalize_cases(response)

    # Apply Python-side filters (best-effort — the list endpoint only returns
    # positional/ID fields, not human-readable status/type strings).
    filtered = all_cases
    if case_status:
        status_lower = case_status.lower()
        filtered = [
            c for c in filtered
            if status_lower in str(c.get("case_status_id", "")).lower()
            or status_lower in str(c.get("primary_party_name", "")).lower()
        ]
    if case_type:
        type_lower = case_type.lower()
        filtered = [
            c for c in filtered
            if type_lower in str(c.get("case_type_id", "")).lower()
        ]

    return filtered[:limit]


async def find_case(client, search: str, limit: int = 50) -> dict:
    """Find a single case by file number or party name (fuzzy match).

    Scans up to ``limit`` cases and returns the first whose file number
    or primary party name contains ``search`` (case-insensitive substring
    match).  File number is checked before party name so that numeric IDs
    are preferred over coincidental name matches.

    Args:
        client: MerusCaseAPIClient instance.
        search: Case file number or party name.
        limit: Max cases to scan.

    Returns:
        Best-matching case dict.

    Raises:
        CaseNotFoundError: If no match is found.
    """
    response = await client.list_cases(limit=limit)
    cases = _normalize_cases(response)

    search_lower = search.lower()

    # Pass 1: exact file number match
    for case in cases:
        file_number = str(case.get("file_number", "")).lower()
        if file_number == search_lower:
            logger.debug("find_case: exact file number match for '%s'", search)
            return case

    # Pass 2: substring match on file number
    for case in cases:
        file_number = str(case.get("file_number", "")).lower()
        if search_lower in file_number:
            logger.debug("find_case: file number substring match for '%s'", search)
            return case

    # Pass 3: substring match on primary party name
    for case in cases:
        party_name = str(case.get("primary_party_name", "")).lower()
        if search_lower in party_name:
            logger.debug("find_case: party name match for '%s'", search)
            return case

    raise CaseNotFoundError(f"No case found matching: {search}")


async def get_case(client, case_id: int) -> dict:
    """Fetch full details for a case by its numeric ID.

    Args:
        client: MerusCaseAPIClient instance.
        case_id: MerusCase numeric case ID.

    Returns:
        Case detail dict.
    """
    return await client.get_case(case_id)


async def create_case(
    party_name: str,
    case_type: str = "Workers Compensation",
    date_opened: Optional[str] = None,
) -> dict:
    """Create a new case via browser automation (no REST API available).

    Delegates to browser_backend.create_case().

    Args:
        party_name: "LASTNAME, FIRSTNAME" format.
        case_type: Case type (default "Workers Compensation").
        date_opened: MM/DD/YYYY. Defaults to today.

    Returns:
        dict: {meruscase_id, url, party_name}
    """
    return await browser_backend.create_case(
        party_name=party_name,
        case_type=case_type,
        date_opened=date_opened,
    )
