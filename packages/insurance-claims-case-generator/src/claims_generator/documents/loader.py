"""
Document loader — imports all document generators to populate the registry.

Import this module once at startup to ensure all @register_document decorators
are executed and all DocumentType values are registered in DocumentRegistry.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

# Tier C — plain letterhead
# Tier B — structured layout
# Tier A — form-accurate approximations
from claims_generator.documents import (
    ame_qme_report,  # noqa: F401
    benefit_notice,  # noqa: F401
    billing_statement,  # noqa: F401
    claim_administration,  # noqa: F401
    correspondence,  # noqa: F401
    deposition_transcript,  # noqa: F401
    discovery_request,  # noqa: F401
    dwc1_claim_form,  # noqa: F401
    dwc_official_form,  # noqa: F401
    employer_report,  # noqa: F401
    imaging_report,  # noqa: F401
    investigation_report,  # noqa: F401
    legal_correspondence,  # noqa: F401
    lien_claim,  # noqa: F401
    medical_chronology,  # noqa: F401
    medical_report,  # noqa: F401
    other_document,  # noqa: F401
    payment_record,  # noqa: F401
    pharmacy_record,  # noqa: F401
    return_to_work,  # noqa: F401
    settlement_document,  # noqa: F401
    utilization_review,  # noqa: F401
    wage_statement,  # noqa: F401
    wcab_filing,  # noqa: F401
    work_product,  # noqa: F401
)
