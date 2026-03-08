"""
Deep dive into uploads/documents endpoints.
"""

import asyncio
import logging
import json
from pathlib import Path
import httpx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_BASE = "https://api.meruscase.com"
TOKEN = Path(".meruscase_token").read_text().strip()


async def explore_uploads():
    """Deep dive into uploads endpoint."""

    logger.info(f"\n{'='*70}")
    logger.info("DEEP DIVE: UPLOADS & DOCUMENTS")
    logger.info(f"{'='*70}\n")

    async with httpx.AsyncClient(
        headers={"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"},
        timeout=30.0,
        follow_redirects=True
    ) as client:

        # 1. Get uploads/index full response
        logger.info("1. Checking uploads/index...")
        resp = await client.get(f"{API_BASE}/uploads/index")
        data = resp.json()
        logger.info(f"   Response: {json.dumps(data, indent=2)[:500]}")

        # 2. Get a case with documents
        logger.info("\n2. Getting cases to find one with documents...")
        resp = await client.get(f"{API_BASE}/caseFiles/index?limit=20")
        cases_data = resp.json()

        case_ids = []
        if "caseFiles" in cases_data:
            for case in cases_data["caseFiles"][:10]:
                case_id = case.get("id")
                case_ids.append(case_id)
                logger.info(f"   Case {case_id}: {case.get('file_number', 'N/A')}")

        # 3. Try uploads/index with case_file_id
        if case_ids:
            logger.info(f"\n3. Testing uploads/index with case_file_id...")
            for case_id in case_ids[:5]:
                resp = await client.get(f"{API_BASE}/uploads/index?case_file_id={case_id}")
                data = resp.json()

                uploads = data.get("data", [])
                if uploads:
                    logger.info(f"   Case {case_id}: {len(uploads)} uploads found!")
                    if isinstance(uploads, list) and uploads:
                        logger.info(f"   Sample upload: {json.dumps(uploads[0], indent=2)[:300]}")

                        # Try to download this upload
                        upload_id = uploads[0].get("id")
                        if upload_id:
                            logger.info(f"\n4. Trying to download upload {upload_id}...")

                            # Try different download patterns
                            patterns = [
                                f"uploads/download/{upload_id}",
                                f"uploads/view/{upload_id}",
                                f"documents/download/{upload_id}",
                                f"uploads/{upload_id}",
                            ]

                            for pattern in patterns:
                                try:
                                    resp = await client.get(f"{API_BASE}/{pattern}")
                                    content_type = resp.headers.get("content-type", "unknown")
                                    logger.info(f"   {pattern}: {resp.status_code} - {content_type[:40]}")

                                    if resp.status_code == 200:
                                        if "application/json" in content_type:
                                            logger.info(f"      JSON: {str(resp.json())[:200]}")
                                        elif "pdf" in content_type or "octet" in content_type:
                                            logger.info(f"      FILE DATA! Size: {len(resp.content)} bytes")
                                except Exception as e:
                                    logger.info(f"   {pattern}: Error - {e}")
                    break

        # 5. Check documents/index with filters
        logger.info("\n5. Testing documents/index variations...")
        doc_patterns = [
            "documents/index",
            "documents/index?limit=100",
        ]

        if case_ids:
            doc_patterns.extend([
                f"documents/index?case_file_id={case_ids[0]}",
                f"documents/index/{case_ids[0]}",
            ])

        for pattern in doc_patterns:
            try:
                resp = await client.get(f"{API_BASE}/{pattern}")
                data = resp.json()

                if resp.status_code == 200:
                    if isinstance(data, list):
                        logger.info(f"   {pattern}: {len(data)} items")
                        if data:
                            logger.info(f"      Keys: {list(data[0].keys()) if isinstance(data[0], dict) else 'N/A'}")
                    elif isinstance(data, dict):
                        logger.info(f"   {pattern}: dict with keys {list(data.keys())[:5]}")
            except Exception as e:
                logger.info(f"   {pattern}: Error - {e}")

        # 6. Check activities for document-related activities
        logger.info("\n6. Checking activities for document references...")
        if case_ids:
            resp = await client.get(f"{API_BASE}/activities/index/{case_ids[0]}?limit=50")
            if resp.status_code == 200:
                data = resp.json()
                activities = data if isinstance(data, list) else data.get("activities", [])

                for act in activities[:20]:
                    if isinstance(act, dict):
                        desc = str(act.get("description", "") or act.get("subject", ""))
                        if any(word in desc.lower() for word in ["document", "upload", "file", "pdf"]):
                            logger.info(f"   Activity: {desc[:80]}")
                            logger.info(f"      Keys: {list(act.keys())}")

        logger.info(f"\n{'='*70}")
        logger.info("EXPLORATION COMPLETE")
        logger.info(f"{'='*70}")


if __name__ == "__main__":
    asyncio.run(explore_uploads())
