"""The petition-for-reconsideration round trip.

Reconsideration is the appellate move inside the WCAB, and it is the shape the
substrate models least: a couple of low-probability documents dangling off
``post_resolution``. It deserves a real machine, because "denied, petitioned,
remanded, settled on remand" is an ordinary applicant-side file and no
generator could previously produce one.

The chain, with its statutory clock:

    FINDINGS_AND_AWARD / ORDER_APPROVING_SETTLEMENT   (the award under attack)
      -> PETITION_RECONSIDERATION_FILED               LC 5903: <= 25 days
      -> PETITION_RECONSIDERATION_OPPOSITION
      -> [PETITION_RECONSIDERATION_REPLY]             (seed-drawn)
      -> ORDER_ON_RECONSIDERATION                     LC 5909: <= 60 days

Then the seeded outcome decides what the file looks like afterwards:

============================  ==========================================
``outcome`` / ``post_recon``  Documents
============================  ==========================================
denied / affirmed_final       nothing — the award stands
granted_remand /              DECLARATION_OF_READINESS,
  further_litigation          NOTICE_OF_HEARING_COURT_ISSUED,
                              MINUTES_OF_HEARING, AMENDED_FINDINGS_AWARD
granted_remand / settled      C&R or Stips + ORDER_APPROVING_SETTLEMENT,
                              all dated after the reconsideration order
granted_reversed              AMENDED_FINDINGS_AWARD, plus whatever its
                              ``post_recon`` path adds
============================  ==========================================

A petition with nothing to attack is a contradiction, so an unresolved case
with ``reconsideration.enabled`` emits nothing and says so loudly.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta

import structlog

from wc_caseload_engine.doc_controls import TRACK_RECON
from wc_caseload_engine.lifecycle_bridge import (
    ROLE_APPLICANT_ATTORNEY,
    ROLE_COURT,
    ROLE_DEFENSE_ATTORNEY,
    CaseTimeline,
    DatedCandidate,
    fit_track,
)
from wc_caseload_engine.seeds import CaseSeed

log = structlog.get_logger(__name__)

PETITION_WINDOW_DAYS = 25
"""LC 5903 — 20 days from service, plus 5 for mail service."""

ORDER_WINDOW_DAYS = 60
"""LC 5909 — the WCAB must act on the petition within 60 days."""

_REPLY_PROBABILITY = 0.45
"""Chance the petitioner files a reply to the opposition."""

_SETTLE_AS_CR_PROBABILITY = 0.6
"""On remand, parties more often close with a C&R than with new stips."""


@dataclass(frozen=True, slots=True)
class ReconTrack:
    """The reconsideration round trip and everything it produced."""

    enabled: bool
    outcome: str | None
    post_recon: str | None
    award_date: date | None
    petition_date: date | None
    order_date: date | None
    documents: tuple[DatedCandidate, ...]
    warnings: tuple[str, ...] = ()

    def summary(self, emitted: int | None = None) -> dict[str, object]:
        """Manifest-shaped summary of the recon round trip.

        Args:
            emitted: documents this track actually contributed to the plan.
                ``len(self.documents)`` is what the machine proposed, before
                perspective and the document controls trimmed it — see
                :meth:`wc_caseload_engine.lien_machine.LienTrack.summary`.
        """
        planned = len(self.documents)
        return {
            "enabled": self.enabled,
            "outcome": self.outcome,
            "postRecon": self.post_recon,
            "awardDate": self.award_date.isoformat() if self.award_date else None,
            "petitionDate": self.petition_date.isoformat() if self.petition_date else None,
            "orderDate": self.order_date.isoformat() if self.order_date else None,
            "documentCount": planned if emitted is None else emitted,
            "plannedDocumentCount": planned,
        }


def _empty(seed: CaseSeed, warnings: tuple[str, ...] = ()) -> ReconTrack:
    """A disabled (or impossible) recon track."""
    recon = seed.lifecycle.reconsideration
    return ReconTrack(
        enabled=recon.enabled,
        outcome=recon.outcome,
        post_recon=recon.post_recon,
        award_date=None,
        petition_date=None,
        order_date=None,
        documents=(),
        warnings=warnings,
    )


def _post_recon_litigation(
    timeline: CaseTimeline, order_date: date, rng: random.Random
) -> list[DatedCandidate]:
    """Remand back to the trial level: new DOR, new hearing, amended award."""
    del timeline  # dates are fitted as one chain in build_recon_track
    dor = order_date + timedelta(days=rng.randint(15, 45))
    notice = dor + timedelta(days=rng.randint(20, 60))
    minutes = notice + timedelta(days=rng.randint(30, 90))
    amended = minutes + timedelta(days=rng.randint(10, 45))
    return [
        DatedCandidate(
            subtype="DECLARATION_OF_READINESS",
            doc_date=dor,
            track=TRACK_RECON,
            priority=22,
            author_role=ROLE_APPLICANT_ATTORNEY,
            stage="post_recon",
        ),
        DatedCandidate(
            subtype="NOTICE_OF_HEARING_COURT_ISSUED",
            doc_date=notice,
            track=TRACK_RECON,
            priority=22,
            author_role=ROLE_COURT,
            stage="post_recon",
        ),
        DatedCandidate(
            subtype="MINUTES_OF_HEARING",
            doc_date=minutes,
            track=TRACK_RECON,
            priority=20,
            author_role=ROLE_COURT,
            stage="post_recon",
        ),
        DatedCandidate(
            subtype="AMENDED_FINDINGS_AWARD",
            doc_date=amended,
            track=TRACK_RECON,
            priority=18,
            author_role=ROLE_COURT,
            stage="post_recon",
        ),
    ]


def _post_recon_settlement(
    seed: CaseSeed, timeline: CaseTimeline, order_date: date, rng: random.Random
) -> list[DatedCandidate]:
    """Settled on remand: a new settlement and its approving order, post-recon."""
    del timeline  # dates are fitted as one chain in build_recon_track
    settled_on = order_date + timedelta(days=rng.randint(30, 120))
    approved_on = settled_on + timedelta(days=rng.randint(15, 60))
    if seed.injury.type == "death":
        settlement = "COMPROMISE_AND_RELEASE_DEPENDENCY"
    elif rng.random() < _SETTLE_AS_CR_PROBABILITY:
        settlement = (
            "COMPROMISE_AND_RELEASE_MSA"
            if seed.lifecycle.resolution.msa
            else "COMPROMISE_AND_RELEASE_STANDARD"
        )
    else:
        settlement = "STIPULATIONS_WITH_REQUEST_FOR_AWARD"
    return [
        DatedCandidate(
            subtype=settlement,
            doc_date=settled_on,
            track=TRACK_RECON,
            priority=18,
            author_role=ROLE_APPLICANT_ATTORNEY,
            stage="post_recon",
        ),
        DatedCandidate(
            subtype="ORDER_APPROVING_SETTLEMENT",
            doc_date=approved_on,
            track=TRACK_RECON,
            priority=18,
            author_role=ROLE_COURT,
            stage="post_recon",
        ),
    ]


def _order_date(rng: random.Random, *, petition_date: date, last_brief: date) -> date:
    """When the Board rules — after the briefing closes, inside LC 5909 if it can.

    Two constraints, and they can disagree. LC 5909 gives the WCAB sixty days
    from the petition; the briefing schedule can put the petitioner's reply as
    late as petition + 30. Drawing the order independently of the briefing (the
    old behaviour) let the second constraint lose silently, producing an order
    dated a day *before* the reply it had supposedly considered.

    So the floor is the later of the two — thirty days for the Board to work,
    and at minimum the day after the last brief — and the statutory window is
    the ceiling only when it is still above that floor. A ruling one day late is
    a realistic file; a ruling that predates the briefing is not a file at all.
    """
    floor = max(petition_date + timedelta(days=30), last_brief + timedelta(days=1))
    ceiling = max(floor, petition_date + timedelta(days=ORDER_WINDOW_DAYS))
    return floor + timedelta(days=rng.randint(0, (ceiling - floor).days))


def build_recon_track(seed: CaseSeed, timeline: CaseTimeline) -> ReconTrack:
    """Build the reconsideration round trip for a case."""
    recon = seed.lifecycle.reconsideration
    if not recon.enabled:
        return _empty(seed)

    award_date = timeline.award_date
    if award_date is None:
        warning = (
            f"case {seed.case_id}: lifecycle.reconsideration.enabled is true but "
            f"lifecycle.resolution.type is {seed.lifecycle.resolution.type!r} — there is no "
            "award to reconsider, so no reconsideration documents were emitted "
            "(set resolution.type to findings_award, stipulations or c_and_r)"
        )
        log.warning(
            "recon.no_award",
            case_id=seed.case_id,
            resolution=seed.lifecycle.resolution.type,
        )
        return _empty(seed, warnings=(warning,))

    rng = seed.rng("recon")

    # Unclamped by design: the whole chain is fitted once, at the end, so its
    # ordering survives a tight window instead of collapsing onto the horizon.
    petition_date = award_date + timedelta(days=rng.randint(1, PETITION_WINDOW_DAYS))
    opposition_date = petition_date + timedelta(days=rng.randint(5, 15))

    documents: list[DatedCandidate] = [
        DatedCandidate(
            subtype="PETITION_RECONSIDERATION_FILED",
            doc_date=petition_date,
            track=TRACK_RECON,
            priority=8,
            author_role=ROLE_APPLICANT_ATTORNEY,
            stage="post_recon",
        ),
        DatedCandidate(
            subtype="PETITION_RECONSIDERATION_OPPOSITION",
            doc_date=opposition_date,
            track=TRACK_RECON,
            priority=12,
            author_role=ROLE_DEFENSE_ATTORNEY,
            stage="post_recon",
        ),
    ]

    # The reply, when it is filed, is the last word before the Board rules.
    last_brief = opposition_date
    if rng.random() < _REPLY_PROBABILITY:
        last_brief = opposition_date + timedelta(days=rng.randint(5, 15))
        documents.append(
            DatedCandidate(
                subtype="PETITION_RECONSIDERATION_REPLY",
                doc_date=last_brief,
                track=TRACK_RECON,
                priority=14,
                author_role=ROLE_APPLICANT_ATTORNEY,
                stage="post_recon",
            )
        )

    order_date = _order_date(rng, petition_date=petition_date, last_brief=last_brief)
    documents.append(
        DatedCandidate(
            subtype="ORDER_ON_RECONSIDERATION",
            doc_date=order_date,
            track=TRACK_RECON,
            priority=8,
            author_role=ROLE_COURT,
            stage="post_recon",
        )
    )

    # Everything from here follows the order, so it is a tail on the chain
    # rather than another interleaved draw.
    tail: list[DatedCandidate] = []

    # A reversal rewrites the award on its face, before any remand proceedings.
    if recon.outcome == "granted_reversed":
        tail.append(
            DatedCandidate(
                subtype="AMENDED_FINDINGS_AWARD",
                doc_date=order_date + timedelta(days=rng.randint(1, 21)),
                track=TRACK_RECON,
                priority=10,
                author_role=ROLE_COURT,
                stage="post_recon",
            )
        )

    if recon.post_recon == "further_litigation":
        tail.extend(_post_recon_litigation(timeline, order_date, rng))
    elif recon.post_recon == "settled":
        tail.extend(_post_recon_settlement(seed, timeline, order_date, rng))

    # A reversal and a remand can both want an amended award; keep the later one.
    deduped: dict[tuple[str, date], DatedCandidate] = {}
    for candidate in tail:
        deduped[(candidate.subtype, candidate.doc_date)] = candidate
    ordered = [
        *documents,
        *sorted(deduped.values(), key=lambda item: (item.doc_date, item.subtype)),
    ]

    # One fit for the whole round trip, over a list that is already in *legal*
    # order rather than one sorted by date. Sorting by ``(date, subtype)`` was
    # the defect: it accepted whatever order the independent draws happened to
    # produce, so a reply drawn at opposition+15 landed after an order drawn at
    # petition+30 and the sort dutifully filed the reply behind the ruling it
    # was replying to. Order is now a property of the sequence, and the dates
    # are fitted to the sequence — never the other way round.
    ordered = fit_track(
        ordered,
        floor=award_date + timedelta(days=1),
        ceiling=max(timeline.horizon, award_date + timedelta(days=len(ordered))),
        label=f"recon:{seed.case_id}",
    )
    petition_date = ordered[0].doc_date
    order_date = next(
        (doc.doc_date for doc in ordered if doc.subtype == "ORDER_ON_RECONSIDERATION"),
        order_date,
    )

    log.debug(
        "recon.built",
        case_id=seed.case_id,
        outcome=recon.outcome,
        post_recon=recon.post_recon,
        documents=len(ordered),
    )
    return ReconTrack(
        enabled=True,
        outcome=recon.outcome,
        post_recon=recon.post_recon,
        award_date=award_date,
        petition_date=petition_date,
        order_date=order_date,
        documents=tuple(ordered),
    )


__all__ = [
    "ORDER_WINDOW_DAYS",
    "PETITION_WINDOW_DAYS",
    "ReconTrack",
    "build_recon_track",
]
