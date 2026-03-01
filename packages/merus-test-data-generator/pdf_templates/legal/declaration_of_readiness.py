"""
Declaration of Readiness to Proceed (DOR).
1-2 page document requesting hearing before WCAB.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import random
from typing import Any

from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import HRFlowable, Paragraph, Spacer, Table, TableStyle

from pdf_templates.base_template import BaseTemplate


class DeclarationOfReadiness(BaseTemplate):
    """Declaration of Readiness to Proceed (DOR)."""

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

        # Title
        story.append(Paragraph("DECLARATION OF READINESS TO PROCEED", self.styles["CenterBold"]))
        story.append(Spacer(1, 12))

        # Hearing type requested
        story.append(Paragraph("I. TYPE OF HEARING REQUESTED", self.styles["SectionHeader"]))

        hearing_types = [
            "Mandatory Settlement Conference (MSC)",
            "Priority Conference",
            "Expedited Hearing",
            "Trial"
        ]
        hearing_type = random.choice(hearing_types)

        story.append(Paragraph(f"Applicant requests that this matter be set for: <b>{hearing_type}</b>",
                              self.styles["BodyText14"]))
        story.append(Spacer(1, 12))

        # Issues for determination
        story.append(Paragraph("II. ISSUES FOR DETERMINATION", self.styles["SectionHeader"]))
        story.append(Paragraph("The following issues remain in dispute and require adjudication:",
                              self.styles["BodyText14"]))
        story.append(Spacer(1, 8))

        # Issue list
        issues = [
            "Permanent disability indemnity and the percentage thereof",
            "Temporary disability indemnity benefits",
            "Need for future medical treatment",
            "Apportionment to non-industrial factors",
            "Life pension benefits (if applicable)",
            "Reimbursement for self-procured medical treatment",
            "Penalties and interest for unreasonable delay",
            "Supplemental job displacement benefits",
        ]

        # Randomly select 4-6 issues
        selected_issues = random.sample(issues, random.randint(4, 6))

        for issue in selected_issues:
            story.append(Paragraph(f"• {issue}", self.styles["BodyText14"]))
            story.append(Spacer(1, 4))

        story.append(Spacer(1, 12))

        # Reason case is ready
        story.append(Paragraph("III. REASON CASE IS READY TO PROCEED", self.styles["SectionHeader"]))

        reasons = [
            f"All medical reports have been received and exchanged. The treating physician, {self.case.treating_physician.full_name}, "
            f"has declared the applicant permanent and stationary as of {doc_spec.doc_date.strftime('%B %d, %Y')}.",

            f"A Qualified Medical Evaluator report has been obtained from {self.case.qme_physician.full_name if self.case.qme_physician else 'the appointed QME'}, "
            f"addressing all disputed medical issues including permanent disability and need for future medical treatment.",

            "All discovery has been completed, including exchange of medical records, employment records, and expert reports. "
            "The parties have been unable to resolve the matter through informal negotiations.",
        ]

        reason_text = " ".join(random.sample(reasons, 2))
        story.append(Paragraph(reason_text, self.styles["DoubleSpaced"]))
        story.append(Spacer(1, 12))

        # Exhibits
        story.append(Paragraph("IV. EXHIBITS TO BE INTRODUCED", self.styles["SectionHeader"]))
        story.append(Paragraph("Applicant intends to introduce the following exhibits at hearing:",
                              self.styles["BodyText14"]))
        story.append(Spacer(1, 8))

        exhibits = [
            f"Exhibit 1: Medical reports from {self.case.treating_physician.full_name}, treating physician",
            f"Exhibit 2: Diagnostic imaging reports (X-rays, MRI, CT scans)",
            f"Exhibit 3: QME report from {self.case.qme_physician.full_name if self.case.qme_physician else 'appointed QME'}",
            f"Exhibit 4: Pharmacy records and billing statements",
            f"Exhibit 5: Employment records including wage statements and job description",
            f"Exhibit 6: Correspondence with claims adjuster and defense counsel",
        ]

        for exhibit in exhibits:
            story.append(Paragraph(exhibit, self.styles["BodyText14"]))
            story.append(Spacer(1, 4))

        story.append(Spacer(1, 12))

        # Declaration under penalty of perjury
        story.append(Paragraph("V. DECLARATION", self.styles["SectionHeader"]))

        declaration = (
            "I declare under penalty of perjury under the laws of the State of California that "
            "the foregoing is true and correct, that discovery has been completed to the extent "
            "necessary to permit the matter to proceed to the requested hearing, and that all parties "
            "have been served with a copy of this Declaration of Readiness to Proceed."
        )

        story.append(Paragraph(declaration, self.styles["DoubleSpaced"]))
        story.append(Spacer(1, 18))

        # Date and signature
        story.append(self.make_date_line("Date", doc_spec.doc_date))
        story.append(Spacer(1, 30))

        sig_data = [
            ["_________________________________"],
            ["Attorney for Applicant"],
            [""],
            ["[Attorney Name]"],
            ["State Bar No. XXXXXX"],
            [""],
            ["[Law Firm Name]"],
            ["[Address]"],
            ["[City, State ZIP]"],
            [f"Phone: {a.phone}"],
        ]

        t = Table(sig_data, colWidths=[3*inch])
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LINEABOVE", (0, 0), (0, 0), 0.5, colors.black),
        ]))
        story.append(t)

        story.append(Spacer(1, 18))

        # Proof of service
        story.append(self.make_hr())
        story.append(Spacer(1, 12))
        story.append(Paragraph("PROOF OF SERVICE", self.styles["SectionHeader"]))

        service_text = (
            f"I declare that I am employed in the county where the mailing occurred. I am over the age of 18 years "
            f"and not a party to this action. On {doc_spec.doc_date.strftime('%B %d, %Y')}, I served the foregoing "
            f"DECLARATION OF READINESS TO PROCEED on all parties by placing a true copy thereof in a sealed envelope "
            f"addressed to each party at their last known address and depositing said envelope in the United States mail "
            f"with postage fully prepaid."
        )

        story.append(Paragraph(service_text, self.styles["BodyText14"]))
        story.append(Spacer(1, 12))

        # Service signature
        story.append(Spacer(1, 30))
        story.append(HRFlowable(width="40%", thickness=0.5, color=colors.black))
        story.append(Paragraph("[Name of Person Serving]", self.styles["SmallItalic"]))

        return story
