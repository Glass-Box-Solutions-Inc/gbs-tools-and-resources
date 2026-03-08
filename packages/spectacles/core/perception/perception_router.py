"""
Spectacles Perception Router
Routes perception requests to DOM or VLM based on context

Strategy:
- 80% DOM: Fast, structured, reliable for standard elements
- 20% VLM: Complex layouts, visual elements, error states
"""

import logging
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from playwright.async_api import Page

from .dom_extractor import DOMExtractor, DOMPerception
from .vlm_perceiver import VLMPerceiver, VLMPerception
from persistence.constants import PerceptionMethod

logger = logging.getLogger(__name__)


@dataclass
class CombinedPerception:
    """Combined result from DOM and/or VLM perception"""
    method: PerceptionMethod
    url: str
    title: str

    # From DOM
    interactive_elements: list
    forms: list
    navigation: list
    main_content: str

    # From VLM (if used)
    page_type: Optional[str] = None
    vlm_elements: Optional[list] = None
    current_state: Optional[str] = None
    suggested_action: Optional[str] = None
    blockers: Optional[list] = None

    # Metadata
    confidence: float = 1.0
    dom_confidence: float = 1.0
    vlm_confidence: float = 0.0

    # Raw perception objects for change detection
    dom_perception: Optional['DOMPerception'] = None
    vlm_perception: Optional['VLMPerception'] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "method": self.method.value,
            "url": self.url,
            "title": self.title,
            "interactive_elements": self.interactive_elements,
            "forms": self.forms,
            "navigation": self.navigation,
            "main_content": self.main_content[:500] if self.main_content else "",
            "page_type": self.page_type,
            "vlm_elements": self.vlm_elements,
            "current_state": self.current_state,
            "suggested_action": self.suggested_action,
            "blockers": self.blockers,
            "confidence": self.confidence,
        }


