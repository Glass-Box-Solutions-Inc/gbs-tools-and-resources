"""
Template hints for generic document generation — provides structure guidance
for subtypes that don't have dedicated templates.

These hints describe the expected format, sections, and page count for each
document subtype, enabling GenericDocumentTemplate to produce correctly
structured PDFs.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TemplateHint:
    """Structure hints for a document subtype."""
    format: str = "General document"
    required_sections: list[str] = field(default_factory=list)
    common_headings: list[str] = field(default_factory=list)
    page_count_range: tuple[int, int] = (1, 3)
    content_style: str = "formal"  # formal, medical, legal, correspondence


# Hints organized by document category
TEMPLATE_HINTS: dict[str, TemplateHint] = {
    # --- Official Forms ---
    "DEU_RATING_REQUEST_FORM": TemplateHint(
        format="Official DWC form",
        required_sections=["Applicant Information", "Injury Details", "Rating Request"],
        common_headings=["DISABILITY EVALUATION UNIT — RATING REQUEST"],
        page_count_range=(2, 4),
        content_style="legal",
    ),
    "QME_PANEL_REQUEST_FORM_105": TemplateHint(
        format="Official DWC form",
        required_sections=["Applicant Information", "Specialty Requested", "Reason for QME"],
        common_headings=["QME PANEL REQUEST — FORM 105"],
        page_count_range=(2, 3),
        content_style="legal",
    ),
    "QME_PANEL_REQUEST_FORM_106": TemplateHint(
        format="Official DWC form",
        required_sections=["Applicant Information", "Specialty", "Objection Basis"],
        common_headings=["QME PANEL REQUEST — FORM 106"],
        page_count_range=(2, 3),
        content_style="legal",
    ),
    "FIRST_FILL_PHARMACY_FORM": TemplateHint(
        format="Pharmacy authorization form",
        required_sections=["Patient Information", "Physician Information", "Medications"],
        common_headings=["FIRST FILL PHARMACY AUTHORIZATION"],
        page_count_range=(1, 2),
        content_style="medical",
    ),
    "OFFER_OF_WORK_REGULAR_AD_10133_53": TemplateHint(
        format="Official DWC offer of work form",
        required_sections=["Employee Information", "Job Offered", "Physical Requirements", "Wage"],
        common_headings=["NOTICE OF OFFER OF REGULAR WORK — DWC AD 10133.53"],
        page_count_range=(2, 3),
        content_style="legal",
    ),
    "OFFER_OF_WORK_MODIFIED_AD_10118": TemplateHint(
        format="Official DWC offer of work form",
        required_sections=["Employee Information", "Modified Job", "Restrictions Accommodated", "Wage"],
        common_headings=["NOTICE OF OFFER OF MODIFIED OR ALTERNATIVE WORK — DWC AD 10118"],
        page_count_range=(2, 3),
        content_style="legal",
    ),
    "DISTRICT_SPECIFIC_FORM": TemplateHint(
        format="District-specific WCAB form",
        required_sections=["Case Information", "District", "Instructions"],
        common_headings=["WCAB DISTRICT FORM"],
        page_count_range=(1, 2),
        content_style="legal",
    ),

    # --- Summaries & Expert Reports ---
    "VOCATIONAL_EXPERT_REPORT": TemplateHint(
        format="Expert report",
        required_sections=["Qualifications", "Background", "Analysis", "Opinions", "Conclusions"],
        common_headings=["VOCATIONAL EXPERT REPORT"],
        page_count_range=(8, 20),
        content_style="formal",
    ),
    "ECONOMIST_REPORT": TemplateHint(
        format="Expert report",
        required_sections=["Qualifications", "Methodology", "Economic Analysis", "Loss Calculations", "Conclusions"],
        common_headings=["ECONOMIC LOSS ANALYSIS"],
        page_count_range=(6, 15),
        content_style="formal",
    ),
    "LIFE_CARE_PLANNER_REPORT": TemplateHint(
        format="Expert medical report",
        required_sections=["Qualifications", "Medical History", "Future Care Needs", "Cost Projections", "Life Expectancy"],
        common_headings=["LIFE CARE PLAN"],
        page_count_range=(10, 30),
        content_style="medical",
    ),
    "ACCIDENT_RECONSTRUCTIONIST_REPORT": TemplateHint(
        format="Expert report",
        required_sections=["Qualifications", "Incident Description", "Analysis", "Conclusions"],
        common_headings=["ACCIDENT RECONSTRUCTION REPORT"],
        page_count_range=(5, 15),
        content_style="formal",
    ),
    "BIOMECHANICAL_EXPERT_REPORT": TemplateHint(
        format="Expert medical report",
        required_sections=["Qualifications", "Biomechanical Analysis", "Injury Causation", "Opinions"],
        common_headings=["BIOMECHANICAL ENGINEERING REPORT"],
        page_count_range=(6, 18),
        content_style="medical",
    ),

    # --- Rating & RTW ---
    "PD_RATING_CONVERSION": TemplateHint(
        format="Rating calculation worksheet",
        required_sections=["Impairment Rating", "Adjustments", "Final PD Rating"],
        common_headings=["PERMANENT DISABILITY RATING — CONVERSION"],
        page_count_range=(1, 3),
        content_style="legal",
    ),
    "PD_RATING_CALCULATION_WORKSHEET": TemplateHint(
        format="Rating worksheet",
        required_sections=["WPI", "FEC Adjustments", "Age/Occupation", "Final Rating"],
        common_headings=["PD RATING CALCULATION WORKSHEET"],
        page_count_range=(2, 4),
        content_style="legal",
    ),
    "EXPENSE_REIMBURSEMENT": TemplateHint(
        format="Financial form",
        required_sections=["Claimant", "Expense Items", "Total", "Authorization"],
        common_headings=["EXPENSE REIMBURSEMENT REQUEST"],
        page_count_range=(1, 2),
        content_style="formal",
    ),

    # --- Employment ---
    "TIMECARDS_SCHEDULES": TemplateHint(
        format="Employment records",
        required_sections=["Employee Information", "Pay Period", "Hours", "Schedule"],
        common_headings=["TIMECARD / SCHEDULE RECORDS"],
        page_count_range=(2, 6),
        content_style="formal",
    ),
    "SAFETY_TRAINING_LOGS_INCIDENT_REPORTS": TemplateHint(
        format="Safety documentation",
        required_sections=["Training Records", "Incident Description", "Date", "Participants"],
        common_headings=["SAFETY TRAINING LOG / INCIDENT REPORT"],
        page_count_range=(2, 5),
        content_style="formal",
    ),
    "PRIOR_CLAIMS_EDD_SDI_INFO": TemplateHint(
        format="Claims history",
        required_sections=["Prior Claims", "EDD Information", "SDI Benefits"],
        common_headings=["PRIOR CLAIMS / EDD / SDI INFORMATION"],
        page_count_range=(1, 4),
        content_style="formal",
    ),
    "VOCATIONAL_EVALUATION_REPORT": TemplateHint(
        format="Vocational assessment",
        required_sections=["Background", "Testing Results", "Employability Analysis", "Recommendations"],
        common_headings=["VOCATIONAL EVALUATION REPORT"],
        page_count_range=(5, 15),
        content_style="formal",
    ),
    "TRAINING_COMPLETION_CERTIFICATE": TemplateHint(
        format="Certificate",
        required_sections=["Participant Name", "Program", "Completion Date", "Certification"],
        common_headings=["CERTIFICATE OF COMPLETION"],
        page_count_range=(1, 1),
        content_style="formal",
    ),

    # --- Surveillance ---
    "SURVEILLANCE_VIDEO": TemplateHint(
        format="Evidence log",
        required_sections=["Date", "Location", "Duration", "Description of Activity"],
        common_headings=["SURVEILLANCE VIDEO LOG"],
        page_count_range=(1, 2),
        content_style="formal",
    ),
    "SOCIAL_MEDIA_EVIDENCE": TemplateHint(
        format="Evidence compilation",
        required_sections=["Platform", "Date Range", "Screenshots Description", "Relevance"],
        common_headings=["SOCIAL MEDIA EVIDENCE REPORT"],
        page_count_range=(2, 8),
        content_style="formal",
    ),
    "ACTIVITY_DIARY_SELF_REPORTED": TemplateHint(
        format="Self-reported diary",
        required_sections=["Date Range", "Daily Activities", "Pain Levels", "Limitations"],
        common_headings=["ACTIVITY DIARY — SELF-REPORTED"],
        page_count_range=(3, 10),
        content_style="formal",
    ),

    # --- Liens ---
    "LIEN_MEDICAL_PROVIDER": TemplateHint(
        format="Lien claim",
        required_sections=["Lien Claimant", "Services Provided", "Amount Claimed", "Dates of Service"],
        common_headings=["LIEN CLAIM — MEDICAL PROVIDER"],
        page_count_range=(2, 5),
        content_style="legal",
    ),
    "LIEN_HOSPITAL": TemplateHint(
        format="Lien claim",
        required_sections=["Hospital", "Admission Dates", "Services", "Amount"],
        common_headings=["LIEN CLAIM — HOSPITAL"],
        page_count_range=(2, 5),
        content_style="legal",
    ),
    "LIEN_PHARMACY": TemplateHint(
        format="Lien claim",
        required_sections=["Pharmacy", "Prescriptions", "Amount"],
        common_headings=["LIEN CLAIM — PHARMACY"],
        page_count_range=(1, 3),
        content_style="legal",
    ),
    "LIEN_ATTORNEY_COSTS": TemplateHint(
        format="Lien claim",
        required_sections=["Attorney", "Costs Itemization", "Total"],
        common_headings=["LIEN CLAIM — ATTORNEY COSTS"],
        page_count_range=(2, 4),
        content_style="legal",
    ),
    "LIEN_AMBULANCE_TRANSPORT": TemplateHint(
        format="Lien claim",
        required_sections=["Transport Provider", "Date", "Origin/Destination", "Amount"],
        common_headings=["LIEN CLAIM — AMBULANCE TRANSPORT"],
        page_count_range=(1, 2),
        content_style="legal",
    ),
    "LIEN_SELF_PROCUREMENT_MEDICAL": TemplateHint(
        format="Lien claim",
        required_sections=["Employee", "Self-Procured Treatment", "Receipts", "Amount"],
        common_headings=["LIEN CLAIM — EMPLOYEE SELF-PROCUREMENT"],
        page_count_range=(1, 3),
        content_style="legal",
    ),
    "LIEN_EDD_OVERPAYMENT": TemplateHint(
        format="Government lien",
        required_sections=["EDD Claim", "Overpayment Calculation", "Amount"],
        common_headings=["LIEN CLAIM — EDD OVERPAYMENT"],
        page_count_range=(2, 4),
        content_style="legal",
    ),
    "LIEN_RESOLUTION": TemplateHint(
        format="Settlement agreement",
        required_sections=["Parties", "Original Amount", "Settled Amount", "Terms"],
        common_headings=["LIEN RESOLUTION AGREEMENT"],
        page_count_range=(2, 4),
        content_style="legal",
    ),
    "LIEN_DISMISSAL": TemplateHint(
        format="Court filing",
        required_sections=["Lien Claimant", "Reason for Dismissal", "Order"],
        common_headings=["ORDER OF DISMISSAL — LIEN"],
        page_count_range=(1, 2),
        content_style="legal",
    ),

    # --- Tier 1 template page-count overrides (for page-aware generation) ---
    "QME_REPORT_INITIAL": TemplateHint(
        format="Expert medical report",
        required_sections=["History", "Examination", "Impairment Rating", "Conclusions"],
        common_headings=["QUALIFIED MEDICAL EVALUATOR REPORT"],
        page_count_range=(5, 15),
        content_style="medical",
    ),
    "QME_REPORT_SUPPLEMENTAL": TemplateHint(
        format="Expert medical report",
        required_sections=["Additional Findings", "Revised Opinions"],
        common_headings=["SUPPLEMENTAL QME REPORT"],
        page_count_range=(3, 8),
        content_style="medical",
    ),
    "AME_REPORT_INITIAL": TemplateHint(
        format="Expert medical report",
        required_sections=["History", "Examination", "Impairment Rating", "Conclusions"],
        common_headings=["AGREED MEDICAL EVALUATOR REPORT"],
        page_count_range=(5, 15),
        content_style="medical",
    ),
    "DEPOSITION_TRANSCRIPT_APPLICANT": TemplateHint(
        format="Deposition transcript",
        required_sections=["Examination"],
        common_headings=["DEPOSITION OF"],
        page_count_range=(10, 30),
        content_style="legal",
    ),
    "DEPOSITION_TRANSCRIPT_DEFENSE_MEDICAL": TemplateHint(
        format="Deposition transcript",
        required_sections=["Examination"],
        common_headings=["DEPOSITION OF"],
        page_count_range=(10, 30),
        content_style="legal",
    ),
    "TREATING_PHYSICIAN_REPORT_PR2": TemplateHint(
        format="Physician progress report",
        required_sections=["Chief Complaints", "Examination", "Assessment", "Plan"],
        common_headings=["PRIMARY TREATING PHYSICIAN'S PROGRESS REPORT"],
        page_count_range=(2, 4),
        content_style="medical",
    ),
    "TREATING_PHYSICIAN_REPORT_PR4": TemplateHint(
        format="Physician final report",
        required_sections=["Chief Complaints", "Examination", "Assessment", "P&S Status", "WPI", "Future Medical"],
        common_headings=["PRIMARY TREATING PHYSICIAN'S REPORT — PERMANENT AND STATIONARY"],
        page_count_range=(3, 5),
        content_style="medical",
    ),
    "UTILIZATION_REVIEW_DECISION_REGULAR": TemplateHint(
        format="UR decision letter",
        required_sections=["Request Details", "Clinical Review", "Decision", "Rationale", "Appeal Rights"],
        common_headings=["UTILIZATION REVIEW DECISION"],
        page_count_range=(2, 4),
        content_style="medical",
    ),
    "IMR_DETERMINATION": TemplateHint(
        format="IMR determination letter",
        required_sections=["Request Details", "Clinical Evidence", "Determination", "Rationale"],
        common_headings=["INDEPENDENT MEDICAL REVIEW DETERMINATION"],
        page_count_range=(3, 5),
        content_style="medical",
    ),
    "MEDICAL_CHRONOLOGY_SUMMARY": TemplateHint(
        format="Medical timeline summary",
        required_sections=["Chronology", "Summary"],
        common_headings=["MEDICAL CHRONOLOGY"],
        page_count_range=(3, 6),
        content_style="medical",
    ),
    "SETTLEMENT_ANALYSIS_MEMO": TemplateHint(
        format="Attorney work product",
        required_sections=["Case Summary", "PD Analysis", "FMC", "Settlement Range", "Strategy"],
        common_headings=["CONFIDENTIAL — SETTLEMENT ANALYSIS MEMORANDUM"],
        page_count_range=(3, 5),
        content_style="legal",
    ),
    "COMPROMISE_AND_RELEASE_STANDARD": TemplateHint(
        format="Settlement agreement",
        required_sections=["Parties", "Terms", "Release Language", "Signatures"],
        common_headings=["COMPROMISE AND RELEASE"],
        page_count_range=(4, 8),
        content_style="legal",
    ),
    "OPERATIVE_REPORT_STANDARD": TemplateHint(
        format="Surgical report",
        required_sections=["Pre-Op Diagnosis", "Procedure", "Findings", "Post-Op"],
        common_headings=["OPERATIVE REPORT"],
        page_count_range=(2, 4),
        content_style="medical",
    ),

    # =========================================================================
    # Phase 2b: 35 new subtypes — correspondence, court, discovery, rating, summaries
    # =========================================================================

    # --- Correspondence: client/carrier/admin ---
    "RETAINER_FEE_AGREEMENT": TemplateHint(
        format="Attorney-client agreement",
        required_sections=["Attorney Information", "Fee Structure", "Scope of Representation", "Client Obligations", "Signatures"],
        common_headings=["RETAINER AGREEMENT — WORKERS' COMPENSATION"],
        page_count_range=(3, 6),
        content_style="legal",
    ),
    "CLIENT_REPORT_ANALYSIS_LETTER": TemplateHint(
        format="Attorney correspondence",
        required_sections=["Report Summary", "Key Findings", "Impact on Case", "Recommendations"],
        common_headings=["RE: ANALYSIS OF MEDICAL REPORT"],
        page_count_range=(2, 4),
        content_style="correspondence",
    ),
    "CLIENT_CASE_VALUATION_LETTER": TemplateHint(
        format="Attorney correspondence",
        required_sections=["Case Summary", "Injury Assessment", "Valuation Factors", "Estimated Range"],
        common_headings=["RE: CASE VALUATION"],
        page_count_range=(2, 4),
        content_style="correspondence",
    ),
    "CLIENT_SETTLEMENT_RECOMMENDATION": TemplateHint(
        format="Attorney correspondence",
        required_sections=["Settlement Offer", "Analysis", "Recommendation", "Next Steps"],
        common_headings=["RE: SETTLEMENT RECOMMENDATION"],
        page_count_range=(2, 4),
        content_style="correspondence",
    ),
    "CLIENT_HIPAA_AUTHORIZATION": TemplateHint(
        format="Authorization form",
        required_sections=["Patient Information", "Authorized Recipients", "Scope of Authorization", "Expiration", "Signature"],
        common_headings=["HIPAA AUTHORIZATION FOR RELEASE OF MEDICAL INFORMATION"],
        page_count_range=(1, 2),
        content_style="legal",
    ),
    "CLIENT_DECLARATION": TemplateHint(
        format="Sworn declaration",
        required_sections=["Declarant Information", "Facts", "Declaration Under Penalty of Perjury", "Signature"],
        common_headings=["DECLARATION OF"],
        page_count_range=(2, 5),
        content_style="legal",
    ),
    "NOTICE_OF_REPRESENTATION": TemplateHint(
        format="Attorney notice",
        required_sections=["Attorney Information", "Client Information", "Case Number", "Direction to Communicate"],
        common_headings=["NOTICE OF REPRESENTATION"],
        page_count_range=(1, 2),
        content_style="correspondence",
    ),
    "BENEFIT_PAYMENT_LEDGER": TemplateHint(
        format="Financial ledger",
        required_sections=["Claimant", "Benefit Type", "Payment History", "Running Total"],
        common_headings=["BENEFIT PAYMENT LEDGER"],
        page_count_range=(2, 6),
        content_style="formal",
    ),
    "CARRIER_POSITION_STATEMENT": TemplateHint(
        format="Insurance position paper",
        required_sections=["Claim Information", "Facts", "Position on Issues", "Supporting Evidence"],
        common_headings=["CARRIER POSITION STATEMENT"],
        page_count_range=(3, 8),
        content_style="legal",
    ),
    "RESERVATION_OF_RIGHTS_LETTER": TemplateHint(
        format="Insurance notice",
        required_sections=["Claim Information", "Coverage Issues", "Reservation Language", "Ongoing Investigation"],
        common_headings=["RESERVATION OF RIGHTS"],
        page_count_range=(2, 4),
        content_style="legal",
    ),
    "EAMS_CASE_SUMMARY": TemplateHint(
        format="Administrative case summary",
        required_sections=["Case Number", "Parties", "Case History", "Pending Issues", "Hearing Dates"],
        common_headings=["EAMS CASE SUMMARY"],
        page_count_range=(2, 4),
        content_style="legal",
    ),

    # --- Administrative Court ---
    "PROOF_OF_SERVICE": TemplateHint(
        format="Legal proof of service",
        required_sections=["Server Information", "Documents Served", "Method of Service", "Declaration"],
        common_headings=["PROOF OF SERVICE"],
        page_count_range=(1, 2),
        content_style="legal",
    ),
    "ANSWER_TO_APPLICATION": TemplateHint(
        format="Defense response filing",
        required_sections=["Case Information", "Responses to Allegations", "Affirmative Defenses", "Verification"],
        common_headings=["ANSWER TO APPLICATION FOR ADJUDICATION"],
        page_count_range=(3, 6),
        content_style="legal",
    ),
    "REQUEST_FOR_CONTINUANCE": TemplateHint(
        format="Court motion",
        required_sections=["Case Information", "Hearing Date", "Reason for Continuance", "Good Cause Showing"],
        common_headings=["REQUEST FOR CONTINUANCE"],
        page_count_range=(1, 3),
        content_style="legal",
    ),
    "PETITION_FOR_PENALTIES_LC_5814": TemplateHint(
        format="Petition for statutory penalties",
        required_sections=["Case Information", "Benefits Owed", "Delay/Denial History", "Penalty Calculation", "Prayer"],
        common_headings=["PETITION FOR PENALTIES PURSUANT TO LABOR CODE SECTION 5814"],
        page_count_range=(3, 6),
        content_style="legal",
    ),
    "ATTORNEY_FEE_PETITION": TemplateHint(
        format="Attorney fee petition",
        required_sections=["Case Information", "Fee Agreement", "Services Rendered", "Fee Calculation", "Prayer"],
        common_headings=["PETITION FOR ATTORNEY'S FEES"],
        page_count_range=(2, 5),
        content_style="legal",
    ),
    "JOINT_PRETRIAL_CONFERENCE_STATEMENT": TemplateHint(
        format="Joint conference statement",
        required_sections=["Parties", "Issues in Dispute", "Stipulations", "Exhibits", "Witnesses", "Time Estimate"],
        common_headings=["JOINT PRE-TRIAL CONFERENCE STATEMENT"],
        page_count_range=(4, 10),
        content_style="legal",
    ),
    "EXHIBIT_LIST": TemplateHint(
        format="Court exhibit listing",
        required_sections=["Case Information", "Exhibit Number", "Description", "Date", "Pages"],
        common_headings=["EXHIBIT LIST"],
        page_count_range=(1, 4),
        content_style="legal",
    ),
    "WITNESS_LIST": TemplateHint(
        format="Court witness listing",
        required_sections=["Case Information", "Witness Name", "Topic", "Estimated Time"],
        common_headings=["WITNESS LIST"],
        page_count_range=(1, 2),
        content_style="legal",
    ),

    # --- Letters / Routine Correspondence ---
    "OBJECTION_TO_QME_AME_REPORT": TemplateHint(
        format="Attorney objection letter",
        required_sections=["Report Identification", "Specific Objections", "Supporting Authority", "Request for Correction"],
        common_headings=["OBJECTION TO QME/AME REPORT"],
        page_count_range=(2, 5),
        content_style="legal",
    ),
    "REQUEST_SUPPLEMENTAL_QME_AME_REPORT": TemplateHint(
        format="Attorney request letter",
        required_sections=["Report Identification", "Additional Questions", "New Medical Records", "Request"],
        common_headings=["REQUEST FOR SUPPLEMENTAL QME/AME REPORT"],
        page_count_range=(2, 4),
        content_style="correspondence",
    ),
    "QME_PANEL_STRIKE_LETTER": TemplateHint(
        format="Panel strike notification",
        required_sections=["Panel Information", "Strike Selection", "Remaining Physician", "Scheduling"],
        common_headings=["QME PANEL STRIKE LETTER"],
        page_count_range=(1, 2),
        content_style="correspondence",
    ),
    "PTP_REFERRAL_LETTER": TemplateHint(
        format="Physician referral letter",
        required_sections=["Patient Information", "Injury History", "Current Treatment", "Referral Request"],
        common_headings=["REFERRAL TO PRIMARY TREATING PHYSICIAN"],
        page_count_range=(1, 3),
        content_style="medical",
    ),

    # --- Discovery ---
    "INTERROGATORIES_SPECIAL": TemplateHint(
        format="Discovery interrogatories",
        required_sections=["Propounding Party", "Responding Party", "Instructions", "Interrogatories"],
        common_headings=["SPECIAL INTERROGATORIES"],
        page_count_range=(3, 8),
        content_style="legal",
    ),
    "INTERROGATORY_RESPONSES": TemplateHint(
        format="Discovery responses",
        required_sections=["Responding Party", "Verification", "Responses"],
        common_headings=["RESPONSES TO SPECIAL INTERROGATORIES"],
        page_count_range=(4, 12),
        content_style="legal",
    ),
    "REQUEST_FOR_PRODUCTION": TemplateHint(
        format="Discovery request",
        required_sections=["Propounding Party", "Responding Party", "Instructions", "Document Requests"],
        common_headings=["REQUEST FOR PRODUCTION OF DOCUMENTS"],
        page_count_range=(3, 8),
        content_style="legal",
    ),
    "PRODUCTION_RESPONSES": TemplateHint(
        format="Discovery responses",
        required_sections=["Responding Party", "Verification", "Responses", "Privilege Log"],
        common_headings=["RESPONSES TO REQUEST FOR PRODUCTION OF DOCUMENTS"],
        page_count_range=(3, 10),
        content_style="legal",
    ),
    "DEPOSITION_TRANSCRIPT_QME_AME": TemplateHint(
        format="Deposition transcript",
        required_sections=["Examination"],
        common_headings=["DEPOSITION OF"],
        page_count_range=(15, 40),
        content_style="legal",
    ),

    # --- Rating / RTW Aids ---
    "TD_RATE_CALCULATION_NOTICE": TemplateHint(
        format="Benefit calculation notice",
        required_sections=["Claimant", "Earnings Data", "Rate Calculation", "Weekly TD Rate"],
        common_headings=["TEMPORARY DISABILITY RATE CALCULATION"],
        page_count_range=(1, 2),
        content_style="formal",
    ),
    "NOTICE_OF_TD_TERMINATION": TemplateHint(
        format="Claims administration notice",
        required_sections=["Claimant", "TD Period", "Reason for Termination", "Appeal Rights"],
        common_headings=["NOTICE OF TERMINATION OF TEMPORARY DISABILITY BENEFITS"],
        page_count_range=(1, 2),
        content_style="formal",
    ),
    "RETURN_TO_WORK_REPORT": TemplateHint(
        format="Employment report",
        required_sections=["Employee", "Return Date", "Work Capacity", "Restrictions", "Accommodations"],
        common_headings=["RETURN TO WORK REPORT"],
        page_count_range=(2, 4),
        content_style="formal",
    ),
    "MILEAGE_REIMBURSEMENT_REQUEST": TemplateHint(
        format="Reimbursement form",
        required_sections=["Claimant", "Trip Details", "Mileage Calculation", "Total Amount"],
        common_headings=["MILEAGE REIMBURSEMENT REQUEST"],
        page_count_range=(1, 2),
        content_style="formal",
    ),
    "INFORMAL_PD_RATING_PRINTOUT": TemplateHint(
        format="Rating computation printout",
        required_sections=["WPI", "Body Part", "FEC Adjustments", "Age/Occupation", "Final PD Percentage"],
        common_headings=["INFORMAL PERMANENT DISABILITY RATING"],
        page_count_range=(1, 3),
        content_style="legal",
    ),

    # --- Summaries / Chronologies ---
    "MSA_ALLOCATION_REPORT": TemplateHint(
        format="Medicare Set-Aside allocation report",
        required_sections=["Claimant Information", "Medical History", "Future Treatment Needs", "Cost Projections", "MSA Amount"],
        common_headings=["MEDICARE SET-ASIDE ALLOCATION REPORT"],
        page_count_range=(8, 20),
        content_style="formal",
    ),
    "CMS_CONDITIONAL_PAYMENT_LETTER": TemplateHint(
        format="CMS conditional payment notice",
        required_sections=["Claimant", "Medicare Payments", "Conditional Payment Amount", "Reimbursement Demand"],
        common_headings=["CMS CONDITIONAL PAYMENT LETTER"],
        page_count_range=(2, 5),
        content_style="formal",
    ),
}


def get_hint(subtype: str) -> TemplateHint:
    """Get template hints for a subtype, with sensible defaults."""
    return TEMPLATE_HINTS.get(subtype, TemplateHint())
