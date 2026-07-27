"""Effective taxonomy — the classifier is the vocabulary of record.

Three vocabularies exist and must not be confused:

============================  =====  =========================================
Set                           Size   Meaning
============================  =====  =========================================
Classifier (source of truth)  353    ``Adjudica-classifier/src/taxonomy/*.ts``
Substrate enum                384    ``data/taxonomy.py`` — 350 canonical keys
                                     plus 34 substrate-local realism subtypes
                                     (fax cover sheets, blank scanned pages…)
Engine canonical              353    substrate ∩ classifier + a 3-subtype
                                     overlay for what the substrate lacks
============================  =====  =========================================

The overlay exists because the substrate's taxonomy was extracted from an older
classifier revision. It is a build-time constant so the engine works fully
offline; ``wc-caseload taxonomy-check`` re-parses the classifier TypeScript at
runtime and exits nonzero if the two ever disagree again.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import structlog

from wc_caseload_engine.substrate import import_substrate

log = structlog.get_logger(__name__)

EXPECTED_SUBTYPE_COUNT = 353
"""Subtype count asserted by the Adjudica-classifier test-suite."""

EXPECTED_TYPE_COUNT = 15
"""Parent document type count."""

CLASSIFIER_ENV_VAR = "WC_CASELOAD_CLASSIFIER"
"""Environment variable overriding classifier source discovery."""

CLASSIFIER_DIR_NAME = "Adjudica-classifier"

_CLASSIFIER_SENTINELS: tuple[str, ...] = (
    "src/taxonomy/types.ts",
    "src/taxonomy/subtypes.ts",
    "src/taxonomy/mapping.ts",
)


@dataclass(frozen=True, slots=True)
class OverlaySubtype:
    """A classifier subtype the substrate enum does not yet carry."""

    label: str
    parent_type: str


OVERLAY_SUBTYPES: Mapping[str, OverlaySubtype] = {
    "PETITION_FOR_PENALTIES": OverlaySubtype("Petition for Penalties", "CORRESPONDENCE"),
    "NOTICE_OF_PENALTY_5814": OverlaySubtype("Notice of Penalty (LC §5814)", "CORRESPONDENCE"),
    "NOTICE_OF_PENALTY_5814_5": OverlaySubtype(
        "Notice of Penalty (LC §5814.5)", "CORRESPONDENCE"
    ),
}
"""Build-time overlay: classifier subtypes absent from the substrate enum."""

SUBSTRATE_ONLY_SUBTYPES: frozenset[str] = frozenset(
    {
        "ATTORNEY_FEE_PETITION",
        "BLANK_SCANNED_PAGE",
        "CARRIER_POSITION_STATEMENT",
        "CLIENT_CASE_VALUATION_LETTER",
        "CLIENT_DECLARATION",
        "CLIENT_HIPAA_AUTHORIZATION",
        "CLIENT_REPORT_ANALYSIS_LETTER",
        "CLIENT_SETTLEMENT_RECOMMENDATION",
        "CMS_CONDITIONAL_PAYMENT_LETTER",
        "COVER_LETTER_ENCLOSURE",
        "DEPOSITION_TRANSCRIPT_QME_AME",
        "EAMS_CASE_SUMMARY",
        "EXHIBIT_LIST",
        "FAX_COVER_SHEET",
        "INFORMAL_PD_RATING_PRINTOUT",
        "INTERNAL_FILE_NOTE",
        "INTERROGATORIES_SPECIAL",
        "INTERROGATORY_RESPONSES",
        "JOINT_PRETRIAL_CONFERENCE_STATEMENT",
        "MILEAGE_REIMBURSEMENT_REQUEST",
        "NOTICE_OF_TD_TERMINATION",
        "OBJECTION_TO_QME_AME_REPORT",
        "PETITION_FOR_PENALTIES_LC_5814",
        "PRODUCTION_RESPONSES",
        "PTP_REFERRAL_LETTER",
        "QME_PANEL_STRIKE_LETTER",
        "REQUEST_FOR_CONTINUANCE",
        "REQUEST_FOR_PRODUCTION",
        "REQUEST_SUPPLEMENTAL_QME_AME_REPORT",
        "RESERVATION_OF_RIGHTS_LETTER",
        "RETAINER_FEE_AGREEMENT",
        "RETURN_TO_WORK_REPORT",
        "TD_RATE_CALCULATION_NOTICE",
        "WITNESS_LIST",
    }
)
"""Substrate-local subtypes that are NOT classifier vocabulary.

