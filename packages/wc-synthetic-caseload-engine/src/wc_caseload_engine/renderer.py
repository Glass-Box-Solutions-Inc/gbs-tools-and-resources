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

**Doctrine content injection.** A planned document may carry
``content_flags`` — the doctrine hooks its subtype is a target for (see
:mod:`wc_caseload_engine.doctrine`). When it does, the resolved template class
is subclassed at render time and its ``build_story`` extended with a trailing
authorities section. The shape of that intervention is deliberate: the base
story is produced by ``super()`` untouched, the appended flowables are plain
``Paragraph``/``Spacer``/``HRFlowable`` objects so the substrate's own
``_story_to_plaintext`` and ``_story_to_docx`` carry them into eml and docx
without further work, and the paragraph choice is drawn from a *private*
:class:`random.Random` rather than the re-seeded global stream, so a flagged
document's pre-existing content is bit-for-bit what it would have been
unflagged. With no flags the wrapper is never built and the code path is the
original one.

Dispatch has one trap worth naming: ``registry.get_template_for_subtype``
answers ``GenericDocumentTemplate`` for keys it does not know, so a missing
template and a deliberate one are the same return value. Every render therefore
records the template it actually used (:attr:`RenderResult.template`) and flags
a degraded dispatch (:attr:`RenderResult.fallback`), and the three overlay
subtypes the substrate enum lacks are resolved here rather than left to fall
through. Silent degradation is the failure mode this module is built to make
impossible.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import hashlib
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import structlog

from wc_caseload_engine import medical_assertions as assertion_module
from wc_caseload_engine.determinism import (
    ensure_deterministic_substrate,
    mark_docx_synthetic,
    normalize_docx,
    normalize_eml,
    normalize_pdf_id,
)
from wc_caseload_engine.doctrine import (
    DOCTRINE_CONTENT,
    MEDICAL_STORY_SIBTF_SECTION_4751_PARAGRAPHS,
    content_flags_for,
    heading_for_register,
    register_for_subtype,
)
from wc_caseload_engine.perspective import file_owner_firm
from wc_caseload_engine.rating import RATING_GROUNDED_DOCTRINE_HOOKS
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

OVERLAY_TEMPLATES: Mapping[str, tuple[str, str]] = {
    # The three classifier subtypes the substrate enum lacks (see
    # ``taxonomy.OVERLAY_SUBTYPES``) reach the registry as unknown keys, and an
    # unknown key silently resolves to ``GenericDocumentTemplate``. The engine
    # invented these keys to reach 353-subtype parity, so the engine owes them a
    # real template. Each maps to the class the substrate already uses for its
    # nearest neighbour — ``PETITION_FOR_PENALTIES`` to the very entry the
    # substrate registers for its own ``PETITION_FOR_PENALTIES_LC_5814``, and
    # the two penalty notices to the class every other ``NOTICE_OF_*`` uses.
    "PETITION_FOR_PENALTIES": ("ApplicationForAdjudication", "Petition for Penalties (LC 5814)"),
    "NOTICE_OF_PENALTY_5814": ("CourtNotice", "penalty_5814"),
    "NOTICE_OF_PENALTY_5814_5": ("CourtNotice", "penalty_5814_5"),
}
"""Engine-owned template resolution for subtypes the substrate registry misses."""

GENERIC_TEMPLATE_CLASS = "GenericDocumentTemplate"
"""The substrate's catch-all — resolving to it is a fallback, not a dispatch."""

_INVARIANT_SET = False


def _ensure_invariant() -> None:
    """Pin ReportLab and freeze the substrate's clock before the first render."""
    global _INVARIANT_SET
    if _INVARIANT_SET:
        return
    ensure_deterministic_substrate()
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
    template: str = ""
    """Resolved template, ``ClassName`` or ``ClassName/variant``.

    Recorded per document so a manifest states *which* template produced a file
    rather than leaving it to be re-derived. A caseload whose dispatch quietly
    degrades is otherwise indistinguishable from one that did not.
    """
    content_flags: tuple[str, ...] = ()
    """Doctrine hooks whose language this file carries.

    Provenance for the same reason :attr:`template` is: a corpus consumer
    grepping for doctrine language needs to know which files were *supposed* to
    contain it, and a file that was flagged but rendered nothing is otherwise
    indistinguishable from one that was never flagged.
    """

    @property
    def fallback(self) -> bool:
        """``True`` when this document did not render as dispatched.

        Covers both degradations: the requested format failed and the document
        fell back to pdf, or the subtype had no registry template and fell
        through to :data:`GENERIC_TEMPLATE_CLASS`.
        """
        return self.fallback_reason is not None


