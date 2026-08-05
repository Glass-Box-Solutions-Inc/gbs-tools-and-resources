from case_analysis_engine.models import Evidence, Fact
from case_analysis_engine.validation import chronology, validate_facts


def _fact(identifier: str, field: str, value: object, confidence: float = 0.9) -> Fact:
    return Fact(
        id=identifier,
        category="injury_employment",
        field=field,
        value=value,
        source_path=f"$.{field}",
        confidence=confidence,
        evidence=(Evidence("source.pdf", f"$.{field}", confidence),),
    )


def test_detects_conflicts_duplicates_low_confidence_and_chronology_questions() -> None:
    facts = (
        _fact("a", "date_of_injury", "2025-02-01"),
        _fact("b", "date_of_injury", "2025-02-01"),
        _fact("c", "date_of_injury", "2025-02-02"),
        _fact("d", "treatment_date", "2025-01-15", confidence=0.2),
    )

    codes = [finding.code for finding in validate_facts(facts)]
    assert "duplicate_fact" in codes
    assert "conflicting_fact" in codes
    assert "low_confidence" in codes
    assert "chronology_question" in codes
    assert [event["date"] for event in chronology(facts)] == ["2025-01-15", "2025-02-01", "2025-02-01", "2025-02-02"]
