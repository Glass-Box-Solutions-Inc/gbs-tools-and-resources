"""
Document Explorer - Discover MerusCase document upload UI structure
"""

import logging
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime
from pathlib import Path
import json

from browser.client import MerusCaseBrowserClient
from browser.element_handler import ElementHandler
from browser.file_handler import FileHandler
from exploration.page_analyzer import PageAnalyzer
from knowledge.screenshot_store import ScreenshotManager
from persistence.session_store import SessionStore
from security.config import SecurityConfig
from security.audit import AuditLogger
from models.document import DocumentExplorationReport, DocumentUIElement

logger = logging.getLogger(__name__)


class DocumentExplorer:
    """
    Explores MerusCase document upload UI to discover:
    - Navigation paths to documents section
    - Upload button selectors
    - File input selectors
    - Drag-and-drop zones

    Results are stored in the knowledge base for use by DocumentUploader.
    """

    def __init__(self, config: Optional[SecurityConfig] = None):
        """
        Initialize document explorer.

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
        self.file_handler: Optional[FileHandler] = None
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
        logger.info("Connecting to Browserless for document exploration...")

        self.browser_client = MerusCaseBrowserClient(
            api_token=self.config.browserless_api_token,
            endpoint=self.config.browserless_endpoint
        )

        await self.browser_client.connect()

        self.element_handler = ElementHandler(self.browser_client.page)
        self.file_handler = FileHandler(self.browser_client.page)
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

            await self.browser_client.navigate(self.config.meruscase_login_url)
            await asyncio.sleep(2)

            # Screenshot: Login page
            await self.screenshot_manager.capture_screenshot(
                self.browser_client.page,
                session_id,
                "explore_login",
                "Login page for document exploration"
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
                logger.info("Login successful for exploration")
                return True

            logger.warning("Login verification uncertain")
            return True

        except Exception as e:
            logger.error(f"Login failed: {e}")
            return False

    async def explore_document_ui(
        self,
        matter_url: str,
        session_id: Optional[str] = None
    ) -> DocumentExplorationReport:
        """
        Full exploration of MerusCase document upload UI.

        Steps:
        1. Login
        2. Navigate to matter
        3. Find documents section
        4. Analyze upload UI
        5. Capture screenshots
        6. Store discoveries

        Args:
            matter_url: URL of a matter to use for exploration
            session_id: Optional session identifier

        Returns:
            DocumentExplorationReport with discovered elements
        """
        if not session_id:
            session_id = f"doc_explore_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        report = DocumentExplorationReport(session_id=session_id, matter_url=matter_url)

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

            # Step 3: Find Documents section navigation
            documents_nav_selectors = [
                "a[href*='document']",
                "a[href*='files']",
                "li:has-text('Documents')",
                "li:has-text('Files')",
                "[data-tab='documents']",
                ".nav-item:has-text('Documents')",
                "a:has-text('Documents')",
                "a:has-text('Files')",
                "[role='tab']:has-text('Documents')",
            ]

            documents_found = False
            for selector in documents_nav_selectors:
                try:
                    element = self.browser_client.page.locator(selector)
                    if await element.is_visible():
                        logger.info(f"Found documents nav: {selector}")
                        report.documents_nav_selectors.append(selector)
                        await element.click()
                        await asyncio.sleep(2)
                        documents_found = True
                        break
                except Exception:
                    continue

            if documents_found:
                # Screenshot: Documents section
                screenshot_path = await self.screenshot_manager.capture_screenshot(
                    self.browser_client.page,
                    session_id,
                    "documents_section",
                    "Documents section loaded"
                )
                report.screenshots.append(screenshot_path)

            # Step 4: Find upload button
            upload_button_selectors = [
                "button:has-text('Add Document')",
                "button:has-text('Upload')",
                "button:has-text('Add File')",
                "button:has-text('New Document')",
                "a:has-text('Add Document')",
                "a:has-text('Upload')",
                "[data-action='upload']",
                "[data-action='add-document']",
                ".add-document-btn",
                ".upload-btn",
                "button[title*='Upload']",
                "button[title*='Add']",
            ]

            upload_found = False
            for selector in upload_button_selectors:
                try:
                    element = self.browser_client.page.locator(selector)
                    if await element.is_visible():
                        logger.info(f"Found upload button: {selector}")
                        report.upload_button_selectors.append(selector)
                        await element.click()
                        await asyncio.sleep(2)
                        upload_found = True
                        break
                except Exception:
                    continue

            if upload_found:
                # Screenshot: Upload dialog
                screenshot_path = await self.screenshot_manager.capture_screenshot(
                    self.browser_client.page,
                    session_id,
                    "upload_dialog",
                    "Upload dialog opened"
                )
                report.screenshots.append(screenshot_path)

            # Step 5: Find file input
            file_input = await self.file_handler.find_file_input()
            if file_input:
                # Get selector info
                try:
                    input_id = await file_input.get_attribute("id")
                    input_name = await file_input.get_attribute("name")
                    input_accept = await file_input.get_attribute("accept")
                    is_multiple = await file_input.get_attribute("multiple") is not None

                    if input_id:
                        report.file_input_selectors.append(f"#{input_id}")
                    if input_name:
                        report.file_input_selectors.append(f"input[type='file'][name='{input_name}']")

                    report.file_input_selectors.append("input[type='file']")
                    report.upload_method = "file_input"
                    report.supports_multiple = is_multiple

                    logger.info(f"Found file input: id={input_id}, name={input_name}, multiple={is_multiple}")

                except Exception as e:
                    logger.debug(f"Could not get file input details: {e}")
                    report.file_input_selectors.append("input[type='file']")
                    report.upload_method = "file_input"

            # Step 6: Find drop zone
            drop_zone = await self.file_handler.find_drop_zone()
            if drop_zone:
                try:
                    zone_class = await drop_zone.get_attribute("class")
                    if zone_class:
                        first_class = zone_class.split()[0]
                        report.drop_zone_selectors.append(f".{first_class}")

                    report.drop_zone_selectors.append("[data-dropzone]")
                    if report.upload_method == "unknown":
                        report.upload_method = "drag_drop"

                    logger.info(f"Found drop zone: class={zone_class}")

                except Exception as e:
                    logger.debug(f"Could not get drop zone details: {e}")

            # Step 7: Store discoveries
            await self._store_discoveries(report)

            logger.info(
                f"Document exploration complete: "
                f"nav selectors: {len(report.documents_nav_selectors)}, "
                f"upload buttons: {len(report.upload_button_selectors)}, "
                f"file inputs: {len(report.file_input_selectors)}"
            )

            return report

        except Exception as e:
            logger.error(f"Document exploration failed: {e}")
            report.error = str(e)
            return report

    async def _store_discoveries(self, report: DocumentExplorationReport):
        """
        Store discovered UI elements in knowledge base.

        Args:
            report: DocumentExplorationReport with discoveries
        """
        try:
            # Store in JSON file
            discoveries_path = Path(self.config.db_path).parent / "document_discoveries.json"

            discoveries = {
                "session_id": report.session_id,
                "explored_at": report.explored_at.isoformat(),
                "matter_url": report.matter_url,
                "documents_nav_selectors": list(set(report.documents_nav_selectors)),
                "upload_button_selectors": list(set(report.upload_button_selectors)),
                "file_input_selectors": list(set(report.file_input_selectors)),
                "drop_zone_selectors": list(set(report.drop_zone_selectors)),
                "upload_method": report.upload_method,
                "supports_multiple": report.supports_multiple,
                "screenshots": report.screenshots,
            }

            discoveries_path.write_text(json.dumps(discoveries, indent=2))
            logger.info(f"Document discoveries saved to {discoveries_path}")

        except Exception as e:
            logger.error(f"Failed to store document discoveries: {e}")


# === CLI Interface ===

async def run_exploration(matter_url: str):
    """
    Run document UI exploration from command line.

    Args:
        matter_url: MerusCase matter URL to explore
    """
    logging.basicConfig(level=logging.INFO)

    print(f"\n{'='*60}")
    print("MerusCase Document Upload UI Explorer")
    print(f"{'='*60}\n")
    print(f"Matter URL: {matter_url}\n")

    async with DocumentExplorer() as explorer:
        report = await explorer.explore_document_ui(matter_url)

        print(f"\n{'='*60}")
        print("Exploration Results")
        print(f"{'='*60}\n")

        if report.error:
            print(f"ERROR: {report.error}")
            return

        print(f"Session ID: {report.session_id}")
        print(f"Upload Method: {report.upload_method}")
        print(f"Supports Multiple Files: {report.supports_multiple}")

        print(f"\nDocuments Navigation Selectors ({len(report.documents_nav_selectors)}):")
        for sel in report.documents_nav_selectors:
            print(f"  - {sel}")

        print(f"\nUpload Button Selectors ({len(report.upload_button_selectors)}):")
        for sel in report.upload_button_selectors:
            print(f"  - {sel}")

        print(f"\nFile Input Selectors ({len(report.file_input_selectors)}):")
        for sel in report.file_input_selectors:
            print(f"  - {sel}")

        print(f"\nDrop Zone Selectors ({len(report.drop_zone_selectors)}):")
        for sel in report.drop_zone_selectors:
            print(f"  - {sel}")

        print(f"\nScreenshots ({len(report.screenshots)}):")
        for path in report.screenshots:
            print(f"  - {path}")

        print(f"\n{'='*60}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python document_explorer.py <matter_url>")
        print("Example: python document_explorer.py https://meruscase.com/matters/12345")
        sys.exit(1)

    matter_url = sys.argv[1]
    asyncio.run(run_exploration(matter_url))
