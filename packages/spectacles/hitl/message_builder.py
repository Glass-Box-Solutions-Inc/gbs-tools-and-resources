"""
Spectacles Message Builder
Slack Block Kit message construction for HITL

Builds rich, interactive messages with:
- Screenshots
- Context information
- Approval/Rejection/Tunnel buttons
"""

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)


class MessageBuilder:
    """
    Build Slack Block Kit messages for HITL operations.

    Creates structured, interactive messages with:
    - Header with task info
    - Screenshot (if available)
    - Action description
    - Context details
    - Interactive buttons
    """

    @staticmethod
    def build_approval_message(
        task_id: str,
        action_description: str,
        screenshot_url: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        blockers: Optional[List[str]] = None
    ) -> List[Dict]:
        """
        Build approval request message with Block Kit.

        Args:
            task_id: Task identifier
            action_description: Description of action needing approval
            screenshot_url: URL to attached screenshot
            context: Additional context (page URL, current state, etc.)
            blockers: List of detected blockers

        Returns:
            List of Block Kit blocks
        """
        blocks = [
            # Header
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "Action Approval Required",
                    "emoji": True
                }
            },
            # Task info
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Task ID:*\n`{task_id}`"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Requested:*\n{datetime.now().strftime('%H:%M:%S')}"
                    }
                ]
            },
            # Divider
            {"type": "divider"},
            # Action description
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*What needs approval:*\n{action_description}"
                }
            }
        ]

        # Add screenshot if available
        if screenshot_url:
            blocks.append({
                "type": "image",
                "image_url": screenshot_url,
                "alt_text": "Current browser state"
            })

        # Add context if provided
        if context:
            context_text = MessageBuilder._format_context(context)
            if context_text:
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Context:*\n{context_text}"
                    }
                })

        # Add blockers if any
        if blockers:
            blocker_text = "\n".join([f"- {b}" for b in blockers])
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f":warning: *Detected Issues:*\n{blocker_text}"
                }
            })

        # Divider before buttons
        blocks.append({"type": "divider"})

        # Action buttons
        blocks.append({
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "Approve",
                        "emoji": True
                    },
                    "style": "primary",
                    "action_id": "approve_action",
                    "value": task_id
                },
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "Reject",
                        "emoji": True
                    },
                    "style": "danger",
                    "action_id": "reject_action",
                    "value": task_id
                },
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "Take Control",
                        "emoji": True
                    },
                    "action_id": "take_control",
                    "value": task_id
                }
            ]
        })

        # Footer context
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "Spectacles | Respond within 5 minutes or action will timeout"
                }
            ]
        })

        return blocks

    @staticmethod
    def build_notification_message(
        title: str,
        message: str,
        task_id: Optional[str] = None,
        level: str = "info",
        details: Optional[Dict[str, Any]] = None
    ) -> List[Dict]:
        """
        Build notification message.

        Args:
            title: Message title
            message: Message content
            task_id: Optional task ID
            level: Notification level
            details: Additional details

        Returns:
            List of Block Kit blocks
        """
        emoji_map = {
            "info": ":information_source:",
            "warning": ":warning:",
            "error": ":x:",
            "success": ":white_check_mark:"
        }

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji_map.get(level, '')} {title}"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": message
                }
            }
        ]

        if task_id:
            blocks.append({
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": f"Task: `{task_id}`"}
                ]
            })

        if details:
            detail_text = MessageBuilder._format_context(details)
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"```{detail_text}```"
                }
            })

        return blocks

    @staticmethod
    def build_task_complete_message(
        task_id: str,
        goal: str,
        actions_taken: int,
        duration_seconds: int
    ) -> List[Dict]:
        """
        Build task completion message.

        Args:
            task_id: Task identifier
            goal: Original goal
            actions_taken: Number of actions executed
            duration_seconds: Total duration

        Returns:
            List of Block Kit blocks
        """
        duration_str = f"{duration_seconds // 60}m {duration_seconds % 60}s"

        return [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "Task Completed"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Goal:* {goal}"
                }
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Task ID:*\n`{task_id}`"},
                    {"type": "mrkdwn", "text": f"*Duration:*\n{duration_str}"},
                    {"type": "mrkdwn", "text": f"*Actions:*\n{actions_taken}"},
                    {"type": "mrkdwn", "text": f"*Status:*\nSuccess"}
                ]
            },
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": f"Completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"}
                ]
            }
        ]

    @staticmethod
    def build_error_message(
        task_id: str,
        error: str,
        screenshot_url: Optional[str] = None
    ) -> List[Dict]:
        """
        Build error notification message.

        Args:
            task_id: Task identifier
            error: Error message
            screenshot_url: Screenshot at time of error

        Returns:
            List of Block Kit blocks
        """
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "Task Failed"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Task ID:* `{task_id}`"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Error:*\n```{error}```"
                }
            }
        ]

        if screenshot_url:
            blocks.append({
                "type": "image",
                "image_url": screenshot_url,
                "alt_text": "Browser state at time of error"
            })

        return blocks

    @staticmethod
    def _format_context(context: Dict[str, Any]) -> str:
        """Format context dict for display"""
        lines = []
        for key, value in context.items():
            if isinstance(value, dict):
                value = str(value)[:100]
            elif isinstance(value, list):
                value = ", ".join(str(v)[:50] for v in value[:3])
                if len(context[key]) > 3:
                    value += f" (+{len(context[key]) - 3} more)"
            else:
                value = str(value)[:200]

            lines.append(f"*{key}:* {value}")

        return "\n".join(lines)
