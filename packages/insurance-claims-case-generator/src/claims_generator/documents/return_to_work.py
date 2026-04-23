"""
RETURN_TO_WORK document generator — Tier B structured layout.

Covers: SJDB (Supplemental Job Displacement Benefit) offer, modified duty offer,
return to work clearance.
Regulatory basis:
  - LC § 4658.6: Modified or alternative work offer
  - LC § 4658.7: Supplemental Job Displacement Benefit (SJDB)
  - 8 CCR 10133.53: SJDB voucher procedures
  - 8 CCR 10133.55: Benefit notice requirements

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
    spacer,
    thick_hline,
)
from claims_generator.documents.registry import register_document
from claims_generator.models.claim import DocumentEvent
from claims_generator.models.enums import DocumentType
from claims_generator.models.profile import ClaimProfile


@register_document
class ReturnToWorkGenerator(DocumentGenerator):
    """Tier B — return to work / SJDB documents."""

    handles = frozenset({DocumentType.RETURN_TO_WORK})

    @classmethod
    def generate(cls, event: DocumentEvent, profile: ClaimProfile) -> bytes:
        buf = io.BytesIO()
        doc = cls._build_doc(buf, title=event.title)

        ins = profile.insurer
        med = profile.medical
        claimant = profile.claimant
        employer = profile.employer
        fin = profile.financial

        slug = event.subtype_slug
        is_sjdb = "sjdb" in slug

        story: list = []
        story.extend(carrier_header_block(profile, form_id="AD 10133.53 (SJDB)" if is_sjdb else "RTW Offer"))
        story.append(spacer(4))

        if is_sjdb:
            story.append(para("SUPPLEMENTAL JOB DISPLACEMENT BENEFIT (SJDB) OFFER", "title"))
            story.append(para("LC § 4658.7 | 8 CCR 10133.53 | DWC Form AD 10133.53", "small"))
        else:
            story.append(para("OFFER OF MODIFIED / ALTERNATIVE WORK", "title"))
            story.append(para("LC § 4658.6 | 8 CCR 10133.53", "small"))

        story.append(thick_hline())
        story.extend(
            claimant_caption_block(
                profile,
                event_date=event.event_date,
                event_title=event.title,
            )
        )

        story.append(para("CLAIMANT AND CLAIM INFORMATION", "heading1"))
        story.append(hline())
        story.append(
            label_value_table([
                ("Claimant:", f"{claimant.first_name} {claimant.last_name}"),
                ("Employer:", employer.company_name),
                ("Claim No.:", ins.claim_number),
                ("Adjuster:", ins.adjuster_name),
                ("Date of Injury (DOI):", med.date_of_injury),
                ("P&S Date:", str(event.event_date)),
                ("WPI:", f"{med.wpi_percent:.1f}%" if med.wpi_percent else "To be rated"),
            ])
        )

        if is_sjdb:
            story.append(spacer(6))
            story.append(para("SJDB VOUCHER DETAILS", "heading1"))
            story.append(hline())

            # SJDB voucher value: $6,000 for injuries on/after 1/1/2013
            voucher_value = 6000.0
            story.append(
                label_value_table([
                    ("SJDB Voucher Value:", f"${voucher_value:,.2f}"),
                    ("Voucher Type:", "Retraining and Skill Enhancement"),
                    ("Eligible Schools:", "BPPE-approved or accredited CA institutions"),
                    ("Expiration:", "2 years from date of issuance (LC § 4658.7(b)(1))"),
                    ("Reason for SJDB:", "Employer unable to offer modified/alternative work within restrictions"),
                ])
            )
            story.append(spacer(6))
            story.append(
                para(
                    f"Pursuant to Labor Code § 4658.7, {claimant.first_name} {claimant.last_name} "
                    f"is entitled to a Supplemental Job Displacement Benefit voucher in the amount "
                    f"of ${voucher_value:,.2f} because {employer.company_name} has not made a "
                    f"timely, valid offer of modified or alternative work consistent with the medical "
                    f"restrictions from the treating physician.\n\n"
                    f"This voucher must be used for education-related retraining expenses at "
                    f"qualifying California institutions. The voucher is non-transferable and may "
                    f"not be redeemed for cash.",
                    "body",
                )
            )
            story.extend(
                regulatory_citation_block([
                    "LC § 4658.7", "8 CCR 10133.53", "AD Form 10133.53"
                ])
            )

        else:
            story.append(spacer(6))
            story.append(para("MODIFIED / ALTERNATIVE WORK OFFER", "heading1"))
            story.append(hline())
            story.append(
                label_value_table([
                    ("Job Title:", claimant.occupation_title + " (Modified)" if claimant.occupation_title else "Modified Duty Position"),
                    ("Work Location:", f"{employer.address_city}, CA"),
                    ("Hours:", "Part-time as restricted"),
                    ("Duration:", "Temporary — per medical restrictions"),
                    ("Wage:", f"${fin.average_weekly_wage / 40 * 8:,.2f}/day (regular wages maintained)"),
                    ("Start Date:", str(event.event_date)),
                ])
            )
            story.append(spacer(6))
            story.append(para("MEDICAL RESTRICTIONS ACCOMMODATED:", "heading2"))
            story.append(
                para(
                    "• No lifting over 10 lbs.<br/>"
                    "• No repetitive bending, twisting, or stooping.<br/>"
                    "• Alternate sitting and standing as needed.<br/>"
                    "• All restrictions per treating physician's work restriction form.<br/>"
                    "• Modified duties subject to change per updated medical documentation.",
                    "body",
                )
            )
            story.append(spacer(6))
            story.append(
                para(
                    f"This offer of modified work is made pursuant to LC § 4658.6. "
                    f"Failure to accept a valid offer of modified work may result in "
                    f"forfeiture of SJDB benefits under LC § 4658.7.",
                    "small",
                )
            )
            story.extend(
                regulatory_citation_block([
                    "LC §§ 4658.6, 4658.7", "8 CCR 10133.53"
                ])
            )

        story.extend(confidentiality_footer())
        doc.build(story)
        return buf.getvalue()
