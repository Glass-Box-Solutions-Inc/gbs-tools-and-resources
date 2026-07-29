"""Lien claimant tracks, from claim through executed resolution.

The substrate models liens as two thin probabilistic nodes. Real applicant
files carry something else entirely: several independent claimants, each with
its own claim, its own notice, often its own conference, and its own executed
resolution — and the fight routinely outlives the case-in-chief, which is why
``post_resolution_litigation`` exists.

Each seeded claimant becomes a :class:`LienTrack`: an ordered, dated document
chain owned end to end by this module.

    lien claim (subtype by claimant type)
      -> NOTICE_OF_LIEN_FILING
      -> [NOTICE_OF_LIEN_CONFERENCE -> PRETRIAL_CONFERENCE_STATEMENT_LIEN]
      -> resolution (LIEN_RESOLUTION | LIEN_STIPULATION_AGREEMENT
                     | LIEN_DISMISSAL | ORDER_ON_LIEN)

Determinism: every claimant choice, conference decision and date offset is
drawn from ``seed.rng("liens")``.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta

import structlog

from wc_caseload_engine.doc_controls import TRACK_LIEN
from wc_caseload_engine.lifecycle_bridge import (
    ROLE_APPLICANT_ATTORNEY,
    ROLE_COURT,
    ROLE_LIEN_CLAIMANT,
    CaseTimeline,
    DatedCandidate,
    fit_track,
)
from wc_caseload_engine.seeds import TREATMENT_LIEN_CLAIMANTS, CaseSeed

log = structlog.get_logger(__name__)

CLAIMANT_SUBTYPES: Mapping[str, str] = {
    "medical_provider": "LIEN_MEDICAL_PROVIDER",
    "hospital": "LIEN_HOSPITAL",
    "pharmacy": "LIEN_PHARMACY",
    "ambulance": "LIEN_AMBULANCE_TRANSPORT",
    "edd": "LIEN_EDD_OVERPAYMENT",
    "attorney_costs": "LIEN_ATTORNEY_COSTS",
    "self_procured": "LIEN_SELF_PROCUREMENT_MEDICAL",
}
"""Seed claimant type -> the classifier subtype for that claimant's lien claim."""

RESOLUTION_SUBTYPES: Mapping[str, str] = {
    "lien_resolution_agreement": "LIEN_RESOLUTION",
    "lien_stipulation": "LIEN_STIPULATION_AGREEMENT",
    "dismissal": "LIEN_DISMISSAL",
    "order_on_lien": "ORDER_ON_LIEN",
}
"""Seed lien resolution -> the document that closes the track."""

MIXED_RESOLUTION_POOL: tuple[str, ...] = (
    "lien_resolution_agreement",
    "lien_stipulation",
    "dismissal",
    "order_on_lien",
)
"""``resolution: mixed`` picks per track from this pool via ``rng("liens")``."""

CLAIMANT_POOL: tuple[str, ...] = (
    "medical_provider",
    "hospital",
    "pharmacy",
    "ambulance",
    "edd",
    "attorney_costs",
    "self_procured",
)
"""Fills out ``liens.count`` when fewer ``claimants`` are named than tracks."""

_CONFERENCE_PROBABILITY = 0.6
"""Chance a negotiated track still goes through a lien conference."""


@dataclass(frozen=True, slots=True)
class LienTrack:
    """One claimant's lien, from claim to disposition."""

    index: int
    claimant: str
    claim_subtype: str
    resolution: str
    resolution_subtype: str | None
    conference: bool
    documents: tuple[DatedCandidate, ...]

    def summary(self, emitted: int | None = None) -> dict[str, object]:
        """Manifest-shaped summary of this track.

        Args:
            emitted: documents this track actually contributed to the plan. The
                lien machine runs *before* perspective suppression and control
                resolution, so ``len(self.documents)`` is a proposal — a case
                that excluded every lien document still reported a track full of
                them. The caller that knows the resolved plan passes the real
                number; ``None`` (a direct caller with no plan in hand) falls
                back to the proposal and says so in ``plannedDocumentCount``.
        """
        planned = len(self.documents)
        return {
            "index": self.index,
            "claimant": self.claimant,
            "claimSubtype": self.claim_subtype,
            "resolution": self.resolution,
            "resolutionSubtype": self.resolution_subtype,
            "conference": self.conference,
            "documentCount": planned if emitted is None else emitted,
            "plannedDocumentCount": planned,
        }


