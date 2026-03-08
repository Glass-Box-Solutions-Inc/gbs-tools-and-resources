"""
Spectacles Desktop Perceiver
Vision-Language Model + OCR for native desktop application understanding

Uses:
- Gemini 2.5 Flash for visual understanding (element location, layout)
- EasyOCR for text extraction from screenshots
- Combined approach for comprehensive desktop perception
"""

import io
import logging
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Lazy imports
_genai = None
_easyocr = None


def _get_genai():
    global _genai
    if _genai is None:
        import google.generativeai as genai
        _genai = genai
    return _genai


def _get_easyocr():
    global _easyocr
    if _easyocr is None:
        import easyocr
        _easyocr = easyocr
    return _easyocr


@dataclass
class OCRResult:
    """Result of OCR text extraction"""
    text: str
    bounds: Tuple[int, int, int, int]  # (x, y, width, height)
    confidence: float
    center: Tuple[int, int]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "bounds": self.bounds,
            "confidence": self.confidence,
            "center": self.center
        }


@dataclass
class DesktopElement:
    """Detected element on desktop"""
    element_type: str  # button, input, menu, icon, text, etc.
    text: str
    description: str
    bounds: Tuple[int, int, int, int]  # (x, y, width, height)
    center: Tuple[int, int]
    confidence: float
    source: str  # "ocr", "vlm", "both"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.element_type,
            "text": self.text,
            "description": self.description,
            "bounds": self.bounds,
            "center": self.center,
            "confidence": self.confidence,
            "source": self.source
        }


@dataclass
class DesktopPerception:
    """Result of desktop perception"""
    application_type: str  # office, browser, ide, file_manager, etc.
    window_title: str
    elements: List[DesktopElement]
    ocr_results: List[OCRResult]
    current_state: str
    suggested_action: str
    blockers: List[str]
    confidence: float
    screenshot_path: Optional[str] = None
    raw_vlm_response: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "application_type": self.application_type,
            "window_title": self.window_title,
            "elements": [e.to_dict() for e in self.elements],
            "ocr_results": [o.to_dict() for o in self.ocr_results],
            "current_state": self.current_state,
            "suggested_action": self.suggested_action,
            "blockers": self.blockers,
            "confidence": self.confidence,
        }


