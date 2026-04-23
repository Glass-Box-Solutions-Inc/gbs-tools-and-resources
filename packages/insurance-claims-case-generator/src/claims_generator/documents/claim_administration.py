"""
CLAIM_ADMINISTRATION document generator — Tier C plain letterhead.

Covers: claim setup records, closure notices, diary entries, case management notes.
Regulatory basis:
  - 8 CCR 10101: Claims file requirements
  - 8 CCR 10111: Electronic claims files
  - LC § 5814: Claims file retention

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

_SETUP_BODY = (
    "This record confirms the establishment of a Workers' Compensation claim file pursuant "
    "to 8 CCR 10101. The claim has been assigned to the adjuster listed above for "
    "investigation and handling.\n\n"
    "Initial reserve established based on available information. Reserve will be reviewed "
    "and updated as additional information is received. MPN notice has been issued to the "
    "claimant. Initial contact has been attempted per 10 CCR 2695.5(b)."
)

_CLOSURE_BODY = (
    "This notice confirms the closure of the above-referenced Workers' Compensation claim "
    "as of the date indicated. All benefits have been paid and all disputes resolved.\n\n"
    "Per LC § 5814, the claim file will be retained for a minimum of five years from "
    "the date of injury or from the date of last payment of indemnity or provision of "
    "medical treatment, whichever is later.\n\n"
    "Future medical treatment: Per settlement documents. Contact the carrier if additional "
    "medical treatment becomes necessary under the terms of the settlement."
)

_DEFAULT_BODY = (
    "This record is a case management entry in the Workers' Compensation claim file "
    "maintained pursuant to 8 CCR 10101 et seq. The claim is active and under management "
    "by the adjuster identified in the header of this document.\n\n"
    "All actions taken on this claim are documented in the claim diary. The file is "
    "available for inspection per LC § 3762."
)


@register_document
class ClaimAdministrationGenerator(DocumentGenerator):
    """Tier C — claim administration records (setup, closure, diary)."""

    handles = frozenset({DocumentType.CLAIM_ADMINISTRATION})

    @classmethod
    def generate(cls, event: DocumentEvent, profile: ClaimProfile) -> bytes:
        buf = io.BytesIO()
        doc = cls._build_doc(buf, title=event.title)

        ins = profile.insurer
        med = profile.medical
        claimant = profile.claimant
        fin = profile.financial

        slug = event.subtype_slug
        if "setup" in slug:
            body_text = _SETUP_BODY
            record_type = "CLAIM SETUP AND ASSIGNMENT RECORD"
        elif "closure" in slug:
            body_text = _CLOSURE_BODY
            record_type = "CLAIM CLOSURE NOTICE"
        else:
            body_text = _DEFAULT_BODY
            record_type = "CLAIM ADMINISTRATION RECORD"

        story: list = []
        story.extend(carrier_header_block(profile))
        story.append(spacer(4))
        story.append(para(record_type, "title"))
        story.append(para(f"8 CCR 10101 | LC § 5814 | Date: {event.event_date}", "small"))
        story.append(thick_hline())

        story.extend(
            claimant_caption_block(
                profile,
                event_date=event.event_date,
                event_title=event.title,
            )
        )

        story.append(para("CLAIM FILE INFORMATION", "heading1"))
        story.append(hline())
        story.append(
            label_value_table([
                ("Claim No.:", ins.claim_number),
                ("Carrier:", ins.carrier_name),
                ("Adjuster:", ins.adjuster_name),
                ("Adjuster Phone:", ins.adjuster_phone),
                ("Adjuster Email:", ins.adjuster_email),
                ("Claimant:", f"{claimant.first_name} {claimant.last_name}"),
                ("Date of Injury:", med.date_of_injury),
                ("Injury Year:", str(fin.injury_year)),
                ("Record Date:", str(event.event_date)),
                ("Stage:", event.stage),
            ])
        )

        story.append(spacer(6))
        story.append(para("RECORD DETAIL", "heading1"))
        story.append(hline())
        for paragraph_text in body_text.split("\n\n"):
            if paragraph_text.strip():
                story.append(para(paragraph_text, "body"))
                story.append(spacer(4))

        story.extend(
            regulatory_citation_block(["8 CCR 10101", "LC § 5814", "10 CCR 2695.5(b)"])
        )
        story.extend(confidentiality_footer())
        doc.build(story)
        return buf.getvalue()
