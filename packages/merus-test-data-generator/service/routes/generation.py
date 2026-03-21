"""Generation API routes — start generation, SSE progress stream."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import StreamingResponse

from data.case_profile_generator import CaseConstraints
from service.dependencies import get_active_runs, get_pipeline, get_tracker, run_generation
from service.models.requests import GenerateRequest
from service.models.responses import GenerateResponse
from service.sse import ProgressEmitter

router = APIRouter(prefix="/api", tags=["generation"])


@router.post("/generate", response_model=GenerateResponse)
async def start_generation(request: GenerateRequest, background_tasks: BackgroundTasks):
    """Start a new generation run. Returns run_id immediately."""
    pipeline = get_pipeline()
    tracker = get_tracker()

    # Parse constraints
    constraints = None
    if request.constraints:
        constraints = CaseConstraints(**request.constraints)

    # Create emitter for progress tracking
    emitter = ProgressEmitter()

    # Start run to get run_id
    run_id = tracker.start_run(total_cases=request.count)

    # Store in active runs
    active_runs = get_active_runs()
    active_runs[run_id] = {"emitter": emitter, "pipeline": pipeline}

    # Run generation in background
    background_tasks.add_task(
        _run_in_thread,
        pipeline, request.count, request.seed,
        request.stage_distribution, constraints, emitter, run_id,
    )

    return GenerateResponse(
        run_id=run_id,
        status="generating",
        message=f"Generating {request.count} cases...",
    )


async def _run_in_thread(
    pipeline, count, seed, stage_distribution, constraints, emitter, run_id
):
    """Run generation and emit progress."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        _sync_generate,
        pipeline, count, seed, stage_distribution, constraints, emitter,
    )
    # Remove from active runs when done
    active_runs = get_active_runs()
    active_runs.pop(run_id, None)


def _sync_generate(pipeline, count, seed, stage_distribution, constraints, emitter):
    """Synchronous generation wrapper for thread executor."""
    try:
        emitter.emit("phase", {"phase": "data_generation", "status": "started"})

        def data_callback(event, data):
            emitter.emit(event, data)

        cases = pipeline.generate_data(
            count=count,
            seed=seed,
            stage_distribution=stage_distribution,
            constraints=constraints,
            progress_callback=data_callback,
        )

        total_docs = sum(len(c.document_specs) for c in cases)
        emitter.emit("phase", {"phase": "pdf_generation", "status": "started", "total_docs": total_docs})

        def pdf_callback(event, data):
            emitter.emit(event, data)

        result = pipeline.generate_pdfs(progress_callback=pdf_callback)

        emitter.complete({
            "cases": len(cases),
            "docs_generated": result["generated"],
            "docs_skipped": result["skipped"],
            "errors": result["errors"],
        })
    except Exception as e:
        emitter.error(str(e))


@router.get("/generate/{run_id}/status")
async def generation_status(run_id: int):
    """SSE stream of generation progress for a run."""
    active_runs = get_active_runs()
    run_data = active_runs.get(run_id)

    if not run_data:
        # Run may be completed — return status from tracker
        tracker = get_tracker()
        summary = tracker.get_status_summary()
        return {"run_id": run_id, "status": "completed" if summary.get("has_run") else "not_found"}

    emitter: ProgressEmitter = run_data["emitter"]
    return StreamingResponse(
        emitter.stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
