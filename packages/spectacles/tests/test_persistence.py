"""
Tests for Spectacles Persistence Layer
"""

import pytest
import os
import tempfile
from unittest.mock import patch


class TestConstants:
    """Test persistence constants"""

    def test_action_types_defined(self):
        """Test all action types are defined"""
        from persistence.constants import ActionType

        actions = ["CLICK", "FILL", "NAVIGATE", "SCREENSHOT", "WAIT"]
        for action in actions:
            assert hasattr(ActionType, action)

    def test_perception_methods_defined(self):
        """Test perception methods"""
        from persistence.constants import PerceptionMethod

        assert PerceptionMethod.DOM.value == "DOM"
        assert PerceptionMethod.VLM.value == "VLM"
        assert PerceptionMethod.HYBRID.value == "HYBRID"

    def test_hitl_request_types_defined(self):
        """Test HITL request types"""
        from persistence.constants import HITLRequestType

        types = ["APPROVAL", "CAPTCHA", "CREDENTIALS", "TWO_FACTOR"]
        for t in types:
            assert hasattr(HITLRequestType, t)

    def test_hitl_status_defined(self):
        """Test HITL status values"""
        from persistence.constants import HITLStatus

        assert HITLStatus.PENDING.value == "PENDING"
        assert HITLStatus.APPROVED.value == "APPROVED"
        assert HITLStatus.REJECTED.value == "REJECTED"

    def test_default_values(self):
        """Test default configuration values"""
        from persistence.constants import (
            DEFAULT_SESSION_TIMEOUT_MIN,
            DEFAULT_MAX_SESSION_HOURS,
            DEFAULT_MAX_RETRIES
        )

        assert DEFAULT_SESSION_TIMEOUT_MIN == 30
        assert DEFAULT_MAX_SESSION_HOURS == 8
        assert DEFAULT_MAX_RETRIES == 3


