"""
ClaimState — mutable flags controlling DAG branching.

All flags start False; scenarios set them before the DAG walk begins.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field


@dataclass
class ClaimState:
    """Mutable state passed through the lifecycle DAG walk."""

    # ── Scenario flags ──────────────────────────────────────────────────────
    litigated: bool = False
    attorney_represented: bool = False
    ct: bool = False  # cumulative trauma
    denied_scenario: bool = False
    death_claim: bool = False
    ptd_claim: bool = False
    psych_overlay: bool = False
    multi_employer: bool = False
    split_carrier: bool = False
    high_liens: bool = False
    sjdb_dispute: bool = False
    expedited: bool = False
    investigation_active: bool = False

    # ── Runtime tracking ────────────────────────────────────────────────────
    stages_visited: list[str] = field(default_factory=list)
    seed: int = 42
    rng: random.Random = field(init=False)

    def __post_init__(self) -> None:
        self.rng = random.Random(self.seed)

    def visit(self, stage: str) -> None:
        """Record a stage as visited."""
        if stage not in self.stages_visited:
            self.stages_visited.append(stage)

    def has_visited(self, stage: str) -> bool:
        """Check if a stage has been visited."""
        return stage in self.stages_visited

    @classmethod
    def from_scenario(cls, slug: str, seed: int, **flags: bool) -> "ClaimState":  # noqa: ARG003
        """Create a ClaimState with flags from keyword arguments."""
        # mypy: unpack bool kwargs as ClaimState fields explicitly
        return cls(
            seed=seed,
            litigated=flags.get("litigated", False),
            attorney_represented=flags.get("attorney_represented", False),
            ct=flags.get("ct", False),
            denied_scenario=flags.get("denied_scenario", False),
            death_claim=flags.get("death_claim", False),
            ptd_claim=flags.get("ptd_claim", False),
            psych_overlay=flags.get("psych_overlay", False),
            multi_employer=flags.get("multi_employer", False),
            split_carrier=flags.get("split_carrier", False),
            high_liens=flags.get("high_liens", False),
            sjdb_dispute=flags.get("sjdb_dispute", False),
            expedited=flags.get("expedited", False),
            investigation_active=flags.get("investigation_active", False),
        )
