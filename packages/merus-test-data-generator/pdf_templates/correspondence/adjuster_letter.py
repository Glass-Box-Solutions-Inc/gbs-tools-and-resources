"""
Insurance Adjuster Letter Template

Generates letters from insurance claims adjusters to applicant attorneys,
including claim acceptance, settlement offers, and UR decisions.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from pdf_templates.base_template import BaseTemplate
from reportlab.platypus import Paragraph, Spacer
from reportlab.lib.units import inch
import random
from datetime import timedelta


class AdjusterLetter(BaseTemplate):
    """Insurance adjuster correspondence template"""

    def build_story(self, doc_spec):
        story = []

        # Insurance carrier letterhead
        adjuster_address = f"{random.randint(100, 9999)} Insurance Plaza\n" \
                          f"Suite {random.randint(100, 999)}\n" \
                          f"San Francisco, CA 9410{random.randint(1, 9)}"

        story.extend(self.make_letterhead(
            self.case.insurance.carrier_name,
            adjuster_address,
            self.case.insurance.adjuster_phone
        ))
        story.append(Spacer(1, 0.3 * inch))

        # Date
        story.append(self.make_date_line("Date", doc_spec.doc_date))
        story.append(Spacer(1, 0.2 * inch))

        # Re: line
        re_text = f"<b>Re:</b> Claim No. {self.case.insurance.claim_number}<br/>" \
                  f"&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{self.case.applicant.full_name}<br/>" \
                  f"&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Date of Injury: {self.case.injuries[0].date_of_injury.strftime('%m/%d/%Y')}"
        story.append(Paragraph(re_text, self.styles['BodyText14']))
        story.append(Spacer(1, 0.3 * inch))

        # Addressed to (assuming applicant's attorney)
        addressee = f"Applicant's Attorney<br/>" \
                   f"Law Offices of Workers' Rights<br/>" \
                   f"{random.randint(100, 9999)} Legal Plaza<br/>" \
                   f"Oakland, CA 9460{random.randint(1, 9)}"
        story.append(Paragraph(addressee, self.styles['BodyText14']))
        story.append(Spacer(1, 0.2 * inch))

        # Salutation
        story.append(Paragraph("Dear Counsel:", self.styles['BodyText14']))
        story.append(Spacer(1, 0.2 * inch))

        # Body - randomly select letter type
        letter_types = [
            self._initial_acceptance,
            self._pd_advance_offer,
            self._settlement_discussion,
            self._medical_records_request,
            self._ur_decision
        ]

        letter_content = random.choice(letter_types)()
        for para in letter_content:
            story.append(Paragraph(para, self.styles['DoubleSpaced']))
            story.append(Spacer(1, 0.15 * inch))

        # Closing
        story.append(Spacer(1, 0.2 * inch))
        story.append(Paragraph("Sincerely,", self.styles['BodyText14']))
        story.append(Spacer(1, 0.5 * inch))

        # Signature block
        story.extend(self.make_signature_block(
            self.case.insurance.adjuster_name,
            "Claims Adjuster",
            None
        ))

        return story

    def _initial_acceptance(self):
        """Initial claim acceptance letter"""
        body_parts = ', '.join(self.case.injuries[0].body_parts)

        return [
            f"This letter confirms that we have accepted liability for the industrial injury sustained "
            f"by {self.case.applicant.full_name} on {self.case.injuries[0].date_of_injury.strftime('%B %d, %Y')} "
            f"at {self.case.employer.company_name}.",

            f"The accepted body parts are: {body_parts}. We will provide medical treatment in accordance "
            f"with the Labor Code and will begin temporary disability payments as appropriate. "
            f"{self.lorem_correspondence(1)}",

            f"Please provide us with any medical reports and treatment records as they become available. "
            f"If you have any questions regarding this claim, please contact me directly at "
            f"{self.case.insurance.adjuster_phone} or via email at {self.case.insurance.adjuster_email}."
        ]

    def _pd_advance_offer(self):
        """Permanent disability advance offer"""
        pd_amount = random.choice([2000, 3000, 5000, 7500, 10000])

        return [
            f"We have reviewed the medical reports in the above-referenced matter and would like to "
            f"discuss a permanent disability advance with your client.",

            f"Based on the current medical evidence, we are prepared to offer a permanent disability "
            f"advance of ${pd_amount:,} to {self.case.applicant.full_name}. This advance would be "
            f"subject to standard credit provisions. {self.lorem_correspondence(1)}",

            f"Please advise if your client is interested in accepting this advance. We believe this "
            f"represents a fair evaluation based on the medical reporting to date. Feel free to contact "
            f"me to discuss this matter further."
        ]

    def _settlement_discussion(self):
        """Settlement offer discussion"""
        return [
            f"I am writing to initiate discussions regarding potential resolution of the above-referenced "
            f"workers' compensation claim for {self.case.applicant.full_name}.",

            f"We have reviewed the medical reports and believe there may be an opportunity to resolve "
            f"this matter through a Compromise and Release or Stipulated Award. {self.lorem_correspondence(1)} "
            f"We would appreciate your client's current treatment status and any updated medical reports.",

            f"Please let me know if your client is interested in exploring settlement options. I am "
            f"available to discuss the value and terms of a potential resolution at your convenience. "
            f"We remain committed to resolving this claim fairly and expeditiously."
        ]

    def _medical_records_request(self):
        """Request for additional medical records"""
        return [
            f"We are in the process of evaluating the above-referenced claim and require additional "
            f"medical documentation to properly assess {self.case.applicant.full_name}'s current medical status.",

            f"Specifically, we request copies of all medical reports from {self.case.treating_physician.full_name} "
            f"for the past 90 days, including any work status reports or requests for changes in treatment. "
            f"{self.lorem_correspondence(1)}",

            f"Please provide these records at your earliest convenience. Timely receipt of this information "
            f"will help us ensure continued authorization of appropriate medical treatment and evaluation "
            f"of any disability claims. Thank you for your cooperation in this matter."
        ]

    def _ur_decision(self):
        """Utilization review decision notification"""
        treatment_type = random.choice([
            "MRI of the lumbar spine",
            "physical therapy beyond 12 visits",
            "pain management consultation",
            "surgical intervention",
            "psychological treatment"
        ])

        return [
            f"This letter serves to notify you that a Utilization Review determination has been made "
            f"regarding the request for {treatment_type} for {self.case.applicant.full_name}.",

            f"After review by our medical consultant, the requested treatment has been "
            f"{random.choice(['approved', 'modified', 'denied'])} based on the Medical Treatment Utilization "
            f"Schedule guidelines. {self.lorem_correspondence(1)} A detailed UR decision letter is being "
            f"sent separately to your client and the treating physician.",

            f"If you disagree with this determination, you have the right to request Independent Medical "
            f"Review through the Administrative Director within 30 days of receipt of this decision. "
            f"Please contact me if you have any questions about this determination."
        ]
