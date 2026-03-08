"""
Specticles Integration Client

Async HTTP client for Specticles visual analysis API.
Provides HITL approval, VLM element finding, and PII-blurred screenshots.
"""

import asyncio
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)


@dataclass
class SpecticlesConfig:
    """Specticles client configuration"""
    api_url: str = "http://localhost:8080"
    api_key: Optional[str] = None
    timeout_seconds: int = 300
    poll_interval_seconds: float = 2.0
    require_approval: bool = True


@dataclass
class TaskResult:
    """Result from a Specticles task"""
    task_id: str
    status: str
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    screenshot_path: Optional[str] = None


class SpecticlesClient:
    """
    Client for Specticles visual analysis API.

    Provides:
    - Browser task execution with HITL approval
    - VLM-powered page analysis
    - PII-blurred screenshots
    - Async polling for task completion
    """

    def __init__(self, config: Optional[SpecticlesConfig] = None):
        """
        Initialize the Specticles client.

        Args:
            config: Optional configuration. Uses environment defaults if not provided.
        """
        self.config = config or SpecticlesConfig()
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        """Async context manager entry"""
        await self._ensure_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        """Ensure HTTP client is initialized"""
        if self._client is None:
            headers = {"Content-Type": "application/json"}
            if self.config.api_key:
                headers["Authorization"] = f"Bearer {self.config.api_key}"
            self._client = httpx.AsyncClient(
                base_url=self.config.api_url,
                headers=headers,
                timeout=httpx.Timeout(30.0)
            )
        return self._client

    async def health_check(self) -> bool:
        """
        Check if Specticles API is healthy.

        Returns:
            True if healthy, False otherwise
        """
        try:
            client = await self._ensure_client()
            response = await client.get("/health")
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Specticles health check failed: {e}")
            return False

    async def get_capabilities(self) -> Dict[str, Any]:
        """
        Get available Specticles capabilities.

        Returns:
            Dictionary with browser, desktop, files capabilities
        """
        client = await self._ensure_client()
        response = await client.get("/skills/capabilities")
        response.raise_for_status()
        return response.json()

    async def execute_task(
        self,
        goal: str,
        start_url: str,
        require_approval: Optional[bool] = None,
        credentials_key: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        wait_for_completion: bool = True
    ) -> TaskResult:
        """
        Execute a browser automation task.

        Args:
            goal: Natural language description of the task
            start_url: Starting URL for the browser
            require_approval: Override HITL approval setting
            credentials_key: GCP Secret Manager key for credentials
            context: Additional context for the task
            wait_for_completion: Whether to poll until complete

        Returns:
            TaskResult with status and any output data
        """
        client = await self._ensure_client()

        payload = {
            "goal": goal,
            "start_url": start_url,
            "require_approval": require_approval if require_approval is not None else self.config.require_approval,
        }

        if credentials_key:
            payload["credentials_key"] = credentials_key
        if context:
            payload["context"] = context

        logger.info(f"Submitting Specticles task: {goal[:50]}...")

        response = await client.post("/skills/browser", json=payload)
        response.raise_for_status()
        result = response.json()

        task_id = result["task_id"]
        logger.info(f"Task submitted: {task_id}")

        if wait_for_completion:
            return await self.wait_for_completion(task_id)

        return TaskResult(
            task_id=task_id,
            status=result.get("status", "pending"),
            success=True
        )

    async def get_task_status(self, task_id: str) -> TaskResult:
        """
        Get the current status of a task.

        Args:
            task_id: The task ID to check

        Returns:
            TaskResult with current status
        """
        client = await self._ensure_client()
        response = await client.get(f"/tasks/{task_id}")
        response.raise_for_status()
        data = response.json()

        return TaskResult(
            task_id=task_id,
            status=data.get("state", "unknown"),
            success=data.get("state") == "COMPLETED",
            data=data,
            error=data.get("error")
        )

    async def wait_for_completion(
        self,
        task_id: str,
        timeout_seconds: Optional[int] = None
    ) -> TaskResult:
        """
        Poll until task completes or times out.

        Args:
            task_id: The task ID to wait for
            timeout_seconds: Override default timeout

        Returns:
            TaskResult with final status
        """
        timeout = timeout_seconds or self.config.timeout_seconds
        elapsed = 0.0

        logger.info(f"Waiting for task {task_id} (timeout: {timeout}s)")

        while elapsed < timeout:
            result = await self.get_task_status(task_id)

            if result.status in ("COMPLETED", "FAILED", "CANCELLED"):
                logger.info(f"Task {task_id} finished: {result.status}")
                return result

            if result.status == "AWAITING_HUMAN":
                logger.info(f"Task {task_id} awaiting human approval...")

            await asyncio.sleep(self.config.poll_interval_seconds)
            elapsed += self.config.poll_interval_seconds

        logger.warning(f"Task {task_id} timed out after {timeout}s")
        return TaskResult(
            task_id=task_id,
            status="TIMEOUT",
            success=False,
            error=f"Task timed out after {timeout} seconds"
        )

    async def take_screenshot(
        self,
        url: Optional[str] = None,
        blur_pii: bool = True,
        full_page: bool = True,
        mode: str = "browser"
    ) -> TaskResult:
        """
        Capture a screenshot with optional PII blurring.

        Args:
            url: URL to screenshot (navigates if provided)
            blur_pii: Whether to blur detected PII
            full_page: Capture full page or viewport only
            mode: "browser" or "desktop"

        Returns:
            TaskResult with screenshot_path
        """
        client = await self._ensure_client()

        payload = {
            "mode": mode,
            "blur_pii": blur_pii,
            "full_page": full_page
        }

        if url:
            payload["url"] = url

        response = await client.post("/skills/screenshot", json=payload)
        response.raise_for_status()
        data = response.json()

        return TaskResult(
            task_id=data.get("task_id", ""),
            status="completed",
            success=True,
            screenshot_path=data.get("screenshot_path"),
            data=data
        )

    async def analyze_page(
        self,
        url: str,
        question: str,
        require_approval: bool = False
    ) -> TaskResult:
        """
        Use VLM to analyze a page and answer a question.

        This submits a task with a goal phrased as an analysis question.

        Args:
            url: URL to analyze
            question: Question to answer about the page
            require_approval: Whether to require HITL approval

        Returns:
            TaskResult with analysis in data field
        """
        goal = f"Navigate to the page and analyze: {question}"

        return await self.execute_task(
            goal=goal,
            start_url=url,
            require_approval=require_approval,
            context={"analysis_mode": True, "question": question}
        )

    async def request_approval(
        self,
        action_description: str,
        current_url: str,
        context: Optional[Dict[str, Any]] = None
    ) -> TaskResult:
        """
        Request HITL approval before performing an action.

        Submits a task that will pause for human approval via Slack.

        Args:
            action_description: What action needs approval
            current_url: Current page URL
            context: Additional context for the approver

        Returns:
            TaskResult indicating approval status
        """
        goal = f"APPROVAL REQUIRED: {action_description}"

        return await self.execute_task(
            goal=goal,
            start_url=current_url,
            require_approval=True,  # Always require approval for this
            context={
                "approval_request": True,
                "action": action_description,
                **(context or {})
            }
        )

    async def find_element_with_vlm(
        self,
        url: str,
        element_description: str
    ) -> Optional[str]:
        """
        Use VLM to find an element by natural language description.

        Useful as a fallback when CSS/XPath selectors fail.

        Args:
            url: Page URL
            element_description: Natural language description of the element

        Returns:
            Selector string if found, None otherwise
        """
        result = await self.analyze_page(
            url=url,
            question=f"Find the element matching: {element_description}. "
                     f"Return the best CSS selector or XPath to locate it.",
            require_approval=False
        )

        if result.success and result.data:
            return result.data.get("selector")
        return None


def create_client_from_config(config_obj) -> SpecticlesClient:
    """
    Create a SpecticlesClient from a SecurityConfig object.

    Args:
        config_obj: SecurityConfig with specticles_* attributes

    Returns:
        Configured SpecticlesClient
    """
    specticles_config = SpecticlesConfig(
        api_url=getattr(config_obj, 'specticles_api_url', 'http://localhost:8080'),
        api_key=getattr(config_obj, 'specticles_api_key', None),
        timeout_seconds=getattr(config_obj, 'specticles_timeout_seconds', 300),
        require_approval=getattr(config_obj, 'specticles_require_approval', True)
    )
    return SpecticlesClient(specticles_config)