def _format_from_roll(mix: Mapping[str, float], roll: float) -> str:
    """Resolve one already-drawn format roll against the effective mix."""
    upto = 0.0
    for name, weight in sorted(mix.items()):
        upto += weight
        if roll <= upto:
            return name
    return sorted(mix)[-1]


def _story_family_key(
    seed: CaseSeed,
    render_key: tuple[object, ...],
    *suffix: object,
) -> tuple[object, ...]:
    """R46's ``(R, ...)`` suffix under the mandatory case prefix."""
    return ("case", seed.case_id, render_key, *suffix)


def document_seed_for(
    seed: CaseSeed,
    index: int,
    family: str,
    medical_story_render_key: tuple[object, ...] | None,
) -> int:
    """Choose the legacy index seed or R59 semantic family seed."""
    if medical_story_render_key is None:
        legacy_prefix = {
            "document-render": "render",
            "document-scan": "scan",
            "document-pdf-id": "pdfid",
        }[family]
        return derive_seed(seed.rng_seed, f"{legacy_prefix}:{index}")
    return assertion_module._medical_story_seed(
        seed,
        family,
        _story_family_key(seed, medical_story_render_key),
    )


def choose_format(
    seed: CaseSeed,
    index: int,
    *,
    medical_story_render_key: tuple[object, ...] | None = None,
) -> str:
    """Pick a format, retaining the gated legacy draw-and-discard."""
    mix = seed.effective_format_mix()
    legacy_roll = random.Random(
        derive_seed(seed.rng_seed, f"format:{index}")
    ).random()
    if medical_story_render_key is None:
        return _format_from_roll(mix, legacy_roll)
    semantic_roll = assertion_module._medical_story_rng(
        seed,
        "document-format",
        _story_family_key(seed, medical_story_render_key),
    ).random()
    return _format_from_roll(mix, semantic_roll)


def scan_seed_for(
    seed: CaseSeed,
    index: int,
    medical_story_render_key: tuple[object, ...] | None = None,
) -> int:
    """The explicit scan-simulation seed for document *index*.

    Derived with SHA-256 from ``rng_seed`` and the index — never from
    ``hash()``, whose salt changes between processes.
    """
    return document_seed_for(
        seed,
        index,
        "document-scan",
        medical_story_render_key,
    )


def resolve_template(subtype: str) -> tuple[str, str | None]:
    """Resolve a subtype to its ``(class name, variant)`` without loading it.

    The registry returns :data:`GENERIC_TEMPLATE_CLASS` for any key it does not
    know, so "unknown subtype" and "deliberately generic" are the same answer.
    :data:`OVERLAY_TEMPLATES` is consulted first, which is what keeps the
    engine's own overlay subtypes from landing in that indistinguishable bucket.
    """
    overlay = OVERLAY_TEMPLATES.get(subtype)
    if overlay is not None:
        return overlay
    registry = import_substrate("pdf_templates.registry")
    class_name, variant = registry.get_template_for_subtype(subtype)
    return class_name, variant


def template_label(class_name: str, variant: str | None) -> str:
    """``ClassName`` or ``ClassName/variant`` — the manifest's provenance string."""
    return f"{class_name}/{variant}" if variant else class_name


