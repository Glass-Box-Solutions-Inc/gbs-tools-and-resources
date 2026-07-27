"""Core-track lifecycle: the seed's story, walked over the substrate DAG.

The substrate (``data.lifecycle_engine``) owns a rich, probabilistic document
DAG. This module maps a :class:`~wc_caseload_engine.seeds.CaseSeed` onto that
DAG, walks it, and normalizes the result into dated, tracked candidates.

**Where the walk fights the seed, the seed wins.** The substrate's branching is
probabilistic and its vocabulary predates several classifier subtypes, so three
classes of correction are applied deterministically:

1. *Ownership* — lien and reconsideration documents are stripped from the walk
   entirely. :mod:`wc_caseload_engine.lien_machine` and
   :mod:`wc_caseload_engine.recon_machine` own those tracks; letting the
   substrate also emit them would produce duplicate documents with claimant
   types and dates that contradict the seed.
2. *Guarantees* — the seed's ``resolution.type`` (and death/UR/IMR branches)
   emit their signature documents by construction, not by probability. The
   substrate's ``resolution_cr`` node, for example, never emits
   ``ORDER_APPROVING_SETTLEMENT``; a C&R without its approving order is not a
   resolved case.
3. *Vocabulary* — the substrate enum carries 34 realism subtypes that are not
   classifier vocabulary. Each is mapped to a canonical equivalent where one
   exists and dropped otherwise, so nothing non-canonical can reach a manifest.

Determinism rule: every date and every draw comes from ``seed.rng(salt)``.
Nothing here reads the wall clock — :data:`~wc_caseload_engine.seeds.ANCHOR_DATE`
is "today", and no document may be dated after it.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import structlog

from wc_caseload_engine.doc_controls import (
    TRACK_CORE,
    TRACK_FILLER,
    TRACK_SUPPORTING,
    DocumentCandidate,
)
from wc_caseload_engine.seeds import ANCHOR_DATE, BODY_PART_CATALOG, CaseSeed
from wc_caseload_engine.substrate import import_substrate
from wc_caseload_engine.taxonomy import effective_taxonomy

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Author roles (who produced the document — drives the party block)
# ---------------------------------------------------------------------------

ROLE_APPLICANT_ATTORNEY = "applicant_attorney"
ROLE_DEFENSE_ATTORNEY = "defense_attorney"
ROLE_CARRIER = "carrier"
ROLE_PHYSICIAN = "physician"
ROLE_COURT = "court"
ROLE_EMPLOYER = "employer"
ROLE_LIEN_CLAIMANT = "lien_claimant"

# ---------------------------------------------------------------------------
# Seed -> substrate parameter mapping
# ---------------------------------------------------------------------------

TARGET_STAGE_MAP: Mapping[str, str] = {
    "intake": "intake",
    "active_treatment": "active_treatment",
    "discovery": "discovery",
    "medical_legal": "medical_legal",
    "pre_trial": "settlement",
    "resolved": "resolved",
    "post_recon": "resolved",
}
"""Seed ``target_stage`` -> substrate ``target_stage``.

The substrate predates ``pre_trial`` and ``post_recon``; both are expressed in
its vocabulary (``settlement`` / ``resolved``) and the extra reach is supplied
by this engine's own machines.
"""

RESOLUTION_MAP: Mapping[str, str] = {
    "stipulations": "stipulations",
    "c_and_r": "c_and_r",
    "findings_award": "trial",
    "take_nothing": "trial",
    "pending": "pending",
}
"""Seed resolution -> substrate ``resolution_type`` (which knows only three)."""

UR_DECISION_MAP: Mapping[str, str] = {"upheld": "denied", "overturned": "approved"}
"""Seed UR decision -> substrate vocabulary.

The seed speaks from the *dispute's* point of view (the UR denial was
``upheld``), the substrate from the *treatment request's* (the request was
``denied``). Getting this backwards would route IMR appeals onto approvals.
"""

# ---------------------------------------------------------------------------
# Vocabulary normalization (substrate-only -> canonical, or dropped)
# ---------------------------------------------------------------------------

SUBSTRATE_TO_CANONICAL: Mapping[str, str] = {
    "ATTORNEY_FEE_PETITION": "ATTORNEY_FEE_DISCLOSURE",
    "CLIENT_CASE_VALUATION_LETTER": "CLIENT_CORRESPONDENCE_INFORMATIONAL",
    "CLIENT_REPORT_ANALYSIS_LETTER": "CLIENT_CORRESPONDENCE_INFORMATIONAL",
    "CLIENT_SETTLEMENT_RECOMMENDATION": "CLIENT_CORRESPONDENCE_INFORMATIONAL",
    "DEPOSITION_TRANSCRIPT_QME_AME": "DEPOSITION_TRANSCRIPT",
    "FAX_COVER_SHEET": "FAX_CORRESPONDENCE",
    "INFORMAL_PD_RATING_PRINTOUT": "PD_RATING_CALCULATION_WORKSHEET",
    "JOINT_PRETRIAL_CONFERENCE_STATEMENT": "PRETRIAL_CONFERENCE_STATEMENT",
    "MILEAGE_REIMBURSEMENT_REQUEST": "MEDICAL_MILEAGE_EXPENSE",
    "PETITION_FOR_PENALTIES_LC_5814": "PETITION_FOR_PENALTIES",
    "RETURN_TO_WORK_REPORT": "RETURN_TO_WORK_COORDINATION",
}
"""Substrate-only subtypes with an unambiguous classifier equivalent.

