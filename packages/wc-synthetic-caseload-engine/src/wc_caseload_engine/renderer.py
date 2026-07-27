"""Rendering bridge — planned documents to real files, reproducibly.

Dispatch itself is simple: resolve the subtype through the substrate template
registry, build a document spec, call ``BaseTemplate.generate()``. What takes
care is *determinism*, because the substrate leaks non-reproducible state in
four places. Each is neutralized here, and each fix is the reason a caseload
regenerates byte-for-byte:

1. **Global RNG.** Every substrate template draws from the module-global
   :mod:`random` stream (``lorem_medical``, ``impairment_rating_section``, ...),
   so a document's content depended on how many documents rendered before it.
   :func:`render_document` re-seeds that stream per document from
   ``rng_seed`` + document index.

2. **Scan seeding via ``hash()``.** ``BaseTemplate._generate_scanned_pdf``
   derives its scan seed from ``hash(title + date)``, and Python salts string
   hashing with ``PYTHONHASHSEED``. Scanned output therefore differed between
   processes. This module never takes that path: it renders a native PDF and
   calls ``simulate_scan`` itself with an explicitly seeded
   :class:`random.Random`.

3. **PDF ``/ID`` and creation date.** ReportLab stamps a wall-clock creation
   date and a random file ID; PyMuPDF stamps its own ``/ID`` on the scanned
   rewrite. ``reportlab.rl_config.invariant`` fixes the former;
   :func:`normalize_pdf_id` rewrites the latter in place, preserving length so
   every byte offset in the xref table stays valid.

4. **Generic-template loading.** The substrate's ``load_template_class``
   falls back through ``orchestration.pipeline``, which imports ``dotenv`` and
   other service-only dependencies. The generic template is imported directly.

Format assignment honours ``seed.effective_format_mix()``; when a subtype and
format cannot be paired the renderer falls back to pdf and says so.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import hashlib
import random
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import structlog

from wc_caseload_engine.determinism import (
    ensure_invariant_pdfs,
    normalize_docx,
    normalize_pdf_id,
)
from wc_caseload_engine.seeds import CaseSeed, derive_seed
from wc_caseload_engine.substrate import import_substrate

log = structlog.get_logger(__name__)

FORMAT_EXTENSIONS: Mapping[str, str] = {
    "pdf": "pdf",
    "scanned_pdf": "pdf",
    "eml": "eml",
    "docx": "docx",
}
"""Output format -> file extension (a scanned PDF is still a ``.pdf``)."""

MIME_TYPES: Mapping[str, str] = {
    "pdf": "application/pdf",
    "scanned_pdf": "application/pdf",
    "eml": "message/rfc822",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
"""Output format -> MIME type recorded in the manifest."""

_INVARIANT_SET = False


def _ensure_invariant() -> None:
    """Pin ReportLab to invariant output (fixed timestamps, fixed file id)."""
    global _INVARIANT_SET
    if _INVARIANT_SET:
        return
    ensure_invariant_pdfs()
    _INVARIANT_SET = True


@dataclass(frozen=True, slots=True)
class _SubtypeProxy:
    """Duck-typed stand-in for the substrate's ``DocumentSubtype`` enum member.

    The engine's canonical taxonomy carries three overlay subtypes the
    substrate enum does not, so a real enum member cannot always be built.
    Templates only ever read ``.value``.
    """

    value: str

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


@dataclass(slots=True)
class _DocumentSpec:
    """Duck-typed stand-in for the substrate's ``DocumentSpec`` model."""

    subtype: _SubtypeProxy
    title: str
    doc_date: date
    template_class: str
    output_format: Any
    context: dict[str, Any] = field(default_factory=dict)
    sequence_number: int = 1


@dataclass(frozen=True, slots=True)
class RenderResult:
    """One rendered file on disk."""

    path: Path
    subtype: str
    doc_format: str
    doc_date: date
    size: int
    md5: str
    mime_type: str
    fallback_reason: str | None = None


def choose_format(seed: CaseSeed, index: int) -> str:
    """Pick an output format for document *index* from the seed's weights."""
    mix = seed.effective_format_mix()
    rng = random.Random(derive_seed(seed.rng_seed, f"format:{index}"))
    roll = rng.random()
    upto = 0.0
    for name, weight in sorted(mix.items()):
        upto += weight
        if roll <= upto:
            return name
    return sorted(mix)[-1]


def scan_seed_for(seed: CaseSeed, index: int) -> int:
    """The explicit scan-simulation seed for document *index*.

    Derived with SHA-256 from ``rng_seed`` and the index — never from
    ``hash()``, whose salt changes between processes.
    """
    return derive_seed(seed.rng_seed, f"scan:{index}")


