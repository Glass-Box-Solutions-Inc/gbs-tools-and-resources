"""
Spectacles State Machine
Manages agent state transitions with LangGraph-style checkpointing

Enables:
- Pause execution at any state
- Human can respond hours later
- Resume from exact state
- State versioning for debugging
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

from persistence.constants import (
    AgentState,
    VALID_STATE_TRANSITIONS,
    is_valid_transition
)
from memory.checkpoint_store import CheckpointStore

logger = logging.getLogger(__name__)


@dataclass
class StateCheckpoint:
    """
    LangGraph-style checkpoint for async human response.

    Captures complete execution state for resumption.
    """
    task_id: str
    checkpoint_id: str
    state: AgentState
    step_index: int
    browser_state: Dict[str, Any] = field(default_factory=dict)  # URL, cookies, session
    action_history: List[Dict[str, Any]] = field(default_factory=list)
    perception_context: Dict[str, Any] = field(default_factory=dict)  # DOM/VLM results
    pending_approval: Optional[Dict[str, Any]] = None
    created_at: datetime = field(default_factory=datetime.now)
    thread_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage"""
        return {
            "task_id": self.task_id,
            "checkpoint_id": self.checkpoint_id,
            "state": self.state.value,
            "step_index": self.step_index,
            "browser_state": self.browser_state,
            "action_history": self.action_history,
            "perception_context": self.perception_context,
            "pending_approval": self.pending_approval,
            "created_at": self.created_at.isoformat(),
            "thread_id": self.thread_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StateCheckpoint":
        """Create from dictionary"""
        return cls(
            task_id=data["task_id"],
            checkpoint_id=data["checkpoint_id"],
            state=AgentState(data["state"]),
            step_index=data.get("step_index", 0),
            browser_state=data.get("browser_state", {}),
            action_history=data.get("action_history", []),
            perception_context=data.get("perception_context", {}),
            pending_approval=data.get("pending_approval"),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),
            thread_id=data.get("thread_id"),
        )


@dataclass
class ExecutionPlan:
    """Plan created by orchestrator"""
    goal: str
    steps: List[Dict[str, Any]] = field(default_factory=list)
    current_step: int = 0
    max_retries: int = 3
    requires_human_approval: bool = True
    estimated_steps: int = 0


class StateMachine:
    """
    Manages agent state transitions with checkpointing.

    Implements LangGraph-inspired patterns:
    - Checkpoints at each state for resumability
    - Interrupt points for human-in-the-loop
    - State graph with conditional edges
    - Async human response handling

    States:
    - PLANNING: Analyzing task, creating execution plan
    - NAVIGATING: Navigating to target URL
    - OBSERVING: Perceiving page state (DOM/VLM)
    - ACTING: Executing browser action
    - EVALUATING: Checking if goal achieved
    - AWAITING_HUMAN: Paused for HITL response
    - ERROR_RECOVERY: Handling errors/retries
    - COMPLETED: Task finished successfully
    - FAILED: Unrecoverable failure
    """

    def __init__(self, checkpoint_store: Optional[CheckpointStore] = None):
        """
        Initialize state machine.

        Args:
            checkpoint_store: Store for saving/loading checkpoints
        """
        self.checkpoint_store = checkpoint_store or CheckpointStore()
        self._current_checkpoints: Dict[str, StateCheckpoint] = {}

    async def transition(
        self,
        task_id: str,
        to_state: AgentState,
        checkpoint_data: Optional[Dict[str, Any]] = None,
        save_checkpoint: bool = True
    ) -> Optional[StateCheckpoint]:
        """
        Transition to new state with optional checkpoint.

        Args:
            task_id: Task identifier
            to_state: Target state
            checkpoint_data: Data to include in checkpoint
            save_checkpoint: Whether to persist checkpoint

        Returns:
            StateCheckpoint if created, None otherwise
        """
        # Get current checkpoint
        current = self._current_checkpoints.get(task_id)
        current_state = current.state if current else AgentState.PLANNING

        # Validate transition
        if not is_valid_transition(current_state, to_state):
            logger.error(
                "Invalid state transition: %s -> %s for task %s",
                current_state, to_state, task_id
            )
            return None

        # Create new checkpoint
        from persistence.utils import generate_checkpoint_id
        checkpoint = StateCheckpoint(
            task_id=task_id,
            checkpoint_id=generate_checkpoint_id(task_id),
            state=to_state,
            step_index=(current.step_index + 1) if current else 0,
            browser_state=checkpoint_data.get("browser_state", {}) if checkpoint_data else {},
            action_history=checkpoint_data.get("action_history", []) if checkpoint_data else [],
            perception_context=checkpoint_data.get("perception_context", {}) if checkpoint_data else {},
            pending_approval=checkpoint_data.get("pending_approval") if checkpoint_data else None,
            thread_id=checkpoint_data.get("thread_id") if checkpoint_data else None,
        )

        # Merge with previous checkpoint data
        if current:
            if not checkpoint.browser_state:
                checkpoint.browser_state = current.browser_state
            if not checkpoint.action_history:
                checkpoint.action_history = current.action_history
            checkpoint.thread_id = checkpoint.thread_id or current.thread_id

        # Save to memory
        self._current_checkpoints[task_id] = checkpoint

        # Persist if requested
        if save_checkpoint:
            await self.checkpoint_store.save_checkpoint(
                task_id=task_id,
                thread_id=checkpoint.thread_id,
                checkpoint_data=checkpoint.to_dict()
            )

        logger.info(
            "State transition: %s -> %s (task=%s, checkpoint=%s)",
            current_state, to_state, task_id, checkpoint.checkpoint_id
        )

        return checkpoint

    async def get_current_state(self, task_id: str) -> Optional[AgentState]:
        """Get current state for task"""
        checkpoint = self._current_checkpoints.get(task_id)
        if checkpoint:
            return checkpoint.state

        # Try loading from store
        loaded = await self.checkpoint_store.load_checkpoint(task_id)
        if loaded:
            checkpoint = StateCheckpoint.from_dict(loaded)
            self._current_checkpoints[task_id] = checkpoint
            return checkpoint.state

        return None

    async def get_checkpoint(self, task_id: str) -> Optional[StateCheckpoint]:
        """Get current checkpoint for task"""
        if task_id in self._current_checkpoints:
            return self._current_checkpoints[task_id]

        # Try loading from store
        loaded = await self.checkpoint_store.load_checkpoint(task_id)
        if loaded:
            checkpoint = StateCheckpoint.from_dict(loaded)
            self._current_checkpoints[task_id] = checkpoint
            return checkpoint

        return None

    async def resume_from_checkpoint(
        self,
        task_id: str,
        checkpoint_id: Optional[str] = None
    ) -> Optional[StateCheckpoint]:
        """
        Resume execution from saved checkpoint.

        Args:
            task_id: Task identifier
            checkpoint_id: Specific checkpoint ID (latest if None)

        Returns:
            Loaded checkpoint or None
        """
        loaded = await self.checkpoint_store.load_checkpoint(task_id, checkpoint_id)
        if not loaded:
            logger.warning("No checkpoint found for task %s", task_id)
            return None

        checkpoint = StateCheckpoint.from_dict(loaded)
        self._current_checkpoints[task_id] = checkpoint

        logger.info(
            "Resumed from checkpoint: %s (state=%s, step=%d)",
            checkpoint.checkpoint_id, checkpoint.state, checkpoint.step_index
        )

        return checkpoint

    async def pause_for_human(
        self,
        task_id: str,
        approval_request: Dict[str, Any],
        browser_state: Optional[Dict[str, Any]] = None,
        perception_context: Optional[Dict[str, Any]] = None
    ) -> StateCheckpoint:
        """
        Pause execution for human intervention.

        Creates checkpoint and transitions to AWAITING_HUMAN state.

        Args:
            task_id: Task identifier
            approval_request: Details of what needs approval
            browser_state: Current browser state to preserve
            perception_context: Current perception context

        Returns:
            Checkpoint for resumption
        """
        checkpoint = await self.transition(
            task_id=task_id,
            to_state=AgentState.AWAITING_HUMAN,
            checkpoint_data={
                "browser_state": browser_state or {},
                "perception_context": perception_context or {},
                "pending_approval": approval_request,
            },
            save_checkpoint=True
        )

        logger.info(
            "Paused for human: task=%s, reason=%s",
            task_id, approval_request.get("reason", "unknown")
        )

        return checkpoint

    async def resume_after_human(
        self,
        task_id: str,
        approved: bool,
        human_input: Optional[Dict[str, Any]] = None
    ) -> Optional[StateCheckpoint]:
        """
        Resume execution after human response.

        Args:
            task_id: Task identifier
            approved: Whether human approved the action
            human_input: Additional input from human

        Returns:
            New checkpoint after transition
        """
        current = await self.get_checkpoint(task_id)
        if not current:
            logger.error("No checkpoint to resume for task %s", task_id)
            return None

        if current.state != AgentState.AWAITING_HUMAN:
            logger.warning(
                "Task %s not in AWAITING_HUMAN state (current: %s)",
                task_id, current.state
            )

        # Determine next state based on approval
        if approved:
            next_state = AgentState.OBSERVING  # Re-observe and continue
        else:
            next_state = AgentState.FAILED  # Human rejected

        # Add human input to context
        perception_context = current.perception_context.copy()
        perception_context["human_response"] = {
            "approved": approved,
            "input": human_input,
            "timestamp": datetime.now().isoformat()
        }

        return await self.transition(
            task_id=task_id,
            to_state=next_state,
            checkpoint_data={
                "browser_state": current.browser_state,
                "action_history": current.action_history,
                "perception_context": perception_context,
            },
            save_checkpoint=True
        )

    def get_valid_transitions(self, state: AgentState) -> List[AgentState]:
        """Get valid next states from current state"""
        return VALID_STATE_TRANSITIONS.get(state, [])

    def is_terminal_state(self, state: AgentState) -> bool:
        """Check if state is terminal"""
        return state in [AgentState.COMPLETED, AgentState.FAILED]

    async def cleanup_task(self, task_id: str):
        """Clean up task state from memory"""
        if task_id in self._current_checkpoints:
            del self._current_checkpoints[task_id]
        logger.info("Cleaned up state for task %s", task_id)
