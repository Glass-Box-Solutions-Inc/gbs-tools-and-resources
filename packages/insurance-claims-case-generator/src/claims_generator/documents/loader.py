"""
Document loader — imports all document generators to populate the registry.

Import this module once at startup to ensure all @register_document decorators
are executed and all DocumentType values are registered in DocumentRegistry.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

# Tier C — plain letterhead
from claims_generator.documents import benefit_notice  # noqa: F401
from claims_generator.documents import claim_administration  # noqa: F401
from claims_generator.documents import correspondence  # noqa: F401
from claims_generator.documents import employer_report  # noqa: F401
from claims_generator.documents import imaging_report  # noqa: F401
from claims_generator.documents import legal_correspondence  # noqa: F401
from claims_generator.documents import other_document  # noqa: F401
from claims_generator.documents import payment_record  # noqa: F401
from claims_generator.documents import pharmacy_record  # noqa: F401
from claims_generator.documents import wage_statement  # noqa: F401

# Tier B — structured layout
from claims_generator.documents import ame_qme_report  # noqa: F401
from claims_generator.documents import billing_statement  # noqa: F401
from claims_generator.documents import deposition_transcript  # noqa: F401
from claims_generator.documents import discovery_request  # noqa: F401
from claims_generator.documents import investigation_report  # noqa: F401
from claims_generator.documents import lien_claim  # noqa: F401
from claims_generator.documents import medical_chronology  # noqa: F401
from claims_generator.documents import medical_report  # noqa: F401
from claims_generator.documents import return_to_work  # noqa: F401
from claims_generator.documents import settlement_document  # noqa: F401
from claims_generator.documents import utilization_review  # noqa: F401
from claims_generator.documents import wcab_filing  # noqa: F401
from claims_generator.documents import work_product  # noqa: F401

# Tier A — form-accurate approximations
from claims_generator.documents import dwc1_claim_form  # noqa: F401
from claims_generator.documents import dwc_official_form  # noqa: F401
