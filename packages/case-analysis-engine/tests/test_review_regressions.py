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


def test_claim_records_in_lists_still_conflict(tmp_path: Path) -> None:
    """Explicit claim records keep conflict detection even though they live in a list."""
    payload = {
        "facts": [
            {"field": "date_of_injury", "value": "2025-02-01", "confidence": 0.9},
            {"field": "date_of_injury", "value": "2025-03-05", "confidence": 0.8},
        ]
    }
    source = tmp_path / "claims.json"
    source.write_text(json.dumps(payload), encoding="utf-8")

    facts = normalize_paths([source])
    assert all(fact.scope == "claim" for fact in facts)
    assert any(finding.code == "conflicting_fact" for finding in validate_facts(facts))


def test_differently_parented_fields_do_not_merge(tmp_path: Path) -> None:
    """applicant.phone_number and adjuster.phone_number are different properties."""
    source = tmp_path / "parties.json"
    source.write_text(
        json.dumps(
            {
                "applicant": {"phone_number": "555-0100"},
                "adjuster": {"phone_number": "555-0199"},
            }
        ),
        encoding="utf-8",
    )

    findings = validate_facts(normalize_paths([source]))
    assert not any(finding.code == "conflicting_fact" for finding in findings)


def test_container_nesting_does_not_hide_conflicts(tmp_path: Path) -> None:
    """A bare field and the same field under a container qualifier still conflict."""
    (tmp_path / "a.json").write_text(json.dumps({"case": {"employer": "Acme"}}), encoding="utf-8")
    (tmp_path / "b.json").write_text(json.dumps({"employer": "Zenith"}), encoding="utf-8")

    findings = validate_facts(normalize_paths([tmp_path / "a.json", tmp_path / "b.json"]))
    assert any(finding.code == "conflicting_fact" for finding in findings)


def test_yaml_native_dates_normalize_and_enter_chronology(tmp_path: Path) -> None:
    """Unquoted YAML dates become ISO strings: JSON output stays valid, chronology sees them."""
    source = tmp_path / "intake.yaml"
    source.write_text(
        "date_of_injury: 2025-01-15\nsurgery_datetime: 2025-03-01 09:30:00\n", encoding="utf-8"
    )

    facts = normalize_paths([source])
    values = {fact.field: fact.value for fact in facts}
    assert values["date_of_injury"] == "2025-01-15"
    assert isinstance(values["surgery_datetime"], str)

    result = CliRunner().invoke(cli, ["normalize", str(source)])
    assert result.exit_code == 0, result.output
    json.loads(result.output)

    report = analyze_paths([source])
    assert any(event["date"] == "2025-01-15" for event in report.chronology)


def test_duplicate_inputs_keep_reports_path_free(tmp_path: Path) -> None:
    """The same file supplied twice falls back to occurrence labels, never absolute paths."""
    case_dir = tmp_path / "TC-001"
    case_dir.mkdir()
    shutil.copy(FIXTURES / "generator_manifest.json", case_dir / "manifest.json")
    target = case_dir / "manifest.json"

    rendered = render_json(analyze_paths([target, target]))
    assert "input-0:manifest.json" in rendered
    assert str(tmp_path) not in rendered


def test_invalid_confidence_never_promotes(tmp_path: Path) -> None:
    """Present-but-invalid confidence stays unscored — even where the default is 1.0."""
    manifest = json.loads((FIXTURES / "generator_manifest.json").read_text(encoding="utf-8"))
    manifest["caseFacts"]["money"]["confidence"] = "high"
    high = tmp_path / "manifest.json"
    high.write_text(json.dumps(manifest), encoding="utf-8")

    money_facts = [
        fact
        for fact in normalize_paths([high])
        if fact.source_path.startswith("$.caseFacts.money.") and "[" not in fact.source_path
    ]
    assert money_facts and all(fact.confidence is None for fact in money_facts)

    for bad in (True, 1.7, -0.2):
        manifest["caseFacts"]["money"]["confidence"] = bad
        high.write_text(json.dumps(manifest), encoding="utf-8")
        facts = [
            fact
            for fact in normalize_paths([high])
            if fact.source_path.startswith("$.caseFacts.money.") and "[" not in fact.source_path
        ]
        assert facts and all(fact.confidence is None for fact in facts), bad


