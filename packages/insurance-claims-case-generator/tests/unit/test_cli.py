"""
CLI smoke tests — verifies generate and scenarios commands produce valid output.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import json
import pathlib

import pytest
from click.testing import CliRunner

from claims_generator.cli import cli


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


def test_generate_standard_outputs_json(runner: CliRunner) -> None:
    """generate --scenario standard_claim must produce valid JSON on stdout."""
    result = runner.invoke(cli, ["generate", "--scenario", "standard_claim", "--seed", "42"])
    assert result.exit_code == 0, f"CLI failed: {result.output}"
    data = json.loads(result.output)
    assert data["scenario_slug"] == "standard_claim"
    assert data["seed"] == 42
    assert len(data["document_events"]) > 0


def test_generate_litigated_qme_doc_count(runner: CliRunner) -> None:
    """generate --scenario litigated_qme seed=42 must have document_events with dates."""
    result = runner.invoke(cli, ["generate", "--scenario", "litigated_qme", "--seed", "42"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data["document_events"]) > 0
    # Dates should be strings (ISO format)
    for event in data["document_events"]:
        assert "event_date" in event
        assert isinstance(event["event_date"], str)


def test_generate_denied_claim(runner: CliRunner) -> None:
    """generate --scenario denied_claim must succeed."""
    result = runner.invoke(cli, ["generate", "--scenario", "denied_claim", "--seed", "99"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["scenario_slug"] == "denied_claim"


def test_generate_unknown_scenario_exits_1(runner: CliRunner) -> None:
    """generate with unknown scenario must exit with code 1."""
    result = runner.invoke(cli, ["generate", "--scenario", "nonexistent"])
    assert result.exit_code == 1


def test_generate_compact_json(runner: CliRunner) -> None:
    """--compact flag must produce compact JSON (no indentation)."""
    result = runner.invoke(
        cli, ["generate", "--scenario", "standard_claim", "--seed", "1", "--compact"]
    )
    assert result.exit_code == 0
    # Compact JSON has no leading whitespace on lines
    lines = result.output.strip().split("\n")
    assert len(lines) == 1  # compact is a single line


def test_generate_output_file(runner: CliRunner, tmp_path: pathlib.Path) -> None:
    """--output flag must write JSON to file instead of stdout."""
    outfile = tmp_path / "test_case.json"
    result = runner.invoke(
        cli,
        ["generate", "--scenario", "standard_claim", "--seed", "7", "--output", str(outfile)],
    )
    assert result.exit_code == 0
    assert outfile.exists()
    data = json.loads(outfile.read_text())
    assert data["seed"] == 7


def test_scenarios_command_lists_all(runner: CliRunner) -> None:
    """scenarios command must list all registered scenario slugs."""
    result = runner.invoke(cli, ["scenarios"])
    assert result.exit_code == 0
    assert "standard_claim" in result.output
    assert "litigated_qme" in result.output
    assert "denied_claim" in result.output


def test_version_option(runner: CliRunner) -> None:
    """--version must return a version string."""
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "0.2.0" in result.output
