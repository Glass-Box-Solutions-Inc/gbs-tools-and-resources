"""
Test Single Folder Import - Test batch import with one folder
"""

import logging
import asyncio
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

from automation.matter_builder import MatterBuilder
from automation.document_uploader import DocumentUploader
from models.matter import MatterDetails, CaseType, CaseStatus
from models.batch_import import CaseFolder
from security.config import SecurityConfig

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_single_folder_import(folder_name: str = "ANDREWS DENNIS_Case3608"):
    """
    Test import with a single folder.

    Args:
        folder_name: Name of the folder to test (default: ANDREWS DENNIS)
    """
    source_path = r"C:\4850 Law"
    folder_path = Path(source_path) / folder_name

    if not folder_path.exists():
        print(f"Folder not found: {folder_path}")
        return

    # Parse folder
    folder = CaseFolder.from_path(str(folder_path))
    print(f"\n{'='*60}")
    print(f"TEST IMPORT: {folder.client_name}")
    print(f"{'='*60}")
    print(f"Folder: {folder.folder_name}")
    print(f"Files: {folder.file_count}")
    print(f"Size: {folder.total_size_bytes / (1024*1024):.1f} MB")
    print(f"{'='*60}\n")

    config = SecurityConfig.from_env()
    matter_builder = None

    try:
        # Initialize matter builder
        matter_builder = MatterBuilder(config=config, dry_run=False)
        await matter_builder.connect()

        # Create matter using MatterDetails
        matter = MatterDetails(
            primary_party=folder.client_name,
            case_type=CaseType.WORKERS_COMP,
            case_status=CaseStatus.OPEN,
        )

        print(f"[1/3] Creating matter: {folder.client_name}...")

        # Let create_matter handle the entire workflow (login, navigate, fill, submit)
        result = await matter_builder.create_matter(matter)

        if result["status"] not in ["success", "dry_run_success"]:
            print(f"ERROR: Matter creation failed: {result.get('message', 'Unknown error')}")
            return

        meruscase_url = result.get("meruscase_url") or matter_builder.browser_client.page.url
        print(f"Matter created! URL: {meruscase_url}")

        # Step 2: Upload documents
        print(f"\n[2/3] Uploading {folder.file_count} documents...")

        # Initialize document uploader with same browser
        doc_uploader = DocumentUploader(
            config=config,
            browser_client=matter_builder.browser_client
        )
        doc_uploader._init_handlers()

        session_id = result.get("session_id", "test_upload")

        # Navigate to documents section
        if not await doc_uploader.navigate_to_matter(meruscase_url, session_id):
            print("WARNING: Could not navigate to matter")

        if not await doc_uploader.navigate_to_documents(session_id):
            print("WARNING: Could not navigate to Documents section")

        # Upload files
        uploaded = 0
        failed = 0

        for i, file_path in enumerate(folder.files):
            try:
                file_name = Path(file_path).name
                print(f"  Uploading [{i+1}/{folder.file_count}]: {file_name[:50]}...")

                # Open upload dialog
                await doc_uploader.open_upload_dialog(session_id)

                # Upload file
                from models.document import DocumentUpload
                doc = DocumentUpload.from_path(file_path)
                updated_doc = await doc_uploader.upload_single_document(doc, session_id)

                if updated_doc.upload_status.value == "success":
                    uploaded += 1
                else:
                    failed += 1
                    print(f"    FAILED: {updated_doc.error_message}")

                # Small delay between uploads
                await asyncio.sleep(1.0)

                # Progress update every 10 files
                if (i + 1) % 10 == 0:
                    print(f"  Progress: {i+1}/{folder.file_count} ({uploaded} uploaded, {failed} failed)")

            except Exception as e:
                failed += 1
                print(f"    ERROR: {e}")

        # Step 3: Summary
        print(f"\n[3/3] Import Complete!")
        print(f"{'='*60}")
        print(f"Matter: {folder.client_name}")
        print(f"URL: {meruscase_url}")
        print(f"Files uploaded: {uploaded}/{folder.file_count}")
        print(f"Files failed: {failed}")
        print(f"{'='*60}\n")

    except Exception as e:
        logger.error(f"Test import failed: {e}")
        print(f"\nERROR: {e}")
        raise

    finally:
        if matter_builder:
            await matter_builder.disconnect()


if __name__ == "__main__":
    asyncio.run(test_single_folder_import())
