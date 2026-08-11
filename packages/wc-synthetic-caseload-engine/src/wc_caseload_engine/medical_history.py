"""The world-truth ledger — what the applicant actually had, before anyone argued about it.

A sibling of :class:`~wc_caseload_engine.case_facts.CaseFacts` rather than a field on
it, following the ``money`` precedent for the same reason money follows it: the
clinical ledger is derived for *every* case, and this one is derived only for a seed
that carries ``scenario.medical_history``. Keeping them apart is what lets "this case
has no medical-history layer" be a single ``None`` the planner can short-circuit on,
instead of a dozen empty collections on a model that is always there.

**Nothing here is published, and that is the design rather than an unfinished edge.**
The two-level design this ledger opens depends on it. World truth is the thing an
assertion is *graded against*; a document that could cite it directly would collapse
the two levels back into one, because a party's assertion about a history could no
longer diverge from the history. So M1 derives the ledger, carries it on the plan,
and writes it nowhere: not into ``case_facts.yaml``, not into the manifest's
``caseFacts`` block, not into the truth manifest. That is the same discipline
``case_facts.py`` already applies to ``wpi`` and ``pd`` — "fields the ledger derives
but nothing renders stay on the model for later phases and out of the output" — one
layer earlier. M3 gives the conditions a document surface; M4 gives the ledger a
scorer-only channel and the version bump that goes with it.

The consequence worth stating plainly: **every field on every model in this module is
byte-inert in M1**, and the seed gate that reaches them is marked "not yet honoured"
so the schema-honesty sweep will force that marker's removal the moment M3 wires a
surface up.

## The sampler

``c-calibrated-by-b``, which is the design record's phrase and is precise. Health
archetypes carry the *correlation* between conditions — real people are not a set of
independent coin flips, and a corpus built from independent draws produces nobody who
is simply healthy. Per-condition *marginals* are then calibrated, per applicant, so
the corpus still reproduces the cited prevalences in
:mod:`~wc_caseload_engine.clinical_grounding`.

Concretely, for one condition and one applicant, everything happens on the log-odds
scale, because everything being combined is an odds ratio:

1. the demographic mixture gives archetype weights ``w_a``;
2. each archetype has a fixed relative affinity ``r_a`` for the condition, and the
   BMI and smoking gradients contribute published odds ratios of their own;
3. :func:`calibrate` solves for the one **intercept** ``b`` where
   ``sum_a w_a * clamp(logistic(b + log r_a + log OR_bmi + log OR_smoking)) == target``,
   integrated over the BMI x smoking population at that age — ``target`` being the
   published rate for that age and sex.

The solve is what makes "the marginals match" true by construction rather than by
hand-tuning, and it is what keeps the archetype table *editable*: add an archetype,
change an affinity, and the marginals still land, because the intercept re-solves.

**It is an intercept and not a multiplicative scale, and the difference is not
stylistic.** The first version calibrated a scale ``s`` and formed the baseline as
``s * r_a`` — a product of two unbounded positives handed to a transform whose
derivation assumes a probability. An exhaustive sweep found 907 cells where that
product exceeded 1; at age 55 the multimorbid lumbar baseline reached 1.231, every BMI
band clamped to the ceiling, and the published 1.79 gradient disappeared in precisely
the profile where the condition is most likely. The logistic link keeps every baseline
strictly inside ``(0, 1)`` across the intercepts a calibrated solve actually produces,
so the property holds structurally instead of by a sweep that finds no counterexample
this week — with ``clamp`` owning the float-saturation extremes the link cannot, since
``sigmoid(38)`` is exactly 1.0 in float64.

``clamp`` then bounds every per-archetype probability strictly inside ``(0, 1)``. That
is the anti-fingerprint guarantee doing real work rather than being asserted: no
archetype can be the only one able to produce a given condition set, because every
archetype can produce every subset.

**What that does and does not buy.** It buys *singleton-freedom*: no observed set of
conditions rules an archetype out, within any demographic cell and claim shape. It does
**not** buy "membership is not recoverable" — the archetype prior concentrates with age
and body mass, correctly so, and on some cells a common set is strongly indicative. The
posterior bound this module guarantees is stated exactly on
``TestProfileMembershipIsNotAFingerprint``, counterexample included. The recoverability
question that matters — ``P(archetype | every analyzer-visible feature)`` — needs
artifacts that do not exist in M1 and is M4's leakage anti-probe (AJC-63).

## The two-surface documentation gate

World truth and what the file *shows* are different things, and the research is
emphatic that conflating them is the standing error. Each condition therefore carries
two booleans — ``surfaces_in_file`` and ``billing_coded`` — calibrated so that, across
a corpus, :data:`~wc_caseload_engine.clinical_grounding.P_SURFACES_IN_FILE` of
applicants have a comorbidity that surfaces anywhere (counsel-confirmed, and revised
by counsel once already) while :data:`P_BILLING_CODED` have one coded in the claim's
own billing (NCCI, measured). The rates are named rather than spelled out here: the
surfacing figure moved from 0.33 to 0.50 on 2026-08-10, and prose that repeats a
number is prose that will be revised in one place and not the other.

The conditional rate is solved **globally**, not per applicant — see
:func:`surfacing_conditional`. Dividing each applicant's own ``P(any)`` into the
target looks equivalent and is not: it caps at 1 for anyone below the target, so those
applicants surface less than the target while nobody surfaces more, and the aggregate
lands under it. Both are flags on world truth here; the surfaces themselves are M3's.
"""

from __future__ import annotations

import datetime as dt
import math
import random
from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from typing import Any, Final, Literal

import structlog
from pydantic import BaseModel, ConfigDict, Field

from wc_caseload_engine.case_context import DERIVED_AGE_RANGE
from wc_caseload_engine.clinical_grounding import (
    CONDITION_CATALOG,
    FEMALE_SHARE,
    OBESE_BANDS,
    P_BILLING_CODED,
    P_SURFACES_IN_FILE,
    REFERENCE_CLAIM_SHAPES,
    RISK_MULTIPLIERS,
    SMOKING_DISTRIBUTION,
    Knob,
    age_band_rate,
    bmi_band_for_draw,
    bmi_distribution,
)
from wc_caseload_engine.seeds import ANCHOR_DATE, CaseSeed, derive_seed

log = structlog.get_logger(__name__)


def _rng(seed: CaseSeed, salt: str) -> random.Random:
    """A private stream under the ``medical:`` namespace.

    A new namespace, not a new salt inside an existing one. ``case_facts`` owns
    ``facts:`` and the cast owns the bare salts; drawing from either would re-roll
    draws that already ship, which is rng drift — the standing R2 risk on this
    programme and the one failure mode that moves goldens without touching a
    template.
    """
    return random.Random(derive_seed(seed.rng_seed, f"medical:{salt}"))


# ---------------------------------------------------------------------------
# Models — world truth
# ---------------------------------------------------------------------------


