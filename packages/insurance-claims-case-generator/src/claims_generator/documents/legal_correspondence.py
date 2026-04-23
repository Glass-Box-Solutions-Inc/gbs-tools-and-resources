"""
LEGAL_CORRESPONDENCE document generator — Tier C plain letterhead.

Covers: QME panel objection letters, QME report objections, attorney correspondence.
Access level: DUAL_ACCESS (examiner + attorney).

Regulatory basis:
  - 8 CCR 31.3 / 31.5: QME panel selection procedures
  - 8 CCR 35.5: QME report objection within 20 days of receipt
  - LC §§ 4060–4062: Medical-legal evaluation procedures

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
    wcab_caption,
)
from claims_generator.documents.pdf_primitives import (
    hline,
    para,
    spacer,
    thick_hline,
)
from claims_generator.documents.registry import register_document
from claims_generator.models.claim import DocumentEvent
from claims_generator.models.enums import DocumentType
from claims_generator.models.profile import ClaimProfile

_QME_PANEL_OBJECTION = (
    "Defendants hereby object to the QME panel issued in the above-captioned matter "
    "on the following grounds:\n\n"
    "1. The specialty requested by Applicant's counsel does not match the industrial injury "
    "as described in the PR-2 and treating physician's records.\n"
    "2. The panel was issued in the incorrect specialty under 8 CCR 31.1.\n"
    "3. One or more panelists on the issued panel have a disqualifying conflict of interest "
    "under 8 CCR 41.5.\n\n"
    "Defendants request that the Medical Unit issue a replacement panel in the specialty of "
    "{specialty}. This objection is timely under 8 CCR 31.3, which requires objections to be "
    "submitted within 10 days of receipt of the panel.\n\n"
    "Please contact the undersigned to schedule the QME examination once the panel dispute "
    "is resolved. The selected QME physician must conduct the evaluation within 30 days of "
    "appointment (8 CCR 31.5)."
)

_QME_REPORT_OBJECTION = (
    "Defendants hereby object to the Qualified Medical Evaluator (QME) report of "
    "Dr. {qme_physician} dated {event_date} on the following grounds:\n\n"
    "1. The report fails to address the mechanism of injury as described in the employment "
    "records and the DWC-1 claim form.\n"
    "2. The evaluator's apportionment analysis under Labor Code § 4663 is incomplete and "
    "fails to consider the non-industrial factors documented in the medical history.\n"
    "3. The WPI rating does not conform to the AMA Guides, 5th Edition, as required by "
    "Labor Code § 4660.\n\n"
    "Pursuant to 8 CCR 35.5, this objection is submitted within 20 days of receipt of the "
    "QME report. Defendants reserve the right to request supplemental questions (8 CCR 35(d)) "
    "and to obtain a cross-examination of the evaluator at the WCAB hearing.\n\n"
    "This objection is without waiver of any and all defenses available to Defendants."
)

_DEFAULT_LEGAL = (
    "This correspondence is submitted on behalf of {carrier_name}, defendant in the "
    "above-captioned Workers' Compensation matter (Claim No. {claim_number}).\n\n"
    "Please direct all future correspondence and service of documents to:\n"
    "{adjuster_name}\n{carrier_name}\n{adjuster_email}\n{adjuster_phone}\n\n"
    "All documents requiring immediate attention should be served pursuant to "
    "8 CCR 10628 (electronic service) or 8 CCR 10630 (service by mail)."
)


@register_document
class LegalCorrespondenceGenerator(DocumentGenerator):
    """Tier C — legal correspondence (QME objections, attorney letters)."""

    handles = frozenset({DocumentType.LEGAL_CORRESPONDENCE})

    @classmethod
    def generate(cls, event: DocumentEvent, profile: ClaimProfile) -> bytes:
        buf = io.BytesIO()
        doc = cls._build_doc(buf, title=event.title)

        ins = profile.insurer
        med = profile.medical

        qme_name = "N/A"
        if med.qme_physician:
            qme_name = f"Dr. {med.qme_physician.last_name}, {med.qme_physician.specialty}"
        specialty = med.treating_physician.specialty

        fmt = {
            "carrier_name": ins.carrier_name,
            "claim_number": ins.claim_number,
            "adjuster_name": ins.adjuster_name,
            "adjuster_phone": ins.adjuster_phone,
            "adjuster_email": ins.adjuster_email,
            "specialty": specialty,
            "qme_physician": qme_name,
            "event_date": str(event.event_date),
        }

        slug = event.subtype_slug
        if "panel_objection" in slug or "qme_panel_objection" in slug:
            body_text = _QME_PANEL_OBJECTION.format(**fmt)
            header_label = "QME PANEL OBJECTION"
            citations = ["8 CCR 31.1", "8 CCR 31.3", "8 CCR 31.5", "LC § 4060"]
        elif "qme_objection" in slug or "report_objection" in slug:
            body_text = _QME_REPORT_OBJECTION.format(**fmt)
            header_label = "OBJECTION TO QME REPORT"
            citations = ["8 CCR 35.5", "LC §§ 4660, 4663", "AMA Guides 5th Ed."]
        else:
            body_text = _DEFAULT_LEGAL.format(**fmt)
            header_label = "LEGAL CORRESPONDENCE"
            citations = ["8 CCR 10628", "LC § 3762"]

        story: list = []
        story.extend(carrier_header_block(profile))
        story.append(spacer(6))
        story.append(para(header_label, "title"))
        story.append(para(f"Date: {event.event_date}", "small"))
        story.append(thick_hline())

        story.extend(wcab_caption(profile))
        story.append(spacer(6))

        for paragraph_text in body_text.split("\n\n"):
            if paragraph_text.strip():
                story.append(para(paragraph_text.replace("\n", "<br/>"), "body"))
                story.append(spacer(4))

        story.extend(regulatory_citation_block(citations))
        story.extend(confidentiality_footer())
        doc.build(story)
        return buf.getvalue()
