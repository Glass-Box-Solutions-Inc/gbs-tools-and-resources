"""
Spectacles Human Router
Routes escalated questions to appropriate humans via Slack DM

Features:
- Topic-based routing (billing → Alex, usage → Brian)
- Project owner routing
- Formatted escalation messages with context
- DM delivery to recipients
"""

import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class HumanRouter:
    """
    Routes escalated questions to appropriate humans.
    
    Routing Logic:
    1. Check for topic keywords (billing, usage, etc.)
    2. Check project owner from channel mapping
    3. Default to fallback recipient
    
    Sends formatted escalation message via DM with:
    - Original question
    - User information
    - AI attempted answer (if available)
    - Relevant context (tasks, messages)
    """
    
    # Topic-based routing keywords
    TOPIC_ROUTES = {
        'alex': ['billing', 'payment', 'cost', 'price', 'invoice', 'account', 'subscription'],
        'brian': ['usage', 'quota', 'limit', 'rate', 'capacity', 'performance'],
    }
    
    # Default recipient user IDs (Slack user IDs)
    DEFAULT_RECIPIENTS = {
        'alex': 'U01234ABCD',  # Replace with actual Slack user ID
        'brian': 'U56789EFGH',  # Replace with actual Slack user ID
    }
    
    def __init__(
        self,
        slack_client,
        context_manager,
        default_recipient: str = 'alex',
        recipient_map: Optional[Dict[str, str]] = None
    ):
        """
        Initialize human router.
        
        Args:
            slack_client: SlackClient for sending DMs
            context_manager: ChannelContextManager for project owner lookup
            default_recipient: Default recipient name ('alex', 'brian')
            recipient_map: Custom recipient mapping (name → Slack user ID)
        """
        self.slack_client = slack_client
        self.context_manager = context_manager
        self.default_recipient = default_recipient
        
        # Merge default and custom recipient maps
        self.recipients = {**self.DEFAULT_RECIPIENTS}
        if recipient_map:
            self.recipients.update(recipient_map)
        
        logger.info(
            "HumanRouter initialized with %d recipients (default: %s)",
            len(self.recipients),
            default_recipient
        )
    
    async def escalate(
        self,
        question: str,
        user_id: str,
        channel_id: str,
        context: Dict[str, Any],
        ai_response: Optional[str] = None,
        confidence: Optional[float] = None
    ):
        """
        Escalate question to appropriate human.
        
        Args:
            question: Original user question
            user_id: Slack user ID (questioner)
            channel_id: Slack channel ID
            context: Context dict from AIQAHandler
            ai_response: AI attempted answer (if available)
            confidence: Confidence score (if available)
        """
        # Determine recipient
        project_name = context.get('project_name')
        recipient_name = self._determine_recipient(project_name, question)
        recipient_id = self.recipients.get(recipient_name, self.recipients[self.default_recipient])
        
        logger.info(
            "Escalating question from user %s to %s (recipient: %s)",
            user_id,
            recipient_name,
            recipient_id
        )
        
        # Format escalation message
        message = self._format_escalation_message(
            question=question,
            user_id=user_id,
            channel_id=channel_id,
            project_name=project_name,
            context=context,
            ai_response=ai_response,
            confidence=confidence
        )
        
        # Send DM to recipient
        try:
            await self._send_dm(recipient_id, message)
            logger.info("Escalation message sent to %s", recipient_name)
        except Exception as e:
            logger.error("Failed to send escalation DM: %s", e)
            # Try fallback recipient if different
            if recipient_name != self.default_recipient:
                logger.info("Trying fallback recipient: %s", self.default_recipient)
                fallback_id = self.recipients[self.default_recipient]
                await self._send_dm(fallback_id, message)
    
    def _determine_recipient(self, project_name: Optional[str], question: str) -> str:
        """
        Determine which human should handle escalation.
        
        Args:
            project_name: Project name (for owner lookup)
            question: Original question (for topic analysis)
        
        Returns:
            Recipient name ('alex', 'brian', etc.)
        """
        question_lower = question.lower()
        
        # 1. Check topic keywords
        for recipient, keywords in self.TOPIC_ROUTES.items():
            if any(keyword in question_lower for keyword in keywords):
                logger.debug("Routing to %s based on topic keywords", recipient)
                return recipient
        
        # 2. Check project owner (if available)
        if project_name and self.context_manager:
            channels = self.context_manager.get_channels_by_project(project_name)
            if channels:
                # Get first channel's mapping
                mapping = self.context_manager.get_mapping(channels[0])
                if mapping and mapping.owner:
                    # Check if owner matches a known recipient
                    owner_lower = mapping.owner.lower()
                    for recipient_name in self.recipients.keys():
                        if recipient_name in owner_lower:
                            logger.debug("Routing to %s (project owner)", recipient_name)
                            return recipient_name
        
        # 3. Default fallback
        logger.debug("Using default recipient: %s", self.default_recipient)
        return self.default_recipient
    
    def _format_escalation_message(
        self,
        question: str,
        user_id: str,
        channel_id: str,
        project_name: Optional[str],
        context: Dict[str, Any],
        ai_response: Optional[str] = None,
        confidence: Optional[float] = None
    ) -> str:
        """
        Format escalation message for human.
        
        Args:
            question: Original question
            user_id: Slack user ID
            channel_id: Slack channel ID
            project_name: Project name
            context: Context dict
            ai_response: AI attempted answer
            confidence: Confidence score
        
        Returns:
            Formatted message text
        """
        # Get channel name (if possible)
        channel_name = f"<#{channel_id}>" if channel_id else "DM"
        
        # Build message
        lines = [
            "🆘 *Escalation Needed*",
            "",
            f"*From:* <@{user_id}> in {channel_name}",
            f"*Project:* {project_name or 'N/A'}",
            "",
            "*Question:*",
            f"> {question}",
            ""
        ]
        
        # Add AI response if available
        if ai_response:
            confidence_text = f" (confidence: {confidence:.0%})" if confidence else ""
            lines.extend([
                f"*AI Response{confidence_text}:*",
                f"> {ai_response}",
                ""
            ])
        
        # Add context
        active_tasks = context.get('active_tasks', [])
        if active_tasks:
            task_list = [
                f"• `{task['task_id']}`: {task['goal']} ({task['state']})"
                for task in active_tasks[:3]  # Show first 3
            ]
            lines.extend([
                "*Active Tasks:*",
                *task_list,
                ""
            ])
        
        recent_messages = context.get('recent_messages', [])
        if recent_messages:
            msg_list = [
                f"• {msg.get('user', 'unknown')}: {msg.get('text', '')[:80]}..."
                for msg in recent_messages[-3:]  # Last 3
            ]
            lines.extend([
                "*Recent Messages:*",
                *msg_list,
                ""
            ])
        
        # Add instructions
        lines.extend([
            "---",
            "_Reply in this thread to answer the user. I'll forward your response._"
        ])
        
        return "\n".join(lines)
    
    async def _send_dm(self, recipient_id: str, message: str):
        """
        Send DM to recipient via Slack.
        
        Args:
            recipient_id: Slack user ID
            message: Message text
        """
        if not self.slack_client:
            logger.error("Slack client not available for sending DM")
            return
        
        try:
            # Open DM channel
            if hasattr(self.slack_client, 'client'):
                # Using Slack Bolt client
                response = await self.slack_client.client.conversations_open(users=recipient_id)
                dm_channel = response['channel']['id']
                
                # Send message
                await self.slack_client.client.chat_postMessage(
                    channel=dm_channel,
                    text=message
                )
            else:
                # Using custom client
                await self.slack_client.send_message(recipient_id, message)
            
            logger.info("DM sent to %s", recipient_id)
            
        except Exception as e:
            logger.error("Failed to send DM to %s: %s", recipient_id, e)
            raise
    
    def set_recipient(self, name: str, user_id: str):
        """
        Add or update recipient mapping.
        
        Args:
            name: Recipient name ('alex', 'brian', etc.)
            user_id: Slack user ID
        """
        self.recipients[name] = user_id
        logger.info("Updated recipient mapping: %s → %s", name, user_id)
    
    def set_default_recipient(self, name: str):
        """
        Set default recipient for escalations.
        
        Args:
            name: Recipient name
        """
        if name not in self.recipients:
            raise ValueError(f"Recipient '{name}' not in recipient map")
        
        self.default_recipient = name
        logger.info("Default recipient set to: %s", name)


# Singleton instance (optional)
_router = None


def get_human_router(
    slack_client,
    context_manager,
    default_recipient: str = 'alex'
) -> HumanRouter:
    """Get singleton human router instance"""
    global _router
    if _router is None:
        _router = HumanRouter(
            slack_client=slack_client,
            context_manager=context_manager,
            default_recipient=default_recipient
        )
    return _router
