"""Format-tolerant input loading and evidence-preserving fact normalization."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import yaml

from case_analysis_engine.models import Evidence, Fact

_METADATA_KEYS = frozenset(
    {
        "confidence",
        "evidence",
        "excerpt",
        "page",
        "pages",
        "source",
        "source_document",
        "sourceDocument",
        "document",
        "document_id",
        "documentId",
        "provenance",
        "metadata",
    }
)
_TOKEN_RE = re.compile(r"[^a-z0-9]+")


def load_payload(path: Path) -> Any:
    """Load one JSON or YAML payload without imposing a vendor-specific extraction schema."""
    text = path.read_text(encoding="utf-8")
    try:
        value = json.loads(text) if path.suffix.lower() == ".json" else yaml.safe_load(text)
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise ValueError(f"{path}: invalid structured input: {exc}") from exc
    if value is None:
        raise ValueError(f"{path}: input is empty")
    return value


def source_kind(payload: Any, path: Path) -> str:
    """Name known artifact formats for report clarity while keeping generic input supported."""
    if isinstance(payload, Mapping) and "caseFacts" in payload:
        return "wc_generator_manifest"
    if path.name == "case_facts.yaml":
        return "wc_generator_case_facts"
    return "document_intake"


def normalize_paths(paths: Iterable[Path]) -> tuple[Fact, ...]:
    """Load and normalize one or more inputs in caller order, then sort deterministically."""
    facts: list[Fact] = []
    for path in paths:
        payload = load_payload(path)
        facts.extend(normalize_payload(payload, source_id=str(path), source_type=source_kind(payload, path)))
    return tuple(sorted(facts, key=lambda fact: (fact.category, fact.field, _stable_value(fact.value), fact.id)))


def normalize_payload(payload: Any, *, source_id: str, source_type: str = "document_intake") -> tuple[Fact, ...]:
    """Turn every scalar in a JSON/YAML payload into an independently traceable fact.

    A common intake shape (a mapping containing ``facts`` records with ``value`` and ``evidence``)
    is understood directly. Everything else is flattened conservatively, retaining its structured
    path as provenance rather than guessing at a proprietary schema.
    """
    default_confidence = 1.0 if source_type.startswith("wc_generator") else 0.7
    facts: list[Fact] = []

    def visit(value: Any, path: str, context: Mapping[str, Any] | None = None) -> None:
        if isinstance(value, Mapping):
            if "value" in value and ("field" in value or "name" in value or "key" in value):
                add_claim(value, path, context)
                return
            child_context = _merged_context(context, value)
            for key in sorted(value, key=str):
                if str(key) not in _METADATA_KEYS:
                    visit(value[key], f"{path}.{key}" if path else str(key), child_context)
            return
        if isinstance(value, list):
            for index, item in enumerate(value):
                visit(item, f"{path}[{index}]", context)
            return
        if value is not None:
            add_scalar(path, value, context)

    def add_claim(record: Mapping[str, Any], path: str, inherited: Mapping[str, Any] | None) -> None:
        field = str(record.get("field") or record.get("name") or record.get("key"))
        context = _merged_context(inherited, record)
        add_scalar(path, record["value"], context, field=field)

    def add_scalar(
        path: str, value: Any, context: Mapping[str, Any] | None, *, field: str | None = None
    ) -> None:
        rendered_field = field or _path_field(path)
        category = classify(rendered_field, path)
        evidence = _evidence_for(source_id, source_type, path, context, default_confidence)
        confidence = min(item.confidence for item in evidence) if evidence else 0.0
        facts.append(
            Fact(
                id=f"{source_id}:{path}",
                category=category,
                field=rendered_field,
                value=value,
                source_path=path,
                confidence=confidence,
                evidence=evidence,
            )
        )

    visit(payload, "$")
    return tuple(sorted(facts, key=lambda fact: (fact.category, fact.field, _stable_value(fact.value), fact.id)))


def classify(field: str, path: str = "") -> str:
    """Assign a broad analysis domain from stable field/path vocabulary, with a safe fallback."""
    tokens = _tokens(f"{field} {path}")
    rules: tuple[tuple[str, frozenset[str]], ...] = (
        ("financial", frozenset({"wage", "rate", "benefit", "payment", "settlement", "lien", "money", "indemnity", "pd", "td", "aww", "fee", "cost"})),
        ("medical", frozenset({"medical", "treatment", "diagnostic", "diagnosis", "provider", "surgery", "visit", "mmi", "impairment", "cpt", "imaging", "mri", "xray", "ct", "emg"})),
        ("procedure", frozenset({"deadline", "hearing", "petition", "filing", "notice", "conference", "deposition", "trial", "discovery", "document", "subpoena", "resolution"})),
        ("injury_employment", frozenset({"injury", "doi", "accident", "body", "employment", "job", "occupation", "hire", "work", "employer"})),
        ("identity_parties", frozenset({"applicant", "claimant", "carrier", "adjuster", "attorney", "firm", "party", "insured", "name", "adj", "case", "number"})),
    )
    return next((category for category, markers in rules if tokens & markers), "other")


def _merged_context(parent: Mapping[str, Any] | None, child: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(parent or {})
    for key in _METADATA_KEYS:
        if key in child:
            result[key] = child[key]
    return result


def _evidence_for(
    source_id: str,
    source_type: str,
    path: str,
    context: Mapping[str, Any] | None,
    default_confidence: float,
) -> tuple[Evidence, ...]:
    context = context or {}
    raw_evidence = context.get("evidence")
    records = raw_evidence if isinstance(raw_evidence, list) else [raw_evidence] if raw_evidence else [context]
    evidence: list[Evidence] = []
    for item in records:
        entry = item if isinstance(item, Mapping) else {}
        raw_confidence = entry.get("confidence", context.get("confidence", default_confidence))
        try:
            confidence = max(0.0, min(1.0, float(raw_confidence)))
        except (TypeError, ValueError):
            confidence = default_confidence
        source = str(
            entry.get("source_document")
            or entry.get("sourceDocument")
            or entry.get("document_id")
            or entry.get("documentId")
            or entry.get("document")
            or context.get("source_document")
            or context.get("document_id")
            or source_id
        )
        page = entry.get("page", context.get("page"))
        excerpt = entry.get("excerpt", context.get("excerpt"))
        evidence.append(
            Evidence(
                source_id=source,
                location=path,
                confidence=confidence,
                source_type=source_type,
                page=str(page) if page is not None else None,
                excerpt=str(excerpt) if excerpt is not None else None,
            )
        )
    return tuple(sorted(evidence, key=lambda item: (item.source_id, item.location, item.page or "")))


def _path_field(path: str) -> str:
    part = path.rsplit(".", 1)[-1]
    return re.sub(r"\[\d+\]", "", part).lstrip("$") or "value"


def _tokens(value: str) -> frozenset[str]:
    return frozenset(token for token in _TOKEN_RE.split(value.lower()) if token)


def _stable_value(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str, separators=(",", ":"))
