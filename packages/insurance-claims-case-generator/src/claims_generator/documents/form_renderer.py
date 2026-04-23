"""
Form renderer — Tier A form-accurate rendering helpers.

PNG blank form overlays are NOT available in assets/ for the following forms:
  - DWC-1 (Workers' Compensation Claim Form)
  - UB-04 (Institutional billing)
  - CMS-1500 (Professional billing)
  - DWC Form 105 (QME Panel Request)
  - DEU Rating Form

Per the Phase 2 plan: if blank PNG forms are not available, use reportlab table
layout approximating the form structure and log to ISSUES.md.

This module provides table-layout approximations of form fields that closely
mirror the section structure of each official form.

ISSUES.md entry: "Tier A form PNG blanks not available — using table approximation;
see docs/executions/AJC-21-2026-04-20.md for details."

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, Table, TableStyle

from claims_generator.documents.pdf_primitives import (
    COLOR_CA_BLUE,
    COLOR_MED_GRAY,
    CONTENT_WIDTH,
    STYLES,
)


def form_field_box(
    label: str,
    value: str,
    width: float = CONTENT_WIDTH,
    height: float = 0.35 * inch,
    label_size: float = 6.5,
) -> Table:
    """
    Single form field box: small label in upper-left, value text below.
    Approximates the box-style fields on DWC-1 and CMS-1500.
    """
    label_para = Paragraph(label, STYLES["label"])
    value_para = Paragraph(str(value), STYLES["body"])

    data = [[label_para], [value_para]]
    t = Table(data, colWidths=[width], rowHeights=[0.12 * inch, height - 0.12 * inch])
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.75, COLOR_MED_GRAY),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return t


def form_row(
    fields: list[tuple[str, str, float]],  # (label, value, width)
) -> Table:
    """
    A single horizontal row of form fields.
    Each element: (label, value, width_in_inches).
    """
    cells = [  # noqa: F841
        [
            Paragraph(label, STYLES["label"]),
            Paragraph(str(value), STYLES["body"]),
        ]
        for label, value, _ in fields
    ]
    widths = [w for _, _, w in fields]

    # Flatten: one column per field (label on top, value below)
    header_row = [Paragraph(label, STYLES["label"]) for label, _, _ in fields]
    value_row = [Paragraph(str(value), STYLES["body"]) for _, value, _ in fields]
    data = [header_row, value_row]

    t = Table(data, colWidths=widths)
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.75, COLOR_MED_GRAY),
        ("GRID", (0, 0), (-1, -1), 0.5, COLOR_MED_GRAY),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 6.5),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, 1), 8.5),
    ]))
    return t


def form_section_header(title: str, width: float = CONTENT_WIDTH) -> Table:
    """
    Dark header bar for a form section, e.g. "SECTION 1 — EMPLOYEE INFORMATION".
    """
    data = [[Paragraph(title, STYLES["label"])]]
    t = Table(data, colWidths=[width])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), COLOR_CA_BLUE),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def checkbox_field(label: str, checked: bool = False) -> Paragraph:
    """Checkbox field for form-style yes/no fields."""
    mark = "[X]" if checked else "[ ]"
    return Paragraph(f"{mark} {label}", STYLES["body"])
