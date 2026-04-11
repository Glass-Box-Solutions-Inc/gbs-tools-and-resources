"""
Fax cover sheet template.

Generates a standard fax transmittal cover sheet — the kind prepended to
every faxed document in a CA WC case file.  Always rendered as scanned_pdf
by format_assignment so the scan simulator adds fax-header artifacts.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import random

from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import HRFlowable, Paragraph, Spacer, Table, TableStyle

from pdf_templates.base_template import BaseTemplate

# Real-sounding fax numbers for WC participants
_ADJUSTER_FAX = "({area}) {prefix}-{line}"
_COURT_FAX_POOL = [
    "(213) 974-1500", "(619) 767-2000", "(415) 703-5030",
    "(714) 558-4121", "(916) 851-2900", "(818) 901-5465",
]

_SENDER_ROLES = [
    "Law Offices of {firm}",
    "{firm} — Workers' Compensation Dept.",
    "Insurance Adjusting Services",
    "Medical Records Department",
]


class FaxCoverSheet(BaseTemplate):
    """Fax cover sheet — one page, table-based layout."""

    def build_story(self, doc_spec) -> list:
        story = []
        case = self.case
        date_str = doc_spec.doc_date.strftime("%B %d, %Y")
        time_str = f"{random.randint(8, 4 + 12):02d}:{random.choice(['00','15','30','45'])} {'AM' if random.random() < 0.4 else 'PM'}"

        # Fax header bar
        story.append(Paragraph("FACSIMILE TRANSMISSION", self.styles["CenterBold"]))
        story.append(Spacer(1, 0.05 * inch))
        story.append(HRFlowable(width="100%", thickness=2, color=colors.black))
        story.append(Spacer(1, 0.15 * inch))

        # Determine sender — law firm
        firm_name = getattr(getattr(case, "law_firm", None), "name", "Martinez & Associates, APC")

        # Determine recipient
        acc = self._get_accumulator(doc_spec)
        if acc and acc.generated_docs:
            recipient = f"{case.employer.company_name} — Claims Department"
        else:
            recipient = random.choice([
                f"{case.employer.company_name} — Claims Department",
                "Workers' Compensation Appeals Board",
                f"{case.employer.company_name} Defense Counsel",
                "Medical Records — Treating Physician",
            ])

        # Build the TO/FROM/RE table
        cell_label = self.styles["SectionHeader"]
        cell_value = self.styles["BodyText14"]

        fields = [
            ["TO:", recipient],
            ["FAX:", random.choice(_COURT_FAX_POOL)],
            ["FROM:", firm_name],
            ["DATE:", f"{date_str}  {time_str}"],
            ["RE:", f"Re: {case.applicant.full_name} / {case.case_number}"],
            ["PAGES:", f"{random.randint(1, 8)} (including this cover sheet)"],
        ]

        table_data = [
            [Paragraph(label, cell_label), Paragraph(value, cell_value)]
            for label, value in fields
        ]

        tbl = Table(table_data, colWidths=[1.2 * inch, 5.3 * inch])
        tbl.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("LINEBELOW", (0, 0), (-1, -2), 0.5, colors.HexColor("#cccccc")),
        ]))
        story.append(tbl)
        story.append(Spacer(1, 0.3 * inch))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.black))
        story.append(Spacer(1, 0.15 * inch))

        # COMMENTS / MESSAGE section
        story.append(Paragraph("COMMENTS / MESSAGE:", self.styles["SectionHeader"]))
        story.append(Spacer(1, 0.1 * inch))

        comments = _build_comment(doc_spec, case, acc)
        story.append(Paragraph(comments, self.styles["BodyText14"]))
        story.append(Spacer(1, 0.5 * inch))

        # Confidentiality notice
        notice = (
            "<i>CONFIDENTIALITY NOTICE: This facsimile transmission contains "
            "confidential information intended only for the use of the individual "
            "or entity named above. If you have received this transmission in error, "
            "please immediately notify the sender by telephone and destroy the "
            "original transmission. Unauthorized use, disclosure, or copying is "
            "strictly prohibited.</i>"
        )
        story.append(Paragraph(notice, self.styles["SmallItalic"]))

        return story


def _build_comment(doc_spec, case, acc) -> str:
    """Generate a plausible fax comment line based on prior docs or generic language."""
    if acc and acc.generated_docs:
        last = acc.generated_docs[-1]
        return (
            f"Please find enclosed the {last.title} dated "
            f"{last.doc_date.strftime('%B %d, %Y')} regarding the above-referenced "
            f"matter. Please confirm receipt at your earliest convenience."
        )
    return (
        f"Please find enclosed documents regarding the above-referenced workers' "
        f"compensation matter for {case.applicant.full_name}. "
        f"Please review and advise at your earliest convenience."
    )
