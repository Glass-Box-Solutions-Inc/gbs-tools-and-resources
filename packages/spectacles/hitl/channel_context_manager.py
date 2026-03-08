"""
Spectacles Channel Context Manager
Maps Slack channels to projects and tracks conversation state

Features:
- Channel to project mapping
- Admin user management
- Channel registration and lookup
- Context retrieval for AI Q&A
"""

import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class ChannelMapping:
    """Mapping between Slack channel and project"""
    project_name: str
    owner: str
    description: str
    created_at: Optional[str] = None


@dataclass
class ChannelContext:
    """Full context for a channel"""
    channel_id: str
    project_name: str
    owner: str
    description: str
    active_tasks: List[str]
    recent_messages: List[Dict[str, Any]]


class ChannelContextManager:
    """
    Manages channel-to-project mappings and context.

    Configuration stored in JSON file with structure:
    {
      "channels": {
        "C01234ABCD": {
          "project_name": "glassy",
          "owner": "alex",
          "description": "Glassy platform development"
        }
      },
      "admin_users": ["U01234", "U56789"]
    }
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize channel context manager.

        Args:
            config_path: Path to channel_mappings.json (default: config/channel_mappings.json)
        """
        if config_path is None:
            # Default to config/channel_mappings.json relative to project root
            config_path = str(Path(__file__).parent.parent / "config" / "channel_mappings.json")

        self.config_path = Path(config_path)
        self.mappings: Dict[str, ChannelMapping] = {}
        self.admin_users: List[str] = []

        # Load configuration
        self._load_config()

        logger.info(
            "ChannelContextManager initialized: %d channels, %d admins",
            len(self.mappings),
            len(self.admin_users)
        )

    def _load_config(self):
        """Load channel mappings from JSON file"""
        try:
            if not self.config_path.exists():
                logger.warning("Config file not found: %s - creating default", self.config_path)
                self._create_default_config()
                return

            with open(self.config_path, 'r') as f:
                data = json.load(f)

            # Load channel mappings
            channels_data = data.get('channels', {})
            for channel_id, channel_data in channels_data.items():
                self.mappings[channel_id] = ChannelMapping(**channel_data)

            # Load admin users
            self.admin_users = data.get('admin_users', [])

            logger.info("Loaded %d channel mappings from %s", len(self.mappings), self.config_path)

        except Exception as e:
            logger.error("Failed to load channel mappings: %s", e)
            # Initialize empty
            self.mappings = {}
            self.admin_users = []

    def _create_default_config(self):
        """Create default config file"""
        default_config = {
            "channels": {},
            "admin_users": []
        }

        try:
            # Create config directory if it doesn't exist
            self.config_path.parent.mkdir(parents=True, exist_ok=True)

            with open(self.config_path, 'w') as f:
                json.dump(default_config, f, indent=2)

            logger.info("Created default config file: %s", self.config_path)

        except Exception as e:
            logger.error("Failed to create default config: %s", e)

    def save_mappings(self):
        """Save mappings to JSON file"""
        try:
            # Convert mappings to dict
            channels_data = {}
            for channel_id, mapping in self.mappings.items():
                channels_data[channel_id] = asdict(mapping)

            config = {
                "channels": channels_data,
                "admin_users": self.admin_users
            }

            # Write to file
            with open(self.config_path, 'w') as f:
                json.dump(config, f, indent=2)

            logger.info("Saved %d channel mappings to %s", len(self.mappings), self.config_path)

        except Exception as e:
            logger.error("Failed to save channel mappings: %s", e)
            raise

    def get_project_for_channel(self, channel_id: str) -> Optional[str]:
        """
        Get project name for channel.

        Args:
            channel_id: Slack channel ID

        Returns:
            Project name or None if not mapped
        """
        mapping = self.mappings.get(channel_id)
        return mapping.project_name if mapping else None

    def get_mapping(self, channel_id: str) -> Optional[ChannelMapping]:
        """
        Get full mapping for channel.

        Args:
            channel_id: Slack channel ID

        Returns:
            ChannelMapping or None
        """
        return self.mappings.get(channel_id)

    def register_channel(
        self,
        channel_id: str,
        project_name: str,
        owner: str,
        description: str = ""
    ) -> bool:
        """
        Register a new channel mapping.

        Args:
            channel_id: Slack channel ID
            project_name: Project name
            owner: Project owner (Slack user ID or name)
            description: Channel description

        Returns:
            True if registered successfully
        """
        try:
            from datetime import datetime

            self.mappings[channel_id] = ChannelMapping(
                project_name=project_name,
                owner=owner,
                description=description,
                created_at=datetime.now().isoformat()
            )

            # Save to file
            self.save_mappings()

            logger.info(
                "Registered channel %s -> project %s (owner: %s)",
                channel_id,
                project_name,
                owner
            )

            return True

        except Exception as e:
            logger.error("Failed to register channel: %s", e)
            return False

    def unregister_channel(self, channel_id: str) -> bool:
        """
        Unregister a channel mapping.

        Args:
            channel_id: Slack channel ID

        Returns:
            True if unregistered successfully
        """
        try:
            if channel_id in self.mappings:
                del self.mappings[channel_id]
                self.save_mappings()
                logger.info("Unregistered channel %s", channel_id)
                return True
            else:
                logger.warning("Channel %s not found for unregistration", channel_id)
                return False

        except Exception as e:
            logger.error("Failed to unregister channel: %s", e)
            return False

    def is_admin(self, user_id: str) -> bool:
        """
        Check if user is admin.

        Args:
            user_id: Slack user ID

        Returns:
            True if user is admin
        """
        return user_id in self.admin_users

    def add_admin(self, user_id: str) -> bool:
        """
        Add admin user.

        Args:
            user_id: Slack user ID

        Returns:
            True if added successfully
        """
        try:
            if user_id not in self.admin_users:
                self.admin_users.append(user_id)
                self.save_mappings()
                logger.info("Added admin user: %s", user_id)
            return True

        except Exception as e:
            logger.error("Failed to add admin: %s", e)
            return False

    def remove_admin(self, user_id: str) -> bool:
        """
        Remove admin user.

        Args:
            user_id: Slack user ID

        Returns:
            True if removed successfully
        """
        try:
            if user_id in self.admin_users:
                self.admin_users.remove(user_id)
                self.save_mappings()
                logger.info("Removed admin user: %s", user_id)
            return True

        except Exception as e:
            logger.error("Failed to remove admin: %s", e)
            return False

    def get_channel_context(
        self,
        channel_id: str,
        task_store=None,
        message_history: Optional[List[Dict[str, Any]]] = None
    ) -> Optional[ChannelContext]:
        """
        Get full context for channel (for AI Q&A).

        Args:
            channel_id: Slack channel ID
            task_store: Optional TaskStore for active tasks
            message_history: Optional recent message history

        Returns:
            ChannelContext or None if channel not mapped
        """
        mapping = self.get_mapping(channel_id)
        if not mapping:
            return None

        # Get active tasks for this project
        active_tasks = []
        if task_store:
            try:
                # Filter tasks by project (if task has project metadata)
                # For now, just get all active tasks
                # TODO: Add project filtering to tasks
                pass
            except Exception as e:
                logger.warning("Failed to get active tasks: %s", e)

        return ChannelContext(
            channel_id=channel_id,
            project_name=mapping.project_name,
            owner=mapping.owner,
            description=mapping.description,
            active_tasks=active_tasks,
            recent_messages=message_history or []
        )

    def list_channels(self) -> Dict[str, ChannelMapping]:
        """
        List all channel mappings.

        Returns:
            Dict of channel_id -> ChannelMapping
        """
        return self.mappings.copy()

    def get_channels_by_project(self, project_name: str) -> List[str]:
        """
        Get all channel IDs for a project.

        Args:
            project_name: Project name

        Returns:
            List of channel IDs
        """
        return [
            channel_id
            for channel_id, mapping in self.mappings.items()
            if mapping.project_name == project_name
        ]


# Singleton instance (optional, for convenience)
_manager = None


def get_context_manager(config_path: Optional[str] = None) -> ChannelContextManager:
    """Get singleton context manager instance"""
    global _manager
    if _manager is None:
        _manager = ChannelContextManager(config_path=config_path)
    return _manager
