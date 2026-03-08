"""
Spectacles Orchestrator
Plans and coordinates browser automation tasks

The delegator component that:
- Plans task execution from natural language goals
- Manages state transitions
- Delegates actions to Browser Specialist
- Triggers HITL when needed
"""

import logging
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, field
from datetime import datetime

from .state_machine import StateMachine, StateCheckpoint, ExecutionPlan
from .browser_specialist import BrowserSpecialist, ActionResult
from .perception import VLMPerceiver
from browser.client import BrowserClient
from persistence.constants import AgentState, ActionStatus, ActionType, HITLRequestType
from persistence.task_store import TaskStore
from security.audit import AuditLogger, get_audit_logger
from security.secrets_vault import get_secrets_vault

logger = logging.getLogger(__name__)


@dataclass
class TaskContext:
    """Context for task execution"""
    task_id: str
    goal: str
    start_url: str
    credentials_key: Optional[str] = None
    require_approval: bool = True
    execution_plan: Optional[ExecutionPlan] = None
    current_perception: Optional[Dict[str, Any]] = None
    action_history: List[Dict[str, Any]] = field(default_factory=list)
    error_count: int = 0
    max_errors: int = 3
    pattern_id: Optional[str] = None  # Track pattern used for this task


class Orchestrator:
    """
    Task Orchestrator - plans and coordinates browser automation.

    Responsibilities:
    - Accept natural language goals
    - Create execution plans
    - Manage state machine transitions
    - Delegate actions to Browser Specialist
    - Request human intervention when needed
    - Handle errors and recovery

    Works with:
    - StateMachine for state management
    - BrowserSpecialist for action execution
    - TaskStore for persistence
    - HITL system for human intervention
    """

    def __init__(
        self,
        browser_client: BrowserClient,
        task_store: Optional[TaskStore] = None,
        vlm_perceiver: Optional[VLMPerceiver] = None,
        hitl_callback: Optional[Callable] = None,
        audit_logger: Optional[AuditLogger] = None
    ):
        """
        Initialize orchestrator.

        Args:
            browser_client: Browser client for automation
            task_store: Task persistence store
            vlm_perceiver: VLM perceiver for visual tasks
            hitl_callback: Callback for HITL requests
            audit_logger: Audit logger for compliance
        """
        self.browser_client = browser_client
        self.task_store = task_store or TaskStore()
        self.audit_logger = audit_logger or get_audit_logger()

        # Initialize components
        self.state_machine = StateMachine()
        self.browser_specialist = BrowserSpecialist(
            browser_client=browser_client,
            vlm_perceiver=vlm_perceiver,
            audit_logger=self.audit_logger
        )

        # HITL callback
        self.hitl_callback = hitl_callback

        # Active tasks
        self._active_tasks: Dict[str, TaskContext] = {}

        # Learning components (initialized via setters)
        self.reasoner = None
        self.pattern_extractor = None
        self.pattern_store = None

    async def submit_task(
        self,
        goal: str,
        start_url: str,
        credentials_key: Optional[str] = None,
        require_approval: bool = True,
        callback_url: Optional[str] = None
    ) -> str:
        """
        Submit a new browser automation task.

        Args:
            goal: Natural language description of what to accomplish
            start_url: URL to start automation
            credentials_key: GCP Secret Manager key for credentials
            require_approval: Whether to require HITL approval
            callback_url: URL to call when task completes

        Returns:
            Task ID
        """
        # Create task in store
        task_id = self.task_store.create_task(
            goal=goal,
            start_url=start_url,
            credentials_key=credentials_key,
            require_approval=require_approval,
            callback_url=callback_url
        )

        # Create context
        context = TaskContext(
            task_id=task_id,
            goal=goal,
            start_url=start_url,
            credentials_key=credentials_key,
            require_approval=require_approval
        )
        self._active_tasks[task_id] = context

        # Log task creation
        self.audit_logger.log_task_lifecycle(
            action="task_created",
            status="SUCCESS",
            task_id=task_id,
            metadata={"goal": goal, "start_url": start_url}
        )

        logger.info("Task submitted: %s", task_id)
        return task_id

    async def execute_task(self, task_id: str) -> Dict[str, Any]:
        """
        Execute a submitted task.

        This is the main execution loop that:
        1. Plans the task
        2. Navigates to start URL
        3. Observes page state
        4. Executes actions
        5. Evaluates progress
        6. Requests HITL when needed

        Args:
            task_id: Task to execute

        Returns:
            Execution result
        """
        context = self._active_tasks.get(task_id)
        if not context:
            # Try to load from store
            task = self.task_store.get_task(task_id)
            if not task:
                raise ValueError(f"Task not found: {task_id}")

            context = TaskContext(
                task_id=task_id,
                goal=task["goal"],
                start_url=task["start_url"],
                credentials_key=task.get("credentials_key"),
                require_approval=task.get("require_approval", True)
            )
            self._active_tasks[task_id] = context

        try:
            # Connect to browser
            logger.info("Connecting to browser for task %s", task_id)
            await self.browser_client.connect()

            # Apply storage state if credentials_key is provided
            # This enables pre-authenticated sessions for services like Google
            if context.credentials_key:
                await self._apply_storage_state(context.credentials_key)

            # Initialize state
            await self.state_machine.transition(
                task_id, AgentState.PLANNING,
                checkpoint_data={"goal": context.goal}
            )

            # Plan the task
            plan = await self._plan_task(context)
            context.execution_plan = plan

            # Navigate to start URL
            await self.state_machine.transition(task_id, AgentState.NAVIGATING)
            nav_result = await self.browser_specialist.navigate(
                context.start_url, task_id=task_id, wait_until="domcontentloaded"
            )

            if nav_result.status != ActionStatus.SUCCESS:
                await self._handle_error(context, nav_result.error or "Navigation failed")
                return {"status": "failed", "error": nav_result.error}

            # Main execution loop
            while True:
                current_state = await self.state_machine.get_current_state(task_id)

                if self.state_machine.is_terminal_state(current_state):
                    break

                # Observe page state
                await self.state_machine.transition(task_id, AgentState.OBSERVING)
                perception_method, perception = await self.browser_specialist.perceive_page(
                    context.goal,
                    context={"history": context.action_history[-5:]}
                )
                context.current_perception = perception

                # Evaluate if goal is achieved
                await self.state_machine.transition(task_id, AgentState.EVALUATING)
                goal_achieved = await self._evaluate_goal(context, perception)

                if goal_achieved:
                    await self.state_machine.transition(task_id, AgentState.COMPLETED)
                    self.task_store.update_task_state(task_id, AgentState.COMPLETED)
                    break

                # Determine next action
                next_action = await self._determine_next_action(context, perception)

                if next_action.get("requires_human"):
                    # Request HITL
                    await self._request_hitl(context, next_action)
                    return {
                        "status": "awaiting_human",
                        "task_id": task_id,
                        "reason": next_action.get("reason")
                    }

                # Execute action
                await self.state_machine.transition(task_id, AgentState.ACTING)
                result = await self._execute_action(context, next_action)

                if result.status == ActionStatus.FAILED:
                    context.error_count += 1
                    if context.error_count >= context.max_errors:
                        await self._handle_error(context, "Max errors exceeded")
                        return {"status": "failed", "error": "Max errors exceeded"}
                    # Try error recovery
                    await self.state_machine.transition(task_id, AgentState.ERROR_RECOVERY)
                    continue

                context.action_history.append(result.to_dict())

            # Task completed
            self.audit_logger.log_task_lifecycle(
                action="task_completed",
                status="SUCCESS",
                task_id=task_id
            )

            # PHASE 4: Pattern Learning Integration
            # Extract pattern from successful task execution
            await self._learn_from_task(task_id, context, success=True)

            return {
                "status": "completed",
                "task_id": task_id,
                "actions_taken": len(context.action_history)
            }

        except Exception as e:
            logger.error("Task execution failed: %s", e, exc_info=True)
            await self._handle_error(context, str(e))
            return {"status": "failed", "error": str(e)}

        finally:
            # Always disconnect browser
            try:
                await self.browser_client.disconnect()
            except Exception as e:
                logger.warning("Browser disconnect failed: %s", e)

    async def resume_task(
        self,
        task_id: str,
        approved: bool,
        human_input: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Resume task after HITL response.

        Args:
            task_id: Task to resume
            approved: Whether human approved
            human_input: Additional input from human

        Returns:
            Execution result
        """
        checkpoint = await self.state_machine.resume_after_human(
            task_id, approved, human_input
        )

        if not checkpoint:
            return {"status": "failed", "error": "No checkpoint found"}

        if not approved:
            self.task_store.update_task_state(
                task_id, AgentState.FAILED,
                error_message="Human rejected action"
            )
            return {"status": "failed", "error": "Human rejected"}

        # Continue execution
        return await self.execute_task(task_id)

    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a running task"""
        self.task_store.update_task_state(
            task_id, AgentState.FAILED,
            error_message="Task cancelled"
        )

        if task_id in self._active_tasks:
            del self._active_tasks[task_id]

        await self.state_machine.cleanup_task(task_id)

        self.audit_logger.log_task_lifecycle(
            action="task_cancelled",
            status="SUCCESS",
            task_id=task_id
        )

        return True

    async def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """Get current task status"""
        task = self.task_store.get_task(task_id)
        if not task:
            return {"error": "Task not found"}

        checkpoint = await self.state_machine.get_checkpoint(task_id)

        return {
            "task_id": task_id,
            "goal": task["goal"],
            "state": task["current_state"],
            "step": task.get("current_step", 0),
            "total_steps": task.get("total_steps", 0),
            "is_active": task.get("is_active", False),
            "created_at": task.get("created_at"),
            "updated_at": task.get("updated_at"),
            "error": task.get("error_message"),
            "checkpoint_id": checkpoint.checkpoint_id if checkpoint else None
        }

    async def _plan_task(self, context: TaskContext) -> ExecutionPlan:
        """Create execution plan for task"""
        # For now, simple plan - in future could use LLM for complex planning
        plan = ExecutionPlan(
            goal=context.goal,
            steps=[
                {"action": "navigate", "target": context.start_url},
                {"action": "observe", "target": "page"},
                {"action": "achieve_goal", "target": context.goal}
            ],
            requires_human_approval=context.require_approval,
            estimated_steps=5
        )

        self.task_store.update_task_step(
            context.task_id,
            current_step=0,
            total_steps=plan.estimated_steps
        )

        return plan

    async def _evaluate_goal(
        self,
        context: TaskContext,
        perception: Dict[str, Any]
    ) -> bool:
        """Evaluate if goal has been achieved"""
        # Simple heuristics - in future could use LLM
        goal_lower = context.goal.lower()

        # Screenshot goals - just need to navigate and capture
        if "screenshot" in goal_lower or "capture" in goal_lower:
            # Take the screenshot and we're done
            await self.browser_specialist.screenshot(
                full_page=True,
                task_id=context.task_id
            )
            return True

        # Navigate-only goals
        if goal_lower.startswith("navigate to") or goal_lower.startswith("go to"):
            # Already navigated, goal achieved
            return True

        # Check for common success patterns
        if "login" in goal_lower:
            # Check if we're past the login page
            url = perception.get("url", "")
            if "login" not in url.lower() and "signin" not in url.lower():
                # Might be logged in
                return True

        # If we've taken many actions without errors, assume progress
        if len(context.action_history) >= 10:
            success_count = sum(
                1 for a in context.action_history
                if a.get("status") == "SUCCESS"
            )
            if success_count >= 8:
                return True

        return False

    async def _determine_next_action(
        self,
        context: TaskContext,
        perception: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Determine next action based on perception"""

        # Check for blockers
        blockers = perception.get("blockers", [])
        if blockers:
            return {
                "requires_human": True,
                "reason": f"Blockers detected: {blockers}",
                "type": HITLRequestType.INTERVENTION
            }

        # Check confidence
        confidence = perception.get("confidence", 0.5)
        if confidence < 0.5 and context.require_approval:
            return {
                "requires_human": True,
                "reason": f"Low confidence: {confidence}",
                "type": HITLRequestType.LOW_CONFIDENCE
            }

        # Use suggested action from VLM if available
        suggested = perception.get("suggested_action")
        if suggested:
            return self._parse_suggested_action(suggested)

        # Analyze forms
        forms = perception.get("forms", [])
        if forms:
            form = forms[0]
            fields = form.get("fields", [])
            unfilled = [f for f in fields if not f.get("value")]
            if unfilled:
                return {
                    "action": "fill",
                    "target": unfilled[0].get("selector") or unfilled[0].get("name"),
                    "field_info": unfilled[0]
                }

        # Look for submit buttons
        buttons = perception.get("interactive_elements", [])
        submit_buttons = [
            b for b in buttons
            if b.get("type") == "button" and
            any(word in b.get("text", "").lower() for word in ["submit", "login", "sign in", "continue", "next"])
        ]
        if submit_buttons:
            return {
                "action": "click",
                "target": submit_buttons[0].get("text") or submit_buttons[0].get("selector")
            }

        # Default: need human input
        return {
            "requires_human": True,
            "reason": "Cannot determine next action",
            "type": HITLRequestType.INTERVENTION
        }

    def _parse_suggested_action(self, suggested: str) -> Dict[str, Any]:
        """Parse VLM suggested action into executable action"""
        suggested_lower = suggested.lower()

        if "click" in suggested_lower:
            return {"action": "click", "target": suggested}
        elif "fill" in suggested_lower or "enter" in suggested_lower:
            return {"action": "fill", "target": suggested, "requires_value": True}
        elif "select" in suggested_lower:
            return {"action": "select", "target": suggested}
        elif "wait" in suggested_lower:
            return {"action": "wait", "duration": 2000}
        else:
            return {"action": "unknown", "suggestion": suggested, "requires_human": True}

    async def _execute_action(
        self,
        context: TaskContext,
        action: Dict[str, Any]
    ) -> ActionResult:
        """Execute a single action"""
        action_type = action.get("action", "unknown")
        target = action.get("target", "")

        # Basic actions
        if action_type == "click":
            return await self.browser_specialist.click(target, task_id=context.task_id)
        elif action_type == "fill":
            value = action.get("value", "")
            return await self.browser_specialist.fill(target, value, task_id=context.task_id)
        elif action_type == "select":
            return await self.browser_specialist.select(
                target,
                value=action.get("value"),
                label=action.get("label"),
                task_id=context.task_id
            )
        elif action_type == "navigate":
            return await self.browser_specialist.navigate(target, task_id=context.task_id)

        # New Phase 1 actions
        elif action_type == "keyboard":
            return await self.browser_specialist.keyboard(
                key=action.get("key", target),
                modifiers=action.get("modifiers"),
                task_id=context.task_id
            )
        elif action_type == "hover":
            return await self.browser_specialist.hover(target, task_id=context.task_id)
        elif action_type == "scroll":
            return await self.browser_specialist.scroll(
                direction=action.get("direction", "down"),
                amount=action.get("amount", 500),
                target=action.get("element"),
                task_id=context.task_id
            )
        elif action_type == "drag_drop":
            return await self.browser_specialist.drag_drop(
                source=action.get("source", target),
                target=action.get("destination", ""),
                task_id=context.task_id
            )
        elif action_type == "double_click":
            return await self.browser_specialist.double_click(target, task_id=context.task_id)
        elif action_type == "right_click":
            return await self.browser_specialist.right_click(target, task_id=context.task_id)
        elif action_type == "upload":
            return await self.browser_specialist.upload_file(
                input_selector=target,
                file_path=action.get("file_path", ""),
                task_id=context.task_id
            )
        elif action_type == "download":
            return await self.browser_specialist.download_file(
                trigger_selector=target,
                download_path=action.get("download_path"),
                task_id=context.task_id
            )
        elif action_type == "wait_for":
            return await self.browser_specialist.wait_for(
                condition=action.get("condition", "element"),
                target=target,
                timeout_ms=action.get("timeout_ms", 10000),
                task_id=context.task_id
            )

        # Legacy wait action
        elif action_type == "wait":
            import asyncio
            await asyncio.sleep(action.get("duration", 1000) / 1000)
            return ActionResult(
                action_type=ActionType.WAIT,
                status=ActionStatus.SUCCESS,
                duration_ms=action.get("duration", 1000)
            )

        # Screenshot and extract
        elif action_type == "screenshot":
            return await self.browser_specialist.screenshot(
                path=action.get("path"),
                full_page=action.get("full_page", False),
                task_id=context.task_id
            )
        elif action_type == "extract":
            return await self.browser_specialist.extract_text(
                selector=target if target else None,
                task_id=context.task_id
            )

        else:
            return ActionResult(
                action_type=ActionType.EXTRACT,
                status=ActionStatus.FAILED,
                error=f"Unknown action type: {action_type}"
            )

    async def _request_hitl(
        self,
        context: TaskContext,
        action: Dict[str, Any]
    ):
        """Request human-in-the-loop intervention"""
        # Take screenshot
        screenshot = await self.browser_specialist.screenshot(task_id=context.task_id)

        # Create checkpoint
        await self.state_machine.pause_for_human(
            task_id=context.task_id,
            approval_request={
                "reason": action.get("reason"),
                "type": action.get("type", HITLRequestType.INTERVENTION).value,
                "suggested_action": action.get("suggestion"),
                "perception": context.current_perception
            },
            browser_state=await self.browser_specialist.get_page_info(),
            perception_context=context.current_perception
        )

        self.task_store.update_task_state(context.task_id, AgentState.AWAITING_HUMAN)

        # Trigger callback if set
        if self.hitl_callback:
            await self.hitl_callback(
                task_id=context.task_id,
                request_type=action.get("type", HITLRequestType.INTERVENTION),
                reason=action.get("reason"),
                screenshot_data=screenshot.data if hasattr(screenshot, 'data') else None
            )

        self.audit_logger.log_hitl(
            action="hitl_requested",
            status="SUCCESS",
            task_id=context.task_id,
            metadata={"reason": action.get("reason")}
        )

    async def _handle_error(self, context: TaskContext, error: str):
        """Handle task error"""
        logger.error("Task %s error: %s", context.task_id, error)

        self.task_store.update_task_state(
            context.task_id,
            AgentState.FAILED,
            error_message=error
        )

        await self.state_machine.transition(
            context.task_id,
            AgentState.FAILED,
            checkpoint_data={"error": error}
        )

        self.audit_logger.log_task_lifecycle(
            action="task_failed",
            status="FAILURE",
            task_id=context.task_id,
            metadata={"error": error}
        )

    def set_reasoner(self, reasoner):
        """
        Set the AI Reasoner for strategic planning.

        Args:
            reasoner: AIReasoner instance
        """
        self.reasoner = reasoner
        logger.info("AI Reasoner configured for orchestrator")

    def set_pattern_components(self, pattern_extractor=None, pattern_store=None):
        """
        Set the pattern learning components.

        Args:
            pattern_extractor: PatternExtractor instance
            pattern_store: PatternStore instance
        """
        if pattern_extractor:
            self.pattern_extractor = pattern_extractor
            logger.info("PatternExtractor configured for orchestrator")

        if pattern_store:
            self.pattern_store = pattern_store
            logger.info("PatternStore configured for orchestrator")

    async def _learn_from_task(self, task_id: str, context: TaskContext, success: bool):
        """
        Learn from completed task execution.

        This method implements the learning integration from Phase 4:
        1. If task used an existing pattern, update its confidence
        2. If task succeeded, extract new pattern for future reuse

        Args:
            task_id: Task ID
            context: Task execution context
            success: Whether the task succeeded
        """
        # 1. Update confidence for existing pattern if used
        if context.pattern_id and self.pattern_store:
            try:
                await self.pattern_store.update_confidence(
                    pattern_id=context.pattern_id,
                    success=success
                )
                logger.info(
                    "Updated pattern %s confidence (success=%s)",
                    context.pattern_id,
                    success
                )
            except Exception as e:
                logger.error("Failed to update pattern confidence: %s", e)
                # Don't fail task if learning fails

        # 2. Extract new pattern from successful task
        if success and self.pattern_extractor:
            try:
                # Get task data and actions from store
                task_data = self.task_store.get_task(task_id)
                actions = self.task_store.get_task_actions(task_id)

                # Extract pattern
                pattern = await self.pattern_extractor.extract_from_task(
                    task_id=task_id,
                    task_data=task_data,
                    actions=actions
                )

                if pattern and self.pattern_store:
                    # Store pattern in memory
                    await self.pattern_store.store_pattern(pattern)
                    logger.info(
                        "Learned new %s pattern for %s (pattern_id=%s)",
                        pattern.pattern_type,
                        pattern.site_domain,
                        pattern.id
                    )
                elif pattern:
                    logger.debug("Pattern extracted but no pattern store configured")
                else:
                    logger.debug("No pattern extracted from task %s", task_id)

            except Exception as e:
                logger.error("Pattern extraction failed: %s", e)
                # Don't fail task if learning fails

    async def _apply_storage_state(self, credentials_key: str) -> bool:
        """
        Apply browser storage state for pre-authenticated sessions.

        This enables automation of services like Google that block automated
        password-based logins. The storage state (cookies, localStorage) is
        retrieved from GCP Secret Manager and applied to the browser context.

        Args:
            credentials_key: Base secret name (will look for {key}-storage-state)

        Returns:
            True if storage state was applied successfully
        """
        vault = get_secrets_vault()
        if not vault:
            logger.warning("SecretsVault not available - cannot apply storage state")
            return False

        try:
            # Try to apply storage state first (preferred for services like Google)
            storage_applied = await vault.apply_storage_state(
                self.browser_client.context,
                credentials_key
            )

            if storage_applied:
                logger.info("Applied storage state for %s", credentials_key)
                return True

            # Fall back to username/password if no storage state
            logger.debug(
                "No storage state for %s, credentials may use username/password",
                credentials_key
            )
            return False

        except Exception as e:
            logger.error("Failed to apply storage state for %s: %s", credentials_key, e)
            return False
