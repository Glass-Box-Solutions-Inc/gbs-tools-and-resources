"""Document-control resolver — the precedence rules, as pure functions.

Input: the candidate documents a lifecycle walk wants to emit, plus the seed's
``documents:`` block. Output: the final planned count per subtype.

**Precedence (highest wins):**

1. **per-subtype override** — ``{subtype: X, count: N}`` emits exactly ``N``,
   even if the lifecycle never proposed it and even if a blacklist or a cap
   says otherwise (a lifecycle-invalid forced subtype logs a WARN, ISC-29).
2. **include_only / exclude** — whitelist then blacklist, matching either a
   subtype key or a parent type key.
3. **per-type min/max** — bounds the surviving total for a parent type.
4. **lifecycle emission defaults** — the candidate list itself.
5. **global_cap** — trims last, taking the most-trimmable documents first
   (filler tracks before supporting before core; within a track, the highest
   ``priority`` number goes first). Never trims a per-subtype override.

Nothing in this module imports the substrate, so the whole precedence matrix is
unit-testable in isolation.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

import structlog

from wc_caseload_engine.seeds import DocumentControls

log = structlog.get_logger(__name__)

TRACK_CORE = "core"
TRACK_LIEN = "lien"
TRACK_RECON = "recon"
TRACK_SUPPORTING = "supporting"
TRACK_FILLER = "filler"

TRACK_TRIM_ORDER: Mapping[str, int] = {
    TRACK_FILLER: 0,
    TRACK_SUPPORTING: 1,
    TRACK_CORE: 2,
    TRACK_LIEN: 3,
    TRACK_RECON: 4,
}
"""Lower rank is trimmed first when ``global_cap`` bites."""

DEFAULT_PRIORITY = 50
"""Mid-scale priority. Lower number = more essential = trimmed last."""

_UNKNOWN_TRACK_RANK = 2


@dataclass(frozen=True, slots=True)
class DocumentCandidate:
    """One document a lifecycle walk proposes to emit.

    ``priority`` is an essentiality rank: ``0`` is a must-have pleading, ``90``
    is disposable filler. ``track`` names the machine that proposed it.
    """

    subtype: str
    priority: int = DEFAULT_PRIORITY
    track: str = TRACK_CORE
    parent_type: str | None = None
    count: int = 1
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PlannedDocumentCount:
    """Final plan for one subtype."""

    subtype: str
    count: int
    parent_type: str | None
    track: str
    priority: int
    forced: bool = False
    reasons: tuple[str, ...] = ()

    def with_count(self, count: int, reason: str | None = None) -> PlannedDocumentCount:
        """Copy with a new count, appending an audit reason."""
        reasons = self.reasons + ((reason,) if reason else ())
        return replace(self, count=count, reasons=reasons)


@dataclass(frozen=True, slots=True)
class ControlResolution:
    """Resolved document plan plus the audit trail that produced it."""

    planned: tuple[PlannedDocumentCount, ...]
    warnings: tuple[str, ...] = ()
    dropped: Mapping[str, str] = field(default_factory=dict)

    @property
    def total(self) -> int:
        """Total planned document count."""
        return sum(entry.count for entry in self.planned)

    def counts(self) -> dict[str, int]:
        """``{subtype: count}`` for every subtype with a positive count."""
        return {entry.subtype: entry.count for entry in self.planned if entry.count > 0}

    def count_for(self, subtype: str) -> int:
        """Planned count for *subtype* (``0`` when absent)."""
        return self.counts().get(subtype, 0)

    def forced_subtypes(self) -> tuple[str, ...]:
        """Subtypes emitted only because an override demanded them."""
        return tuple(entry.subtype for entry in self.planned if entry.forced and entry.count > 0)

    def type_totals(self) -> dict[str, int]:
        """Planned counts aggregated by parent type."""
        totals: Counter[str] = Counter()
        for entry in self.planned:
            if entry.count > 0 and entry.parent_type is not None:
                totals[entry.parent_type] += entry.count
        return dict(totals)


ParentResolver = Callable[[str], str | None]


def _resolve_parent(
    subtype: str,
    declared: str | None,
    parent_type_of: ParentResolver | None,
) -> str | None:
    """Parent type of a subtype: the candidate's own value wins, then the resolver."""
    if declared is not None:
        return declared
    if parent_type_of is None:
        return None
    return parent_type_of(subtype)


