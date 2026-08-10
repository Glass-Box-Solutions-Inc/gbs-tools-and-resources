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
from dataclasses import dataclass, replace
from datetime import date, timedelta
from itertools import pairwise

import structlog

from wc_caseload_engine.case_context import (
    CaseCast,
    align_employer_wage,
    build_case_cast,
)
from wc_caseload_engine.case_facts import (
    CaseFacts,
    derive_case_facts,
    derive_packet_pages,
    resolve_surgery_status,
    resolve_treatment_status,
)
from wc_caseload_engine.doc_controls import (
    TRACK_CORE,
    ControlResolution,
    resolve_document_controls,
    verify_forced_subtypes,
    verify_global_cap,
    verify_type_floors,
)
from wc_caseload_engine.doctrine import (
    content_flags_for,
    unsupported_hooks,
    verify_unsupported_hooks,
)
from wc_caseload_engine.lien_machine import LienTrack, build_lien_tracks, lien_candidates
from wc_caseload_engine.lifecycle_bridge import (
    SUBSTRATE_TO_CANONICAL,
    CaseTimeline,
    DatedCandidate,
    author_role_for,
    build_core_candidates,
    build_timeline,
    fit_dates,
    to_document_candidates,
)
from wc_caseload_engine.medical_history import (
    MedicalHistory,
    derive_medical_history,
    grounding_warnings,
)
from wc_caseload_engine.money import MoneyFacts, derive_money_facts
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
    medical_history: MedicalHistory | None = None
    """The world-truth ledger, when the seed asked for one. ``None`` when it did not.

    A third sibling beside ``case_facts`` and ``money_facts``, on the ``money``
    pattern and for the same reason: derived only for a seed carrying
    ``scenario.medical_history``, so the absence is a value every consumer can
    short-circuit on rather than a dozen empty collections nobody can tell from data.

    **Carried, never published.** Nothing writes it to ``case_facts.yaml``, to the
    manifest's ``caseFacts`` block or to the truth manifest, and that is deliberate:
    world truth is what an assertion is graded *against*, so a document able to cite
    it would collapse the two-level design this ledger opens. Same discipline
    ``case_facts`` already applies to ``wpi`` and ``pd``. M3 gives the conditions a
    document surface and M4 gives the ledger a scorer-only channel.
    """

    money_facts: MoneyFacts | None = None
    """The money spine, when the seed asked for one. ``None`` when it did not.

    Separate from ``case_facts`` rather than folded into it, and the ``None`` is
    the reason. The clinical ledger is derived for *every* case; the money spine
    is derived only for a seed carrying ``scenario.wages``, and keeping the two
    apart is what lets "this case has no money layer" be a value the planner,
    the renderer and the manifest can each short-circuit on. Folded in, the
    absence would have to be spelled as a dozen ``None`` fields on a model that
    is always present, and every consumer would have to agree on which of them
    means "no money".
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

#: The applicant attorney's letters to the client — the correspondence whose
#: *rhythm* ``scenario.attorney.cadence`` describes. ``CLIENT_INTAKE_
#: CORRESPONDENCE`` is deliberately absent: the retainer letter is anchored to
#: the start of the representation, not to the reporting habit that follows it.
ATTORNEY_CADENCE_SUBTYPES: frozenset[str] = frozenset(
    {
        "CLIENT_CORRESPONDENCE_INFORMATIONAL",
        "CLIENT_CORRESPONDENCE_REQUEST",
        "CLIENT_STATUS_LETTERS",
        "STATUS_UPDATE_INFORMATIONAL",
    }
)

#: What counsel sends when a benefit ran late. One per late benefit event, which
#: is what makes correspondence density a *consequence* of the adjuster persona
#: rather than a second, independently drawn knob that could contradict it.
DELAY_CHAIN_SUBTYPE = "DEMAND_LETTER_FORMAL"


def _penalty_candidates(facts: CaseFacts, timeline: CaseTimeline) -> list[DatedCandidate]:
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

    Returned as an ordinary candidate rather than appended to the dated list,
    so it passes through perspective suppression and ``resolve_document_controls``
    like everything else. Appending it afterwards made it invisible to
    ``documents.exclude`` and ``include_only`` — the controls silently did not
    apply to the one subtype this phase added.

    Dated after **every** late event it punishes, not merely the first. A
    petition filed between two late notices would be pleading a delay that had
    not happened yet at the time of filing, and the horizon clamp must never
    pull it back below that floor — better a petition on the last day of the
    file than one that predates its own grievance.
    """
    if not facts.late_benefit_events:
        return []

    latest = max(event.actual_date for event in facts.late_benefit_events)
    filed = getattr(timeline, "application_filed_date", None)
    when = max(latest, filed) if filed is not None else latest
    when = when + timedelta(days=30)

    horizon = getattr(timeline, "resolution_date", None) or filed
    if horizon is not None and when > horizon:
        # ISC-136. Two invariants collide here and only one can hold:
        #
        #   A. the petition post-dates every late event it punishes
        #   B. the petition does not outlast the file's horizon
        #
        # **A wins, explicitly.** A pleading dated before the delay it complains
        # about is incoherent on its face — a reader opens the file and finds a
        # petition alleging a delay that had not happened yet. A petition dated
        # a little past the horizon is not incoherent at all: the horizon is
        # where the *case-in-chief* resolves, and penalty petitions are
        # collateral proceedings that routinely outlive it.
        #
        # So this is not a clamp, despite its shape, and calling it one was the
        # confusion ISC-136 was raised to settle. It is a clamp *subject to a
        # floor*, and where the two disagree the floor is the one that holds.
        #
        # Reachable, narrowly. ``_derive_late_benefit_events`` drops any event
        # past the horizon, so ``latest <= horizon`` always — the conflict needs
        # ``latest == horizon`` exactly, and then the petition lands one day
        # past it. Rare, not impossible, and asserted rather than assumed.
        when = max(horizon, latest + timedelta(days=1))

    return [
        DatedCandidate(
            subtype="PETITION_FOR_PENALTIES",
            doc_date=when,
            track=TRACK_CORE,
            author_role="applicant_attorney",
        )
    ]


#: The wage statement a money-bearing case must contain, and its author.
#:
#: One subtype, not the whole ``WAGE_STATEMENTS_*`` family. The floor exists so
#: that a seed stating wage facts cannot produce a folder with nowhere to read
#: them; emitting all three flavours would be the engine deciding how an employer
#: files its payroll, which is a document-control question and belongs to the
#: seed.
MONEY_WAGE_SUBTYPE = "WAGE_STATEMENTS_PRE_INJURY"

#: The payment records that carry the benefit ledger, each gated on having
#: something to report. A TD record in a file that paid no temporary disability
#: would be a blank form, which is worse than an absent one.
MONEY_TD_SUBTYPE = "TD_PAYMENT_RECORD_ONGOING"
MONEY_PD_SUBTYPE = "PD_PAYMENT_RECORD_ADVANCE"

#: The document that effects an approval, and therefore the one that can print
#: its date. The Board issues it *on* the approval date; the release the parties
#: signed is dated weeks earlier and cannot.
MONEY_APPROVAL_SUBTYPE = "ORDER_APPROVING_SETTLEMENT"

#: The document dated after the settlement draft clears, and therefore the only
#: one that can report that it did — the order is issued before funding, so it
#: cannot carry the funding date either.
MONEY_FUNDING_SUBTYPE = "BENEFIT_PAYMENT_LEDGER"

#: The instruments a settlement is approved *from*. The order recites that this
#: document was "filed herein and considered", so it cannot precede it.
MONEY_INSTRUMENT_SUBTYPES = frozenset(
    {
        "COMPROMISE_AND_RELEASE",
        "COMPROMISE_AND_RELEASE_STANDARD",
        "COMPROMISE_AND_RELEASE_PD_ONLY",
        "COMPROMISE_AND_RELEASE_MSA",
        "COMPROMISE_AND_RELEASE_DEPENDENCY",
        "COMPROMISE_AND_RELEASE_THIRD_PARTY",
        "STIPULATIONS_WITH_REQUEST_FOR_AWARD",
        "STIPULATIONS_WITH_REQUEST_FOR_AWARD_FULL",
        "STIPULATIONS_WITH_REQUEST_FOR_AWARD_PARTIAL",
        "STIPS_WITH_REQUEST_FOR_AWARD_PACKAGE",
    }
)

#: How long before its approval the instrument is filed, when an authored
#: approval date would otherwise leave it stranded after its own order. A
#: working assumption about filing lag, stated rather than dressed up as a rule.
MONEY_INSTRUMENT_LEAD_DAYS = 21

MONEY_FLOOR_SUBTYPES: tuple[str, ...] = (
    MONEY_WAGE_SUBTYPE,
    MONEY_TD_SUBTYPE,
    MONEY_PD_SUBTYPE,
)


