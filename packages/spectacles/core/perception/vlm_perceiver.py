"""
Spectacles VLM Perceiver
Vision-Language Model for visual understanding using Gemini 2.0 Flash

Handles 20% of perception tasks:
- Complex visual layouts
- Canvas elements
- CAPTCHA/visual challenges
- Shadow DOM content
- Error state detection
- Layout understanding when DOM parsing fails
"""

import io
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Lazy import for google.generativeai
_genai = None


def _get_genai():
    global _genai
    if _genai is None:
        import google.generativeai as genai
        _genai = genai
    return _genai


@dataclass
class VLMPerception:
    """Result of VLM-based page perception"""
    page_type: str  # login, form, dashboard, error, captcha, etc.
    elements: List[Dict[str, Any]]  # Detected interactive elements
    current_state: str  # Description of what's visible
    suggested_action: str  # What to do next
    blockers: List[str]  # Issues preventing progress
    confidence: float
    raw_response: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "page_type": self.page_type,
            "elements": self.elements,
            "current_state": self.current_state,
            "suggested_action": self.suggested_action,
            "blockers": self.blockers,
            "confidence": self.confidence,
        }


class VLMPerceiver:
    """
    Vision-Language Model for visual understanding.

    Uses Gemini 2.5 Flash for:
    - Element identification from screenshots
    - Error state detection
    - Visual layout understanding
    - CAPTCHA/visual challenge analysis
    - Form field detection when DOM fails

    Slower than DOM extraction but handles complex cases.
    """

    DEFAULT_MODEL = "gemini-2.5-flash"

    def __init__(
        self,
        api_key: str,
        model: Optional[str] = None,
        timeout_seconds: int = 30
    ):
        """
        Initialize VLM perceiver.

        Args:
            api_key: Google AI API key
            model: Model name (default: gemini-2.0-flash-exp)
            timeout_seconds: Request timeout
        """
        genai = _get_genai()
        genai.configure(api_key=api_key)

        self.model_name = model or self.DEFAULT_MODEL
        self.model = genai.GenerativeModel(self.model_name)
        self.timeout = timeout_seconds

        logger.info("VLMPerceiver initialized with model: %s", self.model_name)

    async def analyze(
        self,
        screenshot_bytes: bytes,
        goal: str,
        specific_query: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> VLMPerception:
        """
        Analyze page screenshot with VLM.

        Args:
            screenshot_bytes: Screenshot as bytes
            goal: Current task goal
            specific_query: Specific question about the page
            context: Additional context (previous actions, DOM info)

        Returns:
            VLMPerception with structured understanding
        """
        try:
            prompt = self._build_perception_prompt(goal, specific_query, context)

            # Prepare image
            image_part = {
                "mime_type": "image/png",
                "data": screenshot_bytes
            }

            # Generate response
            response = await self.model.generate_content_async(
                [prompt, image_part],
                generation_config={
                    "temperature": 0.1,  # Low for structured output
                    "max_output_tokens": 2048,
                }
            )

            # Parse response
            return self._parse_response(response.text)

        except Exception as e:
            logger.error("VLM analysis failed: %s", e)
            return VLMPerception(
                page_type="unknown",
                elements=[],
                current_state=f"VLM analysis failed: {str(e)}",
                suggested_action="Retry or fall back to DOM perception",
                blockers=[str(e)],
                confidence=0.0,
            )

    async def find_element(
        self,
        screenshot_bytes: bytes,
        element_description: str
    ) -> Optional[Dict[str, Any]]:
        """
        Find specific element in screenshot.

        Args:
            screenshot_bytes: Screenshot as bytes
            element_description: Description of element to find

        Returns:
            Element info with approximate location or None
        """
        try:
            prompt = f"""
            Look at this webpage screenshot and find the following element:
            "{element_description}"

            Return a JSON object with:
            {{
                "found": true/false,
                "element_type": "button/input/link/text/image",
                "location": "top-left/top-center/top-right/center-left/center/center-right/bottom-left/bottom-center/bottom-right",
                "text": "visible text on or near element",
                "confidence": 0.0-1.0,
                "notes": "any relevant observations"
            }}

            Return ONLY the JSON object, no other text.
            """

            image_part = {"mime_type": "image/png", "data": screenshot_bytes}

            response = await self.model.generate_content_async(
                [prompt, image_part],
                generation_config={"temperature": 0.1, "max_output_tokens": 512}
            )

            # Parse JSON response
            import json
            try:
                result = json.loads(response.text)
                if result.get("found"):
                    return result
            except json.JSONDecodeError:
                logger.warning("Failed to parse VLM element response")

            return None

        except Exception as e:
            logger.error("VLM element finding failed: %s", e)
            return None

    async def detect_captcha(
        self,
        screenshot_bytes: bytes
    ) -> Dict[str, Any]:
        """
        Detect CAPTCHA or visual verification challenges.

        Returns:
            Dict with captcha_detected, captcha_type, and handling suggestions
        """
        try:
            prompt = """
            Analyze this webpage screenshot for CAPTCHA or visual verification challenges.

            Return a JSON object with:
            {
                "captcha_detected": true/false,
                "captcha_type": "recaptcha/hcaptcha/image-selection/text/slider/none",
                "description": "brief description of the challenge",
                "solvable_by_automation": true/false,
                "requires_human": true/false,
                "suggested_approach": "how to handle this challenge"
            }

            Return ONLY the JSON object, no other text.
            """

            image_part = {"mime_type": "image/png", "data": screenshot_bytes}

            response = await self.model.generate_content_async(
                [prompt, image_part],
                generation_config={"temperature": 0.1, "max_output_tokens": 512}
            )

            import json
            try:
                return json.loads(response.text)
            except json.JSONDecodeError:
                return {
                    "captcha_detected": False,
                    "captcha_type": "unknown",
                    "error": "Failed to parse response"
                }

        except Exception as e:
            logger.error("CAPTCHA detection failed: %s", e)
            return {"captcha_detected": False, "error": str(e)}

    async def detect_error_state(
        self,
        screenshot_bytes: bytes
    ) -> Dict[str, Any]:
        """
        Detect error states in the page.

        Returns:
            Dict with error info and recovery suggestions
        """
        try:
            prompt = """
            Analyze this webpage screenshot for error states or problems.

            Return a JSON object with:
            {
                "has_error": true/false,
                "error_type": "form-validation/auth-failure/server-error/not-found/access-denied/none",
                "error_message": "visible error message if any",
                "severity": "blocking/warning/info",
                "recovery_suggestion": "what action to take"
            }

            Return ONLY the JSON object, no other text.
            """

            image_part = {"mime_type": "image/png", "data": screenshot_bytes}

            response = await self.model.generate_content_async(
                [prompt, image_part],
                generation_config={"temperature": 0.1, "max_output_tokens": 512}
            )

            import json
            try:
                return json.loads(response.text)
            except json.JSONDecodeError:
                return {"has_error": False, "error": "Failed to parse response"}

        except Exception as e:
            logger.error("Error detection failed: %s", e)
            return {"has_error": False, "error": str(e)}

    def _build_perception_prompt(
        self,
        goal: str,
        query: Optional[str],
        context: Optional[Dict[str, Any]]
    ) -> str:
        """Build structured perception prompt"""

        context_str = ""
        if context:
            context_str = f"\n\nContext from previous actions:\n{context}"

        query_str = ""
        if query:
            query_str = f"\n\nSpecific Question: {query}"

        return f"""
        Analyze this webpage screenshot for browser automation.

        Current Goal: {goal}
        {query_str}
        {context_str}

        Provide a JSON response with:
        {{
            "page_type": "login|form|dashboard|error|captcha|list|detail|search|unknown",
            "elements": [
                {{
                    "type": "button|input|link|dropdown|checkbox|radio",
                    "text": "visible text",
                    "location": "top-left|top-center|top-right|center-left|center|center-right|bottom-left|bottom-center|bottom-right",
                    "purpose": "what this element does",
                    "actionable": true/false
                }}
            ],
            "current_state": "description of what's visible on the page",
            "suggested_action": "what should be done next to achieve the goal",
            "blockers": ["list of issues preventing progress"],
            "confidence": 0.0-1.0
        }}

        Focus on:
        1. Interactive elements relevant to the goal
        2. Any error messages or warnings
        3. Form fields that need to be filled
        4. Navigation elements
        5. CAPTCHA or verification challenges

        Return ONLY the JSON object, no other text.
        """

    def _parse_response(self, response_text: str) -> VLMPerception:
        """Parse VLM response into structured perception"""
        import json

        try:
            # Try to extract JSON from response
            # Handle case where model adds markdown code blocks
            text = response_text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]

            data = json.loads(text)

            return VLMPerception(
                page_type=data.get("page_type", "unknown"),
                elements=data.get("elements", []),
                current_state=data.get("current_state", ""),
                suggested_action=data.get("suggested_action", ""),
                blockers=data.get("blockers", []),
                confidence=data.get("confidence", 0.5),
                raw_response=response_text,
            )

        except json.JSONDecodeError as e:
            logger.warning("Failed to parse VLM response as JSON: %s", e)
            return VLMPerception(
                page_type="unknown",
                elements=[],
                current_state=response_text[:500],
                suggested_action="Could not parse VLM response",
                blockers=["JSON parsing failed"],
                confidence=0.3,
                raw_response=response_text,
            )
