"""
Session Store for MerusCase Matter Automation
Manages agent session state with timeout enforcement and lifecycle tracking
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from pathlib import Path

from .constants import AgentPhase, DEFAULT_SESSION_TIMEOUT_MIN, DEFAULT_MAX_SESSION_HOURS
from .utils import (
    safe_json_parse,
    safe_json_dump,
    validate_session_id,
    get_db_connection,
    initialize_database,
    row_to_dict
)

logger = logging.getLogger(__name__)


class SessionStore:
    """
    Store and retrieve agent session state with SOC2-compliant timeout enforcement.

    Sessions track:
    - Agent phase (INITIALIZATION → READY → EXECUTING → COMPLETED/ERROR)
    - Workflow progress and retry counts
    - Session timeouts (30 min inactivity, 8 hr maximum)
    - Active/inactive status
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize session store.

        Args:
            db_path: Path to SQLite database. If None, uses DB_PATH env var
                    or defaults to ./knowledge/db/merus_knowledge.db
        """
        if db_path:
            self.db_path = db_path
        else:
            self.db_path = os.getenv('DB_PATH', './knowledge/db/merus_knowledge.db')

        # Load timeout settings from environment
        self.session_timeout_min = int(os.getenv(
            'MERUS_SESSION_TIMEOUT_MIN',
            DEFAULT_SESSION_TIMEOUT_MIN
        ))
        self.max_session_hours = int(os.getenv(
            'MERUS_MAX_SESSION_HOURS',
            DEFAULT_MAX_SESSION_HOURS
        ))

        # Ensure parent directory exists
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        # Initialize database
        self._init_db()
        logger.info("SessionStore initialized with database: %s", self.db_path)
        logger.info(
            "Session timeout: %d min, max duration: %d hours",
            self.session_timeout_min,
            self.max_session_hours
        )

    def _init_db(self):
        """Initialize database schema from schema.sql if not exists"""
        db_exists = os.path.exists(self.db_path)

        if not db_exists:
            # Find schema file
            schema_path = Path(__file__).parent.parent / 'setup' / 'schema.sql'
            if not schema_path.exists():
                error_msg = f"Database schema not found at {schema_path}. Cannot initialize database."
                logger.error(error_msg)
                raise FileNotFoundError(error_msg)

            # Initialize database
            initialize_database(self.db_path, str(schema_path))
            logger.info("Database initialized at %s", self.db_path)
        else:
            # Verify schema version
            try:
                with get_db_connection(self.db_path) as conn:
                    cursor = conn.execute(
                        "SELECT version FROM schema_version ORDER BY applied_at DESC LIMIT 1"
                    )
                    version = cursor.fetchone()
                    if version:
                        logger.info("Database schema version: %s", version[0])
            except Exception as e:
                logger.warning("Could not verify schema version: %s", e)

    def create_session(
        self,
        session_id: str,
        agent_phase: str = AgentPhase.INITIALIZATION.value,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a new agent session.

        Args:
            session_id: Unique session identifier
            agent_phase: Initial agent phase (default: INITIALIZATION)
            metadata: Optional metadata dictionary

        Returns:
            Created session dictionary

        Raises:
            ValueError: If session_id is invalid or session already exists
        """
        validate_session_id(session_id)

        # Verify agent phase is valid
        if agent_phase not in [p.value for p in AgentPhase]:
            raise ValueError(f"Invalid agent_phase: {agent_phase}")

        now = datetime.now()
        expires_at = now + timedelta(minutes=self.session_timeout_min)
        max_expiry_at = now + timedelta(hours=self.max_session_hours)

        session_data = {
            'session_id': session_id,
            'agent_phase': agent_phase,
            'current_workflow': None,
            'workflow_step': 0,
            'retry_count': 0,
            'is_active': 1,
            'metadata': safe_json_dump(metadata) if metadata else None,
            'started_at': now.isoformat(),
            'last_active_at': now.isoformat(),
            'ended_at': None,
            '_expires_at': expires_at.isoformat(),  # Not in DB, used for validation
            '_max_expiry_at': max_expiry_at.isoformat()  # Not in DB, stored in metadata
        }

        # Add timeout info to metadata
        if metadata is None:
            metadata = {}
        metadata['timeout_config'] = {
            'inactivity_timeout_min': self.session_timeout_min,
            'max_duration_hours': self.max_session_hours,
            'expires_at': expires_at.isoformat(),
            'max_expiry_at': max_expiry_at.isoformat()
        }
        session_data['metadata'] = safe_json_dump(metadata)

        with get_db_connection(self.db_path) as conn:
            try:
                conn.execute("""
                    INSERT INTO sessions (
                        session_id, agent_phase, current_workflow, workflow_step,
                        retry_count, is_active, metadata, started_at, last_active_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    session_data['session_id'],
                    session_data['agent_phase'],
                    session_data['current_workflow'],
                    session_data['workflow_step'],
                    session_data['retry_count'],
                    session_data['is_active'],
                    session_data['metadata'],
                    session_data['started_at'],
                    session_data['last_active_at']
                ))
                conn.commit()

                logger.info(
                    "Created session %s in phase %s (timeout: %d min, max: %d hr)",
                    session_id,
                    agent_phase,
                    self.session_timeout_min,
                    self.max_session_hours
                )

                return self.get_session(session_id)

            except Exception as e:
                logger.error("Failed to create session %s: %s", session_id, e, exc_info=True)
                raise

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve session by ID.

        Args:
            session_id: Session identifier

        Returns:
            Session dictionary or None if not found
        """
        validate_session_id(session_id)

        with get_db_connection(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?",
                (session_id,)
            )
            row = cursor.fetchone()

            if not row:
                return None

            session = row_to_dict(row, json_fields=['metadata'])
            return session

    def validate_session(self, session_id: str) -> bool:
        """
        Validate if session is still active and not expired.

        Checks:
        1. Session exists
        2. Session is marked active
        3. Not past maximum duration (8 hours)
        4. Not past inactivity timeout (30 minutes)

        Args:
            session_id: Session identifier

        Returns:
            True if session is valid, False otherwise
        """
        session = self.get_session(session_id)

        if not session:
            logger.warning("Session %s not found", session_id)
            return False

        if not session['is_active']:
            logger.warning("Session %s is inactive", session_id)
            return False

        now = datetime.now()
        started_at = datetime.fromisoformat(session['started_at'])
        last_active_at = datetime.fromisoformat(session['last_active_at'])

        # Check maximum duration
        max_duration = timedelta(hours=self.max_session_hours)
        if now - started_at > max_duration:
            logger.warning(
                "Session %s exceeded max duration (%d hours)",
                session_id,
                self.max_session_hours
            )
            self.end_session(session_id, reason='max_duration_exceeded')
            return False

        # Check inactivity timeout
        inactivity_timeout = timedelta(minutes=self.session_timeout_min)
        if now - last_active_at > inactivity_timeout:
            logger.warning(
                "Session %s exceeded inactivity timeout (%d minutes)",
                session_id,
                self.session_timeout_min
            )
            self.end_session(session_id, reason='inactivity_timeout')
            return False

        # Session is valid - extend expiry
        self._update_last_active(session_id)
        return True

    def _update_last_active(self, session_id: str):
        """Update last_active_at timestamp"""
        with get_db_connection(self.db_path) as conn:
            conn.execute(
                "UPDATE sessions SET last_active_at = ? WHERE session_id = ?",
                (datetime.now().isoformat(), session_id)
            )
            conn.commit()

    def update_phase(self, session_id: str, agent_phase: str) -> bool:
        """
        Update agent phase for session.

        Args:
            session_id: Session identifier
            agent_phase: New agent phase

        Returns:
            True if updated successfully

        Raises:
            ValueError: If phase is invalid or session not found
        """
        validate_session_id(session_id)

        if agent_phase not in [p.value for p in AgentPhase]:
            raise ValueError(f"Invalid agent_phase: {agent_phase}")

        if not self.validate_session(session_id):
            raise ValueError(f"Session {session_id} is not valid or has expired")

        with get_db_connection(self.db_path) as conn:
            cursor = conn.execute(
                "UPDATE sessions SET agent_phase = ? WHERE session_id = ?",
                (agent_phase, session_id)
            )
            conn.commit()

            if cursor.rowcount == 0:
                logger.error("Session %s not found for phase update", session_id)
                return False

            logger.info("Updated session %s to phase %s", session_id, agent_phase)
            return True

    def update_workflow(
        self,
        session_id: str,
        workflow: str,
        step: int = 0
    ) -> bool:
        """
        Update current workflow and step.

        Args:
            session_id: Session identifier
            workflow: Workflow name
            step: Current step number

        Returns:
            True if updated successfully
        """
        validate_session_id(session_id)

        if not self.validate_session(session_id):
            raise ValueError(f"Session {session_id} is not valid or has expired")

        with get_db_connection(self.db_path) as conn:
            conn.execute("""
                UPDATE sessions
                SET current_workflow = ?, workflow_step = ?
                WHERE session_id = ?
            """, (workflow, step, session_id))
            conn.commit()

            logger.info(
                "Updated session %s workflow: %s (step %d)",
                session_id,
                workflow,
                step
            )
            return True

    def increment_retry(self, session_id: str) -> int:
        """
        Increment retry count for session.

        Args:
            session_id: Session identifier

        Returns:
            New retry count
        """
        validate_session_id(session_id)

        with get_db_connection(self.db_path) as conn:
            cursor = conn.execute(
                "UPDATE sessions SET retry_count = retry_count + 1 WHERE session_id = ?",
                (session_id,)
            )
            conn.commit()

            if cursor.rowcount == 0:
                logger.error("Session %s not found for retry increment", session_id)
                return 0

            # Get updated count
            cursor = conn.execute(
                "SELECT retry_count FROM sessions WHERE session_id = ?",
                (session_id,)
            )
            row = cursor.fetchone()
            retry_count = row['retry_count'] if row else 0

            logger.info("Incremented retry count for session %s to %d", session_id, retry_count)
            return retry_count

    def end_session(self, session_id: str, reason: str = 'completed') -> bool:
        """
        End a session and mark it inactive.

        Args:
            session_id: Session identifier
            reason: Reason for ending (completed, timeout, error, etc.)

        Returns:
            True if session ended successfully
        """
        validate_session_id(session_id)

        with get_db_connection(self.db_path) as conn:
            cursor = conn.execute("""
                UPDATE sessions
                SET is_active = 0, ended_at = ?
                WHERE session_id = ?
            """, (datetime.now().isoformat(), session_id))
            conn.commit()

            if cursor.rowcount == 0:
                logger.warning("Session %s not found for end", session_id)
                return False

            logger.info("Ended session %s (reason: %s)", session_id, reason)
            return True

    def get_active_sessions(self) -> List[Dict[str, Any]]:
        """
        Get all currently active sessions.

        Returns:
            List of active session dictionaries
        """
        with get_db_connection(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT * FROM sessions WHERE is_active = 1 ORDER BY started_at DESC"
            )
            rows = cursor.fetchall()

            sessions = [row_to_dict(row, json_fields=['metadata']) for row in rows]
            return sessions

    def cleanup_expired_sessions(self) -> int:
        """
        Clean up sessions that have exceeded their timeout.

        Should be run periodically to maintain database hygiene.

        Returns:
            Number of sessions cleaned up
        """
        now = datetime.now()
        inactivity_cutoff = now - timedelta(minutes=self.session_timeout_min)
        max_duration_cutoff = now - timedelta(hours=self.max_session_hours)

        with get_db_connection(self.db_path) as conn:
            # End sessions past inactivity timeout
            cursor = conn.execute("""
                UPDATE sessions
                SET is_active = 0, ended_at = ?
                WHERE is_active = 1
                  AND (
                      datetime(last_active_at) < ?
                      OR datetime(started_at) < ?
                  )
            """, (
                now.isoformat(),
                inactivity_cutoff.isoformat(),
                max_duration_cutoff.isoformat()
            ))
            conn.commit()

            cleaned_count = cursor.rowcount

            if cleaned_count > 0:
                logger.info("Cleaned up %d expired sessions", cleaned_count)

            return cleaned_count
