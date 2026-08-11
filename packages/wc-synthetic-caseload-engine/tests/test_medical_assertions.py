"""AJC-61 (M2) — assertion-layer models, exact §C templates, polarity.

The test oracle here is FROZEN from the Parts 1-5 architect contract: template
tests assert the exact literal an author sees, byte for byte, and the
divergence-must-pass family proves the polarity rule — divergence from world
truth is legal case content, only internal incoherence fails.

Everything in this module is plan-free and substrate-free on purpose: the
validator consumes a context, a projection and a ledger, all constructible in
microseconds, so the exact-message surface runs on every push at unit speed.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import datetime as dt
import typing
from typing import Any

import pytest
from pydantic import ValidationError

from wc_caseload_engine.medical_assertions import (
    ApportionmentAssertion,
    AssertionValidationContext,
    AssertionWorldProjection,
    BensonGrounding,
    Contention,
    FirefighterPresumptionGrounding,
    Lc4664PriorAwardGrounding,
    MedicalAssertionLedger,
    MedicalOpinion,
    ProjectedCondition,
    ProjectedPriorAward,
    ProjectedPriorClaim,
    SibtfGrounding,
    assertion_warnings,
    validate_medical_assertions,
)
from wc_caseload_engine.medical_history import PRESUMPTION_DEFAULT_BY_RESOLUTION
from wc_caseload_engine.seeds import (
    ApportionmentAssertionEntry,
    ContentionEntry,
    DoctrineHook,
    MedicalAssertionsScenario,
    MedicalOpinionEntry,
    parse_case_seed,
)

DOI = dt.date(2022, 4, 11)
ANCHOR = dt.date(2026, 1, 1)


def _context(**overrides: Any) -> AssertionValidationContext:
    values: dict[str, Any] = {
        "date_of_injury": DOI,
        "anchor_date": ANCHOR,
        "current_body_parts": ("lumbar_spine", "shoulder"),
        "target_stage": "medical_legal",
        "claim_response": "accepted",
        "eval_type": "qme",
    }
    values.update(overrides)
    return AssertionValidationContext(**values)


def _condition(condition_id: str = "cond-01", **overrides: Any) -> ProjectedCondition:
    values: dict[str, Any] = {
        "id": condition_id,
        "key": "lumbar_disc_degeneration",
        "label": "lumbar disc degeneration",
        "causal_ground_truth": "nonindustrial",
        "onset": dt.date(2015, 6, 1),
        "body_system": "musculoskeletal",
        "body_part": "lumbar_spine",
        "apportionment_targets": ("lumbar_spine",),
        "wholly_unrelated": False,
        "severity": "moderate",
        "trajectory": "stable",
        "symptomatic_before_doi": True,
        "surfaces_in_file": True,
    }
    values.update(overrides)
    return ProjectedCondition(**values)


def _world(**overrides: Any) -> AssertionWorldProjection:
    award = ProjectedPriorAward(
        id="prior-01-award",
        prior_claim_id="prior-01",
        body_parts=("lumbar_spine",),
        pd_percent=12,
        award_date=dt.date(2016, 2, 1),
        resolution_type="stipulated_award",
        conclusively_presumed=True,
    )
    values: dict[str, Any] = {
        "conditions": (
            _condition(),
            _condition(
                "cond-02",
                key="seeded",
                label="invasive ductal carcinoma",
                body_system="oncologic",
                body_part="breast",
                apportionment_targets=(),
                wholly_unrelated=True,
                symptomatic_before_doi=False,
            ),
        ),
        "prior_claims": (
            ProjectedPriorClaim(
                id="prior-01",
                date_of_injury=dt.date(2015, 1, 5),
                body_parts=("lumbar_spine",),
                resolution_type="stipulated_award",
                overlaps_current=True,
                award=award,
            ),
            ProjectedPriorClaim(
                id="prior-02",
                date_of_injury=dt.date(2017, 3, 9),
                body_parts=("knee",),
                resolution_type="c_and_r",
                overlaps_current=False,
                award=ProjectedPriorAward(
                    id="prior-02-award",
                    prior_claim_id="prior-02",
                    body_parts=("knee",),
                    pd_percent=8,
                    award_date=dt.date(2018, 1, 15),
                    resolution_type="c_and_r",
                    conclusively_presumed=False,
                ),
            ),
        ),
    }
    values.update(overrides)
    return AssertionWorldProjection(**values)


def _contention(contention_id: str = "ctn-01", **overrides: Any) -> Contention:
    values: dict[str, Any] = {
        "id": contention_id,
        "claim_type": "industrial_causation",
        "party": "applicant",
        "position": "affirm",
        "target_condition_id": "cond-01",
        "rationale": "the lumbar condition arose from the industrial injury",
        "quality": "supported",
    }
    values.update(overrides)
    return Contention(**values)


def _opinion(opinion_id: str = "opn-01", **overrides: Any) -> MedicalOpinion:
    values: dict[str, Any] = {
        "id": opinion_id,
        "author_role": "qme",
        "report_stage": "final",
        "report_date": dt.date(2023, 6, 1),
        "apportionment_state": "determined",
        "determination_kind": "allocated",
        "examination_performed": True,
        "reviewed_condition_ids": ("cond-01",),
        "rationale": "reviewed the record and examined the applicant",
        "quality": "supported",
    }
    values.update(overrides)
    return MedicalOpinion(**values)


def _assertion(assertion_id: str = "app-01", **overrides: Any) -> ApportionmentAssertion:
    values: dict[str, Any] = {
        "id": assertion_id,
        "opinion_id": "opn-01",
        "body_part": "lumbar_spine",
        "industrial_percent": 80,
        "nonindustrial_percent": 20,
        "basis_kinds": ("preexisting_degenerative_pathology",),
        "condition_ids": ("cond-01",),
        "description": "chronic lumbar disability limiting weight-bearing",
        "disability_causation_stated": True,
        "reasonable_medical_probability": True,
        "causal_rationale": "degenerative pathology contributes to present disability",
        "percentage_rationale": "twenty percent reflects the imaging severity",
        "quality": "supported",
    }
    values.update(overrides)
    return ApportionmentAssertion(**values)


def _ledger(
    contentions: tuple[Contention, ...] = (),
    opinions: tuple[MedicalOpinion, ...] = (),
    assertions: tuple[ApportionmentAssertion, ...] = (),
) -> MedicalAssertionLedger:
    return MedicalAssertionLedger(
        contentions=contentions,
        medical_opinions=opinions,
        apportionment_assertions=assertions,
    )


def _problems(
    ledger: MedicalAssertionLedger,
    world: AssertionWorldProjection | None = None,
    context: AssertionValidationContext | None = None,
) -> tuple[str, ...]:
    return validate_medical_assertions(
        context or _context(), world or _world(), ledger
    )


def _seed_body(scenario: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": "assertion-probe",
        "rng_seed": 6100,
        "injury": {
            "type": "specific",
            "date_of_injury": "2022-04-11",
            "body_parts": [{"part": "lumbar_spine"}, {"part": "shoulder"}],
        },
        "lifecycle": {"target_stage": "medical_legal", "eval_type": "qme"},
        "scenario": scenario,
    }


# ---------------------------------------------------------------------------
# E.1 — models
# ---------------------------------------------------------------------------


def test_assertion_models_are_frozen_strict_and_bound_their_fields() -> None:
    for model in (Contention, MedicalOpinion, ApportionmentAssertion, MedicalAssertionLedger):
        assert model.model_config.get("frozen") is True
        assert model.model_config.get("extra") == "forbid"
    with pytest.raises(ValidationError):
        Contention(**{**_contention().model_dump(), "surprise": 1})
    frozen = _contention()
    with pytest.raises(ValidationError):
        frozen.quality = "thin"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        _assertion(industrial_percent=101)
    with pytest.raises(ValidationError):
        _opinion(reviewed_condition_ids=tuple(f"cond-{i:02d}" for i in range(9)))


def test_seed_assertion_models_have_no_quality_field() -> None:
    """The copied seed is analyzer-visible; a seed quality field is a leak."""
    for model in (
        ContentionEntry,
        MedicalOpinionEntry,
        ApportionmentAssertionEntry,
        MedicalAssertionsScenario,
    ):
        assert "quality" not in model.model_fields, model.__name__
        assert "rubric" not in model.model_fields, model.__name__


def test_contention_doctrine_hooks_accept_exactly_the_shipped_fourteen_members() -> None:
    """The fifteenth hook is AJC-62's; M2 types Hikida instead of enumerating it."""
    hooks = tuple(sorted(typing.get_args(DoctrineHook.__value__)))
    assert len(hooks) == 14
    assert "hikida_treatment_carveout" not in hooks
    for hook in hooks:
        assert _contention(doctrine_hooks=(hook,)).doctrine_hooks == (hook,)
    with pytest.raises(ValidationError):
        _contention(doctrine_hooks=("hikida_treatment_carveout",))


