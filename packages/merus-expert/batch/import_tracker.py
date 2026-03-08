"""
Import Tracker - Track batch import progress in SQLite
"""

import logging
import sqlite3
from typing import Optional, List, Dict, Any
from datetime import datetime
from pathlib import Path

from models.batch_import import BatchJob, BatchTask, BatchStatus, TaskStatus, CaseFolder

logger = logging.getLogger(__name__)


class ImportTracker:
    """
    Tracks batch import progress in SQLite database.

    Features:
    - Job state persistence
    - Task-level tracking
    - Document-level tracking
    - Resume capability
    - Progress reporting
    """

    def __init__(self, db_path: str):
        """
        Initialize import tracker.

        Args:
            db_path: Path to SQLite database
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_tables()

    def _get_conn(self) -> sqlite3.Connection:
        """Get database connection"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_tables(self):
        """Create tables if they don't exist"""
        conn = self._get_conn()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS batch_jobs (
                    job_id TEXT PRIMARY KEY,
                    source_path TEXT NOT NULL,
                    case_type TEXT DEFAULT 'Workers'' Compensation',
                    total_folders INTEGER DEFAULT 0,
                    total_files INTEGER DEFAULT 0,
                    processed_folders INTEGER DEFAULT 0,
                    processed_files INTEGER DEFAULT 0,
                    failed_folders INTEGER DEFAULT 0,
                    failed_files INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'pending',
                    current_folder TEXT,
                    error_message TEXT,
                    dry_run INTEGER DEFAULT 1,
                    include_case_number INTEGER DEFAULT 0,
                    delay_between_uploads REAL DEFAULT 1.0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS batch_tasks (
                    task_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    folder_path TEXT NOT NULL,
                    folder_name TEXT NOT NULL,
                    client_name TEXT NOT NULL,
                    case_number TEXT,
                    total_files INTEGER DEFAULT 0,
                    matter_id TEXT,
                    meruscase_url TEXT,
                    status TEXT DEFAULT 'pending',
                    uploaded_files INTEGER DEFAULT 0,
                    failed_files INTEGER DEFAULT 0,
                    error_message TEXT,
                    screenshot_path TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    FOREIGN KEY (job_id) REFERENCES batch_jobs(job_id)
                );

                CREATE TABLE IF NOT EXISTS batch_documents (
                    doc_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL,
                    file_name TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    file_size INTEGER DEFAULT 0,
                    file_type TEXT,
                    upload_status TEXT DEFAULT 'pending',
                    meruscase_doc_id TEXT,
                    error_message TEXT,
                    uploaded_at TIMESTAMP,
                    FOREIGN KEY (task_id) REFERENCES batch_tasks(task_id)
                );

                CREATE INDEX IF NOT EXISTS idx_batch_tasks_job ON batch_tasks(job_id);
                CREATE INDEX IF NOT EXISTS idx_batch_documents_task ON batch_documents(task_id);
            """)
            conn.commit()
        finally:
            conn.close()

    # === Job Management ===

    def create_job(self, job: BatchJob) -> str:
        """
        Create a new batch job.

        Args:
            job: BatchJob object

        Returns:
            Job ID
        """
        conn = self._get_conn()
        try:
            conn.execute("""
                INSERT INTO batch_jobs (
                    job_id, source_path, case_type, total_folders, total_files,
                    status, dry_run, include_case_number, delay_between_uploads
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                job.job_id, job.source_path, job.case_type,
                job.total_folders, job.total_files, job.status.value,
                1 if job.dry_run else 0, 1 if job.include_case_number_in_name else 0,
                job.delay_between_uploads
            ))
            conn.commit()
            logger.info(f"Created batch job: {job.job_id}")
            return job.job_id
        finally:
            conn.close()

    def get_job(self, job_id: str) -> Optional[BatchJob]:
        """
        Get batch job by ID.

        Args:
            job_id: Job identifier

        Returns:
            BatchJob object or None
        """
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM batch_jobs WHERE job_id = ?",
                (job_id,)
            ).fetchone()

            if not row:
                return None

            return BatchJob(
                job_id=row["job_id"],
                source_path=row["source_path"],
                case_type=row["case_type"],
                total_folders=row["total_folders"],
                total_files=row["total_files"],
                processed_folders=row["processed_folders"],
                processed_files=row["processed_files"],
                failed_folders=row["failed_folders"],
                failed_files=row["failed_files"],
                status=BatchStatus(row["status"]),
                current_folder=row["current_folder"],
                error_message=row["error_message"],
                dry_run=bool(row["dry_run"]),
                include_case_number_in_name=bool(row["include_case_number"]),
                delay_between_uploads=row["delay_between_uploads"],
                created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.now(),
                started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
                completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
            )
        finally:
            conn.close()

    def update_job_status(
        self,
        job_id: str,
        status: BatchStatus,
        current_folder: Optional[str] = None,
        error_message: Optional[str] = None
    ):
        """Update job status"""
        conn = self._get_conn()
        try:
            updates = ["status = ?"]
            params = [status.value]

            if current_folder is not None:
                updates.append("current_folder = ?")
                params.append(current_folder)

            if error_message is not None:
                updates.append("error_message = ?")
                params.append(error_message)

            if status == BatchStatus.RUNNING:
                updates.append("started_at = ?")
                params.append(datetime.now().isoformat())

            if status in [BatchStatus.COMPLETED, BatchStatus.FAILED, BatchStatus.CANCELLED]:
                updates.append("completed_at = ?")
                params.append(datetime.now().isoformat())

            params.append(job_id)

            conn.execute(
                f"UPDATE batch_jobs SET {', '.join(updates)} WHERE job_id = ?",
                params
            )
            conn.commit()
        finally:
            conn.close()

    def update_job_progress(
        self,
        job_id: str,
        processed_folders: Optional[int] = None,
        processed_files: Optional[int] = None,
        failed_folders: Optional[int] = None,
        failed_files: Optional[int] = None
    ):
        """Update job progress counters"""
        conn = self._get_conn()
        try:
            updates = []
            params = []

            if processed_folders is not None:
                updates.append("processed_folders = ?")
                params.append(processed_folders)

            if processed_files is not None:
                updates.append("processed_files = ?")
                params.append(processed_files)

            if failed_folders is not None:
                updates.append("failed_folders = ?")
                params.append(failed_folders)

            if failed_files is not None:
                updates.append("failed_files = ?")
                params.append(failed_files)

            if updates:
                params.append(job_id)
                conn.execute(
                    f"UPDATE batch_jobs SET {', '.join(updates)} WHERE job_id = ?",
                    params
                )
                conn.commit()
        finally:
            conn.close()

    def list_jobs(self, status: Optional[BatchStatus] = None) -> List[Dict[str, Any]]:
        """List all jobs, optionally filtered by status"""
        conn = self._get_conn()
        try:
            if status:
                rows = conn.execute(
                    "SELECT * FROM batch_jobs WHERE status = ? ORDER BY created_at DESC",
                    (status.value,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM batch_jobs ORDER BY created_at DESC"
                ).fetchall()

            return [dict(row) for row in rows]
        finally:
            conn.close()

    # === Task Management ===

    def create_task(self, job_id: str, folder: CaseFolder) -> int:
        """
        Create a task for a folder.

        Args:
            job_id: Parent job ID
            folder: CaseFolder object

        Returns:
            Task ID
        """
        conn = self._get_conn()
        try:
            cursor = conn.execute("""
                INSERT INTO batch_tasks (
                    job_id, folder_path, folder_name, client_name,
                    case_number, total_files, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                job_id, folder.folder_path, folder.folder_name,
                folder.client_name, folder.case_number, folder.file_count,
                TaskStatus.PENDING.value
            ))
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def get_task(self, task_id: int) -> Optional[BatchTask]:
        """Get task by ID"""
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM batch_tasks WHERE task_id = ?",
                (task_id,)
            ).fetchone()

            if not row:
                return None

            folder = CaseFolder(
                folder_path=row["folder_path"],
                folder_name=row["folder_name"],
                client_name=row["client_name"],
                case_number=row["case_number"],
                file_count=row["total_files"],
                files=[],
            )

            return BatchTask(
                task_id=row["task_id"],
                job_id=row["job_id"],
                folder=folder,
                matter_id=row["matter_id"],
                meruscase_url=row["meruscase_url"],
                status=TaskStatus(row["status"]),
                uploaded_files=row["uploaded_files"],
                failed_files=row["failed_files"],
                error_message=row["error_message"],
                screenshot_path=row["screenshot_path"],
            )
        finally:
            conn.close()

    def get_tasks_for_job(self, job_id: str) -> List[BatchTask]:
        """Get all tasks for a job"""
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM batch_tasks WHERE job_id = ? ORDER BY task_id",
                (job_id,)
            ).fetchall()

            tasks = []
            for row in rows:
                folder = CaseFolder(
                    folder_path=row["folder_path"],
                    folder_name=row["folder_name"],
                    client_name=row["client_name"],
                    case_number=row["case_number"],
                    file_count=row["total_files"],
                    files=[],
                )

                tasks.append(BatchTask(
                    task_id=row["task_id"],
                    job_id=row["job_id"],
                    folder=folder,
                    matter_id=row["matter_id"],
                    meruscase_url=row["meruscase_url"],
                    status=TaskStatus(row["status"]),
                    uploaded_files=row["uploaded_files"],
                    failed_files=row["failed_files"],
                    error_message=row["error_message"],
                    screenshot_path=row["screenshot_path"],
                ))

            return tasks
        finally:
            conn.close()

    def get_pending_tasks(self, job_id: str) -> List[BatchTask]:
        """Get pending tasks for a job (for resume)"""
        conn = self._get_conn()
        try:
            rows = conn.execute("""
                SELECT * FROM batch_tasks
                WHERE job_id = ? AND status IN (?, ?)
                ORDER BY task_id
            """, (job_id, TaskStatus.PENDING.value, TaskStatus.CREATING_MATTER.value)).fetchall()

            tasks = []
            for row in rows:
                folder = CaseFolder(
                    folder_path=row["folder_path"],
                    folder_name=row["folder_name"],
                    client_name=row["client_name"],
                    case_number=row["case_number"],
                    file_count=row["total_files"],
                    files=[],
                )

                tasks.append(BatchTask(
                    task_id=row["task_id"],
                    job_id=row["job_id"],
                    folder=folder,
                    status=TaskStatus(row["status"]),
                ))

            return tasks
        finally:
            conn.close()

    def update_task_status(
        self,
        task_id: int,
        status: TaskStatus,
        matter_id: Optional[str] = None,
        meruscase_url: Optional[str] = None,
        error_message: Optional[str] = None,
        screenshot_path: Optional[str] = None
    ):
        """Update task status"""
        conn = self._get_conn()
        try:
            updates = ["status = ?"]
            params = [status.value]

            if matter_id is not None:
                updates.append("matter_id = ?")
                params.append(matter_id)

            if meruscase_url is not None:
                updates.append("meruscase_url = ?")
                params.append(meruscase_url)

            if error_message is not None:
                updates.append("error_message = ?")
                params.append(error_message)

            if screenshot_path is not None:
                updates.append("screenshot_path = ?")
                params.append(screenshot_path)

            if status == TaskStatus.CREATING_MATTER:
                updates.append("started_at = ?")
                params.append(datetime.now().isoformat())

            if status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.SKIPPED]:
                updates.append("completed_at = ?")
                params.append(datetime.now().isoformat())

            params.append(task_id)

            conn.execute(
                f"UPDATE batch_tasks SET {', '.join(updates)} WHERE task_id = ?",
                params
            )
            conn.commit()
        finally:
            conn.close()

    def update_task_progress(
        self,
        task_id: int,
        uploaded_files: Optional[int] = None,
        failed_files: Optional[int] = None
    ):
        """Update task file progress"""
        conn = self._get_conn()
        try:
            updates = []
            params = []

            if uploaded_files is not None:
                updates.append("uploaded_files = ?")
                params.append(uploaded_files)

            if failed_files is not None:
                updates.append("failed_files = ?")
                params.append(failed_files)

            if updates:
                params.append(task_id)
                conn.execute(
                    f"UPDATE batch_tasks SET {', '.join(updates)} WHERE task_id = ?",
                    params
                )
                conn.commit()
        finally:
            conn.close()

    # === Document Tracking ===

    def create_document(
        self,
        task_id: int,
        file_name: str,
        file_path: str,
        file_size: int = 0,
        file_type: str = "unknown"
    ) -> int:
        """Create document record"""
        conn = self._get_conn()
        try:
            cursor = conn.execute("""
                INSERT INTO batch_documents (
                    task_id, file_name, file_path, file_size, file_type, upload_status
                ) VALUES (?, ?, ?, ?, ?, 'pending')
            """, (task_id, file_name, file_path, file_size, file_type))
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def update_document_status(
        self,
        doc_id: int,
        upload_status: str,
        meruscase_doc_id: Optional[str] = None,
        error_message: Optional[str] = None
    ):
        """Update document upload status"""
        conn = self._get_conn()
        try:
            updates = ["upload_status = ?"]
            params = [upload_status]

            if meruscase_doc_id is not None:
                updates.append("meruscase_doc_id = ?")
                params.append(meruscase_doc_id)

            if error_message is not None:
                updates.append("error_message = ?")
                params.append(error_message)

            if upload_status == "success":
                updates.append("uploaded_at = ?")
                params.append(datetime.now().isoformat())

            params.append(doc_id)

            conn.execute(
                f"UPDATE batch_documents SET {', '.join(updates)} WHERE doc_id = ?",
                params
            )
            conn.commit()
        finally:
            conn.close()

    # === Progress Reporting ===

    def get_job_progress(self, job_id: str) -> Dict[str, Any]:
        """Get detailed job progress"""
        job = self.get_job(job_id)
        if not job:
            return {"error": "Job not found"}

        tasks = self.get_tasks_for_job(job_id)

        completed_tasks = sum(1 for t in tasks if t.status == TaskStatus.COMPLETED)
        failed_tasks = sum(1 for t in tasks if t.status == TaskStatus.FAILED)
        pending_tasks = sum(1 for t in tasks if t.status == TaskStatus.PENDING)
        in_progress_tasks = sum(1 for t in tasks if t.status in [
            TaskStatus.CREATING_MATTER, TaskStatus.UPLOADING_DOCUMENTS
        ])

        return {
            "job_id": job_id,
            "status": job.status.value,
            "progress_percent": job.progress_percent,
            "folders": {
                "total": job.total_folders,
                "completed": completed_tasks,
                "failed": failed_tasks,
                "pending": pending_tasks,
                "in_progress": in_progress_tasks,
            },
            "files": {
                "total": job.total_files,
                "processed": job.processed_files,
                "failed": job.failed_files,
            },
            "current_folder": job.current_folder,
            "dry_run": job.dry_run,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "elapsed_time": (datetime.now() - job.started_at).total_seconds() if job.started_at else 0,
        }

    def print_progress(self, job_id: str):
        """Print formatted progress to console"""
        progress = self.get_job_progress(job_id)

        if "error" in progress:
            print(f"Error: {progress['error']}")
            return

        print(f"\n{'='*60}")
        print(f"Job: {progress['job_id']}")
        print(f"{'='*60}")
        print(f"Status: {progress['status']}")
        print(f"Progress: {progress['progress_percent']:.1f}%")
        print(f"Dry Run: {progress['dry_run']}")
        print()
        print("Folders:")
        print(f"  Completed: {progress['folders']['completed']}/{progress['folders']['total']}")
        print(f"  Failed: {progress['folders']['failed']}")
        print(f"  Pending: {progress['folders']['pending']}")
        print(f"  In Progress: {progress['folders']['in_progress']}")
        print()
        print("Files:")
        print(f"  Processed: {progress['files']['processed']:,}/{progress['files']['total']:,}")
        print(f"  Failed: {progress['files']['failed']:,}")
        print()
        if progress['current_folder']:
            print(f"Current: {progress['current_folder']}")
        if progress['elapsed_time']:
            mins = progress['elapsed_time'] / 60
            print(f"Elapsed: {mins:.1f} minutes")
        print(f"{'='*60}\n")
