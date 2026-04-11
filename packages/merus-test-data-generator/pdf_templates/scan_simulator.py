"""
Scan simulator — converts a native PDF into an image-based "scanned" PDF.

Simulates physical scanning artifacts found in real WC case files:
• Slight rotation (-1.5° to +1.5°)
• Brightness/contrast jitter
• JPEG compression artifacts (quality 72–88)
• Light salt-and-pepper noise
• Optional fax transmission header (15% probability)

All transforms are per-page so multi-page documents look naturally inconsistent.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import random
from datetime import date
from io import BytesIO
from typing import Optional

import fitz  # pymupdf
from PIL import Image, ImageEnhance


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def simulate_scan(
    pdf_bytes: bytes,
    rng: random.Random,
    doc_date: Optional[date] = None,
) -> bytes:
    """Convert native PDF bytes into an image-based scanned PDF.

    Args:
        pdf_bytes: Native PDF content produced by reportlab.
        rng: Seeded Random instance for reproducible artifacts.
        doc_date: Document date used in optional fax header.

    Returns:
        New PDF bytes where each page is a JPEG-compressed raster image.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    total_pages = doc.page_count
    add_fax_header = rng.random() < 0.15  # 15% of docs get a fax header

    page_images: list[tuple[Image.Image, int]] = []  # (image, jpeg_quality)

    for page_num in range(total_pages):
        page = doc[page_num]
        dpi = rng.randint(150, 200)
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

        img = _apply_rotation(img, rng)
        img = _apply_brightness_jitter(img, rng)
        img = _apply_noise(img, rng)

        if add_fax_header and page_num == 0:
            img = _prepend_fax_header(img, doc_date, page_num + 1, total_pages, dpi)

        jpeg_quality = rng.randint(72, 88)
        page_images.append((img, jpeg_quality))

    doc.close()
    return _images_to_pdf(page_images)


# ---------------------------------------------------------------------------
# Private transform helpers
# ---------------------------------------------------------------------------

def _apply_rotation(img: Image.Image, rng: random.Random) -> Image.Image:
    """Rotate image slightly to simulate scanner misalignment."""
    angle = rng.uniform(-1.5, 1.5)
    if abs(angle) < 0.2:
        return img
    return img.rotate(angle, expand=False, fillcolor=(255, 255, 255))


def _apply_brightness_jitter(img: Image.Image, rng: random.Random) -> Image.Image:
    """Apply per-page brightness variation (aging/exposure differences)."""
    factor = rng.uniform(0.90, 1.10)
    return ImageEnhance.Brightness(img).enhance(factor)


def _apply_noise(img: Image.Image, rng: random.Random) -> Image.Image:
    """Add very light salt-and-pepper noise simulating scanner sensor noise."""
    if rng.random() > 0.6:
        return img
    pixels = img.load()
    width, height = img.size
    num_pixels = max(1, int(width * height * 0.0005))
    for _ in range(num_pixels):
        x = rng.randint(0, width - 1)
        y = rng.randint(0, height - 1)
        shade = rng.choice([0, 255])
        pixels[x, y] = (shade, shade, shade)
    return img


def _prepend_fax_header(
    img: Image.Image,
    doc_date: Optional[date],
    page_num: int,
    total_pages: int,
    dpi: int,
) -> Image.Image:
    """Add a fax transmission header strip to the top of the image."""
    from PIL import ImageDraw, ImageFont

    date_str = doc_date.strftime("%m/%d/%Y") if doc_date else "01/01/2025"
    header_text = (
        f"FAX TRANSMISSION — {date_str} — "
        f"PAGE {page_num} OF {total_pages} — CONFIDENTIAL"
    )

    strip_height = max(30, int(dpi * 0.25))
    strip = Image.new("RGB", (img.width, strip_height), color=(235, 235, 235))
    draw = ImageDraw.Draw(strip)
    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 14
        )
    except OSError:
        font = ImageFont.load_default()
    draw.text((10, strip_height // 2 - 8), header_text, fill=(50, 50, 50), font=font)
    draw.line(
        [(0, strip_height - 2), (img.width, strip_height - 2)],
        fill=(100, 100, 100),
        width=1,
    )

    combined = Image.new("RGB", (img.width, img.height + strip_height), (255, 255, 255))
    combined.paste(strip, (0, 0))
    combined.paste(img, (0, strip_height))
    return combined


def _images_to_pdf(page_images: list[tuple[Image.Image, int]]) -> bytes:
    """Reassemble PIL images into a single PDF using pymupdf.

    Uses fitz (PyMuPDF) directly to embed JPEG images as full-page PDFs,
    avoiding reportlab's frame-padding constraints.
    """
    out_doc = fitz.open()

    for img, quality in page_images:
        img_buf = BytesIO()
        img.save(img_buf, format="JPEG", quality=quality, optimize=True)
        img_buf.seek(0)

        # Wrap JPEG as a single-page PDF via fitz
        img_doc = fitz.open(stream=img_buf.getvalue(), filetype="jpeg")
        pdfbytes = img_doc.convert_to_pdf()
        img_doc.close()

        img_pdf = fitz.open(stream=pdfbytes, filetype="pdf")
        out_doc.insert_pdf(img_pdf)
        img_pdf.close()

    result = out_doc.tobytes()
    out_doc.close()
    return result
