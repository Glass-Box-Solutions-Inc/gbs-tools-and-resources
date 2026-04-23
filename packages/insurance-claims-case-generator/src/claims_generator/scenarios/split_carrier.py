"""
Split carrier scenario — successive injury with separate carriers for each period.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

from claims_generator.models.scenario import ScenarioPreset
from claims_generator.scenarios.base_scenario import BaseScenario


class SplitCarrier(BaseScenario):
    """Successive injury across two carriers. Carrier-to-carrier coordination. 10–18 documents."""

    preset = ScenarioPreset(
        slug="split_carrier",
        display_name="Split Carrier — Successive Injury",
        description=(
            "A claim involving two separate carriers responsible for different periods of "
            "disability (e.g., specific injury + cumulative trauma). Generates carrier "
            "coordination correspondence, apportionment disputes, and split payment records. "
            "10–18 documents."
        ),
        litigated=False,
        attorney_represented=False,
        ct=False,
        denied_scenario=False,
        death_claim=False,
        ptd_claim=False,
        psych_overlay=False,
        multi_employer=False,
        split_carrier=True,
        high_liens=False,
        sjdb_dispute=False,
        expedited=False,
        investigation_active=False,
        expected_doc_min=10,
        expected_doc_max=18,
    )
