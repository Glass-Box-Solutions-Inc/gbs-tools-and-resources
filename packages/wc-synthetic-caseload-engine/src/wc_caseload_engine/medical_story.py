"""M3 medical-story document surfaces — frozen models and literals (AJC-62).

This module owns the document-scoped view of the medical story: the label-free,
visibility-limited projection records a renderer is allowed to see (R4), the
contention-surface vocabulary that separates a canonical manifest carrier from
its internal ``template_subtype`` (R2/R5), and the gated UR/IMR plan models
(R39). R77 step 6 adds ``plan_medical_story_documents()`` — the planner's
single post-perspective/pre-control insertion point that materializes the
R32-derived contention-document bindings as bound ``DatedCandidate`` objects
with R34 chronology; ``derive_medical_story()`` — the pure projection that
populates the records below after the final document tuple is dated,
controlled, perspective-resolved, sorted and indexed — arrives with the
renderer step, as does the surface map.

Two boundaries are load-bearing:

* **No ``quality``, ever.** Every record here mirrors *semantic* assertion
  fields only. Truth grades live in the production ledger and export to exactly
  one artifact — the truth manifest's assertions channel — which Amendment A1
  freezes to the AJC-61 projection for all of AJC-62, so nothing in this module
  can reach that channel either.
* **Internal only.** :class:`DocumentMedicalStory` and :class:`MedicalStoryPlan`
  are renderer inputs. They are never published to ``case_facts.yaml``,
  ``manifest.json``, copied seed YAML, filenames, warnings or logs (R4).

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from fractions import Fraction
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from wc_caseload_engine.doc_controls import TRACK_CORE, TRACK_SUPPORTING
from wc_caseload_engine.lifecycle_bridge import (
    ROLE_COURT_REPORTER,
    ROLE_PHYSICIAN,
    CaseTimeline,
    DatedCandidate,
    fit_dates,
)
from wc_caseload_engine.medical_assertions import (
    AoeCoeFinding,
    ApportionmentAssertion,
    ApportionmentBasisKind,
    ApportionmentDeterminationKind,
    ApportionmentState,
    Contention,
    ContentionClaimType,
    ContentionDocumentBinding,
    ContentionParty,
    ContentionPosition,
    MedicalAssertionError,
    MedicalAssertionLedger,
    MedicalAssertionPlan,
    MedicalOpinion,
    OpinionAuthorRole,
    OpinionEventKind,
    OpinionReportStage,
    OpinionRevisionKind,
    PsychAddOnExceptionAnalysis,
    RequestedApportionment,
    TreatmentCausation,
)
from wc_caseload_engine.medical_history import (
    ApplicantDemographics,
    MedicalCondition,
    MedicalHistory,
    PriorAward,
    PriorClaim,
    PsychInjuryKind,
)
from wc_caseload_engine.seeds import (
    CaseSeed,
    DoctrineGrounding,
    DoctrineHook,
    ImrOutcome,
    UrDecision,
)

if TYPE_CHECKING:  # pragma: no cover - import cycle guard (planner imports us)
    from wc_caseload_engine.planner import PlannedDocument

type ContentionSurface = Literal[
    "advocacy",
    "objection",
    "supplemental_request",
    "qme_deposition",
]
"""Which contention-loop surface a bound document speaks with (R4/R5).

Internal render state beside ``template_subtype`` — never a manifest subtype,
never a taxonomy key. ``DEPOSITION_TRANSCRIPT`` is medical-story-governed only
when its surface is ``qme_deposition``; ordinary depositions keep their
pre-M3 path (R8).
"""

# ---------------------------------------------------------------------------
# R8 — the frozen governed subtype sets (AJC-62 Part 1)
# ---------------------------------------------------------------------------
# Landed at R77 step 5 because R27/R40 carrier-compatibility validation in the
# contention loop consumes them; the surface MAP that renders them (R9,
# fact-aware subclasses) remains step-7 material. ``DEPOSITION_TRANSCRIPT`` is
# governed only when its ``contention_surface`` is ``qme_deposition``;
# ``IME_REPORT`` and specialty treatment records outside these sets are not
# M3 medical-story surfaces.

INITIAL_MEDLEGAL_SURFACES = frozenset(
    {
        "QME_REPORT_INITIAL",
        "QME_COMPREHENSIVE_REPORT",
        "AME_REPORT",
        "AME_COMPREHENSIVE_REPORT",
        "MEDICAL_LEGAL_QME_AME_IME",
        "APPORTIONMENT_REPORT",
    }
)

PSYCH_MEDLEGAL_SURFACES = frozenset(
    {
        "PSYCH_EVAL_REPORT_QME_AME",
    }
)

SUPPLEMENTAL_MEDLEGAL_SURFACES = frozenset(
    {
        "QME_REPORT_SUPPLEMENTAL",
        "SUPPLEMENTAL_QME_AME_REPORT",
    }
)

PTP_CAUSATION_SURFACES = frozenset(
    {
        "TREATING_PHYSICIAN_REPORT",
        "TREATING_PHYSICIAN_REPORT_PR2",
        "TREATING_PHYSICIAN_REPORT_PR4",
        "TREATING_PHYSICIAN_REPORT_FINAL",
    }
)

PTP_APPORTIONMENT_SURFACES = frozenset(
    {
        "TREATING_PHYSICIAN_REPORT_PR4",
        "TREATING_PHYSICIAN_REPORT_FINAL",
    }
)

ADVOCACY_LETTER_SURFACES = frozenset(
    {
        "ADVOCACY_LETTERS_PTP",
        "ADVOCACY_LETTERS_QME",
        "ADVOCACY_LETTERS_AME",
        "ADVOCACY_LETTERS_PTP_QME_AME",
    }
)

_STORY_MODEL_CONFIG = ConfigDict(extra="forbid", frozen=True)


class StoryDemographics(BaseModel):
    """The demographic facts a governed document may state (R4)."""

    model_config = _STORY_MODEL_CONFIG

    age: int = Field(ge=0)
    sex: Literal["female", "male"]
    bmi_band: Literal["normal_or_under", "overweight", "obese", "severely_obese"]
    smoking_status: Literal["never", "former", "current"]


class StoryCondition(BaseModel):
    """One world condition as a document may see it (R4).

    Deliberately narrower than :class:`~wc_caseload_engine.medical_history.
    MedicalCondition`: no ``causal_ground_truth``, no ``wholly_unrelated``, no
    ``surfaces_in_file`` — visibility is decided by the projector, and truth
    grades never existed here.
    """

    model_config = _STORY_MODEL_CONFIG

    id: str
    label: str
    body_system: str
    body_part: str | None = None
    icd10: str | None = None
    onset: dt.date | None = None
    severity: Literal["subclinical", "mild", "moderate", "severe"]
    trajectory: Literal["resolved", "stable", "progressive", "fluctuating"]
    symptomatic_before_doi: bool | None = None
    billing_coded: bool = False


class StoryPriorClaim(BaseModel):
    """One prior claim as a document may cite it (R4)."""

    model_config = _STORY_MODEL_CONFIG

    id: str
    date_of_injury: dt.date
    body_parts: tuple[str, ...]
    resolution_type: str


class StoryPriorAward(BaseModel):
    """One prior award as a document may cite it (R4)."""

    model_config = _STORY_MODEL_CONFIG

    id: str
    prior_claim_id: str
    body_parts: tuple[str, ...]
    pd_percent: int
    award_date: dt.date
    resolution_type: str
    conclusively_presumed: bool


class StoryRecordReference(BaseModel):
    """One actual earlier planned document a report may reference (R4/R10)."""

    model_config = _STORY_MODEL_CONFIG

    document_index: int
    subtype: str
    title: str
    doc_date: dt.date
    author_role: str


class StoryContention(BaseModel):
    """Every semantic :class:`~wc_caseload_engine.medical_assertions.Contention`
    field except ``quality`` (R4)."""

    model_config = _STORY_MODEL_CONFIG

    id: str
    claim_type: ContentionClaimType
    party: ContentionParty
    position: ContentionPosition
    target_condition_id: str | None = None
    target_prior_claim_id: str | None = None
    target_prior_award_id: str | None = None
    target_body_part: str | None = None
    doctrine_hooks: tuple[DoctrineHook, ...] = ()
    rationale: str | None = None
    treatment_causation: TreatmentCausation | None = None
    requested_apportionment: RequestedApportionment | None = None
    groundings: tuple[DoctrineGrounding, ...] = ()
    psych_injury_kind: PsychInjuryKind | None = None


class StoryMedicalOpinion(BaseModel):
    """Every semantic :class:`~wc_caseload_engine.medical_assertions.
    MedicalOpinion` field except ``quality`` (R4)."""

    model_config = _STORY_MODEL_CONFIG

    id: str
    author_role: OpinionAuthorRole
    report_stage: OpinionReportStage
    report_date: dt.date
    apportionment_state: ApportionmentState
    determination_kind: ApportionmentDeterminationKind | None = None
    determination_rationale: str | None = None
    examination_performed: bool = False
    reviewed_condition_ids: tuple[str, ...] = ()
    reviewed_prior_claim_ids: tuple[str, ...] = ()
    reviewed_prior_award_ids: tuple[str, ...] = ()
    endorses_contention_ids: tuple[str, ...] = ()
    concurs_with_contention_ids: tuple[str, ...] = ()
    rejects_contention_ids: tuple[str, ...] = ()
    defers_contention_ids: tuple[str, ...] = ()
    responds_to_opinion_id: str | None = None
    supersedes_opinion_id: str | None = None
    rationale: str | None = None
    revision_rationale: str | None = None
    event_kind: OpinionEventKind = "base_report"
    revision_kind: OpinionRevisionKind | None = None
    psych_injury_kind: PsychInjuryKind | None = None
    aoe_coe_finding: AoeCoeFinding | None = None
    aoe_coe_rationale: str | None = None


class StoryApportionment(BaseModel):
    """Every semantic :class:`~wc_caseload_engine.medical_assertions.
    ApportionmentAssertion` field except ``quality`` (R4)."""

    model_config = _STORY_MODEL_CONFIG

    id: str
    opinion_id: str
    body_part: str
    industrial_percent: int
    nonindustrial_percent: int
    basis_kinds: tuple[ApportionmentBasisKind, ...] = ()
    condition_ids: tuple[str, ...] = ()
    prior_claim_ids: tuple[str, ...] = ()
    prior_award_ids: tuple[str, ...] = ()
    description: str | None = None
    disability_causation_stated: bool = False
    reasonable_medical_probability: bool = False
    causal_rationale: str | None = None
    percentage_rationale: str | None = None
    prior_award_analysis: str | None = None
    revised_from_percent: int | None = None
    revision_rationale: str | None = None
    psych_exception_analysis: PsychAddOnExceptionAnalysis | None = None
    linked_contention_id: str | None = None
    groundings: tuple[DoctrineGrounding, ...] = ()


class DocumentMedicalStory(BaseModel):
    """The complete medical story ONE document is allowed to tell (R4).

    Internal render state. Populated by ``derive_medical_story()`` from the
    explicit R5/R35 bindings — never guessed from a nearest date, report
    ordinal, subtype coincidence or collection order.
    """

    model_config = _STORY_MODEL_CONFIG

    document_index: int
    subtype: str
    template_subtype: str | None = None
    contention_surface: ContentionSurface | None = None
    demographics: StoryDemographics
    conditions: tuple[StoryCondition, ...] = ()
    prior_claims: tuple[StoryPriorClaim, ...] = ()
    prior_awards: tuple[StoryPriorAward, ...] = ()
    record_references: tuple[StoryRecordReference, ...] = ()
    preceding_report: StoryRecordReference | None = None
    contentions: tuple[StoryContention, ...] = ()
    medical_opinion: StoryMedicalOpinion | None = None
    apportionments: tuple[StoryApportionment, ...] = ()


class MedicalStoryPlan(BaseModel):
    """Every governed document's story, keyed by final document index (R4)."""

    model_config = _STORY_MODEL_CONFIG

    by_document_index: Mapping[int, DocumentMedicalStory] = Field(
        default_factory=dict
    )


