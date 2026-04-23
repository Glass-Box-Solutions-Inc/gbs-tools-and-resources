"""
WCAB_FILING document generator — Tier B structured layout.

Covers: Application for Adjudication (ADJ), Declaration of Readiness to Proceed (DOR),
Minutes of Hearing, Orders.
Regulatory basis:
  - 8 CCR 10400: Application for Adjudication of Claim
  - 8 CCR 10414: Declaration of Readiness to Proceed
  - LC § 5500: Commencement of proceedings

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

# WCAB district offices by county
_WCAB_VENUES: dict[str, str] = {
    "Los Angeles": "Los Angeles",
    "San Diego": "San Diego",
    "Orange": "Anaheim",
    "Riverside": "Riverside",
    "San Bernardino": "San Bernardino",
    "Sacramento": "Sacramento",
    "Fresno": "Fresno",
    "Alameda": "Oakland",
    "Santa Clara": "San Jose",
}


def _get_venue(county: str) -> str:
    return _WCAB_VENUES.get(county, "Los Angeles")


@register_document
class WCABFilingGenerator(DocumentGenerator):
    """Tier B — WCAB filings (Application for Adjudication, DOR, etc.)."""

    handles = frozenset({DocumentType.WCAB_FILING})

    @classmethod
    def generate(cls, event: DocumentEvent, profile: ClaimProfile) -> bytes:
        buf = io.BytesIO()
        doc = cls._build_doc(buf, title=event.title)

        claimant = profile.claimant
        ins = profile.insurer
        med = profile.medical
        employer = profile.employer

        venue = _get_venue(claimant.address_county)
        slug = event.subtype_slug

        story: list = []
        story.extend(carrier_header_block(profile))
        story.append(spacer(4))

        if "application" in slug or "adj" in slug:
            story.append(para("APPLICATION FOR ADJUDICATION OF CLAIM", "title"))
            story.append(para(f"WCAB {venue} District Office | LC § 5500 | 8 CCR 10400", "small"))
            story.append(thick_hline())
            story.extend(wcab_caption(profile, wcab_venue=venue))
            story.append(spacer(6))
            story.append(para("APPLICANT INFORMATION", "heading1"))
            story.append(hline())
            story.append(
                label_value_table([
                    ("Applicant Name:", f"{claimant.first_name} {claimant.last_name}"),
                    ("Date of Birth:", str(claimant.date_of_birth)),
                    ("Address:", f"{claimant.address_city}, CA {claimant.address_zip}"),
                    ("County:", claimant.address_county),
                    ("Occupation:", claimant.occupation_title),
                    ("Employer:", employer.company_name),
                    ("Insurer:", ins.carrier_name),
                    ("Claim No.:", ins.claim_number),
                    ("Date of Injury (DOI):", med.date_of_injury),
                    ("Body Parts:", ", ".join(bp.body_part for bp in med.body_parts)),
                ])
            )
            story.append(spacer(6))
            story.append(para("ISSUES IN DISPUTE", "heading1"))
            story.append(hline())
            story.append(para(
                "Applicant contends that the following issues are in dispute:<br/>"
                "1. Compensability of the claimed industrial injury (AOE/COE).<br/>"
                "2. Nature and extent of permanent disability (LC § 4660).<br/>"
                "3. Apportionment under Labor Code § 4663.<br/>"
                "4. Future medical treatment.<br/>"
                "5. Temporary disability benefits (LC § 4650).",
                "body",
            ))
            story.extend(
                regulatory_citation_block(["8 CCR 10400", "LC §§ 5500, 4660, 4663"])
            )

        elif "dor" in slug or "readiness" in slug:
            story.append(para("DECLARATION OF READINESS TO PROCEED", "title"))
            story.append(para(f"WCAB {venue} District Office | 8 CCR 10414", "small"))
            story.append(thick_hline())
            story.extend(wcab_caption(profile, wcab_venue=venue))
            story.append(spacer(6))
            story.append(
                label_value_table([
                    ("Claim No.:", ins.claim_number),
                    ("Requesting Party:", ins.carrier_name),
                    ("Date:", str(event.event_date)),
                    ("Venue:", f"{venue} WCAB"),
                ])
            )
            story.append(spacer(6))
            story.append(para("DECLARATION", "heading1"))
            story.append(hline())
            story.append(
                para(
                    "The undersigned declares that the above-captioned case is ready to proceed "
                    "to hearing. All discovery has been completed, or the requesting party waives "
                    "further discovery. The case is ready for a Mandatory Settlement Conference (MSC) "
                    "and/or trial on the issues of permanent disability and medical treatment.\n\n"
                    "Pursuant to 8 CCR 10414, this Declaration of Readiness is filed to request "
                    "a hearing date at the earliest available calendar. All parties have been "
                    "served with a copy of this declaration.",
                    "body",
                )
            )
            story.extend(regulatory_citation_block(["8 CCR 10414", "LC § 5500"]))

        else:
            story.append(para("WCAB FILING", "title"))
            story.append(para(f"WCAB {venue} District Office", "small"))
            story.append(thick_hline())
            story.extend(wcab_caption(profile, wcab_venue=venue))
            story.append(spacer(6))
            story.append(
                label_value_table([
                    ("Document Type:", event.title),
                    ("Claim No.:", ins.claim_number),
                    ("Date Filed:", str(event.event_date)),
                    ("Stage:", event.stage),
                ])
            )
            story.extend(regulatory_citation_block(["LC § 5500", "8 CCR 10400"]))

        story.extend(confidentiality_footer())
        doc.build(story)
        return buf.getvalue()
