"""
Treating Physician Report Template (PR-2/PR-3)

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import random
from pdf_templates.base_template import BaseTemplate
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
from data.wc_constants import CPT_CODES, ICD10_CODES, MEDICATIONS, WORK_RESTRICTIONS


class TreatingPhysicianReport(BaseTemplate):
    """PR-2/PR-3 Workers' Compensation treating physician progress report"""

    def build_story(self, doc_spec):
        """Build 2-4 page treating physician report"""
        story = []
        tp = self.case.treating_physician
        patient = self.case.applicant
        injury = self.case.injuries[0] if self.case.injuries else None

        # Letterhead
        story.extend(self.make_letterhead(
            tp.full_name,
            tp.address,
            tp.phone
        ))
        story.append(Spacer(1, 0.3*inch))

        # Patient header
        story.extend(self.make_patient_header())
        story.append(Spacer(1, 0.2*inch))

        # Claim reference
        story.extend(self.make_claim_reference_block())
        story.append(Spacer(1, 0.3*inch))

        # Report header
        story.append(Paragraph(f"<b>{doc_spec.title}</b>", self.styles['CenterBold']))
        story.append(Spacer(1, 0.2*inch))

        # Date of service
        story.append(Paragraph(
            f"<b>Date of Service:</b> {doc_spec.doc_date.strftime('%B %d, %Y')}",
            self.styles['BodyText14']
        ))
        story.append(Paragraph(
            f"<b>Referring Physician:</b> {tp.full_name}, {tp.specialty}",
            self.styles['BodyText14']
        ))
        story.append(Spacer(1, 0.2*inch))

        # Chief complaints
        story.extend(self.make_section(
            "CHIEF COMPLAINTS",
            f"Patient presents today for follow-up evaluation of work-related injuries sustained on "
            f"{self.case.timeline.date_of_injury.strftime('%m/%d/%Y')}. "
            f"Patient reports ongoing {', '.join(injury.body_parts).lower()} symptoms including pain, "
            f"{'stiffness, and limited range of motion' if random.random() > 0.5 else 'swelling, and functional limitations'}."
        ))

        # Physical examination
        exam_findings = self.lorem_medical(random.randint(4, 6))
        story.extend(self.make_section(
            "PHYSICAL EXAMINATION",
            exam_findings
        ))

        # Assessment with ICD-10
        icd_codes = injury.icd10_codes if injury else []
        icd_text = []
        for code in icd_codes[:3]:  # Limit to 3 codes
            # Look up description from ICD10_CODES dict
            desc = "Unspecified injury"
            for _bp, code_list in ICD10_CODES.items():
                for c, d in code_list:
                    if c == code:
                        desc = d
                        break
            icd_text.append(f"• {code} - {desc}")

        assessment_content = (
            f"Based on clinical examination and review of diagnostic studies, patient continues to demonstrate "
            f"findings consistent with work-related {injury.injury_type.value.replace('_', ' ')}.\n\n"
            f"<b>ICD-10 Diagnoses:</b>\n" + "\n".join(icd_text)
        )
        story.extend(self.make_section("ASSESSMENT", assessment_content))

        # Treatment plan with CPT codes
        all_cpts = [(code, desc) for cat_list in CPT_CODES.values() for code, desc in cat_list]
        selected_cpts = random.sample(all_cpts, k=min(random.randint(2, 4), len(all_cpts)))
        treatment_items = []
        for code, desc in selected_cpts:
            treatment_items.append(f"• {code} - {desc}")

        treatment_content = (
            "Treatment plan continues as follows:\n\n" +
            "\n".join(treatment_items) + "\n\n" +
            f"Patient is scheduled for follow-up in {random.choice([2, 3, 4, 6])} weeks."
        )
        story.extend(self.make_section("TREATMENT PLAN", treatment_content))

        # Work restrictions
        restrictions = random.sample(WORK_RESTRICTIONS, k=random.randint(2, 4))
        restrictions_content = (
            "Patient remains under the following work restrictions:\n\n" +
            "\n".join([f"• {r}" for r in restrictions]) + "\n\n" +
            "These restrictions are expected to remain in place pending re-evaluation at next visit."
        )
        story.extend(self.make_section("WORK RESTRICTIONS", restrictions_content))

        # Current medications table
        meds = random.sample(MEDICATIONS, k=random.randint(3, 5))
        med_data = [["Medication", "Dosage", "Frequency", "Purpose"]]
        for med_name, med_dosage, med_freq in meds:
            purpose = "Pain management" if "pain" in med_name.lower() else "Inflammation"
            med_data.append([med_name, med_dosage, med_freq, purpose])

        med_table = Table(med_data, colWidths=[2*inch, 1.2*inch, 1.5*inch, 1.8*inch])
        med_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('TOPPADDING', (0, 1), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
        ]))

        story.append(Paragraph("<b>CURRENT MEDICATIONS</b>", self.styles['SectionHeader']))
        story.append(Spacer(1, 0.1*inch))
        story.append(med_table)
        story.append(Spacer(1, 0.3*inch))

        # Signature
        story.extend(self.make_signature_block(
            tp.full_name,
            tp.specialty,
            tp.license_number
        ))

        return story
