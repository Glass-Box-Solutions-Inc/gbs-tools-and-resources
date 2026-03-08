"""
Spectacles Desktop Client
Screen capture and input simulation using mss and PyAutoGUI
"""

import logging
import asyncio
import io
from typing import Optional, Tuple, List, Dict, Any
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class ScreenRegion:
    """Screen region definition"""
    left: int
    top: int
    width: int
    height: int

    def to_dict(self) -> Dict[str, int]:
        return {
            "left": self.left,
            "top": self.top,
            "width": self.width,
            "height": self.height
        }

    @classmethod
    def from_tuple(cls, t: Tuple[int, int, int, int]) -> 'ScreenRegion':
        return cls(left=t[0], top=t[1], width=t[2], height=t[3])


@dataclass
class MousePosition:
    """Mouse position"""
    x: int
    y: int

    def to_tuple(self) -> Tuple[int, int]:
        return (self.x, self.y)


class DesktopClient:
    """
    Desktop automation client using mss for capture, PyAutoGUI for input.

    Libraries:
    - mss: Fast cross-platform screen capture
    - PyAutoGUI: Mouse/keyboard input simulation

    Note: Only loads on systems with display access. Will fail on Cloud Run.
    """

    def __init__(
        self,
        capture_region: Optional[ScreenRegion] = None,
        failsafe: bool = True,
        pause: float = 0.1
    ):
        """
        Initialize desktop client.

        Args:
            capture_region: Optional region to limit capture area
            failsafe: Enable PyAutoGUI failsafe (move mouse to corner to abort)
            pause: Pause between PyAutoGUI actions in seconds
        """
        # Lazy imports to avoid loading on Cloud Run
        try:
            import mss
            import pyautogui
        except ImportError as e:
            raise RuntimeError(
                f"Desktop automation libraries not available: {e}. "
                "Install with: pip install mss pyautogui"
            )

        # Don't store mss instance - create per-thread to avoid threading issues
        self._mss_module = mss
        self.pyautogui = pyautogui
        self.capture_region = capture_region

        # Configure PyAutoGUI safety
        pyautogui.FAILSAFE = failsafe
        pyautogui.PAUSE = pause

        logger.info(
            "DesktopClient initialized (failsafe=%s, pause=%.2f)",
            failsafe, pause
        )

    async def capture_screen(
        self,
        region: Optional[ScreenRegion] = None,
        monitor: int = 0
    ) -> bytes:
        """
        Capture screen or region as PNG bytes.

        Args:
            region: Optional region to capture (uses full screen if None)
            monitor: Monitor number (0 = all monitors, 1+ = specific monitor)

        Returns:
            PNG image as bytes
        """
        # Run in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self._capture_screen_sync,
            region,
            monitor
        )

    def _capture_screen_sync(
        self,
        region: Optional[ScreenRegion],
        monitor: int
    ) -> bytes:
        """Synchronous screen capture"""
        import mss
        import mss.tools

        # Create new mss instance for this thread (mss uses thread-local storage)
        with mss.mss() as sct:
            if region:
                capture_area = {
                    "left": region.left,
                    "top": region.top,
                    "width": region.width,
                    "height": region.height
                }
            else:
                # Use specified monitor or first monitor
                capture_area = sct.monitors[monitor] if monitor > 0 else sct.monitors[0]

            # Capture
            screenshot = sct.grab(capture_area)

            # Convert to PNG bytes
            png_bytes = mss.tools.to_png(screenshot.rgb, screenshot.size)
            return png_bytes

    async def get_screen_size(self) -> Tuple[int, int]:
        """
        Get screen dimensions.

        Returns:
            Tuple of (width, height)
        """
        size = self.pyautogui.size()
        return (size.width, size.height)

    async def get_mouse_position(self) -> MousePosition:
        """
        Get current mouse position.

        Returns:
            MousePosition
        """
        pos = self.pyautogui.position()
        return MousePosition(x=pos.x, y=pos.y)

    async def move_mouse(
        self,
        x: int,
        y: int,
        duration: float = 0.5
    ):
        """
        Move mouse to coordinates.

        Args:
            x: X coordinate
            y: Y coordinate
            duration: Movement duration in seconds
        """
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: self.pyautogui.moveTo(x, y, duration=duration)
        )
        logger.debug("Mouse moved to (%d, %d)", x, y)

    async def click(
        self,
        x: Optional[int] = None,
        y: Optional[int] = None,
        button: str = "left",
        clicks: int = 1
    ):
        """
        Click at coordinates or current position.

        Args:
            x: X coordinate (None = current position)
            y: Y coordinate (None = current position)
            button: Mouse button ("left", "right", "middle")
            clicks: Number of clicks
        """
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: self.pyautogui.click(x=x, y=y, button=button, clicks=clicks)
        )
        logger.debug("Clicked at (%s, %s) button=%s clicks=%d", x, y, button, clicks)

    async def double_click(
        self,
        x: Optional[int] = None,
        y: Optional[int] = None
    ):
        """Double-click at coordinates"""
        await self.click(x, y, clicks=2)

    async def right_click(
        self,
        x: Optional[int] = None,
        y: Optional[int] = None
    ):
        """Right-click at coordinates"""
        await self.click(x, y, button="right")

    async def type_text(
        self,
        text: str,
        interval: float = 0.05
    ):
        """
        Type text with keyboard.

        Args:
            text: Text to type
            interval: Interval between keystrokes in seconds
        """
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: self.pyautogui.typewrite(text, interval=interval)
        )
        logger.debug("Typed text: %s", text[:20] + "..." if len(text) > 20 else text)

    async def press_key(
        self,
        key: str,
        modifiers: Optional[List[str]] = None
    ):
        """
        Press key or key combination.

        Args:
            key: Key to press (e.g., "enter", "tab", "a")
            modifiers: Modifier keys (e.g., ["ctrl", "shift"])
        """
        loop = asyncio.get_event_loop()

        if modifiers:
            # Hold modifiers and press key
            await loop.run_in_executor(
                None,
                lambda: self.pyautogui.hotkey(*modifiers, key)
            )
        else:
            await loop.run_in_executor(
                None,
                lambda: self.pyautogui.press(key)
            )

        key_desc = "+".join(modifiers + [key]) if modifiers else key
        logger.debug("Pressed key: %s", key_desc)

    async def scroll(
        self,
        amount: int,
        x: Optional[int] = None,
        y: Optional[int] = None
    ):
        """
        Scroll at position.

        Args:
            amount: Scroll amount (positive = up, negative = down)
            x: X coordinate (None = current position)
            y: Y coordinate (None = current position)
        """
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: self.pyautogui.scroll(amount, x=x, y=y)
        )
        logger.debug("Scrolled %d at (%s, %s)", amount, x, y)

    async def drag(
        self,
        start: Tuple[int, int],
        end: Tuple[int, int],
        duration: float = 0.5,
        button: str = "left"
    ):
        """
        Drag from start to end position.

        Args:
            start: Starting (x, y) coordinates
            end: Ending (x, y) coordinates
            duration: Drag duration in seconds
            button: Mouse button to hold
        """
        loop = asyncio.get_event_loop()

        # Move to start
        await self.move_mouse(start[0], start[1], duration=0.1)

        # Drag to end
        await loop.run_in_executor(
            None,
            lambda: self.pyautogui.drag(
                end[0] - start[0],
                end[1] - start[1],
                duration=duration,
                button=button
            )
        )
        logger.debug("Dragged from %s to %s", start, end)

    async def locate_on_screen(
        self,
        image_path: str,
        confidence: float = 0.9,
        region: Optional[ScreenRegion] = None
    ) -> Optional[ScreenRegion]:
        """
        Locate image on screen using template matching.

        Args:
            image_path: Path to template image
            confidence: Match confidence (0-1)
            region: Optional region to search in

        Returns:
            ScreenRegion if found, None otherwise
        """
        loop = asyncio.get_event_loop()

        region_tuple = None
        if region:
            region_tuple = (region.left, region.top, region.width, region.height)

        try:
            result = await loop.run_in_executor(
                None,
                lambda: self.pyautogui.locateOnScreen(
                    image_path,
                    confidence=confidence,
                    region=region_tuple
                )
            )

            if result:
                return ScreenRegion(
                    left=result.left,
                    top=result.top,
                    width=result.width,
                    height=result.height
                )
            return None

        except Exception as e:
            logger.error("Image location failed: %s", e)
            return None

    async def get_monitors(self) -> List[Dict[str, Any]]:
        """
        Get list of available monitors.

        Returns:
            List of monitor info dicts
        """
        monitors = []
        # Create temporary mss instance to get monitor info
        with self._mss_module.mss() as sct:
            for i, mon in enumerate(sct.monitors):
                monitors.append({
                    "index": i,
                    "left": mon.get("left", 0),
                    "top": mon.get("top", 0),
                    "width": mon.get("width", 0),
                    "height": mon.get("height", 0),
                    "is_primary": i == 1  # Monitor 0 is all, 1 is usually primary
                })
        return monitors

    def close(self):
        """Close resources"""
        # No persistent mss instance to close anymore
        logger.info("DesktopClient closed")

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.close()
