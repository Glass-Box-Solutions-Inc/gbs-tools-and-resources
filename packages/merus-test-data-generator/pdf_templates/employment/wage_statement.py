"""
Wage Statement Template

Generates employer wage statements showing pay history for injured workers.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from pdf_templates.base_template import BaseTemplate
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
from datetime import timedelta
import random


class WageStatement(BaseTemplate):
    """Employer wage statement with pay period details and AWW calculation."""

    def build_story(self, doc_spec):
        """Build the wage statement document."""
        story = []

        # Employer letterhead
        story.extend(
            self.make_letterhead(
                self.case.employer.company_name,
                f"{self.case.employer.address_street}, {self.case.employer.address_city}, CA {self.case.employer.address_zip}",
                self.case.employer.phone,
            )
        )
        story.append(Spacer(1, 0.3 * inch))

        # Title
        story.append(Paragraph("WAGE STATEMENT", self.styles["CenterBold"]))
        story.append(Spacer(1, 0.2 * inch))

        # Employee information
        story.append(Paragraph("Employee Information", self.styles["SectionHeader"]))
        emp_data = [
            ["Employee Name:", self.case.applicant.full_name],
            ["Social Security Number:", f"XXX-XX-{self.case.applicant.ssn_last_four}"],
            ["Position:", self.case.employer.position],
            ["Hire Date:", self.case.employer.hire_date.strftime("%m/%d/%Y")],
            ["Department:", self.case.employer.department or "General"],
        ]
        emp_table = Table(emp_data, colWidths=[2 * inch, 4 * inch])
        emp_table.setStyle(
            TableStyle(
                [
                    ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 10),
                    ("FONT", (1, 0), (1, -1), "Helvetica", 10),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        story.append(emp_table)
        story.append(Spacer(1, 0.25 * inch))

        # Pay period table
        story.append(Paragraph("Pay Period History", self.styles["SectionHeader"]))
        story.append(Spacer(1, 0.1 * inch))

        # Generate 8-12 pay periods (biweekly) covering ~3 months before DOI
        num_periods = random.randint(8, 12)
        doi = self.case.injuries[0].date_of_injury
        pay_data = [
            [
                "Pay Period",
                "Regular\nHours",
                "OT\nHours",
                "Hourly\nRate",
                "Regular\nPay",
                "OT Pay",
                "Gross Pay",
            ]
        ]

        total_gross = 0
        total_weeks = 0

        for i in range(num_periods):
            # Calculate pay period end date (biweekly periods going backwards from DOI)
            period_end = doi - timedelta(days=i * 14 + 1)
            period_start = period_end - timedelta(days=13)

            # Generate hours
            regular_hours = random.randint(75, 80)
            ot_hours = random.choice([0, 0, 0, 5, 8, 12, 15, 20])  # OT less common

            # Calculate pay
            hourly_rate = self.case.employer.hourly_rate
            regular_pay = regular_hours * hourly_rate
            ot_pay = ot_hours * hourly_rate * 1.5
            gross_pay = regular_pay + ot_pay

            total_gross += gross_pay
            total_weeks += 2  # biweekly

            pay_data.append(
                [
                    f"{period_start.strftime('%m/%d/%y')}-\n{period_end.strftime('%m/%d/%y')}",
                    str(regular_hours),
                    str(ot_hours) if ot_hours > 0 else "-",
                    f"${hourly_rate:.2f}",
                    f"${regular_pay:.2f}",
                    f"${ot_pay:.2f}" if ot_hours > 0 else "-",
                    f"${gross_pay:.2f}",
                ]
            )

        pay_table = Table(
            pay_data,
            colWidths=[
                1.2 * inch,
                0.7 * inch,
                0.6 * inch,
                0.7 * inch,
                0.9 * inch,
                0.7 * inch,
                0.9 * inch,
            ],
        )
        pay_table.setStyle(
            TableStyle(
                [
                    ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
                    ("FONT", (0, 1), (-1, -1), "Helvetica", 9),
                    ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                    ("ALIGN", (0, 0), (0, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(pay_table)
        story.append(Spacer(1, 0.25 * inch))

        # Calculate summary values
        aww = total_gross / total_weeks
        ttd_rate = min(aww * (2 / 3), 1619.15)  # CA 2024 max TTD
        pd_rate = min(aww * (2 / 3), 290.00)  # CA 2024 max PD weekly

        # Determine highest earning quarter
        quarters = ["Q1", "Q2", "Q3", "Q4"]
        highest_quarter = random.choice(quarters[: num_periods // 3 + 1])

        # Summary section
        story.append(Paragraph("Wage Summary", self.styles["SectionHeader"]))
        summary_data = [
            ["Average Weekly Wage (AWW):", f"${aww:.2f}"],
            [
                "Highest Earning Quarter:",
                f"{highest_quarter} {doi.year - (1 if doi.month < 4 else 0)}",
            ],
            [
                "Temporary Total Disability Rate:",
                f"${ttd_rate:.2f}/week (2/3 AWW, max $1,619.15)",
            ],
            [
                "Permanent Disability Rate:",
                f"${pd_rate:.2f}/week (2/3 AWW, max $290.00)",
            ],
        ]
        summary_table = Table(summary_data, colWidths=[3.5 * inch, 2.5 * inch])
        summary_table.setStyle(
            TableStyle(
                [
                    ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 10),
                    ("FONT", (1, 0), (1, -1), "Helvetica", 10),
                    ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(summary_table)
        story.append(Spacer(1, 0.3 * inch))

        # Prepared by section
        hr_names = [
            "Patricia Martinez",
            "Robert Chen",
            "Jennifer Williams",
            "Michael Brown",
            "Sarah Johnson",
        ]
        hr_rep = random.choice(hr_names)

        story.append(Paragraph("Prepared by:", self.styles["BodyText14"]))
        story.append(
            Paragraph(
                f"<b>{hr_rep}</b>, Human Resources Representative",
                self.styles["BodyText14"],
            )
        )
        story.append(
            Paragraph(
                f"Date: {doc_spec.doc_date.strftime('%m/%d/%Y')}",
                self.styles["BodyText14"],
            )
        )
        story.append(Spacer(1, 0.2 * inch))

        # Attestation
        story.append(
            Paragraph(
                "I hereby certify that the above wage information is true and accurate to the best of my knowledge "
                "and is based on the company's payroll records for the periods indicated.",
                self.styles["SmallItalic"],
            )
        )

        return story
