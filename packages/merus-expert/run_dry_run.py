#!/usr/bin/env python3
"""
Dry-Run Test - Create a matter without submitting
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from models.matter import MatterDetails, CaseType, BillingInfo
from automation.matter_builder import MatterBuilder
from security.config import SecurityConfig

async def run_dry_run():
    """Run dry-run matter creation test"""

    print("=" * 70)
    print("MERUSCASE MATTER CREATION - DRY-RUN TEST")
    print("=" * 70)
    print()

    # Define test matter
    matter = MatterDetails(
        primary_party="Jane Smith",
        case_type=CaseType.PERSONAL_INJURY,
        case_status="Open",
        attorney_responsible="Alex Thompson",
        office="San Francisco Office",
        jurisdiction="California Superior Court",
        billing_info=BillingInfo(
            amount_due=7500.00,
            description="Initial retainer for personal injury case - auto accident",
            amount_received=3500.00,
            check_number="CHK-001234",
            memo="50% upfront payment received"
        ),
        custom_fields={
            "accident_date": "2024-12-15",
            "accident_location": "Highway 101, San Francisco",
            "injury_type": "Whiplash and back injury",
            "insurance_company": "State Farm"
        }
    )

    print("Test Matter Details:")
    print(f"  Primary Party: {matter.primary_party}")
    print(f"  Case Type: {matter.case_type.value}")
    print(f"  Attorney: {matter.attorney_responsible}")
    print(f"  Office: {matter.office}")
    if matter.billing_info:
        print(f"  Amount Due: ${matter.billing_info.amount_due:,.2f}")
        print(f"  Amount Received: ${matter.billing_info.amount_received:,.2f}")
    print(f"  Custom Fields: {len(matter.custom_fields)} fields")
    print()

    print("=" * 70)
    print("Starting Matter Creation Workflow (DRY-RUN MODE)")
    print("=" * 70)
    print()

    try:
        # Load configuration
        config = SecurityConfig.from_env()

        # Create matter builder in dry-run mode
        async with MatterBuilder(config=config, dry_run=True) as builder:
            print("[INFO] Browser connected, starting workflow...")
            print()

            # Create matter
            result = await builder.create_matter(
                matter=matter,
                session_id="dry_run_test_20251226"
            )

            # Display results
            print()
            print("=" * 70)
            print("DRY-RUN RESULTS")
            print("=" * 70)
            print()
            print(f"Status: {result['status']}")
            print(f"Matter ID: {result['matter_id']}")
            print(f"Session ID: {result['session_id']}")
            print(f"Message: {result['message']}")
            print()

            if result.get('screenshot_path'):
                print(f"Screenshot: {result['screenshot_path']}")

            if result.get('filled_values'):
                print()
                print("Filled Form Values:")
                print("-" * 70)
                for field, value in result['filled_values'].items():
                    if value:  # Only show non-empty values
                        print(f"  {field}: {value}")

            print()
            print("=" * 70)
            print("DRY-RUN COMPLETED SUCCESSFULLY")
            print("=" * 70)
            print()
            print("Note: Form was filled but NOT submitted (dry-run mode)")
            print("Check the screenshot to verify field population.")
            print()

            return True

    except Exception as e:
        print()
        print("=" * 70)
        print("DRY-RUN FAILED")
        print("=" * 70)
        print(f"Error: {e}")
        print()
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(run_dry_run())
    sys.exit(0 if success else 1)
