"""
Spectacles Skills Routes
Skill-optimized API endpoints for Glassy and other AI agents

SOC2/HIPAA Compliant with full audit logging.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import logging
import uuid
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field, ConfigDict

from core.capabilities import get_capabilities
from persistence.constants import AutomationMode, ActionStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/skills", tags=["Skills"])


# =============================================================================
# Request/Response Models
# =============================================================================

class CapabilitiesResponse(BaseModel):
    """Available capabilities response"""
    browser: bool = Field(True, description="Browser automation available")
    desktop: bool = Field(False, description="Desktop automation available")
    files: bool = Field(False, description="File operations available")
    modes: List[str] = Field(default_factory=list, description="Available modes")
    deployment: str = Field("unknown", description="Deployment environment")
    has_display: bool = Field(False, description="Display available for desktop")


class BrowserTaskRequest(BaseModel):
    """Browser automation task request"""
    goal: str = Field(..., description="Natural language goal")
    start_url: str = Field(..., description="Starting URL")
    require_approval: bool = Field(True, description="Require HITL approval")
    credentials_key: Optional[str] = Field(None, description="GCP Secret Manager key for credentials")
    context: Optional[Dict[str, Any]] = Field(None, description="Additional context")
    callback_url: Optional[str] = Field(None, description="Webhook URL for async completion")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "goal": "Log into MerusCase and export the billing report for December",
            "start_url": "https://app.meruscase.com/login",
            "require_approval": True,
            "credentials_key": "meruscase-admin",
            "context": {"report_type": "billing", "month": "December"}
        }
    })


class DesktopTaskRequest(BaseModel):
    """Desktop automation task request"""
    goal: str = Field(..., description="Natural language goal")
    app_name: Optional[str] = Field(None, description="Application to open/control")
    require_approval: bool = Field(True, description="Require HITL approval")
    context: Optional[Dict[str, Any]] = Field(None, description="Additional context")
    callback_url: Optional[str] = Field(None, description="Webhook URL for async completion")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "goal": "Open Excel and export the billing spreadsheet as PDF",
            "app_name": "Microsoft Excel",
            "require_approval": True,
            "context": {"file_path": "C:/Documents/Billing.xlsx"}
        }
    })


class ScreenshotRequest(BaseModel):
    """Screenshot capture request"""
    url: Optional[str] = Field(None, description="URL to screenshot (browser mode)")
    mode: str = Field("browser", description="Mode: browser or desktop")
    full_page: bool = Field(True, description="Capture full page (browser only)")
    blur_pii: bool = Field(True, description="Apply PII detection and blur")
    region: Optional[List[int]] = Field(None, description="Screen region [x, y, width, height] for desktop")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "url": "https://example.com",
            "mode": "browser",
            "full_page": True,
            "blur_pii": True
        }
    })


class FileOperationRequest(BaseModel):
    """File system operation request"""
    operation: str = Field(..., description="Operation: read, write, list, copy, move, delete")
    path: str = Field(..., description="Target file/directory path")
    content: Optional[str] = Field(None, description="Content to write (for write operation)")
    destination: Optional[str] = Field(None, description="Destination path (for copy/move)")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "operation": "read",
            "path": "/tmp/spectacles/report.csv"
        }
    })


class TaskResponse(BaseModel):
    """Task submission response"""
    task_id: str
    status: str
    message: str


class ScreenshotResponse(BaseModel):
    """Screenshot response"""
    task_id: str
    screenshot_path: str
    duration_ms: int


class FileOperationResponse(BaseModel):
    """File operation response"""
    task_id: str
    operation: str
    result: Optional[Dict[str, Any]]
    duration_ms: int


class CallbackRequest(BaseModel):
    """Callback from Glassy or other system"""
    task_id: str
    callback_type: str = Field(..., description="Type: task_complete, approval_response, etc.")
    data: Optional[Dict[str, Any]] = Field(None, description="Callback data")


# =============================================================================
# Auth Capture Models
# =============================================================================

class AuthCaptureStartRequest(BaseModel):
    """Start an auth capture session"""
    service: str = Field(..., description="Service name or preset (google, github, meruscase, westlaw)")
    login_url: Optional[str] = Field(None, description="Login page URL (overrides preset)")
    verify_url: Optional[str] = Field(None, description="URL to verify auth after capture")
    credential_key: Optional[str] = Field(None, description="Secret Manager key (default: {service}-auth)")
    timeout_ms: int = Field(600_000, description="Live session timeout in ms")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "service": "google",
            "timeout_ms": 600000
        }
    })


class AuthCaptureStartResponse(BaseModel):
    """Auth capture session started"""
    session_id: str
    live_url: str
    status: str
    message: str


class AuthCaptureCompleteResponse(BaseModel):
    """Auth capture completed"""
    session_id: str
    status: str
    cookie_count: int
    origin_count: int
    local_path: Optional[str]
    gcp_saved: bool
    secret_name: str
    verified: bool


class AuthCaptureStatusResponse(BaseModel):
    """Auth capture session status"""
    session_id: str
    status: str
    service: str


# In-memory store for active auth capture sessions (short-lived, 10min max)
_active_auth_sessions: Dict[str, Any] = {}


# =============================================================================
# Endpoints
# =============================================================================

@router.get("/capabilities", response_model=CapabilitiesResponse)
async def get_skill_capabilities():
    """
    Get available Spectacles capabilities.

    Returns what automation modes are available based on deployment environment.
    Desktop automation requires VM deployment with display access.
    """
    caps = get_capabilities()

    return CapabilitiesResponse(
        browser="browser" in caps.available_modes,
        desktop="desktop" in caps.available_modes,
        files="files" in caps.available_modes,
        modes=caps.available_modes,
        deployment=caps.deployment.value,
        has_display=caps.has_display
    )


@router.post("/browser", response_model=TaskResponse)
async def submit_browser_task(
    request: BrowserTaskRequest,
    background_tasks: BackgroundTasks
):
    """
    Submit browser automation task.

    Executes web automation using Playwright via Browserless.
    Supports HITL approval for sensitive actions.
    """
    import uuid

    task_id = str(uuid.uuid4())

    # Import orchestrator
    from api.routes.tasks import get_orchestrator
    orchestrator = get_orchestrator()

    if orchestrator is None:
        raise HTTPException(
            status_code=503,
            detail="Orchestrator not available"
        )

    # Add task to background
    background_tasks.add_task(
        _run_browser_task,
        orchestrator,
        task_id,
        request.goal,
        request.start_url,
        request.require_approval,
        request.credentials_key,
        request.context,
        request.callback_url
    )

    return TaskResponse(
        task_id=task_id,
        status="pending",
        message=f"Browser task submitted: {request.goal[:50]}..."
    )


@router.post("/desktop", response_model=TaskResponse)
async def submit_desktop_task(
    request: DesktopTaskRequest,
    background_tasks: BackgroundTasks
):
    """
    Submit desktop automation task.

    Executes native app automation using PyAutoGUI and mss.
    Only available on VM deployments with display access.
    """
    import uuid

    # Check if desktop is available
    caps = get_capabilities()
    if "desktop" not in caps.available_modes:
        raise HTTPException(
            status_code=503,
            detail=f"Desktop automation not available. "
                   f"Deployment: {caps.deployment.value}, Display: {caps.has_display}"
        )

    task_id = str(uuid.uuid4())

    # Add task to background
    background_tasks.add_task(
        _run_desktop_task,
        task_id,
        request.goal,
        request.app_name,
        request.require_approval,
        request.context,
        request.callback_url
    )

    return TaskResponse(
        task_id=task_id,
        status="pending",
        message=f"Desktop task submitted: {request.goal[:50]}..."
    )


@router.post("/screenshot", response_model=ScreenshotResponse)
async def take_screenshot(request: ScreenshotRequest):
    """
    Take screenshot.

    Captures current browser page or desktop screen.
    Optionally applies PII detection and blur for HIPAA compliance.
    """
    import uuid
    import time

    task_id = str(uuid.uuid4())[:8]
    start_time = time.time()

    caps = get_capabilities()

    if request.mode == "desktop":
        if "desktop" not in caps.available_modes:
            raise HTTPException(
                status_code=503,
                detail="Desktop mode not available"
            )

        from core.desktop_specialist import DesktopSpecialist

        specialist = DesktopSpecialist()
        region = tuple(request.region) if request.region else None

        result = await specialist.screenshot(
            region=region,
            task_id=task_id
        )

        if result.status.value != "success":
            raise HTTPException(
                status_code=500,
                detail=result.error or "Screenshot failed"
            )

        screenshot_path = result.screenshot_path

    else:
        # Browser screenshot
        from api.routes.tasks import get_orchestrator
        orchestrator = get_orchestrator()

        if orchestrator is None:
            raise HTTPException(
                status_code=503,
                detail="Browser not available"
            )

        # Ensure browser is connected
        if not orchestrator.browser_client.is_connected:
            logger.info("Connecting to browser for screenshot task %s", task_id)
            await orchestrator.browser_client.connect()

        if request.url:
            await orchestrator.browser_specialist.navigate(
                url=request.url,
                task_id=task_id
            )

        result = await orchestrator.browser_specialist.screenshot(
            full_page=request.full_page,
            task_id=task_id
        )

        if result.status != ActionStatus.SUCCESS:
            raise HTTPException(
                status_code=500,
                detail=result.error or "Screenshot failed"
            )

        screenshot_path = result.screenshot_path

    # Apply PII blur if requested
    if request.blur_pii and screenshot_path:
        screenshot_path = await _apply_pii_blur(screenshot_path)

    duration_ms = int((time.time() - start_time) * 1000)

    return ScreenshotResponse(
        task_id=task_id,
        screenshot_path=screenshot_path or "",
        duration_ms=duration_ms
    )


@router.post("/file", response_model=FileOperationResponse)
async def execute_file_operation(request: FileOperationRequest):
    """
    Execute file system operation.

    Sandboxed file operations with audit logging.
    Only works with allowed paths configured in settings.
    """
    import uuid
    import time

    # Check if files is available
    caps = get_capabilities()
    if "files" not in caps.available_modes:
        raise HTTPException(
            status_code=503,
            detail="File operations not available"
        )

    task_id = str(uuid.uuid4())[:8]
    start_time = time.time()

    try:
        from core.file_specialist import FileSpecialist

        specialist = FileSpecialist()

        if request.operation == "read":
            result = await specialist.read_file(
                path=request.path,
                task_id=task_id
            )
        elif request.operation == "write":
            result = await specialist.write_file(
                path=request.path,
                content=request.content or "",
                task_id=task_id
            )
        elif request.operation == "list":
            result = await specialist.list_directory(
                path=request.path,
                task_id=task_id
            )
        elif request.operation == "copy":
            result = await specialist.copy_file(
                source=request.path,
                destination=request.destination or "",
                task_id=task_id
            )
        elif request.operation == "move":
            result = await specialist.move_file(
                source=request.path,
                destination=request.destination or "",
                task_id=task_id
            )
        elif request.operation == "delete":
            result = await specialist.delete_file(
                path=request.path,
                task_id=task_id
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown operation: {request.operation}"
            )

        duration_ms = int((time.time() - start_time) * 1000)

        return FileOperationResponse(
            task_id=task_id,
            operation=request.operation,
            result=result.data if hasattr(result, 'data') else None,
            duration_ms=duration_ms
        )

    except PermissionError as e:
        raise HTTPException(
            status_code=403,
            detail=f"Permission denied: {e}"
        )
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=404,
            detail=f"File not found: {e}"
        )


# =============================================================================
# Auth Capture Endpoints
# =============================================================================

@router.post("/auth-capture", response_model=AuthCaptureStartResponse)
async def start_auth_capture(request: AuthCaptureStartRequest):
    """
    Start an auth capture session.

    Creates a live Browserless browser session and navigates to the login page.
    Returns a live_url that should be opened in a browser to complete login.
    After login, call POST /auth-capture/{session_id}/complete to capture state.
    """
    from security.auth_capture import AuthCaptureSession
    from api.config import settings

    session_id = str(uuid.uuid4())[:12]

    try:
        session = AuthCaptureSession(
            service=request.service,
            login_url=request.login_url,
            verify_url=request.verify_url,
            credential_key=request.credential_key,
            browserless_token=settings.BROWSERLESS_API_TOKEN,
            browserless_wss=settings.BROWSERLESS_ENDPOINT,
            timeout_ms=request.timeout_ms,
        )

        live_url = await session.start()
        _active_auth_sessions[session_id] = session

        logger.info("Auth capture session %s started for %s", session_id, request.service)

        return AuthCaptureStartResponse(
            session_id=session_id,
            live_url=live_url,
            status="awaiting_login",
            message="Open live_url in browser and complete login",
        )

    except Exception as e:
        logger.error("Failed to start auth capture session: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/auth-capture/{session_id}/complete", response_model=AuthCaptureCompleteResponse)
async def complete_auth_capture(session_id: str):
    """
    Complete auth capture: capture cookies/localStorage, save, verify, and close.

    Call this after the user has finished logging in via the live browser session.
    Saves state locally to .auth/ and to GCP Secret Manager.
    """
    from pathlib import Path
    from api.config import settings

    session = _active_auth_sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    try:
        # Capture
        state = await session.capture()
        cookie_count = len(state.get("cookies", []))
        origin_count = len(state.get("origins", []))

        if cookie_count == 0:
            await session.close()
            _active_auth_sessions.pop(session_id, None)
            raise HTTPException(
                status_code=422,
                detail="No cookies captured - login may not have completed",
            )

        # Save locally and to GCP
        auth_dir = str(Path(__file__).resolve().parents[3] / ".auth")
        gcp_project = settings.GCP_PROJECT_ID

        results = await session.save(local_dir=auth_dir, gcp_project=gcp_project)

        # Verify
        verified = await session.verify()

        # Close and clean up
        await session.close()
        _active_auth_sessions.pop(session_id, None)

        logger.info(
            "Auth capture session %s completed: %d cookies, verified=%s",
            session_id,
            cookie_count,
            verified,
        )

        return AuthCaptureCompleteResponse(
            session_id=session_id,
            status="captured",
            cookie_count=cookie_count,
            origin_count=origin_count,
            local_path=results.get("local_path"),
            gcp_saved=results.get("gcp_saved", False),
            secret_name=results.get("secret_name", ""),
            verified=verified,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Auth capture completion failed for %s: %s", session_id, e)
        # Clean up on failure
        await session.close()
        _active_auth_sessions.pop(session_id, None)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/auth-capture/{session_id}", response_model=AuthCaptureStatusResponse)
async def get_auth_capture_status(session_id: str):
    """
    Get the current status of an auth capture session.
    """
    session = _active_auth_sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    return AuthCaptureStatusResponse(
        session_id=session_id,
        status=session.status,
        service=session.service,
    )


@router.delete("/auth-capture/{session_id}")
async def cancel_auth_capture(session_id: str):
    """
    Cancel and clean up an auth capture session.
    """
    session = _active_auth_sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    await session.close()
    _active_auth_sessions.pop(session_id, None)
    logger.info("Auth capture session %s cancelled", session_id)

    return {"session_id": session_id, "status": "cancelled"}


@router.post("/callback")
async def receive_callback(request: CallbackRequest):
    """
    Receive callback from Glassy or other systems.

    Handles async completion notifications and approval responses.
    """
    logger.info(
        "Received callback: task=%s type=%s",
        request.task_id,
        request.callback_type
    )

    # Handle different callback types
    if request.callback_type == "task_complete":
        # Mark task as complete
        pass
    elif request.callback_type == "approval_response":
        # Handle approval/rejection
        from api.routes.tasks import get_orchestrator
        orchestrator = get_orchestrator()

        if orchestrator and request.data:
            approved = request.data.get("approved", False)
            # Resume task with approval status
            pass

    return {"status": "received", "task_id": request.task_id}


# =============================================================================
# Background Task Runners
# =============================================================================

async def _run_browser_task(
    orchestrator,
    task_id: str,
    goal: str,
    start_url: str,
    require_approval: bool,
    credentials_key: Optional[str],
    context: Optional[Dict[str, Any]],
    callback_url: Optional[str]
):
    """Run browser task in background"""
    import httpx

    try:
        # First submit the task to create it in the store
        submitted_task_id = await orchestrator.submit_task(
            goal=goal,
            start_url=start_url,
            credentials_key=credentials_key,
            require_approval=require_approval,
            callback_url=callback_url
        )

        # Then execute the task
        result = await orchestrator.execute_task(submitted_task_id)

        # Send callback if configured
        if callback_url:
            async with httpx.AsyncClient() as client:
                await client.post(
                    callback_url,
                    json={
                        "task_id": task_id,
                        "status": result.status if hasattr(result, 'status') else "completed",
                        "result": result.to_dict() if hasattr(result, 'to_dict') else str(result)
                    }
                )

    except Exception as e:
        logger.error("Browser task %s failed: %s", task_id, e)

        if callback_url:
            async with httpx.AsyncClient() as client:
                await client.post(
                    callback_url,
                    json={
                        "task_id": task_id,
                        "status": "failed",
                        "error": str(e)
                    }
                )


async def _run_desktop_task(
    task_id: str,
    goal: str,
    app_name: Optional[str],
    require_approval: bool,
    context: Optional[Dict[str, Any]],
    callback_url: Optional[str]
):
    """Run desktop task in background"""
    import httpx
    from core.desktop_specialist import DesktopSpecialist

    try:
        specialist = DesktopSpecialist()

        # Open app if specified
        if app_name:
            await specialist.open_application(
                app_name=app_name,
                task_id=task_id
            )

        # TODO: Implement goal-based desktop task execution
        # This would use the desktop perceiver and specialist
        # to iteratively work toward the goal

        # Send callback if configured
        if callback_url:
            async with httpx.AsyncClient() as client:
                await client.post(
                    callback_url,
                    json={
                        "task_id": task_id,
                        "status": "completed",
                        "result": {"goal": goal}
                    }
                )

    except Exception as e:
        logger.error("Desktop task %s failed: %s", task_id, e)

        if callback_url:
            async with httpx.AsyncClient() as client:
                await client.post(
                    callback_url,
                    json={
                        "task_id": task_id,
                        "status": "failed",
                        "error": str(e)
                    }
                )


async def _apply_pii_blur(screenshot_path: str) -> str:
    """
    Apply PII detection and blur to screenshot.

    Uses existing security.pii_blur module.
    Returns path to blurred image.
    """
    try:
        from security.pii_blur import blur_pii_in_image

        blurred_path = screenshot_path.replace(".png", "_blurred.png")
        await blur_pii_in_image(screenshot_path, blurred_path)
        return blurred_path

    except Exception as e:
        logger.warning("PII blur failed, returning original: %s", e)
        return screenshot_path
