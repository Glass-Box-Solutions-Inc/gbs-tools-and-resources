"""
FinancialProfile — TD/PD rate calculations.

TD rate table MUST match AdjudiCLAIMS-ai-app/server/services/benefit-calculator.service.ts exactly.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class FinancialProfile(BaseModel):
    """Financial profile derived from the claimant's earnings and injury year."""

    injury_year: int
    average_weekly_wage: float = Field(ge=0.0, description="AWW in dollars")
    td_weekly_rate: float = Field(ge=0.0, description="TD weekly benefit rate")
    td_min_rate: float = Field(ge=0.0, description="Statutory minimum TD rate for injury year")
    td_max_rate: float = Field(ge=0.0, description="Statutory maximum TD rate for injury year")
    estimated_pd_percent: Optional[float] = Field(
        default=None, ge=0.0, le=100.0, description="Estimated permanent disability %"
    )
    estimated_pd_weeks: Optional[float] = Field(
        default=None, ge=0.0, description="Estimated PD payment weeks"
    )
    life_pension_eligible: bool = False
