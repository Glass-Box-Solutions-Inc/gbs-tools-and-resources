#!/usr/bin/env python3
"""
Interactive Slack Scope Update via Browserless

Opens Slack app settings, waits for user to log in, then automates scope addition.

Usage:
    python3 update_slack_scopes_interactive.py

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import asyncio
import os
from playwright.async_api import async_playwright, Page
import sys

BROWSERLESS_TOKEN = "2TcWyCwbfKt7UWCbec6a2ee3b613b579fb0edb5f7a52b0ace"
BROWSERLESS_ENDPOINT = "wss://production-sfo.browserless.io"


async def wait_for_login(page: Page):
    """Wait for user to log in to Slack"""

    print("\n" + "="*80)
    print("WAITING FOR YOU TO LOG IN")
    print("="*80)
    print("\nPlease log in to Slack in the browser window.")
    print("Once you're logged in and can see the app dashboard, press ENTER here...")
    print("\nLive browser URL (if you need it):")
    print(f"  Check the Playwright browser window")
    print("="*80 + "\n")

    # Wait for user confirmation
    input("Press ENTER when you've logged in and can see the Slack app dashboard...")

    print("\n✅ Proceeding with scope update automation...")


async def add_scopes(page: Page):
    """Add required scopes to Slack app"""

    print("\n📋 Starting scope update process...")

    # Navigate to OAuth & Permissions
    print("\n1. Navigating to OAuth & Permissions...")

    # Look for OAuth & Permissions link
    oauth_link = page.locator('a:has-text("OAuth & Permissions")')

    if await oauth_link.count() > 0:
        await oauth_link.click()
        await page.wait_for_load_state('networkidle')
        print("   ✅ Navigated to OAuth & Permissions")
    else:
        print("   ⚠️  Could not find OAuth & Permissions link - may already be on the page")

    await asyncio.sleep(2)

    # Scroll to Scopes section
    print("\n2. Finding Scopes section...")

    scopes_section = page.locator('text=Bot Token Scopes').first
    if await scopes_section.count() > 0:
        await scopes_section.scroll_into_view_if_needed()
        print("   ✅ Found Bot Token Scopes section")

    await asyncio.sleep(1)

    # Find "Add an OAuth Scope" button
    print("\n3. Looking for 'Add an OAuth Scope' button...")

    add_scope_button = page.locator('button:has-text("Add an OAuth Scope")').first

    if await add_scope_button.count() == 0:
        # Try alternative selectors
        add_scope_button = page.locator('[data-qa="add_scope_button"]').first

    if await add_scope_button.count() > 0:
        print("   ✅ Found 'Add an OAuth Scope' button")

        # Add channels:manage scope
        print("\n4. Adding 'channels:manage' scope...")

        await add_scope_button.click()
        await asyncio.sleep(1)

        # Find the dropdown/input for scope selection
        scope_input = page.locator('input[placeholder*="scope"], input[type="text"]').last

        if await scope_input.count() > 0:
            await scope_input.fill('channels:manage')
            await asyncio.sleep(0.5)

            # Look for the scope in dropdown and click it
            scope_option = page.locator('text=channels:manage').first

            if await scope_option.count() > 0:
                await scope_option.click()
                print("   ✅ Added 'channels:manage' scope")
            else:
                print("   ⚠️  Could not find scope in dropdown - may need manual selection")
                print("   Please select 'channels:manage' from the dropdown manually")
                input("   Press ENTER when done...")
        else:
            print("   ⚠️  Could not find scope input - may need manual entry")
            print("   Please add 'channels:manage' scope manually")
            input("   Press ENTER when done...")
    else:
        print("   ⚠️  Could not find 'Add an OAuth Scope' button")
        print("   Please add 'channels:manage' scope manually")
        input("   Press ENTER when done...")

    await asyncio.sleep(2)

    # Check if reinstall banner appears
    print("\n5. Checking for reinstall banner...")

    reinstall_banner = page.locator('text=Please reinstall your app').first

    if await reinstall_banner.count() > 0:
        print("   ✅ Reinstall banner appeared (scope added successfully)")

        # Find reinstall button
        print("\n6. Looking for 'Reinstall to Workspace' button...")

        reinstall_button = page.locator('button:has-text("Reinstall"), a:has-text("Reinstall to Workspace")').first

        if await reinstall_button.count() > 0:
            print("   ✅ Found reinstall button")
            print("\n   ⚠️  PAUSING - Please review the new permissions before reinstalling")
            print("   When ready, click 'Reinstall to Workspace' in the browser")
            input("   Press ENTER after you've reinstalled the app...")

            # Wait for reinstall to complete
            await asyncio.sleep(3)

            print("\n7. Looking for the new Bot User OAuth Token...")
            print("\n   The token should be visible at the top of the OAuth & Permissions page")
            print("   It starts with 'xoxb-'")
            print("\n   Please copy the token and paste it below:")

            new_token = input("\n   Bot Token: ").strip()

            if new_token and new_token.startswith('xoxb-'):
                print(f"\n   ✅ Token received: {new_token[:15]}...")
                return new_token
            else:
                print("\n   ⚠️  Invalid token format - should start with 'xoxb-'")
                return None
        else:
            print("   ⚠️  Could not find reinstall button")
            return None
    else:
        print("   ⚠️  No reinstall banner appeared - scope may already exist or not added")

        # Check if scope already exists
        existing_scope = page.locator('text=channels:manage').first
        if await existing_scope.count() > 0:
            print("\n   ℹ️  'channels:manage' scope may already be present")

        return None


async def main():
    """Main automation flow"""

    print("\n" + "="*80)
    print("SLACK APP SCOPE UPDATE - INTERACTIVE AUTOMATION")
    print("="*80)

    # Determine Slack App URL
    print("\nWhat is your Slack App ID?")
    print("(You can find it in the URL: https://api.slack.com/apps/A012345)")
    print("Or press ENTER to navigate to app list first")

    app_id = input("\nApp ID (or ENTER to browse): ").strip()

    if app_id:
        start_url = f"https://api.slack.com/apps/{app_id}/oauth"
    else:
        start_url = "https://api.slack.com/apps"

    print(f"\nStarting URL: {start_url}")

    async with async_playwright() as p:
        print("\n🌐 Connecting to Browserless...")

        browser = await p.chromium.connect_over_cdp(
            f"{BROWSERLESS_ENDPOINT}?token={BROWSERLESS_TOKEN}"
        )

        print("✅ Connected to Browserless")

        # Get the default context and page
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

        await page.goto(start_url, wait_until='networkidle', timeout=60000)

        print("✅ Page loaded")

        # Wait for user to log in
        await wait_for_login(page)

        # Add scopes
        new_token = await add_scopes(page)

        if new_token:
            print("\n" + "="*80)
            print("SUCCESS!")
            print("="*80)
            print(f"\n✅ New Bot Token: {new_token[:20]}...")
            print("\nNext step: I'll update GCP Secret Manager with this token")

            # Keep browser open for verification
            print("\n⏸️  Browser will stay open for 60 seconds for verification...")
            print("   You can review the changes in Slack")
            await asyncio.sleep(60)
        else:
            print("\n⚠️  Could not automatically extract token")
            print("   Please copy the Bot User OAuth Token from the page")

            # Keep browser open
            print("\n⏸️  Browser will stay open for 2 minutes...")
            print("   Copy the token and we'll update GCP manually")
            await asyncio.sleep(120)

        await browser.close()
        print("\n✅ Browser session closed")


if __name__ == "__main__":
    asyncio.run(main())
