"""Create a Browserless live session for Slack OAuth token retrieval"""
import asyncio
from playwright.async_api import async_playwright

BROWSERLESS_TOKEN = "2TcWyCwbfKt7UWCbec6a2ee3b613b579fb0edb5f7a52b0ace"
BROWSERLESS_ENDPOINT = "wss://production-sfo.browserless.io"

async def create_live_session():
    async with async_playwright() as p:
        # Connect to Browserless
        browser = await p.chromium.connect_over_cdp(
            f"{BROWSERLESS_ENDPOINT}?token={BROWSERLESS_TOKEN}"
        )

        context = browser.contexts[0]
        page = context.pages[0] if context.pages else await context.new_page()

        # Navigate to Slack OAuth page
        await page.goto("https://api.slack.com/apps/A0A3VF50GSF/oauth")

        # Create CDP session and get liveURL
        cdp = await context.new_cdp_session(page)
        result = await cdp.send("Browserless.liveURL", {
            "timeout": 300000,  # 5 minutes
        })

        print("\n" + "="*60)
        print("LIVE BROWSER SESSION READY!")
        print("="*60)
        print(f"\nOpen this URL in your browser:\n")
        print(f"  {result['liveURL']}")
        print(f"\n1. Sign in with Google if prompted")
        print(f"2. Copy the 'Bot User OAuth Token' (xoxb-...)")
        print(f"3. Press Ctrl+C when done")
        print("="*60 + "\n")

        # Wait for user to finish
        try:
            await asyncio.sleep(300)  # 5 min timeout
        except asyncio.CancelledError:
            pass

        await browser.close()

if __name__ == "__main__":
    asyncio.run(create_live_session())
