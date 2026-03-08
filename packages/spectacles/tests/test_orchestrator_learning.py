"""
Tests for Orchestrator Learning Integration (Phase 4)

Tests the pattern extraction hooks and confidence tracking in the orchestrator.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import pytest
from unittest.mock import Mock, AsyncMock, MagicMock, patch
from datetime import datetime, timedelta

from core.orchestrator import Orchestrator, TaskContext
from core.reasoner import Pattern
from core.memory.extractor import PatternExtractor
from core.memory.pattern_store import PatternStore
from browser.client import BrowserClient
from persistence.task_store import TaskStore


class TestOrchestratorLearning:
    """Test orchestrator integration with pattern learning."""

    @pytest.fixture
    def mock_browser_client(self):
        """Mock browser client."""
        client = Mock(spec=BrowserClient)
        client.connect = AsyncMock()
        client.disconnect = AsyncMock()
        return client

    @pytest.fixture
    def mock_task_store(self):
        """Mock task store."""
        store = Mock(spec=TaskStore)
        store.create_task = Mock(return_value="task-123")
        store.get_task = Mock(return_value={
            "id": "task-123",
            "goal": "Test login",
            "start_url": "https://example.com",
            "current_state": "COMPLETED"
        })
        store.get_task_actions = Mock(return_value=[
            {
                "id": 1,
                "action_type": "FILL",
                "target_element": "#email",
                "action_params": {"field_name": "email"}
            },
            {
                "id": 2,
                "action_type": "FILL",
                "target_element": "#password",
                "action_params": {"field_name": "password"}
            },
            {
                "id": 3,
                "action_type": "CLICK",
                "target_element": "#submit"
            }
        ])
        store.update_task_state = Mock()
        store.update_task_step = Mock()
        return store

    @pytest.fixture
    def mock_pattern_extractor(self):
        """Mock pattern extractor."""
        extractor = Mock(spec=PatternExtractor)

        # Create a mock pattern to return
        mock_pattern = Pattern(
            id="pattern-123",
            site_domain="example.com",
            site_url="https://example.com",
            goal="Test login",
            pattern_type="LOGIN_FLOW",
            pattern_data={
                "selectors": {"email": "#email", "password": "#password"},
                "sequence": [
                    {"action": "FILL", "target": "#email", "field": "email"},
                    {"action": "FILL", "target": "#password", "field": "password"},
                    {"action": "CLICK", "target": "#submit"}
                ],
                "success_indicators": {"state": "COMPLETED"}
            },
            success_count=1,
            failure_count=0,
            created_at=datetime.utcnow(),
            last_used_at=datetime.utcnow()
        )

        extractor.extract_from_task = AsyncMock(return_value=mock_pattern)
        return extractor

    @pytest.fixture
    def mock_pattern_store(self):
        """Mock pattern store."""
        store = Mock(spec=PatternStore)
        store.store_pattern = AsyncMock()
        store.update_confidence = AsyncMock()
        return store

    @pytest.fixture
    def orchestrator(self, mock_browser_client, mock_task_store):
        """Create orchestrator instance."""
        return Orchestrator(
            browser_client=mock_browser_client,
            task_store=mock_task_store
        )

    @pytest.mark.asyncio
    async def test_extraction_hook_called_on_success(
        self,
        orchestrator,
        mock_pattern_extractor,
        mock_pattern_store
    ):
        """Test that pattern extraction is called when task succeeds."""
        # Configure learning components
        orchestrator.set_pattern_components(
            pattern_extractor=mock_pattern_extractor,
            pattern_store=mock_pattern_store
        )

        # Create task context
        context = TaskContext(
            task_id="task-123",
            goal="Test login",
            start_url="https://example.com"
        )

        # Call learning method directly
        await orchestrator._learn_from_task("task-123", context, success=True)

        # Verify extraction was called
        mock_pattern_extractor.extract_from_task.assert_called_once()
        call_args = mock_pattern_extractor.extract_from_task.call_args
        assert call_args[1]["task_id"] == "task-123"

        # Verify pattern was stored
        mock_pattern_store.store_pattern.assert_called_once()

    @pytest.mark.asyncio
    async def test_extraction_not_called_on_failure(
        self,
        orchestrator,
        mock_pattern_extractor,
        mock_pattern_store
    ):
        """Test that pattern extraction is NOT called when task fails."""
        # Configure learning components
        orchestrator.set_pattern_components(
            pattern_extractor=mock_pattern_extractor,
            pattern_store=mock_pattern_store
        )

        # Create task context
        context = TaskContext(
            task_id="task-123",
            goal="Test login",
            start_url="https://example.com"
        )

        # Call learning method with failure
        await orchestrator._learn_from_task("task-123", context, success=False)

        # Verify extraction was NOT called (only extract from successful tasks)
        mock_pattern_extractor.extract_from_task.assert_not_called()

        # Verify pattern was NOT stored
        mock_pattern_store.store_pattern.assert_not_called()

    @pytest.mark.asyncio
    async def test_confidence_update_on_pattern_use(
        self,
        orchestrator,
        mock_pattern_extractor,
        mock_pattern_store
    ):
        """Test that confidence is updated when existing pattern is used."""
        # Configure learning components
        orchestrator.set_pattern_components(
            pattern_extractor=mock_pattern_extractor,
            pattern_store=mock_pattern_store
        )

        # Create task context with pattern ID
        context = TaskContext(
            task_id="task-123",
            goal="Test login",
            start_url="https://example.com",
            pattern_id="pattern-456"  # Task used this pattern
        )

        # Call learning method with success
        await orchestrator._learn_from_task("task-123", context, success=True)

        # Verify confidence was updated
        mock_pattern_store.update_confidence.assert_called_once_with(
            pattern_id="pattern-456",
            success=True
        )

    @pytest.mark.asyncio
    async def test_learning_failure_does_not_break_task(
        self,
        orchestrator,
        mock_pattern_extractor,
        mock_pattern_store
    ):
        """Test that learning failures don't cause task to fail."""
        # Configure learning components
        orchestrator.set_pattern_components(
            pattern_extractor=mock_pattern_extractor,
            pattern_store=mock_pattern_store
        )

        # Make extraction fail
        mock_pattern_extractor.extract_from_task.side_effect = Exception("Extraction error")

        # Create task context
        context = TaskContext(
            task_id="task-123",
            goal="Test login",
            start_url="https://example.com"
        )

        # Call learning method - should not raise exception
        try:
            await orchestrator._learn_from_task("task-123", context, success=True)
            # Success - exception was caught and logged
        except Exception as e:
            pytest.fail(f"Learning failure should not propagate: {e}")


