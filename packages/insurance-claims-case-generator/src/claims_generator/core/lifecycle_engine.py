"""
Lifecycle engine — walks the DAG to produce an ordered list of claim stages.

Entry point: walk_lifecycle(state) → list[str]  (ordered stage IDs)

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

from claims_generator.core.claim_state import ClaimState
from claims_generator.core.dag_nodes import ALL_STAGES
from claims_generator.core.dag_transitions import (
    TERMINAL_STAGES,
    get_transitions_from,
)

# Safety guard — prevent infinite loops
MAX_STAGES = 50


def _choose_next_stage(current: str, state: ClaimState) -> str | None:
    """
    Choose the next stage using weighted random selection.

    Returns None if this is a terminal stage.
    """
    if current in TERMINAL_STAGES:
        return None

    transitions = get_transitions_from(current)
    if not transitions:
        return None

    # Compute effective weights
    weights = [t.effective_weight(state) for t in transitions]
    total = sum(weights)
    if total <= 0:
        # All weights zeroed out — take first available
        return transitions[0].to_stage

    # Weighted random selection
    r = state.rng.random() * total
    cumulative = 0.0
    for transition, weight in zip(transitions, weights, strict=False):
        cumulative += weight
        if r <= cumulative:
            return transition.to_stage

    return transitions[-1].to_stage


def walk_lifecycle(state: ClaimState, start_stage: str = "DWC1_FILED") -> list[str]:
    """
    Walk the lifecycle DAG from start_stage.

    Returns an ordered list of stage IDs representing this claim's path.
    Always starts with DWC1_FILED; always ends with CLOSURE.
    """
    path: list[str] = []
    current: str | None = start_stage
    visited: set[str] = set()
    iterations = 0

    while current is not None and iterations < MAX_STAGES:
        # Guard against cycles (should not occur in well-formed DAG)
        if current in visited:
            break
        visited.add(current)
        path.append(current)
        state.visit(current)

        current = _choose_next_stage(current, state)
        iterations += 1

    # Ensure CLOSURE is always the final stage
    if not path or path[-1] != "CLOSURE":
        if "CLOSURE" in ALL_STAGES:
            path.append("CLOSURE")
            state.visit("CLOSURE")

    return path
