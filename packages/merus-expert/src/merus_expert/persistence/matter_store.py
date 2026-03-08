"""
Matter Store for MerusCase Matter Automation
Tracks matter creation attempts, status, and results
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

from .constants import MatterStatus, MatterType
from .utils import (
    safe_json_parse,
    safe_json_dump,
    validate_session_id,
    validate_matter_id,
    get_db_connection,
    row_to_dict,
    handle_foreign_key_error
)

logger = logging.getLogger(__name__)


class MatterStore:
    """
    Store and retrieve matter creation records.

    Tracks:
    - Matter creation attempts
    - Primary party and case details
    - Success/failure status
    - MerusCase URLs and IDs
    - Screenshots and error messages
    """

    def __init__(self, db_path: str):
        """
        Initialize matter store.

        Args:
            db_path: Path to SQLite database
        """
        self.db_path = db_path
        logger.info("MatterStore initialized with database: %s", db_path)

    def create_matter(
        self,
        session_id: str,
        matter_type: str,
        primary_party: str,
        custom_fields: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        dry_run: bool = False
    ) -> int:
        """
        Create a new matter record.

        Args:
            session_id: Associated session ID
            matter_type: Type of matter (immigration, workers_comp, etc.)
            primary_party: Primary party name
            custom_fields: Case-specific fields
            metadata: Additional metadata
            dry_run: Whether this is a dry-run (no actual submission)

        Returns:
            Matter ID (auto-incremented)

        Raises:
            ValueError: If session doesn't exist or parameters invalid
        """
        validate_session_id(session_id)

        if matter_type not in [mt.value for mt in MatterType]:
            raise ValueError(f"Invalid matter_type: {matter_type}")

        if not primary_party or not primary_party.strip():
            raise ValueError("primary_party cannot be empty")

        matter_data = {
            'session_id': session_id,
            'matter_type': matter_type,
            'primary_party': primary_party.strip(),
            'status': MatterStatus.PENDING.value,
            'custom_fields': safe_json_dump(custom_fields),
            'metadata': safe_json_dump(metadata),
            'dry_run': 1 if dry_run else 0
        }

        with get_db_connection(self.db_path) as conn:
            try:
                cursor = conn.execute("""
                    INSERT INTO matters (
                        session_id, matter_type, primary_party, status,
                        custom_fields, metadata, dry_run
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    matter_data['session_id'],
                    matter_data['matter_type'],
                    matter_data['primary_party'],
                    matter_data['status'],
                    matter_data['custom_fields'],
                    matter_data['metadata'],
                    matter_data['dry_run']
                ))
                conn.commit()

                matter_id = cursor.lastrowid
                logger.info(
                    "Created matter %d for session %s: %s (%s) %s",
                    matter_id,
                    session_id,
                    primary_party,
                    matter_type,
                    "[DRY-RUN]" if dry_run else ""
                )
                return matter_id

            except Exception as e:
                handle_foreign_key_error(e, f"create_matter for session {session_id}")
                raise

    def get_matter(self, matter_id: int) -> Optional[Dict[str, Any]]:
        """
        Retrieve matter by ID.

        Args:
            matter_id: Matter identifier

        Returns:
            Matter dictionary or None if not found
        """
        validate_matter_id(matter_id)

        with get_db_connection(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT * FROM matters WHERE matter_id = ?",
                (matter_id,)
            )
            row = cursor.fetchone()

            if not row:
                return None

            matter = row_to_dict(row, json_fields=['custom_fields', 'metadata'])
            return matter

    def update_status(
        self,
        matter_id: int,
        status: str,
        error_message: Optional[str] = None
    ) -> bool:
        """
        Update matter status.

        Args:
            matter_id: Matter identifier
            status: New status (pending, in_progress, success, failed, needs_review)
            error_message: Optional error message if status is failed

        Returns:
            True if updated successfully
        """
        validate_matter_id(matter_id)

        if status not in [s.value for s in MatterStatus]:
            raise ValueError(f"Invalid status: {status}")

        with get_db_connection(self.db_path) as conn:
            cursor = conn.execute("""
                UPDATE matters
                SET status = ?, error_message = ?
                WHERE matter_id = ?
            """, (status, error_message, matter_id))
            conn.commit()

            if cursor.rowcount == 0:
                logger.warning("Matter %d not found for status update", matter_id)
                return False

            logger.info("Updated matter %d status to %s", matter_id, status)
            return True

    def update_meruscase_info(
        self,
        matter_id: int,
        meruscase_matter_id: Optional[str] = None,
        meruscase_url: Optional[str] = None
    ) -> bool:
        """
        Update MerusCase-specific information.

        Args:
            matter_id: Matter identifier
            meruscase_matter_id: MerusCase's internal matter ID
            meruscase_url: URL to matter in MerusCase

        Returns:
            True if updated successfully
        """
        validate_matter_id(matter_id)

        with get_db_connection(self.db_path) as conn:
            cursor = conn.execute("""
                UPDATE matters
                SET meruscase_matter_id = ?, meruscase_url = ?
                WHERE matter_id = ?
            """, (meruscase_matter_id, meruscase_url, matter_id))
            conn.commit()

            if cursor.rowcount == 0:
                logger.warning("Matter %d not found for MerusCase info update", matter_id)
                return False

            logger.info(
                "Updated matter %d: meruscase_id=%s, url=%s",
                matter_id,
                meruscase_matter_id,
                meruscase_url
            )
            return True

    def add_screenshot(self, matter_id: int, screenshot_path: str) -> bool:
        """
        Add screenshot path to matter.

        Args:
            matter_id: Matter identifier
            screenshot_path: Path to screenshot file

        Returns:
            True if updated successfully
        """
        validate_matter_id(matter_id)

        with get_db_connection(self.db_path) as conn:
            cursor = conn.execute("""
                UPDATE matters
                SET screenshot_path = ?
                WHERE matter_id = ?
            """, (screenshot_path, matter_id))
            conn.commit()

            if cursor.rowcount == 0:
                logger.warning("Matter %d not found for screenshot update", matter_id)
                return False

            logger.info("Added screenshot to matter %d: %s", matter_id, screenshot_path)
            return True

    def get_session_matters(self, session_id: str) -> List[Dict[str, Any]]:
        """
        Get all matters for a session.

        Args:
            session_id: Session identifier

        Returns:
            List of matter dictionaries
        """
        validate_session_id(session_id)

        with get_db_connection(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT * FROM matters WHERE session_id = ? ORDER BY created_at DESC",
                (session_id,)
            )
            rows = cursor.fetchall()

            matters = [
                row_to_dict(row, json_fields=['custom_fields', 'metadata'])
                for row in rows
            ]
            return matters

    def get_matters_by_status(self, status: str) -> List[Dict[str, Any]]:
        """
        Get all matters with specific status.

        Args:
            status: Matter status to filter by

        Returns:
            List of matter dictionaries
        """
        if status not in [s.value for s in MatterStatus]:
            raise ValueError(f"Invalid status: {status}")

        with get_db_connection(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT * FROM matters WHERE status = ? ORDER BY created_at DESC",
                (status,)
            )
            rows = cursor.fetchall()

            matters = [
                row_to_dict(row, json_fields=['custom_fields', 'metadata'])
                for row in rows
            ]
            return matters

    def get_recent_matters(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get most recent matters.

        Args:
            limit: Maximum number of matters to return

        Returns:
            List of matter dictionaries
        """
        with get_db_connection(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT * FROM matters ORDER BY created_at DESC LIMIT ?",
                (limit,)
            )
            rows = cursor.fetchall()

            matters = [
                row_to_dict(row, json_fields=['custom_fields', 'metadata'])
                for row in rows
            ]
            return matters

    def get_matter_stats(self) -> Dict[str, Any]:
        """
        Get statistics about matter creation.

        Returns:
            Dictionary with stats (total, by status, by type, success rate)
        """
        with get_db_connection(self.db_path) as conn:
            # Total matters
            cursor = conn.execute("SELECT COUNT(*) as total FROM matters")
            total = cursor.fetchone()['total']

            # By status
            cursor = conn.execute("""
                SELECT status, COUNT(*) as count
                FROM matters
                GROUP BY status
            """)
            by_status = {row['status']: row['count'] for row in cursor.fetchall()}

            # By type
            cursor = conn.execute("""
                SELECT matter_type, COUNT(*) as count
                FROM matters
                GROUP BY matter_type
            """)
            by_type = {row['matter_type']: row['count'] for row in cursor.fetchall()}

            # Success rate
            success_count = by_status.get(MatterStatus.SUCCESS.value, 0)
            success_rate = (success_count / total * 100) if total > 0 else 0

            # Dry-run vs production
            cursor = conn.execute("""
                SELECT dry_run, COUNT(*) as count
                FROM matters
                GROUP BY dry_run
            """)
            dry_run_stats = {
                'dry_run': 0,
                'production': 0
            }
            for row in cursor.fetchall():
                if row['dry_run']:
                    dry_run_stats['dry_run'] = row['count']
                else:
                    dry_run_stats['production'] = row['count']

            stats = {
                'total': total,
                'by_status': by_status,
                'by_type': by_type,
                'success_rate': round(success_rate, 2),
                'dry_run_stats': dry_run_stats
            }

            logger.info("Matter stats: %s", stats)
            return stats
