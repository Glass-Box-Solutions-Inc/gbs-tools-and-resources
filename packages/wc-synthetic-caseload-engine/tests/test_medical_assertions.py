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
import json
import re
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
from wc_caseload_engine.medical_story import (
    ADVOCACY_LETTER_SURFACES,
    INITIAL_MEDLEGAL_SURFACES,
    PSYCH_MEDLEGAL_SURFACES,
    PTP_CAUSATION_SURFACES,
    SUPPLEMENTAL_MEDLEGAL_SURFACES,
)
from wc_caseload_engine.seeds import (
    ApportionmentAssertionEntry,
    ContentionEntry,
    DoctrineHook,
    MedicalAssertionsScenario,
    MedicalOpinionEntry,
    parse_case_seed,
    parse_caseload_spec,
)

DOI = dt.date(2022, 4, 11)
ANCHOR = dt.date(2026, 1, 1)

EXPECTED_DOCTRINE_HOOKS = (
    "ogilvie",
    "almaraz_guzman",
    "benson",
    "escobedo",
    "kite",
    "going_and_coming",
    "sibtf",
    "death_dependency",
    "lc3208_3_psych",
    "gfpa",
    "firefighter_presumption",
    "imr_constitutionality",
    "ab5_dynamex",
    "lc4664_prior_award",
    "hikida_treatment_carveout",
)
"""The frozen fifteen-member doctrine oracle, in declaration order (AJC-62 R72).

A deliberate independent literal — never derived from the enum it checks. Both
doctrine test modules freeze this exact tuple so a drifted declaration cannot
re-derive its own oracle green.
"""


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


def _m3_model_inventory() -> tuple[type, ...]:
    """Every AJC-62 step-2 model: internal records plus story projections."""
    from wc_caseload_engine.medical_assertions import (
        ContentionDocumentBinding,
        MedicalAssertionPlan,
    )
    from wc_caseload_engine.medical_story import (
        DocumentMedicalStory,
        ImrApplicationContent,
        MedicalStoryPlan,
        MedicalUrPlan,
        StoryApportionment,
        StoryCondition,
        StoryContention,
        StoryDemographics,
        StoryMedicalOpinion,
        StoryPriorAward,
        StoryPriorClaim,
        StoryRecordReference,
    )

    return (
        ContentionDocumentBinding,
        MedicalAssertionPlan,
        StoryDemographics,
        StoryCondition,
        StoryPriorClaim,
        StoryPriorAward,
        StoryRecordReference,
        StoryContention,
        StoryMedicalOpinion,
        StoryApportionment,
        DocumentMedicalStory,
        MedicalStoryPlan,
        ImrApplicationContent,
        MedicalUrPlan,
    )


def test_assertion_models_are_frozen_strict_and_bound_their_fields() -> None:
    from wc_caseload_engine.medical_story import StoryCondition

    for model in (
        Contention,
        MedicalOpinion,
        ApportionmentAssertion,
        MedicalAssertionLedger,
        *_m3_model_inventory(),
    ):
        assert model.model_config.get("frozen") is True, model.__name__
        assert model.model_config.get("extra") == "forbid", model.__name__
    with pytest.raises(ValidationError):
        Contention(**{**_contention().model_dump(), "surprise": 1})
    frozen = _contention()
    with pytest.raises(ValidationError):
        frozen.quality = "thin"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        _assertion(industrial_percent=101)
    with pytest.raises(ValidationError):
        _opinion(reviewed_condition_ids=tuple(f"cond-{i:02d}" for i in range(9)))
    story_condition = StoryCondition(
        id="cond-01",
        label="lumbar disc degeneration",
        body_system="musculoskeletal",
        severity="moderate",
        trajectory="stable",
    )
    with pytest.raises(ValidationError):
        StoryCondition(**{**story_condition.model_dump(), "quality": "supported"})
    with pytest.raises(ValidationError):
        story_condition.label = "edited"  # type: ignore[misc]


def test_seed_assertion_models_have_no_quality_field() -> None:
    """The copied seed is analyzer-visible; a seed quality field is a leak.

    Expanded for AJC-62 step 2: every new seed entry, internal binding record
    and story projection model is quality-free — R26 forbids any new field
    carrying ``quality``, a derived quality synonym, or an analyzer verdict,
    and R39 forbids the ``thin``/``underworked``/``adequacy`` spellings too.
    """
    from wc_caseload_engine.seeds import ContentionDocumentEntry, ImrApplicationEntry

    for model in (
        ContentionEntry,
        MedicalOpinionEntry,
        ApportionmentAssertionEntry,
        MedicalAssertionsScenario,
        ContentionDocumentEntry,
        ImrApplicationEntry,
        *_m3_model_inventory(),
    ):
        for reserved in (
            "quality",
            "rubric",
            "thin",
            "underworked",
            "adequacy",
            "grade",
            "verdict",
        ):
            assert reserved not in model.model_fields, (model.__name__, reserved)


def test_contention_doctrine_hooks_accept_exactly_the_frozen_fifteen_members_in_order() -> None:
    """AJC-62 R72: the declaration IS the frozen oracle, order included.

    Declaration order is load-bearing — the content table mirrors it and the
    LEGACY/MEDICAL_STORY pool split slices it — so the comparison is against
    the declaration directly, not a sorted view. Every member must also
    round-trip through ``Contention``, proving the schema accepts exactly the
    frozen vocabulary and nothing beside it.
    """
    assert typing.get_args(DoctrineHook.__value__) == EXPECTED_DOCTRINE_HOOKS
    for hook in EXPECTED_DOCTRINE_HOOKS:
        assert _contention(doctrine_hooks=(hook,)).doctrine_hooks == (hook,)
    with pytest.raises(ValidationError):
        _contention(doctrine_hooks=("not_a_doctrine_hook",))


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


