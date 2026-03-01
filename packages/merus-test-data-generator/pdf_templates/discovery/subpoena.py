"""
Subpoena Duces Tecum template for Workers' Compensation discovery.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from pdf_templates.base_template import BaseTemplate
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
from datetime import timedelta
import random


class Subpoena(BaseTemplate):
    """Generates a Subpoena Duces Tecum for medical records."""

    def build_story(self, doc_spec):
        """Build the subpoena document story."""
        story = []

        # Header
        story.append(Paragraph("WORKERS' COMPENSATION APPEALS BOARD", self.styles["CenterBold"]))
        story.append(Spacer(1, 0.2 * inch))
        story.append(Paragraph("STATE OF CALIFORNIA", self.styles["CenterBold"]))
        story.append(Spacer(1, 0.3 * inch))

        # Title
        story.append(Paragraph("SUBPOENA DUCES TECUM", self.styles["CenterBold"]))
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

        # Select custodian facility
        if random.random() > 0.3 and self.case.treating_physician.facility:
            facility_name = self.case.treating_physician.facility
        else:
            facilities = [
                "Community Medical Center",
                "Regional Orthopedic Clinic",
                "Valley Imaging Center",
                "Central Coast Medical Group",
                "Pacific Pain Management",
                "Advanced Spine Institute"
            ]
            facility_name = random.choice(facilities)

        # TO line
        story.append(Paragraph(f"<b>TO: Custodian of Records</b><br/>{facility_name}", self.styles["BodyText14"]))
        story.append(Spacer(1, 0.2 * inch))

        # Command
        command_text = f"""
        <b>YOU ARE HEREBY COMMANDED</b> to produce for inspection and copying the following documents,
        records, and things in your possession, custody, or control, relating to
        <b>{self.case.applicant.full_name}</b>, Date of Birth: {self.case.applicant.date_of_birth.strftime('%m/%d/%Y')}.
        """
        story.append(Paragraph(command_text, self.styles["BodyText14"]))
        story.append(Spacer(1, 0.2 * inch))

        # Records requested
        story.append(Paragraph("<b>RECORDS REQUESTED:</b>", self.styles["SectionHeader"]))
        story.append(Spacer(1, 0.1 * inch))

        records_list = [
            "All medical records, including but not limited to progress notes, treatment plans, and discharge summaries",
            "All billing records, including itemized statements and CPT codes",
            "All diagnostic imaging records, including X-rays, MRIs, CT scans, and radiology reports",
            "All laboratory test results and pathology reports",
            "All pharmacy records and medication lists",
            "All consultation reports and referral documentation",
            "All physical therapy, occupational therapy, and rehabilitation records"
        ]

        for item in records_list:
            story.append(Paragraph(f"• {item}", self.styles["BodyText14"]))
        story.append(Spacer(1, 0.2 * inch))

        # Date range
        date_range_text = f"""
        <b>DATE RANGE:</b> From {self.case.injuries[0].date_of_injury.strftime('%m/%d/%Y')}
        through the present date.
        """
        story.append(Paragraph(date_range_text, self.styles["BodyText14"]))
        story.append(Spacer(1, 0.2 * inch))

        # Production details
        return_date = doc_spec.doc_date + timedelta(days=30)
        production_text = f"""
        <b>PRODUCTION DATE:</b> {return_date.strftime('%B %d, %Y')}<br/>
        <br/>
        <b>PRODUCTION LOCATION:</b><br/>
        Workers' Compensation Appeals Board<br/>
        {self.case.venue}<br/>
        California
        """
        story.append(Paragraph(production_text, self.styles["BodyText14"]))
        story.append(Spacer(1, 0.2 * inch))

        # Compliance instructions
        story.append(Paragraph("<b>COMPLIANCE INSTRUCTIONS:</b>", self.styles["SectionHeader"]))
        story.append(Spacer(1, 0.1 * inch))

        compliance_text = """
        Records may be produced by mail or in person. If records are produced by mail,
        they must be accompanied by a declaration under penalty of perjury attesting to their
        authenticity and completeness. All records must be clearly labeled with the case name
        and ADJ number. If the records cannot be produced by the specified date, you must
        notify the undersigned attorney immediately.
        """
        story.append(Paragraph(compliance_text, self.styles["BodyText14"]))
        story.append(Spacer(1, 0.3 * inch))

        # Signature block
        story.append(Paragraph(f"DATED: {doc_spec.doc_date.strftime('%B %d, %Y')}", self.styles["BodyText14"]))
        story.append(Spacer(1, 0.3 * inch))

        # Attorney signature
        state_bar = random.randint(100000, 399999)
        signature_text = f"""
        {self.case.insurance.defense_attorney}<br/>
        State Bar No. {state_bar}<br/>
        {self.case.insurance.defense_firm}<br/>
        Attorney for Defendant
        """
        story.append(Paragraph(signature_text, self.styles["BodyText14"]))

        return story
