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

Doctrine-hook boundary: AJC-61 does **not** add ``hikida_treatment_carveout``
to :data:`~wc_caseload_engine.seeds.DoctrineHook` — the doctrine content tests
require enum/content equality and a re-recorded showcase golden, both AJC-62's.
Hikida/Justice semantics are typed instead: ``claim_type="compensable_consequence"``
plus ``treatment_causation`` and ``requested_apportionment``, graded under the
NARROWED Justice rule (treatment unapportionable only where it is the *sole*
cause of the disability).

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from wc_caseload_engine.medical_history import (
    SIBTF_QUALIFYING,
    MedicalHistory,
)
from wc_caseload_engine.seeds import (
    BensonGrounding,
    ClaimResponse,
    DoctrineGrounding,
    DoctrineHook,
    EvalType,
    FirefighterPresumptionGrounding,
    Lc4664PriorAwardGrounding,
    SibtfGrounding,
    TargetStage,
)

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

type AssertionQuality = Literal["supported", "thin", "unsupportable"]
"""The truth-only grade. Never analyzer-visible; the leakage probe enforces it."""

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

CONTENTION_ID_PATTERN: Final[str] = r"^ctn-(0[1-9]|[1-9][0-9])$"
OPINION_ID_PATTERN: Final[str] = r"^opn-(0[1-9]|[1-9][0-9])$"
APPORTIONMENT_ID_PATTERN: Final[str] = r"^app-(0[1-9]|[1-9][0-9])$"
"""``ctn-01`` … ``ctn-99``; ``opn-``/``app-`` likewise. Two digits from ``01``.
The seed caps (12/8/12) keep two-digit space sufficient; IDs are assigned only
after every stochastic decision, as a pure labelling pass."""

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
    """Validated against exactly the fourteen shipped enum members — the
    fifteenth (Hikida) is typed fields, not an enum member, until AJC-62."""

    rationale: str | None = None
    treatment_causation: TreatmentCausation | None = None
    """Explicit-seed-only in M2; the sampler never sets it. With
    ``requested_apportionment`` it types the narrowed Justice/Hikida claim on a
    ``compensable_consequence`` contention."""

    requested_apportionment: RequestedApportionment | None = None
    groundings: tuple[DoctrineGrounding, ...] = ()

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
        return tuple(
            a for a in self.apportionment_assertions if a.opinion_id == opinion_id
        )

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
        clause.name for clause in SIBTF_QUALIFYING if clause.holds(history)  # type: ignore[arg-type]
    )


__all__ = [
    "APPORTIONMENT_ID_PATTERN",
    "CONTENTION_ID_PATTERN",
    "HOOK_TO_BASIS",
    "OPINION_ID_PATTERN",
    "REVIEWED_IDS_COMBINED_CAP",
    "ApportionmentAssertion",
    "ApportionmentBasisKind",
    "ApportionmentDeterminationKind",
    "ApportionmentState",
    "AssertionQuality",
    "AssertionValidationContext",
    "AssertionWorldProjection",
    "BensonGrounding",
    "Contention",
    "ContentionClaimType",
    "ContentionParty",
    "ContentionPosition",
    "DoctrineGrounding",
    "EvidenceDisposition",
    "FirefighterPresumptionGrounding",
    "Lc4664PriorAwardGrounding",
    "MedicalAssertionLedger",
    "MedicalOpinion",
    "OpinionAuthorRole",
    "OpinionReportStage",
    "ProjectedCondition",
    "ProjectedPriorAward",
    "ProjectedPriorClaim",
    "PsychAddOnExceptionAnalysis",
    "RequestedApportionment",
    "SibtfGrounding",
    "TreatmentCausation",
    "project_medical_history",
    "sibtf_grounding_clauses",
]