def test_dangling_grounding_reference_warns_and_survives() -> None:
    """A typed grounding whose entity ID resolves to no world-truth record
    WARNS and the assertion stands — the frozen §C catalog carries no literal
    for grounding-ID existence, so it is an authoring warning, never a
    validation error (sol open question 3, fix round 1)."""
    contention = _contention(
        doctrine_hooks=("firefighter_presumption",),
        groundings=(FirefighterPresumptionGrounding(condition_id="cond-77"),),
    )
    ledger = _ledger(contentions=(contention,))
    assert not _problems(ledger)
    warnings = assertion_warnings(_world(), ledger)
    assert warnings == (
        "medical_assertions: contention 'ctn-01' grounding for hook "
        "'firefighter_presumption' references unknown condition 'cond-77'; "
        "assertion retained",
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
    monkeypatch.setattr(module, "_medical_story_rng", fail_if_called)

    bare = parse_case_seed(_seed_body({}))
    assert module.derive_medical_assertions(bare, None) is None
    # The gate lives in derive_medical_assertion_plan() (R32/R72 m19-1): the
    # plan entry returns the empty plan — no ledger, no bindings — before any
    # M2 or medical-story stream can exist.
    bare_plan = module.derive_medical_assertion_plan(bare, None)
    assert bare_plan.ledger is None
    assert bare_plan.contention_documents == ()

    with_history = parse_case_seed(_seed_body({"medical_history": {}}))
    history = derive_medical_history(with_history)
    assert module.derive_medical_assertions(with_history, history) is None
    gated_plan = module.derive_medical_assertion_plan(with_history, history)
    assert gated_plan.ledger is None
    assert gated_plan.contention_documents == ()


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


def test_reasoned_supplemental_revision_chain_is_valid() -> None:
    """R72's stronger revision witness (replacing the M2 chain test): a true
    R37 supplemental response — ``event_kind="supplemental_report"``, the
    compatible ``revision_kind="revised_apportionment"``, the exact
    responds-to/supersedes predecessor relationship, same QME author, no fresh
    examination — is coherent, and the reasoned revision itself (item 10) is
    not a defect (*Lindh*)."""
    first = _opinion(
        report_stage="interim",
        apportionment_state="deferred",
        determination_kind=None,
        report_date=dt.date(2023, 2, 1),
    )
    revised = _opinion(
        "opn-02",
        report_date=dt.date(2023, 9, 1),
        event_kind="supplemental_report",
        revision_kind="revised_apportionment",
        responds_to_opinion_id="opn-01",
        supersedes_opinion_id="opn-01",
        examination_performed=False,
        revision_rationale="after reviewing all the previous data again",
    )
    assertion = _assertion(
        opinion_id="opn-02",
        revised_from_percent=10,
        revision_rationale="after reviewing all the previous data again",
    )
    ledger = _ledger(opinions=(first, revised), assertions=(assertion,))
    assert not _problems(ledger)
    # The frozen M2 rubric predates response events: item 5a fires on ANY
    # no-examination owner, and R37 forbids a fresh examination on a
    # supplemental response, so this chain's single miss is exactly 5a and it
    # grades thin under the shipped checklist. The reasoned revision (item 10)
    # is NOT among the misses — that is the *Lindh* half the old test proved.
    # Step 4's response-semantics remodel owns any response-aware 5a change;
    # step 2 changes no grading.
    assert escobedo_misses(_world(), ledger, assertion) == ("5a",)
    assert apportionment_quality(_world(), _context(), ledger, assertion) == "thin"


# ---------------------------------------------------------------------------
# AJC-62 (M3) step 2 — model deltas, seed mirrors, and strict validation
# ---------------------------------------------------------------------------

EXPECTED_OPINION_EVENT_KINDS = ("base_report", "supplemental_report", "deposition")
EXPECTED_OPINION_REVISION_KINDS = (
    "unchanged_additional_reasoning",
    "new_records_no_change",
    "revised_causation",
    "revised_apportionment",
    "revised_causation_and_apportionment",
)
EXPECTED_OPINION_CONTENTION_DISPOSITIONS = (
    "adopted",
    "concurred",
    "rejected",
    "deferred",
    "unaddressed",
)
EXPECTED_DEFENSE_CONTEST_THEORIES = (
    "insufficient_investigation",
    "post_termination",
    "lack_of_substantial_medical_evidence",
)
EXPECTED_CONTEST_PATHS = (
    "objection_only",
    "objection_supplemental",
    "objection_deposition",
    "objection_supplemental_deposition",
    "supplemental_only",
    "supplemental_deposition",
)
EXPECTED_CONTENTION_DOCUMENT_KINDS = (
    "opinion_report",
    "advocacy",
    "objection",
    "supplemental_request",
    "supplemental_report",
    "qme_deposition",
)
EXPECTED_PSYCH_INJURY_KINDS = ("direct", "compensable_consequence")
EXPECTED_AOE_COE_FINDINGS = ("industrial", "nonindustrial", "deferred")


def test_m3_literals_are_exactly_the_frozen_vocabularies_in_order() -> None:
    """R6/R26/R4: the declarations ARE the frozen vocabularies, order included."""
    import wc_caseload_engine.medical_assertions as module
    from wc_caseload_engine.medical_history import PsychInjuryKind
    from wc_caseload_engine.medical_story import ContentionSurface

    assert (
        typing.get_args(module.OpinionEventKind.__value__)
        == EXPECTED_OPINION_EVENT_KINDS
    )
    assert (
        typing.get_args(module.OpinionRevisionKind.__value__)
        == EXPECTED_OPINION_REVISION_KINDS
    )
    assert (
        typing.get_args(module.OpinionContentionDisposition.__value__)
        == EXPECTED_OPINION_CONTENTION_DISPOSITIONS
    )
    assert (
        typing.get_args(module.DefenseContestTheory.__value__)
        == EXPECTED_DEFENSE_CONTEST_THEORIES
    )
    assert typing.get_args(module.ContestPath.__value__) == EXPECTED_CONTEST_PATHS
    assert (
        typing.get_args(module.ContentionDocumentKind.__value__)
        == EXPECTED_CONTENTION_DOCUMENT_KINDS
    )
    assert typing.get_args(PsychInjuryKind.__value__) == EXPECTED_PSYCH_INJURY_KINDS
    assert typing.get_args(module.AoeCoeFinding.__value__) == EXPECTED_AOE_COE_FINDINGS
    assert module.CDOC_ID_PATTERN == r"^cdoc-(0[1-9]|[1-9][0-9])$"
    assert typing.get_args(ContentionSurface.__value__) == (
        "advocacy",
        "objection",
        "supplemental_request",
        "qme_deposition",
    )


def test_condition_psych_injury_kind_requires_a_psychiatric_body_system() -> None:
    from wc_caseload_engine.medical_history import MedicalCondition
    from wc_caseload_engine.seeds import MedicalConditionEntry

    psychiatric = MedicalCondition(
        id="cond-09",
        key="seeded",
        label="post-traumatic stress disorder",
        body_system="psychiatric",
        body_part="psyche",
        psych_injury_kind="compensable_consequence",
    )
    assert psychiatric.psych_injury_kind == "compensable_consequence"
    with pytest.raises(ValidationError, match="psychiatric"):
        MedicalCondition(
            id="cond-09",
            key="seeded",
            label="lumbar strain",
            body_system="musculoskeletal",
            psych_injury_kind="direct",
        )
    entry = MedicalConditionEntry(
        label="post-traumatic stress disorder",
        body_system="psychiatric",
        body_part="psyche",
        psych_injury_kind="direct",
    )
    assert entry.psych_injury_kind == "direct"
    with pytest.raises(ValidationError, match="psychiatric"):
        MedicalConditionEntry(label="lumbar strain", psych_injury_kind="direct")


def _psych_world() -> AssertionWorldProjection:
    return _world(
        conditions=(
            _condition(),
            _condition(
                "cond-02",
                key="seeded",
                label="post-traumatic stress disorder",
                body_system="psychiatric",
                body_part="psyche",
                apportionment_targets=("psyche",),
                wholly_unrelated=False,
                symptomatic_before_doi=False,
            ),
        )
    )


def test_contention_and_opinion_psych_kind_require_a_psychiatric_anchor() -> None:
    """R6: an anchored psych kind validates; an unanchored one fails §C."""
    psych_world = _psych_world()
    anchored = _contention(psych_injury_kind="direct", target_condition_id="cond-02")
    assert not _problems(_ledger(contentions=(anchored,)), psych_world)
    by_part = _contention(
        psych_injury_kind="direct", target_condition_id=None, target_body_part="psyche"
    )
    assert not _problems(_ledger(contentions=(by_part,)), psych_world)
    by_claim = _contention(psych_injury_kind="direct")
    assert not _problems(
        _ledger(contentions=(by_claim,)),
        context=_context(current_body_parts=("lumbar_spine", "psyche")),
    )
    unanchored = _contention(psych_injury_kind="direct")
    problems = _problems(_ledger(contentions=(unanchored,)))
    assert (
        "contention 'ctn-01' sets psych_injury_kind 'direct' without a "
        "psychiatric target condition, a psyche target body part, or a psyche "
        "claim body part"
    ) in problems

    reviewed = _opinion(
        psych_injury_kind="compensable_consequence",
        determination_kind="no_nonindustrial_share",
        reviewed_condition_ids=("cond-02",),
    )
    assert not _problems(_ledger(opinions=(reviewed,)), psych_world)
    via_contention = _opinion(
        psych_injury_kind="compensable_consequence",
        determination_kind="no_nonindustrial_share",
        reviewed_condition_ids=(),
        rejects_contention_ids=("ctn-01",),
    )
    assert not _problems(
        _ledger(contentions=(anchored,), opinions=(via_contention,)), psych_world
    )
    stray = _opinion(
        psych_injury_kind="direct", determination_kind="no_nonindustrial_share"
    )
    assert (
        "medical opinion 'opn-01' sets psych_injury_kind 'direct' without a "
        "psychiatric reviewed condition, a psyche claim body part, or a "
        "referenced psychiatric contention"
    ) in _problems(_ledger(opinions=(stray,)))


def test_psych_kind_divergence_across_layers_is_legal_case_content() -> None:
    """R6/R17: world consequence, applicant/PTP direct framing, QME consequence
    re-derivation — all three layers disagree and the ledger stays coherent.
    Divergence grades and renders; it never fails."""
    psych_world = _psych_world()
    applicant_direct = _contention(
        claim_type="psych_add_on",
        target_condition_id="cond-02",
        target_body_part="psyche",
        psych_injury_kind="direct",
    )
    ptp_direct = _opinion(
        author_role="ptp",
        report_stage="interim",
        apportionment_state="deferred",
        determination_kind=None,
        report_date=dt.date(2023, 2, 1),
        psych_injury_kind="direct",
        aoe_coe_finding="industrial",
        aoe_coe_rationale="the mechanism and clinical course support causation",
        reviewed_condition_ids=("cond-02",),
    )
    qme_consequence = _opinion(
        "opn-02",
        report_date=dt.date(2023, 6, 1),
        determination_kind="no_nonindustrial_share",
        psych_injury_kind="compensable_consequence",
        aoe_coe_finding="industrial",
        reviewed_condition_ids=("cond-02",),
    )
    ledger = _ledger(
        contentions=(applicant_direct,), opinions=(ptp_direct, qme_consequence)
    )
    assert not _problems(ledger, psych_world)


def test_four_disposition_collections_are_pairwise_disjoint_and_resolve() -> None:
    """R26: pairwise disjointness across all four collections, dangling refs
    fail, and the M2 endorses/rejects template survives byte for byte."""
    base = _contention()
    for first, second in (
        ("endorses_contention_ids", "concurs_with_contention_ids"),
        ("endorses_contention_ids", "defers_contention_ids"),
        ("concurs_with_contention_ids", "rejects_contention_ids"),
        ("concurs_with_contention_ids", "defers_contention_ids"),
        ("rejects_contention_ids", "defers_contention_ids"),
    ):
        overlapping = _opinion(**{first: ("ctn-01",), second: ("ctn-01",)})
        problems = _problems(_ledger(contentions=(base,), opinions=(overlapping,)))
        assert any("both" in p and "'ctn-01'" in p for p in problems), (first, second)
    for collection, verb in (
        ("concurs_with_contention_ids", "concurs with"),
        ("defers_contention_ids", "defers"),
    ):
        dangling = _opinion(**{collection: ("ctn-77",)})
        assert (
            f"medical opinion 'opn-01' {verb} unknown contention 'ctn-77'"
            in _problems(_ledger(opinions=(dangling,)))
        )
    both = _opinion(
        endorses_contention_ids=("ctn-01",), rejects_contention_ids=("ctn-01",)
    )
    assert (
        "medical opinion 'opn-01' both endorses and rejects contention 'ctn-01'"
        in _problems(_ledger(contentions=(base,), opinions=(both,)))
    )


def test_response_opinion_structure_is_strict_and_base_reports_stay_free() -> None:
    """R26/R27/R37 structure: each required response-opinion property has an
    independent reject, and the ledger-level author-parity rule fires."""
    with pytest.raises(ValidationError, match="base_report"):
        _opinion(revision_kind="revised_causation")
    with pytest.raises(ValidationError, match="PTP"):
        _opinion(
            author_role="ptp",
            event_kind="supplemental_report",
            revision_kind="new_records_no_change",
            responds_to_opinion_id="opn-09",
            examination_performed=False,
        )
    with pytest.raises(ValidationError, match="revision_kind"):
        _opinion(
            event_kind="supplemental_report",
            responds_to_opinion_id="opn-09",
            examination_performed=False,
        )
    with pytest.raises(ValidationError, match="responds_to_opinion_id"):
        _opinion(
            event_kind="supplemental_report",
            revision_kind="new_records_no_change",
            examination_performed=False,
        )
    with pytest.raises(ValidationError, match="examination"):
        _opinion(
            event_kind="deposition",
            revision_kind="unchanged_additional_reasoning",
            responds_to_opinion_id="opn-09",
            examination_performed=True,
        )
    with pytest.raises(ValidationError, match="rationale"):
        _opinion(
            event_kind="deposition",
            revision_kind="unchanged_additional_reasoning",
            responds_to_opinion_id="opn-09",
            examination_performed=False,
            rationale=None,
            revision_rationale=None,
        )
    # The seed mirror rejects the same shapes with its own dotted path.
    with pytest.raises(ValidationError, match="medical_opinions"):
        MedicalOpinionEntry(
            id="opn-01",
            author_role="ptp",
            report_stage="final",
            report_date=dt.date(2023, 6, 1),
            apportionment_state="determined",
            determination_kind="no_nonindustrial_share",
            event_kind="deposition",
            revision_kind="unchanged_additional_reasoning",
            responds_to_opinion_id="opn-02",
            rationale="testimony",
        )
    # §C: a response opinion keeps its predecessor's author role.
    first = _opinion(
        author_role="ame",
        report_date=dt.date(2023, 2, 1),
        determination_kind="no_nonindustrial_share",
    )
    mismatched = _opinion(
        "opn-02",
        author_role="qme",
        event_kind="supplemental_report",
        revision_kind="new_records_no_change",
        responds_to_opinion_id="opn-01",
        examination_performed=False,
        report_date=dt.date(2023, 6, 1),
        determination_kind="no_nonindustrial_share",
    )
    problems = _problems(
        _ledger(opinions=(first, mismatched)), context=_context(eval_type="none")
    )
    assert (
        "medical opinion 'opn-02' has author_role 'qme' but its predecessor "
        "'opn-01' has author_role 'ame'; a supplemental or deposition opinion "
        "keeps its predecessor's author"
    ) in problems


def _cdoc(**overrides: Any) -> Any:
    from wc_caseload_engine.seeds import ContentionDocumentEntry

    values: dict[str, Any] = {
        "id": "cdoc-01",
        "document_kind": "advocacy",
        "target_medical_opinion_id": "opn-01",
        "actor_party": "applicant",
        "spoken_contention_ids": ["ctn-01"],
    }
    values.update(overrides)
    return ContentionDocumentEntry(**values)


def test_contention_document_entries_enforce_the_r40_field_matrix() -> None:
    """R26/R40: the per-kind required/forbidden matrix, the defense-theory
    rule, the cdoc ID pattern and the three-contention bundle cap."""
    assert _cdoc().document_kind == "advocacy"
    assert (
        _cdoc(
            id="cdoc-02",
            document_kind="objection",
            actor_party="defense",
            defense_contest_theories=["post_termination"],
        ).actor_party
        == "defense"
    )
    assert (
        _cdoc(
            id="cdoc-03",
            document_kind="opinion_report",
            medical_opinion_id="opn-01",
            target_medical_opinion_id=None,
            actor_party=None,
            spoken_contention_ids=[],
        ).medical_opinion_id
        == "opn-01"
    )
    assert (
        _cdoc(
            id="cdoc-04",
            document_kind="supplemental_report",
            medical_opinion_id="opn-02",
            target_medical_opinion_id="opn-01",
            actor_party=None,
            spoken_contention_ids=[],
        ).target_medical_opinion_id
        == "opn-01"
    )
    assert (
        _cdoc(
            id="cdoc-05",
            document_kind="qme_deposition",
            medical_opinion_id="opn-03",
            target_medical_opinion_id="opn-02",
            actor_party="defense",
            defense_contest_theories=["insufficient_investigation"],
        ).document_kind
        == "qme_deposition"
    )

    with pytest.raises(ValidationError):
        _cdoc(id="cdoc-00")
    with pytest.raises(ValidationError, match="medical_opinion_id"):
        _cdoc(
            document_kind="opinion_report",
            target_medical_opinion_id=None,
            actor_party=None,
            spoken_contention_ids=[],
        )
    with pytest.raises(ValidationError, match="target_medical_opinion_id"):
        _cdoc(target_medical_opinion_id=None)
    with pytest.raises(ValidationError, match="target_medical_opinion_id"):
        _cdoc(
            document_kind="opinion_report",
            medical_opinion_id="opn-01",
            actor_party=None,
            spoken_contention_ids=[],
        )
    with pytest.raises(ValidationError, match="actor_party"):
        _cdoc(actor_party=None)
    with pytest.raises(ValidationError, match="actor_party"):
        _cdoc(
            document_kind="supplemental_report",
            medical_opinion_id="opn-02",
            target_medical_opinion_id="opn-01",
            spoken_contention_ids=[],
        )
    with pytest.raises(ValidationError, match="spoken_contention_ids"):
        _cdoc(spoken_contention_ids=[])
    with pytest.raises(ValidationError, match="medical_opinion_id"):
        _cdoc(medical_opinion_id="opn-01")
    with pytest.raises(ValidationError, match="defense_contest_theories"):
        _cdoc(id="cdoc-02", document_kind="objection", actor_party="defense")
    with pytest.raises(ValidationError, match="defense_contest_theories"):
        _cdoc(defense_contest_theories=["post_termination"])
    with pytest.raises(ValidationError):
        _cdoc(spoken_contention_ids=["ctn-01", "ctn-02", "ctn-03", "ctn-04"])


def test_contention_documents_collection_caps_ids_and_references() -> None:
    """R26/R40: the scenario collection parses, caps at 15, rejects duplicate
    ids, rejects reserved truth-label keys anywhere beneath it, and resolves
    every explicit reference before sampling."""
    body = _seed_body(
        {
            "medical_history": {},
            "medical_assertions": {
                "sample_assertions": False,
                "contentions": [
                    {
                        "id": "ctn-01",
                        "claim_type": "industrial_causation",
                        "party": "applicant",
                        "rationale": "the injury is industrial",
                    }
                ],
                "medical_opinions": [
                    {
                        "id": "opn-01",
                        "author_role": "qme",
                        "report_stage": "final",
                        "report_date": "2023-06-01",
                        "apportionment_state": "determined",
                        "determination_kind": "no_nonindustrial_share",
                        "rationale": "reasoned industrial conclusion",
                    }
                ],
                "contention_documents": [
                    {
                        "id": "cdoc-01",
                        "document_kind": "advocacy",
                        "target_medical_opinion_id": "opn-01",
                        "actor_party": "applicant",
                        "spoken_contention_ids": ["ctn-01"],
                    }
                ],
            },
        }
    )
    seed = parse_case_seed(body)
    scenario = seed.scenario.medical_assertions
    assert scenario is not None
    assert scenario.sample_contention_documents is True
    assert scenario.contention_documents[0].id == "cdoc-01"

    duplicate = json.loads(json.dumps(body))
    duplicate["scenario"]["medical_assertions"]["contention_documents"].append(
        {
            "id": "cdoc-01",
            "document_kind": "advocacy",
            "target_medical_opinion_id": "opn-01",
            "actor_party": "defense",
            "spoken_contention_ids": ["ctn-01"],
        }
    )
    with pytest.raises(Exception, match="duplicate id 'cdoc-01'"):
        parse_case_seed(duplicate)

    labelled = json.loads(json.dumps(body))
    labelled["scenario"]["medical_assertions"]["contention_documents"][0][
        "quality"
    ] = "thin"
    with pytest.raises(Exception, match="reserved truth-label field"):
        parse_case_seed(labelled)

    overflowing = json.loads(json.dumps(body))
    overflowing["scenario"]["medical_assertions"]["contention_documents"] = [
        {
            "id": f"cdoc-{index:02d}",
            "document_kind": "advocacy",
            "target_medical_opinion_id": "opn-01",
            "actor_party": "applicant",
            "spoken_contention_ids": ["ctn-01"],
        }
        for index in range(1, 17)
    ]
    with pytest.raises(Exception, match="at most 15"):
        parse_case_seed(overflowing)

    from wc_caseload_engine.medical_assertions import (
        MedicalAssertionError,
        derive_medical_assertions,
    )
    from wc_caseload_engine.medical_history import derive_medical_history

    dangling = json.loads(json.dumps(body))
    dangling["scenario"]["medical_assertions"]["contention_documents"][0][
        "spoken_contention_ids"
    ] = ["ctn-09"]
    bad_seed = parse_case_seed(dangling)
    with pytest.raises(MedicalAssertionError, match="ctn-09"):
        derive_medical_assertions(bad_seed, derive_medical_history(bad_seed))

    unresolved = json.loads(json.dumps(body))
    unresolved["scenario"]["medical_assertions"]["contention_documents"][0][
        "target_medical_opinion_id"
    ] = "opn-09"
    bad_seed = parse_case_seed(unresolved)
    with pytest.raises(MedicalAssertionError, match="opn-09"):
        derive_medical_assertions(bad_seed, derive_medical_history(bad_seed))


def test_imr_application_entry_parses_and_guards_its_gate() -> None:
    """R39: the explicit IMR application block parses sparse or full, requires
    the UR dispute, and cannot coexist with an authored ``imr: false``."""
    from wc_caseload_engine.seeds import ImrApplicationEntry, UrDispute

    entry = ImrApplicationEntry(
        disputed_treatment="lumbar epidural steroid injection",
        diagnosis_icd10="M54.5",
        ur_determination_attached=True,
        supporting_record_subtypes=["TREATING_PHYSICIAN_REPORT_PR2"],
        clinical_rebuttal="the denial misreads the imaging",
        mtus_citations=["MTUS 2016, Low Back Complaints"],
    )
    assert entry.ur_determination_attached is True
    sparse = ImrApplicationEntry()
    assert sparse.disputed_treatment is None
    assert sparse.supporting_record_subtypes == []
    assert "disputed_treatment" not in sparse.model_dump(exclude_none=True)

    dispute = UrDispute(
        enabled=True, decision="upheld", imr=True, imr_application=ImrApplicationEntry()
    )
    assert dispute.imr_application is not None
    with pytest.raises(ValidationError, match="enabled"):
        UrDispute(imr_application=ImrApplicationEntry())
    with pytest.raises(ValidationError, match="explicitly false"):
        UrDispute(
            enabled=True,
            decision="upheld",
            imr=False,
            imr_application=ImrApplicationEntry(),
        )
    unauthored = UrDispute(enabled=True, decision="upheld")
    assert "imr" not in unauthored.model_fields_set


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


# ---------------------------------------------------------------------------
# E.7 — the label-position leakage anti-probe
# ---------------------------------------------------------------------------

#: Structured keys that are truth-label positions wherever they appear in an
#: analyzer-visible mapping.
RESERVED_LABEL_KEYS = frozenset({"quality", "rubric", "assertionQuality", "medicalAssertions"})

#: The one label token rare enough to sweep bare (case-folded, whole word).
#: ``supported`` and ``thin`` are ordinary English the shipped corpus already
#: contains; scanning them bare can only be made green by weakening the probe.
BARE_LABEL_TOKEN = "unsupportable"

#: Named exemptions for residual bare-token overlap. Every entry must identify
#: the analyzer-visible surface that makes the occurrence legitimate. Empty —
#: and the probe's positive controls keep it honest rather than forgotten.
ASSERTION_LEAKAGE_EXEMPTIONS: dict[str, str] = {}

_BARE_TOKEN = re.compile(r"(?<![a-z])unsupportable(?![a-z])")

PRIVATE_PSYCH_REGISTER_KEYS = (
    "safety_officer_ptsd",
    "harassment_gfpa",
    "compensable_consequence",
    "direct_physical_event",
)

R90_FORBIDDEN_VOCABULARY = (
    "real",
    "bogus",
    "good",
    "bad",
    "adequate",
    "inadequate",
    "thin",
    "underworked",
    "quality",
)

_RESERVED_LABEL_POSITION = re.compile(
    r"(?<![a-z0-9_])"
    r"[\"']?(quality|rubric|assertionQuality|medicalAssertions)[\"']?"
    r"\s*[:=]\s*[\"']?(supported|thin|unsupportable)(?![a-z])",
    re.IGNORECASE,
)

MEDICAL_STORY_LEAKAGE_FAMILIES = (
    ("initial_medlegal", INITIAL_MEDLEGAL_SURFACES, None),
    ("psych_medlegal", PSYCH_MEDLEGAL_SURFACES, None),
    ("supplemental_medlegal", SUPPLEMENTAL_MEDLEGAL_SURFACES, None),
    ("ptp", PTP_CAUSATION_SURFACES, None),
    ("advocacy", ADVOCACY_LETTER_SURFACES, "advocacy"),
    (
        "objection",
        frozenset({"ADVOCACY_LETTERS_PTP_QME_AME"}),
        "objection",
    ),
    (
        "supplemental_request",
        frozenset({"ADVOCACY_LETTERS_PTP_QME_AME"}),
        "supplemental_request",
    ),
    (
        "qme_deposition",
        frozenset({"DEPOSITION_TRANSCRIPT"}),
        "qme_deposition",
    ),
)


def _private_psych_register_findings(payload: Any, path: str) -> list[str]:
    """Find renderer-private selector keys without banning the public injury kind."""
    findings: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            here = f"{path}.{key}"
            if key in PRIVATE_PSYCH_REGISTER_KEYS:
                findings.append(f"private psych register key {here}")
            if (
                isinstance(value, str)
                and value in PRIVATE_PSYCH_REGISTER_KEYS
                and not (
                    key == "psych_injury_kind"
                    and value == "compensable_consequence"
                )
            ):
                findings.append(f"private psych register value {here}={value}")
            findings.extend(_private_psych_register_findings(value, here))
    elif isinstance(payload, list):
        for index, item in enumerate(payload):
            findings.extend(_private_psych_register_findings(item, f"{path}[{index}]"))
    return findings


def _leakage_reserved_key_findings(payload: Any, path: str) -> list[str]:
    findings: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            here = f"{path}.{key}"
            if key in RESERVED_LABEL_KEYS:
                findings.append(f"reserved key {here}")
            findings.extend(_leakage_reserved_key_findings(value, here))
    elif isinstance(payload, list):
        for index, item in enumerate(payload):
            findings.extend(_leakage_reserved_key_findings(item, f"{path}[{index}]"))
    return findings


def _without_legal_phrase_exemptions(text: str) -> str:
    """Remove mandated legal phrases before applying R90's vocabulary."""
    return (
        text.lower()
        .replace("good-faith", "")
        .replace("good faith", "")
        .replace("adequate examination", "")
        .replace("adequate history", "")
        .replace("adequate understanding", "")
    )


def _without_public_psych_kind(text: str) -> str:
    """Keep the public injury kind while banning the private selector token."""
    return re.sub(
        r"[\"']?psych_injury_kind[\"']?\s*[:=]\s*"
        r"[\"']?compensable_consequence[\"']?",
        "",
        text,
        flags=re.IGNORECASE,
    )


def _bare_and_private_text_findings(text: str, where: str) -> list[str]:
    """Find the bare M2 label and renderer-private selector vocabulary."""
    findings: list[str] = []
    lowered = text.lower()
    if _BARE_TOKEN.search(lowered) and where not in ASSERTION_LEAKAGE_EXEMPTIONS:
        findings.append(f"bare token at {where}")
    normalized = _without_public_psych_kind(lowered)
    findings.extend(
        f"private psych register token at {where}:{key}"
        for key in PRIVATE_PSYCH_REGISTER_KEYS
        if re.search(rf"\b{re.escape(key)}\b", normalized)
    )
    return findings


def _r90_text_findings(text: str, where: str) -> list[str]:
    """Find every R90 quality-commentary word, after legal exemptions."""
    normalized = _without_legal_phrase_exemptions(text)
    return [
        f"forbidden production vocabulary at {where}:{word}"
        for word in R90_FORBIDDEN_VOCABULARY
        if re.search(rf"\b{re.escape(word)}\b", normalized)
    ]


def test_r90_allows_clinical_adequate_phrases_but_rejects_quality_commentary() -> None:
    clinical = (
        "The evaluator obtained an adequate history and demonstrated "
        "adequate understanding."
    )
    assert _r90_text_findings(clinical, "probe") == []
    assert _r90_text_findings("adequate report", "probe") == [
        "forbidden production vocabulary at probe:adequate"
    ]


def _label_position_findings(text: str, where: str) -> list[str]:
    """Find only reserved-key label syntax, not ordinary supported/thin prose."""
    return [
        f"reserved label position at {where}:{match.group(1)}={match.group(2)}"
        for match in _RESERVED_LABEL_POSITION.finditer(text)
    ]


def _decoded_text_findings(text: str, where: str) -> list[str]:
    """The shared scanner for analyzer-visible decoded semantic text."""
    return [
        *_bare_and_private_text_findings(text, where),
        *_r90_text_findings(text, where),
        *_label_position_findings(text, where),
    ]


def _ocr_png(png: bytes) -> str:
    """Tesseract over one rasterized page — the OCR-only text surface."""
    import os
    import subprocess

    environment = os.environ.copy()
    environment["OMP_THREAD_LIMIT"] = "1"
    completed = subprocess.run(
        ["tesseract", "stdin", "stdout"],
        input=png,
        capture_output=True,
        check=True,
        env=environment,
    )
    return completed.stdout.decode("utf-8", errors="replace")


def test_assertion_leakage_ocr_limits_tesseract_to_one_worker(monkeypatch) -> None:
    """The OCR probe stays deterministic and bounded on shared CI runners."""
    import os
    import subprocess

    sentinel = b"sentinel-png-bytes"
    captured: dict[str, Any] = {}

    class Completed:
        stdout = b"decoded OCR text\n"

    def fake_run(args: list[str], **kwargs: Any) -> Completed:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return Completed()

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert _ocr_png(sentinel) == "decoded OCR text\n"
    assert captured["args"] == ["tesseract", "stdin", "stdout"]
    assert captured["kwargs"]["input"] == sentinel
    assert captured["kwargs"]["capture_output"] is True
    assert captured["kwargs"]["check"] is True
    assert captured["kwargs"]["env"] is not os.environ
    assert captured["kwargs"]["env"]["OMP_THREAD_LIMIT"] == "1"


def _scan_assertion_leakage(
    out_dir: Any, cli_streams: tuple[str, str] | None = None
) -> tuple[list[str], list[str]]:
    """Every label-position finding + the inventory of surfaces read.

    Surfaces: structured keys in seed.yaml / case_facts.yaml / manifest.json /
    caseload_manifest.json; the bare ``unsupportable`` token in every file's
    raw bytes, every filename, relpath and directory name; DOCX body XML plus
    ``docProps`` parsed as key/value properties (reserved-key detection on the
    property NAMES); the PDF Info dictionary raw (custom keys included —
    ``document.metadata`` exposes only the standard ones), the XMP packet
    parsed so element and attribute NAMES are keys (an unparseable packet
    fails loudly), annotations through BOTH ``annotation.info`` and the raw
    xref key enumeration (``.info`` cannot see a custom key), and page text;
    OCR over image-only pages (an unscannable OCR-only surface fails loudly
    rather than passing silently); decoded EML parts (a base64 body hides the
    token from the raw-bytes sweep) and EML header names; and the CLI
    stdout/stderr when supplied. The truth/ subtree is the ONLY exclusion —
    it is the scorer boundary the labels are supposed to live behind.
    """
    import email
    import email.policy
    import io
    import shutil
    import zipfile
    from pathlib import Path
    from xml.etree import ElementTree

    import yaml as yaml_module

    out = Path(out_dir)
    findings: list[str] = []
    surfaces: list[str] = []
    tesseract_missing = shutil.which("tesseract") is None

    def note_token(text: str, where: str) -> None:
        findings.extend(_decoded_text_findings(text, where))

    def note_raw_token(text: str, where: str) -> None:
        findings.extend(_bare_and_private_text_findings(text, where))
        findings.extend(_label_position_findings(text, where))

    def note_reserved(payload: Any, where: str) -> None:
        findings.extend(_leakage_reserved_key_findings(payload, where))
        findings.extend(_private_psych_register_findings(payload, where))

    def note_r90_vocabulary(payload: Any, where: str) -> None:
        findings.extend(_r90_text_findings(json.dumps(payload, default=str), where))

    for path in sorted(out.rglob("*")):
        rel = path.relative_to(out).as_posix()
        if rel == "truth" or rel.startswith("truth/"):
            continue
        note_raw_token(rel, f"path:{rel}")
        if path.is_dir():
            continue
        surfaces.append(rel)
        raw = path.read_bytes()
        note_raw_token(raw.decode("utf-8", errors="ignore"), f"bytes:{rel}")
        if path.name in ("seed.yaml", "case_facts.yaml"):
            payload = yaml_module.safe_load(raw.decode("utf-8"))
            note_reserved(payload, rel)
            if path.name == "seed.yaml":
                note_r90_vocabulary(payload, rel)
        elif path.suffix == ".json":
            payload = json.loads(raw.decode("utf-8"))
            note_reserved(payload, rel)
            if path.name in ("manifest.json", "caseload_manifest.json"):
                note_r90_vocabulary(payload, rel)
        elif path.suffix == ".docx":
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                for name in archive.namelist():
                    if name.endswith(".xml"):
                        surfaces.append(f"{rel}!{name}")
                        note_token(
                            archive.read(name).decode("utf-8", errors="replace"),
                            f"docx:{rel}!{name}",
                        )
                        if name.startswith("docProps/"):
                            # Structured read: element local names and custom
                            # <property name="..."> attributes are KEYS, so
                            # the reserved-key detection applies to parsed
                            # DOCX properties, not just their bytes.
                            properties: dict[str, str] = {}
                            try:
                                root = ElementTree.fromstring(archive.read(name))
                            except ElementTree.ParseError as error:
                                raise RuntimeError(
                                    f"docx-properties:{rel}!{name} is malformed XML; "
                                    "the reserved-key scan cannot certify property names"
                                ) from error
                            for element in root.iter():
                                local = element.tag.rsplit("}", 1)[-1]
                                properties[local] = element.text or ""
                                named = element.attrib.get("name")
                                if named is not None:
                                    properties[named] = element.text or ""
                            note_reserved(
                                properties, f"docx-properties:{rel}!{name}"
                            )
        elif path.suffix == ".pdf":
            fitz = pytest.importorskip("fitz")
            with fitz.open(path) as document:
                surfaces.append(f"{rel}!metadata")
                note_token(
                    json.dumps(document.metadata or {}), f"pdf-metadata:{rel}"
                )
                info_type, info_value = document.xref_get_key(-1, "Info")
                if info_type == "xref":
                    info_xref = int(info_value.split()[0])
                    info = {
                        key: document.xref_get_key(info_xref, key)[1]
                        for key in document.xref_get_keys(info_xref)
                    }
                    surfaces.append(f"{rel}!info")
                    note_reserved(info, f"pdf-info:{rel}")
                    note_token(json.dumps(info), f"pdf-info:{rel}")
                xmp_xref = document.xref_xml_metadata()
                if xmp_xref:
                    xmp_text = document.xref_stream(xmp_xref).decode(
                        "utf-8", errors="replace"
                    )
                    note_token(xmp_text, f"pdf-xmp:{rel}")
                    # Structured read: XMP element and attribute NAMES are
                    # keys — a property named assertionQuality is exactly as
                    # loud as one valued unsupportable. An XMP packet the
                    # parser cannot read fails the scan rather than passing
                    # silently (same discipline as the OCR surface).
                    try:
                        xmp_root = ElementTree.fromstring(xmp_text)
                    except ElementTree.ParseError as error:
                        raise RuntimeError(
                            f"pdf-xmp:{rel} carries an XMP packet that does "
                            f"not parse ({error}); the reserved-key scan "
                            "cannot certify element and attribute names it "
                            "cannot read"
                        ) from error
                    xmp_keys: dict[str, str] = {}
                    for element in xmp_root.iter():
                        xmp_keys[element.tag.rsplit("}", 1)[-1]] = element.text or ""
                        for attribute, value in element.attrib.items():
                            xmp_keys[attribute.rsplit("}", 1)[-1]] = value
                    surfaces.append(f"{rel}!xmp")
                    note_reserved(xmp_keys, f"pdf-xmp:{rel}")
                for page in document:
                    for annotation in page.annots() or ():
                        note_reserved(
                            dict(annotation.info), f"pdf-annotation:{rel}"
                        )
                        note_token(
                            json.dumps(annotation.info), f"pdf-annotation:{rel}"
                        )
                        # The RAW annotation dictionary. ``annotation.info``
                        # surfaces only the standard fields — a custom
                        # /assertionQuality key on the annot object is
                        # invisible to it (sol proved with a live PyMuPDF
                        # probe, fix round 2 F1) — so the keys are enumerated
                        # through the xref like the Info dictionary's.
                        raw_annotation = {
                            key: document.xref_get_key(annotation.xref, key)[1]
                            for key in document.xref_get_keys(annotation.xref)
                        }
                        surfaces.append(f"{rel}!annot{annotation.xref}")
                        note_reserved(
                            raw_annotation, f"pdf-annotation-raw:{rel}"
                        )
                        note_token(
                            json.dumps(raw_annotation),
                            f"pdf-annotation-raw:{rel}",
                        )
                    text = page.get_text()
                    note_token(text, f"pdf-text:{rel}")
                    if not text.strip() and page.get_images(full=True):
                        # The page's words are pixels — an OCR-only surface.
                        where = f"pdf-ocr:{rel}#page{page.number}"
                        if tesseract_missing:
                            raise RuntimeError(
                                f"{where} is image-only and tesseract is not "
                                "installed; the label-position scan cannot "
                                "certify OCR-only surfaces without it "
                                "(apt-get install tesseract-ocr)"
                            )
                        surfaces.append(where)
                        ocr_text = _ocr_png(
                            page.get_pixmap(dpi=150).tobytes("png")
                        )
                        note_token(ocr_text, where)
        elif path.suffix == ".eml":
            message = email.message_from_bytes(raw, policy=email.policy.default)
            note_reserved(
                {name: str(value) for name, value in message.items()},
                f"eml-headers:{rel}",
            )
            note_token(
                json.dumps({name: str(value) for name, value in message.items()}),
                f"eml-headers:{rel}",
            )
            for index, part in enumerate(message.walk()):
                payload = part.get_payload(decode=True)
                if payload is not None:
                    surfaces.append(f"{rel}!part{index}")
                    note_token(
                        payload.decode("utf-8", errors="replace"),
                        f"eml-part:{rel}!part{index}",
                    )

    if cli_streams is not None:
        stdout, stderr = cli_streams
        surfaces.extend(["cli:stdout", "cli:stderr"])
        note_token(stdout, "cli:stdout")
        note_token(stderr, "cli:stderr")
        findings.extend(
            f"reserved key cli-stream:{key}"
            for key in RESERVED_LABEL_KEYS
            if f'"{key}"' in stdout or f'"{key}"' in stderr
        )
    return findings, surfaces


@pytest.fixture(scope="module")
def leakage_tree(tmp_path_factory: pytest.TempPathFactory):
    """The committed R71 probe, generated through the shipped CLI."""
    import subprocess
    import sys
    from pathlib import Path

    from wc_caseload_engine.substrate import find_substrate

    if find_substrate() is None:
        pytest.skip("merus-test-data-generator substrate not on disk")

    root = tmp_path_factory.mktemp("assertion-leakage")
    spec_path = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "medical_story_leakage_probe.yaml"
    )
    out_dir = root / "out"
    package_root = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "wc_caseload_engine",
            "generate",
            "--spec",
            str(spec_path),
            "--out",
            str(out_dir),
        ],
        cwd=package_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    return out_dir, (proc.stdout, proc.stderr)


