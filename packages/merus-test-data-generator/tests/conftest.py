"""
Shared pytest fixtures for the merus-test-data-generator test suite.

Taxonomy: 15 types / 350 subtypes.
"""

from __future__ import annotations

import sys
import os

# Add the package root to sys.path so all imports resolve correctly.
_PACKAGE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PACKAGE_ROOT not in sys.path:
    sys.path.insert(0, _PACKAGE_ROOT)

import pytest

from data.fake_data_generator import FakeDataGenerator
from data.taxonomy import DocumentSubtype


@pytest.fixture(scope="session")
def fake_gen() -> FakeDataGenerator:
    """A seeded FakeDataGenerator instance shared across the session."""
    return FakeDataGenerator(seed=42)


@pytest.fixture(scope="session")
def all_subtypes() -> list[str]:
    """All DocumentSubtype enum values as strings."""
    return [s.value for s in DocumentSubtype]