def test_typed_doctrine_grounding_union_round_trips_all_four_variants() -> None:
    groundings = (
        BensonGrounding(prior_claim_ids=("prior-01",)),
        SibtfGrounding(preexisting_condition_ids=("cond-01",)),
        Lc4664PriorAwardGrounding(prior_award_id="prior-01-award"),
        FirefighterPresumptionGrounding(condition_id="cond-02"),
    )
    contention = _contention(
        claim_type="apportionment_defense",
        party="defense",
        doctrine_hooks=("benson", "sibtf", "lc4664_prior_award", "firefighter_presumption"),
        groundings=groundings,
    )
    restored = Contention.model_validate(contention.model_dump())
    assert restored.groundings == groundings
    assert tuple(type(g) for g in restored.groundings) == tuple(
        type(g) for g in groundings
    )


def test_reviewed_prior_reference_caps_are_exact_and_combined_overflow_rejects() -> None:
    """5/5 matches prior_claims max_length=5 with one award each; 13 combined fails."""
    five_claims = tuple(f"prior-{i:02d}" for i in range(1, 6))
    five_awards = tuple(f"prior-{i:02d}-award" for i in range(1, 6))
    opinion = _opinion(
        reviewed_condition_ids=("cond-01", "cond-02"),
        reviewed_prior_claim_ids=five_claims,
        reviewed_prior_award_ids=five_awards,
    )
    assert len(opinion.reviewed_prior_claim_ids) == 5
    assert len(opinion.reviewed_prior_award_ids) == 5
    with pytest.raises(ValidationError, match="combined cap is 12"):
        _opinion(
            reviewed_condition_ids=("cond-01", "cond-02", "cond-03"),
            reviewed_prior_claim_ids=five_claims,
            reviewed_prior_award_ids=five_awards,
        )
    with pytest.raises(ValidationError, match="combined cap is 12"):
        MedicalOpinionEntry(
            id="opn-01",
            author_role="qme",
            report_stage="final",
            report_date=dt.date(2023, 6, 1),
            apportionment_state="determined",
            determination_kind="allocated",
            reviewed_condition_ids=["cond-01", "cond-02", "cond-03"],
            reviewed_prior_claim_ids=list(five_claims),
            reviewed_prior_award_ids=list(five_awards),
        )


def test_prior_award_presumption_defaults_and_explicit_overrides_are_honored() -> None:
    """Resolution supplies the default; an authored bool always wins."""
    from wc_caseload_engine.medical_history import derive_medical_history

    assert PRESUMPTION_DEFAULT_BY_RESOLUTION == {
        "c_and_r": False,
        "findings_and_award": True,
        "stipulated_award": True,
    }

    def derived(award_extra: dict[str, Any], resolution: str) -> bool:
        body = _seed_body(
            {
                "medical_history": {
                    "sample_conditions": False,
                    "conditions": [{"label": "hypertension", "key": "hypertension"}],
                    "prior_claims": [
                        {
                            "body_parts": ["lumbar_spine"],
                            "date_of_injury": "2015-01-05",
                            "resolution_type": resolution,
                            "award": {
                                "body_parts": ["lumbar_spine"],
                                "pd_percent": 12,
                                "award_date": "2016-02-01",
                                **award_extra,
                            },
                        }
                    ],
                }
            }
        )
        history = derive_medical_history(parse_case_seed(body))
        assert history is not None
        award = history.prior_claims[0].award
        assert award is not None
        return award.still_exists_conclusively_presumed

    assert derived({}, "stipulated_award") is True
    assert derived({}, "findings_and_award") is True
    assert derived({}, "c_and_r") is False
    # The explicit override wins, including against its own resolution's default.
    assert derived({"conclusively_presumed": False}, "stipulated_award") is False
    assert derived({"conclusively_presumed": True}, "c_and_r") is True


# ---------------------------------------------------------------------------
# E.1 — exact error templates
# ---------------------------------------------------------------------------


def test_gate_and_identity_error_templates_are_exact() -> None:
    with pytest.raises(Exception) as no_history:
        parse_case_seed(_seed_body({"medical_assertions": {}}))
    assert (
        "scenario.medical_assertions requires scenario.medical_history; assertion "
        "references cannot resolve without the world-truth ledger. Add a "
        "scenario.medical_history block, or remove scenario.medical_assertions."
    ) in str(no_history.value)

    with pytest.raises(Exception) as empty:
        parse_case_seed(
            _seed_body(
                {
                    "medical_history": {},
                    "medical_assertions": {"sample_assertions": False},
                }
            )
        )
    assert (
        "scenario.medical_assertions is present but sample_assertions is false and "
        "all three explicit assertion collections are empty. Add at least one "
        "explicit contention, medical opinion, or apportionment assertion, set "
        "sample_assertions to true, or remove scenario.medical_assertions."
    ) in str(empty.value)

    contention = {
        "id": "ctn-01",
        "claim_type": "industrial_causation",
        "party": "applicant",
    }
    with pytest.raises(Exception) as duplicate:
        parse_case_seed(
            _seed_body(
                {
                    "medical_history": {},
                    "medical_assertions": {"contentions": [contention, dict(contention)]},
                }
            )
        )
    assert "scenario.medical_assertions.contentions: duplicate id 'ctn-01'" in str(
        duplicate.value
    )

    with pytest.raises(Exception) as reserved:
        parse_case_seed(
            _seed_body(
                {
                    "medical_history": {},
                    "medical_assertions": {
                        "contentions": [{**contention, "quality": "supported"}]
                    },
                }
            )
        )
    assert (
        "scenario.medical_assertions contains reserved truth-label field 'quality' "
        "at scenario.medical_assertions.contentions[0].quality; quality fields may "
        "appear only in the truth manifest"
    ) in str(reserved.value)