def _matches(entry: PlannedDocumentCount, keys: Iterable[str]) -> bool:
    """``True`` when *entry* is named by a subtype key or its parent type key."""
    key_set = set(keys)
    return entry.subtype in key_set or (
        entry.parent_type is not None and entry.parent_type in key_set
    )


def _collapse_candidates(
    candidates: Sequence[DocumentCandidate],
    parent_type_of: ParentResolver | None,
) -> list[PlannedDocumentCount]:
    """Aggregate candidates per subtype, keeping the most essential metadata."""
    order: list[str] = []
    merged: dict[str, PlannedDocumentCount] = {}
    for candidate in candidates:
        if candidate.count < 0:
            raise ValueError(
                f"candidate {candidate.subtype!r} has negative count {candidate.count}"
            )
        parent = _resolve_parent(candidate.subtype, candidate.parent_type, parent_type_of)
        existing = merged.get(candidate.subtype)
        if existing is None:
            order.append(candidate.subtype)
            merged[candidate.subtype] = PlannedDocumentCount(
                subtype=candidate.subtype,
                count=candidate.count,
                parent_type=parent,
                track=candidate.track,
                priority=candidate.priority,
            )
            continue
        # When two machines propose the same subtype, keep the most protective
        # metadata: the most essential priority and the least trimmable track.
        merged[candidate.subtype] = replace(
            existing,
            count=existing.count + candidate.count,
            priority=min(existing.priority, candidate.priority),
            track=max(
                existing.track,
                candidate.track,
                key=lambda track: TRACK_TRIM_ORDER.get(track, _UNKNOWN_TRACK_RANK),
            ),
            parent_type=existing.parent_type or parent,
        )
    return [merged[subtype] for subtype in order]


def _trim_rank(entry: PlannedDocumentCount) -> tuple[int, int, str]:
    """Sort key for cap trimming: most-trimmable first."""
    return (
        TRACK_TRIM_ORDER.get(entry.track, _UNKNOWN_TRACK_RANK),
        -entry.priority,
        entry.subtype,
    )


def _grow_rank(entry: PlannedDocumentCount) -> tuple[int, str]:
    """Sort key for satisfying a type ``min``: most essential first."""
    return (entry.priority, entry.subtype)


