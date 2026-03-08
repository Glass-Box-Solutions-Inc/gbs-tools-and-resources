"""
Integration Tests for Full Learning Cycle (Phase 4)

Tests the complete pattern learning workflow from task execution to pattern storage
and reuse, including confidence updates.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timedelta

from core.orchestrator import Orchestrator, TaskContext
from core.reasoner import Pattern, AIReasoner
from core.memory.extractor import PatternExtractor
from core.memory.pattern_store import PatternStore
from browser.client import BrowserClient
from persistence.task_store import TaskStore


class TestFullLearningCycle:
    """Test complete learning workflow."""

    @pytest.fixture
    def sample_task_data(self):
        """Sample task data for testing."""
        return {
            "id": "task-123",
            "goal": "Login to example.com",
            "start_url": "https://example.com/login",
            "current_state": "COMPLETED"
        }

    @pytest.fixture
    def sample_actions(self):
        """Sample action history for testing."""
        return [
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
                "target_element": "#submit",
                "result_data": {"text": "Login"}
            }
        ]

    @pytest.mark.asyncio
    async def test_task_creates_pattern(self, sample_task_data, sample_actions):
        """Test that successful task execution creates a new pattern."""
        # Create real extractor
        extractor = PatternExtractor()

        # Extract pattern from task
        pattern = await extractor.extract_from_task(
            task_id="task-123",
            task_data=sample_task_data,
            actions=sample_actions
        )

        # Verify pattern was created
        assert pattern is not None
        assert pattern.pattern_type == "LOGIN_FLOW"
        assert pattern.site_domain == "example.com"
        assert pattern.goal == "Login to example.com"
        assert pattern.success_count == 1
        assert pattern.failure_count == 0

        # Verify selectors extracted
        assert "email_field" in pattern.pattern_data["selectors"]
        assert "password_field" in pattern.pattern_data["selectors"]

        # Verify sequence built
        assert len(pattern.pattern_data["sequence"]) == 3
        assert pattern.pattern_data["sequence"][0]["action"] == "FILL"
        assert pattern.pattern_data["sequence"][1]["action"] == "FILL"
        assert pattern.pattern_data["sequence"][2]["action"] == "CLICK"

    @pytest.mark.asyncio
    async def test_pattern_reuse_updates_confidence(self, sample_task_data, sample_actions):
        """Test that using an existing pattern updates its confidence."""
        # Create a stored pattern (simulating previous extraction)
        stored_pattern = Pattern(
            id="pattern-existing",
            site_domain="example.com",
            site_url="https://example.com/login",
            goal="Login to example.com",
            pattern_type="LOGIN_FLOW",
            pattern_data={
                "selectors": {"email_field": "#email", "password_field": "#password"},
                "sequence": [
                    {"action": "FILL", "target": "#email"},
                    {"action": "FILL", "target": "#password"},
                    {"action": "CLICK", "target": "#submit"}
                ],
                "success_indicators": {"state": "COMPLETED"}
            },
            success_count=5,
            failure_count=1,
            created_at=datetime.utcnow(),
            last_used_at=datetime.utcnow()
        )

        # Initial confidence: 5/(5+1) = 0.833... minus sample penalty
        # Sample size = 6 < 10, so penalty = 0.1 * (1 - 6/10) = 0.04
        # Expected: 0.833 - 0.04 = 0.793
        initial_confidence = stored_pattern.confidence
        assert abs(initial_confidence - 0.793) < 0.01

        # Simulate success - increment success count
        stored_pattern.success_count += 1
        stored_pattern.last_used_at = datetime.utcnow()

        # New confidence: 6/(6+1) = 0.857... minus sample penalty
        # Sample size = 7 < 10, so penalty = 0.1 * (1 - 7/10) = 0.03
        # Expected: 0.857 - 0.03 = 0.827
        new_confidence = stored_pattern.confidence
        assert new_confidence > initial_confidence
        assert abs(new_confidence - 0.827) < 0.01

    @pytest.mark.asyncio
    async def test_pattern_confidence_degrades_on_failure(self):
        """Test that pattern confidence decreases when execution fails."""
        # Create pattern with good success rate
        pattern = Pattern(
            id="pattern-test",
            site_domain="example.com",
            site_url="https://example.com/login",
            goal="Login",
            pattern_type="LOGIN_FLOW",
            pattern_data={},
            success_count=8,
            failure_count=2,  # 80% success
            created_at=datetime.utcnow(),
            last_used_at=datetime.utcnow()
        )

        # Initial confidence: 8/10 = 0.8
        initial_confidence = pattern.confidence
        assert initial_confidence == 0.8

        # Simulate failure
        pattern.failure_count += 1
        pattern.last_used_at = datetime.utcnow()

        # New confidence: 8/11 = 0.727...
        new_confidence = pattern.confidence
        assert new_confidence < initial_confidence
        assert abs(new_confidence - 0.727) < 0.01

    @pytest.mark.asyncio
    async def test_end_to_end_learning_workflow(self, sample_task_data, sample_actions):
        """
        Test complete workflow:
        1. Task A executes and creates pattern
        2. Pattern is stored
        3. Task B retrieves pattern
        4. Task B execution updates confidence
        """
        # Step 1: Task A creates pattern
        extractor = PatternExtractor()
        pattern_a = await extractor.extract_from_task(
            task_id="task-a",
            task_data=sample_task_data,
            actions=sample_actions
        )

        assert pattern_a is not None
        assert pattern_a.success_count == 1
        assert pattern_a.failure_count == 0

        # Step 2: Simulate pattern storage (in real system, would be in Qdrant/SQLite)
        stored_patterns = {pattern_a.site_domain: pattern_a}

        # Step 3: Task B retrieves pattern
        retrieved_pattern = stored_patterns.get("example.com")
        assert retrieved_pattern is not None
        assert retrieved_pattern.id == pattern_a.id

        # Step 4: Task B succeeds, update confidence
        retrieved_pattern.success_count += 1
        retrieved_pattern.last_used_at = datetime.utcnow()

        # Verify confidence increased
        # Initial: 1/1 = 1.0 (but penalized for sample size)
        # After: 2/2 = 1.0 (less penalty)
        assert retrieved_pattern.success_count == 2
        assert retrieved_pattern.confidence > 0.8  # High confidence


class TestConfidenceTracking:
    """Test confidence tracking over multiple uses."""

    def test_confidence_improves_with_successes(self):
        """Test that confidence improves as pattern succeeds more."""
        pattern = Pattern(
            id="p1",
            site_domain="example.com",
            site_url="https://example.com",
            goal="Login",
            pattern_type="LOGIN_FLOW",
            pattern_data={},
            success_count=1,
            failure_count=0,
            created_at=datetime.utcnow(),
            last_used_at=datetime.utcnow()
        )

        confidences = [pattern.confidence]

        # Simulate 9 more successes
        for i in range(9):
            pattern.success_count += 1
            pattern.last_used_at = datetime.utcnow()
            confidences.append(pattern.confidence)

        # Confidence should increase (due to reduced sample size penalty)
        assert confidences[-1] > confidences[0]
        assert confidences[-1] == 1.0  # 10 successes, no failures = perfect

    def test_confidence_stabilizes_with_consistent_performance(self):
        """Test that confidence stabilizes with consistent 80% success rate."""
        pattern = Pattern(
            id="p1",
            site_domain="example.com",
            site_url="https://example.com",
            goal="Login",
            pattern_type="LOGIN_FLOW",
            pattern_data={},
            success_count=8,
            failure_count=2,
            created_at=datetime.utcnow(),
            last_used_at=datetime.utcnow()
        )

        initial_confidence = pattern.confidence

        # Add more samples maintaining 80% success
        for i in range(40):
            if i % 5 == 0:  # 1 in 5 fails (80% success)
                pattern.failure_count += 1
            else:
                pattern.success_count += 1
            pattern.last_used_at = datetime.utcnow()

        final_confidence = pattern.confidence

        # Confidence should stabilize around 0.8
        assert abs(final_confidence - 0.8) < 0.05

    def test_old_pattern_loses_confidence(self):
        """Test that patterns lose confidence over time if not used."""
        # Pattern last used 90 days ago
        old_date = datetime.utcnow() - timedelta(days=90)

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

        # Should have significant staleness penalty
        # Base: 1.0
        # Staleness: min(0.3, 0.01 * (90 - 30)) = min(0.3, 0.6) = 0.3
        # Expected: ~0.7
        assert pattern.confidence < 0.8
        assert abs(pattern.confidence - 0.7) < 0.1


class TestLearningRobustness:
    """Test that learning system is robust to edge cases."""

    @pytest.mark.asyncio
    async def test_no_pattern_extracted_from_failed_task(self):
        """Test that failed tasks don't create patterns."""
        extractor = PatternExtractor()

        failed_task = {
            "id": "task-failed",
            "goal": "Login",
            "start_url": "https://example.com",
            "current_state": "FAILED"  # Failed state
        }

        actions = [
            {"id": 1, "action_type": "FILL", "target_element": "#email"}
        ]

        pattern = await extractor.extract_from_task(
            task_id="task-failed",
            task_data=failed_task,
            actions=actions
        )

        # Should not extract pattern from failed task
        assert pattern is None

    @pytest.mark.asyncio
    async def test_no_pattern_from_empty_actions(self):
        """Test that tasks with no actions don't create patterns."""
        extractor = PatternExtractor()

        task = {
            "id": "task-empty",
            "goal": "Login",
            "start_url": "https://example.com",
            "current_state": "COMPLETED"
        }

        # No actions
        actions = []

        pattern = await extractor.extract_from_task(
            task_id="task-empty",
            task_data=task,
            actions=actions
        )

        # Should not extract pattern from task with no actions
        assert pattern is None
