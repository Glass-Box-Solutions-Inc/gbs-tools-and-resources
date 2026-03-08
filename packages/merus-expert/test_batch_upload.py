"""Test batch document upload to ANDREWS DENNIS case"""
import sys
sys.path.insert(0, r"C:\Users\windo\OneDrive\Desktop\Claude_Code\projects\merus-expert")

import asyncio
import logging
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

from automation.document_uploader import DocumentUploader
from models.document import DocumentUpload

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Test config
TEST_FOLDER = r"C:\4850 Law\ANDREWS DENNIS_Case3608"
MAX_FILES = 5  # Only upload first 5 files for testing


async def test_batch_upload():
    """Test batch upload to ANDREWS DENNIS case."""

    # Collect first N files from folder
    folder = Path(TEST_FOLDER)
    files = []
    for f in sorted(folder.iterdir()):
        if f.is_file():
            files.append(DocumentUpload.from_path(str(f)))
            if len(files) >= MAX_FILES:
                break

    logger.info(f"Found {len(files)} files to upload (limited to {MAX_FILES})")
    for doc in files:
        logger.info(f"  - {doc.file_name} ({doc.file_size / 1024:.1f} KB)")

    async with DocumentUploader() as uploader:
        # Login
        session_id = "batch_test"
        if not await uploader.login(session_id):
            logger.error("Login failed!")
            return

        logger.info("Login successful, navigating to case...")

        # Navigate to case and upload tool
        if not await uploader.navigate_to_case_and_upload_tool("ANDREWS", session_id):
            logger.error("Failed to navigate to case!")
            return

        logger.info("Opened Upload Tool, starting batch upload...")

        # Upload files one by one
        success_count = 0
        fail_count = 0

        for i, doc in enumerate(files):
            logger.info(f"\n{'='*50}")
            logger.info(f"Uploading {i+1}/{len(files)}: {doc.file_name}")

            result = await uploader.upload_single_document(doc, session_id)

            if result.upload_status.value == "success":
                success_count += 1
                logger.info(f"✓ Success!")
            else:
                fail_count += 1
                logger.warning(f"✗ Failed: {result.error_message}")

        logger.info(f"\n{'='*60}")
        logger.info("BATCH UPLOAD TEST COMPLETE")
        logger.info(f"{'='*60}")
        logger.info(f"Success: {success_count}/{len(files)}")
        logger.info(f"Failed: {fail_count}/{len(files)}")


if __name__ == "__main__":
    asyncio.run(test_batch_upload())
