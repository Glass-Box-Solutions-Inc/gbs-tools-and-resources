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
    derive_medical_assertions,
    project_medical_history,
    validate_medical_assertions,
)
from wc_caseload_engine.medical_history import derive_medical_history
from wc_caseload_engine.seeds import parse_case_seed

ASSERTION_COHORT_N = 6000
COHORT_SEED_BASE = 610000
ORDINARY_COUNT = 4800
WITNESS_STRATUM_SIZE = 240

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
    "condition": 1444,     # p = 7/40
    "prior_claim": 1275,   # p = 3/20
    "prior_award": 1600,   # p = 1/5
    "sibtf": 900,          # p = 1/10
    "firefighter": 1600,   # p = 1/5
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
    stage, claim_response, eval_type, resolution = COHORT_CELLS[
        (rng_seed - COHORT_SEED_BASE) % 6
    ]
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


def _digest(ledger: MedicalAssertionLedger) -> str:
    import hashlib
    import json

    payload = json.dumps(ledger.model_dump(mode="json"), sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


@cache
def build_cohort(sample: int | None = None) -> CohortResult:
    """Build the cohort (or its first *sample* cases) and aggregate the trace.

    Cached per process so every property test shares one build. The rng-family
    completeness record comes from wrapping the module's own ``_assertion_rng``
    for the duration — reading the streams actually constructed, not a list.
    """
    result = CohortResult()
    for model in ("contentions", "medical_opinions", "apportionment_assertions"):
        result.quality_counts[model] = Counter()

    original_rng = assertion_module._assertion_rng

    def recording_rng(seed: Any, family: str, stable_key: str) -> Any:
        result.families_seen.add(family)
        return original_rng(seed, family, stable_key)

    assertion_module._assertion_rng = recording_rng
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
            ledger = derive_medical_assertions(seed, history, trace=trace)
            assert ledger is not None
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
            if index in (0, 1, 2, 3, 4, 5, 4800, 5040, 5280, 5520, 5760, 5999):
                result.ledger_digests[index] = _digest(ledger)
    finally:
        assertion_module._assertion_rng = original_rng
    return result


# ---------------------------------------------------------------------------
# Pinned measurement — recorded from a completed run, never guessed.
# Measurement command: .venv/bin/python tests/assertion_cohort.py
# Recorded 2026-08-11 against the frozen composition above.
# ---------------------------------------------------------------------------

MEASURED_RECIPE_GRADE_COUNTS: dict[tuple[str, str], int] = {
    ("supported", "supported"): 4631,
    ("supported", "thin"): 336,
    ("supported", "unsupportable"): 126,
    ("thin", "thin"): 823,
    ("thin", "unsupportable"): 60,
    ("unsupportable", "supported"): 29,
    ("unsupportable", "thin"): 38,
    ("unsupportable", "unsupportable"): 317,
}
"""The recipe->grade confusion matrix. Off-diagonal mass is the proof quality
is rederived rather than copied: 336 supported-recipe builds graded thin, 29
unsupportable-recipe builds graded supported, and so on. There is no
('thin', 'supported') cell — a dropped rationale never grades supported."""

MEASURED_ASSERTION_QUALITY_COUNTS: dict[str, dict[str, int]] = {
    "contentions": {"supported": 3642, "thin": 1023, "unsupportable": 433},
    "medical_opinions": {"supported": 4143, "thin": 327, "unsupportable": 530},
    "apportionment_assertions": {"supported": 1018, "thin": 174, "unsupportable": 70},
}

MEASURED_CONTENTION_FAMILY_COUNTS: dict[str, int] = {
    "condition": 1176,
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

MEASURED_DISTRACTOR_COUNTS: dict[str, int] = {"available": 1062, "included": 275}

MEASURED_ELIGIBLE_COUNTS: dict[str, int] = {
    "condition": 6673,
    "firefighter": 1680,
    "prior_award": 2400,
    "prior_claim": 2400,
    "sibtf": 1674,
}

MEASURED_PSYCH_COMPONENT_CASES: int = 2754
MEASURED_PSYCH_ADD_ON_CASES: int = 571

MEASURED_LEDGER_DIGESTS: dict[int, str] = {
    0: "9aef89d1d0fa1960577934d3bcf759e57790a2939bfcf8b6f998e20a384033a4",
    1: "6133b2c2cd8243bd93877ea39a7e65ae14ac80a1f0266404f2a28f0255a95da6",
    2: "7cca22aa5a73a70bd857334ac189fd733d71bc3621a1d48013fb4796ac902c8b",
    3: "e2c883cb04f28372a9ed3201d28b03002667ea5f04236c858f83a0e5e3aaa11f",
    4: "ea63d1e28821028c5d1d69d31d39b457121d8a8e5d750f24f2ed6af11e505071",
    5: "395409c2308c3b9221fbc4bdae08b70ea149195658c434ff61ae315a911bea75",
    4800: "87072051147e435c8eed12f521ce472bd1226eeef03bddfc97869fb656ab29a6",
    5040: "9aef89d1d0fa1960577934d3bcf759e57790a2939bfcf8b6f998e20a384033a4",
    5280: "80c42649922691ba8e3b04cf7f29ced015a934d9685850e27c6b61613ff087f7",
    5520: "bd76d7573b109b8655dd5abdea76f0c02a42fdeba32438efa42f451a838b5899",
    5760: "3075e9b091d5cb9933532f39366c2d67650b9bf912e10cbac23358e1cb025940",
    5999: "66714452795d9c0e56d138c5bb8294ff35d30f4b034da209d740e1f91f5e7c40",
}
"""Spot digests: one per cell plus each witness stratum's first case and the
last case. Indexes 0 and 5040 legitimately coincide — both are intake cases
whose every incidence draw missed, and two empty ledgers are the same bytes."""


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
    print("# ledger digests:", result.ledger_digests)


if __name__ == "__main__":
    _print_measurement()
