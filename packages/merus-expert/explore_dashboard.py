"""
Explore MerusCase Dashboard
Find navigation paths and new matter creation URL.
"""

import asyncio
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from browser.client import MerusCaseBrowserClient
from security.config import SecurityConfig


async def explore_dashboard():
    """Explore the dashboard and find matter creation path."""
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

        # Use the working login approach from matter_builder
        from browser.element_handler import ElementHandler
        element_handler = ElementHandler(page)

        # Find email field using multiple strategies
        email_input = await element_handler.find_input(
            field_name="email",
            label="Email",
            placeholder="Email"
        )

        if email_input:
            print("Found email field, logging in...")

            # Find password field
            password_input = await element_handler.find_input(
                field_name="password",
                label="Password",
                placeholder="Password",
                css_selector="input[type='password']"
            )

            if password_input:
                await email_input.fill(config.meruscase_email)
                await password_input.fill(config.meruscase_password)

                # Find login button
                login_button = await element_handler.find_button(
                    text="LOGIN",
                    css_selector="button[type='submit'], input[type='submit']"
                )

                if login_button:
                    await login_button.click()
                    await page.wait_for_load_state("networkidle", timeout=30000)
                    await asyncio.sleep(3)
                    print("Login submitted!")
        else:
            print("No login form found, might already be logged in")

        print(f"Current URL after login: {page.url}")

        # Take screenshot of dashboard
        screenshot_path = Path("./knowledge/screenshots/dashboard.png")
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(screenshot_path), full_page=True)
        print(f"Dashboard screenshot: {screenshot_path}")

        # Find all links on the page
        print("\n" + "="*60)
        print("NAVIGATION LINKS")
        print("="*60)

        links = await page.query_selector_all("a")
        seen_hrefs = set()
        for link in links:
            try:
                href = await link.get_attribute("href") or ""
                text = (await link.inner_text()).strip()[:50]
                if href and href not in seen_hrefs and not href.startswith("#"):
                    seen_hrefs.add(href)
                    # Look for matter/case related links
                    if any(kw in href.lower() or kw in text.lower() for kw in ['case', 'matter', 'new', 'add', 'create']):
                        print(f"  * {text}: {href}")
                    elif len(seen_hrefs) <= 20:  # First 20 unique links
                        print(f"    {text}: {href}")
            except:
                pass

        # Find menu items / dropdowns
        print("\n" + "="*60)
        print("MENU ITEMS (looking for case/matter creation)")
        print("="*60)

        # Look for common menu patterns
        menu_selectors = [
            "nav a", ".nav a", ".menu a", ".sidebar a",
            "[class*='menu'] a", "[class*='nav'] a",
            "button", "[role='menuitem']"
        ]

        for selector in menu_selectors:
            elements = await page.query_selector_all(selector)
            for el in elements[:10]:
                try:
                    text = (await el.inner_text()).strip()
                    if text and any(kw in text.lower() for kw in ['case', 'matter', 'new', 'add', 'create', 'client']):
                        tag = await el.evaluate("el => el.tagName")
                        href = await el.get_attribute("href") or ""
                        print(f"  [{tag}] {text}: {href}")
                except:
                    pass

        # Try common URLs
        print("\n" + "="*60)
        print("TESTING COMMON URLS")
        print("="*60)

        test_urls = [
            "/cms/cases/new",
            "/cms/matters/new",
            "/cms/add-case",
            "/cms/case/add",
            "/cms/clients/new",
            "/cms/case/new",
            "/cases/new",
            "/case/new",
        ]

        base_url = config.meruscase_base_url
        for test_url in test_urls:
            full_url = f"{base_url}{test_url}"
            try:
                await page.goto(full_url, wait_until="networkidle", timeout=10000)
                await asyncio.sleep(1)

                # Check if it's a valid page (not 404)
                is_404 = await page.locator("text='404'").is_visible()
                is_error = await page.locator("text='Error'").is_visible()

                if not is_404 and not is_error:
                    print(f"  FOUND: {test_url} -> {page.url}")
                    # Take screenshot
                    ss_name = test_url.replace("/", "_").strip("_") + ".png"
                    ss_path = Path(f"./knowledge/screenshots/{ss_name}")
                    await page.screenshot(path=str(ss_path))
                    print(f"         Screenshot: {ss_path}")
                else:
                    print(f"  404/Error: {test_url}")
            except Exception as e:
                print(f"  Failed: {test_url} - {str(e)[:50]}")

        print("\n" + "="*60)
        print("Exploration complete. Check screenshots folder.")
        print("="*60)

        # Keep browser open briefly
        await asyncio.sleep(5)

    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(explore_dashboard())
