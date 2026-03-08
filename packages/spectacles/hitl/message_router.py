"""
Spectacles Message Router
Routes incoming Slack messages to appropriate handlers

Features:
- DM handling
- @mention handling
- Channel message handling
- Thread reply handling
- Intent-based routing
"""

import logging
from typing import Optional, Dict, Any

from .intent_classifier import IntentClassifier, Intent, ClassificationResult
from .command_parser import CommandParser, CommandResult
from .channel_context_manager import ChannelContextManager

logger = logging.getLogger(__name__)


class MessageRouter:
    """
    Routes Slack messages to appropriate handlers.

    Routing Logic:
    1. Check if message is in thread → extract parent task_id → thread handler
    2. Check if DM (channel starts with 'D') → DM handler
    3. Check if bot mentioned → mention handler
    4. Check if channel in project_channels → channel handler
    5. Else → ignore (not in scope)
    """

    def __init__(
        self,
        classifier: IntentClassifier,
        command_parser: CommandParser,
        context_manager: ChannelContextManager,
        ai_qa_handler=None,
        human_router=None
    ):
        """
        Initialize message router.

        Args:
            classifier: Intent classifier
            command_parser: Command parser
            context_manager: Channel context manager
            ai_qa_handler: AI Q&A handler (optional, Phase 3)
            human_router: Human escalation router (optional, Phase 3)
        """
        self.classifier = classifier
        self.command_parser = command_parser
        self.context_manager = context_manager
        self.ai_qa_handler = ai_qa_handler
        self.human_router = human_router

        logger.info("MessageRouter initialized")

    async def route_message(
        self,
        event: Dict[str, Any],
        say_fn=None,
        client=None
    ) -> Optional[str]:
        """
        Route incoming message to appropriate handler.

        Args:
            event: Slack event dict
            say_fn: Slack say function for replying
            client: Slack client for API calls

        Returns:
            Response message or None
        """
        # Extract event data
        channel_id = event.get('channel', '')
        user_id = event.get('user', '')
        text = event.get('text', '').strip()
        thread_ts = event.get('thread_ts')
        message_ts = event.get('ts')

        # Ignore bot messages
        if event.get('bot_id'):
            logger.debug("Ignoring bot message")
            return None

        # Ignore empty messages
        if not text:
            logger.debug("Ignoring empty message")
            return None

        # Remove bot mention from text if present
        text_clean = self._remove_bot_mention(text)

        logger.info(
            "Routing message: channel=%s user=%s text=%s",
            channel_id,
            user_id,
            text_clean[:50]
        )

        try:
            # 1. Check if in thread (thread replies)
            if thread_ts and thread_ts != message_ts:
                response = await self._handle_thread_reply(
                    event, text_clean, user_id, thread_ts, say_fn
                )
                if response and say_fn:
                    await say_fn(text=response, thread_ts=thread_ts)
                return response

            # 2. Check if DM
            if channel_id.startswith('D'):
                response = await self._handle_dm(event, text_clean, user_id, say_fn)
                if response and say_fn:
                    await say_fn(text=response)
                return response

            # 3. Check if bot mentioned
            if self._is_bot_mentioned(text):
                response = await self._handle_mention(event, text_clean, user_id, channel_id, say_fn)
                if response and say_fn:
                    await say_fn(text=response, thread_ts=message_ts)  # Reply in thread
                return response

            # 4. Check if channel is registered for project
            project_name = self.context_manager.get_project_for_channel(channel_id)
            if project_name:
                response = await self._handle_channel_message(
                    event, text_clean, user_id, channel_id, project_name, say_fn
                )
                if response and say_fn:
                    await say_fn(text=response, thread_ts=message_ts)
                return response

            # 5. Not in scope, ignore
            logger.debug("Message not in scope (channel not registered)")
            return None

        except Exception as e:
            logger.error("Error routing message: %s", e, exc_info=True)
            if say_fn:
                await say_fn(
                    text=f" Sorry, I encountered an error processing your message: {str(e)}"
                )
            return None

    async def _handle_dm(
        self,
        event: Dict[str, Any],
        text: str,
        user_id: str,
        say_fn=None
    ) -> str:
        """
        Handle direct messages.

        Args:
            event: Slack event
            text: Message text (cleaned)
            user_id: Slack user ID
            say_fn: Say function

        Returns:
            Response message
        """
        logger.info("Handling DM from user %s: %s", user_id, text[:50])

        # Classify intent
        result = self.classifier.classify(text)

        # Route based on intent
        if result.intent == Intent.HELP:
            return self.command_parser._show_help().message

        if result.intent in [Intent.COMMAND, Intent.STATUS_QUERY]:
            # Execute command
            cmd_result = await self.command_parser.parse_and_execute(text, user_id)
            return cmd_result.message

        if result.intent == Intent.QUESTION:
            # AI Q&A (if available)
            if self.ai_qa_handler:
                return await self.ai_qa_handler.answer_question(text, user_id=user_id)
            else:
                return "Questions are not yet supported in DMs. Try asking in a project channel."

        if result.intent == Intent.CHANNEL_CREATE:
            # Channel creation
            cmd_result = await self.command_parser.parse_and_execute(text, user_id)
            return cmd_result.message

        # Escalate if unclear
        return ("I'm not sure what you're asking. Try:\n"
                "• `help` for available commands\n"
                "• `status task-123` to check task status\n"
                "• `list tasks` to see active tasks")

    async def _handle_mention(
        self,
        event: Dict[str, Any],
        text: str,
        user_id: str,
        channel_id: str,
        say_fn=None
    ) -> str:
        """
        Handle @mentions of the bot.

        Args:
            event: Slack event
            text: Message text (cleaned)
            user_id: Slack user ID
            channel_id: Slack channel ID
            say_fn: Say function

        Returns:
            Response message
        """
        logger.info("Handling mention from user %s in channel %s: %s", user_id, channel_id, text[:50])

        # Empty mention - show help
        if not text:
            return ("Hi! I'm Spectacles, your browser automation assistant.\n\n"
                    "Try:\n"
                    "• Ask me about task status: `status task-123`\n"
                    "• Ask me questions about your project\n"
                    "• Type `help` for all commands")

        # Classify intent
        result = self.classifier.classify(text, context={'channel_id': channel_id})

        # Route based on intent
        if result.intent == Intent.HELP:
            return self.command_parser._show_help().message

        if result.intent in [Intent.COMMAND, Intent.STATUS_QUERY]:
            cmd_result = await self.command_parser.parse_and_execute(text, user_id, channel_id)
            return cmd_result.message

        if result.intent == Intent.QUESTION:
            # AI Q&A (if available and in project channel)
            project_name = self.context_manager.get_project_for_channel(channel_id)
            if self.ai_qa_handler and project_name:
                return await self.ai_qa_handler.answer_question(
                    text,
                    user_id=user_id,
                    channel_id=channel_id,
                    project_name=project_name
                )
            else:
                return "I can answer questions in project channels. Try creating a channel with `create channel for your-project`"

        if result.intent == Intent.CHANNEL_CREATE:
            cmd_result = await self.command_parser.parse_and_execute(text, user_id, channel_id)
            return cmd_result.message

        # Escalate
        if result.intent == Intent.ESCALATE:
            if self.human_router:
                await self.human_router.escalate(
                    question=text,
                    user_id=user_id,
                    channel_id=channel_id,
                    context=result.extracted_data
                )
                return "🆘 I've escalated this to a human. Someone will respond shortly."
            else:
                return "I'm not sure how to handle that. Type `help` for available commands."

        return "I'm not sure what you're asking. Type `help` for available commands."

    async def _handle_channel_message(
        self,
        event: Dict[str, Any],
        text: str,
        user_id: str,
        channel_id: str,
        project_name: str,
        say_fn=None
    ) -> Optional[str]:
        """
        Handle messages in project channels.

        Args:
            event: Slack event
            text: Message text (cleaned)
            user_id: Slack user ID
            channel_id: Slack channel ID
            project_name: Project name for this channel
            say_fn: Say function

        Returns:
            Response message or None
        """
        logger.info(
            "Handling channel message from user %s in project %s: %s",
            user_id,
            project_name,
            text[:50]
        )

        # Classify intent
        result = self.classifier.classify(text, context={
            'channel_id': channel_id,
            'project_name': project_name
        })

        # Route based on intent
        if result.intent in [Intent.COMMAND, Intent.STATUS_QUERY]:
            cmd_result = await self.command_parser.parse_and_execute(text, user_id, channel_id)
            return cmd_result.message

        if result.intent == Intent.QUESTION:
            # AI Q&A with project context
            if self.ai_qa_handler:
                return await self.ai_qa_handler.answer_question(
                    text,
                    user_id=user_id,
                    channel_id=channel_id,
                    project_name=project_name
                )

        # For other intents in channel, don't respond
        # (This prevents bot from being too chatty in channels)
        return None

    async def _handle_thread_reply(
        self,
        event: Dict[str, Any],
        text: str,
        user_id: str,
        thread_ts: str,
        say_fn=None
    ) -> Optional[str]:
        """
        Handle replies in threads.

        Args:
            event: Slack event
            text: Message text (cleaned)
            user_id: Slack user ID
            thread_ts: Thread timestamp
            say_fn: Say function

        Returns:
            Response message or None
        """
        logger.info("Handling thread reply from user %s in thread %s", user_id, thread_ts)

        # TODO: Extract task_id from thread context
        # For now, treat like regular message
        result = self.classifier.classify(text)

        if result.intent in [Intent.COMMAND, Intent.STATUS_QUERY]:
            cmd_result = await self.command_parser.parse_and_execute(text, user_id)
            return cmd_result.message

        # For other intents, check if AI Q&A available
        if result.intent == Intent.QUESTION and self.ai_qa_handler:
            return await self.ai_qa_handler.answer_question(text, user_id=user_id)

        return None

    def _is_bot_mentioned(self, text: str) -> bool:
        """
        Check if bot is mentioned in text.

        Args:
            text: Message text

        Returns:
            True if bot mentioned
        """
        # Check for <@U...> mention format
        return text.startswith('<@U') or '@spectacles' in text.lower()

    def _remove_bot_mention(self, text: str) -> str:
        """
        Remove bot mention from text.

        Args:
            text: Message text

        Returns:
            Cleaned text
        """
        import re

        # Remove <@U...> mention (including underscores for test IDs like U_BOT)
        text = re.sub(r'<@U\w+>', '', text)

        # Remove @spectacles
        text = re.sub(r'@spectacles\s*', '', text, flags=re.IGNORECASE)

        return text.strip()
