"""Versioned scorer-only ground truth for generated workers' compensation cases.

Truth manifests are deliberately separate from each case's document-analysis
directory.  They live under the caseload's ``truth/`` subtree because a label
that is merely hidden inside a normal case manifest is still available to an
analyzer; directory separation makes the intended handoff boundary mechanical.
These artifacts are inputs to the analyzer scorer and must never be inputs to
document analysis.

The envelope and each channel have independent semantic versions.  Consumers
MUST ignore channel keys they do not recognize and MUST NOT fail because an
unknown channel is present.  That forward-compatibility rule is what let the
``assertions`` channel (medical-story M2, AJC-61 — assertion-quality labels,
the redacted world-truth projection and the ledger digest) arrive at envelope
``1.0.0`` without breaking money-channel consumers, and it still holds the door
for ``defects`` (the analyzer testing plan's Phase 3 defect-injection manifest),
which remains unimplemented.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Protocol

from pydantic import BaseModel, ValidationError

from wc_caseload_engine import __version__
from wc_caseload_engine.medical_assertions import (
    AssertionQualityContract,
    AssertionValidationContext,
    AssertionWorldProjection,
    ContentionDocumentProjection,
    MedicalAssertionLedger,
    ProjectedCondition,
    ProjectedPriorAward,
    ProjectedPriorClaim,
    contention_document_projections,
    grade_ledger,
    validate_contention_document_bindings,
    validate_medical_assertions,
)
from wc_caseload_engine.money import (
    AwwComputation,
    BenefitGap,
    BenefitLedger,
    CompRate,
    EarningsPeriod,
    FirstPaymentRule,
    InKindWage,
    MoneyFacts,
    PdAdvance,
    PenaltyAssessment,
    PenaltyBasis,
    PenaltyLedger,
    RateBasis,
    SettlementFact,
    StatutoryDeadlineBasis,
    StatutoryDueDate,
    TdPeriod,
    WageFacts,
    _first_payment_rule_block,
    dollars,
    money_manifest_block,
)
from wc_caseload_engine.planner import CasePlan

if TYPE_CHECKING:
    from wc_caseload_engine.manifests import CaseResult

TRUTH_DIR = "truth"
CASELOAD_TRUTH_NAME = "caseload.truth.json"
SCHEMA_VERSION = "1.0.0"
MONEY_CHANNEL_VERSION = "1.1.0"
ASSERTIONS_CHANNEL_VERSION = "1.0.0"
"""The assertions channel (AJC-61, M2). The ENVELOPE stays at 1.0.0 — the
module contract above exists precisely so a new channel can arrive without
breaking money-channel consumers, and this is that channel arriving.

**FROZEN to the exact AJC-61 projection for all of AJC-62 (Amendment A1).**
M3 adds always-present fields to the assertion models; none of them may enter
this channel merely because they exist on a Pydantic model. Serialization goes
through the literal ``ASSERTIONS_V1_*`` allowlists below, so adding a model
field is inert with respect to channel ``1.0.0``. AJC-63/M4 exclusively owns
the ``2.0.0`` transition and the first serialization of the M3 vocabulary."""

ASSERTIONS_V2_CHANNEL_VERSION = "2.0.0"
"""Explicit opt-in AJC-63/M4 assertions-channel contract."""

ALWAYS_PRESENT_V2_KEYS: Final = frozenset(
    {"contentionDocuments", "spokenContentionIds"}
)
"""The only v2 collection keys whose empty value remains serialized."""

# ---------------------------------------------------------------------------
# Amendment A1 — the frozen assertions-channel 1.0.0 projection (AJC-62)
# ---------------------------------------------------------------------------

#: The exact case-level channel shape. Neither the case channel nor the
#: caseload channel may gain a key during M3 (A1-R2/A1-R5).
ASSERTIONS_V1_CASE_CHANNEL_KEYS: Final = (
    "channelVersion",
    "kind",
    "audience",
    "leakageRule",
    "validationContext",
    "medicalHistory",
    "contentions",
    "medicalOpinions",
    "apportionmentAssertions",
    "ledgerDigest",
)

ASSERTIONS_V1_VALIDATION_CONTEXT_KEYS: Final = (
    "dateOfInjury",
    "anchorDate",
    "currentBodyParts",
    "targetStage",
    "claimResponse",
)

#: ``evalType`` keeps the AJC-61 rule: omitted when its value is ``"none"``.
ASSERTIONS_V1_OPTIONAL_VALIDATION_CONTEXT_KEYS: Final = ("evalType",)

ASSERTIONS_V1_MEDICAL_HISTORY_KEYS: Final = (
    "conditions",
    "priorClaims",
)

ASSERTIONS_V1_CONDITION_FIELDS: Final = (
    "id",
    "key",
    "label",
    "causal_ground_truth",
    "onset",
    "body_system",
    "body_part",
    "apportionment_targets",
    "wholly_unrelated",
    "severity",
    "trajectory",
    "symptomatic_before_doi",
    "surfaces_in_file",
)

ASSERTIONS_V1_PRIOR_CLAIM_FIELDS: Final = (
    "id",
    "date_of_injury",
    "body_parts",
    "resolution_type",
    "overlaps_current",
    "award",
)

ASSERTIONS_V1_PRIOR_AWARD_FIELDS: Final = (
    "id",
    "prior_claim_id",
    "body_parts",
    "pd_percent",
    "award_date",
    "resolution_type",
    "conclusively_presumed",
)

#: Ledger allowlists — the exact AJC-61 field vocabulary (A1-R3). Value-identical
#: to the test-side ``M2_*_ORACLE_FIELDS`` literals (R62), which are declared
#: independently: production never imports test constants, and the coordinated
#: oracle compares the two tuples for exact equality.
ASSERTIONS_V1_CONTENTION_FIELDS: Final = (
    "id",
    "claim_type",
    "party",
    "position",
    "target_condition_id",
    "target_prior_claim_id",
    "target_prior_award_id",
    "target_body_part",
    "doctrine_hooks",
    "rationale",
    "treatment_causation",
    "requested_apportionment",
    "groundings",
    "quality",
)

ASSERTIONS_V1_MEDICAL_OPINION_FIELDS: Final = (
    "id",
    "author_role",
    "report_stage",
    "report_date",
    "apportionment_state",
    "determination_kind",
    "determination_rationale",
    "examination_performed",
    "reviewed_condition_ids",
    "reviewed_prior_claim_ids",
    "reviewed_prior_award_ids",
    "endorses_contention_ids",
    "rejects_contention_ids",
    "responds_to_opinion_id",
    "supersedes_opinion_id",
    "rationale",
    "revision_rationale",
    "quality",
)

ASSERTIONS_V1_APPORTIONMENT_ASSERTION_FIELDS: Final = (
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
    "quality",
)

ASSERTIONS_V1_CASELOAD_CHANNEL_KEYS: Final = (
    "channelVersion",
    "caseCount",
    "assertionCaseCount",
    "counts",
    "qualityCounts",
    "apportionmentStateCounts",
    "determinationKindCounts",
    "cases",
)

ASSERTIONS_V1_CASELOAD_CASE_KEYS: Final = (
    "caseId",
    "truthFile",
    "contentionCount",
    "medicalOpinionCount",
    "apportionmentAssertionCount",
)

# ---------------------------------------------------------------------------
# AJC-63 — assertions-channel 2.x exact additive projection
# ---------------------------------------------------------------------------

ASSERTIONS_V2_CASE_CHANNEL_KEYS: Final = (
    "channelVersion",
    "kind",
    "audience",
    "leakageRule",
    "validationContext",
    "medicalHistory",
    "contentions",
    "medicalOpinions",
    "apportionmentAssertions",
    "contentionDocuments",
    "ledgerDigest",
)

ASSERTIONS_V2_VALIDATION_CONTEXT_KEYS: Final = (
    "dateOfInjury",
    "anchorDate",
    "currentBodyParts",
    "targetStage",
    "claimResponse",
)

ASSERTIONS_V2_OPTIONAL_VALIDATION_CONTEXT_KEYS: Final = ("evalType",)

ASSERTIONS_V2_MEDICAL_HISTORY_KEYS: Final = (
    "conditions",
    "priorClaims",
)

ASSERTIONS_V2_CONDITION_FIELDS: Final = (
    "id",
    "key",
    "label",
    "causal_ground_truth",
    "onset",
    "body_system",
    "body_part",
    "apportionment_targets",
    "wholly_unrelated",
    "severity",
    "trajectory",
    "symptomatic_before_doi",
    "surfaces_in_file",
    "psych_injury_kind",
)

ASSERTIONS_V2_PRIOR_CLAIM_FIELDS: Final = (
    "id",
    "date_of_injury",
    "body_parts",
    "resolution_type",
    "overlaps_current",
    "award",
)

ASSERTIONS_V2_PRIOR_AWARD_FIELDS: Final = (
    "id",
    "prior_claim_id",
    "body_parts",
    "pd_percent",
    "award_date",
    "resolution_type",
    "conclusively_presumed",
)

ASSERTIONS_V2_CONTENTION_FIELDS: Final = (
    "id",
    "claim_type",
    "party",
    "position",
    "target_condition_id",
    "target_prior_claim_id",
    "target_prior_award_id",
    "target_body_part",
    "doctrine_hooks",
    "rationale",
    "treatment_causation",
    "requested_apportionment",
    "groundings",
    "psych_injury_kind",
    "quality",
)

ASSERTIONS_V2_MEDICAL_OPINION_FIELDS: Final = (
    "id",
    "author_role",
    "report_stage",
    "report_date",
    "apportionment_state",
    "determination_kind",
    "determination_rationale",
    "examination_performed",
    "reviewed_condition_ids",
    "reviewed_prior_claim_ids",
    "reviewed_prior_award_ids",
    "endorses_contention_ids",
    "rejects_contention_ids",
    "responds_to_opinion_id",
    "supersedes_opinion_id",
    "rationale",
    "revision_rationale",
    "event_kind",
    "revision_kind",
    "concurs_with_contention_ids",
    "defers_contention_ids",
    "psych_injury_kind",
    "aoe_coe_finding",
    "aoe_coe_rationale",
    "quality",
)

ASSERTIONS_V2_APPORTIONMENT_ASSERTION_FIELDS: Final = (
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
    "quality",
)

ASSERTIONS_V2_CONTENTION_DOCUMENT_FIELDS: Final = (
    "document_index",
    "subtype",
    "document_date",
    "spoken_contention_ids",
    "medical_opinion_id",
    "target_medical_opinion_id",
    "contention_surface",
    "contention_actor_party",
    "defense_contest_theories",
)

ASSERTIONS_V2_CASELOAD_CHANNEL_KEYS: Final = (
    "channelVersion",
    "caseCount",
    "assertionCaseCount",
    "counts",
    "qualityCounts",
    "apportionmentStateCounts",
    "determinationKindCounts",
    "cases",
)

ASSERTIONS_V2_CASELOAD_CASE_KEYS: Final = (
    "caseId",
    "truthFile",
    "contentionCount",
    "medicalOpinionCount",
    "apportionmentAssertionCount",
    "contentionDocumentCount",
)

LEDGER_DIGEST_MISMATCH = (
    "channels.assertions.ledgerDigest does not match the canonical assertions payload"
)
AUDIENCE = "analyzer-scorer"
LEAKAGE_RULE = "Scorer-only ground truth; never use this artifact as an input to document analysis."
GENERATOR = f"wc-synthetic-caseload-engine@{__version__}"
SCORER_ONLY_ENVELOPE_KEY_NAMES = frozenset(
    {"schemaVersion", "channelVersion", "channels", "audience", "leakageRule", "truthFile"}
)
PENALTY_ASSESSMENT_KEY_NAMES = frozenset(
    {
        "assessments",
        "source",
        "ordinal",
        "rule",
        "principal",
        "statutoryDueDate",
        "operationalDueDate",
        "datePaid",
        "daysLate",
        "increaseFraction",
        "amount",
    }
)


class TruthManifestError(ValueError):
    """A truth manifest cannot be safely interpreted under this contract."""


class _CaseResultLike(Protocol):
    """The rollup fields needed without importing the higher-level writer."""

    case_id: str
    plan: CasePlan
    truth_path: Path | None


def case_truth_name(case_id: str) -> str:
    """Return the deterministic filename for one case's truth manifest."""
    return f"{case_id}.truth.json"


