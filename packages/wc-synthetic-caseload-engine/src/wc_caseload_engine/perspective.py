"""Whose file is this — applicant-side or defense-side.

The same injury produces two case files. They share every fact and almost none
of their privileged paper. This module is the *only* place that difference is
expressed, and it is expressed as data: one table, five columns, one edit to
tune.

## The invariant that shapes everything here

**Perspective never changes a case fact.** Same ``rng_seed``, same everything
else: identical cast (both firms exist in both files — they always did, they are
opposing counsel), identical ADJ number, identical date of injury, identical
lifecycle event dates. What changes is which firm owns the file, who authors the
privileged work product, and which side's paper dominates the folder.

That invariant is not a convention, it is enforced structurally: nothing in this
module is reachable from :func:`~wc_caseload_engine.lifecycle_bridge.build_timeline`,
:func:`~wc_caseload_engine.case_context.build_case_cast` or
:func:`~wc_caseload_engine.lifecycle_bridge.build_core_candidates`, and
``perspective`` is never mixed into an RNG salt that feeds a fact. The only RNG
this module draws from is :data:`RNG_SALT`, a stream nothing else reads, used
solely to date documents this side of the file adds. On the applicant path
:func:`apply_perspective` is an identity function that draws nothing at all —
which is what keeps every pre-perspective seed byte-stable.

## The three mechanisms

1. **Work-product swap** (:data:`WORK_PRODUCT_SWAP`). Privileged analysis is
   authored by whoever owns the file. An applicant file holds a
   ``CASE_ANALYSIS_MEMO``; the defense file holding the same analysis calls it
   ``DEFENSE_CASE_ANALYSIS``. Both are canonical ``WORK_PRODUCT`` keys, so the
   swap is a rename, never a taxonomy escape.

2. **Emission profiles** (:data:`PERSPECTIVE_PROFILES`). Per subtype *or* parent
   type, how much of that paper each side's file carries, as a multiplier on
   what the shared lifecycle proposed. ``0.0`` means the paper does not belong
   in that file at all; ``2.5`` means that side generates two and a half times
   as much of it. A profile keyed on a subtype wins over one keyed on its type.

3. **Role flip** (:func:`document_roles`). "Client" means the injured worker on
   an applicant file and the employer/carrier on a defense file, so the author
   and recipient of client correspondence invert. A settlement demand is
   applicant-authored on both files — outgoing on one, received on the other —
   so only its recipient moves.

## Why a floor, and why only one

``INVESTIGATION`` is the case the multiplier alone cannot express: the shared
lifecycle walk proposes *zero* investigator reports, and any multiple of zero is
zero. Surveillance, sub-rosa video and social-media evidence are near-exclusively
defense paper — a defense file without them is not a defense file. So a profile
row may name a :attr:`EmissionProfile.floor`: subtypes planted once each when
that key's pool is otherwise empty, for the side the row marks as characteristic
(the strictly-higher weight). Equal weights mean neither side is characteristic
and nothing is planted.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, timedelta

import structlog

from wc_caseload_engine.doc_controls import TRACK_CORE
from wc_caseload_engine.lifecycle_bridge import (
    ROLE_APPLICANT_ATTORNEY,
    ROLE_CARRIER,
    ROLE_DEFENSE_ATTORNEY,
    ROLE_EMPLOYER,
    CaseTimeline,
    DatedCandidate,
)
from wc_caseload_engine.seeds import CaseSeed, Perspective
from wc_caseload_engine.taxonomy import effective_taxonomy

log = structlog.get_logger(__name__)

APPLICANT: Perspective = "applicant"
DEFENSE: Perspective = "defense"

RNG_SALT = "perspective"
"""The one RNG salt this module draws from.

Deliberately its own stream. Dating a planted surveillance report must never
perturb the draw that picks the applicant's name, and a salt no fact-producing
code reads is how that is guaranteed rather than merely intended.
"""

FLOOR_PRIORITY = 15
"""Essentiality of floor-planted paper — core track, near the top.

