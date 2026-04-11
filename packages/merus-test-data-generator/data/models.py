"""
Pydantic models for generated test case data.
GeneratedCase is the single source of truth per case.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

# Import canonical taxonomy — 350 subtypes, 15 types
from data.taxonomy import DocumentSubtype, DocumentType  # noqa: F401


class OutputFormat(str, Enum):
    """Output format for a generated document."""
    PDF = "pdf"            # Native vector PDF (reportlab)
    EML = "eml"            # RFC 2822 email file
    DOCX = "docx"          # Microsoft Word document
    SCANNED_PDF = "scanned_pdf"  # Image-based PDF simulating a scanned original


class LitigationStage(str, Enum):
    INTAKE = "intake"
    ACTIVE_TREATMENT = "active_treatment"
    DISCOVERY = "discovery"
    MEDICAL_LEGAL = "medical_legal"
    SETTLEMENT = "settlement"
    RESOLVED = "resolved"


class InjuryType(str, Enum):
    SPECIFIC = "specific"
    CUMULATIVE_TRAUMA = "cumulative_trauma"
    DEATH = "death"


class GeneratedApplicant(BaseModel):
    first_name: str
    last_name: str
    full_name: str = ""
    date_of_birth: date
    ssn_last_four: str
    phone: str
    email: str
    address_street: str
    address_city: str
    address_state: str = "CA"
    address_zip: str

    def model_post_init(self, __context: Any) -> None:
        if not self.full_name:
            self.full_name = f"{self.first_name} {self.last_name}"


class GeneratedEmployer(BaseModel):
    company_name: str
    address_street: str
    address_city: str
    address_state: str = "CA"
    address_zip: str
    phone: str
    position: str
    hire_date: date
    hourly_rate: float
    weekly_hours: float = 40.0
    department: str = ""


class GeneratedInsurance(BaseModel):
    carrier_name: str
    claim_number: str
    policy_number: str
    adjuster_name: str
    adjuster_phone: str
    adjuster_email: str
    defense_firm: str
    defense_attorney: str
    defense_phone: str
    defense_email: str


class GeneratedInjury(BaseModel):
    date_of_injury: date
    injury_type: InjuryType
    body_parts: list[str]
    icd10_codes: list[str]
    adj_number: str
    description: str
    mechanism: str


class GeneratedPhysician(BaseModel):
    first_name: str
    last_name: str
    full_name: str = ""
    specialty: str
    facility: str
    address: str
    phone: str
    license_number: str
    npi: str

    def model_post_init(self, __context: Any) -> None:
        if not self.full_name:
            self.full_name = f"{self.first_name} {self.last_name}, M.D."


class GeneratedCaseTimeline(BaseModel):
    date_of_injury: date
    date_claim_filed: date
    date_first_treatment: date
    date_claim_response: Optional[date] = None
    date_application_filed: Optional[date] = None
    date_discovery_start: Optional[date] = None
    date_qme_evaluation: Optional[date] = None
    date_ame_evaluation: Optional[date] = None
    date_deposition: Optional[date] = None
    date_dor_filed: Optional[date] = None
    date_settlement_conference: Optional[date] = None
    date_lien_filed: Optional[date] = None
    date_lien_conference: Optional[date] = None
    date_ur_dispute: Optional[date] = None
    date_imr_decision: Optional[date] = None
    date_trial: Optional[date] = None
    date_resolved: Optional[date] = None


class DocumentSpec(BaseModel):
    subtype: DocumentSubtype
    title: str
    doc_date: date
    template_class: str
    output_format: OutputFormat = OutputFormat.PDF
    context: dict[str, Any] = Field(default_factory=dict)
    sequence_number: int = 1


class GeneratedCase(BaseModel):
    case_number: int
    internal_id: str
    litigation_stage: LitigationStage
    applicant: GeneratedApplicant
    employer: GeneratedEmployer
    insurance: GeneratedInsurance
    injuries: list[GeneratedInjury]
    treating_physician: GeneratedPhysician
    qme_physician: Optional[GeneratedPhysician] = None
    prior_providers: list[GeneratedPhysician] = Field(default_factory=list)
    timeline: GeneratedCaseTimeline
    venue: str
    judge_name: str
    case_title: str = ""
    document_specs: list[DocumentSpec] = Field(default_factory=list)
    # New: lifecycle parameters that produced this case
    case_parameters: Optional[Any] = None

    def model_post_init(self, __context: Any) -> None:
        if not self.case_title:
            self.case_title = (
                f"{self.applicant.full_name} v. {self.employer.company_name}"
            )
