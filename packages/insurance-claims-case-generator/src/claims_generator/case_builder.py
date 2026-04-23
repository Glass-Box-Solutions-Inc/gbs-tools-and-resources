"""
Case builder — orchestrates profile generation + lifecycle DAG + timeline
into a complete ClaimCase (JSON only in Phase 1; pdf_bytes={} until Phase 2).

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import uuid
from datetime import date

from claims_generator.core.claim_state import ClaimState
from claims_generator.core.lifecycle_engine import walk_lifecycle
from claims_generator.core.timeline_builder import build_timeline
from claims_generator.models.claim import ClaimCase
from claims_generator.models.scenario import ScenarioPreset
from claims_generator.profile.profile_generator import generate_profile
from claims_generator.scenarios.registry import get_scenario


def build_case(
    scenario_slug: str,
    seed: int,
) -> ClaimCase:
    """
    Build a complete ClaimCase from a scenario slug and seed.

    Phase 1: Returns ClaimCase with pdf_bytes=b"" for all DocumentEvents.
    Phase 2+: Will populate pdf_bytes via document generators.

    Args:
        scenario_slug: One of the registered scenario slugs
        seed: Random seed for full reproducibility

    Returns:
        ClaimCase with ordered document_events
    """
    preset: ScenarioPreset = get_scenario(scenario_slug)

    # 1. Generate profile
    profile = generate_profile(
        seed=seed,
        psych_overlay=preset.psych_overlay,
        ptd_claim=preset.ptd_claim,
    )

    # 2. Build ClaimState from scenario flags
    state = ClaimState(
        litigated=preset.litigated,
        attorney_represented=preset.attorney_represented,
        ct=preset.ct,
        denied_scenario=preset.denied_scenario,
        death_claim=preset.death_claim,
        ptd_claim=preset.ptd_claim,
        psych_overlay=preset.psych_overlay,
        multi_employer=preset.multi_employer,
        split_carrier=preset.split_carrier,
        high_liens=preset.high_liens,
        sjdb_dispute=preset.sjdb_dispute,
        expedited=preset.expedited,
        investigation_active=preset.investigation_active,
        seed=seed,
    )

    # 3. Walk the lifecycle DAG
    stage_path = walk_lifecycle(state)

    # 4. Build timeline with deadline enforcement
    doi_str = profile.medical.date_of_injury
    doi = date.fromisoformat(doi_str)

    events = build_timeline(
        stage_path=stage_path,
        state=state,
        date_of_injury=doi,
    )

    # 5. Assemble ClaimCase
    case_id = f"case-{uuid.uuid4().hex[:12]}"

    return ClaimCase(
        case_id=case_id,
        scenario_slug=scenario_slug,
        seed=seed,
        profile=profile,
        document_events=events,
        stages_visited=state.stages_visited,
    )
