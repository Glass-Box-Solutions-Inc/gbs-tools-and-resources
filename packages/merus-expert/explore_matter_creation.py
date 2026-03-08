"""Explore MerusCase matter creation flow to understand URL behavior"""
import sys
sys.path.insert(0, r"C:\Users\windo\OneDrive\Desktop\Claude_Code\projects\merus-expert")

import asyncio
import logging
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

from browser.client import MerusCaseBrowserClient
from browser.element_handler import ElementHandler
from security.config import SecurityConfig

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def explore_matter_flow():
    """Explore the matter creation and document upload flow."""
    config = SecurityConfig.from_env()

    client = MerusCaseBrowserClient(
        api_token=config.browserless_api_token,
        endpoint=config.browserless_endpoint,
        headless=config.use_headless,
        use_local=config.use_local_browser
    )

    try:
        await client.connect()
        element_handler = ElementHandler(client.page)

        # Step 1: Login
        logger.info("Step 1: Logging in...")
        await client.navigate(config.meruscase_login_url)
        await asyncio.sleep(2)

        email_input = await element_handler.find_input(field_name="email", label="Email")
        password_input = await element_handler.find_input(
            field_name="password",
            label="Password",
            css_selector="input[type='password']"
        )

        if not email_input or not password_input:
            # Fallback to direct selectors
            email_input = client.page.locator("input[type='email'], input[name='email']").first
            password_input = client.page.locator("input[type='password']").first

        await email_input.fill(config.meruscase_email)
        await password_input.fill(config.meruscase_password)

        login_button = await element_handler.find_button(
            text="Sign In",
            css_selector="button[type='submit'], input[type='submit']"
        )
        await login_button.click()
        await client.page.wait_for_load_state("networkidle", timeout=30000)
        await asyncio.sleep(2)

        logger.info(f"Logged in. URL: {client.page.url}")
        await client.page.screenshot(path="screenshots/explore_1_logged_in.png")

        # Step 2: Navigate to cases list
        logger.info("Step 2: Looking for cases/matters list...")

        # Try to find a link to cases or matters
        case_links = [
            "a:has-text('Cases')",
            "a:has-text('Matters')",
            "a[href*='caseFiles']",
            "a[href*='matters']",
            ".nav-item:has-text('Cases')",
        ]

        for selector in case_links:
            try:
                el = client.page.locator(selector).first
                if await el.is_visible():
                    logger.info(f"Found cases link: {selector}")
                    await el.click()
                    await asyncio.sleep(2)
                    break
            except:
                continue

        logger.info(f"After clicking cases. URL: {client.page.url}")
        await client.page.screenshot(path="screenshots/explore_2_cases_list.png")

        # Step 3: Find and click first matter in the list
        logger.info("Step 3: Looking for a matter to click...")

        # Look for table rows or list items
        matter_selectors = [
            "table tbody tr:first-child",
            ".case-row:first-child",
            "[data-case]:first-child",
            "a[href*='caseFiles/']:not([href*='add'])",
        ]

        for selector in matter_selectors:
            try:
                el = client.page.locator(selector).first
                if await el.is_visible():
                    logger.info(f"Found matter row: {selector}")
                    await el.click()
                    await asyncio.sleep(3)
                    break
            except:
                continue

        logger.info(f"After clicking matter. URL: {client.page.url}")
        await client.page.screenshot(path="screenshots/explore_3_matter_detail.png")

        # Step 4: Look for Documents section
        logger.info("Step 4: Looking for Documents section...")

        doc_selectors = [
            "a:has-text('Documents')",
            "a:has-text('Files')",
            "li:has-text('Documents')",
            "[data-tab='documents']",
            ".tab:has-text('Documents')",
            "button:has-text('Documents')",
        ]

        for selector in doc_selectors:
            try:
                el = client.page.locator(selector).first
                if await el.is_visible():
                    logger.info(f"Found documents nav: {selector}")
                    await el.click()
                    await asyncio.sleep(2)
                    break
            except:
                continue

        logger.info(f"After clicking Documents. URL: {client.page.url}")
        await client.page.screenshot(path="screenshots/explore_4_documents_section.png")

        # Step 5: Look for Upload button
        logger.info("Step 5: Looking for Upload button...")

        upload_selectors = [
            "button:has-text('Add')",
            "button:has-text('Upload')",
            "a:has-text('Add Document')",
            "button:has-text('Add Document')",
            "[title*='Upload']",
            "[title*='Add']",
            ".add-btn",
            ".upload-btn",
        ]

        for selector in upload_selectors:
            try:
                el = client.page.locator(selector).first
                if await el.is_visible():
                    logger.info(f"Found upload button: {selector}")
                    await el.click()
                    await asyncio.sleep(2)
                    break
            except:
                continue

        logger.info(f"After clicking Upload. URL: {client.page.url}")
        await client.page.screenshot(path="screenshots/explore_5_upload_dialog.png")

        # Step 6: Look for file input
        logger.info("Step 6: Looking for file input...")

        file_input = client.page.locator("input[type='file']")
        count = await file_input.count()
        logger.info(f"Found {count} file inputs")

        if count > 0:
            for i in range(count):
                el = file_input.nth(i)
                if await el.is_visible() or await el.is_enabled():
                    input_id = await el.get_attribute("id")
                    input_name = await el.get_attribute("name")
                    input_accept = await el.get_attribute("accept")
                    logger.info(f"  File input {i}: id={input_id}, name={input_name}, accept={input_accept}")

        # Final screenshot
        await client.page.screenshot(path="screenshots/explore_6_final.png")

        logger.info("\nExploration complete! Check the screenshots folder for results.")

    except Exception as e:
        logger.error(f"Exploration failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await client.disconnect()


if __name__ == "__main__":
    import os
    os.makedirs("screenshots", exist_ok=True)
    asyncio.run(explore_matter_flow())
