"""
Complete OAuth flow using browser automation.
MerusCase handles the callback - we just need to authorize and grab the token.
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

SCREENSHOT_DIR = Path("screenshots/oauth_flow")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


async def complete_oauth_flow():
    """Complete OAuth flow via browser and test API."""

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()

        access_token = None

        try:
            # Step 1: Go to OAuth authorize URL
            auth_url = f"{API_BASE}/oauth/authorize?response_type=code&client_id={CLIENT_ID}"
            logger.info(f"Navigating to OAuth authorize URL...")
            await page.goto(auth_url)
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(2)
            await page.screenshot(path=str(SCREENSHOT_DIR / "01_auth_page.png"))

            current_url = page.url
            logger.info(f"Current URL: {current_url}")

            # Step 2: If on login page, log in
            if "login" in current_url.lower() or await page.locator("input[type='password']").is_visible():
                logger.info("Login required, filling credentials...")
                await page.fill("input[name='email'], input[type='email'], #email", EMAIL)
                await page.fill("input[name='password'], input[type='password'], #password", PASSWORD)
                await page.click("button[type='submit'], input[type='submit']")
                await page.wait_for_load_state("networkidle")
                await asyncio.sleep(2)
                await page.screenshot(path=str(SCREENSHOT_DIR / "02_after_login.png"))

            # Step 3: Look for authorize/allow button
            logger.info("Looking for authorize button...")
            current_url = page.url

            # Check if we're on an authorization page
            authorize_btns = [
                "button:has-text('Authorize')",
                "button:has-text('Allow')",
                "button:has-text('Grant')",
                "input[type='submit'][value*='Authorize']",
                "a:has-text('Authorize')",
            ]

            for selector in authorize_btns:
                try:
                    btn = page.locator(selector).first
                    if await btn.is_visible():
                        logger.info(f"Found authorize button: {selector}")
                        await btn.click()
                        await asyncio.sleep(3)
                        await page.screenshot(path=str(SCREENSHOT_DIR / "03_after_authorize.png"))
                        break
                except:
                    pass

            # Step 4: Check current URL for code or token
            current_url = page.url
            logger.info(f"After authorization URL: {current_url}")

            # Look for code in URL
            code_match = re.search(r'[?&]code=([^&]+)', current_url)
            if code_match:
                auth_code = code_match.group(1)
                logger.info(f"Got authorization code: {auth_code[:30]}...")

                # Exchange code for token
                logger.info("Exchanging code for access token...")
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
                    token_data = response.json()
                    logger.info(f"Token response: {token_data}")

                    if "access_token" in token_data:
                        access_token = token_data["access_token"]
                        logger.info(f"Got access token: {access_token[:30]}...")

            # Step 5: If using MerusCase callback, look for token in page
            if not access_token:
                logger.info("Checking page for access token...")
                page_content = await page.content()

                # Look for token in page
                token_match = re.search(r'access_token["\s:=]+([a-zA-Z0-9._~-]+)', page_content)
                if token_match:
                    access_token = token_match.group(1)
                    logger.info(f"Found token in page: {access_token[:30]}...")

                # Look for token in any input fields
                inputs = await page.locator("input, textarea").all()
                for inp in inputs:
                    try:
                        val = await inp.input_value()
                        if val and len(val) > 30 and "." in val:
                            logger.info(f"Potential token in input: {val[:50]}...")
                            access_token = val
                    except:
                        pass

            await page.screenshot(path=str(SCREENSHOT_DIR / "04_final_state.png"), full_page=True)

            # Step 6: Test the API if we got a token
            if access_token:
                logger.info("\n" + "="*60)
                logger.info("TESTING API WITH TOKEN")
                logger.info("="*60)

                # Save token
                with open(".meruscase_token", "w") as f:
                    f.write(access_token)
                logger.info("Token saved to .meruscase_token")

                await test_api(access_token)

            else:
                logger.warning("Could not obtain access token")
                logger.info("Browser will stay open for manual inspection...")
                await asyncio.sleep(60)

        except Exception as e:
            logger.error(f"Error: {e}")
            await page.screenshot(path=str(SCREENSHOT_DIR / "error.png"))
            raise
        finally:
            await browser.close()


async def test_api(access_token: str):
    """Test API endpoints with the token."""

    endpoints = [
        ("GET", "caseFiles/index?limit=5", "List cases"),
        ("GET", "activityTypes/index", "Activity types"),
        ("GET", "billingCodes/index", "Billing codes"),
        ("GET", "caseTypes/index", "Case types"),
        ("GET", "tasks/index?limit=5", "Tasks"),
        ("GET", "users/index", "Firm users"),
    ]

    async with httpx.AsyncClient(
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        },
        timeout=30.0
    ) as client:

        for method, endpoint, description in endpoints:
            try:
                response = await client.get(f"{API_BASE}/{endpoint}")
                status = "✓" if response.status_code == 200 else "✗"
                logger.info(f"  {status} {endpoint}: {response.status_code}")

                if response.status_code == 200:
                    data = response.json()
                    if isinstance(data, list):
                        logger.info(f"      → {len(data)} items")
                    elif isinstance(data, dict):
                        logger.info(f"      → {list(data.keys())[:5]}")

            except Exception as e:
                logger.info(f"  ✗ {endpoint}: ERROR - {e}")


if __name__ == "__main__":
    asyncio.run(complete_oauth_flow())
