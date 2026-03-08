"""
Explore MerusCase Form Structure
Quick script to discover the actual form fields on the new matter page.
"""

import asyncio
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from browser.client import MerusCaseBrowserClient
from browser.element_handler import ElementHandler
from security.config import SecurityConfig


async def explore_form():
    """Explore the new matter form and print field info."""
    config = SecurityConfig.from_env()

    client = MerusCaseBrowserClient(
        api_token=config.browserless_api_token,
        endpoint=config.browserless_endpoint,
        headless=config.use_headless,
        use_local=config.use_local_browser
    )

    try:
        await client.connect()
        page = client.page

        # Login
        print("Logging in...")
        await client.navigate(config.meruscase_login_url)
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(2)

        print(f"Current URL: {page.url}")

        # Check if already logged in (redirected to dashboard)
        if "/cms" in page.url or "dashboard" in page.url.lower():
            print("Already logged in!")
        else:
            # Check if email field exists
            email_visible = await page.locator("input[type='email'], input[name*='email']").first.is_visible()
            if email_visible:
                # Fill login
                email_input = page.locator("input[type='email'], input[name*='email']").first
                password_input = page.locator("input[type='password']").first

                await email_input.fill(config.meruscase_email)
                await password_input.fill(config.meruscase_password)

                submit = page.locator("button[type='submit'], input[type='submit']").first
                await submit.click()

                await page.wait_for_load_state("networkidle")
                print("Logged in!")
            else:
                print("Login form not found, may already be logged in")

        # Navigate to new matter
        print("\nNavigating to new matter form...")
        await client.navigate(f"{config.meruscase_base_url}/matters/new")
        await asyncio.sleep(3)

        # Take screenshot
        screenshot_path = Path("./knowledge/screenshots/form_exploration.png")
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(screenshot_path), full_page=True)
        print(f"Screenshot saved: {screenshot_path}")

        # Find all input fields
        print("\n" + "="*60)
        print("INPUT FIELDS FOUND")
        print("="*60)

        inputs = await page.query_selector_all("input, select, textarea")
        for i, inp in enumerate(inputs[:30]):  # Limit to first 30
            try:
                tag = await inp.evaluate("el => el.tagName")
                name = await inp.get_attribute("name") or ""
                id_attr = await inp.get_attribute("id") or ""
                type_attr = await inp.get_attribute("type") or ""
                placeholder = await inp.get_attribute("placeholder") or ""
                label_text = ""

                # Try to get associated label
                if id_attr:
                    label = await page.query_selector(f"label[for='{id_attr}']")
                    if label:
                        label_text = await label.inner_text()

                print(f"\n[{i+1}] <{tag.lower()}>")
                print(f"    name: {name}")
                print(f"    id: {id_attr}")
                print(f"    type: {type_attr}")
                print(f"    placeholder: {placeholder}")
                print(f"    label: {label_text}")

            except Exception as e:
                print(f"\n[{i+1}] Error reading element: {e}")

        # Find buttons
        print("\n" + "="*60)
        print("BUTTONS FOUND")
        print("="*60)

        buttons = await page.query_selector_all("button, input[type='submit']")
        for i, btn in enumerate(buttons[:10]):
            try:
                text = await btn.inner_text()
                btn_type = await btn.get_attribute("type") or ""
                print(f"  [{i+1}] {text.strip()} (type={btn_type})")
            except:
                pass

        print("\n" + "="*60)
        print("Current URL:", page.url)
        print("="*60)

        # Keep browser open for manual inspection
        print("\nBrowser will close in 30 seconds. Check the screenshot for visual reference.")
        await asyncio.sleep(30)

    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(explore_form())
