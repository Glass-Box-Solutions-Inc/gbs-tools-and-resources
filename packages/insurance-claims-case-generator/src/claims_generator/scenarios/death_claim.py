"""
Death claim scenario — fatal injury with dependency benefits and burial costs.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

from claims_generator.models.scenario import ScenarioPreset
from claims_generator.scenarios.base_scenario import BaseScenario


class DeathClaim(BaseScenario):
    """Fatal workers' compensation claim with dependency benefit determinations. 12–20 documents."""

    preset = ScenarioPreset(
        slug="death_claim",
        display_name="Death Claim — Fatal Injury",
        description=(
            "A fatal workplace injury claim. Generates death certificate, dependency "
            "questionnaires, burial expense reimbursement, and ongoing death benefit "
            "payment records for dependents. 12–20 documents."
        ),
        litigated=False,
        attorney_represented=False,
        ct=False,
        denied_scenario=False,
        death_claim=True,
        ptd_claim=False,
        psych_overlay=False,
        multi_employer=False,
        split_carrier=False,
        high_liens=False,
        sjdb_dispute=False,
        expedited=False,
        investigation_active=False,
        expected_doc_min=12,
        expected_doc_max=20,
    )
