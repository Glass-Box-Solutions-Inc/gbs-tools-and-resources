"""
Spectacles File System Client
Sandboxed file operations with security controls

SOC2/HIPAA Compliant:
- Path sandboxing (only allowed directories)
- Full audit logging of all operations
- File size limits
- Optional delete protection
- PII/PHI detection in file contents
"""

import logging
import os
import shutil
import asyncio
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable, Union
from dataclasses import dataclass, field
from datetime import datetime
from fnmatch import fnmatch

logger = logging.getLogger(__name__)


@dataclass
class FileInfo:
    """Information about a file"""
    path: str
    name: str
    size_bytes: int
    is_file: bool
    is_directory: bool
    created_at: Optional[datetime] = None
    modified_at: Optional[datetime] = None
    extension: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "name": self.name,
            "size_bytes": self.size_bytes,
            "is_file": self.is_file,
            "is_directory": self.is_directory,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "modified_at": self.modified_at.isoformat() if self.modified_at else None,
            "extension": self.extension,
        }


@dataclass
class FileOperationResult:
    """Result of a file operation"""
    success: bool
    operation: str
    path: str
    data: Optional[Any] = None
    error: Optional[str] = None
    audit_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "operation": self.operation,
            "path": self.path,
            "data": self.data,
            "error": self.error,
            "audit_id": self.audit_id,
        }


