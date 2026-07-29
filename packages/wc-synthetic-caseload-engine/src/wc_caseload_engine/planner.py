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

from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

import structlog

from wc_caseload_engine.case_context import CaseCast, build_case_cast
from wc_caseload_engine.case_facts import (
    CaseFacts,
    derive_case_facts,
    resolve_surgery_status,
    resolve_treatment_status,
)
from wc_caseload_engine.doc_controls import (
    TRACK_CORE,
    ControlResolution,
    resolve_document_controls,
)
from wc_caseload_engine.doctrine import content_flags_for, unsupported_hook_warnings
from wc_caseload_engine.lien_machine import LienTrack, build_lien_tracks, lien_candidates
from wc_caseload_engine.lifecycle_bridge import (
    SUBSTRATE_TO_CANONICAL,
    CaseTimeline,
    DatedCandidate,
    author_role_for,
    build_core_candidates,
    build_timeline,
    to_document_candidates,
)
from wc_caseload_engine.perspective import apply_perspective, document_roles
from wc_caseload_engine.recon_machine import ReconTrack, build_recon_track
from wc_caseload_engine.renderer import choose_format
from wc_caseload_engine.seeds import CaseSeed, DocumentControls
from wc_caseload_engine.taxonomy import Taxonomy, effective_taxonomy, parent_type_of

log = structlog.get_logger(__name__)


class ControlKeyError(ValueError):
    """A ``documents:`` control names a key that cannot reach a manifest.

    Raised by :func:`normalize_control_keys` at plan time — which is to say at
    *generate* time. ``wc-caseload validate --spec`` checked control keys and
    ``generate`` did not, so the only gate on the engine's central contract
    ("every subtype written to a manifest is classifier vocabulary") was one a
    caller could skip by not running it.
    """


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
    recipient_role: str = ""
    """Who this document was addressed to, from the file owner's point of view.

    Empty only for plans built before perspective existed; every plan this
    module builds sets it. See :func:`wc_caseload_engine.perspective.document_roles`.
    """
    content_flags: tuple[str, ...] = ()
    """Doctrine hooks whose language this document carries.

    Sorted and deduplicated — the subset of the seed's
    ``lifecycle.doctrine_hooks`` that
    :func:`~wc_caseload_engine.doctrine.content_flags_for` says has content for
    this subtype. Empty for every document of a hook-free case, which is what
    keeps the no-doctrine render path byte-identical to what it was.
    """


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
    lien_document_counts: tuple[int, ...] = ()
    """Documents actually emitted per lien track, positionally aligned to ``lien_tracks``.

    Distinct from ``len(track.documents)``, which is what the lien machine
    *proposed* before perspective suppression and control resolution had their
    say. A manifest that reports the proposal states something untrue about the
    folder next to it.
    """
    recon_document_count: int = 0
    """Documents actually emitted from the reconsideration track, for the same reason."""
    recon_emitted_subtypes: frozenset[str] = frozenset()
    case_facts: CaseFacts | None = None
    """The clinical ledger every fact-aware template reads.

    Derived once, here, so the planner, the renderer and the manifest
    cannot reach three different answers about what happened in the case.
    """
    """Which of the reconsideration track's subtypes survived to the plan.

    Lets the manifest report a date only for a document that was written: a
    suppressed petition must not leave a ``petitionDate`` behind beside a
    ``documentCount`` of zero.
    """
    warnings: tuple[str, ...] = ()
    perspective_notes: tuple[str, ...] = ()
    """Every swap, rescale and suppression the case's perspective applied.

    Empty for an applicant file, which is the whole point: the applicant path
    changes nothing.
    """

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


def canonical_control_key(key: str, taxonomy: Taxonomy) -> str | None:
    """Canonical form of one control key, or ``None`` when it has none.

    Three answers, in order: a parent type key and a canonical subtype are
    already canonical; a substrate-only key with an unambiguous classifier
    equivalent is translated through
    :data:`~wc_caseload_engine.lifecycle_bridge.SUBSTRATE_TO_CANONICAL` — the
    same table the lifecycle walk normalizes through, so a control and a
    candidate mean the same thing by the same rule; anything else has no
    canonical form and must be refused rather than guessed at.
    """
    if taxonomy.is_type(key) or taxonomy.is_canonical(key):
        return key
    return SUBSTRATE_TO_CANONICAL.get(key)


