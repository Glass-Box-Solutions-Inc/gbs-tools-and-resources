"""
Persistence Layer Utilities
Common functionality for JSON handling, logging, database connections, and validation
"""

import json
import logging
import sqlite3
from typing import Optional, Any, Dict, List
from contextlib import contextmanager
from pathlib import Path

# Configure logger for persistence layer
logger = logging.getLogger(__name__)


def safe_json_parse(data: Optional[str], field_name: str = "field") -> Optional[Any]:
    """
    Safely parse JSON with error handling.

    Args:
        data: JSON string to parse
        field_name: Field name for error context

    Returns:
        Parsed JSON data or None if parsing fails
    """
    if not data:
        return None

    try:
        return json.loads(data)
    except json.JSONDecodeError as e:
        logger.warning(
            "Failed to parse %s JSON: %s. Returning None.",
            field_name,
            e,
            exc_info=True
        )
        return None


def safe_json_dump(data: Optional[Any]) -> Optional[str]:
    """
    Safely dump data to JSON.

    Args:
        data: Data to serialize

    Returns:
        JSON string or None if data is falsy
    """
    if not data:
        return None

    try:
        return json.dumps(data, default=str)  # default=str handles datetime objects
    except (TypeError, ValueError) as e:
        logger.warning("Failed to dump JSON: %s. Returning None.", e, exc_info=True)
        return None


def parse_json_fields(row_dict: Dict, fields: List[str]) -> Dict:
    """
    Parse multiple JSON fields in a row dictionary.

    Args:
        row_dict: Dictionary from database row
        fields: List of field names to parse as JSON

    Returns:
        Updated dictionary with parsed JSON fields
    """
    for field in fields:
        if row_dict.get(field):
            row_dict[field] = safe_json_parse(row_dict[field], field)
    return row_dict


def validate_session_id(session_id: Optional[str]) -> str:
    """
    Validate session ID format.

    Args:
        session_id: Session ID to validate

    Returns:
        Validated session ID

    Raises:
        ValueError: If session_id is invalid
    """
    if not session_id:
        raise ValueError("session_id cannot be empty")

    if not isinstance(session_id, str):
        raise ValueError(f"session_id must be a string, got {type(session_id)}")

    if len(session_id) > 255:
        raise ValueError(f"session_id too long: {len(session_id)} chars (max 255)")

    return session_id


def validate_matter_id(matter_id: Optional[int]) -> int:
    """
    Validate matter ID format.

    Args:
        matter_id: Matter ID to validate

    Returns:
        Validated matter ID

    Raises:
        ValueError: If matter_id is invalid
    """
    if matter_id is None:
        raise ValueError("matter_id cannot be None")

    if not isinstance(matter_id, int):
        raise ValueError(f"matter_id must be an integer, got {type(matter_id)}")

    if matter_id <= 0:
        raise ValueError(f"matter_id must be positive, got {matter_id}")

    return matter_id


def handle_foreign_key_error(error: sqlite3.IntegrityError, context: str = "") -> None:
    """
    Convert foreign key constraint errors to meaningful exceptions.

    Args:
        error: SQLite IntegrityError
        context: Context for the error message

    Raises:
        ValueError: With meaningful error message
    """
    error_msg = str(error).lower()

    if "foreign key constraint failed" in error_msg:
        raise ValueError(
            f"{context}: Referenced record does not exist. "
            "Ensure parent record (e.g., session) is created first."
        ) from error

    # Re-raise if not a foreign key error
    raise error


def ensure_database_directory(db_path: str) -> Path:
    """
    Ensure database directory exists.

    Args:
        db_path: Path to database file

    Returns:
        Path object for database file
    """
    db_file = Path(db_path)
    db_file.parent.mkdir(parents=True, exist_ok=True)
    return db_file


@contextmanager
def get_db_connection(db_path: str):
    """
    Context manager for database connections.

    Ensures proper connection cleanup and provides transaction support.
    Enables foreign key constraints and row factory for dict-like access.

    Args:
        db_path: Path to SQLite database

    Yields:
        SQLite connection with row_factory set to sqlite3.Row

    Example:
        with get_db_connection(db_path) as conn:
            cursor = conn.execute("SELECT * FROM sessions WHERE session_id = ?", (id,))
            row = cursor.fetchone()
            conn.commit()
    """
    # Ensure database directory exists
    ensure_database_directory(db_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    try:
        yield conn
    except Exception as e:
        conn.rollback()
        logger.error("Database operation failed: %s. Rolling back transaction.", e, exc_info=True)
        raise
    finally:
        conn.close()


class DatabaseConnectionManager:
    """
    Manages database connections with context manager support.

    Provides a reusable connection manager for stores that need
    multiple operations within a single transaction.

    Example:
        with DatabaseConnectionManager(db_path) as conn:
            cursor = conn.execute("INSERT INTO ...")
            conn.commit()
    """

    def __init__(self, db_path: str):
        """
        Initialize connection manager.

        Args:
            db_path: Path to SQLite database
        """
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None

    def __enter__(self):
        """Enter context manager - open connection"""
        ensure_database_directory(self.db_path)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        return self.conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context manager - close connection with rollback on error"""
        if exc_type is not None:
            # Exception occurred, rollback
            logger.error(
                "Transaction failed with %s: %s. Rolling back.",
                exc_type.__name__,
                exc_val,
                exc_info=True
            )
            if self.conn:
                self.conn.rollback()

        if self.conn:
            self.conn.close()

        return False  # Don't suppress exceptions


def row_to_dict(row: sqlite3.Row, json_fields: Optional[List[str]] = None) -> Dict:
    """
    Convert SQLite Row to dictionary with optional JSON parsing.

    Args:
        row: SQLite Row object
        json_fields: List of field names to parse as JSON

    Returns:
        Dictionary representation of row
    """
    if row is None:
        return {}

    row_dict = dict(row)

    if json_fields:
        row_dict = parse_json_fields(row_dict, json_fields)

    return row_dict


def initialize_database(db_path: str, schema_path: str) -> bool:
    """
    Initialize database with schema if not exists.

    Args:
        db_path: Path to database file
        schema_path: Path to SQL schema file

    Returns:
        True if initialization successful

    Raises:
        FileNotFoundError: If schema file not found
        sqlite3.Error: If schema execution fails
    """
    schema_file = Path(schema_path)

    if not schema_file.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")

    # Read schema SQL
    schema_sql = schema_file.read_text()

    # Execute schema
    with get_db_connection(db_path) as conn:
        try:
            conn.executescript(schema_sql)
            conn.commit()
            logger.info("Database initialized successfully at %s", db_path)
            return True
        except sqlite3.Error as e:
            logger.error("Failed to initialize database: %s", e, exc_info=True)
            raise


def vacuum_database(db_path: str) -> bool:
    """
    Run VACUUM to reclaim space and optimize database.

    Should be run periodically after bulk deletes (e.g., expired screenshots, old audit logs).

    Args:
        db_path: Path to database file

    Returns:
        True if vacuum successful
    """
    try:
        with get_db_connection(db_path) as conn:
            conn.execute("VACUUM")
            conn.commit()
            logger.info("Database vacuum completed successfully")
            return True
    except sqlite3.Error as e:
        logger.error("Failed to vacuum database: %s", e, exc_info=True)
        return False
