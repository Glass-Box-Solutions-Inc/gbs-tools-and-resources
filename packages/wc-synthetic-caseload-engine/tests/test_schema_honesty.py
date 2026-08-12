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
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from conftest import requires_substrate
from wc_caseload_engine.manifests import (
    MANIFEST_NAME,
    SUBPOENAED_RECORDS_SUBTYPES,
    generate_case,
)
from wc_caseload_engine.planner import build_case_plan
from wc_caseload_engine.schema_audit import (
    carries_marker,
    field_docstrings,
    marked_fields,
    scenario_source,
)
from wc_caseload_engine.seeds import parse_case_seed
from wc_caseload_engine.taxonomy import effective_taxonomy

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
    # The money spine (AJC-43). Added the moment the classes existed rather
    # than when something went wrong with them: a scenario class outside this
    # tuple is invisible to the guard, so the tuple is the guard's real scope
    # and forgetting to extend it is how the guard dies quietly.
    "WageScenario",
    "EarningsEntry",
    "InKindEntry",
    "RateBasisOverride",
    "BenefitsScenario",
    "SettlementScenario",
    # The medical-history world-truth layer (AJC-60). Every field it adds is
    # byte-inert until M3 gives the ledger a document surface, so this is the
    # largest block of marked fields the guard has ever held — and the whole
    # point is that wiring any one of them up turns this suite red.
    "MedicalHistoryScenario",
    "MedicalConditionEntry",
    "PriorClaimEntry",
    "PriorAwardEntry",
    # Not a scenario class, and included anyway. The three demographic fields
    # AJC-60 adds to the cast profile are read only by the medical-history
    # sampler, which renders nothing yet — exactly the shape this guard exists
    # for. Leaving them outside the tuple would put a marker on three fields
    # with nothing policing it, which is the failure mode the tuple's own
    # comment warns about, one level up.
    "ApplicantProfile",
    # The assertion layer (AJC-61, M2). In scope from the day the classes exist,
    # and — unlike the medical-history block above — none of their fields
    # carries a "not yet honoured" marker: the AJC-61 vocabulary drives the
    # truth manifest's assertions channel, which is output, and the AJC-62/M3
    # fields (event kinds, dispositions, psych/AOE-COE axes, contention
    # documents) parse, validate and populate the internal ledger that the
    # M3 build steps consume — Amendment A1 deliberately freezes them OUT of
    # the 1.0.0 channel, which is a frozen boundary, not an unwired knob.
    "MedicalAssertionsScenario",
    "ContentionEntry",
    "MedicalOpinionEntry",
    "ApportionmentAssertionEntry",
    "ContentionDocumentEntry",
)

@dataclass(frozen=True)
class InertProbe:
    """One marked field's inertness probe, and the ground it has to stand on.

    ``lifecycle`` and ``witness`` exist because of F1, and the failure they fix
    is worth stating plainly: every probe ran at ``target_stage: medical_legal``,
    which emits **zero** subpoenaed-records documents. The discovery fields were
    therefore proven inert on a case containing nothing that could consume them.
    That is our own "a zero that is not earned is not evidence" standard, broken
    by the very guard written to enforce it.

    So a probe now names the stage where its consumer exists *and* the documents
    that must be present for its result to mean anything, and
    ``test_every_probe_runs_where_its_consumer_exists`` checks the second against
    the first. A probe that cannot witness its consumer fails rather than
    quietly reporting inertness.
    """

    plain: dict[str, Any]
    varied: dict[str, Any]
    lifecycle: dict[str, Any]
    witness: frozenset[str]
    profile: dict[str, Any] | None = None
    """Profile block for the *varied* run, when the field under probe lives there.

    Added for AJC-60's three demographic fields. A probe whose field is not on
    ``scenario`` had no way to state itself before, so the alternative was to leave
    those fields outside the sweep — a marker with nothing policing it, which is
    exactly what this suite exists to prevent.
    """


#: The lifecycle block the discovery probes need. ``medical_legal`` — the
#: previous default — plans 0 subpoena packets at this seed; ``discovery`` plans
#: 3. Measured, not assumed: see ``test_the_probe_stage_is_the_one_that_yields``.
_DISCOVERY_LIFECYCLE = {"target_stage": "discovery", "eval_type": "qme"}

