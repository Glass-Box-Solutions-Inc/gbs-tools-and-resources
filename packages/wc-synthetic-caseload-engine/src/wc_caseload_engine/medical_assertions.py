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
import random
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from wc_caseload_engine.medical_history import (
    SIBTF_QUALIFYING,
    MedicalHistory,
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


def _contention_referential(
    contention: Contention, history: AssertionWorldProjection
) -> list[str]:
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
            problems.append(
                f"medical opinion '{opinion.id}' reviews unknown condition '{ref}'"
            )
    for ref in opinion.reviewed_prior_claim_ids:
        if ref not in history.prior_claim_ids():
            problems.append(
                f"medical opinion '{opinion.id}' reviews unknown prior claim '{ref}'"
            )
    for ref in opinion.reviewed_prior_award_ids:
        if ref not in history.prior_award_ids():
            problems.append(
                f"medical opinion '{opinion.id}' reviews unknown prior award '{ref}'"
            )
    for ref in opinion.endorses_contention_ids:
        if ref not in contention_ids:
            problems.append(
                f"medical opinion '{opinion.id}' endorses unknown contention '{ref}'"
            )
    for ref in opinion.rejects_contention_ids:
        if ref not in contention_ids:
            problems.append(
                f"medical opinion '{opinion.id}' rejects unknown contention '{ref}'"
            )
    for ref in sorted(
        set(opinion.endorses_contention_ids) & set(opinion.rejects_contention_ids)
    ):
        problems.append(
            f"medical opinion '{opinion.id}' both endorses and rejects contention '{ref}'"
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
                f"apportionment assertion '{assertion.id}' references unknown "
                f"condition '{ref}'"
            )
    for ref in assertion.prior_claim_ids:
        if ref not in history.prior_claim_ids():
            problems.append(
                f"apportionment assertion '{assertion.id}' references unknown prior "
                f"claim '{ref}'"
            )
    for ref in assertion.prior_award_ids:
        if ref not in history.prior_award_ids():
            problems.append(
                f"apportionment assertion '{assertion.id}' references unknown prior "
                f"award '{ref}'"
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
                    problems.append(
                        f"medical opinion chain contains a cycle: {chain}"
                    )
    return problems


def _lifecycle(ledger: MedicalAssertionLedger) -> list[str]:
    problems: list[str] = []
    for opinion in ledger.medical_opinions:
        owned_assertions = ledger.assertions_of(opinion.id)
        if opinion.report_stage == "final" and opinion.apportionment_state == "deferred":
            problems.append(
                f"medical opinion '{opinion.id}' is final but apportionment_state "
                "is 'deferred'"
            )
        if opinion.report_stage == "interim" and opinion.apportionment_state == "omitted":
            problems.append(
                f"medical opinion '{opinion.id}' is interim but apportionment_state "
                "is 'omitted'"
            )
        if opinion.apportionment_state == "deferred" and owned_assertions:
            problems.append(
                f"medical opinion '{opinion.id}' is deferred but owns an "
                "apportionment assertion"
            )
        if opinion.apportionment_state == "omitted" and owned_assertions:
            problems.append(
                f"medical opinion '{opinion.id}' is omitted but owns an "
                "apportionment assertion"
            )
        if opinion.apportionment_state == "determined" and opinion.determination_kind is None:
            problems.append(
                f"medical opinion '{opinion.id}' is determined but has no "
                "determination_kind"
            )
        if (
            opinion.determination_kind is not None
            and opinion.apportionment_state != "determined"
        ):
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
        if (
            contention.treatment_causation is not None
            and contention.target_condition_id is None
        ):
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
        "foundation recipe builds — the measured supported-recipe "
        "conditional is 0.8267, and a thin or unsupportable foundation "
        "recipe never grades supported. This mix is the sanctioned "
        "construction adjustment (Part 3:659) solved against that drag so "
        "the realized share lands mid-band: 15/16 x 0.8267 = 0.775. The "
        "thin:unsupportable residual keeps counsel's 2:1 split."
    ),
    source=(
        "Derived from QUALITY_TARGET_WEIGHTS and the measured 6,000-case "
        "cohort drag (fix round 1, PR #44)."
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
    provenance="counsel_estimate",
    rationale=(
        "Counsel: percentages sit 'normally on the fives... or a third'; roundness "
        "is NOT a tell, excess granularity is. Direction counsel's; the exact mass "
        "is invented. Percentage roundness never affects quality."
    ),
    source="sme-answers.md q4; anti-clamp rule per frequency-priors-calibration.md.",
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
    5, 10, 15, 20, 25, 30, 33, 35, 40, 45, 50,
    55, 60, 65, 67, 70, 75, 80, 85, 90, 95,
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
        psych = next(
            (c for c in history.conditions if c.key == "depression_anxiety"), None
        )
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
) -> AssertionQuality:
    """Grade one contention against the world ledger.

    The two hard Hikida rows come first — they are legal-error terminals under
    the narrowed *Justice* rule, not evidence questions. Everything else is the
    evidence tri-state: contradicted is unsupportable, supported-with-reasoning
    is supported, and the indeterminate or unreasoned middle is thin.
    """
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


def _hard_invalid_basis(
    assertion: ApportionmentAssertion, linked: Contention | None
) -> bool:
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
) -> tuple[str, ...]:
    """Which applicable checklist items this assertion misses, in item order.

    Each item reads an independently controllable input, so the frozen oracle
    can move a supported build to its expected lower grade one item at a time.
    """
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
    if owner is not None and not owner.examination_performed:
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
        benson = next(
            (g for g in assertion.groundings if isinstance(g, BensonGrounding)), None
        )
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
    return any(
        ref not in owner.reviewed_prior_award_ids for ref in assertion.prior_award_ids
    )


