# @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""
Spectacles MCP Server -- Thin HTTP Client

FastMCP server that exposes browser automation tools by proxying to the
deployed Spectacles Cloud Run service via REST API.

No Spectacles internal modules are imported.  The SPECTACLES_API_URL
environment variable controls the target service URL.
"""

import logging
from typing import Any, Dict, Optional

from mcp.server.fastmcp import FastMCP

from .tools import SpectaclesTools

logger = logging.getLogger(__name__)


def create_mcp_server() -> FastMCP:
    """
    Create and configure the Spectacles MCP server.

    Returns:
        Configured FastMCP server instance.
    """
    mcp = FastMCP(
        name="spectacles",
        description=(
            "Spectacles Browser Automation -- submit tasks, take screenshots, "
            "and manage browser automation jobs on the deployed Spectacles "
            "Cloud Run service via REST API."
        ),
    )

    tools = SpectaclesTools()

    # =========================================================================
    # Tool: Execute Task
    # =========================================================================

    @mcp.tool()
    async def spectacles_execute_task(
        goal: str,
        start_url: str,
        credentials_key: Optional[str] = None,
        require_approval: bool = True,
        callback_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Submit a browser automation task to the Spectacles service.

        The task is queued for background execution.  Use
        spectacles_get_task_status to poll for completion.

        Args:
            goal: Natural language description of what to accomplish.
                  Example: "Log into the dashboard and download the monthly report"
            start_url: URL to start the browser session at.
                  Example: "https://app.example.com/login"
            credentials_key: Optional GCP Secret Manager key for credentials.
            require_approval: Require human approval via Slack before actions (default True).
            callback_url: Optional webhook URL called on task completion.

        Returns:
            Dict with success, task_id, status, message, and error fields.
        """
        result = await tools.execute_task(
            goal=goal,
            start_url=start_url,
            credentials_key=credentials_key,
            require_approval=require_approval,
            callback_url=callback_url,
        )
        return {
            "success": result.success,
            "task_id": result.task_id,
            "status": result.status,
            "message": result.message,
            "error": result.error,
        }

    # =========================================================================
    # Tool: Get Task Status
    # =========================================================================

    @mcp.tool()
    async def spectacles_get_task_status(task_id: str) -> Dict[str, Any]:
        """
        Get the current status of a browser automation task.

        Possible states: PLANNING, NAVIGATING, OBSERVING, ACTING,
        EVALUATING, AWAITING_HUMAN, ERROR_RECOVERY, COMPLETED, FAILED.

        Args:
            task_id: The task ID returned from spectacles_execute_task.

        Returns:
            Dict with success, task_id, status, full task data, and error.
        """
        result = await tools.get_task_status(task_id)
        return {
            "success": result.success,
            "task_id": result.task_id,
            "status": result.status,
            "data": result.data,
            "error": result.error,
        }

    # =========================================================================
    # Tool: Resume Task
    # =========================================================================

    @mcp.tool()
    async def spectacles_resume_task(
        task_id: str,
        approved: bool = True,
        human_input: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Resume a paused task after human input.

        When a task is in AWAITING_HUMAN state, call this to provide the
        human decision and continue (or reject) execution.

        Args:
            task_id: The task ID to resume.
            approved: True to approve and continue, False to reject and stop.
            human_input: Optional extra data from the human reviewer.

        Returns:
            Dict with success, task_id, status, message, and error.
        """
        result = await tools.resume_task(
            task_id=task_id,
            approved=approved,
            human_input=human_input,
        )
        return {
            "success": result.success,
            "task_id": result.task_id,
            "status": result.status,
            "message": result.message,
            "error": result.error,
        }

    # =========================================================================
    # Tool: Cancel Task
    # =========================================================================

    @mcp.tool()
    async def spectacles_cancel_task(task_id: str) -> Dict[str, Any]:
        """
        Cancel a running browser automation task.  This cannot be undone.

        Args:
            task_id: The task ID to cancel.

        Returns:
            Dict with success, task_id, status, message, and error.
        """
        result = await tools.cancel_task(task_id)
        return {
            "success": result.success,
            "task_id": result.task_id,
            "status": result.status,
            "message": result.message,
            "error": result.error,
        }

    # =========================================================================
    # Tool: Take Screenshot
    # =========================================================================

    @mcp.tool()
    async def spectacles_take_screenshot(
        url: str,
        full_page: bool = True,
        blur_pii: bool = True,
    ) -> Dict[str, Any]:
        """
        Take a screenshot of a URL via the Spectacles service.

        Navigates to the URL and captures a screenshot.  Optionally blurs
        detected PII (emails, phone numbers, SSNs) for HIPAA compliance.

        Args:
            url: URL to screenshot.
            full_page: Capture the full scrollable page (default True).
            blur_pii: Blur detected PII in the screenshot (default True).

        Returns:
            Dict with success, task_id, screenshot data, and error.
        """
        result = await tools.take_screenshot(
            url=url,
            full_page=full_page,
            blur_pii=blur_pii,
        )
        return {
            "success": result.success,
            "task_id": result.task_id,
            "data": result.data,
            "error": result.error,
        }

    # =========================================================================
    # Tool: Health Check
    # =========================================================================

    @mcp.tool()
    async def spectacles_health_check() -> Dict[str, Any]:
        """
        Check whether the Spectacles Cloud Run service is reachable.

        Returns:
            Dict with success, status, health data, and error.
        """
        result = await tools.health_check()
        return {
            "success": result.success,
            "status": result.status,
            "data": result.data,
            "error": result.error,
        }

    # =========================================================================
    # Tool: Get Capabilities
    # =========================================================================

    @mcp.tool()
    async def spectacles_get_capabilities() -> Dict[str, Any]:
        """
        Query available automation capabilities of the Spectacles service.

        Returns which modes are available (browser, desktop, files) based
        on the deployment environment.

        Returns:
            Dict with success, capability data, and error.
        """
        result = await tools.get_capabilities()
        return {
            "success": result.success,
            "data": result.data,
            "error": result.error,
        }

    return mcp
