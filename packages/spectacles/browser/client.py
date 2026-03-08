"""
Spectacles Browser Client
Browserless CDP connection and browser lifecycle management

Adapted from merus-expert/browser/client.py
"""

import logging
from typing import Optional, Dict, Any
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

logger = logging.getLogger(__name__)


class BrowserClient:
    """
    Browser client using Browserless API or local Playwright.

    Manages browser lifecycle and provides context for automation.
    Supports both cloud (Browserless.io) and local execution modes.
    """

    def __init__(
        self,
        api_token: Optional[str] = None,
        endpoint: str = "wss://production-sfo.browserless.io",
        headless: bool = True,
        use_local: bool = False,
        viewport_width: int = 1920,
        viewport_height: int = 1080,
        user_agent: Optional[str] = None
    ):
        """
        Initialize browser client.

        Args:
            api_token: Browserless API token (not needed if use_local=True)
            endpoint: Browserless WebSocket endpoint
            headless: Run browser in headless mode
            use_local: Use local Playwright browser instead of Browserless
            viewport_width: Browser viewport width
            viewport_height: Browser viewport height
            user_agent: Custom user agent string
        """
        self.api_token = api_token
        self.endpoint = endpoint
        self.headless = headless
        self.use_local = use_local
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height
        self.user_agent = user_agent or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )

        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._session_id: Optional[str] = None

        mode = "local" if use_local else "Browserless"
        logger.info("BrowserClient initialized (mode=%s, headless=%s)", mode, headless)

    async def __aenter__(self):
        """Async context manager entry"""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.disconnect()

    async def connect(self) -> Page:
        """
        Establish connection to browser and create page.

        Uses Browserless cloud service or local Playwright browser.

        Returns:
            Playwright Page object

        Raises:
            Exception: If connection fails
        """
        try:
            # Start Playwright
            self._playwright = await async_playwright().start()

            if self.use_local:
                # Use local browser
                logger.info("Launching local Chromium browser...")
                self._browser = await self._playwright.chromium.launch(
                    headless=self.headless
                )
                logger.info("Local browser launched successfully")
            else:
                # Connect to Browserless via WebSocket using CDP
                if not self.api_token:
                    raise ValueError("Browserless API token required for cloud mode")

                logger.info("Connecting to Browserless...")
                # Add timeout parameter and stealth mode for stable sessions
                # Browserless timeout is in milliseconds, set to 5 minutes
                # Stealth mode helps avoid bot detection
                ws_url = f"{self.endpoint}?token={self.api_token}&timeout=300000&stealth=true"
                logger.info(f"Connecting via CDP to: {self.endpoint}?token=***&timeout=300000&stealth=true")

                self._browser = await self._playwright.chromium.connect_over_cdp(
                    ws_url
                )
                logger.info("Successfully connected to Browserless")

            # Create context with stealth settings
            self._context = await self._browser.new_context(
                viewport={"width": self.viewport_width, "height": self.viewport_height},
                user_agent=self.user_agent,
                # Stealth settings
                java_script_enabled=True,
                ignore_https_errors=True,
            )

            # Create page
            self._page = await self._context.new_page()

            logger.info("Browser page created successfully")
            return self._page

        except Exception as e:
            logger.error("Failed to connect to browser: %s", e, exc_info=True)
            await self.disconnect()
            raise

    async def disconnect(self):
        """Close browser connection and cleanup"""
        try:
            if self._page:
                await self._page.close()
                self._page = None

            if self._context:
                await self._context.close()
                self._context = None

            if self._browser:
                await self._browser.close()
                self._browser = None

            if self._playwright:
                await self._playwright.stop()
                self._playwright = None

            logger.info("Browser connection closed")

        except Exception as e:
            logger.warning("Error during disconnect: %s", e)

    @property
    def page(self) -> Page:
        """Get current page"""
        if not self._page:
            raise RuntimeError("Browser not connected. Call connect() first.")
        return self._page

    @property
    def context(self) -> BrowserContext:
        """Get browser context"""
        if not self._context:
            raise RuntimeError("Browser not connected. Call connect() first.")
        return self._context

    @property
    def is_connected(self) -> bool:
        """Check if browser is connected"""
        return self._page is not None and self._browser is not None

    async def navigate(
        self,
        url: str,
        wait_until: str = "networkidle",
        timeout: int = 30000
    ) -> None:
        """
        Navigate to URL.

        Args:
            url: URL to navigate to
            wait_until: Wait condition (networkidle, load, domcontentloaded)
            timeout: Timeout in milliseconds
        """
        logger.info("Navigating to %s", url)
        await self.page.goto(url, wait_until=wait_until, timeout=timeout)

    async def screenshot(
        self,
        path: Optional[str] = None,
        full_page: bool = False
    ) -> bytes:
        """
        Capture screenshot.

        Args:
            path: Optional file path to save screenshot
            full_page: Capture full scrollable page

        Returns:
            Screenshot bytes
        """
        if path:
            logger.info("Capturing screenshot: %s", path)
            screenshot_bytes = await self.page.screenshot(path=path, full_page=full_page)
        else:
            logger.info("Capturing screenshot to memory")
            screenshot_bytes = await self.page.screenshot(full_page=full_page)
        return screenshot_bytes

    async def get_cookies(self) -> list:
        """Get current cookies"""
        return await self.context.cookies()

    async def set_cookies(self, cookies: list):
        """Set cookies in context"""
        await self.context.add_cookies(cookies)

    async def get_current_url(self) -> str:
        """Get current page URL"""
        return self.page.url

    async def get_page_title(self) -> str:
        """Get current page title"""
        return await self.page.title()

    async def get_page_content(self) -> str:
        """Get page HTML content"""
        return await self.page.content()

    async def wait_for_navigation(
        self,
        wait_until: str = "networkidle",
        timeout: int = 30000
    ):
        """Wait for navigation to complete"""
        await self.page.wait_for_load_state(wait_until, timeout=timeout)

    async def get_storage_state(self) -> Dict[str, Any]:
        """
        Get storage state (cookies, localStorage) for session persistence.

        Returns:
            Dict with cookies and origins storage
        """
        return await self.context.storage_state()

    async def set_storage_state(self, storage_state: Dict[str, Any]):
        """
        Restore storage state from previous session.

        Args:
            storage_state: Dict from get_storage_state()
        """
        if storage_state.get("cookies"):
            await self.context.add_cookies(storage_state["cookies"])

    def get_live_view_url(self) -> Optional[str]:
        """
        Get Browserless Live View URL for human takeover (Tunnel Mode).

        Only available when using Browserless cloud mode.

        Returns:
            Live view URL or None if not available
        """
        if self.use_local:
            logger.warning("Live View not available in local mode")
            return None

        # Browserless Live View URL format
        # The session ID is embedded in the WebSocket connection
        if self._session_id:
            return f"https://production-sfo.browserless.io/live?token={self.api_token}&session={self._session_id}"

        # Fallback: Use basic live view
        return f"https://production-sfo.browserless.io/live?token={self.api_token}"