def test_referential_error_templates_are_exact() -> None:
    cases: list[tuple[MedicalAssertionLedger, str]] = [
        (
            _ledger(contentions=(_contention(target_condition_id="cond-99"),)),
            "contention 'ctn-01' references unknown condition 'cond-99'",
        ),
        (
            _ledger(
                contentions=(
                    _contention(
                        claim_type="apportionment_defense",
                        party="defense",
                        target_condition_id=None,
                        target_prior_claim_id="prior-99",
                    ),
                )
            ),
            "contention 'ctn-01' references unknown prior claim 'prior-99'",
        ),
        (
            _ledger(
                contentions=(
                    _contention(
                        claim_type="apportionment_defense",
                        party="defense",
                        target_condition_id=None,
                        target_prior_award_id="prior-99-award",
                    ),
                )
            ),
            "contention 'ctn-01' references unknown prior award 'prior-99-award'",
        ),
        (
            _ledger(
                contentions=(
                    _contention(
                        claim_type="apportionment_defense",
                        party="defense",
                        target_condition_id=None,
                        target_prior_claim_id="prior-02",
                        target_prior_award_id="prior-01-award",
                    ),
                )
            ),
            "contention 'ctn-01' pairs prior claim 'prior-02' with award "
            "'prior-01-award', but that award belongs to prior claim 'prior-01'",
        ),
        (
            _ledger(opinions=(_opinion(reviewed_condition_ids=("cond-99",)),)),
            "medical opinion 'opn-01' reviews unknown condition 'cond-99'",
        ),
        (
            _ledger(opinions=(_opinion(reviewed_prior_claim_ids=("prior-99",)),)),
            "medical opinion 'opn-01' reviews unknown prior claim 'prior-99'",
        ),
        (
            _ledger(opinions=(_opinion(reviewed_prior_award_ids=("prior-99-award",)),)),
            "medical opinion 'opn-01' reviews unknown prior award 'prior-99-award'",
        ),
        (
            _ledger(opinions=(_opinion(endorses_contention_ids=("ctn-09",)),)),
            "medical opinion 'opn-01' endorses unknown contention 'ctn-09'",
        ),
        (
            _ledger(opinions=(_opinion(rejects_contention_ids=("ctn-09",)),)),
            "medical opinion 'opn-01' rejects unknown contention 'ctn-09'",
        ),
        (
            _ledger(
                contentions=(_contention(),),
                opinions=(
                    _opinion(
                        endorses_contention_ids=("ctn-01",),
                        rejects_contention_ids=("ctn-01",),
                    ),
                ),
            ),
            "medical opinion 'opn-01' both endorses and rejects contention 'ctn-01'",
        ),
        (
            _ledger(assertions=(_assertion(opinion_id="opn-77"),)),
            "apportionment assertion 'app-01' references unknown medical opinion "
            "'opn-77'",
        ),
        (
            _ledger(
                opinions=(_opinion(),),
                assertions=(_assertion(linked_contention_id="ctn-44"),),
            ),
            "apportionment assertion 'app-01' references unknown contention 'ctn-44'",
        ),
        (
            _ledger(
                opinions=(_opinion(),),
                assertions=(_assertion(condition_ids=("cond-77",)),),
            ),
            "apportionment assertion 'app-01' references unknown condition 'cond-77'",
        ),
        (
            _ledger(
                opinions=(_opinion(),),
                assertions=(_assertion(prior_claim_ids=("prior-88",)),),
            ),
            "apportionment assertion 'app-01' references unknown prior claim "
            "'prior-88'",
        ),
        (
            _ledger(
                opinions=(_opinion(),),
                assertions=(_assertion(prior_award_ids=("prior-88-award",)),),
            ),
            "apportionment assertion 'app-01' references unknown prior award "
            "'prior-88-award'",
        ),
        (
            _ledger(
                opinions=(_opinion(),),
                assertions=(
                    _assertion(
                        prior_claim_ids=("prior-02",),
                        prior_award_ids=("prior-01-award",),
                    ),
                ),
            ),
            "apportionment assertion 'app-01' pairs prior claim 'prior-02' with "
            "award 'prior-01-award', but that award belongs to prior claim "
            "'prior-01'",
        ),
        (
            _ledger(
                opinions=(_opinion(),),
                assertions=(
                    _assertion(),
                    _assertion("app-02", nonindustrial_percent=30, industrial_percent=70),
                ),
            ),
            "medical opinion 'opn-01' has more than one apportionment assertion for "
            "body part 'lumbar_spine'",
        ),
    ]
    for ledger, expected in cases:
        assert expected in _problems(ledger), expected


def test_opinion_chain_error_templates_are_exact() -> None:
    cases: list[tuple[MedicalAssertionLedger, str]] = [
        (
            _ledger(opinions=(_opinion(responds_to_opinion_id="opn-01"),)),
            "medical opinion 'opn-01' responds to itself",
        ),
        (
            _ledger(opinions=(_opinion(supersedes_opinion_id="opn-01"),)),
            "medical opinion 'opn-01' supersedes itself",
        ),
        (
            _ledger(opinions=(_opinion(responds_to_opinion_id="opn-09"),)),
            "medical opinion 'opn-01' responds to unknown opinion 'opn-09'",
        ),
        (
            _ledger(opinions=(_opinion(supersedes_opinion_id="opn-09"),)),
            "medical opinion 'opn-01' supersedes unknown opinion 'opn-09'",
        ),
        (
            _ledger(opinions=(_opinion(report_date=dt.date(2021, 1, 1)),)),
            "medical opinion 'opn-01' has report_date 2021-01-01, before the current "
            "date of injury 2022-04-11",
        ),
        (
            _ledger(opinions=(_opinion(report_date=dt.date(2026, 3, 1)),)),
            "medical opinion 'opn-01' has report_date 2026-03-01, after the corpus "
            "anchor date 2026-01-01",
        ),
        (
            _ledger(
                opinions=(
                    _opinion(responds_to_opinion_id="opn-02"),
                    _opinion(
                        "opn-02",
                        report_date=dt.date(2023, 6, 1),
                        apportionment_state="determined",
                    ),
                ),
            ),
            "medical opinion 'opn-01' references later-or-same-date opinion "
            "'opn-02'; response and supersession targets must be strictly earlier",
        ),
        (
            _ledger(
                opinions=(
                    _opinion(responds_to_opinion_id="opn-02"),
                    _opinion(
                        "opn-02",
                        report_date=dt.date(2023, 6, 1),
                        responds_to_opinion_id="opn-01",
                    ),
                ),
            ),
            "medical opinion chain contains a cycle: opn-01 -> opn-02 -> opn-01",
        ),
        (
            _ledger(opinions=(_opinion(author_role="ame"),)),
            "medical opinion 'opn-01' has author_role 'ame', which conflicts with "
            "lifecycle.eval_type 'qme'",
        ),
    ]
    for ledger, expected in cases:
        assert expected in _problems(ledger), expected

    # PTP never conflicts, whatever the eval type.
    ptp = _ledger(opinions=(_opinion(author_role="ptp"),))
    assert not any("author_role" in p for p in _problems(ptp))


