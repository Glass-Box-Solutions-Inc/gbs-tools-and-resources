"""
Batch Importer - Orchestrate batch matter creation and document upload
"""

import logging
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime
from pathlib import Path

from batch.folder_scanner import FolderScanner
from batch.import_tracker import ImportTracker
from automation.matter_builder import MatterBuilder
from automation.document_uploader import DocumentUploader
from models.matter import MatterDetails, CaseType, CaseStatus
from models.batch_import import (
    BatchJob, BatchTask, BatchStatus, TaskStatus,
    CaseFolder, DryRunPreview, BatchJobResult
)
from models.document import DocumentUpload
from security.config import SecurityConfig
from security.audit import AuditLogger

logger = logging.getLogger(__name__)


class BatchImporter:
    """
    Orchestrates batch import of matters and documents from local folders.

    Workflow:
    1. Scan source folder
    2. Generate preview (dry-run)
    3. Create matters for each folder
    4. Upload documents to each matter
    5. Track progress and handle errors
    6. Support resume for interrupted jobs
    """

    def __init__(
        self,
        source_path: str,
        config: Optional[SecurityConfig] = None,
        case_type: str = "Workers' Compensation",
        include_case_number: bool = False,
        dry_run: bool = True,
        delay_between_uploads: float = 1.0,
        skip_folders: Optional[List[str]] = None,
        max_folders: Optional[int] = None,
    ):
        """
        Initialize batch importer.

        Args:
            source_path: Path to source folder (e.g., "C:\\4850 Law")
            config: Security configuration
            case_type: Case type for all matters
            include_case_number: Include case number in matter name
            dry_run: If True, preview only without making changes
            delay_between_uploads: Delay between file uploads in seconds
            skip_folders: List of folder names to skip
            max_folders: Maximum number of folders to process (None = all)
        """
        self.source_path = source_path
        self.config = config or SecurityConfig.from_env()
        self.case_type = case_type
        self.include_case_number = include_case_number
        self.dry_run = dry_run
        self.delay_between_uploads = delay_between_uploads
        self.skip_folders = skip_folders or []
        self.max_folders = max_folders

        # Initialize components
        self.scanner = FolderScanner(source_path)
        self.tracker = ImportTracker(self.config.db_path)
        self.audit_logger = AuditLogger(self.config.db_path)

        # Browser clients (initialized during run)
        self.matter_builder: Optional[MatterBuilder] = None
        self.document_uploader: Optional[DocumentUploader] = None

        # Current job
        self.job: Optional[BatchJob] = None
        self._is_running = False
        self._should_stop = False

    def generate_preview(self) -> DryRunPreview:
        """
        Generate a dry-run preview of what will be imported.

        Returns:
            DryRunPreview object
        """
        return self.scanner.generate_preview(
            case_type=self.case_type,
            include_case_number=self.include_case_number
        )

    def print_preview(self):
        """Print formatted preview to console"""
        self.scanner.print_preview(
            case_type=self.case_type,
            include_case_number=self.include_case_number
        )

    async def run(self, job_id: Optional[str] = None) -> BatchJobResult:
        """
        Run the batch import.

        Args:
            job_id: Optional job ID (for resume). Auto-generated if not provided.

        Returns:
            BatchJobResult with import results
        """
        if self._is_running:
            raise RuntimeError("Batch import already running")

        self._is_running = True
        self._should_stop = False

        try:
            # Create or resume job
            if job_id:
                self.job = self.tracker.get_job(job_id)
                if not self.job:
                    raise ValueError(f"Job not found: {job_id}")
                if not self.job.is_resumable:
                    raise ValueError(f"Job is not resumable: {self.job.status}")
                logger.info(f"Resuming job: {job_id}")
            else:
                self.job = await self._create_job()
                logger.info(f"Created new job: {self.job.job_id}")

            # Update job status
            self.tracker.update_job_status(self.job.job_id, BatchStatus.RUNNING)

            # Log start
            self.audit_logger.log(
                event_type="batch_import",
                action="start",
                status="SUCCESS",
                metadata={
                    "job_id": self.job.job_id,
                    "source_path": self.source_path,
                    "total_folders": self.job.total_folders,
                    "total_files": self.job.total_files,
                    "dry_run": self.dry_run,
                }
            )

            # If dry-run, just show preview and return
            if self.dry_run:
                return await self._run_dry_run()

            # Run actual import
            return await self._run_import()

        except Exception as e:
            logger.error(f"Batch import failed: {e}")
            if self.job:
                self.tracker.update_job_status(
                    self.job.job_id,
                    BatchStatus.FAILED,
                    error_message=str(e)
                )
            raise

        finally:
            self._is_running = False

    async def _create_job(self) -> BatchJob:
        """Create a new batch job"""
        # Scan folders
        all_folders = self.scanner.scan()

        # Apply filters
        folders = []
        for folder in all_folders:
            # Skip folders in skip list
            if folder.folder_name in self.skip_folders:
                logger.info(f"Skipping folder: {folder.folder_name}")
                continue
            folders.append(folder)
            # Check max folders limit
            if self.max_folders and len(folders) >= self.max_folders:
                logger.info(f"Reached max_folders limit: {self.max_folders}")
                break

        # Calculate total files for filtered folders
        total_files = sum(f.file_count for f in folders)

        # Create job
        job = BatchJob(
            job_id=f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            source_path=self.source_path,
            case_type=self.case_type,
            total_folders=len(folders),
            total_files=total_files,
            dry_run=self.dry_run,
            include_case_number_in_name=self.include_case_number,
            delay_between_uploads=self.delay_between_uploads,
        )

        # Save job to database
        self.tracker.create_job(job)

        # Create tasks for each folder
        for folder in folders:
            task_id = self.tracker.create_task(job.job_id, folder)
            logger.debug(f"Created task {task_id} for {folder.folder_name}")

        return job

    async def _run_dry_run(self) -> BatchJobResult:
        """Run in dry-run mode - preview only"""
        logger.info("Running in DRY-RUN mode")

        preview = self.generate_preview()

        # Print preview
        self.print_preview()

        # Mark as complete
        self.tracker.update_job_status(self.job.job_id, BatchStatus.COMPLETED)

        return BatchJobResult(
            job_id=self.job.job_id,
            status=BatchStatus.COMPLETED,
            total_folders=preview.total_matters,
            total_files=preview.total_files,
            successful_folders=0,
            successful_files=0,
            failed_folders=0,
            failed_files=0,
            matters_created=[],
            errors=[],
        )

    async def _run_import(self) -> BatchJobResult:
        """Run actual import"""
        logger.info("Running LIVE import")

        results = BatchJobResult(
            job_id=self.job.job_id,
            status=BatchStatus.RUNNING,
            total_folders=self.job.total_folders,
            total_files=self.job.total_files,
            successful_folders=0,
            successful_files=0,
            failed_folders=0,
            failed_files=0,
            matters_created=[],
            errors=[],
        )

        try:
            # Initialize browser clients
            self.matter_builder = MatterBuilder(config=self.config, dry_run=False)
            await self.matter_builder.connect()

            # Login once
            session_id = f"batch_{self.job.job_id}"
            if not await self.matter_builder.login(session_id):
                raise Exception("Login failed")

            # Reuse browser for document uploader
            self.document_uploader = DocumentUploader(
                config=self.config,
                browser_client=self.matter_builder.browser_client
            )
            self.document_uploader._init_handlers()

            # Get pending tasks
            tasks = self.tracker.get_pending_tasks(self.job.job_id)
            logger.info(f"Processing {len(tasks)} pending tasks")

            for i, task in enumerate(tasks):
                if self._should_stop:
                    logger.info("Import stopped by user")
                    break

                # Update current folder
                self.tracker.update_job_status(
                    self.job.job_id,
                    BatchStatus.RUNNING,
                    current_folder=task.folder.folder_name
                )

                logger.info(f"Processing folder {i+1}/{len(tasks)}: {task.folder.folder_name}")

                try:
                    # Process this folder
                    task_result = await self._process_folder(task, session_id)

                    if task_result["success"]:
                        results.successful_folders += 1
                        results.successful_files += task_result["uploaded_files"]
                        results.matters_created.append({
                            "name": task.folder.get_matter_name(self.include_case_number),
                            "url": task_result.get("meruscase_url", ""),
                        })
                    else:
                        results.failed_folders += 1
                        results.failed_files += task.folder.file_count
                        results.errors.append({
                            "folder": task.folder.folder_name,
                            "error": task_result.get("error", "Unknown error"),
                        })

                    # Update job progress
                    self.tracker.update_job_progress(
                        self.job.job_id,
                        processed_folders=results.successful_folders + results.failed_folders,
                        processed_files=results.successful_files + results.failed_files,
                        failed_folders=results.failed_folders,
                        failed_files=results.failed_files,
                    )

                except Exception as e:
                    logger.error(f"Error processing {task.folder.folder_name}: {e}")
                    results.failed_folders += 1
                    results.errors.append({
                        "folder": task.folder.folder_name,
                        "error": str(e),
                    })

                # Delay between folders
                if i < len(tasks) - 1:
                    await asyncio.sleep(2)

            # Determine final status
            if results.failed_folders == 0:
                results.status = BatchStatus.COMPLETED
            elif results.successful_folders > 0:
                results.status = BatchStatus.COMPLETED  # Partial success
            else:
                results.status = BatchStatus.FAILED

            self.tracker.update_job_status(self.job.job_id, results.status)

            return results

        finally:
            # Cleanup
            if self.matter_builder:
                await self.matter_builder.disconnect()

    async def _process_folder(self, task: BatchTask, session_id: str) -> Dict[str, Any]:
        """
        Process a single folder: create matter and upload documents.

        Args:
            task: BatchTask for this folder
            session_id: Session identifier

        Returns:
            Dict with processing results
        """
        result = {
            "success": False,
            "matter_id": None,
            "meruscase_url": None,
            "uploaded_files": 0,
            "failed_files": 0,
            "error": None,
        }

        try:
            # Update task status
            self.tracker.update_task_status(task.task_id, TaskStatus.CREATING_MATTER)

            # Create matter
            matter_name = task.folder.get_matter_name(self.include_case_number)
            matter = MatterDetails(
                primary_party=matter_name,
                case_type=CaseType.WORKERS_COMP,
                case_status=CaseStatus.OPEN,
            )

            logger.info(f"Creating matter: {matter_name}")

            # Navigate to new matter form and create
            if not await self.matter_builder.navigate_to_new_matter_form(session_id):
                raise Exception("Failed to navigate to new matter form")

            # Fill and submit form
            matter_result = await self.matter_builder.create_matter(matter, session_id)

            if matter_result["status"] not in ["success", "dry_run_success"]:
                raise Exception(f"Matter creation failed: {matter_result.get('message', 'Unknown error')}")

            # Get matter URL
            meruscase_url = matter_result.get("meruscase_url")
            if not meruscase_url:
                # Try to get from current URL
                meruscase_url = self.matter_builder.browser_client.page.url

            result["matter_id"] = matter_result.get("matter_id")
            result["meruscase_url"] = meruscase_url

            # Update task with matter info
            self.tracker.update_task_status(
                task.task_id,
                TaskStatus.UPLOADING_DOCUMENTS,
                matter_id=str(result["matter_id"]),
                meruscase_url=meruscase_url
            )

            logger.info(f"Matter created: {meruscase_url}")

            # Upload documents
            if task.folder.files:
                upload_result = await self._upload_folder_documents(
                    task, meruscase_url, session_id
                )
                result["uploaded_files"] = upload_result["uploaded"]
                result["failed_files"] = upload_result["failed"]

            # Mark task complete
            self.tracker.update_task_status(
                task.task_id,
                TaskStatus.COMPLETED,
                screenshot_path=matter_result.get("screenshot_path")
            )
            self.tracker.update_task_progress(
                task.task_id,
                uploaded_files=result["uploaded_files"],
                failed_files=result["failed_files"]
            )

            result["success"] = True
            return result

        except Exception as e:
            logger.error(f"Failed to process folder {task.folder.folder_name}: {e}")
            result["error"] = str(e)

            self.tracker.update_task_status(
                task.task_id,
                TaskStatus.FAILED,
                error_message=str(e)
            )

            return result

    async def _upload_folder_documents(
        self,
        task: BatchTask,
        matter_url: str,
        session_id: str
    ) -> Dict[str, int]:
        """
        Upload all documents from a folder to a matter.

        Args:
            task: BatchTask with folder info
            matter_url: MerusCase matter URL
            session_id: Session identifier

        Returns:
            Dict with uploaded and failed counts
        """
        result = {"uploaded": 0, "failed": 0}

        # Reload folder files
        folder = CaseFolder.from_path(task.folder.folder_path)
        logger.info(f"Uploading {folder.file_count} documents")

        # Create document records
        documents = []
        for file_path in folder.files:
            doc = DocumentUpload.from_path(file_path)
            documents.append(doc)

        # Open Upload Tool from Documents dropdown (we're already on the case page)
        if not await self.document_uploader.open_upload_tool(session_id):
            logger.error("Failed to open Upload Tool")
            result["failed"] = len(documents)
            return result

        # Upload each document (staying on Upload Tool page)
        for i, doc in enumerate(documents):
            try:
                # Upload document (modal is auto-dismissed after each upload)
                updated_doc = await self.document_uploader.upload_single_document(doc, session_id)

                if updated_doc.upload_status.value == "success":
                    result["uploaded"] += 1
                else:
                    result["failed"] += 1

                # Delay between uploads
                if i < len(documents) - 1:
                    await asyncio.sleep(self.delay_between_uploads)

                # Log progress periodically
                if (i + 1) % 10 == 0:
                    logger.info(f"Uploaded {i+1}/{len(documents)} documents")

            except Exception as e:
                logger.error(f"Failed to upload {doc.file_name}: {e}")
                result["failed"] += 1

        logger.info(f"Upload complete: {result['uploaded']}/{len(documents)} successful")
        return result

    def stop(self):
        """Request stop of running import"""
        self._should_stop = True
        logger.info("Stop requested for batch import")

    def get_progress(self) -> Dict[str, Any]:
        """Get current job progress"""
        if not self.job:
            return {"error": "No job running"}
        return self.tracker.get_job_progress(self.job.job_id)

    def print_progress(self):
        """Print current progress"""
        if self.job:
            self.tracker.print_progress(self.job.job_id)


# === CLI Interface ===

async def main():
    """CLI entry point for batch import"""
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    if len(sys.argv) < 2:
        print("Usage: python batch_importer.py <source_path> [--dry-run|--run]")
        print("Example: python batch_importer.py 'C:\\4850 Law' --dry-run")
        sys.exit(1)

    source_path = sys.argv[1]
    is_dry_run = "--run" not in sys.argv

    try:
        importer = BatchImporter(
            source_path=source_path,
            case_type="Workers' Compensation",
            include_case_number=False,
            dry_run=is_dry_run,
        )

        if is_dry_run:
            print("\n[DRY-RUN MODE - No changes will be made]\n")
            importer.print_preview()
        else:
            print("\n[LIVE MODE - This will create matters and upload documents]\n")
            result = await importer.run()
            print(f"\nImport complete!")
            print(f"Status: {result.status.value}")
            print(f"Successful folders: {result.successful_folders}/{result.total_folders}")
            print(f"Successful files: {result.successful_files}/{result.total_files}")
            if result.errors:
                print(f"\nErrors ({len(result.errors)}):")
                for err in result.errors[:5]:
                    print(f"  - {err['folder']}: {err['error']}")

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
