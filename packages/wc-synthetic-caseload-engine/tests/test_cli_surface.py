"""CLI surface tests — help, templates, validation, taxonomy drift exit codes.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from click.testing import CliRunner

from conftest import requires_classifier, requires_substrate
from wc_caseload_engine import seeds
from wc_caseload_engine.cli import cli
from wc_caseload_engine.seed_template import CASE_SEED_TEMPLATE, CASELOAD_SPEC_TEMPLATE


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _write_spec(path: Path, payload: dict[str, Any]) -> Path:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def test_help_lists_every_command(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    for command in ("generate", "seed", "validate", "taxonomy-check"):
        assert command in result.output


@pytest.mark.parametrize("command", ["generate", "seed", "validate", "taxonomy-check"])
def test_every_subcommand_has_help(runner: CliRunner, command: str) -> None:
    result = runner.invoke(cli, [command, "--help"])
    assert result.exit_code == 0
    assert command.replace("-", " ") in result.output.lower() or "Usage" in result.output


def test_seed_template_writes_a_file_that_loads_back(
    runner: CliRunner, tmp_path: Path
) -> None:
    target = tmp_path / "seed.yaml"
    result = runner.invoke(cli, ["seed", "--template", "--out", str(target)])
    assert result.exit_code == 0, result.output
    assert target.is_file()

    seed = seeds.load_case_seed(target)
    assert seed.case_id == "martinez-001"
    assert seed.lifecycle.reconsideration.outcome == "granted_remand"
    assert seed.lifecycle.liens.count == 3
    assert seed.documents.subtype_overrides == {"DEPOSITION_TRANSCRIPT": 2}
    # round-trips through the serializer unchanged
    assert seeds.parse_case_seed(yaml.safe_load(seeds.dump_case_seed(seed))) == seed


def test_seed_template_covers_every_controllable_field() -> None:
    """The template must exercise the whole schema surface, not a subset."""
    payload = yaml.safe_load(CASE_SEED_TEMPLATE)
    seed = seeds.parse_case_seed(payload)
    dumped = seeds.seed_to_dict(seed)

    for section in ("case_id", "rng_seed", "profile", "injury", "lifecycle",
                    "documents", "output"):
        assert section in payload

    # every profile sub-block is populated
    for block in ("applicant", "employer", "carrier", "attorneys", "physicians"):
        assert payload["profile"][block]
    assert dumped["profile"]["applicant"]["name"]

    # every lifecycle sub-block is populated
    lifecycle = payload["lifecycle"]
    for block in ("ur_dispute", "resolution", "reconsideration", "liens"):
        assert lifecycle[block]
    assert lifecycle["doctrine_hooks"]

    # both override flavours are demonstrated
    kinds = {tuple(sorted(entry)) for entry in payload["documents"]["overrides"]}
    assert ("count", "subtype") in kinds
    assert ("max", "min", "type") in kinds


def test_caseload_template_loads_and_resolves(runner: CliRunner, tmp_path: Path) -> None:
    target = tmp_path / "caseload.yaml"
    result = runner.invoke(
        cli, ["seed", "--template", "--kind", "caseload", "--out", str(target)]
    )
    assert result.exit_code == 0, result.output

    spec = seeds.load_caseload_spec(target)
    assert spec.caseload_id == "demo-2026q3"
    assert len(spec.cases) == 2
    assert spec.auto is not None and spec.auto.count == 20
    # defaults deep-merged: case 1 overrides claim_response, keeps eval_type default
    assert spec.cases[0].lifecycle.claim_response == "denied"
    assert spec.cases[0].lifecycle.eval_type == "qme"
    assert spec.cases[0].documents.global_cap == 90
    assert len(seeds.resolve_caseload(spec)) == 22
    assert yaml.safe_load(CASELOAD_SPEC_TEMPLATE)["auto"]["distribution"] == "balanced"


def test_seed_template_prints_to_stdout_without_out(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["seed", "--template"])
    assert result.exit_code == 0
    assert "case_id: martinez-001" in result.output


def test_seed_without_template_is_a_usage_error(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["seed"])
    assert result.exit_code != 0
    assert "--template" in result.output


def test_validate_accepts_a_good_spec(
    runner: CliRunner, tmp_path: Path, minimal_caseload: dict[str, Any]
) -> None:
    spec = _write_spec(tmp_path / "spec.yaml", minimal_caseload)
    result = runner.invoke(cli, ["validate", "--spec", str(spec)])
    assert result.exit_code == 0, result.output
    assert "schema   : OK" in result.output


def test_validate_rejects_a_bad_spec_naming_the_field(
    runner: CliRunner, tmp_path: Path, minimal_caseload: dict[str, Any]
) -> None:
    minimal_caseload["cases"][0]["lifecycle"] = {"claim_response": "accpeted"}
    spec = _write_spec(tmp_path / "bad.yaml", minimal_caseload)
    result = runner.invoke(cli, ["validate", "--spec", str(spec)])
    assert result.exit_code != 0
    assert "cases.0.lifecycle.claim_response" in result.output
    assert "accepted" in result.output


@requires_substrate
def test_validate_rejects_an_unknown_control_key(
    runner: CliRunner, tmp_path: Path, minimal_caseload: dict[str, Any]
) -> None:
    minimal_caseload["cases"][0]["documents"] = {"exclude": ["NOT_A_REAL_SUBTYPE"]}
    spec = _write_spec(tmp_path / "keys.yaml", minimal_caseload)
    result = runner.invoke(cli, ["validate", "--spec", str(spec)])
    assert result.exit_code != 0
    assert "NOT_A_REAL_SUBTYPE" in result.output


@requires_substrate
def test_validate_accepts_control_keys_from_the_template(
    runner: CliRunner, tmp_path: Path
) -> None:
    """Every taxonomy key named in the shipped template must be real."""
    case = yaml.safe_load(CASE_SEED_TEMPLATE)
    spec = _write_spec(tmp_path / "tpl.yaml", {"caseload_id": "tpl", "cases": [case]})
    result = runner.invoke(cli, ["validate", "--spec", str(spec)])
    assert result.exit_code == 0, result.output
    assert "controls : OK" in result.output


def test_validate_without_arguments_is_a_usage_error(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["validate"])
    assert result.exit_code != 0
    assert "--spec" in result.output


def test_generate_dry_run_resolves_the_whole_caseload(
    runner: CliRunner, tmp_path: Path, minimal_caseload: dict[str, Any]
) -> None:
    minimal_caseload["auto"] = {"count": 3, "distribution": "balanced", "rng_seed": 9}
    spec = _write_spec(tmp_path / "spec.yaml", minimal_caseload)
    result = runner.invoke(
        cli, ["generate", "--spec", str(spec), "--out", str(tmp_path / "out"), "--dry-run"]
    )
    assert result.exit_code == 0, result.output
    assert "cases    : 4 (1 explicit, 3 derived)" in result.output
    assert "dry-run: spec is valid; no files written" in result.output
    assert not (tmp_path / "out").exists()


def test_generate_seed_override_changes_derived_cases(
    runner: CliRunner, tmp_path: Path, minimal_caseload: dict[str, Any]
) -> None:
    minimal_caseload["auto"] = {"count": 2, "distribution": "balanced", "rng_seed": 1}
    spec = _write_spec(tmp_path / "spec.yaml", minimal_caseload)
    args = ["generate", "--spec", str(spec), "--out", str(tmp_path / "out"), "--dry-run"]
    default_run = runner.invoke(cli, args)
    overridden = runner.invoke(cli, [*args, "--seed", "424242"])
    assert default_run.exit_code == 0 and overridden.exit_code == 0
    assert default_run.output != overridden.output


def test_generate_stops_at_the_phase_b_boundary(
    runner: CliRunner, tmp_path: Path, minimal_caseload: dict[str, Any]
) -> None:
    spec = _write_spec(tmp_path / "spec.yaml", minimal_caseload)
    result = runner.invoke(
        cli, ["generate", "--spec", str(spec), "--out", str(tmp_path / "out")]
    )
    assert result.exit_code != 0
    assert isinstance(result.exception, NotImplementedError)
    assert "Phase B" in str(result.exception)


def test_generate_validates_the_spec_before_the_phase_b_boundary(
    runner: CliRunner, tmp_path: Path, minimal_caseload: dict[str, Any]
) -> None:
    """Schema errors must surface now, not in Phase B."""
    minimal_caseload["cases"][0]["typo_field"] = True
    spec = _write_spec(tmp_path / "bad.yaml", minimal_caseload)
    result = runner.invoke(
        cli, ["generate", "--spec", str(spec), "--out", str(tmp_path / "out")]
    )
    assert result.exit_code != 0
    assert not isinstance(result.exception, NotImplementedError)
    assert "typo_field" in result.output


@requires_substrate
@requires_classifier
def test_taxonomy_check_passes_against_the_classifier(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["taxonomy-check"])
    assert result.exit_code == 0, result.output
    assert "353" in result.output
    assert "drift: none" in result.output


def test_taxonomy_check_fails_on_a_missing_classifier(
    runner: CliRunner, tmp_path: Path
) -> None:
    result = runner.invoke(cli, ["taxonomy-check", "--classifier-path", str(tmp_path)])
    assert result.exit_code != 0
    assert "src/taxonomy" in result.output


def test_version_flag(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "wc-caseload" in result.output