Learned the hard way. Planted as trimmable supporting paper, the demo's defense
file emitted *zero* investigation documents: ``global_cap: 55`` ate the entire
floor before it touched the twenty-third adjuster letter, so the one mechanism
whose whole job is "this file always has surveillance" reliably produced a file
with no surveillance. A floor that the weakest control can delete is not a floor.
It sits above routine correspondence and below the dispositive pleadings a cap
must never reach.
"""


# ---------------------------------------------------------------------------
# 1. Work-product swap
# ---------------------------------------------------------------------------

WORK_PRODUCT_SWAP: Mapping[str, str] = {
    "CASE_ANALYSIS_MEMO": "DEFENSE_CASE_ANALYSIS",
    "SETTLEMENT_VALUATION_MEMO": "DEFENSE_MSC_STATEMENT",
    "TRIAL_BRIEF": "DEFENSE_TRIAL_BRIEF",
}
"""Applicant-side work product -> its defense-side counterpart.

Only privileged, positional analysis swaps. A ``MEDICAL_CHRONOLOGY_TIMELINE`` or
a ``DEPOSITION_SUMMARY`` is prepared by both sides under the same name and is
deliberately absent here.

``SETTLEMENT_VALUATION_MEMO`` maps to ``DEFENSE_MSC_STATEMENT`` because that is
where a defense file states its valuation: the mandatory settlement conference
statement is the defense's number, filed rather than filed away.

Every key and every value is a canonical ``WORK_PRODUCT`` subtype — asserted in
``tests/test_perspective.py`` against ``effective_taxonomy()``, so a taxonomy
resync that renames one of these fails loudly instead of writing a non-canonical
key into a manifest.
"""


def swap_subtype(subtype: str, perspective: Perspective) -> str:
    """The subtype as it appears in a *perspective* file."""
    if perspective != DEFENSE:
        return subtype
    return WORK_PRODUCT_SWAP.get(subtype, subtype)


# ---------------------------------------------------------------------------
# 2. Emission profiles
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EmissionProfile:
    """How much of one document key each side's file carries.

    Weights multiply the count the shared lifecycle proposed. ``1.0`` leaves it
    alone, ``0.0`` removes it entirely, anything else scales it — a positive
    weight never rounds a non-empty pool down to nothing.
    """

    applicant_weight: float
    defense_weight: float
    floor: tuple[str, ...] = ()
    """Subtypes planted once each when the characteristic side's pool is empty.

    "Characteristic side" is the one with the strictly higher weight. Equal
    weights plant nothing.
    """

    rationale: str = ""
    """Why the numbers are what they are. Read by humans tuning the table."""

    def weight_for(self, perspective: Perspective) -> float:
        """This key's multiplier for *perspective*."""
        return self.defense_weight if perspective == DEFENSE else self.applicant_weight

    def characteristic_side(self) -> Perspective | None:
        """The side this paper belongs to, or ``None`` when neither dominates."""
        if self.defense_weight > self.applicant_weight:
            return DEFENSE
        if self.applicant_weight > self.defense_weight:
            return APPLICANT
        return None


