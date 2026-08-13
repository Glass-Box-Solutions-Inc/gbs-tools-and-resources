"""AJC-62 (M3) — Part 3 stream, semantic-key, knob, and M2-preservation gates.

The R77 step-3 slice of the R70 gate inventory: the exact 34-family
``medical-story`` registry, the R45 canonical semantic-key grammar, the
R48-R58 knob provenance/exactness surface, and the R62/R70 proof that the new
``derive_medical_assertion_plan()`` seam consumes every M2 stream
byte-identically. Later steps EXTEND this module (PTP remodel, adoption,
contest, revision, percentage, date-band, IMR, render-key, cohort, TZ/hash
gates land with their producers); nothing here may be weakened when they do.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import copy
import datetime as dt
import typing
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest
import yaml

from assertion_cohort import (
    M2_APPORTIONMENT_ORACLE_FIELDS,
    M2_CONTENTION_ORACLE_FIELDS,
    M2_OPINION_ORACLE_FIELDS,
    MEASURED_ASSERTION_QUALITY_COUNTS,
    MEASURED_CONTENTION_FAMILY_COUNTS,
    MEASURED_ELIGIBLE_COUNTS,
    MEASURED_LEDGER_DIGESTS,
    MEASURED_M2_STREAM_TRACE_DIGESTS,
    _CountingRandom,
    _digest,
    build_cohort,
    cohort_seed_body,
)
from wc_caseload_engine import fact_templates as fact_templates_module
from wc_caseload_engine import medical_assertions as assertion_module
from wc_caseload_engine import renderer as renderer_module
from wc_caseload_engine.manifests import generate_case
from wc_caseload_engine.medical_assertions import (
    ASSERTION_RNG_FAMILIES,
    ASSERTION_RNG_NAMESPACE,
    COMMON_NONINDUSTRIAL_PERCENTAGES,
    GRANULAR_NONINDUSTRIAL_PERCENTAGES,
    MEDICAL_STORY_ASSERTION_LOOP_FAMILIES,
    MEDICAL_STORY_HASH_SEEDS,
    MEDICAL_STORY_KNOBS,
    MEDICAL_STORY_REPEAT_GENERATIONS,
    MEDICAL_STORY_RNG_FAMILIES,
    MEDICAL_STORY_RNG_NAMESPACE,
    MEDICAL_STORY_TZ_MATRIX,
    AssertionKnob,
    AssertionTrace,
    ContestPath,
    DefenseContestTheory,
    MedicalAssertionError,
    OpinionRevisionKind,
    canonical_story_key,
    derive_medical_assertion_plan,
    derive_medical_assertions,
)
from wc_caseload_engine.medical_history import derive_medical_history
from wc_caseload_engine.medical_story import (
    MedicalUrPlan,
    resolve_imr_application_content,
)
from wc_caseload_engine.planner import build_case_plan
from wc_caseload_engine.seeds import (
    derive_seed,
    parse_case_seed,
    parse_caseload_spec,
)

_RENDER_KEY_FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "medical_story_render_key_pair.yaml"
)
_IMR_FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "medical_story_imr_matrix.yaml"
)

#: An INDEPENDENT literal copy of the R46 registry — never imported from
#: production, so a production edit and this oracle must both move for the
#: gate to stay green. Complete and closed for AJC-62.
EXPECTED_MEDICAL_STORY_FAMILIES: tuple[str, ...] = (
    "advocacy-incidence",
    "advocacy-bundle-size",
    "applicant-psych-framing",
    "ptp-aoe-coe-finding",
    "ptp-psych-classification",
    "qme-ame-indeterminate-disposition",
    "qme-ame-responsive-adoption",
    "defense-contest-incidence",
    "applicant-contest-incidence",
    "completion-incidence",
    "contest-path",
    "defense-theory-count",
    "defense-theory-selection",
    "revision-kind",
    "revision-percentage-register",
    "revision-percentage-value",
    "advocacy-lead",
    "objection-lag",
    "supplemental-request-lag",
    "supplemental-report-lag",
    "deposition-lag",
    "ur-decision",
    "imr-request",
    "imr-outcome",
    "imr-application-lag",
    "imr-decision-lag",
    "imr-field-occupancy",
    "imr-field-count",
    "imr-rebuttal-substance",
    "document-format",
    "document-render",
    "document-scan",
    "document-pdf-id",
    "document-doctrine",
)

#: Which R46 families the frozen M2 cohort positively exercises TODAY.
#:
#: R65's final form requires all 34 families observed across the cohort plus
#: focused render fixtures — a declared-but-unexercised family is a test
#: defect. This literal is the ratchet that forces each step to expand it
#: with exactly what the frozen cohort then observes, or go red.
#:
#: R77 step 5 landed the contention loop, and the frozen cohort now
#: exercises seventeen loop families beyond step 4's two — measured from a
#: completed cohort run (``.venv/bin/python tests/assertion_cohort.py``),
#: never predicted:
#:
#:   ptp-aoe-coe-finding / qme-ame-indeterminate-disposition — step 4's two,
#:       unchanged;
#:   advocacy-incidence / advocacy-bundle-size / advocacy-lead — sampled
#:       standalone advocacy over every R28-eligible pair (R52), each letter
#:       dated through its advocacy-lead band draw (R56);
#:   defense-contest-incidence / applicant-contest-incidence /
#:       completion-incidence / contest-path — the R29/R30 decision table
#:       firing opportunities and selecting ContestPaths (R50);
#:   defense-theory-count / defense-theory-selection — sampled defense
#:       chains drawing their ordered theory tuples (R51);
#:   objection-lag / supplemental-request-lag / supplemental-report-lag /
#:       deposition-lag — the four contest date bands (R56);
#:   qme-ame-responsive-adoption — step 4's channel, cohort-eligible now
#:       that sampled advocacy creates R38 qualifying communications;
#:   revision-kind / revision-percentage-register /
#:       revision-percentage-value — step 4's response consumers, exercised
#:       by the sampled supplemental and deposition opinions.
#:
#: Still awaiting later producers or fixtures (fifteen families):
#:
#:   applicant-psych-framing, ptp-psych-classification — need a world
#:       condition classified compensable_consequence; no frozen cohort seed
#:       authors one and M1 samples none, so the render/psych fixtures
#:       (steps 7-8) supply their positive exercise;
#:   the eight UR/IMR families — step 8's derivation;
#:   the five document families — step 9's rendering.
#:
#: Step 9 retains this cohort-only pin and separately requires the cohort plus
#: focused witnesses to equal the full registry.
EXERCISED_STORY_FAMILIES_TODAY: frozenset[str] = frozenset(
    {
        "ptp-aoe-coe-finding",
        "qme-ame-indeterminate-disposition",
        "advocacy-incidence",
        "advocacy-bundle-size",
        "advocacy-lead",
        "defense-contest-incidence",
        "applicant-contest-incidence",
        "completion-incidence",
        "contest-path",
        "defense-theory-count",
        "defense-theory-selection",
        "objection-lag",
        "supplemental-request-lag",
        "supplemental-report-lag",
        "deposition-lag",
        "qme-ame-responsive-adoption",
        "revision-kind",
        "revision-percentage-register",
        "revision-percentage-value",
    }
)

#: The step-3 trace/digest witnesses: one ordinary cell case and the pinned
#: suppression-collision case.
_TRACE_WITNESS_INDICES = (3, 5760)


def _render_key_seed_pair() -> tuple[Any, Any]:
    """R67's one seed and its sole permitted in-memory insertion clone."""
    payload = yaml.safe_load(_RENDER_KEY_FIXTURE.read_text(encoding="utf-8"))
    assert payload["caseload_id"] == "medical-story-render-key-pair"
    assert len(payload["cases"]) == 1
    base_body = payload["cases"][0]
    assert (base_body["case_id"], base_body["rng_seed"]) == (
        "render-key-stability",
        620401,
    )

    inserted_body = copy.deepcopy(base_body)
    assertions = inserted_body["scenario"]["medical_assertions"]
    assert "contention_documents" not in assertions
    assertions["contention_documents"] = [
        {
            "id": "cdoc-90",
            "document_kind": "advocacy",
            "actor_party": "defense",
            "target_medical_opinion_id": "opn-01",
            "spoken_contention_ids": ["ctn-02"],
            "subtype": "ADVOCACY_LETTERS_QME",
            "doc_date": "2024-08-20",
        }
    ]
    base = parse_case_seed(base_body)
    inserted = parse_case_seed(inserted_body)
    assert base.case_id == inserted.case_id == "render-key-stability"
    assert base.rng_seed == inserted.rng_seed == 620401
    return base, inserted


