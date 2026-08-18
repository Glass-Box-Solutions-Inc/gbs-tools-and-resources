"""AJC-48 truth-manifest contract and lossless money-channel coverage.

These tests build plans rather than documents wherever possible.  The truth
artifact labels decided facts, so rendering paper to prove serialization would
make the contract slower without making it stronger; only the output-tree
boundary test crosses the renderer.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import copy
import datetime as dt
import decimal
import json
import shutil
from dataclasses import replace
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from conftest import extract_text, requires_substrate
from wc_caseload_engine import truth_manifest as truth_manifest_module
from wc_caseload_engine.case_facts import (
    CASE_FACTS_MONEY_RATING_KEYS,
    CASE_FACTS_RATING_IMPAIRMENT_KEYS,
    CASE_FACTS_RATING_KEYS,
    CASE_FACTS_RATING_SCHEDULE_KEYS,
    facts_manifest_block,
)
from wc_caseload_engine.manifests import generate_case, generate_caseload, validate_output_tree
from wc_caseload_engine.medical_assertions import (
    assertion_context,
    grade_ledger,
    project_medical_history,
)
from wc_caseload_engine.money import MoneyFacts, money_manifest_block
from wc_caseload_engine.planner import build_case_plan
from wc_caseload_engine.rating import RatingFacts, RatingImpairment
from wc_caseload_engine.rating_sources import RatingScheduleBinding
from wc_caseload_engine.renderer import render_document
from wc_caseload_engine.seeds import parse_case_seed
from wc_caseload_engine.truth_manifest import (
    CASELOAD_TRUTH_NAME,
    CASELOAD_TRUTH_PROVENANCE_KEYS,
    MONEY_CHANNEL_V1_0_VERSION,
    MONEY_CHANNEL_V1_1_VERSION,
    MONEY_CHANNEL_V1_2_VERSION,
    MONEY_CHANNEL_VERSION,
    MONEY_DEFENSE_SCOPE_UNSUPPORTED,
    MONEY_V1_0_CASE_CHANNEL_KEYS,
    MONEY_V1_0_OPTIONAL_CASE_CHANNEL_KEYS,
    MONEY_V1_1_CASE_CHANNEL_KEYS,
    MONEY_V1_1_OPTIONAL_CASE_CHANNEL_KEYS,
    MONEY_V1_2_CASE_CHANNEL_KEYS,
    MONEY_V1_2_CASELOAD_CASE_KEYS,
    MONEY_V1_2_CASELOAD_CHANNEL_KEYS,
    MONEY_V1_2_OPTIONAL_CASE_CHANNEL_KEYS,
    MONEY_V1_2_PUBLISHED_GROUP_KEYS,
    MONEY_V1_2_RATING_IMPAIRMENT_KEYS,
    MONEY_V1_2_RATING_KEYS,
    MONEY_V1_2_RATING_SCHEDULE_KEYS,
    PENALTY_ASSESSMENT_KEY_NAMES,
    SCORER_ONLY_ENVELOPE_KEY_NAMES,
    SUPPORTED_MONEY_CHANNEL_VERSIONS,
    TRUTH_DIR,
    TRUTH_PROVENANCE_KEYS,
    TruthManifestError,
    build_case_truth_manifest,
    build_caseload_truth_manifest,
    check_truth_dir_is_isolated,
    money_facts_from_truth,
    rating_facts_from_truth,
    read_truth_manifest,
    write_case_truth_manifest,
    write_caseload_truth_manifest,
)

LEGITIMATE_SCORER_VOCABULARY_OVERLAPS: dict[str, str] = {
    # Keep this as a named ledger: every overlap must identify the public world-fact
    # surface that makes the word analyzer input rather than scorer-only metadata.
    "source": "PDF /Resources structure contains the substring but no assessment key",
    "datePaid": "public benefit entries expose the payment date printed on documents",
    "daysLate": "public benefit entries expose the lateness printed on documents",
    "amount": "public wage and benefit entries expose printed currency facts",
}

ENVELOPE_KEYS_THAT_ARE_NOT_SENTINELS: dict[str, str] = {
    # The completeness guard below forces every emitted envelope key to be
    # classified. These are structure the truth manifests emit whose *names*
    # also occur in analyzer-visible artifacts, so none of them can serve as a
    # leakage sentinel — sweeping for them would fire on the case tree by design
    # rather than on a leak.
    "kind": "caseFacts.money.settlement.kind publishes the same word to the analyzer",
    "caseId": "manifest.json names the case to the analyzer under this exact key",
    "caseloadId": "the caseload identifier is the corpus's public name",
    "provenance": "manifest.json carries its own provenance block for the analyzer",
    "cases": "the caseload index lists cases the analyzer can already enumerate",
}

EXPECTED_MONEY_VERSIONS = ("1.0.0", "1.1.0", "1.2.0")
EXPECTED_V1_0_CASE_KEYS = (
    "channelVersion",
    "wage",
    "benefits",
    "published",
    "settlement",
)
EXPECTED_V1_1_CASE_KEYS = (
    "channelVersion",
    "wage",
    "benefits",
    "published",
    "settlement",
    "penalties",
)
EXPECTED_V1_2_CASE_KEYS = (
    "channelVersion",
    "wage",
    "benefits",
    "published",
    "rating",
    "defense",
    "settlement",
    "penalties",
)
EXPECTED_RATING_KEYS = (
    "schedule",
    "dateOfInjury",
    "applicantAge",
    "occupationGroup",
    "occupationTitle",
    "impairments",
    "combinationMethod",
    "kiteImpairmentIds",
    "scheduledCombinedRating",
    "combinedRating",
    "finalPdPercent",
    "ratingString",
)
EXPECTED_RATING_IMPAIRMENT_KEYS = (
    "id",
    "bodyPart",
    "impairmentNumber",
    "description",
    "wpi",
    "adjustmentMethod",
    "fecRank",
    "adjustmentFactor",
    "scheduleAdjusted",
    "variant",
    "occupationAdjusted",
    "ageBand",
    "ageAdjusted",
    "ratingString",
)
EXPECTED_RATING_SCHEDULE_KEYS = (
    "edition",
    "sourceUrl",
    "pdfSha256",
    "extractedTextSha256",
    "tablesSha256",
    "section4Sha256",
    "section4MetaSha256",
    "counselStatus",
)
EXPECTED_V1_2_PUBLISHED_KEYS = (
    "wage",
    "rate",
    "benefits",
    "rating",
    "defense",
    "settlement",
    "penalties",
)
EXPECTED_V1_2_CASELOAD_KEYS = (
    "channelVersion",
    "caseCount",
    "moneyCaseCount",
    "cases",
)
EXPECTED_V1_2_CASELOAD_CASE_KEYS = (
    "caseId",
    "truthFile",
    "seedHash",
    "averageWeeklyWage",
    "tdWeeklyRate",
    "tdBound",
    "method",
    "settlementGrossAmount",
)


def _literal_money_truth(
    channel_version: str,
    *,
    rating: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Independent compact fixture; no production writer or constant supplies it."""
    published: dict[str, Any] = {
        "wage": {},
        "rate": {},
        "benefits": {},
    }
    channel: dict[str, Any] = {
        "channelVersion": channel_version,
        "wage": {
            "periods": [],
            "inKind": [],
            "employmentStart": None,
            "concurrentEmployment": False,
            "pattern": "regular",
            "patternSource": "seed",
            "computation": {
                "method": "actual_weekly_earnings",
                "methodSource": "derived",
                "methodReason": "literal fixture",
                "periodsConsidered": 0,
                "weeksConsidered": "0",
                "grossConsidered": "0",
                "inKindWeekly": "0",
                "averageWeeklyWage": "1000.00",
            },
            "rate": {
                "averageWeeklyWage": "1000.00",
                "tdWeeklyRate": "666.67",
                "tdBound": "unbounded",
                "pdWeeklyRate": "290.00",
                "pdBound": "max",
                "basis": {
                    "label": "literal-2012",
                    "effectiveFrom": "2012-01-01",
                    "effectiveTo": "2013-01-01",
                    "tdFraction": "2/3",
                    "tdMaxWeekly": "1010.50",
                    "tdMinWeekly": "151.57",
                    "pdFraction": "2/3",
                    "pdMaxWeekly": "290.00",
                    "pdMinWeekly": "130.00",
                    "authority": "literal fixture authority",
                    "counselConfirmed": False,
                    "source": "engine_default_table",
                },
            },
        },
        "benefits": {"tdPeriods": [], "pdAdvances": [], "gaps": []},
        "published": published,
    }
    if rating is not None:
        channel["rating"] = copy.deepcopy(rating)
        published["rating"] = copy.deepcopy(rating)
    return {
        "schemaVersion": "1.0.0",
        "kind": "case",
        "caseId": "literal-money",
        "seedHash": "0" * 64,
        "provenance": {},
        "channels": {"money": channel},
    }


LITERAL_RATING_V1_2: dict[str, Any] = {
    "schedule": {
        "edition": "January 2005",
        "sourceUrl": "https://www.dir.ca.gov/dwc/pdr.pdf",
        "pdfSha256": "cfabf43b57533b90133f71aecf882c8b17a5dad3659db7aea6e810728f664201",
        "extractedTextSha256": (
            "827d66440bc9161743aa6add355c823a6d7d5913162df140f38bc871f83f47b1"
        ),
        "tablesSha256": (
            "a7177da9a12cda090a767f3dccd9e604f3686ba2ded7b0ff36e3dae6e6ca2791"
        ),
        "section4Sha256": (
            "23a56ded69f1cffd6ae9c2dc613c52d2e5750a9bd432a86fd5d00d50f3419e83"
        ),
        "section4MetaSha256": (
            "7847c7410dc348de7092fd1283077c1645192b36e01b7e0ee5230cc3cacb52e6"
        ),
        "counselStatus": "PDRS_2005_SOURCE_VERIFIED_POST2013_FACTOR_COUNSEL_RULED",
    },
    "dateOfInjury": "2012-06-15",
    "applicantAge": 30,
    "occupationGroup": "470",
    "occupationTitle": "Warehouse worker",
    "impairments": [
        {
            "id": "cervical",
            "bodyPart": "cervical_spine",
            "impairmentNumber": "15.01.02.02",
            "description": "Cervical N{EN DASH} Range of Motion N{EN DASH} Soft Tissue Lesion",
            "wpi": 8,
            "adjustmentMethod": "fec_rank_table",
            "fecRank": 5,
            "adjustmentFactor": None,
            "scheduleAdjusted": 10,
            "variant": "H",
            "occupationAdjusted": 13,
            "ageBand": "27-31",
            "ageAdjusted": 11,
            "ratingString": "15.01.02.02 - 8 - [5]10 - 470H - 13 - 11%",
        }
    ],
    "combinationMethod": "single",
    "kiteImpairmentIds": None,
    "scheduledCombinedRating": 11,
    "combinedRating": 11,
    "finalPdPercent": 11,
    "ratingString": "15.01.02.02 - 8 - [5]10 - 470H - 13 - 11%",
}


def _seed_body(
    case_id: str,
    *,
    scenario: dict[str, Any] | None,
    doi: str = "2021-06-14",
    rng_seed: int = 4242,
    stage: str = "resolved",
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "case_id": case_id,
        "rng_seed": rng_seed,
        "injury": {
            "type": "specific",
            "date_of_injury": doi,
            "body_parts": [{"part": "lumbar_spine"}],
        },
        "lifecycle": {
            "target_stage": stage,
            "eval_type": "qme",
            "resolution": {"type": "c_and_r"},
        },
        "output": {"formats": ["pdf"]},
        "documents": {"format_mix": {"pdf": 1.0}, "global_cap": 8},
    }
    if scenario is not None:
        body["scenario"] = scenario
    return body


def _plan(
    case_id: str,
    *,
    scenario: dict[str, Any] | None,
    doi: str = "2021-06-14",
    rng_seed: int = 4242,
) -> Any:
    return build_case_plan(
        parse_case_seed(_seed_body(case_id, scenario=scenario, doi=doi, rng_seed=rng_seed)),
        case_number=1,
    )


def _rated_plan(
    case_id: str = "truth-rated",
    *,
    doi: str = "2013-06-14",
    rng_seed: int = 4340,
) -> Any:
    body = _seed_body(
        case_id,
        scenario={
            "wages": {},
            "rating": {
                "schedule": "pdrs_2005",
                "occupation_group": "470",
                "impairments": [
                    {
                        "id": "lumbar",
                        "body_part": "lumbar_spine",
                        "impairment_number": "15.01.02.02",
                        "wpi": 8,
                    }
                ],
                "combination_method": "single",
            },
        },
        doi=doi,
        rng_seed=rng_seed,
    )
    body["profile"] = {
        "applicant": {"age": 30, "occupation": "Warehouse worker"}
    }
    body["documents"] = {
        "format_mix": {"pdf": 1.0},
        "include_only": ["PD_RATING_CALCULATION_WORKSHEET"],
    }
    return build_case_plan(parse_case_seed(body), case_number=1)


@pytest.fixture(scope="module")
def rated_plan() -> Any:
    return _rated_plan()


