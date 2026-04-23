"""
WORK_PRODUCT document generator — Tier B structured layout.

Covers: attorney work product, case evaluation memoranda, reserve analysis.
Access level: ATTORNEY_ONLY.
Regulatory basis:
  - LC § 3762: Attorney-client privilege in WC
  - Evidence Code § 952: Attorney work product doctrine
  - 8 CCR 10607: Privilege in WC proceedings

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import io

from claims_generator.documents.base_document import DocumentGenerator
from claims_generator.documents.letterhead import (
    carrier_header_block,
    confidentiality_footer,
    regulatory_citation_block,
    wcab_caption,
)
from claims_generator.documents.pdf_primitives import (
    COLOR_WARNING,
    hline,
    label_value_table,
    para,
    spacer,
    thick_hline,
)
from claims_generator.documents.registry import register_document
from claims_generator.models.claim import DocumentEvent
from claims_generator.models.enums import DocumentType
from claims_generator.models.profile import ClaimProfile


@register_document
class WorkProductGenerator(DocumentGenerator):
    """Tier B — attorney work product, case evaluations."""

    handles = frozenset({DocumentType.WORK_PRODUCT})

    @classmethod
    def generate(cls, event: DocumentEvent, profile: ClaimProfile) -> bytes:
        buf = io.BytesIO()
        doc = cls._build_doc(buf, title=event.title)

        ins = profile.insurer
        med = profile.medical
        claimant = profile.claimant
        fin = profile.financial

        pd_pct = fin.estimated_pd_percent or 15.0
        pd_weeks = fin.estimated_pd_weeks or 78.0
        pd_rate = fin.td_weekly_rate * 0.60
        pd_value = pd_rate * pd_weeks
        settlement_range_low = pd_value * 0.85
        settlement_range_high = pd_value * 1.25 + 10000

        story: list = []
        story.extend(carrier_header_block(profile))
        story.append(spacer(4))
        story.append(para("PRIVILEGED AND CONFIDENTIAL", "warning"))
        story.append(para("ATTORNEY WORK PRODUCT — DO NOT DISCLOSE", "warning"))
        story.append(para("CASE EVALUATION MEMORANDUM", "title"))
        story.append(para("Evidence Code § 952 | LC § 3762", "small"))
        story.append(thick_hline())

        story.extend(wcab_caption(profile))
        story.append(spacer(6))

        story.append(para("MEMORANDUM", "heading1"))
        story.append(hline())
        story.append(
            label_value_table([
                ("TO:", f"{ins.adjuster_name} — {ins.carrier_name}"),
                ("FROM:", "Defense Counsel"),
                ("DATE:", str(event.event_date)),
                ("RE:", f"Case Evaluation — {claimant.first_name} {claimant.last_name}"),
                ("CLAIM NO.:", ins.claim_number),
            ])
        )

        story.append(spacer(6))
        story.append(para("I. CASE OVERVIEW", "heading1"))
        story.append(hline())
        story.append(
            para(
                f"Claimant {claimant.first_name} {claimant.last_name} filed a workers' "
                f"compensation claim arising from a reported {med.injury_mechanism} on "
                f"{med.date_of_injury} while employed by {profile.employer.company_name}. "
                f"The claimed body parts include {', '.join(bp.body_part for bp in med.body_parts)}.\n\n"
                f"This memorandum evaluates exposure and recommends a resolution strategy "
                f"consistent with the evidence and applicable law.",
                "body",
            )
        )

        story.append(spacer(6))
        story.append(para("II. LIABILITY ANALYSIS", "heading1"))
        story.append(hline())
        story.append(
            para(
                "AOE/COE: Based on available records, the mechanism of injury is consistent "
                "with the described work activities. Industrial causation is likely under "
                "LC § 3600. Denial risk: LOW.\n\n"
                "APPORTIONMENT (LC § 4663): Review of prior medical history indicates "
                "potential non-industrial contributing factors. Apportionment analysis is "
                "warranted pending complete prior records.",
                "body",
            )
        )

        story.append(spacer(6))
        story.append(para("III. EXPOSURE EVALUATION", "heading1"))
        story.append(hline())
        story.append(
            label_value_table([
                ("Estimated PD%:", f"{pd_pct:.1f}%"),
                ("PD Rate:", f"${pd_rate:,.2f}/week"),
                ("PD Weeks:", f"{pd_weeks:.1f}"),
                ("PD Value:", f"${pd_value:,.2f}"),
                ("Settlement Range:", f"${settlement_range_low:,.2f} – ${settlement_range_high:,.2f}"),
                ("Life Pension:", "Yes" if fin.life_pension_eligible else "No"),
                ("Future Medical Exposure:", "$25,000 – $50,000 (estimated)"),
                ("Lien Exposure:", "TBD — see lien log"),
                ("Total Gross Exposure:", f"${settlement_range_high + 35000:,.2f} (high end)"),
            ])
        )

        story.append(spacer(6))
        story.append(para("IV. RECOMMENDATION", "heading1"))
        story.append(hline())
        story.append(
            para(
                "Defense recommends targeting a Compromise and Release (C&R) settlement "
                f"in the range of ${settlement_range_low:,.2f} – ${settlement_range_high:,.2f} "
                "inclusive of future medical. A Stipulations settlement should be considered "
                "if Applicant's counsel demands open future medical.\n\n"
                "Key defense positions:\n"
                "1. Pursue apportionment per LC § 4663.\n"
                "2. Challenge WPI rating if QME report is excessive.\n"
                "3. Obtain independent IME if treating physician is sympathetic.\n"
                "4. Monitor for fraud indicators per 8 CCR 15401.",
                "body",
            )
        )

        story.extend(
            regulatory_citation_block([
                "Evidence Code § 952", "LC § 3762", "LC §§ 4663, 5100.5"
            ])
        )
        story.extend(confidentiality_footer())
        doc.build(story)
        return buf.getvalue()
