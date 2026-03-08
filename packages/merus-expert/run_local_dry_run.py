#!/usr/bin/env python3
"""
Full dry-run matter creation using local browser (no Browserless required)
"""

import asyncio
import sys
import uuid
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Load .env file
from dotenv import load_dotenv
load_dotenv(project_root / ".env")

from browser.local_client import LocalBrowserClient
from automation.form_filler import FormFiller
from models.matter import MatterDetails, CaseType, BillingInfo
from security.config import SecurityConfig
from persistence.session_store import SessionStore
from persistence.matter_store import MatterStore
from security.audit import AuditLogger

async def run_local_dry_run():
    """Run full matter creation workflow with local browser"""

    print("=" * 70)
    print("MERUSCASE MATTER CREATION - LOCAL BROWSER DRY-RUN")
    print("=" * 70)
    print()

    # Load configuration
    config = SecurityConfig.from_env()

    # Initialize persistence
    session_store = SessionStore(config.db_path)
    matter_store = MatterStore(config.db_path)
    audit_logger = AuditLogger(config.db_path)

    # Generate session ID
    session_id = f"local_dry_run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # Define test matter
    matter = MatterDetails(
        primary_party="Test Client - Dry Run",
        case_type=CaseType.PERSONAL_INJURY,
        case_status="Open",
        attorney_responsible="Alex Thompson",
        office="San Francisco Office",
        jurisdiction="California Superior Court",
        billing_info=BillingInfo(
            amount_due=5000.00,
            description="Initial retainer for personal injury case",
            amount_received=2500.00,
            check_number="CHK-TEST-001",
            memo="Dry run test payment"
        )
    )

    print(f"Session ID: {session_id}")
    print()
    print("Matter Details:")
    print(f"  Primary Party: {matter.primary_party}")
    print(f"  Case Type: {matter.case_type.value if matter.case_type else 'None'}")
    print(f"  Attorney: {matter.attorney_responsible}")
    print(f"  Office: {matter.office}")
    if matter.billing_info:
        print(f"  Amount Due: ${matter.billing_info.amount_due:,.2f}")
    print()

    # Create screenshots directory
    screenshots_dir = project_root / "screenshots" / session_id
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Create session
        session_store.create_session(session_id)
        print("[OK] Session created")

        # Create matter record (use snake_case enum name, not display value)
        matter_type_map = {
            CaseType.PERSONAL_INJURY: "personal_injury",
            CaseType.IMMIGRATION: "immigration",
            CaseType.WORKERS_COMP: "workers_comp",
            CaseType.FAMILY_LAW: "family_law",
            CaseType.GENERAL: "general"
        }
        matter_type = matter_type_map.get(matter.case_type, "general")

        matter_id = matter_store.create_matter(
            session_id=session_id,
            matter_type=matter_type,
            primary_party=matter.primary_party,
            dry_run=True
        )
        print(f"[OK] Matter record created: ID={matter_id}")
        print()

        # Start browser
        print("=" * 70)
        print("WORKFLOW: Starting browser automation")
        print("=" * 70)
        print()

        async with LocalBrowserClient(headless=False) as browser:
            print("[OK] Local browser started")
            page = browser.page

            # STEP 1: Login
            print()
            print("[STEP 1] LOGIN")
            print("-" * 40)

            await browser.navigate(config.meruscase_login_url)
            await browser.screenshot(str(screenshots_dir / "01_login_page.png"))

            # Fill login form
            await page.locator('#email').fill(config.meruscase_email)
            await page.locator('input[type="password"]').fill(config.meruscase_password)
            await page.locator('button[type="submit"]').click()
            await page.wait_for_load_state('networkidle', timeout=15000)

            await browser.screenshot(str(screenshots_dir / "02_post_login.png"))
            print(f"[OK] Logged in - URL: {page.url}")

            # STEP 2: Navigate to new matter form
            print()
            print("[STEP 2] NAVIGATE TO NEW MATTER")
            print("-" * 40)

            # MerusCase new matter URL
            new_matter_url = f"{config.meruscase_base_url}/cms#/cases/new"
            await browser.navigate(new_matter_url)
            await asyncio.sleep(2)  # Wait for SPA to load
            await browser.screenshot(str(screenshots_dir / "03_new_matter_form.png"))
            print(f"[OK] Navigated to new matter form")

            # STEP 3: Fill form
            print()
            print("[STEP 3] FILL FORM (DRY-RUN)")
            print("-" * 40)

            # Initialize form filler
            form_filler = FormFiller(page)

            # Fill primary party
            print("  Filling primary party...")
            try:
                # Try different selectors for primary party field
                primary_selectors = [
                    'input[name="primary_party"]',
                    'input[name="client_name"]',
                    'input[placeholder*="client" i]',
                    'input[placeholder*="party" i]',
                    'input[placeholder*="name" i]',
                    '#primary_party',
                    '#client_name'
                ]

                primary_field = None
                for selector in primary_selectors:
                    try:
                        field = page.locator(selector).first
                        if await field.is_visible(timeout=1000):
                            primary_field = field
                            print(f"    Found: {selector}")
                            break
                    except:
                        continue

                if primary_field:
                    await primary_field.fill(matter.primary_party)
                    print(f"  [OK] Primary party filled: {matter.primary_party}")
                else:
                    print("  [WARN] Primary party field not found")

            except Exception as e:
                print(f"  [WARN] Could not fill primary party: {e}")

            # Fill case type dropdown
            print("  Filling case type...")
            try:
                case_type_selectors = [
                    'select[name="case_type"]',
                    'select[name="matter_type"]',
                    '#case_type',
                    '#matter_type'
                ]

                for selector in case_type_selectors:
                    try:
                        dropdown = page.locator(selector).first
                        if await dropdown.is_visible(timeout=1000):
                            await dropdown.select_option(label=matter.case_type.value)
                            print(f"  [OK] Case type selected: {matter.case_type.value}")
                            break
                    except:
                        continue
            except Exception as e:
                print(f"  [WARN] Could not fill case type: {e}")

            # Take screenshot of filled form
            await asyncio.sleep(1)
            await browser.screenshot(str(screenshots_dir / "04_form_filled.png"), full_page=True)
            print()
            print("[OK] Form filling complete (dry-run - no submission)")

            # STEP 4: Extract form values
            print()
            print("[STEP 4] EXTRACT FILLED VALUES")
            print("-" * 40)

            # Extract all form values using JavaScript
            filled_values = await page.evaluate("""
                () => {
                    const values = {};
                    const inputs = document.querySelectorAll('input, select, textarea');
                    inputs.forEach(input => {
                        if (input.name || input.id) {
                            const key = input.name || input.id;
                            if (input.type === 'checkbox' || input.type === 'radio') {
                                values[key] = input.checked;
                            } else {
                                values[key] = input.value;
                            }
                        }
                    });
                    return values;
                }
            """)

            print("Extracted values:")
            for key, value in filled_values.items():
                if value:  # Only show non-empty
                    print(f"  {key}: {value}")

            # Final screenshot
            await browser.screenshot(str(screenshots_dir / "05_dry_run_complete.png"), full_page=True)

            # Keep browser open briefly to see result
            print()
            print("[INFO] Keeping browser open for 5 seconds...")
            await asyncio.sleep(5)

        # Update matter status
        matter_store.update_status(matter_id, "success")
        session_store.end_session(session_id, "completed")

        # Log audit event
        audit_logger.log_matter_operation(
            session_id=session_id,
            event_type="dry_run_completed",
            action="preview",
            status="SUCCESS",
            resource=f"matter_{matter_id}"
        )

        print()
        print("=" * 70)
        print("DRY-RUN COMPLETED SUCCESSFULLY")
        print("=" * 70)
        print()
        print(f"Matter ID: {matter_id}")
        print(f"Session ID: {session_id}")
        print(f"Screenshots: {screenshots_dir}")
        print()
        print("Note: Form was filled but NOT submitted (dry-run mode)")
        print()

        return True

    except Exception as e:
        print()
        print("=" * 70)
        print("DRY-RUN FAILED")
        print("=" * 70)
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

        # Update status on failure
        try:
            if matter_id:
                matter_store.update_status(matter_id, "failed", str(e))
            session_store.end_session(session_id, f"failed: {e}")
        except:
            pass

        return False


if __name__ == "__main__":
    success = asyncio.run(run_local_dry_run())
    sys.exit(0 if success else 1)
