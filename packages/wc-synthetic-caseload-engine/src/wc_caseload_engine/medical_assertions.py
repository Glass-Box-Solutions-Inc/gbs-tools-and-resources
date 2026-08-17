"""The assertion layer — what the parties *say* about the world truth (AJC-61, M2).

Second level of the two-level medical-story design. :mod:`medical_history` holds
what the applicant actually had; this module holds what contentions, medical
opinions and apportionment assertions *claim* about it, each graded
``supported | thin | unsupportable`` against the frozen Escobedo adequacy
rubric (``escobedo-adequacy-checklist-v2.md``).

**The polarity rule, stated once and enforced everywhere:** assertion divergence
from world truth is legal case content — a defense contention that a lumbar
condition is wholly nonindustrial when the ledger says industrial is a *case*,
not a bug. Only *internal incoherence* fails validation: a dangling reference,
a percentage pair that cannot sum, an interim report claiming an omitted
determination. Divergence is graded; incoherence is rejected.

**Quality is truth-only.** The ``quality`` field on the production models below
exports to exactly one place: the truth manifest's ``assertions`` channel. It
never appears in the seed schema, ``case_facts.yaml``, ``manifest.json``, any
rendered document, warning, filename or log. The label-position leakage probe
holds that boundary mechanically.

Doctrine-hook boundary: AJC-62 appended ``hikida_treatment_carveout`` as the
fifteenth :data:`~wc_caseload_engine.seeds.DoctrineHook` member, held out of
the feature-absent draw by ``LEGACY_DOCTRINE_POOL`` (the frozen first
fourteen). The enum member is content/pool machinery only — Hikida/Justice
*semantics* remain typed here: ``claim_type="compensable_consequence"`` plus
``treatment_causation`` and ``requested_apportionment``, graded under the
NARROWED Justice rule (treatment unapportionable only where it is the *sole*
cause of the disability).

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import datetime as dt
import json
import random
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from wc_caseload_engine.medical_history import (
    SIBTF_QUALIFYING,
    MedicalHistory,
    PsychInjuryKind,
)
from wc_caseload_engine.seeds import (
    ANCHOR_DATE,
    BensonGrounding,
    CaseSeed,
    ClaimResponse,
    DoctrineGrounding,
    DoctrineHook,
    EvalType,
    FirefighterPresumptionGrounding,
    Lc4664PriorAwardGrounding,
    SibtfGrounding,
    TargetStage,
    derive_seed,
)

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

type AssertionQuality = Literal["supported", "thin", "unsupportable"]
"""The truth-only grade. Never analyzer-visible; the leakage probe enforces it."""

type AssertionQualityContract = Literal["1.0.0", "2.0.0"]
"""The normalized assertions-channel major selecting grading semantics."""

type ContentionClaimType = Literal[
    "industrial_causation",
    "aggravation",
    "apportionment_defense",
    "compensable_consequence",
    "psych_add_on",
    "denial_of_injury",
]

type ContentionParty = Literal["applicant", "defense"]
type ContentionPosition = Literal["affirm", "deny"]
type OpinionAuthorRole = Literal["ptp", "qme", "ame"]
type OpinionReportStage = Literal["interim", "final"]

type ApportionmentState = Literal["deferred", "determined", "omitted"]
"""``deferred`` is a lifecycle state, not a quality grade — an interim report
legitimately defers (counsel ruling 2). ``omitted`` on a *final* report is a
valid plantable defect that grades ``unsupportable``."""

type TreatmentCausation = Literal["sole_cause", "contributing_cause"]
type RequestedApportionment = Literal["apply", "refuse"]

type ApportionmentDeterminationKind = Literal[
    "allocated",
    "no_nonindustrial_share",
    "unable_to_approximate",
]
"""How a determined final report concluded. ``allocated`` carries one or more
assertion rows with a nonzero nonindustrial share; a reasoned 100%-industrial
conclusion is ``no_nonindustrial_share``; the *Nunes*/*Benson* good-faith
"cannot approximate" safe harbor is ``unable_to_approximate`` — both of the
latter own no row and can grade supported when reasoned."""

type PsychAddOnExceptionAnalysis = Literal[
    "violent_act",
    "direct_exposure",
    "catastrophic_injury",
    "none_applies",
]

type ApportionmentBasisKind = Literal[
    # Ordinary valid pathology bases — graded through the Escobedo checklist.
    "preexisting_degenerative_pathology",
    "asymptomatic_prior_condition",
    "nonindustrial_medical_condition",
    "prior_symptomatic_disability",
    # Rice/Jackson: a weighing factor, never a bar (rubric §2.5).
    "genetics_heredity_pathology",
    # Doctrine-linked bases — valid, but each demands its typed grounding/link.
    "lc4664_prior_award",
    "benson_successive_injury",
    "industrial_treatment",
    # Gradeable defects — representable on purpose; the grader condemns them.
    "vocational_apportionment",
    "psych_impairment_add_on",
    "lc3208_3_threshold_misuse",
    "bare_age",
    "bare_gender",
    "risk_factor_only",
]
"""Fourteen members. The last six are deliberately representable: an
unsupportable basis the schema cannot state is an unsupportable report the
corpus cannot contain. ``genetics_heredity_pathology`` is *not* among them —
*Rice* weighs it (rubric §2.5); only a bare risk-factor substitution
(``risk_factor_only``) is unconditionally hard-invalid."""

type EvidenceDisposition = Literal["supports", "contradicts", "indeterminate"]

# --- AJC-62 (M3) frozen literals — R6 and R26 ---

type AoeCoeFinding = Literal[
    "industrial",
    "nonindustrial",
    "deferred",
]
"""A physician's own AOE/COE conclusion (R6). An independent finding: PTP
sampling never inspects whether an advocacy letter exists (R16), and agreement
in result is concurrence, never responsive adoption."""

type OpinionEventKind = Literal[
    "base_report",
    "supplemental_report",
    "deposition",
]

type OpinionRevisionKind = Literal[
    "unchanged_additional_reasoning",
    "new_records_no_change",
    "revised_causation",
    "revised_apportionment",
    "revised_causation_and_apportionment",
]

type OpinionContentionDisposition = Literal[
    "adopted",
    "concurred",
    "rejected",
    "deferred",
    "unaddressed",
]
"""The five-way classification of one opinion's answer to one contention
(R26). ``adopted`` is responsive adoption of an advocated theory
(``endorses_contention_ids``); ``concurred`` is an independently reached same
result; an ID in none of the four collections is ``unaddressed``."""

type DefenseContestTheory = Literal[
    "insufficient_investigation",
    "post_termination",
    "lack_of_substantial_medical_evidence",
]

type ContestPath = Literal[
    "objection_only",
    "objection_supplemental",
    "objection_deposition",
    "objection_supplemental_deposition",
    "supplemental_only",
    "supplemental_deposition",
]

type ContentionDocumentKind = Literal[
    "opinion_report",
    "advocacy",
    "objection",
    "supplemental_request",
    "supplemental_report",
    "qme_deposition",
]

CONTENTION_ID_PATTERN: Final[str] = r"^ctn-(0[1-9]|[1-9][0-9])$"
OPINION_ID_PATTERN: Final[str] = r"^opn-(0[1-9]|[1-9][0-9])$"
APPORTIONMENT_ID_PATTERN: Final[str] = r"^app-(0[1-9]|[1-9][0-9])$"
CDOC_ID_PATTERN: Final[str] = r"^cdoc-(0[1-9]|[1-9][0-9])$"
"""``ctn-01`` … ``ctn-99``; ``opn-``/``app-``/``cdoc-`` likewise. Two digits
from ``01``. The seed caps (12/8/12, and 15 contention documents) keep
two-digit space sufficient; IDs are assigned only after every stochastic
decision, as a pure labelling pass."""

#: Grounding hook → the apportionment basis kind its typed grounding backs.
HOOK_TO_BASIS: Final[dict[str, str]] = {
    "benson": "benson_successive_injury",
    "lc4664_prior_award": "lc4664_prior_award",
}

#: The maximum reviewed-record references one opinion may carry, combined.
REVIEWED_IDS_COMBINED_CAP: Final[int] = 12


# ---------------------------------------------------------------------------
# Production models — truth-side, frozen, quality-bearing
# ---------------------------------------------------------------------------


class Contention(BaseModel):
    """One party's claim about causation — legal content, graded not policed.

    M3 consumers: ``claim_type``/``party``/``position`` select the advocacy
    register; targets anchor the prose to ledger entities;
    ``requested_apportionment`` drives the apply/refuse conclusion register;
    ``quality`` maps to the truth serializer ONLY.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=CONTENTION_ID_PATTERN)
    claim_type: ContentionClaimType
    party: ContentionParty
    position: ContentionPosition
    target_condition_id: str | None = None
    target_prior_claim_id: str | None = None
    target_prior_award_id: str | None = None
    target_body_part: str | None = None
    doctrine_hooks: tuple[DoctrineHook, ...] = ()
    """Validated against exactly the fifteen frozen enum members (AJC-62 added
    ``hikida_treatment_carveout``); the Hikida *semantics* stay typed below."""

    rationale: str | None = None
    treatment_causation: TreatmentCausation | None = None
    """Explicit-seed-only in M2; the sampler never sets it. With
    ``requested_apportionment`` it types the narrowed Justice/Hikida claim on a
    ``compensable_consequence`` contention."""

    requested_apportionment: RequestedApportionment | None = None
    groundings: tuple[DoctrineGrounding, ...] = ()

    psych_injury_kind: PsychInjuryKind | None = None
    """The party's direct-versus-consequence characterisation (AJC-62, M3) —
    an assertion, free to diverge from the world condition's own kind. Requires
    a psychiatric anchor (psychiatric target condition, psyche target body
    part, or psyche claim body part); §C holds that line. Frozen out of
    assertions channel ``1.0.0`` by Amendment A1."""

    quality: AssertionQuality
    """Truth-only. Derived by the frozen rubric, never authored, never copied
    from a sampling target recipe."""


class MedicalOpinion(BaseModel):
    """One physician's report event — PTP, QME or AME, interim or final."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=OPINION_ID_PATTERN)
    author_role: OpinionAuthorRole
    report_stage: OpinionReportStage
    report_date: dt.date
    apportionment_state: ApportionmentState
    determination_kind: ApportionmentDeterminationKind | None = None
    """M3 consumer: selects the allocated / 100%-industrial /
    unable-to-approximate conclusion template."""

    determination_rationale: str | None = None
    """M3 consumer: the final apportionment determination paragraph."""

    examination_performed: bool = False
    reviewed_condition_ids: tuple[str, ...] = Field(default=(), max_length=8)
    reviewed_prior_claim_ids: tuple[str, ...] = Field(default=(), max_length=5)
    reviewed_prior_award_ids: tuple[str, ...] = Field(default=(), max_length=5)
    endorses_contention_ids: tuple[str, ...] = ()
    rejects_contention_ids: tuple[str, ...] = ()
    responds_to_opinion_id: str | None = None
    supersedes_opinion_id: str | None = None
    rationale: str | None = None
    revision_rationale: str | None = None

    event_kind: OpinionEventKind = "base_report"
    """Which report event this opinion is (AJC-62, M3). Supplemental and
    deposition events are responses: a QME/AME author, an exact
    ``responds_to_opinion_id`` predecessor, a ``revision_kind`` and no fresh
    examination — the validator below and §C hold the structure."""

    revision_kind: OpinionRevisionKind | None = None
    concurs_with_contention_ids: tuple[str, ...] = ()
    """Independent agreement — the evaluator reached the advocated result on
    its own (AJC-62, M3). Distinct from ``endorses_contention_ids``, which is
    responsive adoption; the four disposition collections are pairwise
    disjoint."""

    defers_contention_ids: tuple[str, ...] = ()
    """Contentions the report expressly reserved rather than resolved."""

    psych_injury_kind: PsychInjuryKind | None = None
    aoe_coe_finding: AoeCoeFinding | None = None
    """The physician's own AOE/COE conclusion (AJC-62, M3) — an independent
    finding based on treatment history, examination, mechanism and clinical
    course, never a response to advocacy (R16)."""

    aoe_coe_rationale: str | None = None

    quality: AssertionQuality

    @model_validator(mode="after")
    def _combined_review_cap(self) -> MedicalOpinion:
        combined = (
            len(self.reviewed_condition_ids)
            + len(self.reviewed_prior_claim_ids)
            + len(self.reviewed_prior_award_ids)
        )
        if combined > REVIEWED_IDS_COMBINED_CAP:
            raise ValueError(
                f"medical opinion '{self.id}' reviews {combined} records combined; "
                f"the combined cap is {REVIEWED_IDS_COMBINED_CAP}"
            )
        return self

    @model_validator(mode="after")
    def _event_kind_is_structurally_coherent(self) -> MedicalOpinion:
        """R26/R27/R37's single-model structure. Version-safe by construction:
        a ledger parsed from assertions channel ``1.0.0`` carries only the
        ``base_report`` default, so no clause here can misfire on the
        truth-manifest path (Amendment A1)."""
        if self.event_kind == "base_report":
            if self.revision_kind is not None:
                raise ValueError(
                    f"medical opinion '{self.id}' sets revision_kind "
                    f"{self.revision_kind!r} but event_kind is 'base_report'; "
                    "revision kinds describe supplemental and deposition "
                    "response events"
                )
            return self
        if self.author_role == "ptp":
            raise ValueError(
                f"medical opinion '{self.id}' has event_kind "
                f"{self.event_kind!r} but author_role 'ptp'; PTP opinions may "
                "only be base reports — supplemental and deposition opinions "
                "carry a QME or AME author"
            )
        if self.revision_kind is None:
            raise ValueError(
                f"medical opinion '{self.id}' has event_kind "
                f"{self.event_kind!r} but no revision_kind; a response opinion "
                "states how it relates to its predecessor"
            )
        if self.responds_to_opinion_id is None:
            raise ValueError(
                f"medical opinion '{self.id}' has event_kind "
                f"{self.event_kind!r} but no responds_to_opinion_id; a "
                "response opinion names its exact immediate predecessor"
            )
        if self.examination_performed:
            raise ValueError(
                f"medical opinion '{self.id}' has event_kind "
                f"{self.event_kind!r} but examination_performed is true; a "
                "response opinion reviews and reasons without a fresh "
                "examination"
            )
        if not (self.rationale or self.revision_rationale):
            raise ValueError(
                f"medical opinion '{self.id}' has event_kind "
                f"{self.event_kind!r} but neither rationale nor "
                "revision_rationale; a response opinion states a nonempty "
                "reason appropriate to its revision kind"
            )
        return self


class ApportionmentAssertion(BaseModel):
    """One §4663/§4664 percentage split for one body part, on one opinion.

    Field-per-checklist-item on purpose: the frozen oracle requires every
    Escobedo item to *independently* move a supported build to its expected
    lower grade, so every item needs an independently controllable input.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=APPORTIONMENT_ID_PATTERN)
    opinion_id: str
    body_part: str
    industrial_percent: int = Field(ge=0, le=100)
    nonindustrial_percent: int = Field(ge=0, le=100)
    basis_kinds: tuple[ApportionmentBasisKind, ...] = ()
    condition_ids: tuple[str, ...] = ()
    prior_claim_ids: tuple[str, ...] = ()
    prior_award_ids: tuple[str, ...] = ()

    description: str | None = None
    """Item 2 — the exact nature of the apportionable disability."""

    disability_causation_stated: bool = False
    """Item 1 — percentages attach to DISABILITY causation, not injury
    causation. False models the *Lindh* risk-of-injury substitution."""

    reasonable_medical_probability: bool = False
    """Item 4."""

    causal_rationale: str | None = None
    """Items 3a/6 — the how-and-why of the causal mechanism."""

    percentage_rationale: str | None = None
    """Item 7 — the how-and-why of the split itself."""

    prior_award_analysis: str | None = None
    """Item 9 — the §4664(b) presumption treated separately from §4663
    causation. Applicable only when ``lc4664_prior_award`` is among the bases."""

    revised_from_percent: int | None = Field(default=None, ge=0, le=100)
    revision_rationale: str | None = None
    """Item 10 — an unexplained material revision is unsupportable; a reasoned
    one is not a defect (*Lindh*)."""

    psych_exception_analysis: PsychAddOnExceptionAnalysis | None = None
    """M3 consumer: exception-specific psych paragraph. A
    ``psych_impairment_add_on`` basis with ``None`` or ``none_applies`` grades
    unsupportable; a named exception is graded on its remaining reasoning."""

    linked_contention_id: str | None = None
    """Item 8 — an ``industrial_treatment`` basis must link the
    compensable-consequence contention whose treatment story it apportions."""

    groundings: tuple[DoctrineGrounding, ...] = ()

    quality: AssertionQuality


class MedicalAssertionLedger(BaseModel):
    """The assertion layer for one case — frozen sibling beside the histories."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contentions: tuple[Contention, ...] = ()
    medical_opinions: tuple[MedicalOpinion, ...] = ()
    apportionment_assertions: tuple[ApportionmentAssertion, ...] = ()

    def contention(self, contention_id: str) -> Contention | None:
        return next((c for c in self.contentions if c.id == contention_id), None)

    def opinion(self, opinion_id: str) -> MedicalOpinion | None:
        return next((o for o in self.medical_opinions if o.id == opinion_id), None)

    def assertions_of(self, opinion_id: str) -> tuple[ApportionmentAssertion, ...]:
        return tuple(a for a in self.apportionment_assertions if a.opinion_id == opinion_id)

    def quality_counts(self) -> dict[str, int]:
        counts = {"supported": 0, "thin": 0, "unsupportable": 0}
        for collection in (
            self.contentions,
            self.medical_opinions,
            self.apportionment_assertions,
        ):
            for item in collection:
                counts[item.quality] += 1
        return counts


# AJC-62 Amendment A2-R4: the production-side assertion projection used by
# the M3 plan-digest contract.  These are deliberately literal allowlists,
# not a full model dump with ``quality`` removed.  The cohort oracle declares
# an independent value-identical copy so a coordinated edit cannot silently
# move the change detector.
M3_PLAN_DIGEST_CONTENTION_FIELDS: Final[tuple[str, ...]] = (
    "id",
    "claim_type",
    "party",
    "position",
    "psych_injury_kind",
    "target_condition_id",
    "target_prior_claim_id",
    "target_prior_award_id",
    "target_body_part",
    "doctrine_hooks",
    "rationale",
    "treatment_causation",
    "requested_apportionment",
    "groundings",
)

M3_PLAN_DIGEST_MEDICAL_OPINION_FIELDS: Final[tuple[str, ...]] = (
    "id",
    "author_role",
    "report_stage",
    "report_date",
    "event_kind",
    "revision_kind",
    "apportionment_state",
    "determination_kind",
    "determination_rationale",
    "examination_performed",
    "psych_injury_kind",
    "aoe_coe_finding",
    "aoe_coe_rationale",
    "reviewed_condition_ids",
    "reviewed_prior_claim_ids",
    "reviewed_prior_award_ids",
    "endorses_contention_ids",
    "concurs_with_contention_ids",
    "rejects_contention_ids",
    "defers_contention_ids",
    "responds_to_opinion_id",
    "supersedes_opinion_id",
    "rationale",
    "revision_rationale",
)

M3_PLAN_DIGEST_APPORTIONMENT_ASSERTION_FIELDS: Final[tuple[str, ...]] = (
    "id",
    "opinion_id",
    "body_part",
    "industrial_percent",
    "nonindustrial_percent",
    "basis_kinds",
    "condition_ids",
    "prior_claim_ids",
    "prior_award_ids",
    "description",
    "disability_causation_stated",
    "reasonable_medical_probability",
    "causal_rationale",
    "percentage_rationale",
    "prior_award_analysis",
    "revised_from_percent",
    "revision_rationale",
    "psych_exception_analysis",
    "linked_contention_id",
    "groundings",
)


class ContentionDocumentBinding(BaseModel):
    """One normalized contention-document decision — internal planning state.

    The R26 record behind :class:`~wc_caseload_engine.seeds.
    ContentionDocumentEntry`: every entry field normalized, plus the internal
    ``template_subtype`` carrier split (R2/R35), the proposed date, and whether
    the binding came from an explicit entry, a required opinion realization, or
    sampling. A restricted projection of final realized bindings may enter only
    assertions truth channel ``2.x``. The binding itself never carries
    ``quality`` or a quality-like field, never enters the ordinary manifest,
    and never enters seed YAML.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=CDOC_ID_PATTERN)
    document_kind: ContentionDocumentKind
    subtype: str | None = None
    doc_date: dt.date | None = None
    medical_opinion_id: str | None = None
    target_medical_opinion_id: str | None = None
    spoken_contention_ids: tuple[str, ...] = ()
    """Unbounded on the internal binding by design: an authored
    :class:`~wc_caseload_engine.seeds.ContentionDocumentEntry` keeps R26's
    three-member cap, and every loop *communication* is bundled at
    :data:`MAX_CONTENTIONS_PER_LOOP_DOCUMENT`, but a base opinion report's
    derived binding MUST speak the union of its four disposition collections
    in ledger order (R35) — a docket larger than three is legal there."""

    actor_party: ContentionParty | None = None
    defense_contest_theories: tuple[DefenseContestTheory, ...] = ()
    template_subtype: str | None = None
    proposed_date: dt.date | None = None
    source: Literal["explicit", "required_opinion", "sampled"] = "explicit"
    semantic_key: tuple[object, ...] | None = Field(default=None, exclude=True)
    """R45's pre-ID ``D`` identity, retained for R59 rendering only.

    This is excluded from serialization so manifests, copied seeds, truth
    channels, and existing binding digests do not acquire a publication field.
    """


class ContentionDocumentProjection(BaseModel):
    """One final indexed document's restricted assertions-v2 binding projection.

    This scorer-only record deliberately excludes template dispatch, proposed
    dates, sampler provenance, semantic/render keys, prose projections, record
    references, preceding reports, and UR/IMR lifecycle payloads. It carries no
    quality field and is never written to the ordinary manifest or seed YAML.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    document_index: int = Field(ge=0)
    subtype: str
    document_date: dt.date
    spoken_contention_ids: tuple[str, ...] = ()
    medical_opinion_id: str | None = None
    target_medical_opinion_id: str | None = None
    contention_surface: Literal[
        "advocacy", "objection", "supplemental_request", "qme_deposition"
    ] | None = None
    contention_actor_party: ContentionParty | None = None
    defense_contest_theories: tuple[DefenseContestTheory, ...] = ()


REPORT_CONTENTION_CARRIERS: Final = frozenset(
    {
        "QME_REPORT_INITIAL",
        "QME_COMPREHENSIVE_REPORT",
        "AME_REPORT",
        "AME_COMPREHENSIVE_REPORT",
        "MEDICAL_LEGAL_QME_AME_IME",
        "APPORTIONMENT_REPORT",
        "PSYCH_EVAL_REPORT_QME_AME",
        "QME_REPORT_SUPPLEMENTAL",
        "SUPPLEMENTAL_QME_AME_REPORT",
        "TREATING_PHYSICIAN_REPORT",
        "TREATING_PHYSICIAN_REPORT_PR2",
        "TREATING_PHYSICIAN_REPORT_PR4",
        "TREATING_PHYSICIAN_REPORT_FINAL",
    }
)
"""Literal report carriers. Reports may carry a binding regardless of surface."""

CONTENTION_SURFACE_CARRIERS: Final = {
    "advocacy": frozenset(
        {
            "ADVOCACY_LETTERS_PTP",
            "ADVOCACY_LETTERS_QME",
            "ADVOCACY_LETTERS_AME",
            "ADVOCACY_LETTERS_PTP_QME_AME",
        }
    ),
    "objection": frozenset({"ADVOCACY_LETTERS_PTP_QME_AME"}),
    "supplemental_request": frozenset({"ADVOCACY_LETTERS_PTP_QME_AME"}),
    "qme_deposition": frozenset({"DEPOSITION_TRANSCRIPT"}),
}
"""Literal non-report carrier map used by both plan and truth validation."""


def contention_document_projections(
    documents: Sequence[object],
) -> tuple[ContentionDocumentProjection, ...]:
    """Project only final planned documents carrying an assertion binding."""
    projections: list[ContentionDocumentProjection] = []
    for document in documents:
        spoken = tuple(getattr(document, "spoken_contention_ids", ()))
        medical_opinion_id = getattr(document, "medical_opinion_id", None)
        target_medical_opinion_id = getattr(
            document, "target_medical_opinion_id", None
        )
        surface = getattr(document, "contention_surface", None)
        actor = getattr(document, "contention_actor_party", None)
        theories = tuple(getattr(document, "defense_contest_theories", ()))
        if not any(
            (
                spoken,
                medical_opinion_id,
                target_medical_opinion_id,
                surface,
                actor,
                theories,
            )
        ):
            continue
        projections.append(
            ContentionDocumentProjection(
                document_index=document.index,
                subtype=document.subtype,
                document_date=document.doc_date,
                spoken_contention_ids=spoken,
                medical_opinion_id=medical_opinion_id,
                target_medical_opinion_id=target_medical_opinion_id,
                contention_surface=surface,
                contention_actor_party=actor,
                defense_contest_theories=theories,
            )
        )
    return tuple(projections)


def _artifact_value(document: object, mapping_key: str, attribute: str) -> object:
    if isinstance(document, Mapping):
        return document.get(mapping_key)
    return getattr(document, attribute, None)


def validate_contention_document_bindings(
    projection: AssertionWorldProjection,
    ledger: MedicalAssertionLedger,
    bindings: Sequence[ContentionDocumentProjection],
    documents: Sequence[object] | None = None,
) -> tuple[str, ...]:
    """Validate v2 bindings without turning legal divergence into incoherence.

    Binding incoherence is intentionally limited to dangling projection IDs and
    a canonical subtype that cannot carry its stated contention surface.
    Artifact-link integrity additionally pins each row to the manifest position,
    subtype and date it names. ``surfaces_in_file`` is never consulted here.
    """
    del projection  # World divergence is gradeable and not a binding predicate.
    problems: list[str] = []
    contention_ids = frozenset(item.id for item in ledger.contentions)
    opinion_ids = frozenset(item.id for item in ledger.medical_opinions)
    seen_indexes: set[int] = set()
    for binding in bindings:
        index = binding.document_index
        if index in seen_indexes:
            problems.append(
                f"contentionDocuments contains more than one row for documentIndex {index}"
            )
        seen_indexes.add(index)
        if documents is None:
            pass
        elif index >= len(documents):
            problems.append(
                f"contentionDocuments documentIndex {index} does not select a manifest document"
            )
        else:
            artifact = documents[index]
            subtype = _artifact_value(artifact, "subtype", "subtype")
            raw_date = _artifact_value(artifact, "documentDate", "doc_date")
            artifact_date = (
                raw_date.isoformat() if isinstance(raw_date, dt.date) else raw_date
            )
            if subtype != binding.subtype:
                problems.append(
                    f"contentionDocuments documentIndex {index} subtype "
                    f"{binding.subtype!r} does not match manifest subtype {subtype!r}"
                )
            if artifact_date != binding.document_date.isoformat():
                problems.append(
                    f"contentionDocuments documentIndex {index} documentDate "
                    f"{binding.document_date.isoformat()!r} does not match manifest "
                    f"documentDate {artifact_date!r}"
                )
        for contention_id in binding.spoken_contention_ids:
            if contention_id not in contention_ids:
                problems.append(
                    f"contentionDocuments documentIndex {index} references unknown "
                    f"contention {contention_id!r}"
                )
        for field_name, opinion_id in (
            ("medicalOpinionId", binding.medical_opinion_id),
            ("targetMedicalOpinionId", binding.target_medical_opinion_id),
        ):
            if opinion_id is not None and opinion_id not in opinion_ids:
                problems.append(
                    f"contentionDocuments documentIndex {index} {field_name} references "
                    f"unknown medical opinion {opinion_id!r}"
                )
        surface = binding.contention_surface
        if (
            surface is not None
            and binding.subtype not in REPORT_CONTENTION_CARRIERS
            and binding.subtype not in CONTENTION_SURFACE_CARRIERS[surface]
        ):
            problems.append(
                f"contentionDocuments documentIndex {index} subtype "
                f"{binding.subtype!r} cannot carry contentionSurface {surface!r}"
            )
    return tuple(problems)


class MedicalAssertionPlan(BaseModel):
    """The complete assertion-layer product (R26): ledger plus loop bindings.

    ``derive_medical_assertion_plan()`` (R77 step 3) returns this; step 2 ships
    the frozen shape. The ledger member is the same quality-bearing object as
    today; the bindings never carry a quality, a derived quality synonym, or an
    analyzer verdict.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    ledger: MedicalAssertionLedger | None = None
    contention_documents: tuple[ContentionDocumentBinding, ...] = ()


# ---------------------------------------------------------------------------
# Validation context + world projection — ONE rule implementation, both paths
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AssertionValidationContext:
    """Everything §C and the evidence predicate need beyond the world ledger.

    Constructed from the seed at plan time and parsed from the truth channel's
    ``validationContext`` at validation time, so exactly one implementation of
    every rule exists — no truth-side re-derivation, no second rulebook.
    """

    date_of_injury: dt.date
    anchor_date: dt.date
    current_body_parts: tuple[str, ...]
    target_stage: TargetStage
    claim_response: ClaimResponse
    eval_type: EvalType


@dataclass(frozen=True)
class ProjectedCondition:
    """One world-truth condition, reduced to the fields the rules consume."""

    id: str
    key: str
    label: str
    causal_ground_truth: Literal["industrial", "nonindustrial", "mixed"]
    onset: dt.date | None
    body_system: str
    body_part: str | None
    apportionment_targets: tuple[str, ...]
    wholly_unrelated: bool
    severity: Literal["subclinical", "mild", "moderate", "severe"]
    trajectory: Literal["resolved", "stable", "progressive", "fluctuating"]
    symptomatic_before_doi: bool | None
    surfaces_in_file: bool
    psych_injury_kind: PsychInjuryKind | None = None
    """R6's projection support (AJC-62, M3). Frozen out of assertions channel
    ``1.0.0`` by Amendment A1, so a parsed truth projection carries ``None``."""


@dataclass(frozen=True)
class ProjectedPriorAward:
    id: str
    prior_claim_id: str
    body_parts: tuple[str, ...]
    pd_percent: int
    award_date: dt.date
    resolution_type: str
    conclusively_presumed: bool

    @property
    def still_exists_conclusively_presumed(self) -> bool:
        """Alias matching the production :class:`PriorAward` field name, so the
        shipped SIBTF clauses read a projection exactly as they read a ledger."""
        return self.conclusively_presumed


@dataclass(frozen=True)
class ProjectedPriorClaim:
    id: str
    date_of_injury: dt.date
    body_parts: tuple[str, ...]
    resolution_type: str
    overlaps_current: bool
    award: ProjectedPriorAward | None = None


@dataclass(frozen=True)
class AssertionWorldProjection:
    """The redacted world-truth view every assertion rule consumes.

    Built by :func:`project_medical_history` at plan time and parsed from the
    truth channel's ``medicalHistory`` at validation time. Identity fields —
    demographics, archetype, employers, providers — are deliberately absent.
    """

    conditions: tuple[ProjectedCondition, ...] = ()
    prior_claims: tuple[ProjectedPriorClaim, ...] = ()

    @property
    def awards(self) -> tuple[ProjectedPriorAward, ...]:
        return tuple(c.award for c in self.prior_claims if c.award is not None)

    def condition(self, condition_id: str) -> ProjectedCondition | None:
        return next((c for c in self.conditions if c.id == condition_id), None)

    def prior_claim(self, claim_id: str) -> ProjectedPriorClaim | None:
        return next((c for c in self.prior_claims if c.id == claim_id), None)

    def prior_award(self, award_id: str) -> ProjectedPriorAward | None:
        return next((a for a in self.awards if a.id == award_id), None)

    def condition_ids(self) -> frozenset[str]:
        return frozenset(c.id for c in self.conditions)

    def prior_claim_ids(self) -> frozenset[str]:
        return frozenset(c.id for c in self.prior_claims)

    def prior_award_ids(self) -> frozenset[str]:
        return frozenset(a.id for a in self.awards)


def _condition_targets(condition: object) -> tuple[str, ...]:
    """Apportionment targets for one ledger condition, catalog-first.

    The catalog is the source for a keyed condition (diabetes has no
    ``body_part`` but targets wrist/foot); an uncatalogued explicit condition
    falls back to its stated ``body_part``.
    """
    from wc_caseload_engine.clinical_grounding import CONDITION_CATALOG

    key = getattr(condition, "key", "seeded")
    spec = CONDITION_CATALOG.get(key)
    if spec is not None and spec.apportionment_targets:
        return tuple(spec.apportionment_targets)
    body_part = getattr(condition, "body_part", None)
    return (body_part,) if body_part else ()


def project_medical_history(
    history: MedicalHistory, current_body_parts: tuple[str, ...]
) -> AssertionWorldProjection:
    """Reduce the world-truth ledger to exactly what assertion rules read.

    The redaction boundary: demographics, archetype, employer names and every
    other identity field stay behind. What crosses is the causal record —
    conditions with severity/trajectory/symptom state, prior claims with their
    overlap, awards with their **effective** presumption.
    """
    injured = frozenset(current_body_parts)
    conditions = tuple(
        ProjectedCondition(
            id=c.id,
            key=c.key,
            label=c.label,
            causal_ground_truth=c.causal_ground_truth,
            onset=c.onset,
            body_system=c.body_system,
            body_part=c.body_part,
            apportionment_targets=_condition_targets(c),
            wholly_unrelated=c.wholly_unrelated,
            severity=c.severity,
            trajectory=c.trajectory,
            symptomatic_before_doi=c.symptomatic_before_doi,
            surfaces_in_file=c.surfaces_in_file,
            psych_injury_kind=c.psych_injury_kind,
        )
        for c in history.conditions
    )
    prior_claims = tuple(
        ProjectedPriorClaim(
            id=claim.id,
            date_of_injury=claim.date_of_injury,
            body_parts=tuple(claim.body_parts),
            resolution_type=claim.resolution_type,
            overlaps_current=bool(set(claim.body_parts) & injured),
            award=(
                ProjectedPriorAward(
                    id=claim.award.id,
                    prior_claim_id=claim.id,
                    body_parts=tuple(claim.award.body_parts),
                    pd_percent=claim.award.pd_percent,
                    award_date=claim.award.award_date,
                    resolution_type=claim.award.resolution_type,
                    conclusively_presumed=claim.award.still_exists_conclusively_presumed,
                )
                if claim.award is not None
                else None
            ),
        )
        for claim in history.prior_claims
    )
    return AssertionWorldProjection(conditions=conditions, prior_claims=prior_claims)


def sibtf_grounding_clauses(history: AssertionWorldProjection) -> tuple[str, ...]:
    """Which §4751 clauses this projection satisfies — the *shipped* predicate.

    Runs :data:`~wc_caseload_engine.medical_history.SIBTF_QUALIFYING` itself
    against the projection (which exposes ``conditions`` and ``awards`` in the
    shapes those clauses read), so SIBTF policy has exactly one home and the
    plan path and the truth path cannot drift apart.
    """
    return tuple(
        clause.name
        for clause in SIBTF_QUALIFYING
        if clause.holds(history)  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# The §C referential validator — divergence is legal, incoherence fails
# ---------------------------------------------------------------------------

#: Doctrine hooks whose argument a typed grounding can stand behind. An
#: explicit hook without one WARNS (decision #2 — explicit control wins,
#: loudly); a grounding for a hook the assertion does not carry FAILS.
GROUNDABLE_HOOKS: Final[frozenset[str]] = frozenset(
    {"benson", "sibtf", "lc4664_prior_award", "firefighter_presumption"}
)


class MedicalAssertionError(ValueError):
    """A ledger whose assertions are internally incoherent. Raised at
    generation time — divergence from world truth never lands here."""


def _award_pairing_problem(
    label: str,
    identifier: str,
    claim_ids: tuple[str, ...],
    award_ids: tuple[str, ...],
    history: AssertionWorldProjection,
) -> list[str]:
    """The claim/award cross-reference: a cited award must belong to a cited claim."""
    problems: list[str] = []
    if not claim_ids:
        return problems
    for award_id in award_ids:
        award = history.prior_award(award_id)
        if award is None:
            continue
        if award.prior_claim_id not in claim_ids:
            problems.append(
                f"{label} '{identifier}' pairs prior claim '{claim_ids[0]}' with "
                f"award '{award_id}', but that award belongs to prior claim "
                f"'{award.prior_claim_id}'"
            )
    return problems


def _contention_referential(contention: Contention, history: AssertionWorldProjection) -> list[str]:
    problems: list[str] = []
    condition_ids = history.condition_ids()
    if (
        contention.target_condition_id is not None
        and contention.target_condition_id not in condition_ids
    ):
        problems.append(
            f"contention '{contention.id}' references unknown condition "
            f"'{contention.target_condition_id}'"
        )
    if (
        contention.target_prior_claim_id is not None
        and contention.target_prior_claim_id not in history.prior_claim_ids()
    ):
        problems.append(
            f"contention '{contention.id}' references unknown prior claim "
            f"'{contention.target_prior_claim_id}'"
        )
    if (
        contention.target_prior_award_id is not None
        and contention.target_prior_award_id not in history.prior_award_ids()
    ):
        problems.append(
            f"contention '{contention.id}' references unknown prior award "
            f"'{contention.target_prior_award_id}'"
        )
    if (
        contention.target_prior_claim_id is not None
        and contention.target_prior_award_id is not None
    ):
        problems.extend(
            _award_pairing_problem(
                "contention",
                contention.id,
                (contention.target_prior_claim_id,),
                (contention.target_prior_award_id,),
                history,
            )
        )
    return problems


def _opinion_referential(
    opinion: MedicalOpinion,
    history: AssertionWorldProjection,
    contention_ids: frozenset[str],
) -> list[str]:
    problems: list[str] = []
    for ref in opinion.reviewed_condition_ids:
        if ref not in history.condition_ids():
            problems.append(f"medical opinion '{opinion.id}' reviews unknown condition '{ref}'")
    for ref in opinion.reviewed_prior_claim_ids:
        if ref not in history.prior_claim_ids():
            problems.append(f"medical opinion '{opinion.id}' reviews unknown prior claim '{ref}'")
    for ref in opinion.reviewed_prior_award_ids:
        if ref not in history.prior_award_ids():
            problems.append(f"medical opinion '{opinion.id}' reviews unknown prior award '{ref}'")
    disposition_collections: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("endorses", opinion.endorses_contention_ids),
        ("concurs with", opinion.concurs_with_contention_ids),
        ("rejects", opinion.rejects_contention_ids),
        ("defers", opinion.defers_contention_ids),
    )
    for verb, refs in disposition_collections:
        for ref in refs:
            if ref not in contention_ids:
                problems.append(f"medical opinion '{opinion.id}' {verb} unknown contention '{ref}'")
    # R26: the four disposition collections are pairwise disjoint. The
    # endorses/rejects pair keeps its exact M2 template.
    for index, (verb_a, refs_a) in enumerate(disposition_collections):
        for verb_b, refs_b in disposition_collections[index + 1 :]:
            for ref in sorted(set(refs_a) & set(refs_b)):
                problems.append(
                    f"medical opinion '{opinion.id}' both {verb_a} and {verb_b} contention '{ref}'"
                )
    return problems


def _assertion_referential(
    assertion: ApportionmentAssertion,
    history: AssertionWorldProjection,
    ledger: MedicalAssertionLedger,
) -> list[str]:
    problems: list[str] = []
    if ledger.opinion(assertion.opinion_id) is None:
        problems.append(
            f"apportionment assertion '{assertion.id}' references unknown medical "
            f"opinion '{assertion.opinion_id}'"
        )
    if (
        assertion.linked_contention_id is not None
        and ledger.contention(assertion.linked_contention_id) is None
    ):
        problems.append(
            f"apportionment assertion '{assertion.id}' references unknown contention "
            f"'{assertion.linked_contention_id}'"
        )
    for ref in assertion.condition_ids:
        if ref not in history.condition_ids():
            problems.append(
                f"apportionment assertion '{assertion.id}' references unknown condition '{ref}'"
            )
    for ref in assertion.prior_claim_ids:
        if ref not in history.prior_claim_ids():
            problems.append(
                f"apportionment assertion '{assertion.id}' references unknown prior claim '{ref}'"
            )
    for ref in assertion.prior_award_ids:
        if ref not in history.prior_award_ids():
            problems.append(
                f"apportionment assertion '{assertion.id}' references unknown prior award '{ref}'"
            )
    problems.extend(
        _award_pairing_problem(
            "apportionment assertion",
            assertion.id,
            assertion.prior_claim_ids,
            assertion.prior_award_ids,
            history,
        )
    )
    return problems


def _opinion_chain(
    ledger: MedicalAssertionLedger, context: AssertionValidationContext
) -> list[str]:
    problems: list[str] = []
    known = {opinion.id for opinion in ledger.medical_opinions}
    for opinion in ledger.medical_opinions:
        if opinion.responds_to_opinion_id == opinion.id:
            problems.append(f"medical opinion '{opinion.id}' responds to itself")
        if opinion.supersedes_opinion_id == opinion.id:
            problems.append(f"medical opinion '{opinion.id}' supersedes itself")
        if (
            opinion.responds_to_opinion_id is not None
            and opinion.responds_to_opinion_id != opinion.id
            and opinion.responds_to_opinion_id not in known
        ):
            problems.append(
                f"medical opinion '{opinion.id}' responds to unknown opinion "
                f"'{opinion.responds_to_opinion_id}'"
            )
        if (
            opinion.supersedes_opinion_id is not None
            and opinion.supersedes_opinion_id != opinion.id
            and opinion.supersedes_opinion_id not in known
        ):
            problems.append(
                f"medical opinion '{opinion.id}' supersedes unknown opinion "
                f"'{opinion.supersedes_opinion_id}'"
            )
        if opinion.report_date < context.date_of_injury:
            problems.append(
                f"medical opinion '{opinion.id}' has report_date "
                f"{opinion.report_date.isoformat()}, before the current date of "
                f"injury {context.date_of_injury.isoformat()}"
            )
        if opinion.report_date > context.anchor_date:
            problems.append(
                f"medical opinion '{opinion.id}' has report_date "
                f"{opinion.report_date.isoformat()}, after the corpus anchor date "
                f"{context.anchor_date.isoformat()}"
            )
        for ref in (opinion.responds_to_opinion_id, opinion.supersedes_opinion_id):
            if ref is None or ref == opinion.id:
                continue
            target = ledger.opinion(ref)
            if target is not None and target.report_date >= opinion.report_date:
                problems.append(
                    f"medical opinion '{opinion.id}' references later-or-same-date "
                    f"opinion '{ref}'; response and supersession targets must be "
                    "strictly earlier"
                )
        if opinion.author_role in ("qme", "ame") and (
            context.eval_type in ("qme", "ame") and opinion.author_role != context.eval_type
        ):
            problems.append(
                f"medical opinion '{opinion.id}' has author_role "
                f"'{opinion.author_role}', which conflicts with lifecycle.eval_type "
                f"'{context.eval_type}'"
            )

    # Cycle detection over the response/supersession graph. Strictly-earlier
    # dating already forbids a cycle among coherent entries, so this fires only
    # on chains that are *also* mis-dated — kept as its own error because a
    # cycle is a different repair from a date.
    edges = {
        opinion.id: tuple(
            ref
            for ref in (opinion.responds_to_opinion_id, opinion.supersedes_opinion_id)
            if ref is not None and ref in known
        )
        for opinion in ledger.medical_opinions
    }
    reported: set[str] = set()
    for start in edges:
        path: list[str] = []
        seen: set[str] = set()
        node = start
        while node in edges and node not in seen:
            seen.add(node)
            path.append(node)
            targets = edges[node]
            if not targets:
                break
            node = targets[0]
        else:
            if node in seen and node in path:
                cycle = [*path[path.index(node) :], node]
                chain = " -> ".join(cycle)
                if frozenset(cycle) not in {frozenset(c.split(" -> ")) for c in reported}:
                    reported.add(chain)
                    problems.append(f"medical opinion chain contains a cycle: {chain}")
    return problems


def _psych_kind_anchoring(
    ledger: MedicalAssertionLedger,
    history: AssertionWorldProjection,
    context: AssertionValidationContext,
) -> list[str]:
    """R6: a contention or opinion psych kind requires a psychiatric anchor.

    The anchor is a psychiatric target condition, a psyche target body part, a
    psyche claim body part, or (for an opinion) a referenced psychiatric
    contention. Divergence among the world condition, contention and opinion
    KINDS is legal case content and never lands here — only a psych
    classification with nothing psychiatric anywhere near it is incoherent.

    Version-safe on the truth path by construction (Amendment A1): channel
    ``1.0.0`` omits ``psych_injury_kind``, so a parsed ledger carries ``None``
    everywhere and every clause below is inert — the AJC-61-representable rule
    set, without guessing omitted values.
    """
    problems: list[str] = []
    psyche_claimed = "psyche" in context.current_body_parts

    def psychiatric_target(condition_id: str | None) -> bool:
        if condition_id is None:
            return False
        condition = history.condition(condition_id)
        return condition is not None and condition.body_system == "psychiatric"

    def psychiatric_contention(contention: Contention) -> bool:
        return (
            contention.psych_injury_kind is not None
            or contention.claim_type == "psych_add_on"
            or contention.target_body_part == "psyche"
            or psychiatric_target(contention.target_condition_id)
        )

    for contention in ledger.contentions:
        if contention.psych_injury_kind is None:
            continue
        if (
            psychiatric_target(contention.target_condition_id)
            or contention.target_body_part == "psyche"
            or psyche_claimed
        ):
            continue
        problems.append(
            f"contention '{contention.id}' sets psych_injury_kind "
            f"'{contention.psych_injury_kind}' without a psychiatric target "
            "condition, a psyche target body part, or a psyche claim body part"
        )
    for opinion in ledger.medical_opinions:
        if opinion.psych_injury_kind is None:
            continue
        if psyche_claimed or any(psychiatric_target(ref) for ref in opinion.reviewed_condition_ids):
            continue
        referenced = (
            *opinion.endorses_contention_ids,
            *opinion.concurs_with_contention_ids,
            *opinion.rejects_contention_ids,
            *opinion.defers_contention_ids,
        )
        if any(
            (found := ledger.contention(ref)) is not None and psychiatric_contention(found)
            for ref in referenced
        ):
            continue
        problems.append(
            f"medical opinion '{opinion.id}' sets psych_injury_kind "
            f"'{opinion.psych_injury_kind}' without a psychiatric reviewed "
            "condition, a psyche claim body part, or a referenced psychiatric "
            "contention"
        )
    return problems


def _response_opinion_structure(ledger: MedicalAssertionLedger) -> list[str]:
    """R37's cross-opinion structure: a response keeps its predecessor's author.

    The single-model half (revision kind, predecessor reference, no fresh
    examination, nonempty reasoning) lives on the model validator; what needs
    the ledger is the author-role parity between a supplemental or deposition
    opinion and the exact predecessor it responds to. Inert on a parsed
    channel-``1.0.0`` ledger, where ``event_kind`` is always ``base_report``.
    """
    problems: list[str] = []
    for opinion in ledger.medical_opinions:
        if opinion.event_kind == "base_report":
            continue
        if opinion.responds_to_opinion_id is None:
            continue  # the model validator already rejected this shape
        predecessor = ledger.opinion(opinion.responds_to_opinion_id)
        if predecessor is not None and predecessor.author_role != opinion.author_role:
            problems.append(
                f"medical opinion '{opinion.id}' has author_role "
                f"'{opinion.author_role}' but its predecessor "
                f"'{predecessor.id}' has author_role "
                f"'{predecessor.author_role}'; a supplemental or deposition "
                "opinion keeps its predecessor's author"
            )
    return problems


def _causation_family_changed(response: MedicalOpinion, predecessor: MedicalOpinion) -> bool:
    """R37's causation changed-field family: AOE/COE, psych classification,
    any endorsement/concurrence/rejection/deferral result, or the causation
    rationale differs from the immediate predecessor."""
    if response.aoe_coe_finding != predecessor.aoe_coe_finding:
        return True
    if response.psych_injury_kind != predecessor.psych_injury_kind:
        return True
    if response.aoe_coe_rationale != predecessor.aoe_coe_rationale:
        return True
    return any(
        frozenset(getattr(response, collection)) != frozenset(getattr(predecessor, collection))
        for collection in (
            "endorses_contention_ids",
            "concurs_with_contention_ids",
            "rejects_contention_ids",
            "defers_contention_ids",
        )
    )


def _apportionment_family_changed(
    response: MedicalOpinion,
    predecessor: MedicalOpinion,
    ledger: MedicalAssertionLedger,
) -> bool:
    """R37's apportionment changed-field family: apportionment state,
    determination kind, a row's basis set, or at least one percentage differs
    from the immediate predecessor (a row appearing or disappearing is a
    percentage-surface change)."""
    if response.apportionment_state != predecessor.apportionment_state:
        return True
    if response.determination_kind != predecessor.determination_kind:
        return True
    response_rows = {a.body_part: a for a in ledger.assertions_of(response.id)}
    predecessor_rows = {a.body_part: a for a in ledger.assertions_of(predecessor.id)}
    if set(response_rows) != set(predecessor_rows):
        return True
    return any(
        row.nonindustrial_percent != predecessor_rows[part].nonindustrial_percent
        or frozenset(row.basis_kinds) != frozenset(predecessor_rows[part].basis_kinds)
        for part, row in response_rows.items()
    )


def _reviewed_record_union(opinion: MedicalOpinion) -> frozenset[tuple[str, str]]:
    return frozenset(
        (family, ref)
        for family, refs in (
            ("condition", opinion.reviewed_condition_ids),
            ("prior_claim", opinion.reviewed_prior_claim_ids),
            ("prior_award", opinion.reviewed_prior_award_ids),
        )
        for ref in refs
    )


def _revision_kind_predicates(ledger: MedicalAssertionLedger) -> list[str]:
    """R37's per-kind structural predicates — each kind permits and forbids
    exactly its stated field changes (R77 step 4).

    Inert on a parsed channel-``1.0.0`` ledger, where every ``event_kind`` is
    the ``base_report`` default (Amendment A1). Fires only where the response
    opinion's exact immediate predecessor resolves; dangling predecessors are
    the chain validator's finding, not this one's.
    """
    problems: list[str] = []
    for opinion in ledger.medical_opinions:
        if opinion.event_kind == "base_report" or opinion.revision_kind is None:
            continue
        if opinion.responds_to_opinion_id is None:
            continue  # the model validator already rejected this shape
        predecessor = ledger.opinion(opinion.responds_to_opinion_id)
        if predecessor is None or predecessor.id == opinion.id:
            continue
        kind = opinion.revision_kind
        causation_changed = _causation_family_changed(opinion, predecessor)
        apportionment_changed = _apportionment_family_changed(opinion, predecessor, ledger)
        if kind in ("unchanged_additional_reasoning", "new_records_no_change"):
            if opinion.supersedes_opinion_id is not None:
                problems.append(
                    f"medical opinion '{opinion.id}' has revision_kind "
                    f"'{kind}' but sets supersedes_opinion_id; a response "
                    "that changes no result supersedes nothing"
                )
            if causation_changed:
                problems.append(
                    f"medical opinion '{opinion.id}' has revision_kind "
                    f"'{kind}' but changes a causation-family result relative "
                    f"to predecessor '{predecessor.id}'; AOE/COE, psych "
                    "classification and every disposition result must remain "
                    "the same under this kind"
                )
            if apportionment_changed:
                problems.append(
                    f"medical opinion '{opinion.id}' has revision_kind "
                    f"'{kind}' but changes an apportionment-family result "
                    f"relative to predecessor '{predecessor.id}'; state, "
                    "determination kind, bases and percentages must remain "
                    "the same under this kind"
                )
            if kind == "new_records_no_change" and not (
                _reviewed_record_union(opinion) > _reviewed_record_union(predecessor)
            ):
                problems.append(
                    f"medical opinion '{opinion.id}' has revision_kind "
                    "'new_records_no_change' but its reviewed-record union is "
                    "not a strict superset of predecessor "
                    f"'{predecessor.id}''s; acknowledging new records is what "
                    "this kind states"
                )
        else:
            if opinion.supersedes_opinion_id != predecessor.id:
                problems.append(
                    f"medical opinion '{opinion.id}' has revision_kind "
                    f"'{kind}' but supersedes_opinion_id is not its immediate "
                    f"predecessor '{predecessor.id}'; a revising response "
                    "supersedes exactly the report it revises"
                )
            # The complete R37 conjunction: each revising kind requires its
            # own changed-field family and forbids the family it does not
            # state; the combined kind requires BOTH.
            if (
                kind
                in (
                    "revised_causation",
                    "revised_causation_and_apportionment",
                )
                and not causation_changed
            ):
                problems.append(
                    f"medical opinion '{opinion.id}' has revision_kind "
                    f"'{kind}' but changes no causation-family result "
                    f"relative to predecessor '{predecessor.id}'"
                )
            if (
                kind
                in (
                    "revised_apportionment",
                    "revised_causation_and_apportionment",
                )
                and not apportionment_changed
            ):
                problems.append(
                    f"medical opinion '{opinion.id}' has revision_kind "
                    f"'{kind}' but changes no apportionment-family result "
                    f"relative to predecessor '{predecessor.id}'"
                )
            if kind == "revised_causation" and apportionment_changed:
                problems.append(
                    f"medical opinion '{opinion.id}' has revision_kind "
                    "'revised_causation' but also changes an "
                    "apportionment-family result relative to predecessor "
                    f"'{predecessor.id}'; use "
                    "'revised_causation_and_apportionment'"
                )
            if kind == "revised_apportionment" and causation_changed:
                problems.append(
                    f"medical opinion '{opinion.id}' has revision_kind "
                    "'revised_apportionment' but also changes a "
                    "causation-family result relative to predecessor "
                    f"'{predecessor.id}'; use "
                    "'revised_causation_and_apportionment'"
                )
        problems.extend(_percentage_revision_rows(ledger, opinion, predecessor))
    return problems


def _percentage_revision_rows(
    ledger: MedicalAssertionLedger,
    opinion: MedicalOpinion,
    predecessor: MedicalOpinion,
) -> list[str]:
    """R37's allocated-predecessor row metadata, exact in both directions.

    For an allocated predecessor: an unchanged row keeps the predecessor
    percentages and has ``revised_from_percent=None``; a changed row's
    ``revised_from_percent`` MUST equal the immediate predecessor's
    nonindustrial percentage for that body part and MUST state a nonempty
    ``revision_rationale``. A row on a body part the predecessor never
    allocated has nothing to revise from.
    """
    if predecessor.determination_kind != "allocated":
        return []
    problems: list[str] = []
    predecessor_rows = {a.body_part: a for a in ledger.assertions_of(predecessor.id)}
    for row in ledger.assertions_of(opinion.id):
        prior = predecessor_rows.get(row.body_part)
        if prior is None:
            if row.revised_from_percent is not None:
                problems.append(
                    f"apportionment assertion '{row.id}' sets "
                    f"revised_from_percent but predecessor '{predecessor.id}' "
                    f"allocated no percentage for body part '{row.body_part}'"
                )
            continue
        if row.nonindustrial_percent == prior.nonindustrial_percent:
            if row.revised_from_percent is not None:
                problems.append(
                    f"apportionment assertion '{row.id}' keeps predecessor "
                    f"'{predecessor.id}''s nonindustrial "
                    f"{prior.nonindustrial_percent}% for body part "
                    f"'{row.body_part}' but sets revised_from_percent; an "
                    "unchanged row does not claim revision"
                )
            continue
        if row.revised_from_percent != prior.nonindustrial_percent:
            problems.append(
                f"apportionment assertion '{row.id}' changes body part "
                f"'{row.body_part}' from predecessor '{predecessor.id}''s "
                f"nonindustrial {prior.nonindustrial_percent}% but "
                f"revised_from_percent is {row.revised_from_percent}; a "
                "changed row carries the exact predecessor percentage"
            )
        if not row.revision_rationale:
            problems.append(
                f"apportionment assertion '{row.id}' changes body part "
                f"'{row.body_part}' from predecessor '{predecessor.id}' "
                "without a revision_rationale; a changed percentage states "
                "its reason"
            )
    return problems


def _lifecycle(ledger: MedicalAssertionLedger) -> list[str]:
    problems: list[str] = []
    for opinion in ledger.medical_opinions:
        owned_assertions = ledger.assertions_of(opinion.id)
        if opinion.report_stage == "final" and opinion.apportionment_state == "deferred":
            problems.append(
                f"medical opinion '{opinion.id}' is final but apportionment_state is 'deferred'"
            )
        if opinion.report_stage == "interim" and opinion.apportionment_state == "omitted":
            problems.append(
                f"medical opinion '{opinion.id}' is interim but apportionment_state is 'omitted'"
            )
        if opinion.apportionment_state == "deferred" and owned_assertions:
            problems.append(
                f"medical opinion '{opinion.id}' is deferred but owns an apportionment assertion"
            )
        if opinion.apportionment_state == "omitted" and owned_assertions:
            problems.append(
                f"medical opinion '{opinion.id}' is omitted but owns an apportionment assertion"
            )
        if opinion.apportionment_state == "determined" and opinion.determination_kind is None:
            problems.append(
                f"medical opinion '{opinion.id}' is determined but has no determination_kind"
            )
        if opinion.determination_kind is not None and opinion.apportionment_state != "determined":
            problems.append(
                f"medical opinion '{opinion.id}' has determination_kind "
                f"'{opinion.determination_kind}' but apportionment_state is not "
                "'determined'"
            )
        if opinion.determination_kind == "allocated" and not owned_assertions:
            problems.append(
                f"medical opinion '{opinion.id}' has determination_kind 'allocated' "
                "but owns no apportionment assertion"
            )
        if (
            opinion.determination_kind in ("no_nonindustrial_share", "unable_to_approximate")
            and owned_assertions
        ):
            problems.append(
                f"medical opinion '{opinion.id}' has determination_kind "
                f"'{opinion.determination_kind}' but owns an apportionment assertion"
            )
    return problems


def _grounding_typing(ledger: MedicalAssertionLedger) -> list[str]:
    problems: list[str] = []
    for contention in ledger.contentions:
        hooks = [g.hook for g in contention.groundings]
        for hook in sorted({h for h in hooks if hooks.count(h) > 1}):
            problems.append(
                f"contention '{contention.id}' has more than one grounding for "
                f"doctrine hook '{hook}'"
            )
        for grounding in contention.groundings:
            if grounding.hook not in contention.doctrine_hooks:
                problems.append(
                    f"contention '{contention.id}' supplies grounding for "
                    f"'{grounding.hook}' but does not carry that doctrine hook"
                )
            if isinstance(grounding, SibtfGrounding):
                sibtf = grounding
                if not sibtf.preexisting_condition_ids and not sibtf.prior_award_ids:
                    problems.append(
                        f"SIBTF grounding on contention '{contention.id}' must "
                        "reference at least one preexisting condition or prior award"
                    )
        if (
            contention.treatment_causation is not None
            and contention.claim_type != "compensable_consequence"
        ):
            problems.append(
                f"contention '{contention.id}' sets treatment_causation but "
                "claim_type is not 'compensable_consequence'"
            )
        if contention.treatment_causation is not None and contention.target_condition_id is None:
            problems.append(
                f"contention '{contention.id}' sets treatment_causation but has no "
                "target_condition_id"
            )
        if (
            contention.treatment_causation is not None
            and contention.requested_apportionment is None
        ):
            problems.append(
                f"contention '{contention.id}' sets treatment_causation but has no "
                "requested_apportionment"
            )
        if (
            contention.requested_apportionment is not None
            and contention.claim_type != "compensable_consequence"
        ):
            problems.append(
                f"contention '{contention.id}' sets requested_apportionment but "
                "claim_type is not 'compensable_consequence'"
            )
        if (
            contention.requested_apportionment is not None
            and contention.treatment_causation is None
        ):
            problems.append(
                f"contention '{contention.id}' sets requested_apportionment but has "
                "no treatment_causation"
            )
    for assertion in ledger.apportionment_assertions:
        hooks = [g.hook for g in assertion.groundings]
        for hook in sorted({h for h in hooks if hooks.count(h) > 1}):
            problems.append(
                f"apportionment assertion '{assertion.id}' has more than one "
                f"grounding for doctrine hook '{hook}'"
            )
        for grounding in assertion.groundings:
            basis = HOOK_TO_BASIS.get(grounding.hook)
            if basis is None or basis not in assertion.basis_kinds:
                problems.append(
                    f"apportionment assertion '{assertion.id}' supplies grounding "
                    f"for '{grounding.hook}' but its basis_kinds do not include the "
                    "corresponding doctrine basis"
                )
    return problems


def _apportionment_shape(ledger: MedicalAssertionLedger) -> list[str]:
    problems: list[str] = []
    per_opinion_parts: dict[tuple[str, str], int] = {}
    for assertion in ledger.apportionment_assertions:
        owner = ledger.opinion(assertion.opinion_id)
        key = (assertion.opinion_id, assertion.body_part)
        per_opinion_parts[key] = per_opinion_parts.get(key, 0) + 1
        if per_opinion_parts[key] == 2:
            problems.append(
                f"medical opinion '{assertion.opinion_id}' has more than one "
                f"apportionment assertion for body part '{assertion.body_part}'"
            )
        if owner is not None and owner.determination_kind == "allocated":
            if assertion.industrial_percent + assertion.nonindustrial_percent != 100:
                problems.append(
                    f"apportionment assertion '{assertion.id}' percentages must sum "
                    f"to 100; got industrial={assertion.industrial_percent} and "
                    f"nonindustrial={assertion.nonindustrial_percent}"
                )
            if assertion.nonindustrial_percent == 0:
                problems.append(
                    f"apportionment assertion '{assertion.id}' is allocated but "
                    "nonindustrial_percent is zero; use determination_kind "
                    "'no_nonindustrial_share' on the owning opinion"
                )
        for label, values in (
            ("basis kind", assertion.basis_kinds),
            ("condition id", assertion.condition_ids),
            ("prior claim id", assertion.prior_claim_ids),
            ("prior award id", assertion.prior_award_ids),
        ):
            listed = list(values)
            for value in sorted({v for v in listed if listed.count(v) > 1}):
                problems.append(
                    f"apportionment assertion '{assertion.id}' repeats {label} '{value}'"
                )
        if "lc4664_prior_award" in assertion.basis_kinds and not any(
            isinstance(g, Lc4664PriorAwardGrounding) for g in assertion.groundings
        ):
            problems.append(
                f"apportionment assertion '{assertion.id}' uses 'lc4664_prior_award' "
                "without a typed prior-award grounding"
            )
        if "benson_successive_injury" in assertion.basis_kinds and not any(
            isinstance(g, BensonGrounding) for g in assertion.groundings
        ):
            problems.append(
                f"apportionment assertion '{assertion.id}' uses "
                "'benson_successive_injury' without a typed Benson grounding"
            )
        if "industrial_treatment" in assertion.basis_kinds:
            linked = (
                ledger.contention(assertion.linked_contention_id)
                if assertion.linked_contention_id is not None
                else None
            )
            if linked is None or linked.claim_type != "compensable_consequence":
                problems.append(
                    f"apportionment assertion '{assertion.id}' uses "
                    "'industrial_treatment' without a linked compensable-consequence "
                    "contention"
                )
    return problems


def validate_medical_assertions(
    context: AssertionValidationContext,
    history: AssertionWorldProjection,
    ledger: MedicalAssertionLedger,
) -> tuple[str, ...]:
    """Every internal-incoherence problem in *ledger*, in stable order.

    Empty means coherent. **Divergence from world truth never appears here** —
    a contention that a nonindustrial condition is industrial, an opinion that
    endorses against the evidence, a wrong-Hikida refusal: all legal case
    content, all graded rather than rejected. What fails is a reference that
    resolves to nothing, a lifecycle that contradicts itself, a percentage pair
    that cannot sum — an artifact no coherent case file could contain.

    One implementation for both surfaces: the planner calls this with a
    projection built from the plan's ledger, and the truth-tree validator calls
    it with a projection parsed back out of the truth channel.
    """
    problems: list[str] = []
    contention_ids = frozenset(c.id for c in ledger.contentions)
    for contention in ledger.contentions:
        problems.extend(_contention_referential(contention, history))
    for opinion in ledger.medical_opinions:
        problems.extend(_opinion_referential(opinion, history, contention_ids))
    for assertion in ledger.apportionment_assertions:
        problems.extend(_assertion_referential(assertion, history, ledger))
    problems.extend(_opinion_chain(ledger, context))
    problems.extend(_psych_kind_anchoring(ledger, history, context))
    problems.extend(_response_opinion_structure(ledger))
    problems.extend(_revision_kind_predicates(ledger))
    problems.extend(_lifecycle(ledger))
    problems.extend(_grounding_typing(ledger))
    problems.extend(_apportionment_shape(ledger))
    return tuple(problems)


# ---------------------------------------------------------------------------
# Derivation knobs — Fraction-exact, provenance-bearing (note F v1 + sme deltas)
# ---------------------------------------------------------------------------

type AssertionProvenance = Literal[
    "counsel_estimate",
    "counsel_qualitative",
    "counsel_confirmed",
    "counsel_assumed",
    "invented",
    "derived",
]
"""The M2+ assertion-knob provenance vocabulary. Supersedes the clinical
``Tag`` for every new assertion knob (N12/finding 26): the clinical enum lacks
the counsel gradations this layer's calibration ledger uses, and there is no
implicit mapping between the two — shared ``counsel_confirmed`` means the same
thing; ``counsel_unconfirmed`` maps to nothing here."""


@dataclass(frozen=True, slots=True)
class AssertionKnob[T]:
    """One assertion-layer design choice, stating exactly what it rests on.

    Unlike the clinical ``Knob`` (a bare float), the value may be a scalar,
    range, distribution, mapping, set or policy — and every probability-valued
    component is an exact :class:`fractions.Fraction`; floats are forbidden so
    two draws can never disagree about the third decimal of a rate.
    """

    value: T
    provenance: AssertionProvenance
    rationale: str
    source: str

    def __post_init__(self) -> None:
        if not self.rationale.strip() or not self.source.strip():
            raise ValueError(
                f"assertion knob {self.value!r} has an empty rationale or source — "
                "a value with no provenance is the thing this type exists to make "
                "impossible"
            )


CONTENTION_RATE_RANGE = AssertionKnob[tuple[Fraction, Fraction]](
    value=(Fraction(1, 10), Fraction(1, 4)),
    provenance="counsel_estimate",
    rationale="Counsel: contentions are fact-driven, arising 'when the facts dictate it, 10-25%'.",
    source="sme-answers.md q5 (2026-08-10).",
)

P_CONTENTION_GIVEN_CONDITION = AssertionKnob[Fraction](
    value=Fraction(7, 40),
    provenance="derived",
    rationale="Midpoint of counsel's 0.10-0.25 band, per eligible condition candidate only.",
    source="Derived from CONTENTION_RATE_RANGE; restriction per spec-check finding 16.",
)

P_PRIOR_CLAIM_CONTENTION = AssertionKnob[Fraction](
    value=Fraction(3, 20),
    provenance="invented",
    rationale="Overlapping prior claims are argued somewhat less often than live conditions.",
    source="AJC-61 design calibration; no counsel rate supplied.",
)

P_PRIOR_AWARD_CONTENTION = AssertionKnob[Fraction](
    value=Fraction(1, 5),
    provenance="invented",
    rationale="A conclusively presumed overlapping award is close to a free defense argument.",
    source="AJC-61 design calibration; no counsel rate supplied.",
)

P_SIBTF_CONTENTION = AssertionKnob[Fraction](
    value=Fraction(1, 10),
    provenance="invented",
    rationale="SIBTF claims are rare relative to their qualifying evidence.",
    source="AJC-61 design calibration; no counsel rate supplied.",
)

P_FIREFIGHTER_CONTENTION = AssertionKnob[Fraction](
    value=Fraction(1, 5),
    provenance="invented",
    rationale="An oncology diagnosis under an explicit presumption hook is usually argued.",
    source="AJC-61 design calibration; no counsel rate supplied.",
)

QUALITY_TARGET_WEIGHTS = AssertionKnob[tuple[Fraction, Fraction, Fraction]](
    value=(
        Fraction(4, 5),
        Fraction(2, 15),
        Fraction(1, 15),
    ),
    provenance="counsel_estimate",
    rationale=(
        "Counsel: ~80% of real opinions read as supported; the thin:unsupportable "
        "2:1 residual split is invented. A target selects a construction RECIPE — "
        "the grade itself is always rederived, never copied."
    ),
    source="sme-answers.md q7 (supported mass); residual split AJC-61 design calibration.",
)

OPINION_RECIPE_WEIGHTS = AssertionKnob[tuple[Fraction, Fraction, Fraction]](
    value=(
        Fraction(15, 16),
        Fraction(1, 24),
        Fraction(1, 48),
    ),
    provenance="derived",
    rationale=(
        "Counsel's ~80% figure (q7) describes REALIZED opinions, and an "
        "opinion's grade is the worst of everything it stands behind: the "
        "B.6 lifecycle knobs (final omission, the zero-share defect) and the "
        "worst-of endorsement/row drag land on top of whatever the "
        "foundation recipe builds, and a thin or unsupportable foundation "
        "recipe never grades supported. This mix is the sanctioned "
        "construction adjustment (Part 3:659): the CALIBRATION solve used "
        "the fix-round-1 cohort's supported-recipe conditional rounded to "
        "0.8267 (15/16 x 0.8267 = 0.775, mid-band) — calibration "
        "arithmetic, not a claim about any later cohort. The REALIZED "
        "finite-cohort measurements are pinned exactly in "
        "tests/assertion_cohort.py and asserted by the property suite; the "
        "thin:unsupportable residual keeps counsel's 2:1 split."
    ),
    source=(
        "Derived from QUALITY_TARGET_WEIGHTS and the measured 6,000-case "
        "cohort drag (fix round 1, PR #44); realized values pinned in "
        "tests/assertion_cohort.py."
    ),
)

P_PSYCH_COMPONENT = AssertionKnob[Fraction](
    value=Fraction(9, 20),
    provenance="counsel_estimate",
    rationale="Counsel: 40-50% of the caseload carries a psych component, primary or add-on.",
    source="sme-answers.md q9 (2026-08-10).",
)

P_PSYCH_ADD_ON_CONTENTION_GIVEN_COMPONENT = AssertionKnob[Fraction](
    value=Fraction(1, 5),
    provenance="invented",
    rationale=(
        "The barred 4660.1(c) add-on CONTENTION is much rarer than the psych "
        "component itself; split per spec-check finding 17."
    ),
    source="AJC-61 design calibration; no counsel rate supplied.",
)

P_NONZERO_APPORTIONMENT = AssertionKnob[Fraction](
    value=Fraction(3, 4),
    provenance="counsel_estimate",
    rationale="Counsel: '75%ish. apportionment is evidence based' for litigated QME/AME evals.",
    source="sme-answers.md q2 (2026-08-10) — the modern datapoint that officially does not exist.",
)

P_MEDLEGAL_DEFERRAL = AssertionKnob[Fraction](
    value=Fraction(1, 5),
    provenance="invented",
    rationale="A medical-legal-stage evaluator still occasionally defers to a final report.",
    source="AJC-61 design calibration; no counsel rate supplied.",
)

P_FINAL_REPORT_OMITS_APPORTIONMENT = AssertionKnob[Fraction](
    value=Fraction(1, 10),
    provenance="counsel_estimate",
    rationale=(
        "Counsel: final PD reports include the 4663(c) determination 'most of the "
        "time' — the omission is the small plantable defect, not the norm."
    ),
    source="sme-answers.md ruling 2 / q-final-omission (2026-08-10).",
)

P_COMMON_PERCENTAGE_REGISTER = AssertionKnob[Fraction](
    value=Fraction(17, 20),
    provenance="counsel_confirmed",
    rationale=(
        "Counsel: percentages sit 'normally on the fives... or a third'; roundness "
        "is NOT a tell, excess granularity is. Ruling Set Three confirmed the 0.85 "
        "mass exactly (R48); the denominator is every newly sampled allocated "
        "percentage, including a changed supplemental/deposition row. Percentage "
        "roundness never affects quality."
    ),
    source=(
        "sme-answers.md q4, Ruling Set Three (AJC-62 Part 3 R48); anti-clamp rule "
        "per frequency-priors-calibration.md."
    ),
)

P_EVIDENCE_DISTRACTOR = AssertionKnob[Fraction](
    value=Fraction(1, 4),
    provenance="invented",
    rationale=(
        "One irrelevant-but-visible reviewed record at a label-independent rate, so "
        "record composition cannot separate the quality classes."
    ),
    source="AJC-61 design calibration; no counsel rate supplied.",
)

P_PTP_ENDORSE_SUPPORTED = AssertionKnob[Fraction](
    value=Fraction(3, 5),
    provenance="counsel_qualitative",
    rationale="Treaters lean toward their patient's supported claims without being evaluators.",
    source="Operationalization of counsel's qualitative PTP-adoption answer (sme-answers.md q6).",
)

P_PTP_ENDORSE_INDETERMINATE = AssertionKnob[Fraction](
    value=Fraction(7, 20),
    provenance="invented",
    rationale="A treater sometimes adopts an indeterminate claim a med-legal evaluator would not.",
    source="AJC-61 design calibration; no counsel rate supplied.",
)

P_PTP_ENDORSE_CONTRADICTED = AssertionKnob[Fraction](
    value=Fraction(1, 10),
    provenance="invented",
    rationale="Rarely, a treater endorses against the record — realistic, and graded down.",
    source="AJC-61 design calibration; no counsel rate supplied.",
)

P_PSYCH_PREDOMINANT_CAUSE_DENIAL = AssertionKnob[Fraction](
    value=Fraction(3, 20),
    provenance="invented",
    rationale="Interpretation of counsel's 'low' share for predominant-cause psych denials.",
    source="sme-answers.md q10 direction; rate AJC-61 design calibration.",
)

P_GFPA_DEFENSE = AssertionKnob[Fraction](
    value=Fraction(1, 10),
    provenance="invented",
    rationale="Interpretation of counsel's 'low' share for good-faith-personnel-action defenses.",
    source="sme-answers.md q11 direction; rate AJC-61 design calibration.",
)

P_ZERO_SHARE_DEFECT_GIVEN_NONZERO_MISS = AssertionKnob[Fraction](
    value=Fraction(1, 2),
    provenance="invented",
    rationale=(
        "When substantial nonindustrial evidence exists and the nonzero draw misses, "
        "half the misses become the deliberate contradicted-zero-share defect and "
        "half a graded unable-to-approximate."
    ),
    source="AJC-61 design calibration per Part 4 N10 disposition.",
)

EVIDENCE_BUDGET_MIX = AssertionKnob[tuple[Fraction, Fraction, Fraction]](
    value=(Fraction(7, 20), Fraction(2, 5), Fraction(1, 4)),
    provenance="invented",
    rationale="Vary evidence coverage without making reviewed-record count a quality-label proxy.",
    source="AJC-61 design calibration; no counsel rate supplied.",
)
"""Weights for evidence budgets ``(1, 2, 3)`` reviewed records."""

COMMON_NONINDUSTRIAL_PERCENTAGES: Final[tuple[int, ...]] = (
    5,
    10,
    15,
    20,
    25,
    30,
    33,
    35,
    40,
    45,
    50,
    55,
    60,
    65,
    67,
    70,
    75,
    80,
    85,
    90,
    95,
)
"""The register real percentages cluster on — fives, thirds, quarters. Drawn at
:data:`P_COMMON_PERCENTAGE_REGISTER`; the remaining mass draws from 1..99
excluding this tuple, so granular values exist and never clamp to a folk set."""

ASSERTION_KNOBS: Final[dict[str, AssertionKnob]] = {
    "CONTENTION_RATE_RANGE": CONTENTION_RATE_RANGE,
    "P_CONTENTION_GIVEN_CONDITION": P_CONTENTION_GIVEN_CONDITION,
    "P_PRIOR_CLAIM_CONTENTION": P_PRIOR_CLAIM_CONTENTION,
    "P_PRIOR_AWARD_CONTENTION": P_PRIOR_AWARD_CONTENTION,
    "P_SIBTF_CONTENTION": P_SIBTF_CONTENTION,
    "P_FIREFIGHTER_CONTENTION": P_FIREFIGHTER_CONTENTION,
    "OPINION_RECIPE_WEIGHTS": OPINION_RECIPE_WEIGHTS,
    "QUALITY_TARGET_WEIGHTS": QUALITY_TARGET_WEIGHTS,
    "P_PSYCH_COMPONENT": P_PSYCH_COMPONENT,
    "P_PSYCH_ADD_ON_CONTENTION_GIVEN_COMPONENT": P_PSYCH_ADD_ON_CONTENTION_GIVEN_COMPONENT,
    "P_NONZERO_APPORTIONMENT": P_NONZERO_APPORTIONMENT,
    "P_MEDLEGAL_DEFERRAL": P_MEDLEGAL_DEFERRAL,
    "P_FINAL_REPORT_OMITS_APPORTIONMENT": P_FINAL_REPORT_OMITS_APPORTIONMENT,
    "P_COMMON_PERCENTAGE_REGISTER": P_COMMON_PERCENTAGE_REGISTER,
    "P_EVIDENCE_DISTRACTOR": P_EVIDENCE_DISTRACTOR,
    "P_PTP_ENDORSE_SUPPORTED": P_PTP_ENDORSE_SUPPORTED,
    "P_PTP_ENDORSE_INDETERMINATE": P_PTP_ENDORSE_INDETERMINATE,
    "P_PTP_ENDORSE_CONTRADICTED": P_PTP_ENDORSE_CONTRADICTED,
    "P_PSYCH_PREDOMINANT_CAUSE_DENIAL": P_PSYCH_PREDOMINANT_CAUSE_DENIAL,
    "P_GFPA_DEFENSE": P_GFPA_DEFENSE,
    "P_ZERO_SHARE_DEFECT_GIVEN_NONZERO_MISS": P_ZERO_SHARE_DEFECT_GIVEN_NONZERO_MISS,
    "EVIDENCE_BUDGET_MIX": EVIDENCE_BUDGET_MIX,
}
"""Every assertion knob, by name — the completeness surface the oracle sweeps.

Explicit deferrals (named milestones, not omissions): ``p_defense_escalation``
rides AJC-62's surface chain with M5 finalizing its WPI conditioning;
``p_serious_unrelated_dx_during_claim`` (~0.025) needs an AJC-60 follow-up
before AJC-62, because M2 may not invent a condition after ``MedicalHistory``
is derived. ``SIBTF_DISABLING_SEVERITIES`` is deliberately NOT restated here —
:func:`~wc_caseload_engine.medical_history.sibtf_grounding` stays the single
SIBTF policy source."""


# ---------------------------------------------------------------------------
# M3 medical-story knobs (AJC-62 Part 3, R48-R58) — definitions and provenance
# land at R77 step 3; the samplers that CONSUME them arrive with steps 4-8.
# Provenance vocabulary for every M3 knob is R60's four members only:
# counsel_confirmed | counsel_qualitative | derived | invented.
# ---------------------------------------------------------------------------

P_DEFENSE_CONTEST = AssertionKnob[Fraction](
    value=Fraction(13, 20),
    provenance="counsel_confirmed",
    rationale=(
        "Counsel ruled the defense contests an eligible apportionment/psych "
        "finding at exactly 0.65. Denominator: every raw sampled R30-eligible "
        "(actor, opinion, contention) opportunity before bundling, explicit "
        "collision removal, semantic caps, document controls, or date "
        "feasibility — both R30 disposition classes (determined adverse "
        "objection paths and deferred/unaddressed completion paths). Never "
        "conditioned on WPI, quality, document availability, or future money."
    ),
    source="sme-answers.md, Ruling Set Three (AJC-62 Part 3 R48).",
)

P_PTP_INDUSTRIAL_AOE_COE = AssertionKnob[Fraction](
    value=Fraction(19, 20),
    provenance="counsel_confirmed",
    rationale=(
        "Counsel ruled the sampled treating physician independently finds "
        "industrial AOE/COE at exactly 0.95. Denominator: every sampled PTP "
        "base_report opinion; explicit PTP opinions are excluded. The draw "
        "never inspects advocacy, file perspective, quality, or QME/AME "
        "results (R16 independence)."
    ),
    source="sme-answers.md, Ruling Set Three (AJC-62 Part 3 R48).",
)

P_QME_AME_RESPONSIVE_ADOPTION = AssertionKnob[Fraction](
    value=Fraction(1, 4),
    provenance="counsel_confirmed",
    rationale=(
        "Counsel ruled the QME/AME responsively adopts an advocated theory at "
        "exactly 0.25. Denominator: every sampled QME/AME opinion-contention "
        "pair satisfying all three R38 predicates (evidence-supportable, an "
        "earlier qualifying communication targets the opinion, no explicit "
        "disposition controls the pair) before controls. A miss becomes "
        "independent concurrence, never silence."
    ),
    source="sme-answers.md, Ruling Set Three (AJC-62 Part 3 R48).",
)

P_IMR_REQUEST_GIVEN_UPHELD_DENIAL = AssertionKnob[Fraction](
    value=Fraction(1, 2),
    provenance="counsel_confirmed",
    rationale=(
        "Counsel ruled IMR is requested for exactly 0.5 of UR denials. "
        "Denominator: every effective upheld UR denial for which imr was not "
        "authored; explicit imr values (including false) stay authoritative "
        "and draw nothing."
    ),
    source="sme-answers.md, Ruling Set Three (AJC-62 Part 3 R48).",
)

P_DEFENSE_CONTEST_OUTSIDE_R30 = AssertionKnob[Fraction](
    value=Fraction(0, 1),
    provenance="derived",
    rationale=(
        "A contention outside R30's eligibility creates no sampled defense "
        "chain — the structural consequence of counsel's eligibility rule, "
        "not a tunable rate. Explicit chains remain permitted."
    ),
    source="AJC-62 Part 3 R48; structural consequence of the R30 predicate.",
)

PTP_AOE_COE_COMPLEMENT_WEIGHTS = AssertionKnob[dict[str, Fraction]](
    value={
        "nonindustrial": Fraction(3, 5),
        "deferred": Fraction(2, 5),
    },
    provenance="invented",
    rationale=(
        "The 0.05 PTP complement splits 0.03 nonindustrial / 0.02 deferred so "
        "both contrary and deferred treating reports remain observable. The "
        "0.95 direction is counsel's (P_PTP_INDUSTRIAL_AOE_COE); this exact "
        "split is calibration, expressly not attributed to counsel."
    ),
    source="AJC-62 Part 3 calibration (R49).",
)

P_APPLICANT_DIRECT_PSYCH_FRAMING_GIVEN_CONSEQUENCE = AssertionKnob[Fraction](
    value=Fraction(3, 4),
    provenance="invented",
    rationale=(
        "A sampled applicant contention frames a compensable-consequence psych "
        "condition as direct at 0.75; the complement keeps the honest "
        "compensable_consequence framing. Eligible only for a sampled "
        "applicant contention on a consequence-classified world condition "
        "lacking an explicit classification."
    ),
    source="AJC-62 Part 3 calibration (R49); direction counsel-confirmed.",
)

P_PTP_DIRECT_PSYCH_CLASSIFICATION_GIVEN_CONSEQUENCE = AssertionKnob[Fraction](
    value=Fraction(3, 5),
    provenance="invented",
    rationale=(
        "A sampled PTP opinion classifies a compensable-consequence psych "
        "condition as direct at 0.6, independent of applicant framing and "
        "advocacy; the complement is compensable_consequence."
    ),
    source="AJC-62 Part 3 calibration (R49); direction counsel-confirmed.",
)

P_QME_AME_INDETERMINATE_DEFERRED = AssertionKnob[Fraction](
    value=Fraction(3, 5),
    provenance="invented",
    rationale=(
        "An indeterminate QME/AME contention defers at 0.6 and is otherwise "
        "unaddressed. The stream chooses only between those two results; it "
        "can never produce adoption or concurrence."
    ),
    source="AJC-62 Part 3 calibration (R49).",
)

P_APPLICANT_CONTEST = AssertionKnob[Fraction](
    value=Fraction(1, 2),
    provenance="invented",
    rationale=(
        "An applicant contests a determined-adverse R29 row at 0.5 when the "
        "permitted contesting actor is applicant. Bounded-file realism under "
        "the counsel-fixed defense rate."
    ),
    source="AJC-62 Part 3 calibration (R50).",
)

P_APPLICANT_COMPLETION_REQUEST = AssertionKnob[Fraction](
    value=Fraction(13, 20),
    provenance="invented",
    rationale=(
        "An applicant requests completion of a deferred/unaddressed R29 row "
        "at 0.65 when the permitted requesting actor is applicant. No second "
        "incidence draw occurs after a path has been selected."
    ),
    source="AJC-62 Part 3 calibration (R50).",
)

ADVERSE_CONTEST_PATH_WEIGHTS = AssertionKnob[dict[str, tuple[tuple[str, Fraction], ...]]](
    value={
        "applicant": (
            ("objection_only", Fraction(1, 2)),
            ("objection_supplemental", Fraction(3, 10)),
            ("objection_deposition", Fraction(3, 20)),
            ("objection_supplemental_deposition", Fraction(1, 20)),
        ),
        "defense": (
            ("objection_only", Fraction(2, 5)),
            ("objection_supplemental", Fraction(3, 10)),
            ("objection_deposition", Fraction(1, 5)),
            ("objection_supplemental_deposition", Fraction(1, 10)),
        ),
    },
    provenance="invented",
    rationale=(
        "Ordered ContestPath weights for determined-adverse rows, per actor. "
        "The selected path is the proposed semantic path; R31 truncation may "
        "shorten it but never redraws it."
    ),
    source="AJC-62 Part 3 calibration (R50).",
)

COMPLETION_PATH_WEIGHTS = AssertionKnob[dict[str, tuple[tuple[str, Fraction], ...]]](
    value={
        "applicant": (
            ("supplemental_only", Fraction(17, 20)),
            ("supplemental_deposition", Fraction(3, 20)),
        ),
        "defense": (
            ("supplemental_only", Fraction(3, 4)),
            ("supplemental_deposition", Fraction(1, 4)),
        ),
    },
    provenance="invented",
    rationale=(
        "Ordered ContestPath weights for deferred/unaddressed completion "
        "rows, per actor — a completion request has no conclusion to object "
        "to, so both members start at the supplemental request."
    ),
    source="AJC-62 Part 3 calibration (R50).",
)

DEFENSE_THEORY_COUNT_WEIGHTS = AssertionKnob[tuple[tuple[int, Fraction], ...]](
    value=(
        (1, Fraction(3, 4)),
        (2, Fraction(1, 5)),
        (3, Fraction(1, 20)),
    ),
    provenance="invented",
    rationale=(
        "One count draw per sampled defense chain; selection then proceeds "
        "weighted-without-replacement in DefenseContestTheory declaration "
        "order with exact-Fraction renormalization."
    ),
    source="AJC-62 Part 3 calibration (R51).",
)

DEFENSE_THEORY_WEIGHTS = AssertionKnob[tuple[tuple[str, Fraction], ...]](
    value=(
        ("insufficient_investigation", Fraction(7, 20)),
        ("post_termination", Fraction(7, 20)),
        ("lack_of_substantial_medical_evidence", Fraction(3, 10)),
    ),
    provenance="invented",
    rationale=(
        "The three content categories are counsel_confirmed (Ruling Set "
        "Three); their exact relative weights are calibration. Selection is "
        "weighted without replacement in this declaration order, and the "
        "ordered selected tuple is copied to every attorney-authored document "
        "in the chain."
    ),
    source=(
        "Categories: sme-answers.md, Ruling Set Three. Weights: AJC-62 Part 3 calibration (R51)."
    ),
)

ADVOCACY_INCIDENCE = AssertionKnob[dict[tuple[str, str], Fraction]](
    value={
        ("ptp", "applicant"): Fraction(3, 5),
        ("qme", "applicant"): Fraction(7, 10),
        ("ame", "applicant"): Fraction(3, 5),
        ("qme", "defense"): Fraction(11, 20),
        ("ame", "defense"): Fraction(1, 2),
    },
    provenance="invented",
    rationale=(
        "Advocacy incidence by (target role, actor); all other sampled pairs "
        "have probability zero. One incidence draw per R28-eligible "
        "contention/target pair; eligibility never inspects evidence "
        "disposition or quality."
    ),
    source="AJC-62 Part 3 calibration (R52); target ordering per R28.",
)

ADVOCACY_BUNDLE_SIZE_WEIGHTS = AssertionKnob[tuple[tuple[int, Fraction], ...]](
    value=(
        (1, Fraction(1, 2)),
        (2, Fraction(7, 20)),
        (3, Fraction(3, 20)),
    ),
    provenance="invented",
    rationale=(
        "One weighted size draw per provisional sampled bundle, renormalized "
        "over the sizes not exceeding the remaining winners; a single "
        "provisional winner forms a size-one letter without a draw."
    ),
    source="AJC-62 Part 3 calibration (R52).",
)

REVISION_KIND_WEIGHTS = AssertionKnob[dict[str, tuple[Fraction, ...]]](
    value={
        "supplemental_after_objection": (
            Fraction(7, 20),
            Fraction(3, 20),
            Fraction(3, 20),
            Fraction(1, 4),
            Fraction(1, 10),
        ),
        "supplemental_after_completion": (
            Fraction(3, 20),
            Fraction(1, 5),
            Fraction(1, 5),
            Fraction(3, 10),
            Fraction(3, 20),
        ),
        "deposition_examining_base": (
            Fraction(13, 20),
            Fraction(0, 1),
            Fraction(1, 10),
            Fraction(1, 5),
            Fraction(1, 20),
        ),
        "deposition_examining_supplemental": (
            Fraction(7, 10),
            Fraction(0, 1),
            Fraction(1, 10),
            Fraction(3, 20),
            Fraction(1, 20),
        ),
    },
    provenance="invented",
    rationale=(
        "Revision-kind weights per trigger stage, in exact OpinionRevisionKind "
        "declaration order. Structurally ineligible kinds are removed and the "
        "remainder renormalized BEFORE one draw — never draw-and-retry. The "
        "completion mix is more revision-heavy because the predecessor "
        "omitted or deferred the issue; deposition is mostly clarification "
        "and new_records_no_change always has zero deposition weight."
    ),
    source="AJC-62 Part 3 calibration (R54).",
)

GRANULAR_NONINDUSTRIAL_PERCENTAGES: Final[tuple[int, ...]] = tuple(
    value for value in range(1, 100) if value not in COMMON_NONINDUSTRIAL_PERCENTAGES
)
"""The exactly-78-integer continuous remainder of 1..99 (R55). The granular
selector implements the continuous latent law (uniform by Lebesgue measure over
the union of [g-0.5, g+0.5) intervals) so a non-register percentage is never
the output of a nearest-common-value clamp."""

ADVOCACY_LEAD_DAYS = AssertionKnob[tuple[int, int]](
    value=(14, 45),
    provenance="invented",
    rationale=(
        "Inclusive lead days a proposed advocacy letter precedes its target "
        "report; one randint(lower, upper) draw before R34 fitting, "
        "subtracted from the target report date."
    ),
    source="AJC-62 Part 3 calibration (R56); ordinary service intervals.",
)

OBJECTION_LAG_DAYS = AssertionKnob[tuple[int, int]](
    value=(10, 30),
    provenance="invented",
    rationale=(
        "Inclusive lag days from the objected-to report date; one "
        "randint(lower, upper) draw before R34 fitting."
    ),
    source="AJC-62 Part 3 calibration (R56); ordinary service intervals.",
)

SUPPLEMENTAL_REQUEST_LAG_DAYS = AssertionKnob[tuple[int, int]](
    value=(7, 21),
    provenance="invented",
    rationale=(
        "Inclusive lag days from the objection date on objection-led paths "
        "and from the target report date on completion paths; one "
        "randint(lower, upper) draw before R34 fitting."
    ),
    source="AJC-62 Part 3 calibration (R56); ordinary service intervals.",
)

SUPPLEMENTAL_REPORT_LAG_DAYS = AssertionKnob[tuple[int, int]](
    value=(30, 90),
    provenance="invented",
    rationale=(
        "Inclusive lag days from the supplemental-request date; one "
        "randint(lower, upper) draw before R34 fitting."
    ),
    source="AJC-62 Part 3 calibration (R56); ordinary evaluator intervals.",
)

DEPOSITION_LAG_DAYS = AssertionKnob[tuple[int, int]](
    value=(30, 120),
    provenance="invented",
    rationale=(
        "Inclusive lag days from the examined-report date; one "
        "randint(lower, upper) draw before R34 fitting."
    ),
    source="AJC-62 Part 3 calibration (R56); ordinary discovery intervals.",
)

IMR_APPLICATION_LAG_DAYS = AssertionKnob[tuple[int, int]](
    value=(10, 30),
    provenance="derived",
    rationale=(
        "Inclusive application lag for an M3-effective IMR, preserving the "
        "existing lifecycle range. A legacy authored IMR chain still consumes "
        "and discards the lifecycle RNG's two date draws before the semantic "
        "values replace them; a 0.5-channel IMR uses only the private M3 "
        "streams."
    ),
    source=(
        "Existing lifecycle implementation; LC section 4610.5 window "
        "discipline (AJC-62 Part 3 R56)."
    ),
)

IMR_DECISION_LAG_DAYS = AssertionKnob[tuple[int, int]](
    value=(30, 60),
    provenance="derived",
    rationale=(
        "Inclusive decision lag from the actual application date, preserving "
        "the existing lifecycle range."
    ),
    source=(
        "Existing lifecycle implementation; LC section 4610.5 window "
        "discipline (AJC-62 Part 3 R56)."
    ),
)

UR_DECISION_WEIGHTS_WHEN_UNSTATED = AssertionKnob[tuple[tuple[str, Fraction], ...]](
    value=(
        ("upheld", Fraction(1, 2)),
        ("overturned", Fraction(1, 2)),
    ),
    provenance="derived",
    rationale=(
        "Applies only when the UR decision is unresolved — preserves the "
        "current substrate's uniform 'random' choice. A stated decision "
        "remains authoritative and draws nothing."
    ),
    source="Existing lifecycle/substrate behavior (AJC-62 Part 3 R57).",
)

IMR_OUTCOME_WEIGHTS_WHEN_UNSTATED = AssertionKnob[tuple[tuple[str, Fraction], ...]](
    value=(
        ("upheld", Fraction(1, 2)),
        ("overturned", Fraction(1, 2)),
    ),
    provenance="derived",
    rationale=(
        "Applies only when imr_outcome is unresolved — preserves the current "
        "substrate's uniform choice. The auto-profile's independently "
        "generated 0.80/0.20 outcome, once a resolved seed value, is never "
        "overwritten."
    ),
    source="Existing lifecycle/substrate behavior (AJC-62 Part 3 R57).",
)

IMR_APPLICATION_FIELD_OCCUPANCY = AssertionKnob[dict[str, Fraction]](
    value={
        "disputed_treatment": Fraction(19, 20),
        "diagnosis_icd10": Fraction(3, 5),
        "ur_determination_attached": Fraction(7, 10),
        "supporting_record_subtypes": Fraction(7, 20),
        "clinical_rebuttal": Fraction(1, 4),
        "mtus_citations": Fraction(3, 20),
    },
    provenance="invented",
    rationale=(
        "Per-field occupancy of the sampled applicant-attorney IMR "
        "application, one independent draw per eligible field — "
        "operationalizing counsel's confirmed observation that applicant "
        "attorneys generally under-work IMR. The exact sparse rates are not "
        "attributed to counsel; under-working is inferable only from missing "
        "or generic work product, never a truth-like field."
    ),
    source="AJC-62 Part 3 calibration (R58); direction counsel-confirmed.",
)

SUPPORTING_RECORD_COUNT_WEIGHTS = AssertionKnob[tuple[tuple[int, Fraction], ...]](
    value=(
        (1, Fraction(3, 5)),
        (2, Fraction(3, 10)),
        (3, Fraction(1, 10)),
    ),
    provenance="invented",
    rationale=(
        "One count draw for a populated supporting-record list, clipped only "
        "to the distinct grounded values available; a count above "
        "availability never redraws."
    ),
    source="AJC-62 Part 3 calibration (R58).",
)

MTUS_CITATION_COUNT_WEIGHTS = AssertionKnob[tuple[tuple[int, Fraction], ...]](
    value=(
        (1, Fraction(4, 5)),
        (2, Fraction(1, 5)),
    ),
    provenance="invented",
    rationale=(
        "One count draw for a populated MTUS-citation list, clipped only to "
        "the distinct grounded citations available."
    ),
    source="AJC-62 Part 3 calibration (R58).",
)

P_IMR_CASE_SPECIFIC_REBUTTAL = AssertionKnob[Fraction](
    value=Fraction(1, 2),
    provenance="invented",
    rationale=(
        "When clinical_rebuttal is populated, case-specific versus generic "
        "content splits at 0.5. Both are professionally written; neither "
        "carries a quality label."
    ),
    source="AJC-62 Part 3 calibration (R58).",
)

MEDICAL_STORY_KNOBS: Final[dict[str, AssertionKnob]] = {
    "P_DEFENSE_CONTEST": P_DEFENSE_CONTEST,
    "P_PTP_INDUSTRIAL_AOE_COE": P_PTP_INDUSTRIAL_AOE_COE,
    "P_QME_AME_RESPONSIVE_ADOPTION": P_QME_AME_RESPONSIVE_ADOPTION,
    "P_IMR_REQUEST_GIVEN_UPHELD_DENIAL": P_IMR_REQUEST_GIVEN_UPHELD_DENIAL,
    "P_COMMON_PERCENTAGE_REGISTER": P_COMMON_PERCENTAGE_REGISTER,
    "P_DEFENSE_CONTEST_OUTSIDE_R30": P_DEFENSE_CONTEST_OUTSIDE_R30,
    "PTP_AOE_COE_COMPLEMENT_WEIGHTS": PTP_AOE_COE_COMPLEMENT_WEIGHTS,
    "P_APPLICANT_DIRECT_PSYCH_FRAMING_GIVEN_CONSEQUENCE": (
        P_APPLICANT_DIRECT_PSYCH_FRAMING_GIVEN_CONSEQUENCE
    ),
    "P_PTP_DIRECT_PSYCH_CLASSIFICATION_GIVEN_CONSEQUENCE": (
        P_PTP_DIRECT_PSYCH_CLASSIFICATION_GIVEN_CONSEQUENCE
    ),
    "P_QME_AME_INDETERMINATE_DEFERRED": P_QME_AME_INDETERMINATE_DEFERRED,
    "P_APPLICANT_CONTEST": P_APPLICANT_CONTEST,
    "P_APPLICANT_COMPLETION_REQUEST": P_APPLICANT_COMPLETION_REQUEST,
    "ADVERSE_CONTEST_PATH_WEIGHTS": ADVERSE_CONTEST_PATH_WEIGHTS,
    "COMPLETION_PATH_WEIGHTS": COMPLETION_PATH_WEIGHTS,
    "DEFENSE_THEORY_COUNT_WEIGHTS": DEFENSE_THEORY_COUNT_WEIGHTS,
    "DEFENSE_THEORY_WEIGHTS": DEFENSE_THEORY_WEIGHTS,
    "ADVOCACY_INCIDENCE": ADVOCACY_INCIDENCE,
    "ADVOCACY_BUNDLE_SIZE_WEIGHTS": ADVOCACY_BUNDLE_SIZE_WEIGHTS,
    "REVISION_KIND_WEIGHTS": REVISION_KIND_WEIGHTS,
    "COMMON_NONINDUSTRIAL_PERCENTAGES": AssertionKnob[tuple[int, ...]](
        value=COMMON_NONINDUSTRIAL_PERCENTAGES,
        provenance="counsel_qualitative",
        rationale=(
            "The M2-frozen implementation of counsel's fives/thirds/quarters "
            "register, consumed unchanged by R55's revision selector. Base M2 "
            "rows keep the existing percentage-register stream and value "
            "selector byte-for-byte."
        ),
        source="sme-answers.md q4 direction; M2-frozen pool (AJC-62 Part 3 R55).",
    ),
    "GRANULAR_NONINDUSTRIAL_PERCENTAGES": AssertionKnob[tuple[int, ...]](
        value=GRANULAR_NONINDUSTRIAL_PERCENTAGES,
        provenance="derived",
        rationale=(
            "The continuous remainder — exactly the 78 integers of 1..99 "
            "outside the common pool, selected through the R55 continuous "
            "latent law so no granular value is a nearest-common clamp."
        ),
        source=("Anti-clamp consequence of the M2 pool and integer schema (AJC-62 Part 3 R55)."),
    ),
    "ADVOCACY_LEAD_DAYS": ADVOCACY_LEAD_DAYS,
    "OBJECTION_LAG_DAYS": OBJECTION_LAG_DAYS,
    "SUPPLEMENTAL_REQUEST_LAG_DAYS": SUPPLEMENTAL_REQUEST_LAG_DAYS,
    "SUPPLEMENTAL_REPORT_LAG_DAYS": SUPPLEMENTAL_REPORT_LAG_DAYS,
    "DEPOSITION_LAG_DAYS": DEPOSITION_LAG_DAYS,
    "IMR_APPLICATION_LAG_DAYS": IMR_APPLICATION_LAG_DAYS,
    "IMR_DECISION_LAG_DAYS": IMR_DECISION_LAG_DAYS,
    "UR_DECISION_WEIGHTS_WHEN_UNSTATED": UR_DECISION_WEIGHTS_WHEN_UNSTATED,
    "IMR_OUTCOME_WEIGHTS_WHEN_UNSTATED": IMR_OUTCOME_WEIGHTS_WHEN_UNSTATED,
    "IMR_APPLICATION_FIELD_OCCUPANCY": IMR_APPLICATION_FIELD_OCCUPANCY,
    "SUPPORTING_RECORD_COUNT_WEIGHTS": SUPPORTING_RECORD_COUNT_WEIGHTS,
    "MTUS_CITATION_COUNT_WEIGHTS": MTUS_CITATION_COUNT_WEIGHTS,
    "P_IMR_CASE_SPECIFIC_REBUTTAL": P_IMR_CASE_SPECIFIC_REBUTTAL,
}
"""Every R48-R58 medical-story knob by name (R60), including the existing
:data:`P_COMMON_PERCENTAGE_REGISTER` object BY IDENTITY — one knob, two
registries, zero duplication. Weighted choices consume these through
integerized exact weights or exact cumulative comparison; ``random.choices()``
with float weights is forbidden. R63's statistical denominator floors and the
coverage-only exact-pin floors are recorded at R77 step 12 with the
measurement they gate — never guessed here in advance."""


# ---------------------------------------------------------------------------
# RNG streams — new namespace, semantic keys, independent seeding
# ---------------------------------------------------------------------------

ASSERTION_RNG_NAMESPACE: Final[str] = "medical-assertions"
"""Never ``medical:`` — that namespace is M1's, and reusing it would re-roll
draws that already ship. Independent seeding per family/key means new families
and knobs cannot shift existing draws."""

ASSERTION_RNG_FAMILIES: Final[tuple[str, ...]] = (
    "contention-incidence",
    "contention-type",
    "quality-target",
    "psych-component",
    "psych-add-on-contention",
    "medical-legal-deferral",
    "final-omission",
    "nonzero-apportionment",
    "determination-kind",
    "evidence-budget",
    "evidence-distractor",
    "percentage-register",
    "ptp-disposition",
    "thin-defect",
    "unsupportable-defect",
)
"""The frozen 15-family registry (Part 4 B.2-B.3). QME/AME disposition has NO
stream on purpose — it is completely evidence-conditioned. The salt oracle
asserts the constructed set equals exactly this tuple."""

type SemanticKey = tuple[object, ...]


def _assertion_rng(seed: CaseSeed, family: str, stable_key: str) -> random.Random:
    """A fresh stream under ``medical-assertions:<family>:<key>``.

    ``stable_key`` is always a *semantic* candidate key — a condition id, an
    award id, ``case`` — never an assigned ``ctn-NN`` id, a list position or a
    counter, so adding an explicit entry cannot re-roll an unrelated
    candidate's draws. Callers go through the module namespace
    (``medical_assertions._assertion_rng``) so the absent-gate probe can
    monkeypatch the attribute.
    """
    if family not in ASSERTION_RNG_FAMILIES:
        raise ValueError(
            f"unknown assertion rng family {family!r}; register it in "
            "ASSERTION_RNG_FAMILIES so the salt oracle can see it"
        )
    return random.Random(
        derive_seed(seed.rng_seed, f"{ASSERTION_RNG_NAMESPACE}:{family}:{stable_key}")
    )


# ---------------------------------------------------------------------------
# M3 medical-story streams (AJC-62 Part 3, R44-R46) — namespace, exact family
# registry, canonical semantic-key grammar. Policy constants, not probability
# knobs; each carries its rationale/source here (R60).
# ---------------------------------------------------------------------------

MEDICAL_STORY_RNG_NAMESPACE: Final[str] = "medical-story"
"""The single M3 namespace (R44) — never ``medical:`` (M1) and never
``medical-assertions:`` (M2). Every new M3 stochastic decision derives from
``medical-story:{family}:{canonical-semantic-key}``; a single registered
namespace makes completeness mechanically testable and prevents a new loop
decision from consuming an existing stream. Source: AJC-62 Part 3 R44."""

MEDICAL_STORY_RNG_FAMILIES: Final[tuple[str, ...]] = (
    "advocacy-incidence",
    "advocacy-bundle-size",
    "applicant-psych-framing",
    "ptp-aoe-coe-finding",
    "ptp-psych-classification",
    "qme-ame-indeterminate-disposition",
    "qme-ame-responsive-adoption",
    "defense-contest-incidence",
    "applicant-contest-incidence",
    "completion-incidence",
    "contest-path",
    "defense-theory-count",
    "defense-theory-selection",
    "revision-kind",
    "revision-percentage-register",
    "revision-percentage-value",
    "advocacy-lead",
    "objection-lag",
    "supplemental-request-lag",
    "supplemental-report-lag",
    "deposition-lag",
    "ur-decision",
    "imr-request",
    "imr-outcome",
    "imr-application-lag",
    "imr-decision-lag",
    "imr-field-occupancy",
    "imr-field-count",
    "imr-rebuttal-substance",
    "document-format",
    "document-render",
    "document-scan",
    "document-pdf-id",
    "document-doctrine",
)
"""The exact 34-family medical-story registry (R46) — complete and CLOSED for
AJC-62. Each family has exactly the R46 semantic-key suffix and draw site; a
weighted-without-replacement operation may consume multiple draws from its
entity-private stream, and no other entity shares that ``random.Random``.
Date fitting, stable sorting, record selection, collision removal, cap
application, and contest-document chunking are deterministic and never acquire
a family. Source: AJC-62 Part 3 R46."""

MEDICAL_STORY_ASSERTION_LOOP_FAMILIES: Final[frozenset[str]] = frozenset(
    MEDICAL_STORY_RNG_FAMILIES[:21]
)
"""The 21 contention-loop families, callable only when BOTH gates are present
(R44): ``scenario.medical_history`` and ``scenario.medical_assertions``. The
13-family complement — the eight UR/IMR families and the five document-render
families — may run in a history-present/assertions-absent case where Parts 1-2
authorize them. Source: AJC-62 Part 3 R44; Part 2 R25."""

MEDICAL_STORY_TZ_MATRIX: Final[tuple[str, ...]] = (
    "America/Los_Angeles",
    "Australia/Sydney",
)
"""R65 determinism matrix — the two timezones every M3 plan, binding, output
byte, truth channel, leakage result and counter must be identical across.
Policy constant, not a knob; the step-9 determinism tests consume it.
Source: AJC-62 Part 3 R65."""

MEDICAL_STORY_HASH_SEEDS: Final[tuple[str, ...]] = ("0", "424242")
"""R65 determinism matrix — the two ``PYTHONHASHSEED`` values the cross-process
gates run under. Source: AJC-62 Part 3 R65."""

MEDICAL_STORY_REPEAT_GENERATIONS: Final[int] = 2
"""R65 — repeated-generation count for the byte-identity gate.
Source: AJC-62 Part 3 R65."""

type StorySemanticAtom = str | int | bool | None
type StorySemanticKey = tuple[object, ...]


def _normalized_story_atom(value: object) -> object:
    """One R45 normalization step — structural, pre-ID, JSON-representable.

    Exact rules: dates become ISO ``YYYY-MM-DD``; string-backed literals stay
    their literal strings; tuples and lists become arrays WITHOUT reordering;
    sets and frozensets become sorted arrays; a mapping appears only after
    sorting its items by normalized key. Floats, datetimes, model dumps,
    object representations, memory addresses and Python ``hash()`` are
    forbidden — an unrepresentable atom raises instead of degrading to
    ``str(value)``, because a repr carries a memory address and a float
    carries platform formatting.
    """
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, float):  # must precede int: bool handled above
        raise MedicalAssertionError(
            f"medical-story semantic keys forbid floats ({value!r}); use an "
            "exact int, string literal, or Fraction-free structural value"
        )
    if isinstance(value, int):
        return value
    if isinstance(value, dt.datetime):
        raise MedicalAssertionError(
            "medical-story semantic keys forbid datetimes; a clock-flavored "
            "value is not a structural identity — pass the date"
        )
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, (tuple, list)):
        return [_normalized_story_atom(item) for item in value]
    if isinstance(value, (set, frozenset)):
        normalized = [_normalized_story_atom(item) for item in value]
        return sorted(
            normalized,
            key=lambda item: json.dumps(item, ensure_ascii=True, separators=(",", ":")),
        )
    if isinstance(value, Mapping):
        pairs = [
            [_normalized_story_atom(key), _normalized_story_atom(item)]
            for key, item in value.items()
        ]
        return sorted(
            pairs,
            key=lambda pair: json.dumps(pair[0], ensure_ascii=True, separators=(",", ":")),
        )
    raise MedicalAssertionError(
        f"medical-story semantic keys forbid {type(value).__name__} atoms; "
        "only str/int/bool/None, dates, tuples/lists, sets, and mappings are "
        "structural"
    )


def canonical_story_key(key: StorySemanticKey) -> str:
    """The canonical ASCII-JSON string form of one R45 semantic key.

    Exactly ``json.dumps(normalized_key, ensure_ascii=True,
    separators=(",", ":"))`` over the normalized structure — byte-stable
    across process, timezone, hash seed, and interpreter, which is the whole
    reason positions, indices, and object identities are banned from keys.
    """
    return json.dumps(
        _normalized_story_atom(tuple(key)),
        ensure_ascii=True,
        separators=(",", ":"),
    )


def _medical_story_seed(
    seed: CaseSeed,
    family: str,
    semantic_key: StorySemanticKey,
) -> int:
    """The derived seed for one ``medical-story:{family}:{key}`` stream (R44).

    Fail-closed on every R44 precondition: the family must be registered (an
    unregistered constructed family is an implementation failure, not a
    warning); the medical-story gate must be present (no call to either
    helper is permitted when ``scenario.medical_history is None``);
    assertion-loop families additionally require ``scenario.medical_assertions``
    (UR/IMR and document-render families may run history-present/
    assertions-absent per Parts 1-2). Every key begins
    ``("case", seed.case_id, ...)`` — R45's grammar — so two cases can never
    share a stream. Callers in other modules MUST call through the
    ``medical_assertions`` module attribute (never a locally imported alias)
    so the P4 family recorder can observe every construction.
    """
    if family not in MEDICAL_STORY_RNG_FAMILIES:
        raise MedicalAssertionError(
            f"unknown medical-story rng family {family!r}; the R46 registry "
            "is complete and closed for AJC-62 — a new decision must be "
            "registered in MEDICAL_STORY_RNG_FAMILIES, never drawn under a "
            "generic loop rng"
        )
    if seed.scenario.medical_history is None:
        raise MedicalAssertionError(
            "medical-story rng constructed without the medical-story gate: "
            "scenario.medical_history is None, and the absent path must "
            "return before any stream exists (R44/R1)"
        )
    if family in MEDICAL_STORY_ASSERTION_LOOP_FAMILIES and seed.scenario.medical_assertions is None:
        raise MedicalAssertionError(
            f"assertion-loop family {family!r} constructed while "
            "scenario.medical_assertions is None; only UR/IMR and "
            "document-render families may run history-present/"
            "assertions-absent (R44)"
        )
    if len(semantic_key) < 2 or semantic_key[0] != "case" or semantic_key[1] != seed.case_id:
        raise MedicalAssertionError(
            f"medical-story semantic key {semantic_key!r} does not begin "
            f'("case", {seed.case_id!r}, ...); R45 requires the case prefix '
            "on every key"
        )
    return derive_seed(
        seed.rng_seed,
        f"{MEDICAL_STORY_RNG_NAMESPACE}:{family}:{canonical_story_key(semantic_key)}",
    )


def _medical_story_rng(
    seed: CaseSeed,
    family: str,
    semantic_key: StorySemanticKey,
) -> random.Random:
    """A fresh entity-private stream from :func:`_medical_story_seed` (R44).

    Constructs a new ``random.Random`` on every call — it never shares state
    with M1, M2, lifecycle, format, substrate, or module-global RNGs, so a
    weighted-without-replacement consumer can take several draws without any
    other entity observing them.
    """
    return random.Random(_medical_story_seed(seed, family, semantic_key))


# ---------------------------------------------------------------------------
# R77 step 4 — story semantic keys and the disposition/response draw primitives
# ---------------------------------------------------------------------------


def _story_contention_key(
    seed: CaseSeed,
    contention: Contention,
    explicit_contention_ids: frozenset[str],
) -> StorySemanticKey:
    """The R45 ``C`` identity for one completed contention.

    Explicit form carries the authored ID (the one place an ID may appear);
    the sampled form embeds the full M2 rule-6 semantic tuple — the same
    normalized key the suppression pass uses — exactly as the frozen step-3
    grammar pins (``("case", id, "contention", "sampled", <M2 key>)``).
    """
    if contention.id in explicit_contention_ids:
        return ("case", seed.case_id, "contention", "explicit", contention.id)
    return (
        "case",
        seed.case_id,
        "contention",
        "sampled",
        _contention_semantic_key(contention),
    )


def _story_sampled_base_opinion_key(seed: CaseSeed, opinion: MedicalOpinion) -> StorySemanticKey:
    """The R45 ``O`` identity for the sampled stage base opinion.

    ``("case", id, "opinion", "sampled_base", author_role, report_stage,
    report_date, tuple(sorted(relevant C keys)))``. The relevant-C component
    is the EMPTY tuple for M2's single case-level stage opinion: its M2
    semantic identity is ``{author_role}:case`` — the evaluator of the case,
    not of any contention subset — and embedding the contention docket here
    would let an unrelated added explicit contention shift this opinion's
    private draws, which R41 rule 8 forbids. (Interpretation flagged for the
    spec author: R45 leaves "relevant" undefined for the case-level opinion;
    response-opinion keys get their own composition with their genuinely
    bound revisited-C keys when step 5 lands.)
    """
    return (
        "case",
        seed.case_id,
        "opinion",
        "sampled_base",
        opinion.author_role,
        opinion.report_stage,
        opinion.report_date,
        (),
    )


def _ptp_aoe_coe_finding(seed: CaseSeed, opinion_key: StorySemanticKey) -> str:
    """One R49 independent AOE/COE finding for an eligible sampled PTP base
    opinion — ``ptp-aoe-coe-finding``, keyed ``(O,)``.

    Exactly ``0.95 -> industrial``; the complement consumes a second draw from
    the same entity-private stream under the frozen 3/5 nonindustrial : 2/5
    deferred split, so ``0.03 -> nonindustrial`` and ``0.02 -> deferred``. The
    draw inspects nothing beyond the opinion identity: no advocacy letter, no
    letter author/content/date/subtype, no file perspective, no contention
    quality, no QME/AME result (R49/R16).
    """
    rng = _medical_story_rng(seed, "ptp-aoe-coe-finding", ("case", seed.case_id, opinion_key))
    if _fraction_draw(rng, P_PTP_INDUSTRIAL_AOE_COE.value):
        return "industrial"
    complement = PTP_AOE_COE_COMPLEMENT_WEIGHTS.value
    members = tuple(complement)
    index = _weighted_index(rng, tuple(complement[member] for member in members))
    return members[index]


def _applicant_psych_framing(seed: CaseSeed, contention_key: StorySemanticKey) -> str:
    """R49 applicant framing of a consequence-psych contention —
    ``applicant-psych-framing``, keyed ``(C,)``: 3/4 mischaracterized
    ``direct``, complement ``compensable_consequence``."""
    rng = _medical_story_rng(
        seed, "applicant-psych-framing", ("case", seed.case_id, contention_key)
    )
    if _fraction_draw(rng, P_APPLICANT_DIRECT_PSYCH_FRAMING_GIVEN_CONSEQUENCE.value):
        return "direct"
    return "compensable_consequence"


def _ptp_psych_classification(
    seed: CaseSeed,
    opinion_key: StorySemanticKey,
    contention_key: StorySemanticKey,
) -> str:
    """R49 PTP direct-versus-consequence classification —
    ``ptp-psych-classification``, keyed ``(O, psychiatric C)``: 3/5
    mischaracterized ``direct``, complement ``compensable_consequence``.
    Independent of applicant framing and of advocacy."""
    rng = _medical_story_rng(
        seed,
        "ptp-psych-classification",
        ("case", seed.case_id, opinion_key, contention_key),
    )
    if _fraction_draw(rng, P_PTP_DIRECT_PSYCH_CLASSIFICATION_GIVEN_CONSEQUENCE.value):
        return "direct"
    return "compensable_consequence"


def _qme_ame_indeterminate_disposition(
    seed: CaseSeed,
    opinion_key: StorySemanticKey,
    contention_key: StorySemanticKey,
) -> str:
    """R49's indeterminate stream — ``qme-ame-indeterminate-disposition``,
    keyed ``(O, C)``: 3/5 ``deferred``, complement ``unaddressed``. It chooses
    only between those two states; it cannot produce adoption or concurrence.
    """
    rng = _medical_story_rng(
        seed,
        "qme-ame-indeterminate-disposition",
        ("case", seed.case_id, opinion_key, contention_key),
    )
    if _fraction_draw(rng, P_QME_AME_INDETERMINATE_DEFERRED.value):
        return "deferred"
    return "unaddressed"


def _qme_ame_supported_disposition(
    seed: CaseSeed,
    opinion_key: StorySemanticKey,
    contention_key: StorySemanticKey,
    qualifying_communication_keys: tuple[StorySemanticKey, ...],
) -> str:
    """R38/R53 — adopted versus concurred for one evidence-supported pair.

    A responsive-adoption opportunity exists only when one or more earlier
    qualifying R38 communications target the opinion and speak this
    contention. Without one, the result is concurrence WITHOUT an adoption
    draw — agreement in result is not responsive adoption. With one, exactly
    one ``qme-ame-responsive-adoption`` draw is made, keyed
    ``(O, C, tuple(sorted(qualifying D keys)))``; a miss is concurrence.

    The measured 0.25 denominator is the pre-control structural opportunity
    count: later removal of the communication document may drop its citation
    from the rendered report but MUST NOT retroactively redraw this result
    (R53) — the caller passes the pre-control communication set once.
    """
    if not qualifying_communication_keys:
        return "concurred"
    rng = _medical_story_rng(
        seed,
        "qme-ame-responsive-adoption",
        (
            "case",
            seed.case_id,
            opinion_key,
            contention_key,
            tuple(sorted(qualifying_communication_keys, key=canonical_story_key)),
        ),
    )
    if _fraction_draw(rng, P_QME_AME_RESPONSIVE_ADOPTION.value):
        return "adopted"
    return "concurred"


#: The frozen R54 revision-kind declaration order — one weight row per member.
_REVISION_KIND_ORDER: Final[tuple[str, ...]] = (
    "unchanged_additional_reasoning",
    "new_records_no_change",
    "revised_causation",
    "revised_apportionment",
    "revised_causation_and_apportionment",
)

#: The R54/R37 kinds able to carry a causation-family revision — the only
#: kinds retained after responsive adoption changes a disposition.
_CAUSATION_CAPABLE_REVISION_KINDS: Final[frozenset[str]] = frozenset(
    {"revised_causation", "revised_causation_and_apportionment"}
)


def _draw_revision_kind(
    seed: CaseSeed,
    response_opinion_key: StorySemanticKey,
    predecessor_opinion_key: StorySemanticKey,
    trigger_class: str,
    *,
    can_acknowledge_new_records: bool,
    can_change_apportionment: bool,
    can_change_causation: bool,
    adoption_changed_disposition: bool,
) -> str:
    """One trigger-conditioned compatible R54 revision-kind draw.

    Structurally ineligible kinds are removed BEFORE the single draw — never
    drawn-and-retried (R54):

    - ``new_records_no_change`` goes unless the reviewed-record union can
      become a strict superset from an existing visible condition, prior claim
      or prior award (and its deposition rows already carry zero weight);
    - the apportionment kinds go if no apportionment issue can change;
    - the causation kinds go if no causation, psych classification or
      disposition can change;
    - after responsive adoption changes a disposition, only causation-capable
      kinds remain.

    The remaining exact ``Fraction`` weights are renormalized and exactly one
    draw is consumed from ``revision-kind``, keyed
    ``(response O, predecessor O, trigger_class)``.
    """
    weights_by_trigger = REVISION_KIND_WEIGHTS.value
    if trigger_class not in weights_by_trigger:
        raise MedicalAssertionError(
            f"unknown revision trigger class {trigger_class!r}; R54 freezes "
            "exactly supplemental_after_objection, supplemental_after_completion, "
            "deposition_examining_base and deposition_examining_supplemental"
        )
    row = weights_by_trigger[trigger_class]
    eligible: list[tuple[str, Fraction]] = []
    for kind, weight in zip(_REVISION_KIND_ORDER, row, strict=True):
        if kind == "new_records_no_change" and not can_acknowledge_new_records:
            continue
        if (
            kind in ("revised_apportionment", "revised_causation_and_apportionment")
            and not can_change_apportionment
        ):
            continue
        if (
            kind in ("revised_causation", "revised_causation_and_apportionment")
            and not can_change_causation
        ):
            continue
        if adoption_changed_disposition and kind not in _CAUSATION_CAPABLE_REVISION_KINDS:
            continue
        eligible.append((kind, weight))
    total = sum(weight for _kind, weight in eligible)
    if not eligible or total == 0:
        raise MedicalAssertionError(
            f"no compatible revision kind remains for trigger {trigger_class!r}; "
            "a response opinion cannot be sampled where nothing may change and "
            "nothing may be acknowledged"
        )
    rng = _medical_story_rng(
        seed,
        "revision-kind",
        (
            "case",
            seed.case_id,
            response_opinion_key,
            predecessor_opinion_key,
            trigger_class,
        ),
    )
    index = _weighted_index(rng, tuple(weight / total for _kind, weight in eligible))
    return eligible[index][0]


def _draw_revision_percentage(
    seed: CaseSeed,
    response_opinion_key: StorySemanticKey,
    body_part: str,
    predecessor_assertion_key: StorySemanticKey,
    *,
    predecessor_nonindustrial: int | None,
    require_change: bool,
) -> int:
    """One R55 changed-row percentage for an M3 revision.

    Two entity-private streams share the exact ``(response O, body_part,
    predecessor assertion semantic key)`` identity:
    ``revision-percentage-register`` selects the common pool at the frozen
    17/20 (the existing M2 knob, by identity) versus the 78-member granular
    remainder; ``revision-percentage-value`` then makes ONE selection from the
    resulting pool. When R37 requires a changed percentage, the immediate
    predecessor's value is removed from the SELECTED pool before selection —
    never redrawn after the fact.

    The granular selector implements the continuous latent law: with
    ``U ~ Uniform[0,1)`` over the ordered eligible values ``G``,
    ``z = U*len(G)``, ``i = floor(z)``, ``x = G[i] - 1/2 + (z - i)``, and
    quantization ``floor(x + 1/2)`` returns exactly ``G[i]`` — uniform by
    Lebesgue measure over ``union([g-0.5, g+0.5))``. It never clamps a
    continuous value to the nearest common percentage, never rounds a
    common-pool miss into the common pool, never retries, and roundness never
    touches quality (R55).
    """
    key: StorySemanticKey = (
        "case",
        seed.case_id,
        response_opinion_key,
        body_part,
        predecessor_assertion_key,
    )
    register = _medical_story_rng(seed, "revision-percentage-register", key)
    common_selected = _fraction_draw(register, P_COMMON_PERCENTAGE_REGISTER.value)
    pool = (
        COMMON_NONINDUSTRIAL_PERCENTAGES if common_selected else GRANULAR_NONINDUSTRIAL_PERCENTAGES
    )
    if require_change and predecessor_nonindustrial in pool:
        pool = tuple(value for value in pool if value != predecessor_nonindustrial)
    value_rng = _medical_story_rng(seed, "revision-percentage-value", key)
    if common_selected:
        return pool[value_rng.randrange(len(pool))]
    # Granular remainder: the continuous inverse-CDF construction. The
    # interval index IS the selection — G[i] is returned directly after
    # computing the same index the latent x would quantize back to.
    z = value_rng.random() * len(pool)
    interval = min(int(z), len(pool) - 1)
    return pool[interval]


@dataclass(frozen=True, slots=True)
class AssertionCandidate:
    """One sampled-candidate decision, keyed semantically for suppression."""

    semantic_key: SemanticKey
    candidate_family: str
    payload: dict[str, object]


def _suppress_explicit_collisions(
    sampled_candidates: Sequence[AssertionCandidate],
    explicit_semantic_keys: frozenset[SemanticKey],
) -> tuple[tuple[AssertionCandidate, ...], int]:
    suppression_hits = 0
    retained: list[AssertionCandidate] = []
    for candidate in sampled_candidates:
        semantic_key = candidate.semantic_key
        if semantic_key in explicit_semantic_keys:
            suppression_hits += 1
            continue
        retained.append(candidate)
    return tuple(retained), suppression_hits


def assertion_context(seed: CaseSeed, timeline: object = None) -> AssertionValidationContext:
    """Build the one validation context from the seed (and the planner's timeline).

    The timeline's injury date wins where one exists, mirroring
    ``derive_medical_history`` — the ledger, the assertions and the documents
    must not reach two different injury dates for one case.
    """
    injury_date = getattr(timeline, "injury_date", None) or seed.injury.onset_date
    return AssertionValidationContext(
        date_of_injury=injury_date,
        anchor_date=ANCHOR_DATE,
        current_body_parts=tuple(part.part for part in seed.injury.body_parts),
        target_stage=seed.lifecycle.target_stage,
        claim_response=seed.lifecycle.claim_response,
        eval_type=seed.lifecycle.eval_type,
    )


# ---------------------------------------------------------------------------
# The evidence predicate and the frozen quality rubric (Escobedo v2)
# ---------------------------------------------------------------------------

#: The closed invalid-basis table: bases that are unsupportable as a matter of
#: law whenever they appear, regardless of surrounding prose. Closed means
#: closed — ``genetics_heredity_pathology`` is deliberately NOT here (*Rice*
#: weighs it), and ``psych_impairment_add_on`` is the one conditional member,
#: its predicate given exactly by the four ``psych_exception_analysis`` rows.
UNCONDITIONAL_HARD_INVALID_BASES: Final[frozenset[str]] = frozenset(
    {
        "vocational_apportionment",
        "lc3208_3_threshold_misuse",
        "bare_age",
        "bare_gender",
        "risk_factor_only",
    }
)

#: Rubric confidence carried into the table rather than dropped (finding 19):
#: the §3208.3 row is LOW-MEDIUM (doctrine-tag only) and the §4664
#: separate-analysis rule is the rubric's lower-confidence item 9. Metadata for
#: reviewers and M4's re-grading pass; the grades themselves are unconditional.
BASIS_RULE_CONFIDENCE: Final[dict[str, str]] = {
    "lc3208_3_threshold_misuse": "low_medium",
    "lc4664_prior_award": "lower",
}


def has_substantial_nonindustrial_evidence(history: AssertionWorldProjection) -> bool:
    """Whether the record carries a live, overlapping nonindustrial contributor.

    The predicate behind three rules that must agree: B.6's final-determination
    branch A, the inverse-Hikida refusal row, and the contradicted-zero-share
    row. A contributor is substantial when it is visible, overlaps the claimed
    regions, is nonindustrial or mixed, and has not resolved — or when an
    overlapping conclusively presumed prior award exists.
    """
    for condition in history.conditions:
        if (
            not condition.wholly_unrelated
            and condition.causal_ground_truth in ("nonindustrial", "mixed")
            and condition.surfaces_in_file
            and condition.trajectory != "resolved"
        ):
            return True
    return any(
        claim.overlaps_current and claim.award is not None and claim.award.conclusively_presumed
        for claim in history.prior_claims
    )


def contention_evidence(
    history: AssertionWorldProjection,
    context: AssertionValidationContext,
    contention: Contention,
) -> EvidenceDisposition:
    """The tri-state ledger-evidence read for one contention (B.5).

    For ``position="deny"`` the supports/contradicts poles swap: evidence that
    supports the affirmative proposition contradicts its denial.
    """
    disposition = _affirmative_evidence(history, context, contention)
    if contention.position == "deny":
        if disposition == "supports":
            return "contradicts"
        if disposition == "contradicts":
            return "supports"
    return disposition


def _affirmative_evidence(
    history: AssertionWorldProjection,
    context: AssertionValidationContext,
    contention: Contention,
) -> EvidenceDisposition:
    target = (
        history.condition(contention.target_condition_id)
        if contention.target_condition_id is not None
        else None
    )
    claim_type = contention.claim_type

    if claim_type == "industrial_causation":
        if target is None:
            return "indeterminate"
        if target.causal_ground_truth in ("industrial", "mixed") and target.surfaces_in_file:
            return "supports"
        if target.causal_ground_truth == "nonindustrial" or target.wholly_unrelated:
            return "contradicts"
        return "indeterminate"

    if claim_type == "aggravation":
        if target is None:
            return "indeterminate"
        if target.wholly_unrelated or target.trajectory == "resolved":
            return "contradicts"
        if target.symptomatic_before_doi is True and target.trajectory in (
            "stable",
            "progressive",
            "fluctuating",
        ):
            return "supports"
        return "indeterminate"

    if claim_type == "apportionment_defense":
        claim = (
            history.prior_claim(contention.target_prior_claim_id)
            if contention.target_prior_claim_id is not None
            else None
        )
        award = (
            history.prior_award(contention.target_prior_award_id)
            if contention.target_prior_award_id is not None
            else None
        )
        relevant_condition = (
            target is not None
            and not target.wholly_unrelated
            and target.surfaces_in_file
            and target.causal_ground_truth in ("nonindustrial", "mixed")
        )
        overlapping_claim = claim is not None and claim.overlaps_current
        presumed_award = (
            award is not None
            and award.conclusively_presumed
            and any(part in context.current_body_parts for part in award.body_parts)
        )
        if relevant_condition or overlapping_claim or presumed_award:
            return "supports"
        if target is None and claim is None and award is None:
            return "indeterminate"
        target_dead = target is None or target.wholly_unrelated
        claim_dead = claim is None or not claim.overlaps_current
        award_dead = award is None or not any(
            part in context.current_body_parts for part in award.body_parts
        )
        if target_dead and claim_dead and award_dead:
            return "contradicts"
        return "indeterminate"

    if claim_type == "compensable_consequence":
        if target is None:
            return "indeterminate"
        if (
            target.causal_ground_truth == "industrial"
            and target.onset is not None
            and target.onset >= context.date_of_injury
            and target.surfaces_in_file
        ):
            return "supports"
        if target.causal_ground_truth == "nonindustrial" or (
            target.onset is not None and target.onset < context.date_of_injury
        ):
            return "contradicts"
        return "indeterminate"

    if claim_type == "psych_add_on":
        psych = next((c for c in history.conditions if c.key == "depression_anxiety"), None)
        if target is not None:
            psych = target
        if psych is None:
            return "indeterminate"
        if psych.causal_ground_truth == "nonindustrial" or psych.trajectory == "resolved":
            return "contradicts"
        if (
            psych.causal_ground_truth in ("industrial", "mixed")
            and psych.onset is not None
            and psych.onset >= context.date_of_injury
            and psych.surfaces_in_file
        ):
            return "supports"
        return "indeterminate"

    # denial_of_injury
    if target is None:
        if context.claim_response == "denied":
            return "supports"
        return "indeterminate"
    if target.causal_ground_truth == "nonindustrial" or target.wholly_unrelated:
        return "supports"
    if target.causal_ground_truth in ("industrial", "mixed") and target.surfaces_in_file:
        return "contradicts"
    return "indeterminate"


def qme_disposition(evidence: EvidenceDisposition) -> Literal["endorse", "reject", "neither"]:
    """The QME/AME evidence policy — completely conditioned on the ledger read.

    No draw, no flat endorsement rate: a sampled medical-legal evaluator
    endorses what the evidence supports, rejects what it contradicts, and
    stays silent on the indeterminate. Explicit evaluator dissent remains
    legal divergence — it is graded, never rejected.
    """
    if evidence == "supports":
        disposition = "endorse"
    elif evidence == "contradicts":
        disposition = "reject"
    else:
        disposition = "neither"
    return disposition


def contention_quality(
    history: AssertionWorldProjection,
    context: AssertionValidationContext,
    contention: Contention,
    *,
    quality_contract: AssertionQualityContract,
) -> AssertionQuality:
    """Grade one contention against the world ledger.

    The two hard Hikida rows come first — they are legal-error terminals under
    the narrowed *Justice* rule, not evidence questions. Everything else is the
    evidence tri-state: contradicted is unsupportable, supported-with-reasoning
    is supported, and the indeterminate or unreasoned middle is thin.
    """
    _require_quality_contract(quality_contract)
    if (
        contention.treatment_causation == "sole_cause"
        and contention.requested_apportionment == "apply"
    ):
        return "unsupportable"
    if (
        contention.treatment_causation == "contributing_cause"
        and contention.requested_apportionment == "refuse"
        and has_substantial_nonindustrial_evidence(history)
    ):
        return "unsupportable"
    evidence = contention_evidence(history, context, contention)
    if evidence == "contradicts":
        return "unsupportable"
    if evidence == "supports" and contention.rationale:
        return "supported"
    return "thin"


def _hard_invalid_basis(assertion: ApportionmentAssertion, linked: Contention | None) -> bool:
    """Precedence rule 1 — the closed invalid-basis decision."""
    if any(basis in UNCONDITIONAL_HARD_INVALID_BASES for basis in assertion.basis_kinds):
        return True
    if "psych_impairment_add_on" in assertion.basis_kinds and (
        assertion.psych_exception_analysis is None
        or assertion.psych_exception_analysis == "none_applies"
    ):
        return True
    # Item 8's hard direction: a nonindustrial share applied where the linked
    # treatment story states industrial treatment was the SOLE cause.
    return (
        linked is not None
        and linked.treatment_causation == "sole_cause"
        and assertion.nonindustrial_percent > 0
    )


def escobedo_misses(
    history: AssertionWorldProjection,
    ledger: MedicalAssertionLedger,
    assertion: ApportionmentAssertion,
    *,
    quality_contract: AssertionQualityContract,
) -> tuple[str, ...]:
    """Which applicable checklist items this assertion misses, in item order.

    Each item reads an independently controllable input, so the frozen oracle
    can move a supported build to its expected lower grade one item at a time.
    """
    _require_quality_contract(quality_contract)
    owner = ledger.opinion(assertion.opinion_id)
    linked = (
        ledger.contention(assertion.linked_contention_id)
        if assertion.linked_contention_id is not None
        else None
    )
    misses: list[str] = []
    if not assertion.disability_causation_stated:
        misses.append("1")
    if not assertion.description:
        misses.append("2")
    cited_any = bool(
        assertion.condition_ids or assertion.prior_claim_ids or assertion.prior_award_ids
    )
    if not assertion.basis_kinds or not cited_any:
        misses.append("3a")
    if not assertion.reasonable_medical_probability:
        misses.append("4")
    examined = owner is not None and owner.examination_performed
    if (
        owner is not None
        and quality_contract == "2.0.0"
        and owner.event_kind != "base_report"
    ):
        examined = _response_incorporates_examination(ledger, owner)
    if owner is not None and not examined:
        misses.append("5a")
    if owner is not None and _relied_on_record_gap(history, owner, assertion):
        misses.append("5b")
    if not assertion.causal_rationale:
        misses.append("6")
    if not assertion.percentage_rationale:
        misses.append("7")
    if "industrial_treatment" in assertion.basis_kinds and (
        linked is None or linked.treatment_causation is None
    ):
        misses.append("8")
    if "lc4664_prior_award" in assertion.basis_kinds and not assertion.prior_award_analysis:
        misses.append("9")
    if "benson_successive_injury" in assertion.basis_kinds:
        benson = next((g for g in assertion.groundings if isinstance(g, BensonGrounding)), None)
        separated = benson is not None and set(assertion.prior_claim_ids) <= set(
            benson.prior_claim_ids
        )
        if not separated:
            misses.append("11")
    if "genetics_heredity_pathology" in assertion.basis_kinds and not assertion.condition_ids:
        misses.append("12")
    return tuple(misses)


def _relied_on_record_gap(
    history: AssertionWorldProjection,
    owner: MedicalOpinion,
    assertion: ApportionmentAssertion,
) -> bool:
    """Item 5b — a relied-on factor outside the reviewed record, or invisible."""
    for ref in assertion.condition_ids:
        condition = history.condition(ref)
        if ref not in owner.reviewed_condition_ids:
            return True
        if condition is not None and not condition.surfaces_in_file:
            return True
    if any(ref not in owner.reviewed_prior_claim_ids for ref in assertion.prior_claim_ids):
        return True
    return any(ref not in owner.reviewed_prior_award_ids for ref in assertion.prior_award_ids)


def _require_quality_contract(
    quality_contract: AssertionQualityContract,
) -> AssertionQualityContract:
    """Fail closed when a caller bypasses channel-major normalization."""
    if quality_contract not in ("1.0.0", "2.0.0"):
        raise ValueError(f"unsupported assertion quality contract {quality_contract!r}")
    return quality_contract


def _response_incorporates_examination(
    ledger: MedicalAssertionLedger,
    response: MedicalOpinion,
) -> bool:
    """Whether a v2 response has an exact examined-base predecessor chain."""
    predecessor_id = response.responds_to_opinion_id
    if predecessor_id is None:
        return False
    seen = {response.id}
    current = response
    while predecessor_id is not None:
        if predecessor_id in seen:
            return False
        predecessor = ledger.opinion(predecessor_id)
        if predecessor is None:
            return False
        if predecessor.author_role != current.author_role:
            return False
        if predecessor.report_date >= current.report_date:
            return False
        seen.add(predecessor_id)
        if predecessor.event_kind == "base_report":
            return predecessor.examination_performed
        current = predecessor
        predecessor_id = predecessor.responds_to_opinion_id
    return False


def apportionment_quality(
    history: AssertionWorldProjection,
    context: AssertionValidationContext,
    ledger: MedicalAssertionLedger,
    assertion: ApportionmentAssertion,
    *,
    quality_contract: AssertionQualityContract,
) -> AssertionQuality:
    """Grade one apportionment assertion under the frozen precedence.

    1. hard invalid / zero foundation -> unsupportable;
    2. direct contradiction by all cited factors -> unsupportable;
    3. any applicable checklist miss -> thin;
    4. all pass -> supported.
    """
    _require_quality_contract(quality_contract)
    linked = (
        ledger.contention(assertion.linked_contention_id)
        if assertion.linked_contention_id is not None
        else None
    )
    hard_invalid = _hard_invalid_basis(assertion, linked)
    zero_foundation = not assertion.basis_kinds and not (
        assertion.condition_ids or assertion.prior_claim_ids or assertion.prior_award_ids
    )
    if zero_foundation:
        hard_invalid = True
    if hard_invalid:
        return "unsupportable"

    cited = [history.condition(ref) for ref in assertion.condition_ids]
    cited_claims = [history.prior_claim(ref) for ref in assertion.prior_claim_ids]
    if (
        (cited or cited_claims)
        and all(c is None or c.wholly_unrelated for c in cited)
        and all(c is None or not c.overlaps_current for c in cited_claims)
    ):
        contradicted = any(c is not None and c.wholly_unrelated for c in cited) or any(
            c is not None and not c.overlaps_current for c in cited_claims
        )
        if contradicted:
            return "unsupportable"

    if (
        assertion.revised_from_percent is not None
        and assertion.revised_from_percent != assertion.nonindustrial_percent
        and not assertion.revision_rationale
    ):
        # An unexplained material revision (*Lindh*'s fail condition, promoted
        # to hard by Part 3); an explained one is not a defect at all.
        return "unsupportable"

    if escobedo_misses(
        history,
        ledger,
        assertion,
        quality_contract=quality_contract,
    ):
        return "thin"
    return "supported"


def opinion_quality(
    history: AssertionWorldProjection,
    context: AssertionValidationContext,
    ledger: MedicalAssertionLedger,
    opinion: MedicalOpinion,
    *,
    quality_contract: AssertionQualityContract,
) -> AssertionQuality:
    """Grade one opinion: the worst of everything it stands behind.

    Endorsed contentions are graded as stated; rejected ones on the OPPOSITE
    proposition (a rejection of a false claim is good medicine, never a
    mechanical inversion of the claim's own grade); owned assertions carry
    their own grades; the opinion's own foundation and its final determination
    close the set. Interim deferral itself carries no penalty.
    """
    _require_quality_contract(quality_contract)
    order = {"supported": 0, "thin": 1, "unsupportable": 2}
    worst = "supported"

    def sink(grade: AssertionQuality) -> None:
        nonlocal worst
        if order[grade] > order[worst]:
            worst = grade

    if opinion.report_stage == "final" and opinion.apportionment_state == "omitted":
        sink("unsupportable")

    for ref in opinion.endorses_contention_ids:
        contention = ledger.contention(ref)
        if contention is not None:
            sink(
                contention_quality(
                    history,
                    context,
                    contention,
                    quality_contract=quality_contract,
                )
            )
    for ref in opinion.rejects_contention_ids:
        contention = ledger.contention(ref)
        if contention is not None:
            flipped: ContentionPosition = "deny" if contention.position == "affirm" else "affirm"
            opposite = contention.model_copy(update={"position": flipped})
            sink(
                contention_quality(
                    history,
                    context,
                    opposite,
                    quality_contract=quality_contract,
                )
            )

    for assertion in ledger.assertions_of(opinion.id):
        sink(
            apportionment_quality(
                history,
                context,
                ledger,
                assertion,
                quality_contract=quality_contract,
            )
        )

    relevant_review = bool(
        [
            ref
            for ref in opinion.reviewed_condition_ids
            if (condition := history.condition(ref)) is not None and condition.surfaces_in_file
        ]
        or opinion.reviewed_prior_claim_ids
        or opinion.reviewed_prior_award_ids
    )
    foundation = opinion.examination_performed or relevant_review
    if foundation and opinion.rationale:
        pass
    elif foundation or opinion.rationale:
        sink("thin")
    else:
        sink("unsupportable")

    if opinion.determination_kind == "no_nonindustrial_share":
        if has_substantial_nonindustrial_evidence(history):
            # Contradicted by its own record — unsupportable regardless of how
            # well the zero share is written up (Part 4 B.8 row 1).
            sink("unsupportable")
        elif not opinion.determination_rationale:
            sink("thin")
    if opinion.determination_kind == "unable_to_approximate" and not (
        opinion.determination_rationale and foundation
    ):
        sink("thin")

    return worst


def grade_ledger(
    context: AssertionValidationContext,
    history: AssertionWorldProjection,
    ledger: MedicalAssertionLedger,
    *,
    quality_contract: AssertionQualityContract,
) -> MedicalAssertionLedger:
    """Re-derive every quality in *ledger* from the frozen rubric.

    The single grading pass both composition paths share: explicit entries and
    sampled entries are graded identically, and a sampling target recipe is
    never copied — the truth-side validator re-runs this exact function to
    prove a stated label is the derived one.
    """
    _require_quality_contract(quality_contract)
    contentions = tuple(
        c.model_copy(
            update={
                "quality": contention_quality(
                    history,
                    context,
                    c,
                    quality_contract=quality_contract,
                )
            }
        )
        for c in ledger.contentions
    )
    regraded = MedicalAssertionLedger(
        contentions=contentions,
        medical_opinions=ledger.medical_opinions,
        apportionment_assertions=ledger.apportionment_assertions,
    )
    assertions = tuple(
        a.model_copy(
            update={
                "quality": apportionment_quality(
                    history,
                    context,
                    regraded,
                    a,
                    quality_contract=quality_contract,
                )
            }
        )
        for a in ledger.apportionment_assertions
    )
    regraded = MedicalAssertionLedger(
        contentions=contentions,
        medical_opinions=ledger.medical_opinions,
        apportionment_assertions=assertions,
    )
    opinions = tuple(
        o.model_copy(
            update={
                "quality": opinion_quality(
                    history,
                    context,
                    regraded,
                    o,
                    quality_contract=quality_contract,
                )
            }
        )
        for o in ledger.medical_opinions
    )
    return MedicalAssertionLedger(
        contentions=contentions,
        medical_opinions=opinions,
        apportionment_assertions=assertions,
    )


def assertion_warnings(
    history: AssertionWorldProjection, ledger: MedicalAssertionLedger
) -> tuple[str, ...]:
    """Nonfatal authoring warnings — ungrounded hooks and dangling groundings.

    Warn, never block (decision #2): the hook is kept and the assertion stands;
    the author is told the argument has nothing typed behind it. Grounding IDs
    that resolve to no world-truth entity warn the same way — the frozen §C
    catalog carries no literal for them, so existence is an authoring warning
    rather than a validation error (sol open question 3, fix round 1). One
    warning per distinct finding, sorted, so the output is stable.
    """
    ungrounded: set[str] = set()
    for contention in ledger.contentions:
        supplied = {g.hook for g in contention.groundings}
        for hook in contention.doctrine_hooks:
            if hook in GROUNDABLE_HOOKS and hook not in supplied:
                ungrounded.add(hook)

    condition_ids = {condition.id for condition in history.conditions}
    claim_ids = {claim.id for claim in history.prior_claims}
    award_ids = {award.id for award in history.awards}
    dangling: set[tuple[str, str, str, str, str]] = set()
    for kind, items in (
        ("contention", ledger.contentions),
        ("apportionment assertion", ledger.apportionment_assertions),
    ):
        for item in items:
            for grounding in item.groundings:
                refs: list[tuple[str, str, set[str]]] = []
                if isinstance(grounding, BensonGrounding):
                    refs = [("prior claim", ref, claim_ids) for ref in grounding.prior_claim_ids]
                elif isinstance(grounding, SibtfGrounding):
                    refs = [
                        ("condition", ref, condition_ids)
                        for ref in grounding.preexisting_condition_ids
                    ]
                    refs.extend(
                        ("prior award", ref, award_ids) for ref in grounding.prior_award_ids
                    )
                elif isinstance(grounding, Lc4664PriorAwardGrounding):
                    refs = [("prior award", grounding.prior_award_id, award_ids)]
                elif isinstance(grounding, FirefighterPresumptionGrounding):
                    refs = [("condition", grounding.condition_id, condition_ids)]
                for entity, ref, known in refs:
                    if ref not in known:
                        dangling.add((kind, item.id, grounding.hook, entity, ref))

    return tuple(
        [
            f"medical_assertions: doctrine hook '{hook}' has no typed MedicalHistory "
            "grounding; explicit hook retained"
            for hook in sorted(ungrounded)
        ]
        + [
            f"medical_assertions: {kind} '{item_id}' grounding for hook '{hook}' "
            f"references unknown {entity} '{ref}'; assertion retained"
            for kind, item_id, hook, entity, ref in sorted(dangling)
        ]
    )


# ---------------------------------------------------------------------------
# Composition — explicit entries authoritative, sampling appends, IDs last
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class AssertionTrace:
    """Private cohort diagnostics. Test-only; never serialized anywhere.

    ``suppression_hits`` and the budget/distractor counters exist so the
    frozen oracle can assert composition behaviour positively instead of
    inferring it from absence. Nothing here may enter a ledger, warning,
    manifest or document.

    Every counter above the M3 line is an M2 counter and is NEVER incremented
    by M3 (R61). ``m2_baseline_ledger`` is the one M3-era member: the exact
    M2 post-grade/pre-M3 ledger, recorded by
    :func:`derive_medical_assertion_plan` so the R62 digest oracle and the
    R70 stream gate read the preserved baseline rather than the (later)
    remodeled plan ledger. M3 opportunity/outcome/path/date/revision/field
    counters arrive as separate ``story_*`` members with their producers
    (R77 steps 4-8).
    """

    suppression_hits: int = 0
    recipes: list[tuple[str, str, str]] = None  # type: ignore[assignment]
    evidence_budgets: list[int] = None  # type: ignore[assignment]
    distractor_available: int = 0
    distractor_included: int = 0
    candidate_families: dict[str, int] = None  # type: ignore[assignment]
    eligible_candidates: dict[str, int] = None  # type: ignore[assignment]
    lifecycle: list[str] = None  # type: ignore[assignment]
    m2_baseline_ledger: MedicalAssertionLedger | None = None
    story_raw_date_offsets: list[tuple[str, int]] = field(default_factory=list)
    """R61 ``story_*`` member (R77 step 5): every raw R56 date-band draw the
    contention loop makes, as ``(family, offset)`` — the R70 date-band gate's
    instrument for "inclusive, causal, never redrawn". A truncated stage's
    burned draw stays recorded; nothing here is an M2 counter."""

    def __post_init__(self) -> None:
        self.recipes = [] if self.recipes is None else self.recipes
        self.evidence_budgets = [] if self.evidence_budgets is None else self.evidence_budgets
        self.candidate_families = {} if self.candidate_families is None else self.candidate_families
        self.eligible_candidates = (
            {} if self.eligible_candidates is None else self.eligible_candidates
        )
        self.lifecycle = [] if self.lifecycle is None else self.lifecycle


def _contention_semantic_key(entry: object) -> SemanticKey:
    """The B.2 rule-6 suppression key, normalized (sorted hook tuple)."""
    return (
        "contention",
        entry.claim_type,  # type: ignore[attr-defined]
        entry.position,  # type: ignore[attr-defined]
        entry.target_condition_id,  # type: ignore[attr-defined]
        entry.target_prior_claim_id,  # type: ignore[attr-defined]
        entry.target_prior_award_id,  # type: ignore[attr-defined]
        entry.target_body_part,  # type: ignore[attr-defined]
        tuple(sorted(entry.doctrine_hooks)),  # type: ignore[attr-defined]
    )


def _explicit_reference_problems(scenario: object) -> list[str]:
    """B.2 rule 3 — explicit references may target only explicit IDs.

    Enforced before sampling because a sampled entry can legitimately claim the
    first unused numeric suffix: an explicit reference to ``ctn-02`` must not
    silently start resolving to whatever the sampler happened to draw there.
    Same templates as the ledger validator, raised at the same generation-time
    boundary.
    """
    contention_ids = {e.id for e in scenario.contentions}  # type: ignore[attr-defined]
    opinion_ids = {e.id for e in scenario.medical_opinions}  # type: ignore[attr-defined]
    problems: list[str] = []
    for opinion in scenario.medical_opinions:  # type: ignore[attr-defined]
        for verb, refs in (
            ("endorses", opinion.endorses_contention_ids),
            ("concurs with", opinion.concurs_with_contention_ids),
            ("rejects", opinion.rejects_contention_ids),
            ("defers", opinion.defers_contention_ids),
        ):
            for ref in refs:
                if ref not in contention_ids:
                    problems.append(
                        f"medical opinion '{opinion.id}' {verb} unknown contention '{ref}'"
                    )
        for verb, ref in (
            ("responds to", opinion.responds_to_opinion_id),
            ("supersedes", opinion.supersedes_opinion_id),
        ):
            if ref is not None and ref != opinion.id and ref not in opinion_ids:
                problems.append(f"medical opinion '{opinion.id}' {verb} unknown opinion '{ref}'")
    for document in scenario.contention_documents:  # type: ignore[attr-defined]
        for label, ref in (
            ("medical_opinion_id", document.medical_opinion_id),
            ("target_medical_opinion_id", document.target_medical_opinion_id),
        ):
            if ref is not None and ref not in opinion_ids:
                problems.append(
                    f"contention document '{document.id}' references unknown "
                    f"medical opinion '{ref}' as {label}"
                )
        for ref in document.spoken_contention_ids:
            if ref not in contention_ids:
                problems.append(
                    f"contention document '{document.id}' speaks unknown contention '{ref}'"
                )
    for assertion in scenario.apportionment_assertions:  # type: ignore[attr-defined]
        if assertion.opinion_id not in opinion_ids:
            problems.append(
                f"apportionment assertion '{assertion.id}' references unknown "
                f"medical opinion '{assertion.opinion_id}'"
            )
        if (
            assertion.linked_contention_id is not None
            and assertion.linked_contention_id not in contention_ids
        ):
            problems.append(
                f"apportionment assertion '{assertion.id}' references unknown "
                f"contention '{assertion.linked_contention_id}'"
            )
    return problems


def _groundings_tuple(entry: object) -> tuple[DoctrineGrounding, ...]:
    return tuple(getattr(entry, "groundings", ()) or ())


def _contention_from_entry(entry: object) -> Contention:
    return Contention(
        id=entry.id,  # type: ignore[attr-defined]
        claim_type=entry.claim_type,  # type: ignore[attr-defined]
        party=entry.party,  # type: ignore[attr-defined]
        position=entry.position,  # type: ignore[attr-defined]
        target_condition_id=entry.target_condition_id,  # type: ignore[attr-defined]
        target_prior_claim_id=entry.target_prior_claim_id,  # type: ignore[attr-defined]
        target_prior_award_id=entry.target_prior_award_id,  # type: ignore[attr-defined]
        target_body_part=entry.target_body_part,  # type: ignore[attr-defined]
        doctrine_hooks=tuple(entry.doctrine_hooks),  # type: ignore[attr-defined]
        rationale=entry.rationale,  # type: ignore[attr-defined]
        treatment_causation=entry.treatment_causation,  # type: ignore[attr-defined]
        requested_apportionment=entry.requested_apportionment,  # type: ignore[attr-defined]
        groundings=_groundings_tuple(entry),
        psych_injury_kind=entry.psych_injury_kind,  # type: ignore[attr-defined]
        quality="supported",
    )


def _opinion_from_entry(entry: object) -> MedicalOpinion:
    return MedicalOpinion(
        id=entry.id,  # type: ignore[attr-defined]
        author_role=entry.author_role,  # type: ignore[attr-defined]
        report_stage=entry.report_stage,  # type: ignore[attr-defined]
        report_date=entry.report_date,  # type: ignore[attr-defined]
        apportionment_state=entry.apportionment_state,  # type: ignore[attr-defined]
        determination_kind=entry.determination_kind,  # type: ignore[attr-defined]
        determination_rationale=entry.determination_rationale,  # type: ignore[attr-defined]
        examination_performed=entry.examination_performed,  # type: ignore[attr-defined]
        reviewed_condition_ids=tuple(entry.reviewed_condition_ids),  # type: ignore[attr-defined]
        reviewed_prior_claim_ids=tuple(entry.reviewed_prior_claim_ids),  # type: ignore[attr-defined]
        reviewed_prior_award_ids=tuple(entry.reviewed_prior_award_ids),  # type: ignore[attr-defined]
        endorses_contention_ids=tuple(entry.endorses_contention_ids),  # type: ignore[attr-defined]
        rejects_contention_ids=tuple(entry.rejects_contention_ids),  # type: ignore[attr-defined]
        responds_to_opinion_id=entry.responds_to_opinion_id,  # type: ignore[attr-defined]
        supersedes_opinion_id=entry.supersedes_opinion_id,  # type: ignore[attr-defined]
        rationale=entry.rationale,  # type: ignore[attr-defined]
        revision_rationale=entry.revision_rationale,  # type: ignore[attr-defined]
        event_kind=entry.event_kind,  # type: ignore[attr-defined]
        revision_kind=entry.revision_kind,  # type: ignore[attr-defined]
        concurs_with_contention_ids=tuple(entry.concurs_with_contention_ids),  # type: ignore[attr-defined]
        defers_contention_ids=tuple(entry.defers_contention_ids),  # type: ignore[attr-defined]
        psych_injury_kind=entry.psych_injury_kind,  # type: ignore[attr-defined]
        aoe_coe_finding=entry.aoe_coe_finding,  # type: ignore[attr-defined]
        aoe_coe_rationale=entry.aoe_coe_rationale,  # type: ignore[attr-defined]
        quality="supported",
    )


def _assertion_from_entry(entry: object) -> ApportionmentAssertion:
    return ApportionmentAssertion(
        id=entry.id,  # type: ignore[attr-defined]
        opinion_id=entry.opinion_id,  # type: ignore[attr-defined]
        body_part=entry.body_part,  # type: ignore[attr-defined]
        industrial_percent=entry.industrial_percent,  # type: ignore[attr-defined]
        nonindustrial_percent=entry.nonindustrial_percent,  # type: ignore[attr-defined]
        basis_kinds=tuple(entry.basis_kinds),  # type: ignore[attr-defined]
        condition_ids=tuple(entry.condition_ids),  # type: ignore[attr-defined]
        prior_claim_ids=tuple(entry.prior_claim_ids),  # type: ignore[attr-defined]
        prior_award_ids=tuple(entry.prior_award_ids),  # type: ignore[attr-defined]
        description=entry.description,  # type: ignore[attr-defined]
        disability_causation_stated=entry.disability_causation_stated,  # type: ignore[attr-defined]
        reasonable_medical_probability=entry.reasonable_medical_probability,  # type: ignore[attr-defined]
        causal_rationale=entry.causal_rationale,  # type: ignore[attr-defined]
        percentage_rationale=entry.percentage_rationale,  # type: ignore[attr-defined]
        prior_award_analysis=entry.prior_award_analysis,  # type: ignore[attr-defined]
        revised_from_percent=entry.revised_from_percent,  # type: ignore[attr-defined]
        revision_rationale=entry.revision_rationale,  # type: ignore[attr-defined]
        psych_exception_analysis=entry.psych_exception_analysis,  # type: ignore[attr-defined]
        linked_contention_id=entry.linked_contention_id,  # type: ignore[attr-defined]
        groundings=_groundings_tuple(entry),
        quality="supported",
    )


#: Canonical (party, position) for each sampled claim type (B.4).
_CANONICAL_STANCE: Final[dict[str, tuple[str, str]]] = {
    "industrial_causation": ("applicant", "affirm"),
    "aggravation": ("applicant", "affirm"),
    "apportionment_defense": ("defense", "affirm"),
    "compensable_consequence": ("applicant", "affirm"),
    "psych_add_on": ("applicant", "affirm"),
    "denial_of_injury": ("defense", "affirm"),
}

#: Label-safe rationale registers for sampled entries. Deliberately free of
#: every reserved token so a rationale can never trip the leakage probe.
_CONTENTION_RATIONALES: Final[dict[str, str]] = {
    "industrial_causation": "the condition arose out of and in the course of employment",
    "aggravation": "the industrial injury aggravated a previously symptomatic condition",
    "apportionment_defense": "a nonindustrial factor contributes to the present disability",
    "compensable_consequence": "the condition followed industrially provided treatment",
    "psych_add_on": "a psychiatric consequence accompanies the physical injury",
    "denial_of_injury": "the claimed condition did not arise from the employment",
}


def _semantic_salt(key: SemanticKey) -> str:
    """A stable string form of a semantic key, for stream salts."""
    parts: list[str] = []
    for value in key:
        if value is None:
            parts.append("~")
        elif isinstance(value, tuple):
            parts.append("+".join(str(item) for item in value))
        else:
            parts.append(str(value))
    return "/".join(parts)


def _normalized_grounding_ids(
    groundings: tuple[DoctrineGrounding, ...],
) -> tuple[tuple[str, ...], ...]:
    """Every grounding as a sorted ``(hook, *entity_ids)`` tuple, sorted."""
    normalized: list[tuple[str, ...]] = []
    for grounding in groundings:
        if isinstance(grounding, BensonGrounding):
            normalized.append(("benson", *sorted(grounding.prior_claim_ids)))
        elif isinstance(grounding, SibtfGrounding):
            normalized.append(
                (
                    "sibtf",
                    *sorted(grounding.preexisting_condition_ids),
                    *sorted(grounding.prior_award_ids),
                )
            )
        elif isinstance(grounding, Lc4664PriorAwardGrounding):
            normalized.append(("lc4664_prior_award", grounding.prior_award_id))
        elif isinstance(grounding, FirefighterPresumptionGrounding):
            normalized.append(("firefighter_presumption", grounding.condition_id))
    return tuple(sorted(normalized))


def _full_stream_key(candidate_family: str, entry: object) -> str:
    """The full Part 3 B.2-B.3 candidate STREAM key, as a salt string.

    ``(candidate_family, claim_type, position, target_condition_id,
    target_prior_claim_id, target_prior_award_id, target_body_part,
    sorted(doctrine_hooks), normalized_grounding_ids)`` — DISTINCT from the
    8-field rule-6 tuple, which stays the suppression-equality instrument
    (sol fix round 2, F3: stream identity and suppression equality are
    different instruments).

    The implemented reading of Part 3's "every stochastic family uses this
    key", flagged for the spec author to ratify (sol open question 2):

    - PRE-type draws — ``contention-incidence`` and ``contention-type`` —
      keep their family-prefixed entity keys (``condition:cond-01``): the
      claim type, stance and groundings this key requires do not exist
      before the type is chosen.
    - Every POST-type contention draw — the quality-target recipe, the
      thin/unsupportable defect draws, the ptp-disposition draw — uses this
      full key.
    - An EXPLICIT contention entering a disposition stream is not a sampled
      candidate, so its family slot carries the literal ``explicit`` — an
      honest, collision-free value (no sampled family is named that).
    - Apportionment-row and opinion streams keep their own assertion/opinion
      keys: the Part 3 clause defines the *candidate* key, and those streams
      are not contention candidates.
    """
    return _semantic_salt(
        (
            candidate_family,
            entry.claim_type,  # type: ignore[attr-defined]
            entry.position,  # type: ignore[attr-defined]
            entry.target_condition_id,  # type: ignore[attr-defined]
            entry.target_prior_claim_id,  # type: ignore[attr-defined]
            entry.target_prior_award_id,  # type: ignore[attr-defined]
            entry.target_body_part,  # type: ignore[attr-defined]
            tuple(sorted(entry.doctrine_hooks)),  # type: ignore[attr-defined]
            _normalized_grounding_ids(entry.groundings),  # type: ignore[attr-defined]
        )
    )


def _rng_candidate_key(draft: _ContentionDraft) -> str:
    """The full stream key of one sampled candidate draft."""
    return _full_stream_key(draft.candidate_family, draft)


def _fraction_draw(rng: random.Random, probability: Fraction) -> bool:
    return rng.random() < float(probability)


def _weighted_index(rng: random.Random, weights: Sequence[Fraction]) -> int:
    draw = rng.random()
    cumulative = 0.0
    for index, weight in enumerate(weights):
        cumulative += float(weight)
        if draw < cumulative:
            return index
    return len(weights) - 1


@dataclass(frozen=True, slots=True)
class _ContentionDraft:
    semantic_key: SemanticKey
    candidate_family: str
    claim_type: str
    party: str
    position: str
    target_condition_id: str | None = None
    target_prior_claim_id: str | None = None
    target_prior_award_id: str | None = None
    target_body_part: str | None = None
    doctrine_hooks: tuple[str, ...] = ()
    rationale: str | None = None
    groundings: tuple[DoctrineGrounding, ...] = ()
    recipe: str = "supported"


def _condition_claim_types(
    condition: ProjectedCondition, context: AssertionValidationContext
) -> tuple[str, ...]:
    """The eligible claim types for one condition candidate, sorted (B.4).

    Overlap is exactly ``not condition.wholly_unrelated`` — never a
    ``body_part`` conjunction, which excluded diabetes/CTS (finding 3).
    """
    eligible: set[str] = set()
    if condition.causal_ground_truth in ("industrial", "mixed"):
        eligible.add("industrial_causation")
    if not condition.wholly_unrelated and condition.causal_ground_truth in (
        "nonindustrial",
        "mixed",
    ):
        eligible.add("aggravation")
        eligible.add("apportionment_defense")
    if condition.wholly_unrelated:
        eligible.add("industrial_causation")
        eligible.add("denial_of_injury")
    if (
        condition.causal_ground_truth == "industrial"
        and condition.onset is not None
        and condition.onset >= context.date_of_injury
    ):
        eligible.add("compensable_consequence")
    return tuple(sorted(eligible))


def _condition_target_part(
    condition: ProjectedCondition, context: AssertionValidationContext
) -> str | None:
    overlap = sorted(set(condition.apportionment_targets) & set(context.current_body_parts))
    if overlap:
        return overlap[0]
    return condition.body_part


def _contention_candidates(
    seed: CaseSeed,
    context: AssertionValidationContext,
    history: AssertionWorldProjection,
    trace: AssertionTrace | None,
) -> list[_ContentionDraft]:
    """Every drawn contention candidate, in deterministic enumeration order."""

    def note_eligible(family: str) -> None:
        if trace is not None:
            trace.eligible_candidates[family] = trace.eligible_candidates.get(family, 0) + 1

    def note_drawn(family: str) -> None:
        if trace is not None:
            trace.candidate_families[family] = trace.candidate_families.get(family, 0) + 1

    drafts: list[_ContentionDraft] = []
    firefighter_hook = "firefighter_presumption" in seed.lifecycle.doctrine_hooks

    for condition in history.conditions:
        # Eligibility is the world-truth TYPE — the B.4 table row, nothing
        # more. Visibility is B.5's business: a contention on a condition the
        # file never shows is perfectly draftable, its evidence just reads
        # indeterminate rather than supports.
        claim_types = _condition_claim_types(condition, context)
        if claim_types:
            note_eligible("condition")
            incidence = _assertion_rng(seed, "contention-incidence", f"condition:{condition.id}")
            if _fraction_draw(incidence, P_CONTENTION_GIVEN_CONDITION.value):
                note_drawn("condition")
                chooser = _assertion_rng(seed, "contention-type", f"condition:{condition.id}")
                claim_type = claim_types[chooser.randrange(len(claim_types))]
                party, position = _CANONICAL_STANCE[claim_type]
                target_part = _condition_target_part(condition, context)
                key: SemanticKey = (
                    "contention",
                    claim_type,
                    position,
                    condition.id,
                    None,
                    None,
                    target_part,
                    (),
                )
                drafts.append(
                    _ContentionDraft(
                        semantic_key=key,
                        candidate_family="condition",
                        claim_type=claim_type,
                        party=party,
                        position=position,
                        target_condition_id=condition.id,
                        target_body_part=target_part,
                        rationale=_CONTENTION_RATIONALES[claim_type],
                    )
                )
        if firefighter_hook and condition.body_system == "oncologic":
            note_eligible("firefighter")
            incidence = _assertion_rng(seed, "contention-incidence", f"firefighter:{condition.id}")
            if _fraction_draw(incidence, P_FIREFIGHTER_CONTENTION.value):
                note_drawn("firefighter")
                key = (
                    "contention",
                    "industrial_causation",
                    "affirm",
                    condition.id,
                    None,
                    None,
                    condition.body_part,
                    ("firefighter_presumption",),
                )
                drafts.append(
                    _ContentionDraft(
                        semantic_key=key,
                        candidate_family="firefighter",
                        claim_type="industrial_causation",
                        party="applicant",
                        position="affirm",
                        target_condition_id=condition.id,
                        target_body_part=condition.body_part,
                        doctrine_hooks=("firefighter_presumption",),
                        rationale=(
                            "the presumption attaches to this diagnosis under the "
                            "safety-member statutes"
                        ),
                        groundings=(FirefighterPresumptionGrounding(condition_id=condition.id),),
                    )
                )

    for claim in history.prior_claims:
        if not claim.overlaps_current:
            continue
        note_eligible("prior_claim")
        incidence = _assertion_rng(seed, "contention-incidence", f"prior_claim:{claim.id}")
        if _fraction_draw(incidence, P_PRIOR_CLAIM_CONTENTION.value):
            note_drawn("prior_claim")
            key = (
                "contention",
                "apportionment_defense",
                "affirm",
                None,
                claim.id,
                None,
                None,
                ("benson",),
            )
            drafts.append(
                _ContentionDraft(
                    semantic_key=key,
                    candidate_family="prior_claim",
                    claim_type="apportionment_defense",
                    party="defense",
                    position="affirm",
                    target_prior_claim_id=claim.id,
                    doctrine_hooks=("benson",),
                    rationale=_CONTENTION_RATIONALES["apportionment_defense"],
                    groundings=(BensonGrounding(prior_claim_ids=(claim.id,)),),
                )
            )

    for claim in history.prior_claims:
        award = claim.award
        if award is None or not claim.overlaps_current or not award.conclusively_presumed:
            continue
        note_eligible("prior_award")
        incidence = _assertion_rng(seed, "contention-incidence", f"award:{award.id}")
        if _fraction_draw(incidence, P_PRIOR_AWARD_CONTENTION.value):
            note_drawn("prior_award")
            key = (
                "contention",
                "apportionment_defense",
                "affirm",
                None,
                claim.id,
                award.id,
                None,
                ("lc4664_prior_award",),
            )
            drafts.append(
                _ContentionDraft(
                    semantic_key=key,
                    candidate_family="prior_award",
                    claim_type="apportionment_defense",
                    party="defense",
                    position="affirm",
                    target_prior_claim_id=claim.id,
                    target_prior_award_id=award.id,
                    doctrine_hooks=("lc4664_prior_award",),
                    rationale="the prior award conclusively presumes continuing disability",
                    groundings=(Lc4664PriorAwardGrounding(prior_award_id=award.id),),
                )
            )

    sibtf_clauses = sibtf_grounding_clauses(history)
    if sibtf_clauses:
        note_eligible("sibtf")
        incidence = _assertion_rng(seed, "contention-incidence", "sibtf:case")
        if _fraction_draw(incidence, P_SIBTF_CONTENTION.value):
            note_drawn("sibtf")
            qualifying_conditions = tuple(
                c.id
                for c in history.conditions
                if c.symptomatic_before_doi is True
                and c.severity == "severe"
                and c.trajectory != "resolved"
            )
            award_ids = tuple(a.id for a in history.awards)
            # Target the concrete qualifying entity, award first — a
            # target-free defense contention would read indeterminate against
            # any record, and the SIBTF argument is about *that* disability.
            target_award = award_ids[0] if award_ids else None
            target_condition = (
                qualifying_conditions[0] if target_award is None and qualifying_conditions else None
            )
            target_claim = (
                history.prior_award(target_award).prior_claim_id
                if target_award is not None
                else None
            )
            key = (
                "contention",
                "apportionment_defense",
                "affirm",
                target_condition,
                target_claim,
                target_award,
                None,
                ("sibtf",),
            )
            drafts.append(
                _ContentionDraft(
                    semantic_key=key,
                    candidate_family="sibtf",
                    claim_type="apportionment_defense",
                    party="applicant",
                    position="affirm",
                    target_condition_id=target_condition,
                    target_prior_claim_id=target_claim,
                    target_prior_award_id=target_award,
                    doctrine_hooks=("sibtf",),
                    rationale="a prior permanent disability combines with the new injury",
                    groundings=(
                        SibtfGrounding(
                            preexisting_condition_ids=qualifying_conditions,
                            prior_award_ids=award_ids,
                        ),
                    ),
                )
            )

    if context.claim_response == "denied":
        # A denied current claim carries its denial contention deterministically
        # rather than entering any rate denominator (Part 3 B.4-B.5).
        key = ("contention", "denial_of_injury", "affirm", None, None, None, None, ())
        drafts.append(
            _ContentionDraft(
                semantic_key=key,
                candidate_family="denial",
                claim_type="denial_of_injury",
                party="defense",
                position="affirm",
                rationale=_CONTENTION_RATIONALES["denial_of_injury"],
            )
        )

    psych_component = _fraction_draw(
        _assertion_rng(seed, "psych-component", "case"), P_PSYCH_COMPONENT.value
    )
    if trace is not None and psych_component:
        trace.candidate_families["psych_component"] = (
            trace.candidate_families.get("psych_component", 0) + 1
        )
    if psych_component and _fraction_draw(
        _assertion_rng(seed, "psych-add-on-contention", "case"),
        P_PSYCH_ADD_ON_CONTENTION_GIVEN_COMPONENT.value,
    ):
        psych = next((c for c in history.conditions if c.key == "depression_anxiety"), None)
        key = (
            "contention",
            "psych_add_on",
            "affirm",
            psych.id if psych is not None else None,
            None,
            None,
            psych.body_part if psych is not None else "psyche",
            (),
        )
        drafts.append(
            _ContentionDraft(
                semantic_key=key,
                candidate_family="psych_add_on",
                claim_type="psych_add_on",
                party="applicant",
                position="affirm",
                target_condition_id=psych.id if psych is not None else None,
                target_body_part=psych.body_part if psych is not None else "psyche",
                rationale=_CONTENTION_RATIONALES["psych_add_on"],
            )
        )
        if trace is not None:
            trace.candidate_families["psych_add_on"] = (
                trace.candidate_families.get("psych_add_on", 0) + 1
            )

    return drafts


def _apply_contention_recipe(
    seed: CaseSeed,
    history: AssertionWorldProjection,
    context: AssertionValidationContext,
    draft: _ContentionDraft,
) -> _ContentionDraft:
    """Draw the quality-target recipe and shape the draft's construction.

    The target selects a RECIPE, never a grade: supported keeps the reasoned
    build; thin drops the rationale; unsupportable rebuilds toward the pole
    the evidence contradicts (or, for psych, one of the named defense
    variants). The target is then discarded — the deterministic grader owns
    the label, and any recipe/grade disagreement is measured, not hidden.
    """
    salt = _rng_candidate_key(draft)
    target_index = _weighted_index(
        _assertion_rng(seed, "quality-target", salt), QUALITY_TARGET_WEIGHTS.value
    )
    target = ("supported", "thin", "unsupportable")[target_index]
    shaped = draft
    if target in ("supported", "thin"):
        # A supported (or merely thin) BUILD aims at a supportable construction:
        # a multi-eligible condition candidate steers to an eligible claim type
        # the evidence actually supports, when one exists. Deterministic — no
        # draw — and only construction moves; the grade is still rederived.
        shaped = _steer_to_supported_type(history, context, shaped)
    if target == "thin":
        chooser = _assertion_rng(seed, "thin-defect", salt)
        # One thin lever exists at contention level; the draw stays for
        # determinism symmetry (and future levers) rather than deciding much.
        chooser.random()
        shaped = _replace_draft(shaped, rationale=None)
    elif target == "unsupportable":
        chooser = _assertion_rng(seed, "unsupportable-defect", salt)
        psych_eligible = draft.claim_type == "psych_add_on"
        if psych_eligible:
            roll = chooser.random()
            if roll < float(P_PSYCH_PREDOMINANT_CAUSE_DENIAL.value):
                shaped = _replace_draft(
                    draft,
                    claim_type="denial_of_injury",
                    party="defense",
                    rationale=(
                        "actual events of employment were not the predominant cause "
                        "of the psychiatric injury"
                    ),
                )
            elif roll < float(P_PSYCH_PREDOMINANT_CAUSE_DENIAL.value + P_GFPA_DEFENSE.value):
                shaped = _replace_draft(
                    draft,
                    claim_type="denial_of_injury",
                    party="defense",
                    doctrine_hooks=("gfpa",),
                    rationale=(
                        "the psychiatric claim arises from lawful, nondiscriminatory "
                        "good faith personnel actions"
                    ),
                )
            else:
                shaped = _contradicted_draft(history, context, draft, chooser)
        else:
            shaped = _contradicted_draft(history, context, draft, chooser)
    return _replace_draft(shaped, recipe=target)


def _replace_draft(draft: _ContentionDraft, **updates: object) -> _ContentionDraft:
    values = {
        "semantic_key": draft.semantic_key,
        "candidate_family": draft.candidate_family,
        "claim_type": draft.claim_type,
        "party": draft.party,
        "position": draft.position,
        "target_condition_id": draft.target_condition_id,
        "target_prior_claim_id": draft.target_prior_claim_id,
        "target_prior_award_id": draft.target_prior_award_id,
        "target_body_part": draft.target_body_part,
        "doctrine_hooks": draft.doctrine_hooks,
        "rationale": draft.rationale,
        "groundings": draft.groundings,
        "recipe": draft.recipe,
    }
    values.update(updates)
    return _ContentionDraft(**values)  # type: ignore[arg-type]


def _draft_evidence(
    history: AssertionWorldProjection,
    context: AssertionValidationContext,
    draft: _ContentionDraft,
) -> EvidenceDisposition:
    probe = Contention(
        id="ctn-99",
        claim_type=draft.claim_type,  # type: ignore[arg-type]
        party=draft.party,  # type: ignore[arg-type]
        position=draft.position,  # type: ignore[arg-type]
        target_condition_id=draft.target_condition_id,
        target_prior_claim_id=draft.target_prior_claim_id,
        target_prior_award_id=draft.target_prior_award_id,
        target_body_part=draft.target_body_part,
        quality="supported",
    )
    return contention_evidence(history, context, probe)


def _steer_to_supported_type(
    history: AssertionWorldProjection,
    context: AssertionValidationContext,
    draft: _ContentionDraft,
) -> _ContentionDraft:
    """Steer a condition candidate to an evidence-supported eligible type.

    Only construction moves: same candidate, same targets, first eligible type
    (sorted) whose canonical-stance evidence reads ``supports``. Candidates
    with a single fixed type — doctrine, denial, psych — are returned as-is.
    """
    if draft.candidate_family != "condition":
        return draft
    if _draft_evidence(history, context, draft) == "supports":
        return draft
    condition = (
        history.condition(draft.target_condition_id)
        if draft.target_condition_id is not None
        else None
    )
    if condition is None:
        return draft
    for claim_type in _condition_claim_types(condition, context):
        party, position = _CANONICAL_STANCE[claim_type]
        candidate = _replace_draft(
            draft,
            claim_type=claim_type,
            party=party,
            position=position,
            rationale=_CONTENTION_RATIONALES[claim_type],
        )
        if _draft_evidence(history, context, candidate) == "supports":
            return candidate
    return draft


def _contradicted_draft(
    history: AssertionWorldProjection,
    context: AssertionValidationContext,
    draft: _ContentionDraft,
    chooser: random.Random,
) -> _ContentionDraft:
    """The generic unsupportable recipe: face the pole the evidence rejects."""
    chooser.random()
    probe = Contention(
        id="ctn-99",
        claim_type=draft.claim_type,  # type: ignore[arg-type]
        party=draft.party,  # type: ignore[arg-type]
        position=draft.position,  # type: ignore[arg-type]
        target_condition_id=draft.target_condition_id,
        target_prior_claim_id=draft.target_prior_claim_id,
        target_prior_award_id=draft.target_prior_award_id,
        target_body_part=draft.target_body_part,
        quality="supported",
    )
    if contention_evidence(history, context, probe) == "contradicts":
        return draft
    flipped = "deny" if draft.position == "affirm" else "affirm"
    return _replace_draft(draft, position=flipped)


def _stage_report_date(context: AssertionValidationContext, stage: str) -> dt.date:
    offsets = {"interim": 120, "final": 300}
    proposed = context.date_of_injury + dt.timedelta(days=offsets[stage])
    return min(proposed, context.anchor_date)


def _visible_records(
    history: AssertionWorldProjection,
) -> list[tuple[str, str]]:
    """Every reviewable record as ``(family, id)``, in stable ID order."""
    records = [("condition", c.id) for c in history.conditions if c.surfaces_in_file]
    records.extend(("prior_claim", c.id) for c in history.prior_claims)
    records.extend(("prior_award", a.id) for a in history.awards)
    return sorted(records, key=lambda item: (item[0], item[1]))


def _append_sampled(
    *,
    seed: CaseSeed,
    context: AssertionValidationContext,
    history: AssertionWorldProjection,
    contentions: list[Contention],
    opinions: list[MedicalOpinion],
    assertions: list[ApportionmentAssertion],
    trace: AssertionTrace | None,
) -> tuple[list[Contention], list[MedicalOpinion], list[ApportionmentAssertion]]:
    """Sample and append, without ever altering an explicit entry.

    Every stochastic decision draws from its own semantically keyed stream, so
    an explicit entry's presence changes composition only through suppression —
    a skip, never a redraw. IDs are assigned last, as a pure labelling pass in
    semantic-key order, and internal references resolve through the key->ID
    maps.
    """
    explicit_keys = frozenset(_contention_semantic_key(c) for c in contentions)

    drafts = _contention_candidates(seed, context, history, trace)

    # Shape FIRST. Every recipe/defect draw is keyed by the candidate's
    # original semantic identity, so shaping a candidate that suppression will
    # later drop cannot move any other candidate's stream.
    shaped = [_apply_contention_recipe(seed, history, context, draft) for draft in drafts]

    # Normalize the FINAL semantic key from the shaped surface, with the same
    # B.2 rule-6 function that keys explicit entries. Shaping can change claim
    # type, party, position or hooks; suppressing on the pre-shaping key would
    # let a candidate become semantically identical to an explicit contention
    # AFTER the only suppression pass (sol review, PR #44 M1).
    normalized = [
        _replace_draft(draft, semantic_key=_contention_semantic_key(draft)) for draft in shaped
    ]
    candidates = tuple(
        AssertionCandidate(
            semantic_key=draft.semantic_key,
            candidate_family=draft.candidate_family,
            payload={"draft": draft},
        )
        for draft in normalized
    )
    retained, suppression_hits = _suppress_explicit_collisions(candidates, explicit_keys)
    if trace is not None:
        trace.suppression_hits += suppression_hits

    ordered = sorted(
        (candidate.payload["draft"] for candidate in retained),
        key=lambda draft: _semantic_salt(draft.semantic_key),  # type: ignore[attr-defined]
    )
    # The 12-cap truncates in final-key order BEFORE anything downstream reads
    # the contention set: a truncated candidate must not shape the opinion it
    # can no longer appear beside. IDs are NOT assigned here — every
    # stochastic decision completes first, and one labelling pass at the end
    # assigns ctn/opn/app suffixes and resolves references (globally
    # IDs-last).
    ordered = ordered[: max(0, 12 - len(contentions))]

    # Every contention the opinion machinery may read: explicit entries under
    # their real IDs, sampled drafts under their final semantic keys, each
    # carrying its full Part-3 stream key for the disposition draws. The
    # probe objects carry the exact final fields; only the ID is a
    # placeholder, and nothing below reads it.
    pending: list[tuple[str | SemanticKey, Contention, str]] = [
        (contention.id, contention, _full_stream_key("explicit", contention))
        for contention in contentions
    ]
    for draft in ordered:
        pending.append(
            (
                draft.semantic_key,
                Contention(
                    id="ctn-99",  # labelled last
                    claim_type=draft.claim_type,  # type: ignore[arg-type]
                    party=draft.party,  # type: ignore[arg-type]
                    position=draft.position,  # type: ignore[arg-type]
                    target_condition_id=draft.target_condition_id,
                    target_prior_claim_id=draft.target_prior_claim_id,
                    target_prior_award_id=draft.target_prior_award_id,
                    target_body_part=draft.target_body_part,
                    doctrine_hooks=draft.doctrine_hooks,  # type: ignore[arg-type]
                    rationale=draft.rationale,
                    groundings=draft.groundings,
                    quality="supported",
                ),
                _rng_candidate_key(draft),
            )
        )

    # --- the stage's sampled evaluator opinion (B.6) ------------------------
    sampled_opinions: list[MedicalOpinion] = []
    pending_dispositions: list[tuple[list[str | SemanticKey], list[str | SemanticKey]]] = []
    pending_opinion_recipes: list[str] = []
    sampled_assertions: list[ApportionmentAssertion] = []
    stage = context.target_stage
    if stage != "intake" and len(opinions) < 8:
        if stage in ("active_treatment", "discovery"):
            author_role, report_stage, state = "ptp", "interim", "deferred"
        elif stage == "medical_legal":
            author_role = context.eval_type if context.eval_type in ("qme", "ame") else "ptp"
            opinion_salt = f"{author_role}:case"
            deferred = _fraction_draw(
                _assertion_rng(seed, "medical-legal-deferral", opinion_salt),
                P_MEDLEGAL_DEFERRAL.value,
            )
            report_stage, state = ("interim", "deferred") if deferred else ("final", "determined")
        else:  # pre_trial | resolved | post_recon
            author_role = context.eval_type if context.eval_type in ("qme", "ame") else "ptp"
            report_stage, state = "final", "determined"
        opinion_salt = f"{author_role}:case"

        # The opinion's own quality-target recipe. Counsel's q7 figure was
        # stated about OPINIONS, and it describes realized output, so the
        # construction mix is OPINION_RECIPE_WEIGHTS — the counsel target
        # solved against the measured worst-of drag. Semantically salted like
        # every other stream; the target drives only the opinion's OWN
        # foundation construction (B.8's exam / relevant-review / rationale
        # row) and is then discarded — the worst-of grader owns the label,
        # and B.6's omission, deferral and zero-share machinery keep their
        # independent counsel-knobbed draws.
        opinion_recipe = ("supported", "thin", "unsupportable")[
            _weighted_index(
                _assertion_rng(seed, "quality-target", opinion_salt),
                OPINION_RECIPE_WEIGHTS.value,
            )
        ]

        determination_kind: str | None = None
        determination_rationale: str | None = None
        branch = "-"
        if report_stage == "final":
            omitted = _fraction_draw(
                _assertion_rng(seed, "final-omission", opinion_salt),
                P_FINAL_REPORT_OMITS_APPORTIONMENT.value,
            )
            if omitted:
                state = "omitted"
                branch = "omitted"
            else:
                state = "determined"
                substantial = has_substantial_nonindustrial_evidence(history)
                if substantial:
                    branch = "A"
                    nonzero = _fraction_draw(
                        _assertion_rng(seed, "nonzero-apportionment", opinion_salt),
                        P_NONZERO_APPORTIONMENT.value,
                    )
                    if nonzero:
                        determination_kind = "allocated"
                    elif _fraction_draw(
                        _assertion_rng(seed, "determination-kind", opinion_salt),
                        P_ZERO_SHARE_DEFECT_GIVEN_NONZERO_MISS.value,
                    ):
                        # The deliberate contradicted-zero-share defect.
                        determination_kind = "no_nonindustrial_share"
                        determination_rationale = (
                            "the entire disability is industrial; no other factor "
                            "requires discussion"
                        )
                    else:
                        determination_kind = "unable_to_approximate"
                        determination_rationale = (
                            "the relative contributions cannot be approximated to "
                            "reasonable medical probability on this record"
                        )
                else:
                    contributor_exists = any(
                        not c.wholly_unrelated
                        and c.causal_ground_truth in ("nonindustrial", "mixed")
                        and c.trajectory != "resolved"
                        for c in history.conditions
                    )
                    if contributor_exists:
                        branch = "C"
                        determination_kind = "unable_to_approximate"
                        determination_rationale = (
                            "the undocumented history precludes approximating the "
                            "contributions to reasonable medical probability"
                        )
                    else:
                        branch = "B"
                        determination_kind = "no_nonindustrial_share"
                        determination_rationale = (
                            "the record affirmatively shows the disability is entirely industrial"
                        )

        # The review budget, drawn before the rows so a coherent build can
        # align its citations with the record it will actually review (item 5b
        # is a *planted* defect, never an accident of ordering).
        budget = 1 + _weighted_index(
            _assertion_rng(seed, "evidence-budget", opinion_salt),
            EVIDENCE_BUDGET_MIX.value,
        )
        if trace is not None:
            trace.evidence_budgets.append(budget)

        # Dispositions. The evidence policy is absolute — an evaluator never
        # endorses what the record contradicts and always rejects it — while
        # WHICH supported claims the report takes up is construction: a real
        # report addresses the disputed issue, not the docket. The opinion's
        # quality-target recipe never touches dispositions; it drives the
        # foundation surface alone, and everything the opinion stands behind
        # still grades it through the worst-of rubric.
        endorses: list[str | SemanticKey] = []
        rejects: list[str | SemanticKey] = []
        supportable: list[tuple[str | SemanticKey, Contention, str]] = []
        for ref, contention, stream_key in pending:
            evidence = contention_evidence(history, context, contention)
            if evidence == "contradicts" and author_role in ("qme", "ame"):
                if qme_disposition(evidence) == "reject":
                    rejects.append(ref)
            elif evidence == "supports":
                supportable.append((ref, contention, stream_key))
        if supportable:
            # Grade bookkeeping keys on the UNIQUE pending reference, never
            # the B.2 suppression tuple: two distinct explicit contentions may
            # legally share that tuple, and a tuple-keyed dict kept only the
            # last twin's grade — a thin ctn-02 erased a supported ctn-01's
            # endorsement (sol fix round 2, F2, proved on cohort-4803).
            would_be = {
                ref: contention_quality(
                    history,
                    context,
                    c,
                    quality_contract="2.0.0",
                )
                for ref, c, _key in supportable
            }
            pick = next(
                (item for item in supportable if would_be[item[0]] == "supported"),
                supportable[0] if author_role == "ptp" else None,
            )
            if pick is not None:
                pick_ref, _pick_contention, pick_stream_key = pick
                if author_role in ("qme", "ame"):
                    if qme_disposition("supports") == "endorse":
                        endorses.append(pick_ref)
                else:
                    if _fraction_draw(
                        _assertion_rng(seed, "ptp-disposition", pick_stream_key),
                        P_PTP_ENDORSE_SUPPORTED.value,
                    ):
                        endorses.append(pick_ref)
        elif author_role == "ptp" and pending:
            # The treater's occasional adoption of a weaker claim keeps the
            # indeterminate/contradicted PTP policies live decision families.
            candidate_ref, candidate, candidate_stream_key = pending[0]
            evidence = contention_evidence(history, context, candidate)
            endorse_p = {
                "supports": P_PTP_ENDORSE_SUPPORTED.value,
                "indeterminate": P_PTP_ENDORSE_INDETERMINATE.value,
                "contradicts": P_PTP_ENDORSE_CONTRADICTED.value,
            }[evidence]
            if _fraction_draw(
                _assertion_rng(seed, "ptp-disposition", candidate_stream_key), endorse_p
            ):
                endorses.append(candidate_ref)

        # The record pool a supported build may cite: the first ``budget``
        # relevant, visible entities. Reviewed is built FROM the citations, so
        # the review-gap defect is only ever planted by the thin lever.
        def _relevant_pool() -> list[tuple[str, str]]:
            pool: list[tuple[str, str]] = []
            contributors_pool = [
                c
                for c in history.conditions
                if not c.wholly_unrelated
                and c.causal_ground_truth in ("nonindustrial", "mixed")
                and c.surfaces_in_file
                and c.trajectory != "resolved"
            ]
            pool.extend(("condition", c.id) for c in contributors_pool)
            for claim in history.prior_claims:
                if (
                    claim.award is not None
                    and claim.overlaps_current
                    and claim.award.conclusively_presumed
                ):
                    pool.append(("prior_award", claim.award.id))
            for ref, contention, _stream_key in pending:
                if ref in endorses or ref in rejects:
                    if contention.target_condition_id is not None:
                        condition = history.condition(contention.target_condition_id)
                        if condition is not None and condition.surfaces_in_file:
                            pool.append(("condition", condition.id))
                    if contention.target_prior_claim_id is not None:
                        pool.append(("prior_claim", contention.target_prior_claim_id))
                    if contention.target_prior_award_id is not None:
                        pool.append(("prior_award", contention.target_prior_award_id))
            deduped: list[tuple[str, str]] = []
            for record in pool:
                if record not in deduped:
                    deduped.append(record)
            return deduped

        citable = _relevant_pool()[:budget]

        # Allocated rows: one per targeted body part, register-drawn split.
        if determination_kind == "allocated":
            contributors = [
                c
                for c in history.conditions
                if not c.wholly_unrelated
                and c.causal_ground_truth in ("nonindustrial", "mixed")
                and c.surfaces_in_file
                and c.trajectory != "resolved"
            ]
            parts = sorted(
                {
                    part
                    for c in contributors
                    for part in c.apportionment_targets
                    if part in context.current_body_parts
                }
                | {
                    part
                    for claim in history.prior_claims
                    if claim.award is not None
                    and claim.overlaps_current
                    and claim.award.conclusively_presumed
                    for part in claim.award.body_parts
                    if part in context.current_body_parts
                }
            )
            for part in parts:
                if len(assertions) + len(sampled_assertions) >= 12:
                    break
                assertion_salt = f"{opinion_salt}:{part}"
                register = _assertion_rng(seed, "percentage-register", assertion_salt)
                if _fraction_draw(register, P_COMMON_PERCENTAGE_REGISTER.value):
                    nonindustrial = COMMON_NONINDUSTRIAL_PERCENTAGES[
                        register.randrange(len(COMMON_NONINDUSTRIAL_PERCENTAGES))
                    ]
                else:
                    granular = [
                        value
                        for value in range(1, 100)
                        if value not in COMMON_NONINDUSTRIAL_PERCENTAGES
                    ]
                    nonindustrial = granular[register.randrange(len(granular))]
                citable_conditions = {r for f, r in citable if f == "condition"}
                citable_awards = {r for f, r in citable if f == "prior_award"}
                part_conditions = tuple(
                    c.id
                    for c in contributors
                    if part in c.apportionment_targets and c.id in citable_conditions
                )
                part_awards = tuple(
                    claim.award.id
                    for claim in history.prior_claims
                    if claim.award is not None
                    and claim.overlaps_current
                    and claim.award.conclusively_presumed
                    and part in claim.award.body_parts
                    and claim.award.id in citable_awards
                )
                part_claims: tuple[str, ...] = ()
                if not part_conditions and not part_awards and citable:
                    # Every row states at least one record it relies on (item
                    # 3a); at budget 1 that can be the pool's one record even
                    # when it sits off this exact part — realistic, and still
                    # a reviewed, visible citation.
                    family, ref = citable[0]
                    if family == "condition":
                        part_conditions = (ref,)
                    elif family == "prior_award":
                        part_awards = (ref,)
                    else:
                        part_claims = (ref,)
                basis: list[str] = []
                if part_claims:
                    basis.append("prior_symptomatic_disability")
                for ref in part_conditions:
                    condition = history.condition(ref)
                    if condition is None:
                        continue
                    if condition.symptomatic_before_doi is True:
                        kind = "prior_symptomatic_disability"
                    elif condition.symptomatic_before_doi is False:
                        kind = "asymptomatic_prior_condition"
                    else:
                        kind = "nonindustrial_medical_condition"
                    if kind not in basis:
                        basis.append(kind)
                groundings: list[DoctrineGrounding] = []
                if part_awards:
                    basis.append("lc4664_prior_award")
                    groundings.append(Lc4664PriorAwardGrounding(prior_award_id=part_awards[0]))
                assertion_key: SemanticKey = ("apportionment", author_role, part)
                target_index = _weighted_index(
                    _assertion_rng(seed, "quality-target", _semantic_salt(assertion_key)),
                    QUALITY_TARGET_WEIGHTS.value,
                )
                recipe = ("supported", "thin", "unsupportable")[target_index]
                fields: dict[str, object] = {
                    "description": (f"chronic {part} disability limiting sustained activity"),
                    "disability_causation_stated": True,
                    "reasonable_medical_probability": True,
                    "causal_rationale": (
                        "the documented pathology contributes to the present "
                        "disability by continuing mechanical compromise"
                    ),
                    "percentage_rationale": (
                        "the share reflects the documented severity relative to "
                        "the industrial mechanism"
                    ),
                    "prior_award_analysis": (
                        "the prior award is treated separately under the conclusive presumption"
                        if part_awards
                        else None
                    ),
                }
                uncited_contributor = next(
                    (
                        c.id
                        for c in contributors
                        if part in c.apportionment_targets and c.id not in part_conditions
                    ),
                    None,
                )
                if recipe == "thin":
                    levers = [
                        "description",
                        "disability_causation_stated",
                        "reasonable_medical_probability",
                        "causal_rationale",
                        "percentage_rationale",
                        "review_gap",
                    ]
                    if uncited_contributor is None:
                        levers.remove("review_gap")
                    lever = levers[
                        _assertion_rng(
                            seed, "thin-defect", _semantic_salt(assertion_key)
                        ).randrange(len(levers))
                    ]
                    if lever == "review_gap":
                        # Item 5b, planted: rely on a record the review never
                        # reached.
                        part_conditions = (*part_conditions, uncited_contributor)
                    elif lever in ("disability_causation_stated", "reasonable_medical_probability"):
                        fields[lever] = False
                    else:
                        fields[lever] = None
                elif recipe == "unsupportable":
                    variants = [
                        "vocational_apportionment",
                        "bare_age",
                        "bare_gender",
                        "risk_factor_only",
                    ]
                    variant = variants[
                        _assertion_rng(
                            seed, "unsupportable-defect", _semantic_salt(assertion_key)
                        ).randrange(len(variants))
                    ]
                    basis.append(variant)
                sampled_assertions.append(
                    ApportionmentAssertion(
                        id="app-99",  # relabelled below
                        opinion_id="opn-99",
                        body_part=part,
                        industrial_percent=100 - nonindustrial,
                        nonindustrial_percent=nonindustrial,
                        basis_kinds=tuple(basis),  # type: ignore[arg-type]
                        condition_ids=part_conditions,
                        prior_claim_ids=part_claims,
                        prior_award_ids=part_awards,
                        groundings=tuple(groundings),
                        quality="supported",
                        **fields,  # type: ignore[arg-type]
                    )
                )
                if trace is not None:
                    trace.recipes.append((f"app@{part}", recipe, ""))

        # Reviewed records: the citable pool first (relevant records, capped at
        # the budget), filled from other visible records in stable ID order,
        # plus the label-independent distractor (B.7). The thin lever's extra
        # citation deliberately stays OUT of the review — that is the planted
        # 5b gap, and the only route to one.
        reviewed: list[tuple[str, str]] = list(citable)
        for record in _visible_records(history):
            if len(reviewed) >= budget:
                break
            if record not in reviewed:
                reviewed.append(record)
        relevant_all = _relevant_pool()
        unselected_irrelevant = [
            record
            for record in _visible_records(history)
            if record not in reviewed and record not in relevant_all
        ]
        if unselected_irrelevant:
            if trace is not None:
                trace.distractor_available += 1
            if _fraction_draw(
                _assertion_rng(seed, "evidence-distractor", opinion_salt),
                P_EVIDENCE_DISTRACTOR.value,
            ):
                reviewed.append(unselected_irrelevant[0])
                if trace is not None:
                    trace.distractor_included += 1

        # The recipe's foundation levers (B.8's own-foundation row). thin:
        # drop the rationale — exam and review stand, missing-one grades thin.
        # unsupportable: no exam, no rationale, and — only when the opinion
        # carries no allocated rows — no review either, so the foundation is
        # empty without planting an accidental item-5b gap under every owned
        # assertion. With rows present the review survives and the build
        # grades thin: recipe/grade disagreement is measured, never hidden.
        if opinion_recipe == "unsupportable" and not sampled_assertions:
            reviewed = []
        sampled_opinions.append(
            MedicalOpinion(
                id="opn-99",  # relabelled below
                author_role=author_role,  # type: ignore[arg-type]
                report_stage=report_stage,  # type: ignore[arg-type]
                report_date=_stage_report_date(context, report_stage),
                apportionment_state=state,  # type: ignore[arg-type]
                determination_kind=determination_kind,  # type: ignore[arg-type]
                determination_rationale=determination_rationale,
                examination_performed=opinion_recipe != "unsupportable",
                reviewed_condition_ids=tuple(
                    ref for family, ref in reviewed if family == "condition"
                ),
                reviewed_prior_claim_ids=tuple(
                    ref for family, ref in reviewed if family == "prior_claim"
                ),
                reviewed_prior_award_ids=tuple(
                    ref for family, ref in reviewed if family == "prior_award"
                ),
                endorses_contention_ids=(),  # refs resolved in the labelling pass
                rejects_contention_ids=(),
                rationale=(
                    "the conclusions rest on the examination and the record reviewed"
                    if opinion_recipe == "supported"
                    else None
                ),
                quality="supported",
            )
        )
        pending_dispositions.append((list(endorses), list(rejects)))
        pending_opinion_recipes.append(opinion_recipe)
        if trace is not None:
            trace.lifecycle.append(
                f"{author_role}:{report_stage}:{state}:{determination_kind or '-'}:{branch}"
            )

    # --- the single labelling pass: every stochastic decision is complete ---
    # Contention suffixes first (explicit reserved; first unused, final-key
    # order), then opinions, then assertion rows; references resolve through
    # the key->ID maps and never the other way around.
    used_contention_ids = {c.id for c in contentions}
    key_to_contention_id: dict[SemanticKey, str] = {}
    sampled_contentions: list[Contention] = []
    for draft, (_ref, probe, _stream_key) in zip(ordered, pending[len(contentions) :], strict=True):
        assigned = _first_unused("ctn", used_contention_ids)
        used_contention_ids.add(assigned)
        key_to_contention_id.setdefault(draft.semantic_key, assigned)
        sampled_contentions.append(probe.model_copy(update={"id": assigned}))
        if trace is not None:
            trace.recipes.append((assigned, draft.recipe, ""))
    all_contentions = [*contentions, *sampled_contentions]

    def _resolve_ref(ref: str | SemanticKey) -> str:
        return ref if isinstance(ref, str) else key_to_contention_id[ref]

    used_opinion_ids = {o.id for o in opinions}
    relabelled_opinions: list[MedicalOpinion] = []
    opinion_id_map: dict[str, str] = {}
    for opinion, (endorse_refs, reject_refs), opinion_recipe in zip(
        sampled_opinions, pending_dispositions, pending_opinion_recipes, strict=True
    ):
        assigned = _first_unused("opn", used_opinion_ids)
        used_opinion_ids.add(assigned)
        opinion_id_map[opinion.id] = assigned
        relabelled_opinions.append(
            opinion.model_copy(
                update={
                    "id": assigned,
                    "endorses_contention_ids": tuple(_resolve_ref(ref) for ref in endorse_refs),
                    "rejects_contention_ids": tuple(_resolve_ref(ref) for ref in reject_refs),
                }
            )
        )
        if trace is not None:
            trace.recipes.append((assigned, opinion_recipe, ""))

    used_assertion_ids = {a.id for a in assertions}
    relabelled_assertions: list[ApportionmentAssertion] = []
    for assertion in sampled_assertions:
        assigned = _first_unused("app", used_assertion_ids)
        used_assertion_ids.add(assigned)
        if trace is not None:
            trace.recipes = [
                (assigned, recipe, realized)
                if key == f"app@{assertion.body_part}"
                else (key, recipe, realized)
                for key, recipe, realized in trace.recipes
            ]
        relabelled_assertions.append(
            assertion.model_copy(
                update={
                    "id": assigned,
                    "opinion_id": opinion_id_map.get(assertion.opinion_id, assertion.opinion_id),
                }
            )
        )

    return (
        all_contentions,
        [*opinions, *relabelled_opinions],
        [*assertions, *relabelled_assertions],
    )


def _first_unused(prefix: str, used: set[str]) -> str:
    for suffix in range(1, 100):
        candidate = f"{prefix}-{suffix:02d}"
        if candidate not in used:
            return candidate
    raise MedicalAssertionError(f"no unused {prefix}- id remains below the two-digit ceiling")


def _world_consequence_psych(history: AssertionWorldProjection, condition_id: str | None) -> bool:
    """Whether *condition_id* names a world condition classified
    ``compensable_consequence`` — the R49 eligibility anchor for both psych
    mischaracterization draws."""
    if condition_id is None:
        return False
    condition = history.condition(condition_id)
    return condition is not None and condition.psych_injury_kind == "compensable_consequence"


def _remodel_sampled_ptp(
    seed: CaseSeed,
    ledger: MedicalAssertionLedger,
    history: AssertionWorldProjection,
    opinion: MedicalOpinion,
    opinion_key: StorySemanticKey,
    contention_keys: dict[str, StorySemanticKey],
) -> MedicalOpinion:
    """R49/R16 — the PTP independence remodel for one sampled base opinion.

    The AOE/COE finding is an independent draw; no eligible sampled PTP
    opinion retains ``aoe_coe_finding=None``. For dispositions, the unchanged
    M2 ``ptp-disposition`` stream's affirmative result becomes independent
    concurrence — agreement in result, never responsive endorsement — except
    that a deferred AOE/COE finding places a directly affected causation
    contention (``claim_type="industrial_causation"``) in
    ``defers_contention_ids`` instead. A negative M2 result remains what it
    was, and no sampled PTP result enters ``endorses_contention_ids``. The
    sampled psych classification then fires for the first addressed
    consequence-classified psychiatric contention (R49; the deterministic
    QME/AME triad re-derivation is step-8 surface material).
    """
    finding = _ptp_aoe_coe_finding(seed, opinion_key)
    concurs: list[str] = []
    defers: list[str] = []
    for ref in opinion.endorses_contention_ids:
        contention = ledger.contention(ref)
        if (
            finding == "deferred"
            and contention is not None
            and contention.claim_type == "industrial_causation"
        ):
            defers.append(ref)
        else:
            concurs.append(ref)
    psych_kind = opinion.psych_injury_kind
    for ref in (*concurs, *defers):
        if psych_kind is not None:
            break
        contention = ledger.contention(ref)
        if contention is not None and _world_consequence_psych(
            history, contention.target_condition_id
        ):
            psych_kind = _ptp_psych_classification(seed, opinion_key, contention_keys[ref])
    return opinion.model_copy(
        update={
            "aoe_coe_finding": finding,
            "endorses_contention_ids": (),
            "concurs_with_contention_ids": tuple(concurs),
            "defers_contention_ids": tuple(defers),
            "psych_injury_kind": psych_kind,
        }
    )


def _remodel_sampled_qme_ame(
    seed: CaseSeed,
    context: AssertionValidationContext,
    ledger: MedicalAssertionLedger,
    history: AssertionWorldProjection,
    opinion: MedicalOpinion,
    opinion_key: StorySemanticKey,
    contention_keys: dict[str, StorySemanticKey],
    qualifying_communications: dict[str, tuple[StorySemanticKey, ...]],
) -> MedicalOpinion:
    """R38/R49/R53 — the complete five-state classification for one sampled
    QME/AME base opinion.

    Classification from sufficient evidence is deterministic: every
    evidence-supported pair is adopted or concurred (adoption only through an
    earlier qualifying communication plus the 0.25 channel), and every
    contradicted pair stays in the preserved M2 rejects tuple. Only the
    indeterminate stream draws, choosing deferred versus unaddressed; it can
    produce neither adoption nor concurrence. An ID in no collection is
    unaddressed (R26).
    """
    rejected = frozenset(opinion.rejects_contention_ids)
    adopted: list[str] = []
    concurred: list[str] = []
    deferred: list[str] = []
    # One semantic identity, one decision: two contentions may legally share
    # a full C key (distinct explicit twins never do — their explicit keys
    # carry their own IDs — but two sampled candidates can shape onto one
    # rule-6 tuple). The pair stream is constructed once per identity and the
    # result applies to every contention carrying it.
    decided: dict[str, str] = {}
    for contention in ledger.contentions:
        if contention.id in rejected:
            continue
        contention_key = contention_keys[contention.id]
        identity = canonical_story_key(contention_key)
        evidence = contention_evidence(history, context, contention)
        if evidence == "supports":
            if identity not in decided:
                decided[identity] = _qme_ame_supported_disposition(
                    seed,
                    opinion_key,
                    contention_key,
                    qualifying_communications.get(contention.id, ()),
                )
            if decided[identity] == "adopted":
                adopted.append(contention.id)
            else:
                concurred.append(contention.id)
        elif evidence == "contradicts":
            # The M2 rejection policy already rejected every contradicted
            # pair; the preserved rejects tuple carries them (R38).
            continue
        else:
            if identity not in decided:
                decided[identity] = _qme_ame_indeterminate_disposition(
                    seed, opinion_key, contention_key
                )
            if decided[identity] == "deferred":
                deferred.append(contention.id)
    return opinion.model_copy(
        update={
            "endorses_contention_ids": tuple(adopted),
            "concurs_with_contention_ids": tuple(concurred),
            "defers_contention_ids": tuple(deferred),
        }
    )


def _apply_story_semantics(
    seed: CaseSeed,
    scenario: object,
    context: AssertionValidationContext,
    history: AssertionWorldProjection,
    graded: MedicalAssertionLedger,
    *,
    qualifying_communications: dict[str, tuple[StorySemanticKey, ...]] | None = None,
) -> MedicalAssertionLedger:
    """R77 step 4 — the M3 base-disposition remodel over the graded M2 ledger.

    A pure post-pass: it runs strictly AFTER the exact M2 base derivation and
    its baseline snapshot, touches only SAMPLED entities (authored explicit
    disposition collections and classifications remain authoritative, R49),
    reads no ``quality`` (R32), and draws only from the private
    ``medical-story:`` streams keyed by R45 pre-ID semantics. With sampling
    disabled there is nothing sampled to remodel and no stream is
    constructed.

    ``qualifying_communications`` maps a contention ID to the sorted R45 ``D``
    keys of the earlier qualifying R38 communications that target the sampled
    evaluator opinion and speak that contention — empty until R77 step 5
    plans sampled advocacy, so at step 4 every evidence-supported sampled
    QME/AME pair concurs without an adoption draw (R53).
    """
    if not getattr(scenario, "sample_assertions", True):
        return graded
    explicit_contention_ids = frozenset(
        entry.id
        for entry in scenario.contentions  # type: ignore[attr-defined]
    )
    explicit_opinion_ids = frozenset(
        entry.id
        for entry in scenario.medical_opinions  # type: ignore[attr-defined]
    )
    communications = dict(qualifying_communications or {})
    contention_keys = {
        contention.id: _story_contention_key(seed, contention, explicit_contention_ids)
        for contention in graded.contentions
    }

    # R49 applicant framing — a sampled applicant contention concerning a
    # consequence-classified world psych condition, with no explicit
    # classification, is characterized by one draw keyed (C,). One draw per
    # semantic identity: sampled candidates sharing one rule-6 key share the
    # framing decision.
    framed: dict[str, str] = {}
    contentions: list[Contention] = []
    for contention in graded.contentions:
        if (
            contention.id not in explicit_contention_ids
            and contention.party == "applicant"
            and contention.psych_injury_kind is None
            and _world_consequence_psych(history, contention.target_condition_id)
        ):
            identity = canonical_story_key(contention_keys[contention.id])
            if identity not in framed:
                framed[identity] = _applicant_psych_framing(seed, contention_keys[contention.id])
            contention = contention.model_copy(update={"psych_injury_kind": framed[identity]})
        contentions.append(contention)

    remodeled = MedicalAssertionLedger(
        contentions=tuple(contentions),
        medical_opinions=graded.medical_opinions,
        apportionment_assertions=graded.apportionment_assertions,
    )

    opinions: list[MedicalOpinion] = []
    for opinion in remodeled.medical_opinions:
        if opinion.id in explicit_opinion_ids or opinion.event_kind != "base_report":
            # Authored explicit disposition collections remain authoritative
            # (R49); sampled response events own their step-5 semantics.
            opinions.append(opinion)
            continue
        opinion_key = _story_sampled_base_opinion_key(seed, opinion)
        if opinion.author_role == "ptp":
            opinions.append(
                _remodel_sampled_ptp(
                    seed, remodeled, history, opinion, opinion_key, contention_keys
                )
            )
        else:
            opinions.append(
                _remodel_sampled_qme_ame(
                    seed,
                    context,
                    remodeled,
                    history,
                    opinion,
                    opinion_key,
                    contention_keys,
                    communications,
                )
            )

    return MedicalAssertionLedger(
        contentions=remodeled.contentions,
        medical_opinions=tuple(opinions),
        apportionment_assertions=remodeled.apportionment_assertions,
    )


# ---------------------------------------------------------------------------
# R77 step 5 — contention-loop topology, decision table, contest paths, caps
# ---------------------------------------------------------------------------

MAX_CONTENTION_CHAINS_PER_CASE: Final[int] = 3
MAX_BOUND_CONTENTION_DOCUMENTS_PER_CASE: Final[int] = 15
MAX_CONTENTIONS_PER_LOOP_DOCUMENT: Final[int] = 3
MAX_ADVOCACY_LETTERS_PER_CASE: Final[int] = 3
MAX_OBJECTIONS_PER_CASE: Final[int] = 2
MAX_SUPPLEMENTAL_REQUESTS_PER_CASE: Final[int] = 2
MAX_SUPPLEMENTAL_REPORTS_PER_CASE: Final[int] = 2
MAX_QME_AME_DEPOSITIONS_PER_CASE: Final[int] = 1
"""R31's exact per-case and per-chain caps. A contention chain is keyed by
``(actor_party, target_medical_opinion_id, path)``; bundled contentions do not
consume additional chain slots. The 15-document cap counts every BOUND opinion
report, advocacy letter, objection, supplemental request, supplemental report
and QME/AME deposition — never unbound legacy candidates or copies forced only
by ordinary ``documents:`` controls. Explicit cap violations FAIL; sampled
infeasibility truncates from the tail without redraw. The three-contention cap
governs loop communications (advocacy bundles and contest chunks); a base
report realization speaks its full disposition union per R35."""

ROLE_COURT_REPORTER: Final[str] = "court_reporter"
"""R35 — a deposition transcript's base document author. The examining party
remains separately available through ``contention_actor_party``."""

#: R29's complete disposition x party decision table:
#: (contention party, disposition) -> (eligible actor, disposition class).
#: A "determined_adverse" row proceeds through an objection-led path; a
#: "completion" row has no conclusion to object to and begins with a
#: supplemental request. The table is total: every cell names its one actor.
_R29_DECISION_TABLE: Final[dict[tuple[str, str], tuple[str, str]]] = {
    ("applicant", "adopted"): ("defense", "determined_adverse"),
    ("applicant", "concurred"): ("defense", "determined_adverse"),
    ("applicant", "rejected"): ("applicant", "determined_adverse"),
    ("applicant", "deferred"): ("applicant", "completion"),
    ("applicant", "unaddressed"): ("applicant", "completion"),
    ("defense", "adopted"): ("applicant", "determined_adverse"),
    ("defense", "concurred"): ("applicant", "determined_adverse"),
    ("defense", "rejected"): ("defense", "determined_adverse"),
    ("defense", "deferred"): ("defense", "completion"),
    ("defense", "unaddressed"): ("defense", "completion"),
}

#: The stage sequence each ContestPath proposes (R29's permitted chains).
_PATH_STAGES: Final[dict[str, tuple[str, ...]]] = {
    "objection_only": ("objection",),
    "objection_supplemental": (
        "objection",
        "supplemental_request",
        "supplemental_report",
    ),
    "objection_deposition": ("objection", "qme_deposition"),
    "objection_supplemental_deposition": (
        "objection",
        "supplemental_request",
        "supplemental_report",
        "qme_deposition",
    ),
    "supplemental_only": ("supplemental_request", "supplemental_report"),
    "supplemental_deposition": (
        "supplemental_request",
        "supplemental_report",
        "qme_deposition",
    ),
}

#: The four objection-led (determined-adverse) ContestPath literals; the two
#: completion paths begin at the supplemental request.
_ADVERSE_CONTEST_PATHS: Final[frozenset[str]] = frozenset(
    {
        "objection_only",
        "objection_supplemental",
        "objection_deposition",
        "objection_supplemental_deposition",
    }
)

#: R2/R35 exact carrier bindings for the loop communications.
_LOOP_LETTER_CARRIER: Final[str] = "ADVOCACY_LETTERS_PTP_QME_AME"
_OBJECTION_TEMPLATE_SUBTYPE: Final[str] = "OBJECTION_TO_QME_AME_REPORT"
_REQUEST_TEMPLATE_SUBTYPE: Final[str] = "REQUEST_SUPPLEMENTAL_QME_AME_REPORT"
_DEPOSITION_TEMPLATE_SUBTYPE: Final[str] = "DEPOSITION_TRANSCRIPT_QME_AME"
_DEPOSITION_CARRIER: Final[str] = "DEPOSITION_TRANSCRIPT"
_SUPPLEMENTAL_DEFAULT_CARRIER: Final[str] = "SUPPLEMENTAL_QME_AME_REPORT"

#: R28 sampled advocacy carriers by target role; the combined carrier is
#: available to explicit entries but is never the sampled default.
_ADVOCACY_SAMPLED_CARRIERS: Final[dict[str, str]] = {
    "ptp": "ADVOCACY_LETTERS_PTP",
    "qme": "ADVOCACY_LETTERS_QME",
    "ame": "ADVOCACY_LETTERS_AME",
}

#: R27 default canonical carriers for base opinion realizations, by
#: (author_role, report_stage). The psych carrier overrides for a QME/AME
#: opinion carrying a bound psych finding.
_DEFAULT_BASE_CARRIERS: Final[dict[tuple[str, str], str]] = {
    ("ptp", "interim"): "TREATING_PHYSICIAN_REPORT_PR2",
    ("ptp", "final"): "TREATING_PHYSICIAN_REPORT_PR4",
    ("qme", "interim"): "QME_REPORT_INITIAL",
    ("qme", "final"): "QME_COMPREHENSIVE_REPORT",
    ("ame", "interim"): "AME_REPORT",
    ("ame", "final"): "AME_COMPREHENSIVE_REPORT",
}
_PSYCH_BASE_CARRIER: Final[str] = "PSYCH_EVAL_REPORT_QME_AME"

#: Substrate-only registry keys an explicit ``subtype`` may never state (R40);
#: R2 supplies them internally as ``template_subtype``.
_SUBSTRATE_ONLY_LOOP_KEYS: Final[frozenset[str]] = frozenset(
    {
        _OBJECTION_TEMPLATE_SUBTYPE,
        _REQUEST_TEMPLATE_SUBTYPE,
        _DEPOSITION_TEMPLATE_SUBTYPE,
    }
)


def _loop_surfaces():  # pragma: no cover - trivial import indirection
    """The R8 governed surface sets, imported lazily.

    ``medical_story`` imports this module at top level, so the R27/R40 carrier
    compatibility checks reach R8's frozen sets through a deferred import —
    the same pattern ``_condition_targets`` uses for the clinical catalog.
    """
    from wc_caseload_engine import medical_story as story_module

    return story_module


def _compatible_realization_carriers(opinion: MedicalOpinion) -> frozenset[str]:
    """The R27 carrier compatibility set for one opinion event."""
    surfaces = _loop_surfaces()
    if opinion.event_kind == "deposition":
        return frozenset({_DEPOSITION_CARRIER})
    if opinion.event_kind == "supplemental_report":
        return frozenset(surfaces.SUPPLEMENTAL_MEDLEGAL_SURFACES)
    if opinion.author_role == "ptp":
        return frozenset(surfaces.PTP_CAUSATION_SURFACES)
    return frozenset(surfaces.INITIAL_MEDLEGAL_SURFACES | surfaces.PSYCH_MEDLEGAL_SURFACES)


def _default_realization_carrier(opinion: MedicalOpinion) -> str:
    """R27's default carrier selection for one opinion event."""
    if opinion.event_kind == "deposition":
        return _DEPOSITION_CARRIER
    if opinion.event_kind == "supplemental_report":
        return _SUPPLEMENTAL_DEFAULT_CARRIER
    if opinion.author_role in ("qme", "ame") and opinion.psych_injury_kind is not None:
        return _PSYCH_BASE_CARRIER
    return _DEFAULT_BASE_CARRIERS[(opinion.author_role, opinion.report_stage)]


def _realization_document_kind(opinion: MedicalOpinion) -> str:
    return {
        "base_report": "opinion_report",
        "supplemental_report": "supplemental_report",
        "deposition": "qme_deposition",
    }[opinion.event_kind]


def _story_opinion_key(
    seed: CaseSeed,
    opinion: MedicalOpinion,
    explicit_opinion_ids: frozenset[str],
) -> StorySemanticKey:
    """The R45 ``O`` identity for one ledger opinion (explicit or sampled base).

    Sampled response opinions never route through here — their
    ``sampled_response`` keys are composed at draft time from the predecessor
    key and the revisited ``C`` keys, before any ID exists.
    """
    if opinion.id in explicit_opinion_ids:
        return ("case", seed.case_id, "opinion", "explicit", opinion.id)
    return _story_sampled_base_opinion_key(seed, opinion)


def _classification_of(opinion_view: _OpinionView, contention_id: str) -> str:
    if contention_id in opinion_view.endorses:
        return "adopted"
    if contention_id in opinion_view.concurs:
        return "concurred"
    if contention_id in opinion_view.rejects:
        return "rejected"
    if contention_id in opinion_view.defers:
        return "deferred"
    return "unaddressed"


def _concerns_apportionment_or_psych(
    contention: Contention,
    ledger: MedicalAssertionLedger,
    history: AssertionWorldProjection,
) -> bool:
    """R30's "concerning apportionment or psych" predicate, all six arms.

    The "addressed by a relevant ApportionmentAssertion" arm reads a row that
    links the contention directly or cites the contention's own target entity
    — the implemented reading of "relevant", flagged for the spec author.
    """
    if contention.claim_type in ("apportionment_defense", "psych_add_on"):
        return True
    if contention.requested_apportionment is not None:
        return True
    if contention.psych_injury_kind is not None:
        return True
    if contention.target_body_part == "psyche":
        return True
    if contention.target_condition_id is not None:
        condition = history.condition(contention.target_condition_id)
        if condition is not None and condition.body_system == "psychiatric":
            return True
    for row in ledger.apportionment_assertions:
        if row.linked_contention_id == contention.id:
            return True
        if (
            contention.target_condition_id is not None
            and contention.target_condition_id in row.condition_ids
        ):
            return True
        if (
            contention.target_prior_claim_id is not None
            and contention.target_prior_claim_id in row.prior_claim_ids
        ):
            return True
        if (
            contention.target_prior_award_id is not None
            and contention.target_prior_award_id in row.prior_award_ids
        ):
            return True
    return False


@dataclass(frozen=True, slots=True)
class _OpinionView:
    """One predecessor's semantic surface — ledger opinion or sampled draft.

    The response builder reads predecessors through this one shape so a
    deposition examining a sampled supplemental (whose opinion has no final ID
    yet) uses exactly the machinery a ledger predecessor uses.
    """

    ref: str
    author_role: str
    report_stage: str
    report_date: dt.date
    apportionment_state: str
    determination_kind: str | None
    determination_rationale: str | None
    reviewed_condition_ids: tuple[str, ...]
    reviewed_prior_claim_ids: tuple[str, ...]
    reviewed_prior_award_ids: tuple[str, ...]
    endorses: frozenset[str]
    concurs: frozenset[str]
    rejects: frozenset[str]
    defers: frozenset[str]
    psych_injury_kind: str | None
    aoe_coe_finding: str | None
    aoe_coe_rationale: str | None
    rows: tuple[ApportionmentAssertion, ...]
    event_kind: str
    key: StorySemanticKey
    explicit: bool


def _view_of_ledger_opinion(
    opinion: MedicalOpinion,
    ledger: MedicalAssertionLedger,
    key: StorySemanticKey,
    *,
    explicit: bool,
) -> _OpinionView:
    return _OpinionView(
        ref=opinion.id,
        author_role=opinion.author_role,
        report_stage=opinion.report_stage,
        report_date=opinion.report_date,
        apportionment_state=opinion.apportionment_state,
        determination_kind=opinion.determination_kind,
        determination_rationale=opinion.determination_rationale,
        reviewed_condition_ids=opinion.reviewed_condition_ids,
        reviewed_prior_claim_ids=opinion.reviewed_prior_claim_ids,
        reviewed_prior_award_ids=opinion.reviewed_prior_award_ids,
        endorses=frozenset(opinion.endorses_contention_ids),
        concurs=frozenset(opinion.concurs_with_contention_ids),
        rejects=frozenset(opinion.rejects_contention_ids),
        defers=frozenset(opinion.defers_contention_ids),
        psych_injury_kind=opinion.psych_injury_kind,
        aoe_coe_finding=opinion.aoe_coe_finding,
        aoe_coe_rationale=opinion.aoe_coe_rationale,
        rows=ledger.assertions_of(opinion.id),
        event_kind=opinion.event_kind,
        key=key,
        explicit=explicit,
    )


@dataclass(slots=True)
class _ResponseDraft:
    """One sampled response opinion, complete except for its final ID."""

    placeholder: str
    opinion: MedicalOpinion
    rows: list[ApportionmentAssertion]
    key: StorySemanticKey
    responds_to_ref: str
    supersedes_ref: str | None

    def view(self) -> _OpinionView:
        return _OpinionView(
            ref=self.placeholder,
            author_role=self.opinion.author_role,
            report_stage=self.opinion.report_stage,
            report_date=self.opinion.report_date,
            apportionment_state=self.opinion.apportionment_state,
            determination_kind=self.opinion.determination_kind,
            determination_rationale=self.opinion.determination_rationale,
            reviewed_condition_ids=self.opinion.reviewed_condition_ids,
            reviewed_prior_claim_ids=self.opinion.reviewed_prior_claim_ids,
            reviewed_prior_award_ids=self.opinion.reviewed_prior_award_ids,
            endorses=frozenset(self.opinion.endorses_contention_ids),
            concurs=frozenset(self.opinion.concurs_with_contention_ids),
            rejects=frozenset(self.opinion.rejects_contention_ids),
            defers=frozenset(self.opinion.defers_contention_ids),
            psych_injury_kind=self.opinion.psych_injury_kind,
            aoe_coe_finding=self.opinion.aoe_coe_finding,
            aoe_coe_rationale=self.opinion.aoe_coe_rationale,
            rows=tuple(self.rows),
            event_kind=self.opinion.event_kind,
            key=self.key,
            explicit=False,
        )


@dataclass(slots=True)
class _BindingDraft:
    """One contention-document decision before the final ID pass."""

    document_kind: str
    subtype: str | None
    template_subtype: str | None
    proposed_date: dt.date | None
    doc_date: dt.date | None
    medical_opinion_ref: str | None
    target_ref: str | None
    spoken: tuple[str, ...]
    actor_party: str | None
    theories: tuple[str, ...]
    source: str
    explicit_id: str | None = None
    d_key: StorySemanticKey | None = None


@dataclass(slots=True)
class _AdvocacyLetter:
    """One sampled standalone advocacy letter (R28/R52)."""

    actor: str
    target_ref: str
    target_key: StorySemanticKey
    target_role: str
    target_report_date: dt.date
    contention_refs: tuple[str, ...]
    d_key: StorySemanticKey
    subtype: str


@dataclass(slots=True)
class _AdvocacyPlan:
    letters: list[_AdvocacyLetter] = field(default_factory=list)
    qualifying_communications: dict[str, tuple[StorySemanticKey, ...]] = field(default_factory=dict)


def _advocacy_d_key(
    seed: CaseSeed,
    actor: str,
    target_key: StorySemanticKey,
    spoken_c_keys: tuple[StorySemanticKey, ...],
) -> StorySemanticKey:
    return (
        "case",
        seed.case_id,
        "contention_document",
        "advocacy",
        actor,
        None,
        target_key,
        tuple(sorted(spoken_c_keys, key=canonical_story_key)),
    )


def _contest_d_key(
    seed: CaseSeed,
    document_kind: str,
    actor: str | None,
    current_key: StorySemanticKey | None,
    target_key: StorySemanticKey | None,
    spoken_c_keys: tuple[StorySemanticKey, ...],
) -> StorySemanticKey:
    return (
        "case",
        seed.case_id,
        "contention_document",
        document_kind,
        actor,
        current_key,
        target_key,
        tuple(sorted(spoken_c_keys, key=canonical_story_key)),
    )


def _derive_advocacy(
    seed: CaseSeed,
    scenario: object,
    context: AssertionValidationContext,
    ledger: MedicalAssertionLedger,
    contention_keys: dict[str, StorySemanticKey],
    explicit_opinion_ids: frozenset[str],
) -> _AdvocacyPlan:
    """R28/R52 — sampled standalone advocacy, derived before dispositions.

    One ``advocacy-incidence`` draw per R28-eligible contention/target pair;
    provisional winners stable-sorted by contention semantic key; one
    ``advocacy-bundle-size`` draw per provisional bundle (a single winner
    forms a size-one letter without a draw); explicitly reserved contention
    IDs removed from the formed bundles WITHOUT redraw or repacking; empty
    bundles suppressed without replacement. Eligibility never inspects
    evidence disposition or quality (R52), and a sampled PTP letter is
    applicant-authored (R28).

    The qualifying-communication map covers exactly the letters that target
    the sampled QME/AME evaluator opinion — R38's advocacy channel; explicit
    letters can only reference explicit opinions and explicit opinions keep
    their authored dispositions, so neither enters the map.
    """
    plan = _AdvocacyPlan()
    if not getattr(scenario, "sample_contention_documents", True):
        return plan
    reserved: dict[tuple[str, str], set[str]] = {}
    for entry in getattr(scenario, "contention_documents", []):
        if entry.document_kind != "advocacy":
            continue
        reserved.setdefault((entry.actor_party, entry.target_medical_opinion_id), set()).update(
            entry.spoken_contention_ids
        )

    minimum_window_start = context.date_of_injury + dt.timedelta(days=1)
    for opinion in ledger.medical_opinions:
        if opinion.event_kind != "base_report":
            continue
        role = opinion.author_role
        target_key = _story_opinion_key(seed, opinion, explicit_opinion_ids)
        for actor in ("applicant", "defense"):
            rate = ADVOCACY_INCIDENCE.value.get((role, actor))
            if rate is None:
                continue
            # A letter must be able to strictly precede its target within the
            # case window (injury + 1 day .. horizon): a strictly earlier day
            # must exist at or after the window start.
            if opinion.report_date <= minimum_window_start:
                continue
            winners: list[Contention] = []
            for contention in ledger.contentions:
                if contention.party != actor:
                    continue
                incidence = _medical_story_rng(
                    seed,
                    "advocacy-incidence",
                    (
                        "case",
                        seed.case_id,
                        target_key,
                        contention_keys[contention.id],
                        actor,
                    ),
                )
                if _fraction_draw(incidence, rate):
                    winners.append(contention)
            winners.sort(key=lambda c: canonical_story_key(contention_keys[c.id]))
            remaining = list(winners)
            bundles: list[list[Contention]] = []
            while remaining:
                if len(remaining) == 1:
                    bundles.append([remaining.pop(0)])
                    continue
                sizes = tuple(
                    (size, weight)
                    for size, weight in ADVOCACY_BUNDLE_SIZE_WEIGHTS.value
                    if size <= len(remaining)
                )
                total = sum(weight for _size, weight in sizes)
                chooser = _medical_story_rng(
                    seed,
                    "advocacy-bundle-size",
                    (
                        "case",
                        seed.case_id,
                        target_key,
                        actor,
                        contention_keys[remaining[0].id],
                        tuple(contention_keys[c.id] for c in remaining),
                    ),
                )
                index = _weighted_index(chooser, tuple(weight / total for _size, weight in sizes))
                size = sizes[index][0]
                bundles.append(remaining[:size])
                remaining = remaining[size:]
            reserved_ids = reserved.get((actor, opinion.id), set())
            for bundle in bundles:
                kept = [c for c in bundle if c.id not in reserved_ids]
                if not kept:
                    continue
                spoken_keys = tuple(contention_keys[c.id] for c in kept)
                letter = _AdvocacyLetter(
                    actor=actor,
                    target_ref=opinion.id,
                    target_key=target_key,
                    target_role=role,
                    target_report_date=opinion.report_date,
                    contention_refs=tuple(c.id for c in kept),
                    d_key=_advocacy_d_key(seed, actor, target_key, spoken_keys),
                    subtype=_ADVOCACY_SAMPLED_CARRIERS[role],
                )
                plan.letters.append(letter)
                if role in ("qme", "ame") and opinion.id not in explicit_opinion_ids:
                    for contention in kept:
                        existing = plan.qualifying_communications.get(contention.id, ())
                        plan.qualifying_communications[contention.id] = tuple(
                            sorted(
                                (*existing, letter.d_key),
                                key=canonical_story_key,
                            )
                        )
    return plan


@dataclass(slots=True)
class _ChainChunk:
    """One bundled chunk of one sampled contest chain."""

    actor: str
    target: MedicalOpinion
    target_key: StorySemanticKey
    target_explicit: bool
    path: str
    disposition_class: str
    contentions: tuple[Contention, ...]
    theories: tuple[str, ...] = ()


def _derive_contest_chunks(
    seed: CaseSeed,
    scenario: object,
    context: AssertionValidationContext,
    history: AssertionWorldProjection,
    ledger: MedicalAssertionLedger,
    contention_keys: dict[str, StorySemanticKey],
    explicit_opinion_ids: frozenset[str],
) -> list[_ChainChunk]:
    """R29/R30/R50/R51 — opportunities, incidence, paths, chunks, theories.

    Opportunities enumerate QME/AME base reports plus EXPLICIT supplemental
    reports only: a sampled supplemental never becomes the source of another
    sampled chain (R29 non-recursion), and a deposition is terminal. Each
    ``(actor, opinion, contention)`` opportunity draws once from its own
    incidence family; a fired opportunity draws its path once; contentions
    sharing ``(actor, target, path)`` are bundled deterministically — sorted
    by contention semantic key, chunked at three, membership retained through
    every stage. A sampled defense chain draws its theory count and its
    weighted-without-replacement theory selection from two chain-keyed
    streams and copies the ordered tuple to every attorney-authored document.
    """
    chunks: list[_ChainChunk] = []
    if not getattr(scenario, "sample_contention_documents", True):
        return chunks
    fired: dict[tuple[str, str, str], list[Contention]] = {}
    targets: dict[str, tuple[MedicalOpinion, StorySemanticKey, bool]] = {}
    for opinion in ledger.medical_opinions:
        if opinion.author_role == "ptp":
            continue
        explicit = opinion.id in explicit_opinion_ids
        if opinion.event_kind == "deposition":
            continue
        if opinion.event_kind == "supplemental_report" and not explicit:
            continue
        opinion_key = _story_opinion_key(seed, opinion, explicit_opinion_ids)
        view = _view_of_ledger_opinion(opinion, ledger, opinion_key, explicit=explicit)
        for contention in ledger.contentions:
            disposition = _classification_of(view, contention.id)
            actor, disposition_class = _R29_DECISION_TABLE[(contention.party, disposition)]
            if actor == "defense":
                if not _concerns_apportionment_or_psych(contention, ledger, history):
                    continue  # outside R30: zero probability, no stream
                family = "defense-contest-incidence"
                rate = P_DEFENSE_CONTEST.value
            elif disposition_class == "determined_adverse":
                family = "applicant-contest-incidence"
                rate = P_APPLICANT_CONTEST.value
            else:
                family = "completion-incidence"
                rate = P_APPLICANT_COMPLETION_REQUEST.value
            x_key: StorySemanticKey = (
                "case",
                seed.case_id,
                "opportunity",
                actor,
                disposition_class,
                opinion_key,
                contention_keys[contention.id],
            )
            incidence = _medical_story_rng(seed, family, ("case", seed.case_id, x_key))
            if not _fraction_draw(incidence, rate):
                continue
            weights_table = (
                ADVERSE_CONTEST_PATH_WEIGHTS.value[actor]
                if disposition_class == "determined_adverse"
                else COMPLETION_PATH_WEIGHTS.value[actor]
            )
            chooser = _medical_story_rng(seed, "contest-path", ("case", seed.case_id, x_key))
            index = _weighted_index(chooser, tuple(weight for _path, weight in weights_table))
            path = weights_table[index][0]
            fired.setdefault((actor, opinion.id, path), []).append(contention)
            targets[opinion.id] = (opinion, opinion_key, explicit)

    def chain_sort_key(item: tuple[str, str, str]) -> tuple[str, str, str]:
        actor, target_ref, path = item
        _opinion, target_key, _explicit = targets[target_ref]
        return (actor, canonical_story_key(target_key), path)

    for actor, target_ref, path in sorted(fired, key=chain_sort_key):
        opinion, target_key, explicit = targets[target_ref]
        members = sorted(
            fired[(actor, target_ref, path)],
            key=lambda c: canonical_story_key(contention_keys[c.id]),
        )
        for start in range(0, len(members), MAX_CONTENTIONS_PER_LOOP_DOCUMENT):
            chunk_members = tuple(members[start : start + MAX_CONTENTIONS_PER_LOOP_DOCUMENT])
            chunk = _ChainChunk(
                actor=actor,
                target=opinion,
                target_key=target_key,
                target_explicit=explicit,
                path=path,
                disposition_class=(
                    "determined_adverse" if path in _ADVERSE_CONTEST_PATHS else "completion"
                ),
                contentions=chunk_members,
            )
            if actor == "defense":
                first_kind = (
                    "objection"
                    if chunk.disposition_class == "determined_adverse"
                    else "supplemental_request"
                )
                spoken_keys = tuple(contention_keys[c.id] for c in chunk.contentions)
                chain_d_key = _contest_d_key(seed, first_kind, actor, None, target_key, spoken_keys)
                counts = DEFENSE_THEORY_COUNT_WEIGHTS.value
                count_rng = _medical_story_rng(
                    seed,
                    "defense-theory-count",
                    ("case", seed.case_id, chain_d_key),
                )
                count = counts[_weighted_index(count_rng, tuple(weight for _n, weight in counts))][
                    0
                ]
                selection_rng = _medical_story_rng(
                    seed,
                    "defense-theory-selection",
                    ("case", seed.case_id, chain_d_key),
                )
                pool = list(DEFENSE_THEORY_WEIGHTS.value)
                selected: list[str] = []
                for _ in range(count):
                    total = sum(weight for _theory, weight in pool)
                    index = _weighted_index(
                        selection_rng,
                        tuple(weight / total for _theory, weight in pool),
                    )
                    selected.append(pool[index][0])
                    pool.pop(index)
                chunk.theories = tuple(selected)
            chunks.append(chunk)
    return chunks


def _predecessor_row_key(view: _OpinionView, row: ApportionmentAssertion) -> StorySemanticKey:
    """The R55 predecessor-assertion identity for one changed row."""
    if view.explicit:
        return ("apportionment", "explicit", row.id)
    if view.event_kind == "base_report":
        return ("apportionment", "sampled", view.author_role, row.body_part)
    return ("apportionment", "sampled_response", view.key, row.body_part)


def _new_record_candidate(
    history: AssertionWorldProjection, view: _OpinionView
) -> tuple[str, str] | None:
    """R54's deterministic newly-acknowledged record, or ``None``.

    Selected by record family, source date, and stable ledger ID from the
    visible world entities the predecessor never reviewed, respecting R37's
    reviewed-ID caps (8/5/5, combined 12). No stream is consumed.
    """
    reviewed = (
        {("condition", ref) for ref in view.reviewed_condition_ids}
        | {("prior_claim", ref) for ref in view.reviewed_prior_claim_ids}
        | {("prior_award", ref) for ref in view.reviewed_prior_award_ids}
    )
    combined = len(reviewed)
    if combined >= REVIEWED_IDS_COMBINED_CAP:
        return None
    candidates: list[tuple[str, str, str]] = []
    for condition in history.conditions:
        if condition.surfaces_in_file and len(view.reviewed_condition_ids) < 8:
            onset = condition.onset.isoformat() if condition.onset else ""
            candidates.append(("condition", onset, condition.id))
    for claim in history.prior_claims:
        if len(view.reviewed_prior_claim_ids) < 5:
            candidates.append(("prior_claim", claim.date_of_injury.isoformat(), claim.id))
    for award in history.awards:
        if len(view.reviewed_prior_award_ids) < 5:
            candidates.append(("prior_award", award.award_date.isoformat(), award.id))
    for family, _date, ref in sorted(candidates):
        if (family, ref) not in reviewed:
            return (family, ref)
    return None


_RESPONSE_RATIONALES: Final[dict[str, str]] = {
    "unchanged_additional_reasoning": (
        "the prior conclusions stand; additional reasoning addresses the questions presented"
    ),
    "new_records_no_change": (
        "the newly received records were reviewed and do not change the stated conclusions"
    ),
    "revised_causation": ("the revised conclusions rest on further review of the record"),
    "revised_apportionment": (
        "the revised percentages rest on further review of the documented pathology"
    ),
    "revised_causation_and_apportionment": (
        "the revised conclusions and percentages rest on further review of the record"
    ),
}

_RESPONSE_REVISION_RATIONALES: Final[dict[str, str]] = {
    "revised_causation": ("the causation analysis is revised on further review of the record"),
    "revised_apportionment": ("the apportionment percentages are revised on further review"),
    "revised_causation_and_apportionment": (
        "the causation and apportionment conclusions are revised on further review"
    ),
}

_REVISED_AOE_RATIONALE: Final[str] = (
    "on further consideration the causal analysis is restated with revised reasoning"
)


def _draft_response_opinion(
    seed: CaseSeed,
    context: AssertionValidationContext,
    history: AssertionWorldProjection,
    chunk: _ChainChunk,
    predecessor: _OpinionView,
    contention_keys: dict[str, StorySemanticKey],
    *,
    event_kind: str,
    trigger_class: str,
    report_date: dt.date,
    request_d_key: StorySemanticKey | None,
    placeholder: str,
) -> _ResponseDraft:
    """R37/R38/R53/R54/R55 — one sampled supplemental or deposition opinion.

    Adoption draws come first (one per eligible revisited pair — R53's
    structural denominator; the qualifying communication is the bound
    supplemental request), then the trigger-conditioned compatible revision
    kind (a prospective disposition change restricts the pool to
    causation-capable kinds), then the content that realizes exactly that
    kind's R37 predicate: no-change kinds restate the predecessor's complete
    semantic surface; causation kinds apply the drawn classifications (an
    indeterminate revisited pair re-draws deferred-versus-unaddressed) and
    fall back to a revised causation rationale when the applied results
    happen to equal the predecessor's; apportionment kinds change exactly one
    allocated row through the R55 register/value streams with the
    predecessor's percentage excluded. A deposition revision is a new
    ``MedicalOpinion(event_kind="deposition")``, never an in-place mutation.
    """
    revisited_keys = tuple(
        sorted(
            (contention_keys[c.id] for c in chunk.contentions),
            key=canonical_story_key,
        )
    )
    response_key: StorySemanticKey = (
        "case",
        seed.case_id,
        "opinion",
        "sampled_response",
        event_kind,
        predecessor.author_role,
        predecessor.key,
        revisited_keys,
    )

    prospective: dict[str, str | None] = {}
    for contention in chunk.contentions:
        evidence = contention_evidence(history, context, contention)
        if evidence == "supports":
            if event_kind == "supplemental_report" and request_d_key is not None:
                prospective[contention.id] = _qme_ame_supported_disposition(
                    seed,
                    response_key,
                    contention_keys[contention.id],
                    (request_d_key,),
                )
            else:
                prospective[contention.id] = "concurred"
        elif evidence == "contradicts":
            prospective[contention.id] = "rejected"
        else:
            prospective[contention.id] = None  # indeterminate: kind-gated draw

    prospective_changed = any(
        result is not None and result != _classification_of(predecessor, contention_id)
        for contention_id, result in prospective.items()
    )
    record_candidate = _new_record_candidate(history, predecessor)
    can_change_apportionment = predecessor.determination_kind == "allocated" and bool(
        predecessor.rows
    )
    kind = _draw_revision_kind(
        seed,
        response_key,
        predecessor.key,
        trigger_class,
        can_acknowledge_new_records=record_candidate is not None,
        can_change_apportionment=can_change_apportionment,
        can_change_causation=True,
        adoption_changed_disposition=prospective_changed,
    )

    endorses = set(predecessor.endorses)
    concurs = set(predecessor.concurs)
    rejects = set(predecessor.rejects)
    defers = set(predecessor.defers)
    aoe_coe_rationale = predecessor.aoe_coe_rationale
    causation_capable = kind in _CAUSATION_CAPABLE_REVISION_KINDS
    if causation_capable:
        for contention in chunk.contentions:
            result = prospective[contention.id]
            if result is None:
                result = _qme_ame_indeterminate_disposition(
                    seed, response_key, contention_keys[contention.id]
                )
            for collection in (endorses, concurs, rejects, defers):
                collection.discard(contention.id)
            if result == "adopted":
                endorses.add(contention.id)
            elif result == "concurred":
                concurs.add(contention.id)
            elif result == "rejected":
                rejects.add(contention.id)
            elif result == "deferred":
                defers.add(contention.id)
        unchanged_sets = (
            endorses == predecessor.endorses
            and concurs == predecessor.concurs
            and rejects == predecessor.rejects
            and defers == predecessor.defers
        )
        if unchanged_sets:
            revised = _REVISED_AOE_RATIONALE
            if revised == predecessor.aoe_coe_rationale:
                revised = f"{revised} (supplemental restatement)"
            aoe_coe_rationale = revised

    reviewed_conditions = list(predecessor.reviewed_condition_ids)
    reviewed_claims = list(predecessor.reviewed_prior_claim_ids)
    reviewed_awards = list(predecessor.reviewed_prior_award_ids)
    if kind == "new_records_no_change" and record_candidate is not None:
        family, ref = record_candidate
        {
            "condition": reviewed_conditions,
            "prior_claim": reviewed_claims,
            "prior_award": reviewed_awards,
        }[family].append(ref)

    rows: list[ApportionmentAssertion] = []
    if predecessor.determination_kind == "allocated":
        ordered_rows = sorted(predecessor.rows, key=lambda row: row.body_part)
        change_rows = kind in (
            "revised_apportionment",
            "revised_causation_and_apportionment",
        )
        for index, row in enumerate(ordered_rows):
            if change_rows and index == 0:
                new_percent = _draw_revision_percentage(
                    seed,
                    response_key,
                    row.body_part,
                    _predecessor_row_key(predecessor, row),
                    predecessor_nonindustrial=row.nonindustrial_percent,
                    require_change=True,
                )
                rows.append(
                    row.model_copy(
                        update={
                            "id": "app-99",
                            "opinion_id": "opn-99",
                            "industrial_percent": 100 - new_percent,
                            "nonindustrial_percent": new_percent,
                            "revised_from_percent": row.nonindustrial_percent,
                            "revision_rationale": (
                                "the revised share follows the supplemental analysis of the record"
                            ),
                        }
                    )
                )
            else:
                rows.append(
                    row.model_copy(
                        update={
                            "id": "app-99",
                            "opinion_id": "opn-99",
                            "revised_from_percent": None,
                            "revision_rationale": None,
                        }
                    )
                )

    revising = kind in (
        "revised_causation",
        "revised_apportionment",
        "revised_causation_and_apportionment",
    )
    supersedes_ref = predecessor.ref if revising else None
    opinion = MedicalOpinion(
        id="opn-99",  # labelled in the final subphased pass
        author_role=predecessor.author_role,  # type: ignore[arg-type]
        report_stage=predecessor.report_stage,  # type: ignore[arg-type]
        report_date=report_date,
        apportionment_state=predecessor.apportionment_state,  # type: ignore[arg-type]
        determination_kind=predecessor.determination_kind,  # type: ignore[arg-type]
        determination_rationale=predecessor.determination_rationale,
        examination_performed=False,
        reviewed_condition_ids=tuple(reviewed_conditions),
        reviewed_prior_claim_ids=tuple(reviewed_claims),
        reviewed_prior_award_ids=tuple(reviewed_awards),
        endorses_contention_ids=tuple(ref for ref in _ordered_refs(endorses, predecessor, chunk)),
        concurs_with_contention_ids=tuple(
            ref for ref in _ordered_refs(concurs, predecessor, chunk)
        ),
        rejects_contention_ids=tuple(ref for ref in _ordered_refs(rejects, predecessor, chunk)),
        defers_contention_ids=tuple(ref for ref in _ordered_refs(defers, predecessor, chunk)),
        responds_to_opinion_id="opn-98",  # placeholder; resolved at labeling
        supersedes_opinion_id="opn-98" if supersedes_ref is not None else None,
        rationale=_RESPONSE_RATIONALES[kind],
        revision_rationale=_RESPONSE_REVISION_RATIONALES.get(kind),
        event_kind=event_kind,  # type: ignore[arg-type]
        revision_kind=kind,  # type: ignore[arg-type]
        psych_injury_kind=predecessor.psych_injury_kind,  # type: ignore[arg-type]
        aoe_coe_finding=predecessor.aoe_coe_finding,  # type: ignore[arg-type]
        aoe_coe_rationale=aoe_coe_rationale,
        quality="supported",
    )
    return _ResponseDraft(
        placeholder=placeholder,
        opinion=opinion,
        rows=rows,
        key=response_key,
        responds_to_ref=predecessor.ref,
        supersedes_ref=supersedes_ref,
    )


def _ordered_refs(selected: set[str], predecessor: _OpinionView, chunk: _ChainChunk) -> list[str]:
    """Deterministic collection order for a response's disposition tuples.

    Predecessor-classified IDs first (sorted — a frozenset carries no order),
    then the revisited chunk members in their chunk order; each ID once.
    """
    ordered: list[str] = []
    seen: set[str] = set()
    predecessor_ids = (
        predecessor.endorses | predecessor.concurs | predecessor.rejects | predecessor.defers
    )
    for ref in (*sorted(predecessor_ids), *(c.id for c in chunk.contentions)):
        if ref in selected and ref not in seen:
            ordered.append(ref)
            seen.add(ref)
    return ordered


def _explicit_chain_signature(
    kinds: frozenset[str],
) -> str:
    """The chain-cap grouping label for one explicit attorney-document set.

    Maps the present contest kinds onto the ContestPath literal they spell;
    an explicit shape outside the six sampled literals (a lone deposition)
    keys under its own deterministic label — explicit authoring is free-form,
    and the label only groups documents for the R31 chain cap.
    """
    has_objection = "objection" in kinds
    has_supplemental = "supplemental_request" in kinds
    has_deposition = "qme_deposition" in kinds
    mapping = {
        (True, False, False): "objection_only",
        (True, True, False): "objection_supplemental",
        (True, False, True): "objection_deposition",
        (True, True, True): "objection_supplemental_deposition",
        (False, True, False): "supplemental_only",
        (False, True, True): "supplemental_deposition",
        (False, False, True): "deposition_only",
    }
    return mapping[(has_objection, has_supplemental, has_deposition)]


def _r41_collision_key(entry: object) -> tuple[object, ...]:
    """R41's exact collision identity for one explicit document entry."""
    return (
        entry.document_kind,  # type: ignore[attr-defined]
        entry.actor_party,  # type: ignore[attr-defined]
        entry.medical_opinion_id,  # type: ignore[attr-defined]
        entry.target_medical_opinion_id,  # type: ignore[attr-defined]
        tuple(sorted(entry.spoken_contention_ids)),  # type: ignore[attr-defined]
    )


def _explicit_contention_document_problems(scenario: object) -> list[str]:
    """R40's per-kind validation of every explicit contention document.

    Everything here fails BEFORE sampling (R41: explicit IDs and references
    resolve first) and fails rather than truncates (R31): kind/field matrix
    compatibility with the referenced opinion events, carrier compatibility
    under R27/R8, the substrate-only-key prohibition, exact date equality and
    strict ordering for authored dates, actor/party agreement for advocacy,
    duplicate semantic documents under the R41 collision key, and the
    explicit per-kind, chain, and opinion caps.
    """
    entries = list(getattr(scenario, "contention_documents", []))
    opinions = {entry.id: entry for entry in getattr(scenario, "medical_opinions", [])}
    contentions = {entry.id: entry for entry in getattr(scenario, "contentions", [])}
    problems: list[str] = []
    seen_collisions: dict[tuple[object, ...], str] = {}
    surfaces = _loop_surfaces() if entries else None

    for entry in entries:
        prefix = f"contention document '{entry.id}' ({entry.document_kind})"
        current = (
            opinions.get(entry.medical_opinion_id) if entry.medical_opinion_id is not None else None
        )
        target = (
            opinions.get(entry.target_medical_opinion_id)
            if entry.target_medical_opinion_id is not None
            else None
        )
        collision = _r41_collision_key(entry)
        if collision in seen_collisions:
            problems.append(
                f"{prefix} duplicates the semantic document "
                f"'{seen_collisions[collision]}'; duplicate semantic "
                "documents are forbidden"
            )
        else:
            seen_collisions[collision] = entry.id
        if entry.subtype is not None and entry.subtype in _SUBSTRATE_ONLY_LOOP_KEYS:
            problems.append(
                f"{prefix} states substrate-only key '{entry.subtype}' as its "
                "subtype; R2 supplies the internal template_subtype"
            )
            continue
        if entry.document_kind == "opinion_report" and current is not None:
            if current.event_kind != "base_report":
                problems.append(
                    f"{prefix} names medical opinion '{current.id}' whose "
                    f"event_kind is '{current.event_kind}'; an opinion_report "
                    "realizes a base_report"
                )
            if entry.doc_date is not None and entry.doc_date != current.report_date:
                problems.append(
                    f"{prefix} states doc_date {entry.doc_date.isoformat()} "
                    f"but opinion '{current.id}' reports on "
                    f"{current.report_date.isoformat()}; an opinion report's "
                    "date equals its opinion date"
                )
            if entry.subtype is not None and surfaces is not None:
                compatible = (
                    frozenset(surfaces.PTP_CAUSATION_SURFACES)
                    if current.author_role == "ptp"
                    else frozenset(
                        surfaces.INITIAL_MEDLEGAL_SURFACES | surfaces.PSYCH_MEDLEGAL_SURFACES
                    )
                )
                if entry.subtype not in compatible:
                    problems.append(
                        f"{prefix} selects carrier '{entry.subtype}', which is "
                        f"not a compatible R8 carrier for a "
                        f"{current.author_role} base report"
                    )
        if entry.document_kind == "advocacy":
            if target is not None and target.event_kind != "base_report":
                problems.append(
                    f"{prefix} targets opinion '{target.id}' whose event_kind "
                    f"is '{target.event_kind}'; standalone advocacy precedes a "
                    "base report only (R28)"
                )
            for ref in entry.spoken_contention_ids:
                spoken = contentions.get(ref)
                if spoken is not None and spoken.party != entry.actor_party:
                    problems.append(
                        f"{prefix} is authored by '{entry.actor_party}' but "
                        f"speaks contention '{ref}' advanced by "
                        f"'{spoken.party}'; the letter actor equals the party "
                        "advancing the spoken contentions (R28)"
                    )
            if (
                entry.doc_date is not None
                and target is not None
                and entry.doc_date >= target.report_date
            ):
                problems.append(
                    f"{prefix} states doc_date {entry.doc_date.isoformat()} "
                    f"but its target opinion '{target.id}' reports on "
                    f"{target.report_date.isoformat()}; a letter strictly "
                    "precedes its target report (R34)"
                )
            if entry.subtype is not None and surfaces is not None:
                if entry.subtype not in surfaces.ADVOCACY_LETTER_SURFACES:
                    problems.append(
                        f"{prefix} selects carrier '{entry.subtype}', which is "
                        "not an R8 advocacy carrier"
                    )
                elif (
                    target is not None
                    and entry.subtype != _LOOP_LETTER_CARRIER
                    and entry.subtype != _ADVOCACY_SAMPLED_CARRIERS[target.author_role]
                ):
                    problems.append(
                        f"{prefix} selects role carrier '{entry.subtype}' for "
                        f"a {target.author_role}-authored target; use the "
                        "matching role carrier or the combined carrier"
                    )
        if entry.document_kind in ("objection", "supplemental_request"):
            if target is not None and target.author_role == "ptp":
                problems.append(
                    f"{prefix} targets PTP opinion '{target.id}'; PTP reports "
                    "never generate an M3 objection, supplemental request, or "
                    "QME/AME deposition (R29)"
                )
            if target is not None and target.event_kind == "deposition":
                problems.append(
                    f"{prefix} targets deposition opinion '{target.id}'; a "
                    "deposition is terminal (R29)"
                )
            if (
                entry.doc_date is not None
                and target is not None
                and entry.doc_date <= target.report_date
            ):
                problems.append(
                    f"{prefix} states doc_date {entry.doc_date.isoformat()} "
                    f"on or before target opinion '{target.id}''s "
                    f"{target.report_date.isoformat()}; the contest strictly "
                    "follows the report it challenges (R34)"
                )
            if entry.subtype is not None and entry.subtype != _LOOP_LETTER_CARRIER:
                problems.append(
                    f"{prefix} selects carrier '{entry.subtype}'; the "
                    "objection/request canonical carrier is "
                    f"'{_LOOP_LETTER_CARRIER}' (R35)"
                )
        if entry.document_kind == "supplemental_report" and current is not None:
            if current.event_kind != "supplemental_report":
                problems.append(
                    f"{prefix} names medical opinion '{current.id}' whose "
                    f"event_kind is '{current.event_kind}'; a supplemental "
                    "report realizes a supplemental opinion"
                )
            elif entry.target_medical_opinion_id != current.responds_to_opinion_id:
                problems.append(
                    f"{prefix} targets "
                    f"'{entry.target_medical_opinion_id}' but opinion "
                    f"'{current.id}' responds to "
                    f"'{current.responds_to_opinion_id}'; the target is the "
                    "immediate predecessor (R40)"
                )
            if entry.doc_date is not None and entry.doc_date != current.report_date:
                problems.append(
                    f"{prefix} states doc_date {entry.doc_date.isoformat()} "
                    f"but opinion '{current.id}' reports on "
                    f"{current.report_date.isoformat()}; the date equals the "
                    "opinion date"
                )
            if (
                entry.subtype is not None
                and surfaces is not None
                and entry.subtype not in surfaces.SUPPLEMENTAL_MEDLEGAL_SURFACES
            ):
                problems.append(
                    f"{prefix} selects carrier '{entry.subtype}', which is "
                    "not an R8 supplemental carrier"
                )
        if entry.document_kind == "qme_deposition" and current is not None:
            if current.event_kind != "deposition":
                problems.append(
                    f"{prefix} names medical opinion '{current.id}' whose "
                    f"event_kind is '{current.event_kind}'; a QME/AME "
                    "deposition realizes a deposition opinion"
                )
            elif entry.target_medical_opinion_id != current.responds_to_opinion_id:
                problems.append(
                    f"{prefix} targets "
                    f"'{entry.target_medical_opinion_id}' but deposition "
                    f"opinion '{current.id}' examines "
                    f"'{current.responds_to_opinion_id}'; the target is the "
                    "examined report (R40)"
                )
            if entry.doc_date is not None and entry.doc_date != current.report_date:
                problems.append(
                    f"{prefix} states doc_date {entry.doc_date.isoformat()} "
                    f"but deposition opinion '{current.id}' is taken on "
                    f"{current.report_date.isoformat()}; the date equals the "
                    "opinion date"
                )
            if entry.subtype is not None and entry.subtype != _DEPOSITION_CARRIER:
                problems.append(
                    f"{prefix} selects carrier '{entry.subtype}'; a deposition "
                    f"binds exactly '{_DEPOSITION_CARRIER}' (R27)"
                )

    # Explicit caps fail rather than truncate (R31). Per-kind document counts
    # include the required realizations the explicit opinions themselves
    # force; opinion-bound entries replace realizations and never add.
    kind_counts = Counter(entry.document_kind for entry in entries)
    supplemental_opinions = sum(
        1 for o in opinions.values() if o.event_kind == "supplemental_report"
    )
    deposition_opinions = sum(1 for o in opinions.values() if o.event_kind == "deposition")
    explicit_kind_totals = {
        "advocacy": kind_counts["advocacy"],
        "objection": kind_counts["objection"],
        "supplemental_request": kind_counts["supplemental_request"],
        "supplemental_report": supplemental_opinions,
        "qme_deposition": deposition_opinions,
    }
    for kind, cap in (
        ("advocacy", MAX_ADVOCACY_LETTERS_PER_CASE),
        ("objection", MAX_OBJECTIONS_PER_CASE),
        ("supplemental_request", MAX_SUPPLEMENTAL_REQUESTS_PER_CASE),
        ("supplemental_report", MAX_SUPPLEMENTAL_REPORTS_PER_CASE),
        ("qme_deposition", MAX_QME_AME_DEPOSITIONS_PER_CASE),
    ):
        if explicit_kind_totals[kind] > cap:
            problems.append(
                f"explicit contention documents state "
                f"{explicit_kind_totals[kind]} {kind} documents; the per-case "
                f"cap is {cap} and explicit cap violations fail rather than "
                "truncate (R31)"
            )
    bound_total = (
        len(opinions)
        + kind_counts["advocacy"]
        + kind_counts["objection"]
        + kind_counts["supplemental_request"]
    )
    if bound_total > MAX_BOUND_CONTENTION_DOCUMENTS_PER_CASE:
        problems.append(
            f"explicit opinions and contention documents bind {bound_total} "
            "documents; the per-case bound-document cap is "
            f"{MAX_BOUND_CONTENTION_DOCUMENTS_PER_CASE} (R31)"
        )
    explicit_chains: dict[tuple[str | None, str | None], set[str]] = {}
    for entry in entries:
        if entry.document_kind in ("objection", "supplemental_request", "qme_deposition"):
            explicit_chains.setdefault(
                (entry.actor_party, entry.target_medical_opinion_id), set()
            ).add(entry.document_kind)
    if len(explicit_chains) > MAX_CONTENTION_CHAINS_PER_CASE:
        problems.append(
            f"explicit contention documents form {len(explicit_chains)} "
            "contest chains; the per-case chain cap is "
            f"{MAX_CONTENTION_CHAINS_PER_CASE} (R31)"
        )
    return problems


def _band_offset(
    seed: CaseSeed,
    family: str,
    key: StorySemanticKey,
    band: tuple[int, int],
    trace: AssertionTrace | None,
) -> int:
    """One inclusive R56 raw offset: exactly one ``randint(lower, upper)``."""
    rng = _medical_story_rng(seed, family, key)
    offset = rng.randint(band[0], band[1])
    if trace is not None:
        trace.story_raw_date_offsets.append((family, offset))
    return offset


@dataclass(slots=True)
class _StageRecord:
    stage: str
    binding: _BindingDraft | None
    response: _ResponseDraft | None


def _derive_contention_loop(
    seed: CaseSeed,
    scenario: object,
    context: AssertionValidationContext,
    history: AssertionWorldProjection,
    ledger: MedicalAssertionLedger,
    advocacy: _AdvocacyPlan,
    contention_keys: dict[str, StorySemanticKey],
    explicit_opinion_ids: frozenset[str],
    trace: AssertionTrace | None,
) -> tuple[MedicalAssertionLedger, tuple[ContentionDocumentBinding, ...]]:
    """R77 step 5 — compose the bound contention-document set, IDs last.

    R31 composition order is exact: (1) required realizations for explicit
    opinions — replaced in place by an explicit opinion-bound document entry;
    (2) explicit contention documents, which consume every cap first and FAIL
    on violation; (3) required realizations for sampled base opinions; (4)
    sampled advocacy letters, then sampled responsive chains in stable
    chain-key order, truncating from the tail without redraw wherever a cap,
    the eight-opinion allowance, or the anchor ceiling on a response
    opinion's proposed date makes a stage infeasible. The final subphased
    labeling pass then assigns response ``opn-``/``app-`` suffixes after all
    base entries and ``cdoc-`` suffixes after the explicit ones, and resolves
    every draft reference — no stochastic decision follows it (R32/R47).
    """
    entries = list(getattr(scenario, "contention_documents", []))
    entry_by_opinion = {
        entry.medical_opinion_id: entry for entry in entries if entry.medical_opinion_id is not None
    }
    counters: Counter[str] = Counter()
    caps = {
        "advocacy": MAX_ADVOCACY_LETTERS_PER_CASE,
        "objection": MAX_OBJECTIONS_PER_CASE,
        "supplemental_request": MAX_SUPPLEMENTAL_REQUESTS_PER_CASE,
        "supplemental_report": MAX_SUPPLEMENTAL_REPORTS_PER_CASE,
        "qme_deposition": MAX_QME_AME_DEPOSITIONS_PER_CASE,
    }
    drafts: list[_BindingDraft] = []
    chain_keys: set[tuple[str, str, str]] = set()

    def fits(kind: str) -> bool:
        if counters["total"] >= MAX_BOUND_CONTENTION_DOCUMENTS_PER_CASE:
            return False
        cap = caps.get(kind)
        return cap is None or counters[kind] < cap

    def commit(draft: _BindingDraft, *, explicit: bool) -> None:
        if not fits(draft.document_kind):
            if explicit:
                raise MedicalAssertionError(
                    f"explicit contention document "
                    f"'{draft.explicit_id or draft.document_kind}' exceeds a "
                    "frozen R31 cap once required opinion realizations are "
                    "composed; explicit cap violations fail rather than "
                    "truncate"
                )
            raise MedicalAssertionError(  # pragma: no cover - guarded by callers
                "sampled contention document composed past a cap; sampled "
                "callers must check caps before committing"
            )
        counters[draft.document_kind] += 1
        counters["total"] += 1
        drafts.append(draft)

    def entry_binding(entry: object) -> _BindingDraft:
        kind = entry.document_kind  # type: ignore[attr-defined]
        subtype = entry.subtype  # type: ignore[attr-defined]
        template: str | None = None
        current_ref = entry.medical_opinion_id  # type: ignore[attr-defined]
        current = ledger.opinion(current_ref) if current_ref is not None else None
        if kind == "opinion_report" and current is not None:
            subtype = subtype or _default_realization_carrier(current)
        elif kind == "advocacy":
            target = ledger.opinion(entry.target_medical_opinion_id)  # type: ignore[attr-defined]
            if subtype is None:
                subtype = (
                    _ADVOCACY_SAMPLED_CARRIERS[target.author_role]
                    if target is not None
                    else _LOOP_LETTER_CARRIER
                )
            template = subtype
        elif kind == "objection":
            subtype = subtype or _LOOP_LETTER_CARRIER
            template = _OBJECTION_TEMPLATE_SUBTYPE
        elif kind == "supplemental_request":
            subtype = subtype or _LOOP_LETTER_CARRIER
            template = _REQUEST_TEMPLATE_SUBTYPE
        elif kind == "supplemental_report":
            subtype = subtype or _SUPPLEMENTAL_DEFAULT_CARRIER
            template = subtype
        elif kind == "qme_deposition":
            subtype = subtype or _DEPOSITION_CARRIER
            template = _DEPOSITION_TEMPLATE_SUBTYPE
        doc_date = entry.doc_date  # type: ignore[attr-defined]
        if doc_date is None and current is not None:
            doc_date = current.report_date
        target_ref = entry.target_medical_opinion_id  # type: ignore[attr-defined]
        target = ledger.opinion(target_ref) if target_ref is not None else None
        current_key = (
            _story_opinion_key(seed, current, explicit_opinion_ids) if current is not None else None
        )
        target_key = (
            _story_opinion_key(seed, target, explicit_opinion_ids) if target is not None else None
        )
        spoken = tuple(entry.spoken_contention_ids)  # type: ignore[attr-defined]
        return _BindingDraft(
            document_kind=kind,
            subtype=subtype,
            template_subtype=template,
            proposed_date=doc_date,
            doc_date=entry.doc_date,  # type: ignore[attr-defined]
            medical_opinion_ref=current_ref,
            target_ref=target_ref,
            spoken=spoken,
            actor_party=entry.actor_party,  # type: ignore[attr-defined]
            theories=tuple(entry.defense_contest_theories),  # type: ignore[attr-defined]
            source="explicit",
            explicit_id=entry.id,  # type: ignore[attr-defined]
            d_key=_contest_d_key(
                seed,
                kind,
                entry.actor_party,  # type: ignore[attr-defined]
                current_key,
                target_key,
                tuple(contention_keys[ref] for ref in spoken),
            ),
        )

    def realization_binding(opinion: MedicalOpinion) -> _BindingDraft:
        spoken = _ordered_disposition_union(opinion, ledger)
        kind = _realization_document_kind(opinion)
        subtype = _default_realization_carrier(opinion)
        template = None
        if kind == "supplemental_report":
            template = subtype
        elif kind == "qme_deposition":
            template = _DEPOSITION_TEMPLATE_SUBTYPE
        current_key = _story_opinion_key(seed, opinion, explicit_opinion_ids)
        target = (
            ledger.opinion(opinion.responds_to_opinion_id)
            if opinion.responds_to_opinion_id is not None
            else None
        )
        target_key = (
            _story_opinion_key(seed, target, explicit_opinion_ids) if target is not None else None
        )
        return _BindingDraft(
            document_kind=kind,
            subtype=subtype,
            template_subtype=template,
            proposed_date=opinion.report_date,
            doc_date=None,
            medical_opinion_ref=opinion.id,
            target_ref=opinion.responds_to_opinion_id if kind != "opinion_report" else None,
            spoken=spoken,
            actor_party=None,
            theories=(),
            source="required_opinion",
            d_key=_contest_d_key(
                seed,
                kind,
                None,
                current_key,
                target_key,
                tuple(contention_keys[ref] for ref in spoken),
            ),
        )

    # Groups 1-2 — explicit opinions' realizations (replaced in place by an
    # explicit opinion-bound entry), then the remaining explicit documents.
    for opinion in ledger.medical_opinions:
        if opinion.id not in explicit_opinion_ids:
            continue
        entry = entry_by_opinion.get(opinion.id)
        if entry is not None:
            commit(entry_binding(entry), explicit=True)
        else:
            commit(realization_binding(opinion), explicit=True)
    for entry in entries:
        if entry.medical_opinion_id is not None:
            continue
        commit(entry_binding(entry), explicit=True)

    # Explicit chains occupy chain slots by (actor, target, derived shape),
    # so a sampled chain sharing that identity does not open a new slot.
    explicit_chain_members: dict[tuple[str, str], set[str]] = {}
    for entry in entries:
        if entry.document_kind in ("objection", "supplemental_request", "qme_deposition"):
            explicit_chain_members.setdefault(
                (entry.actor_party, entry.target_medical_opinion_id), set()
            ).add(entry.document_kind)
    for (actor, target_ref), kinds in explicit_chain_members.items():
        chain_keys.add((actor, target_ref, _explicit_chain_signature(frozenset(kinds))))

    # Group 3 — required realizations for sampled base opinions.
    for opinion in ledger.medical_opinions:
        if opinion.id in explicit_opinion_ids:
            continue
        if not fits(_realization_document_kind(opinion)):
            raise MedicalAssertionError(
                f"required realization for sampled opinion '{opinion.id}' "
                "cannot fit inside the frozen R31 caps beside the explicit "
                "documents; reduce the explicit document set or disable "
                "sampling"
            )
        commit(realization_binding(opinion), explicit=False)

    # Group 4 — sampled advocacy letters, then sampled responsive chains.
    response_drafts: list[_ResponseDraft] = []
    if getattr(scenario, "sample_contention_documents", True):
        for letter in advocacy.letters:
            if not fits("advocacy"):
                continue  # suppressed at the semantic cap, never redrawn
            lead = _band_offset(
                seed,
                "advocacy-lead",
                ("case", seed.case_id, letter.d_key, letter.target_key),
                ADVOCACY_LEAD_DAYS.value,
                trace,
            )
            commit(
                _BindingDraft(
                    document_kind="advocacy",
                    subtype=letter.subtype,
                    template_subtype=letter.subtype,
                    proposed_date=letter.target_report_date - dt.timedelta(days=lead),
                    doc_date=None,
                    medical_opinion_ref=None,
                    target_ref=letter.target_ref,
                    spoken=letter.contention_refs,
                    actor_party=letter.actor,
                    theories=(),
                    source="sampled",
                    d_key=letter.d_key,
                ),
                explicit=False,
            )

        reserved: dict[tuple[str, str, str], set[str]] = {}
        for entry in entries:
            if entry.document_kind in (
                "objection",
                "supplemental_request",
                "qme_deposition",
            ):
                reserved.setdefault(
                    (
                        entry.document_kind,
                        entry.actor_party,
                        entry.target_medical_opinion_id,
                    ),
                    set(),
                ).update(entry.spoken_contention_ids)
        explicit_request_dates = {
            (
                entry.actor_party,
                entry.target_medical_opinion_id,
                entry.document_kind,
            ): entry.doc_date
            for entry in entries
            if entry.document_kind in ("objection", "supplemental_request")
        }

        chunks = _derive_contest_chunks(
            seed,
            scenario,
            context,
            history,
            ledger,
            contention_keys,
            explicit_opinion_ids,
        )
        opinion_total = len(ledger.medical_opinions)
        for chunk in chunks:
            chain_key = (chunk.actor, chunk.target.id, chunk.path)
            new_chain = chain_key not in chain_keys
            if new_chain and len(chain_keys) >= MAX_CONTENTION_CHAINS_PER_CASE:
                continue  # the whole sampled chain is suppressed
            records, opinion_total = _build_chain_stages(
                seed,
                context,
                history,
                chunk,
                ledger,
                contention_keys,
                counters,
                caps,
                reserved,
                explicit_request_dates,
                opinion_total,
                len(response_drafts),
                trace,
            )
            if not records:
                continue
            for record in records:
                if record.binding is not None:
                    commit(record.binding, explicit=False)
                if record.response is not None:
                    response_drafts.append(record.response)
            if new_chain:
                chain_keys.add(chain_key)

    # --- the final subphased labeling pass (R32/R47 subphases 4-5) ---------
    if not drafts and not response_drafts:
        return ledger, ()
    used_opinion_ids = {o.id for o in ledger.medical_opinions}
    reference_map: dict[str, str] = {o.id: o.id for o in ledger.medical_opinions}
    for draft in response_drafts:
        assigned = _first_unused("opn", used_opinion_ids)
        used_opinion_ids.add(assigned)
        reference_map[draft.placeholder] = assigned
    used_row_ids = {a.id for a in ledger.apportionment_assertions}
    labelled_opinions: list[MedicalOpinion] = []
    labelled_rows: list[ApportionmentAssertion] = []
    for draft in response_drafts:
        assigned = reference_map[draft.placeholder]
        labelled_opinions.append(
            draft.opinion.model_copy(
                update={
                    "id": assigned,
                    "responds_to_opinion_id": reference_map[draft.responds_to_ref],
                    "supersedes_opinion_id": (
                        reference_map[draft.supersedes_ref]
                        if draft.supersedes_ref is not None
                        else None
                    ),
                }
            )
        )
        for row in draft.rows:
            row_id = _first_unused("app", used_row_ids)
            used_row_ids.add(row_id)
            labelled_rows.append(row.model_copy(update={"id": row_id, "opinion_id": assigned}))
    final_ledger = (
        ledger
        if not labelled_opinions
        else MedicalAssertionLedger(
            contentions=ledger.contentions,
            medical_opinions=(*ledger.medical_opinions, *labelled_opinions),
            apportionment_assertions=(
                *ledger.apportionment_assertions,
                *labelled_rows,
            ),
        )
    )
    used_cdoc_ids = {draft.explicit_id for draft in drafts if draft.explicit_id is not None}
    bindings: list[ContentionDocumentBinding] = []
    for draft in drafts:
        if draft.explicit_id is not None:
            binding_id = draft.explicit_id
        else:
            binding_id = _first_unused("cdoc", used_cdoc_ids)
            used_cdoc_ids.add(binding_id)
        if draft.d_key is None:  # pragma: no cover - every constructor owns D
            raise MedicalAssertionError(
                "contention-document binding reached final labeling without its R45 semantic D key"
            )
        bindings.append(
            ContentionDocumentBinding(
                id=binding_id,
                document_kind=draft.document_kind,  # type: ignore[arg-type]
                subtype=draft.subtype,
                doc_date=draft.doc_date,
                medical_opinion_id=(
                    reference_map.get(draft.medical_opinion_ref, draft.medical_opinion_ref)
                    if draft.medical_opinion_ref is not None
                    else None
                ),
                target_medical_opinion_id=(
                    reference_map.get(draft.target_ref, draft.target_ref)
                    if draft.target_ref is not None
                    else None
                ),
                spoken_contention_ids=draft.spoken,
                actor_party=draft.actor_party,  # type: ignore[arg-type]
                defense_contest_theories=draft.theories,  # type: ignore[arg-type]
                template_subtype=draft.template_subtype,
                proposed_date=draft.proposed_date,
                source=draft.source,  # type: ignore[arg-type]
                semantic_key=draft.d_key,
            )
        )
    return final_ledger, tuple(bindings)


def _ordered_disposition_union(
    opinion: MedicalOpinion, ledger: MedicalAssertionLedger
) -> tuple[str, ...]:
    """R35 — a report realization speaks its disposition union in ledger order."""
    classified = (
        set(opinion.endorses_contention_ids)
        | set(opinion.concurs_with_contention_ids)
        | set(opinion.rejects_contention_ids)
        | set(opinion.defers_contention_ids)
    )
    return tuple(c.id for c in ledger.contentions if c.id in classified)


def _build_chain_stages(
    seed: CaseSeed,
    context: AssertionValidationContext,
    history: AssertionWorldProjection,
    chunk: _ChainChunk,
    ledger: MedicalAssertionLedger,
    contention_keys: dict[str, StorySemanticKey],
    counters: Counter,
    caps: dict[str, int],
    reserved: dict[tuple[str, str, str], set[str]],
    explicit_request_dates: dict[tuple[str, str, str], dt.date | None],
    opinion_total: int,
    response_index: int,
    trace: AssertionTrace | None,
) -> tuple[list[_StageRecord], int]:
    """One chunk's stage walk: caps, raw dates, drafts, tail truncation.

    The R31 collapse law is exact and re-draw-free: a failing deposition
    drops alone; a failing supplemental report (or request) takes the request
    with it — ``R`` never survives sampled truncation without its ``S`` — so
    an adverse chain collapses ``O→R→S→D → O→R→S → O`` and a completion chain
    collapses ``R→S→D → R→S`` and then to nothing. Draws already made for a
    truncated stage stay burned. Explicit reservation (R41) removes only the
    reserved contention IDs from a stage's spoken set, without redraw and
    without repacking; a fully reserved stage document is suppressed as the
    explicit document's semantic duplicate while the chain continues around
    the authored paper.
    """
    stages = _PATH_STAGES[chunk.path]
    tentative: Counter[str] = Counter()
    records: list[_StageRecord] = []
    spoken_keys = tuple(contention_keys[c.id] for c in chunk.contentions)
    target_view = _view_of_ledger_opinion(
        chunk.target,
        ledger,
        chunk.target_key,
        explicit=chunk.target_explicit,
    )

    def stage_fits(kind: str) -> bool:
        if counters["total"] + tentative["total"] >= MAX_BOUND_CONTENTION_DOCUMENTS_PER_CASE:
            return False
        cap = caps.get(kind)
        return cap is None or counters[kind] + tentative[kind] < cap

    def stage_spoken(kind: str) -> tuple[str, ...]:
        reserved_ids = reserved.get((kind, chunk.actor, chunk.target.id), set())
        return tuple(c.id for c in chunk.contentions if c.id not in reserved_ids)

    objection_binding: _BindingDraft | None = None
    request_binding: _BindingDraft | None = None
    request_d_key: StorySemanticKey | None = None
    supplemental_draft: _ResponseDraft | None = None
    failed_stage: str | None = None
    drafted = 0

    for stage in stages:
        if stage == "objection":
            spoken = stage_spoken("objection")
            if not spoken:
                continue  # the explicit objection already carries this event
            if not stage_fits("objection"):
                failed_stage = "objection"
                break
            d_key = _contest_d_key(
                seed,
                "objection",
                chunk.actor,
                None,
                chunk.target_key,
                tuple(contention_keys[ref] for ref in spoken),
            )
            offset = _band_offset(
                seed,
                "objection-lag",
                ("case", seed.case_id, d_key, chunk.target_key),
                OBJECTION_LAG_DAYS.value,
                trace,
            )
            objection_binding = _BindingDraft(
                document_kind="objection",
                subtype=_LOOP_LETTER_CARRIER,
                template_subtype=_OBJECTION_TEMPLATE_SUBTYPE,
                proposed_date=chunk.target.report_date + dt.timedelta(days=offset),
                doc_date=None,
                medical_opinion_ref=None,
                target_ref=chunk.target.id,
                spoken=spoken,
                actor_party=chunk.actor,
                theories=chunk.theories,
                source="sampled",
                d_key=d_key,
            )
            tentative["objection"] += 1
            tentative["total"] += 1
            records.append(_StageRecord("objection", objection_binding, None))
        elif stage == "supplemental_request":
            spoken = stage_spoken("supplemental_request")
            request_base_key: StorySemanticKey
            if objection_binding is not None:
                request_base_key = objection_binding.d_key  # type: ignore[assignment]
                request_base_date = objection_binding.proposed_date
            elif chunk.path in _ADVERSE_CONTEST_PATHS:
                # The sampled objection was suppressed as an explicit
                # duplicate: the request follows the authored objection.
                request_base_key = chunk.target_key
                request_base_date = (
                    explicit_request_dates.get((chunk.actor, chunk.target.id, "objection"))
                    or chunk.target.report_date
                )
            else:
                request_base_key = chunk.target_key
                request_base_date = chunk.target.report_date
            if not spoken:
                request_d_key = _contest_d_key(
                    seed,
                    "supplemental_request",
                    chunk.actor,
                    None,
                    chunk.target_key,
                    spoken_keys,
                )
                continue
            if not stage_fits("supplemental_request"):
                failed_stage = "supplemental_request"
                break
            d_key = _contest_d_key(
                seed,
                "supplemental_request",
                chunk.actor,
                None,
                chunk.target_key,
                tuple(contention_keys[ref] for ref in spoken),
            )
            offset = _band_offset(
                seed,
                "supplemental-request-lag",
                ("case", seed.case_id, d_key, request_base_key),
                SUPPLEMENTAL_REQUEST_LAG_DAYS.value,
                trace,
            )
            assert request_base_date is not None
            request_binding = _BindingDraft(
                document_kind="supplemental_request",
                subtype=_LOOP_LETTER_CARRIER,
                template_subtype=_REQUEST_TEMPLATE_SUBTYPE,
                proposed_date=request_base_date + dt.timedelta(days=offset),
                doc_date=None,
                medical_opinion_ref=None,
                target_ref=chunk.target.id,
                spoken=spoken,
                actor_party=chunk.actor,
                theories=chunk.theories,
                source="sampled",
                d_key=d_key,
            )
            request_d_key = d_key
            tentative["supplemental_request"] += 1
            tentative["total"] += 1
            records.append(_StageRecord("supplemental_request", request_binding, None))
        elif stage == "supplemental_report":
            if not stage_fits("supplemental_report") or opinion_total >= 8:
                failed_stage = "supplemental_report"
                break
            if request_binding is not None:
                report_base = request_binding.proposed_date
            else:
                report_base = (
                    explicit_request_dates.get(
                        (chunk.actor, chunk.target.id, "supplemental_request")
                    )
                    or chunk.target.report_date
                )
            revisited = tuple(sorted(spoken_keys, key=canonical_story_key))
            response_key: StorySemanticKey = (
                "case",
                seed.case_id,
                "opinion",
                "sampled_response",
                "supplemental_report",
                chunk.target.author_role,
                chunk.target_key,
                revisited,
            )
            assert report_base is not None
            offset = _band_offset(
                seed,
                "supplemental-report-lag",
                ("case", seed.case_id, response_key, request_d_key),
                SUPPLEMENTAL_REPORT_LAG_DAYS.value,
                trace,
            )
            report_date = report_base + dt.timedelta(days=offset)
            if report_date > context.anchor_date:
                failed_stage = "supplemental_report"
                break
            trigger = (
                "supplemental_after_objection"
                if chunk.path in _ADVERSE_CONTEST_PATHS
                else "supplemental_after_completion"
            )
            supplemental_draft = _draft_response_opinion(
                seed,
                context,
                history,
                chunk,
                target_view,
                contention_keys,
                event_kind="supplemental_report",
                trigger_class=trigger,
                report_date=report_date,
                request_d_key=request_d_key,
                placeholder=f"response:{response_index + drafted}",
            )
            supplemental_binding = _BindingDraft(
                document_kind="supplemental_report",
                subtype=_SUPPLEMENTAL_DEFAULT_CARRIER,
                template_subtype=_SUPPLEMENTAL_DEFAULT_CARRIER,
                proposed_date=report_date,
                doc_date=None,
                medical_opinion_ref=supplemental_draft.placeholder,
                target_ref=chunk.target.id,
                spoken=tuple(c.id for c in chunk.contentions),
                actor_party=None,
                theories=(),
                source="sampled",
                d_key=_contest_d_key(
                    seed,
                    "supplemental_report",
                    None,
                    supplemental_draft.key,
                    chunk.target_key,
                    spoken_keys,
                ),
            )
            tentative["supplemental_report"] += 1
            tentative["total"] += 1
            opinion_total += 1
            drafted += 1
            records.append(
                _StageRecord("supplemental_report", supplemental_binding, supplemental_draft)
            )
        elif stage == "qme_deposition":
            if not stage_fits("qme_deposition") or opinion_total >= 8:
                failed_stage = "qme_deposition"
                break
            examined = supplemental_draft.view() if supplemental_draft is not None else target_view
            spoken = (
                stage_spoken("qme_deposition")
                if examined is target_view
                else tuple(c.id for c in chunk.contentions)
            )
            if not spoken:
                continue  # fully reserved: the explicit deposition stands
            trigger = (
                "deposition_examining_supplemental"
                if examined.event_kind == "supplemental_report"
                else "deposition_examining_base"
            )
            revisited = tuple(sorted(spoken_keys, key=canonical_story_key))
            deposition_key: StorySemanticKey = (
                "case",
                seed.case_id,
                "opinion",
                "sampled_response",
                "deposition",
                examined.author_role,
                examined.key,
                revisited,
            )
            d_key = _contest_d_key(
                seed,
                "qme_deposition",
                chunk.actor,
                deposition_key,
                examined.key,
                tuple(contention_keys[ref] for ref in spoken),
            )
            offset = _band_offset(
                seed,
                "deposition-lag",
                ("case", seed.case_id, d_key, examined.key),
                DEPOSITION_LAG_DAYS.value,
                trace,
            )
            deposition_date = examined.report_date + dt.timedelta(days=offset)
            if deposition_date > context.anchor_date:
                failed_stage = "qme_deposition"
                break
            deposition_draft = _draft_response_opinion(
                seed,
                context,
                history,
                chunk,
                examined,
                contention_keys,
                event_kind="deposition",
                trigger_class=trigger,
                report_date=deposition_date,
                request_d_key=None,
                placeholder=f"response:{response_index + drafted}",
            )
            deposition_binding = _BindingDraft(
                document_kind="qme_deposition",
                subtype=_DEPOSITION_CARRIER,
                template_subtype=_DEPOSITION_TEMPLATE_SUBTYPE,
                proposed_date=deposition_date,
                doc_date=None,
                medical_opinion_ref=deposition_draft.placeholder,
                target_ref=examined.ref,
                spoken=spoken,
                actor_party=chunk.actor,
                theories=chunk.theories,
                source="sampled",
                d_key=d_key,
            )
            tentative["qme_deposition"] += 1
            tentative["total"] += 1
            opinion_total += 1
            drafted += 1
            records.append(_StageRecord("qme_deposition", deposition_binding, deposition_draft))

    if failed_stage is not None:
        # R31's exact tail collapse. A failing deposition already left the
        # accepted prefix intact by breaking before it was recorded.
        if failed_stage in ("supplemental_report", "supplemental_request"):
            kept = [r for r in records if r.stage == "objection"]
            removed = [r for r in records if r.stage != "objection"]
            for record in removed:
                if record.response is not None:
                    opinion_total -= 1
            records = kept
        elif failed_stage == "objection":
            records = []
    return records, opinion_total


def derive_medical_assertion_plan(
    seed: CaseSeed,
    history: MedicalHistory | None,
    timeline: object = None,
    trace: AssertionTrace | None = None,
) -> MedicalAssertionPlan:
    """The complete assertion-layer product for one case (R32, R77 steps 3-4).

    The IDs-last entry point ``build_case_plan()`` calls. It runs the exact
    M2 base derivation byte-for-byte — same streams, same salts, same draw
    order, same ``ctn/opn/app`` IDs, same graded ledger — records that ledger
    on the test-only ``AssertionTrace.m2_baseline_ledger`` (R61), and only
    THEN applies the step-4 M3 base-disposition remodel
    (:func:`_apply_story_semantics`) and grades the completed ledger (R32
    subphase 10). The baseline snapshot always retains the original result.

    The R47 final labeling pass is subphased and IDs-last by construction:

    1-3. exact M2 base contentions, opinions and apportionment rows — the
         preserved M2 labeling pass inside ``_append_sampled`` assigns them
         in unbroken 01..N sequences;
    4.   M3 response opinions and their rows — attach at R77 step 5, taking
         the first unused suffixes after all base entries;
    5.   contention-document bindings — attach at R77 steps 5-6.

    The step-4 remodel labels nothing and moves no ID: it is a pure
    disposition/classification pass over already-labeled base entities.

    The gate is the first observable and nothing precedes it: no assertion
    rng, no ID allocation, no quality derivation, no warning may run before
    the empty-plan return. That is the whole byte-identity instrument — an
    absent block constructs nothing, so every golden byte stays where it was.
    """
    scenario = seed.scenario.medical_assertions
    if scenario is None:
        return MedicalAssertionPlan(ledger=None, contention_documents=())
    if history is None:
        raise MedicalAssertionError(
            "scenario.medical_assertions requires scenario.medical_history; "
            "assertion references cannot resolve without the world-truth ledger. "
            "Add a scenario.medical_history block, or remove "
            "scenario.medical_assertions."
        )
    context = assertion_context(seed, timeline)
    projection = project_medical_history(history, context.current_body_parts)

    reference_problems = _explicit_reference_problems(scenario)
    if reference_problems:
        raise MedicalAssertionError("\n".join(reference_problems))
    document_problems = _explicit_contention_document_problems(scenario)
    if document_problems:
        raise MedicalAssertionError("\n".join(document_problems))

    contentions = [_contention_from_entry(entry) for entry in scenario.contentions]
    opinions = [_opinion_from_entry(entry) for entry in scenario.medical_opinions]
    assertions = [_assertion_from_entry(entry) for entry in scenario.apportionment_assertions]

    if scenario.sample_assertions:
        contentions, opinions, assertions = _append_sampled(
            seed=seed,
            context=context,
            history=projection,
            contentions=contentions,
            opinions=opinions,
            assertions=assertions,
            trace=trace,
        )

    ledger = MedicalAssertionLedger(
        contentions=tuple(contentions),
        medical_opinions=tuple(opinions),
        apportionment_assertions=tuple(assertions),
    )
    graded = grade_ledger(
        context,
        projection,
        ledger,
        quality_contract="2.0.0",
    )
    if trace is not None:
        realized: dict[str, str] = {}
        for collection in (
            graded.contentions,
            graded.medical_opinions,
            graded.apportionment_assertions,
        ):
            for item in collection:
                realized[item.id] = item.quality
        trace.recipes = [
            (key, recipe, realized.get(key, "")) for key, recipe, _placeholder in trace.recipes
        ]
        # The exact M2 post-grade/pre-M3 ledger (R61). Recorded BEFORE any
        # M3 transformation so the R62 digest oracle and the R70 stream gate
        # always read the preserved baseline; the frozen model is its own
        # snapshot — no M3 subphase may mutate or replace it. The realized
        # recipe grades above are M2 counters and therefore read the
        # baseline, never the remodeled plan ledger.
        trace.m2_baseline_ledger = graded
    # R77 steps 4-5: sampled advocacy is derived FIRST (R32 semantic order —
    # its letters are the R38 qualifying communications), then the M3
    # base-disposition remodel runs strictly after the baseline snapshot,
    # then the contention loop derives contest chains, response opinions and
    # every document binding, labels IDs last, and the completed ledger is
    # graded (R32 subphase 10). Grading stays the frozen M2 rubric — it
    # reads no M3-only field, which is exactly what keeps the writer's
    # stated quality reproducible from the frozen channel-1.0.0 projection
    # (Amendment A1).
    explicit_contention_ids = frozenset(entry.id for entry in scenario.contentions)
    explicit_opinion_ids = frozenset(entry.id for entry in scenario.medical_opinions)
    contention_keys = {
        contention.id: _story_contention_key(seed, contention, explicit_contention_ids)
        for contention in graded.contentions
    }
    advocacy = _derive_advocacy(
        seed, scenario, context, graded, contention_keys, explicit_opinion_ids
    )
    story = _apply_story_semantics(
        seed,
        scenario,
        context,
        projection,
        graded,
        qualifying_communications=advocacy.qualifying_communications,
    )
    loop_ledger, contention_documents = _derive_contention_loop(
        seed,
        scenario,
        context,
        projection,
        story,
        advocacy,
        contention_keys,
        explicit_opinion_ids,
        trace,
    )
    completed = (
        graded
        if loop_ledger is graded
        else grade_ledger(
            context,
            projection,
            loop_ledger,
            quality_contract="2.0.0",
        )
    )
    return MedicalAssertionPlan(ledger=completed, contention_documents=contention_documents)


def derive_medical_assertions(
    seed: CaseSeed,
    history: MedicalHistory | None,
    timeline: object = None,
    trace: AssertionTrace | None = None,
) -> MedicalAssertionLedger | None:
    """Compatibility wrapper over :func:`derive_medical_assertion_plan` (R32).

    Returns only ``.ledger`` — the completed plan ledger (from R77 step 4:
    post-remodel), keeping every existing caller's shape while the plan entry
    point owns the gate, the M2 baseline recording, the step-4 disposition
    remodel, and (from steps 5-6) the loop subphases. The preserved pre-M3
    surface lives on ``AssertionTrace.m2_baseline_ledger``.
    """
    return derive_medical_assertion_plan(seed, history, timeline=timeline, trace=trace).ledger


__all__ = [
    "APPORTIONMENT_ID_PATTERN",
    "ASSERTION_KNOBS",
    "ASSERTION_RNG_FAMILIES",
    "ASSERTION_RNG_NAMESPACE",
    "BASIS_RULE_CONFIDENCE",
    "CDOC_ID_PATTERN",
    "COMMON_NONINDUSTRIAL_PERCENTAGES",
    "CONTENTION_ID_PATTERN",
    "EVIDENCE_BUDGET_MIX",
    "GRANULAR_NONINDUSTRIAL_PERCENTAGES",
    "GROUNDABLE_HOOKS",
    "HOOK_TO_BASIS",
    "M3_PLAN_DIGEST_APPORTIONMENT_ASSERTION_FIELDS",
    "M3_PLAN_DIGEST_CONTENTION_FIELDS",
    "M3_PLAN_DIGEST_MEDICAL_OPINION_FIELDS",
    "MAX_ADVOCACY_LETTERS_PER_CASE",
    "MAX_BOUND_CONTENTION_DOCUMENTS_PER_CASE",
    "MAX_CONTENTIONS_PER_LOOP_DOCUMENT",
    "MAX_CONTENTION_CHAINS_PER_CASE",
    "MAX_OBJECTIONS_PER_CASE",
    "MAX_QME_AME_DEPOSITIONS_PER_CASE",
    "MAX_SUPPLEMENTAL_REPORTS_PER_CASE",
    "MAX_SUPPLEMENTAL_REQUESTS_PER_CASE",
    "MEDICAL_STORY_ASSERTION_LOOP_FAMILIES",
    "MEDICAL_STORY_HASH_SEEDS",
    "MEDICAL_STORY_KNOBS",
    "MEDICAL_STORY_REPEAT_GENERATIONS",
    "MEDICAL_STORY_RNG_FAMILIES",
    "MEDICAL_STORY_RNG_NAMESPACE",
    "MEDICAL_STORY_TZ_MATRIX",
    "OPINION_ID_PATTERN",
    "REVIEWED_IDS_COMBINED_CAP",
    "ROLE_COURT_REPORTER",
    "UNCONDITIONAL_HARD_INVALID_BASES",
    "AoeCoeFinding",
    "ApportionmentAssertion",
    "ApportionmentBasisKind",
    "ApportionmentDeterminationKind",
    "ApportionmentState",
    "AssertionKnob",
    "AssertionProvenance",
    "AssertionQuality",
    "AssertionQualityContract",
    "AssertionTrace",
    "AssertionValidationContext",
    "AssertionWorldProjection",
    "BensonGrounding",
    "Contention",
    "ContentionClaimType",
    "ContentionDocumentBinding",
    "ContentionDocumentKind",
    "ContentionDocumentProjection",
    "ContentionParty",
    "ContentionPosition",
    "ContestPath",
    "DefenseContestTheory",
    "DoctrineGrounding",
    "EvidenceDisposition",
    "FirefighterPresumptionGrounding",
    "Lc4664PriorAwardGrounding",
    "MedicalAssertionError",
    "MedicalAssertionLedger",
    "MedicalAssertionPlan",
    "MedicalOpinion",
    "OpinionAuthorRole",
    "OpinionContentionDisposition",
    "OpinionEventKind",
    "OpinionReportStage",
    "OpinionRevisionKind",
    "ProjectedCondition",
    "ProjectedPriorAward",
    "ProjectedPriorClaim",
    "PsychAddOnExceptionAnalysis",
    "PsychInjuryKind",
    "RequestedApportionment",
    "SibtfGrounding",
    "StorySemanticAtom",
    "StorySemanticKey",
    "TreatmentCausation",
    "apportionment_quality",
    "assertion_context",
    "assertion_warnings",
    "canonical_story_key",
    "contention_document_projections",
    "contention_evidence",
    "contention_quality",
    "derive_medical_assertion_plan",
    "derive_medical_assertions",
    "escobedo_misses",
    "grade_ledger",
    "has_substantial_nonindustrial_evidence",
    "opinion_quality",
    "project_medical_history",
    "qme_disposition",
    "sibtf_grounding_clauses",
    "validate_contention_document_bindings",
    "validate_medical_assertions",
]
