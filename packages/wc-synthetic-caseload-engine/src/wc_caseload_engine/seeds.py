"""Seed schema — the interface of the product.

Everything a synthetic case needs is expressible in one reviewable YAML seed:
who was hurt, how, how far the case went, which doctrines flavour it, and
exactly which documents in what quantities and formats.

This module owns:

* the Pydantic v2 models (``CaseSeed``, ``CaseloadSpec`` and friends, all
  ``extra="forbid"``),
* the YAML loader with actionable, field-path-precise errors,
* deep-merge of a caseload's ``defaults`` under each case,
* deterministic ``auto:`` derivation from calibrated distributions,
* the serializer that writes a ``CaseSeed`` back out as clean YAML
  (``<out>/<case_id>/seed.yaml`` — the surfaced contract).

Determinism rule: nothing here reads the wall clock. Derived dates hang off
:data:`ANCHOR_DATE`, and every random draw comes from a seed-derived
``random.Random``.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import hashlib
import random
from collections.abc import Iterable, Mapping, MutableMapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, ClassVar, Literal

import structlog
import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)

# doctrine.py deliberately imports nothing from this module (its prerequisites
# read a flat ``DoctrineFacts`` record rather than a CaseSeed), so this import
# direction is the acyclic one.
from wc_caseload_engine.clinical_grounding import (
    CONDITION_CATALOG,
    BmiBand,
    BodySystem,
    Sex,
    SmokingStatus,
)
from wc_caseload_engine.doctrine import (
    DOCTRINE_CONTENT,
    DoctrineFacts,
    distinct_body_part_count,
    hook_is_supported,
    supported_hooks,
)

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Enumerations (Literal aliases keep YAML values and type checking in lockstep)
# ---------------------------------------------------------------------------

type InjuryType = Literal["specific", "cumulative_trauma", "death"]
type TargetStage = Literal[
    "intake",
    "active_treatment",
    "discovery",
    "medical_legal",
    "pre_trial",
    "resolved",
    "post_recon",
]
type ClaimResponse = Literal["accepted", "delayed", "denied"]
type EvalType = Literal["qme", "ame", "none"]
type UrDecision = Literal["upheld", "overturned"]
type ImrOutcome = Literal["upheld", "overturned"]
type ResolutionType = Literal[
    "stipulations", "c_and_r", "findings_award", "take_nothing", "pending"
]
type ReconOutcome = Literal["denied", "granted_remand", "granted_reversed"]
type PostReconPath = Literal["further_litigation", "settled", "affirmed_final"]
type LienClaimant = Literal[
    "medical_provider",
    "hospital",
    "pharmacy",
    "ambulance",
    "edd",
    "attorney_costs",
    "self_procured",
]
type LienResolution = Literal[
    "lien_stipulation",
    "lien_resolution_agreement",
    "dismissal",
    "order_on_lien",
    "mixed",
    "pending",
]
type DoctrineHook = Literal[
    "ogilvie",
    "almaraz_guzman",
    "benson",
    "escobedo",
    "kite",
    "going_and_coming",
    "sibtf",
    "death_dependency",
    "lc3208_3_psych",
    "gfpa",
    "firefighter_presumption",
    "imr_constitutionality",
    "ab5_dynamex",
    "lc4664_prior_award",
]
type DocumentFormat = Literal["pdf", "scanned_pdf", "eml", "docx"]
type FilenameStyle = Literal["neutral", "corpus"]
type Perspective = Literal["applicant", "defense"]
"""Whose case file this is.

Not a fact about the claim — a fact about the *file*. The same injury generates
one applicant-side file and one defense-side file, and they contain overlapping
but different paper. See :mod:`wc_caseload_engine.perspective`.
"""
type DistributionName = Literal[
    "balanced", "early_stage", "settlement_heavy", "complex_litigation"
]

ANCHOR_DATE: date = date(2026, 1, 1)
"""Fixed "today" for derived seeds — determinism forbids wall-clock reads."""

STAGE_RUNWAY_DAYS: Mapping[str, int] = {
    "intake": 30,
    "active_treatment": 180,
    "discovery": 180,
    "medical_legal": 365,
    "pre_trial": 365,
    "resolved": 540,
    "post_recon": 720,
}
"""Days a case of each stage needs between the injury onset and :data:`ANCHOR_DATE`.

A California workers' compensation file cannot reach a stage faster than the
statutory clock allows: an Application follows the injury by two to six months,
resolution by another six, a petition for reconsideration by twenty-five days
after the award, and the WCAB's order by sixty more. Seed a 2025-06-01 injury
as ``resolved`` and the entire sequence has to fit into seven months.

Before this floor existed the timeline silently absorbed the shortfall by
clamping, which produced a case whose petition for reconsideration was dated
eighty days *before* its Application for Adjudication. Failing loudly at the
seed boundary is the contract: the seed is the interface, so the seed is where
an impossible story gets rejected.
"""

RESOLVED_RUNWAY_DAYS = 540
"""Runway a *resolved case-in-chief* needs, whatever stage label it carries.

``target_stage`` says how far the file got; ``resolution.type`` says whether it
actually ended. A seed can claim ``pre_trial`` and still settle, and it is the
settlement — not the label — that has to fit before the anchor.
"""

POST_RESOLUTION_RUNWAY_DAYS = 720
"""Runway a case needs when litigation continues *after* the resolution.

Reconsideration and post-resolution lien litigation both run on past the award,
so they need the resolved runway plus room for the appellate round trip.
"""

DENIAL_RESPONSE_RUNWAY_DAYS = 90
"""Runway the denial-response chain needs, independent of the stage.

``lifecycle_bridge._guaranteed_denial_documents`` encodes the sequence: the
denial lands 30-90 days after the claim is filed, the Application follows it by
7-60, and the Declaration of Readiness by 60-180. A 30-day intake seed has room
for none of it, and before this floor existed the whole chain clamped onto the
anchor — a denial letter, the Application answering it and the DOR advancing it
all dated 2026-01-01, in a file whose stage says nothing has happened yet.
"""

UR_DISPUTE_RUNWAY_DAYS = 65
"""Runway a utilization-review dispute needs.

The encoded sequence puts the RFA at 60-240 days after the injury and the UR
decision 3-5 days after that (LC 4610's five working days). Sixty days is the
first of those two; the extra five are the decision window, without which the
RFA and the decision it answers can only share the anchor.
"""

IMR_RUNWAY_DAYS = 120
"""Cumulative runway a UR dispute appealed to IMR needs.

RFA (60) -> UR decision (+3) -> IMR application (+10, LC 4610.5 allows 30) ->
IMR determination (+30) is 103 days at its fastest. 120 leaves the chain room
to be drawn at something other than its minimum on every step.
"""

EVAL_RUNWAY_DAYS = 240
"""Runway a QME or AME evaluation needs.

``_guaranteed_eval_documents`` draws the panel request at 180-365 days after
the injury and the report 60-180 days after the panel — 240 days at the
absolute fastest. The release review proposed 120; the sequence already encoded
in this engine cannot fit in 120, so the floor is set from the code rather than
from the estimate, and a seed claiming a completed QME on a four-month-old
injury is now rejected instead of silently stacking the panel request and the
report on the same day.
"""

CASE_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"
"""Case ids double as output directory names — keep them path-safe."""

DEFAULT_FORMAT_MIX: Mapping[str, float] = {
    "pdf": 0.6,
    "scanned_pdf": 0.25,
    "eml": 0.1,
    "docx": 0.05,
}

_BASE_MODEL_CONFIG = ConfigDict(extra="forbid", validate_assignment=True, frozen=False)


class SeedError(ValueError):
    """Base class for seed loading/validation problems."""


class SeedValidationError(SeedError):
    """Raised when a seed or spec fails schema validation.

    ``str(exc)`` is a multi-line, actionable report: one line per problem with
    the dotted field path, the message (allowed values included) and the input.
    """

    def __init__(self, message: str, *, source: str, errors: Sequence[Mapping[str, Any]] = ()):
        super().__init__(message)
        self.source = source
        self.errors = list(errors)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class _Model(BaseModel):
    """Strict base: unknown keys are rejected so typos surface immediately."""

    model_config = _BASE_MODEL_CONFIG


class ApplicantProfile(_Model):
    """The injured worker. All fields optional — derived from ``rng_seed``."""

    name: str | None = None
    age: int | None = Field(default=None, ge=16, le=99)
    occupation: str | None = None
    tenure_years: float | None = Field(default=None, ge=0, le=60)

    sex: Sex | None = None
    """``None`` means *derive it* on the ``medical:`` namespace.

    Added because note C's grounding tables are sex-conditioned and the engine had
    nowhere to record the answer: SEER incidence, facet arthropathy and hypertension
    all report a split, and every one of them was stranded. Not yet honoured — no
    document renders it (M3), and the archetype mixture that reads it only runs when
    ``scenario.medical_history`` is present.
    """

    bmi_band: BmiBand | None = None
    """``None`` means *derive it*, calibrated to CDC obesity prevalence for the age.

    A risk factor, not a disease state — the design record draws that line and this
    field is which side of it body mass sits on. Not yet honoured (M3).
    """

    smoking_status: SmokingStatus | None = None
    """``None`` means *derive it*. Not yet honoured (M3).

    ``former`` is worth distinguishing from ``never`` because cessation of a year or
    more returns spinal-fusion outcomes to the never-smoker baseline: a former smoker
    is not a continuing apportionment target the way an active one is.
    """


class EmployerProfile(_Model):
    """The employer of record."""

    name: str | None = None
    industry: str | None = None
    county: str | None = None


class CarrierProfile(_Model):
    """The workers' compensation insurance carrier / administrator."""

    name: str | None = None


class AttorneyProfile(_Model):
    """Counsel on both sides (files are applicant-side POV)."""

    applicant_firm: str | None = None
    defense_firm: str | None = None


class PhysicianProfile(_Model):
    """Treating and evaluating physician specialties."""

    ptp_specialty: str | None = None
    qme_specialty: str | None = None


class CaseProfile(_Model):
    """Cast of the case; every section is derived when omitted."""

    applicant: ApplicantProfile = Field(default_factory=ApplicantProfile)
    employer: EmployerProfile = Field(default_factory=EmployerProfile)
    carrier: CarrierProfile = Field(default_factory=CarrierProfile)
    attorneys: AttorneyProfile = Field(default_factory=AttorneyProfile)
    physicians: PhysicianProfile = Field(default_factory=PhysicianProfile)


class BodyPart(_Model):
    """One injured body part with its ICD-10 code."""

    part: str = Field(min_length=1)
    icd10: str | None = None
    detail: str | None = None


def _repeated_part_message(first: str, second: str, *, case_id: str | None = None) -> str:
    """The one wording for a repeated body part, with or without a case name."""
    written = f"{first!r} and {second!r}" if first != second else repr(second)
    prefix = f"case {case_id!r}: " if case_id else ""
    return (
        f"{prefix}injury.body_parts names the same region twice ({written}). "
        "List each part once — a repeated entry is not a second impairment, and "
        "doctrines that need two distinct parts (benson, kite) would be satisfied "
        "by a part and itself. Use injury.body_parts[].detail to describe multiple "
        "findings in one region."
    )


class InjurySpec(_Model):
    """What happened, when, and to which body parts."""

    type: InjuryType = "specific"
    date_of_injury: date | None = None
    ct_start: date | None = None
    ct_end: date | None = None
    body_parts: list[BodyPart] = Field(min_length=1, max_length=5)
    mechanism: str = "auto"

    @staticmethod
    def find_repeated_part(body_parts: Iterable[Any]) -> tuple[str, str] | None:
        """The first region named twice, as ``(first spelling, second)``.

        A ``staticmethod`` over raw entries rather than a method on a built
        instance, because :class:`CaseSeed` has to run this check *before* the
        nested :class:`InjurySpec` is constructed — see
        :meth:`CaseSeed._reject_repeated_body_parts`.
        """
        seen: dict[str, str] = {}
        for entry in body_parts:
            part = entry.get("part") if isinstance(entry, Mapping) else getattr(entry, "part", None)
            if not isinstance(part, str):
                continue  # a malformed entry is the type system's problem, not ours
            key = part.strip().casefold()
            if key in seen:
                return seen[key], part
            seen[key] = part
        return None

    def repeated_body_part(self) -> tuple[str, str] | None:
        """This injury's first repeated region, or ``None``."""
        return self.find_repeated_part(self.body_parts)

    @model_validator(mode="after")
    def _check_distinct_body_parts(self) -> InjurySpec:
        """The invariant belongs to the injury, so the injury enforces it.

        :class:`CaseSeed` runs the same check earlier to produce a message
        naming the case, but ``InjurySpec`` is public API — it is in
        ``__all__`` — and a bare construction must not be able to hold a state
        the rest of the engine treats as impossible.
        """
        repeated = self.repeated_body_part()
        if repeated is None:
            return self
        raise ValueError(_repeated_part_message(*repeated))

    @model_validator(mode="after")
    def _check_dates(self) -> InjurySpec:
        if self.type == "cumulative_trauma":
            if self.ct_start is None or self.ct_end is None:
                raise ValueError(
                    "injury.ct_start and injury.ct_end are required when "
                    "injury.type is 'cumulative_trauma'"
                )
            if self.ct_end < self.ct_start:
                raise ValueError("injury.ct_end must be on or after injury.ct_start")
        elif self.date_of_injury is None:
            raise ValueError(
                f"injury.date_of_injury is required when injury.type is {self.type!r}"
            )
        return self

    @property
    def onset_date(self) -> date:
        """Single date anchoring the lifecycle (CT uses ``ct_end``)."""
        if self.type == "cumulative_trauma" and self.ct_end is not None:
            return self.ct_end
        if self.date_of_injury is None:  # pragma: no cover - _check_dates guarantees this
            raise SeedError("injury.date_of_injury is unset")
        return self.date_of_injury


class UrDispute(_Model):
    """Utilization review dispute and its optional IMR appeal."""

    enabled: bool = False
    decision: UrDecision | None = None
    imr: bool = False
    imr_outcome: ImrOutcome | None = None

    @model_validator(mode="after")
    def _check_consistency(self) -> UrDispute:
        if not self.enabled and (self.decision or self.imr or self.imr_outcome):
            raise ValueError(
                "lifecycle.ur_dispute.enabled must be true to set decision/imr/imr_outcome"
            )
        if self.imr and not self.enabled:
            raise ValueError("lifecycle.ur_dispute.imr requires ur_dispute.enabled: true")
        if self.imr_outcome is not None and not self.imr:
            raise ValueError("lifecycle.ur_dispute.imr_outcome requires ur_dispute.imr: true")
        return self


class ResolutionSpec(_Model):
    """How the case-in-chief ends."""

    type: ResolutionType = "pending"
    msa: bool = False


class ReconsiderationSpec(_Model):
    """Petition-for-reconsideration round trip after an award."""

    enabled: bool = False
    outcome: ReconOutcome | None = None
    post_recon: PostReconPath | None = None

    @model_validator(mode="after")
    def _check_consistency(self) -> ReconsiderationSpec:
        if not self.enabled:
            if self.outcome is not None or self.post_recon is not None:
                raise ValueError(
                    "lifecycle.reconsideration.enabled must be true to set outcome/post_recon"
                )
            return self
        if self.outcome is None:
            raise ValueError(
                "lifecycle.reconsideration.outcome is required when enabled; allowed: "
                "denied, granted_remand, granted_reversed"
            )
        if self.post_recon is None:
            raise ValueError(
                "lifecycle.reconsideration.post_recon is required when enabled; allowed: "
                "further_litigation, settled, affirmed_final"
            )
        if self.outcome == "denied" and self.post_recon != "affirmed_final":
            raise ValueError(
                "lifecycle.reconsideration.post_recon must be 'affirmed_final' when "
                "outcome is 'denied' (a denied petition ends the road)"
            )
        if self.outcome == "granted_remand" and self.post_recon == "affirmed_final":
            raise ValueError(
                "lifecycle.reconsideration.post_recon must be 'further_litigation' or "
                "'settled' when outcome is 'granted_remand'"
            )
        return self


class LienSpec(_Model):
    """Lien claimant tracks running alongside (and past) the case-in-chief."""

    count: int = Field(default=0, ge=0, le=8)
    claimants: list[LienClaimant] = Field(default_factory=list)
    resolution: LienResolution = "pending"
    post_resolution_litigation: bool = False

    @model_validator(mode="after")
    def _check_consistency(self) -> LienSpec:
        if self.count == 0 and self.claimants:
            raise ValueError(
                "lifecycle.liens.claimants listed but lifecycle.liens.count is 0 — "
                "raise count or drop the claimants"
            )
        if self.count == 0 and self.post_resolution_litigation:
            raise ValueError(
                "lifecycle.liens.post_resolution_litigation requires liens.count > 0"
            )
        if len(self.claimants) > self.count:
            raise ValueError(
                f"lifecycle.liens.claimants has {len(self.claimants)} entries but "
                f"liens.count is {self.count}"
            )
        return self


class LifecycleSpec(_Model):
    """How far the case went and which branches it took."""

    target_stage: TargetStage = "medical_legal"
    claim_response: ClaimResponse = "accepted"
    eval_type: EvalType = "qme"
    ur_dispute: UrDispute = Field(default_factory=UrDispute)
    resolution: ResolutionSpec = Field(default_factory=ResolutionSpec)
    reconsideration: ReconsiderationSpec = Field(default_factory=ReconsiderationSpec)
    liens: LienSpec = Field(default_factory=LienSpec)
    doctrine_hooks: list[DoctrineHook] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_consistency(self) -> LifecycleSpec:
        if self.target_stage == "post_recon" and not self.reconsideration.enabled:
            raise ValueError(
                "lifecycle.target_stage 'post_recon' requires "
                "lifecycle.reconsideration.enabled: true"
            )
        duplicates = sorted({h for h in self.doctrine_hooks if self.doctrine_hooks.count(h) > 1})
        if duplicates:
            raise ValueError(f"lifecycle.doctrine_hooks has duplicates: {', '.join(duplicates)}")
        return self


def runway_demands(lifecycle: LifecycleSpec) -> list[tuple[int, str]]:
    """Every runway demand this lifecycle makes, as ``(days, driver name)``.

    A case answers to all of them at once, so the binding demand is simply the
    largest. Listing them rather than folding them into one number is what lets
    the error message name the *branch* that actually blocked the seed:

    * the stage it claims to have reached (:data:`STAGE_RUNWAY_DAYS`),
    * the branches it took — a denied claim, a UR dispute, an IMR appeal, a QME
      or AME evaluation — each of which is a dated document chain,
    * whether the case-in-chief actually resolved
      (:data:`RESOLVED_RUNWAY_DAYS`),
    * whether anything litigates on after that resolution — reconsideration or
      post-resolution lien practice (:data:`POST_RESOLUTION_RUNWAY_DAYS`).

    The branch demands were the gap this closed. Runway was validated against
    the stage and the resolution only, so a 30-day ``intake`` seed that also
    said ``claim_response: denied`` passed validation and then produced a
    denial letter, an Application for Adjudication and a Declaration of
    Readiness all dated on the anchor.
    """
    stage = lifecycle.target_stage
    demands: list[tuple[int, str]] = [
        (STAGE_RUNWAY_DAYS[stage], f"lifecycle.target_stage {stage!r}")
    ]
    if lifecycle.claim_response == "denied":
        demands.append((DENIAL_RESPONSE_RUNWAY_DAYS, "lifecycle.claim_response 'denied'"))
    if lifecycle.ur_dispute.enabled:
        demands.append((UR_DISPUTE_RUNWAY_DAYS, "lifecycle.ur_dispute.enabled"))
    if lifecycle.ur_dispute.imr:
        demands.append((IMR_RUNWAY_DAYS, "lifecycle.ur_dispute.imr"))
    if lifecycle.eval_type in {"qme", "ame"}:
        demands.append((EVAL_RUNWAY_DAYS, f"lifecycle.eval_type {lifecycle.eval_type!r}"))
    if lifecycle.resolution.type != "pending":
        demands.append(
            (RESOLVED_RUNWAY_DAYS, f"lifecycle.resolution.type {lifecycle.resolution.type!r}")
        )
    if lifecycle.reconsideration.enabled:
        demands.append((POST_RESOLUTION_RUNWAY_DAYS, "lifecycle.reconsideration.enabled"))
    if lifecycle.liens.post_resolution_litigation:
        demands.append(
            (POST_RESOLUTION_RUNWAY_DAYS, "lifecycle.liens.post_resolution_litigation")
        )
    return demands


def required_runway_days(lifecycle: LifecycleSpec) -> int:
    """Days this lifecycle needs between the injury onset and :data:`ANCHOR_DATE`."""
    return max(days for days, _driver in runway_demands(lifecycle))


def runway_driver(lifecycle: LifecycleSpec) -> str:
    """Which part of the lifecycle set the runway — named in the error message.

    Ties break toward the *first* demand in :func:`runway_demands`, which lists
    the stage before any branch. A ``resolved`` case that also resolved is
    blocked by 540 days twice over, and the stage is the more useful of the two
    to name: it is the field the author would edit to make the seed fit.
    """
    binding = max(runway_demands(lifecycle), key=lambda demand: demand[0])
    return binding[1]


class DocumentOverride(_Model):
    """One document control entry: an exact subtype count or a per-type bound."""

    subtype: str | None = None
    type: str | None = None
    count: int | None = Field(default=None, ge=0)
    min: int | None = Field(default=None, ge=0)
    max: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _check_shape(self) -> DocumentOverride:
        if (self.subtype is None) == (self.type is None):
            raise ValueError(
                "documents.overrides[] entry needs exactly one of 'subtype' or 'type'"
            )
        if self.subtype is not None:
            if self.count is None:
                raise ValueError(
                    f"documents.overrides[] entry for subtype {self.subtype!r} requires 'count'"
                )
            if self.min is not None or self.max is not None:
                raise ValueError(
                    "documents.overrides[] subtype entries take 'count' only "
                    "(min/max are for 'type' entries)"
                )
        else:
            if self.count is not None:
                raise ValueError(
                    "documents.overrides[] type entries take 'min'/'max' only "
                    "(count is for 'subtype' entries)"
                )
            if self.min is None and self.max is None:
                raise ValueError(
                    f"documents.overrides[] entry for type {self.type!r} requires 'min' or 'max'"
                )
            if self.min is not None and self.max is not None and self.min > self.max:
                raise ValueError(
                    f"documents.overrides[] entry for type {self.type!r}: min "
                    f"({self.min}) exceeds max ({self.max})"
                )
        return self

    @property
    def key(self) -> str:
        """The subtype or type key this override targets."""
        return self.subtype if self.subtype is not None else str(self.type)


class DocumentControls(_Model):
    """Fine-grained control over what lands in the case file."""

    global_cap: int | None = Field(default=None, ge=1)
    format_mix: dict[str, float] = Field(default_factory=lambda: dict(DEFAULT_FORMAT_MIX))
    include_only: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)
    overrides: list[DocumentOverride] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_controls(self) -> DocumentControls:
        allowed = ("pdf", "scanned_pdf", "eml", "docx")
        for key, weight in self.format_mix.items():
            if key not in allowed:
                raise ValueError(
                    f"documents.format_mix key {key!r} is not a format; "
                    f"allowed: {', '.join(allowed)}"
                )
            if weight < 0:
                raise ValueError(f"documents.format_mix[{key}] must be >= 0, got {weight}")
        if self.format_mix and sum(self.format_mix.values()) <= 0:
            raise ValueError("documents.format_mix must have at least one positive weight")
        overlap = sorted(set(self.include_only) & set(self.exclude))
        if overlap:
            raise ValueError(
                "documents.include_only and documents.exclude both name: " + ", ".join(overlap)
            )
        seen: set[str] = set()
        for override in self.overrides:
            if override.key in seen:
                raise ValueError(f"documents.overrides has duplicate entries for {override.key!r}")
            seen.add(override.key)
        return self

    @property
    def subtype_overrides(self) -> dict[str, int]:
        """Exact per-subtype counts, highest precedence control."""
        return {o.subtype: int(o.count) for o in self.overrides if o.subtype is not None}

    @property
    def type_bounds(self) -> dict[str, tuple[int | None, int | None]]:
        """Per-parent-type ``(min, max)`` bounds."""
        return {str(o.type): (o.min, o.max) for o in self.overrides if o.type is not None}


