"""
Get OAuth Credentials from MerusCase 3rd Party Apps -> App Publisher
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
BASE_URL = os.getenv("MERUSCASE_BASE_URL", "https://meruscase.com")

SCREENSHOT_DIR = Path("screenshots/oauth_creds")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


async def get_oauth_creds():
    """Navigate to 3rd Party Apps -> App Publisher to get OAuth credentials."""

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()

        try:
            # Step 1: Login
            logger.info("Logging in...")
            await page.goto(f"{BASE_URL}/users/login")
            await page.wait_for_load_state("networkidle")

            await page.fill("input[name='email'], input[type='email'], #email", EMAIL)
            await page.fill("input[name='password'], input[type='password'], #password", PASSWORD)
            await page.click("button[type='submit'], input[type='submit']")
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(2)

            logger.info(f"Logged in. URL: {page.url}")

            # Step 2: Navigate directly to 3rd Party Apps / OAuth Apps
            logger.info("Navigating to 3rd Party Apps (OAuth Apps)...")
            await page.goto(f"{BASE_URL}/cms#/oauthApps?t=0&lpt=2&lpa=6")
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(2)
            await page.screenshot(path=str(SCREENSHOT_DIR / "01_oauth_apps_page.png"), full_page=True)

            # Step 3: Look for App Publisher tab/link
            logger.info("Looking for App Publisher tab...")

            # Find tabs or links with "publisher" or "create" or "new"
            tabs = await page.locator("a, button, .nav-tabs li, [role='tab']").all()

            for tab in tabs:
                try:
                    text = await tab.text_content()
                    if text and any(kw in text.lower() for kw in ["publisher", "create", "new app", "register", "add app"]):
                        logger.info(f"Found: '{text.strip()}' - clicking...")
                        await tab.click()
                        await asyncio.sleep(2)
                        await page.screenshot(path=str(SCREENSHOT_DIR / "02_app_publisher.png"), full_page=True)
                        break
                except:
                    pass

            # Step 4: Look for existing apps or create new app option
            logger.info("Looking for existing apps or credentials...")

            # Take full page screenshot
            await page.screenshot(path=str(SCREENSHOT_DIR / "03_full_page.png"), full_page=True)

            # Extract any visible credentials or app info
            content = await page.content()

            # Look for input fields with credentials
            inputs = await page.locator("input[type='text'], input[readonly], .credential, .api-key, .client-id, .client-secret").all()

            credentials = {}
            for inp in inputs:
                try:
                    name = await inp.get_attribute("name") or await inp.get_attribute("id") or await inp.get_attribute("placeholder")
                    value = await inp.input_value()
                    if name and value:
                        logger.info(f"  Found field: {name} = {value[:20]}..." if len(value) > 20 else f"  Found field: {name} = {value}")
                        credentials[name] = value
                except:
                    pass

            # Look for any visible text that looks like credentials
            logger.info("Scanning page for credential-like text...")

            # Find elements that might contain API keys or IDs
            credential_elements = await page.locator("code, pre, .key, .secret, .token, [class*='credential'], [class*='api']").all()

            for el in credential_elements:
                try:
                    text = await el.text_content()
                    if text and len(text) > 10:
                        logger.info(f"  Potential credential: {text[:50]}...")
                except:
                    pass

            # Step 5: Try clicking on any existing apps to see their credentials
            logger.info("Looking for existing app entries...")

            app_rows = await page.locator("tr, .app-row, .app-item, .list-group-item").all()

            for i, row in enumerate(app_rows[:5]):  # Check first 5 rows
                try:
                    text = await row.text_content()
                    if text and any(kw in text.lower() for kw in ["app", "oauth", "merus"]):
                        logger.info(f"  App row {i}: {text[:100]}...")

                        # Try clicking to see details
                        edit_btn = await row.locator("a, button").first
                        if edit_btn:
                            await edit_btn.click()
                            await asyncio.sleep(2)
                            await page.screenshot(path=str(SCREENSHOT_DIR / f"04_app_details_{i}.png"), full_page=True)

                            # Check for credentials on detail page
                            detail_inputs = await page.locator("input").all()
                            for inp in detail_inputs:
                                try:
                                    label = await inp.get_attribute("placeholder") or await inp.get_attribute("name") or ""
                                    val = await inp.input_value()
                                    if val and ("id" in label.lower() or "key" in label.lower() or "secret" in label.lower()):
                                        logger.info(f"    CREDENTIAL: {label} = {val}")
                                except:
                                    pass

                            # Go back
                            await page.go_back()
                            await asyncio.sleep(1)
                except:
                    pass

            logger.info("\n" + "="*60)
            logger.info("SCREENSHOTS SAVED - Check for OAuth credentials")
            logger.info("="*60)

            # Keep browser open for manual inspection
            logger.info("\nBrowser staying open for 90 seconds for manual inspection...")
            await asyncio.sleep(90)

        except Exception as e:
            logger.error(f"Error: {e}")
            await page.screenshot(path=str(SCREENSHOT_DIR / "error.png"))
            raise
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(get_oauth_creds())
