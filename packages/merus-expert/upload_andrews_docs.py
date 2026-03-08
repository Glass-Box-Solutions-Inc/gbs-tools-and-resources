"""Upload all documents to ANDREWS DENNIS case"""
import sys
sys.path.insert(0, r"C:\Users\windo\OneDrive\Desktop\Claude_Code\projects\merus-expert")

import asyncio
import logging
import os
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

from automation.document_uploader import DocumentUploader
from models.document import DocumentUpload

PROJECT_DIR = r"C:\Users\windo\OneDrive\Desktop\Claude_Code\projects\merus-expert"
LOG_DIR = os.path.join(PROJECT_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, f"upload_andrews_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ANDREWS DENNIS folder
FOLDER_PATH = r"C:\4850 Law\ANDREWS DENNIS_Case3608"


async def upload_all_andrews_docs():
    """Upload all documents from ANDREWS DENNIS folder."""

    # Get all files
    folder = Path(FOLDER_PATH)
    files = []
    for f in sorted(folder.iterdir()):
        if f.is_file():
            files.append(DocumentUpload.from_path(str(f)))

    print(f"\n{'='*60}")
    print("UPLOAD ALL ANDREWS DENNIS DOCUMENTS")
    print(f"{'='*60}\n")
    print(f"Folder: {FOLDER_PATH}")
    print(f"Total files: {len(files)}")
    print()

    async with DocumentUploader() as uploader:
        # Login
        session_id = f"andrews_upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        logger.info("Logging in...")

        if not await uploader.login(session_id):
            logger.error("Login failed!")
            return

        logger.info("Login successful!")

        # Navigate to ANDREWS case and open Upload Tool
        logger.info("Navigating to ANDREWS DENNIS case...")
        if not await uploader.navigate_to_case_and_upload_tool("ANDREWS", session_id):
            logger.error("Failed to navigate to case!")
            return

        logger.info("Upload Tool opened, starting upload...")

        # Upload stats
        success_count = 0
        fail_count = 0
        start_time = datetime.now()

        # Upload all files
        for i, doc in enumerate(files):
            try:
                logger.info(f"[{i+1}/{len(files)}] Uploading: {doc.file_name}")

                result = await uploader.upload_single_document(doc, session_id)

                if result.upload_status.value == "success":
                    success_count += 1
                    if (i + 1) % 10 == 0:
                        elapsed = (datetime.now() - start_time).total_seconds()
                        rate = (i + 1) / elapsed * 60  # files per minute
                        remaining = (len(files) - i - 1) / rate if rate > 0 else 0
                        print(f"  Progress: {i+1}/{len(files)} ({success_count} success, {fail_count} failed)")
                        print(f"  Rate: {rate:.1f} files/min, ETA: {remaining:.1f} min")
                else:
                    fail_count += 1
                    logger.warning(f"  Failed: {result.error_message}")

            except Exception as e:
                fail_count += 1
                logger.error(f"  Error: {e}")

        # Summary
        elapsed = (datetime.now() - start_time).total_seconds()

        print(f"\n{'='*60}")
        print("UPLOAD COMPLETE")
        print(f"{'='*60}\n")
        print(f"Total files: {len(files)}")
        print(f"Successful: {success_count}")
        print(f"Failed: {fail_count}")
        print(f"Time: {elapsed/60:.1f} minutes")
        print(f"Rate: {len(files)/elapsed*60:.1f} files/minute")


if __name__ == "__main__":
    asyncio.run(upload_all_andrews_docs())