def _load_template(subtype: str) -> tuple[type, str | None, str]:
    """Resolve a subtype to (template class, variant, class name)."""
    registry = import_substrate("pdf_templates.registry")
    class_name, variant = registry.get_template_for_subtype(subtype)
    if class_name == "GenericDocumentTemplate":
        generic = import_substrate("pdf_templates.generic_template")
        return generic.GenericDocumentTemplate, variant, class_name
    return registry.load_template_class(class_name), variant, class_name


def _title_for(subtype: str, taxonomy_label: str | None) -> str:
    """Human document title — the classifier label when there is one."""
    return taxonomy_label or subtype.replace("_", " ").title()


def _md5(payload: bytes) -> str:
    """MD5 of file bytes (manifest checksum field)."""
    return hashlib.md5(payload, usedforsecurity=False).hexdigest()


def render_document(
    *,
    seed: CaseSeed,
    cast: Any,
    subtype: str,
    doc_date: date,
    doc_format: str,
    index: int,
    out_path: Path,
    title: str | None = None,
) -> RenderResult:
    """Render one planned document to *out_path*, reproducibly.

    Args:
        seed: the case seed (supplies every random draw).
        cast: the :class:`~wc_caseload_engine.case_context.CaseCast` for the case.
        subtype: canonical classifier subtype key.
        doc_date: the document's date.
        doc_format: ``pdf`` | ``scanned_pdf`` | ``eml`` | ``docx``.
        index: document index within the case — seeds content and scan noise.
        out_path: destination file (extension included).
        title: document title; defaults to the taxonomy label.

    Returns:
        A :class:`RenderResult` with the checksum and size for the manifest.
    """
    _ensure_invariant()
    models = import_substrate("data.models")

    template_class, variant, class_name = _load_template(subtype)
    output_format = models.OutputFormat(doc_format if doc_format != "scanned_pdf" else "pdf")

    context: dict[str, Any] = {}
    if variant:
        # The substrate never wires the registry's variant into the spec, so
        # UR/QME/TPR templates would all render their default flavour.
        context["variant"] = variant

    spec = _DocumentSpec(
        subtype=_SubtypeProxy(subtype),
        title=title or _title_for(subtype, None),
        doc_date=doc_date,
        template_class=class_name,
        output_format=output_format,
        context=context,
        sequence_number=index + 1,
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fallback_reason: str | None = None
    effective_format = doc_format

    # Re-pin the global stream the substrate templates draw from.
    random.seed(derive_seed(seed.rng_seed, f"render:{index}"))

    template = template_class(cast.case)
    try:
        template.generate(out_path, spec)
    except Exception as exc:
        if doc_format == "pdf":
            raise
        fallback_reason = (
            f"{class_name} could not render {subtype} as {doc_format} "
            f"({type(exc).__name__}: {exc}); fell back to pdf"
        )
        log.warning(
            "render.format_fallback",
            case_id=seed.case_id,
            subtype=subtype,
            requested=doc_format,
            template=class_name,
            error=str(exc),
        )
        effective_format = "pdf"
        spec.output_format = models.OutputFormat("pdf")
        out_path = out_path.with_suffix(".pdf")
        random.seed(derive_seed(seed.rng_seed, f"render:{index}"))
        template_class(cast.case).generate(out_path, spec)

    payload = out_path.read_bytes()

    if effective_format == "scanned_pdf":
        # Never let the substrate derive the scan seed from hash().
        scan_simulator = import_substrate("pdf_templates.scan_simulator")
        scan_rng = random.Random(scan_seed_for(seed, index))
        payload = scan_simulator.simulate_scan(payload, scan_rng, doc_date=doc_date)
        payload = normalize_pdf_id(payload, scan_seed_for(seed, index))
        out_path.write_bytes(payload)
    elif effective_format == "pdf":
        normalized = normalize_pdf_id(payload, derive_seed(seed.rng_seed, f"pdfid:{index}"))
        if normalized != payload:
            out_path.write_bytes(normalized)
            payload = normalized
    elif effective_format == "docx":
        # python-docx stamps wall-clock ZIP entry times; repack them stably.
        payload = normalize_docx(out_path, doc_date)

    return RenderResult(
        path=out_path,
        subtype=subtype,
        doc_format=effective_format,
        doc_date=doc_date,
        size=len(payload),
        md5=_md5(payload),
        mime_type=MIME_TYPES[effective_format],
        fallback_reason=fallback_reason,
    )


__all__ = [
    "FORMAT_EXTENSIONS",
    "MIME_TYPES",
    "RenderResult",
    "choose_format",
    "normalize_pdf_id",
    "render_document",
    "scan_seed_for",
]