def test_lifecycle_error_templates_are_exact() -> None:
    cases: list[tuple[MedicalAssertionLedger, str]] = [
        (
            _ledger(
                opinions=(
                    _opinion(apportionment_state="deferred", determination_kind=None),
                )
            ),
            "medical opinion 'opn-01' is final but apportionment_state is 'deferred'",
        ),
        (
            _ledger(
                opinions=(
                    _opinion(
                        report_stage="interim",
                        apportionment_state="omitted",
                        determination_kind=None,
                    ),
                )
            ),
            "medical opinion 'opn-01' is interim but apportionment_state is "
            "'omitted'",
        ),
        (
            _ledger(
                opinions=(
                    _opinion(
                        report_stage="interim",
                        apportionment_state="deferred",
                        determination_kind=None,
                    ),
                ),
                assertions=(_assertion(),),
            ),
            "medical opinion 'opn-01' is deferred but owns an apportionment "
            "assertion",
        ),
        (
            _ledger(
                opinions=(
                    _opinion(apportionment_state="omitted", determination_kind=None),
                ),
                assertions=(_assertion(),),
            ),
            "medical opinion 'opn-01' is omitted but owns an apportionment assertion",
        ),
        (
            _ledger(opinions=(_opinion(determination_kind=None),)),
            "medical opinion 'opn-01' is determined but has no determination_kind",
        ),
        (
            _ledger(
                opinions=(
                    _opinion(
                        report_stage="interim",
                        apportionment_state="deferred",
                        determination_kind="allocated",
                    ),
                ),
                assertions=(_assertion(),),
            ),
            "medical opinion 'opn-01' has determination_kind 'allocated' but "
            "apportionment_state is not 'determined'",
        ),
        (
            _ledger(opinions=(_opinion(),)),
            "medical opinion 'opn-01' has determination_kind 'allocated' but owns "
            "no apportionment assertion",
        ),
        (
            _ledger(
                opinions=(
                    _opinion(
                        determination_kind="no_nonindustrial_share",
                        determination_rationale="the record shows no nonindustrial share",
                    ),
                ),
                assertions=(_assertion(),),
            ),
            "medical opinion 'opn-01' has determination_kind "
            "'no_nonindustrial_share' but owns an apportionment assertion",
        ),
    ]
    for ledger, expected in cases:
        assert expected in _problems(ledger), expected

    # The valid shapes beside the errors: a final omitted opinion with no row
    # passes, and so do the two rowless determined kinds.
    fine = _ledger(
        opinions=(
            _opinion(apportionment_state="omitted", determination_kind=None),
            _opinion(
                "opn-02",
                report_date=dt.date(2023, 7, 1),
                determination_kind="unable_to_approximate",
                determination_rationale="cannot approximate to reasonable probability",
            ),
        )
    )
    assert not _problems(fine)


def test_doctrine_grounding_and_treatment_typing_messages_are_exact() -> None:
    benson = BensonGrounding(prior_claim_ids=("prior-01",))
    cases: list[tuple[MedicalAssertionLedger, str]] = [
        (
            _ledger(
                contentions=(
                    _contention(
                        claim_type="apportionment_defense",
                        party="defense",
                        doctrine_hooks=("benson",),
                        groundings=(benson, BensonGrounding(prior_claim_ids=("prior-02",))),
                    ),
                )
            ),
            "contention 'ctn-01' has more than one grounding for doctrine hook "
            "'benson'",
        ),
        (
            _ledger(contentions=(_contention(groundings=(benson,)),)),
            "contention 'ctn-01' supplies grounding for 'benson' but does not carry "
            "that doctrine hook",
        ),
        (
            _ledger(
                contentions=(
                    _contention(
                        claim_type="apportionment_defense",
                        party="applicant",
                        doctrine_hooks=("sibtf",),
                        groundings=(SibtfGrounding(),),
                    ),
                )
            ),
            "SIBTF grounding on contention 'ctn-01' must reference at least one "
            "preexisting condition or prior award",
        ),
        (
            _ledger(
                contentions=(
                    _contention(
                        treatment_causation="sole_cause",
                        requested_apportionment="refuse",
                    ),
                )
            ),
            "contention 'ctn-01' sets treatment_causation but claim_type is not "
            "'compensable_consequence'",
        ),
        (
            _ledger(
                contentions=(
                    _contention(
                        claim_type="compensable_consequence",
                        target_condition_id=None,
                        treatment_causation="sole_cause",
                        requested_apportionment="refuse",
                    ),
                )
            ),
            "contention 'ctn-01' sets treatment_causation but has no "
            "target_condition_id",
        ),
        (
            _ledger(
                contentions=(
                    _contention(
                        claim_type="compensable_consequence",
                        treatment_causation="sole_cause",
                    ),
                )
            ),
            "contention 'ctn-01' sets treatment_causation but has no "
            "requested_apportionment",
        ),
        (
            _ledger(contentions=(_contention(requested_apportionment="apply"),)),
            "contention 'ctn-01' sets requested_apportionment but claim_type is not "
            "'compensable_consequence'",
        ),
        (
            _ledger(
                contentions=(
                    _contention(
                        claim_type="compensable_consequence",
                        requested_apportionment="apply",
                    ),
                )
            ),
            "contention 'ctn-01' sets requested_apportionment but has no "
            "treatment_causation",
        ),
        (
            _ledger(
                opinions=(_opinion(),),
                assertions=(
                    _assertion(
                        groundings=(benson, BensonGrounding(prior_claim_ids=("prior-02",))),
                        basis_kinds=("benson_successive_injury",),
                        prior_claim_ids=("prior-01",),
                    ),
                ),
            ),
            "apportionment assertion 'app-01' has more than one grounding for "
            "doctrine hook 'benson'",
        ),
        (
            _ledger(
                opinions=(_opinion(),),
                assertions=(_assertion(groundings=(benson,)),),
            ),
            "apportionment assertion 'app-01' supplies grounding for 'benson' but "
            "its basis_kinds do not include the corresponding doctrine basis",
        ),
    ]
    for ledger, expected in cases:
        assert expected in _problems(ledger), expected

    # The one WARNING, and it is nonfatal: an explicit groundable hook with no
    # typed grounding warns and survives.
    ungrounded = _ledger(
        contentions=(
            _contention(
                claim_type="apportionment_defense",
                party="defense",
                doctrine_hooks=("benson",),
            ),
        )
    )
    assert not any("benson" in p and "grounding" in p for p in _problems(ungrounded))
    assert assertion_warnings(_world(), ungrounded) == (
        "medical_assertions: doctrine hook 'benson' has no typed MedicalHistory "
        "grounding; explicit hook retained",
    )


