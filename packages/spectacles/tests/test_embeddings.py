"""
Unit tests for Embedding Service

Tests semantic embedding generation using sentence-transformers.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import pytest
from core.memory.embeddings import EmbeddingService


class TestEmbeddingService:
    """Test cases for embedding generation."""

    @pytest.fixture
    def embedding_service(self):
        """Create embedding service instance."""
        return EmbeddingService()

    @pytest.mark.asyncio
    async def test_embedding_generation_shape(self, embedding_service):
        """Test that embeddings have correct shape (384 dimensions)."""
        # Generate embedding
        embedding = await embedding_service.generate("test text")
        
        # Verify shape
        assert isinstance(embedding, list)
        assert len(embedding) == 384
        assert all(isinstance(x, float) for x in embedding)

    @pytest.mark.asyncio
    async def test_embedding_cache(self, embedding_service):
        """Test that caching works correctly."""
        text = "test caching"
        
        # First call
        embedding1 = await embedding_service.generate(text)
        cache_size_after_first = embedding_service.cache_size
        
        # Second call (should hit cache)
        embedding2 = await embedding_service.generate(text)
        cache_size_after_second = embedding_service.cache_size
        
        # Verify same embedding returned
        assert embedding1 == embedding2
        
        # Verify cache didn't grow on second call
        assert cache_size_after_first == cache_size_after_second
        assert cache_size_after_first == 1

    @pytest.mark.asyncio
    async def test_task_embedding_format(self, embedding_service):
        """Test task embedding combines URL domain and goal."""
        url = "https://example.com/login"
        goal = "login to system"
        
        # Generate task embedding
        embedding = await embedding_service.generate_task_embedding(url, goal)
        
        # Verify structure
        assert isinstance(embedding, list)
        assert len(embedding) == 384

    def test_cache_clear(self, embedding_service):
        """Test cache clearing functionality."""
        # Add some items to cache (sync for test simplicity)
        embedding_service._cache["test1"] = [0.1] * 384
        embedding_service._cache["test2"] = [0.2] * 384
        
        assert embedding_service.cache_size == 2
        
        # Clear cache
        embedding_service.clear_cache()
        
        assert embedding_service.cache_size == 0
