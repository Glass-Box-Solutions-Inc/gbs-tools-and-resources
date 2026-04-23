"""
EmployerProfile and InsurerProfile.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class EmployerProfile(BaseModel):
    """Profile of the employer at time of injury."""

    company_name: str
    industry: str
    address_city: str
    address_state: str = "CA"
    ein_last4: str = Field(default="0000", description="Last 4 digits of EIN only")
    size_category: str = "medium"  # small / medium / large


class InsurerProfile(BaseModel):
    """Profile of the workers' compensation insurer or TPA."""

    carrier_name: str
    claim_number: str
    adjuster_name: str
    adjuster_phone: str
    adjuster_email: str
    policy_number: str
