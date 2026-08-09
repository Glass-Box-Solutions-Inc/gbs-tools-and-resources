"""Multi-scenario money coherence harness for paper and scorer truth.

Each scenario must sweep at least one governed fact, but a rule may correctly
match nothing in one settlement family.  The union must cover every rule: that
keeps a stipulations case from being blamed for lacking a C&R release while
still making a moved label or vanished surface fail the harness.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from conftest import extract_text, requires_substrate
from money_coherence import GOVERNED_ON_THE_PAGE, SweepResult, sweep
from wc_caseload_engine.manifests import CaseResult, generate_case
from wc_caseload_engine.money import money as quantized_money
from wc_caseload_engine.money import money_manifest_block
from wc_caseload_engine.seeds import parse_case_seed
from wc_caseload_engine.truth_manifest import (
    money_facts_from_truth,
    read_truth_manifest,
    write_case_truth_manifest,
)

pytestmark = [pytest.mark.slow, requires_substrate]

_CENT = Decimal("0.01")

_SCENARIOS: dict[str, dict[str, Any]] = {
    "capped-rate": {
        "case_id": "money-coherence-capped-rate",
        "rng_seed": 4311,
        "injury": {
            "type": "specific",
            "date_of_injury": "2021-03-08",
            "body_parts": [{"part": "lumbar_spine", "icd10": "M54.5"}],
        },
        "lifecycle": {
            "target_stage": "resolved",
            "eval_type": "qme",
            "resolution": {"type": "stipulations"},
        },
        "output": {"formats": ["pdf"]},
        "documents": {"format_mix": {"pdf": 1.0}},
        "scenario": {
            "wages": {
                "pattern": "regular",
                "base_weekly_wage": 10000,
                "lookback_weeks": 52,
                "pay_frequency": "biweekly",
            },
            "settlement": {"gross_amount": 88000},
        },
    },
    "delayed-benefits": {
        "case_id": "money-coherence-delayed-benefits",
        "rng_seed": 4312,
        "injury": {
            "type": "specific",
            "date_of_injury": "2013-06-14",
            "body_parts": [{"part": "lumbar_spine", "icd10": "M54.5"}],
        },
        "lifecycle": {
            "target_stage": "resolved",
            "eval_type": "qme",
            "resolution": {"type": "c_and_r", "msa": True},
        },
        "output": {"formats": ["pdf"]},
        "documents": {"format_mix": {"pdf": 1.0}},
        "scenario": {
            "wages": {
                "pattern": "regular",
                "base_weekly_wage": 1500,
                "lookback_weeks": 52,
                "pay_frequency": "biweekly",
            },
            "benefits": {
                "td_weeks": 24,
                "td_gap_days": 45,
                "late_payments": 2,
                "max_days_late": 30,
            },
            "settlement": {"gross_amount": 92640},
        },
    },
    "penalised-benefits": {
        "case_id": "money-coherence-penalised-benefits",
        "rng_seed": 4313,
        "injury": {
            "type": "specific",
            "date_of_injury": "2021-03-08",
            "body_parts": [{"part": "lumbar_spine", "icd10": "M54.5"}],
        },
        "lifecycle": {
            "target_stage": "resolved",
            "eval_type": "qme",
            "resolution": {"type": "c_and_r"},
        },
        "output": {"formats": ["pdf"]},
        "documents": {"format_mix": {"pdf": 1.0}},
        "scenario": {
            "wages": {
                "pattern": "regular",
                "base_weekly_wage": 1500,
                "lookback_weeks": 52,
                "pay_frequency": "biweekly",
            },
            "benefits": {
                "td_weeks": 24,
                "td_gap_days": 45,
                "late_payments": 2,
                "max_days_late": 45,
            },
            "penalties": {},
            "settlement": {"gross_amount": 92640},
        },
    },
}


@dataclass(frozen=True, slots=True)
class RenderedScenario:
    """One rendered case and the two ledgers its documents are judged against."""

    name: str
    result: CaseResult
    manifest: dict[str, Any]
    truth: dict[str, Any]
    texts: dict[str, str]
    sweep_result: SweepResult

    @property
    def money(self) -> dict[str, Any]:
        """Return the public money ledger from the case manifest."""
        return self.manifest["caseFacts"]["money"]


def _normalized_texts(result: CaseResult, manifest: dict[str, Any]) -> dict[str, str]:
    return {
        document["subtype"]: " ".join(
            extract_text(
                result.directory / "documents" / document["filename"],
                document["format"],
            ).split()
        )
        for document in manifest["documents"]
    }


@pytest.fixture(scope="module")
def rendered_scenarios(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[RenderedScenario, ...]:
    """Render the three additional AJC-48 cases exactly once each."""
    root = tmp_path_factory.mktemp("money-coherence")
    rendered: list[RenderedScenario] = []
    for number, (name, body) in enumerate(_SCENARIOS.items(), 1):
        seed = parse_case_seed(body)
        result = generate_case(seed, root, number, truth_dir=root / "truth")
        assert result.plan.money_facts is not None
        facts = result.plan.money_facts
        if name == "capped-rate":
            assert facts.wages.rate.td_bound == "max"
            assert facts.settlement is not None
            assert facts.settlement.kind == "stipulations"
        elif name == "delayed-benefits":
            assert facts.wages.rate.basis.label == "doi-pre-2014"
            assert facts.benefits.late_payment_count > 0
            assert facts.benefits.gaps
        if name == "penalised-benefits":
            assert facts.penalties is not None
            assert facts.penalties.assessments
        manifest = json.loads(
            (result.directory / "manifest.json").read_text(encoding="utf-8")
        )
        assert result.truth_path is not None
        truth = read_truth_manifest(result.truth_path)
        texts = _normalized_texts(result, manifest)
        if name == "delayed-benefits":
            assert any("NO BENEFITS PAID" in text for text in texts.values())
        rendered.append(
            RenderedScenario(
                name=name,
                result=result,
                manifest=manifest,
                truth=truth,
                texts=texts,
                sweep_result=sweep(texts, manifest["caseFacts"]["money"], GOVERNED_ON_THE_PAGE),
            )
        )
    return tuple(rendered)


def _scenario(
    rendered_scenarios: tuple[RenderedScenario, ...], name: str
) -> RenderedScenario:
    return next(rendered for rendered in rendered_scenarios if rendered.name == name)


def _perturb(money: dict[str, Any], path: str) -> dict[str, Any]:
    changed = copy.deepcopy(money)
    node: Any = changed
    parts = path.split(".")[1:]
    for part in parts[:-1]:
        node = node[int(part)] if isinstance(node, list) else node[part]
    leaf = parts[-1]
    if isinstance(node, list):
        index = int(leaf)
        node[index] = str(Decimal(node[index]) + _CENT)
    else:
        node[leaf] = str(Decimal(node[leaf]) + _CENT)
    return changed


def test_every_governed_figure_agrees_on_every_surface(
    rendered_scenarios: tuple[RenderedScenario, ...],
) -> None:
    for rendered in rendered_scenarios:
        assert not rendered.sweep_result.disagreements, (
            f"{rendered.name}:\n{rendered.sweep_result.describe()}"
        )


def test_each_scenario_sweeps_and_their_union_covers_every_rule(
    rendered_scenarios: tuple[RenderedScenario, ...],
) -> None:
    found: set[str] = set()
    for rendered in rendered_scenarios:
        assert rendered.sweep_result.facts_found, f"{rendered.name} matched no governed fact"
        found.update(rendered.sweep_result.facts_found)
    dead = sorted(GOVERNED_ON_THE_PAGE.keys() - found)
    assert not dead, (
        f"these labels appear in neither scenario: {dead}. Either a label moved "
        "or a document stopped carrying the governed figure."
    )


def test_scorer_truth_equals_the_plan_manifest_and_paper(
    rendered_scenarios: tuple[RenderedScenario, ...],
) -> None:
    for rendered in rendered_scenarios:
        plan_facts = rendered.result.plan.money_facts
        assert plan_facts is not None
        truth_money = rendered.truth["channels"]["money"]
        assert truth_money["published"] == rendered.money
        assert truth_money["published"] == money_manifest_block(plan_facts)
        assert money_facts_from_truth(rendered.truth) == plan_facts
        for surface in rendered.sweep_result.surfaces:
            assert surface.printed == surface.expected


def test_unperturbed_comparator_reports_no_disagreements(
    rendered_scenarios: tuple[RenderedScenario, ...],
) -> None:
    rendered = _scenario(rendered_scenarios, "delayed-benefits")
    result = sweep(rendered.texts, rendered.money, GOVERNED_ON_THE_PAGE)
    assert not result.disagreements, result.describe()


@pytest.mark.parametrize("fact", tuple(GOVERNED_ON_THE_PAGE))
def test_one_cent_perturbation_is_reported_for_every_swept_fact(
    rendered_scenarios: tuple[RenderedScenario, ...], fact: str
) -> None:
    rendered = next(
        (
            scenario
            for scenario in rendered_scenarios
            if any(surface.fact == fact for surface in scenario.sweep_result.surfaces)
        ),
        None,
    )
    assert rendered is not None, f"no control scenario has a surface for {fact}"
    matching = tuple(
        surface for surface in rendered.sweep_result.surfaces if surface.fact == fact
    )
    assert matching, f"the control scenario has no surface for {fact}"
    _pattern, path = GOVERNED_ON_THE_PAGE[fact]
    perturbed = _perturb(rendered.money, path)
    result = sweep(rendered.texts, perturbed, GOVERNED_ON_THE_PAGE)
    disagreements = tuple(surface for surface in result.disagreements if surface.fact == fact)
    assert disagreements, f"a one-cent change to {fact} was not detected"
    assert any(surface.subtype == matching[0].subtype for surface in disagreements)
    description = result.describe()
    assert fact in description
    assert matching[0].subtype in description


def test_penalised_benefits_matches_ledger_paper_and_truth(
    rendered_scenarios: tuple[RenderedScenario, ...],
) -> None:
    """The ticket's 45-day planted positive control is arithmetically checkable."""
    rendered = _scenario(rendered_scenarios, "penalised-benefits")
    penalties = rendered.money["penalties"]
    assert penalties["assessmentCount"] >= 1
    assert {item["daysLate"] for item in penalties["assessments"]} == {45}
    for assessment in penalties["assessments"]:
        expected = quantized_money(
            Decimal(assessment["principal"]) * Decimal(assessment["increaseFraction"])
        )
        assert Decimal(assessment["amount"]) == expected
    assert Decimal(penalties["totalIncrease"]) == sum(
        Decimal(item["amount"]) for item in penalties["assessments"]
    )
    assert rendered.truth["channels"]["money"]["published"]["penalties"] == penalties
    assert any("§4650(d)" in text for text in rendered.texts.values())
    assert any("COUNSEL-UNCONFIRMED" in text for text in rendered.texts.values())
    penalty_facts = {
        "penalty_assessment_1",
        "penalty_assessment_2",
        "penalty_principal",
        "penalty_fraction",
        "penalty_total",
    }
    assert penalty_facts <= rendered.sweep_result.facts_found