def check_truth_dir_is_isolated(
    truth_dir: Path, out_dir: Path, case_ids: Iterable[str]
) -> None:
    """Reject a scorer directory that resolves into any analyzer-visible case tree."""
    resolved_truth = truth_dir.resolve()
    for case_id in case_ids:
        case_dir = (out_dir / case_id).resolve()
        if resolved_truth == case_dir or resolved_truth.is_relative_to(case_dir):
            raise TruthManifestError(
                f"truth directory {resolved_truth} resolves inside case directory {case_dir}; "
                "choose a scorer-only directory outside every case directory instead"
            )


def _write_json(path: Path, payload: dict[str, object]) -> None:
    """Write deterministic, human-diffable JSON for every manifest family."""
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _channel_decimal(value: Any) -> str:
    """Serialize a model Decimal exactly, without exponent notation or quantizing."""
    return f"{value:f}"


def _date(value: Any) -> str | None:
    """Serialize an optional date, including :data:`datetime.date.min`."""
    return value.isoformat() if value is not None else None


def _money_channel(facts: MoneyFacts) -> dict[str, Any]:
    """Build the complete, lossless money channel from decided facts."""
    wage = facts.wages
    rate = wage.rate
    basis = rate.basis
    computation = wage.computation
    channel: dict[str, Any] = {
        "channelVersion": MONEY_CHANNEL_VERSION,
        "wage": {
            "periods": [
                {
                    "periodStart": period.period_start.isoformat(),
                    "periodEnd": period.period_end.isoformat(),
                    "weeks": _channel_decimal(period.weeks),
                    "regularGross": _channel_decimal(period.regular_gross),
                    "overtimeGross": _channel_decimal(period.overtime_gross),
                    "concurrent": period.concurrent,
                }
                for period in wage.periods
            ],
            "inKind": [
                {"kind": item.kind, "weeklyValue": _channel_decimal(item.weekly_value)}
                for item in wage.in_kind
            ],
            "employmentStart": _date(wage.employment_start),
            "concurrentEmployment": wage.concurrent_employment,
            "pattern": wage.pattern,
            "patternSource": wage.pattern_source,
            "computation": {
                "method": computation.method,
                "methodSource": computation.method_source,
                "methodReason": computation.method_reason,
                "periodsConsidered": computation.periods_considered,
                "weeksConsidered": _channel_decimal(computation.weeks_considered),
                "grossConsidered": _channel_decimal(computation.gross_considered),
                "inKindWeekly": _channel_decimal(computation.in_kind_weekly),
                "averageWeeklyWage": _channel_decimal(computation.aww),
            },
            "rate": {
                "averageWeeklyWage": _channel_decimal(rate.aww),
                "tdWeeklyRate": _channel_decimal(rate.td_weekly_rate),
                "tdBound": rate.td_bound,
                "pdWeeklyRate": _channel_decimal(rate.pd_weekly_rate),
                "pdBound": rate.pd_bound,
                "basis": {
                    "label": basis.label,
                    "effectiveFrom": basis.effective_from.isoformat(),
                    "effectiveTo": _date(basis.effective_to),
                    "tdFraction": _channel_decimal(basis.td_fraction),
                    "tdMaxWeekly": _channel_decimal(basis.td_max_weekly),
                    "tdMinWeekly": _channel_decimal(basis.td_min_weekly),
                    "pdFraction": _channel_decimal(basis.pd_fraction),
                    "pdMaxWeekly": _channel_decimal(basis.pd_max_weekly),
                    "pdMinWeekly": _channel_decimal(basis.pd_min_weekly),
                    "authority": basis.authority,
                    "counselConfirmed": basis.counsel_confirmed,
                    "source": basis.source,
                },
            },
        },
        "benefits": {
            "tdPeriods": [
                {
                    "start": period.start.isoformat(),
                    "end": period.end.isoformat(),
                    "weeks": _channel_decimal(period.weeks),
                    "weeklyRate": _channel_decimal(period.weekly_rate),
                    "amount": _channel_decimal(period.amount),
                    "dateDue": period.date_due.isoformat(),
                    "datePaid": _date(period.date_paid),
                    "daysLate": period.days_late,
                }
                for period in facts.benefits.td_periods
            ],
            "pdAdvances": [
                {
                    "dateDue": advance.date_due.isoformat(),
                    "datePaid": advance.date_paid.isoformat(),
                    "weeks": _channel_decimal(advance.weeks),
                    "weeklyRate": _channel_decimal(advance.weekly_rate),
                    "amount": _channel_decimal(advance.amount),
                    "daysLate": advance.days_late,
                }
                for advance in facts.benefits.pd_advances
            ],
            "gaps": [
                {"start": gap.start.isoformat(), "end": gap.end.isoformat(), "days": gap.days}
                for gap in facts.benefits.gaps
            ],
        },
        # The public projection deliberately remains cents-formatted; its bytes
        # are the existing ``money_manifest_block`` contract, unlike this lossless channel.
        "published": money_manifest_block(facts),
    }
    if facts.settlement is not None:
        settlement = facts.settlement
        channel["settlement"] = {
            "kind": settlement.kind,
            "grossAmount": _channel_decimal(settlement.gross_amount),
            "approvalDate": _date(settlement.approval_date),
            "fundingDate": _date(settlement.funding_date),
        }
    if facts.penalties is not None:
        penalties = facts.penalties
        penalty_basis = penalties.basis
        deadline_basis = penalties.deadlines
        channel["penalties"] = {
            "basis": {
                "label": penalty_basis.label,
                "effectiveFrom": penalty_basis.effective_from.isoformat(),
                "effectiveTo": _date(penalty_basis.effective_to),
                "increaseFraction": _channel_decimal(penalty_basis.increase_fraction),
                "authority": penalty_basis.authority,
                "counselConfirmed": penalty_basis.counsel_confirmed,
                "source": penalty_basis.source,
            },
            "deadlines": {
                "label": deadline_basis.label,
                "effectiveFrom": deadline_basis.effective_from.isoformat(),
                "effectiveTo": _date(deadline_basis.effective_to),
                "firstTdPaymentDays": deadline_basis.first_td_payment_days,
                "subsequentTdPaymentDays": deadline_basis.subsequent_td_payment_days,
                "firstPdPaymentDays": deadline_basis.first_pd_payment_days,
                "authority": deadline_basis.authority,
                "counselConfirmed": deadline_basis.counsel_confirmed,
                "source": deadline_basis.source,
            },
            "schedule": [
                {
                    "source": item.source,
                    "ordinal": item.ordinal,
                    "rule": item.rule,
                    "statutoryDueDate": _date(item.statutory_due_date),
                    "operationalDueDate": item.operational_due_date.isoformat(),
                    "datePaid": _date(item.date_paid),
                    "daysLate": item.days_late,
                    "unpaid": item.unpaid,
                }
                for item in penalties.schedule
            ],
            "assessmentCount": penalties.assessed_count,
            "assessments": [
                {
                    "source": assessment.source,
                    "ordinal": assessment.ordinal,
                    "rule": assessment.rule,
                    "principal": _channel_decimal(assessment.principal),
                    "statutoryDueDate": assessment.statutory_due_date.isoformat(),
                    "operationalDueDate": assessment.operational_due_date.isoformat(),
                    "datePaid": assessment.date_paid.isoformat(),
                    "daysLate": assessment.days_late,
                    "increaseFraction": _channel_decimal(assessment.increase_fraction),
                    "amount": _channel_decimal(assessment.amount),
                }
                for assessment in penalties.assessments
            ],
            "totalIncrease": _channel_decimal(penalties.total_increase),
            "principalAssessed": _channel_decimal(penalties.principal_assessed),
        }
        channel["penalties"]["firstPaymentRule"] = _first_payment_rule_block(
            penalties.first_payment_rule
        )
    return channel


