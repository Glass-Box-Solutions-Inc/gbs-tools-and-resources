"""
BILLING_STATEMENT document generator — Tier B structured layout.

Covers: medical billing statements (professional and institutional).
OMFS fee schedule codes referenced per 8 CCR 9789 et seq.
Regulatory basis:
  - 8 CCR 9789.10: OMFS physician fee schedule
  - 8 CCR 9789.70: OMFS pharmaceutical schedule
  - LC § 4603.2: Medical-legal fee schedule
  - 8 CCR 9792.5: Disputes over medical bills (IBR)

NOTE: Tier A form-accurate UB-04 and CMS-1500 are in billing_statement_forms.py.
This generator covers standard WC billing statements (non-form-accurate).

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
)
from claims_generator.documents.registry import register_document
from claims_generator.models.claim import DocumentEvent
from claims_generator.models.enums import DocumentType
from claims_generator.models.profile import ClaimProfile

# Typical WC medical service line items
_SERVICE_LINES: list[dict[str, str]] = [
    {"cpt": "99213", "desc": "Office/Outpatient Visit, Level 3", "mod": "WC", "qty": "1", "fee": "$160.51", "allowed": "$160.51"},  # noqa: E501
    {"cpt": "97110", "desc": "Therapeutic Exercise, 15 min", "mod": "", "qty": "4", "fee": "$39.17", "allowed": "$39.17"},  # noqa: E501
    {"cpt": "97014", "desc": "Electrical Stimulation (unattended)", "mod": "", "qty": "1", "fee": "$31.48", "allowed": "$31.48"},  # noqa: E501
    {"cpt": "72148", "desc": "MRI Lumbar Spine w/o Contrast", "mod": "", "qty": "1", "fee": "$1,248.00", "allowed": "$786.50"},  # noqa: E501
]


@register_document
class BillingStatementGenerator(DocumentGenerator):
    """Tier B — medical billing statements (WC OMFS fee schedule)."""

    handles = frozenset({DocumentType.BILLING_STATEMENT})

    @classmethod
    def generate(cls, event: DocumentEvent, profile: ClaimProfile) -> bytes:
        buf = io.BytesIO()
        doc = cls._build_doc(buf, title=event.title)

        ins = profile.insurer
        med = profile.medical
        claimant = profile.claimant  # noqa: F841
        treating = med.treating_physician

        story: list = []
        story.extend(carrier_header_block(profile))
        story.append(spacer(4))
        story.append(para("MEDICAL BILLING STATEMENT", "title"))
        story.append(para("OMFS Fee Schedule (8 CCR 9789.10) | Workers' Compensation", "small"))
        story.append(thick_hline())

        story.extend(
            claimant_caption_block(
                profile,
                event_date=event.event_date,
                event_title=event.title,
            )
        )

        # Provider and payer info
        story.append(para("PROVIDER AND PAYER INFORMATION", "heading1"))
        story.append(hline())
        story.append(
            label_value_table([
                ("Billing Provider:", f"Dr. {treating.first_name} {treating.last_name}"),
                ("Provider NPI:", treating.npi),
                ("Provider License:", treating.license_number),
                ("Provider City:", treating.address_city),
                ("Payer:", ins.carrier_name),
                ("Claim No.:", ins.claim_number),
                ("Policy No.:", ins.policy_number),
                ("Date of Service:", str(event.event_date)),
                ("Date of Injury (DOI):", med.date_of_injury),
            ])
        )

        # Service lines
        story.append(spacer(8))
        story.append(para("SERVICE DETAIL", "heading1"))
        story.append(hline())

        # Select 2-3 lines based on event
        seed_val = int(event.event_id.replace("-", "")[:8], 16) % len(_SERVICE_LINES) if event.event_id else 0  # noqa: E501
        selected = _SERVICE_LINES[seed_val:seed_val + 3] or _SERVICE_LINES[:2]

        story.append(
            section_table(
                headers=["CPT Code", "Description", "Mod", "Qty", "Billed", "OMFS Allowed"],
                rows=[
                    [s["cpt"], s["desc"], s["mod"], s["qty"], s["fee"], s["allowed"]]
                    for s in selected
                ],
            )
        )

        # Total
        total_billed = sum(
            float(s["fee"].replace("$", "").replace(",", "")) for s in selected
        )
        total_allowed = sum(
            float(s["allowed"].replace("$", "").replace(",", "")) for s in selected
        )
        story.append(spacer(6))
        story.append(
            label_value_table([
                ("Total Billed:", f"${total_billed:,.2f}"),
                ("OMFS Allowed Amount:", f"${total_allowed:,.2f}"),
                ("Adjustment:", f"${total_billed - total_allowed:,.2f}"),
                ("Balance Due:", f"${total_allowed:,.2f}"),
            ])
        )

        story.append(spacer(6))
        story.append(
            para(
                "OMFS rates per 8 CCR 9789.10 effective for date of service. "
                "Disputes over payment amount must be submitted via Independent Bill Review "
                "(IBR) per 8 CCR 9792.5 within 30 days of EOR receipt. "
                "All CPT codes referenced from AMA CPT codebook.",
                "small",
            )
        )

        story.extend(
            regulatory_citation_block([
                "8 CCR 9789.10", "8 CCR 9792.5", "LC § 4603.2"
            ])
        )
        story.extend(confidentiality_footer())
        doc.build(story)
        return buf.getvalue()
