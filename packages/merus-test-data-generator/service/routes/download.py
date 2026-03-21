"""Download API routes — ZIP download of runs and individual cases."""

from __future__ import annotations

import io
import zipfile

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from config import OUTPUT_DIR
from service.dependencies import get_tracker

router = APIRouter(prefix="/api/download", tags=["download"])


@router.get("/{run_id}")
async def download_run(run_id: int):
    """Download entire run as ZIP."""
    tracker = get_tracker()
    cases = tracker.get_all_cases()
    if not cases:
        raise HTTPException(status_code=404, detail="No cases found")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for case_row in cases:
            case_id = case_row["internal_id"]
            case_dir = OUTPUT_DIR / case_id
            if not case_dir.exists():
                continue
            for pdf_file in case_dir.glob("*.pdf"):
                arcname = f"{case_id}/{pdf_file.name}"
                zf.write(pdf_file, arcname)

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=run_{run_id}_cases.zip"},
    )


@router.get("/{run_id}/{case_id}")
async def download_case(run_id: int, case_id: str):
    """Download a single case as ZIP."""
    case_dir = OUTPUT_DIR / case_id
    if not case_dir.exists():
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")

    # Security check
    if not case_dir.resolve().is_relative_to(OUTPUT_DIR.resolve()):
        raise HTTPException(status_code=403, detail="Access denied")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for pdf_file in case_dir.glob("*.pdf"):
            zf.write(pdf_file, pdf_file.name)

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={case_id}_documents.zip"},
    )
