"""
Spectacles Webhook Routes
Slack webhook handlers for interactive components
"""

import logging
import hmac
import hashlib
import time
from typing import Optional
from fastapi import APIRouter, Request, HTTPException, Header

from api.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


def verify_slack_signature(
    body: bytes,
    timestamp: str,
    signature: str,
    signing_secret: str
) -> bool:
    """Verify Slack request signature"""
    if abs(time.time() - int(timestamp)) > 60 * 5:
        return False

    sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
    my_signature = 'v0=' + hmac.new(
        signing_secret.encode(),
        sig_basestring.encode(),
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(my_signature, signature)


@router.post("/slack/events")
async def slack_events(
    request: Request,
    x_slack_signature: Optional[str] = Header(None),
    x_slack_request_timestamp: Optional[str] = Header(None)
):
    """
    Handle Slack events (fallback for Socket Mode).

    This endpoint is used when Socket Mode is not available.
    """
    body = await request.body()

    # Verify signature if signing secret is configured
    if settings.SLACK_SIGNING_SECRET:
        if not x_slack_signature or not x_slack_request_timestamp:
            raise HTTPException(status_code=401, detail="Missing Slack signature")

        if not verify_slack_signature(
            body,
            x_slack_request_timestamp,
            x_slack_signature,
            settings.SLACK_SIGNING_SECRET
        ):
            raise HTTPException(status_code=401, detail="Invalid signature")

    data = await request.json()

    # Handle URL verification challenge
    if data.get("type") == "url_verification":
        return {"challenge": data.get("challenge")}

    # Log event for debugging
    event_type = data.get("event", {}).get("type", "unknown")
    logger.info("Received Slack event: %s", event_type)

    return {"ok": True}


@router.post("/slack/interactions")
async def slack_interactions(
    request: Request,
    x_slack_signature: Optional[str] = Header(None),
    x_slack_request_timestamp: Optional[str] = Header(None)
):
    """
    Handle Slack interactive components (buttons, modals).

    This endpoint processes button clicks from approval messages.
    """
    body = await request.body()

    # Verify signature
    if settings.SLACK_SIGNING_SECRET:
        if not x_slack_signature or not x_slack_request_timestamp:
            raise HTTPException(status_code=401, detail="Missing Slack signature")

        if not verify_slack_signature(
            body,
            x_slack_request_timestamp,
            x_slack_signature,
            settings.SLACK_SIGNING_SECRET
        ):
            raise HTTPException(status_code=401, detail="Invalid signature")

    # Parse form data (Slack sends as form-urlencoded)
    from urllib.parse import parse_qs
    import json

    form_data = parse_qs(body.decode('utf-8'))
    payload_str = form_data.get('payload', [''])[0]

    if not payload_str:
        raise HTTPException(status_code=400, detail="Missing payload")

    try:
        payload = json.loads(payload_str)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid payload")

    # Get action details
    action_type = payload.get("type")
    actions = payload.get("actions", [])

    if not actions:
        return {"ok": True}

    action = actions[0]
    action_id = action.get("action_id")
    task_id = action.get("value")
    user_id = payload.get("user", {}).get("id")

    logger.info(
        "Slack interaction: action=%s, task=%s, user=%s",
        action_id, task_id, user_id
    )

    # Handle different actions
    if action_id == "approve_action":
        # Process approval
        from api.routes.tasks import get_orchestrator
        orchestrator = get_orchestrator()
        await orchestrator.resume_task(task_id, approved=True)

    elif action_id == "reject_action":
        # Process rejection
        from api.routes.tasks import get_orchestrator
        orchestrator = get_orchestrator()
        await orchestrator.resume_task(task_id, approved=False)

    elif action_id == "take_control":
        # Handle tunnel mode request
        logger.info("Tunnel mode requested for task %s", task_id)
        # Tunnel mode handling would go here

    return {"ok": True}


@router.post("/task-complete")
async def task_complete_webhook(request: Request):
    """
    Webhook endpoint for task completion callbacks.

    External systems can register this URL as a callback.
    """
    data = await request.json()

    task_id = data.get("task_id")
    status = data.get("status")

    logger.info("Task complete webhook: task=%s, status=%s", task_id, status)

    return {"received": True, "task_id": task_id}


# =============================================================================
# Glassy Integration Webhooks
# =============================================================================

@router.post("/glassy/callback")
async def glassy_callback(request: Request):
    """
    Webhook endpoint for Glassy AI agent callbacks.

    Receives notifications from Glassy about:
    - Task completion confirmations
    - Approval responses from human operators
    - Status update requests
    - Error handling requests
    """
    data = await request.json()

    callback_type = data.get("callback_type")
    task_id = data.get("task_id")
    payload = data.get("payload", {})

    logger.info(
        "Glassy callback received: type=%s, task=%s",
        callback_type, task_id
    )

    # Handle different callback types
    if callback_type == "approval_response":
        # Glassy relaying human approval decision
        approved = payload.get("approved", False)
        human_input = payload.get("human_input")

        from api.routes.tasks import get_orchestrator
        orchestrator = get_orchestrator()

        if orchestrator:
            await orchestrator.resume_task(
                task_id,
                approved=approved,
                human_input=human_input
            )

        return {
            "status": "processed",
            "task_id": task_id,
            "action": "resumed" if approved else "rejected"
        }

    elif callback_type == "status_request":
        # Glassy requesting task status update
        from api.routes.tasks import get_orchestrator
        orchestrator = get_orchestrator()

        if orchestrator:
            status = await orchestrator.get_task_status(task_id)
            return {
                "status": "success",
                "task_id": task_id,
                "task_status": status
            }

        return {"status": "error", "error": "Orchestrator not available"}

    elif callback_type == "cancel_request":
        # Glassy requesting task cancellation
        from api.routes.tasks import get_orchestrator
        orchestrator = get_orchestrator()

        if orchestrator:
            await orchestrator.cancel_task(task_id)
            return {"status": "cancelled", "task_id": task_id}

        return {"status": "error", "error": "Orchestrator not available"}

    elif callback_type == "error_report":
        # Glassy reporting an error for human review
        error_details = payload.get("error")
        context = payload.get("context", {})

        logger.error(
            "Glassy reported error for task %s: %s",
            task_id, error_details
        )

        # Could trigger Slack notification here
        return {"status": "acknowledged", "task_id": task_id}

    else:
        logger.warning("Unknown Glassy callback type: %s", callback_type)
        return {"status": "unknown_callback", "callback_type": callback_type}


@router.post("/glassy/skill-result")
async def glassy_skill_result(request: Request):
    """
    Receive skill execution results from Glassy.

    When Glassy uses Spectacles as a skill, this endpoint
    receives the results for logging and audit purposes.
    """
    data = await request.json()

    skill_id = data.get("skill_id")
    task_id = data.get("task_id")
    result = data.get("result", {})
    duration_ms = data.get("duration_ms", 0)

    logger.info(
        "Glassy skill result: skill=%s, task=%s, duration=%dms",
        skill_id, task_id, duration_ms
    )

    # Log to audit trail
    from security.audit import get_audit_logger

    audit = get_audit_logger()
    audit.log_browser_action(
        action="glassy_skill_complete",
        status=result.get("status", "unknown"),
        task_id=task_id,
        resource=skill_id,
        additional_data={
            "duration_ms": duration_ms,
            "result_summary": str(result)[:500]
        }
    )

    return {"status": "logged", "skill_id": skill_id, "task_id": task_id}
