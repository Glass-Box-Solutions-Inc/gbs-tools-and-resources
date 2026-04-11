"""
Blank scanned page template.

Produces a near-blank page — a scanning artifact that appears in real
case files when a separator sheet, blank backside, or mis-fed page gets
captured.  Always rendered as scanned_pdf so it goes through the scan
simulator and emerges as a realistic image-based blank.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import random

from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, Spacer

from pdf_templates.base_template import BaseTemplate

# Variants: some blank pages have faint stamps or partial text
_VARIANTS = [
    "pure_blank",    # Completely blank
    "separator",     # "- - - SEPARATOR - - -" or "PAGE INTENTIONALLY LEFT BLANK"
    "faint_stamp",   # Faint "RECEIVED", "COPY", or "FILED" stamp
    "partial_header",  # Just the document header from page 1 bled through
]

_STAMP_TEXTS = ["RECEIVED", "COPY", "FILED", "CONFIDENTIAL", "FOR OFFICIAL USE ONLY"]


class BlankPage(BaseTemplate):
    """Near-blank scanned page — scanning artifact."""

    def build_story(self, doc_spec) -> list:
        story = []
        variant = random.choices(
            _VARIANTS,
            weights=[0.40, 0.30, 0.20, 0.10],
        )[0]

        # All variants start with significant vertical whitespace
        story.append(Spacer(1, 3.0 * inch))

        if variant == "pure_blank":
            # Truly blank — just return the spacer
            pass

        elif variant == "separator":
            msg = random.choice([
                "— PAGE INTENTIONALLY LEFT BLANK —",
                "- - - SEPARATOR PAGE - - -",
                "[ THIS PAGE LEFT BLANK ]",
            ])
            style = self.styles["CenterBold"]
            story.append(Paragraph(
                f'<font color="#cccccc">{msg}</font>',
                style,
            ))

        elif variant == "faint_stamp":
            stamp = random.choice(_STAMP_TEXTS)
            # Render as very light gray to simulate a rubber stamp
            story.append(Paragraph(
                f'<font size="36" color="#e8e8e8"><b>{stamp}</b></font>',
                self.styles["CenterBold"],
            ))

        elif variant == "partial_header":
            # Simulate bleed-through of page 1 firm header
            story.append(Paragraph(
                '<font size="10" color="#eeeeee">Martinez &amp; Associates, APC</font>',
                self.styles["CenterBold"],
            ))
            story.append(Spacer(1, 0.1 * inch))
            story.append(Paragraph(
                '<font size="8" color="#eeeeee">Workers\' Compensation Law • Los Angeles, CA</font>',
                self.styles["CenterBold"],
            ))

        return story
