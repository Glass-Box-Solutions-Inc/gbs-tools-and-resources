"""
Court Notice Template

Generates WCAB hearing notices with case caption, hearing details, and issues.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from pdf_templates.base_template import BaseTemplate
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
import random
from datetime import timedelta


class CourtNotice(BaseTemplate):
    """WCAB hearing notice template"""

    def build_story(self, doc_spec):
        story = []

        # WCAB Header
        story.append(Spacer(1, 0.5 * inch))
        story.append(Paragraph(
            "WORKERS' COMPENSATION APPEALS BOARD",
            self.styles['CenterBold']
        ))
        story.append(Paragraph(
            "STATE OF CALIFORNIA",
            self.styles['CenterBold']
        ))
        story.append(Spacer(1, 0.3 * inch))
        story.append(self.make_hr())
        story.append(Spacer(1, 0.3 * inch))

        # Title
        story.append(Paragraph(
            "NOTICE OF HEARING",
            self.styles['CenterBold']
        ))
        story.append(Spacer(1, 0.4 * inch))

        # Case Caption
        caption_data = [
            [Paragraph(f"<b>{self.case.applicant.full_name.upper()}</b>,", self.styles['BodyText14']), ""],
            [Paragraph("Applicant,", self.styles['BodyText14']), ""],
            ["", ""],
            [Paragraph("vs.", self.styles['BodyText14']), Paragraph(f"<b>Case No.:</b> ADJ {self.case.injuries[0].adj_number}", self.styles['BodyText14'])],
            ["", ""],
            [Paragraph(f"<b>{self.case.employer.company_name.upper()}</b>,", self.styles['BodyText14']), Paragraph(f"<b>Venue:</b> {self.case.venue}", self.styles['BodyText14'])],
            [Paragraph("Employer; and", self.styles['BodyText14']), ""],
            ["", ""],
            [Paragraph(f"<b>{self.case.insurance.carrier_name.upper()}</b>,", self.styles['BodyText14']), Paragraph(f"<b>Judge:</b> {self.case.judge_name}", self.styles['BodyText14'])],
            [Paragraph("Insurance Carrier,", self.styles['BodyText14']), ""],
            ["", ""],
            [Paragraph("Defendants.", self.styles['BodyText14']), ""],
        ]

        caption_table = Table(caption_data, colWidths=[4 * inch, 2.5 * inch])
        caption_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ]))
        story.append(caption_table)
        story.append(Spacer(1, 0.3 * inch))
        story.append(self.make_hr())
        story.append(Spacer(1, 0.3 * inch))

        # Hearing Details
        hearing_date = doc_spec.doc_date + timedelta(days=random.randint(30, 60))
        hearing_time = random.choice(["9:00 AM", "10:00 AM", "1:30 PM", "2:00 PM"])
        hearing_type = random.choice([
            "Mandatory Settlement Conference",
            "Status Conference",
            "Trial",
            "Priority Conference",
            "Pre-Trial Conference"
        ])

        story.append(Paragraph("<b>NOTICE IS HEREBY GIVEN</b> that the above-entitled matter is set for:", self.styles['BodyText14']))
        story.append(Spacer(1, 0.2 * inch))

        hearing_data = [
            [Paragraph("<b>HEARING TYPE:</b>", self.styles['BodyText14']), Paragraph(hearing_type, self.styles['BodyText14'])],
            [Paragraph("<b>DATE:</b>", self.styles['BodyText14']), Paragraph(hearing_date.strftime('%B %d, %Y'), self.styles['BodyText14'])],
            [Paragraph("<b>TIME:</b>", self.styles['BodyText14']), Paragraph(hearing_time, self.styles['BodyText14'])],
            [Paragraph("<b>LOCATION:</b>", self.styles['BodyText14']), Paragraph(f"Workers' Compensation Appeals Board<br/>{self.case.venue} District Office", self.styles['BodyText14'])],
            [Paragraph("<b>JUDGE:</b>", self.styles['BodyText14']), Paragraph(f"Hon. {self.case.judge_name}", self.styles['BodyText14'])],
        ]

        hearing_table = Table(hearing_data, colWidths=[1.5 * inch, 4.5 * inch])
        hearing_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        story.append(hearing_table)
        story.append(Spacer(1, 0.3 * inch))

        # Issues to be addressed
        story.append(Paragraph("<b>ISSUES TO BE ADDRESSED:</b>", self.styles['BodyText14']))
        story.append(Spacer(1, 0.1 * inch))

        # Generate 3-5 issues based on hearing type
        issues = self._generate_issues(hearing_type)
        for i, issue in enumerate(issues, 1):
            story.append(Paragraph(f"{i}. {issue}", self.styles['BodyText14']))
            story.append(Spacer(1, 0.08 * inch))

        story.append(Spacer(1, 0.3 * inch))

        # Notice requirements
        if hearing_type == "Mandatory Settlement Conference":
            notice_text = (
                "<b>SETTLEMENT CONFERENCE REQUIREMENTS:</b> All parties and/or their representatives "
                "with full settlement authority must be present at the conference. Failure to appear "
                "with settlement authority may result in the imposition of sanctions pursuant to Labor "
                "Code Section 5813."
            )
        elif hearing_type == "Trial":
            notice_text = (
                "<b>TRIAL REQUIREMENTS:</b> All parties must be prepared to present evidence and testimony. "
                "All witnesses must be present or available. Failure to appear may result in the matter "
                "being submitted on the record or the issuance of sanctions."
            )
        else:
            notice_text = (
                "<b>APPEARANCE REQUIRED:</b> All parties or their representatives must appear at the "
                "scheduled time. Failure to appear may result in the imposition of sanctions pursuant "
                "to Labor Code Section 5813 and may adversely affect your rights in this case."
            )

        story.append(Paragraph(notice_text, self.styles['BodyText14']))
        story.append(Spacer(1, 0.3 * inch))

        # Continuance policy
        story.append(Paragraph(
            "<b>CONTINUANCES:</b> Requests for continuance must be made in writing and filed at least "
            "10 days prior to the hearing date, absent good cause shown. Continuances are not favored "
            "and will be granted only for good cause.",
            self.styles['BodyText14']
        ))
        story.append(Spacer(1, 0.3 * inch))

        # Electronic filing notice
        story.append(Paragraph(
            "<b>DOCUMENTS:</b> All documents to be considered at the hearing must be filed and served "
            "on all parties at least 10 days before the hearing date pursuant to WCAB Rule 10845.",
            self.styles['BodyText14']
        ))
        story.append(Spacer(1, 0.4 * inch))

        # Dated line
        story.append(Paragraph(
            f"DATED: {doc_spec.doc_date.strftime('%B %d, %Y')}",
            self.styles['BodyText14']
        ))
        story.append(Spacer(1, 0.5 * inch))

        # Clerk signature
        story.append(Paragraph(
            "_________________________________",
            self.styles['BodyText14']
        ))
        story.append(Paragraph(
            "Clerk of the Workers' Compensation Appeals Board",
            self.styles['BodyText14']
        ))

        return story

    def _generate_issues(self, hearing_type):
        """Generate relevant issues based on hearing type"""

        # Common issues pool
        issues_pool = {
            "injury": [
                f"Whether applicant sustained injury to {', '.join(self.case.injuries[0].body_parts)} arising out of and in the course of employment",
                "Nature and extent of industrial injury",
                "Body parts claimed to be injured"
            ],
            "td": [
                "Temporary disability benefits from date of injury to present",
                "Whether applicant is entitled to ongoing temporary disability",
                "Rate of temporary disability"
            ],
            "pd": [
                "Permanent disability and need for future medical treatment",
                "Percentage of permanent disability",
                "Apportionment of permanent disability"
            ],
            "medical": [
                "Whether proposed medical treatment is reasonable and necessary",
                "Selection of primary treating physician",
                "Need for further medical evaluation"
            ],
            "penalties": [
                "Whether defendant is liable for penalties and interest for late payment",
                "Whether defendant acted with unreasonable delay",
                "Self-imposed increase in temporary disability"
            ],
            "settlement": [
                "Settlement value and terms",
                "Future medical treatment provisions",
                "Compromise and Release vs. Stipulated Award"
            ]
        }

        if hearing_type == "Mandatory Settlement Conference":
            selected = random.sample(issues_pool["settlement"], 2) + \
                      random.sample(issues_pool["pd"], 1) + \
                      random.sample(issues_pool["medical"], 1)
        elif hearing_type == "Trial":
            selected = random.sample(issues_pool["injury"], 1) + \
                      random.sample(issues_pool["td"], 1) + \
                      random.sample(issues_pool["pd"], 2)
        elif hearing_type == "Priority Conference":
            selected = random.sample(issues_pool["td"], 1) + \
                      random.sample(issues_pool["medical"], 1) + \
                      random.sample(issues_pool["penalties"], 1)
        else:  # Status/Pre-Trial
            selected = random.sample(issues_pool["injury"], 1) + \
                      random.sample(issues_pool["medical"], 1) + \
                      [random.choice(["Discovery status and completion", "Readiness for trial", "Outstanding depositions"])]

        # Return 3-5 issues
        return random.sample(selected, min(len(selected), random.randint(3, 5)))
