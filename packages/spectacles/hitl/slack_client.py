"""
Spectacles Slack Client
Slack Bolt integration for Human-in-the-Loop operations

Features:
- Interactive approval messages with buttons
- Screenshot attachments for context
- Tunnel Mode for remote browser control
- Async response handling with checkpoints
"""

import asyncio
import logging
from typing import Optional, Dict, Any, Callable
from datetime import datetime

logger = logging.getLogger(__name__)

# Lazy imports for Slack
_slack_bolt = None
_slack_sdk = None


def _get_slack_bolt():
    global _slack_bolt
    if _slack_bolt is None:
        from slack_bolt.async_app import AsyncApp
        from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
        _slack_bolt = {"App": AsyncApp, "Handler": AsyncSocketModeHandler}
    return _slack_bolt


def _get_slack_sdk():
    global _slack_sdk
    if _slack_sdk is None:
        from slack_sdk.web.async_client import AsyncWebClient
        _slack_sdk = {"WebClient": AsyncWebClient}
    return _slack_sdk


class SlackClient:
    """
    Slack integration for Human-In-The-Loop operations.

    Features:
    - Interactive approval messages with buttons
    - Screenshot attachments for context
    - Tunnel Mode for remote browser control
    - Threaded conversation support
    - Async response handling
    """

    def __init__(
        self,
        bot_token: str,
        app_token: str,
        approval_channel: str = "#spectacles-approvals",
        on_approval: Optional[Callable] = None,
        on_rejection: Optional[Callable] = None,
        on_tunnel: Optional[Callable] = None,
        message_router=None
    ):
        """
        Initialize Slack client.

        Args:
            bot_token: Slack bot OAuth token (xoxb-)
            app_token: Slack app token for Socket Mode (xapp-)
            approval_channel: Channel for approval requests
            on_approval: Callback when action is approved
            on_rejection: Callback when action is rejected
            on_tunnel: Callback when user requests tunnel mode
            message_router: MessageRouter for bidirectional communication (optional)
        """
        bolt = _get_slack_bolt()
        sdk = _get_slack_sdk()

        self.app = bolt["App"](token=bot_token)
        self.client = sdk["WebClient"](token=bot_token)
        self.app_token = app_token
        self.approval_channel = approval_channel
        self.message_router = message_router

        # Callbacks
        self.on_approval = on_approval
        self.on_rejection = on_rejection
        self.on_tunnel = on_tunnel

        # Pending approvals
        self.pending_approvals: Dict[str, asyncio.Event] = {}
        self.approval_results: Dict[str, Dict[str, Any]] = {}

        # Register handlers
        self._register_handlers()

        # Register message handlers if message_router is provided
        if self.message_router:
            self._register_message_handlers()
            logger.info("SlackClient initialized with bidirectional communication")
        else:
            logger.info("SlackClient initialized for channel: %s", approval_channel)

    def _register_handlers(self):
        """Register Slack event handlers"""

        @self.app.action("approve_action")
        async def handle_approval(ack, body, client):
            await ack()
            task_id = body["actions"][0]["value"]
            user_id = body["user"]["id"]

            logger.info("Approval received for task %s by user %s", task_id, user_id)

            self.approval_results[task_id] = {
                "approved": True,
                "user_id": user_id,
                "timestamp": datetime.now().isoformat()
            }

            # Update message
            await client.chat_update(
                channel=body["channel"]["id"],
                ts=body["message"]["ts"],
                text=f"Approved by <@{user_id}>",
                blocks=self._build_resolved_blocks(task_id, "approved", user_id)
            )

            # Signal waiting coroutine
            if task_id in self.pending_approvals:
                self.pending_approvals[task_id].set()

            # Call callback
            if self.on_approval:
                await self.on_approval(task_id, user_id)

        @self.app.action("reject_action")
        async def handle_rejection(ack, body, client):
            await ack()
            task_id = body["actions"][0]["value"]
            user_id = body["user"]["id"]

            logger.info("Rejection received for task %s by user %s", task_id, user_id)

            self.approval_results[task_id] = {
                "approved": False,
                "user_id": user_id,
                "timestamp": datetime.now().isoformat()
            }

            await client.chat_update(
                channel=body["channel"]["id"],
                ts=body["message"]["ts"],
                text=f"Rejected by <@{user_id}>",
                blocks=self._build_resolved_blocks(task_id, "rejected", user_id)
            )

            if task_id in self.pending_approvals:
                self.pending_approvals[task_id].set()

            if self.on_rejection:
                await self.on_rejection(task_id, user_id)

        @self.app.action("take_control")
        async def handle_tunnel_request(ack, body, client):
            await ack()
            task_id = body["actions"][0]["value"]
            user_id = body["user"]["id"]

            logger.info("Tunnel mode requested for task %s by user %s", task_id, user_id)

            self.approval_results[task_id] = {
                "tunnel_mode": True,
                "user_id": user_id,
                "timestamp": datetime.now().isoformat()
            }

            # Update message to show tunnel mode active
            await client.chat_update(
                channel=body["channel"]["id"],
                ts=body["message"]["ts"],
                text=f"Tunnel mode activated for <@{user_id}>",
                blocks=self._build_tunnel_blocks(task_id, user_id)
            )

            if self.on_tunnel:
                await self.on_tunnel(task_id, user_id)

    def _register_message_handlers(self):
        """Register message event handlers for bidirectional communication"""

        @self.app.event("message")
        async def handle_message(event, say, client):
            """Handle incoming Slack messages"""
            logger.info("Received message event: %s", event)

            # Ignore bot messages
            if event.get("bot_id") or event.get("subtype") == "bot_message":
                logger.info("Ignoring bot message")
                return

            # Route message through MessageRouter
            if self.message_router:
                try:
                    logger.info("Routing message through MessageRouter")
                    response = await self.message_router.route_message(
                        event=event,
                        say_fn=say,
                        client=client
                    )
                    if response:
                        logger.info("Sending response: %s", response)
                        await say(response)
                except Exception as e:
                    logger.error("Error routing message: %s", e, exc_info=True)
                    await say(f"Sorry, I encountered an error: {str(e)}")

        logger.info("Message handlers registered")

    def register_command(self, command_name: str, handler: Callable):
        """
        Register a slash command handler.

        Args:
            command_name: Command name (without leading slash)
            handler: Async handler function
        """
        self.app.command(f"/{command_name}")(handler)
        logger.info(f"Registered slash command: /{command_name}")

    async def start(self):
        """Start Socket Mode handler"""
        bolt = _get_slack_bolt()
        self.handler = bolt["Handler"](self.app, self.app_token)
        logger.info("Starting Slack Socket Mode handler...")
        await self.handler.start_async()

    async def stop(self):
        """Stop Socket Mode handler"""
        if hasattr(self, 'handler'):
            await self.handler.close_async()
            logger.info("Slack Socket Mode handler stopped")

    async def request_approval(
        self,
        task_id: str,
        action_description: str,
        screenshot_bytes: Optional[bytes] = None,
        context: Optional[Dict[str, Any]] = None,
        timeout_seconds: int = 300
    ) -> Dict[str, Any]:
        """
        Send approval request to Slack and wait for response.

        Args:
            task_id: Task identifier
            action_description: Description of action needing approval
            screenshot_bytes: Screenshot to attach
            context: Additional context
            timeout_seconds: Timeout for response

        Returns:
            Dict with approval result
        """
        from .message_builder import MessageBuilder

        # Upload screenshot if provided
        screenshot_url = None
        if screenshot_bytes:
            try:
                result = await self.client.files_upload_v2(
                    channel=self.approval_channel,
                    file=screenshot_bytes,
                    filename=f"screenshot_{task_id}.png",
                    title=f"Screenshot for task {task_id}"
                )
                screenshot_url = result.get("file", {}).get("permalink")
            except Exception as e:
                logger.warning("Failed to upload screenshot: %s", e)

        # Build message
        blocks = MessageBuilder.build_approval_message(
            task_id=task_id,
            action_description=action_description,
            screenshot_url=screenshot_url,
            context=context
        )

        # Send message
        result = await self.client.chat_postMessage(
            channel=self.approval_channel,
            blocks=blocks,
            text=f"Approval needed: {action_description}"
        )

        message_ts = result["ts"]
        logger.info("Approval request sent for task %s: %s", task_id, message_ts)

        # Wait for response
        event = asyncio.Event()
        self.pending_approvals[task_id] = event

        try:
            await asyncio.wait_for(event.wait(), timeout=timeout_seconds)
            return self.approval_results.get(task_id, {"approved": False, "timeout": False})
        except asyncio.TimeoutError:
            logger.warning("Approval timeout for task %s", task_id)
            return {"approved": False, "timeout": True}
        finally:
            self.pending_approvals.pop(task_id, None)

    async def send_notification(
        self,
        message: str,
        task_id: Optional[str] = None,
        level: str = "info"
    ):
        """
        Send notification message to Slack.

        Args:
            message: Message text
            task_id: Optional task ID for context
            level: Notification level (info, warning, error, success)
        """
        color_map = {
            "info": "#2196F3",
            "warning": "#FFC107",
            "error": "#F44336",
            "success": "#4CAF50"
        }

        blocks = [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": message}
            }
        ]

        if task_id:
            blocks.append({
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": f"Task: `{task_id}`"}
                ]
            })

        await self.client.chat_postMessage(
            channel=self.approval_channel,
            blocks=blocks,
            text=message,
            attachments=[{"color": color_map.get(level, "#2196F3")}]
        )

    async def send_tunnel_url(
        self,
        task_id: str,
        tunnel_url: str,
        user_id: str
    ):
        """
        Send tunnel URL to user for browser control.

        Args:
            task_id: Task identifier
            tunnel_url: Browserless Live View URL
            user_id: Slack user to DM
        """
        # DM the user with the tunnel URL
        await self.client.chat_postMessage(
            channel=user_id,
            blocks=[
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": "Browser Control Access"}
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"You can now control the browser for task `{task_id}`.\n\n*Click the link below to access the browser:*"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"<{tunnel_url}|Open Browser Control>"
                    }
                },
                {
                    "type": "context",
                    "elements": [
                        {"type": "mrkdwn", "text": "This link expires in 30 minutes. The automation will resume after you close the browser."}
                    ]
                }
            ],
            text=f"Browser control link for task {task_id}"
        )

    def _build_resolved_blocks(
        self,
        task_id: str,
        resolution: str,
        user_id: str
    ) -> list:
        """Build blocks for resolved approval message"""
        emoji = "" if resolution == "approved" else ""
        return [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"{emoji} Action {resolution.title()}"}
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"Task `{task_id}` was *{resolution}* by <@{user_id}>"
                }
            },
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": f"Resolved at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"}
                ]
            }
        ]

    def _build_tunnel_blocks(self, task_id: str, user_id: str) -> list:
        """Build blocks for tunnel mode message"""
        return [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "Browser Control Active"}
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"<@{user_id}> has taken control of the browser for task `{task_id}`.\n\nThe automation will resume when browser control is released."
                }
            },
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": "A private link has been sent to the user."}
                ]
            }
        ]
