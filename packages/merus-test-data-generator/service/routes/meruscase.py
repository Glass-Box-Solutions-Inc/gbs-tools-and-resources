"""MerusCase integration API routes — create cases + upload documents."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse

from service.dependencies import get_active_runs, get_pipeline, get_tracker
from service.models.requests import MerusCaseUploadRequest
from service.sse import ProgressEmitter

router = APIRouter(prefix="/api/meruscase", tags=["meruscase"])


@router.post("/create-cases/{run_id}")
async def create_cases(run_id: int, request: MerusCaseUploadRequest, background_tasks: BackgroundTasks):
    """Create cases in MerusCase via browser automation."""
    tracker = get_tracker()
    summary = tracker.get_status_summary()
    if not summary["has_run"]:
        raise HTTPException(status_code=404, detail="No generation run found")

    pipeline = get_pipeline()
    # Load existing case data
    pipeline.generate_data()

    emitter = ProgressEmitter()
    active_runs = get_active_runs()
    active_runs[f"merus_create_{run_id}"] = {"emitter": emitter}

    async def _create():
        try:
            emitter.emit("phase", {"phase": "case_creation", "status": "started"})
            result = await pipeline.create_cases(dry_run=request.dry_run)
            emitter.complete(result)
        except Exception as e:
            emitter.error(str(e))
        finally:
            active_runs.pop(f"merus_create_{run_id}", None)

    background_tasks.add_task(_create)
    return {"status": "creating", "run_id": run_id, "dry_run": request.dry_run}


@router.post("/upload-documents/{run_id}")
async def upload_documents(run_id: int, background_tasks: BackgroundTasks):
    """Upload documents to MerusCase via API."""
    tracker = get_tracker()
    summary = tracker.get_status_summary()
    if not summary["has_run"]:
        raise HTTPException(status_code=404, detail="No generation run found")

    pipeline = get_pipeline()
    emitter = ProgressEmitter()
    active_runs = get_active_runs()
    active_runs[f"merus_upload_{run_id}"] = {"emitter": emitter}

    async def _upload():
        try:
            emitter.emit("phase", {"phase": "document_upload", "status": "started"})
            result = await pipeline.upload_documents()
            emitter.complete(result)
        except Exception as e:
            emitter.error(str(e))
        finally:
            active_runs.pop(f"merus_upload_{run_id}", None)

    background_tasks.add_task(_upload)
    return {"status": "uploading", "run_id": run_id}


@router.get("/status/{run_id}")
async def meruscase_status(run_id: int):
    """SSE stream of MerusCase operation progress."""
    active_runs = get_active_runs()

    # Check for create or upload operations
    for key in [f"merus_create_{run_id}", f"merus_upload_{run_id}"]:
        run_data = active_runs.get(key)
        if run_data:
            emitter: ProgressEmitter = run_data["emitter"]
            return StreamingResponse(
                emitter.stream(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                },
            )

    return {"status": "no_active_operation", "run_id": run_id}
