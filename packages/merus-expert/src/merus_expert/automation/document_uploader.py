"""
Document Uploader - Workflow for uploading documents to MerusCase matters
"""

import logging
import asyncio
from typing import Optional, Dict, Any, List
from pathlib import Path
from datetime import datetime

from merus_expert.browser.client import MerusCaseBrowserClient
from merus_expert.browser.file_handler import FileHandler
from merus_expert.browser.element_handler import ElementHandler
from knowledge.screenshot_store import ScreenshotManager
from merus_expert.persistence.session_store import SessionStore
from merus_expert.security.config import SecurityConfig
from merus_expert.security.audit import AuditLogger
from merus_expert.models.document import (
    DocumentUpload,
    DocumentUploadRequest,
    DocumentUploadResult,
    UploadStatus,
)

logger = logging.getLogger(__name__)


class DocumentUploader:
    """
    Orchestrates document upload workflow for MerusCase matters.

    Workflow steps:
    1. LOGIN - Authenticate with MerusCase (if not already)
    2. NAVIGATE_TO_MATTER - Go to matter page
    3. NAVIGATE_TO_DOCUMENTS - Go to Documents section
    4. OPEN_UPLOAD_DIALOG - Click "Add Document" or similar
    5. UPLOAD_FILES - Upload each file
    6. VERIFY - Confirm uploads successful
    """

    def __init__(
        self,
        config: Optional[SecurityConfig] = None,
        browser_client: Optional[MerusCaseBrowserClient] = None,
    ):
        """
        Initialize document uploader.

        Args:
            config: Security configuration
            browser_client: Existing browser client (for reuse)
        """
        self.config = config or SecurityConfig.from_env()
        self._external_browser = browser_client is not None
        self.browser_client = browser_client

        # Initialize components
        self.session_store = SessionStore(self.config.db_path)
        self.audit_logger = AuditLogger(self.config.db_path)
        self.screenshot_manager = ScreenshotManager(
            self.config.db_path,
            retention_hours=self.config.screenshot_retention_hr
        )

        self.file_handler: Optional[FileHandler] = None
        self.element_handler: Optional[ElementHandler] = None
        self.current_session_id: Optional[str] = None

        # Discovered selectors (from exploration or defaults)
        self.document_nav_selectors = [
            "a[href*='document']",
            "a[href*='files']",
            "li:has-text('Documents')",
            "[data-tab='documents']",
            ".nav-item:has-text('Documents')",
            "a:has-text('Documents')",
        ]

        self.upload_button_selectors = [
            "button:has-text('Add Document')",
            "button:has-text('Upload')",
            "button:has-text('Add File')",
            "a:has-text('Add Document')",
            "a:has-text('Upload')",
            "[data-action='upload']",
            ".add-document-btn",
        ]

    async def __aenter__(self):
        """Async context manager entry"""
        if not self._external_browser:
            await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if not self._external_browser:
            await self.disconnect()

    async def connect(self):
        """Establish browser connection"""
        logger.info("Connecting to browser for document upload...")

        self.browser_client = MerusCaseBrowserClient(
            api_token=self.config.browserless_api_token,
            endpoint=self.config.browserless_endpoint,
            headless=self.config.use_headless,
            use_local=self.config.use_local_browser
        )

        await self.browser_client.connect()
        self._init_handlers()

        logger.info("Browser connected for document upload")

    def _init_handlers(self):
        """Initialize page handlers"""
        if self.browser_client and self.browser_client.page:
            self.file_handler = FileHandler(self.browser_client.page)
            self.element_handler = ElementHandler(self.browser_client.page)

    async def disconnect(self):
        """Close browser connection"""
        if self.browser_client and not self._external_browser:
            await self.browser_client.disconnect()
            logger.info("Document uploader browser disconnected")

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

            await self.browser_client.navigate(self.config.meruscase_login_url)
            await self.browser_client.page.wait_for_load_state("networkidle", timeout=60000)
            await asyncio.sleep(3)

            # Find email input (MerusCase uses text input, not email type)
            email_input = self.browser_client.page.locator("input[type='text']:first-child").first
            await email_input.wait_for(state="visible", timeout=30000)

            # Find password input
            password_input = self.browser_client.page.locator("input[placeholder='Password'], input[type='password']").first

            await email_input.fill(self.config.meruscase_email)
            await password_input.fill(self.config.meruscase_password)

            # Click LOGIN button (MerusCase uses uppercase)
            login_button = self.browser_client.page.locator("button:has-text('LOGIN')").first
            await login_button.click()
            await self.browser_client.page.wait_for_load_state("networkidle", timeout=30000)
            await asyncio.sleep(2)

            logger.info(f"Logged in. URL: {self.browser_client.page.url}")
            return True

        except Exception as e:
            logger.error(f"Login failed: {e}")
            return False

    async def navigate_to_matter(self, matter_url: str, session_id: str) -> bool:
        """
        Navigate to matter page.

        Args:
            matter_url: MerusCase matter URL
            session_id: Session identifier

        Returns:
            True if navigation successful
        """
        try:
            logger.info(f"Navigating to matter: {matter_url}")
            await self.browser_client.navigate(matter_url)
            await asyncio.sleep(2)

            # Screenshot: Matter page
            await self.screenshot_manager.capture_screenshot(
                self.browser_client.page,
                session_id,
                "matter_page",
                "Matter page loaded for document upload"
            )

            return True

        except Exception as e:
            logger.error(f"Navigation to matter failed: {e}")
            return False

    async def navigate_to_case_and_upload_tool(
        self,
        case_name: str,
        session_id: str
    ) -> bool:
        """
        Navigate to a case via search and open Upload Tool.

        MerusCase workflow:
        1. Click Cases dropdown
        2. Search for case
        3. Click on case result
        4. Open Documents dropdown → Upload Tool

        Args:
            case_name: Case name to search for
            session_id: Session identifier

        Returns:
            True if navigation successful
        """
        try:
            logger.info(f"Navigating to case: {case_name}")

            # Step 1: Click Cases dropdown
            cases_menu = self.browser_client.page.locator("a:has-text('Cases')").first
            await cases_menu.click()
            await asyncio.sleep(1)

            # Step 2: Search for case
            search_input = self.browser_client.page.locator(
                "input[placeholder*='Search'], input[type='search'], .search-input"
            ).first
            try:
                if await search_input.is_visible(timeout=3000):
                    await search_input.fill(case_name.split()[0])  # Use first word
                    await asyncio.sleep(2)
            except:
                pass

            # Step 3: Click on case result
            case_link = self.browser_client.page.locator(f"a:has-text('{case_name.split()[0]}')").first
            await case_link.click()
            await asyncio.sleep(3)

            logger.info(f"Case page URL: {self.browser_client.page.url}")

            # Step 4: Open Documents dropdown → Upload Tool
            return await self.open_upload_tool(session_id)

        except Exception as e:
            logger.error(f"Navigation failed: {e}")
            return False

    async def open_upload_tool(self, session_id: str) -> bool:
        """
        Open Upload Tool from Documents dropdown in main nav.

        Args:
            session_id: Session identifier

        Returns:
            True if Upload Tool opened successfully
        """
        logger.info("Opening Upload Tool...")

        try:
            # Click Documents dropdown in main nav
            docs_dropdown = self.browser_client.page.locator(
                "nav a:has-text('Documents'), header a:has-text('Documents')"
            ).first
            await docs_dropdown.click()
            await asyncio.sleep(1)

            # Click Upload Tool option
            upload_tool = self.browser_client.page.locator("a:has-text('Upload Tool')").first
            if await upload_tool.is_visible(timeout=3000):
                await upload_tool.click()
                await asyncio.sleep(3)
                await self.browser_client.page.wait_for_load_state("networkidle", timeout=10000)
                logger.info("Upload Tool opened")
                return True

            logger.warning("Upload Tool not found in dropdown")
            return False

        except Exception as e:
            logger.error(f"Failed to open Upload Tool: {e}")
            return False

    async def navigate_to_documents(self, session_id: str) -> bool:
        """
        Navigate to Documents section of the matter (via tab).

        Args:
            session_id: Session identifier

        Returns:
            True if navigation successful
        """
        logger.info("Navigating to Documents tab...")

        try:
            docs_tab = self.browser_client.page.locator(
                ".nav-tabs a:has-text('Documents'), a[href*='document_search']"
            ).first
            if await docs_tab.is_visible(timeout=3000):
                await docs_tab.click()
                await asyncio.sleep(2)
                logger.info("Documents tab clicked")
                return True
        except:
            pass

        # Fallback: try other selectors
        for selector in self.document_nav_selectors:
            try:
                element = self.browser_client.page.locator(selector)
                if await element.is_visible():
                    logger.info(f"Found documents nav: {selector}")
                    await element.click()
                    await asyncio.sleep(2)
                    return True
            except Exception as e:
                logger.debug(f"Selector {selector} failed: {e}")
                continue

        logger.warning("Could not find Documents navigation")
        return False

    async def open_upload_dialog(self, session_id: str) -> bool:
        """
        Open document upload dialog - uses Upload Tool.

        Args:
            session_id: Session identifier

        Returns:
            True if dialog opened successfully
        """
        return await self.open_upload_tool(session_id)

    async def _dismiss_upload_modal(self):
        """
        Dismiss the upload confirmation modal.

        Tries clicking "Upload More Documents" first, then uses JavaScript
        to forcibly remove modal overlay if needed.
        """
        try:
            # Try clicking "Upload More Documents" button
            more_btn = self.browser_client.page.locator(
                "button:has-text('Upload More Documents')"
            ).first
            if await more_btn.is_visible(timeout=3000):
                await more_btn.click()
                logger.info("Clicked 'Upload More Documents'")
                await asyncio.sleep(2)

            # Verify modal is closed, if not force close with JS
            overlay = self.browser_client.page.locator(".plainmodal-overlay")
            if await overlay.count() > 0:
                # Force remove modal overlay with JavaScript
                await self.browser_client.page.evaluate("""
                    () => {
                        // Remove modal overlays
                        document.querySelectorAll('.plainmodal-overlay').forEach(el => el.remove());
                        document.querySelectorAll('.modal-backdrop').forEach(el => el.remove());
                        document.querySelectorAll('.modal.show').forEach(el => {
                            el.classList.remove('show');
                            el.style.display = 'none';
                        });
                        // Remove body modal class
                        document.body.classList.remove('modal-open');
                        document.body.style.overflow = '';
                    }
                """)
                logger.info("Force-closed modal overlay with JavaScript")
                await asyncio.sleep(1)

        except Exception as e:
            logger.debug(f"Modal dismiss issue: {e}")
            # Last resort: reload Upload Tool
            try:
                await self.open_upload_tool("recovery")
            except:
                pass

    async def upload_single_document(
        self,
        document: DocumentUpload,
        session_id: str
    ) -> DocumentUpload:
        """
        Upload a single document using MerusCase Upload Tool.

        Args:
            document: Document to upload
            session_id: Session identifier

        Returns:
            Updated DocumentUpload with status
        """
        logger.info(f"Uploading: {document.file_name}")
        document.upload_status = UploadStatus.UPLOADING

        try:
            # Find the Upload Tool's file input (accepts any file type)
            file_input_selectors = [
                "input[name='data[Upload][submitted_files][]']",  # Upload Tool main input
                "input[name='data[Upload][folder]']",  # Folder upload input
                "input[type='file']:not([accept='image/*'])",  # Non-image-restricted
                "input[type='file']",  # Fallback
            ]

            file_input = None
            for selector in file_input_selectors:
                try:
                    el = self.browser_client.page.locator(selector)
                    if await el.count() > 0:
                        file_input = el.first
                        logger.info(f"Found file input: {selector}")
                        break
                except:
                    continue

            if not file_input:
                logger.error("No file input found on Upload Tool page")
                document.upload_status = UploadStatus.FAILED
                document.error_message = "No file input found"
                return document

            # Set file to input
            await file_input.set_input_files(document.file_path)
            logger.info("File added to upload queue")

            # Wait for file to be queued
            await asyncio.sleep(3)

            # Click Upload button to finalize
            upload_btn = self.browser_client.page.locator(
                "button:has-text('Upload'), .btn:has-text('Upload')"
            ).first
            if await upload_btn.is_visible(timeout=5000):
                await upload_btn.click()
                logger.info("Upload button clicked")

                # Wait for upload to complete
                await asyncio.sleep(10)

                # Check for success (confirmation dialog appears)
                page_text = await self.browser_client.page.inner_text("body")
                if "attached" in page_text.lower() or "complete" in page_text.lower():
                    document.upload_status = UploadStatus.SUCCESS
                    document.uploaded_at = datetime.now()
                    logger.info(f"✓ Upload successful: {document.file_name}")

                    # Dismiss modal and prepare for next upload
                    await self._dismiss_upload_modal()
                else:
                    document.upload_status = UploadStatus.FAILED
                    document.error_message = "Upload confirmation not found"
                    logger.warning(f"Upload uncertain: {document.file_name}")
            else:
                document.upload_status = UploadStatus.FAILED
                document.error_message = "Upload button not found"
                logger.error("Upload button not visible")

        except Exception as e:
            document.upload_status = UploadStatus.FAILED
            document.error_message = str(e)
            logger.error(f"Upload error for {document.file_name}: {e}")

        return document

    async def upload_documents(
        self,
        request: DocumentUploadRequest,
        session_id: Optional[str] = None
    ) -> DocumentUploadResult:
        """
        Upload multiple documents to a matter.

        Main entry point for document uploads.

        Args:
            request: Upload request with matter and documents
            session_id: Session identifier (auto-generated if not provided)

        Returns:
            DocumentUploadResult with upload results
        """
        if not session_id:
            session_id = f"doc_upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        self.current_session_id = session_id

        result = DocumentUploadResult(
            session_id=session_id,
            matter_id=request.matter_id,
            matter_url=request.matter_url,
            total_documents=len(request.documents),
            uploaded_count=0,
            failed_count=0,
            skipped_count=0,
            status="in_progress",
            documents=request.documents.copy(),
        )

        try:
            logger.info(f"Starting document upload (session: {session_id})")
            logger.info(f"Matter: {request.matter_id}, Documents: {len(request.documents)}")

            # Create session
            self.session_store.create_session(
                session_id,
                metadata={"matter_id": request.matter_id, "type": "document_upload"}
            )

            # Step 1: Navigate to matter and open Upload Tool
            if request.matter_url:
                if not await self.navigate_to_matter(request.matter_url, session_id):
                    raise Exception("Failed to navigate to matter")
                # Open Upload Tool via Documents dropdown
                if not await self.open_upload_tool(session_id):
                    raise Exception("Failed to open Upload Tool")
            elif hasattr(request, 'case_name') and request.case_name:
                # Navigate via case search
                if not await self.navigate_to_case_and_upload_tool(request.case_name, session_id):
                    raise Exception("Failed to navigate to case")
            else:
                raise Exception("Matter URL or case name required")

            # Step 2: Upload each document (staying on Upload Tool page)
            for i, doc in enumerate(result.documents):
                logger.info(f"Uploading document {i+1}/{len(result.documents)}: {doc.file_name}")

                # Validate file exists
                if not Path(doc.file_path).exists():
                    doc.upload_status = UploadStatus.SKIPPED
                    doc.error_message = "File not found"
                    result.skipped_count += 1
                    continue

                # Upload document
                updated_doc = await self.upload_single_document(doc, session_id)
                result.documents[i] = updated_doc

                if updated_doc.upload_status == UploadStatus.SUCCESS:
                    result.uploaded_count += 1
                elif updated_doc.upload_status == UploadStatus.FAILED:
                    result.failed_count += 1
                elif updated_doc.upload_status == UploadStatus.SKIPPED:
                    result.skipped_count += 1

                # Small delay between uploads
                if i < len(result.documents) - 1:
                    await asyncio.sleep(1)

            # Step 5: Final screenshot
            screenshot_path = await self.screenshot_manager.capture_screenshot(
                self.browser_client.page,
                session_id,
                "upload_complete",
                f"Uploaded {result.uploaded_count}/{result.total_documents} documents"
            )
            result.screenshot_path = screenshot_path

            # Determine final status
            if result.failed_count == 0 and result.skipped_count == 0:
                result.status = "success"
            elif result.uploaded_count > 0:
                result.status = "partial"
            else:
                result.status = "failed"

            result.completed_at = datetime.now()

            # End session
            self.session_store.end_session(session_id)

            # Audit log
            self.audit_logger.log(
                event_type="document_upload",
                action="upload_documents",
                status="SUCCESS" if result.status == "success" else "PARTIAL",
                session_id=session_id,
                resource=request.matter_url,
                metadata={
                    "total": result.total_documents,
                    "uploaded": result.uploaded_count,
                    "failed": result.failed_count,
                }
            )

            logger.info(f"Document upload complete: {result.uploaded_count}/{result.total_documents}")

            return result

        except Exception as e:
            logger.error(f"Document upload failed: {e}")
            result.status = "failed"
            result.error = str(e)
            result.completed_at = datetime.now()

            if session_id:
                self.session_store.end_session(session_id)

            self.audit_logger.log(
                event_type="document_upload",
                action="upload_documents",
                status="FAILURE",
                session_id=session_id,
                metadata={"error": str(e)}
            )

            return result

    async def upload_folder(
        self,
        folder_path: str,
        matter_url: str,
        matter_id: str,
        session_id: Optional[str] = None,
        file_types: Optional[List[str]] = None,
    ) -> DocumentUploadResult:
        """
        Upload all files from a folder to a matter.

        Convenience method for batch operations.

        Args:
            folder_path: Path to folder containing files
            matter_url: MerusCase matter URL
            matter_id: Matter ID
            session_id: Session identifier
            file_types: File extensions to include (None = all)

        Returns:
            DocumentUploadResult
        """
        folder = Path(folder_path)
        if not folder.exists() or not folder.is_dir():
            raise ValueError(f"Invalid folder path: {folder_path}")

        # Collect files
        documents = []
        for f in sorted(folder.iterdir()):
            if f.is_file():
                # Filter by type if specified
                if file_types:
                    if f.suffix.lower().lstrip('.') not in file_types:
                        continue

                documents.append(DocumentUpload.from_path(str(f)))

        if not documents:
            raise ValueError(f"No files found in folder: {folder_path}")

        logger.info(f"Found {len(documents)} files in {folder_path}")

        # Create request
        request = DocumentUploadRequest(
            matter_id=matter_id,
            matter_url=matter_url,
            documents=documents,
            session_id=session_id,
        )

        return await self.upload_documents(request, session_id)


