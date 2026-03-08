"""Login to Slack and get Bot Token"""
import asyncio
import os
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from playwright.async_api import async_playwright

BROWSERLESS_TOKEN = os.environ.get("BROWSERLESS_API_TOKEN", "")
BROWSERLESS_ENDPOINT = "wss://production-sfo.browserless.io"

if not BROWSERLESS_TOKEN:
    raise ValueError("Missing BROWSERLESS_API_TOKEN environment variable")

async def login_and_get_token():
    print("Starting Browserless session for Slack login...")

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(
            f"{BROWSERLESS_ENDPOINT}?token={BROWSERLESS_TOKEN}",
            timeout=30000
        )
        print("[OK] Connected to Browserless")

        context = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = context.pages[0] if context.pages else await context.new_page()

        # Go to Slack sign in
        print("Navigating to Slack sign-in...")
        await page.goto("https://slack.com/signin", wait_until="networkidle", timeout=60000)
        print(f"[OK] At: {page.url}")

        # Create liveURL for user to sign in
        cdp = await context.new_cdp_session(page)
        result = await cdp.send("Browserless.liveURL", {"timeout": 600000})  # 10 min

        print("\n" + "="*70)
        print("LIVE BROWSER SESSION - Sign in to Slack")
        print("="*70)
        print(f"\nOpen this URL in your browser:\n")
        print(result['liveURL'])
        print("\nSteps:")
        print("1. Sign in with Google")
        print("2. Go to: https://api.slack.com/apps/A0A3VF50GSF/oauth")
        print("3. Copy the Bot User OAuth Token (xoxb-...)")
        print("4. Paste it back here in Claude Code")
        print("\nSession expires in 10 minutes.")
        print("="*70)

        # Listen for when user navigates to OAuth page
        async def check_for_token():
            while True:
                await asyncio.sleep(5)
                try:
                    current_url = page.url
                    if "oauth" in current_url.lower() and "slack.com" in current_url:
                        print(f"\n[OK] Detected OAuth page: {current_url}")
                        # Try to find the token
                        await asyncio.sleep(2)  # Wait for page to load
                        content = await page.content()
                        if "xoxb-" in content:
                            import re
                            match = re.search(r'xoxb-[a-zA-Z0-9-]+', content)
                            if match:
                                print(f"\n*** FOUND BOT TOKEN: {match.group()} ***\n")
                                return match.group()
                except:
                    pass

        # Wait for user or timeout
        try:
            token = await asyncio.wait_for(check_for_token(), timeout=600)
            if token:
                print(f"\nBot Token: {token}")
        except asyncio.TimeoutError:
            print("\n[!] Session timed out")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(login_and_get_token())
