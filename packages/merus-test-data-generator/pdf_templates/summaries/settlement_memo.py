"""
Settlement Analysis Memorandum Template

Generates a confidential settlement analysis memo for Workers' Compensation cases.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from pdf_templates.base_template import BaseTemplate
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
import random
from datetime import date
from data.wc_constants import WPI_RATINGS


class SettlementMemo(BaseTemplate):
    """Settlement analysis memorandum template."""

    def build_story(self, doc_spec):
        """Build the settlement analysis memo."""
        story = []

        # Law firm letterhead
        story.extend(self.make_letterhead(
            "Adjudica Legal Services",
            "123 Legal Plaza, Suite 400, Los Angeles, CA 90012",
            "(213) 555-0100"
        ))
        story.append(Spacer(1, 0.3 * inch))

        # Confidential header
        conf_title = Paragraph(
            "CONFIDENTIAL — SETTLEMENT ANALYSIS MEMORANDUM",
            self.styles['CenterBold']
        )
        story.append(conf_title)
        story.append(Spacer(1, 0.05 * inch))

        work_product = Paragraph(
            "<i>ATTORNEY WORK PRODUCT</i>",
            self.styles['SmallItalic']
        )
        story.append(work_product)
        story.append(Spacer(1, 0.2 * inch))

        # Case caption
        caption = [
            f"<b>RE:</b> {self.case.applicant.full_name} v. {self.case.employer.company_name}",
            f"<b>ADJ Number:</b> {self.case.injuries[0].adj_number}",
            f"<b>Date of Injury:</b> {self.case.injuries[0].date_of_injury.strftime('%m/%d/%Y')}",
            f"<b>Date:</b> {doc_spec.doc_date.strftime('%B %d, %Y')}",
        ]

        for line in caption:
            story.append(Paragraph(line, self.styles['BodyText14']))

        story.append(Spacer(1, 0.2 * inch))
        story.append(self.make_hr())

        # Section 1: Case Summary
        story.extend(self.make_section(
            "1. CASE SUMMARY",
            self._generate_case_summary()
        ))
        story.append(Spacer(1, 0.15 * inch))

        # Section 2: PD Rating Analysis
        story.extend(self._make_pd_analysis_section())
        story.append(Spacer(1, 0.15 * inch))

        # Section 3: Future Medical Treatment
        story.extend(self._make_fmc_section())
        story.append(Spacer(1, 0.15 * inch))

        # Section 4: Other Benefits
        story.extend(self._make_other_benefits_section())
        story.append(Spacer(1, 0.15 * inch))

        # Section 5: Settlement Range
        story.extend(self._make_settlement_range_section())
        story.append(Spacer(1, 0.15 * inch))

        # Section 6: Negotiation Strategy
        story.extend(self.make_section(
            "6. NEGOTIATION STRATEGY",
            self._generate_negotiation_strategy()
        ))
        story.append(Spacer(1, 0.3 * inch))

        # Attorney signature
        story.extend(self.make_signature_block(
            "Senior Attorney",
            "Adjudica Legal Services",
            "CA Bar #123456"
        ))

        story.append(Spacer(1, 0.2 * inch))

        # Confidentiality footer
        footer = Paragraph(
            "<b>THIS MEMO IS CONFIDENTIAL ATTORNEY WORK PRODUCT</b>",
            self.styles['SmallItalic']
        )
        story.append(footer)

        return story

    def _generate_case_summary(self):
        """Generate case summary narrative."""
        applicant = self.case.applicant.full_name
        employer = self.case.employer.company_name
        position = self.case.employer.position
        injury_date = self.case.injuries[0].date_of_injury.strftime('%B %d, %Y')
        injury_type = self.case.injuries[0].injury_type.value.replace('_', ' ')
        body_parts = ', '.join(self.case.injuries[0].body_parts)
        mechanism = self.case.injuries[0].mechanism

        treating_doc = self.case.treating_physician.full_name

        summary = (
            f"{applicant}, a {position} employed by {employer}, sustained a work-related "
            f"{injury_type} on {injury_date}. The injury occurred {mechanism.lower()}, "
            f"affecting the {body_parts}. "
            f"The applicant sought immediate medical attention and has been under the care of "
            f"{treating_doc} throughout the treatment course. "
        )

        if self.case.qme_physician:
            qme_date = self.case.timeline.date_qme_evaluation.strftime('%B %d, %Y') if self.case.timeline.date_qme_evaluation else "recently"
            summary += (
                f"A Qualified Medical Evaluation was conducted by {self.case.qme_physician.full_name} "
                f"on {qme_date}, finding the applicant to be permanent and stationary with measurable "
                f"whole person impairment. "
            )

        summary += (
            f"The applicant continues to experience ongoing symptoms and has permanent work restrictions "
            f"that limit their ability to return to their prior occupation. This analysis evaluates "
            f"the case for potential settlement."
        )

        return summary

    def _make_pd_analysis_section(self):
        """Generate PD rating analysis section."""
        story = []

        title = Paragraph("<b>2. PERMANENT DISABILITY RATING ANALYSIS</b>", self.styles['SectionHeader'])
        story.append(title)
        story.append(Spacer(1, 0.1 * inch))

        # Calculate WPI ratings for each body part
        body_part_ratings = []
        total_wpi = 0

        for body_part in self.case.injuries[0].body_parts:
            body_part_lower = body_part.lower()

            # Find matching rating category
            wpi_range = None
            for key, value in WPI_RATINGS.items():
                if key in body_part_lower or body_part_lower in key:
                    wpi_range = value
                    break

            # Default if no match
            if not wpi_range:
                wpi_range = (5, 15)

            # Pick a value within range
            wpi = random.randint(wpi_range[0], wpi_range[1])
            body_part_ratings.append((body_part, wpi))
            total_wpi += wpi

        # Combined WPI (simplified combined values formula)
        if len(body_part_ratings) > 1:
            # Rough approximation: not quite sum, accounts for overlap
            combined_wpi = total_wpi * 0.85
        else:
            combined_wpi = total_wpi

        combined_wpi = int(combined_wpi)

        # Build ratings table
        ratings_text = "<b>Impairment Ratings:</b><br/>"
        for body_part, wpi in body_part_ratings:
            ratings_text += f"&nbsp;&nbsp;• {body_part}: {wpi}% WPI<br/>"
        ratings_text += f"&nbsp;&nbsp;• <b>Combined WPI: {combined_wpi}%</b>"

        story.append(Paragraph(ratings_text, self.styles['BodyText14']))
        story.append(Spacer(1, 0.1 * inch))

        # Adjustment factors (occupation, age)
        adjustment_factor = random.uniform(1.1, 1.4)
        adjusted_pd = int(combined_wpi * adjustment_factor)

        # Weeks of PD (typically 3-5 weeks per percent)
        weeks_per_percent = random.uniform(3, 5)
        pd_weeks = int(adjusted_pd * weeks_per_percent)

        # PD rate (statutory rate)
        pd_rate = 290  # Current CA statutory rate

        # Total PD value
        total_pd = pd_weeks * pd_rate

        calc_text = (
            f"<b>Adjusted PD Rating:</b> {adjusted_pd}% (after occupational and age adjustments)<br/>"
            f"<b>PD Duration:</b> {pd_weeks} weeks<br/>"
            f"<b>Weekly Rate:</b> ${pd_rate}<br/>"
            f"<b>Total PD Indemnity:</b> <b>${total_pd:,}</b>"
        )

        story.append(Paragraph(calc_text, self.styles['BodyText14']))

        # Store for later calculations
        self._pd_value = total_pd

        return story

    def _make_fmc_section(self):
        """Generate future medical care section."""
        story = []

        title = Paragraph("<b>3. FUTURE MEDICAL TREATMENT</b>", self.styles['SectionHeader'])
        story.append(title)
        story.append(Spacer(1, 0.1 * inch))

        # Estimate annual cost based on injury severity
        num_body_parts = len(self.case.injuries[0].body_parts)
        annual_cost = random.randint(3000 + num_body_parts * 2000, 8000 + num_body_parts * 3000)

        # Calculate life expectancy based on age
        dob = self.case.applicant.date_of_birth
        current_age = (date.today() - dob).days // 365
        life_expectancy_years = max(10, 78 - current_age)

        # Apply discount factor for present value
        discount_factor = 0.7
        total_fmc = int(annual_cost * life_expectancy_years * discount_factor)

        fmc_text = (
            f"<b>Estimated Annual FMC:</b> ${annual_cost:,}<br/>"
            f"<b>Life Expectancy:</b> {life_expectancy_years} years (applicant age {current_age})<br/>"
            f"<b>Present Value Discount:</b> {int(discount_factor * 100)}%<br/>"
            f"<b>Total FMC Value:</b> <b>${total_fmc:,}</b><br/><br/>"
            f"<i>Note: Medicare Set-Aside allocation may be required depending on Medicare eligibility "
            f"and settlement amount. Recommend MSA evaluation if settlement exceeds ${int(total_fmc * 0.3):,}.</i>"
        )

        story.append(Paragraph(fmc_text, self.styles['BodyText14']))

        # Store for later calculations
        self._fmc_value = total_fmc

        return story

    def _make_other_benefits_section(self):
        """Generate other benefits section."""
        story = []

        title = Paragraph("<b>4. OTHER BENEFITS</b>", self.styles['SectionHeader'])
        story.append(title)
        story.append(Spacer(1, 0.1 * inch))

        # Calculate TTD (rough estimate based on timeline)
        if self.case.timeline.date_qme_evaluation:
            ttd_days = (self.case.timeline.date_qme_evaluation - self.case.injuries[0].date_of_injury).days
        else:
            ttd_days = random.randint(60, 180)

        # TTD is 2/3 of weekly wage, max $1,619.15 (2024 rate)
        weekly_wage = self.case.employer.hourly_rate * self.case.employer.weekly_hours
        ttd_rate = min(weekly_wage * 2 / 3, 1619.15)
        ttd_weeks = ttd_days // 7
        ttd_paid = int(ttd_rate * ttd_weeks)

        # SJDB voucher
        sjdb_voucher = 6000

        # Self-procured medical (sometimes applicants pay out of pocket)
        self_procured = random.choice([0, 0, random.randint(500, 2000)])

        benefits_text = (
            f"<b>Temporary Total Disability (TTD) Paid:</b> ${ttd_paid:,} "
            f"({ttd_weeks} weeks @ ${ttd_rate:.2f}/week)<br/>"
            f"<b>Supplemental Job Displacement Benefit Voucher:</b> ${sjdb_voucher:,}<br/>"
            f"<b>Self-Procured Medical Reimbursement:</b> ${self_procured:,}"
        )

        story.append(Paragraph(benefits_text, self.styles['BodyText14']))

        # Store for calculations
        self._other_benefits = sjdb_voucher + self_procured

        return story

    def _make_settlement_range_section(self):
        """Generate settlement range section."""
        story = []

        title = Paragraph("<b>5. SETTLEMENT RANGE ANALYSIS</b>", self.styles['SectionHeader'])
        story.append(title)
        story.append(Spacer(1, 0.1 * inch))

        # Calculate settlement range
        low_estimate = self._pd_value + int(self._fmc_value * 0.5) + self._other_benefits
        mid_estimate = self._pd_value + self._fmc_value + self._other_benefits
        high_estimate = self._pd_value + self._fmc_value + self._other_benefits + random.randint(5000, 15000)

        # Target is typically 85-95% of mid estimate
        target = int(mid_estimate * random.uniform(0.85, 0.95))

        range_text = (
            f"<b>Low Estimate:</b> ${low_estimate:,} (reduced FMC consideration)<br/>"
            f"<b>Mid Estimate:</b> ${mid_estimate:,} (full value of all components)<br/>"
            f"<b>High Estimate:</b> ${high_estimate:,} (includes additional considerations)<br/><br/>"
            f"<b><u>Recommended Settlement Target: ${target:,}</u></b><br/><br/>"
            f"<i>This target represents a fair compromise accounting for litigation risks, "
            f"defense medical evaluations, and the applicant's need for closure.</i>"
        )

        story.append(Paragraph(range_text, self.styles['BodyText14']))

        return story

    def _generate_negotiation_strategy(self):
        """Generate negotiation strategy points."""
        strategies = [
            "Begin negotiations at high estimate to establish favorable anchoring. "
            "Defense will likely counter significantly lower, expect protracted negotiation.",

            "Emphasize permanent work restrictions and impact on earning capacity. "
            "Applicant's inability to return to prior occupation strengthens our position.",

            "Leverage QME findings as objective medical evidence supporting our rating. "
            "Anticipate defense medical evaluation may provide lower rating, be prepared to argue.",

            "Highlight future medical needs and present evidence of ongoing treatment requirements. "
            "Medicare Set-Aside considerations add complexity that may motivate settlement.",

            "Consider applicant's personal circumstances and need for closure. Balance maximum recovery "
            "with practical settlement that provides certainty versus litigation risk.",
        ]

        # Pick 2-3 strategies
        selected = random.sample(strategies, random.randint(2, 3))

        strategy_text = ""
        for i, strategy in enumerate(selected, 1):
            strategy_text += f"{i}. {strategy}<br/><br/>"

        return strategy_text.rstrip("<br/>")
