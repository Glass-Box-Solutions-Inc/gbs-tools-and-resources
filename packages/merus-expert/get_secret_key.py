"""
Get Secret Key from MerusCase OAuth App
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

SCREENSHOT_DIR = Path("screenshots/secret_key")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


async def get_secret_key():
    """Click Show Secret Key button to get OAuth client_secret."""

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

            # Navigate to App Publisher
            logger.info("Navigating to App Publisher...")
            await page.goto(f"{BASE_URL}/cms#/oauthApps?t=0&lpt=2&lpa=6")
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(2)

            # Click App Publisher tab
            await page.click("text=App Publisher")
            await asyncio.sleep(2)

            # Click on app menu and Edit
            logger.info("Opening app for editing...")
            menu_btn = page.locator("tr:has-text('Review File') button").first
            await menu_btn.click()
            await asyncio.sleep(1)

            await page.click("text=Edit App Configuration")
            await asyncio.sleep(2)

            # Now click "Show Secret Key & Auth Request URL" button
            logger.info("Clicking 'Show Secret Key & Auth Request URL'...")
            show_secret_btn = page.locator("button:has-text('Show Secret Key'), button:has-text('Secret Key')").first
            await show_secret_btn.click()
            await asyncio.sleep(2)

            await page.screenshot(path=str(SCREENSHOT_DIR / "01_secret_revealed.png"), full_page=True)

            # Extract the revealed secret
            logger.info("\n" + "="*60)
            logger.info("LOOKING FOR SECRET KEY")
            logger.info("="*60)

            # Look for modal or revealed content
            # Secret might be in a modal, alert, or newly visible element

            # Check for modal content
            modal = page.locator(".modal, .modal-content, [role='dialog']")
            if await modal.count() > 0:
                modal_text = await modal.first.text_content()
                logger.info(f"Modal content: {modal_text}")

            # Look for any text that looks like a secret (long alphanumeric string)
            all_text = await page.locator("body").text_content()

            # Look for inputs that might now have the secret
            inputs = await page.locator("input, textarea").all()
            for inp in inputs:
                try:
                    val = await inp.input_value()
                    placeholder = await inp.get_attribute("placeholder") or ""
                    name = await inp.get_attribute("name") or ""

                    if val and len(val) > 20:
                        logger.info(f"  Input ({name or placeholder}): {val}")
                except:
                    pass

            # Look for code/pre elements
            code_elements = await page.locator("code, pre, .secret, .key, .token, .credential").all()
            for el in code_elements:
                try:
                    text = await el.text_content()
                    if text:
                        logger.info(f"  Code element: {text}")
                except:
                    pass

            # Look for any div/span that might contain the secret
            secret_elements = await page.locator("[class*='secret'], [class*='key'], [class*='token'], .ng-binding").all()
            for el in secret_elements:
                try:
                    text = await el.text_content()
                    if text and len(text) > 15:
                        logger.info(f"  Secret element: {text}")
                except:
                    pass

            # Take another screenshot
            await page.screenshot(path=str(SCREENSHOT_DIR / "02_after_click.png"), full_page=True)

            logger.info("\n" + "="*60)
            logger.info("Check screenshots for the secret key")
            logger.info("="*60)

            # Keep browser open for manual inspection
            logger.info("\nBrowser open for 90 seconds - check the screen for the secret...")
            await asyncio.sleep(90)

        except Exception as e:
            logger.error(f"Error: {e}")
            await page.screenshot(path=str(SCREENSHOT_DIR / "error.png"))
            raise
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(get_secret_key())
