"""AJC-64 item 0c — the Initial File Review stops certifying its own inputs.

`defense_lens.py` used to **hardcode** ``ENGINE_POLICY_WITH_COUNSEL_CONFIRMED_INPUTS``
on every Initial File Review, and `fact_templates.py` printed it as an
"Authority Status:" line. Nothing checked any input's counsel status, and
`money.py` labels its own rate bindings COUNSEL-UNCONFIRMED throughout. A
document that certifies itself is evidence of nothing (M5-R40).

The fix derives the status from the M5-R36b figure→class map rather than
asserting it. These oracles are written so that the derivation cannot be
satisfied vacuously:

* the map is pinned by **exact dictionary equality against literals here**, not
  read from the module, so a re-classified figure cannot re-classify its own
  oracle (Form A);
* the printed-path set is **walked from the renderer** and asserted *equal* to
  the map's key set, so a figure the renderer prints and the map omits fails —
  the map cannot silently under-cover (m24-83);
* the resolution is exercised with an **all-resolved positive control** as well
  as an unresolved fixture, because a branch that is merely absent is not a
  branch that is proved reachable;
* transitivity is probed with a single unconfirmed leaf under a doubly derived
  total, which is the case a one-level implementation gets wrong while looking
  correct (m24-124).

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest

from conftest import extract_text, requires_substrate
from test_defense_lens import _seed, _three_event_defense
from wc_caseload_engine import defense_lens
from wc_caseload_engine.defense_lens import (
    AUTHORITY_STATUS_CONFIRMED,
    AUTHORITY_STATUS_UNCONFIRMED,
    CONFIRMED_FIGURE_CLASSES,
    DERIVED_FIGURE_CLASS,
    IFR_DERIVED_INPUTS,
    IFR_FIGURE_CLASSES,
    AuthorityDerivationError,
    resolve_authority_status,
    resolved_figures,
)
from wc_caseload_engine.planner import build_case_plan
from wc_caseload_engine.renderer import render_document
from wc_caseload_engine.seeds import parse_case_seed

UNCONFIRMED = "ENGINE_POLICY_UNCONFIRMED"
DERIVED = "DERIVED"

#: The complete M5-R36b inventory, as literals. Keys are exact printed model
#: paths on the axis order the renderer actually reads
#: (``getattr(exposure.low, "indemnity")`` → ``exposure.low.indemnity``);
#: conceptual key names cannot be checked against anything.
EXPECTED_FIGURE_CLASSES = {
    "exposure.low.indemnity": UNCONFIRMED,
    "exposure.low.medical": UNCONFIRMED,
    "exposure.low.expense_alae": UNCONFIRMED,
    "exposure.low.total": DERIVED,
    "exposure.expected.indemnity": UNCONFIRMED,
    "exposure.expected.medical": UNCONFIRMED,
    "exposure.expected.expense_alae": UNCONFIRMED,
    "exposure.expected.total": DERIVED,
    "exposure.high.indemnity": UNCONFIRMED,
    "exposure.high.medical": UNCONFIRMED,
    "exposure.high.expense_alae": UNCONFIRMED,
    "exposure.high.total": DERIVED,
    "recommendation.paid.indemnity": UNCONFIRMED,
    "recommendation.paid.medical": UNCONFIRMED,
    "recommendation.paid.expense_alae": UNCONFIRMED,
    "recommendation.paid.total": DERIVED,
    "recommendation.outstanding_reserve.indemnity": UNCONFIRMED,
    "recommendation.outstanding_reserve.medical": UNCONFIRMED,
    "recommendation.outstanding_reserve.expense_alae": UNCONFIRMED,
    "recommendation.outstanding_reserve.total": DERIVED,
    "recommendation.incurred.indemnity": DERIVED,
    "recommendation.incurred.medical": DERIVED,
    "recommendation.incurred.expense_alae": DERIVED,
    "recommendation.incurred.total": DERIVED,
    "booked_snapshot.paid.indemnity": UNCONFIRMED,
    "booked_snapshot.paid.medical": UNCONFIRMED,
    "booked_snapshot.paid.expense_alae": UNCONFIRMED,
    "booked_snapshot.paid.total": DERIVED,
    "booked_snapshot.outstanding_reserve.indemnity": UNCONFIRMED,
    "booked_snapshot.outstanding_reserve.medical": UNCONFIRMED,
    "booked_snapshot.outstanding_reserve.expense_alae": UNCONFIRMED,
    "booked_snapshot.outstanding_reserve.total": DERIVED,
    "booked_snapshot.incurred.indemnity": DERIVED,
    "booked_snapshot.incurred.medical": DERIVED,
    "booked_snapshot.incurred.expense_alae": DERIVED,
    "booked_snapshot.incurred.total": DERIVED,
    "litigation_budget": UNCONFIRMED,
    "adoption_lag_days": UNCONFIRMED,
}

EXPECTED_DERIVED_INPUTS = {
    "exposure.low.total": (
        "exposure.low.indemnity",
        "exposure.low.medical",
        "exposure.low.expense_alae",
    ),
    "exposure.expected.total": (
        "exposure.expected.indemnity",
        "exposure.expected.medical",
        "exposure.expected.expense_alae",
    ),
    "exposure.high.total": (
        "exposure.high.indemnity",
        "exposure.high.medical",
        "exposure.high.expense_alae",
    ),
    "recommendation.paid.total": (
        "recommendation.paid.indemnity",
        "recommendation.paid.medical",
        "recommendation.paid.expense_alae",
    ),
    "recommendation.outstanding_reserve.total": (
        "recommendation.outstanding_reserve.indemnity",
        "recommendation.outstanding_reserve.medical",
        "recommendation.outstanding_reserve.expense_alae",
    ),
    "booked_snapshot.paid.total": (
        "booked_snapshot.paid.indemnity",
        "booked_snapshot.paid.medical",
        "booked_snapshot.paid.expense_alae",
    ),
    "booked_snapshot.outstanding_reserve.total": (
        "booked_snapshot.outstanding_reserve.indemnity",
        "booked_snapshot.outstanding_reserve.medical",
        "booked_snapshot.outstanding_reserve.expense_alae",
    ),
    "recommendation.incurred.indemnity": (
        "recommendation.paid.indemnity",
        "recommendation.outstanding_reserve.indemnity",
    ),
    "recommendation.incurred.medical": (
        "recommendation.paid.medical",
        "recommendation.outstanding_reserve.medical",
    ),
    "recommendation.incurred.expense_alae": (
        "recommendation.paid.expense_alae",
        "recommendation.outstanding_reserve.expense_alae",
    ),
    "booked_snapshot.incurred.indemnity": (
        "booked_snapshot.paid.indemnity",
        "booked_snapshot.outstanding_reserve.indemnity",
    ),
    "booked_snapshot.incurred.medical": (
        "booked_snapshot.paid.medical",
        "booked_snapshot.outstanding_reserve.medical",
    ),
    "booked_snapshot.incurred.expense_alae": (
        "booked_snapshot.paid.expense_alae",
        "booked_snapshot.outstanding_reserve.expense_alae",
    ),
    "recommendation.incurred.total": (
        "recommendation.incurred.indemnity",
        "recommendation.incurred.medical",
        "recommendation.incurred.expense_alae",
    ),
    "booked_snapshot.incurred.total": (
        "booked_snapshot.incurred.indemnity",
        "booked_snapshot.incurred.medical",
        "booked_snapshot.incurred.expense_alae",
    ),
}

#: The buckets `reserve_bucket_rows` prints, as a literal. Read back out of the
#: renderer's own source below, because a hand-copied column list is exactly how
#: revision 7's inventory came to omit every `total` column.
EXPECTED_BUCKET_FIELDS = ("indemnity", "medical", "expense_alae", "total")
EXPECTED_EXPOSURE_AXES = ("low", "expected", "high")
EXPECTED_SNAPSHOT_AXES = ("paid", "outstanding_reserve", "incurred")
EXPECTED_SCALAR_PATHS = ("litigation_budget", "adoption_lag_days")


def _fact_templates_source() -> ast.Module:
    path = Path(defense_lens.__file__).with_name("fact_templates.py")
    return ast.parse(path.read_text(encoding="utf-8"))


def _renderer_bucket_fields() -> tuple[str, ...]:
    """The bucket column keys, read from `reserve_bucket_rows` in the renderer.

    The tuple lives inside a function body, so it is recovered from the syntax
    tree rather than imported. Reading it is what makes the path parity below a
    statement about the renderer instead of a statement about this file.
    """
    for node in ast.walk(_fact_templates_source()):
        if not isinstance(node, ast.Assign):
            continue
        targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if "reserve_bucket_rows" not in targets:
            continue
        assert isinstance(node.value, ast.Tuple)
        fields: list[str] = []
        for element in node.value.elts:
            assert isinstance(element, ast.Tuple)
            field = element.elts[1]
            assert isinstance(field, ast.Constant)
            fields.append(field.value)
        return tuple(fields)
    raise AssertionError("reserve_bucket_rows is no longer assigned in fact_templates")


def _renderer_axis_attributes(function_name: str, receiver: str) -> tuple[str, ...]:
    """The measure axes a table builder reads, in source order.

    ``exposure_table`` reads ``exposure.low``/``.expected``/``.high``;
    ``snapshot_table`` reads ``snapshot.paid``/``.outstanding_reserve``/
    ``.incurred``. Recovering them from the tree is how a renamed or added axis
    surfaces as a failing parity assertion rather than as an untested column.
    """
    for node in ast.walk(_fact_templates_source()):
        if not isinstance(node, ast.FunctionDef) or node.name != function_name:
            continue
        axes: list[str] = []
        for inner in ast.walk(node):
            if (
                isinstance(inner, ast.Attribute)
                and isinstance(inner.value, ast.Name)
                and inner.value.id == receiver
                and inner.attr not in axes
            ):
                axes.append(inner.attr)
        return tuple(axes)
    raise AssertionError(f"{function_name} is no longer defined in fact_templates")


def _printed_numeric_paths(review: Any) -> set[str]:
    """Every numeric path the IFR actually prints, walked from a live object.

    Walked over the renderer's own column and axis names — not transcribed —
    and through ``getattr``, so ``BucketAmounts.total`` (a *property*, invisible
    to a ``model_fields`` walk) is collected exactly as the renderer collects it.
    """
    buckets = _renderer_bucket_fields()
    paths: set[str] = set()
    for axis in _renderer_axis_attributes("exposure_table", "exposure"):
        measure = getattr(review.exposure, axis)
        for bucket in buckets:
            getattr(measure, bucket)
            paths.add(f"exposure.{axis}.{bucket}")
    for root in ("recommendation", "booked_snapshot"):
        snapshot = getattr(review, root)
        for axis in _renderer_axis_attributes("snapshot_table", "snapshot"):
            measure = getattr(snapshot, axis)
            for bucket in buckets:
                getattr(measure, bucket)
                paths.add(f"{root}.{axis}.{bucket}")
    for scalar in EXPECTED_SCALAR_PATHS:
        getattr(review, scalar)
        paths.add(scalar)
    return paths


def _all_resolved(classes: dict[str, str]) -> dict[str, str]:
    """Every non-derived row promoted to a confirmed class."""
    return {
        path: value if value == DERIVED else "LEGAL_BINDING"
        for path, value in classes.items()
    }


class TestFigureMap:
    """The inventory itself, pinned rather than described."""

    def test_the_map_is_exactly_the_pinned_inventory(self) -> None:
        """m24-84: a re-classified figure cannot re-classify its own oracle."""
        assert IFR_FIGURE_CLASSES == EXPECTED_FIGURE_CLASSES
        assert len(EXPECTED_FIGURE_CLASSES) == 38
        assert IFR_DERIVED_INPUTS == EXPECTED_DERIVED_INPUTS

    def test_every_derived_key_states_its_inputs_and_vice_versa(self) -> None:
        """A DERIVED row with no derivation would default to confirmed."""
        derived = {
            path
            for path, value in IFR_FIGURE_CLASSES.items()
            if value == DERIVED_FIGURE_CLASS
        }
        assert derived == set(IFR_DERIVED_INPUTS)
        assert len(derived) == 15
        for path, inputs in IFR_DERIVED_INPUTS.items():
            assert inputs, f"{path} states an empty input set"
            for source in inputs:
                assert source in IFR_FIGURE_CLASSES, (
                    f"{path} derives from {source}, which is not a printed figure"
                )

    def test_only_two_classes_count_as_confirmed(self) -> None:
        expected_confirmed = frozenset({"LEGAL_BINDING", "PRIMARY_SOURCE_LITERAL"})
        assert expected_confirmed == CONFIRMED_FIGURE_CLASSES
        assert UNCONFIRMED not in CONFIRMED_FIGURE_CLASSES
        assert DERIVED_FIGURE_CLASS not in CONFIRMED_FIGURE_CLASSES


class TestRendererPathParity:
    """The map is compared to what the renderer prints, never to a transcript."""

    def test_the_printed_path_set_equals_the_map(self) -> None:
        """m24-83: a dropped row leaves a printed figure unclassified."""
        review = _three_event_defense().initial_file_review
        printed = _printed_numeric_paths(review)
        assert printed == set(IFR_FIGURE_CLASSES), (
            "printed but unclassified: "
            f"{sorted(printed - set(IFR_FIGURE_CLASSES))}; "
            "classified but not printed: "
            f"{sorted(set(IFR_FIGURE_CLASSES) - printed)}"
        )

    def test_the_renderer_columns_and_axes_are_the_pinned_ones(self) -> None:
        """The `total` column is the one revision 7's inventory omitted."""
        assert _renderer_bucket_fields() == EXPECTED_BUCKET_FIELDS
        assert _renderer_axis_attributes("exposure_table", "exposure") == (
            EXPECTED_EXPOSURE_AXES
        )
        assert _renderer_axis_attributes("snapshot_table", "snapshot") == (
            EXPECTED_SNAPSHOT_AXES
        )


