"""
Scenario registry — maps slug → ScenarioPreset.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

from claims_generator.models.scenario import ScenarioPreset
from claims_generator.scenarios.denied_claim import DeniedClaim
from claims_generator.scenarios.litigated_qme import LitigatedQme
from claims_generator.scenarios.standard_claim import StandardClaim

# Registry: slug → ScenarioPreset
SCENARIO_REGISTRY: dict[str, ScenarioPreset] = {
    "standard_claim": StandardClaim.preset,
    "litigated_qme": LitigatedQme.preset,
    "denied_claim": DeniedClaim.preset,
}


def get_scenario(slug: str) -> ScenarioPreset:
    """Look up a scenario preset by slug. Raises KeyError if not found."""
    if slug not in SCENARIO_REGISTRY:
        valid = ", ".join(SCENARIO_REGISTRY.keys())
        raise KeyError(f"Unknown scenario slug: {slug!r}. Valid slugs: {valid}")
    return SCENARIO_REGISTRY[slug]


def list_scenarios() -> list[ScenarioPreset]:
    """Return all registered scenario presets."""
    return list(SCENARIO_REGISTRY.values())