def _rating_from_literal_projection(document: dict[str, Any]) -> RatingFacts:
    schedule_doc = document["schedule"]
    schedule = RatingScheduleBinding(
        edition=schedule_doc["edition"],
        source_url=schedule_doc["sourceUrl"],
        pdf_sha256=schedule_doc["pdfSha256"],
        extracted_text_sha256=schedule_doc["extractedTextSha256"],
        tables_sha256=schedule_doc["tablesSha256"],
        section4_sha256=schedule_doc["section4Sha256"],
        section4_meta_sha256=schedule_doc["section4MetaSha256"],
        counsel_status=schedule_doc["counselStatus"],
    )
    impairments = tuple(
        RatingImpairment(
            id=row["id"],
            body_part=row["bodyPart"],
            impairment_number=row["impairmentNumber"],
            description=row["description"],
            wpi=row["wpi"],
            adjustment_method=row["adjustmentMethod"],
            fec_rank=row["fecRank"],
            adjustment_factor=row["adjustmentFactor"],
            schedule_adjusted=row["scheduleAdjusted"],
            variant=row["variant"],
            occupation_adjusted=row["occupationAdjusted"],
            age_band=row["ageBand"],
            age_adjusted=row["ageAdjusted"],
            rating_string=row["ratingString"],
        )
        for row in document["impairments"]
    )
    return RatingFacts(
        schedule=schedule,
        date_of_injury=document["dateOfInjury"],
        applicant_age=document["applicantAge"],
        occupation_group=document["occupationGroup"],
        occupation_title=document["occupationTitle"],
        impairments=impairments,
        combination_method=document["combinationMethod"],
        kite_impairment_ids=document["kiteImpairmentIds"],
        scheduled_combined_rating=document["scheduledCombinedRating"],
        combined_rating=document["combinedRating"],
        final_pd_percent=document["finalPdPercent"],
        rating_string=document["ratingString"],
    )


