"""
Medical profile models — body parts, ICD-10 entries, physicians.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class BodyPart(BaseModel):
    """A single injured body part."""

    body_part: str  # e.g. "lumbar spine"
    laterality: Optional[str] = None  # left / right / bilateral / None
    primary: bool = False


class ICD10Entry(BaseModel):
    """ICD-10 diagnosis code with description."""

    code: str  # e.g. "M54.5"
    description: str
    body_part: str


class PhysicianProfile(BaseModel):
    """A physician involved in the claim."""

    role: str  # treating_md / qme / ame / ime / psych
    first_name: str
    last_name: str
    specialty: str
    license_number: str
    address_city: str
    npi: str


class MedicalProfile(BaseModel):
    """Full medical profile for the claim."""

    date_of_injury: str  # ISO date string
    injury_mechanism: str  # e.g. "slip and fall", "repetitive motion"
    body_parts: list[BodyPart]
    icd10_codes: list[ICD10Entry]
    treating_physician: PhysicianProfile
    qme_physician: Optional[PhysicianProfile] = None
    ame_physician: Optional[PhysicianProfile] = None
    has_surgery: bool = False
    surgery_description: Optional[str] = None
    mmi_reached: bool = False
    wpi_percent: Optional[float] = None  # Whole Person Impairment %
