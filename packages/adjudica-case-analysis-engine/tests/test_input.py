from pathlib import Path

from adjudica_case_analysis_engine.input import normalize_paths

FIXTURES = Path(__file__).parent / "fixtures"


def test_normalizes_generic_intake_with_evidence() -> None:
    facts = normalize_paths([FIXTURES / "intake.json"])

    applicant = next(fact for fact in facts if fact.field == "applicant_name")
    assert applicant.value == "Jordan Doe"
    assert applicant.evidence[0].source_id == "application.pdf"
    assert applicant.evidence[0].page == "1"
    assert all(fact.evidence for fact in facts)


def test_normalizes_generator_manifest_and_case_facts_without_importing_generator() -> None:
    facts = normalize_paths([FIXTURES / "generator_manifest.json", FIXTURES / "case_facts.yaml"])

    assert any(fact.source_path == "$.caseFacts.money.averageWeeklyWage" for fact in facts)
    assert any(fact.source_path == "$.money.averageWeeklyWage" for fact in facts)
    assert all(fact.evidence[0].source_type.startswith("wc_generator") for fact in facts)
