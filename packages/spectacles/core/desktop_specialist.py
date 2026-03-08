"""
Spectacles Desktop Specialist
Executes desktop automation actions using PyAutoGUI and mss

The worker component that translates high-level directives into desktop commands.
Uses VLM + OCR perception for element finding on native applications.
"""

import logging
import asyncio
import os
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from datetime import datetime

from persistence.constants import ActionType, ActionStatus, PerceptionMethod
from security.audit import AuditLogger, get_audit_logger

logger = logging.getLogger(__name__)


@dataclass
class DesktopActionResult:
    """Result of a desktop action"""
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
            "screenshot_path": self.screenshot_path,
        }


class DesktopSpecialist:
    """
    Desktop Specialist - executes native desktop automation actions.

    Responsibilities:
    - Capture screen regions
    - Click at coordinates or locate elements visually
    - Type text and press keys
    - Open applications
    - Switch between windows
    - Scroll and drag operations
    - OCR text extraction

    Works under the Orchestrator's direction.
    Only available on VMs/local machines with display access.
    """

    def __init__(
        self,
        audit_logger: Optional[AuditLogger] = None,
        screenshot_dir: str = "./screenshots"
    ):
        """
        Initialize desktop specialist.

        Args:
            audit_logger: Audit logger for compliance
            screenshot_dir: Directory to store screenshots
        """
        self.audit_logger = audit_logger or get_audit_logger()
        self.screenshot_dir = screenshot_dir

        # Lazy imports for desktop components
        self._desktop_client = None
        self._window_manager = None
        self._desktop_perceiver = None

        # Ensure screenshot directory exists
        os.makedirs(screenshot_dir, exist_ok=True)

        logger.info("DesktopSpecialist initialized")

    @property
    def desktop_client(self):
        """Lazy-load desktop client"""
        if self._desktop_client is None:
            from desktop import DesktopClient
            self._desktop_client = DesktopClient()
        return self._desktop_client

    @property
    def window_manager(self):
        """Lazy-load window manager"""
        if self._window_manager is None:
            from desktop import WindowManager
            self._window_manager = WindowManager()
        return self._window_manager

    @property
    def desktop_perceiver(self):
        """Lazy-load desktop perceiver"""
        if self._desktop_perceiver is None:
            from .perception.desktop_perceiver import DesktopPerceiver
            self._desktop_perceiver = DesktopPerceiver()
        return self._desktop_perceiver

    async def screenshot(
        self,
        region: Optional[Tuple[int, int, int, int]] = None,
        save_path: Optional[str] = None,
        task_id: Optional[str] = None
    ) -> DesktopActionResult:
        """
        Capture screenshot of screen or region.

        Args:
            region: Optional (left, top, width, height) tuple
            save_path: Path to save screenshot
            task_id: Task ID for logging

        Returns:
            DesktopActionResult with screenshot path
        """
        start_time = datetime.now()
        try:
            from desktop.client import ScreenRegion

            screen_region = None
            if region:
                screen_region = ScreenRegion(
                    left=region[0],
                    top=region[1],
                    width=region[2],
                    height=region[3]
                )

            # Capture screen
            png_bytes = await self.desktop_client.capture_screen(region=screen_region)

            # Generate save path if not provided
            if not save_path:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                save_path = os.path.join(
                    self.screenshot_dir,
                    f"desktop_{task_id or 'manual'}_{timestamp}.png"
                )

            # Save screenshot
            with open(save_path, 'wb') as f:
                f.write(png_bytes)

            duration = int((datetime.now() - start_time).total_seconds() * 1000)

            self.audit_logger.log_browser_action(
                action="desktop_screenshot",
                status="SUCCESS",
                task_id=task_id,
                resource=save_path
            )

            return DesktopActionResult(
                action_type=ActionType.DESKTOP_SCREENSHOT,
                status=ActionStatus.SUCCESS,
                duration_ms=duration,
                screenshot_path=save_path,
                data={"size_bytes": len(png_bytes), "region": region}
            )

        except Exception as e:
            duration = int((datetime.now() - start_time).total_seconds() * 1000)
            logger.error("Screenshot failed: %s", e)

            self.audit_logger.log_browser_action(
                action="desktop_screenshot",
                status="FAILED",
                task_id=task_id,
                resource=str(e)
            )

            return DesktopActionResult(
                action_type=ActionType.DESKTOP_SCREENSHOT,
                status=ActionStatus.FAILED,
                duration_ms=duration,
                error=str(e)
            )

    async def click(
        self,
        x: Optional[int] = None,
        y: Optional[int] = None,
        button: str = "left",
        clicks: int = 1,
        task_id: Optional[str] = None
    ) -> DesktopActionResult:
        """
        Click at coordinates.

        Args:
            x: X coordinate (None for current position)
            y: Y coordinate (None for current position)
            button: Mouse button ("left", "right", "middle")
            clicks: Number of clicks
            task_id: Task ID for logging

        Returns:
            DesktopActionResult
        """
        start_time = datetime.now()
        try:
            await self.desktop_client.click(x=x, y=y, button=button, clicks=clicks)

            duration = int((datetime.now() - start_time).total_seconds() * 1000)

            target_desc = f"({x}, {y})" if x is not None else "current position"

            self.audit_logger.log_browser_action(
                action="desktop_click",
                status="SUCCESS",
                task_id=task_id,
                resource=target_desc
            )

            return DesktopActionResult(
                action_type=ActionType.DESKTOP_CLICK,
                status=ActionStatus.SUCCESS,
                target=target_desc,
                duration_ms=duration,
                data={"x": x, "y": y, "button": button, "clicks": clicks}
            )

        except Exception as e:
            duration = int((datetime.now() - start_time).total_seconds() * 1000)
            logger.error("Click failed: %s", e)

            return DesktopActionResult(
                action_type=ActionType.DESKTOP_CLICK,
                status=ActionStatus.FAILED,
                duration_ms=duration,
                error=str(e)
            )

    async def click_element(
        self,
        description: str,
        button: str = "left",
        clicks: int = 1,
        task_id: Optional[str] = None
    ) -> DesktopActionResult:
        """
        Click on an element by description using visual perception.

        Args:
            description: Description of element to click (e.g., "Save button", "File menu")
            button: Mouse button
            clicks: Number of clicks
            task_id: Task ID for logging

        Returns:
            DesktopActionResult
        """
        start_time = datetime.now()
        try:
            # Capture screen and perceive
            perception = await self.perceive_screen(
                goal=f"Find and click: {description}",
                task_id=task_id
            )

            # Look for element in perception results
            element_location = None
            confidence = 0.0

            if perception and "elements" in perception:
                for elem in perception["elements"]:
                    if description.lower() in elem.get("text", "").lower() or \
                       description.lower() in elem.get("description", "").lower():
                        element_location = elem.get("center", elem.get("bounds"))
                        confidence = elem.get("confidence", 0.8)
                        break

            if not element_location:
                return DesktopActionResult(
                    action_type=ActionType.DESKTOP_CLICK,
                    status=ActionStatus.FAILED,
                    target=description,
                    duration_ms=int((datetime.now() - start_time).total_seconds() * 1000),
                    error=f"Could not find element: {description}"
                )

            # Click at the location
            x, y = element_location[0], element_location[1]
            await self.desktop_client.click(x=x, y=y, button=button, clicks=clicks)

            duration = int((datetime.now() - start_time).total_seconds() * 1000)

            self.audit_logger.log_browser_action(
                action="desktop_click_element",
                status="SUCCESS",
                task_id=task_id,
                resource=description
            )

            return DesktopActionResult(
                action_type=ActionType.DESKTOP_CLICK,
                status=ActionStatus.SUCCESS,
                target=description,
                duration_ms=duration,
                perception_method=PerceptionMethod.VLM,
                confidence=confidence,
                data={"x": x, "y": y, "button": button, "clicks": clicks}
            )

        except Exception as e:
            duration = int((datetime.now() - start_time).total_seconds() * 1000)
            logger.error("Click element failed: %s", e)

            return DesktopActionResult(
                action_type=ActionType.DESKTOP_CLICK,
                status=ActionStatus.FAILED,
                target=description,
                duration_ms=duration,
                error=str(e)
            )

    async def type_text(
        self,
        text: str,
        target: Optional[str] = None,
        interval: float = 0.05,
        task_id: Optional[str] = None
    ) -> DesktopActionResult:
        """
        Type text, optionally clicking target first.

        Args:
            text: Text to type
            target: Optional element description to click first
            interval: Interval between keystrokes
            task_id: Task ID for logging

        Returns:
            DesktopActionResult
        """
        start_time = datetime.now()
        try:
            # Click target first if specified
            if target:
                click_result = await self.click_element(
                    description=target,
                    task_id=task_id
                )
                if click_result.status != ActionStatus.SUCCESS:
                    return DesktopActionResult(
                        action_type=ActionType.DESKTOP_TYPE,
                        status=ActionStatus.FAILED,
                        target=target,
                        duration_ms=int((datetime.now() - start_time).total_seconds() * 1000),
                        error=f"Could not click target: {click_result.error}"
                    )
                # Brief pause after click
                await asyncio.sleep(0.1)

            # Type the text
            await self.desktop_client.type_text(text, interval=interval)

            duration = int((datetime.now() - start_time).total_seconds() * 1000)

            # Mask sensitive text in logs
            display_text = text[:20] + "..." if len(text) > 20 else text

            self.audit_logger.log_browser_action(
                action="desktop_type",
                status="SUCCESS",
                task_id=task_id,
                resource=target or "current focus"
            )

            return DesktopActionResult(
                action_type=ActionType.DESKTOP_TYPE,
                status=ActionStatus.SUCCESS,
                target=target or "current focus",
                duration_ms=duration,
                data={"text_length": len(text), "target": target}
            )

        except Exception as e:
            duration = int((datetime.now() - start_time).total_seconds() * 1000)
            logger.error("Type text failed: %s", e)

            return DesktopActionResult(
                action_type=ActionType.DESKTOP_TYPE,
                status=ActionStatus.FAILED,
                target=target,
                duration_ms=duration,
                error=str(e)
            )

    async def press_key(
        self,
        key: str,
        modifiers: Optional[List[str]] = None,
        task_id: Optional[str] = None
    ) -> DesktopActionResult:
        """
        Press key or key combination.

        Args:
            key: Key to press (e.g., "enter", "tab", "a")
            modifiers: Modifier keys (e.g., ["ctrl", "shift"])
            task_id: Task ID for logging

        Returns:
            DesktopActionResult
        """
        start_time = datetime.now()
        try:
            await self.desktop_client.press_key(key, modifiers=modifiers)

            duration = int((datetime.now() - start_time).total_seconds() * 1000)

            key_desc = "+".join(modifiers + [key]) if modifiers else key

            self.audit_logger.log_browser_action(
                action="desktop_key",
                status="SUCCESS",
                task_id=task_id,
                resource=key_desc
            )

            return DesktopActionResult(
                action_type=ActionType.DESKTOP_KEY,
                status=ActionStatus.SUCCESS,
                target=key_desc,
                duration_ms=duration,
                data={"key": key, "modifiers": modifiers}
            )

        except Exception as e:
            duration = int((datetime.now() - start_time).total_seconds() * 1000)
            logger.error("Press key failed: %s", e)

            return DesktopActionResult(
                action_type=ActionType.DESKTOP_KEY,
                status=ActionStatus.FAILED,
                duration_ms=duration,
                error=str(e)
            )

    async def scroll(
        self,
        amount: int,
        x: Optional[int] = None,
        y: Optional[int] = None,
        task_id: Optional[str] = None
    ) -> DesktopActionResult:
        """
        Scroll at position.

        Args:
            amount: Scroll amount (positive = up, negative = down)
            x: X coordinate (None for current position)
            y: Y coordinate (None for current position)
            task_id: Task ID for logging

        Returns:
            DesktopActionResult
        """
        start_time = datetime.now()
        try:
            await self.desktop_client.scroll(amount, x=x, y=y)

            duration = int((datetime.now() - start_time).total_seconds() * 1000)

            self.audit_logger.log_browser_action(
                action="desktop_scroll",
                status="SUCCESS",
                task_id=task_id,
                resource=f"amount={amount}"
            )

            return DesktopActionResult(
                action_type=ActionType.DESKTOP_SCROLL,
                status=ActionStatus.SUCCESS,
                duration_ms=duration,
                data={"amount": amount, "x": x, "y": y}
            )

        except Exception as e:
            duration = int((datetime.now() - start_time).total_seconds() * 1000)
            logger.error("Scroll failed: %s", e)

            return DesktopActionResult(
                action_type=ActionType.DESKTOP_SCROLL,
                status=ActionStatus.FAILED,
                duration_ms=duration,
                error=str(e)
            )

    async def drag(
        self,
        start: Tuple[int, int],
        end: Tuple[int, int],
        duration: float = 0.5,
        task_id: Optional[str] = None
    ) -> DesktopActionResult:
        """
        Drag from start to end position.

        Args:
            start: Starting (x, y) coordinates
            end: Ending (x, y) coordinates
            duration: Drag duration in seconds
            task_id: Task ID for logging

        Returns:
            DesktopActionResult
        """
        start_time = datetime.now()
        try:
            await self.desktop_client.drag(start, end, duration=duration)

            action_duration = int((datetime.now() - start_time).total_seconds() * 1000)

            self.audit_logger.log_browser_action(
                action="desktop_drag",
                status="SUCCESS",
                task_id=task_id,
                resource=f"{start} -> {end}"
            )

            return DesktopActionResult(
                action_type=ActionType.DESKTOP_DRAG,
                status=ActionStatus.SUCCESS,
                duration_ms=action_duration,
                data={"start": start, "end": end, "drag_duration": duration}
            )

        except Exception as e:
            action_duration = int((datetime.now() - start_time).total_seconds() * 1000)
            logger.error("Drag failed: %s", e)

            return DesktopActionResult(
                action_type=ActionType.DESKTOP_DRAG,
                status=ActionStatus.FAILED,
                duration_ms=action_duration,
                error=str(e)
            )

    async def open_application(
        self,
        app_name: str,
        wait_seconds: float = 3.0,
        task_id: Optional[str] = None
    ) -> DesktopActionResult:
        """
        Open application by name.

        Args:
            app_name: Application name or path
            wait_seconds: Time to wait for app to open
            task_id: Task ID for logging

        Returns:
            DesktopActionResult
        """
        import platform
        import subprocess

        start_time = datetime.now()
        try:
            system = platform.system().lower()

            if system == "windows":
                # Windows: use start command
                subprocess.Popen(["start", app_name], shell=True)
            elif system == "darwin":
                # macOS: use open command
                subprocess.Popen(["open", "-a", app_name])
            else:
                # Linux: try to run directly
                subprocess.Popen([app_name], start_new_session=True)

            # Wait for app to open
            await asyncio.sleep(wait_seconds)

            duration = int((datetime.now() - start_time).total_seconds() * 1000)

            self.audit_logger.log_browser_action(
                action="open_app",
                status="SUCCESS",
                task_id=task_id,
                resource=app_name
            )

            return DesktopActionResult(
                action_type=ActionType.OPEN_APP,
                status=ActionStatus.SUCCESS,
                target=app_name,
                duration_ms=duration,
                data={"app_name": app_name, "wait_seconds": wait_seconds}
            )

        except Exception as e:
            duration = int((datetime.now() - start_time).total_seconds() * 1000)
            logger.error("Open application failed: %s", e)

            return DesktopActionResult(
                action_type=ActionType.OPEN_APP,
                status=ActionStatus.FAILED,
                target=app_name,
                duration_ms=duration,
                error=str(e)
            )

    async def switch_to_window(
        self,
        window_title: str,
        partial: bool = True,
        task_id: Optional[str] = None
    ) -> DesktopActionResult:
        """
        Switch to window by title.

        Args:
            window_title: Window title to switch to
            partial: Allow partial title match
            task_id: Task ID for logging

        Returns:
            DesktopActionResult
        """
        start_time = datetime.now()
        try:
            success = await self.window_manager.focus_window(window_title, partial=partial)

            duration = int((datetime.now() - start_time).total_seconds() * 1000)

            if success:
                self.audit_logger.log_browser_action(
                    action="switch_window",
                    status="SUCCESS",
                    task_id=task_id,
                    resource=window_title
                )

                return DesktopActionResult(
                    action_type=ActionType.SWITCH_WINDOW,
                    status=ActionStatus.SUCCESS,
                    target=window_title,
                    duration_ms=duration,
                    data={"partial_match": partial}
                )
            else:
                return DesktopActionResult(
                    action_type=ActionType.SWITCH_WINDOW,
                    status=ActionStatus.FAILED,
                    target=window_title,
                    duration_ms=duration,
                    error=f"Window not found: {window_title}"
                )

        except Exception as e:
            duration = int((datetime.now() - start_time).total_seconds() * 1000)
            logger.error("Switch window failed: %s", e)

            return DesktopActionResult(
                action_type=ActionType.SWITCH_WINDOW,
                status=ActionStatus.FAILED,
                target=window_title,
                duration_ms=duration,
                error=str(e)
            )

    async def list_windows(
        self,
        task_id: Optional[str] = None
    ) -> DesktopActionResult:
        """
        List all visible windows.

        Args:
            task_id: Task ID for logging

        Returns:
            DesktopActionResult with window list
        """
        start_time = datetime.now()
        try:
            windows = await self.window_manager.list_windows()

            duration = int((datetime.now() - start_time).total_seconds() * 1000)

            window_list = [w.to_dict() for w in windows]

            return DesktopActionResult(
                action_type=ActionType.SWITCH_WINDOW,  # Reuse for listing
                status=ActionStatus.SUCCESS,
                duration_ms=duration,
                data={"windows": window_list, "count": len(window_list)}
            )

        except Exception as e:
            duration = int((datetime.now() - start_time).total_seconds() * 1000)
            logger.error("List windows failed: %s", e)

            return DesktopActionResult(
                action_type=ActionType.SWITCH_WINDOW,
                status=ActionStatus.FAILED,
                duration_ms=duration,
                error=str(e)
            )

    async def perceive_screen(
        self,
        goal: str,
        region: Optional[Tuple[int, int, int, int]] = None,
        use_ocr: bool = True,
        use_vlm: bool = True,
        task_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Perceive screen contents using VLM and/or OCR.

        Args:
            goal: What we're trying to understand/find
            region: Optional region to perceive
            use_ocr: Use OCR for text extraction
            use_vlm: Use VLM for visual understanding
            task_id: Task ID for logging

        Returns:
            Perception results dict
        """
        try:
            # Capture screenshot
            screenshot_result = await self.screenshot(
                region=region,
                task_id=task_id
            )

            if screenshot_result.status != ActionStatus.SUCCESS:
                return {"error": "Screenshot failed", "elements": []}

            # Use desktop perceiver
            perception = await self.desktop_perceiver.perceive(
                screenshot_path=screenshot_result.screenshot_path,
                goal=goal,
                use_ocr=use_ocr,
                use_vlm=use_vlm
            )

            return perception

        except Exception as e:
            logger.error("Perceive screen failed: %s", e)
            return {"error": str(e), "elements": []}

    async def get_mouse_position(self) -> Tuple[int, int]:
        """Get current mouse position"""
        pos = await self.desktop_client.get_mouse_position()
        return (pos.x, pos.y)

    async def get_screen_size(self) -> Tuple[int, int]:
        """Get screen dimensions"""
        return await self.desktop_client.get_screen_size()

    async def get_active_window(self) -> Optional[Dict[str, Any]]:
        """Get currently active window info"""
        window = await self.window_manager.get_active_window()
        return window.to_dict() if window else None

    def close(self):
        """Close resources"""
        if self._desktop_client:
            self._desktop_client.close()
        logger.info("DesktopSpecialist closed")

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.close()
