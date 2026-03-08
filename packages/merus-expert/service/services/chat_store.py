# @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""
Chat Store - SQLite persistence for chat conversations
Manages conversation state and message history
"""

import sqlite3
import json
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

from service.services.conversation_flow import ConversationContext, ConversationState

logger = logging.getLogger(__name__)


class ChatStore:
    """
    Persistent storage for chat conversations.

    Stores conversation state and message history in SQLite.
    """

    def __init__(self, db_path: str = "./knowledge/db/merus_knowledge.db"):
        """
        Initialize chat store.

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
        """Create chat tables if they don't exist"""
        with self._get_connection() as conn:
            # Chat conversations table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_conversations (
                    conversation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT UNIQUE NOT NULL,
                    state TEXT NOT NULL DEFAULT 'greeting',
                    collected_data TEXT,
                    retry_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Chat messages table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_messages (
                    message_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
                    content TEXT NOT NULL,
                    metadata TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create indexes
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_chat_messages_session
                ON chat_messages(session_id, timestamp)
            """)

            logger.info("Chat tables initialized")

    def create_session(self, session_id: str) -> ConversationContext:
        """
        Create a new chat session.

        Args:
            session_id: Unique session identifier

        Returns:
            New ConversationContext
        """
        context = ConversationContext(session_id=session_id)

        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO chat_conversations (session_id, state, collected_data)
                VALUES (?, ?, ?)
            """, (session_id, context.state.value, json.dumps(context.collected_data)))

        logger.info(f"Created chat session: {session_id}")
        return context

    def get_context(self, session_id: str) -> Optional[ConversationContext]:
        """
        Get conversation context for session.

        Args:
            session_id: Session identifier

        Returns:
            ConversationContext or None if not found
        """
        with self._get_connection() as conn:
            row = conn.execute("""
                SELECT state, collected_data, retry_count
                FROM chat_conversations
                WHERE session_id = ?
            """, (session_id,)).fetchone()

            if not row:
                return None

            # Parse collected_data from JSON
            collected_data = {}
            if row['collected_data']:
                try:
                    collected_data = json.loads(row['collected_data'])
                    # Convert case_type back to enum if present
                    if 'case_type' in collected_data and collected_data['case_type']:
                        from merus_expert.models.matter import CaseType
                        case_type_str = collected_data['case_type']
                        # Handle both string value and enum value formats
                        for ct in CaseType:
                            if ct.value == case_type_str or ct.name == case_type_str:
                                collected_data['case_type'] = ct
                                break
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse collected_data for session {session_id}")

            return ConversationContext(
                session_id=session_id,
                state=ConversationState(row['state']),
                collected_data=collected_data,
                retry_count=row['retry_count'] or 0
            )

    def save_context(self, context: ConversationContext) -> None:
        """
        Save conversation context.

        Args:
            context: ConversationContext to save
        """
        # Serialize collected_data, handling enums
        collected_data = {}
        for key, value in context.collected_data.items():
            if hasattr(value, 'value'):  # Enum
                collected_data[key] = value.value
            else:
                collected_data[key] = value

        with self._get_connection() as conn:
            conn.execute("""
                UPDATE chat_conversations
                SET state = ?, collected_data = ?, retry_count = ?, updated_at = ?
                WHERE session_id = ?
            """, (
                context.state.value if hasattr(context.state, 'value') else context.state,
                json.dumps(collected_data),
                context.retry_count,
                datetime.now().isoformat(),
                context.session_id
            ))

        logger.debug(f"Saved context for session {context.session_id}")

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Add a message to chat history.

        Args:
            session_id: Session identifier
            role: 'user' or 'assistant'
            content: Message content
            metadata: Optional metadata

        Returns:
            Message ID
        """
        with self._get_connection() as conn:
            cursor = conn.execute("""
                INSERT INTO chat_messages (session_id, role, content, metadata)
                VALUES (?, ?, ?, ?)
            """, (session_id, role, content, json.dumps(metadata) if metadata else None))

            return cursor.lastrowid

    def get_messages(self, session_id: str) -> List[Dict[str, Any]]:
        """
        Get all messages for a session.

        Args:
            session_id: Session identifier

        Returns:
            List of message dictionaries
        """
        with self._get_connection() as conn:
            rows = conn.execute("""
                SELECT role, content, timestamp, metadata
                FROM chat_messages
                WHERE session_id = ?
                ORDER BY timestamp ASC
            """, (session_id,)).fetchall()

            messages = []
            for row in rows:
                msg = {
                    'role': row['role'],
                    'content': row['content'],
                    'timestamp': row['timestamp']
                }
                if row['metadata']:
                    try:
                        msg['metadata'] = json.loads(row['metadata'])
                    except json.JSONDecodeError:
                        pass
                messages.append(msg)

            return messages

    def session_exists(self, session_id: str) -> bool:
        """Check if session exists"""
        with self._get_connection() as conn:
            row = conn.execute("""
                SELECT 1 FROM chat_conversations WHERE session_id = ?
            """, (session_id,)).fetchone()
            return row is not None

    def delete_session(self, session_id: str) -> bool:
        """
        Delete a chat session and its messages.

        Args:
            session_id: Session identifier

        Returns:
            True if deleted
        """
        with self._get_connection() as conn:
            # Delete messages first
            conn.execute("""
                DELETE FROM chat_messages WHERE session_id = ?
            """, (session_id,))

            # Delete conversation
            cursor = conn.execute("""
                DELETE FROM chat_conversations WHERE session_id = ?
            """, (session_id,))

            deleted = cursor.rowcount > 0
            if deleted:
                logger.info(f"Deleted chat session: {session_id}")
            return deleted
