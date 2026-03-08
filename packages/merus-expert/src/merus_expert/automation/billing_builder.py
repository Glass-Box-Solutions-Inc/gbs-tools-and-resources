"""
Billing Builder - Main orchestrator for time entry creation workflow
"""

import logging
from typing import Optional, Dict, Any
from pathlib import Path
from datetime import datetime
import asyncio

from merus_expert.browser.client import MerusCaseBrowserClient
from merus_expert.browser.element_handler import ElementHandler
from merus_expert.browser.matter_finder import MatterFinder
from merus_expert.automation.billing_form_filler import BillingFormFiller
from knowledge.screenshot_store import ScreenshotManager
from merus_expert.persistence.session_store import SessionStore
from merus_expert.security.audit import AuditLogger
from merus_expert.security.config import SecurityConfig
from merus_expert.models.billing import (
    TimeEntry,
    TimeEntryResult,
    MatterReference,
    MatterSelectionMethod,
)

logger = logging.getLogger(__name__)


class BillingBuilder:
    """
    Orchestrates the complete time entry creation workflow.

    Workflow steps:
    1. LOGIN - Authenticate with MerusCase
    2. RESOLVE_MATTER - Find and navigate to matter
    3. NAVIGATE_TO_BILLING - Find billing section
    4. OPEN_ENTRY_FORM - Click add entry button
    5. FILL_FORM - Fill time entry fields
    6. SUBMIT/PREVIEW - Submit or dry-run
    7. VERIFY - Confirm entry created
    """

    # Common selectors for billing navigation
    BILLING_NAV_SELECTORS = [
        "a[href*='billing']",
        "a[href*='time']",
        "a[href*='fees']",
        "li:has-text('Billing')",
        "li:has-text('Time')",
        "[data-tab='billing']",
        "[data-tab='time']",
        "button:has-text('Billing')",
        ".tab:has-text('Billing')",
        ".nav-item:has-text('Billing')",
        ".sidebar a:has-text('Time')",
    ]

    ADD_ENTRY_SELECTORS = [
        "button:has-text('Add Time')",
        "button:has-text('New Entry')",
        "button:has-text('Add Entry')",
        "button:has-text('New Time')",
        "a:has-text('Add Time')",
        "a:has-text('New Entry')",
        "[data-action='add-time']",
        ".add-time-btn",
        "button:has-text('+')",
        ".btn-add-entry",
    ]

    def __init__(
        self,
        config: Optional[SecurityConfig] = None,
        dry_run: bool = True
    ):
        """
        Initialize billing builder.

        Args:
            config: Security configuration
            dry_run: If True, preview only without submitting
        """
        self.config = config or SecurityConfig.from_env()
        self.dry_run = dry_run

        # Initialize components
        self.session_store = SessionStore(self.config.db_path)
        self.audit_logger = AuditLogger(self.config.db_path)
        self.screenshot_manager = ScreenshotManager(
            self.config.db_path,
            retention_hours=self.config.screenshot_retention_hr
        )

        # Browser components (initialized on connect)
        self.browser_client: Optional[MerusCaseBrowserClient] = None
        self.element_handler: Optional[ElementHandler] = None
        self.matter_finder: Optional[MatterFinder] = None
        self.form_filler: Optional[BillingFormFiller] = None

        self.current_session_id: Optional[str] = None

    async def __aenter__(self):
        """Async context manager entry"""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.disconnect()

    async def connect(self):
        """Establish browser connection"""
        logger.info("Connecting to Browserless for billing...")

        self.browser_client = MerusCaseBrowserClient(
            api_token=self.config.browserless_api_token,
            endpoint=self.config.browserless_endpoint
        )

        await self.browser_client.connect()

        # Initialize page-dependent components
        self.element_handler = ElementHandler(self.browser_client.page)
        self.matter_finder = MatterFinder(
            self.browser_client.page,
            self.config.meruscase_base_url
        )

        # Load discoveries if available
        discoveries_path = Path(self.config.db_path).parent / "billing_discoveries.json"
        self.form_filler = BillingFormFiller(
            self.browser_client.page,
            str(discoveries_path) if discoveries_path.exists() else None
        )

        logger.info("Billing browser connected")

    async def disconnect(self):
        """Close browser connection"""
        if self.browser_client:
            await self.browser_client.disconnect()
            logger.info("Billing browser disconnected")

    async def login(self, session_id: str) -> bool:
        """
        Login to MerusCase.

        Args:
            session_id: Session identifier

        Returns:
            True if login successful
        """
        try:
            logger.info("Logging into MerusCase...")

            # Navigate to login page
            await self.browser_client.navigate(self.config.meruscase_login_url)
            await asyncio.sleep(2)

            # Screenshot: Login page
            await self.screenshot_manager.capture_screenshot(
                self.browser_client.page,
                session_id,
                "billing_login",
                "Login page for billing"
            )

            # Find and fill email
            email_input = await self.element_handler.find_input(
                field_name="email",
                label="Email",
                placeholder="Email"
            )
            if not email_input:
                logger.error("Could not find email field")
                return False

            password_input = await self.element_handler.find_input(
                field_name="password",
                label="Password",
                placeholder="Password"
            )
            if not password_input:
                logger.error("Could not find password field")
                return False

            await email_input.fill(self.config.meruscase_email)
            await password_input.fill(self.config.meruscase_password)

            # Click login
            login_button = await self.element_handler.find_button(
                text="Sign In",
                css_selector="button[type='submit'], input[type='submit']"
            )
            if not login_button:
                logger.error("Could not find login button")
                return False

            await login_button.click()
            await self.browser_client.page.wait_for_load_state("networkidle", timeout=30000)
            await asyncio.sleep(2)

            # Verify login
            is_logged_in = await self.browser_client.page.locator(
                "[href*='logout'], [href*='sign-out'], .user-menu, .profile"
            ).is_visible()

            if is_logged_in:
                logger.info("Login successful")
                self.audit_logger.log_event(
                    session_id=session_id,
                    category="AUTHENTICATION",
                    action="LOGIN",
                    details={"success": True, "workflow": "billing"}
                )
                return True

            logger.warning("Login verification uncertain, continuing...")
            return True

        except Exception as e:
            logger.error(f"Login failed: {e}")
            return False

    async def navigate_to_billing_section(self, session_id: str) -> bool:
        """
        Navigate to billing/time entry section within current matter.

        Args:
            session_id: Session identifier

        Returns:
            True if navigation successful
        """
        logger.info("Navigating to billing section...")

        for selector in self.BILLING_NAV_SELECTORS:
            try:
                element = self.browser_client.page.locator(selector).first
                if await element.is_visible():
                    logger.info(f"Found billing nav: {selector}")
                    await element.click()
                    await asyncio.sleep(2)

                    # Screenshot: Billing section
                    await self.screenshot_manager.capture_screenshot(
                        self.browser_client.page,
                        session_id,
                        "billing_section",
                        "Billing section loaded"
                    )

                    return True
            except Exception:
                continue

        # Try URL-based navigation
        current_url = self.browser_client.page.url
        if "/matters/" in current_url or "/cases/" in current_url:
            billing_url = current_url.rstrip("/") + "/billing"
            try:
                await self.browser_client.navigate(billing_url)
                await asyncio.sleep(2)
                return True
            except Exception:
                pass

        logger.warning("Could not find billing section")
        return False

    async def open_entry_form(self, session_id: str) -> bool:
        """
        Open new time entry form.

        Args:
            session_id: Session identifier

        Returns:
            True if form opened
        """
        logger.info("Opening time entry form...")

        for selector in self.ADD_ENTRY_SELECTORS:
            try:
                element = self.browser_client.page.locator(selector).first
                if await element.is_visible():
                    logger.info(f"Found add entry button: {selector}")
                    await element.click()
                    await asyncio.sleep(2)

                    # Screenshot: Entry form
                    await self.screenshot_manager.capture_screenshot(
                        self.browser_client.page,
                        session_id,
                        "entry_form",
                        "Time entry form opened"
                    )

                    return True
            except Exception:
                continue

        logger.warning("Could not find add entry button")
        return False

    async def submit_entry(self, session_id: str) -> bool:
        """
        Submit the time entry form.

        Args:
            session_id: Session identifier

        Returns:
            True if submission successful
        """
        if self.dry_run:
            logger.info("DRY-RUN: Skipping actual submission")
            return True

        logger.info("Submitting time entry...")

        if not await self.form_filler.click_save():
            logger.error("Could not click save button")
            return False

        # Wait for submission
        await self.browser_client.page.wait_for_load_state("networkidle", timeout=30000)
        await asyncio.sleep(2)

        # Screenshot: After submission
        await self.screenshot_manager.capture_screenshot(
            self.browser_client.page,
            session_id,
            "entry_submitted",
            "Time entry submitted"
        )

        logger.info("Time entry submitted")
        return True

    async def create_time_entry(
        self,
        matter_ref: MatterReference,
        entry: TimeEntry,
        session_id: Optional[str] = None
    ) -> TimeEntryResult:
        """
        Create a time entry in MerusCase.

        Complete workflow:
        1. Login
        2. Resolve and navigate to matter
        3. Navigate to billing section
        4. Open entry form
        5. Fill form
        6. Submit (or preview in dry-run)

        Args:
            matter_ref: Reference to the matter
            entry: TimeEntry data
            session_id: Optional session identifier

        Returns:
            TimeEntryResult with status and details
        """
        if not session_id:
            session_id = f"billing_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        self.current_session_id = session_id

        result = TimeEntryResult(
            session_id=session_id,
            status="pending",
            message="Starting time entry creation",
            dry_run=self.dry_run,
        )

        try:
            # Log start
            self.audit_logger.log_event(
                session_id=session_id,
                category="BILLING_OPERATIONS",
                action="CREATE_ENTRY_START",
                details={
                    "matter_method": matter_ref.method.value,
                    "hours": entry.hours,
                    "dry_run": self.dry_run,
                }
            )

            # Step 1: Login
            result.message = "Logging in..."
            if not await self.login(session_id):
                result.status = "failed"
                result.error = "Login failed"
                result.message = "Failed to login to MerusCase"
                return result

            # Step 2: Resolve matter
            result.message = "Resolving matter..."
            resolved = await self.matter_finder.resolve_matter(matter_ref)
            if not resolved:
                result.status = "failed"
                result.error = "Matter not found"
                result.message = f"Could not find matter: {matter_ref.value}"
                return result

            result.matter_id = resolved.resolved_id
            result.matter_name = resolved.resolved_name
            result.meruscase_url = resolved.meruscase_url

            # Step 3: Navigate to matter
            result.message = "Navigating to matter..."
            if not await self.matter_finder.navigate_to_matter(resolved):
                result.status = "failed"
                result.error = "Navigation failed"
                result.message = "Could not navigate to matter"
                return result

            # Screenshot: Matter page
            await self.screenshot_manager.capture_screenshot(
                self.browser_client.page,
                session_id,
                "matter_page",
                f"Matter: {resolved.resolved_name}"
            )

            # Step 4: Navigate to billing section
            result.message = "Navigating to billing..."
            if not await self.navigate_to_billing_section(session_id):
                # Try continuing anyway - some systems have inline entry
                logger.warning("Billing section not found, trying inline entry")

            # Step 5: Open entry form
            result.message = "Opening entry form..."
            if not await self.open_entry_form(session_id):
                # Try continuing - form might already be visible
                logger.warning("Add entry button not found, form may be inline")

            # Step 6: Fill form
            result.message = "Filling time entry..."
            if not await self.form_filler.fill_complete_entry(entry):
                result.status = "failed"
                result.error = "Form fill failed"
                result.message = "Could not fill time entry form"
                return result

            # Screenshot: Filled form
            screenshot_path = await self.screenshot_manager.capture_screenshot(
                self.browser_client.page,
                session_id,
                "entry_filled",
                "Time entry form filled"
            )
            result.screenshot_path = screenshot_path

            # Step 7: Submit or preview
            if self.dry_run:
                result.message = "Dry-run complete - form filled but not submitted"
                result.status = "dry_run_success"

                # Extract filled values
                filled_values = await self.form_filler.extract_filled_values()
                result.metadata["filled_values"] = filled_values

            else:
                result.message = "Submitting entry..."
                if not await self.submit_entry(session_id):
                    result.status = "failed"
                    result.error = "Submission failed"
                    result.message = "Could not submit time entry"
                    return result

                result.status = "success"
                result.message = "Time entry created successfully"

            # Log completion
            self.audit_logger.log_event(
                session_id=session_id,
                category="BILLING_OPERATIONS",
                action="CREATE_ENTRY_COMPLETE",
                details={
                    "matter_id": result.matter_id,
                    "hours": entry.hours,
                    "status": result.status,
                    "dry_run": self.dry_run,
                }
            )

            return result

        except Exception as e:
            logger.error(f"Time entry creation failed: {e}")
            result.status = "failed"
            result.error = str(e)
            result.message = f"Error: {str(e)}"

            self.audit_logger.log_event(
                session_id=session_id,
                category="BILLING_OPERATIONS",
                action="CREATE_ENTRY_ERROR",
                details={"error": str(e)}
            )

            return result

    async def quick_entry(
        self,
        matter_url: str,
        hours: float,
        description: str,
        category: str = "Other",
        session_id: Optional[str] = None
    ) -> TimeEntryResult:
        """
        Quick entry helper - simplified interface.

        Args:
            matter_url: MerusCase matter URL
            hours: Hours to bill
            description: Work description
            category: Billing category name
            session_id: Optional session ID

        Returns:
            TimeEntryResult
        """
        from merus_expert.models.billing import BillingCategory

        # Create matter reference
        matter_ref = MatterReference(
            method=MatterSelectionMethod.URL,
            value=matter_url
        )

        # Parse category
        try:
            billing_category = BillingCategory(category)
        except ValueError:
            billing_category = BillingCategory.OTHER

        # Create entry
        entry = TimeEntry(
            hours=hours,
            description=description,
            category=billing_category,
        )

        return await self.create_time_entry(matter_ref, entry, session_id)


# === CLI Interface ===

async def run_billing_demo():
    """Run billing demo from command line"""
    logging.basicConfig(level=logging.INFO)

    print("\n" + "="*60)
    print("MerusCase Billing Demo (Dry-Run)")
    print("="*60 + "\n")

    # This is a demo - replace with actual matter URL
    demo_matter_url = input("Enter matter URL (or press Enter for demo): ").strip()
    if not demo_matter_url:
        print("No URL provided - exiting demo")
        return

    demo_hours = float(input("Hours (e.g., 1.5): ") or "1.0")
    demo_description = input("Description: ") or "Demo time entry"

    print("\nStarting dry-run...")

    async with BillingBuilder(dry_run=True) as builder:
        result = await builder.quick_entry(
            matter_url=demo_matter_url,
            hours=demo_hours,
            description=demo_description,
        )

        print("\n" + "="*60)
        print("Result")
        print("="*60)
        print(f"Status: {result.status}")
        print(f"Message: {result.message}")
        if result.matter_name:
            print(f"Matter: {result.matter_name}")
        if result.screenshot_path:
            print(f"Screenshot: {result.screenshot_path}")
        if result.error:
            print(f"Error: {result.error}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(run_billing_demo())
