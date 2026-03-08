"""
Check My Apps section for existing OAuth tokens.
"""

import asyncio
import logging
import os
from pathlib import Path
from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

EMAIL = os.getenv("MERUSCASE_EMAIL", "Alex@adjudica.ai")
PASSWORD = os.getenv("MERUSCASE_PASSWORD")
BASE_URL = "https://meruscase.com"

SCREENSHOT_DIR = Path("screenshots/my_apps")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


async def check_my_apps():
    """Check My Apps for existing token."""

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()

        try:
            # Login
            logger.info("Logging in...")
            await page.goto(f"{BASE_URL}/users/login")
            await page.wait_for_load_state("networkidle")
            await page.fill("input[name='email'], input[type='email'], #email", EMAIL)
            await page.fill("input[name='password'], input[type='password'], #password", PASSWORD)
            await page.click("button[type='submit'], input[type='submit']")
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(2)

            # Go to 3rd Party Apps -> My Apps
            logger.info("Navigating to My Apps...")
            await page.goto(f"{BASE_URL}/cms#/oauthApps?t=0&lpt=2&lpa=6")
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(2)

            await page.screenshot(path=str(SCREENSHOT_DIR / "01_oauth_apps.png"), full_page=True)

            # Click My Apps tab (should be default)
            my_apps_tab = page.locator("text=My Apps").first
            if await my_apps_tab.is_visible():
                await my_apps_tab.click()
                await asyncio.sleep(2)
                await page.screenshot(path=str(SCREENSHOT_DIR / "02_my_apps.png"), full_page=True)

            # Look for existing authorized apps
            logger.info("Looking for authorized apps...")
            page_text = await page.locator("body").text_content()
            logger.info(f"Page content: {page_text[:500]}...")

            # Look for tokens or app entries
            app_rows = await page.locator("tr, .app-item, .list-group-item").all()
            for i, row in enumerate(app_rows[:10]):
                text = await row.text_content()
                if text and len(text.strip()) > 5:
                    logger.info(f"  Row {i}: {text[:100]}...")

            # Look for any token display
            token_elements = await page.locator("[class*='token'], code, pre, .access-token").all()
            for el in token_elements:
                text = await el.text_content()
                if text:
                    logger.info(f"  Token element: {text}")

            logger.info("\nBrowser open for 60 seconds to inspect My Apps...")
            await asyncio.sleep(60)

        except Exception as e:
            logger.error(f"Error: {e}")
            await page.screenshot(path=str(SCREENSHOT_DIR / "error.png"))
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(check_my_apps())
