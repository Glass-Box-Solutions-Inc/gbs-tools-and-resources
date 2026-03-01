"""
Subpoenaed Records Cover Sheet template for Workers' Compensation discovery.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from pdf_templates.base_template import BaseTemplate
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
from datetime import timedelta
import random


class SubpoenaedRecords(BaseTemplate):
    """Generates a cover sheet for subpoenaed medical records."""

    def build_story(self, doc_spec):
        """Build the subpoenaed records cover sheet story."""
        story = []

        # Header
        story.append(Paragraph(
            "RECORDS RECEIVED PURSUANT TO SUBPOENA",
            self.styles["CenterBold"]
        ))
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

        # Select facility
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

        # Records from
        story.append(Paragraph("<b>RECORDS PRODUCED BY:</b>", self.styles["SectionHeader"]))
        story.append(Spacer(1, 0.1 * inch))
        story.append(Paragraph(facility_name, self.styles["BodyText14"]))
        story.append(Spacer(1, 0.2 * inch))

        # Date range
        end_date = doc_spec.doc_date
        date_range_text = f"""
        <b>DATE RANGE OF RECORDS:</b><br/>
        {self.case.injuries[0].date_of_injury.strftime('%m/%d/%Y')} through {end_date.strftime('%m/%d/%Y')}
        """
        story.append(Paragraph(date_range_text, self.styles["BodyText14"]))
        story.append(Spacer(1, 0.2 * inch))

        # Custodian declaration
        custodian_names = [
            "Maria Rodriguez",
            "James Patterson",
            "Susan Chen",
            "Michael Anderson",
            "Jennifer Davis"
        ]
        custodian_name = random.choice(custodian_names)

        declaration_text = f"""
        <b>CUSTODIAN OF RECORDS DECLARATION:</b><br/>
        <br/>
        I, {custodian_name}, am the duly authorized custodian of records for {facility_name}.
        I hereby certify under penalty of perjury under the laws of the State of California that
        the attached records are true and correct copies of records in the possession of {facility_name}
        pertaining to {self.case.applicant.full_name}.
        """
        story.append(Paragraph(declaration_text, self.styles["BodyText14"]))
        story.append(Spacer(1, 0.3 * inch))

        # Table of contents
        story.append(Paragraph("<b>TABLE OF CONTENTS - RECORDS PRODUCED:</b>", self.styles["SectionHeader"]))
        story.append(Spacer(1, 0.2 * inch))

        # Generate list of records
        record_types = [
            ("Office Visit Notes", random.randint(3, 8)),
            ("Initial Consultation Report", 2),
            ("Progress Notes", random.randint(4, 10)),
            ("Laboratory Test Results", random.randint(1, 4)),
            ("Imaging Reports (X-Ray/MRI/CT)", random.randint(1, 3)),
            ("Prescription Records", random.randint(2, 5)),
            ("Physical Therapy Notes", random.randint(3, 7)),
            ("Billing and Insurance Records", random.randint(2, 6)),
        ]

        # Randomly select 5-8 record types
        selected_records = random.sample(record_types, k=random.randint(5, 8))
        selected_records.sort(key=lambda x: x[0])

        # Create table data
        table_data = [["Record Type", "Pages"]]
        total_pages = 0

        for record_type, pages in selected_records:
            table_data.append([record_type, str(pages)])
            total_pages += pages

        # Add total row
        table_data.append(["<b>TOTAL PAGES:</b>", f"<b>{total_pages}</b>"])

        # Create and style table
        col_widths = [4.5 * inch, 1.5 * inch]
        records_table = Table(table_data, colWidths=col_widths)
        records_table.setStyle(TableStyle([
            # Header row
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),

            # Data rows
            ('FONTNAME', (0, 1), (-1, -2), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -2), 10),
            ('ALIGN', (0, 1), (0, -2), 'LEFT'),
            ('ALIGN', (1, 1), (1, -2), 'CENTER'),

            # Total row
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, -1), (-1, -1), 11),
            ('BACKGROUND', (0, -1), (-1, -1), colors.lightgrey),
            ('ALIGN', (0, -1), (0, -1), 'LEFT'),
            ('ALIGN', (1, -1), (1, -1), 'CENTER'),

            # All cells
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ]))

        story.append(records_table)
        story.append(Spacer(1, 0.3 * inch))

        # Date received
        date_received = doc_spec.doc_date + timedelta(days=random.randint(14, 28))
        story.append(Paragraph(
            f"<b>DATE RECEIVED:</b> {date_received.strftime('%B %d, %Y')}",
            self.styles["BodyText14"]
        ))
        story.append(Spacer(1, 0.3 * inch))

        # Certification statement
        cert_text = """
        <b>CERTIFICATION:</b><br/>
        <br/>
        I certify that the attached records are true and correct copies of the original records
        maintained by this facility. These records have been produced in response to a subpoena
        duces tecum issued in the above-referenced matter. The records are transmitted in
        accordance with California Evidence Code Section 1560 and related provisions.
        """
        story.append(Paragraph(cert_text, self.styles["BodyText14"]))
        story.append(Spacer(1, 0.3 * inch))

        # Custodian signature block
        story.append(Paragraph(
            f"DATED: {doc_spec.doc_date.strftime('%B %d, %Y')}",
            self.styles["BodyText14"]
        ))
        story.append(Spacer(1, 0.4 * inch))

        signature_text = f"""
        _______________________________<br/>
        {custodian_name}<br/>
        Custodian of Records<br/>
        {facility_name}
        """
        story.append(Paragraph(signature_text, self.styles["BodyText14"]))
        story.append(Spacer(1, 0.3 * inch))

        # Privacy notice
        privacy_text = """
        <i><b>PRIVACY NOTICE:</b> These records contain confidential medical information protected by
        state and federal privacy laws. Unauthorized disclosure or use of this information may subject
        you to civil or criminal penalties. These records should be handled, stored, and disposed of
        in accordance with applicable privacy regulations.</i>
        """
        story.append(Paragraph(privacy_text, self.styles["SmallItalic"]))

        return story
