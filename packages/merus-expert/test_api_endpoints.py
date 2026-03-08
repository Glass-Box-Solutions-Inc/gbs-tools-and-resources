"""
Test MerusCase API Endpoints
Uses OAuth flow to get access token, then tests available endpoints.
"""

import asyncio
import logging
import os
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from dotenv import load_dotenv
import httpx

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# OAuth Configuration
CLIENT_ID = os.getenv("MERUSCASE_API_CLIENT_ID", "1405")
CLIENT_SECRET = os.getenv("MERUSCASE_API_CLIENT_SECRET")
REDIRECT_URI = os.getenv("MERUSCASE_API_REDIRECT_URI", "https://api.meruscase.com/oauth/authcodeCallback")
API_BASE = "https://api.meruscase.com"

# For local callback handling
LOCAL_PORT = 8765
LOCAL_REDIRECT = f"http://localhost:{LOCAL_PORT}/callback"

# Store the auth code
auth_code = None


class CallbackHandler(BaseHTTPRequestHandler):
    """Handle OAuth callback."""

    def do_GET(self):
        global auth_code
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if "code" in params:
            auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body><h1>Authorization successful!</h1><p>You can close this window.</p></body></html>")
            logger.info(f"Received auth code: {auth_code[:20]}...")
        else:
            self.send_response(400)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body><h1>Error</h1><p>No authorization code received.</p></body></html>")

    def log_message(self, format, *args):
        pass  # Suppress HTTP logs


async def exchange_code_for_token(code: str) -> dict:
    """Exchange authorization code for access token."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{API_BASE}/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "redirect_uri": LOCAL_REDIRECT,
            }
        )
        return response.json()


async def test_endpoint(client: httpx.AsyncClient, method: str, endpoint: str, description: str) -> dict:
    """Test a single API endpoint."""
    try:
        if method == "GET":
            response = await client.get(f"{API_BASE}/{endpoint}")
        else:
            response = await client.post(f"{API_BASE}/{endpoint}")

        return {
            "endpoint": endpoint,
            "description": description,
            "status_code": response.status_code,
            "success": response.status_code == 200,
            "data_preview": str(response.json())[:200] if response.status_code == 200 else response.text[:200],
        }
    except Exception as e:
        return {
            "endpoint": endpoint,
            "description": description,
            "status_code": None,
            "success": False,
            "error": str(e),
        }


async def test_all_endpoints(access_token: str):
    """Test all known MerusCase API endpoints."""

    endpoints = [
        ("GET", "caseFiles/index", "List all cases"),
        ("GET", "activityTypes/index", "List activity types"),
        ("GET", "billingCodes/index", "List billing codes"),
        ("GET", "caseTypes/index", "List case types"),
        ("GET", "partyGroups/index", "List party groups"),
        ("GET", "paymentMethods/index", "List payment methods"),
        ("GET", "statutes/index", "List statutes"),
        ("GET", "tasks/index", "List tasks"),
        ("GET", "events/index", "List calendar events"),
        ("GET", "eventTypes/index", "List event types"),
        ("GET", "receivables/index", "List receivables"),
        ("GET", "caseLedgersOpen/index", "List open ledgers"),
        ("GET", "users/index", "List firm users (admin)"),
    ]

    logger.info("\n" + "="*70)
    logger.info("TESTING MERUSCASE API ENDPOINTS")
    logger.info("="*70)

    async with httpx.AsyncClient(
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        },
        timeout=30.0
    ) as client:

        results = []
        for method, endpoint, description in endpoints:
            result = await test_endpoint(client, method, endpoint, description)
            results.append(result)

            status = "✓" if result["success"] else "✗"
            logger.info(f"  {status} {endpoint}: {result.get('status_code', 'ERR')} - {description}")

        # Summary
        logger.info("\n" + "="*70)
        logger.info("RESULTS SUMMARY")
        logger.info("="*70)

        working = [r for r in results if r["success"]]
        failed = [r for r in results if not r["success"]]

        logger.info(f"\n  Working endpoints: {len(working)}/{len(results)}")
        logger.info(f"  Failed endpoints: {len(failed)}/{len(results)}")

        if working:
            logger.info("\n  WORKING:")
            for r in working:
                logger.info(f"    - {r['endpoint']}: {r['description']}")

        if failed:
            logger.info("\n  FAILED:")
            for r in failed:
                logger.info(f"    - {r['endpoint']}: {r.get('status_code', 'ERR')} - {r.get('error', '')}")

        return results


async def main():
    """Main OAuth flow and API testing."""
    global auth_code

    logger.info("="*70)
    logger.info("MERUSCASE API TEST")
    logger.info("="*70)
    logger.info(f"\nClient ID: {CLIENT_ID}")
    logger.info(f"Redirect URI: {LOCAL_REDIRECT}")

    # Step 1: Start local server for callback
    logger.info(f"\nStarting local callback server on port {LOCAL_PORT}...")
    server = HTTPServer(("localhost", LOCAL_PORT), CallbackHandler)

    # Step 2: Open authorization URL
    auth_url = f"{API_BASE}/oauth/authorize?response_type=code&client_id={CLIENT_ID}&redirect_uri={LOCAL_REDIRECT}"
    logger.info(f"\nOpening authorization URL in browser...")
    logger.info(f"URL: {auth_url}")

    webbrowser.open(auth_url)

    # Step 3: Wait for callback
    logger.info("\nWaiting for authorization callback...")
    logger.info("(Please authorize the app in the browser window)")

    while auth_code is None:
        server.handle_request()

    server.server_close()

    # Step 4: Exchange code for token
    logger.info("\nExchanging code for access token...")
    token_response = await exchange_code_for_token(auth_code)

    if "access_token" in token_response:
        access_token = token_response["access_token"]
        logger.info(f"Got access token: {access_token[:20]}...")

        # Save token for future use
        with open(".meruscase_token", "w") as f:
            f.write(access_token)
        logger.info("Token saved to .meruscase_token")

        # Step 5: Test endpoints
        await test_all_endpoints(access_token)

    else:
        logger.error(f"Failed to get access token: {token_response}")


if __name__ == "__main__":
    # Check if we have a saved token
    if os.path.exists(".meruscase_token"):
        with open(".meruscase_token") as f:
            saved_token = f.read().strip()
        if saved_token:
            logger.info("Found saved token, testing endpoints...")
            asyncio.run(test_all_endpoints(saved_token))
        else:
            asyncio.run(main())
    else:
        asyncio.run(main())