def _claimants_for(seed: CaseSeed, rng: random.Random) -> list[str]:
    """Resolve ``liens.count`` claimant types, honouring those named in the seed.

    Under ``treatment.status: never_treated`` the *derived* pool drops medical,
    hospital and pharmacy claimants. The seed-level validator already rejects
    those when an author names them, but rejecting is the wrong answer here:
    nobody asked for a hospital lien, the engine was about to invent one. Same
    stated-vs-derived split as surgery — a stated conflict is an error, a
    derived one is simply not drawn.

    Without this, ``{status: never_treated, liens: {count: 6, claimants: []}}``
    loaded cleanly and planned LIEN_HOSPITAL and LIEN_PHARMACY into a file whose
    ledger says nobody ever treated.
    """
    liens = seed.lifecycle.liens
    chosen = list(liens.claimants)
    if len(chosen) >= liens.count:
        return chosen[: liens.count]

    allowed = CLAIMANT_POOL
    if seed.scenario.treatment.status == "never_treated":
        allowed = tuple(c for c in CLAIMANT_POOL if c not in TREATMENT_LIEN_CLAIMANTS)

    pool = [c for c in allowed if c not in chosen]
    rng.shuffle(pool)
    while len(chosen) < liens.count:
        chosen.append(pool.pop(0) if pool else rng.choice(allowed))
    return chosen


def _track_resolution(seed: CaseSeed, rng: random.Random) -> str:
    """The resolution route for one track (``mixed`` decides per track)."""
    declared = seed.lifecycle.liens.resolution
    if declared == "mixed":
        return rng.choice(MIXED_RESOLUTION_POOL)
    return declared


def _base_date(seed: CaseSeed, timeline: CaseTimeline, rng: random.Random) -> date:
    """When this case's lien activity starts.

    Post-resolution lien litigation is the common real-world shape: the
    case-in-chief settles, the liens keep fighting. When seeded, every lien
    document is dated strictly after the case-in-chief resolution.
    """
    liens = seed.lifecycle.liens
    resolution_date = timeline.resolution_date
    if liens.post_resolution_litigation and resolution_date is not None:
        return resolution_date + timedelta(days=rng.randint(15, 90))
    proposed = timeline.injury_date + timedelta(days=rng.randint(365, 730))
    if resolution_date is not None and proposed > resolution_date:
        proposed = resolution_date - timedelta(days=rng.randint(30, 120))
    return max(timeline.injury_date, min(proposed, timeline.horizon))


def _track_window(seed: CaseSeed, timeline: CaseTimeline, proposed: Sequence[date]) -> tuple[
    date, date
]:
    """The ``[floor, ceiling]`` one lien track's documents must fit inside.

    The floor is the injury, or the case-in-chief resolution when the seed says
    the liens litigate on past it — a lien conference cannot precede the
    settlement it is fighting over.

    The ceiling is normally the case horizon. For a post-resolution track it is
    **extended past the horizon** to whatever the chain actually needs. This is
    the deliberate half of the fix: post-resolution lien practice genuinely runs
    later than the case-in-chief, and a fixed anchor is an artifact of
    determinism, not a fact about the file. Squeezing five lien documents into
    the days between a late settlement and the anchor is what produced five
    documents sharing one date; letting the track run past the anchor keeps the
    story legible and the ordering real.
    """
    liens = seed.lifecycle.liens
    resolution_date = timeline.resolution_date
    post_resolution = liens.post_resolution_litigation and resolution_date is not None

    floor = resolution_date + timedelta(days=1) if post_resolution else timeline.injury_date
    if post_resolution:
        needed = max(proposed) if proposed else floor
        ceiling = max(timeline.horizon, needed, floor + timedelta(days=len(proposed)))
    else:
        ceiling = timeline.horizon
    return floor, max(ceiling, floor)