class ImrApplicationContent(BaseModel):
    """The resolved IMR application content one bound form renders (R39).

    The sparse-field register IS the content: applicant-attorney under-working
    is expressed only through absent attachments, records, rebuttals or MTUS
    citations — never through a ``thin``/``underworked``/``adequacy``/
    ``quality`` style field, which this model deliberately does not have.
    """

    model_config = _STORY_MODEL_CONFIG

    disputed_treatment: str | None = None
    diagnosis_icd10: str | None = None
    ur_determination_attached: bool | None = None
    supporting_record_subtypes: tuple[str, ...] = ()
    clinical_rebuttal: str | None = None
    mtus_citations: tuple[str, ...] = ()
    target_denial_subtype: str
    target_denial_date: dt.date


class MedicalUrPlan(BaseModel):
    """The gated UR/IMR resolution for the medical-story path (R39).

    Resolves an unstated UR decision ONCE and supplies that same answer to
    substrate parameters and guaranteed UR documents; a stated ``decision`` or
    ``imr`` (detected through Pydantic's authored-field set, explicit ``false``
    included) remains authoritative. Populated by the step-8 derivation; the
    medical-story-absent path never constructs one.
    """

    model_config = _STORY_MODEL_CONFIG

    effective_decision: UrDecision
    decision_was_authored: bool
    imr_requested: bool
    imr_was_authored: bool
    effective_imr_outcome: ImrOutcome | None = None
    imr_application: ImrApplicationContent | None = None


def medical_ur_semantic_key(seed: CaseSeed) -> tuple[object, ...]:
    """R45's exact structural ``U`` identity for one UR dispute."""
    return (
        "case",
        seed.case_id,
        "ur",
        seed.injury.onset_date,
        seed.scenario.surgery,
        tuple(sorted(part.part for part in seed.injury.body_parts)),
    )


def _medical_ur_stream_key(seed: CaseSeed, *suffix: object) -> tuple[object, ...]:
    """R46 family key with the structural ``U`` embedded as one identity."""
    return ("case", seed.case_id, medical_ur_semantic_key(seed), *suffix)


def _fraction_hit(rng: Any, probability: Fraction) -> bool:
    """Use the engine's frozen Fraction draw convention (R49/R57)."""
    return rng.random() < float(probability)


def _weighted_member(rng: Any, rows: Sequence[tuple[Any, Fraction]]) -> Any:
    """Use the engine's frozen ordered weighted-choice convention."""
    draw = rng.random()
    cursor = 0.0
    for member, weight in rows:
        cursor += float(weight)
        if draw < cursor:
            return member
    return rows[-1][0]


def derive_medical_ur_plan(
    seed: CaseSeed,
    *,
    target_denial_date: dt.date | None = None,
    resolved_decision: UrDecision | None = None,
) -> MedicalUrPlan | None:
    """Resolve the gated R39/R57 UR decision, IMR request, and outcome once.

    The feature-absent path returns before constructing an M3 stream.  The IMR
    request waits for the actual denial date because R46 keys that draw by
    ``(U, denial_date)``; callers therefore resolve once before the lifecycle
    walk for its UR decision, then once with that hard date before supplying
    the completed answer to both substrate parameters and guaranteed paper.
    Both calls are pure and entity-private, so they return the same decision.
    """
    if seed.scenario.medical_history is None:
        return None
    ur = seed.lifecycle.ur_dispute
    if not ur.enabled:
        return None

    # Import through the module attribute so R68/R70's production stream
    # recorder observes every construction (R44).
    from wc_caseload_engine import medical_assertions as assertions_module

    decision_was_authored = (
        "decision" in ur.model_fields_set and ur.decision is not None
    )
    if resolved_decision is not None:
        effective_decision = resolved_decision
    elif decision_was_authored:
        effective_decision = ur.decision
    else:
        effective_decision = _weighted_member(
            assertions_module._medical_story_rng(
                seed, "ur-decision", _medical_ur_stream_key(seed)
            ),
            assertions_module.UR_DECISION_WEIGHTS_WHEN_UNSTATED.value,
        )

    imr_was_authored = "imr" in ur.model_fields_set
    if imr_was_authored:
        imr_requested = ur.imr
    elif effective_decision == "upheld" and target_denial_date is not None:
        imr_requested = _fraction_hit(
            assertions_module._medical_story_rng(
                seed,
                "imr-request",
                _medical_ur_stream_key(seed, target_denial_date),
            ),
            assertions_module.P_IMR_REQUEST_GIVEN_UPHELD_DENIAL.value,
        )
    else:
        imr_requested = False

    if imr_requested and effective_decision != "upheld":
        raise MedicalAssertionError(
            "medical-story IMR request requires an effective upheld UR denial; "
            f"case {seed.case_id!r} authored imr=true against "
            f"{effective_decision!r} (R39)"
        )
    if ur.imr_application is not None and not imr_requested:
        raise MedicalAssertionError(
            "medical-story explicit imr_application requires an effective IMR "
            f"request in case {seed.case_id!r} (R39)"
        )

    effective_outcome: ImrOutcome | None = None
    if imr_requested:
        if ur.imr_outcome is not None:
            effective_outcome = ur.imr_outcome
        elif target_denial_date is not None:
            effective_outcome = _weighted_member(
                assertions_module._medical_story_rng(
                    seed,
                    "imr-outcome",
                    _medical_ur_stream_key(seed, target_denial_date),
                ),
                assertions_module.IMR_OUTCOME_WEIGHTS_WHEN_UNSTATED.value,
            )

    return MedicalUrPlan(
        effective_decision=effective_decision,
        decision_was_authored=decision_was_authored,
        imr_requested=imr_requested,
        imr_was_authored=imr_was_authored,
        effective_imr_outcome=effective_outcome,
    )


