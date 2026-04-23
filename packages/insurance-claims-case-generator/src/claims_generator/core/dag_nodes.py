"""
DAG node definitions — ClaimStageNode and DocumentEmission.

Each node in the lifecycle DAG defines which documents it emits
(type, subtype slug, probability, access level) and duration bounds.

15 claim lifecycle stages covering the full CA Workers' Compensation
claim lifecycle from DWC-1 filing through closure.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

from dataclasses import dataclass, field

from claims_generator.models.enums import DocumentType


@dataclass
class DocumentEmission:
    """A document that may be emitted at a lifecycle stage."""

    document_type: DocumentType
    subtype_slug: str
    title_template: str
    probability: float  # 0.0–1.0
    access_level: str = "EXAMINER_ONLY"  # EXAMINER_ONLY / DUAL_ACCESS / ATTORNEY_ONLY
    deadline_statute: str | None = None  # e.g. "LC 4650"
    deadline_days: int | None = None  # days from stage anchor date


@dataclass
class ClaimStageNode:
    """A node in the lifecycle DAG."""

    stage_id: str
    display_name: str
    emissions: list[DocumentEmission] = field(default_factory=list)
    # Duration bounds in calendar days from previous stage anchor
    duration_min_days: int = 1
    duration_max_days: int = 30


# ── Stage definitions ──────────────────────────────────────────────────────────

DWC1_FILED = ClaimStageNode(
    stage_id="DWC1_FILED",
    display_name="DWC-1 Claim Form Filed",
    duration_min_days=0,
    duration_max_days=0,
    emissions=[
        DocumentEmission(
            document_type=DocumentType.DWC1_CLAIM_FORM,
            subtype_slug="dwc1_claim_form",
            title_template="DWC-1 Workers' Compensation Claim Form",
            probability=1.0,
        ),
        DocumentEmission(
            document_type=DocumentType.EMPLOYER_REPORT,
            subtype_slug="employer_report_of_injury",
            title_template="Employer's Report of Occupational Injury or Illness",
            probability=0.85,
        ),
    ],
)

INITIAL_CONTACT = ClaimStageNode(
    stage_id="INITIAL_CONTACT",
    display_name="Initial Contact",
    duration_min_days=1,
    duration_max_days=15,
    emissions=[
        DocumentEmission(
            document_type=DocumentType.BENEFIT_NOTICE,
            subtype_slug="benefit_notice_delay",
            title_template="Notice of Delay in Claims Decision",
            probability=0.40,
            deadline_statute="10 CCR 2695.5(b)",
            deadline_days=15,
        ),
        DocumentEmission(
            document_type=DocumentType.CORRESPONDENCE,
            subtype_slug="adjuster_initial_contact",
            title_template="Initial Claims Contact Letter",
            probability=0.60,
        ),
        DocumentEmission(
            document_type=DocumentType.CLAIM_ADMINISTRATION,
            subtype_slug="claim_setup_record",
            title_template="Claim Setup and Assignment Record",
            probability=0.90,
        ),
    ],
)

CLAIM_ACCEPTED = ClaimStageNode(
    stage_id="CLAIM_ACCEPTED",
    display_name="Claim Accepted",
    duration_min_days=1,
    duration_max_days=40,
    emissions=[
        DocumentEmission(
            document_type=DocumentType.BENEFIT_NOTICE,
            subtype_slug="benefit_notice_acceptance",
            title_template="Notice of Acceptance of Workers' Compensation Claim",
            probability=1.0,
            deadline_statute="10 CCR 2695.7(b)",
            deadline_days=40,
        ),
    ],
)

CLAIM_DENIED = ClaimStageNode(
    stage_id="CLAIM_DENIED",
    display_name="Claim Denied",
    duration_min_days=1,
    duration_max_days=90,
    emissions=[
        DocumentEmission(
            document_type=DocumentType.BENEFIT_NOTICE,
            subtype_slug="benefit_notice_denial",
            title_template="Notice of Denial of Workers' Compensation Claim",
            probability=1.0,
            deadline_statute="10 CCR 2695.7(b)",
            deadline_days=90,
        ),
        DocumentEmission(
            document_type=DocumentType.INVESTIGATION_REPORT,
            subtype_slug="investigation_report_denial_basis",
            title_template="Claims Investigation Report — Denial Basis",
            probability=0.75,
        ),
        DocumentEmission(
            document_type=DocumentType.CORRESPONDENCE,
            subtype_slug="denial_explanation_letter",
            title_template="Denial Explanation Letter to Claimant",
            probability=0.80,
        ),
    ],
)

TREATMENT_BEGINS = ClaimStageNode(
    stage_id="TREATMENT_BEGINS",
    display_name="Medical Treatment Begins",
    duration_min_days=1,
    duration_max_days=14,
    emissions=[
        DocumentEmission(
            document_type=DocumentType.MEDICAL_REPORT,
            subtype_slug="medical_report_pr2",
            title_template="Primary Treating Physician Report (PR-2)",
            probability=0.80,
        ),
        DocumentEmission(
            document_type=DocumentType.BILLING_STATEMENT,
            subtype_slug="billing_statement_medical",
            title_template="Medical Services Billing Statement",
            probability=0.90,
        ),
        DocumentEmission(
            document_type=DocumentType.IMAGING_REPORT,
            subtype_slug="imaging_report_xray",
            title_template="Diagnostic Imaging Report",
            probability=0.55,
        ),
    ],
)

TD_PAYMENTS = ClaimStageNode(
    stage_id="TD_PAYMENTS",
    display_name="Temporary Disability Payments",
    duration_min_days=1,
    duration_max_days=14,
    emissions=[
        DocumentEmission(
            document_type=DocumentType.PAYMENT_RECORD,
            subtype_slug="payment_record_td_first",
            title_template="First Temporary Disability Payment Record",
            probability=1.0,
            deadline_statute="LC 4650",
            deadline_days=14,
        ),
        DocumentEmission(
            document_type=DocumentType.BENEFIT_NOTICE,
            subtype_slug="benefit_notice_td_rate",
            title_template="Notice of Temporary Disability Rate",
            probability=1.0,
        ),
        DocumentEmission(
            document_type=DocumentType.WAGE_STATEMENT,
            subtype_slug="wage_statement_employer",
            title_template="Employer Wage Verification Statement",
            probability=0.75,
        ),
    ],
)

UR_RFA_CYCLE = ClaimStageNode(
    stage_id="UR_RFA_CYCLE",
    display_name="Utilization Review / RFA Cycle",
    duration_min_days=5,
    duration_max_days=30,
    emissions=[
        DocumentEmission(
            document_type=DocumentType.UTILIZATION_REVIEW,
            subtype_slug="utilization_review_rfa",
            title_template="Request for Authorization (RFA)",
            probability=1.0,
        ),
        DocumentEmission(
            document_type=DocumentType.UTILIZATION_REVIEW,
            subtype_slug="utilization_review_decision",
            title_template="Utilization Review Decision",
            probability=1.0,
        ),
        DocumentEmission(
            document_type=DocumentType.MEDICAL_REPORT,
            subtype_slug="medical_report_treating_progress",
            title_template="Treating Physician Progress Report",
            probability=0.70,
        ),
    ],
)

QME_DISPUTE = ClaimStageNode(
    stage_id="QME_DISPUTE",
    display_name="QME Panel Request / Dispute",
    duration_min_days=10,
    duration_max_days=45,
    emissions=[
        DocumentEmission(
            document_type=DocumentType.DWC_OFFICIAL_FORM,
            subtype_slug="dwc_form_105_qme_panel",
            title_template="DWC Form 105 — QME Panel Request",
            probability=1.0,
        ),
        DocumentEmission(
            document_type=DocumentType.LEGAL_CORRESPONDENCE,
            subtype_slug="legal_correspondence_qme_objection",
            title_template="QME Panel Objection Letter",
            probability=0.80,
            access_level="DUAL_ACCESS",
        ),
        DocumentEmission(
            document_type=DocumentType.WCAB_FILING,
            subtype_slug="wcab_filing_application",
            title_template="Application for Adjudication of Claim",
            probability=0.70,
            access_level="DUAL_ACCESS",
        ),
    ],
)

QME_EXAM = ClaimStageNode(
    stage_id="QME_EXAM",
    display_name="QME Examination",
    duration_min_days=30,
    duration_max_days=90,
    emissions=[
        DocumentEmission(
            document_type=DocumentType.AME_QME_REPORT,
            subtype_slug="qme_report_initial",
            title_template="Qualified Medical Evaluator Report",
            probability=1.0,
        ),
        DocumentEmission(
            document_type=DocumentType.AME_QME_REPORT,
            subtype_slug="qme_report_psychiatric",
            title_template="Psychiatric QME Evaluation Report",
            probability=0.40,  # boosted by psych_overlay in engine
        ),
        DocumentEmission(
            document_type=DocumentType.LEGAL_CORRESPONDENCE,
            subtype_slug="qme_objection_letter",
            title_template="QME Report Objection",
            probability=0.35,
            access_level="DUAL_ACCESS",
        ),
    ],
)

MMI_REACHED = ClaimStageNode(
    stage_id="MMI_REACHED",
    display_name="Maximum Medical Improvement Reached",
    duration_min_days=60,
    duration_max_days=365,
    emissions=[
        DocumentEmission(
            document_type=DocumentType.MEDICAL_REPORT,
            subtype_slug="medical_report_ps",
            title_template="Permanent and Stationary Report (P&S)",
            probability=1.0,
        ),
        DocumentEmission(
            document_type=DocumentType.IMAGING_REPORT,
            subtype_slug="imaging_report_mri",
            title_template="MRI / Diagnostic Imaging Report at MMI",
            probability=0.70,
        ),
    ],
)

PD_RATING = ClaimStageNode(
    stage_id="PD_RATING",
    display_name="Permanent Disability Rating",
    duration_min_days=30,
    duration_max_days=120,
    emissions=[
        DocumentEmission(
            document_type=DocumentType.DWC_OFFICIAL_FORM,
            subtype_slug="dwc_form_deu_rating",
            title_template="DEU Formal Rating — Permanent Disability",
            probability=0.85,
        ),
        DocumentEmission(
            document_type=DocumentType.PAYMENT_RECORD,
            subtype_slug="payment_record_pd_worksheet",
            title_template="Permanent Disability Benefit Calculation Worksheet",
            probability=0.80,
        ),
        DocumentEmission(
            document_type=DocumentType.RETURN_TO_WORK,
            subtype_slug="return_to_work_sjdb_offer",
            title_template="Supplemental Job Displacement Benefit Offer",
            probability=0.45,
        ),
    ],
)

SETTLEMENT_CR = ClaimStageNode(
    stage_id="SETTLEMENT_CR",
    display_name="Compromise and Release Settlement",
    duration_min_days=30,
    duration_max_days=180,
    emissions=[
        DocumentEmission(
            document_type=DocumentType.SETTLEMENT_DOCUMENT,
            subtype_slug="settlement_compromise_release",
            title_template="Compromise and Release Agreement",
            probability=1.0,
            access_level="DUAL_ACCESS",
        ),
        DocumentEmission(
            document_type=DocumentType.MEDICAL_CHRONOLOGY,
            subtype_slug="medical_chronology_settlement",
            title_template="Medical Chronology for Settlement",
            probability=0.65,
        ),
    ],
)

SETTLEMENT_STIPS = ClaimStageNode(
    stage_id="SETTLEMENT_STIPS",
    display_name="Stipulations with Request for Award",
    duration_min_days=30,
    duration_max_days=180,
    emissions=[
        DocumentEmission(
            document_type=DocumentType.SETTLEMENT_DOCUMENT,
            subtype_slug="settlement_stipulations",
            title_template="Stipulations with Request for Award",
            probability=1.0,
            access_level="DUAL_ACCESS",
        ),
    ],
)

WCAB_HEARING = ClaimStageNode(
    stage_id="WCAB_HEARING",
    display_name="WCAB Hearing / Trial",
    duration_min_days=60,
    duration_max_days=360,
    emissions=[
        DocumentEmission(
            document_type=DocumentType.WCAB_FILING,
            subtype_slug="wcab_filing_dor",
            title_template="Declaration of Readiness to Proceed",
            probability=1.0,
            access_level="DUAL_ACCESS",
        ),
        DocumentEmission(
            document_type=DocumentType.DEPOSITION_TRANSCRIPT,
            subtype_slug="deposition_transcript_applicant",
            title_template="Deposition Transcript — Applicant",
            probability=0.70,
            access_level="DUAL_ACCESS",
        ),
        DocumentEmission(
            document_type=DocumentType.DISCOVERY_REQUEST,
            subtype_slug="discovery_request_subpoena",
            title_template="Subpoena Duces Tecum — Medical Records",
            probability=0.60,
            access_level="DUAL_ACCESS",
        ),
        DocumentEmission(
            document_type=DocumentType.LIEN_CLAIM,
            subtype_slug="lien_claim_medical_provider",
            title_template="Medical Provider Lien Claim",
            probability=0.30,
        ),
    ],
)

CLOSURE = ClaimStageNode(
    stage_id="CLOSURE",
    display_name="Claim Closure",
    duration_min_days=1,
    duration_max_days=30,
    emissions=[
        DocumentEmission(
            document_type=DocumentType.PAYMENT_RECORD,
            subtype_slug="payment_record_pd_final",
            title_template="Final Permanent Disability Payment Record",
            probability=0.90,
        ),
        DocumentEmission(
            document_type=DocumentType.CLAIM_ADMINISTRATION,
            subtype_slug="claim_closure_notice",
            title_template="Claim Closure Notice",
            probability=1.0,
        ),
    ],
)

# ── Registry ───────────────────────────────────────────────────────────────────

ALL_STAGES: dict[str, ClaimStageNode] = {
    s.stage_id: s
    for s in [
        DWC1_FILED,
        INITIAL_CONTACT,
        CLAIM_ACCEPTED,
        CLAIM_DENIED,
        TREATMENT_BEGINS,
        TD_PAYMENTS,
        UR_RFA_CYCLE,
        QME_DISPUTE,
        QME_EXAM,
        MMI_REACHED,
        PD_RATING,
        SETTLEMENT_CR,
        SETTLEMENT_STIPS,
        WCAB_HEARING,
        CLOSURE,
    ]
}
