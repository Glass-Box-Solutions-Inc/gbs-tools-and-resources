"""
Stipulations with Request for Award.
3-5 page stipulated settlement document with agreed facts and award.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import random
from typing import Any

from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import HRFlowable, Paragraph, Spacer, Table, TableStyle

from pdf_templates.base_template import BaseTemplate


class Stipulations(BaseTemplate):
    """Stipulations with Request for Award."""

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
            ["", "", ""],
            [Paragraph(f"<b>{emp.company_name}</b>", self.styles["TableCell"]), "", ""],
            [Paragraph("Employer", self.styles["TableCell"]), "", ""],
            ["", "", ""],
            [Paragraph(f"{ins.carrier_name}", self.styles["TableCell"]), "", ""],
            [Paragraph("Insurance Carrier, Defendants", self.styles["TableCell"]), "", ""],
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
        story.append(Paragraph("STIPULATIONS WITH REQUEST FOR AWARD", self.styles["CenterBold"]))
        story.append(Spacer(1, 12))

        # Preamble
        preamble = (
            "The parties to the above-captioned matter, by and through their respective attorneys of record, "
            "hereby stipulate to the following facts and respectfully request that the Workers' Compensation "
            "Appeals Board issue an Award based upon these stipulations pursuant to Labor Code Section 5702."
        )
        story.append(Paragraph(preamble, self.styles["DoubleSpaced"]))
        story.append(Spacer(1, 12))

        # Stipulations
        story.append(Paragraph("STIPULATIONS", self.styles["SectionHeader"]))

        # Generate random PD percentage and award amount
        pd_percentage = random.randint(15, 65)
        base_pd_award = random.randint(5000, 75000)
        attorney_fee_percentage = 15
        attorney_fee_amount = int(base_pd_award * (attorney_fee_percentage / 100))
        net_pd_award = base_pd_award - attorney_fee_amount

        # Stipulation 1: Employment
        story.append(Paragraph(
            f"<b>1.</b> That on {inj.date_of_injury.strftime('%B %d, %Y')}, applicant {a.full_name} was employed by "
            f"{emp.company_name} as a {emp.position}, with an average weekly wage of ${emp.hourly_rate * emp.weekly_hours:.2f}.",
            self.styles["DoubleSpaced"]
        ))
        story.append(Spacer(1, 8))

        # Stipulation 2: Injury AOE/COE
        body_parts_text = ", ".join(inj.body_parts)
        story.append(Paragraph(
            f"<b>2.</b> That on said date, applicant sustained injury arising out of and occurring in the course "
            f"of employment (AOE/COE) to the following body parts: {body_parts_text}.",
            self.styles["DoubleSpaced"]
        ))
        story.append(Spacer(1, 8))

        # Stipulation 3: Defendants
        story.append(Paragraph(
            f"<b>3.</b> That at all relevant times, {emp.company_name} was insured for workers' compensation "
            f"liability through {ins.carrier_name}, claim number {ins.claim_number}.",
            self.styles["DoubleSpaced"]
        ))
        story.append(Spacer(1, 8))

        # Stipulation 4: PD rating
        story.append(Paragraph(
            f"<b>4.</b> That applicant has sustained permanent disability as a result of the industrial injury, "
            f"which disability is rated at {pd_percentage}% under the provisions of the Labor Code and applicable "
            f"Rating Schedule. The parties stipulate that permanent disability indemnity is payable in the amount of "
            f"<b>${base_pd_award:,}</b>, less attorney fees and costs as set forth herein.",
            self.styles["DoubleSpaced"]
        ))
        story.append(Spacer(1, 8))

        # Stipulation 5: Future medical
        story.append(Paragraph(
            f"<b>5.</b> That applicant is in need of future medical treatment to cure and/or relieve from the "
            f"effects of the industrial injury, including but not limited to physician consultations, diagnostic "
            f"testing, physical therapy, medications, medical supplies, and surgical intervention if reasonably "
            f"required. Defendant shall provide and pay for all such treatment pursuant to Labor Code Section 4600.",
            self.styles["DoubleSpaced"]
        ))
        story.append(Spacer(1, 8))

        # Stipulation 6: Attorney fees
        story.append(Paragraph(
            f"<b>6.</b> That applicant's attorney is entitled to a reasonable attorney fee of {attorney_fee_percentage}% "
            f"of the permanent disability award, which equals <b>${attorney_fee_amount:,}</b>, to be paid from the "
            f"permanent disability indemnity. Net permanent disability indemnity payable to applicant is "
            f"<b>${net_pd_award:,}</b>.",
            self.styles["DoubleSpaced"]
        ))
        story.append(Spacer(1, 8))

        # Stipulation 7: Self-procured medical
        self_procured_amount = random.randint(500, 5000)
        story.append(Paragraph(
            f"<b>7.</b> That applicant incurred reasonable and necessary self-procured medical expenses in the amount of "
            f"<b>${self_procured_amount:,}</b> for treatment of the industrial injury. Defendant shall reimburse applicant "
            f"for said expenses within thirty (30) days of the date of this Award.",
            self.styles["DoubleSpaced"]
        ))
        story.append(Spacer(1, 8))

        # Stipulation 8: Supplemental Job Displacement
        if pd_percentage >= 15:
            story.append(Paragraph(
                f"<b>8.</b> That applicant is entitled to a Supplemental Job Displacement Benefit voucher in the amount "
                f"of $6,000.00 pursuant to Labor Code Section 4658.7. Defendant shall issue said voucher within thirty (30) "
                f"days of the date of this Award.",
                self.styles["DoubleSpaced"]
            ))
            story.append(Spacer(1, 8))

        # Stipulation 9: Temporary disability
        td_weeks = random.randint(4, 52)
        td_weekly_rate = emp.hourly_rate * emp.weekly_hours * 0.67
        td_total = td_weekly_rate * td_weeks
        story.append(Paragraph(
            f"<b>9.</b> That temporary disability indemnity has been paid for {td_weeks} weeks at the rate of "
            f"${td_weekly_rate:.2f} per week, totaling ${td_total:.2f}, and no further temporary disability is owed.",
            self.styles["DoubleSpaced"]
        ))
        story.append(Spacer(1, 12))

        # Request for Award
        story.append(Paragraph("REQUEST FOR AWARD", self.styles["SectionHeader"]))

        request = (
            "Based upon the foregoing stipulations, the parties respectfully request that the Workers' Compensation "
            "Appeals Board issue an Award consistent with the terms set forth above, finding that applicant sustained "
            "industrial injury arising out of and occurring in the course of employment, and ordering payment of permanent "
            "disability indemnity, self-procured medical expenses, Supplemental Job Displacement Benefit voucher, attorney "
            "fees, and future medical treatment as stipulated."
        )
        story.append(Paragraph(request, self.styles["DoubleSpaced"]))
        story.append(Spacer(1, 18))

        # Summary table
        story.append(Paragraph("SUMMARY OF AWARD", self.styles["SectionHeader"]))

        summary_data = [
            ["Permanent Disability (Gross)", f"${base_pd_award:,}"],
            ["Less: Attorney Fees (15%)", f"$(${attorney_fee_amount:,})"],
            ["Net Permanent Disability to Applicant", f"${net_pd_award:,}"],
            ["Self-Procured Medical Reimbursement", f"${self_procured_amount:,}"],
            ["SJDB Voucher", "$6,000" if pd_percentage >= 15 else "N/A"],
            ["Future Medical Treatment", "Provided pursuant to LC §4600"],
        ]

        t = Table(summary_data, colWidths=[4*inch, 2.5*inch])
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOX", (0, 0), (-1, -1), 1, colors.black),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("BACKGROUND", (0, -2), (-1, -1), colors.HexColor("#f0f0f0")),
        ]))
        story.append(t)
        story.append(Spacer(1, 18))

        # Signatures
        story.append(Paragraph("Dated: " + doc_spec.doc_date.strftime("%B %d, %Y"), self.styles["BodyText14"]))
        story.append(Spacer(1, 24))

        sig_data = [
            ["_________________________________", "_________________________________"],
            ["Attorney for Applicant", "Attorney for Defendants"],
            ["", ""],
            ["[Attorney Name]", ins.defense_attorney],
            ["State Bar No. XXXXXX", ins.defense_firm],
            ["", ""],
            ["", ""],
            ["_________________________________", ""],
            [a.full_name, ""],
            ["Applicant", ""],
        ]

        t = Table(sig_data, colWidths=[3.25*inch, 3.25*inch])
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LINEABOVE", (0, 0), (0, 0), 0.5, colors.black),
            ("LINEABOVE", (1, 0), (1, 0), 0.5, colors.black),
            ("LINEABOVE", (0, 7), (0, 7), 0.5, colors.black),
        ]))
        story.append(t)

        return story
