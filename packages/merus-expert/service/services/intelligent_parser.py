# @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""
Intelligent Parser - Gemini-powered entity extraction with fuzzy matching fallback.
Extracts multiple entities from a single natural-language user message.
"""

import os
import re
import json
import logging
from enum import Enum
from typing import Optional, Tuple
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class Intent(str, Enum):
    SUBMIT = "submit"
    PREVIEW = "preview"
    EDIT = "edit"
    CANCEL = "cancel"
    SKIP = "skip"
    DATA = "data"


class ParsedEntities(BaseModel):
    primary_party: Optional[str] = None
    case_type: Optional[str] = None
    case_type_confidence: float = 1.0
    attorney_responsible: Optional[str] = None
    office: Optional[str] = None
    venue_based_upon: Optional[str] = None
    client_email: Optional[str] = None
    client_phone: Optional[str] = None
    has_billing: Optional[bool] = None
    billing_amount_due: Optional[float] = None
    billing_description: Optional[str] = None
    initial_note: Optional[str] = None
    intent: Intent = Intent.DATA


class IntelligentParser:
    """
    Parses user messages to extract matter fields intelligently.

    Uses Gemini 2.5 Flash as primary extractor with rule-based + rapidfuzz fallback.
    Gracefully degrades when GOOGLE_API_KEY is not set.
    """

    def __init__(self):
        self.google_api_key = os.getenv("GOOGLE_API_KEY")
        self.model = None
        if self.google_api_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.google_api_key)
                self.model = genai.GenerativeModel("gemini-2.5-flash")
                logger.info("IntelligentParser: Gemini 2.5 Flash initialized")
            except ImportError:
                logger.warning("IntelligentParser: google-generativeai not installed, using rule-based fallback")
            except Exception as e:
                logger.warning(f"IntelligentParser: Failed to initialize Gemini: {e}")
        else:
            logger.info("IntelligentParser: No GOOGLE_API_KEY found, using rule-based fallback")

    async def extract_entities(self, text: str, collected_so_far: dict) -> ParsedEntities:
        """
        Extract entities from user message.

        Tries Gemini first, falls back to rule-based extraction.

        Args:
            text: User message text
            collected_so_far: Already-collected fields (to avoid re-extracting)

        Returns:
            ParsedEntities with all extractable fields populated
        """
        if self.model:
            return await self._gemini_extract(text, collected_so_far)
        return self._rule_based_extract(text)

    async def _gemini_extract(self, text: str, collected_so_far: dict) -> ParsedEntities:
        """Use Gemini to extract entities from user message."""
        prompt = f"""Extract legal matter fields from this user message. Return ONLY a JSON object.
Fields to extract (use null if not present):
- primary_party: client/party name (string or null)
- case_type: one of "Immigration", "Workers\'  Compensation", "Family Law", "Personal Injury", "General" (or null)
- attorney_responsible: attorney name (string or null)
- office: office name (string or null)
- venue_based_upon: venue/jurisdiction (string or null)
- client_email: email address (string or null)
- client_phone: phone number (string or null)
- billing_amount_due: numeric amount (number or null)
- billing_description: billing description (string or null)
- initial_note: case note (string or null)
- intent: one of "data", "submit", "preview", "edit", "cancel", "skip"

Be strict - only extract fields explicitly stated. Do not infer.
User message: "{text}"
Already collected: {collected_so_far}
Return JSON only, no explanation."""
        try:
            response = await self.model.generate_content_async(prompt)
            json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                # Only include valid fields that have values
                valid_data = {
                    k: v for k, v in data.items()
                    if v is not None and k in ParsedEntities.model_fields
                }
                return ParsedEntities(**valid_data)
        except Exception as e:
            logger.warning(f"Gemini extraction failed, falling back to rule-based: {e}")
        return self._rule_based_extract(text)

    def _rule_based_extract(self, text: str) -> ParsedEntities:
        """
        Rule-based entity extraction fallback.

        Handles intent detection and case type fuzzy matching without Gemini.
        """
        entities = ParsedEntities()
        entities.intent = self.detect_intent(text)

        # Try fuzzy case type match
        ct, conf = self.fuzzy_match_case_type(text)
        if ct:
            entities.case_type = ct
            entities.case_type_confidence = conf

        # Simple email detection
        email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        email_match = re.search(email_pattern, text)
        if email_match:
            entities.client_email = email_match.group().lower()

        # Simple phone detection
        phone_pattern = r'\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}'
        phone_match = re.search(phone_pattern, text)
        if phone_match:
            digits = re.sub(r'\D', '', phone_match.group())
            if len(digits) == 10:
                entities.client_phone = f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"

        # Simple dollar amount detection
        amount_pattern = r'\$?([\d,]+(?:\.\d{2})?)\s*(?:dollars?)?'
        amount_match = re.search(amount_pattern, text)
        if amount_match:
            try:
                amount = float(amount_match.group(1).replace(',', ''))
                if amount > 0:
                    entities.billing_amount_due = amount
            except ValueError:
                pass

        return entities

    def fuzzy_match_case_type(self, text: str) -> Tuple[Optional[str], float]:
        """
        Fuzzy match text against case type aliases.

        Uses rapidfuzz if available, falls back to simple string matching.

        Args:
            text: User input text

        Returns:
            Tuple of (case_type_string, confidence_score) or (None, 0.0)
        """
        choices = {
            "Workers' Compensation": ["workers comp", "wc", "workers compensation", "workmans comp", "workcomp", "work comp"],
            "Personal Injury": ["personal injury", "pi", "injury", "accident"],
            "Family Law": ["family law", "family", "divorce", "custody", "fl"],
            "Immigration": ["immigration", "imm", "visa", "deportation", "asylum"],
            "General": ["general", "gen", "other", "misc"],
        }

        text_lower = text.lower().strip()

        try:
            from rapidfuzz import fuzz
            best_score = 0.0
            best_type = None
            for case_type, aliases in choices.items():
                for alias in aliases:
                    score = fuzz.WRatio(text_lower, alias) / 100.0
                    if score > best_score:
                        best_score = score
                        best_type = case_type
            if best_score >= 0.6:
                return best_type, best_score
        except ImportError:
            # Fallback without rapidfuzz - exact/substring matching
            for case_type, aliases in choices.items():
                for alias in aliases:
                    if text_lower == alias or alias in text_lower or text_lower in alias:
                        return case_type, 1.0

        return None, 0.0

    def detect_intent(self, text: str) -> Intent:
        """
        Detect user intent from message text.

        Args:
            text: User message

        Returns:
            Intent enum value
        """
        lower = text.lower().strip()
        if any(w in lower for w in ["submit", "create", "save", "yes, submit", "go ahead"]):
            return Intent.SUBMIT
        if any(w in lower for w in ["preview", "dry run", "dry-run", "test run"]):
            return Intent.PREVIEW
        if any(w in lower for w in ["edit", "change", "modify", "go back", "back"]):
            return Intent.EDIT
        if any(w in lower for w in ["cancel", "quit", "exit", "stop", "nevermind"]):
            return Intent.CANCEL
        if lower == "skip":
            return Intent.SKIP
        return Intent.DATA
