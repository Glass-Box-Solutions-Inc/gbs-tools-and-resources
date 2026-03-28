"""
WC case lifecycle engine — models a Workers' Compensation case as a DAG
with probabilistic branching. Each case walks the graph from INJURY to its
target_stage, emitting documents at each node.

The lifecycle graph:

  INJURY → CLAIM_FILED → CLAIM_RESPONSE
    ├─ accepted (55%) → ACTIVE_TREATMENT
    ├─ delayed (30%) → INVESTIGATION → CLAIM_RESOLVED
    └─ denied (15%) → APPEAL → CLAIM_RESOLVED
                             ↓
  ACTIVE_TREATMENT → UR_DISPUTE_BRANCH
    ├─ no dispute (60%) ───────────────────────┐
    └─ UR dispute (40%) → UR_DECISION          │
         ├─ approved → ───────────────────────┐│
         └─ denied → IMR_APPEAL               ││
              ├─ upheld ────────────────────┐  ││
              └─ overturned ──────────────┐ │  ││
                                          ↓ ↓  ↓↓
  APPLICATION_FOR_ADJUDICATION (if attorney) ←─┘
                             ↓
  MEDICAL_LEGAL_BRANCH
    ├─ QME panel (50%) → QME_EVALUATION
    ├─ AME agreed (20%) → AME_EVALUATION
    └─ none (30%) ──────────────────────────┐
                                            ↓
  DISCOVERY (depositions, subpoenas) ←──────┘
                             ↓
  LIEN_BRANCH
    ├─ has liens (30%) → LIEN_FILING → LIEN_CONFERENCE
    └─ no liens (70%) ─────────────────────┐
                                            ↓
  RESOLUTION_BRANCH ←─────────────────────┘
    ├─ Stipulations (45%)
    ├─ Compromise & Release (40%)
    └─ Trial (15%)
                             ↓
  POST_RESOLUTION
    ├─ petition to reopen (10%)
    └─ complete (90%)

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Case lifecycle stages (more granular than the old 6-stage LitigationStage)
# ---------------------------------------------------------------------------

class LifecycleStage(str, Enum):
    """Granular lifecycle stages for the DAG."""
    INJURY = "injury"
    CLAIM_FILED = "claim_filed"
    CLAIM_RESPONSE = "claim_response"
    INVESTIGATION = "investigation"
    APPEAL = "appeal"
    ACTIVE_TREATMENT = "active_treatment"
    UR_DISPUTE = "ur_dispute"
    UR_DECISION = "ur_decision"
    IMR_APPEAL = "imr_appeal"
    APPLICATION_FILED = "application_filed"
    QME_EVALUATION = "qme_evaluation"
    AME_EVALUATION = "ame_evaluation"
    DISCOVERY = "discovery"
    LIEN_FILING = "lien_filing"
    LIEN_CONFERENCE = "lien_conference"
    RESOLUTION_STIPULATIONS = "resolution_stipulations"
    RESOLUTION_CR = "resolution_cr"
    RESOLUTION_TRIAL = "resolution_trial"
    POST_RESOLUTION = "post_resolution"


# Map the old 6-stage enum to target lifecycle stages
LITIGATION_STAGE_TO_TARGET: dict[str, LifecycleStage] = {
    "intake": LifecycleStage.CLAIM_RESPONSE,
    "active_treatment": LifecycleStage.ACTIVE_TREATMENT,
    "discovery": LifecycleStage.DISCOVERY,
    "medical_legal": LifecycleStage.QME_EVALUATION,
    "settlement": LifecycleStage.RESOLUTION_STIPULATIONS,
    "resolved": LifecycleStage.POST_RESOLUTION,
}


# ---------------------------------------------------------------------------
# CaseParameters — controls all probabilistic branching
# ---------------------------------------------------------------------------

class CaseParameters(BaseModel):
    """All parameters that control a case's lifecycle path and document generation."""

    # Claim response path
    claim_response: str = Field(
        default="random",
        description="accepted / delayed / denied / random",
    )

    # Attorney involvement
    has_attorney: bool = Field(default=True)

    # UR dispute path
    has_ur_dispute: bool = Field(default=False)
    ur_decision: str = Field(
        default="random",
        description="approved / denied / random (only if has_ur_dispute)",
    )
    imr_filed: bool = Field(default=False)
    imr_outcome: str = Field(
        default="random",
        description="upheld / overturned / random (only if imr_filed)",
    )

    # Medical-legal evaluation type
    eval_type: str = Field(
        default="random",
        description="qme / ame / none / random",
    )

    # Resolution type
    resolution_type: str = Field(
        default="random",
        description="stipulations / c_and_r / trial / pending / random",
    )

    # Case characteristics
    has_surgery: bool = Field(default=False)
    has_psych_component: bool = Field(default=False)
    has_liens: bool = Field(default=False)
    num_body_parts: int = Field(default=1, ge=1, le=5)

    # Complexity scaling — "standard" or "complex" (Salerno-style mega-cases)
    complexity: str = Field(default="standard", description="standard / complex")

    # Target stage — how far the case has progressed
    target_stage: str = Field(
        default="resolved",
        description="One of LitigationStage values: intake, active_treatment, discovery, medical_legal, settlement, resolved",
    )

    # Injury characteristics
    injury_type: str = Field(default="random", description="specific / cumulative_trauma / death / random")
    body_part_category: str = Field(default="random", description="spine / upper_extremity / lower_extremity / psyche / internal / head / random")

    def resolve_random(self, rng: random.Random) -> CaseParameters:
        """Resolve all 'random' fields using the provided RNG. Returns a new instance."""
        data = self.model_dump()

        if data["claim_response"] == "random":
            r = rng.random()
            if r < 0.55:
                data["claim_response"] = "accepted"
            elif r < 0.85:
                data["claim_response"] = "delayed"
            else:
                data["claim_response"] = "denied"

        if data["eval_type"] == "random":
            r = rng.random()
            if r < 0.50:
                data["eval_type"] = "qme"
            elif r < 0.70:
                data["eval_type"] = "ame"
            else:
                data["eval_type"] = "none"

        if data["resolution_type"] == "random":
            r = rng.random()
            if r < 0.45:
                data["resolution_type"] = "stipulations"
            elif r < 0.85:
                data["resolution_type"] = "c_and_r"
            else:
                data["resolution_type"] = "trial"

        if data["ur_decision"] == "random":
            data["ur_decision"] = rng.choice(["approved", "denied"])

        if data["imr_outcome"] == "random":
            data["imr_outcome"] = rng.choice(["upheld", "overturned"])

        if data["injury_type"] == "random":
            data["injury_type"] = rng.choices(
                ["specific", "cumulative_trauma", "death"],
                weights=[0.65, 0.33, 0.02],
            )[0]

        if data["body_part_category"] == "random":
            data["body_part_category"] = rng.choices(
                ["spine", "upper_extremity", "lower_extremity", "psyche", "internal", "head"],
                weights=[0.30, 0.25, 0.20, 0.12, 0.08, 0.05],
            )[0]

        return CaseParameters(**data)


