"""
Spectacles Task Store
Manages task lifecycle and persistence
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from pathlib import Path

from .constants import AgentState, is_valid_transition
from .utils import (
    generate_task_id,
    validate_task_id,
    safe_json_parse,
    safe_json_dump,
    get_db_connection,
    initialize_database,
    row_to_dict
)

logger = logging.getLogger(__name__)


class TaskStore:
    """
    Store and retrieve browser automation tasks.

    Manages:
    - Task creation and updates
    - State transitions
    - Action history
    - Checkpoint management
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize task store.

        Args:
            db_path: Path to SQLite database. Uses DB_PATH env var if not provided.
        """
        self.db_path = db_path or os.getenv('DB_PATH', './spectacles.db')

        # Ensure parent directory exists
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        # Initialize database
        self._init_db()
        logger.info("TaskStore initialized with database: %s", self.db_path)

    def _init_db(self):
        """Initialize database schema if not exists"""
        db_exists = os.path.exists(self.db_path)

        if not db_exists:
            schema_path = Path(__file__).parent.parent / 'setup' / 'schema.sql'
            if not schema_path.exists():
                raise FileNotFoundError(f"Schema not found at {schema_path}")

            initialize_database(self.db_path, str(schema_path))
            logger.info("Database initialized at %s", self.db_path)

    def create_task(
        self,
        goal: str,
        start_url: str,
        credentials_key: Optional[str] = None,
        require_approval: bool = True,
        callback_url: Optional[str] = None,
        max_retries: int = 3,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create a new browser automation task.

        Args:
            goal: Natural language description of what to accomplish
            start_url: URL to start the automation
            credentials_key: GCP Secret Manager key for credentials
            require_approval: Whether to require HITL approval for actions
            callback_url: URL to call when task completes
            max_retries: Maximum retry attempts
            metadata: Additional task metadata

        Returns:
            Generated task_id
        """
        task_id = generate_task_id()
        now = datetime.now().isoformat()

        with get_db_connection(self.db_path) as conn:
            conn.execute("""
                INSERT INTO tasks (
                    task_id, goal, start_url, current_state,
                    require_approval, credentials_key, callback_url,
                    max_retries, metadata, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                task_id, goal, start_url, AgentState.PLANNING.value,
                1 if require_approval else 0, credentials_key, callback_url,
                max_retries, safe_json_dump(metadata), now, now
            ))
            conn.commit()

        logger.info("Created task: %s", task_id)
        return task_id

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Get task by ID.

        Args:
            task_id: Task identifier

        Returns:
            Task dict or None
        """
        validate_task_id(task_id)

        with get_db_connection(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT * FROM tasks WHERE task_id = ?",
                (task_id,)
            )
            row = cursor.fetchone()

        if not row:
            return None

        task = row_to_dict(row)
        task['metadata'] = safe_json_parse(task.get('metadata'))
        task['require_approval'] = bool(task.get('require_approval'))
        task['is_active'] = bool(task.get('is_active'))
        return task

    def update_task_state(
        self,
        task_id: str,
        new_state: AgentState,
        error_message: Optional[str] = None
    ) -> bool:
        """
        Update task state with validation.

        Args:
            task_id: Task identifier
            new_state: New agent state
            error_message: Error message if transitioning to FAILED

        Returns:
            True if updated successfully
        """
        task = self.get_task(task_id)
        if not task:
            logger.error("Task not found: %s", task_id)
            return False

        current_state = AgentState(task['current_state'])

        # Validate transition
        if not is_valid_transition(current_state, new_state):
            logger.warning(
                "Invalid state transition: %s -> %s for task %s",
                current_state, new_state, task_id
            )
            return False

        now = datetime.now().isoformat()
        updates = {
            'current_state': new_state.value,
            'updated_at': now
        }

        # Handle terminal states
        if new_state in [AgentState.COMPLETED, AgentState.FAILED]:
            updates['is_active'] = 0
            updates['completed_at'] = now
            if error_message:
                updates['error_message'] = error_message

        # Start time for first state transition
        if current_state == AgentState.PLANNING and not task.get('started_at'):
            updates['started_at'] = now

        with get_db_connection(self.db_path) as conn:
            set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
            values = list(updates.values()) + [task_id]
            conn.execute(
                f"UPDATE tasks SET {set_clause} WHERE task_id = ?",
                values
            )
            conn.commit()

        logger.info("Task %s state: %s -> %s", task_id, current_state, new_state)
        return True

    def update_task_step(
        self,
        task_id: str,
        current_step: int,
        total_steps: Optional[int] = None
    ) -> bool:
        """Update task progress"""
        now = datetime.now().isoformat()

        with get_db_connection(self.db_path) as conn:
            if total_steps is not None:
                conn.execute(
                    "UPDATE tasks SET current_step = ?, total_steps = ?, updated_at = ? WHERE task_id = ?",
                    (current_step, total_steps, now, task_id)
                )
            else:
                conn.execute(
                    "UPDATE tasks SET current_step = ?, updated_at = ? WHERE task_id = ?",
                    (current_step, now, task_id)
                )
            conn.commit()

        return True

    def increment_retry(self, task_id: str) -> int:
        """
        Increment retry count.

        Returns:
            New retry count
        """
        with get_db_connection(self.db_path) as conn:
            conn.execute(
                "UPDATE tasks SET retry_count = retry_count + 1, updated_at = ? WHERE task_id = ?",
                (datetime.now().isoformat(), task_id)
            )
            conn.commit()

            cursor = conn.execute(
                "SELECT retry_count FROM tasks WHERE task_id = ?",
                (task_id,)
            )
            row = cursor.fetchone()
            return row[0] if row else 0

    def get_active_tasks(self) -> List[Dict[str, Any]]:
        """Get all active tasks"""
        with get_db_connection(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT * FROM tasks WHERE is_active = 1 ORDER BY created_at DESC"
            )
            rows = cursor.fetchall()

        return [row_to_dict(row) for row in rows]

    def record_action(
        self,
        task_id: str,
        action_type: str,
        action_params: Optional[Dict[str, Any]] = None,
        target_element: Optional[str] = None,
        result_status: str = "PENDING",
        result_data: Optional[Dict[str, Any]] = None,
        perception_method: Optional[str] = None,
        confidence_score: Optional[float] = None,
        duration_ms: Optional[int] = None,
        screenshot_path: Optional[str] = None
    ) -> int:
        """
        Record an action in history.

        Returns:
            Action history ID
        """
        with get_db_connection(self.db_path) as conn:
            cursor = conn.execute("""
                INSERT INTO action_history (
                    task_id, action_type, action_params, target_element,
                    result_status, result_data, perception_method,
                    confidence_score, duration_ms, screenshot_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                task_id, action_type,
                safe_json_dump(action_params), target_element,
                result_status, safe_json_dump(result_data),
                perception_method, confidence_score, duration_ms, screenshot_path
            ))
            conn.commit()
            return cursor.lastrowid

    def get_action_history(
        self,
        task_id: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get action history for task"""
        with get_db_connection(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT * FROM action_history
                WHERE task_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (task_id, limit))
            rows = cursor.fetchall()

        actions = []
        for row in rows:
            action = row_to_dict(row)
            action['action_params'] = safe_json_parse(action.get('action_params'))
            action['result_data'] = safe_json_parse(action.get('result_data'))
            actions.append(action)

        return actions

    def cleanup_old_tasks(self, days: int = 7) -> int:
        """
        Clean up tasks older than specified days.

        Returns:
            Number of tasks deleted
        """
        with get_db_connection(self.db_path) as conn:
            cursor = conn.execute("""
                DELETE FROM tasks
                WHERE is_active = 0
                AND completed_at < datetime('now', ?)
            """, (f'-{days} days',))
            count = cursor.rowcount
            conn.commit()

        logger.info("Cleaned up %d old tasks", count)
        return count