@pytest.fixture(scope="module")
def pristine_leakage_scan(leakage_tree):
    """Scan the pristine tree once: OCR is the expensive, deterministic step."""
    out_dir, streams = leakage_tree
    return _scan_assertion_leakage(out_dir, streams)


@pytest.mark.slow
def test_assertion_leakage_probe_seed_really_contains_truth_labels(leakage_tree) -> None:
    out_dir, _streams = leakage_tree
    truth = json.loads(
        (
            out_dir
            / "truth"
            / "medical-story-leakage-pristine.truth.json"
        ).read_text(encoding="utf-8")
    )
    qualities = {
        item["quality"]
        for collection in ("contentions", "medicalOpinions", "apportionmentAssertions")
        for item in truth["channels"]["assertions"][collection]
    }
    assert qualities == {"supported", "thin", "unsupportable"}


@pytest.mark.slow
def test_assertion_label_positions_are_absent_from_every_analyzer_visible_artifact(
    pristine_leakage_scan,
) -> None:
    findings, surfaces = pristine_leakage_scan
    reserved = [finding for finding in findings if finding.startswith("reserved ")]
    private = [
        finding for finding in findings if finding.startswith("private psych register")
    ]
    r90 = [
        finding
        for finding in findings
        if finding.startswith("forbidden production vocabulary")
    ]
    bare = [finding for finding in findings if finding.startswith("bare token")]
    assert reserved == [], f"reserved label positions leaked: {reserved}"
    assert private == [], f"private Part-5 selectors leaked: {private}"
    assert r90 == [], f"R90 quality commentary leaked: {r90}"
    assert bare == [], f"bare unsupportable leaked: {bare}"
    assert "medical-story-leakage-pristine/seed.yaml" in surfaces
    assert "medical-story-leakage-pristine/manifest.json" in surfaces
    assert "caseload_manifest.json" in surfaces
    assert any(surface.startswith("pdf-ocr:") for surface in surfaces)
    assert set(PRIVATE_PSYCH_REGISTER_KEYS) == {
        "safety_officer_ptsd",
        "harassment_gfpa",
        "compensable_consequence",
        "direct_physical_event",
    }
    assert findings == [], f"aggregate analyzer-visible leakage: {findings}"


