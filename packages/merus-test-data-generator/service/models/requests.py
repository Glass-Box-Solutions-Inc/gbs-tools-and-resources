"""
Request models for the FastAPI service.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    count: int = Field(default=20, ge=1, le=500, description="Number of cases to generate")
    seed: Optional[int] = Field(default=None, description="Random seed for reproducibility")
    stage_distribution: Optional[dict[str, float]] = Field(
        default=None,
        description="Stage distribution proportions (e.g. {'intake': 0.3, 'resolved': 0.7})",
    )
    constraints: Optional[dict] = Field(
        default=None,
        description="Generation constraints (min_surgery_cases, attorney_rate, etc.)",
    )


class MerusCaseUploadRequest(BaseModel):
    dry_run: bool = Field(default=False, description="Preview without uploading")