class ApplicantDemographics(BaseModel):
    """The applicant facts the archetype mixture conditions on.

    Distinct from ``profile.applicant`` on the seed, which states what an author
    *asked for*: this states what was *decided*, with every unstated field drawn.
    Disease states are deliberately absent — they are not demographics, they live in
    :class:`MedicalHistory` via the archetype draw, and the design record names that
    split explicitly.

    ``age`` is derived from the date of birth against ``ANCHOR_DATE``, never from a
    wall clock. The clock-relative version of this calculation is the exact defect
    ``case_context._date_of_birth`` exists to hold shut, and re-introducing it one
    module over would be the same bug with a new address.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    age: int = Field(ge=0)
    """Whole years at ``ANCHOR_DATE``. Not yet honoured — no document renders it (M3)."""

    sex: Literal["female", "male"]
    """Not yet honoured — carried for the archetype mixture and M3's prose registers."""

    bmi_band: Literal["normal_or_under", "overweight", "obese", "severely_obese"]
    """A risk factor, not a disease state. Not yet honoured — M3 renders it, and M5's
    surgical-clearance story (note C §4.1: the BMI 40 arthroplasty threshold) is what
    makes the ``severely_obese`` band worth distinguishing at all."""

    smoking_status: Literal["never", "former", "current"]
    """Not yet honoured. ``former`` is distinguished from ``never`` because note C
    §4.3 records that cessation of a year or more returns fusion outcomes to the
    never-smoker baseline — a former smoker is not a continuing apportionment target
    the way an active one is, and that distinction is M3/M5 content."""

    @property
    def obese(self) -> bool:
        return self.bmi_band in OBESE_BANDS


class MedicalCondition(BaseModel):
    """One true pre-existing or concurrent condition — world truth, never rendered.

    Distinct from a diagnosis a document asserts. A document's diagnosis is itself an
    assertion and belongs on the M2 assertion layer; this is the fact that assertion
    will be graded against.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    key: str
    """Catalog key, or ``seeded`` for an author-stated condition with no catalog row.

    The join back to :data:`~wc_caseload_engine.clinical_grounding.CONDITION_CATALOG`,
    which is what lets the marginal-matching test count realised conditions against
    the table they were drawn from without re-deriving the mapping from labels.
    """

    label: str
    body_system: str
    body_part: str | None = None
    """``None`` for a systemic condition with no body-part linkage. Not the same as
    'we do not know': hypertension genuinely has no region."""

    icd10: str | None = None

    onset: dt.date | None = None
    """``None`` is a legitimate world-truth state, not a missing field.

    Every degenerative finding in the catalog is drawn from a study of *asymptomatic*
    people, where the finding was discovered on imaging and has no onset date at all.
    Fabricating one would assert a fact the sources contradict.
    """

    causal_ground_truth: Literal["industrial", "nonindustrial", "mixed"] = "nonindustrial"
    """The actual causal category, distinct from what any party will assert about it."""

    wholly_unrelated: bool = False
    """No overlap at all with the claimed regions, so not an apportionment target.

    Distinct from ``causal_ground_truth='nonindustrial'``: a nonindustrial *lumbar*
    finding in a lumbar case is a legitimate section 4663 target if it is shown to be
    causing disability now; a condition with no overlapping impairment is not a target
    at all, because there is nothing to apportion between. Derived from the catalog's
    ``apportionment_targets`` against the claim's own body parts.
    """

    severity: Literal["subclinical", "mild", "moderate", "severe"] = "mild"
    trajectory: Literal["resolved", "stable", "progressive", "fluctuating"] = "stable"

    symptomatic_before_doi: bool | None = None
    """Was this already producing disability before the injury? Escobedo turns on it.

    Not a coin. A finding drawn from an asymptomatic-population table is asymptomatic
    by construction — that is what the study measured — and a diagnosed systemic
    condition is under management. No source gives a rate for the exceptions, so none
    is invented; M2 revisits this when the assertion layer needs the contested case.
    """

    billing_coded: bool = False
    """Coded in this claim's own medical billing. Not yet honoured — M3 renders it."""

    surfaces_in_file: bool = False
    """Visible anywhere in the file, by any route. Implied by ``billing_coded``.

    The wider of the two surfaces. Note F's standing warning applies: if this
    correlates with anything mechanical a renderer also varies, an analyzer can learn
    to separate label classes on document counts instead of on legal reasoning.
    """


class PriorAward(BaseModel):
    """The section 4664(b) fact itself: an adjudicated or stipulated PD award.

    Its own referential target rather than only a field inside
    :class:`PriorClaim`, because an M2 apportionment assertion has to be able to point
    at *the award* the way the graph's APPORTIONS edge targets a body part rather than
    a whole claim history.

    **Data model only.** No overlap arithmetic, no dollars, no rendering. The
    conclusive-presumption maths and the section 4664 offset are M5's and are gated on
    a counsel check that has not landed; building the fields now and the arithmetic
    later is the order that keeps an unreviewed legal calculation out of the corpus.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    body_parts: tuple[str, ...] = Field(min_length=1)
    """Section 4664(b) and (c) both operate per region of the body, which is why this
    is a tuple of regions rather than one. Not yet honoured — M3 renders it."""

    pd_percent: int = Field(ge=1, le=100)
    """The figure section 4664 subtracts. Not yet honoured — M5 owns the subtraction,
    and even a real QME declines to perform it in the report."""

    award_date: dt.date
    resolution_type: Literal["stipulated_award", "findings_and_award", "c_and_r"]

    still_exists_conclusively_presumed: bool = False
    """Section 4664(b)'s presumption, modelled rather than hardcoded.

    Carries the **resolved** value. The seed field is ``bool | None``; when the
    author says nothing, :data:`PRESUMPTION_DEFAULT_BY_RESOLUTION` supplies the
    default from how the award issued — counsel resolved §2-Q7 on 2026-08-10:
    a stipulated award presumes, a findings-and-award presumes (counsel-assumed,
    M5 micro-confirm), a compromise and release never does. An explicit seed
    value always wins. M2's assertion layer consumes this; M5 owns the offset
    arithmetic.
    """


class PriorClaim(BaseModel):
    """A workers' compensation claim the applicant filed before this one.

    Seed-stated only. Unlike conditions, prior claims are not sampled: a prior claim
    is a discrete litigated event with its own dates, employer and resolution, and
    drawing one probabilistically would invent a case history no author asked for.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    body_parts: tuple[str, ...] = Field(min_length=1)
    date_of_injury: dt.date
    employer: str | None = None
    """``None`` means the same employer as the current claim — the common pattern. A
    distinct value marks a different-employer prior claim, which is what Benson
    framing turns on. Not yet honoured — M3 renders it."""

    resolution_type: Literal[
        "c_and_r", "stipulated_award", "findings_and_award", "dismissed", "denied", "pending"
    ]
    resolution_date: dt.date | None = None
    award: PriorAward | None = None
    """Set only where the claim produced a PD award. Modelled independently of
    ``resolution_type`` rather than derived from it, so "claim happened, no award
    resulted" stays representable and a C&R that *did* carry an award can be stated
    explicitly instead of assumed either way."""


