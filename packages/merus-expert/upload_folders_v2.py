"""Upload all case folders using MerusCase Upload Tool - v2."""
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
        logging.FileHandler(os.path.join(LOG_DIR, f"upload_v2_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"), encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Configuration
SOURCE_PATH = r"C:\4850 Law"
MERUSCASE_EMAIL = os.getenv("MERUSCASE_EMAIL")
MERUSCASE_PASSWORD = os.getenv("MERUSCASE_PASSWORD")
BASE_URL = "https://meruscase.com"

# Mapping of folder names to MerusCase case IDs (new IDs from 12/31/2024)
CASE_MAPPING = {
    "ANDREWS DENNIS_Case3608": 56171783,
    "ANDREWS JARED_Case3724": 56171785,
    "BAKER ANDREW R_Case3145": 56171786,
    "BATISTE RUSSELL P_Case3365": 56171787,
    "BLACK KIMBERLY Y_Case3456": 56171788,
    "BRYANT JONATHAN A_Case3221": 56171789,
    "CHARRON JAMES F_Case3431": 56171791,
    "CONTRERAS BENNY L_Case3389": 56171792,
    "CONTRERAS RAUL_Case3697": 56171794,
    "DAVIS CHRISTINA Y_Case3241": 56171795,
    "DJERF SHAWN V_Case3376": 56171796,
    "ELIZONDO JAMES J_Case3013": 56171797,
    "EVERETT JOVITA R_Case3410": 56171798,
    "FLUKER JAN L_Case3201": 56171799,
    "FUORI JOSEPH W_Case3349": 56171800,
    "GARDNER KERRY D_Case3246": 56171802,
    "GREEN KIMBERLY_Case3711": 56171803,
    "GUTH ANDREW S_Case3260": 56171804,
    "HANNA MAGDY_Case3338": 56171805,
    "HERNANDEZ ROBERT L_Case3090": 56171806,
    "HORST AMY_Case3550": 56171807,
    "JOHNSON DWIGHT_Case3539": 56171809,
    "KIRLEY TERRENCE_Case3394": 56171810,
    "MONGE JOE_Case3708": 56171811,
    "MYERS TRENT S_Case3243": 56171812,
    "PANIAGUA MARIO_Case3454": 56171813,
    "PEDERSEN DAN M_Case3048": 56171814,
    "RODRIGUEZ GEORGE M_Case3694": 56171815,
    "ROHBOCK JEREMIAH_Case3695": 56171816,
    "RUPE CHRISTOPHER D_Case3228": 56171817,
    "SALERNO ALBERT L_Case3046": 56171818,
    "SEGLER RICKY_Case3768": 56171819,
    "SMITH WILLIAM J_Case3140": 56171820,
    "SNOW ROBERT_Case3702": 56171821,
    "SPANGLER GREGORY G_Case3678": 56171822,
    "VANDERLINDEN JASON M_Case3490": 56171823,
    "WAKELING MARK C_Case3111": 56171824,
    "WEBB EDWARD A_Case3405": 56171825,
    "WEBSTER CHRISTIAN V_Case3307": 56171826,
    "WEIDNER MICHAEL W_Case3364": 56171828,
    "YEADON CHARLES_Case3772": 56171829,
}

# Only upload first case for testing
ONLY_FOLDERS = ["ANDREWS DENNIS_Case3608"]
SKIP_FOLDERS = []


def get_folders_to_upload():
    """Get list of folders to upload with their case IDs."""
    folders = []
    source = Path(SOURCE_PATH)

    for item in sorted(source.iterdir()):
        if item.is_dir() and item.name not in SKIP_FOLDERS:
            # If ONLY_FOLDERS is set, only process those
            if ONLY_FOLDERS and item.name not in ONLY_FOLDERS:
                continue
            case_id = CASE_MAPPING.get(item.name)
            if case_id:
                file_count = len([f for f in item.iterdir() if f.is_file()])
                folders.append({
                    "path": str(item),
                    "name": item.name,
                    "case_id": case_id,
                    "file_count": file_count
                })
    return folders


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

    # Click Documents in main nav
    docs_menu = page.locator("nav a:has-text('Documents'), header a:has-text('Documents'), a.nav-link:has-text('Documents')").first
    try:
        await docs_menu.click(timeout=5000)
        await asyncio.sleep(1)
    except Exception as e:
        logger.warning(f"Documents menu click failed: {e}")
        # Try clicking anywhere first to close any open dropdowns
        await page.locator("body").click()
        await asyncio.sleep(1)
        await docs_menu.click(timeout=5000)
        await asyncio.sleep(1)

    # Click Upload Tool
    upload_tool = page.locator("a:has-text('Upload Tool')").first
    try:
        await upload_tool.wait_for(state="visible", timeout=5000)
        await upload_tool.click()
        await asyncio.sleep(3)
        await page.wait_for_load_state("networkidle")
        logger.info("Upload Tool opened")
        return True
    except Exception as e:
        logger.error(f"Upload Tool not found: {e}")
        return False


async def upload_folder_files(page, folder_path: str, folder_name: str):
    """Upload all files from a folder by clicking 'upload an entire folder' link.

    Workflow:
    1. Click the 'upload an entire folder' link in the instruction text
    2. Select the folder in the folder picker dialog
    3. Click Upload button
    4. Wait for completion
    """
    import re

    folder = Path(folder_path)
    file_count = len([f for f in folder.iterdir() if f.is_file()])

    if file_count == 0:
        logger.warning(f"No files in folder: {folder_name}")
        return {"status": "skipped", "error": "No files"}

    # Get all file paths in the folder
    file_paths = [str(f) for f in folder.iterdir() if f.is_file()]
    logger.info(f"Uploading {file_count} files from {folder_name}")

    try:
        # Step 1: Find and click the "upload an entire folder" link
        # This link is in the instruction text on the upload page
        folder_link = page.get_by_text("upload an entire folder")

        if not await folder_link.is_visible(timeout=5000):
            # Try alternative selectors
            folder_link = page.locator("a:has-text('upload an entire folder')").first

        if not await folder_link.is_visible(timeout=3000):
            logger.error("Could not find 'upload an entire folder' link")
            return {"status": "failed", "error": "Folder upload link not found"}

        logger.info("Found 'upload an entire folder' link")

        # Step 2: Find the hidden webkitdirectory input that the link triggers
        folder_input = page.locator("input[webkitdirectory]").first

        if not await folder_input.count():
            folder_input = page.locator("input[name='data[Upload][folder]']").first

        if not await folder_input.count():
            logger.error("Could not find folder input element")
            return {"status": "failed", "error": "Folder input not found"}

        # Step 3: Set the folder path directly on the webkitdirectory input
        # This bypasses the file chooser dialog which Playwright can't handle well
        logger.info(f"Setting folder path on webkitdirectory input: {folder_path}")
        await folder_input.set_input_files(folder_path)
        logger.info(f"Folder path set, waiting for files to queue...")

        # Wait for ALL files to be queued in the UI (longer wait for large folders)
        queue_wait = max(10, file_count // 10)  # At least 10 seconds, +1 sec per 10 files
        logger.info(f"Waiting {queue_wait} seconds for {file_count} files to queue...")
        await asyncio.sleep(queue_wait)

        # Step 4: Click Upload button
        upload_btn = page.locator("button:has-text('Upload')").first
        if await upload_btn.is_visible(timeout=10000):
            await upload_btn.click()
            logger.info("Upload button clicked, waiting for upload to complete...")

            # Dynamic wait time based on file count (10 seconds per file, min 60 seconds)
            wait_time = max(60, file_count * 10)
            logger.info(f"Waiting up to {wait_time} seconds for {file_count} files...")

            # Wait for upload with progress monitoring
            start_time = asyncio.get_event_loop().time()
            while asyncio.get_event_loop().time() - start_time < wait_time:
                try:
                    # Look for success modal or completion message
                    if await page.locator("text=documents attached").is_visible(timeout=2000):
                        logger.info("Upload completion detected")
                        break
                    if await page.locator("button:has-text('Upload More Documents')").is_visible(timeout=1000):
                        logger.info("Upload More Documents button visible - upload complete")
                        break
                except:
                    pass
                await asyncio.sleep(5)

            # Verify upload count
            try:
                page_text = await page.inner_text("body")
                match = re.search(r'(\d+)\s+documents?\s+attached', page_text)
                if match:
                    actual_uploaded = int(match.group(1))
                    logger.info(f"Verified: {actual_uploaded} documents attached")
                    if actual_uploaded < file_count:
                        logger.warning(f"Only {actual_uploaded}/{file_count} files uploaded!")
            except Exception as e:
                logger.warning(f"Could not verify upload count: {e}")

            await dismiss_modal(page)
            logger.info(f"Upload complete: {file_count} files")
            return {"status": "success", "files": file_count}
        else:
            logger.error("Upload button not visible")
            return {"status": "failed", "error": "Upload button not visible"}

    except Exception as e:
        logger.error(f"Upload failed: {e}")
        return {"status": "failed", "error": str(e)[:100]}


async def dismiss_modal(page):
    """Dismiss any upload modal."""
    try:
        # Try clicking various modal dismiss buttons
        buttons = [
            "button:has-text('Upload More Documents')",
            "button:has-text('Done')",
            "button:has-text('Close')",
            "button:has-text('OK')",
        ]
        for selector in buttons:
            btn = page.locator(selector).first
            if await btn.is_visible(timeout=2000):
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


async def upload_to_case(page, case_id: int, folder_path: str, folder_name: str):
    """Upload a folder to a specific case."""
    logger.info(f"Processing case {case_id}: {folder_name}")

    # Navigate to case
    await navigate_to_case(page, case_id)

    # Open upload tool
    if not await open_upload_tool(page):
        return {"status": "failed", "error": "Could not open Upload Tool"}

    # Upload files
    return await upload_folder_files(page, folder_path, folder_name)


async def main():
    """Upload all folders."""
    folders = get_folders_to_upload()

    print(f"\n{'='*60}")
    print("UPLOAD ALL CASE FOLDERS - v2")
    print(f"{'='*60}\n")
    print(f"Folders to upload: {len(folders)}")
    total_files = sum(f["file_count"] for f in folders)
    print(f"Total files: {total_files}\n")

    results = {"success": [], "failed": []}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await context.new_page()

        try:
            await login(page)

            for i, folder in enumerate(folders):
                print(f"\n[{i+1}/{len(folders)}] {folder['name']} ({folder['file_count']} files)")

                result = await upload_to_case(
                    page,
                    folder["case_id"],
                    folder["path"],
                    folder["name"]
                )

                if result["status"] == "success":
                    results["success"].append({
                        "name": folder["name"],
                        "files": result.get("files", folder["file_count"])
                    })
                    print(f"  [OK] Uploaded {result.get('files', '?')} files")
                else:
                    results["failed"].append({
                        "name": folder["name"],
                        "error": result.get("error", "Unknown")
                    })
                    print(f"  [FAIL] {result.get('error', 'Unknown')}")

                # 30-second pause between cases
                if i < len(folders) - 1:  # Don't pause after last folder
                    print("  Pausing 30 seconds before next case...")
                    await asyncio.sleep(30)

            # Summary
            print(f"\n{'='*60}")
            print("SUMMARY")
            print(f"{'='*60}")
            print(f"Success: {len(results['success'])}")
            print(f"Failed: {len(results['failed'])}")

            total_uploaded = sum(r.get("files", 0) for r in results["success"])
            print(f"Total files uploaded: {total_uploaded}")

            # Save results
            results_file = os.path.join(LOG_DIR, f"upload_v2_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
            with open(results_file, "w", encoding="utf-8") as f:
                f.write(f"UPLOAD RESULTS\n{'='*60}\n")
                f.write(f"Success: {len(results['success'])}\n")
                f.write(f"Failed: {len(results['failed'])}\n")
                f.write(f"Files uploaded: {total_uploaded}\n\n")

                for r in results["success"]:
                    f.write(f"+ {r['name']} ({r['files']} files)\n")

                if results["failed"]:
                    f.write("\nFAILED:\n")
                    for r in results["failed"]:
                        f.write(f"- {r['name']}: {r['error']}\n")

            print(f"\nResults saved: {results_file}")

        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