def resolve_imr_application_content(
    seed: CaseSeed,
    plan: MedicalUrPlan,
    *,
    target_denial_date: dt.date,
    medical_history: MedicalHistory | None,
    earlier_record_subtypes: Sequence[str],
    disputed_treatment: str,
) -> ImrApplicationContent | None:
    """Resolve R58's authored or sampled sparse application fields.

    This is structural content only.  Part 5/R90 owns the visible application
    register and exact prose; step 8 merely decides which existing fields are
    populated and binds them to the actual denial.  No grade or quality-like
    state is read or produced.
    """
    if not plan.imr_requested:
        return None
    ur = seed.lifecycle.ur_dispute
    if ur.imr_application is not None:
        entry = ur.imr_application
        return ImrApplicationContent(
            disputed_treatment=entry.disputed_treatment,
            diagnosis_icd10=entry.diagnosis_icd10,
            ur_determination_attached=entry.ur_determination_attached,
            supporting_record_subtypes=tuple(entry.supporting_record_subtypes),
            clinical_rebuttal=entry.clinical_rebuttal,
            mtus_citations=tuple(entry.mtus_citations),
            target_denial_subtype="MEDICAL_TREATMENT_DENIAL_UR",
            target_denial_date=target_denial_date,
        )

    from wc_caseload_engine import medical_assertions as assertions_module

    occupancy = assertions_module.IMR_APPLICATION_FIELD_OCCUPANCY.value

    def populated(field_name: str) -> bool:
        return _fraction_hit(
            assertions_module._medical_story_rng(
                seed,
                "imr-field-occupancy",
                _medical_ur_stream_key(seed, field_name),
            ),
            occupancy[field_name],
        )

    visible_diagnoses = tuple(
        condition
        for condition in (medical_history.surfaced_conditions() if medical_history else ())
        if condition.icd10
    )
    records = tuple(dict.fromkeys(earlier_record_subtypes))

    diagnosis_icd10 = None
    if visible_diagnoses and populated("diagnosis_icd10"):
        diagnosis_icd10 = visible_diagnoses[0].icd10

    support: tuple[str, ...] = ()
    if records and populated("supporting_record_subtypes"):
        count = _weighted_member(
            assertions_module._medical_story_rng(
                seed,
                "imr-field-count",
                _medical_ur_stream_key(seed, "supporting_record_subtypes"),
            ),
            assertions_module.SUPPORTING_RECORD_COUNT_WEIGHTS.value,
        )
        support = records[:count]

    rebuttal = None
    if populated("clinical_rebuttal"):
        case_specific = _fraction_hit(
            assertions_module._medical_story_rng(
                seed, "imr-rebuttal-substance", _medical_ur_stream_key(seed)
            ),
            assertions_module.P_IMR_CASE_SPECIFIC_REBUTTAL.value,
        )
        if case_specific and visible_diagnoses:
            rebuttal = (
                "The utilization-review determination does not account for "
                f"the documented {visible_diagnoses[0].label}."
            )
        else:
            rebuttal = (
                "Reconsideration of the utilization-review determination is requested."
            )

    # R58 makes MTUS occupancy eligible only when Part 5 supplies a grounded,
    # treatment-relevant citation.  Step 8 deliberately has no phrase pool, so
    # no citation is eligible yet and no occupancy/count draw occurs here.
    return ImrApplicationContent(
        disputed_treatment=(
            disputed_treatment if populated("disputed_treatment") else None
        ),
        diagnosis_icd10=diagnosis_icd10,
        ur_determination_attached=(
            True if populated("ur_determination_attached") else None
        ),
        supporting_record_subtypes=support,
        clinical_rebuttal=rebuttal,
        mtus_citations=(),
        target_denial_subtype="MEDICAL_TREATMENT_DENIAL_UR",
        target_denial_date=target_denial_date,
    )


# ---------------------------------------------------------------------------
# R33/R34 — contention-document planning (R77 step 6)
# ---------------------------------------------------------------------------
# ``plan_medical_story_documents()`` is the planner's single post-perspective /
# pre-control insertion point: it binds or adds the required opinion-report
# candidates, materializes every ContentionDocumentBinding as a DatedCandidate,
# fits communication dates around the hard opinion/explicit anchors, and
# re-fits the QME panel predecessors when binding moved the report date. It
# runs exactly once per plan, never draws randomness (every stochastic loop
# decision was completed in the R32 IDs-last derivation), and returns bound
# candidates plus nonfatal planning warnings. ``resolve_document_controls()``
# stays the only count resolver — this stage adds candidates, never counts.

#: R36's exact planning ranks for every contention-loop candidate.
CONTENTION_LOOP_PLANNING_RANKS: Mapping[str, tuple[str, int]] = {
    "opinion_report": (TRACK_CORE, 15),
    "objection": (TRACK_SUPPORTING, 25),
    "supplemental_request": (TRACK_SUPPORTING, 26),
    "supplemental_report": (TRACK_SUPPORTING, 27),
    "qme_deposition": (TRACK_SUPPORTING, 30),
    "advocacy": (TRACK_SUPPORTING, 35),
}

#: The internal candidate-metadata key R36 requires, and its two companions.
#: ``contention_loop_source`` is ``explicit | required_opinion | sampled``;
#: the id/kind keys let the reconciliation pass and the instance-selection
#: order identify a bound candidate without guessing from its subtype.
CONTENTION_LOOP_SOURCE_KEY = "contention_loop_source"
CONTENTION_BINDING_ID_KEY = "contention_binding_id"
CONTENTION_DOCUMENT_KIND_KEY = "contention_document_kind"

#: R36's warning prefix for every contention-loop planning/reconciliation note.
CONTENTION_LOOP_WARNING_PREFIX = "medical_story.contention_loop:"

#: The QME panel paperwork that must stay strictly before the first bound QME
#: base report (R34), in its causal order.
QME_PANEL_PREDECESSOR_SUBTYPES: tuple[str, ...] = (
    "QME_PANEL_REQUEST_FORM_105",
    "ORDER_APPOINTING_QME_PANEL",
)

_COMMUNICATION_SURFACES: Mapping[str, ContentionSurface] = {
    "advocacy": "advocacy",
    "objection": "objection",
    "supplemental_request": "supplemental_request",
    "qme_deposition": "qme_deposition",
}

_CHAIN_STAGE_RANK: Mapping[str, int] = {"objection": 0, "supplemental_request": 1}


@dataclass(frozen=True, slots=True)
class StoryDocumentPlanning:
    """What the R33 insertion point returns: candidates plus nonfatal warnings."""

    candidates: tuple[DatedCandidate, ...]
    warnings: tuple[str, ...] = ()


