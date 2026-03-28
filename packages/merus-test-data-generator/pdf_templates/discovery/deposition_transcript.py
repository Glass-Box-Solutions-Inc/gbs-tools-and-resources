"""
Deposition Transcript template for Workers' Compensation discovery.

Uses topic-organized Q&A pools from data/deposition_exchanges.py to generate
80-150 exchange depositions (10-30 pages) with objections, exhibits, and time markers.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import random

from reportlab.lib.units import inch
from reportlab.platypus import PageBreak, Paragraph, Spacer

from data.deposition_exchanges import (
    generate_deposition_exchanges,
    generate_exhibit_reference,
    generate_objection,
    generate_time_marker,
)
from pdf_templates.base_template import BaseTemplate


class DepositionTranscript(BaseTemplate):
    """Generates a deposition transcript in Q&A format with realistic length."""

    def build_story(self, doc_spec):
        """Build deposition transcript — 10-30 pages."""
        story = []

        # Reporter info (used across cover, cert, and final cert)
        reporter_names = [
            "Jennifer Martinez", "Robert Chen", "Sarah Williams",
            "Michael Johnson", "Lisa Thompson", "Patricia Nguyen",
            "David Morales", "Karen O'Brien",
        ]
        reporter_name = random.choice(reporter_names)
        reporter_number = random.randint(5000, 15000)

        # --- Cover page ---
        story.extend(self._build_cover_page(doc_spec, reporter_name, reporter_number))

        # --- Certification page ---
        story.extend(self._build_certification(doc_spec, reporter_name, reporter_number))

        # --- Appearances ---
        story.extend(self._build_appearances())

        # --- Examination header ---
        story.append(self.make_hr())
        story.append(Spacer(1, 0.2 * inch))
        story.append(Paragraph(
            f"<b>EXAMINATION BY {self.case.insurance.defense_attorney}</b>",
            self.styles["SectionHeader"],
        ))
        story.append(Spacer(1, 0.2 * inch))

        # --- Generate Q&A exchanges ---
        # More exchanges = more pages. Target 10-30 pages requires 100-200+ exchanges
        # at ~8-10 exchanges per page in Courier 10pt
        exchanges = generate_deposition_exchanges(self.case, min_exchanges=100, max_exchanges=180)

        # Determine objection and exhibit insertion points
        total = len(exchanges)
        objection_count = random.randint(5, 10)
        exhibit_count = random.randint(3, 5)
        time_marker_count = random.randint(2, 4)

        objection_indices = set(random.sample(range(10, total - 5), min(objection_count, total - 15)))
        exhibit_indices = set(random.sample(range(15, total - 10), min(exhibit_count, total - 25)))
        # Time markers at roughly evenly-spaced points
        time_marker_positions = set()
        if total > 30:
            segment = total // (time_marker_count + 1)
            for i in range(1, time_marker_count + 1):
                time_marker_positions.add(segment * i + random.randint(-3, 3))

        line_num = 1
        exhibit_num = 1

        for idx, (q, a) in enumerate(exchanges):
            # Insert time marker before this exchange
            if idx in time_marker_positions:
                marker = generate_time_marker()
                story.append(Spacer(1, 0.15 * inch))
                story.append(Paragraph(
                    f"<i>{marker}</i>", self.styles["SmallItalic"],
                ))
                story.append(Spacer(1, 0.15 * inch))

            # Insert exhibit reference before this exchange
            if idx in exhibit_indices:
                exhibit_text = generate_exhibit_reference(exhibit_num, self.case)
                story.append(Spacer(1, 0.1 * inch))
                story.append(Paragraph(
                    f"{line_num:>3}  Q. {exhibit_text}", self.styles["Transcript"],
                ))
                line_num += 1
                story.append(Paragraph(
                    f"{line_num:>3}  A. {random.choice(['Yes, I recognize that', 'I believe so', 'Yes, that looks familiar', 'Let me take a look. Yes, I recognize it'])}.",
                    self.styles["Transcript"],
                ))
                line_num += 1
                story.append(Spacer(1, 0.1 * inch))
                exhibit_num += 1

            # Question
            story.append(Paragraph(f"{line_num:>3}  {q}", self.styles["Transcript"]))
            line_num += 1
            story.append(Spacer(1, 0.1 * inch))

            # Insert objection after question, before answer
            if idx in objection_indices:
                objection = generate_objection()
                story.append(Paragraph(
                    f"{line_num:>3}  MR./MS. ATTORNEY: {objection}",
                    self.styles["Transcript"],
                ))
                line_num += 1
                story.append(Paragraph(
                    f"{line_num:>3}  THE WITNESS: {random.choice(['Can I still answer?', ''])}",
                    self.styles["Transcript"],
                ))
                line_num += 1
                story.append(Paragraph(
                    f"{line_num:>3}  BY {self.case.insurance.defense_attorney}: You may answer.",
                    self.styles["Transcript"],
                ))
                line_num += 1
                story.append(Spacer(1, 0.05 * inch))

            # Answer
            story.append(Paragraph(f"{line_num:>3}  {a}", self.styles["Transcript"]))
            line_num += 1
            story.append(Spacer(1, 0.15 * inch))

        # --- End of examination ---
        story.append(Spacer(1, 0.3 * inch))
        end_hour = random.randint(11, 14)
        end_min = random.randint(10, 50)
        ampm = "A.M." if end_hour < 12 else "P.M."
        story.append(Paragraph(
            f"{line_num:>3}  (Deposition concluded at {end_hour}:{end_min:02d} {ampm})",
            self.styles["Transcript"],
        ))
        story.append(PageBreak())

        # --- Final certification ---
        story.extend(self._build_final_certification(doc_spec, reporter_name, reporter_number))

        return story

    def _build_cover_page(self, doc_spec, reporter_name, reporter_number):
        """Build the deposition cover page."""
        elements = []
        elements.append(Spacer(1, 1.5 * inch))
        elements.append(Paragraph("DEPOSITION OF", self.styles["CenterBold"]))
        elements.append(Spacer(1, 0.2 * inch))
        elements.append(Paragraph(
            self.case.applicant.full_name.upper(), self.styles["CenterBold"],
        ))
        elements.append(Spacer(1, 0.5 * inch))

        case_info = (
            f"Case: {self.case.applicant.full_name} v. {self.case.employer.company_name}<br/>"
            f"ADJ No.: {self.case.injuries[0].adj_number}<br/>"
            f"<br/>"
            f"Date: {doc_spec.doc_date.strftime('%B %d, %Y')}<br/>"
            f"Time: 10:00 A.M.<br/>"
            f"Location: {self.case.insurance.defense_firm}"
        )
        elements.append(Paragraph(case_info, self.styles["CenterBold"]))
        elements.append(Spacer(1, 0.5 * inch))

        reporter_info = (
            f"Reported by:<br/>"
            f"{reporter_name}<br/>"
            f"Certified Shorthand Reporter No. {reporter_number}"
        )
        elements.append(Paragraph(reporter_info, self.styles["CenterBold"]))
        elements.append(PageBreak())
        return elements

    def _build_certification(self, doc_spec, reporter_name, reporter_number):
        """Build the initial certification page."""
        elements = []
        cert_text = (
            f"<b>CERTIFICATION</b><br/>"
            f"<br/>"
            f"I, {reporter_name}, a Certified Shorthand Reporter for the State of California, "
            f"do hereby certify:<br/>"
            f"<br/>"
            f"That prior to being examined, the witness named in the foregoing deposition was by me "
            f"duly sworn to testify to the truth, the whole truth, and nothing but the truth;<br/>"
            f"<br/>"
            f"That said deposition is a true record of the testimony given by said witness;<br/>"
            f"<br/>"
            f"That I am neither counsel for, nor related to, any party to said action, nor in any way "
            f"interested in the outcome thereof.<br/>"
            f"<br/>"
            f"IN WITNESS WHEREOF, I have hereunto set my hand this "
            f"{doc_spec.doc_date.strftime('%d day of %B, %Y')}.<br/>"
            f"<br/><br/>"
            f"_______________________________<br/>"
            f"{reporter_name}<br/>"
            f"CSR No. {reporter_number}"
        )
        elements.append(Paragraph(cert_text, self.styles["BodyText14"]))
        elements.append(PageBreak())
        return elements

    def _build_appearances(self):
        """Build the appearances section."""
        elements = []
        elements.append(Paragraph("<b>APPEARANCES</b>", self.styles["SectionHeader"]))
        elements.append(Spacer(1, 0.2 * inch))

        appearances = (
            f"For Defendant:<br/>"
            f"{self.case.insurance.defense_attorney}<br/>"
            f"{self.case.insurance.defense_firm}<br/>"
            f"<br/>"
            f"For Applicant:<br/>"
            f"{self.case.applicant.full_name}<br/>"
            f"Appearing in Pro Per"
        )
        elements.append(Paragraph(appearances, self.styles["BodyText14"]))
        elements.append(Spacer(1, 0.3 * inch))
        return elements

    def _build_final_certification(self, doc_spec, reporter_name, reporter_number):
        """Build the final reporter certification."""
        elements = []
        final_cert = (
            f"<b>CERTIFICATE OF REPORTER</b><br/>"
            f"<br/>"
            f"I, {reporter_name}, Certified Shorthand Reporter, hereby certify that the witness in the "
            f"foregoing deposition was by me duly sworn to testify the truth, the whole truth, and nothing "
            f"but the truth; that said deposition was taken down in shorthand by me at the time and place "
            f"therein stated and was thereafter reduced to typewriting under my direction; that the "
            f"foregoing is a true and correct transcript of my shorthand notes so taken.<br/>"
            f"<br/>"
            f"I further certify that I am not of counsel or attorney for either or any of the parties to "
            f"said deposition nor in any way interested in the outcome of the cause named in said caption.<br/>"
            f"<br/>"
            f"IN WITNESS WHEREOF, I have hereunto set my hand this "
            f"{doc_spec.doc_date.strftime('%d day of %B, %Y')}.<br/>"
            f"<br/><br/><br/>"
            f"_______________________________<br/>"
            f"{reporter_name}<br/>"
            f"Certified Shorthand Reporter No. {reporter_number}<br/>"
            f"State of California"
        )
        elements.append(Paragraph(final_cert, self.styles["BodyText14"]))
        return elements
