"""
Test billing entry API endpoints.
"""

import asyncio
import logging
import json
from pathlib import Path
from datetime import datetime
import httpx

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

API_BASE = "https://api.meruscase.com"
TOKEN = Path(".meruscase_token").read_text().strip()


async def test_billing_endpoints():
    """Test billing/ledger creation endpoints."""

    logger.info("=" * 70)
    logger.info("TESTING BILLING ENTRY API ACCESS")
    logger.info("=" * 70)

    async with httpx.AsyncClient(
        headers={"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"},
        timeout=30.0
    ) as client:

        # First, get a valid case_file_id to test with
        logger.info("\n1. Getting a case to test with...")
        resp = await client.get(f"{API_BASE}/caseFiles/index?limit=1")
        cases_data = resp.json()

        case_id = None
        if "data" in cases_data and cases_data["data"]:
            case_id = list(cases_data["data"].keys())[0]
            case_info = cases_data["data"][case_id]
            logger.info(f"   Using case: {case_id} - {case_info.get('file_number', 'N/A')}")
        else:
            logger.info("   No cases found!")
            return

        # Get billing codes
        logger.info("\n2. Getting billing codes...")
        resp = await client.get(f"{API_BASE}/billingCodes/index")
        billing_codes = resp.json()

        billing_code_id = None
        if "data" in billing_codes and billing_codes["data"]:
            billing_code_id = list(billing_codes["data"].keys())[0]
            code_info = billing_codes["data"][billing_code_id]
            logger.info(f"   Using billing code: {billing_code_id} - {code_info.get('name', code_info.get('code', 'N/A'))}")

        # Get activity types
        logger.info("\n3. Getting activity types...")
        resp = await client.get(f"{API_BASE}/activityTypes/index")
        activity_types = resp.json()

        activity_type_id = None
        if "data" in activity_types and activity_types["data"]:
            activity_type_id = list(activity_types["data"].keys())[0]
            type_info = activity_types["data"][activity_type_id]
            logger.info(f"   Using activity type: {activity_type_id} - {type_info.get('name', 'N/A')}")

        # =====================================================
        # TEST POST ENDPOINTS FOR BILLING
        # =====================================================

        logger.info("\n" + "=" * 70)
        logger.info("TESTING POST ENDPOINTS")
        logger.info("=" * 70)

        # Test 1: POST /activities/add (documented)
        logger.info("\n4. Testing POST /activities/add...")

        activity_data = {
            "case_file_id": case_id,
            "subject": "API Test - Delete Me",
            "description": "Testing API billing entry creation",
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "duration": 6,  # 0.1 hours = 6 minutes
            "billable": 1,
        }

        if activity_type_id:
            activity_data["activity_type_id"] = activity_type_id
        if billing_code_id:
            activity_data["billing_code_id"] = billing_code_id

        logger.info(f"   Payload: {json.dumps(activity_data, indent=2)}")

        resp = await client.post(
            f"{API_BASE}/activities/add",
            json=activity_data
        )

        logger.info(f"   Status: {resp.status_code}")
        logger.info(f"   Response: {json.dumps(resp.json(), indent=2)[:500]}")

        # Test 2: POST /caseLedgers/add (undocumented - test if exists)
        logger.info("\n5. Testing POST /caseLedgers/add...")

        ledger_data = {
            "case_file_id": case_id,
            "amount": "25.00",
            "description": "API Test - Delete Me",
            "date": datetime.now().strftime("%Y-%m-%d"),
            "type": "fee",
        }

        if billing_code_id:
            ledger_data["billing_code_id"] = billing_code_id

        logger.info(f"   Payload: {json.dumps(ledger_data, indent=2)}")

        resp = await client.post(
            f"{API_BASE}/caseLedgers/add",
            json=ledger_data
        )

        logger.info(f"   Status: {resp.status_code}")
        try:
            logger.info(f"   Response: {json.dumps(resp.json(), indent=2)[:500]}")
        except:
            logger.info(f"   Response: {resp.text[:500]}")

        # Test 3: POST /caseLedgersOpen/add (alternative)
        logger.info("\n6. Testing POST /caseLedgersOpen/add...")

        resp = await client.post(
            f"{API_BASE}/caseLedgersOpen/add",
            json=ledger_data
        )

        logger.info(f"   Status: {resp.status_code}")
        try:
            logger.info(f"   Response: {json.dumps(resp.json(), indent=2)[:500]}")
        except:
            logger.info(f"   Response: {resp.text[:500]}")

        # Test 4: Check what fields activities/add requires
        logger.info("\n7. Testing activities/add with minimal payload...")

        minimal_data = {
            "case_file_id": case_id,
            "subject": "Minimal Test",
        }

        resp = await client.post(
            f"{API_BASE}/activities/add",
            json=minimal_data
        )

        logger.info(f"   Status: {resp.status_code}")
        logger.info(f"   Response: {json.dumps(resp.json(), indent=2)[:500]}")

        # Test 5: Try form-encoded instead of JSON
        logger.info("\n8. Testing activities/add with form encoding...")

        resp = await client.post(
            f"{API_BASE}/activities/add",
            data=activity_data,  # form-encoded
            headers={
                "Authorization": f"Bearer {TOKEN}",
                "Content-Type": "application/x-www-form-urlencoded"
            }
        )

        logger.info(f"   Status: {resp.status_code}")
        try:
            logger.info(f"   Response: {json.dumps(resp.json(), indent=2)[:500]}")
        except:
            logger.info(f"   Response: {resp.text[:500]}")

        logger.info("\n" + "=" * 70)
        logger.info("BILLING API TEST COMPLETE")
        logger.info("=" * 70)


if __name__ == "__main__":
    asyncio.run(test_billing_endpoints())
