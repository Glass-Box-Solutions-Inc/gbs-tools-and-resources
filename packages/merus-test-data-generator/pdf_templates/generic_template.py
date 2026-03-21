"""
Generic document template — fallback for subtypes without dedicated templates.

Uses template hints from data/template_hints.py to generate correctly structured
PDFs with appropriate titles, sections, and content style.

Tier 3 in the template hierarchy:
  Tier 1: Dedicated build_story() per subtype
  Tier 2: Parameterized variants of Tier 1 templates
  Tier 3: This generic template (correct structure, generic content)

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors

from data.template_hints import TemplateHint, get_hint
from data.taxonomy import DOCUMENT_SUBTYPE_LABELS
from pdf_templates.base_template import BaseTemplate


class GenericDocumentTemplate(BaseTemplate):
    """Generic template that adapts its output based on template hints."""

    def build_story(self, doc_spec) -> list:
        story = []
        subtype_str = doc_spec.subtype.value if hasattr(doc_spec.subtype, 'value') else str(doc_spec.subtype)
        hint = get_hint(subtype_str)
        label = DOCUMENT_SUBTYPE_LABELS.get(subtype_str, subtype_str.replace("_", " ").title())

        # Document header — use the first common heading or the label
        heading = hint.common_headings[0] if hint.common_headings else label.upper()
        story.append(Paragraph(heading, self.styles["CenterBold"]))
        story.append(Spacer(1, 0.15 * inch))

        # Generate content based on style
        if hint.content_style == "medical":
            story.extend(self._build_medical_style(doc_spec, hint, label))
        elif hint.content_style == "legal":
            story.extend(self._build_legal_style(doc_spec, hint, label))
        elif hint.content_style == "correspondence":
            story.extend(self._build_correspondence_style(doc_spec, hint, label))
        else:
            story.extend(self._build_formal_style(doc_spec, hint, label))

        return story

    def _build_medical_style(self, doc_spec, hint: TemplateHint, label: str) -> list:
        """Generate medical-style document content."""
        story = []

        # Patient header
        story.extend(self.make_patient_header())
        story.append(Spacer(1, 0.1 * inch))

        # Claim reference
        story.extend(self.make_claim_reference_block())
        story.append(Spacer(1, 0.15 * inch))

        # Date
        story.append(self.make_date_line("Document Date", doc_spec.doc_date))
        story.append(Spacer(1, 0.15 * inch))

        # Sections from hints
        for section_title in hint.required_sections:
            story.extend(self.make_section(section_title, self.lorem_medical(3)))
            story.append(Spacer(1, 0.1 * inch))

        # If no sections specified, generate default medical content
        if not hint.required_sections:
            story.extend(self.make_section("Clinical Summary", self.lorem_medical(4)))
            story.append(Spacer(1, 0.1 * inch))
            story.extend(self.make_section("Assessment", self.lorem_medical(3)))
            story.append(Spacer(1, 0.1 * inch))
            story.extend(self.make_section("Plan", self.lorem_medical(2)))

        return story

    def _build_legal_style(self, doc_spec, hint: TemplateHint, label: str) -> list:
        """Generate legal-style document content."""
        story = []

        # Case caption
        story.append(Paragraph(
            f"<b>WORKERS' COMPENSATION APPEALS BOARD</b><br/>"
            f"<b>STATE OF CALIFORNIA</b>",
            self.styles["CenterBold"],
        ))
        story.append(Spacer(1, 0.1 * inch))

        story.append(Paragraph(
            f"{self.case.applicant.full_name}, Applicant,<br/>"
            f"vs.<br/>"
            f"{self.case.employer.company_name}, Defendant(s),<br/>"
            f"ADJ No.: {self.case.injuries[0].adj_number if self.case.injuries else 'N/A'}",
            self.styles["BodyText14"],
        ))
        story.append(Spacer(1, 0.15 * inch))

        # Document title
        story.append(Paragraph(f"<b>{label}</b>", self.styles["CenterBold"]))
        story.append(Spacer(1, 0.15 * inch))

        # Date
        story.append(self.make_date_line("Date Filed", doc_spec.doc_date))
        story.append(Spacer(1, 0.15 * inch))

        # Sections
        for section_title in hint.required_sections:
            story.extend(self.make_section(section_title, self.lorem_legal(3)))
            story.append(Spacer(1, 0.1 * inch))

        if not hint.required_sections:
            story.extend(self.make_section("Statement of Facts", self.lorem_legal(4)))
            story.append(Spacer(1, 0.1 * inch))
            story.extend(self.make_section("Legal Analysis", self.lorem_legal(3)))
            story.append(Spacer(1, 0.1 * inch))
            story.extend(self.make_section("Conclusion", self.lorem_legal(2)))

        return story

    def _build_correspondence_style(self, doc_spec, hint: TemplateHint, label: str) -> list:
        """Generate correspondence-style content."""
        story = []

        # Letterhead
        story.extend(self.make_letterhead(
            self.case.insurance.carrier_name,
            f"Claims Department",
            self.case.insurance.adjuster_phone,
        ))
        story.append(Spacer(1, 0.2 * inch))

        # Date and address
        story.append(self.make_date_line("Date", doc_spec.doc_date))
        story.append(Spacer(1, 0.15 * inch))

        # Re: line
        story.append(Paragraph(
            f"<b>Re:</b> {self.case.applicant.full_name} — "
            f"Claim No. {self.case.insurance.claim_number}",
            self.styles["BodyText14"],
        ))
        story.append(Spacer(1, 0.15 * inch))

        # Body sections
        for section_title in hint.required_sections:
            story.extend(self.make_section(section_title, self.lorem_correspondence(3)))
            story.append(Spacer(1, 0.1 * inch))

        if not hint.required_sections:
            story.append(Paragraph(self.lorem_correspondence(5), self.styles["BodyText14"]))

        # Signature
        story.append(Spacer(1, 0.3 * inch))
        story.extend(self.make_signature_block(
            self.case.insurance.adjuster_name, "Claims Adjuster", ""
        ))

        return story

    def _build_formal_style(self, doc_spec, hint: TemplateHint, label: str) -> list:
        """Generate general formal document content."""
        story = []

        # Patient/case reference
        story.extend(self.make_patient_header())
        story.append(Spacer(1, 0.1 * inch))
        story.extend(self.make_claim_reference_block())
        story.append(Spacer(1, 0.15 * inch))

        # Date
        story.append(self.make_date_line("Date", doc_spec.doc_date))
        story.append(Spacer(1, 0.15 * inch))

        # Sections from hints
        for section_title in hint.required_sections:
            # Choose content style based on section name
            if any(kw in section_title.lower() for kw in ["medical", "clinical", "treatment", "diagnosis"]):
                content = self.lorem_medical(3)
            elif any(kw in section_title.lower() for kw in ["legal", "order", "finding", "petition"]):
                content = self.lorem_legal(3)
            else:
                content = self.lorem_correspondence(3)
            story.extend(self.make_section(section_title, content))
            story.append(Spacer(1, 0.1 * inch))

        if not hint.required_sections:
            story.extend(self.make_section("Summary", self.lorem_correspondence(4)))
            story.append(Spacer(1, 0.1 * inch))
            story.extend(self.make_section("Details", self.lorem_correspondence(3)))

        return story