def _load_template(
    subtype: str,
    *,
    fact_aware: bool = False,
    template_subtype: str | None = None,
) -> tuple[type, str | None, str]:
    """Resolve a subtype to (template class, variant, class name).

    When *fact_aware* and the subtype is registered in
    :func:`~wc_caseload_engine.fact_templates.fact_aware_templates`, the
    engine-owned subclass is returned in place of the substrate class. Anything
    unregistered takes the original path unchanged — that is what keeps a case
    with no fact-aware subtype byte-identical to 0.2.0.

    ``template_subtype`` is AJC-62's internal substrate dispatch key (R2): when
    present, the substrate class and registry variant are resolved from IT —
    that is how an ``ADVOCACY_LETTERS_PTP_QME_AME`` manifest carrier reaches
    the registered ``Objection to QME/AME Report`` variant — while the
    canonical subtype keeps naming the manifest, the filename and the
    fact-aware registration. Template provenance records the actually resolved
    class/variant.

    The reported ``class_name`` stays the *substrate* class either way, because
    it is the manifest's ``template`` provenance string and the subclass renders
    the same document through the same base. The subclass is not a fallback and
    must not read as one.
    """
    class_name, variant = resolve_template(template_subtype or subtype)
    if fact_aware:
        from wc_caseload_engine.fact_templates import fact_aware_templates

        override = fact_aware_templates().get(subtype)
        if override is not None:
            return override, variant, class_name
    if class_name == GENERIC_TEMPLATE_CLASS:
        generic = import_substrate("pdf_templates.generic_template")
        return generic.GenericDocumentTemplate, variant, class_name
    registry = import_substrate("pdf_templates.registry")
    return registry.load_template_class(class_name), variant, class_name


def _title_for(subtype: str, taxonomy_label: str | None) -> str:
    """Human document title — the classifier label when there is one."""
    return taxonomy_label or subtype.replace("_", " ").title()


def _md5(payload: bytes) -> str:
    """MD5 of file bytes (manifest checksum field)."""
    return hashlib.md5(payload, usedforsecurity=False).hexdigest()


# ---------------------------------------------------------------------------
# AJC-62 (M3) — the AJC-65 and AJC-66 governance seams (R12/R13, R77 step 7)
# ---------------------------------------------------------------------------

AJC66_LETTER_TEMPLATE_SUBTYPES: frozenset[str] = frozenset(
    {
        "ADVOCACY_LETTERS_PTP",
        "ADVOCACY_LETTERS_QME",
        "ADVOCACY_LETTERS_AME",
        "ADVOCACY_LETTERS_PTP_QME_AME",
        "OBJECTION_TO_QME_AME_REPORT",
        "REQUEST_SUPPLEMENTAL_QME_AME_REPORT",
    }
)
"""Template subtypes whose registered AJC-66 variant family is ``letter`` (R2)."""

AJC66_DEPOSITION_TEMPLATE_SUBTYPES: frozenset[str] = frozenset(
    {
        "DEPOSITION_TRANSCRIPT_QME_AME",
    }
)
"""Template subtypes whose registered AJC-66 family is ``deposition_transcript``."""


def ajc66_variant_content(template_subtype: str | None) -> dict[str, bool] | None:
    """R13 — the family-scoped AJC-66 switch for one internal dispatch key.

    Only the applicable namespaced switch is ever set: ``{"letter": True}``
    for the advocacy/objection/request registered variants and
    ``{"deposition_transcript": True}`` for the QME/AME deposition. M3 never
    sets global ``True`` — under the substrate's namespaced contract a global
    switch would opt diagnostic, hospital and deposition-notice families into
    variant content in documents whose author never asked for any of it —
    and a key that is absent, ``False`` or ``{}`` reads as off everywhere.
    ``None`` means "set nothing": supplemental-report carriers and every
    non-loop dispatch stay exactly as they were.
    """
    if template_subtype in AJC66_LETTER_TEMPLATE_SUBTYPES:
        return {"letter": True}
    if template_subtype in AJC66_DEPOSITION_TEMPLATE_SUBTYPES:
        return {"deposition_transcript": True}
    return None


def _row_basis_text(row: Any) -> str:
    """The stated basis for one apportionment row, from its semantic fields."""
    if row.description:
        return str(row.description)
    if row.basis_kinds:
        return ", ".join(kind.replace("_", " ") for kind in row.basis_kinds)
    return "nonindustrial factors"


def _single_row_opinion(row: Any) -> str:
    """A determined single-split conclusion, composed from semantic fields only."""
    part = row.body_part.replace("_", " ")
    sentences = [
        f"As to the {part}, {row.nonindustrial_percent} percent of the current "
        f"permanent disability is apportioned to {_row_basis_text(row)} and "
        f"{row.industrial_percent} percent is caused by the industrial injury, "
        "per Labor Code sections 4663 and 4664."
    ]
    if row.causal_rationale:
        sentences.append(str(row.causal_rationale))
    if row.percentage_rationale:
        sentences.append(str(row.percentage_rationale))
    if row.reasonable_medical_probability:
        sentences.append(
            "This apportionment is stated to a reasonable degree of medical "
            "probability."
        )
    return " ".join(sentences)


