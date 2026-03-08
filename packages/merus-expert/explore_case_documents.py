"""Explore MerusCase - Navigate to a case and discover document upload UI"""
import sys
sys.path.insert(0, r"C:\Users\windo\OneDrive\Desktop\Claude_Code\projects\merus-expert")

import asyncio
import logging
import os
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

SCREENSHOT_DIR = r"C:\Users\windo\OneDrive\Desktop\Claude_Code\projects\merus-expert\knowledge\screenshots"


async def explore_case_documents():
    """Navigate to a case and explore its document upload UI."""
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
        await client.page.wait_for_load_state("networkidle", timeout=60000)
        await asyncio.sleep(3)

        await client.page.screenshot(path=f"{SCREENSHOT_DIR}/explore_00_login_page.png")

        # Try multiple selectors for email input
        email_selectors = [
            "input[placeholder='Email']",
            "input[type='text']:first-child",
            "form input:first-of-type",
            "input:visible:first",
        ]

        email_input = None
        for selector in email_selectors:
            try:
                el = client.page.locator(selector).first
                if await el.is_visible(timeout=5000):
                    email_input = el
                    logger.info(f"Found email input with: {selector}")
                    break
            except:
                continue

        if not email_input:
            # Fall back to getting all inputs
            inputs = client.page.locator("input:visible")
            count = await inputs.count()
            logger.info(f"Found {count} visible inputs")
            if count >= 2:
                email_input = inputs.nth(0)
                password_input = inputs.nth(1)
            else:
                raise Exception("Could not find login inputs")
        else:
            password_input = client.page.locator("input[placeholder='Password'], input[type='password']").first

        await email_input.fill(config.meruscase_email)
        await password_input.fill(config.meruscase_password)

        # Login button
        login_button = client.page.locator("button:has-text('LOGIN'), button:has-text('Login'), input[type='submit']").first
        await login_button.click()
        await client.page.wait_for_load_state("networkidle", timeout=30000)
        await asyncio.sleep(2)

        logger.info(f"Logged in. URL: {client.page.url}")
        await client.page.screenshot(path=f"{SCREENSHOT_DIR}/explore_01_logged_in.png")

        # Step 2: Click on Cases dropdown to see cases list
        logger.info("Step 2: Opening Cases dropdown...")
        cases_menu = client.page.locator("a:has-text('Cases')").first
        await cases_menu.click()
        await asyncio.sleep(1)
        await client.page.screenshot(path=f"{SCREENSHOT_DIR}/explore_02_cases_dropdown.png")

        # Step 3: Look for a search or list of cases
        logger.info("Step 3: Looking for case list or search...")

        # Try to find a search box for cases
        search_input = client.page.locator("input[placeholder*='Search'], input[type='search'], .search-input").first
        if await search_input.is_visible():
            logger.info("Found search box, searching for ANDREWS...")
            await search_input.fill("ANDREWS")
            await asyncio.sleep(2)
            await client.page.screenshot(path=f"{SCREENSHOT_DIR}/explore_03_search_results.png")

        # Step 4: Click on a case from the list/dropdown
        logger.info("Step 4: Looking for a case to click...")

        # Look for case link in dropdown or list
        case_selectors = [
            "a:has-text('ANDREWS')",
            "li:has-text('ANDREWS')",
            "tr:has-text('ANDREWS')",
            ".case-item:has-text('ANDREWS')",
            "[data-case]:has-text('ANDREWS')",
        ]

        case_clicked = False
        for selector in case_selectors:
            try:
                el = client.page.locator(selector).first
                if await el.is_visible():
                    logger.info(f"Found case: {selector}")
                    await el.click()
                    case_clicked = True
                    await asyncio.sleep(3)
                    break
            except:
                continue

        if not case_clicked:
            # Try to navigate to cases list view first
            logger.info("Trying to go to full cases list...")
            cases_list_link = client.page.locator("a[href*='caseFiles'], a:has-text('View All Cases')").first
            if await cases_list_link.is_visible():
                await cases_list_link.click()
                await asyncio.sleep(2)

        await client.page.screenshot(path=f"{SCREENSHOT_DIR}/explore_04_after_case_click.png")
        logger.info(f"URL after case interaction: {client.page.url}")

        # Step 5: Now look at the page structure - find document-related elements
        logger.info("Step 5: Analyzing page for document elements...")

        # Look for Documents tab/link within the case
        doc_selectors = [
            ".nav-tabs a:has-text('Documents')",
            ".tab:has-text('Documents')",
            "a[href*='documents']",
            "button:has-text('Documents')",
            "li:has-text('Documents') a",
            ".sidebar a:has-text('Documents')",
        ]

        for selector in doc_selectors:
            try:
                el = client.page.locator(selector).first
                if await el.is_visible():
                    logger.info(f"Found documents element: {selector}")
                    await el.click()
                    await asyncio.sleep(2)
                    break
            except:
                continue

        await client.page.screenshot(path=f"{SCREENSHOT_DIR}/explore_05_documents_area.png")
        logger.info(f"URL in documents area: {client.page.url}")

        # Step 6: Look for Add/Upload document button
        logger.info("Step 6: Looking for upload controls...")

        upload_selectors = [
            "button:has-text('Add')",
            "button:has-text('Upload')",
            "button:has-text('New Document')",
            "a:has-text('Add Document')",
            "button:has-text('Add Document')",
            "[title*='Add']",
            "[title*='Upload']",
            ".btn-add",
            ".upload-btn",
            "input[type='file']",
        ]

        for selector in upload_selectors:
            try:
                el = client.page.locator(selector).first
                if await el.is_visible():
                    logger.info(f"Found upload control: {selector}")
                    # Don't click file input, just report
                    if "input[type='file']" not in selector:
                        await el.click()
                        await asyncio.sleep(2)
                    break
            except:
                continue

        await client.page.screenshot(path=f"{SCREENSHOT_DIR}/explore_06_upload_dialog.png")

        # Step 7: Check for file input
        logger.info("Step 7: Looking for file input...")
        file_inputs = client.page.locator("input[type='file']")
        count = await file_inputs.count()
        logger.info(f"Found {count} file input(s)")

        for i in range(count):
            el = file_inputs.nth(i)
            attrs = {
                "id": await el.get_attribute("id"),
                "name": await el.get_attribute("name"),
                "accept": await el.get_attribute("accept"),
                "multiple": await el.get_attribute("multiple"),
            }
            logger.info(f"  File input {i}: {attrs}")

        # Final screenshot
        await client.page.screenshot(path=f"{SCREENSHOT_DIR}/explore_07_final.png", full_page=True)

        logger.info("\n=== Exploration Complete ===")
        logger.info(f"Final URL: {client.page.url}")
        logger.info(f"Screenshots saved to: {SCREENSHOT_DIR}")

    except Exception as e:
        logger.error(f"Exploration failed: {e}")
        import traceback
        traceback.print_exc()
        await client.page.screenshot(path=f"{SCREENSHOT_DIR}/explore_error.png")
    finally:
        await client.disconnect()


if __name__ == "__main__":
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    asyncio.run(explore_case_documents())
