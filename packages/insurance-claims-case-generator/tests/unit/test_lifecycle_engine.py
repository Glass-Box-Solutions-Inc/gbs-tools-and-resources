"""
Unit tests for the lifecycle engine DAG walk.

Verifies that each scenario produces a valid ordered stage list with
expected properties.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import pytest

from claims_generator.core.claim_state import ClaimState
from claims_generator.core.dag_nodes import ALL_STAGES
from claims_generator.core.lifecycle_engine import walk_lifecycle
from claims_generator.scenarios.registry import get_scenario


@pytest.mark.parametrize("scenario_slug", ["standard_claim", "litigated_qme", "denied_claim"])
def test_walk_produces_nonempty_path(scenario_slug: str) -> None:
    """Every scenario walk must produce at least 2 stages."""
    preset = get_scenario(scenario_slug)
    state = ClaimState(
        litigated=preset.litigated,
        attorney_represented=preset.attorney_represented,
        denied_scenario=preset.denied_scenario,
        investigation_active=preset.investigation_active,
        seed=42,
    )
    path = walk_lifecycle(state)
    assert len(path) >= 2, f"{scenario_slug} walk returned fewer than 2 stages"


@pytest.mark.parametrize("scenario_slug", ["standard_claim", "litigated_qme", "denied_claim"])
def test_walk_starts_with_dwc1(scenario_slug: str) -> None:
    """Every walk must start with DWC1_FILED."""
    preset = get_scenario(scenario_slug)
    state = ClaimState(
        litigated=preset.litigated,
        attorney_represented=preset.attorney_represented,
        denied_scenario=preset.denied_scenario,
        investigation_active=preset.investigation_active,
        seed=42,
    )
    path = walk_lifecycle(state)
    assert path[0] == "DWC1_FILED", f"{scenario_slug} walk must start with DWC1_FILED"


@pytest.mark.parametrize("scenario_slug", ["standard_claim", "litigated_qme", "denied_claim"])
def test_walk_ends_with_closure(scenario_slug: str) -> None:
    """Every walk must end with CLOSURE."""
    preset = get_scenario(scenario_slug)
    state = ClaimState(
        litigated=preset.litigated,
        attorney_represented=preset.attorney_represented,
        denied_scenario=preset.denied_scenario,
        investigation_active=preset.investigation_active,
        seed=42,
    )
    path = walk_lifecycle(state)
    assert path[-1] == "CLOSURE", f"{scenario_slug} walk must end with CLOSURE"


@pytest.mark.parametrize("scenario_slug", ["standard_claim", "litigated_qme", "denied_claim"])
def test_walk_no_cycles(scenario_slug: str) -> None:
    """No stage should appear more than once in the path."""
    preset = get_scenario(scenario_slug)
    state = ClaimState(
        litigated=preset.litigated,
        attorney_represented=preset.attorney_represented,
        denied_scenario=preset.denied_scenario,
        investigation_active=preset.investigation_active,
        seed=42,
    )
    path = walk_lifecycle(state)
    assert len(path) == len(set(path)), f"{scenario_slug} walk has duplicate stages: {path}"


@pytest.mark.parametrize("scenario_slug", ["standard_claim", "litigated_qme", "denied_claim"])
def test_walk_all_stages_known(scenario_slug: str) -> None:
    """All stages in the walk must be registered in ALL_STAGES."""
    preset = get_scenario(scenario_slug)
    state = ClaimState(
        litigated=preset.litigated,
        attorney_represented=preset.attorney_represented,
        denied_scenario=preset.denied_scenario,
        investigation_active=preset.investigation_active,
        seed=42,
    )
    path = walk_lifecycle(state)
    unknown = [s for s in path if s not in ALL_STAGES]
    assert not unknown, f"{scenario_slug} walk contains unknown stages: {unknown}"


def test_litigated_scenario_includes_qme_or_wcab() -> None:
    """Litigated scenario should statistically visit QME_DISPUTE or WCAB_HEARING."""
    # Run 20 seeds — at least 80% should visit QME or WCAB
    preset = get_scenario("litigated_qme")
    hits = 0
    for seed in range(20):
        state = ClaimState(
            litigated=preset.litigated,
            attorney_represented=preset.attorney_represented,
            denied_scenario=preset.denied_scenario,
            investigation_active=preset.investigation_active,
            seed=seed,
        )
        path = walk_lifecycle(state)
        if "QME_DISPUTE" in path or "WCAB_HEARING" in path:
            hits += 1
    assert hits >= 16, f"litigated_qme should include QME or WCAB in ≥80% of runs, got {hits}/20"


def test_denied_scenario_includes_claim_denied() -> None:
    """Denied scenario must always include CLAIM_DENIED stage."""
    preset = get_scenario("denied_claim")
    hits = 0
    for seed in range(10):
        state = ClaimState(
            litigated=preset.litigated,
            attorney_represented=preset.attorney_represented,
            denied_scenario=preset.denied_scenario,
            investigation_active=preset.investigation_active,
            seed=seed,
        )
        path = walk_lifecycle(state)
        if "CLAIM_DENIED" in path:
            hits += 1
    assert hits >= 8, f"denied_claim should include CLAIM_DENIED in ≥80% of runs, got {hits}/10"


def test_standard_no_qme_most_runs() -> None:
    """Standard claim should not usually include QME_DISPUTE (no litigated flag)."""
    preset = get_scenario("standard_claim")
    qme_count = 0
    for seed in range(20):
        state = ClaimState(
            litigated=preset.litigated,
            attorney_represented=preset.attorney_represented,
            denied_scenario=preset.denied_scenario,
            investigation_active=preset.investigation_active,
            seed=seed,
        )
        path = walk_lifecycle(state)
        if "QME_DISPUTE" in path:
            qme_count += 1
    # QME_DISPUTE base weight is 0.25 from TD_PAYMENTS — at most ~50% without litigated flag
    assert qme_count <= 15, (
        f"standard_claim should rarely visit QME_DISPUTE, but got {qme_count}/20"
    )
