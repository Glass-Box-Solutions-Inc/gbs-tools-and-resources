"""
Audit Store for SOC2 Compliance
Manages audit logging with 90-day retention and structured event tracking
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from .constants import (
    AuditEventCategory,
    AuditEventStatus,
    DEFAULT_AUDIT_RETENTION_DAYS,
    SOC2_CONTROLS
)
from .utils import (
    safe_json_dump,
    get_db_connection,
    row_to_dict
)

logger = logging.getLogger(__name__)


class AuditStore:
    """
    Store and retrieve SOC2-compliant audit events.

    Features:
    - Structured event logging with categories
    - 90-day automatic retention
    - SOC2 control mapping
    - Screenshot path tracking
    - Query by session, category, type, status
    """

    def __init__(self, db_path: str, retention_days: Optional[int] = None):
        """
        Initialize audit store.

        Args:
            db_path: Path to SQLite database
            retention_days: Audit log retention period (default: 90 days)
        """
        self.db_path = db_path
        self.retention_days = retention_days or DEFAULT_AUDIT_RETENTION_DAYS
        logger.info(
            "AuditStore initialized with database: %s (retention: %d days)",
            db_path,
            self.retention_days
        )

    def log_event(
        self,
        event_category: str,
        event_type: str,
        action: str,
        status: str,
        session_id: Optional[str] = None,
        actor: str = "merus_agent",
        resource: Optional[str] = None,
        screenshot_path: Optional[str] = None,
        ip_address: Optional[str] = None,
        soc2_control: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Log an audit event.

        Args:
            event_category: Category (AUTHENTICATION, MATTER_OPERATIONS, etc.)
            event_type: Specific event type (login_attempt, matter_submitted, etc.)
            action: Action taken (create, navigate, submit, etc.)
            status: Event status (SUCCESS, FAILURE, WARNING, PENDING)
            session_id: Associated session ID (optional)
            actor: Who performed the action (default: merus_agent)
            resource: Resource affected (URL, matter ID, etc.)
            screenshot_path: Path to associated screenshot
            ip_address: IP address of actor
            soc2_control: SOC2 control reference (CC6.6, CC6.8, etc.)
            metadata: Additional event-specific data

        Returns:
            Event ID (UUID)

        Raises:
            ValueError: If category or status invalid
        """
        # Validate category
        if event_category not in [c.value for c in AuditEventCategory]:
            raise ValueError(f"Invalid event_category: {event_category}")

        # Validate status
        if status not in [s.value for s in AuditEventStatus]:
            raise ValueError(f"Invalid status: {status}")

        event_id = str(uuid.uuid4())
        now = datetime.now()
        retention_until = now + timedelta(days=self.retention_days)

        event_data = {
            'event_id': event_id,
            'session_id': session_id,
            'event_category': event_category,
            'event_type': event_type,
            'action': action,
            'actor': actor,
            'resource': resource,
            'status': status,
            'screenshot_path': screenshot_path,
            'ip_address': ip_address,
            'soc2_control': soc2_control,
            'metadata': safe_json_dump(metadata),
            'timestamp': now.isoformat(),
            'retention_until': retention_until.isoformat()
        }

        with get_db_connection(self.db_path) as conn:
            conn.execute("""
                INSERT INTO audit_log (
                    event_id, session_id, event_category, event_type, action,
                    actor, resource, status, screenshot_path, ip_address,
                    soc2_control, metadata, timestamp, retention_until
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                event_data['event_id'],
                event_data['session_id'],
                event_data['event_category'],
                event_data['event_type'],
                event_data['action'],
                event_data['actor'],
                event_data['resource'],
                event_data['status'],
                event_data['screenshot_path'],
                event_data['ip_address'],
                event_data['soc2_control'],
                event_data['metadata'],
                event_data['timestamp'],
                event_data['retention_until']
            ))
            conn.commit()

            logger.debug(
                "Logged audit event %s: %s/%s [%s]",
                event_id,
                event_category,
                event_type,
                status
            )

            return event_id

    def get_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve audit event by ID.

        Args:
            event_id: Event identifier

        Returns:
            Event dictionary or None if not found
        """
        with get_db_connection(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT * FROM audit_log WHERE event_id = ?",
                (event_id,)
            )
            row = cursor.fetchone()

            if not row:
                return None

            event = row_to_dict(row, json_fields=['metadata'])
            return event

    def get_session_events(
        self,
        session_id: str,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all audit events for a session.

        Args:
            session_id: Session identifier
            limit: Maximum number of events to return

        Returns:
            List of event dictionaries in chronological order
        """
        with get_db_connection(self.db_path) as conn:
            if limit:
                cursor = conn.execute("""
                    SELECT * FROM audit_log
                    WHERE session_id = ?
                    ORDER BY timestamp ASC
                    LIMIT ?
                """, (session_id, limit))
            else:
                cursor = conn.execute("""
                    SELECT * FROM audit_log
                    WHERE session_id = ?
                    ORDER BY timestamp ASC
                """, (session_id,))

            rows = cursor.fetchall()
            events = [row_to_dict(row, json_fields=['metadata']) for row in rows]
            return events

    def get_events_by_category(
        self,
        category: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get events by category.

        Args:
            category: Event category
            limit: Maximum number of events

        Returns:
            List of event dictionaries
        """
        if category not in [c.value for c in AuditEventCategory]:
            raise ValueError(f"Invalid category: {category}")

        with get_db_connection(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT * FROM audit_log
                WHERE event_category = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (category, limit))

            rows = cursor.fetchall()
            events = [row_to_dict(row, json_fields=['metadata']) for row in rows]
            return events

    def get_failed_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get recent failed events for monitoring.

        Args:
            limit: Maximum number of events

        Returns:
            List of failed event dictionaries
        """
        with get_db_connection(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT * FROM audit_log
                WHERE status = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (AuditEventStatus.FAILURE.value, limit))

            rows = cursor.fetchall()
            events = [row_to_dict(row, json_fields=['metadata']) for row in rows]
            return events

    def cleanup_expired_events(self) -> int:
        """
        Delete audit events past retention period.

        Should be run daily as part of maintenance.

        Returns:
            Number of events deleted
        """
        now = datetime.now()

        with get_db_connection(self.db_path) as conn:
            cursor = conn.execute("""
                DELETE FROM audit_log
                WHERE datetime(retention_until) < datetime(?)
            """, (now.isoformat(),))
            conn.commit()

            deleted_count = cursor.rowcount

            if deleted_count > 0:
                logger.info(
                    "Cleaned up %d expired audit events (retention: %d days)",
                    deleted_count,
                    self.retention_days
                )

            return deleted_count

    def get_audit_stats(self) -> Dict[str, Any]:
        """
        Get audit log statistics.

        Returns:
            Dictionary with stats (total, by category, by status, etc.)
        """
        with get_db_connection(self.db_path) as conn:
            # Total events
            cursor = conn.execute("SELECT COUNT(*) as total FROM audit_log")
            total = cursor.fetchone()['total']

            # By category
            cursor = conn.execute("""
                SELECT event_category, COUNT(*) as count
                FROM audit_log
                GROUP BY event_category
            """)
            by_category = {row['event_category']: row['count'] for row in cursor.fetchall()}

            # By status
            cursor = conn.execute("""
                SELECT status, COUNT(*) as count
                FROM audit_log
                GROUP BY status
            """)
            by_status = {row['status']: row['count'] for row in cursor.fetchall()}

            # Events with screenshots
            cursor = conn.execute("""
                SELECT COUNT(*) as count
                FROM audit_log
                WHERE screenshot_path IS NOT NULL
            """)
            with_screenshots = cursor.fetchone()['count']

            # Events by SOC2 control
            cursor = conn.execute("""
                SELECT soc2_control, COUNT(*) as count
                FROM audit_log
                WHERE soc2_control IS NOT NULL
                GROUP BY soc2_control
            """)
            by_soc2_control = {row['soc2_control']: row['count'] for row in cursor.fetchall()}

            # Expiring soon (next 7 days)
            seven_days_from_now = datetime.now() + timedelta(days=7)
            cursor = conn.execute("""
                SELECT COUNT(*) as count
                FROM audit_log
                WHERE datetime(retention_until) < datetime(?)
            """, (seven_days_from_now.isoformat(),))
            expiring_soon = cursor.fetchone()['count']

            stats = {
                'total': total,
                'by_category': by_category,
                'by_status': by_status,
                'with_screenshots': with_screenshots,
                'by_soc2_control': by_soc2_control,
                'expiring_soon': expiring_soon,
                'retention_days': self.retention_days
            }

            return stats