# ---------------------------------------------------------------------------
# Document emission rules
# ---------------------------------------------------------------------------

@dataclass
class NodeDocumentRule:
    """Rule for emitting a document at a lifecycle node."""
    subtype: str                          # DocumentSubtype value from taxonomy
    count: tuple[int, int] = (1, 1)       # (min, max) documents
    probability: float = 1.0              # 0.0–1.0 chance of appearing
    condition: str | None = None          # e.g., "has_surgery", "eval_type == 'qme'"
    date_anchor: str = "doi"              # Reference date: doi, claim_filed, application_filed, etc.
    date_offset_days: tuple[int, int] = (0, 30)  # (min, max) days from anchor


# ---------------------------------------------------------------------------
# Lifecycle node definitions with document emission rules
# ---------------------------------------------------------------------------

# Each lifecycle stage maps to a list of document rules.
# These are data-driven — no if/elif chains.

LIFECYCLE_DOCUMENT_RULES: dict[str, list[NodeDocumentRule]] = {
    # --- INJURY / CLAIM FILED ---
    "injury": [
        NodeDocumentRule("EMERGENCY_ROOM_RECORDS", (0, 1), 0.35, date_anchor="doi", date_offset_days=(0, 1)),
    ],

    "claim_filed": [
        NodeDocumentRule("CLAIM_FORM_DWC1", (1, 1), 1.0, date_anchor="doi", date_offset_days=(1, 14)),
        NodeDocumentRule("EMPLOYER_REPORT_INJURY", (1, 1), 1.0, date_anchor="doi", date_offset_days=(3, 21)),
        NodeDocumentRule("FIRST_REPORT_OF_INJURY_PHYSICIAN", (1, 1), 0.8, date_anchor="doi", date_offset_days=(1, 7)),
        NodeDocumentRule("CLIENT_INTAKE_CORRESPONDENCE", (1, 2), 1.0, date_anchor="doi", date_offset_days=(7, 30)),
        NodeDocumentRule("MPN_AUTHORIZATION", (0, 1), 0.6, date_anchor="doi", date_offset_days=(3, 14)),
        NodeDocumentRule("WAGE_STATEMENTS_PRE_INJURY", (1, 1), 1.0, date_anchor="doi", date_offset_days=(14, 60)),
        NodeDocumentRule("JOB_DESCRIPTION_PRE_INJURY", (0, 1), 0.7, date_anchor="doi", date_offset_days=(14, 45)),
        NodeDocumentRule("NOTICE_OF_BENEFITS", (0, 1), 0.5, date_anchor="doi", date_offset_days=(14, 30)),
    ],

    "claim_response": [
        NodeDocumentRule("CLAIM_ACCEPTANCE_LETTER", (1, 1), 1.0, condition="claim_response == 'accepted'", date_anchor="claim_filed", date_offset_days=(14, 45)),
        NodeDocumentRule("CLAIM_DENIAL_LETTER", (1, 1), 1.0, condition="claim_response == 'denied'", date_anchor="claim_filed", date_offset_days=(30, 90)),
        NodeDocumentRule("CLAIM_DELAY_NOTICE", (1, 1), 1.0, condition="claim_response == 'delayed'", date_anchor="claim_filed", date_offset_days=(14, 90)),
        NodeDocumentRule("ADJUSTER_LETTER_INFORMATIONAL", (1, 2), 1.0, date_anchor="claim_filed", date_offset_days=(7, 60)),
    ],

    "investigation": [
        NodeDocumentRule("ADJUSTER_LETTER_REQUEST", (1, 2), 1.0, date_anchor="claim_filed", date_offset_days=(30, 90)),
        NodeDocumentRule("SUBPOENAED_RECORDS_MEDICAL", (0, 1), 0.5, date_anchor="claim_filed", date_offset_days=(30, 90)),
        NodeDocumentRule("SUBPOENAED_RECORDS_EMPLOYMENT", (0, 1), 0.4, date_anchor="claim_filed", date_offset_days=(30, 90)),
        NodeDocumentRule("INVESTIGATOR_REPORT", (0, 1), 0.15, date_anchor="claim_filed", date_offset_days=(45, 120)),
    ],

    "appeal": [
        NodeDocumentRule("PETITION_RECONSIDERATION_FILED", (0, 1), 0.3, date_anchor="claim_filed", date_offset_days=(60, 120)),
    ],

    # --- ACTIVE TREATMENT ---
    "active_treatment": [
        NodeDocumentRule("TREATING_PHYSICIAN_REPORT_PR2", (1, 2), 1.0, date_anchor="doi", date_offset_days=(7, 30)),
        NodeDocumentRule("TREATING_PHYSICIAN_REPORT_PR4", (2, 5), 1.0, date_anchor="doi", date_offset_days=(30, 365)),
        NodeDocumentRule("DIAGNOSTICS_IMAGING", (1, 3), 1.0, date_anchor="doi", date_offset_days=(3, 180)),
        NodeDocumentRule("DIAGNOSTICS_LAB_RESULTS", (0, 1), 0.3, date_anchor="doi", date_offset_days=(7, 90)),
        NodeDocumentRule("PHARMACY_RECORDS", (1, 2), 0.9, date_anchor="doi", date_offset_days=(7, 180)),
        NodeDocumentRule("BILLING_CMS_1500", (2, 4), 1.0, date_anchor="doi", date_offset_days=(14, 365)),
        NodeDocumentRule("BILLING_UB04", (0, 1), 0.3, condition="has_surgery", date_anchor="doi", date_offset_days=(30, 180)),
        NodeDocumentRule("ORTHOPEDIC_RECORDS", (1, 3), 0.6, date_anchor="doi", date_offset_days=(14, 270)),
        NodeDocumentRule("PHYSICAL_THERAPY_RECORDS", (1, 2), 0.5, date_anchor="doi", date_offset_days=(30, 270)),
        NodeDocumentRule("PAIN_MANAGEMENT_RECORDS", (0, 2), 0.35, date_anchor="doi", date_offset_days=(60, 365)),
        NodeDocumentRule("CHIROPRACTIC_RECORDS", (0, 2), 0.25, date_anchor="doi", date_offset_days=(14, 180)),
        NodeDocumentRule("PSYCHIATRIC_TREATMENT_RECORDS", (0, 2), 0.8, condition="has_psych_component", date_anchor="doi", date_offset_days=(30, 365)),
        NodeDocumentRule("OPERATIVE_HOSPITAL_RECORDS", (1, 1), 1.0, condition="has_surgery", date_anchor="doi", date_offset_days=(30, 180)),
        NodeDocumentRule("DISCHARGE_SUMMARY", (1, 1), 0.9, condition="has_surgery", date_anchor="doi", date_offset_days=(31, 185)),
        NodeDocumentRule("ACUTE_CARE_HOSPITAL_RECORDS", (0, 1), 0.4, condition="has_surgery", date_anchor="doi", date_offset_days=(30, 180)),
        NodeDocumentRule("ONGOING_TREATMENT_RECORDS", (1, 3), 0.6, date_anchor="doi", date_offset_days=(60, 365)),
        NodeDocumentRule("MEDICAL_TREATMENT_AUTHORIZATION_RFA", (1, 3), 0.7, date_anchor="doi", date_offset_days=(14, 180)),
        NodeDocumentRule("ADJUSTER_LETTER_INFORMATIONAL", (1, 2), 1.0, date_anchor="doi", date_offset_days=(30, 180)),
        NodeDocumentRule("DEFENSE_COUNSEL_LETTER_INFORMATIONAL", (0, 1), 0.5, date_anchor="doi", date_offset_days=(60, 270)),
        NodeDocumentRule("WORK_RESTRICTIONS_POST_INJURY", (1, 2), 0.8, date_anchor="doi", date_offset_days=(7, 180)),
        NodeDocumentRule("TD_PAYMENT_RECORD_ONGOING", (1, 2), 0.7, date_anchor="doi", date_offset_days=(14, 180)),
        NodeDocumentRule("CLIENT_STATUS_LETTERS", (0, 1), 0.4, date_anchor="doi", date_offset_days=(30, 180)),
    ],

    # --- UR DISPUTE BRANCH ---
    "ur_dispute": [
        NodeDocumentRule("UTILIZATION_REVIEW_DECISION_REGULAR", (1, 2), 1.0, date_anchor="doi", date_offset_days=(60, 270)),
        NodeDocumentRule("UTILIZATION_REVIEW_DECISION_EXPEDITED", (0, 1), 0.2, date_anchor="doi", date_offset_days=(30, 120)),
        NodeDocumentRule("MEDICAL_TREATMENT_DENIAL_UR", (1, 1), 0.7, date_anchor="doi", date_offset_days=(60, 270)),
    ],

    "ur_decision": [
        NodeDocumentRule("MEDICAL_TREATMENT_AUTHORIZATION", (1, 1), 1.0, condition="ur_decision == 'approved'", date_anchor="doi", date_offset_days=(90, 300)),
    ],

    "imr_appeal": [
        NodeDocumentRule("IMR_APPLICATION_FORM", (1, 1), 1.0, date_anchor="doi", date_offset_days=(90, 300)),
        NodeDocumentRule("INDEPENDENT_MEDICAL_REVIEW_DECISION", (1, 1), 1.0, date_anchor="doi", date_offset_days=(150, 365)),
    ],

    # --- APPLICATION FILED ---
    "application_filed": [
        NodeDocumentRule("APPLICATION_FOR_ADJUDICATION_ORIGINAL", (1, 1), 1.0, date_anchor="doi", date_offset_days=(60, 180)),
        NodeDocumentRule("NOTICE_OF_HEARING_COURT_ISSUED", (0, 1), 0.6, date_anchor="application_filed", date_offset_days=(30, 90)),
        NodeDocumentRule("DEFENSE_COUNSEL_LETTER_INFORMATIONAL", (1, 2), 1.0, date_anchor="application_filed", date_offset_days=(14, 60)),
        NodeDocumentRule("COURT_DISTRICT_NOTICE", (0, 1), 0.4, date_anchor="application_filed", date_offset_days=(14, 45)),
    ],

    # --- MEDICAL-LEGAL EVALUATION ---
    "qme_evaluation": [
        NodeDocumentRule("QME_PANEL_REQUEST_FORM_105", (1, 1), 0.6, date_anchor="doi", date_offset_days=(180, 365)),
        NodeDocumentRule("ORDER_APPOINTING_QME_PANEL", (1, 1), 0.8, date_anchor="doi", date_offset_days=(200, 400)),
        NodeDocumentRule("QME_REPORT_INITIAL", (1, 1), 1.0, date_anchor="doi", date_offset_days=(270, 545)),
        NodeDocumentRule("QME_REPORT_SUPPLEMENTAL", (0, 1), 0.3, date_anchor="doi", date_offset_days=(365, 630)),
        NodeDocumentRule("APPORTIONMENT_REPORT", (0, 1), 0.4, date_anchor="doi", date_offset_days=(300, 600)),
        NodeDocumentRule("ADVOCACY_LETTERS_QME", (0, 1), 0.5, date_anchor="doi", date_offset_days=(200, 400)),
        NodeDocumentRule("PSYCH_EVAL_REPORT_QME_AME", (0, 1), 0.8, condition="has_psych_component", date_anchor="doi", date_offset_days=(270, 545)),
    ],

    "ame_evaluation": [
        NodeDocumentRule("AME_REPORT", (1, 1), 1.0, date_anchor="doi", date_offset_days=(270, 545)),
        NodeDocumentRule("APPORTIONMENT_REPORT", (0, 1), 0.5, date_anchor="doi", date_offset_days=(300, 600)),
        NodeDocumentRule("ADVOCACY_LETTERS_AME", (0, 1), 0.5, date_anchor="doi", date_offset_days=(200, 400)),
        NodeDocumentRule("PSYCH_EVAL_REPORT_QME_AME", (0, 1), 0.8, condition="has_psych_component", date_anchor="doi", date_offset_days=(270, 545)),
    ],

    # --- DISCOVERY ---
    "discovery": [
        NodeDocumentRule("SUBPOENA_SDT_ISSUED", (1, 3), 1.0, date_anchor="doi", date_offset_days=(180, 545)),
        NodeDocumentRule("SUBPOENA_SDT_RECEIVED", (0, 1), 0.3, date_anchor="doi", date_offset_days=(200, 545)),
        NodeDocumentRule("SUBPOENAED_RECORDS_MEDICAL", (2, 5), 0.9, date_anchor="doi", date_offset_days=(210, 600)),
        NodeDocumentRule("SUBPOENAED_RECORDS_EMPLOYMENT", (0, 1), 0.5, date_anchor="doi", date_offset_days=(210, 600)),
        NodeDocumentRule("SUBPOENAED_RECORDS_OTHER", (0, 1), 0.35, date_anchor="doi", date_offset_days=(240, 630)),
        NodeDocumentRule("DEPOSITION_NOTICE_APPLICANT", (1, 1), 0.8, date_anchor="doi", date_offset_days=(270, 600)),
        NodeDocumentRule("DEPOSITION_NOTICE_DEFENDANT", (0, 1), 0.4, date_anchor="doi", date_offset_days=(270, 600)),
        NodeDocumentRule("DEPOSITION_NOTICE_MEDICAL_WITNESS", (0, 1), 0.3, date_anchor="doi", date_offset_days=(300, 630)),
        NodeDocumentRule("DEPOSITION_TRANSCRIPT", (1, 2), 0.8, date_anchor="doi", date_offset_days=(300, 660)),
        NodeDocumentRule("DEPOSITION_SUMMARY", (0, 1), 0.3, date_anchor="doi", date_offset_days=(330, 690)),
        NodeDocumentRule("MEDICAL_CHRONOLOGY_TIMELINE", (0, 1), 0.6, date_anchor="doi", date_offset_days=(300, 660)),
        NodeDocumentRule("DECLARATION_OF_READINESS_REGULAR", (0, 1), 0.5, date_anchor="doi", date_offset_days=(365, 730)),
        NodeDocumentRule("NOTICE_OF_HEARING_COURT_ISSUED", (0, 1), 0.4, date_anchor="doi", date_offset_days=(365, 730)),
        NodeDocumentRule("DEFENSE_COUNSEL_LETTER_DEMAND", (0, 1), 0.4, date_anchor="doi", date_offset_days=(270, 545)),
        NodeDocumentRule("ADJUSTER_LETTER_REQUEST", (1, 2), 0.8, date_anchor="doi", date_offset_days=(180, 545)),
        NodeDocumentRule("PERSONNEL_FILES", (0, 1), 0.4, date_anchor="doi", date_offset_days=(210, 400)),
    ],

    # --- LIEN BRANCH ---
    "lien_filing": [
        NodeDocumentRule("LIEN_MEDICAL_PROVIDER", (1, 2), 0.7, date_anchor="doi", date_offset_days=(365, 730)),
        NodeDocumentRule("LIEN_HOSPITAL", (0, 1), 0.3, condition="has_surgery", date_anchor="doi", date_offset_days=(365, 730)),
        NodeDocumentRule("LIEN_PHARMACY", (0, 1), 0.2, date_anchor="doi", date_offset_days=(365, 730)),
        NodeDocumentRule("LIEN_ATTORNEY_COSTS", (0, 1), 0.15, date_anchor="doi", date_offset_days=(365, 730)),
        NodeDocumentRule("NOTICE_OF_LIEN_FILING", (1, 1), 1.0, date_anchor="doi", date_offset_days=(365, 730)),
        NodeDocumentRule("NOTICE_OF_INTENT_TO_FILE_LIEN", (0, 1), 0.4, date_anchor="doi", date_offset_days=(300, 660)),
    ],

    "lien_conference": [
        NodeDocumentRule("NOTICE_OF_LIEN_CONFERENCE", (1, 1), 1.0, date_anchor="doi", date_offset_days=(500, 900)),
        NodeDocumentRule("ORDER_ON_LIEN", (0, 1), 0.5, date_anchor="doi", date_offset_days=(550, 950)),
        NodeDocumentRule("LIEN_RESOLUTION", (0, 1), 0.6, date_anchor="doi", date_offset_days=(550, 1000)),
        NodeDocumentRule("LIEN_DISMISSAL", (0, 1), 0.3, date_anchor="doi", date_offset_days=(550, 1000)),
    ],

    # --- RESOLUTION ---
    "resolution_stipulations": [
        NodeDocumentRule("SETTLEMENT_DEMAND_LETTER", (1, 1), 0.8, date_anchor="doi", date_offset_days=(500, 900)),
        NodeDocumentRule("SETTLEMENT_CONFERENCE_STATEMENT", (0, 1), 0.5, date_anchor="doi", date_offset_days=(550, 950)),
        NodeDocumentRule("NOTICE_OF_MSC", (1, 1), 0.9, date_anchor="doi", date_offset_days=(500, 900)),
        NodeDocumentRule("ORDER_ON_MSC", (0, 1), 0.5, date_anchor="doi", date_offset_days=(550, 950)),
        NodeDocumentRule("DECLARATION_OF_READINESS_REGULAR", (1, 1), 1.0, date_anchor="doi", date_offset_days=(500, 730)),
        NodeDocumentRule("STIPULATIONS_WITH_REQUEST_FOR_AWARD", (1, 1), 1.0, date_anchor="doi", date_offset_days=(600, 1000)),
        NodeDocumentRule("SETTLEMENT_VALUATION_MEMO", (1, 1), 1.0, date_anchor="doi", date_offset_days=(550, 950)),
        NodeDocumentRule("PD_RATING_CALCULATION_WORKSHEET", (0, 1), 0.7, date_anchor="doi", date_offset_days=(500, 900)),
        NodeDocumentRule("DEU_RATING_REQUEST_FORM", (0, 1), 0.4, date_anchor="doi", date_offset_days=(400, 800)),
        NodeDocumentRule("MEDICAL_CHRONOLOGY_TIMELINE", (1, 1), 0.8, date_anchor="doi", date_offset_days=(500, 900)),
        NodeDocumentRule("QME_AME_SUMMARY_WITH_ISSUE_LIST", (0, 1), 0.5, date_anchor="doi", date_offset_days=(400, 800)),
        NodeDocumentRule("SJDB_VOUCHER_6000", (0, 1), 0.2, date_anchor="doi", date_offset_days=(600, 1000)),
    ],

    "resolution_cr": [
        NodeDocumentRule("SETTLEMENT_DEMAND_LETTER", (1, 1), 0.8, date_anchor="doi", date_offset_days=(500, 900)),
        NodeDocumentRule("NOTICE_OF_MSC", (1, 1), 0.9, date_anchor="doi", date_offset_days=(500, 900)),
        NodeDocumentRule("COMPROMISE_AND_RELEASE_STANDARD", (1, 1), 1.0, date_anchor="doi", date_offset_days=(600, 1000)),
        NodeDocumentRule("COMPROMISE_AND_RELEASE_MSA", (0, 1), 0.15, date_anchor="doi", date_offset_days=(600, 1000)),
        NodeDocumentRule("SETTLEMENT_VALUATION_MEMO", (1, 1), 1.0, date_anchor="doi", date_offset_days=(550, 950)),
        NodeDocumentRule("PD_RATING_CALCULATION_WORKSHEET", (0, 1), 0.6, date_anchor="doi", date_offset_days=(500, 900)),
        NodeDocumentRule("DECLARATION_OF_READINESS_REGULAR", (1, 1), 1.0, date_anchor="doi", date_offset_days=(500, 730)),
        NodeDocumentRule("MEDICAL_CHRONOLOGY_TIMELINE", (1, 1), 0.8, date_anchor="doi", date_offset_days=(500, 900)),
        NodeDocumentRule("QME_AME_SUMMARY_WITH_ISSUE_LIST", (0, 1), 0.5, date_anchor="doi", date_offset_days=(400, 800)),
    ],

    "resolution_trial": [
        NodeDocumentRule("TRIAL_BRIEF", (1, 1), 1.0, date_anchor="doi", date_offset_days=(600, 1000)),
        NodeDocumentRule("PRETRIAL_CONFERENCE_STATEMENT", (1, 1), 1.0, date_anchor="doi", date_offset_days=(550, 950)),
        NodeDocumentRule("NOTICE_OF_TRIAL", (1, 1), 1.0, date_anchor="doi", date_offset_days=(550, 900)),
        NodeDocumentRule("DECLARATION_OF_READINESS_REGULAR", (1, 1), 1.0, date_anchor="doi", date_offset_days=(500, 730)),
        NodeDocumentRule("SETTLEMENT_VALUATION_MEMO", (1, 1), 0.8, date_anchor="doi", date_offset_days=(550, 950)),
        NodeDocumentRule("MEDICAL_CHRONOLOGY_TIMELINE", (1, 1), 1.0, date_anchor="doi", date_offset_days=(500, 900)),
        NodeDocumentRule("NOTICE_OF_HEARING_COURT_ISSUED", (1, 2), 1.0, date_anchor="doi", date_offset_days=(550, 950)),
        NodeDocumentRule("MINUTES_ORDERS_FINDINGS_AWARD", (1, 2), 1.0, date_anchor="doi", date_offset_days=(700, 1095)),
    ],

    # --- POST-RESOLUTION ---
    "post_resolution": [
        NodeDocumentRule("MINUTES_ORDERS_FINDINGS_AWARD", (1, 2), 0.8, date_anchor="doi", date_offset_days=(700, 1095)),
        NodeDocumentRule("ORDER_FINAL", (0, 1), 0.5, date_anchor="doi", date_offset_days=(730, 1095)),
        NodeDocumentRule("PD_PAYMENT_RECORD_FINAL", (0, 1), 0.6, date_anchor="doi", date_offset_days=(730, 1095)),
        NodeDocumentRule("PD_PAYMENT_RECORD_ADVANCE", (0, 1), 0.3, date_anchor="doi", date_offset_days=(500, 900)),
        NodeDocumentRule("EXPENSE_REIMBURSEMENT", (0, 1), 0.2, date_anchor="doi", date_offset_days=(730, 1095)),
        NodeDocumentRule("PETITION_REOPENING", (0, 1), 0.10, date_anchor="doi", date_offset_days=(900, 1460)),
        NodeDocumentRule("CASE_ANALYSIS_MEMO", (0, 1), 0.3, date_anchor="doi", date_offset_days=(700, 1095)),
    ],
}