class MedicalHistory(BaseModel):
    """The applicant's actual pre-injury and concurrent medical picture, in full.

    Carried beside :class:`~wc_caseload_engine.case_facts.CaseFacts` on the plan.
    Computed once by :func:`derive_medical_history` and never mutated.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    demographics: ApplicantDemographics
    archetype: str
    """Which health profile this applicant was drawn from.

    Recorded so the anti-fingerprint property can be *tested* — a test needs to know
    the true archetype to assert that it is not recoverable from the conditions. It is
    exactly the kind of field that must never reach an analyzer-visible artifact, and
    in M1 nothing reaches one at all.
    """

    conditions: tuple[MedicalCondition, ...] = ()
    prior_claims: tuple[PriorClaim, ...] = ()

    def condition(self, condition_id: str) -> MedicalCondition | None:
        return next((c for c in self.conditions if c.id == condition_id), None)

    def prior_award(self, award_id: str) -> PriorAward | None:
        for claim in self.prior_claims:
            if claim.award is not None and claim.award.id == award_id:
                return claim.award
        return None

    @property
    def awards(self) -> tuple[PriorAward, ...]:
        return tuple(c.award for c in self.prior_claims if c.award is not None)

    def wholly_unrelated_conditions(self) -> tuple[MedicalCondition, ...]:
        return tuple(c for c in self.conditions if c.wholly_unrelated)

    def surfaced_conditions(self) -> tuple[MedicalCondition, ...]:
        return tuple(c for c in self.conditions if c.surfaces_in_file)

    def condition_keys(self) -> frozenset[str]:
        return frozenset(c.key for c in self.conditions)


# ---------------------------------------------------------------------------
# Archetypes
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class HealthArchetype:
    """One health profile: a base share of the population and a taste in conditions.

    ``affinity`` is *relative*, never a probability. The calibration below turns it
    into one, per condition and per applicant, which is the whole point — an affinity
    written as a probability would have to be re-tuned by hand every time a published
    rate moved, and the marginals would silently stop matching in between.
    """

    name: str
    base_weight: float
    affinity: dict[str, float]
    default_affinity: float = 1.0

    def affinity_for(self, condition: str) -> float:
        return self.affinity.get(condition, self.default_affinity)


HEALTH_ARCHETYPES: dict[str, HealthArchetype] = {
    "resilient": HealthArchetype(
        name="resilient",
        base_weight=0.36,
        affinity={},
        default_affinity=0.85,
    ),
    "metabolic": HealthArchetype(
        name="metabolic",
        base_weight=0.20,
        affinity={
            "diabetes": 2.40,
            "hypertension": 1.77,
            "knee_cartilage_defect": 1.21,
            "lumbar_disc_degeneration": 1.11,
            "depression_anxiety": 1.04,
        },
        default_affinity=0.93,
    ),
    "degenerative": HealthArchetype(
        name="degenerative",
        base_weight=0.22,
        affinity={
            "lumbar_disc_degeneration": 1.56,
            "lumbar_facet_arthropathy": 1.56,
            "cervical_disc_bulge": 1.42,
            "rotator_cuff_tear": 1.49,
            "knee_cartilage_defect": 1.49,
            "hip_labral_tear": 1.42,
            "osteoporosis": 1.28,
        },
        default_affinity=0.86,
    ),
    "psych_burdened": HealthArchetype(
        name="psych_burdened",
        base_weight=0.12,
        affinity={"depression_anxiety": 2.19},
        default_affinity=0.97,
    ),
    "multimorbid": HealthArchetype(
        name="multimorbid",
        base_weight=0.10,
        affinity={},
        default_affinity=2.00,
    ),
}
"""Five profiles, tuned for correlation rather than for level.

Level is the calibration's job. What these numbers decide is which conditions travel
*together* — a metabolic applicant's diabetes and hypertension arriving as a pair, a
degenerative applicant's findings clustering in the musculoskeletal system — and
therefore how far the aggregate "has at least one condition" rate sits below the naive
independent product.

**The spread is deliberately narrower than it first shipped, and the reason is the
anti-fingerprint bound.** The first table ran ``resilient`` at 0.22 against
``multimorbid`` at 2.8 — nearly a thirteenfold spread — which made a *sparse* condition
set almost conclusive: on a cervical-plus-wrist claim, "cervical disc bulge and nothing
else" came back ``resilient`` in 634 of 641 cases, a posterior of 0.989. Review found
it by conditioning the posterior on the claim's own body parts, which is the right way
round: **body parts are visible on the face of the file**, so an observer never has to
average over claim shapes the way the pooled measurement did.

Compressing toward 1.0 costs correlation and buys separability, and that trade is the
honest one to make here: an archetype that can be *read off* the conditions is not a
latent profile at all. The aggregate rose from 0.71 to about 0.76 as a result, which is
the visible price and is pinned in ``P_ANY_CONDITION_MEASURED``.

