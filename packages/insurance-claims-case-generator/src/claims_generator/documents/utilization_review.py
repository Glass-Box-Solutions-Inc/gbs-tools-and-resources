"""
UTILIZATION_REVIEW document generator — Tier B structured layout.

Covers: RFA (Request for Authorization), UR decision (approval/modification/denial).
Regulatory basis:
  - 8 CCR 9792.6: UR process and timeframes
  - 8 CCR 9792.6.1: MTUS drug formulary
  - LC § 4610: UR program requirements
  - LC § 4610.5: Independent Medical Review (IMR)
  - LC § 4600: Authorized medical treatment

UR timeframes:
  - Prospective/concurrent: 5 working days (2 days for urgent/expedited)
  - Retrospective: 30 days

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
class UtilizationReviewGenerator(DocumentGenerator):
    """Tier B — Utilization Review documents (RFA, UR decision)."""

    handles = frozenset({DocumentType.UTILIZATION_REVIEW})

    @classmethod
    def generate(cls, event: DocumentEvent, profile: ClaimProfile) -> bytes:
        buf = io.BytesIO()
        doc = cls._build_doc(buf, title=event.title)

        ins = profile.insurer
        med = profile.medical
        claimant = profile.claimant
        treating = med.treating_physician

        slug = event.subtype_slug
        is_rfa = "rfa" in slug

        story: list = []
        story.extend(carrier_header_block(profile, form_id="RFA / DWC Form RFA"))
        story.append(spacer(4))

        if is_rfa:
            story.append(para("REQUEST FOR AUTHORIZATION (RFA)", "title"))
            story.append(para("DWC Form RFA | 8 CCR 9792.6 | LC § 4610", "small"))
        else:
            story.append(para("UTILIZATION REVIEW DECISION", "title"))
            story.append(para("8 CCR 9792.6 | LC §§ 4610, 4610.5", "small"))

        story.append(thick_hline())
        story.extend(
            claimant_caption_block(
                profile,
                event_date=event.event_date,
                event_title=event.title,
            )
        )

        if is_rfa:
            # Request for Authorization
            story.append(para("REQUESTING PHYSICIAN INFORMATION", "heading1"))
            story.append(hline())
            story.append(
                label_value_table([
                    ("Treating Physician:", f"Dr. {treating.first_name} {treating.last_name}"),
                    ("Specialty:", treating.specialty),
                    ("NPI:", treating.npi),
                    ("License No.:", treating.license_number),
                    ("Date of RFA:", str(event.event_date)),
                    ("Claim No.:", ins.claim_number),
                    ("Type:", "Prospective"),
                ])
            )

            story.append(spacer(6))
            story.append(para("TREATMENT REQUESTED", "heading1"))
            story.append(hline())

            # Determine treatment based on body parts
            primary_bp = med.body_parts[0].body_part if med.body_parts else "affected area"
            if med.has_surgery and med.surgery_description:
                treatment_requested = med.surgery_description
                treatment_type = "Surgical — Prior Authorization Required"
                cpt_codes = "CPT 63030 (Lumbar Discectomy)" if "spine" in primary_bp.lower() else "CPT to be determined"
            else:
                treatment_requested = (
                    f"Physical therapy 2x per week x 8 weeks for {primary_bp} "
                    f"per MTUS Chronic Pain guidelines (8 CCR 9792.6)"
                )
                treatment_type = "Physical Medicine / Rehabilitation"
                cpt_codes = "CPT 97110 (Therapeutic Exercise), CPT 97014 (Electrical Stimulation)"

            story.append(
                label_value_table([
                    ("Treatment Requested:", treatment_requested),
                    ("Treatment Type:", treatment_type),
                    ("CPT Codes:", cpt_codes),
                    ("ICD-10 Diagnosis:", (
                        med.icd10_codes[0].code + " — " + med.icd10_codes[0].description
                        if med.icd10_codes else "Per attached records"
                    )),
                    ("Clinical Basis:", "Per attached PR-2 and medical records"),
                    ("MTUS Guideline:", "8 CCR 9792.6 — applicable chapter"),
                    ("Urgency:", "Non-urgent"),
                ])
            )
            story.append(spacer(6))
            story.append(
                para(
                    "Pursuant to 8 CCR 9792.6, the claims administrator must issue a UR "
                    "decision within 5 working days of receipt of this RFA (2 working days if "
                    "urgent). Failure to timely respond results in deemed approval under LC § 4610.",
                    "small",
                )
            )
            story.extend(regulatory_citation_block(["8 CCR 9792.6", "LC §§ 4600, 4610"]))

        else:
            # UR Decision
            story.append(para("UR DECISION DETAILS", "heading1"))
            story.append(hline())
            story.append(
                label_value_table([
                    ("Decision Type:", "APPROVED"),
                    ("Date of Decision:", str(event.event_date)),
                    ("UR Reviewer:", "UR Medical Reviewer (Credentials on file)"),
                    ("UR Organization:", ins.carrier_name + " UR Program"),
                    ("Review Type:", "Prospective"),
                    ("Decision Date:", str(event.event_date)),
                    ("Claim No.:", ins.claim_number),
                ])
            )
            story.append(spacer(6))
            story.append(para("TREATMENT DECISION", "heading1"))
            story.append(hline())
            story.append(
                para(
                    "APPROVED: The requested treatment has been approved as consistent with "
                    "the MTUS guidelines (8 CCR 9792.6) and medically necessary for the "
                    "treatment of the industrial injury.\n\n"
                    "MODIFIED / DENIED PORTIONS: None at this time.\n\n"
                    "IMR RIGHTS: If any portion of treatment is denied or modified, "
                    "Applicant has the right to request Independent Medical Review (IMR) "
                    "within 30 days of receipt of this UR decision (LC § 4610.5). "
                    "IMR request forms are available at www.dir.ca.gov/dwc.",
                    "body",
                )
            )
            story.extend(
                regulatory_citation_block([
                    "8 CCR 9792.6", "LC §§ 4610, 4610.5", "MTUS"
                ])
            )

        story.extend(confidentiality_footer())
        doc.build(story)
        return buf.getvalue()
