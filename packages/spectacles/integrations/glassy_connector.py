"""
Spectacles Skill Connector for Glassy
Enables Glassy AI agents to use Spectacles automation capabilities

Following BaseSkillConnector pattern from glassy-infra.
SOC2/HIPAA compliant with full audit logging.
"""

import logging
import asyncio
import os
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

import httpx

logger = logging.getLogger(__name__)


class SkillStatus(str, Enum):
    """Skill execution status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    AWAITING_APPROVAL = "awaiting_approval"
    CANCELLED = "cancelled"


@dataclass
class SkillResult:
    """Result from skill execution"""
    task_id: str
    status: SkillStatus
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    screenshots: List[str] = field(default_factory=list)
    duration_ms: int = 0
    audit_trail: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "screenshots": self.screenshots,
            "duration_ms": self.duration_ms,
            "audit_trail": self.audit_trail,
        }


@dataclass
class SpectaclesCapabilities:
    """Available Spectacles capabilities"""
    browser: bool = True
    desktop: bool = False
    files: bool = False
    modes: List[str] = field(default_factory=lambda: ["browser"])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "browser": self.browser,
            "desktop": self.desktop,
            "files": self.files,
            "modes": self.modes,
        }


class SpectaclesSkillConnector:
    """
    Skill connector for Glassy to use Spectacles.

    Provides:
    - Browser automation (web tasks, form filling, data extraction)
    - Desktop automation (native app control - VM only)
    - File operations (read, write, monitor)
    - Screenshot capture with optional PII blur
    - Full HITL (Human-in-the-Loop) support via Slack

    SOC2/HIPAA Compliance:
    - All actions audit logged
    - PII/PHI filtering on screenshots
    - Secure credential handling (never exposed to LLM)
    - Full transparency with audit trails

    Usage from Glassy:
    ```python
    from integrations import SpectaclesSkillConnector

    connector = SpectaclesSkillConnector(
        api_url="https://spectacles-api.run.app",
        api_key="..."
    )

    # Execute browser task
    result = await connector.execute_browser_task(
        goal="Log into MerusCase and export billing report",
        start_url="https://app.meruscase.com",
        require_approval=True,
        credentials_key="meruscase-admin"
    )
    ```
    """

    def __init__(
        self,
        api_url: Optional[str] = None,
        api_key: Optional[str] = None,
        callback_url: Optional[str] = None,
        timeout_seconds: int = 300,
        poll_interval_seconds: float = 2.0
    ):
        """
        Initialize Spectacles skill connector.

        Args:
            api_url: Spectacles API URL (from env if not provided)
            api_key: API key for authentication
            callback_url: Webhook URL for async completion callbacks
            timeout_seconds: Default task timeout
            poll_interval_seconds: Polling interval for status checks
        """
        self.api_url = api_url or os.environ.get(
            "SPECTICLES_API_URL",
            "http://localhost:8080"
        )
        self.api_key = api_key or os.environ.get("SPECTICLES_API_KEY")
        self.callback_url = callback_url
        self.timeout = timeout_seconds
        self.poll_interval = poll_interval_seconds

        # HTTP client
        self._client: Optional[httpx.AsyncClient] = None

        logger.info(
            "SpectaclesSkillConnector initialized (url=%s)",
            self.api_url
        )

    @property
    def client(self) -> httpx.AsyncClient:
        """Get or create HTTP client"""
        if self._client is None:
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            self._client = httpx.AsyncClient(
                base_url=self.api_url,
                headers=headers,
                timeout=httpx.Timeout(self.timeout)
            )
        return self._client

    async def get_capabilities(self) -> SpectaclesCapabilities:
        """
        Get available Spectacles capabilities.

        Returns:
            SpectaclesCapabilities indicating what modes are available
        """
        try:
            response = await self.client.get("/skills/capabilities")
            response.raise_for_status()

            data = response.json()
            return SpectaclesCapabilities(
                browser=data.get("browser", True),
                desktop=data.get("desktop", False),
                files=data.get("files", False),
                modes=data.get("modes", ["browser"])
            )

        except Exception as e:
            logger.error("Failed to get capabilities: %s", e)
            # Return default (browser only)
            return SpectaclesCapabilities()

    async def execute_browser_task(
        self,
        goal: str,
        start_url: str,
        require_approval: bool = True,
        credentials_key: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        wait_for_completion: bool = True
    ) -> SkillResult:
        """
        Execute browser automation task.

        Args:
            goal: Natural language description of what to accomplish
            start_url: URL to start from
            require_approval: Whether to require HITL approval for actions
            credentials_key: Key to retrieve credentials from vault (NOT the credentials themselves)
            context: Additional context for the task
            wait_for_completion: Whether to wait for task completion

        Returns:
            SkillResult with task outcome
        """
        payload = {
            "goal": goal,
            "start_url": start_url,
            "require_approval": require_approval,
            "mode": "browser",
            "context": context or {},
        }

        if credentials_key:
            payload["credentials_key"] = credentials_key

        if self.callback_url and not wait_for_completion:
            payload["callback_url"] = self.callback_url

        try:
            response = await self.client.post("/tasks", json=payload)
            response.raise_for_status()

            data = response.json()
            task_id = data.get("task_id")

            if wait_for_completion:
                return await self._poll_task_completion(task_id)
            else:
                return SkillResult(
                    task_id=task_id,
                    status=SkillStatus.PENDING
                )

        except Exception as e:
            logger.error("Browser task failed: %s", e)
            return SkillResult(
                task_id="",
                status=SkillStatus.FAILED,
                error=str(e)
            )

    async def execute_desktop_task(
        self,
        goal: str,
        app_name: Optional[str] = None,
        require_approval: bool = True,
        context: Optional[Dict[str, Any]] = None,
        wait_for_completion: bool = True
    ) -> SkillResult:
        """
        Execute desktop automation task.

        Args:
            goal: Natural language description of what to accomplish
            app_name: Application to open/control
            require_approval: Whether to require HITL approval for actions
            context: Additional context for the task
            wait_for_completion: Whether to wait for task completion

        Returns:
            SkillResult with task outcome
        """
        # Check if desktop is available
        capabilities = await self.get_capabilities()
        if not capabilities.desktop:
            return SkillResult(
                task_id="",
                status=SkillStatus.FAILED,
                error="Desktop automation not available (requires VM deployment)"
            )

        payload = {
            "goal": goal,
            "app_name": app_name,
            "require_approval": require_approval,
            "mode": "desktop",
            "context": context or {},
        }

        if self.callback_url and not wait_for_completion:
            payload["callback_url"] = self.callback_url

        try:
            response = await self.client.post("/tasks", json=payload)
            response.raise_for_status()

            data = response.json()
            task_id = data.get("task_id")

            if wait_for_completion:
                return await self._poll_task_completion(task_id)
            else:
                return SkillResult(
                    task_id=task_id,
                    status=SkillStatus.PENDING
                )

        except Exception as e:
            logger.error("Desktop task failed: %s", e)
            return SkillResult(
                task_id="",
                status=SkillStatus.FAILED,
                error=str(e)
            )

    async def take_screenshot(
        self,
        url: Optional[str] = None,
        mode: str = "browser",
        full_page: bool = True,
        blur_pii: bool = True
    ) -> SkillResult:
        """
        Take screenshot of current state.

        Args:
            url: URL to screenshot (browser mode)
            mode: "browser" or "desktop"
            full_page: Capture full page (browser)
            blur_pii: Apply PII detection and blur

        Returns:
            SkillResult with screenshot path
        """
        payload = {
            "url": url,
            "mode": mode,
            "full_page": full_page,
            "blur_pii": blur_pii,
        }

        try:
            response = await self.client.post("/skills/screenshot", json=payload)
            response.raise_for_status()

            data = response.json()
            return SkillResult(
                task_id=data.get("task_id", "screenshot"),
                status=SkillStatus.COMPLETED,
                result={"screenshot_path": data.get("screenshot_path")},
                screenshots=[data.get("screenshot_path")],
                duration_ms=data.get("duration_ms", 0)
            )

        except Exception as e:
            logger.error("Screenshot failed: %s", e)
            return SkillResult(
                task_id="",
                status=SkillStatus.FAILED,
                error=str(e)
            )

    async def get_task_status(self, task_id: str) -> SkillResult:
        """
        Get status of a task.

        Args:
            task_id: Task ID to check

        Returns:
            SkillResult with current status
        """
        try:
            response = await self.client.get(f"/tasks/{task_id}")
            response.raise_for_status()

            data = response.json()
            return self._parse_task_response(data)

        except Exception as e:
            logger.error("Status check failed: %s", e)
            return SkillResult(
                task_id=task_id,
                status=SkillStatus.FAILED,
                error=str(e)
            )

    async def cancel_task(self, task_id: str) -> bool:
        """
        Cancel a running task.

        Args:
            task_id: Task ID to cancel

        Returns:
            True if cancelled successfully
        """
        try:
            response = await self.client.post(f"/tasks/{task_id}/cancel")
            response.raise_for_status()
            return True

        except Exception as e:
            logger.error("Cancel failed: %s", e)
            return False

    async def resume_task(
        self,
        task_id: str,
        human_input: Optional[str] = None
    ) -> SkillResult:
        """
        Resume a paused task (after HITL intervention).

        Args:
            task_id: Task ID to resume
            human_input: Optional human-provided input

        Returns:
            SkillResult with resumed task status
        """
        payload = {}
        if human_input:
            payload["human_input"] = human_input

        try:
            response = await self.client.post(
                f"/tasks/{task_id}/resume",
                json=payload
            )
            response.raise_for_status()

            data = response.json()
            return self._parse_task_response(data)

        except Exception as e:
            logger.error("Resume failed: %s", e)
            return SkillResult(
                task_id=task_id,
                status=SkillStatus.FAILED,
                error=str(e)
            )

    async def execute_file_operation(
        self,
        operation: str,
        path: str,
        content: Optional[str] = None,
        destination: Optional[str] = None
    ) -> SkillResult:
        """
        Execute file system operation.

        Args:
            operation: Operation type (read, write, list, copy, move, delete)
            path: Target file/directory path
            content: Content to write (for write operation)
            destination: Destination path (for copy/move)

        Returns:
            SkillResult with operation outcome
        """
        # Check if files is available
        capabilities = await self.get_capabilities()
        if not capabilities.files:
            return SkillResult(
                task_id="",
                status=SkillStatus.FAILED,
                error="File operations not available"
            )

        payload = {
            "operation": operation,
            "path": path,
        }

        if content is not None:
            payload["content"] = content
        if destination:
            payload["destination"] = destination

        try:
            response = await self.client.post("/skills/file", json=payload)
            response.raise_for_status()

            data = response.json()
            return SkillResult(
                task_id=data.get("task_id", f"file_{operation}"),
                status=SkillStatus.COMPLETED,
                result=data.get("result"),
                duration_ms=data.get("duration_ms", 0)
            )

        except Exception as e:
            logger.error("File operation failed: %s", e)
            return SkillResult(
                task_id="",
                status=SkillStatus.FAILED,
                error=str(e)
            )

    async def _poll_task_completion(
        self,
        task_id: str,
        timeout: Optional[int] = None
    ) -> SkillResult:
        """
        Poll for task completion.

        Args:
            task_id: Task ID to poll
            timeout: Override timeout (uses default if not provided)

        Returns:
            Final SkillResult
        """
        effective_timeout = timeout or self.timeout
        start_time = datetime.now()

        while True:
            elapsed = (datetime.now() - start_time).total_seconds()
            if elapsed > effective_timeout:
                return SkillResult(
                    task_id=task_id,
                    status=SkillStatus.FAILED,
                    error=f"Task timed out after {effective_timeout}s"
                )

            result = await self.get_task_status(task_id)

            if result.status in [
                SkillStatus.COMPLETED,
                SkillStatus.FAILED,
                SkillStatus.CANCELLED
            ]:
                return result

            if result.status == SkillStatus.AWAITING_APPROVAL:
                # Keep polling but log the wait
                logger.info("Task %s awaiting HITL approval", task_id)

            await asyncio.sleep(self.poll_interval)

    def _parse_task_response(self, data: Dict[str, Any]) -> SkillResult:
        """Parse API response into SkillResult"""
        status_str = data.get("status", "unknown")
        try:
            status = SkillStatus(status_str.lower())
        except ValueError:
            status = SkillStatus.FAILED

        return SkillResult(
            task_id=data.get("task_id", ""),
            status=status,
            result=data.get("result"),
            error=data.get("error"),
            screenshots=data.get("screenshots", []),
            duration_ms=data.get("duration_ms", 0),
            audit_trail=data.get("audit_trail", [])
        )

    async def close(self):
        """Close HTTP client"""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


# Convenience function for direct use
async def create_connector(
    api_url: Optional[str] = None,
    api_key: Optional[str] = None
) -> SpectaclesSkillConnector:
    """Create and return a Spectacles skill connector"""
    return SpectaclesSkillConnector(
        api_url=api_url,
        api_key=api_key
    )