def _reuse_family(opinion: MedicalOpinion) -> frozenset[str] | None:
    """The R8 carrier family a required realization may reuse a slot from.

    ``None`` for depositions: R8 forbids rewriting ordinary applicant,
    employer or witness depositions, so a walk-proposed
    ``DEPOSITION_TRANSCRIPT`` is never "compatible" with a QME/AME deposition
    event — the realization always adds its own bound candidate instead.
    """
    if opinion.event_kind == "base_report":
        if opinion.author_role == "ptp":
            return PTP_CAUSATION_SURFACES
        return INITIAL_MEDLEGAL_SURFACES | PSYCH_MEDLEGAL_SURFACES
    if opinion.event_kind == "supplemental_report":
        return SUPPLEMENTAL_MEDLEGAL_SURFACES
    return None


def _is_loop_bound(candidate: DatedCandidate) -> bool:
    """Whether *candidate* already belongs to the contention loop."""
    return (
        CONTENTION_LOOP_SOURCE_KEY in candidate.metadata
        or candidate.medical_opinion_id is not None
    )


def _bound_author_role(binding: ContentionDocumentBinding) -> str:
    """R35 author identity for a bound candidate.

    Reports speak in the evaluator's voice, a deposition transcript's base
    document author is the court reporter (the examining party stays visible
    through ``contention_actor_party``), and a communication is authored by
    its actor's attorney.
    """
    if binding.document_kind in ("opinion_report", "supplemental_report"):
        return ROLE_PHYSICIAN
    if binding.document_kind == "qme_deposition":
        return ROLE_COURT_REPORTER
    return f"{binding.actor_party}_attorney"


def _bound_candidate(
    binding: ContentionDocumentBinding,
    doc_date: dt.date,
    base: DatedCandidate | None,
) -> DatedCandidate:
    """One binding materialized as a fully bound :class:`DatedCandidate`.

    *base* is the reused lifecycle slot for a required realization — its
    stage and any pre-existing metadata ride along — or ``None`` when the
    binding adds a fresh candidate.
    """
    track, priority = CONTENTION_LOOP_PLANNING_RANKS[binding.document_kind]
    surface = (
        _COMMUNICATION_SURFACES.get(binding.document_kind)
        if binding.document_kind != "supplemental_report"
        else None
    )
    metadata = {
        **(base.metadata if base is not None else {}),
        CONTENTION_LOOP_SOURCE_KEY: binding.source,
        CONTENTION_BINDING_ID_KEY: binding.id,
        CONTENTION_DOCUMENT_KIND_KEY: binding.document_kind,
    }
    assert binding.subtype is not None  # resolved by the R32 derivation
    return DatedCandidate(
        subtype=binding.subtype,
        doc_date=doc_date,
        track=track,
        priority=priority,
        author_role=_bound_author_role(binding),
        stage=base.stage if base is not None else "contention_loop",
        metadata=metadata,
        medical_opinion_id=binding.medical_opinion_id,
        spoken_contention_ids=binding.spoken_contention_ids,
        contention_surface=surface,
        template_subtype=binding.template_subtype,
        target_medical_opinion_id=binding.target_medical_opinion_id,
        contention_actor_party=binding.actor_party,
        defense_contest_theories=binding.defense_contest_theories,
        medical_story_render_key=binding.semantic_key,
    )


def _reusable_slot(
    candidates: Sequence[DatedCandidate],
    opinion: MedicalOpinion,
) -> int | None:
    """The compatible, still-unbound lifecycle slot for *opinion*, if any.

    Deterministic: the earliest-dated compatible candidate, ties broken by
    subtype then list position. Reusing (rather than appending beside) the
    walk's own report candidate is what keeps R27's "one opinion event, one
    report" — the slot is rewritten to the required canonical subtype and the
    opinion's hard report date, so no second unbound lifecycle report is left
    representing the same opinion event.
    """
    family = _reuse_family(opinion)
    if family is None:
        return None
    best: tuple[dt.date, str, int] | None = None
    for index, candidate in enumerate(candidates):
        if _is_loop_bound(candidate) or candidate.subtype not in family:
            continue
        key = (candidate.doc_date, candidate.subtype, index)
        if best is None or key < best:
            best = key
    return best[2] if best is not None else None


def _binding_label(binding: ContentionDocumentBinding) -> str:
    """The ids R34 failures must name: the ``cdoc-*`` and any ``opn-*`` refs."""
    refs = [binding.id]
    if binding.medical_opinion_id is not None:
        refs.append(binding.medical_opinion_id)
    if binding.target_medical_opinion_id is not None:
        refs.append(binding.target_medical_opinion_id)
    return "/".join(refs)


@dataclass(slots=True)
class _ChainFit:
    """One open contest chain during date fitting."""

    members: list[ContentionDocumentBinding]
    ceiling: dt.date | None = None
    ceiling_id: str | None = None


@dataclass(slots=True)
class _ChainFitState:
    """The shared mutable state one date-resolution pass accumulates."""

    horizon: dt.date
    resolved: dict[str, dt.date]
    dropped: set[str]
    warnings: list[str]


def _place_soft_date(
    binding: ContentionDocumentBinding,
    fitted: dt.date,
    lo: dt.date,
    hi: dt.date,
    used: set[dt.date],
    floor_date: dt.date | None,
    resolved: dict[str, dt.date],
) -> dt.date | None:
    """Land one soft date, bumping deterministically off claimed dates.

    ``None`` means a sampled document found no free strict slot; an explicit
    one in that position fails instead (R34).
    """
    day = dt.timedelta(days=1)
    value = max(fitted, lo)
    if floor_date is not None and value <= floor_date:
        value = floor_date + day
    while value in used and value <= hi:
        value += day
    if value > hi:
        if binding.source != "sampled":
            raise MedicalAssertionError(
                f"explicit contention document '{_binding_label(binding)}' "
                f"cannot land strictly inside {lo.isoformat()} .. "
                f"{hi.isoformat()} without sharing a date with a related "
                "event; restate the authored dates (R34)"
            )
        return None
    used.add(value)
    resolved[binding.id] = value
    return value


def _flush_chain_run(
    run: list[ContentionDocumentBinding],
    previous: dt.date,
    next_hard: dt.date | None,
    chain: _ChainFit,
    key: tuple[str | None, str | None],
    used: set[dt.date],
    state: _ChainFitState,
) -> dt.date:
    """Fit one contiguous soft run of chain communications between anchors.

    The run's segment is ``(previous, next_hard)`` exclusive — or the horizon
    when no later hard anchor exists. A sampled run that cannot fit truncates
    without redraw (R31); an explicit member fails with its ids; and a
    truncation need arising under an attached supplemental ceiling is an
    engine-coherence failure, because the R32 derivation guarantees at least
    47 days of runway ahead of every sampled supplemental report.
    """
    if not run:
        return previous
    day = dt.timedelta(days=1)
    lo = previous + day
    hi = (next_hard - day) if next_hard is not None else state.horizon
    span = (hi - lo).days + 1
    keep = run
    if span < len(run):
        infeasible = run[max(span, 0) :]
        explicit = [b for b in infeasible if b.source != "sampled"]
        if explicit:
            raise MedicalAssertionError(
                "explicit contention documents "
                + ", ".join(f"'{_binding_label(b)}'" for b in explicit)
                + " cannot satisfy the strict chain ordering inside "
                f"{lo.isoformat()} .. {hi.isoformat()} (R34); restate "
                "the authored dates"
            )
        if chain.ceiling is not None:
            raise MedicalAssertionError(
                "contention chain toward opinion "
                f"'{key[1]}' cannot hold its sampled communications "
                "before its supplemental report; the R32 derivation "
                "must not have committed this chain"
            )
        for binding in infeasible:
            state.dropped.add(binding.id)
            state.warnings.append(
                f"{CONTENTION_LOOP_WARNING_PREFIX} sampled "
                f"{binding.document_kind} '{binding.id}' targeting "
                f"opinion '{binding.target_medical_opinion_id}' cannot "
                "fit strictly inside the case window; the chain tail "
                "is truncated without redraw (R31/R34)"
            )
        keep = run[: max(span, 0)]
    if not keep:
        return previous
    fitted = fit_dates(
        [binding.proposed_date or lo for binding in keep],
        floor=lo,
        ceiling=hi,
        label=f"medical-story:chain:{key[0]}:{key[1]}",
    )
    landed_previous = previous
    for binding, when in zip(keep, fitted, strict=True):
        landed = _place_soft_date(
            binding, when, lo, hi, used, landed_previous, state.resolved
        )
        if landed is None:
            state.dropped.add(binding.id)
            state.warnings.append(
                f"{CONTENTION_LOOP_WARNING_PREFIX} sampled "
                f"{binding.document_kind} '{binding.id}' has no free "
                "date inside its chain segment; the chain tail is "
                "truncated without redraw (R31/R34)"
            )
            continue
        landed_previous = landed
    return landed_previous