@pytest.mark.slow
def test_bare_unsupportable_is_absent_except_for_named_exemptions(
    pristine_leakage_scan,
) -> None:
    findings, _surfaces = pristine_leakage_scan
    bare = [finding for finding in findings if finding.startswith("bare token")]
    assert not bare, bare
    assert ASSERTION_LEAKAGE_EXEMPTIONS == {}


@pytest.mark.slow
def test_assertion_leakage_probe_covers_docx_properties_and_pdf_metadata(
    pristine_leakage_scan,
) -> None:
    _findings, surfaces = pristine_leakage_scan
    assert any("docProps/core.xml" in surface for surface in surfaces), (
        "the probe never opened a DOCX docProps part"
    )
    assert any(surface.endswith("!metadata") for surface in surfaces), (
        "the probe never read a PDF metadata block"
    )
    assert any(surface.endswith("!info") for surface in surfaces), (
        "the probe never read a raw PDF Info dictionary"
    )
    assert any(surface.startswith("pdf-ocr:") for surface in surfaces), (
        "the probe never OCRed an image-only page — the fixture must render "
        "a scanned_pdf and tesseract must be installed"
    )
    assert any("!part" in surface and surface.endswith("part0") for surface in surfaces), (
        "the probe never decoded an EML part"
    )
    assert "cli:stdout" in surfaces and "cli:stderr" in surfaces


