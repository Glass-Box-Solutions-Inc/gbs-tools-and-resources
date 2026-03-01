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


class DocumentSubtype(str, Enum):
    # Medical
    TREATING_PHYSICIAN_REPORT = "TREATING_PHYSICIAN_REPORT"
    DIAGNOSTIC_REPORT = "DIAGNOSTIC_REPORT"
    OPERATIVE_HOSPITAL_RECORDS = "OPERATIVE_HOSPITAL_RECORDS"
    QME_AME_REPORT = "QME_AME_REPORT"
    UTILIZATION_REVIEW = "UTILIZATION_REVIEW"
    PHARMACY_RECORDS = "PHARMACY_RECORDS"
    BILLING_UB04_HCFA_SUPERBILLS = "BILLING_UB04_HCFA_SUPERBILLS"
    # Legal
    APPLICATION_FOR_ADJUDICATION = "APPLICATION_FOR_ADJUDICATION"
    DECLARATION_OF_READINESS = "DECLARATION_OF_READINESS"
    MINUTES_ORDERS_FINDINGS = "MINUTES_ORDERS_FINDINGS"
    STIPULATIONS = "STIPULATIONS"
    COMPROMISE_AND_RELEASE = "COMPROMISE_AND_RELEASE"
    # Correspondence
    ADJUSTER_LETTER = "ADJUSTER_LETTER"
    DEFENSE_COUNSEL_LETTER = "DEFENSE_COUNSEL_LETTER"
    COURT_NOTICE = "COURT_NOTICE"
    CLIENT_INTAKE_CORRESPONDENCE = "CLIENT_INTAKE_CORRESPONDENCE"
    # Discovery
    SUBPOENA_SDT_ISSUED = "SUBPOENA_SDT_ISSUED"
    DEPOSITION_NOTICE = "DEPOSITION_NOTICE"
    DEPOSITION_TRANSCRIPT = "DEPOSITION_TRANSCRIPT"
    SUBPOENAED_RECORDS = "SUBPOENAED_RECORDS"
    # Employment
    WAGE_STATEMENTS = "WAGE_STATEMENTS"
    JOB_DESCRIPTION = "JOB_DESCRIPTION"
    PERSONNEL_FILE = "PERSONNEL_FILE"
    # Claim forms
    CLAIM_FORM = "CLAIM_FORM"
    EMPLOYER_REPORT = "EMPLOYER_REPORT"
    # Summaries
    MEDICAL_CHRONOLOGY = "MEDICAL_CHRONOLOGY"
    SETTLEMENT_MEMO = "SETTLEMENT_MEMO"


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
    date_application_filed: Optional[date] = None
    date_discovery_start: Optional[date] = None
    date_qme_evaluation: Optional[date] = None
    date_deposition: Optional[date] = None
    date_dor_filed: Optional[date] = None
    date_settlement_conference: Optional[date] = None
    date_resolved: Optional[date] = None


class DocumentSpec(BaseModel):
    subtype: DocumentSubtype
    title: str
    doc_date: date
    template_class: str
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
    timeline: GeneratedCaseTimeline
    venue: str
    judge_name: str
    case_title: str = ""
    document_specs: list[DocumentSpec] = Field(default_factory=list)

    def model_post_init(self, __context: Any) -> None:
        if not self.case_title:
            self.case_title = (
                f"{self.applicant.full_name} v. {self.employer.company_name}"
            )
