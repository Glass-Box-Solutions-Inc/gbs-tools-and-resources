"""
BILLING_STATEMENT_FORMS — Tier A form-accurate approximations for UB-04 and CMS-1500.

NOTE: PNG blank forms are NOT available in assets/. These generators use
reportlab table layout closely approximating the official form box structure.
Logged to ISSUES.md as a backlog item for future PNG overlay support.

UB-04: NUBC uniform billing form (institutional — hospitals, ASCs)
CMS-1500: Standard professional billing form (physicians)

References:
  - NUBC UB-04 Data Specifications Manual
  - CMS-1500 (02/12) form instructions
  - 8 CCR 9789.10: OMFS fee schedule
  - 8 CCR 9789.20: Outpatient surgery fee schedule

This module re-uses the BILLING_STATEMENT DocumentType since UB-04 and CMS-1500
are subtypes of billing; they are included as a subtype-routing path within the
BillingStatementFormsGenerator.

The main BillingStatementGenerator (billing_statement.py) handles generic WC
billing. This module registers an ADDITIONAL handler that, if imported, overrides
billing_statement.py. To avoid registry conflicts, this module extends the
generic generator rather than re-registering — it is invoked from
billing_statement.py via subtype routing.

IMPORTANT: Do not import this module from registry auto-loading — it is imported
by billing_statement.py directly for subtype dispatch.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import io

from reportlab.lib.units import inch

from claims_generator.documents.form_renderer import (
    form_row,
    form_section_header,
)
from claims_generator.documents.letterhead import (
    confidentiality_footer,
    regulatory_citation_block,
)
from claims_generator.documents.pdf_primitives import (
    CONTENT_WIDTH,
    para,
    spacer,
    thick_hline,
)
from claims_generator.models.claim import DocumentEvent
from claims_generator.models.profile import ClaimProfile


def generate_cms1500(event: DocumentEvent, profile: ClaimProfile) -> bytes:
    """
    Generate CMS-1500 (02/12) professional billing form approximation.
    Used for physician / professional billing in WC context.
    """

    buf = io.BytesIO()
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate

    doc = SimpleDocTemplate(buf, pagesize=letter,
                            leftMargin=0.5 * inch, rightMargin=0.5 * inch,
                            topMargin=0.5 * inch, bottomMargin=0.5 * inch)

    c = profile.claimant
    ins = profile.insurer
    med = profile.medical
    treating = med.treating_physician

    col_q = CONTENT_WIDTH / 4
    col_h = CONTENT_WIDTH / 2
    col_t = CONTENT_WIDTH / 3

    story: list = []
    story.append(para("<b>HEALTH INSURANCE CLAIM FORM</b>", "title"))
    story.append(para("CMS-1500 (02/12) | APPROVED BY NATIONAL UNIFORM CLAIM COMMITTEE | Workers' Compensation", "small"))  # noqa: E501
    story.append(thick_hline())

    # Box 1: Insurance type
    story.append(form_section_header("1. INSURANCE TYPE"))
    story.append(form_row([
        ("1. Insurance Type:", "X  WORKERS' COMP", CONTENT_WIDTH),
    ]))
    story.append(spacer(2))

    # Patient info
    story.append(form_section_header("PATIENT AND INSURED INFORMATION"))
    story.append(form_row([
        ("2. Patient's Name (Last, First, MI):", f"{c.last_name}, {c.first_name}", col_h),
        ("3. Patient's DOB:", str(c.date_of_birth), col_q),
        ("4. Sex:", c.gender, col_q),
    ]))
    story.append(spacer(1))
    story.append(form_row([
        ("5. Patient Address:", f"{c.address_city}, CA {c.address_zip}", col_h),
        ("6. Patient Relationship:", "Self", col_q),
        ("7. Insured's ID No.:", ins.claim_number, col_q),
    ]))
    story.append(spacer(2))

    # Condition
    story.append(form_section_header("CONDITION RELATED TO"))
    story.append(form_row([
        ("10a. Condition related to EMPLOYMENT?", "X YES", col_t),
        ("10b. Related to AUTO?", "NO", col_t),
        ("10c. Related to OTHER?", "NO", col_t),
    ]))
    story.append(spacer(2))

    # Diagnosis
    story.append(form_section_header("DIAGNOSIS / NATURE OF ILLNESS OR INJURY (ICD-10-CM)"))
    icd_entries = med.icd10_codes[:4]
    diag_fields = []
    for i, icd in enumerate(icd_entries):
        diag_fields.append((f"{chr(65+i)}.", f"{icd.code}", col_q))
    while len(diag_fields) < 4:
        diag_fields.append((f"{chr(65+len(diag_fields))}.", "", col_q))
    story.append(form_row(diag_fields))
    story.append(spacer(2))

    # Service lines (Box 24)
    story.append(form_section_header("24. SERVICE LINE DETAIL"))
    story.append(form_row([
        ("A. DOS:", str(event.event_date), col_q),
        ("B. POS:", "11 (Office)", col_q * 0.8),
        ("D. CPT Code:", "99213", col_q * 0.8),
        ("E. Diagnosis Ptr:", "A", col_q * 0.5),
        ("F. $ Charges:", "$160.51", col_q * 0.8),
        ("G. Days:", "1", col_q * 0.4),
        ("J. NPI:", treating.npi, CONTENT_WIDTH - col_q - col_q*0.8*2 - col_q*0.5 - col_q*0.4),
    ]))
    story.append(spacer(2))

    # Totals
    story.append(form_section_header("TOTALS"))
    story.append(form_row([
        ("28. Total Charge:", "$160.51", col_t),
        ("29. Amount Paid:", "$0.00", col_t),
        ("30. Rsvd for NUCC Use:", "", col_t),
    ]))
    story.append(spacer(2))

    # Physician info
    story.append(form_section_header("PHYSICIAN OR SUPPLIER INFORMATION"))
    story.append(form_row([
        ("31. Signature:", f"Dr. {treating.last_name}", col_h),
        ("32. Service Facility:", f"{treating.address_city}, CA", col_h),
    ]))
    story.append(spacer(1))
    story.append(form_row([
        ("33. Billing Provider:", f"Dr. {treating.first_name} {treating.last_name}", col_h),
        ("33a. NPI:", treating.npi, col_h),
    ]))

    story.extend(regulatory_citation_block(["8 CCR 9789.10", "CMS-1500 (02/12)"]))
    story.extend(confidentiality_footer())
    doc.build(story)
    return buf.getvalue()


def generate_ub04(event: DocumentEvent, profile: ClaimProfile) -> bytes:
    """
    Generate UB-04 institutional billing form approximation.
    Used for hospital and ASC billing in WC context.
    """
    buf = io.BytesIO()
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate

    doc = SimpleDocTemplate(buf, pagesize=letter,
                            leftMargin=0.5 * inch, rightMargin=0.5 * inch,
                            topMargin=0.5 * inch, bottomMargin=0.5 * inch)

    c = profile.claimant
    ins = profile.insurer
    med = profile.medical
    employer = profile.employer

    col_q = CONTENT_WIDTH / 4
    col_h = CONTENT_WIDTH / 2

    story: list = []
    story.append(para("<b>UB-04 UNIFORM BILLING CLAIM FORM</b>", "title"))
    story.append(para("NUBC UB-04 | Workers' Compensation | 8 CCR 9789.20 (ASC/Hospital)", "small"))
    story.append(thick_hline())

    story.append(form_section_header("1–3. PROVIDER INFORMATION"))
    story.append(form_row([
        ("1. Provider Name:", f"{employer.company_name} Medical Facility", col_h),
        ("2. Pay-To Address:", f"{employer.address_city}, CA", col_h),
    ]))
    story.append(spacer(1))
    story.append(form_row([
        ("3a. Patient Control No.:", ins.claim_number, col_q),
        ("3b. Medical Record No.:", f"MR-{ins.claim_number}", col_q),
        ("4. Type of Bill:", "131 (Hospital Outpatient)", col_h),
    ]))
    story.append(spacer(2))

    story.append(form_section_header("12–17. PATIENT INFORMATION"))
    story.append(form_row([
        ("12. Patient Name:", f"{c.last_name}, {c.first_name}", col_h),
        ("14. DOB:", str(c.date_of_birth), col_q),
        ("15. Sex:", c.gender, col_q),
    ]))
    story.append(spacer(1))
    story.append(form_row([
        ("17. Admission Date:", med.date_of_injury, col_q),
        ("16. Admission Hour:", "08", col_q * 0.5),
        ("18. Admission Type:", "3 (Elective)", col_h),
    ]))
    story.append(spacer(2))

    story.append(form_section_header("42–49. SERVICE LINE DETAIL"))
    story.append(form_row([
        ("42. Rev. Code:", "0450", col_q * 0.7),
        ("43. Description:", "Emergency Room", col_h),
        ("44. HCPCS:", "99283", col_q * 0.7),
        ("46. Service Units:", "1", col_q * 0.4),
        ("47. Total Charges:", "$1,248.00", col_q),
    ]))
    story.append(spacer(2))

    story.append(form_section_header("67–67Q. PRINCIPAL DIAGNOSIS"))
    icd_fields = []
    for i, icd in enumerate(med.icd10_codes[:4]):
        icd_fields.append((f"{'A' if i==0 else chr(65+i)}. ICD-10:", icd.code, col_q))
    while len(icd_fields) < 4:
        icd_fields.append((f"{chr(65+len(icd_fields))}.", "", col_q))
    story.append(form_row(icd_fields))
    story.append(spacer(2))

    story.append(form_section_header("PAYER INFORMATION"))
    story.append(form_row([
        ("Payer Name:", ins.carrier_name, col_h),
        ("Claim No.:", ins.claim_number, col_h),
    ]))

    story.extend(regulatory_citation_block(["8 CCR 9789.20", "NUBC UB-04"]))
    story.extend(confidentiality_footer())
    doc.build(story)
    return buf.getvalue()
