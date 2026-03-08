"""
MerusAgent Usage Examples

Demonstrates how to use the MerusAgent for common operations.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import asyncio
import logging
from datetime import datetime
from merus_agent import MerusAgent, quick_bill_time, quick_add_cost

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def example_pull_operations():
    """Example: Pulling information from MerusCase"""
    print("\n" + "=" * 70)
    print("EXAMPLE: PULL OPERATIONS (READ)")
    print("=" * 70)

    async with MerusAgent() as agent:
        # 1. Find a case by name
        print("\n1. Finding case by party name...")
        try:
            case = await agent.find_case("Smith")
            print(f"   ✓ Found case: {case['id']} - {case.get('primary_party_name')}")
            print(f"     File number: {case.get('file_number')}")
            case_id = int(case['id'])
        except Exception as e:
            print(f"   ✗ Error: {e}")
            return

        # 2. Get case details
        print("\n2. Getting full case details...")
        try:
            details = await agent.get_case_details(case_id)
            print(f"   ✓ Retrieved {len(details)} detail fields")
        except Exception as e:
            print(f"   ✗ Error: {e}")

        # 3. Get billing information
        print("\n3. Getting billing/ledger entries...")
        try:
            billing = await agent.get_case_billing(case_id)
            entries = billing.get("data", {})
            print(f"   ✓ Found {len(entries)} billing entries")
        except Exception as e:
            print(f"   ✗ Error: {e}")

        # 4. Get activities
        print("\n4. Getting case activities...")
        try:
            activities = await agent.get_case_activities(case_id, limit=10)
            print(f"   ✓ Found {len(activities)} activities")
            if activities:
                latest = activities[0]
                print(f"     Latest: {latest.get('subject')}")
        except Exception as e:
            print(f"   ✗ Error: {e}")

        # 5. Get parties
        print("\n5. Getting case parties...")
        try:
            parties = await agent.get_case_parties(case_id)
            print(f"   ✓ Retrieved party information")
        except Exception as e:
            print(f"   ✗ Error: {e}")

        # 6. List all cases
        print("\n6. Listing all active cases...")
        try:
            cases = await agent.list_all_cases(case_status="Active", limit=5)
            print(f"   ✓ Found {len(cases)} active cases")
            for case in cases[:3]:
                print(f"     - {case['id']}: {case.get('primary_party_name')} ({case.get('file_number')})")
        except Exception as e:
            print(f"   ✗ Error: {e}")


async def example_push_operations():
    """Example: Pushing billing entries to MerusCase"""
    print("\n" + "=" * 70)
    print("EXAMPLE: PUSH OPERATIONS (CREATE)")
    print("=" * 70)

    async with MerusAgent() as agent:
        # 1. Bill time (natural language)
        print("\n1. Billing 0.2 hours (12 minutes) to Smith case...")
        try:
            result = await agent.bill_time(
                case_search="Smith",
                hours=0.2,
                description="Review medical records and QME report - API Test"
            )
            print(f"   ✓ Success!")
            print(f"     Activity ID: {result['activity_id']}")
            print(f"     Case ID: {result['case_id']}")
            print(f"     Case Name: {result['case_name']}")
            print(f"     Hours: {result['hours']} ({result['minutes']} minutes)")
        except Exception as e:
            print(f"   ✗ Error: {e}")

        # 2. Add a cost (filing fee)
        print("\n2. Adding $25 WCAB filing fee to Smith case...")
        try:
            result = await agent.add_cost(
                case_search="Smith",
                amount=25.00,
                description="WCAB Filing Fee - API Test",
                ledger_type="cost"
            )
            print(f"   ✓ Success!")
            print(f"     Ledger ID: {result['ledger_id']}")
            print(f"     Case ID: {result['case_id']}")
            print(f"     Amount: ${result['amount']:.2f}")
        except Exception as e:
            print(f"   ✗ Error: {e}")

        # 3. Add a non-billable note
        print("\n3. Adding non-billable note to Smith case...")
        try:
            result = await agent.add_note(
                case_search="Smith",
                subject="Client called - API Test",
                description="Discussed upcoming MSC hearing and settlement options"
            )
            print(f"   ✓ Success!")
            print(f"     Activity ID: {result['activity_id']}")
            print(f"     Case ID: {result['case_id']}")
        except Exception as e:
            print(f"   ✗ Error: {e}")


async def example_batch_operations():
    """Example: Batch billing multiple cases"""
    print("\n" + "=" * 70)
    print("EXAMPLE: BATCH OPERATIONS")
    print("=" * 70)

    async with MerusAgent() as agent:
        # Batch bill time to multiple cases
        print("\n1. Batch billing time to multiple cases...")

        entries = [
            {
                "case_search": "Smith",
                "hours": 0.1,
                "description": "Quick phone call - API Test"
            },
            {
                "case_search": "Smith",
                "hours": 0.3,
                "description": "Draft demand letter - API Test"
            },
        ]

        try:
            results = await agent.bulk_bill_time(entries)
            successful = sum(1 for r in results if r.get("success"))
            print(f"   ✓ Completed: {successful}/{len(entries)} succeeded")

            for i, result in enumerate(results):
                if result.get("success"):
                    print(f"     [{i+1}] Success: {result['description'][:40]}...")
                else:
                    print(f"     [{i+1}] Failed: {result.get('error')}")
        except Exception as e:
            print(f"   ✗ Error: {e}")


async def example_reference_data():
    """Example: Accessing cached reference data"""
    print("\n" + "=" * 70)
    print("EXAMPLE: REFERENCE DATA (CACHED)")
    print("=" * 70)

    async with MerusAgent() as agent:
        # Get billing codes (cached for 1 hour)
        print("\n1. Getting billing codes (cached)...")
        try:
            codes = await agent.get_billing_codes()
            print(f"   ✓ Found {len(codes)} billing codes")
            for code_id, code in list(codes.items())[:3]:
                name = code.get("name", code.get("code", "N/A"))
                print(f"     - {code_id}: {name}")
        except Exception as e:
            print(f"   ✗ Error: {e}")

        # Get activity types (cached for 1 hour)
        print("\n2. Getting activity types (cached)...")
        try:
            types = await agent.get_activity_types()
            print(f"   ✓ Found {len(types)} activity types")
            for type_id, type_data in list(types.items())[:3]:
                name = type_data.get("name", "N/A")
                print(f"     - {type_id}: {name}")
        except Exception as e:
            print(f"   ✗ Error: {e}")


async def example_billing_summary():
    """Example: Get billing summary for a case"""
    print("\n" + "=" * 70)
    print("EXAMPLE: BILLING SUMMARY")
    print("=" * 70)

    async with MerusAgent() as agent:
        print("\n1. Getting billing summary for Smith case...")
        try:
            summary = await agent.get_billing_summary("Smith")
            print(f"   ✓ Success!")
            print(f"     Case: {summary['case_name']} ({summary['case_id']})")
            print(f"     Total Amount: ${summary['total_amount']:.2f}")
            print(f"     Total Entries: {summary['total_entries']}")

            # Show last 3 entries
            entries = list(summary['entries'].values())
            if entries:
                print(f"\n     Recent entries:")
                for entry in entries[:3]:
                    date = entry.get('date', 'N/A')
                    amount = entry.get('amount', 0)
                    desc = entry.get('description', 'N/A')[:40]
                    print(f"     - {date}: ${amount} - {desc}")
        except Exception as e:
            print(f"   ✗ Error: {e}")


async def example_quick_functions():
    """Example: Using convenience functions"""
    print("\n" + "=" * 70)
    print("EXAMPLE: QUICK CONVENIENCE FUNCTIONS")
    print("=" * 70)

    # Bill time without instantiating agent
    print("\n1. Using quick_bill_time()...")
    try:
        result = await quick_bill_time(
            case_search="Smith",
            hours=0.1,
            description="Quick call with client - API Test"
        )
        print(f"   ✓ Success! Activity ID: {result['activity_id']}")
    except Exception as e:
        print(f"   ✗ Error: {e}")

    # Add cost without instantiating agent
    print("\n2. Using quick_add_cost()...")
    try:
        result = await quick_add_cost(
            case_search="Smith",
            amount=10.00,
            description="Copy fees - API Test"
        )
        print(f"   ✓ Success! Ledger ID: {result['ledger_id']}")
    except Exception as e:
        print(f"   ✗ Error: {e}")


async def example_error_handling():
    """Example: Error handling"""
    print("\n" + "=" * 70)
    print("EXAMPLE: ERROR HANDLING")
    print("=" * 70)

    async with MerusAgent() as agent:
        # 1. Case not found
        print("\n1. Trying to find non-existent case...")
        try:
            case = await agent.find_case("NonExistentCase12345")
            print(f"   Found: {case}")
        except Exception as e:
            print(f"   ✓ Expected error caught: {type(e).__name__}")
            print(f"     Message: {e}")

        # 2. Invalid hours
        print("\n2. Trying to bill negative hours...")
        try:
            result = await agent.bill_time(
                case_search="Smith",
                hours=-0.5,  # Invalid
                description="Invalid time entry"
            )
        except Exception as e:
            print(f"   ✓ Expected error caught: {type(e).__name__}")


async def main():
    """Run all examples"""
    print("\n" + "=" * 70)
    print("MERUSAGENT - COMPREHENSIVE EXAMPLES")
    print("=" * 70)
    print("\nThis script demonstrates all major features of MerusAgent:")
    print("- Pull operations (READ)")
    print("- Push operations (CREATE)")
    print("- Batch operations")
    print("- Reference data caching")
    print("- Billing summaries")
    print("- Convenience functions")
    print("- Error handling")

    # Run examples
    await example_pull_operations()
    await example_push_operations()
    await example_batch_operations()
    await example_reference_data()
    await example_billing_summary()
    await example_quick_functions()
    await example_error_handling()

    print("\n" + "=" * 70)
    print("ALL EXAMPLES COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
