"""Create all matters in MerusCase using MatterBuilder"""
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

SOURCE_PATH = r"C:\4850 Law"
SKIP_FOLDERS = ["ANDREWS DENNIS_Case3608"]  # Already created


async def create_all_matters():
    """Create all matters using MatterBuilder."""
    config = SecurityConfig.from_env()

    # Scan folders
    scanner = FolderScanner(SOURCE_PATH)
    folders = scanner.scan()
    folders_to_process = [f for f in folders if f.folder_name not in SKIP_FOLDERS]

    print(f"\n{'='*60}")
    print("CREATE ALL MATTERS")
    print(f"{'='*60}\n")
    print(f"Will create: {len(folders_to_process)} matters\n")

    results = {"created": [], "failed": []}

    # Initialize MatterBuilder (handles login, form filling, etc.)
    builder = MatterBuilder(config=config, dry_run=False)

    try:
        await builder.connect()

        # Create each matter
        for i, folder in enumerate(folders_to_process):
            matter_name = folder.get_matter_name(include_case_number=False)
            print(f"\n[{i+1}/{len(folders_to_process)}] Creating: {matter_name}")

            try:
                # Create MatterDetails
                matter = MatterDetails(
                    primary_party=matter_name,
                    case_type=CaseType.WORKERS_COMP,
                    case_status=CaseStatus.OPEN,
                )

                # Use MatterBuilder to create (handles entire workflow)
                result = await builder.create_matter(matter)

                if result["status"] in ["success", "dry_run_success"]:
                    url = result.get("meruscase_url") or builder.browser_client.page.url
                    results["created"].append({
                        "name": matter_name,
                        "url": url,
                        "files": folder.file_count
                    })
                    logger.info(f"Created: {matter_name} -> {url}")
                    print(f"  [OK] {url}")
                else:
                    raise Exception(result.get("message", "Unknown error"))

                await asyncio.sleep(2)

            except Exception as e:
                error_str = str(e)
                # Truncate long errors
                if len(error_str) > 100:
                    error_str = error_str[:100] + "..."
                logger.error(f"Failed {matter_name}: {error_str}")
                print(f"  [FAIL] {error_str}")
                results["failed"].append({"name": matter_name, "error": error_str})

        # Summary
        print(f"\n{'='*60}")
        print("SUMMARY")
        print(f"{'='*60}")
        print(f"Created: {len(results['created'])}/{len(folders_to_process)}")
        print(f"Failed: {len(results['failed'])}")

        if results["created"]:
            print(f"\nMatters Created ({len(results['created'])}):")
            for m in results["created"]:
                print(f"  + {m['name']} ({m['files']} files)")
                print(f"    {m['url']}")

        if results["failed"]:
            print(f"\nFailed ({len(results['failed'])}):")
            for m in results["failed"]:
                print(f"  - {m['name']}: {m['error']}")

        # Save results
        results_file = os.path.join(LOG_DIR, f"matters_created_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
        with open(results_file, "w", encoding="utf-8") as f:
            f.write(f"MATTERS CREATED: {len(results['created'])}/{len(folders_to_process)}\n")
            f.write("="*60 + "\n\n")
            for m in results["created"]:
                f.write(f"{m['name']}\n")
                f.write(f"  URL: {m['url']}\n")
                f.write(f"  Files: {m['files']}\n\n")
            if results["failed"]:
                f.write("\nFAILED:\n")
                for m in results["failed"]:
                    f.write(f"  {m['name']}: {m['error']}\n")

        print(f"\nResults saved: {results_file}")

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await builder.disconnect()


if __name__ == "__main__":
    asyncio.run(create_all_matters())
