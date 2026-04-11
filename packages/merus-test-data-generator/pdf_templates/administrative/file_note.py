"""
Internal file note / diary entry template.

Replicates the short internal notes attorneys and adjusters create in
their case management systems — e.g., "Spoke with adjuster. Confirmed
TD payment sent." Always native PDF; these never get scanned or emailed.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import random

from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import HRFlowable, Paragraph, Spacer, Table, TableStyle

from pdf_templates.base_template import BaseTemplate

_NOTE_AUTHORS = [
    "J. Martinez, Esq.", "S. Kim, Paralegal", "A. Rodriguez, Esq.",
    "M. Chen, Case Manager", "D. Nguyen, Esq.", "Legal Staff",
]

_NOTE_SUBJECTS = [
    "Telephone conference with adjuster re: status",
    "Receipt and review of medical records",
    "Client telephone conference — status update",
    "Review of QME report — notes",
    "Discovery response deadline calendared",
    "Correspondence with defense counsel",
    "File review — trial preparation notes",
    "IMR outcome review — next steps",
    "Lien negotiation call with provider",
    "Settlement conference preparation",
    "Internal strategy session notes",
    "Medical appointment confirmed with client",
]

_NOTE_BODIES = [
    (
        "Spoke with adjuster at {carrier} regarding status of claim. Adjuster confirmed "
        "that TD payments are current through {date}. No outstanding issues at this time. "
        "Will follow up in 30 days or upon receipt of next medical report."
    ),
    (
        "Received and reviewed medical records from treating physician. Records span "
        "approximately {pages} pages and are consistent with prior reports. No unexpected "
        "findings. Forwarded copy to client for review per standard protocol."
    ),
    (
        "Telephone conference with client. Client reports continued pain and functional "
        "limitations. Treatment ongoing. Client advised re: upcoming QME appointment and "
        "what to expect. Client instructed not to minimize or exaggerate symptoms. "
        "File note prepared for record."
    ),
    (
        "Reviewed QME report received {date}. WPI rating appears consistent with "
        "clinical findings. PD rating calculation to follow. Potential objection to "
        "apportionment findings — schedule follow-up with client and reviewing physician."
    ),
    (
        "Calendared discovery response deadline for {date}. Subpoena returns pending "
        "from {entity}. Deposition of applicant scheduled — notice to issue this week. "
        "Defense counsel confirmed availability."
    ),
    (
        "Correspondence with defense counsel re: settlement posture. Defense indicated "
        "willingness to discuss C&R at upcoming MSC. Will prepare valuation memo in advance "
        "of conference. Client to be advised."
    ),
]


class FileNote(BaseTemplate):
    """Internal file note / diary entry — short, memo-style."""

    def build_story(self, doc_spec) -> list:
        story = []
        case = self.case
        date_str = doc_spec.doc_date.strftime("%B %d, %Y")
        acc = self._get_accumulator(doc_spec)

        author = random.choice(_NOTE_AUTHORS)
        subject = random.choice(_NOTE_SUBJECTS)

        # Header
        story.append(Paragraph("INTERNAL FILE NOTE", self.styles["CenterBold"]))
        story.append(Spacer(1, 0.1 * inch))
        story.append(HRFlowable(width="100%", thickness=1.5, color=colors.black))
        story.append(Spacer(1, 0.1 * inch))

        # Metadata table
        meta_rows = [
            ["DATE:", date_str],
            ["CASE:", f"{case.applicant.full_name} — {case.case_number}"],
            ["PREPARED BY:", author],
            ["RE:", subject],
        ]

        label_style = self.styles["SectionHeader"]
        value_style = self.styles["BodyText14"]

        tbl_data = [
            [Paragraph(lbl, label_style), Paragraph(val, value_style)]
            for lbl, val in meta_rows
        ]

        tbl = Table(tbl_data, colWidths=[1.4 * inch, 5.1 * inch])
        tbl.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("LINEBELOW", (0, 0), (-1, -2), 0.5, colors.HexColor("#dddddd")),
        ]))
        story.append(tbl)
        story.append(Spacer(1, 0.2 * inch))
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#aaaaaa")))
        story.append(Spacer(1, 0.15 * inch))

        # Note body
        body_template = random.choice(_NOTE_BODIES)
        body = body_template.format(
            carrier=getattr(case, "insurance_carrier", "the carrier") or "the carrier",
            date=date_str,
            pages=random.randint(20, 120),
            entity=random.choice(["Kaiser Permanente", "St. Francis Medical Center", "the employer"]),
        )
        # If accumulator has prior docs, splice in a reference
        if acc and acc.generated_docs:
            last = acc.generated_docs[-1]
            body = (
                f"Following receipt of {last.title} ({last.doc_date.strftime('%m/%d/%Y')}): "
                + body
            )

        story.append(Paragraph(body, self.styles["BodyText14"]))
        story.append(Spacer(1, 0.3 * inch))

        # Action items (optional)
        if random.random() < 0.6:
            story.append(Paragraph("ACTION ITEMS:", self.styles["SectionHeader"]))
            actions = random.sample([
                f"Follow up with adjuster in {random.randint(7, 30)} days.",
                "Calendar response deadline.",
                "Send copy of records to client.",
                "Prepare demand letter.",
                "Schedule client telephone conference.",
                "Review and calendar QME panel selection deadline.",
                "Confirm deposition date with all parties.",
            ], k=random.randint(1, 3))
            for action in actions:
                story.append(Paragraph(f"• {action}", self.styles["BodyText14"]))

        story.append(Spacer(1, 0.5 * inch))
        story.append(Paragraph(
            "<i>This note is attorney work product and is confidential.</i>",
            self.styles["SmallItalic"],
        ))

        return story
