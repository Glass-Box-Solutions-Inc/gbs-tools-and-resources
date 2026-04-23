"""
Permanent Total Disability (PTD) claim — litigated, high-value lifetime benefits.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

from claims_generator.models.scenario import ScenarioPreset
from claims_generator.scenarios.base_scenario import BaseScenario


class PtdClaim(BaseScenario):
    """PTD claim — litigated, attorney-represented, lifetime benefit dispute. 20–35 documents."""

    preset = ScenarioPreset(
        slug="ptd_claim",
        display_name="Permanent Total Disability — Litigated",
        description=(
            "A high-complexity claim where the injured worker is permanently and totally "
            "disabled (LC 4662). Attorney-represented with WCAB litigation over lifetime "
            "benefit calculations, vocational expert reports, and life-care plans. "
            "20–35 documents."
        ),
        litigated=True,
        attorney_represented=True,
        ct=False,
        denied_scenario=False,
        death_claim=False,
        ptd_claim=True,
        psych_overlay=False,
        multi_employer=False,
        split_carrier=False,
        high_liens=False,
        sjdb_dispute=False,
        expedited=False,
        investigation_active=False,
        expected_doc_min=20,
        expected_doc_max=35,
    )
