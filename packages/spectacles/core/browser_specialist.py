"""
Spectacles Browser Specialist
Executes browser actions using perception layer

The worker component that translates high-level directives into Playwright commands.
Uses hybrid DOM/VLM perception for robust element finding.
"""

import logging
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from datetime import datetime

from playwright.async_api import Page

from browser.client import BrowserClient
from browser.element_handler import ElementHandler
from .perception import PerceptionRouter, DOMExtractor, VLMPerceiver
from persistence.constants import ActionType, ActionStatus, PerceptionMethod
from security.audit import AuditLogger, get_audit_logger

logger = logging.getLogger(__name__)


@dataclass
class ActionResult:
    """Result of a browser action"""
    action_type: ActionType
    status: ActionStatus
    target: Optional[str] = None
    duration_ms: int = 0
    perception_method: Optional[PerceptionMethod] = None
    confidence: float = 1.0
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    screenshot_path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_type": self.action_type.value,
            "status": self.status.value,
            "target": self.target,
            "duration_ms": self.duration_ms,
            "perception_method": self.perception_method.value if self.perception_method else None,
            "confidence": self.confidence,
            "data": self.data,
            "error": self.error,
        }


class BrowserSpecialist:
    """
    Browser Specialist - executes browser automation actions.

    Responsibilities:
    - Navigate to URLs
    - Find elements using hybrid perception (DOM + VLM)
    - Fill forms
    - Click buttons and links
    - Extract page data
    - Take screenshots
    - Handle authentication (with SecretsVault)

    Works under the Orchestrator's direction.
    """

    def __init__(
        self,
        browser_client: BrowserClient,
        vlm_perceiver: Optional[VLMPerceiver] = None,
        audit_logger: Optional[AuditLogger] = None
    ):
        """
        Initialize browser specialist.

        Args:
            browser_client: Browser client for page operations
            vlm_perceiver: Optional VLM perceiver for visual tasks
            audit_logger: Audit logger for compliance
        """
        self.browser_client = browser_client
        self.vlm_perceiver = vlm_perceiver
        self.audit_logger = audit_logger or get_audit_logger()
        self._element_handler: Optional[ElementHandler] = None
        self._perception_router: Optional[PerceptionRouter] = None

    @property
    def page(self) -> Page:
        """Get current page"""
        return self.browser_client.page

    @property
    def element_handler(self) -> ElementHandler:
        """Get or create element handler"""
        if self._element_handler is None:
            self._element_handler = ElementHandler(self.page)
        return self._element_handler

    @property
    def perception_router(self) -> PerceptionRouter:
        """Get or create perception router"""
        if self._perception_router is None:
            self._perception_router = PerceptionRouter(
                self.page,
                self.vlm_perceiver
            )
        return self._perception_router

    async def navigate(
        self,
        url: str,
        task_id: Optional[str] = None,
        wait_until: str = "networkidle"
    ) -> ActionResult:
        """
        Navigate to URL.

        Args:
            url: Target URL
            task_id: Task ID for logging
            wait_until: Wait condition

        Returns:
            ActionResult
        """
        start_time = datetime.now()
        try:
            await self.browser_client.navigate(url, wait_until=wait_until)

            duration = int((datetime.now() - start_time).total_seconds() * 1000)

            self.audit_logger.log_browser_action(
                action="navigate",
                status="SUCCESS",
                task_id=task_id,
                resource=url
            )

            return ActionResult(
                action_type=ActionType.NAVIGATE,
                status=ActionStatus.SUCCESS,
                target=url,
                duration_ms=duration,
                data={"final_url": self.page.url}
            )

        except Exception as e:
            duration = int((datetime.now() - start_time).total_seconds() * 1000)
            logger.error("Navigation failed: %s", e)

            self.audit_logger.log_browser_action(
                action="navigate",
                status="FAILURE",
                task_id=task_id,
                resource=url,
                metadata={"error": str(e)}
            )

            return ActionResult(
                action_type=ActionType.NAVIGATE,
                status=ActionStatus.FAILED,
                target=url,
                duration_ms=duration,
                error=str(e)
            )

    async def click(
        self,
        target: str,
        task_id: Optional[str] = None,
        use_vlm: bool = False
    ) -> ActionResult:
        """
        Click an element.

        Args:
            target: Element selector or description
            task_id: Task ID for logging
            use_vlm: Use VLM to find element

        Returns:
            ActionResult
        """
        start_time = datetime.now()
        perception_method = PerceptionMethod.DOM

        try:
            # Try to find element
            locator = None

            # First try DOM-based finding
            locator = await self.element_handler.find_button(text=target)

            if not locator:
                locator = await self.element_handler.find_link(text=target)

            if not locator:
                locator = await self.element_handler.find_element(
                    css_selector=target if target.startswith(('.', '#', '[')) else None,
                    text=target if not target.startswith(('.', '#', '[')) else None
                )

            # Fall back to VLM if needed
            if not locator and use_vlm and self.vlm_perceiver:
                perception_method = PerceptionMethod.VLM
                logger.info("Using VLM to find element: %s", target)
                screenshot = await self.page.screenshot()
                vlm_result = await self.vlm_perceiver.find_element(
                    screenshot, target
                )
                if vlm_result and vlm_result.get("found"):
                    # Try to click based on VLM guidance
                    # This is approximate - VLM provides location hints
                    logger.info("VLM found element at: %s", vlm_result.get("location"))

            if not locator:
                return ActionResult(
                    action_type=ActionType.CLICK,
                    status=ActionStatus.FAILED,
                    target=target,
                    duration_ms=int((datetime.now() - start_time).total_seconds() * 1000),
                    perception_method=perception_method,
                    error="Element not found"
                )

            # Click the element
            await self.element_handler.click_element(locator)

            duration = int((datetime.now() - start_time).total_seconds() * 1000)

            self.audit_logger.log_browser_action(
                action="click",
                status="SUCCESS",
                task_id=task_id,
                resource=target
            )

            return ActionResult(
                action_type=ActionType.CLICK,
                status=ActionStatus.SUCCESS,
                target=target,
                duration_ms=duration,
                perception_method=perception_method
            )

        except Exception as e:
            duration = int((datetime.now() - start_time).total_seconds() * 1000)
            logger.error("Click failed: %s", e)

            return ActionResult(
                action_type=ActionType.CLICK,
                status=ActionStatus.FAILED,
                target=target,
                duration_ms=duration,
                perception_method=perception_method,
                error=str(e)
            )

    async def fill(
        self,
        target: str,
        value: str,
        task_id: Optional[str] = None,
        clear_first: bool = True
    ) -> ActionResult:
        """
        Fill an input field.

        Args:
            target: Field selector, name, label, or placeholder
            value: Value to fill
            task_id: Task ID for logging
            clear_first: Clear existing value first

        Returns:
            ActionResult
        """
        start_time = datetime.now()

        try:
            # Find the input
            locator = await self.element_handler.find_input(
                field_name=target if not target.startswith(('.', '#', '[')) else None,
                label=target,
                placeholder=target,
                css_selector=target if target.startswith(('.', '#', '[')) else None
            )

            if not locator:
                return ActionResult(
                    action_type=ActionType.FILL,
                    status=ActionStatus.FAILED,
                    target=target,
                    duration_ms=int((datetime.now() - start_time).total_seconds() * 1000),
                    error="Input field not found"
                )

            # Fill the field
            success = await self.element_handler.fill_input(
                locator, value, clear_first=clear_first
            )

            duration = int((datetime.now() - start_time).total_seconds() * 1000)

            if success:
                self.audit_logger.log_browser_action(
                    action="fill",
                    status="SUCCESS",
                    task_id=task_id,
                    resource=target
                )

                return ActionResult(
                    action_type=ActionType.FILL,
                    status=ActionStatus.SUCCESS,
                    target=target,
                    duration_ms=duration,
                    perception_method=PerceptionMethod.DOM
                )
            else:
                return ActionResult(
                    action_type=ActionType.FILL,
                    status=ActionStatus.FAILED,
                    target=target,
                    duration_ms=duration,
                    error="Fill operation failed"
                )

        except Exception as e:
            duration = int((datetime.now() - start_time).total_seconds() * 1000)
            logger.error("Fill failed: %s", e)

            return ActionResult(
                action_type=ActionType.FILL,
                status=ActionStatus.FAILED,
                target=target,
                duration_ms=duration,
                error=str(e)
            )

    async def select(
        self,
        target: str,
        value: Optional[str] = None,
        label: Optional[str] = None,
        task_id: Optional[str] = None
    ) -> ActionResult:
        """
        Select option from dropdown.

        Args:
            target: Dropdown selector or label
            value: Option value
            label: Option visible text
            task_id: Task ID for logging

        Returns:
            ActionResult
        """
        start_time = datetime.now()

        try:
            locator = await self.element_handler.find_dropdown(
                field_name=target if not target.startswith(('.', '#', '[')) else None,
                label=target,
                css_selector=target if target.startswith(('.', '#', '[')) else None
            )

            if not locator:
                return ActionResult(
                    action_type=ActionType.SELECT,
                    status=ActionStatus.FAILED,
                    target=target,
                    duration_ms=int((datetime.now() - start_time).total_seconds() * 1000),
                    error="Dropdown not found"
                )

            success = await self.element_handler.select_option(
                locator, value=value, label=label
            )

            duration = int((datetime.now() - start_time).total_seconds() * 1000)

            if success:
                return ActionResult(
                    action_type=ActionType.SELECT,
                    status=ActionStatus.SUCCESS,
                    target=target,
                    duration_ms=duration,
                    data={"value": value, "label": label}
                )
            else:
                return ActionResult(
                    action_type=ActionType.SELECT,
                    status=ActionStatus.FAILED,
                    target=target,
                    duration_ms=duration,
                    error="Select operation failed"
                )

        except Exception as e:
            duration = int((datetime.now() - start_time).total_seconds() * 1000)
            return ActionResult(
                action_type=ActionType.SELECT,
                status=ActionStatus.FAILED,
                target=target,
                duration_ms=duration,
                error=str(e)
            )

    async def screenshot(
        self,
        path: Optional[str] = None,
        full_page: bool = False,
        task_id: Optional[str] = None
    ) -> ActionResult:
        """
        Take screenshot.

        Args:
            path: Optional file path
            full_page: Capture full scrollable page
            task_id: Task ID for logging

        Returns:
            ActionResult with screenshot bytes in data
        """
        import os
        import tempfile

        start_time = datetime.now()

        try:
            # Generate path if not provided
            if path is None:
                screenshots_dir = os.path.join(tempfile.gettempdir(), "spectacles_screenshots")
                os.makedirs(screenshots_dir, exist_ok=True)
                path = os.path.join(screenshots_dir, f"screenshot_{task_id or 'unknown'}_{int(start_time.timestamp())}.png")

            screenshot_bytes = await self.browser_client.screenshot(
                path=path,
                full_page=full_page
            )

            duration = int((datetime.now() - start_time).total_seconds() * 1000)

            return ActionResult(
                action_type=ActionType.SCREENSHOT,
                status=ActionStatus.SUCCESS,
                duration_ms=duration,
                screenshot_path=path,
                data={"bytes_length": len(screenshot_bytes)}
            )

        except Exception as e:
            duration = int((datetime.now() - start_time).total_seconds() * 1000)
            return ActionResult(
                action_type=ActionType.SCREENSHOT,
                status=ActionStatus.FAILED,
                duration_ms=duration,
                error=str(e)
            )

    async def extract_text(
        self,
        selector: Optional[str] = None,
        task_id: Optional[str] = None
    ) -> ActionResult:
        """
        Extract text from page or element.

        Args:
            selector: Optional element selector (body if None)
            task_id: Task ID for logging

        Returns:
            ActionResult with extracted text in data
        """
        start_time = datetime.now()

        try:
            if selector:
                text = await self.element_handler.get_element_text(selector)
            else:
                text = await self.element_handler.get_all_text_content()

            duration = int((datetime.now() - start_time).total_seconds() * 1000)

            return ActionResult(
                action_type=ActionType.EXTRACT,
                status=ActionStatus.SUCCESS,
                target=selector,
                duration_ms=duration,
                data={"text": text}
            )

        except Exception as e:
            duration = int((datetime.now() - start_time).total_seconds() * 1000)
            return ActionResult(
                action_type=ActionType.EXTRACT,
                status=ActionStatus.FAILED,
                target=selector,
                duration_ms=duration,
                error=str(e)
            )

    async def perceive_page(
        self,
        goal: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Tuple[PerceptionMethod, Dict[str, Any]]:
        """
        Perceive current page state.

        Args:
            goal: Current task goal
            context: Additional context

        Returns:
            Tuple of (perception method, perception data)
        """
        method, perception = await self.perception_router.perceive(goal, context)
        return method, perception.to_dict()

    async def get_page_info(self) -> Dict[str, Any]:
        """Get basic page information"""
        return {
            "url": self.page.url,
            "title": await self.page.title(),
        }

    async def wait_for_navigation(self, timeout: int = 30000):
        """Wait for page navigation to complete"""
        await self.browser_client.wait_for_navigation(timeout=timeout)

    async def get_storage_state(self) -> Dict[str, Any]:
        """Get browser storage state for session persistence"""
        return await self.browser_client.get_storage_state()

    # ==================== Phase 1: New Browser Interactions ====================

    async def keyboard(
        self,
        key: str,
        modifiers: Optional[List[str]] = None,
        task_id: Optional[str] = None
    ) -> ActionResult:
        """
        Press keyboard key or combination.

        Args:
            key: Key to press (e.g., "Enter", "Tab", "a", "Escape")
            modifiers: Modifier keys (e.g., ["Control", "Shift"])
            task_id: Task ID for logging

        Returns:
            ActionResult
        """
        start_time = datetime.now()

        try:
            # Build key combination string
            if modifiers:
                key_combo = "+".join(modifiers + [key])
            else:
                key_combo = key

            # Execute key press
            await self.page.keyboard.press(key_combo)

            duration = int((datetime.now() - start_time).total_seconds() * 1000)

            self.audit_logger.log_browser_action(
                action="keyboard",
                status="SUCCESS",
                task_id=task_id,
                resource=key_combo
            )

            return ActionResult(
                action_type=ActionType.KEYBOARD,
                status=ActionStatus.SUCCESS,
                target=key_combo,
                duration_ms=duration,
                data={"key": key, "modifiers": modifiers}
            )

        except Exception as e:
            duration = int((datetime.now() - start_time).total_seconds() * 1000)
            logger.error("Keyboard action failed: %s", e)

            return ActionResult(
                action_type=ActionType.KEYBOARD,
                status=ActionStatus.FAILED,
                target=key if not modifiers else f"{'+'.join(modifiers)}+{key}",
                duration_ms=duration,
                error=str(e)
            )

    async def hover(
        self,
        target: str,
        task_id: Optional[str] = None
    ) -> ActionResult:
        """
        Hover over an element (for tooltips, dropdowns, etc.).

        Args:
            target: Element selector or text
            task_id: Task ID for logging

        Returns:
            ActionResult
        """
        start_time = datetime.now()

        try:
            # Find element using various strategies
            locator = await self.element_handler.find_element(
                css_selector=target if target.startswith(('.', '#', '[')) else None,
                text=target if not target.startswith(('.', '#', '[')) else None
            )

            if not locator:
                # Try button/link
                locator = await self.element_handler.find_button(text=target)

            if not locator:
                locator = await self.element_handler.find_link(text=target)

            if not locator:
                return ActionResult(
                    action_type=ActionType.HOVER,
                    status=ActionStatus.FAILED,
                    target=target,
                    duration_ms=int((datetime.now() - start_time).total_seconds() * 1000),
                    error="Element not found"
                )

            # Hover over the element
            await locator.hover()

            duration = int((datetime.now() - start_time).total_seconds() * 1000)

            self.audit_logger.log_browser_action(
                action="hover",
                status="SUCCESS",
                task_id=task_id,
                resource=target
            )

            return ActionResult(
                action_type=ActionType.HOVER,
                status=ActionStatus.SUCCESS,
                target=target,
                duration_ms=duration,
                perception_method=PerceptionMethod.DOM
            )

        except Exception as e:
            duration = int((datetime.now() - start_time).total_seconds() * 1000)
            logger.error("Hover failed: %s", e)

            return ActionResult(
                action_type=ActionType.HOVER,
                status=ActionStatus.FAILED,
                target=target,
                duration_ms=duration,
                error=str(e)
            )

    async def scroll(
        self,
        direction: str = "down",
        amount: int = 500,
        target: Optional[str] = None,
        task_id: Optional[str] = None
    ) -> ActionResult:
        """
        Scroll page or element.

        Args:
            direction: Scroll direction ("up", "down", "left", "right")
            amount: Scroll amount in pixels
            target: Optional element selector to scroll within
            task_id: Task ID for logging

        Returns:
            ActionResult
        """
        start_time = datetime.now()

        try:
            if target:
                # Scroll within specific element
                locator = await self.element_handler.find_element(css_selector=target)
                if locator:
                    await locator.scroll_into_view_if_needed()
                    # Scroll within element
                    delta_x = amount if direction == "right" else (-amount if direction == "left" else 0)
                    delta_y = amount if direction == "down" else (-amount if direction == "up" else 0)
                    await locator.evaluate(
                        f"el => el.scrollBy({delta_x}, {delta_y})"
                    )
                else:
                    return ActionResult(
                        action_type=ActionType.SCROLL,
                        status=ActionStatus.FAILED,
                        target=target,
                        duration_ms=int((datetime.now() - start_time).total_seconds() * 1000),
                        error="Target element not found"
                    )
            else:
                # Scroll page
                delta_x = amount if direction == "right" else (-amount if direction == "left" else 0)
                delta_y = amount if direction == "down" else (-amount if direction == "up" else 0)
                await self.page.evaluate(f"window.scrollBy({delta_x}, {delta_y})")

            duration = int((datetime.now() - start_time).total_seconds() * 1000)

            self.audit_logger.log_browser_action(
                action="scroll",
                status="SUCCESS",
                task_id=task_id,
                resource=target or "page"
            )

            return ActionResult(
                action_type=ActionType.SCROLL,
                status=ActionStatus.SUCCESS,
                target=target or "page",
                duration_ms=duration,
                data={"direction": direction, "amount": amount}
            )

        except Exception as e:
            duration = int((datetime.now() - start_time).total_seconds() * 1000)
            logger.error("Scroll failed: %s", e)

            return ActionResult(
                action_type=ActionType.SCROLL,
                status=ActionStatus.FAILED,
                target=target or "page",
                duration_ms=duration,
                error=str(e)
            )

    async def drag_drop(
        self,
        source: str,
        target: str,
        task_id: Optional[str] = None
    ) -> ActionResult:
        """
        Drag element from source to target.

        Args:
            source: Source element selector or text
            target: Target element selector or text
            task_id: Task ID for logging

        Returns:
            ActionResult
        """
        start_time = datetime.now()

        try:
            # Find source element
            source_locator = await self.element_handler.find_element(
                css_selector=source if source.startswith(('.', '#', '[')) else None,
                text=source if not source.startswith(('.', '#', '[')) else None
            )

            if not source_locator:
                return ActionResult(
                    action_type=ActionType.DRAG_DROP,
                    status=ActionStatus.FAILED,
                    target=f"{source} -> {target}",
                    duration_ms=int((datetime.now() - start_time).total_seconds() * 1000),
                    error="Source element not found"
                )

            # Find target element
            target_locator = await self.element_handler.find_element(
                css_selector=target if target.startswith(('.', '#', '[')) else None,
                text=target if not target.startswith(('.', '#', '[')) else None
            )

            if not target_locator:
                return ActionResult(
                    action_type=ActionType.DRAG_DROP,
                    status=ActionStatus.FAILED,
                    target=f"{source} -> {target}",
                    duration_ms=int((datetime.now() - start_time).total_seconds() * 1000),
                    error="Target element not found"
                )

            # Perform drag and drop
            await source_locator.drag_to(target_locator)

            duration = int((datetime.now() - start_time).total_seconds() * 1000)

            self.audit_logger.log_browser_action(
                action="drag_drop",
                status="SUCCESS",
                task_id=task_id,
                resource=f"{source} -> {target}"
            )

            return ActionResult(
                action_type=ActionType.DRAG_DROP,
                status=ActionStatus.SUCCESS,
                target=f"{source} -> {target}",
                duration_ms=duration,
                perception_method=PerceptionMethod.DOM
            )

        except Exception as e:
            duration = int((datetime.now() - start_time).total_seconds() * 1000)
            logger.error("Drag and drop failed: %s", e)

            return ActionResult(
                action_type=ActionType.DRAG_DROP,
                status=ActionStatus.FAILED,
                target=f"{source} -> {target}",
                duration_ms=duration,
                error=str(e)
            )

    async def double_click(
        self,
        target: str,
        task_id: Optional[str] = None
    ) -> ActionResult:
        """
        Double-click an element.

        Args:
            target: Element selector or text
            task_id: Task ID for logging

        Returns:
            ActionResult
        """
        start_time = datetime.now()

        try:
            # Find element
            locator = await self.element_handler.find_element(
                css_selector=target if target.startswith(('.', '#', '[')) else None,
                text=target if not target.startswith(('.', '#', '[')) else None
            )

            if not locator:
                locator = await self.element_handler.find_button(text=target)

            if not locator:
                return ActionResult(
                    action_type=ActionType.DOUBLE_CLICK,
                    status=ActionStatus.FAILED,
                    target=target,
                    duration_ms=int((datetime.now() - start_time).total_seconds() * 1000),
                    error="Element not found"
                )

            # Double-click
            await locator.dblclick()

            duration = int((datetime.now() - start_time).total_seconds() * 1000)

            self.audit_logger.log_browser_action(
                action="double_click",
                status="SUCCESS",
                task_id=task_id,
                resource=target
            )

            return ActionResult(
                action_type=ActionType.DOUBLE_CLICK,
                status=ActionStatus.SUCCESS,
                target=target,
                duration_ms=duration,
                perception_method=PerceptionMethod.DOM
            )

        except Exception as e:
            duration = int((datetime.now() - start_time).total_seconds() * 1000)
            logger.error("Double-click failed: %s", e)

            return ActionResult(
                action_type=ActionType.DOUBLE_CLICK,
                status=ActionStatus.FAILED,
                target=target,
                duration_ms=duration,
                error=str(e)
            )

    async def right_click(
        self,
        target: str,
        task_id: Optional[str] = None
    ) -> ActionResult:
        """
        Right-click an element (context menu).

        Args:
            target: Element selector or text
            task_id: Task ID for logging

        Returns:
            ActionResult
        """
        start_time = datetime.now()

        try:
            # Find element
            locator = await self.element_handler.find_element(
                css_selector=target if target.startswith(('.', '#', '[')) else None,
                text=target if not target.startswith(('.', '#', '[')) else None
            )

            if not locator:
                locator = await self.element_handler.find_button(text=target)

            if not locator:
                return ActionResult(
                    action_type=ActionType.RIGHT_CLICK,
                    status=ActionStatus.FAILED,
                    target=target,
                    duration_ms=int((datetime.now() - start_time).total_seconds() * 1000),
                    error="Element not found"
                )

            # Right-click
            await locator.click(button="right")

            duration = int((datetime.now() - start_time).total_seconds() * 1000)

            self.audit_logger.log_browser_action(
                action="right_click",
                status="SUCCESS",
                task_id=task_id,
                resource=target
            )

            return ActionResult(
                action_type=ActionType.RIGHT_CLICK,
                status=ActionStatus.SUCCESS,
                target=target,
                duration_ms=duration,
                perception_method=PerceptionMethod.DOM
            )

        except Exception as e:
            duration = int((datetime.now() - start_time).total_seconds() * 1000)
            logger.error("Right-click failed: %s", e)

            return ActionResult(
                action_type=ActionType.RIGHT_CLICK,
                status=ActionStatus.FAILED,
                target=target,
                duration_ms=duration,
                error=str(e)
            )

    async def upload_file(
        self,
        input_selector: str,
        file_path: str,
        task_id: Optional[str] = None
    ) -> ActionResult:
        """
        Upload file to file input element.

        Args:
            input_selector: File input selector
            file_path: Path to file to upload
            task_id: Task ID for logging

        Returns:
            ActionResult
        """
        start_time = datetime.now()

        try:
            # Find file input
            locator = self.page.locator(input_selector)

            # Set files
            await locator.set_input_files(file_path)

            duration = int((datetime.now() - start_time).total_seconds() * 1000)

            self.audit_logger.log_browser_action(
                action="upload",
                status="SUCCESS",
                task_id=task_id,
                resource=input_selector,
                metadata={"file": file_path}
            )

            return ActionResult(
                action_type=ActionType.UPLOAD,
                status=ActionStatus.SUCCESS,
                target=input_selector,
                duration_ms=duration,
                data={"file_path": file_path}
            )

        except Exception as e:
            duration = int((datetime.now() - start_time).total_seconds() * 1000)
            logger.error("File upload failed: %s", e)

            return ActionResult(
                action_type=ActionType.UPLOAD,
                status=ActionStatus.FAILED,
                target=input_selector,
                duration_ms=duration,
                error=str(e)
            )

    async def download_file(
        self,
        trigger_selector: str,
        download_path: Optional[str] = None,
        task_id: Optional[str] = None
    ) -> ActionResult:
        """
        Trigger download and optionally save to path.

        Args:
            trigger_selector: Selector for download trigger (button/link)
            download_path: Optional path to save downloaded file
            task_id: Task ID for logging

        Returns:
            ActionResult with download info
        """
        start_time = datetime.now()

        try:
            # Set up download handler
            async with self.page.expect_download() as download_info:
                # Click the download trigger
                await self.page.locator(trigger_selector).click()

            download = await download_info.value

            # Save file if path provided
            if download_path:
                await download.save_as(download_path)
                saved_path = download_path
            else:
                saved_path = await download.path()

            duration = int((datetime.now() - start_time).total_seconds() * 1000)

            self.audit_logger.log_browser_action(
                action="download",
                status="SUCCESS",
                task_id=task_id,
                resource=trigger_selector,
                metadata={"saved_to": saved_path}
            )

            return ActionResult(
                action_type=ActionType.DOWNLOAD,
                status=ActionStatus.SUCCESS,
                target=trigger_selector,
                duration_ms=duration,
                data={
                    "filename": download.suggested_filename,
                    "saved_path": str(saved_path),
                    "url": download.url
                }
            )

        except Exception as e:
            duration = int((datetime.now() - start_time).total_seconds() * 1000)
            logger.error("File download failed: %s", e)

            return ActionResult(
                action_type=ActionType.DOWNLOAD,
                status=ActionStatus.FAILED,
                target=trigger_selector,
                duration_ms=duration,
                error=str(e)
            )

    async def wait_for(
        self,
        condition: str,
        target: Optional[str] = None,
        timeout_ms: int = 10000,
        task_id: Optional[str] = None
    ) -> ActionResult:
        """
        Wait for specific condition.

        Args:
            condition: Wait condition ("element", "hidden", "navigation", "network_idle", "load")
            target: Target selector (for element conditions)
            timeout_ms: Timeout in milliseconds
            task_id: Task ID for logging

        Returns:
            ActionResult
        """
        start_time = datetime.now()

        try:
            if condition == "element" and target:
                # Wait for element to be visible
                locator = self.page.locator(target)
                await locator.wait_for(state="visible", timeout=timeout_ms)

            elif condition == "hidden" and target:
                # Wait for element to be hidden
                locator = self.page.locator(target)
                await locator.wait_for(state="hidden", timeout=timeout_ms)

            elif condition == "navigation":
                # Wait for navigation
                await self.page.wait_for_load_state("networkidle", timeout=timeout_ms)

            elif condition == "network_idle":
                # Wait for network to be idle
                await self.page.wait_for_load_state("networkidle", timeout=timeout_ms)

            elif condition == "load":
                # Wait for page load
                await self.page.wait_for_load_state("load", timeout=timeout_ms)

            else:
                return ActionResult(
                    action_type=ActionType.WAIT_FOR,
                    status=ActionStatus.FAILED,
                    target=target,
                    duration_ms=int((datetime.now() - start_time).total_seconds() * 1000),
                    error=f"Unknown wait condition: {condition}"
                )

            duration = int((datetime.now() - start_time).total_seconds() * 1000)

            return ActionResult(
                action_type=ActionType.WAIT_FOR,
                status=ActionStatus.SUCCESS,
                target=target,
                duration_ms=duration,
                data={"condition": condition, "timeout_ms": timeout_ms}
            )

        except Exception as e:
            duration = int((datetime.now() - start_time).total_seconds() * 1000)
            logger.error("Wait failed: %s", e)

            return ActionResult(
                action_type=ActionType.WAIT_FOR,
                status=ActionStatus.FAILED,
                target=target,
                duration_ms=duration,
                error=str(e)
            )
