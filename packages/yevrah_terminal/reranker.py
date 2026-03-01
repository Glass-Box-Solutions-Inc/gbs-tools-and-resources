"""
Cohere Rerank integration for improving search result relevance.
Uses Cohere's rerank-v4.0-fast model to reorder search results based on query relevance.
"""
import os
import logging
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv(override=True)

logger = logging.getLogger("reranker")


class CohereReranker:
    """Client for Cohere Rerank API."""

    def __init__(self):
        """Initialize Cohere reranker with API key from environment."""
        api_key = os.getenv("COHERE_API_KEY")

        if not api_key:
            self.client = None
            logger.warning("COHERE_API_KEY not found. Reranking will be skipped.")
            return

        try:
            import cohere
            self.client = cohere.ClientV2(api_key=api_key)
            self.model = "rerank-v4.0-fast"
            logger.info(f"Initialized Cohere reranker with model: {self.model}")
        except ImportError:
            self.client = None
            logger.error("Cohere library not installed. Run: pip install cohere>=5.0.0")
        except Exception as e:
            self.client = None
            logger.error(f"Failed to initialize Cohere client: {e}")

    def rerank(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        top_n: int = 5,
        return_documents: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Rerank search results using Cohere's rerank model.

        Args:
            query: The search query
            documents: List of document dicts with at least 'snippet' or 'case_name' fields
            top_n: Number of top results to return (default 5)
            return_documents: Whether to return full document objects (default True)

        Returns:
            List of reranked documents, limited to top_n
        """
        if not self.client:
            logger.warning("Cohere client not available. Returning original documents.")
            return documents[:top_n]

        if not documents:
            return []

        if len(documents) <= top_n:
            # Already have fewer results than requested
            return documents

        try:
            # Prepare documents for reranking - combine multiple fields for richer context
            doc_texts = []
            for doc in documents:
                case_name = doc.get("case_name", "")
                snippet = doc.get("snippet", "")
                syllabus = doc.get("syllabus", "")
                court = doc.get("court", "")
                posture = doc.get("posture", "")
                procedural_history = doc.get("procedural_history", "")

                # Get opinion snippets if available (may have multiple opinions)
                opinions = doc.get("opinions", [])
                opinion_snippets = []
                for opinion in opinions[:2]:  # Limit to first 2 opinions
                    op_snippet = opinion.get("snippet", "")
                    if op_snippet and op_snippet != snippet:  # Avoid duplicates
                        opinion_snippets.append(op_snippet)

                # Build rich context for reranking
                parts = []
                if case_name:
                    parts.append(f"Case: {case_name}")
                if court:
                    parts.append(f"Court: {court}")
                if snippet:
                    parts.append(f"Snippet: {snippet}")

                # Add additional opinion snippets
                for i, op_snippet in enumerate(opinion_snippets, 1):
                    parts.append(f"Opinion {i}: {op_snippet}")

                # Syllabus is most valuable - add if available
                if syllabus:
                    parts.append(f"Summary: {syllabus[:500]}")  # Limit syllabus to 500 chars

                # Fallback fields when syllabus is not available
                if not syllabus:
                    if posture:
                        parts.append(f"Posture: {posture[:300]}")  # Limit to 300 chars
                    if procedural_history:
                        parts.append(f"History: {procedural_history[:300]}")  # Limit to 300 chars

                text = "\n".join(parts) if parts else case_name
                doc_texts.append(text)

            logger.info(f"Reranking {len(documents)} results with query: {query[:80]}...")

            # Call Cohere rerank API
            response = self.client.rerank(
                model=self.model,
                query=query,
                documents=doc_texts,
                top_n=top_n,
                return_documents=return_documents
            )

            # Extract reranked results
            reranked = []
            for result in response.results:
                original_doc = documents[result.index]
                # Add relevance score to the document
                reranked_doc = {**original_doc, "rerank_score": result.relevance_score}
                reranked.append(reranked_doc)

            logger.info(f"Reranked to top {len(reranked)} results. Score range: "
                       f"{reranked[0]['rerank_score']:.3f} - {reranked[-1]['rerank_score']:.3f}")

            return reranked

        except Exception as e:
            logger.error(f"Reranking failed: {e}. Returning original top {top_n} results.")
            return documents[:top_n]

    def is_available(self) -> bool:
        """Check if reranker is available for use."""
        return self.client is not None
