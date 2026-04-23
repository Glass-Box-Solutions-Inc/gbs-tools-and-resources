"""
ClaimantProfile — demographics for the injured worker.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class ClaimantProfile(BaseModel):
    """Demographic profile of the injured worker."""

    first_name: str
    last_name: str
    date_of_birth: date
    gender: str  # M / F / NB
    address_city: str
    address_county: str
    address_zip: str
    phone: str
    ssn_last4: str = Field(description="Last 4 digits only — never full SSN")
    primary_language: str = "English"
    occupation_title: str = ""
    years_employed: Optional[float] = None
