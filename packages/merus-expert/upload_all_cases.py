"""Upload all case folders with verification - MerusCase batch upload."""
import sys
sys.path.insert(0, r"C:\Users\windo\OneDrive\Desktop\Claude_Code\projects\merus-expert")

import asyncio
import logging
import os
import re
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
        logging.FileHandler(os.path.join(LOG_DIR, f"upload_all_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"), encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Configuration
SOURCE_PATH = r"C:\4850 Law"
MAX_BATCH_SIZE_MB = 250
MAX_FILES_PER_BATCH = 100
MERUSCASE_EMAIL = os.getenv("MERUSCASE_EMAIL")
MERUSCASE_PASSWORD = os.getenv("MERUSCASE_PASSWORD")
BASE_URL = "https://meruscase.com"

# Case mapping - folder name to MerusCase case ID (from 12/31/2024 batch creation)
CASE_MAPPING = {
    "ANDREWS DENNIS_Case3608": 56171871,
    "ANDREWS JARED_Case3724": 56171872,
    "BAKER ANDREW R_Case3145": 56171873,
    "BATISTE RUSSELL P_Case3365": 56171875,
    "BLACK KIMBERLY Y_Case3456": 56171876,
    "BRYANT JONATHAN A_Case3221": 56171877,
    "CHARRON JAMES F_Case3431": 56171878,
    "CONTRERAS BENNY L_Case3389": 56171879,
    "CONTRERAS RAUL_Case3697": 56171881,
    "DAVIS CHRISTINA Y_Case3241": 56171882,
    "DJERF SHAWN V_Case3376": 56171883,
    "ELIZONDO JAMES J_Case3013": 56171884,
    "EVERETT JOVITA R_Case3410": 56171885,
    "FLUKER JAN L_Case3201": 56171886,
    "FUORI JOSEPH W_Case3349": 56171888,
    "GARDNER KERRY D_Case3246": 56171889,
    "GREEN KIMBERLY_Case3711": 56171890,
    "GUTH ANDREW S_Case3260": 56171891,
    "HANNA MAGDY_Case3338": 56171893,
    "HERNANDEZ ROBERT L_Case3090": 56171894,
    "HORST AMY_Case3550": 56171895,
    "JOHNSON DWIGHT_Case3539": 56171896,
    "KIRLEY TERRENCE_Case3394": 56171897,
    "MONGE JOE_Case3708": 56171898,
    "MYERS TRENT S_Case3243": 56171899,
    "PANIAGUA MARIO_Case3454": 56171900,
    "PEDERSEN DAN M_Case3048": 56171901,
    "RODRIGUEZ GEORGE M_Case3694": 56171902,
    "ROHBOCK JEREMIAH_Case3695": 56171903,
    "RUPE CHRISTOPHER D_Case3228": 56171904,
    "SALERNO ALBERT L_Case3046": 56171905,
    "SEGLER RICKY_Case3768": 56171906,
    "SMITH WILLIAM J_Case3140": 56171907,
    "SNOW ROBERT_Case3702": 56171909,
    "SPANGLER GREGORY G_Case3678": 56171910,
    "VANDERLINDEN JASON M_Case3490": 56171911,
    "WAKELING MARK C_Case3111": 56171912,
    "WEBB EDWARD A_Case3405": 56171913,
    "WEBSTER CHRISTIAN V_Case3307": 56171914,
    "WEIDNER MICHAEL W_Case3364": 56171915,
    "YEADON CHARLES_Case3772": 56171916,
}

# Skip these cases (already uploaded)
SKIP_CASES = ["ANDREWS JARED_Case3724"]


def get_file_batches(folder_path: str, max_mb: float = 250, max_files: int = 100):
    """Split files into batches respecting both size and file count limits."""
    folder = Path(folder_path)
    files = []

    for f in sorted(folder.iterdir()):
        if f.is_file():
            size_mb = f.stat().st_size / (1024 * 1024)
            files.append({"path": str(f), "name": f.name, "size_mb": size_mb})

    batches = []
    current_batch = []
    current_size = 0

    for f in files:
        if (current_size + f["size_mb"] > max_mb or len(current_batch) >= max_files) and current_batch:
            batches.append(current_batch)
            current_batch = [f]
            current_size = f["size_mb"]
        else:
            current_batch.append(f)
            current_size += f["size_mb"]

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


async def open_upload_tool(page, case_id: int):
    """Open the Upload Tool."""
    logger.info("Opening Upload Tool...")

    docs_menu = page.locator("nav a:has-text('Documents'), header a:has-text('Documents')").first
    try:
        await docs_menu.click(timeout=5000)
        await asyncio.sleep(2)
    except:
        await page.locator("body").click()
        await asyncio.sleep(1)
        await docs_menu.click(timeout=5000)
        await asyncio.sleep(2)

    upload_tool = page.locator("a:has-text('Upload Tool')").first
    try:
        await upload_tool.click(timeout=5000)
    except:
        upload_url = f"{BASE_URL}/cms#/uploads?rpt=0&case_file_id={case_id}&t=0"
        await page.goto(upload_url)

    await asyncio.sleep(3)
    await page.wait_for_load_state("networkidle")
    logger.info("Upload Tool opened")
    return True


async def upload_batch(page, batch: list, batch_num: int, total_batches: int):
    """Upload a batch of files."""
    file_paths = [f["path"] for f in batch]
    batch_size_mb = sum(f["size_mb"] for f in batch)

    logger.info(f"Batch {batch_num}/{total_batches}: {len(batch)} files, {batch_size_mb:.1f} MB")

    try:
        file_input = page.locator("input[name='data[Upload][submitted_files][]']").first

        if not await file_input.count():
            file_input = page.locator("input[type='file'][multiple]:not([webkitdirectory])").first

        if not await file_input.count():
            logger.error("Could not find regular file input")
            return {"status": "failed", "error": "File input not found"}

        await file_input.set_input_files(file_paths)
        logger.info(f"Added {len(file_paths)} files to upload queue")

        await asyncio.sleep(3)

        upload_btn = page.locator("button:has-text('Upload')").first
        if await upload_btn.is_visible(timeout=10000):
            await upload_btn.click()
            logger.info("Upload button clicked, waiting for completion...")

            wait_time = max(120, int(batch_size_mb * 2))
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

            # Verify batch upload
            verification = await verify_batch_upload(page, len(batch))
            logger.info(f"Batch verification: {verification['message']}")

            if not verification["success"]:
                logger.warning(f"Batch verification: expected {len(batch)}, got {verification.get('actual', 'unknown')}")
                await capture_verification_screenshot(page, f"batch_{batch_num}_mismatch")

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

    await page.evaluate("""
        () => {
            document.querySelectorAll('.plainmodal-overlay, .modal-backdrop').forEach(el => el.remove());
            document.body.classList.remove('modal-open');
            document.body.style.overflow = '';
        }
    """)


async def verify_batch_upload(page, expected_count: int) -> dict:
    """Verify batch upload by parsing the success message."""
    try:
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
    try:
        docs_url = f"{BASE_URL}/cms#/caseFiles/view/{case_id}?t=documents"
        await page.goto(docs_url)
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(3)

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


async def upload_case(page, folder_name: str, case_id: int) -> dict:
    """Upload all files for a single case with verification."""
    folder_path = os.path.join(SOURCE_PATH, folder_name)

    if not os.path.exists(folder_path):
        return {"status": "failed", "error": "Folder not found", "folder": folder_name}

    batches, all_files = get_file_batches(folder_path, MAX_BATCH_SIZE_MB, MAX_FILES_PER_BATCH)
    total_files = len(all_files)
    total_size_mb = sum(f["size_mb"] for f in all_files)

    if total_files == 0:
        return {"status": "skipped", "error": "No files", "folder": folder_name}

    logger.info(f"Case {folder_name}: {total_files} files, {total_size_mb:.1f} MB, {len(batches)} batches")

    case_results = {
        "folder": folder_name,
        "case_id": case_id,
        "total_files": total_files,
        "total_size_mb": total_size_mb,
        "batches": len(batches),
        "batches_success": 0,
        "batches_partial": 0,
        "batches_failed": 0,
        "files_uploaded": 0,
        "verified_uploaded": 0,
        "final_verification": None
    }

    for i, batch in enumerate(batches):
        batch_num = i + 1

        # Navigate to case and open upload tool before each batch
        await navigate_to_case(page, case_id)
        await open_upload_tool(page, case_id)

        result = await upload_batch(page, batch, batch_num, len(batches))

        if result["status"] == "success":
            case_results["batches_success"] += 1
            case_results["files_uploaded"] += result["files"]
            case_results["verified_uploaded"] += result.get("verified_count") or result["files"]
        elif result["status"] == "partial":
            case_results["batches_partial"] += 1
            case_results["files_uploaded"] += result["files"]
            case_results["verified_uploaded"] += result.get("verified_count") or 0
        else:
            case_results["batches_failed"] += 1

        # 5-second pause between batches
        if batch_num < len(batches):
            await asyncio.sleep(5)

    # Final verification
    final_verification = await verify_case_documents(page, case_id, total_files)
    await capture_verification_screenshot(page, f"case_{case_id}_final")
    case_results["final_verification"] = final_verification

    if final_verification.get("success"):
        case_results["status"] = "success"
    elif case_results["batches_failed"] == 0:
        case_results["status"] = "partial"
    else:
        case_results["status"] = "failed"

    return case_results


async def main():
    """Upload all cases with verification."""
    # Get list of cases to upload
    cases_to_upload = []
    for folder_name, case_id in CASE_MAPPING.items():
        if folder_name not in SKIP_CASES:
            folder_path = os.path.join(SOURCE_PATH, folder_name)
            if os.path.exists(folder_path):
                file_count = len([f for f in Path(folder_path).iterdir() if f.is_file()])
                cases_to_upload.append({
                    "folder": folder_name,
                    "case_id": case_id,
                    "file_count": file_count
                })

    total_cases = len(cases_to_upload)
    total_files = sum(c["file_count"] for c in cases_to_upload)

    print(f"\n{'='*60}")
    print("UPLOAD ALL CASES WITH VERIFICATION")
    print(f"{'='*60}\n")
    print(f"Cases to upload: {total_cases}")
    print(f"Skipped cases: {len(SKIP_CASES)}")
    print(f"Total files: {total_files}")
    print()

    all_results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await context.new_page()

        try:
            await login(page)

            for i, case_info in enumerate(cases_to_upload):
                case_num = i + 1
                print(f"\n{'='*60}")
                print(f"[{case_num}/{total_cases}] {case_info['folder']}")
                print(f"  Case ID: {case_info['case_id']}, Files: {case_info['file_count']}")
                print(f"{'='*60}")

                result = await upload_case(page, case_info['folder'], case_info['case_id'])
                all_results.append(result)

                # Print case result
                if result["status"] == "success":
                    fv = result.get("final_verification", {})
                    actual = fv.get("actual", "?")
                    print(f"  [OK] Uploaded {result['files_uploaded']}/{result['total_files']} files")
                    print(f"  Final verification: {actual}/{result['total_files']} - PASS")
                elif result["status"] == "partial":
                    fv = result.get("final_verification", {})
                    actual = fv.get("actual", "?")
                    print(f"  [PARTIAL] Uploaded {result['files_uploaded']}/{result['total_files']} files")
                    print(f"  Final verification: {actual}/{result['total_files']} - INCOMPLETE")
                else:
                    print(f"  [FAIL] {result.get('error', 'Unknown error')}")

                # 10-second pause between cases
                if case_num < total_cases:
                    print("  Pausing 10 seconds before next case...")
                    await asyncio.sleep(10)

            # Final summary
            print(f"\n{'='*60}")
            print("FINAL SUMMARY")
            print(f"{'='*60}")

            success_count = sum(1 for r in all_results if r["status"] == "success")
            partial_count = sum(1 for r in all_results if r["status"] == "partial")
            failed_count = sum(1 for r in all_results if r["status"] == "failed")
            total_uploaded = sum(r.get("files_uploaded", 0) for r in all_results)
            total_verified = sum(r.get("verified_uploaded", 0) for r in all_results)

            print(f"Cases successful: {success_count}/{total_cases}")
            print(f"Cases partial: {partial_count}/{total_cases}")
            print(f"Cases failed: {failed_count}/{total_cases}")
            print(f"Files uploaded: {total_uploaded}/{total_files}")
            print(f"Files verified: {total_verified}/{total_files}")

            # Save detailed results
            results_file = os.path.join(LOG_DIR, f"upload_all_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
            with open(results_file, "w", encoding="utf-8") as f:
                f.write(f"UPLOAD ALL CASES - RESULTS\n{'='*60}\n")
                f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Cases processed: {total_cases}\n")
                f.write(f"Successful: {success_count}\n")
                f.write(f"Partial: {partial_count}\n")
                f.write(f"Failed: {failed_count}\n")
                f.write(f"Files uploaded: {total_uploaded}/{total_files}\n")
                f.write(f"Files verified: {total_verified}/{total_files}\n\n")

                f.write("CASE DETAILS:\n")
                f.write("-" * 60 + "\n")
                for r in all_results:
                    fv = r.get("final_verification", {})
                    fv_actual = fv.get("actual", "?")
                    fv_status = "PASS" if fv.get("success") else "FAIL"
                    f.write(f"\n{r['folder']}\n")
                    f.write(f"  Status: {r['status'].upper()}\n")
                    f.write(f"  Case ID: {r.get('case_id', '?')}\n")
                    f.write(f"  Files: {r.get('files_uploaded', 0)}/{r.get('total_files', 0)}\n")
                    f.write(f"  Verified: {r.get('verified_uploaded', 0)}/{r.get('total_files', 0)}\n")
                    f.write(f"  Final verification: {fv_actual}/{r.get('total_files', 0)} - {fv_status}\n")

            print(f"\nResults saved: {results_file}")

        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
