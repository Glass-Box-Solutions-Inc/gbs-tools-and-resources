"""
Base scenario — protocol for all scenario implementations.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

from claims_generator.models.scenario import ScenarioPreset


class BaseScenario:
    """Base class for all scenario implementations."""

    preset: ScenarioPreset

    @classmethod
    def get_preset(cls) -> ScenarioPreset:
        """Return the ScenarioPreset for this scenario."""
        return cls.preset
