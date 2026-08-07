"""Evidence-bounded analysis and perspective generation over a canonical fact ledger."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from case_analysis_engine.input import normalize_paths_report
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
    normalized = normalize_paths_report(paths)
    return analyze_facts(normalized.facts, skipped=normalized.skipped)


def analyze_facts(
    facts: tuple[Fact, ...] | list[Fact], *, skipped: tuple[str, ...] = ()
) -> AnalysisReport:
    """Analyze supplied facts only; legal conclusions need a separate sourced authority adapter."""
    canonical_facts = tuple(sorted(facts, key=lambda item: (item.category, item.field, item.id)))
    findings = validate_facts(canonical_facts)
    if skipped:
        findings = tuple(
            sorted(
                findings
                + (
                    Finding(
                        code="skipped_metadata_keys",
                        severity="info",
                        message=(
                            f"{len(skipped)} input key(s) were treated as claim metadata and "
                            "not normalized as facts; see skippedKeys for the full accounting."
                        ),
                        fact_ids=(),
                        category="evidence_quality",
                    ),
                ),
                key=lambda item: (item.severity, item.code, item.fact_ids),
            )
        )
    domains = _domain_summary(canonical_facts, findings)
    return AnalysisReport(
        facts=canonical_facts,
        findings=findings,
        domains=domains,
        chronology=chronology(canonical_facts),
        angles=_angles(canonical_facts, findings),
        skipped=skipped,
    )


def _domain_summary(
    facts: tuple[Fact, ...], findings: tuple[Finding, ...]
) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for key, label in _DOMAINS:
        domain_facts = tuple(fact for fact in facts if fact.category == key)
        domain_findings = tuple(finding for finding in findings if finding.category == key)
        if key == "evidence_quality":
            domain_facts = facts
            domain_findings = tuple(
                finding for finding in findings if finding.category == "evidence_quality"
            )
        scored = [fact.confidence for fact in domain_facts if fact.confidence is not None]
        result[key] = {
            "label": label,
            "factCount": len(domain_facts),
            "averageConfidence": round(sum(scored) / len(scored), 3) if scored else None,
            "unscoredFactCount": len(domain_facts) - len(scored),
            "findingIds": [finding.code for finding in domain_findings],
            "factIds": [fact.id for fact in domain_facts],
        }
    return result


def _angles(facts: tuple[Fact, ...], findings: tuple[Finding, ...]) -> tuple[Angle, ...]:
    applicant_domains = {"injury_employment", "medical", "financial"}
    applicant = tuple(fact for fact in facts if fact.category in applicant_domains)
    defense = tuple(
        finding
        for finding in findings
        if finding.code
        in {
            "conflicting_fact",
            "chronology_question",
            "low_confidence",
            "missing_evidence",
            "limited_evidence",
        }
    )
    evidence_counts = Counter(item.source_id for fact in facts for item in fact.evidence)
    severity_counts = Counter(item.severity for item in findings)
    neutral_notes = [
        f"The ledger contains {len(facts)} normalized facts "
        f"from {len(evidence_counts)} identified source(s).",
        f"Integrity review produced {severity_counts['error']} error(s), "
        f"{severity_counts['warning']} warning(s), and "
        f"{severity_counts['info']} duplicate/other note(s).",
    ]
    applicant_notes = [
        f"{len(applicant)} supplied injury, medical, or financial fact(s) "
        "are available for evidence review."
    ]
    if not applicant:
        applicant_notes.append(
            "No supplied injury, medical, or financial fact supports an applicant-focused review."
        )
    defense_notes = [
        f"{len(defense)} supplied-data issue(s) could require clarification, "
        "corroboration, or chronology review."
    ]
    if not defense:
        defense_notes.append(
            "No contradiction, low-confidence or unscored fact, missing provenance, "
            "or chronology question was detected."
        )
    caveat = (
        "Perspective observations describe the supplied record only; "
        "they are not legal conclusions."
    )
    return (
        Angle("applicant", tuple(applicant_notes), tuple(fact.id for fact in applicant), caveat),
        Angle(
            "defense",
            tuple(defense_notes),
            tuple(fact_id for finding in defense for fact_id in finding.fact_ids),
            caveat,
        ),
        Angle("neutral", tuple(neutral_notes), tuple(fact.id for fact in facts), caveat),
    )