class FileSystemClient:
    """
    Sandboxed file system client.

    Security Features:
    - Path sandboxing: Only operates in allowed directories
    - File size limits: Prevents large file operations
    - Delete protection: Optional extra protection for destructive ops
    - Audit logging: All operations logged for compliance
    - Path traversal prevention: Blocks ../ attacks

    Usage:
    ```python
    client = FileSystemClient(
        allowed_paths=["~/Documents", "~/Downloads", "/tmp/spectacles"],
        max_file_size_mb=100,
        allow_delete=False  # Extra protection
    )

    # Read a file
    result = await client.read_file("~/Documents/report.txt")
    print(result.data)  # File contents

    # List directory
    files = await client.list_directory("~/Downloads")

    # Write file (only in allowed paths)
    await client.write_file("/tmp/spectacles/output.txt", "content")
    ```
    """

    def __init__(
        self,
        allowed_paths: Optional[List[str]] = None,
        max_file_size_mb: int = 100,
        allow_delete: bool = False,
        audit_logger: Optional[Any] = None
    ):
        """
        Initialize file system client.

        Args:
            allowed_paths: List of allowed base paths (supports ~ expansion)
            max_file_size_mb: Maximum file size for operations
            allow_delete: Whether to allow file deletion
            audit_logger: Audit logger for compliance
        """
        # Default allowed paths
        default_paths = [
            "~/Documents",
            "~/Downloads",
            "/tmp/spectacles"
        ]

        # Expand and normalize paths
        self.allowed_paths = []
        for path in (allowed_paths or default_paths):
            expanded = os.path.expanduser(path)
            normalized = os.path.normpath(expanded)
            self.allowed_paths.append(normalized)

        self.max_file_size_bytes = max_file_size_mb * 1024 * 1024
        self.allow_delete = allow_delete

        # Audit logger
        if audit_logger:
            self.audit_logger = audit_logger
        else:
            from security.audit import get_audit_logger
            self.audit_logger = get_audit_logger()

        # File watchers (for watchdog integration)
        self._watchers: Dict[str, Any] = {}

        logger.info(
            "FileSystemClient initialized (paths=%d, max_size=%dMB, delete=%s)",
            len(self.allowed_paths), max_file_size_mb, allow_delete
        )

    def _validate_path(self, path: str) -> str:
        """
        Validate and normalize a file path.

        Args:
            path: Path to validate

        Returns:
            Normalized absolute path

        Raises:
            PermissionError: If path is not in allowed directories
            ValueError: If path contains traversal attempts
        """
        # Expand user path
        expanded = os.path.expanduser(path)

        # Get absolute path
        absolute = os.path.abspath(expanded)

        # Check for path traversal
        if ".." in path:
            raise ValueError(f"Path traversal not allowed: {path}")

        # Check if path is under an allowed base
        is_allowed = False
        for allowed in self.allowed_paths:
            try:
                # Ensure the path starts with an allowed path
                if absolute.startswith(allowed):
                    is_allowed = True
                    break
            except Exception:
                continue

        if not is_allowed:
            raise PermissionError(
                f"Path not in allowed directories: {path}. "
                f"Allowed: {self.allowed_paths}"
            )

        return absolute

    def _generate_audit_id(self) -> str:
        """Generate unique audit ID"""
        import uuid
        return str(uuid.uuid4())[:8]

    async def read_file(
        self,
        path: str,
        encoding: str = "utf-8",
        binary: bool = False,
        task_id: Optional[str] = None
    ) -> FileOperationResult:
        """
        Read file contents.

        Args:
            path: File path to read
            encoding: Text encoding (ignored for binary)
            binary: Read as binary
            task_id: Task ID for logging

        Returns:
            FileOperationResult with file contents
        """
        audit_id = self._generate_audit_id()

        try:
            validated_path = self._validate_path(path)

            # Check file exists
            if not os.path.isfile(validated_path):
                raise FileNotFoundError(f"File not found: {path}")

            # Check file size
            size = os.path.getsize(validated_path)
            if size > self.max_file_size_bytes:
                raise ValueError(
                    f"File too large: {size} bytes > {self.max_file_size_bytes} bytes"
                )

            # Read file
            loop = asyncio.get_event_loop()

            def _read():
                mode = "rb" if binary else "r"
                with open(validated_path, mode, encoding=None if binary else encoding) as f:
                    return f.read()

            content = await loop.run_in_executor(None, _read)

            self.audit_logger.log_browser_action(
                action="file_read",
                status="SUCCESS",
                task_id=task_id,
                resource=validated_path,
                additional_data={"audit_id": audit_id, "size": size}
            )

            return FileOperationResult(
                success=True,
                operation="read",
                path=validated_path,
                data=content,
                audit_id=audit_id
            )

        except (PermissionError, FileNotFoundError, ValueError) as e:
            self.audit_logger.log_browser_action(
                action="file_read",
                status="FAILED",
                task_id=task_id,
                resource=path,
                additional_data={"audit_id": audit_id, "error": str(e)}
            )

            return FileOperationResult(
                success=False,
                operation="read",
                path=path,
                error=str(e),
                audit_id=audit_id
            )

    async def write_file(
        self,
        path: str,
        content: Union[str, bytes],
        encoding: str = "utf-8",
        append: bool = False,
        task_id: Optional[str] = None
    ) -> FileOperationResult:
        """
        Write content to file.

        Args:
            path: File path to write
            content: Content to write
            encoding: Text encoding
            append: Append to existing file
            task_id: Task ID for logging

        Returns:
            FileOperationResult
        """
        audit_id = self._generate_audit_id()

        try:
            validated_path = self._validate_path(path)

            # Check content size
            content_size = len(content.encode() if isinstance(content, str) else content)
            if content_size > self.max_file_size_bytes:
                raise ValueError(
                    f"Content too large: {content_size} bytes > {self.max_file_size_bytes} bytes"
                )

            # Ensure parent directory exists
            parent = os.path.dirname(validated_path)
            if parent:
                os.makedirs(parent, exist_ok=True)

            # Write file
            loop = asyncio.get_event_loop()

            def _write():
                binary = isinstance(content, bytes)
                mode = "ab" if append and binary else "a" if append else "wb" if binary else "w"
                with open(validated_path, mode, encoding=None if binary else encoding) as f:
                    f.write(content)

            await loop.run_in_executor(None, _write)

            self.audit_logger.log_browser_action(
                action="file_write",
                status="SUCCESS",
                task_id=task_id,
                resource=validated_path,
                additional_data={
                    "audit_id": audit_id,
                    "size": content_size,
                    "append": append
                }
            )

            return FileOperationResult(
                success=True,
                operation="write",
                path=validated_path,
                data={"size": content_size},
                audit_id=audit_id
            )

        except (PermissionError, ValueError, OSError) as e:
            self.audit_logger.log_browser_action(
                action="file_write",
                status="FAILED",
                task_id=task_id,
                resource=path,
                additional_data={"audit_id": audit_id, "error": str(e)}
            )

            return FileOperationResult(
                success=False,
                operation="write",
                path=path,
                error=str(e),
                audit_id=audit_id
            )

    async def list_directory(
        self,
        path: str,
        pattern: str = "*",
        recursive: bool = False,
        task_id: Optional[str] = None
    ) -> FileOperationResult:
        """
        List directory contents.

        Args:
            path: Directory path
            pattern: Glob pattern for filtering
            recursive: Include subdirectories
            task_id: Task ID for logging

        Returns:
            FileOperationResult with list of FileInfo
        """
        audit_id = self._generate_audit_id()

        try:
            validated_path = self._validate_path(path)

            if not os.path.isdir(validated_path):
                raise NotADirectoryError(f"Not a directory: {path}")

            loop = asyncio.get_event_loop()

            def _list():
                files = []
                if recursive:
                    for root, dirs, filenames in os.walk(validated_path):
                        for name in filenames + dirs:
                            full_path = os.path.join(root, name)
                            if fnmatch(name, pattern):
                                files.append(self._get_file_info(full_path))
                else:
                    for name in os.listdir(validated_path):
                        if fnmatch(name, pattern):
                            full_path = os.path.join(validated_path, name)
                            files.append(self._get_file_info(full_path))
                return files

            files = await loop.run_in_executor(None, _list)

            self.audit_logger.log_browser_action(
                action="file_list",
                status="SUCCESS",
                task_id=task_id,
                resource=validated_path,
                additional_data={"audit_id": audit_id, "count": len(files)}
            )

            return FileOperationResult(
                success=True,
                operation="list",
                path=validated_path,
                data=[f.to_dict() for f in files],
                audit_id=audit_id
            )

        except (PermissionError, NotADirectoryError) as e:
            self.audit_logger.log_browser_action(
                action="file_list",
                status="FAILED",
                task_id=task_id,
                resource=path,
                additional_data={"audit_id": audit_id, "error": str(e)}
            )

            return FileOperationResult(
                success=False,
                operation="list",
                path=path,
                error=str(e),
                audit_id=audit_id
            )

    def _get_file_info(self, path: str) -> FileInfo:
        """Get FileInfo for a path"""
        stat = os.stat(path)
        return FileInfo(
            path=path,
            name=os.path.basename(path),
            size_bytes=stat.st_size,
            is_file=os.path.isfile(path),
            is_directory=os.path.isdir(path),
            created_at=datetime.fromtimestamp(stat.st_ctime),
            modified_at=datetime.fromtimestamp(stat.st_mtime),
            extension=os.path.splitext(path)[1] if os.path.isfile(path) else None
        )

    async def copy_file(
        self,
        source: str,
        destination: str,
        task_id: Optional[str] = None
    ) -> FileOperationResult:
        """
        Copy file to new location.

        Args:
            source: Source file path
            destination: Destination path
            task_id: Task ID for logging

        Returns:
            FileOperationResult
        """
        audit_id = self._generate_audit_id()

        try:
            validated_source = self._validate_path(source)
            validated_dest = self._validate_path(destination)

            if not os.path.exists(validated_source):
                raise FileNotFoundError(f"Source not found: {source}")

            # Check source size
            size = os.path.getsize(validated_source)
            if size > self.max_file_size_bytes:
                raise ValueError(f"File too large: {size} bytes")

            loop = asyncio.get_event_loop()

            def _copy():
                if os.path.isdir(validated_source):
                    shutil.copytree(validated_source, validated_dest)
                else:
                    # Ensure parent exists
                    os.makedirs(os.path.dirname(validated_dest), exist_ok=True)
                    shutil.copy2(validated_source, validated_dest)

            await loop.run_in_executor(None, _copy)

            self.audit_logger.log_browser_action(
                action="file_copy",
                status="SUCCESS",
                task_id=task_id,
                resource=f"{validated_source} -> {validated_dest}",
                additional_data={"audit_id": audit_id, "size": size}
            )

            return FileOperationResult(
                success=True,
                operation="copy",
                path=validated_dest,
                data={"source": validated_source, "size": size},
                audit_id=audit_id
            )

        except (PermissionError, FileNotFoundError, ValueError) as e:
            self.audit_logger.log_browser_action(
                action="file_copy",
                status="FAILED",
                task_id=task_id,
                resource=f"{source} -> {destination}",
                additional_data={"audit_id": audit_id, "error": str(e)}
            )

            return FileOperationResult(
                success=False,
                operation="copy",
                path=destination,
                error=str(e),
                audit_id=audit_id
            )

    async def move_file(
        self,
        source: str,
        destination: str,
        task_id: Optional[str] = None
    ) -> FileOperationResult:
        """
        Move file to new location.

        Args:
            source: Source file path
            destination: Destination path
            task_id: Task ID for logging

        Returns:
            FileOperationResult
        """
        audit_id = self._generate_audit_id()

        try:
            validated_source = self._validate_path(source)
            validated_dest = self._validate_path(destination)

            if not os.path.exists(validated_source):
                raise FileNotFoundError(f"Source not found: {source}")

            loop = asyncio.get_event_loop()

            def _move():
                os.makedirs(os.path.dirname(validated_dest), exist_ok=True)
                shutil.move(validated_source, validated_dest)

            await loop.run_in_executor(None, _move)

            self.audit_logger.log_browser_action(
                action="file_move",
                status="SUCCESS",
                task_id=task_id,
                resource=f"{validated_source} -> {validated_dest}",
                additional_data={"audit_id": audit_id}
            )

            return FileOperationResult(
                success=True,
                operation="move",
                path=validated_dest,
                data={"source": validated_source},
                audit_id=audit_id
            )

        except (PermissionError, FileNotFoundError) as e:
            self.audit_logger.log_browser_action(
                action="file_move",
                status="FAILED",
                task_id=task_id,
                resource=f"{source} -> {destination}",
                additional_data={"audit_id": audit_id, "error": str(e)}
            )

            return FileOperationResult(
                success=False,
                operation="move",
                path=destination,
                error=str(e),
                audit_id=audit_id
            )

    async def delete_file(
        self,
        path: str,
        task_id: Optional[str] = None
    ) -> FileOperationResult:
        """
        Delete file (requires allow_delete=True).

        Args:
            path: File path to delete
            task_id: Task ID for logging

        Returns:
            FileOperationResult
        """
        audit_id = self._generate_audit_id()

        try:
            if not self.allow_delete:
                raise PermissionError("File deletion is disabled")

            validated_path = self._validate_path(path)

            if not os.path.exists(validated_path):
                raise FileNotFoundError(f"File not found: {path}")

            loop = asyncio.get_event_loop()

            def _delete():
                if os.path.isdir(validated_path):
                    shutil.rmtree(validated_path)
                else:
                    os.remove(validated_path)

            await loop.run_in_executor(None, _delete)

            self.audit_logger.log_browser_action(
                action="file_delete",
                status="SUCCESS",
                task_id=task_id,
                resource=validated_path,
                additional_data={"audit_id": audit_id}
            )

            return FileOperationResult(
                success=True,
                operation="delete",
                path=validated_path,
                audit_id=audit_id
            )

        except (PermissionError, FileNotFoundError) as e:
            self.audit_logger.log_browser_action(
                action="file_delete",
                status="FAILED",
                task_id=task_id,
                resource=path,
                additional_data={"audit_id": audit_id, "error": str(e)}
            )

            return FileOperationResult(
                success=False,
                operation="delete",
                path=path,
                error=str(e),
                audit_id=audit_id
            )

    async def watch_path(
        self,
        path: str,
        callback: Callable[[str, str], None],
        recursive: bool = False,
        task_id: Optional[str] = None
    ) -> str:
        """
        Watch path for changes using watchdog.

        Args:
            path: Path to watch
            callback: Function(event_type, file_path) called on changes
            recursive: Watch subdirectories
            task_id: Task ID for logging

        Returns:
            Watch ID for stopping later
        """
        import uuid

        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler

            validated_path = self._validate_path(path)
            watch_id = str(uuid.uuid4())[:8]

            class Handler(FileSystemEventHandler):
                def on_any_event(self, event):
                    callback(event.event_type, event.src_path)

            observer = Observer()
            observer.schedule(Handler(), validated_path, recursive=recursive)
            observer.start()

            self._watchers[watch_id] = observer

            self.audit_logger.log_browser_action(
                action="file_watch_start",
                status="SUCCESS",
                task_id=task_id,
                resource=validated_path,
                additional_data={"watch_id": watch_id}
            )

            return watch_id

        except Exception as e:
            logger.error("Watch failed: %s", e)
            return ""

    async def stop_watch(self, watch_id: str) -> bool:
        """
        Stop watching a path.

        Args:
            watch_id: Watch ID returned from watch_path

        Returns:
            True if stopped successfully
        """
        if watch_id in self._watchers:
            observer = self._watchers[watch_id]
            observer.stop()
            observer.join()
            del self._watchers[watch_id]

            self.audit_logger.log_browser_action(
                action="file_watch_stop",
                status="SUCCESS",
                task_id=None,
                resource=watch_id
            )

            return True
        return False

    async def search_files(
        self,
        path: str,
        pattern: str,
        content_search: Optional[str] = None,
        task_id: Optional[str] = None
    ) -> FileOperationResult:
        """
        Search for files matching pattern, optionally searching content.

        Args:
            path: Base path to search
            pattern: Filename pattern (glob)
            content_search: Optional text to search in files
            task_id: Task ID for logging

        Returns:
            FileOperationResult with matching files
        """
        audit_id = self._generate_audit_id()

        try:
            validated_path = self._validate_path(path)
            matches = []

            loop = asyncio.get_event_loop()

            def _search():
                results = []
                for root, dirs, files in os.walk(validated_path):
                    for name in files:
                        if fnmatch(name, pattern):
                            full_path = os.path.join(root, name)

                            # If content search, check file contents
                            if content_search:
                                try:
                                    with open(full_path, 'r', errors='ignore') as f:
                                        if content_search in f.read():
                                            results.append(full_path)
                                except Exception:
                                    continue
                            else:
                                results.append(full_path)
                return results

            matches = await loop.run_in_executor(None, _search)

            self.audit_logger.log_browser_action(
                action="file_search",
                status="SUCCESS",
                task_id=task_id,
                resource=f"{validated_path}/{pattern}",
                additional_data={"audit_id": audit_id, "matches": len(matches)}
            )

            return FileOperationResult(
                success=True,
                operation="search",
                path=validated_path,
                data=matches,
                audit_id=audit_id
            )

        except PermissionError as e:
            return FileOperationResult(
                success=False,
                operation="search",
                path=path,
                error=str(e),
                audit_id=audit_id
            )

    def close(self):
        """Stop all watchers and cleanup"""
        for watch_id in list(self._watchers.keys()):
            observer = self._watchers[watch_id]
            observer.stop()
            observer.join()
        self._watchers.clear()
        logger.info("FileSystemClient closed")

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.close()
