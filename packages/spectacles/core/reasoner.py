"""
AI Reasoner Core - Strategic task planning using LLM reasoning

This module implements the AI-based decision layer that determines whether to use
cached patterns from memory or perform VLM-based discovery for browser automation tasks.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import logging
from typing import Optional, Dict, List
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class ExecutionPlan:
    """Plan for executing a browser automation task."""
    plan_type: str  # "pattern" | "discovery"
    pattern_id: Optional[str]
    steps: List[Dict]
    estimated_vlm_calls: int
    confidence: float
    reasoning: str  # Explanation of why this plan was chosen


class AIReasoner:
    """
    AI-based strategic planner for browser automation tasks.
    
    The reasoner decides whether to:
    1. Use a cached pattern from memory (fast, no VLM cost)
    2. Perform VLM-based discovery (slower, higher cost, but flexible)
    
    Decision factors:
    - Pattern availability in memory
    - Pattern confidence score (success rate)
    - Task similarity to known patterns
    - Confidence threshold (default: 0.7)
    """

    def __init__(
        self,
        pattern_store=None,
        gemini_api_key: str = None,
        reasoning_model: str = "gemini-3.0",
        timeout_seconds: int = 60
    ):
        """
        Initialize the AI Reasoner.

        Args:
            pattern_store: PatternStore instance for memory queries (optional for now)
            gemini_api_key: Google AI API key for Gemini reasoning
            reasoning_model: Gemini model for strategic reasoning (default: gemini-3.0)
            timeout_seconds: Timeout for reasoning calls
        """
        self.pattern_store = pattern_store
        self.gemini_api_key = gemini_api_key
        self.reasoning_model = reasoning_model
        self.timeout_seconds = timeout_seconds
        self.confidence_threshold = 0.7

        # Initialize Gemini client if API key provided
        self.model = None
        if gemini_api_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=gemini_api_key)
                self.model = genai.GenerativeModel(reasoning_model)
                logger.info(
                    "AIReasoner initialized with %s (confidence threshold: %.2f)",
                    reasoning_model,
                    self.confidence_threshold
                )
            except Exception as e:
                logger.warning("Failed to initialize Gemini for reasoning: %s", e)
        else:
            logger.info("AIReasoner initialized without Gemini (confidence threshold: %.2f)", self.confidence_threshold)

    async def plan_task(self, goal: str, url: str, context: dict = None) -> ExecutionPlan:
        """
        Generate execution plan for a browser automation task.
        
        Strategy:
        1. Query memory for similar patterns
        2. If high-confidence pattern exists (>0.7), use it
        3. Otherwise, create discovery plan with VLM
        
        Args:
            goal: Natural language task description
            url: Starting URL for the task
            context: Additional context (credentials, requirements, etc.)
            
        Returns:
            ExecutionPlan with type, steps, and estimated costs
        """
        context = context or {}
        
        logger.info("Planning task: '%s' at '%s'", goal, url)
        
        # 1. Query memory for similar patterns (if pattern store exists)
        if self.pattern_store:
            patterns = await self.pattern_store.query_similar(goal, url, limit=5)
            
            # 2. If high-confidence pattern exists, use it
            if patterns and patterns[0].confidence > self.confidence_threshold:
                logger.info(
                    "Found high-confidence pattern: %s (%.2f confidence)",
                    patterns[0].id,
                    patterns[0].confidence
                )
                return self._create_pattern_plan(patterns[0])
        else:
            logger.debug("Pattern store not configured, skipping memory query")
        
        # 3. Otherwise, create discovery plan
        logger.info("No high-confidence pattern found, using VLM discovery mode")
        return await self._create_discovery_plan(goal, url, context)

    def _create_pattern_plan(self, pattern) -> ExecutionPlan:
        """
        Create execution plan from cached pattern.
        
        This path avoids VLM calls entirely, executing stored selectors and actions directly.
        
        Args:
            pattern: Pattern object from memory
            
        Returns:
            ExecutionPlan with pattern-based steps (0 VLM calls)
        """
        return ExecutionPlan(
            plan_type="pattern",
            pattern_id=pattern.id,
            steps=pattern.pattern_data.get("sequence", []),
            estimated_vlm_calls=0,  # No VLM needed!
            confidence=pattern.confidence,
            reasoning=f"Using cached pattern (success rate: {pattern.success_count}/{pattern.success_count + pattern.failure_count})"
        )

    async def _create_discovery_plan(self, goal: str, url: str, context: dict) -> ExecutionPlan:
        """
        Use Gemini 2.5 Pro to reason about task structure for unknown tasks.

        This is the fallback path when no pattern exists or confidence is too low.
        It uses strategic reasoning to plan the optimal approach with minimal VLM usage.

        Args:
            goal: Task description
            url: Starting URL
            context: Additional context

        Returns:
            ExecutionPlan with AI-generated strategic steps
        """
        # If Gemini model is available, use it for strategic planning
        if self.model:
            try:
                plan = await self._generate_strategic_plan(goal, url, context)
                if plan:
                    return plan
            except Exception as e:
                logger.warning("Gemini reasoning failed, falling back to basic plan: %s", e)

        # Fallback: Basic discovery plan
        steps = [
            {"action": "navigate", "target": url},
            {"action": "observe", "purpose": "Locate relevant elements"},
            {"action": "achieve_goal", "goal": goal}
        ]

        return ExecutionPlan(
            plan_type="discovery",
            pattern_id=None,
            steps=steps,
            estimated_vlm_calls=3,  # Rough estimate for typical tasks
            confidence=0.5,  # Unknown task, medium confidence
            reasoning="No pattern available, using VLM-based discovery"
        )

    async def _generate_strategic_plan(self, goal: str, url: str, context: dict) -> Optional[ExecutionPlan]:
        """
        Use Gemini 3.0 to generate a strategic execution plan.

        This leverages advanced reasoning to minimize VLM calls and maximize efficiency.

        Args:
            goal: Task description
            url: Starting URL
            context: Additional context

        Returns:
            ExecutionPlan or None if generation fails
        """
        prompt = f"""You are a strategic planner for browser automation tasks.

