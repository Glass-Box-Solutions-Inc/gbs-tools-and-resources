"""
Minutes of Hearing and Orders.
1-2 page official hearing record from WCAB.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import random
from datetime import timedelta
from typing import Any

from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import HRFlowable, Paragraph, Spacer, Table, TableStyle

from pdf_templates.base_template import BaseTemplate


class MinutesOrders(BaseTemplate):
    """Minutes of Hearing and Orders."""

    def build_story(self, doc_spec: Any) -> list:
        story = []
        a = self.case.applicant
        emp = self.case.employer
        ins = self.case.insurance
        inj = self.case.injuries[0]

        # Header
        story.append(Paragraph("WORKERS' COMPENSATION APPEALS BOARD", self.styles["Letterhead"]))
        story.append(Paragraph("STATE OF CALIFORNIA", self.styles["CenterBold"]))
        story.append(Spacer(1, 12))
        story.append(self.make_hr())
        story.append(Spacer(1, 12))

        # Case caption
        caption_data = [
            [Paragraph(f"<b>{a.full_name}</b>", self.styles["TableCell"]), "",
             Paragraph(f"<b>ADJ No.:</b> {inj.adj_number}", self.styles["TableCell"])],
            [Paragraph("Applicant", self.styles["TableCell"]), "", ""],
            ["", "", Paragraph(f"<b>Venue:</b> {self.case.venue}", self.styles["TableCell"])],
            [Paragraph("vs.", self.styles["TableCell"]), "", ""],
            ["", "", Paragraph(f"<b>Judge:</b> {self.case.judge_name}", self.styles["TableCell"])],
            [Paragraph(f"<b>{emp.company_name}</b>", self.styles["TableCell"]), "", ""],
            [Paragraph("Employer", self.styles["TableCell"]), "", ""],
            ["", "", ""],
            [Paragraph(f"{ins.carrier_name}", self.styles["TableCell"]), "", ""],
            [Paragraph("Defendants", self.styles["TableCell"]), "", ""],
        ]

        t = Table(caption_data, colWidths=[3*inch, 1.5*inch, 2*inch])
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(t)
        story.append(Spacer(1, 18))

        # Title
        story.append(Paragraph("MINUTES OF HEARING AND ORDERS", self.styles["CenterBold"]))
        story.append(Spacer(1, 12))

        # Hearing information
        story.append(Paragraph("HEARING INFORMATION", self.styles["SectionHeader"]))

        hearing_types = [
            "Mandatory Settlement Conference",
            "Priority Conference",
            "Status Conference",
            "Trial"
        ]
        hearing_type = random.choice(hearing_types)

        # Generate hearing time
        hearing_hour = random.randint(9, 15)
        hearing_minute = random.choice([0, 15, 30, 45])
        hearing_time = f"{hearing_hour}:{hearing_minute:02d} {'AM' if hearing_hour < 12 else 'PM'}"

        hearing_data = [
            ["Hearing Date:", doc_spec.doc_date.strftime("%B %d, %Y")],
            ["Hearing Time:", hearing_time],
            ["Hearing Type:", hearing_type],
            ["Judge:", self.case.judge_name],
            ["Venue:", self.case.venue],
        ]

        t = Table(hearing_data, colWidths=[2*inch, 4.5*inch])
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(t)
        story.append(Spacer(1, 12))

        # Appearances
        story.append(Paragraph("APPEARANCES", self.styles["SectionHeader"]))

        appearances = [
            f"For Applicant: [Attorney Name], Esq., State Bar No. XXXXXX",
            f"For Defendant {emp.company_name}: {ins.defense_attorney}, Esq., {ins.defense_firm}",
            "Applicant did not appear in person.",
        ]

        for appearance in appearances:
            story.append(Paragraph(appearance, self.styles["BodyText14"]))
            story.append(Spacer(1, 4))

        story.append(Spacer(1, 12))

        # Proceedings
        story.append(Paragraph("SUMMARY OF PROCEEDINGS", self.styles["SectionHeader"]))

        proceedings_options = [
            f"The matter came on regularly for {hearing_type}. Counsel for both parties appeared and the matter was discussed at length. "
            f"The parties have been unable to reach a settlement agreement at this time. The Court reviewed the status of medical "
            f"reports and discovery. Issues in dispute include permanent disability, need for future medical treatment, and apportionment.",

            f"This {hearing_type} was held as scheduled. Both parties appeared through counsel. The Court reviewed the file and "
            f"heard argument from counsel regarding the disputed issues. The parties reported that medical discovery is ongoing. "
            f"Defendant's counsel indicated that additional time is needed to complete vocational rehabilitation evaluation.",

            f"The hearing proceeded with both parties present through their respective counsel. The Court inquired as to the status "
            f"of discovery and settlement negotiations. Applicant's counsel reported that the treating physician has issued a final "
            f"report declaring the applicant permanent and stationary. The parties discussed potential settlement but were unable to "
            f"reach agreement on the value of permanent disability.",
        ]

        proceedings_text = random.choice(proceedings_options)
        story.append(Paragraph(proceedings_text, self.styles["DoubleSpaced"]))
        story.append(Spacer(1, 12))

        # Orders
        story.append(Paragraph("ORDERS", self.styles["SectionHeader"]))
        story.append(Paragraph("Based on the proceedings, the Workers' Compensation Appeals Board makes the following orders:",
                              self.styles["BodyText14"]))
        story.append(Spacer(1, 8))

        # Generate future dates
        discovery_deadline = doc_spec.doc_date + timedelta(days=random.randint(30, 60))
        deposition_date = doc_spec.doc_date + timedelta(days=random.randint(45, 90))
        next_hearing_date = doc_spec.doc_date + timedelta(days=random.randint(60, 120))

        order_options = [
            f"1. Discovery is to be completed by {discovery_deadline.strftime('%B %d, %Y')}. All medical reports, "
            f"employment records, and expert opinions shall be exchanged by that date.",

            f"2. Deposition of {self.case.qme_physician.full_name if self.case.qme_physician else 'the Qualified Medical Evaluator'} "
            f"is authorized and shall be scheduled for a date on or before {deposition_date.strftime('%B %d, %Y')}.",

            f"3. Applicant's counsel shall provide updated wage loss calculations and permanent disability rating within 30 days.",

            f"4. Defendant shall authorize and schedule an evaluation with an Agreed Medical Evaluator within 45 days.",

            f"5. The parties are ordered to participate in a settlement conference call with the Court within 60 days to discuss "
            f"potential resolution of all disputed issues.",

            f"6. All discovery disputes shall be brought to the Court's attention by way of a properly noticed Declaration of Readiness.",
        ]

        selected_orders = random.sample(order_options, random.randint(3, 4))

        for order in selected_orders:
            story.append(Paragraph(order, self.styles["BodyText14"]))
            story.append(Spacer(1, 6))

        story.append(Spacer(1, 12))

        # Next hearing
        story.append(Paragraph("NEXT HEARING", self.styles["SectionHeader"]))

        next_hearing_types = ["Mandatory Settlement Conference", "Status Conference", "Trial"]
        next_hearing_type = random.choice(next_hearing_types)

        next_hearing_hour = random.randint(9, 15)
        next_hearing_minute = random.choice([0, 15, 30, 45])
        next_hearing_time = f"{next_hearing_hour}:{next_hearing_minute:02d} {'AM' if next_hearing_hour < 12 else 'PM'}"

        next_hearing_data = [
            ["Date:", next_hearing_date.strftime("%B %d, %Y")],
            ["Time:", next_hearing_time],
            ["Type:", next_hearing_type],
            ["Judge:", self.case.judge_name],
        ]

        t = Table(next_hearing_data, colWidths=[1.5*inch, 5*inch])
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(t)
        story.append(Spacer(1, 18))

        # Judge signature
        story.append(Paragraph("IT IS SO ORDERED.", self.styles["BodyText14"]))
        story.append(Spacer(1, 12))

        story.append(self.make_date_line("Dated", doc_spec.doc_date))
        story.append(Spacer(1, 30))

        sig_data = [
            ["_________________________________"],
            [self.case.judge_name],
            ["Workers' Compensation Judge"],
            ["Workers' Compensation Appeals Board"],
        ]

        t = Table(sig_data, colWidths=[3*inch])
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("FONTNAME", (1, 0), (1, 0), "Helvetica-Bold"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LINEABOVE", (0, 0), (0, 0), 0.5, colors.black),
        ]))
        story.append(t)

        return story
