"""
Compromise and Release Agreement.
4-6 page comprehensive settlement document releasing all claims.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import random
from typing import Any

from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import HRFlowable, Paragraph, Spacer, Table, TableStyle

from pdf_templates.base_template import BaseTemplate


class CompromiseAndRelease(BaseTemplate):
    """Compromise and Release Agreement."""

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
            ["", "", Paragraph(f"<b>Date of Injury:</b> {inj.date_of_injury.strftime('%m/%d/%Y')}", self.styles["TableCell"])],
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
        story.append(Paragraph("COMPROMISE AND RELEASE", self.styles["CenterBold"]))
        story.append(Spacer(1, 12))

        # Generate settlement amounts
        gross_settlement = random.randint(25000, 150000)
        attorney_fee_percentage = 15
        attorney_fee_amount = int(gross_settlement * (attorney_fee_percentage / 100))
        costs = random.randint(500, 3000)
        medicare_set_aside = random.randint(5000, 25000)
        net_to_applicant = gross_settlement - attorney_fee_amount - costs - medicare_set_aside

        # Whereas clauses
        story.append(Paragraph("RECITALS", self.styles["SectionHeader"]))

        whereas_text = (
            f"<b>WHEREAS,</b> applicant {a.full_name} filed an Application for Adjudication of Claim with the "
            f"Workers' Compensation Appeals Board alleging injury arising out of and occurring in the course of "
            f"employment with {emp.company_name} on or about {inj.date_of_injury.strftime('%B %d, %Y')}; and"
        )
        story.append(Paragraph(whereas_text, self.styles["DoubleSpaced"]))
        story.append(Spacer(1, 8))

        whereas_text2 = (
            f"<b>WHEREAS,</b> applicant claims to have sustained industrial injury to the following body parts: "
            f"{', '.join(inj.body_parts)}; and"
        )
        story.append(Paragraph(whereas_text2, self.styles["DoubleSpaced"]))
        story.append(Spacer(1, 8))

        whereas_text3 = (
            f"<b>WHEREAS,</b> certain issues remain in dispute between the parties, including but not limited to "
            f"the extent of permanent disability, need for future medical treatment, and apportionment; and"
        )
        story.append(Paragraph(whereas_text3, self.styles["DoubleSpaced"]))
        story.append(Spacer(1, 8))

        whereas_text4 = (
            f"<b>WHEREAS,</b> the parties desire to compromise and settle all disputed issues and to enter into a "
            f"full and final Compromise and Release of all claims arising from the alleged industrial injury;"
        )
        story.append(Paragraph(whereas_text4, self.styles["DoubleSpaced"]))
        story.append(Spacer(1, 12))

        story.append(Paragraph(
            "<b>NOW, THEREFORE,</b> in consideration of the mutual covenants and promises contained herein, "
            "the parties agree as follows:",
            self.styles["DoubleSpaced"]
        ))
        story.append(Spacer(1, 12))

        # Terms and Conditions
        story.append(Paragraph("TERMS AND CONDITIONS", self.styles["SectionHeader"]))

        # Section 1: Settlement Amount
        story.append(Paragraph(
            f"<b>1. Settlement Amount.</b> Defendant agrees to pay applicant the total sum of <b>${gross_settlement:,}</b> "
            f"as full and complete compromise and settlement of all claims, past, present, and future, arising from or "
            f"related to the alleged industrial injury of {inj.date_of_injury.strftime('%B %d, %Y')}.",
            self.styles["DoubleSpaced"]
        ))
        story.append(Spacer(1, 8))

        # Section 2: Distribution
        story.append(Paragraph(
            f"<b>2. Distribution of Settlement.</b> The settlement amount shall be distributed as follows:",
            self.styles["DoubleSpaced"]
        ))
        story.append(Spacer(1, 6))

        distribution_data = [
            ["Gross Settlement Amount", f"${gross_settlement:,}"],
            ["Less: Attorney Fees (15%)", f"(${attorney_fee_amount:,})"],
            ["Less: Costs and Expenses", f"(${costs:,})"],
            ["Less: Medicare Set-Aside Allocation", f"(${medicare_set_aside:,})"],
            ["<b>Net to Applicant</b>", f"<b>${net_to_applicant:,}</b>"],
        ]

        t = Table(distribution_data, colWidths=[4*inch, 2.5*inch])
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (0, -2), "Helvetica"),
            ("FONTNAME", (0, -1), (0, -1), "Helvetica-Bold"),
            ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("BOX", (0, 0), (-1, -1), 1, colors.black),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#f0f0f0")),
            ("LINEABOVE", (0, -1), (-1, -1), 1.5, colors.black),
        ]))
        story.append(t)
        story.append(Spacer(1, 8))

        # Section 3: Body Parts Covered
        story.append(Paragraph(
            f"<b>3. Body Parts Covered.</b> This Compromise and Release covers all injuries to the following body parts: "
            f"{', '.join(inj.body_parts)}, including all consequences and sequelae thereof.",
            self.styles["DoubleSpaced"]
        ))
        story.append(Spacer(1, 8))

        # Section 4: Release of All Claims
        story.append(Paragraph(
            f"<b>4. Release of All Claims.</b> Applicant hereby releases and forever discharges {emp.company_name}, "
            f"{ins.carrier_name}, and all related entities, officers, directors, employees, and agents from any and all "
            f"claims, demands, damages, actions, or causes of action, whether known or unknown, arising from or related "
            f"to the alleged industrial injury of {inj.date_of_injury.strftime('%B %d, %Y')}. This release includes, "
            f"without limitation, claims for permanent disability indemnity, temporary disability indemnity, life pension, "
            f"vocational rehabilitation benefits, supplemental job displacement benefits, medical treatment, and all other "
            f"benefits under the California Labor Code.",
            self.styles["DoubleSpaced"]
        ))
        story.append(Spacer(1, 8))

        # Section 5: Future Medical Treatment
        story.append(Paragraph(
            f"<b>5. Future Medical Treatment.</b> As part of this Compromise and Release, applicant expressly waives and "
            f"releases all claims for future medical treatment related to the industrial injury. Applicant acknowledges that "
            f"defendant will have no obligation to provide or pay for any medical treatment after approval of this Compromise "
            f"and Release by the Workers' Compensation Appeals Board.",
            self.styles["DoubleSpaced"]
        ))
        story.append(Spacer(1, 8))

        # Section 6: Medicare Set-Aside
        story.append(Paragraph(
            f"<b>6. Medicare Set-Aside Allocation.</b> The parties acknowledge that ${medicare_set_aside:,} of the settlement "
            f"has been allocated for future medical expenses related to the industrial injury. Applicant agrees to use these "
            f"funds exclusively for Medicare-covered services related to the work injury before seeking payment from Medicare. "
            f"Applicant shall be solely responsible for proper administration and documentation of the Medicare Set-Aside "
            f"account. See Addendum A for detailed Medicare Set-Aside considerations.",
            self.styles["DoubleSpaced"]
        ))
        story.append(Spacer(1, 8))

        # Section 7: No Admission of Liability
        story.append(Paragraph(
            f"<b>7. No Admission of Liability.</b> This Compromise and Release is entered into for the purpose of settling "
            f"disputed claims and shall not be construed as an admission of liability by any party. Defendant denies all "
            f"liability and enters into this agreement solely to avoid the cost, expense, and uncertainty of litigation.",
            self.styles["DoubleSpaced"]
        ))
        story.append(Spacer(1, 8))

        # Section 8: Supplemental Job Displacement Benefit
        if random.random() > 0.3:  # 70% chance of including SJDB
            sjdb_status = random.choice([
                "issued and delivered to applicant prior to execution of this agreement",
                "waived by applicant in exchange for the settlement consideration herein",
                "to be issued by defendant within 30 days of Board approval of this C&R"
            ])
            story.append(Paragraph(
                f"<b>8. Supplemental Job Displacement Benefit Voucher.</b> The parties stipulate that the Supplemental Job "
                f"Displacement Benefit voucher has been {sjdb_status}. See Addendum B for SJDB voucher status.",
                self.styles["DoubleSpaced"]
            ))
            story.append(Spacer(1, 8))

        # Section 9: Attorney Fees
        story.append(Paragraph(
            f"<b>9. Attorney Fees and Costs.</b> Applicant's attorney is entitled to reasonable attorney fees in the amount "
            f"of ${attorney_fee_amount:,} (15% of gross settlement) plus costs of ${costs:,}. These amounts shall be paid "
            f"directly to applicant's attorney from the settlement proceeds.",
            self.styles["DoubleSpaced"]
        ))
        story.append(Spacer(1, 8))

        # Section 10: Entire Agreement
        story.append(Paragraph(
            f"<b>10. Entire Agreement.</b> This Compromise and Release constitutes the entire agreement between the parties "
            f"and supersedes all prior negotiations, representations, or agreements, whether written or oral. This agreement "
            f"may not be modified except by written instrument signed by all parties.",
            self.styles["DoubleSpaced"]
        ))
        story.append(Spacer(1, 12))

        # Acknowledgment
        story.append(Paragraph("APPLICANT'S ACKNOWLEDGMENT", self.styles["SectionHeader"]))

        acknowledgment = (
            f"I, {a.full_name}, declare that I have read and understand the terms of this Compromise and Release. I have "
            f"discussed this agreement with my attorney and fully understand my rights and the consequences of entering into "
            f"this settlement. I acknowledge that I am releasing all claims for future medical treatment and that defendant "
            f"will have no obligation to provide medical care after this agreement is approved. I enter into this Compromise "
            f"and Release freely and voluntarily, without coercion or duress. I understand that once approved by the Workers' "
            f"Compensation Appeals Board, this settlement will be final and binding and cannot be set aside except for fraud."
        )
        story.append(Paragraph(acknowledgment, self.styles["DoubleSpaced"]))
        story.append(Spacer(1, 18))

        # Signatures
        story.append(Paragraph("Dated: " + doc_spec.doc_date.strftime("%B %d, %Y"), self.styles["BodyText14"]))
        story.append(Spacer(1, 24))

        sig_data = [
            ["_________________________________", "_________________________________"],
            [a.full_name, "Attorney for Applicant"],
            ["Applicant", ""],
            ["", "[Attorney Name]"],
            ["", "State Bar No. XXXXXX"],
            ["", ""],
            ["", ""],
            ["_________________________________", "_________________________________"],
            ["Attorney for Defendants", "Representative of Defendant"],
            ["", ""],
            [ins.defense_attorney, "[Adjuster/Representative Name]"],
            [ins.defense_firm, ins.carrier_name],
        ]

        t = Table(sig_data, colWidths=[3.25*inch, 3.25*inch])
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LINEABOVE", (0, 0), (0, 0), 0.5, colors.black),
            ("LINEABOVE", (1, 0), (1, 0), 0.5, colors.black),
            ("LINEABOVE", (0, 7), (0, 7), 0.5, colors.black),
            ("LINEABOVE", (1, 7), (1, 7), 0.5, colors.black),
        ]))
        story.append(t)
        story.append(Spacer(1, 24))

        # Page break for addenda
        story.append(Spacer(1, 0.5*inch))
        story.append(self.make_hr())
        story.append(Spacer(1, 12))

        # Addendum A: Medicare Set-Aside
        story.append(Paragraph("ADDENDUM A", self.styles["CenterBold"]))
        story.append(Paragraph("MEDICARE SET-ASIDE CONSIDERATIONS", self.styles["CenterBold"]))
        story.append(Spacer(1, 12))

        msa_text = (
            f"The parties have allocated ${medicare_set_aside:,} of the settlement proceeds for future medical expenses "
            f"related to the work injury. This allocation is based on applicant's age, life expectancy, and anticipated "
            f"future medical needs. Applicant must use these funds to pay for Medicare-covered services related to the work "
            f"injury before Medicare will make payment for such services. Applicant is responsible for maintaining detailed "
            f"records of all expenditures from the Medicare Set-Aside account and for annual reporting to Medicare. "
            f"Failure to properly administer the Medicare Set-Aside account may result in Medicare's refusal to pay for "
            f"future medical treatment related to the work injury."
        )
        story.append(Paragraph(msa_text, self.styles["DoubleSpaced"]))
        story.append(Spacer(1, 12))

        # Addendum B: SJDB Voucher
        story.append(self.make_hr())
        story.append(Spacer(1, 12))
        story.append(Paragraph("ADDENDUM B", self.styles["CenterBold"]))
        story.append(Paragraph("SUPPLEMENTAL JOB DISPLACEMENT BENEFIT VOUCHER", self.styles["CenterBold"]))
        story.append(Spacer(1, 12))

        sjdb_text = (
            f"Applicant is eligible for a Supplemental Job Displacement Benefit voucher in the amount of $6,000 pursuant "
            f"to Labor Code Section 4658.7. This voucher may be used for education-related retraining or skill enhancement "
            f"at state-approved or accredited schools. The voucher is valid for five years from the date of injury or two "
            f"years from the date the voucher is furnished, whichever is later. Applicant acknowledges receipt and "
            f"understanding of the SJDB voucher rights and limitations."
        )
        story.append(Paragraph(sjdb_text, self.styles["DoubleSpaced"]))
        story.append(Spacer(1, 12))

        # Board Approval Section
        story.append(self.make_hr())
        story.append(Spacer(1, 12))
        story.append(Paragraph("APPROVED AND SO ORDERED", self.styles["CenterBold"]))
        story.append(Spacer(1, 12))

        approval_text = (
            "The foregoing Compromise and Release is hereby approved by the Workers' Compensation Appeals Board. "
            "The parties are bound by the terms and conditions set forth herein."
        )
        story.append(Paragraph(approval_text, self.styles["BodyText14"]))
        story.append(Spacer(1, 12))

        story.append(Paragraph("Dated: ___________________________", self.styles["BodyText14"]))
        story.append(Spacer(1, 30))

        judge_sig = [
            ["_________________________________"],
            ["Workers' Compensation Judge"],
            ["Workers' Compensation Appeals Board"],
            [f"Venue: {self.case.venue}"],
        ]

        t = Table(judge_sig, colWidths=[3*inch])
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LINEABOVE", (0, 0), (0, 0), 0.5, colors.black),
        ]))
        story.append(t)

        return story
