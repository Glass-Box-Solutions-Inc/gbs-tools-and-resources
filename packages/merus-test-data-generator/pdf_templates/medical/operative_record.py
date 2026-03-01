"""
Operative Record Template

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import random
from pdf_templates.base_template import BaseTemplate
from reportlab.platypus import Paragraph, Spacer
from reportlab.lib.units import inch
from data.wc_constants import CPT_CODES


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

        # Select surgical procedure — flatten CPT_CODES and filter for surgical procedures
        surgical_cpts = []
        for cat, code_list in CPT_CODES.items():
            if any(word in cat for word in ['surgery', 'injection']):
                surgical_cpts.extend(code_list)
            else:
                for code, desc in code_list:
                    if any(word in desc.lower() for word in ['surgery', 'repair', 'arthroscop', 'fusion', 'replacement', 'discectomy']):
                        surgical_cpts.append((code, desc))
        if not surgical_cpts:
            all_cpts = [(code, desc) for cat_list in CPT_CODES.values() for code, desc in cat_list]
            surgical_cpts = all_cpts[:5]

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
