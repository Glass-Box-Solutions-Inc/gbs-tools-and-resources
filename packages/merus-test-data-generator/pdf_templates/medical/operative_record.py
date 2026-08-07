"""
Operative Record Template

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import random
from pdf_templates.base_template import BaseTemplate
from reportlab.platypus import Paragraph, Spacer
from reportlab.lib.units import inch
from data.wc_constants import CPT_CODES


# Body-part-aware CPT category mapping. Every mapped part points only at its
# own anatomical region: an operative report must never borrow another region's
# procedure (AJC-55 — wrist cases were drawing rotator cuff repairs through the
# old "upper extremity fallback").
BODY_PART_TO_SURGERY_CATEGORY: dict[str, list[str]] = {
    # spine_injection deliberately absent: an epidural injection is not an
    # operation, and this selector feeds operative records and the wcce
    # ledger's SurgeryFact. Injections keep their own CPT_CODES category for
    # non-surgical delivery paths.
    "cervical spine": ["surgery_spine"],
    "lumbar spine": ["surgery_spine"],
    "thoracic spine": ["surgery_spine"],
    "spine": ["surgery_spine"],
    "neck": ["surgery_spine"],
    "back": ["surgery_spine"],
    "shoulder": ["surgery_shoulder"],
    "knee": ["surgery_knee"],
    "wrist": ["surgery_wrist_hand"],
    "hand": ["surgery_wrist_hand"],
    "elbow": ["surgery_elbow"],
    "hip": ["surgery_hip"],
    "ankle": ["surgery_ankle_foot"],
    "foot": ["surgery_ankle_foot"],
}

# The only procedure an unmapped body part may claim. Anatomically honest by
# construction; also the same default the wc-synthetic-caseload-engine ledger
# uses, so the two sources cannot disagree on the fallback.
UNLISTED_SURGICAL_CPT: tuple[str, str] = ("64999", "Unlisted procedure, nervous system")


def _select_surgical_cpts(body_parts: list[str]) -> list[tuple[str, str]]:
    """Select CPT codes matching the case's injured body parts.

    Unmapped parts (and mapped parts whose category pool is empty) fall back to
    ``UNLISTED_SURGICAL_CPT`` — never to another region's surgery list.
    """
    matched_categories: list[str] = []
    for bp in body_parts:
        bp_lower = bp.lower()
        for key, cats in BODY_PART_TO_SURGERY_CATEGORY.items():
            if key in bp_lower:
                matched_categories.extend(cats)

    surgical_cpts: list[tuple[str, str]] = []
    for cat in sorted(set(matched_categories)):
        surgical_cpts.extend(CPT_CODES.get(cat, []))
    if surgical_cpts:
        return surgical_cpts

    return [UNLISTED_SURGICAL_CPT]


class OperativeRecord(BaseTemplate):
    """Surgical operative report"""

    def build_story(self, doc_spec):
        """Build 2-3 page operative record"""
        story = []
        injury = self.case.injuries[0] if self.case.injuries else None
        body_part = ", ".join(injury.body_parts) if injury else "Spine"

        # Hospital letterhead
        hospital_name = random.choice([
            "California Pacific Medical Center",
            "St. Mary's Surgery Center",
            "Bay Area Orthopedic Hospital",
            "Regional Medical Center"
        ])
        story.extend(self.make_letterhead(
            hospital_name,
            f"{random.randint(1000, 9999)} Hospital Boulevard\n"
            f"San Francisco, CA 9411{random.randint(0, 9)}",
            f"({random.randint(400, 999)}) {random.randint(200, 999)}-{random.randint(1000, 9999)}"
        ))
        story.append(Spacer(1, 0.3*inch))

        # Patient header and claim reference
        story.extend(self.make_patient_header())
        story.append(Spacer(1, 0.2*inch))
        story.extend(self.make_claim_reference_block())
        story.append(Spacer(1, 0.3*inch))

        # Title
        story.append(Paragraph("<b>OPERATIVE REPORT</b>", self.styles['CenterBold']))
        story.append(Spacer(1, 0.2*inch))

        # Surgeon and case details
        surgeon_name = self.case.treating_physician.full_name
        anesthesiologist = f"Dr. {random.choice(['Lisa', 'John', 'Maria', 'Thomas'])} "
        anesthesiologist += random.choice(['Chang', 'Rodriguez', 'Kim', 'Anderson'])

        # Select surgical procedure — body-part-aware CPT selection
        body_parts = injury.body_parts if injury else ["Spine"]
        surgical_cpts = _select_surgical_cpts(body_parts)
        procedure_code, procedure_name = random.choice(surgical_cpts)

        story.append(Paragraph(f"<b>Date of Surgery:</b> {doc_spec.doc_date.strftime('%B %d, %Y')}", self.styles['BodyText14']))
        story.append(Paragraph(f"<b>Surgeon:</b> {surgeon_name}, MD", self.styles['BodyText14']))
        story.append(Paragraph(f"<b>Anesthesiologist:</b> {anesthesiologist}, MD", self.styles['BodyText14']))
        story.append(Paragraph(f"<b>Assistant:</b> Surgical Team", self.styles['BodyText14']))
        story.append(Paragraph(
            f"<b>Anesthesia:</b> {random.choice(['General endotracheal', 'Spinal', 'Regional block with sedation'])}",
            self.styles['BodyText14']
        ))
        story.append(Spacer(1, 0.2*inch))

        # Diagnoses
        diagnosis = f"Work-related {injury.injury_type.value.replace('_', ' ') if injury else 'injury'} of {body_part.lower()}"
        story.append(Paragraph(f"<b>PRE-OPERATIVE DIAGNOSIS:</b>", self.styles['BodyText14']))
        story.append(Paragraph(diagnosis, self.styles['BodyText14']))
        story.append(Spacer(1, 0.1*inch))
        story.append(Paragraph(f"<b>POST-OPERATIVE DIAGNOSIS:</b>", self.styles['BodyText14']))
        story.append(Paragraph(diagnosis, self.styles['BodyText14']))
        story.append(Spacer(1, 0.2*inch))

        # Procedure
        story.append(Paragraph(f"<b>PROCEDURE PERFORMED:</b>", self.styles['BodyText14']))
        story.append(Paragraph(f"{procedure_name} (CPT {procedure_code})", self.styles['BodyText14']))
        story.append(Spacer(1, 0.2*inch))

        # Operative narrative
        narrative_paragraphs = [
            "The patient was brought to the operating room and identified by name and date of birth. "
            "After appropriate anesthesia was administered, the patient was positioned and standard sterile "
            "preparation and draping was performed.",

            f"A surgical approach to the {body_part.lower()} was made using standard technique. "
            f"Careful dissection was carried down through the subcutaneous tissues with hemostasis maintained throughout. "
            f"The operative field was thoroughly inspected.",
        ]

        # Add medical lorem for detailed procedure
        narrative_paragraphs.append(self.lorem_medical(random.randint(6, 10)))

        narrative_paragraphs.extend([
            "All surgical objectives were achieved without complication. Hemostasis was confirmed and the wound "
            "was irrigated thoroughly with sterile saline solution.",

            f"Closure was performed in layers using {random.choice(['absorbable sutures', 'non-absorbable sutures', 'surgical staples'])}. "
            "Sterile dressing was applied. The patient tolerated the procedure well and was transferred to the "
            "post-anesthesia care unit in stable condition."
        ])

        story.extend(self.make_section("OPERATIVE NARRATIVE", "\n\n".join(narrative_paragraphs)))

        # Additional details
        ebl = random.choice([50, 75, 100, 150, 200])
        story.append(Paragraph(f"<b>Estimated Blood Loss:</b> {ebl} mL", self.styles['BodyText14']))
        story.append(Paragraph(
            f"<b>Specimens:</b> {random.choice(['None', 'Tissue sent to pathology', 'Bone fragments removed'])}",
            self.styles['BodyText14']
        ))
        story.append(Paragraph("<b>Complications:</b> None", self.styles['BodyText14']))
        story.append(Spacer(1, 0.4*inch))

        # Surgeon signature
        story.extend(self.make_signature_block(
            surgeon_name,
            self.case.treating_physician.specialty,
            self.case.treating_physician.license_number
        ))

        return story