def test_apportionment_shape_error_templates_are_exact() -> None:
    lc4664 = Lc4664PriorAwardGrounding(prior_award_id="prior-01-award")
    cases: list[tuple[MedicalAssertionLedger, str]] = [
        (
            _ledger(
                opinions=(_opinion(),),
                assertions=(_assertion(industrial_percent=70, nonindustrial_percent=20),),
            ),
            "apportionment assertion 'app-01' percentages must sum to 100; got "
            "industrial=70 and nonindustrial=20",
        ),
        (
            _ledger(
                opinions=(_opinion(),),
                assertions=(_assertion(industrial_percent=100, nonindustrial_percent=0),),
            ),
            "apportionment assertion 'app-01' is allocated but nonindustrial_percent "
            "is zero; use determination_kind 'no_nonindustrial_share' on the owning "
            "opinion",
        ),
        (
            _ledger(
                opinions=(_opinion(),),
                assertions=(
                    _assertion(
                        basis_kinds=(
                            "preexisting_degenerative_pathology",
                            "preexisting_degenerative_pathology",
                        )
                    ),
                ),
            ),
            "apportionment assertion 'app-01' repeats basis kind "
            "'preexisting_degenerative_pathology'",
        ),
        (
            _ledger(
                opinions=(_opinion(),),
                assertions=(_assertion(condition_ids=("cond-01", "cond-01")),),
            ),
            "apportionment assertion 'app-01' repeats condition id 'cond-01'",
        ),
        (
            _ledger(
                opinions=(_opinion(),),
                assertions=(_assertion(prior_claim_ids=("prior-01", "prior-01")),),
            ),
            "apportionment assertion 'app-01' repeats prior claim id 'prior-01'",
        ),
        (
            _ledger(
                opinions=(_opinion(),),
                assertions=(
                    _assertion(prior_award_ids=("prior-01-award", "prior-01-award")),
                ),
            ),
            "apportionment assertion 'app-01' repeats prior award id "
            "'prior-01-award'",
        ),
        (
            _ledger(
                opinions=(_opinion(),),
                assertions=(
                    _assertion(
                        basis_kinds=("lc4664_prior_award",),
                        prior_award_ids=("prior-01-award",),
                    ),
                ),
            ),
            "apportionment assertion 'app-01' uses 'lc4664_prior_award' without a "
            "typed prior-award grounding",
        ),
        (
            _ledger(
                opinions=(_opinion(),),
                assertions=(
                    _assertion(
                        basis_kinds=("benson_successive_injury",),
                        prior_claim_ids=("prior-01",),
                    ),
                ),
            ),
            "apportionment assertion 'app-01' uses 'benson_successive_injury' "
            "without a typed Benson grounding",
        ),
        (
            _ledger(
                opinions=(_opinion(),),
                assertions=(_assertion(basis_kinds=("industrial_treatment",)),),
            ),
            "apportionment assertion 'app-01' uses 'industrial_treatment' without a "
            "linked compensable-consequence contention",
        ),
    ]
    for ledger, expected in cases:
        assert expected in _problems(ledger), expected

    # A grounded §4664 row with matching basis passes the shape family.
    grounded = _ledger(
        opinions=(_opinion(reviewed_prior_award_ids=("prior-01-award",)),),
        assertions=(
            _assertion(
                basis_kinds=("lc4664_prior_award",),
                prior_award_ids=("prior-01-award",),
                prior_award_analysis="the 2016 stipulated award presumes per 4664(b)",
                groundings=(lc4664,),
            ),
        ),
    )
    assert not _problems(grounded)


# ---------------------------------------------------------------------------
# The quality rubric — closed table, checklist independence, Hikida fixtures
# ---------------------------------------------------------------------------

from wc_caseload_engine.medical_assertions import (
    UNCONDITIONAL_HARD_INVALID_BASES,
    apportionment_quality,
    contention_quality,
    escobedo_misses,
    opinion_quality,
)


def _graded_assertion(**overrides: Any) -> str:
    """Grade one assertion inside a coherent single-opinion ledger."""
    assertion = _assertion(**overrides)
    ledger = _ledger(opinions=(_opinion(),), assertions=(assertion,))
    return apportionment_quality(_world(), _context(), ledger, assertion)


def test_closed_invalid_basis_decision_table_is_exact() -> None:
    """All fourteen bases, each mapped: the closed list is closed."""
    assert frozenset(
        {
            "vocational_apportionment",
            "lc3208_3_threshold_misuse",
            "bare_age",
            "bare_gender",
            "risk_factor_only",
        }
    ) == UNCONDITIONAL_HARD_INVALID_BASES
    for basis in sorted(UNCONDITIONAL_HARD_INVALID_BASES):
        grade = _graded_assertion(
            basis_kinds=("preexisting_degenerative_pathology", basis)
        )
        assert grade == "unsupportable", basis

    # The one conditional member: its predicate is exactly the four
    # psych_exception_analysis rows.
    assert (
        _graded_assertion(basis_kinds=("psych_impairment_add_on",)) == "unsupportable"
    )
    assert (
        _graded_assertion(
            basis_kinds=("psych_impairment_add_on",),
            psych_exception_analysis="none_applies",
        )
        == "unsupportable"
    )
    for exception in ("violent_act", "direct_exposure", "catastrophic_injury"):
        grade = _graded_assertion(
            basis_kinds=("psych_impairment_add_on",),
            psych_exception_analysis=exception,  # type: ignore[arg-type]
        )
        assert grade == "supported", exception

    # Every remaining basis is gradeable, not barred: a full build stays
    # supported. Genetics needs its diagnosed pathology; the doctrine-linked
    # bases need their grounding/link, exercised in their own tests below.
    for basis in (
        "preexisting_degenerative_pathology",
        "asymptomatic_prior_condition",
        "nonindustrial_medical_condition",
        "prior_symptomatic_disability",
        "genetics_heredity_pathology",
    ):
        assert _graded_assertion(basis_kinds=(basis,)) == "supported", basis


