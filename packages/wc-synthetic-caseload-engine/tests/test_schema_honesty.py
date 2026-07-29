"""ISC-137 — the schema's prose cannot outrun the schema's behaviour.

Three of five findings in the PR #25 review were code-and-prose disagreements,
one of them a schema field documented as driving output that drove nothing.
This is the mechanical answer to that class.

The direction of the failure is the point. When a Phase-3b field gets wired up,
its byte-inertness assertion here starts failing, and the only way back to green
is to delete the "not yet honoured" marker from its docstring — the exact edit
that gets forgotten. The guard does not check that the prose was updated; it
makes stale prose impossible to leave behind.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from conftest import requires_substrate
from wc_caseload_engine.manifests import MANIFEST_NAME, generate_case
from wc_caseload_engine.schema_audit import (
    carries_marker,
    field_docstrings,
    marked_fields,
    scenario_source,
)
from wc_caseload_engine.seeds import parse_case_seed

pytestmark = requires_substrate

#: Every scenario model the sweep covers.
SCENARIO_CLASSES = (
    "ScenarioSpec",
    "AdjusterScenario",
    "AttorneyScenario",
    "DiscoveryScenario",
    "PageRange",
    "TreatmentScenario",
    "DiagnosticsScenario",
    "DiagnosticEntry",
)

#: Two scenario blocks per marked field: one plain, one exercising the field.
#:
#: Hand-written, so it carries its own liveness guard below — a marked field
#: with no probe would otherwise pass by never being tested, which is the
#: vacuous-assertion class this suite has hit three times.
INERT_PROBES: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {
    "DiscoveryScenario.subpoena_sets": ({}, {"discovery": {"subpoena_sets": 6}}),
    "DiscoveryScenario.pages_per_set": (
        {},
        {"discovery": {"pages_per_set": {"min": 300, "max": 400}}},
    ),
    # AttorneyScenario.cadence had a probe here until ISC-123/124 honoured it.
    # The guard removed it: the byte-inertness run reported that varying the
    # field moved 35 documents and named the docstring to correct. That is the
    # meta-guard's whole purpose, and it fired without anyone remembering to
    # look.
}


def _body(case_id: str, scenario: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "rng_seed": 9900,
        "injury": {
            "type": "specific",
            "date_of_injury": "2022-04-11",
            "body_parts": [{"part": "lumbar_spine"}, {"part": "shoulder"}],
        },
        "lifecycle": {"target_stage": "medical_legal", "eval_type": "qme"},
        "scenario": scenario,
        "documents": {"format_mix": {"pdf": 1.0}},
        "output": {"formats": ["pdf"]},
    }


def _fingerprint(scenario: dict[str, Any], out_dir: Path) -> tuple[str, ...]:
    """Every rendered document's checksum, keyed by filename.

    Compared as a whole rather than by tree digest so a failure names which
    documents moved, not merely that something did.
    """
    seed = parse_case_seed(_body("inert-probe", scenario))
    generate_case(seed, out_dir, case_number=1)
    manifest = json.loads((out_dir / seed.case_id / MANIFEST_NAME).read_text())
    return tuple(
        f"{entry['filename']}:{entry['md5Checksum']}" for entry in manifest["documents"]
    )


class TestTheMarkerSweepIsWellFormed:
    def test_the_sweep_finds_the_classes_it_names(self) -> None:
        source = scenario_source()
        for class_name in SCENARIO_CLASSES:
            assert field_docstrings(source, class_name) is not None

    def test_every_marked_field_has_an_inertness_probe(self) -> None:
        """A marked field with no probe would pass by never being tested."""
        marked = set(marked_fields(scenario_source(), SCENARIO_CLASSES))
        missing = sorted(marked - set(INERT_PROBES))
        assert not missing, (
            f"fields documented as 'not yet honoured' with no inertness probe: {missing}. "
            "Add one, or remove the marker if the field is now honoured."
        )

    def test_every_probe_targets_a_still_marked_field(self) -> None:
        """The reverse: a probe for a field whose marker is gone is stale."""
        marked = set(marked_fields(scenario_source(), SCENARIO_CLASSES))
        stale = sorted(set(INERT_PROBES) - marked)
        assert not stale, (
            f"inertness probes for fields that no longer claim to be inert: {stale}. "
            "The field is honoured now — delete its probe."
        )

    def test_the_sweep_currently_finds_something(self) -> None:
        """Guard against a regex that silently stops matching.

        This assertion is expected to *fail* once Phase 3b honours the last
        marked field, at which point it should be deleted along with the
        markers. That is the intended lifecycle, not a defect.
        """
        assert marked_fields(scenario_source(), SCENARIO_CLASSES), (
            "no field carries the marker — if that is genuinely true, delete this "
            "test and the INERT_PROBES table with it"
        )


class TestMarkedFieldsAreByteInert:
    @pytest.mark.parametrize("field", sorted(INERT_PROBES))
    def test_varying_a_marked_field_changes_no_output_byte(
        self, field: str, tmp_path: Path
    ) -> None:
        plain, varied = INERT_PROBES[field]
        before = _fingerprint(plain, tmp_path / "before")
        after = _fingerprint(varied, tmp_path / "after")
        assert before == after, (
            f"{field} is documented as 'not yet honoured' but changing it moved "
            f"{sum(1 for a, b in zip(before, after, strict=False) if a != b)} document(s). "
            "Delete the marker from its docstring — the field is honoured now."
        )

    def test_the_probe_can_detect_a_change_at_all(self, tmp_path: Path) -> None:
        """Anti-vacuity: a fingerprint that never varies would pass everything.

        Both sides state a value. The first version compared ``{}`` against
        ``negligent`` and failed, because this seed *derives* negligent — so the
        two cases were identical and the control proved nothing. Exactly the
        coincidence that hid the Phase-1 critical, caught here by the guard
        whose whole job is to notice when a probe has stopped probing.
        """
        attentive = _fingerprint({"adjuster": {"diligence": "attentive"}}, tmp_path / "att")
        negligent = _fingerprint({"adjuster": {"diligence": "negligent"}}, tmp_path / "neg")
        assert attentive != negligent, (
            "varying a genuinely honoured field moved no bytes, so the inertness "
            "assertions above cannot fail and prove nothing"
        )


class TestThePlantedControlGoesRed:
    """The guard must catch a marker on a field that does something."""

    def test_a_marker_planted_on_an_honoured_field_is_detected(self) -> None:
        source = scenario_source()
        original = field_docstrings(source, "AdjusterScenario")["diligence"]
        assert not carries_marker(original), (
            "diligence already claims to be unhonoured; the control is meaningless"
        )

        planted = source.replace(
            '    diligence: Literal["attentive", "ordinary", "negligent"] | None = None\n'
            '    """``None`` means *derive it* on the ``facts:`` namespace."""',
            '    diligence: Literal["attentive", "ordinary", "negligent"] | None = None\n'
            '    """``None`` means *derive it*. Not yet honoured."""',
            1,
        )
        assert planted != source, "the planted control did not apply; update its anchor"

        marked = marked_fields(planted, ("AdjusterScenario",))
        assert "AdjusterScenario.diligence" in marked, (
            "the sweep did not notice a marker planted on an honoured field"
        )

    @pytest.mark.parametrize(
        "text",
        [
            "Not yet honoured.",
            "not yet honored",  # US spelling
            "accepted and validated,\n    not yet honoured — see ISC-126",
        ],
    )
    def test_the_marker_matches_its_real_spellings(self, text: str) -> None:
        assert carries_marker(text)

    @pytest.mark.parametrize(
        "text",
        ["honoured by the planner", "This field is honoured.", "nothing to see"],
    )
    def test_the_marker_does_not_match_ordinary_prose(self, text: str) -> None:
        assert not carries_marker(text)


class TestHonouredFieldsCarryNoMarker:
    @pytest.mark.parametrize(
        "field",
        [
            "AdjusterScenario.diligence",
            "TreatmentScenario.status",
            "TreatmentScenario.providers",
            "ScenarioSpec.surgery",
        ],
    )
    def test_a_field_that_moves_bytes_makes_no_inertness_claim(self, field: str) -> None:
        class_name, _, attribute = field.partition(".")
        doc = field_docstrings(scenario_source(), class_name).get(attribute, "")
        assert not carries_marker(doc), (
            f"{field} is honoured but its docstring says otherwise"
        )


def _digest(values: tuple[str, ...]) -> str:
    """Stable digest of a fingerprint, for failure messages."""
    return hashlib.md5("|".join(values).encode(), usedforsecurity=False).hexdigest()
