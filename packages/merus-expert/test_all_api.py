"""
Test all MerusCase API endpoints with the working token.
"""

import asyncio
import logging
from pathlib import Path
import httpx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_BASE = "https://api.meruscase.com"

# Load token
TOKEN = Path(".meruscase_token").read_text().strip()


async def test_all():
    """Test all known endpoints."""

    endpoints = [
        # Case Files
        ("GET", "caseFiles/index?limit=5", "List cases"),
        ("GET", "caseTypes/index", "List case types"),

        # Activities
        ("GET", "activityTypes/index", "List activity types"),

        # Billing
        ("GET", "billingCodes/index", "List billing codes"),
        ("GET", "caseLedgersOpen/index", "Open ledgers"),

        # Parties
        ("GET", "partyGroups/index", "Party groups"),

        # Tasks & Events
        ("GET", "tasks/index?limit=5", "List tasks"),
        ("GET", "events/index?limit=5", "List events"),
        ("GET", "eventTypes/index", "Event types"),

        # Reference data
        ("GET", "statutes/index", "Statutes"),
        ("GET", "paymentMethods/index", "Payment methods"),

        # Users (may require admin)
        ("GET", "users/index", "Firm users"),

        # Receivables
        ("GET", "receivables/index?limit=5", "Receivables"),
    ]

    logger.info(f"\n{'='*70}")
    logger.info("MERUSCASE API ENDPOINT TEST")
    logger.info(f"{'='*70}")
    logger.info(f"Token: {TOKEN[:20]}...")
    logger.info("")

    results = {"working": [], "failed": []}

    async with httpx.AsyncClient(
        headers={"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"},
        timeout=30.0
    ) as client:

        for method, endpoint, description in endpoints:
            try:
                resp = await client.get(f"{API_BASE}/{endpoint}")
                data = resp.json()

                has_error = "errors" in data and data.get("errors")

                if resp.status_code == 200 and not has_error:
                    count = len(data) if isinstance(data, list) else "dict"
                    logger.info(f"  ✓ {endpoint}: {count} items")
                    results["working"].append((endpoint, description, count))

                    # Show sample
                    if isinstance(data, list) and len(data) > 0:
                        sample = data[0]
                        if isinstance(sample, dict):
                            keys = list(sample.keys())[:5]
                            logger.info(f"      Keys: {keys}")
                else:
                    error = data.get("errors", resp.status_code)
                    logger.info(f"  ✗ {endpoint}: {error}")
                    results["failed"].append((endpoint, description, error))

            except Exception as e:
                logger.info(f"  ✗ {endpoint}: {e}")
                results["failed"].append((endpoint, description, str(e)))

    # Summary
    logger.info(f"\n{'='*70}")
    logger.info("SUMMARY")
    logger.info(f"{'='*70}")
    logger.info(f"\n  Working: {len(results['working'])}/{len(endpoints)}")
    logger.info(f"  Failed:  {len(results['failed'])}/{len(endpoints)}")

    if results["working"]:
        logger.info("\n  WORKING ENDPOINTS:")
        for ep, desc, count in results["working"]:
            logger.info(f"    • {desc}: {ep}")

    if results["failed"]:
        logger.info("\n  FAILED ENDPOINTS:")
        for ep, desc, err in results["failed"]:
            logger.info(f"    • {desc}: {err}")

    return results


if __name__ == "__main__":
    asyncio.run(test_all())