def _leakage_fixture_seed_and_plan() -> tuple[Any, Any]:
    from pathlib import Path

    import yaml

    from wc_caseload_engine.planner import build_case_plan

    fixture = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "medical_story_leakage_probe.yaml"
    )
    spec = parse_caseload_spec(yaml.safe_load(fixture.read_text(encoding="utf-8")))
    assert spec.caseload_id == "medical-story-leakage-probe"
    assert tuple(case.case_id for case in spec.cases) == (
        "medical-story-leakage-pristine",
    )
    seed = spec.cases[0]
    assert seed.rng_seed == 6100
    assert seed.documents.global_cap == 15
    assert seed.scenario.medical_assertions is not None
    assert seed.scenario.medical_assertions.sample_contention_documents is False
    return seed, build_case_plan(seed)


def _leakage_family_representatives(plan: Any) -> dict[str, Any]:
    assert plan.medical_story is not None
    representatives: dict[str, Any] = {}
    for document in plan.documents:
        story = plan.medical_story.by_document_index.get(document.index)
        if story is None:
            continue
        for family, subtypes, contention_surface in MEDICAL_STORY_LEAKAGE_FAMILIES:
            if (
                document.subtype in subtypes
                and story.contention_surface == contention_surface
            ):
                representatives.setdefault(family, document)
    return representatives


