"""
Unit tests for AI Reasoner Core

Tests the strategic planning logic that decides between pattern-based
and VLM-based discovery execution.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, Mock
from core.reasoner import AIReasoner, ExecutionPlan, Pattern


class TestAIReasoner:
    """Test cases for AIReasoner strategic planning."""

    @pytest.fixture
    def mock_pattern_store(self):
        """Create a mock pattern store."""
        store = AsyncMock()
        return store

    @pytest.fixture
    def reasoner_with_store(self, mock_pattern_store):
        """Create reasoner with mocked pattern store."""
        return AIReasoner(
            pattern_store=mock_pattern_store,
            gemini_api_key="test-key"
        )

    @pytest.fixture
    def reasoner_no_store(self):
        """Create reasoner without pattern store."""
        return AIReasoner(
            pattern_store=None,
            gemini_api_key="test-key"
        )

    @pytest.fixture
    def high_confidence_pattern(self):
        """Create a high-confidence pattern (success rate > 0.7)."""
        return Pattern(
            id="pattern-123",
            site_domain="example.com",
            site_url="https://example.com",
            goal="login",
            pattern_type="LOGIN_FLOW",
            pattern_data={
                "sequence": [
                    {"action": "fill", "target": "#email", "field": "email"},
                    {"action": "fill", "target": "#password", "field": "password"},
                    {"action": "click", "target": "#submit"}
                ]
            },
            success_count=8,
            failure_count=2,
            created_at=datetime.utcnow(),
            last_used_at=datetime.utcnow()
        )

    @pytest.fixture
    def low_confidence_pattern(self):
        """Create a low-confidence pattern (success rate < 0.7)."""
        return Pattern(
            id="pattern-456",
            site_domain="example.com",
            site_url="https://example.com",
            goal="search",
            pattern_type="NAVIGATION",
            pattern_data={"sequence": []},
            success_count=3,
            failure_count=7,
            created_at=datetime.utcnow(),
            last_used_at=datetime.utcnow()
        )

    @pytest.mark.asyncio
    async def test_reasoner_pattern_retrieval(self, reasoner_with_store, mock_pattern_store, high_confidence_pattern):
        """Test that reasoner retrieves and uses high-confidence patterns."""
        # Setup
        mock_pattern_store.query_similar.return_value = [high_confidence_pattern]

        # Execute
        plan = await reasoner_with_store.plan_task(
            goal="login to site",
            url="https://example.com/login"
        )

        # Verify
        assert plan.plan_type == "pattern"
        assert plan.pattern_id == "pattern-123"
        assert plan.estimated_vlm_calls == 0
        assert plan.confidence > 0.7
        assert len(plan.steps) == 3
        assert plan.steps[0]["action"] == "fill"
        
        # Verify pattern store was queried
        mock_pattern_store.query_similar.assert_called_once()

    @pytest.mark.asyncio
    async def test_reasoner_fallback_discovery(self, reasoner_with_store, mock_pattern_store):
        """Test that reasoner falls back to discovery when no pattern found."""
        # Setup - no patterns returned
        mock_pattern_store.query_similar.return_value = []

        # Execute
        plan = await reasoner_with_store.plan_task(
            goal="unknown task",
            url="https://newsite.com"
        )

        # Verify
        assert plan.plan_type == "discovery"
        assert plan.pattern_id is None
        assert plan.estimated_vlm_calls > 0
        assert plan.confidence == 0.5
        assert len(plan.steps) > 0

    @pytest.mark.asyncio
    async def test_reasoner_confidence_threshold(self, reasoner_with_store, mock_pattern_store, low_confidence_pattern):
        """Test that patterns below 0.7 confidence threshold are not used."""
        # Setup - return low confidence pattern
        mock_pattern_store.query_similar.return_value = [low_confidence_pattern]

        # Execute
        plan = await reasoner_with_store.plan_task(
            goal="search",
            url="https://example.com"
        )

        # Verify - should fall back to discovery despite pattern existing
        assert plan.plan_type == "discovery"
        assert plan.pattern_id is None
        assert plan.estimated_vlm_calls > 0

    @pytest.mark.asyncio
    async def test_reasoner_with_orchestrator(self, reasoner_no_store):
        """Test reasoner integration pattern (no pattern store yet)."""
        # Execute
        plan = await reasoner_no_store.plan_task(
            goal="test task",
            url="https://example.com"
        )

        # Verify - should use discovery mode when no store
        assert plan.plan_type == "discovery"
        assert plan.pattern_id is None
        assert isinstance(plan.steps, list)
        assert plan.estimated_vlm_calls > 0

    def test_pattern_confidence_calculation(self):
        """Test pattern confidence calculation logic."""
        # High success rate
        pattern_high = Pattern(
            id="test",
            site_domain="example.com",
            site_url="https://example.com",
            goal="test",
            pattern_type="GENERIC",
            pattern_data={},
            success_count=9,
            failure_count=1,
            created_at=datetime.utcnow(),
            last_used_at=datetime.utcnow()
        )
        assert pattern_high.confidence == 0.9

        # Low success rate
        pattern_low = Pattern(
            id="test2",
            site_domain="example.com",
            site_url="https://example.com",
            goal="test",
            pattern_type="GENERIC",
            pattern_data={},
            success_count=2,
            failure_count=8,
            created_at=datetime.utcnow(),
            last_used_at=datetime.utcnow()
        )
        assert pattern_low.confidence == 0.2

        # No data yet
        pattern_new = Pattern(
            id="test3",
            site_domain="example.com",
            site_url="https://example.com",
            goal="test",
            pattern_type="GENERIC",
            pattern_data={},
            success_count=0,
            failure_count=0,
            created_at=datetime.utcnow(),
            last_used_at=datetime.utcnow()
        )
        assert pattern_new.confidence == 0.5

    def test_execution_plan_structure(self):
        """Test ExecutionPlan dataclass structure."""
        plan = ExecutionPlan(
            plan_type="pattern",
            pattern_id="test-123",
            steps=[{"action": "click"}],
            estimated_vlm_calls=0,
            confidence=0.85,
            reasoning="test"
        )

        assert plan.plan_type == "pattern"
        assert plan.pattern_id == "test-123"
        assert len(plan.steps) == 1
        assert plan.estimated_vlm_calls == 0
        assert plan.confidence == 0.85
