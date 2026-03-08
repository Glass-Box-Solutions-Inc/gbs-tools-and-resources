"""
Spectacles Webhook Client
Simple webhook-based Slack integration for HITL notifications.

Uses Incoming Webhooks (no OAuth required) for:
- Approval request notifications
- Status updates
- Screenshots (as links)

Limitations vs full Slack Bolt:
- No interactive buttons (one-way communication)
- No file uploads (use external image hosting)
- No message updates (new messages only)
"""

import asyncio
import logging
import base64
from typing import Optional, Dict, Any
from datetime import datetime
import httpx

logger = logging.getLogger(__name__)


class WebhookClient:
    """
    Simple webhook-based Slack client for HITL notifications.

    Use this when OAuth/Bot tokens aren't available.
    For full interactive features, use SlackClient instead.
    """

    def __init__(
        self,
        webhook_url: str,
        webhooks: Optional[Dict[str, str]] = None
    ):
        """
        Initialize webhook client.

        Args:
            webhook_url: Default webhook URL for notifications
            webhooks: Optional dict of named webhooks {"alex": "https://...", "main": "https://..."}
        """
        self.default_webhook = webhook_url
        self.webhooks = webhooks or {}
        self.webhooks["default"] = webhook_url

        logger.info("WebhookClient initialized with %d webhooks", len(self.webhooks))

    async def send_message(
        self,
        text: str,
        blocks: Optional[list] = None,
        webhook_name: str = "default"
    ) -> bool:
        """
        Send message to Slack via webhook.

        Args:
            text: Fallback text
            blocks: Block Kit blocks
            webhook_name: Which webhook to use

        Returns:
            True if sent successfully
        """
        webhook_url = self.webhooks.get(webhook_name, self.default_webhook)

        payload = {"text": text}
        if blocks:
            payload["blocks"] = blocks

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    webhook_url,
                    json=payload,
                    timeout=10.0
                )

                if response.status_code == 200:
                    logger.info("Message sent to webhook '%s'", webhook_name)
                    return True
                else:
                    logger.error("Webhook failed: %s %s", response.status_code, response.text)
                    return False

        except Exception as e:
            logger.error("Webhook error: %s", e)
            return False

    async def request_approval(
        self,
        task_id: str,
        action_description: str,
        screenshot_url: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        webhook_name: str = "default"
    ) -> bool:
        """
        Send approval request notification.

        Note: Since webhooks are one-way, this doesn't wait for response.
        The user must respond via another channel (thread reply, emoji, etc.)

        Args:
            task_id: Task identifier
            action_description: What action needs approval
            screenshot_url: URL to screenshot (must be externally hosted)
            context: Additional context dict
            webhook_name: Which webhook to use

        Returns:
            True if notification sent
        """
        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "Approval Needed", "emoji": True}
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Task:* `{task_id}`\n\n{action_description}"
                }
            }
        ]

        # Add screenshot if available
        if screenshot_url:
            blocks.append({
                "type": "image",
                "image_url": screenshot_url,
                "alt_text": "Browser screenshot"
            })

        # Add context
        if context:
            context_text = "\n".join([f"*{k}:* {v}" for k, v in context.items()])
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": context_text}
            })

        # Instructions for responding
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Reply with :white_check_mark: to approve or :x: to reject | Task ID: {task_id}"
                }
            ]
        })

        blocks.append({"type": "divider"})

        return await self.send_message(
            text=f"Approval needed for task {task_id}: {action_description}",
            blocks=blocks,
            webhook_name=webhook_name
        )

    async def send_notification(
        self,
        message: str,
        task_id: Optional[str] = None,
        level: str = "info",
        webhook_name: str = "default"
    ) -> bool:
        """
        Send status notification.

        Args:
            message: Notification message
            task_id: Optional task ID
            level: info, warning, error, success
            webhook_name: Which webhook to use
        """
        emoji_map = {
            "info": "information_source",
            "warning": "warning",
            "error": "x",
            "success": "white_check_mark"
        }
        emoji = emoji_map.get(level, "speech_balloon")

        blocks = [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f":{emoji}: {message}"}
            }
        ]

        if task_id:
            blocks.append({
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": f"Task: `{task_id}`"}]
            })

        return await self.send_message(
            text=message,
            blocks=blocks,
            webhook_name=webhook_name
        )

    async def send_tunnel_link(
        self,
        task_id: str,
        tunnel_url: str,
        webhook_name: str = "default"
    ) -> bool:
        """
        Send browser control link.

        Args:
            task_id: Task ID
            tunnel_url: Browserless Live View URL
            webhook_name: Which webhook to use
        """
        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "Browser Control Available"}
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"Task `{task_id}` requires human intervention.\n\n<{tunnel_url}|Click here to take control of the browser>"
                }
            },
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": "Link expires in 10 minutes"}
                ]
            }
        ]

        return await self.send_message(
            text=f"Browser control link for task {task_id}",
            blocks=blocks,
            webhook_name=webhook_name
        )

    async def send_task_complete(
        self,
        task_id: str,
        summary: str,
        success: bool = True,
        webhook_name: str = "default"
    ) -> bool:
        """
        Send task completion notification.

        Args:
            task_id: Task ID
            summary: Completion summary
            success: Whether task succeeded
            webhook_name: Which webhook to use
        """
        emoji = "white_check_mark" if success else "x"
        status = "completed successfully" if success else "failed"

        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f":{emoji}: Task `{task_id}` {status}\n\n{summary}"
                }
            },
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": f"Completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"}
                ]
            }
        ]

        return await self.send_message(
            text=f"Task {task_id} {status}",
            blocks=blocks,
            webhook_name=webhook_name
        )


def create_webhook_client_from_env() -> WebhookClient:
    """
    Create WebhookClient from environment variables.

    Expected env vars:
    - SLACK_APPROVAL_WEBHOOK or SLACK_WEBHOOK_MAIN: Default webhook
    - SLACK_WEBHOOK_ALEX: Alex's webhook
    - SLACK_WEBHOOK_BRIAN: Brian's webhook
    - SLACK_WEBHOOK_SOCIAL: Social channel webhook
    """
    import os

    default = os.environ.get("SLACK_APPROVAL_WEBHOOK") or os.environ.get("SLACK_WEBHOOK_MAIN", "")

    webhooks = {}
    for key in ["ALEX", "BRIAN", "MAIN", "SOCIAL"]:
        env_key = f"SLACK_WEBHOOK_{key}"
        if env_key in os.environ:
            webhooks[key.lower()] = os.environ[env_key]

    if not default:
        raise ValueError("No SLACK_APPROVAL_WEBHOOK or SLACK_WEBHOOK_MAIN configured")

    return WebhookClient(webhook_url=default, webhooks=webhooks)