@pytest.mark.slow
def test_assertion_leakage_probe_covers_every_medical_story_surface_family(
    leakage_tree,
) -> None:
    _out_dir, _streams = leakage_tree
    _seed, plan = _leakage_fixture_seed_and_plan()
    observed_families = set(_leakage_family_representatives(plan))
    assert observed_families == {
        "initial_medlegal",
        "psych_medlegal",
        "supplemental_medlegal",
        "ptp",
        "advocacy",
        "objection",
        "supplemental_request",
        "qme_deposition",
    }


def test_medical_story_seed_binding_warning_and_trace_fields_have_no_quality_like_key() -> None:
    """R71's internal names stay label-free before any artifact is rendered."""
    from dataclasses import fields

    from wc_caseload_engine.medical_assertions import (
        AssertionTrace,
        derive_medical_assertion_plan,
    )
    from wc_caseload_engine.medical_history import derive_medical_history

    seed, case_plan = _leakage_fixture_seed_and_plan()
    assert set(PRIVATE_PSYCH_REGISTER_KEYS) == {
        "safety_officer_ptsd",
        "harassment_gfpa",
        "compensable_consequence",
        "direct_physical_event",
    }
    trace = AssertionTrace()
    assertion_plan = derive_medical_assertion_plan(
        seed, derive_medical_history(seed), trace=trace
    )

    def keys(payload: Any, path: str) -> list[str]:
        found: list[str] = []
        if isinstance(payload, dict):
            for key, value in payload.items():
                here = f"{path}.{key}"
                found.append(here)
                found.extend(keys(value, here))
        elif isinstance(payload, (list, tuple)):
            for index, value in enumerate(payload):
                found.extend(keys(value, f"{path}[{index}]"))
        return found

    key_paths = keys(seed.model_dump(mode="json"), "seed")
    for index, binding in enumerate(assertion_plan.contention_documents):
        key_paths.extend(
            keys(binding.model_dump(mode="json"), f"binding[{index}]")
        )
    key_paths.extend(f"trace.{item.name}" for item in fields(trace))
    forbidden_key_fragments = (
        *RESERVED_LABEL_KEYS,
        *PRIVATE_PSYCH_REGISTER_KEYS,
        "supported",
        "thin",
        "unsupportable",
    )
    assert [
        path
        for path in key_paths
        if any(
            fragment.lower() in path.rsplit(".", 1)[-1].lower()
            for fragment in forbidden_key_fragments
        )
    ] == []
    warning_text = "\n".join(case_plan.warnings).lower()
    assert not _BARE_TOKEN.search(warning_text)
    assert not any(key in warning_text for key in PRIVATE_PSYCH_REGISTER_KEYS)