def _resolve_contention_dates(
    timeline: CaseTimeline,
    bindings: Sequence[ContentionDocumentBinding],
    opinions: Mapping[str, MedicalOpinion],
) -> tuple[dict[str, dt.date], set[str], list[str]]:
    """R34 — one resolved date per binding, hard anchors preserved exactly.

    Hard opinion report dates and explicitly seeded ``doc_date`` values are
    never moved by fitting, and no contention-chain date ever goes through
    per-document ``timeline.clamp()``: soft communication dates are fitted
    with :func:`~wc_caseload_engine.lifecycle_bridge.fit_dates` on the
    available segment between their hard anchors, inside the overall
    ``injury_date + 1 .. horizon`` window. A sampled communication that
    cannot fit strictly truncates its chain tail without redraw (R31); an
    explicit sequence that cannot fit fails, naming the involved ``cdoc-*``
    and ``opn-*`` ids.

    Returns ``(resolved, dropped, warnings)``.
    """
    window_floor = timeline.injury_date + dt.timedelta(days=1)
    horizon = timeline.horizon
    day = dt.timedelta(days=1)
    warnings: list[str] = []
    dropped: set[str] = set()
    resolved: dict[str, dt.date] = {}
    state = _ChainFitState(
        horizon=horizon, resolved=resolved, dropped=dropped, warnings=warnings
    )

    for binding in bindings:
        if binding.medical_opinion_id is not None:
            resolved[binding.id] = (
                binding.doc_date
                if binding.doc_date is not None
                else opinions[binding.medical_opinion_id].report_date
            )
        elif binding.doc_date is not None:
            resolved[binding.id] = binding.doc_date

    realization_date: dict[str, dt.date] = {
        binding.medical_opinion_id: resolved[binding.id]
        for binding in bindings
        if binding.medical_opinion_id is not None
    }

    def target_date(binding: ContentionDocumentBinding) -> dt.date:
        target = binding.target_medical_opinion_id
        if target is None or target not in realization_date:
            raise MedicalAssertionError(
                f"contention document '{_binding_label(binding)}' targets an "
                "opinion with no bound report realization; the loop cannot "
                "date a communication around a report that does not exist"
            )
        return realization_date[target]

    # Dates already claimed around each target opinion: its own report plus
    # every hard-dated document aimed at it. "No related events may share a
    # date" (R34) is enforced against this set as soft dates land.
    used_by_target: dict[str, set[dt.date]] = {}
    for binding in bindings:
        target = binding.target_medical_opinion_id
        if target is None:
            continue
        used = used_by_target.setdefault(target, set())
        if target in realization_date:
            used.add(realization_date[target])
        if binding.id in resolved:
            used.add(resolved[binding.id])

    # --- standalone advocacy letters: fitted per target, before the report --
    letters_by_target: dict[str, list[ContentionDocumentBinding]] = {}
    for binding in bindings:
        if binding.document_kind == "advocacy" and binding.id not in resolved:
            letters_by_target.setdefault(
                binding.target_medical_opinion_id or "", []
            ).append(binding)
    for target, letters in letters_by_target.items():
        anchor = target_date(letters[0])
        lo, hi = window_floor, anchor - day
        used = used_by_target.setdefault(target, set())
        ordered = sorted(
            letters, key=lambda b: (b.proposed_date or lo, b.id)
        )
        span = (hi - lo).days + 1
        keep = ordered
        if span < len(ordered):
            infeasible = ordered[max(span, 0) :]
            explicit = [b for b in infeasible if b.source != "sampled"]
            if explicit:
                raise MedicalAssertionError(
                    "explicit advocacy "
                    + ", ".join(f"'{_binding_label(b)}'" for b in explicit)
                    + f" cannot precede its target report of {anchor.isoformat()} "
                    "inside the case window (R34); move the report later or "
                    "drop the letter"
                )
            for binding in infeasible:
                dropped.add(binding.id)
                warnings.append(
                    f"{CONTENTION_LOOP_WARNING_PREFIX} sampled advocacy "
                    f"'{binding.id}' targeting opinion "
                    f"'{binding.target_medical_opinion_id}' cannot precede the "
                    f"report of {anchor.isoformat()} inside the case window; "
                    "the letter is truncated without redraw (R31/R34) — move "
                    "the opinion later to keep it"
                )
            keep = ordered[: max(span, 0)]
        if not keep:
            continue
        fitted = fit_dates(
            [binding.proposed_date or lo for binding in keep],
            floor=lo,
            ceiling=hi,
            label=f"medical-story:advocacy:{target}",
        )
        previous: dt.date | None = None
        for binding, when in zip(keep, fitted, strict=True):
            landed = _place_soft_date(binding, when, lo, hi, used, previous, resolved)
            if landed is None:
                dropped.add(binding.id)
                warnings.append(
                    f"{CONTENTION_LOOP_WARNING_PREFIX} sampled advocacy "
                    f"'{binding.id}' has no free date before the report of "
                    f"{anchor.isoformat()}; truncated without redraw (R31/R34)"
                )
                continue
            previous = landed

    # --- contest chains: soft objection/request runs between hard anchors --
    chains: dict[tuple[str | None, str | None], _ChainFit] = {}
    order: list[tuple[str | None, str | None]] = []
    for binding in bindings:
        kind = binding.document_kind
        if kind in _CHAIN_STAGE_RANK:
            key = (binding.actor_party, binding.target_medical_opinion_id)
            if key not in chains:
                chains[key] = _ChainFit(members=[])
                order.append(key)
            chains[key].members.append(binding)
        elif kind == "supplemental_report":
            # The resulting supplemental closes the most recent chain on the
            # same predecessor that carries a request and no ceiling yet —
            # chunk stages are committed contiguously, so this pairing is the
            # chain's own S, never a sibling chain's.
            for key in reversed(order):
                chain = chains[key]
                if key[1] != binding.target_medical_opinion_id:
                    continue
                if chain.ceiling is not None:
                    continue
                if not any(
                    member.document_kind == "supplemental_request"
                    for member in chain.members
                ):
                    continue
                chain.ceiling = resolved[binding.id]
                chain.ceiling_id = binding.id
                break

    for key in order:
        chain = chains[key]
        members = sorted(
            enumerate(chain.members),
            key=lambda item: (_CHAIN_STAGE_RANK[item[1].document_kind], item[0]),
        )
        target = key[1] or ""
        anchor = target_date(chain.members[0])
        used = used_by_target.setdefault(target, set())
        previous = anchor
        run: list[ContentionDocumentBinding] = []

        for _position, member in members:
            if member.id in resolved:  # an authored hard interior anchor
                previous = _flush_chain_run(
                    run, previous, resolved[member.id], chain, key, used, state
                )
                run = []
                hard = resolved[member.id]
                if hard <= previous:
                    raise MedicalAssertionError(
                        f"explicit contention document '{_binding_label(member)}' "
                        f"dated {hard.isoformat()} does not strictly follow its "
                        f"predecessor event of {previous.isoformat()} (R34)"
                    )
                previous = hard
            else:
                run.append(member)
        _flush_chain_run(run, previous, chain.ceiling, chain, key, used, state)

    return resolved, dropped, warnings


