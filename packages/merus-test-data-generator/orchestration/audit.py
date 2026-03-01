"""
SOC2-compliant audit logger with HMAC-chained integrity verification.

Provides tamper-evident logging for pipeline operations, credential access,
document operations, and API calls.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class EventCategory(str, Enum):
    CREDENTIAL_ACCESS = "CREDENTIAL_ACCESS"
    PIPELINE_OPERATIONS = "PIPELINE_OPERATIONS"
    DOCUMENT_OPERATIONS = "DOCUMENT_OPERATIONS"
    API_OPERATIONS = "API_OPERATIONS"


class EventStatus(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    ERROR = "error"
    START = "start"
    COMPLETE = "complete"


_DEFAULT_RETENTION_DAYS = 90


class PipelineAuditLogger:
    """SOC2 audit logger with HMAC-chained records stored in SQLite."""

    def __init__(self, db_path: str | Path, hmac_key: str = ""):
        self._db_path = str(db_path)
        self._hmac_key = (hmac_key or os.urandom(32).hex()).encode("utf-8")
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self._db_path)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
        return self._conn

    def _init_db(self) -> None:
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                event_id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                event_category TEXT NOT NULL,
                event_type TEXT NOT NULL,
                action TEXT NOT NULL,
                actor TEXT NOT NULL DEFAULT 'system',
                resource TEXT,
                status TEXT NOT NULL,
                metadata TEXT,
                hmac_hash TEXT NOT NULL,
                previous_hash TEXT NOT NULL DEFAULT '',
                retention_until TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_timestamp
            ON audit_log(timestamp)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_category
            ON audit_log(event_category)
        """)
        conn.commit()

    def _compute_hmac(
        self,
        event_id: str,
        timestamp: str,
        category: str,
        status: str,
        previous_hash: str,
    ) -> str:
        message = f"{event_id}{timestamp}{category}{status}{previous_hash}"
        return hmac.new(
            self._hmac_key, message.encode("utf-8"), hashlib.sha256
        ).hexdigest()

    def _get_last_hash(self) -> str:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT hmac_hash FROM audit_log ORDER BY rowid DESC LIMIT 1"
        ).fetchone()
        return row["hmac_hash"] if row else ""

    def _log_event(
        self,
        category: EventCategory,
        event_type: str,
        action: str,
        status: EventStatus,
        actor: str = "system",
        resource: str | None = None,
        metadata: dict[str, Any] | None = None,
        retention_days: int = _DEFAULT_RETENTION_DAYS,
    ) -> str:
        event_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        timestamp = now.isoformat()
        retention_until = (now + timedelta(days=retention_days)).isoformat()
        previous_hash = self._get_last_hash()

        hmac_hash = self._compute_hmac(
            event_id, timestamp, category.value, status.value, previous_hash
        )

        conn = self._get_conn()
        conn.execute(
            """INSERT INTO audit_log
               (event_id, timestamp, event_category, event_type, action,
                actor, resource, status, metadata, hmac_hash, previous_hash,
                retention_until)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event_id,
                timestamp,
                category.value,
                event_type,
                action,
                actor,
                resource,
                status.value,
                json.dumps(metadata) if metadata else None,
                hmac_hash,
                previous_hash,
                retention_until,
            ),
        )
        conn.commit()
        return event_id

    # --- Convenience methods ---

    def log_pipeline_start(self, run_id: int, total_cases: int) -> str:
        return self._log_event(
            category=EventCategory.PIPELINE_OPERATIONS,
            event_type="pipeline_start",
            action="Pipeline execution started",
            status=EventStatus.START,
            resource=f"run:{run_id}",
            metadata={"total_cases": total_cases},
        )

    def log_pipeline_complete(
        self, run_id: int, results: dict[str, Any]
    ) -> str:
        return self._log_event(
            category=EventCategory.PIPELINE_OPERATIONS,
            event_type="pipeline_complete",
            action="Pipeline execution completed",
            status=EventStatus.COMPLETE,
            resource=f"run:{run_id}",
            metadata={"results_summary": {
                k: v for k, v in results.items()
                if isinstance(v, (int, str, float, bool, dict))
            }},
        )

    def log_case_created(
        self, case_id: str, meruscase_id: int | None, success: bool
    ) -> str:
        return self._log_event(
            category=EventCategory.PIPELINE_OPERATIONS,
            event_type="case_created",
            action=f"Case {case_id} {'created' if success else 'failed'}",
            status=EventStatus.SUCCESS if success else EventStatus.FAILURE,
            resource=f"case:{case_id}",
            metadata={"meruscase_id": meruscase_id},
        )

    def log_document_uploaded(
        self,
        case_id: str,
        filename: str,
        success: bool,
        doc_id: int | None = None,
    ) -> str:
        return self._log_event(
            category=EventCategory.DOCUMENT_OPERATIONS,
            event_type="document_uploaded",
            action=f"Document {filename} {'uploaded' if success else 'upload failed'}",
            status=EventStatus.SUCCESS if success else EventStatus.FAILURE,
            resource=f"case:{case_id}/doc:{filename}",
            metadata={"document_id": doc_id},
        )

    def log_credential_access(
        self, secret_name: str, source: str, success: bool
    ) -> str:
        return self._log_event(
            category=EventCategory.CREDENTIAL_ACCESS,
            event_type="credential_access",
            action=f"Accessed {secret_name} from {source}",
            status=EventStatus.SUCCESS if success else EventStatus.FAILURE,
            resource=f"secret:{secret_name}",
            metadata={"source": source},
        )

    def log_api_call(
        self,
        method: str,
        endpoint: str,
        status_code: int | None = None,
        success: bool = True,
    ) -> str:
        return self._log_event(
            category=EventCategory.API_OPERATIONS,
            event_type="api_call",
            action=f"{method} {endpoint}",
            status=EventStatus.SUCCESS if success else EventStatus.FAILURE,
            resource=f"api:{endpoint}",
            metadata={"method": method, "status_code": status_code},
        )

    def log_error(
        self,
        category: EventCategory,
        event_type: str,
        error_message: str,
        resource: str | None = None,
    ) -> str:
        return self._log_event(
            category=category,
            event_type=event_type,
            action=error_message,
            status=EventStatus.ERROR,
            resource=resource,
        )

    # --- Verification ---

    def verify_chain(self) -> dict[str, Any]:
        """Validate the entire HMAC chain. Returns pass/fail with details."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM audit_log ORDER BY rowid ASC"
        ).fetchall()

        if not rows:
            return {"valid": True, "total": 0, "errors": []}

        errors: list[dict[str, str]] = []
        expected_prev = ""

        for row in rows:
            expected_hmac = self._compute_hmac(
                row["event_id"],
                row["timestamp"],
                row["event_category"],
                row["status"],
                expected_prev,
            )
            if row["hmac_hash"] != expected_hmac:
                errors.append({
                    "event_id": row["event_id"],
                    "timestamp": row["timestamp"],
                    "expected_prev": expected_prev,
                    "stored_prev": row["previous_hash"],
                })
            if row["previous_hash"] != expected_prev:
                errors.append({
                    "event_id": row["event_id"],
                    "timestamp": row["timestamp"],
                    "issue": "previous_hash mismatch",
                    "expected": expected_prev,
                    "stored": row["previous_hash"],
                })
            expected_prev = row["hmac_hash"]

        return {
            "valid": len(errors) == 0,
            "total": len(rows),
            "errors": errors,
        }

    # --- Query helpers ---

    def get_stats(self) -> dict[str, int]:
        """Event counts by category."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT event_category, COUNT(*) as cnt FROM audit_log GROUP BY event_category"
        ).fetchall()
        stats = {row["event_category"]: row["cnt"] for row in rows}
        total = conn.execute("SELECT COUNT(*) as cnt FROM audit_log").fetchone()
        stats["TOTAL"] = total["cnt"] if total else 0
        return stats

    def get_recent(self, limit: int = 20) -> list[dict[str, Any]]:
        """Get recent audit events."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM audit_log ORDER BY rowid DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(row) for row in rows]

    # --- Retention ---

    def cleanup_expired(self) -> int:
        """Delete records past their retention date. Returns count deleted."""
        conn = self._get_conn()
        now = datetime.now(timezone.utc).isoformat()
        cursor = conn.execute(
            "DELETE FROM audit_log WHERE retention_until < ?", (now,)
        )
        conn.commit()
        return cursor.rowcount

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
