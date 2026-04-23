"""
DWC1_CLAIM_FORM document generator — Tier A form-accurate approximation.

Form: DWC-1 (Workers' Compensation Claim Form)
Required by: LC § 5401 — employer must provide DWC-1 within 1 working day
             of knowledge of the injury.
Note: PNG blank form not available in assets/; using table approximation
      per Phase 2 plan. See ISSUES.md for PNG blank backlog item.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import io

from reportlab.lib.units import inch

from claims_generator.documents.base_document import DocumentGenerator
from claims_generator.documents.form_renderer import (
    checkbox_field,
    form_row,
    form_section_header,
)
from claims_generator.documents.letterhead import (
    confidentiality_footer,
    regulatory_citation_block,
)
from claims_generator.documents.pdf_primitives import (
    CONTENT_WIDTH,
    para,
    spacer,
    thick_hline,
)
from claims_generator.documents.registry import register_document
from claims_generator.models.claim import DocumentEvent
from claims_generator.models.enums import DocumentType
from claims_generator.models.profile import ClaimProfile


@register_document
class DWC1ClaimFormGenerator(DocumentGenerator):
    """Tier A — DWC-1 Workers' Compensation Claim Form (table approximation)."""

    handles = frozenset({DocumentType.DWC1_CLAIM_FORM})

    @classmethod
    def generate(cls, event: DocumentEvent, profile: ClaimProfile) -> bytes:
        buf = io.BytesIO()
        doc = cls._build_doc(buf, title="DWC-1 Workers' Compensation Claim Form")

        c = profile.claimant
        med = profile.medical
        employer = profile.employer
        ins = profile.insurer

        body_parts_str = ", ".join(
            f"{bp.body_part}{' (' + bp.laterality + ')' if bp.laterality else ''}"
            for bp in med.body_parts
        )

        col_half = CONTENT_WIDTH / 2
        col_third = CONTENT_WIDTH / 3
        col_two_thirds = CONTENT_WIDTH * 2 / 3

        story: list = []

        # Form header
        story.append(para("<b>STATE OF CALIFORNIA</b>", "subtitle"))
        story.append(para("<b>WORKERS' COMPENSATION CLAIM FORM (DWC 1)</b>", "title"))
        story.append(para(
            "Labor Code § 5401 | Give this form to your employer — keep a copy for your records. "
            "This form also serves as your claim for workers' compensation benefits.",
            "small",
        ))
        story.append(spacer(4))
        story.append(thick_hline())

        # EMPLOYEE SECTION
        story.append(spacer(4))
        story.append(form_section_header("SECTION 1 — EMPLOYEE: Fill out this section and give the form to your employer"))
        story.append(spacer(2))

        story.append(form_row([
            ("1. Name of injured employee:", f"{c.first_name} {c.last_name}", col_two_thirds),
            ("2. Social Security No. (last 4):", c.ssn_last4, col_third),
        ]))
        story.append(spacer(1))
        story.append(form_row([
            ("3. Date of injury / illness (DOI):", med.date_of_injury, col_half),
            ("4. Time of injury:", "During work hours", col_half),
        ]))
        story.append(spacer(1))
        story.append(form_row([
            ("5. Address:", f"{c.address_city}, {c.address_county} County, CA {c.address_zip}", CONTENT_WIDTH),
        ]))
        story.append(spacer(1))
        story.append(form_row([
            ("6. Date of birth:", str(c.date_of_birth), col_third),
            ("7. Sex:", c.gender, col_third * 0.7),
            ("8. Occupation:", c.occupation_title, CONTENT_WIDTH - col_third - col_third * 0.7),
        ]))
        story.append(spacer(1))
        story.append(form_row([
            ("9. Describe the injury/illness and the part of the body affected:", body_parts_str, CONTENT_WIDTH),
        ]))
        story.append(spacer(1))
        story.append(form_row([
            ("10. How did the injury/illness occur?", med.injury_mechanism, CONTENT_WIDTH),
        ]))
        story.append(spacer(1))
        story.append(form_row([
            ("11. Describe the specific activity you were performing when injured:", c.occupation_title + " — regular work duties", CONTENT_WIDTH),
        ]))
        story.append(spacer(1))
        story.append(form_row([
            ("12. Where did the accident or exposure occur?", f"{employer.address_city}, CA — employer's premises", CONTENT_WIDTH),
        ]))
        story.append(spacer(2))
        story.append(para("13. <b>Signature of employee:</b> ______________________________   <b>Date:</b> " + str(event.event_date), "body"))

        story.append(spacer(8))

        # EMPLOYER SECTION
        story.append(form_section_header("SECTION 2 — EMPLOYER: Complete and return this form within 1 working day (LC § 5401)"))
        story.append(spacer(2))

        story.append(form_row([
            ("14. Employer name:", employer.company_name, col_two_thirds),
            ("15. Policy No.:", ins.policy_number, col_third),
        ]))
        story.append(spacer(1))
        story.append(form_row([
            ("16. Date employer learned of injury:", med.date_of_injury, col_half),
            ("17. Date form given to employee:", str(event.event_date), col_half),
        ]))
        story.append(spacer(1))
        story.append(form_row([
            ("18. Insurance carrier:", ins.carrier_name, col_half),
            ("19. Claim No.:", ins.claim_number, col_half),
        ]))
        story.append(spacer(1))
        story.append(form_row([
            ("20. Has employee returned to work?",
             checkbox_field("Yes", False).text + "  " + checkbox_field("No", True).text,
             col_half),
            ("21. If yes, date:", "N/A", col_half),
        ]))
        story.append(spacer(2))
        story.append(para("22. <b>Signature of employer representative:</b> ______________________________   <b>Date:</b> " + str(event.event_date), "body"))

        # Tear line and employee copy
        story.append(spacer(6))
        story.append(thick_hline())
        story.append(para("<b>EMPLOYEE — TEAR HERE AND KEEP THIS SECTION</b>", "subtitle"))
        story.append(para(
            f"You filed a Workers' Compensation claim. "
            f"Employer: {employer.company_name} | "
            f"Carrier: {ins.carrier_name} | "
            f"Claim No.: {ins.claim_number} | "
            f"If claim is not decided within 90 days, it is presumed compensable (LC § 5402).",
            "small",
        ))

        story.extend(regulatory_citation_block(["LC § 5401", "LC § 5402", "8 CCR 10133.54"]))
        story.extend(confidentiality_footer())
        doc.build(story)
        return buf.getvalue()