``resilient`` still carries the largest single share, because without a substantial
genuinely-healthy mass every synthetic applicant is comorbid and the corpus stops
looking like a caseload.
"""

#: How demographics steer archetype membership. Multiplicative on the base weight.
#:
#: This is the *correlation* half of the risk story: an obese applicant is made more
#: likely to be metabolic, and the metabolic profile's taste for diabetes and
#: hypertension then makes those two arrive together. What it deliberately does **not**
#: carry is per-condition dose-response — steering cannot express that knee cartilage
#: responds to body mass more steeply than a lumbar disc does, because an archetype
#: shifts every one of its conditions at once. That is
#: :data:`~wc_caseload_engine.clinical_grounding.RISK_MULTIPLIERS`' job, and the two
#: mechanisms are kept apart because they answer different questions.
_BMI_STEER: dict[str, dict[str, float]] = {
    "normal_or_under": {"resilient": 1.35, "metabolic": 0.55, "multimorbid": 0.6},
    "overweight": {"resilient": 1.0, "metabolic": 1.0, "multimorbid": 1.0},
    "obese": {"resilient": 0.6, "metabolic": 2.0, "multimorbid": 1.6},
    "severely_obese": {"resilient": 0.35, "metabolic": 2.6, "multimorbid": 2.4},
}

_SMOKING_STEER: dict[str, dict[str, float]] = {
    "never": {"resilient": 1.15, "multimorbid": 0.85},
    "former": {"resilient": 1.0, "multimorbid": 1.0},
    "current": {"resilient": 0.7, "multimorbid": 1.5, "psych_burdened": 1.3},
}

_AGE_STEER: tuple[tuple[int, dict[str, float]], ...] = (
    (35, {"resilient": 1.5, "degenerative": 0.5, "multimorbid": 0.5}),
    (50, {"resilient": 1.1, "degenerative": 0.9}),
    (65, {"resilient": 0.75, "degenerative": 1.4, "multimorbid": 1.3}),
    (200, {"resilient": 0.5, "degenerative": 1.8, "multimorbid": 1.7}),
)
"""``(exclusive upper age, multipliers)``, first match wins. Age is the dominant risk
factor for every degenerative finding in the catalog, so it steers hardest."""

#: Per-archetype probabilities are clamped here and never reach 0 or 1.
#:
#: The lower bound is the anti-fingerprint guarantee: an archetype with a zero
#: probability for some condition could be *excluded* by observing that condition,
#: and a chain of such exclusions is exactly how profile membership becomes
#: recoverable. It also has to sit below the smallest published rate the sampler must
#: reproduce — diabetes at 18-34 is 0.013 — or that target becomes unreachable.
_P_FLOOR = 0.005
_P_CEILING = 0.995


def _steer(base: dict[str, float], multipliers: dict[str, float]) -> dict[str, float]:
    return {name: weight * multipliers.get(name, 1.0) for name, weight in base.items()}


def archetype_weights(
    age: int, bmi_band: str, smoking_status: str
) -> dict[str, float]:
    """The archetype mixture for one applicant. Sums to 1.

    Sex is deliberately not a steer. Where the literature reports a sex difference it
    is reported *in the prevalence table itself* — hypertension at 40-59, facet
    arthropathy at every band — so the calibration already carries it. Steering the
    mixture on sex as well would apply the same published difference twice.
    """
    weights = {name: arch.base_weight for name, arch in HEALTH_ARCHETYPES.items()}
    for upper, multipliers in _AGE_STEER:
        if age < upper:
            weights = _steer(weights, multipliers)
            break
    weights = _steer(weights, _BMI_STEER[bmi_band])
    weights = _steer(weights, _SMOKING_STEER[smoking_status])
    total = sum(weights.values())
    return {name: weight / total for name, weight in weights.items()}


def _clamped(probability: float) -> float:
    """The floor and ceiling, and nothing else.

    Separated from the gradient so the two cannot be confused again. The clamp is the
    anti-fingerprint guarantee — no archetype probability ever reaches 0 or 1 — and it
    is applied last, after the odds-scale transform, so it bounds the number that is
    actually used.
    """
    return min(_P_CEILING, max(_P_FLOOR, probability))


def _logistic(log_odds: float) -> float:
    """The inverse logit, written to survive large magnitudes without overflowing."""
    if log_odds >= 0.0:
        return 1.0 / (1.0 + math.exp(-log_odds))
    exponential = math.exp(log_odds)
    return exponential / (1.0 + exponential)


def _baseline(intercept: float, affinity: float) -> float:
    """One archetype's pre-gradient probability. **Strictly inside (0, 1).**

    This is the correction the second review round forced, and the bug it fixes was
    hiding in plain sight. The calibrated quantity used to be a *multiplicative scale*
    and the baseline was ``scale * affinity`` — a product of two unbounded positives,
    handed to a transform whose whole derivation assumes it receives a probability.
    An exhaustive sweep found 907 cells where it did not: at age 55 the multimorbid
    archetype's lumbar baseline came out at 1.231, and once a "probability" exceeds 1
    the odds transform has no meaning left to preserve. All four BMI bands clamped to
    0.995 and the published 1.79 gradient vanished — in the one profile where the
    condition is most likely, which is where a reader would look for it.

    So the calibrated quantity is now a logistic **intercept**, and the archetype
    affinity enters as an odds ratio on the log-odds scale. Across every intercept a
    calibrated solve produces, this is strictly inside ``(0, 1)`` — structurally,
    rather than by a sweep that happens to find no counterexample today.

    **Strictly, over production intercepts — not over every float.** ``_logistic``
    saturates: ``sigmoid(38)`` is exactly 1.0 in float64 and the intercept search
    brackets ±40, so at the search bounds the open interval is held by the final
    ``_clamped`` rather than by the link. The two are not redundant, and saying the
    link "cannot leave (0, 1)" was an overstatement this module's own boundary test
    disproves.
    """
    return _logistic(intercept + math.log(affinity))


def _graded(intercept: float, affinity: float, condition: str, bmi: str, smoking: str) -> float:
    """One archetype's probability in one cell: baseline, graded on odds, clamped.

    Three steps, in an order that is load-bearing. :func:`_baseline` produces a real
    probability; the gradient then moves it **on the odds scale**, because that is
    what an odds ratio is a ratio of — multiplying the probability instead overstates
    the effect wherever the baseline is large, and these conditions are common. The
    clamp comes last and bounds the number actually used.

    Because log-odds add, this is one linear predictor:
    ``logit(p) = intercept + log(affinity) + log(OR_bmi) + log(OR_smoking)``. Written
    as a composition rather than a sum so that :meth:`RiskGradient.apply` stays the
    single place the odds transform lives.
    """
    return _clamped(
        RISK_MULTIPLIERS[condition].apply(_baseline(intercept, affinity), bmi, smoking)
    )


def _cell_rate(intercept: float, condition: str, age: int, bmi: str, smoking: str) -> float:
    """The mixture rate for one demographic cell at a given intercept."""
    return sum(
        weight
        * _graded(
            intercept,
            HEALTH_ARCHETYPES[name].affinity_for(condition),
            condition,
            bmi,
            smoking,
        )
        for name, weight in archetype_weights(age, bmi, smoking).items()
    )


def _population_rate(intercept: float, condition: str, age: int) -> float:
    """The rate across the whole (BMI x smoking) population at a given intercept.

    The integral the calibration has to hit. Every cell contributes at its own
    multiplier, weighted by how common that cell is at this age, so a gradient can be
    steep and the aggregate can still land on its citation.
    """
    smoking_weights = {status: knob.value for status, knob in SMOKING_DISTRIBUTION.items()}
    return sum(
        bmi_share * smoking_share * _cell_rate(intercept, condition, age, bmi, smoking)
        for bmi, bmi_share in bmi_distribution(age).items()
        for smoking, smoking_share in smoking_weights.items()
    )


#: How far the intercept search may run before the target is declared unreachable.
#:
#: A logit of ±40 is a probability of about 4e-18 and its complement, so the bracket
#: is wider than any published rate could need by many orders of magnitude. Finite
#: rather than "grow until it works" because an unbounded search on a monotone
#: function that has plateaued is an infinite loop with extra steps.
_INTERCEPT_BOUND = 40.0


@cache
def calibrate(condition: str, age: int, target: float) -> float:
    """The one logistic **intercept** at which the *population* reproduces *target*.

    Solved once per (condition, age) — **not** once per demographic cell, and that is
    the whole point of this function's shape. Per-cell was the first version, and it
    silently cancelled every risk gradient: each cell hit the age/sex marginal exactly,
    so a severely obese current smoker and a normal-weight never-smoker came out with
    identical diabetes risk, and ``bmi_band`` became a field that was drawn, stored and
    never consulted. Review caught it. The fix is to pin the *aggregate* and let the
    cells differ underneath it.

    **An intercept rather than a multiplicative scale**, which is the second review
    round's correction. A scale times an affinity is an unbounded positive number, and
    it was being handed to the odds transform as though it were a probability: 907
    cells came out above 1, and there the gradient could not be expressed at all. A
    logistic link makes every baseline a probability by construction, so the argument
    for correctness stops depending on a sweep finding no counterexample.

    Bisection rather than an analytic inverse: the clamp puts a kink in every
    archetype's contribution and the closed form is a case analysis nobody would want
    to maintain. The population rate is monotone non-decreasing in the intercept, so
    bisection is exact to tolerance with no local minima to fall into.

    Raises:
        ValueError: when *target* lies outside what the bounds can express — a
            published rate the floor or ceiling cannot reach. Clamping silently would
            leave a marginal wrong by an amount nothing reports.
    """
    if not _P_FLOOR <= target <= _P_CEILING:
        raise ValueError(
            f"{condition}: published rate {target} lies outside the archetype "
            f"probability bounds [{_P_FLOOR}, {_P_CEILING}], so no intercept "
            "reproduces it; widen the bounds deliberately rather than accepting a "
            "marginal that misses its own source"
        )
    low, high = -_INTERCEPT_BOUND, _INTERCEPT_BOUND
    if _population_rate(high, condition, age) < target:  # pragma: no cover - bounds check
        raise ValueError(
            f"{condition}: target {target} is unreachable at age {age} even at the "
            f"widest intercept the search admits ({_INTERCEPT_BOUND})"
        )
    for _ in range(200):
        middle = (low + high) / 2.0
        if _population_rate(middle, condition, age) < target:
            low = middle
        else:
            high = middle
    return (low + high) / 2.0


@cache
def condition_probabilities(
    condition: str, age: int, sex: str, bmi_band: str, smoking_status: str
) -> tuple[tuple[str, float], ...]:
    """``(archetype, probability)`` for one condition and one applicant.

    Two mechanisms shape this number, and they do different jobs — which is why both
    exist rather than one standing in for the other:

    * the **archetype mixture** carries correlation *between* conditions, so a
      metabolic applicant's diabetes and hypertension arrive together;
    * the **risk gradient** carries dose-response *within* one condition, at the
      magnitude its own source reports, and on the **odds scale**. Nothing about
      archetype membership can express that knee cartilage responds to body mass more
      steeply (OR 2.63) than a lumbar disc does (OR 1.79); only a per-condition odds
      ratio can.

    Memoised because the solve is pure in its arguments and a cohort of any size
    revisits the same few thousand cells. Purity is also what keeps this
    cross-process deterministic: the cache is an optimisation, never state that could
    differ between two runs.
    """
    citation = age_band_rate(condition, age, sex)
    if citation is None:
        return ()
    intercept = calibrate(condition, age, citation.value)
    return tuple(
        (
            name,
            _graded(
                intercept,
                HEALTH_ARCHETYPES[name].affinity_for(condition),
                condition,
                bmi_band,
                smoking_status,
            ),
        )
        for name in sorted(archetype_weights(age, bmi_band, smoking_status))
    )


def eligible_conditions(body_parts: frozenset[str]) -> tuple[str, ...]:
    """Catalog keys a claim over *body_parts* can carry, in catalog order.

    A degenerative finding is gated on the claim naming its region, and the gate is
    about evidence rather than biology: a lumbar disc finding in a wrist claim is real
    in the applicant, but nobody imaged the lumbar spine, so it is not a fact this
    file could ever contain. Systemic conditions are eligible for every case.
    """
    return tuple(
        key
        for key, spec in CONDITION_CATALOG.items()
        if spec.systemic or set(spec.body_parts) & body_parts
    )


def probability_of_any_condition(
    age: int, sex: str, bmi_band: str, smoking_status: str, body_parts: frozenset[str]
) -> float:
    """P(at least one sampled condition), computed rather than measured.

    Analytic on purpose. The documentation gate below divides by this number to hold
    the counsel-confirmed surfacing union, and estimating it from the cohort would
    make the gate depend on the corpus it is generating.
    """
    weights = archetype_weights(age, bmi_band, smoking_status)
    keys = eligible_conditions(body_parts)
    none_at_all = 0.0
    for name, weight in weights.items():
        product = 1.0
        for key in keys:
            probabilities = dict(
                condition_probabilities(key, age, sex, bmi_band, smoking_status)
            )
            product *= 1.0 - probabilities.get(name, 0.0)
        none_at_all += weight * product
    return 1.0 - none_at_all


# ---------------------------------------------------------------------------
# Derivation knobs with no source
# ---------------------------------------------------------------------------

SEVERITY_WEIGHTS: dict[str, dict[str, float]] = {
    "incidental": {"subclinical": 0.34, "mild": 0.38, "moderate": 0.21, "severe": 0.07},
    "managed": {"subclinical": 0.05, "mild": 0.42, "moderate": 0.39, "severe": 0.14},
}
"""Severity mix, by whether the source measured an incidental finding or a diagnosis.

