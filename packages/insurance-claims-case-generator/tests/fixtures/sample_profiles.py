"""
Sample profile fixtures for use in tests.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

from claims_generator.models.profile import ClaimProfile
from claims_generator.profile.profile_generator import generate_profile


def make_standard_profile(seed: int = 42) -> ClaimProfile:
    """Standard profile — no special flags."""
    return generate_profile(seed=seed)


def make_psych_profile(seed: int = 99) -> ClaimProfile:
    """Profile with psychiatric overlay."""
    return generate_profile(seed=seed, psych_overlay=True)


def make_ptd_profile(seed: int = 100) -> ClaimProfile:
    """Profile for a PTD claim — higher wages."""
    return generate_profile(seed=seed, ptd_claim=True)