Deliberately conservative. A wrong mapping silently poisons the classifier
accuracy corpus this engine exists to feed, so anything requiring judgement is
dropped instead (see :data:`DROPPED_SUBSTRATE_ONLY`) — losing a realism filler
costs nothing, mislabelling one costs measurement integrity.
"""

DROPPED_SUBSTRATE_ONLY: frozenset[str] = frozenset(
    {
        "BLANK_SCANNED_PAGE",
        "CARRIER_POSITION_STATEMENT",
        "CLIENT_DECLARATION",
        "CLIENT_HIPAA_AUTHORIZATION",
        "CMS_CONDITIONAL_PAYMENT_LETTER",
        "COVER_LETTER_ENCLOSURE",
        "EAMS_CASE_SUMMARY",
        "EXHIBIT_LIST",
        "INTERNAL_FILE_NOTE",
        "INTERROGATORIES_SPECIAL",
        "INTERROGATORY_RESPONSES",
        "NOTICE_OF_TD_TERMINATION",
        "OBJECTION_TO_QME_AME_REPORT",
        "PRODUCTION_RESPONSES",
        "PTP_REFERRAL_LETTER",
        "QME_PANEL_STRIKE_LETTER",
        "REQUEST_FOR_CONTINUANCE",
        "REQUEST_FOR_PRODUCTION",
        "REQUEST_SUPPLEMENTAL_QME_AME_REPORT",
        "RESERVATION_OF_RIGHTS_LETTER",
        "RETAINER_FEE_AGREEMENT",
        "TD_RATE_CALCULATION_NOTICE",
        "WITNESS_LIST",
    }
)
"""Substrate-only subtypes with no honest canonical equivalent — never emitted."""

LIEN_OWNED_SUBTYPES: frozenset[str] = frozenset(
    {
        "LIEN_AMBULANCE_TRANSPORT",
        "LIEN_ATTORNEY_COSTS",
        "LIEN_CLAIM",
        "LIEN_DISMISSAL",
        "LIEN_EDD_OVERPAYMENT",
        "LIEN_HOSPITAL",
        "LIEN_MEDICAL_PROVIDER",
        "LIEN_PHARMACY",
        "LIEN_RESOLUTION",
        "LIEN_SELF_PROCUREMENT_MEDICAL",
        "LIEN_STIPULATION_AGREEMENT",
        "NOTICE_OF_INTENT_TO_FILE_LIEN",
        "NOTICE_OF_LIEN_CONFERENCE",
        "NOTICE_OF_LIEN_FILING",
        "ORDER_ON_LIEN",
        "PRETRIAL_CONFERENCE_STATEMENT_LIEN",
    }
)
"""Owned by :mod:`wc_caseload_engine.lien_machine` — stripped from the walk."""

RECON_OWNED_SUBTYPES: frozenset[str] = frozenset(
    {
        "AMENDED_FINDINGS_AWARD",
        "ORDER_ON_RECONSIDERATION",
        "PETITION_RECONSIDERATION_FILED",
        "PETITION_RECONSIDERATION_OPPOSITION",
        "PETITION_RECONSIDERATION_REPLY",
    }
)
"""Owned by :mod:`wc_caseload_engine.recon_machine` — stripped from the walk."""

# Subtypes whose realism value is low enough that the cap should eat them first.
_FILLER_SUBTYPES: frozenset[str] = frozenset(
    {"FAX_CORRESPONDENCE", "CLAIMS_DIARY_NOTE", "PROOF_OF_SERVICE", "COURT_DISTRICT_NOTICE"}
)

SINGLETON_SUBTYPES: frozenset[str] = frozenset(
    {
        "AMENDED_FINDINGS_AWARD",
        "APPLICATION_FOR_ADJUDICATION_DEATH",
        "APPLICATION_FOR_ADJUDICATION_ORIGINAL",
        "CLAIM_ACCEPTANCE_LETTER",
        "CLAIM_DELAY_NOTICE",
        "CLAIM_DENIAL_LETTER",
        "CLAIM_FORM_DWC1",
        "COMPROMISE_AND_RELEASE",
        "COMPROMISE_AND_RELEASE_DEPENDENCY",
        "COMPROMISE_AND_RELEASE_MSA",
        "COMPROMISE_AND_RELEASE_PD_ONLY",
        "COMPROMISE_AND_RELEASE_STANDARD",
        "DEATH_CERTIFICATE",
        "DEPENDENCY_DECLARATION",
        "EMPLOYER_REPORT_INJURY",
        "FINDINGS_AND_AWARD",
        "IMR_APPLICATION_FORM",
        "IMR_DETERMINATION_FORM",
        "NOTICE_OF_EMPLOYEE_DEATH",
        "NOTICE_OF_REPRESENTATION",
        "OPINION_ON_DECISION",
        "ORDER_APPOINTING_QME_PANEL",
        "ORDER_APPROVING_SETTLEMENT",
        "STIPULATIONS_DEATH_CASE",
        "STIPULATIONS_WITH_REQUEST_FOR_AWARD",
        "STIPULATIONS_WITH_REQUEST_FOR_AWARD_FULL",
    }
)
"""Documents a case has exactly one of.

