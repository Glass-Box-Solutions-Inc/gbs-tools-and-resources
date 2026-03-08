"""
Unit tests for Pattern Store

Tests Qdrant-based pattern storage and retrieval.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import pytest
import tempfile
import shutil
from datetime import datetime
from core.memory.pattern_store import PatternStore
from core.reasoner import Pattern


class TestPatternStore:
    """Test cases for pattern store operations."""

    @pytest.fixture
    def temp_storage(self):
        """Create temporary storage directory."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        # Cleanup
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def pattern_store(self, temp_storage):
        """Create pattern store with temporary storage."""
        return PatternStore(storage_path=temp_storage)

    @pytest.fixture
    def sample_pattern(self):
        """Create a sample pattern for testing."""
        return Pattern(
            id="test-pattern-123",
            site_domain="example.com",
            site_url="https://example.com/login",
            goal="login to system",
            pattern_type="LOGIN_FLOW",
            pattern_data={
                "sequence": [
                    {"action": "fill", "target": "#email"},
                    {"action": "fill", "target": "#password"},
                    {"action": "click", "target": "#submit"}
                ]
            },
            success_count=5,
            failure_count=1,
            created_at=datetime.utcnow(),
            last_used_at=datetime.utcnow()
        )

    def test_pattern_store_initialization(self, pattern_store, temp_storage):
        """Test that pattern store initializes correctly."""
        assert pattern_store.storage_path == temp_storage
        assert pattern_store.collection_name == "spectacles-memory"
        assert pattern_store.embeddings is not None

    @pytest.mark.asyncio
    async def test_query_similar_empty(self, pattern_store):
        """Test querying returns empty list when no patterns stored."""
        results = await pattern_store.query_similar(
            goal="test goal",
            url="https://example.com",
            limit=5
        )
        
        assert isinstance(results, list)
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_store_pattern(self, pattern_store, sample_pattern):
        """Test storing a pattern (architecture test, not full implementation)."""
        # This tests the interface exists and doesn't error
        await pattern_store.store_pattern(sample_pattern)
        
        # For Phase 2, we're focusing on architecture
        # Full storage/retrieval will be completed in integration

    @pytest.mark.asyncio
    async def test_update_confidence(self, pattern_store):
        """Test confidence update interface."""
        # Test interface exists
        await pattern_store.update_confidence("test-pattern-123", success=True)
        
        # No assertion needed - testing interface exists

    def test_collection_info(self, pattern_store):
        """Test getting collection information."""
        info = pattern_store.get_collection_info()
        
        assert isinstance(info, dict)
        assert "name" in info
        assert info["name"] == "spectacles-memory"