def test_findings_never_mix_incompatible_chains(tmp_path: Path) -> None:
    """Each finding's facts are mutually compatible; incompatible chains never aggregate."""
    triple = tmp_path / "triple.json"
    triple.write_text(
        json.dumps(
            {"a": {"b": {"status": "X"}}, "b": {"status": "Y"}, "c": {"b": {"status": "Z"}}}
        ),
        encoding="utf-8",
    )
    facts = normalize_paths([triple])
    conflicts = [f for f in validate_facts(facts) if f.code == "conflicting_fact"]
    assert len(conflicts) == 2
    assert all(len(finding.fact_ids) == 2 for finding in conflicts)
    for finding in conflicts:
        joined = " ".join(finding.fact_ids)
        assert not ("$.a.b." in joined and "$.c.b." in joined)

    parties = tmp_path / "parties.json"
    parties.write_text(
        json.dumps({"applicant": {"status": "employed"}, "adjuster": {"status": "employed"}}),
        encoding="utf-8",
    )
    findings = validate_facts(normalize_paths([parties]))
    assert not any(f.code in ("duplicate_fact", "conflicting_fact") for f in findings)


def test_legacy_normalized_claims_recover_scope(tmp_path: Path) -> None:
    """Serialized facts without a scope key restore claims as claims, entities as entities."""
    claims = tmp_path / "claims.json"
    claims.write_text(
        json.dumps(
            {
                "facts": [
                    {"field": "date_of_injury", "value": "2025-02-01", "confidence": 0.9},
                    {"field": "date_of_injury", "value": "2025-03-05", "confidence": 0.8},
                ]
            }
        ),
        encoding="utf-8",
    )
    original = normalize_paths([claims, FIXTURES / "generator_manifest.json"])

    legacy_records = []
    for fact in original:
        record = fact.as_dict()
        del record["scope"]
        legacy_records.append(record)
    legacy = tmp_path / "legacy.json"
    legacy.write_text(json.dumps({"facts": legacy_records}), encoding="utf-8")

    restored = normalize_paths([legacy])
    scopes = {fact.id: fact.scope for fact in restored}
    assert {fact.id: fact.scope for fact in original} == scopes
    assert any(finding.code == "conflicting_fact" for finding in validate_facts(restored))


def test_colliding_or_structural_keys_are_rejected(tmp_path: Path) -> None:
    """Keys that would collide into one fact ID fail loudly instead of merging."""
    import pytest

    date_twins = tmp_path / "dates.yaml"
    date_twins.write_text("2025-01-15: a\n'2025-01-15': b\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate mapping key"):
        normalize_paths([date_twins])

    int_twins = tmp_path / "ints.yaml"
    int_twins.write_text("1: a\n'1': b\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate mapping key"):
        normalize_paths([int_twins])

    dotted = tmp_path / "dotted.json"
    dotted.write_text(json.dumps({"a.b": 1}), encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported mapping key"):
        normalize_paths([dotted])


def test_explicit_null_confidence_stays_unscored(tmp_path: Path) -> None:
    """confidence: null is the author's unscored statement, never the generator default."""
    manifest = json.loads((FIXTURES / "generator_manifest.json").read_text(encoding="utf-8"))
    manifest["caseFacts"]["money"]["confidence"] = None
    source = tmp_path / "manifest.json"
    source.write_text(json.dumps(manifest), encoding="utf-8")

    money_facts = [
        fact
        for fact in normalize_paths([source])
        if fact.source_path.startswith("$.caseFacts.money.") and fact.scope == "case"
    ]
    assert money_facts and all(fact.confidence is None for fact in money_facts)
    findings = validate_facts(normalize_paths([source]))
    assert any(finding.code == "limited_evidence" for finding in findings)