class TestPatternConfidence:
    """Test pattern confidence calculation."""

    def test_confidence_perfect_success(self):
        """Test confidence with 100% success rate."""
        pattern = Pattern(
            id="p1",
            site_domain="example.com",
            site_url="https://example.com",
            goal="Login",
            pattern_type="LOGIN_FLOW",
            pattern_data={},
            success_count=10,
            failure_count=0,
            created_at=datetime.utcnow(),
            last_used_at=datetime.utcnow()
        )

        # Perfect success = 1.0 confidence
        assert pattern.confidence == 1.0

    def test_confidence_with_failures(self):
        """Test confidence with some failures."""
        pattern = Pattern(
            id="p1",
            site_domain="example.com",
            site_url="https://example.com",
            goal="Login",
            pattern_type="LOGIN_FLOW",
            pattern_data={},
            success_count=8,
            failure_count=2,  # 80% success rate
            created_at=datetime.utcnow(),
            last_used_at=datetime.utcnow()
        )

        # 80% success = 0.8 confidence
        assert pattern.confidence == 0.8

    def test_confidence_sample_size_penalty(self):
        """Test that small sample sizes reduce confidence."""
        pattern = Pattern(
            id="p1",
            site_domain="example.com",
            site_url="https://example.com",
            goal="Login",
            pattern_type="LOGIN_FLOW",
            pattern_data={},
            success_count=3,
            failure_count=0,  # 100% success but only 3 samples
            created_at=datetime.utcnow(),
            last_used_at=datetime.utcnow()
        )

        # Should be penalized for small sample
        # Base: 1.0, Penalty: 0.1 * (1 - 3/10) = 0.07
        # Expected: 1.0 - 0.07 = 0.93
        assert abs(pattern.confidence - 0.93) < 0.01

    def test_confidence_staleness_penalty(self):
        """Test that old patterns are penalized."""
        # Pattern last used 60 days ago
        old_date = datetime.utcnow() - timedelta(days=60)

        pattern = Pattern(
            id="p1",
            site_domain="example.com",
            site_url="https://example.com",
            goal="Login",
            pattern_type="LOGIN_FLOW",
            pattern_data={},
            success_count=10,
            failure_count=0,
            created_at=old_date,
            last_used_at=old_date
        )

        # Should be penalized for staleness
        # Base: 1.0
        # Staleness: min(0.3, 0.01 * (60 - 30)) = min(0.3, 0.3) = 0.3
        # Expected: 1.0 - 0.3 = 0.7
        assert abs(pattern.confidence - 0.7) < 0.01

    def test_confidence_no_usage(self):
        """Test confidence with no usage history."""
        pattern = Pattern(
            id="p1",
            site_domain="example.com",
            site_url="https://example.com",
            goal="Login",
            pattern_type="LOGIN_FLOW",
            pattern_data={},
            success_count=0,
            failure_count=0,
            created_at=datetime.utcnow(),
            last_used_at=datetime.utcnow()
        )

        # No usage = 0.5 (neutral)
        assert pattern.confidence == 0.5

    def test_confidence_bounds(self):
        """Test that confidence stays within 0.0-1.0 bounds."""
        # Pattern with many failures and staleness
        old_date = datetime.utcnow() - timedelta(days=100)

        pattern = Pattern(
            id="p1",
            site_domain="example.com",
            site_url="https://example.com",
            goal="Login",
            pattern_type="LOGIN_FLOW",
            pattern_data={},
            success_count=1,
            failure_count=9,  # 10% success
            created_at=old_date,
            last_used_at=old_date
        )

        # Confidence should never go below 0.0
        assert pattern.confidence >= 0.0
        assert pattern.confidence <= 1.0