def test_non_opted_outputs_are_byte_identical_and_penalty_free(tmp_path: Path) -> None:
    body = copy.deepcopy(_SCENARIOS["delayed-benefits"])
    assert "penalties" not in body["scenario"]
    seed = parse_case_seed(body)
    first = generate_case(seed, tmp_path / "first", 1)
    second = generate_case(seed, tmp_path / "second", 1)
    for filename in ("manifest.json", "case_facts.yaml"):
        assert (first.directory / filename).read_bytes() == (
            second.directory / filename
        ).read_bytes()
    manifest = json.loads((first.directory / "manifest.json").read_text(encoding="utf-8"))
    assert "penalties" not in json.dumps(manifest["caseFacts"])


def test_empty_penalty_ledger_leaves_the_benefit_document_byte_unchanged(
    tmp_path: Path,
) -> None:
    base = copy.deepcopy(_SCENARIOS["delayed-benefits"])
    base["scenario"]["benefits"] = {"td_weeks": 8, "late_payments": 0}
    without = generate_case(parse_case_seed(base), tmp_path / "without", 1)
    base["scenario"]["penalties"] = {}
    empty = generate_case(parse_case_seed(base), tmp_path / "empty", 1)
    assert empty.plan.money_facts is not None
    assert empty.plan.money_facts.penalties is not None
    assert not empty.plan.money_facts.penalties.assessments

    def benefit_bytes(rendered: CaseResult) -> bytes:
        manifest = json.loads(
            (rendered.directory / "manifest.json").read_text(encoding="utf-8")
        )
        entry = next(
            item for item in manifest["documents"] if item["subtype"] == "BENEFIT_PAYMENT_LEDGER"
        )
        return (rendered.directory / "documents" / entry["filename"]).read_bytes()

    assert benefit_bytes(without) == benefit_bytes(empty)


def test_truth_manifest_is_byte_deterministic_from_the_same_plan(
    tmp_path: Path, rendered_scenarios: tuple[RenderedScenario, ...]
) -> None:
    for rendered in rendered_scenarios:
        first = write_case_truth_manifest(rendered.result.plan, tmp_path / rendered.name / "first")
        second = write_case_truth_manifest(
            rendered.result.plan, tmp_path / rendered.name / "second"
        )
        assert first.read_bytes() == second.read_bytes()