PERSPECTIVE_PROFILES: Mapping[str, EmissionProfile] = {
    # -- Client correspondence -------------------------------------------------
    # "Client" is the injured worker on one file and the employer/carrier on the
    # other. Both files carry the same volume of it; only the roles invert, which
    # document_roles() handles. Listed at 1.0/1.0 so the table states the
    # decision rather than leaving it to the absence of a row.
    "CLIENT_CORRESPONDENCE_INFORMATIONAL": EmissionProfile(
        1.0, 1.0, rationale="Both firms update their own client; only the roles invert."
    ),
    "CLIENT_CORRESPONDENCE_REQUEST": EmissionProfile(
        1.0, 1.0, rationale="Both firms ask their own client for things."
    ),
    # -- Applicant-only paper --------------------------------------------------
    # Intake and status letters are the applicant firm's relationship with an
    # injured worker it signed up. Defense counsel is assigned by a carrier; it
    # runs no intake and writes no status letters to a claimant.
    "CLIENT_INTAKE_CORRESPONDENCE": EmissionProfile(
        1.0, 0.0, rationale="Defense counsel is assigned by the carrier; it runs no intake."
    ),
    "CLIENT_STATUS_LETTERS": EmissionProfile(
        1.0, 0.0, rationale="Status letters go to an injured worker, not to a carrier file."
    ),
    # Advocacy letters lobby a treating or evaluating physician toward a finding.
    # That is applicant-side practice; the defense equivalent is cross-examination
    # and its own QME, not a letter to the PTP.
    "ADVOCACY_LETTERS_PTP": EmissionProfile(
        1.0, 0.0, rationale="Advocacy to the treating physician is applicant-side practice."
    ),
    "ADVOCACY_LETTERS_QME": EmissionProfile(1.0, 0.0, rationale="As ADVOCACY_LETTERS_PTP."),
    "ADVOCACY_LETTERS_AME": EmissionProfile(1.0, 0.0, rationale="As ADVOCACY_LETTERS_PTP."),
    "ADVOCACY_LETTERS_PTP_QME_AME": EmissionProfile(
        1.0, 0.0, rationale="As ADVOCACY_LETTERS_PTP."
    ),
    # -- Settlement demand -----------------------------------------------------
    # Applicant-authored on both files. It sits in the defense file as received
    # correspondence, which is a recipient change, not a count change.
    "SETTLEMENT_DEMAND_LETTER": EmissionProfile(
        1.0,
        1.0,
        rationale="Applicant-authored; the defense file holds it as received correspondence.",
    ),
    # -- Parent types ----------------------------------------------------------
    # The carrier's own administration of the claim — reserve worksheets, diary
    # notes, nurse case management, compensability determinations — is generated
    # by the defense side and lives in its file natively. The applicant firm sees
    # only what gets served or produced.
    "CLAIMS_ADMINISTRATION": EmissionProfile(
        1.0,
        2.5,
        rationale=(
            "The carrier's own claim file. Applicant counsel receives a fraction of it; "
            "defense counsel works from all of it."
        ),
    ),
    # Investigation is the case a multiplier cannot express on its own: the shared
    # walk proposes none, and any multiple of zero is zero. Hence the floor.
    "INVESTIGATION": EmissionProfile(
        1.0,
        3.0,
        floor=("INVESTIGATOR_REPORT", "SURVEILLANCE_VIDEO", "SOCIAL_MEDIA_EVIDENCE"),
        rationale=(
            "Sub-rosa surveillance and social-media workups are retained by the defense. "
            "The shared lifecycle proposes none at all, so the floor plants the three "
            "staples a defense file always has."
        ),
    ),
}
"""Subtype-or-type key -> :class:`EmissionProfile`.

**Tuning is one edit here.** A subtype row beats a parent-type row; a key with no
row is carried unchanged by both files.
"""


def profile_for(subtype: str, parent_type: str | None) -> EmissionProfile | None:
    """The governing profile for *subtype* — its own row, else its type's."""
    own = PERSPECTIVE_PROFILES.get(subtype)
    if own is not None:
        return own
    if parent_type is None:
        return None
    return PERSPECTIVE_PROFILES.get(parent_type)


def scaled_count(proposed: int, weight: float) -> int:
    """Apply *weight* to a proposed count.

    A positive weight never empties a non-empty pool: scaling is for tuning
    volume, and only an explicit ``0.0`` removes a document from a file.
    """
    if weight <= 0.0:
        return 0
    if proposed == 0:
        return 0
    return max(1, round(proposed * weight))


# ---------------------------------------------------------------------------
# 3. Roles
# ---------------------------------------------------------------------------

