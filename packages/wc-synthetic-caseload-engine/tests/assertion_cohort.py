"""The frozen AJC-61 measurement cohort — 6,000 ledgers, no rendering.

Composition is FROZEN by the Parts 1-5 contract and may not be tuned until a
draw happens to pass: seeds ``610000..615999``; 4,800 ordinary M1-sampled
histories; five explicit witness strata of 240 cases each (industrial, mixed,
post-DOI compensable consequence, post-DOI industrial psych, oncology +
firefighter + prior-claim/award + SIBTF-severe); and the six-cell lifecycle
schedule ``(rng_seed - 610000) % 6``, 1,000 cases per cell, exactly 40 per
witness stratum per cell.

The ``MEASURED_*`` constants below are pinned from a completed run of this
module (``.venv/bin/python tests/assertion_cohort.py``) — recorded output, not
guesses; the property suite asserts exact deterministic reproduction.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import copy
import datetime as dt
import random
import re
from collections import Counter
from dataclasses import dataclass, field
from fractions import Fraction
from functools import cache
from math import ceil
from typing import Any

from wc_caseload_engine import medical_assertions as assertion_module
from wc_caseload_engine.medical_assertions import (
    AssertionTrace,
    MedicalAssertionLedger,
    assertion_context,
    derive_medical_assertion_plan,
    project_medical_history,
    validate_medical_assertions,
)
from wc_caseload_engine.medical_history import derive_medical_history
from wc_caseload_engine.medical_story import (
    derive_medical_ur_plan,
    resolve_imr_application_content,
)
from wc_caseload_engine.seeds import parse_case_seed

ASSERTION_COHORT_N = 6000
COHORT_SEED_BASE = 610000
ORDINARY_COUNT = 4800
WITNESS_STRATUM_SIZE = 240
IMR_PROBE_MODULUS = 4
IMR_PROBE_REMAINDER = 1
IMR_PROBE_CASES = 1500

QUALITY_KEYS: tuple[str, ...] = ("supported", "thin", "unsupportable")
RESPONSE_EVENT_KINDS: tuple[str, ...] = ("supplemental_report", "deposition")

#: The M2 spot-digest positions — one per lifecycle cell plus each witness
#: stratum's first case and the last case. R64 reuses exactly these indices
#: for the later M3 plan digests.
DIGEST_INDICES: tuple[int, ...] = (0, 1, 2, 3, 4, 5, 4800, 5040, 5280, 5520, 5760, 5999)

#: The frozen six-cell lifecycle schedule (Part 5 B.9). ``post_recon`` is
#: intentionally excluded — it adds no unique M2 assertion decision family.
COHORT_CELLS: tuple[tuple[str, str, str, str], ...] = (
    ("intake", "accepted", "none", "pending"),
    ("active_treatment", "delayed", "none", "pending"),
    ("discovery", "denied", "none", "pending"),
    ("medical_legal", "accepted", "qme", "pending"),
    ("pre_trial", "delayed", "ame", "pending"),
    ("resolved", "denied", "none", "c_and_r"),
)

#: Three-sigma denominator floors: minimum_n(p) = ceil(p(1-p) / ((3/100)/3)**2).
MIN_TAGGED_FAMILY_CANDIDATES: dict[str, int] = {
    "condition": 1444,  # p = 7/40
    "prior_claim": 1275,  # p = 3/20
    "prior_award": 1600,  # p = 1/5
    "sibtf": 900,  # p = 1/10
    "firefighter": 1600,  # p = 1/5
}

TAGGED_FAMILY_RATES: dict[str, Fraction] = {
    "condition": Fraction(7, 40),
    "prior_claim": Fraction(3, 20),
    "prior_award": Fraction(1, 5),
    "sibtf": Fraction(1, 10),
    "firefighter": Fraction(1, 5),
}


def minimum_n(p: Fraction) -> int:
    """The ±0.03 band's three-sigma floor for a rate of *p*."""
    return ceil(p * (1 - p) / ((Fraction(3, 100) / 3) ** 2))


_WITNESS_PRIOR_CLAIMS: list[dict[str, Any]] = [
    {
        "body_parts": ["lumbar_spine"],
        "date_of_injury": "2015-01-05",
        "resolution_type": "stipulated_award",
        "award": {
            "body_parts": ["lumbar_spine"],
            "pd_percent": 12,
            "award_date": "2016-02-01",
        },
    },
    {
        "body_parts": ["shoulder"],
        "date_of_injury": "2018-06-10",
        "resolution_type": "findings_and_award",
        "award": {
            "body_parts": ["shoulder"],
            "pd_percent": 9,
            "award_date": "2019-03-15",
        },
    },
]

_ONCOLOGY_LABELS = (
    "invasive ductal carcinoma, right breast",
    "pulmonary nodule, left lower lobe",
    "papillary thyroid carcinoma",
    "renal cell carcinoma, left kidney",
    "colonic adenocarcinoma",
    "cutaneous melanoma, upper back",
    "non-Hodgkin lymphoma, axillary",
)


def _witness_conditions(stratum: int) -> list[dict[str, Any]]:
    if stratum == 0:  # industrial condition
        return [
            {
                "label": "industrial lumbar strain sequela",
                "origin": "industrial",
                "body_part": "lumbar_spine",
                "severity": "moderate",
                "symptomatic_before_doi": False,
            }
        ]
    if stratum == 1:  # mixed condition
        return [
            {
                "label": "mixed-etiology degenerative lumbar disease",
                "origin": "mixed",
                "body_part": "lumbar_spine",
                "severity": "moderate",
                "trajectory": "progressive",
                "symptomatic_before_doi": True,
            }
        ]
    if stratum == 2:  # post-DOI industrial compensable consequence
        return [
            {
                "label": "post-surgical adjacent segment syndrome",
                "origin": "industrial",
                "body_part": "lumbar_spine",
                "onset": "2024-06-15",
                "severity": "moderate",
            }
        ]
    if stratum == 3:  # post-DOI industrial psych condition
        return [
            {
                "label": "post-injury depressive disorder",
                "key": "depression_anxiety",
                "body_system": "psychiatric",
                "origin": "industrial",
                "onset": "2024-07-01",
                "severity": "moderate",
            }
        ]
    # stratum 4: oncology + firefighter hook + SIBTF-severe evidence
    conditions: list[dict[str, Any]] = [
        {
            "label": label,
            "body_system": "oncologic",
            "body_part": "breast",
            "wholly_unrelated": True,
            "severity": "severe",
        }
        for label in _ONCOLOGY_LABELS
    ]
    conditions.append(
        {
            "label": "severe degenerative lumbar disease",
            "origin": "nonindustrial",
            "body_part": "lumbar_spine",
            "severity": "severe",
            "trajectory": "progressive",
            "symptomatic_before_doi": True,
        }
    )
    return conditions


def cohort_seed_body(index: int) -> dict[str, Any]:
    """The frozen seed body for cohort position *index* (0-based)."""
    rng_seed = COHORT_SEED_BASE + index
    stage, claim_response, eval_type, resolution = COHORT_CELLS[(rng_seed - COHORT_SEED_BASE) % 6]
    lifecycle: dict[str, Any] = {
        "target_stage": stage,
        "claim_response": claim_response,
        "eval_type": eval_type,
        "resolution": {"type": resolution},
    }
    medical_history: dict[str, Any] = {}
    if index >= ORDINARY_COUNT:
        stratum = (index - ORDINARY_COUNT) // WITNESS_STRATUM_SIZE
        medical_history = {
            "conditions": _witness_conditions(stratum),
            "prior_claims": [dict(claim) for claim in _WITNESS_PRIOR_CLAIMS],
        }
        if stratum == 4:
            lifecycle["doctrine_hooks"] = ["firefighter_presumption"]
    return {
        "case_id": f"cohort-{index:04d}",
        "rng_seed": rng_seed,
        "injury": {
            "type": "specific",
            "date_of_injury": "2024-03-01",
            "body_parts": [{"part": "lumbar_spine"}, {"part": "shoulder"}],
        },
        "lifecycle": lifecycle,
        "scenario": {"medical_history": medical_history, "medical_assertions": {}},
    }


def medical_story_cohort_seed_body(index: int) -> dict[str, Any]:
    """R61's measurement-only overlay over the frozen M2 cohort body.

    The copy is load-bearing: neither :func:`cohort_seed_body` nor
    :func:`build_cohort` may ever observe the forced UR-denial probe.  Exactly
    one position in four receives an upheld denial with unauthored IMR state,
    giving 1,500 opportunities across the complete 6,000-case view.
    """

    body = copy.deepcopy(cohort_seed_body(index))
    if index % IMR_PROBE_MODULUS == IMR_PROBE_REMAINDER:
        body["lifecycle"]["ur_dispute"] = {
            "enabled": True,
            "decision": "upheld",
        }
    return body


