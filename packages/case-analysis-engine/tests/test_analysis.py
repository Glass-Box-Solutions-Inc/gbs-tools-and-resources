from pathlib import Path

from case_analysis_engine.analysis import analyze_paths
from case_analysis_engine.render import render_json, render_markdown

FIXTURES = Path(__file__).parent / "fixtures"


def test_analysis_reports_all_domains_angles_and_is_deterministic() -> None:
    report = analyze_paths([FIXTURES / "intake.json", FIXTURES / "generator_manifest.json"])

    assert set(report.domains) == {
        "identity_parties",
        "injury_employment",
        "medical",
        "procedure",
        "financial",
        "evidence_quality",
    }
    assert [angle.name for angle in report.angles] == ["applicant", "defense", "neutral"]
    assert "does not state legal conclusions" in report.caveat
    assert render_json(report) == render_json(report)
    assert "# Case analysis report" in render_markdown(report)
