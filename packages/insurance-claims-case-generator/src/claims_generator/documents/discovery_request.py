"""
DISCOVERY_REQUEST document generator — Tier B structured layout.

Covers: Subpoena Duces Tecum, Demand for Production of Records.
Access level: DUAL_ACCESS.
Regulatory basis:
  - 8 CCR 10550: Discovery procedures
  - LC § 5710: Subpoenas and discovery
  - CCP § 1985: Subpoena form requirements
  - 8 CCR 10622: Verification of pleadings

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import io

from claims_generator.documents.base_document import DocumentGenerator
from claims_generator.documents.letterhead import (
    carrier_header_block,
    confidentiality_footer,
    regulatory_citation_block,
    wcab_caption,
)
from claims_generator.documents.pdf_primitives import (
    hline,
    label_value_table,
    para,
    spacer,
    thick_hline,
)
from claims_generator.documents.registry import register_document
from claims_generator.models.claim import DocumentEvent
from claims_generator.models.enums import DocumentType
from claims_generator.models.profile import ClaimProfile


@register_document
class DiscoveryRequestGenerator(DocumentGenerator):
    """Tier B — discovery requests (subpoena, demand for records)."""

    handles = frozenset({DocumentType.DISCOVERY_REQUEST})

    @classmethod
    def generate(cls, event: DocumentEvent, profile: ClaimProfile) -> bytes:
        buf = io.BytesIO()
        doc = cls._build_doc(buf, title=event.title)

        ins = profile.insurer
        med = profile.medical
        claimant = profile.claimant

        slug = event.subtype_slug
        is_subpoena = "subpoena" in slug

        story: list = []
        story.extend(carrier_header_block(profile))
        story.append(spacer(4))

        if is_subpoena:
            story.append(para("SUBPOENA DUCES TECUM", "title"))
            story.append(para("CCP § 1985 | LC § 5710 | 8 CCR 10550", "small"))
        else:
            story.append(para("DEMAND FOR PRODUCTION OF RECORDS", "title"))
            story.append(para("8 CCR 10550 | LC § 5710", "small"))

        story.append(thick_hline())
        story.extend(wcab_caption(profile))
        story.append(spacer(6))

        story.append(para("TO THE CUSTODIAN OF RECORDS:", "heading1"))
        story.append(hline())

        if is_subpoena:
            story.append(
                para(
                    f"YOU ARE HEREBY COMMANDED to produce and permit inspection, copying, "
                    f"testing, or sampling of the following documents relating to:<br/><br/>"
                    f"<b>Patient / Claimant:</b> {claimant.first_name} {claimant.last_name}<br/>"
                    f"<b>Date of Birth:</b> {claimant.date_of_birth}<br/>"
                    f"<b>Date(s) of Service:</b> All dates from DOI ({med.date_of_injury}) to present",  # noqa: E501
                    "body",
                )
            )
        else:
            story.append(
                para(
                    f"Pursuant to 8 CCR 10550, Defendant {ins.carrier_name} demands production "
                    f"of the following records relating to Claimant {claimant.first_name} "
                    f"{claimant.last_name} (DOB: {claimant.date_of_birth}):",
                    "body",
                )
            )

        story.append(spacer(4))
        story.append(para("RECORDS REQUESTED:", "heading2"))

        records_list = [
            "1. All medical records from any provider, from 5 years prior to DOI to present date;",
            "2. All emergency room records related to the claimed or any similar condition;",
            f"3. All records relating to the {', '.join(bp.body_part for bp in med.body_parts)};",
            "4. All diagnostic imaging films and reports (X-rays, MRI, CT scans);",
            "5. All pharmacy and prescription records;",
            "6. All prior workers' compensation claim records;",
            "7. Employment and payroll records from 3 years prior to DOI;",
            "8. All records relating to any prior injury to the claimed body parts;",
        ]

        for item in records_list:
            story.append(para(item, "body"))
            story.append(spacer(1))

        story.append(spacer(6))
        story.append(para("RESPONSE INFORMATION", "heading1"))
        story.append(hline())
        story.append(
            label_value_table([
                ("Requesting Party:", ins.carrier_name),
                ("Adjuster:", ins.adjuster_name),
                ("Email:", ins.adjuster_email),
                ("Phone:", ins.adjuster_phone),
                ("Claim No.:", ins.claim_number),
                ("Date Issued:", str(event.event_date)),
                ("Response Deadline:", "20 days from service (CCP § 1985.3)" if is_subpoena else "20 days"),  # noqa: E501
            ])
        )

        story.append(spacer(6))
        story.append(
            para(
                "HIPAA Authorization: A signed HIPAA authorization form is attached (or will "
                "be provided). Disclosure is permitted under 45 CFR 164.512(e) for workers' "
                "compensation proceedings. Compliance with this request is required by law.",
                "small",
            )
        )

        story.extend(
            regulatory_citation_block([
                "CCP § 1985", "LC § 5710", "8 CCR 10550", "45 CFR 164.512(e)"
            ])
        )
        story.extend(confidentiality_footer())
        doc.build(story)
        return buf.getvalue()
