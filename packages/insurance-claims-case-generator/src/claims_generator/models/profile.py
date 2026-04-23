"""
ClaimProfile — top-level profile aggregating all sub-profiles.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

from pydantic import BaseModel

from claims_generator.models.claimant import ClaimantProfile
from claims_generator.models.employer import EmployerProfile, InsurerProfile
from claims_generator.models.financial import FinancialProfile
from claims_generator.models.medical import MedicalProfile


class ClaimProfile(BaseModel):
    """Complete profile for one generated claim case."""

    claimant: ClaimantProfile
    employer: EmployerProfile
    insurer: InsurerProfile
    medical: MedicalProfile
    financial: FinancialProfile
