"""
LIEN_CLAIM document generator — Tier B structured layout.

Covers: medical provider lien claims, lien conference filings.
Regulatory basis:
  - LC § 4903: Lien claims against compensation awards
  - LC § 4903.05: Lien filing requirements
  - LC § 4903.06: Lien filing fees
  - 8 CCR 10770: Lien claimant procedures
  - 8 CCR 10770.1: Lien filing requirements

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
    section_table,
    spacer,
    thick_hline,
)
from claims_generator.documents.registry import register_document
from claims_generator.models.claim import DocumentEvent
from claims_generator.models.enums import DocumentType
from claims_generator.models.profile import ClaimProfile


@register_document
class LienClaimGenerator(DocumentGenerator):
    """Tier B — lien claim filings."""

    handles = frozenset({DocumentType.LIEN_CLAIM})

    @classmethod
    def generate(cls, event: DocumentEvent, profile: ClaimProfile) -> bytes:
        buf = io.BytesIO()
        doc = cls._build_doc(buf, title=event.title)

        ins = profile.insurer
        med = profile.medical
        claimant = profile.claimant
        treating = med.treating_physician

        # Derive lien amount from financial profile
        fin = profile.financial
        lien_amount = fin.average_weekly_wage * 2.5  # proxy for medical lien

        story: list = []
        story.extend(carrier_header_block(profile))
        story.append(spacer(4))
        story.append(para("LIEN CLAIM", "title"))
        story.append(para("LC §§ 4903, 4903.05 | 8 CCR 10770", "small"))
        story.append(thick_hline())

        story.extend(wcab_caption(profile))
        story.append(spacer(6))

        story.append(para("LIEN CLAIMANT INFORMATION", "heading1"))
        story.append(hline())
        story.append(
            label_value_table([
                ("Lien Claimant:", f"Dr. {treating.first_name} {treating.last_name} / {treating.address_city} Medical Group"),
                ("NPI:", treating.npi),
                ("License No.:", treating.license_number),
                ("Type of Lien:", "Medical Provider — LC § 4903(b)"),
                ("Filing Date:", str(event.event_date)),
                ("Claim No.:", ins.claim_number),
                ("Insurer:", ins.carrier_name),
            ])
        )

        story.append(spacer(6))
        story.append(para("CLAIMANT (INJURED WORKER) INFORMATION", "heading1"))
        story.append(hline())
        story.append(
            label_value_table([
                ("Injured Worker:", f"{claimant.first_name} {claimant.last_name}"),
                ("Date of Injury (DOI):", med.date_of_injury),
                ("Body Parts:", ", ".join(bp.body_part for bp in med.body_parts)),
                ("Employer:", profile.employer.company_name),
            ])
        )

        story.append(spacer(6))
        story.append(para("LIEN AMOUNT DETAIL", "heading1"))
        story.append(hline())
        story.append(
            section_table(
                headers=["Service Period", "Description", "Billed", "Paid", "Lien Amount"],
                rows=[
                    [
                        f"{med.date_of_injury} – {event.event_date}",
                        "Medical treatment — industrially related conditions",
                        f"${lien_amount:,.2f}",
                        "$0.00",
                        f"${lien_amount:,.2f}",
                    ]
                ],
            )
        )
        story.append(spacer(4))
        story.append(
            label_value_table([
                ("TOTAL LIEN AMOUNT:", f"${lien_amount:,.2f}"),
                ("Lien Filing Fee Paid:", "$150.00 (LC § 4903.06)"),
            ])
        )

        story.append(spacer(6))
        story.append(para("LEGAL BASIS FOR LIEN", "heading1"))
        story.append(hline())
        story.append(
            para(
                f"Lien Claimant provided medical treatment to the injured worker for conditions "
                f"arising out of and in the course of employment pursuant to LC § 3600. "
                f"The employer and/or insurance carrier failed to pay for said treatment within "
                f"the timeframes required by LC § 4603.2 and 8 CCR 9792.5.\n\n"
                f"This lien is filed pursuant to LC § 4903(b) and 8 CCR 10770.1. "
                f"Lien Claimant requests that the WCAB adjudicate this lien claim and order "
                f"payment from the compensation award in this matter.",
                "body",
            )
        )

        story.extend(
            regulatory_citation_block([
                "LC §§ 4903, 4903.05, 4903.06", "8 CCR 10770", "LC § 4603.2"
            ])
        )
        story.extend(confidentiality_footer())
        doc.build(story)
        return buf.getvalue()