class TestResolution:
    """Derivation, both arms, and the transitive closure."""

    def test_the_baseline_resolves_unconfirmed(self) -> None:
        assert resolve_authority_status() == AUTHORITY_STATUS_UNCONFIRMED

    def test_an_all_resolved_fixture_reaches_the_confirmed_branch(self) -> None:
        """The positive control: the branch is reachable, not merely absent."""
        assert (
            resolve_authority_status(
                _all_resolved(EXPECTED_FIGURE_CLASSES), EXPECTED_DERIVED_INPUTS
            )
            == AUTHORITY_STATUS_CONFIRMED
        )

    @pytest.mark.parametrize(
        "unresolved",
        [
            "exposure.low.indemnity",
            "booked_snapshot.outstanding_reserve.medical",
            "litigation_budget",
            "adoption_lag_days",
        ],
    )
    def test_one_unconfirmed_leaf_is_enough_to_mix(self, unresolved: str) -> None:
        classes = _all_resolved(EXPECTED_FIGURE_CLASSES)
        classes[unresolved] = UNCONFIRMED
        assert (
            resolve_authority_status(classes, EXPECTED_DERIVED_INPUTS)
            == AUTHORITY_STATUS_UNCONFIRMED
        )

    def test_resolution_is_transitive_to_a_fixed_point(self) -> None:
        """m24-124: `incurred.total` is two levels above the leaf that failed.

        Asserted **per figure**, not on the aggregate status. The aggregate
        answers ``MIXED_OR_UNCONFIRMED`` under a one-level walk too — the
        planted leaf is itself an unconfirmed row, so the aggregate short
        circuits on it and the walk's depth never shows. Only the per-path
        answer separates them: a one-level implementation sees three inputs
        already marked ``DERIVED``, treats "is derived" as "is confirmed", and
        reports ``recommendation.incurred.total`` **confirmed** while a leaf two
        levels beneath it is not.
        """
        classes = _all_resolved(EXPECTED_FIGURE_CLASSES)
        classes["recommendation.paid.medical"] = UNCONFIRMED
        resolved = resolved_figures(classes, EXPECTED_DERIVED_INPUTS)

        assert resolved["recommendation.paid.medical"] is False
        # One level up.
        assert resolved["recommendation.incurred.medical"] is False
        # Two levels up — the one a non-transitive walk gets wrong.
        assert resolved["recommendation.incurred.total"] is False
        # And the sibling total whose own leaves were untouched still resolves,
        # so the failures above are attributable to the planted leaf rather than
        # to a fixture that is unconfirmed everywhere.
        assert resolved["booked_snapshot.incurred.total"] is True
        assert resolved["recommendation.incurred.indemnity"] is True
        assert (
            resolve_authority_status(classes, EXPECTED_DERIVED_INPUTS)
            == AUTHORITY_STATUS_UNCONFIRMED
        )

    def test_a_derived_row_without_inputs_fails_rather_than_defaulting(self) -> None:
        classes = _all_resolved(EXPECTED_FIGURE_CLASSES)
        inputs = dict(EXPECTED_DERIVED_INPUTS)
        del inputs["exposure.low.total"]
        with pytest.raises(AuthorityDerivationError):
            resolve_authority_status(classes, inputs)

    def test_an_unclassified_figure_fails_rather_than_defaulting(self) -> None:
        classes = _all_resolved(EXPECTED_FIGURE_CLASSES)
        del classes["exposure.low.indemnity"]
        with pytest.raises(AuthorityDerivationError):
            resolve_authority_status(classes, EXPECTED_DERIVED_INPUTS)


