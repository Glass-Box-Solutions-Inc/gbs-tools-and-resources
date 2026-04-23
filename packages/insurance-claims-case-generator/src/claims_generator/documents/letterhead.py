"""
Letterhead — WCAB captions, CA Workers' Compensation header/footer, confidentiality notices.

Provides consistent document-level framing for all Tier A/B/C generators.
Headers include form identifiers, regulatory citations, and CA WC acronyms
per the Glass Box realism standard.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

from datetime import date
from typing import Any

from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import (
    Flowable,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from claims_generator.documents.pdf_primitives import (
    COLOR_CA_BLUE,
    COLOR_HEADER_BG,
    COLOR_MED_GRAY,
    COLOR_WHITE,
    CONTENT_WIDTH,
    STYLES,
    hline,
    para,
    spacer,
    thick_hline,
)
from claims_generator.models.claim import DocumentEvent
from claims_generator.models.profile import ClaimProfile


# ── Carrier header block ───────────────────────────────────────────────────────


def carrier_header_block(profile: ClaimProfile, form_id: str = "") -> list[Flowable]:
    """
    Top-of-page carrier/insurer identification block with optional form identifier.

    Args:
        profile: ClaimProfile containing insurer and employer data.
        form_id: Optional form identifier, e.g. "PR-2", "AD 10133.53".
    """
    insurer = profile.insurer
    employer = profile.employer

    header_data = [
        [
            Paragraph(
                f"<b>{insurer.carrier_name}</b><br/>"
                f"Workers' Compensation Division<br/>"
                f"Claim No.: <b>{insurer.claim_number}</b><br/>"
                f"Policy No.: {insurer.policy_number}",
                STYLES["body"],
            ),
            Paragraph(
                f"<b>STATE OF CALIFORNIA</b><br/>"
                f"Department of Industrial Relations<br/>"
                f"Division of Workers' Compensation<br/>"
                f"{'<b>Form: ' + form_id + '</b>' if form_id else ''}",
                STYLES["body"],
            ),
        ]
    ]
    t = Table(header_data, colWidths=[CONTENT_WIDTH / 2, CONTENT_WIDTH / 2])
    t.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), COLOR_HEADER_BG),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("BOX", (0, 0), (-1, -1), 1, COLOR_CA_BLUE),
            ("LINEAFTER", (0, 0), (0, -1), 0.5, COLOR_MED_GRAY),
        ])
    )

    employer_line = (
        f"Employer: {employer.company_name} | Industry: {employer.industry} | "
        f"Adjuster: {insurer.adjuster_name} | Phone: {insurer.adjuster_phone}"
    )

    return [
        t,
        spacer(4),
        para(employer_line, "small"),
        spacer(2),
    ]


def claimant_caption_block(
    profile: ClaimProfile,
    event_date: date,
    event_title: str,
) -> list[Flowable]:
    """
    Claimant identification / WCAB caption block.

    Includes claimant name, DOB, employer, DOI, body parts, ICD-10 codes,
    and claim identifiers formatted per WCAB caption conventions.

    Args:
        profile: ClaimProfile containing all party data.
        event_date: Date of this document event.
        event_title: Document title shown in the caption.
    """
    claimant = profile.claimant
    medical = profile.medical
    insurer = profile.insurer

    doi = medical.date_of_injury
    body_parts_str = ", ".join(
        f"{bp.body_part}{' (' + bp.laterality + ')' if bp.laterality else ''}"
        for bp in medical.body_parts
    )
    icd_str = ", ".join(f"{e.code} ({e.description})" for e in medical.icd10_codes[:3])

    rows = [
        ["APPLICANT:", f"{claimant.last_name}, {claimant.first_name}"],
        ["DATE OF BIRTH:", str(claimant.date_of_birth)],
        ["OCCUPATION:", claimant.occupation_title or "N/A"],
        ["DEFENDANT/EMPLOYER:", profile.employer.company_name],
        ["INSURANCE CARRIER:", insurer.carrier_name],
        ["CLAIM NUMBER:", insurer.claim_number],
        ["DATE OF INJURY (DOI):", doi],
        ["BODY PARTS CLAIMED:", body_parts_str],
        ["DIAGNOSIS (ICD-10):", icd_str],
        ["DOCUMENT DATE:", str(event_date)],
    ]

    data = [
        [
            Paragraph(label, STYLES["label"]),
            Paragraph(value, STYLES["value"]),
        ]
        for label, value in rows
    ]
    t = Table(data, colWidths=[1.6 * inch, CONTENT_WIDTH - 1.6 * inch])
    t.setStyle(
        TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("LINEBELOW", (0, 0), (-1, -2), 0.25, COLOR_MED_GRAY),
        ])
    )

    return [
        para(event_title, "subtitle"),
        spacer(4),
        t,
        spacer(6),
        thick_hline(),
    ]


def wcab_caption(
    profile: ClaimProfile,
    case_number: str = "",
    wcab_venue: str = "Los Angeles",
) -> list[Flowable]:
    """
    Formal WCAB case caption for filings and legal documents.

    Args:
        profile: ClaimProfile.
        case_number: ADJ case number if available.
        wcab_venue: WCAB district office venue.
    """
    claimant = profile.claimant
    employer = profile.employer
    insurer = profile.insurer

    caption_text = (
        f"WORKERS' COMPENSATION APPEALS BOARD<br/>"
        f"STATE OF CALIFORNIA — {wcab_venue.upper()} DISTRICT OFFICE<br/><br/>"
        f"{claimant.last_name.upper()}, {claimant.first_name.upper()}, "
        f"<i>Applicant,</i><br/>"
        f"vs.<br/>"
        f"{employer.company_name.upper()}; {insurer.carrier_name.upper()}, "
        f"<i>Defendants.</i>"
    )
    if case_number:
        caption_text += f"<br/><br/>ADJ No.: <b>{case_number}</b>"

    return [
        para(caption_text, "subtitle"),
        spacer(4),
        hline(),
    ]


def confidentiality_footer() -> list[Flowable]:
    """
    HIPAA / CA WC confidentiality notice footer.
    Added at the bottom of medical and legal documents.
    """
    text = (
        "CONFIDENTIALITY NOTICE: This document contains information that is privileged, "
        "confidential, and exempt from disclosure under the California Workers' Compensation "
        "laws (LC § 3762) and applicable HIPAA regulations (45 CFR Parts 160 and 164). "
        "Unauthorized review, use, disclosure, or distribution is prohibited."
    )
    return [spacer(8), hline(), para(text, "disclaimer")]


def regulatory_citation_block(citations: list[str]) -> list[Flowable]:
    """
    Regulatory citation block appended to documents that carry statutory deadlines.

    Args:
        citations: List of citation strings, e.g. ["LC 4650", "8 CCR 9792.6"].
    """
    if not citations:
        return []
    text = "<b>Regulatory Authority:</b> " + " | ".join(citations)
    return [spacer(4), para(text, "small")]
