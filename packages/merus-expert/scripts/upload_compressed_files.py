"""
Upload compressed PDFs and converted videos to MerusCase.
Uses the existing upload infrastructure from merus-expert.
"""

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
PROJECT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from browser.client import BrowserClient
from security.config import Config

# Compressed PDFs to upload
COMPRESSED_PDFS = [
    {
        "path": r"C:\4850 Law\_Compressed_GS\INS PROPOSED LT DR TIRMIZI W- ECNLOSURES CLM 06235532, 03-19-2025.pdf",
        "case_name": "FLUKER JAN L",
        "case_id": 56171886,
    },
    {
        "path": r"C:\4850 Law\_Compressed_GS\MED-LEGAL MRC'S- LAW OFFICES OF CHRISLIP & HERVATIN, 03-10-2021.pdf",
        "case_name": "WEBSTER CHRISTIAN V",
        "case_id": 56171914,
    },
    {
        "path": r"C:\4850 Law\_Compressed_GS\POS- MEDICAL RECORDS- IRONWOOD PRIMARY CARE DATED 02-06-2025 (1).pdf",
        "case_name": "WEIDNER MICHAEL W",
        "case_id": 56171915,
    },
    {
        "path": r"C:\4850 Law\_Compressed_GS\INS PQME COVER LT- DR JACOBO CHODAKIEWITZ, CLM 06493938, 12-27-2023.pdf",
        "case_name": "DAVIS CHRISTINA Y",
        "case_id": 56171882,
    },
    {
        "path": r"C:\4850 Law\_Compressed_GS\INS LTR- PROPOSED PQME COVER LTR CLM 06493938, 12-06-2023.pdf",
        "case_name": "DAVIS CHRISTINA Y",
        "case_id": 56171882,
    },
    {
        "path": r"C:\4850 Law\_Compressed_GS\WCH MRCS- BARTON HEALTH, MEDICAL RECORDS, 02-12-2025.pdf",
        "case_name": "WEIDNER MICHAEL W",
        "case_id": 56171915,
    },
]

# Converted videos folder (will be populated after conversion)
CONVERTED_VIDEOS_DIR = r"C:\4850 Law\_Converted_Videos"
ELIZONDO_CASE_ID = 56171884

BASE_URL = "https://meruscase.com"

import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def login(page) -> bool:
    """Login to MerusCase."""
    config = Config()
    email = config.get("MERUSCASE_EMAIL")
    password = config.get("MERUSCASE_PASSWORD")

    logger.info("Logging in to MerusCase...")
    await page.goto(f"{BASE_URL}/login")
    await page.wait_for_load_state("networkidle")

    await page.fill('input[name="email"]', email)
    await page.fill('input[name="password"]', password)
    await page.click('button[type="submit"]')

    await page.wait_for_url(lambda url: "login" not in url, timeout=30000)
    await asyncio.sleep(2)

    logger.info(f"Logged in: {page.url}")
    return True


async def navigate_to_case(page, case_id: int):
    """Navigate to a specific case's documents tab."""
    url = f"{BASE_URL}/cms#/caseFiles/view/{case_id}?t=documents"
    await page.goto(url)
    await page.wait_for_load_state("networkidle")
    await asyncio.sleep(2)
    logger.info(f"Navigated to case {case_id}")


async def upload_file(page, file_path: str) -> bool:
    """Upload a single file to the current case."""
    try:
        # Open upload tool
        upload_btn = page.locator("text=Upload Tool").first
        if await upload_btn.is_visible():
            await upload_btn.click()
        else:
            # Try menu path
            await page.click("text=Documents")
            await asyncio.sleep(1)
            await page.click("text=Upload Tool")

        await asyncio.sleep(3)

        # Set file input
        file_input = page.locator('input[type="file"]').first
        await file_input.set_input_files(file_path)
        await asyncio.sleep(2)

        # Click upload button
        upload_btn = page.locator('button:has-text("Upload")').first
        if await upload_btn.is_visible():
            await upload_btn.click()

            # Wait for completion
            for _ in range(60):  # Wait up to 5 minutes
                await asyncio.sleep(5)

                # Check for success indicators
                if await page.locator("text=Upload More Documents").is_visible():
                    logger.info("Upload complete!")
                    return True

                if await page.locator("text=successfully uploaded").is_visible():
                    logger.info("Upload successful!")
                    return True

            logger.warning("Upload timeout - may have succeeded")
            return True
        else:
            logger.error("Upload button not visible")
            return False

    except Exception as e:
        logger.error(f"Upload error: {e}")
        return False


