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
from typing import TYPE_CHECKING, Any, Protocol

from pydantic import ValidationError

from wc_caseload_engine import __version__
from wc_caseload_engine.medical_assertions import (
    AssertionValidationContext,
    AssertionWorldProjection,
    MedicalAssertionLedger,
    ProjectedCondition,
    ProjectedPriorAward,
    ProjectedPriorClaim,
    grade_ledger,
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
breaking money-channel consumers, and this is that channel arriving."""

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


def _camelize(value: Any) -> Any:
    """Recursively camelCase mapping keys; values (enum strings, ids) untouched."""
    if isinstance(value, Mapping):
        return {
            _camel(str(key)): _camelize(item)
            for key, item in value.items()
            if item is not None and item != [] and item != ()
        }
    if isinstance(value, list | tuple):
        return [_camelize(item) for item in value]
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


def _assertions_channel(plan: CasePlan) -> dict[str, Any]:
    """The complete assertions channel for one plan — the ONLY quality surface."""
    from wc_caseload_engine.medical_assertions import (
        assertion_context,
        project_medical_history,
    )

    ledger = plan.medical_assertions
    assert ledger is not None
    context = assertion_context(plan.seed, plan.timeline)
    projection = project_medical_history(
        plan.medical_history, context.current_body_parts
    )

    validation_context: dict[str, Any] = {
        "dateOfInjury": context.date_of_injury.isoformat(),
        "anchorDate": context.anchor_date.isoformat(),
        "currentBodyParts": list(context.current_body_parts),
        "targetStage": context.target_stage,
        "claimResponse": context.claim_response,
    }
    if context.eval_type != "none":
        validation_context["evalType"] = context.eval_type

    medical_history = {
        "conditions": [
            _camelize(
                {
                    "id": c.id,
                    "key": c.key,
                    "label": c.label,
                    "causal_ground_truth": c.causal_ground_truth,
                    "onset": c.onset.isoformat() if c.onset is not None else None,
                    "body_system": c.body_system,
                    "body_part": c.body_part,
                    "apportionment_targets": list(c.apportionment_targets),
                    "wholly_unrelated": c.wholly_unrelated,
                    "severity": c.severity,
                    "trajectory": c.trajectory,
                    "symptomatic_before_doi": c.symptomatic_before_doi,
                    "surfaces_in_file": c.surfaces_in_file,
                }
            )
            for c in projection.conditions
        ],
        "priorClaims": [
            _camelize(
                {
                    "id": claim.id,
                    "date_of_injury": claim.date_of_injury.isoformat(),
                    "body_parts": list(claim.body_parts),
                    "resolution_type": claim.resolution_type,
                    "overlaps_current": claim.overlaps_current,
                    "award": (
                        {
                            "id": claim.award.id,
                            "prior_claim_id": claim.award.prior_claim_id,
                            "body_parts": list(claim.award.body_parts),
                            "pd_percent": claim.award.pd_percent,
                            "award_date": claim.award.award_date.isoformat(),
                            "resolution_type": claim.award.resolution_type,
                            "conclusively_presumed": claim.award.conclusively_presumed,
                        }
                        if claim.award is not None
                        else None
                    ),
                }
            )
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
            _camelize(c.model_dump(mode="json", exclude_none=True))
            for c in ledger.contentions
        ],
        "medicalOpinions": [
            _camelize(o.model_dump(mode="json", exclude_none=True))
            for o in ledger.medical_opinions
        ],
        "apportionmentAssertions": [
            _camelize(a.model_dump(mode="json", exclude_none=True))
            for a in ledger.apportionment_assertions
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


def _ledger_from_truth(channel: Mapping[str, Any]) -> MedicalAssertionLedger:
    def entries(key: str) -> list[dict[str, Any]]:
        return [_snakeize(item) for item in channel.get(key, [])]

    return MedicalAssertionLedger.model_validate(
        {
            "contentions": entries("contentions"),
            "medical_opinions": entries("medicalOpinions"),
            "apportionment_assertions": entries("apportionmentAssertions"),
        }
    )


def medical_assertions_from_truth(
    document: Mapping[str, Any],
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
    _require_compatible_version(
        channel,
        key="channelVersion",
        path="channels.assertions",
        supported=ASSERTIONS_CHANNEL_VERSION,
        label="assertions channel",
    )
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
        ledger = _ledger_from_truth(channel)
    except TruthManifestError:
        raise
    except (TypeError, ValueError, KeyError, ValidationError) as exc:
        raise TruthManifestError(f"malformed assertions channel: {exc}") from exc

    problems = validate_medical_assertions(context, projection, ledger)
    if problems:
        raise TruthManifestError("\n".join(problems))

    rederived = grade_ledger(context, projection, ledger)
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


def build_case_truth_manifest(plan: CasePlan) -> dict[str, Any]:
    """Build one versioned scorer envelope without reading any wall clock."""
    channels: dict[str, Any] = {}
    if plan.money_facts is not None:
        channels["money"] = _money_channel(plan.money_facts)
    if plan.medical_assertions is not None:
        channels["assertions"] = _assertions_channel(plan)
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
    caseload_id: str, results: Sequence[CaseResult | _CaseResultLike]
) -> dict[str, Any]:
    """Build a complete corpus index while omitting an empty money channel."""
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
        channels["money"] = {
            "channelVersion": MONEY_CHANNEL_VERSION,
            "caseCount": len(results),
            "moneyCaseCount": money_case_count,
            "cases": cases,
        }

    # The assertions rollup uses NEWLY ALLOCATED lists and case dictionaries —
    # the shipped money rollup aliases the top-level list, and extending that
    # aliasing here would let a later mutation of one channel move another
    # channel's bytes (L16).
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
        ledger = result.plan.medical_assertions
        if ledger is None:
            continue
        entry = {
            "caseId": result.case_id,
            "truthFile": f"{result.truth_path.parent.name}/{result.truth_path.name}",
            "contentionCount": len(ledger.contentions),
            "medicalOpinionCount": len(ledger.medical_opinions),
            "apportionmentAssertionCount": len(ledger.apportionment_assertions),
        }
        assertion_cases.append(entry)
        for quality, count in ledger.quality_counts().items():
            quality_counts[quality] += count
        totals["contentions"] += len(ledger.contentions)
        totals["medicalOpinions"] += len(ledger.medical_opinions)
        totals["apportionmentAssertions"] += len(ledger.apportionment_assertions)
        for opinion in ledger.medical_opinions:
            state_counts[opinion.apportionment_state] += 1
            if opinion.determination_kind is not None:
                determination_kind_counts[_camel(opinion.determination_kind)] += 1
    if assertion_cases:
        channels["assertions"] = {
            "channelVersion": ASSERTIONS_CHANNEL_VERSION,
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


def write_case_truth_manifest(plan: CasePlan, truth_dir: Path) -> Path:
    """Write one case truth artifact and return its exact path."""
    truth_dir.mkdir(parents=True, exist_ok=True)
    path = truth_dir / case_truth_name(plan.seed.case_id)
    _write_json(path, build_case_truth_manifest(plan))
    return path


def write_caseload_truth_manifest(
    caseload_id: str,
    results: Sequence[CaseResult | _CaseResultLike],
    truth_dir: Path,
) -> Path:
    """Write the scorer's caseload index beside the per-case truth artifacts."""
    truth_dir.mkdir(parents=True, exist_ok=True)
    path = truth_dir / CASELOAD_TRUTH_NAME
    _write_json(path, build_caseload_truth_manifest(caseload_id, results))
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
        _require_compatible_version(
            assertions_channel,
            key="channelVersion",
            path="channels.assertions",
            supported=ASSERTIONS_CHANNEL_VERSION,
            label="assertions channel",
        )
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
    "ASSERTIONS_CHANNEL_VERSION",
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
    "read_truth_manifest",
    "write_case_truth_manifest",
    "write_caseload_truth_manifest",
]
