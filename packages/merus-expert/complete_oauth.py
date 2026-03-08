"""
Complete OAuth flow - handle the authorization checkbox and button.
"""

import asyncio
import logging
import os
import re
from pathlib import Path
from dotenv import load_dotenv
from playwright.async_api import async_playwright
import httpx

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

EMAIL = os.getenv("MERUSCASE_EMAIL", "Alex@adjudica.ai")
PASSWORD = os.getenv("MERUSCASE_PASSWORD")
CLIENT_ID = os.getenv("MERUSCASE_API_CLIENT_ID", "1405")
CLIENT_SECRET = os.getenv("MERUSCASE_API_CLIENT_SECRET")
API_BASE = "https://api.meruscase.com"

SCREENSHOT_DIR = Path("screenshots/oauth_complete")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


async def complete_oauth():
    """Complete OAuth flow with proper checkbox handling."""

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()

        access_token = None

        try:
            # Step 1: Go to OAuth authorize URL
            auth_url = f"{API_BASE}/oauth/authorize?response_type=code&client_id={CLIENT_ID}"
            logger.info(f"Navigating to: {auth_url}")
            await page.goto(auth_url)
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(2)
            await page.screenshot(path=str(SCREENSHOT_DIR / "01_initial_page.png"))

            current_url = page.url
            logger.info(f"Current URL: {current_url}")

            # Step 2: Login if needed (check if password field exists with short timeout)
            try:
                password_visible = await page.locator("input[type='password']").is_visible(timeout=3000)
                if password_visible:
                    logger.info("Login form detected, logging in...")
                    await page.fill("input[type='email'], input[name='data[User][email]']", EMAIL)
                    await page.fill("input[type='password']", PASSWORD)
                    await page.click("input[type='submit'], button[type='submit']")
                    await page.wait_for_load_state("networkidle")
                    await asyncio.sleep(2)
                    await page.screenshot(path=str(SCREENSHOT_DIR / "02_after_login.png"))
            except:
                logger.info("No login form, continuing...")

            # Step 3: Check if we're on authorization page
            await page.screenshot(path=str(SCREENSHOT_DIR / "03_before_auth.png"))

            # Check for agreement checkbox
            logger.info("Looking for agreement checkbox...")
            try:
                checkbox = page.locator("input[type='checkbox']").first
                if await checkbox.is_visible(timeout=3000):
                    is_checked = await checkbox.is_checked()
                    if not is_checked:
                        logger.info("Checking the agreement checkbox...")
                        await checkbox.check()
                        await asyncio.sleep(1)
            except:
                logger.info("No checkbox found or already checked")

            # Step 4: Click "Yep" button to authorize
            logger.info("Looking for authorize button...")
            try:
                # Try multiple selectors for the Yep button
                yep_selectors = [
                    "input[value='Yep']",
                    "button:has-text('Yep')",
                    "input[type='submit']",
                    "button[type='submit']",
                ]
                for selector in yep_selectors:
                    btn = page.locator(selector).first
                    if await btn.is_visible(timeout=2000):
                        logger.info(f"Clicking button: {selector}")
                        await btn.click()
                        await page.wait_for_load_state("networkidle")
                        await asyncio.sleep(3)
                        break
            except Exception as e:
                logger.info(f"Button click issue: {e}")

            await page.screenshot(path=str(SCREENSHOT_DIR / "04_after_authorize.png"))

            # Step 5: Check where we ended up
            current_url = page.url
            logger.info(f"After authorization URL: {current_url}")

            # Look for authorization code in URL
            code_match = re.search(r'[?&]code=([^&]+)', current_url)
            if code_match:
                auth_code = code_match.group(1)
                logger.info(f"Got auth code: {auth_code}")

                # Exchange for token
                logger.info("Exchanging code for token...")
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{API_BASE}/oauth/token",
                        data={
                            "grant_type": "authorization_code",
                            "code": auth_code,
                            "client_id": CLIENT_ID,
                            "client_secret": CLIENT_SECRET,
                        }
                    )
                    logger.info(f"Token response: {response.status_code}")
                    token_data = response.json()
                    logger.info(f"Token data: {token_data}")

                    if "access_token" in token_data:
                        access_token = token_data["access_token"]

            # Step 6: Check page content if no code in URL
            if not access_token:
                logger.info("Checking page for token info...")
                page_text = await page.locator("body").text_content()

                # Look for access_token in page
                if "access_token" in page_text.lower():
                    token_match = re.search(r'access_token["\s:=]+([a-zA-Z0-9._~-]+)', page_text)
                    if token_match:
                        access_token = token_match.group(1)
                        logger.info(f"Found token: {access_token[:40]}...")

                # Log page content for debugging
                logger.info(f"Page text: {page_text[:300]}...")

                await page.screenshot(path=str(SCREENSHOT_DIR / "05_final.png"), full_page=True)

            # Step 7: Test API if we have token
            if access_token:
                logger.info("\n" + "="*60)
                logger.info(f"ACCESS TOKEN: {access_token}")
                logger.info("="*60)

                with open(".meruscase_token", "w") as f:
                    f.write(access_token)
                logger.info("Token saved to .meruscase_token")

                await test_api(access_token)
            else:
                logger.warning("No access token obtained")
                logger.info("Browser open for 60 seconds for manual inspection...")
                await asyncio.sleep(60)

        except Exception as e:
            logger.error(f"Error: {e}")
            import traceback
            traceback.print_exc()
            await page.screenshot(path=str(SCREENSHOT_DIR / "error.png"))
        finally:
            await browser.close()


async def test_api(token: str):
    """Test API endpoints."""
    logger.info("\nTesting API endpoints...")

    endpoints = [
        "caseFiles/index?limit=3",
        "activityTypes/index",
        "caseTypes/index",
        "tasks/index?limit=3",
    ]

    async with httpx.AsyncClient(
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        timeout=30.0
    ) as client:
        for endpoint in endpoints:
            try:
                resp = await client.get(f"{API_BASE}/{endpoint}")
                data = resp.json()

                if "errors" in data and data.get("errors"):
                    logger.info(f"  ✗ {endpoint}: {resp.status_code} - {data.get('errors')}")
                else:
                    count = len(data) if isinstance(data, list) else "dict"
                    logger.info(f"  ✓ {endpoint}: {resp.status_code} - {count} items")
                    if isinstance(data, list) and len(data) > 0:
                        logger.info(f"      Sample: {str(data[0])[:100]}...")
            except Exception as e:
                logger.info(f"  ✗ {endpoint}: {e}")


if __name__ == "__main__":
    asyncio.run(complete_oauth())
