"""
Dynamic case profile generator — replaces 20 hardcoded CASE_PROFILES with
configurable generation of 1–500 case profiles.

Supports:
  - Random generation with configurable stage distribution
  - Constraint-based generation (min surgery cases, min psych cases, etc.)
  - Reproducible via seed
  - Legacy preset that reproduces the original 20 profiles

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import random
from typing import Optional

from pydantic import BaseModel, Field

from data.lifecycle_engine import CaseParameters


# ---------------------------------------------------------------------------
# Constraints model
# ---------------------------------------------------------------------------

class CaseConstraints(BaseModel):
    """Constraints for dynamic case generation."""

    # Minimum counts for specific case features
    min_surgery_cases: int = Field(default=0, ge=0)
    min_psych_cases: int = Field(default=0, ge=0)
    min_lien_cases: int = Field(default=0, ge=0)
    min_ur_dispute_cases: int = Field(default=0, ge=0)

    # Rate targets (0.0–1.0)
    attorney_rate: float = Field(default=0.70, ge=0.0, le=1.0)
    surgery_rate: float = Field(default=0.25, ge=0.0, le=1.0)
    psych_rate: float = Field(default=0.15, ge=0.0, le=1.0)
    ur_dispute_rate: float = Field(default=0.40, ge=0.0, le=1.0)
    lien_rate: float = Field(default=0.30, ge=0.0, le=1.0)
    imr_rate: float = Field(default=0.20, ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Stage distribution
# ---------------------------------------------------------------------------

DEFAULT_STAGE_DISTRIBUTION: dict[str, float] = {
    "intake": 0.15,
    "active_treatment": 0.25,
    "discovery": 0.20,
    "medical_legal": 0.15,
    "settlement": 0.15,
    "resolved": 0.10,
}

# Presets for quick configuration
PRESETS: dict[str, dict[str, float]] = {
    "balanced": DEFAULT_STAGE_DISTRIBUTION,
    "early_stage": {
        "intake": 0.30,
        "active_treatment": 0.35,
        "discovery": 0.15,
        "medical_legal": 0.10,
        "settlement": 0.07,
        "resolved": 0.03,
    },
    "settlement_heavy": {
        "intake": 0.05,
        "active_treatment": 0.10,
        "discovery": 0.15,
        "medical_legal": 0.20,
        "settlement": 0.30,
        "resolved": 0.20,
    },
    "complex_litigation": {
        "intake": 0.05,
        "active_treatment": 0.10,
        "discovery": 0.25,
        "medical_legal": 0.25,
        "settlement": 0.20,
        "resolved": 0.15,
    },
}


# ---------------------------------------------------------------------------
# Doc count ranges by stage
# ---------------------------------------------------------------------------

STAGE_DOC_RANGES: dict[str, tuple[int, int]] = {
    "intake": (18, 28),
    "active_treatment": (25, 45),
    "discovery": (30, 55),
    "medical_legal": (30, 55),
    "settlement": (35, 65),
    "resolved": (45, 75),
}


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

class CaseProfileGenerator:
    """Generate dynamic case profiles with lifecycle parameters."""

    @staticmethod
    def generate_profiles(
        count: int = 20,
        seed: int = 42,
        stage_distribution: dict[str, float] | None = None,
        constraints: CaseConstraints | None = None,
    ) -> list[CaseParameters]:
        """Generate `count` case profiles with the given distribution and constraints.

        Args:
            count: Number of cases to generate (1–500)
            seed: Random seed for reproducibility
            stage_distribution: Dict mapping stage names to proportions (must sum to ~1.0)
            constraints: Minimum counts and rate targets

        Returns:
            List of CaseParameters, one per case to generate
        """
        rng = random.Random(seed)
        constraints = constraints or CaseConstraints()
        dist = stage_distribution or DEFAULT_STAGE_DISTRIBUTION

        # Normalize distribution
        total = sum(dist.values())
        if total > 0:
            dist = {k: v / total for k, v in dist.items()}

        # Allocate cases to stages
        stages = list(dist.keys())
        weights = [dist[s] for s in stages]
        stage_assignments = rng.choices(stages, weights=weights, k=count)

        # Build base profiles
        profiles: list[CaseParameters] = []
        for i, stage in enumerate(stage_assignments):
            profile = CaseParameters(
                target_stage=stage,
                has_attorney=rng.random() < constraints.attorney_rate,
                has_surgery=rng.random() < constraints.surgery_rate,
                has_psych_component=rng.random() < constraints.psych_rate,
                has_ur_dispute=rng.random() < constraints.ur_dispute_rate,
                has_liens=rng.random() < constraints.lien_rate,
                imr_filed=rng.random() < constraints.imr_rate,
                num_body_parts=rng.choices([1, 2, 3], weights=[0.55, 0.30, 0.15])[0],
            )
            # Resolve random fields
            profile = profile.resolve_random(rng)
            profiles.append(profile)

        # Enforce minimum constraints by flipping flags on random profiles
        _enforce_minimums(profiles, constraints, rng)

        return profiles

    @staticmethod
    def generate_legacy_profiles() -> list[CaseParameters]:
        """Generate parameters matching the original 20 hardcoded case profiles.

        This preserves backward compatibility — the lifecycle engine will produce
        similar (not identical) document sets to the old hardcoded distributions.
        """
        legacy = [
            # Intake (3)
            CaseParameters(target_stage="intake", injury_type="specific", body_part_category="spine",
                           has_attorney=True, num_body_parts=1),
            CaseParameters(target_stage="intake", injury_type="specific", body_part_category="upper_extremity",
                           has_attorney=True, num_body_parts=1),
            CaseParameters(target_stage="intake", injury_type="cumulative_trauma", body_part_category="upper_extremity",
                           has_attorney=True, num_body_parts=1),

            # Active Treatment (5)
            CaseParameters(target_stage="active_treatment", injury_type="specific", body_part_category="spine",
                           has_attorney=True, num_body_parts=1),
            CaseParameters(target_stage="active_treatment", injury_type="specific", body_part_category="lower_extremity",
                           has_attorney=True, has_surgery=True, num_body_parts=1),
            CaseParameters(target_stage="active_treatment", injury_type="cumulative_trauma", body_part_category="spine",
                           has_attorney=True, num_body_parts=1),
            CaseParameters(target_stage="active_treatment", injury_type="specific", body_part_category="upper_extremity",
                           has_attorney=True, num_body_parts=1),
            CaseParameters(target_stage="active_treatment", injury_type="specific", body_part_category="lower_extremity",
                           has_attorney=True, num_body_parts=1),

            # Discovery (4)
            CaseParameters(target_stage="discovery", injury_type="specific", body_part_category="spine",
                           has_attorney=True, has_surgery=True, num_body_parts=1),
            CaseParameters(target_stage="discovery", injury_type="cumulative_trauma", body_part_category="upper_extremity",
                           has_attorney=True, num_body_parts=2),
            CaseParameters(target_stage="discovery", injury_type="specific", body_part_category="lower_extremity",
                           has_attorney=True, num_body_parts=1),
            CaseParameters(target_stage="discovery", injury_type="specific", body_part_category="psyche",
                           has_attorney=True, has_psych_component=True, num_body_parts=1),

            # Medical-Legal (3)
            CaseParameters(target_stage="medical_legal", injury_type="cumulative_trauma", body_part_category="spine",
                           has_attorney=True, has_psych_component=True, num_body_parts=2, eval_type="qme"),
            CaseParameters(target_stage="medical_legal", injury_type="specific", body_part_category="upper_extremity",
                           has_attorney=True, has_surgery=True, num_body_parts=1, eval_type="qme"),
            CaseParameters(target_stage="medical_legal", injury_type="specific", body_part_category="lower_extremity",
                           has_attorney=True, num_body_parts=1, eval_type="qme"),

            # Settlement (3)
            CaseParameters(target_stage="settlement", injury_type="specific", body_part_category="spine",
                           has_attorney=True, has_surgery=True, has_psych_component=True, num_body_parts=2,
                           eval_type="qme", resolution_type="stipulations"),
            CaseParameters(target_stage="settlement", injury_type="cumulative_trauma", body_part_category="upper_extremity",
                           has_attorney=True, num_body_parts=1, eval_type="ame", resolution_type="c_and_r"),
            CaseParameters(target_stage="settlement", injury_type="specific", body_part_category="lower_extremity",
                           has_attorney=True, has_surgery=True, num_body_parts=1,
                           eval_type="qme", resolution_type="stipulations"),

            # Resolved (2)
            CaseParameters(target_stage="resolved", injury_type="specific", body_part_category="spine",
                           has_attorney=True, has_surgery=True, has_psych_component=True, num_body_parts=2,
                           eval_type="qme", resolution_type="stipulations"),
            CaseParameters(target_stage="resolved", injury_type="cumulative_trauma", body_part_category="lower_extremity",
                           has_attorney=True, num_body_parts=2,
                           eval_type="qme", resolution_type="c_and_r"),
        ]

        # Resolve any remaining random fields deterministically
        rng = random.Random(42)
        return [p.resolve_random(rng) for p in legacy]


def _enforce_minimums(
    profiles: list[CaseParameters],
    constraints: CaseConstraints,
    rng: random.Random,
) -> None:
    """Flip flags on random profiles to satisfy minimum constraints."""
    def _count(attr: str) -> int:
        return sum(1 for p in profiles if getattr(p, attr))

    def _enforce(attr: str, minimum: int) -> None:
        current = _count(attr)
        if current >= minimum:
            return
        candidates = [i for i, p in enumerate(profiles) if not getattr(p, attr)]
        rng.shuffle(candidates)
        for idx in candidates[:minimum - current]:
            data = profiles[idx].model_dump()
            data[attr] = True
            profiles[idx] = CaseParameters(**data)

    _enforce("has_surgery", constraints.min_surgery_cases)
    _enforce("has_psych_component", constraints.min_psych_cases)
    _enforce("has_liens", constraints.min_lien_cases)
    _enforce("has_ur_dispute", constraints.min_ur_dispute_cases)
