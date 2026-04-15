"""
Document operations: upload files, list documents.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


def _normalize_documents(response: dict) -> list[dict]:
    """Extract a flat list of document dicts from a MerusCase API response.

    The CakePHP API can return documents as a dict keyed by ID or as a list.

    Args:
        response: Raw dict from MerusCaseAPIClient.list_documents().

    Returns:
        Flat list of document dicts.
    """
    docs_data = response.get("data", response)

    if isinstance(docs_data, list):
        return docs_data

    if isinstance(docs_data, dict):
        return list(docs_data.values())

    logger.warning(
        "_normalize_documents: unexpected type %s", type(docs_data)
    )
    return []


async def upload_document(
    client,
    case_id: int,
    file_path: str,
    description: str = "",
    folder_id: Optional[int] = None,
) -> dict:
    """Upload a document file to a case.

    Args:
        client: MerusCaseAPIClient.
        case_id: MerusCase case ID.
        file_path: Absolute path to local file.
        description: Optional document description.
        folder_id: Optional target folder ID.

    Returns:
        dict: {success, case_id, filename, data}

    Raises:
        FileNotFoundError: If file_path does not exist.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    response = await client.upload_document(
        case_id,
        file_path,
        description=description,
        folder_id=folder_id,
    )

    filename = os.path.basename(file_path)
    logger.info(
        "upload_document: '%s' uploaded to case %s", filename, case_id
    )

    return {
        "success": True,
        "case_id": case_id,
        "filename": filename,
        "data": response,
    }


async def list_documents(client, case_id: int) -> list[dict]:
    """List documents associated with a case.

    Args:
        client: MerusCaseAPIClient.
        case_id: MerusCase case ID.

    Returns:
        List of document dicts.
    """
    response = await client.list_documents(case_id)
    return _normalize_documents(response)
