"""Regression guards for the PR #30 review findings — one test per fixed defect."""

import json
import shutil
from pathlib import Path

import yaml
from click.testing import CliRunner

from case_analysis_engine.analysis import analyze_paths
from case_analysis_engine.cli import cli
from case_analysis_engine.input import normalize_paths
from case_analysis_engine.render import render_json, render_markdown
from case_analysis_engine.validation import validate_facts

FIXTURES = Path(__file__).parent / "fixtures"


def test_repeated_list_records_are_not_conflicts() -> None:
    """A manifest with two documents, providers, diagnostics, and benefit events is valid."""
    facts = normalize_paths([FIXTURES / "generator_manifest.json"])

    codes = {finding.code for finding in validate_facts(facts)}
    assert "conflicting_fact" not in codes
    assert "duplicate_fact" not in codes

    result = CliRunner().invoke(cli, ["validate", str(FIXTURES / "generator_manifest.json")])
    assert result.exit_code == 0, result.output


def test_case_level_conflicts_still_fire_across_naming_dialects(tmp_path: Path) -> None:
    """camelCase and snake_case spellings of one field meet in the same conflict check."""
    (tmp_path / "a.json").write_text(json.dumps({"dateOfInjury": "2025-02-01"}), encoding="utf-8")
    (tmp_path / "b.json").write_text(json.dumps({"date_of_injury": "2025-03-05"}), encoding="utf-8")

    findings = validate_facts(normalize_paths([tmp_path / "a.json", tmp_path / "b.json"]))
    conflicts = [finding for finding in findings if finding.code == "conflicting_fact"]
    assert len(conflicts) == 1
    assert len(conflicts[0].fact_ids) == 2


def test_normalize_output_round_trips_losslessly(tmp_path: Path) -> None:
    """Re-analyzing normalize output keeps every fact and evidence field byte-for-byte."""
    original = normalize_paths([FIXTURES / "intake.json"])
    payload = {"facts": [fact.as_dict() for fact in original]}

    as_json = tmp_path / "normalized.json"
    as_yaml = tmp_path / "normalized.yaml"
    as_json.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    as_yaml.write_text(yaml.safe_dump(payload, sort_keys=True), encoding="utf-8")

    assert normalize_paths([as_json]) == original
    assert normalize_paths([as_yaml]) == original


def test_unscored_claim_is_reported_not_scored(tmp_path: Path) -> None:
    """A claim with no supplied confidence stays unscored and is flagged, never given 0.7."""
    source = tmp_path / "bare.json"
    source.write_text(json.dumps({"injuryDescription": "fell from ladder"}), encoding="utf-8")

    facts = normalize_paths([source])
    assert [fact.confidence for fact in facts] == [None]

    codes = [finding.code for finding in validate_facts(facts)]
    assert "limited_evidence" in codes
    assert "low_confidence" not in codes


def test_angle_observations_cite_fact_ids() -> None:
    """Markdown and the angles CLI both carry fact references for every perspective."""
    report = analyze_paths([FIXTURES / "intake.json"])
    markdown = render_markdown(report)
    for angle in report.angles:
        section = markdown.split(f"### {angle.name.title()}", 1)[1]
        assert "- Facts: " in section
        if angle.fact_ids:
            assert angle.fact_ids[0] in section.split("###", 1)[0]

    result = CliRunner().invoke(cli, ["angles", str(FIXTURES / "intake.json")])
    assert result.exit_code == 0, result.output
    assert result.output.count("- Facts: ") == 3


def test_report_bytes_do_not_depend_on_path_spelling(tmp_path: Path, monkeypatch) -> None:
    """Relative, absolute, and different-checkout invocations produce identical bytes."""
    for root in ("checkout-a", "checkout-b"):
        case_dir = tmp_path / root / "TC-001"
        case_dir.mkdir(parents=True)
        shutil.copy(FIXTURES / "generator_manifest.json", case_dir / "manifest.json")

    absolute = render_json(analyze_paths([tmp_path / "checkout-a" / "TC-001" / "manifest.json"]))
    monkeypatch.chdir(tmp_path / "checkout-a" / "TC-001")
    relative = render_json(analyze_paths([Path("manifest.json")]))
    other_checkout = render_json(
        analyze_paths([tmp_path / "checkout-b" / "TC-001" / "manifest.json"])
    )

    assert absolute == relative == other_checkout
    assert "checkout-a" not in absolute
