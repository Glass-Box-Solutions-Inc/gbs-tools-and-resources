"""
DAG transitions — StageTransition and WeightModifier.

Weighted probabilities for branching decisions in the lifecycle DAG.
Modifiers adjust base weights based on ClaimState flags.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from claims_generator.core.claim_state import ClaimState


@dataclass
class WeightModifier:
    """Adjusts transition weight based on a ClaimState flag."""

    flag_name: str  # e.g. "litigated"
    flag_value: bool  # True = flag is set
    delta: float  # added to base_weight when condition matches


@dataclass
class StageTransition:
    """A weighted transition between two lifecycle stages."""

    from_stage: str
    to_stage: str
    base_weight: float
    modifiers: list[WeightModifier] = field(default_factory=list)

    def effective_weight(self, state: "ClaimState") -> float:
        """Compute effective weight after applying modifiers."""
        w = self.base_weight
        for mod in self.modifiers:
            if getattr(state, mod.flag_name, False) == mod.flag_value:
                w += mod.delta
        return max(0.0, w)  # weights never go negative


# ── Transition table ───────────────────────────────────────────────────────────
# After DWC1_FILED: always goes to INITIAL_CONTACT
# After INITIAL_CONTACT: branches to CLAIM_ACCEPTED / CLAIM_DENIED
# After CLAIM_ACCEPTED: always goes to TREATMENT_BEGINS (then TD_PAYMENTS)
# After TREATMENT_BEGINS: optionally UR_RFA_CYCLE, then QME_DISPUTE path or MMI
# After CLAIM_DENIED: goes to WCAB_HEARING (if attorney) or CLOSURE

TRANSITIONS: list[StageTransition] = [
    # ── DWC1 → Initial Contact ────────────────────────────────────────────
    StageTransition(from_stage="DWC1_FILED", to_stage="INITIAL_CONTACT", base_weight=1.0),

    # ── Initial Contact → Accept / Deny ───────────────────────────────────
    StageTransition(
        from_stage="INITIAL_CONTACT",
        to_stage="CLAIM_ACCEPTED",
        base_weight=0.55,
        modifiers=[
            WeightModifier("denied_scenario", False, +0.10),
            WeightModifier("denied_scenario", True, -0.40),
        ],
    ),
    StageTransition(
        from_stage="INITIAL_CONTACT",
        to_stage="CLAIM_DENIED",
        base_weight=0.20,
        modifiers=[
            WeightModifier("denied_scenario", True, +0.30),
            WeightModifier("investigation_active", True, +0.10),
        ],
    ),
    # Delayed decision (90-day) goes to CLAIM_ACCEPTED eventually
    StageTransition(
        from_stage="INITIAL_CONTACT",
        to_stage="CLAIM_ACCEPTED",
        base_weight=0.25,
        modifiers=[
            WeightModifier("ct", True, -0.15),
            # Delayed acceptance less likely when denied_scenario is set
            WeightModifier("denied_scenario", True, -0.25),
        ],
    ),

    # ── Accepted → Treatment ──────────────────────────────────────────────
    StageTransition(from_stage="CLAIM_ACCEPTED", to_stage="TREATMENT_BEGINS", base_weight=1.0),

    # ── Treatment → TD Payments ───────────────────────────────────────────
    StageTransition(from_stage="TREATMENT_BEGINS", to_stage="TD_PAYMENTS", base_weight=1.0),

    # ── TD Payments → UR RFA Cycle (optional) ─────────────────────────────
    StageTransition(
        from_stage="TD_PAYMENTS",
        to_stage="UR_RFA_CYCLE",
        base_weight=0.40,
        modifiers=[
            WeightModifier("litigated", True, +0.20),
        ],
    ),
    StageTransition(
        from_stage="TD_PAYMENTS",
        to_stage="QME_DISPUTE",
        base_weight=0.25,
        modifiers=[
            WeightModifier("litigated", True, +0.75),
        ],
    ),
    StageTransition(from_stage="TD_PAYMENTS", to_stage="MMI_REACHED", base_weight=0.35),

    # ── UR RFA → QME Dispute or MMI ───────────────────────────────────────
    StageTransition(
        from_stage="UR_RFA_CYCLE",
        to_stage="QME_DISPUTE",
        base_weight=0.25,
        modifiers=[
            WeightModifier("litigated", True, +0.75),
        ],
    ),
    StageTransition(from_stage="UR_RFA_CYCLE", to_stage="MMI_REACHED", base_weight=0.75),

    # ── QME Dispute → QME Exam ────────────────────────────────────────────
    StageTransition(from_stage="QME_DISPUTE", to_stage="QME_EXAM", base_weight=1.0),

    # ── QME Exam → MMI ────────────────────────────────────────────────────
    StageTransition(from_stage="QME_EXAM", to_stage="MMI_REACHED", base_weight=1.0),

    # ── MMI → PD Rating ───────────────────────────────────────────────────
    StageTransition(from_stage="MMI_REACHED", to_stage="PD_RATING", base_weight=1.0),

    # ── PD Rating → Settlement (C&R or Stips) or WCAB ────────────────────
    StageTransition(
        from_stage="PD_RATING",
        to_stage="SETTLEMENT_CR",
        base_weight=0.40,
        modifiers=[
            WeightModifier("litigated", True, +0.10),
            WeightModifier("high_liens", True, +0.15),
        ],
    ),
    StageTransition(
        from_stage="PD_RATING",
        to_stage="SETTLEMENT_STIPS",
        base_weight=0.45,
        modifiers=[
            WeightModifier("litigated", False, +0.10),
        ],
    ),
    StageTransition(
        from_stage="PD_RATING",
        to_stage="WCAB_HEARING",
        base_weight=0.15,
        modifiers=[
            WeightModifier("litigated", True, +0.45),
            WeightModifier("attorney_represented", False, -0.15),
        ],
    ),

    # ── Denied → WCAB Hearing (if attorney) or Closure ────────────────────
    StageTransition(
        from_stage="CLAIM_DENIED",
        to_stage="WCAB_HEARING",
        base_weight=0.20,
        modifiers=[
            WeightModifier("attorney_represented", True, +0.60),
            WeightModifier("litigated", True, +0.30),
        ],
    ),
    StageTransition(
        from_stage="CLAIM_DENIED",
        to_stage="CLOSURE",
        base_weight=0.80,
        modifiers=[
            WeightModifier("attorney_represented", True, -0.60),
        ],
    ),

    # ── WCAB Hearing → Settlement ─────────────────────────────────────────
    StageTransition(
        from_stage="WCAB_HEARING",
        to_stage="SETTLEMENT_CR",
        base_weight=0.50,
    ),
    StageTransition(
        from_stage="WCAB_HEARING",
        to_stage="SETTLEMENT_STIPS",
        base_weight=0.35,
    ),
    StageTransition(
        from_stage="WCAB_HEARING",
        to_stage="CLOSURE",
        base_weight=0.15,
    ),

    # ── Settlements → Closure ────────────────────────────────────────────
    StageTransition(from_stage="SETTLEMENT_CR", to_stage="CLOSURE", base_weight=1.0),
    StageTransition(from_stage="SETTLEMENT_STIPS", to_stage="CLOSURE", base_weight=1.0),
]


def get_transitions_from(stage_id: str) -> list[StageTransition]:
    """Return all transitions that originate from the given stage."""
    return [t for t in TRANSITIONS if t.from_stage == stage_id]


# Terminal stages — DAG walk ends here
TERMINAL_STAGES: frozenset[str] = frozenset(["CLOSURE"])