The substrate scales complex cases by multiplying every rule's count (2-3x),
which is right for treatment reports and wrong for dispositive paperwork — it
produced three denial letters and two Compromise and Release agreements on one
claim. These are trimmed to a single copy after the walk, keeping the most
essential candidate (a deterministic guarantee outranks a probabilistic hit).

Lien and reconsideration subtypes are deliberately absent: three lien claimants
genuinely produce three Lien Resolution Agreements. An explicit per-subtype
override still wins over this cap, loudly, as the control precedence promises.
"""

_ROLE_BY_PREFIX: tuple[tuple[str, str], ...] = (
    ("ADJUSTER_", ROLE_CARRIER),
    ("CLAIM_", ROLE_CARRIER),
    ("CLAIMS_", ROLE_CARRIER),
    ("NOTICE_OF_BENEFITS", ROLE_CARRIER),
    ("RESERVE_", ROLE_CARRIER),
    ("COMPENSABILITY_", ROLE_CARRIER),
    ("TD_", ROLE_CARRIER),
    ("PD_PAYMENT", ROLE_CARRIER),
    ("BENEFIT_", ROLE_CARRIER),
    ("EXPLANATION_OF_REVIEW", ROLE_CARRIER),
    ("UTILIZATION_", ROLE_CARRIER),
    ("MEDICAL_TREATMENT_", ROLE_CARRIER),
    ("IMR_", ROLE_CARRIER),
    ("INDEPENDENT_MEDICAL_REVIEW", ROLE_CARRIER),
    ("DEFENSE_", ROLE_DEFENSE_ATTORNEY),
    ("ANSWER_TO_", ROLE_DEFENSE_ATTORNEY),
    ("ORDER_", ROLE_COURT),
    ("MINUTES_", ROLE_COURT),
    ("NOTICE_OF_HEARING", ROLE_COURT),
    ("NOTICE_OF_TRIAL", ROLE_COURT),
    ("NOTICE_OF_MSC", ROLE_COURT),
    ("OPINION_ON_DECISION", ROLE_COURT),
    ("FINDINGS_AND_AWARD", ROLE_COURT),
    ("COURT_", ROLE_COURT),
    ("EMPLOYER_", ROLE_EMPLOYER),
    ("WAGE_", ROLE_EMPLOYER),
    ("JOB_", ROLE_EMPLOYER),
    ("PERSONNEL_", ROLE_EMPLOYER),
    ("TIMECARDS", ROLE_EMPLOYER),
    ("OFFER_OF_WORK", ROLE_EMPLOYER),
    ("TREATING_PHYSICIAN", ROLE_PHYSICIAN),
    ("QME_", ROLE_PHYSICIAN),
    ("AME_", ROLE_PHYSICIAN),
    ("PSYCH_", ROLE_PHYSICIAN),
    ("DIAGNOSTICS_", ROLE_PHYSICIAN),
    ("ORTHOPEDIC_", ROLE_PHYSICIAN),
    ("PHYSICAL_THERAPY", ROLE_PHYSICIAN),
    ("PHARMACY_", ROLE_PHYSICIAN),
    ("OPERATIVE_", ROLE_PHYSICIAN),
    ("DISCHARGE_", ROLE_PHYSICIAN),
    ("EMERGENCY_", ROLE_PHYSICIAN),
    ("FIRST_REPORT", ROLE_PHYSICIAN),
    ("ONGOING_TREATMENT", ROLE_PHYSICIAN),
    ("PAIN_MANAGEMENT", ROLE_PHYSICIAN),
    ("CHIROPRACTIC_", ROLE_PHYSICIAN),
    ("ACUPUNCTURE_", ROLE_PHYSICIAN),
    ("WORK_RESTRICTIONS", ROLE_PHYSICIAN),
    ("APPORTIONMENT_", ROLE_PHYSICIAN),
    ("LIEN_", ROLE_LIEN_CLAIMANT),
)


def author_role_for(subtype: str) -> str:
    """Best-effort author role for a subtype (applicant-side is the default)."""
    for prefix, role in _ROLE_BY_PREFIX:
        if subtype.startswith(prefix):
            return role
    return ROLE_APPLICANT_ATTORNEY


# ---------------------------------------------------------------------------
# Dated candidates and the case timeline
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DatedCandidate:
    """One proposed document with its date, track and provenance."""

    subtype: str
    doc_date: date
    track: str = TRACK_CORE
    priority: int = 50
    author_role: str = ROLE_APPLICANT_ATTORNEY
    stage: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_candidate(self, parent_type: str | None = None) -> DocumentCandidate:
        """Adapt to the control resolver's input type."""
        return DocumentCandidate(
            subtype=self.subtype,
            priority=self.priority,
            track=self.track,
            parent_type=parent_type,
            count=1,
            metadata={"stage": self.stage, "author_role": self.author_role},
        )


