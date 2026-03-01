"""
Personnel File Template

Generates personnel file extracts with employment history and attendance records.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from pdf_templates.base_template import BaseTemplate
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
from datetime import timedelta
import random


class PersonnelFile(BaseTemplate):
    """Personnel file extract with employment history and records."""

    def build_story(self, doc_spec):
        """Build the personnel file document."""
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
        story.append(Paragraph("PERSONNEL FILE EXTRACT", self.styles["CenterBold"]))
        story.append(Spacer(1, 0.1 * inch))
        story.append(
            Paragraph(
                "Prepared pursuant to subpoena / discovery request",
                self.styles["SmallItalic"],
            )
        )
        story.append(Spacer(1, 0.2 * inch))

        # Employee Information
        story.append(Paragraph("Employee Information", self.styles["SectionHeader"]))

        supervisor_names = [
            "David Martinez",
            "Linda Chen",
            "James Wilson",
            "Maria Rodriguez",
            "Thomas Anderson",
        ]
        supervisor = random.choice(supervisor_names)

        emp_data = [
            ["Name:", self.case.applicant.full_name],
            [
                "Date of Birth:",
                self.case.applicant.date_of_birth.strftime("%m/%d/%Y"),
            ],
            [
                "Social Security Number:",
                f"XXX-XX-{self.case.applicant.ssn_last_four}",
            ],
            ["Hire Date:", self.case.employer.hire_date.strftime("%m/%d/%Y")],
            ["Current Position:", self.case.employer.position],
            ["Department:", self.case.employer.department or "Operations"],
            ["Supervisor:", supervisor],
        ]
        emp_table = Table(emp_data, colWidths=[2.5 * inch, 3.5 * inch])
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

        # Position History
        story.append(Paragraph("Position History", self.styles["SectionHeader"]))

        # Generate 1-3 position changes
        num_positions = random.randint(1, 3)
        history_data = [["Date", "Position", "Department", "Pay Rate", "Action"]]

        # Start with hire
        history_data.append([
            self.case.employer.hire_date.strftime("%m/%d/%Y"),
            self.case.employer.position,
            self.case.employer.department or "Operations",
            f"${self.case.employer.hourly_rate:.2f}/hr",
            "Hired",
        ])

        # Add promotions/transfers if applicable
        if num_positions > 1:
            months_employed = (
                self.case.injuries[0].date_of_injury - self.case.employer.hire_date
            ).days / 30
            if months_employed > 6:
                # Promotion after 6-18 months
                promo_date = self.case.employer.hire_date + timedelta(
                    days=random.randint(180, min(540, int(months_employed * 30)))
                )
                promo_rate = self.case.employer.hourly_rate * random.uniform(1.05, 1.15)

                position_variants = {
                    "warehouse": ["Senior Warehouse Associate", "Lead Warehouse Worker"],
                    "construction": ["Journeyman", "Lead Carpenter"],
                    "healthcare": ["Senior Nursing Assistant", "Lead CNA"],
                    "retail": ["Senior Sales Associate", "Lead Cashier"],
                    "food": ["Line Cook", "Prep Supervisor"],
                }

                # Determine category
                position_lower = self.case.employer.position.lower()
                if any(kw in position_lower for kw in ["warehouse", "forklift", "loader"]):
                    promo_title = random.choice(position_variants.get("warehouse", [self.case.employer.position]))
                elif any(kw in position_lower for kw in ["construction", "carpenter"]):
                    promo_title = random.choice(position_variants.get("construction", [self.case.employer.position]))
                elif any(kw in position_lower for kw in ["nurse", "aide", "caregiver"]):
                    promo_title = random.choice(position_variants.get("healthcare", [self.case.employer.position]))
                elif any(kw in position_lower for kw in ["retail", "cashier", "sales"]):
                    promo_title = random.choice(position_variants.get("retail", [self.case.employer.position]))
                elif any(kw in position_lower for kw in ["cook", "chef", "server", "food"]):
                    promo_title = random.choice(position_variants.get("food", [self.case.employer.position]))
                else:
                    promo_title = f"Senior {self.case.employer.position}"

                history_data.append([
                    promo_date.strftime("%m/%d/%Y"),
                    promo_title,
                    self.case.employer.department or "Operations",
                    f"${promo_rate:.2f}/hr",
                    "Promoted",
                ])

        if num_positions > 2:
            # Department transfer
            months_employed = (
                self.case.injuries[0].date_of_injury - self.case.employer.hire_date
            ).days / 30
            if months_employed > 12:
                transfer_date = self.case.employer.hire_date + timedelta(
                    days=random.randint(365, min(730, int(months_employed * 30)))
                )
                departments = ["Operations", "Production", "Logistics", "Quality Control", "Maintenance"]
                new_dept = random.choice([d for d in departments if d != self.case.employer.department])

                history_data.append([
                    transfer_date.strftime("%m/%d/%Y"),
                    self.case.employer.position,
                    new_dept,
                    f"${self.case.employer.hourly_rate:.2f}/hr",
                    "Transfer",
                ])

        history_table = Table(
            history_data,
            colWidths=[1.2 * inch, 1.8 * inch, 1.3 * inch, 1.0 * inch, 1.0 * inch],
        )
        history_table.setStyle(
            TableStyle(
                [
                    ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
                    ("FONT", (0, 1), (-1, -1), "Helvetica", 9),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
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
        story.append(history_table)
        story.append(Spacer(1, 0.25 * inch))

        # Attendance/Leave Records
        story.append(Paragraph("Attendance and Leave Records", self.styles["SectionHeader"]))

        # Calculate days from injury to doc_date or return to work
        doi = self.case.injuries[0].date_of_injury
        if hasattr(self.case.timeline, "return_to_work") and self.case.timeline.return_to_work:
            leave_end = self.case.timeline.return_to_work
            leave_status = f"Returned to work: {leave_end.strftime('%m/%d/%Y')}"
        else:
            leave_end = doc_spec.doc_date
            leave_status = "Currently on leave"

        days_on_leave = (leave_end - doi).days

        # Generate annual sick days usage for years employed
        years_employed = (doi - self.case.employer.hire_date).days / 365
        sick_days_text = ""
        for year in range(max(1, int(years_employed))):
            year_val = self.case.employer.hire_date.year + year
            sick_days = random.randint(3, 12)
            sick_days_text += f"{year_val}: {sick_days} days used<br/>"

        leave_text = (
            f"<b>Sick Leave Usage (prior to injury):</b><br/>{sick_days_text}<br/>"
            f"<b>Workers' Compensation Leave:</b><br/>"
            f"Start Date: {doi.strftime('%m/%d/%Y')}<br/>"
            f"Duration: {days_on_leave} days<br/>"
            f"Status: {leave_status}<br/><br/>"
        )

        # FMLA/CFRA if applicable (leave > 3 days)
        if days_on_leave > 3:
            fmla_approved = doi + timedelta(days=random.randint(7, 21))
            leave_text += (
                f"<b>FMLA/CFRA Leave:</b><br/>"
                f"Approved: {fmla_approved.strftime('%m/%d/%Y')}<br/>"
                f"Reason: Work-related injury<br/>"
            )

        story.append(Paragraph(leave_text, self.styles["BodyText14"]))
        story.append(Spacer(1, 0.2 * inch))

        # Performance Reviews
        story.append(Paragraph("Performance Reviews", self.styles["SectionHeader"]))

        # Generate 1-2 reviews
        num_reviews = random.randint(1, 2)
        review_data = [["Review Date", "Rating", "Reviewer"]]

        for i in range(num_reviews):
            # Reviews typically annual or at 6-month intervals
            months_back = (i + 1) * random.randint(6, 12)
            review_date = doi - timedelta(days=months_back * 30)

            # Ensure review date is after hire date
            if review_date < self.case.employer.hire_date:
                continue

            rating = random.choice([
                "Meets Expectations",
                "Meets Expectations",
                "Exceeds Expectations",
            ])

            reviewers = [
                "David Martinez",
                "Linda Chen",
                "James Wilson",
                "Maria Rodriguez",
                "Thomas Anderson",
            ]
            reviewer = random.choice(reviewers)

            review_data.append([
                review_date.strftime("%m/%d/%Y"),
                rating,
                reviewer,
            ])

        if len(review_data) > 1:
            review_table = Table(
                review_data, colWidths=[1.5 * inch, 2.5 * inch, 2.0 * inch]
            )
            review_table.setStyle(
                TableStyle(
                    [
                        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
                        ("FONT", (0, 1), (-1, -1), "Helvetica", 9),
                        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
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
            story.append(review_table)
        else:
            story.append(
                Paragraph(
                    "No performance reviews on file during employment period.",
                    self.styles["BodyText14"],
                )
            )

        story.append(Spacer(1, 0.2 * inch))

        # Disciplinary Actions
        story.append(Paragraph("Disciplinary Actions", self.styles["SectionHeader"]))
        story.append(
            Paragraph("None on file.", self.styles["BodyText14"])
        )
        story.append(Spacer(1, 0.3 * inch))

        # HR Certification
        story.append(self.make_hr())
        story.append(Spacer(1, 0.1 * inch))

        story.append(
            Paragraph(
                "This is a true and correct extract from the personnel file of the above-named employee, "
                "prepared in response to a lawful request for employment records. These records are maintained "
                "in the ordinary course of business and are kept in accordance with applicable employment laws.",
                self.styles["SmallItalic"],
            )
        )
        story.append(Spacer(1, 0.2 * inch))

        # HR signature block
        hr_names = [
            "Patricia Martinez",
            "Robert Chen",
            "Jennifer Williams",
            "Michael Brown",
            "Sarah Johnson",
        ]
        hr_rep = random.choice(hr_names)

        story.append(
            Paragraph(
                f"<b>{hr_rep}</b><br/>"
                f"Human Resources Representative<br/>"
                f"{self.case.employer.company_name}<br/>"
                f"Date: {doc_spec.doc_date.strftime('%m/%d/%Y')}",
                self.styles["BodyText14"],
            )
        )

        return story
