"""
Tests for the template registry (pdf_templates/registry.py).

Phase 2: taxonomy has 350 subtypes; registry covers all 350 of them.
0 subtypes fall through to the generic template.
"""

from __future__ import annotations

import importlib

from data.taxonomy import DocumentSubtype
from pdf_templates.registry import (
    TEMPLATE_REGISTRY,
    get_registry_coverage,
    get_template_for_subtype,
    load_template_class,
)


def test_every_subtype_has_registry_entry() -> None:
    """Verify registry coverage is 100% (Phase 2: all 350 subtypes registered).

    Phase 2 added explicit TemplateEntry mappings for all 163 new subtypes
    introduced by the 350-subtype taxonomy migration. No subtype should fall
    through to GenericDocumentTemplate.
    """
    missing = [
        subtype.value
        for subtype in DocumentSubtype
        if subtype.value not in TEMPLATE_REGISTRY
    ]
    assert len(missing) == 0, (
        f"Expected 0 subtypes missing from TEMPLATE_REGISTRY (Phase 2: full coverage), "
        f"but found {len(missing)}: {missing}"
    )


def test_template_classes_importable() -> None:
    """For each unique (class_name, module_path) in the registry, the module must
    be importable and the class must be present on it."""
    seen: set[tuple[str, str]] = set()
    errors: list[str] = []

    for subtype_key, entry in TEMPLATE_REGISTRY.items():
        pair = (entry.class_name, entry.module_path)
        if pair in seen:
            continue
        seen.add(pair)

        try:
            module = importlib.import_module(entry.module_path)
        except ImportError as exc:
            errors.append(
                f"Cannot import module {entry.module_path!r} "
                f"(needed for {subtype_key!r}): {exc}"
            )
            continue

        if not hasattr(module, entry.class_name):
            errors.append(
                f"Module {entry.module_path!r} has no attribute {entry.class_name!r} "
                f"(needed for {subtype_key!r})"
            )

    assert not errors, "\n".join(errors)


def test_get_template_for_subtype_all() -> None:
    """Calling get_template_for_subtype() for any subtype must never return the
    generic fallback. Phase 2: all 350 subtypes have explicit registry entries."""
    unexpected_generic_fallbacks: list[str] = []

    for subtype in DocumentSubtype:
        class_name, _variant = get_template_for_subtype(subtype.value)
        if class_name == "GenericDocumentTemplate":
            unexpected_generic_fallbacks.append(subtype.value)

    assert not unexpected_generic_fallbacks, (
        f"These subtypes unexpectedly fell back to GenericDocumentTemplate: "
        f"{unexpected_generic_fallbacks}"
    )


def test_registry_coverage_stats() -> None:
    """get_registry_coverage() must report 350 total subtypes with full coverage.

    Phase 2: all 350 subtypes have explicit registry entries; 0 fall through to
    GenericDocumentTemplate.
    """
    stats = get_registry_coverage()
    assert stats["total_subtypes"] == 350, (
        f"Expected total_subtypes=350, got {stats['total_subtypes']}"
    )
    assert stats["registry_covered"] == 350, (
        f"Expected registry_covered=350, got {stats['registry_covered']}"
    )
    assert stats["generic_fallthrough"] == 0, (
        f"Expected generic_fallthrough=0 (Phase 2: full coverage), "
        f"got {stats['generic_fallthrough']}"
    )