@dataclass(frozen=True, slots=True)
class CaseTimeline:
    """The dates every track hangs off, all derived from the seed."""

    injury_date: date
    claim_filed_date: date
    application_filed_date: date
    resolution_date: date | None
    award_date: date | None
    horizon: date = ANCHOR_DATE

    def clamp(self, value: date) -> date:
        """Never let a document be dated in the future or before the injury."""
        if value > self.horizon:
            return self.horizon
        if value < self.injury_date:
            return self.injury_date
        return value

    def anchor(self, name: str) -> date:
        """Resolve a substrate ``date_anchor`` name to a real date."""
        if name == "claim_filed":
            return self.claim_filed_date
        if name == "application_filed":
            return self.application_filed_date
        return self.injury_date


RECON_RESERVE_DAYS: Mapping[str | None, int] = {
    None: 0,
    "affirmed_final": 120,
    "settled": 280,
    "further_litigation": 340,
}
"""Days of runway reserved after the award for each post-reconsideration path."""


def recon_enabled(seed: CaseSeed) -> bool:
    """``True`` when the seed asks for a reconsideration round trip."""
    return seed.lifecycle.reconsideration.enabled


def _offset(rng: random.Random, bounds: tuple[int, int]) -> int:
    """Inclusive random day offset from a substrate rule's ``date_offset_days``."""
    low, high = bounds
    if low > high:
        low, high = high, low
    return rng.randint(low, high)


def build_timeline(seed: CaseSeed) -> CaseTimeline:
    """Derive the case's spine of dates from the seed alone.

    Statutory shape encoded here:

    * the DWC-1 is filed within two weeks of the injury,
    * the carrier's accept/deny decision lands inside the LC 5402 90-day window
      (enforced by the substrate's own ``claim_response`` offsets),
    * the Application for Adjudication follows two to six months later,
    * resolution — and therefore the award that a petition for reconsideration
      attacks — is at least six months after the application.
    """
    rng = seed.rng("dates")
    injury = seed.injury.onset_date
    horizon = ANCHOR_DATE

    claim_filed = min(injury + timedelta(days=rng.randint(1, 14)), horizon)
    application_filed = min(injury + timedelta(days=rng.randint(60, 180)), horizon)

    resolution_type = seed.lifecycle.resolution.type
    if resolution_type == "pending":
        return CaseTimeline(
            injury_date=injury,
            claim_filed_date=claim_filed,
            application_filed_date=application_filed,
            resolution_date=None,
            award_date=None,
            horizon=horizon,
        )

    # Everything after the award needs runway, or the clamp to ANCHOR_DATE
    # collapses the sequence into a single day. The petition window (25) plus
    # the decision window (60) is the floor; a remand that goes back to trial
    # or settles needs months more.
    reserve = RECON_RESERVE_DAYS.get(
        seed.lifecycle.reconsideration.post_recon if recon_enabled(seed) else None, 0
    )
    earliest = application_filed + timedelta(days=180)
    proposed = injury + timedelta(days=rng.randint(600, 1000))
    latest = horizon - timedelta(days=reserve)
    resolution = max(earliest, proposed)
    if resolution > latest:
        resolution = latest
    if resolution < injury:
        resolution = injury
    resolution = min(resolution, horizon)

    return CaseTimeline(
        injury_date=injury,
        claim_filed_date=claim_filed,
        application_filed_date=application_filed,
        resolution_date=resolution,
        award_date=resolution,
        horizon=horizon,
    )


