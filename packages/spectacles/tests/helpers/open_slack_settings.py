#!/usr/bin/env python3
"""
Open Slack App Settings in Browserless

Opens a live browser session for manual interaction with Slack app settings.

Usage:
    python3 open_slack_settings.py

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import asyncio
from playwright.async_api import async_playwright
import time

BROWSERLESS_TOKEN = "2TcWyCwbfKt7UWCbec6a2ee3b613b579fb0edb5f7a52b0ace"
BROWSERLESS_ENDPOINT = "wss://production-sfo.browserless.io"


async def main():
    """Open browser and wait"""

    print("\n" + "="*80)
    print("OPENING SLACK APP SETTINGS IN BROWSERLESS")
    print("="*80)

    start_url = "https://api.slack.com/apps"

    async with async_playwright() as p:
        print("\n🌐 Connecting to Browserless...")

        browser = await p.chromium.connect_over_cdp(
            f"{BROWSERLESS_ENDPOINT}?token={BROWSERLESS_TOKEN}"
        )

        print("✅ Connected to Browserless")

        # Get or create context and page
        contexts = browser.contexts
        if contexts:
            context = contexts[0]
        else:
            context = await browser.new_context()

        pages = context.pages
        if pages:
            page = pages[0]
        else:
            page = await context.new_page()

        print(f"\n🔗 Navigating to: {start_url}")
        await page.goto(start_url, wait_until='domcontentloaded', timeout=60000)
        print("✅ Page loaded")

        print("\n" + "="*80)
        print("BROWSER SESSION ACTIVE")
        print("="*80)
        print("\nYou can now interact with the browser to:")
        print("1. Log in to Slack (if needed)")
        print("2. Select your Spectacles app")
        print("3. Navigate to OAuth & Permissions")
        print("4. Add the 'channels:manage' scope")
        print("5. Reinstall the app")
        print("6. Copy the new Bot User OAuth Token")
        print("\n⏰ Browser will stay open for 10 minutes...")
        print("   (Close this script when done: Ctrl+C)")
        print("="*80 + "\n")

        # Keep browser open for 10 minutes
        for i in range(600):
            await asyncio.sleep(1)
            if i % 60 == 0 and i > 0:
                print(f"⏰ {10 - i//60} minutes remaining...")

        print("\n⏱️  Time expired - closing browser")
        await browser.close()
        print("✅ Browser session closed")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⏹️  Session interrupted by user")
        print("✅ Browser session ended")
