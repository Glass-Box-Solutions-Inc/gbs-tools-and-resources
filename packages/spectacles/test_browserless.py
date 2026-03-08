"""Test Browserless connection directly"""
import asyncio
import sys
import os
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from playwright.async_api import async_playwright

# Load from environment or .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BROWSERLESS_TOKEN = os.environ.get("BROWSERLESS_API_TOKEN", "")
BROWSERLESS_ENDPOINT = os.environ.get("BROWSERLESS_ENDPOINT", "wss://production-sfo.browserless.io")

if not BROWSERLESS_TOKEN:
    print("[ERROR] BROWSERLESS_API_TOKEN not set in environment")
    print("  Set it with: export BROWSERLESS_API_TOKEN=your-token")
    print("  Or create a .env file with BROWSERLESS_API_TOKEN=your-token")
    sys.exit(1)

async def test_connection():
    print("Testing Browserless connection...")

    async with async_playwright() as p:
        print(f"Connecting to {BROWSERLESS_ENDPOINT}...")

        try:
            browser = await p.chromium.connect_over_cdp(
                f"{BROWSERLESS_ENDPOINT}?token={BROWSERLESS_TOKEN}",
                timeout=30000
            )
            print("[OK] Connected to Browserless!")

            # Get or create page
            context = browser.contexts[0] if browser.contexts else await browser.new_context()
            page = context.pages[0] if context.pages else await context.new_page()

            # Navigate to Slack
            print("Navigating to Slack API...")
            await page.goto("https://api.slack.com/apps/A0A3VF50GSF/oauth", wait_until="networkidle", timeout=60000)
            print(f"[OK] Page loaded: {page.url}")
            print(f"  Title: {await page.title()}")

            # Take screenshot
            screenshot = await page.screenshot()
            with open("slack_page.png", "wb") as f:
                f.write(screenshot)
            print("[OK] Screenshot saved to slack_page.png")

            # Get page content
            content = await page.content()
            print(f"[OK] Page content length: {len(content)} chars")

            # Check if we need to sign in
            if "Sign in" in content or "sign in" in content.lower():
                print("\n[!] Page requires sign-in")

                # Create liveURL for user interaction
                cdp = await context.new_cdp_session(page)
                result = await cdp.send("Browserless.liveURL", {"timeout": 300000})
                print(f"\n{'='*60}")
                print("SIGN IN REQUIRED - Open this URL:")
                print(f"\n  {result['liveURL']}")
                print(f"\n{'='*60}")

                # Wait for user
                print("\nWaiting for sign-in (5 min timeout)...")
                await asyncio.sleep(300)
            else:
                # Look for the bot token on the page
                print("\nLooking for Bot Token on page...")
                token_element = await page.query_selector('input[value^="xoxb-"]')
                if token_element:
                    token = await token_element.get_attribute("value")
                    print(f"\n[OK] FOUND BOT TOKEN: {token}")
                else:
                    print("Bot token input not found directly")
                    # Try to find it in the page text
                    text = await page.inner_text("body")
                    if "xoxb-" in text:
                        import re
                        match = re.search(r'xoxb-[a-zA-Z0-9-]+', text)
                        if match:
                            print(f"\n[OK] FOUND BOT TOKEN: {match.group()}")

            await browser.close()
            print("\n[OK] Test complete!")

        except Exception as e:
            print(f"\n[ERROR] {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_connection())
