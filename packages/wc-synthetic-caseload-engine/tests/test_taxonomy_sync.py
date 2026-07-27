"""Taxonomy tests — the classifier is the vocabulary of record (ISC-60/61).

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import pytest

from conftest import requires_classifier, requires_substrate
from wc_caseload_engine import taxonomy as tax


@requires_substrate
def test_effective_taxonomy_has_exactly_353_subtypes() -> None:
    engine = tax.effective_taxonomy()
    assert len(engine.subtypes) == tax.EXPECTED_SUBTYPE_COUNT
    assert len(set(engine.subtypes)) == tax.EXPECTED_SUBTYPE_COUNT
    assert len(engine.types) == tax.EXPECTED_TYPE_COUNT


@requires_substrate
@requires_classifier
def test_zero_set_diff_against_the_classifier_source() -> None:
    drift = tax.check_taxonomy_drift()
    assert drift.missing_from_engine == ()
    assert drift.extra_in_engine == ()
    assert drift.parent_mismatches == ()
    assert drift.missing_types == ()
    assert drift.extra_types == ()
    assert drift.clean
    assert drift.classifier_count == tax.EXPECTED_SUBTYPE_COUNT


@requires_classifier
def test_classifier_parser_reads_keys_labels_and_mapping() -> None:
    parsed = tax.parse_classifier_taxonomy()
    assert len(parsed.subtypes) == tax.EXPECTED_SUBTYPE_COUNT
    assert len(parsed.subtype_labels) == tax.EXPECTED_SUBTYPE_COUNT
    assert len(parsed.types) == tax.EXPECTED_TYPE_COUNT
    # Every subtype is mapped to exactly one parent type.
    assert set(parsed.subtype_to_type) == set(parsed.subtypes)


@requires_classifier
def test_classifier_parser_decodes_unicode_escapes_in_labels() -> None:
    parsed = tax.parse_classifier_taxonomy()
    label = parsed.subtype_labels["NOTICE_OF_PENALTY_5814"]
    assert "§5814" in label
    assert "\\u" not in label


@requires_classifier
def test_known_taxonomy_gotchas_are_preserved() -> None:
    """Shared labels and key/label swaps are real — the key is always truth."""
    parsed = tax.parse_classifier_taxonomy()
    labels = parsed.subtype_labels

    # CLAIM_FORM and CLAIM_FORM_DWC1 deliberately share one label.
    assert labels["CLAIM_FORM"] == labels["CLAIM_FORM_DWC1"] == "Claim Form (DWC-1)"

    # The two offer-of-work labels are swapped against their keys upstream.
    assert "Modified/Alternative" in labels["OFFER_OF_WORK_REGULAR_AD_10133_53"]
    assert "Regular Work" in labels["OFFER_OF_WORK_MODIFIED_AD_10118"]

    # PETITION_FOR_PENALTIES lives under CORRESPONDENCE, not PLEADINGS_FILINGS.
    assert parsed.subtype_to_type["PETITION_FOR_PENALTIES"] == "CORRESPONDENCE"


@requires_substrate
def test_overlay_covers_the_subtypes_the_substrate_lacks() -> None:
    engine = tax.effective_taxonomy()
    assert engine.overlay == frozenset(tax.OVERLAY_SUBTYPES)
    for subtype, overlay in tax.OVERLAY_SUBTYPES.items():
        assert engine.is_canonical(subtype)
        assert engine.parent_of(subtype) == overlay.parent_type
        assert engine.label(subtype) == overlay.label


@requires_substrate
def test_substrate_only_subtypes_are_renderable_but_not_canonical() -> None:
    engine = tax.effective_taxonomy()
    assert "FAX_COVER_SHEET" in engine.substrate_only
    assert not engine.is_canonical("FAX_COVER_SHEET")
    assert engine.is_renderable("FAX_COVER_SHEET")
    assert engine.subtype_set.isdisjoint(engine.substrate_only)


@requires_substrate
def test_every_canonical_subtype_has_a_parent_and_appears_under_it() -> None:
    engine = tax.effective_taxonomy()
    for subtype in engine.subtypes:
        parent = engine.parent_of(subtype)
        assert parent is not None, subtype
        assert subtype in engine.subtypes_for_type(parent)


@requires_substrate
def test_resolve_control_keys_expands_parent_types() -> None:
    engine = tax.effective_taxonomy()
    expanded = tax.resolve_control_keys(["LIENS", "DEPOSITION_TRANSCRIPT"], engine)
    assert "DEPOSITION_TRANSCRIPT" in expanded
    assert set(engine.subtypes_for_type("LIENS")).issubset(set(expanded))


def test_missing_classifier_raises_actionable_error(tmp_path: object) -> None:
    with pytest.raises(tax.TaxonomySourceError) as excinfo:
        tax.parse_classifier_taxonomy(str(tmp_path))
    message = str(excinfo.value)
    assert tax.CLASSIFIER_ENV_VAR in message
    assert "src/taxonomy" in message


@requires_substrate
def test_drift_report_names_the_missing_subtype(monkeypatch: pytest.MonkeyPatch) -> None:
    """A regressed overlay must surface as a named, actionable diff."""
    engine = tax.effective_taxonomy()
    crippled = tax.Taxonomy(
        types=engine.types,
        subtypes=tuple(s for s in engine.subtypes if s != "PETITION_FOR_PENALTIES"),
        subtype_labels=engine.subtype_labels,
        subtype_to_type=engine.subtype_to_type,
        type_to_subtypes=engine.type_to_subtypes,
    )
    if tax.find_classifier() is None:  # pragma: no cover - covered by the marker above
        pytest.skip("classifier unavailable")
    drift = tax.check_taxonomy_drift(taxonomy=crippled)
    assert drift.missing_from_engine == ("PETITION_FOR_PENALTIES",)
    assert not drift.clean
    assert "PETITION_FOR_PENALTIES" in drift.render()
    assert "OVERLAY_SUBTYPES" in drift.render()
