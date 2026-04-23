"""
QME dispute only scenario — panel dispute without full litigation.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

from claims_generator.models.scenario import ScenarioPreset
from claims_generator.scenarios.base_scenario import BaseScenario


class QmeDisputeOnly(BaseScenario):
    """QME panel dispute on an otherwise accepted, non-litigated claim. 8–14 documents."""

    preset = ScenarioPreset(
        slug="qme_dispute_only",
        display_name="QME Dispute — Non-Litigated",
        description=(
            "An accepted claim where the injured worker invokes QME panel rights "
            "(LC 4062.2) without full litigation. Generates Form 105, panel QME "
            "selection correspondence, and QME evaluation report. 8–14 documents."
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
