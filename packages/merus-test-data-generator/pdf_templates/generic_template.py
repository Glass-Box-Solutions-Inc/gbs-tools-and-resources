"""
Generic document template — fallback for subtypes without dedicated templates.

Uses template hints from data/template_hints.py to generate correctly structured
PDFs with appropriate titles, sections, and content style.

Enhanced with page-count-aware content scaling and expert report styles.

Tier 3 in the template hierarchy:
  Tier 1: Dedicated build_story() per subtype
  Tier 2: Parameterized variants of Tier 1 templates
  Tier 3: This generic template (correct structure, scaled content)

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import random

from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from data.template_hints import TemplateHint, get_hint
from data.taxonomy import DOCUMENT_SUBTYPE_LABELS
from pdf_templates.base_template import BaseTemplate


class GenericDocumentTemplate(BaseTemplate):
    """Generic template that adapts its output based on template hints and page count."""

    def build_story(self, doc_spec) -> list:
        story = []
        subtype_str = doc_spec.subtype.value if hasattr(doc_spec.subtype, "value") else str(doc_spec.subtype)
        hint = get_hint(subtype_str)
        label = DOCUMENT_SUBTYPE_LABELS.get(subtype_str, subtype_str.replace("_", " ").title())

        # Determine content scale from page_count_range
        min_pages, max_pages = hint.page_count_range
        target_pages = random.randint(min_pages, max_pages)
        # Approximate: ~5-6 sections with 3-sentence default, each section ~0.3 pages
        # So for N pages, we want ~N*3 sentences per section or more sections
        sentences_per_section = max(3, target_pages * 2)
        num_extra_sections = max(0, target_pages - 2)

        # Document header
        heading = hint.common_headings[0] if hint.common_headings else label.upper()
        story.append(Paragraph(heading, self.styles["CenterBold"]))
        story.append(Spacer(1, 0.15 * inch))

        # Check for expert report format
        is_expert = hint.format in ("Expert report", "Expert medical report")

        # Generate content based on style
        if is_expert:
            story.extend(self._build_expert_style(doc_spec, hint, label, sentences_per_section))
        elif hint.content_style == "medical":
            story.extend(self._build_medical_style(doc_spec, hint, label, sentences_per_section, num_extra_sections))
        elif hint.content_style == "legal":
            story.extend(self._build_legal_style(doc_spec, hint, label, sentences_per_section, num_extra_sections))
        elif hint.content_style == "correspondence":
            story.extend(self._build_correspondence_style(doc_spec, hint, label, sentences_per_section))
        else:
            story.extend(self._build_formal_style(doc_spec, hint, label, sentences_per_section, num_extra_sections))

        return story

    def _build_expert_style(self, doc_spec, hint: TemplateHint, label: str, sentences: int) -> list:
        """Generate expert report style (vocational, economist, life care, biomechanical)."""
        story = []

        # Expert credentials header
        expert_name = f"Dr. {random.choice(['James', 'Patricia', 'Robert', 'Linda', 'Michael'])} "
        expert_name += random.choice(["Morrison", "Castellano", "Whitfield", "Nakamura", "Petersen"])
        expert_title = random.choice([
            "Certified Vocational Expert", "Forensic Economist",
            "Certified Life Care Planner", "Biomechanical Engineer",
        ])

        story.extend(self.make_letterhead(
            expert_name, "Expert Consulting Services", "(310) 555-0200",
        ))
        story.append(Spacer(1, 0.2 * inch))

        # Case reference
        story.extend(self.make_patient_header())
        story.append(Spacer(1, 0.1 * inch))
        story.extend(self.make_claim_reference_block())
        story.append(Spacer(1, 0.15 * inch))

        # Date
        story.append(self.make_date_line("Report Date", doc_spec.doc_date))
        story.append(Spacer(1, 0.15 * inch))

        # Qualifications section (always first for expert reports)
        quals = (
            f"I, {expert_name}, am a {expert_title} with over "
            f"{random.randint(10, 30)} years of experience in my field. "
            f"I hold a {random.choice(['Ph.D.', 'Master of Science', 'Doctorate'])} in "
            f"{random.choice(['Vocational Rehabilitation', 'Economics', 'Nursing/Life Care Planning', 'Biomedical Engineering'])}. "
            f"I have been retained by counsel to provide an independent "
            f"{'vocational' if 'vocational' in label.lower() else 'expert'} analysis in this matter. "
            f"My curriculum vitae is attached as Appendix A."
        )
        story.extend(self.make_section("QUALIFICATIONS", quals))
        story.append(Spacer(1, 0.1 * inch))

        # Required sections with scaled content
        for section_title in hint.required_sections:
            if section_title.lower() == "qualifications":
                continue  # Already added
            if any(kw in section_title.lower() for kw in ["medical", "clinical", "treatment", "care"]):
                content = self.lorem_medical(sentences)
            elif any(kw in section_title.lower() for kw in ["analysis", "methodology", "calculation", "cost"]):
                content = self.lorem_legal(sentences) + " " + self.lorem_medical(max(2, sentences // 2))
            else:
                content = self.lorem_correspondence(sentences)
            story.extend(self.make_section(section_title, content))
            story.append(Spacer(1, 0.1 * inch))

        # Add padding sections for larger reports
        if sentences > 6:
            padding_sections = [
                ("MATERIALS REVIEWED", self.lorem_correspondence(sentences)),
                ("METHODOLOGY", self.lorem_legal(sentences)),
                ("LIMITATIONS OF ANALYSIS",
                 "The opinions expressed in this report are based on the materials reviewed "
                 "and my professional experience. Should additional information become available, "
                 "I reserve the right to supplement or revise my opinions."),
            ]
            for title, content in padding_sections[:max(0, (sentences - 6) // 3)]:
                story.extend(self.make_section(title, content))
                story.append(Spacer(1, 0.1 * inch))

        # Expert signature
        story.append(Spacer(1, 0.3 * inch))
        story.extend(self.make_signature_block(expert_name, expert_title, ""))
        story.append(Paragraph(
            "<i>I declare under penalty of perjury that the foregoing is true and correct.</i>",
            self.styles["SmallItalic"],
        ))

        return story

    def _build_medical_style(self, doc_spec, hint: TemplateHint, label: str,
                             sentences: int, extra_sections: int) -> list:
        """Generate medical-style document content with page-count scaling."""
        story = []

        story.extend(self.make_patient_header())
        story.append(Spacer(1, 0.1 * inch))
        story.extend(self.make_claim_reference_block())
        story.append(Spacer(1, 0.15 * inch))
        story.append(self.make_date_line("Document Date", doc_spec.doc_date))
        story.append(Spacer(1, 0.15 * inch))

        for section_title in hint.required_sections:
            story.extend(self.make_section(section_title, self.lorem_medical(sentences)))
            story.append(Spacer(1, 0.1 * inch))

        if not hint.required_sections:
            story.extend(self.make_section("Clinical Summary", self.lorem_medical(sentences + 1)))
            story.append(Spacer(1, 0.1 * inch))
            story.extend(self.make_section("Assessment", self.lorem_medical(sentences)))
            story.append(Spacer(1, 0.1 * inch))
            story.extend(self.make_section("Plan", self.lorem_medical(max(2, sentences - 1))))

        # Add padding sections for longer documents
        padding = ["Additional Findings", "Follow-Up Recommendations", "Clinical Notes"]
        for i in range(min(extra_sections, len(padding))):
            story.extend(self.make_section(padding[i], self.lorem_medical(sentences)))
            story.append(Spacer(1, 0.1 * inch))

        return story

    def _build_legal_style(self, doc_spec, hint: TemplateHint, label: str,
                           sentences: int, extra_sections: int) -> list:
        """Generate legal-style document content with page-count scaling."""
        story = []

        story.append(Paragraph(
            "<b>WORKERS' COMPENSATION APPEALS BOARD</b><br/>"
            "<b>STATE OF CALIFORNIA</b>",
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
        story.append(Paragraph(f"<b>{label}</b>", self.styles["CenterBold"]))
        story.append(Spacer(1, 0.15 * inch))
        story.append(self.make_date_line("Date Filed", doc_spec.doc_date))
        story.append(Spacer(1, 0.15 * inch))

        for section_title in hint.required_sections:
            story.extend(self.make_section(section_title, self.lorem_legal(sentences)))
            story.append(Spacer(1, 0.1 * inch))

        if not hint.required_sections:
            story.extend(self.make_section("Statement of Facts", self.lorem_legal(sentences + 1)))
            story.append(Spacer(1, 0.1 * inch))
            story.extend(self.make_section("Legal Analysis", self.lorem_legal(sentences)))
            story.append(Spacer(1, 0.1 * inch))
            story.extend(self.make_section("Conclusion", self.lorem_legal(max(2, sentences - 1))))

        padding = ["Argument", "Supporting Evidence", "Prayer for Relief"]
        for i in range(min(extra_sections, len(padding))):
            story.extend(self.make_section(padding[i], self.lorem_legal(sentences)))
            story.append(Spacer(1, 0.1 * inch))

        return story

    def _build_correspondence_style(self, doc_spec, hint: TemplateHint, label: str,
                                    sentences: int) -> list:
        """Generate correspondence-style content."""
        story = []

        story.extend(self.make_letterhead(
            self.case.insurance.carrier_name,
            "Claims Department",
            self.case.insurance.adjuster_phone,
        ))
        story.append(Spacer(1, 0.2 * inch))
        story.append(self.make_date_line("Date", doc_spec.doc_date))
        story.append(Spacer(1, 0.15 * inch))
        story.append(Paragraph(
            f"<b>Re:</b> {self.case.applicant.full_name} — "
            f"Claim No. {self.case.insurance.claim_number}",
            self.styles["BodyText14"],
        ))
        story.append(Spacer(1, 0.15 * inch))

        for section_title in hint.required_sections:
            story.extend(self.make_section(section_title, self.lorem_correspondence(sentences)))
            story.append(Spacer(1, 0.1 * inch))

        if not hint.required_sections:
            story.append(Paragraph(self.lorem_correspondence(sentences + 2), self.styles["BodyText14"]))

        story.append(Spacer(1, 0.3 * inch))
        story.extend(self.make_signature_block(
            self.case.insurance.adjuster_name, "Claims Adjuster", "",
        ))

        return story

    def _build_formal_style(self, doc_spec, hint: TemplateHint, label: str,
                            sentences: int, extra_sections: int) -> list:
        """Generate general formal document content with page-count scaling."""
        story = []

        story.extend(self.make_patient_header())
        story.append(Spacer(1, 0.1 * inch))
        story.extend(self.make_claim_reference_block())
        story.append(Spacer(1, 0.15 * inch))
        story.append(self.make_date_line("Date", doc_spec.doc_date))
        story.append(Spacer(1, 0.15 * inch))

        for section_title in hint.required_sections:
            if any(kw in section_title.lower() for kw in ["medical", "clinical", "treatment", "diagnosis"]):
                content = self.lorem_medical(sentences)
            elif any(kw in section_title.lower() for kw in ["legal", "order", "finding", "petition"]):
                content = self.lorem_legal(sentences)
            else:
                content = self.lorem_correspondence(sentences)
            story.extend(self.make_section(section_title, content))
            story.append(Spacer(1, 0.1 * inch))

        if not hint.required_sections:
            story.extend(self.make_section("Summary", self.lorem_correspondence(sentences + 1)))
            story.append(Spacer(1, 0.1 * inch))
            story.extend(self.make_section("Details", self.lorem_correspondence(sentences)))

        padding = ["Additional Information", "Notes", "Appendix"]
        for i in range(min(extra_sections, len(padding))):
            story.extend(self.make_section(padding[i], self.lorem_correspondence(sentences)))
            story.append(Spacer(1, 0.1 * inch))

        return story