# ---------------------------------------------------------------------------
# Substrate parameter construction
# ---------------------------------------------------------------------------


def _body_part_category(seed: CaseSeed) -> str:
    """Reverse-map the seed's first body part onto a substrate category."""
    first = seed.injury.body_parts[0].part
    for category, entries in BODY_PART_CATALOG.items():
        if any(part == first for part, _icd, _detail in entries):
            return category
    return "spine"


def seed_to_case_parameters(seed: CaseSeed) -> Any:
    """Build the substrate's :class:`CaseParameters` from a seed.

    ``has_liens`` is deliberately forced to ``False``: the substrate's lien
    nodes would emit a second, contradictory set of lien documents alongside
    :mod:`wc_caseload_engine.lien_machine`, which owns that track.
    """
    lifecycle_engine = import_substrate("data.lifecycle_engine")
    lifecycle = seed.lifecycle
    rng = seed.rng("clinical")

    psych = any(part.part == "psyche" for part in seed.injury.body_parts)
    if "lc3208_3_psych" in lifecycle.doctrine_hooks:
        psych = True

    complexity = (
        "complex"
        if len(seed.injury.body_parts) >= 3 or len(lifecycle.doctrine_hooks) >= 2
        else "standard"
    )

    ur = lifecycle.ur_dispute
    return lifecycle_engine.CaseParameters(
        claim_response=lifecycle.claim_response,
        has_attorney=True,
        has_ur_dispute=ur.enabled,
        ur_decision=UR_DECISION_MAP.get(ur.decision or "", "random"),
        imr_filed=ur.imr,
        imr_outcome=ur.imr_outcome or "random",
        eval_type=lifecycle.eval_type,
        resolution_type=RESOLUTION_MAP[lifecycle.resolution.type],
        has_surgery=seed.injury.type != "death" and not psych and rng.random() < 0.35,
        has_psych_component=psych,
        has_liens=False,
        num_body_parts=len(seed.injury.body_parts),
        is_medicare_eligible=lifecycle.resolution.msa,
        complexity=complexity,
        target_stage=TARGET_STAGE_MAP[lifecycle.target_stage],
        injury_type=seed.injury.type,
        body_part_category=_body_part_category(seed),
    )


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------


def normalize_subtype(subtype: str) -> str | None:
    """Map a substrate subtype to canonical vocabulary, or ``None`` to drop it.

    Guarantees the caller can never place a non-classifier key in a manifest.
    """
    taxonomy = effective_taxonomy()
    if subtype in SUBSTRATE_TO_CANONICAL:
        return SUBSTRATE_TO_CANONICAL[subtype]
    if subtype in DROPPED_SUBSTRATE_ONLY:
        return None
    if taxonomy.is_canonical(subtype):
        return subtype
    log.debug("lifecycle.subtype_dropped", subtype=subtype, reason="not canonical")
    return None


def _priority_for(subtype: str, stage: str) -> tuple[int, str]:
    """Essentiality rank and trim track for a walked document."""
    if subtype in _FILLER_SUBTYPES:
        return 85, TRACK_FILLER
    if stage in {"injury", "claim_filed", "claim_response"}:
        return 15, TRACK_CORE
    if stage in {"resolution_stipulations", "resolution_cr", "resolution_trial"}:
        return 10, TRACK_CORE
    if stage in {"qme_evaluation", "ame_evaluation", "application_filed"}:
        return 25, TRACK_CORE
    if stage in {"discovery", "ur_dispute", "ur_decision", "imr_appeal"}:
        return 45, TRACK_SUPPORTING
    return 60, TRACK_SUPPORTING


# ---------------------------------------------------------------------------
# The walk
# ---------------------------------------------------------------------------


