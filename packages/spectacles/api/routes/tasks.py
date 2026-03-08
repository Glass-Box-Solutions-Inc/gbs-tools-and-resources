"""
Spectacles Task Routes
API endpoints for task management
"""

import logging
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from pydantic import BaseModel, Field, ConfigDict

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tasks", tags=["Tasks"])


# =============================================================================
# Request/Response Models
# =============================================================================

class TaskSubmitRequest(BaseModel):
    """Request to submit a new task"""
    goal: str = Field(..., description="Natural language goal")
    start_url: str = Field(..., description="Starting URL")
    credentials_key: Optional[str] = Field(None, description="GCP Secret Manager key")
    require_approval: bool = Field(True, description="Require HITL approval")
    callback_url: Optional[str] = Field(None, description="Webhook on completion")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "goal": "Log into example.com and download the monthly report",
            "start_url": "https://example.com/login",
            "credentials_key": "example-com-login",
            "require_approval": True
        }
    })


class TaskResponse(BaseModel):
    """Task submission response"""
    task_id: str
    status: str
    message: str


class TaskStatusResponse(BaseModel):
    """Task status response"""
    task_id: str
    goal: str
    state: str
    step: int
    total_steps: int
    is_active: bool
    created_at: Optional[str]
    updated_at: Optional[str]
    error: Optional[str]
    checkpoint_id: Optional[str]


class TaskResumeRequest(BaseModel):
    """Request to resume a paused task"""
    approved: bool = Field(..., description="Whether to approve the action")
    human_input: Optional[Dict[str, Any]] = Field(None, description="Additional input")


# =============================================================================
# Dependency for Orchestrator
# =============================================================================

_orchestrator = None


def get_orchestrator():
    """Get or create orchestrator instance"""
    global _orchestrator
    if _orchestrator is None:
        from core.orchestrator import Orchestrator
        from browser.client import BrowserClient
        from api.config import settings

        browser_client = BrowserClient(
            api_token=settings.BROWSERLESS_API_TOKEN,
            endpoint=settings.BROWSERLESS_ENDPOINT,
            use_local=settings.USE_LOCAL_BROWSER
        )

        # VLM perceiver if configured
        vlm_perceiver = None
        if settings.has_vlm:
            from core.perception import VLMPerceiver
            vlm_perceiver = VLMPerceiver(
                api_key=settings.GOOGLE_AI_API_KEY,
                model=settings.VLM_MODEL
            )

        _orchestrator = Orchestrator(
            browser_client=browser_client,
            vlm_perceiver=vlm_perceiver
        )

    return _orchestrator


# =============================================================================
# Endpoints
# =============================================================================

@router.post("/", response_model=TaskResponse)
async def submit_task(
    request: TaskSubmitRequest,
    background_tasks: BackgroundTasks
):
    """
    Submit a new browser automation task.

    The task will be queued for execution in the background.
    """
    try:
        orchestrator = get_orchestrator()

        task_id = await orchestrator.submit_task(
            goal=request.goal,
            start_url=request.start_url,
            credentials_key=request.credentials_key,
            require_approval=request.require_approval,
            callback_url=request.callback_url
        )

        # Execute in background
        background_tasks.add_task(orchestrator.execute_task, task_id)

        return TaskResponse(
            task_id=task_id,
            status="submitted",
            message="Task queued for execution"
        )

    except Exception as e:
        logger.error("Task submission failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/execute", response_model=Dict[str, Any])
async def execute_task_sync(request: TaskSubmitRequest):
    """
    Submit and execute a task synchronously.

    This endpoint waits for task completion before returning.
    Use this for Cloud Run or when you need immediate results.
    Timeout is 5 minutes max.
    """
    try:
        orchestrator = get_orchestrator()

        # Submit task
        task_id = await orchestrator.submit_task(
            goal=request.goal,
            start_url=request.start_url,
            credentials_key=request.credentials_key,
            require_approval=request.require_approval,
            callback_url=request.callback_url
        )

        # Execute synchronously
        result = await orchestrator.execute_task(task_id)

        return {
            "task_id": task_id,
            "result": result
        }

    except Exception as e:
        logger.error("Task execution failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    """Get status of a task"""
    try:
        orchestrator = get_orchestrator()
        status = await orchestrator.get_task_status(task_id)

        if "error" in status and status["error"] == "Task not found":
            raise HTTPException(status_code=404, detail="Task not found")

        return TaskStatusResponse(**status)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get task status: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{task_id}/resume", response_model=TaskResponse)
async def resume_task(
    task_id: str,
    request: TaskResumeRequest,
    background_tasks: BackgroundTasks
):
    """
    Resume a paused task after HITL response.

    Call this endpoint when a human has responded to an approval request.
    """
    try:
        orchestrator = get_orchestrator()

        # Resume in background
        background_tasks.add_task(
            orchestrator.resume_task,
            task_id,
            request.approved,
            request.human_input
        )

        return TaskResponse(
            task_id=task_id,
            status="resuming",
            message="Task resuming with human input"
        )

    except Exception as e:
        logger.error("Failed to resume task: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{task_id}/cancel", response_model=TaskResponse)
async def cancel_task(task_id: str):
    """Cancel a running task"""
    try:
        orchestrator = get_orchestrator()
        success = await orchestrator.cancel_task(task_id)

        if success:
            return TaskResponse(
                task_id=task_id,
                status="cancelled",
                message="Task has been cancelled"
            )
        else:
            raise HTTPException(status_code=404, detail="Task not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to cancel task: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{task_id}/actions")
async def get_task_actions(task_id: str, limit: int = 50):
    """Get action history for a task"""
    try:
        from persistence.task_store import TaskStore
        task_store = TaskStore()
        actions = task_store.get_action_history(task_id, limit=limit)
        return {"task_id": task_id, "actions": actions}

    except Exception as e:
        logger.error("Failed to get actions: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
