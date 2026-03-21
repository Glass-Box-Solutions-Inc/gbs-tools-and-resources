"""
Backward-compatibility mapping from old 27-subtype enum to new 188-subtype taxonomy.

The original DocumentSubtype enum in models.py used simplified names. This module
maps those names to the canonical classifier taxonomy names so that legacy code
(and the 20 hardcoded case profiles) continues to work.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

# Old enum value → new canonical subtype(s)
# When the old name maps to a generic parent, we pick the most common specific variant.
LEGACY_TO_CANONICAL: dict[str, str] = {
    # Medical
    "TREATING_PHYSICIAN_REPORT": "TREATING_PHYSICIAN_REPORT_PR2",
    "DIAGNOSTIC_REPORT": "DIAGNOSTICS_IMAGING",
    "OPERATIVE_HOSPITAL_RECORDS": "OPERATIVE_HOSPITAL_RECORDS",
    "QME_AME_REPORT": "QME_REPORT_INITIAL",
    "UTILIZATION_REVIEW": "UTILIZATION_REVIEW_DECISION_REGULAR",
    "PHARMACY_RECORDS": "PHARMACY_RECORDS",
    "BILLING_UB04_HCFA_SUPERBILLS": "BILLING_UB04_HCFA_SUPERBILLS",

    # Legal
    "APPLICATION_FOR_ADJUDICATION": "APPLICATION_FOR_ADJUDICATION_ORIGINAL",
    "DECLARATION_OF_READINESS": "DECLARATION_OF_READINESS_REGULAR",
    "MINUTES_ORDERS_FINDINGS": "MINUTES_ORDERS_FINDINGS_AWARD",
    "STIPULATIONS": "STIPULATIONS_WITH_REQUEST_FOR_AWARD",
    "COMPROMISE_AND_RELEASE": "COMPROMISE_AND_RELEASE_STANDARD",

    # Correspondence
    "ADJUSTER_LETTER": "ADJUSTER_LETTER_INFORMATIONAL",
    "DEFENSE_COUNSEL_LETTER": "DEFENSE_COUNSEL_LETTER_INFORMATIONAL",
    "COURT_NOTICE": "NOTICE_OF_HEARING_COURT_ISSUED",
    "CLIENT_INTAKE_CORRESPONDENCE": "CLIENT_INTAKE_CORRESPONDENCE",

    # Discovery
    "SUBPOENA_SDT_ISSUED": "SUBPOENA_SDT_ISSUED",
    "DEPOSITION_NOTICE": "DEPOSITION_NOTICE_APPLICANT",
    "DEPOSITION_TRANSCRIPT": "DEPOSITION_TRANSCRIPT",
    "SUBPOENAED_RECORDS": "SUBPOENAED_RECORDS_MEDICAL",

    # Employment
    "WAGE_STATEMENTS": "WAGE_STATEMENTS_PRE_INJURY",
    "JOB_DESCRIPTION": "JOB_DESCRIPTION_PRE_INJURY",
    "PERSONNEL_FILE": "PERSONNEL_FILES",

    # Claim forms
    "CLAIM_FORM": "CLAIM_FORM_DWC1",
    "EMPLOYER_REPORT": "EMPLOYER_REPORT_INJURY",

    # Summaries
    "MEDICAL_CHRONOLOGY": "MEDICAL_CHRONOLOGY_TIMELINE",
    "SETTLEMENT_MEMO": "SETTLEMENT_VALUATION_MEMO",
}

# Reverse: canonical → legacy (for display compatibility)
CANONICAL_TO_LEGACY: dict[str, str] = {v: k for k, v in LEGACY_TO_CANONICAL.items()}


def resolve_legacy_subtype(legacy_name: str) -> str:
    """Convert a legacy subtype name to its canonical equivalent.

    If the name is already canonical (exists in the 188-taxonomy), returns it unchanged.
    """
    from data.taxonomy import DocumentSubtype

    # Already canonical?
    try:
        DocumentSubtype(legacy_name)
        return legacy_name
    except ValueError:
        pass

    # Try legacy mapping
    canonical = LEGACY_TO_CANONICAL.get(legacy_name)
    if canonical:
        return canonical

    raise ValueError(
        f"Unknown subtype '{legacy_name}' — not in legacy or canonical taxonomy"
    )
