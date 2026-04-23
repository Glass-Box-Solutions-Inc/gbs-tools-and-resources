"""
ScenarioPreset — base model for named scenario configurations.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ScenarioPreset(BaseModel):
    """Named scenario preset that seeds ClaimState flags."""

    slug: str = Field(description="Machine-readable identifier, e.g. 'litigated_qme'")
    display_name: str
    description: str

    # ClaimState flags
    litigated: bool = False
    attorney_represented: bool = False
    ct: bool = False  # cumulative trauma
    denied_scenario: bool = False
    death_claim: bool = False
    ptd_claim: bool = False
    psych_overlay: bool = False
    multi_employer: bool = False
    split_carrier: bool = False
    high_liens: bool = False
    sjdb_dispute: bool = False
    expedited: bool = False
    investigation_active: bool = False

    # Expected document count range for validation
    expected_doc_min: int = 8
    expected_doc_max: int = 30

    # Optional target stage override
    target_stage: Optional[str] = None
