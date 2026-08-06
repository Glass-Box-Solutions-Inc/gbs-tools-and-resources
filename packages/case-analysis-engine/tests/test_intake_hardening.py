"""Regression guards for AJC-50 — intake heuristic hardening (Fable review A1/A2/A4)."""

import json
from pathlib import Path

from click.testing import CliRunner

from case_analysis_engine.analysis import analyze_paths
from case_analysis_engine.cli import cli
from case_analysis_engine.input import normalize_paths, normalize_paths_report
from case_analysis_engine.render import render_json
from case_analysis_engine.validation import validate_facts

FIXTURES = Path(__file__).parent / "fixtures"


def test_itemized_name_value_rows_do_not_conflict(tmp_path: Path) -> None:
    """Two benefit payments are two entity rows, not contradictory assertions."""
    source = tmp_path / "benefits.json"
    source.write_text(
        json.dumps(
            {
                "benefits": [
                    {"name": "td_payment", "value": 800},
                    {"name": "td_payment", "value": 650},
                ]
            }
        ),
        encoding="utf-8",
    )
    facts = normalize_paths([source])
    assert all(fact.scope == "entity" for fact in facts)
    assert not any(f.code == "conflicting_fact" for f in validate_facts(facts))

    result = CliRunner().invoke(cli, ["validate", str(source)])
    assert result.exit_code == 0, result.output


def test_claim_shorthand_promotes_only_in_claim_containers(tmp_path: Path) -> None:
    """name/key shorthand works in facts[]; explicit field promotes anywhere."""
    source = tmp_path / "claims.json"
    source.write_text(
        json.dumps(
            {
                "facts": [
                    {"name": "date_of_injury", "value": "2025-02-01"},
                    {"key": "date_of_injury", "value": "2025-03-05"},
                ],
                "case": {"summary": {"value": "Jordan Doe", "field": "applicant_name"}},
            }
        ),
        encoding="utf-8",
    )
    facts = normalize_paths([source])
    scopes = {fact.field: fact.scope for fact in facts}
    assert scopes["date_of_injury"] == "claim"
    assert scopes["applicant_name"] == "claim"
    assert any(f.code == "conflicting_fact" for f in validate_facts(facts))


def test_metadata_named_fields_survive_when_pure(tmp_path: Path) -> None:
    """A mapping of only metadata-named keys is data — referral.source is an assertion."""
    source = tmp_path / "referral.json"
    source.write_text(
        json.dumps({"referral": {"source": "attorney lopez"}, "note": "intake call"}),
        encoding="utf-8",
    )
    facts = normalize_paths([source])
    values = {fact.source_path: fact.value for fact in facts}
    assert values["$.referral.source"] == "attorney lopez"


def test_skipped_metadata_keys_are_accounted(tmp_path: Path) -> None:
    """Every key skipped as claim metadata is visible in normalize output and reports."""
    source = tmp_path / "mixed.json"
    source.write_text(
        json.dumps({"applicant_name": "Jordan", "page": 3, "source_document": "application.pdf"}),
        encoding="utf-8",
    )
    normalized = normalize_paths_report([source])
    assert normalized.skipped == ("mixed.json:$.page", "mixed.json:$.source_document")

    report = analyze_paths([source])
    assert report.skipped == normalized.skipped
    assert any(f.code == "skipped_metadata_keys" for f in report.findings)
    assert "skippedKeys" in render_json(report)

    cli_out = CliRunner().invoke(cli, ["normalize", str(source)])
    assert cli_out.exit_code == 0, cli_out.output
    assert json.loads(cli_out.output)["skipped"] == list(normalized.skipped)


