"""
Abstract base class for all document generators.

Every DocumentGenerator subclass:
1. Declares which DocumentType(s) it handles via `handles`.
2. Implements `generate()` → bytes (PDF).
3. Uses `_build_doc()` to set up the SimpleDocTemplate with standard margins.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import io
from abc import ABC, abstractmethod

from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate

from claims_generator.documents.pdf_primitives import (
    BOTTOM_MARGIN,
    LEFT_MARGIN,
    RIGHT_MARGIN,
    TOP_MARGIN,
)
from claims_generator.models.claim import DocumentEvent
from claims_generator.models.enums import DocumentType
from claims_generator.models.profile import ClaimProfile


class DocumentGenerator(ABC):
    """
    Abstract base for all PDF document generators.

    Subclasses register themselves via `@register_document` and are
    dispatched by DocumentRegistry based on `document_type`.
    """

    #: DocumentType(s) this generator handles. Must be set by subclass.
    handles: frozenset[DocumentType]

    @classmethod
    @abstractmethod
    def generate(cls, event: DocumentEvent, profile: ClaimProfile) -> bytes:
        """
        Generate a PDF document and return its bytes.

        Args:
            event: The DocumentEvent driving this generation request.
            profile: The ClaimProfile providing party/case data.

        Returns:
            PDF file content as bytes. Must be > 500 bytes.
        """
        ...

    @classmethod
    def _build_doc(cls, buf: io.BytesIO, title: str = "") -> SimpleDocTemplate:
        """
        Build a standard-margin SimpleDocTemplate targeting a BytesIO buffer.

        Args:
            buf: BytesIO buffer to write the PDF into.
            title: Optional document title for PDF metadata.

        Returns:
            Configured SimpleDocTemplate ready for story.build().
        """
        return SimpleDocTemplate(
            buf,
            pagesize=letter,
            leftMargin=LEFT_MARGIN,
            rightMargin=RIGHT_MARGIN,
            topMargin=TOP_MARGIN,
            bottomMargin=BOTTOM_MARGIN,
            title=title,
            author="Glass Box Solutions — AdjudiCLAIMS Case Generator",
        )
