"""
Explore MerusCase API Settings
Log in and find OAuth/API credentials in the settings area.
"""

import asyncio
import logging
import os
from pathlib import Path
from dotenv import load_dotenv
from playwright.async_api import async_playwright

# Load environment
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Credentials
EMAIL = os.getenv("MERUSCASE_EMAIL", "Alex@adjudica.ai")
PASSWORD = os.getenv("MERUSCASE_PASSWORD")
BASE_URL = os.getenv("MERUSCASE_BASE_URL", "https://meruscase.com")

SCREENSHOT_DIR = Path("screenshots/api_discovery")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


async def explore_api_settings():
    """Log into MerusCase and explore API/developer settings."""

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()

        try:
            # Step 1: Login
            logger.info("Step 1: Logging into MerusCase...")
            await page.goto(f"{BASE_URL}/users/login")
            await page.wait_for_load_state("networkidle")
            await page.screenshot(path=str(SCREENSHOT_DIR / "01_login_page.png"))

            # Fill login form
            await page.fill("input[name='email'], input[type='email'], #email", EMAIL)
            await page.fill("input[name='password'], input[type='password'], #password", PASSWORD)
            await page.screenshot(path=str(SCREENSHOT_DIR / "02_credentials_filled.png"))

            # Click login button
            await page.click("button[type='submit'], input[type='submit'], button:has-text('Sign In')")
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(2)
            await page.screenshot(path=str(SCREENSHOT_DIR / "03_after_login.png"))

            current_url = page.url
            logger.info(f"Logged in. Current URL: {current_url}")

            # Step 2: Look for settings/admin menu
            logger.info("Step 2: Looking for settings/admin area...")

            # Common places to find API settings
            settings_urls = [
                f"{BASE_URL}/cms#/settings",
                f"{BASE_URL}/cms#/admin",
                f"{BASE_URL}/cms#/firm/settings",
                f"{BASE_URL}/cms#/firm",
                f"{BASE_URL}/cms#/api",
                f"{BASE_URL}/cms#/integrations",
                f"{BASE_URL}/cms#/developer",
                f"{BASE_URL}/cms#/apps",
            ]

            # Try to find settings link on page first
            settings_selectors = [
                "a[href*='settings']",
                "a[href*='admin']",
                "a[href*='firm']",
                "button:has-text('Settings')",
                "[class*='settings']",
                "[class*='gear']",
                ".user-menu a",
                ".dropdown-menu a",
            ]

            for selector in settings_selectors:
                try:
                    elements = await page.locator(selector).all()
                    if elements:
                        logger.info(f"Found {len(elements)} elements matching '{selector}'")
                        for i, el in enumerate(elements[:5]):
                            text = await el.text_content()
                            href = await el.get_attribute("href") if await el.count() else None
                            logger.info(f"  [{i}] text='{text}', href='{href}'")
                except:
                    pass

            # Step 3: Navigate to settings pages
            logger.info("Step 3: Exploring settings pages...")

            for i, url in enumerate(settings_urls):
                try:
                    logger.info(f"Trying: {url}")
                    await page.goto(url)
                    await page.wait_for_load_state("networkidle")
                    await asyncio.sleep(1)

                    # Take screenshot
                    screenshot_name = f"04_settings_{i}_{url.split('#/')[-1].replace('/', '_')}.png"
                    await page.screenshot(path=str(SCREENSHOT_DIR / screenshot_name))

                    # Check page content for API-related elements
                    page_text = await page.content()

                    api_keywords = ["API", "OAuth", "token", "client_id", "client_secret",
                                   "app", "integration", "developer", "webhook", "key"]

                    found_keywords = [kw for kw in api_keywords if kw.lower() in page_text.lower()]
                    if found_keywords:
                        logger.info(f"  Found keywords: {found_keywords}")
                        await page.screenshot(path=str(SCREENSHOT_DIR / f"05_api_found_{i}.png"), full_page=True)

                except Exception as e:
                    logger.warning(f"  Error: {e}")

            # Step 4: Look specifically for API/OAuth settings
            logger.info("Step 4: Looking for API credentials...")

            # Navigate to firm settings which usually has integrations
            await page.goto(f"{BASE_URL}/cms#/firm")
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(2)
            await page.screenshot(path=str(SCREENSHOT_DIR / "06_firm_page.png"), full_page=True)

            # Look for tabs or links
            tabs = await page.locator("a, button, .tab, [role='tab']").all()
            logger.info(f"Found {len(tabs)} potential navigation elements")

            for tab in tabs[:20]:
                try:
                    text = await tab.text_content()
                    if text and any(kw in text.lower() for kw in ["api", "app", "integrat", "develop", "oauth"]):
                        logger.info(f"  Potential API tab: '{text}'")
                        await tab.click()
                        await asyncio.sleep(1)
                        await page.screenshot(path=str(SCREENSHOT_DIR / "07_api_tab_clicked.png"), full_page=True)
                except:
                    pass

            # Final screenshot of current state
            await page.screenshot(path=str(SCREENSHOT_DIR / "08_final_state.png"), full_page=True)

            logger.info(f"\nScreenshots saved to: {SCREENSHOT_DIR.absolute()}")
            logger.info("Please check the screenshots for API settings location.")

            # Keep browser open for manual inspection
            logger.info("\nBrowser will stay open for 60 seconds for manual inspection...")
            await asyncio.sleep(60)

        except Exception as e:
            logger.error(f"Error: {e}")
            await page.screenshot(path=str(SCREENSHOT_DIR / "error.png"))
            raise
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(explore_api_settings())
