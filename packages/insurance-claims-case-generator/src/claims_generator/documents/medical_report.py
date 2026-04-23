"""
MEDICAL_REPORT document generator — Tier B structured layout.

Covers: PR-2 treating physician reports, progress reports, P&S (permanent and stationary).
Form identifiers: PR-2 (treating physician), PR-3, PR-4.
Regulatory basis:
  - 8 CCR 9785: Treating physician reporting duties
  - 8 CCR 9792.6: MTUS compliance for treatment requests
  - LC § 4061: Objection to treating physician's report

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import io

from claims_generator.documents.base_document import DocumentGenerator
from claims_generator.documents.letterhead import (
    carrier_header_block,
    claimant_caption_block,
    confidentiality_footer,
    regulatory_citation_block,
)
from claims_generator.documents.pdf_primitives import (
    hline,
    label_value_table,
    para,
    section_table,
    spacer,
    thick_hline,
    two_col_section,
)
from claims_generator.documents.registry import register_document
from claims_generator.models.claim import DocumentEvent
from claims_generator.models.enums import DocumentType
from claims_generator.models.profile import ClaimProfile


@register_document
class MedicalReportGenerator(DocumentGenerator):
    """Tier B — treating physician medical reports (PR-2, progress, P&S)."""

    handles = frozenset({DocumentType.MEDICAL_REPORT})

    @classmethod
    def generate(cls, event: DocumentEvent, profile: ClaimProfile) -> bytes:
        buf = io.BytesIO()

        slug = event.subtype_slug
        if "ps" in slug or "permanent" in slug or "stationary" in slug:
            form_id = "PR-4 (P&S Report)"
        elif "progress" in slug:
            form_id = "PR-3 (Progress Report)"
        else:
            form_id = "PR-2 (Primary Treating Physician Report)"

        doc = cls._build_doc(buf, title=event.title)

        med = profile.medical
        ins = profile.insurer
        claimant = profile.claimant

        treating = med.treating_physician
        body_parts_str = ", ".join(
            f"{bp.body_part}{' (' + bp.laterality + ')' if bp.laterality else ''}"
            for bp in med.body_parts
        )
        icd_rows = [
            [e.code, e.description, e.body_part]
            for e in med.icd10_codes
        ]

        story: list = []
        story.extend(carrier_header_block(profile, form_id=form_id))
        story.append(spacer(4))
        story.append(para(f"MEDICAL REPORT — {form_id}", "title"))
        story.append(para("State of California — Division of Workers' Compensation", "subtitle"))
        story.append(thick_hline())

        story.extend(
            claimant_caption_block(
                profile,
                event_date=event.event_date,
                event_title=event.title,
            )
        )

        # Section 1: Physician information
        story.append(para("SECTION 1: TREATING PHYSICIAN INFORMATION", "heading1"))
        story.append(hline())
        story.append(
            two_col_section(
                left_items=[
                    ("Physician", f"Dr. {treating.first_name} {treating.last_name}"),
                    ("Specialty", treating.specialty),
                    ("License No.", treating.license_number),
                ],
                right_items=[
                    ("NPI", treating.npi),
                    ("City", treating.address_city),
                    ("Date of Report", str(event.event_date)),
                ],
            )
        )

        # Section 2: Diagnoses
        story.append(spacer(6))
        story.append(para("SECTION 2: DIAGNOSIS AND BODY PARTS", "heading1"))
        story.append(hline())
        story.append(
            label_value_table([
                ("Primary Body Parts:", body_parts_str),
                ("Mechanism of Injury:", med.injury_mechanism),
                ("Date of Injury (DOI):", med.date_of_injury),
            ])
        )
        story.append(spacer(4))
        if icd_rows:
            story.append(para("ICD-10 Diagnoses:", "heading2"))
            story.append(
                section_table(
                    headers=["ICD-10 Code", "Description", "Body Part"],
                    rows=icd_rows,
                )
            )

        # Section 3: Treatment / Status
        story.append(spacer(6))
        story.append(para("SECTION 3: TREATMENT STATUS", "heading1"))
        story.append(hline())

        if "ps" in slug or "permanent" in slug:
            # Permanent and Stationary
            wpi = f"{med.wpi_percent:.1f}%" if med.wpi_percent else "Pending formal rating"
            story.append(
                label_value_table([
                    ("P&S Status:", "PERMANENT AND STATIONARY (MMI REACHED)"),
                    ("Date P&S:", str(event.event_date)),
                    ("WPI (Whole Person Impairment):", wpi),
                    ("Future Medical Care:", "None indicated" if not med.has_surgery else "Follow-up as needed"),
                    ("Work Restrictions:", "Modified duty per attached work restriction form"),
                    ("Apportionment:", "Subject to formal apportionment per LC § 4663"),
                    ("Rating Method:", "AMA Guides 5th Edition (LC § 4660)"),
                ])
            )
            story.append(spacer(4))
            story.append(
                para(
                    "The patient has reached Maximum Medical Improvement (MMI) and is Permanent "
                    "and Stationary (P&S) as of the date of this report. No further improvement "
                    "is expected with or without additional medical treatment. This report is "
                    "submitted pursuant to 8 CCR 9785(f) for final rating by the DEU.",
                    "body",
                )
            )
        else:
            # Progress / PR-2
            story.append(
                label_value_table([
                    ("Current Status:", "Active Treatment — NOT Permanent & Stationary"),
                    ("Work Status:", "Temporary Total Disability (TD)" if "pr2" in slug else "Modified Duty"),
                    ("Next Appointment:", "4 weeks"),
                    ("Treatment Plan:", "Per MTUS guidelines (8 CCR 9792.6)"),
                    ("Surgery:", "Recommended" if med.has_surgery else "Not indicated"),
                    ("Referrals:", "Orthopedic specialist" if len(med.body_parts) > 1 else "None at this time"),
                    ("MMI Expected:", "Not yet reached"),
                ])
            )
            if med.has_surgery and med.surgery_description:
                story.append(spacer(4))
                story.append(para("SURGICAL RECOMMENDATION:", "heading2"))
                story.append(para(med.surgery_description, "body"))

        # Section 4: Regulatory compliance
        story.append(spacer(6))
        story.append(para("SECTION 4: REGULATORY COMPLIANCE", "heading1"))
        story.append(hline())
        story.append(
            para(
                "This report is submitted pursuant to 8 CCR 9785 (treating physician reporting "
                "requirements). Treatment provided is consistent with MTUS guidelines per 8 CCR "
                "9792.6. Requests for authorization of additional treatment have been or will be "
                "submitted via the Request for Authorization (RFA) process per 8 CCR 9792.6.",
                "body",
            )
        )

        story.extend(
            regulatory_citation_block([
                "8 CCR 9785", "8 CCR 9792.6", "LC § 4600", "AMA Guides 5th Ed.", "LC § 4663"
            ])
        )
        story.extend(confidentiality_footer())
        doc.build(story)
        return buf.getvalue()
