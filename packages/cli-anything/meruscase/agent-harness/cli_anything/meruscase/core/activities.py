"""
Activity operations: list activities, add notes.
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def _normalize_activities(response: dict) -> list[dict]:
    """Extract a flat list of activity dicts from a MerusCase API response.

    The CakePHP API can return activities as a dict keyed by ID or as a list.

    Args:
        response: Raw dict from MerusCaseAPIClient.get_activities().

    Returns:
        Flat list of activity dicts.
    """
    activities_data = response.get("data", response)

    if isinstance(activities_data, list):
        return activities_data

    if isinstance(activities_data, dict):
        return list(activities_data.values())

    logger.warning(
        "_normalize_activities: unexpected type %s", type(activities_data)
    )
    return []


async def get_activities(client, case_id: int, limit: int = 100) -> list[dict]:
    """Fetch activities and notes for a case.

    The API returns all activities regardless of limit; slicing is applied
    in Python after normalisation.

    Args:
        client: MerusCaseAPIClient.
        case_id: MerusCase case ID.
        limit: Max results to return.

    Returns:
        List of activity dicts (up to ``limit``).
    """
    response = await client.get_activities(case_id)
    all_activities = _normalize_activities(response)
    return all_activities[:limit]


async def add_note(
    client,
    case_id: int,
    subject: str,
    description: Optional[str] = None,
    activity_type_id: Optional[int] = None,
) -> dict:
    """Add a non-billable note/activity to a case.

    Args:
        client: MerusCaseAPIClient.
        case_id: MerusCase case ID.
        subject: Note subject line.
        description: Optional detailed note body.
        activity_type_id: Optional activity type ID.

    Returns:
        dict: {success, activity_id, case_id, subject}
    """
    data: dict = {
        "case_file_id": case_id,
        "subject": subject,
        "description": description or "",
        "billable": False,
    }
    if activity_type_id is not None:
        data["activity_type_id"] = activity_type_id

    response = await client.add_activity(data)

    # The API wraps the saved record under {"Activity": {...}}
    activity_record = response.get("Activity", response.get("data", response))
    activity_id = (
        activity_record.get("id")
        if isinstance(activity_record, dict)
        else None
    )

    logger.info(
        "add_note: note '%s' added to case %s (activity_id=%s)",
        subject,
        case_id,
        activity_id,
    )

    return {
        "success": True,
        "activity_id": activity_id,
        "case_id": case_id,
        "subject": subject,
    }


async def get_activity_types(client) -> dict:
    """Fetch available activity types (cached 1 hour by the API client).

    Args:
        client: MerusCaseAPIClient.

    Returns:
        Dict of activity types keyed by ID.
    """
    return await client.get_activity_types()
