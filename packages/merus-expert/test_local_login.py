#!/usr/bin/env python3
"""
Test MerusCase login using local browser (no Browserless required)
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Load .env file
from dotenv import load_dotenv
load_dotenv(project_root / ".env")

from browser.local_client import LocalBrowserClient
from security.config import SecurityConfig

async def test_local_login():
    """Test login to MerusCase using local browser"""

    print("=" * 70)
    print("MERUSCASE LOGIN TEST - LOCAL BROWSER")
    print("=" * 70)
    print()

    # Load configuration
    config = SecurityConfig.from_env()

    print(f"Login URL: {config.meruscase_login_url}")
    print(f"Email: {config.meruscase_email}")
    print(f"Password: {'*' * len(config.meruscase_password)}")
    print()

    # Create screenshots directory
    screenshots_dir = project_root / "screenshots" / "test"
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Use local browser (headless=False to see the browser)
        async with LocalBrowserClient(headless=False) as browser:
            print("[INFO] Local browser started")
            print()

            # Navigate to login page
            print("[STEP 1] Navigating to login page...")
            await browser.navigate(config.meruscase_login_url)
            await browser.screenshot(str(screenshots_dir / "01_login_page.png"))
            print("[OK] Login page loaded")
            print()

            # Find and fill email field
            print("[STEP 2] Filling email...")
            page = browser.page

            # Try different selectors for email
            email_selectors = [
                'input[name="email"]',
                'input[type="email"]',
                '#email',
                'input[placeholder*="email" i]',
                'input[placeholder*="Email" i]'
            ]

            email_field = None
            for selector in email_selectors:
                try:
                    email_field = page.locator(selector).first
                    if await email_field.is_visible(timeout=2000):
                        print(f"  Found email field: {selector}")
                        break
                except:
                    continue

            if email_field:
                await email_field.fill(config.meruscase_email)
                print("[OK] Email filled")
            else:
                print("[WARN] Could not find email field")
            print()

            # Find and fill password field
            print("[STEP 3] Filling password...")
            password_selectors = [
                'input[name="password"]',
                'input[type="password"]',
                '#password'
            ]

            password_field = None
            for selector in password_selectors:
                try:
                    password_field = page.locator(selector).first
                    if await password_field.is_visible(timeout=2000):
                        print(f"  Found password field: {selector}")
                        break
                except:
                    continue

            if password_field:
                await password_field.fill(config.meruscase_password)
                print("[OK] Password filled")
            else:
                print("[WARN] Could not find password field")
            print()

            # Take screenshot before login
            await browser.screenshot(str(screenshots_dir / "02_credentials_filled.png"))

            # Find and click login button
            print("[STEP 4] Clicking login button...")
            login_selectors = [
                'button[type="submit"]',
                'input[type="submit"]',
                'button:has-text("Log in")',
                'button:has-text("Login")',
                'button:has-text("Sign in")'
            ]

            login_button = None
            for selector in login_selectors:
                try:
                    login_button = page.locator(selector).first
                    if await login_button.is_visible(timeout=2000):
                        print(f"  Found login button: {selector}")
                        break
                except:
                    continue

            if login_button:
                await login_button.click()
                print("[OK] Login button clicked")

                # Wait for navigation
                await page.wait_for_load_state('networkidle', timeout=15000)
                print()

                # Check current URL
                current_url = page.url
                print(f"[INFO] Current URL: {current_url}")

                # Take post-login screenshot
                await browser.screenshot(str(screenshots_dir / "03_post_login.png"))

                # Check for success indicators
                if '/login' not in current_url.lower():
                    print()
                    print("=" * 70)
                    print("[SUCCESS] LOGIN SUCCESSFUL!")
                    print("=" * 70)
                else:
                    print()
                    print("=" * 70)
                    print("[WARN] Still on login page - check credentials")
                    print("=" * 70)
            else:
                print("[WARN] Could not find login button")

            print()
            print(f"Screenshots saved to: {screenshots_dir}")
            print()

            # Keep browser open for a moment to see result
            await asyncio.sleep(3)

            return True

    except Exception as e:
        print()
        print("=" * 70)
        print("[FAILED] LOGIN TEST FAILED")
        print("=" * 70)
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_local_login())
    sys.exit(0 if success else 1)
