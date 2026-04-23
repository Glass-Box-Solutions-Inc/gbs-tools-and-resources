"""
Complex lien scenario — litigated claim with high medical provider lien load.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

from claims_generator.models.scenario import ScenarioPreset
from claims_generator.scenarios.base_scenario import BaseScenario


class ComplexLien(BaseScenario):
    """Litigated claim with multiple high-value provider liens. 20–32 documents."""

    preset = ScenarioPreset(
        slug="complex_lien",
        display_name="Complex Lien — High Lien Load",
        description=(
            "A litigated claim with multiple medical provider liens totaling $50K+. "
            "Generates lien conference notices, lien orders, provider billing disputes, "
            "and settlement negotiations that include lien resolution. 20–32 documents."
        ),
        litigated=True,
        attorney_represented=True,
        ct=False,
        denied_scenario=False,
        death_claim=False,
        ptd_claim=False,
        psych_overlay=False,
        multi_employer=False,
        split_carrier=False,
        high_liens=True,
        sjdb_dispute=False,
        expedited=False,
        investigation_active=False,
        expected_doc_min=20,
        expected_doc_max=32,
    )
