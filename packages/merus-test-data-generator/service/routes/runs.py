"""Runs API routes — list, detail, delete runs."""

from __future__ import annotations

import shutil

from fastapi import APIRouter, HTTPException

from config import OUTPUT_DIR
from service.dependencies import get_tracker
from service.models.responses import RunStatus

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.get("", response_model=list[RunStatus])
async def list_runs():
    """List all runs."""
    tracker = get_tracker()
    summary = tracker.get_status_summary()
    if not summary["has_run"]:
        return []
    return [RunStatus(
        run_id=summary["run_id"],
        status=summary["run_status"],
        started_at=summary.get("started_at"),
        completed_at=summary.get("completed_at"),
        total_cases=summary["total_cases"],
        total_docs=summary["total_docs"],
        cases_data_generated=summary["cases_data_generated"],
        cases_pdfs_generated=summary["cases_pdfs_generated"],
        docs_pdf_generated=summary["docs_pdf_generated"],
        docs_uploaded=summary.get("docs_uploaded", 0),
        errors=summary.get("cases_errored", 0),
    )]


@router.get("/{run_id}", response_model=RunStatus)
async def get_run(run_id: int):
    """Get run details."""
    tracker = get_tracker()
    summary = tracker.get_status_summary()
    if not summary["has_run"] or summary["run_id"] != run_id:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return RunStatus(
        run_id=summary["run_id"],
        status=summary["run_status"],
        started_at=summary.get("started_at"),
        completed_at=summary.get("completed_at"),
        total_cases=summary["total_cases"],
        total_docs=summary["total_docs"],
        cases_data_generated=summary["cases_data_generated"],
        cases_pdfs_generated=summary["cases_pdfs_generated"],
        docs_pdf_generated=summary["docs_pdf_generated"],
        docs_uploaded=summary.get("docs_uploaded", 0),
        errors=summary.get("cases_errored", 0),
    )


@router.delete("/{run_id}")
async def delete_run(run_id: int):
    """Delete a run and its output files."""
    tracker = get_tracker()
    summary = tracker.get_status_summary()
    if not summary["has_run"] or summary["run_id"] != run_id:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    # Delete output files
    cases = tracker.get_all_cases()
    for case_row in cases:
        case_dir = OUTPUT_DIR / case_row["internal_id"]
        if case_dir.exists():
            shutil.rmtree(case_dir)

    # Reset tracker
    tracker.reset()

    return {"status": "deleted", "run_id": run_id}
