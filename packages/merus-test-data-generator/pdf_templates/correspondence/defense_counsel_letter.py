"""
Defense Counsel Letter Template

Generates letters from defense attorneys to applicant's counsel,
including discovery requests, deposition scheduling, and settlement discussions.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from pdf_templates.base_template import BaseTemplate
from reportlab.platypus import Paragraph, Spacer
from reportlab.lib.units import inch
import random
from datetime import timedelta


class DefenseCounselLetter(BaseTemplate):
    """Defense attorney correspondence template"""

    def build_story(self, doc_spec):
        story = []

        # Law firm letterhead
        firm_address = f"{random.randint(100, 9999)} Tower Boulevard\n" \
                      f"Floor {random.randint(10, 45)}\n" \
                      f"Los Angeles, CA 9001{random.randint(1, 9)}"

        story.extend(self.make_letterhead(
            self.case.insurance.defense_firm,
            firm_address,
            self.case.insurance.defense_phone
        ))
        story.append(Spacer(1, 0.3 * inch))

        # Date
        story.append(self.make_date_line("Date", doc_spec.doc_date))
        story.append(Spacer(1, 0.2 * inch))

        # Via Email and U.S. Mail
        story.append(Paragraph("<i>Via Email and U.S. Mail</i>", self.styles['SmallItalic']))
        story.append(Spacer(1, 0.2 * inch))

        # Addressed to applicant's attorney
        addressee = f"Applicant's Attorney, Esq.<br/>" \
                   f"Law Offices of Workers' Rights<br/>" \
                   f"{random.randint(100, 9999)} Legal Plaza<br/>" \
                   f"Oakland, CA 9460{random.randint(1, 9)}"
        story.append(Paragraph(addressee, self.styles['BodyText14']))
        story.append(Spacer(1, 0.2 * inch))

        # Re: line
        re_text = f"<b>Re:</b> {self.case.applicant.full_name} v. {self.case.employer.company_name}<br/>" \
                  f"&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;ADJ {self.case.injuries[0].adj_number}<br/>" \
                  f"&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Date of Injury: {self.case.injuries[0].date_of_injury.strftime('%m/%d/%Y')}"
        story.append(Paragraph(re_text, self.styles['BodyText14']))
        story.append(Spacer(1, 0.3 * inch))

        # Salutation
        story.append(Paragraph("Dear Counsel:", self.styles['BodyText14']))
        story.append(Spacer(1, 0.2 * inch))

        # Body - randomly select letter type
        letter_types = [
            self._discovery_request,
            self._deposition_scheduling,
            self._qme_panel_request,
            self._settlement_discussion,
            self._motion_to_compel
        ]

        letter_content = random.choice(letter_types)()
        for para in letter_content:
            story.append(Paragraph(para, self.styles['DoubleSpaced']))
            story.append(Spacer(1, 0.15 * inch))

        # Closing
        story.append(Spacer(1, 0.2 * inch))
        story.append(Paragraph("Very truly yours,", self.styles['BodyText14']))
        story.append(Spacer(1, 0.5 * inch))

        # Signature block
        story.extend(self.make_signature_block(
            f"{self.case.insurance.defense_attorney}, Esq.",
            "Attorney for Defendants",
            None
        ))

        return story

    def _discovery_request(self):
        """Discovery request letter"""
        return [
            f"This office represents {self.case.employer.company_name} and {self.case.insurance.carrier_name} "
            f"in the above-referenced workers' compensation matter. Pursuant to California Code of Regulations, "
            f"Title 8, Section 10536, we hereby request responses to the following discovery.",

            f"Please provide copies of all medical reports, records, and billing statements for treatment "
            f"received by {self.case.applicant.full_name} related to the alleged industrial injury of "
            f"{self.case.injuries[0].date_of_injury.strftime('%B %d, %Y')}. Additionally, we request all "
            f"employment records, including hiring documents, performance evaluations, attendance records, "
            f"and wage statements for the period of {(self.case.injuries[0].date_of_injury - timedelta(days=365)).strftime('%B %d, %Y')} "
            f"through present.",

            f"We further request your client's written responses to Defendant's Form Interrogatories "
            f"(enclosed) within thirty (30) days of the date of this letter. Should you require an extension "
            f"of time to respond, please contact this office immediately. We appreciate your cooperation in "
            f"this matter and look forward to your timely response."
        ]

    def _deposition_scheduling(self):
        """Deposition scheduling letter"""
        depo_date = self.case.injuries[0].date_of_injury + timedelta(days=random.randint(180, 365))

        return [
            f"Pursuant to Labor Code Section 5710 and California Code of Regulations, Title 8, Section 10536, "
            f"we hereby notice the deposition of {self.case.applicant.full_name} in the above-referenced matter.",

            f"The deposition is scheduled for {depo_date.strftime('%B %d, %Y')} at 10:00 a.m. at our offices "
            f"located at the address listed above. We anticipate the deposition will last approximately "
            f"three (3) hours. A certified court reporter will be present to record the proceedings.",

            f"Please confirm your client's availability for this date at your earliest convenience. Should "
            f"this date present a conflict, please contact me within ten (10) days to discuss alternative "
            f"dates. We request that your client bring any and all medical records in their possession related "
            f"to the claimed injury. Thank you for your anticipated cooperation."
        ]

    def _qme_panel_request(self):
        """QME panel request letter"""
        specialty = random.choice([
            "Orthopedic Surgery",
            "Neurology",
            "Internal Medicine",
            "Pain Management",
            "Psychiatry"
        ])

        return [
            f"The parties have been unable to agree upon a primary treating physician or Agreed Medical "
            f"Evaluator in the above-referenced matter. Accordingly, pursuant to Labor Code Section 4062.2, "
            f"we request a Qualified Medical Evaluator panel in the specialty of {specialty}.",

            f"The disputed medical issues include the nature and extent of injury to {', '.join(self.case.injuries[0].body_parts)}, "
            f"need for further medical treatment, apportionment, and permanent disability. We believe an "
            f"independent medical evaluation is necessary to properly assess these issues and facilitate "
            f"resolution of this claim.",

            f"Please advise within ten (10) days if you agree to this request. If we do not hear from you, "
            f"we will proceed with filing the necessary panel request with the Medical Unit of the Division "
            f"of Workers' Compensation. Should you prefer to discuss an Agreed Medical Evaluator in lieu of "
            f"a panel, I am available to confer at your convenience."
        ]

    def _settlement_discussion(self):
        """Settlement discussion letter"""
        return [
            f"I am writing to explore the possibility of resolving the above-referenced workers' compensation "
            f"claim through a Compromise and Release Agreement. Our review of the medical evidence and file "
            f"suggests that there may be an opportunity for mutually agreeable resolution.",

            f"Based upon the medical reports of {self.case.treating_physician.full_name} and consideration of your "
            f"client's age, occupation, and the nature of the alleged injury, we believe there is room for "
            f"meaningful settlement discussions. We are prepared to engage in good faith negotiations to "
            f"resolve all aspects of this claim, including permanent disability, future medical treatment, "
            f"and any outstanding temporary disability.",

            f"Please advise whether your client is amenable to settlement discussions at this time. If so, "
            f"I would appreciate receiving your settlement demand and any supporting documentation you believe "
            f"would be helpful in our evaluation. I am available to discuss this matter at your convenience "
            f"and look forward to the possibility of reaching a resolution that is fair and acceptable to all parties."
        ]

    def _motion_to_compel(self):
        """Motion to compel notice"""
        discovery_type = random.choice([
            "Form Interrogatories",
            "medical records",
            "employment records",
            "deposition testimony",
            "Special Interrogatories"
        ])

        return [
            f"This office served {discovery_type} upon your client on {(self.case.injuries[0].date_of_injury + timedelta(days=60)).strftime('%B %d, %Y')}. "
            f"To date, we have not received responses to said discovery despite the expiration of the time "
            f"for response set forth in the California Code of Regulations, Title 8, Section 10536.",

            f"Pursuant to Labor Code Section 5710, we hereby demand that you provide complete responses to "
            f"the outstanding discovery within fifteen (15) days of the date of this letter. Failure to "
            f"provide said responses will result in the filing of a Petition for Order Compelling Discovery "
            f"with the Workers' Compensation Appeals Board.",

            f"Please be advised that should we be required to file a petition to compel, we will seek an "
            f"order for sanctions and attorney's fees pursuant to Labor Code Section 5813. We trust this "
            f"will not be necessary and that you will provide the requested discovery forthwith. If there "
            f"are any legitimate objections to the discovery requests, please contact me immediately so that "
            f"we may attempt to resolve these issues without the need for judicial intervention."
        ]
