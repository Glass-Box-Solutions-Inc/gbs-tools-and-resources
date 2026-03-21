"""
FastAPI dependency injection — shared Pipeline, ProgressTracker, and AuditLogger instances.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import asyncio
from typing import Any

from config import AUDIT_DB_PATH, AUDIT_HMAC_KEY, DB_PATH, OUTPUT_DIR
from data.case_profile_generator import CaseConstraints
from orchestration.audit import PipelineAuditLogger
from orchestration.pipeline import Pipeline
from orchestration.progress_tracker import ProgressTracker
from service.sse import ProgressEmitter

# Shared instances
_tracker: ProgressTracker | None = None
_audit: PipelineAuditLogger | None = None
_active_runs: dict[int, dict[str, Any]] = {}


def get_tracker() -> ProgressTracker:
    global _tracker
    if _tracker is None:
        _tracker = ProgressTracker()
    return _tracker


def get_audit() -> PipelineAuditLogger:
    global _audit
    if _audit is None:
        _audit = PipelineAuditLogger(db_path=AUDIT_DB_PATH, hmac_key=AUDIT_HMAC_KEY)
    return _audit


def get_pipeline() -> Pipeline:
    return Pipeline(get_tracker(), audit=get_audit())


def get_active_runs() -> dict[int, dict[str, Any]]:
    return _active_runs


async def run_generation(
    pipeline: Pipeline,
    count: int,
    seed: int | None,
    stage_distribution: dict[str, float] | None,
    constraints: CaseConstraints | None,
    emitter: ProgressEmitter,
) -> None:
    """Run generation in background, emitting progress via SSE."""
    try:
        emitter.emit("phase", {"phase": "data_generation", "status": "started"})

        def data_callback(event, data):
            emitter.emit(event, data)

        # Run data generation (CPU-bound, but fast enough for sync)
        cases = pipeline.generate_data(
            count=count,
            seed=seed,
            stage_distribution=stage_distribution,
            constraints=constraints,
            progress_callback=data_callback,
        )

        emitter.emit("phase", {"phase": "pdf_generation", "status": "started", "total_docs": sum(len(c.document_specs) for c in cases)})

        def pdf_callback(event, data):
            emitter.emit(event, data)

        # Run PDF generation
        result = pipeline.generate_pdfs(progress_callback=pdf_callback)

        emitter.complete({
            "cases": len(cases),
            "docs_generated": result["generated"],
            "docs_skipped": result["skipped"],
            "errors": result["errors"],
        })
    except Exception as e:
        emitter.error(str(e))