def apportionment_quality(
    history: AssertionWorldProjection,
    context: AssertionValidationContext,
    ledger: MedicalAssertionLedger,
    assertion: ApportionmentAssertion,
) -> AssertionQuality:
    """Grade one apportionment assertion under the frozen precedence.

    1. hard invalid / zero foundation -> unsupportable;
    2. direct contradiction by all cited factors -> unsupportable;
    3. any applicable checklist miss -> thin;
    4. all pass -> supported.
    """
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
    if (cited or cited_claims) and all(
        c is None or c.wholly_unrelated for c in cited
    ) and all(c is None or not c.overlaps_current for c in cited_claims):
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

    if escobedo_misses(history, ledger, assertion):
        return "thin"
    return "supported"


def opinion_quality(
    history: AssertionWorldProjection,
    context: AssertionValidationContext,
    ledger: MedicalAssertionLedger,
    opinion: MedicalOpinion,
) -> AssertionQuality:
    """Grade one opinion: the worst of everything it stands behind.

    Endorsed contentions are graded as stated; rejected ones on the OPPOSITE
    proposition (a rejection of a false claim is good medicine, never a
    mechanical inversion of the claim's own grade); owned assertions carry
    their own grades; the opinion's own foundation and its final determination
    close the set. Interim deferral itself carries no penalty.
    """
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
            sink(contention_quality(history, context, contention))
    for ref in opinion.rejects_contention_ids:
        contention = ledger.contention(ref)
        if contention is not None:
            flipped: ContentionPosition = (
                "deny" if contention.position == "affirm" else "affirm"
            )
            opposite = contention.model_copy(update={"position": flipped})
            sink(contention_quality(history, context, opposite))

    for assertion in ledger.assertions_of(opinion.id):
        sink(apportionment_quality(history, context, ledger, assertion))

    relevant_review = bool(
        [
            ref
            for ref in opinion.reviewed_condition_ids
            if (condition := history.condition(ref)) is not None
            and condition.surfaces_in_file
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
) -> MedicalAssertionLedger:
    """Re-derive every quality in *ledger* from the frozen rubric.

    The single grading pass both composition paths share: explicit entries and
    sampled entries are graded identically, and a sampling target recipe is
    never copied — the truth-side validator re-runs this exact function to
    prove a stated label is the derived one.
    """
    contentions = tuple(
        c.model_copy(update={"quality": contention_quality(history, context, c)})
        for c in ledger.contentions
    )
    regraded = MedicalAssertionLedger(
        contentions=contentions,
        medical_opinions=ledger.medical_opinions,
        apportionment_assertions=ledger.apportionment_assertions,
    )
    assertions = tuple(
        a.model_copy(
            update={"quality": apportionment_quality(history, context, regraded, a)}
        )
        for a in ledger.apportionment_assertions
    )
    regraded = MedicalAssertionLedger(
        contentions=contentions,
        medical_opinions=ledger.medical_opinions,
        apportionment_assertions=assertions,
    )
    opinions = tuple(
        o.model_copy(update={"quality": opinion_quality(history, context, regraded, o)})
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
                    refs = [
                        ("prior claim", ref, claim_ids)
                        for ref in grounding.prior_claim_ids
                    ]
                elif isinstance(grounding, SibtfGrounding):
                    refs = [
                        ("condition", ref, condition_ids)
                        for ref in grounding.preexisting_condition_ids
                    ]
                    refs.extend(
                        ("prior award", ref, award_ids)
                        for ref in grounding.prior_award_ids
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
    """

    suppression_hits: int = 0
    recipes: list[tuple[str, str, str]] = None  # type: ignore[assignment]
    evidence_budgets: list[int] = None  # type: ignore[assignment]
    distractor_available: int = 0
    distractor_included: int = 0
    candidate_families: dict[str, int] = None  # type: ignore[assignment]
    eligible_candidates: dict[str, int] = None  # type: ignore[assignment]
    lifecycle: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.recipes = [] if self.recipes is None else self.recipes
        self.evidence_budgets = [] if self.evidence_budgets is None else self.evidence_budgets
        self.candidate_families = (
            {} if self.candidate_families is None else self.candidate_families
        )
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
        for ref in opinion.endorses_contention_ids:
            if ref not in contention_ids:
                problems.append(
                    f"medical opinion '{opinion.id}' endorses unknown contention '{ref}'"
                )
        for ref in opinion.rejects_contention_ids:
            if ref not in contention_ids:
                problems.append(
                    f"medical opinion '{opinion.id}' rejects unknown contention '{ref}'"
                )
        for verb, ref in (
            ("responds to", opinion.responds_to_opinion_id),
            ("supersedes", opinion.supersedes_opinion_id),
        ):
            if ref is not None and ref != opinion.id and ref not in opinion_ids:
                problems.append(
                    f"medical opinion '{opinion.id}' {verb} unknown opinion '{ref}'"
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
            incidence = _assertion_rng(
                seed, "contention-incidence", f"condition:{condition.id}"
            )
            if _fraction_draw(incidence, P_CONTENTION_GIVEN_CONDITION.value):
                note_drawn("condition")
                chooser = _assertion_rng(
                    seed, "contention-type", f"condition:{condition.id}"
                )
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
            incidence = _assertion_rng(
                seed, "contention-incidence", f"firefighter:{condition.id}"
            )
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
                        groundings=(
                            FirefighterPresumptionGrounding(condition_id=condition.id),
                        ),
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
                qualifying_conditions[0]
                if target_award is None and qualifying_conditions
                else None
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
    salt = _semantic_salt(draft.semantic_key)
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
            elif roll < float(
                P_PSYCH_PREDOMINANT_CAUSE_DENIAL.value + P_GFPA_DEFENSE.value
            ):
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
        _replace_draft(draft, semantic_key=_contention_semantic_key(draft))
        for draft in shaped
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
    # their real IDs, sampled drafts under their final semantic keys. The
    # probe objects carry the exact final fields; only the ID is a
    # placeholder, and nothing below reads it.
    pending: list[tuple[str | SemanticKey, Contention]] = [
        (contention.id, contention) for contention in contentions
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
            report_stage, state = (
                ("interim", "deferred") if deferred else ("final", "determined")
            )
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
                            "the record affirmatively shows the disability is "
                            "entirely industrial"
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
        supportable: list[tuple[str | SemanticKey, Contention]] = []
        for ref, contention in pending:
            evidence = contention_evidence(history, context, contention)
            if evidence == "contradicts" and author_role in ("qme", "ame"):
                if qme_disposition(evidence) == "reject":
                    rejects.append(ref)
            elif evidence == "supports":
                supportable.append((ref, contention))
        if supportable:
            # Grade bookkeeping keys on the UNIQUE pending reference, never
            # the B.2 suppression tuple: two distinct explicit contentions may
            # legally share that tuple, and a tuple-keyed dict kept only the
            # last twin's grade — a thin ctn-02 erased a supported ctn-01's
            # endorsement (sol fix round 2, F2, proved on cohort-4803).
            would_be = {
                ref: contention_quality(history, context, c) for ref, c in supportable
            }
            pick = next(
                ((ref, c) for ref, c in supportable if would_be[ref] == "supported"),
                supportable[0] if author_role == "ptp" else None,
            )
            if pick is not None:
                pick_ref, pick_contention = pick
                if author_role in ("qme", "ame"):
                    if qme_disposition("supports") == "endorse":
                        endorses.append(pick_ref)
                else:
                    contention_salt = _semantic_salt(
                        _contention_semantic_key(pick_contention)
                    )
                    if _fraction_draw(
                        _assertion_rng(seed, "ptp-disposition", contention_salt),
                        P_PTP_ENDORSE_SUPPORTED.value,
                    ):
                        endorses.append(pick_ref)
        elif author_role == "ptp" and pending:
            # The treater's occasional adoption of a weaker claim keeps the
            # indeterminate/contradicted PTP policies live decision families.
            candidate_ref, candidate = pending[0]
            evidence = contention_evidence(history, context, candidate)
            endorse_p = {
                "supports": P_PTP_ENDORSE_SUPPORTED.value,
                "indeterminate": P_PTP_ENDORSE_INDETERMINATE.value,
                "contradicts": P_PTP_ENDORSE_CONTRADICTED.value,
            }[evidence]
            contention_salt = _semantic_salt(_contention_semantic_key(candidate))
            if _fraction_draw(
                _assertion_rng(seed, "ptp-disposition", contention_salt), endorse_p
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
            for ref, contention in pending:
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
                    groundings.append(
                        Lc4664PriorAwardGrounding(prior_award_id=part_awards[0])
                    )
                assertion_key: SemanticKey = ("apportionment", author_role, part)
                target_index = _weighted_index(
                    _assertion_rng(seed, "quality-target", _semantic_salt(assertion_key)),
                    QUALITY_TARGET_WEIGHTS.value,
                )
                recipe = ("supported", "thin", "unsupportable")[target_index]
                fields: dict[str, object] = {
                    "description": (
                        f"chronic {part} disability limiting sustained activity"
                    ),
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
                        "the prior award is treated separately under the "
                        "conclusive presumption"
                        if part_awards
                        else None
                    ),
                }
                uncited_contributor = next(
                    (
                        c.id
                        for c in contributors
                        if part in c.apportionment_targets
                        and c.id not in part_conditions
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
                    elif lever in ("disability_causation_stated",
                                   "reasonable_medical_probability"):
                        fields[lever] = False
                    else:
                        fields[lever] = None
                elif recipe == "unsupportable":
                    variants = ["vocational_apportionment", "bare_age", "bare_gender",
                                "risk_factor_only"]
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
    for draft, (_ref, probe) in zip(
        ordered, pending[len(contentions) :], strict=True
    ):
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
                    "endorses_contention_ids": tuple(
                        _resolve_ref(ref) for ref in endorse_refs
                    ),
                    "rejects_contention_ids": tuple(
                        _resolve_ref(ref) for ref in reject_refs
                    ),
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
                    "opinion_id": opinion_id_map.get(
                        assertion.opinion_id, assertion.opinion_id
                    ),
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
    raise MedicalAssertionError(
        f"no unused {prefix}- id remains below the two-digit ceiling"
    )


def derive_medical_assertions(
    seed: CaseSeed,
    history: MedicalHistory | None,
    timeline: object = None,
    trace: AssertionTrace | None = None,
) -> MedicalAssertionLedger | None:
    """The assertion ledger for one case, or ``None`` when the seed asked for none.

    The gate is the first observable and nothing precedes it: no assertion rng,
    no ID allocation, no quality derivation, no warning may run before the
    ``None`` return. That is the whole byte-identity instrument — an absent
    block constructs nothing, so every golden byte stays where it was.
    """
    scenario = seed.scenario.medical_assertions
    if scenario is None:
        return None
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
    graded = grade_ledger(context, projection, ledger)
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
            (key, recipe, realized.get(key, ""))
            for key, recipe, _placeholder in trace.recipes
        ]
    return graded


__all__ = [
    "APPORTIONMENT_ID_PATTERN",
    "ASSERTION_KNOBS",
    "ASSERTION_RNG_FAMILIES",
    "ASSERTION_RNG_NAMESPACE",
    "BASIS_RULE_CONFIDENCE",
    "COMMON_NONINDUSTRIAL_PERCENTAGES",
    "CONTENTION_ID_PATTERN",
    "EVIDENCE_BUDGET_MIX",
    "GROUNDABLE_HOOKS",
    "HOOK_TO_BASIS",
    "OPINION_ID_PATTERN",
    "REVIEWED_IDS_COMBINED_CAP",
    "UNCONDITIONAL_HARD_INVALID_BASES",
    "ApportionmentAssertion",
    "ApportionmentBasisKind",
    "ApportionmentDeterminationKind",
    "ApportionmentState",
    "AssertionKnob",
    "AssertionProvenance",
    "AssertionQuality",
    "AssertionTrace",
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
    "MedicalAssertionError",
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
    "apportionment_quality",
    "assertion_context",
    "assertion_warnings",
    "contention_evidence",
    "contention_quality",
    "derive_medical_assertions",
    "escobedo_misses",
    "grade_ledger",
    "has_substantial_nonindustrial_evidence",
    "opinion_quality",
    "project_medical_history",
    "qme_disposition",
    "sibtf_grounding_clauses",
    "validate_medical_assertions",
]
