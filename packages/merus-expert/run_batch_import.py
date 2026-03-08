"""Run batch import for all case folders"""
import sys
sys.path.insert(0, r"C:\Users\windo\OneDrive\Desktop\Claude_Code\projects\merus-expert")

import asyncio
import logging
import os
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

from batch.batch_importer import BatchImporter

# Ensure logs directory exists
os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f"logs/batch_import_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Source folder
SOURCE_PATH = r"C:\4850 Law"

# Folders to skip (already processed)
SKIP_FOLDERS = [
    "ANDREWS DENNIS_Case3608",  # Already created with test uploads
]

# Start with smaller folders for testing
# Set to None to process all folders
MAX_FOLDERS = 2  # Process 2 folders first to test full flow


async def main():
    """Run batch import"""
    print(f"\n{'='*60}")
    print("MERUSCASE BATCH IMPORT")
    print(f"{'='*60}\n")
    print(f"Source: {SOURCE_PATH}")
    print(f"Skip folders: {SKIP_FOLDERS}")
    print(f"Max folders: {MAX_FOLDERS or 'All'}")
    print()

    importer = BatchImporter(
        source_path=SOURCE_PATH,
        case_type="Workers' Compensation",
        include_case_number=False,
        dry_run=False,  # LIVE MODE
        delay_between_uploads=1.0,
        skip_folders=SKIP_FOLDERS,
        max_folders=MAX_FOLDERS,
    )

    # Show preview
    preview = importer.generate_preview()
    folders_to_process = [f for f in preview.folders if f.folder_name not in SKIP_FOLDERS]
    if MAX_FOLDERS:
        folders_to_process = folders_to_process[:MAX_FOLDERS]

    print(f"\nWill process {len(folders_to_process)} folders:")
    for f in folders_to_process:
        print(f"  - {f.folder_name}: {f.file_count} files ({f.total_size_mb:.1f} MB)")

    total_files = sum(f.file_count for f in folders_to_process)
    print(f"\nTotal: {len(folders_to_process)} folders, {total_files} files")

    # Confirm
    response = input("\nProceed with batch import? (yes/no): ")
    if response.lower() != "yes":
        print("Aborted.")
        return

    # Run import
    print(f"\n{'='*60}")
    print("STARTING BATCH IMPORT")
    print(f"{'='*60}\n")

    try:
        result = await importer.run()

        print(f"\n{'='*60}")
        print("BATCH IMPORT COMPLETE")
        print(f"{'='*60}\n")
        print(f"Status: {result.status.value}")
        print(f"Successful folders: {result.successful_folders}/{result.total_folders}")
        print(f"Successful files: {result.successful_files}/{result.total_files}")
        print(f"Failed folders: {result.failed_folders}")
        print(f"Failed files: {result.failed_files}")

        if result.matters_created:
            print("\nMatters created:")
            for m in result.matters_created:
                print(f"  - {m['name']}: {m['url']}")

        if result.errors:
            print(f"\nErrors ({len(result.errors)}):")
            for err in result.errors:
                print(f"  - {err['folder']}: {err['error']}")

    except Exception as e:
        logger.error(f"Batch import failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