#: Every provenance field a truth artifact may carry, and the complete list.
#:
#: **A truth file's bytes must depend on the corpus and nothing else.** These are
#: root files in the output tree, so the golden gate hashes them **raw** — the
#: ``provenance.substrateSha`` redaction that `_case_digest` and `_caseload_digest`
#: apply to the *manifests* cannot reach them. `substrateSha` comes from `git log`
#: over the substrate directory, so it describes the checkout: the same corpus
#: generated from a PR branch and from that PR's merge ref produces different
#: truth bytes, and the gate correctly reports drift for a corpus that never
#: changed. That is exactly what happened on this branch in CI, and it is the
#: gate working — it caught an artifact that varied by checkout, which no local
#: run could see, because locally the two checkouts are the same one.
#:
#: The pin is not lost: `manifest.json` still carries `provenance.substrateSha`,
#: where the redaction contract already governs it. A scorer that needs the
#: substrate revision reads it there. Duplicating a checkout-dependent value into
#: an artifact hashed raw was the defect.
TRUTH_PROVENANCE_KEYS: frozenset[str] = frozenset({"generator", "seedHash", "rngSeed"})
CASELOAD_TRUTH_PROVENANCE_KEYS: frozenset[str] = frozenset({"generator"})


_CAMEL_BOUNDARY = re.compile(r"_([a-z0-9])")


def _camel(name: str) -> str:
    return _CAMEL_BOUNDARY.sub(lambda match: match.group(1).upper(), name)


_SNAKE_BOUNDARY = re.compile(r"([A-Z])")


def _snake(name: str) -> str:
    return _SNAKE_BOUNDARY.sub(lambda match: f"_{match.group(1).lower()}", name)


def _camelize(
    value: Any,
    *,
    always_present_keys: frozenset[str] = frozenset(),
) -> Any:
    """Recursively camelCase keys while dropping ordinary null/empty values."""
    if isinstance(value, Mapping):
        return {
            _camel(str(key)): _camelize(
                item,
                always_present_keys=always_present_keys,
            )
            for key, item in value.items()
            if (
                _camel(str(key)) in always_present_keys
                or (item is not None and item != [] and item != ())
            )
        }
    if isinstance(value, list | tuple):
        return [
            _camelize(item, always_present_keys=always_present_keys)
            for item in value
        ]
    return value


def _snakeize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {_snake(str(key)): _snakeize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_snakeize(item) for item in value]
    return value


def assertion_ledger_digest(channel: Mapping[str, Any]) -> str:
    """SHA-256 over the canonical assertions payload.

    Canonical means compact separators, sorted keys, UTF-8, with
    ``channelVersion`` and ``ledgerDigest`` removed — the digest covers the
    validation context, the redacted history projection, every semantic
    assertion field, every lifecycle state and every truth-only quality.
    """
    payload = {
        key: value
        for key, value in channel.items()
        if key not in ("channelVersion", "ledgerDigest")
    }
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _assertions_v1_projection(
    model: BaseModel,
    fields: tuple[str, ...],
) -> dict[str, object]:
    """The A1-R4 restricted projection: allowlist first, serialization second.

    The unrestricted ``model_dump(mode="json", exclude_none=True)`` this
    replaced would serialize every field a model *has*, so an M3 field added to
    :class:`~wc_caseload_engine.medical_assertions.MedicalOpinion` would leak
    into the frozen ``1.0.0`` channel merely by existing. Selection happens
    through the literal tuple; the restricted ``model_dump(include=...)`` is
    only the value encoder inside that selection; the result is reconstructed
    in allowlist order. Adding a model field is therefore inert here.
    """
    serialized = model.model_dump(
        mode="json",
        include=frozenset(fields),
        exclude_none=True,
    )
    return {
        field: serialized[field]
        for field in fields
        if field in serialized
    }


def _assertions_v1_record(source: object, fields: tuple[str, ...]) -> dict[str, Any]:
    """One projection dataclass record, reduced to its frozen v1 field tuple.

    The manually built ``validationContext``/``medicalHistory`` sections must
    obey the same rule as the ledger models (A1-R4): membership comes from the
    allowlist, never from the object's own attribute surface, so a new field on
    :class:`~wc_caseload_engine.medical_assertions.ProjectedCondition` cannot
    enter channel ``1.0.0``. ``None`` values survive here and are dropped by
    ``_camelize`` exactly as before.
    """
    values: dict[str, Any] = {}
    for name in fields:
        value = getattr(source, name)
        if isinstance(value, dt.date):
            value = value.isoformat()
        elif isinstance(value, tuple):
            value = list(value)
        values[name] = value
    return values


