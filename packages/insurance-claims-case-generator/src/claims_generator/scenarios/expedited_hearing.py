"""
Expedited hearing scenario — fast-track WCAB hearing for TD or medical disputes.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

from claims_generator.models.scenario import ScenarioPreset
from claims_generator.scenarios.base_scenario import BaseScenario


class ExpeditedHearing(BaseScenario):
    """Expedited WCAB hearing for TD payment or treatment disputes. 10–16 documents."""

    preset = ScenarioPreset(
        slug="expedited_hearing",
        display_name="Expedited Hearing — Fast-Track WCAB",
        description=(
            "A claim that triggers an expedited WCAB hearing (LC 5502(b)) due to "
            "disputed TD payments or denied medical treatment. Generates expedited "
            "DOR, MSC, and hearing order. Faster lifecycle than standard litigation. "
            "10–16 documents."
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
        expedited=True,
        investigation_active=False,
        expected_doc_min=10,
        expected_doc_max=16,
    )