@dataclass
class CohortResult:
    """Everything the frozen property oracle asserts on, from one build."""

    quality_counts: dict[str, Counter] = field(default_factory=dict)
    recipe_grade_counts: Counter = field(default_factory=Counter)
    contention_family_counts: Counter = field(default_factory=Counter)
    eligible_counts: Counter = field(default_factory=Counter)
    lifecycle_counts: Counter = field(default_factory=Counter)
    evidence_budget_counts: Counter = field(default_factory=Counter)
    distractor_counts: Counter = field(default_factory=Counter)
    psych_component_cases: int = 0
    psych_add_on_cases: int = 0
    suppression_hits: int = 0
    invalid_ledgers: int = 0
    families_seen: set = field(default_factory=set)
    cell_counts: Counter = field(default_factory=Counter)
    stratum_cell_counts: Counter = field(default_factory=Counter)
    ledger_digests: dict[int, str] = field(default_factory=dict)
    budget_quality: Counter = field(default_factory=Counter)
    contention_shapes: set = field(default_factory=set)
    stream_trace_digests: dict[int, str] = field(default_factory=dict)
    story_families_seen: set = field(default_factory=set)
    story_key_findings: list = field(default_factory=list)


def _quality_counter() -> Counter:
    """A complete A2 counter: zero-valued quality cells stay observable."""

    return Counter(dict.fromkeys(QUALITY_KEYS, 0))


@dataclass
class MedicalStoryCohortResult:
    """R61/R64's separate M3 measurement surface.

    Quality is intentionally stratified.  There is no aggregate all-opinion
    band field: Amendment A2 makes the two base populations primary and keeps
    response populations diagnostic-only.
    """

    story_eligible_counts: Counter = field(default_factory=Counter)
    story_draw_counts: Counter = field(default_factory=Counter)
    advocacy_counts: Counter = field(default_factory=Counter)
    contest_path_counts: Counter = field(default_factory=Counter)
    chain_length_counts: Counter = field(default_factory=Counter)
    disposition_counts: Counter = field(default_factory=Counter)
    revision_kind_counts: Counter = field(default_factory=Counter)
    percentage_register_counts: Counter = field(default_factory=Counter)
    date_offset_counts: dict[str, Counter] = field(
        default_factory=lambda: {"raw": Counter(), "fitted": Counter()}
    )
    imr_field_counts: Counter = field(default_factory=Counter)
    base_opinion_quality_counts: Counter = field(default_factory=_quality_counter)
    base_owner_apportionment_quality_counts: Counter = field(default_factory=_quality_counter)
    response_opinion_quality_counts: Counter = field(default_factory=_quality_counter)
    response_apportionment_quality_counts: Counter = field(default_factory=_quality_counter)
    response_quality_counts_by_event_kind: dict[str, Counter] = field(
        default_factory=lambda: {
            event_kind: _quality_counter() for event_kind in RESPONSE_EVENT_KINDS
        }
    )
    medical_story_plan_digests: dict[int, str] = field(default_factory=dict)
    invalid_ledgers: int = 0


def measure_m3_quality_strata(
    ledger: MedicalAssertionLedger,
) -> tuple[Counter, Counter, Counter, Counter, dict[str, Counter]]:
    """Measure A2's two primary base strata and response diagnostics.

    Ownership is resolved through the ledger, never inferred from assertion
    order or ID shape.  Unknown owners are invalid elsewhere and do not get
    silently assigned to either denominator here.
    """

    base_opinions = _quality_counter()
    base_assertions = _quality_counter()
    response_opinions = _quality_counter()
    response_assertions = _quality_counter()
    by_event_kind = {event_kind: _quality_counter() for event_kind in RESPONSE_EVENT_KINDS}
    owners = {opinion.id: opinion for opinion in ledger.medical_opinions}
    for opinion in ledger.medical_opinions:
        if opinion.event_kind == "base_report":
            base_opinions[opinion.quality] += 1
        else:
            response_opinions[opinion.quality] += 1
            by_event_kind[opinion.event_kind][opinion.quality] += 1
    for assertion in ledger.apportionment_assertions:
        owner = owners.get(assertion.opinion_id)
        if owner is None:
            raise AssertionError(
                "the M3 quality measurement cannot classify apportionment "
                f"assertion {assertion.id!r}: owner {assertion.opinion_id!r} "
                "is absent"
            )
        if owner.event_kind == "base_report":
            base_assertions[assertion.quality] += 1
        else:
            response_assertions[assertion.quality] += 1
            by_event_kind[owner.event_kind][assertion.quality] += 1
    return (
        base_opinions,
        base_assertions,
        response_opinions,
        response_assertions,
        by_event_kind,
    )