def test_every_escobedo_checklist_item_can_independently_move_supported_to_the_expected_lower_grade() -> None:  # noqa: E501
    assert _graded_assertion() == "supported"

    thin_toggles: dict[str, dict[str, Any]] = {
        "1": {"disability_causation_stated": False},
        "2": {"description": None},
        "3a": {"condition_ids": (), "prior_claim_ids": (), "prior_award_ids": ()},
        "4": {"reasonable_medical_probability": False},
        "6": {"causal_rationale": None},
        "7": {"percentage_rationale": None},
    }
    for item, toggle in thin_toggles.items():
        assert _graded_assertion(**toggle) == "thin", item

    # 5a — the owning opinion never examined.
    assertion = _assertion()
    ledger = _ledger(
        opinions=(_opinion(examination_performed=False),), assertions=(assertion,)
    )
    assert apportionment_quality(_world(), _context(), ledger, assertion) == "thin"

    # 5b — a relied-on factor outside the reviewed record.
    ledger = _ledger(
        opinions=(_opinion(reviewed_condition_ids=()),), assertions=(assertion,)
    )
    assert apportionment_quality(_world(), _context(), ledger, assertion) == "thin"
    assert "5b" in escobedo_misses(_world(), ledger, assertion)

    # 8 — industrial_treatment without the explicit sole/contributing statement.
    treatment = _contention(
        claim_type="compensable_consequence",
        target_condition_id="cond-01",
    )
    assertion8 = _assertion(
        basis_kinds=("preexisting_degenerative_pathology", "industrial_treatment"),
        linked_contention_id="ctn-01",
    )
    ledger8 = _ledger(
        contentions=(treatment,), opinions=(_opinion(),), assertions=(assertion8,)
    )
    assert apportionment_quality(_world(), _context(), ledger8, assertion8) == "thin"
    assert "8" in escobedo_misses(_world(), ledger8, assertion8)

    # 9 — §4664 basis with no separate presumption analysis.
    assertion9 = _assertion(
        basis_kinds=("lc4664_prior_award",),
        prior_award_ids=("prior-01-award",),
        groundings=(Lc4664PriorAwardGrounding(prior_award_id="prior-01-award"),),
    )
    ledger9 = _ledger(
        opinions=(_opinion(reviewed_prior_award_ids=("prior-01-award",)),),
        assertions=(assertion9,),
    )
    assert apportionment_quality(_world(), _context(), ledger9, assertion9) == "thin"
    assert "9" in escobedo_misses(_world(), ledger9, assertion9)

    # 10 — an unexplained material revision is the expected lower grade
    # UNSUPPORTABLE (Part 3 B.8); a reasoned one is not a defect at all.
    assert (
        _graded_assertion(revised_from_percent=10) == "unsupportable"
    )
    assert (
        _graded_assertion(
            revised_from_percent=10,
            revision_rationale="after reviewing all the previous data again",
        )
        == "supported"
    )

    # 11 — Benson basis whose grounding does not separate every cited injury.
    assertion11 = _assertion(
        basis_kinds=("benson_successive_injury",),
        prior_claim_ids=("prior-01", "prior-02"),
        groundings=(BensonGrounding(prior_claim_ids=("prior-01",)),),
    )
    ledger11 = _ledger(
        opinions=(
            _opinion(reviewed_prior_claim_ids=("prior-01", "prior-02")),
        ),
        assertions=(assertion11,),
    )
    assert apportionment_quality(_world(), _context(), ledger11, assertion11) == "thin"
    assert "11" in escobedo_misses(_world(), ledger11, assertion11)

    # 12 — genetics with no diagnosed pathology referenced.
    assertion12 = _assertion(
        basis_kinds=("genetics_heredity_pathology",), condition_ids=()
    )
    ledger12 = _ledger(opinions=(_opinion(),), assertions=(assertion12,))
    assert apportionment_quality(_world(), _context(), ledger12, assertion12) == "thin"
    assert "12" in escobedo_misses(_world(), ledger12, assertion12)


def _hikida_world() -> AssertionWorldProjection:
    """A world with a post-DOI industrial consequence AND a live nonindustrial
    contributor — both sides of the narrowed Justice line reachable."""
    return _world(
        conditions=(
            _condition(),
            _condition(
                "cond-03",
                key="seeded",
                label="post-surgical CRPS",
                causal_ground_truth="industrial",
                onset=dt.date(2022, 9, 1),
                body_part="lumbar_spine",
                apportionment_targets=("lumbar_spine",),
                symptomatic_before_doi=False,
            ),
        ),
    )


def test_explicit_hikida_forward_and_inverse_fixture_decision_table_is_exact() -> None:
    world = _hikida_world()

    def grade(**overrides: Any) -> str:
        contention = _contention(
            claim_type="compensable_consequence",
            target_condition_id="cond-03",
            **overrides,
        )
        return contention_quality(world, _context(), contention)

    # Forward: treatment stated as SOLE cause, apportionment requested anyway.
    assert grade(
        treatment_causation="sole_cause", requested_apportionment="apply"
    ) == "unsupportable"
    # Inverse: contributing cause, refusal to apportion despite a substantial
    # nonindustrial contributor on the record — over-applying Hikida.
    assert grade(
        treatment_causation="contributing_cause", requested_apportionment="refuse"
    ) == "unsupportable"
    # Contributing cause with application and reasoning may be supported.
    assert grade(
        treatment_causation="contributing_cause", requested_apportionment="apply"
    ) == "supported"
    # Sole cause with refusal is the correct Hikida paradigm.
    assert grade(
        treatment_causation="sole_cause", requested_apportionment="refuse"
    ) == "supported"

    # The assertion-side hard direction: a nonzero nonindustrial share where the
    # linked treatment story says sole cause.
    sole = _contention(
        claim_type="compensable_consequence",
        target_condition_id="cond-03",
        treatment_causation="sole_cause",
        requested_apportionment="refuse",
    )
    assertion = _assertion(linked_contention_id="ctn-01")
    ledger = _ledger(contentions=(sole,), opinions=(_opinion(),), assertions=(assertion,))
    assert apportionment_quality(world, _context(), ledger, assertion) == "unsupportable"


def _agreeing_world() -> AssertionWorldProjection:
    """A world with NO substantial nonindustrial contributor."""
    return AssertionWorldProjection(
        conditions=(
            _condition(
                causal_ground_truth="industrial",
                symptomatic_before_doi=False,
            ),
        ),
        prior_claims=(),
    )


def test_reasoned_zero_share_and_unable_to_approximate_can_grade_supported_when_ledger_agrees() -> None:  # noqa: E501
    world = _agreeing_world()
    zero_share = _opinion(
        determination_kind="no_nonindustrial_share",
        determination_rationale=(
            "the record shows no nonindustrial factor causing present disability"
        ),
    )
    unable = _opinion(
        "opn-02",
        report_date=dt.date(2023, 7, 1),
        determination_kind="unable_to_approximate",
        determination_rationale=(
            "the percentages cannot be approximated to reasonable medical probability"
        ),
    )
    ledger = _ledger(opinions=(zero_share, unable))
    assert not _problems(ledger, world)
    assert opinion_quality(world, _context(), ledger, zero_share) == "supported"
    assert opinion_quality(world, _context(), ledger, unable) == "supported"


def test_zero_share_contradicted_by_substantial_nonindustrial_evidence_is_unsupportable() -> None:
    """The deliberate B.6 defect: zero share against a recorded contributor —
    unsupportable regardless of rationale."""
    zero_share = _opinion(
        determination_kind="no_nonindustrial_share",
        determination_rationale="I find no nonindustrial contribution whatsoever",
    )
    ledger = _ledger(opinions=(zero_share,))
    assert not _problems(ledger)
    assert opinion_quality(_world(), _context(), ledger, zero_share) == "unsupportable"


# ---------------------------------------------------------------------------
# E.2 — divergence-must-pass: legal case content is graded, never rejected
# ---------------------------------------------------------------------------


def test_nonindustrial_world_condition_may_be_asserted_industrial() -> None:
    contention = _contention()  # cond-01 is nonindustrial world truth
    ledger = _ledger(contentions=(contention,))
    assert not _problems(ledger)
    assert contention_quality(_world(), _context(), contention) == "unsupportable"


def test_wholly_unrelated_condition_may_be_apportioned() -> None:
    assertion = _assertion(condition_ids=("cond-02",), body_part="lumbar_spine")
    ledger = _ledger(
        opinions=(_opinion(reviewed_condition_ids=("cond-02",)),),
        assertions=(assertion,),
    )
    assert not _problems(ledger)
    assert apportionment_quality(_world(), _context(), ledger, assertion) == "unsupportable"


def test_false_prior_award_overlap_is_graded_not_rejected() -> None:
    contention = _contention(
        claim_type="apportionment_defense",
        party="defense",
        target_condition_id=None,
        target_prior_claim_id="prior-02",
        target_prior_award_id="prior-02-award",
    )
    ledger = _ledger(contentions=(contention,))
    assert not _problems(ledger)
    assert contention_quality(_world(), _context(), contention) in ("thin", "unsupportable")


