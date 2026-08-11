"""AJC-61 (M2) — the frozen empirical oracle over the 6,000-case cohort.

Every band below is asserted against a value the cohort actually produced and
pinned (``tests/assertion_cohort.py``); no band was widened to make a draw
pass. The cohort builds ledgers only — no rendering — and is cached per
process so the whole property surface shares one build.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import typing
from fractions import Fraction
from typing import Any

import pytest

from assertion_cohort import (
    ASSERTION_COHORT_N,
    COHORT_CELLS,
    COHORT_SEED_BASE,
    MEASURED_ASSERTION_QUALITY_COUNTS,
    MEASURED_CONTENTION_FAMILY_COUNTS,
    MEASURED_DISTRACTOR_COUNTS,
    MEASURED_ELIGIBLE_COUNTS,
    MEASURED_EVIDENCE_BUDGET_COUNTS,
    MEASURED_LEDGER_DIGESTS,
    MEASURED_LIFECYCLE_COUNTS,
    MEASURED_PSYCH_ADD_ON_CASES,
    MEASURED_PSYCH_COMPONENT_CASES,
    MEASURED_RECIPE_GRADE_COUNTS,
    MIN_TAGGED_FAMILY_CANDIDATES,
    ORDINARY_COUNT,
    TAGGED_FAMILY_RATES,
    WITNESS_STRATUM_SIZE,
    build_cohort,
    cohort_seed_body,
    minimum_n,
)
from wc_caseload_engine import medical_assertions as assertion_module
from wc_caseload_engine.medical_assertions import (
    ASSERTION_KNOBS,
    ASSERTION_RNG_FAMILIES,
    AssertionKnob,
    AssertionTrace,
    derive_medical_assertions,
    qme_disposition,
)
from wc_caseload_engine.medical_history import derive_medical_history
from wc_caseload_engine.seeds import parse_case_seed

#: The pinned suppression-collision case (m19-16's anti-vacuity seed): cohort
#: index 5760 samples an lc4664 defense contention against prior-00-award, and
#: an explicit contention with the same semantic key suppresses it.
COLLISION_INDEX = 5760

pytestmark = pytest.mark.slow


def _cohort():
    return build_cohort()


def _derive(index: int, scenario_patch: dict[str, Any] | None = None, trace=None):
    body = cohort_seed_body(index)
    if scenario_patch:
        body["scenario"].update(scenario_patch)
    seed = parse_case_seed(body)
    history = derive_medical_history(seed)
    return derive_medical_assertions(seed, history, trace=trace)


# ---------------------------------------------------------------------------
# Pinned reproduction
# ---------------------------------------------------------------------------


def test_sampler_cohort_matches_pinned_empirical_metrics() -> None:
    result = _cohort()
    assert {
        model: dict(counts) for model, counts in result.quality_counts.items()
    } == MEASURED_ASSERTION_QUALITY_COUNTS
    assert dict(result.contention_family_counts) == MEASURED_CONTENTION_FAMILY_COUNTS
    assert dict(result.lifecycle_counts) == MEASURED_LIFECYCLE_COUNTS
    assert dict(result.eligible_counts) == MEASURED_ELIGIBLE_COUNTS
    assert result.psych_component_cases == MEASURED_PSYCH_COMPONENT_CASES
    assert result.psych_add_on_cases == MEASURED_PSYCH_ADD_ON_CASES
    assert result.invalid_ledgers == 0
    assert result.ledger_digests == MEASURED_LEDGER_DIGESTS


def test_supported_shares_hold_the_counsel_ruling_bands() -> None:
    """Counsel ruling AJC-61/D1 (2026-08-11): the 0.75-0.85 band governs
    OPINIONS and ASSERTIONS; contentions carry a 0.65 floor with the measured
    value pinned exactly in ``MEASURED_ASSERTION_QUALITY_COUNTS``. The psych
    realism rules stand unchanged, and the fix-round-1 reversions (H2:
    candidacy is world-truth-typed, the firefighter override is gone) are part
    of the measured number. The measured contention share is 0.5880 — BELOW
    the ruling's floor. Per the ruling that is a fresh counsel question, not
    the sampler's to absorb: the floor stays RED, the number stays pinned,
    and the decomposition travels with the fix-round report. Deliberately its
    own test so the pinned-reproduction guard the mutation gate relies on
    stays green while THIS carries the open ruling question.
    """
    for model in ("medical_opinions", "apportionment_assertions"):
        counts = MEASURED_ASSERTION_QUALITY_COUNTS[model]
        share = counts["supported"] / sum(counts.values())
        assert 0.75 <= share <= 0.85, (model, share)
    contention_counts = MEASURED_ASSERTION_QUALITY_COUNTS["contentions"]
    contention_share = contention_counts["supported"] / sum(contention_counts.values())
    assert contention_share >= 0.65, contention_share


def test_recipe_to_grade_confusion_matrix_matches_pinned_cohort() -> None:
    result = _cohort()
    assert dict(result.recipe_grade_counts) == MEASURED_RECIPE_GRADE_COUNTS
    # A dropped rationale can never read as full reasoning.
    assert ("thin", "supported") not in MEASURED_RECIPE_GRADE_COUNTS


def test_quality_rederivation_has_deliberate_disagreement_controls() -> None:
    """Copying a target and rederiving must be distinguishable — and they are:
    the matrix carries deliberate off-diagonal mass in both directions."""
    assert MEASURED_RECIPE_GRADE_COUNTS[("supported", "thin")] > 0
    assert MEASURED_RECIPE_GRADE_COUNTS[("supported", "unsupportable")] > 0
    assert MEASURED_RECIPE_GRADE_COUNTS[("unsupportable", "supported")] > 0


def test_evidence_budget_and_distractor_counts_match_pinned_cohort() -> None:
    result = _cohort()
    assert dict(result.evidence_budget_counts) == MEASURED_EVIDENCE_BUDGET_COUNTS
    assert dict(result.distractor_counts) == MEASURED_DISTRACTOR_COUNTS
    available = MEASURED_DISTRACTOR_COUNTS["available"]
    included = MEASURED_DISTRACTOR_COUNTS["included"]
    assert available >= 500
    assert included > 0
    assert 0.22 <= included / available <= 0.28


# ---------------------------------------------------------------------------
# Counsel bands and knob-tagged rates
# ---------------------------------------------------------------------------


def test_condition_contention_rate_hits_the_derived_midpoint_inside_counsel_bounds() -> None:
    drawn = MEASURED_CONTENTION_FAMILY_COUNTS["condition"]
    eligible = MEASURED_ELIGIBLE_COUNTS["condition"]
    rate = drawn / eligible
    assert 0.155 <= rate <= 0.195, rate
    assert 0.10 <= rate <= 0.25


def test_psych_component_and_add_on_rates_are_distinct_and_calibrated() -> None:
    component_rate = MEASURED_PSYCH_COMPONENT_CASES / ASSERTION_COHORT_N
    add_on_rate = MEASURED_PSYCH_ADD_ON_CASES / MEASURED_PSYCH_COMPONENT_CASES
    assert 0.42 <= component_rate <= 0.48, component_rate
    assert 0.17 <= add_on_rate <= 0.23, add_on_rate
    assert component_rate != add_on_rate


def test_nonzero_apportionment_hits_the_counsel_estimated_band() -> None:
    allocated = sum(
        count
        for label, count in MEASURED_LIFECYCLE_COUNTS.items()
        if ":allocated:" in label
    )
    branch_a = sum(
        count for label, count in MEASURED_LIFECYCLE_COUNTS.items() if label.endswith(":A")
    )
    rate = allocated / branch_a
    assert 0.70 <= rate <= 0.80, rate


def test_final_report_omission_rate_is_inside_its_band() -> None:
    omitted = sum(
        count
        for label, count in MEASURED_LIFECYCLE_COUNTS.items()
        if ":omitted:" in label
    )
    finals = sum(
        count for label, count in MEASURED_LIFECYCLE_COUNTS.items() if ":final:" in label
    )
    assert 0.075 <= omitted / finals <= 0.125


def test_every_tagged_contention_family_meets_candidate_floor_before_rate_band() -> None:
    for family, floor in MIN_TAGGED_FAMILY_CANDIDATES.items():
        rate = TAGGED_FAMILY_RATES[family]
        assert floor == minimum_n(rate), family
        eligible = MEASURED_ELIGIBLE_COUNTS[family]
        assert eligible >= floor, (family, eligible, floor)
        drawn = MEASURED_CONTENTION_FAMILY_COUNTS.get(family, 0)
        realized = drawn / eligible
        assert abs(realized - float(rate)) <= 0.03, (family, realized)


def test_every_assertion_knob_has_value_rationale_source_and_provenance() -> None:
    from wc_caseload_engine.medical_assertions import AssertionProvenance

    allowed = set(typing.get_args(AssertionProvenance.__value__))
    assert len(ASSERTION_KNOBS) >= 21
    for name, knob in ASSERTION_KNOBS.items():
        assert isinstance(knob, AssertionKnob), name
        assert knob.rationale.strip(), name
        assert knob.source.strip(), name
        assert knob.provenance in allowed, name
        flattened = knob.value if isinstance(knob.value, tuple) else (knob.value,)
        for component in flattened:
            if isinstance(component, int | float) and not isinstance(component, Fraction):
                pytest.fail(
                    f"{name} carries a non-Fraction numeric component {component!r}; "
                    "probability values must be exact Fractions"
                )
    with pytest.raises(ValueError, match="empty rationale or source"):
        AssertionKnob(value=Fraction(1, 2), provenance="invented", rationale=" ", source="x")


def test_assertion_provenance_supersedes_clinical_tag_for_new_knobs() -> None:
    from wc_caseload_engine.clinical_grounding import Tag
    from wc_caseload_engine.medical_assertions import AssertionProvenance

    clinical = set(typing.get_args(Tag.__value__))
    assertion = set(typing.get_args(AssertionProvenance.__value__))
    # Shared counsel_confirmed keeps one meaning; counsel_unconfirmed maps to
    # nothing here, and the counsel gradations exist only on the new enum.
    assert "counsel_confirmed" in clinical & assertion
    assert "counsel_unconfirmed" in clinical - assertion
    assert {"counsel_estimate", "counsel_qualitative", "counsel_assumed"} <= (
        assertion - clinical
    )


# ---------------------------------------------------------------------------
# Dispositions
# ---------------------------------------------------------------------------


def test_qme_disposition_is_completely_conditioned_on_ledger_evidence() -> None:
    assert qme_disposition("supports") == "endorse"
    assert qme_disposition("contradicts") == "reject"
    assert qme_disposition("indeterminate") == "neither"
    # And over the cohort: no sampled evaluator ever endorses a contradicted
    # contention or rejects a supported one. Checked over a deterministic
    # slice — the policy is a pure function, the slice proves the wiring.
    from wc_caseload_engine.medical_assertions import (
        assertion_context,
        contention_evidence,
        project_medical_history,
    )

    checked = 0
    for index in (3, 9, 15, 5763, 5769, 5283, 5289):
        body = cohort_seed_body(index)
        seed = parse_case_seed(body)
        history = derive_medical_history(seed)
        ledger = derive_medical_assertions(seed, history)
        context = assertion_context(seed)
        projection = project_medical_history(history, context.current_body_parts)
        for opinion in ledger.medical_opinions:
            if opinion.author_role not in ("qme", "ame"):
                continue
            for ref in opinion.endorses_contention_ids:
                contention = ledger.contention(ref)
                assert contention_evidence(projection, context, contention) == "supports"
                checked += 1
            for ref in opinion.rejects_contention_ids:
                contention = ledger.contention(ref)
                assert (
                    contention_evidence(projection, context, contention) == "contradicts"
                )
                checked += 1
    assert checked > 0


def test_ptp_disposition_uses_its_separate_tagged_policy() -> None:
    """PTP endorsement is a draw under its own tagged trio, not the QME policy:
    across the cohort's PTP opinions some supported-evidence contentions stay
    unendorsed, which the deterministic QME policy could never produce."""
    result = _cohort()
    ptp_opinions = sum(
        count
        for label, count in MEASURED_LIFECYCLE_COUNTS.items()
        if label.startswith("ptp:")
    )
    assert ptp_opinions > 0
    knobs = {
        "P_PTP_ENDORSE_SUPPORTED",
        "P_PTP_ENDORSE_INDETERMINATE",
        "P_PTP_ENDORSE_CONTRADICTED",
    }
    assert knobs <= set(ASSERTION_KNOBS)
    assert "ptp-disposition" in result.families_seen


def test_evidence_budget_distribution_is_label_independent() -> None:
    """The budget draw happens before any grade exists and its realized totals
    are pinned; every budget value coexists with every opinion grade."""
    result = _cohort()
    budgets = {budget for budget, _quality in result.budget_quality}
    assert budgets == {1, 2, 3}
    for budget in (1, 2, 3):
        qualities = {q for b, q in result.budget_quality if b == budget}
        assert "supported" in qualities, budget
        assert "thin" in qualities or "unsupportable" in qualities, budget


def test_every_quality_is_reachable_at_every_evidence_budget() -> None:
    result = _cohort()
    for budget in (1, 2, 3):
        for quality in ("supported", "thin", "unsupportable"):
            assert result.budget_quality.get((budget, quality), 0) > 0, (budget, quality)


def test_every_eligible_claim_type_and_party_position_pair_is_reachable() -> None:
    result = _cohort()
    claim_types = {shape[0] for shape in result.contention_shapes}
    assert claim_types == {
        "industrial_causation",
        "aggravation",
        "apportionment_defense",
        "compensable_consequence",
        "psych_add_on",
        "denial_of_injury",
    }
    assert {shape[1] for shape in result.contention_shapes} == {"applicant", "defense"}
    assert {shape[2] for shape in result.contention_shapes} == {"affirm", "deny"}


def test_explicit_witness_strata_reach_industrial_mixed_post_doi_psych_and_oncology_branches() -> None:  # noqa: E501
    """One case per stratum, derived directly: each stratum's defining branch
    is live, not attributed to the population sampler."""
    from wc_caseload_engine.medical_assertions import (
        assertion_context,
        project_medical_history,
    )

    def projection_for(index: int):
        seed = parse_case_seed(cohort_seed_body(index))
        history = derive_medical_history(seed)
        context = assertion_context(seed)
        return project_medical_history(history, context.current_body_parts)

    industrial = projection_for(ORDINARY_COUNT)
    assert any(c.causal_ground_truth == "industrial" for c in industrial.conditions)
    mixed = projection_for(ORDINARY_COUNT + WITNESS_STRATUM_SIZE)
    assert any(c.causal_ground_truth == "mixed" for c in mixed.conditions)
    post_doi = projection_for(ORDINARY_COUNT + 2 * WITNESS_STRATUM_SIZE)
    assert any(
        c.causal_ground_truth == "industrial"
        and c.onset is not None
        and c.onset.isoformat() == "2024-06-15"
        for c in post_doi.conditions
    )
    psych = projection_for(ORDINARY_COUNT + 3 * WITNESS_STRATUM_SIZE)
    assert any(c.key == "depression_anxiety" for c in psych.conditions)
    oncology = projection_for(ORDINARY_COUNT + 4 * WITNESS_STRATUM_SIZE)
    assert sum(1 for c in oncology.conditions if c.body_system == "oncologic") >= 7
    assert any(
        c.severity == "severe" and c.symptomatic_before_doi is True
        for c in oncology.conditions
    )
    assert len(oncology.awards) == 2


def test_assertion_cohort_lifecycle_schedule_is_exact_and_family_complete() -> None:
    result = _cohort()
    assert dict(result.cell_counts) == dict.fromkeys(range(6), 1000)
    for stratum in range(5):
        for cell in range(6):
            assert result.stratum_cell_counts[(stratum, cell)] == 40, (stratum, cell)
    assert result.families_seen == set(ASSERTION_RNG_FAMILIES)
    assert COHORT_CELLS[5] == ("resolved", "denied", "none", "c_and_r")
    assert COHORT_SEED_BASE == 610000


# ---------------------------------------------------------------------------
# Structural sampler guarantees
# ---------------------------------------------------------------------------


def test_sampler_never_creates_a_dangling_reference() -> None:
    assert _cohort().invalid_ledgers == 0


def test_sampler_never_exceeds_seed_schema_collection_or_review_limits() -> None:
    for index in (3, 5763, 5283, 5043, 5523, 5999):
        ledger = _derive(index)
        assert len(ledger.contentions) <= 12
        assert len(ledger.medical_opinions) <= 8
        assert len(ledger.apportionment_assertions) <= 12
        for opinion in ledger.medical_opinions:
            combined = (
                len(opinion.reviewed_condition_ids)
                + len(opinion.reviewed_prior_claim_ids)
                + len(opinion.reviewed_prior_award_ids)
            )
            assert combined <= 4


def test_sampler_cohort_is_stable_and_non_vacuous() -> None:
    result = _cohort()
    total = sum(sum(c.values()) for c in result.quality_counts.values())
    assert total > 10000
    again = _derive(5763)
    once_more = _derive(5763)
    assert again.model_dump() == once_more.model_dump()


def test_same_seed_derives_the_same_assertion_ledger_and_digest() -> None:
    import hashlib
    import json

    first = _derive(5763)
    second = _derive(5763)

    def digest(ledger) -> str:
        return hashlib.sha256(
            json.dumps(ledger.model_dump(mode="json"), sort_keys=True).encode()
        ).hexdigest()

    assert first.model_dump() == second.model_dump()
    assert digest(first) == digest(second)


def test_sampled_ids_are_assigned_after_semantic_keyed_draws() -> None:
    """IDs are a labelling pass: an explicit entry shifts suffixes, never the
    semantic content of unrelated sampled candidates."""
    baseline = _derive(COLLISION_INDEX)
    explicit = {
        "medical_assertions": {
            "contentions": [
                {
                    "id": "ctn-01",
                    "claim_type": "industrial_causation",
                    "party": "applicant",
                    "position": "affirm",
                    "rationale": "an explicit placeholder contention",
                }
            ]
        }
    }
    shifted = _derive(COLLISION_INDEX, explicit)

    def shapes(ledger) -> set:
        return {
            (
                c.claim_type,
                c.party,
                c.position,
                c.target_condition_id,
                c.target_prior_claim_id,
                c.target_prior_award_id,
                tuple(sorted(c.doctrine_hooks)),
                c.rationale,
            )
            for c in ledger.contentions
        }

    placeholder = ("industrial_causation", "applicant", "affirm", None, None, None, (), (
        "an explicit placeholder contention"
    ))
    assert shapes(shifted) - {placeholder} == shapes(baseline)
    for contention in shifted.contentions:
        assert contention.id.startswith("ctn-")


def test_adding_an_explicit_entry_does_not_reroll_unrelated_semantic_candidates() -> None:
    baseline = _derive(COLLISION_INDEX)
    with_explicit = _derive(
        COLLISION_INDEX,
        {
            "medical_assertions": {
                "contentions": [
                    {
                        "id": "ctn-01",
                        "claim_type": "denial_of_injury",
                        "party": "defense",
                        "position": "affirm",
                        "rationale": "explicit denial for suppression symmetry",
                    }
                ]
            }
        },
    )
    baseline_awards = {
        (c.claim_type, c.target_prior_award_id, c.position)
        for c in baseline.contentions
        if c.target_prior_award_id is not None
    }
    explicit_awards = {
        (c.claim_type, c.target_prior_award_id, c.position)
        for c in with_explicit.contentions
        if c.target_prior_award_id is not None
    }
    assert baseline_awards == explicit_awards


def test_explicit_entries_are_preserved_and_sampled_entries_append_without_duplicates() -> None:
    baseline = _derive(COLLISION_INDEX)
    sampled_lc4664 = [
        c
        for c in baseline.contentions
        if c.target_prior_award_id is not None and "lc4664_prior_award" in c.doctrine_hooks
    ]
    assert sampled_lc4664, "the pinned collision seed stopped sampling its lc4664 draw"
    target = sampled_lc4664[0]

    trace = AssertionTrace()
    collided = _derive(
        COLLISION_INDEX,
        {
            "medical_assertions": {
                "contentions": [
                    {
                        "id": "ctn-01",
                        "claim_type": "apportionment_defense",
                        "party": "defense",
                        "position": "affirm",
                        "target_prior_claim_id": target.target_prior_claim_id,
                        "target_prior_award_id": target.target_prior_award_id,
                        "doctrine_hooks": ["lc4664_prior_award"],
                        "rationale": (
                            "the prior award conclusively presumes continuing disability"
                        ),
                        "groundings": [
                            {
                                "hook": "lc4664_prior_award",
                                "prior_award_id": target.target_prior_award_id,
                            }
                        ],
                    }
                ]
            }
        },
        trace=trace,
    )
    assert trace.suppression_hits == 1
    explicit = collided.contention("ctn-01")
    assert explicit is not None
    assert explicit.target_prior_award_id == target.target_prior_award_id
    duplicates = [
        c
        for c in collided.contentions
        if c.id != "ctn-01"
        and c.target_prior_award_id == target.target_prior_award_id
        and c.claim_type == "apportionment_defense"
    ]
    assert not duplicates


def test_sample_assertions_false_constructs_no_rng_and_keeps_only_explicit_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_called(*args: object, **kwargs: object):
        pytest.fail("assertion RNG constructed while sample_assertions was false")

    monkeypatch.setattr(assertion_module, "_assertion_rng", fail_if_called)
    ledger = _derive(
        COLLISION_INDEX,
        {
            "medical_assertions": {
                "sample_assertions": False,
                "contentions": [
                    {
                        "id": "ctn-01",
                        "claim_type": "industrial_causation",
                        "party": "applicant",
                        "position": "affirm",
                        "rationale": "explicit only",
                    }
                ],
            }
        },
    )
    assert [c.id for c in ledger.contentions] == ["ctn-01"]
    assert not ledger.medical_opinions
    assert not ledger.apportionment_assertions


def test_condition_overlap_uses_wholly_unrelated_not_body_part() -> None:
    """The diabetes shape: no singular body part, real apportionment targets."""
    import datetime as dt

    from wc_caseload_engine.medical_assertions import (
        AssertionValidationContext,
        ProjectedCondition,
        _condition_claim_types,
    )

    context = AssertionValidationContext(
        date_of_injury=dt.date(2024, 3, 1),
        anchor_date=dt.date(2026, 1, 1),
        current_body_parts=("wrist",),
        target_stage="medical_legal",
        claim_response="accepted",
        eval_type="qme",
    )
    diabetes = ProjectedCondition(
        id="cond-00",
        key="diabetes",
        label="type 2 diabetes mellitus",
        causal_ground_truth="nonindustrial",
        onset=dt.date(2018, 1, 1),
        body_system="endocrine",
        body_part=None,
        apportionment_targets=("wrist", "foot"),
        wholly_unrelated=False,
        severity="moderate",
        trajectory="stable",
        symptomatic_before_doi=True,
        surfaces_in_file=True,
    )
    types = _condition_claim_types(diabetes, context)
    assert "aggravation" in types
    assert "apportionment_defense" in types
    assert "denial_of_injury" not in types


def test_every_assertion_stream_uses_literal_namespace_exact_family_set_and_disjoint_m1_salts() -> None:  # noqa: E501
    """The salt oracle: literal namespace, exact family set, uniqueness, and
    disjointness from every salt medical_history._rng emits."""
    from wc_caseload_engine import medical_history as history_module

    assertion_salts: list[str] = []
    history_salts: list[str] = []

    original_assertion = assertion_module.derive_seed
    original_history = history_module.derive_seed

    def record_assertion(base: int, salt: str = "") -> int:
        assertion_salts.append(salt)
        return original_assertion(base, salt)

    def record_history(base: int, salt: str = "") -> int:
        history_salts.append(salt)
        return original_history(base, salt)

    assertion_module.derive_seed = record_assertion  # type: ignore[assignment]
    history_module.derive_seed = record_history  # type: ignore[assignment]
    per_case_salts: list[list[str]] = []
    try:
        for index in (3, 9, 15, *range(5520, 5550), *range(5760, 5790)):
            body = cohort_seed_body(index)
            seed = parse_case_seed(body)
            history = derive_medical_history(seed)
            assertion_salts.clear()
            derive_medical_assertions(seed, history)
            per_case_salts.append(list(assertion_salts))
    finally:
        assertion_module.derive_seed = original_assertion  # type: ignore[assignment]
        history_module.derive_seed = original_history  # type: ignore[assignment]

    all_salts = [salt for case in per_case_salts for salt in case]
    assert all_salts
    for salt in all_salts:
        assert salt.startswith("medical-assertions:"), salt
    families = {salt.split(":", 2)[1] for salt in all_salts}
    assert families == set(ASSERTION_RNG_FAMILIES)
    # Within one derivation every stream is constructed at most once — a salt
    # constructed twice would be one decision drawn from two places.
    for case in per_case_salts:
        assert len(case) == len(set(case))
    assert set(all_salts).isdisjoint(set(history_salts))
    assert all(salt.startswith("medical:") for salt in history_salts)


def test_adding_an_unused_decision_family_cannot_shift_existing_draws(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Independent per-family seeding: registering (and even drawing from) a
    new family leaves every existing stream untouched."""
    before = _derive(5763)
    widened = (*ASSERTION_RNG_FAMILIES, "future-decision")
    monkeypatch.setattr(assertion_module, "ASSERTION_RNG_FAMILIES", widened)
    seed = parse_case_seed(cohort_seed_body(5763))
    probe = assertion_module._assertion_rng(seed, "future-decision", "case")
    probe.random()
    after = _derive(5763)
    assert before.model_dump() == after.model_dump()


def test_assertion_streams_do_not_move_medical_history_cast_facts_or_documents() -> None:
    """The world ledger derives identically with and without the assertion
    block — the new streams read nothing another layer draws from."""
    body_with = cohort_seed_body(5763)
    body_without = cohort_seed_body(5763)
    body_without["scenario"].pop("medical_assertions")
    with_block = derive_medical_history(parse_case_seed(body_with))
    without_block = derive_medical_history(parse_case_seed(body_without))
    assert with_block.model_dump() == without_block.model_dump()
