"""M3 medical-story document surfaces — frozen models and literals (AJC-62).

This module owns the document-scoped view of the medical story: the label-free,
visibility-limited projection records a renderer is allowed to see (R4), the
contention-surface vocabulary that separates a canonical manifest carrier from
its internal ``template_subtype`` (R2/R5), and the gated UR/IMR plan models
(R39). R77 step 2 ships the MODELS only; ``derive_medical_story()`` — the pure
projection that populates them after the final document tuple is dated,
controlled, perspective-resolved, sorted and indexed — arrives with the
planner/renderer steps, as does the surface map.

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
from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from wc_caseload_engine.medical_assertions import (
    AoeCoeFinding,
    ApportionmentBasisKind,
    ApportionmentDeterminationKind,
    ApportionmentState,
    ContentionClaimType,
    ContentionParty,
    ContentionPosition,
    OpinionAuthorRole,
    OpinionEventKind,
    OpinionReportStage,
    OpinionRevisionKind,
    PsychAddOnExceptionAnalysis,
    RequestedApportionment,
    TreatmentCausation,
)
from wc_caseload_engine.medical_history import PsychInjuryKind
from wc_caseload_engine.seeds import DoctrineGrounding, DoctrineHook, UrDecision

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
    imr_application: ImrApplicationContent | None = None


__all__ = [
    "ADVOCACY_LETTER_SURFACES",
    "INITIAL_MEDLEGAL_SURFACES",
    "PSYCH_MEDLEGAL_SURFACES",
    "PTP_APPORTIONMENT_SURFACES",
    "PTP_CAUSATION_SURFACES",
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
    "StoryMedicalOpinion",
    "StoryPriorAward",
    "StoryPriorClaim",
    "StoryRecordReference",
]