#: Two scenario blocks per marked field: one plain, one exercising the field.
#:
#: Hand-written, so it carries its own liveness guard below — a marked field
#: with no probe would otherwise pass by never being tested, which is the
#: vacuous-assertion class this suite has hit three times.
#: Where the medical-history layer's consumer will be.
#:
#: M3 renders past-medical-history, records-review and apportionment sections into the
#: medical-legal reports, so these are the documents each probe below has to stand on.
#: ``APPORTIONMENT_REPORT`` is the one that matters most: it is where a prior award
#: and a nonindustrial contributor would actually be argued.
#:
#: Written from a measurement, not from a guess. The first draft named
#: ``QME_COMPREHENSIVE_REPORT``, which this stage does not plan at all — so all seven
#: probes would have proven inertness on a case that could never consume the field,
#: which is F1's unearned zero exactly. The guard below caught it, which is the guard
#: working rather than an anecdote about it.
_MEDICAL_WITNESS = frozenset(
    {"QME_REPORT_INITIAL", "APPORTIONMENT_REPORT", "TREATING_PHYSICIAN_REPORT_PR4"}
)

_PRIOR_CLAIM = {
    "body_parts": ["lumbar_spine"],
    "date_of_injury": "2015-01-05",
    "resolution_type": "stipulated_award",
    "award": {
        "body_parts": ["lumbar_spine"],
        "pd_percent": 12,
        "award_date": "2016-02-01",
    },
}


def _medical(**block: Any) -> dict[str, Any]:
    return {"medical_history": block}


INERT_PROBES: dict[str, InertProbe] = {
    # ISC-126 emptied this table, and that was the intended end state at the time:
    #   AttorneyScenario.cadence          honoured by ISC-123/124
    #   DiscoveryScenario.subpoena_sets   honoured by ISC-126
    #   DiscoveryScenario.pages_per_set   honoured by ISC-126
    # Each was removed only after the byte-inertness run went red on it, which is
    # the meta-guard doing its job in every case.
    #
    # AJC-60 refills it. The medical-history layer derives a full world-truth
    # ledger and renders none of it: M3 owns every document surface, M4 owns the
    # scorer channel, M5 owns the section 4664 arithmetic. Each entry below is a
    # tripwire on one of those milestones.
    "MedicalHistoryScenario.archetype": InertProbe(
        plain=_medical(),
        varied=_medical(archetype="multimorbid"),
        lifecycle={"target_stage": "medical_legal", "eval_type": "qme"},
        witness=_MEDICAL_WITNESS,
    ),
    "PriorClaimEntry.employer": InertProbe(
        plain=_medical(prior_claims=[_PRIOR_CLAIM]),
        varied=_medical(prior_claims=[{**_PRIOR_CLAIM, "employer": "Ridgeline Foods"}]),
        lifecycle={"target_stage": "medical_legal", "eval_type": "qme"},
        witness=_MEDICAL_WITNESS,
    ),
    # PriorAwardEntry.conclusively_presumed's probe was deleted with its marker
    # in AJC-61: M2 consumes the field (the resolution-keyed presumption default
    # plus explicit override feeds assertion eligibility, the validator and the
    # truth projection), so it is honoured now and the reverse guard would
    # reject a probe whose marker is gone. No replacement probe — that is the
    # rule working, not a gap.
}


def _body(
    case_id: str,
    scenario: dict[str, Any],
    lifecycle: dict[str, Any] | None = None,
    profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "rng_seed": 9900,
        "profile": {"applicant": profile or {}},
        "injury": {
            "type": "specific",
            "date_of_injury": "2022-04-11",
            "body_parts": [{"part": "lumbar_spine"}, {"part": "shoulder"}],
        },
        "lifecycle": lifecycle or {"target_stage": "medical_legal", "eval_type": "qme"},
        "scenario": scenario,
        "documents": {"format_mix": {"pdf": 1.0}},
        "output": {"formats": ["pdf"]},
    }


def _fingerprint(
    scenario: dict[str, Any],
    out_dir: Path,
    lifecycle: dict[str, Any] | None = None,
    profile: dict[str, Any] | None = None,
) -> tuple[str, ...]:
    """Every rendered document's checksum, keyed by filename.

    Compared as a whole rather than by tree digest so a failure names which
    documents moved, not merely that something did.
    """
    seed = parse_case_seed(_body("inert-probe", scenario, lifecycle, profile))
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

def assert_probe_stands_on_ground(field: str, probe: InertProbe) -> None:
    """F1's check, as a function so the planted control can run the real thing.

    Inlining it in the parametrized test would leave the control re-implementing
    the assertion it is supposed to validate, which proves only that two pieces
    of code agree.
    """
    plan = build_case_plan(parse_case_seed(_body("witness", probe.plain, probe.lifecycle)))
    present = sum(1 for doc in plan.documents if doc.subtype in probe.witness)
    assert present, (
        f"{field}'s probe plans no document from {sorted(probe.witness)}. "
        "Inertness proven on a case with nothing to consume the field is "
        "the unearned zero this suite exists to reject — move the probe to "
        "a stage that emits its consumer."
    )