def _assertions_v1_prior_claim(claim: Any) -> dict[str, Any]:
    """One prior-claim record with its nested award, both allowlist-driven."""
    values: dict[str, Any] = {}
    for name in ASSERTIONS_V1_PRIOR_CLAIM_FIELDS:
        if name == "award":
            values[name] = (
                _assertions_v1_record(claim.award, ASSERTIONS_V1_PRIOR_AWARD_FIELDS)
                if claim.award is not None
                else None
            )
        else:
            value = getattr(claim, name)
            if isinstance(value, dt.date):
                value = value.isoformat()
            elif isinstance(value, tuple):
                value = list(value)
            values[name] = value
    return values


def _assertions_v1_channel(plan: CasePlan) -> dict[str, Any]:
    """The complete assertions channel for one plan — the ONLY quality surface.

    FROZEN to the AJC-61 projection (Amendment A1): every section below is
    built from an ``ASSERTIONS_V1_*`` literal allowlist, so an M3 model or
    projection field serializes here only when a future channel ``2.0.0``
    (AJC-63/M4) adds it on purpose.
    """
    from wc_caseload_engine.medical_assertions import (
        assertion_context,
        project_medical_history,
    )

    source_ledger = plan.medical_assertions
    assert source_ledger is not None
    context = assertion_context(plan.seed, plan.timeline)
    projection = project_medical_history(
        plan.medical_history, context.current_body_parts
    )
    ledger = grade_ledger(
        context,
        projection,
        source_ledger,
        quality_contract="1.0.0",
    )

    validation_context: dict[str, Any] = {}
    for key in ASSERTIONS_V1_VALIDATION_CONTEXT_KEYS:
        value: Any = getattr(context, _snake(key))
        if isinstance(value, dt.date):
            value = value.isoformat()
        elif isinstance(value, tuple):
            value = list(value)
        validation_context[key] = value
    for key in ASSERTIONS_V1_OPTIONAL_VALIDATION_CONTEXT_KEYS:
        optional = getattr(context, _snake(key))
        if optional != "none":
            validation_context[key] = optional

    medical_history = {
        "conditions": [
            _camelize(_assertions_v1_record(c, ASSERTIONS_V1_CONDITION_FIELDS))
            for c in projection.conditions
        ],
        "priorClaims": [
            _camelize(_assertions_v1_prior_claim(claim))
            for claim in projection.prior_claims
        ],
    }

    channel: dict[str, Any] = {
        "channelVersion": ASSERTIONS_CHANNEL_VERSION,
        "kind": "case",
        "audience": AUDIENCE,
        "leakageRule": LEAKAGE_RULE,
        "validationContext": validation_context,
        "medicalHistory": medical_history,
        "contentions": [
            _camelize(_assertions_v1_projection(c, ASSERTIONS_V1_CONTENTION_FIELDS))
            for c in ledger.contentions
        ],
        "medicalOpinions": [
            _camelize(_assertions_v1_projection(o, ASSERTIONS_V1_MEDICAL_OPINION_FIELDS))
            for o in ledger.medical_opinions
        ],
        "apportionmentAssertions": [
            _camelize(
                _assertions_v1_projection(a, ASSERTIONS_V1_APPORTIONMENT_ASSERTION_FIELDS)
            )
            for a in ledger.apportionment_assertions
        ],
    }
    channel["ledgerDigest"] = assertion_ledger_digest(channel)
    return channel


def _assertions_v2_projection(
    model: BaseModel,
    fields: tuple[str, ...],
) -> dict[str, object]:
    """V2's independent literal projection; never serialize unrestricted models."""
    serialized = model.model_dump(
        mode="json",
        include=frozenset(fields),
        exclude_none=True,
    )
    return {
        field: serialized[field]
        for field in fields
        if field in serialized
    }


