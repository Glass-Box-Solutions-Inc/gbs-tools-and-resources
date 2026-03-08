"""
Document Data Models
Pydantic models for document upload operations
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from pathlib import Path
from enum import Enum


class UploadStatus(str, Enum):
    """Document upload status"""
    PENDING = "pending"
    UPLOADING = "uploading"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class DocumentType(str, Enum):
    """Document file types"""
    PDF = "pdf"
    DOC = "doc"
    DOCX = "docx"
    XLS = "xls"
    XLSX = "xlsx"
    TXT = "txt"
    RTF = "rtf"
    JPG = "jpg"
    JPEG = "jpeg"
    PNG = "png"
    TIFF = "tiff"
    XFML = "xfml"  # MerusCase forms
    OTHER = "other"

    @classmethod
    def from_extension(cls, ext: str) -> "DocumentType":
        """Get DocumentType from file extension"""
        ext_lower = ext.lower().lstrip(".")
        try:
            return cls(ext_lower)
        except ValueError:
            return cls.OTHER


class DocumentUpload(BaseModel):
    """Single document upload record"""
    file_path: str = Field(..., description="Full local file path")
    file_name: str = Field(..., description="Original filename")
    file_size: int = Field(default=0, description="Size in bytes")
    file_type: DocumentType = DocumentType.OTHER
    upload_status: UploadStatus = UploadStatus.PENDING
    meruscase_doc_id: Optional[str] = None
    error_message: Optional[str] = None
    uploaded_at: Optional[datetime] = None

    @classmethod
    def from_path(cls, path: str) -> "DocumentUpload":
        """Create DocumentUpload from file path"""
        p = Path(path)
        return cls(
            file_path=str(p),
            file_name=p.name,
            file_size=p.stat().st_size if p.exists() else 0,
            file_type=DocumentType.from_extension(p.suffix),
        )


class DocumentUploadRequest(BaseModel):
    """Request to upload documents to a matter"""
    matter_id: str = Field(..., description="MerusCase matter ID")
    matter_url: Optional[str] = None
    documents: List[DocumentUpload] = Field(default_factory=list)
    session_id: Optional[str] = None


class DocumentUploadResult(BaseModel):
    """Result of document upload operation"""
    session_id: str
    matter_id: str
    matter_url: Optional[str] = None
    total_documents: int
    uploaded_count: int
    failed_count: int
    skipped_count: int
    status: str  # pending, in_progress, success, partial, failed
    documents: List[DocumentUpload] = Field(default_factory=list)
    error: Optional[str] = None
    screenshot_path: Optional[str] = None
    started_at: datetime = Field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class DocumentUIElement(BaseModel):
    """Discovered UI element for document upload"""
    element_key: str  # 'upload_button', 'file_input', 'drop_zone'
    primary_selector: str
    fallback_selectors: List[str] = Field(default_factory=list)
    element_type: str  # 'input', 'button', 'div'
    supports_multiple: bool = False
    discovered_at: datetime = Field(default_factory=datetime.now)


class DocumentExplorationReport(BaseModel):
    """Report from document upload UI exploration"""
    session_id: str
    matter_url: Optional[str] = None
    documents_nav_selectors: List[str] = Field(default_factory=list)
    upload_button_selectors: List[str] = Field(default_factory=list)
    file_input_selectors: List[str] = Field(default_factory=list)
    drop_zone_selectors: List[str] = Field(default_factory=list)
    upload_method: str = "unknown"  # file_input, drag_drop, api
    supports_multiple: bool = False
    screenshots: List[str] = Field(default_factory=list)
    error: Optional[str] = None
    explored_at: datetime = Field(default_factory=datetime.now)