@pytest.mark.slow
def test_assertion_leakage_probe_has_positive_controls_for_every_medical_story_surface_family(
    leakage_tree, tmp_path: Any
) -> None:
    """Each bound family gets its own format-valid planted copy and live scan."""
    import shutil
    import zipfile
    from pathlib import Path

    fitz = pytest.importorskip("fitz")

    out_dir, _streams = leakage_tree
    _seed, plan = _leakage_fixture_seed_and_plan()
    representatives = _leakage_family_representatives(plan)
    assert set(representatives) == {
        "initial_medlegal",
        "psych_medlegal",
        "supplemental_medlegal",
        "ptp",
        "advocacy",
        "objection",
        "supplemental_request",
        "qme_deposition",
    }

    source_case_dir = out_dir / "medical-story-leakage-pristine"
    source_manifest = json.loads(
        (source_case_dir / "manifest.json").read_text(encoding="utf-8")
    )

    def plant(path: Path) -> None:
        if path.suffix == ".pdf":
            with fitz.open(path) as document:
                document[0].insert_text((72, 96), "unsupportable", fontsize=18)
                planted = path.with_suffix(".planted.pdf")
                document.save(planted)
            path.unlink()
            planted.rename(path)
            return
        if path.suffix == ".docx":
            source = path.with_suffix(".docx.orig")
            path.rename(source)
            with zipfile.ZipFile(source) as inp, zipfile.ZipFile(path, "w") as outp:
                for item in inp.infolist():
                    data = inp.read(item.filename)
                    if item.filename == "word/document.xml":
                        data = data.replace(
                            b"</w:body>",
                            b"<w:p><w:r><w:t>unsupportable</w:t></w:r></w:p>"
                            b"</w:body>",
                        )
                    outp.writestr(item, data)
            source.unlink()
            return
        assert path.suffix == ".eml", path
        path.write_bytes(path.read_bytes() + b"\nunsupportable\n")

    for family, document in representatives.items():
        copy_root = tmp_path / family
        copy_root.mkdir()
        manifest_entry = source_manifest["documents"][document.index]
        source_path = source_case_dir / "documents" / manifest_entry["filename"]
        planted_path = copy_root / manifest_entry["filename"]
        assert manifest_entry["subtype"] == document.subtype
        shutil.copy2(source_path, planted_path)
        plant(planted_path)
        findings, _surfaces = _scan_assertion_leakage(copy_root)
        assert any(
            finding.startswith("bare token at ")
            and manifest_entry["filename"] in finding
            for finding in findings
        ), f"the {family} format-valid plant was not detected: {findings}"


