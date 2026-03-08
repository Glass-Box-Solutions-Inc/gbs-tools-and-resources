"""
Spectacles Checkpoint Store
LangGraph-style state persistence for async HITL

Enables:
- Pause execution at any state
- Human can respond hours later
- Resume from exact state
- State versioning for rollback
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from pathlib import Path

from persistence.utils import (
    get_db_connection,
    generate_checkpoint_id,
    safe_json_dump,
    safe_json_parse,
    row_to_dict
)

logger = logging.getLogger(__name__)


class CheckpointStore:
    """
    LangGraph-style checkpointing for async human response.

    Stores complete execution state including:
    - Agent state
    - Browser state (URL, cookies, session)
    - Action history
    - Perception context
    - Pending human request

    Enables task resume even hours after pause.
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        checkpoint_ttl_hours: int = 24
    ):
        """
        Initialize checkpoint store.

        Args:
            db_path: Path to SQLite database
            checkpoint_ttl_hours: Hours before checkpoints expire
        """
        self.db_path = db_path or os.getenv('DB_PATH', './spectacles.db')
        self.checkpoint_ttl_hours = checkpoint_ttl_hours
        logger.info("CheckpointStore initialized: %s", self.db_path)

    async def save_checkpoint(
        self,
        task_id: str,
        thread_id: Optional[str],
        checkpoint_data: Dict[str, Any]
    ) -> str:
        """
        Save execution checkpoint.

        Stores:
        - Current agent state
        - Browser state (URL, cookies, session)
        - Action history
        - Perception context
        - Pending human request

        Args:
            task_id: Task identifier
            thread_id: Thread/conversation ID
            checkpoint_data: Complete checkpoint data

        Returns:
            Generated checkpoint ID
        """
        checkpoint_id = checkpoint_data.get("checkpoint_id") or generate_checkpoint_id(task_id)
        expires_at = datetime.now() + timedelta(hours=self.checkpoint_ttl_hours)

        with get_db_connection(self.db_path) as conn:
            conn.execute("""
                INSERT INTO checkpoints (
                    checkpoint_id, task_id, thread_id, agent_state,
                    step_index, state_data, browser_state, action_history,
                    perception_context, pending_approval, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                checkpoint_id,
                task_id,
                thread_id,
                checkpoint_data.get("state", "PLANNING"),
                checkpoint_data.get("step_index", 0),
                safe_json_dump(checkpoint_data),
                safe_json_dump(checkpoint_data.get("browser_state")),
                safe_json_dump(checkpoint_data.get("action_history")),
                safe_json_dump(checkpoint_data.get("perception_context")),
                safe_json_dump(checkpoint_data.get("pending_approval")),
                expires_at.isoformat()
            ))
            conn.commit()

        logger.info("Saved checkpoint: %s (expires: %s)", checkpoint_id, expires_at)
        return checkpoint_id

    async def load_checkpoint(
        self,
        task_id: str,
        checkpoint_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Load checkpoint (latest if ID not specified).

        Args:
            task_id: Task identifier
            checkpoint_id: Specific checkpoint ID

        Returns:
            Checkpoint data or None
        """
        with get_db_connection(self.db_path) as conn:
            if checkpoint_id:
                cursor = conn.execute(
                    "SELECT * FROM checkpoints WHERE checkpoint_id = ? AND expires_at > datetime('now')",
                    (checkpoint_id,)
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM checkpoints WHERE task_id = ? AND expires_at > datetime('now') ORDER BY created_at DESC LIMIT 1",
                    (task_id,)
                )
            row = cursor.fetchone()

        if not row:
            logger.debug("No checkpoint found for task %s", task_id)
            return None

        # Reconstruct checkpoint data
        checkpoint = {
            "checkpoint_id": row["checkpoint_id"],
            "task_id": row["task_id"],
            "thread_id": row["thread_id"],
            "state": row["agent_state"],
            "step_index": row["step_index"],
            "browser_state": safe_json_parse(row["browser_state"]) or {},
            "action_history": safe_json_parse(row["action_history"]) or [],
            "perception_context": safe_json_parse(row["perception_context"]) or {},
            "pending_approval": safe_json_parse(row["pending_approval"]),
            "created_at": row["created_at"],
        }

        logger.info("Loaded checkpoint: %s", checkpoint["checkpoint_id"])
        return checkpoint

    async def list_checkpoints(
        self,
        task_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        List checkpoints for a task.

        Args:
            task_id: Task identifier
            limit: Maximum checkpoints to return

        Returns:
            List of checkpoint summaries
        """
        with get_db_connection(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT checkpoint_id, agent_state, step_index, created_at, expires_at
                FROM checkpoints
                WHERE task_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (task_id, limit))
            rows = cursor.fetchall()

        return [row_to_dict(row) for row in rows]

    async def delete_checkpoint(self, checkpoint_id: str) -> bool:
        """Delete specific checkpoint"""
        with get_db_connection(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM checkpoints WHERE checkpoint_id = ?",
                (checkpoint_id,)
            )
            conn.commit()
            return cursor.rowcount > 0

    async def delete_task_checkpoints(self, task_id: str) -> int:
        """Delete all checkpoints for a task"""
        with get_db_connection(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM checkpoints WHERE task_id = ?",
                (task_id,)
            )
            conn.commit()
            count = cursor.rowcount

        logger.info("Deleted %d checkpoints for task %s", count, task_id)
        return count

    async def cleanup_expired(self) -> int:
        """
        Clean up expired checkpoints.

        Returns:
            Number of checkpoints deleted
        """
        with get_db_connection(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM checkpoints WHERE expires_at < datetime('now')"
            )
            conn.commit()
            count = cursor.rowcount

        if count > 0:
            logger.info("Cleaned up %d expired checkpoints", count)
        return count

    async def get_pending_human_requests(self) -> List[Dict[str, Any]]:
        """
        Get all checkpoints awaiting human response.

        Returns:
            List of checkpoints with pending_approval set
        """
        with get_db_connection(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT checkpoint_id, task_id, agent_state, pending_approval, created_at
                FROM checkpoints
                WHERE agent_state = 'AWAITING_HUMAN'
                AND expires_at > datetime('now')
                AND pending_approval IS NOT NULL
                ORDER BY created_at ASC
            """)
            rows = cursor.fetchall()

        results = []
        for row in rows:
            checkpoint = row_to_dict(row)
            checkpoint["pending_approval"] = safe_json_parse(checkpoint.get("pending_approval"))
            results.append(checkpoint)

        return results

    async def extend_checkpoint_ttl(
        self,
        checkpoint_id: str,
        additional_hours: int = 24
    ) -> bool:
        """
        Extend checkpoint expiration time.

        Useful when human needs more time to respond.

        Args:
            checkpoint_id: Checkpoint to extend
            additional_hours: Hours to add

        Returns:
            True if extended successfully
        """
        new_expires = datetime.now() + timedelta(hours=additional_hours)

        with get_db_connection(self.db_path) as conn:
            cursor = conn.execute(
                "UPDATE checkpoints SET expires_at = ? WHERE checkpoint_id = ?",
                (new_expires.isoformat(), checkpoint_id)
            )
            conn.commit()
            success = cursor.rowcount > 0

        if success:
            logger.info("Extended checkpoint %s to %s", checkpoint_id, new_expires)
        return success
