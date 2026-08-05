"""Format-tolerant input loading and evidence-preserving fact normalization."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import yaml

from case_analysis_engine.models import Evidence, Fact
from case_analysis_engine.text import stable_value, tokens

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
#: Keys every serialized fact carries; used to recognize this engine's own output.
_NORMALIZED_FACT_KEYS = frozenset({"id", "category", "field", "value", "confidence", "evidence"})


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
    if is_normalized_payload(payload):
        return "case_analysis_normalized"
    if isinstance(payload, Mapping) and "caseFacts" in payload:
        return "wc_generator_manifest"
    if path.name == "case_facts.yaml":
        return "wc_generator_case_facts"
    return "document_intake"


def is_normalized_payload(payload: Any) -> bool:
    """True when the payload is this engine's own ``normalize`` output.

    Recognized so a normalize-then-analyze pipeline round-trips facts losslessly
    instead of re-flattening them and replacing their original provenance.
    """
    if not isinstance(payload, Mapping) or set(payload) != {"facts"}:
        return False
    records = payload["facts"]
    return (
        isinstance(records, list)
        and bool(records)
        and all(
            isinstance(record, Mapping)
            and _NORMALIZED_FACT_KEYS <= set(record)
            and ("sourcePath" in record or "source_path" in record)
            for record in records
        )
    )


def logical_source_ids(paths: list[Path]) -> dict[int, str]:
    """A stable label per input, independent of how the caller spelled the path.

    The label is the shortest trailing-path suffix that distinguishes the inputs
    from each other (``manifest.json``, or ``TC-001/manifest.json`` when two
    cases each supply one). Report bytes therefore do not change between
    relative and absolute invocations or between checkouts, as long as the
    distinguishing directories travel with the corpus.
    """
    resolved = [Path(path).resolve() for path in paths]
    max_depth = max((len(path.parts) for path in resolved), default=1)
    labels = [path.name for path in resolved]
    for depth in range(1, max_depth + 1):
        labels = ["/".join(path.parts[-min(depth, len(path.parts)) :]) for path in resolved]
        if len(set(labels)) == len(labels):
            break
    if len(set(labels)) != len(labels):
        labels = [f"input-{index}:{label}" for index, label in enumerate(labels)]
    return dict(enumerate(labels))


def normalize_paths(paths: Iterable[Path]) -> tuple[Fact, ...]:
    """Load and normalize one or more inputs in caller order, then sort deterministically."""
    ordered = [Path(path) for path in paths]
    labels = logical_source_ids(ordered)
    facts: list[Fact] = []
    for index, path in enumerate(ordered):
        payload = load_payload(path)
        facts.extend(
            normalize_payload(
                payload, source_id=labels[index], source_type=source_kind(payload, path)
            )
        )
    return tuple(
        sorted(
            facts, key=lambda fact: (fact.category, fact.field, stable_value(fact.value), fact.id)
        )
    )


def normalize_payload(
    payload: Any, *, source_id: str, source_type: str = "document_intake"
) -> tuple[Fact, ...]:
    """Turn every scalar in a JSON/YAML payload into an independently traceable fact.

    Three shapes are understood directly: this engine's own ``normalize`` output
    (deserialized losslessly, provenance intact), a common intake shape (a mapping
    containing ``facts`` records with ``value`` and ``evidence``), and generator
    artifacts. Everything else is flattened conservatively, retaining its
    structured path as provenance rather than guessing at a proprietary schema.

    Confidence policy: a claim keeps the confidence its input supplied. A
    generator artifact defaults to ``1.0`` because the ledger is its own system
    of record; a generic claim with no supplied score gets ``None`` — never an
    invented number — and validation reports it as unscored.
    """
    if is_normalized_payload(payload):
        return _facts_from_normalized(payload)
    default_confidence = 1.0 if source_type.startswith("wc_generator") else None
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

    def add_claim(
        record: Mapping[str, Any], path: str, inherited: Mapping[str, Any] | None
    ) -> None:
        field = str(record.get("field") or record.get("name") or record.get("key"))
        context = _merged_context(inherited, record)
        add_scalar(path, record["value"], context, field=field)

    def add_scalar(
        path: str, value: Any, context: Mapping[str, Any] | None, *, field: str | None = None
    ) -> None:
        rendered_field = field or _path_field(path)
        category = classify(rendered_field, path)
        evidence = _evidence_for(source_id, source_type, path, context, default_confidence)
        supplied = [item.confidence for item in evidence if item.confidence is not None]
        facts.append(
            Fact(
                id=f"{source_id}:{path}",
                category=category,
                field=rendered_field,
                value=value,
                source_path=path,
                confidence=min(supplied) if supplied else None,
                evidence=evidence,
            )
        )

    visit(payload, "$")
    return tuple(
        sorted(
            facts, key=lambda fact: (fact.category, fact.field, stable_value(fact.value), fact.id)
        )
    )


def classify(field: str, path: str = "") -> str:
    """Assign a broad analysis domain from stable field/path vocabulary, with a safe fallback."""
    words = tokens(f"{field} {path}")
    rules: tuple[tuple[str, frozenset[str]], ...] = (
        (
            "financial",
            frozenset(
                {
                    "wage",
                    "rate",
                    "benefit",
                    "payment",
                    "settlement",
                    "lien",
                    "money",
                    "indemnity",
                    "pd",
                    "td",
                    "aww",
                    "fee",
                    "cost",
                }
            ),
        ),
        (
            "medical",
            frozenset(
                {
                    "medical",
                    "treatment",
                    "diagnostic",
                    "diagnosis",
                    "provider",
                    "surgery",
                    "visit",
                    "mmi",
                    "impairment",
                    "cpt",
                    "imaging",
                    "mri",
                    "xray",
                    "ct",
                    "emg",
                }
            ),
        ),
        (
            "procedure",
            frozenset(
                {
                    "deadline",
                    "hearing",
                    "petition",
                    "filing",
                    "notice",
                    "conference",
                    "deposition",
                    "trial",
                    "discovery",
                    "document",
                    "subpoena",
                    "resolution",
                }
            ),
        ),
        (
            "injury_employment",
            frozenset(
                {
                    "injury",
                    "doi",
                    "accident",
                    "body",
                    "employment",
                    "job",
                    "occupation",
                    "hire",
                    "work",
                    "employer",
                }
            ),
        ),
        (
            "identity_parties",
            frozenset(
                {
                    "applicant",
                    "claimant",
                    "carrier",
                    "adjuster",
                    "attorney",
                    "firm",
                    "party",
                    "insured",
                    "name",
                    "adj",
                    "case",
                    "number",
                }
            ),
        ),
    )
    return next((category for category, markers in rules if words & markers), "other")


def _facts_from_normalized(payload: Mapping[str, Any]) -> tuple[Fact, ...]:
    facts = tuple(_fact_from_record(record) for record in payload["facts"])
    return tuple(
        sorted(
            facts, key=lambda fact: (fact.category, fact.field, stable_value(fact.value), fact.id)
        )
    )


def _fact_from_record(record: Mapping[str, Any]) -> Fact:
    evidence = tuple(
        Evidence(
            source_id=str(item["source_id"]),
            location=str(item["location"]),
            confidence=_optional_float(item.get("confidence")),
            source_type=str(item.get("source_type", "document_intake")),
            page=str(item["page"]) if item.get("page") is not None else None,
            excerpt=str(item["excerpt"]) if item.get("excerpt") is not None else None,
        )
        for item in record.get("evidence", ())
        if isinstance(item, Mapping)
    )
    return Fact(
        id=str(record["id"]),
        category=str(record["category"]),
        field=str(record["field"]),
        value=record["value"],
        source_path=str(record.get("sourcePath", record.get("source_path", ""))),
        confidence=_optional_float(record.get("confidence")),
        evidence=evidence,
    )


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return None


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
    default_confidence: float | None,
) -> tuple[Evidence, ...]:
    context = context or {}
    raw_evidence = context.get("evidence")
    records = (
        raw_evidence
        if isinstance(raw_evidence, list)
        else [raw_evidence]
        if raw_evidence
        else [context]
    )
    evidence: list[Evidence] = []
    for item in records:
        entry = item if isinstance(item, Mapping) else {}
        raw_confidence = entry.get("confidence", context.get("confidence", default_confidence))
        confidence = _optional_float(raw_confidence)
        if confidence is None and raw_confidence is not None:
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
    return tuple(
        sorted(evidence, key=lambda item: (item.source_id, item.location, item.page or ""))
    )


def _path_field(path: str) -> str:
    part = path.rsplit(".", 1)[-1]
    return _strip_indexes(part).lstrip("$") or "value"


def _strip_indexes(part: str) -> str:
    while "[" in part and part.endswith("]"):
        part = part[: part.rindex("[")]
    return part
