"""
MEDICAL_CHRONOLOGY document generator — Tier B structured layout.

Covers: medical chronology for settlement, legal review, case analysis.
Regulatory basis:
  - LC § 5002: Evidence — medical records
  - 8 CCR 10606: Medical reports in evidence
  - Used in settlement preparation (C&R, Stipulations)

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import io
from datetime import date, timedelta

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


@register_document
class MedicalChronologyGenerator(DocumentGenerator):
    """Tier B — medical chronology for settlement and legal review."""

    handles = frozenset({DocumentType.MEDICAL_CHRONOLOGY})

    @classmethod
    def generate(cls, event: DocumentEvent, profile: ClaimProfile) -> bytes:
        buf = io.BytesIO()
        doc = cls._build_doc(buf, title=event.title)

        ins = profile.insurer
        med = profile.medical
        claimant = profile.claimant
        treating = med.treating_physician

        doi = date.fromisoformat(med.date_of_injury)
        body_parts_str = ", ".join(bp.body_part for bp in med.body_parts)

        # Synthesize chronology entries from available data
        entries: list[list[str]] = [
            [str(doi), "DWC-1 Claim Form Filed", "DWC-1", "Claim reported — mechanism: " + med.injury_mechanism],
            [str(doi + timedelta(days=3)), "Initial Medical Evaluation", f"Dr. {treating.last_name}", f"Diagnosis: {med.icd10_codes[0].description if med.icd10_codes else 'See records'}"],
            [str(doi + timedelta(days=7)), "PR-2 Report", f"Dr. {treating.last_name}", f"Work status: TD; Body parts: {body_parts_str}"],
            [str(doi + timedelta(days=14)), "UR / RFA", ins.carrier_name, "RFA for treatment — submitted per 8 CCR 9792.6"],
            [str(doi + timedelta(days=21)), "UR Decision", ins.carrier_name, "Treatment APPROVED"],
        ]

        if med.has_surgery:
            entries.append([
                str(doi + timedelta(days=90)),
                "Surgery",
                f"Dr. {treating.last_name}",
                med.surgery_description or "Surgical procedure performed",
            ])

        entries.append([
            str(doi + timedelta(days=180)),
            "MMI / P&S Evaluation",
            f"Dr. {treating.last_name}",
            f"P&S declared. WPI: {med.wpi_percent or 'TBD'}%",
        ])

        entries.append([
            str(event.event_date),
            "Chronology Prepared",
            ins.adjuster_name,
            "For settlement review",
        ])

        story: list = []
        story.extend(carrier_header_block(profile))
        story.append(spacer(4))
        story.append(para("MEDICAL CHRONOLOGY", "title"))
        story.append(para(f"Date Prepared: {event.event_date}", "small"))
        story.append(thick_hline())

        story.extend(
            claimant_caption_block(
                profile,
                event_date=event.event_date,
                event_title=event.title,
            )
        )

        story.append(para("CASE SUMMARY", "heading1"))
        story.append(hline())
        story.append(
            label_value_table([
                ("Claimant:", f"{claimant.first_name} {claimant.last_name}"),
                ("Date of Injury (DOI):", str(doi)),
                ("Claim No.:", ins.claim_number),
                ("Body Parts:", body_parts_str),
                ("Primary Diagnosis:", med.icd10_codes[0].description if med.icd10_codes else "See records"),
                ("WPI:", f"{med.wpi_percent:.1f}%" if med.wpi_percent else "Not yet rated"),
                ("MMI Reached:", "Yes" if med.mmi_reached else "No"),
                ("Treating Physician:", f"Dr. {treating.first_name} {treating.last_name}, {treating.specialty}"),
                ("QME Physician:", (
                    f"Dr. {med.qme_physician.first_name} {med.qme_physician.last_name}"
                    if med.qme_physician else "Not assigned"
                )),
            ])
        )

        story.append(spacer(8))
        story.append(para("CHRONOLOGICAL MEDICAL HISTORY", "heading1"))
        story.append(hline())
        story.append(
            section_table(
                headers=["Date", "Event / Document", "Provider / Party", "Summary"],
                rows=entries,
            )
        )

        story.append(spacer(6))
        story.append(
            para(
                "This medical chronology is prepared from the claim file documents and "
                "is intended for settlement review purposes only. It does not constitute "
                "a legal opinion or medical analysis. Source documents are incorporated "
                "by reference per 8 CCR 10606.",
                "small",
            )
        )

        story.extend(
            regulatory_citation_block(["LC § 5002", "8 CCR 10606"])
        )
        story.extend(confidentiality_footer())
        doc.build(story)
        return buf.getvalue()
