"""
Application for Adjudication of Claim — WCAB form (DWC-1).
2-3 page formal application to initiate workers' compensation claim.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import random
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.units import inch
from reportlab.platypus import HRFlowable, Paragraph, Spacer, Table, TableStyle

from pdf_templates.base_template import BaseTemplate


class ApplicationForAdjudication(BaseTemplate):
    """WCAB Application for Adjudication of Claim."""

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
        story.append(Paragraph("CASE CAPTION", self.styles["SectionHeader"]))

        caption_data = [
            [Paragraph(f"<b>{a.full_name}</b>", self.styles["TableCell"]), "", ""],
            [Paragraph("Applicant", self.styles["TableCell"]), "", ""],
            ["", "", ""],
            [Paragraph("vs.", self.styles["TableCell"]), "", ""],
            ["", "", ""],
            [Paragraph(f"<b>{emp.company_name}</b>", self.styles["TableCell"]), "",
             Paragraph(f"<b>ADJ No.:</b> {inj.adj_number}", self.styles["TableCell"])],
            [Paragraph("Employer", self.styles["TableCell"]), "", ""],
            ["", "", ""],
            [Paragraph(f"{ins.carrier_name}", self.styles["TableCell"]), "",
             Paragraph(f"<b>Venue:</b> {self.case.venue}", self.styles["TableCell"])],
            [Paragraph("Insurance Carrier", self.styles["TableCell"]), "", ""],
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

        # Applicant information
        story.append(Paragraph("I. APPLICANT INFORMATION", self.styles["SectionHeader"]))

        applicant_data = [
            ["Full Name:", a.full_name],
            ["Date of Birth:", a.date_of_birth.strftime("%m/%d/%Y")],
            ["Social Security Number (last 4):", f"XXX-XX-{a.ssn_last_four}"],
            ["Address:", a.address_street],
            ["City, State, ZIP:", f"{a.address_city}, {a.address_state} {a.address_zip}"],
            ["Phone:", a.phone],
            ["Email:", a.email],
        ]

        t = Table(applicant_data, colWidths=[2.5*inch, 4*inch])
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

        # Employer information
        story.append(Paragraph("II. EMPLOYER INFORMATION", self.styles["SectionHeader"]))

        employer_data = [
            ["Employer Name:", emp.company_name],
            ["Address:", emp.address_street],
            ["City, State, ZIP:", f"{emp.address_city}, {emp.address_state} {emp.address_zip}"],
            ["Phone:", emp.phone],
            ["Applicant's Position:", emp.position],
            ["Date of Hire:", emp.hire_date.strftime("%m/%d/%Y")],
        ]

        t = Table(employer_data, colWidths=[2.5*inch, 4*inch])
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

        # Insurance carrier information
        story.append(Paragraph("III. INSURANCE CARRIER INFORMATION", self.styles["SectionHeader"]))

        insurance_data = [
            ["Carrier Name:", ins.carrier_name],
            ["Claim Number:", ins.claim_number],
            ["Policy Number:", ins.policy_number],
            ["Claims Adjuster:", ins.adjuster_name],
            ["Adjuster Phone:", ins.adjuster_phone],
        ]

        t = Table(insurance_data, colWidths=[2.5*inch, 4*inch])
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

        # Injury information
        story.append(Paragraph("IV. INJURY INFORMATION", self.styles["SectionHeader"]))

        injury_type_display = inj.injury_type.value.replace("_", " ").title()
        body_parts_display = ", ".join(inj.body_parts)

        injury_data = [
            ["Date of Injury:", inj.date_of_injury.strftime("%m/%d/%Y")],
            ["Type of Injury:", injury_type_display],
            ["Body Parts Injured:", body_parts_display],
        ]

        t = Table(injury_data, colWidths=[2.5*inch, 4*inch])
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

        # Description of injury
        story.append(Paragraph("V. DESCRIPTION OF INJURY AND HOW IT OCCURRED", self.styles["SectionHeader"]))

        description = (
            f"On {inj.date_of_injury.strftime('%B %d, %Y')}, while employed by {emp.company_name} "
            f"as a {emp.position}, applicant sustained an industrial injury arising out of and occurring "
            f"in the course of employment. {inj.mechanism} As a result of this incident, applicant sustained "
            f"injuries to the following body parts: {body_parts_display}. {inj.description}"
        )

        story.append(Paragraph(description, self.styles["DoubleSpaced"]))
        story.append(Spacer(1, 12))

        # Request for findings
        story.append(Paragraph("VI. REQUEST FOR FINDINGS AND AWARD", self.styles["SectionHeader"]))
        story.append(Paragraph("Applicant requests that the Workers' Compensation Appeals Board make the following findings and award:",
                              self.styles["BodyText14"]))
        story.append(Spacer(1, 8))

        # Checkbox items
        findings = [
            "☑ That applicant sustained injury arising out of and occurring in the course of employment",
            "☑ That applicant is entitled to temporary disability indemnity benefits",
            "☑ That applicant is entitled to permanent disability indemnity benefits",
            "☑ That applicant is entitled to medical treatment reasonably required to cure or relieve from the effects of the injury",
            "☑ That applicant is entitled to reimbursement for self-procured medical treatment",
            "☑ That applicant is entitled to vocational rehabilitation benefits",
            "☑ That applicant is entitled to supplemental job displacement benefits",
            "☑ That defendant is liable for penalties and interest for unreasonable delay",
            "☑ That applicant is entitled to reimbursement of costs incurred",
            "☑ For such other and further relief as the Board deems just and proper",
        ]

        for finding in findings:
            story.append(Paragraph(finding, self.styles["BodyText14"]))
            story.append(Spacer(1, 4))

        story.append(Spacer(1, 12))

        # Declaration
        story.append(Paragraph("VII. DECLARATION", self.styles["SectionHeader"]))
        declaration_text = (
            "I declare under penalty of perjury under the laws of the State of California "
            "that the foregoing is true and correct to the best of my knowledge and belief."
        )
        story.append(Paragraph(declaration_text, self.styles["DoubleSpaced"]))
        story.append(Spacer(1, 12))

        # Date and signature
        story.append(self.make_date_line("Date Filed", doc_spec.doc_date))
        story.append(Spacer(1, 24))

        sig_data = [
            ["_________________________________", "_________________________________"],
            ["Applicant's Attorney", "Applicant"],
            ["", ""],
            [f"[Attorney Name for Applicant]", a.full_name],
            ["State Bar No. XXXXXX", ""],
        ]

        t = Table(sig_data, colWidths=[3.25*inch, 3.25*inch])
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LINEABOVE", (0, 0), (0, 0), 0.5, colors.black),
            ("LINEABOVE", (1, 0), (1, 0), 0.5, colors.black),
        ]))
        story.append(t)

        return story
