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

    # =========================================================================
    # PHASE 2: 163 new subtypes from 350-subtype taxonomy migration
    # =========================================================================

    # --- MEDICAL_CLINICAL: new specialty records subtypes ---
    "ALLERGY_IMMUNOLOGY_RECORDS": TemplateEntry("TreatingPhysicianReport", "pdf_templates.medical.treating_physician_report", "allergy_immunology"),
    "CARDIOVASCULAR_RECORDS": TemplateEntry("TreatingPhysicianReport", "pdf_templates.medical.treating_physician_report", "cardiovascular"),
    "DENTISTRY_RECORDS": TemplateEntry("TreatingPhysicianReport", "pdf_templates.medical.treating_physician_report", "dentistry"),
    "DERMATOLOGY_RECORDS": TemplateEntry("TreatingPhysicianReport", "pdf_templates.medical.treating_physician_report", "dermatology"),
    "ENDOCRINOLOGY_RECORDS": TemplateEntry("TreatingPhysicianReport", "pdf_templates.medical.treating_physician_report", "endocrinology"),
    "FAMILY_PRACTICE_RECORDS": TemplateEntry("TreatingPhysicianReport", "pdf_templates.medical.treating_physician_report", "family_practice"),
    "GASTROENTEROLOGY_RECORDS": TemplateEntry("TreatingPhysicianReport", "pdf_templates.medical.treating_physician_report", "gastroenterology"),
    "GENERAL_SURGERY_RECORDS": TemplateEntry("TreatingPhysicianReport", "pdf_templates.medical.treating_physician_report", "general_surgery"),
    "HAND_SURGERY_RECORDS": TemplateEntry("TreatingPhysicianReport", "pdf_templates.medical.treating_physician_report", "hand_surgery"),
    "HEMATOLOGY_RECORDS": TemplateEntry("TreatingPhysicianReport", "pdf_templates.medical.treating_physician_report", "hematology"),
    "HOME_HEALTH_RECORDS": TemplateEntry("TreatingPhysicianReport", "pdf_templates.medical.treating_physician_report", "home_health"),
    "INFECTIOUS_DISEASE_RECORDS": TemplateEntry("TreatingPhysicianReport", "pdf_templates.medical.treating_physician_report", "infectious_disease"),
    "INTERNAL_MEDICINE_RECORDS": TemplateEntry("TreatingPhysicianReport", "pdf_templates.medical.treating_physician_report", "internal_medicine"),
    "NEPHROLOGY_RECORDS": TemplateEntry("TreatingPhysicianReport", "pdf_templates.medical.treating_physician_report", "nephrology"),
    "NEUROLOGICAL_SURGERY_RECORDS": TemplateEntry("TreatingPhysicianReport", "pdf_templates.medical.treating_physician_report", "neurological_surgery"),
    "NEUROLOGY_RECORDS": TemplateEntry("TreatingPhysicianReport", "pdf_templates.medical.treating_physician_report", "neurology"),
    "NURSING_RECORDS": TemplateEntry("TreatingPhysicianReport", "pdf_templates.medical.treating_physician_report", "nursing"),
    "OBSTETRICS_GYNECOLOGY_RECORDS": TemplateEntry("TreatingPhysicianReport", "pdf_templates.medical.treating_physician_report", "obstetrics_gynecology"),
    "OCCUPATIONAL_MEDICINE_RECORDS": TemplateEntry("TreatingPhysicianReport", "pdf_templates.medical.treating_physician_report", "occupational_medicine"),
    "ONCOLOGY_RECORDS": TemplateEntry("TreatingPhysicianReport", "pdf_templates.medical.treating_physician_report", "oncology"),
    "OPTOMETRY_RECORDS": TemplateEntry("TreatingPhysicianReport", "pdf_templates.medical.treating_physician_report", "optometry"),
    "OTOLARYNGOLOGY_RECORDS": TemplateEntry("TreatingPhysicianReport", "pdf_templates.medical.treating_physician_report", "otolaryngology"),
    "PHYSICAL_MEDICINE_REHAB_RECORDS": TemplateEntry("TreatingPhysicianReport", "pdf_templates.medical.treating_physician_report", "physical_medicine_rehab"),
    "PODIATRY_RECORDS": TemplateEntry("TreatingPhysicianReport", "pdf_templates.medical.treating_physician_report", "podiatry"),
    "PREVENTIVE_MEDICINE_RECORDS": TemplateEntry("TreatingPhysicianReport", "pdf_templates.medical.treating_physician_report", "preventive_medicine"),
    "PSYCHOLOGY_RECORDS": TemplateEntry("TreatingPhysicianReport", "pdf_templates.medical.treating_physician_report", "psychology"),
    "PULMONARY_RECORDS": TemplateEntry("TreatingPhysicianReport", "pdf_templates.medical.treating_physician_report", "pulmonary"),
    "RHEUMATOLOGY_RECORDS": TemplateEntry("TreatingPhysicianReport", "pdf_templates.medical.treating_physician_report", "rheumatology"),
    "SPINE_RECORDS": TemplateEntry("TreatingPhysicianReport", "pdf_templates.medical.treating_physician_report", "spine"),
    "THORACIC_SURGERY_RECORDS": TemplateEntry("TreatingPhysicianReport", "pdf_templates.medical.treating_physician_report", "thoracic_surgery"),
    "TOXICOLOGY_RECORDS": TemplateEntry("TreatingPhysicianReport", "pdf_templates.medical.treating_physician_report", "toxicology"),
    "UROLOGY_RECORDS": TemplateEntry("TreatingPhysicianReport", "pdf_templates.medical.treating_physician_report", "urology"),
    "VASCULAR_SURGERY_RECORDS": TemplateEntry("TreatingPhysicianReport", "pdf_templates.medical.treating_physician_report", "vascular_surgery"),
    "FACE_SHEET": TemplateEntry("OperativeRecord", "pdf_templates.medical.operative_record", "face_sheet"),
    "NEUROPSYCHOLOGICAL_EVALUATION": TemplateEntry("QmeAmeReport", "pdf_templates.medical.qme_ame_report", "neuropsych"),
    "SLEEP_STUDY": TemplateEntry("DiagnosticReport", "pdf_templates.medical.diagnostic_report", "sleep_study"),
    "EMG_NCV_STUDY": TemplateEntry("DiagnosticReport", "pdf_templates.medical.diagnostic_report", "emg_ncv"),
    "DEATH_CERTIFICATE": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake", "death_certificate"),
    "AUTOPSY_REPORT": TemplateEntry("QmeAmeReport", "pdf_templates.medical.qme_ame_report", "autopsy"),

    # --- MEDICAL_LEGAL: new subtypes ---
    "AME_COMPREHENSIVE_REPORT": TemplateEntry("QmeAmeReport", "pdf_templates.medical.qme_ame_report", "ame_comprehensive"),
    "SUPPLEMENTAL_QME_AME_REPORT": TemplateEntry("QmeAmeReport", "pdf_templates.medical.qme_ame_report", "supplemental"),
    "FCE_REPORT": TemplateEntry("QmeAmeReport", "pdf_templates.medical.qme_ame_report", "fce"),
    "PEER_REVIEW_REPORT": TemplateEntry("QmeAmeReport", "pdf_templates.medical.qme_ame_report", "peer_review"),
    "IMPAIRMENT_RATING_WORKSHEET": TemplateEntry("SettlementMemo", "pdf_templates.summaries.settlement_memo", "impairment_worksheet"),
    "MEDICAL_RECORD_REVIEW_LIST": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake", "record_review_list"),
    "PSYCHOLOGICAL_TESTING_PROTOCOL": TemplateEntry("QmeAmeReport", "pdf_templates.medical.qme_ame_report", "psych_testing"),
    "LIFE_EXPECTANCY_REPORT": TemplateEntry("QmeAmeReport", "pdf_templates.medical.qme_ame_report", "life_expectancy"),
    "QME_COMPREHENSIVE_REPORT": TemplateEntry("QmeAmeReport", "pdf_templates.medical.qme_ame_report", "qme_comprehensive"),

    # --- UTILIZATION_MANAGEMENT: new subtypes ---
    "UR_APPEAL_LETTER": TemplateEntry("UtilizationReview", "pdf_templates.medical.utilization_review", "appeal"),
    "UR_PEER_TO_PEER_NOTES": TemplateEntry("UtilizationReview", "pdf_templates.medical.utilization_review", "peer_to_peer"),
    "PHARMACY_AUTHORIZATION": TemplateEntry("UtilizationReview", "pdf_templates.medical.utilization_review", "pharmacy_auth"),
    "DME_AUTHORIZATION": TemplateEntry("UtilizationReview", "pdf_templates.medical.utilization_review", "dme_auth"),

    # --- PLEADINGS_FILINGS: new subtypes ---
    "APPLICATION_FOR_ADJUDICATION_DEATH": TemplateEntry("ApplicationForAdjudication", "pdf_templates.legal.application_for_adjudication", "death"),
    "APPLICATION_ADDENDUM_EMPLOYER_ENTITY": TemplateEntry("ApplicationForAdjudication", "pdf_templates.legal.application_for_adjudication", "addendum_employer"),
    "ANSWER_TO_APPLICATION": TemplateEntry("DefenseCounselLetter", "pdf_templates.correspondence.defense_counsel_letter", "answer_application"),
    "OBJECTION_TO_DOR": TemplateEntry("DefenseCounselLetter", "pdf_templates.correspondence.defense_counsel_letter", "objection_dor"),
    "PETITION_132A_DISCRIMINATION": TemplateEntry("ApplicationForAdjudication", "pdf_templates.legal.application_for_adjudication", "discrimination_132a"),
    "PETITION_TO_DISMISS": TemplateEntry("ApplicationForAdjudication", "pdf_templates.legal.application_for_adjudication", "dismiss"),
    "PETITION_CHANGE_PTP": TemplateEntry("ApplicationForAdjudication", "pdf_templates.legal.application_for_adjudication", "change_ptp"),
    "PETITION_COMMUTATION": TemplateEntry("ApplicationForAdjudication", "pdf_templates.legal.application_for_adjudication", "commutation"),
    "PETITION_FOR_COSTS": TemplateEntry("ApplicationForAdjudication", "pdf_templates.legal.application_for_adjudication", "costs"),
    "PETITION_GUARDIAN_AD_LITEM": TemplateEntry("ApplicationForAdjudication", "pdf_templates.legal.application_for_adjudication", "guardian_ad_litem"),
    "PETITION_NEW_FURTHER_DISABILITY": TemplateEntry("ApplicationForAdjudication", "pdf_templates.legal.application_for_adjudication", "new_further_disability"),
    "PETITION_TERMINATE_TD": TemplateEntry("ApplicationForAdjudication", "pdf_templates.legal.application_for_adjudication", "terminate_td"),
    "PETITION_TO_BIFURCATE": TemplateEntry("ApplicationForAdjudication", "pdf_templates.legal.application_for_adjudication", "bifurcate"),
    "MOTION_FOR_JOINDER": TemplateEntry("ApplicationForAdjudication", "pdf_templates.legal.application_for_adjudication", "motion_joinder"),
    "MOTION_FOR_SANCTIONS": TemplateEntry("ApplicationForAdjudication", "pdf_templates.legal.application_for_adjudication", "motion_sanctions"),
    "MOTION_TO_COMPEL": TemplateEntry("ApplicationForAdjudication", "pdf_templates.legal.application_for_adjudication", "motion_compel"),
    "MOTION_TO_CONSOLIDATE": TemplateEntry("ApplicationForAdjudication", "pdf_templates.legal.application_for_adjudication", "motion_consolidate"),
    "MOTION_TO_QUASH_SUBPOENA": TemplateEntry("ApplicationForAdjudication", "pdf_templates.legal.application_for_adjudication", "motion_quash"),
    "PROOF_OF_SERVICE": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake", "proof_of_service"),
    "SUBSTITUTION_OF_ATTORNEY": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake", "substitution_attorney"),
    "ATTORNEY_FEE_DISCLOSURE": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake", "fee_disclosure"),
    "ARBITRATION_SUBMITTAL": TemplateEntry("SettlementMemo", "pdf_templates.summaries.settlement_memo", "arbitration"),
    "PRETRIAL_CONFERENCE_STATEMENT_LIEN": TemplateEntry("SettlementMemo", "pdf_templates.summaries.settlement_memo", "pretrial_lien"),

    # --- ORDERS_DECISIONS: new subtypes ---
    "FINDINGS_AND_AWARD": TemplateEntry("MinutesOrders", "pdf_templates.legal.minutes_orders", "findings_award"),
    "AMENDED_FINDINGS_AWARD": TemplateEntry("MinutesOrders", "pdf_templates.legal.minutes_orders", "amended_findings"),
    "OPINION_ON_DECISION": TemplateEntry("MinutesOrders", "pdf_templates.legal.minutes_orders", "opinion"),
    "APPELLATE_COURT_DECISION": TemplateEntry("MinutesOrders", "pdf_templates.legal.minutes_orders", "appellate"),
    "MINUTES_OF_HEARING": TemplateEntry("MinutesOrders", "pdf_templates.legal.minutes_orders", "hearing_minutes"),
    "MINUTES_OF_HEARING_SUPPLEMENT": TemplateEntry("MinutesOrders", "pdf_templates.legal.minutes_orders", "hearing_supplement"),
    "ORDER_APPROVING_SETTLEMENT": TemplateEntry("MinutesOrders", "pdf_templates.legal.minutes_orders", "approving_settlement"),
    "ORDER_DISMISSING_CASE": TemplateEntry("MinutesOrders", "pdf_templates.legal.minutes_orders", "dismissing"),
    "ORDER_TAKING_OFF_CALENDAR": TemplateEntry("MinutesOrders", "pdf_templates.legal.minutes_orders", "off_calendar"),

    # --- SETTLEMENTS: new subtypes ---
    "COMPROMISE_AND_RELEASE_PD_ONLY": TemplateEntry("CompromiseAndRelease", "pdf_templates.legal.compromise_and_release", "pd_only"),
    "COMPROMISE_AND_RELEASE_DEPENDENCY": TemplateEntry("CompromiseAndRelease", "pdf_templates.legal.compromise_and_release", "dependency"),
    "COMPROMISE_AND_RELEASE_THIRD_PARTY": TemplateEntry("CompromiseAndRelease", "pdf_templates.legal.compromise_and_release", "third_party"),
    "STIPULATIONS_DEATH_CASE": TemplateEntry("Stipulations", "pdf_templates.legal.stipulations", "death"),
    "ADDENDUM_TO_SETTLEMENT": TemplateEntry("CompromiseAndRelease", "pdf_templates.legal.compromise_and_release", "addendum"),
    "MSA_SUBMISSION": TemplateEntry("SettlementMemo", "pdf_templates.summaries.settlement_memo", "msa_submission"),
    "MSA_APPROVAL_LETTER": TemplateEntry("AdjusterLetter", "pdf_templates.correspondence.adjuster_letter", "msa_approval"),
    "STRUCTURED_SETTLEMENT_QUOTE": TemplateEntry("SettlementMemo", "pdf_templates.summaries.settlement_memo", "structured_quote"),

    # --- REGULATORY_FORMS: new subtypes ---
    "QME_REPLACEMENT_PANEL_REQUEST": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake", "qme_replacement_panel"),
    "QME_ADDITIONAL_PANEL_REQUEST": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake", "qme_additional_panel"),
    "QME_PANEL_COMMUNICATION_FORM": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake", "qme_panel_comm"),
    "QME_EXAM_NOTICE_TO_WORKER": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake", "qme_exam_notice"),
    "QME_UNAVAILABILITY_NOTICE": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake", "qme_unavailability"),
    "QME_CONFLICT_OF_INTEREST": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake", "qme_conflict"),
    "QME_DECLARATION_OF_SERVICE": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake", "qme_declaration"),
    "QME_FACTUAL_CORRECTION_REQUEST": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake", "qme_factual_correction"),
    "DEU_RATING_REQUEST_QME": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake", "deu_rating_qme"),
    "DEU_RATING_REQUEST_PTP": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake", "deu_rating_ptp"),
    "DEU_RATING_RECONSIDERATION": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake", "deu_reconsideration"),
    "DEU_CONSULTATIVE_RATING_REQUEST": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake", "deu_consultative"),
    "DEU_APPORTIONMENT_REQUEST": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake", "deu_apportionment"),
    "DEU_NOTICE_OPTIONS_POST_RATING": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake", "deu_notice_options"),
    "EMPLOYER_NOTICE_TO_EMPLOYEES": TemplateEntry("AdjusterLetter", "pdf_templates.correspondence.adjuster_letter", "employer_notice"),
    "NOTICE_OF_EMPLOYEE_DEATH": TemplateEntry("AdjusterLetter", "pdf_templates.correspondence.adjuster_letter", "death_notice"),
    "OFFER_OF_WORK_MODIFIED_ALTERNATIVE": TemplateEntry("AdjusterLetter", "pdf_templates.correspondence.adjuster_letter", "offer_modified_alt"),
    "PHYSICIAN_RTW_VOUCHER_REPORT": TemplateEntry("TreatingPhysicianReport", "pdf_templates.medical.treating_physician_report", "rtw_voucher"),
    "PREDESIGNATION_PHYSICIAN": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake", "predesignation_physician"),
    "PREDESIGNATION_CHIRO_ACUPUNCTURE": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake", "predesignation_chiro"),
    "SJDB_JOB_DUTIES_DESCRIPTION": TemplateEntry("JobDescription", "pdf_templates.employment.job_description", "sjdb_duties"),
    "EMPLOYEE_PD_QUESTIONNAIRE": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake", "pd_questionnaire"),
    "MEDICAL_MILEAGE_EXPENSE": TemplateEntry("BillingRecords", "pdf_templates.medical.billing_records", "mileage"),
    "SECTION_111_REPORT": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake", "section_111"),
    "OSHA_FORM_300_LOG": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake", "osha_300"),

    # --- CLAIMS_ADMINISTRATION: new subtypes ---
    "CLAIMS_ADMINISTRATION_DOCUMENT": TemplateEntry("AdjusterLetter", "pdf_templates.correspondence.adjuster_letter", "claims_admin"),
    "CLAIMS_CLOSURE_SUMMARY": TemplateEntry("AdjusterLetter", "pdf_templates.correspondence.adjuster_letter", "closure_summary"),
    "CLAIMS_DIARY_NOTE": TemplateEntry("AdjusterLetter", "pdf_templates.correspondence.adjuster_letter", "diary_note"),
    "CLAIM_INVESTIGATION_REPORT": TemplateEntry("AdjusterLetter", "pdf_templates.correspondence.adjuster_letter", "investigation_report"),
    "COMPENSABILITY_DETERMINATION": TemplateEntry("AdjusterLetter", "pdf_templates.correspondence.adjuster_letter", "compensability"),
    "EXCESS_CARRIER_REPORT": TemplateEntry("SettlementMemo", "pdf_templates.summaries.settlement_memo", "excess_carrier"),
    "LARGE_LOSS_REPORT": TemplateEntry("SettlementMemo", "pdf_templates.summaries.settlement_memo", "large_loss"),
    "MEDICAL_MANAGEMENT_SUMMARY": TemplateEntry("AdjusterLetter", "pdf_templates.correspondence.adjuster_letter", "medical_management"),
    "NURSE_CASE_MANAGER_REPORT": TemplateEntry("TreatingPhysicianReport", "pdf_templates.medical.treating_physician_report", "nurse_case_manager"),
    "RESERVE_CHANGE_NOTICE": TemplateEntry("BillingRecords", "pdf_templates.medical.billing_records", "reserve_change"),
    "RESERVE_WORKSHEET": TemplateEntry("BillingRecords", "pdf_templates.medical.billing_records", "reserve_worksheet"),
    "RETURN_TO_WORK_COORDINATION": TemplateEntry("AdjusterLetter", "pdf_templates.correspondence.adjuster_letter", "rtw_coordination"),

    # --- BILLING_FINANCIAL: new subtypes ---
    "BENEFIT_CALCULATION_WORKSHEET": TemplateEntry("BillingRecords", "pdf_templates.medical.billing_records", "benefit_calc"),
    "BENEFIT_PAYMENT_LEDGER": TemplateEntry("BillingRecords", "pdf_templates.medical.billing_records", "payment_ledger"),
    "BILL_REVIEW_DECISION": TemplateEntry("BillingRecords", "pdf_templates.medical.billing_records", "bill_review"),
    "CONDITIONAL_PAYMENT_NOTICE": TemplateEntry("AdjusterLetter", "pdf_templates.correspondence.adjuster_letter", "conditional_payment"),
    "IBR_APPLICATION": TemplateEntry("BillingRecords", "pdf_templates.medical.billing_records", "ibr_application"),
    "IBR_DECISION": TemplateEntry("BillingRecords", "pdf_templates.medical.billing_records", "ibr_decision"),
    "ML_FEE_BILLING": TemplateEntry("BillingRecords", "pdf_templates.medical.billing_records", "ml_fee"),
    "PAYMENT_RECORD": TemplateEntry("BillingRecords", "pdf_templates.medical.billing_records", "payment"),
    "PROVIDER_PAYMENT_SUMMARY": TemplateEntry("BillingRecords", "pdf_templates.medical.billing_records", "provider_summary"),
    "SECOND_BILL_REVIEW_REQUEST": TemplateEntry("BillingRecords", "pdf_templates.medical.billing_records", "second_review"),
    "SUBROGATION_DEMAND": TemplateEntry("DefenseCounselLetter", "pdf_templates.correspondence.defense_counsel_letter", "subrogation"),

    # --- CORRESPONDENCE: new subtypes ---
    "COVERAGE_OPINION_LETTER": TemplateEntry("DefenseCounselLetter", "pdf_templates.correspondence.defense_counsel_letter", "coverage_opinion"),
    "EVALUATION_COVER_LETTER": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake", "eval_cover"),
    "NOTICE_OF_REPRESENTATION": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake", "representation"),
    "NOTICE_DISMISSAL_OF_ATTORNEY": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake", "dismissal_attorney"),

    # --- DISCOVERY: new subtypes ---
    "CUSTODIAN_OF_RECORDS_DECLARATION": TemplateEntry("SubpoenaedRecords", "pdf_templates.discovery.subpoenaed_records", "custodian"),

    # --- EMPLOYMENT_RECORDS: new subtypes ---
    "EMPLOYER_INCIDENT_INVESTIGATION": TemplateEntry("PersonnelFile", "pdf_templates.employment.personnel_file", "investigation"),
    "ERGONOMIC_ASSESSMENT": TemplateEntry("JobDescription", "pdf_templates.employment.job_description", "ergonomic"),
    "DEPENDENCY_DECLARATION": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake", "dependency"),

    # --- LIENS: new subtypes ---
    "LIEN_CLAIM": TemplateEntry("BillingRecords", "pdf_templates.medical.billing_records", "lien_general"),
    "LIEN_STIPULATION_AGREEMENT": TemplateEntry("Stipulations", "pdf_templates.legal.stipulations", "lien_stipulation"),

    # --- INVESTIGATION: new subtypes ---
    "FRAUD_INVESTIGATION_REPORT": TemplateEntry("SettlementMemo", "pdf_templates.summaries.settlement_memo", "fraud_investigation"),
    "INVESTIGATION_REPORT": TemplateEntry("SettlementMemo", "pdf_templates.summaries.settlement_memo", "investigation_general"),
    "OSHA_CITATION": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake", "osha_citation"),
    "OSHA_INSPECTION_REPORT": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake", "osha_inspection"),

    # --- WORK_PRODUCT: new subtypes ---
    "APPORTIONMENT_WORKSHEET": TemplateEntry("SettlementMemo", "pdf_templates.summaries.settlement_memo", "apportionment_worksheet"),
    "DEFENSE_CASE_ANALYSIS": TemplateEntry("SettlementMemo", "pdf_templates.summaries.settlement_memo", "defense_analysis"),
    "DEFENSE_MSC_STATEMENT": TemplateEntry("SettlementMemo", "pdf_templates.summaries.settlement_memo", "defense_msc"),
    "DEFENSE_TRIAL_BRIEF": TemplateEntry("SettlementMemo", "pdf_templates.summaries.settlement_memo", "defense_trial_brief"),
    "EARNINGS_CAPACITY_OPINION": TemplateEntry("QmeAmeReport", "pdf_templates.medical.qme_ame_report", "earnings_capacity"),
    "LABOR_MARKET_SURVEY": TemplateEntry("QmeAmeReport", "pdf_templates.medical.qme_ame_report", "labor_market"),
    "MSA_ALLOCATION_REPORT": TemplateEntry("SettlementMemo", "pdf_templates.summaries.settlement_memo", "msa_allocation"),
    "TRANSFERABLE_SKILLS_ANALYSIS": TemplateEntry("QmeAmeReport", "pdf_templates.medical.qme_ame_report", "transferable_skills"),
    "WORK_PRODUCT_DOCUMENT": TemplateEntry("SettlementMemo", "pdf_templates.summaries.settlement_memo", "work_product"),

    # =========================================================================
    # PHASE 2b: 30 new subtypes — correspondence, court, discovery, rating, summaries
    # =========================================================================

    # --- CORRESPONDENCE: new client/carrier/admin subtypes ---
    "RETAINER_FEE_AGREEMENT": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake", "Retainer / Fee Agreement"),
    "CLIENT_REPORT_ANALYSIS_LETTER": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake", "Client Report Analysis Letter"),
    "CLIENT_CASE_VALUATION_LETTER": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake", "Client Case Valuation Letter"),
    "CLIENT_SETTLEMENT_RECOMMENDATION": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake", "Client Settlement Recommendation"),
    "CLIENT_HIPAA_AUTHORIZATION": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake", "Client HIPAA Authorization"),
    "CLIENT_DECLARATION": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake", "Client Declaration"),
    "CARRIER_POSITION_STATEMENT": TemplateEntry("AdjusterLetter", "pdf_templates.correspondence.adjuster_letter", "Carrier Position Statement"),
    "RESERVATION_OF_RIGHTS_LETTER": TemplateEntry("AdjusterLetter", "pdf_templates.correspondence.adjuster_letter", "Reservation of Rights Letter"),
    "EAMS_CASE_SUMMARY": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake", "EAMS Case Summary"),

    # --- PLEADINGS_FILINGS: new filing subtypes ---
    "REQUEST_FOR_CONTINUANCE": TemplateEntry("ApplicationForAdjudication", "pdf_templates.legal.application_for_adjudication", "Request for Continuance"),
    "PETITION_FOR_PENALTIES_LC_5814": TemplateEntry("ApplicationForAdjudication", "pdf_templates.legal.application_for_adjudication", "Petition for Penalties (LC 5814)"),
    "ATTORNEY_FEE_PETITION": TemplateEntry("ApplicationForAdjudication", "pdf_templates.legal.application_for_adjudication", "Attorney Fee Petition"),
    "JOINT_PRETRIAL_CONFERENCE_STATEMENT": TemplateEntry("SettlementMemo", "pdf_templates.summaries.settlement_memo", "Joint Pre-Trial Conference Statement"),
    "EXHIBIT_LIST": TemplateEntry("SettlementMemo", "pdf_templates.summaries.settlement_memo", "Exhibit List"),
    "WITNESS_LIST": TemplateEntry("SettlementMemo", "pdf_templates.summaries.settlement_memo", "Witness List"),

    # --- CORRESPONDENCE: QME/PTP letter subtypes ---
    "OBJECTION_TO_QME_AME_REPORT": TemplateEntry("DefenseCounselLetter", "pdf_templates.correspondence.defense_counsel_letter", "Objection to QME/AME Report"),
    "REQUEST_SUPPLEMENTAL_QME_AME_REPORT": TemplateEntry("DefenseCounselLetter", "pdf_templates.correspondence.defense_counsel_letter", "Request for Supplemental QME/AME Report"),
    "QME_PANEL_STRIKE_LETTER": TemplateEntry("ClientIntake", "pdf_templates.correspondence.client_intake", "QME Panel Strike Letter"),
    "PTP_REFERRAL_LETTER": TemplateEntry("TreatingPhysicianReport", "pdf_templates.medical.treating_physician_report", "PTP Referral Letter"),

    # --- DISCOVERY: new subtypes ---
    "INTERROGATORIES_SPECIAL": TemplateEntry("Subpoena", "pdf_templates.discovery.subpoena", "Special Interrogatories"),
    "INTERROGATORY_RESPONSES": TemplateEntry("DepositionTranscript", "pdf_templates.discovery.deposition_transcript", "Interrogatory Responses"),
    "REQUEST_FOR_PRODUCTION": TemplateEntry("Subpoena", "pdf_templates.discovery.subpoena", "Request for Production of Documents"),
    "PRODUCTION_RESPONSES": TemplateEntry("DepositionTranscript", "pdf_templates.discovery.deposition_transcript", "Responses to Request for Production"),
    "DEPOSITION_TRANSCRIPT_QME_AME": TemplateEntry("DepositionTranscript", "pdf_templates.discovery.deposition_transcript", "Deposition Transcript (QME/AME)"),

    # --- BILLING/CLAIMS/EMPLOYMENT/WORK_PRODUCT: new subtypes ---
    "TD_RATE_CALCULATION_NOTICE": TemplateEntry("WageStatement", "pdf_templates.employment.wage_statement", "TD Rate Calculation Notice"),
    "NOTICE_OF_TD_TERMINATION": TemplateEntry("AdjusterLetter", "pdf_templates.correspondence.adjuster_letter", "Notice of TD Termination"),
    "RETURN_TO_WORK_REPORT": TemplateEntry("JobDescription", "pdf_templates.employment.job_description", "Return to Work Report"),
    "MILEAGE_REIMBURSEMENT_REQUEST": TemplateEntry("BillingRecords", "pdf_templates.medical.billing_records", "Mileage Reimbursement Request"),
    "INFORMAL_PD_RATING_PRINTOUT": TemplateEntry("SettlementMemo", "pdf_templates.summaries.settlement_memo", "Informal PD Rating Printout"),
    "CMS_CONDITIONAL_PAYMENT_LETTER": TemplateEntry("AdjusterLetter", "pdf_templates.correspondence.adjuster_letter", "CMS Conditional Payment Letter"),
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