def _verify_contention_chronology(
    timeline: CaseTimeline,
    bindings: Sequence[ContentionDocumentBinding],
    opinions: Mapping[str, MedicalOpinion],
    resolved: Mapping[str, dt.date],
    dropped: set[str],
) -> None:
    """R34's strict-edge and window verification over the resolved dates.

    Every violation is fatal and names the involved ``cdoc-*``/``opn-*`` ids:
    an explicit sequence that cannot satisfy the constraints must fail, and a
    sampled one reaching here would be an engine bug — silent incoherence is
    the one outcome this pass exists to remove.
    """
    window_floor = timeline.injury_date + dt.timedelta(days=1)
    horizon = timeline.horizon
    problems: list[str] = []
    live = [b for b in bindings if b.id not in dropped]
    realization_date = {
        b.medical_opinion_id: resolved[b.id]
        for b in live
        if b.medical_opinion_id is not None
    }
    for binding in live:
        when = resolved[binding.id]
        if not window_floor <= when <= horizon:
            problems.append(
                f"'{_binding_label(binding)}' lands on {when.isoformat()}, "
                f"outside the {window_floor.isoformat()} .. "
                f"{horizon.isoformat()} window"
            )
        target = binding.target_medical_opinion_id
        anchor = realization_date.get(target) if target is not None else None
        if anchor is None:
            continue
        if binding.document_kind == "advocacy" and when >= anchor:
            problems.append(
                f"advocacy '{_binding_label(binding)}' does not strictly "
                f"precede its target report of {anchor.isoformat()}"
            )
        if (
            binding.document_kind
            in ("objection", "supplemental_request", "qme_deposition", "supplemental_report")
            and when <= anchor
        ):
            problems.append(
                f"{binding.document_kind} '{_binding_label(binding)}' does not "
                f"strictly follow its target report of {anchor.isoformat()}"
            )
    # Same-chain ordering: objection < supplemental request.
    for binding in live:
        if binding.document_kind != "supplemental_request":
            continue
        for other in live:
            if (
                other.document_kind == "objection"
                and other.actor_party == binding.actor_party
                and other.target_medical_opinion_id
                == binding.target_medical_opinion_id
                and resolved[other.id] >= resolved[binding.id]
            ):
                problems.append(
                    f"objection '{_binding_label(other)}' does not strictly "
                    f"precede its supplemental request '{binding.id}'"
                )
    if problems:
        raise MedicalAssertionError(
            "medical-story chronology cannot be satisfied (R34):\n  "
            + "\n  ".join(problems)
        )


def _refit_qme_panel_predecessors(
    timeline: CaseTimeline,
    candidates: list[DatedCandidate],
    first_bound_qme: dt.date,
) -> list[str]:
    """R34 — keep the panel request and order strictly before the bound report.

    The walk dated the panel chain against its own drawn report date; binding
    rewrites that slot to ``MedicalOpinion.report_date``, so the predecessors
    are re-fitted before the new hard anchor whenever they no longer precede
    it. Already-ordered paperwork is left untouched.
    """
    positions = [
        index
        for index, candidate in enumerate(candidates)
        if candidate.subtype in QME_PANEL_PREDECESSOR_SUBTYPES
        and not _is_loop_bound(candidate)
    ]
    if not positions or all(
        candidates[index].doc_date < first_bound_qme for index in positions
    ):
        return []
    causal = sorted(
        positions,
        key=lambda index: (
            QME_PANEL_PREDECESSOR_SUBTYPES.index(candidates[index].subtype),
            candidates[index].doc_date,
            index,
        ),
    )
    floor = timeline.injury_date + dt.timedelta(days=1)
    ceiling = first_bound_qme - dt.timedelta(days=1)
    fitted = fit_dates(
        [candidates[index].doc_date for index in causal],
        floor=floor,
        ceiling=ceiling,
        label="medical-story:qme-panel-refit",
    )
    for index, when in zip(causal, fitted, strict=True):
        candidates[index] = replace(candidates[index], doc_date=when)
    warnings: list[str] = []
    if (ceiling - floor).days + 1 < len(causal):
        warnings.append(
            f"{CONTENTION_LOOP_WARNING_PREFIX} the QME panel request and order "
            f"cannot all sit strictly before the bound report of "
            f"{first_bound_qme.isoformat()}; the window saturated — move the "
            "opinion later to keep the panel chain strictly ordered"
        )
    return warnings


def plan_medical_story_documents(
    seed: CaseSeed,
    timeline: CaseTimeline,
    plan: MedicalAssertionPlan,
    candidates: Sequence[DatedCandidate],
) -> StoryDocumentPlanning:
    """R33 — bind and add the contention-document candidates, exactly once.

    Receives the already perspective-resolved candidate list; loop candidates
    never pass through ``apply_perspective()`` a second time, and the
    applicant-only advocacy weights keep governing unbound legacy proposals
    only. On the medical-story-absent path this returns the input untouched
    and constructs nothing — no RNG, no binding, no warning, no byte.
    """
    out = list(candidates)
    if seed.scenario.medical_history is None:
        return StoryDocumentPlanning(candidates=tuple(out))
    bindings = plan.contention_documents
    if not bindings or plan.ledger is None:
        return StoryDocumentPlanning(candidates=tuple(out))

    opinions = {opinion.id: opinion for opinion in plan.ledger.medical_opinions}
    resolved, dropped, warnings = _resolve_contention_dates(
        timeline, bindings, opinions
    )
    _verify_contention_chronology(timeline, bindings, opinions, resolved, dropped)

    for binding in bindings:
        if binding.id in dropped:
            continue
        doc_date = resolved[binding.id]
        if binding.medical_opinion_id is not None:
            opinion = opinions[binding.medical_opinion_id]
            slot = _reusable_slot(out, opinion)
            if slot is not None:
                out[slot] = _bound_candidate(binding, doc_date, out[slot])
                continue
        out.append(_bound_candidate(binding, doc_date, None))

    bound_qme_bases = [
        resolved[binding.id]
        for binding in bindings
        if binding.id not in dropped
        and binding.medical_opinion_id is not None
        and opinions[binding.medical_opinion_id].event_kind == "base_report"
        and opinions[binding.medical_opinion_id].author_role == "qme"
    ]
    if bound_qme_bases:
        warnings = list(warnings) + _refit_qme_panel_predecessors(
            timeline, out, min(bound_qme_bases)
        )

    return StoryDocumentPlanning(candidates=tuple(out), warnings=tuple(warnings))


# ---------------------------------------------------------------------------
# R4/R5/R10 — derive_medical_story(): the pure, label-free document projection
# (R77 step 7)
# ---------------------------------------------------------------------------
# Runs after the final document tuple is dated, controlled, perspective-
# resolved, sorted and indexed (R3). It is a pure projection: no RNG, no
# ledger mutation, no draw. Content is resolved from the explicit R5/R35
# bindings only — never a nearest date, report ordinal, subtype coincidence
# or collection order — and every projection below uses an explicit field
# allowlist so a future truth-only field cannot leak by default (R4).

#: R2/R35 — the exact canonical-manifest-carrier / internal-template pair per
#: governed contention communication surface. The FIRST member of each pair is
#: what ``manifest.json``, filenames and controls see; the SECOND is internal
#: render state that resolves the registered substrate variant. The order is
#: load-bearing: swapping a pair would put a substrate-only registry key into
#: the manifest vocabulary, which is the one thing the manifest promises never
#: to contain.
CONTENTION_SURFACE_TEMPLATE_PAIRS: Mapping[ContentionSurface, tuple[str, str]] = {
    "objection": ("ADVOCACY_LETTERS_PTP_QME_AME", "OBJECTION_TO_QME_AME_REPORT"),
    "supplemental_request": (
        "ADVOCACY_LETTERS_PTP_QME_AME",
        "REQUEST_SUPPLEMENTAL_QME_AME_REPORT",
    ),
    "qme_deposition": ("DEPOSITION_TRANSCRIPT", "DEPOSITION_TRANSCRIPT_QME_AME"),
}

#: R10 — the parent types whose earlier planned documents a governed report's
#: records review may cite. ``cadence_anchors`` remains untouched; expanding
#: ``CADENCE_ANCHOR_SUBTYPES`` would alter attorney-letter timing (R10).
RECORD_REFERENCE_PARENT_TYPES: frozenset[str] = frozenset(
    {"MEDICAL_CLINICAL", "MEDICAL_LEGAL"}
)

_REPORT_SURFACE_SETS: tuple[frozenset[str], ...] = (
    INITIAL_MEDLEGAL_SURFACES,
    PSYCH_MEDLEGAL_SURFACES,
    SUPPLEMENTAL_MEDLEGAL_SURFACES,
    PTP_CAUSATION_SURFACES,
)