They remain renderable (the substrate has templates for them and they add file
realism) but they never appear in the canonical 353-subtype set, and Phase B
must not put them in a manifest without mapping them to a canonical key.
"""


# ---------------------------------------------------------------------------
# TypeScript source parsing (classifier = vocabulary of record)
# ---------------------------------------------------------------------------

_TS_ENTRY_RE = re.compile(
    r'^[ \t]*([A-Z0-9_]+)[ \t]*:[ \t]*(?:\n[ \t]*)?"((?:[^"\\]|\\.)*)"[ \t]*,?[ \t]*$',
    re.MULTILINE,
)
_TS_ARRAY_ENTRY_RE = re.compile(r'"([A-Z0-9_]+)"')
_TS_UNICODE_ESCAPE_RE = re.compile(r"\\+u([0-9a-fA-F]{4})")


class TaxonomySourceError(RuntimeError):
    """Raised when the classifier TypeScript source cannot be located or parsed."""


def _decode_ts_string(raw: str) -> str:
    """Decode the escape sequences TypeScript string literals may carry."""
    decoded = _TS_UNICODE_ESCAPE_RE.sub(lambda m: chr(int(m.group(1), 16)), raw)
    return decoded.replace('\\"', '"').replace("\\\\", "\\")


def _object_body(text: str, const_name: str, *, source: str) -> str:
    """Return the brace-balanced body of ``export const <const_name> = { ... }``."""
    match = re.search(r"export const " + re.escape(const_name) + r"\b[^=]*=\s*\{", text)
    if match is None:
        raise TaxonomySourceError(f"{source}: could not find `export const {const_name}`")
    start = match.end()
    depth = 1
    index = start
    while depth and index < len(text):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        index += 1
    if depth:
        raise TaxonomySourceError(f"{source}: unbalanced braces in `{const_name}`")
    return text[start : index - 1]


def _parse_ts_string_map(text: str, const_name: str, *, source: str) -> dict[str, str]:
    """Parse a ``{ KEY: "value" }`` TypeScript object into a dict."""
    body = _object_body(text, const_name, source=source)
    return {key: _decode_ts_string(value) for key, value in _TS_ENTRY_RE.findall(body)}


def _parse_ts_array_map(text: str, const_name: str, *, source: str) -> dict[str, tuple[str, ...]]:
    """Parse a ``{ KEY: ["A", "B"] }`` TypeScript object into a dict of tuples."""
    body = _object_body(text, const_name, source=source)
    out: dict[str, tuple[str, ...]] = {}
    for key, array_body in re.findall(r"([A-Z0-9_]+)\s*:\s*\[(.*?)\]", body, re.DOTALL):
        out[key] = tuple(_TS_ARRAY_ENTRY_RE.findall(array_body))
    return out


@dataclass(frozen=True, slots=True)
class ClassifierTaxonomy:
    """The taxonomy exactly as declared by the classifier TypeScript source."""

    source: Path
    types: tuple[str, ...]
    type_labels: Mapping[str, str]
    subtypes: tuple[str, ...]
    subtype_labels: Mapping[str, str]
    type_to_subtypes: Mapping[str, tuple[str, ...]]
    subtype_to_type: Mapping[str, str]

    @property
    def subtype_set(self) -> frozenset[str]:
        return frozenset(self.subtypes)


def _classifier_candidates(explicit: Path | str | None) -> list[Path]:
    """Candidate classifier roots in priority order.

    An explicitly supplied path (argument or environment variable) is
    authoritative: a wrong ``--classifier-path`` must fail loudly rather than
    silently checking a different checkout.
    """
    if explicit is not None:
        return [Path(explicit).expanduser()]
    env = os.environ.get(CLASSIFIER_ENV_VAR)
    if env:
        return [Path(env).expanduser()]
    candidates: list[Path] = []
    home = Path.home()
    candidates.extend(
        [
            home / "projects" / CLASSIFIER_DIR_NAME,
            home / "code" / CLASSIFIER_DIR_NAME,
            home / CLASSIFIER_DIR_NAME,
        ]
    )
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidates.append(parent / CLASSIFIER_DIR_NAME)
    return candidates


def find_classifier(path: Path | str | None = None) -> Path | None:
    """Locate the classifier source tree, or ``None`` when unavailable."""
    seen: set[Path] = set()
    for candidate in _classifier_candidates(path):
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if all((resolved / rel).is_file() for rel in _CLASSIFIER_SENTINELS):
            return resolved
    return None


def classifier_path(path: Path | str | None = None) -> Path:
    """Return the classifier root, raising :class:`TaxonomySourceError` if absent."""
    found = find_classifier(path)
    if found is None:
        probed = "\n  ".join(str(candidate) for candidate in _classifier_candidates(path)[:6])
        raise TaxonomySourceError(
            "Adjudica-classifier source tree not found.\n"
            f"  Pass --classifier-path or set {CLASSIFIER_ENV_VAR}=/abs/path/to/"
            f"{CLASSIFIER_DIR_NAME}.\n"
            f"  Searched:\n  {probed}\n"
            "  A valid tree contains src/taxonomy/{types,subtypes,mapping}.ts."
        )
    return found


def parse_classifier_taxonomy(path: Path | str | None = None) -> ClassifierTaxonomy:
    """Parse the classifier's ``types.ts`` / ``subtypes.ts`` / ``mapping.ts``."""
    root = classifier_path(path)
    tax_dir = root / "src" / "taxonomy"
    types_src = (tax_dir / "types.ts").read_text(encoding="utf-8")
    subtypes_src = (tax_dir / "subtypes.ts").read_text(encoding="utf-8")
    mapping_src = (tax_dir / "mapping.ts").read_text(encoding="utf-8")

    types_map = _parse_ts_string_map(types_src, "DOCUMENT_TYPES", source="types.ts")
    type_labels = _parse_ts_string_map(types_src, "DOCUMENT_TYPE_LABELS", source="types.ts")
    subtypes_map = _parse_ts_string_map(subtypes_src, "DOCUMENT_SUBTYPES", source="subtypes.ts")
    subtype_labels = _parse_ts_string_map(
        subtypes_src, "DOCUMENT_SUBTYPE_LABELS", source="subtypes.ts"
    )
    type_to_subtypes = _parse_ts_array_map(
        mapping_src, "DOCUMENT_TYPE_TO_SUBTYPES", source="mapping.ts"
    )

    subtype_to_type: dict[str, str] = {}
    for parent, children in type_to_subtypes.items():
        for child in children:
            subtype_to_type[child] = parent

    return ClassifierTaxonomy(
        source=root,
        types=tuple(types_map),
        type_labels=type_labels,
        subtypes=tuple(subtypes_map),
        subtype_labels=subtype_labels,
        type_to_subtypes=type_to_subtypes,
        subtype_to_type=subtype_to_type,
    )


