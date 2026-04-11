"""
Format assignment for generated documents.

Maps DocumentSubtype values to output formats (pdf, eml, docx, scanned_pdf)
using probability tables derived from real CA Workers' Compensation case file
composition: ~10-15% email, ~15-20% Word drafts, ~35-40% scanned PDF, ~20-25%
native PDF.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from data.models import OutputFormat


# ---------------------------------------------------------------------------
# Format rules — (format_value, probability)
# If probability < 1.0: that probability routes to the listed format;
# remaining probability routes to native PDF.
# If a subtype is absent from this map it always gets native PDF.
# ---------------------------------------------------------------------------

# Email correspondence — 50% probability
_EMAIL_SUBTYPES: frozenset[str] = frozenset({
    "ADJUSTER_LETTER_INFORMATIONAL",
    "ADJUSTER_LETTER_REQUEST",
    "ADJUSTER_LETTER",
    "DEFENSE_COUNSEL_LETTER_INFORMATIONAL",
    "DEFENSE_COUNSEL_LETTER_DEMAND",
    "DEFENSE_COUNSEL_LETTER",
    "CLIENT_CORRESPONDENCE_INFORMATIONAL",
    "CLIENT_CORRESPONDENCE_REQUEST",
    "CLIENT_STATUS_LETTERS",
    "ADVOCACY_LETTERS_PTP",
    "ADVOCACY_LETTERS_QME",
    "ADVOCACY_LETTERS_AME",
    "ADVOCACY_LETTERS_PTP_QME_AME",
    "SETTLEMENT_DEMAND_LETTER",
    "QME_PANEL_STRIKE_LETTER",
    "CLIENT_REPORT_ANALYSIS_LETTER",
    "CLIENT_SETTLEMENT_RECOMMENDATION",
    "CLIENT_CASE_VALUATION_LETTER",
    "PTP_REFERRAL_LETTER",
})
_EMAIL_PROBABILITY = 0.50

# Word work product — 100% probability
_DOCX_SUBTYPES: frozenset[str] = frozenset({
    "SETTLEMENT_VALUATION_MEMO",
    "CASE_ANALYSIS_MEMO",
    "TRIAL_BRIEF",
    "DEFENSE_TRIAL_BRIEF",
    "MEDICAL_CHRONOLOGY_TIMELINE",
    "DEPOSITION_SUMMARY",
    "SETTLEMENT_CONFERENCE_STATEMENT",
    "PRETRIAL_CONFERENCE_STATEMENT",
    "PRETRIAL_CONFERENCE_STATEMENT_LIEN",
    "JOINT_PRETRIAL_CONFERENCE_STATEMENT",
})

# Scanned PDF — medical / external records — 60% probability
_SCANNED_SUBTYPES: frozenset[str] = frozenset({
    "TREATING_PHYSICIAN_REPORT_PR2",
    "TREATING_PHYSICIAN_REPORT_PR4",
    "TREATING_PHYSICIAN_REPORT_FINAL",
    "TREATING_PHYSICIAN_REPORT",
    "DIAGNOSTICS_IMAGING",
    "DIAGNOSTICS_LAB_RESULTS",
    "OPERATIVE_HOSPITAL_RECORDS",
    "DISCHARGE_SUMMARY",
    "ACUTE_CARE_HOSPITAL_RECORDS",
    "EMERGENCY_ROOM_RECORDS",
    "PHARMACY_RECORDS",
    "SUBPOENAED_RECORDS_MEDICAL",
    "SUBPOENAED_RECORDS_EMPLOYMENT",
    "SUBPOENAED_RECORDS_OTHER",
    "SUBPOENAED_RECORDS",
    "PERSONNEL_FILES",
    "WAGE_STATEMENTS_PRE_INJURY",
    "WAGE_STATEMENTS_POST_INJURY",
    "WAGE_STATEMENTS_EARNING_RECORDS",
})
_SCANNED_PROBABILITY = 0.60

# Always scanned — these are intrinsically scan-origin documents
_ALWAYS_SCANNED_SUBTYPES: frozenset[str] = frozenset({
    "FAX_CORRESPONDENCE",
    "FAX_COVER_SHEET",
    "BLANK_SCANNED_PAGE",
})


def assign_output_format(subtype: str, rng: random.Random) -> "OutputFormat":
    """Return the OutputFormat for a given document subtype.

    Assignment is probabilistic for email and scanned-PDF categories so the
    resulting case file has a realistic mix of formats.  Word work-product and
    native-PDF documents are always deterministic.

    Args:
        subtype: DocumentSubtype value string (e.g. "ADJUSTER_LETTER_INFORMATIONAL").
        rng: Seeded Random instance so output is reproducible given the same seed.

    Returns:
        OutputFormat enum member.
    """
    # Import here to avoid circular import at module load time
    from data.models import OutputFormat

    if subtype in _ALWAYS_SCANNED_SUBTYPES:
        return OutputFormat.SCANNED_PDF

    if subtype in _DOCX_SUBTYPES:
        return OutputFormat.DOCX

    if subtype in _EMAIL_SUBTYPES:
        return OutputFormat.EML if rng.random() < _EMAIL_PROBABILITY else OutputFormat.PDF

    if subtype in _SCANNED_SUBTYPES:
        return OutputFormat.SCANNED_PDF if rng.random() < _SCANNED_PROBABILITY else OutputFormat.PDF

    return OutputFormat.PDF