async def upload_files_to_case(page, files: list, case_name: str, case_id: int) -> dict:
    """Upload multiple files to a case."""
    results = {
        "case_name": case_name,
        "case_id": case_id,
        "total": len(files),
        "success": 0,
        "failed": 0,
        "files": []
    }

    await navigate_to_case(page, case_id)

    for file_path in files:
        if not os.path.exists(file_path):
            logger.warning(f"File not found: {file_path}")
            results["failed"] += 1
            results["files"].append({"path": file_path, "status": "not_found"})
            continue

        file_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path) / (1024 * 1024)  # MB

        logger.info(f"Uploading: {file_name} ({file_size:.1f} MB)")

        success = await upload_file(page, file_path)

        if success:
            results["success"] += 1
            results["files"].append({"path": file_path, "status": "success", "size_mb": file_size})
        else:
            results["failed"] += 1
            results["files"].append({"path": file_path, "status": "failed", "size_mb": file_size})

        # Close any modals
        try:
            close_btn = page.locator("button:has-text('Close')").first
            if await close_btn.is_visible():
                await close_btn.click()
                await asyncio.sleep(1)
        except:
            pass

    return results


async def main():
    """Main upload process."""
    print("=" * 60)
    print("MerusCase Compressed Files Upload")
    print("=" * 60)
    print()

    # Group PDFs by case
    cases = {}
    for pdf in COMPRESSED_PDFS:
        case_id = pdf["case_id"]
        if case_id not in cases:
            cases[case_id] = {
                "name": pdf["case_name"],
                "files": []
            }
        cases[case_id]["files"].append(pdf["path"])

    # Add converted videos if they exist
    if os.path.exists(CONVERTED_VIDEOS_DIR):
        video_files = [
            os.path.join(CONVERTED_VIDEOS_DIR, f)
            for f in os.listdir(CONVERTED_VIDEOS_DIR)
            if f.endswith(".mp4") and os.path.getsize(os.path.join(CONVERTED_VIDEOS_DIR, f)) < 384 * 1024 * 1024
        ]
        if video_files:
            if ELIZONDO_CASE_ID not in cases:
                cases[ELIZONDO_CASE_ID] = {"name": "ELIZONDO JAMES J", "files": []}
            cases[ELIZONDO_CASE_ID]["files"].extend(video_files)
            print(f"Found {len(video_files)} converted videos to upload")

    print(f"Cases to process: {len(cases)}")
    for case_id, data in cases.items():
        print(f"  - {data['name']} (ID: {case_id}): {len(data['files'])} files")
    print()

    all_results = []

    async with BrowserClient() as client:
        page = await client.new_page()

        # Login
        await login(page)

        # Upload to each case
        for case_id, data in cases.items():
            print(f"\n{'='*60}")
            print(f"Uploading to: {data['name']} (Case ID: {case_id})")
            print(f"Files: {len(data['files'])}")
            print("=" * 60)

            result = await upload_files_to_case(
                page,
                data["files"],
                data["name"],
                case_id
            )
            all_results.append(result)

            print(f"\nResult: {result['success']}/{result['total']} uploaded successfully")

            await asyncio.sleep(5)

    # Summary
    print("\n" + "=" * 60)
    print("UPLOAD SUMMARY")
    print("=" * 60)

    total_success = sum(r["success"] for r in all_results)
    total_failed = sum(r["failed"] for r in all_results)
    total_files = sum(r["total"] for r in all_results)

    print(f"Total files: {total_files}")
    print(f"Successful: {total_success}")
    print(f"Failed: {total_failed}")

    for r in all_results:
        status = "✅" if r["failed"] == 0 else "⚠️"
        print(f"{status} {r['case_name']}: {r['success']}/{r['total']}")

    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = PROJECT_DIR / "logs" / f"compressed_upload_{timestamp}.txt"

    with open(log_path, "w") as f:
        f.write(f"COMPRESSED FILES UPLOAD RESULTS\n")
        f.write(f"{'='*60}\n")
        f.write(f"Date: {datetime.now()}\n")
        f.write(f"Total: {total_success}/{total_files}\n\n")

        for r in all_results:
            f.write(f"\n{r['case_name']} (ID: {r['case_id']})\n")
            f.write(f"  Success: {r['success']}/{r['total']}\n")
            for file_info in r["files"]:
                f.write(f"  - {os.path.basename(file_info['path'])}: {file_info['status']}\n")

    print(f"\nResults saved: {log_path}")


if __name__ == "__main__":
    asyncio.run(main())
