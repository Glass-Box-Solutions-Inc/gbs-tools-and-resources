"""
Multi-employer cumulative trauma scenario — apportionment across multiple employers.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

from claims_generator.models.scenario import ScenarioPreset
from claims_generator.scenarios.base_scenario import BaseScenario


class MultiEmployer(BaseScenario):
    """Multi-employer CT claim with apportionment and joinder proceedings. 16–26 documents."""

    preset = ScenarioPreset(
        slug="multi_employer",
        display_name="Multi-Employer Cumulative Trauma",
        description=(
            "A cumulative trauma claim spanning multiple employers. Generates joinder "
            "petitions, apportionment reports, and multi-carrier coordination documents. "
            "Used to test multi-defendant WCAB proceedings. 16–26 documents."
        ),
        litigated=False,
        attorney_represented=False,
        ct=True,
        denied_scenario=False,
        death_claim=False,
        ptd_claim=False,
        psych_overlay=False,
        multi_employer=True,
        split_carrier=False,
        high_liens=False,
        sjdb_dispute=False,
        expedited=False,
        investigation_active=False,
        expected_doc_min=16,
        expected_doc_max=26,
    )