Both rows are **invented**. No source in note C or note F grades severity at all, and
saying so is cheaper than a number that reads as measured. The split between the two
rows is the part that is *reasoned*: a finding drawn from an asymptomatic-population
table is by construction incidental, so weighting it toward ``subclinical`` follows
from what the study measured rather than from a preference.

Interview: for the preexisting conditions you actually see argued, how severe are
they typically — incidental findings, managed-but-real, or genuinely disabling?
"""

TRAJECTORY_WEIGHTS: dict[str, dict[str, float]] = {
    "incidental": {"stable": 0.55, "progressive": 0.38, "fluctuating": 0.07},
    "managed": {"stable": 0.48, "progressive": 0.30, "fluctuating": 0.22},
}
"""Trajectory mix. **Invented**, same absence of a source as severity.

``resolved`` is deliberately absent from both rows rather than given a small weight: a
resolved condition is not a live apportionment factor, and a corpus that produced them
at any rate would be inviting an assertion layer to apportion to something that is
over. M2 revisits this when the assertion layer needs the resolved case.
"""

ONSET_YEARS_BEFORE_INJURY: Knob = Knob(
    value=8.0,
    tag="invented",
    rationale=(
        "Mean years between a managed systemic condition's onset and the industrial "
        "injury, drawn over 1-20 years. No source dates comorbidity onset relative to "
        "a claim. Incidental findings get no onset at all rather than a drawn one — "
        "see MedicalCondition.onset."
    ),
    source=(
        "Interview: when a preexisting condition is documented, how far back does the "
        "record usually reach — a year or two, or a decade?"
    ),
)


def _weighted(rng: random.Random, weights: dict[str, float]) -> str:
    """One key, drawn in sorted order so the draw does not depend on dict order."""
    keys = sorted(weights)
    return rng.choices(keys, weights=[weights[k] for k in keys], k=1)[0]


# ---------------------------------------------------------------------------
# Demographic draw
# ---------------------------------------------------------------------------


def _draw_bmi_band(rng: random.Random, age: int) -> str:
    """A BMI band from :func:`bmi_band_for_draw` — the *same* definition the
    calibration integrates over.

    It used to be a second, hand-written expression of that arithmetic, and the two
    drifted exactly where a second expression always drifts: at the edge nobody
    exercised. CDC's obesity series starts at 20 and the schema admits applicants from
    16. ``bmi_distribution`` handles that by reusing the youngest reported band, an
    extrapolation it names; this function turned the same missing citation into
    ``obese_share = 0.0`` and drew *nobody* obese. So for four birth years the
    calibration integrated over a 35.5%-obese population that the sampler never drew,
    and an age-18 male's hypertension came out at 0.239 against a cited 0.300.

    The fix is not a better fallback here — it is having no second definition to keep
    in step. The first attempt at that fix walked a cumulative sum of the shares, which
    is the obvious way to write an inverse CDF and reintroduced the same class of
    defect one layer down: ``severe + (obese - severe)`` is not ``obese`` in floating
    point. The classifier now owns the comparison chain and the distribution derives
    its shares from the classifier's own cutoffs.
    """
    return bmi_band_for_draw(rng.random(), age)


def derive_demographics(seed: CaseSeed, date_of_birth: dt.date) -> ApplicantDemographics:
    """Resolve the applicant's demographics: seed first, derivation for the rest.

    ``date_of_birth`` is passed in rather than recomputed. The cast already owns that
    field and already derives it against ``ANCHOR_DATE``; deriving a second copy here
    is how the ledger and the documents would come to disagree about the applicant's
    age, which is the class of defect the whole ledger pattern exists to remove.
    """
    applicant = seed.profile.applicant
    age = _years_between(date_of_birth, ANCHOR_DATE)

    sex = applicant.sex
    if sex is None:
        sex = "female" if _rng(seed, "sex").random() < FEMALE_SHARE.value else "male"

    bmi_band = applicant.bmi_band
    if bmi_band is None:
        bmi_band = _draw_bmi_band(_rng(seed, "bmi"), age)

    smoking_status = applicant.smoking_status
    if smoking_status is None:
        smoking_status = _weighted(
            _rng(seed, "smoking"),
            {status: knob.value for status, knob in SMOKING_DISTRIBUTION.items()},
        )

    return ApplicantDemographics(
        age=age, sex=sex, bmi_band=bmi_band, smoking_status=smoking_status
    )


def _years_between(born: dt.date, on: dt.date) -> int:
    """Whole years, never through a wall clock. ``ANCHOR_DATE`` is 'today' here."""
    return on.year - born.year - ((on.month, on.day) < (born.month, born.day))


# ---------------------------------------------------------------------------
# Condition draw
# ---------------------------------------------------------------------------


def _condition_from_catalog(
    key: str,
    index: int,
    injured: frozenset[str],
    injury_date: dt.date,
    rng: random.Random,
) -> MedicalCondition:
    spec = CONDITION_CATALOG[key]
    flavour = "incidental" if spec.asymptomatic_source else "managed"
    overlap = set(spec.apportionment_targets) & injured
    onset: dt.date | None = None
    if not spec.asymptomatic_source:
        years = rng.randint(1, int(ONSET_YEARS_BEFORE_INJURY.value * 2) + 4)
        onset = injury_date - dt.timedelta(days=int(years * 365.25))
    return MedicalCondition(
        id=f"cond-{index:02d}",
        key=key,
        label=spec.label,
        body_system=spec.body_system,
        body_part=next(iter(sorted(overlap)), None) if spec.body_parts else None,
        icd10=spec.icd10,
        onset=onset,
        causal_ground_truth="nonindustrial",
        wholly_unrelated=not overlap,
        severity=_weighted(rng, SEVERITY_WEIGHTS[flavour]),
        trajectory=_weighted(rng, TRAJECTORY_WEIGHTS[flavour]),
        symptomatic_before_doi=not spec.asymptomatic_source,
    )


@cache
def reference_age_weights() -> dict[int, float]:
    """``P(age)`` under the cast's *actual* date-of-birth law, computed exactly.

    Not uniform on ``DERIVED_AGE_RANGE``, and assuming it was cost a fifth decimal
    place. The draw is ``randint(low*365, high*365) + randint(0, 364)`` days before
    ``ANCHOR_DATE``, so three things happen that a flat table misses: the two uniforms
    convolve into a **trapezoid** rather than a rectangle, a 365-day year against a
    calendar containing leap days drags a small tail onto ``low - 1``, and the
    endpoints carry roughly half the weight of an interior year.

    Derived rather than sampled, and derived from the *same* law
    ``case_context._date_of_birth`` executes — the cast draw itself is deliberately
    untouched, because it is golden-sensitive and there is nothing wrong with it. What
    was wrong was this module's description of it.

    The convolution is closed-form: for a total offset ``d``, the number of
    ``(coarse, fine)`` pairs producing it is the overlap of ``[low, high]`` with
    ``[d - 364, d]``. That is one pass over ~14k offsets instead of 4.9M pairs.
    """
    low, high = DERIVED_AGE_RANGE
    coarse_low, coarse_high = low * 365, high * 365
    counts: dict[int, int] = {}
    total_pairs = 0
    for offset in range(coarse_low, coarse_high + 365):
        overlap_low = max(coarse_low, offset - 364)
        overlap_high = min(coarse_high, offset)
        if overlap_high < overlap_low:
            continue  # pragma: no cover - the range above cannot produce this
        pairs = overlap_high - overlap_low + 1
        born = ANCHOR_DATE - dt.timedelta(days=offset)
        age = _years_between(born, ANCHOR_DATE)
        counts[age] = counts.get(age, 0) + pairs
        total_pairs += pairs
    return {age: pairs / total_pairs for age, pairs in sorted(counts.items())}


@cache
def expected_any_condition() -> float:
    """``E[P(at least one condition)]`` over the reference population.

    Analytic, not sampled: :func:`probability_of_any_condition` is exact for a cell, so
    the expectation is a weighted sum over :func:`reference_age_weights`, sex, the
    age's own BMI distribution, the smoking table and
    :data:`~wc_caseload_engine.clinical_grounding.REFERENCE_CLAIM_SHAPES`. Cached
    because it is a constant of the tables, and pure in the way the rest of this module
    is pure — no rng, no clock, no corpus.

    The age weights are the *exact* law rather than a uniform stand-in. The difference
    is small — 0.771010 against 0.771068 — and the reason to care is not the fifth
    decimal but the claim attached to it: an identity asserted at 1e-12 against an
    approximate population is an identity about the approximation, and the surrounding
    comments said "the generation population".
    """
    female = FEMALE_SHARE.value
    sex_weights = {"female": female, "male": 1.0 - female}
    smoking_weights = {status: knob.value for status, knob in SMOKING_DISTRIBUTION.items()}
    shape_weights = {shape: knob.value for shape, knob in REFERENCE_CLAIM_SHAPES.items()}

    total = 0.0
    for age, age_weight in reference_age_weights().items():
        bmi_weights = bmi_distribution(age)
        for sex, sex_share in sex_weights.items():
            for bmi, bmi_share in bmi_weights.items():
                for smoking, smoking_share in smoking_weights.items():
                    for shape, shape_share in shape_weights.items():
                        weight = (
                            age_weight * sex_share * bmi_share * smoking_share * shape_share
                        )
                        total += weight * probability_of_any_condition(
                            age, sex, bmi, smoking, frozenset(shape)
                        )
    return total


@cache
def surfacing_conditional() -> float:
    """``P(surfaces | has a condition)`` — **one constant for the whole corpus**.

    The corrected form of a gate that could not reach its own target. It used to divide
    each applicant's own ``P(any)`` into the union and cap at 1, which makes that
    applicant's *unconditional* surfacing rate ``min(P_any, target)``. Every applicant
    below the target therefore contributed less than the target and **nothing
    contributed more**, because the cap is one-sided. The aggregate landed at about
    0.484 against a target of 0.50 — an error of the same order as the ±0.02 sampled
    tolerance that was supposed to be watching it, which is why it survived a round.

    A single conditional rate fixes it exactly rather than approximately. Each cell
    surfaces at ``P_any(cell) * q``, so the expectation is ``E[P_any] * q``, and setting
    ``q = target / E[P_any]`` makes that identically the target. No cap is needed
    because ``q`` is a constant below 1, so no cell is truncated and no cell has to
    compensate for another.

    It also says something truer about a file: an applicant carrying more conditions is
    *more* likely to have one documented, in proportion to how much there is to
    document. The per-applicant form flattened exactly that away at the top end.

    Raises:
        ValueError: if the target exceeds the reference population's own ``E[P(any)]``,
            which would demand more documented applicants than there are applicants
            with anything to document. Unreachable with the current tables — asserted
            rather than assumed, because it is the one way this can silently cap again.
    """
    expected = expected_any_condition()
    conditional = P_SURFACES_IN_FILE.value / expected
    if conditional > 1.0:
        raise ValueError(
            f"the surfacing union {P_SURFACES_IN_FILE.value} exceeds the reference "
            f"population's own P(any condition) of {expected:.4f}; no conditional rate "
            "can document more applicants than have something to document"
        )
    return conditional


@cache
def billing_conditional() -> float:
    """``P(billing-coded | surfaces)`` — the floor, calibrated the same way."""
    surfaces = P_SURFACES_IN_FILE.value
    if surfaces <= 0.0:  # pragma: no cover - the knob is a positive rate
        return 0.0
    return min(1.0, P_BILLING_CODED.value / surfaces)


def _apply_documentation_gate(
    conditions: list[MedicalCondition],
    p_any: float,
    rng: random.Random,
) -> list[MedicalCondition]:
    """Set ``surfaces_in_file`` and ``billing_coded`` to hold the two published unions.

    The arithmetic is counsel's own, generalised from a caseload to a case — and the
    generalisation is the part that had to be redone. Counsel's rate is an
    *applicant-level* expectation **across a caseload**, so it is held in expectation
    over the reference population rather than inside each applicant. See
    :func:`surfacing_conditional` for why the per-applicant form could not attain it.

    The rates are read from the knobs rather than written into this docstring on
    purpose: counsel revised the surfacing union from 0.33 to 0.50 on 2026-08-10, and a
    number spelled out in three places is a number that will be revised in two of them.

    Within a case that does surface something, each condition draws at
    ``1 - (1 - q)**(1/n)``, which makes P(at least one) equal ``q`` for *every* n. A
    flat per-condition rate would make the union climb with the count, so a file with
    five comorbidities would document five times as much as a file with one — which is
    not how a file works. Its appetite is roughly constant.

    ``billing_coded`` is drawn only among conditions that already surface, because the
    measured 6.6% is a floor *inside* the surfacing union rather than a competing
    figure. The NCCI figure did not move when counsel's estimate did, and it should
    not: one is a measurement of billing records, the other an expert's estimate of
    what a file mentions.
    """
    if not conditions or p_any <= 0.0:
        return conditions
    q_surface = surfacing_conditional()
    if rng.random() >= q_surface:
        return conditions

    count = len(conditions)
    per_condition = 1.0 - (1.0 - q_surface) ** (1.0 / count)
    surfaced = [index for index in range(count) if rng.random() < per_condition]
    if not surfaced:
        surfaced = [rng.randrange(count)]

    share = billing_conditional()
    per_surfaced = 1.0 - (1.0 - share) ** (1.0 / len(surfaced))

    out = list(conditions)
    for index in surfaced:
        coded = rng.random() < per_surfaced
        out[index] = out[index].model_copy(
            update={"surfaces_in_file": True, "billing_coded": coded}
        )
    return out


def sample_conditions(
    seed: CaseSeed,
    demographics: ApplicantDemographics,
    injured: frozenset[str],
    injury_date: dt.date,
    archetype: str,
    first_index: int,
) -> list[MedicalCondition]:
    """Draw this applicant's conditions from their archetype.

    One stream, consumed in catalog order, so the draw does not depend on which
    conditions happened to be eligible — a case whose eligible set differs by one
    entry must not re-roll every other condition it shares with its neighbour.
    """
    rng = _rng(seed, "conditions")
    detail = _rng(seed, "condition_detail")
    drawn: list[MedicalCondition] = []
    for key in eligible_conditions(injured):
        probabilities = dict(
            condition_probabilities(
                key,
                demographics.age,
                demographics.sex,
                demographics.bmi_band,
                demographics.smoking_status,
            )
        )
        if rng.random() >= probabilities.get(archetype, 0.0):
            continue
        drawn.append(
            _condition_from_catalog(
                key, first_index + len(drawn), injured, injury_date, detail
            )
        )
    p_any = probability_of_any_condition(
        demographics.age,
        demographics.sex,
        demographics.bmi_band,
        demographics.smoking_status,
        injured,
    )
    return _apply_documentation_gate(drawn, p_any, _rng(seed, "documentation"))


def draw_archetype(seed: CaseSeed, demographics: ApplicantDemographics) -> str:
    """The applicant's health profile, drawn from the demographic mixture."""
    weights = archetype_weights(
        demographics.age, demographics.bmi_band, demographics.smoking_status
    )
    return _weighted(_rng(seed, "archetype"), weights)


