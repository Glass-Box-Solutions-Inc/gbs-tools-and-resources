from pathlib import Path

from click.testing import CliRunner

from adjudica_case_analysis_engine.cli import cli

FIXTURES = Path(__file__).parent / "fixtures"


def test_cli_normalize_analyze_validate_and_angles(tmp_path: Path) -> None:
    runner = CliRunner()
    normalized = tmp_path / "normalized.json"
    report_json = tmp_path / "report.json"
    report_markdown = tmp_path / "report.md"

    normalize_result = runner.invoke(
        cli, ["normalize", str(FIXTURES / "intake.json"), "--out", str(normalized)]
    )
    analyze_result = runner.invoke(
        cli,
        [
            "analyze",
            str(FIXTURES / "intake.json"),
            str(FIXTURES / "generator_manifest.json"),
            "--json-out",
            str(report_json),
            "--markdown-out",
            str(report_markdown),
        ],
    )
    validate_result = runner.invoke(cli, ["validate", str(FIXTURES / "intake.json")])
    angles_result = runner.invoke(
        cli, ["angles", str(FIXTURES / "intake.json"), "--angle", "defense"]
    )

    assert normalize_result.exit_code == 0, normalize_result.output
    assert analyze_result.exit_code == 0, analyze_result.output
    assert validate_result.exit_code == 0, validate_result.output
    assert angles_result.exit_code == 0, angles_result.output
    assert normalized.is_file() and report_json.is_file() and report_markdown.is_file()
    assert "defense:" in angles_result.output
