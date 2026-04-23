"""
Regression tests for financial_gen.py TD rate calculations.

These values MUST match AdjudiCLAIMS-ai-app/server/services/benefit-calculator.service.ts.
If any assertion fails, check BOTH files for sync.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import pytest

from claims_generator.profile.financial_gen import (
    TD_RATE_MULTIPLIER,
    TD_RATE_TABLE,
    compute_td_rate,
)

# ── Table integrity ────────────────────────────────────────────────────────────

def test_td_rate_table_has_required_years() -> None:
    """TD_RATE_TABLE must have entries for 2024, 2025, and 2026."""
    assert 2024 in TD_RATE_TABLE
    assert 2025 in TD_RATE_TABLE
    assert 2026 in TD_RATE_TABLE


def test_td_rate_table_2024_values() -> None:
    """2024 rates must match benefit-calculator.service.ts exactly."""
    assert TD_RATE_TABLE[2024]["min"] == 230.95
    assert TD_RATE_TABLE[2024]["max"] == 1619.15


def test_td_rate_table_2025_values() -> None:
    """2025 rates must match benefit-calculator.service.ts exactly."""
    assert TD_RATE_TABLE[2025]["min"] == 242.86
    assert TD_RATE_TABLE[2025]["max"] == 1694.57


def test_td_rate_table_2026_values() -> None:
    """2026 rates must match benefit-calculator.service.ts exactly."""
    assert TD_RATE_TABLE[2026]["min"] == 252.43
    assert TD_RATE_TABLE[2026]["max"] == 1761.71


# ── Rate multiplier ────────────────────────────────────────────────────────────

def test_td_rate_multiplier() -> None:
    """TD rate multiplier must be 2/3 per CA LC 4653."""
    assert abs(TD_RATE_MULTIPLIER - (2.0 / 3.0)) < 1e-10


# ── compute_td_rate behavior ───────────────────────────────────────────────────

@pytest.mark.parametrize("year", [2024, 2025, 2026])
def test_minimum_aww_returns_min_rate(year: int) -> None:
    """AWW of $0 must return the statutory minimum."""
    rate, td_min, td_max = compute_td_rate(aww=0.0, injury_year=year)
    assert rate == TD_RATE_TABLE[year]["min"]
    assert td_min == TD_RATE_TABLE[year]["min"]
    assert td_max == TD_RATE_TABLE[year]["max"]


@pytest.mark.parametrize("year", [2024, 2025, 2026])
def test_very_high_aww_returns_max_rate(year: int) -> None:
    """AWW of $10,000 must return the statutory maximum."""
    rate, td_min, td_max = compute_td_rate(aww=10000.0, injury_year=year)
    assert rate == TD_RATE_TABLE[year]["max"]


@pytest.mark.parametrize("year", [2024, 2025, 2026])
def test_mid_range_aww_is_two_thirds(year: int) -> None:
    """Mid-range AWW must produce exactly 2/3 of AWW as TD rate."""
    # AWW where 2/3 falls between min and max
    aww = 1200.0
    rate, _, _ = compute_td_rate(aww=aww, injury_year=year)
    expected = round(aww * (2.0 / 3.0), 2)
    assert rate == expected, f"Year {year}: expected {expected}, got {rate}"


def test_compute_td_rate_2025_specific_values() -> None:
    """Spot-check specific 2025 values from benefit-calculator.service.ts."""
    # AWW $500 → 2/3 = $333.33 — above 2025 min ($242.86), below max ($1694.57)
    rate, _, _ = compute_td_rate(aww=500.0, injury_year=2025)
    expected = round(500.0 * 2.0 / 3.0, 2)
    assert rate == expected  # $333.33

    # AWW $300 → 2/3 = $200.00 — below 2025 min → clamp to min
    rate, _, _ = compute_td_rate(aww=300.0, injury_year=2025)
    assert rate == 242.86  # 2025 min

    # AWW $3000 → 2/3 = $2000.00 — above 2025 max → clamp to max
    rate, _, _ = compute_td_rate(aww=3000.0, injury_year=2025)
    assert rate == 1694.57  # 2025 max


def test_unknown_year_uses_fallback() -> None:
    """Unknown injury year must use the fallback year without raising."""
    rate, td_min, td_max = compute_td_rate(aww=1000.0, injury_year=2020)
    # Should not raise — uses 2025 fallback
    assert td_min > 0
    assert td_max > td_min
    assert rate >= td_min
    assert rate <= td_max


@pytest.mark.parametrize("year", [2024, 2025, 2026])
def test_rate_always_within_bounds(year: int) -> None:
    """TD rate must always be within [min, max] for any positive AWW."""
    import random
    rng = random.Random(42)
    for _ in range(100):
        aww = rng.uniform(0, 5000)
        rate, td_min, td_max = compute_td_rate(aww=aww, injury_year=year)
        assert td_min <= rate <= td_max, (
            f"Year {year}, AWW={aww}: rate {rate} out of bounds [{td_min}, {td_max}]"
        )
