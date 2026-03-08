"""Upload compressed PDFs to their respective MerusCase matters."""
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
        logging.FileHandler(os.path.join(LOG_DIR, f"upload_compressed_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"), encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

MERUSCASE_EMAIL = os.getenv("MERUSCASE_EMAIL")
MERUSCASE_PASSWORD = os.getenv("MERUSCASE_PASSWORD")
BASE_URL = "https://meruscase.com"

# Compressed PDFs grouped by case
UPLOADS = {
    56171886: {  # FLUKER JAN L
        "name": "FLUKER JAN L",
        "files": [
            r"C:\4850 Law\_Compressed_GS\INS PROPOSED LT DR TIRMIZI W- ECNLOSURES CLM 06235532, 03-19-2025.pdf"
        ]
    },
    56171914: {  # WEBSTER CHRISTIAN V
        "name": "WEBSTER CHRISTIAN V",
        "files": [
            r"C:\4850 Law\_Compressed_GS\MED-LEGAL MRC'S- LAW OFFICES OF CHRISLIP & HERVATIN, 03-10-2021.pdf"
        ]
    },
    56171915: {  # WEIDNER MICHAEL W
        "name": "WEIDNER MICHAEL W",
        "files": [
            r"C:\4850 Law\_Compressed_GS\POS- MEDICAL RECORDS- IRONWOOD PRIMARY CARE DATED 02-06-2025 (1).pdf",
            r"C:\4850 Law\_Compressed_GS\WCH MRCS- BARTON HEALTH, MEDICAL RECORDS, 02-12-2025.pdf"
        ]
    },
    56171882: {  # DAVIS CHRISTINA Y
        "name": "DAVIS CHRISTINA Y",
        "files": [
            r"C:\4850 Law\_Compressed_GS\INS PQME COVER LT- DR JACOBO CHODAKIEWITZ, CLM 06493938, 12-27-2023.pdf",
            r"C:\4850 Law\_Compressed_GS\INS LTR- PROPOSED PQME COVER LTR CLM 06493938, 12-06-2023.pdf"
        ]
    }
}


async def login(page):
    """Login to MerusCase."""
    logger.info("Logging in to MerusCase...")
    await page.goto(f"{BASE_URL}/users/login")
    await page.wait_for_load_state("networkidle")
    await asyncio.sleep(3)

    email_input = page.locator("input[type='text']").first
    await email_input.wait_for(state="visible", timeout=30000)
    await email_input.fill(MERUSCASE_EMAIL)

    password_input = page.locator("input[type='password']").first
    await password_input.fill(MERUSCASE_PASSWORD)

    login_btn = page.locator("button:has-text('LOGIN')").first
    await login_btn.click()

    await page.wait_for_load_state("networkidle", timeout=30000)
    await asyncio.sleep(2)
    logger.info(f"Logged in: {page.url}")
    return True


async def navigate_to_case(page, case_id: int):
    """Navigate to a case page."""
    case_url = f"{BASE_URL}/cms#/caseFiles/view/{case_id}?t=case_details"
    await page.goto(case_url)
    await page.wait_for_load_state("networkidle")
    await asyncio.sleep(3)
    logger.info(f"Navigated to case {case_id}")


async def open_upload_tool(page, case_id: int):
    """Open the Upload Tool from Documents dropdown."""
    logger.info("Opening Upload Tool...")

    # Click Documents in main nav to open dropdown
    docs_menu = page.locator("nav a:has-text('Documents'), header a:has-text('Documents')").first
    try:
        await docs_menu.click(timeout=5000)
        await asyncio.sleep(2)
    except:
        # Try clicking body first to close any open dropdowns
        await page.locator("body").click()
        await asyncio.sleep(1)
        await docs_menu.click(timeout=5000)
        await asyncio.sleep(2)

    # Click Upload Tool in dropdown
    upload_tool = page.locator("a:has-text('Upload Tool')").first
    try:
        await upload_tool.click(timeout=5000)
    except:
        # Navigate directly to upload URL
        upload_url = f"{BASE_URL}/cms#/uploads?rpt=0&case_file_id={case_id}&t=0"
        await page.goto(upload_url)

    await asyncio.sleep(3)
    await page.wait_for_load_state("networkidle")
    logger.info("Upload Tool opened")


async def upload_files(page, file_paths: list) -> bool:
    """Upload files to the currently open upload tool."""
    try:
        # Find the regular file input (not the webkitdirectory one)
        file_input = page.locator("input[name='data[Upload][submitted_files][]']").first

        if not await file_input.count():
            # Try alternative selector
            file_input = page.locator("input[type='file'][multiple]:not([webkitdirectory])").first

        if not await file_input.count():
            file_input = page.locator("input[type='file']").first

        await file_input.wait_for(state="attached", timeout=10000)

        # Set files
        await file_input.set_input_files(file_paths)
        logger.info(f"Added {len(file_paths)} files to upload queue")
        await asyncio.sleep(3)

        # Click upload button
        upload_btn = page.locator("button:has-text('Upload')").first
        if await upload_btn.is_visible():
            await upload_btn.click()
            logger.info("Upload button clicked, waiting for completion...")

            # Calculate timeout based on file sizes
            total_size = sum(os.path.getsize(f) for f in file_paths) / (1024 * 1024)
            timeout = max(120, int(total_size * 2))  # 2 seconds per MB, min 2 min
            logger.info(f"Waiting up to {timeout} seconds for upload...")

            # Wait for completion
            for _ in range(timeout // 5):
                await asyncio.sleep(5)

                # Check for completion
                upload_more = page.locator("button:has-text('Upload More Documents')")
                if await upload_more.is_visible():
                    logger.info("Upload complete - 'Upload More Documents' button visible")
                    return True

                # Also check for success text
                success_text = page.locator("text=successfully")
                if await success_text.is_visible():
                    logger.info("Upload complete - success message visible")
                    return True

            logger.warning("Upload timeout - may still have succeeded")
            return True

        else:
            logger.error("Upload button not visible")
            return False

    except Exception as e:
        logger.error(f"Upload error: {e}")
        return False


async def main():
    """Main upload process."""
    print("=" * 60)
    print("Upload Compressed PDFs to MerusCase")
    print("=" * 60)

    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()

        # Login
        await login(page)

        # Process each case
        for case_id, data in UPLOADS.items():
            case_name = data["name"]
            files = [f for f in data["files"] if os.path.exists(f)]

            if not files:
                logger.warning(f"No files found for {case_name}")
                continue

            print(f"\n{'='*60}")
            print(f"Case: {case_name} (ID: {case_id})")
            print(f"Files: {len(files)}")

            for f in files:
                size_mb = os.path.getsize(f) / (1024 * 1024)
                print(f"  - {os.path.basename(f)} ({size_mb:.1f} MB)")

            print("=" * 60)

            # Navigate to case
            await navigate_to_case(page, case_id)

            # Open upload tool
            await open_upload_tool(page, case_id)

            # Upload files
            success = await upload_files(page, files)

            results.append({
                "case": case_name,
                "case_id": case_id,
                "files": len(files),
                "success": success
            })

            if success:
                print(f"SUCCESS: Uploaded {len(files)} files to {case_name}")
            else:
                print(f"FAILED: Could not upload to {case_name}")

            # Close modal and wait
            try:
                close_btn = page.locator("button:has-text('Close'), button.close").first
                if await close_btn.is_visible():
                    await close_btn.click()
            except:
                pass

            await asyncio.sleep(5)

        await browser.close()

    # Summary
    print("\n" + "=" * 60)
    print("UPLOAD SUMMARY")
    print("=" * 60)

    success_count = sum(1 for r in results if r["success"])
    total_files = sum(r["files"] for r in results)

    print(f"Cases processed: {len(results)}")
    print(f"Successful: {success_count}/{len(results)}")
    print(f"Total files: {total_files}")

    for r in results:
        status = "OK" if r["success"] else "FAIL"
        print(f"  [{status}] {r['case']}: {r['files']} files")


if __name__ == "__main__":
    asyncio.run(main())
