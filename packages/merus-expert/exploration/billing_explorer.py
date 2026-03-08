"""
Billing Explorer - Discover MerusCase billing UI structure
"""

import logging
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime
from pathlib import Path
import json

from browser.client import MerusCaseBrowserClient
from browser.element_handler import ElementHandler
from exploration.page_analyzer import PageAnalyzer, PageStructure
from knowledge.screenshot_store import ScreenshotManager
from persistence.session_store import SessionStore
from security.config import SecurityConfig
from security.audit import AuditLogger
from models.billing import (
    ExplorationReport,
    BillingUIElement,
    BillingCategoryInfo
)

logger = logging.getLogger(__name__)


class BillingExplorer:
    """
    Explores MerusCase billing UI to discover:
    - Navigation paths to billing section
    - Form field selectors
    - Dropdown options (categories, timekeepers)
    - Button locations

    Results are stored in the knowledge base for use by BillingBuilder.
    """

    def __init__(
        self,
        config: Optional[SecurityConfig] = None
    ):
        """
        Initialize billing explorer.

        Args:
            config: Security configuration
        """
        self.config = config or SecurityConfig.from_env()

        # Initialize components
        self.session_store = SessionStore(self.config.db_path)
        self.audit_logger = AuditLogger(self.config.db_path)
        self.screenshot_manager = ScreenshotManager(
            self.config.db_path,
            retention_hours=self.config.screenshot_retention_hr
        )

        self.browser_client: Optional[MerusCaseBrowserClient] = None
        self.element_handler: Optional[ElementHandler] = None
        self.page_analyzer: Optional[PageAnalyzer] = None

    async def __aenter__(self):
        """Async context manager entry"""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.disconnect()

    async def connect(self):
        """Establish browser connection"""
        logger.info("Connecting to Browserless for exploration...")

        self.browser_client = MerusCaseBrowserClient(
            api_token=self.config.browserless_api_token,
            endpoint=self.config.browserless_endpoint
        )

        await self.browser_client.connect()

        self.element_handler = ElementHandler(self.browser_client.page)
        self.page_analyzer = PageAnalyzer(self.browser_client.page)

        logger.info("Browser connected for exploration")

    async def disconnect(self):
        """Close browser connection"""
        if self.browser_client:
            await self.browser_client.disconnect()
            logger.info("Explorer browser disconnected")

    async def login(self, session_id: str) -> bool:
        """
        Login to MerusCase.

        Args:
            session_id: Session identifier

        Returns:
            True if login successful
        """
        try:
            logger.info("Logging into MerusCase for exploration...")

            # Navigate to login page
            await self.browser_client.navigate(self.config.meruscase_login_url)
            await asyncio.sleep(2)

            # Screenshot: Login page
            await self.screenshot_manager.capture_screenshot(
                self.browser_client.page,
                session_id,
                "explore_login",
                "Login page for exploration"
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

            # Find and fill password
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
                logger.info("Login successful for exploration")
                return True

            logger.warning("Login verification uncertain")
            return True  # Continue anyway

        except Exception as e:
            logger.error(f"Login failed: {e}")
            return False

    async def explore_billing_ui(
        self,
        matter_url: str,
        session_id: Optional[str] = None
    ) -> ExplorationReport:
        """
        Full exploration of MerusCase billing UI.

        Steps:
        1. Login
        2. Navigate to matter
        3. Find billing section
        4. Open time entry form
        5. Extract all form elements
        6. Capture screenshots
        7. Store discoveries

        Args:
            matter_url: URL of a matter to use for exploration
            session_id: Optional session identifier

        Returns:
            ExplorationReport with discovered elements
        """
        if not session_id:
            session_id = f"explore_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        report = ExplorationReport(session_id=session_id, matter_url=matter_url)

        try:
            # Step 1: Login
            if not await self.login(session_id):
                report.error = "Login failed"
                return report

            # Step 2: Navigate to matter
            logger.info(f"Navigating to matter: {matter_url}")
            await self.browser_client.navigate(matter_url)
            await asyncio.sleep(2)

            # Screenshot: Matter page
            screenshot_path = await self.screenshot_manager.capture_screenshot(
                self.browser_client.page,
                session_id,
                "matter_page",
                "Matter page loaded"
            )
            report.screenshots.append(screenshot_path)

            # Step 3: Analyze matter page for billing navigation
            matter_structure = await self.page_analyzer.analyze_page()
            billing_elements = await self.page_analyzer.find_billing_related_elements()

            # Find billing tab/link
            billing_nav = billing_elements.get("billing_tabs", [])
            for nav in billing_nav:
                report.billing_nav_selectors.append(nav.selector)

            # Try common billing section selectors
            billing_selectors = [
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
            ]

            # Step 4: Navigate to billing section
            billing_found = False
            for selector in billing_selectors:
                try:
                    element = self.browser_client.page.locator(selector)
                    if await element.is_visible():
                        logger.info(f"Found billing nav: {selector}")
                        report.billing_nav_selectors.append(selector)
                        await element.click()
                        await asyncio.sleep(2)
                        billing_found = True
                        break
                except Exception:
                    continue

            if billing_found:
                # Screenshot: Billing section
                screenshot_path = await self.screenshot_manager.capture_screenshot(
                    self.browser_client.page,
                    session_id,
                    "billing_section",
                    "Billing section loaded"
                )
                report.screenshots.append(screenshot_path)

            # Step 5: Find "Add Time Entry" button
            add_entry_selectors = [
                "button:has-text('Add Time')",
                "button:has-text('New Entry')",
                "button:has-text('Add Entry')",
                "a:has-text('Add Time')",
                "a:has-text('New Entry')",
                "[data-action='add-time']",
                ".add-time-btn",
                "button:has-text('+')",
            ]

            for selector in add_entry_selectors:
                try:
                    element = self.browser_client.page.locator(selector)
                    if await element.is_visible():
                        logger.info(f"Found add entry button: {selector}")
                        report.add_entry_selectors.append(selector)
                        await element.click()
                        await asyncio.sleep(2)
                        break
                except Exception:
                    continue

            # Step 6: Extract form fields
            form_structure = await self.page_analyzer.analyze_page()

            # Screenshot: Entry form
            screenshot_path = await self.screenshot_manager.capture_screenshot(
                self.browser_client.page,
                session_id,
                "entry_form",
                "Time entry form"
            )
            report.screenshots.append(screenshot_path)

            # Map discovered fields to billing elements
            for field in form_structure.form_fields:
                element = BillingUIElement(
                    element_key=self._infer_element_key(field),
                    primary_selector=field.selector,
                    fallback_selectors=[],
                    element_type=field.tag_name,
                    label_text=field.label,
                    is_required=field.required,
                )
                report.form_fields.append(element)

                # Store dropdown options
                if field.options:
                    report.dropdown_options[field.name] = field.options

            # Step 7: Store discoveries in knowledge base
            await self._store_discoveries(report)

            logger.info(
                f"Exploration complete: {len(report.form_fields)} fields, "
                f"{len(report.dropdown_options)} dropdowns"
            )

            return report

        except Exception as e:
            logger.error(f"Exploration failed: {e}")
            report.error = str(e)
            return report

    def _infer_element_key(self, field) -> str:
        """
        Infer semantic key for a form field.

        Args:
            field: FormFieldInfo object

        Returns:
            Semantic key like 'hours_input', 'category_dropdown'
        """
        name_lower = (field.name + field.label + field.placeholder).lower()

        # Hours/time field
        if any(kw in name_lower for kw in ['hour', 'time', 'duration', 'qty']):
            return 'hours_input'

        # Description field
        if any(kw in name_lower for kw in ['description', 'note', 'narrative', 'detail']):
            return 'description_field'

        # Category/type dropdown
        if field.tag_name == 'select':
            if any(kw in name_lower for kw in ['category', 'type', 'activity', 'code']):
                return 'category_dropdown'
            if any(kw in name_lower for kw in ['timekeeper', 'attorney', 'user']):
                return 'timekeeper_dropdown'

        # Date field
        if any(kw in name_lower for kw in ['date']):
            return 'date_input'

        # Rate field
        if any(kw in name_lower for kw in ['rate', 'price']):
            return 'rate_input'

        # Billable checkbox
        if field.field_type == 'checkbox' and 'billable' in name_lower:
            return 'billable_checkbox'

        return f"unknown_{field.name or field.id or 'field'}"

    async def _store_discoveries(self, report: ExplorationReport):
        """
        Store discovered UI elements in knowledge base.

        Args:
            report: ExplorationReport with discoveries
        """
        try:
            # Store in JSON file for now (can be migrated to DB later)
            discoveries_path = Path(self.config.db_path).parent / "billing_discoveries.json"

            discoveries = {
                "session_id": report.session_id,
                "explored_at": report.explored_at.isoformat(),
                "matter_url": report.matter_url,
                "billing_nav_selectors": list(set(report.billing_nav_selectors)),
                "add_entry_selectors": list(set(report.add_entry_selectors)),
                "form_fields": [
                    {
                        "element_key": f.element_key,
                        "primary_selector": f.primary_selector,
                        "element_type": f.element_type,
                        "label_text": f.label_text,
                        "is_required": f.is_required,
                    }
                    for f in report.form_fields
                ],
                "dropdown_options": report.dropdown_options,
                "screenshots": report.screenshots,
            }

            discoveries_path.write_text(json.dumps(discoveries, indent=2))
            logger.info(f"Discoveries saved to {discoveries_path}")

        except Exception as e:
            logger.error(f"Failed to store discoveries: {e}")

    async def quick_explore(
        self,
        matter_url: str,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Quick exploration - just capture screenshots and basic structure.

        Args:
            matter_url: Matter URL to explore
            session_id: Optional session ID

        Returns:
            Dict with basic exploration results
        """
        if not session_id:
            session_id = f"quick_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        result = {
            "session_id": session_id,
            "success": False,
            "screenshots": [],
            "page_titles": [],
            "error": None,
        }

        try:
            # Login
            if not await self.login(session_id):
                result["error"] = "Login failed"
                return result

            # Navigate and screenshot
            await self.browser_client.navigate(matter_url)
            await asyncio.sleep(2)

            result["page_titles"].append(await self.browser_client.page.title())

            # Screenshot matter page
            screenshot = await self.screenshot_manager.capture_screenshot(
                self.browser_client.page,
                session_id,
                "quick_matter",
                "Quick explore - matter page"
            )
            result["screenshots"].append(screenshot)

            # Try to find and click billing tab
            billing_clicked = False
            for selector in ["a:has-text('Billing')", "a:has-text('Time')", "[data-tab='billing']"]:
                try:
                    el = self.browser_client.page.locator(selector)
                    if await el.is_visible():
                        await el.click()
                        await asyncio.sleep(2)
                        billing_clicked = True
                        break
                except Exception:
                    continue

            if billing_clicked:
                result["page_titles"].append(await self.browser_client.page.title())
                screenshot = await self.screenshot_manager.capture_screenshot(
                    self.browser_client.page,
                    session_id,
                    "quick_billing",
                    "Quick explore - billing section"
                )
                result["screenshots"].append(screenshot)

            result["success"] = True
            return result

        except Exception as e:
            result["error"] = str(e)
            return result


# === CLI Interface ===

async def run_exploration(matter_url: str):
    """
    Run exploration from command line.

    Args:
        matter_url: MerusCase matter URL to explore
    """
    logging.basicConfig(level=logging.INFO)

    print(f"\n{'='*60}")
    print("MerusCase Billing UI Explorer")
    print(f"{'='*60}\n")
    print(f"Matter URL: {matter_url}\n")

    async with BillingExplorer() as explorer:
        report = await explorer.explore_billing_ui(matter_url)

        print(f"\n{'='*60}")
        print("Exploration Results")
        print(f"{'='*60}\n")

        if report.error:
            print(f"ERROR: {report.error}")
            return

        print(f"Session ID: {report.session_id}")
        print(f"\nBilling Navigation Selectors ({len(report.billing_nav_selectors)}):")
        for sel in report.billing_nav_selectors:
            print(f"  - {sel}")

        print(f"\nAdd Entry Selectors ({len(report.add_entry_selectors)}):")
        for sel in report.add_entry_selectors:
            print(f"  - {sel}")

        print(f"\nForm Fields ({len(report.form_fields)}):")
        for field in report.form_fields:
            print(f"  - {field.element_key}: {field.primary_selector}")
            if field.label_text:
                print(f"    Label: {field.label_text}")

        print(f"\nDropdown Options:")
        for name, options in report.dropdown_options.items():
            print(f"  {name}: {len(options)} options")
            for opt in options[:5]:
                print(f"    - {opt.get('text', opt.get('value', '?'))}")
            if len(options) > 5:
                print(f"    ... and {len(options) - 5} more")

        print(f"\nScreenshots ({len(report.screenshots)}):")
        for path in report.screenshots:
            print(f"  - {path}")

        print(f"\n{'='*60}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python billing_explorer.py <matter_url>")
        print("Example: python billing_explorer.py https://meruscase.com/matters/12345")
        sys.exit(1)

    matter_url = sys.argv[1]
    asyncio.run(run_exploration(matter_url))