FILE_OWNER_AUTHORED: frozenset[str] = frozenset(
    {
        *WORK_PRODUCT_SWAP,
        *WORK_PRODUCT_SWAP.values(),
        "CLIENT_CORRESPONDENCE_INFORMATIONAL",
        "CLIENT_CORRESPONDENCE_REQUEST",
        "CLIENT_INTAKE_CORRESPONDENCE",
        "CLIENT_STATUS_LETTERS",
    }
)
"""Subtypes whose author is by definition the firm that owns the file.

Everything else keeps the author the facts give it. An Application for
Adjudication is applicant-filed in *both* files; a QME report is physician-
authored in both; an order is the judge's in both. Flipping those would not make
the file defense-side, it would make it wrong.
"""

ROLE_INJURED_WORKER = "injured_worker"
"""The applicant firm's client. Not an author role, so it has no home in
:mod:`~wc_caseload_engine.lifecycle_bridge` — a worker signs paper, it does not
author it — but it is who applicant-side client correspondence is addressed to.
"""

OWNER_CLIENT_ROLE: Mapping[Perspective, str] = {
    APPLICANT: ROLE_INJURED_WORKER,
    DEFENSE: ROLE_EMPLOYER,
}
"""Who "the client" is for each side."""

OWNER_ATTORNEY_ROLE: Mapping[Perspective, str] = {
    APPLICANT: ROLE_APPLICANT_ATTORNEY,
    DEFENSE: ROLE_DEFENSE_ATTORNEY,
}
"""The role of the firm that owns the file."""


@dataclass(frozen=True, slots=True)
class DocumentRoles:
    """Who wrote a document and who received it, from this file's point of view."""

    author_role: str
    recipient_role: str


def document_roles(
    subtype: str, base_author_role: str, perspective: Perspective
) -> DocumentRoles:
    """Resolve author and recipient for *subtype* in a *perspective* file.

    Two rules, in order:

    1. If the file owner authors this kind of document, the author is the owner's
       attorney and the recipient is the owner's client.
    2. Otherwise the author is whoever the facts say, and the recipient is the
       firm that owns the file — that is what makes a document *received* paper.
    """
    owner_attorney = OWNER_ATTORNEY_ROLE[perspective]
    if subtype in FILE_OWNER_AUTHORED:
        return DocumentRoles(
            author_role=owner_attorney,
            recipient_role=OWNER_CLIENT_ROLE[perspective],
        )
    if base_author_role == owner_attorney:
        # The owner wrote it; it went to the other side.
        opposing = OWNER_ATTORNEY_ROLE[APPLICANT if perspective == DEFENSE else DEFENSE]
        return DocumentRoles(author_role=owner_attorney, recipient_role=opposing)
    return DocumentRoles(author_role=base_author_role, recipient_role=owner_attorney)


def file_owner_firm(perspective: Perspective, applicant_firm: str, defense_firm: str) -> str:
    """The firm whose file this is."""
    return defense_firm if perspective == DEFENSE else applicant_firm


# ---------------------------------------------------------------------------
# Applying it all
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PerspectiveResult:
    """The candidate list as this side's file holds it, plus why."""

    candidates: tuple[DatedCandidate, ...]
    suppressed: Mapping[str, str]
    """``{subtype: reason}`` for paper this side's file does not hold.

    Handed to :func:`~wc_caseload_engine.doc_controls.resolve_document_controls`
    so an explicit ``documents.overrides`` entry can still force it back in, with
    the WARN that path already emits (ISC-29). Perspective is a default, not a
    veto.
    """

    notes: tuple[str, ...] = ()


def _plant_date(seed: CaseSeed, timeline: CaseTimeline, salt: str) -> date:
    """A deterministic date inside the case's active span for planted paper."""
    rng = seed.rng(f"{RNG_SALT}:{salt}")
    span_end = timeline.resolution_date or timeline.horizon
    span_days = max((span_end - timeline.injury_date).days, 1)
    return timeline.clamp(timeline.injury_date + timedelta(days=rng.randint(1, span_days)))


