"""
Spectacles Persistence Utilities
Database connection and helper functions
"""

import json
import uuid
import sqlite3
import logging
from typing import Optional, Dict, Any
from pathlib import Path
from contextlib import contextmanager

logger = logging.getLogger(__name__)


def generate_task_id() -> str:
    """Generate unique task ID"""
    return f"task_{uuid.uuid4().hex[:12]}"


def generate_checkpoint_id(task_id: str) -> str:
    """Generate unique checkpoint ID"""
    return f"{task_id}_cp_{uuid.uuid4().hex[:8]}"


def generate_session_id() -> str:
    """Generate unique session ID"""
    return f"sess_{uuid.uuid4().hex[:12]}"


def generate_request_id() -> str:
    """Generate unique HITL request ID"""
    return f"hitl_{uuid.uuid4().hex[:12]}"


def validate_task_id(task_id: str) -> bool:
    """Validate task ID format"""
    if not task_id or not isinstance(task_id, str):
        raise ValueError("Task ID must be a non-empty string")
    if len(task_id) > 50:
        raise ValueError("Task ID too long (max 50 characters)")
    return True


def safe_json_parse(json_str: Optional[str]) -> Optional[Dict[str, Any]]:
    """Safely parse JSON string"""
    if not json_str:
        return None
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        logger.warning("Failed to parse JSON: %s", json_str[:100])
        return None


def safe_json_dump(data: Optional[Dict[str, Any]]) -> Optional[str]:
    """Safely dump dict to JSON string"""
    if data is None:
        return None
    try:
        return json.dumps(data)
    except (TypeError, ValueError) as e:
        logger.warning("Failed to dump JSON: %s", e)
        return None


def row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    """Convert sqlite3.Row to dictionary"""
    return dict(zip(row.keys(), row))


@contextmanager
def get_db_connection(db_path: str):
    """
    Context manager for database connections.

    Ensures proper connection handling and row factory setup.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def initialize_database(db_path: str, schema_path: str) -> None:
    """
    Initialize database from schema file.

    Args:
        db_path: Path to SQLite database file
        schema_path: Path to SQL schema file
    """
    # Ensure parent directory exists
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    # Read schema
    with open(schema_path, 'r') as f:
        schema_sql = f.read()

    # Execute schema
    with get_db_connection(db_path) as conn:
        conn.executescript(schema_sql)
        conn.commit()

    logger.info("Database initialized at %s", db_path)


def cleanup_expired_records(db_path: str) -> Dict[str, int]:
    """
    Clean up expired records from database.

    Returns:
        Dict with counts of deleted records per table
    """
    results = {}

    with get_db_connection(db_path) as conn:
        # Clean up expired screenshots
        cursor = conn.execute("""
            UPDATE screenshots
            SET deleted_at = CURRENT_TIMESTAMP
            WHERE expires_at < CURRENT_TIMESTAMP
            AND deleted_at IS NULL
        """)
        results["screenshots"] = cursor.rowcount

        # Clean up expired checkpoints
        cursor = conn.execute("""
            DELETE FROM checkpoints
            WHERE expires_at < CURRENT_TIMESTAMP
        """)
        results["checkpoints"] = cursor.rowcount

        # Clean up old audit logs (90 days)
        cursor = conn.execute("""
            DELETE FROM audit_log
            WHERE created_at < datetime('now', '-90 days')
        """)
        results["audit_log"] = cursor.rowcount

        conn.commit()

    logger.info("Cleanup results: %s", results)
    return results