class PerceptionRouter:
    """
    Routes perception requests to appropriate method.

    Strategy:
    - Try DOM first (fast, reliable)
    - Fall back to VLM when:
        - DOM extraction has low confidence
        - Complex elements detected (canvas, CAPTCHA)
        - Goal requires visual understanding
        - Previous DOM attempt failed

    Can also run both in HYBRID mode for highest accuracy.
    """

    # Keywords that suggest VLM is needed
    VLM_KEYWORDS = [
        "captcha",
        "verify",
        "visual",
        "image",
        "picture",
        "drag",
        "slider",
        "puzzle",
        "canvas",
        "drawing",
        "screenshot",
    ]

    # Confidence threshold for DOM-only
    DOM_CONFIDENCE_THRESHOLD = 0.7

    def __init__(
        self,
        page: Page,
        vlm_perceiver: Optional[VLMPerceiver] = None
    ):
        """
        Initialize perception router.

        Args:
            page: Playwright page object
            vlm_perceiver: VLM perceiver instance (optional)
        """
        self.page = page
        self.dom_extractor = DOMExtractor(page)
        self.vlm_perceiver = vlm_perceiver

    async def perceive(
        self,
        goal: str,
        context: Optional[Dict[str, Any]] = None,
        force_method: Optional[PerceptionMethod] = None,
        force_vlm: bool = False
    ) -> Tuple[PerceptionMethod, CombinedPerception]:
        """
        Determine perception method and extract page state.

        Args:
            goal: Current task goal
            context: Additional context from previous actions
            force_method: Force specific perception method
            force_vlm: Force VLM usage (alternative to force_method)

        Returns:
            Tuple of (method used, combined perception result)
        """
        # Check if VLM is available
        has_vlm = self.vlm_perceiver is not None

        # Check for VLM keywords in goal
        needs_vlm_for_goal = self._goal_needs_vlm(goal)

        # Handle force_vlm parameter
        if force_vlm:
            force_method = PerceptionMethod.VLM

        # Forced method
        if force_method:
            if force_method == PerceptionMethod.VLM and not has_vlm:
                logger.warning("VLM requested but not available, falling back to DOM")
                force_method = PerceptionMethod.DOM

        # Start with DOM extraction (always fast)
        logger.info("Running DOM perception...")
        dom_result = await self.dom_extractor.extract()

        # Decide if VLM is needed
        use_vlm = False
        vlm_reason = None

        if force_method == PerceptionMethod.VLM:
            use_vlm = True
            vlm_reason = "Forced VLM mode"
        elif force_method == PerceptionMethod.HYBRID:
            use_vlm = True
            vlm_reason = "Hybrid mode requested"
        elif dom_result.needs_vlm:
            use_vlm = True
            vlm_reason = dom_result.vlm_reason
        elif dom_result.confidence < self.DOM_CONFIDENCE_THRESHOLD:
            use_vlm = True
            vlm_reason = f"Low DOM confidence: {dom_result.confidence}"
        elif needs_vlm_for_goal:
            use_vlm = True
            vlm_reason = "Goal requires visual understanding"

        # Run VLM if needed and available
        vlm_result = None
        if use_vlm and has_vlm:
            logger.info("Running VLM perception: %s", vlm_reason)
            screenshot = await self.page.screenshot()
            vlm_result = await self.vlm_perceiver.analyze(
                screenshot_bytes=screenshot,
                goal=goal,
                context=context
            )

        # Determine final method
        if vlm_result:
            if force_method == PerceptionMethod.HYBRID or dom_result.confidence >= 0.5:
                method = PerceptionMethod.HYBRID
            else:
                method = PerceptionMethod.VLM
        else:
            method = PerceptionMethod.DOM

        # Combine results
        combined = self._combine_results(dom_result, vlm_result, method)

        logger.info(
            "Perception complete: method=%s, confidence=%.2f",
            method, combined.confidence
        )

        return method, combined

    async def quick_dom_check(self) -> DOMPerception:
        """
        Quick DOM-only perception for simple checks.

        Returns:
            DOM perception result
        """
        return await self.dom_extractor.extract()

    async def vlm_only(
        self,
        goal: str,
        query: Optional[str] = None
    ) -> Optional[VLMPerception]:
        """
        Run VLM perception only.

        Args:
            goal: Current task goal
            query: Specific question

        Returns:
            VLM perception result or None if unavailable
        """
        if not self.vlm_perceiver:
            logger.warning("VLM not available")
            return None

        screenshot = await self.page.screenshot()
        return await self.vlm_perceiver.analyze(
            screenshot_bytes=screenshot,
            goal=goal,
            specific_query=query
        )

    def _goal_needs_vlm(self, goal: str) -> bool:
        """Check if goal keywords suggest VLM is needed"""
        goal_lower = goal.lower()
        return any(keyword in goal_lower for keyword in self.VLM_KEYWORDS)

    def _combine_results(
        self,
        dom: DOMPerception,
        vlm: Optional[VLMPerception],
        method: PerceptionMethod
    ) -> CombinedPerception:
        """Combine DOM and VLM results"""

        # Calculate combined confidence
        if method == PerceptionMethod.HYBRID and vlm:
            confidence = (dom.confidence * 0.4) + (vlm.confidence * 0.6)
        elif method == PerceptionMethod.VLM and vlm:
            confidence = vlm.confidence
        else:
            confidence = dom.confidence

        return CombinedPerception(
            method=method,
            url=dom.url,
            title=dom.title,
            interactive_elements=dom.interactive_elements,
            forms=dom.forms,
            navigation=dom.navigation,
            main_content=dom.main_content,
            page_type=vlm.page_type if vlm else None,
            vlm_elements=vlm.elements if vlm else None,
            current_state=vlm.current_state if vlm else None,
            suggested_action=vlm.suggested_action if vlm else None,
            blockers=vlm.blockers if vlm else None,
            confidence=confidence,
            dom_confidence=dom.confidence,
            vlm_confidence=vlm.confidence if vlm else 0.0,
            # Store raw perception objects for change detection
            dom_perception=dom,
            vlm_perception=vlm,
        )

    def set_vlm_perceiver(self, vlm_perceiver: VLMPerceiver):
        """Set or update VLM perceiver"""
        self.vlm_perceiver = vlm_perceiver
        logger.info("VLM perceiver set: %s", vlm_perceiver.model_name)