def _plural_row_sentences(rows: Sequence[Any]) -> list[str]:
    """One per-body-part sentence per row, in ledger order."""
    sentences = []
    for row in rows:
        part = row.body_part.replace("_", " ")
        sentences.append(
            f"As to the {part}, {row.nonindustrial_percent} percent of the "
            f"permanent disability is apportioned to {_row_basis_text(row)} "
            f"and {row.industrial_percent} percent is caused by the "
            "industrial injury."
        )
    return sentences


def _ajc65_apportionment_block(
    opinion: Any, rows: Sequence[Any]
) -> dict[str, Any] | None:
    """R12 — the frozen opinion-state → AJC-65 projection mapping.

    Lossless by construction: every branch renders exactly the semantic state
    the ledger carries, and no branch invents a number the evaluator never
    stated. ``None`` means the opinion does not govern apportionment (an
    ``omitted`` state), so the substrate's own legacy behaviour stands.
    """
    if opinion.apportionment_state == "deferred":
        # Deferred: register only, no percentage — the substrate renders its
        # own §4663/§4664 reservation language from the register.
        return {"register": "deferred"}
    if opinion.determination_kind == "no_nonindustrial_share":
        reasoned = opinion.determination_rationale or (
            "The entire permanent disability is caused by the industrial "
            "injury. This conclusion rests on the history obtained, the "
            "records reviewed, and the examination findings documented in "
            "this report."
        )
        return {"register": "none", "nonindustrial_pct": 0, "opinion": reasoned}
    if opinion.determination_kind == "unable_to_approximate":
        # Prose-only: no percentage exists and none may be invented.
        prose = opinion.determination_rationale or (
            "The relative contributions of industrial and nonindustrial "
            "factors to the current permanent disability cannot be "
            "approximated on this record within reasonable medical "
            "probability, and no percentage allocation is stated."
        )
        return {"opinion": prose}
    if not rows:
        return None
    if len(rows) == 1:
        row = rows[0]
        return {
            "register": "apportioned",
            "nonindustrial_pct": row.nonindustrial_percent,
            "basis": _row_basis_text(row),
            "opinion": _single_row_opinion(row),
        }
    shares = {row.nonindustrial_percent for row in rows}
    if len(shares) == 1:
        common = rows[0].nonindustrial_percent
        return {
            "register": "apportioned",
            "nonindustrial_pct": common,
            "basis": _row_basis_text(rows[0]),
            "opinion": " ".join(
                [
                    f"For each body part addressed below, {common} percent of "
                    "the permanent disability is apportioned to nonindustrial "
                    "factors per Labor Code sections 4663 and 4664.",
                    *_plural_row_sentences(rows),
                ]
            ),
        }
    # R12 — heterogeneous plural rows are PROSE-ONLY. The rows carry different
    # nonindustrial percentages, so no single scalar exists: an average, a
    # maximum, a first row or a "primary" body part would each state a split
    # the evaluator never made. AJC-65 suppresses its scalar impairment block
    # on a prose-only opinion, and the wcce subclass renders the body-part
    # table in its place.
    return {
        "opinion": " ".join(
            [
                "Apportionment of permanent disability is determined "
                "separately for each body part, per Labor Code sections 4663 "
                "and 4664.",
                *_plural_row_sentences(rows),
            ]
        )
    }


def _ajc65_causation_block(opinion: Any) -> dict[str, str]:
    """R12 — the causation projection for one bound medical opinion."""
    discussion: str | None = None
    if opinion.aoe_coe_rationale:
        discussion = str(opinion.aoe_coe_rationale)
    elif opinion.aoe_coe_finding == "nonindustrial":
        discussion = (
            "It is my opinion, within reasonable medical probability, that "
            "the current condition did not arise out of and in the course of "
            "employment. The available history, records, and examination "
            "findings do not establish industrial causation."
        )
    elif opinion.aoe_coe_finding == "deferred":
        discussion = (
            "The determination of whether the condition arose out of and in "
            "the course of employment is deferred pending receipt and review "
            "of the outstanding records identified in this report."
        )
    elif opinion.rationale:
        discussion = str(opinion.rationale)
    attribution = (
        "entirely"
        if opinion.determination_kind == "no_nonindustrial_share"
        else "predominantly"
    )
    block: dict[str, str] = {"attribution": attribution}
    if discussion:
        block["discussion"] = discussion
    return block


