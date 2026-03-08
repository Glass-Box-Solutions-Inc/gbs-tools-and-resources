"""
Embedding Service - Generate semantic embeddings for pattern matching

Uses sentence-transformers (all-MiniLM-L6-v2) for fast, local embedding generation.
No external API calls required - model runs locally in Docker container.

Performance:
- Embedding generation: <100ms per text
- Dimension: 384 (compact but effective)
- Model size: ~90MB (cached in Docker image)

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import logging
from typing import List
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class EmbeddingService:
    """
    Generate embeddings for semantic search using sentence-transformers.
    
    Features:
    - Local model execution (no API calls)
    - In-memory caching for repeated queries
    - Fast generation (<100ms per embedding)
    - 384-dimensional vectors (good balance of size/quality)
    """

    def __init__(self, model_name: str = 'all-MiniLM-L6-v2'):
        """
        Initialize embedding service.
        
        Args:
            model_name: Sentence transformer model name
        """
        self.model_name = model_name
        self._model = None
        self._cache = {}  # In-memory cache for embeddings
        
        logger.info("EmbeddingService initialized (model: %s)", model_name)

    def _ensure_model_loaded(self):
        """Lazy load the sentence transformer model."""
        if self._model is None:
            logger.info("Loading sentence transformer model: %s", self.model_name)
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.model_name)
                logger.info("Model loaded successfully")
            except ImportError:
                logger.error("sentence-transformers not installed. Run: pip install sentence-transformers")
                raise
            except Exception as e:
                logger.error("Failed to load model: %s", e)
                raise

    async def generate(self, text: str) -> List[float]:
        """
        Generate 384-dim embedding for text.
        
        Args:
            text: Input text to embed
            
        Returns:
            List of 384 floats representing the embedding
        """
        # Check cache first
        if text in self._cache:
            logger.debug("Cache hit for text: %s", text[:50])
            return self._cache[text]

        # Ensure model is loaded
        self._ensure_model_loaded()

        # Generate embedding
        try:
            embedding = self._model.encode(text, convert_to_numpy=True)
            embedding_list = embedding.tolist()
            
            # Cache result
            self._cache[text] = embedding_list
            
            logger.debug("Generated embedding for text: %s (dim: %d)", text[:50], len(embedding_list))
            return embedding_list
        except Exception as e:
            logger.error("Error generating embedding: %s", e)
            raise

    async def generate_task_embedding(self, url: str, goal: str) -> List[float]:
        """
        Generate embedding for a browser automation task.
        
        Combines URL domain and goal into a semantic representation:
        "example.com login to the system"
        
        This allows matching similar tasks on the same site.
        
        Args:
            url: Starting URL for the task
            goal: Natural language task description
            
        Returns:
            384-dimensional embedding vector
        """
        # Extract domain from URL
        try:
            domain = urlparse(url).netloc
        except Exception as e:
            logger.warning("Failed to parse URL '%s': %s", url, e)
            domain = url

        # Combine domain and goal for semantic matching
        text = f"{domain} {goal}"
        
        logger.debug("Generating task embedding: '%s'", text)
        return await self.generate(text)

    def clear_cache(self):
        """Clear the embedding cache."""
        cache_size = len(self._cache)
        self._cache.clear()
        logger.info("Cleared embedding cache (%d entries)", cache_size)

    @property
    def cache_size(self) -> int:
        """Get current cache size."""
        return len(self._cache)
