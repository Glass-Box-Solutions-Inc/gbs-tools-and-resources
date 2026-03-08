"""
Spectacles Audit Logger
SOC2-compliant audit logging for all agent operations
"""

import os
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

from persistence.constants import AuditEventType
from persistence.utils import get_db_connection, safe_json_dump, row_to_dict

logger = logging.getLogger(__name__)


class AuditLogger:
    """
    SOC2-compliant audit logging.

    Logs all significant operations with:
    - Event type and action
    - Status (success/failure)
    - Associated task/session
    - Timestamp
    - Additional metadata

    Retention: 90 days (configurable)
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize audit logger.

        Args:
            db_path: Path to SQLite database
        """
        self.db_path = db_path or os.getenv('DB_PATH', './spectacles.db')
        logger.info("AuditLogger initialized with database: %s", self.db_path)

    def log(
        self,
        event_type: AuditEventType,
        action: str,
        status: str,
        task_id: Optional[str] = None,
        session_id: Optional[str] = None,
        resource: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Log an audit event.

        Args:
            event_type: Type of event (AUTHENTICATION, BROWSER_AUTOMATION, etc.)
            action: Specific action performed
            status: SUCCESS or FAILURE
            task_id: Associated task ID
            session_id: Associated session ID
            resource: Resource being accessed/modified
            metadata: Additional context

        Returns:
            Audit log entry ID
        """
        try:
            with get_db_connection(self.db_path) as conn:
                cursor = conn.execute("""
                    INSERT INTO audit_log (
                        event_type, action, status, task_id,
                        session_id, resource, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    event_type.value if isinstance(event_type, AuditEventType) else event_type,
                    action,
                    status,
                    task_id,
                    session_id,
                    resource,
                    safe_json_dump(metadata)
                ))
                conn.commit()
                entry_id = cursor.lastrowid

            logger.debug(
                "Audit: [%s] %s - %s (task=%s)",
                event_type, action, status, task_id
            )
            return entry_id

        except Exception as e:
            logger.error("Failed to write audit log: %s", e)
            return -1

    def log_authentication(
        self,
        action: str,
        status: str,
        task_id: Optional[str] = None,
        resource: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """Log authentication event"""
        return self.log(
            AuditEventType.AUTHENTICATION,
            action, status, task_id,
            resource=resource, metadata=metadata
        )

    def log_browser_action(
        self,
        action: str,
        status: str,
        task_id: str,
        resource: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """Log browser automation event"""
        return self.log(
            AuditEventType.BROWSER_AUTOMATION,
            action, status, task_id,
            resource=resource, metadata=metadata
        )

    def log_hitl(
        self,
        action: str,
        status: str,
        task_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """Log HITL interaction event"""
        return self.log(
            AuditEventType.HITL_INTERACTION,
            action, status, task_id,
            metadata=metadata
        )

    def log_credential_access(
        self,
        action: str,
        status: str,
        task_id: Optional[str] = None,
        resource: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """Log credential access event"""
        return self.log(
            AuditEventType.CREDENTIAL_ACCESS,
            action, status, task_id,
            resource=resource, metadata=metadata
        )

    def log_security_event(
        self,
        action: str,
        status: str,
        task_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """Log security event"""
        return self.log(
            AuditEventType.SECURITY_EVENT,
            action, status, task_id,
            metadata=metadata
        )

    def log_task_lifecycle(
        self,
        action: str,
        status: str,
        task_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """Log task lifecycle event"""
        return self.log(
            AuditEventType.TASK_LIFECYCLE,
            action, status, task_id,
            metadata=metadata
        )

    def get_logs(
        self,
        task_id: Optional[str] = None,
        event_type: Optional[AuditEventType] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Retrieve audit logs.

        Args:
            task_id: Filter by task ID
            event_type: Filter by event type
            limit: Maximum records to return
            offset: Offset for pagination

        Returns:
            List of audit log entries
        """
        conditions = []
        params = []

        if task_id:
            conditions.append("task_id = ?")
            params.append(task_id)

        if event_type:
            conditions.append("event_type = ?")
            params.append(event_type.value if isinstance(event_type, AuditEventType) else event_type)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        with get_db_connection(self.db_path) as conn:
            cursor = conn.execute(f"""
                SELECT * FROM audit_log
                WHERE {where_clause}
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            """, params + [limit, offset])
            rows = cursor.fetchall()

        return [row_to_dict(row) for row in rows]

    def cleanup_old_logs(self, retention_days: int = 90) -> int:
        """
        Clean up logs older than retention period.

        Args:
            retention_days: Days to retain logs

        Returns:
            Number of records deleted
        """
        with get_db_connection(self.db_path) as conn:
            cursor = conn.execute("""
                DELETE FROM audit_log
                WHERE created_at < datetime('now', ?)
            """, (f'-{retention_days} days',))
            count = cursor.rowcount
            conn.commit()

        logger.info("Cleaned up %d audit log entries older than %d days", count, retention_days)
        return count


# Singleton instance
_audit_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    """Get singleton AuditLogger instance"""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger
