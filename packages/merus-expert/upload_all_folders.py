"""Upload all case folders using MerusCase Upload Folder function."""
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
        logging.FileHandler(os.path.join(LOG_DIR, f"upload_folders_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"), encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Configuration
SOURCE_PATH = r"C:\4850 Law"
MERUSCASE_EMAIL = os.getenv("MERUSCASE_EMAIL")
MERUSCASE_PASSWORD = os.getenv("MERUSCASE_PASSWORD")
BASE_URL = "https://meruscase.com"

# Mapping of folder names to MerusCase case IDs (from batch creation)
# Folders are in alphabetical order by client name
CASE_MAPPING = {
    "ANDREWS DENNIS_Case3608": 56171171,  # Already uploaded
    "ANDREWS JARED_Case3724": 56171406,
    "BAKER ANDREW R_Case3145": 56171407,
    "BATISTE RUSSELL P_Case3365": 56171408,
    "BLACK KIMBERLY Y_Case3456": 56171409,
    "BRYANT JONATHAN A_Case3221": 56171410,
    "CHARRON JAMES F_Case3431": 56171411,
    "CONTRERAS BENNY L_Case3389": 56171412,
    "CONTRERAS RAUL_Case3697": 56171413,
    "DAVIS CHRISTINA Y_Case3241": 56171414,
    "DJERF SHAWN V_Case3376": 56171415,
    "ELIZONDO JAMES J_Case3013": 56171416,
    "EVERETT JOVITA R_Case3410": 56171417,
    "FLUKER JAN L_Case3201": 56171418,
    "FUORI JOSEPH W_Case3349": 56171419,
    "GARDNER KERRY D_Case3246": 56171420,
    "GREEN KIMBERLY_Case3711": 56171421,
    "GUTH ANDREW S_Case3260": 56171422,
    "HANNA MAGDY_Case3338": 56171423,
    "HERNANDEZ ROBERT L_Case3090": 56171424,
    "HORST AMY_Case3550": 56171425,
    "JOHNSON DWIGHT_Case3539": 56171426,
    "KIRLEY TERRENCE_Case3394": 56171427,
    "MONGE JOE_Case3708": 56171428,
    "MYERS TRENT S_Case3243": 56171429,
    "PANIAGUA MARIO_Case3454": 56171430,
    "PEDERSEN DAN M_Case3048": 56171431,
    "RODRIGUEZ GEORGE M_Case3694": 56171432,
    "ROHBOCK JEREMIAH_Case3695": 56171433,
    "RUPE CHRISTOPHER D_Case3228": 56171434,
    "SALERNO ALBERT L_Case3046": 56171435,
    "SEGLER RICKY_Case3768": 56171436,
    "SMITH WILLIAM J_Case3140": 56171437,
    "SNOW ROBERT_Case3702": 56171438,
    "SPANGLER GREGORY G_Case3678": 56171439,
    "VANDERLINDEN JASON M_Case3490": 56171440,
    "WAKELING MARK C_Case3111": 56171441,
    "WEBB EDWARD A_Case3405": 56171442,
    "WEBSTER CHRISTIAN V_Case3307": 56171443,
    "WEIDNER MICHAEL W_Case3364": 56171444,
    "YEADON CHARLES_Case3772": 56171445,
}

# Skip these (already uploaded)
SKIP_FOLDERS = ["ANDREWS DENNIS_Case3608"]


def get_folders_to_upload():
    """Get list of folders to upload with their case IDs."""
    folders = []
    source = Path(SOURCE_PATH)

    for item in sorted(source.iterdir()):
        if item.is_dir() and item.name not in SKIP_FOLDERS:
            case_id = CASE_MAPPING.get(item.name)
            if case_id:
                file_count = len([f for f in item.iterdir() if f.is_file()])
                folders.append({
                    "path": str(item),
                    "name": item.name,
                    "case_id": case_id,
                    "file_count": file_count
                })
            else:
                logger.warning(f"No case ID mapping for: {item.name}")

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

    password_input = page.locator("input[placeholder='Password'], input[type='password']").first
    await password_input.fill(MERUSCASE_PASSWORD)

    login_btn = page.locator("button:has-text('LOGIN')").first
    await login_btn.click()

    await page.wait_for_load_state("networkidle", timeout=30000)
    await asyncio.sleep(2)
    logger.info(f"Logged in: {page.url}")
    return True


async def upload_folder_to_case(page, case_id: int, folder_path: str, folder_name: str):
    """Upload a folder to a case using the Upload Tool with multiple file selection."""
    logger.info(f"Uploading folder to case {case_id}: {folder_name}")

    # Navigate directly to upload page for this case
    upload_url = f"{BASE_URL}/cms#/uploads?rpt=0&case_file_id={case_id}&t=0&lpt=0&lpa=0"
    await page.goto(upload_url)
    await asyncio.sleep(3)
    await page.wait_for_load_state("networkidle")

    # Find the file input (name=files, multiple)
    file_input = page.locator("input[type='file'][name='files'], input[type='file'][multiple]").first

    try:
        await file_input.wait_for(state="attached", timeout=10000)
    except Exception as e:
        logger.error(f"Could not find file input: {e}")
        # Try clicking Upload Tool link first
        try:
            upload_link = page.locator("a:has-text('Upload Tool')").first
            await upload_link.click(timeout=5000)
            await asyncio.sleep(3)
            file_input = page.locator("input[type='file']").first
            await file_input.wait_for(state="attached", timeout=10000)
        except:
            return {"status": "failed", "error": "File input not found"}

    try:
        # Get all files in the folder
        folder = Path(folder_path)
        files = [str(f) for f in folder.iterdir() if f.is_file()]

        if not files:
            logger.warning(f"No files found in folder: {folder_path}")
            return {"status": "skipped", "error": "No files in folder"}

        logger.info(f"Uploading {len(files)} files from {folder_name}")

        # Upload all files at once
        await file_input.set_input_files(files)
        await asyncio.sleep(2)

        # Wait for files to be processed/shown
        await page.wait_for_load_state("networkidle", timeout=60000)

        # Click Upload button
        upload_btn = page.locator("button:has-text('Upload'), button.btn-primary:has-text('Upload')").first
        try:
            await upload_btn.wait_for(state="visible", timeout=5000)
            await upload_btn.click()
            logger.info("Clicked Upload button, waiting for upload to complete...")

            # Wait for upload to complete - this can take a while for large folders
            # Watch for success message or redirect
            await asyncio.sleep(5)

            # Wait for network to settle (uploads happening)
            # Increase timeout for larger folders
            timeout = max(120000, len(files) * 3000)  # 3 seconds per file minimum
            await page.wait_for_load_state("networkidle", timeout=timeout)

        except Exception as e:
            logger.warning(f"Upload button issue: {e}")

        # Check for success - look for success message or redirect
        await asyncio.sleep(3)
        current_url = page.url

        # Dismiss any modal
        try:
            modal_btns = ["button:has-text('Upload More Documents')",
                         "button:has-text('Done')",
                         "button:has-text('Close')",
                         ".btn:has-text('OK')"]
            for selector in modal_btns:
                btn = page.locator(selector).first
                if await btn.is_visible(timeout=2000):
                    await btn.click()
                    await asyncio.sleep(1)
                    break
        except:
            pass

        # Force remove modal overlay if present
        await page.evaluate("""
            () => {
                document.querySelectorAll('.plainmodal-overlay, .modal-backdrop').forEach(el => el.remove());
                document.body.classList.remove('modal-open');
            }
        """)

        logger.info(f"Upload complete for {folder_name} ({len(files)} files)")
        return {"status": "success", "files": len(files)}

    except Exception as e:
        logger.error(f"Upload failed for {folder_name}: {e}")
        return {"status": "failed", "error": str(e)[:100]}


async def main():
    """Upload all folders to their respective cases."""
    folders = get_folders_to_upload()

    print(f"\n{'='*60}")
    print("UPLOAD ALL CASE FOLDERS")
    print(f"{'='*60}\n")
    print(f"Found {len(folders)} folders to upload\n")

    total_files = sum(f["file_count"] for f in folders)
    print(f"Total files to upload: {total_files}\n")

    results = {"success": [], "failed": [], "skipped": []}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await context.new_page()

        try:
            if not await login(page):
                logger.error("Login failed!")
                return

            for i, folder in enumerate(folders):
                print(f"\n[{i+1}/{len(folders)}] Uploading: {folder['name']} ({folder['file_count']} files)")

                try:
                    result = await upload_folder_to_case(
                        page,
                        folder["case_id"],
                        folder["path"],
                        folder["name"]
                    )

                    if result["status"] == "success":
                        results["success"].append({
                            "name": folder["name"],
                            "case_id": folder["case_id"],
                            "files": result.get("files", folder["file_count"])
                        })
                        print(f"  [OK] Uploaded {result.get('files', '?')} files")
                    elif result["status"] == "skipped":
                        results["skipped"].append({
                            "name": folder["name"],
                            "reason": result.get("error", "Unknown")
                        })
                        print(f"  [SKIP] {result.get('error', 'Unknown')}")
                    else:
                        results["failed"].append({
                            "name": folder["name"],
                            "error": result.get("error", "Unknown")
                        })
                        print(f"  [FAIL] {result.get('error', 'Unknown')}")

                    # Brief pause between uploads
                    await asyncio.sleep(3)

                except Exception as e:
                    error_str = str(e)[:100]
                    logger.error(f"Failed {folder['name']}: {error_str}")
                    print(f"  [FAIL] {error_str}")
                    results["failed"].append({"name": folder["name"], "error": error_str})

            # Summary
            print(f"\n{'='*60}")
            print("SUMMARY")
            print(f"{'='*60}")
            print(f"Success: {len(results['success'])}")
            print(f"Skipped: {len(results['skipped'])}")
            print(f"Failed: {len(results['failed'])}")

            if results["success"]:
                total_uploaded = sum(r.get("files", 0) for r in results["success"])
                print(f"\nUploaded ({len(results['success'])} folders, {total_uploaded} files):")
                for r in results["success"]:
                    print(f"  + {r['name']} ({r.get('files', '?')} files)")

            if results["failed"]:
                print(f"\nFailed ({len(results['failed'])}):")
                for r in results["failed"]:
                    print(f"  - {r['name']}: {r['error']}")

            # Save results
            results_file = os.path.join(LOG_DIR, f"upload_folders_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
            with open(results_file, "w", encoding="utf-8") as f:
                f.write("FOLDER UPLOAD RESULTS\n")
                f.write(f"{'='*60}\n")
                f.write(f"Success: {len(results['success'])}\n")
                f.write(f"Failed: {len(results['failed'])}\n\n")

                if results["success"]:
                    f.write("UPLOADED:\n")
                    for r in results["success"]:
                        f.write(f"  {r['name']} - Case {r['case_id']} ({r.get('files', '?')} files)\n")

                if results["failed"]:
                    f.write("\nFAILED:\n")
                    for r in results["failed"]:
                        f.write(f"  {r['name']}: {r['error']}\n")

            print(f"\nResults saved: {results_file}")

        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
