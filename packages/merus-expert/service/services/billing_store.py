# @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""
Billing Store - SQLite persistence for billing sessions
Manages billing session state and time entry history
"""

import sqlite3
import json
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

from service.services.billing_flow import BillingContext, BillingState

logger = logging.getLogger(__name__)


class BillingStore:
    """
    Persistent storage for billing sessions.

    Stores billing session state and time entry history in SQLite.
    """

    def __init__(self, db_path: str = "./knowledge/db/merus_knowledge.db"):
        """
        Initialize billing store.

        Args:
            db_path: Path to SQLite database
        """
        self.db_path = db_path
        self._ensure_tables()

    @contextmanager
    def _get_connection(self):
        """Get database connection with context manager"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            conn.close()

    def _ensure_tables(self) -> None:
        """Create billing tables if they don't exist"""
        with self._get_connection() as conn:
            # Billing sessions table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS billing_sessions (
                    session_id TEXT PRIMARY KEY,
                    state TEXT NOT NULL DEFAULT 'init',
                    matter_data TEXT,
                    entry_data TEXT,
                    search_results TEXT,
                    retry_count INTEGER DEFAULT 0,
                    errors TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Billing messages table (for conversation history)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS billing_messages (
                    message_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
                    content TEXT NOT NULL,
                    metadata TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES billing_sessions(session_id)
                )
            """)

            # Time entries table (completed entries)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS time_entries (
                    entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    matter_id TEXT,
                    matter_name TEXT,
                    client_name TEXT,
                    hours REAL NOT NULL,
                    description TEXT NOT NULL,
                    category TEXT,
                    entry_date DATE,
                    timekeeper TEXT,
                    billable INTEGER DEFAULT 1,
                    rate REAL,
                    status TEXT DEFAULT 'pending',
                    meruscase_url TEXT,
                    error_message TEXT,
                    dry_run INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    submitted_at TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES billing_sessions(session_id)
                )
            """)

            # Recent matters cache
            conn.execute("""
                CREATE TABLE IF NOT EXISTS recent_matters (
                    matter_id TEXT PRIMARY KEY,
                    matter_name TEXT NOT NULL,
                    client_name TEXT,
                    case_type TEXT,
                    meruscase_url TEXT,
                    last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create indexes
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_billing_messages_session
                ON billing_messages(session_id, timestamp)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_time_entries_session
                ON time_entries(session_id, created_at)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_time_entries_matter
                ON time_entries(matter_id, entry_date)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_recent_matters_accessed
                ON recent_matters(last_accessed DESC)
            """)

            logger.info("Billing tables initialized")

    def create_session(self, session_id: str) -> BillingContext:
        """
        Create a new billing session.

        Args:
            session_id: Unique session identifier

        Returns:
            New BillingContext
        """
        context = BillingContext(session_id=session_id)

        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO billing_sessions
                (session_id, state, matter_data, entry_data, search_results, retry_count, errors)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                session_id,
                context.state.value,
                json.dumps(context.matter) if context.matter else None,
                json.dumps(context.entry) if context.entry else None,
                json.dumps(context.search_results),
                context.retry_count,
                json.dumps(context.errors),
            ))

        logger.info(f"Created billing session: {session_id}")
        return context

    def get_context(self, session_id: str) -> Optional[BillingContext]:
        """
        Get billing context for session.

        Args:
            session_id: Session identifier

        Returns:
            BillingContext or None if not found
        """
        with self._get_connection() as conn:
            row = conn.execute("""
                SELECT state, matter_data, entry_data, search_results, retry_count, errors
                FROM billing_sessions
                WHERE session_id = ?
            """, (session_id,)).fetchone()

        if not row:
            return None

        # Reconstruct context
        try:
            state = BillingState(row["state"])
        except ValueError:
            state = BillingState.INIT

        context = BillingContext(
            session_id=session_id,
            state=state,
            matter=json.loads(row["matter_data"]) if row["matter_data"] else None,
            entry=json.loads(row["entry_data"]) if row["entry_data"] else None,
            search_results=json.loads(row["search_results"]) if row["search_results"] else [],
            retry_count=row["retry_count"] or 0,
            errors=json.loads(row["errors"]) if row["errors"] else [],
        )

        return context

    def save_context(self, context: BillingContext) -> None:
        """
        Save billing context.

        Args:
            context: BillingContext to save
        """
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE billing_sessions
                SET state = ?,
                    matter_data = ?,
                    entry_data = ?,
                    search_results = ?,
                    retry_count = ?,
                    errors = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE session_id = ?
            """, (
                context.state.value,
                json.dumps(context.matter) if context.matter else None,
                json.dumps(context.entry) if context.entry else None,
                json.dumps(context.search_results),
                context.retry_count,
                json.dumps(context.errors),
                context.session_id,
            ))

        logger.debug(f"Saved billing context: {context.session_id}")

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Add message to conversation history.

        Args:
            session_id: Session identifier
            role: Message role (user, assistant, system)
            content: Message content
            metadata: Optional metadata
        """
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO billing_messages
                (session_id, role, content, metadata)
                VALUES (?, ?, ?, ?)
            """, (
                session_id,
                role,
                content,
                json.dumps(metadata) if metadata else None,
            ))

    def get_messages(
        self,
        session_id: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get message history for session.

        Args:
            session_id: Session identifier
            limit: Maximum messages to return

        Returns:
            List of message dicts
        """
        with self._get_connection() as conn:
            rows = conn.execute("""
                SELECT role, content, metadata, timestamp
                FROM billing_messages
                WHERE session_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (session_id, limit)).fetchall()

        return [
            {
                "role": row["role"],
                "content": row["content"],
                "metadata": json.loads(row["metadata"]) if row["metadata"] else None,
                "timestamp": row["timestamp"],
            }
            for row in reversed(rows)  # Chronological order
        ]

    def save_time_entry(
        self,
        session_id: str,
        matter_id: str,
        matter_name: str,
        client_name: str,
        hours: float,
        description: str,
        category: str,
        entry_date: str,
        status: str = "pending",
        dry_run: bool = True,
        meruscase_url: Optional[str] = None,
        timekeeper: Optional[str] = None,
        billable: bool = True,
        rate: Optional[float] = None,
        error_message: Optional[str] = None,
    ) -> int:
        """
        Save a time entry record.

        Args:
            Various time entry fields

        Returns:
            entry_id of created record
        """
        with self._get_connection() as conn:
            cursor = conn.execute("""
                INSERT INTO time_entries
                (session_id, matter_id, matter_name, client_name, hours, description,
                 category, entry_date, timekeeper, billable, rate, status,
                 meruscase_url, dry_run, error_message,
                 submitted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                session_id,
                matter_id,
                matter_name,
                client_name,
                hours,
                description,
                category,
                entry_date,
                timekeeper,
                1 if billable else 0,
                rate,
                status,
                meruscase_url,
                1 if dry_run else 0,
                error_message,
                datetime.now().isoformat() if status == "success" else None,
            ))

            entry_id = cursor.lastrowid

        logger.info(f"Saved time entry {entry_id}: {hours}h for {matter_name}")
        return entry_id

    def update_entry_status(
        self,
        entry_id: int,
        status: str,
        error_message: Optional[str] = None
    ) -> None:
        """Update time entry status"""
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE time_entries
                SET status = ?,
                    error_message = ?,
                    submitted_at = CASE WHEN ? = 'success' THEN CURRENT_TIMESTAMP ELSE submitted_at END
                WHERE entry_id = ?
            """, (status, error_message, status, entry_id))

    def get_entries_for_session(self, session_id: str) -> List[Dict[str, Any]]:
        """Get all time entries for a session"""
        with self._get_connection() as conn:
            rows = conn.execute("""
                SELECT *
                FROM time_entries
                WHERE session_id = ?
                ORDER BY created_at DESC
            """, (session_id,)).fetchall()

        return [dict(row) for row in rows]

    def get_entries_for_matter(
        self,
        matter_id: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get time entries for a specific matter"""
        with self._get_connection() as conn:
            rows = conn.execute("""
                SELECT *
                FROM time_entries
                WHERE matter_id = ?
                ORDER BY entry_date DESC, created_at DESC
                LIMIT ?
            """, (matter_id, limit)).fetchall()

        return [dict(row) for row in rows]

    def add_recent_matter(
        self,
        matter_id: str,
        matter_name: str,
        client_name: str = "",
        case_type: Optional[str] = None,
        meruscase_url: str = ""
    ) -> None:
        """Add or update a matter in recent cache"""
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO recent_matters
                (matter_id, matter_name, client_name, case_type, meruscase_url, last_accessed)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (matter_id, matter_name, client_name, case_type, meruscase_url))

    def get_recent_matters(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recently accessed matters"""
        with self._get_connection() as conn:
            rows = conn.execute("""
                SELECT matter_id, matter_name, client_name, case_type, meruscase_url, last_accessed
                FROM recent_matters
                ORDER BY last_accessed DESC
                LIMIT ?
            """, (limit,)).fetchall()

        return [dict(row) for row in rows]

    def delete_session(self, session_id: str) -> None:
        """Delete a billing session and its messages"""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM billing_messages WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM billing_sessions WHERE session_id = ?", (session_id,))

        logger.info(f"Deleted billing session: {session_id}")

    def cleanup_old_sessions(self, days: int = 7) -> int:
        """
        Delete sessions older than specified days.

        Args:
            days: Age threshold in days

        Returns:
            Number of sessions deleted
        """
        with self._get_connection() as conn:
            # Get old session IDs
            old_sessions = conn.execute("""
                SELECT session_id
                FROM billing_sessions
                WHERE updated_at < datetime('now', ?)
            """, (f"-{days} days",)).fetchall()

            session_ids = [row["session_id"] for row in old_sessions]

            if session_ids:
                placeholders = ",".join("?" * len(session_ids))
                conn.execute(f"DELETE FROM billing_messages WHERE session_id IN ({placeholders})", session_ids)
                conn.execute(f"DELETE FROM billing_sessions WHERE session_id IN ({placeholders})", session_ids)

        if session_ids:
            logger.info(f"Cleaned up {len(session_ids)} old billing sessions")

        return len(session_ids)
