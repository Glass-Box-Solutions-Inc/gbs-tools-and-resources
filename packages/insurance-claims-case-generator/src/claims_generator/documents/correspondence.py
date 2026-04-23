"""
CORRESPONDENCE document generator — Tier C plain letterhead.

Covers: adjuster initial contact, denial explanation, general correspondence.
Regulatory basis: 10 CCR 2695.5(b) — initial contact within 15 days of claim receipt.

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
    STYLES,
    hline,
    para,
    spacer,
)
from claims_generator.documents.registry import register_document
from claims_generator.models.claim import DocumentEvent
from claims_generator.models.enums import DocumentType
from claims_generator.models.profile import ClaimProfile

# Subtype-specific body templates
_BODY_TEMPLATES: dict[str, str] = {
    "adjuster_initial_contact": (
        "Dear {first_name} {last_name},\n\n"
        "This letter confirms that {carrier_name} has received your Workers' Compensation "
        "claim (Claim No. {claim_number}) arising from the reported injury on {doi}. "
        "Your claim has been assigned to the undersigned adjuster for investigation and handling.\n\n"
        "Pursuant to 10 CCR 2695.5(b), we are required to initiate contact with you within "
        "15 days of claim receipt. Please contact our office at {adjuster_phone} with any "
        "questions regarding your claim status, benefits, or the claims process.\n\n"
        "You have the right to select a treating physician from the Medical Provider Network "
        "(MPN) designated by your employer. A copy of the MPN notice and access instructions "
        "is enclosed or available upon request.\n\n"
        "Sincerely,\n{adjuster_name}\nClaims Adjuster\n{carrier_name}"
    ),
    "denial_explanation_letter": (
        "Dear {first_name} {last_name},\n\n"
        "We have completed our investigation of your Workers' Compensation claim "
        "(Claim No. {claim_number}) for the reported injury of {doi}. Based on our review "
        "of the available medical records, witness statements, and applicable law under "
        "Labor Code § 3600, we have determined that the claimed injury did not arise out of "
        "and in the course of employment (AOE/COE).\n\n"
        "A formal Notice of Denial has been issued pursuant to 10 CCR 2695.7(b). You have "
        "the right to dispute this determination by filing an Application for Adjudication of "
        "Claim (ADJ) with the Workers' Compensation Appeals Board (WCAB).\n\n"
        "You are advised to consult with an attorney regarding your rights. The State Bar of "
        "California Lawyer Referral Service can be reached at 1-800-843-9053.\n\n"
        "Sincerely,\n{adjuster_name}\nClaims Adjuster\n{carrier_name}"
    ),
}

_DEFAULT_BODY = (
    "Dear {first_name} {last_name},\n\n"
    "This correspondence is in reference to Workers' Compensation Claim No. {claim_number} "
    "for the injury reported on {doi}.\n\n"
    "Please contact our office at {adjuster_phone} or {adjuster_email} with any questions "
    "regarding your claim.\n\n"
    "Sincerely,\n{adjuster_name}\nClaims Adjuster\n{carrier_name}"
)


@register_document
class CorrespondenceGenerator(DocumentGenerator):
    """Tier C — plain letterhead correspondence."""

    handles = frozenset({DocumentType.CORRESPONDENCE})

    @classmethod
    def generate(cls, event: DocumentEvent, profile: ClaimProfile) -> bytes:
        buf = io.BytesIO()
        doc = cls._build_doc(buf, title=event.title)

        c = profile.claimant
        ins = profile.insurer
        med = profile.medical

        fmt = {
            "first_name": c.first_name,
            "last_name": c.last_name,
            "carrier_name": ins.carrier_name,
            "claim_number": ins.claim_number,
            "doi": med.date_of_injury,
            "adjuster_name": ins.adjuster_name,
            "adjuster_phone": ins.adjuster_phone,
            "adjuster_email": ins.adjuster_email,
        }

        template = _BODY_TEMPLATES.get(event.subtype_slug, _DEFAULT_BODY)
        body_text = template.format(**fmt)

        story: list = []
        story.extend(carrier_header_block(profile))
        story.append(spacer(8))
        story.append(para(f"Date: {event.event_date}", "body"))
        story.append(para(f"Re: {event.title}", "heading1"))
        story.append(hline())
        story.append(spacer(6))

        for paragraph_text in body_text.split("\n\n"):
            if paragraph_text.strip():
                story.append(para(paragraph_text.replace("\n", "<br/>"), "body"))
                story.append(spacer(4))

        if event.deadline_statute:
            story.extend(regulatory_citation_block([event.deadline_statute]))

        story.extend(confidentiality_footer())
        doc.build(story)
        return buf.getvalue()