# ---------------------------------------------------------------------------
# Effective taxonomy (substrate + overlay, classifier-shaped)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Taxonomy:
    """The engine's effective taxonomy.

    ``subtypes`` is the canonical, classifier-facing set (353). ``substrate_only``
    holds renderable-but-non-canonical substrate extras; ``overlay`` holds the
    classifier subtypes the substrate lacks.
    """

    types: tuple[str, ...]
    subtypes: tuple[str, ...]
    subtype_labels: Mapping[str, str]
    subtype_to_type: Mapping[str, str]
    type_to_subtypes: Mapping[str, tuple[str, ...]]
    substrate_only: frozenset[str] = field(default=frozenset())
    overlay: frozenset[str] = field(default=frozenset())

    @property
    def subtype_set(self) -> frozenset[str]:
        return frozenset(self.subtypes)

    def is_canonical(self, subtype: str) -> bool:
        """``True`` when *subtype* is part of the classifier vocabulary."""
        return subtype in self.subtype_set

    def is_renderable(self, subtype: str) -> bool:
        """``True`` when the substrate can render *subtype* (canonical or extra)."""
        return subtype in self.subtype_set or subtype in self.substrate_only

    def is_type(self, key: str) -> bool:
        """``True`` when *key* names a parent document type."""
        return key in self.types

    def parent_of(self, subtype: str) -> str | None:
        """Parent document type of *subtype*, or ``None`` when unknown."""
        return self.subtype_to_type.get(subtype)

    def subtypes_for_type(self, doc_type: str) -> tuple[str, ...]:
        """Canonical subtypes belonging to *doc_type*."""
        return self.type_to_subtypes.get(doc_type, ())

    def label(self, subtype: str) -> str | None:
        """Human label for *subtype*."""
        return self.subtype_labels.get(subtype)


