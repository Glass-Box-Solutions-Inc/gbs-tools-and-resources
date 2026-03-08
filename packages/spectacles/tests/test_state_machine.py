"""
Tests for Spectacles State Machine
"""

import pytest
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime


class TestAgentState:
    """Test AgentState enum"""

    def test_all_states_defined(self):
        """Test all required states are defined"""
        from persistence.constants import AgentState

        required_states = [
            "PLANNING", "NAVIGATING", "OBSERVING", "ACTING",
            "EVALUATING", "AWAITING_HUMAN", "ERROR_RECOVERY",
            "COMPLETED", "FAILED"
        ]

        for state_name in required_states:
            assert hasattr(AgentState, state_name)
            assert AgentState[state_name].value == state_name

    def test_state_string_representation(self):
        """Test states have correct string values"""
        from persistence.constants import AgentState

        assert AgentState.PLANNING.value == "PLANNING"
        assert str(AgentState.COMPLETED) == "AgentState.COMPLETED"


class TestStateTransitions:
    """Test state transition validation"""

    def test_valid_transitions_from_planning(self):
        """Test valid transitions from PLANNING state"""
        from persistence.constants import AgentState, is_valid_transition

        assert is_valid_transition(AgentState.PLANNING, AgentState.NAVIGATING)
        assert is_valid_transition(AgentState.PLANNING, AgentState.FAILED)
        assert not is_valid_transition(AgentState.PLANNING, AgentState.COMPLETED)

    def test_valid_transitions_from_observing(self):
        """Test valid transitions from OBSERVING state"""
        from persistence.constants import AgentState, is_valid_transition

        assert is_valid_transition(AgentState.OBSERVING, AgentState.ACTING)
        assert is_valid_transition(AgentState.OBSERVING, AgentState.EVALUATING)
        assert is_valid_transition(AgentState.OBSERVING, AgentState.AWAITING_HUMAN)
        assert is_valid_transition(AgentState.OBSERVING, AgentState.ERROR_RECOVERY)

    def test_valid_transitions_from_awaiting_human(self):
        """Test valid transitions from AWAITING_HUMAN state"""
        from persistence.constants import AgentState, is_valid_transition

        assert is_valid_transition(AgentState.AWAITING_HUMAN, AgentState.ACTING)
        assert is_valid_transition(AgentState.AWAITING_HUMAN, AgentState.FAILED)
        assert is_valid_transition(AgentState.AWAITING_HUMAN, AgentState.OBSERVING)

    def test_terminal_states_have_no_transitions(self):
        """Test COMPLETED and FAILED are terminal states"""
        from persistence.constants import AgentState, VALID_STATE_TRANSITIONS

        assert VALID_STATE_TRANSITIONS[AgentState.COMPLETED] == []
        assert VALID_STATE_TRANSITIONS[AgentState.FAILED] == []


class TestStateCheckpoint:
    """Test StateCheckpoint data class"""

    def test_checkpoint_creation(self):
        """Test creating a checkpoint"""
        from core.state_machine import StateCheckpoint
        from persistence.constants import AgentState

        checkpoint = StateCheckpoint(
            task_id="task_123",
            checkpoint_id="cp_001",
            state=AgentState.OBSERVING,
            step_index=2,
            browser_state={"url": "https://example.com"},
            action_history=[{"type": "CLICK"}],
        )

        assert checkpoint.task_id == "task_123"
        assert checkpoint.state == AgentState.OBSERVING
        assert checkpoint.step_index == 2

    def test_checkpoint_to_dict(self):
        """Test checkpoint serialization"""
        from core.state_machine import StateCheckpoint
        from persistence.constants import AgentState

        checkpoint = StateCheckpoint(
            task_id="task_123",
            checkpoint_id="cp_001",
            state=AgentState.PLANNING,
            step_index=0
        )

        data = checkpoint.to_dict()

        assert data["task_id"] == "task_123"
        assert data["checkpoint_id"] == "cp_001"
        assert data["state"] == "PLANNING"
        assert data["step_index"] == 0
        assert "created_at" in data

    def test_checkpoint_from_dict(self):
        """Test checkpoint deserialization"""
        from core.state_machine import StateCheckpoint
        from persistence.constants import AgentState

        data = {
            "task_id": "task_456",
            "checkpoint_id": "cp_002",
            "state": "ACTING",
            "step_index": 3,
            "browser_state": {"url": "https://test.com"},
            "action_history": [],
            "perception_context": {},
            "pending_approval": None,
            "created_at": "2025-01-01T12:00:00",
            "thread_id": "thread_123"
        }

        checkpoint = StateCheckpoint.from_dict(data)

        assert checkpoint.task_id == "task_456"
        assert checkpoint.state == AgentState.ACTING
        assert checkpoint.thread_id == "thread_123"


