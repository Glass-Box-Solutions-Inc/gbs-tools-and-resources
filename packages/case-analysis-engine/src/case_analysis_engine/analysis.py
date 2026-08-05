"""Evidence-bounded analysis and perspective generation over a canonical fact ledger."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from case_analysis_engine.input import normalize_paths
from case_analysis_engine.models import AnalysisReport, Angle, Fact, Finding
from case_analysis_engine.validation import chronology, validate_facts

_DOMAINS = (
    ("identity_parties", "Identity and parties"),
    ("injury_employment", "Injury and employment"),
    ("medical", "Medical, treatment, and diagnostics"),
    ("procedure", "Procedure and deadlines"),
    ("financial", "Wages, rates, benefits, settlement, and liens"),
    ("evidence_quality", "Evidence quality"),
)


def analyze_paths(paths: list[Path] | tuple[Path, ...]) -> AnalysisReport:
    """Normalize paths and produce a report without relying on upstream package imports."""
    return analyze_facts(normalize_paths(paths))


def analyze_facts(facts: tuple[Fact, ...] | list[Fact]) -> AnalysisReport:
    """Analyze supplied facts only; legal conclusions require a separate sourced authority adapter."""
    canonical_facts = tuple(sorted(facts, key=lambda item: (item.category, item.field, item.id)))
    findings = validate_facts(canonical_facts)
    domains = _domain_summary(canonical_facts, findings)
    return AnalysisReport(
        facts=canonical_facts,
        findings=findings,
        domains=domains,
        chronology=chronology(canonical_facts),
        angles=_angles(canonical_facts, findings),
    )


def _domain_summary(facts: tuple[Fact, ...], findings: tuple[Finding, ...]) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for key, label in _DOMAINS:
        domain_facts = tuple(fact for fact in facts if fact.category == key)
        domain_findings = tuple(finding for finding in findings if finding.category == key)
        if key == "evidence_quality":
            domain_facts = facts
            domain_findings = tuple(
                finding for finding in findings if finding.category == "evidence_quality"
            )
        confidence = round(
            sum(fact.confidence for fact in domain_facts) / len(domain_facts), 3
        ) if domain_facts else None
        result[key] = {
            "label": label,
            "factCount": len(domain_facts),
            "averageConfidence": confidence,
            "findingIds": [finding.code for finding in domain_findings],
            "factIds": [fact.id for fact in domain_facts],
        }
    return result


def _angles(facts: tuple[Fact, ...], findings: tuple[Finding, ...]) -> tuple[Angle, ...]:
    relevant = lambda categories: tuple(fact for fact in facts if fact.category in categories)
    applicant = relevant({"injury_employment", "medical", "financial"})
    defense = tuple(
        finding for finding in findings if finding.code in {"conflicting_fact", "chronology_question", "low_confidence", "missing_evidence"}
    )
    evidence_counts = Counter(item.source_id for fact in facts for item in fact.evidence)
    neutral_notes = [
        f"The ledger contains {len(facts)} normalized facts from {len(evidence_counts)} identified source(s).",
        f"Integrity review produced {sum(1 for item in findings if item.severity == 'error')} error(s), "
        f"{sum(1 for item in findings if item.severity == 'warning')} warning(s), and "
        f"{sum(1 for item in findings if item.severity == 'info')} duplicate/other note(s).",
    ]
    applicant_notes = [
        f"{len(applicant)} supplied injury, medical, or financial fact(s) are available for evidence review."
    ]
    if not applicant:
        applicant_notes.append("No supplied injury, medical, or financial fact supports an applicant-focused review.")
    defense_notes = [
        f"{len(defense)} supplied-data issue(s) could require clarification, corroboration, or chronology review."
    ]
    if not defense:
        defense_notes.append("No contradiction, low-confidence fact, missing provenance, or chronology question was detected.")
    caveat = "Perspective observations describe the supplied record only; they are not legal conclusions."
    return (
        Angle("applicant", tuple(applicant_notes), tuple(fact.id for fact in applicant), caveat),
        Angle("defense", tuple(defense_notes), tuple(fact_id for finding in defense for fact_id in finding.fact_ids), caveat),
        Angle("neutral", tuple(neutral_notes), tuple(fact.id for fact in facts), caveat),
    )