# ---------------------------------------------------------------------------
# Lifecycle walk — determine which nodes a case passes through
# ---------------------------------------------------------------------------

# Ordered list of all lifecycle stages. The walk proceeds sequentially,
# with branching controlled by CaseParameters.
LIFECYCLE_ORDER: list[LifecycleStage] = [
    LifecycleStage.INJURY,
    LifecycleStage.CLAIM_FILED,
    LifecycleStage.CLAIM_RESPONSE,
    LifecycleStage.INVESTIGATION,
    LifecycleStage.APPEAL,
    LifecycleStage.ACTIVE_TREATMENT,
    LifecycleStage.UR_DISPUTE,
    LifecycleStage.UR_DECISION,
    LifecycleStage.IMR_APPEAL,
    LifecycleStage.APPLICATION_FILED,
    LifecycleStage.QME_EVALUATION,
    LifecycleStage.AME_EVALUATION,
    LifecycleStage.DISCOVERY,
    LifecycleStage.LIEN_FILING,
    LifecycleStage.LIEN_CONFERENCE,
    LifecycleStage.RESOLUTION_STIPULATIONS,
    LifecycleStage.RESOLUTION_CR,
    LifecycleStage.RESOLUTION_TRIAL,
    LifecycleStage.POST_RESOLUTION,
]