def _money_control_warnings(seed: CaseSeed, money_facts: MoneyFacts | None) -> list[str]:
    """Report a money control the case's own runway could not honour.

    The seed schema refuses a control that is impossible on its face — lateness
    with nothing paid, a gap in a run too short to hold one. It cannot see the
    *timeline*, so it cannot see truncation: `td_weeks: 520` on a file whose
    runway holds twelve is a request silently reduced by a factor of forty.

    A warning rather than an error, and the distinction is the one this package
    already draws elsewhere: an impossible seed is rejected, a seed whose story
    outruns its calendar is honoured as far as the calendar goes and the
    shortfall is reported. Same shape as the control-suppression warnings — the
    operator is told what they asked for and what they got.
    """
    if money_facts is None:
        return []

    out: list[str] = []
    ledger = money_facts.benefits
    scenario = seed.scenario.benefits
    if scenario is None:
        # No benefits block to have been truncated, but a settlement can still
        # have outrun the calendar — the two are separate seed blocks and gating
        # one behind the other silently dropped the settlement report.
        return _settlement_warnings(seed, money_facts)
    if scenario.td_weeks:
        realized = sum(int(period.weeks) for period in ledger.td_periods)
        if realized < scenario.td_weeks:
            out.append(
                f"scenario.benefits.td_weeks asked for {scenario.td_weeks} week(s) of "
                f"temporary disability; the case's runway holds {realized}. Move the "
                "injury earlier, or seed a lifecycle that reaches further, to pay the "
                "whole run."
            )
    if scenario.pd_advances and len(ledger.pd_advances) < scenario.pd_advances:
        out.append(
            f"scenario.benefits.pd_advances asked for {scenario.pd_advances} advance(s); "
            f"the case's runway holds {len(ledger.pd_advances)}. Move the injury earlier, "
            "or lower pd_advances."
        )
    if scenario.td_gap_days and not ledger.gaps:
        out.append(
            f"scenario.benefits.td_gap_days asked for a {scenario.td_gap_days}-day "
            "interruption; the temporary-disability run this case reached is too short to "
            "hold one. Raise td_weeks, or move the injury earlier."
        )
    if scenario.late_payments:
        realized = ledger.late_payment_count
        if realized < scenario.late_payments:
            # The seed schema refuses lateness with nothing paid at all; it
            # cannot see that eight weeks is two four-week blocks, so three late
            # payments become two and the ledger publishes the smaller number
            # without comment.
            out.append(
                f"scenario.benefits.late_payments asked for {scenario.late_payments} late "
                f"payment(s); this case holds {realized} payable event(s) to be late. "
                "Raise td_weeks or pd_advances, or lower late_payments."
            )
    return out + _settlement_warnings(seed, money_facts)


def _settlement_warnings(seed: CaseSeed, money_facts: MoneyFacts) -> list[str]:
    """Report a settlement whose stated dates the file's own calendar could not hold."""
    settlement = money_facts.settlement
    stated_settlement = seed.scenario.settlement
    warnings: list[str] = []
    if (
        settlement is not None
        and stated_settlement is not None
        and stated_settlement.approval_date is not None
        and settlement.approval_date is not None
        and settlement.approval_date != stated_settlement.approval_date
    ):
        # Moved, and said so. A stated control that is quietly adjusted is the
        # defect ISC-184 exists to prevent, and an approval before the file's own
        # Application is a story the calendar cannot hold rather than an
        # impossible seed — so it is a warning, like every other runway
        # truncation in this module, not a refusal.
        warnings.append(
            f"scenario.settlement.approval_date of "
            f"{stated_settlement.approval_date.isoformat()} falls before this case "
            f"could have reached the Board; approved "
            f"{settlement.approval_date.isoformat()} instead, which is the first date "
            "leaving the settlement instrument somewhere to stand after the "
            "Application for Adjudication"
        )
    if (
        settlement is None
        or settlement.approval_date is None
        or settlement.funding_date is not None
    ):
        return warnings
    stated = seed.scenario.settlement
    stated_lag = stated.funding_days if stated is not None else None
    stated_date = stated.funding_date if stated is not None else None
    # Name the control that actually produced this state. The warning knew only
    # about `funding_days` and blamed the adjuster for everything else, so a
    # *stated* `funding_date` carried past the horizon by a forced approval was
    # reported as an adjuster's lag the seed never mentioned — a warning that
    # names the wrong knob is not followable, which is the whole point of one.
    if stated_date is not None:
        # Name the *effective* date, not the authored one. Review found the
        # warning reporting "funding_date of 2025-12-31 carries funding past the
        # horizon" when 2025-12-31 is comfortably inside it — the 133-day
        # approval shift is what carried it out, so the authored date read as
        # the culprit and the advice to "move the approval earlier" was exactly
        # backwards, since an earlier approval means a larger shift.
        shift = (settlement.approval_date - stated.approval_date).days if (
            stated.approval_date is not None
        ) else 0
        if shift:
            detail = (
                f"scenario.settlement.funding_date of {stated_date.isoformat()}, "
                f"carried {shift} day(s) forward with the approval this file could "
                f"first support, "
            )
        else:
            detail = f"scenario.settlement.funding_date of {stated_date.isoformat()} "
    elif stated_lag is not None:
        detail = f"scenario.settlement.funding_days of {stated_lag} "
    else:
        detail = "the funding lag for this adjuster "
    return [
        *warnings,
        f"the settlement was approved {settlement.approval_date} but {detail}"
        "carries funding past the date this engine treats as today, so the case is "
        "published as approved and not yet funded. Bring the funding date or lag "
        "earlier, or move the approval *later* so it needs no forward shift, if the "
        "file should show the money arriving."
    ]


def _money_candidates(
    seed: CaseSeed,
    money_facts: MoneyFacts | None,
    timeline: CaseTimeline,
    existing: list[DatedCandidate],
) -> list[DatedCandidate]:
    """A floor: the documents a money-bearing case must be able to be read from.

    The ISC-92.1 pattern — a stated scenario fact guarantees the document that
    carries it — applied to money. A seed that states an earnings history and
    gets back a folder with no wage statement in it has a ledger nothing can
    check, which is precisely the "asserted, not derived" failure this layer
    exists to remove.

    A **floor**, not an emission: a subtype the lifecycle walk already proposed
    is never doubled, so this cannot give a case two of a document it was going
    to have one of. And returned as ordinary candidates, so ``documents.exclude``
    and ``include_only`` still bind — the PR #25 M1 lesson (anything appended
    after ``resolve_document_controls`` is invisible to the controls) applied at
    design time rather than after a review found it.

    Dated as three *independent* documents, each clamped, rather than fitted as a
    chain. They have no causal relationship with one another — an employer's
    payroll certificate does not cause a carrier's payment printout — which is
    the one shape ``CaseTimeline.clamp`` is sound for.

    **An already-proposed document is re-dated, not skipped**, and this is the
    correction that matters most. The first cut returned early when the walk had
    already proposed the subtype, which quietly abandoned the date this function
    had just decided the document needed. The walk dates a payment record from
    the lifecycle stage; the ledger it now carries runs to whenever the last
    payment cleared. Measured across 132 planned records on 30 seeds and three
    stages, **106 were dated before the last payment printed on them** — one by
    123 days. A carrier's printout dated four months before a payment it lists
    is not a snapshot, it is a document contradicting itself, and it is the money
    layer that put the ledger on the page to contradict.

    Re-dating moves the date **forward only**, and only for the money floor's own
    subtypes. Forward, because the constraint is one-sided: these documents
    report events, so they may be issued any time after the last one and never
    before it. And it is sound to move them precisely because they are the
    parallel, causally-unrelated set described above — nothing is sequenced
    behind them to be dragged along.
    """
    if money_facts is None:
        return []

    out: list[DatedCandidate] = []
    already: dict[str, list[int]] = defaultdict(list)
    for index, candidate in enumerate(existing):
        already[candidate.subtype].append(index)

    def add(subtype: str, when: date, *, pin: bool = False) -> None:
        required = timeline.clamp(when)
        indices = already.get(subtype)
        if indices:
            if pin:
                # An approving order does not report an approval, it *is* the
                # approval, so its date is the event's date — not merely on or
                # after it. Forward-only re-dating left an authored approval of
                # 2022-01-05 evidenced by an order dated 2023-12-27, 721 days
                # later, and the on-or-after rule certified it. The one-sided
                # constraint is right for a document that *reports* events and
                # wrong for one that constitutes an event.
                for index in indices:
                    prior = existing[index]
                    if prior.doc_date != required:
                        existing[index] = replace(prior, doc_date=required)
                return
            # *Every* candidate for the subtype, not the first one found. The
            # walk may propose several, and the pool below picks the earliest
            # ones by date — so moving one and leaving its siblings behind
            # leaves the earliest still standing, which is exactly what the
            # first attempt at this fix did and what the sweep caught.
            for index in indices:
                prior = existing[index]
                if prior.doc_date < required:
                    # ``DatedCandidate`` is frozen, so the move is a
                    # replacement. Everything else the walk decided about this
                    # document — track, priority, author role, stage — is
                    # carried across untouched; only the date the ledger
                    # contradicts is corrected.
                    existing[index] = replace(prior, doc_date=required)
            return
        out.append(
            DatedCandidate(
                subtype=subtype,
                doc_date=required,
                track=TRACK_CORE,
                author_role=author_role_for(subtype),
            )
        )

    # The employer certifies earnings once the claim reaches it. Three weeks
    # after the claim form is a working assumption, not a statutory window, and
    # it is stated here rather than dressed up as one.
    add(MONEY_WAGE_SUBTYPE, timeline.claim_filed_date + timedelta(days=21))

    benefits = money_facts.benefits
    if benefits.td_periods:
        last_td = max(
            (period.date_paid or period.end for period in benefits.td_periods),
        )
        add(MONEY_TD_SUBTYPE, last_td + timedelta(days=7))
    if benefits.pd_advances:
        last_pd = max(advance.date_paid for advance in benefits.pd_advances)
        add(MONEY_PD_SUBTYPE, last_pd + timedelta(days=7))

    # A settlement's two published dates each need a document whose own date is
    # on or after the event, which is the ISC-175 rule stated generally rather
    # than for payment records. The release cannot carry either: the parties
    # sign it before the Board approves, and the Board approves before the draft
    # clears. So the order carries the approval and a ledger carries the
    # funding, and the floor guarantees both rather than hoping the walk did.
    settlement = money_facts.settlement
    if settlement is not None:
        if settlement.approval_date is not None:
            # The chain is: instrument <= approval == order <= funding <= ledger.
            # Pinning the order to an *authored* approval was found to break the
            # first link — an approval of 2022-01-05 put the order 677 days
            # before the stipulations it recites as "filed herein". The order is
            # pinned because it constitutes the approval; the instrument is
            # pulled back only when it would otherwise post-date its own order,
            # and never past the claim it settles.
            approval = timeline.clamp(settlement.approval_date)
            floor = timeline.claim_filed_date
            filed = max(floor, approval - timedelta(days=MONEY_INSTRUMENT_LEAD_DAYS))
            for subtype in MONEY_INSTRUMENT_SUBTYPES:
                for index in already.get(subtype, ()):
                    prior = existing[index]
                    if prior.doc_date > approval:
                        existing[index] = replace(prior, doc_date=min(filed, approval))
            add(MONEY_APPROVAL_SUBTYPE, settlement.approval_date, pin=True)
        if settlement.funding_date is not None:
            add(MONEY_FUNDING_SUBTYPE, settlement.funding_date + timedelta(days=7))

    return out