def normalize_control_keys(controls: DocumentControls, *, case_id: str) -> DocumentControls:
    """Canonicalize every ``documents:`` key, refusing the ones with no home.

    Args:
        controls: the seed's ``documents:`` block.
        case_id: named in the error, because a caseload fails one case at a time.

    Returns:
        *controls* unchanged when every key was already canonical, or a copy
        with substrate-only keys translated.

    Raises:
        ControlKeyError: listing every offending key at once. One key per run
            would make fixing a spec an exercise in repetition.
    """
    taxonomy = effective_taxonomy()
    problems: list[str] = []
    renamed: dict[str, str] = {}

    def resolve(field: str, key: str) -> str:
        canonical = canonical_control_key(key, taxonomy)
        if canonical is None:
            problems.append(
                f"{field}: {key!r} is not a classifier subtype or document type. "
                "Only the 353 canonical subtypes, the 15 parent types, and substrate "
                "keys with an unambiguous canonical equivalent may be named — run "
                "`wc-caseload validate --spec <spec.yaml>` to see every offending key "
                "in one pass, and `wc-caseload seed --template --kind caseload` for a "
                "worked example of the controls."
            )
            return key
        if canonical != key:
            renamed[key] = canonical
        return canonical

    include_only = [resolve("documents.include_only", key) for key in controls.include_only]
    exclude = [resolve("documents.exclude", key) for key in controls.exclude]
    overrides = []
    for override in controls.overrides:
        if override.subtype is not None:
            overrides.append(
                override.model_copy(
                    update={"subtype": resolve("documents.overrides[].subtype", override.subtype)}
                )
            )
        else:
            overrides.append(
                override.model_copy(
                    update={"type": resolve("documents.overrides[].type", str(override.type))}
                )
            )

    if problems:
        raise ControlKeyError(
            f"case {case_id!r}: {len(problems)} document control key(s) cannot be "
            "written to a manifest:\n  " + "\n  ".join(problems)
        )

    if not renamed:
        return controls

    # Aliasing creates collisions the schema could not have seen. Three
    # substrate keys canonicalize to CLIENT_CORRESPONDENCE_INFORMATIONAL and two
    # more pairs exist, so `include_only: [CLIENT_CORRESPONDENCE_INFORMATIONAL]`
    # with `exclude: [CLIENT_REPORT_ANALYSIS_LETTER]` is one subtype written two
    # ways — the schema validator compares raw strings, sees no overlap, and the
    # resolver then drops the include the seed explicitly asked for. Every check
    # the schema runs on raw keys is therefore re-run on canonical ones, and the
    # error names the original aliases because those are what the author wrote.
    def _aliases_for(canonical: str, keys: Sequence[str]) -> str:
        written = sorted({key for key in keys if renamed.get(key, key) == canonical})
        return ", ".join(repr(key) for key in written)

    overlap = sorted(set(include_only) & set(exclude))
    if overlap:
        detail = "; ".join(
            f"{canonical} (include_only: {_aliases_for(canonical, controls.include_only)}, "
            f"exclude: {_aliases_for(canonical, controls.exclude)})"
            for canonical in overlap
        )
        raise ControlKeyError(
            f"case {case_id!r}: documents.include_only and documents.exclude name the same "
            f"subtype under different substrate aliases — {detail}. Name it once, canonically."
        )

    for field, keys in (
        ("documents.include_only", (include_only, controls.include_only)),
        ("documents.exclude", (exclude, controls.exclude)),
    ):
        canonical_keys, original_keys = keys
        duplicated = sorted({key for key in canonical_keys if canonical_keys.count(key) > 1})
        if duplicated:
            detail = "; ".join(
                f"{canonical} ({_aliases_for(canonical, original_keys)})"
                for canonical in duplicated
            )
            raise ControlKeyError(
                f"case {case_id!r}: {field} names the same subtype more than once under "
                f"different substrate aliases — {detail}. Name it once, canonically."
            )

    # The schema forbids duplicate override entries; collapsing two aliases into
    # one silently would make a count mean something the seed did not say.
    collided = sorted(
        {
            entry.subtype
            for entry in overrides
            if entry.subtype is not None
            and sum(1 for other in overrides if other.subtype == entry.subtype) > 1
        }
    )
    if collided:
        detail = "; ".join(
            f"{canonical} ("
            + ", ".join(
                repr(override.subtype)
                for override in controls.overrides
                if override.subtype is not None
                and renamed.get(override.subtype, override.subtype) == canonical
            )
            + ")"
            for canonical in collided
        )
        raise ControlKeyError(
            f"case {case_id!r}: documents.overrides entries collapse onto the same "
            f"canonical subtype(s) after normalization — {detail}; name the canonical "
            "key once with the count you want"
        )

    log.info("controls.normalized", case_id=case_id, renamed=dict(sorted(renamed.items())))
    return controls.model_copy(
        update={"include_only": include_only, "exclude": exclude, "overrides": overrides}
    )