#: A subtype no discovery-stage case can plan: it asserts an operation happened,
#: and the probe body seeds no surgery. Canonical, so the control cannot pass by
#: naming a key the taxonomy has never heard of — which would make it a typo
#: test rather than a witness test.
UNREACHABLE_WITNESS = "OPERATIVE_HOSPITAL_RECORDS"


class TestEveryProbeStandsOnGround:
    """F1. An inertness result is only worth what its case can consume.

    These are the guards that would have caught the original defect, and they
    are deliberately cheap plan-level checks so they run on every field rather
    than only the ones someone remembered to look at.

    ``INERT_PROBES`` is empty, which is the intended end state — so the
    parametrized check below runs **zero times**, and on its own its
    red-capability would rest on reading it. That is exactly the class F1
    existed to replace, one level up. The planted control underneath executes
    the real function against a probe whose consumer cannot appear.
    """

    @pytest.mark.parametrize("field", sorted(INERT_PROBES))
    def test_every_probe_runs_where_its_consumer_exists(self, field: str) -> None:
        assert_probe_stands_on_ground(field, INERT_PROBES[field])

    def test_the_witness_check_fails_on_a_probe_that_cannot_witness(self) -> None:
        """The planted control. Zero parametrized runs must not mean zero proof."""
        assert effective_taxonomy().is_canonical(UNREACHABLE_WITNESS), (
            f"{UNREACHABLE_WITNESS} is not a canonical subtype; the control would "
            "pass on a typo rather than on an absent consumer"
        )
        planted = InertProbe(
            plain={},
            varied={"discovery": {"subpoena_sets": 2}},
            lifecycle=_DISCOVERY_LIFECYCLE,
            witness=frozenset({UNREACHABLE_WITNESS}),
        )
        with pytest.raises(AssertionError, match="plans no document from"):
            assert_probe_stands_on_ground("planted.field", planted)

    def test_the_same_check_passes_on_a_probe_that_can(self) -> None:
        """The other half: the control's failure must come from the witness.

        Without this, a check that raised for any input at all would satisfy the
        test above and prove nothing about what it is measuring.
        """
        reachable = InertProbe(
            plain={},
            varied={"discovery": {"subpoena_sets": 2}},
            lifecycle=_DISCOVERY_LIFECYCLE,
            witness=SUBPOENAED_RECORDS_SUBTYPES,
        )
        assert_probe_stands_on_ground("reachable.field", reachable)

    def test_the_probe_stage_is_the_one_that_yields(self) -> None:
        """The measurement behind ``_DISCOVERY_LIFECYCLE``, kept executable.

        ``medical_legal`` was the old default and plans zero packets. If that
        ever stops being true the comment explaining this repair goes stale, so
        it is asserted rather than written down.
        """
        def packets(stage: str) -> int:
            plan = build_case_plan(
                parse_case_seed(
                    _body("stage", {}, {"target_stage": stage, "eval_type": "qme"})
                )
            )
            return sum(
                1 for d in plan.documents if d.subtype in SUBPOENAED_RECORDS_SUBTYPES
            )

        assert packets("medical_legal") == 0, (
            "medical_legal now emits subpoena packets; the F1 repair's premise "
            "has changed and its comment is now wrong"
        )
        assert packets("discovery") > 0

    def test_the_medical_probe_stage_yields_its_witness(self) -> None:
        """AJC-60's own version of the measurement above, kept executable.

        Seven probes stand on ``QME_COMPREHENSIVE_REPORT`` because that is where M3
        will render the past-medical-history section. If the stage stops emitting it,
        every one of those probes silently becomes an unearned zero — inertness proven
        on a case with nothing that could ever consume the field.
        """
        plan = build_case_plan(
            parse_case_seed(
                _body(
                    "medical-witness",
                    {"medical_history": {}},
                    {"target_stage": "medical_legal", "eval_type": "qme"},
                )
            )
        )
        assert any(doc.subtype in _MEDICAL_WITNESS for doc in plan.documents), (
            f"no document from {sorted(_MEDICAL_WITNESS)} is planned at this stage; "
            "the medical-history probes are standing on nothing"
        )


class TestMarkedFieldsAreByteInert:
    @pytest.mark.parametrize("field", sorted(INERT_PROBES))
    def test_varying_a_marked_field_changes_no_output_byte(
        self, field: str, tmp_path: Path
    ) -> None:
        probe = INERT_PROBES[field]
        plain, varied, lifecycle = probe.plain, probe.varied, probe.lifecycle
        before = _fingerprint(plain, tmp_path / "before", lifecycle)
        after = _fingerprint(varied, tmp_path / "after", lifecycle, probe.profile)
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
