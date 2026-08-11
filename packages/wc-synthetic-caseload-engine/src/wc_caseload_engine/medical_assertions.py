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
    """Nonfatal authoring warnings — the ungrounded-explicit-hook case.

    Warn, never block (decision #2): the hook is kept and the assertion stands;
    the author is told the argument has nothing typed behind it. One warning
    per distinct hook, sorted, so the output is stable.
    """
    ungrounded: set[str] = set()
    for contention in ledger.contentions:
        supplied = {g.hook for g in contention.groundings}
        for hook in contention.doctrine_hooks:
            if hook in GROUNDABLE_HOOKS and hook not in supplied:
                ungrounded.add(hook)
    return tuple(
        f"medical_assertions: doctrine hook '{hook}' has no typed MedicalHistory "
        "grounding; explicit hook retained"
        for hook in sorted(ungrounded)
    )


__all__ = [
    "APPORTIONMENT_ID_PATTERN",
    "BASIS_RULE_CONFIDENCE",
    "CONTENTION_ID_PATTERN",
    "GROUNDABLE_HOOKS",
    "HOOK_TO_BASIS",
    "OPINION_ID_PATTERN",
    "REVIEWED_IDS_COMBINED_CAP",
    "UNCONDITIONAL_HARD_INVALID_BASES",
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
    "assertion_warnings",
    "contention_evidence",
    "contention_quality",
    "escobedo_misses",
    "grade_ledger",
    "has_substantial_nonindustrial_evidence",
    "opinion_quality",
    "project_medical_history",
    "qme_disposition",
    "sibtf_grounding_clauses",
    "validate_medical_assertions",
]
