"""
Manual OAuth - Opens browser, YOU log in and authorize, script captures token.
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

CLIENT_ID = os.getenv("MERUSCASE_API_CLIENT_ID", "1405")
CLIENT_SECRET = os.getenv("MERUSCASE_API_CLIENT_SECRET")
API_BASE = "https://api.meruscase.com"

SCREENSHOT_DIR = Path("screenshots/manual_oauth")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


async def manual_oauth():
    """Open OAuth page - user logs in manually."""

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()

        access_token = None

        try:
            auth_url = f"{API_BASE}/oauth/authorize?response_type=code&client_id={CLIENT_ID}"
            logger.info(f"\n{'='*60}")
            logger.info("MANUAL OAUTH FLOW")
            logger.info(f"{'='*60}")
            logger.info(f"\nOpening: {auth_url}")
            logger.info("\n>>> PLEASE LOG IN MANUALLY AND CLICK 'YEP' TO AUTHORIZE <<<\n")

            await page.goto(auth_url)

            # Wait for user to complete login and authorization
            # Poll for URL change indicating success
            logger.info("Waiting for authorization (up to 120 seconds)...")

            for i in range(60):  # 120 seconds max
                await asyncio.sleep(2)
                current_url = page.url

                # Check for auth code in URL
                if "code=" in current_url:
                    code_match = re.search(r'[?&]code=([^&]+)', current_url)
                    if code_match:
                        auth_code = code_match.group(1)
                        logger.info(f"\n✓ Got authorization code: {auth_code[:30]}...")

                        # Exchange for token
                        logger.info("Exchanging for access token...")
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
                            data = resp.json()
                            logger.info(f"Token response: {data}")

                            if "access_token" in data:
                                access_token = data["access_token"]
                        break

                # Check for callback URL (MerusCase managed)
                if "authcodeCallback" in current_url:
                    logger.info(f"\n✓ Redirected to callback: {current_url}")
                    # Try to find token on page
                    page_text = await page.content()
                    token_match = re.search(r'access_token["\s:=]+([a-zA-Z0-9._~-]+)', page_text)
                    if token_match:
                        access_token = token_match.group(1)
                    break

                # Check if still on login page
                if "oauth/login" in current_url:
                    if i % 10 == 0:
                        logger.info(f"  Still waiting... ({i*2}s)")

            await page.screenshot(path=str(SCREENSHOT_DIR / "final.png"), full_page=True)

            if access_token:
                logger.info(f"\n{'='*60}")
                logger.info(f"SUCCESS! Access Token:")
                logger.info(f"{access_token}")
                logger.info(f"{'='*60}")

                with open(".meruscase_token", "w") as f:
                    f.write(access_token)
                logger.info("Token saved to .meruscase_token")

                # Test it
                await test_api(access_token)
            else:
                logger.warning("\nNo token obtained. Check the browser window.")
                await asyncio.sleep(30)

        except Exception as e:
            logger.error(f"Error: {e}")
        finally:
            await browser.close()


async def test_api(token: str):
    """Quick API test."""
    logger.info("\nTesting API...")
    async with httpx.AsyncClient(
        headers={"Authorization": f"Bearer {token}"},
        timeout=30.0
    ) as client:
        resp = await client.get(f"{API_BASE}/caseFiles/index?limit=2")
        data = resp.json()
        if "errors" not in data or not data.get("errors"):
            logger.info(f"  ✓ caseFiles/index: {resp.status_code} - Working!")
            if isinstance(data, list):
                logger.info(f"    Found {len(data)} cases")
        else:
            logger.info(f"  ✗ Error: {data}")


if __name__ == "__main__":
    asyncio.run(manual_oauth())