Task Goal: {goal}
Starting URL: {url}
Context: {context}

Create an efficient execution plan with these guidelines:
1. Minimize vision API calls (they're expensive) - prefer DOM-based actions
2. Break complex goals into clear, sequential steps
3. Anticipate common web patterns (login forms, navigation, data extraction)
4. Plan for error handling and verification

Return a JSON object with:
{{
    "steps": [
        {{
            "action": "navigate|click|fill|observe|wait|verify",
            "target": "CSS selector or description",
            "purpose": "why this step is needed",
            "requires_vlm": true/false,
            "fallback": "what to do if this step fails"
        }}
    ],
    "estimated_vlm_calls": <number>,
    "confidence": 0.0-1.0,
    "reasoning": "explanation of the strategy",
    "risks": ["potential issues"],
    "success_criteria": "how to know the task succeeded"
}}

Focus on efficiency and reliability. Return ONLY the JSON object."""

        try:
            response = await self.model.generate_content_async(
                prompt,
                generation_config={
                    "temperature": 0.3,  # Low for structured planning, but not too rigid
                    "max_output_tokens": 2048,
                }
            )

            # Parse response
            import json
            text = response.text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]

            data = json.loads(text)

            return ExecutionPlan(
                plan_type="discovery",
                pattern_id=None,
                steps=data.get("steps", []),
                estimated_vlm_calls=data.get("estimated_vlm_calls", 5),
                confidence=data.get("confidence", 0.6),
                reasoning=data.get("reasoning", "AI-generated strategic plan")
            )

        except Exception as e:
            logger.error("Failed to generate strategic plan with Gemini: %s", e)
            return None


# Pattern data structure (will be properly implemented in Phase 2)
@dataclass
class Pattern:
    """Pattern stored in memory for reuse."""
    id: str
    site_domain: str
    site_url: str
    goal: str
    pattern_type: str
    pattern_data: Dict
    success_count: int
    failure_count: int
    created_at: datetime
    last_used_at: datetime
    
    @property
    def confidence(self) -> float:
        """
        Calculate pattern confidence (0.0-1.0).

        Factors:
        1. Success rate (primary)
        2. Sample size (confidence in rate)
        3. Recency (penalize stale patterns)

        Returns:
            Confidence score between 0.0 and 1.0
        """
        total = self.success_count + self.failure_count
        if total == 0:
            return 0.5

        # Base confidence from success rate
        base_confidence = self.success_count / total

        # Sample size adjustment - penalize patterns with few uses
        if total < 10:
            sample_penalty = 0.1 * (1 - total / 10)
            base_confidence -= sample_penalty

        # Staleness penalty - penalize patterns not used recently
        from datetime import datetime
        days_since_use = (datetime.utcnow() - self.last_used_at).days
        if days_since_use > 30:
            staleness_penalty = min(0.3, 0.01 * (days_since_use - 30))
            base_confidence -= staleness_penalty

        # Ensure confidence stays in valid range
        return max(0.0, min(1.0, base_confidence))
