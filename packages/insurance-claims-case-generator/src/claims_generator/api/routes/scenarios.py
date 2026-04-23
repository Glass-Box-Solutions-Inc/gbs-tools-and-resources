"""
GET /api/v1/scenarios        — list all scenario presets
GET /api/v1/scenarios/{slug} — get a single scenario preset

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from claims_generator.api.schemas import ScenarioResponse
from claims_generator.scenarios.registry import get_scenario, list_scenarios

router = APIRouter()


@router.get("/scenarios", response_model=list[ScenarioResponse], tags=["scenarios"])
async def list_all_scenarios() -> list[ScenarioResponse]:
    """Return all 13 registered scenario presets."""
    return [ScenarioResponse.from_preset(p) for p in list_scenarios()]


@router.get("/scenarios/{slug}", response_model=ScenarioResponse, tags=["scenarios"])
async def get_scenario_by_slug(slug: str) -> ScenarioResponse:
    """Return a single scenario preset by slug."""
    try:
        preset = get_scenario(slug)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ScenarioResponse.from_preset(preset)
