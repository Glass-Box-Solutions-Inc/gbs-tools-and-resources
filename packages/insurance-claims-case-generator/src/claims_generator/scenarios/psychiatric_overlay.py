"""
Psychiatric overlay scenario — physical injury with added psych component.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

from claims_generator.models.scenario import ScenarioPreset
from claims_generator.scenarios.base_scenario import BaseScenario


class PsychiatricOverlay(BaseScenario):
    """Physical injury claim with psychiatric overlay. Psych eval + apportionment. 14–22 docs."""

    preset = ScenarioPreset(
        slug="psychiatric_overlay",
        display_name="Psychiatric Overlay Claim",
        description=(
            "A physical injury claim with an added psychiatric component (depression, PTSD, "
            "adjustment disorder). Generates psychiatric QME report, psych UR, and "
            "apportionment reports alongside the physical injury documents. 14–22 documents."
        ),
        litigated=False,
        attorney_represented=False,
        ct=False,
        denied_scenario=False,
        death_claim=False,
        ptd_claim=False,
        psych_overlay=True,
        multi_employer=False,
        split_carrier=False,
        high_liens=False,
        sjdb_dispute=False,
        expedited=False,
        investigation_active=False,
        expected_doc_min=14,
        expected_doc_max=22,
    )
