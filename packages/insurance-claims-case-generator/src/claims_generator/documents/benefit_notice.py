"""
BENEFIT_NOTICE document generator — Tier C plain letterhead.

Covers: acceptance, denial, delay, TD rate notice, and generic benefit notices.
Regulatory basis:
  - 10 CCR 2695.7(b): Accept (40 days) or deny (90 days) from claim receipt
  - LC 4650: First TD payment within 14 days of knowledge of disability
  - AD 10133.53 / 10133.55: Notice of TD rate, benefit notices

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
    spacer,
    thick_hline,
)
from claims_generator.documents.registry import register_document
from claims_generator.models.claim import DocumentEvent
from claims_generator.models.enums import DocumentType
from claims_generator.models.profile import ClaimProfile

_ACCEPTANCE_TEXT = (
    "Your Workers' Compensation claim has been accepted pursuant to Labor Code § 3600 "
    "et seq. Benefits payable under this claim include medical treatment reasonably "
    "required to cure or relieve the effects of the industrial injury, and Temporary "
    "Disability (TD) indemnity if you are taken off work by your treating physician.\n\n"
    "Medical treatment must be provided within the Medical Provider Network (MPN) "
    "designated by {carrier_name} unless you have properly predesignated a personal "
    "physician. Please contact your adjuster at {adjuster_phone} to obtain the MPN directory.\n\n"
    "This acceptance is subject to an ongoing investigation of the nature, extent, and "
    "compensability of all claimed body parts. Specific issues including AOE/COE, apportionment "
    "(LC § 4663), and extent of permanent disability remain subject to further evaluation."
)

_DENIAL_TEXT = (
    "Your claim for Workers' Compensation benefits has been denied pursuant to 10 CCR "
    "2695.7(b). Grounds for denial include:\n\n"
    "1. The injury did not arise out of and occur in the course of employment (AOE/COE) "
    "as required by Labor Code § 3600.\n"
    "2. The claimed condition is not work-related based on available medical evidence.\n\n"
    "RIGHT TO DISPUTE: You have the right to dispute this denial by filing an Application "
    "for Adjudication of Claim (ADJ) with the Workers' Compensation Appeals Board (WCAB) "
    "at the district office serving your area. Forms are available at www.dir.ca.gov/dwc.\n\n"
    "STATUTE OF LIMITATIONS: Labor Code § 5405 provides a 1-year statute of limitations "
    "from the date of injury (or date of last payment of indemnity or provision of medical "
    "treatment) to file an Application for Adjudication."
)

_DELAY_TEXT = (
    "Pursuant to 10 CCR 2695.5(b), this notice confirms that {carrier_name} has received "
    "your Workers' Compensation claim. A decision on your claim's compensability has not yet "
    "been made. We are currently investigating the circumstances of your reported injury.\n\n"
    "A determination will be made within the timeframes required by 10 CCR 2695.7(b): "
    "acceptance within 40 days or denial within 90 days of claim receipt.\n\n"
    "You are entitled to up to $10,000 in medical treatment while your claim is under "
    "investigation (Labor Code § 5402(c))."
)

_TD_RATE_TEXT = (
    "Pursuant to Labor Code § 4650 and Administrative Director Form AD 10133.55, this "
    "notice confirms your Temporary Disability (TD) benefit rate as follows:\n\n"
    "Your TD benefits will be paid at the rate stated below. TD payments are due within "
    "14 days of the employer's knowledge of disability (LC § 4650). Continued payments are "
    "due every 14 days while TD status continues.\n\n"
    "If you disagree with the TD rate, you may request a Benefit Audit (LC § 129) through "
    "the Division of Workers' Compensation. Contact your adjuster to request a wage statement "
    "review under 8 CCR 10166."
)


@register_document
class BenefitNoticeGenerator(DocumentGenerator):
    """Tier C — benefit notices (acceptance, denial, delay, TD rate)."""

    handles = frozenset({DocumentType.BENEFIT_NOTICE})

    @classmethod
    def generate(cls, event: DocumentEvent, profile: ClaimProfile) -> bytes:
        buf = io.BytesIO()
        doc = cls._build_doc(buf, title=event.title)

        ins = profile.insurer
        fin = profile.financial
        claimant = profile.claimant

        fmt = {
            "carrier_name": ins.carrier_name,
            "claim_number": ins.claim_number,
            "adjuster_phone": ins.adjuster_phone,
        }

        # Select body text
        slug = event.subtype_slug
        if "acceptance" in slug:
            body_text = _ACCEPTANCE_TEXT.format(**fmt)
            notice_type = "NOTICE OF ACCEPTANCE"
        elif "denial" in slug:
            body_text = _DENIAL_TEXT.format(**fmt)
            notice_type = "NOTICE OF DENIAL"
        elif "delay" in slug:
            body_text = _DELAY_TEXT.format(**fmt)
            notice_type = "NOTICE OF DELAY IN CLAIMS DECISION"
        elif "td_rate" in slug:
            body_text = _TD_RATE_TEXT.format(**fmt)
            notice_type = "NOTICE OF TEMPORARY DISABILITY RATE"
        else:
            body_text = (
                f"This notice is issued pursuant to the California Workers' Compensation "
                f"laws regarding Claim No. {ins.claim_number}. Please contact your adjuster "
                f"at {ins.adjuster_phone} for further information."
            )
            notice_type = "BENEFIT NOTICE"

        story: list = []
        story.extend(carrier_header_block(profile, form_id="AD 10133.53"))
        story.append(spacer(6))
        story.append(para(notice_type, "title"))
        story.append(para(f"Form: AD 10133.53 | Date: {event.event_date}", "small"))
        story.append(thick_hline())

        story.extend(
            claimant_caption_block(
                profile,
                event_date=event.event_date,
                event_title=event.title,
            )
        )

        for paragraph_text in body_text.split("\n\n"):
            if paragraph_text.strip():
                story.append(para(paragraph_text.replace("\n", "<br/>"), "body"))
                story.append(spacer(4))

        # TD rate details for TD rate notices
        if "td_rate" in slug:
            story.append(spacer(6))
            story.append(para("BENEFIT RATE DETAIL", "heading1"))
            story.append(hline())
            story.append(
                label_value_table([
                    ("Claimant:", f"{claimant.first_name} {claimant.last_name}"),
                    ("Avg. Weekly Wage (AWW):", f"${fin.average_weekly_wage:,.2f}"),
                    ("TD Weekly Rate (2/3 AWW):", f"${fin.td_weekly_rate:,.2f}/week"),
                    ("Statutory Minimum (Inj. Year):", f"${fin.td_min_rate:,.2f}/week"),
                    ("Statutory Maximum (Inj. Year):", f"${fin.td_max_rate:,.2f}/week"),
                    ("Injury Year:", str(fin.injury_year)),
                    ("Statutory Authority:", "LC §§ 4453, 4650, 4657"),
                ])
            )

        citations = [event.deadline_statute] if event.deadline_statute else []
        citations.append("10 CCR 2695.7(b)")
        citations.append("LC §§ 3600, 4650")
        story.extend(regulatory_citation_block(list(dict.fromkeys(c for c in citations if c))))

        story.extend(confidentiality_footer())
        doc.build(story)
        return buf.getvalue()
