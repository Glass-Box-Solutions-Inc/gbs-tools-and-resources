"""
Spectacles Command Parser
Parses and executes task commands from Slack messages

Supported Commands:
- status task-123: Get task status
- pause task-123: Pause task
- resume task-123: Resume paused task
- cancel task-123: Cancel task
- list tasks: List active tasks
- create channel project-name: Create project channel (admin only)
- help: Show available commands
"""

import logging
import re
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass

from persistence.constants import AgentState
from persistence.task_store import TaskStore
from .channel_context_manager import ChannelContextManager

logger = logging.getLogger(__name__)


@dataclass
class CommandResult:
    """Result of command execution"""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None


class CommandParser:
    """
    Parses and executes task commands.

    Features:
    - Task control (status, pause, cancel, resume)
    - Task listing
    - Channel management (admin only)
    - Authorization checks
    """

    # Command patterns
    TASK_ID_PATTERN = re.compile(r'task[\s-]?(\d+)', re.IGNORECASE)
    PROJECT_NAME_PATTERN = re.compile(r'^[a-z0-9][a-z0-9-]{2,79}$')

    def __init__(
        self,
        orchestrator,
        task_store: TaskStore,
        context_manager: ChannelContextManager,
        slack_client=None
    ):
        """
        Initialize command parser.

        Args:
            orchestrator: Orchestrator for task control
            task_store: TaskStore for task queries
            context_manager: ChannelContextManager for authorization
            slack_client: SlackClient for channel creation
        """
        self.orchestrator = orchestrator
        self.task_store = task_store
        self.context_manager = context_manager
        self.slack_client = slack_client

        logger.info("CommandParser initialized")

    async def parse_and_execute(
        self,
        message: str,
        user_id: str,
        channel_id: Optional[str] = None
    ) -> CommandResult:
        """
        Parse message and execute command.

        Args:
            message: Command message
            user_id: Slack user ID
            channel_id: Slack channel ID (for context)

        Returns:
            CommandResult with execution outcome
        """
        message = message.strip().lower()

        # Help command
        if message in ['help', 'commands']:
            return self._show_help()

        # Status command
        if 'status' in message:
            return await self._handle_status(message, user_id)

        # Pause command
        if 'pause' in message:
            return await self._handle_pause(message, user_id)

        # Resume command
        if 'resume' in message:
            return await self._handle_resume(message, user_id)

        # Cancel command
        if any(word in message for word in ['cancel', 'stop', 'kill']):
            return await self._handle_cancel(message, user_id)

        # List command
        if 'list' in message:
            return await self._handle_list(user_id)

        # Create channel command (admin only)
        if 'create' in message and 'channel' in message:
            return await self._handle_create_channel(message, user_id, channel_id)

        # Unknown command
        return CommandResult(
            success=False,
            message="Unknown command. Type `help` for available commands."
        )

    def _show_help(self) -> CommandResult:
        """Show help text with available commands"""
        help_text = """*Available Commands:*

*Task Control:*
• `status task-123` - Get status of task
• `pause task-123` - Pause running task
• `resume task-123` - Resume paused task
• `cancel task-123` - Cancel task
• `list tasks` - List all active tasks

*Channel Management (admin only):*
• `create channel project-name` - Create project channel

*General:*
• `help` - Show this message

*Examples:*
• "What's the status of task-456?"
• "Pause task 789"
• "List all tasks"
• "Create channel for glassy-v2"
"""
        return CommandResult(
            success=True,
            message=help_text
        )

    async def _handle_status(self, message: str, user_id: str) -> CommandResult:
        """Handle status query"""
        task_id = self._extract_task_id(message)

        if not task_id:
            return CommandResult(
                success=False,
                message="Please specify a task ID. Example: `status task-123`"
            )

        # Get task from store
        task = self.task_store.get_task(task_id)

        if not task:
            return CommandResult(
                success=False,
                message=f"Task `{task_id}` not found."
            )

        # Build status message
        state = task.get('current_state', 'UNKNOWN')
        goal = task.get('goal', 'No goal')
        created_at = task.get('created_at', '')
        updated_at = task.get('updated_at', '')

        status_message = f"""*Task Status: {task_id}*

*Goal:* {goal}
*State:* `{state}`
*Created:* {created_at[:19] if created_at else 'Unknown'}
*Updated:* {updated_at[:19] if updated_at else 'Unknown'}
"""

        # Add error if failed
        if state == 'FAILED' and task.get('error_message'):
            status_message += f"\n*Error:* {task['error_message']}"

        # Add URL if available
        if task.get('start_url'):
            status_message += f"\n*URL:* {task['start_url']}"

        return CommandResult(
            success=True,
            message=status_message,
            data=task
        )

    async def _handle_pause(self, message: str, user_id: str) -> CommandResult:
        """Handle pause command"""
        task_id = self._extract_task_id(message)

        if not task_id:
            return CommandResult(
                success=False,
                message="Please specify a task ID. Example: `pause task-123`"
            )

        # Check if user is authorized (admin or task owner)
        if not await self._check_authorization(task_id, user_id):
            return CommandResult(
                success=False,
                message="You don't have permission to pause this task."
            )

        # Pause task via orchestrator
        try:
            # TODO: Implement pause in orchestrator
            # For now, update state in task store
            task = self.task_store.get_task(task_id)

            if not task:
                return CommandResult(
                    success=False,
                    message=f"Task `{task_id}` not found."
                )

            current_state = task.get('current_state')

            if current_state in ['COMPLETED', 'FAILED', 'CANCELLED']:
                return CommandResult(
                    success=False,
                    message=f"Cannot pause task in state `{current_state}`"
                )

            # Update state to AWAITING_HUMAN (paused)
            self.task_store.update_task_state(task_id, AgentState.AWAITING_HUMAN)

            return CommandResult(
                success=True,
                message=f" Task `{task_id}` paused. Use `resume task-{task_id.split('-')[1]}` to continue."
            )

        except Exception as e:
            logger.error("Failed to pause task %s: %s", task_id, e)
            return CommandResult(
                success=False,
                message=f"Failed to pause task: {str(e)}"
            )

    async def _handle_resume(self, message: str, user_id: str) -> CommandResult:
        """Handle resume command"""
        task_id = self._extract_task_id(message)

        if not task_id:
            return CommandResult(
                success=False,
                message="Please specify a task ID. Example: `resume task-123`"
            )

        # Check authorization
        if not await self._check_authorization(task_id, user_id):
            return CommandResult(
                success=False,
                message="You don't have permission to resume this task."
            )

        try:
            # Resume task via orchestrator
            if hasattr(self.orchestrator, 'resume_task'):
                await self.orchestrator.resume_task(task_id, user_approval=True)
                return CommandResult(
                    success=True,
                    message=f" Task `{task_id}` resumed."
                )
            else:
                return CommandResult(
                    success=False,
                    message="Resume functionality not yet implemented."
                )

        except Exception as e:
            logger.error("Failed to resume task %s: %s", task_id, e)
            return CommandResult(
                success=False,
                message=f"Failed to resume task: {str(e)}"
            )

    async def _handle_cancel(self, message: str, user_id: str) -> CommandResult:
        """Handle cancel command"""
        task_id = self._extract_task_id(message)

        if not task_id:
            return CommandResult(
                success=False,
                message="Please specify a task ID. Example: `cancel task-123`"
            )

        # Check authorization
        if not await self._check_authorization(task_id, user_id):
            return CommandResult(
                success=False,
                message="You don't have permission to cancel this task."
            )

        try:
            # Cancel task
            task = self.task_store.get_task(task_id)

            if not task:
                return CommandResult(
                    success=False,
                    message=f"Task `{task_id}` not found."
                )

            current_state = task.get('current_state')

            if current_state in ['COMPLETED', 'FAILED', 'CANCELLED']:
                return CommandResult(
                    success=False,
                    message=f"Task already in terminal state: `{current_state}`"
                )

            # Update state to CANCELLED
            self.task_store.update_task_state(task_id, AgentState.CANCELLED)

            return CommandResult(
                success=True,
                message=f" Task `{task_id}` cancelled."
            )

        except Exception as e:
            logger.error("Failed to cancel task %s: %s", task_id, e)
            return CommandResult(
                success=False,
                message=f"Failed to cancel task: {str(e)}"
            )

    async def _handle_list(self, user_id: str) -> CommandResult:
        """Handle list tasks command"""
        try:
            # Query active tasks from database
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

            if not rows:
                return CommandResult(
                    success=True,
                    message="No active tasks."
                )

            # Build list message
            message_lines = ["*Active Tasks:*\n"]

            for row in rows:
                task_id = row[0]
                goal = row[1][:50] + "..." if len(row[1]) > 50 else row[1]
                state = row[2]
                created = row[3][:10]  # Just date

                message_lines.append(f"• `{task_id}` - {goal} ({state}) - {created}")

            return CommandResult(
                success=True,
                message="\n".join(message_lines)
            )

        except Exception as e:
            logger.error("Failed to list tasks: %s", e)
            return CommandResult(
                success=False,
                message=f"Failed to list tasks: {str(e)}"
            )

    async def _handle_create_channel(
        self,
        message: str,
        user_id: str,
        channel_id: Optional[str]
    ) -> CommandResult:
        """Handle create channel command (admin only)"""
        # Check if user is admin
        if not self.context_manager.is_admin(user_id):
            return CommandResult(
                success=False,
                message=" Only admins can create channels."
            )

        # Extract project name
        project_name = self._extract_project_name(message)

        if not project_name:
            return CommandResult(
                success=False,
                message="Please specify a project name. Example: `create channel for glassy-v2`"
            )

        # Validate project name
        if not self.PROJECT_NAME_PATTERN.match(project_name):
            return CommandResult(
                success=False,
                message=f"Invalid project name: `{project_name}`. Must be lowercase, hyphens only, 3-80 chars."
            )

        # Check if slack_client is available
        if not self.slack_client:
            return CommandResult(
                success=False,
                message="Slack client not available for channel creation."
            )

        try:
            # Create Slack channel
            channel_name = f"spectacles-{project_name}"

            # Call Slack API to create channel
            if hasattr(self.slack_client, 'create_channel'):
                new_channel_id = await self.slack_client.create_channel(
                    name=channel_name,
                    description=f"Spectacles automation for {project_name}"
                )
            else:
                # Use Slack client directly
                result = await self.slack_client.client.conversations_create(
                    name=channel_name,
                    is_private=False
                )
                new_channel_id = result['channel']['id']

            # Register channel in context manager
            self.context_manager.register_channel(
                channel_id=new_channel_id,
                project_name=project_name,
                owner=user_id,
                description=f"Spectacles automation for {project_name}"
            )

            # Invite admins to channel
            for admin_id in self.context_manager.admin_users:
                try:
                    await self.slack_client.client.conversations_invite(
                        channel=new_channel_id,
                        users=admin_id
                    )
                except Exception as e:
                    logger.warning("Failed to invite admin %s: %s", admin_id, e)

            return CommandResult(
                success=True,
                message=f" Channel created: <#{new_channel_id}> for project `{project_name}`",
                data={"channel_id": new_channel_id, "project_name": project_name}
            )

        except Exception as e:
            logger.error("Failed to create channel: %s", e)
            return CommandResult(
                success=False,
                message=f"Failed to create channel: {str(e)}"
            )

    def _extract_task_id(self, message: str) -> Optional[str]:
        """
        Extract task ID from message.

        Args:
            message: Message text

        Returns:
            Task ID (e.g., "task-123") or None
        """
        match = self.TASK_ID_PATTERN.search(message)
        if match:
            return f"task-{match.group(1)}"
        return None

    def _extract_project_name(self, message: str) -> Optional[str]:
        """
        Extract project name from message.

        Args:
            message: Message text

        Returns:
            Project name or None
        """
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

    async def _check_authorization(self, task_id: str, user_id: str) -> bool:
        """
        Check if user is authorized to control task.

        Args:
            task_id: Task ID
            user_id: Slack user ID

        Returns:
            True if authorized
        """
        # Admins can control any task
        if self.context_manager.is_admin(user_id):
            return True

        # TODO: Check if user is task owner (if we store this in task metadata)
        # For now, allow any user to control any task
        return True
