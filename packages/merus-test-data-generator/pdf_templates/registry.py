"""
Centralized template registry — maps DocumentSubtype → (template_class, module_path, variant).

Tier 1: Dedicated build_story() per subtype (existing 25 templates)
Tier 2: Parameterized variants of Tier 1 templates (variant parameter)
Tier 3: GenericDocumentTemplate fallthrough for all remaining subtypes

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Optional


@dataclass
class TemplateEntry:
    """Registry entry mapping a subtype to its template implementation."""
    class_name: str
    module_path: str
    variant: str | None = None


# ---------------------------------------------------------------------------
# Template Registry
# ---------------------------------------------------------------------------
# Subtypes not listed here fall through to GenericDocumentTemplate.

TEMPLATE_REGISTRY: dict[str, TemplateEntry] = {
    # === TIER 1: Dedicated templates (25 existing) ===

    # Medical — Treating Physician Reports (variant-aware)
    "TREATING_PHYSICIAN_REPORT_PR2": TemplateEntry("TreatingPhysicianReport", "pdf_templates.medical.treating_physician_report", "pr2"),
    "TREATING_PHYSICIAN_REPORT_PR4": TemplateEntry("TreatingPhysicianReport", "pdf_templates.medical.treating_physician_report", "pr4"),
    "TREATING_PHYSICIAN_REPORT_FINAL": TemplateEntry("TreatingPhysicianReport", "pdf_templates.medical.treating_physician_report", "final"),
    "TREATING_PHYSICIAN_REPORT": TemplateEntry("TreatingPhysicianReport", "pdf_templates.medical.treating_physician_report"),

    # Medical — Diagnostics
    "DIAGNOSTICS_IMAGING": TemplateEntry("DiagnosticReport", "pdf_templates.medical.diagnostic_report", "imaging"),
    "DIAGNOSTICS_LAB_RESULTS": TemplateEntry("DiagnosticReport", "pdf_templates.medical.diagnostic_report", "lab"),
    "DIAGNOSTICS": TemplateEntry("DiagnosticReport", "pdf_templates.medical.diagnostic_report"),

    # Medical — Surgery/Hospital
    "OPERATIVE_HOSPITAL_RECORDS": TemplateEntry("OperativeRecord", "pdf_templates.medical.operative_record"),
    "ACUTE_CARE_HOSPITAL_RECORDS": TemplateEntry("OperativeRecord", "pdf_templates.medical.operative_record", "acute"),
    "EMERGENCY_ROOM_RECORDS": TemplateEntry("OperativeRecord", "pdf_templates.medical.operative_record", "er"),
    "DISCHARGE_SUMMARY": TemplateEntry("OperativeRecord", "pdf_templates.medical.operative_record", "discharge"),

    # Medical — QME/AME/IME
    "QME_REPORT_INITIAL": TemplateEntry("QmeAmeReport", "pdf_templates.medical.qme_ame_report", "qme_initial"),
    "QME_REPORT_SUPPLEMENTAL": TemplateEntry("QmeAmeReport", "pdf_templates.medical.qme_ame_report", "qme_supplemental"),
    "AME_REPORT": TemplateEntry("QmeAmeReport", "pdf_templates.medical.qme_ame_report", "ame"),
    "IME_REPORT": TemplateEntry("QmeAmeReport", "pdf_templates.medical.qme_ame_report", "ime"),
    "PSYCH_EVAL_REPORT_QME_AME": TemplateEntry("QmeAmeReport", "pdf_templates.medical.qme_ame_report", "psych"),
    "APPORTIONMENT_REPORT": TemplateEntry("QmeAmeReport", "pdf_templates.medical.qme_ame_report", "apportionment"),
    "MEDICAL_LEGAL_QME_AME_IME": TemplateEntry("QmeAmeReport", "pdf_templates.medical.qme_ame_report"),

    # Medical — UR
    "UTILIZATION_REVIEW_DECISION_REGULAR": TemplateEntry("UtilizationReview", "pdf_templates.medical.utilization_review", "regular"),
    "UTILIZATION_REVIEW_DECISION_EXPEDITED": TemplateEntry("UtilizationReview", "pdf_templates.medical.utilization_review", "expedited"),
    "UTILIZATION_REVIEW_DECISION": TemplateEntry("UtilizationReview", "pdf_templates.medical.utilization_review"),
    "INDEPENDENT_MEDICAL_REVIEW_DECISION": TemplateEntry("UtilizationReview", "pdf_templates.medical.utilization_review", "imr"),
    "MEDICAL_TREATMENT_AUTHORIZATION": TemplateEntry("UtilizationReview", "pdf_templates.medical.utilization_review", "authorization"),
    "MEDICAL_TREATMENT_DENIAL_UR": TemplateEntry("UtilizationReview", "pdf_templates.medical.utilization_review", "denial"),

    # Medical — Billing
    "BILLING_UB04": TemplateEntry("BillingRecords", "pdf_templates.medical.billing_records", "ub04"),
    "BILLING_CMS_1500": TemplateEntry("BillingRecords", "pdf_templates.medical.billing_records", "cms1500"),
    "BILLING_SUPERBILLS": TemplateEntry("BillingRecords", "pdf_templates.medical.billing_records", "superbills"),
    "BILLING_UB04_HCFA_SUPERBILLS": TemplateEntry("BillingRecords", "pdf_templates.medical.billing_records"),
    "PHARMACY_RECORDS": TemplateEntry("PharmacyRecords", "pdf_templates.medical.pharmacy_records"),

    # Medical — Specialty Records (Tier 2: variant of TreatingPhysicianReport)
    "ORTHOPEDIC_RECORDS": TemplateEntry("TreatingPhysicianReport", "pdf_templates.medical.treating_physician_report", "orthopedic"),
    "CHIROPRACTIC_RECORDS": TemplateEntry("TreatingPhysicianReport", "pdf_templates.medical.treating_physician_report", "chiropractic"),
    "PHYSICAL_THERAPY_RECORDS": TemplateEntry("TreatingPhysicianReport", "pdf_templates.medical.treating_physician_report", "pt"),
    "PAIN_MANAGEMENT_RECORDS": TemplateEntry("TreatingPhysicianReport", "pdf_templates.medical.treating_physician_report", "pain"),
    "PSYCHIATRIC_TREATMENT_RECORDS": TemplateEntry("TreatingPhysicianReport", "pdf_templates.medical.treating_physician_report", "psych"),
    "ACUPUNCTURE_RECORDS": TemplateEntry("TreatingPhysicianReport", "pdf_templates.medical.treating_physician_report", "acupuncture"),
    "ONGOING_TREATMENT_RECORDS": TemplateEntry("TreatingPhysicianReport", "pdf_templates.medical.treating_physician_report", "ongoing"),

    # Legal — Applications
    "APPLICATION_FOR_ADJUDICATION_ORIGINAL": TemplateEntry("ApplicationForAdjudication", "pdf_templates.legal.application_for_adjudication", "original"),
    "APPLICATION_FOR_ADJUDICATION_AMENDED": TemplateEntry("ApplicationForAdjudication", "pdf_templates.legal.application_for_adjudication", "amended"),
    "APPLICATION_FOR_ADJUDICATION_PACKAGE": TemplateEntry("ApplicationForAdjudication", "pdf_templates.legal.application_for_adjudication", "package"),
    "APPLICATION_FOR_ADJUDICATION": TemplateEntry("ApplicationForAdjudication", "pdf_templates.legal.application_for_adjudication"),

    # Legal — DOR
    "DECLARATION_OF_READINESS_REGULAR": TemplateEntry("DeclarationOfReadiness", "pdf_templates.legal.declaration_of_readiness", "regular"),
    "DECLARATION_OF_READINESS_EXPEDITED": TemplateEntry("DeclarationOfReadiness", "pdf_templates.legal.declaration_of_readiness", "expedited"),
    "DECLARATION_OF_READINESS_MSC": TemplateEntry("DeclarationOfReadiness", "pdf_templates.legal.declaration_of_readiness", "msc"),
    "DECLARATION_OF_READINESS": TemplateEntry("DeclarationOfReadiness", "pdf_templates.legal.declaration_of_readiness"),
    "DOR_STATUS_MSC_EXPEDITED": TemplateEntry("DeclarationOfReadiness", "pdf_templates.legal.declaration_of_readiness", "status_package"),

    # Legal — Minutes/Orders
    "MINUTES_ORDERS_FINDINGS_AWARD": TemplateEntry("MinutesOrders", "pdf_templates.legal.minutes_orders"),
    "ORDER_APPOINTING_QME_PANEL": TemplateEntry("MinutesOrders", "pdf_templates.legal.minutes_orders", "qme_panel"),
    "ORDER_ON_SANCTIONS": TemplateEntry("MinutesOrders", "pdf_templates.legal.minutes_orders", "sanctions"),
    "ORDER_ON_LIEN": TemplateEntry("MinutesOrders", "pdf_templates.legal.minutes_orders", "lien"),
    "ORDER_ON_RECONSIDERATION": TemplateEntry("MinutesOrders", "pdf_templates.legal.minutes_orders", "reconsideration"),
    "ORDER_ON_MSC": TemplateEntry("MinutesOrders", "pdf_templates.legal.minutes_orders", "msc"),
    "ORDER_INTERLOCUTORY": TemplateEntry("MinutesOrders", "pdf_templates.legal.minutes_orders", "interlocutory"),
    "ORDER_FINAL": TemplateEntry("MinutesOrders", "pdf_templates.legal.minutes_orders", "final"),

    # Legal — Settlements
    "STIPULATIONS_WITH_REQUEST_FOR_AWARD_PARTIAL": TemplateEntry("Stipulations", "pdf_templates.legal.stipulations", "partial"),
    "STIPULATIONS_WITH_REQUEST_FOR_AWARD_FULL": TemplateEntry("Stipulations", "pdf_templates.legal.stipulations", "full"),
    "STIPULATIONS_WITH_REQUEST_FOR_AWARD": TemplateEntry("Stipulations", "pdf_templates.legal.stipulations"),
    "STIPS_WITH_REQUEST_FOR_AWARD_PACKAGE": TemplateEntry("Stipulations", "pdf_templates.legal.stipulations", "package"),
    "COMPROMISE_AND_RELEASE_STANDARD": TemplateEntry("CompromiseAndRelease", "pdf_templates.legal.compromise_and_release", "standard"),
    "COMPROMISE_AND_RELEASE_MSA": TemplateEntry("CompromiseAndRelease", "pdf_templates.legal.compromise_and_release", "msa"),
    "COMPROMISE_AND_RELEASE": TemplateEntry("CompromiseAndRelease", "pdf_templates.legal.compromise_and_release"),
    "CR_PACKAGE_WITH_ADDENDA": TemplateEntry("CompromiseAndRelease", "pdf_templates.legal.compromise_and_release", "package"),

    # Correspondence
    "ADJUSTER_LETTER_INFORMATIONAL": TemplateEntry("AdjusterLetter", "pdf_templates.correspondence.adjuster_letter", "informational"),
    "ADJUSTER_LETTER_REQUEST": TemplateEntry("AdjusterLetter", "pdf_templates.correspondence.adjuster_letter", "request"),
    "ADJUSTER_LETTER": TemplateEntry("AdjusterLetter", "pdf_templates.correspondence.adjuster_letter"),
    "DEFENSE_COUNSEL_LETTER_INFORMATIONAL": TemplateEntry("DefenseCounselLetter", "pdf_templates.correspondence.defense_counsel_letter", "informational"),
    "DEFENSE_COUNSEL_LETTER_DEMAND": TemplateEntry("DefenseCounselLetter", "pdf_templates.correspondence.defense_counsel_letter", "demand"),
    "DEFENSE_COUNSEL_LETTER": TemplateEntry("DefenseCounselLetter", "pdf_templates.correspondence.defense_counsel_letter"),
    "NOTICE_OF_HEARING_COURT_ISSUED": TemplateEntry("CourtNotice", "pdf_templates.correspondence.court_notice", "hearing"),
    "NOTICE_OF_HEARING_PARTY_SERVED": TemplateEntry("CourtNotice", "pdf_templates.correspondence.court_notice", "hearing_served"),
    "NOTICE_OF_TRIAL": TemplateEntry("CourtNotice", "pdf_templates.correspondence.court_notice", "trial"),
    "NOTICE_OF_MSC": TemplateEntry("CourtNotice", "pdf_templates.correspondence.court_notice", "msc"),
    "NOTICE_OF_ORDER": TemplateEntry("CourtNotice", "pdf_templates.correspondence.court_notice", "order"),
    "COURT_DISTRICT_NOTICE": TemplateEntry("CourtNotice", "pdf_templates.correspondence.court_notice", "district"),
    "NOTICE_TO_APPEAR": TemplateEntry("CourtNotice", "pdf_templates.correspondence.court_notice", "appear"),
    "CLIENT_INTAKE_CORRESPONDENCE": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake"),
    "CLIENT_CORRESPONDENCE_INFORMATIONAL": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake", "informational"),
    "CLIENT_CORRESPONDENCE_REQUEST": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake", "request"),

    # Discovery
    "SUBPOENA_SDT_ISSUED": TemplateEntry("Subpoena", "pdf_templates.discovery.subpoena", "issued"),
    "SUBPOENA_SDT_RECEIVED": TemplateEntry("Subpoena", "pdf_templates.discovery.subpoena", "received"),
    "DEPOSITION_NOTICE_APPLICANT": TemplateEntry("DepositionNotice", "pdf_templates.discovery.deposition_notice", "applicant"),
    "DEPOSITION_NOTICE_DEFENDANT": TemplateEntry("DepositionNotice", "pdf_templates.discovery.deposition_notice", "defendant"),
    "DEPOSITION_NOTICE_MEDICAL_WITNESS": TemplateEntry("DepositionNotice", "pdf_templates.discovery.deposition_notice", "medical_witness"),
    "DEPOSITION_NOTICE": TemplateEntry("DepositionNotice", "pdf_templates.discovery.deposition_notice"),
    "DEPOSITION_TRANSCRIPT": TemplateEntry("DepositionTranscript", "pdf_templates.discovery.deposition_transcript"),
    "SUBPOENAED_RECORDS_MEDICAL": TemplateEntry("SubpoenaedRecords", "pdf_templates.discovery.subpoenaed_records", "medical"),
    "SUBPOENAED_RECORDS_EMPLOYMENT": TemplateEntry("SubpoenaedRecords", "pdf_templates.discovery.subpoenaed_records", "employment"),
    "SUBPOENAED_RECORDS_OTHER": TemplateEntry("SubpoenaedRecords", "pdf_templates.discovery.subpoenaed_records", "other"),
    "SUBPOENAED_RECORDS": TemplateEntry("SubpoenaedRecords", "pdf_templates.discovery.subpoenaed_records"),

    # Employment
    "WAGE_STATEMENTS_PRE_INJURY": TemplateEntry("WageStatement", "pdf_templates.employment.wage_statement", "pre_injury"),
    "WAGE_STATEMENTS_POST_INJURY": TemplateEntry("WageStatement", "pdf_templates.employment.wage_statement", "post_injury"),
    "WAGE_STATEMENTS_EARNING_RECORDS": TemplateEntry("WageStatement", "pdf_templates.employment.wage_statement"),
    "JOB_DESCRIPTION_PRE_INJURY": TemplateEntry("JobDescription", "pdf_templates.employment.job_description", "pre_injury"),
    "JOB_DESCRIPTIONS_ESSENTIAL_FUNCTIONS": TemplateEntry("JobDescription", "pdf_templates.employment.job_description", "essential_functions"),
    "PERSONNEL_FILES": TemplateEntry("PersonnelFile", "pdf_templates.employment.personnel_file"),

    # Summaries
    "MEDICAL_CHRONOLOGY_TIMELINE": TemplateEntry("MedicalChronology", "pdf_templates.summaries.medical_chronology"),
    "SETTLEMENT_VALUATION_MEMO": TemplateEntry("SettlementMemo", "pdf_templates.summaries.settlement_memo"),
}

# --- Tier 2 additional mappings (use existing templates with variant) ---
_TIER2_ADDITIONS: dict[str, TemplateEntry] = {
    # Official forms reusing close templates
    "CLAIM_FORM_DWC1": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake", "dwc1"),
    "CLAIM_FORM": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake", "claim"),
    "EMPLOYER_REPORT_INJURY": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake", "employer_report"),
    "EMPLOYER_REPORT": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake", "employer_report"),
    "FIRST_REPORT_OF_INJURY_PHYSICIAN": TemplateEntry("TreatingPhysicianReport", "pdf_templates.medical.treating_physician_report", "first_report"),
    "CLAIM_ACCEPTANCE_LETTER": TemplateEntry("AdjusterLetter", "pdf_templates.correspondence.adjuster_letter", "acceptance"),
    "CLAIM_DENIAL_LETTER": TemplateEntry("AdjusterLetter", "pdf_templates.correspondence.adjuster_letter", "denial"),
    "CLAIM_DELAY_NOTICE": TemplateEntry("AdjusterLetter", "pdf_templates.correspondence.adjuster_letter", "delay"),
    "NOTICE_OF_BENEFITS": TemplateEntry("AdjusterLetter", "pdf_templates.correspondence.adjuster_letter", "benefits"),
    "MPN_AUTHORIZATION": TemplateEntry("AdjusterLetter", "pdf_templates.correspondence.adjuster_letter", "mpn"),
    "MEDICAL_TREATMENT_AUTHORIZATION_RFA": TemplateEntry("UtilizationReview", "pdf_templates.medical.utilization_review", "rfa"),
    "IMR_APPLICATION_FORM": TemplateEntry("UtilizationReview", "pdf_templates.medical.utilization_review", "imr_application"),
    "IMR_DETERMINATION_FORM": TemplateEntry("UtilizationReview", "pdf_templates.medical.utilization_review", "imr_determination"),

    # Billing variants
    "MEDICAL_BILL_INITIAL": TemplateEntry("BillingRecords", "pdf_templates.medical.billing_records", "initial"),
    "MEDICAL_BILL_SECOND_REQUEST": TemplateEntry("BillingRecords", "pdf_templates.medical.billing_records", "second_request"),
    "MEDICAL_BILL_COLLECTION_NOTICE": TemplateEntry("BillingRecords", "pdf_templates.medical.billing_records", "collection"),
    "EXPLANATION_OF_REVIEW_EOR": TemplateEntry("BillingRecords", "pdf_templates.medical.billing_records", "eor"),

    # Settlement/Petition templates
    "SETTLEMENT_DEMAND_LETTER": TemplateEntry("DefenseCounselLetter", "pdf_templates.correspondence.defense_counsel_letter", "settlement_demand"),
    "SETTLEMENT_CONFERENCE_STATEMENT": TemplateEntry("SettlementMemo", "pdf_templates.summaries.settlement_memo", "conference"),
    "SETTLEMENT_AGREEMENT_DRAFT": TemplateEntry("CompromiseAndRelease", "pdf_templates.legal.compromise_and_release", "agreement_draft"),
    "SETTLEMENT_AGREEMENT_EXECUTED": TemplateEntry("CompromiseAndRelease", "pdf_templates.legal.compromise_and_release", "agreement_executed"),

    # Lien templates
    "LIEN_MEDICAL_PROVIDER": TemplateEntry("BillingRecords", "pdf_templates.medical.billing_records", "lien_medical"),
    "LIEN_HOSPITAL": TemplateEntry("BillingRecords", "pdf_templates.medical.billing_records", "lien_hospital"),
    "LIEN_PHARMACY": TemplateEntry("BillingRecords", "pdf_templates.medical.billing_records", "lien_pharmacy"),
    "LIEN_ATTORNEY_COSTS": TemplateEntry("BillingRecords", "pdf_templates.medical.billing_records", "lien_attorney"),
    "LIEN_AMBULANCE_TRANSPORT": TemplateEntry("BillingRecords", "pdf_templates.medical.billing_records", "lien_ambulance"),
    "LIEN_SELF_PROCUREMENT_MEDICAL": TemplateEntry("BillingRecords", "pdf_templates.medical.billing_records", "lien_self"),
    "LIEN_EDD_OVERPAYMENT": TemplateEntry("BillingRecords", "pdf_templates.medical.billing_records", "lien_edd"),
    "LIEN_RESOLUTION": TemplateEntry("Stipulations", "pdf_templates.legal.stipulations", "lien_resolution"),
    "LIEN_DISMISSAL": TemplateEntry("CourtNotice", "pdf_templates.correspondence.court_notice", "lien_dismissal"),

    # Notices
    "NOTICE_OF_LIEN_FILING": TemplateEntry("CourtNotice", "pdf_templates.correspondence.court_notice", "lien_filing"),
    "NOTICE_OF_LIEN_CONFERENCE": TemplateEntry("CourtNotice", "pdf_templates.correspondence.court_notice", "lien_conference"),
    "NOTICE_OF_INTENT_TO_FILE_LIEN": TemplateEntry("CourtNotice", "pdf_templates.correspondence.court_notice", "intent_lien"),

    # Petitions
    "PETITION_RECONSIDERATION_FILED": TemplateEntry("ApplicationForAdjudication", "pdf_templates.legal.application_for_adjudication", "reconsideration"),
    "PETITION_RECONSIDERATION_OPPOSITION": TemplateEntry("DefenseCounselLetter", "pdf_templates.correspondence.defense_counsel_letter", "opposition"),
    "PETITION_RECONSIDERATION_REPLY": TemplateEntry("DefenseCounselLetter", "pdf_templates.correspondence.defense_counsel_letter", "reply"),
    "PETITION_REMOVAL_FILED": TemplateEntry("ApplicationForAdjudication", "pdf_templates.legal.application_for_adjudication", "removal"),
    "PETITION_REMOVAL_ANSWER": TemplateEntry("DefenseCounselLetter", "pdf_templates.correspondence.defense_counsel_letter", "answer"),
    "PETITION_REOPENING": TemplateEntry("ApplicationForAdjudication", "pdf_templates.legal.application_for_adjudication", "reopening"),
    "PETITION_SERIOUS_WILLFUL": TemplateEntry("ApplicationForAdjudication", "pdf_templates.legal.application_for_adjudication", "serious_willful"),

    # Rating/Payment
    "PD_RATING_CALCULATION_WORKSHEET": TemplateEntry("SettlementMemo", "pdf_templates.summaries.settlement_memo", "rating_worksheet"),
    "PD_RATING_CONVERSION": TemplateEntry("SettlementMemo", "pdf_templates.summaries.settlement_memo", "rating_conversion"),
    "TD_PAYMENT_RECORD_ONGOING": TemplateEntry("WageStatement", "pdf_templates.employment.wage_statement", "td_ongoing"),
    "TD_PAYMENT_RECORD_RETROACTIVE": TemplateEntry("WageStatement", "pdf_templates.employment.wage_statement", "td_retroactive"),
    "PD_PAYMENT_RECORD_ADVANCE": TemplateEntry("WageStatement", "pdf_templates.employment.wage_statement", "pd_advance"),
    "PD_PAYMENT_RECORD_ONGOING": TemplateEntry("WageStatement", "pdf_templates.employment.wage_statement", "pd_ongoing"),
    "PD_PAYMENT_RECORD_FINAL": TemplateEntry("WageStatement", "pdf_templates.employment.wage_statement", "pd_final"),
    "EXPENSE_REIMBURSEMENT": TemplateEntry("BillingRecords", "pdf_templates.medical.billing_records", "reimbursement"),

    # Employment extras
    "WORK_RESTRICTIONS_POST_INJURY": TemplateEntry("JobDescription", "pdf_templates.employment.job_description", "restrictions"),
    "TIMECARDS_SCHEDULES": TemplateEntry("WageStatement", "pdf_templates.employment.wage_statement", "timecards"),
    "SAFETY_TRAINING_LOGS_INCIDENT_REPORTS": TemplateEntry("PersonnelFile", "pdf_templates.employment.personnel_file", "safety"),
    "PRIOR_CLAIMS_EDD_SDI_INFO": TemplateEntry("WageStatement", "pdf_templates.employment.wage_statement", "prior_claims"),

    # Letters/Routine
    "CLIENT_STATUS_LETTERS": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake", "status"),
    "ADJUSTER_DEMANDS_REQUESTS": TemplateEntry("AdjusterLetter", "pdf_templates.correspondence.adjuster_letter", "demands"),
    "ADVOCACY_LETTERS_PTP": TemplateEntry("DefenseCounselLetter", "pdf_templates.correspondence.defense_counsel_letter", "advocacy_ptp"),
    "ADVOCACY_LETTERS_QME": TemplateEntry("DefenseCounselLetter", "pdf_templates.correspondence.defense_counsel_letter", "advocacy_qme"),
    "ADVOCACY_LETTERS_AME": TemplateEntry("DefenseCounselLetter", "pdf_templates.correspondence.defense_counsel_letter", "advocacy_ame"),
    "ADVOCACY_LETTERS_PTP_QME_AME": TemplateEntry("DefenseCounselLetter", "pdf_templates.correspondence.defense_counsel_letter", "advocacy"),
    "EMAIL_CORRESPONDENCE": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake", "email"),
    "FAX_CORRESPONDENCE": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake", "fax"),
    "MAILED_CORRESPONDENCE": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake", "mail"),
    "DEMAND_LETTER_FORMAL": TemplateEntry("DefenseCounselLetter", "pdf_templates.correspondence.defense_counsel_letter", "formal_demand"),
    "REQUEST_FOR_INFORMATION_FORMAL": TemplateEntry("AdjusterLetter", "pdf_templates.correspondence.adjuster_letter", "info_request"),
    "STATUS_UPDATE_INFORMATIONAL": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake", "status_update"),
    "COURTESY_COPY_FYI": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake", "courtesy"),

    # Summaries
    "QME_AME_SUMMARY_WITH_ISSUE_LIST": TemplateEntry("SettlementMemo", "pdf_templates.summaries.settlement_memo", "qme_summary"),
    "DEPOSITION_SUMMARY": TemplateEntry("SettlementMemo", "pdf_templates.summaries.settlement_memo", "deposition_summary"),
    "TRIAL_BRIEF": TemplateEntry("SettlementMemo", "pdf_templates.summaries.settlement_memo", "trial_brief"),
    "PRETRIAL_CONFERENCE_STATEMENT": TemplateEntry("SettlementMemo", "pdf_templates.summaries.settlement_memo", "pretrial"),
    "CASE_ANALYSIS_MEMO": TemplateEntry("SettlementMemo", "pdf_templates.summaries.settlement_memo", "case_analysis"),

    # Expert reports
    "VOCATIONAL_EXPERT_REPORT": TemplateEntry("QmeAmeReport", "pdf_templates.medical.qme_ame_report", "vocational"),
    "VOCATIONAL_EVALUATION_REPORT": TemplateEntry("QmeAmeReport", "pdf_templates.medical.qme_ame_report", "vocational_eval"),
    "ECONOMIST_REPORT": TemplateEntry("SettlementMemo", "pdf_templates.summaries.settlement_memo", "economist"),
    "LIFE_CARE_PLANNER_REPORT": TemplateEntry("QmeAmeReport", "pdf_templates.medical.qme_ame_report", "life_care"),
    "ACCIDENT_RECONSTRUCTIONIST_REPORT": TemplateEntry("SettlementMemo", "pdf_templates.summaries.settlement_memo", "accident_recon"),
    "BIOMECHANICAL_EXPERT_REPORT": TemplateEntry("QmeAmeReport", "pdf_templates.medical.qme_ame_report", "biomechanical"),

    # Official forms
    "QME_PANEL_REQUEST_FORM_105": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake", "qme_105"),
    "QME_PANEL_REQUEST_FORM_106": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake", "qme_106"),
    "DEU_RATING_REQUEST_FORM": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake", "deu"),
    "FIRST_FILL_PHARMACY_FORM": TemplateEntry("PharmacyRecords", "pdf_templates.medical.pharmacy_records", "first_fill"),
    "OFFER_OF_WORK_REGULAR_AD_10133_53": TemplateEntry("AdjusterLetter", "pdf_templates.correspondence.adjuster_letter", "offer_regular"),
    "OFFER_OF_WORK_MODIFIED_AD_10118": TemplateEntry("AdjusterLetter", "pdf_templates.correspondence.adjuster_letter", "offer_modified"),
    "SJDB_VOUCHER_6000": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake", "sjdb_6000"),
    "SJDB_VOUCHER_8000": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake", "sjdb_8000"),
    "SJDB_VOUCHER_10000": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake", "sjdb_10000"),
    "DISTRICT_SPECIFIC_FORM": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake", "district"),
    "TRAINING_COMPLETION_CERTIFICATE": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake", "certificate"),

    # Surveillance/Investigation
    "INVESTIGATOR_REPORT": TemplateEntry("SettlementMemo", "pdf_templates.summaries.settlement_memo", "investigator"),
    "WITNESS_STATEMENT": TemplateEntry("DepositionTranscript", "pdf_templates.discovery.deposition_transcript", "witness"),
    "SURVEILLANCE_VIDEO": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake", "surveillance_log"),
    "SOCIAL_MEDIA_EVIDENCE": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake", "social_media"),
    "ACTIVITY_DIARY_SELF_REPORTED": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake", "activity_diary"),
}

# Merge tier 2 into main registry (tier 1 takes precedence)
for subtype, entry in _TIER2_ADDITIONS.items():
    if subtype not in TEMPLATE_REGISTRY:
        TEMPLATE_REGISTRY[subtype] = entry


# ---------------------------------------------------------------------------
# Template loader
# ---------------------------------------------------------------------------

_template_cache: dict[str, type] = {}


def load_template_class(class_name: str) -> type:
    """Load a template class by name, using the registry for module resolution.

    Falls back to GenericDocumentTemplate for unknown classes.
    """
    if class_name in _template_cache:
        return _template_cache[class_name]

    # Search registry for module path
    module_path = None
    for entry in TEMPLATE_REGISTRY.values():
        if entry.class_name == class_name:
            module_path = entry.module_path
            break

    if not module_path:
        # Fallback to old-style lookup
        from orchestration.pipeline import TEMPLATE_REGISTRY as OLD_REGISTRY
        module_path = OLD_REGISTRY.get(class_name)

    if not module_path:
        raise ValueError(f"Unknown template class: {class_name}")

    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    _template_cache[class_name] = cls
    return cls


def get_template_for_subtype(subtype: str) -> tuple[str, str | None]:
    """Get (template_class_name, variant) for a document subtype.

    Returns ("GenericDocumentTemplate", None) for subtypes not in the registry.
    """
    entry = TEMPLATE_REGISTRY.get(subtype)
    if entry:
        return entry.class_name, entry.variant
    return "GenericDocumentTemplate", None


def get_registry_coverage() -> dict[str, int]:
    """Return coverage stats for the registry."""
    from data.taxonomy import DocumentSubtype
    total = len(DocumentSubtype)
    covered = sum(1 for s in DocumentSubtype if s.value in TEMPLATE_REGISTRY)
    return {
        "total_subtypes": total,
        "registry_covered": covered,
        "generic_fallthrough": total - covered,
    }