def apply_perspective(
    seed: CaseSeed,
    timeline: CaseTimeline,
    candidates: Sequence[DatedCandidate],
) -> PerspectiveResult:
    """Rewrite a candidate list into the file *seed.perspective* describes.

    On the applicant path this is an identity function that draws no randomness:
    the swap table is defense-only, every applicant weight is ``1.0``, and no row
    is applicant-characteristic. That is deliberate and load-bearing — it is why
    every seed written before this field existed still plans, dates and renders
    exactly as it did.

    Args:
        seed: the case seed (supplies the perspective and the RNG).
        timeline: the case's dates — read, never rewritten.
        candidates: what the three machines proposed, perspective-blind.

    Returns:
        A :class:`PerspectiveResult`.
    """
    perspective = seed.perspective
    if perspective == APPLICANT:
        return PerspectiveResult(candidates=tuple(candidates), suppressed={})

    taxonomy = effective_taxonomy()

    # 1. Swap privileged work product into this side's vocabulary.
    swapped: list[DatedCandidate] = []
    notes: list[str] = []
    for candidate in candidates:
        target = swap_subtype(candidate.subtype, perspective)
        if target == candidate.subtype:
            swapped.append(candidate)
            continue
        notes.append(f"{candidate.subtype} -> {target} (defense work product)")
        swapped.append(replace(candidate, subtype=target))

    # 2. Scale each key's pool by its profile weight.
    pools: dict[str, list[DatedCandidate]] = {}
    for candidate in swapped:
        pools.setdefault(candidate.subtype, []).append(candidate)

    kept: list[DatedCandidate] = []
    suppressed: dict[str, str] = {}
    for subtype, pool in pools.items():
        profile = profile_for(subtype, taxonomy.parent_of(subtype))
        if profile is None:
            kept.extend(pool)
            continue
        target = scaled_count(len(pool), profile.weight_for(perspective))
        if target == 0:
            suppressed[subtype] = f"{perspective} perspective ({profile.rationale})"
            notes.append(f"{subtype} x{len(pool)} suppressed ({perspective} file)")
            continue
        kept.extend(pool[:target])
        for extra in range(target - len(pool)):
            source = pool[extra % len(pool)]
            kept.append(
                replace(
                    source,
                    doc_date=_plant_date(seed, timeline, f"{subtype}:{extra}"),
                )
            )
        if target != len(pool):
            notes.append(f"{subtype} {len(pool)} -> {target} ({perspective} weight)")

    # 3. Plant the floor for characteristic paper this file would otherwise lack.
    present = {candidate.subtype for candidate in kept}
    for key, profile in PERSPECTIVE_PROFILES.items():
        if profile.characteristic_side() != perspective or not profile.floor:
            continue
        if any(taxonomy.parent_of(subtype) == key or subtype == key for subtype in present):
            continue
        for planted in profile.floor:
            kept.append(
                DatedCandidate(
                    subtype=planted,
                    doc_date=_plant_date(seed, timeline, f"floor:{planted}"),
                    track=TRACK_CORE,
                    priority=FLOOR_PRIORITY,
                    author_role=ROLE_CARRIER,
                    stage=f"{key.lower()}_floor",
                )
            )
        notes.append(f"{key} floor planted: {', '.join(profile.floor)} ({perspective} file)")

    kept.sort(key=lambda item: (item.doc_date, item.subtype, item.track))
    log.debug(
        "perspective.applied",
        case_id=seed.case_id,
        perspective=perspective,
        before=len(candidates),
        after=len(kept),
        suppressed=len(suppressed),
    )
    return PerspectiveResult(
        candidates=tuple(kept), suppressed=suppressed, notes=tuple(notes)
    )


__all__ = [
    "APPLICANT",
    "DEFENSE",
    "FILE_OWNER_AUTHORED",
    "FLOOR_PRIORITY",
    "OWNER_ATTORNEY_ROLE",
    "OWNER_CLIENT_ROLE",
    "PERSPECTIVE_PROFILES",
    "RNG_SALT",
    "ROLE_INJURED_WORKER",
    "WORK_PRODUCT_SWAP",
    "DocumentRoles",
    "EmissionProfile",
    "PerspectiveResult",
    "apply_perspective",
    "document_roles",
    "file_owner_firm",
    "profile_for",
    "scaled_count",
    "swap_subtype",
]
