"""
Find MerusCase API Settings - Navigate to 3rd Party Apps
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

SCREENSHOT_DIR = Path("screenshots/api_settings")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


async def find_api_settings():
    """Navigate to 3rd Party Apps / API settings."""

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
            await page.screenshot(path=str(SCREENSHOT_DIR / "01_logged_in.png"))

            # Step 2: Click on user menu (top right)
            logger.info("Looking for user menu...")

            # Try clicking the user dropdown in top right
            user_menu_selectors = [
                ".user-dropdown",
                "[class*='user-menu']",
                "a[href*='users/view']",
                ".navbar-right .dropdown-toggle",
                "text=Alex",
                "[aria-label*='user']",
            ]

            for selector in user_menu_selectors:
                try:
                    el = page.locator(selector).first
                    if await el.is_visible():
                        logger.info(f"Found user menu: {selector}")
                        await el.click()
                        await asyncio.sleep(1)
                        await page.screenshot(path=str(SCREENSHOT_DIR / "02_user_menu_open.png"))
                        break
                except:
                    pass

            # Step 3: Look for 3rd Party Apps in the page/menu
            logger.info("Looking for 3rd Party Apps link...")

            # Search all links for API-related text
            all_links = await page.locator("a").all()
            api_links = []

            for link in all_links:
                try:
                    text = await link.text_content()
                    href = await link.get_attribute("href")
                    if text and any(kw in text.lower() for kw in ["3rd party", "third party", "api", "app", "oauth", "developer", "integration"]):
                        api_links.append({"text": text.strip(), "href": href})
                        logger.info(f"  Found: '{text.strip()}' -> {href}")
                except:
                    pass

            await page.screenshot(path=str(SCREENSHOT_DIR / "03_links_found.png"))

            # Step 4: Try direct navigation to common API settings paths
            logger.info("Trying direct navigation to API settings...")

            api_urls = [
                f"{BASE_URL}/cms#/merusApps",
                f"{BASE_URL}/cms#/apps",
                f"{BASE_URL}/cms#/thirdPartyApps",
                f"{BASE_URL}/cms#/oauth",
                f"{BASE_URL}/cms#/apiSettings",
                f"{BASE_URL}/cms#/merusAccounts/viewAccount?subtab=apps",
                f"{BASE_URL}/cms#/merusAccounts/viewAccount?t=0&subtab=third-party-apps",
            ]

            for url in api_urls:
                try:
                    logger.info(f"Trying: {url}")
                    await page.goto(url)
                    await page.wait_for_load_state("networkidle")
                    await asyncio.sleep(1)

                    # Check if we got an error
                    error_visible = await page.locator("text=not have sufficient privileges").is_visible()
                    if error_visible:
                        await page.locator("button:has-text('OK')").click()
                        await asyncio.sleep(0.5)
                        continue

                    # Check for API-related content
                    content = await page.content()
                    if any(kw in content.lower() for kw in ["client_id", "client_secret", "oauth", "app id", "api key"]):
                        logger.info(f"SUCCESS! Found API settings at: {url}")
                        await page.screenshot(path=str(SCREENSHOT_DIR / "04_api_settings_found.png"), full_page=True)
                        break

                except Exception as e:
                    logger.warning(f"  Error: {e}")

            # Step 5: Navigate to subscription/account page
            logger.info("Checking MerusCase Subscription page...")
            await page.goto(f"{BASE_URL}/cms#/merusAccounts/viewAccount?t=0&lpt=2&subtab=account-info&lpa=7")
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(2)
            await page.screenshot(path=str(SCREENSHOT_DIR / "05_account_page.png"), full_page=True)

            # Look for tabs on the account page
            tabs = await page.locator(".nav-tabs a, .tab-nav a, [role='tab']").all()
            logger.info(f"Found {len(tabs)} tabs on account page")

            for tab in tabs:
                try:
                    text = await tab.text_content()
                    logger.info(f"  Tab: '{text.strip()}'")
                    if any(kw in text.lower() for kw in ["app", "api", "3rd", "third", "oauth"]):
                        logger.info(f"  -> Clicking '{text.strip()}'")
                        await tab.click()
                        await asyncio.sleep(2)
                        await page.screenshot(path=str(SCREENSHOT_DIR / "06_apps_tab.png"), full_page=True)
                except:
                    pass

            # Final: Keep browser open for manual navigation
            logger.info("\n" + "="*50)
            logger.info("Browser staying open for 120 seconds")
            logger.info("Please manually navigate to find API settings")
            logger.info("="*50)

            await asyncio.sleep(120)

        except Exception as e:
            logger.error(f"Error: {e}")
            await page.screenshot(path=str(SCREENSHOT_DIR / "error.png"))
            raise
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(find_api_settings())
