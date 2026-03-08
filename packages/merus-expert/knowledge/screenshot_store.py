"""
Screenshot Manager - Capture and manage screenshots with 24-hour retention
"""

import logging
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import sqlite3

from persistence.utils import get_db_connection, safe_json_dump

logger = logging.getLogger(__name__)


class ScreenshotManager:
    """
    Manages screenshot capture with metadata tracking and automated cleanup.

    Features:
    - Screenshot capture at key workflow steps
    - Metadata tracking (session, URL, step, timestamp)
    - 24-hour automated retention
    - Organized storage by date and session
    """

    def __init__(
        self,
        db_path: str,
        screenshot_dir: str = "./screenshots",
        retention_hours: int = 24
    ):
        """
        Initialize screenshot manager.

        Args:
            db_path: Path to SQLite database
            screenshot_dir: Base directory for screenshots
            retention_hours: Screenshot retention period in hours
        """
        self.db_path = db_path
        self.screenshot_dir = Path(screenshot_dir)
        self.retention_hours = retention_hours

        # Ensure screenshot directory exists
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

    def _get_screenshot_path(
        self,
        session_id: str,
        step_key: str
    ) -> Path:
        """
        Generate screenshot file path.

        Format: screenshots/YYYYMMDD/session_id/HH-MM-SS_step_key.png

        Args:
            session_id: Session identifier
            step_key: Step identifier (e.g., 'login_page', 'form_filled')

        Returns:
            Full path to screenshot file
        """
        now = datetime.now()
        date_dir = self.screenshot_dir / now.strftime("%Y%m%d")
        session_dir = date_dir / session_id

        # Create directories
        session_dir.mkdir(parents=True, exist_ok=True)

        # Generate filename
        timestamp = now.strftime("%H-%M-%S")
        filename = f"{timestamp}_{step_key}.png"

        return session_dir / filename

    async def capture_screenshot(
        self,
        page,  # Playwright Page object
        session_id: str,
        step_key: str,
        description: Optional[str] = None,
        full_page: bool = False
    ) -> Optional[str]:
        """
        Capture screenshot and save metadata.

        Args:
            page: Playwright page object
            session_id: Session identifier
            step_key: Step identifier
            description: Human-readable description
            full_page: Capture full scrollable page

        Returns:
            Screenshot file path or None on error
        """
        try:
            # Generate path
            screenshot_path = self._get_screenshot_path(session_id, step_key)

            # Capture screenshot
            await page.screenshot(
                path=str(screenshot_path),
                full_page=full_page
            )

            # Get page URL
            page_url = page.url

            # Get file size
            file_size_kb = screenshot_path.stat().st_size / 1024

            # Get viewport size
            viewport = page.viewport_size
            resolution = f"{viewport['width']}x{viewport['height']}" if viewport else "unknown"

            # Calculate expiration
            expires_at = datetime.now() + timedelta(hours=self.retention_hours)

            # Save metadata
            self._save_metadata(
                session_id=session_id,
                screenshot_path=str(screenshot_path),
                step_key=step_key,
                description=description,
                page_url=page_url,
                file_size_kb=file_size_kb,
                resolution=resolution,
                expires_at=expires_at
            )

            logger.info(
                f"Screenshot captured: {step_key} -> {screenshot_path} "
                f"({file_size_kb:.1f} KB)"
            )

            return str(screenshot_path)

        except Exception as e:
            logger.error(f"Failed to capture screenshot {step_key}: {e}")
            return None

    def _save_metadata(
        self,
        session_id: str,
        screenshot_path: str,
        step_key: str,
        description: Optional[str],
        page_url: str,
        file_size_kb: float,
        resolution: str,
        expires_at: datetime
    ):
        """
        Save screenshot metadata to database.

        Args:
            session_id: Session identifier
            screenshot_path: Path to screenshot file
            step_key: Step identifier
            description: Description
            page_url: Page URL
            file_size_kb: File size in KB
            resolution: Screen resolution
            expires_at: Expiration datetime
        """
        try:
            with get_db_connection(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO screenshot_metadata (
                        session_id, screenshot_path, step_key, description,
                        page_url, file_size_kb, resolution, expires_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    session_id,
                    screenshot_path,
                    step_key,
                    description,
                    page_url,
                    file_size_kb,
                    resolution,
                    expires_at.isoformat()
                ))

                logger.debug(f"Screenshot metadata saved for {step_key}")

        except Exception as e:
            logger.error(f"Failed to save screenshot metadata: {e}")

    def get_session_screenshots(self, session_id: str) -> list:
        """
        Get all screenshots for a session.

        Args:
            session_id: Session identifier

        Returns:
            List of screenshot records
        """
        try:
            with get_db_connection(self.db_path) as conn:
                cursor = conn.execute("""
                    SELECT
                        screenshot_id, session_id, screenshot_path, step_key,
                        description, page_url, file_size_kb, resolution,
                        timestamp, expires_at
                    FROM screenshot_metadata
                    WHERE session_id = ?
                    ORDER BY timestamp ASC
                """, (session_id,))

                screenshots = []
                for row in cursor:
                    screenshots.append({
                        "screenshot_id": row[0],
                        "session_id": row[1],
                        "screenshot_path": row[2],
                        "step_key": row[3],
                        "description": row[4],
                        "page_url": row[5],
                        "file_size_kb": row[6],
                        "resolution": row[7],
                        "timestamp": row[8],
                        "expires_at": row[9]
                    })

                return screenshots

        except Exception as e:
            logger.error(f"Failed to get session screenshots: {e}")
            return []

    def cleanup_expired_screenshots(self) -> int:
        """
        Delete expired screenshots from filesystem and database.

        Returns:
            Number of screenshots deleted
        """
        try:
            deleted_count = 0

            with get_db_connection(self.db_path) as conn:
                # Get expired screenshots
                cursor = conn.execute("""
                    SELECT screenshot_id, screenshot_path
                    FROM screenshot_metadata
                    WHERE expires_at < datetime('now')
                """)

                expired = cursor.fetchall()

                for screenshot_id, screenshot_path in expired:
                    # Delete file
                    try:
                        Path(screenshot_path).unlink(missing_ok=True)
                        logger.debug(f"Deleted expired screenshot: {screenshot_path}")
                    except Exception as e:
                        logger.warning(f"Could not delete file {screenshot_path}: {e}")

                    # Delete metadata
                    conn.execute("""
                        DELETE FROM screenshot_metadata
                        WHERE screenshot_id = ?
                    """, (screenshot_id,))

                    deleted_count += 1

            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} expired screenshots")

            return deleted_count

        except Exception as e:
            logger.error(f"Failed to cleanup expired screenshots: {e}")
            return 0

    def get_screenshot_stats(self) -> Dict[str, Any]:
        """
        Get screenshot statistics.

        Returns:
            Statistics dictionary
        """
        try:
            with get_db_connection(self.db_path) as conn:
                # Total screenshots
                cursor = conn.execute("""
                    SELECT COUNT(*), COALESCE(SUM(file_size_kb), 0)
                    FROM screenshot_metadata
                """)
                total, total_size_kb = cursor.fetchone()

                # Expired screenshots
                cursor = conn.execute("""
                    SELECT COUNT(*)
                    FROM screenshot_metadata
                    WHERE expires_at < datetime('now')
                """)
                expired = cursor.fetchone()[0]

                return {
                    "total": total,
                    "total_size_kb": float(total_size_kb),
                    "expired": expired,
                    "active": total - expired
                }

        except Exception as e:
            logger.error(f"Failed to get screenshot stats: {e}")
            return {"total": 0, "total_size_kb": 0.0, "expired": 0, "active": 0}