class DesktopPerceiver:
    """
    Desktop Perceiver for native application understanding.

    Combines:
    - EasyOCR for text extraction
    - Gemini VLM for visual element detection and layout understanding

    Slower than browser DOM extraction but necessary for native apps.
    """

    DEFAULT_MODEL = "gemini-2.0-flash-exp"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        languages: List[str] = None,
        timeout_seconds: int = 30
    ):
        """
        Initialize desktop perceiver.

        Args:
            api_key: Google AI API key (from env if not provided)
            model: VLM model name
            languages: OCR languages (default: ["en"])
            timeout_seconds: Request timeout
        """
        import os

        self.api_key = api_key or os.environ.get("GOOGLE_AI_API_KEY")
        self.model_name = model or self.DEFAULT_MODEL
        self.languages = languages or ["en"]
        self.timeout = timeout_seconds

        # Lazy-loaded components
        self._vlm_model = None
        self._ocr_reader = None

        logger.info(
            "DesktopPerceiver initialized (model=%s, languages=%s)",
            self.model_name, self.languages
        )

    @property
    def vlm_model(self):
        """Lazy-load VLM model"""
        if self._vlm_model is None and self.api_key:
            genai = _get_genai()
            genai.configure(api_key=self.api_key)
            self._vlm_model = genai.GenerativeModel(self.model_name)
        return self._vlm_model

    @property
    def ocr_reader(self):
        """Lazy-load OCR reader"""
        if self._ocr_reader is None:
            easyocr = _get_easyocr()
            self._ocr_reader = easyocr.Reader(self.languages, gpu=False)
        return self._ocr_reader

    async def perceive(
        self,
        screenshot_path: str,
        goal: str,
        use_ocr: bool = True,
        use_vlm: bool = True,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Perceive desktop screenshot.

        Args:
            screenshot_path: Path to screenshot image
            goal: What we're trying to find/understand
            use_ocr: Enable OCR text extraction
            use_vlm: Enable VLM visual analysis
            context: Additional context

        Returns:
            Perception results dict
        """
        import asyncio

        results = {
            "elements": [],
            "ocr_results": [],
            "current_state": "",
            "suggested_action": "",
            "blockers": [],
            "confidence": 0.0
        }

        try:
            # Read screenshot
            with open(screenshot_path, "rb") as f:
                screenshot_bytes = f.read()

            tasks = []

            # Run OCR if enabled
            if use_ocr:
                tasks.append(self._extract_ocr(screenshot_path))

            # Run VLM if enabled and API key available
            if use_vlm and self.vlm_model:
                tasks.append(self._analyze_vlm(screenshot_bytes, goal, context))

            # Execute concurrently
            if tasks:
                completed = await asyncio.gather(*tasks, return_exceptions=True)

                for i, result in enumerate(completed):
                    if isinstance(result, Exception):
                        logger.error("Perception task failed: %s", result)
                        continue

                    if use_ocr and i == 0:
                        results["ocr_results"] = result
                        # Convert OCR results to elements
                        for ocr in result:
                            results["elements"].append({
                                "type": "text",
                                "text": ocr.text,
                                "description": ocr.text,
                                "bounds": ocr.bounds,
                                "center": ocr.center,
                                "confidence": ocr.confidence,
                                "source": "ocr"
                            })
                    elif use_vlm and (i == 1 or (not use_ocr and i == 0)):
                        # Merge VLM results
                        results["current_state"] = result.get("current_state", "")
                        results["suggested_action"] = result.get("suggested_action", "")
                        results["blockers"] = result.get("blockers", [])
                        results["confidence"] = result.get("confidence", 0.0)
                        results["application_type"] = result.get("application_type", "unknown")

                        # Add VLM-detected elements
                        for elem in result.get("elements", []):
                            elem["source"] = "vlm"
                            results["elements"].append(elem)

            # Calculate overall confidence
            if results["elements"]:
                avg_conf = sum(e.get("confidence", 0) for e in results["elements"]) / len(results["elements"])
                results["confidence"] = max(results["confidence"], avg_conf)

        except Exception as e:
            logger.error("Desktop perception failed: %s", e)
            results["error"] = str(e)

        return results

    async def _extract_ocr(self, screenshot_path: str) -> List[OCRResult]:
        """
        Extract text using OCR.

        Args:
            screenshot_path: Path to screenshot

        Returns:
            List of OCR results
        """
        import asyncio

        loop = asyncio.get_event_loop()

        def _run_ocr():
            results = []
            try:
                # EasyOCR returns: [[bbox, text, confidence], ...]
                ocr_output = self.ocr_reader.readtext(screenshot_path)

                for item in ocr_output:
                    bbox, text, confidence = item

                    # EasyOCR bbox is [[x1,y1], [x2,y1], [x2,y2], [x1,y2]]
                    x1, y1 = int(bbox[0][0]), int(bbox[0][1])
                    x2, y2 = int(bbox[2][0]), int(bbox[2][1])

                    width = x2 - x1
                    height = y2 - y1
                    center_x = x1 + width // 2
                    center_y = y1 + height // 2

                    results.append(OCRResult(
                        text=text,
                        bounds=(x1, y1, width, height),
                        confidence=float(confidence),
                        center=(center_x, center_y)
                    ))

            except Exception as e:
                logger.error("OCR extraction failed: %s", e)

            return results

        return await loop.run_in_executor(None, _run_ocr)

    async def _analyze_vlm(
        self,
        screenshot_bytes: bytes,
        goal: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Analyze screenshot using VLM.

        Args:
            screenshot_bytes: Screenshot image bytes
            goal: What we're looking for
            context: Additional context

        Returns:
            VLM analysis results
        """
        import asyncio
        from PIL import Image

        loop = asyncio.get_event_loop()

        def _run_vlm():
            try:
                # Create PIL Image from bytes
                image = Image.open(io.BytesIO(screenshot_bytes))

                # Build prompt
                prompt = self._build_vlm_prompt(goal, context)

                # Call VLM
                response = self.vlm_model.generate_content(
                    [prompt, image],
                    generation_config={
                        "temperature": 0.1,
                        "max_output_tokens": 2048,
                    }
                )

                # Parse response
                return self._parse_vlm_response(response.text, goal)

            except Exception as e:
                logger.error("VLM analysis failed: %s", e)
                return {
                    "elements": [],
                    "current_state": f"VLM analysis failed: {e}",
                    "suggested_action": "Retry or use OCR only",
                    "blockers": [str(e)],
                    "confidence": 0.0
                }

        return await loop.run_in_executor(None, _run_vlm)

    def _build_vlm_prompt(self, goal: str, context: Optional[Dict[str, Any]] = None) -> str:
        """Build VLM analysis prompt"""
        context_str = ""
        if context:
            context_str = f"\nContext: {context}"

        return f"""Analyze this desktop screenshot to help achieve the goal: {goal}
{context_str}

Identify and describe:
1. APPLICATION TYPE: What type of application is shown (office, browser, IDE, file manager, terminal, etc.)
2. WINDOW TITLE: The title of the active window
3. INTERACTIVE ELEMENTS: List clickable buttons, menu items, input fields, icons with:
   - Type (button, menu, input, icon, checkbox, dropdown, etc.)
   - Text or label
   - Approximate position as percentage of screen (e.g., "top-left", "center", "30% from left, 50% from top")
   - Confidence (0-1)
4. CURRENT STATE: What is currently visible/happening
5. SUGGESTED ACTION: What action would help achieve the goal
6. BLOCKERS: Any issues preventing progress (dialogs, errors, loading states)

Format as JSON:
{{
    "application_type": "string",
    "window_title": "string",
    "elements": [
        {{
            "type": "button|menu|input|icon|checkbox|dropdown|text",
            "text": "visible text",
            "description": "what this element does",
            "position": "description of position",
            "position_percent": [x_percent, y_percent],
            "confidence": 0.0-1.0
        }}
    ],
    "current_state": "description of what's visible",
    "suggested_action": "what to do next",
    "blockers": ["list of issues"]
}}"""

    def _parse_vlm_response(self, response_text: str, goal: str) -> Dict[str, Any]:
        """Parse VLM response into structured data"""
        import json
        import re

        result = {
            "application_type": "unknown",
            "window_title": "",
            "elements": [],
            "current_state": "",
            "suggested_action": "",
            "blockers": [],
            "confidence": 0.5,
            "raw_response": response_text
        }

        try:
            # Extract JSON from response
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                parsed = json.loads(json_match.group())

                result["application_type"] = parsed.get("application_type", "unknown")
                result["window_title"] = parsed.get("window_title", "")
                result["current_state"] = parsed.get("current_state", "")
                result["suggested_action"] = parsed.get("suggested_action", "")
                result["blockers"] = parsed.get("blockers", [])

                # Process elements
                for elem in parsed.get("elements", []):
                    # Convert position_percent to approximate pixel coordinates
                    # Assuming standard 1920x1080 screen for now
                    screen_width, screen_height = 1920, 1080
                    pos_percent = elem.get("position_percent", [50, 50])

                    if isinstance(pos_percent, list) and len(pos_percent) >= 2:
                        x = int(screen_width * pos_percent[0] / 100)
                        y = int(screen_height * pos_percent[1] / 100)
                    else:
                        x, y = screen_width // 2, screen_height // 2

                    result["elements"].append({
                        "type": elem.get("type", "unknown"),
                        "text": elem.get("text", ""),
                        "description": elem.get("description", elem.get("text", "")),
                        "bounds": (x - 50, y - 20, 100, 40),  # Approximate bounds
                        "center": (x, y),
                        "confidence": elem.get("confidence", 0.7),
                        "position_description": elem.get("position", "")
                    })

                # Calculate confidence based on element count
                if result["elements"]:
                    result["confidence"] = 0.7 + (0.3 * min(len(result["elements"]) / 10, 1.0))
                else:
                    result["confidence"] = 0.3

        except json.JSONDecodeError as e:
            logger.warning("Failed to parse VLM JSON response: %s", e)
            # Fall back to text parsing
            result["current_state"] = response_text[:500]

        return result

    async def find_element_by_text(
        self,
        screenshot_path: str,
        text_to_find: str,
        fuzzy: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        Find element containing specific text.

        Args:
            screenshot_path: Path to screenshot
            text_to_find: Text to search for
            fuzzy: Allow partial/fuzzy matching

        Returns:
            Element dict if found, None otherwise
        """
        # Use OCR to find text
        ocr_results = await self._extract_ocr(screenshot_path)

        text_lower = text_to_find.lower()

        for result in ocr_results:
            result_text = result.text.lower()

            if fuzzy:
                if text_lower in result_text or result_text in text_lower:
                    return {
                        "type": "text",
                        "text": result.text,
                        "bounds": result.bounds,
                        "center": result.center,
                        "confidence": result.confidence,
                        "source": "ocr"
                    }
            else:
                if result_text == text_lower:
                    return {
                        "type": "text",
                        "text": result.text,
                        "bounds": result.bounds,
                        "center": result.center,
                        "confidence": result.confidence,
                        "source": "ocr"
                    }

        return None

    async def get_all_text(self, screenshot_path: str) -> str:
        """
        Extract all visible text from screenshot.

        Args:
            screenshot_path: Path to screenshot

        Returns:
            Concatenated text from all OCR results
        """
        ocr_results = await self._extract_ocr(screenshot_path)
        return " ".join(r.text for r in ocr_results)

    async def is_error_state(
        self,
        screenshot_path: str,
        error_keywords: List[str] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if screenshot shows an error state.

        Args:
            screenshot_path: Path to screenshot
            error_keywords: Keywords indicating errors

        Returns:
            Tuple of (is_error, error_message)
        """
        default_keywords = [
            "error", "failed", "failure", "exception",
            "not found", "invalid", "access denied",
            "permission denied", "cannot", "unable"
        ]
        keywords = error_keywords or default_keywords

        all_text = await self.get_all_text(screenshot_path)
        text_lower = all_text.lower()

        for keyword in keywords:
            if keyword.lower() in text_lower:
                # Extract surrounding context
                idx = text_lower.find(keyword.lower())
                start = max(0, idx - 50)
                end = min(len(all_text), idx + len(keyword) + 50)
                context = all_text[start:end]
                return True, context

        return False, None