def test_false_c_and_r_legal_assertion_is_graded_not_rejected() -> None:
    """Asserting §4664 presumption out of a C&R is bad law, not incoherence."""
    contention = _contention(
        claim_type="apportionment_defense",
        party="defense",
        target_condition_id=None,
        target_prior_award_id="prior-02-award",
        rationale="the prior C&R conclusively presumes continuing disability",
    )
    ledger = _ledger(contentions=(contention,))
    assert not _problems(ledger)
    assert contention_quality(_world(), _context(), contention) in ("thin", "unsupportable")


def test_competing_medical_opinions_may_disagree() -> None:
    contention = _contention()
    endorser = _opinion(
        endorses_contention_ids=("ctn-01",),
        determination_kind=None,
        apportionment_state="deferred",
        report_stage="interim",
    )
    rejecter = _opinion(
        "opn-02",
        report_date=dt.date(2023, 8, 1),
        rejects_contention_ids=("ctn-01",),
        determination_kind=None,
        apportionment_state="deferred",
        report_stage="interim",
    )
    ledger = _ledger(contentions=(contention,), opinions=(endorser, rejecter))
    assert not _problems(ledger)


def test_explicit_qme_may_dissent_from_ledger_evidence() -> None:
    """An explicit evaluator endorsing a contradicted claim is graded, kept."""
    contention = _contention()  # contradicted by world truth
    dissenting = _opinion(
        endorses_contention_ids=("ctn-01",),
        determination_kind=None,
        apportionment_state="deferred",
        report_stage="interim",
    )
    ledger = _ledger(contentions=(contention,), opinions=(dissenting,))
    assert not _problems(ledger)
    assert opinion_quality(_world(), _context(), ledger, dissenting) == "unsupportable"


def test_hikida_legal_error_is_graded_not_rejected() -> None:
    contention = _contention(
        claim_type="compensable_consequence",
        target_condition_id="cond-03",
        treatment_causation="sole_cause",
        requested_apportionment="apply",
    )
    ledger = _ledger(contentions=(contention,))
    assert not _problems(ledger, _hikida_world())
    assert contention_quality(_hikida_world(), _context(), contention) == "unsupportable"


def test_vocational_apportionment_is_graded_not_rejected() -> None:
    assert _graded_assertion(
        basis_kinds=("vocational_apportionment",)
    ) == "unsupportable"
    ledger = _ledger(
        opinions=(_opinion(),),
        assertions=(_assertion(basis_kinds=("vocational_apportionment",)),),
    )
    assert not _problems(ledger)


def test_psych_add_on_error_is_graded_not_rejected() -> None:
    ledger = _ledger(
        opinions=(_opinion(),),
        assertions=(
            _assertion(
                basis_kinds=("psych_impairment_add_on",),
                psych_exception_analysis="none_applies",
            ),
        ),
    )
    assert not _problems(ledger)
    assert _graded_assertion(
        basis_kinds=("psych_impairment_add_on",),
        psych_exception_analysis="none_applies",
    ) == "unsupportable"


def test_bare_demographic_basis_is_graded_not_rejected() -> None:
    for basis in ("bare_age", "bare_gender"):
        ledger = _ledger(
            opinions=(_opinion(),), assertions=(_assertion(basis_kinds=(basis,)),)
        )
        assert not _problems(ledger)
        assert _graded_assertion(basis_kinds=(basis,)) == "unsupportable"


def test_rice_genetics_basis_is_weighed_not_barred() -> None:
    assert _graded_assertion(
        basis_kinds=("genetics_heredity_pathology",), condition_ids=("cond-01",)
    ) == "supported"


def test_interim_deferral_is_valid() -> None:
    deferring = _opinion(
        author_role="ptp",
        report_stage="interim",
        apportionment_state="deferred",
        determination_kind=None,
    )
    ledger = _ledger(opinions=(deferring,))
    assert not _problems(ledger)
    # Deferral itself carries no penalty: with a real foundation the opinion
    # stays supported.
    assert opinion_quality(_world(), _context(), ledger, deferring) == "supported"


def test_final_report_omission_is_valid_but_unsupportable() -> None:
    omitting = _opinion(apportionment_state="omitted", determination_kind=None)
    ledger = _ledger(opinions=(omitting,))
    assert not _problems(ledger)
    assert opinion_quality(_world(), _context(), ledger, omitting) == "unsupportable"


def test_ungrounded_entity_hook_warns_and_survives() -> None:
    contention = _contention(
        claim_type="apportionment_defense",
        party="defense",
        doctrine_hooks=("lc4664_prior_award",),
        target_condition_id=None,
        target_prior_award_id="prior-01-award",
    )
    ledger = _ledger(contentions=(contention,))
    assert not _problems(ledger)
    assert assertion_warnings(_world(), ledger) == (
        "medical_assertions: doctrine hook 'lc4664_prior_award' has no typed "
        "MedicalHistory grounding; explicit hook retained",
    )


# ---------------------------------------------------------------------------
# E.4 — the absent gate: nothing constructs behind a missing block
# ---------------------------------------------------------------------------


