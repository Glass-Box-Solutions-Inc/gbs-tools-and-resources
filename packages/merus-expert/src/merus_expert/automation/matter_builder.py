"""
Matter Builder - Main orchestrator for matter creation workflow
"""

import logging
from typing import Optional, Dict, Any
from pathlib import Path
import asyncio

from merus_expert.browser.client import MerusCaseBrowserClient
from merus_expert.automation.form_filler import FormFiller
from knowledge.screenshot_store import ScreenshotManager
from merus_expert.persistence.session_store import SessionStore
from merus_expert.persistence.matter_store import MatterStore
from merus_expert.security.audit import AuditLogger
from merus_expert.models.matter import MatterDetails
from merus_expert.security.config import SecurityConfig

logger = logging.getLogger(__name__)


class MatterBuilder:
    """
    Orchestrates the complete matter creation workflow.

    Workflow steps:
    1. LOGIN - Authenticate with MerusCase
    2. NAVIGATE - Navigate to new matter form
    3. FILL_FORM - Fill all form fields
    4. VALIDATE - Validate filled data
    5. SUBMIT - Submit form (or preview in dry-run)
    6. VERIFY - Verify matter created successfully
    """

    def __init__(
        self,
        config: Optional[SecurityConfig] = None,
        dry_run: bool = False
    ):
        """
        Initialize matter builder.

        Args:
            config: Security configuration
            dry_run: If True, preview only without submitting
        """
        self.config = config or SecurityConfig.from_env()
        self.dry_run = dry_run

        # Initialize components
        self.session_store = SessionStore(self.config.db_path)
        self.matter_store = MatterStore(self.config.db_path)
        self.audit_logger = AuditLogger(self.config.db_path)
        self.screenshot_manager = ScreenshotManager(
            self.config.db_path,
            retention_hours=self.config.screenshot_retention_hr
        )

        self.browser_client = None
        self.form_filler: Optional[FormFiller] = None
        self.current_session_id: Optional[str] = None
        self.current_matter_id: Optional[int] = None

    async def __aenter__(self):
        """Async context manager entry"""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.disconnect()

    async def connect(self):
        """Establish browser connection"""
        mode = "local browser" if self.config.use_local_browser else "Browserless"
        logger.info(f"Connecting to {mode}...")

        self.browser_client = MerusCaseBrowserClient(
            api_token=self.config.browserless_api_token,
            endpoint=self.config.browserless_endpoint,
            headless=self.config.use_headless,
            use_local=self.config.use_local_browser
        )

        await self.browser_client.connect()

        self.form_filler = FormFiller(self.browser_client.page)

        logger.info("Browser connected successfully")

    async def disconnect(self):
        """Close browser connection"""
        if self.browser_client:
            await self.browser_client.disconnect()
            logger.info("Browser disconnected")

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

            # Screenshot: Login page
            await self.screenshot_manager.capture_screenshot(
                self.browser_client.page,
                session_id,
                "login_page",
                "MerusCase login page loaded"
            )

            # Find email field
            email_input = await self.form_filler.element_handler.find_input(
                field_name="email",
                label="Email",
                placeholder="Email"
            )

            if not email_input:
                logger.error("Could not find email input field")
                return False

            # Find password field - try multiple strategies
            password_input = await self.form_filler.element_handler.find_input(
                field_name="password",
                label="Password",
                placeholder="Password",
                css_selector="input[type='password']"
            )

            if not password_input:
                logger.error("Could not find password input field")
                return False

            # Fill credentials
            await email_input.fill(self.config.meruscase_email)
            await password_input.fill(self.config.meruscase_password)

            # Find and click login button
            login_button = await self.form_filler.element_handler.find_button(
                text="Sign In",
                css_selector="button[type='submit'], input[type='submit']"
            )

            if not login_button:
                logger.error("Could not find login button")
                return False

            await login_button.click()

            # Wait for navigation
            await self.browser_client.page.wait_for_load_state("networkidle", timeout=30000)

            # Screenshot: Post-login
            await self.screenshot_manager.capture_screenshot(
                self.browser_client.page,
                session_id,
                "post_login",
                "Successfully logged in"
            )

            # Verify login success (check for dashboard or logout button)
            is_logged_in = await self.browser_client.page.locator(
                "[href*='logout'], [href*='sign-out'], .user-menu, .profile"
            ).is_visible()

            if is_logged_in:
                logger.info("Login successful")
                self.audit_logger.log(
                    event_type="login",
                    action="authenticate",
                    status="SUCCESS",
                    session_id=session_id,
                    resource=self.config.meruscase_login_url
                )
                return True
            else:
                logger.error("Login verification failed")
                return False

        except Exception as e:
            logger.error(f"Login failed: {e}")
            self.audit_logger.log(
                event_type="login",
                action="authenticate",
                status="FAILURE",
                session_id=session_id,
                metadata={"error": str(e)}
            )
            return False

    async def navigate_to_new_matter_form(self, session_id: str) -> bool:
        """
        Navigate to new matter creation form.

        Args:
            session_id: Session identifier

        Returns:
            True if navigation successful
        """
        try:
            logger.info("Navigating to new matter form...")

            # Common navigation patterns:
            # 1. Cases > New Case
            # 2. Matters > New Matter
            # 3. Direct URL

            # Navigate to new case form (MerusCase uses hash-based Angular routes)
            new_matter_url = f"{self.config.meruscase_base_url}/cms#/caseFiles/add?t=1&lpt=0&nr=1&lpa=0"
            await self.browser_client.navigate(new_matter_url)

            await asyncio.sleep(2)  # Wait for page to settle

            # Screenshot: New matter form
            await self.screenshot_manager.capture_screenshot(
                self.browser_client.page,
                session_id,
                "new_matter_form",
                "New matter form loaded"
            )

            # Verify form loaded (check for primary party field or form element)
            form_loaded = await self.browser_client.page.locator(
                "form, [data-form='matter'], input[name*='party'], input[name*='client']"
            ).is_visible()

            if form_loaded:
                logger.info("New matter form loaded successfully")
                return True
            else:
                logger.warning("Form verification uncertain, proceeding...")
                return True

        except Exception as e:
            logger.error(f"Navigation to new matter form failed: {e}")
            return False

    async def fill_matter_form(
        self,
        matter: MatterDetails,
        session_id: str,
        matter_id: int
    ) -> bool:
        """
        Fill the complete matter creation form.

        Args:
            matter: Matter details
            session_id: Session identifier
            matter_id: Matter tracking ID

        Returns:
            True if form filled successfully
        """
        try:
            logger.info("Filling matter form...")

            # Update matter status
            self.matter_store.update_status(matter_id, "in_progress")

            # Fill form using FormFiller
            success = await self.form_filler.fill_complete_form(matter)

            if not success:
                logger.error("Form filling failed")
                self.matter_store.update_status(matter_id, "failed")
                return False

            # Screenshot: Form filled
            screenshot_path = await self.screenshot_manager.capture_screenshot(
                self.browser_client.page,
                session_id,
                "form_filled",
                "All form fields populated",
                full_page=True
            )

            # Update matter with screenshot
            if screenshot_path:
                self.matter_store.add_screenshot(matter_id, screenshot_path)

            logger.info("Form filled successfully")
            return True

        except Exception as e:
            logger.error(f"Error filling form: {e}")
            self.matter_store.update_status(matter_id, "failed")
            return False

    async def submit_matter(self, session_id: str, matter_id: int) -> bool:
        """
        Submit the matter creation form.

        Args:
            session_id: Session identifier
            matter_id: Matter tracking ID

        Returns:
            True if submission successful
        """
        try:
            logger.info("Submitting matter form...")

            # Find submit button
            submit_button = await self.form_filler.element_handler.find_button(
                text="Save",
                css_selector="button[type='submit'], input[type='submit'], button:has-text('Save')"
            )

            if not submit_button:
                logger.error("Could not find submit button")
                return False

            # Click submit
            await submit_button.click()

            # Wait for submission to complete
            await self.browser_client.page.wait_for_load_state("networkidle", timeout=30000)

            # Wait for potential redirect after submission
            await asyncio.sleep(3)

            # Screenshot: Post-submit
            await self.screenshot_manager.capture_screenshot(
                self.browser_client.page,
                session_id,
                "post_submit",
                "Matter form submitted"
            )

            # Extract matter URL if redirected to matter details page
            # MerusCase uses hash-based Angular routes like #/caseFiles/{id}
            current_url = self.browser_client.page.url
            logger.info(f"Post-submit URL: {current_url}")

            # Check for matter page patterns (hash-based or path-based)
            is_matter_page = (
                ("/matters/" in current_url or "/cases/" in current_url) or
                ("#/caseFiles/" in current_url and "/add" not in current_url) or
                ("#/matters/" in current_url)
            )

            if is_matter_page:
                logger.info(f"Matter created successfully: {current_url}")
                self.matter_store.update_meruscase_info(
                    matter_id,
                    meruscase_url=current_url
                )
                self.matter_store.update_status(matter_id, "success")
                return True
            else:
                # Even if URL doesn't change, the matter might be created
                # Try to extract matter ID from success message or page content
                logger.warning(f"Submission result unclear (URL: {current_url})")

                # Store the current URL anyway for document upload attempts
                self.matter_store.update_meruscase_info(
                    matter_id,
                    meruscase_url=current_url
                )
                self.matter_store.update_status(matter_id, "needs_review")
                return True

        except Exception as e:
            logger.error(f"Submission failed: {e}")
            self.matter_store.update_status(matter_id, "failed")
            return False

    async def create_matter(
        self,
        matter: MatterDetails,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new matter in MerusCase.

        Main entry point for matter creation.

        Args:
            matter: Matter details
            session_id: Optional session ID (auto-generated if not provided)

        Returns:
            Result dictionary with matter_id, status, and metadata
        """
        # Generate session ID if not provided
        if not session_id:
            from datetime import datetime
            session_id = f"matter_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        self.current_session_id = session_id

        try:
            logger.info(f"Starting matter creation workflow (session: {session_id})")

            # Create session
            self.session_store.create_session(
                session_id,
                metadata={"dry_run": self.dry_run}
            )

            # Map CaseType to MatterType (models use display names, persistence uses snake_case)
            case_type_map = {
                "Immigration": "immigration",
                "Workers' Compensation": "workers_comp",
                "Family Law": "family_law",
                "Personal Injury": "personal_injury",
                "General": "general",
            }
            matter_type_value = case_type_map.get(
                matter.case_type.value if matter.case_type else "General",
                "general"
            )

            # Create matter record
            matter_id = self.matter_store.create_matter(
                session_id=session_id,
                matter_type=matter_type_value,
                primary_party=matter.primary_party,
                custom_fields=matter.custom_fields,
                dry_run=self.dry_run
            )

            self.current_matter_id = matter_id

            # Step 1: Login
            if not await self.login(session_id):
                raise Exception("Login failed")

            # Step 2: Navigate to form
            if not await self.navigate_to_new_matter_form(session_id):
                raise Exception("Navigation to form failed")

            # Step 3: Fill form
            if not await self.fill_matter_form(matter, session_id, matter_id):
                raise Exception("Form filling failed")

            # Step 4: Submit or preview
            if self.dry_run:
                logger.info("DRY-RUN MODE: Skipping submission")

                # Extract filled values for preview
                filled_values = await self.form_filler.extract_filled_values()

                # Screenshot: Dry-run preview
                screenshot_path = await self.screenshot_manager.capture_screenshot(
                    self.browser_client.page,
                    session_id,
                    "dry_run_preview",
                    "Dry-run preview (not submitted)",
                    full_page=True
                )

                self.matter_store.update_status(matter_id, "success")

                result = {
                    "matter_id": matter_id,
                    "session_id": session_id,
                    "status": "dry_run_success",
                    "filled_values": filled_values,
                    "screenshot_path": screenshot_path,
                    "message": "Form filled successfully (dry-run, not submitted)"
                }

            else:
                # Submit for real
                if not await self.submit_matter(session_id, matter_id):
                    raise Exception("Submission failed")

                result = {
                    "matter_id": matter_id,
                    "session_id": session_id,
                    "status": "success",
                    "meruscase_url": self.matter_store.get_matter(matter_id).get("meruscase_url"),
                    "message": "Matter created successfully"
                }

            # End session
            self.session_store.end_session(session_id)

            logger.info(f"Matter creation workflow completed: {result['status']}")

            return result

        except Exception as e:
            logger.error(f"Matter creation failed: {e}")

            # Update matter status
            if self.current_matter_id:
                self.matter_store.update_status(self.current_matter_id, "failed", error_message=str(e))

            # End session
            if session_id:
                self.session_store.end_session(session_id)

            # Log audit event
            self.audit_logger.log(
                event_type="matter_creation",
                action="create_matter",
                status="FAILURE",
                session_id=session_id,
                metadata={"error": str(e), "dry_run": self.dry_run}
            )

            return {
                "matter_id": self.current_matter_id,
                "session_id": session_id,
                "status": "failed",
                "error": str(e),
                "message": f"Matter creation failed: {str(e)}"
            }
