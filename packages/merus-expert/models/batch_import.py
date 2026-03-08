"""
Batch Import Data Models
Pydantic models for batch matter creation and document upload
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from pathlib import Path
from enum import Enum
import re


class BatchStatus(str, Enum):
    """Batch job status"""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskStatus(str, Enum):
    """Individual task status"""
    PENDING = "pending"
    CREATING_MATTER = "creating_matter"
    UPLOADING_DOCUMENTS = "uploading_documents"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class CaseFolder(BaseModel):
    """Represents a case folder to be imported"""
    folder_path: str = Field(..., description="Full path to folder")
    folder_name: str = Field(..., description="Folder name (e.g., 'ANDREWS DENNIS_Case3608')")
    client_name: str = Field(..., description="Client name extracted from folder")
    case_number: Optional[str] = None
    file_count: int = 0
    files: List[str] = Field(default_factory=list)
    total_size_bytes: int = 0

    @classmethod
    def from_path(cls, path: str) -> "CaseFolder":
        """Create CaseFolder from folder path"""
        p = Path(path)
        folder_name = p.name

        # Parse folder name: "LASTNAME FIRSTNAME_CaseXXXX"
        client_name = folder_name
        case_number = None

        # Try to extract case number
        match = re.match(r'^(.+?)_Case(\d+)$', folder_name)
        if match:
            client_name = match.group(1).strip()
            case_number = match.group(2)

        # Get files in folder
        files = []
        total_size = 0
        if p.exists() and p.is_dir():
            for f in p.iterdir():
                if f.is_file():
                    files.append(str(f))
                    total_size += f.stat().st_size

        return cls(
            folder_path=str(p),
            folder_name=folder_name,
            client_name=client_name,
            case_number=case_number,
            file_count=len(files),
            files=files,
            total_size_bytes=total_size,
        )

    def get_matter_name(self, include_case_number: bool = False) -> str:
        """Get formatted matter name for MerusCase"""
        if include_case_number and self.case_number:
            return f"{self.client_name} - Case {self.case_number}"
        return self.client_name


class BatchTask(BaseModel):
    """Single matter import task within a batch job"""
    task_id: Optional[int] = None
    job_id: str
    folder: CaseFolder
    matter_id: Optional[str] = None
    meruscase_url: Optional[str] = None
    status: TaskStatus = TaskStatus.PENDING
    uploaded_files: int = 0
    failed_files: int = 0
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    screenshot_path: Optional[str] = None

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }


class BatchJob(BaseModel):
    """Batch import job for multiple matters"""
    job_id: str = Field(..., description="Unique job identifier")
    source_path: str = Field(..., description="Source folder path (e.g., C:\\4850 Law)")
    case_type: str = Field(default="Workers' Compensation", description="Case type for all matters")

    # Counts
    total_folders: int = 0
    total_files: int = 0
    processed_folders: int = 0
    processed_files: int = 0
    failed_folders: int = 0
    failed_files: int = 0

    # Status
    status: BatchStatus = BatchStatus.PENDING
    current_folder: Optional[str] = None
    current_task_id: Optional[int] = None
    error_message: Optional[str] = None

    # Settings
    dry_run: bool = True
    include_case_number_in_name: bool = False
    delay_between_uploads: float = 1.0  # seconds

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Tasks (not persisted in DB, loaded separately)
    tasks: List[BatchTask] = Field(default_factory=list)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }

    @property
    def progress_percent(self) -> float:
        """Calculate overall progress percentage"""
        if self.total_files == 0:
            return 0.0
        return (self.processed_files / self.total_files) * 100

    @property
    def is_resumable(self) -> bool:
        """Check if job can be resumed"""
        return self.status in [BatchStatus.PAUSED, BatchStatus.FAILED]

    def get_summary(self) -> Dict[str, Any]:
        """Get job summary for display"""
        return {
            "job_id": self.job_id,
            "source_path": self.source_path,
            "status": self.status.value,
            "progress": f"{self.progress_percent:.1f}%",
            "folders": f"{self.processed_folders}/{self.total_folders}",
            "files": f"{self.processed_files}/{self.total_files}",
            "failed": f"{self.failed_folders} folders, {self.failed_files} files",
            "current": self.current_folder,
            "dry_run": self.dry_run,
        }


class BatchJobResult(BaseModel):
    """Result summary for completed batch job"""
    job_id: str
    status: BatchStatus
    total_folders: int
    total_files: int
    successful_folders: int
    successful_files: int
    failed_folders: int
    failed_files: int
    duration_seconds: Optional[float] = None
    matters_created: List[Dict[str, str]] = Field(default_factory=list)  # [{name, url}]
    errors: List[Dict[str, str]] = Field(default_factory=list)  # [{folder, error}]


class DryRunPreview(BaseModel):
    """Preview of what batch import will do"""
    job_id: str
    source_path: str
    case_type: str
    include_case_number: bool = False

    # What will be created
    matters_to_create: List[Dict[str, Any]] = Field(default_factory=list)
    # [{name, folder, file_count, total_size_mb}]

    # Summary
    total_matters: int = 0
    total_files: int = 0
    total_size_mb: float = 0.0

    # Warnings
    warnings: List[str] = Field(default_factory=list)
    # e.g., "Large folder: ELIZONDO (1,338 files)"

    # Estimated time
    estimated_hours: Optional[float] = None


# === Helper Functions ===

def scan_source_folder(source_path: str) -> List[CaseFolder]:
    """
    Scan source folder and return list of CaseFolder objects.

    Args:
        source_path: Path to source folder (e.g., "C:\\4850 Law")

    Returns:
        List of CaseFolder objects
    """
    p = Path(source_path)
    if not p.exists():
        raise ValueError(f"Source path does not exist: {source_path}")
    if not p.is_dir():
        raise ValueError(f"Source path is not a directory: {source_path}")

    folders = []
    for item in sorted(p.iterdir()):
        if item.is_dir():
            folder = CaseFolder.from_path(str(item))
            if folder.file_count > 0:  # Only include folders with files
                folders.append(folder)

    return folders


def create_dry_run_preview(
    source_path: str,
    case_type: str = "Workers' Compensation",
    include_case_number: bool = False
) -> DryRunPreview:
    """
    Create a dry-run preview of what will be imported.

    Args:
        source_path: Path to source folder
        case_type: Case type to assign
        include_case_number: Include case number in matter name

    Returns:
        DryRunPreview object
    """
    from datetime import datetime

    job_id = f"preview_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    folders = scan_source_folder(source_path)

    matters = []
    total_files = 0
    total_size = 0
    warnings = []

    for folder in folders:
        matter_name = folder.get_matter_name(include_case_number)
        size_mb = folder.total_size_bytes / (1024 * 1024)

        matters.append({
            "name": matter_name,
            "folder": folder.folder_name,
            "file_count": folder.file_count,
            "total_size_mb": round(size_mb, 2),
        })

        total_files += folder.file_count
        total_size += folder.total_size_bytes

        # Add warnings for large folders
        if folder.file_count > 500:
            warnings.append(f"Large folder: {folder.folder_name} ({folder.file_count:,} files)")

    # Estimate time: ~30 sec per file average
    estimated_hours = (total_files * 30) / 3600

    return DryRunPreview(
        job_id=job_id,
        source_path=source_path,
        case_type=case_type,
        include_case_number=include_case_number,
        matters_to_create=matters,
        total_matters=len(matters),
        total_files=total_files,
        total_size_mb=round(total_size / (1024 * 1024), 2),
        warnings=warnings,
        estimated_hours=round(estimated_hours, 1),
    )