# The M2 digest oracle projects each item onto the exact AJC-61 field
# vocabulary (R62): "Because R6 and R26 add defaulted fields to existing
# models, the M2 digest oracle MUST use a literal AJC-61 field projection
# rather than a new full model_dump()." These are independent test-side
# literals — production's ASSERTIONS_V1_* tuples are declared separately and
# the coordinated oracle compares the two for exact equality. Every pinned
# digest below is therefore byte-identical to its pre-M3 recording.
M2_CONTENTION_ORACLE_FIELDS = (
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

M2_OPINION_ORACLE_FIELDS = (
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

M2_APPORTIONMENT_ORACLE_FIELDS = (
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

# Amendment A2-R4's independent test-side plan-digest projection.  These
# literals equal production's declarations but are not imported from them;
# ``quality`` is absent by construction, never dumped and removed afterward.
M3_PLAN_DIGEST_CONTENTION_FIELDS = (
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

M3_PLAN_DIGEST_MEDICAL_OPINION_FIELDS = (
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

M3_PLAN_DIGEST_APPORTIONMENT_ASSERTION_FIELDS = (
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


def _oracle_projection(item, fields: tuple[str, ...]) -> dict:
    dumped = item.model_dump(mode="json")
    return {name: dumped[name] for name in fields}


def _digest(ledger: MedicalAssertionLedger) -> str:
    import hashlib
    import json

    payload = json.dumps(
        {
            "contentions": [
                _oracle_projection(item, M2_CONTENTION_ORACLE_FIELDS) for item in ledger.contentions
            ],
            "medical_opinions": [
                _oracle_projection(item, M2_OPINION_ORACLE_FIELDS)
                for item in ledger.medical_opinions
            ],
            "apportionment_assertions": [
                _oracle_projection(item, M2_APPORTIONMENT_ORACLE_FIELDS)
                for item in ledger.apportionment_assertions
            ],
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _m3_projection(item: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    """Literal include-only serialization for the A2-R4 digest."""

    return item.model_dump(mode="json", include=set(fields))


def _m3_plan_digest(plan: Any, medical_ur_plan: Any) -> str:
    """R64's quality-free M3 semantic-plan change detector."""

    import hashlib
    import json

    ledger = plan.ledger
    assert ledger is not None
    payload = {
        "ledger": {
            "contentions": [
                _m3_projection(item, M3_PLAN_DIGEST_CONTENTION_FIELDS)
                for item in ledger.contentions
            ],
            "medical_opinions": [
                _m3_projection(item, M3_PLAN_DIGEST_MEDICAL_OPINION_FIELDS)
                for item in ledger.medical_opinions
            ],
            "apportionment_assertions": [
                _m3_projection(item, M3_PLAN_DIGEST_APPORTIONMENT_ASSERTION_FIELDS)
                for item in ledger.apportionment_assertions
            ],
        },
        "contention_documents": [
            binding.model_dump(mode="json") for binding in plan.contention_documents
        ],
        "medical_ur_plan": (
            None if medical_ur_plan is None else medical_ur_plan.model_dump(mode="json")
        ),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def _base_opinion_id(ledger: MedicalAssertionLedger, opinion_id: str | None) -> str | None:
    """Resolve one response chain to its base report without guessing."""

    seen: set[str] = set()
    current = ledger.opinion(opinion_id) if opinion_id is not None else None
    while current is not None and current.event_kind != "base_report":
        if current.id in seen:
            return None
        seen.add(current.id)
        current = ledger.opinion(current.responds_to_opinion_id or "")
    return None if current is None else current.id


def _record_chain_metrics(result: MedicalStoryCohortResult, plan: Any) -> None:
    """Aggregate retained sampled chain shapes from final assertion bindings."""

    ledger = plan.ledger
    assert ledger is not None
    groups: dict[tuple[Any, ...], set[str]] = {}
    for binding in plan.contention_documents:
        if binding.source != "sampled" or binding.document_kind == "advocacy":
            continue
        opinion_ref = binding.target_medical_opinion_id or binding.medical_opinion_id
        base_id = _base_opinion_id(ledger, opinion_ref)
        key = (
            binding.actor_party,
            base_id,
            tuple(binding.spoken_contention_ids),
        )
        groups.setdefault(key, set()).add(binding.document_kind)
        if binding.proposed_date is not None:
            target = ledger.opinion(binding.target_medical_opinion_id or "")
            if target is not None:
                delta = (binding.proposed_date - target.report_date).days
                result.date_offset_counts["fitted"][(binding.document_kind, delta)] += 1

    pattern_to_path = {
        frozenset({"objection"}): "objection_only",
        frozenset({"objection", "qme_deposition"}): "objection_deposition",
        frozenset(
            {"objection", "supplemental_request", "supplemental_report"}
        ): "objection_supplemental",
        frozenset(
            {
                "objection",
                "supplemental_request",
                "supplemental_report",
                "qme_deposition",
            }
        ): "objection_supplemental_deposition",
        frozenset({"supplemental_request", "supplemental_report"}): "supplemental_only",
        frozenset(
            {"supplemental_request", "supplemental_report", "qme_deposition"}
        ): "supplemental_deposition",
    }
    stage_symbols = {
        "objection": "O",
        "supplemental_request": "R",
        "supplemental_report": "S",
        "qme_deposition": "D",
    }
    stage_order = tuple(stage_symbols)
    for stages in groups.values():
        ordered = tuple(stage for stage in stage_order if stage in stages)
        result.chain_length_counts[len(ordered)] += 1
        result.chain_length_counts["".join(stage_symbols[stage] for stage in ordered)] += 1
        path = pattern_to_path.get(frozenset(stages))
        if path is not None:
            result.contest_path_counts[path] += 1


def _record_m3_plan_metrics(
    result: MedicalStoryCohortResult,
    plan: Any,
    trace: AssertionTrace,
) -> None:
    ledger = plan.ledger
    assert ledger is not None
    (
        base_opinions,
        base_assertions,
        response_opinions,
        response_assertions,
        response_by_kind,
    ) = measure_m3_quality_strata(ledger)
    result.base_opinion_quality_counts.update(base_opinions)
    result.base_owner_apportionment_quality_counts.update(base_assertions)
    result.response_opinion_quality_counts.update(response_opinions)
    result.response_apportionment_quality_counts.update(response_assertions)
    for event_kind in RESPONSE_EVENT_KINDS:
        result.response_quality_counts_by_event_kind[event_kind].update(
            response_by_kind[event_kind]
        )

    for opinion in ledger.medical_opinions:
        if opinion.event_kind != "base_report":
            result.revision_kind_counts[(opinion.event_kind, opinion.revision_kind)] += 1
        if opinion.author_role == "ptp" and opinion.event_kind == "base_report":
            result.disposition_counts[f"ptp:{opinion.aoe_coe_finding}"] += 1
        elif opinion.author_role in ("qme", "ame") and opinion.event_kind == "base_report":
            for contention in ledger.contentions:
                if contention.id in opinion.endorses_contention_ids:
                    disposition = "adopted"
                elif contention.id in opinion.concurs_with_contention_ids:
                    disposition = "concurred"
                elif contention.id in opinion.rejects_contention_ids:
                    disposition = "rejected"
                elif contention.id in opinion.defers_contention_ids:
                    disposition = "deferred"
                else:
                    disposition = "unaddressed"
                result.disposition_counts[f"qme_ame:{disposition}"] += 1

    for assertion in ledger.apportionment_assertions:
        value = assertion.nonindustrial_percent
        register = (
            "common" if value in assertion_module.COMMON_NONINDUSTRIAL_PERCENTAGES else "granular"
        )
        result.percentage_register_counts[register] += 1
        if assertion.revised_from_percent is not None:
            result.percentage_register_counts[f"revision:{register}"] += 1
        result.percentage_register_counts[(register, value)] += 1

    for binding in plan.contention_documents:
        if binding.document_kind == "advocacy":
            result.advocacy_counts["total"] += 1
            result.advocacy_counts[f"actor:{binding.actor_party}"] += 1
            result.advocacy_counts[f"source:{binding.source}"] += 1
        for theory in binding.defense_contest_theories:
            result.advocacy_counts[f"defense_theory:{theory}"] += 1
    for family, offset in trace.story_raw_date_offsets:
        result.date_offset_counts["raw"][(family, offset)] += 1
    _record_chain_metrics(result, plan)


class _CountingRandom(random.Random):
    """A byte-transparent draw counter.

    State is transplanted from the stream the production helper constructed,
    so every value drawn is bit-identical to the uninstrumented stream — the
    subclass only counts how many times the stream was consumed. Both
    ``random()`` and ``getrandbits()`` are counted because every public
    consuming method funnels through one of them.
    """

    def __init__(self) -> None:
        super().__init__()
        self.draws = 0

    def random(self) -> float:
        self.draws += 1
        return super().random()

    def getrandbits(self, k: int) -> int:
        self.draws += 1
        return super().getrandbits(k)


_SAMPLED_ID_SHAPE = re.compile(r"^(ctn|opn|app|cdoc)-\d{2}$")


def pre_id_key_problems(semantic_key: tuple) -> list[str]:
    """R45's pre-ID discipline over one production story key (R70's family
    recorder, attached at R77 step 4 with the first production key sites).

    A ``ctn/opn/app/cdoc``-shaped atom may appear only in an explicit key
    form — the atom immediately following an ``"explicit"`` marker. Any other
    occurrence means a sampled pre-label key was salted with an assigned ID,
    collection position, or final index.
    """
    problems: list[str] = []

    def walk(node, parent: tuple, position: int) -> None:
        if isinstance(node, tuple):
            for index, item in enumerate(node):
                walk(item, node, index)
            return
        if isinstance(node, str) and _SAMPLED_ID_SHAPE.match(node):
            preceded_by_explicit = position > 0 and parent[position - 1] == "explicit"
            if not preceded_by_explicit:
                problems.append(f"assigned-ID atom {node!r} in sampled key {semantic_key!r}")

    walk(semantic_key, (), 0)
    return problems


def _stream_trace_digest(trace: list[tuple[str, str, _CountingRandom]]) -> str:
    """SHA-256 over the ordered (family, full salt, draw count) construction
    trace of one case — the R70 instrument that sees what the ledger digest
    cannot: a stream constructed under the wrong family or namespace whose
    draws happen not to move the sampled payload."""
    import hashlib
    import json

    payload = json.dumps(
        [[family, salt, rng.draws] for family, salt, rng in trace],
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()


@cache
def build_cohort(sample: int | None = None) -> CohortResult:
    """Build the cohort (or its first *sample* cases) and aggregate the trace.

    Cached per process so every property test shares one build. The rng-family
    completeness record comes from wrapping the module's own ``_assertion_rng``
    for the duration — reading the streams actually constructed, not a list —
    and, since R77 step 3, every returned stream is a state-transplanted
    counting twin so the per-case construction/draw trace can be digested.

    Every M2 measurement below reads ``AssertionTrace.m2_baseline_ledger`` —
    the exact post-grade/pre-M3 ledger the plan entry point records (R61/R72)
    — never the (later remodeled) plan ledger, so the pinned M2 constants keep
    measuring the preserved baseline through every M3 step.
    ``_medical_story_rng`` is wrapped alongside: any medical-story family the
    M2 cohort derivation constructs lands in ``story_families_seen`` for the
    R70 registry gate.
    """
    result = CohortResult()
    for model in ("contentions", "medical_opinions", "apportionment_assertions"):
        result.quality_counts[model] = Counter()

    original_rng = assertion_module._assertion_rng
    original_story_rng = assertion_module._medical_story_rng
    case_streams: list[tuple[str, str, _CountingRandom]] = []

    def recording_rng(seed: Any, family: str, stable_key: str) -> Any:
        result.families_seen.add(family)
        constructed = original_rng(seed, family, stable_key)
        counting = _CountingRandom()
        counting.setstate(constructed.getstate())
        case_streams.append(
            (
                family,
                f"{assertion_module.ASSERTION_RNG_NAMESPACE}:{family}:{stable_key}",
                counting,
            )
        )
        return counting

    def recording_story_rng(seed: Any, family: str, semantic_key: Any) -> Any:
        result.story_families_seen.add(family)
        result.story_key_findings.extend(pre_id_key_problems(semantic_key))
        return original_story_rng(seed, family, semantic_key)

    assertion_module._assertion_rng = recording_rng
    assertion_module._medical_story_rng = recording_story_rng
    try:
        count = ASSERTION_COHORT_N if sample is None else sample
        for index in range(count):
            body = cohort_seed_body(index)
            seed = parse_case_seed(body)
            cell = (seed.rng_seed - COHORT_SEED_BASE) % 6
            result.cell_counts[cell] += 1
            if index >= ORDINARY_COUNT:
                stratum = (index - ORDINARY_COUNT) // WITNESS_STRATUM_SIZE
                result.stratum_cell_counts[(stratum, cell)] += 1
            history = derive_medical_history(seed)
            trace = AssertionTrace()
            case_streams.clear()
            plan = derive_medical_assertion_plan(seed, history, trace=trace)
            ledger = trace.m2_baseline_ledger
            assert ledger is not None
            assert plan.ledger is not None
            context = assertion_context(seed)
            projection = project_medical_history(history, context.current_body_parts)
            if validate_medical_assertions(context, projection, ledger):
                result.invalid_ledgers += 1
            for model in result.quality_counts:
                for item in getattr(ledger, model):
                    result.quality_counts[model][item.quality] += 1
            for _key, recipe, realized in trace.recipes:
                result.recipe_grade_counts[(recipe, realized)] += 1
            for family, drawn in trace.candidate_families.items():
                result.contention_family_counts[family] += drawn
            for family, eligible in trace.eligible_candidates.items():
                result.eligible_counts[family] += eligible
            for label in trace.lifecycle:
                result.lifecycle_counts[label] += 1
            for budget in trace.evidence_budgets:
                result.evidence_budget_counts[budget] += 1
            if trace.evidence_budgets and ledger.medical_opinions:
                result.budget_quality[
                    (trace.evidence_budgets[0], ledger.medical_opinions[0].quality)
                ] += 1
            for contention in ledger.contentions:
                result.contention_shapes.add(
                    (contention.claim_type, contention.party, contention.position)
                )
            result.distractor_counts["available"] += trace.distractor_available
            result.distractor_counts["included"] += trace.distractor_included
            if trace.candidate_families.get("psych_component"):
                result.psych_component_cases += 1
            if trace.candidate_families.get("psych_add_on"):
                result.psych_add_on_cases += 1
            result.suppression_hits += trace.suppression_hits
            if index in DIGEST_INDICES:
                result.ledger_digests[index] = _digest(ledger)
                result.stream_trace_digests[index] = _stream_trace_digest(case_streams)
    finally:
        assertion_module._assertion_rng = original_rng
        assertion_module._medical_story_rng = original_story_rng
    return result


@cache
def build_medical_story_cohort(
    sample: int | None = None,
) -> MedicalStoryCohortResult:
    """Build R61's separate 6,000-case M3 measurement view.

    This deliberately does not call :func:`build_cohort`: the M2 oracle keeps
    its original seed bodies and counters, while this view consumes the deep-
    copied IMR overlay and the completed M3 assertion plan.  Story streams are
    state-transplanted counting twins, so construction counts and draw counts
    are observed without changing a sampled bit.
    """

    result = MedicalStoryCohortResult()
    original_story_rng = assertion_module._medical_story_rng
    case_streams: list[tuple[str, _CountingRandom]] = []

    def recording_story_rng(seed: Any, family: str, semantic_key: Any) -> Any:
        constructed = original_story_rng(seed, family, semantic_key)
        counting = _CountingRandom()
        counting.setstate(constructed.getstate())
        case_streams.append((family, counting))
        return counting

    assertion_module._medical_story_rng = recording_story_rng
    try:
        count = ASSERTION_COHORT_N if sample is None else sample
        for index in range(count):
            seed = parse_case_seed(medical_story_cohort_seed_body(index))
            history = derive_medical_history(seed)
            trace = AssertionTrace()
            case_streams.clear()
            plan = derive_medical_assertion_plan(seed, history, trace=trace)
            ledger = plan.ledger
            assert ledger is not None
            context = assertion_context(seed)
            projection = project_medical_history(history, context.current_body_parts)
            if validate_medical_assertions(context, projection, ledger):
                result.invalid_ledgers += 1

            denial_date = seed.injury.onset_date + dt.timedelta(days=180)
            ur_plan = derive_medical_ur_plan(
                seed,
                target_denial_date=denial_date,
            )
            if ur_plan is not None:
                result.imr_field_counts["request:eligible"] += 1
                result.imr_field_counts[
                    f"request:{'requested' if ur_plan.imr_requested else 'not_requested'}"
                ] += 1
                if ur_plan.effective_imr_outcome is not None:
                    result.imr_field_counts[f"outcome:{ur_plan.effective_imr_outcome}"] += 1
                content = resolve_imr_application_content(
                    seed,
                    ur_plan,
                    target_denial_date=denial_date,
                    medical_history=history,
                    earlier_record_subtypes=(
                        "PRIMARY_TREATING_PHYSICIAN_PROGRESS_REPORT",
                        "QME_REPORT_ORTHOPEDIC",
                    ),
                    disputed_treatment="lumbar spine physical therapy",
                )
                if content is not None:
                    for field_name in (
                        "disputed_treatment",
                        "diagnosis_icd10",
                        "ur_determination_attached",
                        "supporting_record_subtypes",
                        "clinical_rebuttal",
                        "mtus_citations",
                    ):
                        result.imr_field_counts[f"field:{field_name}:eligible"] += 1
                        if getattr(content, field_name):
                            result.imr_field_counts[f"field:{field_name}:populated"] += 1
                    if content.clinical_rebuttal:
                        case_specific = "documented " in content.clinical_rebuttal
                        result.imr_field_counts[
                            "clinical_rebuttal:case_specific"
                            if case_specific
                            else "clinical_rebuttal:generic"
                        ] += 1

            for family, rng in case_streams:
                result.story_eligible_counts[family] += 1
                result.story_draw_counts[family] += rng.draws
            _record_m3_plan_metrics(result, plan, trace)
            if index in DIGEST_INDICES:
                result.medical_story_plan_digests[index] = _m3_plan_digest(plan, ur_plan)
    finally:
        assertion_module._medical_story_rng = original_story_rng
    return result


# ---------------------------------------------------------------------------
# Pinned measurement — recorded from a completed run, never guessed.
# Measurement command: .venv/bin/python tests/assertion_cohort.py
# Recorded 2026-08-11 against the frozen composition above.
# ---------------------------------------------------------------------------

MEASURED_RECIPE_GRADE_COUNTS: dict[tuple[str, str], int] = {
    ("supported", "supported"): 8613,
    ("supported", "thin"): 1370,
    ("supported", "unsupportable"): 878,
    ("thin", "thin"): 1165,
    ("thin", "unsupportable"): 110,
    ("unsupportable", "supported"): 3,
    ("unsupportable", "thin"): 98,
    ("unsupportable", "unsupportable"): 462,
}
"""The recipe->grade confusion matrix, pooled over contentions, opinions and
apportionment rows (opinions carry their own foundation recipe since fix
round 1). Off-diagonal mass is the proof quality is rederived rather than
copied: 1,370 supported-recipe builds graded thin, 3 unsupportable-recipe
builds graded supported, and so on. There is no ('thin', 'supported') cell —
a dropped rationale never grades supported."""

MEASURED_ASSERTION_QUALITY_COUNTS: dict[str, dict[str, int]] = {
    "contentions": {"supported": 3770, "thin": 1896, "unsupportable": 771},
    "medical_opinions": {"supported": 3849, "thin": 542, "unsupportable": 609},
    "apportionment_assertions": {"supported": 997, "thin": 195, "unsupportable": 70},
}

MEASURED_CONTENTION_FAMILY_COUNTS: dict[str, int] = {
    "condition": 2515,
    "firefighter": 333,
    "prior_award": 480,
    "prior_claim": 348,
    "psych_add_on": 571,
    "psych_component": 2754,
    "sibtf": 190,
}

MEASURED_LIFECYCLE_COUNTS: dict[str, int] = {
    "ame:final:determined:allocated:A": 361,
    "ame:final:determined:no_nonindustrial_share:A": 54,
    "ame:final:determined:no_nonindustrial_share:B": 195,
    "ame:final:determined:unable_to_approximate:A": 60,
    "ame:final:determined:unable_to_approximate:C": 249,
    "ame:final:omitted:-:omitted": 81,
    "ptp:final:determined:allocated:A": 302,
    "ptp:final:determined:no_nonindustrial_share:A": 61,
    "ptp:final:determined:no_nonindustrial_share:B": 172,
    "ptp:final:determined:unable_to_approximate:A": 53,
    "ptp:final:determined:unable_to_approximate:C": 293,
    "ptp:final:omitted:-:omitted": 119,
    "ptp:interim:deferred:-:-": 2000,
    "qme:final:determined:allocated:A": 236,
    "qme:final:determined:no_nonindustrial_share:A": 45,
    "qme:final:determined:no_nonindustrial_share:B": 170,
    "qme:final:determined:unable_to_approximate:A": 55,
    "qme:final:determined:unable_to_approximate:C": 207,
    "qme:final:omitted:-:omitted": 91,
    "qme:interim:deferred:-:-": 196,
}

MEASURED_EVIDENCE_BUDGET_COUNTS: dict[int, int] = {1: 1723, 2: 2053, 3: 1224}

MEASURED_DISTRACTOR_COUNTS: dict[str, int] = {"available": 1066, "included": 276}

MEASURED_ELIGIBLE_COUNTS: dict[str, int] = {
    "condition": 14056,
    "firefighter": 1680,
    "prior_award": 2400,
    "prior_claim": 2400,
    "sibtf": 1674,
}
"""Condition eligibility counts EVERY world-truth condition (fix round 1, H2):
the B.4 table keys candidacy on type alone, and visibility only conditions the
B.5 evidence read — so the denominator includes conditions the file never
shows."""

MEASURED_PSYCH_COMPONENT_CASES: int = 2754
MEASURED_PSYCH_ADD_ON_CASES: int = 571

MEASURED_LEDGER_DIGESTS: dict[int, str] = {
    0: "9aef89d1d0fa1960577934d3bcf759e57790a2939bfcf8b6f998e20a384033a4",
    1: "f941da1ed756daf22d69722dc9deb91fb6d06c12b2ef62483a0967ce18748cd6",
    2: "7cca22aa5a73a70bd857334ac189fd733d71bc3621a1d48013fb4796ac902c8b",
    3: "e2c883cb04f28372a9ed3201d28b03002667ea5f04236c858f83a0e5e3aaa11f",
    4: "ea63d1e28821028c5d1d69d31d39b457121d8a8e5d750f24f2ed6af11e505071",
    5: "fa027b6d3ad3c4efce41daf070e4485d457ef391edd449052f6a3066ab486a0e",
    4800: "87072051147e435c8eed12f521ce472bd1226eeef03bddfc97869fb656ab29a6",
    5040: "9aef89d1d0fa1960577934d3bcf759e57790a2939bfcf8b6f998e20a384033a4",
    5280: "80c42649922691ba8e3b04cf7f29ced015a934d9685850e27c6b61613ff087f7",
    5520: "1fc8f633a9195f60fe2e7158fb3c359416a30be876c9e65db6e1f640203ea0dd",
    5760: "20b945e58d4a281eab0b0aebb90a4e93e228783275cb6e13c8c5fe17df1e7cba",
    5999: "e5e151df3ffe3ea78b6b8bf9d06ac5b21f0f9a2a5722123a20e2741574f3a708",
}
"""Spot digests: one per cell plus each witness stratum's first case and the
last case. Indexes 0 and 5040 legitimately coincide — both are intake cases
whose every incidence draw missed, and two empty ledgers are the same bytes."""

MEASURED_M2_STREAM_TRACE_DIGESTS: dict[int, str] = {
    0: "94c4d2bcb9d8b8ae39aec60cce89605ce8e8415c36c72434c7b745755311e5e4",
    1: "a7b032e88e12f9cc4287b183cf8f2174cfe4e64c352ea27b17c56b5379b6bf15",
    2: "c29896526efe1578287c0775088f62cde416e4882da4173d26302273645955e6",
    3: "8d55bceec6fd63c41290f9ca5d4d38af691b109ec5a6ab4ed415fbc18937b563",
    4: "d7b7b7351d7d3d7dccb9ebc4ae1c9776f8053acd0459a893b7744e0ec7b5f14a",
    5: "b028d955f574d4686351dc6af38c29ff0bce045f756748a74a558388eb0e341f",
    4800: "5ac8fe79fac68c93678fb9bcec6b658976deb693df7ea12d062a9d6428afd715",
    5040: "5349e6c8855b7a5e627f20521b65be393426040fdd3249f0d4e41ebe25537aa2",
    5280: "9231e27ba8ab4e1b5edc463c3321cd6e15a08d73e744616e1303038c319e7ee9",
    5520: "75e515bd762f14d34079e1784fc810b1aa24d313150445ecccac666e8666efe8",
    5760: "9096d964f0882eb02e9eca0676f3e222b1e91e2946886ac59e01bd429d7206ef",
    5999: "f392a67c2ed1c9d68816e7ade8d65f7408ffc978b7d59f936110da3946d5ab70",
}
"""The R70 M2 stream-trace pins: per spot index, SHA-256 over the ordered
``(family, complete semantic salt, within-stream draw count)`` construction
trace of the M2 base derivation. Recorded at R77 step 3, where byte-identity
with the ``eedad1093`` baseline is separately proven by the UNCHANGED
``MEASURED_LEDGER_DIGESTS`` (any draw inserted into an M2 stream moves the
sampled payload and reddens those frozen digests) — so the trace pinned here
IS the M2 baseline trace, frozen thereafter. What this instrument sees that
the ledger digests cannot: a fresh stream constructed under an M2 family or
namespace by later M3 code, whose private draws leave the M2 payload intact
(the m20-10 failure shape)."""


# ---------------------------------------------------------------------------
# AJC-62 R64 / Amendment A2 pinned M3 measurement.
# First complete in-band run: 2026-08-14, 6,000 fixed cases, zero invalid.
# The literal 0.75-0.85 base-stratum bands are the PRIMARY oracle; these
# first-run values are deterministic change detectors (Form A by construction).
# Response diagnostics are deliberately not pinned (A2-R3).
# ---------------------------------------------------------------------------

MEASURED_STORY_ELIGIBLE_COUNTS: dict[Any, Any] = {
    "advocacy-bundle-size": 193,
    "advocacy-incidence": 2332,
    "advocacy-lead": 1311,
    "applicant-contest-incidence": 895,
    "completion-incidence": 277,
    "contest-path": 841,
    "defense-contest-incidence": 233,
    "defense-theory-count": 154,
    "defense-theory-selection": 154,
    "deposition-lag": 144,
    "imr-field-count": 266,
    "imr-field-occupancy": 3433,
    "imr-outcome": 753,
    "imr-rebuttal-substance": 189,
    "imr-request": 1500,
    "objection-lag": 476,
    "ptp-aoe-coe-finding": 3000,
    "qme-ame-indeterminate-disposition": 578,
    "qme-ame-responsive-adoption": 617,
    "revision-kind": 593,
    "revision-percentage-register": 84,
    "revision-percentage-value": 84,
    "supplemental-report-lag": 449,
    "supplemental-request-lag": 449,
}

MEASURED_STORY_DRAW_COUNTS: dict[Any, Any] = {
    "advocacy-bundle-size": 193,
    "advocacy-incidence": 2332,
    "advocacy-lead": 2666,
    "applicant-contest-incidence": 895,
    "completion-incidence": 277,
    "contest-path": 841,
    "defense-contest-incidence": 233,
    "defense-theory-count": 154,
    "defense-theory-selection": 205,
    "deposition-lag": 202,
    "imr-field-count": 266,
    "imr-field-occupancy": 3433,
    "imr-outcome": 753,
    "imr-rebuttal-substance": 189,
    "imr-request": 1500,
    "objection-lag": 723,
    "ptp-aoe-coe-finding": 3158,
    "qme-ame-indeterminate-disposition": 578,
    "qme-ame-responsive-adoption": 617,
    "revision-kind": 593,
    "revision-percentage-register": 84,
    "revision-percentage-value": 134,
    "supplemental-report-lag": 472,
    "supplemental-request-lag": 482,
}

MEASURED_ADVOCACY_COUNTS: dict[Any, Any] = {
    "actor:applicant": 860,
    "actor:defense": 451,
    "defense_theory:insufficient_investigation": 91,
    "defense_theory:lack_of_substantial_medical_evidence": 75,
    "defense_theory:post_termination": 93,
    "source:sampled": 1311,
    "total": 1311,
}

MEASURED_CONTEST_PATH_COUNTS: dict[Any, Any] = {"objection_deposition": 73, "objection_only": 238}

MEASURED_CHAIN_LENGTH_COUNTS: dict[Any, Any] = {
    1: 928,
    2: 253,
    3: 28,
    "O": 238,
    "OD": 73,
    "OR": 137,
    "ORD": 28,
    "R": 241,
    "RD": 43,
    "S": 449,
}

MEASURED_DISPOSITION_COUNTS: dict[Any, Any] = {
    "ptp:deferred": 57,
    "ptp:industrial": 2842,
    "ptp:nonindustrial": 101,
    "qme_ame:adopted": 102,
    "qme_ame:concurred": 735,
    "qme_ame:deferred": 244,
    "qme_ame:rejected": 199,
    "qme_ame:unaddressed": 169,
}

MEASURED_REVISION_KIND_COUNTS: dict[Any, Any] = {
    ("deposition", "revised_apportionment"): 7,
    ("deposition", "revised_causation"): 23,
    ("deposition", "revised_causation_and_apportionment"): 4,
    ("deposition", "unchanged_additional_reasoning"): 110,
    ("supplemental_report", "new_records_no_change"): 32,
    ("supplemental_report", "revised_apportionment"): 38,
    ("supplemental_report", "revised_causation"): 193,
    ("supplemental_report", "revised_causation_and_apportionment"): 35,
    ("supplemental_report", "unchanged_additional_reasoning"): 151,
}

MEASURED_PERCENTAGE_REGISTER_COUNTS: dict[Any, Any] = {
    "common": 1398,
    "granular": 235,
    "revision:common": 72,
    "revision:granular": 12,
    ("common", 5): 61,
    ("common", 10): 55,
    ("common", 15): 47,
    ("common", 20): 74,
    ("common", 25): 54,
    ("common", 30): 61,
    ("common", 33): 75,
    ("common", 35): 78,
    ("common", 40): 56,
    ("common", 45): 79,
    ("common", 50): 85,
    ("common", 55): 67,
    ("common", 60): 65,
    ("common", 65): 68,
    ("common", 67): 66,
    ("common", 70): 61,
    ("common", 75): 72,
    ("common", 80): 81,
    ("common", 85): 68,
    ("common", 90): 69,
    ("common", 95): 56,
    ("granular", 1): 3,
    ("granular", 2): 1,
    ("granular", 3): 4,
    ("granular", 6): 3,
    ("granular", 7): 3,
    ("granular", 8): 4,
    ("granular", 9): 3,
    ("granular", 11): 1,
    ("granular", 12): 3,
    ("granular", 13): 1,
    ("granular", 14): 5,
    ("granular", 16): 2,
    ("granular", 17): 4,
    ("granular", 18): 7,
    ("granular", 21): 5,
    ("granular", 22): 5,
    ("granular", 23): 3,
    ("granular", 24): 2,
    ("granular", 26): 2,
    ("granular", 29): 3,
    ("granular", 32): 7,
    ("granular", 34): 1,
    ("granular", 36): 2,
    ("granular", 37): 4,
    ("granular", 38): 7,
    ("granular", 39): 1,
    ("granular", 41): 6,
    ("granular", 42): 6,
    ("granular", 43): 6,
    ("granular", 44): 4,
    ("granular", 47): 3,
    ("granular", 48): 5,
    ("granular", 49): 1,
    ("granular", 51): 2,
    ("granular", 52): 2,
    ("granular", 53): 6,
    ("granular", 54): 3,
    ("granular", 56): 1,
    ("granular", 57): 1,
    ("granular", 58): 2,
    ("granular", 59): 4,
    ("granular", 61): 8,
    ("granular", 62): 5,
    ("granular", 63): 1,
    ("granular", 64): 4,
    ("granular", 66): 1,
    ("granular", 68): 1,
    ("granular", 69): 3,
    ("granular", 71): 4,
    ("granular", 72): 6,
    ("granular", 73): 2,
    ("granular", 74): 3,
    ("granular", 76): 1,
    ("granular", 77): 5,
    ("granular", 79): 3,
    ("granular", 81): 3,
    ("granular", 82): 1,
    ("granular", 83): 1,
    ("granular", 84): 3,
    ("granular", 86): 7,
    ("granular", 87): 3,
    ("granular", 88): 2,
    ("granular", 89): 7,
    ("granular", 91): 5,
    ("granular", 92): 3,
    ("granular", 93): 5,
    ("granular", 96): 2,
    ("granular", 97): 2,
    ("granular", 98): 3,
    ("granular", 99): 3,
}

MEASURED_DATE_OFFSET_COUNTS: dict[Any, Any] = {
    "fitted": {
        ("objection", 10): 28,
        ("objection", 11): 21,
        ("objection", 12): 16,
        ("objection", 13): 19,
        ("objection", 14): 31,
        ("objection", 15): 22,
        ("objection", 16): 22,
        ("objection", 17): 10,
        ("objection", 18): 23,
        ("objection", 19): 25,
        ("objection", 20): 20,
        ("objection", 21): 18,
        ("objection", 22): 24,
        ("objection", 23): 21,
        ("objection", 24): 27,
        ("objection", 25): 34,
        ("objection", 26): 19,
        ("objection", 27): 22,
        ("objection", 28): 19,
        ("objection", 29): 35,
        ("objection", 30): 20,
        ("qme_deposition", 30): 2,
        ("qme_deposition", 31): 2,
        ("qme_deposition", 34): 2,
        ("qme_deposition", 36): 1,
        ("qme_deposition", 37): 4,
        ("qme_deposition", 38): 2,
        ("qme_deposition", 39): 2,
        ("qme_deposition", 40): 2,
        ("qme_deposition", 41): 4,
        ("qme_deposition", 42): 1,
        ("qme_deposition", 43): 1,
        ("qme_deposition", 44): 2,
        ("qme_deposition", 46): 2,
        ("qme_deposition", 47): 2,
        ("qme_deposition", 49): 2,
        ("qme_deposition", 51): 1,
        ("qme_deposition", 52): 2,
        ("qme_deposition", 53): 1,
        ("qme_deposition", 55): 4,
        ("qme_deposition", 56): 3,
        ("qme_deposition", 57): 1,
        ("qme_deposition", 59): 3,
        ("qme_deposition", 60): 1,
        ("qme_deposition", 61): 1,
        ("qme_deposition", 62): 3,
        ("qme_deposition", 63): 1,
        ("qme_deposition", 66): 3,
        ("qme_deposition", 67): 1,
        ("qme_deposition", 68): 3,
        ("qme_deposition", 69): 3,
        ("qme_deposition", 70): 1,
        ("qme_deposition", 71): 2,
        ("qme_deposition", 72): 3,
        ("qme_deposition", 73): 2,
        ("qme_deposition", 74): 2,
        ("qme_deposition", 77): 2,
        ("qme_deposition", 80): 1,
        ("qme_deposition", 81): 3,
        ("qme_deposition", 82): 1,
        ("qme_deposition", 84): 1,
        ("qme_deposition", 85): 1,
        ("qme_deposition", 86): 3,
        ("qme_deposition", 87): 3,
        ("qme_deposition", 88): 4,
        ("qme_deposition", 89): 1,
        ("qme_deposition", 90): 3,
        ("qme_deposition", 92): 3,
        ("qme_deposition", 93): 2,
        ("qme_deposition", 94): 1,
        ("qme_deposition", 95): 1,
        ("qme_deposition", 96): 2,
        ("qme_deposition", 97): 1,
        ("qme_deposition", 98): 1,
        ("qme_deposition", 99): 1,
        ("qme_deposition", 100): 1,
        ("qme_deposition", 101): 3,
        ("qme_deposition", 103): 1,
        ("qme_deposition", 104): 1,
        ("qme_deposition", 105): 2,
        ("qme_deposition", 106): 3,
        ("qme_deposition", 108): 4,
        ("qme_deposition", 109): 1,
        ("qme_deposition", 111): 1,
        ("qme_deposition", 112): 4,
        ("qme_deposition", 113): 2,
        ("qme_deposition", 114): 3,
        ("qme_deposition", 115): 1,
        ("qme_deposition", 116): 3,
        ("qme_deposition", 117): 1,
        ("qme_deposition", 118): 1,
        ("qme_deposition", 119): 2,
        ("qme_deposition", 120): 3,
        ("supplemental_report", 38): 2,
        ("supplemental_report", 39): 1,
        ("supplemental_report", 40): 5,
        ("supplemental_report", 41): 2,
        ("supplemental_report", 42): 4,
        ("supplemental_report", 43): 2,
        ("supplemental_report", 44): 4,
        ("supplemental_report", 45): 5,
        ("supplemental_report", 46): 3,
        ("supplemental_report", 47): 3,
        ("supplemental_report", 48): 5,
        ("supplemental_report", 49): 6,
        ("supplemental_report", 50): 3,
        ("supplemental_report", 51): 3,
        ("supplemental_report", 52): 5,
        ("supplemental_report", 53): 3,
        ("supplemental_report", 54): 4,
        ("supplemental_report", 55): 1,
        ("supplemental_report", 56): 1,
        ("supplemental_report", 57): 3,
        ("supplemental_report", 58): 3,
        ("supplemental_report", 59): 3,
        ("supplemental_report", 60): 3,
        ("supplemental_report", 61): 7,
        ("supplemental_report", 62): 7,
        ("supplemental_report", 63): 8,
        ("supplemental_report", 64): 2,
        ("supplemental_report", 65): 3,
        ("supplemental_report", 66): 7,
        ("supplemental_report", 67): 6,
        ("supplemental_report", 68): 9,
        ("supplemental_report", 69): 8,
        ("supplemental_report", 70): 11,
        ("supplemental_report", 71): 6,
        ("supplemental_report", 72): 11,
        ("supplemental_report", 73): 7,
        ("supplemental_report", 74): 4,
        ("supplemental_report", 75): 8,
        ("supplemental_report", 76): 9,
        ("supplemental_report", 77): 8,
        ("supplemental_report", 78): 4,
        ("supplemental_report", 79): 3,
        ("supplemental_report", 80): 10,
        ("supplemental_report", 81): 7,
        ("supplemental_report", 82): 12,
        ("supplemental_report", 83): 8,
        ("supplemental_report", 84): 10,
        ("supplemental_report", 85): 9,
        ("supplemental_report", 86): 9,
        ("supplemental_report", 87): 8,
        ("supplemental_report", 88): 7,
        ("supplemental_report", 89): 9,
        ("supplemental_report", 90): 9,
        ("supplemental_report", 91): 8,
        ("supplemental_report", 92): 16,
        ("supplemental_report", 93): 7,
        ("supplemental_report", 94): 3,
        ("supplemental_report", 95): 6,
        ("supplemental_report", 96): 8,
        ("supplemental_report", 97): 10,
        ("supplemental_report", 98): 7,
        ("supplemental_report", 99): 4,
        ("supplemental_report", 100): 4,
        ("supplemental_report", 101): 4,
        ("supplemental_report", 102): 4,
        ("supplemental_report", 103): 6,
        ("supplemental_report", 104): 7,
        ("supplemental_report", 105): 6,
        ("supplemental_report", 106): 5,
        ("supplemental_report", 107): 8,
        ("supplemental_report", 108): 4,
        ("supplemental_report", 109): 2,
        ("supplemental_report", 110): 3,
        ("supplemental_report", 111): 3,
        ("supplemental_report", 112): 2,
        ("supplemental_report", 113): 3,
        ("supplemental_report", 114): 3,
        ("supplemental_report", 115): 1,
        ("supplemental_report", 116): 3,
        ("supplemental_report", 117): 1,
        ("supplemental_report", 119): 1,
        ("supplemental_report", 120): 1,
        ("supplemental_report", 121): 2,
        ("supplemental_report", 122): 1,
        ("supplemental_report", 124): 2,
        ("supplemental_report", 125): 2,
        ("supplemental_report", 131): 1,
        ("supplemental_report", 135): 1,
        ("supplemental_request", 7): 17,
        ("supplemental_request", 8): 18,
        ("supplemental_request", 9): 24,
        ("supplemental_request", 10): 18,
        ("supplemental_request", 11): 23,
        ("supplemental_request", 12): 24,
        ("supplemental_request", 13): 19,
        ("supplemental_request", 14): 22,
        ("supplemental_request", 15): 14,
        ("supplemental_request", 16): 29,
        ("supplemental_request", 17): 21,
        ("supplemental_request", 18): 15,
        ("supplemental_request", 19): 19,
        ("supplemental_request", 20): 17,
        ("supplemental_request", 21): 11,
        ("supplemental_request", 22): 6,
        ("supplemental_request", 23): 4,
        ("supplemental_request", 24): 4,
        ("supplemental_request", 25): 6,
        ("supplemental_request", 26): 7,
        ("supplemental_request", 27): 7,
        ("supplemental_request", 28): 6,
        ("supplemental_request", 29): 3,
        ("supplemental_request", 30): 4,
        ("supplemental_request", 31): 7,
        ("supplemental_request", 32): 8,
        ("supplemental_request", 33): 11,
        ("supplemental_request", 34): 12,
        ("supplemental_request", 35): 11,
        ("supplemental_request", 36): 5,
        ("supplemental_request", 37): 7,
        ("supplemental_request", 38): 9,
        ("supplemental_request", 39): 8,
        ("supplemental_request", 40): 6,
        ("supplemental_request", 41): 5,
        ("supplemental_request", 42): 1,
        ("supplemental_request", 43): 5,
        ("supplemental_request", 44): 5,
        ("supplemental_request", 45): 2,
        ("supplemental_request", 46): 2,
        ("supplemental_request", 47): 2,
        ("supplemental_request", 48): 1,
        ("supplemental_request", 49): 3,
        ("supplemental_request", 50): 1,
    },
    "raw": {
        ("advocacy-lead", 14): 32,
        ("advocacy-lead", 15): 36,
        ("advocacy-lead", 16): 33,
        ("advocacy-lead", 17): 45,
        ("advocacy-lead", 18): 30,
        ("advocacy-lead", 19): 36,
        ("advocacy-lead", 20): 40,
        ("advocacy-lead", 21): 39,
        ("advocacy-lead", 22): 50,
        ("advocacy-lead", 23): 45,
        ("advocacy-lead", 24): 41,
        ("advocacy-lead", 25): 35,
        ("advocacy-lead", 26): 37,
        ("advocacy-lead", 27): 43,
        ("advocacy-lead", 28): 54,
        ("advocacy-lead", 29): 46,
        ("advocacy-lead", 30): 46,
        ("advocacy-lead", 31): 33,
        ("advocacy-lead", 32): 42,
        ("advocacy-lead", 33): 53,
        ("advocacy-lead", 34): 37,
        ("advocacy-lead", 35): 45,
        ("advocacy-lead", 36): 43,
        ("advocacy-lead", 37): 31,
        ("advocacy-lead", 38): 55,
        ("advocacy-lead", 39): 47,
        ("advocacy-lead", 40): 38,
        ("advocacy-lead", 41): 39,
        ("advocacy-lead", 42): 43,
        ("advocacy-lead", 43): 52,
        ("advocacy-lead", 44): 31,
        ("advocacy-lead", 45): 34,
        ("deposition-lag", 30): 2,
        ("deposition-lag", 31): 2,
        ("deposition-lag", 34): 2,
        ("deposition-lag", 36): 1,
        ("deposition-lag", 37): 4,
        ("deposition-lag", 38): 2,
        ("deposition-lag", 39): 2,
        ("deposition-lag", 40): 2,
        ("deposition-lag", 41): 4,
        ("deposition-lag", 42): 1,
        ("deposition-lag", 43): 1,
        ("deposition-lag", 44): 2,
        ("deposition-lag", 46): 2,
        ("deposition-lag", 47): 2,
        ("deposition-lag", 49): 2,
        ("deposition-lag", 51): 1,
        ("deposition-lag", 52): 2,
        ("deposition-lag", 53): 1,
        ("deposition-lag", 55): 4,
        ("deposition-lag", 56): 3,
        ("deposition-lag", 57): 1,
        ("deposition-lag", 59): 3,
        ("deposition-lag", 60): 1,
        ("deposition-lag", 61): 1,
        ("deposition-lag", 62): 3,
        ("deposition-lag", 63): 1,
        ("deposition-lag", 66): 3,
        ("deposition-lag", 67): 1,
        ("deposition-lag", 68): 3,
        ("deposition-lag", 69): 3,
        ("deposition-lag", 70): 1,
        ("deposition-lag", 71): 2,
        ("deposition-lag", 72): 3,
        ("deposition-lag", 73): 2,
        ("deposition-lag", 74): 2,
        ("deposition-lag", 77): 2,
        ("deposition-lag", 80): 1,
        ("deposition-lag", 81): 3,
        ("deposition-lag", 82): 1,
        ("deposition-lag", 84): 1,
        ("deposition-lag", 85): 1,
        ("deposition-lag", 86): 3,
        ("deposition-lag", 87): 3,
        ("deposition-lag", 88): 4,
        ("deposition-lag", 89): 1,
        ("deposition-lag", 90): 3,
        ("deposition-lag", 92): 3,
        ("deposition-lag", 93): 2,
        ("deposition-lag", 94): 1,
        ("deposition-lag", 95): 1,
        ("deposition-lag", 96): 2,
        ("deposition-lag", 97): 1,
        ("deposition-lag", 98): 1,
        ("deposition-lag", 99): 1,
        ("deposition-lag", 100): 1,
        ("deposition-lag", 101): 3,
        ("deposition-lag", 103): 1,
        ("deposition-lag", 104): 1,
        ("deposition-lag", 105): 2,
        ("deposition-lag", 106): 3,
        ("deposition-lag", 108): 4,
        ("deposition-lag", 109): 1,
        ("deposition-lag", 111): 1,
        ("deposition-lag", 112): 4,
        ("deposition-lag", 113): 2,
        ("deposition-lag", 114): 3,
        ("deposition-lag", 115): 1,
        ("deposition-lag", 116): 3,
        ("deposition-lag", 117): 1,
        ("deposition-lag", 118): 1,
        ("deposition-lag", 119): 2,
        ("deposition-lag", 120): 3,
        ("objection-lag", 10): 28,
        ("objection-lag", 11): 21,
        ("objection-lag", 12): 16,
        ("objection-lag", 13): 19,
        ("objection-lag", 14): 31,
        ("objection-lag", 15): 22,
        ("objection-lag", 16): 22,
        ("objection-lag", 17): 10,
        ("objection-lag", 18): 23,
        ("objection-lag", 19): 25,
        ("objection-lag", 20): 20,
        ("objection-lag", 21): 18,
        ("objection-lag", 22): 24,
        ("objection-lag", 23): 21,
        ("objection-lag", 24): 27,
        ("objection-lag", 25): 34,
        ("objection-lag", 26): 19,
        ("objection-lag", 27): 22,
        ("objection-lag", 28): 19,
        ("objection-lag", 29): 35,
        ("objection-lag", 30): 20,
        ("supplemental-report-lag", 30): 11,
        ("supplemental-report-lag", 31): 12,
        ("supplemental-report-lag", 32): 5,
        ("supplemental-report-lag", 33): 11,
        ("supplemental-report-lag", 34): 7,
        ("supplemental-report-lag", 35): 9,
        ("supplemental-report-lag", 36): 5,
        ("supplemental-report-lag", 37): 9,
        ("supplemental-report-lag", 38): 3,
        ("supplemental-report-lag", 39): 4,
        ("supplemental-report-lag", 40): 3,
        ("supplemental-report-lag", 41): 5,
        ("supplemental-report-lag", 42): 5,
        ("supplemental-report-lag", 43): 10,
        ("supplemental-report-lag", 44): 6,
        ("supplemental-report-lag", 45): 8,
        ("supplemental-report-lag", 46): 10,
        ("supplemental-report-lag", 47): 6,
        ("supplemental-report-lag", 48): 6,
        ("supplemental-report-lag", 49): 5,
        ("supplemental-report-lag", 50): 6,
        ("supplemental-report-lag", 51): 6,
        ("supplemental-report-lag", 52): 8,
        ("supplemental-report-lag", 53): 5,
        ("supplemental-report-lag", 54): 7,
        ("supplemental-report-lag", 55): 13,
        ("supplemental-report-lag", 56): 13,
        ("supplemental-report-lag", 57): 8,
        ("supplemental-report-lag", 58): 7,
        ("supplemental-report-lag", 59): 9,
        ("supplemental-report-lag", 60): 8,
        ("supplemental-report-lag", 61): 13,
        ("supplemental-report-lag", 62): 7,
        ("supplemental-report-lag", 63): 5,
        ("supplemental-report-lag", 64): 9,
        ("supplemental-report-lag", 65): 4,
        ("supplemental-report-lag", 66): 9,
        ("supplemental-report-lag", 67): 15,
        ("supplemental-report-lag", 68): 7,
        ("supplemental-report-lag", 69): 9,
        ("supplemental-report-lag", 70): 8,
        ("supplemental-report-lag", 71): 8,
        ("supplemental-report-lag", 72): 8,
        ("supplemental-report-lag", 73): 8,
        ("supplemental-report-lag", 74): 9,
        ("supplemental-report-lag", 75): 3,
        ("supplemental-report-lag", 76): 5,
        ("supplemental-report-lag", 77): 2,
        ("supplemental-report-lag", 78): 7,
        ("supplemental-report-lag", 79): 8,
        ("supplemental-report-lag", 80): 6,
        ("supplemental-report-lag", 81): 6,
        ("supplemental-report-lag", 82): 4,
        ("supplemental-report-lag", 83): 7,
        ("supplemental-report-lag", 84): 2,
        ("supplemental-report-lag", 85): 10,
        ("supplemental-report-lag", 86): 5,
        ("supplemental-report-lag", 87): 8,
        ("supplemental-report-lag", 88): 12,
        ("supplemental-report-lag", 89): 10,
        ("supplemental-report-lag", 90): 5,
        ("supplemental-request-lag", 7): 30,
        ("supplemental-request-lag", 8): 31,
        ("supplemental-request-lag", 9): 35,
        ("supplemental-request-lag", 10): 30,
        ("supplemental-request-lag", 11): 35,
        ("supplemental-request-lag", 12): 35,
        ("supplemental-request-lag", 13): 34,
        ("supplemental-request-lag", 14): 31,
        ("supplemental-request-lag", 15): 23,
        ("supplemental-request-lag", 16): 38,
        ("supplemental-request-lag", 17): 31,
        ("supplemental-request-lag", 18): 23,
        ("supplemental-request-lag", 19): 25,
        ("supplemental-request-lag", 20): 24,
        ("supplemental-request-lag", 21): 24,
    },
}

MEASURED_IMR_FIELD_COUNTS: dict[Any, Any] = {
    "clinical_rebuttal:case_specific": 54,
    "clinical_rebuttal:generic": 135,
    "field:clinical_rebuttal:eligible": 753,
    "field:clinical_rebuttal:populated": 189,
    "field:diagnosis_icd10:eligible": 753,
    "field:diagnosis_icd10:populated": 250,
    "field:disputed_treatment:eligible": 753,
    "field:disputed_treatment:populated": 725,
    "field:mtus_citations:eligible": 753,
    "field:supporting_record_subtypes:eligible": 753,
    "field:supporting_record_subtypes:populated": 266,
    "field:ur_determination_attached:eligible": 753,
    "field:ur_determination_attached:populated": 518,
    "outcome:overturned": 379,
    "outcome:upheld": 374,
    "request:eligible": 1500,
    "request:not_requested": 747,
    "request:requested": 753,
}

MEASURED_M3_BASE_OPINION_QUALITY_COUNTS: dict[Any, Any] = {
    "supported": 4013,
    "thin": 391,
    "unsupportable": 596,
}

MEASURED_M3_BASE_OWNER_APPORTIONMENT_QUALITY_COUNTS: dict[Any, Any] = {
    "supported": 997,
    "thin": 195,
    "unsupportable": 70,
}

MEASURED_MEDICAL_STORY_PLAN_DIGESTS: dict[Any, Any] = {
    0: "e1b23fb8bf8837b76a57df579741bc62246ce9a8cfd6cafa6fe6602ad38905d6",
    1: "3e3d85b1ee789de95f04c8cb0afecf96e5d5dba7b6334231c9c452ea49cec5cc",
    2: "1effb6034c38ca541cb2bb51f2683a153504c118d60e18d0230b17b95188cef6",
    3: "21c718de28b8fef0e5d882e3780f1d337c2525c13f6975bbfd5f32812e997887",
    4: "8e74f9d3f97f7862746cf7c597b1aea76adc6c91f494b4a49ccdcd8bde06e192",
    5: "b6dded716efd126d5e05f8eb27ecb757301de3ed70c9cf1011df728219884202",
    4800: "b27b28c91d38f7594a2aff1763b185df888411e1ba2fd0bfe56ceac08d40dccb",
    5040: "e1b23fb8bf8837b76a57df579741bc62246ce9a8cfd6cafa6fe6602ad38905d6",
    5280: "0d28eaa7f01167453798f6bcecc543806f9629343d8ff9c7f1911f38e38b9419",
    5520: "a48b9d03325d34e54dde69c2e326c2a9dc73aa1ced7363372d89fde256b72869",
    5760: "158c37c4649ac713436fb8e8fac31c8b3a45cc8d826b086e81bbb21adb989128",
    5999: "2a7683a48e7f85147e5db242f0fcbfe0fd412d02b61b5ad21847e946e005f79d",
}


def _print_measurement() -> None:
    import structlog

    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(50))
    result = build_cohort()
    print("MEASURED_RECIPE_GRADE_COUNTS =", dict(sorted(result.recipe_grade_counts.items())))
    print(
        "MEASURED_ASSERTION_QUALITY_COUNTS =",
        {model: dict(sorted(counts.items())) for model, counts in result.quality_counts.items()},
    )
    print(
        "MEASURED_CONTENTION_FAMILY_COUNTS =",
        dict(sorted(result.contention_family_counts.items())),
    )
    print("MEASURED_LIFECYCLE_COUNTS =", dict(sorted(result.lifecycle_counts.items())))
    print(
        "MEASURED_EVIDENCE_BUDGET_COUNTS =",
        dict(sorted(result.evidence_budget_counts.items())),
    )
    print("MEASURED_DISTRACTOR_COUNTS =", dict(sorted(result.distractor_counts.items())))
    print("MEASURED_ELIGIBLE_COUNTS =", dict(sorted(result.eligible_counts.items())))
    print("MEASURED_PSYCH_COMPONENT_CASES =", result.psych_component_cases)
    print("MEASURED_PSYCH_ADD_ON_CASES =", result.psych_add_on_cases)
    print("# invalid ledgers:", result.invalid_ledgers)
    print("# suppression hits:", result.suppression_hits)
    print("# families seen:", sorted(result.families_seen))
    print("# story families seen:", sorted(result.story_families_seen))
    print("# ledger digests:", result.ledger_digests)
    print("MEASURED_M2_STREAM_TRACE_DIGESTS =", result.stream_trace_digests)
    story = build_medical_story_cohort()
    print("MEASURED_STORY_ELIGIBLE_COUNTS =", dict(sorted(story.story_eligible_counts.items())))
    print("MEASURED_STORY_DRAW_COUNTS =", dict(sorted(story.story_draw_counts.items())))
    print("MEASURED_ADVOCACY_COUNTS =", dict(sorted(story.advocacy_counts.items())))
    print("MEASURED_CONTEST_PATH_COUNTS =", dict(sorted(story.contest_path_counts.items())))
    print(
        "MEASURED_CHAIN_LENGTH_COUNTS =",
        dict(sorted(story.chain_length_counts.items(), key=lambda item: str(item[0]))),
    )
    print("MEASURED_DISPOSITION_COUNTS =", dict(sorted(story.disposition_counts.items())))
    print("MEASURED_REVISION_KIND_COUNTS =", dict(sorted(story.revision_kind_counts.items())))
    print(
        "MEASURED_PERCENTAGE_REGISTER_COUNTS =",
        dict(sorted(story.percentage_register_counts.items(), key=lambda item: str(item[0]))),
    )
    print(
        "MEASURED_DATE_OFFSET_COUNTS =",
        {
            kind: dict(sorted(counts.items(), key=lambda item: str(item[0])))
            for kind, counts in story.date_offset_counts.items()
        },
    )
    print("MEASURED_IMR_FIELD_COUNTS =", dict(sorted(story.imr_field_counts.items())))
    print(
        "MEASURED_M3_BASE_OPINION_QUALITY_COUNTS =",
        dict(story.base_opinion_quality_counts),
    )
    print(
        "MEASURED_M3_BASE_OWNER_APPORTIONMENT_QUALITY_COUNTS =",
        dict(story.base_owner_apportionment_quality_counts),
    )
    print(
        "# response_opinion_quality_counts =",
        dict(story.response_opinion_quality_counts),
    )
    print(
        "# response_apportionment_quality_counts =",
        dict(story.response_apportionment_quality_counts),
    )
    print(
        "# response_quality_counts_by_event_kind =",
        {
            event_kind: dict(counts)
            for event_kind, counts in story.response_quality_counts_by_event_kind.items()
        },
    )
    print(
        "MEASURED_MEDICAL_STORY_PLAN_DIGESTS =",
        story.medical_story_plan_digests,
    )
    print("# medical story invalid ledgers:", story.invalid_ledgers)


if __name__ == "__main__":
    _print_measurement()
