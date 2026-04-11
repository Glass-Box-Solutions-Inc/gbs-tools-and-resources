"""
Style mapping from reportlab ParagraphStyle names to python-docx equivalents.

Provides a consistent Word document appearance for attorney work product:
Times New Roman 12pt body, firm letterhead in header, CONFIDENTIAL footer.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Style name mapping — reportlab → python-docx built-in style names
# ---------------------------------------------------------------------------

# Maps reportlab style name → (docx_style_name, bold, italic, font_size_pt)
# font_size_pt = None means use the style's default
STYLE_MAP: dict[str, tuple[str, bool, bool, int | None]] = {
    "CenterBold":    ("Title",      True,  False, 14),
    "SectionHeader": ("Heading 2",  True,  False, None),
    "BodyText14":    ("Normal",     False, False, 12),
    "DoubleSpaced":  ("Normal",     False, False, 12),
    "SmallItalic":   ("Normal",     False, True,  9),
    "RightAligned":  ("Normal",     False, False, 10),
    "TableCell":     ("Normal",     False, False, 9),
    "Transcript":    ("Normal",     False, False, 10),
    "MonoFindings":  ("Normal",     False, False, 9),
    "Letterhead":    ("Title",      True,  False, 14),
    "LetterheadSub": ("Subtitle",   False, False, 10),
}

# Letterhead configuration — used in Word document header section
FIRM_LETTERHEAD = {
    "name":    "Martinez & Associates, APC",
    "address": "1250 Wilshire Blvd., Suite 800 • Los Angeles, CA 90017",
    "phone":   "Tel: (213) 555-0100 • Fax: (213) 555-0199",
}

# Styles that force Courier (monospace) font in Word
MONOSPACE_STYLES: frozenset[str] = frozenset({"Transcript", "MonoFindings"})

# Styles that should use double line spacing
DOUBLE_SPACED_STYLES: frozenset[str] = frozenset({"DoubleSpaced"})

# Styles that should be center-aligned
CENTER_ALIGNED_STYLES: frozenset[str] = frozenset({"CenterBold", "Letterhead", "LetterheadSub"})

# Styles that should be right-aligned
RIGHT_ALIGNED_STYLES: frozenset[str] = frozenset({"RightAligned"})
