"""
DWC_OFFICIAL_FORM document generator — Tier A form-accurate approximation.

Covers:
  - DWC Form 105: QME Panel Request
  - DEU Formal Rating: Permanent Disability rating

NOTE: PNG blank forms are NOT available in assets/. Using table approximation
per Phase 2 plan. Logged to ISSUES.md.

Regulatory basis:
  - 8 CCR 31.1: QME panel request procedures (Form 105)
  - 8 CCR 10160: DEU (Disability Evaluation Unit) rating procedures
  - LC § 4660: Permanent disability rating scale
  - AMA Guides 5th Edition: WPI methodology

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import io

from claims_generator.documents.base_document import DocumentGenerator
from claims_generator.documents.form_renderer import (
    checkbox_field,
    form_row,
    form_section_header,
)
from claims_generator.documents.letterhead import (
    confidentiality_footer,
    regulatory_citation_block,
    wcab_caption,
)
from claims_generator.documents.pdf_primitives import (
    CONTENT_WIDTH,
    label_value_table,
    para,
    spacer,
    thick_hline,
)
from claims_generator.documents.registry import register_document
from claims_generator.models.claim import DocumentEvent
from claims_generator.models.enums import DocumentType
from claims_generator.models.profile import ClaimProfile

col_h = CONTENT_WIDTH / 2
col_t = CONTENT_WIDTH / 3
col_q = CONTENT_WIDTH / 4


@register_document
class DWCOfficialFormGenerator(DocumentGenerator):
    """Tier A — DWC official forms (Form 105 QME Panel, DEU Rating)."""

    handles = frozenset({DocumentType.DWC_OFFICIAL_FORM})

    @classmethod
    def generate(cls, event: DocumentEvent, profile: ClaimProfile) -> bytes:
        slug = event.subtype_slug
        if "deu" in slug or "rating" in slug:
            return cls._generate_deu_rating(event, profile)
        return cls._generate_form_105(event, profile)

    @classmethod
    def _generate_form_105(cls, event: DocumentEvent, profile: ClaimProfile) -> bytes:
        """DWC Form 105 — Request for Qualified Medical Evaluator Panel."""
        buf = io.BytesIO()
        doc = cls._build_doc(buf, title="DWC Form 105 — QME Panel Request")

        c = profile.claimant
        med = profile.medical
        ins = profile.insurer
        employer = profile.employer

        specialty = med.treating_physician.specialty
        body_parts_str = ", ".join(bp.body_part for bp in med.body_parts)

        story: list = []
        story.append(para("<b>STATE OF CALIFORNIA — DEPARTMENT OF INDUSTRIAL RELATIONS</b>", "subtitle"))  # noqa: E501
        story.append(para("<b>DIVISION OF WORKERS' COMPENSATION — MEDICAL UNIT</b>", "subtitle"))
        story.append(para("<b>DWC FORM 105 — REQUEST FOR QUALIFIED MEDICAL EVALUATOR (QME) PANEL</b>", "title"))  # noqa: E501
        story.append(para("8 CCR 31.1 | LC § 4062.2", "small"))
        story.append(thick_hline())
        story.extend(wcab_caption(profile))
        story.append(spacer(4))

        story.append(form_section_header("SECTION 1 — FILING PARTY INFORMATION"))
        story.append(form_row([
            ("Requesting Party:", "Defendant / Insurer", col_h),
            ("Date of Request:", str(event.event_date), col_h),
        ]))
        story.append(spacer(1))
        story.append(form_row([
            ("Carrier:", ins.carrier_name, col_h),
            ("Claim No.:", ins.claim_number, col_h),
        ]))
        story.append(spacer(2))

        story.append(form_section_header("SECTION 2 — CLAIMANT INFORMATION"))
        story.append(form_row([
            ("Employee Name:", f"{c.first_name} {c.last_name}", col_h),
            ("DOB:", str(c.date_of_birth), col_q),
            ("Gender:", c.gender, col_q),
        ]))
        story.append(spacer(1))
        story.append(form_row([
            ("Employer:", employer.company_name, col_h),
            ("Date of Injury (DOI):", med.date_of_injury, col_h),
        ]))
        story.append(spacer(2))

        story.append(form_section_header("SECTION 3 — PANEL REQUEST INFORMATION"))
        story.append(form_row([
            ("Specialty Requested:", specialty, col_h),
            ("Body Parts:", body_parts_str, col_h),
        ]))
        story.append(spacer(1))
        story.append(para("Reason for QME Panel Request:", "heading2"))
        story.append(form_row([
            ("Dispute Type:", "Medical-legal evaluation — AOE/COE / PD / Apportionment", CONTENT_WIDTH),  # noqa: E501
        ]))
        story.append(spacer(1))
        story.append(para("Is applicant represented by an attorney?", "body"))
        story.append(checkbox_field("Yes — Unrepresented applicant — random QME panel (LC § 4062.1)", False))  # noqa: E501
        story.append(checkbox_field("No — Attorney-represented — strike panel (LC § 4062.2)", True))
        story.append(spacer(2))

        story.append(form_section_header("SECTION 4 — PANEL ISSUANCE (Medical Unit use only)"))
        story.append(form_row([
            ("Panel No.:", "PENDING", col_t),
            ("Specialty Issued:", specialty, col_t),
            ("Date Issued:", "Pending", col_t),
        ]))
        story.append(spacer(1))
        story.append(para(
            "Panelists will be issued by the DWC Medical Unit. Each party has 10 days "
            "to object and strike one QME from the panel per 8 CCR 31.3. Selection of "
            "the QME must be completed within 10 days of the objection period.",
            "small",
        ))

        story.extend(
            regulatory_citation_block([
                "8 CCR 31.1", "8 CCR 31.3", "LC §§ 4062.1, 4062.2"
            ])
        )
        story.extend(confidentiality_footer())
        doc.build(story)
        return buf.getvalue()

    @classmethod
    def _generate_deu_rating(cls, event: DocumentEvent, profile: ClaimProfile) -> bytes:
        """DEU Formal Rating — Permanent Disability rating summary."""
        buf = io.BytesIO()
        doc = cls._build_doc(buf, title="DEU Formal Rating — Permanent Disability")

        c = profile.claimant
        med = profile.medical
        ins = profile.insurer
        fin = profile.financial

        wpi = fin.estimated_pd_percent or med.wpi_percent or 10.0
        pd_pct = wpi
        pd_weeks = fin.estimated_pd_weeks or (wpi * 4.0)
        pd_rate = fin.td_weekly_rate * 0.60
        pd_value = pd_weeks * pd_rate

        story: list = []
        story.append(para("<b>STATE OF CALIFORNIA — DEPARTMENT OF INDUSTRIAL RELATIONS</b>", "subtitle"))  # noqa: E501
        story.append(para("<b>DISABILITY EVALUATION UNIT (DEU) — FORMAL RATING</b>", "title"))
        story.append(para("8 CCR 10160 | LC § 4660 | AMA Guides 5th Edition", "small"))
        story.append(thick_hline())
        story.extend(wcab_caption(profile))
        story.append(spacer(4))

        story.append(form_section_header("SECTION 1 — CLAIM IDENTIFICATION"))
        story.append(form_row([
            ("Claimant:", f"{c.first_name} {c.last_name}", col_h),
            ("Claim No.:", ins.claim_number, col_h),
        ]))
        story.append(spacer(1))
        story.append(form_row([
            ("Date of Injury (DOI):", med.date_of_injury, col_t),
            ("Injury Year:", str(fin.injury_year), col_t),
            ("P&S Date:", str(event.event_date), col_t),
        ]))
        story.append(spacer(2))

        story.append(form_section_header("SECTION 2 — WPI AND RATING SUMMARY"))
        story.append(form_row([
            ("WPI Source:", "QME / AME Report", col_h),
            ("WPI Percent:", f"{wpi:.1f}%", col_h),
        ]))
        story.append(spacer(1))
        story.append(form_row([
            ("Rating Formula:", "PDRS 2005 (AMA Guides 5th Ed.)", col_h),
            ("Apportionment:", "None (or per QME report)", col_h),
        ]))
        story.append(spacer(2))

        story.append(form_section_header("SECTION 3 — PD CALCULATION"))
        story.append(
            label_value_table([
                ("WPI (Whole Person Impairment):", f"{wpi:.1f}%"),
                ("Adjusted PD%:", f"{pd_pct:.1f}%"),
                ("PD Weekly Rate (LC § 4658):", f"${pd_rate:,.2f}"),
                ("PD Weeks:", f"{pd_weeks:.1f}"),
                ("Total PD Value:", f"${pd_value:,.2f}"),
                ("Life Pension:", "Yes" if fin.life_pension_eligible else "No — PD% below threshold"),  # noqa: E501
            ])
        )
        story.append(spacer(4))
        story.append(
            para(
                "This formal rating is issued by the Disability Evaluation Unit (DEU) pursuant "
                "to 8 CCR 10160 and is based on the medical-legal report(s) on file. The rating "
                "is advisory and subject to WCAB adjudication. Parties may object to this rating "
                "within 20 days of receipt.",
                "small",
            )
        )

        story.extend(
            regulatory_citation_block([
                "8 CCR 10160", "LC § 4660", "LC § 4658", "AMA Guides 5th Ed."
            ])
        )
        story.extend(confidentiality_footer())
        doc.build(story)
        return buf.getvalue()
