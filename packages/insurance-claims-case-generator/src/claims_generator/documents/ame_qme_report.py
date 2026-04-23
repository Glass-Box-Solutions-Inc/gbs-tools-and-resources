"""
AME_QME_REPORT document generator — Tier B structured layout.

Covers: QME initial report, psychiatric QME, AME report.
Form identifiers: QME panel reports per 8 CCR Chapter 2 (DWC Medical Unit).
Regulatory basis:
  - LC §§ 4060–4062: Medical-legal evaluation procedures
  - 8 CCR 35: QME reporting requirements
  - AMA Guides 5th Edition: WPI rating methodology
  - 8 CCR 46: AME agreement procedures

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
    two_col_section,
)
from claims_generator.documents.registry import register_document
from claims_generator.models.claim import DocumentEvent
from claims_generator.models.enums import DocumentType
from claims_generator.models.profile import ClaimProfile


@register_document
class AmeQmeReportGenerator(DocumentGenerator):
    """Tier B — QME and AME medical-legal evaluation reports."""

    handles = frozenset({DocumentType.AME_QME_REPORT})

    @classmethod
    def generate(cls, event: DocumentEvent, profile: ClaimProfile) -> bytes:
        buf = io.BytesIO()
        doc = cls._build_doc(buf, title=event.title)

        med = profile.medical

        slug = event.subtype_slug
        is_psych = "psych" in slug or "psychiatric" in slug
        is_ame = "ame" in slug

        # Determine evaluating physician
        if is_ame and med.ame_physician:
            physician = med.ame_physician
            eval_type = "AME"
            form_label = "Agreed Medical Evaluator (AME) Report"
        elif med.qme_physician:
            physician = med.qme_physician
            eval_type = "QME"
            form_label = (
                "Psychiatric QME Report" if is_psych
                else "Qualified Medical Evaluator (QME) Report"
            )
        else:
            physician = med.treating_physician
            eval_type = "QME"
            form_label = "Medical-Legal Evaluation Report"

        wpi = f"{med.wpi_percent:.1f}%" if med.wpi_percent else "To be determined"

        story: list = []
        story.extend(carrier_header_block(profile, form_id=f"{eval_type} Report"))
        story.append(spacer(4))
        story.append(para(form_label.upper(), "title"))
        story.append(para(
            f"State of California — Division of Workers' Compensation | "
            f"{'Psychiatric' if is_psych else physician.specialty} Evaluation",
            "subtitle",
        ))
        story.append(thick_hline())

        story.extend(
            claimant_caption_block(
                profile,
                event_date=event.event_date,
                event_title=event.title,
            )
        )

        # Evaluator info
        story.append(para(f"SECTION 1: {eval_type} EVALUATOR INFORMATION", "heading1"))
        story.append(hline())
        story.append(
            two_col_section(
                left_items=[
                    ("Evaluator", f"Dr. {physician.first_name} {physician.last_name}"),
                    ("Specialty", "Psychiatry/Psychology" if is_psych else physician.specialty),
                    ("License No.", physician.license_number),
                ],
                right_items=[
                    ("NPI", physician.npi),
                    ("Evaluation Date", str(event.event_date)),
                    ("Evaluation City", physician.address_city),
                ],
            )
        )

        # History
        story.append(spacer(6))
        story.append(para("SECTION 2: HISTORY AND BACKGROUND", "heading1"))
        story.append(hline())
        story.append(
            label_value_table([
                ("Date of Injury (DOI):", med.date_of_injury),
                ("Mechanism of Injury:", med.injury_mechanism),
                ("Disputed Body Parts:", ", ".join(bp.body_part for bp in med.body_parts)),
                ("Prior Medical History:", "Reviewed per available records"),
                ("Prior WC Claims:", "None reported by claimant (records review pending)"),
            ])
        )

        if is_psych:
            story.append(spacer(4))
            story.append(
                label_value_table([
                    ("Psychiatric History:", "Reviewed — claimant denies prior psychiatric Hx"),
                    ("DSM-5 Evaluation:", "Administered GAD-7, PHQ-9, PCL-5"),
                    ("Mental Status Exam:", "Alert and oriented x4; affect appropriate"),
                    ("Symptom Validity Testing:", "Administered — results within normal limits"),
                ])
            )

        # Findings
        story.append(spacer(6))
        story.append(para("SECTION 3: PHYSICAL / PSYCHIATRIC FINDINGS", "heading1"))
        story.append(hline())

        if is_psych:
            story.append(
                para(
                    "PSYCHIATRIC FINDINGS: Claimant reports anxiety, sleep disturbance, "
                    "and depressed mood following the industrial injury. Findings are consistent "
                    "with Adjustment Disorder with Mixed Anxiety and Depressed Mood (F43.23) "
                    "per DSM-5 criteria. Industrial causation: The psychiatric condition is "
                    "industrially caused and aggravated per LC § 3600.",
                    "body",
                )
            )
            diag_rows = [
                ["F43.23", "Adjustment Disorder w/ Mixed Anxiety & Depressed Mood", "Psychiatric"]
            ]
            for e in med.icd10_codes[:2]:
                diag_rows.append([e.code, e.description, e.body_part])
        else:
            body_part_str = med.body_parts[0].body_part if med.body_parts else "reported body part"
            story.append(
                para(
                    f"PHYSICAL FINDINGS: Range of motion testing, orthopedic provocative tests, "
                    f"and neurological examination were performed. Findings are consistent with "
                    f"the claimed industrial injury to the {body_part_str}. "
                    f"No evidence of malingering or symptom magnification was observed.",
                    "body",
                )
            )
            diag_rows = [[e.code, e.description, e.body_part] for e in med.icd10_codes]

        story.append(spacer(4))
        story.append(
            section_table(
                headers=["ICD-10 Code", "Diagnosis", "Body Part"],
                rows=diag_rows,
            )
        )

        # Impairment rating
        story.append(spacer(6))
        story.append(para("SECTION 4: IMPAIRMENT RATING (AMA GUIDES 5TH EDITION)", "heading1"))
        story.append(hline())
        story.append(
            label_value_table([
                ("WPI — Whole Person Impairment:", wpi),
                ("Rating Method:", "AMA Guides to the Evaluation of Permanent Impairment, 5th Ed."),
                (
                    "Chapter Referenced:",
                    "Chapter 15 (Spine)" if not is_psych else "Chapter 14 (Mental & Behavioral)",
                ),
                (
                    "Apportionment (LC § 4663):",
                    "Non-industrial factors: none identified"
                    if not is_psych
                    else "30% non-industrial per prior psychiatric history review",
                ),
                ("MMI Status:", "Permanent and Stationary" if med.mmi_reached else "Not yet P&S"),
            ])
        )

        story.append(spacer(6))
        story.append(para("SECTION 5: RECOMMENDATIONS", "heading1"))
        story.append(hline())
        story.append(
            para(
                "Based on my evaluation, I offer the following recommendations:<br/>"
                "1. Future medical treatment: " +
                ("Psychiatric treatment per MTUS Mental Health guidelines (8 CCR 9792.6)."
                 if is_psych else
                 "Physical therapy per MTUS guidelines for the rated conditions.") +
                "<br/>2. Work restrictions: Permanent work restrictions as noted in the RFC form."
                "<br/>"
                "3. Apportionment: As stated above per LC § 4663.<br/>"
                "4. Further evaluation: None required.",
                "body",
            )
        )

        story.extend(
            regulatory_citation_block([
                "LC §§ 4060–4062, 4663", "8 CCR 35", "AMA Guides 5th Ed.", "LC § 4660"
            ])
        )
        story.extend(confidentiality_footer())
        doc.build(story)
        return buf.getvalue()
