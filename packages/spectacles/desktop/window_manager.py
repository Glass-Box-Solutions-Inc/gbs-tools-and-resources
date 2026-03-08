"""
Spectacles Window Manager
Window detection and management using PyGetWindow
"""

import logging
import asyncio
import platform
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class WindowInfo:
    """Window information"""
    title: str
    left: int
    top: int
    width: int
    height: int
    is_active: bool = False
    is_minimized: bool = False
    is_maximized: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "left": self.left,
            "top": self.top,
            "width": self.width,
            "height": self.height,
            "is_active": self.is_active,
            "is_minimized": self.is_minimized,
            "is_maximized": self.is_maximized,
        }

    @property
    def bounds(self) -> Tuple[int, int, int, int]:
        """Return (left, top, width, height)"""
        return (self.left, self.top, self.width, self.height)


class WindowManager:
    """
    Window detection and management.

    Uses PyGetWindow for cross-platform window management.
    Note: Full functionality on Windows, limited on other platforms.
    """

    def __init__(self):
        """Initialize window manager"""
        self._system = platform.system().lower()

        try:
            import pygetwindow as gw
            self.gw = gw
        except ImportError as e:
            logger.warning("PyGetWindow not available: %s", e)
            self.gw = None

        logger.info("WindowManager initialized on %s", self._system)

    async def list_windows(self) -> List[WindowInfo]:
        """
        List all visible windows.

        Returns:
            List of WindowInfo objects
        """
        if not self.gw:
            return []

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._list_windows_sync)

    def _list_windows_sync(self) -> List[WindowInfo]:
        """Synchronous window listing"""
        windows = []

        try:
            all_windows = self.gw.getAllWindows()

            for win in all_windows:
                # Skip empty titles
                if not win.title:
                    continue

                try:
                    info = WindowInfo(
                        title=win.title,
                        left=win.left,
                        top=win.top,
                        width=win.width,
                        height=win.height,
                        is_active=win.isActive,
                        is_minimized=win.isMinimized,
                        is_maximized=win.isMaximized,
                    )
                    windows.append(info)
                except Exception as e:
                    logger.debug("Error getting window info: %s", e)
                    continue

        except Exception as e:
            logger.error("Error listing windows: %s", e)

        return windows

    async def find_window(
        self,
        title: Optional[str] = None,
        partial: bool = True
    ) -> Optional[WindowInfo]:
        """
        Find window by title.

        Args:
            title: Window title to search for
            partial: Allow partial title match

        Returns:
            WindowInfo if found, None otherwise
        """
        if not self.gw or not title:
            return None

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self._find_window_sync,
            title,
            partial
        )

    def _find_window_sync(self, title: str, partial: bool) -> Optional[WindowInfo]:
        """Synchronous window finding"""
        try:
            if partial:
                # Get all windows and filter
                all_windows = self.gw.getAllWindows()
                title_lower = title.lower()

                for win in all_windows:
                    if win.title and title_lower in win.title.lower():
                        return WindowInfo(
                            title=win.title,
                            left=win.left,
                            top=win.top,
                            width=win.width,
                            height=win.height,
                            is_active=win.isActive,
                            is_minimized=win.isMinimized,
                            is_maximized=win.isMaximized,
                        )
            else:
                # Exact match
                windows = self.gw.getWindowsWithTitle(title)
                if windows:
                    win = windows[0]
                    return WindowInfo(
                        title=win.title,
                        left=win.left,
                        top=win.top,
                        width=win.width,
                        height=win.height,
                        is_active=win.isActive,
                        is_minimized=win.isMinimized,
                        is_maximized=win.isMaximized,
                    )

        except Exception as e:
            logger.error("Error finding window '%s': %s", title, e)

        return None

    async def get_active_window(self) -> Optional[WindowInfo]:
        """
        Get currently focused/active window.

        Returns:
            WindowInfo for active window, None if error
        """
        if not self.gw:
            return None

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_active_window_sync)

    def _get_active_window_sync(self) -> Optional[WindowInfo]:
        """Synchronous active window detection"""
        try:
            win = self.gw.getActiveWindow()
            if win:
                return WindowInfo(
                    title=win.title,
                    left=win.left,
                    top=win.top,
                    width=win.width,
                    height=win.height,
                    is_active=True,
                    is_minimized=win.isMinimized,
                    is_maximized=win.isMaximized,
                )
        except Exception as e:
            logger.error("Error getting active window: %s", e)

        return None

    async def focus_window(self, title: str, partial: bool = True) -> bool:
        """
        Bring window to foreground.

        Args:
            title: Window title
            partial: Allow partial title match

        Returns:
            True if successful
        """
        if not self.gw:
            return False

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self._focus_window_sync,
            title,
            partial
        )

    def _focus_window_sync(self, title: str, partial: bool) -> bool:
        """Synchronous window focusing"""
        try:
            if partial:
                all_windows = self.gw.getAllWindows()
                title_lower = title.lower()

                for win in all_windows:
                    if win.title and title_lower in win.title.lower():
                        win.activate()
                        return True
            else:
                windows = self.gw.getWindowsWithTitle(title)
                if windows:
                    windows[0].activate()
                    return True

        except Exception as e:
            logger.error("Error focusing window '%s': %s", title, e)

        return False

    async def minimize_window(self, title: str, partial: bool = True) -> bool:
        """Minimize window"""
        if not self.gw:
            return False

        loop = asyncio.get_event_loop()

        def minimize():
            try:
                if partial:
                    all_windows = self.gw.getAllWindows()
                    title_lower = title.lower()
                    for win in all_windows:
                        if win.title and title_lower in win.title.lower():
                            win.minimize()
                            return True
                else:
                    windows = self.gw.getWindowsWithTitle(title)
                    if windows:
                        windows[0].minimize()
                        return True
            except Exception as e:
                logger.error("Error minimizing window: %s", e)
            return False

        return await loop.run_in_executor(None, minimize)

    async def maximize_window(self, title: str, partial: bool = True) -> bool:
        """Maximize window"""
        if not self.gw:
            return False

        loop = asyncio.get_event_loop()

        def maximize():
            try:
                if partial:
                    all_windows = self.gw.getAllWindows()
                    title_lower = title.lower()
                    for win in all_windows:
                        if win.title and title_lower in win.title.lower():
                            win.maximize()
                            return True
                else:
                    windows = self.gw.getWindowsWithTitle(title)
                    if windows:
                        windows[0].maximize()
                        return True
            except Exception as e:
                logger.error("Error maximizing window: %s", e)
            return False

        return await loop.run_in_executor(None, maximize)

    async def restore_window(self, title: str, partial: bool = True) -> bool:
        """Restore minimized/maximized window to normal state"""
        if not self.gw:
            return False

        loop = asyncio.get_event_loop()

        def restore():
            try:
                if partial:
                    all_windows = self.gw.getAllWindows()
                    title_lower = title.lower()
                    for win in all_windows:
                        if win.title and title_lower in win.title.lower():
                            win.restore()
                            return True
                else:
                    windows = self.gw.getWindowsWithTitle(title)
                    if windows:
                        windows[0].restore()
                        return True
            except Exception as e:
                logger.error("Error restoring window: %s", e)
            return False

        return await loop.run_in_executor(None, restore)

    async def move_window(
        self,
        title: str,
        x: int,
        y: int,
        partial: bool = True
    ) -> bool:
        """
        Move window to position.

        Args:
            title: Window title
            x: New X position
            y: New Y position
            partial: Allow partial title match

        Returns:
            True if successful
        """
        if not self.gw:
            return False

        loop = asyncio.get_event_loop()

        def move():
            try:
                if partial:
                    all_windows = self.gw.getAllWindows()
                    title_lower = title.lower()
                    for win in all_windows:
                        if win.title and title_lower in win.title.lower():
                            win.moveTo(x, y)
                            return True
                else:
                    windows = self.gw.getWindowsWithTitle(title)
                    if windows:
                        windows[0].moveTo(x, y)
                        return True
            except Exception as e:
                logger.error("Error moving window: %s", e)
            return False

        return await loop.run_in_executor(None, move)

    async def resize_window(
        self,
        title: str,
        width: int,
        height: int,
        partial: bool = True
    ) -> bool:
        """
        Resize window.

        Args:
            title: Window title
            width: New width
            height: New height
            partial: Allow partial title match

        Returns:
            True if successful
        """
        if not self.gw:
            return False

        loop = asyncio.get_event_loop()

        def resize():
            try:
                if partial:
                    all_windows = self.gw.getAllWindows()
                    title_lower = title.lower()
                    for win in all_windows:
                        if win.title and title_lower in win.title.lower():
                            win.resizeTo(width, height)
                            return True
                else:
                    windows = self.gw.getWindowsWithTitle(title)
                    if windows:
                        windows[0].resizeTo(width, height)
                        return True
            except Exception as e:
                logger.error("Error resizing window: %s", e)
            return False

        return await loop.run_in_executor(None, resize)

    async def get_window_bounds(
        self,
        title: str,
        partial: bool = True
    ) -> Optional[Tuple[int, int, int, int]]:
        """
        Get window position and size.

        Args:
            title: Window title
            partial: Allow partial title match

        Returns:
            Tuple of (left, top, width, height) or None
        """
        window = await self.find_window(title, partial)
        if window:
            return window.bounds
        return None
