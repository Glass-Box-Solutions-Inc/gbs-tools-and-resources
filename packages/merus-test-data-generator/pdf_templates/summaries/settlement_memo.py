"""
Settlement Analysis Memorandum Template — Enhanced with AMA Guides methodology,
itemized future medical, and litigation risk analysis.

Generates 3-5 page confidential settlement memos with detailed PD rating analysis,
AMA Guides methodology discussion, and structured negotiation strategy.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import random
from datetime import date

from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from data.ama_guides_content import calculate_combined_wpi, generate_impairment_narrative
from data.content_pools import get_future_medical_items
from data.wc_constants import WPI_RATINGS
from pdf_templates.base_template import BaseTemplate


class SettlementMemo(BaseTemplate):
    """Settlement analysis memorandum template with AMA Guides methodology."""

    def build_story(self, doc_spec):
        """Build 3-5 page settlement analysis memo."""
        story = []

        # Law firm letterhead
        story.extend(self.make_letterhead(
            "Adjudica Legal Services",
            "123 Legal Plaza, Suite 400, Los Angeles, CA 90012",
            "(213) 555-0100",
        ))
        story.append(Spacer(1, 0.3 * inch))

        # Confidential header
        story.append(Paragraph(
            "CONFIDENTIAL — SETTLEMENT ANALYSIS MEMORANDUM",
            self.styles["CenterBold"],
        ))
        story.append(Spacer(1, 0.05 * inch))
        story.append(Paragraph(
            "<i>ATTORNEY WORK PRODUCT — PRIVILEGED AND CONFIDENTIAL</i>",
            self.styles["SmallItalic"],
        ))
        story.append(Spacer(1, 0.2 * inch))

        # Case caption
        caption = [
            f"<b>RE:</b> {self.case.applicant.full_name} v. {self.case.employer.company_name}",
            f"<b>ADJ Number:</b> {self.case.injuries[0].adj_number}",
            f"<b>Date of Injury:</b> {self.case.injuries[0].date_of_injury.strftime('%m/%d/%Y')}",
            f"<b>Date:</b> {doc_spec.doc_date.strftime('%B %d, %Y')}",
        ]
        for line in caption:
            story.append(Paragraph(line, self.styles["BodyText14"]))
        story.append(Spacer(1, 0.2 * inch))
        story.append(self.make_hr())

        # 1. Case Summary (2-3 paragraphs)
        story.extend(self.make_section("1. CASE SUMMARY", self._generate_case_summary()))
        story.append(Spacer(1, 0.15 * inch))

        # 2. PD Rating Analysis with AMA Guides methodology
        story.extend(self._make_pd_analysis_section())
        story.append(Spacer(1, 0.15 * inch))

        # 3. Future Medical Treatment (itemized with costs)
        story.extend(self._make_fmc_section())
        story.append(Spacer(1, 0.15 * inch))

        # 4. Other Benefits
        story.extend(self._make_other_benefits_section())
        story.append(Spacer(1, 0.15 * inch))

        # 5. Litigation Risk Analysis (NEW)
        story.extend(self._make_risk_analysis_section())
        story.append(Spacer(1, 0.15 * inch))

        # 6. Settlement Range
        story.extend(self._make_settlement_range_section())
        story.append(Spacer(1, 0.15 * inch))

        # 7. Negotiation Strategy
        story.extend(self.make_section("7. NEGOTIATION STRATEGY", self._generate_negotiation_strategy()))
        story.append(Spacer(1, 0.3 * inch))

        # Attorney signature
        story.extend(self.make_signature_block(
            "Senior Attorney", "Adjudica Legal Services", "CA Bar #123456",
        ))
        story.append(Spacer(1, 0.2 * inch))
        story.append(Paragraph(
            "<b>THIS MEMO IS CONFIDENTIAL ATTORNEY WORK PRODUCT — DO NOT DISTRIBUTE</b>",
            self.styles["SmallItalic"],
        ))

        return story

    def _generate_case_summary(self):
        """Case summary — 2-3 paragraphs."""
        applicant = self.case.applicant.full_name
        employer = self.case.employer.company_name
        position = self.case.employer.position
        injury_date = self.case.injuries[0].date_of_injury.strftime("%B %d, %Y")
        injury_type = self.case.injuries[0].injury_type.value.replace("_", " ")
        body_parts = ", ".join(self.case.injuries[0].body_parts)
        mechanism = self.case.injuries[0].mechanism
        treating_doc = self.case.treating_physician.full_name

        summary = (
            f"{applicant}, a {position.lower()} employed by {employer}, sustained a work-related "
            f"{injury_type} on {injury_date}. The injury occurred {mechanism.lower()}, "
            f"affecting the {body_parts}. The applicant sought immediate medical attention and has "
            f"been under the care of {treating_doc} throughout the treatment course.\n\n"
        )

        if self.case.qme_physician:
            qme_date = (
                self.case.timeline.date_qme_evaluation.strftime("%B %d, %Y")
                if self.case.timeline.date_qme_evaluation
                else "recently"
            )
            summary += (
                f"A Qualified Medical Evaluation was conducted by {self.case.qme_physician.full_name} "
                f"on {qme_date}, finding the applicant to be permanent and stationary with measurable "
                f"whole person impairment per the AMA Guides, Fifth Edition.\n\n"
            )

        summary += (
            f"The applicant continues to experience ongoing symptoms including pain, functional "
            f"limitations, and permanent work restrictions that prevent return to the pre-injury "
            f"occupation. The treatment course has included conservative management, physical therapy, "
            f"medication management, and diagnostic studies. This analysis evaluates the case for "
            f"potential settlement considering all components of permanent disability, future medical "
            f"care, and associated benefits."
        )

        return summary

    def _make_pd_analysis_section(self):
        """PD Rating Analysis with AMA Guides methodology discussion."""
        story = []
        story.append(Paragraph(
            "<b>2. PERMANENT DISABILITY RATING ANALYSIS</b>", self.styles["SectionHeader"],
        ))
        story.append(Spacer(1, 0.1 * inch))

        body_parts = self.case.injuries[0].body_parts
        specialty = (self.case.qme_physician and self.case.qme_physician.specialty) or self.case.treating_physician.specialty

        # AMA Guides methodology discussion
        story.append(Paragraph(
            "Permanent disability is calculated per LC §4660.1 using the AMA Guides to the "
            "Evaluation of Permanent Impairment, Fifth Edition. The following analysis discusses "
            "the applicable rating methodology for each body part.",
            self.styles["BodyText14"],
        ))
        story.append(Spacer(1, 0.1 * inch))

        # Generate impairment narrative
        _, total_wpi, ratings = generate_impairment_narrative(body_parts, specialty, apportionment_pct=0)

        # Build ratings table
        ratings_data = [["Body Part", "Method", "WPI"]]
        for r in ratings:
            method = r.get("method", "AMA Guides")
            if "category" in r:
                method = f"DRE Cat {r['category']}"
            ratings_data.append([r["body_part"].title(), method, f"{r['wpi']}%"])

        if len(ratings_data) > 1:
            ratings_table = Table(ratings_data, colWidths=[2 * inch, 2 * inch, 1.2 * inch])
            ratings_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#34495e")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                *[("BACKGROUND", (0, i), (-1, i), colors.HexColor("#f8f9fa"))
                  for i in range(2, len(ratings_data), 2)],
            ]))
            story.append(ratings_table)
            story.append(Spacer(1, 0.1 * inch))

        story.append(Paragraph(
            f"<b>Combined WPI: {total_wpi}%</b>", self.styles["BodyText14"],
        ))

        # Adjustment factors
        adjustment = random.uniform(1.1, 1.4)
        adjusted_pd = int(total_wpi * adjustment)
        weeks_per_pct = random.uniform(3, 5)
        pd_weeks = int(adjusted_pd * weeks_per_pct)
        pd_rate = 290
        total_pd = pd_weeks * pd_rate

        calc_text = (
            f"<b>Adjusted PD Rating:</b> {adjusted_pd}% (after FEC, occupation, and age adjustments)\n"
            f"<b>PD Duration:</b> {pd_weeks} weeks\n"
            f"<b>Weekly Rate:</b> ${pd_rate}\n"
            f"<b>Total PD Indemnity:</b> <b>${total_pd:,}</b>"
        )
        story.append(Spacer(1, 0.05 * inch))
        story.append(Paragraph(calc_text, self.styles["BodyText14"]))

        self._pd_value = total_pd
        self._total_wpi = total_wpi
        return story

    def _make_fmc_section(self):
        """Future Medical Care — itemized with per-item costs."""
        story = []
        story.append(Paragraph(
            "<b>3. FUTURE MEDICAL TREATMENT</b>", self.styles["SectionHeader"],
        ))
        story.append(Spacer(1, 0.1 * inch))

        body_parts = self.case.injuries[0].body_parts
        items = get_future_medical_items(body_parts, count=random.randint(6, 10))

        # Build itemized table
        table_data = [["Treatment Item", "Est. Annual Cost"]]
        total_annual = 0
        for item in items:
            # Extract cost from item text if present
            cost = random.randint(500, 5000)
            if "$" in item:
                # Use the cost range in the item description
                pass
            total_annual += cost
            table_data.append([item.split("(")[0].strip(), f"${cost:,}"])

        table_data.append(["TOTAL ESTIMATED ANNUAL COST", f"${total_annual:,}"])

        fmt_table = Table(table_data, colWidths=[4.5 * inch, 1.5 * inch])
        fmt_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#34495e")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#ecf0f1")),
        ]))
        story.append(fmt_table)
        story.append(Spacer(1, 0.1 * inch))

        # Life expectancy calculation
        dob = self.case.applicant.date_of_birth
        current_age = (date.today() - dob).days // 365
        life_exp = max(10, 78 - current_age)
        discount = 0.7
        total_fmc = int(total_annual * life_exp * discount)

        fmc_calc = (
            f"<b>Life Expectancy:</b> {life_exp} years (applicant age {current_age})\n"
            f"<b>Present Value Discount:</b> {int(discount * 100)}%\n"
            f"<b>Total FMC Value:</b> <b>${total_fmc:,}</b>\n\n"
            f"<i>Medicare Set-Aside allocation may be required depending on Medicare eligibility "
            f"and settlement amount.</i>"
        )
        story.append(Paragraph(fmc_calc, self.styles["BodyText14"]))
        self._fmc_value = total_fmc
        return story

    def _make_other_benefits_section(self):
        """Other benefits: TTD, SJDB, self-procured."""
        story = []
        story.append(Paragraph(
            "<b>4. OTHER BENEFITS</b>", self.styles["SectionHeader"],
        ))
        story.append(Spacer(1, 0.1 * inch))

        if self.case.timeline.date_qme_evaluation:
            ttd_days = (self.case.timeline.date_qme_evaluation - self.case.injuries[0].date_of_injury).days
        else:
            ttd_days = random.randint(60, 180)

        weekly_wage = self.case.employer.hourly_rate * self.case.employer.weekly_hours
        ttd_rate = min(weekly_wage * 2 / 3, 1619.15)
        ttd_weeks = ttd_days // 7
        ttd_paid = int(ttd_rate * ttd_weeks)
        sjdb_voucher = 6000
        self_procured = random.choice([0, 0, random.randint(500, 2000)])

        benefits_text = (
            f"<b>Temporary Total Disability (TTD):</b> ${ttd_paid:,} "
            f"({ttd_weeks} weeks @ ${ttd_rate:.2f}/week)\n"
            f"<b>SJDB Voucher:</b> ${sjdb_voucher:,} (LC §4658.7)\n"
            f"<b>Self-Procured Medical:</b> ${self_procured:,}"
        )
        story.append(Paragraph(benefits_text, self.styles["BodyText14"]))
        self._other_benefits = sjdb_voucher + self_procured
        return story

    def _make_risk_analysis_section(self):
        """NEW: Litigation Risk Analysis section."""
        story = []
        story.append(Paragraph(
            "<b>5. LITIGATION RISK ANALYSIS</b>", self.styles["SectionHeader"],
        ))
        story.append(Spacer(1, 0.1 * inch))

        risks = [
            (
                "Defense Medical Evaluation",
                f"The defense AME/QME may rate the impairment lower than our {self._total_wpi}% WPI. "
                f"Defense evaluations typically result in ratings 30-50% lower than applicant's QME.",
                random.choice(["Moderate", "Significant"]),
            ),
            (
                "Apportionment",
                "Defense may argue apportionment to pre-existing degenerative changes or prior "
                "injuries under LC §4663/§4664. Pre-injury imaging may support this argument.",
                random.choice(["Low", "Moderate", "Significant"]),
            ),
            (
                "Causation Dispute",
                "Defendant may challenge the industrial causation of certain body parts, "
                "particularly if there is limited contemporaneous documentation.",
                random.choice(["Low", "Moderate"]),
            ),
            (
                "Future Medical Dispute",
                "The extent and cost of future medical care is subject to dispute. Defense may "
                "argue that treatment has plateaued and limited future care is needed.",
                random.choice(["Moderate", "Significant"]),
            ),
            (
                "Trial Uncertainty",
                "Proceeding to trial introduces uncertainty regarding the judge's interpretation "
                "of competing medical evidence. Settlement provides certainty of outcome.",
                "Moderate",
            ),
        ]

        selected_risks = random.sample(risks, min(4, len(risks)))
        for risk_name, desc, severity in selected_risks:
            story.append(Paragraph(
                f"<b>{risk_name}</b> (Risk: {severity}): {desc}",
                self.styles["BodyText14"],
            ))
            story.append(Spacer(1, 0.05 * inch))

        return story

    def _make_settlement_range_section(self):
        """Settlement range with comparable case language."""
        story = []
        story.append(Paragraph(
            "<b>6. SETTLEMENT RANGE ANALYSIS</b>", self.styles["SectionHeader"],
        ))
        story.append(Spacer(1, 0.1 * inch))

        low = self._pd_value + int(self._fmc_value * 0.5) + self._other_benefits
        mid = self._pd_value + self._fmc_value + self._other_benefits
        high = self._pd_value + self._fmc_value + self._other_benefits + random.randint(5000, 15000)
        target = int(mid * random.uniform(0.85, 0.95))

        range_data = [
            ["Scenario", "PD Value", "FMC Value", "Other", "Total"],
            ["Conservative", f"${self._pd_value:,}", f"${int(self._fmc_value * 0.5):,}", f"${self._other_benefits:,}", f"${low:,}"],
            ["Expected", f"${self._pd_value:,}", f"${self._fmc_value:,}", f"${self._other_benefits:,}", f"${mid:,}"],
            ["Optimistic", f"${self._pd_value:,}", f"${self._fmc_value:,}", f"${self._other_benefits + random.randint(5000, 15000):,}", f"${high:,}"],
        ]

        range_table = Table(range_data, colWidths=[1.2 * inch, 1.2 * inch, 1.2 * inch, 1 * inch, 1.2 * inch])
        range_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ]))
        story.append(range_table)
        story.append(Spacer(1, 0.15 * inch))

        story.append(Paragraph(
            f"<b><u>Recommended Settlement Target: ${target:,}</u></b>",
            self.styles["BodyText14"],
        ))
        story.append(Spacer(1, 0.05 * inch))

        comparable = random.choice([
            f"Comparable cases with similar body parts and impairment levels have settled in "
            f"the range of ${int(target * 0.8):,} to ${int(target * 1.2):,} in the "
            f"{self.case.venue} district.",
            f"Based on recent WCAB decisions and settlements in similar cases, the recommended "
            f"target represents a fair compromise considering litigation risks and the applicant's "
            f"need for resolution.",
        ])
        story.append(Paragraph(comparable, self.styles["BodyText14"]))

        return story

    def _generate_negotiation_strategy(self):
        """Negotiation strategy points."""
        strategies = [
            "Begin negotiations at the optimistic estimate to establish favorable anchoring. "
            "The defense will likely counter at 40-60% of our opening, so initial positioning "
            "at the high end preserves room for negotiation.",
            "Emphasize the applicant's permanent work restrictions and inability to return to "
            "the pre-injury occupation. The loss of earning capacity argument strengthens our "
            "position, particularly given the applicant's age and limited transferable skills.",
            "Leverage the QME findings as objective medical evidence supporting our impairment "
            "rating. The defense medical evaluation may provide a lower rating, but the QME "
            "opinion carries significant weight as the independent evaluator.",
            "Highlight the substantial future medical needs and present detailed cost projections. "
            "Medicare Set-Aside requirements add complexity and cost that may motivate the "
            "carrier to settle to avoid ongoing administration.",
            "Consider the applicant's personal circumstances and desire for closure. Balance "
            "maximizing recovery with practical settlement that provides certainty. Litigation "
            "risk favors settlement in cases with apportionment exposure.",
            "Prepare a detailed demand letter with supporting documentation including the QME "
            "report, treatment records, and comparable settlement data. A well-documented "
            "demand accelerates the negotiation process.",
        ]

        selected = random.sample(strategies, random.randint(3, 4))
        parts = []
        for i, strategy in enumerate(selected, 1):
            parts.append(f"{i}. {strategy}")
        return "<br/><br/>".join(parts)