# === CLI Interface ===

async def run_upload(matter_url: str, folder_path: str):
    """
    Run document upload from command line.

    Args:
        matter_url: MerusCase matter URL
        folder_path: Path to folder with documents
    """
    logging.basicConfig(level=logging.INFO)

    print(f"\n{'='*60}")
    print("MerusCase Document Uploader")
    print(f"{'='*60}\n")
    print(f"Matter URL: {matter_url}")
    print(f"Folder: {folder_path}\n")

    async with DocumentUploader() as uploader:
        # Login first
        session_id = f"upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        if not await uploader.login(session_id):
            print("ERROR: Login failed")
            return

        # Upload folder
        result = await uploader.upload_folder(
            folder_path=folder_path,
            matter_url=matter_url,
            matter_id="unknown",
            session_id=session_id,
        )

        print(f"\n{'='*60}")
        print("Upload Results")
        print(f"{'='*60}\n")
        print(f"Status: {result.status}")
        print(f"Total: {result.total_documents}")
        print(f"Uploaded: {result.uploaded_count}")
        print(f"Failed: {result.failed_count}")
        print(f"Skipped: {result.skipped_count}")

        if result.error:
            print(f"\nError: {result.error}")

        print(f"\nScreenshot: {result.screenshot_path}")
        print(f"\n{'='*60}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python document_uploader.py <matter_url> <folder_path>")
        sys.exit(1)

    matter_url = sys.argv[1]
    folder_path = sys.argv[2]
    asyncio.run(run_upload(matter_url, folder_path))