@lru_cache(maxsize=1)
def effective_taxonomy() -> Taxonomy:
    """Build the engine taxonomy from the substrate enum plus the overlay.

    Requires the substrate on disk (raises ``SubstrateUnavailableError`` otherwise).
    """
    substrate_tax = import_substrate("data.taxonomy")

    substrate_subtypes = {member.value for member in substrate_tax.DocumentSubtype}
    substrate_labels: dict[str, str] = dict(substrate_tax.DOCUMENT_SUBTYPE_LABELS)
    substrate_parent: dict[str, str] = dict(substrate_tax.SUBTYPE_TO_TYPE)

    canonical = (substrate_subtypes - SUBSTRATE_ONLY_SUBTYPES) | set(OVERLAY_SUBTYPES)

    labels: dict[str, str] = {}
    parents: dict[str, str] = {}
    for subtype in canonical:
        overlay = OVERLAY_SUBTYPES.get(subtype)
        if overlay is not None and subtype not in substrate_subtypes:
            labels[subtype] = overlay.label
            parents[subtype] = overlay.parent_type
        else:
            labels[subtype] = substrate_labels.get(subtype, subtype)
            parent = substrate_parent.get(subtype)
            if parent is None and overlay is not None:
                parent = overlay.parent_type
            if parent is not None:
                parents[subtype] = parent

    types = tuple(member.value for member in substrate_tax.DocumentType)
    type_to_subtypes: dict[str, list[str]] = {doc_type: [] for doc_type in types}
    for subtype in sorted(canonical):
        parent = parents.get(subtype)
        if parent is not None:
            type_to_subtypes.setdefault(parent, []).append(subtype)

    taxonomy = Taxonomy(
        types=types,
        subtypes=tuple(sorted(canonical)),
        subtype_labels=labels,
        subtype_to_type=parents,
        type_to_subtypes={key: tuple(value) for key, value in type_to_subtypes.items()},
        substrate_only=frozenset(substrate_subtypes & SUBSTRATE_ONLY_SUBTYPES),
        overlay=frozenset(set(OVERLAY_SUBTYPES) - substrate_subtypes),
    )
    log.debug(
        "taxonomy.built",
        canonical=len(taxonomy.subtypes),
        overlay=len(taxonomy.overlay),
        substrate_only=len(taxonomy.substrate_only),
    )
    return taxonomy


def parent_type_of(subtype: str) -> str | None:
    """Convenience resolver for :mod:`wc_caseload_engine.doc_controls`."""
    return effective_taxonomy().parent_of(subtype)


