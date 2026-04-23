"""
DEPOSITION_TRANSCRIPT document generator — Tier B structured layout.

Covers: applicant deposition, treating physician deposition, QME deposition.
Access level: DUAL_ACCESS.
Regulatory basis:
  - 8 CCR 10550: Discovery in workers' compensation proceedings
  - LC § 5710: Deposition rights
  - 8 CCR 10628: Service of deposition notice

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
class DepositionTranscriptGenerator(DocumentGenerator):
    """Tier B — deposition transcripts (applicant, treating physician)."""

    handles = frozenset({DocumentType.DEPOSITION_TRANSCRIPT})

    @classmethod
    def generate(cls, event: DocumentEvent, profile: ClaimProfile) -> bytes:
        buf = io.BytesIO()
        doc = cls._build_doc(buf, title=event.title)

        ins = profile.insurer
        med = profile.medical
        claimant = profile.claimant

        slug = event.subtype_slug
        is_applicant = "applicant" in slug
        is_physician = "physician" in slug or "doctor" in slug

        if is_applicant:
            deponent = f"{claimant.first_name} {claimant.last_name}"
            deponent_role = "Applicant"
        elif is_physician:
            deponent = f"Dr. {med.treating_physician.last_name}"
            deponent_role = "Treating Physician"
        elif "qme" in slug and med.qme_physician:
            deponent = f"Dr. {med.qme_physician.last_name}"
            deponent_role = "Qualified Medical Evaluator"
        else:
            deponent = "Witness"
            deponent_role = "Witness"

        story: list = []
        story.extend(carrier_header_block(profile))
        story.append(spacer(4))
        story.append(para("DEPOSITION TRANSCRIPT", "title"))
        story.append(para(f"LC § 5710 | 8 CCR 10550 | Date: {event.event_date}", "small"))
        story.append(thick_hline())

        story.extend(wcab_caption(profile))
        story.append(spacer(6))

        story.append(para("DEPOSITION INFORMATION", "heading1"))
        story.append(hline())
        story.append(
            label_value_table([
                ("Deponent:", deponent),
                ("Role:", deponent_role),
                ("Date of Deposition:", str(event.event_date)),
                ("Location:", f"{claimant.address_city}, CA"),
                ("Court Reporter:", "Certified Court Reporter (CCR #XXXXX)"),
                ("Noticing Party:", ins.carrier_name),
                ("Claim No.:", ins.claim_number),
            ])
        )

        story.append(spacer(6))
        story.append(para(f"IN THE MATTER OF {claimant.last_name.upper()}", "heading1"))
        story.append(para(f"Deposition of {deponent}, {deponent_role}", "heading2"))
        story.append(hline())

        if is_applicant:
            qa_lines = [
                ("Q", "Please state your full name for the record."),
                ("A", f"{claimant.first_name} {claimant.last_name}."),
                ("Q", f"On {med.date_of_injury}, were you employed by {profile.employer.company_name}?"),
                ("A", "Yes, I was."),
                ("Q", f"Can you describe the {med.injury_mechanism} incident?"),
                ("A", f"I was performing my regular duties when the injury occurred to my {med.body_parts[0].body_part if med.body_parts else 'body'}."),
                ("Q", "Have you treated with any physicians following the injury?"),
                ("A", f"Yes, I have been treating with Dr. {med.treating_physician.last_name}."),
                ("Q", "Are you currently able to perform your regular work duties?"),
                ("A", "No, I have restrictions due to my injury."),
            ]
        else:
            body_parts_str = ", ".join(bp.body_part for bp in med.body_parts)
            qa_lines = [
                ("Q", "Please state your name and specialty."),
                ("A", f"Dr. {med.treating_physician.first_name} {med.treating_physician.last_name}, {med.treating_physician.specialty}."),
                ("Q", f"Are you familiar with the patient {claimant.first_name} {claimant.last_name}?"),
                ("A", "Yes, I have been their treating physician."),
                ("Q", f"What is your diagnosis regarding the {body_parts_str}?"),
                ("A", f"My diagnosis includes {med.icd10_codes[0].description if med.icd10_codes else 'the conditions noted in my PR-2'}."),
                ("Q", "Is the condition in your opinion industrially caused?"),
                ("A", "Based on the mechanism of injury described and my clinical findings, yes."),
                ("Q", "Has the patient reached MMI?"),
                ("A", "Yes" if med.mmi_reached else "Not at this time."),
            ]

        story.append(spacer(4))
        for speaker, line in qa_lines:
            style = "body_bold" if speaker == "Q" else "body"
            story.append(para(f"<b>{speaker}:</b> {line}", style))
            story.append(spacer(2))

        story.append(spacer(8))
        story.append(para("CERTIFICATION", "heading2"))
        story.append(hline())
        story.append(
            para(
                "I, the undersigned Certified Court Reporter, do hereby certify that the "
                "foregoing is a true and accurate transcript of the deposition proceedings "
                "described herein. The deponent was duly sworn before testimony was given.",
                "small",
            )
        )

        story.extend(
            regulatory_citation_block(["LC § 5710", "8 CCR 10550", "8 CCR 10628"])
        )
        story.extend(confidentiality_footer())
        doc.build(story)
        return buf.getvalue()