def _assertions_v2_record(source: object, fields: tuple[str, ...]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for name in fields:
        value = getattr(source, name)
        if isinstance(value, dt.date):
            value = value.isoformat()
        elif isinstance(value, tuple):
            value = list(value)
        values[name] = value
    return values


def _assertions_v2_prior_claim(claim: Any) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for name in ASSERTIONS_V2_PRIOR_CLAIM_FIELDS:
        if name == "award":
            values[name] = (
                _assertions_v2_record(
                    claim.award,
                    ASSERTIONS_V2_PRIOR_AWARD_FIELDS,
                )
                if claim.award is not None
                else None
            )
        else:
            value = getattr(claim, name)
            if isinstance(value, dt.date):
                value = value.isoformat()
            elif isinstance(value, tuple):
                value = list(value)
            values[name] = value
    return values


def _assertions_v2_binding_record(
    binding: ContentionDocumentProjection,
    documents: Sequence[object],
) -> dict[str, Any]:
    """Serialize one already-validated final binding in its literal v2 shape."""
    # Keep the realized document available at this boundary: the canonical
    # subtype is intentionally already captured on ``binding``; internal
    # template dispatch must never replace it here.
    document = documents[binding.document_index]
    row = _camelize(
        _assertions_v2_projection(
            binding,
            ASSERTIONS_V2_CONTENTION_DOCUMENT_FIELDS,
        ),
        always_present_keys=ALWAYS_PRESENT_V2_KEYS,
    )
    assert document.subtype == row["subtype"]
    return row


def _assertions_v2_channel(plan: CasePlan) -> dict[str, Any]:
    """Build the exact additive AJC-63 assertions-channel projection."""
    from wc_caseload_engine.medical_assertions import (
        assertion_context,
        project_medical_history,
    )

    source_ledger = plan.medical_assertions
    assert source_ledger is not None
    context = assertion_context(plan.seed, plan.timeline)
    projection = project_medical_history(
        plan.medical_history,
        context.current_body_parts,
    )
    ledger = grade_ledger(
        context,
        projection,
        source_ledger,
        quality_contract="2.0.0",
    )

    validation_context: dict[str, Any] = {}
    for key in ASSERTIONS_V2_VALIDATION_CONTEXT_KEYS:
        value: Any = getattr(context, _snake(key))
        if isinstance(value, dt.date):
            value = value.isoformat()
        elif isinstance(value, tuple):
            value = list(value)
        validation_context[key] = value
    for key in ASSERTIONS_V2_OPTIONAL_VALIDATION_CONTEXT_KEYS:
        optional = getattr(context, _snake(key))
        if optional != "none":
            validation_context[key] = optional

    medical_history = {
        "conditions": [
            _camelize(
                _assertions_v2_record(c, ASSERTIONS_V2_CONDITION_FIELDS),
                always_present_keys=ALWAYS_PRESENT_V2_KEYS,
            )
            for c in projection.conditions
        ],
        "priorClaims": [
            _camelize(
                _assertions_v2_prior_claim(claim),
                always_present_keys=ALWAYS_PRESENT_V2_KEYS,
            )
            for claim in projection.prior_claims
        ],
    }
    bindings = contention_document_projections(plan.documents)
    binding_problems = validate_contention_document_bindings(
        projection,
        ledger,
        bindings,
        plan.documents,
    )
    if binding_problems:
        raise TruthManifestError("\n".join(binding_problems))

    channel: dict[str, Any] = {
        "channelVersion": ASSERTIONS_V2_CHANNEL_VERSION,
        "kind": "case",
        "audience": AUDIENCE,
        "leakageRule": LEAKAGE_RULE,
        "validationContext": validation_context,
        "medicalHistory": medical_history,
        "contentions": [
            _camelize(
                _assertions_v2_projection(c, ASSERTIONS_V2_CONTENTION_FIELDS),
                always_present_keys=ALWAYS_PRESENT_V2_KEYS,
            )
            for c in ledger.contentions
        ],
        "medicalOpinions": [
            _camelize(
                _assertions_v2_projection(
                    opinion,
                    ASSERTIONS_V2_MEDICAL_OPINION_FIELDS,
                ),
                always_present_keys=ALWAYS_PRESENT_V2_KEYS,
            )
            for opinion in ledger.medical_opinions
        ],
        "apportionmentAssertions": [
            _camelize(
                _assertions_v2_projection(
                    assertion,
                    ASSERTIONS_V2_APPORTIONMENT_ASSERTION_FIELDS,
                ),
                always_present_keys=ALWAYS_PRESENT_V2_KEYS,
            )
            for assertion in ledger.apportionment_assertions
        ],
        "contentionDocuments": [
            _assertions_v2_binding_record(binding, plan.documents)
            for binding in bindings
        ],
    }
    channel["ledgerDigest"] = assertion_ledger_digest(channel)
    return channel


def _context_from_truth(document: Mapping[str, Any]) -> AssertionValidationContext:
    return AssertionValidationContext(
        date_of_injury=dt.date.fromisoformat(
            _required(document, "dateOfInjury", "channels.assertions.validationContext")
        ),
        anchor_date=dt.date.fromisoformat(
            _required(document, "anchorDate", "channels.assertions.validationContext")
        ),
        current_body_parts=tuple(
            _required(
                document, "currentBodyParts", "channels.assertions.validationContext"
            )
        ),
        target_stage=_required(
            document, "targetStage", "channels.assertions.validationContext"
        ),
        claim_response=_required(
            document, "claimResponse", "channels.assertions.validationContext"
        ),
        eval_type=document.get("evalType", "none"),
    )


def _projection_from_truth(document: Mapping[str, Any]) -> AssertionWorldProjection:
    conditions = []
    for item in document.get("conditions", []):
        data = _snakeize(item)
        data["onset"] = (
            dt.date.fromisoformat(data["onset"]) if data.get("onset") else None
        )
        data.setdefault("body_part", None)
        data.setdefault("symptomatic_before_doi", None)
        data["apportionment_targets"] = tuple(data.get("apportionment_targets", ()))
        conditions.append(ProjectedCondition(**data))
    claims = []
    for item in document.get("priorClaims", []):
        data = _snakeize(item)
        award_data = data.pop("award", None)
        award = None
        if award_data is not None:
            award_data["award_date"] = dt.date.fromisoformat(award_data["award_date"])
            award_data["body_parts"] = tuple(award_data["body_parts"])
            award = ProjectedPriorAward(**award_data)
        data["date_of_injury"] = dt.date.fromisoformat(data["date_of_injury"])
        data["body_parts"] = tuple(data["body_parts"])
        claims.append(ProjectedPriorClaim(award=award, **data))
    return AssertionWorldProjection(
        conditions=tuple(conditions), prior_claims=tuple(claims)
    )


def _ledger_from_truth(
    channel: Mapping[str, Any],
    *,
    quality_contract: AssertionQualityContract,
) -> MedicalAssertionLedger:
    def entries(key: str) -> list[dict[str, Any]]:
        return [_snakeize(item) for item in channel.get(key, [])]

    opinions = entries("medicalOpinions")
    if quality_contract == "2.0.0":
        raw_opinions = channel.get("medicalOpinions", [])
        for index, item in enumerate(raw_opinions):
            opinion = _mapping(
                item,
                f"channels.assertions.medicalOpinions[{index}]",
            )
            if "eventKind" not in opinion:
                raise TruthManifestError(
                    "malformed assertions channel: medical opinion "
                    f"{index} is missing required eventKind"
                )
            event_kind = opinion["eventKind"]
            if event_kind == "base_report" and "revisionKind" in opinion:
                raise TruthManifestError(
                    "malformed assertions channel: base medical opinion "
                    f"{index} must omit revisionKind"
                )
            if event_kind != "base_report" and "revisionKind" not in opinion:
                raise TruthManifestError(
                    "malformed assertions channel: response medical opinion "
                    f"{index} is missing required revisionKind"
                )

    return MedicalAssertionLedger.model_validate(
        {
            "contentions": entries("contentions"),
            "medical_opinions": opinions,
            "apportionment_assertions": entries("apportionmentAssertions"),
        }
    )


def _contention_documents_from_truth(
    channel: Mapping[str, Any],
    *,
    quality_contract: AssertionQualityContract,
) -> tuple[ContentionDocumentProjection, ...]:
    if quality_contract == "1.0.0":
        return ()
    if "contentionDocuments" not in channel:
        raise TruthManifestError(
            "malformed assertions channel: missing channels.assertions.contentionDocuments"
        )
    rows = _sequence(
        channel["contentionDocuments"],
        "channels.assertions.contentionDocuments",
    )
    bindings: list[ContentionDocumentProjection] = []
    for index, item in enumerate(rows):
        row = _mapping(
            item,
            f"channels.assertions.contentionDocuments[{index}]",
        )
        if "spokenContentionIds" not in row:
            raise TruthManifestError(
                "malformed assertions channel: contentionDocuments row "
                f"{index} is missing required spokenContentionIds"
            )
        bindings.append(
            ContentionDocumentProjection.model_validate(_snakeize(row))
        )
    return tuple(bindings)


def parse_medical_assertions_from_truth(
    document: Mapping[str, Any],
) -> tuple[
    AssertionQualityContract,
    AssertionValidationContext,
    AssertionWorldProjection,
    MedicalAssertionLedger,
    tuple[ContentionDocumentProjection, ...],
] | None:
    """Parse the typed assertions payload without running either validator."""
    _require_compatible_version(
        document,
        key="schemaVersion",
        path="$",
        supported=SCHEMA_VERSION,
        label="truth manifest envelope",
    )
    channels = _mapping(_required(document, "channels", "$"), "channels")
    if "assertions" not in channels:
        return None
    channel = _mapping(channels["assertions"], "channels.assertions")
    quality_contract = _assertions_quality_contract(channel)
    stated_digest = channel.get("ledgerDigest")
    if stated_digest != assertion_ledger_digest(channel):
        raise TruthManifestError(LEDGER_DIGEST_MISMATCH)
    try:
        context = _context_from_truth(
            _mapping(
                _required(channel, "validationContext", "channels.assertions"),
                "channels.assertions.validationContext",
            )
        )
        projection = _projection_from_truth(
            _mapping(
                _required(channel, "medicalHistory", "channels.assertions"),
                "channels.assertions.medicalHistory",
            )
        )
        ledger = _ledger_from_truth(
            channel,
            quality_contract=quality_contract,
        )
        bindings = _contention_documents_from_truth(
            channel,
            quality_contract=quality_contract,
        )
    except TruthManifestError:
        raise
    except (TypeError, ValueError, KeyError, ValidationError) as exc:
        raise TruthManifestError(f"malformed assertions channel: {exc}") from exc
    return quality_contract, context, projection, ledger, bindings


def medical_assertions_from_truth(
    document: Mapping[str, Any],
    *,
    manifest_documents: Sequence[object] | None = None,
) -> tuple[AssertionValidationContext, AssertionWorldProjection, MedicalAssertionLedger] | None:
    """Validate and reconstruct the assertions channel, or ``None`` when absent.

    The order is the contract (Part 4 §D): check the channel major, recompute
    the digest against the canonical payload, parse the typed context /
    projection / ledger, run the §C incoherence validator, then rederive every
    ``quality`` under the frozen rubric — a tampered label is artifact
    incoherence even when the digest was recomputed to match.

    Requires no substrate checkout and performs no substrate-access call: every
    input the rules need rides in the recorded payload.
    """
    parsed = parse_medical_assertions_from_truth(document)
    if parsed is None:
        return None
    quality_contract, context, projection, ledger, bindings = parsed

    problems = validate_medical_assertions(context, projection, ledger)
    if quality_contract == "2.0.0":
        problems += validate_contention_document_bindings(
            projection,
            ledger,
            bindings,
            manifest_documents,
        )
    if problems:
        raise TruthManifestError("\n".join(problems))

    rederived = grade_ledger(
        context,
        projection,
        ledger,
        quality_contract=quality_contract,
    )
    for stated_collection, derived_collection in (
        (ledger.contentions, rederived.contentions),
        (ledger.medical_opinions, rederived.medical_opinions),
        (ledger.apportionment_assertions, rederived.apportionment_assertions),
    ):
        for stated, derived in zip(stated_collection, derived_collection, strict=True):
            if stated.quality != derived.quality:
                raise TruthManifestError(
                    f"channels.assertions: quality '{stated.quality}' on "
                    f"'{stated.id}' does not match the rederived grade "
                    f"'{derived.quality}'"
                )
    return context, projection, ledger


def _truth_manifest_version(value: int) -> int:
    if value not in (1, 2):
        raise TruthManifestError(
            f"truth manifest version {value!r} is unsupported; choose 1 or 2"
        )
    return value


def _ledger_for_contract(
    plan: CasePlan,
    quality_contract: AssertionQualityContract,
) -> MedicalAssertionLedger:
    from wc_caseload_engine.medical_assertions import (
        assertion_context,
        project_medical_history,
    )

    ledger = plan.medical_assertions
    assert ledger is not None
    context = assertion_context(plan.seed, plan.timeline)
    projection = project_medical_history(
        plan.medical_history,
        context.current_body_parts,
    )
    return grade_ledger(
        context,
        projection,
        ledger,
        quality_contract=quality_contract,
    )


def build_case_truth_manifest(
    plan: CasePlan,
    truth_manifest_version: int = 1,
) -> dict[str, Any]:
    """Build one versioned scorer envelope without reading any wall clock."""
    version = _truth_manifest_version(truth_manifest_version)
    channels: dict[str, Any] = {}
    if plan.money_facts is not None:
        channels["money"] = _money_channel(plan.money_facts)
    if plan.medical_assertions is not None:
        channels["assertions"] = (
            _assertions_v1_channel(plan)
            if version == 1
            else _assertions_v2_channel(plan)
        )
    return {
        "schemaVersion": SCHEMA_VERSION,
        "kind": "case",
        "audience": AUDIENCE,
        "leakageRule": LEAKAGE_RULE,
        "caseId": plan.seed.case_id,
        # Deterministic fields only — see TRUTH_PROVENANCE_KEYS.
        "provenance": {
            "generator": GENERATOR,
            "seedHash": plan.seed.seed_hash(),
            "rngSeed": plan.seed.rng_seed,
        },
        "channels": channels,
    }


def build_caseload_truth_manifest(
    caseload_id: str,
    results: Sequence[CaseResult | _CaseResultLike],
    truth_manifest_version: int = 1,
) -> dict[str, Any]:
    """Build a complete corpus index while omitting an empty money channel."""
    version = _truth_manifest_version(truth_manifest_version)
    quality_contract: AssertionQualityContract = (
        "1.0.0" if version == 1 else "2.0.0"
    )
    cases: list[dict[str, Any]] = []
    money_case_count = 0
    for result in results:
        if result.truth_path is None:
            raise TruthManifestError(
                f"cannot index case {result.case_id!r}: its truth manifest was not written"
            )
        plan = result.plan
        entry: dict[str, Any] = {
            "caseId": result.case_id,
            "truthFile": f"{result.truth_path.parent.name}/{result.truth_path.name}",
            "seedHash": plan.seed.seed_hash(),
        }
        if plan.money_facts is not None:
            money_case_count += 1
            facts = plan.money_facts
            entry.update(
                {
                    "averageWeeklyWage": dollars(facts.wages.aww),
                    "tdWeeklyRate": dollars(facts.wages.rate.td_weekly_rate),
                    "tdBound": facts.wages.rate.td_bound,
                    "method": facts.wages.computation.method,
                }
            )
            if facts.settlement is not None:
                entry["settlementGrossAmount"] = dollars(facts.settlement.gross_amount)
        cases.append(entry)

    channels: dict[str, Any] = {}
    if money_case_count:
        # An independent list of independent record dicts — the top-level
        # index, channels.money.cases and channels.assertions.cases must
        # never share structure, or a later mutation of one channel moves
        # another channel's bytes (sol review, PR #44 M2 / Part 4:141).
        channels["money"] = {
            "channelVersion": MONEY_CHANNEL_VERSION,
            "caseCount": len(results),
            "moneyCaseCount": money_case_count,
            "cases": [dict(entry) for entry in cases],
        }

    # The assertions rollup allocates its own list and case dictionaries for
    # the same reason (L16).
    assertion_cases: list[dict[str, Any]] = []
    quality_counts = {"supported": 0, "thin": 0, "unsupportable": 0}
    state_counts = {"deferred": 0, "determined": 0, "omitted": 0}
    determination_kind_counts = {
        "allocated": 0,
        "noNonindustrialShare": 0,
        "unableToApproximate": 0,
    }
    totals = {"contentions": 0, "medicalOpinions": 0, "apportionmentAssertions": 0}
    for result in results:
        source_ledger = result.plan.medical_assertions
        if source_ledger is None:
            continue
        ledger = _ledger_for_contract(result.plan, quality_contract)
        bindings = contention_document_projections(result.plan.documents)
        entry = {
            "caseId": result.case_id,
            "truthFile": f"{result.truth_path.parent.name}/{result.truth_path.name}",
            "contentionCount": len(ledger.contentions),
            "medicalOpinionCount": len(ledger.medical_opinions),
            "apportionmentAssertionCount": len(ledger.apportionment_assertions),
        }
        if version == 2:
            entry["contentionDocumentCount"] = len(bindings)
        assertion_cases.append(entry)
        for quality, count in ledger.quality_counts().items():
            quality_counts[quality] += count
        totals["contentions"] += len(ledger.contentions)
        totals["medicalOpinions"] += len(ledger.medical_opinions)
        totals["apportionmentAssertions"] += len(ledger.apportionment_assertions)
        if version == 2:
            totals["contentionDocuments"] = totals.get("contentionDocuments", 0) + len(
                bindings
            )
        for opinion in ledger.medical_opinions:
            state_counts[opinion.apportionment_state] += 1
            if opinion.determination_kind is not None:
                determination_kind_counts[_camel(opinion.determination_kind)] += 1
    if assertion_cases:
        channels["assertions"] = {
            "channelVersion": (
                ASSERTIONS_CHANNEL_VERSION
                if version == 1
                else ASSERTIONS_V2_CHANNEL_VERSION
            ),
            "caseCount": len(results),
            "assertionCaseCount": len(assertion_cases),
            "counts": totals,
            "qualityCounts": quality_counts,
            "apportionmentStateCounts": state_counts,
            "determinationKindCounts": determination_kind_counts,
            "cases": assertion_cases,
        }
    return {
        "schemaVersion": SCHEMA_VERSION,
        "kind": "caseload",
        "audience": AUDIENCE,
        "leakageRule": LEAKAGE_RULE,
        "caseloadId": caseload_id,
        # Deterministic fields only — see CASELOAD_TRUTH_PROVENANCE_KEYS.
        "provenance": {"generator": GENERATOR},
        "cases": cases,
        "channels": channels,
    }


def write_case_truth_manifest(
    plan: CasePlan,
    truth_dir: Path,
    truth_manifest_version: int = 1,
) -> Path:
    """Write one case truth artifact and return its exact path."""
    truth_dir.mkdir(parents=True, exist_ok=True)
    path = truth_dir / case_truth_name(plan.seed.case_id)
    _write_json(
        path,
        build_case_truth_manifest(
            plan,
            truth_manifest_version=truth_manifest_version,
        ),
    )
    return path


def write_caseload_truth_manifest(
    caseload_id: str,
    results: Sequence[CaseResult | _CaseResultLike],
    truth_dir: Path,
    truth_manifest_version: int = 1,
) -> Path:
    """Write the scorer's caseload index beside the per-case truth artifacts."""
    truth_dir.mkdir(parents=True, exist_ok=True)
    path = truth_dir / CASELOAD_TRUTH_NAME
    _write_json(
        path,
        build_caseload_truth_manifest(
            caseload_id,
            results,
            truth_manifest_version=truth_manifest_version,
        ),
    )
    return path


def read_truth_manifest(path: Path) -> dict[str, Any]:
    """Read a truth manifest after validating the envelope's container shapes."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TruthManifestError(f"cannot read truth manifest {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise TruthManifestError(f"truth manifest {path} must contain a JSON object")
    _require_compatible_version(
        payload,
        key="schemaVersion",
        path="$",
        supported=SCHEMA_VERSION,
        label="truth manifest envelope",
    )
    channels = payload.get("channels")
    if not isinstance(channels, dict):
        raise TruthManifestError(f"truth manifest {path} must contain an object at 'channels'")
    if "money" in channels:
        money_channel = _mapping(channels["money"], "channels.money")
        _require_compatible_version(
            money_channel,
            key="channelVersion",
            path="channels.money",
            supported=MONEY_CHANNEL_VERSION,
            label="money channel",
        )
    if "assertions" in channels:
        assertions_channel = _mapping(channels["assertions"], "channels.assertions")
        _assertions_quality_contract(assertions_channel)
    return payload


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TruthManifestError(f"malformed money channel: {path} must be an object")
    return value


def _sequence(value: Any, path: str) -> Sequence[Any]:
    if not isinstance(value, list):
        raise TruthManifestError(f"malformed money channel: {path} must be an array")
    return value


def _required(document: Mapping[str, Any], key: str, path: str) -> Any:
    try:
        return document[key]
    except KeyError as exc:
        raise TruthManifestError(f"malformed money channel: missing {path}.{key}") from exc


def _require_compatible_version(
    document: Mapping[str, Any],
    *,
    key: str,
    path: str,
    supported: str,
    label: str,
) -> str:
    """Parse one contract semver and require the reader's supported major."""
    location = key if path == "$" else f"{path}.{key}"
    if key not in document:
        raise TruthManifestError(f"malformed {label}: missing {location}")
    version = document[key]
    if not isinstance(version, str):
        raise TruthManifestError(
            f"malformed {label}: {location} {version!r} must be major.minor.patch"
        )
    parts = version.split(".")
    if len(parts) != 3 or any(not part.isdigit() for part in parts):
        raise TruthManifestError(
            f"malformed {label}: {location} {version!r} must be major.minor.patch"
        )
    if parts[0] != supported.partition(".")[0]:
        raise TruthManifestError(
            f"unsupported {label} version {version!r}; reader supports {supported!r}"
        )
    return version


def _assertions_quality_contract(
    channel: Mapping[str, Any],
) -> AssertionQualityContract:
    """Normalize a compatible assertions-channel semver to its major contract."""
    location = "channels.assertions.channelVersion"
    if "channelVersion" not in channel:
        raise TruthManifestError(
            f"malformed assertions channel: missing {location}"
        )
    version = channel["channelVersion"]
    if not isinstance(version, str):
        raise TruthManifestError(
            f"malformed assertions channel: {location} {version!r} must be major.minor.patch"
        )
    parts = version.split(".")
    if len(parts) != 3 or any(not part.isdigit() for part in parts):
        raise TruthManifestError(
            f"malformed assertions channel: {location} {version!r} must be major.minor.patch"
        )
    if parts[0] == "1":
        return "1.0.0"
    if parts[0] == "2":
        return "2.0.0"
    raise TruthManifestError(
        f"unsupported assertions channel version {version!r}; reader supports "
        f"{ASSERTIONS_CHANNEL_VERSION!r} and {ASSERTIONS_V2_CHANNEL_VERSION!r}"
    )


def _model_data(document: Mapping[str, Any], names: Mapping[str, str], path: str) -> dict[str, Any]:
    return {field: _required(document, key, path) for key, field in names.items()}


def money_facts_from_truth(document: Mapping[str, Any]) -> MoneyFacts | None:
    """Reconstruct validated money facts, ignoring every unrelated channel."""
    _require_compatible_version(
        document,
        key="schemaVersion",
        path="$",
        supported=SCHEMA_VERSION,
        label="truth manifest envelope",
    )
    channels = _mapping(_required(document, "channels", "$"), "channels")
    if "money" not in channels:
        return None
    channel = _mapping(channels["money"], "channels.money")
    _require_compatible_version(
        channel,
        key="channelVersion",
        path="channels.money",
        supported=MONEY_CHANNEL_VERSION,
        label="money channel",
    )

    try:
        wage_doc = _mapping(_required(channel, "wage", "channels.money"), "channels.money.wage")
        computation_doc = _mapping(
            _required(wage_doc, "computation", "channels.money.wage"),
            "channels.money.wage.computation",
        )
        rate_doc = _mapping(
            _required(wage_doc, "rate", "channels.money.wage"), "channels.money.wage.rate"
        )
        basis_doc = _mapping(
            _required(rate_doc, "basis", "channels.money.wage.rate"),
            "channels.money.wage.rate.basis",
        )
        basis = RateBasis(
            **_model_data(
                basis_doc,
                {
                    "label": "label",
                    "effectiveFrom": "effective_from",
                    "effectiveTo": "effective_to",
                    "tdFraction": "td_fraction",
                    "tdMaxWeekly": "td_max_weekly",
                    "tdMinWeekly": "td_min_weekly",
                    "pdFraction": "pd_fraction",
                    "pdMaxWeekly": "pd_max_weekly",
                    "pdMinWeekly": "pd_min_weekly",
                    "authority": "authority",
                    "counselConfirmed": "counsel_confirmed",
                    "source": "source",
                },
                "channels.money.wage.rate.basis",
            )
        )
        computation = AwwComputation(
            **_model_data(
                computation_doc,
                {
                    "method": "method",
                    "methodSource": "method_source",
                    "methodReason": "method_reason",
                    "periodsConsidered": "periods_considered",
                    "weeksConsidered": "weeks_considered",
                    "grossConsidered": "gross_considered",
                    "inKindWeekly": "in_kind_weekly",
                    "averageWeeklyWage": "aww",
                },
                "channels.money.wage.computation",
            )
        )
        rate = CompRate(
            basis=basis,
            **_model_data(
                rate_doc,
                {
                    "averageWeeklyWage": "aww",
                    "tdWeeklyRate": "td_weekly_rate",
                    "tdBound": "td_bound",
                    "pdWeeklyRate": "pd_weekly_rate",
                    "pdBound": "pd_bound",
                },
                "channels.money.wage.rate",
            ),
        )
        periods = tuple(
            EarningsPeriod(
                **_model_data(
                    _mapping(item, f"channels.money.wage.periods[{index}]"),
                    {
                        "periodStart": "period_start",
                        "periodEnd": "period_end",
                        "weeks": "weeks",
                        "regularGross": "regular_gross",
                        "overtimeGross": "overtime_gross",
                        "concurrent": "concurrent",
                    },
                    f"channels.money.wage.periods[{index}]",
                )
            )
            for index, item in enumerate(
                _sequence(
                    _required(wage_doc, "periods", "channels.money.wage"),
                    "channels.money.wage.periods",
                )
            )
        )
        in_kind = tuple(
            InKindWage(
                **_model_data(
                    _mapping(item, f"channels.money.wage.inKind[{index}]"),
                    {
                        "kind": "kind",
                        "weeklyValue": "weekly_value",
                    },
                    f"channels.money.wage.inKind[{index}]",
                )
            )
            for index, item in enumerate(
                _sequence(
                    _required(wage_doc, "inKind", "channels.money.wage"),
                    "channels.money.wage.inKind",
                )
            )
        )
        wage = WageFacts(
            periods=periods,
            in_kind=in_kind,
            computation=computation,
            rate=rate,
            **_model_data(
                wage_doc,
                {
                    "employmentStart": "employment_start",
                    "concurrentEmployment": "concurrent_employment",
                    "pattern": "pattern",
                    "patternSource": "pattern_source",
                },
                "channels.money.wage",
            ),
        )
        benefits_doc = _mapping(
            _required(channel, "benefits", "channels.money"), "channels.money.benefits"
        )
        td_periods = tuple(
            TdPeriod(
                **_model_data(
                    _mapping(item, f"channels.money.benefits.tdPeriods[{index}]"),
                    {
                        "start": "start",
                        "end": "end",
                        "weeks": "weeks",
                        "weeklyRate": "weekly_rate",
                        "amount": "amount",
                        "dateDue": "date_due",
                        "datePaid": "date_paid",
                        "daysLate": "days_late",
                    },
                    f"channels.money.benefits.tdPeriods[{index}]",
                )
            )
            for index, item in enumerate(
                _sequence(
                    _required(benefits_doc, "tdPeriods", "channels.money.benefits"),
                    "channels.money.benefits.tdPeriods",
                )
            )
        )
        pd_advances = tuple(
            PdAdvance(
                **_model_data(
                    _mapping(item, f"channels.money.benefits.pdAdvances[{index}]"),
                    {
                        "dateDue": "date_due",
                        "datePaid": "date_paid",
                        "weeks": "weeks",
                        "weeklyRate": "weekly_rate",
                        "amount": "amount",
                        "daysLate": "days_late",
                    },
                    f"channels.money.benefits.pdAdvances[{index}]",
                )
            )
            for index, item in enumerate(
                _sequence(
                    _required(benefits_doc, "pdAdvances", "channels.money.benefits"),
                    "channels.money.benefits.pdAdvances",
                )
            )
        )
        gaps = tuple(
            BenefitGap(
                **_model_data(
                    _mapping(item, f"channels.money.benefits.gaps[{index}]"),
                    {
                        "start": "start",
                        "end": "end",
                        "days": "days",
                    },
                    f"channels.money.benefits.gaps[{index}]",
                )
            )
            for index, item in enumerate(
                _sequence(
                    _required(benefits_doc, "gaps", "channels.money.benefits"),
                    "channels.money.benefits.gaps",
                )
            )
        )
        benefits = BenefitLedger(td_periods=td_periods, pd_advances=pd_advances, gaps=gaps)
        settlement = None
        if "settlement" in channel:
            settlement_doc = _mapping(channel["settlement"], "channels.money.settlement")
            settlement = SettlementFact(
                **_model_data(
                    settlement_doc,
                    {
                        "kind": "kind",
                        "grossAmount": "gross_amount",
                        "approvalDate": "approval_date",
                        "fundingDate": "funding_date",
                    },
                    "channels.money.settlement",
                )
            )
        penalties = None
        if "penalties" in channel:
            penalties_doc = _mapping(channel["penalties"], "channels.money.penalties")
            penalty_basis_doc = _mapping(
                _required(penalties_doc, "basis", "channels.money.penalties"),
                "channels.money.penalties.basis",
            )
            penalty_basis = PenaltyBasis(
                **_model_data(
                    penalty_basis_doc,
                    {
                        "label": "label",
                        "effectiveFrom": "effective_from",
                        "effectiveTo": "effective_to",
                        "increaseFraction": "increase_fraction",
                        "authority": "authority",
                        "counselConfirmed": "counsel_confirmed",
                        "source": "source",
                    },
                    "channels.money.penalties.basis",
                )
            )
            deadline_basis_doc = _mapping(
                _required(penalties_doc, "deadlines", "channels.money.penalties"),
                "channels.money.penalties.deadlines",
            )
            deadline_basis = StatutoryDeadlineBasis(
                **_model_data(
                    deadline_basis_doc,
                    {
                        "label": "label",
                        "effectiveFrom": "effective_from",
                        "effectiveTo": "effective_to",
                        "firstTdPaymentDays": "first_td_payment_days",
                        "subsequentTdPaymentDays": "subsequent_td_payment_days",
                        "firstPdPaymentDays": "first_pd_payment_days",
                        "authority": "authority",
                        "counselConfirmed": "counsel_confirmed",
                        "source": "source",
                    },
                    "channels.money.penalties.deadlines",
                )
            )
            schedule = tuple(
                StatutoryDueDate(
                    **_model_data(
                        _mapping(item, f"channels.money.penalties.schedule[{index}]"),
                        {
                            "source": "source",
                            "ordinal": "ordinal",
                            "rule": "rule",
                            "statutoryDueDate": "statutory_due_date",
                            "operationalDueDate": "operational_due_date",
                            "datePaid": "date_paid",
                            "daysLate": "days_late",
                            "unpaid": "unpaid",
                        },
                        f"channels.money.penalties.schedule[{index}]",
                    )
                )
                for index, item in enumerate(
                    _sequence(
                        _required(penalties_doc, "schedule", "channels.money.penalties"),
                        "channels.money.penalties.schedule",
                    )
                )
            )
            assessments = tuple(
                PenaltyAssessment(
                    **_model_data(
                        _mapping(item, f"channels.money.penalties.assessments[{index}]"),
                        {
                            "source": "source",
                            "ordinal": "ordinal",
                            "rule": "rule",
                            "principal": "principal",
                            "statutoryDueDate": "statutory_due_date",
                            "operationalDueDate": "operational_due_date",
                            "datePaid": "date_paid",
                            "daysLate": "days_late",
                            "increaseFraction": "increase_fraction",
                            "amount": "amount",
                        },
                        f"channels.money.penalties.assessments[{index}]",
                    )
                )
                for index, item in enumerate(
                    _sequence(
                        _required(penalties_doc, "assessments", "channels.money.penalties"),
                        "channels.money.penalties.assessments",
                    )
                )
            )
            first_payment_rule = None
            if penalties_doc.get("firstPaymentRule") is not None:
                first_payment_rule = FirstPaymentRule(
                    **_model_data(
                        _mapping(
                            penalties_doc["firstPaymentRule"],
                            "channels.money.penalties.firstPaymentRule",
                        ),
                        {
                            "anchor": "anchor",
                            "anchorDate": "anchor_date",
                            "dueDate": "due_date",
                            "datePaid": "date_paid",
                            "daysLate": "days_late",
                            "assessed": "assessed",
                            "counselConfirmed": "counsel_confirmed",
                            "authority": "authority",
                            "openQuestion": "open_question",
                        },
                        "channels.money.penalties.firstPaymentRule",
                    )
                )
            penalties = PenaltyLedger(
                basis=penalty_basis,
                deadlines=deadline_basis,
                schedule=schedule,
                assessments=assessments,
                first_payment_rule=first_payment_rule,
            )
        return MoneyFacts(
            wages=wage,
            benefits=benefits,
            settlement=settlement,
            penalties=penalties,
        )
    except TruthManifestError:
        raise
    except (TypeError, ValueError, ValidationError) as exc:
        raise TruthManifestError(f"malformed money channel: {exc}") from exc


__all__ = [
    "ALWAYS_PRESENT_V2_KEYS",
    "ASSERTIONS_CHANNEL_VERSION",
    "ASSERTIONS_V1_APPORTIONMENT_ASSERTION_FIELDS",
    "ASSERTIONS_V1_CASELOAD_CASE_KEYS",
    "ASSERTIONS_V1_CASELOAD_CHANNEL_KEYS",
    "ASSERTIONS_V1_CASE_CHANNEL_KEYS",
    "ASSERTIONS_V1_CONDITION_FIELDS",
    "ASSERTIONS_V1_CONTENTION_FIELDS",
    "ASSERTIONS_V1_MEDICAL_HISTORY_KEYS",
    "ASSERTIONS_V1_MEDICAL_OPINION_FIELDS",
    "ASSERTIONS_V1_OPTIONAL_VALIDATION_CONTEXT_KEYS",
    "ASSERTIONS_V1_PRIOR_AWARD_FIELDS",
    "ASSERTIONS_V1_PRIOR_CLAIM_FIELDS",
    "ASSERTIONS_V1_VALIDATION_CONTEXT_KEYS",
    "ASSERTIONS_V2_APPORTIONMENT_ASSERTION_FIELDS",
    "ASSERTIONS_V2_CASELOAD_CASE_KEYS",
    "ASSERTIONS_V2_CASELOAD_CHANNEL_KEYS",
    "ASSERTIONS_V2_CASE_CHANNEL_KEYS",
    "ASSERTIONS_V2_CHANNEL_VERSION",
    "ASSERTIONS_V2_CONDITION_FIELDS",
    "ASSERTIONS_V2_CONTENTION_DOCUMENT_FIELDS",
    "ASSERTIONS_V2_CONTENTION_FIELDS",
    "ASSERTIONS_V2_MEDICAL_HISTORY_KEYS",
    "ASSERTIONS_V2_MEDICAL_OPINION_FIELDS",
    "ASSERTIONS_V2_OPTIONAL_VALIDATION_CONTEXT_KEYS",
    "ASSERTIONS_V2_PRIOR_AWARD_FIELDS",
    "ASSERTIONS_V2_PRIOR_CLAIM_FIELDS",
    "ASSERTIONS_V2_VALIDATION_CONTEXT_KEYS",
    "CASELOAD_TRUTH_NAME",
    "CASELOAD_TRUTH_PROVENANCE_KEYS",
    "LEDGER_DIGEST_MISMATCH",
    "PENALTY_ASSESSMENT_KEY_NAMES",
    "SCORER_ONLY_ENVELOPE_KEY_NAMES",
    "TRUTH_DIR",
    "TRUTH_PROVENANCE_KEYS",
    "TruthManifestError",
    "assertion_ledger_digest",
    "build_case_truth_manifest",
    "build_caseload_truth_manifest",
    "case_truth_name",
    "check_truth_dir_is_isolated",
    "medical_assertions_from_truth",
    "money_facts_from_truth",
    "parse_medical_assertions_from_truth",
    "read_truth_manifest",
    "write_case_truth_manifest",
    "write_caseload_truth_manifest",
]
