"""The realized format distribution matches the seeded one (ISC-27).

``documents.format_mix`` is a promise about proportions, and the previous
evidence for it was a control-resolver unit test — which proves the weights are
*read*, not that they are *honoured*. Between reading and honouring sits
:func:`~wc_caseload_engine.renderer.choose_format`, a cumulative-weight walk
over a seeded RNG, and a walk like that fails quietly: an off-by-one in the
ordering or a stale renormalization skews the mix without raising anything.

**Why chi-square and not tolerance bands.** A fixed band ("pdf within five
points of 60%") has to be set per category, and the loose band a rare category
needs — docx at 5% of 120 documents is six files — makes the band on the common
category meaningless. Chi-square asks the one question actually being asked, in
one number, with the sample size built in: *are these counts consistent with
these weights, or is the deviation more than sampling explains?*

The statistic is computed directly rather than pulled from SciPy, which is not
a dependency and is not worth becoming one for six lines of arithmetic. The
critical value is read from a small table at alpha = 0.001 - deliberately slack,
because this test guards against a *broken* sampler, not a slightly unlucky
one, and a determinstic suite that fails once a year on a fair draw is worse
than no test.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

from collections import Counter
from typing import Any

import pytest

from conftest import requires_substrate
from wc_caseload_engine.planner import build_case_plan
from wc_caseload_engine.renderer import choose_format
from wc_caseload_engine.seeds import parse_case_seed

pytestmark = requires_substrate

SEEDED_MIX = {"pdf": 0.5, "scanned_pdf": 0.25, "eml": 0.15, "docx": 0.10}
"""A deliberately uneven mix — a uniform one would pass a broken sampler."""

CHI_SQUARE_CRITICAL = {1: 10.83, 2: 13.82, 3: 16.27, 4: 18.47, 5: 20.52}
"""Upper-tail critical values at alpha = 0.001, keyed by degrees of freedom."""

DOCUMENT_COUNT = 120
"""Documents in the probe case. Above 100 so every category's expectation
clears the conventional chi-square floor of five (docx: 0.10 x 120 = 12)."""


def _chi_square(observed: dict[str, int], weights: dict[str, float], total: int) -> float:
    """Pearson's chi-square of *observed* against *weights* over *total* draws."""
    return sum(
        (observed.get(name, 0) - total * weight) ** 2 / (total * weight)
        for name, weight in weights.items()
    )


@pytest.fixture(scope="module")
def realized_formats() -> Counter[str]:
    """Formats assigned across a single large case.

    Planning is enough — format assignment happens in the planner, and skipping
    the render keeps a distribution test from costing two minutes of ReportLab.
    """
    seed = parse_case_seed(
        {
            "case_id": "format-mix-probe",
            "rng_seed": 606060,
            "injury": {
                "type": "specific",
                "date_of_injury": "2022-04-04",
                "body_parts": [{"part": "lumbar_spine", "icd10": "M54.5"}],
            },
            "lifecycle": {
                "target_stage": "post_recon",
                "claim_response": "denied",
                "resolution": {"type": "findings_award"},
                "reconsideration": {
                    "enabled": True,
                    "outcome": "granted_remand",
                    "post_recon": "further_litigation",
                },
                "liens": {"count": 3, "resolution": "lien_resolution_agreement"},
            },
            "documents": {"global_cap": DOCUMENT_COUNT, "format_mix": SEEDED_MIX},
        }
    )
    plan = build_case_plan(seed)
    return Counter(document.doc_format for document in plan.documents)


def test_the_probe_case_is_large_enough_to_measure(realized_formats: Counter[str]) -> None:
    """Guards the test: a short case makes any distribution look plausible."""
    total = sum(realized_formats.values())
    assert total >= 100, f"only {total} documents — too few for a distribution claim"
    for name, weight in SEEDED_MIX.items():
        assert total * weight >= 5, f"expected count for {name} is below the chi-square floor"


def test_every_seeded_format_actually_appears(realized_formats: Counter[str]) -> None:
    assert set(realized_formats) == set(SEEDED_MIX), (
        f"realized {sorted(realized_formats)} against seeded {sorted(SEEDED_MIX)}"
    )


def test_realized_format_mix_is_consistent_with_the_seeded_weights(
    realized_formats: Counter[str],
) -> None:
    total = sum(realized_formats.values())
    statistic = _chi_square(dict(realized_formats), SEEDED_MIX, total)
    degrees = len(SEEDED_MIX) - 1
    critical = CHI_SQUARE_CRITICAL[degrees]
    shares = {name: round(count / total, 3) for name, count in sorted(realized_formats.items())}
    assert statistic < critical, (
        f"chi-square {statistic:.2f} exceeds {critical} at {degrees} df — "
        f"realized {shares} against seeded {SEEDED_MIX}"
    )


def test_the_chi_square_probe_rejects_a_skewed_distribution() -> None:
    """Positive control. A statistic that never rejects is not a test."""
    total = DOCUMENT_COUNT
    skewed = {"pdf": total, "scanned_pdf": 0, "eml": 0, "docx": 0}
    statistic = _chi_square(skewed, SEEDED_MIX, total)
    assert statistic > CHI_SQUARE_CRITICAL[len(SEEDED_MIX) - 1]

    fair = {name: round(total * weight) for name, weight in SEEDED_MIX.items()}
    assert _chi_square(fair, SEEDED_MIX, total) < 1.0


def test_format_assignment_is_deterministic_for_a_seed() -> None:
    """The mix is a property of the seed, not of when it ran."""
    seed = parse_case_seed(
        {
            "case_id": "format-determinism",
            "rng_seed": 4321,
            "injury": {
                "type": "specific",
                "date_of_injury": "2022-04-04",
                "body_parts": [{"part": "knee", "icd10": "M23.51"}],
            },
            "documents": {"format_mix": SEEDED_MIX},
        }
    )
    first = [choose_format(seed, index) for index in range(DOCUMENT_COUNT)]
    second = [choose_format(seed, index) for index in range(DOCUMENT_COUNT)]
    assert first == second
    assert len(set(first)) == len(SEEDED_MIX), "a deterministic mix must still be a mix"


def test_a_single_format_mix_produces_only_that_format() -> None:
    """Degenerate weights are the clearest possible statement of intent."""
    seed = parse_case_seed(
        {
            "case_id": "format-single",
            "rng_seed": 99,
            "injury": {
                "type": "specific",
                "date_of_injury": "2022-04-04",
                "body_parts": [{"part": "knee", "icd10": "M23.51"}],
            },
            "documents": {"format_mix": {"pdf": 1.0}},
            "output": {"formats": ["pdf"]},
        }
    )
    assert {choose_format(seed, index) for index in range(60)} == {"pdf"}


def test_demo_caseload_format_counts_track_its_seeded_mix(
    demo_manifests: dict[str, dict[str, Any]],
) -> None:
    """The same claim, made about the caseload actually shipped."""
    observed: Counter[str] = Counter()
    for manifest in demo_manifests.values():
        observed.update(entry["format"] for entry in manifest["documents"])
    total = sum(observed.values())
    demo_mix = {"pdf": 0.6, "scanned_pdf": 0.25, "eml": 0.1, "docx": 0.05}
    statistic = _chi_square(dict(observed), demo_mix, total)
    shares = {name: round(count / total, 3) for name, count in sorted(observed.items())}
    assert statistic < CHI_SQUARE_CRITICAL[len(demo_mix) - 1], (
        f"demo chi-square {statistic:.2f}: realized {shares} against seeded {demo_mix}"
    )