MODALITIES: tuple[str, ...] = ("mri", "ct", "xray", "emg", "labs")
"""Diagnostic vocabulary a ``scenario:`` block may name.

Duplicated from :mod:`wc_caseload_engine.case_facts` rather than imported: that
module imports :class:`CaseSeed` from here, so importing it back would close a
cycle. A test asserts the two tuples are equal, which is cheaper than the
indirection needed to share one.
"""


class DiagnosticEntry(_Model):
    """One ``scenario.diagnostics`` entry: a modality, optionally scoped.

    Accepts either a bare modality (``mri``) or a modality bound to a region
    (``{modality: mri, body_part: shoulder}``). Bare means "the primary body
    part", which is what a seed author almost always means and saves stating a
    region the injury block already names.
    """

    modality: str
    body_part: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _accept_a_bare_modality(cls, value: Any) -> Any:
        return {"modality": value} if isinstance(value, str) else value

    @field_validator("modality")
    @classmethod
    def _known_modality(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if normalized not in MODALITIES:
            raise ValueError(
                f"{value!r} is not a diagnostic modality this engine can render. "
                f"Use one of: {', '.join(MODALITIES)}."
            )
        return normalized


class DiagnosticsScenario(_Model):
    """What was imaged, and what deliberately was not.

    Both halves matter. ``performed`` is what the file's documents may cite;
    ``absent`` is what no document may cite, and stating it explicitly is what
    turns "the QME invented an MRI" from an unfalsifiable complaint into a
    grep. Leaving both empty hands the whole decision to derivation.
    """

    performed: list[DiagnosticEntry] = Field(default_factory=list, max_length=12)
    absent: list[DiagnosticEntry] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def _no_study_is_both(self) -> DiagnosticsScenario:
        performed = {(e.modality, e.body_part) for e in self.performed}
        clashes = sorted(
            f"{e.modality}"
            + (f" on {e.body_part}" if e.body_part else " (primary body part)")
            for e in self.absent
            if (e.modality, e.body_part) in performed
        )
        if clashes:
            raise ValueError(
                "scenario.diagnostics lists the same study as both performed and "
                f"absent: {'; '.join(clashes)}. A study either happened or it did "
                "not — name it once, in whichever list is true."
            )
        return self


#: Lien claimants whose existence implies somebody treated the applicant.
#:
#: EDD, attorney costs, self-procured and ambulance liens do not: a benefits
#: overpayment or a cost bill can exist in a file where no provider was ever
#: seen, so ``never_treated`` tolerates them.
TREATMENT_LIEN_CLAIMANTS: tuple[str, ...] = ("medical_provider", "hospital", "pharmacy")


class TreatmentScenario(_Model):
    """The shape of the treatment record, before any document is planned.

    ``status`` is the trajectory the file tells:

    - ``ongoing`` — the default arc: visits continue through evaluation.
    - ``discharged`` — care ended; a discharge summary exists and no treating
      report post-dates it.
    - ``gap`` — a stretch with no visits, which is the fact a defense file is
      usually built around.
    - ``never_treated`` — the applicant did not treat. Everything past the
      first-report tier is suppressed at the planner.
    """

    status: Literal["ongoing", "discharged", "gap", "never_treated"] | None = None
    """``None`` means *derive it*, preserving whatever the substrate did before."""

    providers: int | None = Field(default=None, ge=1, le=8)
    """Ledger roster size. ``None`` takes the substrate case's own provider list."""


class AdjusterScenario(_Model):
    """How diligently the claims administrator handled the file.

    The axis a delay-and-penalty file turns on. ``attentive`` pays and notices
    early inside the statutory windows; ``ordinary`` uses most of them;
    ``negligent`` can miss them, and when it does the lateness becomes a ledger
    fact with the days recorded — which is what lets the LC 5814 penalty
    petition be *earned* rather than coin-flipped.
    """

    diligence: Literal["attentive", "ordinary", "negligent"] | None = None
    """``None`` means *derive it* on the ``facts:`` namespace."""


class AttorneyScenario(_Model):
    """How often applicant's counsel wrote to the client.

    ``every_30_days`` is the diligent practice; ``event_driven`` writes when
    something happened and is silent otherwise; ``sporadic`` is the file with a
    three-month hole in the correspondence that opposing counsel will notice.
    """

    cadence: Literal["every_30_days", "event_driven", "sporadic"] | None = None
    """``None`` means *derive it* on the ``facts:`` namespace.

    Honoured: counsel's client letters are re-dated onto the resolved cadence
    (ISC-123/124). ``every_30_days`` walks a thirty-day clock; ``event_driven``
    follows the reports and milestones already in the file, five days behind
    each; ``sporadic`` opens at least one gap over ninety days. Published on
    ``caseFacts.attorney.cadence``, because the letter dates in the manifest are
    what a reader checks it against.

    A file too short to hold the rhythm it declares is reported, not silently
    compressed — see the ``sporadic`` warning in ``_apply_attorney_cadence``.
    """


class PageRange(_Model):
    """Inclusive page-count bounds for one subpoenaed-records packet."""

    min: int = Field(default=15, ge=1, le=2000)
    max: int = Field(default=45, ge=1, le=2000)

    @model_validator(mode="after")
    def _min_does_not_exceed_max(self) -> PageRange:
        if self.min > self.max:
            raise ValueError(
                f"scenario.discovery.pages_per_set has min {self.min} greater than max "
                f"{self.max} — a packet cannot hold fewer pages than its own floor. "
                "Swap the two values, or raise max to at least the min."
            )
        return self


class DiscoveryScenario(_Model):
    """How much paper the discovery phase produced."""

    subpoena_sets: int | None = Field(default=None, ge=0, le=24)
    """Records packets to emit.

    Honoured: the plan is trimmed or extended to exactly this many packets
    (ISC-126). ``None`` keeps whatever the lifecycle walk proposed, which is
    what leaves every pre-0.7.0 seed byte-identical.

    A stage that proposes no packets at all is warned about rather than silently
    ignored — the count has nothing to act on before ``target_stage:
    discovery``.
    """

    pages_per_set: PageRange = Field(default_factory=PageRange)
    """Declared page volume per packet.

    Honoured, and *pages* means physical pages. One count is drawn per packet on
    the ``facts:`` stream; the renderer measures what actually came out, adjusts,
    and writes the cover sheet's table from the measurement — so the ledger, the
    table of contents and the paper are three readings of one number.

    Before ISC-126 the table of contents summed its own ``random.randint`` draws
    while the body drew separately, so a cover sheet could promise 23 pages in
    front of a packet holding 6.
    """


#: The named methods by which an average weekly wage may be computed.
#:
#: **These are engine labels, not statutory citations.** Each names the
#: *arithmetic* the engine performs, so the analyzer (AJC-38) is scored against a
#: label whose meaning is defined by this package's own code rather than by a
#: statutory subdivision nobody here has confirmed. The controlling authority for
#: each method is carried separately, as counsel-unconfirmed prose, on
#: :class:`~wc_caseload_engine.money.RateBasis`.
#:
#: The method name is ground truth. It is recorded explicitly on the ledger and
#: printed on the wage statement; it is never inferred by a reader from the
#: numbers, because two methods can coincide on one earnings history and a label
#: that is only sometimes recoverable is not a label.
type AwwMethod = Literal[
    "actual_weekly_earnings",
    "irregular_earnings_average",
    "short_history_projection",
    "concurrent_aggregate",
    "earning_capacity",
]

AWW_METHODS: tuple[str, ...] = (
    "actual_weekly_earnings",
    "irregular_earnings_average",
    "short_history_projection",
    "concurrent_aggregate",
    "earning_capacity",
)
"""Runtime mirror of :data:`AwwMethod`, for iteration and error messages."""

type EarningsPattern = Literal["regular", "irregular", "seasonal"]
type PayFrequency = Literal["weekly", "biweekly", "semimonthly", "monthly"]

PAY_PERIODS_PER_YEAR: Mapping[str, int] = {
    "weekly": 52,
    "biweekly": 26,
    "semimonthly": 24,
    "monthly": 12,
}
"""Pay periods a year, per frequency — the divisor the wage statement rows use."""


class EarningsEntry(_Model):
    """One pay period, stated by the seed rather than derived.

    Stating periods explicitly is how a test — or a seed author reproducing a
    real file — pins an earnings history exactly. Anything left unstated is
    derived from :class:`WageScenario`'s shape knobs instead, and the two are
    mutually exclusive by construction: a seed either lists its periods or
    describes them.

    ``gross`` is the period's **total**, overtime included, because that is what
    a payroll record prints. ``overtime`` breaks out how much of that total was
    premium pay, which is the figure an analyzer has to recover separately when
    method selection turns on it.
    """

    period_start: date
    period_end: date
    gross: float = Field(ge=0, le=1_000_000)
    """Total gross for the period, in dollars. Overtime included."""

    overtime: float = Field(default=0.0, ge=0, le=1_000_000)
    """How much of ``gross`` was overtime premium pay."""

    concurrent: bool = False
    """True when this period is earnings from a *second*, concurrent employer."""

    @model_validator(mode="after")
    def _period_is_ordered_and_overtime_fits(self) -> EarningsEntry:
        if self.period_end < self.period_start:
            raise ValueError(
                f"scenario.wages.earnings has a period ending {self.period_end} before it "
                f"starts {self.period_start}. Swap the two dates, or correct whichever one "
                "is mistyped."
            )
        if self.overtime > self.gross:
            raise ValueError(
                f"scenario.wages.earnings has overtime {self.overtime} greater than the "
                f"period's gross {self.gross} — gross is the total and overtime is part of "
                "it. Raise gross to at least the overtime, or lower the overtime."
            )
        return self


def _days_covered(entry: EarningsEntry) -> Iterable[date]:
    """Every calendar day one earnings period spans, inclusive of both ends."""
    cursor = entry.period_start
    while cursor <= entry.period_end:
        yield cursor
        cursor += timedelta(days=1)


class InKindEntry(_Model):
    """Non-cash wages — board, lodging, a vehicle — at their weekly value.

    Modelled because in-kind wages are one of the standing arguments about what
    an average weekly wage includes, and a corpus that cannot express them
    cannot pose the question.
    """

    kind: str = Field(min_length=1, max_length=64)
    weekly_value: float = Field(gt=0, le=10_000)


class RateBasisOverride(_Model):
    """Seed-supplied statutory rate parameters for this case's date of injury.

    **Every number here is a legal binding and none of them is confirmed.** The
    engine ships a default table so a seed need not restate the law, but that
    table is explicitly counsel-unconfirmed and this block is the seam by which
    a verified authority replaces it per case. See
    :mod:`wc_caseload_engine.money` for the module-level seam KB-167 will fill.

    A seed that sets this block owns the numbers. The ledger records the source
    as ``seed`` so a reader can tell an authored binding from a defaulted one.
    """

    td_fraction: float | None = Field(default=None, gt=0, le=1)
    """Fraction of AWW that becomes the temporary-disability weekly rate."""

    td_max_weekly: float | None = Field(default=None, gt=0, le=100_000)
    td_min_weekly: float | None = Field(default=None, ge=0, le=100_000)
    pd_fraction: float | None = Field(default=None, gt=0, le=1)
    pd_max_weekly: float | None = Field(default=None, gt=0, le=100_000)
    pd_min_weekly: float | None = Field(default=None, ge=0, le=100_000)

    authority: str | None = Field(default=None, max_length=400)
    """The citation these numbers came from, in the author's own words."""

    counsel_confirmed: bool = False
    """Whether counsel has verified this binding. Defaults false, deliberately.

    A seed author may flip it, and the ledger publishes whatever it says; the
    engine's own table can never set it true.
    """

    #: Every number a complete statutory binding states.
    NUMERIC_FIELDS: ClassVar[tuple[str, ...]] = (
        "td_fraction",
        "td_max_weekly",
        "td_min_weekly",
        "pd_fraction",
        "pd_max_weekly",
        "pd_min_weekly",
    )

    @model_validator(mode="after")
    def _bounds_are_ordered(self) -> RateBasisOverride:
        """A bound is stated with the bound it is bounded by, and in order.

        The pairing requirement is the half that was missing. A lone
        ``td_min_weekly`` merges against a *defaulted* ceiling this block never
        saw, so a pairwise check on the override alone finds a floor with
        nothing beside it and passes — measured, a $5,000 floor went through
        under the $1,539.71 default ceiling and produced a temporary-disability
        rate above the maximum published in the same basis, recorded as ``min``.

        Requiring the pair is what makes the ordering check meaningful here
        rather than only in :class:`~wc_caseload_engine.money.RateBasis`, where
        it is now also enforced on the merged result. An author overriding one
        end of a range has an opinion about the range; stating both is the cost
        of that opinion, and it is one line of YAML.
        """
        for low, high, name in (
            (self.td_min_weekly, self.td_max_weekly, "td"),
            (self.pd_min_weekly, self.pd_max_weekly, "pd"),
        ):
            if (low is None) != (high is None):
                stated, missing = (
                    (f"{name}_min_weekly", f"{name}_max_weekly")
                    if high is None
                    else (f"{name}_max_weekly", f"{name}_min_weekly")
                )
                raise ValueError(
                    f"scenario.wages.rate_basis sets {stated} without {missing} — the "
                    "other end of the range would come from the engine's unverified "
                    "default table, where it may sit on the wrong side of the figure "
                    f"you stated. Add {missing}, or remove {stated}."
                )
            if low is not None and high is not None and low > high:
                raise ValueError(
                    f"scenario.wages.rate_basis has {name}_min_weekly {low} above "
                    f"{name}_max_weekly {high} — a floor cannot sit above its own ceiling. "
                    "Swap the two values, or raise the maximum."
                )
        return self

    @model_validator(mode="after")
    def _confirmation_covers_a_whole_binding(self) -> RateBasisOverride:
        """Confirmation is a claim about numbers, so it needs the numbers.

        The engine's table is counsel-unconfirmed in every row and says so in
        its own authority text. A block carrying nothing but
        ``counsel_confirmed: true`` used to publish that entire table as
        confirmed — engine numbers, engine authority string still reading
        ``COUNSEL-UNCONFIRMED``, and ``counselConfirmed: true`` on the manifest
        above it. That is the one assertion this package promises it can never
        make, and it was reachable in five words of YAML.

        Confirming therefore means stating what is confirmed: all six figures
        and the authority they come from. Anything less is an override of the
        numbers it names, defaulted for the rest, and unconfirmed — which is
        what a partially authored binding actually is.
        """
        if not self.counsel_confirmed:
            return self
        missing = [name for name in self.NUMERIC_FIELDS if getattr(self, name) is None]
        if self.authority is None:
            missing.append("authority")
        if missing:
            raise ValueError(
                "scenario.wages.rate_basis sets counsel_confirmed: true but leaves "
                f"{', '.join(missing)} unset — the engine's own figures are unverified "
                "placeholders, so confirming a binding means stating the binding rather "
                "than adopting theirs. Supply every rate_basis figure and the authority "
                "they come from, or set counsel_confirmed to false."
            )
        return self


class WageScenario(_Model):
    """The earnings history behind this file's money. **The gate.**

    Presence of this block is what turns the money spine on. A seed without it
    derives no money facts at all, publishes no money in its manifest, and
    renders every document through the code path it took before this block
    existed — which is the anti-criterion the money layer is held to.

    Two ways to state a history, and they do not mix:

    * ``earnings`` — list the pay periods outright. Exact, and how a test or a
      reproduction of a real file pins the numbers.
    * the shape knobs (``pattern``, ``base_weekly_wage``, ``lookback_weeks``,
      ``pay_frequency``, ``overtime_share``) — describe the history and let the
      engine derive periods on its own deterministic stream.

    ``method`` is the one field that is ground truth rather than input. Left
    unset it is *selected* from the wage facts by a stated, testable rule and
    recorded with the reason; set, it is taken as given and recorded as authored.
    Either way the answer is written down rather than left to be inferred.
    """

    #: The knobs that *describe* a history, and so cannot sit beside a listed one.
    #:
    #: Named as data rather than checked one by one, because the set is what the
    #: class docstring promises and a list that drifts from the prose is how four
    #: of these six went unenforced. :meth:`_history_is_stated_one_way` reads
    #: this against ``model_fields_set``, which is the only way to see a knob
    #: whose stated value happens to equal its default.
    SHAPE_KNOBS: ClassVar[frozenset[str]] = frozenset(
        {
            "pattern",
            "base_weekly_wage",
            "lookback_weeks",
            "pay_frequency",
            "overtime_share",
            "concurrent_weekly_wage",
        }
    )

    earnings: list[EarningsEntry] = Field(default_factory=list, max_length=60)
    """Explicit pay periods. Mutually exclusive with the shape knobs."""

    pattern: EarningsPattern = "regular"
    """Shape of a derived history — steady, irregular, or seasonal."""

    base_weekly_wage: float | None = Field(default=None, gt=0, le=100_000)
    """Weekly wage a derived history varies around. Derived when unset."""

    lookback_weeks: int = Field(default=52, ge=4, le=260)
    """Weeks of history the statement covers, counting back from the injury."""

    pay_frequency: PayFrequency = "biweekly"
    """How often the applicant was paid — the row granularity of the statement."""

    overtime_share: float = Field(default=0.0, ge=0, le=0.6)
    """Fraction of gross that is overtime premium, on average, in a derived history."""

    employment_start: date | None = None
    """When this employment began. Earlier than the lookback means a full
    history; later truncates it, which is what makes the short-history method
    reachable."""

    concurrent_employment: bool = False
    """Whether a second, concurrent employer's earnings belong in the average."""

    concurrent_weekly_wage: float | None = Field(default=None, gt=0, le=100_000)
    """Weekly wage of the concurrent employment. Derived when unset."""

    in_kind: list[InKindEntry] = Field(default_factory=list, max_length=6)
    """Non-cash wages, at weekly value, added to the computed average."""

    method: AwwMethod | None = None
    """The named method. ``None`` means *select it* from the wage facts."""

    earning_capacity_weekly: float | None = Field(default=None, gt=0, le=100_000)
    """Required by, and only by, ``method: earning_capacity``.

    The catch-all method exists precisely because no arithmetic over the
    earnings history produces the right answer, so the answer has to be stated.
    """

    rate_basis: RateBasisOverride | None = None
    """Per-case override of the statutory rate parameters. See the class."""

    @model_validator(mode="after")
    def _dependent_fields_have_their_enabler(self) -> WageScenario:
        """A figure only one setting consumes is refused without that setting.

        Both fields document themselves as required by, and *only* by, something
        else — and both were accepted and ignored without it.
        ``earning_capacity_weekly: 7777`` beside a described history published
        ``996.73`` under ``actual_weekly_earnings``; ``concurrent_weekly_wage:
        8888`` published no concurrent employment at all. A seed author reading
        either manifest would have to work out that the engine had discarded a
        number they wrote, which is ISC-29's rule inverted.
        """
        if self.earning_capacity_weekly is not None and self.method != "earning_capacity":
            stated = "unset" if self.method is None else repr(self.method)
            raise ValueError(
                f"scenario.wages sets earning_capacity_weekly but method is {stated} — the "
                "figure is consumed by, and only by, the earning_capacity method, so "
                "nothing here would read it. Set scenario.wages.method to "
                "'earning_capacity', or remove earning_capacity_weekly."
            )
        if self.concurrent_weekly_wage is not None and not self.concurrent_employment:
            raise ValueError(
                "scenario.wages sets concurrent_weekly_wage but concurrent_employment is "
                "false — there is no second employment for that wage to belong to. Set "
                "scenario.wages.concurrent_employment to true, or remove "
                "concurrent_weekly_wage."
            )
        if self.method == "concurrent_aggregate" and not (
            self.concurrent_employment or any(e.concurrent for e in self.earnings)
        ):
            # A seed may name any method — the author's argument wins over the
            # engine's rule, which is why ``method`` is authored at all. This one
            # is different in kind: the other four label an *argument* about how
            # to average one history, and could be argued over any history.
            # ``concurrent_aggregate`` labels a *fact* — that earnings from more
            # than one employer were combined — and over a single employment
            # there was nothing to combine. Measured: the seed loaded and
            # published ``method: concurrent_aggregate`` beside
            # ``concurrentEmployment: false`` on a computation containing only
            # primary earnings, which is a ground-truth label the manifest
            # contradicts one field later.
            raise ValueError(
                "scenario.wages.method is 'concurrent_aggregate' but this history has no "
                "concurrent employment — the method names earnings combined across "
                "employers, and there is only one here, so the label would assert an "
                "aggregation that did not happen. Set "
                "scenario.wages.concurrent_employment to true, or mark the second "
                "employer's periods 'concurrent: true', or choose a method that averages "
                "one employment."
            )
        return self

    @model_validator(mode="after")
    def _history_is_stated_one_way(self) -> WageScenario:
        if not self.earnings:
            if self.method == "earning_capacity" and self.earning_capacity_weekly is None:
                raise ValueError(
                    "scenario.wages.method is 'earning_capacity' but "
                    "scenario.wages.earning_capacity_weekly is unset — the catch-all method "
                    "exists because no arithmetic over the earnings history gives the "
                    "answer, so the answer has to be stated. Set "
                    "scenario.wages.earning_capacity_weekly, or choose a method that "
                    "computes."
                )
            return self

        # Read from the *set* fields, not from the values. Four of the six shape
        # knobs carry defaults, so "is it None" cannot tell a knob the author
        # wrote from one Pydantic filled in — which is why the first cut of this
        # validator policed only the two nullable ones and let the other four
        # through. ``pattern`` is the sharp case: it is a **published ground
        # truth label**, so a seed listing a steady history under
        # ``pattern: irregular`` shipped a wrong label to the analyzer, silently.
        stated = sorted(self.model_fields_set & set(self.SHAPE_KNOBS))
        if stated:
            raise ValueError(
                f"scenario.wages lists explicit earnings and also sets "
                f"{', '.join(stated)} — a history is either listed or described, "
                "never both, because the two would disagree and the listed periods "
                f"would win silently. Remove the listed earnings, or remove "
                f"{', '.join(stated)}."
            )
        if not any(not entry.concurrent for entry in self.earnings):
            raise ValueError(
                "scenario.wages.earnings marks every period 'concurrent: true' — the "
                "average weekly wage is computed over the weeks of the *primary* "
                "employment, so a history with no primary period averages a real gross "
                "over zero weeks and publishes an average weekly wage of 0.00. Set "
                "'concurrent: false' on the primary employer's periods, or add them."
            )
        primary_days = {
            day
            for entry in self.earnings
            if not entry.concurrent
            for day in _days_covered(entry)
        }
        concurrent_days = {
            day
            for entry in self.earnings
            if entry.concurrent
            for day in _days_covered(entry)
        }
        if concurrent_days and concurrent_days != primary_days:
            # One gross over one denominator cannot express two employments that
            # ran for different lengths. Measured: a two-week primary job at
            # $1,000/week beside a fifty-two-week second job at $1,000/week
            # aggregated to $54,000, and *any* single denominator is wrong for
            # it — 2 weeks says $27,000, 52 weeks says $1,038.46, and the answer
            # a reader would defend is $2,000, the sum of the two weekly rates
            # while both were running. Reaching that needs per-employment
            # operands, which needs employer identity: a boolean cannot say
            # *which* employer a period belongs to, so it cannot group them.
            #
            # Refused rather than approximated. An additive Wave-2 field can
            # open this shape properly; publishing a number here that no
            # arithmetic on the page reproduces would put exactly the asserted
            # figure this layer exists to remove into the one method whose whole
            # point is combining employments.
            raise ValueError(
                "scenario.wages.earnings has concurrent periods covering different dates "
                "from the primary ones — the aggregate is one gross over one span, so two "
                "employments of different lengths cannot both be right in it. Replace the "
                "concurrent periods with ones covering the primary dates, or drop them "
                "and describe the second employment with concurrent_employment instead."
            )
        if self.method == "earning_capacity" and self.earning_capacity_weekly is None:
            raise ValueError(
                "scenario.wages.method is 'earning_capacity' but "
                "scenario.wages.earning_capacity_weekly is unset — the catch-all method "
                "exists because no arithmetic over the earnings history gives the answer, "
                "so the answer has to be stated. Set "
                "scenario.wages.earning_capacity_weekly, or choose a method that computes."
            )
        if self.concurrent_employment and not any(e.concurrent for e in self.earnings):
            raise ValueError(
                "scenario.wages.concurrent_employment is true but no listed earnings entry "
                "is marked 'concurrent: true' — the aggregate would be over one employer. "
                "Set 'concurrent: true' on the second employer's periods, or set "
                "concurrent_employment to false."
            )
        return self


class BenefitsScenario(_Model):
    """What was actually paid, and how badly.

    The knobs here are the ones a delay-and-penalty file turns on. They exist so
    that lateness and interruption are *stated facts of the seed* with the days
    recorded, rather than something a reader has to infer from payment dates —
    which is what lets Wave 3 compute a penalty against a known exposure instead
    of against a guess.

    Every field left unset derives from ``scenario.adjuster.diligence``, so the
    persona already in the schema drives the money without a second, independent
    knob that could contradict it.
    """

    td_weeks: int | None = Field(default=None, ge=0, le=520)
    """Weeks of temporary disability paid. Derived from the timeline when unset."""

    td_gap_days: int | None = Field(default=None, ge=0, le=1_000)
    """A deliberate interruption in the temporary-disability series, in days."""

    late_payments: int | None = Field(default=None, ge=0, le=52)
    """How many payments issued after their due date. Derived from diligence."""

    max_days_late: int | None = Field(default=None, ge=1, le=730)
    """The worst single lateness, in days. Derived from diligence when unset."""

    pd_advances: int | None = Field(default=None, ge=0, le=52)
    """Permanent-disability advances paid before any award. Derived when unset."""

    #: Blocks of temporary disability a gap needs on either side of it.
    #:
    #: Payments issue in four-week blocks and a gap sits *between* two of them,
    #: so eight weeks is the shortest run that can hold one.
    GAP_MINIMUM_WEEKS: ClassVar[int] = 8

    @model_validator(mode="after")
    def _lateness_is_coherent(self) -> BenefitsScenario:
        if self.late_payments == 0 and self.max_days_late is not None:
            raise ValueError(
                "scenario.benefits.late_payments is 0 but max_days_late is "
                f"{self.max_days_late} — no payment was late, so none can be late by a "
                "number of days. Raise late_payments above zero, or drop max_days_late."
            )
        if self.max_days_late is not None and self.late_payments is None:
            # The pair is the fact, exactly as approval and funding are. Alone,
            # ``max_days_late`` is measured against a count that comes from the
            # adjuster persona — so on an `attentive` file it described a delay
            # of sixty-two days across zero late payments, and published no
            # lateness at all without a word.
            raise ValueError(
                f"scenario.benefits sets max_days_late to {self.max_days_late} without "
                "late_payments — how many payments were late comes from "
                "scenario.adjuster.diligence otherwise, and on an attentive administrator "
                "that is none, so the delay would be dropped in silence. Add "
                "scenario.benefits.late_payments, or drop max_days_late and let diligence "
                "decide both."
            )
        return self

    @model_validator(mode="after")
    def _every_stated_control_can_be_honoured(self) -> BenefitsScenario:
        """A control the ledger cannot honour is refused, not quietly dropped.

        ISC-29's rule — an explicit control wins loudly — applied to the money
        knobs. Measured before this validator: ``{td_weeks: 0, pd_advances: 0,
        late_payments: 3, max_days_late: 62}`` loaded and published
        ``latePayments: 0``, and ``{td_weeks: 0, td_gap_days: 90}`` published
        ``gapDays: 0``. The seed asked for a delay file and got a clean one,
        with nothing anywhere saying the request had been dropped.

        Only what the seed alone can decide is checked here. Truncation against
        the case's own runway needs the timeline, so the planner reports that as
        a warning instead — see ``planner._money_control_warnings``.
        """
        if self.td_weeks == 0 and self.pd_advances == 0:
            for name in ("late_payments", "max_days_late"):
                value = getattr(self, name)
                if value:
                    raise ValueError(
                        f"scenario.benefits sets {name} to {value} but pays nothing — "
                        "td_weeks and pd_advances are both 0, so there is no payment to "
                        f"be late. Raise td_weeks or pd_advances above zero, or drop "
                        f"{name}."
                    )
        if self.td_gap_days and (self.td_weeks or 0) < self.GAP_MINIMUM_WEEKS:
            stated = "0" if self.td_weeks == 0 else str(self.td_weeks)
            raise ValueError(
                f"scenario.benefits sets td_gap_days to {self.td_gap_days} with td_weeks "
                f"{stated} — payments issue in four-week blocks and a gap sits between "
                f"two of them, so a run shorter than {self.GAP_MINIMUM_WEEKS} weeks has "
                "nowhere to put one and the gap would be dropped in silence. Raise "
                f"td_weeks to {self.GAP_MINIMUM_WEEKS} or more, or drop td_gap_days."
            )
        return self


#: The smallest settlement gross the documents can represent: the stipulated
#: award splits it into a permanent-disability award and a self-procured
#: reimbursement, each at least a whole dollar.
#:
#: There was briefly a twenty-dollar *step* here too, adopted so the fifteen
#: percent attorney fee both documents truncate to whole dollars would be exact.
#: Review was right that it was the wrong abstraction: real settlements are not
#: multiples of twenty, and narrowing a **published** field to work around a
#: renderer's rounding makes the corpus systematically unrealistic in a figure
#: the analyzer is scored on. The fee is printed to cents instead.
#:
#: Which moved the binding constraint. The release subtracts more than the award
#: does, so the award's two-dollar split is no longer what decides the floor —
#: see :func:`settlement_deductions` and the search below. The floor is derived
#: from the deduction rule rather than asserted beside it, because the last three
#: defects in this module were all a bound somebody chose once and then stopped
#: re-deriving when the arithmetic under it moved.

#: The release's three deductions. Costs and the set-aside are fractions of the
#: gross rather than the substrate's flat $500-$3,000 and $5,000-$25,000 draws,
#: which knew nothing about the settlement they were subtracted from and printed
#: a negative net on a small one. Each is floored at a dollar so its row prints.
SETTLEMENT_FEE_RATE = Decimal("0.15")
SETTLEMENT_COSTS_DIVISOR = 40
SETTLEMENT_SET_ASIDE_DIVISOR = 5


def settlement_deductions(gross: int) -> tuple[Decimal, int, int]:
    """Fee, costs and Medicare set-aside for *gross*.

    One definition, imported by the renderer that prints these figures and by
    the floor derived from them, so the two cannot drift apart. The set-aside is
    returned whether or not the file has one; the caller drops it when
    ``lifecycle.resolution.msa`` is false, and the floor keeps it because the
    worst case is the case that pays it.
    """
    fee = (Decimal(gross) * SETTLEMENT_FEE_RATE).quantize(Decimal("0.01"))
    return fee, max(gross // SETTLEMENT_COSTS_DIVISOR, 1), max(
        gross // SETTLEMENT_SET_ASIDE_DIVISOR, 1
    )


def _smallest_gross_the_documents_can_carry() -> int:
    """Search up from the award's own two-line minimum until the release closes.

    Searched rather than stated. Both constraints are real — the award needs a
    dollar on each of its two lines, and the release must leave the applicant
    something after fee, costs and set-aside — and which of them binds depends
    on arithmetic three modules away. A search re-derives the answer every
    import; a literal would have to be remembered.
    """
    for gross in range(2, 1000):
        fee, costs, set_aside = settlement_deductions(gross)
        if Decimal(gross) - fee - Decimal(costs) - Decimal(set_aside) > 0:
            return gross
    raise AssertionError(
        "no settlement gross under $1,000 leaves the applicant money after the "
        "deductions in settlement_deductions — the deduction rule is wrong"
    )


SETTLEMENT_GROSS_MINIMUM = _smallest_gross_the_documents_can_carry()

class SettlementScenario(_Model):
    """How the money side of the case ended.

    Defined in Wave 1 rather than alongside the disbursement work, so the
    defense-lens and applicant-lens tickets can both attach to a settled object
    without waiting on each other.

    ``approval_date`` and ``funding_date`` are separate fields on purpose. They
    are separate events in a real file — the Board approves, and then somebody
    cuts a cheque — and the interval between them is exactly the fact a late
    funding argument is made of. Collapsing them into one date would delete the
    argument from the corpus.
    """

    gross_amount: float | None = Field(default=None, ge=0, le=10_000_000)
    """Gross settlement, before any deduction. Derived when unset."""

    approval_date: date | None = None
    """When the Board approved. Defaults to the file's own approval order date."""

    funding_days: int | None = Field(default=None, ge=0, le=730)
    """Days from approval to funding. Derived from diligence when unset."""

    funding_date: date | None = None
    """When the settlement was actually funded. Overrides ``funding_days``."""

    @model_validator(mode="after")
    def _gross_is_whole_dollars(self) -> SettlementScenario:
        """A gross the release cannot print is a gross the ledger must not claim.

        The substrate's compromise and release draws its gross as an integer and
        derives the fee, costs, set-aside and net from it; the engine pins that
        draw, and an integer is all it can pin. A ledger stating ``88000.99``
        therefore labels a document reading ``$88,000`` — measured, and off by
        99 cents, which in an arithmetic check is simply wrong.

        Refused rather than rounded, because rounding is the engine quietly
        overruling an explicit control. The author is told which way to go.
        """
        if self.gross_amount is None:
            return self
        if self.gross_amount != int(self.gross_amount):
            raise ValueError(
                f"scenario.settlement.gross_amount is {self.gross_amount} — the release "
                "that carries this figure prints whole dollars, so a ledger holding cents "
                "would label a document that contradicts it. State "
                f"scenario.settlement.gross_amount as a whole number of dollars "
                f"(for example {int(self.gross_amount)})."
            )
        return self

    @model_validator(mode="after")
    def _gross_is_large_enough_for_a_document_to_print(self) -> SettlementScenario:
        """A settlement too small to have components is one no award can state.

        `gross_amount: 0` and `1` were accepted here while the stipulated award
        silently skipped its reconciliation for them and printed a $27,581
        permanent-disability award beside a published $0.00. "Unreachable from a
        sane seed" is not a boundary when the schema accepts the value; either
        the schema refuses it or the document reconciles it.

        The floor is derived rather than invented. The stipulated award prints a
        permanent-disability award and a self-procured reimbursement that must
        sum to this figure, each at least a whole dollar, and the award carries
        a fifteen percent fee the substrate truncates to an integer — so the
        award must be a multiple of twenty for that fee to be the fifteen
        percent it says it is. Twenty plus one is the smallest total satisfying
        both.
        """
        if self.gross_amount is None:
            return self
        gross = int(self.gross_amount)
        if gross < SETTLEMENT_GROSS_MINIMUM:
            raise ValueError(
                f"scenario.settlement.gross_amount is {gross}, which is too small for "
                "the documents that carry it to print: the stipulated award splits it "
                "into a permanent-disability award and a self-procured reimbursement, "
                "each at least a whole dollar, and the release subtracts an attorney "
                "fee, costs and a Medicare set-aside from it and must still leave the "
                f"applicant money. Raise scenario.settlement.gross_amount to "
                f"{SETTLEMENT_GROSS_MINIMUM} or more, or remove scenario.settlement if "
                "this case did not settle for money."
            )
        return self

    @model_validator(mode="after")
    def _funding_is_stated_one_way(self) -> SettlementScenario:
        if self.funding_date is not None and self.funding_days is not None:
            raise ValueError(
                "scenario.settlement sets both funding_date and funding_days — the two "
                "would disagree the moment the approval date moves. Keep funding_date for "
                "an exact date, or funding_days for an interval, and drop the other."
            )
        for name in ("approval_date", "funding_date"):
            stated = getattr(self, name)
            if stated is not None and stated > ANCHOR_DATE:
                # Every document in the case is clamped to the anchor, so a
                # settlement dated past it is an event no paper in the folder can
                # report. Measured: `approval_date: 2099-01-01` loaded, published
                # a 2099 approval and a 2099 funding, and left every document in
                # the case dated 2026-01-01 or earlier.
                raise ValueError(
                    f"scenario.settlement.{name} is {stated}, after the anchor date "
                    f"{ANCHOR_DATE} this engine treats as today — every document in the "
                    "case is dated on or before it, so no paper in the folder could "
                    f"report this event. Move scenario.settlement.{name} to on or before "
                    f"{ANCHOR_DATE}."
                )
        if self.funding_date is not None and self.approval_date is None:
            # An exact funding date is only meaningful against the approval it
            # follows, and the approval it would otherwise be measured against is
            # derived from the timeline — which the seed cannot see. Left
            # unpaired, a 2024 funding date under a 2021 derived approval loaded
            # cleanly and published a negative funding lag; only ``validate --out``
            # caught it, one whole generation later.
            raise ValueError(
                "scenario.settlement sets funding_date without approval_date — the "
                "interval between them is the fact this pair exists to carry, and the "
                "approval it would be measured against is derived from the timeline, "
                "where this seed cannot see it. Add scenario.settlement.approval_date, "
                "or state funding_days instead and let the approval date lead it."
            )
        if (
            self.funding_date is not None
            and self.approval_date is not None
            and self.funding_date < self.approval_date
        ):
            raise ValueError(
                f"scenario.settlement.funding_date {self.funding_date} precedes "
                f"approval_date {self.approval_date} — money does not move before the "
                "Board approves. Move funding_date to on or after the approval, or correct "
                "the approval date."
            )
        return self


class PenaltyScenario(_Model):
    """Opt in to the automatic self-imposed increase on late indemnity.

    The block is deliberately optional. Its presence asks the engine to assess
    the late temporary-disability periods and permanent-disability advances the
    benefit ledger already decided; its absence preserves the pre-penalty code
    path and publishes no penalty claim. The default fraction is a
    counsel-unconfirmed statutory placeholder, so a seed may replace the figure
    and its authority without changing the arithmetic or inventing lateness.
    """

    increase_fraction: Decimal | None = None
    """Override the dated table's fraction; ``None`` keeps the table figure."""

    authority: str | None = Field(default=None, max_length=400)
    """Override the table's authority prose."""

    counsel_confirmed: bool = False

    @model_validator(mode="after")
    def _fraction_is_a_positive_share(self) -> PenaltyScenario:
        if self.increase_fraction is not None and not (
            Decimal("0") < self.increase_fraction <= Decimal("1")
        ):
            raise ValueError(
                "scenario.penalties.increase_fraction must be greater than 0 and no more "
                "than 1 — state the increase as a positive fraction, such as 0.10, or "
                "remove it to use the dated table."
            )
        return self

    @model_validator(mode="after")
    def _confirmed_authority_is_real(self) -> PenaltyScenario:
        if self.counsel_confirmed and (
            self.authority is None or "UNCONFIRMED" in self.authority.upper()
        ):
            raise ValueError(
                "scenario.penalties.counsel_confirmed is true but its authority is absent "
                "or still marked unconfirmed — add verified authority prose without the "
                "UNCONFIRMED marker, or set counsel_confirmed to false."
            )
        return self


class MedicalConditionEntry(_Model):
    """One pre-existing or concurrent condition the author states outright.

    Everything here is world truth — what the applicant actually had — never what a
    document says about it. A physician's characterisation of this condition is an
    assertion and belongs to M2's layer, which is why nothing on this model grades
    the condition or takes a side about it.
    """

    label: str = Field(min_length=1)
    """Free text, e.g. 'invasive ductal carcinoma, right breast'."""

    key: str | None = None
    """A :data:`~wc_caseload_engine.clinical_grounding.CONDITION_CATALOG` key, when
    the condition is one the catalog knows. ``None`` for anything else — the flagship
    wholly-unrelated stories are deliberately off-catalog, because a condition with a
    published prevalence curve is by definition not a rare event."""

    body_system: BodySystem = "musculoskeletal"
    body_part: str | None = None
    """``None`` for a systemic condition with no region. Distinct from 'unknown'."""

    icd10: str | None = None
    origin: Literal["industrial", "nonindustrial", "mixed"] = "nonindustrial"
    """The condition's actual causal category, not any party's position on it."""

    wholly_unrelated: bool | None = None
    """``None`` means *derive it* — from the catalog's apportionment targets against
    this claim's own regions, or from ``body_part`` for an off-catalog entry. State it
    to pin the case the derivation cannot see."""

    onset: date | None = None
    """``None`` is a legitimate state, not a gap: an incidental imaging finding has
    no onset date, which is exactly how a real chart carries it."""

    severity: Literal["subclinical", "mild", "moderate", "severe"] = "mild"
    trajectory: Literal["resolved", "stable", "progressive", "fluctuating"] = "stable"
    symptomatic_before_doi: bool | None = None
    """Was it already producing disability before the injury? Escobedo turns on this
    exactly: a nonindustrial factor must be shown to be causing disability *now*, not
    merely to be visible or to predate the injury."""

    surfaces_in_file: bool = True
    """Whether the file shows this condition anywhere.

    Defaults ``True`` for a stated condition and ``False`` for a drawn one, and the
    asymmetry is deliberate rather than an inconsistency: an author who names a
    condition is telling a story with it, while the drawn population is calibrated to
    the counsel-confirmed documentation rate. Set it ``False`` to author
    the case the two-surface gate exists for — a real condition the file never
    mentions.
    """

    billing_coded: bool = False
    """Coded in this claim's own billing. Implies ``surfaces_in_file``."""

    @model_validator(mode="after")
    def _key_is_a_catalog_key(self) -> MedicalConditionEntry:
        if self.key is not None and self.key not in CONDITION_CATALOG:
            known = ", ".join(sorted(CONDITION_CATALOG))
            raise ValueError(
                f"scenario.medical_history.conditions[].key is {self.key!r}, which is "
                f"not a grounding-catalog condition. Use one of: {known} — or drop the "
                "key entirely, which is the right answer for a condition the catalog "
                "has no prevalence curve for."
            )
        return self


class PriorAwardEntry(_Model):
    """A prior permanent-disability award — the section 4664(b) fact itself.

    Data model only in M1. No overlap arithmetic and no dollars: that is M5's, and it
    is gated on a counsel check that has not landed.
    """

    body_parts: list[str] = Field(min_length=1)
    pd_percent: int = Field(ge=1, le=100)
    award_date: date
    resolution_type: Literal["stipulated_award", "findings_and_award", "c_and_r"] | None = (
        None
    )
    """``None`` means the claim's own resolution, which is nearly always the answer.

    It used to default to ``stipulated_award``, and that default was a small trap: an
    award is not an independent event, it is *how the claim resolved*, so a default
    value here could contradict the claim it sits inside without anybody typing the
    contradiction. Writing it is still allowed — an author who states it explicitly
    means it — and :meth:`PriorClaimEntry._an_award_needs_a_resolution_that_can_produce_one`
    then checks the two agree.
    """

    conclusively_presumed: bool = False
    """Whether section 4664(b)'s presumption is taken to apply.

    Defaults ``False`` on the design record's conservative ruling: a compromise and
    release does not straightforwardly carry the same weight as a rated award, so the
    presumption is opted into rather than assumed. Not yet honoured — M5 owns the
    arithmetic this flag will govern.
    """


class PriorClaimEntry(_Model):
    """A workers' compensation claim the applicant filed before this one.

    Stated, never drawn. A prior claim is a discrete litigated event with its own
    dates, employer and resolution; sampling one would invent a case history no author
    asked for, which is a different thing from sampling a population-level condition.
    """

    body_parts: list[str] = Field(min_length=1)
    date_of_injury: date
    employer: str | None = None
    """``None`` means the same employer as this claim — the common pattern. A distinct
    value is what Benson framing turns on. Not yet honoured (M3)."""

    resolution_type: Literal[
        "c_and_r", "stipulated_award", "findings_and_award", "dismissed", "denied", "pending"
    ]
    resolution_date: date | None = None
    award: PriorAwardEntry | None = None
    """Set only where the claim produced a PD award. Independent of
    ``resolution_type`` rather than derived from it, so "claim happened, no award"
    stays representable."""

    @model_validator(mode="after")
    def _award_overlaps_its_own_claim(self) -> PriorClaimEntry:
        if self.award is not None and not set(self.award.body_parts) & set(self.body_parts):
            raise ValueError(
                "scenario.medical_history.prior_claims[].award.body_parts does not "
                "overlap the claim's own body_parts — an award for a region the claim "
                "never named cannot have come from that claim. Add the region to the "
                "claim's body_parts, or move the award to the claim it belongs to."
            )
        return self

    #: Resolutions that can produce a permanent-disability award, and their names.
    #:
    #: The other three cannot. ``denied`` and ``dismissed`` are the claim ending with
    #: nothing awarded; ``pending`` has not ended at all. A claim in one of those
    #: states carrying an award block is not an unusual case, it is two contradictory
    #: facts in one entry — and because :class:`PriorAwardEntry` defaults its own
    #: ``resolution_type`` to ``stipulated_award``, the contradiction could be created
    #: by writing nothing at all.
    AWARDING_RESOLUTIONS: ClassVar[frozenset[str]] = frozenset(
        {"c_and_r", "stipulated_award", "findings_and_award"}
    )

    @model_validator(mode="after")
    def _an_award_needs_a_resolution_that_can_produce_one(self) -> PriorClaimEntry:
        """A denied claim cannot hold an award, and a matching one cannot disagree.

        Two failures, one cause: nothing was comparing the claim's resolution with the
        award's. A ``denied`` claim with a default award block loaded cleanly, derived
        into the ledger, and grounded a SIBTF hook on evidence that says the opposite
        of what the hook needs — the Fund's argument *against* liability, read as
        evidence for it.

        The second clause is the one that would otherwise be found later: a
        ``c_and_r`` claim whose award says ``stipulated_award`` is a smaller
        contradiction than the first but the same kind, and the award's default value
        makes it the easy one to write by accident.
        """
        if self.award is None:
            return self
        if self.resolution_type not in self.AWARDING_RESOLUTIONS:
            raise ValueError(
                "scenario.medical_history.prior_claims[] carries an award block but "
                f"its resolution_type is {self.resolution_type!r} — a claim that was "
                "denied, dismissed or is still pending produced no permanent "
                "disability to award. The resolutions that can produce one are "
                f"{', '.join(sorted(self.AWARDING_RESOLUTIONS))}. Remove the award "
                "block, or change the claim's resolution_type to one of them."
            )
        if (
            self.award.resolution_type is not None
            and self.award.resolution_type != self.resolution_type
        ):
            raise ValueError(
                "scenario.medical_history.prior_claims[].award.resolution_type is "
                f"{self.award.resolution_type!r} but the claim resolved by "
                f"{self.resolution_type!r} — one award cannot have issued out of two "
                "different resolutions. Set the award's resolution_type to match the "
                "claim, or drop it and let it inherit."
            )
        return self

    @model_validator(mode="after")
    def _resolution_precedes_nothing_impossible(self) -> PriorClaimEntry:
        if self.resolution_date is not None and self.resolution_date < self.date_of_injury:
            raise ValueError(
                "scenario.medical_history.prior_claims[].resolution_date precedes its "
                "own date_of_injury — a claim cannot resolve before it arises. Correct "
                "the resolution_date, or correct the date_of_injury."
            )
        if self.award is not None and self.award.award_date < self.date_of_injury:
            raise ValueError(
                "scenario.medical_history.prior_claims[].award.award_date precedes the "
                "claim's date_of_injury — an award cannot issue before the injury it "
                "compensates. Correct the award_date, or correct the date_of_injury."
            )
        return self


class MedicalHistoryScenario(_Model):
    """The world-truth layer: what the applicant actually had, before any assertion.

    Its presence on :class:`ScenarioSpec` is the whole gate. Absent — the default —
    means this case has no medical-history layer at all, and produces output
    byte-identical to every case generated before this axis existed.
    """

    conditions: list[MedicalConditionEntry] = Field(default_factory=list, max_length=8)
    """Conditions stated outright. Always kept, and the sampler never contradicts one."""

    prior_claims: list[PriorClaimEntry] = Field(default_factory=list, max_length=5)

    archetype: Literal[
        "resilient", "metabolic", "degenerative", "psych_burdened", "multimorbid"
    ] | None = None
    """``None`` means *draw it* from the demographic mixture. Pin it to author a
    specific health profile. Not yet honoured (M3)."""

    sample_conditions: bool = True
    """Whether to draw conditions from the archetype on top of any stated above.

    ``True`` by default: opening this block asks for the world-truth layer, and a
    layer that only ever holds what an author typed cannot reproduce a population.
    Set ``False`` for a pinned showcase case whose story would be muddied by drawn
    comorbidities.
    """

    @model_validator(mode="after")
    def _a_pinned_archetype_needs_a_draw_to_pin(self) -> MedicalHistoryScenario:
        if self.archetype is not None and not self.sample_conditions:
            raise ValueError(
                "scenario.medical_history names an archetype but sets "
                "sample_conditions to false, so nothing draws from it and the "
                "archetype decides nothing. Set sample_conditions to true, or remove "
                "the archetype."
            )
        return self


class ScenarioSpec(_Model):
    """Seed-surfaced case facts.

    The axes of real-file variability this engine can currently *render*
    coherently. Deliberately small: an axis in the schema that no template
    honours is worse than an absent one, because it reads as a promise.
    """

    diagnostics: DiagnosticsScenario = Field(default_factory=DiagnosticsScenario)
    treatment: TreatmentScenario = Field(default_factory=TreatmentScenario)
    adjuster: AdjusterScenario = Field(default_factory=AdjusterScenario)
    attorney: AttorneyScenario = Field(default_factory=AttorneyScenario)
    discovery: DiscoveryScenario = Field(default_factory=DiscoveryScenario)
    wages: WageScenario | None = None
    """The money gate. ``None`` — the default — means this case has no money layer.

    Deliberately ``None`` rather than a default-constructed block. A present
    empty block and an absent one would be indistinguishable, and the whole
    anti-criterion rests on the engine being able to tell "the author asked for
    wage facts" from "the author said nothing".
    """

    benefits: BenefitsScenario | None = None
    """What was paid. Requires ``wages`` — see :meth:`_money_needs_a_wage_block`."""

    settlement: SettlementScenario | None = None
    """How the money ended. Requires ``wages`` — see the same validator."""
    penalties: PenaltyScenario | None = None
    """Automatic late-indemnity increases. Requires ``wages`` — see the same validator."""
    medical_history: MedicalHistoryScenario | None = None
    """The world-truth gate. Not yet honoured — no document renders it (M3).

    ``None`` — the default — means this case has no medical-history layer: no
    comorbidities, no prior claims, nothing an apportionment opinion could concretely
    reference. Deliberately ``None`` rather than a default-constructed block, and
    deliberately *not* auto-derived when absent, which is the opposite of what
    ``diagnostics`` does.

    The difference is that diagnostics had a prior existence. Templates were already
    drawing imaging independently, and the ledger's job was to make behaviour that
    already shipped coherent. Nothing today derives comorbidities or prior claims for
    any case, so auto-deriving them the moment this field existed would silently start
    populating history into every case in the demo caseload and every golden fixture —
    the uncontrolled blast radius the ``wages`` gate exists to prevent.

    So this follows ``wages``: an absent block moves zero bytes, and that is the
    instrument the whole milestone's back-compat claim is measured with.
    """

    surgery: Literal["none", "performed", "recommended", "denied_by_ur"] | None = None
    """``None`` means *derive it* — preserving the substrate's 35% coin exactly.

    ``recommended`` and ``denied_by_ur`` both mean no operation happened: one
    was proposed and is pending, the other was proposed and refused. Neither
    emits an operative document, and ``validate`` enforces their absence.
    """

    @model_validator(mode="after")
    def _money_needs_a_wage_block(self) -> ScenarioSpec:
        """One gate for the whole money layer, and it is the wage block.

        ``benefits``, ``settlement`` and ``penalties`` describe money moving. A benefit
        payment has a rate, and a rate is derived from an average weekly wage —
        so a benefits block with no wage facts behind it is exactly the asserted
        number this layer exists to replace with a derived one. The settlement
        is held to the same gate rather than a looser one of its own, because
        one gate is what makes "a seed with no wage block produces zero money
        artifacts" a single checkable sentence instead of three.
        """
        if self.wages is not None:
            return self
        stated = [
            name
            for name in ("benefits", "settlement", "penalties")
            if getattr(self, name) is not None
        ]
        if stated:
            raise ValueError(
                f"scenario.{' and scenario.'.join(stated)} needs scenario.wages — a "
                "benefit rate and a settlement both rest on an average weekly wage, and "
                "without an earnings history this engine would have to assert one. Add a "
                f"scenario.wages block, or remove scenario.{stated[0]}."
            )
        return self

    @model_validator(mode="after")
    def _never_treated_implies_no_surgery(self) -> ScenarioSpec:
        if self.treatment.status == "never_treated" and self.surgery not in (None, "none"):
            raise ValueError(
                "scenario.treatment.status is 'never_treated' but scenario.surgery is "
                f"{self.surgery!r} — an applicant who never treated did not have surgery "
                "proposed, denied or performed. Set scenario.surgery to 'none' (or drop "
                "it), or change scenario.treatment.status."
            )
        return self


class OutputSpec(_Model):
    """Filename policy and permitted output formats."""

    filename_style: FilenameStyle = "neutral"
    formats: list[DocumentFormat] = Field(
        default_factory=lambda: ["pdf", "scanned_pdf", "eml", "docx"]
    )

    @model_validator(mode="after")
    def _check_formats(self) -> OutputSpec:
        if not self.formats:
            raise ValueError(
                "output.formats must list at least one of: pdf, scanned_pdf, eml, docx"
            )
        duplicates = sorted({f for f in self.formats if self.formats.count(f) > 1})
        if duplicates:
            raise ValueError(f"output.formats has duplicates: {', '.join(duplicates)}")
        return self


class CaseSeed(_Model):
    """One synthetic case, fully specified. The unit Phase B renders."""

    case_id: str = Field(pattern=CASE_ID_PATTERN)
    rng_seed: int = Field(ge=0, lt=2**32)
    perspective: Perspective = "applicant"
    """Whose file this is. Top-level because it governs the whole document set.

    Deliberately *not* part of ``profile`` or ``documents``: it is neither a
    party fact nor a control knob, and it changes no case fact at all. Defaults
    to ``applicant`` so every seed written before this field existed loads and
    generates exactly as it did.
    """

    profile: CaseProfile = Field(default_factory=CaseProfile)
    injury: InjurySpec
    lifecycle: LifecycleSpec = Field(default_factory=LifecycleSpec)
    scenario: ScenarioSpec = Field(default_factory=ScenarioSpec)
    documents: DocumentControls = Field(default_factory=DocumentControls)
    output: OutputSpec = Field(default_factory=OutputSpec)

    @field_validator("injury", mode="before")
    @classmethod
    def _reject_repeated_body_parts(cls, value: Any, info: ValidationInfo) -> Any:
        """One claim cannot injure the same region twice.

        A repeated entry is not a second impairment, but ``benson`` and ``kite``
        both gate on there being two — so ``[lumbar_spine, lumbar_spine]`` used
        to satisfy Kite and put a synergistic-effect argument between a body
        part and itself into the file, silently. The seed is where an impossible
        story gets rejected (AJC-35 #25).

        ``InjurySpec`` enforces the same invariant, so why here as well? Because
        pydantic validates a nested model *before* the outer model's ``after``
        validators run, so the injury's own error would win and the message
        would lose the case name — and in a caseload of thirty, "some injury has
        a duplicate" is not an actionable error. ``mode="before"`` runs ahead of
        the nested construction, and ``case_id`` is declared above ``injury`` so
        it is already validated and present in ``info.data``.
        """
        parts = (
            value.get("body_parts")
            if isinstance(value, Mapping)
            else getattr(value, "body_parts", None)
        )
        if isinstance(parts, Sequence) and not isinstance(parts, str | bytes):
            repeated = InjurySpec.find_repeated_part(parts)
            if repeated is not None:
                raise ValueError(
                    _repeated_part_message(*repeated, case_id=info.data.get("case_id"))
                )
        return value

    @model_validator(mode="after")
    def _a_fatal_injury_has_no_disability_benefits_to_pay(self) -> CaseSeed:
        """Money on a death claim is a different benefit class, and it is not built yet.

        ``scenario.wages`` on a fatal injury loaded cleanly and derived ordinary
        temporary and permanent disability from it. Measured: a death on
        2023-01-19 published a first temporary-disability period running
        2023-01-22 to 2023-02-18 — begun three days after the worker died —
        thirteen periods totalling $39,133.85, and two permanent-disability
        advances. Permanent disability is a rating of a living worker's residual
        capacity and temporary disability replaces wages the worker would have
        earned; neither survives the worker.

        What a fatal claim actually pays is dependency benefits and burial
        expenses, which are a different computation with different rules and no
        model here. So this is refused rather than approximated, on the rule
        that governs the rest of this schema: an impossible seed is rejected,
        not absorbed. The dependency ontology is a Wave 2 ticket; when it lands
        this validator is what gets replaced.
        """
        if self.injury.type != "death":
            return self
        stated = [
            name
            for name in ("wages", "benefits", "settlement")
            if getattr(self.scenario, name, None) is not None
        ]
        if stated:
            raise ValueError(
                f"injury.type is 'death' but scenario states {', '.join(sorted(stated))} — "
                "the money layer computes temporary and permanent disability, which are "
                "benefits of a living worker, and a fatal claim pays dependency benefits "
                "instead. Remove the money blocks from this seed, or change injury.type "
                "to 'specific' or 'cumulative_trauma'."
            )
        return self

    @model_validator(mode="after")
    def _a_prior_claim_precedes_the_current_injury(self) -> CaseSeed:
        """"Prior" is a claim about order, and nothing was enforcing it.

        :class:`PriorClaimEntry` can police its own internal dates — a claim cannot
        resolve before it arises, an award cannot issue before the injury it
        compensates — but it cannot see the injury it is prior *to*. So a claim dated
        after the current injury loaded cleanly, derived into the ledger as a prior
        claim, and every §4664 and Benson hook downstream would have read it as
        predating the injury it postdates.

        **Strictly before.** Two claims arising the same day are not a prior and a
        current; they are one event pleaded twice, or a data error. Either reading
        makes the seed wrong, and ``<=`` would have admitted it.

        **Only the injury date carries the ordering claim.** A prior claim still
        resolving when the new injury happens is ordinary — a 2019 injury resolving
        in 2023 is a slow but unremarkable file, and an open prior claim is precisely
        the fact pattern a §4664 apportionment argument turns on. So the resolution
        date, the award date and the claim's status are all deliberately unchecked
        here.

        **CT compares against ``onset_date``, which is the later bound.** A specific
        injury arising inside an ongoing cumulative-trauma exposure period is
        therefore admitted, and that is the right call: a worker whose back is
        accumulating damage over three years can also drop a crate on their foot in
        year two. Rejecting that would refuse a real fact pattern in order to tidy an
        edge. What stays refused is only what is impossible.
        """
        history = self.scenario.medical_history
        if history is None or not history.prior_claims:
            return self
        onset = self.injury.onset_date
        for index, claim in enumerate(history.prior_claims):
            if claim.date_of_injury < onset:
                continue
            raise ValueError(
                f"scenario.medical_history.prior_claims[{index}].date_of_injury "
                f"({claim.date_of_injury.isoformat()}) does not precede the current "
                f"injury ({onset.isoformat()}) — a prior claim has to arise before the "
                "claim it is prior to, and one arising the same day is the same event "
                "pleaded twice. Move the prior claim's date_of_injury earlier, or move "
                "injury.date_of_injury later."
            )
        return self

    @model_validator(mode="after")
    def _check_scenario_against_the_lifecycle(self) -> CaseSeed:
        """Cross-validate the scenario against fields it cannot see from inside.

        ``ScenarioSpec`` can police itself, but ``never_treated`` contradicts a
        lien block and ``denied_by_ur`` depends on one, and both of those live
        under ``lifecycle``. Every message names both sides and the edit that
        resolves it: an error that says only "incompatible" leaves the author
        guessing which field to change.
        """
        scenario = self.scenario

        if scenario.treatment.status == "never_treated":
            offenders = sorted(
                {c for c in self.lifecycle.liens.claimants if c in TREATMENT_LIEN_CLAIMANTS}
            )
            if offenders:
                raise ValueError(
                    "scenario.treatment.status is 'never_treated' but "
                    f"lifecycle.liens.claimants includes {', '.join(offenders)} — a "
                    "provider, hospital or pharmacy only holds a lien for treatment it "
                    "gave. Drop those claimants (edd, ambulance, attorney_costs and "
                    "self_procured are compatible), or change the treatment status."
                )

        if scenario.surgery == "denied_by_ur":
            ur = self.lifecycle.ur_dispute
            if not ur.enabled:
                raise ValueError(
                    "scenario.surgery is 'denied_by_ur' but lifecycle.ur_dispute.enabled "
                    "is false — a denial needs the utilization review that issued it. Add "
                    "'lifecycle: {ur_dispute: {enabled: true, decision: upheld}}' to this "
                    "seed, or use scenario.surgery: 'recommended' for a request that was "
                    "never adjudicated. This is not auto-enabled: a UR dispute pulls in "
                    "an RFA, a determination and an IMR window, and the seed is the "
                    "contract."
                )
            if ur.decision != "upheld":
                # ``overturned`` contradicts the surgery outright, and an unstated
                # decision resolves through the substrate's
                # ``rng.choice(["approved", "denied"])`` — so it can *become*
                # overturned, non-deterministically from the author's point of view.
                # Both produce the same file: a treating report saying the request was
                # denied and under appeal, next to the authorization that approved it.
                # An explicit ``upheld`` is the only state in which the denial stands.
                stated = f"is {ur.decision!r}" if ur.decision else "is unset"
                consequence = (
                    "which approves the request the ledger says was refused"
                    if ur.decision == "overturned"
                    else "which resolves at random and can approve the request the "
                    "ledger says was refused"
                )
                raise ValueError(
                    f"scenario.surgery is 'denied_by_ur' but lifecycle.ur_dispute."
                    f"decision {stated}, {consequence}. Set "
                    "'lifecycle: {ur_dispute: {decision: upheld}}' so the denial stands, "
                    "or use scenario.surgery: 'recommended' if the request is still "
                    "pending. ('upheld' and 'overturned' are the only values; the seed "
                    "speaks from the dispute's point of view, so 'upheld' means the UR "
                    "denial was upheld.)"
                )

        if scenario.settlement is not None and self.lifecycle.resolution.type not in (
            "c_and_r",
            "stipulations",
        ):
            # A settlement object on a case that did not settle would publish an
            # approval date for an order the file does not contain. The two
            # resolution types that *are* settlements are named rather than
            # inferred, because ``findings_award`` and ``take_nothing`` are also
            # endings and neither is one anybody funds.
            raise ValueError(
                "scenario.settlement is set but lifecycle.resolution.type is "
                f"{self.lifecycle.resolution.type!r} — only a compromise and release or "
                "stipulations is a settlement anybody approves and funds. Set "
                "'lifecycle: {resolution: {type: c_and_r}}' (or 'stipulations'), or remove "
                "scenario.settlement."
            )

        if scenario.wages is not None:
            wages = scenario.wages
            start = wages.employment_start
            if start is not None and start > self.injury.onset_date:
                raise ValueError(
                    f"scenario.wages.employment_start {start} is after the injury on "
                    f"{self.injury.onset_date} — nobody is hurt at a job they have not "
                    "started. Move employment_start to on or before the injury, or correct "
                    "the injury date."
                )
            after = sorted(
                str(entry.period_end)
                for entry in wages.earnings
                if entry.period_end > self.injury.onset_date
            )
            if after:
                raise ValueError(
                    "scenario.wages.earnings has "
                    f"{len(after)} period(s) ending after the injury on "
                    f"{self.injury.onset_date} (first: {after[0]}) — the average weekly "
                    "wage is computed from earnings *before* the injury, so a later period "
                    "would silently be ignored. Remove those periods, or move "
                    "injury.date_of_injury later."
                )

        return self

    @model_validator(mode="after")
    def _check_runway(self) -> CaseSeed:
        """Reject an injury date too close to the anchor for the seeded story.

        Fail-loud rather than silently compressible: the lifecycle used to
        absorb a short runway by clamping every over-horizon date onto the
        anchor, which inverted the date spine — a reconsideration petition
        landing *before* the Application for Adjudication it appealed from.
        """
        required = required_runway_days(self.lifecycle)
        onset = self.injury.onset_date
        latest = ANCHOR_DATE - timedelta(days=required)
        if onset <= latest:
            return self

        field = (
            "injury.ct_end"
            if self.injury.type == "cumulative_trauma"
            else "injury.date_of_injury"
        )
        available = (ANCHOR_DATE - onset).days
        raise ValueError(
            f"{field} is {onset.isoformat()}, which leaves {available} day(s) before the "
            f"{ANCHOR_DATE.isoformat()} anchor, but {runway_driver(self.lifecycle)} needs at "
            f"least {required}. Move {field} to {latest.isoformat()} or earlier, or seed a "
            f"lifecycle that reaches less far."
        )

    def effective_format_mix(self) -> dict[str, float]:
        """Format weights restricted to ``output.formats`` and normalized to 1.0."""
        allowed = set(self.output.formats)
        mix = {k: v for k, v in self.documents.format_mix.items() if k in allowed and v > 0}
        if not mix:
            raise SeedError(
                f"case {self.case_id}: documents.format_mix has no positive weight for any "
                f"format in output.formats ({', '.join(self.output.formats)})"
            )
        total = sum(mix.values())
        return {k: v / total for k, v in sorted(mix.items())}

    def seed_hash(self) -> str:
        """Stable hash of the seed content — provenance for manifests."""
        payload = yaml.safe_dump(
            self.model_dump(mode="json", exclude_none=True), sort_keys=True
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def rng(self, salt: str = "") -> random.Random:
        """A deterministic ``Random`` derived from ``rng_seed`` (+ optional salt)."""
        return random.Random(derive_seed(self.rng_seed, salt))


class AutoSpec(_Model):
    """Auto-derivation block: N cases drawn from a calibrated distribution."""

    count: int = Field(ge=1, le=500)
    distribution: DistributionName = "balanced"
    rng_seed: int = Field(default=0, ge=0, lt=2**32)


class CaseloadSpec(_Model):
    """A caseload: shared defaults, explicit cases, and/or auto-derived cases."""

    caseload_id: str = Field(pattern=CASE_ID_PATTERN)
    defaults: dict[str, Any] = Field(default_factory=dict)
    cases: list[CaseSeed] = Field(default_factory=list)
    auto: AutoSpec | None = None

    @model_validator(mode="after")
    def _check_nonempty(self) -> CaseloadSpec:
        if not self.cases and self.auto is None:
            raise ValueError("caseload needs at least one entry in 'cases' or an 'auto' block")
        ids = [case.case_id for case in self.cases]
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        if duplicates:
            raise ValueError(f"duplicate case_id values in cases[]: {', '.join(duplicates)}")
        return self


# ---------------------------------------------------------------------------
# Deep merge + loading
# ---------------------------------------------------------------------------


def deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    """Recursively merge *override* onto *base* without mutating either.

    Mappings merge key-wise; every other value (including lists) is replaced
    wholesale by *override* — a case that names ``documents.exclude`` replaces
    the default list rather than appending to it.
    """
    merged: dict[str, Any] = dict(base)
    for key, value in override.items():
        current = merged.get(key)
        if isinstance(current, Mapping) and isinstance(value, Mapping):
            merged[key] = deep_merge(current, value)
        else:
            merged[key] = value
    return merged


def _format_errors(exc: ValidationError, *, source: str, prefix: str = "") -> str:
    """Render a Pydantic error into an actionable, field-path-precise report."""
    lines = [f"{source}: {exc.error_count()} validation error(s)"]
    for error in exc.errors():
        loc = ".".join(str(part) for part in error["loc"]) or "<root>"
        path = f"{prefix}{loc}" if prefix else loc
        message = error["msg"]
        expected = error.get("ctx", {}).get("expected")
        if expected and "allowed" not in message.lower():
            message = f"{message} (allowed: {expected})"
        if error["type"] == "extra_forbidden":
            message = "unknown field — remove it or fix the spelling"
        given = error.get("input")
        if isinstance(given, dict | list):
            rendered_input = f"<{type(given).__name__}>"
        else:
            rendered_input = repr(given)
        lines.append(f"  {path}: {message} [got {rendered_input}]")
    return "\n".join(lines)


def parse_case_seed(
    raw: Mapping[str, Any], *, source: str = "<dict>", prefix: str = ""
) -> CaseSeed:
    """Validate a raw mapping into a :class:`CaseSeed` with actionable errors."""
    try:
        return CaseSeed.model_validate(dict(raw))
    except ValidationError as exc:
        raise SeedValidationError(
            _format_errors(exc, source=source, prefix=prefix),
            source=source,
            errors=exc.errors(),
        ) from exc


def _read_yaml(path: Path | str) -> dict[str, Any]:
    """Read a YAML mapping from disk with clear failures."""
    file_path = Path(path)
    if not file_path.is_file():
        raise SeedError(f"{file_path}: file not found")
    try:
        loaded = yaml.safe_load(file_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise SeedError(f"{file_path}: invalid YAML — {exc}") from exc
    if loaded is None:
        raise SeedError(f"{file_path}: file is empty")
    if not isinstance(loaded, Mapping):
        raise SeedError(f"{file_path}: expected a YAML mapping, got {type(loaded).__name__}")
    return dict(loaded)


def load_case_seed(path: Path | str) -> CaseSeed:
    """Load one ``seed.yaml`` into a :class:`CaseSeed`."""
    return parse_case_seed(_read_yaml(path), source=str(path))


def parse_caseload_spec(raw: Mapping[str, Any], *, source: str = "<dict>") -> CaseloadSpec:
    """Validate a caseload mapping, deep-merging ``defaults`` under each case."""
    data = dict(raw)
    defaults = data.get("defaults") or {}
    if not isinstance(defaults, Mapping):
        raise SeedError(f"{source}: 'defaults' must be a mapping, got {type(defaults).__name__}")

    raw_cases = data.get("cases") or []
    if not isinstance(raw_cases, Sequence) or isinstance(raw_cases, str | bytes):
        raise SeedError(f"{source}: 'cases' must be a list")

    merged_cases: list[dict[str, Any]] = []
    for index, case in enumerate(raw_cases):
        if not isinstance(case, Mapping):
            raise SeedError(f"{source}: cases[{index}] must be a mapping")
        merged_cases.append(deep_merge(defaults, case))
    data["cases"] = merged_cases

    try:
        return CaseloadSpec.model_validate(data)
    except ValidationError as exc:
        raise SeedValidationError(
            _format_errors(exc, source=source), source=source, errors=exc.errors()
        ) from exc


def load_caseload_spec(path: Path | str) -> CaseloadSpec:
    """Load a caseload spec YAML (defaults already merged into each case)."""
    return parse_caseload_spec(_read_yaml(path), source=str(path))


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def seed_to_dict(seed: CaseSeed) -> dict[str, Any]:
    """JSON-safe dict of a seed, dropping ``None`` placeholders."""
    return seed.model_dump(mode="json", exclude_none=True)


def dump_case_seed(seed: CaseSeed) -> str:
    """Serialize a :class:`CaseSeed` back to clean, schema-ordered YAML."""
    header = (
        f"# wc-caseload seed — case {seed.case_id}\n"
        "# Regenerate this exact case with:\n"
        f"#   wc-caseload generate --spec <spec.yaml> --out <dir>   (rng_seed {seed.rng_seed})\n"
    )
    body = yaml.safe_dump(
        seed_to_dict(seed),
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
        width=100,
    )
    return header + body


def write_case_seed(seed: CaseSeed, path: Path | str) -> Path:
    """Write ``seed.yaml`` for a case, creating parent directories."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(dump_case_seed(seed), encoding="utf-8")
    return target


# ---------------------------------------------------------------------------
# Deterministic derivation
# ---------------------------------------------------------------------------


def derive_seed(base_seed: int, salt: str = "") -> int:
    """Derive a stable 32-bit sub-seed from *base_seed* and *salt*.

    Uses SHA-256 rather than :func:`hash` — Python's string hashing is
    ``PYTHONHASHSEED``-dependent and would break determinism across runs.
    """
    digest = hashlib.sha256(f"{base_seed}:{salt}".encode()).digest()
    return int.from_bytes(digest[:4], "big")


@dataclass(frozen=True, slots=True)
class DistributionProfile:
    """Calibrated draw weights for one ``auto.distribution`` preset."""

    name: str
    description: str
    stages: Mapping[str, float]
    claim_responses: Mapping[str, float]
    injury_types: Mapping[str, float]
    body_part_categories: Mapping[str, float]
    complex_rate: float
    ur_dispute_rate: float
    imr_rate: float
    lien_rate: float
    lien_count_range: tuple[int, int]
    recon_rate: float
    doctrine_hook_rate: float
    msa_rate: float


# Calibration source: /home/vncuser/projects/wc-knowledge-base/docs/
# PRD-WC-ATTORNEY-MOCK-CASELOAD.md section 3 + Appendices A-E (47-case caseload).
#   Stage       intake 11 / active_tx 15 / discovery 13 / med-legal 19 /
#               settlement 23 / resolved 13
#   Injury      specific 70 / CT 26 / death 4
#   Response    accepted 64 / denied 19 / delayed 17
#   Complexity  standard 55 / complex 45
#   Body part   spine 36 / upper 21 / lower 17 / internal 9 / psyche 6 / head 6
#               (n/a 4 -> death cases)
# The PRD's six stage rows sum to 94% (rounding); the engine allots the 6%
# remainder to `post_recon`, a stage the PRD predates. Rates the PRD does not
# quantify (UR/IMR, liens, recon, MSA, doctrine hooks) are set from the
# substrate's lifecycle branch probabilities (data/lifecycle_engine.py header).

_PRD_BODY_PARTS: Mapping[str, float] = {
    "spine": 0.36,
    "upper_extremity": 0.21,
    "lower_extremity": 0.17,
    "internal": 0.09,
    "psyche": 0.06,
    "head": 0.06,
}

DISTRIBUTIONS: Mapping[str, DistributionProfile] = {
    "balanced": DistributionProfile(
        name="balanced",
        description="PRD §3 attorney-caseload mix — every stage represented, med-legal heavy",
        stages={
            "intake": 0.11,
            "active_treatment": 0.15,
            "discovery": 0.13,
            "medical_legal": 0.19,
            "pre_trial": 0.23,
            "resolved": 0.13,
            "post_recon": 0.06,
        },
        claim_responses={"accepted": 0.64, "denied": 0.19, "delayed": 0.17},
        injury_types={"specific": 0.70, "cumulative_trauma": 0.26, "death": 0.04},
        body_part_categories=_PRD_BODY_PARTS,
        complex_rate=0.45,
        ur_dispute_rate=0.40,
        imr_rate=0.50,
        lien_rate=0.30,
        lien_count_range=(1, 3),
        recon_rate=0.10,
        doctrine_hook_rate=0.35,
        msa_rate=0.15,
    ),
    "early_stage": DistributionProfile(
        name="early_stage",
        description="Fresh files — intake through discovery, nothing resolved",
        stages={
            "intake": 0.40,
            "active_treatment": 0.35,
            "discovery": 0.20,
            "medical_legal": 0.05,
            "pre_trial": 0.0,
            "resolved": 0.0,
            "post_recon": 0.0,
        },
        claim_responses={"accepted": 0.55, "denied": 0.25, "delayed": 0.20},
        injury_types={"specific": 0.78, "cumulative_trauma": 0.20, "death": 0.02},
        body_part_categories=_PRD_BODY_PARTS,
        complex_rate=0.25,
        ur_dispute_rate=0.25,
        imr_rate=0.35,
        lien_rate=0.10,
        lien_count_range=(1, 2),
        recon_rate=0.0,
        doctrine_hook_rate=0.15,
        msa_rate=0.0,
    ),
    "settlement_heavy": DistributionProfile(
        name="settlement_heavy",
        description="Files at or past settlement — C&R and stips dominate",
        stages={
            "intake": 0.0,
            "active_treatment": 0.05,
            "discovery": 0.05,
            "medical_legal": 0.15,
            "pre_trial": 0.45,
            "resolved": 0.28,
            "post_recon": 0.02,
        },
        claim_responses={"accepted": 0.70, "denied": 0.15, "delayed": 0.15},
        injury_types={"specific": 0.68, "cumulative_trauma": 0.29, "death": 0.03},
        body_part_categories=_PRD_BODY_PARTS,
        complex_rate=0.40,
        ur_dispute_rate=0.35,
        imr_rate=0.45,
        lien_rate=0.55,
        lien_count_range=(1, 4),
        recon_rate=0.05,
        doctrine_hook_rate=0.30,
        msa_rate=0.30,
    ),
    "complex_litigation": DistributionProfile(
        name="complex_litigation",
        description="Litigated files — trials, liens, reconsideration round trips, doctrines",
        stages={
            "intake": 0.0,
            "active_treatment": 0.05,
            "discovery": 0.15,
            "medical_legal": 0.25,
            "pre_trial": 0.20,
            "resolved": 0.15,
            "post_recon": 0.20,
        },
        claim_responses={"accepted": 0.40, "denied": 0.38, "delayed": 0.22},
        injury_types={"specific": 0.60, "cumulative_trauma": 0.32, "death": 0.08},
        body_part_categories=_PRD_BODY_PARTS,
        complex_rate=0.90,
        ur_dispute_rate=0.65,
        imr_rate=0.70,
        lien_rate=0.75,
        lien_count_range=(2, 6),
        recon_rate=0.55,
        doctrine_hook_rate=0.85,
        msa_rate=0.35,
    ),
}
"""Auto-derivation presets. ``balanced`` mirrors the KB PRD; the rest re-weight it."""

BODY_PART_CATALOG: Mapping[str, tuple[tuple[str, str, str], ...]] = {
    "spine": (
        ("lumbar_spine", "M54.5", "L4-L5 disc protrusion"),
        ("cervical_spine", "M54.2", "C5-C6 disc bulge"),
        ("thoracic_spine", "M54.6", "T7-T8 strain"),
    ),
    "upper_extremity": (
        ("shoulder", "M75.100", "rotator cuff tear"),
        ("wrist", "G56.00", "carpal tunnel syndrome"),
        ("elbow", "M77.10", "lateral epicondylitis"),
        ("hand", "M79.641", "grip strength loss"),
    ),
    "lower_extremity": (
        ("knee", "M23.51", "medial meniscus tear"),
        ("ankle", "S93.401", "lateral ligament sprain"),
        ("hip", "M25.551", "labral tear"),
        ("foot", "M79.671", "plantar fasciitis"),
    ),
    "psyche": (
        ("psyche", "F43.10", "post-traumatic stress"),
        ("psyche", "F32.1", "major depressive disorder, moderate"),
    ),
    "head": (
        ("head", "S06.0X0A", "concussion without loss of consciousness"),
        ("head", "H53.2", "post-traumatic diplopia"),
    ),
    "internal": (
        ("internal", "I25.10", "cardiac — atherosclerotic heart disease"),
        ("internal", "J45.909", "respiratory — occupational asthma"),
        ("internal", "K43.9", "hernia, ventral"),
    ),
}
"""Body parts with ICD-10 codes by PRD body-part category."""

_LIEN_CLAIMANT_POOL: tuple[str, ...] = (
    "medical_provider",
    "hospital",
    "pharmacy",
    "ambulance",
    "edd",
    "attorney_costs",
    "self_procured",
)

_LIEN_RESOLUTIONS: tuple[str, ...] = (
    "lien_resolution_agreement",
    "lien_stipulation",
    "dismissal",
    "order_on_lien",
    "mixed",
)

_DOCTRINE_POOL: tuple[str, ...] = tuple(DOCTRINE_CONTENT)
"""Hooks ``auto:`` derivation may draw, in content-table order (AJC-60).

Read from :data:`~wc_caseload_engine.doctrine.DOCTRINE_CONTENT` rather than
transcribed, because the transcription had already drifted: thirteen entries
against the table's fourteen, with ``death_dependency`` present in the table,
accepted by the schema, and reachable only by naming it in a seed. A hand-kept
third copy of a list two other places already agree on is a drift waiting to
happen, and the next hook added is the one that would have inherited it.

Derived in **insertion order, not sorted**. ``_derive_doctrine_hooks`` shuffles
this sequence, so its order is an input to every ``auto:`` draw — sorting it
would silently re-roll every auto-derived caseload. Insertion order preserves
the thirteen entries' existing relative positions exactly.
"""

_MECHANISMS: Mapping[str, tuple[str, ...]] = {
    "specific": (
        "lifting a pallet of stock from a floor-level rack",
        "slip and fall on a wet loading dock",
        "struck by falling inventory during a restock",
        "motor vehicle accident while driving a company route",
        "ladder collapse during a maintenance call",
    ),
    "cumulative_trauma": (
        "repetitive keyboard and mouse use over a multi-year assignment",
        "repetitive overhead reaching on an assembly line",
        "continuous heavy lifting across a warehouse shift rotation",
        "prolonged vibration exposure operating heavy equipment",
    ),
    "death": (
        "fatal fall from an unguarded elevated platform",
        "fatal motor vehicle accident on a delivery route",
        "fatal cardiac event during an emergency response shift",
    ),
}

# Stage → (age of the injury in days, resolution weights). Later stages have
# older injuries and firmer resolutions.
_STAGE_AGE_DAYS: Mapping[str, tuple[int, int]] = {
    # Widened from (30, 75) when the denial-response chain got a runway floor:
    # a derived intake case can draw ``claim_response: denied``, and 30 days is
    # not enough calendar for a denial letter and the Application answering it.
    "intake": (90, 165),
    "active_treatment": (240, 360),
    "discovery": (240, 480),
    "medical_legal": (365, 640),
    "pre_trial": (540, 900),
    "resolved": (720, 1200),
    "post_recon": (900, 1500),
}
"""How old a derived case's injury is, per stage.

Each lower bound is at or above the corresponding runway floor, and
:func:`_derive_injury` raises it further at run time rather than trusting this
table to stay in step — so a derived seed can never fail the validation in
:meth:`CaseSeed._check_runway`, no matter how the windows are later tuned.
"""

_STAGE_RESOLUTIONS: Mapping[str, Mapping[str, float]] = {
    "intake": {"pending": 1.0},
    "active_treatment": {"pending": 1.0},
    "discovery": {"pending": 1.0},
    "medical_legal": {"pending": 1.0},
    "pre_trial": {"pending": 0.55, "c_and_r": 0.25, "stipulations": 0.20},
    "resolved": {
        "c_and_r": 0.40,
        "stipulations": 0.35,
        "findings_award": 0.18,
        "take_nothing": 0.07,
    },
    "post_recon": {"findings_award": 0.60, "stipulations": 0.22, "c_and_r": 0.18},
}

_STAGE_EVALS: Mapping[str, Mapping[str, float]] = {
    "intake": {"none": 1.0},
    "active_treatment": {"none": 0.75, "qme": 0.25},
    "discovery": {"qme": 0.55, "ame": 0.15, "none": 0.30},
    "medical_legal": {"qme": 0.65, "ame": 0.30, "none": 0.05},
    "pre_trial": {"qme": 0.60, "ame": 0.35, "none": 0.05},
    "resolved": {"qme": 0.60, "ame": 0.35, "none": 0.05},
    "post_recon": {"qme": 0.55, "ame": 0.45},
}

_RESOLVED_STAGES: frozenset[str] = frozenset({"resolved", "post_recon"})


def _weighted_choice(rng: random.Random, weights: Mapping[str, float]) -> str:
    """Deterministic weighted pick; ignores zero/negative weights."""
    positive = [(key, float(value)) for key, value in weights.items() if value > 0]
    if not positive:
        raise SeedError(f"no positive weights to choose from: {dict(weights)}")
    total = sum(weight for _, weight in positive)
    roll = rng.random() * total
    upto = 0.0
    for key, weight in positive:
        upto += weight
        if roll <= upto:
            return key
    return positive[-1][0]


def _derive_body_parts(rng: random.Random, category: str, count: int) -> list[BodyPart]:
    """Pick up to *count* distinct body parts, starting in *category*.

    Distinctness is enforced by part name, not by catalog position.
    ``BODY_PART_CATALOG`` lists several regions more than once *within* a single
    category — ``psyche`` twice, ``head`` twice, ``internal`` three times, each
    entry a different ICD-10 code and detail — so shuffling a category pool and
    slicing it returned the same region repeatedly. About 8% of auto-derived
    seeds carried a repeat, which ``benson`` and ``kite`` then counted as two
    impairments (AJC-35 #25).

    A narrow category can therefore yield fewer than *count* parts once the
    other categories are exhausted too. That is the intended trade: a case with
    one impairment is ordinary, whereas a case claiming the same region twice is
    not a case at all.
    """
    chosen: list[tuple[str, str, str]] = []
    seen: set[str] = set()

    def take(entries: Iterable[tuple[str, str, str]]) -> None:
        for part, icd10, detail in entries:
            if len(chosen) == count:
                return
            key = part.strip().casefold()
            if key in seen:
                continue
            seen.add(key)
            chosen.append((part, icd10, detail))

    pool: list[tuple[str, str, str]] = list(BODY_PART_CATALOG[category])
    rng.shuffle(pool)
    take(pool)

    # The second shuffle stays behind the same condition it has always been
    # behind. Draining the category pool first and only reaching for other
    # categories when it came up short means a seed whose category pool already
    # held `count` distinct parts consumes exactly the RNG it used to, and so
    # regenerates byte-identically. Only seeds that were previously served a
    # repeat — the ones whose output had to change anyway — reach this branch
    # newly.
    if len(chosen) < count:
        others = [
            entry
            for other, entries in sorted(BODY_PART_CATALOG.items())
            if other != category
            for entry in entries
        ]
        rng.shuffle(others)
        take(others)

    return [BodyPart(part=part, icd10=icd10, detail=detail) for part, icd10, detail in chosen]


def _stage_runway_floor(stage: str) -> int:
    """The worst-case runway any lifecycle at *stage* can demand.

    :func:`_derive_injury` runs before the lifecycle exists, so it assumes the
    most demanding shape the stage can still take. Three families of demand:

    * *Stage reach* — the resolved stages can go on to draw reconsideration or
      post-resolution lien litigation, and both need
      :data:`POST_RESOLUTION_RUNWAY_DAYS`; ``pre_trial`` can settle the
      case-in-chief (``_STAGE_RESOLUTIONS['pre_trial']``).
    * *Branches available at every stage* — ``claim_responses`` includes
      ``denied`` in every distribution, so the denial chain's floor applies
      everywhere.
    * *Branches the stage can draw* — UR/IMR is suppressed at ``intake``
      (:func:`_derive_ur_dispute`) and an evaluation is impossible there
      (``_STAGE_EVALS['intake']`` is ``none`` with probability 1), so those two
      floors apply from ``active_treatment`` on.

    Keeping this in step with :func:`runway_demands` by hand is the one way
    auto-derivation can start emitting seeds its own validator rejects, which is
    why ``TestAutoDerivedSeedsAreCompliant`` draws sixty per distribution rather
    than trusting the table.
    """
    floor = max(STAGE_RUNWAY_DAYS[stage], DENIAL_RESPONSE_RUNWAY_DAYS)
    if stage != "intake":
        floor = max(floor, UR_DISPUTE_RUNWAY_DAYS, IMR_RUNWAY_DAYS, EVAL_RUNWAY_DAYS)
    if stage in _RESOLVED_STAGES:
        return max(floor, RESOLVED_RUNWAY_DAYS, POST_RESOLUTION_RUNWAY_DAYS)
    if stage == "pre_trial":
        return max(floor, RESOLVED_RUNWAY_DAYS)
    return floor


def _derive_injury(rng: random.Random, profile: DistributionProfile, stage: str) -> InjurySpec:
    """Derive the injury block for one case, always leaving statutory runway."""
    injury_type = _weighted_choice(rng, profile.injury_types)
    category = _weighted_choice(rng, profile.body_part_categories)
    low, high = _STAGE_AGE_DAYS[stage]
    low = max(low, _stage_runway_floor(stage))
    high = max(high, low)
    age_days = rng.randint(low, high)
    onset = ANCHOR_DATE - timedelta(days=age_days)
    part_count = 1 if rng.random() > profile.complex_rate else rng.randint(2, 5)
    if injury_type == "death":
        part_count = 1
    body_parts = _derive_body_parts(rng, category, part_count)
    mechanism = rng.choice(_MECHANISMS[injury_type])

    if injury_type == "cumulative_trauma":
        ct_span = rng.randint(180, 1460)
        return InjurySpec(
            type="cumulative_trauma",
            ct_start=onset - timedelta(days=ct_span),
            ct_end=onset,
            body_parts=body_parts,
            mechanism=mechanism,
        )
    return InjurySpec(
        type=injury_type,  # type: ignore[arg-type]
        date_of_injury=onset,
        body_parts=body_parts,
        mechanism=mechanism,
    )


def _derive_liens(rng: random.Random, profile: DistributionProfile, stage: str) -> LienSpec:
    """Derive the lien block; liens only resolve on resolved-ish cases."""
    if rng.random() >= profile.lien_rate:
        return LienSpec()
    low, high = profile.lien_count_range
    count = rng.randint(low, high)
    pool = list(_LIEN_CLAIMANT_POOL)
    rng.shuffle(pool)
    claimants = pool[:count]
    if stage in _RESOLVED_STAGES:
        resolution = rng.choice(list(_LIEN_RESOLUTIONS))
        post_resolution = rng.random() < 0.45
    else:
        resolution = "pending"
        post_resolution = False
    return LienSpec(
        count=count,
        claimants=claimants,  # type: ignore[arg-type]
        resolution=resolution,  # type: ignore[arg-type]
        post_resolution_litigation=post_resolution,
    )


def _derive_reconsideration(
    rng: random.Random,
    profile: DistributionProfile,
    stage: str,
    resolution: ResolutionSpec,
) -> ReconsiderationSpec:
    """Derive the recon block — only awards can be reconsidered."""
    award_available = resolution.type in {"findings_award", "stipulations", "c_and_r"}
    if stage == "post_recon":
        forced = True
    elif not award_available or stage not in _RESOLVED_STAGES:
        return ReconsiderationSpec()
    else:
        forced = rng.random() < profile.recon_rate
    if not forced:
        return ReconsiderationSpec()

    outcome = _weighted_choice(
        rng, {"denied": 0.55, "granted_remand": 0.33, "granted_reversed": 0.12}
    )
    if outcome == "denied":
        post_recon = "affirmed_final"
    elif outcome == "granted_remand":
        post_recon = _weighted_choice(rng, {"further_litigation": 0.55, "settled": 0.45})
    else:
        post_recon = _weighted_choice(
            rng, {"affirmed_final": 0.6, "further_litigation": 0.25, "settled": 0.15}
        )
    return ReconsiderationSpec(
        enabled=True,
        outcome=outcome,  # type: ignore[arg-type]
        post_recon=post_recon,  # type: ignore[arg-type]
    )


def _derive_ur_dispute(rng: random.Random, profile: DistributionProfile, stage: str) -> UrDispute:
    """Derive the UR/IMR block."""
    if stage == "intake" or rng.random() >= profile.ur_dispute_rate:
        return UrDispute()
    decision = _weighted_choice(rng, {"upheld": 0.65, "overturned": 0.35})
    if decision == "upheld" and rng.random() < profile.imr_rate:
        imr_outcome = _weighted_choice(rng, {"upheld": 0.80, "overturned": 0.20})
        return UrDispute(
            enabled=True,
            decision="upheld",
            imr=True,
            imr_outcome=imr_outcome,  # type: ignore[arg-type]
        )
    return UrDispute(enabled=True, decision=decision)  # type: ignore[arg-type]


def _derive_doctrine_hooks(
    rng: random.Random,
    profile: DistributionProfile,
    injury: InjurySpec,
    facts: Any,
) -> list[str]:
    """Derive doctrine hooks that fit the case being derived.

    The draw used to run over the whole pool, so an auto-derived caseload could
    put a death-benefits argument in a living applicant's file or an IMR
    due-process challenge in a case that never went to IMR. A seed author naming
    a hook is making a choice the engine respects loudly (see
    :func:`~wc_caseload_engine.doctrine.unsupported_hook_warnings`); a *draw* is
    nobody's choice, so it is filtered against the same prerequisites.

    Args:
        facts: :class:`~wc_caseload_engine.doctrine.DoctrineFacts` for the case
            under construction — the lifecycle fields exist here before the
            :class:`CaseSeed` that will hold them does.
    """
    hooks: list[str] = []
    if injury.type == "death":
        hooks.append("death_dependency")
    if rng.random() < profile.doctrine_hook_rate:
        pool = [
            hook
            for hook in _DOCTRINE_POOL
            if hook not in hooks and hook_is_supported(hook, facts)
        ]
        rng.shuffle(pool)
        extra = 1 if rng.random() > profile.complex_rate else 2
        hooks.extend(pool[:extra])
    return supported_hooks(hooks, facts)


def derive_case_seed(
    index: int,
    auto: AutoSpec,
    *,
    case_id: str | None = None,
) -> CaseSeed:
    """Materialize one fully-specified :class:`CaseSeed` from a distribution.

    Deterministic in ``(auto.rng_seed, index)`` — the same pair always yields a
    byte-identical seed.
    """
    profile = DISTRIBUTIONS.get(auto.distribution)
    if profile is None:  # pragma: no cover - Literal keeps this unreachable
        raise SeedError(
            f"unknown distribution {auto.distribution!r}; allowed: "
            f"{', '.join(sorted(DISTRIBUTIONS))}"
        )

    case_seed_value = derive_seed(auto.rng_seed, f"case:{index}")
    rng = random.Random(derive_seed(auto.rng_seed, f"derive:{index}"))

    stage = _weighted_choice(rng, profile.stages)
    claim_response = _weighted_choice(rng, profile.claim_responses)
    injury = _derive_injury(rng, profile, stage)
    eval_type = _weighted_choice(rng, _STAGE_EVALS[stage])
    resolution = ResolutionSpec(
        type=_weighted_choice(rng, _STAGE_RESOLUTIONS[stage]),  # type: ignore[arg-type]
        msa=rng.random() < profile.msa_rate,
    )
    recon = _derive_reconsideration(rng, profile, stage, resolution)
    ur_dispute = _derive_ur_dispute(rng, profile, stage)

    # The prerequisites read lifecycle facts, so they are assembled before the
    # hooks that depend on them rather than off a seed that does not exist yet.
    #
    # ``occupation`` and ``industry`` are deliberately absent, not forgotten: a
    # derived seed carries no ``profile`` block at all (see the CaseSeed built
    # below), because the cast is drawn later, in ``case_context``, and never
    # written back. So there is nothing to pass, and the two fields keep their
    # empty defaults.
    #
    # The consequence is that ``firefighter_presumption`` — the one hook gated
    # on those two fields — can never be auto-drawn. Measured at 0 across 975
    # derived seeds. That fails *closed*, so it is a coverage gap rather than an
    # incoherent case, and closing it means giving derivation an occupation and
    # industry distribution plus a profile in the materialized seed. Tracked as
    # its own AJC-35 item; ``TestFirefighterPresumptionCannotBeAutoDrawn`` pins
    # the current behaviour so the gap cannot close silently.
    doctrine_facts = DoctrineFacts(
        injury_type=injury.type,
        body_part_count=distinct_body_part_count(injury.body_parts),
        has_psych_body_part=any(
            part.part.strip().casefold() == "psyche" for part in injury.body_parts
        ),
        eval_type=eval_type,
        claim_response=claim_response,
        imr_filed=bool(ur_dispute.enabled and ur_dispute.imr),
    )

    lifecycle = LifecycleSpec(
        target_stage=stage,  # type: ignore[arg-type]
        claim_response=claim_response,  # type: ignore[arg-type]
        eval_type=eval_type,  # type: ignore[arg-type]
        ur_dispute=ur_dispute,
        resolution=resolution,
        reconsideration=recon,
        liens=_derive_liens(rng, profile, stage),
        doctrine_hooks=_derive_doctrine_hooks(  # type: ignore[arg-type]
            rng, profile, injury, doctrine_facts
        ),
    )

    return CaseSeed(
        case_id=case_id or f"auto-{index + 1:03d}",
        rng_seed=case_seed_value,
        injury=injury,
        lifecycle=lifecycle,
    )


def derive_auto_seeds(auto: AutoSpec, *, existing_ids: Iterable[str] = ()) -> list[CaseSeed]:
    """Derive ``auto.count`` fully-materialized seeds, avoiding id collisions."""
    taken = set(existing_ids)
    derived: list[CaseSeed] = []
    for index in range(auto.count):
        seed = derive_case_seed(index, auto)
        if seed.case_id in taken:
            suffix = 1
            candidate = f"{seed.case_id}-{suffix}"
            while candidate in taken:
                suffix += 1
                candidate = f"{seed.case_id}-{suffix}"
            seed = derive_case_seed(index, auto, case_id=candidate)
        taken.add(seed.case_id)
        derived.append(seed)
    log.debug(
        "seeds.auto_derived",
        count=len(derived),
        distribution=auto.distribution,
        rng_seed=auto.rng_seed,
    )
    return derived


def resolve_caseload(spec: CaseloadSpec) -> list[CaseSeed]:
    """Explicit cases plus auto-derived cases, all fully materialized."""
    cases = list(spec.cases)
    if spec.auto is not None:
        cases.extend(derive_auto_seeds(spec.auto, existing_ids=[c.case_id for c in cases]))
    return cases


def apply_defaults(defaults: Mapping[str, Any], case: Mapping[str, Any]) -> dict[str, Any]:
    """Public wrapper over :func:`deep_merge` for a single raw case mapping."""
    return deep_merge(defaults, case)


def stage_order(stage: str) -> int:
    """Ordinal of a lifecycle stage — handy for Phase B date engines."""
    stages: MutableMapping[str, int] = {
        "intake": 0,
        "active_treatment": 1,
        "discovery": 2,
        "medical_legal": 3,
        "pre_trial": 4,
        "resolved": 5,
        "post_recon": 6,
    }
    return stages[stage]


__all__ = [
    "ANCHOR_DATE",
    "AWW_METHODS",
    "BODY_PART_CATALOG",
    "DEFAULT_FORMAT_MIX",
    "DISTRIBUTIONS",
    "PAY_PERIODS_PER_YEAR",
    "POST_RESOLUTION_RUNWAY_DAYS",
    "RESOLVED_RUNWAY_DAYS",
    "STAGE_RUNWAY_DAYS",
    "TREATMENT_LIEN_CLAIMANTS",
    "AdjusterScenario",
    "ApplicantProfile",
    "AttorneyProfile",
    "AttorneyScenario",
    "AutoSpec",
    "BenefitsScenario",
    "BodyPart",
    "CarrierProfile",
    "CaseProfile",
    "CaseSeed",
    "CaseloadSpec",
    "DiagnosticEntry",
    "DiagnosticsScenario",
    "DiscoveryScenario",
    "DistributionProfile",
    "DocumentControls",
    "DocumentOverride",
    "EarningsEntry",
    "EmployerProfile",
    "InKindEntry",
    "InjurySpec",
    "LienSpec",
    "LifecycleSpec",
    "OutputSpec",
    "PageRange",
    "PhysicianProfile",
    "RateBasisOverride",
    "ReconsiderationSpec",
    "ResolutionSpec",
    "ScenarioSpec",
    "SeedError",
    "SeedValidationError",
    "SettlementScenario",
    "TreatmentScenario",
    "UrDispute",
    "WageScenario",
    "apply_defaults",
    "deep_merge",
    "derive_auto_seeds",
    "derive_case_seed",
    "derive_seed",
    "dump_case_seed",
    "load_case_seed",
    "load_caseload_spec",
    "parse_case_seed",
    "parse_caseload_spec",
    "required_runway_days",
    "resolve_caseload",
    "runway_driver",
    "seed_to_dict",
    "stage_order",
    "write_case_seed",
]