def resolve_document_controls(
    candidates: Sequence[DocumentCandidate],
    controls: DocumentControls,
    *,
    parent_type_of: ParentResolver | None = None,
    case_id: str | None = None,
    logger: Any | None = None,
) -> ControlResolution:
    """Apply the documented control precedence and return the final plan.

    Args:
        candidates: what the lifecycle walk proposes (the emission defaults).
        controls: the seed's ``documents:`` block.
        parent_type_of: resolves a subtype to its parent type when a candidate
            or an override does not declare one (pass
            :func:`wc_caseload_engine.taxonomy.parent_type_of` in production;
            omit it in pure unit tests).
        case_id: included in warning logs.
        logger: structlog-style logger override (defaults to this module's).

    Returns:
        A :class:`ControlResolution` carrying the plan, warnings and drop audit.
    """
    emit_log = logger if logger is not None else log
    warnings: list[str] = []
    dropped: dict[str, str] = {}

    # 4. Lifecycle emission defaults.
    plan: list[PlannedDocumentCount] = _collapse_candidates(candidates, parent_type_of)

    # 2. include_only, then exclude.
    if controls.include_only:
        kept: list[PlannedDocumentCount] = []
        for entry in plan:
            if _matches(entry, controls.include_only):
                kept.append(entry)
            else:
                dropped[entry.subtype] = "not in documents.include_only"
        plan = kept
    if controls.exclude:
        kept = []
        for entry in plan:
            if _matches(entry, controls.exclude):
                dropped[entry.subtype] = "documents.exclude"
            else:
                kept.append(entry)
        plan = kept

    # 3. Per-parent-type min/max bounds.
    for doc_type, (minimum, maximum) in controls.type_bounds.items():
        members = [entry for entry in plan if entry.parent_type == doc_type]
        total = sum(entry.count for entry in members)
        if maximum is not None and total > maximum:
            plan = _apply_type_max(plan, doc_type, members, total - maximum)
        elif minimum is not None and total < minimum:
            shortfall = minimum - total
            if not members:
                warning = (
                    f"documents.overrides min={minimum} for type {doc_type} cannot be "
                    "satisfied: the lifecycle proposed no documents of that type"
                )
                warnings.append(warning)
                emit_log.warning(
                    "doc_controls.min_unsatisfiable",
                    case_id=case_id,
                    doc_type=doc_type,
                    minimum=minimum,
                )
            else:
                plan = _apply_type_min(plan, members, shortfall)

    # 1. Per-subtype overrides — highest precedence, may resurrect or invent.
    plan = _apply_subtype_overrides(
        plan,
        controls,
        parent_type_of=parent_type_of,
        dropped=dropped,
        warnings=warnings,
        emit_log=emit_log,
        case_id=case_id,
    )

    # 5. global_cap trims last, respecting every higher-precedence floor.
    if controls.global_cap is not None:
        type_minimums = {
            doc_type: minimum
            for doc_type, (minimum, _) in controls.type_bounds.items()
            if minimum is not None
        }
        plan, cap_warnings = _apply_global_cap(plan, controls.global_cap, type_minimums)
        for warning in cap_warnings:
            warnings.append(warning)
            emit_log.warning(
                "doc_controls.cap_unreachable",
                case_id=case_id,
                global_cap=controls.global_cap,
                detail=warning,
            )

    plan = [entry for entry in plan if entry.count > 0]
    return ControlResolution(
        planned=tuple(plan), warnings=tuple(warnings), dropped=dict(dropped)
    )


def _apply_type_max(
    plan: Sequence[PlannedDocumentCount],
    doc_type: str,
    members: Sequence[PlannedDocumentCount],
    excess: int,
) -> list[PlannedDocumentCount]:
    """Trim *excess* documents from one parent type, most-trimmable first."""
    reductions: Counter[str] = Counter()
    order = sorted(members, key=_trim_rank)
    remaining = excess
    while remaining > 0:
        progressed = False
        for entry in order:
            available = entry.count - reductions[entry.subtype]
            if available <= 0:
                continue
            reductions[entry.subtype] += 1
            remaining -= 1
            progressed = True
            if remaining == 0:
                break
        if not progressed:  # pragma: no cover - excess is bounded by the total
            break
    out: list[PlannedDocumentCount] = []
    for entry in plan:
        cut = reductions.get(entry.subtype, 0)
        if cut and entry.parent_type == doc_type:
            out.append(entry.with_count(entry.count - cut, f"type max for {doc_type}"))
        else:
            out.append(entry)
    return out


def _apply_type_min(
    plan: Sequence[PlannedDocumentCount],
    members: Sequence[PlannedDocumentCount],
    shortfall: int,
) -> list[PlannedDocumentCount]:
    """Grow a parent type to its ``min``, adding to the most essential subtypes."""
    additions: Counter[str] = Counter()
    order = sorted(members, key=_grow_rank)
    for step in range(shortfall):
        additions[order[step % len(order)].subtype] += 1
    out: list[PlannedDocumentCount] = []
    for entry in plan:
        add = additions.get(entry.subtype, 0)
        if add:
            out.append(entry.with_count(entry.count + add, "type min"))
        else:
            out.append(entry)
    return out