def walk_lifecycle(params: CaseParameters) -> list[LifecycleStage]:
    """Determine which lifecycle nodes a case passes through based on its parameters.

    Returns an ordered list of nodes the case visits.
    """
    target = LITIGATION_STAGE_TO_TARGET.get(params.target_stage, LifecycleStage.POST_RESOLUTION)
    target_idx = LIFECYCLE_ORDER.index(target)

    visited: list[LifecycleStage] = []

    for stage in LIFECYCLE_ORDER:
        stage_idx = LIFECYCLE_ORDER.index(stage)
        if stage_idx > target_idx:
            break

        # Branching logic — skip nodes that don't apply
        if stage == LifecycleStage.INVESTIGATION:
            if params.claim_response != "delayed":
                continue
        elif stage == LifecycleStage.APPEAL:
            if params.claim_response != "denied":
                continue
        elif stage == LifecycleStage.UR_DISPUTE:
            if not params.has_ur_dispute:
                continue
        elif stage == LifecycleStage.UR_DECISION:
            if not params.has_ur_dispute:
                continue
        elif stage == LifecycleStage.IMR_APPEAL:
            if not (params.has_ur_dispute and params.ur_decision == "denied" and params.imr_filed):
                continue
        elif stage == LifecycleStage.APPLICATION_FILED:
            if not params.has_attorney:
                continue
        elif stage == LifecycleStage.QME_EVALUATION:
            if params.eval_type != "qme":
                continue
        elif stage == LifecycleStage.AME_EVALUATION:
            if params.eval_type != "ame":
                continue
        elif stage == LifecycleStage.LIEN_FILING:
            if not params.has_liens:
                continue
        elif stage == LifecycleStage.LIEN_CONFERENCE:
            if not params.has_liens:
                continue
        elif stage == LifecycleStage.RESOLUTION_STIPULATIONS:
            if params.resolution_type != "stipulations":
                continue
        elif stage == LifecycleStage.RESOLUTION_CR:
            if params.resolution_type != "c_and_r":
                continue
        elif stage == LifecycleStage.RESOLUTION_TRIAL:
            if params.resolution_type != "trial":
                continue

        visited.append(stage)

    return visited


