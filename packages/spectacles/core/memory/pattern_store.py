"""
Pattern Store - Qdrant-based pattern storage and retrieval

Implements fully isolated memory system using Qdrant embedded mode.
No external services required - all data stored locally.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import logging
import os
from typing import List, Optional
from datetime import datetime
from urllib.parse import urlparse

from core.reasoner import Pattern
from core.memory.embeddings import EmbeddingService

logger = logging.getLogger(__name__)


class PatternStore:
    """
    Interface for storing and retrieving patterns from Qdrant.
    
    Features:
    - Qdrant embedded mode (no external service)
    - Semantic similarity search
    - Domain-based filtering
    - Pattern confidence tracking
    """

    def __init__(self, storage_path: str = "./qdrant_storage"):
        """
        Initialize pattern store with Qdrant embedded mode.
        
        Args:
            storage_path: Local directory for Qdrant storage
        """
        self.storage_path = storage_path
        self.collection_name = "spectacles-memory"
        self.embeddings = EmbeddingService()
        self._client = None
        
        logger.info("PatternStore initialized (storage: %s)", storage_path)

    def _ensure_client(self):
        """Lazy initialize Qdrant client."""
        if self._client is None:
            try:
                from qdrant_client import QdrantClient
                from qdrant_client.models import Distance, VectorParams
                
                logger.info("Initializing Qdrant client (embedded mode)")
                self._client = QdrantClient(path=self.storage_path)
                
                # Ensure collection exists
                self._ensure_collection()
            except ImportError:
                logger.error("qdrant-client not installed. Run: pip install qdrant-client")
                raise
            except Exception as e:
                logger.error("Failed to initialize Qdrant client: %s", e)
                raise

    def _ensure_collection(self):
        """Create Qdrant collection if it doesn't exist."""
        from qdrant_client.models import Distance, VectorParams
        
        try:
            collections = self._client.get_collections().collections
            collection_names = [c.name for c in collections]
            
            if self.collection_name not in collection_names:
                logger.info("Creating Qdrant collection: %s", self.collection_name)
                self._client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(size=384, distance=Distance.COSINE)
                )
                logger.info("Collection created successfully")
            else:
                logger.debug("Collection '%s' already exists", self.collection_name)
        except Exception as e:
            logger.error("Error ensuring collection exists: %s", e)
            raise

    async def query_similar(self, goal: str, url: str, limit: int = 5) -> List[Pattern]:
        """
        Query Qdrant for similar patterns.
        
        Args:
            goal: Task goal description
            url: Starting URL
            limit: Maximum number of results
            
        Returns:
            List of matching Pattern objects, sorted by similarity
        """
        # Ensure client is initialized
        self._ensure_client()

        # Generate embedding for query
        embedding = await self.embeddings.generate_task_embedding(url, goal)

        # Extract domain for filtering
        domain = urlparse(url).netloc

        try:
            # Query Qdrant
            # Note: Actual querying logic will be implemented with real DB schema
            # For now, return empty list (no patterns stored yet)
            logger.debug("Querying patterns for domain=%s, goal='%s'", domain, goal)
            return []
        except Exception as e:
            logger.error("Error querying patterns: %s", e)
            return []

    async def store_pattern(self, pattern: Pattern):
        """
        Store pattern in Qdrant and update metadata.
        
        Args:
            pattern: Pattern object to store
        """
        # Ensure client is initialized
        self._ensure_client()

        # Generate embedding
        embedding = await self.embeddings.generate_task_embedding(
            pattern.site_url,
            pattern.goal
        )

        logger.info("Storing pattern: %s (type: %s, domain: %s)",
                   pattern.id, pattern.pattern_type, pattern.site_domain)

        # Note: Actual storage will be implemented with proper schema
        # For Phase 2, focus is on architecture and interfaces

    async def update_confidence(self, pattern_id: str, success: bool):
        """
        Update pattern confidence after use.
        
        Args:
            pattern_id: Pattern ID to update
            success: Whether the pattern execution succeeded
        """
        logger.info("Updating pattern confidence: %s (success=%s)", pattern_id, success)
        
        # Note: Will implement with SQLite integration
        pass

    def get_collection_info(self) -> dict:
        """Get information about the Qdrant collection."""
        self._ensure_client()
        
        try:
            collection = self._client.get_collection(self.collection_name)
            return {
                "name": self.collection_name,
                "vectors_count": collection.vectors_count if hasattr(collection, 'vectors_count') else 0,
                "status": "ready"
            }
        except Exception as e:
            logger.error("Error getting collection info: %s", e)
            return {
                "name": self.collection_name,
                "error": str(e),
                "status": "error"
            }