def _condition_from_entry(entry: Any, index: int, injured: frozenset[str]) -> MedicalCondition:
    """One author-stated condition. The seed wins on every field it states.

    ``wholly_unrelated`` is the one field that may be left open, because an author
    naming a catalog condition should not have to work out whether it overlaps this
    claim's regions — the catalog already knows. Stating it explicitly is what the
    flagship wholly-unrelated story needs (a breast cancer in a lumbar claim has no
    catalog row at all), so both routes stay available.
    """
    spec = CONDITION_CATALOG.get(entry.key) if entry.key else None
    if entry.wholly_unrelated is not None:
        unrelated = entry.wholly_unrelated
    elif spec is not None:
        unrelated = not (set(spec.apportionment_targets) & injured)
    else:
        unrelated = entry.body_part not in injured
    return MedicalCondition(
        id=f"cond-{index:02d}",
        key=entry.key or "seeded",
        label=entry.label,
        body_system=entry.body_system,
        body_part=entry.body_part,
        icd10=entry.icd10 or (spec.icd10 if spec else None),
        onset=entry.onset,
        causal_ground_truth=entry.origin,
        wholly_unrelated=unrelated,
        severity=entry.severity,
        trajectory=entry.trajectory,
        symptomatic_before_doi=entry.symptomatic_before_doi,
        billing_coded=entry.billing_coded,
        surfaces_in_file=entry.surfaces_in_file or entry.billing_coded,
    )