def _is_governed_document(document: PlannedDocument) -> bool:
    """Whether *document* is an R8 medical-story surface.

    Report surfaces are governed whenever the gate is open — a history-present
    case gets history-only expression on them even without a bound opinion
    (R1). Communications are governed only through their bound
    ``contention_surface``: an unbound legacy advocacy letter and an ordinary
    applicant/employer/witness deposition keep their exact pre-M3 path (R8).
    """
    if any(document.subtype in surface_set for surface_set in _REPORT_SURFACE_SETS):
        return True
    if document.subtype in ADVOCACY_LETTER_SURFACES:
        return document.contention_surface in (
            "advocacy",
            "objection",
            "supplemental_request",
        )
    if document.subtype == "DEPOSITION_TRANSCRIPT":
        return document.contention_surface == "qme_deposition"
    return False


def _project_demographics(demographics: ApplicantDemographics) -> StoryDemographics:
    """R4 — the explicit demographic allowlist."""
    return StoryDemographics(
        age=demographics.age,
        sex=demographics.sex,
        bmi_band=demographics.bmi_band,
        smoking_status=demographics.smoking_status,
    )


def _project_condition(condition: MedicalCondition) -> StoryCondition:
    """R4 — the explicit condition allowlist.

    Deliberately narrower than the world record: no ``causal_ground_truth``,
    no ``wholly_unrelated``, no ``surfaces_in_file``, no world
    ``psych_injury_kind`` — visibility is decided by the projector and causal
    truth never reaches a document.
    """
    return StoryCondition(
        id=condition.id,
        label=condition.label,
        body_system=condition.body_system,
        body_part=condition.body_part,
        icd10=condition.icd10,
        onset=condition.onset,
        severity=condition.severity,
        trajectory=condition.trajectory,
        symptomatic_before_doi=condition.symptomatic_before_doi,
        billing_coded=condition.billing_coded,
    )


def _project_prior_claim(claim: PriorClaim) -> StoryPriorClaim:
    """R4 — the explicit prior-claim allowlist."""
    return StoryPriorClaim(
        id=claim.id,
        date_of_injury=claim.date_of_injury,
        body_parts=claim.body_parts,
        resolution_type=claim.resolution_type,
    )


def _project_prior_award(award: PriorAward, prior_claim_id: str) -> StoryPriorAward:
    """R4 — the explicit prior-award allowlist."""
    return StoryPriorAward(
        id=award.id,
        prior_claim_id=prior_claim_id,
        body_parts=award.body_parts,
        pd_percent=award.pd_percent,
        award_date=award.award_date,
        resolution_type=award.resolution_type,
        conclusively_presumed=award.still_exists_conclusively_presumed,
    )


def _project_contention(contention: Contention) -> StoryContention:
    """R4 — the explicit contention allowlist: every semantic field, never
    ``quality``."""
    return StoryContention(
        id=contention.id,
        claim_type=contention.claim_type,
        party=contention.party,
        position=contention.position,
        target_condition_id=contention.target_condition_id,
        target_prior_claim_id=contention.target_prior_claim_id,
        target_prior_award_id=contention.target_prior_award_id,
        target_body_part=contention.target_body_part,
        doctrine_hooks=contention.doctrine_hooks,
        rationale=contention.rationale,
        treatment_causation=contention.treatment_causation,
        requested_apportionment=contention.requested_apportionment,
        groundings=contention.groundings,
        psych_injury_kind=contention.psych_injury_kind,
    )


def _project_opinion(opinion: MedicalOpinion) -> StoryMedicalOpinion:
    """R4 — the explicit opinion-projection allowlist.

    Every semantic ``MedicalOpinion`` field, stated literally, and never
    ``quality``: an unrestricted ``model_dump()`` followed by removal would
    let a future truth-only field leak by default, which is exactly the
    failure mode this block exists to make impossible.
    """
    return StoryMedicalOpinion(
        id=opinion.id,
        author_role=opinion.author_role,
        report_stage=opinion.report_stage,
        report_date=opinion.report_date,
        apportionment_state=opinion.apportionment_state,
        determination_kind=opinion.determination_kind,
        determination_rationale=opinion.determination_rationale,
        examination_performed=opinion.examination_performed,
        reviewed_condition_ids=opinion.reviewed_condition_ids,
        reviewed_prior_claim_ids=opinion.reviewed_prior_claim_ids,
        reviewed_prior_award_ids=opinion.reviewed_prior_award_ids,
        endorses_contention_ids=opinion.endorses_contention_ids,
        concurs_with_contention_ids=opinion.concurs_with_contention_ids,
        rejects_contention_ids=opinion.rejects_contention_ids,
        defers_contention_ids=opinion.defers_contention_ids,
        responds_to_opinion_id=opinion.responds_to_opinion_id,
        supersedes_opinion_id=opinion.supersedes_opinion_id,
        rationale=opinion.rationale,
        revision_rationale=opinion.revision_rationale,
        event_kind=opinion.event_kind,
        revision_kind=opinion.revision_kind,
        psych_injury_kind=opinion.psych_injury_kind,
        aoe_coe_finding=opinion.aoe_coe_finding,
        aoe_coe_rationale=opinion.aoe_coe_rationale,
    )


def _project_apportionment(assertion: ApportionmentAssertion) -> StoryApportionment:
    """R4 — the explicit apportionment allowlist: every semantic field, never
    ``quality``."""
    return StoryApportionment(
        id=assertion.id,
        opinion_id=assertion.opinion_id,
        body_part=assertion.body_part,
        industrial_percent=assertion.industrial_percent,
        nonindustrial_percent=assertion.nonindustrial_percent,
        basis_kinds=assertion.basis_kinds,
        condition_ids=assertion.condition_ids,
        prior_claim_ids=assertion.prior_claim_ids,
        prior_award_ids=assertion.prior_award_ids,
        description=assertion.description,
        disability_causation_stated=assertion.disability_causation_stated,
        reasonable_medical_probability=assertion.reasonable_medical_probability,
        causal_rationale=assertion.causal_rationale,
        percentage_rationale=assertion.percentage_rationale,
        prior_award_analysis=assertion.prior_award_analysis,
        revised_from_percent=assertion.revised_from_percent,
        revision_rationale=assertion.revision_rationale,
        psych_exception_analysis=assertion.psych_exception_analysis,
        linked_contention_id=assertion.linked_contention_id,
        groundings=assertion.groundings,
    )


def _record_reference(document: PlannedDocument) -> StoryRecordReference:
    """One actual earlier planned document, as a report may cite it (R10)."""
    return StoryRecordReference(
        document_index=document.index,
        subtype=document.subtype,
        title=document.title,
        doc_date=document.doc_date,
        author_role=document.author_role,
    )


def _document_label(document: PlannedDocument) -> str:
    return f"planned document {document.index} ({document.subtype})"


def _check_condition_exposure(
    document: PlannedDocument,
    history: MedicalHistory,
    opinion: MedicalOpinion | None,
    contentions: Sequence[Contention],
    apportionments: Sequence[ApportionmentAssertion],
) -> None:
    """R4 — a bound assertion must not expose a hidden world condition.

    A condition enters a document projection only by surfacing in the file. A
    bound assertion whose reference would put a ``surfaces_in_file=False``
    condition on the page is internally incoherent and fails here, before
    rendering; the projector never silently mutates the world ledger to make
    the reference true.
    """
    referenced: list[tuple[str, str]] = []
    if opinion is not None:
        referenced.extend(
            (ref, f"medical opinion '{opinion.id}' reviewed_condition_ids")
            for ref in opinion.reviewed_condition_ids
        )
    for contention in contentions:
        if contention.target_condition_id is not None:
            referenced.append(
                (
                    contention.target_condition_id,
                    f"contention '{contention.id}' target_condition_id",
                )
            )
    for assertion in apportionments:
        referenced.extend(
            (ref, f"apportionment assertion '{assertion.id}' condition_ids")
            for ref in assertion.condition_ids
        )
    for ref, via in referenced:
        condition = history.condition(ref)
        if condition is None:
            raise MedicalAssertionError(
                f"{_document_label(document)} binds a condition reference "
                f"'{ref}' (via {via}) that does not exist in the world ledger; "
                "the projection fails closed rather than render a dangling "
                "reference (R4)"
            )
        if not condition.surfaces_in_file:
            raise MedicalAssertionError(
                f"{_document_label(document)} would expose condition '{ref}' "
                f"(via {via}) while its world record says "
                "surfaces_in_file=false; a bound assertion that exposes a "
                "hidden condition is internally incoherent, and the projector "
                "never mutates the world ledger to repair it (R4)"
            )


