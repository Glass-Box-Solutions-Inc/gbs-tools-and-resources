"""
Explore MerusCase API for document download endpoints.
"""

import asyncio
import logging
from pathlib import Path
import httpx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_BASE = "https://api.meruscase.com"
TOKEN = Path(".meruscase_token").read_text().strip()


async def explore_documents():
    """Try various document-related endpoints."""

    # Common endpoint patterns to try
    doc_endpoints = [
        # Document listing
        ("GET", "documents/index", "List all documents"),
        ("GET", "uploads/index", "List uploads"),
        ("GET", "files/index", "List files"),
        ("GET", "attachments/index", "List attachments"),

        # Document folders
        ("GET", "folders/index", "List folders"),
        ("GET", "documentFolders/index", "Document folders"),

        # With case file ID (we'll get one first)
        # These will be tested after we get a case ID
    ]

    logger.info(f"\n{'='*70}")
    logger.info("EXPLORING DOCUMENT API ENDPOINTS")
    logger.info(f"{'='*70}\n")

    async with httpx.AsyncClient(
        headers={"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"},
        timeout=30.0
    ) as client:

        # First, get a case file ID to test with
        logger.info("Step 1: Getting a case file ID...")
        resp = await client.get(f"{API_BASE}/caseFiles/index?limit=3")
        cases_data = resp.json()

        case_id = None
        if isinstance(cases_data, dict) and "caseFiles" in cases_data:
            cases = cases_data["caseFiles"]
            if cases:
                case_id = cases[0].get("id") or cases[0].get("case_file_id")
                logger.info(f"  Found case ID: {case_id}")
                logger.info(f"  Case keys: {list(cases[0].keys())[:10]}")
        elif isinstance(cases_data, list) and cases_data:
            case_id = cases_data[0].get("id") or cases_data[0].get("case_file_id")
            logger.info(f"  Found case ID: {case_id}")

        # Test generic document endpoints
        logger.info("\nStep 2: Testing generic document endpoints...")
        for method, endpoint, description in doc_endpoints:
            try:
                resp = await client.get(f"{API_BASE}/{endpoint}")
                data = resp.json()

                has_error = "errors" in data and data.get("errors")

                if resp.status_code == 200 and not has_error:
                    logger.info(f"  ✓ {endpoint}: WORKS!")
                    if isinstance(data, dict):
                        logger.info(f"      Keys: {list(data.keys())[:8]}")
                    elif isinstance(data, list):
                        logger.info(f"      Items: {len(data)}")
                else:
                    error = data.get("errors", [{"errorMessage": f"HTTP {resp.status_code}"}])
                    if isinstance(error, list) and error:
                        msg = error[0].get("errorMessage", str(error))
                    else:
                        msg = str(error)
                    logger.info(f"  ✗ {endpoint}: {msg[:50]}")

            except Exception as e:
                logger.info(f"  ✗ {endpoint}: {str(e)[:50]}")

        # Test case-specific document endpoints
        if case_id:
            logger.info(f"\nStep 3: Testing case-specific endpoints (case_id={case_id})...")

            case_doc_endpoints = [
                f"documents/index/{case_id}",
                f"documents/index?case_file_id={case_id}",
                f"uploads/index/{case_id}",
                f"uploads/index?case_file_id={case_id}",
                f"files/index/{case_id}",
                f"files/index?case_file_id={case_id}",
                f"attachments/index/{case_id}",
                f"attachments/index?case_file_id={case_id}",
                f"caseFiles/view/{case_id}",  # Full case details might include docs
                f"folders/index/{case_id}",
                f"folders/index?case_file_id={case_id}",
            ]

            for endpoint in case_doc_endpoints:
                try:
                    resp = await client.get(f"{API_BASE}/{endpoint}")
                    data = resp.json()

                    has_error = "errors" in data and data.get("errors")

                    if resp.status_code == 200 and not has_error:
                        logger.info(f"  ✓ {endpoint}: WORKS!")
                        if isinstance(data, dict):
                            logger.info(f"      Keys: {list(data.keys())[:10]}")
                            # Check for document-related keys
                            for key in data.keys():
                                if any(doc_word in key.lower() for doc_word in ["doc", "file", "upload", "attach", "folder"]):
                                    logger.info(f"      >>> Found '{key}': {str(data[key])[:100]}")
                        elif isinstance(data, list):
                            logger.info(f"      Items: {len(data)}")
                            if data:
                                logger.info(f"      Sample keys: {list(data[0].keys()) if isinstance(data[0], dict) else 'N/A'}")
                    else:
                        pass  # Skip logging failures for brevity

                except Exception as e:
                    pass

        # Check case file view for document info
        if case_id:
            logger.info(f"\nStep 4: Checking full case details for document info...")
            resp = await client.get(f"{API_BASE}/caseFiles/view/{case_id}")
            data = resp.json()

            if resp.status_code == 200:
                logger.info(f"  Case view response keys: {list(data.keys())}")

                # Look for any document-related data
                def find_doc_keys(obj, prefix=""):
                    if isinstance(obj, dict):
                        for k, v in obj.items():
                            if any(word in k.lower() for word in ["doc", "file", "upload", "attach", "folder"]):
                                logger.info(f"  >>> {prefix}{k}: {str(v)[:100]}")
                            if isinstance(v, (dict, list)):
                                find_doc_keys(v, f"{prefix}{k}.")
                    elif isinstance(obj, list) and obj:
                        find_doc_keys(obj[0], f"{prefix}[0].")

                find_doc_keys(data)

        # Try download endpoint patterns
        logger.info(f"\nStep 5: Testing download endpoint patterns...")
        download_patterns = [
            "documents/download/1",
            "uploads/download/1",
            "files/download/1",
            "attachments/download/1",
            "documents/view/1",
            "uploads/view/1",
        ]

        for endpoint in download_patterns:
            try:
                resp = await client.get(f"{API_BASE}/{endpoint}")
                if resp.status_code == 200:
                    content_type = resp.headers.get("content-type", "")
                    logger.info(f"  ✓ {endpoint}: {resp.status_code} ({content_type[:30]})")
                elif resp.status_code == 404:
                    # 404 might mean endpoint exists but ID doesn't
                    logger.info(f"  ? {endpoint}: 404 (endpoint may exist)")
                else:
                    pass
            except:
                pass

        logger.info(f"\n{'='*70}")
        logger.info("EXPLORATION COMPLETE")
        logger.info(f"{'='*70}")


if __name__ == "__main__":
    asyncio.run(explore_documents())
