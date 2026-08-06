"""Small immutable data contracts shared by ingestion, validation, and reporting."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

Severity = Literal["error", "warning", "info"]


@dataclass(frozen=True, slots=True)
class Evidence:
    """Where a fact came from, without claiming more certainty than the input provides.

    ``confidence`` is ``None`` when the input supplied no score; the engine never
    invents a probability for evidence it did not receive.
    """

    source_id: str
    location: str
    confidence: float | None
    source_type: str = "document_intake"
    page: str | None = None
    excerpt: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


FactScope = Literal["claim", "case", "entity"]


@dataclass(frozen=True, slots=True)
class Fact:
    """One normalized assertion, preserving its original path and all available evidence.

    ``scope`` records what kind of assertion this is, decided at normalization:
    ``claim`` — an explicit claim record naming its own field; ``case`` — a
    case-level scalar flattened from an unindexed path; ``entity`` — an
    attribute of one element of a repeated collection (a document, a provider),
    which is never compared against its siblings' attributes.
    """

    id: str
    category: str
    field: str
    value: Any
    source_path: str
    confidence: float | None
    evidence: tuple[Evidence, ...] = ()
    scope: FactScope = "case"

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category,
            "field": self.field,
            "value": self.value,
            "sourcePath": self.source_path,
            "confidence": self.confidence,
            "scope": self.scope,
            "evidence": [item.as_dict() for item in self.evidence],
        }


@dataclass(frozen=True, slots=True)
class Finding:
    """A traceable data-quality or analysis observation, never a legal determination."""

    code: str
    severity: Severity
    message: str
    fact_ids: tuple[str, ...] = ()
    category: str = "evidence_quality"

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "factIds": list(self.fact_ids),
            "category": self.category,
        }


@dataclass(frozen=True, slots=True)
class Angle:
    """A bounded perspective over the same facts; not advocacy or a conclusion of law."""

    name: Literal["applicant", "defense", "neutral"]
    observations: tuple[str, ...]
    fact_ids: tuple[str, ...]
    caveat: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "observations": list(self.observations),
            "factIds": list(self.fact_ids),
            "caveat": self.caveat,
        }


@dataclass(frozen=True, slots=True)
class AnalysisReport:
    """The full deterministic product of normalization, integrity checks, and analysis."""

    facts: tuple[Fact, ...]
    findings: tuple[Finding, ...]
    domains: dict[str, dict[str, Any]]
    chronology: tuple[dict[str, Any], ...]
    angles: tuple[Angle, ...]
    skipped: tuple[str, ...] = ()
    caveat: str = (
        "This report organizes supplied evidence and identifies data-quality questions. "
        "It does not state legal conclusions, deadlines, entitlement, or legal advice."
    )

    def as_dict(self) -> dict[str, Any]:
        return {
            "caveat": self.caveat,
            "facts": [fact.as_dict() for fact in self.facts],
            "findings": [finding.as_dict() for finding in self.findings],
            "domains": self.domains,
            "chronology": list(self.chronology),
            "angles": [angle.as_dict() for angle in self.angles],
            "skippedKeys": list(self.skipped),
        }