def _delay_chain_candidates(facts: CaseFacts, timeline: CaseTimeline) -> list[DatedCandidate]:
    """ISC-119. One demand letter for each benefit the carrier paid late.

    Correspondence density is the *visible* consequence of the adjuster persona.
    An attentive adjuster runs no benefit past its statutory window, so nothing
    chases them; a negligent one accumulates late events, and each one draws a
    letter. Density therefore scales through the ledger rather than through a
    second knob multiplying counts — which matters because
    ``caseFacts.adjuster.lateBenefitEvents`` is published: a reader holding the
    manifest can count the demand letters in the folder and check the two agree.
    A free-standing density multiplier would have nothing to check it against,
    and the persona itself is deliberately unpublished (it is an input, and no
    document reflects it).

    Emitted as candidates for the same reason the penalty petition is: anything
    appended after ``resolve_document_controls`` is invisible to
    ``documents.exclude``, ``include_only`` and count overrides. That defect
    shipped once already.

    Dated a week after the delay, staggered so two late benefits in one week do
    not produce two letters on one day. Where the offset would push a letter
    past the horizon the ISC-136 rule applies unchanged: the letter post-dates
    the delay it chases, because correspondence complaining about something that
    has not happened yet is incoherent in a way that a letter written near the
    end of the file is not.
    """
    if not facts.late_benefit_events:
        return []

    horizon = getattr(timeline, "resolution_date", None) or timeline.horizon
    out: list[DatedCandidate] = []
    ordered = sorted(facts.late_benefit_events, key=lambda event: event.actual_date)
    for offset, event in enumerate(ordered):
        when = event.actual_date + timedelta(days=7 + offset)
        if horizon is not None and when > horizon:
            when = max(horizon, event.actual_date + timedelta(days=1))
        out.append(
            DatedCandidate(
                subtype=DELAY_CHAIN_SUBTYPE,
                doc_date=when,
                track=TRACK_CORE,
                author_role="applicant_attorney",
            )
        )
    return out


def _penalty_control_warnings(
    facts: CaseFacts,
    dated: list[tuple[date, str, str, str]],
    controls: DocumentControls,
) -> tuple[str, ...]:
    """Note when a petition the ledger earned is absent from the final plan.

    Keyed off the **outcome**, not off which control name matched. The first
    version asked "did ``exclude`` or ``include_only`` name this subtype?", and
    so stayed silent for a zero-count override, a ``global_cap`` that ate the
    petition, a parent-type exclude, and perspective suppression — four routes to
    the same missing document, three of them undetected. Enumerating suppression
    mechanisms is a losing game; the next one added would have been silent too.

    Asking instead "the ledger earned this and the plan does not contain it" is
    one question with one answer, and it cannot go stale when a new control
    lands.

    The precedence itself is unchanged and follows ISC-29: the control wins, the
    seed is the contract. It wins *loudly*, because a file whose ledger records
    four late benefit notices and holds no penalty petition is a coherent
    artifact only if somebody meant it. This is the mirror of the
    emit-with-warning cases — there the seed asked for something the substrate
    excludes and got it with a note; here the seed refused something the facts
    support, and gets that with a note too.
    """
    if not facts.late_benefit_events:
        return ()
    if any(subtype == "PETITION_FOR_PENALTIES" for _date, subtype, _track, _role in dated):
        return ()

    # Name the likely route when one is identifiable — an author who wrote the
    # control wants to know which line to change — but warn either way.
    if "PETITION_FOR_PENALTIES" in set(controls.exclude):
        because = "documents.exclude names it"
    elif any(
        override.subtype == "PETITION_FOR_PENALTIES" and override.count == 0
        for override in controls.overrides
    ):
        because = "a documents.overrides entry sets its count to 0"
    elif controls.include_only:
        because = "documents.include_only does not name it"
    elif controls.global_cap is not None:
        because = f"documents.global_cap of {controls.global_cap} excluded it"
    else:
        because = "a document control or the file's perspective excluded it"

    return (
        f"scenario: the ledger records {len(facts.late_benefit_events)} late benefit "
        f"event(s), which earns a PETITION_FOR_PENALTIES, but the plan holds none — "
        f"{because}. The control wins; drop it if the delay should be pleaded.",
    )


#: The gap pattern ``sporadic`` walks, in days. Fixed rather than drawn: the
#: cadence is a *described* habit, and a draw could hand a "sporadic" file a
#: tidy monthly rhythm — the coincidence-pass that has cost this build twice.
#: The 120 is what makes the three-month hole a certainty rather than a hope.
_SPORADIC_GAPS: tuple[int, ...] = (24, 120, 41, 96, 33)

#: Below this, a file has no rhythm to impose: one client letter cannot be
#: early or late relative to anything, so the cadence leaves it alone.
CADENCE_MIN_LETTERS = 2

#: How long after an event counsel writes about it — the time to read a report
#: and dictate a letter.
EVENT_DRIVEN_LAG_DAYS = 5

#: Added per extra pass through the anchor list, when a file holds more letters
#: than events worth writing about.
EVENT_DRIVEN_LAP_DAYS = 45