#: Section 4664(b)'s presumption default, keyed by the *resolved* award
#: resolution. Counsel resolved §2-Q7 on 2026-08-10: "No - only a stip" — a
#: compromise and release never presumes; a stipulated award does; a prior
#: findings-and-award also presumes (counsel-assumed, micro-confirm at M5 spec).
#: This supplies only the DEFAULT: an explicit seed ``conclusively_presumed``
#: always wins, including when it differs from its own resolution's default,
#: because an authored override is an authored fact rather than incoherence.
PRESUMPTION_DEFAULT_BY_RESOLUTION: Final[dict[str, bool]] = {
    "c_and_r": False,
    "findings_and_award": True,
    "stipulated_award": True,
}


def _claim_from_entry(entry: Any, index: int) -> PriorClaim:
    award = None
    if entry.award is not None:
        # ``None`` on the seed means "the claim's own", which the seed schema has
        # already checked is a resolution capable of producing an award. The
        # ledger carries the resolved value so no consumer has to know that.
        resolved_award_resolution_type = (
            entry.award.resolution_type or entry.resolution_type
        )
        effective_conclusively_presumed = (
            entry.award.conclusively_presumed
            if entry.award.conclusively_presumed is not None
            else PRESUMPTION_DEFAULT_BY_RESOLUTION[resolved_award_resolution_type]
        )
        award = PriorAward(
            id=f"prior-{index:02d}-award",
            body_parts=tuple(entry.award.body_parts),
            pd_percent=entry.award.pd_percent,
            award_date=entry.award.award_date,
            resolution_type=resolved_award_resolution_type,
            still_exists_conclusively_presumed=effective_conclusively_presumed,
        )
    return PriorClaim(
        id=f"prior-{index:02d}",
        body_parts=tuple(entry.body_parts),
        date_of_injury=entry.date_of_injury,
        employer=entry.employer,
        resolution_type=entry.resolution_type,
        resolution_date=entry.resolution_date,
        award=award,
    )


def derive_medical_history(
    seed: CaseSeed, timeline: Any = None, date_of_birth: dt.date | None = None
) -> MedicalHistory | None:
    """The world-truth ledger for one case, or ``None`` when the seed asked for none.

    ``None`` rather than an empty :class:`MedicalHistory`, and the distinction is the
    whole back-compat instrument. A present-but-empty ledger and an absent one would
    be indistinguishable downstream, and everything M1 claims rests on the engine
    being able to tell "the author asked for a medical-history layer" from "the author
    said nothing" — the same sentence ``scenario.wages`` is built on, for the same
    reason.

    Deliberately *not* auto-derived when absent, unlike ``scenario.diagnostics``.
    Diagnostics auto-derives because templates were already drawing imaging
    independently and the ledger's job was to make existing behaviour coherent.
    Nothing today derives comorbidities for any case, so auto-deriving them would
    silently start populating history into every case in the demo caseload and every
    golden fixture — precisely the uncontrolled blast radius the wages gate exists to
    prevent.
    """
    scenario = seed.scenario.medical_history
    if scenario is None:
        return None

    if date_of_birth is None:
        from wc_caseload_engine.case_context import applicant_date_of_birth

        date_of_birth = applicant_date_of_birth(seed)
    demographics = derive_demographics(seed, date_of_birth)
    archetype = scenario.archetype or draw_archetype(seed, demographics)

    injured = frozenset(part.part for part in seed.injury.body_parts)
    injury_date = getattr(timeline, "injury_date", None) or seed.injury.onset_date

    conditions = [
        _condition_from_entry(entry, index, injured)
        for index, entry in enumerate(scenario.conditions)
    ]
    stated = {c.key for c in conditions if c.key != "seeded"}
    if scenario.sample_conditions:
        conditions.extend(
            condition
            for condition in sample_conditions(
                seed, demographics, injured, injury_date, archetype, len(conditions)
            )
            # An author who states a condition has decided it; a draw does not get
            # to state it again under a second id and make the ledger hold two
            # facts about one thing.
            if condition.key not in stated
        )

    prior_claims = tuple(
        _claim_from_entry(entry, index) for index, entry in enumerate(scenario.prior_claims)
    )

    history = MedicalHistory(
        demographics=demographics,
        archetype=archetype,
        conditions=tuple(conditions),
        prior_claims=prior_claims,
    )
    log.debug(
        "medical_history.derived",
        case_id=seed.case_id,
        archetype=archetype,
        conditions=len(history.conditions),
        surfaced=len(history.surfaced_conditions()),
        prior_claims=len(history.prior_claims),
    )
    return history


