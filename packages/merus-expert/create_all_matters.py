"""Create all matters in MerusCase (without document uploads)"""
import sys
sys.path.insert(0, r"C:\Users\windo\OneDrive\Desktop\Claude_Code\projects\merus-expert")

import asyncio
import logging
import os
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

from batch.folder_scanner import FolderScanner
from automation.matter_builder import MatterBuilder
from models.matter import MatterDetails, CaseType, CaseStatus
from security.config import SecurityConfig

PROJECT_DIR = r"C:\Users\windo\OneDrive\Desktop\Claude_Code\projects\merus-expert"
LOG_DIR = os.path.join(PROJECT_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, f"create_matters_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Source folder
SOURCE_PATH = r"C:\4850 Law"

# Folders to skip (already created)
SKIP_FOLDERS = [
    "ANDREWS DENNIS_Case3608",  # Already created
]


async def create_all_matters():
    """Create all matters without uploading documents."""
    config = SecurityConfig.from_env()

    # Scan folders
    scanner = FolderScanner(SOURCE_PATH)
    folders = scanner.scan()

    # Filter out already processed
    folders_to_process = [f for f in folders if f.folder_name not in SKIP_FOLDERS]

    print(f"\n{'='*60}")
    print("CREATE ALL MATTERS")
    print(f"{'='*60}\n")
    print(f"Total folders: {len(folders)}")
    print(f"Skipping: {len(SKIP_FOLDERS)}")
    print(f"Will create: {len(folders_to_process)} matters\n")

    for f in folders_to_process:
        print(f"  - {f.get_matter_name(include_case_number=False)}")

    print()

    # Track results
    results = {
        "created": [],
        "failed": [],
    }

    # Initialize matter builder
    builder = MatterBuilder(config=config, dry_run=False)

    try:
        await builder.connect()

        # Login once
        session_id = f"create_matters_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        logger.info("Logging in...")

        if not await builder.login(session_id):
            logger.error("Login failed!")
            return

        logger.info("Login successful!")

        # Create each matter
        for i, folder in enumerate(folders_to_process):
            matter_name = folder.get_matter_name(include_case_number=False)

            print(f"\n[{i+1}/{len(folders_to_process)}] Creating: {matter_name}")
            logger.info(f"Creating matter {i+1}/{len(folders_to_process)}: {matter_name}")

            try:
                # Navigate to new matter form
                if not await builder.navigate_to_new_matter_form(session_id):
                    raise Exception("Failed to navigate to new matter form")

                # Create matter details
                matter = MatterDetails(
                    primary_party=matter_name,
                    case_type=CaseType.WORKERS_COMP,
                    case_status=CaseStatus.OPEN,
                )

                # Fill and submit
                result = await builder.create_matter(matter, session_id)

                if result["status"] in ["success", "dry_run_success"]:
                    url = result.get("meruscase_url", builder.browser_client.page.url)
                    results["created"].append({
                        "name": matter_name,
                        "folder": folder.folder_name,
                        "url": url,
                        "file_count": folder.file_count,
                    })
                    logger.info(f"✓ Created: {matter_name} -> {url}")
                    print(f"  ✓ Created: {url}")
                else:
                    raise Exception(result.get("message", "Unknown error"))

                # Small delay between creations
                await asyncio.sleep(2)

            except Exception as e:
                logger.error(f"✗ Failed to create {matter_name}: {e}")
                print(f"  ✗ Failed: {e}")
                results["failed"].append({
                    "name": matter_name,
                    "folder": folder.folder_name,
                    "error": str(e),
                })

        # Print summary
        print(f"\n{'='*60}")
        print("SUMMARY")
        print(f"{'='*60}\n")
        print(f"Created: {len(results['created'])}/{len(folders_to_process)}")
        print(f"Failed: {len(results['failed'])}/{len(folders_to_process)}")

        if results["created"]:
            print(f"\nMatters Created ({len(results['created'])}):")
            for m in results["created"]:
                print(f"  ✓ {m['name']} ({m['file_count']} files)")
                print(f"    URL: {m['url']}")

        if results["failed"]:
            print(f"\nFailed ({len(results['failed'])}):")
            for m in results["failed"]:
                print(f"  ✗ {m['name']}: {m['error']}")

        # Save results to file
        results_file = f"logs/matters_created_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(results_file, "w") as f:
            f.write("MATTERS CREATED\n")
            f.write("="*60 + "\n\n")
            for m in results["created"]:
                f.write(f"{m['name']}\n")
                f.write(f"  Folder: {m['folder']}\n")
                f.write(f"  URL: {m['url']}\n")
                f.write(f"  Files: {m['file_count']}\n\n")

            if results["failed"]:
                f.write("\nFAILED\n")
                f.write("="*60 + "\n\n")
                for m in results["failed"]:
                    f.write(f"{m['name']}: {m['error']}\n")

        print(f"\nResults saved to: {results_file}")

    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await builder.disconnect()


if __name__ == "__main__":
    asyncio.run(create_all_matters())
