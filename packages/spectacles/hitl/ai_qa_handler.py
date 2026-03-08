"""
Spectacles AI Q&A Handler
Answers user questions using Gemini 2.0 Flash with project context

Features:
- Project-aware question answering
- Context building from channel history and tasks
- Confidence-based escalation
- PII filtering
"""

import logging
import re
from typing import Optional, Dict, Any
from datetime import datetime

try:
    import google.generativeai as genai
except ImportError:
    genai = None

logger = logging.getLogger(__name__)


class AIQAHandler:
    """
    AI-powered Q&A handler using Gemini 2.0 Flash.
    
    Answers questions about:
    - Task status and progress
    - Project context and history
    - System capabilities
    - General help
    
    Escalates to human when:
    - Confidence < 0.6
    - Billing/pricing/account questions
    - User requests escalation
    - Timeout (>10s)
    """
    
    # Keywords that trigger automatic escalation
    ESCALATION_KEYWORDS = [
        'billing', 'payment', 'cost', 'price', 'invoice', 'account',
        'talk to human', 'speak to human', 'escalate', 'real person'
    ]
    
    # PII patterns for filtering logs
    PII_PATTERNS = {
        'email': re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
        'phone': re.compile(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b'),
        'ssn': re.compile(r'\b\d{3}-\d{2}-\d{4}\b'),
        'credit_card': re.compile(r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b'),
    }
    
    def __init__(
        self,
        gemini_api_key: str,
        context_manager,
        task_store=None,
        human_router=None,
        confidence_threshold: float = 0.6,
        timeout_seconds: int = 10
    ):
        """
        Initialize AI Q&A handler.
        
        Args:
            gemini_api_key: Google AI API key
            context_manager: ChannelContextManager for project context
            task_store: TaskStore for task queries
            human_router: HumanRouter for escalation
            confidence_threshold: Minimum confidence for direct answer
            timeout_seconds: Max time for AI response
        """
        self.api_key = gemini_api_key
        self.context_manager = context_manager
        self.task_store = task_store
        self.human_router = human_router
        self.confidence_threshold = confidence_threshold
        self.timeout_seconds = timeout_seconds

        # Initialize Gemini client
        try:
            if genai is None:
                raise ImportError("google-generativeai not installed")
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel('gemini-2.5-flash')
            logger.info("AIQAHandler initialized with Gemini 2.5 Flash")
        except Exception as e:
            logger.error("Failed to initialize Gemini: %s", e)
            self.model = None
    
    async def answer_question(
        self,
        question: str,
        user_id: str,
        channel_id: Optional[str] = None,
        project_name: Optional[str] = None
    ) -> str:
        """
        Answer user question with project context.
        
        Args:
            question: User's question
            user_id: Slack user ID
            channel_id: Slack channel ID (for context)
            project_name: Project name (if known)
        
        Returns:
            Answer string (or escalation message)
        """
        # Check for automatic escalation keywords
        if self._should_auto_escalate(question):
            logger.info("Auto-escalating question with billing/account keywords")
            return await self._escalate_to_human(
                question, user_id, channel_id, project_name,
                reason="Question contains billing/account keywords"
            )
        
        # Build context
        context = self._build_context(channel_id, project_name)
        
        # Generate AI response
        try:
            response, confidence = await self._generate_response(question, context)
            
            # Check if should escalate based on confidence
            if self._should_escalate(response, confidence):
                logger.info(
                    "Escalating low-confidence answer (%.2f < %.2f)",
                    confidence, self.confidence_threshold
                )
                return await self._escalate_to_human(
                    question, user_id, channel_id, project_name,
                    ai_response=response, confidence=confidence
                )
            
            # Return AI answer
            logger.info("Answered question with confidence %.2f", confidence)
            return response
            
        except Exception as e:
            logger.error("Error generating AI response: %s", e)
            return await self._escalate_to_human(
                question, user_id, channel_id, project_name,
                reason=f"AI error: {str(e)}"
            )
    
    def _build_context(
        self,
        channel_id: Optional[str],
        project_name: Optional[str]
    ) -> Dict[str, Any]:
        """
        Build context from channel and project information.
        
        Args:
            channel_id: Slack channel ID
            project_name: Project name
        
        Returns:
            Context dict with project info, tasks, messages
        """
        context = {
            'project_name': project_name or 'unknown',
            'project_description': '',
            'active_tasks': [],
            'recent_messages': [],
            'task_history': []
        }
        
        # Get channel context if available
        if channel_id and self.context_manager:
            channel_context = self.context_manager.get_channel_context(
                channel_id,
                task_store=self.task_store
            )
            
            if channel_context:
                context['project_name'] = channel_context.project_name
                context['project_description'] = channel_context.description
                context['active_tasks'] = channel_context.active_tasks
                context['recent_messages'] = channel_context.recent_messages[:20]
        
        # Get active tasks from task store
        if self.task_store and project_name:
            try:
                from persistence.utils import get_db_connection
                with get_db_connection(self.task_store.db_path) as conn:
                    cursor = conn.execute("""
                        SELECT task_id, goal, current_state, created_at
                        FROM tasks
                        WHERE current_state NOT IN ('COMPLETED', 'FAILED', 'CANCELLED')
                        ORDER BY created_at DESC
                        LIMIT 10
                    """)
                    rows = cursor.fetchall()
                    
                    context['active_tasks'] = [
                        {
                            'task_id': row[0],
                            'goal': row[1],
                            'state': row[2],
                            'created_at': row[3]
                        }
                        for row in rows
                    ]
            except Exception as e:
                logger.warning("Failed to get active tasks: %s", e)
        
        return context
    
    async def _generate_response(
        self,
        question: str,
        context: Dict[str, Any]
    ) -> tuple[str, float]:
        """
        Generate AI response using Gemini.
        
        Args:
            question: User's question
            context: Project context
        
        Returns:
            Tuple of (response_text, confidence_score)
        """
        if not self.model:
            return "AI service is not available. Please contact support.", 0.0
        
        # Build prompt with context
        prompt = self._build_prompt(question, context)
        
        # Filter PII from prompt before logging
        safe_prompt = self._filter_pii(prompt)
        logger.debug("Generated prompt (PII filtered): %s", safe_prompt[:200])
        
        try:
            # Generate response with timeout
            import asyncio
            response = await asyncio.wait_for(
                self._call_gemini(prompt),
                timeout=self.timeout_seconds
            )
            
            # Extract confidence from response (if model provides it)
            confidence = self._extract_confidence(response)
            
            return response, confidence
            
        except asyncio.TimeoutError:
            logger.warning("Gemini response timeout after %ds", self.timeout_seconds)
            return "Request timed out. Please try again or contact support.", 0.0
        except Exception as e:
            logger.error("Gemini API error: %s", e)
            return f"AI error: {str(e)}", 0.0
    
    async def _call_gemini(self, prompt: str) -> str:
        """
        Call Gemini API with prompt.
        
        Args:
            prompt: Prompt text
        
        Returns:
            Response text
        """
        # Generate content
        response = self.model.generate_content(prompt)
        
        # Extract text
        return response.text
    
    def _build_prompt(self, question: str, context: Dict[str, Any]) -> str:
        """
        Build prompt for Gemini with context.
        
        Args:
            question: User's question
            context: Project context
        
        Returns:
            Formatted prompt
        """
        # Format active tasks
        tasks_text = "None"
        if context['active_tasks']:
            tasks_list = [
                f"- {task['task_id']}: {task['goal']} ({task['state']})"
                for task in context['active_tasks']
            ]
            tasks_text = "\n".join(tasks_list)
        
        # Format recent messages (if available)
        messages_text = "No recent messages available"
        if context['recent_messages']:
            messages_list = [
                f"- {msg.get('user', 'unknown')}: {msg.get('text', '')[:100]}"
                for msg in context['recent_messages'][-5:]  # Last 5
            ]
            messages_text = "\n".join(messages_list)
        
        # Build prompt
        prompt = f"""You are Spectacles, an AI assistant for browser automation tasks.

Context:
- Project: {context['project_name']}
- Description: {context['project_description'] or 'N/A'}

Active Tasks:
{tasks_text}

Recent Messages:
{messages_text}

User Question: {question}

Instructions:
1. Answer the user's question based on the provided context
2. Be concise and helpful (2-3 sentences max)
3. If you don't have enough information, say so clearly
4. For task status, reference specific task IDs when available
5. For general questions about capabilities, explain what Spectacles can do
6. If the question is about billing, pricing, or account management, respond with: "ESCALATE: This requires human assistance."

Answer:"""
        
        return prompt
    
    def _extract_confidence(self, response: str) -> float:
        """
        Extract confidence score from response.
        
        For now, use heuristics:
        - Contains "I don't know" or "not sure" → low confidence (0.3)
        - Contains "ESCALATE" → very low (0.1)
        - Contains specific task IDs or data → high confidence (0.9)
        - Otherwise → medium confidence (0.7)
        
        Args:
            response: AI response text
        
        Returns:
            Confidence score (0.0-1.0)
        """
        response_lower = response.lower()
        
        # Check for escalation markers
        if "escalate" in response_lower or "human assistance" in response_lower:
            return 0.1
        
        # Check for uncertainty markers
        uncertainty_markers = [
            "i don't know", "not sure", "unclear", "can't say",
            "don't have enough information", "unable to determine"
        ]
        if any(marker in response_lower for marker in uncertainty_markers):
            return 0.3
        
        # Check for specific information (task IDs, numbers)
        has_task_id = bool(re.search(r'task-\d+', response_lower))
        has_numbers = bool(re.search(r'\d+', response))
        
        if has_task_id or has_numbers:
            return 0.9
        
        # Default medium confidence
        return 0.7
    
    def _should_auto_escalate(self, question: str) -> bool:
        """
        Check if question should automatically escalate (billing, etc.).
        
        Args:
            question: User's question
        
        Returns:
            True if should escalate
        """
        question_lower = question.lower()
        return any(keyword in question_lower for keyword in self.ESCALATION_KEYWORDS)
    
    def _should_escalate(self, response: str, confidence: float) -> bool:
        """
        Determine if response should escalate to human.
        
        Args:
            response: AI response text
            confidence: Confidence score
        
        Returns:
            True if should escalate
        """
        # Check confidence threshold
        if confidence < self.confidence_threshold:
            return True
        
        # Check if response contains escalation markers
        if "ESCALATE" in response or "human assistance" in response.lower():
            return True
        
        return False
    
    async def _escalate_to_human(
        self,
        question: str,
        user_id: str,
        channel_id: Optional[str],
        project_name: Optional[str],
        ai_response: Optional[str] = None,
        confidence: Optional[float] = None,
        reason: Optional[str] = None
    ) -> str:
        """
        Escalate question to human router.
        
        Args:
            question: Original question
            user_id: Slack user ID
            channel_id: Slack channel ID
            project_name: Project name
            ai_response: AI attempted response (if any)
            confidence: Confidence score
            reason: Escalation reason
        
        Returns:
            Escalation acknowledgment message
        """
        # Build context for escalation
        context = {
            'project_name': project_name,
            'ai_response': ai_response,
            'confidence': confidence,
            'reason': reason or "Low confidence or complex question"
        }
        
        # Call human router if available
        if self.human_router:
            try:
                await self.human_router.escalate(
                    question=question,
                    user_id=user_id,
                    channel_id=channel_id or '',
                    context=context,
                    ai_response=ai_response,
                    confidence=confidence
                )
                return "🆘 I've escalated your question to a human. Someone will respond shortly."
            except Exception as e:
                logger.error("Failed to escalate to human: %s", e)
        
        # Fallback if human router not available
        return ("I'm not confident in my answer to this question. "
                "Please contact support or try rephrasing your question.")
    
    def _filter_pii(self, text: str) -> str:
        """
        Filter PII from text for safe logging.
        
        Args:
            text: Text to filter
        
        Returns:
            Text with PII redacted
        """
        filtered = text
        
        for pii_type, pattern in self.PII_PATTERNS.items():
            filtered = pattern.sub(f'[{pii_type.upper()}_REDACTED]', filtered)
        
        return filtered


# Singleton instance (optional)
_handler = None


def get_ai_qa_handler(
    gemini_api_key: str,
    context_manager,
    task_store=None,
    human_router=None
) -> AIQAHandler:
    """Get singleton AI Q&A handler instance"""
    global _handler
    if _handler is None:
        _handler = AIQAHandler(
            gemini_api_key=gemini_api_key,
            context_manager=context_manager,
            task_store=task_store,
            human_router=human_router
        )
    return _handler
