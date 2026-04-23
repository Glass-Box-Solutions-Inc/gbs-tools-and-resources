"""
SJDB voucher scenario — Supplemental Job Displacement Benefit dispute.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

from claims_generator.models.scenario import ScenarioPreset
from claims_generator.scenarios.base_scenario import BaseScenario


class SjdbVoucher(BaseScenario):
    """Claim with SJDB voucher dispute (AD 10133.53 / LC 4658.7). 10–16 documents."""

    preset = ScenarioPreset(
        slug="sjdb_voucher",
        display_name="SJDB Voucher Dispute",
        description=(
            "A claim where the employer cannot offer modified or alternative work, "
            "triggering the Supplemental Job Displacement Benefit voucher (LC 4658.7). "
            "Generates RTW offer letters, SJDB Form AD 10133.53, and voucher issuance "
            "or dispute correspondence. 10–16 documents."
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
        sjdb_dispute=True,
        expedited=False,
        investigation_active=False,
        expected_doc_min=10,
        expected_doc_max=16,
    )
