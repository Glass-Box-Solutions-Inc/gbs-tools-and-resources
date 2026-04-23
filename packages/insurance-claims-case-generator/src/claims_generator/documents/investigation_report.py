"""
INVESTIGATION_REPORT document generator — Tier B structured layout.

Covers: denial basis investigations, surveillance summaries, fraud referral reports.
Regulatory basis:
  - 10 CCR 2695.7(b): Denial within 90 days
  - LC § 1871.4: Workers' compensation fraud
  - IC § 1871.8: Fraud reporting to WCIS
  - 8 CCR 15401: SIU program requirements

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


@register_document
class InvestigationReportGenerator(DocumentGenerator):
    """Tier B — claims investigation reports."""

    handles = frozenset({DocumentType.INVESTIGATION_REPORT})

    @classmethod
    def generate(cls, event: DocumentEvent, profile: ClaimProfile) -> bytes:
        buf = io.BytesIO()
        doc = cls._build_doc(buf, title=event.title)

        ins = profile.insurer
        med = profile.medical
        claimant = profile.claimant
        employer = profile.employer

        story: list = []
        story.extend(carrier_header_block(profile))
        story.append(spacer(4))
        story.append(para("CLAIMS INVESTIGATION REPORT", "title"))
        story.append(para(f"CONFIDENTIAL — WORK PRODUCT | {ins.carrier_name} SIU / Claims", "small"))  # noqa: E501
        story.append(thick_hline())

        story.extend(
            claimant_caption_block(
                profile,
                event_date=event.event_date,
                event_title=event.title,
            )
        )

        story.append(para("INVESTIGATION SUMMARY", "heading1"))
        story.append(hline())
        story.append(
            label_value_table([
                ("Investigator:", ins.adjuster_name),
                ("Investigation Date:", str(event.event_date)),
                ("Claim No.:", ins.claim_number),
                ("Carrier:", ins.carrier_name),
                ("Claimant:", f"{claimant.first_name} {claimant.last_name}"),
                ("Employer:", employer.company_name),
                ("Date of Injury (DOI):", med.date_of_injury),
                ("Mechanism of Injury:", med.injury_mechanism),
                ("Report Type:", event.subtype_slug.replace("_", " ").title()),
            ])
        )

        story.append(spacer(6))
        story.append(para("INVESTIGATION FINDINGS", "heading1"))
        story.append(hline())

        slug = event.subtype_slug

        if "denial" in slug:
            story.append(
                para(
                    "The following findings support a denial of the claimed workers' "
                    "compensation injury pursuant to 10 CCR 2695.7(b):\n\n"
                    "1. AOE/COE ISSUE: Witness statements obtained from co-workers indicate "
                    "the reported mechanism of injury is inconsistent with the claimant's "
                    "job duties on the date of injury. No corroborating witnesses have been "
                    "identified.\n\n"
                    "2. MEDICAL EVIDENCE: The treating physician's initial report does not "
                    "establish a clear causal relationship between the claimed injury and "
                    "the industrial work activities.\n\n"
                    "3. PRIOR MEDICAL HISTORY: Records review indicates a pre-existing condition "
                    "to the claimed body part predating the reported DOI. Apportionment under "
                    "LC § 4663 may apply.\n\n"
                    "RECOMMENDATION: Deny claim per 10 CCR 2695.7(b). Issue formal Notice of "
                    "Denial within statutory timeframe.",
                    "body",
                )
            )
            story.extend(
                regulatory_citation_block([
                    "10 CCR 2695.7(b)", "LC § 3600", "LC § 4663"
                ])
            )
        else:
            story.append(
                para(
                    "Investigation conducted pursuant to the carrier's Standard Investigation "
                    "Unit (SIU) program (8 CCR 15401). The following steps were completed:\n\n"
                    "1. Claimant interview completed per 10 CCR 2695.5(b).\n"
                    "2. Employment records and payroll reviewed.\n"
                    "3. Medical records obtained and reviewed.\n"
                    "4. Treating physician contacted for additional information.\n"
                    "5. Employer injury report (DLSR 5020) reviewed.\n\n"
                    "FINDINGS: No evidence of fraudulent misrepresentation identified at this "
                    "time. Claim investigation continues. File will be updated as additional "
                    "information is received.",
                    "body",
                )
            )
            story.extend(
                regulatory_citation_block([
                    "10 CCR 2695.5(b)", "8 CCR 15401", "LC § 1871.4"
                ])
            )

        story.append(spacer(6))
        story.append(para("NEXT STEPS", "heading1"))
        story.append(hline())
        story.append(
            label_value_table([
                ("Action Items:", "1. Request additional medical records"),
                ("", "2. Complete witness statements"),
                ("", "3. Review employer surveillance (if applicable)"),
                ("Target Resolution:", "Per 10 CCR 2695.7(b) statutory timeframe"),
                ("Adjuster:", ins.adjuster_name),
                ("Contact:", ins.adjuster_email),
            ])
        )

        story.extend(confidentiality_footer())
        doc.build(story)
        return buf.getvalue()
