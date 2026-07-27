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
from pathlib import Path
from typing import Any, Literal

import structlog
import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

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


class InjurySpec(_Model):
    """What happened, when, and to which body parts."""

    type: InjuryType = "specific"
    date_of_injury: date | None = None
    ct_start: date | None = None
    ct_end: date | None = None
    body_parts: list[BodyPart] = Field(min_length=1, max_length=5)
    mechanism: str = "auto"

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


def required_runway_days(lifecycle: LifecycleSpec) -> int:
    """Days this lifecycle needs between the injury onset and :data:`ANCHOR_DATE`.

    The maximum of three independent demands, because a case answers to all of
    them at once:

    * the stage it claims to have reached (:data:`STAGE_RUNWAY_DAYS`),
    * whether the case-in-chief actually resolved
      (:data:`RESOLVED_RUNWAY_DAYS`),
    * whether anything litigates on after that resolution — reconsideration or
      post-resolution lien practice (:data:`POST_RESOLUTION_RUNWAY_DAYS`).
    """
    required = STAGE_RUNWAY_DAYS[lifecycle.target_stage]
    if lifecycle.resolution.type != "pending":
        required = max(required, RESOLVED_RUNWAY_DAYS)
    if lifecycle.reconsideration.enabled or lifecycle.liens.post_resolution_litigation:
        required = max(required, POST_RESOLUTION_RUNWAY_DAYS)
    return required


def runway_driver(lifecycle: LifecycleSpec) -> str:
    """Which part of the lifecycle set the runway — named in the error message."""
    if lifecycle.reconsideration.enabled:
        return "lifecycle.reconsideration.enabled"
    if lifecycle.liens.post_resolution_litigation:
        return "lifecycle.liens.post_resolution_litigation"
    if (
        lifecycle.resolution.type != "pending"
        and STAGE_RUNWAY_DAYS[lifecycle.target_stage] < RESOLVED_RUNWAY_DAYS
    ):
        return f"lifecycle.resolution.type {lifecycle.resolution.type!r}"
    return f"lifecycle.target_stage {lifecycle.target_stage!r}"


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
    profile: CaseProfile = Field(default_factory=CaseProfile)
    injury: InjurySpec
    lifecycle: LifecycleSpec = Field(default_factory=LifecycleSpec)
    documents: DocumentControls = Field(default_factory=DocumentControls)
    output: OutputSpec = Field(default_factory=OutputSpec)

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

_DOCTRINE_POOL: tuple[str, ...] = (
    "ogilvie",
    "almaraz_guzman",
    "benson",
    "escobedo",
    "kite",
    "going_and_coming",
    "sibtf",
    "lc3208_3_psych",
    "gfpa",
    "firefighter_presumption",
    "imr_constitutionality",
    "ab5_dynamex",
    "lc4664_prior_award",
)

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
    "intake": (30, 75),
    "active_treatment": (180, 300),
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
    """Pick *count* distinct body parts, starting in *category*."""
    pool: list[tuple[str, str, str]] = list(BODY_PART_CATALOG[category])
    rng.shuffle(pool)
    chosen: list[tuple[str, str, str]] = pool[:count]
    if len(chosen) < count:
        others = [
            entry
            for other, entries in sorted(BODY_PART_CATALOG.items())
            if other != category
            for entry in entries
        ]
        rng.shuffle(others)
        chosen.extend(others[: count - len(chosen)])
    return [BodyPart(part=part, icd10=icd10, detail=detail) for part, icd10, detail in chosen]


def _stage_runway_floor(stage: str) -> int:
    """The worst-case runway any lifecycle at *stage* can demand.

    :func:`_derive_injury` runs before the lifecycle exists, so it assumes the
    most demanding shape the stage can still take: the resolved stages can go on
    to draw reconsideration or post-resolution lien litigation, and both need
    :data:`POST_RESOLUTION_RUNWAY_DAYS`.
    """
    floor = STAGE_RUNWAY_DAYS[stage]
    if stage in _RESOLVED_STAGES:
        return max(floor, RESOLVED_RUNWAY_DAYS, POST_RESOLUTION_RUNWAY_DAYS)
    if stage == "pre_trial":
        # ``_STAGE_RESOLUTIONS['pre_trial']`` can settle the case-in-chief.
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
) -> list[str]:
    """Derive doctrine hooks, honouring injury-driven implications."""
    hooks: list[str] = []
    if injury.type == "death":
        hooks.append("death_dependency")
    if rng.random() < profile.doctrine_hook_rate:
        pool = [hook for hook in _DOCTRINE_POOL if hook not in hooks]
        rng.shuffle(pool)
        extra = 1 if rng.random() > profile.complex_rate else 2
        hooks.extend(pool[:extra])
    return hooks


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

    lifecycle = LifecycleSpec(
        target_stage=stage,  # type: ignore[arg-type]
        claim_response=claim_response,  # type: ignore[arg-type]
        eval_type=eval_type,  # type: ignore[arg-type]
        ur_dispute=_derive_ur_dispute(rng, profile, stage),
        resolution=resolution,
        reconsideration=recon,
        liens=_derive_liens(rng, profile, stage),
        doctrine_hooks=_derive_doctrine_hooks(rng, profile, injury),  # type: ignore[arg-type]
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
    "BODY_PART_CATALOG",
    "DEFAULT_FORMAT_MIX",
    "DISTRIBUTIONS",
    "POST_RESOLUTION_RUNWAY_DAYS",
    "RESOLVED_RUNWAY_DAYS",
    "STAGE_RUNWAY_DAYS",
    "ApplicantProfile",
    "AttorneyProfile",
    "AutoSpec",
    "BodyPart",
    "CarrierProfile",
    "CaseProfile",
    "CaseSeed",
    "CaseloadSpec",
    "DistributionProfile",
    "DocumentControls",
    "DocumentOverride",
    "EmployerProfile",
    "InjurySpec",
    "LienSpec",
    "LifecycleSpec",
    "OutputSpec",
    "PhysicianProfile",
    "ReconsiderationSpec",
    "ResolutionSpec",
    "SeedError",
    "SeedValidationError",
    "UrDispute",
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
