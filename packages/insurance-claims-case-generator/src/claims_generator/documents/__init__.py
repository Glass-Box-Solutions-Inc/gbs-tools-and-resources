"""
Document generation package — reportlab-based PDF generators for all 25 DocumentType values.

Tier A: Form-accurate (DWC-1, UB-04, CMS-1500, Form 105/DEU)
Tier B: Structured layout (medical reports, WCAB filings, settlement docs, etc.)
Tier C: Plain letterhead (benefit notices, correspondence, payment records, etc.)

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from claims_generator.documents.registry import DocumentRegistry, register_document

__all__ = ["DocumentRegistry", "register_document"]
