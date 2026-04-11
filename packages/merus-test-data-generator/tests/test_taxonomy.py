"""
Tests for the canonical taxonomy module (data/taxonomy.py).

Phase 1: asserts updated counts of 15 types and 350 subtypes from Adjudica-classifier.
"""

from __future__ import annotations

from data.taxonomy import (
    DocumentSubtype,
    DocumentType,
    DOCUMENT_SUBTYPE_LABELS,
    DOCUMENT_TYPE_LABELS,
    DOCUMENT_TYPE_TO_SUBTYPES,
    SUBTYPE_TO_TYPE,
)

# ---------------------------------------------------------------------------
# Count assertions (Phase 0 baseline)
# ---------------------------------------------------------------------------

def test_document_type_count() -> None:
    """Taxonomy must have exactly 15 parent document types (Phase 1)."""
    assert len(DocumentType) == 15


def test_document_subtype_count() -> None:
    """Taxonomy must have exactly 384 document subtypes (380 + 4 administrative noise)."""
    assert len(DocumentSubtype) == 384


# ---------------------------------------------------------------------------
# Label completeness
# ---------------------------------------------------------------------------

def test_type_labels_complete() -> None:
    """Every DocumentType member must have an entry in DOCUMENT_TYPE_LABELS."""
    for doc_type in DocumentType:
        assert doc_type.value in DOCUMENT_TYPE_LABELS, (
            f"DocumentType.{doc_type.name} ({doc_type.value!r}) is missing from "
            "DOCUMENT_TYPE_LABELS"
        )


def test_subtype_labels_complete() -> None:
    """Every DocumentSubtype member must have an entry in DOCUMENT_SUBTYPE_LABELS."""
    for subtype in DocumentSubtype:
        assert subtype.value in DOCUMENT_SUBTYPE_LABELS, (
            f"DocumentSubtype.{subtype.name} ({subtype.value!r}) is missing from "
            "DOCUMENT_SUBTYPE_LABELS"
        )


# ---------------------------------------------------------------------------
# DOCUMENT_TYPE_TO_SUBTYPES mapping integrity
# ---------------------------------------------------------------------------

def test_type_to_subtypes_mapping_complete() -> None:
    """Every key in DOCUMENT_TYPE_TO_SUBTYPES must be a valid DocumentType value."""
    valid_type_values = {t.value for t in DocumentType}
    for type_key in DOCUMENT_TYPE_TO_SUBTYPES:
        assert type_key in valid_type_values, (
            f"Key {type_key!r} in DOCUMENT_TYPE_TO_SUBTYPES is not a valid DocumentType"
        )


def test_every_subtype_in_exactly_one_type() -> None:
    """Each DocumentSubtype value should appear in exactly one type's subtype list.

    The 15-type / 350-subtype taxonomy has no intentional duplicates — each subtype
    belongs to exactly one parent type.
    """
    subtype_occurrences: dict[str, list[str]] = {}
    for type_key, subtypes in DOCUMENT_TYPE_TO_SUBTYPES.items():
        for subtype in subtypes:
            subtype_occurrences.setdefault(subtype, []).append(type_key)

    duplicates: dict[str, list[str]] = {
        subtype: types
        for subtype, types in subtype_occurrences.items()
        if len(types) > 1
    }

    assert not duplicates, (
        f"These subtypes appear in more than one type mapping: {duplicates}"
    )

    # Also verify every DocumentSubtype is accounted for
    all_mapped = set(subtype_occurrences.keys())
    all_enum_values = {s.value for s in DocumentSubtype}
    missing = all_enum_values - all_mapped
    assert not missing, (
        f"These DocumentSubtype values are not in any DOCUMENT_TYPE_TO_SUBTYPES list: "
        f"{missing}"
    )


def test_no_orphan_subtypes_in_mapping() -> None:
    """Every subtype string in DOCUMENT_TYPE_TO_SUBTYPES must be a valid DocumentSubtype value."""
    valid_subtype_values = {s.value for s in DocumentSubtype}
    orphans: list[str] = []
    for type_key, subtypes in DOCUMENT_TYPE_TO_SUBTYPES.items():
        for subtype in subtypes:
            if subtype not in valid_subtype_values:
                orphans.append(f"{subtype!r} (in type {type_key!r})")
    assert not orphans, (
        f"These strings in DOCUMENT_TYPE_TO_SUBTYPES are not valid DocumentSubtype values: "
        f"{orphans}"
    )


# ---------------------------------------------------------------------------
# SUBTYPE_TO_TYPE reverse map
# ---------------------------------------------------------------------------

def test_subtype_to_type_reverse_map() -> None:
    """The SUBTYPE_TO_TYPE dict must cover every DocumentSubtype value."""
    for subtype in DocumentSubtype:
        assert subtype.value in SUBTYPE_TO_TYPE, (
            f"DocumentSubtype.{subtype.name} ({subtype.value!r}) is missing from "
            "SUBTYPE_TO_TYPE reverse map"
        )
