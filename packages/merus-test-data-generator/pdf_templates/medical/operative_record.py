"""
Operative Record Template

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import random
import re

from pdf_templates.base_template import BaseTemplate
from reportlab.platypus import Paragraph, Spacer
from reportlab.lib.units import inch
from data.wc_constants import SURGICAL_CPT_POOLS


# Body-part aliases → canonical SURGICAL_CPT_POOLS part (AJC-55). Matching is
# by whole word-token sequence, never raw substring: "background" must not
# match "back", "secondhand" must not match "hand". Ambiguous generic terms
# ("spine", "back" alone — which segment?) are deliberately unmapped: an
# operative record for a part this table cannot place claims no specific
# procedure at all rather than guessing one from the wrong segment or region.
BODY_PART_ALIASES: dict[str, str] = {
    "lumbar spine": "lumbar_spine",
    "low back": "lumbar_spine",
    "cervical spine": "cervical_spine",
    "neck": "cervical_spine",
    "thoracic spine": "thoracic_spine",
    "shoulder": "shoulder",
    "knee": "knee",
    "wrist": "wrist",
    "hand": "hand",
    "elbow": "elbow",
    "hip": "hip",
    "ankle": "ankle",
    "foot": "foot",
}


def _tokens(text: str) -> list[str]:
    """Lower-cased word tokens with all separators normalized away."""
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).split()


def _contains_token_sequence(haystack: list[str], needle: list[str]) -> bool:
    if not needle or len(needle) > len(haystack):
        return False
    return any(
        haystack[i : i + len(needle)] == needle for i in range(len(haystack) - len(needle) + 1)
    )


#: Reverse lookup: which part a pool code operates on, for narrative
#: provenance — the approach line must name the operated part, not the whole
#: injured-part list (AJC-55 round 3).
PART_BY_CPT: dict[str, str] = {
    code: part for part, pool in SURGICAL_CPT_POOLS.items() for code, _ in pool
}


def _select_surgical_cpts(body_parts: list[str]) -> list[tuple[str, str]]:
    """Surgical CPT pool for the case's injured body parts, one region each.

    Returns the union of ``SURGICAL_CPT_POOLS`` entries for every recognized
    part, and an **empty list** when no part is recognized: a body part this
    module cannot place anatomically gets no procedure code at all — never a
    borrowed one. Callers decide how to render the absence.
    """
    matched_parts: list[str] = []
    for bp in body_parts:
        bp_tokens = _tokens(bp)
        for alias, part in BODY_PART_ALIASES.items():
            if _contains_token_sequence(bp_tokens, _tokens(alias)) and part not in matched_parts:
                matched_parts.append(part)

    pool: list[tuple[str, str]] = []
    for part in sorted(matched_parts):
        for entry in SURGICAL_CPT_POOLS[part]:
            if entry not in pool:
                pool.append(entry)
    return pool


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

        # Select surgical procedure — body-part-aware CPT selection. A part
        # the alias table cannot place yields no pool; the record then names an
        # unlisted procedure WITHOUT fabricating a coded operation from some
        # other anatomy (AJC-55).
        body_parts = injury.body_parts if injury else ["Spine"]
        surgical_cpts = _select_surgical_cpts(body_parts)
        if surgical_cpts:
            procedure_code, procedure_name = random.choice(surgical_cpts)
        else:
            procedure_code, procedure_name = "N/A", "Unlisted surgical procedure"
        # The approach narrative names the part the chosen procedure operates
        # on; the full injured-part list stays in the diagnosis lines only.
        operated_part = PART_BY_CPT.get(procedure_code, "").replace("_", " ") or body_part.lower()

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

            f"A surgical approach to the {operated_part} was made using standard technique. "
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
