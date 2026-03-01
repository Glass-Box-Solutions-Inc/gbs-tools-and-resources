"""
Diagnostic Report Template (MRI/CT/X-ray)

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import random
from pdf_templates.base_template import BaseTemplate
from reportlab.platypus import Paragraph, Spacer
from reportlab.lib.units import inch


class DiagnosticReport(BaseTemplate):
    """Radiology and diagnostic imaging report"""

    def build_story(self, doc_spec):
        """Build 1-2 page diagnostic imaging report"""
        story = []
        injury = self.case.injuries[0] if self.case.injuries else None
        body_part = ", ".join(injury.body_parts) if injury else "Spine"

        # Imaging center letterhead
        facility_name = random.choice([
            "Pacific Radiology Associates",
            "California Diagnostic Imaging",
            "Advanced MRI & CT Center",
            "Coastal Imaging Center"
        ])
        story.extend(self.make_letterhead(
            facility_name,
            f"{random.randint(100, 9999)} Medical Center Drive\nSuite {random.randint(100, 500)}\n"
            f"San Francisco, CA 9411{random.randint(0, 9)}",
            f"({random.randint(400, 999)}) {random.randint(200, 999)}-{random.randint(1000, 9999)}"
        ))
        story.append(Spacer(1, 0.3*inch))

        # Patient header
        story.extend(self.make_patient_header())
        story.append(Spacer(1, 0.3*inch))

        # Exam details
        exam_type = random.choice(["MRI", "CT", "X-Ray"])
        story.append(Paragraph(f"<b>EXAMINATION:</b> {exam_type} {body_part}", self.styles['BodyText14']))
        story.append(Paragraph(f"<b>Date of Exam:</b> {doc_spec.doc_date.strftime('%B %d, %Y')}", self.styles['BodyText14']))
        story.append(Paragraph(f"<b>Ordering Physician:</b> {self.case.treating_physician.full_name}", self.styles['BodyText14']))
        story.append(Spacer(1, 0.2*inch))

        # Clinical indication
        indication = (
            f"Patient presents with work-related {injury.injury_type.value.replace('_', ' ') if injury else 'injury'} "
            f"to {body_part.lower()}. Clinical evaluation for extent of internal derangement and structural abnormalities."
        )
        story.extend(self.make_section("CLINICAL INDICATION", indication))

        # Technique
        if exam_type == "MRI":
            technique = (
                f"MRI of the {body_part.lower()} was performed without contrast using standard sagittal T1, "
                f"T2, and STIR sequences, as well as axial T2 and gradient echo sequences. "
                f"Field strength: {random.choice(['1.5', '3.0'])} Tesla."
            )
        elif exam_type == "CT":
            technique = (
                f"CT of the {body_part.lower()} was performed without contrast in axial plane "
                f"with coronal and sagittal reformations. Slice thickness: {random.choice(['1', '2', '3'])} mm."
            )
        else:
            technique = (
                f"Radiographic examination of the {body_part.lower()} was performed including "
                f"{random.choice(['AP and lateral', 'AP, lateral, and oblique', 'multiple standard views'])} projections."
            )

        story.extend(self.make_section("TECHNIQUE", technique))

        # Findings
        findings_text = self.lorem_medical(random.randint(5, 8))
        story.extend(self.make_section("FINDINGS", findings_text))

        # Impression
        severity = random.choice(["mild", "moderate", "moderate-to-severe"])
        impression_items = []

        if injury and injury.injury_type:
            impression_items.append(f"1. {injury.injury_type.value.replace('_', ' ').title()} of {body_part.lower()} with {severity} findings.")

        impression_items.extend([
            f"2. {random.choice(['Evidence of', 'Findings consistent with', 'Presence of'])} "
            f"{random.choice(['degenerative changes', 'soft tissue edema', 'structural abnormalities'])}.",
            f"3. {random.choice(['Recommend clinical correlation', 'Suggest follow-up imaging if clinically indicated', 'Clinical correlation recommended'])}."
        ])

        impression_content = "\n\n".join(impression_items)
        story.extend(self.make_section("IMPRESSION", impression_content))

        # Radiologist signature
        radiologist_name = f"Dr. {random.choice(['Robert', 'Jennifer', 'Michael', 'Sarah', 'David'])} "
        radiologist_name += random.choice(['Chen', 'Patel', 'Johnson', 'Martinez', 'Lee'])

        story.append(Spacer(1, 0.4*inch))
        story.extend(self.make_signature_block(
            radiologist_name,
            "Board Certified Radiologist",
            f"CA License #{random.randint(10000, 99999)}"
        ))

        return story
