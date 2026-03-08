"""
File Handler - File input detection and upload operations
"""

import logging
import asyncio
from typing import Optional, List, Dict, Any
from pathlib import Path
from playwright.async_api import Page, Locator, TimeoutError as PlaywrightTimeout

logger = logging.getLogger(__name__)


class FileHandler:
    """
    Handles file upload operations with multiple detection strategies.

    Supports:
    - Native file input (<input type="file">)
    - Drag-and-drop zones
    - Custom upload buttons that trigger file dialogs
    """

    def __init__(self, page: Page):
        """
        Initialize file handler.

        Args:
            page: Playwright page object
        """
        self.page = page

    async def find_file_input(
        self,
        field_name: Optional[str] = None,
        label: Optional[str] = None,
        css_selector: Optional[str] = None,
        accept: Optional[str] = None,
        timeout: int = 5000
    ) -> Optional[Locator]:
        """
        Find file input element using multiple strategies.

        Args:
            field_name: Input name attribute
            label: Associated label text
            css_selector: CSS selector
            accept: File type filter (e.g., ".pdf,.doc")
            timeout: Timeout in milliseconds

        Returns:
            Locator object or None if not found
        """
        strategies = []

        # Strategy 1: CSS selector
        if css_selector:
            strategies.append(("CSS selector", lambda: self.page.locator(css_selector)))

        # Strategy 2: Name attribute for file input
        if field_name:
            strategies.append((
                f"file input name={field_name}",
                lambda: self.page.locator(f"input[type='file'][name='{field_name}']")
            ))

        # Strategy 3: Accept attribute match
        if accept:
            strategies.append((
                f"file input accept={accept}",
                lambda: self.page.locator(f"input[type='file'][accept*='{accept}']")
            ))

        # Strategy 4: Label association
        if label:
            strategies.append((
                f"label={label}",
                lambda: self.page.get_by_label(label, exact=False)
            ))

        # Strategy 5: Generic file input (fallback)
        strategies.append((
            "generic file input",
            lambda: self.page.locator("input[type='file']")
        ))

        # Try each strategy
        for strategy_name, locator_func in strategies:
            try:
                locator = locator_func()
                # File inputs may be hidden, so check for attached state
                count = await locator.count()
                if count > 0:
                    logger.info(f"Found file input using {strategy_name} ({count} found)")
                    return locator.first
            except PlaywrightTimeout:
                logger.debug(f"Strategy {strategy_name} timed out")
                continue
            except Exception as e:
                logger.debug(f"Strategy {strategy_name} error: {e}")
                continue

        logger.warning(f"Could not find file input (name={field_name}, label={label})")
        return None

    async def find_upload_button(
        self,
        text: Optional[str] = None,
        css_selector: Optional[str] = None,
        timeout: int = 5000
    ) -> Optional[Locator]:
        """
        Find upload button that triggers file dialog.

        Args:
            text: Button text (e.g., "Upload", "Add Document")
            css_selector: CSS selector
            timeout: Timeout in milliseconds

        Returns:
            Locator object or None
        """
        # Common upload button texts
        upload_texts = ["Upload", "Add Document", "Add File", "Choose File", "Browse"]
        if text:
            upload_texts.insert(0, text)

        strategies = []

        # Strategy 1: CSS selector
        if css_selector:
            strategies.append(("CSS selector", lambda: self.page.locator(css_selector)))

        # Strategy 2: Button by text
        for btn_text in upload_texts:
            strategies.append((
                f"button text='{btn_text}'",
                lambda t=btn_text: self.page.get_by_role("button", name=t, exact=False)
            ))

        # Strategy 3: Link styled as button
        for btn_text in upload_texts:
            strategies.append((
                f"link text='{btn_text}'",
                lambda t=btn_text: self.page.locator(f"a:has-text('{t}')")
            ))

        # Try each strategy
        for strategy_name, locator_func in strategies:
            try:
                locator = locator_func()
                await locator.wait_for(state="visible", timeout=timeout)
                logger.info(f"Found upload button using {strategy_name}")
                return locator
            except PlaywrightTimeout:
                logger.debug(f"Strategy {strategy_name} timed out")
                continue
            except Exception as e:
                logger.debug(f"Strategy {strategy_name} error: {e}")
                continue

        logger.warning(f"Could not find upload button (text={text})")
        return None

    async def find_drop_zone(
        self,
        css_selector: Optional[str] = None,
        timeout: int = 5000
    ) -> Optional[Locator]:
        """
        Find drag-and-drop upload zone.

        Args:
            css_selector: CSS selector
            timeout: Timeout in milliseconds

        Returns:
            Locator object or None
        """
        # Common drop zone selectors
        drop_zone_selectors = [
            ".dropzone",
            ".drop-zone",
            ".upload-drop",
            ".file-drop",
            "[data-dropzone]",
            "[data-upload-zone]",
            ".upload-area",
            ".drag-drop-area",
        ]

        if css_selector:
            drop_zone_selectors.insert(0, css_selector)

        for selector in drop_zone_selectors:
            try:
                locator = self.page.locator(selector)
                await locator.wait_for(state="visible", timeout=timeout)
                logger.info(f"Found drop zone: {selector}")
                return locator
            except PlaywrightTimeout:
                continue
            except Exception:
                continue

        logger.warning("Could not find drop zone")
        return None

    async def upload_file(
        self,
        file_path: str,
        file_input: Optional[Locator] = None,
        field_name: Optional[str] = None,
        wait_for_upload: bool = True,
        timeout: int = 30000
    ) -> bool:
        """
        Upload single file to input field.

        Args:
            file_path: Path to file to upload
            file_input: Pre-found file input locator (optional)
            field_name: File input name (if locator not provided)
            wait_for_upload: Wait for upload to complete
            timeout: Upload timeout in milliseconds

        Returns:
            True if upload successful
        """
        # Validate file exists
        path = Path(file_path)
        if not path.exists():
            logger.error(f"File does not exist: {file_path}")
            return False

        # Find file input if not provided
        if not file_input:
            file_input = await self.find_file_input(field_name=field_name)
            if not file_input:
                logger.error("Could not find file input for upload")
                return False

        try:
            # Use Playwright's native file upload
            await file_input.set_input_files(str(path))
            logger.info(f"Set file input: {path.name}")

            if wait_for_upload:
                # Wait for upload to complete
                await self._wait_for_upload_complete(timeout)

            return True

        except Exception as e:
            logger.error(f"File upload failed: {e}")
            return False

    async def upload_multiple_files(
        self,
        file_paths: List[str],
        file_input: Optional[Locator] = None,
        field_name: Optional[str] = None,
        wait_for_upload: bool = True,
        timeout: int = 60000
    ) -> Dict[str, bool]:
        """
        Upload multiple files.

        Args:
            file_paths: List of file paths
            file_input: Pre-found file input locator
            field_name: File input name (if locator not provided)
            wait_for_upload: Wait for uploads to complete
            timeout: Total upload timeout in milliseconds

        Returns:
            Dict mapping file paths to success status
        """
        results = {}

        # Validate all files exist
        valid_paths = []
        for fp in file_paths:
            path = Path(fp)
            if path.exists():
                valid_paths.append(str(path))
            else:
                logger.warning(f"File does not exist, skipping: {fp}")
                results[fp] = False

        if not valid_paths:
            logger.error("No valid files to upload")
            return results

        # Find file input if not provided
        if not file_input:
            file_input = await self.find_file_input(field_name=field_name)
            if not file_input:
                logger.error("Could not find file input for upload")
                for fp in valid_paths:
                    results[fp] = False
                return results

        # Check if input supports multiple files
        multiple_attr = await file_input.get_attribute("multiple")
        supports_multiple = multiple_attr is not None

        if supports_multiple:
            # Upload all at once
            try:
                await file_input.set_input_files(valid_paths)
                logger.info(f"Set {len(valid_paths)} files at once")

                if wait_for_upload:
                    await self._wait_for_upload_complete(timeout)

                for fp in valid_paths:
                    results[fp] = True

            except Exception as e:
                logger.error(f"Multi-file upload failed: {e}")
                for fp in valid_paths:
                    results[fp] = False
        else:
            # Upload one at a time
            logger.info("File input doesn't support multiple, uploading one by one")
            for fp in valid_paths:
                success = await self.upload_file(
                    fp,
                    file_input=file_input,
                    wait_for_upload=wait_for_upload,
                    timeout=timeout // len(valid_paths)
                )
                results[fp] = success

                # Re-find input for next file (form may reset)
                file_input = await self.find_file_input(field_name=field_name)
                if not file_input:
                    logger.error("Lost file input after upload")
                    break

                await asyncio.sleep(1)  # Brief delay between uploads

        return results

    async def upload_with_file_chooser(
        self,
        file_path: str,
        trigger_locator: Locator,
        timeout: int = 30000
    ) -> bool:
        """
        Upload file using file chooser dialog.

        Use this when the upload button triggers a native file dialog
        instead of a visible file input.

        Args:
            file_path: Path to file
            trigger_locator: Button/element that triggers file dialog
            timeout: Timeout in milliseconds

        Returns:
            True if upload successful
        """
        path = Path(file_path)
        if not path.exists():
            logger.error(f"File does not exist: {file_path}")
            return False

        try:
            # Start waiting for file chooser before clicking
            async with self.page.expect_file_chooser(timeout=timeout) as fc_info:
                await trigger_locator.click()

            file_chooser = await fc_info.value
            await file_chooser.set_files(str(path))

            logger.info(f"Uploaded via file chooser: {path.name}")
            return True

        except Exception as e:
            logger.error(f"File chooser upload failed: {e}")
            return False

    async def _wait_for_upload_complete(self, timeout: int = 30000) -> bool:
        """
        Wait for upload to complete.

        Monitors for:
        - Progress indicators to disappear
        - Success messages to appear
        - Loading spinners to complete

        Args:
            timeout: Timeout in milliseconds

        Returns:
            True if upload appears complete
        """
        # Common loading/progress indicators
        loading_selectors = [
            ".uploading",
            ".upload-progress",
            "[data-uploading='true']",
            ".progress-bar:not([style*='width: 100%'])",
            ".spinner",
            ".loading",
        ]

        # Success indicators
        success_selectors = [
            ".upload-success",
            ".upload-complete",
            "[data-upload-status='complete']",
            ".file-uploaded",
        ]

        start_time = asyncio.get_event_loop().time()
        end_time = start_time + (timeout / 1000)

        while asyncio.get_event_loop().time() < end_time:
            # Check for loading indicators
            is_loading = False
            for selector in loading_selectors:
                try:
                    if await self.page.locator(selector).is_visible():
                        is_loading = True
                        break
                except Exception:
                    continue

            if not is_loading:
                # Check for success indicator
                for selector in success_selectors:
                    try:
                        if await self.page.locator(selector).is_visible():
                            logger.info("Upload complete indicator found")
                            return True
                    except Exception:
                        continue

                # No loading, no explicit success - assume complete
                await asyncio.sleep(0.5)
                logger.info("Upload appears complete (no loading indicators)")
                return True

            await asyncio.sleep(0.5)

        logger.warning("Upload completion wait timed out")
        return False

    async def get_upload_status(self) -> Dict[str, Any]:
        """
        Get current upload status from page.

        Returns:
            Dict with status info (uploaded_count, pending_count, errors)
        """
        status = {
            "uploaded_count": 0,
            "pending_count": 0,
            "errors": [],
        }

        try:
            # Try to find uploaded file list
            uploaded = self.page.locator(".uploaded-file, .file-item, .document-row")
            status["uploaded_count"] = await uploaded.count()

            # Try to find pending uploads
            pending = self.page.locator(".uploading, .upload-pending")
            status["pending_count"] = await pending.count()

            # Try to find error messages
            errors = self.page.locator(".upload-error, .file-error")
            error_count = await errors.count()
            for i in range(error_count):
                error_text = await errors.nth(i).text_content()
                if error_text:
                    status["errors"].append(error_text.strip())

        except Exception as e:
            logger.debug(f"Could not get upload status: {e}")

        return status

    async def clear_file_input(self, file_input: Locator) -> bool:
        """
        Clear file input for new upload.

        Args:
            file_input: File input locator

        Returns:
            True if cleared successfully
        """
        try:
            await file_input.set_input_files([])
            logger.info("File input cleared")
            return True
        except Exception as e:
            logger.debug(f"Could not clear file input: {e}")
            return False
