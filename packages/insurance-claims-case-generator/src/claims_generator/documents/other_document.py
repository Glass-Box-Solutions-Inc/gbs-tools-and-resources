"""
OTHER document generator — Tier C plain letterhead fallback.

Covers: miscellaneous documents that don't fit other categories.
Used as a catch-all for the OTHER DocumentType enum value.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import io

from claims_generator.documents.base_document import DocumentGenerator
from claims_generator.documents.letterhead import (
    carrier_header_block,
    claimant_caption_block,
    confidentiality_footer,
)
from claims_generator.documents.pdf_primitives import (
    para,
    spacer,
    thick_hline,
)
from claims_generator.documents.registry import register_document
from claims_generator.models.claim import DocumentEvent
from claims_generator.models.enums import DocumentType
from claims_generator.models.profile import ClaimProfile


@register_document
class OtherDocumentGenerator(DocumentGenerator):
    """Tier C — OTHER document type fallback."""

    handles = frozenset({DocumentType.OTHER})

    @classmethod
    def generate(cls, event: DocumentEvent, profile: ClaimProfile) -> bytes:
        buf = io.BytesIO()
        doc = cls._build_doc(buf, title=event.title)

        ins = profile.insurer

        story: list = []
        story.extend(carrier_header_block(profile))
        story.append(spacer(4))
        story.append(para(event.title.upper(), "title"))
        story.append(para(f"Date: {event.event_date} | Claim No.: {ins.claim_number}", "small"))
        story.append(thick_hline())

        story.extend(
            claimant_caption_block(
                profile,
                event_date=event.event_date,
                event_title=event.title,
            )
        )

        story.append(
            para(
                f"This document ({event.subtype_slug}) is associated with Workers' "
                f"Compensation Claim No. {ins.claim_number} administered by {ins.carrier_name}. "
                f"Filed: {event.event_date}. Stage: {event.stage}.",
                "body",
            )
        )
        story.append(spacer(6))
        story.append(
            para(
                "This document is part of the claim file maintained pursuant to "
                "8 CCR 10101 et seq. and is subject to the document retention requirements "
                "of Labor Code § 5814.",
                "small",
            )
        )

        story.extend(confidentiality_footer())
        doc.build(story)
        return buf.getvalue()