def evaluate_condition(condition: str | None, params: CaseParameters) -> bool:
    """Evaluate a document rule condition against case parameters."""
    if condition is None:
        return True

    # Simple condition evaluator — avoids eval()
    condition = condition.strip()

    if condition == "has_surgery":
        return params.has_surgery
    elif condition == "has_psych_component":
        return params.has_psych_component
    elif condition == "has_liens":
        return params.has_liens
    elif condition == "has_attorney":
        return params.has_attorney
    elif condition == "has_ur_dispute":
        return params.has_ur_dispute
    elif condition.startswith("claim_response"):
        _, _, val = condition.partition("==")
        return params.claim_response == val.strip().strip("'\"")
    elif condition.startswith("eval_type"):
        _, _, val = condition.partition("==")
        return params.eval_type == val.strip().strip("'\"")
    elif condition.startswith("resolution_type"):
        _, _, val = condition.partition("==")
        return params.resolution_type == val.strip().strip("'\"")
    elif condition.startswith("ur_decision"):
        _, _, val = condition.partition("==")
        return params.ur_decision == val.strip().strip("'\"")
    elif condition.startswith("imr_outcome"):
        _, _, val = condition.partition("==")
        return params.imr_outcome == val.strip().strip("'\"")

    # Unknown condition — default to True for forward compat
    return True


