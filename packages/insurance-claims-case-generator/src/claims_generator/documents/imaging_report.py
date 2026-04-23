"""
IMAGING_REPORT document generator — Tier C plain letterhead.

Covers: X-ray, MRI, CT scan diagnostic imaging reports.
Regulatory basis:
  - MTUS Imaging guidelines (8 CCR 9792.6)
  - 8 CCR 9789.12: OMFS radiology fee schedule
  - LC § 4600: Medical treatment — authorized imaging

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
    two_col_section,
)
from claims_generator.documents.registry import register_document
from claims_generator.models.claim import DocumentEvent
from claims_generator.models.enums import DocumentType
from claims_generator.models.profile import ClaimProfile

# Modality-specific findings templates
_FINDINGS: dict[str, dict[str, str]] = {
    "xray": {
        "title": "X-RAY / PLAIN FILM REPORT",
        "modality": "X-Ray (Plain Radiograph)",
        "cpt": "72100 (Lumbar spine AP/Lat) / 73010 (Shoulder AP)",
        "findings": (
            "FINDINGS: AP and lateral views obtained. Alignment is maintained. "
            "No acute fracture or dislocation. Mild degenerative changes noted at multiple "
            "levels consistent with age-related changes. Disc space heights appear preserved. "
            "Soft tissues unremarkable."
        ),
        "impression": (
            "1. No acute fracture or dislocation.\n"
            "2. Mild degenerative changes — degenerative disc disease.\n"
            "3. Clinical correlation recommended."
        ),
    },
    "mri": {
        "title": "MRI REPORT",
        "modality": "MRI (Magnetic Resonance Imaging)",
        "cpt": "72148 (Lumbar MRI w/o) / 73221 (Shoulder MRI w/o)",
        "findings": (
            "FINDINGS: Multiplanar, multisequence MRI obtained without intravenous contrast. "
            "Focal disc protrusion identified at L4-5 with mild neural foraminal narrowing. "
            "Disc signal loss consistent with degenerative disc disease at L4-5 and L5-S1. "
            "No significant central canal stenosis. Posterior paraspinal muscles show signal "
            "changes consistent with mild muscular strain. Facet joints show mild hypertrophy."
        ),
        "impression": (
            "1. L4-5 disc protrusion with mild neural foraminal narrowing.\n"
            "2. L4-5, L5-S1 degenerative disc disease.\n"
            "3. Mild posterior paraspinal muscular strain.\n"
            "4. No significant central canal stenosis."
        ),
    },
    "ct": {
        "title": "CT SCAN REPORT",
        "modality": "CT (Computed Tomography)",
        "cpt": "72131 (CT Lumbar w/o) / 73200 (CT Upper Extremity w/o)",
        "findings": (
            "FINDINGS: Axial CT images obtained without intravenous contrast. "
            "Osseous structures show no acute fracture. Mild spondylosis and osteophyte "
            "formation noted. Disc herniations not optimally evaluated on CT. "
            "No significant osseous abnormality identified."
        ),
        "impression": (
            "1. No acute osseous fracture.\n"
            "2. Mild degenerative spondylosis.\n"
            "3. MRI recommended for soft tissue evaluation."
        ),
    },
}


@register_document
class ImagingReportGenerator(DocumentGenerator):
    """Tier C — diagnostic imaging reports (X-ray, MRI, CT)."""

    handles = frozenset({DocumentType.IMAGING_REPORT})

    @classmethod
    def generate(cls, event: DocumentEvent, profile: ClaimProfile) -> bytes:
        buf = io.BytesIO()
        doc = cls._build_doc(buf, title=event.title)

        ins = profile.insurer
        med = profile.medical
        claimant = profile.claimant
        treating = med.treating_physician

        slug = event.subtype_slug
        if "mri" in slug:
            template = _FINDINGS["mri"]
        elif "ct" in slug:
            template = _FINDINGS["ct"]
        else:
            template = _FINDINGS["xray"]

        primary_bp = med.body_parts[0].body_part if med.body_parts else "affected area"
        primary_bp_lat = (
            f"{med.body_parts[0].laterality} {primary_bp}"
            if med.body_parts and med.body_parts[0].laterality
            else primary_bp
        )

        story: list = []
        story.extend(carrier_header_block(profile))
        story.append(spacer(4))
        story.append(para(template["title"], "title"))
        story.append(para(f"8 CCR 9789.12 (OMFS Radiology) | MTUS Imaging Guidelines | CPT: {template['cpt']}", "small"))  # noqa: E501
        story.append(thick_hline())

        story.extend(
            claimant_caption_block(
                profile,
                event_date=event.event_date,
                event_title=event.title,
            )
        )

        story.append(para("EXAMINATION INFORMATION", "heading1"))
        story.append(hline())
        story.append(
            two_col_section(
                left_items=[
                    ("Patient", f"{claimant.first_name} {claimant.last_name}"),
                    ("DOB", str(claimant.date_of_birth)),
                    ("Exam Date", str(event.event_date)),
                ],
                right_items=[
                    ("Body Part", primary_bp_lat.title()),
                    ("Modality", template["modality"]),
                    ("Ordering Physician", f"Dr. {treating.last_name}"),
                ],
            )
        )

        story.append(spacer(4))
        story.append(
            label_value_table([
                ("Clinical Indication:", f"Workers' Compensation injury — {med.injury_mechanism}"),
                ("Claim No.:", ins.claim_number),
                ("Authorization:", "MTUS / UR Approved"),
                ("Comparison Studies:", "None available"),
            ])
        )

        story.append(spacer(6))
        story.append(para("FINDINGS", "heading1"))
        story.append(hline())
        story.append(para(
            template["findings"].replace("{body_part}", primary_bp_lat),
            "body",
        ))

        story.append(spacer(6))
        story.append(para("IMPRESSION", "heading1"))
        story.append(hline())
        for line in template["impression"].split("\n"):
            if line.strip():
                story.append(para(line, "body"))
                story.append(spacer(2))

        story.append(spacer(4))
        story.append(
            label_value_table([
                ("Interpreting Radiologist:", "Board-Certified Radiologist (credentials on file)"),
                ("Date Signed:", str(event.event_date)),
                ("OMFS Billable Amount:", "$786.50 per 8 CCR 9789.12"),
            ])
        )

        story.extend(
            regulatory_citation_block([
                "8 CCR 9789.12", "MTUS Imaging Guidelines", "LC § 4600"
            ])
        )
        story.extend(confidentiality_footer())
        doc.build(story)
        return buf.getvalue()
