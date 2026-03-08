"""
Spectacles File Specialist
Executes file system operations with security controls

SOC2/HIPAA Compliant with full audit logging and path sandboxing.
"""

import logging
import os
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass
from datetime import datetime

from persistence.constants import ActionType, ActionStatus
from security.audit import AuditLogger, get_audit_logger

logger = logging.getLogger(__name__)


@dataclass
class FileActionResult:
    """Result of a file operation"""
    action_type: ActionType
    status: ActionStatus
    path: Optional[str] = None
    duration_ms: int = 0
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    audit_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_type": self.action_type.value,
            "status": self.status.value,
            "path": self.path,
            "duration_ms": self.duration_ms,
            "data": self.data,
            "error": self.error,
            "audit_id": self.audit_id,
        }


class FileSpecialist:
    """
    File Specialist - executes sandboxed file operations.

    Responsibilities:
    - Read files within allowed directories
    - Write files with size limits
    - List directories
    - Copy/move files
    - Watch for file changes
    - Search files by pattern or content

    Security Features:
    - Path sandboxing (configurable allowed paths)
    - File size limits
    - Delete protection (optional)
    - Full audit logging for SOC2/HIPAA

    Works under the Orchestrator's direction.
    """

    def __init__(
        self,
        allowed_paths: Optional[List[str]] = None,
        max_file_size_mb: int = 100,
        allow_delete: bool = False,
        audit_logger: Optional[AuditLogger] = None
    ):
        """
        Initialize file specialist.

        Args:
            allowed_paths: List of allowed base paths
            max_file_size_mb: Maximum file size for operations
            allow_delete: Whether to allow file deletion
            audit_logger: Audit logger for compliance
        """
        self.audit_logger = audit_logger or get_audit_logger()

        # Load from config if not provided
        if allowed_paths is None:
            from api.config import settings
            allowed_paths = settings.allowed_file_paths_list
            max_file_size_mb = settings.MAX_FILE_SIZE_MB
            allow_delete = settings.ALLOW_FILE_DELETE

        # Lazy-loaded filesystem client
        self._fs_client = None
        self._allowed_paths = allowed_paths
        self._max_file_size_mb = max_file_size_mb
        self._allow_delete = allow_delete

        logger.info(
            "FileSpecialist initialized (paths=%d, max_size=%dMB, delete=%s)",
            len(allowed_paths), max_file_size_mb, allow_delete
        )

    @property
    def fs_client(self):
        """Lazy-load filesystem client"""
        if self._fs_client is None:
            from filesystem import FileSystemClient
            self._fs_client = FileSystemClient(
                allowed_paths=self._allowed_paths,
                max_file_size_mb=self._max_file_size_mb,
                allow_delete=self._allow_delete,
                audit_logger=self.audit_logger
            )
        return self._fs_client

    async def read_file(
        self,
        path: str,
        encoding: str = "utf-8",
        binary: bool = False,
        task_id: Optional[str] = None
    ) -> FileActionResult:
        """
        Read file contents.

        Args:
            path: File path to read
            encoding: Text encoding
            binary: Read as binary
            task_id: Task ID for logging

        Returns:
            FileActionResult with file contents
        """
        start_time = datetime.now()

        try:
            result = await self.fs_client.read_file(
                path=path,
                encoding=encoding,
                binary=binary,
                task_id=task_id
            )

            duration = int((datetime.now() - start_time).total_seconds() * 1000)

            if result.success:
                return FileActionResult(
                    action_type=ActionType.FILE_READ,
                    status=ActionStatus.SUCCESS,
                    path=result.path,
                    duration_ms=duration,
                    data={"content": result.data, "size": len(result.data) if result.data else 0},
                    audit_id=result.audit_id
                )
            else:
                return FileActionResult(
                    action_type=ActionType.FILE_READ,
                    status=ActionStatus.FAILED,
                    path=path,
                    duration_ms=duration,
                    error=result.error,
                    audit_id=result.audit_id
                )

        except Exception as e:
            duration = int((datetime.now() - start_time).total_seconds() * 1000)
            logger.error("Read file failed: %s", e)

            return FileActionResult(
                action_type=ActionType.FILE_READ,
                status=ActionStatus.FAILED,
                path=path,
                duration_ms=duration,
                error=str(e)
            )

    async def write_file(
        self,
        path: str,
        content: str,
        encoding: str = "utf-8",
        append: bool = False,
        task_id: Optional[str] = None
    ) -> FileActionResult:
        """
        Write content to file.

        Args:
            path: File path to write
            content: Content to write
            encoding: Text encoding
            append: Append to existing file
            task_id: Task ID for logging

        Returns:
            FileActionResult
        """
        start_time = datetime.now()

        try:
            result = await self.fs_client.write_file(
                path=path,
                content=content,
                encoding=encoding,
                append=append,
                task_id=task_id
            )

            duration = int((datetime.now() - start_time).total_seconds() * 1000)

            if result.success:
                return FileActionResult(
                    action_type=ActionType.FILE_WRITE,
                    status=ActionStatus.SUCCESS,
                    path=result.path,
                    duration_ms=duration,
                    data=result.data,
                    audit_id=result.audit_id
                )
            else:
                return FileActionResult(
                    action_type=ActionType.FILE_WRITE,
                    status=ActionStatus.FAILED,
                    path=path,
                    duration_ms=duration,
                    error=result.error,
                    audit_id=result.audit_id
                )

        except Exception as e:
            duration = int((datetime.now() - start_time).total_seconds() * 1000)
            logger.error("Write file failed: %s", e)

            return FileActionResult(
                action_type=ActionType.FILE_WRITE,
                status=ActionStatus.FAILED,
                path=path,
                duration_ms=duration,
                error=str(e)
            )

    async def list_directory(
        self,
        path: str,
        pattern: str = "*",
        recursive: bool = False,
        task_id: Optional[str] = None
    ) -> FileActionResult:
        """
        List directory contents.

        Args:
            path: Directory path
            pattern: Glob pattern for filtering
            recursive: Include subdirectories
            task_id: Task ID for logging

        Returns:
            FileActionResult with list of files
        """
        start_time = datetime.now()

        try:
            result = await self.fs_client.list_directory(
                path=path,
                pattern=pattern,
                recursive=recursive,
                task_id=task_id
            )

            duration = int((datetime.now() - start_time).total_seconds() * 1000)

            if result.success:
                return FileActionResult(
                    action_type=ActionType.FILE_LIST,
                    status=ActionStatus.SUCCESS,
                    path=result.path,
                    duration_ms=duration,
                    data={"files": result.data, "count": len(result.data) if result.data else 0},
                    audit_id=result.audit_id
                )
            else:
                return FileActionResult(
                    action_type=ActionType.FILE_LIST,
                    status=ActionStatus.FAILED,
                    path=path,
                    duration_ms=duration,
                    error=result.error,
                    audit_id=result.audit_id
                )

        except Exception as e:
            duration = int((datetime.now() - start_time).total_seconds() * 1000)
            logger.error("List directory failed: %s", e)

            return FileActionResult(
                action_type=ActionType.FILE_LIST,
                status=ActionStatus.FAILED,
                path=path,
                duration_ms=duration,
                error=str(e)
            )

    async def copy_file(
        self,
        source: str,
        destination: str,
        task_id: Optional[str] = None
    ) -> FileActionResult:
        """
        Copy file to new location.

        Args:
            source: Source file path
            destination: Destination path
            task_id: Task ID for logging

        Returns:
            FileActionResult
        """
        start_time = datetime.now()

        try:
            result = await self.fs_client.copy_file(
                source=source,
                destination=destination,
                task_id=task_id
            )

            duration = int((datetime.now() - start_time).total_seconds() * 1000)

            if result.success:
                return FileActionResult(
                    action_type=ActionType.FILE_COPY,
                    status=ActionStatus.SUCCESS,
                    path=result.path,
                    duration_ms=duration,
                    data=result.data,
                    audit_id=result.audit_id
                )
            else:
                return FileActionResult(
                    action_type=ActionType.FILE_COPY,
                    status=ActionStatus.FAILED,
                    path=destination,
                    duration_ms=duration,
                    error=result.error,
                    audit_id=result.audit_id
                )

        except Exception as e:
            duration = int((datetime.now() - start_time).total_seconds() * 1000)
            logger.error("Copy file failed: %s", e)

            return FileActionResult(
                action_type=ActionType.FILE_COPY,
                status=ActionStatus.FAILED,
                path=destination,
                duration_ms=duration,
                error=str(e)
            )

    async def move_file(
        self,
        source: str,
        destination: str,
        task_id: Optional[str] = None
    ) -> FileActionResult:
        """
        Move file to new location.

        Args:
            source: Source file path
            destination: Destination path
            task_id: Task ID for logging

        Returns:
            FileActionResult
        """
        start_time = datetime.now()

        try:
            result = await self.fs_client.move_file(
                source=source,
                destination=destination,
                task_id=task_id
            )

            duration = int((datetime.now() - start_time).total_seconds() * 1000)

            if result.success:
                return FileActionResult(
                    action_type=ActionType.FILE_MOVE,
                    status=ActionStatus.SUCCESS,
                    path=result.path,
                    duration_ms=duration,
                    data=result.data,
                    audit_id=result.audit_id
                )
            else:
                return FileActionResult(
                    action_type=ActionType.FILE_MOVE,
                    status=ActionStatus.FAILED,
                    path=destination,
                    duration_ms=duration,
                    error=result.error,
                    audit_id=result.audit_id
                )

        except Exception as e:
            duration = int((datetime.now() - start_time).total_seconds() * 1000)
            logger.error("Move file failed: %s", e)

            return FileActionResult(
                action_type=ActionType.FILE_MOVE,
                status=ActionStatus.FAILED,
                path=destination,
                duration_ms=duration,
                error=str(e)
            )

    async def delete_file(
        self,
        path: str,
        task_id: Optional[str] = None
    ) -> FileActionResult:
        """
        Delete file (requires allow_delete=True).

        Args:
            path: File path to delete
            task_id: Task ID for logging

        Returns:
            FileActionResult
        """
        start_time = datetime.now()

        try:
            result = await self.fs_client.delete_file(
                path=path,
                task_id=task_id
            )

            duration = int((datetime.now() - start_time).total_seconds() * 1000)

            if result.success:
                return FileActionResult(
                    action_type=ActionType.FILE_DELETE,
                    status=ActionStatus.SUCCESS,
                    path=result.path,
                    duration_ms=duration,
                    audit_id=result.audit_id
                )
            else:
                return FileActionResult(
                    action_type=ActionType.FILE_DELETE,
                    status=ActionStatus.FAILED,
                    path=path,
                    duration_ms=duration,
                    error=result.error,
                    audit_id=result.audit_id
                )

        except Exception as e:
            duration = int((datetime.now() - start_time).total_seconds() * 1000)
            logger.error("Delete file failed: %s", e)

            return FileActionResult(
                action_type=ActionType.FILE_DELETE,
                status=ActionStatus.FAILED,
                path=path,
                duration_ms=duration,
                error=str(e)
            )

    async def watch_directory(
        self,
        path: str,
        callback: Callable[[str, str], None],
        recursive: bool = False,
        task_id: Optional[str] = None
    ) -> FileActionResult:
        """
        Watch directory for changes.

        Args:
            path: Directory path to watch
            callback: Function(event_type, file_path) called on changes
            recursive: Watch subdirectories
            task_id: Task ID for logging

        Returns:
            FileActionResult with watch_id
        """
        start_time = datetime.now()

        try:
            watch_id = await self.fs_client.watch_path(
                path=path,
                callback=callback,
                recursive=recursive,
                task_id=task_id
            )

            duration = int((datetime.now() - start_time).total_seconds() * 1000)

            if watch_id:
                return FileActionResult(
                    action_type=ActionType.FILE_WATCH,
                    status=ActionStatus.SUCCESS,
                    path=path,
                    duration_ms=duration,
                    data={"watch_id": watch_id}
                )
            else:
                return FileActionResult(
                    action_type=ActionType.FILE_WATCH,
                    status=ActionStatus.FAILED,
                    path=path,
                    duration_ms=duration,
                    error="Failed to start watch"
                )

        except Exception as e:
            duration = int((datetime.now() - start_time).total_seconds() * 1000)
            logger.error("Watch directory failed: %s", e)

            return FileActionResult(
                action_type=ActionType.FILE_WATCH,
                status=ActionStatus.FAILED,
                path=path,
                duration_ms=duration,
                error=str(e)
            )

    async def stop_watch(self, watch_id: str) -> bool:
        """
        Stop watching a directory.

        Args:
            watch_id: Watch ID from watch_directory

        Returns:
            True if stopped successfully
        """
        return await self.fs_client.stop_watch(watch_id)

    async def search_files(
        self,
        path: str,
        pattern: str,
        content_search: Optional[str] = None,
        task_id: Optional[str] = None
    ) -> FileActionResult:
        """
        Search for files by pattern and optionally content.

        Args:
            path: Base path to search
            pattern: Filename pattern (glob)
            content_search: Optional text to search in files
            task_id: Task ID for logging

        Returns:
            FileActionResult with matching files
        """
        start_time = datetime.now()

        try:
            result = await self.fs_client.search_files(
                path=path,
                pattern=pattern,
                content_search=content_search,
                task_id=task_id
            )

            duration = int((datetime.now() - start_time).total_seconds() * 1000)

            if result.success:
                return FileActionResult(
                    action_type=ActionType.FILE_SEARCH,
                    status=ActionStatus.SUCCESS,
                    path=result.path,
                    duration_ms=duration,
                    data={"matches": result.data, "count": len(result.data) if result.data else 0},
                    audit_id=result.audit_id
                )
            else:
                return FileActionResult(
                    action_type=ActionType.FILE_SEARCH,
                    status=ActionStatus.FAILED,
                    path=path,
                    duration_ms=duration,
                    error=result.error,
                    audit_id=result.audit_id
                )

        except Exception as e:
            duration = int((datetime.now() - start_time).total_seconds() * 1000)
            logger.error("Search files failed: %s", e)

            return FileActionResult(
                action_type=ActionType.FILE_SEARCH,
                status=ActionStatus.FAILED,
                path=path,
                duration_ms=duration,
                error=str(e)
            )

    def close(self):
        """Close resources"""
        if self._fs_client:
            self._fs_client.close()
        logger.info("FileSpecialist closed")

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.close()
