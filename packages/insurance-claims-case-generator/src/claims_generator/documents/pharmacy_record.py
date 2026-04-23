"""
PHARMACY_RECORD document generator — Tier C plain letterhead.

Covers: pharmacy dispensing records, pharmaceutical benefit summaries.
Regulatory basis:
  - LC § 4600: Employer's duty to provide medical treatment
  - 8 CCR 9792.6: MTUS drug formulary compliance
  - 8 CCR 9789.70: OMFS pharmaceutical fee schedule

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import io
import random

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
)
from claims_generator.documents.registry import register_document
from claims_generator.models.claim import DocumentEvent
from claims_generator.models.enums import DocumentType
from claims_generator.models.profile import ClaimProfile

# Common WC pharmaceutical entries keyed by injury type
_WC_MEDICATIONS: dict[str, list[dict[str, str]]] = {
    "musculoskeletal": [
        {"ndc": "00093-0058-01", "drug": "Ibuprofen 800mg", "qty": "30", "days": "30",
         "formulary": "Preferred", "cost": "$18.50"},
        {"ndc": "00591-0451-05", "drug": "Cyclobenzaprine 10mg", "qty": "20", "days": "10",
         "formulary": "Preferred", "cost": "$12.00"},
        {"ndc": "00143-9628-01", "drug": "Naproxen 500mg", "qty": "60", "days": "30",
         "formulary": "Preferred", "cost": "$22.75"},
    ],
    "neurological": [
        {"ndc": "00093-8194-01", "drug": "Gabapentin 300mg", "qty": "90", "days": "30",
         "formulary": "Preferred", "cost": "$45.00"},
        {"ndc": "00228-3070-11", "drug": "Amitriptyline 25mg", "qty": "30", "days": "30",
         "formulary": "Non-Formulary — PA Required", "cost": "$28.00"},
    ],
    "pain": [
        {"ndc": "00406-0512-01", "drug": "Tramadol 50mg", "qty": "60", "days": "15",
         "formulary": "Non-Formulary — UR Required (8 CCR 9792.6)", "cost": "$35.00"},
    ],
}

_DEFAULT_MEDICATIONS = _WC_MEDICATIONS["musculoskeletal"]


@register_document
class PharmacyRecordGenerator(DocumentGenerator):
    """Tier C — pharmacy dispensing records."""

    handles = frozenset({DocumentType.PHARMACY_RECORD})

    @classmethod
    def generate(cls, event: DocumentEvent, profile: ClaimProfile) -> bytes:
        buf = io.BytesIO()
        doc = cls._build_doc(buf, title=event.title)

        ins = profile.insurer
        med = profile.medical
        claimant = profile.claimant

        # Select medications based on injury mechanism
        mechanism = med.injury_mechanism.lower()
        if any(k in mechanism for k in ("back", "spine", "shoulder", "knee", "wrist")):
            meds = _WC_MEDICATIONS["musculoskeletal"]
        elif any(k in mechanism for k in ("nerve", "carpal", "repetitive")):
            meds = _WC_MEDICATIONS["neurological"]
        else:
            meds = _DEFAULT_MEDICATIONS

        # Use seed from event_id for deterministic selection
        seed_val = int(event.event_id.replace("-", "")[:8], 16) if event.event_id else 42
        rng = random.Random(seed_val)
        selected = rng.sample(meds, min(len(meds), 2))

        story: list = []
        story.extend(carrier_header_block(profile))
        story.append(spacer(4))
        story.append(para("PHARMACY DISPENSING RECORD", "title"))
        story.append(para(f"Date: {event.event_date} | OMFS Pharmaceutical Schedule (8 CCR 9789.70)", "small"))
        story.append(thick_hline())

        story.extend(
            claimant_caption_block(
                profile,
                event_date=event.event_date,
                event_title=event.title,
            )
        )

        story.append(para("CLAIM AND PROVIDER INFORMATION", "heading1"))
        story.append(hline())
        story.append(
            label_value_table([
                ("Claimant:", f"{claimant.first_name} {claimant.last_name}"),
                ("Claim No.:", ins.claim_number),
                ("Carrier:", ins.carrier_name),
                ("Prescribing Physician:", (
                    f"Dr. {med.treating_physician.last_name}, "
                    f"{med.treating_physician.specialty}"
                )),
                ("NPI:", med.treating_physician.npi),
                ("Date of Injury (DOI):", med.date_of_injury),
                ("Formulary:", "MTUS Drug Formulary (8 CCR 9792.6.1)"),
            ])
        )

        story.append(spacer(8))
        story.append(para("DISPENSED MEDICATIONS", "heading1"))
        story.append(hline())
        story.append(
            section_table(
                headers=["NDC", "Drug / Strength", "Qty", "Days Supply", "Formulary Status", "Cost"],
                rows=[
                    [m["ndc"], m["drug"], m["qty"], m["days"], m["formulary"], m["cost"]]
                    for m in selected
                ],
            )
        )

        total_cost = sum(
            float(m["cost"].replace("$", "")) for m in selected
        )
        story.append(spacer(4))
        story.append(para(f"<b>Total Pharmaceutical Charges: ${total_cost:,.2f}</b>", "body_bold"))

        story.append(spacer(6))
        story.append(
            para(
                "Non-formulary medications require prior authorization per 8 CCR 9792.6. "
                "Formulary preferred medications are dispensed as authorized under the MTUS "
                "Drug Formulary effective January 2024. Disputes over pharmaceutical benefits "
                "are subject to Independent Medical Review (IMR) under LC § 4610.5.",
                "small",
            )
        )

        story.extend(
            regulatory_citation_block([
                "LC § 4600", "8 CCR 9792.6", "8 CCR 9789.70", "MTUS Drug Formulary"
            ])
        )
        story.extend(confidentiality_footer())
        doc.build(story)
        return buf.getvalue()