# ---------------------------------------------------------------------------
# The grounding warnings — explicit control wins, loudly
# ---------------------------------------------------------------------------

#: Doctrine hooks whose argument needs a concrete entity this ledger can hold.
#:
#: Read against a medical-history block that *exists*: a seed with no block at all is
#: silent here, and has to be. "Absent moves zero bytes" is M1's whole back-compat
#: claim, and a warning is a manifest byte. So this speaks only to an author who
#: opened the layer and then left the entity the hook argues about out of it — which
#: is an authoring mistake worth naming, and the only one this milestone can see.
@dataclass(frozen=True)
class SibtfClause:
    """One way the ledger can evidence a pre-existing permanent disability.

    A predicate and the sentence that describes it, kept in one object because the
    two came apart last time they were kept in two.
    """

    name: str
    remediation: str
    holds: Callable[[MedicalHistory], bool]


#: The disability grades that count as "labor disabling" for §4751 purposes.
#:
#: ``subclinical`` and ``mild`` were excluded from the start, because every degenerative
#: finding in the catalog is drawn from a study of *asymptomatic* people — that is what
#: those prevalence tables measured — so a predicate accepting any predating finding
#: would ground SIBTF on roughly half the corpus and mean nothing.
#:
#: ``moderate`` was excluded later, on counsel's ruling that the moderate-or-worse line
#: was **too loose** [counsel-confirmed 2026-08-10]. It is worth being precise about
#: what that ruling settles and what it does not. **The direction is confirmed**: the
#: bar sits higher than "moderate". **The threshold is not** — §4751 speaks of a
#: pre-existing permanent partial disability the Fund could be liable for, and where
#: exactly that lands against this module's four-grade vocabulary is an **open counsel
#: item for M2** [counsel-unconfirmed]. Severe is the conservative reading of a
#: confirmed direction, which is the right way to be wrong here: the cost of being too
#: strict is a warning that fires when it need not, and the cost of being too loose is
#: a doctrine hook standing on evidence that does not support it.
SIBTF_DISABLING_SEVERITIES: frozenset[str] = frozenset({"severe"})


#: Trajectories a §4751 disability can still be running on at the date of injury.
#:
#: ``resolved`` is excluded, and the exclusion is not a technicality. This module defines
#: a resolved condition as one that is no longer a live factor; §4751 asks whether a
#: pre-existing disability *combines* with the new injury to produce a greater one. A
#: factor that has stopped operating cannot combine with anything, so a severe
#: condition that resolved before the injury grounds no more than no condition at all.
SIBTF_LIVE_TRAJECTORIES: frozenset[str] = frozenset(
    {"stable", "progressive", "fluctuating"}
)


def _has_qualifying_condition(history: MedicalHistory) -> bool:
    return any(
        condition.symptomatic_before_doi is True
        and condition.severity in SIBTF_DISABLING_SEVERITIES
        and condition.trajectory in SIBTF_LIVE_TRAJECTORIES
        for condition in history.conditions
    )


def _has_qualifying_award(history: MedicalHistory) -> bool:
    return bool(history.awards)


#: What the ledger has to carry before a ``sibtf`` hook is standing on something.
#:
#: Labor Code §4751 makes the Fund liable where a *pre-existing permanent disability*
#: combines with the new injury, so the question is whether the ledger models a prior
#: disability — not whether it models a prior *claim*. A denied claim is the Fund's
#: argument against liability; a pending one has decided nothing yet.
SIBTF_QUALIFYING: tuple[SibtfClause, ...] = (
    SibtfClause(
        name="prior_award",
        remediation="add a prior_claims entry carrying an award block",
        holds=_has_qualifying_award,
    ),
    SibtfClause(
        name="predating_condition",
        remediation=(
            "add a conditions entry with symptomatic_before_doi true, severity "
            "severe, and a trajectory other than resolved"
        ),
        holds=_has_qualifying_condition,
    ),
)


def sibtf_grounding(history: MedicalHistory) -> tuple[str, ...]:
    """Which §4751 clauses this ledger satisfies, in registration order.

    Empty means the hook has nothing behind it. One predicate, consumed by both the
    evaluation and the message — see :func:`sibtf_requirement`.
    """
    return tuple(clause.name for clause in SIBTF_QUALIFYING if clause.holds(history))


def sibtf_requirement() -> str:
    """The remediation sentence, generated from the clauses it evaluates.

    Two independently maintained descriptions of one rule will drift, and this pair
    drifted before anyone ran it: the text offered "a condition predating the injury"
    and the check looked only at ``prior_claims``, so following the message changed
    nothing. Building the sentence from :data:`SIBTF_QUALIFYING` makes that particular
    lie unrepresentable.
    """
    return (
        "a prior permanent disability the Fund could be liable for — "
        + ", or ".join(clause.remediation for clause in SIBTF_QUALIFYING)
    )


HOOK_GROUNDING: dict[str, str] = {
    "lc4664_prior_award": (
        "a prior award of permanent disability — add a prior_claims entry carrying an "
        "award block"
    ),
    "benson": (
        "a second, distinct injury to apportion between — add a prior_claims entry"
    ),
    "sibtf": sibtf_requirement(),
}


def grounding_warnings(seed: CaseSeed, history: MedicalHistory | None) -> list[str]:
    """Warn where a seeded doctrine hook argues about an entity the ledger lacks.

    Warn, never block. The design record settles this as ISC-29's standing rule —
    an explicit control wins, and it wins loudly — and the alternative would make
    adding a schema axis retroactively invalidate seeds that were legal before it
    existed. The hook is kept and still renders; the author is told the argument has
    nothing behind it.
    """
    if history is None:
        return []
    out: list[str] = []
    for hook in seed.lifecycle.doctrine_hooks:
        requirement = HOOK_GROUNDING.get(hook)
        if requirement is None:
            continue
        if hook == "lc4664_prior_award" and history.awards:
            continue
        if hook == "benson" and history.prior_claims:
            continue
        if hook == "sibtf" and sibtf_grounding(history):
            continue
        out.append(
            f"lifecycle.doctrine_hooks names {hook} on a case whose "
            f"scenario.medical_history does not carry {requirement}. The hook is kept "
            "(an explicit seed wins) and its language still renders, but nothing in "
            "the world-truth ledger stands behind the argument."
        )
        log.warning("medical_history.ungrounded_hook", hook=hook, case_id=seed.case_id)
    return out


__all__ = [
    "HEALTH_ARCHETYPES",
    "HOOK_GROUNDING",
    "ONSET_YEARS_BEFORE_INJURY",
    "PRESUMPTION_DEFAULT_BY_RESOLUTION",
    "SEVERITY_WEIGHTS",
    "SIBTF_DISABLING_SEVERITIES",
    "SIBTF_QUALIFYING",
    "TRAJECTORY_WEIGHTS",
    "ApplicantDemographics",
    "HealthArchetype",
    "MedicalCondition",
    "MedicalHistory",
    "PriorAward",
    "PriorClaim",
    "archetype_weights",
    "billing_conditional",
    "calibrate",
    "condition_probabilities",
    "derive_demographics",
    "derive_medical_history",
    "draw_archetype",
    "eligible_conditions",
    "expected_any_condition",
    "grounding_warnings",
    "probability_of_any_condition",
    "reference_age_weights",
    "sample_conditions",
    "sibtf_grounding",
    "sibtf_requirement",
    "surfacing_conditional",
]
