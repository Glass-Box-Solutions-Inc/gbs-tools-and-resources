"""Preview API routes — browse generated cases and documents."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from config import OUTPUT_DIR
from service.dependencies import get_tracker
from service.models.responses import CaseDetail, CasePreview, DocumentPreview

router = APIRouter(prefix="/api/preview", tags=["preview"])


@router.get("/{run_id}/cases", response_model=list[CasePreview])
async def list_cases(run_id: int):
    """List all generated cases for a run."""
    tracker = get_tracker()
    cases = tracker.get_all_cases()
    return [
        CasePreview(
            internal_id=c["internal_id"],
            case_number=c["case_number"],
            applicant_name=c["applicant_name"],
            employer_name=c.get("employer_name", ""),
            litigation_stage=c["litigation_stage"],
            status=c["status"],
            total_docs=c["total_docs"],
            docs_generated=c.get("pdfs_generated", 0),
        )
        for c in cases
    ]


@router.get("/{run_id}/cases/{case_id}", response_model=CaseDetail)
async def get_case_detail(run_id: int, case_id: str):
    """Get case detail with document manifest."""
    tracker = get_tracker()
    cases = tracker.get_all_cases()
    case_row = next((c for c in cases if c["internal_id"] == case_id), None)
    if not case_row:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")

    docs = tracker.get_docs_for_case(case_id)
    doc_previews = [
        DocumentPreview(
            filename=d["filename"],
            subtype=d["subtype"],
            title=d["title"],
            doc_date=d["doc_date"],
            pdf_generated=bool(d["pdf_generated"]),
            pdf_path=d.get("pdf_path"),
        )
        for d in docs
    ]

    case_preview = CasePreview(
        internal_id=case_row["internal_id"],
        case_number=case_row["case_number"],
        applicant_name=case_row["applicant_name"],
        employer_name=case_row.get("employer_name", ""),
        litigation_stage=case_row["litigation_stage"],
        status=case_row["status"],
        total_docs=case_row["total_docs"],
        docs_generated=case_row.get("pdfs_generated", 0),
    )

    return CaseDetail(case=case_preview, documents=doc_previews)


_MIME_TYPES: dict[str, str] = {
    ".pdf": "application/pdf",
    ".eml": "message/rfc822",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


@router.get("/{run_id}/documents/{case_id}/{filename}")
async def get_document(run_id: int, case_id: str, filename: str):
    """Serve a generated document (PDF, EML, or DOCX)."""
    doc_path = OUTPUT_DIR / case_id / filename
    if not doc_path.exists():
        raise HTTPException(status_code=404, detail=f"Document not found: {filename}")

    # Security: verify path is within OUTPUT_DIR
    if not doc_path.resolve().is_relative_to(OUTPUT_DIR.resolve()):
        raise HTTPException(status_code=403, detail="Access denied")

    suffix = Path(filename).suffix.lower()
    media_type = _MIME_TYPES.get(suffix, "application/octet-stream")

    return FileResponse(
        path=str(doc_path),
        media_type=media_type,
        filename=filename,
    )
