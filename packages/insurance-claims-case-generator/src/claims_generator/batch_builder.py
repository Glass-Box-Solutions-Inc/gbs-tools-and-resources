"""
Batch builder — ThreadPoolExecutor wrapper for generating multiple ClaimCase objects.

Uses concurrent.futures.ThreadPoolExecutor for parallelism.
reportlab is thread-safe for independent documents.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from claims_generator.case_builder import build_case
from claims_generator.models.claim import ClaimCase

logger = logging.getLogger(__name__)


@dataclass
class BatchJob:
    """A single case generation job in a batch."""

    scenario_slug: str
    seed: int

    @property
    def job_id(self) -> str:
        return f"{self.scenario_slug}:{self.seed}"


def build_batch(
    jobs: list[BatchJob],
    max_workers: int = 4,
    generate_pdfs: bool = True,
) -> list[ClaimCase]:
    """
    Generate multiple ClaimCase objects in parallel using a thread pool.

    Args:
        jobs: List of BatchJob specifications.
        max_workers: Maximum concurrent threads. Default 4.
        generate_pdfs: Whether to generate PDFs for each case. Default True.

    Returns:
        List of ClaimCase objects in the same order as input jobs.
        Failed jobs result in None entries in the result list (logged as errors).

    Raises:
        ValueError: If jobs list is empty.
    """
    if not jobs:
        raise ValueError("build_batch requires at least one job")

    results: dict[int, ClaimCase | None] = {}

    def _build_one(index: int, job: BatchJob) -> tuple[int, ClaimCase | None]:
        try:
            case = build_case(
                scenario_slug=job.scenario_slug,
                seed=job.seed,
                generate_pdfs=generate_pdfs,
            )
            logger.info(
                "Built case %s for job %s (%d documents)",
                case.case_id,
                job.job_id,
                len(case.document_events),
            )
            return index, case
        except Exception:
            logger.exception("Failed to build case for job %s", job.job_id)
            return index, None

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_build_one, i, job): i
            for i, job in enumerate(jobs)
        }
        for future in as_completed(futures):
            idx, case = future.result()
            results[idx] = case

    # Return in original order, filtering None failures
    ordered = [results.get(i) for i in range(len(jobs))]
    failures = sum(1 for r in ordered if r is None)
    if failures:
        logger.warning("%d/%d batch jobs failed", failures, len(jobs))

    return [r for r in ordered if r is not None]


def build_batch_simple(
    count: int,
    scenario_slug: str = "standard_claim",
    seed_start: int = 0,
    max_workers: int = 4,
    generate_pdfs: bool = True,
) -> list[ClaimCase]:
    """
    Convenience wrapper: generate `count` cases of the same scenario with sequential seeds.

    Args:
        count: Number of cases to generate.
        scenario_slug: Scenario to use for all cases.
        seed_start: Starting seed value (increments by 1 for each case).
        max_workers: Thread pool size.
        generate_pdfs: Whether to generate PDFs.

    Returns:
        List of ClaimCase objects.
    """
    jobs = [
        BatchJob(scenario_slug=scenario_slug, seed=seed_start + i)
        for i in range(count)
    ]
    return build_batch(jobs, max_workers=max_workers, generate_pdfs=generate_pdfs)
