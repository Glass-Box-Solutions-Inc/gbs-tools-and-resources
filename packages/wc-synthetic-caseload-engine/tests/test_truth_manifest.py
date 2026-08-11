"""AJC-48 truth-manifest contract and lossless money-channel coverage.

These tests build plans rather than documents wherever possible.  The truth
artifact labels decided facts, so rendering paper to prove serialization would
make the contract slower without making it stronger; only the output-tree
boundary test crosses the renderer.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import copy
import decimal
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
    CASELOAD_TRUTH_PROVENANCE_KEYS,
    PENALTY_ASSESSMENT_KEY_NAMES,
    SCORER_ONLY_ENVELOPE_KEY_NAMES,
    TRUTH_DIR,
    TRUTH_PROVENANCE_KEYS,
    TruthManifestError,
    build_case_truth_manifest,
    build_caseload_truth_manifest,
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

    assert any(
        "published" in problem and "totalIncrease" in problem for problem in problems
    ), problems


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
        structural
        - SCORER_ONLY_ENVELOPE_KEY_NAMES
        - ENVELOPE_KEYS_THAT_ARE_NOT_SENTINELS.keys()
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


def test_assertions_channel_round_trips_the_complete_ledger() -> None:
    plan = _assertion_plan()
    truth = json.loads(json.dumps(build_case_truth_manifest(plan)))
    parsed = medical_assertions_from_truth(truth)
    assert parsed is not None
    _context, _projection, ledger = parsed
    assert ledger.model_dump() == plan.medical_assertions.model_dump()


def test_assertion_bearing_case_keeps_envelope_1_and_uses_assertions_channel_1() -> None:
    payload = _assertion_truth()
    assert payload["schemaVersion"] == "1.0.0"
    assert payload["channels"]["assertions"].get("channelVersion") == "1.0.0"
    assert ASSERTIONS_CHANNEL_VERSION == "1.0.0"


def test_assertion_absent_case_remains_byte_identical_envelope_1() -> None:
    """No assertions block, no assertions channel, envelope unchanged — the
    byte-identity half is carried by the golden gate over all four corpora."""
    plan = _plan("assertions-absent", scenario={"medical_history": {}})
    truth = build_case_truth_manifest(plan)
    assert truth["schemaVersion"] == "1.0.0"
    assert "assertions" not in truth["channels"]


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
            "Scorer-only ground truth; never use this artifact as an input to "
            "document analysis."
        ),
        "caseId": "legacy",
        "provenance": {"generator": "wc-synthetic-caseload-engine@0.0.0"},
        "channels": {},
    }
    assert medical_assertions_from_truth(legacy) is None
    assert money_facts_from_truth(legacy) is None


def test_assertions_channel_rejects_an_unknown_major(tmp_path: Path) -> None:
    payload = _assertion_truth()
    payload["channels"]["assertions"]["channelVersion"] = "2.0.0"
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
    absent = _fake_result(
        "absent", _plan("absent", scenario={"medical_history": {}}), tmp_path
    )
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
    assert channel["counts"] == {
        "contentions": len(ledger.contentions),
        "medicalOpinions": len(ledger.medical_opinions),
        "apportionmentAssertions": len(ledger.apportionment_assertions),
    }
    assert channel["qualityCounts"] == ledger.quality_counts()
    assert (
        sum(channel["apportionmentStateCounts"].values())
        == len(ledger.medical_opinions)
    )
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
    channel["contentions"][0]["quality"] = (
        "supported" if original != "supported" else "thin"
    )
    channel["ledgerDigest"] = assertion_ledger_digest(channel)
    with pytest.raises(TruthManifestError, match="does not match the rederived grade"):
        medical_assertions_from_truth(payload)


def test_output_validator_rejects_tampered_assertion_reference_after_digest_recomputed() -> None:
    payload = _assertion_truth()
    channel = payload["channels"]["assertions"]
    channel["contentions"][0]["targetConditionId"] = "cond-77"
    channel["ledgerDigest"] = assertion_ledger_digest(channel)
    with pytest.raises(
        TruthManifestError, match="references unknown condition 'cond-77'"
    ):
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
    plan_projection = project_medical_history(
        plan.medical_history, context.current_body_parts
    )
    parsed = medical_assertions_from_truth(_assertion_truth())
    assert parsed is not None
    truth_context, truth_projection, _ledger = parsed
    assert truth_context == context
    assert truth_projection == plan_projection


def test_plan_and_truth_paths_use_one_assertion_validation_context_and_rule_implementation() -> None:  # noqa: E501
    import wc_caseload_engine.medical_assertions as assertion_module
    import wc_caseload_engine.planner as planner_module
    import wc_caseload_engine.truth_manifest as truth_module

    assert (
        truth_module.validate_medical_assertions
        is assertion_module.validate_medical_assertions
    )
    assert (
        planner_module.validate_medical_assertions
        is assertion_module.validate_medical_assertions
    )
    assert truth_module.grade_ledger is assertion_module.grade_ledger
    assert (
        truth_module.AssertionValidationContext
        is assertion_module.AssertionValidationContext
    )


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
