"""
MerusCase Browser Client
Browserless CDP connection and browser lifecycle management
"""

import logging
from typing import Optional
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

logger = logging.getLogger(__name__)


class MerusCaseBrowserClient:
    """
    Browser client using Browserless API.

    Manages browser lifecycle and provides context for automation.
    """

    def __init__(
        self,
        api_token: str = None,
        endpoint: str = "wss://production-sfo.browserless.io",
        headless: bool = True,
        use_local: bool = False
    ):
        """
        Initialize browser client.

        Args:
            api_token: Browserless API token (not needed if use_local=True)
            endpoint: Browserless WebSocket endpoint
            headless: Run browser in headless mode
            use_local: Use local Playwright browser instead of Browserless
        """
        self.api_token = api_token
        self.endpoint = endpoint
        self.headless = headless
        self.use_local = use_local

        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

        mode = "local" if use_local else "Browserless"
        logger.info("MerusCaseBrowserClient initialized (mode=%s, headless=%s)", mode, headless)

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
                logger.info("Connecting to Browserless...")
                ws_url = f"{self.endpoint}?token={self.api_token}"
                logger.info(f"Connecting via CDP to: {self.endpoint}?token=***")

                self._browser = await self._playwright.chromium.connect_over_cdp(
                    ws_url,
                    headers={"Authorization": f"Bearer {self.api_token}"}
                )
                logger.info("Successfully connected to Browserless")

            # Create context
            self._context = await self._browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )

            # Create page
            self._page = await self._context.new_page()

            logger.info("Browser page created successfully")
            return self._page

        except Exception as e:
            logger.error("Failed to connect to Browserless: %s", e, exc_info=True)
            await self.disconnect()
            raise

    async def disconnect(self):
        """Close browser connection and cleanup"""
        try:
            if self._page:
                await self._page.close()

            if self._context:
                await self._context.close()

            if self._browser:
                await self._browser.close()

            if self._playwright:
                await self._playwright.stop()

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

    async def navigate(self, url: str, wait_until: str = 'networkidle') -> None:
        """
        Navigate to URL.

        Args:
            url: URL to navigate to
            wait_until: Wait condition (networkidle, load, domcontentloaded)
        """
        logger.info("Navigating to %s", url)
        await self.page.goto(url, wait_until=wait_until, timeout=30000)

    async def screenshot(
        self,
        path: str,
        full_page: bool = False
    ) -> bytes:
        """
        Capture screenshot.

        Args:
            path: File path to save screenshot
            full_page: Capture full scrollable page

        Returns:
            Screenshot bytes
        """
        logger.info("Capturing screenshot: %s", path)
        screenshot_bytes = await self.page.screenshot(path=path, full_page=full_page)
        return screenshot_bytes

    async def get_cookies(self) -> list:
        """Get current cookies"""
        return await self.context.cookies()

    async def set_cookies(self, cookies: list):
        """Set cookies in context"""
        await self.context.add_cookies(cookies)