# ---------------------------------------------------------------------------
# R46 — the exact 34-family registry
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_medical_story_stream_registry_is_exact_complete_and_namespaced(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """R70's complete closed registry and positive construction witness.

    The registry equals the independent R46 literal in exact order under the
    one exact namespace; family names are disjoint from every M2 family; an
    undeclared constructed family fails closed at the helper. The frozen M2
    cohort retains its independent nineteen-family ratchet, then focused psych,
    UR/IMR, and render fixtures positively construct the remaining families.
    Their union must equal the literal R46 copy: a declared but unexercised
    family therefore fails rather than entering the registry invisibly.
    """
    assert MEDICAL_STORY_RNG_NAMESPACE == "medical-story"
    assert MEDICAL_STORY_RNG_FAMILIES == EXPECTED_MEDICAL_STORY_FAMILIES
    assert len(MEDICAL_STORY_RNG_FAMILIES) == 34
    assert len(set(MEDICAL_STORY_RNG_FAMILIES)) == 34
    # The loop/optional split is structural (R44): the 21 assertion-loop
    # families are exactly the registry minus the eight UR/IMR and five
    # document-render families.
    assert frozenset(
        EXPECTED_MEDICAL_STORY_FAMILIES[:21]
    ) == MEDICAL_STORY_ASSERTION_LOOP_FAMILIES
    assert frozenset(EXPECTED_MEDICAL_STORY_FAMILIES[21:]) == {
        "ur-decision",
        "imr-request",
        "imr-outcome",
        "imr-application-lag",
        "imr-decision-lag",
        "imr-field-occupancy",
        "imr-field-count",
        "imr-rebuttal-substance",
        "document-format",
        "document-render",
        "document-scan",
        "document-pdf-id",
        "document-doctrine",
    }
    # No name collision with the M2 registry — a shared name is how a loop
    # decision would quietly consume an existing stream.
    assert set(MEDICAL_STORY_RNG_FAMILIES).isdisjoint(set(ASSERTION_RNG_FAMILIES))

    # An undeclared constructed family is an implementation failure, not a
    # warning: the helper refuses it before any stream exists.
    seed = parse_case_seed(cohort_seed_body(3))
    with pytest.raises(MedicalAssertionError, match="unknown medical-story rng family"):
        assertion_module._medical_story_rng(
            seed, "not-a-registered-family", ("case", seed.case_id)
        )

    observed: set[str] = set()
    original_story_seed = assertion_module._medical_story_seed

    def recording_story_seed(seed_obj: Any, family: str, semantic_key: Any) -> int:
        observed.add(family)
        return original_story_seed(seed_obj, family, semantic_key)

    monkeypatch.setattr(
        assertion_module, "_medical_story_seed", recording_story_seed
    )

    # The fixed 6,000-case cohort remains an independently pinned nineteen
    # families; the focused witnesses below close only the fifteen known gaps.
    result = build_cohort()
    assert result.story_families_seen == EXERCISED_STORY_FAMILIES_TODAY
    observed.update(result.story_families_seen)

    render_payload = yaml.safe_load(_RENDER_KEY_FIXTURE.read_text(encoding="utf-8"))
    render_spec = parse_caseload_spec(render_payload)
    assert [(case.case_id, case.rng_seed) for case in render_spec.cases] == [
        ("render-key-stability", 620401)
    ]
    render_seed = render_spec.cases[0]

    # The two psych draw sites are focused at their actual production seams.
    # Their keys are literal R45 identities, not values discovered from the
    # registry, so deleting either producer removes an observed family.
    c_key = (
        "case",
        render_seed.case_id,
        "contention",
        "explicit",
        "psych-family-focus",
    )
    o_key = (
        "case",
        render_seed.case_id,
        "opinion",
        "explicit",
        "psych-family-focus",
    )
    assertion_module._applicant_psych_framing(render_seed, c_key)
    assertion_module._ptp_psych_classification(render_seed, o_key, c_key)

    # The frozen IMR matrix supplies the natural positive denominators. A
    # clone with only the authored decision removed exercises ur-decision.
    imr_payload = yaml.safe_load(_IMR_FIXTURE.read_text(encoding="utf-8"))
    imr_spec = parse_caseload_spec(imr_payload)
    for seed_obj in imr_spec.cases:
        build_case_plan(seed_obj)
    sampled_imr = next(
        seed_obj
        for seed_obj in imr_spec.cases
        if seed_obj.case_id == "imr-sampled-upheld"
    )
    unstated_ur = sampled_imr.lifecycle.ur_dispute.model_copy(
        update={"decision": None}
    )
    unstated = sampled_imr.model_copy(
        update={
            "case_id": "imr-unstated-decision-family-focus",
            "lifecycle": sampled_imr.lifecycle.model_copy(
                update={"ur_dispute": unstated_ur}
            ),
        }
    )
    assert unstated.lifecycle.ur_dispute.decision is None
    build_case_plan(unstated)

    # Seed 620004 is a literal positive-control witness: both a supporting
    # record count and rebuttal-substance decision are eligible and populated.
    # Without this witness the two conditional families could remain declared
    # forever while every focused fixture missed their branch.
    sparse_seed = render_seed.model_copy(update={"rng_seed": 620004})
    sparse_content = resolve_imr_application_content(
        sparse_seed,
        MedicalUrPlan(
            effective_decision="upheld",
            decision_was_authored=True,
            imr_requested=True,
            imr_was_authored=False,
            effective_imr_outcome="upheld",
        ),
        target_denial_date=dt.date(2024, 8, 1),
        medical_history=derive_medical_history(sparse_seed),
        earlier_record_subtypes=(
            "TREATING_PHYSICIAN_REPORT_PR2",
            "MRI_REPORT",
        ),
        disputed_treatment="lumbar epidural injection",
    )
    assert sparse_content is not None
    assert sparse_content.supporting_record_subtypes
    assert sparse_content.clinical_rebuttal

    # Full generation, not a helper call, constructs format, render, scan,
    # PDF-ID, and doctrine streams from the required one-case render fixture.
    generated = generate_case(render_seed, tmp_path / "render-families")
    assert generated.renders
    assert {render.doc_format for render in generated.renders} >= {
        "pdf",
        "scanned_pdf",
    }
    assert any(render.content_flags for render in generated.renders)

    assert observed == set(EXPECTED_MEDICAL_STORY_FAMILIES)
    # The R70 pre-ID key recorder, attached at step 4 with the first
    # production key sites: no sampled story key carries a ctn/opn/app/cdoc
    # ID atom outside the explicit key forms.
    assert result.story_key_findings == []


def test_inserting_an_unrelated_document_cannot_move_semantic_render_outputs(
    tmp_path: Path,
) -> None:
    """R59/R70: one inserted D cannot perturb surviving R8-governed bytes.

    This is an insertion-controlled invariant, not repeat rendering: both plans
    retain the exact frozen case ID and RNG seed, and the only seed-definition
    delta is one explicit advocacy document. Every document has an R, but only
    R8-governed surfaces use it to drive rendering; ungoverned documents retain
    legacy index salts and are outside this invariant. At least one common
    governed surface must move to a different final index, after which its
    complete rendered bytes still have to match.
    """
    base_seed, inserted_seed = _render_key_seed_pair()
    base_result = generate_case(base_seed, tmp_path / "base")
    inserted_result = generate_case(inserted_seed, tmp_path / "inserted")

    def by_render_key(result: Any) -> dict[str, tuple[Any, Any, bytes]]:
        observed: dict[str, tuple[Any, Any, bytes]] = {}
        for document, render in zip(
            result.plan.documents, result.renders, strict=True
        ):
            key = document.medical_story_render_key
            assert key is not None, (
                f"history-present document {document.index} has no R45 render key"
            )
            canonical = canonical_story_key(key)
            assert canonical not in observed, f"duplicate semantic R key: {canonical}"
            observed[canonical] = (document, render, render.path.read_bytes())
        return observed

    base = by_render_key(base_result)
    inserted = by_render_key(inserted_result)
    common = set(base) & set(inserted)
    assert common, "the insertion left no unrelated semantic document to compare"

    added_advocacy = [
        document
        for document in inserted_result.plan.documents
        if document.contention_surface == "advocacy"
        and document.target_medical_opinion_id == "opn-01"
        and document.spoken_contention_ids == ("ctn-02",)
    ]
    assert len(added_advocacy) == 1
    added_advocacy_key = added_advocacy[0].medical_story_render_key
    assert added_advocacy_key is not None
    assert added_advocacy_key[2] == "contention_document"
    assert added_advocacy_key == (
        "case",
        "render-key-stability",
        "contention_document",
        "advocacy",
        "defense",
        None,
        (
            "case",
            "render-key-stability",
            "opinion",
            "explicit",
            "opn-01",
        ),
        (
            (
                "case",
                "render-key-stability",
                "contention",
                "explicit",
                "ctn-02",
            ),
        ),
    )
    assert canonical_story_key(
        added_advocacy_key
    ) not in base

    qme_key_prefix = (
        "case",
        "render-key-stability",
        "contention_document",
    )
    base_qme = next(
        document
        for document, _render, _payload in base.values()
        if document.subtype == "QME_COMPREHENSIVE_REPORT"
    )
    inserted_qme = next(
        document
        for document, _render, _payload in inserted.values()
        if document.subtype == "QME_COMPREHENSIVE_REPORT"
    )
    assert base_qme.medical_story_render_key is not None
    assert inserted_qme.medical_story_render_key is not None
    assert base_qme.medical_story_render_key[:3] == qme_key_prefix
    assert inserted_qme.medical_story_render_key[:3] == qme_key_prefix

    moved = [
        key for key in common if base[key][0].index != inserted[key][0].index
    ]
    assert moved, "the control insertion moved no common final index"
    for key in sorted(common):
        base_document, base_render, base_bytes = base[key]
        inserted_document, inserted_render, inserted_bytes = inserted[key]
        assert base_document.doc_format == inserted_document.doc_format, key
        assert base_render.doc_format == inserted_render.doc_format, key
        assert base_render.template == inserted_render.template, key
        assert base_render.content_flags == inserted_render.content_flags, key
        assert base_bytes == inserted_bytes, (
            f"semantic document {key} changed after one unrelated insertion: "
            f"index {base_document.index} -> {inserted_document.index}"
        )


def test_semantic_format_replaces_but_does_not_skip_the_legacy_format_draw(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R59 consumes ``format:{index}``, discards it, then uses family R."""
    seed, _inserted = _render_key_seed_pair()
    document = build_case_plan(seed).documents[8]
    assert document.subtype == "QME_COMPREHENSIVE_REPORT"
    assert document.medical_story_render_key is not None

    legacy_seed = derive_seed(seed.rng_seed, "format:8")
    semantic_seed = assertion_module._medical_story_seed(
        seed,
        "document-format",
        (
            "case",
            seed.case_id,
            document.medical_story_render_key,
        ),
    )
    constructed: list[int] = []
    original_random = renderer_module.random.Random

    def recording_random(value: int) -> Any:
        constructed.append(value)
        return original_random(value)

    monkeypatch.setattr(renderer_module.random, "Random", recording_random)
    selected = renderer_module.choose_format(
        seed,
        document.index,
        medical_story_render_key=document.medical_story_render_key,
    )

    assert constructed == [legacy_seed, semantic_seed]
    assert renderer_module._format_from_roll(
        seed.effective_format_mix(), original_random(legacy_seed).random()
    ) == "pdf"
    assert selected == "eml"


# ---------------------------------------------------------------------------
# R45 — semantic-key grammar: structural, pre-ID, canonical
# ---------------------------------------------------------------------------


def test_medical_story_keys_use_pre_id_semantics_and_never_positions_or_indices() -> None:
    """R70's semantic-key gate: the R45 grammar, pinned canonically.

    Every key begins ``("case", case_id, ...)`` — the helper fails closed on
    any other prefix — and the canonical form is byte-pinned for each R45
    identity shape, so a position, index, counter, or object identity cannot
    enter a salt without moving one of these exact strings. ``ctn-*``/
    ``opn-*``/``app-*``/``cdoc-*`` IDs, advancing counters, collection
    positions and final document indices stay out of SAMPLED pre-label keys
    as a construction-site rule (authored explicit IDs are permitted only in
    the explicit forms below); its mechanical recorder is the P4 family
    recorder, which attaches as the step-4-8 consumers introduce production
    key-construction sites.
    """
    seed = parse_case_seed(cohort_seed_body(3))

    # The case prefix is mandatory — R45's first two atoms.
    for bad_key in (
        (),
        ("case",),
        ("contention", "sampled"),
        ("case", "some-other-case", "ur"),
    ):
        with pytest.raises(MedicalAssertionError, match="does not begin"):
            assertion_module._medical_story_seed(seed, "ur-decision", bad_key)

    case_id = seed.case_id
    assert case_id == "cohort-0003"

    # C, sampled — carries the M2 full contention semantic key, never an id.
    c_sampled = (
        "case",
        case_id,
        "contention",
        "sampled",
        (
            "contention",
            "industrial_causation",
            "affirm",
            "cond-00",
            None,
            None,
            None,
            ("kite",),
        ),
    )
    assert canonical_story_key(c_sampled) == (
        f'["case","{case_id}","contention","sampled",'
        '["contention","industrial_causation","affirm","cond-00",'
        'null,null,null,["kite"]]]'
    )

    # C, explicit — the one place an authored explicit ID may appear.
    c_explicit = ("case", case_id, "contention", "explicit", "ctn-01")
    assert canonical_story_key(c_explicit) == (
        f'["case","{case_id}","contention","explicit","ctn-01"]'
    )

    # O, sampled base — role/stage/date plus the sorted relevant C keys,
    # embedded as key TUPLES (nested arrays), never as assigned opinion IDs.
    o_base = (
        "case",
        case_id,
        "opinion",
        "sampled_base",
        "qme",
        "final",
        dt.date(2025, 6, 1),
        (c_sampled,),
    )
    assert canonical_story_key(o_base) == (
        f'["case","{case_id}","opinion","sampled_base","qme","final",'
        f'"2025-06-01",[["case","{case_id}","contention","sampled",'
        '["contention","industrial_causation","affirm","cond-00",'
        'null,null,null,["kite"]]]]]'
    )

    # U — dates become ISO, booleans stay JSON booleans, body parts arrive
    # pre-sorted as R45 composes them.
    u_key = (
        "case",
        case_id,
        "ur",
        dt.date(2024, 3, 1),
        True,
        ("lumbar_spine", "shoulder"),
    )
    assert canonical_story_key(u_key) == (
        f'["case","{case_id}","ur","2024-03-01",true,'
        '["lumbar_spine","shoulder"]]'
    )

    # Tuples and lists are NEVER reordered; sets and frozensets ALWAYS are.
    ordered = ("case", case_id, "probe", ("b", "a"))
    assert canonical_story_key(ordered) == (
        f'["case","{case_id}","probe",["b","a"]]'
    )
    unordered = ("case", case_id, "probe", frozenset({"b", "a"}))
    assert canonical_story_key(unordered) == (
        f'["case","{case_id}","probe",["a","b"]]'
    )
    # A mapping appears only after sorting its items by normalized key.
    mapped = ("case", case_id, "probe", {"z": 1, "a": 2})
    assert canonical_story_key(mapped) == (
        f'["case","{case_id}","probe",[["a",2],["z",1]]]'
    )

    # Floats, datetimes, and arbitrary objects are forbidden atoms — a repr
    # carries a memory address, a float carries platform formatting, a
    # datetime carries a clock.
    for forbidden in (
        ("case", case_id, 0.5),
        ("case", case_id, dt.datetime(2024, 3, 1, 12, 0)),
        ("case", case_id, object()),
        ("case", case_id, b"bytes"),
    ):
        with pytest.raises(MedicalAssertionError, match="forbid"):
            canonical_story_key(forbidden)

    # Canonicalization is ASCII-stable: non-ASCII content is escaped, never
    # re-encoded differently per locale.
    accented = ("case", case_id, "probe", "café")
    assert canonical_story_key(accented) == (
        f'["case","{case_id}","probe","caf\\u00e9"]'
    )


def test_medical_story_rng_streams_are_fresh_independent_and_gated() -> None:
    """R44 unit surface: fresh per-construction streams under the exact
    namespace, seed-disjoint from M1/M2, and fail-closed on both gates."""
    seed = parse_case_seed(cohort_seed_body(3))
    key = ("case", seed.case_id, "gate-probe")

    # Same family and key: an identical, reproducible stream — and a FRESH
    # instance per call, so consuming one cannot advance the other.
    first = assertion_module._medical_story_rng(seed, "ur-decision", key)
    second = assertion_module._medical_story_rng(seed, "ur-decision", key)
    assert first is not second
    sequence = [first.random() for _ in range(4)]
    assert [second.random() for _ in range(4)] == sequence

    # Different family, different key, or different namespace: different seed.
    seeds = {
        assertion_module._medical_story_seed(seed, family, key)
        for family in ("ur-decision", "imr-request", "document-render")
    }
    assert len(seeds) == 3
    assert assertion_module._medical_story_seed(
        seed, "ur-decision", key
    ) != assertion_module._medical_story_seed(
        seed, "ur-decision", ("case", seed.case_id, "other-probe")
    )
    from wc_caseload_engine.seeds import derive_seed

    canonical = canonical_story_key(key)
    story_seed = assertion_module._medical_story_seed(seed, "ur-decision", key)
    assert story_seed == derive_seed(
        seed.rng_seed, f"medical-story:ur-decision:{canonical}"
    )
    for foreign_namespace in ("medical-assertions", "medical"):
        assert story_seed != derive_seed(
            seed.rng_seed, f"{foreign_namespace}:ur-decision:{canonical}"
        )

    # Gate half: no helper call is permitted without medical history; the 21
    # assertion-loop families additionally require the assertions block, while
    # UR/IMR and document-render families may run history-only (R44).
    history_only = cohort_seed_body(3)
    history_only["scenario"].pop("medical_assertions")
    history_only_seed = parse_case_seed(history_only)
    allowed = assertion_module._medical_story_rng(
        history_only_seed, "ur-decision", ("case", history_only_seed.case_id)
    )
    assert 0.0 <= allowed.random() < 1.0
    with pytest.raises(MedicalAssertionError, match="assertion-loop family"):
        assertion_module._medical_story_rng(
            history_only_seed, "contest-path", ("case", history_only_seed.case_id)
        )

    bare = cohort_seed_body(3)
    bare["scenario"] = {}
    bare_seed = parse_case_seed(bare)
    with pytest.raises(MedicalAssertionError, match="medical-story gate"):
        assertion_module._medical_story_rng(
            bare_seed, "ur-decision", ("case", bare_seed.case_id)
        )


# ---------------------------------------------------------------------------
# R62/R70 — M2 stream preservation through the new plan seam
# ---------------------------------------------------------------------------


def _record_m2_streams(index: int) -> tuple[Any, AssertionTrace, list[tuple[str, str, int]]]:
    """Derive one case through ``derive_medical_assertion_plan`` recording the
    ordered (family, complete salt, within-stream draw count) construction
    trace of every ``medical-assertions`` stream, byte-transparently."""
    body = cohort_seed_body(index)
    seed = parse_case_seed(body)
    history = derive_medical_history(seed)
    original = assertion_module._assertion_rng
    live: list[tuple[str, str, _CountingRandom]] = []

    def recording(seed_obj: Any, family: str, stable_key: str) -> Any:
        constructed = original(seed_obj, family, stable_key)
        counting = _CountingRandom()
        counting.setstate(constructed.getstate())
        live.append(
            (family, f"{ASSERTION_RNG_NAMESPACE}:{family}:{stable_key}", counting)
        )
        return counting

    assertion_module._assertion_rng = recording
    try:
        trace = AssertionTrace()
        plan = derive_medical_assertion_plan(seed, history, trace=trace)
    finally:
        assertion_module._assertion_rng = original
    return plan, trace, [(family, salt, rng.draws) for family, salt, rng in live]


@pytest.mark.slow
def test_m2_baseline_stream_calls_ids_counts_and_digests_are_byte_identical() -> None:
    """R70's M2-stream gate: family names, complete semantic salts,
    construction counts, within-stream draw counts, base ctn/opn/app IDs, the
    R62 field-projected payload and ``MEASURED_LEDGER_DIGESTS`` — all read
    from ``AssertionTrace.m2_baseline_ledger`` through the new
    ``derive_medical_assertion_plan()`` seam and byte-identical to the frozen
    M2 recording.

    Two instruments, deliberately overlapping: the ledger digests were pinned
    PRE-M3 (any draw inserted into an M2 stream moves the sampled payload and
    reddens them), and the stream-trace digests — pinned at step 3 under that
    separately proven byte-identity — additionally see a construction the
    payload cannot: a fresh stream created under an M2 family or namespace by
    later M3 code whose private draws leave the M2 payload intact (the m20-10
    failure shape).
    """
    result = build_cohort()
    # The R62 payload digests, computed from m2_baseline_ledger with the
    # literal M2 field allowlists, equal the frozen pre-M3 pins — no pin may
    # be re-recorded to accommodate M3; a mismatch is an implementation
    # defect (R62).
    assert result.ledger_digests == MEASURED_LEDGER_DIGESTS
    # The construction/draw traces equal their step-3 recordings.
    assert result.stream_trace_digests == MEASURED_M2_STREAM_TRACE_DIGESTS
    # …and the existing M2 counters stand unchanged beside them (R70 names
    # the counters in this gate; the pinned-reproduction guard owns the full
    # counter surface, this node re-checks the load-bearing three so it is a
    # complete witness on its own).
    assert {
        model: dict(counts) for model, counts in result.quality_counts.items()
    } == MEASURED_ASSERTION_QUALITY_COUNTS
    assert dict(result.contention_family_counts) == MEASURED_CONTENTION_FAMILY_COUNTS
    assert dict(result.eligible_counts) == MEASURED_ELIGIBLE_COUNTS

    for index in _TRACE_WITNESS_INDICES:
        plan, trace, streams = _record_m2_streams(index)
        baseline = trace.m2_baseline_ledger
        assert baseline is not None
        assert plan.ledger is not None
        # Step-5 shape (evolved from step 3's "no bindings yet"): the plan
        # now carries the loop's bound documents — every ledger opinion is
        # realized (R27) — while the recorded baseline stays the graded M2
        # ledger and every M2 instrument below stays byte-identical.
        realized = {
            binding.medical_opinion_id
            for binding in plan.contention_documents
            if binding.medical_opinion_id is not None
        }
        assert realized == {opinion.id for opinion in plan.ledger.medical_opinions}

        # Every constructed stream lives in the M2 namespace under a
        # registered M2 family; no medical-story stream may be constructed
        # inside the M2 base derivation, and within one derivation every
        # stream is constructed at most once.
        assert streams, "the witness case stopped constructing M2 streams"
        for family, salt, draws in streams:
            assert family in ASSERTION_RNG_FAMILIES, family
            assert salt.startswith("medical-assertions:"), salt
            assert not salt.startswith("medical-story:"), salt
            assert draws >= 0
        salts = [salt for _family, salt, _draws in streams]
        assert len(salts) == len(set(salts))

        # Base ctn/opn/app IDs remain the unbroken 01..N sequences the M2
        # final labeling pass assigns — the sequences later response events
        # must extend, never disturb (R47).
        for collection, prefix in (
            (baseline.contentions, "ctn"),
            (baseline.medical_opinions, "opn"),
            (baseline.apportionment_assertions, "app"),
        ):
            assert [item.id for item in collection] == [
                f"{prefix}-{position:02d}"
                for position in range(1, len(collection) + 1)
            ]

        # The R62 field projection of the baseline reproduces the frozen pin.
        assert _digest(baseline) == MEASURED_LEDGER_DIGESTS[index]

        # Determinism of the trace itself: a second derivation constructs the
        # same streams in the same order with the same draw counts.
        _plan_again, _trace_again, streams_again = _record_m2_streams(index)
        assert streams_again == streams

        # And the compatibility wrapper returns exactly the plan ledger.
        body = cohort_seed_body(index)
        seed = parse_case_seed(body)
        history = derive_medical_history(seed)
        wrapped = derive_medical_assertions(seed, history)
        assert wrapped is not None
        assert wrapped.model_dump() == plan.ledger.model_dump()


def test_m2_oracle_allowlists_are_independent_literals_equal_to_production_v1_tuples() -> None:
    """A1-R9's step-3 obligation: the test-only R62 allowlists stay
    independently literal AND value-identical to the production assertions-v1
    tuples. Production never imports the test constants (A1-R3); the
    coordinated oracle compares the two declarations for exact equality."""
    from wc_caseload_engine import truth_manifest as tm

    assert M2_CONTENTION_ORACLE_FIELDS == tm.ASSERTIONS_V1_CONTENTION_FIELDS
    assert M2_OPINION_ORACLE_FIELDS == tm.ASSERTIONS_V1_MEDICAL_OPINION_FIELDS
    assert (
        M2_APPORTIONMENT_ORACLE_FIELDS
        == tm.ASSERTIONS_V1_APPORTIONMENT_ASSERTION_FIELDS
    )
    # Independence is identity-level: equal values, distinct declarations.
    assert M2_CONTENTION_ORACLE_FIELDS is not tm.ASSERTIONS_V1_CONTENTION_FIELDS
    assert M2_OPINION_ORACLE_FIELDS is not tm.ASSERTIONS_V1_MEDICAL_OPINION_FIELDS
    assert (
        M2_APPORTIONMENT_ORACLE_FIELDS
        is not tm.ASSERTIONS_V1_APPORTIONMENT_ASSERTION_FIELDS
    )
    # The R62 vocabulary ends at quality on every collection.
    for fields in (
        M2_CONTENTION_ORACLE_FIELDS,
        M2_OPINION_ORACLE_FIELDS,
        M2_APPORTIONMENT_ORACLE_FIELDS,
    ):
        assert fields[-1] == "quality"


# ---------------------------------------------------------------------------
# R48-R60 — knob provenance and exact-choice surface
# ---------------------------------------------------------------------------

#: R60's M3 provenance vocabulary — four members, not the six the M2 enum
#: carries. counsel_estimate and counsel_assumed are M2-era gradations and may
#: not tag a medical-story knob.
_M3_PROVENANCE = frozenset({"counsel_confirmed", "counsel_qualitative", "derived", "invented"})

_EXPECTED_KNOB_NAMES = frozenset(
    {
        "P_DEFENSE_CONTEST",
        "P_PTP_INDUSTRIAL_AOE_COE",
        "P_QME_AME_RESPONSIVE_ADOPTION",
        "P_IMR_REQUEST_GIVEN_UPHELD_DENIAL",
        "P_COMMON_PERCENTAGE_REGISTER",
        "P_DEFENSE_CONTEST_OUTSIDE_R30",
        "PTP_AOE_COE_COMPLEMENT_WEIGHTS",
        "P_APPLICANT_DIRECT_PSYCH_FRAMING_GIVEN_CONSEQUENCE",
        "P_PTP_DIRECT_PSYCH_CLASSIFICATION_GIVEN_CONSEQUENCE",
        "P_QME_AME_INDETERMINATE_DEFERRED",
        "P_APPLICANT_CONTEST",
        "P_APPLICANT_COMPLETION_REQUEST",
        "ADVERSE_CONTEST_PATH_WEIGHTS",
        "COMPLETION_PATH_WEIGHTS",
        "DEFENSE_THEORY_COUNT_WEIGHTS",
        "DEFENSE_THEORY_WEIGHTS",
        "ADVOCACY_INCIDENCE",
        "ADVOCACY_BUNDLE_SIZE_WEIGHTS",
        "REVISION_KIND_WEIGHTS",
        "COMMON_NONINDUSTRIAL_PERCENTAGES",
        "GRANULAR_NONINDUSTRIAL_PERCENTAGES",
        "ADVOCACY_LEAD_DAYS",
        "OBJECTION_LAG_DAYS",
        "SUPPLEMENTAL_REQUEST_LAG_DAYS",
        "SUPPLEMENTAL_REPORT_LAG_DAYS",
        "DEPOSITION_LAG_DAYS",
        "IMR_APPLICATION_LAG_DAYS",
        "IMR_DECISION_LAG_DAYS",
        "UR_DECISION_WEIGHTS_WHEN_UNSTATED",
        "IMR_OUTCOME_WEIGHTS_WHEN_UNSTATED",
        "IMR_APPLICATION_FIELD_OCCUPANCY",
        "SUPPORTING_RECORD_COUNT_WEIGHTS",
        "MTUS_CITATION_COUNT_WEIGHTS",
        "P_IMR_CASE_SPECIFIC_REBUTTAL",
    }
)


def _assert_no_float(name: str, value: object) -> None:
    """Recursively forbid floats anywhere inside a knob value — every
    probability or weight is an exact Fraction and every structural member an
    int, string, date pair or nested container of those."""
    if isinstance(value, Fraction):
        return
    if isinstance(value, float):
        pytest.fail(f"{name} carries a float component {value!r}; exact values only")
    if isinstance(value, dict):
        for key, item in value.items():
            _assert_no_float(name, key)
            _assert_no_float(name, item)
        return
    if isinstance(value, (tuple, list, set, frozenset)):
        for item in value:
            _assert_no_float(name, item)


def test_every_medical_story_knob_has_value_rationale_source_and_provenance() -> None:
    """R70's provenance gate over R60's registry: every R48-R58 knob present
    by name, carrying an exact float-free value, a nonempty rationale and
    source, and one of R60's four provenance members — with the existing
    P_COMMON_PERCENTAGE_REGISTER object shared BY IDENTITY, never duplicated.
    """
    assert set(MEDICAL_STORY_KNOBS) == _EXPECTED_KNOB_NAMES
    for name, knob in MEDICAL_STORY_KNOBS.items():
        assert isinstance(knob, AssertionKnob), name
        assert knob.rationale.strip(), name
        assert knob.source.strip(), name
        assert knob.provenance in _M3_PROVENANCE, (name, knob.provenance)
        _assert_no_float(name, knob.value)

    # One knob, two registries, zero duplication — and the value is untouched.
    shared = MEDICAL_STORY_KNOBS["P_COMMON_PERCENTAGE_REGISTER"]
    assert shared is assertion_module.P_COMMON_PERCENTAGE_REGISTER
    assert shared is assertion_module.ASSERTION_KNOBS["P_COMMON_PERCENTAGE_REGISTER"]
    assert shared.value == Fraction(17, 20)

    # The two percentage pools are held by identity too — the knob registry
    # documents the module tuples, it does not fork them.
    assert (
        MEDICAL_STORY_KNOBS["COMMON_NONINDUSTRIAL_PERCENTAGES"].value
        is COMMON_NONINDUSTRIAL_PERCENTAGES
    )
    assert (
        MEDICAL_STORY_KNOBS["GRANULAR_NONINDUSTRIAL_PERCENTAGES"].value
        is GRANULAR_NONINDUSTRIAL_PERCENTAGES
    )


def test_every_counsel_ruled_medical_story_knob_and_denominator_is_exact() -> None:
    """R70's counsel-knob gate: the five R48 constants exact under
    counsel_confirmed provenance with their Ruling Set Three source and their
    exact denominator language recorded on the knob; every other R48-R58
    exact choice pinned against independent literals. The behavioral
    denominator witnesses (which draws actually consume which populations)
    land with the samplers in steps 4-8 and the R63 cohort measurement at
    step 12 — this gate freezes the ruled values so those steps cannot bend
    them."""
    knobs = MEDICAL_STORY_KNOBS

    counsel_five = {
        "P_DEFENSE_CONTEST": (Fraction(13, 20), "before bundling"),
        "P_PTP_INDUSTRIAL_AOE_COE": (Fraction(19, 20), "explicit PTP opinions are excluded"),
        "P_QME_AME_RESPONSIVE_ADOPTION": (Fraction(1, 4), "all three R38 predicates"),
        "P_IMR_REQUEST_GIVEN_UPHELD_DENIAL": (
            Fraction(1, 2),
            "imr was not authored",
        ),
        "P_COMMON_PERCENTAGE_REGISTER": (
            Fraction(17, 20),
            "every newly sampled allocated percentage",
        ),
    }
    for name, (value, denominator_phrase) in counsel_five.items():
        knob = knobs[name]
        assert knob.value == value, name
        assert knob.provenance == "counsel_confirmed", name
        assert "Ruling Set Three" in knob.source, name
        assert denominator_phrase in knob.rationale, (name, denominator_phrase)

    # Outside R30 there is no defense channel at all.
    assert knobs["P_DEFENSE_CONTEST_OUTSIDE_R30"].value == Fraction(0, 1)

    # R49 — complement split and psych masses.
    assert knobs["PTP_AOE_COE_COMPLEMENT_WEIGHTS"].value == {
        "nonindustrial": Fraction(3, 5),
        "deferred": Fraction(2, 5),
    }
    assert sum(knobs["PTP_AOE_COE_COMPLEMENT_WEIGHTS"].value.values()) == 1
    assert knobs["P_APPLICANT_DIRECT_PSYCH_FRAMING_GIVEN_CONSEQUENCE"].value == Fraction(3, 4)
    assert knobs["P_PTP_DIRECT_PSYCH_CLASSIFICATION_GIVEN_CONSEQUENCE"].value == Fraction(3, 5)
    assert knobs["P_QME_AME_INDETERMINATE_DEFERRED"].value == Fraction(3, 5)

    # R50 — applicant incidence and the complete ContestPath mixes.
    assert knobs["P_APPLICANT_CONTEST"].value == Fraction(1, 2)
    assert knobs["P_APPLICANT_COMPLETION_REQUEST"].value == Fraction(13, 20)
    contest_paths = set(typing.get_args(ContestPath.__value__))
    adverse = knobs["ADVERSE_CONTEST_PATH_WEIGHTS"].value
    assert adverse == {
        "applicant": (
            ("objection_only", Fraction(1, 2)),
            ("objection_supplemental", Fraction(3, 10)),
            ("objection_deposition", Fraction(3, 20)),
            ("objection_supplemental_deposition", Fraction(1, 20)),
        ),
        "defense": (
            ("objection_only", Fraction(2, 5)),
            ("objection_supplemental", Fraction(3, 10)),
            ("objection_deposition", Fraction(1, 5)),
            ("objection_supplemental_deposition", Fraction(1, 10)),
        ),
    }
    completion = knobs["COMPLETION_PATH_WEIGHTS"].value
    assert completion == {
        "applicant": (
            ("supplemental_only", Fraction(17, 20)),
            ("supplemental_deposition", Fraction(3, 20)),
        ),
        "defense": (
            ("supplemental_only", Fraction(3, 4)),
            ("supplemental_deposition", Fraction(1, 4)),
        ),
    }
    for table in (adverse, completion):
        for actor, weighted in table.items():
            assert actor in ("applicant", "defense")
            assert sum(weight for _path, weight in weighted) == 1, actor
            for path, _weight in weighted:
                assert path in contest_paths, path

    # R51 — theory count and weighted selection; categories are exactly the
    # DefenseContestTheory declaration order (counsel_confirmed content).
    assert knobs["DEFENSE_THEORY_COUNT_WEIGHTS"].value == (
        (1, Fraction(3, 4)),
        (2, Fraction(1, 5)),
        (3, Fraction(1, 20)),
    )
    theory_weights = knobs["DEFENSE_THEORY_WEIGHTS"].value
    assert theory_weights == (
        ("insufficient_investigation", Fraction(7, 20)),
        ("post_termination", Fraction(7, 20)),
        ("lack_of_substantial_medical_evidence", Fraction(3, 10)),
    )
    assert tuple(theory for theory, _weight in theory_weights) == typing.get_args(
        DefenseContestTheory.__value__
    )
    assert "Ruling Set Three" in knobs["DEFENSE_THEORY_WEIGHTS"].source
    for weighted in (
        knobs["DEFENSE_THEORY_COUNT_WEIGHTS"].value,
        theory_weights,
    ):
        assert sum(weight for _member, weight in weighted) == 1

    # R52 — advocacy incidence and bundling.
    assert knobs["ADVOCACY_INCIDENCE"].value == {
        ("ptp", "applicant"): Fraction(3, 5),
        ("qme", "applicant"): Fraction(7, 10),
        ("ame", "applicant"): Fraction(3, 5),
        ("qme", "defense"): Fraction(11, 20),
        ("ame", "defense"): Fraction(1, 2),
    }
    assert knobs["ADVOCACY_BUNDLE_SIZE_WEIGHTS"].value == (
        (1, Fraction(1, 2)),
        (2, Fraction(7, 20)),
        (3, Fraction(3, 20)),
    )
    assert sum(w for _size, w in knobs["ADVOCACY_BUNDLE_SIZE_WEIGHTS"].value) == 1

    # R54 — revision-kind distributions per trigger stage, in exact
    # OpinionRevisionKind declaration order (five members per row), each row
    # summing to one, deposition rows carrying zero new_records_no_change.
    revision_kinds = typing.get_args(OpinionRevisionKind.__value__)
    assert revision_kinds == (
        "unchanged_additional_reasoning",
        "new_records_no_change",
        "revised_causation",
        "revised_apportionment",
        "revised_causation_and_apportionment",
    )
    revision = knobs["REVISION_KIND_WEIGHTS"].value
    assert revision == {
        "supplemental_after_objection": (
            Fraction(7, 20),
            Fraction(3, 20),
            Fraction(3, 20),
            Fraction(1, 4),
            Fraction(1, 10),
        ),
        "supplemental_after_completion": (
            Fraction(3, 20),
            Fraction(1, 5),
            Fraction(1, 5),
            Fraction(3, 10),
            Fraction(3, 20),
        ),
        "deposition_examining_base": (
            Fraction(13, 20),
            Fraction(0, 1),
            Fraction(1, 10),
            Fraction(1, 5),
            Fraction(1, 20),
        ),
        "deposition_examining_supplemental": (
            Fraction(7, 10),
            Fraction(0, 1),
            Fraction(1, 10),
            Fraction(3, 20),
            Fraction(1, 20),
        ),
    }
    for trigger, row in revision.items():
        assert len(row) == len(revision_kinds), trigger
        assert sum(row) == 1, trigger
        if trigger.startswith("deposition"):
            assert row[1] == 0, trigger

    # R55 — the percentage pools: the M2 pool untouched, the granular
    # remainder exactly the 78-integer complement of 1..99.
    assert COMMON_NONINDUSTRIAL_PERCENTAGES == (
        5, 10, 15, 20, 25, 30, 33, 35, 40, 45, 50,
        55, 60, 65, 67, 70, 75, 80, 85, 90, 95,
    )
    assert tuple(
        value
        for value in range(1, 100)
        if value not in COMMON_NONINDUSTRIAL_PERCENTAGES
    ) == GRANULAR_NONINDUSTRIAL_PERCENTAGES
    assert len(GRANULAR_NONINDUSTRIAL_PERCENTAGES) == 78
    assert set(COMMON_NONINDUSTRIAL_PERCENTAGES).isdisjoint(
        GRANULAR_NONINDUSTRIAL_PERCENTAGES
    )
    assert set(COMMON_NONINDUSTRIAL_PERCENTAGES) | set(
        GRANULAR_NONINDUSTRIAL_PERCENTAGES
    ) == set(range(1, 100))

    # R56 — inclusive integer date bands, strictly positive and ordered.
    bands = {
        "ADVOCACY_LEAD_DAYS": (14, 45),
        "OBJECTION_LAG_DAYS": (10, 30),
        "SUPPLEMENTAL_REQUEST_LAG_DAYS": (7, 21),
        "SUPPLEMENTAL_REPORT_LAG_DAYS": (30, 90),
        "DEPOSITION_LAG_DAYS": (30, 120),
        "IMR_APPLICATION_LAG_DAYS": (10, 30),
        "IMR_DECISION_LAG_DAYS": (30, 60),
    }
    for name, expected in bands.items():
        value = knobs[name].value
        assert value == expected, name
        lower, upper = value
        assert isinstance(lower, int) and isinstance(upper, int), name
        assert 0 < lower < upper, name

    # R57 — unstated-result weights preserve the uniform substrate choice.
    for name in ("UR_DECISION_WEIGHTS_WHEN_UNSTATED", "IMR_OUTCOME_WEIGHTS_WHEN_UNSTATED"):
        assert knobs[name].value == (
            ("upheld", Fraction(1, 2)),
            ("overturned", Fraction(1, 2)),
        ), name
        assert knobs[name].provenance == "derived", name

    # R58 — applicant-attorney IMR sparseness.
    assert knobs["IMR_APPLICATION_FIELD_OCCUPANCY"].value == {
        "disputed_treatment": Fraction(19, 20),
        "diagnosis_icd10": Fraction(3, 5),
        "ur_determination_attached": Fraction(7, 10),
        "supporting_record_subtypes": Fraction(7, 20),
        "clinical_rebuttal": Fraction(1, 4),
        "mtus_citations": Fraction(3, 20),
    }
    assert knobs["SUPPORTING_RECORD_COUNT_WEIGHTS"].value == (
        (1, Fraction(3, 5)),
        (2, Fraction(3, 10)),
        (3, Fraction(1, 10)),
    )
    assert knobs["MTUS_CITATION_COUNT_WEIGHTS"].value == (
        (1, Fraction(4, 5)),
        (2, Fraction(1, 5)),
    )
    for name in ("SUPPORTING_RECORD_COUNT_WEIGHTS", "MTUS_CITATION_COUNT_WEIGHTS"):
        assert sum(weight for _count, weight in knobs[name].value) == 1, name
    assert knobs["P_IMR_CASE_SPECIFIC_REBUTTAL"].value == Fraction(1, 2)

    # R65 — determinism matrices are policy constants with exact members.
    assert MEDICAL_STORY_TZ_MATRIX == ("America/Los_Angeles", "Australia/Sydney")
    assert MEDICAL_STORY_HASH_SEEDS == ("0", "424242")
    assert MEDICAL_STORY_REPEAT_GENERATIONS == 2


# ---------------------------------------------------------------------------
# R77 step 4 — PTP remodel, adoption/concurrence, revision draws, percentage
# law (R49/R53/R54/R55, gated by R70).
#
# R70's date-band gate — test_raw_date_band_draws_are_inclusive_causal_and_
# never_redrawn — is DEFERRED: no date-band family has a producer yet. The
# lag/lead draws happen when sampled response drafts and chain documents
# propose dates, which R77 assigns to steps 5-6; the test lands with those
# producers (deferral recorded in the build ledger).
# ---------------------------------------------------------------------------


def _derive_case(index: int, patch: dict[str, Any] | None = None):
    """One cohort case through the plan seam, with its baseline trace."""
    body = cohort_seed_body(index)
    if patch:
        body["scenario"].update(patch)
    seed = parse_case_seed(body)
    history = derive_medical_history(seed)
    trace = AssertionTrace()
    plan = derive_medical_assertion_plan(seed, history, trace=trace)
    return seed, history, trace, plan


def _record_story_streams(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, Any]]:
    """Observe every medical-story stream the wrapped module attribute
    constructs, without disturbing a single drawn value."""
    constructed: list[tuple[str, Any]] = []
    original = assertion_module._medical_story_rng

    def recording(seed: Any, family: str, semantic_key: Any) -> Any:
        constructed.append((family, semantic_key))
        return original(seed, family, semantic_key)

    monkeypatch.setattr(assertion_module, "_medical_story_rng", recording)
    return constructed


def _sampled_opinion_ids(trace: AssertionTrace, patch_explicit: set[str]) -> set[str]:
    baseline = trace.m2_baseline_ledger
    assert baseline is not None
    return {o.id for o in baseline.medical_opinions if o.id not in patch_explicit}


def test_ptp_remodel_has_exact_findings_complement_and_no_sampled_endorsement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R70's PTP-remodel gate (R49/R16/R47).

    The finding law is exact — 19/20 industrial from the entity-private
    stream, complement split 3/5 nonindustrial : 2/5 deferred consumed from
    the SAME stream — no eligible sampled PTP opinion retains
    ``aoe_coe_finding=None``, no sampled PTP result enters
    ``endorses_contention_ids``, the unchanged M2 ``ptp-disposition``
    affirmative result reappears as independent concurrence (deferral for a
    directly affected causation contention under a deferred finding), the M2
    baseline snapshot retains the original endorsement, and an explicit PTP
    opinion is excluded from the draw entirely.
    """
    import random as random_module

    from wc_caseload_engine.seeds import derive_seed

    # The exact draw law, reproduced independently: one uniform against
    # 19/20; on a miss, a second uniform from the SAME stream against the
    # 3/5 : 2/5 complement. Swept over many opinion identities so all three
    # findings are positively observed.
    observed: set[str] = set()
    seed3 = parse_case_seed(cohort_seed_body(3))
    for day in range(1, 400):
        opinion_key = (
            "case",
            seed3.case_id,
            "opinion",
            "sampled_base",
            "ptp",
            "interim",
            dt.date(2024, 3, 1) + dt.timedelta(days=day),
            (),
        )
        full_key = ("case", seed3.case_id, opinion_key)
        oracle = random_module.Random(
            derive_seed(
                seed3.rng_seed,
                "medical-story:ptp-aoe-coe-finding:"
                + canonical_story_key(full_key),
            )
        )
        if oracle.random() < float(Fraction(19, 20)):
            expected = "industrial"
        elif oracle.random() < float(Fraction(3, 5)):
            expected = "nonindustrial"
        else:
            expected = "deferred"
        actual = assertion_module._ptp_aoe_coe_finding(seed3, opinion_key)
        assert actual == expected, (day, actual, expected)
        observed.add(actual)
    assert observed == {"industrial", "nonindustrial", "deferred"}

    # End-to-end over PTP cells: findings present, endorsements remodeled to
    # concurrence, baseline untouched.
    checked = 0
    for index in (1, 2, 5, 7, 8, 11, 4801, 4802, 5761, 5762):
        _seed, _history, trace, plan = _derive_case(index)
        baseline = trace.m2_baseline_ledger
        assert baseline is not None
        assert plan.ledger is not None
        # Step-5 responses append strictly AFTER the base entries, so the
        # base-opinion pairing reads the base prefix, still strict.
        for base_opinion, plan_opinion in zip(
            baseline.medical_opinions,
            plan.ledger.medical_opinions[: len(baseline.medical_opinions)],
            strict=True,
        ):
            if base_opinion.author_role != "ptp":
                continue
            checked += 1
            assert plan_opinion.aoe_coe_finding is not None
            assert plan_opinion.endorses_contention_ids == ()
            assert base_opinion.aoe_coe_finding is None
            assert set(base_opinion.endorses_contention_ids) == set(
                plan_opinion.concurs_with_contention_ids
            ) | set(plan_opinion.defers_contention_ids)
            for ref in plan_opinion.defers_contention_ids:
                assert plan_opinion.aoe_coe_finding == "deferred"
                contention = plan.ledger.contention(ref)
                assert contention is not None
                assert contention.claim_type == "industrial_causation"
    assert checked >= 8

    # Deferral placement, forced through the sanctioned entity-private
    # replacement (R67): with the finding stream forced into the deferred
    # complement, the affirmative M2 result on a causation contention lands
    # in defers_contention_ids, never concurrence, never endorsement.
    class _ForcedComplement(random_module.Random):
        def __init__(self) -> None:
            super().__init__()
            self._values = iter((0.99, 0.99))

        def random(self) -> float:
            try:
                return next(self._values)
            except StopIteration:  # pragma: no cover - two draws maximum
                return 0.5

    original = assertion_module._medical_story_rng

    def forcing(seed: Any, family: str, semantic_key: Any) -> Any:
        if family == "ptp-aoe-coe-finding":
            return _ForcedComplement()
        return original(seed, family, semantic_key)

    monkeypatch.setattr(assertion_module, "_medical_story_rng", forcing)
    _seed, _history, trace, plan = _derive_case(2)
    monkeypatch.setattr(assertion_module, "_medical_story_rng", original)
    baseline = trace.m2_baseline_ledger
    assert baseline is not None and plan.ledger is not None
    forced = next(
        o for o in plan.ledger.medical_opinions if o.author_role == "ptp"
    )
    base = next(
        o for o in baseline.medical_opinions if o.author_role == "ptp"
    )
    assert forced.aoe_coe_finding == "deferred"
    assert base.endorses_contention_ids, "cohort-0002 stopped endorsing"
    endorsed = base.endorses_contention_ids[0]
    endorsed_claim = baseline.contention(endorsed)
    assert endorsed_claim is not None
    if endorsed_claim.claim_type == "industrial_causation":
        assert forced.defers_contention_ids == (endorsed,)
        assert forced.concurs_with_contention_ids == ()
    else:  # pragma: no cover - cohort-0002 endorses industrial causation
        assert forced.concurs_with_contention_ids == (endorsed,)
    assert forced.endorses_contention_ids == ()

    # Explicit PTP opinions are excluded from the draw and keep their
    # authored (absent) finding.
    explicit_patch = {
        "medical_assertions": {
            "medical_opinions": [
                {
                    "id": "opn-01",
                    "author_role": "ptp",
                    "report_stage": "interim",
                    "report_date": "2024-06-01",
                    "apportionment_state": "deferred",
                    "examination_performed": True,
                    "rationale": "explicit treating narrative",
                }
            ]
        }
    }
    _seed, _history, trace, plan = _derive_case(1, explicit_patch)
    assert plan.ledger is not None
    explicit_opinion = plan.ledger.opinion("opn-01")
    assert explicit_opinion is not None
    assert explicit_opinion.aoe_coe_finding is None
    sampled = [
        o
        for o in plan.ledger.medical_opinions
        if o.id != "opn-01" and o.author_role == "ptp"
    ]
    for opinion in sampled:
        assert opinion.aoe_coe_finding is not None


def test_qme_ame_responsive_adoption_requires_evidence_and_prior_communication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R70's adoption gate (R38/R53).

    Adoption requires ALL THREE: supporting evidence, an earlier qualifying
    communication targeting the opinion, and the 0.25 channel firing. Since
    R77 step 5 the qualifying communications are REAL — sampled advocacy
    letters targeting the sampled evaluator — so the channel is exercised
    end to end: a supported pair without a communication concurs with no
    adoption draw; a supported pair with one goes through the exact 0.25
    channel; a missed draw is concurrence; contradicted evidence stays in
    the preserved M2 rejection result whatever communications exist;
    indeterminate evidence defers or stays unaddressed through its own
    stream and can never be adopted or concurred.
    """
    import random as random_module

    from wc_caseload_engine.medical_assertions import (
        assertion_context,
        contention_evidence,
        project_medical_history,
    )
    from wc_caseload_engine.seeds import derive_seed

    # End-to-end (step 5): the adoption stream exists exactly where a
    # supported pair carries a qualifying communication, and cohort-0081 is
    # the pinned positive witness — its 0.25 draw hits, so the final plan
    # ledger carries a sampled endorsement reachable ONLY through the
    # advocacy -> communication -> adoption path.
    constructed = _record_story_streams(monkeypatch)
    checked_opinions = 0
    adoption_witnessed = False
    for index in (3, 9, 4, 10, 5283, 5763, 5523, 5043, 81):
        before = len(constructed)
        seed, history, trace, plan = _derive_case(index)
        case_streams = list(constructed[before:])
        baseline = trace.m2_baseline_ledger
        assert baseline is not None and plan.ledger is not None
        context = assertion_context(seed)
        projection = project_medical_history(history, context.current_body_parts)
        # The qualifying communications, re-derived at the production seam:
        # sampled advocacy letters targeting the sampled evaluator (R38).
        contention_keys = {
            contention.id: assertion_module._story_contention_key(
                seed, contention, frozenset()
            )
            for contention in baseline.contentions
        }
        communications = assertion_module._derive_advocacy(
            seed,
            seed.scenario.medical_assertions,
            context,
            baseline,
            contention_keys,
            frozenset(),
        ).qualifying_communications
        communicated_supported = any(
            communications.get(contention.id)
            and contention_evidence(projection, context, contention) == "supports"
            for contention in baseline.contentions
        )
        # Step-5 responses append strictly AFTER the base entries, so the
        # base-opinion pairing reads the base prefix, still strict.
        for base_opinion, plan_opinion in zip(
            baseline.medical_opinions,
            plan.ledger.medical_opinions[: len(baseline.medical_opinions)],
            strict=True,
        ):
            if base_opinion.author_role not in ("qme", "ame"):
                continue
            checked_opinions += 1
            assert plan_opinion.rejects_contention_ids == (
                base_opinion.rejects_contention_ids
            )
            endorsed = set(plan_opinion.endorses_contention_ids)
            concurred = set(plan_opinion.concurs_with_contention_ids)
            deferred = set(plan_opinion.defers_contention_ids)
            rejected = set(plan_opinion.rejects_contention_ids)
            assert endorsed <= {
                contention.id
                for contention in baseline.contentions
                if communications.get(contention.id)
            }, "an endorsement appeared without a qualifying communication"
            for contention in baseline.contentions:
                evidence = contention_evidence(projection, context, contention)
                if contention.id in rejected:
                    assert evidence == "contradicts"
                    assert contention.id not in endorsed | concurred
                    continue
                if evidence == "supports":
                    if communications.get(contention.id):
                        assert (contention.id in endorsed) != (
                            contention.id in concurred
                        )
                        if contention.id in endorsed:
                            adoption_witnessed = True
                    else:
                        assert contention.id not in endorsed
                        assert contention.id in concurred
                    assert contention.id not in deferred
                elif evidence == "indeterminate":
                    assert contention.id not in endorsed | concurred
                else:
                    assert contention.id not in endorsed | concurred | deferred
        adoption_constructed = any(
            family == "qme-ame-responsive-adoption" for family, _key in case_streams
        )
        assert adoption_constructed == communicated_supported, (
            "the adoption stream exists exactly when a supported pair "
            "carries a qualifying communication"
        )
    assert checked_opinions >= 6
    assert adoption_witnessed, (
        "no communicated supported pair adopted across the sweep; "
        "cohort-0081's pinned witness disappeared"
    )

    # The pinned witness in full: the endorsement and its qualifying
    # communication are BOTH visible in one plan — the sampled advocacy
    # binding speaks the adopted contention at the endorsing evaluator.
    seed, history, trace, plan = _derive_case(81)
    baseline = trace.m2_baseline_ledger
    assert baseline is not None and plan.ledger is not None
    context = assertion_context(seed)
    projection = project_medical_history(history, context.current_body_parts)
    evaluator = next(
        opinion
        for opinion in plan.ledger.medical_opinions[: len(baseline.medical_opinions)]
        if opinion.author_role in ("qme", "ame")
    )
    assert "ctn-01" in evaluator.endorses_contention_ids
    adopted = plan.ledger.contention("ctn-01")
    assert adopted is not None
    assert contention_evidence(projection, context, adopted) == "supports"
    witnesses = [
        binding
        for binding in plan.contention_documents
        if binding.document_kind == "advocacy"
        and binding.source == "sampled"
        and binding.target_medical_opinion_id == evaluator.id
        and "ctn-01" in binding.spoken_contention_ids
    ]
    assert witnesses, "the qualifying communication left no advocacy binding"

    # Unit half — the classifier itself. Without a communication: concurrence
    # and NO stream construction at all.
    seed3 = parse_case_seed(cohort_seed_body(3))
    opinion_key = (
        "case",
        seed3.case_id,
        "opinion",
        "sampled_base",
        "qme",
        "final",
        dt.date(2024, 12, 26),
        (),
    )
    contention_key = (
        "case",
        seed3.case_id,
        "contention",
        "sampled",
        ("contention", "industrial_causation", "affirm", "cond-00", None, None, None, ()),
    )

    def fail_if_constructed(*args: object, **kwargs: object):
        pytest.fail("adoption draw constructed without a qualifying communication")

    monkeypatch.setattr(assertion_module, "_medical_story_rng", fail_if_constructed)
    assert (
        assertion_module._qme_ame_supported_disposition(
            seed3, opinion_key, contention_key, ()
        )
        == "concurred"
    )
    monkeypatch.undo()

    # With a qualifying communication: exactly the 0.25 law against the
    # (O, C, sorted D keys) stream — fires adopted, misses concurred — and
    # the D-key ordering is canonical, so presentation order cannot move the
    # draw.
    d_key_a = (
        "case",
        seed3.case_id,
        "contention_document",
        "advocacy",
        "applicant",
        None,
        opinion_key,
        (contention_key,),
    )
    d_key_b = (
        "case",
        seed3.case_id,
        "contention_document",
        "advocacy",
        "defense",
        None,
        opinion_key,
        (contention_key,),
    )
    outcomes: set[str] = set()
    for day in range(1, 200):
        shifted_opinion_key = (
            "case",
            seed3.case_id,
            "opinion",
            "sampled_base",
            "qme",
            "final",
            dt.date(2023, 1, 1) + dt.timedelta(days=day),
            (),
        )
        sorted_d = tuple(
            sorted((d_key_b, d_key_a), key=canonical_story_key)
        )
        full_key = (
            "case",
            seed3.case_id,
            shifted_opinion_key,
            contention_key,
            sorted_d,
        )
        oracle = random_module.Random(
            derive_seed(
                seed3.rng_seed,
                "medical-story:qme-ame-responsive-adoption:"
                + canonical_story_key(full_key),
            )
        )
        expected = (
            "adopted" if oracle.random() < float(Fraction(1, 4)) else "concurred"
        )
        forward = assertion_module._qme_ame_supported_disposition(
            seed3, shifted_opinion_key, contention_key, (d_key_a, d_key_b)
        )
        reversed_order = assertion_module._qme_ame_supported_disposition(
            seed3, shifted_opinion_key, contention_key, (d_key_b, d_key_a)
        )
        assert forward == expected
        assert reversed_order == expected
        outcomes.add(forward)
    assert outcomes == {"adopted", "concurred"}

    # A communication cannot resurrect a contradicted pair: the preserved M2
    # rejection stands and no adoption enters the ledger.
    seed, history, trace, plan = _derive_case(5763)
    baseline = trace.m2_baseline_ledger
    assert baseline is not None
    context = assertion_context(seed)
    projection = project_medical_history(history, context.current_body_parts)
    base_evaluator = next(
        o for o in baseline.medical_opinions if o.author_role in ("qme", "ame")
    )
    assert base_evaluator.rejects_contention_ids, "cohort-5763 stopped rejecting"
    rejected_id = base_evaluator.rejects_contention_ids[0]
    scenario = seed.scenario.medical_assertions
    remodeled = assertion_module._apply_story_semantics(
        seed,
        scenario,
        context,
        projection,
        baseline,
        qualifying_communications={rejected_id: (d_key_a,)},
    )
    evaluator = next(
        o for o in remodeled.medical_opinions if o.author_role in ("qme", "ame")
    )
    assert rejected_id in evaluator.rejects_contention_ids
    assert rejected_id not in evaluator.endorses_contention_ids
    assert rejected_id not in evaluator.concurs_with_contention_ids

    # …while a supported pair WITH a communication goes through the exact
    # 0.25 channel inside the full remodel.
    supported_id = base_evaluator.endorses_contention_ids[0]
    remodeled = assertion_module._apply_story_semantics(
        seed,
        scenario,
        context,
        projection,
        baseline,
        qualifying_communications={supported_id: (d_key_a,)},
    )
    evaluator = next(
        o for o in remodeled.medical_opinions if o.author_role in ("qme", "ame")
    )
    assert (
        supported_id
        in evaluator.endorses_contention_ids + evaluator.concurs_with_contention_ids
    )


def test_revision_kind_draws_follow_trigger_conditioned_compatible_weights(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R70's revision gate (R54): trigger-conditioned weights, compatibility
    pruning BEFORE the single draw, exact renormalization, adoption
    conditioning, structurally zero deposition ``new_records_no_change``, and
    fail-closed impossibility — never a draw-and-retry loop."""
    import random as random_module

    from wc_caseload_engine.seeds import derive_seed

    seed3 = parse_case_seed(cohort_seed_body(3))
    revision_kinds = typing.get_args(OpinionRevisionKind.__value__)
    weights = {
        "supplemental_after_objection": (
            Fraction(7, 20), Fraction(3, 20), Fraction(3, 20),
            Fraction(1, 4), Fraction(1, 10),
        ),
        "supplemental_after_completion": (
            Fraction(3, 20), Fraction(1, 5), Fraction(1, 5),
            Fraction(3, 10), Fraction(3, 20),
        ),
        "deposition_examining_base": (
            Fraction(13, 20), Fraction(0, 1), Fraction(1, 10),
            Fraction(1, 5), Fraction(1, 20),
        ),
        "deposition_examining_supplemental": (
            Fraction(7, 10), Fraction(0, 1), Fraction(1, 10),
            Fraction(3, 20), Fraction(1, 20),
        ),
    }

    def response_key(day: int):
        return (
            "case",
            seed3.case_id,
            "opinion",
            "sampled_response",
            "supplemental_report",
            "qme",
            dt.date(2025, 1, 1) + dt.timedelta(days=day),
            (),
        )

    predecessor_key = (
        "case",
        seed3.case_id,
        "opinion",
        "sampled_base",
        "qme",
        "final",
        dt.date(2024, 12, 26),
        (),
    )

    def oracle_kind(
        trigger: str,
        day: int,
        eligible: tuple[str, ...],
    ) -> str:
        pool = [
            (kind, weight)
            for kind, weight in zip(revision_kinds, weights[trigger], strict=True)
            if kind in eligible
        ]
        total = sum(weight for _kind, weight in pool)
        full_key = (
            "case",
            seed3.case_id,
            response_key(day),
            predecessor_key,
            trigger,
        )
        stream = random_module.Random(
            derive_seed(
                seed3.rng_seed,
                "medical-story:revision-kind:" + canonical_story_key(full_key),
            )
        )
        draw = stream.random()
        cumulative = 0.0
        for kind, weight in pool:
            cumulative += float(weight / total)
            if draw < cumulative:
                return kind
        return pool[-1][0]

    everything = tuple(revision_kinds)
    no_records = tuple(k for k in everything if k != "new_records_no_change")
    causation_only = (
        "unchanged_additional_reasoning",
        "new_records_no_change",
        "revised_causation",
    )
    adoption_pool = ("revised_causation", "revised_causation_and_apportionment")

    for trigger in weights:
        seen: set[str] = set()
        for day in range(1, 120):
            # Full eligibility.
            actual = assertion_module._draw_revision_kind(
                seed3,
                response_key(day),
                predecessor_key,
                trigger,
                can_acknowledge_new_records=True,
                can_change_apportionment=True,
                can_change_causation=True,
                adoption_changed_disposition=False,
            )
            assert actual == oracle_kind(trigger, day, everything), (trigger, day)
            seen.add(actual)
            # Records structurally unavailable: the kind is pruned before the
            # draw and the remaining weights renormalize exactly.
            pruned = assertion_module._draw_revision_kind(
                seed3,
                response_key(day),
                predecessor_key,
                trigger,
                can_acknowledge_new_records=False,
                can_change_apportionment=True,
                can_change_causation=True,
                adoption_changed_disposition=False,
            )
            assert pruned == oracle_kind(trigger, day, no_records), (trigger, day)
            assert pruned != "new_records_no_change"
            # No apportionment issue can change.
            causation_pruned = assertion_module._draw_revision_kind(
                seed3,
                response_key(day),
                predecessor_key,
                trigger,
                can_acknowledge_new_records=True,
                can_change_apportionment=False,
                can_change_causation=True,
                adoption_changed_disposition=False,
            )
            assert causation_pruned == oracle_kind(trigger, day, causation_only)
            # Responsive adoption changed a disposition: only
            # causation-capable kinds remain.
            adopted = assertion_module._draw_revision_kind(
                seed3,
                response_key(day),
                predecessor_key,
                trigger,
                can_acknowledge_new_records=True,
                can_change_apportionment=True,
                can_change_causation=True,
                adoption_changed_disposition=True,
            )
            assert adopted == oracle_kind(trigger, day, adoption_pool)
            assert adopted in adoption_pool
        if trigger.startswith("deposition"):
            # The zero-weight member can never be selected even when the
            # record predicate would allow it.
            assert "new_records_no_change" not in seen
        else:
            assert seen == set(everything), (trigger, seen)

    # Exactly ONE draw is consumed — pruning renormalizes, it never retries.
    draws: list[int] = []
    original = assertion_module._medical_story_rng

    def counting(seed: Any, family: str, semantic_key: Any) -> Any:
        stream = _CountingRandom()
        stream.setstate(original(seed, family, semantic_key).getstate())
        draws.append(0)
        outer = stream

        class _Probe:
            def random(self) -> float:
                draws[-1] += 1
                return outer.random()

        return _Probe()

    monkeypatch.setattr(assertion_module, "_medical_story_rng", counting)
    assertion_module._draw_revision_kind(
        seed3,
        response_key(1),
        predecessor_key,
        "supplemental_after_completion",
        can_acknowledge_new_records=False,
        can_change_apportionment=False,
        can_change_causation=True,
        adoption_changed_disposition=False,
    )
    monkeypatch.undo()
    assert draws == [1]

    # Fail-closed: an unknown trigger and an impossible pool are loud errors.
    with pytest.raises(MedicalAssertionError, match="unknown revision trigger"):
        assertion_module._draw_revision_kind(
            seed3,
            response_key(1),
            predecessor_key,
            "supplemental_after_lunch",
            can_acknowledge_new_records=True,
            can_change_apportionment=True,
            can_change_causation=True,
            adoption_changed_disposition=False,
        )
    with pytest.raises(MedicalAssertionError, match="no compatible revision kind"):
        assertion_module._draw_revision_kind(
            seed3,
            response_key(1),
            predecessor_key,
            "supplemental_after_objection",
            can_acknowledge_new_records=True,
            can_change_apportionment=True,
            can_change_causation=False,
            adoption_changed_disposition=True,
        )


def test_percentage_register_pool_continuous_remainder_and_predecessor_exclusion_are_exact() -> None:  # noqa: E501
    """R70's percentage gate (R55): the 17/20 register selects the exact M2
    common pool versus the 78-member granular remainder; when R37 requires a
    changed percentage the immediate predecessor's value leaves the SELECTED
    pool before the single value selection; the granular selector implements
    the continuous latent law's interval index — never a clamp onto the
    common register, never a retry."""
    import random as random_module

    from wc_caseload_engine.seeds import derive_seed

    seed3 = parse_case_seed(cohort_seed_body(3))
    response_key = (
        "case",
        seed3.case_id,
        "opinion",
        "sampled_response",
        "supplemental_report",
        "qme",
        dt.date(2025, 3, 1),
        (),
    )

    def predecessor_row_key(day: int):
        return ("apportionment", "sampled", "qme", "lumbar_spine", day)

    common = COMMON_NONINDUSTRIAL_PERCENTAGES
    granular = GRANULAR_NONINDUSTRIAL_PERCENTAGES

    def oracle(day: int, predecessor: int | None, require_change: bool) -> int:
        full_key = (
            "case",
            seed3.case_id,
            response_key,
            "lumbar_spine",
            predecessor_row_key(day),
        )
        register = random_module.Random(
            derive_seed(
                seed3.rng_seed,
                "medical-story:revision-percentage-register:"
                + canonical_story_key(full_key),
            )
        )
        common_selected = register.random() < float(Fraction(17, 20))
        pool = common if common_selected else granular
        if require_change and predecessor in pool:
            pool = tuple(v for v in pool if v != predecessor)
        value = random_module.Random(
            derive_seed(
                seed3.rng_seed,
                "medical-story:revision-percentage-value:"
                + canonical_story_key(full_key),
            )
        )
        if common_selected:
            return pool[value.randrange(len(pool))]
        z = value.random() * len(pool)
        return pool[min(int(z), len(pool) - 1)]

    common_seen = 0
    granular_seen = 0
    exclusion_exercised = 0
    for day in range(1, 500):
        # No change required: the full selected pool is used.
        unforced = assertion_module._draw_revision_percentage(
            seed3,
            response_key,
            "lumbar_spine",
            predecessor_row_key(day),
            predecessor_nonindustrial=25,
            require_change=False,
        )
        assert unforced == oracle(day, 25, False), day
        # Change required against a common predecessor: the predecessor
        # leaves whichever pool was selected before the single selection.
        changed = assertion_module._draw_revision_percentage(
            seed3,
            response_key,
            "lumbar_spine",
            predecessor_row_key(day),
            predecessor_nonindustrial=25,
            require_change=True,
        )
        assert changed == oracle(day, 25, True), day
        assert changed != 25
        # …and against a granular predecessor.
        granular_changed = assertion_module._draw_revision_percentage(
            seed3,
            response_key,
            "lumbar_spine",
            predecessor_row_key(day),
            predecessor_nonindustrial=42,
            require_change=True,
        )
        assert granular_changed == oracle(day, 42, True), day
        assert granular_changed != 42
        if changed in common:
            common_seen += 1
            if unforced == 25:
                exclusion_exercised += 1
        else:
            granular_seen += 1
            # The anti-clamp law: a common-pool miss is NEVER rounded into
            # the common register.
            assert changed in granular
        assert 1 <= changed <= 99
    assert common_seen and granular_seen
    assert exclusion_exercised, (
        "the sweep never hit the predecessor value without exclusion — the "
        "exclusion branch was not positively exercised"
    )

    # Every granular result obeys the interval law exactly (already pinned
    # by the oracle equality above); the pool partition is total and exact.
    assert set(common).isdisjoint(granular)
    assert set(common) | set(granular) == set(range(1, 100))
    assert len(granular) == 78


# ---------------------------------------------------------------------------
# R56 — the five loop date bands: inclusive, causal, never redrawn
# ---------------------------------------------------------------------------


def test_raw_date_band_draws_are_inclusive_causal_and_never_redrawn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R70's date-band gate, scoped to the five R56 loop bands that R77
    step 5 owns: ``advocacy-lead``, ``objection-lag``,
    ``supplemental-request-lag``, ``supplemental-report-lag`` and
    ``deposition-lag``.

    Each raw draw is exactly one inclusive ``randint(lower, upper)`` with
    both endpoints reachable; each drawn offset is applied to its CAUSE's
    date (the target report, the objection, the request, the response
    report, the examined report); and no ``(family, key)`` stream is ever
    constructed twice — a truncated stage's draw stays burned, never
    redrawn, which the branch/truncation gate witnesses from the other
    side. The two IMR bands (``imr-application-lag``, ``imr-decision-lag``)
    belong to R77 step 8's UR/IMR derivation and are asserted with it.
    """
    from test_medical_story_loop import (
        _contest_world,
        _fire,
        _matrix_seeds,
        _route_story_streams,
    )

    bands = {
        "advocacy-lead": assertion_module.ADVOCACY_LEAD_DAYS.value,
        "objection-lag": assertion_module.OBJECTION_LAG_DAYS.value,
        "supplemental-request-lag": (
            assertion_module.SUPPLEMENTAL_REQUEST_LAG_DAYS.value
        ),
        "supplemental-report-lag": (
            assertion_module.SUPPLEMENTAL_REPORT_LAG_DAYS.value
        ),
        "deposition-lag": assertion_module.DEPOSITION_LAG_DAYS.value,
    }
    assert bands == {
        "advocacy-lead": (14, 45),
        "objection-lag": (10, 30),
        "supplemental-request-lag": (7, 21),
        "supplemental-report-lag": (30, 90),
        "deposition-lag": (30, 120),
    }

    # Inclusive, one draw per offset: swept at the production helper with
    # every constructed stream counted — every offset comes from exactly one
    # randint, every value stays inside the band, and BOTH endpoints are
    # positively observed for every family.
    class _CountingStream:
        def __init__(self, inner: Any) -> None:
            self._inner = inner
            self.randints = 0

        def randint(self, lower: int, upper: int) -> int:
            self.randints += 1
            return self._inner.randint(lower, upper)

        def __getattr__(self, name: str) -> Any:
            return getattr(self._inner, name)

    original = assertion_module._medical_story_rng
    streams: list[_CountingStream] = []

    def counting(seed: Any, family: str, semantic_key: Any) -> Any:
        stream = _CountingStream(original(seed, family, semantic_key))
        streams.append(stream)
        return stream

    monkeypatch.setattr(assertion_module, "_medical_story_rng", counting)
    seed3 = parse_case_seed(cohort_seed_body(3))
    unit_trace = AssertionTrace()
    observed: dict[str, set[int]] = {family: set() for family in bands}
    probes = 1000
    for family, band in bands.items():
        for probe in range(probes):
            offset = assertion_module._band_offset(
                seed3,
                family,
                ("case", seed3.case_id, "band-probe", family, probe),
                band,
                unit_trace,
            )
            assert band[0] <= offset <= band[1]
            observed[family].add(offset)
    monkeypatch.undo()
    for family, band in bands.items():
        assert band[0] in observed[family], (family, "lower endpoint unreached")
        assert band[1] in observed[family], (family, "upper endpoint unreached")
    assert len(streams) == probes * len(bands)
    assert all(stream.randints == 1 for stream in streams)
    assert [family for family, _offset in unit_trace.story_raw_date_offsets] == [
        family for family in bands for _ in range(probes)
    ]

    # Causal, end to end: one forced full chain draws each band exactly
    # once, in causal order, and every proposed date is its cause's date
    # plus (or minus, for the lead) exactly the recorded raw offset.
    forced = _contest_world("objection_supplemental_deposition")
    forced["advocacy-incidence"] = _fire
    recorded: list[tuple[str, Any]] = []
    _route_story_streams(monkeypatch, forced, recorded)
    seed = _matrix_seeds()["loop-applicant-rejected"]
    history = derive_medical_history(seed)
    trace = AssertionTrace()
    plan = derive_medical_assertion_plan(seed, history, trace=trace)
    monkeypatch.undo()

    assert [family for family, _offset in trace.story_raw_date_offsets] == [
        "advocacy-lead",
        "objection-lag",
        "supplemental-request-lag",
        "supplemental-report-lag",
        "deposition-lag",
    ]
    offsets = dict(trace.story_raw_date_offsets)
    for family, offset in trace.story_raw_date_offsets:
        lower, upper = bands[family]
        assert lower <= offset <= upper

    ledger = plan.ledger
    assert ledger is not None
    base, supplemental, deposition = ledger.medical_opinions
    by_kind = {
        binding.document_kind: binding
        for binding in plan.contention_documents
        if binding.source == "sampled"
    }
    assert by_kind["advocacy"].proposed_date == base.report_date - dt.timedelta(
        days=offsets["advocacy-lead"]
    )
    assert by_kind["objection"].proposed_date == base.report_date + dt.timedelta(
        days=offsets["objection-lag"]
    )
    assert by_kind["supplemental_request"].proposed_date == by_kind[
        "objection"
    ].proposed_date + dt.timedelta(days=offsets["supplemental-request-lag"])
    assert by_kind["supplemental_report"].proposed_date == by_kind[
        "supplemental_request"
    ].proposed_date + dt.timedelta(days=offsets["supplemental-report-lag"])
    assert by_kind["supplemental_report"].proposed_date == supplemental.report_date
    assert by_kind[
        "qme_deposition"
    ].proposed_date == supplemental.report_date + dt.timedelta(
        days=offsets["deposition-lag"]
    )
    assert by_kind["qme_deposition"].proposed_date == deposition.report_date

    # Never redrawn: no (family, key) pair is constructed twice within the
    # derivation, and a second derivation replays byte-identical raw draws.
    band_streams = [
        (family, canonical_story_key(key))
        for family, key in recorded
        if family in bands
    ]
    assert len(band_streams) == 5
    assert len(band_streams) == len(set(band_streams))
    _route_story_streams(monkeypatch, forced)
    trace_again = AssertionTrace()
    plan_again = derive_medical_assertion_plan(
        seed, derive_medical_history(seed), trace=trace_again
    )
    monkeypatch.undo()
    assert trace_again.story_raw_date_offsets == trace.story_raw_date_offsets
    assert [b.model_dump() for b in plan_again.contention_documents] == [
        b.model_dump() for b in plan.contention_documents
    ]


def test_part5_phrase_pools_are_deterministic_without_new_streams_or_draws(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R80/R91 — immutable projection over existing pinned stream traces."""
    register_names = (
        "PSYCH_HISTORY_REGISTER",
        "PSYCH_QME_PROTOCOL_REGISTER",
        "PSYCH_ROLDA_REGISTER",
        "PSYCH_THRESHOLD_REGISTER",
        "PSYCH_ACTUAL_EVENTS_REGISTER",
        "PSYCH_SAFETY_OFFICER_REGISTER",
        "PSYCH_GAF_PDRS_REGISTER",
        "PSYCH_SECTION_4660_1C_REGISTER",
        "PSYCH_DEFENSE_CONTEST_REGISTER",
        "PSYCH_CONTENTION_SURFACE_REGISTER",
        "IMR_APPLICATION_REGISTER",
    )
    for name in register_names:
        register = getattr(fact_templates_module, name)
        assert isinstance(register, tuple) and register
        assert all(
            isinstance(row, tuple)
            and len(row) == 2
            and isinstance(row[0], str)
            and isinstance(row[1], tuple)
            for row in register
        )
    assert set(register_names).isdisjoint(MEDICAL_STORY_KNOBS)
    assert MEDICAL_STORY_RNG_FAMILIES == EXPECTED_MEDICAL_STORY_FAMILIES
    assert len(MEDICAL_STORY_RNG_FAMILIES) == 34

    # Existing independent pins, not a before/after derivation comparison.
    cohort = build_cohort()
    assert cohort.stream_trace_digests == MEASURED_M2_STREAM_TRACE_DIGESTS
    assert cohort.ledger_digests == MEASURED_LEDGER_DIGESTS

    from test_medical_story import _bound, _case

    _seed, plan = _case("surface-psych-medlegal")

    class _NoPart5Draw:
        def __getattr__(self, name: str) -> Any:
            raise AssertionError(f"Part 5 attempted random.{name}")

    monkeypatch.setattr(fact_templates_module, "random", _NoPart5Draw())
    template = typing.cast(Any, type("Template", (), {"case": plan.cast.case})())
    observed = []
    for opinion_id in ("opn-01", "opn-02", "opn-03", "opn-04"):
        _document, story = _bound("surface-psych-medlegal", opinion_id)
        observed.append(fact_templates_module._psych_register_key(template, story))
        prose = fact_templates_module._story_psych_complaint_text(template, story)
        assert prose
    assert observed == [
        "direct_physical_event",
        "harassment_gfpa",
        "compensable_consequence",
        "safety_officer_ptsd",
    ]
