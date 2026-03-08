"""
Spectacles Intent Classifier
Determines user intent from Slack messages using pattern matching and AI fallback

Intent Types:
- STATUS_QUERY: Check task status
- COMMAND: Execute task command (pause, cancel, resume, list)
- QUESTION: General question about project/system
- CHANNEL_CREATE: Request to create a new project channel
- ESCALATE: Complex/ambiguous query requiring human review
"""

import re
import logging
from enum import Enum
from typing import Optional, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class Intent(str, Enum):
    """User intent types"""
    STATUS_QUERY = "status_query"
    COMMAND = "command"
    QUESTION = "question"
    CHANNEL_CREATE = "channel_create"
    ESCALATE = "escalate"
    HELP = "help"


@dataclass
class ClassificationResult:
    """Result of intent classification"""
    intent: Intent
    confidence: float
    extracted_data: Dict[str, Any]
    reasoning: Optional[str] = None


class IntentClassifier:
    """
    Classifies user intent from Slack messages.

    Uses pattern matching (fast, 90% accuracy) with optional AI fallback.
    """

    # Regex patterns for intent detection
    PATTERNS = {
        Intent.HELP: [
            # Core help requests
            r'\bhelp\b',
            r'\bcommands?\b',

            # What can you do variations
            r'\bwhat can (you|spectacles|this|the bot) do\b',
            r'\bwhat (can|could|do) (i|we) do\b',

            # How to use (Spectacles itself)
            r'\bhow (do|can) (i|we|you) (use|start|work with)\b',
            r'\bhow to (use|work|start|get started)',
            r'\bhow does (this|spectacles) work\b',

            # Show/list variations
            r'\b(show|list|tell) (me )?(the )?(commands?|options?|what you can do)\b',
            r'\bavailable (commands?|actions?|options?)\b',

            # Contractions and natural language
            r'\bwhat\'?s (available|possible)\b',
            r'\bi need help\b',
            r'\bhelp me( out| get started)?\b',
        ],
        Intent.STATUS_QUERY: [
            # Specific task status queries
            r'status\s+(of\s+)?task[\s-]?\d+',
            r'task[\s-]?\d+\s+status',

            # Command-style status requests (no question words)
            r'^\s*(show|check|get|display) status\b',
            r'^\s*status\b',
            r'^\s*(current )?progress\b',

            # Status-related but not question-style
            r'\bprogress\s+(of|on) task',
        ],
        Intent.COMMAND: [
            r'^(pause|cancel|resume|stop|kill)\s+task',
            r'^list\s+(tasks|active)',
            r'^task[\s-]?\d+\s+(pause|cancel|resume)',
        ],
        Intent.CHANNEL_CREATE: [
            r'create\s+(a\s+)?channel',
            r'new\s+(project\s+)?channel',
            r'set\s?up\s+(a\s+)?channel',
        ],
        Intent.QUESTION: [
            # Status/progress questions (with contractions) - specific objects
            r'\bwhat\'?s (the |your |my )?(current )?(status|progress|result|task|url|screenshot|error|issue)',
            r'\bhow\'?s (the|my|your|it|that)',
            r'\bwhere\'?s (the|my|your|it)',
            r'\bwhen\'?s (the|my|your|it) ',

            # General what questions - various forms
            r'\bwhat (is|are|was|were) (the|this|that|a|an)',
            r'\bwhy (is|are|was|were|did) (it|the|this|that)',

            # How questions about specific things (not general "how to use")
            # Exclude "how do i/we" (usage questions go to HELP)
            # Exclude "how does this/spectacles work" (capability questions go to HELP)
            r'\bhow (does|did) (the|that|it) (fail|break|happen)',

            # Questions about events/happenings
            r'\bwhat (happened|went wrong|failed|broke)',
            r'\bwhen (did|was|will) ',
            r'\bwhere (is|are|was|did) ',

            # Information requests (not about capabilities/commands/options)
            r'\btell me (about |the )?(status|progress|result|error|project|task)',
            r'\btell me about (the|this|that)',
            r'\bexplain (what happened|the|this|that)',
            r'\bshow me what (happened|failed|you found)',
            r'\bshow me (the|your|my) (status|result|error|screenshot)',

            # Can/could/would/should questions
            r'\b(can|could|would|should) (you|i|we) (help|tell|show|explain)',

            # Do/does questions
            r'\bdo you (know|have|think)',
            r'\bdoes (it|this|that|the) ',
            r'\bdo (I|we) ',

            # Is/are questions
            r'\bis (this|that|it|the) ',
            r'\bare (these|those|they|the) ',
        ],
    }

    # Task ID extraction pattern
    TASK_ID_PATTERN = re.compile(r'task[\s-]?(\d+)', re.IGNORECASE)

    def __init__(self, use_ai_fallback: bool = False, ai_confidence_threshold: float = 0.6):
        """
        Initialize intent classifier.

        Args:
            use_ai_fallback: Enable Gemini fallback for ambiguous cases
            ai_confidence_threshold: Minimum confidence for AI classification
        """
        self.use_ai_fallback = use_ai_fallback
        self.ai_confidence_threshold = ai_confidence_threshold

        # Compile patterns
        self.compiled_patterns = {
            intent: [re.compile(pattern, re.IGNORECASE) for pattern in patterns]
            for intent, patterns in self.PATTERNS.items()
        }

        logger.info("IntentClassifier initialized (AI fallback: %s)", use_ai_fallback)

    def classify(self, message: str, context: Optional[Dict[str, Any]] = None) -> ClassificationResult:
        """
        Classify user intent from message.

        Args:
            message: Message text
            context: Optional context (channel_id, user_id, thread_ts)

        Returns:
            ClassificationResult with intent and confidence
        """
        message = message.strip()

        # Empty message
        if not message:
            return ClassificationResult(
                intent=Intent.HELP,
                confidence=0.9,
                extracted_data={},
                reasoning="Empty message - showing help"
            )

        # Try pattern matching first (fast path)
        result = self._classify_with_patterns(message, context)

        # If confidence is high enough, return immediately
        if result.confidence >= 0.7:
            return result

        # If low confidence and AI fallback enabled, use Gemini
        if self.use_ai_fallback and result.confidence < self.ai_confidence_threshold:
            logger.info("Low confidence (%.2f), using AI fallback", result.confidence)
            ai_result = self._classify_with_ai(message, context)
            if ai_result.confidence > result.confidence:
                return ai_result

        return result

    def _classify_with_patterns(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None
    ) -> ClassificationResult:
        """
        Classify using regex pattern matching.

        Args:
            message: Message text
            context: Optional context

        Returns:
            ClassificationResult
        """
        message_lower = message.lower()

        # Track matches
        matches = []

        for intent, patterns in self.compiled_patterns.items():
            for pattern in patterns:
                if pattern.search(message_lower):
                    matches.append(intent)
                    break  # Only count each intent once

        # Extract task ID if present
        task_id_match = self.TASK_ID_PATTERN.search(message)
        task_id = task_id_match.group(1) if task_id_match else None

        extracted_data = {}
        if task_id:
            extracted_data['task_id'] = f"task-{task_id}"

        # No matches - check if it's a question
        if not matches:
            # Check if message ends with question mark
            if message.strip().endswith('?'):
                return ClassificationResult(
                    intent=Intent.QUESTION,
                    confidence=0.75,  # Stronger signal that ? = question
                    extracted_data=extracted_data,
                    reasoning="Message ends with question mark"
                )

            # Default to escalate for unknown patterns
            return ClassificationResult(
                intent=Intent.ESCALATE,
                confidence=0.5,
                extracted_data=extracted_data,
                reasoning="No clear pattern match"
            )

        # Single match - high confidence
        if len(matches) == 1:
            intent = matches[0]

            # For commands, extract command type
            if intent == Intent.COMMAND:
                command = self._extract_command(message_lower)
                if command:
                    extracted_data['command'] = command

            # For channel creation, extract project name
            if intent == Intent.CHANNEL_CREATE:
                project_name = self._extract_project_name(message)
                if project_name:
                    extracted_data['project_name'] = project_name

            return ClassificationResult(
                intent=intent,
                confidence=0.9,
                extracted_data=extracted_data,
                reasoning=f"Clear match for {intent.value}"
            )

        # Multiple matches - lower confidence, pick most specific
        # Priority: COMMAND > CHANNEL_CREATE > HELP > QUESTION > STATUS_QUERY
        # HELP beats QUESTION for capability questions
        # QUESTION beats STATUS_QUERY for question-style queries
        priority_order = [
            Intent.COMMAND,
            Intent.CHANNEL_CREATE,
            Intent.HELP,           # Higher than QUESTION for capability questions
            Intent.QUESTION,       # Higher than STATUS_QUERY for question-style
            Intent.STATUS_QUERY,
        ]

        for intent in priority_order:
            if intent in matches:
                return ClassificationResult(
                    intent=intent,
                    confidence=0.7,
                    extracted_data=extracted_data,
                    reasoning=f"Multiple matches, picked {intent.value} by priority"
                )

        # Fallback
        return ClassificationResult(
            intent=Intent.ESCALATE,
            confidence=0.5,
            extracted_data=extracted_data,
            reasoning="Ambiguous intent"
        )

    def _extract_command(self, message: str) -> Optional[str]:
        """
        Extract command from message.

        Args:
            message: Message text (lowercase)

        Returns:
            Command name or None
        """
        command_patterns = {
            'status': r'\bstatus\b',
            'pause': r'\bpause\b',
            'cancel': r'\b(cancel|stop|kill)\b',
            'resume': r'\bresume\b',
            'list': r'\blist\b',
        }

        for command, pattern in command_patterns.items():
            if re.search(pattern, message):
                return command

        return None

    def _extract_project_name(self, message: str) -> Optional[str]:
        """
        Extract project name from channel creation request.

        Args:
            message: Message text

        Returns:
            Project name or None
        """
        # Try patterns like "create channel for X" or "new channel: X"
        patterns = [
            r'channel\s+for\s+([a-z0-9-]+)',
            r'channel[:\s]+([a-z0-9-]+)',
            r'project\s+([a-z0-9-]+)',
        ]

        for pattern in patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                return match.group(1).lower()

        return None

    def _classify_with_ai(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None
    ) -> ClassificationResult:
        """
        Classify using Gemini AI (fallback for ambiguous cases).

        Args:
            message: Message text
            context: Optional context

        Returns:
            ClassificationResult
        """
        # TODO: Implement Gemini classification
        # For now, return escalate with low confidence
        logger.warning("AI classification not yet implemented")
        return ClassificationResult(
            intent=Intent.ESCALATE,
            confidence=0.4,
            extracted_data={},
            reasoning="AI classification not available"
        )


# Singleton instance (optional, for convenience)
_classifier = None


def get_classifier(use_ai_fallback: bool = False) -> IntentClassifier:
    """Get singleton classifier instance"""
    global _classifier
    if _classifier is None:
        _classifier = IntentClassifier(use_ai_fallback=use_ai_fallback)
    return _classifier