@pytest.mark.slow
def test_assertion_leakage_probe_has_positive_controls_for_every_position(
    leakage_tree, tmp_path: Any
) -> None:
    """Plant EVERY enumerated position class into a copy of the tree; the scan
    must fire on each one. Every format's presence is asserted, never skipped —
    a control that silently skipped would leave its position unproven."""
    import base64
    import shutil
    import zipfile
    from pathlib import Path

    fitz = pytest.importorskip("fitz")

    out_dir, _streams = leakage_tree
    copy_root = tmp_path / "planted"
    shutil.copytree(out_dir, copy_root)

    case_dir = next(p for p in copy_root.iterdir() if (p / "manifest.json").exists())
    documents = case_dir / "documents"

    # 1. Reserved structured keys in the analyzer-visible JSON artifacts:
    #    the case manifest and the caseload-level index.
    manifest_path = case_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["assertionQuality"] = ["a", "b"]
    manifest["reviewComment"] = "bogus"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    caseload_path = copy_root / "caseload_manifest.json"
    caseload = json.loads(caseload_path.read_text(encoding="utf-8"))
    caseload["medicalAssertions"] = {}
    caseload["reviewComment"] = "underworked"
    caseload_path.write_text(json.dumps(caseload), encoding="utf-8")

    # 2. Reserved keys in the copied seed and case-facts YAML.
    seed_path = case_dir / "seed.yaml"
    seed_path.write_text(
        seed_path.read_text(encoding="utf-8")
        + "\nquality: supported\nreview_comment: bad\nharassment_gfpa: planted\n",
        encoding="utf-8",
    )
    facts_path = case_dir / "case_facts.yaml"
    facts_path.write_text(
        facts_path.read_text(encoding="utf-8")
        + "\nrubric: planted\nselector: safety_officer_ptsd\n",
        encoding="utf-8",
    )

    # 3. The bare token in a rendered EML's raw bytes.
    eml = next(iter(sorted(documents.glob("*.eml"))), None)
    assert eml is not None, "the fixture rendered no EML to plant into"
    eml.write_bytes(eml.read_bytes() + b"\nUNSUPPORTABLE\n")

    # 4. A base64-encoded EML part — invisible to the raw-bytes sweep, so
    #    only the decoded-part scan can find it — plus a reserved header name.
    encoded = base64.b64encode(b"the finding is unsupportable on this record").decode()
    (documents / "planted-note.eml").write_text(
        "MIME-Version: 1.0\n"
        "Content-Type: text/plain\n"
        "Content-Transfer-Encoding: base64\n"
        "assertionQuality: 1\n"
        "Subject: exhibit index\n"
        "\n"
        f"{encoded}\n",
        encoding="utf-8",
    )

    # 5. DOCX: the bare token in docProps AND in body XML, plus a reserved
    #    property NAME the parsed-properties read must catch.
    docx = next(iter(sorted(documents.glob("*.docx"))), None)
    assert docx is not None, "the fixture rendered no DOCX to plant into"
    source = docx.with_suffix(".docx.orig")
    docx.rename(source)
    with zipfile.ZipFile(source) as inp, zipfile.ZipFile(docx, "w") as outp:
        for item in inp.infolist():
            data = inp.read(item.filename)
            if item.filename == "docProps/core.xml":
                data = data.replace(
                    b"</cp:coreProperties>",
                    b"<dc:subject>unsupportable</dc:subject>"
                    b"<quality>planted</quality>"
                    b"</cp:coreProperties>",
                )
            if item.filename == "word/document.xml":
                data = data.replace(
                    b"</w:body>",
                    b"<w:p><w:r><w:t>quality: supported</w:t></w:r></w:p>"
                    b"</w:body>",
                )
            outp.writestr(item, data)
    source.unlink()

    def _page_zero_text(path: Path) -> str:
        with fitz.open(path) as probe:
            return probe[0].get_text().strip()

    # 6. PDF: the token in the metadata block, the token AND a reserved key
    #    in the raw Info dictionary, a planted annotation, planted page text.
    text_pdf = next((p for p in sorted(documents.glob("*.pdf")) if _page_zero_text(p)), None)
    assert text_pdf is not None, "the fixture rendered no text-layer PDF"
    with fitz.open(text_pdf) as doc:
        metadata = dict(doc.metadata or {})
        metadata["subject"] = "unsupportable"
        doc.set_metadata(metadata)
        info_type, info_value = doc.xref_get_key(-1, "Info")
        assert info_type == "xref", "the planted PDF lost its Info dictionary"
        doc.xref_set_key(int(info_value.split()[0]), "assertionQuality", "(planted)")
        page = doc[0]
        annot = page.add_text_annot((72, 72), "unsupportable")
        # A custom key on the RAW annotation dictionary — invisible to
        # annotation.info, visible only to the xref enumeration (sol F1).
        doc.xref_set_key(annot.xref, "assertionQuality", "(planted)")
        page.insert_text((72, 120), "unsupportable")
        # An XMP packet whose reserved key is an attribute NAME, not a value.
        doc.set_xml_metadata(
            '<x:xmpmeta xmlns:x="adobe:ns:meta/">'
            '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
            '<rdf:Description assertionQuality="planted"/>'
            "</rdf:RDF></x:xmpmeta>"
        )
        planted_pdf = text_pdf.with_suffix(".planted.pdf")
        doc.save(planted_pdf)
    text_pdf.unlink()
    planted_pdf.rename(text_pdf)

    # 7. The OCR-only position: rasterize the token and stamp it into an
    #    image-only page as PIXELS — no text layer anywhere on the page.
    scanned_pdf = next(
        (p for p in sorted(documents.glob("*.pdf")) if not _page_zero_text(p)), None
    )
    assert scanned_pdf is not None, "the fixture rendered no image-only PDF"
    stamp = fitz.open()
    stamp_page = stamp.new_page(width=560, height=100)
    stamp_page.insert_text(
        (20, 60), "unsupportable and underworked", fontsize=30
    )
    png = stamp_page.get_pixmap(dpi=150).tobytes("png")
    stamp.close()
    with fitz.open(scanned_pdf) as doc:
        page = doc[0]
        assert not page.get_text().strip()
        page.insert_image(fitz.Rect(40, 40, 460, 115), stream=png)
        planted_scan = scanned_pdf.with_suffix(".planted.pdf")
        doc.save(planted_scan)
    scanned_pdf.unlink()
    planted_scan.rename(scanned_pdf)

    # 8. The bare token in a filename and in a directory name.
    (documents / "unsupportable-note.txt").write_text("planted", encoding="utf-8")
    (documents / "unsupportable-exhibits").mkdir()

    # 9. CLI streams: the bare token on stdout, unquoted label syntax on stderr.
    findings, _surfaces = _scan_assertion_leakage(
        copy_root, ("note: this reads unsupportable", "rubric: thin")
    )
    joined = "\n".join(findings)
    assert "manifest.json.assertionQuality" in joined
    assert any(
        finding.endswith("manifest.json:bogus")
        and finding.startswith("forbidden production vocabulary at ")
        for finding in findings
    ), "the R90 forbidden-vocabulary plant in the ordinary manifest was not caught"
    assert "caseload_manifest.json.medicalAssertions" in joined
    assert (
        "forbidden production vocabulary at caseload_manifest.json:underworked"
        in findings
    ), "the distinct caseload-manifest R90 plant was not caught"
    assert "seed.yaml.quality" in joined
    assert (
        "reserved label position at bytes:medical-story-leakage-pristine/"
        "seed.yaml:quality=supported"
        in findings
    )
    assert (
        "forbidden production vocabulary at medical-story-leakage-pristine/seed.yaml:bad"
        in findings
    ), "the copied-seed R90 plant was not caught"
    assert any(
        finding.startswith("private psych register key seed.yaml.harassment_gfpa")
        for finding in findings
    ), "the planted private register key in the copied seed was not caught"
    assert "case_facts.yaml.rubric" in joined
    assert any(
        finding.startswith("private psych register value case_facts.yaml.selector=")
        for finding in findings
    ), "the planted structured private register value was not caught"
    assert any(
        f.startswith("bare token at bytes:") and f.endswith(".eml") for f in findings
    )
    assert any(
        f.startswith("bare token at eml-part:") and "planted-note.eml" in f
        for f in findings
    ), "the base64-encoded EML part was not decoded and scanned"
    assert any(
        f.startswith("reserved key eml-headers:") and ".assertionQuality" in f
        for f in findings
    )
    assert any(
        f.startswith("bare token at docx:") and "docProps/core.xml" in f
        for f in findings
    )
    assert any(
        f.startswith("reserved key docx-properties:") and ".quality" in f
        for f in findings
    ), "the planted DOCX property NAME was not caught by the parsed-key read"
    assert any(
        f.startswith("reserved label position at docx:")
        and "word/document.xml" in f
        for f in findings
    ), "the reserved DOCX-body label position was not caught"
    assert any(f.startswith("bare token at pdf-metadata:") for f in findings)
    assert any(f.startswith("bare token at pdf-info:") for f in findings)
    assert any(
        f.startswith("reserved key pdf-info:") and ".assertionQuality" in f
        for f in findings
    ), "the planted custom Info key was not caught by the raw-dictionary read"
    assert any(f.startswith("bare token at pdf-annotation:") for f in findings)
    assert any(
        f.startswith("reserved key pdf-annotation-raw:") and ".assertionQuality" in f
        for f in findings
    ), "the planted raw annotation key was not caught by the xref enumeration"
    assert any(
        f.startswith("reserved key pdf-xmp:") and ".assertionQuality" in f
        for f in findings
    ), "the planted XMP attribute NAME was not caught by the parsed packet read"
    assert any(f.startswith("bare token at pdf-text:") for f in findings)
    assert any(f.startswith("bare token at pdf-ocr:") for f in findings), (
        "the rasterized token was not recovered from the image-only page"
    )
    assert any(
        f.startswith("forbidden production vocabulary at pdf-ocr:")
        and f.endswith(":underworked")
        for f in findings
    ), "the OCR surface was scanned only for the bare label, not full R90"
    assert any(
        f.startswith("bare token at path:") and "unsupportable-note.txt" in f
        for f in findings
    )
    assert any(
        f.startswith("bare token at path:") and "unsupportable-exhibits" in f
        for f in findings
    )
    assert "bare token at cli:stdout" in findings
    assert "reserved label position at cli:stderr:rubric=thin" in findings


@pytest.mark.slow
def test_assertion_leakage_probe_fails_closed_on_malformed_docprops_xml(
    leakage_tree, tmp_path: Any
) -> None:
    """A corrupt property part cannot silently bypass the structured key scan."""
    import shutil
    import zipfile

    out_dir, _streams = leakage_tree
    source = next(
        iter(
            sorted(
                (
                    out_dir
                    / "medical-story-leakage-pristine"
                    / "documents"
                ).glob("*.docx")
            )
        ),
        None,
    )
    assert source is not None, "the fixture rendered no DOCX to corrupt"
    planted = tmp_path / source.name
    original = tmp_path / f"{source.name}.orig"
    shutil.copy2(source, original)
    with zipfile.ZipFile(original) as inp, zipfile.ZipFile(planted, "w") as outp:
        for item in inp.infolist():
            data = inp.read(item.filename)
            if item.filename == "docProps/core.xml":
                data = b"<cp:coreProperties"
            outp.writestr(item, data)

    with pytest.raises(RuntimeError) as caught:
        _scan_assertion_leakage(tmp_path)
    assert str(caught.value) == (
        f"docx-properties:{source.name}!docProps/core.xml is malformed XML; "
        "the reserved-key scan cannot certify property names"
    )


def test_part5_psych_and_imr_registers_do_not_leak_labels_or_quality_commentary():
    """R90/R93 — only rendered Part-5 strings are analyzer-visible evidence."""
    from test_medical_story import _part5_psych_report
    from test_medical_story_loop import _part5_imr_case

    rendered_surfaces: list[tuple[str, str]] = []
    for opinion_id in ("opn-01", "opn-02", "opn-03", "opn-04"):
        _document, _story, rendered = _part5_psych_report(opinion_id)
        rendered_surfaces.append((f"psych-report:{opinion_id}", rendered))

    for case_id in (
        "imr-authored-true-upheld",
        "imr-sparse-explicit",
        "imr-sampled-upheld",
    ):
        _seed, _plan, _document, _content, rendered = _part5_imr_case(case_id)
        rendered_surfaces.append((f"imr-application:{case_id}", rendered))

    findings = [
        finding
        for label, rendered in rendered_surfaces
        for finding in _decoded_text_findings(rendered, label)
    ]
    assert [label for label, _rendered in rendered_surfaces] == [
        "psych-report:opn-01",
        "psych-report:opn-02",
        "psych-report:opn-03",
        "psych-report:opn-04",
        "imr-application:imr-authored-true-upheld",
        "imr-application:imr-sparse-explicit",
        "imr-application:imr-sampled-upheld",
    ]
    assert findings == []