def walk_core_track(seed: CaseSeed, timeline: CaseTimeline) -> list[DatedCandidate]:
    """Walk the substrate DAG and return normalized, dated core-track candidates."""
    lifecycle_engine = import_substrate("data.lifecycle_engine")
    params = seed_to_case_parameters(seed)
    walk_rng = seed.rng("walk")
    date_rng = seed.rng("walk-dates")

    raw = lifecycle_engine.collect_documents_for_case(params, walk_rng)

    out: list[DatedCandidate] = []
    for subtype, rule, stage in raw:
        if subtype in LIEN_OWNED_SUBTYPES or subtype in RECON_OWNED_SUBTYPES:
            continue
        canonical = normalize_subtype(subtype)
        if canonical is None:
            continue
        anchor = timeline.anchor(getattr(rule, "date_anchor", "doi"))
        offset = _offset(date_rng, getattr(rule, "date_offset_days", (0, 30)))
        priority, track = _priority_for(canonical, stage)
        out.append(
            DatedCandidate(
                subtype=canonical,
                doc_date=timeline.clamp(anchor + timedelta(days=offset)),
                track=track,
                priority=priority,
                author_role=author_role_for(canonical),
                stage=stage,
            )
        )
    return out


# ---------------------------------------------------------------------------
# Deterministic guarantees the probabilistic walk cannot make
# ---------------------------------------------------------------------------


def _guaranteed_denial_documents(
    seed: CaseSeed, timeline: CaseTimeline, rng: random.Random
) -> list[DatedCandidate]:
    """A denied claim always denies in writing and is always answered."""
    if seed.lifecycle.claim_response != "denied":
        return []
    denial = timeline.clamp(timeline.claim_filed_date + timedelta(days=rng.randint(30, 90)))
    docs = [
        DatedCandidate(
            subtype="CLAIM_DENIAL_LETTER",
            doc_date=denial,
            priority=5,
            author_role=ROLE_CARRIER,
            stage="claim_response",
        ),
        DatedCandidate(
            subtype="APPLICATION_FOR_ADJUDICATION_ORIGINAL",
            doc_date=timeline.clamp(denial + timedelta(days=rng.randint(7, 60))),
            priority=5,
            author_role=ROLE_APPLICANT_ATTORNEY,
            stage="application_filed",
        ),
        DatedCandidate(
            subtype="DECLARATION_OF_READINESS",
            doc_date=timeline.clamp(denial + timedelta(days=rng.randint(60, 180))),
            priority=12,
            author_role=ROLE_APPLICANT_ATTORNEY,
            stage="application_filed",
        ),
    ]
    return docs


def _guaranteed_ur_documents(
    seed: CaseSeed, timeline: CaseTimeline, rng: random.Random
) -> list[DatedCandidate]:
    """RFA -> UR decision -> (optional) IMR application + determination, in order."""
    ur = seed.lifecycle.ur_dispute
    if not ur.enabled:
        return []
    rfa_date = timeline.clamp(timeline.injury_date + timedelta(days=rng.randint(60, 240)))
    # LC 4610: a non-expedited UR decision is due within five working days.
    ur_date = timeline.clamp(rfa_date + timedelta(days=rng.randint(3, 5)))
    # Priorities sit near the resolution band: a seeded UR dispute is part of
    # the case's story, so a global_cap must eat filler before it eats this.
    docs = [
        DatedCandidate(
            subtype="MEDICAL_TREATMENT_AUTHORIZATION_RFA",
            doc_date=rfa_date,
            priority=14,
            author_role=ROLE_PHYSICIAN,
            stage="ur_dispute",
        ),
        DatedCandidate(
            subtype="UTILIZATION_REVIEW_DECISION_REGULAR",
            doc_date=ur_date,
            priority=12,
            author_role=ROLE_CARRIER,
            stage="ur_dispute",
        ),
    ]
    if ur.decision == "upheld":
        docs.append(
            DatedCandidate(
                subtype="MEDICAL_TREATMENT_DENIAL_UR",
                doc_date=ur_date,
                priority=12,
                author_role=ROLE_CARRIER,
                stage="ur_dispute",
            )
        )
    else:
        docs.append(
            DatedCandidate(
                subtype="MEDICAL_TREATMENT_AUTHORIZATION",
                doc_date=timeline.clamp(ur_date + timedelta(days=rng.randint(1, 10))),
                priority=16,
                author_role=ROLE_CARRIER,
                stage="ur_decision",
            )
        )
    if ur.imr:
        # LC 4610.5: the IMR application is due within 30 days of the UR denial.
        imr_app = timeline.clamp(ur_date + timedelta(days=rng.randint(10, 30)))
        docs.append(
            DatedCandidate(
                subtype="IMR_APPLICATION_FORM",
                doc_date=imr_app,
                priority=12,
                author_role=ROLE_APPLICANT_ATTORNEY,
                stage="imr_appeal",
            )
        )
        docs.append(
            DatedCandidate(
                subtype="IMR_DETERMINATION_FORM",
                doc_date=timeline.clamp(imr_app + timedelta(days=rng.randint(30, 60))),
                priority=12,
                author_role=ROLE_CARRIER,
                stage="imr_appeal",
            )
        )
    return docs


