"""
PAYMENT_RECORD document generator — Tier C plain letterhead.

Covers: first TD payment, PD worksheet, final PD payment records.
Regulatory basis:
  - LC 4650: First TD payment within 14 days of knowledge of disability
  - LC 4657: TD payment amount calculation (2/3 AWW)
  - LC 4658: PD benefit schedule
  - 8 CCR 10166: Wage statement requirements

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
class PaymentRecordGenerator(DocumentGenerator):
    """Tier C — payment records (TD, PD worksheet, final PD)."""

    handles = frozenset({DocumentType.PAYMENT_RECORD})

    @classmethod
    def generate(cls, event: DocumentEvent, profile: ClaimProfile) -> bytes:
        buf = io.BytesIO()
        doc = cls._build_doc(buf, title=event.title)

        ins = profile.insurer
        fin = profile.financial
        claimant = profile.claimant

        slug = event.subtype_slug

        story: list = []
        story.extend(carrier_header_block(profile))
        story.append(spacer(4))
        story.append(para("PAYMENT RECORD", "title"))
        story.append(para(f"Date: {event.event_date} | Claim No.: {ins.claim_number}", "small"))
        story.append(thick_hline())

        story.extend(
            claimant_caption_block(
                profile,
                event_date=event.event_date,
                event_title=event.title,
            )
        )

        if "td" in slug:
            # Temporary Disability payment record
            story.append(para("TEMPORARY DISABILITY PAYMENT DETAIL", "heading1"))
            story.append(hline())

            story.append(
                label_value_table([
                    ("Claimant:", f"{claimant.first_name} {claimant.last_name}"),
                    ("Claim No.:", ins.claim_number),
                    ("Payment Type:", "Temporary Disability (TD) Indemnity"),
                    ("AWW (Average Weekly Wage):", f"${fin.average_weekly_wage:,.2f}"),
                    ("TD Rate (2/3 AWW):", f"${fin.td_weekly_rate:,.2f}/week"),
                    ("Statutory Minimum:", f"${fin.td_min_rate:,.2f}/week"),
                    ("Statutory Maximum:", f"${fin.td_max_rate:,.2f}/week"),
                    ("Injury Year:", str(fin.injury_year)),
                    ("Payment Date:", str(event.event_date)),
                    ("Statutory Authority:", "LC §§ 4650, 4653, 4657"),
                ])
            )

            story.append(spacer(8))
            story.append(para("PAYMENT SCHEDULE", "heading2"))
            story.append(
                section_table(
                    headers=["Pay Period", "Gross Amount", "Net Amount", "Status"],
                    rows=[
                        [
                            f"Week 1 (from {event.event_date})",
                            f"${fin.td_weekly_rate:,.2f}",
                            f"${fin.td_weekly_rate:,.2f}",
                            "ISSUED",
                        ]
                    ],
                )
            )
            story.append(
                para(
                    "TD payments continue every 14 days while disability status is certified "
                    "by the treating physician. Per LC § 4650, late TD payments are subject to "
                    "a 10% self-imposed increase penalty.",
                    "small",
                )
            )
            story.extend(
                regulatory_citation_block(["LC §§ 4650, 4653, 4657", "8 CCR 10166"])
            )

        elif "pd" in slug and "worksheet" in slug:
            # PD worksheet
            story.append(para("PERMANENT DISABILITY BENEFIT CALCULATION WORKSHEET", "heading1"))
            story.append(hline())

            pd_pct = fin.estimated_pd_percent or 0.0
            pd_weeks = fin.estimated_pd_weeks or 0.0
            pd_weekly = fin.td_weekly_rate * 0.60  # PD rate approx 60% of AWW

            story.append(
                label_value_table([
                    ("WPI % (Whole Person Impairment):", f"{pd_pct:.1f}%"),
                    ("Adj. PD% (per LC § 4660 formula):", f"{pd_pct:.1f}%"),
                    ("PD Weekly Rate:", f"${pd_weekly:,.2f}/week"),
                    ("PD Weeks:", f"{pd_weeks:.1f} weeks"),
                    ("Total PD Value:", f"${pd_weekly * pd_weeks:,.2f}"),
                    ("Life Pension Eligible:", "Yes" if fin.life_pension_eligible else "No"),
                    ("Rating Method:", "AMA Guides 5th Edition + PDRS 2005"),
                    ("Apportionment Applied:", "None documented (subject to final eval)"),
                    ("Statutory Authority:", "LC §§ 4658, 4660, 4663"),
                ])
            )
            story.extend(
                regulatory_citation_block(["LC §§ 4658, 4660, 4663", "8 CCR 10166"])
            )

        else:
            # Final / generic payment record
            story.append(para("FINAL BENEFIT PAYMENT RECORD", "heading1"))
            story.append(hline())
            story.append(
                label_value_table([
                    ("Claimant:", f"{claimant.first_name} {claimant.last_name}"),
                    ("Claim No.:", ins.claim_number),
                    ("Payment Date:", str(event.event_date)),
                    ("Payment Type:", "Final Benefits Payment"),
                    ("Carrier:", ins.carrier_name),
                    ("Adjuster:", ins.adjuster_name),
                ])
            )
            story.extend(
                regulatory_citation_block(["LC §§ 4650, 4658"])
            )

        story.extend(confidentiality_footer())
        doc.build(story)
        return buf.getvalue()
