"""Money W2 Items 7-8 defense models, arithmetic, events, and planner oracles."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

from conftest import extract_text, requires_substrate
from wc_caseload_engine.defense_lens import (
    DEFENSE_ACCOUNTING_EQUATION_BROKEN,
    DEFENSE_ARTIFACT_BINDING_MISMATCH,
    DEFENSE_ARTIFACT_BINDING_MISSING,
    DEFENSE_BUCKET_CATEGORIES,
    DEFENSE_DUPLICATE_INITIAL_REVIEW_EVENT,
    DEFENSE_DUPLICATE_PAID_COST_ID,
    DEFENSE_DUPLICATE_RESERVE_TRIGGER,
    DEFENSE_DUPLICATE_W1_PAID_COST,
    DEFENSE_ERROR_CODES,
    DEFENSE_EXPOSURE_BELOW_PAID,
    DEFENSE_INELIGIBLE_RESERVE_TRIGGER,
    DEFENSE_INITIAL_FILE_REVIEW_REQUIRED,
    DEFENSE_INITIAL_REVIEW_REQUIRED,
    DEFENSE_INVALID_BUCKET_CATEGORY,
    DEFENSE_INVALID_EXPOSURE_RANGE,
    DEFENSE_NEGATIVE_AMOUNT,
    DEFENSE_REQUIRED_CARRIER_REMOVED,
    DEFENSE_REQUIRES_DEFENSE_PERSPECTIVE,
    DEFENSE_REQUIRES_WAGES,
    DEFENSE_RESERVE_TRIGGERS,
    DEFENSE_TRIGGER_OCCURRENCE_ID_MISSING,
    DEFENSE_TRIGGER_ORDER_INVALID,
    DEFENSE_TRIGGER_SOURCE_DATE_MISMATCH,
    DEFENSE_TRIGGER_SOURCE_REMOVED,
    DEFENSE_UNBOUND_RESERVE_NOTICE,
    DEFENSE_UNKNOWN_RESERVE_TRIGGER,
    BucketAmounts,
    DefenseLensFacts,
    DefenseLensScenario,
    DefenseScorerLabels,
    ExposureInput,
    ExposureProjection,
    InitialFileReview,
    PaidCost,
    PaidCostInput,
    ReserveArtifactBinding,
    ReserveEvent,
    ReserveSnapshot,
    TriggerOccurrence,
    apply_booking_policy,
    bind_defense_artifacts,
    bind_defense_facts,
    build_unbound_defense,
    is_stair_stepping,
    paid_cost_ledger,
    paid_to_date,
    project_exposure,
    recommended_reserve_snapshot,
    reserve_adequacy,
    reserve_event_for_document,
    resolve_trigger_occurrences,
    validate_exposure_against_paid,
    validate_required_trigger_sources,
    validate_reserve_artifact_candidates,
)
from wc_caseload_engine.fact_templates import fact_aware_templates
from wc_caseload_engine.lifecycle_bridge import DatedCandidate
from wc_caseload_engine.planner import DEFENSE_PLANNER_STAGES, build_case_plan
from wc_caseload_engine.renderer import render_document
from wc_caseload_engine.seeds import SeedValidationError, parse_case_seed, seed_to_dict

EXPECTED_SCENARIO_FIELDS = (
    "case_evaluation",
    "assumptions",
    "discovery_plan",
    "litigation_budget",
    "exposure_events",
    "paid_costs",
)
EXPECTED_BUCKET_FIELDS = ("indemnity", "medical", "expense_alae")
EXPECTED_EXPOSURE_INPUT_FIELDS = ("trigger", "low", "expected", "high")
EXPECTED_PAID_FIELDS = (
    "id",
    "date",
    "bucket",
    "category",
    "amount",
    "source_document_subtype",
)
EXPECTED_PROJECTION_FIELDS = (
    "trigger",
    "effective_date",
    "low",
    "expected",
    "high",
    "assumptions",
)
EXPECTED_SNAPSHOT_FIELDS = ("paid", "outstanding_reserve", "incurred")
EXPECTED_FACT_FIELDS = (
    "exposure_events",
    "paid_costs",
    "initial_file_review",
    "reserve_events",
    "scorer_labels",
)
EXPECTED_SCORER_LABEL_FIELDS = (
    "stair_stepping",
    "reserve_adequacy",
)
EXPECTED_OCCURRENCE_FIELDS = (
    "trigger",
    "semantic_event_id",
    "effective_date",
    "source_kind",
    "source_record_id",
    "requires_planned_document",
)
EXPECTED_BINDING_FIELDS = ("event_id", "document_index", "subtype", "document_date")
EXPECTED_IFR_FIELDS = (
    "event_id",
    "review_date",
    "case_evaluation",
    "compensability_posture",
    "exposure",
    "recommendation",
    "booked_snapshot",
    "litigation_budget",
    "discovery_plan",
    "assumptions",
    "authority_status",
    "adoption_lag_days",
    "artifact_binding",
)
EXPECTED_IFR_WIRE_KEYS = (
    "eventId",
    "reviewDate",
    "caseEvaluation",
    "compensabilityPosture",
    "exposure",
    "recommendation",
    "bookedSnapshot",
    "litigationBudget",
    "discoveryPlan",
    "assumptions",
    "authorityStatus",
    "adoptionLagDays",
    "artifactBinding",
)
EXPECTED_RESERVE_EVENT_FIELDS = (
    "id",
    "trigger",
    "event_date",
    "prior_snapshot",
    "exposure",
    "recommendation",
    "booked_snapshot",
    "adoption_lag_days",
    "reason",
    "artifact_binding",
)
EXPECTED_TRIGGERS = (
    "initial_file_review",
    "compensability_decision",
    "aoe_coe_outcome",
    "surgery_authorized",
    "mmi",
    "qme_ame_wpi",
    "formal_rating",
    "trial_setting",
    "petition_for_reconsideration",
)
EXPECTED_BUCKET_CATEGORIES = {
    "indemnity": ("td", "pd", "life_pension", "death"),
    "medical": ("treatment", "future_medical", "msa"),
    "expense_alae": (
        "defense_fees",
        "med_legal",
        "sub_rosa",
        "interpreters",
        "court_reporters",
        "copy_service",
    ),
}
EXPECTED_DEFENSE_ERROR_CODES = {
    "DEFENSE_REQUIRES_WAGES",
    "DEFENSE_REQUIRES_DEFENSE_PERSPECTIVE",
    "DEFENSE_INVALID_BUCKET_CATEGORY",
    "DEFENSE_INVALID_EXPOSURE_RANGE",
    "DEFENSE_EXPOSURE_BELOW_PAID",
    "DEFENSE_DUPLICATE_W1_PAID_COST",
    "DEFENSE_UNKNOWN_RESERVE_TRIGGER",
    "DEFENSE_INELIGIBLE_RESERVE_TRIGGER",
    "DEFENSE_INITIAL_REVIEW_REQUIRED",
    "DEFENSE_DUPLICATE_INITIAL_REVIEW_EVENT",
    "DEFENSE_TRIGGER_ORDER_INVALID",
    "DEFENSE_TRIGGER_OCCURRENCE_ID_MISSING",
    "DEFENSE_TRIGGER_SOURCE_REMOVED",
    "DEFENSE_TRIGGER_SOURCE_DATE_MISMATCH",
    "DEFENSE_REQUIRED_CARRIER_REMOVED",
    "DEFENSE_ARTIFACT_BINDING_MISSING",
    "DEFENSE_ARTIFACT_BINDING_MISMATCH",
    "DEFENSE_UNBOUND_RESERVE_NOTICE",
    "DEFENSE_ACCOUNTING_EQUATION_BROKEN",
}


def _amounts(
    indemnity: str = "100.00",
    medical: str = "50.00",
    expense_alae: str = "25.00",
) -> BucketAmounts:
    return BucketAmounts(
        indemnity=indemnity,
        medical=medical,
        expense_alae=expense_alae,
    )


def _exposure(
    trigger: str = "initial_file_review",
    *,
    low: BucketAmounts | None = None,
    expected: BucketAmounts | None = None,
    high: BucketAmounts | None = None,
) -> ExposureInput:
    return ExposureInput(
        trigger=trigger,
        low=low or _amounts("100.00", "50.00", "25.00"),
        expected=expected or _amounts("150.00", "80.00", "40.00"),
        high=high or _amounts("200.00", "110.00", "55.00"),
    )


def _defense_block() -> dict[str, Any]:
    return {
        "case_evaluation": "Accepted lumbar claim with active treatment.",
        "assumptions": ["No surgery unless later authorized."],
        "discovery_plan": ["Obtain prior treatment records."],
        "litigation_budget": 25000,
        "exposure_events": [
            {
                "trigger": "initial_file_review",
                "low": {
                    "indemnity": 10000,
                    "medical": 15000,
                    "expense_alae": 5000,
                },
                "expected": {
                    "indemnity": 20000,
                    "medical": 30000,
                    "expense_alae": 10000,
                },
                "high": {
                    "indemnity": 40000,
                    "medical": 60000,
                    "expense_alae": 20000,
                },
            }
        ],
        "paid_costs": [],
    }


def _seed(*, perspective: str = "defense", wages: bool = True) -> dict[str, Any]:
    scenario: dict[str, Any] = {"defense_lens": _defense_block()}
    if wages:
        scenario["wages"] = {}
    return {
        "case_id": "defense-item-7",
        "rng_seed": 7007,
        "perspective": perspective,
        "injury": {
            "type": "specific",
            "date_of_injury": "2021-01-15",
            "body_parts": [{"part": "lumbar_spine"}],
        },
        "lifecycle": {"target_stage": "resolved"},
        "scenario": scenario,
    }


def _seed_with_compensability() -> dict[str, Any]:
    raw = _seed()
    raw["scenario"]["defense_lens"]["exposure_events"].append(
        {
            "trigger": "compensability_decision",
            "low": {
                "indemnity": 1000000,
                "medical": 1000000,
                "expense_alae": 1000000,
            },
            "expected": {
                "indemnity": 1100000,
                "medical": 1100000,
                "expense_alae": 1100000,
            },
            "high": {
                "indemnity": 1200000,
                "medical": 1200000,
                "expense_alae": 1200000,
            },
        }
    )
    return raw


def test_r54_r57_r60_r71_model_fields_and_registers_are_literal() -> None:
    assert tuple(DefenseLensScenario.model_fields) == EXPECTED_SCENARIO_FIELDS
    assert tuple(BucketAmounts.model_fields) == EXPECTED_BUCKET_FIELDS
    assert tuple(ExposureInput.model_fields) == EXPECTED_EXPOSURE_INPUT_FIELDS
    assert tuple(PaidCostInput.model_fields) == EXPECTED_PAID_FIELDS
    assert tuple(PaidCost.model_fields) == EXPECTED_PAID_FIELDS
    assert tuple(ExposureProjection.model_fields) == EXPECTED_PROJECTION_FIELDS
    assert tuple(ReserveSnapshot.model_fields) == EXPECTED_SNAPSHOT_FIELDS
    assert tuple(DefenseLensFacts.model_fields) == EXPECTED_FACT_FIELDS
    assert tuple(DefenseScorerLabels.model_fields) == EXPECTED_SCORER_LABEL_FIELDS
    assert tuple(TriggerOccurrence.model_fields) == EXPECTED_OCCURRENCE_FIELDS
    assert tuple(ReserveArtifactBinding.model_fields) == EXPECTED_BINDING_FIELDS
    assert tuple(InitialFileReview.model_fields) == EXPECTED_IFR_FIELDS
    assert EXPECTED_IFR_WIRE_KEYS == (
        "eventId",
        "reviewDate",
        "caseEvaluation",
        "compensabilityPosture",
        "exposure",
        "recommendation",
        "bookedSnapshot",
        "litigationBudget",
        "discoveryPlan",
        "assumptions",
        "authorityStatus",
        "adoptionLagDays",
        "artifactBinding",
    )
    assert tuple(ReserveEvent.model_fields) == EXPECTED_RESERVE_EVENT_FIELDS
    assert ExposureInput.model_fields["low"].annotation is BucketAmounts
    assert DEFENSE_RESERVE_TRIGGERS == EXPECTED_TRIGGERS
    assert DEFENSE_BUCKET_CATEGORIES == EXPECTED_BUCKET_CATEGORIES


def test_r79_error_code_register_and_remediation_table_are_literal() -> None:
    assert DEFENSE_ERROR_CODES == EXPECTED_DEFENSE_ERROR_CODES
    assert {
        DEFENSE_REQUIRES_WAGES,
        DEFENSE_REQUIRES_DEFENSE_PERSPECTIVE,
        DEFENSE_INVALID_BUCKET_CATEGORY,
        DEFENSE_INVALID_EXPOSURE_RANGE,
        DEFENSE_EXPOSURE_BELOW_PAID,
        DEFENSE_DUPLICATE_W1_PAID_COST,
        DEFENSE_UNKNOWN_RESERVE_TRIGGER,
        DEFENSE_INELIGIBLE_RESERVE_TRIGGER,
        DEFENSE_INITIAL_REVIEW_REQUIRED,
        DEFENSE_DUPLICATE_INITIAL_REVIEW_EVENT,
        DEFENSE_TRIGGER_ORDER_INVALID,
        DEFENSE_TRIGGER_OCCURRENCE_ID_MISSING,
        DEFENSE_TRIGGER_SOURCE_REMOVED,
        DEFENSE_TRIGGER_SOURCE_DATE_MISMATCH,
        DEFENSE_REQUIRED_CARRIER_REMOVED,
        DEFENSE_ARTIFACT_BINDING_MISSING,
        DEFENSE_ARTIFACT_BINDING_MISMATCH,
        DEFENSE_UNBOUND_RESERVE_NOTICE,
        DEFENSE_ACCOUNTING_EQUATION_BROKEN,
    } == EXPECTED_DEFENSE_ERROR_CODES
    remediation = {
        "DEFENSE_REQUIRES_WAGES": ("wages", "author scenario.wages"),
        "DEFENSE_REQUIRES_DEFENSE_PERSPECTIVE": (
            "perspective",
            "set perspective: defense",
        ),
        "DEFENSE_INVALID_BUCKET_CATEGORY": ("category", "use the bucket's category"),
        "DEFENSE_INVALID_EXPOSURE_RANGE": ("low", "order low, expected, high"),
        "DEFENSE_EXPOSURE_BELOW_PAID": ("paid-to-date", "raise every ultimate bound"),
        "DEFENSE_DUPLICATE_W1_PAID_COST": ("duplicate", "remove the W1 paid copy"),
        "DEFENSE_UNKNOWN_RESERVE_TRIGGER": ("trigger", "use an R61 trigger"),
        "DEFENSE_INELIGIBLE_RESERVE_TRIGGER": ("eligible", "seed its semantic source"),
        "DEFENSE_INITIAL_REVIEW_REQUIRED": (
            "initial_file_review",
            "author it exactly once",
        ),
        "DEFENSE_DUPLICATE_INITIAL_REVIEW_EVENT": (
            "InitialFileReview",
            "remove it from reserve_events",
        ),
        "DEFENSE_TRIGGER_ORDER_INVALID": ("chronological", "order resolved events"),
        "DEFENSE_TRIGGER_OCCURRENCE_ID_MISSING": (
            "occurrence",
            "retain the semantic event ID",
        ),
        "DEFENSE_TRIGGER_SOURCE_REMOVED": ("source", "retain one consumed source"),
        "DEFENSE_TRIGGER_SOURCE_DATE_MISMATCH": (
            "date",
            "restore the semantic source date",
        ),
        "DEFENSE_REQUIRED_CARRIER_REMOVED": ("carrier", "retain the required artifact"),
        "DEFENSE_ARTIFACT_BINDING_MISSING": ("binding", "restore the final binding"),
        "DEFENSE_ARTIFACT_BINDING_MISMATCH": ("binding", "match event ID, subtype, date"),
        "DEFENSE_UNBOUND_RESERVE_NOTICE": ("notice", "remove the unbound notice"),
        "DEFENSE_ACCOUNTING_EQUATION_BROKEN": (
            "incurred",
            "set incurred to paid plus outstanding",
        ),
    }
    assert set(remediation) == EXPECTED_DEFENSE_ERROR_CODES
    assert all(fragment and edit for fragment, edit in remediation.values())


def test_defense_seed_requires_wages_and_defense_perspective() -> None:
    parsed = parse_case_seed(_seed())
    assert parsed.scenario.defense_lens is not None
    assert parsed.scenario.defense_lens.litigation_budget == Decimal("25000.00")

    with pytest.raises(SeedValidationError, match=DEFENSE_REQUIRES_WAGES):
        parse_case_seed(_seed(wages=False))
    with pytest.raises(
        SeedValidationError,
        match=DEFENSE_REQUIRES_DEFENSE_PERSPECTIVE,
    ):
        parse_case_seed(_seed(perspective="applicant"))


def test_absent_defense_seed_stays_unset_and_serializes_no_block() -> None:
    raw = _seed()
    del raw["scenario"]["defense_lens"]
    parsed = parse_case_seed(raw)
    assert parsed.scenario.defense_lens is None
    assert "defense_lens" not in seed_to_dict(parsed)["scenario"]


def test_authored_seed_cannot_supply_derived_reserve_fields() -> None:
    for forbidden in (
        "booked_reserve",
        "incurred",
        "stair_stepping",
        "reserve_adequacy",
        "event_dates",
        "artifact_bindings",
    ):
        raw = _seed()
        raw["scenario"]["defense_lens"][forbidden] = "not authored"
        with pytest.raises(SeedValidationError, match="unknown field"):
            parse_case_seed(raw)


def test_trigger_range_identifier_and_category_validation_fail_closed() -> None:
    with pytest.raises(ValidationError, match=DEFENSE_UNKNOWN_RESERVE_TRIGGER):
        _exposure("not_a_trigger")

    with pytest.raises(ValidationError, match=DEFENSE_INVALID_EXPOSURE_RANGE):
        _exposure(
            low=_amounts("101.00", "50.00", "25.00"),
            expected=_amounts("100.00", "80.00", "40.00"),
        )

    with pytest.raises(ValidationError, match=DEFENSE_NEGATIVE_AMOUNT):
        _amounts("-0.01", "0", "0")

    with pytest.raises(ValidationError, match=DEFENSE_INVALID_BUCKET_CATEGORY):
        PaidCostInput(
            id="bad-pair",
            date=date(2022, 1, 1),
            bucket="medical",
            category="defense_fees",
            amount="1.00",
            source_document_subtype="MEDICAL_BILL",
        )
    with pytest.raises(ValidationError, match=DEFENSE_INVALID_BUCKET_CATEGORY):
        PaidCostInput.model_validate(
            {
                "id": "unknown-category",
                "date": "2022-01-01",
                "bucket": "medical",
                "category": "not_a_category",
                "amount": "1.00",
                "source_document_subtype": "MEDICAL_BILL",
            }
        )

    first = _exposure()
    repeated = _exposure("compensability_decision")
    with pytest.raises(ValidationError, match=DEFENSE_DUPLICATE_RESERVE_TRIGGER):
        DefenseLensScenario(
            case_evaluation="literal",
            assumptions=(),
            discovery_plan=(),
            litigation_budget="1.00",
            exposure_events=(first, repeated, repeated),
        )
    with pytest.raises(ValidationError, match=DEFENSE_INITIAL_FILE_REVIEW_REQUIRED):
        DefenseLensScenario(
            case_evaluation="literal",
            assumptions=(),
            discovery_plan=(),
            litigation_budget="1.00",
            exposure_events=(repeated,),
        )

    duplicate = PaidCostInput(
        id="same",
        date=date(2022, 1, 1),
        bucket="medical",
        category="treatment",
        amount="1.00",
        source_document_subtype="MEDICAL_BILL",
    )
    with pytest.raises(ValidationError, match=DEFENSE_DUPLICATE_PAID_COST_ID):
        DefenseLensScenario(
            case_evaluation="literal",
            assumptions=(),
            discovery_plan=(),
            litigation_budget="1.00",
            exposure_events=(first,),
            paid_costs=(duplicate, duplicate),
        )


def test_paid_ledger_sorts_and_sums_w1_and_non_w1_costs_through_snapshot() -> None:
    inputs = (
        PaidCostInput(
            id="expense",
            date=date(2022, 2, 1),
            bucket="expense_alae",
            category="defense_fees",
            amount="30.00",
            source_document_subtype="LEGAL_INVOICE",
        ),
        PaidCostInput(
            id="indemnity",
            date=date(2022, 1, 1),
            bucket="indemnity",
            category="life_pension",
            amount="10.00",
            source_document_subtype="BENEFIT_PAYMENT_LEDGER",
        ),
        PaidCostInput(
            id="medical",
            date=date(2022, 1, 15),
            bucket="medical",
            category="treatment",
            amount="20.00",
            source_document_subtype="MEDICAL_BILL",
        ),
        PaidCostInput(
            id="future",
            date=date(2022, 4, 1),
            bucket="medical",
            category="treatment",
            amount="999.00",
            source_document_subtype="MEDICAL_BILL",
        ),
    )
    ledger = paid_cost_ledger(inputs)
    assert tuple(item.id for item in ledger) == (
        "indemnity",
        "medical",
        "expense",
        "future",
    )
    paid = paid_to_date(
        inputs,
        snapshot_date=date(2022, 3, 1),
        w1_indemnity_payments=(
            (date(2022, 1, 10), "100.00"),
            (date(2022, 3, 10), "500.00"),
        ),
    )
    assert paid.indemnity == Decimal("110.00")
    assert paid.medical == Decimal("20.00")
    assert paid.expense_alae == Decimal("30.00")
    assert paid.total == Decimal("160.00")

    duplicate_w1 = PaidCostInput(
        id="authored-td",
        date=date(2022, 1, 1),
        bucket="indemnity",
        category="td",
        amount="1.00",
        source_document_subtype="BENEFIT_PAYMENT_LEDGER",
    )
    with pytest.raises(
        ValueError,
        match=DEFENSE_DUPLICATE_W1_PAID_COST,
    ):
        paid_to_date((duplicate_w1,), snapshot_date=date(2022, 3, 1))
    with pytest.raises(ValidationError, match=DEFENSE_DUPLICATE_W1_PAID_COST):
        DefenseLensScenario(
            case_evaluation="literal",
            assumptions=(),
            discovery_plan=(),
            litigation_budget="1.00",
            exposure_events=(_exposure(),),
            paid_costs=(duplicate_w1,),
        )


def test_bucket_arithmetic_preserves_literal_components() -> None:
    """m23-17: no total-only representation may erase bucket identity."""
    left = _amounts("10.10", "20.20", "30.30")
    right = _amounts("1.01", "2.02", "3.03")

    added = left + right
    assert added.indemnity == Decimal("11.11")
    assert added.medical == Decimal("22.22")
    assert added.expense_alae == Decimal("33.33")
    assert added.total == Decimal("66.66")

    floored = right.subtract_floored(_amounts("2.00", "1.00", "4.00"))
    assert floored.indemnity == Decimal("0.00")
    assert floored.medical == Decimal("1.02")
    assert floored.expense_alae == Decimal("0.00")
    assert floored.total == Decimal("1.02")


def test_recommended_snapshot_incurred_includes_paid() -> None:
    """m23-18: incurred is paid plus recommended outstanding per bucket."""
    paid = _amounts("125.25", "50.10", "25.00")
    expected = _amounts("500.50", "300.30", "200.20")

    try:
        snapshot = recommended_reserve_snapshot(
            paid=paid,
            expected_ultimate=expected,
        )
    except ValidationError as exc:
        raise AssertionError(
            f"recommended snapshot must satisfy its own model: {exc}"
        ) from exc
    assert snapshot.paid.indemnity == Decimal("125.25")
    assert snapshot.paid.medical == Decimal("50.10")
    assert snapshot.paid.expense_alae == Decimal("25.00")
    assert snapshot.paid.total == Decimal("200.35")
    assert snapshot.outstanding_reserve.indemnity == Decimal("375.25")
    assert snapshot.outstanding_reserve.medical == Decimal("250.20")
    assert snapshot.outstanding_reserve.expense_alae == Decimal("175.20")
    assert snapshot.outstanding_reserve.total == Decimal("800.65")
    assert snapshot.incurred.indemnity == Decimal("500.50")
    assert snapshot.incurred.medical == Decimal("300.30")
    assert snapshot.incurred.expense_alae == Decimal("200.20")
    assert snapshot.incurred.total == Decimal("1001.00")


def test_exposure_one_cent_below_paid_fails_before_flooring() -> None:
    """m23-32: max(..., 0) cannot launder a below-paid ultimate."""
    paid = _amounts("100.00", "50.00", "25.00")
    equal = ExposureProjection(
        trigger="initial_file_review",
        effective_date=date(2022, 1, 1),
        low=paid,
        expected=paid,
        high=paid,
        assumptions=("literal boundary",),
    )
    validate_exposure_against_paid(equal, paid)
    snapshot = recommended_reserve_snapshot(paid=paid, expected_ultimate=paid)
    assert snapshot.outstanding_reserve == _amounts("0.00", "0.00", "0.00")
    assert snapshot.incurred == paid

    one_cent_low = _amounts("99.99", "50.00", "25.00")
    one_cent_expected = _amounts("99.99", "50.00", "25.00")
    one_cent_high = _amounts("99.99", "50.00", "25.00")
    boundaries = (
        (one_cent_low, paid, paid),
        (one_cent_low, one_cent_expected, paid),
        (one_cent_low, one_cent_expected, one_cent_high),
    )
    for low, expected, high in boundaries:
        exposure = ExposureProjection(
            trigger="initial_file_review",
            effective_date=date(2022, 1, 1),
            low=low,
            expected=expected,
            high=high,
            assumptions=(),
        )
        with pytest.raises(ValueError, match=DEFENSE_EXPOSURE_BELOW_PAID):
            validate_exposure_against_paid(exposure, paid)

    with pytest.raises(ValueError, match=DEFENSE_EXPOSURE_BELOW_PAID):
        recommended_reserve_snapshot(
            paid=paid,
            expected_ultimate=one_cent_expected,
        )


def test_projection_retains_authored_exposure_without_rng() -> None:
    """m23-48: projection dates exact authored amounts and performs no draw."""
    authored = _exposure(
        expected=_amounts("150.15", "80.08", "40.04"),
    )
    first = project_exposure(
        authored,
        effective_date=date(2022, 2, 2),
        case_assumptions=("A", "B", "A"),
        trigger_facts=("B", "C"),
    )
    second = project_exposure(
        authored,
        effective_date=date(2022, 2, 2),
        case_assumptions=("A", "B", "A"),
        trigger_facts=("B", "C"),
    )
    assert first == second
    assert first.low == _amounts("100.00", "50.00", "25.00")
    assert first.expected == _amounts("150.15", "80.08", "40.04")
    assert first.high == _amounts("200.00", "110.00", "55.00")
    assert first.assumptions == ("A", "B", "C")


def test_defense_amounts_use_decimal_str_and_half_up() -> None:
    """m23-50: binary-float conversion cannot precede cent quantization."""
    amounts = BucketAmounts(
        indemnity=2.675,
        medical=0.005,
        expense_alae="1.004",
    )
    assert amounts.indemnity == Decimal("2.68")
    assert amounts.medical == Decimal("0.01")
    assert amounts.expense_alae == Decimal("1.00")
    assert amounts.total == Decimal("3.69")


def _dated_projection(
    trigger: str,
    when: date,
    *,
    indemnity: str,
    medical: str = "0.00",
    expense: str = "0.00",
) -> ExposureProjection:
    amounts = _amounts(indemnity, medical, expense)
    return ExposureProjection(
        trigger=trigger,
        effective_date=when,
        low=amounts,
        expected=amounts,
        high=amounts,
        assumptions=("fixed authored exposure",),
    )


def test_booking_policy_is_pure_over_fixed_exposure_and_paid_inputs() -> None:
    """m23-19: diligence changes bookings, never exposure or recommendation."""
    exposures = (
        _dated_projection(
            "initial_file_review",
            date(2022, 1, 1),
            indemnity="10000.00",
            medical="5000.00",
            expense="1000.00",
        ),
        _dated_projection(
            "compensability_decision",
            date(2022, 1, 11),
            indemnity="20000.00",
            medical="10000.00",
            expense="2000.00",
        ),
        _dated_projection(
            "mmi",
            date(2022, 2, 1),
            indemnity="21000.00",
            medical="10500.00",
            expense="2100.00",
        ),
    )
    ledger = (
        PaidCost(
            id="medical-1",
            date=date(2022, 1, 5),
            bucket="medical",
            category="treatment",
            amount="100.00",
            source_document_subtype="MEDICAL_BILL",
        ),
    )
    attentive = apply_booking_policy(exposures, ledger, "attentive")
    ordinary = apply_booking_policy(exposures, ledger, "ordinary")
    negligent = apply_booking_policy(exposures, ledger, "negligent")

    for series in (ordinary, negligent):
        assert tuple(item.exposure for item in series) == exposures
        assert tuple(item.recommendation for item in series) == tuple(
            item.recommendation for item in attentive
        )
        assert tuple(item.recommendation.paid for item in series) == (
            _amounts("0.00", "0.00", "0.00"),
            _amounts("0.00", "100.00", "0.00"),
            _amounts("0.00", "100.00", "0.00"),
        )
    assert attentive[1].booked_snapshot.outstanding_reserve == _amounts(
        "20000.00", "9900.00", "2000.00"
    )
    assert ordinary[0].booked_snapshot.outstanding_reserve == _amounts(
        "7500.00", "3750.00", "750.00"
    )
    assert ordinary[1].booked_snapshot.outstanding_reserve == _amounts(
        "20000.00", "9900.00", "2000.00"
    )
    assert ordinary[2].booked_snapshot.outstanding_reserve == _amounts(
        "20000.00", "9900.00", "2000.00"
    )
    assert negligent[0].booked_snapshot.outstanding_reserve == _amounts(
        "4000.00", "2000.00", "400.00"
    )


def test_negligent_policy_under_reserves_and_detects_stair_stepping() -> None:
    """m23-20: negligent policy cannot silently adopt the full recommendation."""
    exposures = (
        _dated_projection(
            "initial_file_review", date(2022, 1, 1), indemnity="30000.00"
        ),
        _dated_projection(
            "compensability_decision", date(2022, 1, 11), indemnity="60000.00"
        ),
        _dated_projection("mmi", date(2022, 2, 1), indemnity="70000.00"),
        _dated_projection("formal_rating", date(2022, 3, 2), indemnity="80000.00"),
    )
    decisions = apply_booking_policy(exposures, (), "negligent")
    assert tuple(
        item.booked_snapshot.outstanding_reserve.indemnity for item in decisions
    ) == (
        Decimal("12000.00"),
        Decimal("24000.00"),
        Decimal("35500.00"),
        Decimal("46625.00"),
    )
    assert decisions[-1].recommendation.outstanding_reserve.indemnity == Decimal(
        "80000.00"
    )
    assert reserve_adequacy(decisions) == "under_reserved"
    assert is_stair_stepping(decisions) is True
    assert is_stair_stepping(apply_booking_policy(exposures, (), "attentive")) is False


def test_adoption_lag_tracks_bucket_first_uninterrupted_shortfall() -> None:
    """m23-39: event lag is the maximum literal per-bucket shortfall age."""
    exposures = (
        _dated_projection(
            "initial_file_review",
            date(2022, 1, 1),
            indemnity="10000.00",
            medical="5000.00",
            expense="1000.00",
        ),
        _dated_projection(
            "compensability_decision",
            date(2022, 1, 11),
            indemnity="12000.00",
            medical="6000.00",
            expense="1000.00",
        ),
        _dated_projection(
            "mmi",
            date(2022, 2, 1),
            indemnity="14000.00",
            medical="7000.00",
            expense="1200.00",
        ),
    )
    decisions = apply_booking_policy(exposures, (), "negligent")
    assert tuple(item.adoption_lag_days for item in decisions) == (0, 10, 31)


def _three_event_defense() -> DefenseLensFacts:
    def event(trigger: str, indemnity: str, medical: str, expense: str) -> ExposureInput:
        amounts = _amounts(indemnity, medical, expense)
        return ExposureInput(
            trigger=trigger,
            low=amounts,
            expected=amounts,
            high=amounts,
        )

    scenario = DefenseLensScenario(
        case_evaluation="Three fixed reserve decisions.",
        assumptions=("No unrecorded paid costs.",),
        discovery_plan=("Obtain treatment ledger.",),
        litigation_budget="9000.00",
        exposure_events=(
            event("initial_file_review", "10000.00", "5000.00", "1000.00"),
            event("compensability_decision", "20000.00", "6000.00", "2000.00"),
            event("mmi", "30000.00", "7000.00", "3000.00"),
        ),
    )
    timeline = SimpleNamespace(
        claim_filed_date=date(2022, 1, 1),
        horizon=date(2023, 1, 1),
    )
    lifecycle = SimpleNamespace(
        claim_response="accepted",
        eval_type="qme",
        target_stage="resolved",
        reconsideration=SimpleNamespace(enabled=False),
    )
    facts = SimpleNamespace(
        surgery=SimpleNamespace(cpt_code=None, body_part=None),
        mmi_date=date(2022, 2, 1),
        rating=None,
    )
    claim = SimpleNamespace(
        subtype="CLAIM_ACCEPTANCE_LETTER",
        doc_date=date(2022, 1, 11),
        semantic_event_id="claim-response:accepted",
        medical_opinion_id=None,
    )
    paid = (
        PaidCost(
            id="medical-1",
            date=date(2022, 1, 5),
            bucket="medical",
            category="treatment",
            amount="100.00",
            source_document_subtype="MEDICAL_BILL",
        ),
    )
    state = build_unbound_defense(
        scenario,
        timeline=timeline,
        lifecycle=lifecycle,
        case_facts=facts,
        candidates=(claim,),
        paid_costs=paid,
        diligence="ordinary",
    )
    documents = (
        SimpleNamespace(
            index=0,
            subtype="RESERVE_WORKSHEET",
            doc_date=date(2022, 1, 1),
            semantic_event_id="reserve:initial_file_review",
        ),
        SimpleNamespace(
            index=1,
            subtype="RESERVE_CHANGE_NOTICE",
            doc_date=date(2022, 1, 11),
            semantic_event_id="reserve:compensability_decision",
        ),
        SimpleNamespace(
            index=2,
            subtype="RESERVE_CHANGE_NOTICE",
            doc_date=date(2022, 2, 1),
            semantic_event_id="reserve:mmi",
        ),
    )
    bindings = bind_defense_artifacts(state, documents=documents)
    defense = bind_defense_facts(state, bindings, claim_response="accepted")
    return defense


def test_three_event_ledger_materializes_literal_snapshots_and_bindings() -> None:
    defense = _three_event_defense()

    assert defense.initial_file_review.exposure is defense.exposure_events[0]
    assert tuple(event.exposure for event in defense.reserve_events) == (
        defense.exposure_events[1],
        defense.exposure_events[2],
    )
    assert all(
        event.exposure is exposure
        for event, exposure in zip(
            defense.reserve_events,
            defense.exposure_events[1:],
            strict=True,
        )
    )
    assert defense.scorer_labels == DefenseScorerLabels(
        stair_stepping=False,
        reserve_adequacy="adequate",
    )
    assert defense.initial_file_review.booked_snapshot.outstanding_reserve == _amounts(
        "7500.00", "3750.00", "750.00"
    )
    assert len(defense.reserve_events) == 2
    first, second = defense.reserve_events
    assert first.recommendation.paid == _amounts("0.00", "100.00", "0.00")
    assert first.recommendation.outstanding_reserve == _amounts(
        "20000.00", "5900.00", "2000.00"
    )
    assert first.booked_snapshot.incurred == _amounts(
        "20000.00", "6000.00", "2000.00"
    )
    assert first.prior_snapshot == defense.initial_file_review.booked_snapshot
    assert first.artifact_binding == ReserveArtifactBinding(
        event_id="reserve:compensability_decision",
        document_index=1,
        subtype="RESERVE_CHANGE_NOTICE",
        document_date=date(2022, 1, 11),
    )
    assert second.prior_snapshot == first.booked_snapshot
    assert second.recommendation.outstanding_reserve == _amounts(
        "30000.00", "6900.00", "3000.00"
    )
    assert second.booked_snapshot.incurred.total == Decimal("40000.00")


def test_r79_accounting_and_artifact_binding_codes_are_decisive() -> None:
    defense = _three_event_defense()
    snapshot = defense.initial_file_review.recommendation
    with pytest.raises(ValidationError, match=DEFENSE_ACCOUNTING_EQUATION_BROKEN):
        ReserveSnapshot(
            paid=snapshot.paid,
            outstanding_reserve=snapshot.outstanding_reserve,
            incurred=_amounts("0.01", "0.00", "0.00"),
        )

    review = defense.initial_file_review
    review_data = review.model_dump()
    review_data.pop("artifact_binding")
    with pytest.raises(ValidationError, match=DEFENSE_ARTIFACT_BINDING_MISSING):
        InitialFileReview.model_validate(review_data)

    review_data["artifact_binding"] = review.artifact_binding.model_copy(
        update={"event_id": "reserve:wrong"}
    )
    with pytest.raises(ValidationError, match=DEFENSE_ARTIFACT_BINDING_MISMATCH):
        InitialFileReview.model_validate(review_data)


def test_reserve_adequacy_has_three_exact_states() -> None:
    base = _dated_projection(
        "initial_file_review", date(2022, 1, 1), indemnity="10000.00"
    )
    lower = _dated_projection(
        "compensability_decision", date(2022, 1, 2), indemnity="7000.00"
    )
    adequate = apply_booking_policy((base,), (), "attentive")
    under = apply_booking_policy((base,), (), "negligent")
    over = apply_booking_policy((base, lower), (), "ordinary")
    assert reserve_adequacy(adequate) == "adequate"
    assert reserve_adequacy(under) == "under_reserved"
    assert reserve_adequacy(over) == "over_reserved"


def _trigger_inputs() -> tuple[ExposureInput, ...]:
    return tuple(_exposure(trigger) for trigger in EXPECTED_TRIGGERS)


def _all_trigger_context() -> tuple[Any, Any, Any, tuple[Any, ...], tuple[Any, ...], Any]:
    timeline = SimpleNamespace(
        claim_filed_date=date(2022, 1, 1),
        horizon=date(2023, 1, 1),
    )
    lifecycle = SimpleNamespace(
        claim_response="accepted",
        eval_type="qme",
        target_stage="post_recon",
        reconsideration=SimpleNamespace(enabled=True),
    )
    facts = SimpleNamespace(
        surgery=SimpleNamespace(cpt_code="63030", body_part="lumbar_spine"),
        mmi_date=date(2022, 3, 1),
        rating=object(),
    )
    aoe = SimpleNamespace(
        id="opinion-aoe",
        author_role="ptp",
        report_stage="final",
        report_date=date(2022, 1, 20),
        aoe_coe_finding="industrial",
    )
    qme = SimpleNamespace(
        id="opinion-qme",
        author_role="qme",
        report_stage="final",
        report_date=date(2022, 4, 1),
        aoe_coe_finding=None,
    )
    candidates = (
        SimpleNamespace(
            subtype="CLAIM_ACCEPTANCE_LETTER",
            doc_date=date(2022, 1, 10),
            semantic_event_id="claim-response:accepted",
            medical_opinion_id=None,
        ),
        SimpleNamespace(
            subtype="TREATING_PHYSICIAN_REPORT_FINAL",
            doc_date=aoe.report_date,
            semantic_event_id="medical-opinion:opinion-aoe",
            medical_opinion_id="opinion-aoe",
        ),
        SimpleNamespace(
            subtype="MEDICAL_TREATMENT_AUTHORIZATION",
            doc_date=date(2022, 2, 1),
            semantic_event_id="surgery-authorization:63030",
            medical_opinion_id=None,
        ),
        SimpleNamespace(
            subtype="QME_COMPREHENSIVE_REPORT",
            doc_date=qme.report_date,
            semantic_event_id="medical-opinion:opinion-qme",
            medical_opinion_id="opinion-qme",
        ),
        SimpleNamespace(
            subtype="PD_RATING_CALCULATION_WORKSHEET",
            doc_date=date(2022, 5, 1),
            semantic_event_id="rating:formal",
            medical_opinion_id=None,
        ),
        SimpleNamespace(
            subtype="NOTICE_OF_TRIAL",
            doc_date=date(2022, 6, 1),
            semantic_event_id="trial-setting:2022-06-01",
            medical_opinion_id=None,
        ),
        SimpleNamespace(
            subtype="PETITION_RECONSIDERATION_FILED",
            doc_date=date(2022, 7, 1),
            semantic_event_id="recon:petition",
            medical_opinion_id=None,
        ),
    )
    recon = SimpleNamespace(petition_date=date(2022, 7, 1))
    return timeline, lifecycle, facts, candidates, (aoe, qme), recon


def test_all_nine_triggers_resolve_from_literal_semantic_date_map() -> None:
    """m23-36: absent semantic sources reject; dates never use a fallback."""
    timeline, lifecycle, facts, candidates, opinions, recon = _all_trigger_context()
    occurrences = resolve_trigger_occurrences(
        _trigger_inputs(),
        timeline=timeline,
        lifecycle=lifecycle,
        case_facts=facts,
        candidates=candidates,
        opinions=opinions,
        recon=recon,
    )
    assert {item.trigger: item.effective_date for item in occurrences} == {
        "initial_file_review": date(2022, 1, 1),
        "compensability_decision": date(2022, 1, 10),
        "aoe_coe_outcome": date(2022, 1, 20),
        "surgery_authorized": date(2022, 2, 1),
        "mmi": date(2022, 3, 1),
        "qme_ame_wpi": date(2022, 4, 1),
        "formal_rating": date(2022, 5, 1),
        "trial_setting": date(2022, 6, 1),
        "petition_for_reconsideration": date(2022, 7, 1),
    }
    assert {item.trigger: item.semantic_event_id for item in occurrences} == {
        "initial_file_review": "timeline:claim_filed",
        "compensability_decision": "claim-response:accepted",
        "aoe_coe_outcome": "medical-opinion:opinion-aoe",
        "surgery_authorized": "surgery-authorization:63030",
        "mmi": "case-facts:mmi",
        "qme_ame_wpi": "medical-opinion:opinion-qme",
        "formal_rating": "rating:formal",
        "trial_setting": "trial-setting:2022-06-01",
        "petition_for_reconsideration": "recon:petition",
    }
    no_claim_response = tuple(
        item for item in candidates if item.subtype != "CLAIM_ACCEPTANCE_LETTER"
    )
    with pytest.raises(ValueError, match=DEFENSE_INELIGIBLE_RESERVE_TRIGGER):
        resolve_trigger_occurrences(
            (_exposure(), _exposure("compensability_decision")),
            timeline=timeline,
            lifecycle=lifecycle,
            case_facts=facts,
            candidates=no_claim_response,
            opinions=opinions,
            recon=recon,
        )


def test_aoe_coe_requires_a_final_opinion_not_claim_response() -> None:
    """m23-37: identical claim responses differ only by eligible opinion."""
    timeline, lifecycle, facts, candidates, opinions, recon = _all_trigger_context()
    inputs = (_exposure(), _exposure("aoe_coe_outcome"))
    without_opinion = tuple(
        item for item in candidates if item.medical_opinion_id != "opinion-aoe"
    )
    with pytest.raises(ValueError, match=DEFENSE_INELIGIBLE_RESERVE_TRIGGER):
        resolve_trigger_occurrences(
            inputs,
            timeline=timeline,
            lifecycle=lifecycle,
            case_facts=facts,
            candidates=without_opinion,
            opinions=opinions,
            recon=recon,
        )
    resolved = resolve_trigger_occurrences(
        inputs,
        timeline=timeline,
        lifecycle=lifecycle,
        case_facts=facts,
        candidates=candidates,
        opinions=opinions,
        recon=recon,
    )
    assert resolved[1].effective_date == date(2022, 1, 20)
    assert resolved[1].source_record_id == "opinion-aoe"


def test_opinion_bound_carrier_date_cannot_be_fit_moved() -> None:
    """m23-49: opinion-bound carriers remain on exact report dates."""
    timeline, lifecycle, facts, candidates, opinions, recon = _all_trigger_context()
    moved = tuple(
        SimpleNamespace(**{**item.__dict__, "doc_date": date(2022, 1, 21)})
        if item.medical_opinion_id == "opinion-aoe"
        else item
        for item in candidates
    )
    with pytest.raises(ValueError, match=DEFENSE_TRIGGER_SOURCE_DATE_MISMATCH):
        resolve_trigger_occurrences(
            (_exposure(), _exposure("aoe_coe_outcome")),
            timeline=timeline,
            lifecycle=lifecycle,
            case_facts=facts,
            candidates=moved,
            opinions=opinions,
            recon=recon,
        )


def test_planner_runs_literal_ten_stage_defense_pipeline() -> None:
    """m23-40: defense construction follows M4 candidate semantics."""
    trace: list[str] = []
    plan = build_case_plan(parse_case_seed(_seed()), _phase_trace=trace)
    assert DEFENSE_PLANNER_STAGES == (
        "cast",
        "case_facts_rating",
        "early_w1",
        "lifecycle_m4_rating_recon_candidates",
        "unbound_defense",
        "reserve_candidates",
        "controls",
        "bindings",
        "final_money_facts",
        "render",
    )
    assert tuple(trace) == DEFENSE_PLANNER_STAGES
    assert plan.money_facts is not None
    assert plan.money_facts.defense is not None
    assert plan.money_facts.defense.initial_file_review.review_date == (
        plan.timeline.claim_filed_date
    )
    assert plan.money_facts.defense.initial_file_review.artifact_binding.subtype == (
        "RESERVE_WORKSHEET"
    )
    assert sum(
        document.subtype == "RESERVE_WORKSHEET" for document in plan.documents
    ) == 1


def test_controls_cannot_remove_required_ifr_artifact() -> None:
    raw = _seed()
    raw["documents"] = {"exclude": ["RESERVE_WORKSHEET"]}
    with pytest.raises(ValueError, match=DEFENSE_REQUIRED_CARRIER_REMOVED):
        build_case_plan(parse_case_seed(raw))


def test_controls_cannot_remove_or_reconstruct_a_trigger_source() -> None:
    occurrence = TriggerOccurrence(
        trigger="formal_rating",
        semantic_event_id="rating:formal",
        effective_date=date(2022, 5, 1),
        source_kind="rating",
        source_record_id="rating:formal",
        requires_planned_document=True,
    )
    source_subtypes = {
        "rating:formal": ("PD_RATING_CALCULATION_WORKSHEET",),
    }
    with pytest.raises(ValueError, match=DEFENSE_TRIGGER_SOURCE_REMOVED):
        validate_required_trigger_sources(
            (occurrence,),
            (),
            source_subtypes=source_subtypes,
        )
    reconstructed = SimpleNamespace(
        subtype="PD_RATING_CALCULATION_WORKSHEET",
        semantic_event_id=None,
        medical_opinion_id=None,
        doc_date=date(2022, 5, 1),
    )
    with pytest.raises(ValueError, match=DEFENSE_TRIGGER_OCCURRENCE_ID_MISSING):
        validate_required_trigger_sources(
            (occurrence,),
            (reconstructed,),
            source_subtypes=source_subtypes,
        )


def test_duplicate_initial_review_cannot_enter_reserve_events() -> None:
    """m23-41: the IFR exists once, in its sole R72 model."""
    defense = _three_event_defense()
    first = defense.reserve_events[0]
    duplicate = first.model_copy(
        update={
            "id": "reserve:initial_file_review",
            "trigger": "initial_file_review",
            "event_date": defense.initial_file_review.review_date,
            "prior_snapshot": defense.initial_file_review.booked_snapshot,
            "exposure": defense.exposure_events[0],
            "artifact_binding": None,
        }
    )
    with pytest.raises(
        ValidationError,
        match=DEFENSE_DUPLICATE_INITIAL_REVIEW_EVENT,
    ):
        DefenseLensFacts(
            exposure_events=defense.exposure_events,
            paid_costs=defense.paid_costs,
            initial_file_review=defense.initial_file_review,
            reserve_events=(duplicate, *defense.reserve_events),
            scorer_labels=defense.scorer_labels,
        )


def test_reserve_event_artifact_bijection_is_literal() -> None:
    """m23-23: every final reserve document resolves to its sole event."""
    defense = _three_event_defense()
    expected = {
        0: ("RESERVE_WORKSHEET", "reserve:initial_file_review"),
        1: ("RESERVE_CHANGE_NOTICE", "reserve:compensability_decision"),
        2: ("RESERVE_CHANGE_NOTICE", "reserve:mmi"),
    }
    actual = {
        defense.initial_file_review.artifact_binding.document_index: (
            defense.initial_file_review.artifact_binding.subtype,
            defense.initial_file_review.event_id,
        ),
        **{
            event.artifact_binding.document_index: (
                event.artifact_binding.subtype,
                event.id,
            )
            for event in defense.reserve_events
            if event.artifact_binding is not None
        },
    }
    assert actual == expected
    assert all(event.trigger != "initial_file_review" for event in defense.reserve_events)
    assert (
        reserve_event_for_document(
            defense,
            document_index=2,
            subtype="RESERVE_CHANGE_NOTICE",
        )
        is defense.reserve_events[1]
    )


def _no_change_defense() -> tuple[Any, DefenseLensFacts]:
    amount = _amounts("10000.00", "5000.00", "1000.00")
    scenario = DefenseLensScenario(
        case_evaluation="No exposure change.",
        assumptions=("No new information.",),
        discovery_plan=("Continue records collection.",),
        litigation_budget="1000.00",
        exposure_events=(
            ExposureInput(
                trigger="initial_file_review",
                low=amount,
                expected=amount,
                high=amount,
            ),
            ExposureInput(
                trigger="compensability_decision",
                low=amount,
                expected=amount,
                high=amount,
            ),
        ),
    )
    timeline = SimpleNamespace(
        claim_filed_date=date(2022, 1, 1),
        horizon=date(2023, 1, 1),
    )
    lifecycle = SimpleNamespace(
        claim_response="accepted",
        eval_type="qme",
        target_stage="resolved",
        reconsideration=SimpleNamespace(enabled=False),
    )
    facts = SimpleNamespace(
        surgery=SimpleNamespace(cpt_code=None, body_part=None),
        mmi_date=None,
        rating=None,
    )
    claim = SimpleNamespace(
        subtype="CLAIM_ACCEPTANCE_LETTER",
        doc_date=date(2022, 1, 11),
        semantic_event_id="claim-response:accepted",
        medical_opinion_id=None,
    )
    state = build_unbound_defense(
        scenario,
        timeline=timeline,
        lifecycle=lifecycle,
        case_facts=facts,
        candidates=(claim,),
        paid_costs=(),
        diligence="attentive",
    )
    documents = (
        SimpleNamespace(
            index=0,
            subtype="RESERVE_WORKSHEET",
            doc_date=date(2022, 1, 1),
            semantic_event_id="reserve:initial_file_review",
        ),
    )
    bindings = bind_defense_artifacts(state, documents=documents)
    return state, bind_defense_facts(state, bindings, claim_response="accepted")


def test_no_change_event_has_no_notice_and_forced_notice_is_unbound() -> None:
    state, defense = _no_change_defense()
    assert len(defense.reserve_events) == 1
    assert defense.reserve_events[0].artifact_binding is None
    assert state.decisions[1].requires_notice is False

    forced = (
        SimpleNamespace(
            subtype="RESERVE_WORKSHEET",
            doc_date=date(2022, 1, 1),
            semantic_event_id="reserve:initial_file_review",
        ),
        SimpleNamespace(
            subtype="RESERVE_CHANGE_NOTICE",
            doc_date=date(2022, 1, 11),
            semantic_event_id="reserve:compensability_decision",
        ),
    )
    with pytest.raises(ValueError, match=DEFENSE_UNBOUND_RESERVE_NOTICE):
        validate_reserve_artifact_candidates(state, forced)


def test_required_source_copy_identity_survives_and_last_removal_fails() -> None:
    occurrence = TriggerOccurrence(
        trigger="formal_rating",
        semantic_event_id="rating:formal",
        effective_date=date(2022, 5, 1),
        source_kind="rating",
        source_record_id="rating:formal",
        requires_planned_document=True,
    )
    source = DatedCandidate(
        subtype="PD_RATING_CALCULATION_WORKSHEET",
        doc_date=date(2022, 5, 1),
        semantic_event_id="rating:formal",
    )
    copied = replace(source)
    assert copied.semantic_event_id == source.semantic_event_id == "rating:formal"
    validate_required_trigger_sources((occurrence,), (source, copied))
    validate_required_trigger_sources((occurrence,), (copied,))
    with pytest.raises(ValueError, match=DEFENSE_TRIGGER_SOURCE_REMOVED):
        validate_required_trigger_sources((occurrence,), ())


def test_planner_preserves_semantic_identity_and_rejects_last_source_removal() -> None:
    """m23-42/m23-43: controls cannot erase or regenerate semantic identity."""
    raw = _seed_with_compensability()
    plan = build_case_plan(parse_case_seed(raw))
    claim_sources = tuple(
        document
        for document in plan.documents
        if document.semantic_event_id == "claim-response:accepted"
    )
    assert len(claim_sources) >= 1
    assert all(
        document.semantic_event_id == "claim-response:accepted"
        for document in claim_sources
    )

    raw["documents"] = {"exclude": ["CLAIM_ACCEPTANCE_LETTER"]}
    with pytest.raises(ValueError, match=DEFENSE_TRIGGER_SOURCE_REMOVED):
        build_case_plan(parse_case_seed(raw))


def test_planner_reserve_carriers_have_exact_titles_and_bijection() -> None:
    """m23-46: controls cannot fabricate an unbound reserve notice."""
    try:
        plan = build_case_plan(parse_case_seed(_seed_with_compensability()))
    except ValueError as exc:
        pytest.fail(f"valid reserve carrier plan rejected: {exc}")
    defense = plan.money_facts.defense
    assert defense is not None
    worksheets = tuple(
        document for document in plan.documents if document.subtype == "RESERVE_WORKSHEET"
    )
    notices = tuple(
        document
        for document in plan.documents
        if document.subtype == "RESERVE_CHANGE_NOTICE"
    )
    assert len(worksheets) == 1
    assert worksheets[0].title == "Initial File Review"
    assert defense.initial_file_review.artifact_binding == ReserveArtifactBinding(
        event_id="reserve:initial_file_review",
        document_index=worksheets[0].index,
        subtype="RESERVE_WORKSHEET",
        document_date=worksheets[0].doc_date,
    )
    changed_events = tuple(
        event for event in defense.reserve_events if event.artifact_binding is not None
    )
    assert len(notices) == len(changed_events) == 1
    assert notices[0].semantic_event_id == changed_events[0].id
    assert notices[0].index == changed_events[0].artifact_binding.document_index


def _paper_section(text: str, heading: str, next_heading: str) -> str:
    assert heading in text
    section = text.split(heading, 1)[1]
    assert next_heading in section
    return section.split(next_heading, 1)[0]


def _assert_paper_money_matrix(
    section: str,
    expected_counts: dict[str, int],
) -> None:
    for bucket in ("Indemnity", "Medical", "Expense / ALAE", "Total"):
        assert bucket in section
    for literal, count in expected_counts.items():
        assert section.count(literal) == count


@requires_substrate
def test_reserve_renderers_follow_bound_literal_figures(tmp_path: Any) -> None:
    """m23-22: paper figures follow the bound object, including a one-cent edit."""
    registry = fact_aware_templates()
    assert registry["RESERVE_WORKSHEET"].__name__ == "FactAwareInitialFileReview"
    assert registry["RESERVE_CHANGE_NOTICE"].__name__ == (
        "FactAwareReserveChangeNotice"
    )

    seed = parse_case_seed(_seed())
    plan = build_case_plan(seed)
    defense = _three_event_defense()
    ifr_result = render_document(
        seed=seed,
        cast=plan.cast,
        subtype="RESERVE_WORKSHEET",
        doc_date=defense.initial_file_review.review_date,
        doc_format="pdf",
        index=0,
        out_path=tmp_path / "ifr.pdf",
        title="Initial File Review",
        reserve_event=defense.initial_file_review,
    )
    ifr_text = extract_text(ifr_result.path, ifr_result.doc_format)
    for literal in (
        "Initial File Review",
        "Indemnity",
        "Medical",
        "Expense / ALAE",
        "Ultimate Exposure Range",
        "$10,000.00",
        "$5,000.00",
        "$1,000.00",
        "$7,500.00",
        "$3,750.00",
        "$750.00",
        "$16,000.00",
        "$12,000.00",
        "Three fixed reserve decisions.",
        "$9,000.00",
        "Obtain treatment ledger.",
        "No unrecorded paid costs.",
        "Adoption Lag: 0 days",
    ):
        assert literal in ifr_text
    assert "Independent Bill Review" not in ifr_text
    _assert_paper_money_matrix(
        _paper_section(ifr_text, "Ultimate Exposure Range", "Recommended Snapshot"),
        {
            "$10,000.00": 3,
            "$5,000.00": 3,
            "$1,000.00": 3,
            "$16,000.00": 3,
        },
    )
    _assert_paper_money_matrix(
        _paper_section(ifr_text, "Recommended Snapshot", "Booked Snapshot"),
        {
            "$0.00": 4,
            "$10,000.00": 2,
            "$5,000.00": 2,
            "$1,000.00": 2,
            "$16,000.00": 2,
        },
    )
    _assert_paper_money_matrix(
        _paper_section(ifr_text, "Booked Snapshot", "Discovery Plan"),
        {
            "$0.00": 4,
            "$7,500.00": 2,
            "$3,750.00": 2,
            "$750.00": 2,
            "$12,000.00": 2,
        },
    )

    event = defense.reserve_events[0]
    notice_result = render_document(
        seed=seed,
        cast=plan.cast,
        subtype="RESERVE_CHANGE_NOTICE",
        doc_date=event.event_date,
        doc_format="pdf",
        index=1,
        out_path=tmp_path / "notice.pdf",
        reserve_event=event,
    )
    notice_text = extract_text(notice_result.path, notice_result.doc_format)
    for literal in (
        "Reserve Change Notice",
        "compensability_decision",
        "Prior Booked Snapshot",
        "Recommended Snapshot",
        "New Booked Snapshot",
        "$20,000.00",
        "$5,900.00",
        "$2,000.00",
        "$100.00",
        "$27,900.00",
        "$28,000.00",
    ):
        assert literal in notice_text
    _assert_paper_money_matrix(
        _paper_section(
            notice_text,
            "Ultimate Exposure Range",
            "Prior Booked Snapshot",
        ),
        {
            "$20,000.00": 3,
            "$6,000.00": 3,
            "$2,000.00": 3,
            "$28,000.00": 3,
        },
    )
    _assert_paper_money_matrix(
        _paper_section(
            notice_text,
            "Prior Booked Snapshot",
            "Recommended Snapshot",
        ),
        {
            "$0.00": 4,
            "$7,500.00": 2,
            "$3,750.00": 2,
            "$750.00": 2,
            "$12,000.00": 2,
        },
    )
    _assert_paper_money_matrix(
        _paper_section(
            notice_text,
            "Recommended Snapshot",
            "New Booked Snapshot",
        ),
        {
            "$0.00": 2,
            "$100.00": 2,
            "$20,000.00": 2,
            "$5,900.00": 1,
            "$6,000.00": 1,
            "$2,000.00": 2,
            "$27,900.00": 1,
            "$28,000.00": 1,
        },
    )
    _assert_paper_money_matrix(
        _paper_section(
            notice_text,
            "New Booked Snapshot",
            "Exposure Assumptions",
        ),
        {
            "$0.00": 2,
            "$100.00": 2,
            "$20,000.00": 2,
            "$5,900.00": 1,
            "$6,000.00": 1,
            "$2,000.00": 2,
            "$27,900.00": 1,
            "$28,000.00": 1,
        },
    )

    booked = event.booked_snapshot
    changed_outstanding = booked.outstanding_reserve.model_copy(
        update={"indemnity": Decimal("20000.01")}
    )
    changed_incurred = booked.incurred.model_copy(
        update={"indemnity": Decimal("20000.01")}
    )
    changed_snapshot = ReserveSnapshot(
        paid=booked.paid,
        outstanding_reserve=changed_outstanding,
        incurred=changed_incurred,
    )
    changed_event = event.model_copy(update={"booked_snapshot": changed_snapshot})
    changed_result = render_document(
        seed=seed,
        cast=plan.cast,
        subtype="RESERVE_CHANGE_NOTICE",
        doc_date=changed_event.event_date,
        doc_format="pdf",
        index=2,
        out_path=tmp_path / "notice-cent.pdf",
        reserve_event=changed_event,
    )
    changed_text = extract_text(changed_result.path, changed_result.doc_format)
    assert "$20,000.01" in changed_text

    ibr_raw = _seed()
    ibr_raw["documents"] = {
        "overrides": [{"subtype": "IBR_APPLICATION", "count": 1}]
    }
    ibr_seed = parse_case_seed(ibr_raw)
    ibr_plan = build_case_plan(ibr_seed)
    ibr_document = next(
        document
        for document in ibr_plan.documents
        if document.subtype == "IBR_APPLICATION"
    )
    ibr_result = render_document(
        seed=ibr_seed,
        cast=ibr_plan.cast,
        subtype=ibr_document.subtype,
        doc_date=ibr_document.doc_date,
        doc_format="pdf",
        index=ibr_document.index,
        out_path=tmp_path / "ibr-application.pdf",
        title=ibr_document.title,
        case_facts=ibr_plan.case_facts,
        money_facts=ibr_plan.money_facts,
    )
    ibr_text = extract_text(ibr_result.path, ibr_result.doc_format)
    assert "STATEMENT OF CHARGES" in ibr_text
    assert "Initial File Review" not in ibr_text
    assert "Outstanding Reserve" not in ibr_text