def _guaranteed_death_documents(
    seed: CaseSeed, timeline: CaseTimeline, rng: random.Random
) -> list[DatedCandidate]:
    """Death claims carry their own paper the substrate never emits."""
    if seed.injury.type != "death":
        return []
    return [
        DatedCandidate(
            subtype="DEATH_CERTIFICATE",
            doc_date=timeline.clamp(timeline.injury_date + timedelta(days=rng.randint(3, 21))),
            priority=5,
            author_role=ROLE_PHYSICIAN,
            stage="claim_filed",
        ),
        DatedCandidate(
            subtype="NOTICE_OF_EMPLOYEE_DEATH",
            doc_date=timeline.clamp(timeline.injury_date + timedelta(days=rng.randint(1, 10))),
            priority=5,
            author_role=ROLE_EMPLOYER,
            stage="claim_filed",
        ),
        DatedCandidate(
            subtype="DEPENDENCY_DECLARATION",
            doc_date=timeline.clamp(timeline.injury_date + timedelta(days=rng.randint(30, 150))),
            priority=8,
            author_role=ROLE_APPLICANT_ATTORNEY,
            stage="application_filed",
        ),
        DatedCandidate(
            subtype="APPLICATION_FOR_ADJUDICATION_DEATH",
            doc_date=timeline.application_filed_date,
            priority=5,
            author_role=ROLE_APPLICANT_ATTORNEY,
            stage="application_filed",
        ),
    ]


def _guaranteed_resolution_documents(
    seed: CaseSeed, timeline: CaseTimeline, rng: random.Random
) -> list[DatedCandidate]:
    """The seeded resolution emits its signature documents by construction."""
    resolution = seed.lifecycle.resolution
    if resolution.type == "pending" or timeline.resolution_date is None:
        return []

    resolved_on = timeline.resolution_date
    is_death = seed.injury.type == "death"
    docs: list[DatedCandidate] = []

    # The settlement/trial paperwork is filed shortly before it is approved.
    filed_on = timeline.clamp(resolved_on - timedelta(days=rng.randint(7, 45)))

    if resolution.type == "c_and_r":
        if is_death:
            settlement = "COMPROMISE_AND_RELEASE_DEPENDENCY"
        elif resolution.msa:
            settlement = "COMPROMISE_AND_RELEASE_MSA"
        else:
            settlement = "COMPROMISE_AND_RELEASE_STANDARD"
        docs.append(
            DatedCandidate(
                subtype=settlement,
                doc_date=filed_on,
                priority=0,
                author_role=ROLE_APPLICANT_ATTORNEY,
                stage="resolution_cr",
            )
        )
        docs.append(
            DatedCandidate(
                subtype="ORDER_APPROVING_SETTLEMENT",
                doc_date=resolved_on,
                priority=0,
                author_role=ROLE_COURT,
                stage="resolution_cr",
            )
        )
    elif resolution.type == "stipulations":
        stips = "STIPULATIONS_DEATH_CASE" if is_death else "STIPULATIONS_WITH_REQUEST_FOR_AWARD"
        docs.append(
            DatedCandidate(
                subtype=stips,
                doc_date=filed_on,
                priority=0,
                author_role=ROLE_APPLICANT_ATTORNEY,
                stage="resolution_stipulations",
            )
        )
        docs.append(
            DatedCandidate(
                subtype="ORDER_APPROVING_SETTLEMENT",
                doc_date=resolved_on,
                priority=0,
                author_role=ROLE_COURT,
                stage="resolution_stipulations",
            )
        )
    else:  # findings_award / take_nothing — both end in a tried decision
        docs.append(
            DatedCandidate(
                subtype="MINUTES_OF_HEARING",
                doc_date=filed_on,
                priority=0,
                author_role=ROLE_COURT,
                stage="resolution_trial",
            )
        )
        docs.append(
            DatedCandidate(
                subtype="FINDINGS_AND_AWARD",
                doc_date=resolved_on,
                priority=0,
                author_role=ROLE_COURT,
                stage="resolution_trial",
            )
        )
        docs.append(
            DatedCandidate(
                subtype="OPINION_ON_DECISION",
                doc_date=resolved_on,
                priority=0,
                author_role=ROLE_COURT,
                stage="resolution_trial",
            )
        )
    return docs


