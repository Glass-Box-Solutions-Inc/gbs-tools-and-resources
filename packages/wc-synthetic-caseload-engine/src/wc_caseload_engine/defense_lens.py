"""Frozen defense models, semantic events, and pure reserve-booking policies.

The module owns authored operands, exact trigger resolution, the staged
builder state, and final event facts. Renderers and truth projections consume
those facts later without redrawing an amount or reconstructing an event.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Context, Decimal, InvalidOperation, localcontext
from typing import Annotated, Any, Literal, NoReturn

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    model_validator,
)

type DefenseBucket = Literal["indemnity", "medical", "expense_alae"]
type PaidCategory = Literal[
    "td",
    "pd",
    "life_pension",
    "death",
    "treatment",
    "future_medical",
    "msa",
    "defense_fees",
    "med_legal",
    "sub_rosa",
    "interpreters",
    "court_reporters",
    "copy_service",
]
type ReserveTrigger = Literal[
    "initial_file_review",
    "compensability_decision",
    "aoe_coe_outcome",
    "surgery_authorized",
    "mmi",
    "qme_ame_wpi",
    "formal_rating",
    "trial_setting",
    "petition_for_reconsideration",
]
type PostIfrReserveTrigger = Literal[
    "compensability_decision",
    "aoe_coe_outcome",
    "surgery_authorized",
    "mmi",
    "qme_ame_wpi",
    "formal_rating",
    "trial_setting",
    "petition_for_reconsideration",
]
type TriggerSourceKind = Literal[
    "timeline",
    "planned_document",
    "medical_opinion",
    "case_facts",
    "rating",
    "recon_track",
]
type AdjusterDiligence = Literal["attentive", "ordinary", "negligent"]
type ReserveAdequacy = Literal["under_reserved", "adequate", "over_reserved"]

DEFENSE_INVALID_BUCKET_CATEGORY = "DEFENSE_INVALID_BUCKET_CATEGORY"
DEFENSE_EXPOSURE_BELOW_PAID = "DEFENSE_EXPOSURE_BELOW_PAID"
DEFENSE_DUPLICATE_W1_PAID_COST = "DEFENSE_DUPLICATE_W1_PAID_COST"
DEFENSE_UNKNOWN_RESERVE_TRIGGER = "DEFENSE_UNKNOWN_RESERVE_TRIGGER"
DEFENSE_INVALID_EXPOSURE_RANGE = "DEFENSE_INVALID_EXPOSURE_RANGE"
DEFENSE_REQUIRES_WAGES = "DEFENSE_REQUIRES_WAGES"
DEFENSE_REQUIRES_DEFENSE_PERSPECTIVE = "DEFENSE_REQUIRES_DEFENSE_PERSPECTIVE"
DEFENSE_TRIGGER_OCCURRENCE_ID_MISSING = "DEFENSE_TRIGGER_OCCURRENCE_ID_MISSING"
DEFENSE_TRIGGER_SOURCE_REMOVED = "DEFENSE_TRIGGER_SOURCE_REMOVED"
DEFENSE_TRIGGER_SOURCE_DATE_MISMATCH = "DEFENSE_TRIGGER_SOURCE_DATE_MISMATCH"
DEFENSE_INELIGIBLE_RESERVE_TRIGGER = "DEFENSE_INELIGIBLE_RESERVE_TRIGGER"
DEFENSE_TRIGGER_ORDER_INVALID = "DEFENSE_TRIGGER_ORDER_INVALID"
DEFENSE_REQUIRED_CARRIER_REMOVED = "DEFENSE_REQUIRED_CARRIER_REMOVED"
DEFENSE_UNBOUND_RESERVE_NOTICE = "DEFENSE_UNBOUND_RESERVE_NOTICE"
DEFENSE_INITIAL_REVIEW_REQUIRED = "DEFENSE_INITIAL_REVIEW_REQUIRED"
DEFENSE_DUPLICATE_INITIAL_REVIEW_EVENT = (
    "DEFENSE_DUPLICATE_INITIAL_REVIEW_EVENT"
)
DEFENSE_ARTIFACT_BINDING_MISSING = "DEFENSE_ARTIFACT_BINDING_MISSING"
DEFENSE_ARTIFACT_BINDING_MISMATCH = "DEFENSE_ARTIFACT_BINDING_MISMATCH"
DEFENSE_ACCOUNTING_EQUATION_BROKEN = "DEFENSE_ACCOUNTING_EQUATION_BROKEN"

# Compatibility spellings retained for Items 7-9 callers. The frozen R79
# register below contains only the canonical Item 10 vocabulary.
DEFENSE_INITIAL_FILE_REVIEW_REQUIRED = DEFENSE_INITIAL_REVIEW_REQUIRED
DEFENSE_INVALID_AMOUNT = DEFENSE_INVALID_EXPOSURE_RANGE
DEFENSE_NEGATIVE_AMOUNT = DEFENSE_INVALID_EXPOSURE_RANGE
DEFENSE_DUPLICATE_PAID_COST_ID = DEFENSE_DUPLICATE_W1_PAID_COST
DEFENSE_DUPLICATE_RESERVE_TRIGGER = DEFENSE_UNKNOWN_RESERVE_TRIGGER

DEFENSE_ERROR_CODES = frozenset(
    {
        DEFENSE_ACCOUNTING_EQUATION_BROKEN,
        DEFENSE_ARTIFACT_BINDING_MISMATCH,
        DEFENSE_ARTIFACT_BINDING_MISSING,
        DEFENSE_DUPLICATE_INITIAL_REVIEW_EVENT,
        DEFENSE_DUPLICATE_W1_PAID_COST,
        DEFENSE_EXPOSURE_BELOW_PAID,
        DEFENSE_INELIGIBLE_RESERVE_TRIGGER,
        DEFENSE_INITIAL_REVIEW_REQUIRED,
        DEFENSE_INVALID_BUCKET_CATEGORY,
        DEFENSE_INVALID_EXPOSURE_RANGE,
        DEFENSE_REQUIRED_CARRIER_REMOVED,
        DEFENSE_REQUIRES_DEFENSE_PERSPECTIVE,
        DEFENSE_REQUIRES_WAGES,
        DEFENSE_TRIGGER_OCCURRENCE_ID_MISSING,
        DEFENSE_TRIGGER_ORDER_INVALID,
        DEFENSE_TRIGGER_SOURCE_DATE_MISMATCH,
        DEFENSE_TRIGGER_SOURCE_REMOVED,
        DEFENSE_UNBOUND_RESERVE_NOTICE,
        DEFENSE_UNKNOWN_RESERVE_TRIGGER,
    }
)

DEFENSE_WIRE_FACT_KEYS = (
    "exposureEvents",
    "paidCosts",
    "reserveEvents",
    "initialFileReview",
    "scorerLabels",
)
DEFENSE_WIRE_PUBLIC_KEYS = DEFENSE_WIRE_FACT_KEYS[:-1]
DEFENSE_WIRE_BUCKET_KEYS = ("indemnity", "medical", "expenseAlae", "total")
DEFENSE_WIRE_PAID_COST_KEYS = (
    "id",
    "date",
    "bucket",
    "category",
    "amount",
    "sourceDocumentSubtype",
)
DEFENSE_WIRE_EXPOSURE_KEYS = (
    "trigger",
    "effectiveDate",
    "low",
    "expected",
    "high",
    "assumptions",
)
DEFENSE_WIRE_SNAPSHOT_KEYS = ("paid", "outstandingReserve", "incurred")
DEFENSE_WIRE_INITIAL_REVIEW_KEYS = (
    "eventId",
    "reviewDate",
    "caseEvaluation",
    "compensabilityPosture",
    "exposure",
    "recommendation",
    "bookedSnapshot",
    "litigationBudget",
    "discoveryPlan",
    "assumptions",
    "authorityStatus",
    "adoptionLagDays",
    "artifactBinding",
)
DEFENSE_WIRE_RESERVE_EVENT_KEYS = (
    "id",
    "trigger",
    "eventDate",
    "priorSnapshot",
    "exposure",
    "recommendation",
    "bookedSnapshot",
    "adoptionLagDays",
    "reason",
    "artifactBinding",
)
DEFENSE_WIRE_BINDING_KEYS = (
    "eventId",
    "documentIndex",
    "subtype",
    "documentDate",
)
DEFENSE_WIRE_SCORER_LABEL_KEYS = ("stairStepping", "reserveAdequacy")

DEFENSE_RESERVE_TRIGGERS: tuple[ReserveTrigger, ...] = (
    "initial_file_review",
    "compensability_decision",
    "aoe_coe_outcome",
    "surgery_authorized",
    "mmi",
    "qme_ame_wpi",
    "formal_rating",
    "trial_setting",
    "petition_for_reconsideration",
)

DEFENSE_BUCKET_CATEGORIES: dict[DefenseBucket, tuple[PaidCategory, ...]] = {
    "indemnity": ("td", "pd", "life_pension", "death"),
    "medical": ("treatment", "future_medical", "msa"),
    "expense_alae": (
        "defense_fees",
        "med_legal",
        "sub_rosa",
        "interpreters",
        "court_reporters",
        "copy_service",
    ),
}

_STRICT_MODEL_CONFIG = ConfigDict(extra="forbid", frozen=True, validate_default=True)
_MONEY_CONTEXT = Context(prec=28, rounding=ROUND_HALF_UP)
_CENTS = Decimal("0.01")
_ZERO = Decimal("0.00")
_W1_BENEFIT_CATEGORIES = frozenset({"td", "pd"})
_BUCKET_NAMES: tuple[DefenseBucket, ...] = (
    "indemnity",
    "medical",
    "expense_alae",
)


class DefenseValidationError(ValueError):
    """One stable defense-lens failure with its offending path and value."""

    def __init__(self, code: str, path: str, value: object, detail: str) -> None:
        self.code = code
        self.path = path
        self.value = value
        super().__init__(f"{code}: {path}={value!r} — {detail}")


def _fail(code: str, path: str, value: object, detail: str) -> NoReturn:
    raise DefenseValidationError(code, path, value, detail)


def _quantized_amount(value: Any) -> Decimal:
    """Coerce through ``Decimal(str(value))`` and quantize exactly once."""
    try:
        with localcontext(_MONEY_CONTEXT):
            amount = Decimal(str(value))
            if not amount.is_finite():
                raise InvalidOperation
            amount = amount.quantize(_CENTS, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        _fail(
            DEFENSE_INVALID_AMOUNT,
            "defense.amount",
            value,
            "defense amounts must be finite decimal-compatible values",
        )
    if amount < _ZERO:
        _fail(
            DEFENSE_NEGATIVE_AMOUNT,
            "defense.amount",
            value,
            "defense amounts cannot be negative",
        )
    return amount


type DefenseAmount = Annotated[Decimal, BeforeValidator(_quantized_amount)]


def _money_sum(*values: Decimal) -> Decimal:
    with localcontext(_MONEY_CONTEXT):
        return sum(values, _ZERO).quantize(_CENTS, rounding=ROUND_HALF_UP)


def _money_difference(left: Decimal, right: Decimal) -> Decimal:
    with localcontext(_MONEY_CONTEXT):
        return (left - right).quantize(_CENTS, rounding=ROUND_HALF_UP)


class BucketAmounts(BaseModel):
    """The three non-interchangeable defense money buckets."""

    model_config = _STRICT_MODEL_CONFIG

    indemnity: DefenseAmount
    medical: DefenseAmount
    expense_alae: DefenseAmount

    @property
    def total(self) -> Decimal:
        return _money_sum(self.indemnity, self.medical, self.expense_alae)

    def __add__(self, other: BucketAmounts) -> BucketAmounts:
        if not isinstance(other, BucketAmounts):
            return NotImplemented
        return BucketAmounts(
            indemnity=_money_sum(self.indemnity, other.indemnity),
            medical=_money_sum(self.medical, other.medical),
            expense_alae=_money_sum(self.expense_alae, other.expense_alae),
        )

    def subtract_floored(self, other: BucketAmounts) -> BucketAmounts:
        """Subtract component-wise, flooring only this expressly named operation."""

        def component(left: Decimal, right: Decimal) -> Decimal:
            return _money_sum(max(left - right, _ZERO))

        return BucketAmounts(
            indemnity=component(self.indemnity, other.indemnity),
            medical=component(self.medical, other.medical),
            expense_alae=component(self.expense_alae, other.expense_alae),
        )

    def components(self) -> tuple[tuple[DefenseBucket, Decimal], ...]:
        return (
            ("indemnity", self.indemnity),
            ("medical", self.medical),
            ("expense_alae", self.expense_alae),
        )


def _validate_exposure_range(
    low: BucketAmounts,
    expected: BucketAmounts,
    high: BucketAmounts,
    *,
    path: str,
) -> None:
    for bucket in DEFENSE_BUCKET_CATEGORIES:
        values = (
            getattr(low, bucket),
            getattr(expected, bucket),
            getattr(high, bucket),
        )
        if values[0] <= values[1] <= values[2]:
            continue
        _fail(
            DEFENSE_INVALID_EXPOSURE_RANGE,
            f"{path}.{bucket}",
            values,
            "ultimate exposure must obey low <= expected <= high per bucket",
        )
    totals = (low.total, expected.total, high.total)
    if not totals[0] <= totals[1] <= totals[2]:
        _fail(
            DEFENSE_INVALID_EXPOSURE_RANGE,
            f"{path}.total",
            totals,
            "ultimate exposure totals must obey low <= expected <= high",
        )


def _validate_trigger(value: Any, *, path: str) -> ReserveTrigger:
    if value not in DEFENSE_RESERVE_TRIGGERS:
        _fail(
            DEFENSE_UNKNOWN_RESERVE_TRIGGER,
            path,
            value,
            f"trigger must be one of {DEFENSE_RESERVE_TRIGGERS!r}",
        )
    return value


class ExposureInput(BaseModel):
    """One authored ultimate-exposure range at a registered trigger."""

    model_config = _STRICT_MODEL_CONFIG

    trigger: ReserveTrigger
    low: BucketAmounts
    expected: BucketAmounts
    high: BucketAmounts

    @model_validator(mode="before")
    @classmethod
    def _trigger_is_registered(cls, value: Any) -> Any:
        if isinstance(value, dict) and "trigger" in value:
            _validate_trigger(
                value["trigger"],
                path="scenario.defense_lens.exposure_events[].trigger",
            )
        return value

    @model_validator(mode="after")
    def _range_is_ordered(self) -> ExposureInput:
        _validate_exposure_range(
            self.low,
            self.expected,
            self.high,
            path="scenario.defense_lens.exposure_events[]",
        )
        return self


class _PaidCostBase(BaseModel):
    model_config = _STRICT_MODEL_CONFIG

    id: str = Field(min_length=1)
    date: date
    bucket: DefenseBucket
    category: PaidCategory
    amount: DefenseAmount
    source_document_subtype: str = Field(min_length=1)

    @model_validator(mode="before")
    @classmethod
    def _raw_category_belongs_to_bucket(cls, value: Any) -> Any:
        if isinstance(value, dict):
            bucket = value.get("bucket")
            category = value.get("category")
            if (
                bucket not in DEFENSE_BUCKET_CATEGORIES
                or category not in DEFENSE_BUCKET_CATEGORIES[bucket]
            ):
                _fail(
                    DEFENSE_INVALID_BUCKET_CATEGORY,
                    "defense.paid_costs[].category",
                    (bucket, category),
                    "paid-cost category must belong to its stated bucket",
                )
        return value

    @model_validator(mode="after")
    def _category_belongs_to_bucket(self) -> _PaidCostBase:
        if self.category not in DEFENSE_BUCKET_CATEGORIES[self.bucket]:
            _fail(
                DEFENSE_INVALID_BUCKET_CATEGORY,
                "defense.paid_costs[].category",
                (self.bucket, self.category),
                "paid-cost category must belong to its stated bucket",
            )
        return self


class PaidCostInput(_PaidCostBase):
    """One authored non-W1 paid cost."""


class PaidCost(_PaidCostBase):
    """One normalized paid ledger row."""


class DefenseLensScenario(BaseModel):
    """The exact authored defense-lens block; no derived reserve fields."""

    model_config = _STRICT_MODEL_CONFIG

    case_evaluation: str
    assumptions: tuple[str, ...]
    discovery_plan: tuple[str, ...]
    litigation_budget: DefenseAmount
    exposure_events: tuple[ExposureInput, ...]
    paid_costs: tuple[PaidCostInput, ...] = ()

    @model_validator(mode="after")
    def _authored_registers_are_unique(self) -> DefenseLensScenario:
        triggers = tuple(event.trigger for event in self.exposure_events)
        if triggers.count("initial_file_review") != 1:
            _fail(
                DEFENSE_INITIAL_FILE_REVIEW_REQUIRED,
                "scenario.defense_lens.exposure_events",
                triggers,
                "initial_file_review is required exactly once",
            )
        if len(set(triggers)) != len(triggers):
            duplicate = next(trigger for trigger in triggers if triggers.count(trigger) > 1)
            _fail(
                DEFENSE_DUPLICATE_RESERVE_TRIGGER,
                "scenario.defense_lens.exposure_events[].trigger",
                duplicate,
                "authored exposure triggers cannot repeat",
            )
        _validate_unique_paid_ids(self.paid_costs)
        duplicate_w1 = next(
            (
                item
                for item in self.paid_costs
                if item.category in _W1_BENEFIT_CATEGORIES
            ),
            None,
        )
        if duplicate_w1 is not None:
            _fail(
                DEFENSE_DUPLICATE_W1_PAID_COST,
                "scenario.defense_lens.paid_costs",
                duplicate_w1.id,
                "authored td/pd costs duplicate components owned by the W1 benefit ledger",
            )
        return self


class ExposureProjection(BaseModel):
    """One dated ultimate-exposure projection, never an outstanding reserve."""

    model_config = _STRICT_MODEL_CONFIG

    trigger: ReserveTrigger
    effective_date: date
    low: BucketAmounts
    expected: BucketAmounts
    high: BucketAmounts
    assumptions: tuple[str, ...]

    @model_validator(mode="before")
    @classmethod
    def _trigger_is_registered(cls, value: Any) -> Any:
        if isinstance(value, dict) and "trigger" in value:
            _validate_trigger(value["trigger"], path="defense.exposure.trigger")
        return value

    @model_validator(mode="after")
    def _range_is_ordered(self) -> ExposureProjection:
        _validate_exposure_range(
            self.low,
            self.expected,
            self.high,
            path="defense.exposure",
        )
        return self


class ReserveSnapshot(BaseModel):
    """Paid, outstanding, and incurred at one already-selected snapshot."""

    model_config = _STRICT_MODEL_CONFIG

    paid: BucketAmounts
    outstanding_reserve: BucketAmounts
    incurred: BucketAmounts

    @model_validator(mode="after")
    def _incurred_is_paid_plus_outstanding(self) -> ReserveSnapshot:
        expected = self.paid + self.outstanding_reserve
        if self.incurred != expected:
            _fail(
                DEFENSE_ACCOUNTING_EQUATION_BROKEN,
                "defense.reserve_snapshot.incurred",
                self.incurred,
                "incurred must equal paid plus outstanding reserve per bucket",
            )
        return self


class TriggerOccurrence(BaseModel):
    """One eligible semantic occurrence resolved before document controls."""

    model_config = _STRICT_MODEL_CONFIG

    trigger: ReserveTrigger
    semantic_event_id: str = Field(min_length=1)
    effective_date: date
    source_kind: TriggerSourceKind
    source_record_id: str = Field(min_length=1)
    requires_planned_document: bool


class ReserveArtifactBinding(BaseModel):
    """Final-plan identity of the artifact bound to one reserve event."""

    model_config = _STRICT_MODEL_CONFIG

    event_id: str = Field(min_length=1)
    document_index: int = Field(ge=0)
    subtype: Literal["RESERVE_WORKSHEET", "RESERVE_CHANGE_NOTICE"]
    document_date: date


class InitialFileReview(BaseModel):
    """The required IFR, materialized only after its final artifact is bound."""

    model_config = _STRICT_MODEL_CONFIG

    event_id: Literal["reserve:initial_file_review"]
    review_date: date
    case_evaluation: str
    compensability_posture: Literal["accepted", "denied", "delayed"]
    exposure: ExposureProjection
    recommendation: ReserveSnapshot
    booked_snapshot: ReserveSnapshot
    litigation_budget: DefenseAmount
    discovery_plan: tuple[str, ...]
    assumptions: tuple[str, ...]
    authority_status: Literal[
        "ENGINE_POLICY_WITH_COUNSEL_CONFIRMED_INPUTS",
        "MIXED_OR_UNCONFIRMED",
    ]
    adoption_lag_days: Literal[0]
    artifact_binding: ReserveArtifactBinding

    @model_validator(mode="before")
    @classmethod
    def _artifact_binding_is_present(cls, value: Any) -> Any:
        if isinstance(value, Mapping) and value.get("artifact_binding") is None:
            _fail(
                DEFENSE_ARTIFACT_BINDING_MISSING,
                "defense.initial_file_review.artifact_binding",
                value.get("artifact_binding"),
                "the initial file review requires its final worksheet binding",
            )
        return value

    @model_validator(mode="after")
    def _dates_and_paid_match(self) -> InitialFileReview:
        if self.exposure.trigger != "initial_file_review":
            _fail(
                DEFENSE_TRIGGER_ORDER_INVALID,
                "defense.initial_file_review.exposure.trigger",
                self.exposure.trigger,
                "the IFR exposure must use initial_file_review",
            )
        if self.review_date != self.exposure.effective_date:
            _fail(
                DEFENSE_TRIGGER_SOURCE_DATE_MISMATCH,
                "defense.initial_file_review.review_date",
                self.review_date,
                "the IFR review and exposure dates must match",
            )
        if self.recommendation.paid != self.booked_snapshot.paid:
            _fail(
                DEFENSE_INVALID_EXPOSURE_RANGE,
                "defense.initial_file_review.booked_snapshot.paid",
                self.booked_snapshot.paid,
                "IFR recommendation and booked snapshot must carry identical paid",
            )
        if (
            self.artifact_binding.event_id != self.event_id
            or self.artifact_binding.subtype != "RESERVE_WORKSHEET"
            or self.artifact_binding.document_date != self.review_date
        ):
            _fail(
                DEFENSE_ARTIFACT_BINDING_MISMATCH,
                "defense.initial_file_review.artifact_binding",
                self.artifact_binding,
                "IFR binding must name its RESERVE_WORKSHEET on the review date",
            )
        return self


class ReserveEvent(BaseModel):
    """One post-IFR reserve decision in resolved semantic order."""

    model_config = _STRICT_MODEL_CONFIG

    id: str = Field(pattern=r"^reserve:[a-z_]+$")
    trigger: PostIfrReserveTrigger
    event_date: date
    prior_snapshot: ReserveSnapshot
    exposure: ExposureProjection
    recommendation: ReserveSnapshot
    booked_snapshot: ReserveSnapshot
    adoption_lag_days: int = Field(ge=0)
    reason: str = Field(min_length=1)
    artifact_binding: ReserveArtifactBinding | None

    @model_validator(mode="after")
    def _identity_and_paid_match(self) -> ReserveEvent:
        if self.id != f"reserve:{self.trigger}" or self.exposure.trigger != self.trigger:
            _fail(
                DEFENSE_TRIGGER_ORDER_INVALID,
                "defense.reserve_event.id",
                self.id,
                "reserve event ID and exposure trigger must name the event trigger",
            )
        if self.event_date != self.exposure.effective_date:
            _fail(
                DEFENSE_TRIGGER_SOURCE_DATE_MISMATCH,
                "defense.reserve_event.event_date",
                self.event_date,
                "event and exposure dates must match",
            )
        if self.recommendation.paid != self.booked_snapshot.paid:
            _fail(
                DEFENSE_INVALID_EXPOSURE_RANGE,
                "defense.reserve_event.booked_snapshot.paid",
                self.booked_snapshot.paid,
                "recommendation and booked snapshot must carry identical paid",
            )
        if self.artifact_binding is not None and (
            self.artifact_binding.event_id != self.id
            or self.artifact_binding.subtype != "RESERVE_CHANGE_NOTICE"
            or self.artifact_binding.document_date != self.event_date
        ):
            _fail(
                DEFENSE_ARTIFACT_BINDING_MISMATCH,
                "defense.reserve_event.artifact_binding",
                self.artifact_binding,
                "reserve-event binding must name its notice on the event date",
            )
        return self


class DefenseScorerLabels(BaseModel):
    """The two labels derived only after the booked-reserve ledger exists."""

    model_config = _STRICT_MODEL_CONFIG

    stair_stepping: bool
    reserve_adequacy: ReserveAdequacy


class DefenseLensFacts(BaseModel):
    """The single generation, extraction, and scorer defense-lens object."""

    model_config = _STRICT_MODEL_CONFIG

    exposure_events: tuple[ExposureProjection, ...]
    paid_costs: tuple[PaidCost, ...]
    initial_file_review: InitialFileReview
    reserve_events: tuple[ReserveEvent, ...]
    scorer_labels: DefenseScorerLabels

    @model_validator(mode="after")
    def _ledgers_are_canonical(self) -> DefenseLensFacts:
        if not self.exposure_events or self.exposure_events[0].trigger != (
            "initial_file_review"
        ):
            _fail(
                DEFENSE_INITIAL_FILE_REVIEW_REQUIRED,
                "defense.exposure_events",
                tuple(event.trigger for event in self.exposure_events),
                "the exposure ledger must begin with initial_file_review",
            )
        if self.initial_file_review.exposure is not self.exposure_events[0]:
            _fail(
                DEFENSE_INVALID_EXPOSURE_RANGE,
                "defense.initial_file_review.exposure",
                self.initial_file_review.exposure.trigger,
                "the IFR must retain the first exposure-ledger object by identity",
            )
        _validate_unique_paid_ids(self.paid_costs)
        ordered = tuple(sorted(self.paid_costs, key=lambda item: (item.date, item.id)))
        if self.paid_costs != ordered:
            _fail(
                DEFENSE_DUPLICATE_PAID_COST_ID,
                "defense.paid_costs",
                tuple(item.id for item in self.paid_costs),
                "paid-cost ledger must be sorted by (date, id)",
            )
        prior = self.initial_file_review.booked_snapshot
        prior_date = self.initial_file_review.review_date
        post_exposures = {event.trigger: event for event in self.exposure_events[1:]}
        if len(post_exposures) != len(self.exposure_events) - 1:
            _fail(
                DEFENSE_DUPLICATE_RESERVE_TRIGGER,
                "defense.exposure_events",
                tuple(event.trigger for event in self.exposure_events),
                "resolved exposure triggers cannot repeat",
            )
        for event in self.reserve_events:
            if event.trigger == "initial_file_review":
                _fail(
                    DEFENSE_DUPLICATE_INITIAL_REVIEW_EVENT,
                    "defense.reserve_events",
                    event.id,
                    "initial_file_review exists only as InitialFileReview",
                )
            matched_exposure = post_exposures.get(event.trigger)
            if event.exposure is not matched_exposure:
                _fail(
                    DEFENSE_INVALID_EXPOSURE_RANGE,
                    f"defense.reserve_events[{event.id}].exposure",
                    event.trigger,
                    "reserve events must retain their trigger-matched exposure by identity",
                )
            if event.event_date < prior_date or event.prior_snapshot != prior:
                _fail(
                    DEFENSE_TRIGGER_ORDER_INVALID,
                    "defense.reserve_events",
                    event.id,
                    "events must be chronological and chain the prior booked snapshot",
                )
            paid_since = _bucket_map(
                lambda current, previous: _money_sum(
                    max(_money_difference(current, previous or _ZERO), _ZERO)
                ),
                event.booked_snapshot.paid,
                prior.paid,
            )
            carried = prior.outstanding_reserve.subtract_floored(paid_since)
            binding_required = event.booked_snapshot.outstanding_reserve != carried
            if binding_required != (event.artifact_binding is not None):
                code = (
                    DEFENSE_ARTIFACT_BINDING_MISSING
                    if binding_required
                    else DEFENSE_ARTIFACT_BINDING_MISMATCH
                )
                _fail(
                    code,
                    f"defense.reserve_events[{event.id}].artifact_binding",
                    event.artifact_binding,
                    "a notice is required exactly when booked reserve changes from carried",
                )
            prior = event.booked_snapshot
            prior_date = event.event_date
        if tuple(event.trigger for event in self.reserve_events) != tuple(
            event.trigger for event in self.exposure_events[1:]
        ):
            _fail(
                DEFENSE_TRIGGER_ORDER_INVALID,
                "defense.reserve_events",
                tuple(event.trigger for event in self.reserve_events),
                "reserve-event order must exactly match the post-IFR exposure ledger",
            )
        return self


def _wire_amount(value: Decimal) -> str:
    return f"{value.quantize(_CENTS, rounding=ROUND_HALF_UP):f}"


def _wire_bucket(amounts: BucketAmounts) -> dict[str, Any]:
    values = {
        "indemnity": _wire_amount(amounts.indemnity),
        "medical": _wire_amount(amounts.medical),
        "expenseAlae": _wire_amount(amounts.expense_alae),
        "total": _wire_amount(amounts.total),
    }
    return {key: values[key] for key in DEFENSE_WIRE_BUCKET_KEYS}


def _wire_paid_cost(cost: PaidCost) -> dict[str, Any]:
    values = {
        "id": cost.id,
        "date": cost.date.isoformat(),
        "bucket": cost.bucket,
        "category": cost.category,
        "amount": _wire_amount(cost.amount),
        "sourceDocumentSubtype": cost.source_document_subtype,
    }
    return {key: values[key] for key in DEFENSE_WIRE_PAID_COST_KEYS}


def _wire_exposure(exposure: ExposureProjection) -> dict[str, Any]:
    values = {
        "trigger": exposure.trigger,
        "effectiveDate": exposure.effective_date.isoformat(),
        "low": _wire_bucket(exposure.low),
        "expected": _wire_bucket(exposure.expected),
        "high": _wire_bucket(exposure.high),
        "assumptions": list(exposure.assumptions),
    }
    return {key: values[key] for key in DEFENSE_WIRE_EXPOSURE_KEYS}


def _wire_snapshot(snapshot: ReserveSnapshot) -> dict[str, Any]:
    values = {
        "paid": _wire_bucket(snapshot.paid),
        "outstandingReserve": _wire_bucket(snapshot.outstanding_reserve),
        "incurred": _wire_bucket(snapshot.incurred),
    }
    return {key: values[key] for key in DEFENSE_WIRE_SNAPSHOT_KEYS}


def _wire_binding(binding: ReserveArtifactBinding) -> dict[str, Any]:
    values = {
        "eventId": binding.event_id,
        "documentIndex": binding.document_index,
        "subtype": binding.subtype,
        "documentDate": binding.document_date.isoformat(),
    }
    return {key: values[key] for key in DEFENSE_WIRE_BINDING_KEYS}


def _wire_initial_review(review: InitialFileReview) -> dict[str, Any]:
    values = {
        "eventId": review.event_id,
        "reviewDate": review.review_date.isoformat(),
        "caseEvaluation": review.case_evaluation,
        "compensabilityPosture": review.compensability_posture,
        "exposure": _wire_exposure(review.exposure),
        "recommendation": _wire_snapshot(review.recommendation),
        "bookedSnapshot": _wire_snapshot(review.booked_snapshot),
        "litigationBudget": _wire_amount(review.litigation_budget),
        "discoveryPlan": list(review.discovery_plan),
        "assumptions": list(review.assumptions),
        "authorityStatus": review.authority_status,
        "adoptionLagDays": review.adoption_lag_days,
        "artifactBinding": _wire_binding(review.artifact_binding),
    }
    return {key: values[key] for key in DEFENSE_WIRE_INITIAL_REVIEW_KEYS}


def _wire_reserve_event(event: ReserveEvent) -> dict[str, Any]:
    values: dict[str, Any] = {
        "id": event.id,
        "trigger": event.trigger,
        "eventDate": event.event_date.isoformat(),
        "priorSnapshot": _wire_snapshot(event.prior_snapshot),
        "exposure": _wire_exposure(event.exposure),
        "recommendation": _wire_snapshot(event.recommendation),
        "bookedSnapshot": _wire_snapshot(event.booked_snapshot),
        "adoptionLagDays": event.adoption_lag_days,
        "reason": event.reason,
    }
    if event.artifact_binding is not None:
        values["artifactBinding"] = _wire_binding(event.artifact_binding)
    return {
        key: values[key]
        for key in DEFENSE_WIRE_RESERVE_EVENT_KEYS
        if key in values
    }


def defense_wire_projection(
    facts: DefenseLensFacts,
    *,
    include_scorer_labels: bool,
) -> dict[str, Any]:
    """Project the one domain object through the exact public or scorer allowlist."""
    values: dict[str, Any] = {
        "exposureEvents": [_wire_exposure(item) for item in facts.exposure_events],
        "paidCosts": [_wire_paid_cost(item) for item in facts.paid_costs],
        "reserveEvents": [_wire_reserve_event(item) for item in facts.reserve_events],
        "initialFileReview": _wire_initial_review(facts.initial_file_review),
    }
    if include_scorer_labels:
        values["scorerLabels"] = {
            "stairStepping": facts.scorer_labels.stair_stepping,
            "reserveAdequacy": facts.scorer_labels.reserve_adequacy,
        }
    keys = DEFENSE_WIRE_FACT_KEYS if include_scorer_labels else DEFENSE_WIRE_PUBLIC_KEYS
    return {key: values[key] for key in keys}


@dataclass(frozen=True, slots=True)
class BookingDecision:
    """Internal policy result before final-plan artifact binding."""

    exposure: ExposureProjection
    prior_snapshot: ReserveSnapshot | None
    recommendation: ReserveSnapshot
    booked_snapshot: ReserveSnapshot
    carried_outstanding: BucketAmounts
    adoption_lag_days: int
    reason: str
    requires_notice: bool


@dataclass(frozen=True, slots=True)
class _UnboundDefenseState:
    """Stage-5 builder state; consumed source IDs never become a public model."""

    scenario: DefenseLensScenario
    trigger_occurrences: tuple[TriggerOccurrence, ...]
    paid_costs: tuple[PaidCost, ...]
    decisions: tuple[BookingDecision, ...]
    consumed_source_ids: tuple[str, ...]
    source_subtypes: tuple[tuple[str, tuple[str, ...]], ...]


@dataclass(frozen=True, slots=True)
class _BoundReserveArtifacts:
    """Stage-8 binding data, before the stage-9 domain object exists."""

    initial_file_review: ReserveArtifactBinding
    reserve_events: tuple[tuple[str, ReserveArtifactBinding | None], ...]


def _validate_unique_paid_ids(costs: Iterable[_PaidCostBase]) -> None:
    identifiers = tuple(cost.id for cost in costs)
    if len(set(identifiers)) == len(identifiers):
        return
    duplicate = next(identifier for identifier in identifiers if identifiers.count(identifier) > 1)
    _fail(
        DEFENSE_DUPLICATE_PAID_COST_ID,
        "defense.paid_costs[].id",
        duplicate,
        "paid-cost IDs must be unique",
    )


def paid_cost_ledger(costs: Sequence[PaidCostInput | PaidCost]) -> tuple[PaidCost, ...]:
    """Normalize, validate, and sort the paid ledger by ``(date, id)``."""
    _validate_unique_paid_ids(costs)
    normalized = tuple(
        PaidCost(
            id=cost.id,
            date=cost.date,
            bucket=cost.bucket,
            category=cost.category,
            amount=cost.amount,
            source_document_subtype=cost.source_document_subtype,
        )
        for cost in costs
    )
    return tuple(sorted(normalized, key=lambda item: (item.date, item.id)))


def paid_to_date(
    paid_costs: Sequence[PaidCostInput | PaidCost],
    *,
    snapshot_date: date,
    w1_indemnity_payments: Sequence[tuple[date, Any]] = (),
) -> BucketAmounts:
    """Aggregate actual paid costs through a date without reserve arithmetic."""
    ledger = paid_cost_ledger(paid_costs)
    duplicate = next(
        (item for item in ledger if item.category in _W1_BENEFIT_CATEGORIES),
        None,
    )
    if duplicate is not None:
        _fail(
            DEFENSE_DUPLICATE_W1_PAID_COST,
            "scenario.defense_lens.paid_costs",
            duplicate.id,
            "authored td/pd costs duplicate components owned by the W1 benefit ledger",
        )

    indemnity = _money_sum(
        *(
            _quantized_amount(amount)
            for paid_date, amount in w1_indemnity_payments
            if paid_date <= snapshot_date
        )
    )
    medical = _ZERO
    expense = _ZERO
    for item in ledger:
        if item.date > snapshot_date:
            continue
        if item.bucket == "indemnity":
            indemnity = _money_sum(indemnity, item.amount)
        elif item.bucket == "medical":
            medical = _money_sum(medical, item.amount)
        else:
            expense = _money_sum(expense, item.amount)
    return BucketAmounts(
        indemnity=indemnity,
        medical=medical,
        expense_alae=expense,
    )


def _stable_unique(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return tuple(ordered)


def project_exposure(
    authored: ExposureInput,
    *,
    effective_date: date,
    case_assumptions: Sequence[str],
    trigger_facts: Sequence[str] = (),
) -> ExposureProjection:
    """Date an authored ultimate range without any RNG or reconstruction."""
    return ExposureProjection(
        trigger=authored.trigger,
        effective_date=effective_date,
        low=authored.low,
        expected=authored.expected,
        high=authored.high,
        assumptions=_stable_unique((*case_assumptions, *trigger_facts)),
    )


def _validate_bound_at_least_paid(
    bound_name: str,
    ultimate: BucketAmounts,
    paid: BucketAmounts,
) -> None:
    for bucket in DEFENSE_BUCKET_CATEGORIES:
        ultimate_amount = getattr(ultimate, bucket)
        paid_amount = getattr(paid, bucket)
        if ultimate_amount < paid_amount:
            _fail(
                DEFENSE_EXPOSURE_BELOW_PAID,
                f"defense.exposure.{bound_name}.{bucket}",
                ultimate_amount,
                f"ultimate exposure cannot be below paid-to-date {paid_amount}",
            )


def validate_exposure_against_paid(
    exposure: ExposureProjection,
    paid: BucketAmounts,
) -> None:
    """Prove all three ultimate bounds cover paid before reserve subtraction."""
    _validate_bound_at_least_paid("low", exposure.low, paid)
    _validate_bound_at_least_paid("expected", exposure.expected, paid)
    _validate_bound_at_least_paid("high", exposure.high, paid)


def recommended_reserve_snapshot(
    *,
    paid: BucketAmounts,
    expected_ultimate: BucketAmounts,
) -> ReserveSnapshot:
    """Compute recommended outstanding and incurred after below-paid proof."""
    _validate_bound_at_least_paid("expected", expected_ultimate, paid)
    outstanding = expected_ultimate.subtract_floored(paid)
    return ReserveSnapshot(
        paid=paid,
        outstanding_reserve=outstanding,
        incurred=paid + outstanding,
    )


def _bucket_map(
    operation: Any,
    left: BucketAmounts,
    right: BucketAmounts | None = None,
) -> BucketAmounts:
    values: dict[str, Decimal] = {}
    for bucket in _BUCKET_NAMES:
        left_value = getattr(left, bucket)
        values[bucket] = operation(
            left_value,
            None if right is None else getattr(right, bucket),
        )
    return BucketAmounts(**values)


def _scale(amounts: BucketAmounts, factor: Decimal) -> BucketAmounts:
    def scale(value: Decimal, _unused: Decimal | None) -> Decimal:
        with localcontext(_MONEY_CONTEXT):
            return (value * factor).quantize(_CENTS, rounding=ROUND_HALF_UP)

    return _bucket_map(scale, amounts)


def _paid_from_ledger(costs: Sequence[PaidCost], snapshot_date: date) -> BucketAmounts:
    totals: dict[DefenseBucket, Decimal] = {
        "indemnity": _ZERO,
        "medical": _ZERO,
        "expense_alae": _ZERO,
    }
    for cost in costs:
        if cost.date <= snapshot_date:
            totals[cost.bucket] = _money_sum(totals[cost.bucket], cost.amount)
    return BucketAmounts(**totals)


def _booked_snapshot(paid: BucketAmounts, outstanding: BucketAmounts) -> ReserveSnapshot:
    incurred = paid + outstanding
    return ReserveSnapshot(
        paid=paid,
        outstanding_reserve=outstanding,
        incurred=incurred,
    )


def _reason(
    trigger: ReserveTrigger,
    current: BucketAmounts,
    prior: BucketAmounts | None,
) -> str:
    if prior is None:
        return "initial_file_review established the first expected ultimate exposure"
    delta = _money_difference(current.total, prior.total)
    direction = "increased" if delta > _ZERO else "decreased" if delta < _ZERO else "held"
    return f"{trigger} {direction} expected ultimate exposure by {abs(delta):.2f}"


def apply_booking_policy(
    exposure_events: Sequence[ExposureProjection],
    paid_ledger: Sequence[PaidCost],
    diligence: AdjusterDiligence,
) -> tuple[BookingDecision, ...]:
    """Apply one deterministic booking policy to fixed exposure and paid inputs."""
    if diligence not in {"attentive", "ordinary", "negligent"}:
        raise ValueError(f"unsupported diligence {diligence!r}")
    ordered = tuple(
        sorted(
            exposure_events,
            key=lambda item: (
                item.effective_date,
                DEFENSE_RESERVE_TRIGGERS.index(item.trigger),
            ),
        )
    )
    if not ordered or ordered[0].trigger != "initial_file_review":
        _fail(
            DEFENSE_TRIGGER_ORDER_INVALID,
            "defense.exposure_events",
            tuple(event.trigger for event in ordered),
            "the semantic series must start with initial_file_review",
        )

    ledger = tuple(sorted(paid_ledger, key=lambda item: (item.date, item.id)))
    decisions: list[BookingDecision] = []
    under_since: dict[DefenseBucket, date | None] = {
        "indemnity": None,
        "medical": None,
        "expense_alae": None,
    }
    for index, exposure in enumerate(ordered):
        paid = _paid_from_ledger(ledger, exposure.effective_date)
        validate_exposure_against_paid(exposure, paid)
        recommendation = recommended_reserve_snapshot(
            paid=paid,
            expected_ultimate=exposure.expected,
        )
        prior_decision = decisions[-1] if decisions else None
        prior_snapshot = None if prior_decision is None else prior_decision.booked_snapshot
        if prior_snapshot is None:
            carried = BucketAmounts(indemnity=0, medical=0, expense_alae=0)
        else:
            paid_since = _bucket_map(
                lambda current, previous: _money_sum(
                    max(_money_difference(current, previous or _ZERO), _ZERO)
                ),
                paid,
                prior_snapshot.paid,
            )
            carried = prior_snapshot.outstanding_reserve.subtract_floored(paid_since)

        recommended = recommendation.outstanding_reserve
        if diligence == "attentive":
            booked = recommended
            policy_reason = "attentive policy adopted the full recommendation"
        elif diligence == "ordinary" and index == 0:
            booked = _scale(recommended, Decimal("0.75"))
            policy_reason = "ordinary IFR policy booked 75 percent of recommendation"
        elif diligence == "ordinary":
            assert prior_decision is not None
            prior_expected = prior_decision.exposure.expected.total
            with localcontext(_MONEY_CONTEXT):
                materiality = max(
                    Decimal("5000.00"),
                    prior_expected * Decimal("0.10"),
                )
            delta = abs(_money_difference(exposure.expected.total, prior_expected))
            if delta >= materiality:
                booked = recommended
                policy_reason = "ordinary policy adopted a material exposure change"
            else:
                booked = carried
                policy_reason = "ordinary policy retained the carried reserve"
        elif index == 0:
            booked = _scale(recommended, Decimal("0.40"))
            policy_reason = "negligent IFR policy booked 40 percent of recommendation"
        else:
            def negligent_component(
                recommendation_value: Decimal,
                carried_value: Decimal | None,
            ) -> Decimal:
                carried_amount = carried_value or _ZERO
                if recommendation_value < carried_amount:
                    return recommendation_value
                with localcontext(_MONEY_CONTEXT):
                    increment = (
                        (recommendation_value - carried_amount) * Decimal("0.25")
                    ).quantize(_CENTS, rounding=ROUND_HALF_UP)
                return _money_sum(carried_amount, increment)

            booked = _bucket_map(negligent_component, recommended, carried)
            policy_reason = "negligent policy adopted 25 percent of each upward gap"

        lag_values: list[int] = []
        for bucket in _BUCKET_NAMES:
            is_under = getattr(booked, bucket) < getattr(recommended, bucket)
            if is_under and under_since[bucket] is None:
                under_since[bucket] = exposure.effective_date
            elif not is_under:
                under_since[bucket] = None
            start = under_since[bucket]
            lag_values.append(
                0 if start is None else (exposure.effective_date - start).days
            )
        lag = 0 if index == 0 else max(lag_values)
        booked_snapshot = _booked_snapshot(paid, booked)
        prior_expected_for_reason = (
            None if prior_decision is None else prior_decision.exposure.expected
        )
        decisions.append(
            BookingDecision(
                exposure=exposure,
                prior_snapshot=prior_snapshot,
                recommendation=recommendation,
                booked_snapshot=booked_snapshot,
                carried_outstanding=carried,
                adoption_lag_days=lag,
                reason=(
                    f"{_reason(exposure.trigger, exposure.expected, prior_expected_for_reason)}; "
                    f"{policy_reason}"
                ),
                requires_notice=index > 0 and booked != carried,
            )
        )
    return tuple(decisions)


def reserve_adequacy(decisions: Sequence[BookingDecision]) -> ReserveAdequacy:
    """Classify the final booked total with no tolerance band."""
    final = decisions[-1]
    booked = final.booked_snapshot.outstanding_reserve.total
    recommended = final.recommendation.outstanding_reserve.total
    if booked < recommended:
        return "under_reserved"
    if booked > recommended:
        return "over_reserved"
    return "adequate"


def is_stair_stepping(decisions: Sequence[BookingDecision]) -> bool:
    """Detect the exact R70 three-consecutive-post-event pattern."""
    post = tuple(decisions[1:])
    if len(post) < 3 or (
        post[-1].booked_snapshot.outstanding_reserve.total
        >= post[-1].recommendation.outstanding_reserve.total
    ):
        return False
    for start in range(len(post) - 2):
        run = post[start : start + 3]
        booked = tuple(item.booked_snapshot.outstanding_reserve.total for item in run)
        recommended = tuple(item.recommendation.outstanding_reserve.total for item in run)
        if not (booked[0] < booked[1] < booked[2]):
            continue
        if not (recommended[0] <= recommended[1] <= recommended[2]):
            continue
        first_shortfall = _money_difference(recommended[0], booked[0])
        if first_shortfall <= _ZERO:
            continue
        with localcontext(_MONEY_CONTEXT):
            half_shortfall = first_shortfall * Decimal("0.50")
        if all(
            _money_difference(booked[index], booked[index - 1])
            < half_shortfall
            for index in (1, 2)
        ):
            return True
    return False


def _candidate_matches_occurrence(candidate: Any, occurrence: TriggerOccurrence) -> bool:
    subtype = getattr(candidate, "subtype", None)
    trigger = occurrence.trigger
    if trigger == "compensability_decision":
        return subtype in {
            "CLAIM_ACCEPTANCE_LETTER",
            "CLAIM_DENIAL_LETTER",
            "CLAIM_DELAY_NOTICE",
        }
    if trigger in {"aoe_coe_outcome", "qme_ame_wpi"}:
        return getattr(candidate, "medical_opinion_id", None) == occurrence.source_record_id
    return subtype == {
        "surgery_authorized": "MEDICAL_TREATMENT_AUTHORIZATION",
        "formal_rating": "PD_RATING_CALCULATION_WORKSHEET",
        "trial_setting": "NOTICE_OF_TRIAL",
        "petition_for_reconsideration": "PETITION_RECONSIDERATION_FILED",
    }.get(trigger)


def _planned_occurrence(
    *,
    trigger: ReserveTrigger,
    semantic_event_id: str,
    candidates: Sequence[Any],
    subtypes: frozenset[str],
    source_record_id: str,
) -> TriggerOccurrence:
    matches = tuple(
        candidate
        for candidate in candidates
        if getattr(candidate, "subtype", None) in subtypes
        and getattr(candidate, "semantic_event_id", None) == semantic_event_id
    )
    if not matches:
        _fail(
            DEFENSE_INELIGIBLE_RESERVE_TRIGGER,
            f"scenario.defense_lens.exposure_events[{trigger}]",
            semantic_event_id,
            "the trigger has no eligible semantic planned-document source",
        )
    return TriggerOccurrence(
        trigger=trigger,
        semantic_event_id=semantic_event_id,
        effective_date=min(candidate.doc_date for candidate in matches),
        source_kind="planned_document",
        source_record_id=source_record_id,
        requires_planned_document=True,
    )


def resolve_trigger_occurrences(
    authored_events: Sequence[ExposureInput],
    *,
    timeline: Any,
    lifecycle: Any,
    case_facts: Any,
    candidates: Sequence[Any],
    opinions: Sequence[Any] = (),
    recon: Any = None,
) -> tuple[TriggerOccurrence, ...]:
    """Resolve all authored triggers from exact semantic sources, never fallbacks."""
    by_trigger = {event.trigger: event for event in authored_events}
    occurrences: list[TriggerOccurrence] = []
    for trigger in DEFENSE_RESERVE_TRIGGERS:
        if trigger not in by_trigger:
            continue
        if trigger == "initial_file_review":
            occurrence = TriggerOccurrence(
                trigger=trigger,
                semantic_event_id="timeline:claim_filed",
                effective_date=timeline.claim_filed_date,
                source_kind="timeline",
                source_record_id="claim_filed",
                requires_planned_document=False,
            )
        elif trigger == "compensability_decision":
            response = lifecycle.claim_response
            subtype = {
                "accepted": "CLAIM_ACCEPTANCE_LETTER",
                "denied": "CLAIM_DENIAL_LETTER",
                "delayed": "CLAIM_DELAY_NOTICE",
            }[response]
            occurrence = _planned_occurrence(
                trigger=trigger,
                semantic_event_id=f"claim-response:{response}",
                candidates=candidates,
                subtypes=frozenset({subtype}),
                source_record_id=response,
            )
        elif trigger in {"aoe_coe_outcome", "qme_ame_wpi"}:
            eligible: list[tuple[Any, Any]] = []
            for opinion in opinions:
                if getattr(opinion, "report_stage", None) != "final":
                    continue
                if trigger == "aoe_coe_outcome" and getattr(
                    opinion, "aoe_coe_finding", None
                ) not in {"industrial", "nonindustrial"}:
                    continue
                if trigger == "qme_ame_wpi" and (
                    getattr(lifecycle, "eval_type", None) not in {"qme", "ame"}
                    or getattr(opinion, "author_role", None) != lifecycle.eval_type
                    or getattr(case_facts, "rating", None) is None
                ):
                    continue
                carriers = tuple(
                    candidate
                    for candidate in candidates
                    if getattr(candidate, "medical_opinion_id", None) == opinion.id
                    and getattr(candidate, "semantic_event_id", None)
                    == f"medical-opinion:{opinion.id}"
                )
                if carriers:
                    eligible.append((opinion, min(carriers, key=lambda item: item.doc_date)))
            if not eligible:
                _fail(
                    DEFENSE_INELIGIBLE_RESERVE_TRIGGER,
                    f"scenario.defense_lens.exposure_events[{trigger}]",
                    trigger,
                    "the trigger has no eligible final medical-opinion carrier",
                )
            opinion, carrier = min(
                eligible,
                key=lambda pair: (pair[0].report_date, pair[0].id),
            )
            if carrier.doc_date != opinion.report_date:
                _fail(
                    DEFENSE_TRIGGER_SOURCE_DATE_MISMATCH,
                    f"defense.trigger.{trigger}.effective_date",
                    carrier.doc_date,
                    f"opinion carrier date must equal report date {opinion.report_date}",
                )
            occurrence = TriggerOccurrence(
                trigger=trigger,
                semantic_event_id=f"medical-opinion:{opinion.id}",
                effective_date=opinion.report_date,
                source_kind="medical_opinion",
                source_record_id=opinion.id,
                requires_planned_document=True,
            )
        elif trigger == "surgery_authorized":
            surgery = case_facts.surgery
            procedure_key = surgery.cpt_code or (
                f"{surgery.body_part}:uncoded" if surgery.body_part else None
            )
            if procedure_key is None:
                _fail(
                    DEFENSE_INELIGIBLE_RESERVE_TRIGGER,
                    "scenario.defense_lens.exposure_events[surgery_authorized]",
                    None,
                    "surgery authorization requires a named CaseFacts procedure",
                )
            occurrence = _planned_occurrence(
                trigger=trigger,
                semantic_event_id=f"surgery-authorization:{procedure_key}",
                candidates=candidates,
                subtypes=frozenset({"MEDICAL_TREATMENT_AUTHORIZATION"}),
                source_record_id=procedure_key,
            )
        elif trigger == "mmi":
            mmi_date = getattr(case_facts, "mmi_date", None)
            if mmi_date is None or mmi_date > timeline.horizon:
                _fail(
                    DEFENSE_INELIGIBLE_RESERVE_TRIGGER,
                    "scenario.defense_lens.exposure_events[mmi]",
                    mmi_date,
                    "MMI must exist and be reached within the case timeline",
                )
            occurrence = TriggerOccurrence(
                trigger=trigger,
                semantic_event_id="case-facts:mmi",
                effective_date=mmi_date,
                source_kind="case_facts",
                source_record_id="mmi_date",
                requires_planned_document=False,
            )
        elif trigger == "formal_rating":
            if getattr(case_facts, "rating", None) is None:
                _fail(
                    DEFENSE_INELIGIBLE_RESERVE_TRIGGER,
                    "scenario.defense_lens.exposure_events[formal_rating]",
                    None,
                    "formal rating requires real RatingFacts",
                )
            occurrence = _planned_occurrence(
                trigger=trigger,
                semantic_event_id="rating:formal",
                candidates=candidates,
                subtypes=frozenset({"PD_RATING_CALCULATION_WORKSHEET"}),
                source_record_id="rating:formal",
            )
            occurrence = occurrence.model_copy(update={"source_kind": "rating"})
        elif trigger == "trial_setting":
            if lifecycle.target_stage not in {"pre_trial", "resolved", "post_recon"}:
                _fail(
                    DEFENSE_INELIGIBLE_RESERVE_TRIGGER,
                    "scenario.defense_lens.exposure_events[trial_setting]",
                    lifecycle.target_stage,
                    "trial setting requires a reached trial-capable stage",
                )
            notices = tuple(
                candidate
                for candidate in candidates
                if getattr(candidate, "subtype", None) == "NOTICE_OF_TRIAL"
                and getattr(candidate, "semantic_event_id", None)
                == f"trial-setting:{candidate.doc_date.isoformat()}"
            )
            if not notices:
                _fail(
                    DEFENSE_INELIGIBLE_RESERVE_TRIGGER,
                    "scenario.defense_lens.exposure_events[trial_setting]",
                    None,
                    "trial setting requires a semantic NOTICE_OF_TRIAL occurrence",
                )
            notice = min(notices, key=lambda item: item.doc_date)
            occurrence = TriggerOccurrence(
                trigger=trigger,
                semantic_event_id=notice.semantic_event_id,
                effective_date=notice.doc_date,
                source_kind="planned_document",
                source_record_id=f"NOTICE_OF_TRIAL:{notice.doc_date.isoformat()}",
                requires_planned_document=True,
            )
        else:
            petition_date = None if recon is None else recon.petition_date
            if (
                not getattr(getattr(lifecycle, "reconsideration", None), "enabled", False)
                or petition_date is None
            ):
                _fail(
                    DEFENSE_INELIGIBLE_RESERVE_TRIGGER,
                    "scenario.defense_lens.exposure_events[petition_for_reconsideration]",
                    petition_date,
                    "reconsideration trigger requires an enabled petition track",
                )
            petition_occurrence = _planned_occurrence(
                trigger=trigger,
                semantic_event_id="recon:petition",
                candidates=candidates,
                subtypes=frozenset({"PETITION_RECONSIDERATION_FILED"}),
                source_record_id="PETITION_RECONSIDERATION_FILED",
            )
            if petition_occurrence.effective_date != petition_date:
                _fail(
                    DEFENSE_TRIGGER_SOURCE_DATE_MISMATCH,
                    "defense.trigger.petition_for_reconsideration.effective_date",
                    petition_occurrence.effective_date,
                    f"petition carrier date must equal recon date {petition_date}",
                )
            occurrence = petition_occurrence.model_copy(
                update={
                    "effective_date": petition_date,
                    "source_kind": "recon_track",
                }
            )
        occurrences.append(occurrence)

    ordered = tuple(
        sorted(
            occurrences,
            key=lambda item: (
                item.effective_date,
                DEFENSE_RESERVE_TRIGGERS.index(item.trigger),
            ),
        )
    )
    if ordered[0].trigger != "initial_file_review":
        _fail(
            DEFENSE_TRIGGER_ORDER_INVALID,
            "defense.trigger_occurrences",
            tuple(item.trigger for item in ordered),
            "no post-IFR event may precede initial_file_review",
        )
    return ordered


def validate_required_trigger_sources(
    occurrences: Sequence[TriggerOccurrence],
    candidates: Sequence[Any],
    *,
    source_subtypes: dict[str, tuple[str, ...]] | None = None,
) -> None:
    """Fail when controls erase or synthesize a required semantic source."""
    for occurrence in occurrences:
        if not occurrence.requires_planned_document:
            continue
        original_subtypes = () if source_subtypes is None else source_subtypes.get(
            occurrence.semantic_event_id,
            (),
        )
        qualifying = tuple(
            item
            for item in candidates
            if _candidate_matches_occurrence(item, occurrence)
            or getattr(item, "subtype", None) in original_subtypes
        )
        if any(getattr(item, "semantic_event_id", None) is None for item in qualifying):
            _fail(
                DEFENSE_TRIGGER_OCCURRENCE_ID_MISSING,
                f"defense.trigger.{occurrence.trigger}",
                None,
                "a qualifying control-created carrier has no semantic occurrence ID",
            )
        surviving = tuple(
            item
            for item in qualifying
            if getattr(item, "semantic_event_id", None) == occurrence.semantic_event_id
        )
        if not surviving:
            _fail(
                DEFENSE_TRIGGER_SOURCE_REMOVED,
                f"defense.trigger.{occurrence.trigger}",
                occurrence.semantic_event_id,
                "document controls removed the last required trigger source",
            )
        if occurrence.source_kind == "medical_opinion" and any(
            item.doc_date != occurrence.effective_date for item in surviving
        ):
            _fail(
                DEFENSE_TRIGGER_SOURCE_DATE_MISMATCH,
                f"defense.trigger.{occurrence.trigger}.effective_date",
                tuple(item.doc_date for item in surviving),
                "opinion-bound carriers are fitting-exempt and must retain report date",
            )


def build_unbound_defense(
    scenario: DefenseLensScenario,
    *,
    timeline: Any,
    lifecycle: Any,
    case_facts: Any,
    candidates: Sequence[Any],
    paid_costs: Sequence[PaidCost],
    diligence: AdjusterDiligence,
    opinions: Sequence[Any] = (),
    recon: Any = None,
) -> _UnboundDefenseState:
    """Build stage-5 defense state after M4/rating/recon candidates exist."""
    occurrences = resolve_trigger_occurrences(
        scenario.exposure_events,
        timeline=timeline,
        lifecycle=lifecycle,
        case_facts=case_facts,
        candidates=candidates,
        opinions=opinions,
        recon=recon,
    )
    authored = {event.trigger: event for event in scenario.exposure_events}
    exposures = tuple(
        project_exposure(
            authored[occurrence.trigger],
            effective_date=occurrence.effective_date,
            case_assumptions=scenario.assumptions,
            trigger_facts=(f"semantic source {occurrence.semantic_event_id}",),
        )
        for occurrence in occurrences
    )
    canonical_paid = tuple(sorted(paid_costs, key=lambda item: (item.date, item.id)))
    decisions = apply_booking_policy(exposures, canonical_paid, diligence)
    return _UnboundDefenseState(
        scenario=scenario,
        trigger_occurrences=occurrences,
        paid_costs=canonical_paid,
        decisions=decisions,
        consumed_source_ids=tuple(item.semantic_event_id for item in occurrences),
        source_subtypes=tuple(
            (
                occurrence.semantic_event_id,
                tuple(
                    sorted(
                        {
                            candidate.subtype
                            for candidate in candidates
                            if getattr(candidate, "semantic_event_id", None)
                            == occurrence.semantic_event_id
                        }
                    )
                ),
            )
            for occurrence in occurrences
            if occurrence.requires_planned_document
        ),
    )


def _artifact_binding(
    documents: Sequence[Any],
    *,
    event_id: str,
    subtype: Literal["RESERVE_WORKSHEET", "RESERVE_CHANGE_NOTICE"],
    event_date: date,
) -> ReserveArtifactBinding:
    matches = tuple(
        document
        for document in documents
        if document.subtype == subtype
        and getattr(document, "semantic_event_id", None) == event_id
    )
    if len(matches) != 1 or matches[0].doc_date != event_date:
        _fail(
            DEFENSE_REQUIRED_CARRIER_REMOVED,
            f"defense.artifact_binding.{event_id}",
            tuple((item.index, item.doc_date) for item in matches),
            f"exactly one {subtype} must survive at the reserve event date",
        )
    document = matches[0]
    return ReserveArtifactBinding(
        event_id=event_id,
        document_index=document.index,
        subtype=subtype,
        document_date=document.doc_date,
    )


def validate_reserve_artifact_candidates(
    state: _UnboundDefenseState,
    candidates: Sequence[Any],
) -> None:
    """Stage-7 check that controls retained each exact required reserve carrier."""
    expected: list[tuple[str, str, date]] = [
        (
            "reserve:initial_file_review",
            "RESERVE_WORKSHEET",
            state.decisions[0].exposure.effective_date,
        )
    ]
    expected.extend(
        (
            f"reserve:{decision.exposure.trigger}",
            "RESERVE_CHANGE_NOTICE",
            decision.exposure.effective_date,
        )
        for decision in state.decisions[1:]
        if decision.requires_notice
    )
    bound_notice_ids = {
        event_id
        for event_id, subtype, _event_date in expected
        if subtype == "RESERVE_CHANGE_NOTICE"
    }
    for candidate in candidates:
        if candidate.subtype != "RESERVE_CHANGE_NOTICE":
            continue
        event_id = getattr(candidate, "semantic_event_id", None)
        if event_id not in bound_notice_ids:
            _fail(
                DEFENSE_UNBOUND_RESERVE_NOTICE,
                "defense.artifact_binding.reserve_change_notice",
                event_id,
                "a reserve-change notice must bind one changed post-IFR event",
            )
    for event_id, subtype, event_date in expected:
        matches = tuple(
            candidate
            for candidate in candidates
            if candidate.subtype == subtype
            and getattr(candidate, "semantic_event_id", None) == event_id
        )
        if len(matches) != 1 or matches[0].doc_date != event_date:
            _fail(
                DEFENSE_REQUIRED_CARRIER_REMOVED,
                f"defense.artifact_binding.{event_id}",
                tuple(item.doc_date for item in matches),
                f"controls must retain exactly one {subtype} on the event date",
            )


def bind_defense_artifacts(
    state: _UnboundDefenseState,
    *,
    documents: Sequence[Any],
) -> _BoundReserveArtifacts:
    """Resolve stage-8 artifact indexes/dates without constructing defense facts."""
    first = state.decisions[0]
    ifr_binding = _artifact_binding(
        documents,
        event_id="reserve:initial_file_review",
        subtype="RESERVE_WORKSHEET",
        event_date=first.exposure.effective_date,
    )
    events: list[tuple[str, ReserveArtifactBinding | None]] = []
    for decision in state.decisions[1:]:
        event_id = f"reserve:{decision.exposure.trigger}"
        binding = (
            _artifact_binding(
                documents,
                event_id=event_id,
                subtype="RESERVE_CHANGE_NOTICE",
                event_date=decision.exposure.effective_date,
            )
            if decision.requires_notice
            else None
        )
        events.append((event_id, binding))
    return _BoundReserveArtifacts(
        initial_file_review=ifr_binding,
        reserve_events=tuple(events),
    )


def bind_defense_facts(
    state: _UnboundDefenseState,
    bindings: _BoundReserveArtifacts,
    *,
    claim_response: Literal["accepted", "denied", "delayed"],
) -> DefenseLensFacts:
    """Construct the sole frozen stage-9 defense facts object."""
    first = state.decisions[0]
    initial = InitialFileReview(
        event_id="reserve:initial_file_review",
        review_date=first.exposure.effective_date,
        case_evaluation=state.scenario.case_evaluation,
        compensability_posture=claim_response,
        exposure=first.exposure,
        recommendation=first.recommendation,
        booked_snapshot=first.booked_snapshot,
        litigation_budget=state.scenario.litigation_budget,
        discovery_plan=state.scenario.discovery_plan,
        assumptions=state.scenario.assumptions,
        authority_status="ENGINE_POLICY_WITH_COUNSEL_CONFIRMED_INPUTS",
        adoption_lag_days=0,
        artifact_binding=bindings.initial_file_review,
    )
    events: list[ReserveEvent] = []
    for decision, (bound_event_id, binding) in zip(
        state.decisions[1:],
        bindings.reserve_events,
        strict=True,
    ):
        trigger = decision.exposure.trigger
        event_id = f"reserve:{trigger}"
        assert bound_event_id == event_id
        assert decision.prior_snapshot is not None
        events.append(
            ReserveEvent(
                id=event_id,
                trigger=trigger,
                event_date=decision.exposure.effective_date,
                prior_snapshot=decision.prior_snapshot,
                exposure=decision.exposure,
                recommendation=decision.recommendation,
                booked_snapshot=decision.booked_snapshot,
                adoption_lag_days=decision.adoption_lag_days,
                reason=decision.reason,
                artifact_binding=binding,
            )
        )
    return DefenseLensFacts(
        exposure_events=tuple(decision.exposure for decision in state.decisions),
        paid_costs=state.paid_costs,
        initial_file_review=initial,
        reserve_events=tuple(events),
        scorer_labels=DefenseScorerLabels(
            stair_stepping=is_stair_stepping(state.decisions),
            reserve_adequacy=reserve_adequacy(state.decisions),
        ),
    )


def reserve_event_for_document(
    facts: DefenseLensFacts,
    *,
    document_index: int,
    subtype: Literal["RESERVE_WORKSHEET", "RESERVE_CHANGE_NOTICE"],
) -> InitialFileReview | ReserveEvent:
    """Return the sole domain event bound to one final reserve document."""
    if subtype == "RESERVE_WORKSHEET":
        binding = facts.initial_file_review.artifact_binding
        if binding.document_index == document_index and binding.subtype == subtype:
            return facts.initial_file_review
    else:
        matches = tuple(
            event
            for event in facts.reserve_events
            if event.artifact_binding is not None
            and event.artifact_binding.document_index == document_index
            and event.artifact_binding.subtype == subtype
        )
        if len(matches) == 1:
            return matches[0]
    _fail(
        DEFENSE_UNBOUND_RESERVE_NOTICE,
        f"defense.artifact_binding.document[{document_index}]",
        subtype,
        "the final reserve document must have exactly one bound defense event",
    )


__all__ = [
    "DEFENSE_ACCOUNTING_EQUATION_BROKEN",
    "DEFENSE_ARTIFACT_BINDING_MISMATCH",
    "DEFENSE_ARTIFACT_BINDING_MISSING",
    "DEFENSE_BUCKET_CATEGORIES",
    "DEFENSE_DUPLICATE_INITIAL_REVIEW_EVENT",
    "DEFENSE_DUPLICATE_PAID_COST_ID",
    "DEFENSE_DUPLICATE_RESERVE_TRIGGER",
    "DEFENSE_DUPLICATE_W1_PAID_COST",
    "DEFENSE_ERROR_CODES",
    "DEFENSE_EXPOSURE_BELOW_PAID",
    "DEFENSE_INELIGIBLE_RESERVE_TRIGGER",
    "DEFENSE_INITIAL_FILE_REVIEW_REQUIRED",
    "DEFENSE_INITIAL_REVIEW_REQUIRED",
    "DEFENSE_INVALID_AMOUNT",
    "DEFENSE_INVALID_BUCKET_CATEGORY",
    "DEFENSE_INVALID_EXPOSURE_RANGE",
    "DEFENSE_NEGATIVE_AMOUNT",
    "DEFENSE_REQUIRED_CARRIER_REMOVED",
    "DEFENSE_REQUIRES_DEFENSE_PERSPECTIVE",
    "DEFENSE_REQUIRES_WAGES",
    "DEFENSE_RESERVE_TRIGGERS",
    "DEFENSE_TRIGGER_OCCURRENCE_ID_MISSING",
    "DEFENSE_TRIGGER_ORDER_INVALID",
    "DEFENSE_TRIGGER_SOURCE_DATE_MISMATCH",
    "DEFENSE_TRIGGER_SOURCE_REMOVED",
    "DEFENSE_UNBOUND_RESERVE_NOTICE",
    "DEFENSE_UNKNOWN_RESERVE_TRIGGER",
    "DEFENSE_WIRE_BINDING_KEYS",
    "DEFENSE_WIRE_BUCKET_KEYS",
    "DEFENSE_WIRE_EXPOSURE_KEYS",
    "DEFENSE_WIRE_FACT_KEYS",
    "DEFENSE_WIRE_INITIAL_REVIEW_KEYS",
    "DEFENSE_WIRE_PAID_COST_KEYS",
    "DEFENSE_WIRE_PUBLIC_KEYS",
    "DEFENSE_WIRE_RESERVE_EVENT_KEYS",
    "DEFENSE_WIRE_SCORER_LABEL_KEYS",
    "DEFENSE_WIRE_SNAPSHOT_KEYS",
    "BookingDecision",
    "BucketAmounts",
    "DefenseBucket",
    "DefenseLensFacts",
    "DefenseLensScenario",
    "DefenseScorerLabels",
    "DefenseValidationError",
    "ExposureInput",
    "ExposureProjection",
    "InitialFileReview",
    "PaidCategory",
    "PaidCost",
    "PaidCostInput",
    "ReserveArtifactBinding",
    "ReserveEvent",
    "ReserveSnapshot",
    "ReserveTrigger",
    "TriggerOccurrence",
    "apply_booking_policy",
    "bind_defense_artifacts",
    "bind_defense_facts",
    "build_unbound_defense",
    "defense_wire_projection",
    "is_stair_stepping",
    "paid_cost_ledger",
    "paid_to_date",
    "project_exposure",
    "recommended_reserve_snapshot",
    "reserve_adequacy",
    "reserve_event_for_document",
    "resolve_trigger_occurrences",
    "validate_exposure_against_paid",
    "validate_required_trigger_sources",
    "validate_reserve_artifact_candidates",
]
