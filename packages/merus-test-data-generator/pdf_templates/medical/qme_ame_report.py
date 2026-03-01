"""
QME/AME Report Template

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import random
from pdf_templates.base_template import BaseTemplate
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
from data.wc_constants import ICD10_CODES, WORK_RESTRICTIONS


class QmeAmeReport(BaseTemplate):
    """Qualified Medical Evaluator / Agreed Medical Evaluator comprehensive report"""

    def build_story(self, doc_spec):
        """Build 5-12 page QME/AME report"""
        story = []
        qme = self.case.qme_physician
        injury = self.case.injuries[0] if self.case.injuries else None

        # QME letterhead
        story.extend(self.make_letterhead(
            qme.full_name,
            qme.address,
            qme.phone
        ))
        story.append(Spacer(1, 0.3*inch))

        # Patient header
        story.extend(self.make_patient_header())
        story.append(Spacer(1, 0.2*inch))

        # Claim reference
        story.extend(self.make_claim_reference_block())
        story.append(Spacer(1, 0.3*inch))

        # Title
        story.append(Paragraph(
            f"<b>QUALIFIED MEDICAL EVALUATOR REPORT</b>",
            self.styles['CenterBold']
        ))
        story.append(Spacer(1, 0.2*inch))

        # Examination date
        story.append(Paragraph(
            f"<b>Date of Examination:</b> {doc_spec.doc_date.strftime('%B %d, %Y')}",
            self.styles['BodyText14']
        ))
        story.append(Paragraph(
            f"<b>Specialty:</b> {qme.specialty}",
            self.styles['BodyText14']
        ))
        story.append(Spacer(1, 0.3*inch))

        # History of present injury
        # Calculate age from date of birth
        from datetime import date as _date
        applicant_age = (_date.today() - self.case.applicant.date_of_birth).days // 365
        history = (
            f"The patient is a {applicant_age}-year-old {self.case.employer.position.lower()} "
            f"who sustained a work-related injury on {self.case.timeline.date_of_injury.strftime('%m/%d/%Y')} "
            f"while employed by {self.case.employer.company_name}. "
            f"The mechanism of injury involved {injury.mechanism.lower() if injury else 'workplace incident'}. "
            f"Patient reports immediate onset of symptoms affecting the {', '.join(injury.body_parts).lower() if injury else 'body'}.\n\n"
            f"Since the date of injury, the patient has received treatment from {self.case.treating_physician.full_name}, "
            f"{self.case.treating_physician.specialty}, including {random.choice(['conservative management', 'physical therapy and medication management', 'both conservative and interventional treatments'])}. "
            f"Patient describes symptoms as {random.choice(['persistent and limiting', 'variable but ongoing', 'gradually improving but still present'])}."
        )
        story.extend(self.make_section("HISTORY OF PRESENT INJURY", history))

        # Review of medical records
        reviewed_docs = [
            f"Medical records from {self.case.treating_physician.full_name}, {self.case.timeline.date_first_treatment.strftime('%m/%d/%Y')} through {doc_spec.doc_date.strftime('%m/%d/%Y')}",
            f"Diagnostic imaging reports dated {self.case.timeline.date_first_treatment.strftime('%m/%d/%Y')}",
            "Physical therapy progress notes",
            f"Pharmacy records and medication history",
            f"Employer's First Report of Injury dated {self.case.timeline.date_of_injury.strftime('%m/%d/%Y')}"
        ]

        if random.random() > 0.5:
            reviewed_docs.append("Operative report and surgical records")

        reviewed_content = "\n".join([f"• {doc}" for doc in reviewed_docs])
        story.extend(self.make_section("REVIEW OF MEDICAL RECORDS", reviewed_content))

        # Physical examination
        exam_intro = (
            "Patient presents as a well-developed, well-nourished individual in no acute distress. "
            "Patient ambulates independently and follows commands appropriately."
        )
        exam_findings = self.lorem_medical(random.randint(8, 12))
        exam_content = exam_intro + "\n\n" + exam_findings
        story.extend(self.make_section("PHYSICAL EXAMINATION FINDINGS", exam_content))

        # Diagnostic review
        diagnostic = self.lorem_medical(random.randint(4, 6))
        story.extend(self.make_section("DIAGNOSTIC REVIEW", diagnostic))

        # AMA Guides Impairment Rating
        wpi_rating = random.randint(5, 30)
        impairment_content = (
            f"Based on comprehensive evaluation and application of the AMA Guides to the Evaluation of "
            f"Permanent Impairment, {random.choice(['Fifth', 'Sixth'])} Edition, the patient's permanent "
            f"impairment is calculated as follows:\n\n"
            f"<b>Whole Person Impairment (WPI): {wpi_rating}%</b>\n\n"
            f"This rating reflects {random.choice(['persistent functional limitations', 'documented range of motion deficits', 'chronic pain and loss of function'])} "
            f"related to the {', '.join(injury.body_parts).lower() if injury else 'injured area'}. "
            f"The rating is based on {random.choice(['objective clinical findings', 'measurable functional deficits', 'diagnostic study results and clinical examination'])}."
        )
        story.extend(self.make_section("IMPAIRMENT RATING", impairment_content))

        # Apportionment analysis
        apportionment_percentage = random.choice([0, 0, 0, 10, 15, 20, 25])  # Often 0%
        if apportionment_percentage == 0:
            apportionment_content = (
                "After thorough review of the medical record and consideration of all relevant factors, "
                "there is no basis for apportionment in this case. The current impairment is entirely "
                "attributable to the industrial injury sustained on "
                f"{self.case.timeline.date_of_injury.strftime('%m/%d/%Y')}. "
                "There is no evidence of pre-existing pathology or non-industrial contributing factors."
            )
        else:
            apportionment_content = (
                f"Apportionment of {apportionment_percentage}% is applicable in this case due to "
                f"{random.choice(['pre-existing degenerative changes', 'prior non-industrial injury', 'underlying constitutional factors'])}. "
                f"The industrial injury is responsible for {100 - apportionment_percentage}% of the current impairment."
            )
        story.extend(self.make_section("APPORTIONMENT ANALYSIS", apportionment_content))

        # Future medical treatment
        fmt_items = [
            f"{random.choice(['Continued pain management', 'Ongoing physical therapy', 'Periodic re-evaluation'])}",
            f"{random.choice(['Medication management as needed', 'Over-the-counter analgesics', 'Prescription medications as medically necessary'])}",
            f"Follow-up with treating physician every {random.choice(['3-6', '6-12', '4-6'])} months",
        ]

        if random.random() > 0.6:
            fmt_items.append("Potential surgical intervention if conservative measures fail")

        fmt_content = "\n".join([f"• {item}" for item in fmt_items])
        story.extend(self.make_section("FUTURE MEDICAL TREATMENT", fmt_content))

        # Work restrictions
        restrictions = random.sample(WORK_RESTRICTIONS, k=random.randint(3, 5))
        if random.random() > 0.7:
            restrictions_content = (
                "Based on current functional capacity, the following permanent work restrictions are recommended:\n\n" +
                "\n".join([f"• {r}" for r in restrictions])
            )
        else:
            restrictions_content = (
                "Patient has reached maximum medical improvement with minimal residual limitations. "
                "No permanent work restrictions are necessary at this time."
            )
        story.extend(self.make_section("WORK RESTRICTIONS", restrictions_content))

        # Conclusions and opinions
        conclusions = [
            f"1. The injury sustained on {self.case.timeline.date_of_injury.strftime('%m/%d/%Y')} is industrial in nature.",
            f"2. Permanent impairment is rated at {wpi_rating}% whole person.",
            f"3. {'No apportionment is applicable.' if apportionment_percentage == 0 else f'Apportionment of {apportionment_percentage}% applies.'}",
            f"4. Patient has {'reached' if random.random() > 0.5 else 'substantially reached'} maximum medical improvement.",
            f"5. Future medical care {'is' if random.random() > 0.4 else 'may be'} reasonably required."
        ]
        conclusions_content = "\n\n".join(conclusions)
        story.extend(self.make_section("CONCLUSIONS AND MEDICAL-LEGAL OPINIONS", conclusions_content))

        # Signature with QME certification
        story.append(Spacer(1, 0.4*inch))
        story.extend(self.make_signature_block(
            qme.full_name,
            qme.specialty,
            qme.license_number
        ))
        story.append(Spacer(1, 0.1*inch))
        story.append(Paragraph(
            f"<i>Qualified Medical Evaluator #QME{random.randint(10000, 99999)}</i>",
            self.styles['SmallItalic']
        ))
        story.append(Paragraph(
            "<i>I declare under penalty of perjury that this report is true and correct to the best of my knowledge.</i>",
            self.styles['SmallItalic']
        ))

        return story