def test_string_evidence_names_the_source_document(tmp_path: Path) -> None:
    """evidence: "application.pdf" is provenance, not noise."""
    source = tmp_path / "claims.json"
    source.write_text(
        json.dumps(
            {
                "facts": [
                    {
                        "field": "applicant_name",
                        "value": "Jordan",
                        "evidence": "application.pdf",
                        "confidence": 0.9,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    facts = normalize_paths([source])
    assert facts[0].evidence[0].source_id == "application.pdf"
    assert facts[0].confidence == 0.9


def test_normalize_output_with_skipped_still_round_trips(tmp_path: Path) -> None:
    """The skipped key in versioned output is accepted and ignored on re-ingest."""
    source = tmp_path / "mixed.json"
    source.write_text(json.dumps({"applicant_name": "Jordan", "page": 3}), encoding="utf-8")
    cli_out = CliRunner().invoke(cli, ["normalize", str(source)])
    assert cli_out.exit_code == 0, cli_out.output

    round_trip = tmp_path / "normalized.json"
    round_trip.write_text(cli_out.output, encoding="utf-8")
    assert normalize_paths([round_trip]) == normalize_paths([source])


def test_skipped_accounting_survives_round_trip(tmp_path: Path) -> None:
    """Analyzing preserved normalize output reports the same skipped keys as direct analysis."""
    import yaml

    source = tmp_path / "mixed.json"
    source.write_text(
        json.dumps({"applicant_name": "Jordan", "page": 3, "source_document": "application.pdf"}),
        encoding="utf-8",
    )
    direct = analyze_paths([source])
    cli_out = CliRunner().invoke(cli, ["normalize", str(source)])
    assert cli_out.exit_code == 0, cli_out.output

    as_json = tmp_path / "normalized.json"
    as_json.write_text(cli_out.output, encoding="utf-8")
    as_yaml = tmp_path / "normalized.yaml"
    as_yaml.write_text(yaml.safe_dump(json.loads(cli_out.output), sort_keys=True), encoding="utf-8")

    for preserved in (as_json, as_yaml):
        replayed = analyze_paths([preserved])
        assert replayed.skipped == direct.skipped
        assert any(f.code == "skipped_metadata_keys" for f in replayed.findings)
        assert "- Skipped metadata keys: 2" in __import__(
            "case_analysis_engine.render", fromlist=["render_markdown"]
        ).render_markdown(replayed)


def test_analysis_report_positional_constructor_is_stable() -> None:
    """The sixth positional argument remains the caveat; skipped stays keyword-safe."""
    from case_analysis_engine.models import AnalysisReport

    report = AnalysisReport((), (), {}, (), (), "custom caveat")
    assert report.caveat == "custom caveat"
    assert report.skipped == ()
    assert report.as_dict()["skippedKeys"] == []


def test_claim_container_status_resets_at_intermediate_mappings(tmp_path: Path) -> None:
    """name/value under facts.by_topic.medical[] is an entity row, not a claim."""
    source = tmp_path / "grouped.json"
    source.write_text(
        json.dumps(
            {"facts": {"by_topic": {"medical": [{"name": "mmi_date", "value": "2025-06-01"}]}}}
        ),
        encoding="utf-8",
    )
    facts = normalize_paths([source])
    assert all(fact.scope == "entity" for fact in facts)


def test_dollar_prefixed_filenames_do_not_double_qualify(tmp_path: Path) -> None:
    """Qualification is decided by payload origin, never by an entry's first character."""
    source = tmp_path / "$case.json"
    source.write_text(json.dumps({"applicant_name": "Jordan", "page": 3}), encoding="utf-8")
    direct = analyze_paths([source])
    assert direct.skipped == ("$case.json:$.page",)

    cli_out = CliRunner().invoke(cli, ["normalize", str(source)])
    assert cli_out.exit_code == 0, cli_out.output
    preserved = tmp_path / "normalized.json"
    preserved.write_text(cli_out.output, encoding="utf-8")
    replayed = analyze_paths([preserved])
    assert replayed.skipped == direct.skipped
    assert render_json(replayed) == render_json(direct)


def test_versions_agree_everywhere(tmp_path: Path) -> None:
    """pyproject, __version__, and the CLI identify one build."""
    import tomllib

    import case_analysis_engine

    pyproject = tomllib.loads(
        (Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    )
    assert case_analysis_engine.__version__ == pyproject["project"]["version"]

    result = CliRunner().invoke(cli, ["--version"])
    assert result.exit_code == 0, result.output
    assert pyproject["project"]["version"] in result.output


def test_invalid_skipped_shapes_are_rejected(tmp_path: Path) -> None:
    """A versioned payload with a malformed skipped list errors clearly."""
    import pytest

    for bad in ("nope", [1], {"a": 1}):
        source = tmp_path / "bad.json"
        source.write_text(json.dumps({"version": 1, "facts": [], "skipped": bad}), encoding="utf-8")
        with pytest.raises(ValueError, match="skipped"):
            normalize_paths([source])
