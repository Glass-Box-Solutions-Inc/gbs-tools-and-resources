"""
Audit Logger for SOC2 Compliance
Wrapper around audit_store.py for convenient logging
"""

import logging
from typing import Optional, Dict, Any

from persistence.audit_store import AuditStore
from persistence.constants import AuditEventCategory, AuditEventStatus


logger = logging.getLogger(__name__)


class AuditLogger:
    """
    Convenient wrapper for SOC2-compliant audit logging.

    Provides simplified methods for common audit operations.
    """

    def __init__(self, db_path: str, retention_days: int = 90):
        """
        Initialize audit logger.

        Args:
            db_path: Path to SQLite database
            retention_days: Audit log retention period
        """
        self.store = AuditStore(db_path, retention_days)
        logger.info("AuditLogger initialized")

    def log(
        self,
        event_type: str,
        action: str,
        status: str = AuditEventStatus.SUCCESS.value,
        session_id: Optional[str] = None,
        category: str = AuditEventCategory.MATTER_OPERATIONS.value,
        **kwargs
    ) -> str:
        """
        Log an audit event with simplified interface.

        Args:
            event_type: Type of event (login_attempt, matter_submitted, etc.)
            action: Action taken (create, navigate, submit, etc.)
            status: Event status (default: SUCCESS)
            session_id: Associated session ID
            category: Event category (default: MATTER_OPERATIONS)
            **kwargs: Additional fields (resource, metadata, etc.)

        Returns:
            Event ID
        """
        return self.store.log_event(
            event_category=category,
            event_type=event_type,
            action=action,
            status=status,
            session_id=session_id,
            **kwargs
        )

    def log_authentication(
        self,
        event_type: str,
        status: str,
        session_id: Optional[str] = None,
        **kwargs
    ) -> str:
        """Log authentication event"""
        return self.log(
            event_type=event_type,
            action="authenticate",
            status=status,
            session_id=session_id,
            category=AuditEventCategory.AUTHENTICATION.value,
            **kwargs
        )

    def log_matter_operation(
        self,
        event_type: str,
        action: str,
        status: str,
        session_id: str,
        **kwargs
    ) -> str:
        """Log matter creation operation"""
        return self.log(
            event_type=event_type,
            action=action,
            status=status,
            session_id=session_id,
            category=AuditEventCategory.MATTER_OPERATIONS.value,
            soc2_control="CC6.8",  # Audit logging control
            **kwargs
        )

    def log_browser_action(
        self,
        event_type: str,
        action: str,
        session_id: str,
        resource: Optional[str] = None,
        **kwargs
    ) -> str:
        """Log browser automation action"""
        return self.log(
            event_type=event_type,
            action=action,
            status=AuditEventStatus.SUCCESS.value,
            session_id=session_id,
            category=AuditEventCategory.BROWSER_AUTOMATION.value,
            resource=resource,
            **kwargs
        )

    def log_credential_access(
        self,
        event_type: str,
        session_id: Optional[str] = None,
        **kwargs
    ) -> str:
        """Log credential access event"""
        return self.log(
            event_type=event_type,
            action="access_credential",
            status=AuditEventStatus.SUCCESS.value,
            session_id=session_id,
            category=AuditEventCategory.CREDENTIAL_ACCESS.value,
            soc2_control="CC6.6",  # Encryption control
            **kwargs
        )

    def log_security_event(
        self,
        event_type: str,
        status: str,
        session_id: Optional[str] = None,
        **kwargs
    ) -> str:
        """Log security-related event"""
        return self.log(
            event_type=event_type,
            action="security_check",
            status=status,
            session_id=session_id,
            category=AuditEventCategory.SECURITY_EVENTS.value,
            **kwargs
        )