def _guaranteed_eval_documents(
    seed: CaseSeed, timeline: CaseTimeline, rng: random.Random
) -> list[DatedCandidate]:
    """The seeded evaluation type always produces its panel paperwork and report."""
    eval_type = seed.lifecycle.eval_type
    if eval_type == "none":
        return []
    panel_date = timeline.clamp(timeline.injury_date + timedelta(days=rng.randint(180, 365)))
    report_date = timeline.clamp(panel_date + timedelta(days=rng.randint(60, 180)))
    if eval_type == "qme":
        return [
            DatedCandidate(
                subtype="QME_PANEL_REQUEST_FORM_105",
                doc_date=panel_date,
                priority=18,
                author_role=ROLE_APPLICANT_ATTORNEY,
                stage="qme_evaluation",
            ),
            DatedCandidate(
                subtype="ORDER_APPOINTING_QME_PANEL",
                doc_date=timeline.clamp(panel_date + timedelta(days=rng.randint(10, 30))),
                priority=18,
                author_role=ROLE_COURT,
                stage="qme_evaluation",
            ),
            DatedCandidate(
                subtype="QME_REPORT_INITIAL",
                doc_date=report_date,
                priority=15,
                author_role=ROLE_PHYSICIAN,
                stage="qme_evaluation",
            ),
        ]
    return [
        DatedCandidate(
            subtype="AME_REPORT",
            doc_date=report_date,
            priority=15,
            author_role=ROLE_PHYSICIAN,
            stage="ame_evaluation",
        )
    ]


def _enforce_singletons(candidates: list[DatedCandidate]) -> list[DatedCandidate]:
    """Trim :data:`SINGLETON_SUBTYPES` to one copy — the most essential one.

    Lowest ``priority`` wins (deterministic guarantees are ranked more
    essential than probabilistic walk hits), earliest date breaks ties.
    """
    best: dict[str, DatedCandidate] = {}
    for candidate in candidates:
        if candidate.subtype not in SINGLETON_SUBTYPES:
            continue
        incumbent = best.get(candidate.subtype)
        if incumbent is None or (candidate.priority, candidate.doc_date) < (
            incumbent.priority,
            incumbent.doc_date,
        ):
            best[candidate.subtype] = candidate

    out: list[DatedCandidate] = []
    for candidate in candidates:
        if candidate.subtype not in SINGLETON_SUBTYPES or best[candidate.subtype] is candidate:
            out.append(candidate)
    return out


def build_core_candidates(seed: CaseSeed, timeline: CaseTimeline) -> list[DatedCandidate]:
    """Full core track: the substrate walk plus the seed's deterministic guarantees.

    Guarantees are appended after the walk and de-duplicated by
    ``(subtype, date)`` so a probabilistic hit and a guarantee do not double up.
    """
    rng = seed.rng("guarantees")
    candidates = walk_core_track(seed, timeline)
    candidates.extend(_guaranteed_denial_documents(seed, timeline, rng))
    candidates.extend(_guaranteed_ur_documents(seed, timeline, rng))
    candidates.extend(_guaranteed_death_documents(seed, timeline, rng))
    candidates.extend(_guaranteed_eval_documents(seed, timeline, rng))
    candidates.extend(_guaranteed_resolution_documents(seed, timeline, rng))

    seen: set[tuple[str, date]] = set()
    unique: list[DatedCandidate] = []
    for candidate in candidates:
        key = (candidate.subtype, candidate.doc_date)
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    unique = _enforce_singletons(unique)
    unique.sort(key=lambda item: (item.doc_date, item.subtype))
    log.debug(
        "lifecycle.core_built",
        case_id=seed.case_id,
        candidates=len(unique),
        stage=seed.lifecycle.target_stage,
    )
    return unique


def to_document_candidates(
    candidates: Sequence[DatedCandidate],
) -> list[DocumentCandidate]:
    """Adapt dated candidates for :func:`resolve_document_controls`."""
    taxonomy = effective_taxonomy()
    return [item.to_candidate(taxonomy.parent_of(item.subtype)) for item in candidates]


__all__ = [
    "DROPPED_SUBSTRATE_ONLY",
    "LIEN_OWNED_SUBTYPES",
    "RECON_OWNED_SUBTYPES",
    "RESOLUTION_MAP",
    "ROLE_APPLICANT_ATTORNEY",
    "ROLE_CARRIER",
    "ROLE_COURT",
    "ROLE_DEFENSE_ATTORNEY",
    "ROLE_EMPLOYER",
    "ROLE_LIEN_CLAIMANT",
    "ROLE_PHYSICIAN",
    "SUBSTRATE_TO_CANONICAL",
    "TARGET_STAGE_MAP",
    "UR_DECISION_MAP",
    "CaseTimeline",
    "DatedCandidate",
    "author_role_for",
    "build_core_candidates",
    "build_timeline",
    "normalize_subtype",
    "seed_to_case_parameters",
    "to_document_candidates",
    "walk_core_track",
]