class TestStateMachine:
    """Test StateMachine class"""

    @pytest.mark.asyncio
    async def test_initial_transition(self, state_machine):
        """Test initial state transition"""
        from persistence.constants import AgentState

        checkpoint = await state_machine.transition(
            task_id="task_001",
            to_state=AgentState.NAVIGATING
        )

        assert checkpoint is not None
        assert checkpoint.state == AgentState.NAVIGATING
        assert checkpoint.task_id == "task_001"

    @pytest.mark.asyncio
    async def test_valid_transition_sequence(self, state_machine):
        """Test valid sequence of state transitions"""
        from persistence.constants import AgentState

        # Start with PLANNING -> NAVIGATING
        await state_machine.transition("task_002", AgentState.NAVIGATING)

        # NAVIGATING -> OBSERVING
        checkpoint = await state_machine.transition("task_002", AgentState.OBSERVING)
        assert checkpoint.state == AgentState.OBSERVING

        # OBSERVING -> ACTING
        checkpoint = await state_machine.transition("task_002", AgentState.ACTING)
        assert checkpoint.state == AgentState.ACTING

    @pytest.mark.asyncio
    async def test_invalid_transition_returns_none(self, state_machine):
        """Test invalid transition returns None"""
        from persistence.constants import AgentState

        # Start with PLANNING -> NAVIGATING
        await state_machine.transition("task_003", AgentState.NAVIGATING)

        # Try invalid: NAVIGATING -> COMPLETED (should fail)
        result = await state_machine.transition("task_003", AgentState.COMPLETED)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_current_state(self, state_machine):
        """Test getting current state"""
        from persistence.constants import AgentState

        await state_machine.transition("task_004", AgentState.NAVIGATING)
        state = await state_machine.get_current_state("task_004")

        assert state == AgentState.NAVIGATING

    @pytest.mark.asyncio
    async def test_pause_for_human(self, state_machine):
        """Test pausing for human intervention"""
        from persistence.constants import AgentState

        # Get to OBSERVING state first
        await state_machine.transition("task_005", AgentState.NAVIGATING)
        await state_machine.transition("task_005", AgentState.OBSERVING)

        # Pause for human
        checkpoint = await state_machine.pause_for_human(
            task_id="task_005",
            approval_request={"reason": "Confirm button click"},
            browser_state={"url": "https://example.com"}
        )

        assert checkpoint.state == AgentState.AWAITING_HUMAN
        assert checkpoint.pending_approval["reason"] == "Confirm button click"

    @pytest.mark.asyncio
    async def test_resume_after_human_approved(self, state_machine):
        """Test resuming after human approval"""
        from persistence.constants import AgentState

        # Setup: get to AWAITING_HUMAN
        await state_machine.transition("task_006", AgentState.NAVIGATING)
        await state_machine.transition("task_006", AgentState.OBSERVING)
        await state_machine.pause_for_human(
            task_id="task_006",
            approval_request={"reason": "test"}
        )

        # Resume with approval
        checkpoint = await state_machine.resume_after_human(
            task_id="task_006",
            approved=True,
            human_input={"notes": "Approved"}
        )

        assert checkpoint.state == AgentState.OBSERVING

    @pytest.mark.asyncio
    async def test_resume_after_human_rejected(self, state_machine):
        """Test resuming after human rejection"""
        from persistence.constants import AgentState

        # Setup: get to AWAITING_HUMAN
        await state_machine.transition("task_007", AgentState.NAVIGATING)
        await state_machine.transition("task_007", AgentState.OBSERVING)
        await state_machine.pause_for_human(
            task_id="task_007",
            approval_request={"reason": "test"}
        )

        # Resume with rejection
        checkpoint = await state_machine.resume_after_human(
            task_id="task_007",
            approved=False
        )

        assert checkpoint.state == AgentState.FAILED

    def test_is_terminal_state(self, state_machine):
        """Test terminal state detection"""
        from persistence.constants import AgentState

        assert state_machine.is_terminal_state(AgentState.COMPLETED)
        assert state_machine.is_terminal_state(AgentState.FAILED)
        assert not state_machine.is_terminal_state(AgentState.PLANNING)
        assert not state_machine.is_terminal_state(AgentState.OBSERVING)

    def test_get_valid_transitions(self, state_machine):
        """Test getting valid next transitions"""
        from persistence.constants import AgentState

        transitions = state_machine.get_valid_transitions(AgentState.OBSERVING)

        assert AgentState.ACTING in transitions
        assert AgentState.EVALUATING in transitions
        assert AgentState.AWAITING_HUMAN in transitions

    @pytest.mark.asyncio
    async def test_cleanup_task(self, state_machine):
        """Test cleaning up task state"""
        from persistence.constants import AgentState

        await state_machine.transition("task_008", AgentState.NAVIGATING)

        # Verify state exists
        state = await state_machine.get_current_state("task_008")
        assert state is not None

        # Cleanup
        await state_machine.cleanup_task("task_008")

        # State should still be loadable from store (but not in memory)
        # Memory is cleared
        assert "task_008" not in state_machine._current_checkpoints
