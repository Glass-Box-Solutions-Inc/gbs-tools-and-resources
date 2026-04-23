"""
Denied claim scenario — investigation-heavy denial with potential WCAB appeal.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

from claims_generator.models.scenario import ScenarioPreset
from claims_generator.scenarios.base_scenario import BaseScenario


class DeniedClaim(BaseScenario):
    """Claim denied after investigation. 10–16 documents."""

    preset = ScenarioPreset(
        slug="denied_claim",
        display_name="Denied Claim — Investigation",
        description=(
            "A claim that is denied after active investigation. Generates "
            "investigation report, denial notice, and may proceed to WCAB hearing "
            "if attorney-represented. 10–16 documents."
        ),
        litigated=False,
        attorney_represented=False,
        ct=False,
        denied_scenario=True,
        death_claim=False,
        ptd_claim=False,
        psych_overlay=False,
        multi_employer=False,
        split_carrier=False,
        high_liens=False,
        sjdb_dispute=False,
        expedited=False,
        investigation_active=True,
        expected_doc_min=10,
        expected_doc_max=16,
    )
