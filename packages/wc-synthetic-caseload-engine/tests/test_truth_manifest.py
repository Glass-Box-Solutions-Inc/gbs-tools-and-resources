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
import shutil
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from conftest import requires_substrate
from wc_caseload_engine.manifests import generate_case, generate_caseload, validate_output_tree
from wc_caseload_engine.money import money_manifest_block
from wc_caseload_engine.planner import build_case_plan
from wc_caseload_engine.seeds import parse_case_seed
from wc_caseload_engine.truth_manifest import (
    CASELOAD_TRUTH_NAME,
    PENALTY_ASSESSMENT_KEY_NAMES,
    SCORER_ONLY_ENVELOPE_KEY_NAMES,
    TRUTH_DIR,
    TruthManifestError,
    build_case_truth_manifest,
    check_truth_dir_is_isolated,
    money_facts_from_truth,
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
    assert oldest_basis.effective_from.isoformat() == "0001-01-01"


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

    compatible = copy.deepcopy(document)
    compatible["channels"]["money"]["channelVersion"] = "1.9.0"
    assert money_facts_from_truth(compatible) == plan.money_facts

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
    tmp_path: Path, money_plans: tuple[Any, ...],
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


def test_additive_1_1_money_channel_keeps_same_major_acceptance(
    money_plans: tuple[Any, ...],
) -> None:
    """A 1.0 contract consumer accepts the additive 1.1 penalty channel by major."""
    plan = money_plans[-1]
    document = build_case_truth_manifest(plan)
    channel = document["channels"]["money"]
    assert channel["channelVersion"] == "1.1.0"
    assert "penalties" in channel
    assert money_facts_from_truth(document) == plan.money_facts

    prior_minor = copy.deepcopy(document)
    prior_minor["channels"]["money"]["channelVersion"] = "1.0.0"
    assert money_facts_from_truth(prior_minor) == plan.money_facts


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
        "assessments[1].amount is" in problem and "product" in problem
        for problem in problems
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
        if (item["source"], item["ordinal"])
        == (assessment["source"], assessment["ordinal"])
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
