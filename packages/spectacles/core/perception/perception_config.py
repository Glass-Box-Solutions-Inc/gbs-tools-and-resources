"""
Spectacles Perception Configuration
Adaptive perception mode settings for cost-conscious operation
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, List


class PerceptionMode(str, Enum):
    """Perception execution modes"""
    PER_ACTION = "per_action"       # Screenshot/perceive after each action (cheap, simple tasks)
    CONTINUOUS = "continuous"        # Polling/streaming perception (complex tasks, monitoring)
    ON_DEMAND = "on_demand"          # Only when explicitly requested
    HYBRID = "hybrid"                # DOM for fast checks, VLM only when needed (default)


class PerceptionTrigger(str, Enum):
    """Events that trigger perception"""
    ACTION_COMPLETE = "action_complete"     # After browser action completes
    INTERVAL = "interval"                   # Periodic polling
    CHANGE_DETECTED = "change_detected"     # Page content changed
    ERROR_STATE = "error_state"             # Error occurred, need visual context
    EXPLICIT_REQUEST = "explicit_request"   # Manually requested
    NAVIGATION_COMPLETE = "navigation_complete"  # Page navigation finished
    TASK_START = "task_start"               # Beginning of new task


@dataclass
class PerceptionConfig:
    """
    Configuration for adaptive perception behavior.

    Balances cost (VLM calls) vs accuracy (visual verification).
    """

    # Perception mode
    mode: PerceptionMode = PerceptionMode.HYBRID

    # Continuous mode settings
    interval_ms: int = 2000              # Polling interval for continuous mode

    # VLM budget management
    vlm_budget_per_task: int = 10        # Max VLM calls per task
    vlm_budget_warning_threshold: int = 3  # Warn when this many calls remain

    # DOM vs VLM routing
    dom_confidence_threshold: float = 0.7  # Below this, fall back to VLM
    prefer_dom: bool = True              # Try DOM first when possible

    # Change detection
    detect_changes: bool = True          # Monitor for page changes
    change_detection_interval_ms: int = 500  # How often to check for changes

    # Error handling
    screenshot_on_error: bool = True     # Always screenshot on errors
    vlm_on_error: bool = True           # Use VLM for error analysis

    # Caching
    cache_dom_results: bool = True       # Cache DOM perception results
    cache_ttl_ms: int = 1000            # Cache validity duration

    # Cost tracking
    track_costs: bool = True             # Track perception costs

    # Triggers
    enabled_triggers: List[PerceptionTrigger] = field(default_factory=lambda: [
        PerceptionTrigger.ACTION_COMPLETE,
        PerceptionTrigger.ERROR_STATE,
        PerceptionTrigger.NAVIGATION_COMPLETE,
        PerceptionTrigger.TASK_START
    ])

    def should_use_vlm(self, dom_confidence: float, vlm_calls_used: int) -> bool:
        """
        Determine if VLM should be used based on confidence and budget.

        Args:
            dom_confidence: Confidence score from DOM perception
            vlm_calls_used: Number of VLM calls already used in task

        Returns:
            True if VLM should be used
        """
        if vlm_calls_used >= self.vlm_budget_per_task:
            return False  # Budget exhausted

        if dom_confidence < self.dom_confidence_threshold:
            return True  # Low confidence, need VLM

        return False

    def is_trigger_enabled(self, trigger: PerceptionTrigger) -> bool:
        """Check if a perception trigger is enabled"""
        return trigger in self.enabled_triggers

    def get_budget_remaining(self, vlm_calls_used: int) -> int:
        """Get remaining VLM budget"""
        return max(0, self.vlm_budget_per_task - vlm_calls_used)

    def is_budget_low(self, vlm_calls_used: int) -> bool:
        """Check if VLM budget is running low"""
        remaining = self.get_budget_remaining(vlm_calls_used)
        return remaining <= self.vlm_budget_warning_threshold


# Preset configurations for common use cases
PERCEPTION_PRESETS = {
    "monitoring": PerceptionConfig(
        mode=PerceptionMode.CONTINUOUS,
        interval_ms=1000,
        vlm_budget_per_task=20,
        detect_changes=True,
        enabled_triggers=[
            PerceptionTrigger.INTERVAL,
            PerceptionTrigger.CHANGE_DETECTED,
            PerceptionTrigger.ERROR_STATE
        ]
    ),
    "simple_task": PerceptionConfig(
        mode=PerceptionMode.PER_ACTION,
        vlm_budget_per_task=5,
        prefer_dom=True,
        detect_changes=False,
        enabled_triggers=[
            PerceptionTrigger.ACTION_COMPLETE,
            PerceptionTrigger.TASK_START
        ]
    ),
    "complex_task": PerceptionConfig(
        mode=PerceptionMode.HYBRID,
        vlm_budget_per_task=15,
        dom_confidence_threshold=0.6,
        detect_changes=True,
        enabled_triggers=[
            PerceptionTrigger.ACTION_COMPLETE,
            PerceptionTrigger.CHANGE_DETECTED,
            PerceptionTrigger.ERROR_STATE,
            PerceptionTrigger.NAVIGATION_COMPLETE
        ]
    ),
    "cost_conscious": PerceptionConfig(
        mode=PerceptionMode.HYBRID,
        vlm_budget_per_task=3,
        dom_confidence_threshold=0.5,
        prefer_dom=True,
        detect_changes=False,
        screenshot_on_error=True,
        vlm_on_error=False
    )
}


def get_preset_config(preset_name: str) -> PerceptionConfig:
    """Get a preset perception configuration"""
    return PERCEPTION_PRESETS.get(preset_name, PerceptionConfig())
