"""
In-memory async job store for batch generation jobs.

Stores job metadata keyed by UUID. No persistence — cleared on restart.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class JobStatus(str, Enum):
    """Possible states for a batch job."""

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass
class JobRecord:
    """Mutable record for a single batch job."""

    job_id: str
    status: JobStatus = JobStatus.PENDING
    progress: int = 0  # 0–100
    total: int = 0
    completed: int = 0
    result_zip: Optional[bytes] = None
    error: Optional[str] = None
    scenario_slugs: list[str] = field(default_factory=list)


class JobStore:
    """Thread-safe in-memory job store backed by asyncio.Lock."""

    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._lock = asyncio.Lock()

    async def create(self, scenario_slugs: list[str], total: int) -> str:
        """Create a new job record and return its job_id."""
        job_id = str(uuid.uuid4())
        async with self._lock:
            self._jobs[job_id] = JobRecord(
                job_id=job_id,
                status=JobStatus.PENDING,
                total=total,
                scenario_slugs=scenario_slugs,
            )
        return job_id

    async def get(self, job_id: str) -> Optional[JobRecord]:
        """Return the JobRecord for a given job_id, or None if not found."""
        async with self._lock:
            return self._jobs.get(job_id)

    async def update_running(self, job_id: str, completed: int) -> None:
        """Update progress for a running job."""
        async with self._lock:
            record = self._jobs.get(job_id)
            if record is not None:
                record.status = JobStatus.RUNNING
                record.completed = completed
                record.progress = int(completed / record.total * 100) if record.total > 0 else 0

    async def mark_done(self, job_id: str, result_zip: bytes) -> None:
        """Mark a job as done and attach the result ZIP bytes."""
        async with self._lock:
            record = self._jobs.get(job_id)
            if record is not None:
                record.status = JobStatus.DONE
                record.progress = 100
                record.completed = record.total
                record.result_zip = result_zip

    async def mark_failed(self, job_id: str, error: str) -> None:
        """Mark a job as failed with an error message."""
        async with self._lock:
            record = self._jobs.get(job_id)
            if record is not None:
                record.status = JobStatus.FAILED
                record.error = error

    def __len__(self) -> int:
        return len(self._jobs)


# Module-level singleton — shared across the FastAPI app lifetime
_store: Optional[JobStore] = None


def get_job_store() -> JobStore:
    """Return the module-level JobStore singleton."""
    global _store
    if _store is None:
        _store = JobStore()
    return _store


def reset_job_store() -> None:
    """Reset the module-level singleton. Intended for testing only."""
    global _store
    _store = None
