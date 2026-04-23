"""
Financial profile generator — AWW → TD rate calculations.

TD_RATE_TABLE MUST match AdjudiCLAIMS-ai-app/server/services/benefit-calculator.service.ts
exactly. Any change requires updating both files simultaneously.

Source table (from benefit-calculator.service.ts):
  2024: min: 230.95, max: 1619.15
  2025: min: 242.86, max: 1694.57
  2026: min: 252.43, max: 1761.71

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import random

from claims_generator.models.financial import FinancialProfile

# ── TD Rate Table — MUST match benefit-calculator.service.ts EXACTLY ──────────
# Any change requires a simultaneous update to benefit-calculator.service.ts.
TD_RATE_TABLE: dict[int, dict[str, float]] = {
    2024: {"min": 230.95, "max": 1619.15},
    2025: {"min": 242.86, "max": 1694.57},
    2026: {"min": 252.43, "max": 1761.71},
}

# CA LC 4453: TD = 2/3 of AWW, clamped to [min, max]
TD_RATE_MULTIPLIER: float = 2.0 / 3.0

# Fallback year when injury year not in table
FALLBACK_YEAR: int = 2025


def compute_td_rate(aww: float, injury_year: int) -> tuple[float, float, float]:
    """
    Compute weekly TD rate from AWW and injury year.

    CA LC 4653: TD = 2/3 AWW, subject to statutory min/max.

    Args:
        aww: Average Weekly Wage in dollars
        injury_year: Year of injury (determines min/max bounds)

    Returns:
        (td_weekly_rate, td_min, td_max)
    """
    rates = TD_RATE_TABLE.get(injury_year) or TD_RATE_TABLE[FALLBACK_YEAR]
    td_min = rates["min"]
    td_max = rates["max"]

    raw_td = aww * TD_RATE_MULTIPLIER
    td_rate = max(td_min, min(td_max, raw_td))

    return round(td_rate, 2), td_min, td_max


def generate_financial(
    rng: random.Random,
    injury_year: int,
    occupation_title: str = "",
    ptd_claim: bool = False,
) -> FinancialProfile:
    """
    Generate a financial profile based on occupation and injury year.

    Args:
        rng: Seeded random generator
        injury_year: Year of injury (for TD rate table lookup)
        occupation_title: Used to weight AWW distribution
        ptd_claim: PTD claims get higher AWW (more at stake)
    """
    # AWW distribution by occupation category
    # High-risk occupations tend toward higher wages
    high_wage_occupations = {
        "Truck Driver (CDL)", "Maintenance Technician", "Police Officer",
        "Firefighter", "Auto Mechanic", "Forklift Operator",
    }
    low_wage_occupations = {
        "Food Service Worker", "Retail Associate", "Janitor / Custodian",
        "Home Health Aide", "Landscaper",
    }

    if ptd_claim:
        # PTD cases tend to have higher wages
        aww = round(rng.uniform(1200.0, 2500.0), 2)
    elif occupation_title in high_wage_occupations:
        aww = round(rng.uniform(900.0, 2200.0), 2)
    elif occupation_title in low_wage_occupations:
        aww = round(rng.uniform(400.0, 900.0), 2)
    else:
        aww = round(rng.uniform(600.0, 1800.0), 2)

    td_rate, td_min, td_max = compute_td_rate(aww, injury_year)

    # PD estimation — rough heuristic, not medically authoritative
    # Real PD rating requires DEU evaluation
    estimated_pd_percent = None
    estimated_pd_weeks = None
    life_pension = False

    if rng.random() > 0.30:  # ~70% of accepted claims have some PD
        pd_percent = round(rng.uniform(3.0, 45.0), 1)
        estimated_pd_percent = pd_percent
        # Rough CA PD week calculation (simplified)
        estimated_pd_weeks = round(pd_percent * 3.0, 1)
        if pd_percent >= 70.0:
            life_pension = True

    return FinancialProfile(
        injury_year=injury_year,
        average_weekly_wage=aww,
        td_weekly_rate=td_rate,
        td_min_rate=td_min,
        td_max_rate=td_max,
        estimated_pd_percent=estimated_pd_percent,
        estimated_pd_weeks=estimated_pd_weeks,
        life_pension_eligible=life_pension,
    )