class TestDerivedValueOnTheObject:
    """The built IFR carries the derivation, not a constant."""

    def test_the_built_review_carries_the_derived_status(self) -> None:
        """m24-28: restoring the hardcode reddens here."""
        review = _three_event_defense().initial_file_review
        assert review.authority_status == AUTHORITY_STATUS_UNCONFIRMED
        assert review.authority_status == resolve_authority_status()

    def test_the_defense_wire_carries_the_same_value(self) -> None:
        wire = defense_lens.defense_wire_projection(
            _three_event_defense(), include_scorer_labels=False
        )
        assert wire["initialFileReview"]["authorityStatus"] == (
            AUTHORITY_STATUS_UNCONFIRMED
        )


@requires_substrate
def test_the_rendered_authority_line_equals_the_derivation(tmp_path: Any) -> None:
    """M5-R40's extraction arm: paper says what the derivation says."""
    seed = parse_case_seed(_seed())
    plan = build_case_plan(seed)
    review = _three_event_defense().initial_file_review
    result = render_document(
        seed=seed,
        cast=plan.cast,
        subtype="RESERVE_WORKSHEET",
        doc_date=review.review_date,
        doc_format="pdf",
        index=0,
        out_path=tmp_path / "ifr.pdf",
        title="Initial File Review",
        reserve_event=review,
    )
    text = extract_text(result.path, result.doc_format)
    assert f"Authority Status: {resolve_authority_status()}" in text
    assert f"Authority Status: {AUTHORITY_STATUS_UNCONFIRMED}" in text
    assert AUTHORITY_STATUS_CONFIRMED not in text
