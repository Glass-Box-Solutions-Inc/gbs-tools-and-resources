"""
Shared pytest fixtures for insurance-claims-case-generator tests.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import os
import sys

# Ensure src/ is on the path for all tests
_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import pytest  # noqa: E402

from claims_generator.case_builder import build_case  # noqa: E402
from claims_generator.models.claim import ClaimCase  # noqa: E402


@pytest.fixture(scope="session")
def standard_case() -> ClaimCase:
    """A seeded standard_claim case."""
    return build_case(scenario_slug="standard_claim", seed=42)


@pytest.fixture(scope="session")
def litigated_case() -> ClaimCase:
    """A seeded litigated_qme case."""
    return build_case(scenario_slug="litigated_qme", seed=42)


@pytest.fixture(scope="session")
def denied_case() -> ClaimCase:
    """A seeded denied_claim case."""
    return build_case(scenario_slug="denied_claim", seed=42)


@pytest.fixture(scope="session")
def all_cases(
    standard_case: ClaimCase,
    litigated_case: ClaimCase,
    denied_case: ClaimCase,
) -> list[ClaimCase]:
    """All three Phase 1 scenarios."""
    return [standard_case, litigated_case, denied_case]
