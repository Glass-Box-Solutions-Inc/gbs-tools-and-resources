"""Batch upload documents to ANDREWS JARED case in 375MB chunks."""
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
        logging.FileHandler(os.path.join(LOG_DIR, f"upload_batch_jared_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"), encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Configuration
FOLDER_PATH = r"C:\4850 Law\ANDREWS JARED_Case3724"
CASE_ID = 56171872  # New case ID for ANDREWS JARED
MAX_BATCH_SIZE_MB = 250
MERUSCASE_EMAIL = os.getenv("MERUSCASE_EMAIL")
MERUSCASE_PASSWORD = os.getenv("MERUSCASE_PASSWORD")
BASE_URL = "https://meruscase.com"


def get_file_batches(folder_path: str, max_mb: float = 250, max_files: int = 100):
    """Split files into batches respecting both size and file count limits.

    MerusCase limits: 100 documents per upload, 384 MB per file.
    """
    folder = Path(folder_path)
    files = []

    # Get all files with their sizes
    for f in sorted(folder.iterdir()):
        if f.is_file():
            size_mb = f.stat().st_size / (1024 * 1024)
            files.append({"path": str(f), "name": f.name, "size_mb": size_mb})

    # Create batches respecting BOTH limits
    batches = []
    current_batch = []
    current_size = 0

    for f in files:
        # Start new batch if EITHER limit would be exceeded
        if (current_size + f["size_mb"] > max_mb or len(current_batch) >= max_files) and current_batch:
            batches.append(current_batch)
            current_batch = [f]
            current_size = f["size_mb"]
        else:
            current_batch.append(f)
            current_size += f["size_mb"]

    # Add last batch
    if current_batch:
        batches.append(current_batch)

    return batches, files


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
    await asyncio.sleep(3)
    await page.wait_for_load_state("networkidle")
    return True


async def open_upload_tool(page):
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
        # Try alternative - navigate directly to upload URL
        upload_url = f"{BASE_URL}/cms#/uploads?rpt=0&case_file_id={CASE_ID}&t=0"
        await page.goto(upload_url)

    await asyncio.sleep(3)
    await page.wait_for_load_state("networkidle")
    logger.info("Upload Tool opened")
    return True


async def upload_batch(page, batch: list, batch_num: int, total_batches: int):
    """Upload a batch of files using regular file upload."""
    file_paths = [f["path"] for f in batch]
    batch_size_mb = sum(f["size_mb"] for f in batch)

    logger.info(f"Batch {batch_num}/{total_batches}: {len(batch)} files, {batch_size_mb:.1f} MB")

    try:
        # Find the regular file input (not the webkitdirectory one)
        file_input = page.locator("input[name='data[Upload][submitted_files][]']").first

        if not await file_input.count():
            # Try alternative selector
            file_input = page.locator("input[type='file'][multiple]:not([webkitdirectory])").first

        if not await file_input.count():
            logger.error("Could not find regular file input")
            return {"status": "failed", "error": "File input not found"}

        # Set all files in this batch
        await file_input.set_input_files(file_paths)
        logger.info(f"Added {len(file_paths)} files to upload queue")

        # Wait for files to be queued
        await asyncio.sleep(3)

        # Click Upload button
        upload_btn = page.locator("button:has-text('Upload')").first
        if await upload_btn.is_visible(timeout=10000):
            await upload_btn.click()
            logger.info("Upload button clicked, waiting for completion...")

            # Wait for upload - generous timeout based on batch size
            wait_time = max(120, int(batch_size_mb * 2))  # ~2 seconds per MB
            logger.info(f"Waiting up to {wait_time} seconds for upload...")

            start_time = asyncio.get_event_loop().time()
            while asyncio.get_event_loop().time() - start_time < wait_time:
                try:
                    if await page.locator("button:has-text('Upload More Documents')").is_visible(timeout=2000):
                        logger.info("Upload complete - 'Upload More Documents' button visible")
                        break
                    if await page.locator("text=documents attached").is_visible(timeout=1000):
                        logger.info("Upload complete - documents attached message visible")
                        break
                except:
                    pass
                await asyncio.sleep(5)

            # Verify the batch upload before dismissing modal
            verification = await verify_batch_upload(page, len(batch))
            logger.info(f"Batch verification: {verification['message']}")

            if not verification["success"]:
                logger.warning(f"Batch verification: expected {len(batch)}, got {verification.get('actual', 'unknown')}")
                await capture_verification_screenshot(page, f"batch_{batch_num}_mismatch")

            # Dismiss any modal - we'll re-navigate to case for next batch
            await dismiss_modal(page)

            return {
                "status": "success" if verification.get("success", True) else "partial",
                "files": len(batch),
                "verified_count": verification.get("actual"),
                "size_mb": batch_size_mb,
                "verification": verification
            }
        else:
            logger.error("Upload button not visible")
            return {"status": "failed", "error": "Upload button not visible"}

    except Exception as e:
        logger.error(f"Batch upload failed: {e}")
        return {"status": "failed", "error": str(e)[:100]}


async def dismiss_modal(page):
    """Dismiss any upload modal."""
    try:
        buttons = [
            "button:has-text('Upload More Documents')",
            "button:has-text('Done')",
            "button:has-text('Close')",
            "button:has-text('OK')",
        ]
        for selector in buttons:
            btn = page.locator(selector).first
            if await btn.is_visible(timeout=1000):
                await btn.click()
                await asyncio.sleep(1)
                break
    except:
        pass

    # Force remove overlay
    await page.evaluate("""
        () => {
            document.querySelectorAll('.plainmodal-overlay, .modal-backdrop').forEach(el => el.remove());
            document.body.classList.remove('modal-open');
            document.body.style.overflow = '';
        }
    """)


async def verify_batch_upload(page, expected_count: int) -> dict:
    """Verify batch upload by parsing the success message."""
    import re

    try:
        # Extract the count from page text
        page_text = await page.inner_text("body")
        match = re.search(r'(\d+)\s+documents?\s+attached', page_text, re.IGNORECASE)

        if match:
            actual_count = int(match.group(1))
            success = (actual_count >= expected_count)

            return {
                "verified": True,
                "expected": expected_count,
                "actual": actual_count,
                "success": success,
                "message": f"Verified: {actual_count}/{expected_count} documents"
            }
        else:
            return {
                "verified": False,
                "expected": expected_count,
                "actual": None,
                "success": False,
                "message": "Could not parse document count from page"
            }
    except Exception as e:
        return {
            "verified": False,
            "expected": expected_count,
            "actual": None,
            "success": False,
            "message": f"Verification error: {str(e)}"
        }


async def verify_case_documents(page, case_id: int, expected_total: int) -> dict:
    """Navigate to case and count total documents."""
    import re

    try:
        # Navigate to case documents tab
        docs_url = f"{BASE_URL}/cms#/caseFiles/view/{case_id}?t=documents"
        await page.goto(docs_url)
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(3)

        # Look for document count in the UI - try multiple selectors
        selectors = [
            "tr[ng-repeat*='document']",
            ".document-row",
            "tr.document-item",
            "[data-document-id]",
            ".file-list-item"
        ]

        for selector in selectors:
            count = await page.locator(selector).count()
            if count > 0:
                return {
                    "verified": True,
                    "expected": expected_total,
                    "actual": count,
                    "success": (count >= expected_total),
                    "selector": selector
                }

        # Fallback: parse from page text (look for "Showing X of Y")
        page_text = await page.inner_text("body")
        match = re.search(r'Showing\s+\d+\s+of\s+(\d+)', page_text, re.IGNORECASE)
        if match:
            count = int(match.group(1))
            return {
                "verified": True,
                "expected": expected_total,
                "actual": count,
                "success": (count >= expected_total),
                "selector": "text_parse"
            }

        # Another fallback pattern
        match = re.search(r'(\d+)\s+(?:documents?|files?)', page_text, re.IGNORECASE)
        if match:
            count = int(match.group(1))
            return {
                "verified": True,
                "expected": expected_total,
                "actual": count,
                "success": (count >= expected_total),
                "selector": "text_parse"
            }

        return {
            "verified": False,
            "expected": expected_total,
            "actual": 0,
            "success": False,
            "message": "Could not find document list"
        }

    except Exception as e:
        return {
            "verified": False,
            "expected": expected_total,
            "actual": None,
            "success": False,
            "message": str(e)
        }


async def capture_verification_screenshot(page, context: str) -> str:
    """Capture screenshot as verification evidence."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    screenshot_dir = os.path.join(PROJECT_DIR, "screenshots", "verification")
    os.makedirs(screenshot_dir, exist_ok=True)

    screenshot_path = os.path.join(screenshot_dir, f"{context}_{timestamp}.png")
    await page.screenshot(path=screenshot_path, full_page=True)
    logger.info(f"Screenshot saved: {screenshot_path}")

    return screenshot_path


async def main():
    """Upload all files in batches."""
    # Analyze folder and create batches
    batches, all_files = get_file_batches(FOLDER_PATH, MAX_BATCH_SIZE_MB)

    total_files = len(all_files)
    total_size_mb = sum(f["size_mb"] for f in all_files)

    print(f"\n{'='*60}")
    print("BATCH UPLOAD - ANDREWS JARED")
    print(f"{'='*60}\n")
    print(f"Total files: {total_files}")
    print(f"Total size: {total_size_mb:.1f} MB")
    print(f"Max batch size: {MAX_BATCH_SIZE_MB} MB")
    print(f"Number of batches: {len(batches)}")
    print()

    for i, batch in enumerate(batches):
        batch_size = sum(f["size_mb"] for f in batch)
        print(f"  Batch {i+1}: {len(batch)} files, {batch_size:.1f} MB")
    print()

    results = {"success": 0, "failed": 0, "partial": 0, "files_uploaded": 0, "verified_uploaded": 0, "mb_uploaded": 0}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await context.new_page()

        try:
            await login(page)

            for i, batch in enumerate(batches):
                batch_num = i + 1
                print(f"\n[Batch {batch_num}/{len(batches)}] Uploading {len(batch)} files...")

                # Navigate to case and open upload tool BEFORE each batch
                await navigate_to_case(page, CASE_ID)
                await open_upload_tool(page)

                result = await upload_batch(page, batch, batch_num, len(batches))

                if result["status"] == "success":
                    results["success"] += 1
                    results["files_uploaded"] += result["files"]
                    results["verified_uploaded"] += result.get("verified_count") or result["files"]
                    results["mb_uploaded"] += result["size_mb"]
                    verified = result.get("verified_count", "?")
                    print(f"  [OK] Uploaded {result['files']} files ({result['size_mb']:.1f} MB) - Verified: {verified}")
                elif result["status"] == "partial":
                    results["partial"] += 1
                    results["files_uploaded"] += result["files"]
                    results["verified_uploaded"] += result.get("verified_count") or 0
                    results["mb_uploaded"] += result["size_mb"]
                    verified = result.get("verified_count", "?")
                    print(f"  [PARTIAL] Expected {result['files']}, verified {verified} ({result['size_mb']:.1f} MB)")
                else:
                    results["failed"] += 1
                    print(f"  [FAIL] {result.get('error', 'Unknown')}")

                # 5-second pause between batches
                if batch_num < len(batches):
                    print("  Pausing 5 seconds before next batch...")
                    await asyncio.sleep(5)

            # Final verification - navigate to case documents and count total
            print(f"\n{'='*60}")
            print("FINAL VERIFICATION")
            print(f"{'='*60}")
            logger.info("Performing final case document verification...")

            final_verification = await verify_case_documents(page, CASE_ID, total_files)
            await capture_verification_screenshot(page, "final_verification")

            if final_verification["verified"]:
                actual = final_verification.get("actual", "Unknown")
                status = "PASS" if final_verification["success"] else "FAIL"
                print(f"  Expected: {total_files} documents")
                print(f"  Actual:   {actual} documents")
                print(f"  Status:   {status}")
                if not final_verification["success"]:
                    print(f"  Missing:  {total_files - (actual or 0)} documents")
            else:
                print(f"  Verification failed: {final_verification.get('message', 'Unknown error')}")

            # Summary
            print(f"\n{'='*60}")
            print("SUMMARY")
            print(f"{'='*60}")
            print(f"Batches successful: {results['success']}/{len(batches)}")
            print(f"Batches partial: {results['partial']}/{len(batches)}")
            print(f"Files uploaded: {results['files_uploaded']}/{total_files}")
            print(f"Verified uploaded: {results['verified_uploaded']}/{total_files}")
            print(f"Data uploaded: {results['mb_uploaded']:.1f}/{total_size_mb:.1f} MB")
            print(f"Final verification: {'PASS' if final_verification.get('success') else 'FAIL'}")

            # Save results
            results_file = os.path.join(LOG_DIR, f"upload_batch_jared_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
            with open(results_file, "w", encoding="utf-8") as f:
                f.write(f"BATCH UPLOAD RESULTS - ANDREWS JARED\n{'='*60}\n")
                f.write(f"Case ID: {CASE_ID}\n")
                f.write(f"Total batches: {len(batches)}\n")
                f.write(f"Successful: {results['success']}\n")
                f.write(f"Partial: {results['partial']}\n")
                f.write(f"Failed: {results['failed']}\n")
                f.write(f"Files uploaded: {results['files_uploaded']}/{total_files}\n")
                f.write(f"Verified uploaded: {results['verified_uploaded']}/{total_files}\n")
                f.write(f"Data uploaded: {results['mb_uploaded']:.1f}/{total_size_mb:.1f} MB\n")
                f.write(f"\nFINAL VERIFICATION:\n")
                f.write(f"  Expected: {total_files}\n")
                f.write(f"  Actual: {final_verification.get('actual', 'Unknown')}\n")
                f.write(f"  Status: {'PASS' if final_verification.get('success') else 'FAIL'}\n")

            print(f"\nResults saved: {results_file}")

        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