# ---------------------------------------------------------------------------
# Drift detection
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TaxonomyDrift:
    """Set-diff between the engine's canonical taxonomy and the classifier source."""

    classifier_source: Path
    engine_count: int
    classifier_count: int
    missing_from_engine: tuple[str, ...]
    extra_in_engine: tuple[str, ...]
    parent_mismatches: tuple[tuple[str, str, str], ...]
    missing_types: tuple[str, ...]
    extra_types: tuple[str, ...]

    @property
    def clean(self) -> bool:
        """``True`` when the engine and the classifier agree exactly."""
        return not (
            self.missing_from_engine
            or self.extra_in_engine
            or self.parent_mismatches
            or self.missing_types
            or self.extra_types
        )

    def render(self) -> str:
        """Human-readable drift report (empty-diff aware)."""
        lines = [
            f"classifier source : {self.classifier_source}",
            f"classifier subtypes: {self.classifier_count}",
            f"engine subtypes    : {self.engine_count}",
        ]
        if self.clean:
            lines.append("drift: none — engine taxonomy matches the classifier exactly")
            return "\n".join(lines)
        if self.missing_types:
            lines.append(f"types missing from engine ({len(self.missing_types)}):")
            lines.extend(f"  - {name}" for name in self.missing_types)
        if self.extra_types:
            lines.append(f"types not in classifier ({len(self.extra_types)}):")
            lines.extend(f"  + {name}" for name in self.extra_types)
        if self.missing_from_engine:
            lines.append(f"subtypes missing from engine ({len(self.missing_from_engine)}):")
            lines.extend(f"  - {name}" for name in self.missing_from_engine)
            lines.append("  fix: add them to OVERLAY_SUBTYPES in taxonomy.py")
        if self.extra_in_engine:
            lines.append(f"subtypes not in classifier ({len(self.extra_in_engine)}):")
            lines.extend(f"  + {name}" for name in self.extra_in_engine)
            lines.append("  fix: add them to SUBSTRATE_ONLY_SUBTYPES in taxonomy.py")
        if self.parent_mismatches:
            lines.append(f"parent-type mismatches ({len(self.parent_mismatches)}):")
            lines.extend(
                f"  ~ {subtype}: engine={engine} classifier={classifier}"
                for subtype, engine, classifier in self.parent_mismatches
            )
        return "\n".join(lines)


def check_taxonomy_drift(
    classifier_source: Path | str | None = None,
    taxonomy: Taxonomy | None = None,
) -> TaxonomyDrift:
    """Diff the engine's canonical taxonomy against the classifier TypeScript source."""
    engine = taxonomy if taxonomy is not None else effective_taxonomy()
    classifier = parse_classifier_taxonomy(classifier_source)

    engine_subtypes = engine.subtype_set
    classifier_subtypes = classifier.subtype_set

    mismatches: list[tuple[str, str, str]] = []
    for subtype in sorted(engine_subtypes & classifier_subtypes):
        engine_parent = engine.parent_of(subtype)
        classifier_parent = classifier.subtype_to_type.get(subtype)
        if engine_parent != classifier_parent:
            mismatches.append((subtype, str(engine_parent), str(classifier_parent)))

    return TaxonomyDrift(
        classifier_source=classifier.source,
        engine_count=len(engine_subtypes),
        classifier_count=len(classifier_subtypes),
        missing_from_engine=tuple(sorted(classifier_subtypes - engine_subtypes)),
        extra_in_engine=tuple(sorted(engine_subtypes - classifier_subtypes)),
        parent_mismatches=tuple(mismatches),
        missing_types=tuple(sorted(set(classifier.types) - set(engine.types))),
        extra_types=tuple(sorted(set(engine.types) - set(classifier.types))),
    )


def resolve_control_keys(keys: Sequence[str], taxonomy: Taxonomy | None = None) -> list[str]:
    """Expand a mixed list of subtype/type keys into canonical subtype keys."""
    engine = taxonomy if taxonomy is not None else effective_taxonomy()
    expanded: list[str] = []
    for key in keys:
        if engine.is_type(key):
            expanded.extend(engine.subtypes_for_type(key))
        else:
            expanded.append(key)
    return expanded


__all__ = [
    "CLASSIFIER_ENV_VAR",
    "EXPECTED_SUBTYPE_COUNT",
    "EXPECTED_TYPE_COUNT",
    "OVERLAY_SUBTYPES",
    "SUBSTRATE_ONLY_SUBTYPES",
    "ClassifierTaxonomy",
    "OverlaySubtype",
    "Taxonomy",
    "TaxonomyDrift",
    "TaxonomySourceError",
    "check_taxonomy_drift",
    "classifier_path",
    "effective_taxonomy",
    "find_classifier",
    "parent_type_of",
    "parse_classifier_taxonomy",
    "resolve_control_keys",
]
