"""Create all matters in MerusCase - Direct browser automation."""
import sys
sys.path.insert(0, r"C:\Users\windo\OneDrive\Desktop\Claude_Code\projects\merus-expert")

import asyncio
import logging
import os
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

from playwright.async_api import async_playwright

PROJECT_DIR = r"C:\Users\windo\OneDrive\Desktop\Claude_Code\projects\merus-expert"
LOG_DIR = os.path.join(PROJECT_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, f"batch_create_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"), encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Configuration
SOURCE_PATH = r"C:\4850 Law"
MERUSCASE_EMAIL = os.getenv("MERUSCASE_EMAIL")
MERUSCASE_PASSWORD = os.getenv("MERUSCASE_PASSWORD")
BASE_URL = "https://meruscase.com"

# Skip these (already created) - empty since everything was deleted
SKIP_FOLDERS = []


def get_folders():
    """Get list of client folders to process."""
    folders = []
    source = Path(SOURCE_PATH)
    for item in sorted(source.iterdir()):
        if item.is_dir() and item.name not in SKIP_FOLDERS:
            # Parse folder name: "LASTNAME FIRSTNAME_CaseXXXX" or "LASTNAME FIRSTNAME"
            name = item.name.split("_Case")[0] if "_Case" in item.name else item.name
            folders.append({"path": item, "name": name})
    return folders


async def login(page):
    """Login to MerusCase."""
    logger.info("Logging in to MerusCase...")
    await page.goto(f"{BASE_URL}/users/login")
    await page.wait_for_load_state("networkidle")
    await asyncio.sleep(3)  # Wait for page to fully load

    # MerusCase uses text input for email, not email type
    email_input = page.locator("input[type='text']").first
    await email_input.wait_for(state="visible", timeout=30000)
    await email_input.fill(MERUSCASE_EMAIL)

    # Fill password
    password_input = page.locator("input[placeholder='Password'], input[type='password']").first
    await password_input.fill(MERUSCASE_PASSWORD)

    # Click LOGIN button (MerusCase uses uppercase)
    login_btn = page.locator("button:has-text('LOGIN')").first
    await login_btn.click()

    # Wait for redirect to dashboard
    await page.wait_for_load_state("networkidle", timeout=30000)
    await asyncio.sleep(2)
    logger.info(f"Logged in: {page.url}")
    return True


async def create_single_matter(page, name):
    """Create a single matter in MerusCase."""
    # Parse name - format: "LASTNAME FIRSTNAME"
    parts = name.strip().split()
    if len(parts) >= 2:
        last_name = parts[0]
        first_name = " ".join(parts[1:])
    else:
        last_name = name
        first_name = ""

    logger.info(f"Creating matter: {last_name}, {first_name}")

    # Navigate to add case form
    add_url = f"{BASE_URL}/cms#/caseFiles/add?t=1&lpt=0&nr=1&lpa=0"
    await page.goto(add_url)

    # Wait for Angular SPA to load
    await asyncio.sleep(3)
    await page.wait_for_load_state("networkidle")

    # Wait for form to appear - look for the Last Name field
    try:
        last_name_input = page.locator("input[name='data[Contact][last_name]']").first
        await last_name_input.wait_for(state="visible", timeout=15000)
    except Exception as e:
        # Try alternative - wait for any input field on form
        logger.warning(f"Waiting for form with alternative method...")
        await page.wait_for_selector("form input[type='text']", state="visible", timeout=15000)
        last_name_input = page.locator("input[name='data[Contact][last_name]']").first

    # Fill Last Name
    await last_name_input.fill(last_name)
    logger.info(f"Filled Last Name: {last_name}")

    # Fill First Name
    first_name_input = page.locator("input[name='data[Contact][first_name]']").first
    await first_name_input.fill(first_name)
    logger.info(f"Filled First Name: {first_name}")

    # Wait for conflict check
    await asyncio.sleep(2)

    # Select Case Type - Workers' Compensation
    try:
        case_type_select = page.locator("select[name='data[CaseFile][case_type_id]']")
        if await case_type_select.is_visible(timeout=3000):
            # Look for Workers' Comp option
            options = await case_type_select.locator("option").all_text_contents()
            wc_option = next((opt for opt in options if "worker" in opt.lower() or "comp" in opt.lower()), None)
            if wc_option:
                await case_type_select.select_option(label=wc_option)
                logger.info(f"Selected Case Type: {wc_option}")
    except Exception as e:
        logger.warning(f"Could not set case type: {e}")

    # Click Save button
    save_btn = page.locator("button:has-text('Save'), input[type='submit'][value*='Save']").first
    await save_btn.click()

    # Wait for save to complete
    await asyncio.sleep(3)
    await page.wait_for_load_state("networkidle")

    # Check if we're on a case details page (URL should change from /add to /view/ID)
    current_url = page.url

    if "/caseFiles/view/" in current_url or ("/caseFiles/" in current_url and "/add" not in current_url):
        logger.info(f"Matter created: {current_url}")
        return {"status": "success", "url": current_url}
    else:
        # Check for success message on page
        success_msg = await page.locator(".alert-success, .success-message").is_visible()
        if success_msg:
            logger.info(f"Matter created (success message found)")
            return {"status": "success", "url": current_url}
        else:
            logger.warning(f"Uncertain result, URL: {current_url}")
            return {"status": "uncertain", "url": current_url}


