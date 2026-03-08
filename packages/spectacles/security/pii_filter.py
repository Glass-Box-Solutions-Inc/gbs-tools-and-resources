"""
Spectacles PII Filter
Blur personally identifiable information in screenshots before sending to Slack

Detects and blurs:
- Credit card numbers
- Social Security Numbers
- Phone numbers
- Email addresses (optional)
- Custom patterns
"""

import re
import io
import logging
from typing import List, Tuple, Optional, Pattern
from dataclasses import dataclass

from PIL import Image, ImageFilter, ImageDraw

logger = logging.getLogger(__name__)


@dataclass
class PIIMatch:
    """Represents a detected PII match"""
    pattern_name: str
    text: str
    bbox: Tuple[int, int, int, int]  # x1, y1, x2, y2
    confidence: float


class PIIFilter:
    """
    Filter and blur PII in screenshots before external transmission.

    Uses regex patterns to detect sensitive data in OCR text,
    then applies gaussian blur to matching regions.
    """

    # Default PII patterns
    DEFAULT_PATTERNS: List[Tuple[str, str]] = [
        ("credit_card", r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b'),
        ("ssn", r'\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b'),
        ("phone", r'\b\d{3}[-\s.]?\d{3}[-\s.]?\d{4}\b'),
        ("email", r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
    ]

    def __init__(
        self,
        blur_radius: int = 15,
        extra_patterns: Optional[List[Tuple[str, str]]] = None,
        blur_emails: bool = False
    ):
        """
        Initialize PII filter.

        Args:
            blur_radius: Gaussian blur radius
            extra_patterns: Additional regex patterns as (name, pattern) tuples
            blur_emails: Whether to blur email addresses (default False)
        """
        self.blur_radius = blur_radius
        self.patterns: List[Tuple[str, Pattern]] = []

        # Compile default patterns
        for name, pattern in self.DEFAULT_PATTERNS:
            if name == "email" and not blur_emails:
                continue
            try:
                self.patterns.append((name, re.compile(pattern, re.IGNORECASE)))
            except re.error as e:
                logger.warning("Invalid pattern %s: %s", name, e)

        # Add extra patterns
        if extra_patterns:
            for name, pattern in extra_patterns:
                try:
                    self.patterns.append((name, re.compile(pattern, re.IGNORECASE)))
                except re.error as e:
                    logger.warning("Invalid extra pattern %s: %s", name, e)

    def detect_pii_in_text(self, text: str) -> List[str]:
        """
        Detect PII patterns in text.

        Args:
            text: Text to scan

        Returns:
            List of matched PII strings
        """
        matches = []
        for name, pattern in self.patterns:
            for match in pattern.finditer(text):
                matches.append(match.group())
        return matches

    def is_pii(self, text: str) -> bool:
        """
        Check if text contains PII.

        Args:
            text: Text to check

        Returns:
            True if PII detected
        """
        for name, pattern in self.patterns:
            if pattern.search(text):
                return True
        return False

    async def blur_pii_regions(
        self,
        screenshot_bytes: bytes,
        detected_regions: Optional[List[Tuple[str, Tuple[int, int, int, int]]]] = None
    ) -> bytes:
        """
        Blur regions containing PII.

        Args:
            screenshot_bytes: Original screenshot as bytes
            detected_regions: List of (text, bbox) tuples from OCR.
                            If None, no blurring is applied.

        Returns:
            Screenshot bytes with PII regions blurred
        """
        if not detected_regions:
            return screenshot_bytes

        try:
            image = Image.open(io.BytesIO(screenshot_bytes))

            pii_regions_blurred = 0

            for text, bbox in detected_regions:
                if self.is_pii(text):
                    # Expand bbox slightly for better coverage
                    x1, y1, x2, y2 = bbox
                    padding = 5
                    x1 = max(0, x1 - padding)
                    y1 = max(0, y1 - padding)
                    x2 = min(image.width, x2 + padding)
                    y2 = min(image.height, y2 + padding)

                    # Extract region, blur, and paste back
                    region = image.crop((x1, y1, x2, y2))
                    blurred = region.filter(ImageFilter.GaussianBlur(radius=self.blur_radius))
                    image.paste(blurred, (x1, y1))
                    pii_regions_blurred += 1

            if pii_regions_blurred > 0:
                logger.info("Blurred %d PII regions", pii_regions_blurred)

            # Convert back to bytes
            output = io.BytesIO()
            image.save(output, format='PNG')
            return output.getvalue()

        except Exception as e:
            logger.error("Error blurring PII: %s", e)
            return screenshot_bytes

    def blur_entire_sensitive_area(
        self,
        image_bytes: bytes,
        bbox: Tuple[int, int, int, int]
    ) -> bytes:
        """
        Blur a specific area of the image.

        Useful for manually specified sensitive regions like password fields.

        Args:
            image_bytes: Image as bytes
            bbox: Bounding box (x1, y1, x2, y2)

        Returns:
            Image bytes with region blurred
        """
        try:
            image = Image.open(io.BytesIO(image_bytes))

            x1, y1, x2, y2 = bbox
            region = image.crop((x1, y1, x2, y2))
            blurred = region.filter(ImageFilter.GaussianBlur(radius=self.blur_radius))
            image.paste(blurred, (x1, y1))

            output = io.BytesIO()
            image.save(output, format='PNG')
            return output.getvalue()

        except Exception as e:
            logger.error("Error blurring area: %s", e)
            return image_bytes

    def add_watermark(
        self,
        image_bytes: bytes,
        text: str = "SPECTICLES - CONFIDENTIAL"
    ) -> bytes:
        """
        Add watermark to image.

        Args:
            image_bytes: Image as bytes
            text: Watermark text

        Returns:
            Image bytes with watermark
        """
        try:
            image = Image.open(io.BytesIO(image_bytes))
            draw = ImageDraw.Draw(image)

            # Position at bottom right
            text_width = len(text) * 8  # Approximate
            x = image.width - text_width - 10
            y = image.height - 20

            # Semi-transparent white background
            draw.rectangle([x - 5, y - 2, x + text_width + 5, y + 15], fill=(255, 255, 255, 180))
            draw.text((x, y), text, fill=(100, 100, 100))

            output = io.BytesIO()
            image.save(output, format='PNG')
            return output.getvalue()

        except Exception as e:
            logger.error("Error adding watermark: %s", e)
            return image_bytes


# Default filter instance
_pii_filter: Optional[PIIFilter] = None


def get_pii_filter() -> PIIFilter:
    """Get default PII filter instance"""
    global _pii_filter
    if _pii_filter is None:
        _pii_filter = PIIFilter()
    return _pii_filter
