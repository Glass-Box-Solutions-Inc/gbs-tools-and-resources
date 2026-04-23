"""
Litigated QME scenario — attorney-represented claim with QME dispute.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

from claims_generator.models.scenario import ScenarioPreset
from claims_generator.scenarios.base_scenario import BaseScenario


class LitigatedQme(BaseScenario):
    """Litigated claim with attorney representation and QME dispute. 18–30 documents."""

    preset = ScenarioPreset(
        slug="litigated_qme",
        display_name="Litigated Claim — QME Dispute",
        description=(
            "An attorney-represented claim that proceeds through QME panel dispute, "
            "QME evaluation, WCAB filings, and deposition. Typical for disputed "
            "permanent disability or denied treatment. 18–30 documents."
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
        high_liens=False,
        sjdb_dispute=False,
        expedited=False,
        investigation_active=False,
        expected_doc_min=18,
        expected_doc_max=30,
    )