def ajc65_story_governance(story: Any) -> dict[str, dict[str, Any]]:
    """R12 — the AJC-65 context blocks for one document's bound opinion.

    Empty for a history-only document: with no bound opinion there is nothing
    to govern, and the substrate's own draws stand exactly as they did. The
    same returned objects govern the impairment and conclusion call sites,
    because the substrate parses this context once and renders both sections
    from the single parsed decision.
    """
    opinion = getattr(story, "medical_opinion", None)
    if opinion is None:
        return {}
    governance: dict[str, dict[str, Any]] = {
        "causation": _ajc65_causation_block(opinion)
    }
    apportionment = _ajc65_apportionment_block(opinion, tuple(story.apportionments))
    if apportionment is not None:
        governance["apportionment"] = apportionment
    return governance


# ---------------------------------------------------------------------------
# Doctrine content injection
# ---------------------------------------------------------------------------

DOCTRINE_CLASS_SUFFIX = "WithDoctrine"
"""Appended to a template class name when it is wrapped for content injection.

Named rather than inlined so a test can tell a wrapped dispatch from a plain
one without matching on a string literal it also has to keep in sync.
"""


def doctrine_flowables(
    template: Any,
    *,
    subtype: str,
    seed: CaseSeed,
    index: int,
    content_flags: Sequence[str],
    medical_story_enabled: bool = False,
    medical_story_render_key: tuple[object, ...] | None = None,
) -> list[Any]:
    """The authorities section appended to a flagged document's story.

    Built from the *base template's own* style sheet and rules, so the section
    looks like the rest of the document rather than like something bolted on.
    Each flagged hook contributes one paragraph — chosen with a private
    :class:`random.Random` seeded from ``rng_seed`` and the hook name, never
    from the global stream the substrate templates draw from — followed by the
    controlling authority.

    Returns an empty list when no flagged hook has content for *subtype*, so a
    heading is never emitted over nothing.
    """
    from reportlab.platypus import Paragraph, Spacer

    styles = template.styles
    body: list[Any] = []
    for hook in sorted(set(content_flags)):
        content = DOCTRINE_CONTENT.get(hook)
        if content is None:
            log.warning("render.unknown_doctrine_hook", hook=hook, subtype=subtype)
            continue
        pool = (
            MEDICAL_STORY_SIBTF_SECTION_4751_PARAGRAPHS
            if medical_story_enabled and hook == "sibtf"
            else content.paragraphs_for(subtype)
        )
        if not pool:
            continue
        if medical_story_render_key is None:
            rng = random.Random(
                derive_seed(seed.rng_seed, f"doctrine:{index}:{hook}")
            )
        else:
            rng = assertion_module._medical_story_rng(
                seed,
                "document-doctrine",
                _story_family_key(seed, medical_story_render_key, hook),
            )
        body.append(Paragraph(rng.choice(pool), styles["BodyText14"]))
        body.append(Paragraph(content.citation, styles["SmallItalic"]))
        facts = getattr(template, "_wc_case_facts", None)
        rating = getattr(facts, "rating", None)
        if hook in RATING_GROUNDED_DOCTRINE_HOOKS and rating is not None:
            body.append(
                Paragraph(
                    "Selected unapportioned permanent disability rating: "
                    f"{rating.final_pd_percent}%.",
                    styles["BodyText14"],
                )
            )
            if hook == "kite" and rating.combination_method == "kite_addition":
                body.append(
                    Paragraph(
                        "Explicit Kite addition selected; scheduled CVC comparator: "
                        f"{rating.scheduled_combined_rating}%.",
                        styles["BodyText14"],
                    )
                )
        body.append(Spacer(1, 8))

    if not body:
        return []

    heading = heading_for_register(register_for_subtype(subtype))
    return [
        Spacer(1, 16),
        template.make_hr(),
        Paragraph(heading, styles["SectionHeader"]),
        *body,
    ]


