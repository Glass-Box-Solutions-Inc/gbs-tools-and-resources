# @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""
Spectacles MCP Tools -- Pure HTTP Client

Thin HTTP client that calls the deployed Spectacles Cloud Run service.
No internal Spectacles module imports. All communication via REST API.

API base URL is read from the SPECTACLES_API_URL environment variable,
defaulting to the production Cloud Run service.
"""

import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

# Default to the canonical production Cloud Run URL
DEFAULT_API_URL = "https://spectacles-gc2qovgs7q-uc.a.run.app"

# HTTP timeout for standard requests (seconds)
DEFAULT_TIMEOUT = 60.0


@dataclass
class TaskResult:
    """Structured result returned by every tool method."""

    success: bool
    task_id: Optional[str] = None
    status: Optional[str] = None
    message: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class SpectaclesTools:
    """
    HTTP client for the deployed Spectacles REST API.

    All methods make outbound HTTP calls -- no Spectacles internal modules
    are imported or instantiated.
    """

    def __init__(self, api_url: Optional[str] = None, api_key: Optional[str] = None):
        """
        Args:
            api_url: Base URL of the Spectacles service.
                     Falls back to SPECTACLES_API_URL env var, then the
                     production Cloud Run URL.
            api_key: Optional API key for authenticated endpoints.
                     Falls back to SPECTACLES_API_KEY env var.
        """
        self.api_url = (
            api_url
            or os.environ.get("SPECTACLES_API_URL", DEFAULT_API_URL)
        ).rstrip("/")
        self.api_key = api_key or os.environ.get("SPECTACLES_API_KEY")

    # --------------------------------------------------------------------- #
    # Internal helpers
    # --------------------------------------------------------------------- #

    def _headers(self) -> Dict[str, str]:
        """Build common request headers."""
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> Dict[str, Any]:
        """
        Execute an HTTP request against the Spectacles API.

        Returns the parsed JSON body on success.
        Raises httpx.HTTPStatusError on 4xx/5xx responses.
        """
        url = f"{self.api_url}{path}"
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(
                method,
                url,
                headers=self._headers(),
                json=json,
                params=params,
            )
            response.raise_for_status()
            return response.json()

    # --------------------------------------------------------------------- #
    # Health
    # --------------------------------------------------------------------- #

    async def health_check(self) -> TaskResult:
        """
        GET /health -- check whether the Spectacles service is reachable.

        Returns:
            TaskResult with service health data.
        """
        try:
            data = await self._request("GET", "/health")
            return TaskResult(
                success=True,
                status=data.get("status"),
                data=data,
            )
        except Exception as exc:
            logger.error("Health check failed: %s", exc)
            return TaskResult(success=False, error=str(exc))

    # --------------------------------------------------------------------- #
    # Task management  (POST /api/tasks/, GET /api/tasks/{id}, etc.)
    # --------------------------------------------------------------------- #

    async def execute_task(
        self,
        goal: str,
        start_url: str,
        credentials_key: Optional[str] = None,
        require_approval: bool = True,
        callback_url: Optional[str] = None,
    ) -> TaskResult:
        """
        POST /api/tasks/ -- submit a browser automation task.

        The task is queued for background execution on the Spectacles
        service.  Use get_task_status() to poll for completion.

        Args:
            goal: Natural language description of what to accomplish.
            start_url: URL to start the browser session at.
            credentials_key: GCP Secret Manager key for login credentials.
            require_approval: Whether HITL approval is needed before actions.
            callback_url: Webhook URL called when the task completes.

        Returns:
            TaskResult with the assigned task_id and initial status.
        """
        payload: Dict[str, Any] = {
            "goal": goal,
            "start_url": start_url,
            "require_approval": require_approval,
        }
        if credentials_key is not None:
            payload["credentials_key"] = credentials_key
        if callback_url is not None:
            payload["callback_url"] = callback_url

        try:
            data = await self._request("POST", "/api/tasks/", json=payload)
            return TaskResult(
                success=True,
                task_id=data.get("task_id"),
                status=data.get("status"),
                message=data.get("message"),
            )
        except httpx.HTTPStatusError as exc:
            logger.error("Task submission failed (HTTP %s): %s", exc.response.status_code, exc)
            return TaskResult(
                success=False,
                error=f"HTTP {exc.response.status_code}: {exc.response.text}",
            )
        except Exception as exc:
            logger.error("Task submission failed: %s", exc)
            return TaskResult(success=False, error=str(exc))

    async def get_task_status(self, task_id: str) -> TaskResult:
        """
        GET /api/tasks/{task_id} -- retrieve the current state of a task.

        Args:
            task_id: The task ID returned from execute_task().

        Returns:
            TaskResult with full task state data.
        """
        try:
            data = await self._request("GET", f"/api/tasks/{task_id}")
            return TaskResult(
                success=True,
                task_id=data.get("task_id", task_id),
                status=data.get("state"),
                data=data,
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return TaskResult(success=False, task_id=task_id, error="Task not found")
            logger.error("Get task status failed (HTTP %s): %s", exc.response.status_code, exc)
            return TaskResult(
                success=False,
                task_id=task_id,
                error=f"HTTP {exc.response.status_code}: {exc.response.text}",
            )
        except Exception as exc:
            logger.error("Get task status failed: %s", exc)
            return TaskResult(success=False, task_id=task_id, error=str(exc))

    async def resume_task(
        self,
        task_id: str,
        approved: bool = True,
        human_input: Optional[Dict[str, Any]] = None,
    ) -> TaskResult:
        """
        POST /api/tasks/{task_id}/resume -- resume a paused task after HITL.

        Args:
            task_id: The task to resume.
            approved: Whether the human approved the pending action.
            human_input: Optional additional data from the human.

        Returns:
            TaskResult indicating resume status.
        """
        payload: Dict[str, Any] = {"approved": approved}
        if human_input is not None:
            payload["human_input"] = human_input

        try:
            data = await self._request("POST", f"/api/tasks/{task_id}/resume", json=payload)
            return TaskResult(
                success=True,
                task_id=data.get("task_id", task_id),
                status=data.get("status"),
                message=data.get("message"),
            )
        except httpx.HTTPStatusError as exc:
            logger.error("Resume task failed (HTTP %s): %s", exc.response.status_code, exc)
            return TaskResult(
                success=False,
                task_id=task_id,
                error=f"HTTP {exc.response.status_code}: {exc.response.text}",
            )
        except Exception as exc:
            logger.error("Resume task failed: %s", exc)
            return TaskResult(success=False, task_id=task_id, error=str(exc))

    async def cancel_task(self, task_id: str) -> TaskResult:
        """
        POST /api/tasks/{task_id}/cancel -- cancel a running task.

        Args:
            task_id: The task to cancel.

        Returns:
            TaskResult indicating cancellation status.
        """
        try:
            data = await self._request("POST", f"/api/tasks/{task_id}/cancel")
            return TaskResult(
                success=True,
                task_id=data.get("task_id", task_id),
                status=data.get("status"),
                message=data.get("message"),
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return TaskResult(success=False, task_id=task_id, error="Task not found")
            logger.error("Cancel task failed (HTTP %s): %s", exc.response.status_code, exc)
            return TaskResult(
                success=False,
                task_id=task_id,
                error=f"HTTP {exc.response.status_code}: {exc.response.text}",
            )
        except Exception as exc:
            logger.error("Cancel task failed: %s", exc)
            return TaskResult(success=False, task_id=task_id, error=str(exc))

    async def get_task_actions(self, task_id: str, limit: int = 50) -> TaskResult:
        """
        GET /api/tasks/{task_id}/actions -- retrieve action history.

        Args:
            task_id: The task whose actions to retrieve.
            limit: Maximum number of actions to return.

        Returns:
            TaskResult with action history in data.
        """
        try:
            data = await self._request(
                "GET",
                f"/api/tasks/{task_id}/actions",
                params={"limit": limit},
            )
            return TaskResult(success=True, task_id=task_id, data=data)
        except Exception as exc:
            logger.error("Get task actions failed: %s", exc)
            return TaskResult(success=False, task_id=task_id, error=str(exc))

    # --------------------------------------------------------------------- #
    # Skills API  (POST /api/skills/...)
    # --------------------------------------------------------------------- #

    async def take_screenshot(
        self,
        url: str,
        full_page: bool = True,
        blur_pii: bool = True,
        mode: str = "browser",
    ) -> TaskResult:
        """
        POST /api/skills/screenshot -- capture a screenshot via the deployed service.

        Args:
            url: URL to navigate to and screenshot.
            full_page: Whether to capture the full scrollable page.
            blur_pii: Whether to apply PII detection and blur.
            mode: "browser" (default) or "desktop" (VM deployments only).

        Returns:
            TaskResult with screenshot_path, task_id, and duration_ms in data.
        """
        payload: Dict[str, Any] = {
            "url": url,
            "mode": mode,
            "full_page": full_page,
            "blur_pii": blur_pii,
        }

        try:
            data = await self._request("POST", "/api/skills/screenshot", json=payload)
            return TaskResult(
                success=True,
                task_id=data.get("task_id"),
                data=data,
            )
        except httpx.HTTPStatusError as exc:
            logger.error("Screenshot failed (HTTP %s): %s", exc.response.status_code, exc)
            return TaskResult(
                success=False,
                error=f"HTTP {exc.response.status_code}: {exc.response.text}",
            )
        except Exception as exc:
            logger.error("Screenshot failed: %s", exc)
            return TaskResult(success=False, error=str(exc))

    async def submit_browser_task(
        self,
        goal: str,
        start_url: str,
        require_approval: bool = True,
        credentials_key: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        callback_url: Optional[str] = None,
    ) -> TaskResult:
        """
        POST /api/skills/browser -- submit a browser task via the Skills API.

        This is the AI-agent-optimized variant of execute_task().  It accepts
        an additional context dict and routes through the Skills endpoint.

        Args:
            goal: Natural language goal.
            start_url: Starting URL.
            require_approval: Whether HITL approval is needed.
            credentials_key: GCP Secret Manager key for credentials.
            context: Extra context for the task.
            callback_url: Webhook URL for async completion.

        Returns:
            TaskResult with task_id and status.
        """
        payload: Dict[str, Any] = {
            "goal": goal,
            "start_url": start_url,
            "require_approval": require_approval,
        }
        if credentials_key is not None:
            payload["credentials_key"] = credentials_key
        if context is not None:
            payload["context"] = context
        if callback_url is not None:
            payload["callback_url"] = callback_url

        try:
            data = await self._request("POST", "/api/skills/browser", json=payload)
            return TaskResult(
                success=True,
                task_id=data.get("task_id"),
                status=data.get("status"),
                message=data.get("message"),
            )
        except httpx.HTTPStatusError as exc:
            logger.error("Browser task failed (HTTP %s): %s", exc.response.status_code, exc)
            return TaskResult(
                success=False,
                error=f"HTTP {exc.response.status_code}: {exc.response.text}",
            )
        except Exception as exc:
            logger.error("Browser task failed: %s", exc)
            return TaskResult(success=False, error=str(exc))

    async def get_capabilities(self) -> TaskResult:
        """
        GET /api/skills/capabilities -- query available automation capabilities.

        Returns:
            TaskResult with capability data (browser, desktop, files, modes).
        """
        try:
            data = await self._request("GET", "/api/skills/capabilities")
            return TaskResult(success=True, data=data)
        except Exception as exc:
            logger.error("Get capabilities failed: %s", exc)
            return TaskResult(success=False, error=str(exc))
