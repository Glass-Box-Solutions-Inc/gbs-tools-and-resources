"""Work Item 3 oracles for rating schemas and fail-closed validation."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from wc_caseload_engine.case_facts import CaseFacts
from wc_caseload_engine.planner import build_case_plan
from wc_caseload_engine.rating import (
    RATING_AGE_CELL_MISSING,
    RATING_COMBINATION_EXTREMITY_IDENTITY_REQUIRED,
    RATING_COMBINATION_UNSUPPORTED_OVERLAP,
    RATING_ERROR_CODES,
    RATING_FEC_CELL_MISSING,
    RATING_INVALID_AGE_INPUT,
    RATING_KITE_NEEDS_TWO_DISTINCT_ROWS,
    RATING_KITE_PAIR_INVALID,
    RATING_KITE_SCOPE_UNSUPPORTED,
    RATING_OCC_CELL_MISSING,
    RATING_REQUIRED_CARRIER_REMOVED,
    RATING_REQUIRES_EVALUATOR,
    RATING_REQUIRES_WAGES,
    RATING_SOURCE_BUNDLE_MISMATCH,
    RATING_UNKNOWN_IMPAIRMENT_NUMBER,
    RATING_UNKNOWN_OCCUPATION_GROUP,
    RATING_UNSUPPORTED_DOI,
    RATING_VARIANT_CROSS_REFERENCE_REQUIRED,
    KiteAdditionInput,
    RatingFacts,
    RatingImpairment,
    RatingImpairmentInput,
    RatingScenario,
    RatingValidationError,
    age_band_for,
    applicant_age_at_doi,
    combine_cvc_ratings,
    derive_rating_facts,
    rating_adjustment_method,
    section4_row_key,
    validate_rating_inputs,
)
from wc_caseload_engine.rating_sources import (
    RatingScheduleBinding,
    load_rating_source_bundle,
)
from wc_caseload_engine.seeds import (
    SeedValidationError,
    load_caseload_spec,
    parse_case_seed,
    resolve_caseload,
)

RATING_SCENARIO_FIELDS = {
    "schedule",
    "occupation_group",
    "impairments",
    "combination_method",
    "kite_addition",
}
RATING_IMPAIRMENT_INPUT_FIELDS = {"id", "body_part", "impairment_number", "wpi"}
KITE_ADDITION_INPUT_FIELDS = {"impairment_ids"}
RATING_FACTS_FIELDS = {
    "schedule",
    "date_of_injury",
    "applicant_age",
    "occupation_group",
    "occupation_title",
    "impairments",
    "combination_method",
    "kite_impairment_ids",
    "scheduled_combined_rating",
    "combined_rating",
    "final_pd_percent",
    "rating_string",
}
RATING_IMPAIRMENT_FIELDS = {
    "id",
    "body_part",
    "impairment_number",
    "wpi",
    "description",
    "adjustment_method",
    "fec_rank",
    "adjustment_factor",
    "schedule_adjusted",
    "variant",
    "occupation_adjusted",
    "age_band",
    "age_adjusted",
    "rating_string",
}
EXPECTED_ERROR_CODES = {
    "RATING_REQUIRES_WAGES",
    "RATING_REQUIRES_EVALUATOR",
    "RATING_UNSUPPORTED_DOI",
    "RATING_INVALID_AGE_INPUT",
    "RATING_UNKNOWN_OCCUPATION_GROUP",
    "RATING_UNKNOWN_IMPAIRMENT_NUMBER",
    "RATING_VARIANT_CROSS_REFERENCE_REQUIRED",
    "RATING_FEC_CELL_MISSING",
    "RATING_OCC_CELL_MISSING",
    "RATING_AGE_CELL_MISSING",
    "RATING_COMBINATION_UNSUPPORTED_OVERLAP",
    "RATING_COMBINATION_EXTREMITY_IDENTITY_REQUIRED",
    "RATING_KITE_NEEDS_TWO_DISTINCT_ROWS",
    "RATING_KITE_PAIR_INVALID",
    "RATING_KITE_SCOPE_UNSUPPORTED",
    "RATING_REQUIRED_CARRIER_REMOVED",
    "RATING_SOURCE_BUNDLE_MISMATCH",
}
EXPECTED_RATING_CARRIERS = frozenset(
    {
        "IMPAIRMENT_RATING_WORKSHEET",
        "PD_RATING_CALCULATION_WORKSHEET",
        "PD_RATING_CONVERSION",
    }
)
EXPECTED_RATING_GROUNDING_HOOKS = frozenset(
    {
        "ogilvie",
        "almaraz_guzman",
        "escobedo",
        "benson",
        "kite",
        "lc4664_prior_award",
    }
)


def _row(
    identifier: str = "cervical",
    body_part: str = "cervical_spine",
    impairment_number: str = "15.01.02.02",
    wpi: int = 10,
) -> dict[str, Any]:
    return {
        "id": identifier,
        "body_part": body_part,
        "impairment_number": impairment_number,
        "wpi": wpi,
    }


def _rating(
    *,
    rows: list[dict[str, Any]] | None = None,
    occupation_group: str = "470",
    combination_method: str = "single",
    kite_addition: dict[str, Any] | None = None,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schedule": "pdrs_2005",
        "occupation_group": occupation_group,
        "impairments": rows if rows is not None else [_row()],
        "combination_method": combination_method,
    }
    if kite_addition is not None:
        value["kite_addition"] = kite_addition
    return value


def _seed(
    *,
    doi: str = "2013-01-01",
    rating: dict[str, Any] | None = None,
    eval_type: str = "qme",
    wages: dict[str, Any] | None = None,
    body_parts: list[str] | None = None,
) -> dict[str, Any]:
    parts = body_parts if body_parts is not None else ["cervical_spine"]
    scenario: dict[str, Any] = {"rating": rating if rating is not None else _rating()}
    if wages is not None:
        scenario["wages"] = wages
    return {
        "case_id": "rating-probe",
        "rng_seed": 42,
        "injury": {
            "type": "specific",
            "date_of_injury": doi,
            "body_parts": [{"part": part} for part in parts],
        },
        "lifecycle": {"target_stage": "medical_legal", "eval_type": eval_type},
        "scenario": scenario,
    }


def _parse(**changes: Any):
    changes.setdefault("wages", {})
    return parse_case_seed(_seed(**changes))


def _message(**changes: Any) -> str:
    with pytest.raises(SeedValidationError) as excinfo:
        _parse(**changes)
    return str(excinfo.value)


def _canonical_impairment(
    *,
    identifier: str = "cervical",
    method: str = "fec_rank_table",
    fec_rank: int | None = 5,
    factor: Decimal | None = None,
) -> RatingImpairment:
    return RatingImpairment(
        id=identifier,
        body_part="cervical_spine",
        impairment_number="15.01.02.02",
        wpi=10,
        description="Cervical soft tissue lesion",
        adjustment_method=method,
        fec_rank=fec_rank,
        adjustment_factor=factor,
        schedule_adjusted=14,
        variant="H",
        occupation_adjusted=17,
        age_band="37-41",
        age_adjusted=19,
        rating_string="15.01.02.02 - 10 - [5]14H - 17 - 19%",
    )


def _canonical_facts(
    *,
    doi: date = date(2012, 12, 31),
    impairment: RatingImpairment | None = None,
) -> RatingFacts:
    return RatingFacts(
        schedule=RatingScheduleBinding(),
        date_of_injury=doi,
        applicant_age=40,
        occupation_group="470",
        occupation_title="Warehouse worker",
        impairments=(impairment or _canonical_impairment(),),
        combination_method="single",
        kite_impairment_ids=None,
        scheduled_combined_rating=19,
        combined_rating=19,
        final_pd_percent=19,
        rating_string="15.01.02.02 - 10 - [5]14H - 17 - 19%",
    )


def test_r26_and_r44_field_sets_are_literal_and_models_are_closed() -> None:
    assert set(RatingScenario.model_fields) == RATING_SCENARIO_FIELDS
    assert set(RatingImpairmentInput.model_fields) == RATING_IMPAIRMENT_INPUT_FIELDS
    assert set(KiteAdditionInput.model_fields) == KITE_ADDITION_INPUT_FIELDS
    assert set(RatingFacts.model_fields) == RATING_FACTS_FIELDS
    assert set(RatingImpairment.model_fields) == RATING_IMPAIRMENT_FIELDS
    assert "rating" in CaseFacts.model_fields
    assert "wpi" not in CaseFacts.model_fields
    assert "pd" not in CaseFacts.model_fields

    facts = _canonical_facts()
    with pytest.raises(ValidationError):
        facts.final_pd_percent = 20
    with pytest.raises(ValidationError) as excinfo:
        RatingFacts.model_validate({**facts.model_dump(), "artifact_rating": {}})
    assert "artifact_rating" in str(excinfo.value)
    assert "Extra inputs are not permitted" in str(excinfo.value)


def test_r50_error_code_registry_is_exact_and_frozen() -> None:
    assert RATING_ERROR_CODES == EXPECTED_ERROR_CODES
    assert isinstance(RATING_ERROR_CODES, frozenset)
    assert {
        RATING_AGE_CELL_MISSING,
        RATING_COMBINATION_EXTREMITY_IDENTITY_REQUIRED,
        RATING_COMBINATION_UNSUPPORTED_OVERLAP,
        RATING_FEC_CELL_MISSING,
        RATING_INVALID_AGE_INPUT,
        RATING_KITE_NEEDS_TWO_DISTINCT_ROWS,
        RATING_KITE_PAIR_INVALID,
        RATING_KITE_SCOPE_UNSUPPORTED,
        RATING_OCC_CELL_MISSING,
        RATING_REQUIRED_CARRIER_REMOVED,
        RATING_REQUIRES_EVALUATOR,
        RATING_REQUIRES_WAGES,
        RATING_SOURCE_BUNDLE_MISMATCH,
        RATING_UNKNOWN_IMPAIRMENT_NUMBER,
        RATING_UNKNOWN_OCCUPATION_GROUP,
        RATING_UNSUPPORTED_DOI,
        RATING_VARIANT_CROSS_REFERENCE_REQUIRED,
    } == EXPECTED_ERROR_CODES


def test_rating_requires_the_existing_wage_gate() -> None:
    message = _message(wages=None)
    assert RATING_REQUIRES_WAGES in message
    assert "scenario.rating" in message
    assert "scenario.wages" in message

    seed = _parse(wages={})
    assert seed.scenario.wages is not None
    assert seed.scenario.rating is not None


def test_rating_bound_authored_age_uses_the_stable_failure_code() -> None:
    payload = _seed(wages={})
    payload["profile"] = {"applicant": {"age": 15}}
    with pytest.raises(SeedValidationError) as excinfo:
        parse_case_seed(payload)
    message = str(excinfo.value)
    assert RATING_INVALID_AGE_INPUT in message
    assert "profile.applicant.age" in message
    assert "15" in message

    payload["profile"] = {"applicant": {"age": 16}}
    assert parse_case_seed(payload).profile.applicant.age == 16


def test_pure_rating_schedule_boundary_rejects_1997_and_accepts_2005() -> None:
    message = _message(doi="2004-12-31")
    assert RATING_UNSUPPORTED_DOI in message
    assert "injury.date_of_injury" in message
    assert "2004-12-31" in message
    assert "1997 PDRS rating is unavailable" in message

    seed = _parse(doi="2005-01-01")
    assert rating_adjustment_method(seed.injury.onset_date) == "fec_rank_table"


def test_doi_selects_audited_fec_through_2012_and_dfec_from_2013() -> None:
    old = _parse(doi="2012-12-31")
    new = _parse(doi="2013-01-01")
    assert rating_adjustment_method(old.injury.onset_date) == "fec_rank_table"
    assert rating_adjustment_method(new.injury.onset_date) == "dfec_1_4"


def test_2013_branch_never_consults_the_fec_rank_table() -> None:
    source_without_fec = replace(load_rating_source_bundle(), fec_lookup={})
    authored = RatingScenario.model_validate(_rating())
    arguments = {
        "rating": authored,
        "evaluator": "qme",
        "injury_body_parts": ("cervical_spine",),
        "bundle": source_without_fec,
    }
    with pytest.raises(RatingValidationError) as excinfo:
        validate_rating_inputs(
            date_of_injury=date(2012, 12, 31),
            **arguments,
        )
    assert excinfo.value.code == RATING_FEC_CELL_MISSING
    assert "5|10" in str(excinfo.value)

    assert (
        validate_rating_inputs(
            date_of_injury=date(2013, 1, 1),
            **arguments,
        )
        == "dfec_1_4"
    )


def test_known_occupation_470_has_unknown_471_neighbor() -> None:
    assert _parse(rating=_rating(occupation_group="470")).scenario.rating is not None
    message = _message(rating=_rating(occupation_group="471"))
    assert RATING_UNKNOWN_OCCUPATION_GROUP in message
    assert "scenario.rating.occupation_group" in message
    assert "471" in message


def test_known_impairment_has_unknown_neighbor() -> None:
    assert _parse(rating=_rating(rows=[_row(impairment_number="15.01.02.02")]))
    message = _message(rating=_rating(rows=[_row(impairment_number="15.01.02.99")]))
    assert RATING_UNKNOWN_IMPAIRMENT_NUMBER in message
    assert "scenario.rating.impairments[0].impairment_number" in message
    assert "15.01.02.99" in message


def test_section4_cross_reference_never_falls_back() -> None:
    """m23-5: the literal negative and its Form C positive neighbor."""
    assert _parse(rating=_rating(rows=[_row(impairment_number="13.07.07.00")]))
    message = _message(rating=_rating(rows=[_row(impairment_number="13.07.08.00")]))
    assert RATING_VARIANT_CROSS_REFERENCE_REQUIRED in message
    assert "13.07.08.00" in message
    assert "11.03.04.00" in message
    assert "no fallback is permitted" in message


@pytest.mark.parametrize("eval_type", ["qme", "ame"])
def test_rating_accepts_only_actual_evaluators(eval_type: str) -> None:
    assert _parse(eval_type=eval_type).lifecycle.eval_type == eval_type


def test_none_evaluator_is_rejected_with_its_positive_neighbors_above() -> None:
    message = _message(eval_type="none")
    assert RATING_REQUIRES_EVALUATOR in message
    assert "lifecycle.eval_type" in message
    assert "none" in message
    assert "qme" in message and "ame" in message


def test_one_kite_row_is_rejected_and_two_explicit_rows_are_accepted() -> None:
    one = _rating(
        combination_method="cvc",
        kite_addition={"impairment_ids": ["cervical", "knee"]},
    )
    message = _message(rating=one)
    assert RATING_KITE_NEEDS_TWO_DISTINCT_ROWS in message
    assert "scenario.rating.impairments" in message

    rows = [
        _row("shoulder", "shoulder", "16.02.01.00"),
        _row("knee", "knee", "17.05.04.00"),
    ]
    seed = _parse(
        rating=_rating(
            rows=rows,
            combination_method="cvc",
            kite_addition={"impairment_ids": ["shoulder", "knee"]},
        ),
        body_parts=["shoulder", "knee"],
    )
    authored = seed.scenario.rating
    assert authored is not None
    assert "kite_addition" in authored.model_fields_set
    assert authored.kite_addition is not None
    assert authored.kite_addition.impairment_ids == ("shoulder", "knee")


def test_cvc_requires_distinguishable_extremity_identity() -> None:
    """m23-51: two 16.* rows fail while one 16.* plus one 17.* passes."""
    ambiguous_rows = [
        _row("shoulder", "shoulder", "16.02.01.00"),
        _row("wrist", "wrist", "16.04.01.00"),
    ]
    message = _message(
        rating=_rating(rows=ambiguous_rows, combination_method="cvc"),
        body_parts=["shoulder", "wrist"],
    )
    assert RATING_COMBINATION_EXTREMITY_IDENTITY_REQUIRED in message
    assert "16.02.01.00" in message and "16.04.01.00" in message
    assert "distinct extremities" in message

    distinguishable_rows = [
        _row("shoulder", "shoulder", "16.02.01.00"),
        _row("knee", "knee", "17.05.04.00"),
    ]
    accepted = _parse(
        rating=_rating(rows=distinguishable_rows, combination_method="cvc"),
        body_parts=["shoulder", "knee"],
    )
    assert accepted.scenario.rating is not None
    assert len(accepted.scenario.rating.impairments) == 2


def test_every_impairment_body_part_must_exist_in_the_injury() -> None:
    message = _message(rating=_rating(rows=[_row(body_part="knee")]))
    assert RATING_COMBINATION_UNSUPPORTED_OVERLAP in message
    assert "scenario.rating.impairments[0].body_part" in message
    assert "knee" in message and "cervical_spine" in message


def test_kite_pair_is_exactly_the_complete_authored_two_row_set() -> None:
    rows = [
        _row("shoulder", "shoulder", "16.02.01.00"),
        _row("knee", "knee", "17.05.04.00"),
    ]
    message = _message(
        rating=_rating(
            rows=rows,
            combination_method="cvc",
            kite_addition={"impairment_ids": ["shoulder", "missing"]},
        ),
        body_parts=["shoulder", "knee"],
    )
    assert RATING_KITE_PAIR_INVALID in message
    assert "scenario.rating.kite_addition.impairment_ids" in message
    assert "missing" in message

    three = [*rows, _row("lumbar", "lumbar_spine", "15.03.01.00")]
    message = _message(
        rating=_rating(
            rows=three,
            combination_method="cvc",
            kite_addition={"impairment_ids": ["shoulder", "knee"]},
        ),
        body_parts=["shoulder", "knee", "lumbar_spine"],
    )
    assert RATING_KITE_PAIR_INVALID in message
    assert "complete two-row impairment ID set" in message


def test_canonical_nullability_follows_the_whole_doi_branch() -> None:
    old = _canonical_facts()
    assert old.impairments[0].fec_rank == 5
    assert old.impairments[0].adjustment_factor is None

    new_row = _canonical_impairment(
        method="dfec_1_4", fec_rank=None, factor=Decimal("1.4")
    )
    new = _canonical_facts(doi=date(2013, 1, 1), impairment=new_row)
    assert new.impairments[0].fec_rank is None
    assert new.impairments[0].adjustment_factor == Decimal("1.4")

    with pytest.raises(ValidationError) as excinfo:
        _canonical_facts(
            doi=date(2013, 1, 1),
            impairment=_canonical_impairment(
                method="dfec_1_4", fec_rank=5, factor=Decimal("1.4")
            ),
        )
    assert RATING_FEC_CELL_MISSING in str(excinfo.value)
    assert "2013+ rows require" in str(excinfo.value)


def test_canonical_method_and_kite_pairing_cannot_diverge() -> None:
    row = _canonical_impairment()
    payload = _canonical_facts().model_dump()
    payload.update(
        {
            "impairments": (row,),
            "combination_method": "single",
            "kite_impairment_ids": ("cervical", "other"),
        }
    )
    with pytest.raises(ValidationError) as excinfo:
        RatingFacts.model_validate(payload)
    assert RATING_KITE_PAIR_INVALID in str(excinfo.value)
    assert "single ratings" in str(excinfo.value)


def test_rating_scenario_cannot_author_any_derived_result() -> None:
    for forbidden in (
        "final_pd_percent",
        "fec_rank",
        "variant",
        "schedule_adjusted",
        "rating_string",
        "apportionment_percentage",
        "dollar_value",
    ):
        authored = _rating()
        authored[forbidden] = 10
        message = _message(rating=authored)
        assert f"scenario.rating.{forbidden}" in message
        assert "unknown field" in message


def _worked_example():
    return derive_rating_facts(
        RatingScenario.model_validate(_rating(rows=[_row(wpi=8)])),
        date_of_injury=date(2012, 6, 15),
        birth_date=date(1982, 6, 15),
        occupation_title="Warehouse worker",
    )


def test_r30_age_is_attained_at_doi_and_bands_are_literal() -> None:
    doi = date(2012, 6, 15)
    assert applicant_age_at_doi(doi, date(1982, 6, 15)) == 30
    assert applicant_age_at_doi(doi, date(1982, 6, 16)) == 29
    ages = (21, 22, 26, 27, 31, 32, 36, 37, 41, 42, 46, 47, 51, 52, 56, 57, 61, 62)
    assert [age_band_for(age) for age in ages] == [
        "<=21",
        "22-26",
        "22-26",
        "27-31",
        "27-31",
        "32-36",
        "32-36",
        "37-41",
        "37-41",
        "42-46",
        "42-46",
        "47-51",
        "47-51",
        "52-56",
        "52-56",
        "57-61",
        "57-61",
        ">=62",
    ]


@pytest.mark.parametrize("birth_date", [None, date(2012, 6, 16)])
def test_r30_missing_or_future_birth_date_fails_closed(birth_date: date | None) -> None:
    with pytest.raises(RatingValidationError) as excinfo:
        applicant_age_at_doi(date(2012, 6, 15), birth_date)
    assert excinfo.value.code == RATING_INVALID_AGE_INPUT


def test_r34_section4_resolver_requires_exactly_one_printed_row() -> None:
    source = load_rating_source_bundle()
    assert section4_row_key("15.01.02.02", source) == "15.01 -- 15.03"

    without_range = dict(source.section4_matrix)
    without_range.pop("15.01 -- 15.03")
    with pytest.raises(RatingValidationError) as excinfo:
        section4_row_key(
            "15.01.02.02", replace(source, section4_matrix=without_range)
        )
    assert excinfo.value.code == RATING_VARIANT_CROSS_REFERENCE_REQUIRED

    with_exact_duplicate = dict(source.section4_matrix)
    with_exact_duplicate["15.01.02.02"] = dict(
        source.section4_matrix["15.01 -- 15.03"]
    )
    with pytest.raises(RatingValidationError) as excinfo:
        section4_row_key(
            "15.01.02.02",
            replace(source, section4_matrix=with_exact_duplicate),
        )
    assert excinfo.value.code == RATING_VARIANT_CROSS_REFERENCE_REQUIRED


def test_r38_worked_example_pins_every_intermediate_and_printed_row() -> None:
    facts = _worked_example()
    row = facts.impairments[0]
    assert facts.date_of_injury == date(2012, 6, 15)
    assert facts.applicant_age == 30
    assert facts.occupation_group == "470"
    assert facts.occupation_title == "Warehouse worker"
    assert row.impairment_number == "15.01.02.02"
    assert row.wpi == 8
    assert row.description == (
        "Cervical \N{EN DASH} Range of Motion \N{EN DASH} Soft Tissue Lesion"
    )
    assert row.adjustment_method == "fec_rank_table"
    assert row.fec_rank == 5
    assert row.adjustment_factor is None
    assert row.schedule_adjusted == 10
    assert section4_row_key(row.impairment_number) == "15.01 -- 15.03"
    assert row.variant == "H"
    assert row.occupation_adjusted == 13
    assert row.age_band == "27-31"
    assert row.age_adjusted == 11
    assert row.rating_string == "15.01.02.02 - 8 - [5]10 - 470H - 13 - 11%"
    assert facts.scheduled_combined_rating == 11
    assert facts.combined_rating == 11
    assert facts.final_pd_percent == 11
    assert facts.rating_string == "15.01.02.02 - 8 - [5]10 - 470H - 13 - 11%"


def test_r38_final_pd_is_literal_not_derived_noise() -> None:
    """m23-6: authored operands deterministically finish at eleven percent."""
    assert _worked_example().final_pd_percent == 11


class _Post2013RegisterEntry:
    def __getitem__(self, index: int) -> object:
        if index == 0:
            raise AssertionError("2013+ consulted the FEC rank")
        if index == 1:
            return "Cervical \N{EN DASH} Range of Motion \N{EN DASH} Soft Tissue Lesion"
        raise AssertionError(f"unexpected parsed.imp index {index}")


class _Post2013ForbiddenFec(dict[str, int]):
    def __getitem__(self, key: str) -> int:
        raise AssertionError(f"2013+ consulted parsed.fec[{key!r}]")

    def __contains__(self, key: object) -> bool:
        raise AssertionError(f"2013+ consulted parsed.fec membership for {key!r}")

    def get(self, key: str, default: object = None) -> int:
        raise AssertionError(f"2013+ consulted parsed.fec.get({key!r}, {default!r})")


def test_post2013_derivation_never_reads_fec_rank_or_table() -> None:
    """m23-7: the raising spy covers both forbidden post-2013 source reads."""
    source = load_rating_source_bundle()
    register = dict(source.impairment_register)
    register["15.01.02.02"] = _Post2013RegisterEntry()  # type: ignore[assignment]
    guarded = replace(
        source,
        impairment_register=register,
        fec_lookup=_Post2013ForbiddenFec(),
    )
    facts = derive_rating_facts(
        RatingScenario.model_validate(_rating(rows=[_row(wpi=8)])),
        date_of_injury=date(2013, 6, 15),
        birth_date=date(1983, 6, 15),
        occupation_title="Warehouse worker",
        bundle=guarded,
    )
    row = facts.impairments[0]
    assert row.description == (
        "Cervical \N{EN DASH} Range of Motion \N{EN DASH} Soft Tissue Lesion"
    )
    assert row.adjustment_method == "dfec_1_4"
    assert row.fec_rank is None
    assert row.adjustment_factor == Decimal("1.4")
    assert row.schedule_adjusted == 11
    assert row.rating_string == "15.01.02.02 - 8 - [1.4]11 - 470H - 14 - 12%"


def test_r38_occupation_adjustment_is_not_skipped() -> None:
    """m23-8: the worked row advances from schedule ten to occupation thirteen."""
    row = _worked_example().impairments[0]
    assert row.schedule_adjusted == 10
    assert row.occupation_adjusted == 13


def test_r38_age_adjustment_is_not_skipped() -> None:
    """m23-9: age band 27-31 advances occupation thirteen to eleven."""
    row = _worked_example().impairments[0]
    assert row.occupation_adjusted == 13
    assert row.age_adjusted == 11


def test_r39_rating_string_token_order_is_exact_ascii() -> None:
    """m23-10: punctuation, adjacency, token order, and percent are frozen."""
    value = _worked_example().impairments[0].rating_string
    assert value == "15.01.02.02 - 8 - [5]10 - 470H - 13 - 11%"
    assert value.isascii()


@pytest.mark.parametrize(
    ("table_name", "missing_key", "expected_code"),
    [
        ("occupational_adjustment", "10", RATING_OCC_CELL_MISSING),
        ("age_adjustment", "13", RATING_AGE_CELL_MISSING),
    ],
)
def test_r36_missing_adjustment_cells_fail_closed(
    table_name: str, missing_key: str, expected_code: str
) -> None:
    source = load_rating_source_bundle()
    table = dict(getattr(source, table_name))
    table.pop(missing_key)
    with pytest.raises(RatingValidationError) as excinfo:
        derive_rating_facts(
            RatingScenario.model_validate(_rating(rows=[_row(wpi=8)])),
            date_of_injury=date(2012, 6, 15),
            birth_date=date(1982, 6, 15),
            occupation_title="Warehouse worker",
            bundle=replace(source, **{table_name: table}),
        )
    assert excinfo.value.code == expected_code


def _controlled_cvc_bundle():
    source = load_rating_source_bundle()
    zeroes = (0, 0, 0, 0, 0, 0, 0, 0)

    def variant_row(value: int) -> tuple[int, ...]:
        return (*zeroes[:5], value, *zeroes[6:])

    def age_row(value: int) -> tuple[int, ...]:
        return (1, 1, value, 1, 1, 1, 1, 1, 1, 1)

    return replace(
        source,
        impairment_register={
            "15.02.01.00": (1, "row thirteen"),
            "15.03.01.00": (2, "row fifty"),
            "15.01.02.02": (5, "row thirty-two"),
        },
        fec_lookup={"1|8": 5, "2|8": 20, "5|8": 10},
        occupational_adjustment={
            "5": variant_row(13),
            "20": variant_row(50),
            "10": variant_row(30),
        },
        age_adjustment={
            "13": age_row(13),
            "50": age_row(50),
            "30": age_row(32),
        },
    )


def test_r40_cvc_combines_descending_but_serializes_authored_order() -> None:
    rating = RatingScenario.model_validate(
        _rating(
            rows=[
                _row("thirteen", "cervical_spine", "15.02.01.00", 8),
                _row("fifty", "lumbar_spine", "15.03.01.00", 8),
                _row("thirty-two", "thoracic_spine", "15.01.02.02", 8),
            ],
            combination_method="cvc",
        )
    )
    facts = derive_rating_facts(
        rating,
        date_of_injury=date(2012, 6, 15),
        birth_date=date(1982, 6, 15),
        occupation_title="Warehouse worker",
        bundle=_controlled_cvc_bundle(),
    )
    assert tuple(row.id for row in facts.impairments) == (
        "thirteen",
        "fifty",
        "thirty-two",
    )
    assert tuple(row.age_adjusted for row in facts.impairments) == (13, 50, 32)
    assert facts.scheduled_combined_rating == 70
    assert facts.combined_rating == 70
    assert facts.final_pd_percent == 70
    assert facts.rating_string == (
        "15.02.01.00 - 8 - [1]5 - 470H - 13 - 13%\n"
        "15.03.01.00 - 8 - [2]20 - 470H - 50 - 50%\n"
        "15.01.02.02 - 8 - [5]10 - 470H - 30 - 32%\n"
        "Combined PD (CVC): 70%"
    )


def test_r41_official_cvc_examples_use_decimal_half_up() -> None:
    assert combine_cvc_ratings((50, 32)) == 66
    assert combine_cvc_ratings((66, 13)) == 70
    assert combine_cvc_ratings((70, 4)) == 71
    # Section 8 extracted-text SHA-256:
    # 827d66440bc9161743aa6add355c823a6d7d5913162df140f38bc871f83f47b1
    assert combine_cvc_ratings((50, 1)) == 51


def test_cvc_rejects_duplicate_body_parts_even_for_different_impairments() -> None:
    rows = [
        _row("first", "cervical_spine", "15.01.02.02"),
        _row("second", "cervical_spine", "15.02.01.00"),
    ]
    message = _message(
        rating=_rating(rows=rows, combination_method="cvc"),
        body_parts=["cervical_spine"],
    )
    assert RATING_COMBINATION_UNSUPPORTED_OVERLAP in message
    assert "unique body part" in message


def _derive_controlled_two_row_rating(rating: RatingScenario, *, capped: bool = False):
    bundle = _controlled_cvc_bundle()
    if capped:
        def age_row(value: int) -> tuple[int, ...]:
            return (1, 1, value, 1, 1, 1, 1, 1, 1, 1)

        bundle = replace(
            bundle,
            age_adjustment={"13": age_row(60), "50": age_row(55)},
        )
    return derive_rating_facts(
        rating,
        date_of_injury=date(2012, 6, 15),
        birth_date=date(1982, 6, 15),
        occupation_title="Warehouse worker",
        bundle=bundle,
    )


def _controlled_two_row_payload() -> dict[str, Any]:
    return _rating(
        rows=[
            _row("thirteen", "cervical_spine", "15.02.01.00", 8),
            _row("fifty", "lumbar_spine", "15.03.01.00", 8),
        ],
        combination_method="cvc",
    )


def test_r42_raw_opt_in_is_the_only_kite_addition_switch() -> None:
    """Form C: identical rows stay CVC unless raw YAML names the exact pair."""
    plain = RatingScenario.model_validate(_controlled_two_row_payload())
    assert "kite_addition" not in plain.model_fields_set
    plain_facts = _derive_controlled_two_row_rating(plain)
    assert plain_facts.combination_method == "cvc"
    assert plain_facts.kite_impairment_ids is None
    assert plain_facts.scheduled_combined_rating == 57
    assert plain_facts.combined_rating == 57
    assert plain_facts.final_pd_percent == 57
    assert plain_facts.rating_string.endswith("Combined PD (CVC): 57%")

    explicit_null_payload = _controlled_two_row_payload()
    explicit_null_payload["kite_addition"] = None
    explicit_null = RatingScenario.model_validate(explicit_null_payload)
    assert "kite_addition" in explicit_null.model_fields_set
    assert explicit_null.kite_addition is None
    assert _derive_controlled_two_row_rating(explicit_null).combination_method == "cvc"

    opted_in_payload = _controlled_two_row_payload()
    opted_in_payload["kite_addition"] = {
        "impairment_ids": ["fifty", "thirteen"]
    }
    opted_in = RatingScenario.model_validate(opted_in_payload)
    assert "kite_addition" in opted_in.model_fields_set
    kite_facts = _derive_controlled_two_row_rating(opted_in)
    assert kite_facts.combination_method == "kite_addition"
    assert kite_facts.kite_impairment_ids == ("thirteen", "fifty")
    assert kite_facts.scheduled_combined_rating == 57
    assert kite_facts.combined_rating == 63
    assert kite_facts.final_pd_percent == 63
    assert kite_facts.rating_string == (
        "15.02.01.00 - 8 - [1]5 - 470H - 13 - 13%\n"
        "15.03.01.00 - 8 - [2]20 - 470H - 50 - 50%\n"
        "Combined PD (Kite addition; explicit pair thirteen+fifty; "
        "scheduled CVC 57%): 63%"
    )


def test_r42_kite_addition_is_capped_at_100_after_retaining_scheduled_cvc() -> None:
    """m23-30: 60 + 55 caps at 100 while its scheduled CVC remains 82."""
    payload = _controlled_two_row_payload()
    payload["kite_addition"] = {
        "impairment_ids": ["thirteen", "fifty"]
    }
    facts = _derive_controlled_two_row_rating(
        RatingScenario.model_validate(payload), capped=True
    )
    assert tuple(row.age_adjusted for row in facts.impairments) == (60, 55)
    assert facts.scheduled_combined_rating == 82
    assert facts.combined_rating == 100
    assert facts.final_pd_percent == 100
    assert facts.rating_string.endswith(
        "Combined PD (Kite addition; explicit pair thirteen+fifty; "
        "scheduled CVC 82%): 100%"
    )


def test_r42_kite_hook_and_existing_corpora_never_auto_select_addition() -> None:
    """m23-11: doctrine prose and two rows cannot replace raw opt-in."""
    rows = [
        _row("shoulder", "shoulder", "16.02.01.00"),
        _row("knee", "knee", "17.05.04.00"),
    ]
    payload = _seed(
        wages={},
        rating=_rating(rows=rows, combination_method="cvc"),
        body_parts=["shoulder", "knee"],
    )
    payload["profile"] = {
        "applicant": {"age": 30, "occupation": "Warehouse worker"}
    }
    payload["lifecycle"]["doctrine_hooks"] = ["kite"]
    direct = build_case_plan(parse_case_seed(payload)).case_facts
    assert direct is not None and direct.rating is not None
    assert direct.rating.combination_method == "cvc"
    assert direct.rating.kite_impairment_ids is None
    assert direct.rating.combined_rating == direct.rating.scheduled_combined_rating
    assert direct.rating.final_pd_percent == direct.rating.scheduled_combined_rating
    assert "Kite addition" not in direct.rating.rating_string

    opted_in_payload = _seed(
        wages={},
        rating=_rating(
            rows=rows,
            combination_method="cvc",
            kite_addition={"impairment_ids": ["knee", "shoulder"]},
        ),
        body_parts=["shoulder", "knee"],
    )
    opted_in_payload["profile"] = payload["profile"]
    opted_in_payload["lifecycle"]["doctrine_hooks"] = ["kite"]
    opted_in = build_case_plan(parse_case_seed(opted_in_payload)).case_facts
    assert opted_in is not None and opted_in.rating is not None
    assert opted_in.rating.combination_method == "kite_addition"
    assert opted_in.rating.kite_impairment_ids == ("shoulder", "knee")
    assert opted_in.rating.scheduled_combined_rating == combine_cvc_ratings(
        tuple(row.age_adjusted for row in opted_in.rating.impairments)
    )
    assert opted_in.rating.combined_rating == min(
        100, sum(row.age_adjusted for row in opted_in.rating.impairments)
    )
    assert opted_in.rating.final_pd_percent == opted_in.rating.combined_rating

    examples = Path(__file__).resolve().parents[1] / "examples"
    existing_specs = (
        "demo-caseload.yaml",
        "doctrine-showcase.yaml",
        "medical-story-showcase.yaml",
        "money-showcase.yaml",
        "personas-showcase.yaml",
    )
    for name in existing_specs:
        path = examples / name
        assert "kite_addition:" not in path.read_text(encoding="utf-8")
        for seed in resolve_caseload(load_caseload_spec(path)):
            facts = build_case_plan(seed).case_facts
            assert facts is not None
            if facts.rating is None:
                continue
            assert facts.rating.combination_method != "kite_addition"
            assert facts.rating.kite_impairment_ids is None
            assert facts.rating.combined_rating == facts.rating.scheduled_combined_rating
            assert facts.rating.final_pd_percent == facts.rating.scheduled_combined_rating
            assert "Kite addition" not in facts.rating.rating_string


def test_rating_present_seed_populates_case_facts_from_resolved_plan_inputs() -> None:
    payload = _seed(wages={}, doi="2013-01-01")
    payload["profile"] = {
        "applicant": {"age": 30, "occupation": "Warehouse worker"}
    }
    plan = build_case_plan(parse_case_seed(payload))
    assert plan.case_facts is not None
    facts = plan.case_facts.rating
    assert facts is not None
    assert facts.date_of_injury == plan.timeline.injury_date
    assert facts.applicant_age == applicant_age_at_doi(
        plan.timeline.injury_date, plan.cast.case.applicant.date_of_birth
    )
    assert facts.occupation_title == plan.cast.case.employer.position
    assert facts.final_pd_percent == facts.impairments[0].age_adjusted
    assert plan.case_facts.wpi == facts.impairments[0].wpi
    assert plan.case_facts.pd == facts.final_pd_percent


def _carrier_probe(
    *,
    rows: list[dict[str, Any]],
    hooks: list[str] | None = None,
    documents: dict[str, Any] | None = None,
):
    payload = _seed(
        wages={},
        rating=_rating(
            rows=rows,
            combination_method="single" if len(rows) == 1 else "cvc",
        ),
        body_parts=["shoulder", "knee"],
    )
    payload["profile"] = {
        "applicant": {"age": 30, "occupation": "Warehouse worker"}
    }
    payload["lifecycle"]["doctrine_hooks"] = hooks or []
    if documents is not None:
        payload["documents"] = documents
    return parse_case_seed(payload)


def _planned_rating_carriers(seed: Any) -> frozenset[str]:
    try:
        plan = build_case_plan(seed)
    except RatingValidationError as exc:
        # Mutation guards must fail as assertions, never score a production
        # exception as evidence that the requested matrix was enforced.
        return frozenset({f"ERROR:{exc.code}"})
    return frozenset(
        document.subtype
        for document in plan.documents
        if document.subtype in EXPECTED_RATING_CARRIERS
    )


def test_r48_rating_carrier_matrix_is_literal_and_deterministic() -> None:
    """m23-12: lifecycle randomness cannot choose rating carriers."""
    single = [_row("shoulder", "shoulder", "16.02.01.00", 8)]
    multiple = [
        _row("shoulder", "shoulder", "16.02.01.00", 8),
        _row("knee", "knee", "17.05.04.00", 8),
    ]
    calculations = frozenset({"PD_RATING_CALCULATION_WORKSHEET"})
    calculations_and_impairments = frozenset(
        {"PD_RATING_CALCULATION_WORKSHEET", "IMPAIRMENT_RATING_WORKSHEET"}
    )
    matrix = (
        (single, [], calculations),
        (single, ["ogilvie"], calculations),
        (single, ["almaraz_guzman"], calculations_and_impairments),
        (single, ["sibtf"], calculations_and_impairments),
        (single, ["kite"], EXPECTED_RATING_CARRIERS),
        (multiple, [], EXPECTED_RATING_CARRIERS),
    )
    assert frozenset(
        {
            "IMPAIRMENT_RATING_WORKSHEET",
            "PD_RATING_CALCULATION_WORKSHEET",
            "PD_RATING_CONVERSION",
        }
    ) == EXPECTED_RATING_CARRIERS
    assert frozenset(
        {
            "ogilvie",
            "almaraz_guzman",
            "escobedo",
            "benson",
            "kite",
            "lc4664_prior_award",
        }
    ) == EXPECTED_RATING_GROUNDING_HOOKS
    for rows, hooks, expected in matrix:
        actual = _planned_rating_carriers(_carrier_probe(rows=rows, hooks=hooks))
        assert actual == expected, (hooks, len(rows), actual, expected)

    plan = build_case_plan(_carrier_probe(rows=multiple))
    assert sum(
        document.subtype == "PD_RATING_CALCULATION_WORKSHEET"
        for document in plan.documents
    ) == 1
    assert all(
        document.subtype != "INFORMAL_PD_RATING_PRINTOUT"
        for document in plan.documents
    )


@pytest.mark.parametrize("subtype", sorted(EXPECTED_RATING_CARRIERS))
def test_r48_explicit_control_cannot_remove_a_required_carrier(
    subtype: str,
) -> None:
    rows = [
        _row("shoulder", "shoulder", "16.02.01.00", 8),
        _row("knee", "knee", "17.05.04.00", 8),
    ]
    seed = _carrier_probe(rows=rows, documents={"exclude": [subtype]})
    with pytest.raises(RatingValidationError) as excinfo:
        build_case_plan(seed)
    assert excinfo.value.code == RATING_REQUIRED_CARRIER_REMOVED
    assert excinfo.value.path == "documents"
    assert subtype in excinfo.value.value


def test_r48_controls_may_add_copies_without_changing_rating_truth() -> None:
    rows = [_row("shoulder", "shoulder", "16.02.01.00", 8)]
    seed = _carrier_probe(
        rows=rows,
        documents={
            "overrides": [
                {
                    "subtype": "PD_RATING_CALCULATION_WORKSHEET",
                    "count": 3,
                }
            ]
        },
    )
    plan = build_case_plan(seed)
    copies = [
        document
        for document in plan.documents
        if document.subtype == "PD_RATING_CALCULATION_WORKSHEET"
    ]
    assert len(copies) == 3
    assert plan.case_facts is not None
    assert plan.case_facts.rating is not None