def doctrine_template_class(base: type, section_builder: Any) -> type:
    """Subclass *base* so its story gains the section *section_builder* returns.

    The substrate is consumed as a read-only library, so injection happens by
    subclassing rather than by patching: the wrapper calls ``super()`` for the
    document the template would otherwise have produced and appends to the
    result. ``section_builder(template, doc_spec)`` returns the flowables to
    append.
    """

    def build_story(self: Any, doc_spec: Any) -> list[Any]:
        # ``wrapper`` is bound below, before this ever runs — the two-argument
        # ``super()`` is required because this function is not defined inside a
        # class body and so has no ``__class__`` cell to close over.
        story = list(super(wrapper, self).build_story(doc_spec))
        story.extend(section_builder(self, doc_spec))
        return story

    wrapper = type(
        f"{base.__name__}{DOCTRINE_CLASS_SUFFIX}",
        (base,),
        {
            "build_story": build_story,
            "__doc__": f"{base.__name__} with a doctrine authorities section appended.",
        },
    )
    return wrapper


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
    author_role: str | None = None,
    recipient_role: str | None = None,
    content_flags: Sequence[str] = (),
    case_facts: Any = None,
    money_facts: Any = None,
    reserve_event: Any = None,
    packet_index: int | None = None,
    report_ordinal: int | None = None,
    letter_ordinal: int | None = None,
    cadence_anchors: tuple[tuple[str, date], ...] = (),
    template_subtype: str | None = None,
    medical_story: Any = None,
    contention_actor_party: str | None = None,
    defense_contest_theories: Sequence[str] = (),
    imr_application_content: Any = None,
    imr_outcome: str | None = None,
    medical_story_render_key: tuple[object, ...] | None = None,
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
        author_role: who wrote it, from the file owner's point of view.
        recipient_role: who received it, likewise.
        content_flags: doctrine hooks whose language this document carries
            (:attr:`~wc_caseload_engine.planner.PlannedDocument.content_flags`).
            Empty is the original code path exactly — no wrapper class is built
            and nothing is appended.
        case_facts: the clinical ledger, or ``None``.
        money_facts: the money spine, or ``None`` — which is the state for
            every seed that carries no ``scenario.wages``. The money-aware
            templates all delegate straight to the substrate on ``None``, so a
            case with no money layer renders through the unmodified path even
            for the subtypes the money registry claims.
        reserve_event: the exact bound InitialFileReview or ReserveEvent for a
            reserve artifact. It is never selected or reconstructed here.
        template_subtype: AJC-62's internal substrate dispatch key (R2), or
            ``None`` for every pre-M3 document. Resolves the substrate class
            and registry variant while ``subtype`` stays the canonical
            manifest carrier.
        medical_story: this document's
            :class:`~wc_caseload_engine.medical_story.DocumentMedicalStory`,
            or ``None``. ``None`` is the exact pre-M3 render path: no new
            context key, no AJC-65 block, no AJC-66 switch (R1).
        contention_actor_party: the bound acting party for a contention-loop
            communication or deposition, threaded to the subclasses through
            the story context (R14/R35).
        defense_contest_theories: the bound defense theories, in their frozen
            tuple order (R30).
        imr_application_content: R39's sparse, denial-bound application fields.
        imr_outcome: the one R57 outcome carried by the governed IMR decision.
        medical_story_render_key: R45/R59 final semantic render identity. When
            absent, every legacy index-salted renderer path remains exact.

    Returns:
        A :class:`RenderResult` with the checksum and size for the manifest.
    """
    _ensure_invariant()
    models = import_substrate("data.models")

    template_class, variant, class_name = _load_template(
        subtype,
        fact_aware=case_facts is not None or reserve_event is not None,
        template_subtype=template_subtype,
    )
    output_format = models.OutputFormat(doc_format if doc_format != "scanned_pdf" else "pdf")

    # Canonicalize before anything is decided by it. ``render_document`` is
    # public and takes whatever it is handed — duplicates, arbitrary order,
    # hooks that do not exist, hooks with no content for *this* subtype — while
    # ``doctrine_flowables`` silently skips the last two. Storing the request
    # rather than what was applied would let a document's own provenance claim
    # doctrines it does not contain a word of, which is the same class of
    # untrue-manifest bug as a fallback that does not say so.
    flags = content_flags_for(content_flags, subtype)
    if flags:
        # Wrap once, before every construction below (including the format
        # fallback's second attempt), so a flagged document cannot lose its
        # doctrine section by falling back to pdf.
        template_class = doctrine_template_class(
            template_class,
            lambda template, _doc_spec: doctrine_flowables(
                template,
                subtype=subtype,
                seed=seed,
                index=index,
                content_flags=flags,
                medical_story_enabled=medical_story is not None,
                medical_story_render_key=medical_story_render_key,
            ),
        )

    context: dict[str, Any] = {}
    if variant:
        # The substrate never wires the registry's variant into the spec, so
        # UR/QME/TPR templates would all render their default flavour.
        context["variant"] = variant

    # Point of view. The substrate reads only ``_accumulator`` off the context,
    # so these keys reach the templates that grow to want them and are inert in
    # the rest — the honest state of a bridge we do not edit. The one visible
    # consequence today is the docx letterhead, which is hard-coded to the
    # applicant firm and therefore wrong on a defense file (README limitation).
    if case_facts is not None:
        # The seam doctrine injection already uses. Substrate templates ignore
        # unknown context keys, so this is inert for every class that has not
        # opted in via FACT_AWARE_TEMPLATES.
        context["case_facts"] = case_facts
        context["document_index"] = index
        # Restores the substrate's own round-robin. ``SubpoenaedRecords``
        # reads ``provider_index`` and indexes ``case.prior_providers``; the
        # engine path never set it, so every packet in every case was answered
        # by the treating physician — a subpoena to four providers, returned
        # four times by one clinic. ``packet_index`` counts packets, not
        # documents, so consecutive packets land on different providers.
        packet = packet_index if packet_index is not None else index
        # ISC-126. Which records packet this is, so the template can read its
        # own page budget off the ledger instead of drawing one.
        context["packet_ordinal"] = packet
        if case_facts.providers:
            context["provider_index"] = packet % len(case_facts.providers)
        # Same reasoning, different axis: the trajectory advances per treating
        # report, so it needs a report ordinal rather than a document index.
        context["report_ordinal"] = report_ordinal if report_ordinal is not None else 0
        # Same axis again for adjuster letters, whose *type* sequence has to
        # advance per letter so a case cannot accept the claim three times.
        context["letter_ordinal"] = letter_ordinal if letter_ordinal is not None else 0
        # ISC-125. The events in this file a client letter may refer back to.
        # Passed whole rather than pre-selected: the template knows its own
        # doc_date and picks the most recent anchor preceding it, so the
        # reference cannot name a document dated after the letter citing it.
        context["cadence_anchors"] = cadence_anchors
    if reserve_event is not None:
        context["reserve_event"] = reserve_event
    context["perspective"] = seed.perspective
    # Whether this file carries a Medicare set-aside. ``lifecycle.resolution.msa``
    # already governs it, and the release needs it to decide whether to print an
    # allocation row — a release printing one for a seed that said `msa: false`
    # contradicts a fact the schema owns.
    context["medicare_set_aside"] = bool(
        getattr(getattr(seed.lifecycle, "resolution", None), "msa", False)
    )
    context["file_owner_firm"] = file_owner_firm(
        seed.perspective, cast.applicant_firm, cast.defense_firm
    )
    if author_role:
        context["author_role"] = author_role
    if recipient_role:
        context["recipient_role"] = recipient_role

    if medical_story is not None:
        # AJC-62 (M3). Every key below is gated on the story's presence: the
        # medical-story-absent path constructs no new renderer context key,
        # no AJC-65 block and no AJC-66 switch (R1).
        context["medical_story"] = medical_story
        context["medical_story_firms"] = {
            "applicant": cast.applicant_firm,
            "defense": cast.defense_firm,
        }
        if contention_actor_party is not None:
            context["contention_actor_party"] = contention_actor_party
        if defense_contest_theories:
            context["defense_contest_theories"] = tuple(defense_contest_theories)
        # R12 — the AJC-65 seam: causation and apportionment derived from the
        # bound opinion through the frozen state mapping. The same parsed
        # objects govern the impairment and conclusion call sites.
        context.update(ajc65_story_governance(medical_story))
        # R13 — the AJC-66 seam: only the bound letter or deposition family
        # activates, and only through its namespaced switch.
        variant_switch = ajc66_variant_content(template_subtype)
        if variant_switch is not None:
            context["variant_content"] = variant_switch
    if imr_application_content is not None:
        context["imr_application_content"] = imr_application_content
        context["imr_applicant_firm"] = cast.applicant_firm
    if imr_outcome is not None:
        context["imr_outcome"] = imr_outcome

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

    if class_name == GENERIC_TEMPLATE_CLASS:
        # Not an error — the generic template renders a real document — but it
        # is a *degraded* dispatch, and the manifest says so rather than
        # presenting it as the subtype's own template.
        fallback_reason = f"no registry template for {subtype}; rendered by {class_name}"
        log.warning("render.generic_fallback", case_id=seed.case_id, subtype=subtype)

    # Re-pin the global stream the substrate templates draw from. R59 replaces
    # the gated index salt with the document's semantic R identity; the absent
    # path remains the exact legacy seed.
    render_seed = document_seed_for(
        seed,
        index,
        "document-render",
        medical_story_render_key,
    )
    random.seed(render_seed)

    template = template_class(cast.case)
    if case_facts is not None:
        # ``_build_diagnostic_review`` / ``_build_treatment_plan`` are called
        # without the doc_spec, so the ledger has to reach them off the
        # instance rather than the context alone.
        template._wc_case_facts = case_facts
    if money_facts is not None:
        template._wc_money_facts = money_facts
    if reserve_event is not None:
        template._wc_reserve_event = reserve_event
    try:
        template.generate(out_path, spec)
    except Exception as exc:
        if doc_format == "pdf":
            raise
        format_reason = (
            f"{class_name} could not render {subtype} as {doc_format} "
            f"({type(exc).__name__}: {exc}); fell back to pdf"
        )
        # A generic-template dispatch that then loses its format is two
        # degradations, not one; keep both reasons.
        fallback_reason = (
            f"{fallback_reason}; {format_reason}" if fallback_reason else format_reason
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
        random.seed(render_seed)
        retry = template_class(cast.case)
        if case_facts is not None:
            retry._wc_case_facts = case_facts
        if money_facts is not None:
            retry._wc_money_facts = money_facts
        if reserve_event is not None:
            retry._wc_reserve_event = reserve_event
        retry.generate(out_path, spec)

    payload = out_path.read_bytes()

    if effective_format == "scanned_pdf":
        # Never let the substrate derive the scan seed from hash().
        scan_simulator = import_substrate("pdf_templates.scan_simulator")
        scan_seed = scan_seed_for(seed, index, medical_story_render_key)
        scan_rng = random.Random(scan_seed)
        payload = scan_simulator.simulate_scan(payload, scan_rng, doc_date=doc_date)
        payload = normalize_pdf_id(payload, scan_seed)
        out_path.write_bytes(payload)
    elif effective_format == "pdf":
        normalized = normalize_pdf_id(
            payload,
            document_seed_for(
                seed,
                index,
                "document-pdf-id",
                medical_story_render_key,
            ),
        )
        if normalized != payload:
            out_path.write_bytes(normalized)
            payload = normalized
    elif effective_format == "docx":
        # Mark first, repack second: the ZIP normalization must be the last
        # thing that touches the file, or the marker's save re-stamps the
        # entry times it just fixed.
        mark_docx_synthetic(out_path)
        payload = normalize_docx(out_path, doc_date)
    elif effective_format == "eml":
        # The substrate's Date header resolves a naive datetime in local time.
        payload = normalize_eml(out_path, doc_date)

    return RenderResult(
        path=out_path,
        subtype=subtype,
        doc_format=effective_format,
        doc_date=doc_date,
        size=len(payload),
        md5=_md5(payload),
        mime_type=MIME_TYPES[effective_format],
        fallback_reason=fallback_reason,
        template=template_label(class_name, variant),
        content_flags=flags,
    )


__all__ = [
    "AJC66_DEPOSITION_TEMPLATE_SUBTYPES",
    "AJC66_LETTER_TEMPLATE_SUBTYPES",
    "DOCTRINE_CLASS_SUFFIX",
    "FORMAT_EXTENSIONS",
    "GENERIC_TEMPLATE_CLASS",
    "MIME_TYPES",
    "OVERLAY_TEMPLATES",
    "RenderResult",
    "ajc65_story_governance",
    "ajc66_variant_content",
    "choose_format",
    "doctrine_flowables",
    "doctrine_template_class",
    "document_seed_for",
    "normalize_pdf_id",
    "render_document",
    "resolve_template",
    "scan_seed_for",
    "template_label",
]
