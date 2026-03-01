"""
Client Intake Letter Template

Generates welcome/retainer letters to new workers' compensation clients,
outlining case summary and next steps.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from pdf_templates.base_template import BaseTemplate
from reportlab.platypus import Paragraph, Spacer
from reportlab.lib.units import inch
import random


class ClientIntake(BaseTemplate):
    """Client intake and welcome letter template"""

    def build_story(self, doc_spec):
        story = []

        # Law firm letterhead
        firm_name = "Adjudica Legal Services"
        firm_address = f"{random.randint(100, 9999)} Workers' Rights Boulevard\n" \
                      f"Suite {random.randint(100, 999)}\n" \
                      f"Sacramento, CA 9581{random.randint(1, 9)}"
        firm_phone = f"(916) {random.randint(200, 999)}-{random.randint(1000, 9999)}"

        story.extend(self.make_letterhead(
            firm_name,
            firm_address,
            firm_phone
        ))
        story.append(Spacer(1, 0.3 * inch))

        # Date
        story.append(self.make_date_line("Date", doc_spec.doc_date))
        story.append(Spacer(1, 0.2 * inch))

        # Client address
        client_address = f"{self.case.applicant.full_name}<br/>" \
                        f"{self.case.applicant.address_street}<br/>" \
                        f"{self.case.applicant.address_city}, CA {self.case.applicant.address_zip}"
        story.append(Paragraph(client_address, self.styles['BodyText14']))
        story.append(Spacer(1, 0.2 * inch))

        # Re: line
        re_text = f"<b>Re:</b> Your Workers' Compensation Claim<br/>" \
                  f"&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Date of Injury: {self.case.injuries[0].date_of_injury.strftime('%m/%d/%Y')}<br/>" \
                  f"&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Employer: {self.case.employer.company_name}"
        story.append(Paragraph(re_text, self.styles['BodyText14']))
        story.append(Spacer(1, 0.3 * inch))

        # Salutation
        story.append(Paragraph(f"Dear {self.case.applicant.full_name.split()[0]}:", self.styles['BodyText14']))
        story.append(Spacer(1, 0.2 * inch))

        # Welcome paragraph
        welcome = (
            f"Welcome to {firm_name}. We are pleased to represent you in your workers' compensation claim. "
            f"This letter confirms our attorney-client relationship and outlines what you can expect as we "
            f"work together to pursue your claim."
        )
        story.append(Paragraph(welcome, self.styles['DoubleSpaced']))
        story.append(Spacer(1, 0.15 * inch))

        # Retainer reference
        retainer = (
            f"You have signed our retainer agreement, which outlines our fees and the terms of our representation. "
            f"As a reminder, our fee for workers' compensation cases is contingent, meaning we only receive payment "
            f"if you receive benefits. Our fee is limited by law and will be paid from your recovery, subject to "
            f"approval by the Workers' Compensation Appeals Board."
        )
        story.append(Paragraph(retainer, self.styles['DoubleSpaced']))
        story.append(Spacer(1, 0.15 * inch))

        # Case summary section
        story.append(Paragraph("<b>Your Case Summary</b>", self.styles['SectionHeader']))
        story.append(Spacer(1, 0.1 * inch))

        body_parts = ', '.join(self.case.injuries[0].body_parts)
        case_summary = (
            f"Based on our consultation, you sustained an industrial injury on "
            f"{self.case.injuries[0].date_of_injury.strftime('%B %d, %Y')} while employed by "
            f"{self.case.employer.company_name} as a {self.case.employer.position}. You reported injury to "
            f"your {body_parts}. The workers' compensation insurance carrier is {self.case.insurance.carrier_name}, "
            f"and they have assigned claim number {self.case.insurance.claim_number} to your case."
        )
        story.append(Paragraph(case_summary, self.styles['DoubleSpaced']))
        story.append(Spacer(1, 0.2 * inch))

        # Next steps section
        story.append(Paragraph("<b>What Happens Next</b>", self.styles['SectionHeader']))
        story.append(Spacer(1, 0.1 * inch))

        story.append(Paragraph(
            "We will be taking the following steps on your behalf:",
            self.styles['BodyText14']
        ))
        story.append(Spacer(1, 0.1 * inch))

        # Generate next steps based on case status
        next_steps = self._generate_next_steps()
        for i, step in enumerate(next_steps, 1):
            story.append(Paragraph(f"{i}. {step}", self.styles['DoubleSpaced']))
            story.append(Spacer(1, 0.08 * inch))

        story.append(Spacer(1, 0.2 * inch))

        # Client responsibilities
        story.append(Paragraph("<b>Your Responsibilities</b>", self.styles['SectionHeader']))
        story.append(Spacer(1, 0.1 * inch))

        responsibilities = (
            f"To help us best represent your interests, please: (1) Attend all medical appointments and follow "
            f"your doctor's treatment plan; (2) Keep us informed of any changes in your contact information, "
            f"work status, or medical condition; (3) Promptly provide any documents we request; (4) Do not sign "
            f"any documents from the insurance company or employer without consulting us first; and (5) Keep copies "
            f"of all correspondence and documentation related to your claim."
        )
        story.append(Paragraph(responsibilities, self.styles['DoubleSpaced']))
        story.append(Spacer(1, 0.2 * inch))

        # Medical treatment paragraph
        medical_treatment = (
            f"You have the right to receive medical treatment for your work-related injury. Your treating "
            f"physician is {self.case.treating_physician.full_name}. If you have not yet been evaluated by a physician, "
            f"please schedule an appointment as soon as possible. If you have already been treating, please "
            f"provide us with copies of all medical reports and records. You may need to sign medical release "
            f"forms, which we will provide to you."
        )
        story.append(Paragraph(medical_treatment, self.styles['DoubleSpaced']))
        story.append(Spacer(1, 0.2 * inch))

        # Temporary disability benefits
        td_info = (
            f"If you have been unable to work due to your injury, you may be entitled to temporary disability "
            f"benefits. These benefits generally equal two-thirds of your average weekly wage and are paid "
            f"tax-free. There is a three-day waiting period before benefits begin, but if you are disabled for "
            f"more than 14 days, you will be paid for those first three days retroactively."
        )
        story.append(Paragraph(td_info, self.styles['DoubleSpaced']))
        story.append(Spacer(1, 0.2 * inch))

        # Contact information section
        story.append(Paragraph("<b>Questions or Concerns?</b>", self.styles['SectionHeader']))
        story.append(Spacer(1, 0.1 * inch))

        contact_info = (
            f"Please do not hesitate to contact our office if you have any questions or concerns about your "
            f"case. You can reach us at {firm_phone} during regular business hours (Monday through Friday, "
            f"9:00 AM to 5:00 PM). We will keep you informed of all significant developments in your case and "
            f"will respond to your inquiries as promptly as possible."
        )
        story.append(Paragraph(contact_info, self.styles['DoubleSpaced']))
        story.append(Spacer(1, 0.2 * inch))

        # Closing paragraph
        closing = (
            f"We appreciate the opportunity to represent you in this matter. Our goal is to ensure that you "
            f"receive all the workers' compensation benefits to which you are entitled, including medical "
            f"treatment, temporary disability payments, permanent disability benefits, and vocational "
            f"rehabilitation if necessary. We look forward to working with you."
        )
        story.append(Paragraph(closing, self.styles['DoubleSpaced']))
        story.append(Spacer(1, 0.3 * inch))

        # Signature
        story.append(Paragraph("Sincerely,", self.styles['BodyText14']))
        story.append(Spacer(1, 0.5 * inch))

        # Attorney signature block
        attorney_name = random.choice([
            "Sarah Martinez",
            "David Chen",
            "Jennifer Williams",
            "Michael Rodriguez",
            "Lisa Thompson"
        ])
        bar_number = f"State Bar No. {random.randint(100000, 399999)}"

        story.extend(self.make_signature_block(
            f"{attorney_name}, Esq.",
            firm_name,
            bar_number
        ))

        # Enclosure note
        story.append(Spacer(1, 0.3 * inch))
        story.append(Paragraph(
            "<i>Enclosures: Medical Release Forms, Client Information Sheet</i>",
            self.styles['SmallItalic']
        ))

        return story

    def _generate_next_steps(self):
        """Generate appropriate next steps based on case"""

        steps_pool = [
            f"Obtain and review all medical records from {self.case.treating_physician.full_name} and any other healthcare providers who have treated you for this injury",
            f"File an Application for Adjudication of Claim with the Workers' Compensation Appeals Board to formally initiate your case",
            f"Communicate with {self.case.insurance.carrier_name} regarding temporary disability benefits and medical treatment authorization",
            "Request your complete personnel file and wage records from your employer to establish your earnings",
            "Monitor your medical treatment progress and ensure you are receiving all necessary care",
            "Gather any witness statements or documentation supporting your claim that the injury occurred at work",
            "Keep detailed records of all work restrictions, medical appointments, and lost wages",
            "Coordinate with your treating physician to obtain work status reports and disability information"
        ]

        # Select 4-6 steps
        selected_steps = random.sample(steps_pool, random.randint(4, 6))

        # Always include filing application as first or second step
        if selected_steps[0] != [s for s in steps_pool if "Application for Adjudication" in s][0]:
            app_step = [s for s in steps_pool if "Application for Adjudication" in s][0]
            if app_step in selected_steps:
                selected_steps.remove(app_step)
            selected_steps.insert(1, app_step)

        return selected_steps
