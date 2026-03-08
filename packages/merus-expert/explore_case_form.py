"""
Explore MerusCase New Case Form
Find all form fields for case creation.
"""

import asyncio
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from browser.client import MerusCaseBrowserClient
from browser.element_handler import ElementHandler
from security.config import SecurityConfig


async def explore_case_form():
    """Explore the new case form fields."""
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
        element_handler = ElementHandler(page)

        # Login
        print("Logging in...")
        await client.navigate(config.meruscase_login_url)
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(2)

        email_input = await element_handler.find_input(
            field_name="email", label="Email", placeholder="Email"
        )
        if email_input:
            password_input = await element_handler.find_input(
                field_name="password", label="Password",
                placeholder="Password", css_selector="input[type='password']"
            )
            if password_input:
                await email_input.fill(config.meruscase_email)
                await password_input.fill(config.meruscase_password)
                login_button = await element_handler.find_button(
                    text="LOGIN", css_selector="button[type='submit']"
                )
                if login_button:
                    await login_button.click()
                    await page.wait_for_load_state("networkidle")
                    await asyncio.sleep(3)

        print(f"Logged in! Current URL: {page.url}")

        # Navigate to new case form
        print("\nNavigating to new case form...")
        new_case_url = f"{config.meruscase_base_url}/cms#/caseFiles/add?t=1&lpt=0&nr=1&lpa=0"
        await page.goto(new_case_url)
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(3)  # Wait for Angular to render

        print(f"New case form URL: {page.url}")

        # Take screenshot
        screenshot_path = Path("./knowledge/screenshots/new_case_form.png")
        await page.screenshot(path=str(screenshot_path), full_page=True)
        print(f"Screenshot: {screenshot_path}")

        # Find all form fields
        print("\n" + "="*70)
        print("FORM FIELDS")
        print("="*70)

        # All inputs
        inputs = await page.query_selector_all("input:not([type='hidden']), select, textarea")
        for i, inp in enumerate(inputs[:40]):
            try:
                tag = await inp.evaluate("el => el.tagName")
                name = await inp.get_attribute("name") or ""
                id_attr = await inp.get_attribute("id") or ""
                type_attr = await inp.get_attribute("type") or ""
                placeholder = await inp.get_attribute("placeholder") or ""
                ng_model = await inp.get_attribute("ng-model") or ""
                classes = await inp.get_attribute("class") or ""

                # Get label if any
                label_text = ""
                if id_attr:
                    label = await page.query_selector(f"label[for='{id_attr}']")
                    if label:
                        label_text = (await label.inner_text()).strip()

                # Get parent label text
                parent_label = await inp.evaluate("""el => {
                    let parent = el.closest('.form-group, .input-group, .field-container');
                    if (parent) {
                        let label = parent.querySelector('label, .label, .field-label');
                        return label ? label.innerText.trim() : '';
                    }
                    return '';
                }""")

                print(f"\n[{i+1}] <{tag.lower()}>")
                if name: print(f"    name: {name}")
                if id_attr: print(f"    id: {id_attr}")
                if type_attr: print(f"    type: {type_attr}")
                if placeholder: print(f"    placeholder: {placeholder}")
                if ng_model: print(f"    ng-model: {ng_model}")
                if label_text: print(f"    label: {label_text}")
                if parent_label: print(f"    parent-label: {parent_label}")

            except Exception as e:
                pass

        # Look for specific case-related fields
        print("\n" + "="*70)
        print("SEARCHING FOR KEY FIELDS")
        print("="*70)

        key_fields = [
            ("Primary Party / Client", "input[ng-model*='party'], input[ng-model*='client'], input[name*='party'], input[name*='client']"),
            ("Case Type", "select[ng-model*='type'], select[name*='type'], select[ng-model*='caseType']"),
            ("Case Status", "select[ng-model*='status'], select[name*='status']"),
            ("Attorney", "select[ng-model*='attorney'], input[ng-model*='attorney']"),
            ("Office", "select[ng-model*='office'], input[ng-model*='office']"),
        ]

        for field_name, selector in key_fields:
            try:
                el = await page.query_selector(selector)
                if el:
                    actual_name = await el.get_attribute("name") or await el.get_attribute("ng-model") or ""
                    print(f"  FOUND: {field_name} -> {actual_name}")
                else:
                    print(f"  NOT FOUND: {field_name}")
            except:
                print(f"  ERROR: {field_name}")

        # Get all visible text that might be labels
        print("\n" + "="*70)
        print("VISIBLE LABELS (first 30)")
        print("="*70)

        labels = await page.query_selector_all("label, .label, .field-label, th")
        for i, label in enumerate(labels[:30]):
            try:
                text = (await label.inner_text()).strip()
                if text and len(text) < 50:
                    print(f"  {text}")
            except:
                pass

        print("\n" + "="*70)
        print("Keep browser open for 60 seconds for manual inspection...")
        print("="*70)
        await asyncio.sleep(60)

    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(explore_case_form())
