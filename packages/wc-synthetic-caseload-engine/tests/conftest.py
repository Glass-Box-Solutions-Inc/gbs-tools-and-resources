"""Shared fixtures. No network access, no wall-clock dependence.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

from typing import Any

import pytest

from wc_caseload_engine.substrate import find_substrate
from wc_caseload_engine.taxonomy import find_classifier

requires_substrate = pytest.mark.skipif(
    find_substrate() is None,
    reason="merus-test-data-generator substrate not on disk",
)

requires_classifier = pytest.mark.skipif(
    find_classifier() is None,
    reason="Adjudica-classifier source tree not on disk",
)


@pytest.fixture
def minimal_case() -> dict[str, Any]:
    """Smallest valid CaseSeed mapping."""
    return {
        "case_id": "probe-001",
        "rng_seed": 42,
        "injury": {
            "type": "specific",
            "date_of_injury": "2023-04-12",
            "body_parts": [{"part": "lumbar_spine", "icd10": "M54.5"}],
        },
    }


@pytest.fixture
def minimal_caseload(minimal_case: dict[str, Any]) -> dict[str, Any]:
    """Smallest valid CaseloadSpec mapping."""
    return {"caseload_id": "probe-load", "cases": [minimal_case]}
