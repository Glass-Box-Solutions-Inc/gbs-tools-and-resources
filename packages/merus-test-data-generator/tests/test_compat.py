"""
Tests for the taxonomy backward-compatibility layer (data/taxonomy_compat.py).

Verifies that legacy subtype names resolve correctly to canonical values, that
canonical names pass through unchanged, and that unknown names raise ValueError.
"""

from __future__ import annotations

import pytest

from data.taxonomy import DocumentSubtype
from data.taxonomy_compat import LEGACY_TO_CANONICAL, resolve_legacy_subtype

_VALID_SUBTYPES: frozenset[str] = frozenset(s.value for s in DocumentSubtype)

# A representative sample of canonical names that should pass through unchanged.
_CANONICAL_SAMPLE = [
    "APPLICATION_FOR_ADJUDICATION_ORIGINAL",
    "QME_REPORT_INITIAL",
    "BILLING_UB04",
]


def test_legacy_names_resolve() -> None:
    """Every key in LEGACY_TO_CANONICAL must resolve to a valid DocumentSubtype value."""
    bad: list[str] = []
    for legacy_name in LEGACY_TO_CANONICAL:
        try:
            result = resolve_legacy_subtype(legacy_name)
        except ValueError as exc:
            bad.append(f"{legacy_name!r}: raised ValueError — {exc}")
            continue

        if result not in _VALID_SUBTYPES:
            bad.append(
                f"{legacy_name!r}: resolved to {result!r}, which is not a valid "
                "DocumentSubtype value"
            )

    assert not bad, "\n".join(bad)


def test_canonical_names_passthrough() -> None:
    """Canonical subtype names must pass through resolve_legacy_subtype() unchanged."""
    for canonical_name in _CANONICAL_SAMPLE:
        result = resolve_legacy_subtype(canonical_name)
        assert result == canonical_name, (
            f"Expected canonical name {canonical_name!r} to pass through unchanged, "
            f"but got {result!r}"
        )


def test_unknown_name_raises() -> None:
    """resolve_legacy_subtype() must raise ValueError for completely unknown names."""
    with pytest.raises(ValueError, match="TOTALLY_BOGUS_NAME"):
        resolve_legacy_subtype("TOTALLY_BOGUS_NAME")


def test_legacy_188_resolution() -> None:
    """Subtypes removed during the 188-to-350 migration must resolve to their canonical replacement."""
    result = resolve_legacy_subtype("DOR_STATUS_MSC_EXPEDITED")
    assert result == "DECLARATION_OF_READINESS", (
        f"Expected 'DECLARATION_OF_READINESS', got {result!r}"
    )