async def main():
    """Create all matters."""
    folders = get_folders()

    print(f"\n{'='*60}")
    print("BATCH MATTER CREATION")
    print(f"{'='*60}\n")
    print(f"Found {len(folders)} folders to process\n")

    results = {"success": [], "failed": [], "uncertain": []}

    async with async_playwright() as p:
        # Launch browser
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await context.new_page()

        try:
            # Login once
            if not await login(page):
                logger.error("Login failed!")
                return

            # Create each matter
            for i, folder in enumerate(folders):
                name = folder["name"]
                print(f"\n[{i+1}/{len(folders)}] Creating: {name}")

                try:
                    result = await create_single_matter(page, name)

                    if result["status"] == "success":
                        results["success"].append({"name": name, "url": result["url"]})
                        print(f"  [OK] {result['url']}")
                    elif result["status"] == "uncertain":
                        results["uncertain"].append({"name": name, "url": result["url"]})
                        print(f"  [?] Uncertain: {result['url']}")
                    else:
                        results["failed"].append({"name": name, "error": result.get("error", "Unknown")})
                        print(f"  [FAIL] {result.get('error', 'Unknown')}")

                    # Brief pause between creations
                    await asyncio.sleep(2)

                except Exception as e:
                    error_str = str(e)[:100]
                    logger.error(f"Failed {name}: {error_str}")
                    print(f"  [FAIL] {error_str}")
                    results["failed"].append({"name": name, "error": error_str})

            # Summary
            print(f"\n{'='*60}")
            print("SUMMARY")
            print(f"{'='*60}")
            print(f"Success: {len(results['success'])}")
            print(f"Uncertain: {len(results['uncertain'])}")
            print(f"Failed: {len(results['failed'])}")

            if results["success"]:
                print(f"\nCreated ({len(results['success'])}):")
                for m in results["success"]:
                    print(f"  + {m['name']}")
                    print(f"    {m['url']}")

            if results["uncertain"]:
                print(f"\nUncertain ({len(results['uncertain'])}):")
                for m in results["uncertain"]:
                    print(f"  ? {m['name']}: {m['url']}")

            if results["failed"]:
                print(f"\nFailed ({len(results['failed'])}):")
                for m in results["failed"]:
                    print(f"  - {m['name']}: {m['error']}")

            # Save results
            results_file = os.path.join(LOG_DIR, f"matters_batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
            with open(results_file, "w", encoding="utf-8") as f:
                f.write(f"BATCH MATTER CREATION RESULTS\n")
                f.write(f"{'='*60}\n")
                f.write(f"Success: {len(results['success'])}\n")
                f.write(f"Uncertain: {len(results['uncertain'])}\n")
                f.write(f"Failed: {len(results['failed'])}\n\n")

                if results["success"]:
                    f.write("CREATED:\n")
                    for m in results["success"]:
                        f.write(f"  {m['name']}\n")
                        f.write(f"    URL: {m['url']}\n")

                if results["uncertain"]:
                    f.write("\nUNCERTAIN:\n")
                    for m in results["uncertain"]:
                        f.write(f"  {m['name']}: {m['url']}\n")

                if results["failed"]:
                    f.write("\nFAILED:\n")
                    for m in results["failed"]:
                        f.write(f"  {m['name']}: {m['error']}\n")

            print(f"\nResults saved: {results_file}")

        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
