"""
POST /api/v1/batch — async batch generation.

Accepts 1–500 jobs, enqueues them as a background task, returns a job_id for polling.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from claims_generator.api.job_store import JobStatus, JobStore, get_job_store
from claims_generator.api.schemas import BatchRequest, BatchResponse
from claims_generator.batch_builder import BatchJob, build_batch
from claims_generator.exporter import export_batch_to_zip

logger = logging.getLogger(__name__)
router = APIRouter()


async def _run_batch(
    job_id: str,
    store: JobStore,
    jobs: list[BatchJob],
    generate_pdfs: bool,
    max_workers: int,
) -> None:
    """Background task: run build_batch in a thread pool and update job progress."""
    try:
        loop = asyncio.get_event_loop()

        def _progress_build() -> list:
            """
            Run batch in executor. Progress is approximated — the ThreadPoolExecutor
            doesn't expose per-job callbacks, so we mark RUNNING at start and DONE
            at finish.
            """
            return build_batch(jobs, max_workers=max_workers, generate_pdfs=generate_pdfs)

        # Mark running before dispatching
        await store.update_running(job_id, completed=0)

        cases = await loop.run_in_executor(None, _progress_build)

        # Build ZIP in executor (IO-bound)
        zip_bytes = await loop.run_in_executor(None, export_batch_to_zip, cases)

        await store.mark_done(job_id, zip_bytes)
        logger.info(
            "Batch job %s completed: %d cases, %d bytes ZIP",
            job_id, len(cases), len(zip_bytes),
        )

    except Exception as exc:
        logger.exception("Batch job %s failed", job_id)
        await store.mark_failed(job_id, str(exc))


@router.post("/batch", response_model=BatchResponse, status_code=202, tags=["batch"])
async def submit_batch(
    req: BatchRequest,
    background_tasks: BackgroundTasks,
    store: JobStore = Depends(get_job_store),
) -> BatchResponse:
    """
    Submit a batch of 1–500 case generation jobs.

    Returns immediately with a ``job_id``.  Poll GET /api/v1/jobs/{job_id} for
    progress, then download GET /api/v1/export/{job_id} when status is ``done``.
    """
    scenario_slugs = [j.scenario for j in req.jobs]

    # Validate all scenario slugs before accepting the job
    from claims_generator.scenarios.registry import get_scenario

    for slug in scenario_slugs:
        try:
            get_scenario(slug)
        except KeyError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    batch_jobs = [BatchJob(scenario_slug=j.scenario, seed=j.seed) for j in req.jobs]
    job_id = await store.create(scenario_slugs=scenario_slugs, total=len(batch_jobs))

    background_tasks.add_task(
        _run_batch,
        job_id=job_id,
        store=store,
        jobs=batch_jobs,
        generate_pdfs=req.generate_pdfs,
        max_workers=req.max_workers,
    )

    return BatchResponse(
        job_id=job_id,
        status=JobStatus.PENDING,
        total=len(batch_jobs),
        message=f"Batch job submitted: {len(batch_jobs)} cases queued",
    )
