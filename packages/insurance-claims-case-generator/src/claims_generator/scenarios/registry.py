"""
Scenario registry — maps slug → ScenarioPreset.

All 13 named scenarios are registered here.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

from claims_generator.models.scenario import ScenarioPreset
from claims_generator.scenarios.complex_lien import ComplexLien
from claims_generator.scenarios.cumulative_trauma import CumulativeTrauma
from claims_generator.scenarios.death_claim import DeathClaim
from claims_generator.scenarios.denied_claim import DeniedClaim
from claims_generator.scenarios.expedited_hearing import ExpeditedHearing
from claims_generator.scenarios.litigated_qme import LitigatedQme
from claims_generator.scenarios.multi_employer import MultiEmployer
from claims_generator.scenarios.psychiatric_overlay import PsychiatricOverlay
from claims_generator.scenarios.ptd_claim import PtdClaim
from claims_generator.scenarios.qme_dispute_only import QmeDisputeOnly
from claims_generator.scenarios.sjdb_voucher import SjdbVoucher
from claims_generator.scenarios.split_carrier import SplitCarrier
from claims_generator.scenarios.standard_claim import StandardClaim

# Registry: slug → ScenarioPreset (13 scenarios total)
SCENARIO_REGISTRY: dict[str, ScenarioPreset] = {
    "standard_claim": StandardClaim.preset,
    "cumulative_trauma": CumulativeTrauma.preset,
    "litigated_qme": LitigatedQme.preset,
    "denied_claim": DeniedClaim.preset,
    "death_claim": DeathClaim.preset,
    "ptd_claim": PtdClaim.preset,
    "psychiatric_overlay": PsychiatricOverlay.preset,
    "multi_employer": MultiEmployer.preset,
    "split_carrier": SplitCarrier.preset,
    "complex_lien": ComplexLien.preset,
    "expedited_hearing": ExpeditedHearing.preset,
    "qme_dispute_only": QmeDisputeOnly.preset,
    "sjdb_voucher": SjdbVoucher.preset,
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
