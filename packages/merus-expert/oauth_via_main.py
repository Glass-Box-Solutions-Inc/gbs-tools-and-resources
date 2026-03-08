"""
OAuth via main MerusCase login - bypass API login reCAPTCHA.
Log into main site first, then access OAuth while authenticated.
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
MAIN_BASE = "https://meruscase.com"

SCREENSHOT_DIR = Path("screenshots/oauth_main")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


async def oauth_via_main():
    """Log into main site first, then access OAuth."""

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()

        access_token = None

        try:
            # Step 1: Log into main MerusCase site
            logger.info("Logging into main MerusCase site...")
            await page.goto(f"{MAIN_BASE}/users/login")
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(2)

            # Fill login form
            await page.fill("input[name='email'], input[type='email'], #email", EMAIL)
            await page.fill("input[name='password'], input[type='password'], #password", PASSWORD)
            await page.click("button[type='submit'], input[type='submit']")
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(3)

            await page.screenshot(path=str(SCREENSHOT_DIR / "01_logged_in.png"))
            logger.info(f"Logged in. URL: {page.url}")

            # Step 2: Now go to OAuth authorize URL
            logger.info("Navigating to OAuth authorize...")
            auth_url = f"{API_BASE}/oauth/authorize?response_type=code&client_id={CLIENT_ID}"
            await page.goto(auth_url)
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(2)

            await page.screenshot(path=str(SCREENSHOT_DIR / "02_oauth_page.png"))
            logger.info(f"OAuth page URL: {page.url}")

            # Step 3: Check if we're on authorization consent page
            page_text = await page.locator("body").text_content()
            logger.info(f"Page preview: {page_text[:200]}...")

            # Check for checkbox and authorize button
            checkbox = page.locator("input[type='checkbox']").first
            if await checkbox.is_visible(timeout=3000):
                if not await checkbox.is_checked():
                    logger.info("Checking agreement checkbox...")
                    await checkbox.check()
                    await asyncio.sleep(1)

            # Click Yep/authorize button
            yep_btn = page.locator("input[value='Yep'], button:has-text('Yep')").first
            if await yep_btn.is_visible(timeout=3000):
                logger.info("Clicking Yep button...")
                await yep_btn.click()
                await page.wait_for_load_state("networkidle")
                await asyncio.sleep(3)

            await page.screenshot(path=str(SCREENSHOT_DIR / "03_after_auth.png"))

            # Step 4: Check for code in URL or token on page
            current_url = page.url
            logger.info(f"After auth URL: {current_url}")

            code_match = re.search(r'[?&]code=([^&]+)', current_url)
            if code_match:
                auth_code = code_match.group(1)
                logger.info(f"Got auth code: {auth_code}")

                # Exchange for token
                async with httpx.AsyncClient() as client:
                    resp = await client.post(
                        f"{API_BASE}/oauth/token",
                        data={
                            "grant_type": "authorization_code",
                            "code": auth_code,
                            "client_id": CLIENT_ID,
                            "client_secret": CLIENT_SECRET,
                        }
                    )
                    token_data = resp.json()
                    logger.info(f"Token response: {token_data}")
                    if "access_token" in token_data:
                        access_token = token_data["access_token"]

            # Check page for token if redirected to callback
            if not access_token and "authcodeCallback" in current_url:
                # MerusCase might display the token on callback page
                page_text = await page.locator("body").text_content()
                logger.info(f"Callback page: {page_text[:500]}...")

                # Look for token
                token_match = re.search(r'access_token["\s:=]+([a-zA-Z0-9._~-]+)', page_text)
                if token_match:
                    access_token = token_match.group(1)

            await page.screenshot(path=str(SCREENSHOT_DIR / "04_final.png"), full_page=True)

            # Step 5: Test API
            if access_token:
                logger.info(f"\n{'='*60}")
                logger.info(f"ACCESS TOKEN: {access_token}")
                logger.info(f"{'='*60}")

                with open(".meruscase_token", "w") as f:
                    f.write(access_token)
                logger.info("Token saved!")

                await test_api(access_token)
            else:
                logger.warning("No token obtained")
                logger.info("Browser open for 90 seconds...")
                await asyncio.sleep(90)

        except Exception as e:
            logger.error(f"Error: {e}")
            import traceback
            traceback.print_exc()
            await page.screenshot(path=str(SCREENSHOT_DIR / "error.png"))
        finally:
            await browser.close()


async def test_api(token: str):
    """Test API endpoints."""
    logger.info("\nTesting API...")

    async with httpx.AsyncClient(
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        timeout=30.0
    ) as client:
        endpoints = ["caseFiles/index?limit=3", "activityTypes/index", "caseTypes/index"]
        for ep in endpoints:
            resp = await client.get(f"{API_BASE}/{ep}")
            data = resp.json()
            has_errors = "errors" in data and data["errors"]
            status = "✗" if has_errors else "✓"
            logger.info(f"  {status} {ep}: {resp.status_code}")
            if not has_errors and isinstance(data, list):
                logger.info(f"      → {len(data)} items")


if __name__ == "__main__":
    asyncio.run(oauth_via_main())
