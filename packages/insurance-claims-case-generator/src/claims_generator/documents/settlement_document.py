"""
SETTLEMENT_DOCUMENT document generator — Tier B structured layout.

Covers: Compromise and Release (C&R), Stipulations with Request for Award.
Access level: DUAL_ACCESS.
Regulatory basis:
  - LC § 5100.5: Compromise and Release requirements
  - LC § 5702: Stipulations with Request for Award
  - 8 CCR 10700: Settlement agreement format requirements

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
class SettlementDocumentGenerator(DocumentGenerator):
    """Tier B — settlement documents (C&R, Stipulations)."""

    handles = frozenset({DocumentType.SETTLEMENT_DOCUMENT})

    @classmethod
    def generate(cls, event: DocumentEvent, profile: ClaimProfile) -> bytes:
        buf = io.BytesIO()
        doc = cls._build_doc(buf, title=event.title)

        claimant = profile.claimant
        ins = profile.insurer
        med = profile.medical
        fin = profile.financial
        employer = profile.employer

        slug = event.subtype_slug
        is_cr = "compromise" in slug or "release" in slug

        # Calculate settlement values
        pd_pct = fin.estimated_pd_percent or 15.0
        pd_weeks = fin.estimated_pd_weeks or 78.0
        pd_rate = fin.td_weekly_rate * 0.60
        pd_value = pd_rate * pd_weeks
        future_med = 15000.0 if is_cr else 0.0
        lien_reserve = 5000.0 if is_cr else 0.0
        gross_settlement = pd_value + future_med + lien_reserve if is_cr else pd_value

        story: list = []
        story.extend(carrier_header_block(profile))
        story.append(spacer(4))

        if is_cr:
            story.append(para("COMPROMISE AND RELEASE AGREEMENT", "title"))
            story.append(para("LC § 5100.5 | 8 CCR 10700 | WCAB Form C&R", "small"))
        else:
            story.append(para("STIPULATIONS WITH REQUEST FOR AWARD", "title"))
            story.append(para("LC § 5702 | 8 CCR 10700 | WCAB Form STIPS", "small"))

        story.append(thick_hline())
        story.extend(wcab_caption(profile))
        story.append(spacer(6))

        story.append(para("PARTIES AND CLAIM INFORMATION", "heading1"))
        story.append(hline())
        story.append(
            label_value_table([
                ("Applicant:", f"{claimant.first_name} {claimant.last_name}"),
                ("Date of Birth:", str(claimant.date_of_birth)),
                ("Defendant/Employer:", employer.company_name),
                ("Insurance Carrier:", ins.carrier_name),
                ("Claim No.:", ins.claim_number),
                ("Policy No.:", ins.policy_number),
                ("Date of Injury (DOI):", med.date_of_injury),
                ("Body Parts:", ", ".join(bp.body_part for bp in med.body_parts)),
                ("Settlement Date:", str(event.event_date)),
            ])
        )

        story.append(spacer(6))
        story.append(para("BENEFIT SUMMARY", "heading1"))
        story.append(hline())

        if is_cr:
            rows = [
                ("Permanent Disability % (PD%):", f"{pd_pct:.1f}%"),
                ("PD Rate:", f"${pd_rate:,.2f}/week"),
                ("PD Weeks:", f"{pd_weeks:.1f}"),
                ("PD Value:", f"${pd_value:,.2f}"),
                ("Future Medical (allocated):", f"${future_med:,.2f}"),
                ("Lien Reserve:", f"${lien_reserve:,.2f}"),
                ("GROSS SETTLEMENT:", f"${gross_settlement:,.2f}"),
            ]
            story.append(label_value_table(rows))
            story.append(spacer(6))
            story.append(para("COMPROMISE AND RELEASE TERMS", "heading1"))
            story.append(hline())
            story.append(
                para(
                    f"In consideration of the gross sum of <b>${gross_settlement:,.2f}</b>, "
                    f"Applicant {claimant.first_name} {claimant.last_name} hereby releases and "
                    f"discharges {employer.company_name} and {ins.carrier_name} from any and all "
                    f"liability for workers' compensation benefits arising out of the injury of "
                    f"{med.date_of_injury}, including all present and future claims for:<br/><br/>"
                    f"• Temporary disability (LC §§ 4650–4657)<br/>"
                    f"• Permanent disability (LC §§ 4658–4660)<br/>"
                    f"• Future medical treatment (LC § 4600)<br/>"
                    f"• Supplemental Job Displacement Benefits (LC § 4658.7)<br/>"
                    f"• Death benefits (LC § 4700 et seq.)<br/><br/>"
                    f"This release is a FULL AND COMPLETE RELEASE of all claims arising from "
                    f"the DOI stated above. Subject to WCAB approval per LC § 5100.6.",
                    "body",
                )
            )
        else:
            rows = [
                ("Permanent Disability % (PD%):", f"{pd_pct:.1f}%"),
                ("PD Rate:", f"${pd_rate:,.2f}/week"),
                ("PD Weeks:", f"{pd_weeks:.1f}"),
                ("PD Value:", f"${pd_value:,.2f}"),
                ("Future Medical:", "Open per LC § 4600"),
                ("Life Pension:", "Yes" if fin.life_pension_eligible else "Not applicable"),
            ]
            story.append(label_value_table(rows))
            story.append(spacer(6))
            story.append(para("STIPULATIONS", "heading1"))
            story.append(hline())
            story.append(
                para(
                    f"The parties hereby stipulate and agree as follows:<br/><br/>"
                    f"1. Date of Injury: {med.date_of_injury}<br/>"
                    f"2. Body Parts: {', '.join(bp.body_part for bp in med.body_parts)}<br/>"
                    f"3. Permanent Disability: {pd_pct:.1f}%<br/>"
                    f"4. Future Medical: Open and continuing per LC § 4600<br/>"
                    f"5. All other benefits to be determined by the WCAB.<br/><br/>"
                    f"The parties request that the WCAB issue an award consistent with these "
                    f"stipulations. Any disputes not addressed herein are reserved.",
                    "body",
                )
            )

        story.append(spacer(8))
        story.append(para("SIGNATURES", "heading1"))
        story.append(hline())
        story.append(
            label_value_table([
                ("Applicant:", "______________________________"),
                ("Applicant's Attorney:", "______________________________"),
                ("Defendant's Representative:", ins.adjuster_name),
                ("Defense Attorney:", "______________________________"),
                ("Date:", str(event.event_date)),
            ])
        )

        story.extend(
            regulatory_citation_block([
                "LC §§ 5100.5, 5702", "8 CCR 10700", "LC § 4600"
            ])
        )
        story.extend(confidentiality_footer())
        doc.build(story)
        return buf.getvalue()
