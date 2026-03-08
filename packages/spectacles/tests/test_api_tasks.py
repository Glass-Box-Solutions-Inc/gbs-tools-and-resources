"""
Tests for Spectacles Task API Endpoints
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock


class TestTaskSubmission:
    """Test task submission endpoints"""

    @patch('api.routes.tasks.get_orchestrator')
    def test_submit_task_success(self, mock_get_orch, test_client, sample_task_data):
        """Test successful task submission"""
        mock_orchestrator = MagicMock()
        mock_orchestrator.submit_task = AsyncMock(return_value="task_123")
        mock_orchestrator.execute_task = AsyncMock()
        mock_get_orch.return_value = mock_orchestrator

        response = test_client.post("/api/tasks/", json={
            "goal": sample_task_data["goal"],
            "start_url": sample_task_data["start_url"],
            "require_approval": sample_task_data["require_approval"]
        })

        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == "task_123"
        assert data["status"] == "submitted"
        assert "message" in data

    def test_submit_task_missing_goal(self, test_client):
        """Test task submission fails without goal"""
        response = test_client.post("/api/tasks/", json={
            "start_url": "https://example.com"
        })

        assert response.status_code == 422  # Validation error

    def test_submit_task_missing_url(self, test_client):
        """Test task submission fails without start_url"""
        response = test_client.post("/api/tasks/", json={
            "goal": "Do something"
        })

        assert response.status_code == 422  # Validation error


class TestTaskStatus:
    """Test task status endpoints"""

    @patch('api.routes.tasks.get_orchestrator')
    def test_get_task_status_found(self, mock_get_orch, test_client):
        """Test getting status of existing task"""
        mock_orchestrator = MagicMock()
        mock_orchestrator.get_task_status = AsyncMock(return_value={
            "task_id": "task_123",
            "goal": "Test goal",
            "state": "PLANNING",
            "step": 0,
            "total_steps": 5,
            "is_active": True,
            "created_at": "2025-01-01T00:00:00",
            "updated_at": "2025-01-01T00:00:00",
            "error": None,
            "checkpoint_id": None
        })
        mock_get_orch.return_value = mock_orchestrator

        response = test_client.get("/api/tasks/task_123")

        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == "task_123"
        assert data["state"] == "PLANNING"

    @patch('api.routes.tasks.get_orchestrator')
    def test_get_task_status_not_found(self, mock_get_orch, test_client):
        """Test getting status of non-existent task"""
        mock_orchestrator = MagicMock()
        mock_orchestrator.get_task_status = AsyncMock(return_value={
            "error": "Task not found"
        })
        mock_get_orch.return_value = mock_orchestrator

        response = test_client.get("/api/tasks/nonexistent_task")

        assert response.status_code == 404


class TestTaskResume:
    """Test task resume endpoints"""

    @patch('api.routes.tasks.get_orchestrator')
    def test_resume_task_approved(self, mock_get_orch, test_client):
        """Test resuming task with approval"""
        mock_orchestrator = MagicMock()
        mock_orchestrator.resume_task = AsyncMock()
        mock_get_orch.return_value = mock_orchestrator

        response = test_client.post("/api/tasks/task_123/resume", json={
            "approved": True,
            "human_input": {"notes": "Looks good"}
        })

        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == "task_123"
        assert data["status"] == "resuming"

    @patch('api.routes.tasks.get_orchestrator')
    def test_resume_task_rejected(self, mock_get_orch, test_client):
        """Test resuming task with rejection"""
        mock_orchestrator = MagicMock()
        mock_orchestrator.resume_task = AsyncMock()
        mock_get_orch.return_value = mock_orchestrator

        response = test_client.post("/api/tasks/task_123/resume", json={
            "approved": False
        })

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "resuming"


class TestTaskCancel:
    """Test task cancellation endpoints"""

    @patch('api.routes.tasks.get_orchestrator')
    def test_cancel_task_success(self, mock_get_orch, test_client):
        """Test successful task cancellation"""
        mock_orchestrator = MagicMock()
        mock_orchestrator.cancel_task = AsyncMock(return_value=True)
        mock_get_orch.return_value = mock_orchestrator

        response = test_client.post("/api/tasks/task_123/cancel")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "cancelled"

    @patch('api.routes.tasks.get_orchestrator')
    def test_cancel_task_not_found(self, mock_get_orch, test_client):
        """Test cancelling non-existent task"""
        mock_orchestrator = MagicMock()
        mock_orchestrator.cancel_task = AsyncMock(return_value=False)
        mock_get_orch.return_value = mock_orchestrator

        response = test_client.post("/api/tasks/nonexistent/cancel")

        assert response.status_code == 404


class TestTaskActions:
    """Test task action history endpoints"""

    @patch('persistence.task_store.TaskStore')
    def test_get_task_actions(self, mock_store_class, test_client):
        """Test getting action history"""
        mock_store = MagicMock()
        mock_store.get_action_history.return_value = [
            {"action_type": "CLICK", "target_element": "#btn"},
            {"action_type": "FILL", "target_element": "#input"}
        ]
        mock_store_class.return_value = mock_store

        response = test_client.get("/api/tasks/task_123/actions")

        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == "task_123"
        assert len(data["actions"]) == 2