def collect_documents_for_case(
    params: CaseParameters,
    rng: random.Random,
) -> list[tuple[str, NodeDocumentRule]]:
    """Walk the lifecycle and collect all document rules that fire.

    Returns list of (subtype_str, rule) tuples for documents to generate.
    """
    stages = walk_lifecycle(params)
    documents: list[tuple[str, NodeDocumentRule]] = []
    is_complex = params.complexity == "complex"

    for stage in stages:
        rules = LIFECYCLE_DOCUMENT_RULES.get(stage.value, [])
        for rule in rules:
            # Check condition
            if not evaluate_condition(rule.condition, params):
                continue

            # For complex cases: boost probability so more optional docs appear
            effective_prob = rule.probability
            if is_complex and effective_prob < 1.0:
                effective_prob = min(1.0, effective_prob * 2.5)

            # Check probability
            if effective_prob < 1.0 and rng.random() > effective_prob:
                continue

            # Determine count — complex cases get 3-5x documents
            if is_complex:
                scaled_min = rule.count[0] * 3
                scaled_max = rule.count[1] * 5
                count = rng.randint(max(scaled_min, 1), max(scaled_max, scaled_min + 1))
            else:
                count = rng.randint(rule.count[0], rule.count[1])

            for _ in range(count):
                documents.append((rule.subtype, rule))

    return documents
