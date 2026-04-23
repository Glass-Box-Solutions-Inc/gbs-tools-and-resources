"""
Cumulative trauma scenario — multi-year exposure, complex onset date dispute.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

from claims_generator.models.scenario import ScenarioPreset
from claims_generator.scenarios.base_scenario import BaseScenario


class CumulativeTrauma(BaseScenario):
    """Cumulative trauma claim (ct=True). Complex onset date and apportionment. 12–18 documents."""

    preset = ScenarioPreset(
        slug="cumulative_trauma",
        display_name="Cumulative Trauma Claim",
        description=(
            "A claim arising from cumulative trauma over multiple years of employment. "
            "Generates complex onset date disputes, apportionment reports, and extended "
            "treatment cycles. 12–18 documents."
        ),
        litigated=False,
        attorney_represented=False,
        ct=True,
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
        expected_doc_min=12,
        expected_doc_max=18,
    )