def _emitted_per_track(
    documents: Sequence[PlannedDocument],
    tracks: Sequence[Sequence[DatedCandidate]],
) -> tuple[int, ...]:
    """How many of each track's proposed documents actually survived to the plan.

    Matches on ``(subtype, date)`` and consumes each emitted document once, so a
    document proposed by two tracks is attributed to the first that claims it
    rather than counted twice. Exact for every document the planner took from a
    candidate (it keeps the candidate's own date); a synthesized extra copy —
    one a per-subtype override demanded beyond what the machines proposed — has
    a date no track proposed and is correctly attributed to none of them.
    """
    remaining: Counter[tuple[str, date]] = Counter(
        (document.subtype, document.doc_date) for document in documents
    )
    counts: list[int] = []
    for candidates in tracks:
        emitted = 0
        for candidate in candidates:
            key = (candidate.subtype, candidate.doc_date)
            if remaining[key] > 0:
                remaining[key] -= 1
                emitted += 1
        counts.append(emitted)
    return tuple(counts)


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


#: What survives ``treatment: never_treated``.
#:
#: An applicant who never treated still generates paper. Somebody reported the
#: injury, a claim form was filed, and if they went to an emergency department
#: once and never returned, that visit exists. What does not exist is a course
#: of care: no progress reports, no imaging ordered by a treater, no bills for
#: visits that never happened.
#:
#: Stated as an explicit allowlist rather than a denylist because the failure
#: modes point opposite ways. A subtype missing from a denylist silently
#: survives and quietly contradicts the seed; a subtype missing from this list
#: is merely absent from a file the seed already says is sparse.
NEVER_TREATED_TIER: frozenset[str] = frozenset(
    {
        "FIRST_REPORT_OF_INJURY_PHYSICIAN",
        "CLAIM_FORM",
        "CLAIM_FORM_DWC1",
        "EMERGENCY_ROOM_RECORDS",
        "FACE_SHEET",
    }
)

#: Types whose documents imply a course of treatment.
NEVER_TREATED_SUPPRESSED_TYPES: frozenset[str] = frozenset(
    {"MEDICAL_CLINICAL", "BILLING_FINANCIAL", "UTILIZATION_MANAGEMENT"}
)

#: Documents that must not post-date a discharge from care.
POST_DISCHARGE_FORBIDDEN: frozenset[str] = frozenset(
    {
        "TREATING_PHYSICIAN_REPORT",
        "TREATING_PHYSICIAN_REPORT_PR2",
        "TREATING_PHYSICIAN_REPORT_PR4",
        "TREATING_PHYSICIAN_REPORT_FINAL",
        "ONGOING_TREATMENT_RECORDS",
    }
)

#: Documents that assert an operation happened.
OPERATIVE_SUBTYPES: frozenset[str] = frozenset({"OPERATIVE_HOSPITAL_RECORDS"})


def _penalty_candidates(
    facts: CaseFacts, timeline: CaseTimeline
) -> list[tuple[date, str, str, str]]:
    """The LC 5814 penalty petition, emitted only when a benefit was late.

    The substrate's own rule is a flat 10% coin with no condition, so one file
    in ten pleaded an unreasonable delay in payment whether or not anything had
    been delayed — a pleading with no facts under it. The subtype is stripped
    from the walk (``PENALTY_OWNED_SUBTYPES``) and emitted here instead, gated
    on the ledger.

    The gate reads ``CaseFacts.late_benefit_events``, which is the *resolved*
    lateness — derived from the resolved diligence, not from whatever the seed
    happened to declare. A seed that says nothing about the adjuster still gets
    a derived diligence, and a derived-negligent file earns its petition exactly
    as a stated one does.

    Dated after the latest late event rather than off a uniform window: the
    petition is a response to the delay, so it cannot predate the delay it
    complains about.
    """
    if not facts.late_benefit_events:
        return []

    latest = max(event.actual_date for event in facts.late_benefit_events)
    filed = getattr(timeline, "application_filed_date", None)
    when = max(latest, filed) if filed is not None else latest
    when = when + timedelta(days=30)

    horizon = getattr(timeline, "resolution_date", None) or filed
    if horizon is not None and when > horizon:
        when = horizon

    return [(when, "PETITION_FOR_PENALTIES", TRACK_CORE, "applicant_attorney")]


