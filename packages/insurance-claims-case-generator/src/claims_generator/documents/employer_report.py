"""
EMPLOYER_REPORT document generator — Tier C plain letterhead.

Covers: DLSR 5020 Employer's Report of Occupational Injury or Illness.
Form identifier: DLSR 5020.
Regulatory basis:
  - LC § 6409.1: Employer reporting requirements
  - 8 CCR 14006: DLSR 5020 filing requirements
  - Within 5 days for serious injuries (LC § 6409)

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
    two_col_section,
)
from claims_generator.documents.registry import register_document
from claims_generator.models.claim import DocumentEvent
from claims_generator.models.enums import DocumentType
from claims_generator.models.profile import ClaimProfile


@register_document
class EmployerReportGenerator(DocumentGenerator):
    """Tier C — employer's report of occupational injury (DLSR 5020)."""

    handles = frozenset({DocumentType.EMPLOYER_REPORT})

    @classmethod
    def generate(cls, event: DocumentEvent, profile: ClaimProfile) -> bytes:
        buf = io.BytesIO()
        doc = cls._build_doc(buf, title=event.title)

        ins = profile.insurer
        med = profile.medical
        claimant = profile.claimant
        employer = profile.employer

        body_parts_str = ", ".join(
            f"{bp.body_part}{' (' + bp.laterality + ')' if bp.laterality else ''}"
            for bp in med.body_parts
        )
        primary_icd = (
            f"{med.icd10_codes[0].code} — {med.icd10_codes[0].description}"
            if med.icd10_codes else "Pending medical evaluation"
        )

        story: list = []
        story.extend(carrier_header_block(profile, form_id="DLSR 5020"))
        story.append(spacer(4))
        story.append(para("EMPLOYER'S REPORT OF OCCUPATIONAL INJURY OR ILLNESS", "title"))
        story.append(para("Form DLSR 5020 | LC § 6409.1 | 8 CCR 14006", "subtitle"))
        story.append(para(
            "Required to be filed with insurer within 5 days of employer's knowledge "
            "of injury. Copy filed with DWC within 5 days for serious injuries (LC § 6409).",
            "small",
        ))
        story.append(thick_hline())

        story.extend(
            claimant_caption_block(
                profile,
                event_date=event.event_date,
                event_title=event.title,
            )
        )

        story.append(para("SECTION 1: EMPLOYER INFORMATION", "heading1"))
        story.append(hline())
        story.append(
            two_col_section(
                left_items=[
                    ("Employer", employer.company_name),
                    ("Industry", employer.industry),
                    ("State", "CA"),
                ],
                right_items=[
                    ("EIN (last 4)", employer.ein_last4),
                    ("Insurer", ins.carrier_name),
                    ("Policy No.", ins.policy_number),
                ],
            )
        )

        story.append(spacer(6))
        story.append(para("SECTION 2: EMPLOYEE / CLAIMANT INFORMATION", "heading1"))
        story.append(hline())
        story.append(
            two_col_section(
                left_items=[
                    ("Employee Name", f"{claimant.first_name} {claimant.last_name}"),
                    ("Date of Birth", str(claimant.date_of_birth)),
                    ("Occupation", claimant.occupation_title),
                ],
                right_items=[
                    ("City", claimant.address_city),
                    ("County", claimant.address_county),
                    ("SSN (last 4)", claimant.ssn_last4),
                ],
            )
        )

        story.append(spacer(6))
        story.append(para("SECTION 3: INJURY INFORMATION", "heading1"))
        story.append(hline())
        story.append(
            label_value_table([
                ("Date of Injury (DOI):", med.date_of_injury),
                ("Time of Injury:", "During regular work hours"),
                ("Injury Location:", f"{employer.address_city}, CA workplace"),
                ("Mechanism / How Injured:", med.injury_mechanism),
                ("Activity at Time of Injury:", claimant.occupation_title or "Regular work duties"),
                ("Body Parts Injured:", body_parts_str),
                ("Nature of Injury (ICD-10):", primary_icd),
                ("Medical Treatment Required:", "Yes — referred to MPN physician"),
                ("Lost Time:", "Yes" if med.mmi_reached else "Yes — ongoing"),
                ("Returned to Work:", "No" if not med.mmi_reached else "Modified duty"),
            ])
        )

        story.append(spacer(6))
        story.append(para("SECTION 4: WITNESS INFORMATION", "heading1"))
        story.append(hline())
        story.append(
            label_value_table([
                ("Witness 1:", "Co-worker — name on file"),
                ("Witness 2:", "Supervisor — name on file"),
                ("Date Employer Notified:", med.date_of_injury),
                ("Supervisor:", "On file"),
            ])
        )

        story.append(spacer(6))
        story.append(
            para(
                f"This report is filed by {employer.company_name} pursuant to Labor Code "
                f"§ 6409.1. The employer is required to file this report with the insurer "
                f"within 5 days of learning of the injury.",
                "small",
            )
        )
        story.append(
            label_value_table([
                ("Authorized by:", "HR / Safety Manager"),
                ("Date Submitted:", str(event.event_date)),
            ])
        )

        story.extend(
            regulatory_citation_block(["LC § 6409.1", "8 CCR 14006", "DLSR 5020"])
        )
        story.extend(confidentiality_footer())
        doc.build(story)
        return buf.getvalue()