def _apply_subtype_overrides(
    plan: Sequence[PlannedDocumentCount],
    controls: DocumentControls,
    *,
    parent_type_of: ParentResolver | None,
    dropped: dict[str, str],
    warnings: list[str],
    emit_log: Any,
    case_id: str | None,
) -> list[PlannedDocumentCount]:
    """Force exact per-subtype counts, warning when the lifecycle never proposed one."""
    overrides = controls.subtype_overrides
    if not overrides:
        return list(plan)

    by_subtype = {entry.subtype: entry for entry in plan}
    out: list[PlannedDocumentCount] = []
    for entry in plan:
        if entry.subtype in overrides:
            out.append(
                replace(
                    entry,
                    count=overrides[entry.subtype],
                    forced=True,
                    reasons=(*entry.reasons, "per-subtype override"),
                )
            )
        else:
            out.append(entry)

    for subtype, count in overrides.items():
        if subtype in by_subtype:
            dropped.pop(subtype, None)
            continue
        reason = dropped.pop(subtype, None)
        warning = (
            f"documents.overrides forces {subtype} x{count}: "
            + (
                f"suppressed by {reason} but an explicit override wins"
                if reason
                else "the lifecycle for this case never emits it (control wins, loudly)"
            )
        )
        warnings.append(warning)
        emit_log.warning(
            "doc_controls.forced_subtype",
            case_id=case_id,
            subtype=subtype,
            count=count,
            suppressed_by=reason,
        )
        out.append(
            PlannedDocumentCount(
                subtype=subtype,
                count=count,
                parent_type=_resolve_parent(subtype, None, parent_type_of),
                track=TRACK_CORE,
                priority=0,
                forced=True,
                reasons=("per-subtype override", "lifecycle-invalid"),
            )
        )
    return out


def _apply_global_cap(
    plan: Sequence[PlannedDocumentCount],
    global_cap: int,
    type_minimums: Mapping[str, int] | None = None,
) -> tuple[list[PlannedDocumentCount], list[str]]:
    """Trim the plan down to *global_cap*, honouring higher-precedence floors.

    The cap is the weakest control: it never trims a per-subtype override and
    never pushes a parent type below its ``min`` bound.
    """
    total = sum(entry.count for entry in plan)
    if total <= global_cap:
        return list(plan), []

    minimums = dict(type_minimums or {})
    slack: dict[str, int] = {}
    if minimums:
        totals: Counter[str] = Counter()
        for entry in plan:
            if entry.parent_type is not None:
                totals[entry.parent_type] += entry.count
        slack = {
            doc_type: max(totals.get(doc_type, 0) - minimum, 0)
            for doc_type, minimum in minimums.items()
        }

    excess = total - global_cap
    reductions: Counter[str] = Counter()
    trimmable = sorted((entry for entry in plan if not entry.forced), key=_trim_rank)
    for entry in trimmable:
        if excess == 0:
            break
        available = entry.count - reductions[entry.subtype]
        if entry.parent_type in slack:
            available = min(available, slack[entry.parent_type])
        take = min(available, excess)
        if take > 0:
            reductions[entry.subtype] += take
            excess -= take
            if entry.parent_type in slack:
                slack[entry.parent_type] -= take

    out = [
        entry.with_count(entry.count - reductions[entry.subtype], "global_cap")
        if reductions.get(entry.subtype)
        else entry
        for entry in plan
    ]
    warnings: list[str] = []
    if excess > 0:
        pinned = sum(entry.count for entry in plan if entry.forced)
        floors = ", ".join(
            f"{doc_type} min={value}" for doc_type, value in sorted(minimums.items())
        )
        detail = f"{pinned} document(s) pinned by per-subtype overrides"
        if floors:
            detail += f"; type floors: {floors}"
        warnings.append(
            f"documents.global_cap={global_cap} cannot be met without breaking a "
            f"higher-precedence control ({detail})"
        )
    return out, warnings


__all__ = [
    "DEFAULT_PRIORITY",
    "TRACK_CORE",
    "TRACK_FILLER",
    "TRACK_LIEN",
    "TRACK_RECON",
    "TRACK_SUPPORTING",
    "TRACK_TRIM_ORDER",
    "ControlResolution",
    "DocumentCandidate",
    "ParentResolver",
    "PlannedDocumentCount",
    "resolve_document_controls",
]
