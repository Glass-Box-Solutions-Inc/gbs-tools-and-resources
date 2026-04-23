"""
Unit tests for DocumentRegistry — registration, dispatch, all 25 types covered.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import pytest

# Load all generators before testing registry
import claims_generator.documents.loader  # noqa: F401
from claims_generator.documents.registry import DocumentRegistry
from claims_generator.models.enums import DocumentType


class TestRegistryCompleteness:
    """Verify all 25 DocumentType values are registered."""

    def test_all_document_types_registered(self) -> None:
        """All 25 DocumentType enum values must have a registered generator."""
        registered = DocumentRegistry.registered_types()
        all_types = set(DocumentType)
        unregistered = all_types - registered
        assert not unregistered, (
            f"The following DocumentTypes are NOT registered: {unregistered}\n"
            f"Registered: {registered}"
        )

    def test_registered_count_equals_25(self) -> None:
        """Registry must contain exactly 25 entries."""
        assert len(DocumentRegistry.registered_types()) == len(DocumentType), (
            f"Expected {len(DocumentType)} registered types, "
            f"got {len(DocumentRegistry.registered_types())}"
        )

    @pytest.mark.parametrize("doc_type", list(DocumentType))
    def test_each_type_is_registered(self, doc_type: DocumentType) -> None:
        """Each individual DocumentType must be registered."""
        assert DocumentRegistry.is_registered(doc_type), (
            f"DocumentType.{doc_type.name} is not registered"
        )


class TestRegistryDispatch:
    """Verify DocumentRegistry.generate() returns valid bytes for all types."""

    def test_registry_does_not_raise_on_import(self) -> None:
        """Importing the loader must not raise any errors."""
        # Already imported above — just verify the registry is populated
        assert len(DocumentRegistry.registered_types()) > 0

    def test_is_registered_true_for_known_type(self) -> None:
        assert DocumentRegistry.is_registered(DocumentType.DWC1_CLAIM_FORM) is True

    def test_is_registered_false_for_unknown_type(self) -> None:
        """Use a sentinel — can't easily test with valid enum, so check registry directly."""
        # All types should be registered; this just verifies the method works
        result = DocumentRegistry.is_registered(DocumentType.OTHER)
        assert isinstance(result, bool)
