"""
DocumentRegistry — maps DocumentType → DocumentGenerator and dispatches generation.

Usage:
    @register_document
    class MyGenerator(DocumentGenerator):
        handles = frozenset({DocumentType.MEDICAL_REPORT})

        @classmethod
        def generate(cls, event, profile):
            ...

    pdf_bytes = DocumentRegistry.generate(event, profile)

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Type

from claims_generator.models.enums import DocumentType

if TYPE_CHECKING:
    from claims_generator.documents.base_document import DocumentGenerator
    from claims_generator.models.claim import DocumentEvent
    from claims_generator.models.profile import ClaimProfile

logger = logging.getLogger(__name__)

# Registry mapping DocumentType → generator class
_REGISTRY: dict[DocumentType, Type["DocumentGenerator"]] = {}


def register_document(cls: Type["DocumentGenerator"]) -> Type["DocumentGenerator"]:
    """
    Class decorator — registers a DocumentGenerator subclass in the registry.

    Raises:
        ValueError: If a DocumentType is already registered by another class.
    """
    for doc_type in cls.handles:
        if doc_type in _REGISTRY:
            existing = _REGISTRY[doc_type]
            if existing is not cls:
                raise ValueError(
                    f"DocumentType {doc_type!r} already registered by {existing.__name__}; "
                    f"cannot re-register with {cls.__name__}"
                )
        _REGISTRY[doc_type] = cls
    return cls


class DocumentRegistry:
    """Static registry and dispatch facade for document generators."""

    @staticmethod
    def generate(event: "DocumentEvent", profile: "ClaimProfile") -> bytes:
        """
        Generate a PDF for the given DocumentEvent.

        Falls back to a minimal stub PDF if no generator is registered for the type,
        logging a warning so the stub is easily detectable in test output.

        Args:
            event: DocumentEvent to generate.
            profile: ClaimProfile providing context data.

        Returns:
            PDF bytes. Always > 0 bytes.
        """
        doc_type = event.document_type
        generator = _REGISTRY.get(doc_type)
        if generator is None:
            logger.warning(
                "No generator registered for DocumentType %s; returning stub PDF",
                doc_type,
            )
            return _stub_pdf(event)
        try:
            return generator.generate(event, profile)
        except Exception:
            logger.exception(
                "Generator %s raised an error for event %s (%s); returning stub PDF",
                generator.__name__,
                event.event_id,
                doc_type,
            )
            return _stub_pdf(event)

    @staticmethod
    def registered_types() -> frozenset[DocumentType]:
        """Return the set of DocumentTypes that have a registered generator."""
        return frozenset(_REGISTRY.keys())

    @staticmethod
    def is_registered(doc_type: DocumentType) -> bool:
        """Return True if doc_type has a registered generator."""
        return doc_type in _REGISTRY


def _stub_pdf(event: "DocumentEvent") -> bytes:
    """
    Minimal stub PDF for unregistered or errored document types.
    Used only as a safety net — all 25 types should be registered.
    """
    import io

    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import Paragraph, SimpleDocTemplate

    from claims_generator.documents.pdf_primitives import STYLES

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter)
    story = [
        Paragraph(f"STUB — {event.document_type}", STYLES["title"]),
        Paragraph(event.title, STYLES["body"]),
        Paragraph(f"Event ID: {event.event_id}", STYLES["small"]),
        Paragraph(f"Subtype: {event.subtype_slug}", STYLES["small"]),
        Paragraph("No registered generator found for this document type.", STYLES["warning"]),
    ]
    doc.build(story)
    return buf.getvalue()
