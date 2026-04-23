"""
DocumentType enum — mirrors AdjudiCLAIMS prisma/schema.prisma EXACTLY.

25 values. Any change here MUST be reflected in the Prisma schema and vice versa.
Do NOT reorder, rename, or add values without updating schema.prisma first.

Source: AdjudiCLAIMS-ai-app/prisma/schema.prisma  enum DocumentType { ... }

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from enum import Enum


class DocumentType(str, Enum):
    """Document type classification — exact mirror of Prisma DocumentType enum."""

    DWC1_CLAIM_FORM = "DWC1_CLAIM_FORM"
    MEDICAL_REPORT = "MEDICAL_REPORT"
    BILLING_STATEMENT = "BILLING_STATEMENT"
    LEGAL_CORRESPONDENCE = "LEGAL_CORRESPONDENCE"
    EMPLOYER_REPORT = "EMPLOYER_REPORT"
    INVESTIGATION_REPORT = "INVESTIGATION_REPORT"
    UTILIZATION_REVIEW = "UTILIZATION_REVIEW"
    AME_QME_REPORT = "AME_QME_REPORT"
    DEPOSITION_TRANSCRIPT = "DEPOSITION_TRANSCRIPT"
    IMAGING_REPORT = "IMAGING_REPORT"
    PHARMACY_RECORD = "PHARMACY_RECORD"
    WAGE_STATEMENT = "WAGE_STATEMENT"
    BENEFIT_NOTICE = "BENEFIT_NOTICE"
    SETTLEMENT_DOCUMENT = "SETTLEMENT_DOCUMENT"
    CORRESPONDENCE = "CORRESPONDENCE"
    OTHER = "OTHER"
    WCAB_FILING = "WCAB_FILING"
    LIEN_CLAIM = "LIEN_CLAIM"
    DISCOVERY_REQUEST = "DISCOVERY_REQUEST"
    RETURN_TO_WORK = "RETURN_TO_WORK"
    PAYMENT_RECORD = "PAYMENT_RECORD"
    DWC_OFFICIAL_FORM = "DWC_OFFICIAL_FORM"
    WORK_PRODUCT = "WORK_PRODUCT"
    MEDICAL_CHRONOLOGY = "MEDICAL_CHRONOLOGY"
    CLAIM_ADMINISTRATION = "CLAIM_ADMINISTRATION"