def build_lien_tracks(seed: CaseSeed, timeline: CaseTimeline) -> list[LienTrack]:
    """Build every lien track for a case (empty when ``liens.count`` is 0)."""
    liens = seed.lifecycle.liens
    if liens.count <= 0:
        return []

    rng = seed.rng("liens")
    claimants = _claimants_for(seed, rng)
    tracks: list[LienTrack] = []

    for index, claimant in enumerate(claimants):
        claim_subtype = CLAIMANT_SUBTYPES[claimant]
        resolution = _track_resolution(seed, rng)
        resolution_subtype = RESOLUTION_SUBTYPES.get(resolution)

        base = _base_date(seed, timeline, rng)
        # Stagger claimants so a file does not show eight liens filed the same day.
        claim_date = base + timedelta(days=index * rng.randint(3, 21))
        docs: list[DatedCandidate] = [
            DatedCandidate(
                subtype=claim_subtype,
                doc_date=claim_date,
                track=TRACK_LIEN,
                priority=30,
                author_role=ROLE_LIEN_CLAIMANT,
                stage="lien_filing",
                metadata={"lien_index": index, "claimant": claimant},
            ),
            DatedCandidate(
                subtype="NOTICE_OF_LIEN_FILING",
                doc_date=claim_date + timedelta(days=rng.randint(0, 14)),
                track=TRACK_LIEN,
                priority=32,
                author_role=ROLE_LIEN_CLAIMANT,
                stage="lien_filing",
                metadata={"lien_index": index, "claimant": claimant},
            ),
        ]

        # An adjudicated disposition always follows a conference; a negotiated
        # one usually does, but can settle on the papers.
        conference = resolution == "order_on_lien" or (
            resolution != "pending" and rng.random() < _CONFERENCE_PROBABILITY
        )
        conference_date = claim_date + timedelta(days=rng.randint(60, 180))
        if conference:
            docs.append(
                DatedCandidate(
                    subtype="NOTICE_OF_LIEN_CONFERENCE",
                    doc_date=conference_date,
                    track=TRACK_LIEN,
                    priority=34,
                    author_role=ROLE_COURT,
                    stage="lien_conference",
                    metadata={"lien_index": index, "claimant": claimant},
                )
            )
            docs.append(
                DatedCandidate(
                    subtype="PRETRIAL_CONFERENCE_STATEMENT_LIEN",
                    doc_date=conference_date + timedelta(days=rng.randint(20, 45)),
                    track=TRACK_LIEN,
                    priority=36,
                    author_role=ROLE_APPLICANT_ATTORNEY,
                    stage="lien_conference",
                    metadata={"lien_index": index, "claimant": claimant},
                )
            )

        if resolution_subtype is not None:
            anchor = conference_date if conference else claim_date
            docs.append(
                DatedCandidate(
                    subtype=resolution_subtype,
                    doc_date=anchor + timedelta(days=rng.randint(30, 150)),
                    track=TRACK_LIEN,
                    priority=28,
                    author_role=(
                        ROLE_COURT if resolution == "order_on_lien" else ROLE_APPLICANT_ATTORNEY
                    ),
                    stage="lien_conference",
                    metadata={"lien_index": index, "claimant": claimant},
                )
            )

        # Dates above are the chain's *intent*, deliberately unclamped. Fitting
        # the whole chain at once is what keeps the ordering; clamping each date
        # as it was built is what used to pile a whole track onto the horizon.
        floor, ceiling = _track_window(seed, timeline, [doc.doc_date for doc in docs])
        docs = fit_track(docs, floor=floor, ceiling=ceiling, label=f"lien[{index}]:{claimant}")

        tracks.append(
            LienTrack(
                index=index,
                claimant=claimant,
                claim_subtype=claim_subtype,
                resolution=resolution,
                resolution_subtype=resolution_subtype,
                conference=conference,
                documents=tuple(docs),
            )
        )

    log.debug(
        "liens.built",
        case_id=seed.case_id,
        tracks=len(tracks),
        post_resolution=liens.post_resolution_litigation,
    )
    return tracks


def lien_candidates(tracks: Sequence[LienTrack]) -> list[DatedCandidate]:
    """Flatten every track's documents into one dated candidate list."""
    out: list[DatedCandidate] = []
    for track in tracks:
        out.extend(track.documents)
    out.sort(key=lambda item: (item.doc_date, item.subtype))
    return out


__all__ = [
    "CLAIMANT_POOL",
    "CLAIMANT_SUBTYPES",
    "MIXED_RESOLUTION_POOL",
    "RESOLUTION_SUBTYPES",
    "LienTrack",
    "build_lien_tracks",
    "lien_candidates",
]
