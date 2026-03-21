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
}


def get_hint(subtype: str) -> TemplateHint:
    """Get template hints for a subtype, with sensible defaults."""
    return TEMPLATE_HINTS.get(subtype, TemplateHint())