def event_driven_max_lag_days(letters: int, anchors: int) -> int:
    """Widest gap an ``event_driven`` letter may sit behind a preceding event.

    A *function of the case*, not a constant, and getting that wrong is the
    second half of F2. The first attempt at this repair asserted a fixed ceiling
    of ``LAG + LAP`` — one lap — because a 38-seed sample topped out at 50 days.
    A twelve-seed sample at ``discovery`` stage, which carries more letters per
    anchor, immediately produced 100. The sample had not been wide enough to
    show the shape, and a constant fitted to it would have been a magic number
    with better manners.

    The real bound falls out of the cycle: with more letters than anchors the
    walk laps the anchor list, and the last lap is
    ``ceil(letters / anchors) - 1``.

    F2 in one line: the CHANGELOG claimed "1-5 days" while the guard allowed
    0-60. Measured over 38 cases / 218 letters, 179 land at exactly
    :data:`EVENT_DRIVEN_LAG_DAYS`, the fit pulls a few as close as 0, and the
    lap tail runs as far as the case's own shape allows. "1-5" was false at both
    ends; 60 was arbitrary.
    """
    if anchors <= 0:
        return 0
    laps = max(0, -(-letters // anchors) - 1)  # ceil division, zero-based
    return EVENT_DRIVEN_LAG_DAYS + EVENT_DRIVEN_LAP_DAYS * laps

#: What counts as an "event" worth writing to the client about. Medical reports
#: and the case's own milestones — the documents that change what counsel can
#: tell the client. Correspondence is excluded on purpose: letters answering
#: letters is a rhythm of its own, not an event-driven one.
CADENCE_ANCHOR_SUBTYPES: frozenset[str] = frozenset(
    {
        "TREATING_PHYSICIAN_REPORT",
        "TREATING_PHYSICIAN_REPORT_PR2",
        "TREATING_PHYSICIAN_REPORT_PR4",
        "TREATING_PHYSICIAN_REPORT_FINAL",
        "QME_REPORT_INITIAL",
        "QME_REPORT_SUPPLEMENTAL",
        "QME_COMPREHENSIVE_REPORT",
        "AME_REPORT",
        "AME_COMPREHENSIVE_REPORT",
        "MEDICAL_LEGAL_QME_AME_IME",
        "DISCHARGE_SUMMARY",
        "OPERATIVE_HOSPITAL_RECORDS",
        "APPLICATION_FOR_ADJUDICATION",
        "COMPROMISE_AND_RELEASE",
        "STIPULATIONS_WITH_REQUEST_FOR_AWARD",
        "FINDINGS_AND_AWARD",
        "ORDER_APPROVING_SETTLEMENT",
    }
)


def _cadence_dates(
    cadence: str, count: int, first: date, anchors: Sequence[date]
) -> list[date]:
    """The dates counsel's letters land on under one cadence.

    Every branch returns an *intended* chain, unclamped. The caller fits it —
    date-spine rule 2 — because these letters cause each other in the sense
    that matters here: they are one rhythm, and clamping them date by date
    stacks the tail on the horizon and destroys the very gaps the cadence is
    supposed to show.
    """
    if cadence == "every_30_days":
        return [first + timedelta(days=30 * step) for step in range(count)]

    if cadence == "sporadic":
        dates = [first]
        for step in range(1, count):
            gap = _SPORADIC_GAPS[(step - 1) % len(_SPORADIC_GAPS)]
            dates.append(dates[-1] + timedelta(days=gap))
        return dates

    # event_driven: counsel writes when something happened, and is silent
    # otherwise. Each letter follows its anchor by a few days — the time it
    # takes to read a report and dictate a letter about it.
    #
    # The anchors are the *other documents in this file* (see
    # ``CADENCE_ANCHOR_SUBTYPES``), not the timeline's four milestones. That
    # started as the obvious choice and was wrong: after filtering to milestones
    # at or after the first letter, most cases had one anchor left, the cycle
    # below degenerated into a fixed lap offset, and "event driven" rendered as
    # a tidy 90-day metronome. It passed the three-cadences-differ test — for
    # entirely the wrong reason.
    if not anchors:
        # No events to follow. Say so by spacing them loosely rather than
        # inventing a rhythm that would be indistinguishable from a cadence the
        # file did not ask for.
        return [first + timedelta(days=45 * step) for step in range(count)]
    dates = []
    for step in range(count):
        anchor = anchors[step % len(anchors)]
        lap = step // len(anchors)
        dates.append(
            anchor + timedelta(days=EVENT_DRIVEN_LAG_DAYS + EVENT_DRIVEN_LAP_DAYS * lap)
        )
    return sorted(dates)


def _apply_attorney_cadence(
    facts: CaseFacts,
    timeline: CaseTimeline,
    dated: list[tuple[date, str, str, str]],
) -> tuple[list[tuple[date, str, str, str]], tuple[str, ...]]:
    """ISC-123/124. Re-date counsel's client letters onto the resolved cadence.

    Reads ``facts.attorney_cadence`` — the *resolved* value — not
    ``seed.scenario.attorney.cadence``. A seed that says nothing still resolves
    a cadence, and a file whose ledger claims ``every_30_days`` while its
    letters are scattered at random is exactly the incoherence this phase
    exists to remove. Reading the declared value instead is the defect class
    that has appeared in every phase of this ticket so far.

    Moves dates only. It adds no document and drops none, so it needs no pass
    through ``resolve_document_controls`` and cannot change what a seed's
    controls decided.
    """
    letters = sorted(
        (entry for entry in dated if entry[1] in ATTORNEY_CADENCE_SUBTYPES),
        key=lambda entry: entry[0],
    )
    if len(letters) < CADENCE_MIN_LETTERS:
        # One letter has no rhythm, and zero letters have nothing to re-date.
        return dated, ()

    cadence = facts.attorney_cadence
    first = letters[0][0]
    # The events counsel would actually write *about*, taken from the file
    # itself so a reader can hold the letter beside the report that prompted it.
    anchors = sorted(
        {entry[0] for entry in dated if entry[1] in CADENCE_ANCHOR_SUBTYPES}
    )
    intended = _cadence_dates(cadence, len(letters), first, anchors)

    ceiling = timeline.horizon
    floor = min(first, min(intended))
    fitted = fit_dates(intended, floor=floor, ceiling=ceiling, label=f"cadence:{cadence}")

    moved = {id(entry): when for entry, when in zip(letters, fitted, strict=True)}
    shaped = [
        (moved[id(entry)], entry[1], entry[2], entry[3]) if id(entry) in moved else entry
        for entry in dated
    ]

    warnings: list[str] = []
    if cadence == "sporadic":
        gaps = [(b - a).days for a, b in pairwise(fitted)]
        if gaps and max(gaps) < 90:
            # Honest reporting rather than a silent near-miss: the window was
            # too short to hold the hole the cadence describes.
            warnings.append(
                "scenario.attorney.cadence is 'sporadic' but the file's runway "
                f"compressed the correspondence to a largest gap of {max(gaps)} "
                "days; lengthen the case or reduce the letter count for a "
                "visible break in the record"
            )
    return shaped, tuple(warnings)


#: The records-packet subtypes ``scenario.discovery.subpoena_sets`` counts.
#: Kept beside the planner rather than imported from ``manifests`` to avoid a
#: cycle; ``test_the_discovery_tables_agree`` asserts the two stay identical.
DISCOVERY_PACKET_SUBTYPES: frozenset[str] = frozenset(
    {
        "SUBPOENAED_RECORDS",
        "SUBPOENAED_RECORDS_MEDICAL",
        "SUBPOENAED_RECORDS_EMPLOYMENT",
        "SUBPOENAED_RECORDS_OTHER",
    }
)


def _packet_control_keys(subtype: str, taxonomy: Taxonomy) -> frozenset[str]:
    """Every ``documents:`` key that can name *subtype* — its own and its parent's.

    ``exclude: [DISCOVERY]`` empties the file of packets exactly as
    ``exclude: [SUBPOENAED_RECORDS_MEDICAL]`` does, and an attribution bound to
    the subtype spelling would report the parent-type route as "no control
    involved". Resolved through the taxonomy rather than a literal, because the
    parent of a packet subtype is the taxonomy's answer to give.
    """
    parent = taxonomy.parent_of(subtype)
    return frozenset({subtype} | ({parent} if parent else set()))


def _suppressed_packet_subtypes(
    controls: DocumentControls,
) -> dict[str, tuple[str, tuple[str, ...]]]:
    """Packet subtypes the controls forbid outright: ``{subtype: (control, keys)}``.

    *keys* are the seed lines the author must edit, which are not always the
    subtype — ``exclude: [DISCOVERY]`` suppresses all four packet subtypes through
    the parent type, and "remove SUBPOENAED_RECORDS_MEDICAL from documents.exclude"
    would send them to a line that does not exist. Empty where there is no key to
    remove, which is what ``include_only`` omission *is*.

    **Every** matching key is returned, not the first one sorted. A seed may name
    both the subtype and its parent, and removing either alone still delivers
    nothing; the lexicographic pick prescribed "remove DISCOVERY" and left
    ``SUBPOENAED_RECORDS_MEDICAL`` excluded, so following the warning literally
    was a no-op. An imperative that does not deliver is the defect this warning
    exists to remove, one level up.

    Membership only — a *positive* count is a cap and is read separately, because
    it caps rather than forbids. Precedence is the resolver's own
    (``doc_controls.resolve_document_controls``): an explicit
    ``documents.overrides`` entry decides the subtype's fate in both directions,
    which is why a positive override on an excluded subtype is *not* suppression
    — that is the resurrection path the resolver already warns about.

    **Both spellings of ``documents.overrides`` are read.** A seed writes either
    ``{subtype: X, count: N}`` or ``{type: T, max: N}``, and :class:`DocumentControls`
    splits them into two properties — ``subtype_overrides`` and ``type_bounds``.
    Reading only the first made ``{type: DISCOVERY, max: 0}`` invisible: it
    suppressed every packet and was attributed to the lifecycle stage, on seeds
    already at ``target_stage: discovery`` where the prescribed edit is a no-op.
    That is the ISC-148 defect surviving inside the ISC-148 fix, through the very
    control this module calls highest-precedence. Found by cross-model review.

    ``global_cap`` is deliberately absent, and absent means *not named* — see
    :func:`_discovery_shortfall_warning`, which must not reach for the stage
    sentence just because nothing here matched. It trims the whole plan by rank
    and cannot be attributed to a subtype.
    """
    taxonomy = effective_taxonomy()
    overrides = controls.subtype_overrides
    bounds = controls.type_bounds
    exclude, include_only = set(controls.exclude), set(controls.include_only)
    forbidden: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {}
    for subtype in sorted(DISCOVERY_PACKET_SUBTYPES):
        keys = _packet_control_keys(subtype, taxonomy)
        parent = taxonomy.parent_of(subtype)
        # An explicit per-subtype override decides this subtype's fate outright,
        # in both directions. That is the resolver's own resurrection path, and
        # the only control that genuinely short-circuits the rest.
        if subtype in overrides:
            if overrides[subtype] == 0:
                forbidden[subtype] = (("documents.overrides", (subtype,)),)
            continue
        # Membership first, then the type bound — the order
        # `resolve_document_controls` actually applies them. A type bound used to
        # `continue` past these checks whatever its value, so a seed carrying
        # both `exclude: [DISCOVERY]` and `{type: DISCOVERY, max: 2}` was told
        # only about the cap, and raising the cap delivered nothing. A control
        # the resolver did act on went unnamed, which is the same wrong answer
        # this function exists to remove.
        causes: list[tuple[str, tuple[str, ...]]] = []
        if matched := tuple(sorted(exclude & keys)):
            causes.append(("documents.exclude", matched))
        elif include_only and not (include_only & keys):
            causes.append(("documents.include_only", ()))
        if parent is not None and parent in bounds and bounds[parent][1] == 0:
            causes.append(("documents.overrides", (parent,)))
        if causes:
            forbidden[subtype] = tuple(causes)
    return forbidden


def _packet_count_controls(
    controls: DocumentControls,
) -> tuple[dict[str, tuple[str, int]], dict[str, tuple[str, int]]]:
    """``(pins, ceilings)`` — the two ways a control can state a packet count.

    Both are spelled ``documents.overrides`` and they are **not** the same thing,
    which is the distinction the first pass at this got wrong in both directions:

    * A **pin** is ``{subtype: X, count: N}`` — an exact count, a floor *and* a
      ceiling. It binds both ways: the refill may not clone above it and the trim
      may not slice below it.
    * A **ceiling** is ``{type: T, max: N}`` — a bound on the whole parent type,
      not on any one subtype, and measurably not a per-packet count: on the same
      seed, ``max: 3`` yields one packet, ``max: 6`` two, ``max: 12`` three. It
      forbids cloning, because a synthesized packet is one more document under
      the type; it does **not** oblige the file to hold any particular number, so
      trimming below it is legal and treating it as a pin would refuse the trim
      the seed asked for and warn about an overage that was never required.

    A zero belongs to neither — that is suppression, and
    :func:`_suppressed_packet_subtypes` owns it. Values are keyed by the seed line
    the author wrote, so a type bound is reported once under its own key rather
    than once per subtype it governs.
    """
    taxonomy = effective_taxonomy()
    overrides = controls.subtype_overrides
    bounds = controls.type_bounds
    pins: dict[str, tuple[str, int]] = {}
    ceilings: dict[str, tuple[str, int]] = {}
    for subtype in sorted(DISCOVERY_PACKET_SUBTYPES):
        if subtype in overrides:
            if overrides[subtype] > 0:
                pins[subtype] = (subtype, overrides[subtype])
            continue
        parent = taxonomy.parent_of(subtype)
        if parent is not None and parent in bounds:
            maximum = bounds[parent][1]
            if maximum is not None and maximum > 0:
                ceilings[subtype] = (parent, maximum)
    return pins, ceilings


def taxonomy_parent(subtype: str) -> str | None:
    """The parent type of *subtype*, resolved through the effective taxonomy."""
    return effective_taxonomy().parent_of(subtype)


def _packets_a_type_floor_requires(
    dated: list[tuple[date, str, str, str]],
    controls: DocumentControls,
) -> dict[str, int]:
    """``{parent_type: packets that must survive the trim}`` for each ``min`` bound.

    ``{type: T, min: N}`` is the other half of ``type_bounds`` and was never
    read. `_packet_count_controls` looked only at ``bounds[parent][1]``, so the
    trim sliced straight through a floor the author had written — measured, a
    ``min: 12`` floor holding 12 documents dropped to 10 under ``subpoena_sets:
    1``, silently and with no warning. That is the round-2 defect's other half:
    that round protected exact counts and ceilings from the trim and left floors
    exposed.

    The floor is on the whole type, so what it requires of *packets* is whatever
    the type's non-packet documents do not already supply. Zero when they supply
    it all — a floor satisfied elsewhere constrains nothing here.
    """
    floors = {
        parent: minimum
        for parent, (minimum, _) in controls.type_bounds.items()
        if minimum is not None and minimum > 0
    }
    if not floors:
        return {}
    taxonomy = effective_taxonomy()
    non_packet = Counter(
        taxonomy.parent_of(entry[1])
        for entry in dated
        if entry[1] not in DISCOVERY_PACKET_SUBTYPES
    )
    return {
        parent: max(0, minimum - non_packet.get(parent, 0))
        for parent, minimum in floors.items()
    }


def _type_headroom(
    dated: list[tuple[date, str, str, str]],
    ceilinged: dict[str, tuple[str, int]],
) -> dict[str, int]:
    """How many more documents each ceilinged subtype's parent type may hold.

    A ``{type: T, max: N}`` bound is on the whole type, and the plan does not
    always fill it — so "there is a ceiling" and "the ceiling binds" are
    different questions, and only the second forbids a clone. Counted from the
    dated candidate set rather than from the packets alone, because every
    subtype under the type consumes the same allowance.
    """
    if not ceilinged:
        return {}
    taxonomy = effective_taxonomy()
    under_type = Counter(taxonomy.parent_of(entry[1]) for entry in dated)
    return {
        subtype: maximum - under_type.get(parent, 0)
        for subtype, (parent, maximum) in ceilinged.items()
    }


#: The lifecycle half of the shortfall message, kept verbatim from ISC-126.
#:
#: Unchanged on purpose: it is still the right thing to say when the stage
#: really is the cause, and rewording it would move the text of a warning that
#: shipped. What ISC-148 changes is *when* it is said.
_STAGE_CAUSE = (
    "this file's lifecycle stage proposes no records packets at all; the count "
    "has nothing to act on — try target_stage 'discovery' or later"
)


def _stage_cause(delivered: int) -> str:
    """:data:`_STAGE_CAUSE`, or its honest form when the file holds packets anyway.

    ``stage_is_a_cause`` is derived from what the *walk* proposed, and the walk
    is not the last word: ``resolve_document_controls`` applies the per-subtype
    overrides afterwards, and those may invent packets of a subtype no stage
    proposes. When they do, the shipped sentence's second clause — "the count
    has nothing to act on" — is a false statement about a file that holds three
    records packets, and the same sentence then offers to lower the count to
    three, a number it could only have got from the packets it just denied.

    Round 4's version of this branch carried "the file holds {delivered} records
    packet(s)" and was factually complete; round 5 rewrote the branch for a
    different defect and dropped the count with it. That regression is what this
    repairs. The zero case still returns the shipped text verbatim, because the
    stage really is the whole story there and rewording a warning that shipped
    for no reason is its own cost.
    """
    if delivered == 0:
        return _STAGE_CAUSE
    return (
        "this file's lifecycle stage proposes no records packets at all, so the "
        f"{delivered} the file holds come from documents.overrides alone — try "
        "target_stage 'discovery' or later"
    )


def _control_causes(
    forbidden: dict[str, tuple[tuple[str, tuple[str, ...]], ...]],
    capped: dict[str, int],
) -> tuple[list[str], list[str]]:
    """Turn the blocking controls into ``(findings, imperatives)``.

    Separated from the sentence assembly so each control says what it *did* in
    its own words. The first draft used one template — "X suppresses Y" — and
    described a subtype capped at two by an override as suppressed, which is a
    false statement about a subtype the file holds.

    Imperatives are verb-first and lower-case (ISC-150): they are joined into a
    sentence whose first word is capitalized by the caller, so a directive is
    never pushed off the front of its clause by a hedge, and never reads as a
    capital in mid-sentence either.
    """
    # A subtype may be suppressed by more than one control at once, and each is
    # a genuine cause with its own edit — naming one and stopping is how the
    # exclude-plus-cap seed got an imperative that delivered nothing.
    grouped: dict[tuple[str, tuple[str, ...]], list[str]] = {}
    for subtype, causes in sorted(forbidden.items()):
        for where in causes:
            grouped.setdefault(where, []).append(subtype)

    findings: list[str] = []
    # Per control, the subtypes whose ``documents.overrides`` count must go up —
    # a zero entry and a positive one take the same edit, so they take one line.
    override_targets: list[str] = []
    exclude_keys: list[str] = []
    include_only_targets: list[str] = []

    for (control, keys), subtypes in grouped.items():
        listed = ", ".join(subtypes)
        if control == "documents.exclude":
            named = ", ".join(keys)
            # "names X, which suppresses X" on the subtype-key route; the longer
            # form is only informative when the key is the parent type.
            findings.append(
                f"documents.exclude names {named}"
                if subtypes == list(keys)
                else f"documents.exclude names {named}, which suppresses {listed}"
            )
            exclude_keys.extend(keys)
        elif control == "documents.include_only":
            findings.append(f"documents.include_only does not name {listed}")
            include_only_targets.extend(subtypes)
        else:
            # Name the line the author wrote. A `{type: DISCOVERY, max: 0}` entry
            # suppresses four subtypes through one key, and prescribing the four
            # subtype spellings sends them to lines their seed does not contain —
            # the same non-delivering imperative as the exclude route above.
            named = ", ".join(keys)
            findings.append(
                f"documents.overrides sets {named} to 0"
                if subtypes == list(keys)
                else f"documents.overrides sets {named} to 0, which suppresses {listed}"
            )
            override_targets.extend(keys)

    if capped:
        findings.append(
            "documents.overrides caps "
            + ", ".join(f"{subtype} at {count}" for subtype, count in sorted(capped.items()))
        )
        override_targets.extend(capped)

    imperatives: list[str] = []
    if exclude_keys:
        imperatives.append(f"remove {', '.join(sorted(set(exclude_keys)))} from documents.exclude")
    if include_only_targets:
        imperatives.append(
            f"add {', '.join(sorted(set(include_only_targets)))} to documents.include_only"
        )
    if override_targets:
        imperatives.append(
            "raise the documents.overrides count for "
            + ", ".join(sorted(set(override_targets)))
        )
    return findings, imperatives


def _discovery_shortfall_warning(
    declared: int,
    delivered: int,
    *,
    stage_is_a_cause: bool,
    forbidden: dict[str, tuple[tuple[str, tuple[str, ...]], ...]],
    capped: dict[str, int],
) -> str:
    """Say why the packet count could not be met, naming every cause at once.

    ISC-148. The predecessor had one message and one cause, so a control that
    emptied the file was reported as a lifecycle-stage problem — on seeds already
    at ``target_stage: discovery``, where the prescribed edit is a no-op. Both
    causes are real, they are independent, and a seed can carry both: an early
    stage proposes nothing *and* a zero-count override pins the subtype at
    nothing, so neither edit alone delivers a packet. Naming one of them there is
    a wrong answer, not a partial one.

    "No control matched" is **not** a reason to say the stage did it. The first
    fix reached for :data:`_STAGE_CAUSE` whenever ``findings`` was empty, without
    consulting *stage_is_a_cause* — so ``global_cap``, which is deliberately not
    attributable to a subtype, reproduced the original defect exactly: the stage
    blamed on a seed already at ``discovery``. Where the cause is real but
    unnameable, this says so and prescribes the edits that do exist, which is a
    true sentence. Found by cross-model review.
    """
    findings, imperatives = _control_causes(forbidden, capped)
    if not findings:
        if stage_is_a_cause:
            return (
                f"scenario.discovery.subpoena_sets is {declared} but "
                f"{_stage_cause(delivered)}"
            )
        return (
            f"scenario.discovery.subpoena_sets is {declared} but the file holds "
            f"{delivered} records packet(s) and no per-subtype control accounts for "
            "it — documents.global_cap trims the whole plan by rank, so it cannot "
            "be attributed to one subtype. Raise or remove documents.global_cap, or "
            f"lower scenario.discovery.subpoena_sets to {delivered}"
        )

    detail = "; ".join(findings)
    fallback = f"lower scenario.discovery.subpoena_sets to {delivered}"
    if stage_is_a_cause:
        # The stage is the cause we can prove; the controls are causes we cannot
        # yet see. With nothing proposed there is no way to tell, from here,
        # which of them will bite once the stage produces packets — and the
        # answer is not even a property of the subtype. `exclude:
        # [SUBPOENAED_RECORDS_EMPLOYMENT]` at `subpoena_sets: 3` was measured
        # across ten rng_seed draws: in eight the stage edit alone delivered 3
        # of 3 with the exclude still in the file, and in two (777, 1234) the
        # walk proposed that subtype, the exclude removed it, and the stage edit
        # alone delivered 0. Same seed, same control, opposite answers by draw.
        #
        # An earlier revision of this comment asserted the walk "never proposes
        # that subtype at any stage". That was never measured and is false —
        # round 6 disproved it by counting. It is recorded here because the
        # false claim was the load-bearing justification for the sentence below,
        # and the sentence survives only because the truth is *stronger*: not
        # "this control is harmless" but "which control binds is undecidable
        # from this branch".
        #
        # An earlier pass asserted "both edits are needed" for every listed
        # control. That is a confident false claim in the second case — measured
        # in 9 of 12 rng_seed draws, the stage edit alone delivered the full
        # count with the exclude still in place. The first pass had the opposite
        # defect, withholding the control entirely, which left a non-delivering
        # imperative when the control did bite.
        #
        # Both failures come from asserting something unknowable. This states the
        # stage as the cause, prescribes its edit, and lists the controls as the
        # next place to look rather than as a second required edit — which is
        # true whichever way the unknown resolves, and still delivers when
        # followed in order.
        edits = ", and ".join(imperatives)
        return (
            f"scenario.discovery.subpoena_sets is {declared} but {_stage_cause(delivered)}. "
            f"The file also carries controls over records packets: {detail}. "
            f"{_capitalized(edits)} if the stage change alone does not deliver "
            f"the count, or {fallback}"
        )
    edits = ", or ".join(imperatives)
    return (
        f"scenario.discovery.subpoena_sets is {declared} but the document controls "
        f"permit only {delivered} records packet(s): {detail}. "
        f"{_capitalized(edits)}, or {fallback} — the control wins until then"
    )


def _capitalized(sentence: str) -> str:
    """*sentence* with its first letter upper-cased and the rest untouched.

    ``str.capitalize`` lower-cases the tail, which would turn every subtype key
    in the imperative into prose.
    """
    return sentence[:1].upper() + sentence[1:]


def _shape_discovery(
    seed: CaseSeed,
    timeline: CaseTimeline,
    dated: list[tuple[date, str, str, str]],
    controls: DocumentControls,
    *,
    proposed: frozenset[str],
) -> tuple[list[tuple[date, str, str, str]], tuple[str, ...]]:
    """ISC-126/148. Make the file hold the packets the seed asked for — up to the controls.

    Trims from the end and extends by repeating a surviving packet's shape on a
    later date, which keeps the added packets inside the file's own runway rather
    than inventing a discovery phase that never happened.

    Gated on a *stated* count. A seed that says nothing keeps whatever the walk
    proposed, byte for byte — the same rule ISC-109 set for surgery, and what
    keeps every pre-0.7.0 seed identical.

    ISC-148 threads the resolved ``documents:`` block in, because without it this
    function outranked the highest-precedence control in the package. Two defects
    came out of that blindness, and the second is the one a guard for the first
    walks straight past:

    * the refill cloned the last packet to reach *declared* even when
      ``documents.overrides`` had set that subtype's exact count, which needs a
      **mixed** set to reproduce — one subtype surviving, another suppressed;
    * with nothing surviving, the shortfall was reported as a lifecycle-stage
      problem on files already at ``target_stage: discovery``.

    Args:
        seed: the case seed; ``scenario.discovery.subpoena_sets`` is the gate.
        timeline: supplies the horizon any synthesized packet date is fitted to.
        dated: the shaped candidate set, controls already applied.
        controls: the **normalized** ``documents:`` block — canonical keys, so a
            substrate-only spelling in the seed cannot read as "no control here".
        proposed: the packet subtypes the lifecycle walk proposed *before* the
            controls ran. This is what separates the two causes: a control that
            names a subtype the walk never proposed removed nothing, and blaming
            it would send the author to a line whose edit changes nothing.

    Returns:
        The shaped list and at most one warning naming every cause of a shortfall.
    """
    declared = seed.scenario.discovery.subpoena_sets
    if declared is None:
        return dated, ()

    packets = [entry for entry in dated if entry[1] in DISCOVERY_PACKET_SUBTYPES]
    if len(packets) == declared:
        return dated, ()

    forbidden = _suppressed_packet_subtypes(controls)
    pinned, ceilinged = _packet_count_controls(controls)
    # A pin states an exact count, so cloning one is always an overrule and the
    # subtype cannot be a donor. A ceiling is enforced differently — by clamping
    # how many clones the donor may produce, below — and deliberately NOT by
    # excluding the subtype here.
    #
    # The distinction is measured, not assumed: `max: 3` fills the DISCOVERY type
    # to 3 of 3 and `max: 6` to 6 of 6, but `max: 12` reaches only 10 of 12 — two
    # spare. Reading the packet ladder alone (1, 2, 3 packets) suggests a ceiling
    # always binds; counting documents under the type shows it does not, and
    # refusing to refill below the cap denies a count both controls permit.
    #
    # An earlier pass excluded at-cap ceilinged subtypes here as well. The gate
    # then scored that clause SURVIVED, which was correct: every packet subtype
    # shares the parent DISCOVERY, so a type bound ceilings all of them at once
    # and the clamp already yields zero clones at zero headroom. Two mechanisms
    # for one rule, the second unreachable. Removed rather than given a mutant
    # that could only ever pass.
    headroom = _type_headroom(dated, ceilinged)
    uncloneable = set(pinned)

    shaped = [entry for entry in dated if entry[1] not in DISCOVERY_PACKET_SUBTYPES]
    packets.sort(key=lambda entry: entry[0])
    overage: dict[str, int] = {}
    floors: list[tuple[str, int, int]] = []
    if len(packets) > declared:
        # The trim side used to be `packets[:declared]` — a blind date-ordered
        # prefix. `resolve_document_controls` has already applied the override
        # counts by this point, so those packets are the count the author wrote;
        # slicing them off overruled the highest-precedence control in exactly
        # the direction the refill fix did not cover. Measured: two subtypes each
        # pinned at 2 with `subpoena_sets: 1` dropped one subtype ENTIRELY, and
        # said nothing. Found by cross-model review.
        #
        # Pinned packets are kept whole and the remainder is trimmed from the
        # unpinned ones, latest first. When the pins alone exceed `declared` the
        # two controls genuinely conflict, and `documents.overrides` wins by
        # documented precedence — so the file holds more than `subpoena_sets`
        # asked for and the warning says which pins did it.
        # Kept-ness is tracked by POSITION in `packets`, not by tuple value. A
        # packet is a `(date, subtype, track, role)` tuple, and two of them can
        # be equal without being the same document — the resolver may plan two
        # of one subtype and the parallel core track may date them alike. Under
        # `entry not in kept`, one copy in `kept` made BOTH copies invisible to
        # the floor restore below, so a floor could be reported short with a
        # spare packet sitting unused. Positions are unique by construction.
        #
        # The pre-sort concatenation order is preserved exactly — pinned, then
        # the unpinned prefix, then whatever the floor restores — because the
        # sort is stable and packets sharing a date resolve their tie by it.
        # Changing that order would change bytes for tied dates.
        pinned_at = [index for index, entry in enumerate(packets) if entry[1] in pinned]
        unpinned_at = [
            index for index, entry in enumerate(packets) if entry[1] not in pinned
        ]
        room = declared - len(pinned_at)
        kept_at = pinned_at + (unpinned_at[:room] if room > 0 else [])
        kept = sorted((packets[index] for index in kept_at), key=lambda entry: entry[0])
        # A `{type: T, min: N}` floor is the other half of `type_bounds`, and the
        # trim used to cut straight through it — a floor holding 12 documents
        # dropped to 10 under `subpoena_sets: 1`, silently. Restore whichever
        # trimmed packets the floor still needs, earliest of the trimmed first,
        # so the kept set stays a suffix-consistent slice rather than an
        # arbitrary one.
        required = _packets_a_type_floor_requires(dated, controls)
        floors_binding: list[str] = []
        for parent, need in sorted(required.items()):
            held = sum(1 for index in kept_at if taxonomy_parent(packets[index][1]) == parent)
            if held >= need:
                continue
            spare = [
                index
                for index in range(len(packets))
                if index not in kept_at and taxonomy_parent(packets[index][1]) == parent
            ]
            kept_at = kept_at + spare[: need - held]
            kept = sorted(
                (packets[index] for index in kept_at), key=lambda entry: entry[0]
            )
            floors_binding.append(parent)
        if room < 0 or floors_binding:
            # Report the seed lines that state the counts, not the subtypes they
            # happen to govern — `{type: DISCOVERY, max: 2}` is one line.
            overage = {
                pinned[subtype][0]: pinned[subtype][1]
                for subtype in sorted({entry[1] for entry in kept})
                if subtype in pinned
            }
            # A floor is NOT a pin, and its number is not counted in the same
            # unit. `overage` maps a seed key to a packet count and its sentence
            # says "pins <key> at <n>". An earlier pass merged the floors into it
            # with `overage.update(floors_binding)`, which stated two falsehoods
            # at once: it called `{type: DISCOVERY, min: 67}` a pin, and it
            # printed 67 as though the file held 67 records packets — 67 counts
            # *documents under the type*, and the file held 52 of them. The
            # sentence therefore claimed a floor was being honoured at the exact
            # moment it was unmet. Floors get their own clause below, in their
            # own unit, reporting what the file actually holds.
            for parent in floors_binding:
                held_documents = sum(
                    1 for entry in shaped + kept if taxonomy_parent(entry[1]) == parent
                )
                floors.append(
                    (parent, controls.type_bounds[parent][0] or 0, held_documents)
                )
    else:
        kept = list(packets)
    if len(packets) < declared:
        # The latest packet whose count no control pinned. With no overrides at
        # all this is `packets[-1]` — the pre-ISC-148 donor, byte for byte.
        donor = next(
            (entry for entry in reversed(packets) if entry[1] not in uncloneable), None
        )
        if donor is not None:
            last_date, subtype, track, role = donor
            ceiling = timeline.horizon
            # Clone up to the shortfall, but never past the donor's own type
            # allowance. A subtype reaches this line only with headroom > 0, and
            # the headroom is how many more the type may hold — so a shortfall
            # larger than the spare room is filled as far as the control permits
            # and then reported, rather than met by breaching it.
            wanted = declared - len(packets)
            allowed = min(wanted, headroom[subtype]) if subtype in headroom else wanted
            for step in range(allowed):
                when = min(last_date + timedelta(days=14 * (step + 1)), ceiling)
                kept.append((when, subtype, track, role))

    if len(kept) == declared:
        return shaped + kept, ()

    if overage or floors:
        # Two controls, two units, two sentences. A pin counts records packets of
        # one subtype; a floor counts every document under a parent type, packets
        # and non-packets alike. Each clause states its own number in its own
        # unit, and the floor clause reports what the file holds rather than
        # asserting the floor is satisfied — because it need not be. When the
        # spare packets run out before the minimum is reached the trim has kept
        # everything it can and the floor is still short, which is the one case
        # the author most needs told.
        causes: list[str] = []
        remedies: list[str] = []
        if overage:
            pins = ", ".join(
                f"{key} at {count}" for key, count in sorted(overage.items())
            )
            causes.append(f"pins {pins}")
            remedies.append("lower the documents.overrides count(s)")
        for parent, minimum, held in sorted(floors):
            if held >= minimum:
                causes.append(
                    f"sets min {minimum} on {parent}, which the file meets with "
                    f"{held} document(s) under that type"
                )
            else:
                causes.append(
                    f"sets min {minimum} on {parent} and the file holds only {held} "
                    "document(s) under that type, so every records packet was kept "
                    "and the floor is still short"
                )
            # "Lower the min" is not an edit that converges, and it was shipped
            # as though it were. The reported `held` is not independent of the
            # floor — `_apply_type_min` grows the type to reach it — so lowering
            # the min to the number the sentence just printed lowers the number:
            # measured, 67 -> 52 -> 41 -> 32 -> 26 -> 21 -> 17, still short at
            # every step. Removing the floor is the edit that actually resolves
            # this cause, and it is the one prescribed.
            remedies.append(f"remove the documents.overrides min on {parent}")
        # The remedies are NOT independently sufficient, and joining them with
        # "or" said they were. With a pin and a floor both in force, removing the
        # floor alone still leaves the pinned packets — measured, 2 against a
        # declared 1. Raising the declared count is the one edit that always
        # resolves this warning, so it leads; the rest is offered as "whichever
        # binds", which asserts nothing about sufficiency.
        #
        # A floor left short by this trim is no longer this sentence's business
        # either: every `min` is now verified against the finished plan in
        # `doc_controls`, so it carries its own warning and keeps it after the
        # author acts on any remedy here. Round 6 measured the alternative —
        # lowering the pin silenced this warning and left a floor short by 16
        # with nothing said at all.
        return shaped + kept, (
            f"scenario.discovery.subpoena_sets is {declared} but documents.overrides "
            f"{'; and '.join(causes)} — {len(kept)} records packet(s) in total. The "
            "override is the higher-precedence control, so the file holds what it "
            "requires rather than the declared count. Raise "
            f"scenario.discovery.subpoena_sets to {len(kept)}, or lift whichever of "
            f"these binds: {'; '.join(remedies)}",
        )

    # Attribution, keyed off what a control actually did rather than off whether
    # its key appears in the seed. A membership control earns the blame for a
    # subtype the walk proposed for it to remove — and a zero-count override
    # earns it regardless, because the author wrote it about this exact subtype.
    #
    # The third clause is the one an earlier pass got backwards. When the walk
    # proposed nothing, `subtype in proposed` is false for every subtype, so
    # every membership control was exonerated — at exactly the moment
    # `stage_is_a_cause` is true. An early stage plus `exclude:
    # [SUBPOENAED_RECORDS_MEDICAL]` therefore printed the stage sentence alone,
    # and following it delivered nothing because the exclude bites the instant
    # the stage stops being the obstacle. "Removed nothing yet" is not
    # "innocent"; it is the second half of a two-edit fix, which is the case
    # `_discovery_shortfall_warning` was written to handle and this filter was
    # quietly withholding from it.
    stage_is_a_cause = not proposed
    blocking = {
        subtype: causes
        for subtype, causes in forbidden.items()
        if subtype in proposed
        or stage_is_a_cause
        or any(control == "documents.overrides" for control, _ in causes)
    }
    # Keyed by the seed line, so a type-level bound is reported once under the
    # key the author wrote rather than once per subtype it governs. A ceiling is
    # reported whether or not a packet survived it: unlike a pin, `max: 2` can
    # bind hard enough to leave none, and staying silent then would hand the
    # shortfall to the unattributable branch and name no control at all.
    present = {entry[1] for entry in kept}
    capping = {key: count for subtype, (key, count) in pinned.items() if subtype in present}
    capping.update(
        {
            key: count
            for subtype, (key, count) in ceilinged.items()
            if subtype in present or subtype in proposed
        }
    )

    return shaped + kept, (
        _discovery_shortfall_warning(
            declared,
            len(kept),
            stage_is_a_cause=stage_is_a_cause,
            forbidden=blocking,
            capped=capping,
        ),
    )


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

    # The cast is built here rather than after the document loop so the ledger
    # can be derived *once*, with the cast, and used everywhere. Deriving a
    # cast-free copy for planning and a cast-bearing copy for publication meant
    # two derivations per case that disagreed with each other — the planner saw
    # one provider, the manifest published five.
    cast = build_case_cast(seed, timeline, case_number=case_number)
    case_facts = derive_case_facts(seed, timeline, cast)
    # The resolved diligence is passed in rather than re-resolved, so the money
    # and the clinical ledger cannot disagree about who handled this file. Two
    # independent resolutions of the same persona is the defect that let
    # ``scenario.surgery`` and ``has_surgery`` contradict each other in Phase 1.
    money_facts = derive_money_facts(seed, timeline, case_facts.adjuster_diligence)
    # The cast's date of birth rather than a second derivation of it — the ledger and
    # the documents must not reach two different ages for one applicant.
    medical_history = derive_medical_history(
        seed, timeline, date_of_birth=cast.case.applicant.date_of_birth
    )
    # …and the substrate's own wage field follows the published one, before any
    # template reads it. Three document families derive money from
    # ``employer.hourly_rate``; none of them were fact-aware.
    align_employer_wage(cast.case, money_facts)

    core = build_core_candidates(seed, timeline)
    lien_tracks = build_lien_tracks(seed, timeline)
    recon = build_recon_track(seed, timeline)

    candidates: list[DatedCandidate] = [
        *core,
        *lien_candidates(lien_tracks),
        *recon.documents,
        # Through the same gate as everything else — see _penalty_candidates.
        *_penalty_candidates(case_facts, timeline),
        *_delay_chain_candidates(case_facts, timeline),
    ]
    candidates.extend(_money_candidates(seed, money_facts, timeline, candidates))

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

    dated, scenario_warnings = _shape_for_scenario(seed, timeline, case_facts, dated)
    # After shaping: `never_treated` and `discharged` both drop documents, and
    # re-dating a set that is about to lose members would leave gaps the cadence
    # never intended.
    # ISC-148. The controls ride in with the walk's own packet proposal, because
    # "the stage proposed none" and "a control removed them" are different
    # defects with different edits, and the shaper cannot tell them apart from
    # the surviving plan alone.
    dated, discovery_warnings = _shape_discovery(
        seed,
        timeline,
        dated,
        controls,
        proposed=frozenset(
            candidate.subtype
            for candidate in candidates
            if candidate.subtype in DISCOVERY_PACKET_SUBTYPES
        ),
    )
    # ISC-126. The page budget is drawn only once the packet count is final, so
    # the ledger, the cover sheet and the rendered pages are three readings of
    # one number rather than three independent draws.
    packet_count = sum(1 for entry in dated if entry[1] in DISCOVERY_PACKET_SUBTYPES)
    case_facts = case_facts.model_copy(
        update={"packet_pages": derive_packet_pages(seed, packet_count)}
    )
    dated, cadence_warnings = _apply_attorney_cadence(case_facts, timeline, dated)
    penalty_warnings = _penalty_control_warnings(case_facts, dated, controls)
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


    emitted = _emitted_per_track(
        documents, [track.documents for track in lien_tracks] + [recon.documents]
    )
    lien_counts, recon_count = emitted[: len(lien_tracks)], emitted[len(lien_tracks)]
    emitted_subtypes = {document.subtype for document in documents}
    recon_subtypes = frozenset(
        candidate.subtype for candidate in recon.documents if candidate.subtype in emitted_subtypes
    )

    # The floor verdict, taken here because here is the first place the finished
    # file exists. `resolve_document_controls` hands out the question rather than
    # an answer: the scenario shaping between it and this line can drop a whole
    # type, so a floor decided there described a file that no longer existed by
    # the time the manifest was written. Counted off `dated`, which is exactly
    # what becomes `plan.documents`.
    held_by_type = Counter(
        parent for entry in dated if (parent := taxonomy.parent_of(entry[1])) is not None
    )
    floor_warnings = verify_type_floors(
        control.floor_checks, held_by_type, control.type_totals()
    )
    # The cap verdict, for the same reason and in the same place. Round 8 moved
    # the floor verdict out here because the resolver's plan is not the file, and
    # left this one behind — so `global_cap: 5` warned "cannot be met" about a
    # file holding zero documents, naming as the culprit a floor that a second
    # warning in the same manifest reported empty.
    # Both parentheticals describe the file too: the pinned count is what
    # SURVIVED, not what the resolver pinned, and whether a forced subtype's
    # control "won" is a question only the finished file can answer.
    held_by_subtype = Counter(entry[1] for entry in dated)
    floor_warnings.extend(
        verify_global_cap(
            control.cap_check,
            len(dated),
            sum(held_by_subtype[key] for key in control.forced_subtypes()),
        )
    )
    floor_warnings.extend(
        verify_forced_subtypes(control.forced_checks, held_by_subtype)
    )

    # The sixth site, and the only one outside `doc_controls`. "Its language will
    # be rendered" is a claim about the finished file, and doctrine text reaches
    # a file only through `content_flags` on a document that survives — so the
    # count comes from `documents`, not from the seed. Measured before this
    # change: the warning fired in 24 of 24 configurations and the language was
    # rendered in none of them, because the condition that makes a hook
    # unsupported is usually the same one that removes its carrier documents.
    carried_by_hook: Counter[str] = Counter()
    for document in documents:
        for flag in document.content_flags or ():
            carried_by_hook[flag] += 1
    hook_warnings = verify_unsupported_hooks(
        unsupported_hooks(seed.lifecycle.doctrine_hooks, seed), carried_by_hook
    )

    warnings = (
        *control.warnings,
        *floor_warnings,
        *recon.warnings,
        *cast.warnings,
        *scenario_warnings,
        *discovery_warnings,
        *cadence_warnings,
        *penalty_warnings,
        *_money_control_warnings(seed, money_facts),
        *hook_warnings,
        # Silent unless the seed opened the medical-history layer — see
        # medical_history.HOOK_GROUNDING for why a warning cannot be allowed to fire
        # on a seed that never asked for the layer at all.
        *grounding_warnings(seed, medical_history),
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
        case_facts=case_facts,
        money_facts=money_facts,
        medical_history=medical_history,
    )


__all__ = [
    "MONEY_FLOOR_SUBTYPES",
    "MONEY_PD_SUBTYPE",
    "MONEY_TD_SUBTYPE",
    "MONEY_WAGE_SUBTYPE",
    "CasePlan",
    "ControlKeyError",
    "PlannedDocument",
    "build_case_plan",
    "canonical_control_key",
    "normalize_control_keys",
]