def _shape_for_scenario(
    seed: CaseSeed,
    timeline: CaseTimeline,
    facts: CaseFacts,
    dated: list[tuple[date, str, str, str]],
) -> tuple[list[tuple[date, str, str, str]], tuple[str, ...]]:
    """Apply the seed's treatment and surgery scenario to the candidate set.

    Shaping happens *here*, on candidates, rather than through the document
    controls a seed author writes by hand. ``never_treated`` means the file has
    no course of care in it, which is a statement about the case — expressing it
    as thirty ``exclude:`` keys would make the seed unreadable and would drift
    the moment the taxonomy grew.

    Returns the shaped candidate list and any warnings, which ride the same
    channel as denylist and doctrine-hook warnings: keep what the seed asked
    for, and say what was unusual about it.
    """
    scenario = seed.scenario
    if scenario.treatment.status is None and scenario.surgery is None:
        # Nothing stated: identical to v0.3.0, candidate for candidate. Every
        # byte guarantee for scenario-free seeds rests on this early return.
        return dated, ()

    taxonomy = effective_taxonomy()
    status = resolve_treatment_status(seed)
    surgery_status = resolve_surgery_status(seed)
    warnings: list[str] = []
    shaped = list(dated)

    if status == "never_treated":
        kept = [
            entry
            for entry in shaped
            if entry[1] in NEVER_TREATED_TIER
            or taxonomy.parent_of(entry[1]) not in NEVER_TREATED_SUPPRESSED_TYPES
        ]
        dropped = len(shaped) - len(kept)
        if dropped:
            warnings.append(
                f"scenario.treatment.status is 'never_treated': suppressed {dropped} "
                "treatment, diagnostic and billing document(s); the first-report tier "
                "is retained"
            )
        shaped = kept

    if status == "discharged":
        discharge = facts.discharge_date
        if discharge is not None:
            after = [
                entry
                for entry in shaped
                if entry[1] in POST_DISCHARGE_FORBIDDEN and entry[0] > discharge
            ]
            if after:
                shaped = [entry for entry in shaped if entry not in after]
                warnings.append(
                    f"scenario.treatment.status is 'discharged': dropped {len(after)} "
                    f"treating document(s) dated after the discharge of {discharge}"
                )
            if not any(entry[1] == "DISCHARGE_SUMMARY" for entry in shaped):
                shaped.append((discharge, "DISCHARGE_SUMMARY", TRACK_CORE, "treating_physician"))

    # ISC-109. A *stated* surgery floors the operative document; a derived one
    # keeps the substrate's probabilistic emission untouched, which is what
    # leaves v0.3.0 bytes alone for every seed that states nothing.
    if scenario.surgery == "performed" and not any(
        entry[1] in OPERATIVE_SUBTYPES for entry in shaped
    ):
        when = facts.surgery.date or timeline.injury_date + timedelta(days=210)
        shaped.append((when, "OPERATIVE_HOSPITAL_RECORDS", TRACK_CORE, "treating_physician"))

    if surgery_status in ("none", "recommended", "denied_by_ur"):
        operative = [entry for entry in shaped if entry[1] in OPERATIVE_SUBTYPES]
        if operative:
            shaped = [entry for entry in shaped if entry not in operative]
            warnings.append(
                f"scenario.surgery is {surgery_status!r}: dropped {len(operative)} "
                "operative document(s) the walk proposed"
            )

    # ISC-114. Keep-and-warn parity: the seed wins, and the file says so.
    if scenario.surgery in ("performed", "recommended", "denied_by_ur"):
        psych = any(part.part == "psyche" for part in seed.injury.body_parts) or (
            "lc3208_3_psych" in seed.lifecycle.doctrine_hooks
        )
        if seed.injury.type == "death" or psych:
            excluded = "a death claim" if seed.injury.type == "death" else "a psychiatric claim"
            warnings.append(
                f"scenario.surgery is {scenario.surgery!r} on {excluded}, which the "
                "substrate's own rule excludes from surgery — the seed is the "
                "contract, so it is honoured, but check this is intended"
            )

    return shaped, tuple(warnings)


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
    # Before anything is decided by them: a control key with no canonical form
    # can only end as a non-canonical subtype in a manifest, and the cheapest
    # place to say so is here, naming the key the seed author wrote.
    controls = normalize_control_keys(seed.documents, case_id=seed.case_id)
    timeline = build_timeline(seed)

    core = build_core_candidates(seed, timeline)
    lien_tracks = build_lien_tracks(seed, timeline)
    recon = build_recon_track(seed, timeline)

    candidates: list[DatedCandidate] = [*core, *lien_candidates(lien_tracks), *recon.documents]

    # Whose file is this? The three machines above are perspective-blind on
    # purpose — they model the *claim*, which both sides share. Only here does
    # the claim become one side's folder.
    pov = apply_perspective(seed, timeline, candidates)
    candidates = list(pov.candidates)

    control = resolve_document_controls(
        to_document_candidates(candidates),
        controls,
        parent_type_of=parent_type_of,
        case_id=seed.case_id,
        pre_dropped=pov.suppressed,
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

    # Derived once and threaded through. Each of these helpers used to derive
    # its own copy, which put four full derivations on every plan build and
    # took the suite from 155s to over 600s. Identical output either way —
    # derivation is pure — so this is cost, not correctness.
    planning_facts = derive_case_facts(seed, timeline)
    dated.extend(_penalty_candidates(planning_facts, timeline))
    dated, scenario_warnings = _shape_for_scenario(seed, timeline, planning_facts, dated)
    dated.sort(key=lambda item: (item[0], item[1], item[2]))

    documents: list[PlannedDocument] = []
    for index, (doc_date, subtype, track, role) in enumerate(dated):
        if not taxonomy.is_canonical(subtype):
            # Fail closed. ``normalize_control_keys`` above is the gate; this is
            # the assertion that catches a *future* path into the planner that
            # does not pass through it. A non-canonical subtype here becomes a
            # non-canonical subtype in a manifest, which is the one thing the
            # manifest promises never to contain.
            raise ControlKeyError(
                f"case {seed.case_id!r}: planned document {index} has subtype "
                f"{subtype!r}, which is not classifier vocabulary and must never "
                "reach a manifest"
            )
        roles = document_roles(subtype, role, seed.perspective)
        documents.append(
            PlannedDocument(
                index=index,
                subtype=subtype,
                parent_type=taxonomy.parent_of(subtype),
                doc_date=doc_date,
                doc_format=choose_format(seed, index),
                track=track,
                author_role=roles.author_role,
                title=taxonomy.label(subtype) or subtype.replace("_", " ").title(),
                recipient_role=roles.recipient_role,
                content_flags=content_flags_for(seed.lifecycle.doctrine_hooks, subtype),
            )
        )

    cast = build_case_cast(seed, timeline, case_number=case_number)

    emitted = _emitted_per_track(
        documents, [track.documents for track in lien_tracks] + [recon.documents]
    )
    lien_counts, recon_count = emitted[: len(lien_tracks)], emitted[len(lien_tracks)]
    emitted_subtypes = {document.subtype for document in documents}
    recon_subtypes = frozenset(
        candidate.subtype for candidate in recon.documents if candidate.subtype in emitted_subtypes
    )

    warnings = (
        *control.warnings,
        *recon.warnings,
        *cast.warnings,
        *scenario_warnings,
        *unsupported_hook_warnings(seed.lifecycle.doctrine_hooks, seed),
    )

    log.debug(
        "plan.built",
        case_id=seed.case_id,
        perspective=seed.perspective,
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
        lien_document_counts=lien_counts,
        recon_document_count=recon_count,
        recon_emitted_subtypes=recon_subtypes,
        warnings=warnings,
        perspective_notes=pov.notes,
        case_facts=derive_case_facts(seed, timeline, cast),
    )


__all__ = [
    "CasePlan",
    "ControlKeyError",
    "PlannedDocument",
    "build_case_plan",
    "canonical_control_key",
    "normalize_control_keys",
]
