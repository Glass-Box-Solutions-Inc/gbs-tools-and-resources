"""
Email metadata for .eml document generation.

Maps document subtypes to sender/recipient role pairs so generated emails
look like they came from the right participant (adjuster writes to attorney,
attorney writes to client, etc.).

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import re
from datetime import date
from email.utils import formataddr, formatdate
from typing import Any


# ---------------------------------------------------------------------------
# Participant role pairs per document subtype
# Each entry is (sender_role, recipient_role) where roles are keys
# understood by _resolve_participant().
# ---------------------------------------------------------------------------

EMAIL_PARTICIPANT_MAP: dict[str, tuple[str, str]] = {
    # Adjuster → attorney
    "ADJUSTER_LETTER_INFORMATIONAL": ("adjuster", "attorney"),
    "ADJUSTER_LETTER_REQUEST":       ("adjuster", "attorney"),
    "ADJUSTER_LETTER":               ("adjuster", "attorney"),

    # Defense counsel → applicant attorney
    "DEFENSE_COUNSEL_LETTER_INFORMATIONAL": ("defense", "attorney"),
    "DEFENSE_COUNSEL_LETTER_DEMAND":        ("defense", "attorney"),
    "DEFENSE_COUNSEL_LETTER":               ("defense", "attorney"),

    # Attorney → client (applicant)
    "CLIENT_CORRESPONDENCE_INFORMATIONAL": ("attorney", "applicant"),
    "CLIENT_CORRESPONDENCE_REQUEST":       ("attorney", "applicant"),
    "CLIENT_STATUS_LETTERS":               ("attorney", "applicant"),
    "CLIENT_REPORT_ANALYSIS_LETTER":       ("attorney", "applicant"),
    "CLIENT_CASE_VALUATION_LETTER":        ("attorney", "applicant"),
    "CLIENT_SETTLEMENT_RECOMMENDATION":    ("attorney", "applicant"),

    # Attorney → treating physician / QME / AME
    "ADVOCACY_LETTERS_PTP":         ("attorney", "treating_physician"),
    "ADVOCACY_LETTERS_QME":         ("attorney", "qme_physician"),
    "ADVOCACY_LETTERS_AME":         ("attorney", "qme_physician"),
    "ADVOCACY_LETTERS_PTP_QME_AME": ("attorney", "treating_physician"),
    "PTP_REFERRAL_LETTER":          ("treating_physician", "attorney"),

    # Attorney → adjuster / defense (demand/settlement)
    "SETTLEMENT_DEMAND_LETTER":          ("attorney", "adjuster"),
    "QME_PANEL_STRIKE_LETTER":           ("attorney", "adjuster"),
}

# Synthetic firm name used as the applicant attorney sender
_ATTORNEY_FIRM = "Martinez & Associates, APC"
_ATTORNEY_DOMAIN = "martinezapc.com"


def _resolve_participant(role: str, case: Any) -> tuple[str, str]:
    """Return (display_name, email_address) for a given role from a GeneratedCase.

    Generates plausible email addresses for roles that don't have explicit
    email fields on the model (attorney, treating physician, QME).
    """
    a = case.applicant
    ins = case.insurance
    tp = case.treating_physician

    role_map = {
        "applicant":         (a.full_name, a.email),
        "adjuster":          (ins.adjuster_name, ins.adjuster_email),
        "defense":           (ins.defense_attorney, ins.defense_email),
        "attorney":          (
            f"Applicant's Attorney",
            f"attorney@{_ATTORNEY_DOMAIN}",
        ),
        "treating_physician": (
            tp.full_name,
            f"{tp.first_name.lower()}.{tp.last_name.lower()}@{_slug(tp.facility)}.com",
        ),
        "qme_physician": (
            (case.qme_physician.full_name if case.qme_physician else "QME Physician"),
            (
                f"qme@{_slug(case.qme_physician.facility)}.com"
                if case.qme_physician
                else "qme@wcmedgroup.com"
            ),
        ),
    }
    return role_map.get(role, ("Unknown", "unknown@example.com"))


def _slug(text: str) -> str:
    """Convert a facility/firm name to a DNS-safe domain fragment."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "", text)
    return text[:20] or "medcenter"


def generate_email_headers(
    subtype: str,
    case: Any,
    doc_date: date,
    subject: str,
) -> dict[str, str]:
    """Build RFC 2822 email header fields for a document.

    Args:
        subtype: DocumentSubtype value string.
        case: GeneratedCase instance.
        doc_date: Date of the document.
        subject: Subject line (usually the document title).

    Returns:
        Dict of header name → value, ready for email.message.Message.
    """
    sender_role, recipient_role = EMAIL_PARTICIPANT_MAP.get(
        subtype, ("attorney", "adjuster")
    )
    sender_name, sender_addr = _resolve_participant(sender_role, case)
    recip_name, recip_addr = _resolve_participant(recipient_role, case)

    # Format RFC 2822 date from doc_date (use noon to avoid timezone issues)
    from datetime import datetime
    dt = datetime(doc_date.year, doc_date.month, doc_date.day, 12, 0, 0)
    rfc_date = formatdate(dt.timestamp(), localtime=False)

    ins = case.insurance
    inj = case.injuries[0]

    return {
        "From":         formataddr((sender_name, sender_addr)),
        "To":           formataddr((recip_name, recip_addr)),
        "Date":         rfc_date,
        "Subject":      subject,
        "Message-ID":   f"<{ins.claim_number}.{doc_date.isoformat()}@{_ATTORNEY_DOMAIN}>",
        "MIME-Version": "1.0",
        "Content-Type": "text/plain; charset=utf-8",
        "X-Claim-Number": ins.claim_number,
        "X-ADJ-Number":   inj.adj_number,
    }