@pytest.fixture(scope="module")
def generated_penalty_tree(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One real on-disk scorer tree, copied before each corruption probe."""
    out_dir = tmp_path_factory.mktemp("truth-validator")
    body = _seed_body(
        "truth-penalty-validator",
        scenario={
            "wages": {"pattern": "regular", "base_weekly_wage": 1500.0},
            "benefits": {
                "td_weeks": 24,
                "td_gap_days": 45,
                "late_payments": 2,
                "max_days_late": 30,
            },
            "penalties": {},
        },
        rng_seed=4310,
    )
    carriers = [
        "WAGE_STATEMENTS_PRE_INJURY",
        "TD_PAYMENT_RECORD_ONGOING",
        "COMPROMISE_AND_RELEASE",
        "ORDER_APPROVING_SETTLEMENT",
        "BENEFIT_PAYMENT_LEDGER",
    ]
    body["documents"] = {
        "format_mix": {"pdf": 1.0},
        "include_only": carriers,
        "overrides": [{"subtype": subtype, "count": 1} for subtype in carriers],
        "global_cap": len(carriers),
    }
    seed = parse_case_seed(body)
    generate_caseload("truth-validator", (seed,), out_dir, truth=True)
    truth = read_truth_manifest(out_dir / TRUTH_DIR / "truth-penalty-validator.truth.json")
    assert truth["channels"]["money"]["penalties"]["assessments"]
    assert validate_output_tree(out_dir).problems == []
    return out_dir


def _copy_generated_tree(source: Path, tmp_path: Path, name: str = "out") -> Path:
    target = tmp_path / name
    shutil.copytree(source, target)
    return target


def _truth_path(out_dir: Path) -> Path:
    return out_dir / TRUTH_DIR / "truth-penalty-validator.truth.json"


def _rewrite_json(path: Path, document: dict[str, Any]) -> None:
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


@pytest.fixture(scope="module")
def money_plans() -> tuple[Any, ...]:
    regular = _plan(
        "truth-regular",
        scenario={
            "wages": {"pattern": "regular", "base_weekly_wage": 1000.0},
            "settlement": {"gross_amount": 88000},
        },
        doi="2013-06-14",
        rng_seed=4301,
    )
    explicit = _plan(
        "truth-explicit",
        scenario={
            "wages": {
                "earnings": [
                    {
                        "period_start": "2021-05-17",
                        "period_end": "2021-05-30",
                        "gross": 2400,
                        "overtime": 200,
                    },
                    {
                        "period_start": "2021-05-31",
                        "period_end": "2021-06-13",
                        "gross": 2600,
                        "overtime": 300,
                    },
                ]
            }
        },
        rng_seed=4302,
    )
    capped = _plan(
        "truth-capped",
        scenario={"wages": {"pattern": "regular", "base_weekly_wage": 10000.0}},
        rng_seed=4303,
    )
    assert capped.money_facts is not None
    assert capped.money_facts.wages.rate.td_bound == "max"
    complex_plan = _plan(
        "truth-complex",
        scenario={
            "wages": {
                "pattern": "regular",
                "base_weekly_wage": 1500.0,
                "concurrent_employment": True,
                "concurrent_weekly_wage": 450.0,
                "in_kind": [{"kind": "lodging", "weekly_value": 175.0}],
            },
            "benefits": {
                "td_weeks": 24,
                "td_gap_days": 45,
                "late_payments": 2,
                "max_days_late": 30,
            },
            "penalties": {},
        },
        rng_seed=4304,
    )
    assert complex_plan.money_facts is not None
    assert complex_plan.money_facts.benefits.late_payment_count > 0
    assert complex_plan.money_facts.benefits.gaps
    assert complex_plan.money_facts.penalties is not None
    assert complex_plan.money_facts.penalties.assessments
    return regular, explicit, capped, complex_plan


def test_money_channel_round_trips_four_materially_different_plans(
    tmp_path: Path, money_plans: tuple[Any, ...]
) -> None:
    for plan in money_plans:
        path = write_case_truth_manifest(plan, tmp_path)
        reconstructed = money_facts_from_truth(read_truth_manifest(path))
        assert reconstructed == plan.money_facts

    oldest_basis = money_plans[0].money_facts.wages.rate.basis
    assert oldest_basis.effective_from.isoformat() == "2013-01-01"
    assert oldest_basis.td_fraction == Fraction(2, 3)
    assert oldest_basis.pd_fraction == Fraction(2, 3)


@pytest.mark.parametrize("decimal_field", ["listed_gross", "rate_fraction"])
def test_money_channel_round_trip_preserves_subcent_model_values(
    tmp_path: Path, money_plans: tuple[Any, ...], decimal_field: str
) -> None:
    """The scorer channel preserves model Decimals, even below the published cent."""
    plan = money_plans[1]
    assert plan.money_facts is not None
    wages = plan.money_facts.wages
    if decimal_field == "listed_gross":
        period = wages.periods[0].model_copy(update={"regular_gross": Decimal("2400.00125")})
        wages = wages.model_copy(update={"periods": (period, *wages.periods[1:])})
    else:
        basis = wages.rate.basis.model_copy(update={"td_fraction": Decimal("0.6666667")})
        rate = wages.rate.model_copy(update={"basis": basis})
        wages = wages.model_copy(update={"rate": rate})
    facts = plan.money_facts.model_copy(update={"wages": wages})
    precise_plan = replace(plan, money_facts=facts)

    path = write_case_truth_manifest(precise_plan, tmp_path / decimal_field)

    assert money_facts_from_truth(read_truth_manifest(path)) == facts


def test_money_gate_omits_channel_and_reimports_as_none() -> None:
    plan = _plan("truth-no-money", scenario=None, rng_seed=4305)
    document = build_case_truth_manifest(plan)
    assert document["channels"] == {}
    assert money_facts_from_truth(document) is None
    assert rating_facts_from_truth(document) is None


def test_r17_r18_money_versions_and_allowlists_are_literal() -> None:
    assert MONEY_CHANNEL_V1_0_VERSION == "1.0.0"
    assert MONEY_CHANNEL_V1_1_VERSION == "1.1.0"
    assert MONEY_CHANNEL_V1_2_VERSION == "1.2.0"
    assert MONEY_CHANNEL_VERSION == "1.1.0"
    assert SUPPORTED_MONEY_CHANNEL_VERSIONS == EXPECTED_MONEY_VERSIONS
    assert MONEY_V1_0_CASE_CHANNEL_KEYS == EXPECTED_V1_0_CASE_KEYS
    assert MONEY_V1_0_OPTIONAL_CASE_CHANNEL_KEYS == ("settlement",)
    assert MONEY_V1_1_CASE_CHANNEL_KEYS == EXPECTED_V1_1_CASE_KEYS
    assert MONEY_V1_1_OPTIONAL_CASE_CHANNEL_KEYS == (
        "settlement",
        "penalties",
    )
    assert MONEY_V1_2_CASE_CHANNEL_KEYS == EXPECTED_V1_2_CASE_KEYS
    assert MONEY_V1_2_OPTIONAL_CASE_CHANNEL_KEYS == (
        "rating",
        "defense",
        "settlement",
        "penalties",
    )
    assert MONEY_V1_2_PUBLISHED_GROUP_KEYS == EXPECTED_V1_2_PUBLISHED_KEYS
    assert MONEY_V1_2_CASELOAD_CHANNEL_KEYS == EXPECTED_V1_2_CASELOAD_KEYS
    assert MONEY_V1_2_CASELOAD_CASE_KEYS == EXPECTED_V1_2_CASELOAD_CASE_KEYS
    assert MONEY_V1_2_RATING_KEYS == EXPECTED_RATING_KEYS
    assert MONEY_V1_2_RATING_IMPAIRMENT_KEYS == EXPECTED_RATING_IMPAIRMENT_KEYS
    assert MONEY_V1_2_RATING_SCHEDULE_KEYS == EXPECTED_RATING_SCHEDULE_KEYS
    assert CASE_FACTS_RATING_KEYS == EXPECTED_RATING_KEYS
    assert CASE_FACTS_MONEY_RATING_KEYS == EXPECTED_RATING_KEYS
    assert CASE_FACTS_RATING_IMPAIRMENT_KEYS == EXPECTED_RATING_IMPAIRMENT_KEYS
    assert CASE_FACTS_RATING_SCHEDULE_KEYS == EXPECTED_RATING_SCHEDULE_KEYS


def test_r97_independent_literal_1_0_1_1_and_1_2_fixtures_parse_exactly() -> None:
    literal_1_0 = _literal_money_truth("1.0.0")
    literal_1_1 = _literal_money_truth("1.1.0")
    literal_1_2 = _literal_money_truth("1.2.0", rating=LITERAL_RATING_V1_2)
    literal_1_1_bytes = json.dumps(literal_1_1, indent=2, ensure_ascii=False) + "\n"

    facts_1_0 = money_facts_from_truth(literal_1_0)
    facts_1_1 = money_facts_from_truth(literal_1_1)
    facts_1_2 = money_facts_from_truth(literal_1_2)
    assert facts_1_0 == facts_1_1 == facts_1_2
    assert rating_facts_from_truth(literal_1_0) is None
    assert rating_facts_from_truth(literal_1_1) is None
    assert rating_facts_from_truth(literal_1_2) == _rating_from_literal_projection(
        LITERAL_RATING_V1_2
    )
    assert json.dumps(literal_1_1, indent=2, ensure_ascii=False) + "\n" == (
        literal_1_1_bytes
    )


def test_r97_literal_1_0_1_1_and_1_2_fixtures_dispatch_exactly(
    money_plans: tuple[Any, ...], rated_plan: Any
) -> None:
    current = build_case_truth_manifest(money_plans[0])
    current_bytes = json.dumps(current, indent=2, ensure_ascii=False) + "\n"
    current_channel = current["channels"]["money"]
    assert current_channel["channelVersion"] == "1.1.0"
    assert tuple(current_channel) == tuple(
        key for key in EXPECTED_V1_1_CASE_KEYS if key in current_channel
    )
    assert money_facts_from_truth(current) == money_plans[0].money_facts
    assert rating_facts_from_truth(current) is None
    assert json.dumps(current, indent=2, ensure_ascii=False) + "\n" == current_bytes

    legacy = copy.deepcopy(current)
    legacy["channels"]["money"]["channelVersion"] = "1.0.0"
    legacy_before = copy.deepcopy(legacy)
    assert tuple(legacy["channels"]["money"]) == tuple(
        key
        for key in EXPECTED_V1_0_CASE_KEYS
        if key in legacy["channels"]["money"]
    )
    assert money_facts_from_truth(legacy) == money_plans[0].money_facts
    assert rating_facts_from_truth(legacy) is None
    assert legacy == legacy_before

    w2 = build_case_truth_manifest(rated_plan)
    w2_channel = w2["channels"]["money"]
    assert w2_channel["channelVersion"] == "1.2.0"
    assert tuple(w2_channel) == tuple(
        key for key in EXPECTED_V1_2_CASE_KEYS if key in w2_channel
    )
    assert "rating" in w2_channel
    assert "defense" not in w2_channel
    assert money_facts_from_truth(w2) == rated_plan.money_facts
    assert rating_facts_from_truth(w2) == rated_plan.case_facts.rating


def test_money_reader_rejects_invented_1_9_0(
    money_plans: tuple[Any, ...],
) -> None:
    """m23-14: exact dispatch rejects an invented same-major version."""
    document = build_case_truth_manifest(money_plans[0])
    document["channels"]["money"]["channelVersion"] = "1.9.0"
    with pytest.raises(TruthManifestError, match=r"1[.]9[.]0"):
        money_facts_from_truth(document)


@pytest.mark.parametrize("version", [None, "1.1", "one.one.zero"])
def test_money_reader_rejects_missing_or_malformed_version(
    money_plans: tuple[Any, ...], version: str | None
) -> None:
    document = build_case_truth_manifest(money_plans[0])
    if version is None:
        del document["channels"]["money"]["channelVersion"]
    else:
        document["channels"]["money"]["channelVersion"] = version
    with pytest.raises(TruthManifestError, match="channelVersion"):
        money_facts_from_truth(document)


def test_money_reader_rejects_rating_under_v1_1(
    money_plans: tuple[Any, ...], rated_plan: Any
) -> None:
    """m23-15: v1.1 cannot silently drop a v1.2 rating group."""
    current = build_case_truth_manifest(money_plans[0])
    rating = build_case_truth_manifest(rated_plan)["channels"]["money"][
        "rating"
    ]
    current["channels"]["money"]["rating"] = rating
    with pytest.raises(TruthManifestError, match="rating"):
        money_facts_from_truth(current)


def test_r19_cross_version_and_missing_required_fields_fail_closed(
    money_plans: tuple[Any, ...], rated_plan: Any
) -> None:
    w1 = build_case_truth_manifest(money_plans[0])
    with_defense = copy.deepcopy(w1)
    with_defense["channels"]["money"]["defense"] = None
    with pytest.raises(TruthManifestError, match="defense"):
        money_facts_from_truth(with_defense)

    penalties = build_case_truth_manifest(money_plans[-1])
    penalties["channels"]["money"]["channelVersion"] = "1.0.0"
    with pytest.raises(TruthManifestError, match="penalties"):
        money_facts_from_truth(penalties)

    w2 = build_case_truth_manifest(rated_plan)
    del w2["channels"]["money"]["wage"]
    with pytest.raises(TruthManifestError, match="wage"):
        money_facts_from_truth(w2)


def test_v1_2_defense_reader_seam_accepts_only_null_reserved_slot(
    rated_plan: Any,
) -> None:
    document = build_case_truth_manifest(rated_plan)
    document["channels"]["money"]["defense"] = None
    assert money_facts_from_truth(document) == rated_plan.money_facts
    assert rating_facts_from_truth(document) == rated_plan.case_facts.rating

    document["channels"]["money"]["defense"] = {"reserve": "premature"}
    with pytest.raises(TruthManifestError, match=MONEY_DEFENSE_SCOPE_UNSUPPORTED):
        money_facts_from_truth(document)


@pytest.mark.parametrize("change", ["missing", "unknown"])
def test_r51_rating_projection_rejects_missing_or_unknown_keys(
    rated_plan: Any, change: str
) -> None:
    document = build_case_truth_manifest(rated_plan)
    rating = document["channels"]["money"]["rating"]
    published = document["channels"]["money"]["published"]["rating"]
    if change == "missing":
        del rating["occupationTitle"]
        del published["occupationTitle"]
    else:
        rating["artifactRating"] = 9
        published["artifactRating"] = 9
    with pytest.raises(TruthManifestError, match="rating"):
        rating_facts_from_truth(document)


def test_r51_both_adjustment_keys_are_required_and_mutually_exclusive() -> None:
    post2013 = build_case_truth_manifest(_rated_plan("truth-dfec", doi="2013-06-14"))
    post2013_row = post2013["channels"]["money"]["rating"]["impairments"][0]
    assert "fecRank" in post2013_row and post2013_row["fecRank"] is None
    assert post2013_row["adjustmentFactor"] == "1.4"

    fec = build_case_truth_manifest(_rated_plan("truth-fec", doi="2012-06-14"))
    fec_row = fec["channels"]["money"]["rating"]["impairments"][0]
    assert isinstance(fec_row["fecRank"], int)
    assert "adjustmentFactor" in fec_row and fec_row["adjustmentFactor"] is None
    assert rating_facts_from_truth(fec) == _rated_plan(
        "truth-fec", doi="2012-06-14"
    ).case_facts.rating


def test_r46_writer_passes_the_single_rating_reference_to_money_channel(
    rated_plan: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """m23-27: no copied or independently computed rating DTO enters truth."""
    assert rated_plan.case_facts is not None
    expected = rated_plan.case_facts.rating
    assert expected is not None
    captured: list[RatingFacts | None] = []
    original = truth_manifest_module._money_channel

    def capture_reference(
        facts: MoneyFacts, *, rating: RatingFacts | None
    ) -> dict[str, Any]:
        captured.append(rating)
        return original(facts, rating=rating)

    monkeypatch.setattr(
        truth_manifest_module,
        "_money_channel",
        capture_reference,
    )
    document = truth_manifest_module.build_case_truth_manifest(rated_plan)
    assert captured == [expected]
    assert captured[0] is expected
    assert rating_facts_from_truth(document) == expected


def test_mixed_money_caseload_selects_1_2_but_keeps_narrow_member_rows(
    tmp_path: Path, money_plans: tuple[Any, ...], rated_plan: Any
) -> None:
    """m23-45: one rated case upgrades only the aggregate channel version."""
    truth_dir = tmp_path / TRUTH_DIR
    w1 = money_plans[0]
    plans = (w1, rated_plan)
    results = []
    for plan in plans:
        path = write_case_truth_manifest(plan, truth_dir)
        results.append(
            SimpleNamespace(
                case_id=plan.seed.case_id,
                plan=plan,
                truth_path=path,
            )
        )
    member_versions = tuple(
        read_truth_manifest(result.truth_path)["channels"]["money"][
            "channelVersion"
        ]
        for result in results
    )
    assert member_versions == ("1.1.0", "1.2.0")

    mixed = build_caseload_truth_manifest("mixed-money", results)
    channel = mixed["channels"]["money"]
    assert channel["channelVersion"] == "1.2.0"
    assert tuple(channel) == EXPECTED_V1_2_CASELOAD_KEYS
    assert all(
        tuple(row) == tuple(
            key for key in EXPECTED_V1_2_CASELOAD_CASE_KEYS if key in row
        )
        for row in channel["cases"]
    )
    assert all("rating" not in row and "defense" not in row for row in channel["cases"])

    all_w1 = build_caseload_truth_manifest("all-w1", results[:1])
    assert all_w1["channels"]["money"] == {
        "channelVersion": "1.1.0",
        "caseCount": 1,
        "moneyCaseCount": 1,
        "cases": [
            {
                "caseId": "truth-regular",
                "truthFile": "truth/truth-regular.truth.json",
                "seedHash": w1.seed.seed_hash(),
                "averageWeeklyWage": "1001.15",
                "tdWeeklyRate": "667.43",
                "tdBound": "unbounded",
                "method": "actual_weekly_earnings",
                "settlementGrossAmount": "88000.00",
            }
        ],
    }


@requires_substrate
def test_r87_seed_to_paper_public_inverse_and_scorer_round_trip(
    tmp_path: Path, rated_plan: Any
) -> None:
    assert rated_plan.case_facts is not None
    rating = rated_plan.case_facts.rating
    assert rating is not None
    assert "rating" not in MoneyFacts.model_fields

    public = facts_manifest_block(rated_plan.case_facts, rated_plan.money_facts)
    truth = build_case_truth_manifest(rated_plan)
    scorer = truth["channels"]["money"]["rating"]
    assert tuple(public["rating"]) == EXPECTED_RATING_KEYS
    assert tuple(public["money"]["rating"]) == EXPECTED_RATING_KEYS
    assert tuple(scorer) == EXPECTED_RATING_KEYS
    assert tuple(scorer["schedule"]) == EXPECTED_RATING_SCHEDULE_KEYS
    assert all(
        tuple(row) == EXPECTED_RATING_IMPAIRMENT_KEYS
        for row in scorer["impairments"]
    )
    assert public["rating"] == public["money"]["rating"] == scorer
    assert truth["channels"]["money"]["published"]["rating"] == scorer

    analyzer_extraction = _rating_from_literal_projection(public["rating"])
    inverse = rating_facts_from_truth(truth)
    assert analyzer_extraction == rating
    assert inverse == rating

    for index, subtype in enumerate(
        (
            "IMPAIRMENT_RATING_WORKSHEET",
            "PD_RATING_CALCULATION_WORKSHEET",
            "PD_RATING_CONVERSION",
        )
    ):
        result = render_document(
            seed=rated_plan.seed,
            cast=rated_plan.cast,
            subtype=subtype,
            doc_date=rated_plan.timeline.horizon,
            doc_format="pdf",
            index=600 + index,
            out_path=tmp_path / f"{subtype}.pdf",
            case_facts=rated_plan.case_facts,
            money_facts=rated_plan.money_facts,
        )
        text = extract_text(result.path, result.doc_format)
        for row in rating.impairments:
            assert row.rating_string in text
        assert f"{rating.final_pd_percent}%" in text


def test_envelope_is_complete_timeless_and_byte_deterministic(
    tmp_path: Path, money_plans: tuple[Any, ...]
) -> None:
    plan = money_plans[0]
    first = write_case_truth_manifest(plan, tmp_path / "first")
    second = write_case_truth_manifest(plan, tmp_path / "second")
    document = read_truth_manifest(first)

    assert document["schemaVersion"] == "1.0.0"
    assert document["kind"] == "case"
    assert document["audience"] == "analyzer-scorer"
    assert "never" in document["leakageRule"].lower()
    # No substrateSha: a truth file is a root file, hashed raw by the golden
    # gate, so it may carry nothing that describes the checkout. See
    # test_truth_provenance_carries_no_checkout_dependent_field.
    assert set(document["provenance"]) == {"generator", "seedHash", "rngSeed"}
    serialized = json.dumps(document)
    assert '"generatedAt"' not in serialized
    assert '"timestamp"' not in serialized
    assert first.read_bytes() == second.read_bytes()


def test_published_block_is_the_existing_public_contract(money_plans: tuple[Any, ...]) -> None:
    plan = money_plans[1]
    assert plan.money_facts is not None
    channel = build_case_truth_manifest(plan)["channels"]["money"]
    assert channel["published"] == money_manifest_block(plan.money_facts)


def test_unknown_channel_is_ignored_and_money_exact_version_is_guarded(
    money_plans: tuple[Any, ...],
) -> None:
    plan = money_plans[0]
    document = build_case_truth_manifest(plan)
    document["channels"]["defects"] = {"channelVersion": "19.0.0"}
    assert money_facts_from_truth(document) == plan.money_facts

    incompatible = copy.deepcopy(document)
    incompatible["channels"]["money"]["channelVersion"] = "2.4.0"
    with pytest.raises(TruthManifestError) as raised:
        money_facts_from_truth(incompatible)
    assert "2.4.0" in str(raised.value)
    assert "1.1.0" in str(raised.value)

    with pytest.raises(TruthManifestError, match=r"channels[.]money must be an object"):
        money_facts_from_truth({"schemaVersion": "1.0.0", "channels": {"money": []}})


@pytest.mark.parametrize("schema_version", [None, "1", "x.y.z", 1.0])
def test_envelope_schema_version_is_required_and_well_formed(
    tmp_path: Path, money_plans: tuple[Any, ...], schema_version: Any
) -> None:
    document = build_case_truth_manifest(money_plans[0])
    if schema_version is None:
        del document["schemaVersion"]
    else:
        document["schemaVersion"] = schema_version
    path = tmp_path / "malformed.truth.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(TruthManifestError, match="schemaVersion"):
        read_truth_manifest(path)
    with pytest.raises(TruthManifestError, match="schemaVersion"):
        money_facts_from_truth(document)


def test_envelope_schema_version_accepts_minor_and_rejects_other_major(
    tmp_path: Path,
    money_plans: tuple[Any, ...],
) -> None:
    compatible = build_case_truth_manifest(money_plans[0])
    compatible["schemaVersion"] = "1.9.0"
    path = tmp_path / "compatible.truth.json"
    path.write_text(json.dumps(compatible), encoding="utf-8")
    assert money_facts_from_truth(read_truth_manifest(path)) == money_plans[0].money_facts

    incompatible = copy.deepcopy(compatible)
    incompatible["schemaVersion"] = "2.0.0"
    with pytest.raises(TruthManifestError) as raised:
        money_facts_from_truth(incompatible)
    assert "2.0.0" in str(raised.value)
    assert "1.0.0" in str(raised.value)


def test_exact_1_0_money_channel_rejects_1_1_penalty_fields(
    money_plans: tuple[Any, ...],
) -> None:
    """The historical 1.0 contract never silently drops 1.1 penalties."""
    plan = money_plans[-1]
    document = build_case_truth_manifest(plan)
    channel = document["channels"]["money"]
    assert channel["channelVersion"] == "1.1.0"
    assert "penalties" in channel
    assert money_facts_from_truth(document) == plan.money_facts

    prior_minor = copy.deepcopy(document)
    prior_minor["channels"]["money"]["channelVersion"] = "1.0.0"
    with pytest.raises(TruthManifestError, match="penalties"):
        money_facts_from_truth(prior_minor)


def test_rollup_indexes_money_and_non_money_cases_and_resolves_paths(
    tmp_path: Path, money_plans: tuple[Any, ...]
) -> None:
    no_money = _plan("truth-rollup-empty", scenario=None, rng_seed=4306)
    plans = (money_plans[0], no_money)
    truth_dir = tmp_path / TRUTH_DIR
    results = []
    for plan in plans:
        truth_path = write_case_truth_manifest(plan, truth_dir)
        results.append(
            SimpleNamespace(
                case_id=plan.seed.case_id,
                plan=plan,
                truth_path=truth_path,
            )
        )

    rollup_path = write_caseload_truth_manifest("truth-rollup", results, truth_dir)
    assert rollup_path.name == CASELOAD_TRUTH_NAME
    rollup = read_truth_manifest(rollup_path)
    assert [entry["caseId"] for entry in rollup["cases"]] == [
        "truth-regular",
        "truth-rollup-empty",
    ]
    channel = rollup["channels"]["money"]
    assert channel["caseCount"] == 2
    assert channel["moneyCaseCount"] == 1
    assert [entry["caseId"] for entry in channel["cases"]] == [
        "truth-regular",
        "truth-rollup-empty",
    ]
    assert "averageWeeklyWage" in channel["cases"][0]
    assert "averageWeeklyWage" not in channel["cases"][1]
    for entry in channel["cases"]:
        assert (tmp_path / entry["truthFile"]).is_file()

    empty_truth_dir = tmp_path / "empty" / TRUTH_DIR
    empty_path = write_case_truth_manifest(no_money, empty_truth_dir)
    empty_result = SimpleNamespace(
        case_id=no_money.seed.case_id,
        plan=no_money,
        truth_path=empty_path,
    )
    empty_rollup = write_caseload_truth_manifest("truth-empty", [empty_result], empty_truth_dir)
    empty_document = read_truth_manifest(empty_rollup)
    assert empty_document["channels"] == {}
    assert empty_document["cases"][0]["caseId"] == "truth-rollup-empty"


def test_rollup_omits_unsettled_amount_but_keeps_settled_amount(
    tmp_path: Path, money_plans: tuple[Any, ...]
) -> None:
    settled = money_plans[0]
    assert settled.money_facts is not None
    assert settled.money_facts.settlement is not None
    unsettled = replace(
        money_plans[1],
        money_facts=money_plans[1].money_facts.model_copy(update={"settlement": None}),
    )
    results = []
    for plan in (unsettled, settled):
        truth_path = write_case_truth_manifest(plan, tmp_path / TRUTH_DIR)
        results.append(SimpleNamespace(case_id=plan.seed.case_id, plan=plan, truth_path=truth_path))

    rollup = read_truth_manifest(
        write_caseload_truth_manifest("absent-not-null", results, tmp_path / TRUTH_DIR)
    )
    entries = rollup["channels"]["money"]["cases"]
    assert "settlementGrossAmount" not in entries[0]
    assert entries[1]["settlementGrossAmount"] == "88000.00"


def test_output_validator_recomputes_truth_penalty_amount(
    tmp_path: Path, generated_penalty_tree: Path
) -> None:
    out_dir = _copy_generated_tree(generated_penalty_tree, tmp_path)
    path = _truth_path(out_dir)
    truth = read_truth_manifest(path)
    assessment = truth["channels"]["money"]["penalties"]["assessments"][0]
    assessment["amount"] = f"{Decimal(assessment['amount']) + Decimal('0.01'):.2f}"
    _rewrite_json(path, truth)

    problems = validate_output_tree(out_dir).problems

    assert any(
        "assessments[1].amount is" in problem and "product" in problem for problem in problems
    )


def test_output_validator_recomputes_truth_penalty_days_late(
    tmp_path: Path, generated_penalty_tree: Path
) -> None:
    out_dir = _copy_generated_tree(generated_penalty_tree, tmp_path)
    path = _truth_path(out_dir)
    truth = read_truth_manifest(path)
    assessment = truth["channels"]["money"]["penalties"]["assessments"][0]
    assessment["daysLate"] += 1
    _rewrite_json(path, truth)

    problems = validate_output_tree(out_dir).problems

    assert any("daysLate is" in problem and "statutoryDueDate" in problem for problem in problems)


def test_output_validator_rejects_assessment_for_unpaid_schedule_entry(
    tmp_path: Path, generated_penalty_tree: Path
) -> None:
    out_dir = _copy_generated_tree(generated_penalty_tree, tmp_path)
    path = _truth_path(out_dir)
    truth = read_truth_manifest(path)
    penalties = truth["channels"]["money"]["penalties"]
    assessment = penalties["assessments"][0]
    schedule_entry = next(
        item
        for item in penalties["schedule"]
        if (item["source"], item["ordinal"]) == (assessment["source"], assessment["ordinal"])
    )
    schedule_entry["unpaid"] = True
    _rewrite_json(path, truth)

    problems = validate_output_tree(out_dir).problems

    assert any("unpaid" in problem and "remove assessments" in problem for problem in problems)


def test_output_validator_reports_missing_and_stray_case_truth_files(
    tmp_path: Path, generated_penalty_tree: Path
) -> None:
    missing = _copy_generated_tree(generated_penalty_tree, tmp_path, "missing")
    _truth_path(missing).unlink()
    missing_problems = validate_output_tree(missing).problems
    assert any(
        "truth-penalty-validator" in problem and "truth manifest is missing" in problem
        for problem in missing_problems
    )

    stray = _copy_generated_tree(generated_penalty_tree, tmp_path, "stray")
    shutil.copyfile(_truth_path(stray), stray / TRUTH_DIR / "not-a-case.truth.json")
    stray_problems = validate_output_tree(stray).problems
    assert any(
        "not-a-case" in problem and "case directory is missing" in problem
        for problem in stray_problems
    )


def test_output_validator_reports_truth_published_projection_drift(
    tmp_path: Path, generated_penalty_tree: Path
) -> None:
    out_dir = _copy_generated_tree(generated_penalty_tree, tmp_path)
    path = _truth_path(out_dir)
    truth = read_truth_manifest(path)
    published = truth["channels"]["money"]["published"]
    published["wage"]["averageWeeklyWage"] = "0.01"
    _rewrite_json(path, truth)

    problems = validate_output_tree(out_dir).problems

    assert any(
        "published minus penalties" in problem and "caseFacts.money" in problem
        for problem in problems
    )


def test_output_validator_recomputes_the_published_penalty_block(
    tmp_path: Path, generated_penalty_tree: Path
) -> None:
    """The compact block that actually ships must be checked, not only its twin.

    ``published.penalties`` is the shape a scorer reads, and it was validated by
    nothing: the analyzer projection pops ``penalties`` before the manifest is
    written, and the truth-tree check popped it again before comparing — so the
    lossless channel carried every assertion while the shipped bytes carried
    none. Perturbing only the published total is the difference between "the
    same numbers twice" and "the numbers we hand out".
    """
    out_dir = _copy_generated_tree(generated_penalty_tree, tmp_path)
    path = _truth_path(out_dir)
    truth = read_truth_manifest(path)
    published = truth["channels"]["money"]["published"]["penalties"]
    assert published["assessments"], "the probe needs a published assessment"
    published["totalIncrease"] = f"{Decimal(published['totalIncrease']) + Decimal('0.01'):.2f}"
    _rewrite_json(path, truth)

    problems = validate_output_tree(out_dir).problems

    assert any("published" in problem and "totalIncrease" in problem for problem in problems), (
        problems
    )


def test_penalty_validation_is_exact_under_a_reduced_ambient_precision(
    tmp_path: Path,
) -> None:
    """The validator recomputes in the producer's context, not the caller's.

    Every figure is produced inside ``exact()``. The three recomputations that
    check them ran in whatever context the caller happened to be in, so a host
    process with a reduced ``decimal`` precision would have the validator invent
    drift and condemn a correct corpus. The operands below are exact and correct;
    only the ambient precision is hostile.
    """
    from wc_caseload_engine.manifests import _validate_penalties

    assessment = {
        "source": "td_period",
        "ordinal": 1,
        "rule": "subsequent_td_payment",
        "principal": "7974.24",
        "statutoryDueDate": "2021-07-28",
        "operationalDueDate": "2021-07-28",
        "datePaid": "2021-08-12",
        "daysLate": 15,
        "increaseFraction": "0.1",
        "amount": "797.42",
    }
    second = dict(assessment, ordinal=2)
    penalties = {
        "assessmentCount": 2,
        "counselConfirmed": False,
        "deadlineConfirmed": False,
        "unpaidCount": 0,
        "schedule": [
            {
                "source": "td_period",
                "ordinal": ordinal,
                "rule": "subsequent_td_payment",
                "statutoryDueDate": "2021-07-28",
                "operationalDueDate": "2021-07-28",
                "datePaid": "2021-08-12",
                "daysLate": 15,
                "unpaid": False,
            }
            for ordinal in (1, 2)
        ],
        "assessments": [assessment, second],
        # 797.42 + 797.42, and 7974.24 + 7974.24 — the second sum needs seven
        # significant digits, which is what a six-digit context cannot hold.
        "totalIncrease": "1594.84",
        "principalAssessed": "15948.48",
    }
    surfaces = {"TD_PAYMENT_RECORD_ONGOING"}

    assert _validate_penalties(penalties, surfaces, "precision-probe") == []

    with decimal.localcontext(decimal.Context(prec=6)):
        problems = _validate_penalties(penalties, surfaces, "precision-probe")

    assert problems == [], problems


def test_scorer_vocabulary_covers_every_emitted_truth_key(tmp_path: Path) -> None:
    """The two frozensets must be derived from the builders, not remembered.

    They are the sweep terms the case-tree leakage anti-probe runs on, so a key
    the builders emit but the sets never learned about is a term nothing
    watches. Equality in both directions: a new emitted key fails until it is
    classified, and a set member nothing emits any more fails as stale.
    """
    plan = _plan(
        "vocabulary-probe",
        scenario={
            "wages": {"pattern": "regular", "base_weekly_wage": 1500},
            "benefits": {
                "td_weeks": 24,
                "td_gap_days": 45,
                "late_payments": 2,
                "max_days_late": 30,
            },
            "penalties": {},
            "settlement": {"gross_amount": 90000},
        },
        rng_seed=4309,
    )
    envelope = build_case_truth_manifest(plan)
    index = build_caseload_truth_manifest(
        "vocabulary-probe-load",
        (
            SimpleNamespace(
                case_id="vocabulary-probe", plan=plan, truth_path=tmp_path / "x.truth.json"
            ),
        ),
    )

    # The envelope *structure*: both manifests' own top-level keys, the version
    # each channel stamps on itself, and the pointer an index record uses to
    # name a scorer file. Money facts carried inside an index record are public
    # world facts and are governed by GOVERNED_MONEY_FIELDS, not by this set.
    structural = set(envelope) | set(index)
    for document in (envelope, index):
        for channel in document["channels"].values():
            structural |= set(channel) & {"channelVersion"}
    for record in index["cases"]:
        structural |= set(record) & {"truthFile"}

    unclassified = (
        structural - SCORER_ONLY_ENVELOPE_KEY_NAMES - ENVELOPE_KEYS_THAT_ARE_NOT_SENTINELS.keys()
    )
    assert not unclassified, (
        f"truth envelopes emit {sorted(unclassified)}, which neither "
        "SCORER_ONLY_ENVELOPE_KEY_NAMES nor the exemption ledger accounts for — "
        "classify the key as a scorer-only sentinel or record why it cannot be one"
    )
    stale = SCORER_ONLY_ENVELOPE_KEY_NAMES - structural
    assert not stale, f"SCORER_ONLY_ENVELOPE_KEY_NAMES names unemitted keys {sorted(stale)}"

    money_channel = envelope["channels"]["money"]
    penalty_blocks = [
        money_channel["penalties"],
        money_channel["published"]["penalties"],
    ]
    emitted_assessment_keys: set[str] = {"assessments"}
    for block in penalty_blocks:
        assert block["assessments"], "the probe needs an assessment to walk"
        for record in block["assessments"]:
            emitted_assessment_keys |= set(record)

    assert emitted_assessment_keys == PENALTY_ASSESSMENT_KEY_NAMES, (
        "PENALTY_ASSESSMENT_KEY_NAMES must equal the keys the assessment builders "
        f"emit; emitted {sorted(emitted_assessment_keys)}"
    )


def test_truth_provenance_carries_no_checkout_dependent_field(tmp_path: Path) -> None:
    """A truth file's bytes must depend on the corpus and nothing else.

    Truth files are **root files** in the output tree, so the golden gate hashes
    them raw; the ``provenance.substrateSha`` redaction that covers the case and
    caseload *manifests* cannot reach them. `substrateSha` comes from `git log`
    over the substrate directory, so it describes the checkout — and the same
    corpus generated from a PR branch and from that PR's merge ref produced
    different truth bytes, reddening the gate for a corpus nothing had changed.

    This pins both provenance blocks to an exact key set rather than asserting
    the absence of one field, so any future checkout-dependent value has to be
    argued for here before it can reach an artifact hashed raw.
    """
    plan = _plan(
        "provenance-probe",
        scenario={"wages": {"pattern": "regular", "base_weekly_wage": 1500}},
        rng_seed=4311,
    )
    envelope = build_case_truth_manifest(plan)
    index = build_caseload_truth_manifest(
        "provenance-probe-load",
        (
            SimpleNamespace(
                case_id="provenance-probe", plan=plan, truth_path=tmp_path / "x.truth.json"
            ),
        ),
    )

    assert set(envelope["provenance"]) == set(TRUTH_PROVENANCE_KEYS)
    assert set(index["provenance"]) == set(CASELOAD_TRUTH_PROVENANCE_KEYS)
    assert set(TRUTH_PROVENANCE_KEYS) == {"generator", "seedHash", "rngSeed"}
    assert set(CASELOAD_TRUTH_PROVENANCE_KEYS) == {"generator"}
    assert "substrateSha" not in json.dumps(envelope)
    assert "substrateSha" not in json.dumps(index)


def test_output_validator_reports_truth_seed_hash_drift(
    tmp_path: Path, generated_penalty_tree: Path
) -> None:
    out_dir = _copy_generated_tree(generated_penalty_tree, tmp_path)
    path = _truth_path(out_dir)
    truth = read_truth_manifest(path)
    truth["provenance"]["seedHash"] = "wrong-seed-hash"
    _rewrite_json(path, truth)

    problems = validate_output_tree(out_dir).problems

    assert any(
        "truth provenance.seedHash" in problem and "wrong-seed-hash" in problem
        for problem in problems
    )


def test_output_validator_accepts_clean_truth_and_legacy_tree_without_truth(
    tmp_path: Path, generated_penalty_tree: Path
) -> None:
    clean = _copy_generated_tree(generated_penalty_tree, tmp_path, "clean")
    clean_report = validate_output_tree(clean)
    assert clean_report.problems == []
    assert clean_report.truth_manifests == 1

    legacy = _copy_generated_tree(generated_penalty_tree, tmp_path, "legacy")
    shutil.rmtree(legacy / TRUTH_DIR)
    legacy_report = validate_output_tree(legacy)
    assert legacy_report.problems == []
    assert legacy_report.truth_manifests == 0


def test_truth_directory_isolation_resolves_direct_and_traversal_paths(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    case_dir = out_dir / "case-001"
    with pytest.raises(TruthManifestError) as direct:
        check_truth_dir_is_isolated(case_dir / "labels", out_dir, ("case-001",))
    assert str((case_dir / "labels").resolve()) in str(direct.value)
    assert str(case_dir.resolve()) in str(direct.value)
    assert "outside" in str(direct.value)

    check_truth_dir_is_isolated(out_dir / TRUTH_DIR, out_dir, ("case-001",))

    traversal = out_dir / TRUTH_DIR / ".." / "case-001" / "labels"
    with pytest.raises(TruthManifestError):
        check_truth_dir_is_isolated(traversal, out_dir, ("case-001",))


def test_generate_case_rejects_nested_truth_directory_before_writing(tmp_path: Path) -> None:
    seed = parse_case_seed(_seed_body("nested-truth", scenario=None, stage="intake"))
    case_dir = tmp_path / seed.case_id

    with pytest.raises(TruthManifestError):
        generate_case(seed, tmp_path, truth_dir=case_dir / "scorer")

    assert not case_dir.exists()


def test_disabled_truth_output_succeeds_when_no_truth_directory_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("wc_caseload_engine.manifests.check_substrate_pin", lambda: None)
    out_dir = tmp_path / "clean"
    assert generate_caseload("clean", (), out_dir, truth=False) == []
    assert (out_dir / "caseload_manifest.json").is_file()
    assert not (out_dir / TRUTH_DIR).exists()


def test_disabled_truth_output_rejects_and_preserves_existing_truth_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("wc_caseload_engine.manifests.check_substrate_pin", lambda: None)
    truth_dir = tmp_path / "stale" / TRUTH_DIR
    truth_dir.mkdir(parents=True)
    marker = truth_dir / "operator-file"
    marker.write_text("keep", encoding="utf-8")

    with pytest.raises(TruthManifestError) as raised:
        generate_caseload("stale", (), tmp_path / "stale", truth=False)
    assert str(truth_dir) in str(raised.value)
    assert "remove" in str(raised.value)
    assert marker.read_text(encoding="utf-8") == "keep"


@pytest.mark.slow
@requires_substrate
def test_case_tree_contains_no_scorer_only_vocabulary(tmp_path: Path) -> None:
    """Sweep scorer metadata, not legitimate facts used for document coherence.

    The analyzer intentionally receives ``seed.yaml``, ``case_facts.yaml``, and
    ``manifest.json``'s ``caseFacts`` world facts so it can compare documents with
    those facts.  The separate truth channel protects scorer-only assessment and
    provenance vocabulary, plus future defect and assertion-quality labels; this
    probe therefore targets that vocabulary rather than pretending facts are secret.
    """
    seed = parse_case_seed(
        _seed_body(
            "leakage-probe",
            scenario={
                "wages": {"pattern": "regular", "base_weekly_wage": 1500},
                "benefits": {"td_weeks": 8, "late_payments": 2, "max_days_late": 15},
                "penalties": {},
            },
            rng_seed=4308,
        )
    )
    result = generate_case(seed, tmp_path)
    vocabulary = (
        SCORER_ONLY_ENVELOPE_KEY_NAMES | PENALTY_ASSESSMENT_KEY_NAMES | {"truth"}
    ) - LEGITIMATE_SCORER_VOCABULARY_OVERLAPS.keys()
    artifacts = [
        result.directory / "seed.yaml",
        result.directory / "case_facts.yaml",
        result.directory / "manifest.json",
        *(result.directory / "documents").rglob("*"),
    ]
    leaks = {
        term: str(path.relative_to(result.directory))
        for path in artifacts
        if path.is_file()
        for term in vocabulary
        if term.encode() in path.read_bytes()
        or (term == "truth" and term.encode() in path.read_bytes().lower())
    }
    assert not leaks


@pytest.mark.slow
@requires_substrate
def test_truth_subtree_is_outside_case_and_does_not_confuse_validator(
    generated_penalty_tree: Path,
) -> None:
    truth_path = _truth_path(generated_penalty_tree)
    case_dir = generated_penalty_tree / "truth-penalty-validator"

    assert truth_path.is_file()
    assert not (case_dir / TRUTH_DIR).exists()
    assert validate_output_tree(generated_penalty_tree).ok


# ---------------------------------------------------------------------------
# AJC-61 (M2) — the assertions channel (E.6)
# ---------------------------------------------------------------------------

from wc_caseload_engine.truth_manifest import (
    ASSERTIONS_CHANNEL_VERSION,
    LEDGER_DIGEST_MISMATCH,
    assertion_ledger_digest,
    medical_assertions_from_truth,
)

#: A deterministic assertion-bearing seed: explicit world truth, explicit
#: divergent assertions, sampling on — the writer-side witness for E.6.
_ASSERTION_SCENARIO: dict[str, Any] = {
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
                "resolution_type": "stipulated_award",
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
            {
                "id": "ctn-01",
                "claim_type": "industrial_causation",
                "party": "applicant",
                "position": "affirm",
                "target_condition_id": "cond-00",
                "rationale": "the lumbar condition arose from the industrial injury",
            }
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
                "reviewed_condition_ids": ["cond-00"],
                "rationale": "examined the applicant and reviewed the record",
            }
        ],
        "apportionment_assertions": [
            {
                "id": "app-01",
                "opinion_id": "opn-01",
                "body_part": "lumbar_spine",
                "industrial_percent": 80,
                "nonindustrial_percent": 20,
                "basis_kinds": ["preexisting_degenerative_pathology"],
                "condition_ids": ["cond-00"],
                "description": "chronic lumbar disability limiting weight-bearing",
                "disability_causation_stated": True,
                "reasonable_medical_probability": True,
                "causal_rationale": "degenerative pathology contributes to disability",
                "percentage_rationale": "the share reflects the imaging severity",
            }
        ],
    },
}


def _assertion_plan(case_id: str = "assertions-truth") -> Any:
    return _plan(case_id, scenario=copy.deepcopy(_ASSERTION_SCENARIO), doi="2021-06-14")


def _assertion_truth(case_id: str = "assertions-truth") -> dict[str, Any]:
    return json.loads(json.dumps(build_case_truth_manifest(_assertion_plan(case_id))))


# ---------------------------------------------------------------------------
# AJC-62 Amendment A1 — the frozen assertions-channel 1.0.0 projection
#
# Every tuple below is an INDEPENDENT literal (A1-R7): never derived from and
# never imported into production. The anti-expansion test compares them with
# the production ASSERTIONS_V1_* constants for exact equality, so neither side
# can drift the other green.
# ---------------------------------------------------------------------------

AJC61_CASE_CHANNEL_KEYS = (
    "channelVersion",
    "kind",
    "audience",
    "leakageRule",
    "validationContext",
    "medicalHistory",
    "contentions",
    "medicalOpinions",
    "apportionmentAssertions",
    "ledgerDigest",
)

AJC61_VALIDATION_CONTEXT_KEYS = (
    "dateOfInjury",
    "anchorDate",
    "currentBodyParts",
    "targetStage",
    "claimResponse",
)

AJC61_OPTIONAL_VALIDATION_CONTEXT_KEYS = ("evalType",)

AJC61_MEDICAL_HISTORY_KEYS = ("conditions", "priorClaims")

AJC61_CONDITION_FIELDS = (
    "id",
    "key",
    "label",
    "causal_ground_truth",
    "onset",
    "body_system",
    "body_part",
    "apportionment_targets",
    "wholly_unrelated",
    "severity",
    "trajectory",
    "symptomatic_before_doi",
    "surfaces_in_file",
)

AJC61_PRIOR_CLAIM_FIELDS = (
    "id",
    "date_of_injury",
    "body_parts",
    "resolution_type",
    "overlaps_current",
    "award",
)

AJC61_PRIOR_AWARD_FIELDS = (
    "id",
    "prior_claim_id",
    "body_parts",
    "pd_percent",
    "award_date",
    "resolution_type",
    "conclusively_presumed",
)

AJC61_CONTENTION_FIELDS = (
    "id",
    "claim_type",
    "party",
    "position",
    "target_condition_id",
    "target_prior_claim_id",
    "target_prior_award_id",
    "target_body_part",
    "doctrine_hooks",
    "rationale",
    "treatment_causation",
    "requested_apportionment",
    "groundings",
    "quality",
)

AJC61_MEDICAL_OPINION_FIELDS = (
    "id",
    "author_role",
    "report_stage",
    "report_date",
    "apportionment_state",
    "determination_kind",
    "determination_rationale",
    "examination_performed",
    "reviewed_condition_ids",
    "reviewed_prior_claim_ids",
    "reviewed_prior_award_ids",
    "endorses_contention_ids",
    "rejects_contention_ids",
    "responds_to_opinion_id",
    "supersedes_opinion_id",
    "rationale",
    "revision_rationale",
    "quality",
)

AJC61_APPORTIONMENT_ASSERTION_FIELDS = (
    "id",
    "opinion_id",
    "body_part",
    "industrial_percent",
    "nonindustrial_percent",
    "basis_kinds",
    "condition_ids",
    "prior_claim_ids",
    "prior_award_ids",
    "description",
    "disability_causation_stated",
    "reasonable_medical_probability",
    "causal_rationale",
    "percentage_rationale",
    "prior_award_analysis",
    "revised_from_percent",
    "revision_rationale",
    "psych_exception_analysis",
    "linked_contention_id",
    "groundings",
    "quality",
)

AJC61_CASELOAD_CHANNEL_KEYS = (
    "channelVersion",
    "caseCount",
    "assertionCaseCount",
    "counts",
    "qualityCounts",
    "apportionmentStateCounts",
    "determinationKindCounts",
    "cases",
)

AJC61_CASELOAD_CASE_KEYS = (
    "caseId",
    "truthFile",
    "contentionCount",
    "medicalOpinionCount",
    "apportionmentAssertionCount",
)

#: M3-only vocabulary that must NEVER appear in channel 1.0.0, in both
#: spellings (A1-R3). Scanned as exact quoted JSON keys so ``opinionId`` (an
#: AJC-61 apportionment field) cannot shadow ``medicalOpinionId``.
M3_FORBIDDEN_CHANNEL_FIELDS = (
    "psych_injury_kind",
    "aoe_coe_finding",
    "aoe_coe_rationale",
    "event_kind",
    "revision_kind",
    "concurs_with_contention_ids",
    "defers_contention_ids",
    "contention_documents",
    "sample_contention_documents",
    "medical_opinion_id",
    "target_medical_opinion_id",
    "spoken_contention_ids",
    "contention_surface",
    "actor_party",
    "contention_actor_party",
    "defense_contest_theories",
    "contest_path",
    "document_kind",
    "template_subtype",
    "proposed_date",
    "contention_loop_source",
    "imr_application",
    "imr_application_content",
    "imr_target_denial_date",
    "target_denial_subtype",
    "target_denial_date",
    "disputed_treatment",
    "ur_determination_attached",
    "supporting_record_subtypes",
    "clinical_rebuttal",
    "mtus_citations",
    "by_document_index",
    "record_references",
    "preceding_report",
)


def _camel_case(name: str) -> str:
    """Independent camelizer for the expected-projection helper."""
    head, *rest = name.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in rest)


def _camelize_expected(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            _camel_case(str(key)): _camelize_expected(item)
            for key, item in value.items()
            if item is not None and item != [] and item != ()
        }
    if isinstance(value, list | tuple):
        return [_camelize_expected(item) for item in value]
    return value


def _ajc61_projection(model: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    """The independently constructed AJC-61 projection of one ledger model.

    Filters a full JSON-mode dump down to the frozen field tuple, then applies
    the local camelize/omission rules — never the production helper, and never
    a complete-M3 ``model_dump()`` comparison (A1-R6 points 2/7).
    """
    dumped = model.model_dump(mode="json")
    return _camelize_expected({name: dumped[name] for name in fields if name in dumped})


def _assert_channel_collections_match_ajc61_projection(
    channel: dict[str, Any], ledger: Any
) -> None:
    assert channel["contentions"] == [
        _ajc61_projection(c, AJC61_CONTENTION_FIELDS) for c in ledger.contentions
    ]
    assert channel["medicalOpinions"] == [
        _ajc61_projection(o, AJC61_MEDICAL_OPINION_FIELDS) for o in ledger.medical_opinions
    ]
    assert channel["apportionmentAssertions"] == [
        _ajc61_projection(a, AJC61_APPORTIONMENT_ASSERTION_FIELDS)
        for a in ledger.apportionment_assertions
    ]


def _v1_graded_ledger(plan: Any) -> Any:
    ledger = plan.medical_assertions
    assert ledger is not None
    context = assertion_context(plan.seed, plan.timeline)
    projection = project_medical_history(plan.medical_history, context.current_body_parts)
    return grade_ledger(context, projection, ledger, quality_contract="1.0.0")


def _m4_response_plan(case_id: str = "assertions-m4-response") -> Any:
    """The frozen §2 response chain plus a money channel for R98 isolation."""
    from test_medical_assertions import _assertion, _ledger, _opinion

    body = _m3_seed_body(case_id)
    body["scenario"]["wages"] = {
        "pattern": "regular",
        "base_weekly_wage": 1000.0,
    }
    plan = build_case_plan(parse_case_seed(body), case_number=1)
    base = _opinion(
        "opn-01",
        report_date=dt.date(2023, 2, 1),
        reviewed_condition_ids=("cond-00",),
    )
    response = _opinion(
        "opn-02",
        report_date=dt.date(2023, 9, 1),
        reviewed_condition_ids=("cond-00",),
        event_kind="supplemental_report",
        revision_kind="unchanged_additional_reasoning",
        responds_to_opinion_id="opn-01",
        examination_performed=False,
        revision_rationale="the additional records confirm the same allocation",
    )
    base_row = _assertion("app-01", opinion_id="opn-01", condition_ids=("cond-00",))
    response_row = _assertion("app-02", opinion_id="opn-02", condition_ids=("cond-00",))
    return replace(
        plan,
        medical_assertions=_ledger(opinions=(base, response), assertions=(base_row, response_row)),
    )


def _m3_complete_scenario() -> dict[str, Any]:
    """The A1-R6 fixture: every optional AJC-61 field, plus the M3 vocabulary.

    Exercises non-default psych classifications, AOE/COE finding and rationale,
    base/supplemental/deposition opinion events, revision kinds, all five
    disposition classes (adopted ``ctn-01`` / rejected ``ctn-02`` / deferred
    ``ctn-03`` / concurred ``ctn-04`` / unaddressed ``ctn-05``), and explicit
    contention-document bindings — none of which may reach channel ``1.0.0``.
    """
    return {
        "medical_history": {
            "sample_conditions": False,
            "conditions": [
                {
                    "label": "nonindustrial lumbar degenerative disease",
                    "origin": "nonindustrial",
                    "body_part": "lumbar_spine",
                    "icd10": "M51.36",
                    "severity": "moderate",
                    "trajectory": "progressive",
                    "symptomatic_before_doi": True,
                    "billing_coded": True,
                },
                {
                    "label": "post-traumatic stress disorder",
                    "body_system": "psychiatric",
                    "body_part": "psyche",
                    "origin": "mixed",
                    "severity": "moderate",
                    "symptomatic_before_doi": False,
                    "psych_injury_kind": "compensable_consequence",
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
                    "resolution_type": "stipulated_award",
                    "resolution_date": "2016-02-01",
                    "award": {
                        "body_parts": ["lumbar_spine"],
                        "pd_percent": 12,
                        "award_date": "2016-02-01",
                        "conclusively_presumed": True,
                    },
                }
            ],
        },
        "medical_assertions": {
            "sample_assertions": False,
            "contentions": [
                {
                    "id": "ctn-01",
                    "claim_type": "industrial_causation",
                    "party": "applicant",
                    "position": "affirm",
                    "target_condition_id": "cond-00",
                    "target_body_part": "lumbar_spine",
                    "rationale": "the lumbar condition arose from the industrial injury",
                },
                {
                    "id": "ctn-02",
                    "claim_type": "apportionment_defense",
                    "party": "defense",
                    "position": "affirm",
                    "target_prior_claim_id": "prior-00",
                    "target_prior_award_id": "prior-00-award",
                    "doctrine_hooks": ["lc4664_prior_award"],
                    "rationale": "the prior stipulated award conclusively presumes",
                    "groundings": [
                        {
                            "hook": "lc4664_prior_award",
                            "prior_award_id": "prior-00-award",
                        }
                    ],
                },
                {
                    "id": "ctn-03",
                    "claim_type": "compensable_consequence",
                    "party": "applicant",
                    "position": "affirm",
                    "target_condition_id": "cond-00",
                    "treatment_causation": "contributing_cause",
                    "requested_apportionment": "apply",
                    "doctrine_hooks": ["hikida_treatment_carveout"],
                    "rationale": "industrial treatment contributed to the disability",
                },
                {
                    "id": "ctn-04",
                    "claim_type": "psych_add_on",
                    "party": "applicant",
                    "position": "affirm",
                    "target_condition_id": "cond-01",
                    "target_body_part": "psyche",
                    "psych_injury_kind": "direct",
                    "rationale": "the psychiatric injury flows directly from the event",
                },
                {
                    "id": "ctn-05",
                    "claim_type": "aggravation",
                    "party": "applicant",
                    "position": "affirm",
                    "target_condition_id": "cond-00",
                    "rationale": "the injury aggravated the preexisting condition",
                },
            ],
            "medical_opinions": [
                {
                    "id": "opn-01",
                    "author_role": "ptp",
                    "report_stage": "interim",
                    "report_date": "2022-09-15",
                    "apportionment_state": "deferred",
                    "examination_performed": True,
                    "reviewed_condition_ids": ["cond-00"],
                    "aoe_coe_finding": "industrial",
                    "aoe_coe_rationale": (
                        "the treatment course and mechanism support industrial causation"
                    ),
                    "psych_injury_kind": "direct",
                    "rationale": "treatment course reviewed; causation addressed",
                },
                {
                    "id": "opn-02",
                    "author_role": "qme",
                    "report_stage": "final",
                    "report_date": "2023-06-01",
                    "apportionment_state": "determined",
                    "determination_kind": "allocated",
                    "determination_rationale": (
                        "the split follows the imaging severity and prior award"
                    ),
                    "examination_performed": True,
                    "reviewed_condition_ids": ["cond-00", "cond-01"],
                    "reviewed_prior_claim_ids": ["prior-00"],
                    "reviewed_prior_award_ids": ["prior-00-award"],
                    "endorses_contention_ids": ["ctn-01"],
                    "rejects_contention_ids": ["ctn-02"],
                    "concurs_with_contention_ids": ["ctn-04"],
                    "defers_contention_ids": ["ctn-03"],
                    "aoe_coe_finding": "industrial",
                    "aoe_coe_rationale": (
                        "records, examination and mechanism reviewed to reasonable "
                        "medical probability"
                    ),
                    "psych_injury_kind": "compensable_consequence",
                    "rationale": "examined the applicant and reviewed the record",
                },
                {
                    # R37 (enforced at R77 step 4): a revised_apportionment
                    # response changes ONLY the apportionment family — it
                    # restates the predecessor's disposition results, AOE/COE
                    # and psych classification unchanged.
                    "id": "opn-03",
                    "author_role": "qme",
                    "report_stage": "final",
                    "report_date": "2023-11-01",
                    "apportionment_state": "determined",
                    "determination_kind": "allocated",
                    "determination_rationale": "the revised split follows the new records",
                    "examination_performed": False,
                    "event_kind": "supplemental_report",
                    "revision_kind": "revised_apportionment",
                    "reviewed_condition_ids": ["cond-00", "cond-01"],
                    "reviewed_prior_claim_ids": ["prior-00"],
                    "responds_to_opinion_id": "opn-02",
                    "supersedes_opinion_id": "opn-02",
                    "endorses_contention_ids": ["ctn-01"],
                    "rejects_contention_ids": ["ctn-02"],
                    "concurs_with_contention_ids": ["ctn-04"],
                    "defers_contention_ids": ["ctn-03"],
                    "aoe_coe_finding": "industrial",
                    "aoe_coe_rationale": (
                        "records, examination and mechanism reviewed to reasonable "
                        "medical probability"
                    ),
                    "psych_injury_kind": "compensable_consequence",
                    "rationale": "the newly produced records were reviewed",
                    "revision_rationale": (
                        "newly produced imaging changes the nonindustrial share"
                    ),
                },
                {
                    # R37: unchanged_additional_reasoning changes NOTHING —
                    # same dispositions, AOE/COE, psych classification,
                    # apportionment state/kind and percentages as opn-03.
                    "id": "opn-04",
                    "author_role": "qme",
                    "report_stage": "final",
                    "report_date": "2024-03-01",
                    "apportionment_state": "determined",
                    "determination_kind": "allocated",
                    "determination_rationale": "the percentages stand as previously stated",
                    "examination_performed": False,
                    "event_kind": "deposition",
                    "revision_kind": "unchanged_additional_reasoning",
                    "reviewed_condition_ids": ["cond-00"],
                    "responds_to_opinion_id": "opn-03",
                    "endorses_contention_ids": ["ctn-01"],
                    "rejects_contention_ids": ["ctn-02"],
                    "concurs_with_contention_ids": ["ctn-04"],
                    "defers_contention_ids": ["ctn-03"],
                    "aoe_coe_finding": "industrial",
                    "aoe_coe_rationale": (
                        "records, examination and mechanism reviewed to reasonable "
                        "medical probability"
                    ),
                    "psych_injury_kind": "compensable_consequence",
                    "rationale": (
                        "testimony under oath restates the written conclusions with "
                        "additional reasoning"
                    ),
                },
            ],
            "apportionment_assertions": [
                {
                    "id": "app-01",
                    "opinion_id": "opn-02",
                    "body_part": "lumbar_spine",
                    "industrial_percent": 80,
                    "nonindustrial_percent": 20,
                    "basis_kinds": ["preexisting_degenerative_pathology"],
                    "condition_ids": ["cond-00"],
                    "description": "chronic lumbar disability limiting weight-bearing",
                    "disability_causation_stated": True,
                    "reasonable_medical_probability": True,
                    "causal_rationale": (
                        "degenerative pathology contributes to present disability"
                    ),
                    "percentage_rationale": "the share reflects the imaging severity",
                },
                {
                    "id": "app-02",
                    "opinion_id": "opn-02",
                    "body_part": "shoulder",
                    "industrial_percent": 90,
                    "nonindustrial_percent": 10,
                    "basis_kinds": ["lc4664_prior_award"],
                    "prior_claim_ids": ["prior-00"],
                    "prior_award_ids": ["prior-00-award"],
                    "description": "overlap with the previously awarded disability",
                    "disability_causation_stated": True,
                    "reasonable_medical_probability": True,
                    "causal_rationale": "the prior award overlaps the present disability",
                    "percentage_rationale": "the overlap is small but present",
                    "prior_award_analysis": (
                        "the section 4664(b) presumption is analyzed separately from "
                        "section 4663 causation"
                    ),
                    "groundings": [
                        {
                            "hook": "lc4664_prior_award",
                            "prior_award_id": "prior-00-award",
                        }
                    ],
                },
                {
                    "id": "app-03",
                    "opinion_id": "opn-03",
                    "body_part": "lumbar_spine",
                    "industrial_percent": 70,
                    "nonindustrial_percent": 30,
                    "basis_kinds": [
                        "preexisting_degenerative_pathology",
                        "industrial_treatment",
                    ],
                    "condition_ids": ["cond-00"],
                    "linked_contention_id": "ctn-03",
                    "description": "revised lumbar split after the new records",
                    "disability_causation_stated": True,
                    "reasonable_medical_probability": True,
                    "causal_rationale": ("the new imaging shows greater degenerative contribution"),
                    "percentage_rationale": "the revised share follows the new imaging",
                    "revised_from_percent": 20,
                    "revision_rationale": (
                        "newly produced imaging changes the nonindustrial share"
                    ),
                },
                {
                    # R37: the unchanged deposition row keeps opn-03's exact
                    # percentages AND basis set, and claims no revision.
                    "id": "app-04",
                    "opinion_id": "opn-04",
                    "body_part": "lumbar_spine",
                    "industrial_percent": 70,
                    "nonindustrial_percent": 30,
                    "basis_kinds": [
                        "preexisting_degenerative_pathology",
                        "industrial_treatment",
                    ],
                    "condition_ids": ["cond-00"],
                    "linked_contention_id": "ctn-03",
                    "description": "the deposition restates the supplemental split",
                    "disability_causation_stated": True,
                    "reasonable_medical_probability": True,
                    "causal_rationale": "the causal analysis stands as written",
                    "percentage_rationale": "the percentages stand as written",
                    "psych_exception_analysis": "none_applies",
                },
            ],
            "contention_documents": [
                {
                    "id": "cdoc-01",
                    "document_kind": "advocacy",
                    "target_medical_opinion_id": "opn-02",
                    "actor_party": "applicant",
                    "spoken_contention_ids": ["ctn-01", "ctn-03"],
                    "doc_date": "2023-04-01",
                },
                {
                    "id": "cdoc-02",
                    "document_kind": "objection",
                    "target_medical_opinion_id": "opn-02",
                    "actor_party": "defense",
                    "spoken_contention_ids": ["ctn-02"],
                    "defense_contest_theories": [
                        "insufficient_investigation",
                        "lack_of_substantial_medical_evidence",
                    ],
                },
                {
                    "id": "cdoc-03",
                    "document_kind": "supplemental_report",
                    "medical_opinion_id": "opn-03",
                    "target_medical_opinion_id": "opn-02",
                },
            ],
        },
    }


def _m3_seed_body(case_id: str) -> dict[str, Any]:
    body = _seed_body(case_id, scenario=_m3_complete_scenario(), doi="2021-06-14")
    body["injury"]["body_parts"] = [
        {"part": "lumbar_spine"},
        {"part": "shoulder"},
        {"part": "psyche"},
    ]
    body["lifecycle"]["ur_dispute"] = {
        "enabled": True,
        "decision": "upheld",
        "imr": True,
        "imr_outcome": "upheld",
        "imr_application": {
            "disputed_treatment": "lumbar epidural steroid injection",
            "diagnosis_icd10": "M54.5",
            "ur_determination_attached": True,
            "supporting_record_subtypes": ["TREATING_PHYSICIAN_REPORT_PR2"],
            "clinical_rebuttal": "the denial misreads the current imaging",
            "mtus_citations": ["MTUS 2016, Low Back Complaints"],
        },
    }
    return body


def _m3_plan(case_id: str = "assertions-m3-truth") -> Any:
    return build_case_plan(parse_case_seed(_m3_seed_body(case_id)), case_number=1)


def _exercise_m3_internal_state(plan: Any) -> None:
    """Construct every step-2 internal M3 object the serializer must ignore.

    A1-R6's fixture bullets beyond the ledger: contention-document bindings
    with contest theories, document-scoped medical-story facts, and grounded /
    conclusory / sampled-sparse IMR state. The planner does not carry these
    yet (their derivations are later build steps), so the test constructs the
    objects directly — the serializer's input plan and the anti-expansion
    scans prove none of this vocabulary can reach channel ``1.0.0``.
    """
    import datetime as real_dt

    from wc_caseload_engine.medical_assertions import (
        ContentionDocumentBinding,
        MedicalAssertionPlan,
    )
    from wc_caseload_engine.medical_story import (
        DocumentMedicalStory,
        ImrApplicationContent,
        MedicalStoryPlan,
        MedicalUrPlan,
        StoryContention,
        StoryDemographics,
        StoryMedicalOpinion,
        StoryRecordReference,
    )

    ledger = plan.medical_assertions
    bindings = (
        ContentionDocumentBinding(
            id="cdoc-01",
            document_kind="advocacy",
            target_medical_opinion_id="opn-02",
            spoken_contention_ids=("ctn-01", "ctn-03"),
            actor_party="applicant",
            proposed_date=real_dt.date(2023, 4, 1),
            source="explicit",
        ),
        ContentionDocumentBinding(
            id="cdoc-02",
            document_kind="objection",
            subtype="ADVOCACY_LETTERS_PTP_QME_AME",
            template_subtype="OBJECTION_TO_QME_AME_REPORT",
            target_medical_opinion_id="opn-02",
            spoken_contention_ids=("ctn-02",),
            actor_party="defense",
            defense_contest_theories=(
                "insufficient_investigation",
                "lack_of_substantial_medical_evidence",
            ),
            source="explicit",
        ),
        ContentionDocumentBinding(
            id="cdoc-03",
            document_kind="supplemental_report",
            medical_opinion_id="opn-03",
            target_medical_opinion_id="opn-02",
            source="required_opinion",
        ),
    )
    assertion_plan = MedicalAssertionPlan(ledger=ledger, contention_documents=bindings)
    assert assertion_plan.ledger is ledger
    assert len(assertion_plan.contention_documents) == 3

    grounded = ImrApplicationContent(
        disputed_treatment="lumbar epidural steroid injection",
        diagnosis_icd10="M54.5",
        ur_determination_attached=True,
        supporting_record_subtypes=("TREATING_PHYSICIAN_REPORT_PR2",),
        clinical_rebuttal="the denial misreads the current imaging",
        mtus_citations=("MTUS 2016, Low Back Complaints",),
        target_denial_subtype="MEDICAL_TREATMENT_DENIAL_UR",
        target_denial_date=real_dt.date(2023, 3, 1),
    )
    conclusory = ImrApplicationContent(
        disputed_treatment="lumbar epidural steroid injection",
        clinical_rebuttal="the treatment is necessary",
        target_denial_subtype="MEDICAL_TREATMENT_DENIAL_UR",
        target_denial_date=real_dt.date(2023, 3, 1),
    )
    sampled_sparse = ImrApplicationContent(
        target_denial_subtype="MEDICAL_TREATMENT_DENIAL_UR",
        target_denial_date=real_dt.date(2023, 3, 1),
    )
    ur_plan = MedicalUrPlan(
        effective_decision="upheld",
        decision_was_authored=True,
        imr_requested=True,
        imr_was_authored=True,
        imr_application=grounded,
    )
    assert ur_plan.imr_application is grounded
    assert conclusory.ur_determination_attached is None
    assert sampled_sparse.disputed_treatment is None

    opinion = next(o for o in ledger.medical_opinions if o.id == "opn-03")
    story = DocumentMedicalStory(
        document_index=7,
        subtype="SUPPLEMENTAL_QME_AME_REPORT",
        demographics=StoryDemographics(
            age=44, sex="female", bmi_band="overweight", smoking_status="never"
        ),
        preceding_report=StoryRecordReference(
            document_index=3,
            subtype="QME_COMPREHENSIVE_REPORT",
            title="QME Comprehensive Report",
            doc_date=real_dt.date(2023, 6, 1),
            author_role="physician",
        ),
        contentions=tuple(
            StoryContention(**{name: getattr(c, name) for name in StoryContention.model_fields})
            for c in ledger.contentions
        ),
        medical_opinion=StoryMedicalOpinion(
            **{name: getattr(opinion, name) for name in StoryMedicalOpinion.model_fields}
        ),
    )
    story_plan = MedicalStoryPlan(by_document_index={7: story})
    assert story_plan.by_document_index[7].medical_opinion is not None
    assert story_plan.by_document_index[7].medical_opinion.event_kind == ("supplemental_report")
    for record in (
        *story.contentions,
        story.medical_opinion,
    ):
        assert "quality" not in type(record).model_fields


def test_assertions_channel_1_round_trips_the_complete_ajc61_projection() -> None:
    """A1-R6: channel 1.0.0 round-trips exactly the AJC-61 projection.

    The complete M3 plan serializes; each emitted collection equals an
    independently constructed AJC-61 projection; the parsed ledger, projected
    through the same frozen vocabulary, equals the source projection. Parsing
    runs digest verification, the shared incoherence validator and quality
    rederivation. Omitted M3 fields and bindings are NOT required to
    round-trip, and no complete-M3 ``model_dump()`` comparison happens here.
    """
    plan = _m3_plan()
    ledger = plan.medical_assertions
    assert ledger is not None
    _exercise_m3_internal_state(plan)
    truth = json.loads(json.dumps(build_case_truth_manifest(plan)))
    channel = truth["channels"]["assertions"]
    v1_ledger = _v1_graded_ledger(plan)

    _assert_channel_collections_match_ajc61_projection(channel, v1_ledger)
    assert channel["ledgerDigest"] == assertion_ledger_digest(channel)

    parsed = medical_assertions_from_truth(truth)
    assert parsed is not None
    _context, _projection, parsed_ledger = parsed
    for source_items, parsed_items, fields in (
        (v1_ledger.contentions, parsed_ledger.contentions, AJC61_CONTENTION_FIELDS),
        (
            v1_ledger.medical_opinions,
            parsed_ledger.medical_opinions,
            AJC61_MEDICAL_OPINION_FIELDS,
        ),
        (
            v1_ledger.apportionment_assertions,
            parsed_ledger.apportionment_assertions,
            AJC61_APPORTIONMENT_ASSERTION_FIELDS,
        ),
    ):
        assert [_ajc61_projection(item, fields) for item in parsed_items] == [
            _ajc61_projection(item, fields) for item in source_items
        ]


def test_v1_and_v2_rederive_response_quality_under_their_exact_version_contracts() -> None:
    """R98: default-v1/v2-opt-in differ only in assertions on this plan."""
    plan = _m4_response_plan()
    document_snapshot = tuple((item.index, item.subtype, item.doc_date) for item in plan.documents)
    default_payload = build_case_truth_manifest(plan)
    v1_payload = build_case_truth_manifest(plan, truth_manifest_version=1)
    v2_payload = build_case_truth_manifest(plan, truth_manifest_version=2)

    assert json.dumps(default_payload, separators=(",", ":")) == json.dumps(
        v1_payload, separators=(",", ":")
    )
    v1_channel = v1_payload["channels"]["assertions"]
    v2_channel = v2_payload["channels"]["assertions"]
    assert default_payload["channels"]["assertions"]["channelVersion"] == "1.0.0"
    assert v1_channel["channelVersion"] == "1.0.0"
    assert v2_channel["channelVersion"] == "2.0.0"
    assert "money" in v1_payload["channels"]
    assert json.dumps(v1_payload["channels"]["money"], separators=(",", ":")) == (
        json.dumps(v2_payload["channels"]["money"], separators=(",", ":"))
    )
    assert json.dumps(v1_channel, separators=(",", ":")) != json.dumps(
        v2_channel, separators=(",", ":")
    )
    assert [row["quality"] for row in v1_channel["apportionmentAssertions"]] == [
        "supported",
        "thin",
    ]
    assert [row["quality"] for row in v2_channel["apportionmentAssertions"]] == [
        "supported",
        "supported",
    ]
    assert [row["quality"] for row in v1_channel["medicalOpinions"]] == [
        "supported",
        "thin",
    ]
    assert [row["quality"] for row in v2_channel["medicalOpinions"]] == [
        "supported",
        "supported",
    ]

    parsed_v1 = medical_assertions_from_truth(v1_payload)
    parsed_v2 = medical_assertions_from_truth(v2_payload)
    assert parsed_v1 is not None and parsed_v2 is not None
    assert parsed_v1[2].apportionment_assertions[1].quality == "thin"
    assert parsed_v2[2].apportionment_assertions[1].quality == "supported"
    assert (
        tuple((item.index, item.subtype, item.doc_date) for item in plan.documents)
        == document_snapshot
    )
    assert v2_channel["contentionDocuments"] == []

    compatible_minor = copy.deepcopy(v2_payload)
    compatible_minor["channels"]["assertions"]["channelVersion"] = "2.1.0"
    compatible_minor["channels"]["assertions"]["ledgerDigest"] = assertion_ledger_digest(
        compatible_minor["channels"]["assertions"]
    )
    try:
        parsed_minor = medical_assertions_from_truth(compatible_minor)
    except ValueError as error:
        raise AssertionError(f"compatible assertions minor did not normalize: {error}") from error
    assert parsed_minor is not None
    assert parsed_minor[2] == parsed_v2[2]


def test_assertions_channel_1_serializes_only_the_frozen_ajc61_projection() -> None:
    """A1-R7: the anti-expansion witness for the frozen 1.0.0 channel.

    Declares its expected tuples independently, asserts them equal to the
    production constants, then proves the emitted channel carries exactly the
    frozen key vocabulary — an unrestricted ``model_dump(mode="json",
    exclude_none=True)`` serializer reddens this on the M3 fixture.
    """
    from wc_caseload_engine import truth_manifest as tm

    assert tm.ASSERTIONS_V1_CASE_CHANNEL_KEYS == AJC61_CASE_CHANNEL_KEYS
    assert tm.ASSERTIONS_V1_VALIDATION_CONTEXT_KEYS == AJC61_VALIDATION_CONTEXT_KEYS
    assert (
        tm.ASSERTIONS_V1_OPTIONAL_VALIDATION_CONTEXT_KEYS == AJC61_OPTIONAL_VALIDATION_CONTEXT_KEYS
    )
    assert tm.ASSERTIONS_V1_MEDICAL_HISTORY_KEYS == AJC61_MEDICAL_HISTORY_KEYS
    assert tm.ASSERTIONS_V1_CONDITION_FIELDS == AJC61_CONDITION_FIELDS
    assert tm.ASSERTIONS_V1_PRIOR_CLAIM_FIELDS == AJC61_PRIOR_CLAIM_FIELDS
    assert tm.ASSERTIONS_V1_PRIOR_AWARD_FIELDS == AJC61_PRIOR_AWARD_FIELDS
    assert tm.ASSERTIONS_V1_CONTENTION_FIELDS == AJC61_CONTENTION_FIELDS
    assert tm.ASSERTIONS_V1_MEDICAL_OPINION_FIELDS == AJC61_MEDICAL_OPINION_FIELDS
    assert tm.ASSERTIONS_V1_APPORTIONMENT_ASSERTION_FIELDS == AJC61_APPORTIONMENT_ASSERTION_FIELDS
    assert tm.ASSERTIONS_V1_CASELOAD_CHANNEL_KEYS == AJC61_CASELOAD_CHANNEL_KEYS
    assert tm.ASSERTIONS_V1_CASELOAD_CASE_KEYS == AJC61_CASELOAD_CASE_KEYS

    plan = _m3_plan()
    ledger = plan.medical_assertions
    assert ledger is not None
    v1_ledger = _v1_graded_ledger(plan)
    truth = json.loads(json.dumps(build_case_truth_manifest(plan)))
    channel = truth["channels"]["assertions"]

    assert tuple(channel) == AJC61_CASE_CHANNEL_KEYS
    context_keys = set(channel["validationContext"])
    assert set(AJC61_VALIDATION_CONTEXT_KEYS) <= context_keys
    assert context_keys <= set(AJC61_VALIDATION_CONTEXT_KEYS) | set(
        AJC61_OPTIONAL_VALIDATION_CONTEXT_KEYS
    )
    assert tuple(channel["medicalHistory"]) == AJC61_MEDICAL_HISTORY_KEYS
    for record in channel["medicalHistory"]["conditions"]:
        assert set(record) <= {_camel_case(f) for f in AJC61_CONDITION_FIELDS}
    for record in channel["medicalHistory"]["priorClaims"]:
        assert set(record) <= {_camel_case(f) for f in AJC61_PRIOR_CLAIM_FIELDS}
        if "award" in record:
            assert set(record["award"]) <= {_camel_case(f) for f in AJC61_PRIOR_AWARD_FIELDS}

    for emitted_items, source_items, fields in (
        (channel["contentions"], v1_ledger.contentions, AJC61_CONTENTION_FIELDS),
        (
            channel["medicalOpinions"],
            v1_ledger.medical_opinions,
            AJC61_MEDICAL_OPINION_FIELDS,
        ),
        (
            channel["apportionmentAssertions"],
            v1_ledger.apportionment_assertions,
            AJC61_APPORTIONMENT_ASSERTION_FIELDS,
        ),
    ):
        allowed = {_camel_case(field) for field in fields}
        for emitted, source in zip(emitted_items, source_items, strict=True):
            assert emitted == _ajc61_projection(source, fields)
            assert set(emitted) <= allowed
            outside_allowlist = {
                _camel_case(name) for name in type(source).model_fields if name not in fields
            }
            assert not (set(emitted) & outside_allowlist), sorted(set(emitted) & outside_allowlist)

    channel_text = json.dumps(channel)
    for name in M3_FORBIDDEN_CHANNEL_FIELDS:
        for spelling in (name, _camel_case(name)):
            assert f'"{spelling}"' not in channel_text, spelling

    truth_dir = Path(__file__).parent
    result = SimpleNamespace(
        case_id=plan.seed.case_id,
        plan=plan,
        truth_path=truth_dir / "unused.truth.json",
    )
    rollup = json.loads(json.dumps(build_caseload_truth_manifest("a1-anti-expansion", [result])))
    caseload_channel = rollup["channels"]["assertions"]
    assert tuple(caseload_channel) == AJC61_CASELOAD_CHANNEL_KEYS
    for entry in caseload_channel["cases"]:
        assert tuple(entry) == AJC61_CASELOAD_CASE_KEYS
    caseload_text = json.dumps(caseload_channel)
    for name in M3_FORBIDDEN_CHANNEL_FIELDS:
        for spelling in (name, _camel_case(name)):
            assert f'"{spelling}"' not in caseload_text, spelling

    again = json.loads(json.dumps(build_case_truth_manifest(_m3_plan())))
    assert again["channels"]["assertions"] == channel
    assert again["channels"]["assertions"]["ledgerDigest"] == channel["ledgerDigest"]


def test_assertion_bearing_case_keeps_envelope_1_and_uses_assertions_channel_1() -> None:
    payload = _assertion_truth()
    assert payload["schemaVersion"] == "1.0.0"
    assert payload["channels"]["assertions"].get("channelVersion") == "1.0.0"
    assert ASSERTIONS_CHANNEL_VERSION == "1.0.0"


def test_assertion_absent_case_remains_byte_identical_envelope_1() -> None:
    """R98 Form C: absent v1/v2 agree; a response-chain neighbor differs."""
    plan = _plan("assertions-absent", scenario={"medical_history": {}})
    default_truth = build_case_truth_manifest(plan)
    v1_truth = build_case_truth_manifest(plan, truth_manifest_version=1)
    v2_truth = build_case_truth_manifest(plan, truth_manifest_version=2)
    assert default_truth["schemaVersion"] == "1.0.0"
    assert "assertions" not in default_truth["channels"]
    assert json.dumps(default_truth, separators=(",", ":")) == json.dumps(
        v1_truth, separators=(",", ":")
    )
    assert json.dumps(v1_truth, separators=(",", ":")) == json.dumps(
        v2_truth, separators=(",", ":")
    )

    positive = _m4_response_plan("assertions-present-neighbor")
    positive_v1 = build_case_truth_manifest(positive, truth_manifest_version=1)
    positive_v2 = build_case_truth_manifest(positive, truth_manifest_version=2)
    assert positive_v1["channels"]["assertions"]["channelVersion"] == "1.0.0"
    assert positive_v2["channels"]["assertions"]["channelVersion"] == "2.0.0"
    assert positive_v1["channels"]["assertions"] != positive_v2["channels"]["assertions"]


def test_read_truth_manifest_accepts_every_writer_emitted_shape(tmp_path: Path) -> None:
    bearing = tmp_path / "bearing.truth.json"
    bearing.write_text(json.dumps(_assertion_truth()), encoding="utf-8")
    assert read_truth_manifest(bearing)["channels"]["assertions"]

    absent_plan = _plan("assertions-absent", scenario={"medical_history": {}})
    absent = tmp_path / "absent.truth.json"
    absent.write_text(json.dumps(build_case_truth_manifest(absent_plan)), encoding="utf-8")
    assert "assertions" not in read_truth_manifest(absent)["channels"]


def test_money_facts_from_truth_accepts_every_writer_emitted_shape() -> None:
    scenario = copy.deepcopy(_ASSERTION_SCENARIO)
    scenario["wages"] = {"pattern": "regular", "base_weekly_wage": 1500.0}
    plan = _plan("assertions-money", scenario=scenario)
    truth = json.loads(json.dumps(build_case_truth_manifest(plan)))
    facts = money_facts_from_truth(truth)
    assert facts is not None
    assert money_facts_from_truth(_assertion_truth()) is None


def test_legacy_v1_without_assertions_remains_valid() -> None:
    legacy = {
        "schemaVersion": "1.0.0",
        "kind": "case",
        "audience": "analyzer-scorer",
        "leakageRule": (
            "Scorer-only ground truth; never use this artifact as an input to document analysis."
        ),
        "caseId": "legacy",
        "provenance": {"generator": "wc-synthetic-caseload-engine@0.0.0"},
        "channels": {},
    }
    assert medical_assertions_from_truth(legacy) is None
    assert money_facts_from_truth(legacy) is None


def test_assertions_channel_rejects_an_unknown_major(tmp_path: Path) -> None:
    payload = _assertion_truth()
    payload["channels"]["assertions"]["channelVersion"] = "3.0.0"
    with pytest.raises(TruthManifestError, match="unsupported assertions channel"):
        medical_assertions_from_truth(payload)
    path = tmp_path / "major.truth.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(TruthManifestError, match="unsupported assertions channel"):
        read_truth_manifest(path)


def _fake_result(case_id: str, plan: Any, tmp_path: Path) -> Any:
    truth_dir = tmp_path / TRUTH_DIR
    truth_dir.mkdir(parents=True, exist_ok=True)
    truth_path = truth_dir / f"{case_id}.truth.json"
    truth_path.write_text(json.dumps(build_case_truth_manifest(plan)), encoding="utf-8")
    return SimpleNamespace(case_id=case_id, plan=plan, truth_path=truth_path)


def test_mixed_caseload_keeps_every_envelope_at_1_and_indexes_assertions(
    tmp_path: Path,
) -> None:
    from wc_caseload_engine.truth_manifest import build_caseload_truth_manifest

    bearing = _fake_result("bearing", _assertion_plan("bearing"), tmp_path)
    absent = _fake_result("absent", _plan("absent", scenario={"medical_history": {}}), tmp_path)
    rollup = build_caseload_truth_manifest("mixed", [bearing, absent])
    assert rollup["schemaVersion"] == "1.0.0"
    channel = rollup["channels"]["assertions"]
    assert channel["channelVersion"] == "1.0.0"
    assert channel["caseCount"] == 2
    assert channel["assertionCaseCount"] == 1
    assert [entry["caseId"] for entry in channel["cases"]] == ["bearing"]
    # The absent case keeps its v1 shape: no assertions channel in its file.
    absent_payload = json.loads(absent.truth_path.read_text(encoding="utf-8"))
    assert "assertions" not in absent_payload["channels"]


def test_assertion_rollup_counts_match_case_channels(tmp_path: Path) -> None:
    from wc_caseload_engine.truth_manifest import build_caseload_truth_manifest

    bearing = _fake_result("bearing", _assertion_plan("bearing"), tmp_path)
    rollup = build_caseload_truth_manifest("counted", [bearing])
    channel = rollup["channels"]["assertions"]
    ledger = bearing.plan.medical_assertions
    v1_ledger = _v1_graded_ledger(bearing.plan)
    assert channel["counts"] == {
        "contentions": len(ledger.contentions),
        "medicalOpinions": len(ledger.medical_opinions),
        "apportionmentAssertions": len(ledger.apportionment_assertions),
    }
    assert channel["qualityCounts"] == v1_ledger.quality_counts()
    assert sum(channel["apportionmentStateCounts"].values()) == len(ledger.medical_opinions)
    assert set(channel["determinationKindCounts"]) == {
        "allocated",
        "noNonindustrialShare",
        "unableToApproximate",
    }


def test_assertion_rollup_uses_independent_case_records(tmp_path: Path) -> None:
    from wc_caseload_engine.truth_manifest import build_caseload_truth_manifest

    scenario = copy.deepcopy(_ASSERTION_SCENARIO)
    scenario["wages"] = {"pattern": "regular", "base_weekly_wage": 1500.0}
    bearing = _fake_result("bearing", _plan("bearing", scenario=scenario), tmp_path)
    rollup = build_caseload_truth_manifest("aliasing", [bearing])
    top_cases = rollup["cases"]
    money_cases = rollup["channels"]["money"]["cases"]
    assertion_cases = rollup["channels"]["assertions"]["cases"]
    assert assertion_cases is not top_cases
    assert assertion_cases is not money_cases
    assert top_cases is not money_cases
    for one, other in (
        (assertion_cases, top_cases),
        (assertion_cases, money_cases),
        (money_cases, top_cases),
    ):
        assert all(entry is not record for entry in one for record in other)
    before = json.dumps(money_cases, sort_keys=True)
    assertion_cases[0]["contentionCount"] = 99
    assert json.dumps(money_cases, sort_keys=True) == before
    # Record-level: mutating a money record must not move the top-level index.
    top_before = json.dumps(top_cases, sort_keys=True)
    money_cases[0]["averageWeeklyWage"] = "0.01"
    assert json.dumps(top_cases, sort_keys=True) == top_before


def test_output_validator_rejects_tampered_assertion_quality_after_digest_recomputed() -> None:
    payload = _assertion_truth()
    channel = payload["channels"]["assertions"]
    original = channel["contentions"][0]["quality"]
    channel["contentions"][0]["quality"] = "supported" if original != "supported" else "thin"
    channel["ledgerDigest"] = assertion_ledger_digest(channel)
    with pytest.raises(TruthManifestError, match="does not match the rederived grade"):
        medical_assertions_from_truth(payload)


def test_output_validator_rejects_tampered_assertion_reference_after_digest_recomputed() -> None:
    payload = _assertion_truth()
    channel = payload["channels"]["assertions"]
    channel["contentions"][0]["targetConditionId"] = "cond-77"
    channel["ledgerDigest"] = assertion_ledger_digest(channel)
    with pytest.raises(TruthManifestError, match="references unknown condition 'cond-77'"):
        medical_assertions_from_truth(payload)


def test_output_validator_rejects_tampered_assertion_digest_with_exact_literal() -> None:
    payload = _assertion_truth()
    payload["channels"]["assertions"]["contentions"][0]["rationale"] = "edited later"
    with pytest.raises(TruthManifestError) as raised:
        medical_assertions_from_truth(payload)
    assert str(raised.value) == LEDGER_DIGEST_MISMATCH


def test_assertions_ledger_digest_covers_canonical_channel_payload() -> None:
    payload = _assertion_truth()
    channel = payload["channels"]["assertions"]
    baseline = assertion_ledger_digest(channel)
    # The two excluded keys move nothing.
    variant = dict(channel)
    variant["channelVersion"] = "9.9.9"
    variant["ledgerDigest"] = "0" * 64
    assert assertion_ledger_digest(variant) == baseline
    # Every covered surface moves it: context, projection, semantics, quality.
    for mutate in (
        lambda c: c["validationContext"].__setitem__("targetStage", "intake"),
        lambda c: c["medicalHistory"]["conditions"][0].__setitem__("severity", "severe"),
        lambda c: c["contentions"][0].__setitem__("rationale", "different"),
        lambda c: c["contentions"][0].__setitem__("quality", "thin"),
    ):
        variant = json.loads(json.dumps(channel))
        mutate(variant)
        assert assertion_ledger_digest(variant) != baseline


def test_truth_assertion_projection_omits_redacted_identity_fields() -> None:
    channel_text = json.dumps(_assertion_truth()["channels"]["assertions"])
    for token in (
        "archetype",
        "bmiBand",
        "smokingStatus",
        '"sex"',
        "employer",
        '"age"',
        "billingCoded",
        "icd10",
    ):
        assert token not in channel_text, token


def test_truth_projection_round_trips_every_evidence_and_quality_input() -> None:
    from wc_caseload_engine.medical_assertions import (
        assertion_context,
        project_medical_history,
    )

    plan = _assertion_plan()
    context = assertion_context(plan.seed, plan.timeline)
    plan_projection = project_medical_history(plan.medical_history, context.current_body_parts)
    parsed = medical_assertions_from_truth(_assertion_truth())
    assert parsed is not None
    truth_context, truth_projection, _ledger = parsed
    assert truth_context == context
    assert truth_projection == plan_projection


def test_plan_and_truth_paths_use_one_assertion_validation_context_and_rule_implementation() -> None:  # noqa: E501
    import wc_caseload_engine.medical_assertions as assertion_module
    import wc_caseload_engine.planner as planner_module
    import wc_caseload_engine.truth_manifest as truth_module

    assert truth_module.validate_medical_assertions is assertion_module.validate_medical_assertions
    assert (
        planner_module.validate_medical_assertions is assertion_module.validate_medical_assertions
    )
    assert truth_module.grade_ledger is assertion_module.grade_ledger
    assert truth_module.AssertionValidationContext is assertion_module.AssertionValidationContext


def test_validate_out_assertions_path_requires_no_substrate_checkout_or_import_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The recorded payload carries every input the rules need: the assertions
    validation path runs with the substrate checkout absent and every
    substrate-access seam trapped."""
    payload = _assertion_truth()  # built once, while the substrate exists

    import wc_caseload_engine.substrate as substrate_module

    def fail_access(*args: object, **kwargs: object):
        pytest.fail("assertions truth validation reached a substrate-access call")

    monkeypatch.setattr(substrate_module, "find_substrate", lambda *a, **k: None)
    monkeypatch.setattr(substrate_module, "substrate_available", lambda *a, **k: False)
    for name in ("import_substrate", "ensure_substrate"):
        if hasattr(substrate_module, name):
            monkeypatch.setattr(substrate_module, name, fail_access)

    parsed = medical_assertions_from_truth(payload)
    assert parsed is not None
