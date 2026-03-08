"""
Extract OAuth Credentials from existing MerusCase App
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

SCREENSHOT_DIR = Path("screenshots/oauth_extract")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


async def extract_oauth_creds():
    """Click on existing app to extract OAuth credentials."""

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

            # Navigate to 3rd Party Apps -> App Publisher
            logger.info("Navigating to App Publisher...")
            await page.goto(f"{BASE_URL}/cms#/oauthApps?t=0&lpt=2&lpa=6")
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(2)

            # Click App Publisher tab
            await page.click("text=App Publisher")
            await asyncio.sleep(2)
            await page.screenshot(path=str(SCREENSHOT_DIR / "01_app_publisher.png"))

            # Click on the existing app row (the "..." menu or Edit link)
            logger.info("Looking for app to click...")

            # Try clicking on the app row's menu button (...)
            menu_btn = page.locator("tr:has-text('Review File') button, tr:has-text('Review File') .dropdown-toggle, tr:has-text('GlassBox') button").first
            if await menu_btn.is_visible():
                logger.info("Clicking app menu...")
                await menu_btn.click()
                await asyncio.sleep(1)
                await page.screenshot(path=str(SCREENSHOT_DIR / "02_menu_open.png"))

                # Click Edit App Configuration
                edit_link = page.locator("text=Edit App Configuration").first
                if await edit_link.is_visible():
                    logger.info("Clicking Edit App Configuration...")
                    await edit_link.click()
                    await asyncio.sleep(2)
                    await page.screenshot(path=str(SCREENSHOT_DIR / "03_edit_app.png"), full_page=True)

            # Now extract credentials from the form
            logger.info("\n" + "="*60)
            logger.info("EXTRACTING CREDENTIALS")
            logger.info("="*60)

            # Get all input values
            inputs = await page.locator("input").all()
            credentials = {}

            for inp in inputs:
                try:
                    inp_id = await inp.get_attribute("id") or ""
                    inp_name = await inp.get_attribute("name") or ""
                    inp_placeholder = await inp.get_attribute("placeholder") or ""
                    inp_value = await inp.input_value()

                    identifier = inp_id or inp_name or inp_placeholder

                    if inp_value and identifier:
                        # Check if this looks like a credential field
                        if any(kw in identifier.lower() for kw in ["id", "key", "secret", "token", "client", "app"]):
                            logger.info(f"  {identifier}: {inp_value}")
                            credentials[identifier] = inp_value
                        elif inp_value and len(inp_value) > 20:
                            logger.info(f"  {identifier}: {inp_value[:50]}...")
                            credentials[identifier] = inp_value
                except Exception as e:
                    pass

            # Also look for text that might be displayed (not in input)
            logger.info("\nLooking for displayed text credentials...")

            # Look for elements that might show IDs/secrets
            code_elements = await page.locator("code, pre, .credential, .key, .secret, .token, span.ng-binding").all()
            for el in code_elements:
                try:
                    text = await el.text_content()
                    if text and len(text) > 15:
                        logger.info(f"  Text element: {text}")
                except:
                    pass

            # Look for labeled values (label + value pairs)
            labels = await page.locator("label").all()
            for label in labels:
                try:
                    label_text = await label.text_content()
                    if label_text and any(kw in label_text.lower() for kw in ["id", "key", "secret", "client"]):
                        # Try to find the associated value
                        parent = label.locator("xpath=..")
                        value_el = parent.locator("input, span, div.value, .form-control-static")
                        if await value_el.count() > 0:
                            value = await value_el.first.text_content() or await value_el.first.input_value()
                            if value:
                                logger.info(f"  {label_text.strip()}: {value}")
                                credentials[label_text.strip()] = value
                except:
                    pass

            await page.screenshot(path=str(SCREENSHOT_DIR / "04_credentials_page.png"), full_page=True)

            logger.info("\n" + "="*60)
            logger.info("CREDENTIALS FOUND:")
            logger.info("="*60)
            for k, v in credentials.items():
                logger.info(f"  {k}: {v}")

            # Keep browser open
            logger.info("\nBrowser open for 60 seconds...")
            await asyncio.sleep(60)

        except Exception as e:
            logger.error(f"Error: {e}")
            await page.screenshot(path=str(SCREENSHOT_DIR / "error.png"))
            raise
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(extract_oauth_creds())
