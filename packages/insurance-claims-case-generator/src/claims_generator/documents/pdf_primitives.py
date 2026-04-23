"""
PDF primitives — reusable reportlab Flowable wrappers for CA Workers' Compensation documents.

Provides consistent typography, spacing, and CA WC-specific formatting
across all document tiers (A/B/C).

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

# ── Page geometry ──────────────────────────────────────────────────────────────

PAGE_WIDTH, PAGE_HEIGHT = letter
LEFT_MARGIN = 1.0 * inch
RIGHT_MARGIN = 1.0 * inch
TOP_MARGIN = 1.0 * inch
BOTTOM_MARGIN = 1.0 * inch
CONTENT_WIDTH = PAGE_WIDTH - LEFT_MARGIN - RIGHT_MARGIN

# ── Color palette ──────────────────────────────────────────────────────────────

COLOR_CA_BLUE = colors.HexColor("#003366")       # California state blue
COLOR_HEADER_BG = colors.HexColor("#E8EEF5")     # Light header background
COLOR_RULE = colors.HexColor("#4A7AB5")          # Section rule color
COLOR_WARNING = colors.HexColor("#CC3300")       # Warning / denial text
COLOR_LIGHT_GRAY = colors.HexColor("#F5F5F5")    # Table alternating row
COLOR_MED_GRAY = colors.HexColor("#CCCCCC")      # Table border
COLOR_BLACK = colors.black
COLOR_WHITE = colors.white

# ── Style sheet ────────────────────────────────────────────────────────────────

_BASE_STYLES = getSampleStyleSheet()


def build_styles() -> dict[str, ParagraphStyle]:
    """Build and return the shared CA WC document style dictionary."""
    return {
        "title": ParagraphStyle(
            "WCTitle",
            parent=_BASE_STYLES["Normal"],
            fontSize=14,
            fontName="Helvetica-Bold",
            textColor=COLOR_CA_BLUE,
            spaceAfter=6,
            alignment=1,  # center
        ),
        "subtitle": ParagraphStyle(
            "WCSubtitle",
            parent=_BASE_STYLES["Normal"],
            fontSize=11,
            fontName="Helvetica-Bold",
            textColor=COLOR_CA_BLUE,
            spaceAfter=4,
            alignment=1,
        ),
        "heading1": ParagraphStyle(
            "WCHeading1",
            parent=_BASE_STYLES["Normal"],
            fontSize=11,
            fontName="Helvetica-Bold",
            textColor=COLOR_CA_BLUE,
            spaceBefore=8,
            spaceAfter=4,
        ),
        "heading2": ParagraphStyle(
            "WCHeading2",
            parent=_BASE_STYLES["Normal"],
            fontSize=10,
            fontName="Helvetica-Bold",
            spaceBefore=6,
            spaceAfter=3,
        ),
        "body": ParagraphStyle(
            "WCBody",
            parent=_BASE_STYLES["Normal"],
            fontSize=9,
            fontName="Helvetica",
            spaceAfter=4,
            leading=13,
        ),
        "body_bold": ParagraphStyle(
            "WCBodyBold",
            parent=_BASE_STYLES["Normal"],
            fontSize=9,
            fontName="Helvetica-Bold",
            spaceAfter=4,
        ),
        "small": ParagraphStyle(
            "WCSmall",
            parent=_BASE_STYLES["Normal"],
            fontSize=7.5,
            fontName="Helvetica",
            spaceAfter=2,
            leading=10,
            textColor=colors.HexColor("#555555"),
        ),
        "disclaimer": ParagraphStyle(
            "WCDisclaimer",
            parent=_BASE_STYLES["Normal"],
            fontSize=7,
            fontName="Helvetica-Oblique",
            spaceAfter=2,
            leading=10,
            textColor=colors.HexColor("#666666"),
        ),
        "label": ParagraphStyle(
            "WCLabel",
            parent=_BASE_STYLES["Normal"],
            fontSize=7.5,
            fontName="Helvetica-Bold",
            textColor=colors.HexColor("#333333"),
        ),
        "value": ParagraphStyle(
            "WCValue",
            parent=_BASE_STYLES["Normal"],
            fontSize=9,
            fontName="Helvetica",
        ),
        "warning": ParagraphStyle(
            "WCWarning",
            parent=_BASE_STYLES["Normal"],
            fontSize=9,
            fontName="Helvetica-Bold",
            textColor=COLOR_WARNING,
            spaceAfter=4,
        ),
        "mono": ParagraphStyle(
            "WCMono",
            parent=_BASE_STYLES["Normal"],
            fontSize=8,
            fontName="Courier",
            spaceAfter=2,
            leading=12,
        ),
    }


STYLES = build_styles()


# ── Flowable helpers ───────────────────────────────────────────────────────────


def hline(width: float = CONTENT_WIDTH, thickness: float = 0.75) -> HRFlowable:
    """Thin horizontal rule."""
    return HRFlowable(width=width, thickness=thickness, color=COLOR_RULE, spaceAfter=4)


def thick_hline(width: float = CONTENT_WIDTH) -> HRFlowable:
    """Thick horizontal rule for section breaks."""
    return HRFlowable(width=width, thickness=2, color=COLOR_CA_BLUE, spaceAfter=6)


def spacer(height_pts: float = 6) -> Spacer:
    """Vertical spacer."""
    return Spacer(1, height_pts)


def para(text: str, style_name: str = "body") -> Paragraph:
    """Convenience wrapper: create a Paragraph from style name."""
    return Paragraph(text, STYLES[style_name])


def label_value_table(
    rows: list[tuple[str, str]],
    col_widths: tuple[float, float] = (1.8 * inch, CONTENT_WIDTH - 1.8 * inch),
) -> Table:
    """
    Two-column label/value table used throughout CA WC forms.

    Args:
        rows: List of (label, value) string pairs.
        col_widths: Column width tuple.
    """
    data = [
        [
            Paragraph(label, STYLES["label"]),
            Paragraph(str(value), STYLES["value"]),
        ]
        for label, value in rows
    ]
    t = Table(data, colWidths=list(col_widths))
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
    return t


def section_table(
    headers: list[str],
    rows: list[list[str]],
    col_widths: list[float] | None = None,
    header_bg: colors.Color = COLOR_HEADER_BG,
) -> Table:
    """
    Multi-column data table with styled header row.

    Args:
        headers: Column header labels.
        rows: Data rows (list of string lists).
        col_widths: Optional explicit column widths; defaults to equal split.
        header_bg: Header background color.
    """
    if col_widths is None:
        col_widths = [CONTENT_WIDTH / len(headers)] * len(headers)

    header_row = [Paragraph(h, STYLES["label"]) for h in headers]
    data_rows = [
        [Paragraph(str(cell), STYLES["body"]) for cell in row] for row in rows
    ]

    all_rows = [header_row] + data_rows
    t = Table(all_rows, colWidths=col_widths)

    style = [
        ("BACKGROUND", (0, 0), (-1, 0), header_bg),
        ("TEXTCOLOR", (0, 0), (-1, 0), COLOR_CA_BLUE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
        ("TOPPADDING", (0, 0), (-1, 0), 5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("TOPPADDING", (0, 1), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("GRID", (0, 0), (-1, -1), 0.5, COLOR_MED_GRAY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [COLOR_WHITE, COLOR_LIGHT_GRAY]),
    ]
    t.setStyle(TableStyle(style))
    return t


def two_col_section(
    left_items: list[tuple[str, str]],
    right_items: list[tuple[str, str]],
    left_width: float = CONTENT_WIDTH / 2 - 6,
    right_width: float = CONTENT_WIDTH / 2 - 6,
) -> Table:
    """
    Side-by-side two-column label/value layout for form-style sections.
    """

    def _cell(label: str, value: str) -> str:
        return f"<b>{label}:</b> {value}"

    max_rows = max(len(left_items), len(right_items))
    data = []
    for i in range(max_rows):
        left_text = _cell(*left_items[i]) if i < len(left_items) else ""
        right_text = _cell(*right_items[i]) if i < len(right_items) else ""
        data.append([
            Paragraph(left_text, STYLES["body"]),
            Paragraph(right_text, STYLES["body"]),
        ])

    t = Table(data, colWidths=[left_width, right_width])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t
