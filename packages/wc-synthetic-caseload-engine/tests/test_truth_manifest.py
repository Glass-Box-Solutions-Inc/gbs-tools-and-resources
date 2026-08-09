"""AJC-48 truth-manifest contract and lossless money-channel coverage.

These tests build plans rather than documents wherever possible.  The truth
artifact labels decided facts, so rendering paper to prove serialization would
make the contract slower without making it stronger; only the output-tree
boundary test crosses the renderer.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from conftest import requires_substrate
from wc_caseload_engine.manifests import generate_case, validate_output_tree
from wc_caseload_engine.money import money_manifest_block
from wc_caseload_engine.planner import build_case_plan
from wc_caseload_engine.seeds import parse_case_seed
from wc_caseload_engine.truth_manifest import (
    CASELOAD_TRUTH_NAME,
    TRUTH_DIR,
    TruthManifestError,
    build_case_truth_manifest,
    money_facts_from_truth,
    read_truth_manifest,
    write_case_truth_manifest,
    write_caseload_truth_manifest,
)


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
        },
        rng_seed=4304,
    )
    assert complex_plan.money_facts is not None
    assert complex_plan.money_facts.benefits.late_payment_count > 0
    assert complex_plan.money_facts.benefits.gaps
    return regular, explicit, capped, complex_plan


def test_money_channel_round_trips_four_materially_different_plans(
    tmp_path: Path, money_plans: tuple[Any, ...]
) -> None:
    for plan in money_plans:
        path = write_case_truth_manifest(plan, tmp_path)
        reconstructed = money_facts_from_truth(read_truth_manifest(path))
        assert reconstructed == plan.money_facts

    oldest_basis = money_plans[0].money_facts.wages.rate.basis
    assert oldest_basis.effective_from.isoformat() == "0001-01-01"


def test_money_gate_omits_channel_and_reimports_as_none() -> None:
    plan = _plan("truth-no-money", scenario=None, rng_seed=4305)
    document = build_case_truth_manifest(plan)
    assert document["channels"] == {}
    assert money_facts_from_truth(document) is None


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
    assert set(document["provenance"]) == {
        "generator",
        "substrateSha",
        "seedHash",
        "rngSeed",
    }
    serialized = json.dumps(document)
    assert '"generatedAt"' not in serialized
    assert '"timestamp"' not in serialized
    assert first.read_bytes() == second.read_bytes()


def test_published_block_is_the_existing_public_contract(money_plans: tuple[Any, ...]) -> None:
    plan = money_plans[1]
    assert plan.money_facts is not None
    channel = build_case_truth_manifest(plan)["channels"]["money"]
    assert channel["published"] == money_manifest_block(plan.money_facts)


def test_unknown_channel_is_ignored_and_money_major_is_guarded(
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
    assert "1.0.0" in str(raised.value)


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
    assert read_truth_manifest(empty_rollup)["channels"] == {}


@pytest.mark.slow
@requires_substrate
def test_truth_subtree_is_outside_case_and_does_not_confuse_validator(
    tmp_path: Path,
) -> None:
    seed = parse_case_seed(
        _seed_body(
            "truth-boundary",
            scenario=None,
            rng_seed=4307,
            stage="intake",
        )
    )
    truth_dir = tmp_path / TRUTH_DIR
    result = generate_case(seed, tmp_path, truth_dir=truth_dir)

    assert result.truth_path == truth_dir / "truth-boundary.truth.json"
    assert result.truth_path.is_file()
    assert not (result.directory / TRUTH_DIR).exists()
    assert validate_output_tree(tmp_path).ok
