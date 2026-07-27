"""Composition: three machines, one control resolver, one ordered case plan.

This is where the seed becomes a concrete list of documents. The core
lifecycle, the lien tracks and the reconsideration round trip each propose
dated candidates; :func:`~wc_caseload_engine.doc_controls.resolve_document_controls`
decides the final count per subtype; this module turns those counts back into
individually dated, formatted, ordered documents.

The count-then-redate shape matters: the control resolver deliberately works in
counts (so its precedence rules stay pure and unit-testable, with no dates in
sight), which means dates must be re-attached afterwards. Candidates keep their
own dates; a control that demands *more* copies than the lifecycle proposed
gets deterministically synthesized dates continuing the same series.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

import structlog

from wc_caseload_engine.case_context import CaseCast, build_case_cast
from wc_caseload_engine.doc_controls import (
    TRACK_CORE,
    ControlResolution,
    resolve_document_controls,
)
from wc_caseload_engine.lien_machine import LienTrack, build_lien_tracks, lien_candidates
from wc_caseload_engine.lifecycle_bridge import (
    CaseTimeline,
    DatedCandidate,
    author_role_for,
    build_core_candidates,
    build_timeline,
    to_document_candidates,
)
from wc_caseload_engine.recon_machine import ReconTrack, build_recon_track
from wc_caseload_engine.renderer import choose_format
from wc_caseload_engine.seeds import CaseSeed
from wc_caseload_engine.taxonomy import effective_taxonomy, parent_type_of

log = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class PlannedDocument:
    """One document, fully decided: what it is, when it is, how it renders."""

    index: int
    subtype: str
    parent_type: str | None
    doc_date: date
    doc_format: str
    track: str
    author_role: str
    title: str


@dataclass(frozen=True, slots=True)
class CasePlan:
    """Everything needed to render and manifest one case."""

    seed: CaseSeed
    timeline: CaseTimeline
    cast: CaseCast
    documents: tuple[PlannedDocument, ...]
    lien_tracks: tuple[LienTrack, ...]
    recon: ReconTrack
    control: ControlResolution
    warnings: tuple[str, ...] = ()

    @property
    def document_count(self) -> int:
        """Number of documents this case will emit."""
        return len(self.documents)

    def format_counts(self) -> dict[str, int]:
        """Documents per output format."""
        counts: dict[str, int] = {}
        for document in self.documents:
            counts[document.doc_format] = counts.get(document.doc_format, 0) + 1
        return counts

    def track_counts(self) -> dict[str, int]:
        """Documents per track."""
        counts: dict[str, int] = {}
        for document in self.documents:
            counts[document.track] = counts.get(document.track, 0) + 1
        return counts


def _synthesize_dates(
    seed: CaseSeed,
    timeline: CaseTimeline,
    subtype: str,
    existing: list[DatedCandidate],
    needed: int,
) -> list[date]:
    """Deterministic dates for copies the lifecycle never proposed.

    A per-subtype override may demand more documents than the case naturally
    produced (or demand a subtype it never produced at all). Extra copies
    continue the existing series; a subtype with no series at all is spread
    across the case's active span.
    """
    rng = seed.rng(f"extra:{subtype}")
    out: list[date] = []
    if existing:
        cursor = existing[-1].doc_date
        for _ in range(needed):
            cursor = timeline.clamp(cursor + timedelta(days=rng.randint(7, 60)))
            out.append(cursor)
        return out

    span_end = timeline.resolution_date or timeline.horizon
    span_days = max((span_end - timeline.injury_date).days, 1)
    for _ in range(needed):
        out.append(timeline.clamp(timeline.injury_date + timedelta(days=rng.randint(1, span_days))))
    return sorted(out)


def build_case_plan(seed: CaseSeed, case_number: int = 1) -> CasePlan:
    """Turn one seed into a fully decided case plan.

    Args:
        seed: the case seed.
        case_number: position in the caseload (feeds the substrate's internal id).

    Returns:
        A :class:`CasePlan` — ordered documents, cast, tracks and the audit
        trail of every control decision.
    """
    taxonomy = effective_taxonomy()
    timeline = build_timeline(seed)

    core = build_core_candidates(seed, timeline)
    lien_tracks = build_lien_tracks(seed, timeline)
    recon = build_recon_track(seed, timeline)

    candidates: list[DatedCandidate] = [*core, *lien_candidates(lien_tracks), *recon.documents]

    control = resolve_document_controls(
        to_document_candidates(candidates),
        seed.documents,
        parent_type_of=parent_type_of,
        case_id=seed.case_id,
    )

    pool: dict[str, list[DatedCandidate]] = defaultdict(list)
    for candidate in candidates:
        pool[candidate.subtype].append(candidate)
    for entries in pool.values():
        entries.sort(key=lambda item: (item.doc_date, item.track))

    dated: list[tuple[date, str, str, str]] = []
    for entry in control.planned:
        if entry.count <= 0:
            continue
        available = pool.get(entry.subtype, [])
        chosen = available[: entry.count]
        for candidate in chosen:
            dated.append(
                (candidate.doc_date, entry.subtype, candidate.track, candidate.author_role)
            )
        shortfall = entry.count - len(chosen)
        if shortfall > 0:
            role = chosen[-1].author_role if chosen else author_role_for(entry.subtype)
            track = chosen[-1].track if chosen else TRACK_CORE
            for extra in _synthesize_dates(seed, timeline, entry.subtype, available, shortfall):
                dated.append((extra, entry.subtype, track, role))

    dated.sort(key=lambda item: (item[0], item[1], item[2]))

    documents: list[PlannedDocument] = []
    for index, (doc_date, subtype, track, role) in enumerate(dated):
        documents.append(
            PlannedDocument(
                index=index,
                subtype=subtype,
                parent_type=taxonomy.parent_of(subtype),
                doc_date=doc_date,
                doc_format=choose_format(seed, index),
                track=track,
                author_role=role,
                title=taxonomy.label(subtype) or subtype.replace("_", " ").title(),
            )
        )

    cast = build_case_cast(seed, timeline, case_number=case_number)
    warnings = (*control.warnings, *recon.warnings)

    log.debug(
        "plan.built",
        case_id=seed.case_id,
        documents=len(documents),
        liens=len(lien_tracks),
        recon=recon.enabled,
        warnings=len(warnings),
    )
    return CasePlan(
        seed=seed,
        timeline=timeline,
        cast=cast,
        documents=tuple(documents),
        lien_tracks=tuple(lien_tracks),
        recon=recon,
        control=control,
        warnings=warnings,
    )


__all__ = ["CasePlan", "PlannedDocument", "build_case_plan"]
