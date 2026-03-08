"""
Test MerusAgent functionality

Quick test to verify MerusAgent works correctly.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import asyncio
import logging
from merus_agent import MerusAgent, CaseNotFoundError, BillingError

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


async def test_agent():
    """Test basic MerusAgent functionality"""
    print("\n" + "="*70)
    print("TESTING MERUSAGENT")
    print("="*70)

    try:
        async with MerusAgent() as agent:
            # Test 1: Find a case
            print("\n[1/5] Testing case search...")
            try:
                case = await agent.find_case("Smith")
                case_id = int(case["id"])
                case_name = case.get("primary_party_name", "Unknown")
                file_number = case.get("file_number", "N/A")
                print(f"✓ Found case: {case_name} ({file_number})")
            except CaseNotFoundError:
                print("✗ No case found named 'Smith' - trying to get first case...")
                cases = await agent.list_all_cases(limit=1)
                if cases:
                    case = cases[0]
                    case_id = int(case["id"])
                    case_name = case.get("primary_party_name", "Unknown")
                    file_number = case.get("file_number", "N/A")
                    print(f"✓ Using first case: {case_name} ({file_number})")
                else:
                    print("✗ No cases found in account")
                    return

            # Test 2: Get case details
            print("\n[2/5] Testing get case details...")
            try:
                details = await agent.get_case_details(case_id)
                print(f"✓ Retrieved case details ({len(details)} fields)")
            except Exception as e:
                print(f"✗ Failed: {e}")

            # Test 3: Get billing information
            print("\n[3/5] Testing get case billing...")
            try:
                billing = await agent.get_case_billing(case_id)
                entries = billing.get("data", {})
                print(f"✓ Retrieved {len(entries)} billing entries")
            except Exception as e:
                print(f"✗ Failed: {e}")

            # Test 4: Get activities
            print("\n[4/5] Testing get case activities...")
            try:
                activities = await agent.get_case_activities(case_id, limit=5)
                print(f"✓ Retrieved {len(activities)} activities")
            except Exception as e:
                print(f"✗ Failed: {e}")

            # Test 5: Get billing codes (cached)
            print("\n[5/5] Testing reference data (cached)...")
            try:
                codes = await agent.get_billing_codes()
                print(f"✓ Retrieved {len(codes)} billing codes (cached)")
            except Exception as e:
                print(f"✗ Failed: {e}")

            print("\n" + "="*70)
            print("BASIC TESTS COMPLETE")
            print("="*70)
            print("\nTo test billing operations (creates real entries):")
            print("  python test_merus_agent.py --write-test")

    except Exception as e:
        print(f"\n✗ FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()


async def test_agent_write_operations():
    """Test write operations (creates actual entries)"""
    print("\n" + "="*70)
    print("TESTING WRITE OPERATIONS (CREATES REAL ENTRIES)")
    print("="*70)
    print("\n⚠️  WARNING: This will create actual billing entries in MerusCase")
    response = input("Continue? (yes/no): ")

    if response.lower() != "yes":
        print("Aborted.")
        return

    try:
        async with MerusAgent() as agent:
            # Find a case to test with
            print("\n[1/3] Finding test case...")
            try:
                case = await agent.find_case("Smith")
                case_name = case.get("primary_party_name", "Unknown")
            except CaseNotFoundError:
                cases = await agent.list_all_cases(limit=1)
                if not cases:
                    print("✗ No cases found")
                    return
                case = cases[0]
                case_name = case.get("primary_party_name", "Unknown")

            print(f"✓ Using case: {case_name}")

            # Test bill time
            print("\n[2/3] Testing bill_time() - 0.1 hours...")
            try:
                result = await agent.bill_time(
                    case_search=case_name,
                    hours=0.1,
                    description="MerusAgent Test - Bill Time (DELETE ME)"
                )
                print(f"✓ Created activity ID: {result['activity_id']}")
            except Exception as e:
                print(f"✗ Failed: {e}")

            # Test add cost
            print("\n[3/3] Testing add_cost() - $5.00...")
            try:
                result = await agent.add_cost(
                    case_search=case_name,
                    amount=5.00,
                    description="MerusAgent Test - Add Cost (DELETE ME)"
                )
                print(f"✓ Created ledger entry ID: {result['ledger_id']}")
            except Exception as e:
                print(f"✗ Failed: {e}")

            print("\n" + "="*70)
            print("WRITE TESTS COMPLETE")
            print("="*70)
            print("\n⚠️  Remember to delete test entries from MerusCase!")

    except Exception as e:
        print(f"\n✗ FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    import sys

    if "--write-test" in sys.argv:
        asyncio.run(test_agent_write_operations())
    else:
        asyncio.run(test_agent())
