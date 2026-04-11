"""
Cover letter / transmittal enclosure template.

Short letter accompanying a mailed or hand-delivered document package.
Common in CA WC: "Enclosed please find the QME report for your review..."
Always native PDF. Used for EVALUATION_COVER_LETTER and
COVER_LETTER_ENCLOSURE subtypes.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import random

from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, Spacer

from pdf_templates.base_template import BaseTemplate

_GREETINGS = [
    "Dear {name}:",
    "Dear Claims Representative:",
    "Dear Counsel:",
    "To Whom It May Concern:",
    "Dear Sir or Madam:",
]

_OPENINGS = [
    "Enclosed please find the following document(s) regarding the above-referenced matter:",
    "Please find enclosed the following materials in connection with this workers' compensation matter:",
    "We are forwarding herewith the enclosed documents for your review and file:",
    "Pursuant to our telephone conversation, please find the enclosed documentation:",
    "In response to your request, enclosed please find the following:",
]

_CLOSINGS = [
    (
        "Should you have any questions or require additional documentation, please do not "
        "hesitate to contact our office. We look forward to resolving this matter."
    ),
    (
        "Please review the enclosed materials at your earliest convenience and advise us "
        "of your position. We remain available to discuss this matter at any time."
    ),
    (
        "If you need additional information or have any questions regarding the enclosed "
        "documents, please contact our office directly."
    ),
    (
        "We trust the enclosed materials will be sufficient for your purposes. "
        "Please confirm receipt at your earliest convenience."
    ),
]

_SIGNATORIES = [
    ("Sincerely,", "J. Martinez, Esq.", "Attorney for Applicant"),
    ("Very truly yours,", "S. Rodriguez, Esq.", "Senior Associate"),
    ("Respectfully submitted,", "A. Kim, Esq.", "Workers' Compensation Specialist"),
    ("Best regards,", "Legal Staff", "Martinez & Associates, APC"),
]


class CoverLetterEnclosure(BaseTemplate):
    """Short transmittal cover letter — 1 page."""

    def build_story(self, doc_spec) -> list:
        story = []
        case = self.case
        date_str = doc_spec.doc_date.strftime("%B %d, %Y")
        acc = self._get_accumulator(doc_spec)

        # Firm letterhead
        firm_name = getattr(getattr(case, "law_firm", None), "name", "Martinez & Associates, APC")
        story.append(Paragraph(firm_name, self.styles["Letterhead"]))
        story.append(Paragraph(
            "Workers' Compensation Attorneys",
            self.styles["LetterheadSub"],
        ))
        story.append(Spacer(1, 0.3 * inch))

        # Date
        story.append(Paragraph(date_str, self.styles["RightAligned"]))
        story.append(Spacer(1, 0.2 * inch))

        # RE line
        story.append(Paragraph(
            f"<b>RE: {case.applicant.full_name} v. {case.employer.company_name}<br/>"
            f"Claim No.: {case.case_number}</b>",
            self.styles["BodyText14"],
        ))
        story.append(Spacer(1, 0.2 * inch))

        # Greeting
        recipient_name = random.choice(["the Adjuster", "Defense Counsel", "the WCAB Clerk"])
        greeting = random.choice(_GREETINGS).format(name=recipient_name)
        story.append(Paragraph(greeting, self.styles["BodyText14"]))
        story.append(Spacer(1, 0.15 * inch))

        # Opening paragraph
        story.append(Paragraph(random.choice(_OPENINGS), self.styles["BodyText14"]))
        story.append(Spacer(1, 0.1 * inch))

        # Enclosure list — pulled from accumulator if available, else generic
        if acc and acc.generated_docs:
            enclosures = acc.get_prior_docs(limit=3)
            for doc in enclosures:
                story.append(Paragraph(
                    f"• {doc.title} (dated {doc.doc_date.strftime('%m/%d/%Y')})",
                    self.styles["BodyText14"],
                ))
        else:
            generic_docs = random.sample([
                "Medical report from treating physician",
                "Wage statements and earnings records",
                "QME panel request form",
                "Declaration of Readiness to Proceed",
                "Proof of Service",
                "Application for Adjudication of Claim",
            ], k=random.randint(1, 3))
            for doc_name in generic_docs:
                story.append(Paragraph(f"• {doc_name}", self.styles["BodyText14"]))

        story.append(Spacer(1, 0.2 * inch))

        # Closing paragraph
        story.append(Paragraph(random.choice(_CLOSINGS), self.styles["BodyText14"]))
        story.append(Spacer(1, 0.4 * inch))

        # Signature block
        closing, name, title = random.choice(_SIGNATORIES)
        story.append(Paragraph(closing, self.styles["BodyText14"]))
        story.append(Spacer(1, 0.5 * inch))
        story.append(Paragraph(f"<b>{name}</b>", self.styles["BodyText14"]))
        story.append(Paragraph(title, self.styles["BodyText14"]))
        story.append(Paragraph(firm_name, self.styles["BodyText14"]))
        story.append(Spacer(1, 0.3 * inch))

        # Enclosures notation
        story.append(Paragraph("Enclosures", self.styles["SmallItalic"]))

        return story