def test_absent_gate_returns_before_any_assertion_rng_is_constructed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The gate is the first observable. A monkeypatched rng that fails the
    test on construction proves the return happens before ANY stream exists."""
    from typing import NoReturn

    from wc_caseload_engine import medical_assertions as module
    from wc_caseload_engine.medical_history import derive_medical_history

    def fail_if_called(*args: object, **kwargs: object) -> NoReturn:
        pytest.fail("assertion RNG constructed while medical_assertions gate was absent")

    monkeypatch.setattr(module, "_assertion_rng", fail_if_called)

    bare = parse_case_seed(_seed_body({}))
    assert module.derive_medical_assertions(bare, None) is None

    with_history = parse_case_seed(_seed_body({"medical_history": {}}))
    history = derive_medical_history(with_history)
    assert module.derive_medical_assertions(with_history, history) is None


def test_absent_gate_plan_has_no_assertion_ledger_warning_or_truth_channel() -> None:
    from conftest import requires_substrate  # noqa: F401 - marker applied below
    from wc_caseload_engine.planner import build_case_plan
    from wc_caseload_engine.substrate import find_substrate
    from wc_caseload_engine.truth_manifest import build_case_truth_manifest

    if find_substrate() is None:
        pytest.skip("merus-test-data-generator substrate not on disk")

    plan = build_case_plan(parse_case_seed(_seed_body({"medical_history": {}})))
    assert plan.medical_assertions is None
    assert not any("medical_assertions" in warning for warning in plan.warnings)
    truth = build_case_truth_manifest(plan)
    assert "assertions" not in truth["channels"]


def test_reasoned_revision_chain_is_valid() -> None:
    first = _opinion(
        report_stage="interim",
        apportionment_state="deferred",
        determination_kind=None,
        report_date=dt.date(2023, 2, 1),
    )
    revised = _opinion(
        "opn-02",
        report_date=dt.date(2023, 9, 1),
        supersedes_opinion_id="opn-01",
        revision_rationale="after reviewing all the previous data again",
    )
    assertion = _assertion(
        opinion_id="opn-02",
        revised_from_percent=10,
        revision_rationale="after reviewing all the previous data again",
    )
    ledger = _ledger(opinions=(first, revised), assertions=(assertion,))
    assert not _problems(ledger)
    assert apportionment_quality(_world(), _context(), ledger, assertion) == "supported"


# ---------------------------------------------------------------------------
# E.8 — validator polarity through the shipped CLI surfaces
# ---------------------------------------------------------------------------

_DIVERGENT_SCENARIO: dict[str, Any] = {
    "medical_history": {
        "sample_conditions": False,
        "conditions": [
            {
                "label": "nonindustrial lumbar degenerative disease",
                "origin": "nonindustrial",
                "body_part": "lumbar_spine",
                "severity": "moderate",
                "symptomatic_before_doi": True,
            },
            {
                "label": "invasive ductal carcinoma, right breast",
                "body_system": "oncologic",
                "body_part": "breast",
                "wholly_unrelated": True,
                "severity": "severe",
            },
        ],
        "prior_claims": [
            {
                "body_parts": ["lumbar_spine"],
                "date_of_injury": "2015-01-05",
                "resolution_type": "c_and_r",
                "award": {
                    "body_parts": ["lumbar_spine"],
                    "pd_percent": 12,
                    "award_date": "2016-02-01",
                },
            }
        ],
    },
    "medical_assertions": {
        "sample_assertions": False,
        "contentions": [
            # Divergence 1: nonindustrial world condition asserted industrial.
            {
                "id": "ctn-01",
                "claim_type": "industrial_causation",
                "party": "applicant",
                "position": "affirm",
                "target_condition_id": "cond-00",
                "rationale": "the lumbar condition arose from the industrial injury",
            },
            # Divergence 2: a false C&R-presumption legal assertion.
            {
                "id": "ctn-02",
                "claim_type": "apportionment_defense",
                "party": "defense",
                "position": "affirm",
                "target_prior_claim_id": "prior-00",
                "target_prior_award_id": "prior-00-award",
                "doctrine_hooks": ["lc4664_prior_award"],
                "rationale": "the prior compromise and release conclusively presumes",
                "groundings": [
                    {"hook": "lc4664_prior_award", "prior_award_id": "prior-00-award"}
                ],
            },
        ],
        "medical_opinions": [
            {
                "id": "opn-01",
                "author_role": "qme",
                "report_stage": "final",
                "report_date": "2022-06-01",
                "apportionment_state": "determined",
                "determination_kind": "allocated",
                "examination_performed": True,
                "reviewed_condition_ids": ["cond-00", "cond-01"],
                "endorses_contention_ids": ["ctn-01"],
                "rationale": "examined the applicant and reviewed the record",
            }
        ],
        "apportionment_assertions": [
            # Divergence 3: apportioning to the wholly unrelated condition.
            {
                "id": "app-01",
                "opinion_id": "opn-01",
                "body_part": "lumbar_spine",
                "industrial_percent": 70,
                "nonindustrial_percent": 30,
                "basis_kinds": ["nonindustrial_medical_condition"],
                "condition_ids": ["cond-01"],
                "description": "chronic lumbar disability",
                "disability_causation_stated": True,
                "reasonable_medical_probability": True,
                "causal_rationale": "the oncology history is noted in the record",
                "percentage_rationale": "thirty percent reflects the noted history",
            }
        ],
    },
}


def _generate_body(case_id: str, scenario: dict[str, Any]) -> dict[str, Any]:
    body = _seed_body(scenario)
    body["case_id"] = case_id
    body["documents"] = {"format_mix": {"pdf": 1.0}, "global_cap": 6}
    body["output"] = {"formats": ["pdf"]}
    return body


@pytest.mark.slow
def test_validate_out_accepts_every_planted_world_truth_divergence(tmp_path: Any) -> None:
    """A corpus full of legal divergence — false industrial claims, wrong-way
    apportionment, misapplied C&R presumptions — validates clean end to end."""
    from conftest import requires_substrate  # noqa: F401
    from wc_caseload_engine.manifests import generate_caseload, validate_output_tree
    from wc_caseload_engine.substrate import find_substrate

    if find_substrate() is None:
        pytest.skip("merus-test-data-generator substrate not on disk")

    seed = parse_case_seed(_generate_body("divergent-case", dict(_DIVERGENT_SCENARIO)))
    out_dir = tmp_path / "divergent"
    generate_caseload("divergent", [seed], out_dir)
    report = validate_output_tree(out_dir)
    assert report.ok, report.render()
    assert report.truth_manifests == 1


def test_validate_spec_rejects_each_planted_internal_incoherence_with_exact_template(
    tmp_path: Any,
) -> None:
    import yaml
    from click.testing import CliRunner

    from wc_caseload_engine.cli import cli
    from wc_caseload_engine.substrate import find_substrate

    if find_substrate() is None:
        pytest.skip("merus-test-data-generator substrate not on disk")

    incoherent = {
        "caseload_id": "incoherent",
        "cases": [
            {
                **_generate_body("incoherent-case", dict(_DIVERGENT_SCENARIO)),
            }
        ],
    }
    incoherent["cases"][0]["scenario"] = {
        "medical_history": {"sample_conditions": False, "conditions": [
            {"label": "hypertension", "key": "hypertension"},
        ]},
        "medical_assertions": {
            "sample_assertions": False,
            "contentions": [
                {
                    "id": "ctn-01",
                    "claim_type": "industrial_causation",
                    "party": "applicant",
                    "position": "affirm",
                    "target_condition_id": "cond-99",
                    "rationale": "targets a condition the world ledger never held",
                }
            ],
        },
    }
    spec_path = tmp_path / "incoherent.yaml"
    spec_path.write_text(yaml.safe_dump(incoherent), encoding="utf-8")
    result = CliRunner().invoke(cli, ["validate", "--spec", str(spec_path)])
    assert result.exit_code != 0
    assert "contention 'ctn-01' references unknown condition 'cond-99'" in result.output


@pytest.mark.slow
def test_validate_out_rejects_tampered_assertion_incoherence_with_exact_template(
    tmp_path: Any,
) -> None:
    import json

    from wc_caseload_engine.manifests import generate_caseload, validate_output_tree
    from wc_caseload_engine.substrate import find_substrate
    from wc_caseload_engine.truth_manifest import TRUTH_DIR, assertion_ledger_digest

    if find_substrate() is None:
        pytest.skip("merus-test-data-generator substrate not on disk")

    seed = parse_case_seed(_generate_body("tampered-case", dict(_DIVERGENT_SCENARIO)))
    out_dir = tmp_path / "tampered"
    generate_caseload("tampered", [seed], out_dir)
    truth_path = out_dir / TRUTH_DIR / "tampered-case.truth.json"
    payload = json.loads(truth_path.read_text(encoding="utf-8"))
    channel = payload["channels"]["assertions"]
    channel["contentions"][0]["targetConditionId"] = "cond-77"
    channel["ledgerDigest"] = assertion_ledger_digest(channel)
    truth_path.write_text(json.dumps(payload), encoding="utf-8")

    report = validate_output_tree(out_dir)
    assert not report.ok
    rendered = report.render()
    assert "contention 'ctn-01' references unknown condition 'cond-77'" in rendered