class TestTaskStore:
    """Test TaskStore class"""

    def test_create_task(self, task_store, sample_task_data):
        """Test creating a new task"""
        task_id = task_store.create_task(
            goal=sample_task_data["goal"],
            start_url=sample_task_data["start_url"],
            require_approval=sample_task_data["require_approval"],
            credentials_key=sample_task_data["credentials_key"],
            max_retries=sample_task_data["max_retries"],
            metadata=sample_task_data["metadata"]
        )

        assert task_id is not None
        assert len(task_id) > 0

    def test_get_task(self, task_store, sample_task_data):
        """Test retrieving a task by ID"""
        task_id = task_store.create_task(
            goal=sample_task_data["goal"],
            start_url=sample_task_data["start_url"]
        )

        task = task_store.get_task(task_id)

        assert task is not None
        assert task["task_id"] == task_id
        assert task["goal"] == sample_task_data["goal"]
        assert task["start_url"] == sample_task_data["start_url"]
        assert task["current_state"] == "PLANNING"

    def test_get_nonexistent_task(self, task_store):
        """Test getting a task that doesn't exist"""
        task = task_store.get_task("nonexistent_task_id")
        assert task is None

    def test_update_task_state(self, task_store):
        """Test updating task state"""
        from persistence.constants import AgentState

        task_id = task_store.create_task(
            goal="Test task",
            start_url="https://example.com"
        )

        # Valid transition: PLANNING -> NAVIGATING
        result = task_store.update_task_state(task_id, AgentState.NAVIGATING)
        assert result is True

        task = task_store.get_task(task_id)
        assert task["current_state"] == "NAVIGATING"

    def test_update_task_state_invalid_transition(self, task_store):
        """Test invalid state transition is rejected"""
        from persistence.constants import AgentState

        task_id = task_store.create_task(
            goal="Test task",
            start_url="https://example.com"
        )

        # Invalid transition: PLANNING -> COMPLETED
        result = task_store.update_task_state(task_id, AgentState.COMPLETED)
        assert result is False

        # State should remain PLANNING
        task = task_store.get_task(task_id)
        assert task["current_state"] == "PLANNING"

    def test_update_task_state_terminal(self, task_store):
        """Test transitioning to terminal state"""
        from persistence.constants import AgentState

        task_id = task_store.create_task(
            goal="Test task",
            start_url="https://example.com"
        )

        # Transition to terminal state
        task_store.update_task_state(task_id, AgentState.FAILED, error_message="Test error")

        task = task_store.get_task(task_id)
        assert task["current_state"] == "FAILED"
        assert task["is_active"] is False
        assert task["error_message"] == "Test error"

    def test_increment_retry(self, task_store):
        """Test incrementing retry count"""
        task_id = task_store.create_task(
            goal="Test task",
            start_url="https://example.com"
        )

        # Initial retry count should be 0
        task = task_store.get_task(task_id)
        assert task.get("retry_count", 0) == 0

        # Increment
        new_count = task_store.increment_retry(task_id)
        assert new_count == 1

        new_count = task_store.increment_retry(task_id)
        assert new_count == 2

    def test_get_active_tasks(self, task_store):
        """Test getting active tasks"""
        # Create multiple tasks
        task_store.create_task(goal="Task 1", start_url="https://example.com/1")
        task_store.create_task(goal="Task 2", start_url="https://example.com/2")

        active_tasks = task_store.get_active_tasks()

        assert len(active_tasks) >= 2
        for task in active_tasks:
            assert task["is_active"] in [1, True]

    def test_record_action(self, task_store, sample_action_data):
        """Test recording an action"""
        task_id = task_store.create_task(
            goal="Test task",
            start_url="https://example.com"
        )

        action_id = task_store.record_action(
            task_id=task_id,
            action_type=sample_action_data["action_type"],
            target_element=sample_action_data["target_element"],
            action_params=sample_action_data["action_params"],
            result_status=sample_action_data["result_status"],
            confidence_score=sample_action_data["confidence_score"],
            duration_ms=sample_action_data["duration_ms"]
        )

        assert action_id is not None

    def test_get_action_history(self, task_store):
        """Test getting action history"""
        task_id = task_store.create_task(
            goal="Test task",
            start_url="https://example.com"
        )

        # Record multiple actions
        task_store.record_action(task_id, "CLICK", target_element="#btn1")
        task_store.record_action(task_id, "FILL", target_element="#input")
        task_store.record_action(task_id, "CLICK", target_element="#submit")

        history = task_store.get_action_history(task_id)

        assert len(history) == 3
        # Most recent first
        assert history[0]["action_type"] == "CLICK"

    def test_update_task_step(self, task_store):
        """Test updating task progress"""
        task_id = task_store.create_task(
            goal="Test task",
            start_url="https://example.com"
        )

        task_store.update_task_step(task_id, current_step=2, total_steps=5)

        task = task_store.get_task(task_id)
        assert task["current_step"] == 2
        assert task["total_steps"] == 5


class TestDatabaseUtils:
    """Test database utility functions"""

    def test_generate_task_id(self):
        """Test task ID generation"""
        from persistence.utils import generate_task_id

        task_id1 = generate_task_id()
        task_id2 = generate_task_id()

        assert task_id1 != task_id2
        assert len(task_id1) > 0
        assert "task_" in task_id1 or len(task_id1) >= 8

    def test_validate_task_id(self):
        """Test task ID validation"""
        from persistence.utils import validate_task_id, generate_task_id

        # Valid ID should not raise
        valid_id = generate_task_id()
        validate_task_id(valid_id)  # Should not raise

        # Empty ID should raise
        with pytest.raises(ValueError):
            validate_task_id("")

        # None should raise
        with pytest.raises((ValueError, TypeError)):
            validate_task_id(None)

    def test_safe_json_parse(self):
        """Test safe JSON parsing"""
        from persistence.utils import safe_json_parse

        # Valid JSON
        result = safe_json_parse('{"key": "value"}')
        assert result == {"key": "value"}

        # Invalid JSON returns empty dict
        result = safe_json_parse("not json")
        assert result == {} or result is None

        # None returns empty dict
        result = safe_json_parse(None)
        assert result == {} or result is None

    def test_safe_json_dump(self):
        """Test safe JSON dumping"""
        from persistence.utils import safe_json_dump

        data = {"key": "value", "number": 42}
        result = safe_json_dump(data)

        assert '"key"' in result
        assert '"value"' in result

        # None returns None or empty string
        result = safe_json_dump(None)
        assert result is None or result == "null"
