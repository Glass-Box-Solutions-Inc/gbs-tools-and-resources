"""
Notice of Taking Deposition template for Workers' Compensation discovery.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from pdf_templates.base_template import BaseTemplate
from reportlab.platypus import Paragraph, Spacer
from reportlab.lib.units import inch
from datetime import timedelta
import random


class DepositionNotice(BaseTemplate):
    """Generates a Notice of Taking Deposition."""

    def build_story(self, doc_spec):
        """Build the deposition notice story."""
        story = []

        # Letterhead
        story.extend(self.make_letterhead(
            self.case.insurance.defense_firm,
            "123 Legal Plaza, Suite 500",
            self.case.insurance.defense_phone
        ))
        story.append(Spacer(1, 0.3 * inch))

        # Title
        story.append(Paragraph("NOTICE OF TAKING DEPOSITION", self.styles["CenterBold"]))
        story.append(Spacer(1, 0.3 * inch))

        # Case caption
        case_caption = f"""
        <b>{self.case.applicant.full_name.upper()},</b><br/>
        <br/>
        &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Applicant,<br/>
        <br/>
        vs.<br/>
        <br/>
        <b>{self.case.employer.company_name.upper()},</b><br/>
        <br/>
        &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Defendant.
        """
        story.append(Paragraph(case_caption, self.styles["BodyText14"]))
        story.append(Spacer(1, 0.2 * inch))

        # ADJ number
        story.append(Paragraph(f"<b>ADJ No.: {self.case.injuries[0].adj_number}</b>", self.styles["BodyText14"]))
        story.append(Spacer(1, 0.3 * inch))

        # TO line (applicant's attorney or unrepresented applicant)
        story.append(Paragraph(f"<b>TO: {self.case.applicant.full_name}</b>", self.styles["BodyText14"]))
        story.append(Paragraph("Applicant in Pro Per", self.styles["BodyText14"]))
        story.append(Spacer(1, 0.2 * inch))

        # Determine deponent
        deponent_is_applicant = random.random() > 0.4

        if deponent_is_applicant:
            deponent_name = self.case.applicant.full_name
            deponent_type = "Applicant"
            documents_list = [
                "All tax returns for the three years prior to the date of injury",
                "All pay stubs from defendant employer",
                "Any and all medical records in your possession",
                "Any correspondence with the insurance carrier or adjuster",
                "Any photographs of the injury or accident scene"
            ]
        else:
            deponent_name = self.case.treating_physician.full_name
            deponent_type = f"Treating Physician ({self.case.treating_physician.specialty})"
            documents_list = [
                "Complete medical chart for the patient",
                "All diagnostic test results and imaging reports",
                "Treatment notes and progress reports",
                "Billing records and CPT codes",
                "Any correspondence regarding the patient's treatment"
            ]

        # Notice text
        depo_date = doc_spec.doc_date + timedelta(days=random.randint(21, 45))
        is_remote = random.random() > 0.5

        if is_remote:
            location_text = "via Zoom videoconference (link to be provided)"
        else:
            location_text = f"""{self.case.insurance.defense_firm}<br/>
            123 Legal Plaza, Suite 500<br/>
            Conference Room A"""

        notice_text = f"""
        <b>PLEASE TAKE NOTICE</b> that the deposition of <b>{deponent_name}</b>,
        {deponent_type}, will be taken before a certified shorthand reporter on:
        """
        story.append(Paragraph(notice_text, self.styles["BodyText14"]))
        story.append(Spacer(1, 0.2 * inch))

        # Deposition details
        details_text = f"""
        <b>DATE:</b> {depo_date.strftime('%B %d, %Y')}<br/>
        <b>TIME:</b> 10:00 A.M.<br/>
        <b>LOCATION:</b><br/>
        {location_text}
        """
        story.append(Paragraph(details_text, self.styles["BodyText14"]))
        story.append(Spacer(1, 0.2 * inch))

        # Recording notice
        recording_text = """
        The deposition will be recorded by stenographic means by a certified court reporter.
        The deponent may be examined regarding any matter, not privileged, that is relevant
        to the subject matter of this action.
        """
        story.append(Paragraph(recording_text, self.styles["BodyText14"]))
        story.append(Spacer(1, 0.2 * inch))

        # Documents to bring
        story.append(Paragraph("<b>DOCUMENTS TO BE PRODUCED:</b>", self.styles["SectionHeader"]))
        story.append(Spacer(1, 0.1 * inch))

        story.append(Paragraph(
            "The deponent is requested to bring the following documents to the deposition:",
            self.styles["BodyText14"]
        ))
        story.append(Spacer(1, 0.1 * inch))

        for item in documents_list:
            story.append(Paragraph(f"• {item}", self.styles["BodyText14"]))
        story.append(Spacer(1, 0.3 * inch))

        # Objections notice
        objections_text = """
        If you have any objections to this deposition or the production of documents,
        you must file written objections with the Workers' Compensation Appeals Board
        and serve them on all parties at least three days prior to the scheduled deposition date.
        """
        story.append(Paragraph(objections_text, self.styles["BodyText14"]))
        story.append(Spacer(1, 0.3 * inch))

        # Signature block
        story.append(Paragraph(f"DATED: {doc_spec.doc_date.strftime('%B %d, %Y')}", self.styles["BodyText14"]))
        story.append(Spacer(1, 0.3 * inch))

        state_bar = random.randint(100000, 399999)
        signature_text = f"""
        {self.case.insurance.defense_attorney}<br/>
        State Bar No. {state_bar}<br/>
        Attorney for Defendant<br/>
        {self.case.insurance.defense_firm}
        """
        story.append(Paragraph(signature_text, self.styles["BodyText14"]))

        return story
