"""
WAGE_STATEMENT document generator — Tier C plain letterhead.

Covers: employer wage verification statements.
Regulatory basis:
  - LC § 4453: Earnings basis for TD rate calculation
  - 8 CCR 10166: Wage statement requirements
  - 8 CCR 9785(a): Treating physician wage reporting duties

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import io

from claims_generator.documents.base_document import DocumentGenerator
from claims_generator.documents.letterhead import (
    carrier_header_block,
    claimant_caption_block,
    confidentiality_footer,
    regulatory_citation_block,
)
from claims_generator.documents.pdf_primitives import (
    hline,
    label_value_table,
    para,
    section_table,
    spacer,
    thick_hline,
)
from claims_generator.documents.registry import register_document
from claims_generator.models.claim import DocumentEvent
from claims_generator.models.enums import DocumentType
from claims_generator.models.profile import ClaimProfile


@register_document
class WageStatementGenerator(DocumentGenerator):
    """Tier C — employer wage verification statements."""

    handles = frozenset({DocumentType.WAGE_STATEMENT})

    @classmethod
    def generate(cls, event: DocumentEvent, profile: ClaimProfile) -> bytes:
        buf = io.BytesIO()
        doc = cls._build_doc(buf, title=event.title)

        ins = profile.insurer  # noqa: F841
        fin = profile.financial
        claimant = profile.claimant
        employer = profile.employer

        # Derive weekly earnings breakdown from AWW
        aww = fin.average_weekly_wage
        hourly_rate = aww / 40.0  # Assume 40-hour week
        overtime = aww * 0.15     # Approximate OT component

        story: list = []
        story.extend(carrier_header_block(profile))
        story.append(spacer(4))
        story.append(para("EMPLOYER WAGE VERIFICATION STATEMENT", "title"))
        story.append(para("LC § 4453 | 8 CCR 10166 | TD Rate Verification", "small"))
        story.append(thick_hline())

        story.extend(
            claimant_caption_block(
                profile,
                event_date=event.event_date,
                event_title=event.title,
            )
        )

        story.append(para("EMPLOYER CERTIFICATION", "heading1"))
        story.append(hline())
        story.append(
            label_value_table([
                ("Employer:", employer.company_name),
                ("Industry:", employer.industry),
                ("State:", "CA"),
                ("EIN (last 4):", employer.ein_last4),
                ("Employee:", f"{claimant.first_name} {claimant.last_name}"),
                ("Occupation:", claimant.occupation_title),
                ("Employment Length:", f"{claimant.years_employed or 1.5:.1f} years"),
                ("Date of Injury (DOI):", profile.medical.date_of_injury),
                ("Date Prepared:", str(event.event_date)),
            ])
        )

        story.append(spacer(8))
        story.append(para("WAGE AND EARNINGS DETAIL (52-WEEK PERIOD PRIOR TO DOI)", "heading1"))
        story.append(hline())
        story.append(
            section_table(
                headers=["Earnings Component", "Weekly Amount", "Annual Amount"],
                rows=[
                    ["Base/Regular Wages", f"${aww - overtime:,.2f}", f"${(aww - overtime) * 52:,.2f}"],  # noqa: E501
                    ["Overtime", f"${overtime:,.2f}", f"${overtime * 52:,.2f}"],
                    ["TOTAL AWW", f"${aww:,.2f}", f"${aww * 52:,.2f}"],
                ],
            )
        )

        story.append(spacer(6))
        story.append(para("BENEFIT RATE CALCULATION (LC § 4453)", "heading1"))
        story.append(hline())
        story.append(
            label_value_table([
                ("Average Weekly Wage (AWW):", f"${aww:,.2f}"),
                ("TD Rate (2/3 of AWW):", f"${fin.td_weekly_rate:,.2f}"),
                ("Statutory Minimum:", f"${fin.td_min_rate:,.2f}"),
                ("Statutory Maximum:", f"${fin.td_max_rate:,.2f}"),
                ("Injury Year:", str(fin.injury_year)),
                ("Calculated Rate Applied:", f"${fin.td_weekly_rate:,.2f}/week"),
                ("Hourly Rate (approx.):", f"${hourly_rate:,.2f}/hr"),
            ])
        )

        story.append(spacer(6))
        story.append(
            para(
                f"I, the undersigned authorized representative of {employer.company_name}, "
                f"hereby certify under penalty of perjury that the wage information stated "
                f"above is true and correct to the best of my knowledge.",
                "body",
            )
        )
        story.append(spacer(4))
        story.append(
            label_value_table([
                ("Authorized Signature:", "______________________________"),
                ("Title:", "Payroll / HR Representative"),
                ("Date:", str(event.event_date)),
            ])
        )

        story.extend(
            regulatory_citation_block(["LC § 4453", "8 CCR 10166"])
        )
        story.extend(confidentiality_footer())
        doc.build(story)
        return buf.getvalue()
