"""
Spectacles Perception Manager
Orchestrates adaptive perception based on task complexity and cost constraints
"""

import logging
import asyncio
import hashlib
from typing import Dict, Any, Optional, Tuple, Callable, List
from dataclasses import dataclass, field
from datetime import datetime

from .perception_config import PerceptionConfig, PerceptionMode, PerceptionTrigger
from .perception_router import PerceptionRouter, CombinedPerception
from persistence.constants import PerceptionMethod

logger = logging.getLogger(__name__)


@dataclass
class PerceptionStats:
    """Statistics for perception usage"""
    dom_calls: int = 0
    vlm_calls: int = 0
    cache_hits: int = 0
    total_perception_time_ms: int = 0
    changes_detected: int = 0
    errors_captured: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dom_calls": self.dom_calls,
            "vlm_calls": self.vlm_calls,
            "cache_hits": self.cache_hits,
            "total_perception_time_ms": self.total_perception_time_ms,
            "changes_detected": self.changes_detected,
            "errors_captured": self.errors_captured
        }


@dataclass
class CachedPerception:
    """Cached perception result"""
    perception: CombinedPerception
    method: PerceptionMethod
    timestamp: datetime
    dom_hash: str


class PerceptionManager:
    """
    Manages adaptive perception based on task complexity and cost constraints.

    Responsibilities:
    - Track VLM usage budget
    - Decide when to perceive (per-action vs continuous)
    - Detect page changes for intelligent triggering
    - Cache DOM results for fast repeated checks
    - Provide cost-aware method selection
    """

    def __init__(
        self,
        perception_router: PerceptionRouter,
        config: Optional[PerceptionConfig] = None
    ):
        """
        Initialize perception manager.

        Args:
            perception_router: Router for perception methods
            config: Perception configuration (uses default if None)
        """
        self.router = perception_router
        self.config = config or PerceptionConfig()

        # State
        self.stats = PerceptionStats()
        self._cache: Optional[CachedPerception] = None
        self._last_dom_hash: Optional[str] = None
        self._continuous_task: Optional[asyncio.Task] = None
        self._change_callback: Optional[Callable] = None

        logger.info(
            "PerceptionManager initialized with mode=%s, vlm_budget=%d",
            self.config.mode.value,
            self.config.vlm_budget_per_task
        )

    async def should_perceive(
        self,
        trigger: PerceptionTrigger,
        context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Determine if perception should run based on config and context.

        Args:
            trigger: What triggered this perception request
            context: Additional context (e.g., error info)

        Returns:
            True if perception should proceed
        """
        # Check if trigger is enabled
        if not self.config.is_trigger_enabled(trigger):
            logger.debug("Trigger %s not enabled", trigger.value)
            return False

        # Always perceive on error if configured
        if trigger == PerceptionTrigger.ERROR_STATE and self.config.screenshot_on_error:
            return True

        # Check mode-specific rules
        if self.config.mode == PerceptionMode.ON_DEMAND:
            # Only explicit requests
            return trigger == PerceptionTrigger.EXPLICIT_REQUEST

        if self.config.mode == PerceptionMode.CONTINUOUS:
            # Continuous mode handles its own timing
            return trigger in [
                PerceptionTrigger.INTERVAL,
                PerceptionTrigger.CHANGE_DETECTED,
                PerceptionTrigger.ERROR_STATE
            ]

        # PER_ACTION and HYBRID modes
        return True

    async def perceive_adaptive(
        self,
        goal: str,
        trigger: PerceptionTrigger,
        context: Optional[Dict[str, Any]] = None,
        force_vlm: bool = False
    ) -> Tuple[PerceptionMethod, CombinedPerception]:
        """
        Run perception with cost-aware method selection.

        Args:
            goal: Current task goal
            trigger: What triggered this perception
            context: Additional context
            force_vlm: Force VLM usage regardless of budget

        Returns:
            Tuple of (method used, perception result)
        """
        start_time = datetime.now()

        # Check cache first
        if self.config.cache_dom_results and self._cache:
            cache_age_ms = int((datetime.now() - self._cache.timestamp).total_seconds() * 1000)
            if cache_age_ms < self.config.cache_ttl_ms:
                self.stats.cache_hits += 1
                logger.debug("Using cached perception (age=%dms)", cache_age_ms)
                return self._cache.method, self._cache.perception

        # Determine which method to use
        use_vlm = force_vlm

        if not use_vlm and self.config.mode == PerceptionMode.HYBRID:
            # In hybrid mode, try DOM first
            if self.config.prefer_dom:
                # Check if we should use VLM based on budget and history
                if self.stats.vlm_calls < self.config.vlm_budget_per_task:
                    # VLM available, but prefer DOM unless needed
                    use_vlm = False
                else:
                    use_vlm = False  # Budget exhausted, DOM only

        # Error triggers may force VLM
        if trigger == PerceptionTrigger.ERROR_STATE and self.config.vlm_on_error:
            if self.stats.vlm_calls < self.config.vlm_budget_per_task:
                use_vlm = True
                self.stats.errors_captured += 1

        # Run perception through router
        try:
            method, perception = await self.router.perceive(
                goal=goal,
                context=context,
                force_vlm=use_vlm
            )

            # Update stats
            if method == PerceptionMethod.VLM:
                self.stats.vlm_calls += 1
            else:
                self.stats.dom_calls += 1

            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            self.stats.total_perception_time_ms += duration_ms

            # Cache DOM results
            if self.config.cache_dom_results and method == PerceptionMethod.DOM:
                dom_hash = self._compute_dom_hash(perception)
                self._cache = CachedPerception(
                    perception=perception,
                    method=method,
                    timestamp=datetime.now(),
                    dom_hash=dom_hash
                )

                # Check for changes
                if self._last_dom_hash and dom_hash != self._last_dom_hash:
                    self.stats.changes_detected += 1
                    logger.debug("Page content changed")
                self._last_dom_hash = dom_hash

            # Log budget warning if needed
            if self.config.is_budget_low(self.stats.vlm_calls):
                remaining = self.config.get_budget_remaining(self.stats.vlm_calls)
                logger.warning("VLM budget low: %d calls remaining", remaining)

            logger.debug(
                "Perception complete: method=%s, duration=%dms, vlm_used=%d/%d",
                method.value, duration_ms,
                self.stats.vlm_calls, self.config.vlm_budget_per_task
            )

            return method, perception

        except Exception as e:
            logger.error("Perception failed: %s", e)
            raise

    async def start_continuous_monitoring(
        self,
        goal: str,
        callback: Callable[[PerceptionMethod, CombinedPerception], None],
        context: Optional[Dict[str, Any]] = None
    ):
        """
        Start continuous perception polling.

        Args:
            goal: Task goal for perception
            callback: Function to call with each perception result
            context: Additional context
        """
        if self.config.mode != PerceptionMode.CONTINUOUS:
            logger.warning("Continuous monitoring requested but mode is %s", self.config.mode.value)

        self._change_callback = callback

        async def monitor_loop():
            while True:
                try:
                    # Check if we should perceive
                    if await self.should_perceive(PerceptionTrigger.INTERVAL):
                        method, perception = await self.perceive_adaptive(
                            goal=goal,
                            trigger=PerceptionTrigger.INTERVAL,
                            context=context
                        )
                        callback(method, perception)

                    await asyncio.sleep(self.config.interval_ms / 1000)

                except asyncio.CancelledError:
                    logger.info("Continuous monitoring cancelled")
                    break
                except Exception as e:
                    logger.error("Error in continuous monitoring: %s", e)
                    await asyncio.sleep(1)  # Brief pause before retry

        self._continuous_task = asyncio.create_task(monitor_loop())
        logger.info("Continuous monitoring started (interval=%dms)", self.config.interval_ms)

    async def stop_continuous_monitoring(self):
        """Stop continuous perception polling"""
        if self._continuous_task:
            self._continuous_task.cancel()
            try:
                await self._continuous_task
            except asyncio.CancelledError:
                pass
            self._continuous_task = None
            logger.info("Continuous monitoring stopped")

    async def detect_page_changes(self) -> bool:
        """
        Detect if page content has changed since last perception.

        Returns:
            True if content changed
        """
        if not self.config.detect_changes:
            return False

        # Quick DOM snapshot for comparison
        try:
            method, perception = await self.router.perceive(
                goal="change_detection",
                context={"lightweight": True}
            )

            new_hash = self._compute_dom_hash(perception)

            if self._last_dom_hash and new_hash != self._last_dom_hash:
                self._last_dom_hash = new_hash
                self.stats.changes_detected += 1
                return True

            self._last_dom_hash = new_hash
            return False

        except Exception as e:
            logger.error("Change detection failed: %s", e)
            return False

    def get_budget_remaining(self) -> int:
        """Get remaining VLM calls in budget"""
        return self.config.get_budget_remaining(self.stats.vlm_calls)

    def get_stats(self) -> Dict[str, Any]:
        """Get perception statistics"""
        return {
            **self.stats.to_dict(),
            "budget_remaining": self.get_budget_remaining(),
            "budget_total": self.config.vlm_budget_per_task,
            "mode": self.config.mode.value
        }

    def reset_stats(self):
        """Reset perception statistics (for new task)"""
        self.stats = PerceptionStats()
        self._cache = None
        self._last_dom_hash = None
        logger.debug("Perception stats reset")

    def _compute_dom_hash(self, perception: CombinedPerception) -> str:
        """Compute hash of DOM content for change detection"""
        # Use key page attributes for hash
        content = ""

        if hasattr(perception, 'dom_perception') and perception.dom_perception:
            dom = perception.dom_perception
            content += str(dom.url or "")
            content += str(dom.title or "")
            content += str(len(dom.interactive_elements or []))
            content += str(len(dom.forms or []))
            # Include main text hash
            if dom.main_text:
                content += dom.main_text[:500]  # First 500 chars

        return hashlib.md5(content.encode()).hexdigest()

    def update_config(self, **kwargs):
        """Update configuration values"""
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
                logger.debug("Config updated: %s = %s", key, value)
