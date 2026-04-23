"""
Standard claim scenario — baseline accepted claim, no special flags.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

from claims_generator.models.scenario import ScenarioPreset
from claims_generator.scenarios.base_scenario import BaseScenario


class StandardClaim(BaseScenario):
    """Standard accepted claim — all flags False, 8–14 documents."""

    preset = ScenarioPreset(
        slug="standard_claim",
        display_name="Standard Accepted Claim",
        description=(
            "A straightforward accepted workers' compensation claim. "
            "No litigation, no attorney, standard treatment and resolution. "
            "8–14 documents across the lifecycle."
        ),
        litigated=False,
        attorney_represented=False,
        ct=False,
        denied_scenario=False,
        death_claim=False,
        ptd_claim=False,
        psych_overlay=False,
        multi_employer=False,
        split_carrier=False,
        high_liens=False,
        sjdb_dispute=False,
        expedited=False,
        investigation_active=False,
        expected_doc_min=8,
        expected_doc_max=14,
    )
