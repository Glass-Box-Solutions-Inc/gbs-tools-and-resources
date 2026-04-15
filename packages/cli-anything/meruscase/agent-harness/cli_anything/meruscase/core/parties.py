"""
Party operations: list parties associated with a case, add a party.
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def _normalize_parties(response: dict) -> list[dict]:
    """Extract a flat list of party dicts from a MerusCase API response.

    The CakePHP API returns parties as a dict keyed by party ID, with positional
    field names. Known positional mappings (confirmed from live API):
      "0" → people_type_id (party type ID)
      "1" → first_name
      "2" → last_name

    Args:
        response: Raw dict from MerusCaseAPIClient.get_parties().

    Returns:
        Flat list of party dicts with named fields added.
    """
    parties_data = response.get("data", response)

    if isinstance(parties_data, list):
        return parties_data

    if isinstance(parties_data, dict):
        result = []
        for party_id, party_data in parties_data.items():
            first = str(party_data.get("1", "")).strip()
            last = str(party_data.get("2", "")).strip()
            name = f"{last}, {first}" if last and first else (last or first or "")
            named = {
                "id": party_id,
                "name": name,
                "first_name": first,
                "last_name": last,
                **party_data,
            }
            result.append(named)
        return result

    logger.warning(
        "_normalize_parties: unexpected type %s", type(parties_data)
    )
    return []


async def get_parties(client, case_id: int) -> list[dict]:
    """List all parties for a case.

    Args:
        client: MerusCaseAPIClient.
        case_id: MerusCase case ID.

    Returns:
        List of party dicts (Client, Employer, Insurance Company, etc.).
    """
    response = await client.get_parties(case_id)
    return _normalize_parties(response)


async def add_party(
    client,
    case_id: int,
    party_type: str,
    company_name: Optional[str] = None,
    notes: Optional[str] = None,
) -> dict:
    """Add a party to a case.

    Args:
        client: MerusCaseAPIClient.
        case_id: MerusCase case ID.
        party_type: e.g. "Employer", "Insurance Company", "Opposing Party".
        company_name: Optional company name.
        notes: Optional notes.

    Returns:
        dict: {success, party_id, case_id, party_type}
    """
    data: dict = {
        "case_file_id": case_id,
        "party_type": party_type,
    }
    if company_name is not None:
        data["company_name"] = company_name
    if notes is not None:
        data["notes"] = notes

    response = await client.add_party(data)

    # The API wraps the saved record under {"Party": {...}}
    party_record = response.get("Party", response.get("data", response))
    party_id = (
        party_record.get("id")
        if isinstance(party_record, dict)
        else None
    )

    logger.info(
        "add_party: %s party added to case %s (party_id=%s)",
        party_type,
        case_id,
        party_id,
    )

    return {
        "success": True,
        "party_id": party_id,
        "case_id": case_id,
        "party_type": party_type,
    }