def _verify_surface_carrier(document: PlannedDocument) -> None:
    """R2/R35 — a governed communication rides its exact carrier pair."""
    surface = document.contention_surface
    if surface in CONTENTION_SURFACE_TEMPLATE_PAIRS:
        carrier, template = CONTENTION_SURFACE_TEMPLATE_PAIRS[surface]
        if document.subtype != carrier or document.template_subtype != template:
            raise MedicalAssertionError(
                f"{_document_label(document)} carries surface '{surface}' with "
                f"carrier '{document.subtype}' / template "
                f"'{document.template_subtype}'; the frozen pair is "
                f"('{carrier}', '{template}') — the canonical carrier is the "
                "manifest vocabulary and the template subtype is internal "
                "dispatch, never the reverse (R2/R35)"
            )
    elif surface == "advocacy":
        if (
            document.subtype not in ADVOCACY_LETTER_SURFACES
            or document.template_subtype != document.subtype
        ):
            raise MedicalAssertionError(
                f"{_document_label(document)} carries surface 'advocacy' with "
                f"carrier '{document.subtype}' / template "
                f"'{document.template_subtype}'; an advocacy letter rides a "
                "registered advocacy carrier whose template subtype is the "
                "same registered subtype (R2/R35)"
            )


def derive_medical_story(
    seed: CaseSeed,
    history: MedicalHistory | None,
    ledger: MedicalAssertionLedger | None,
    documents: Sequence[PlannedDocument],
) -> MedicalStoryPlan | None:
    """R4 — the label-free, visibility-limited story every governed document tells.

    The medical-story gate is ``scenario.medical_history`` (R1): when it is
    absent this returns ``None`` before constructing any projection, and the
    plan carries ``medical_story=None``. History-present/assertions-absent
    cases receive history-only projections on the R8 report surfaces — no
    contention prose, no governed apportionment, no bound opinion.

    Pure. No RNG, no mutation, no draw: rendering must be a function of the
    completed plan (R3).
    """
    if seed.scenario.medical_history is None:
        return None
    if history is None:  # pragma: no cover - the planner derives both together
        raise MedicalAssertionError(
            "the medical-story gate is open but no MedicalHistory was derived; "
            "derive_medical_story() requires the world ledger the seed asked for"
        )

    opinions: dict[str, MedicalOpinion] = {}
    contentions: dict[str, Contention] = {}
    if ledger is not None:
        opinions = {opinion.id: opinion for opinion in ledger.medical_opinions}
        contentions = {contention.id: contention for contention in ledger.contentions}

    realization_by_opinion: dict[str, PlannedDocument] = {}
    for document in documents:
        if document.medical_opinion_id is not None:
            realization_by_opinion.setdefault(document.medical_opinion_id, document)

    demographics = _project_demographics(history.demographics)
    visible_conditions = tuple(
        _project_condition(condition) for condition in history.surfaced_conditions()
    )
    prior_claims = tuple(
        _project_prior_claim(claim) for claim in history.prior_claims
    )
    prior_awards = tuple(
        _project_prior_award(claim.award, claim.id)
        for claim in history.prior_claims
        if claim.award is not None
    )

    medical_record_documents = [
        document
        for document in documents
        if document.parent_type in RECORD_REFERENCE_PARENT_TYPES
    ]

    stories: dict[int, DocumentMedicalStory] = {}
    for document in documents:
        if not _is_governed_document(document):
            continue
        _verify_surface_carrier(document)

        opinion: MedicalOpinion | None = None
        if document.medical_opinion_id is not None:
            opinion = opinions.get(document.medical_opinion_id)
            if opinion is None:
                # R5 — an explicit binding is the only basis for content.
                # This failure is the boundary: a dangling opinion ID must
                # never be repaired by choosing the opinion with the nearest
                # report date, a report ordinal, a subtype coincidence or
                # collection order.
                raise MedicalAssertionError(
                    f"{_document_label(document)} binds medical opinion "
                    f"'{document.medical_opinion_id}', which does not exist in "
                    "the completed ledger; a missing or unbound opinion ID "
                    "fails instead of guessing by date (R5)"
                )

        spoken: list[Contention] = []
        for contention_id in document.spoken_contention_ids:
            contention = contentions.get(contention_id)
            if contention is None:
                raise MedicalAssertionError(
                    f"{_document_label(document)} speaks contention "
                    f"'{contention_id}', which does not exist in the completed "
                    "ledger; the story is resolved from explicit bindings only "
                    "(R5)"
                )
            spoken.append(contention)

        apportionments: tuple[ApportionmentAssertion, ...] = ()
        if opinion is not None and ledger is not None:
            apportionments = ledger.assertions_of(opinion.id)

        _check_condition_exposure(document, history, opinion, spoken, apportionments)

        preceding_report: StoryRecordReference | None = None
        target_id = document.target_medical_opinion_id
        if target_id is not None and document.contention_surface != "advocacy":
            if target_id not in opinions:
                raise MedicalAssertionError(
                    f"{_document_label(document)} targets medical opinion "
                    f"'{target_id}', which does not exist in the completed "
                    "ledger (R5/R35)"
                )
            target_document = realization_by_opinion.get(target_id)
            if target_document is None:
                raise MedicalAssertionError(
                    f"{_document_label(document)} targets medical opinion "
                    f"'{target_id}', whose report realization is absent from "
                    "the final plan; a chain dependent must have been removed "
                    "by reconciliation rather than left citing a document "
                    "that does not exist (R35/R36)"
                )
            preceding_report = _record_reference(target_document)

        references = tuple(
            _record_reference(entry)
            for entry in medical_record_documents
            if entry.index != document.index
            and entry.doc_date < document.doc_date
            and (
                preceding_report is None
                or document.subtype not in SUPPLEMENTAL_MEDLEGAL_SURFACES
                or entry.doc_date > preceding_report.doc_date
            )
        )

        stories[document.index] = DocumentMedicalStory(
            document_index=document.index,
            subtype=document.subtype,
            template_subtype=document.template_subtype,
            contention_surface=document.contention_surface,
            demographics=demographics,
            conditions=visible_conditions,
            prior_claims=prior_claims,
            prior_awards=prior_awards,
            record_references=references,
            preceding_report=preceding_report,
            contentions=tuple(_project_contention(entry) for entry in spoken),
            medical_opinion=_project_opinion(opinion) if opinion is not None else None,
            apportionments=tuple(
                _project_apportionment(entry) for entry in apportionments
            ),
        )

    return MedicalStoryPlan(by_document_index=stories)


__all__ = [
    "ADVOCACY_LETTER_SURFACES",
    "CONTENTION_BINDING_ID_KEY",
    "CONTENTION_DOCUMENT_KIND_KEY",
    "CONTENTION_LOOP_PLANNING_RANKS",
    "CONTENTION_LOOP_SOURCE_KEY",
    "CONTENTION_LOOP_WARNING_PREFIX",
    "CONTENTION_SURFACE_TEMPLATE_PAIRS",
    "INITIAL_MEDLEGAL_SURFACES",
    "PSYCH_MEDLEGAL_SURFACES",
    "PTP_APPORTIONMENT_SURFACES",
    "PTP_CAUSATION_SURFACES",
    "QME_PANEL_PREDECESSOR_SUBTYPES",
    "RECORD_REFERENCE_PARENT_TYPES",
    "SUPPLEMENTAL_MEDLEGAL_SURFACES",
    "ContentionSurface",
    "DocumentMedicalStory",
    "ImrApplicationContent",
    "MedicalStoryPlan",
    "MedicalUrPlan",
    "StoryApportionment",
    "StoryCondition",
    "StoryContention",
    "StoryDemographics",
    "StoryDocumentPlanning",
    "StoryMedicalOpinion",
    "StoryPriorAward",
    "StoryPriorClaim",
    "StoryRecordReference",
    "derive_medical_story",
    "derive_medical_ur_plan",
    "medical_ur_semantic_key",
    "plan_medical_story_documents",
    "resolve_imr_application_content",
]
