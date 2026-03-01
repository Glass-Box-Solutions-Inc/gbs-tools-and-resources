"""
CourtListener API client for searching case law.
Enhanced with error handling, retries, and pagination support.

Reference: https://www.courtlistener.com/help/api/rest/search/
"""
import os
import time
import logging
import requests
from typing import Dict, List, Optional, Any, Generator
from urllib.parse import urlencode, urlparse, parse_qs
from dotenv import load_dotenv

load_dotenv(override=True)  # Force reload to pick up .env changes

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("courtlistener")


# =============================================================================
# CUSTOM EXCEPTIONS
# =============================================================================

class CourtListenerError(Exception):
    """Base exception for CourtListener API errors."""
    pass


class AuthenticationError(CourtListenerError):
    """Raised when API token is invalid or missing."""
    pass


class RateLimitError(CourtListenerError):
    """Raised when API rate limit is exceeded."""
    def __init__(self, message: str, retry_after: int = None):
        super().__init__(message)
        self.retry_after = retry_after


class InvalidQueryError(CourtListenerError):
    """Raised when the search query is malformed."""
    def __init__(self, message: str, field: str = None, details: dict = None):
        super().__init__(message)
        self.field = field
        self.details = details or {}


class ServerError(CourtListenerError):
    """Raised when CourtListener server returns 5xx error."""
    pass


class NetworkError(CourtListenerError):
    """Raised when network connection fails."""
    pass


# =============================================================================
# CONSTANTS
# =============================================================================

COURTLISTENER_API_BASE = "https://www.courtlistener.com/api/rest/v4"

# Rate limiting / retry settings
MAX_RETRIES = 3
RETRY_BACKOFF_FACTOR = 2
DEFAULT_RETRY_AFTER = 60


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _extract_cursor_from_url(url: str) -> Optional[str]:
    """Extract cursor parameter from a pagination URL."""
    if not url:
        return None
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    cursor_list = params.get("cursor", [])
    return cursor_list[0] if cursor_list else None


def _handle_error_response(response: requests.Response) -> None:
    """Parse error response and raise appropriate exception."""
    status_code = response.status_code
    
    try:
        error_data = response.json()
    except:
        error_data = {"detail": response.text}
    
    # Authentication errors
    if status_code == 401:
        raise AuthenticationError(
            "Invalid or missing API token. Please check your COURTLISTENER_API_KEY."
        )
    
    if status_code == 403:
        raise AuthenticationError(
            f"Access forbidden. Your API token may not have permission. Details: {error_data}"
        )
    
    # Rate limiting
    if status_code == 429:
        retry_after = response.headers.get("Retry-After")
        retry_seconds = int(retry_after) if retry_after else DEFAULT_RETRY_AFTER
        raise RateLimitError(
            f"Rate limit exceeded. Retry after {retry_seconds} seconds.",
            retry_after=retry_seconds
        )
    
    # Bad request / Invalid query
    if status_code == 400:
        if isinstance(error_data, dict):
            if "order_by" in error_data:
                raise InvalidQueryError(
                    f"Invalid order_by value: {error_data['order_by']}",
                    field="order_by",
                    details=error_data
                )
            if "q" in error_data:
                raise InvalidQueryError(
                    f"Invalid query syntax: {error_data['q']}",
                    field="query",
                    details=error_data
                )
            if "court" in error_data:
                raise InvalidQueryError(
                    f"Invalid court ID: {error_data['court']}",
                    field="court",
                    details=error_data
                )
        
        raise InvalidQueryError(
            f"Bad request: {error_data}",
            details=error_data
        )
    
    # Not found
    if status_code == 404:
        raise CourtListenerError(f"Resource not found: {error_data}")
    
    # Server errors
    if 500 <= status_code < 600:
        raise ServerError(
            f"CourtListener server error ({status_code}): {error_data}. Please try again later."
        )
    
    # Generic error
    raise CourtListenerError(f"API error ({status_code}): {error_data}")


# =============================================================================
# MAIN CLIENT CLASS
# =============================================================================

class CourtListenerClient:
    """
    Client for interacting with CourtListener API.
    
    Features:
    - Keyword and semantic search
    - Automatic retry with exponential backoff
    - Rate limit handling
    - Pagination support
    - Full opinion text retrieval
    """
    
    def __init__(self):
        """Initialize the CourtListener API client."""
        # Check both possible env var names
        self.api_key = os.getenv("COURTLISTENER_API_KEY") or os.getenv("COURTLISTENER_TOKEN")
        if not self.api_key:
            raise ValueError("COURTLISTENER_API_KEY or COURTLISTENER_TOKEN environment variable is required")
        
        # Store raw key for endpoints that need "Token " prefix
        self.raw_api_key = self.api_key.replace("Token ", "") if self.api_key.startswith("Token ") else self.api_key
        
        # Search endpoint works without "Token " prefix
        self.headers = {
            "Authorization": self.api_key if self.api_key.startswith("Token ") else self.api_key,
            "Content-Type": "application/json"
        }
        
        # Headers for endpoints requiring "Token " prefix (opinions, clusters)
        self.headers_with_token = {
            "Authorization": f"Token {self.raw_api_key}",
            "Content-Type": "application/json"
        }
    
    def search(
        self,
        query: str,
        search_type: str = "keyword",
        court: str = "",
        filed_after: str = "",
        filed_before: str = "",
        status: str = "published",
        order_by: str = "score desc",
        cited_gt: Optional[int] = None,
        cited_lt: Optional[int] = None,
        page_size: int = 10,
        cursor: Optional[str] = None,
        highlight: bool = True,
        retry_on_rate_limit: bool = True
    ) -> Dict[str, Any]:
        """
        Search CourtListener for case law with error handling and pagination.
        
        Args:
            query: Search query (keyword syntax or natural language for semantic)
            search_type: 'keyword' or 'semantic'
            court: Space-separated court_id values to filter
            filed_after: Date string for minimum date (MM/DD/YYYY or YYYY-MM-DD)
            filed_before: Date string for maximum date (MM/DD/YYYY or YYYY-MM-DD)
            status: 'published', 'unpublished', or 'all'
            order_by: Sort order - 'score desc', 'dateFiled desc', 'citeCount desc'
            cited_gt: Minimum citation count (added to query as fielded search)
            cited_lt: Maximum citation count (added to query as fielded search)
            page_size: Number of results per page (1-20)
            cursor: Pagination cursor from previous response
            highlight: Whether to highlight matches in snippets
            retry_on_rate_limit: Whether to automatically retry on rate limit
            
        Returns:
            dict with 'success', 'count', 'results', 'pagination', and 'meta'
            
        Raises:
            AuthenticationError: Invalid or missing API token
            RateLimitError: Rate limit exceeded (if retry_on_rate_limit=False)
            InvalidQueryError: Malformed query or invalid parameters
            ServerError: CourtListener server error
            NetworkError: Connection failed
        """
        # Validate inputs
        if not query or not query.strip():
            raise InvalidQueryError("Query cannot be empty", field="query")
        
        if search_type not in ("keyword", "semantic"):
            raise InvalidQueryError(
                f"Invalid search_type: {search_type}. Must be 'keyword' or 'semantic'",
                field="search_type"
            )
        
        # Add citation count filters to query if specified (for keyword search)
        effective_query = query
        if search_type == "keyword":
            if cited_gt is not None:
                effective_query = f"({effective_query}) AND citeCount:[{cited_gt} TO *]"
            if cited_lt is not None:
                effective_query = f"({effective_query}) AND citeCount:[* TO {cited_lt}]"
        
        # Build parameters
        params = self._build_params(
            query=effective_query,
            search_type=search_type,
            court=court,
            filed_after=filed_after,
            filed_before=filed_before,
            status=status,
            order_by=order_by,
            page_size=page_size,
            cursor=cursor,
            highlight=highlight
        )
        
        # Build full URL for display
        query_string = urlencode(params)
        full_url = f"{COURTLISTENER_API_BASE}/search/?{query_string}"
        
        # Retry loop for rate limiting and transient errors
        last_exception = None
        for attempt in range(MAX_RETRIES):
            try:
                logger.info(f"Searching CourtListener (attempt {attempt + 1}/{MAX_RETRIES}): {effective_query[:80]}...")
                
                response = requests.get(
                    f"{COURTLISTENER_API_BASE}/search/",
                    params=params,
                    headers=self.headers,
                    timeout=30
                )
                
                # Success
                if response.status_code == 200:
                    data = response.json()
                    return self._format_response(data, search_type, query, full_url)
                
                # Handle error responses
                _handle_error_response(response)
                
            except RateLimitError as e:
                last_exception = e
                if retry_on_rate_limit and attempt < MAX_RETRIES - 1:
                    wait_time = e.retry_after or (DEFAULT_RETRY_AFTER * (RETRY_BACKOFF_FACTOR ** attempt))
                    logger.warning(f"Rate limited. Waiting {wait_time} seconds before retry...")
                    time.sleep(wait_time)
                    continue
                raise
                
            except ServerError as e:
                last_exception = e
                if attempt < MAX_RETRIES - 1:
                    wait_time = RETRY_BACKOFF_FACTOR ** attempt * 5
                    logger.warning(f"Server error. Waiting {wait_time} seconds before retry...")
                    time.sleep(wait_time)
                    continue
                raise
                
            except requests.exceptions.Timeout:
                last_exception = NetworkError("Request timed out after 30 seconds")
                if attempt < MAX_RETRIES - 1:
                    logger.warning("Request timed out. Retrying...")
                    continue
                raise last_exception
                
            except requests.exceptions.ConnectionError as e:
                last_exception = NetworkError(f"Failed to connect to CourtListener: {e}")
                if attempt < MAX_RETRIES - 1:
                    wait_time = RETRY_BACKOFF_FACTOR ** attempt * 2
                    logger.warning(f"Connection error. Waiting {wait_time} seconds before retry...")
                    time.sleep(wait_time)
                    continue
                raise last_exception
                
            except requests.exceptions.RequestException as e:
                raise NetworkError(f"Network error: {e}")
        
        if last_exception:
            raise last_exception
        raise CourtListenerError("Unknown error occurred")
    
    def _build_params(
        self,
        query: str,
        search_type: str,
        court: str = "",
        filed_after: str = "",
        filed_before: str = "",
        status: str = "published",
        order_by: str = "score desc",
        page_size: int = 10,
        cursor: Optional[str] = None,
        highlight: bool = True
    ) -> Dict[str, Any]:
        """Build query parameters for the API request."""
        params = {
            "q": query,
            "type": "o",  # opinions
            "page_size": min(max(page_size, 1), 20),
            "order_by": order_by,
        }
        
        # Semantic search flag
        if search_type == "semantic":
            params["semantic"] = "true"
        
        # Highlighting
        if highlight:
            params["highlight"] = "on"
        
        # Court filter
        if court:
            params["court"] = court
        
        # Date filters
        if filed_after:
            params["filed_after"] = filed_after
        if filed_before:
            params["filed_before"] = filed_before
        
        # Status filter
        if status == "published":
            params["stat_Published"] = "on"
        elif status == "unpublished":
            params["stat_Unpublished"] = "on"
        elif status == "all":
            params["stat_Published"] = "on"
            params["stat_Unpublished"] = "on"
        
        # Pagination cursor
        if cursor:
            params["cursor"] = cursor
        
        return params
    
    def _format_response(
        self,
        data: dict,
        search_type: str,
        query: str,
        full_url: str
    ) -> Dict[str, Any]:
        """Format API response into standardized output."""
        results = []
        for item in data.get("results", []):
            # Extract first opinion's snippet and download_url for top-level access
            opinions_data = item.get("opinions", [])
            first_opinion = opinions_data[0] if opinions_data else {}
            
            # Extract relevance scores from meta
            meta_data = item.get("meta", {})
            score_data = meta_data.get("score", {})
            
            result = {
                "case_name": item.get("caseName"),
                "case_name_full": item.get("caseNameFull"),
                "citation": item.get("citation", []),
                "court": item.get("court"),
                "court_id": item.get("court_id"),
                "date_filed": item.get("dateFiled"),
                "date_argued": item.get("dateArgued"),
                "docket_number": item.get("docketNumber"),
                "cite_count": item.get("citeCount", 0),
                "status": item.get("status"),
                "judge": item.get("judge"),
                "url": f"https://www.courtlistener.com{item.get('absolute_url', '')}",
                "absolute_url": item.get("absolute_url", ""),
                "cluster_id": item.get("cluster_id"),
                "docket_id": item.get("docket_id"),
                "syllabus": item.get("syllabus"),
                "suit_nature": item.get("suitNature"),
                "procedural_history": item.get("procedural_history"),
                "posture": item.get("posture"),
                "panel_names": item.get("panel_names", []),
                "court_citation_string": item.get("court_citation_string", ""),
                # Top-level snippet and download_url for easy access
                "snippet": first_opinion.get("snippet", ""),
                "download_url": first_opinion.get("download_url", ""),
                # Relevance scores
                "score_bm25": score_data.get("bm25"),
                "score_semantic": score_data.get("semantic"),
                "meta": meta_data,
                "opinions": []
            }
            
            # Extract all opinion details
            for opinion in opinions_data:
                result["opinions"].append({
                    "id": opinion.get("id"),
                    "type": opinion.get("type"),
                    "snippet": opinion.get("snippet"),
                    "author_id": opinion.get("author_id"),
                    "per_curiam": opinion.get("per_curiam"),
                    "download_url": opinion.get("download_url"),
                    "local_path": opinion.get("local_path"),
                    "cites": opinion.get("cites", []),
                    "joined_by_ids": opinion.get("joined_by_ids", [])
                })
            
            results.append(result)
        
        # Extract pagination cursors
        next_cursor = _extract_cursor_from_url(data.get("next"))
        prev_cursor = _extract_cursor_from_url(data.get("previous"))
        
        return {
            "success": True,
            "count": data.get("count", 0),
            "results": results,
            "pagination": {
                "next_cursor": next_cursor,
                "prev_cursor": prev_cursor,
                "next_url": data.get("next"),
                "prev_url": data.get("previous"),
                "has_more": next_cursor is not None
            },
            "_api_url": full_url,
            "_search_type": "Semantic" if search_type == "semantic" else "Keyword",
            "meta": {
                "search_type": search_type,
                "query": query,
                "results_returned": len(results)
            }
        }
    
    # =========================================================================
    # LEGACY METHODS (for backward compatibility)
    # =========================================================================
    
    def search_filtered(
        self,
        query: str,
        court: str = "",
        date_filed_min: str = "",
        date_filed_max: str = "",
        page_size: int = 10,
        order_by: str = "score desc",
        semantic: bool = False
    ) -> Dict:
        """
        Legacy search method for backward compatibility.
        Converts to new search() method format.
        """
        try:
            result = self.search(
                query=query,
                search_type="semantic" if semantic else "keyword",
                court=court,
                filed_after=date_filed_min,
                filed_before=date_filed_max,
                page_size=page_size,
                order_by=order_by
            )
            return result
        except CourtListenerError as e:
            # Convert exceptions to error dict for backward compatibility
            return {
                "error": str(e),
                "results": [],
                "count": 0,
                "_api_url": ""
            }
    
    def format_search_results(self, results_data: Dict) -> List[Dict]:
        """
        Format search results for display (legacy compatibility).
        New search() method already returns formatted results.
        """
        if "error" in results_data:
            return []
        
        # If already formatted (from new search method)
        if results_data.get("success"):
            return results_data.get("results", [])
        
        # Legacy format conversion
        formatted_results = []
        for result in results_data.get("results", []):
            opinions = result.get("opinions", [])
            first_opinion = opinions[0] if opinions else {}
            
            formatted_result = {
                "case_name": result.get("caseName", result.get("case_name", "N/A")),
                "case_name_full": result.get("caseNameFull", result.get("case_name_full", "")),
                "court": result.get("court", "N/A"),
                "court_id": result.get("court_id", ""),
                "court_citation_string": result.get("court_citation_string", ""),
                "date_filed": result.get("dateFiled", result.get("date_filed")),
                "date_argued": result.get("dateArgued", result.get("date_argued")),
                "citation": result.get("citation", []),
                "docket_number": result.get("docketNumber", result.get("docket_number", "N/A")),
                "absolute_url": result.get("absolute_url", ""),
                "snippet": first_opinion.get("snippet", result.get("snippet", "")),
                "cite_count": result.get("citeCount", result.get("cite_count", 0)),
                "judge": result.get("judge", ""),
                "cluster_id": result.get("cluster_id"),
                "status": result.get("status", ""),
                "suit_nature": result.get("suitNature", result.get("suit_nature", "")),
                "download_url": first_opinion.get("download_url", result.get("download_url", "")),
                "url": result.get("url", ""),
            }
            formatted_results.append(formatted_result)
        
        return formatted_results
    
    # =========================================================================
    # PAGINATION HELPERS
    # =========================================================================
    
    def get_next_page(self, previous_response: Dict[str, Any], **kwargs) -> Optional[Dict[str, Any]]:
        """
        Fetch the next page of results from a previous response.
        
        Args:
            previous_response: Response dict from a previous search call
            **kwargs: Override any parameters from original search
            
        Returns:
            Next page of results, or None if no more pages
        """
        pagination = previous_response.get("pagination", {})
        next_cursor = pagination.get("next_cursor")
        
        if not next_cursor:
            return None
        
        meta = previous_response.get("meta", {})
        
        return self.search(
            query=kwargs.get("query", meta.get("query", "")),
            search_type=kwargs.get("search_type", meta.get("search_type", "keyword")),
            cursor=next_cursor,
            **{k: v for k, v in kwargs.items() if k not in ["query", "search_type", "cursor"]}
        )
    
    def search_all_pages(
        self,
        query: str,
        search_type: str,
        max_results: int = 100,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Fetch multiple pages of results up to max_results.
        
        Args:
            query: Search query
            search_type: 'keyword' or 'semantic'
            max_results: Maximum total results to fetch (default 100)
            **kwargs: Additional arguments passed to search
            
        Returns:
            Combined results dict with all fetched results
        """
        all_results = []
        cursor = None
        total_count = 0
        page_size = min(kwargs.get("page_size", 20), 20)
        
        while len(all_results) < max_results:
            remaining = max_results - len(all_results)
            current_page_size = min(page_size, remaining)
            
            response = self.search(
                query=query,
                search_type=search_type,
                cursor=cursor,
                page_size=current_page_size,
                **{k: v for k, v in kwargs.items() if k != "page_size"}
            )
            
            if not response.get("success"):
                break
                
            total_count = response.get("count", 0)
            all_results.extend(response.get("results", []))
            
            cursor = response.get("pagination", {}).get("next_cursor")
            if not cursor:
                break
                
            logger.info(f"Fetched {len(all_results)}/{min(max_results, total_count)} results...")
        
        return {
            "success": True,
            "count": total_count,
            "results": all_results,
            "meta": {
                "search_type": search_type,
                "query": query,
                "results_returned": len(all_results),
                "max_results_requested": max_results,
                "all_results_fetched": len(all_results) >= total_count or len(all_results) >= max_results
            }
        }
    
    def iterate_results(
        self,
        query: str,
        search_type: str,
        **kwargs
    ) -> Generator[Dict, None, None]:
        """
        Generator that yields all results across pages.
        
        Args:
            query: Search query
            search_type: 'keyword' or 'semantic'
            **kwargs: Additional arguments passed to search
            
        Yields:
            Individual case result dicts
        """
        cursor = None
        
        while True:
            response = self.search(
                query=query,
                search_type=search_type,
                cursor=cursor,
                page_size=20,
                **kwargs
            )
            
            if not response.get("success"):
                break
            
            for case in response.get("results", []):
                yield case
            
            cursor = response.get("pagination", {}).get("next_cursor")
            if not cursor:
                break
    
    # =========================================================================
    # FETCH FULL CONTENT
    # =========================================================================
    
    def get_opinion_full_text(self, opinion_id: int) -> Dict[str, Any]:
        """
        Fetch the full text of an opinion by ID.
        
        Args:
            opinion_id: The opinion ID from search results
            
        Returns:
            dict with full opinion text and metadata
        """
        try:
            response = requests.get(
                f"{COURTLISTENER_API_BASE}/opinions/{opinion_id}/",
                headers=self.headers_with_token,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                return {
                    "success": True,
                    "opinion_id": opinion_id,
                    "plain_text": data.get("plain_text"),
                    "html": data.get("html"),
                    "html_with_citations": data.get("html_with_citations"),
                    "html_lawbox": data.get("html_lawbox"),
                    "html_columbia": data.get("html_columbia"),
                    "xml_harvard": data.get("xml_harvard"),
                    "type": data.get("type"),
                    "author": data.get("author"),
                    "joined_by": data.get("joined_by"),
                    "per_curiam": data.get("per_curiam"),
                    "cluster": data.get("cluster"),
                    "download_url": data.get("download_url")
                }
            
            _handle_error_response(response)
            
        except requests.exceptions.RequestException as e:
            raise NetworkError(f"Failed to fetch opinion {opinion_id}: {e}")
    
    def get_cluster_details(self, cluster_id: int) -> Dict[str, Any]:
        """
        Fetch full cluster (case) details by ID.
        
        Args:
            cluster_id: The cluster_id from search results
            
        Returns:
            dict with full case metadata and all opinions
        """
        try:
            response = requests.get(
                f"{COURTLISTENER_API_BASE}/clusters/{cluster_id}/",
                headers=self.headers_with_token,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                return {
                    "success": True,
                    "cluster_id": cluster_id,
                    "case_name": data.get("case_name"),
                    "case_name_full": data.get("case_name_full"),
                    "date_filed": data.get("date_filed"),
                    "docket": data.get("docket"),
                    "citations": data.get("citations"),
                    "judges": data.get("judges"),
                    "syllabus": data.get("syllabus"),
                    "procedural_history": data.get("procedural_history"),
                    "posture": data.get("posture"),
                    "sub_opinions": data.get("sub_opinions"),
                    "panel": data.get("panel"),
                    "source": data.get("source"),
                    "precedential_status": data.get("precedential_status")
                }
            
            _handle_error_response(response)
            
        except requests.exceptions.RequestException as e:
            raise NetworkError(f"Failed to fetch cluster {cluster_id}: {e}")
    
    def get_opinion_text_by_cluster(self, cluster_id: int) -> Dict[str, Any]:
        """
        Fetch the full text of opinions for a given cluster ID.
        
        Tries multiple text fields in priority order:
        plain_text, html_with_citations, html, html_lawbox, html_columbia, xml_harvard
        
        Args:
            cluster_id: The cluster_id from search results
            
        Returns:
            dict with opinion text and metadata
        """
        FIELDS_PRIORITY = [
            "plain_text",
            "html_with_citations",
            "html",
            "html_lawbox",
            "html_columbia",
            "html_anon_2020",
            "xml_harvard",
        ]
        
        try:
            # Fetch opinions for this cluster
            params = {
                "cluster": cluster_id,
                "fields": ",".join([
                    "id",
                    "absolute_url",
                    "type",
                    "plain_text",
                    "html_with_citations",
                    "html",
                    "html_lawbox",
                    "html_columbia",
                    "html_anon_2020",
                    "xml_harvard",
                ])
            }
            
            # Use same header format as search (which works)
            response = requests.get(
                f"{COURTLISTENER_API_BASE}/opinions/",
                params=params,
                headers=self.headers_with_token,  # Opinions endpoint needs Token prefix
                timeout=60  # Longer timeout for full text
            )
            
            if response.status_code != 200:
                _handle_error_response(response)
            
            data = response.json()
            results = data.get("results", [])
            
            if not results:
                return {
                    "success": False,
                    "error": "No opinions found for this cluster",
                    "cluster_id": cluster_id
                }
            
            # Find the first opinion with text
            for opinion in results:
                for field in FIELDS_PRIORITY:
                    text = opinion.get(field)
                    if isinstance(text, str) and text.strip():
                        return {
                            "success": True,
                            "cluster_id": cluster_id,
                            "opinion_id": opinion.get("id"),
                            "absolute_url": opinion.get("absolute_url"),
                            "type": opinion.get("type"),
                            "text_field": field,
                            "text": text.strip(),
                            "is_html": field != "plain_text"
                        }
            
            return {
                "success": False,
                "error": "No text content found in any opinion",
                "cluster_id": cluster_id,
                "opinion_count": len(results)
            }
            
        except requests.exceptions.RequestException as e:
            raise NetworkError(f"Failed to fetch opinion text for cluster {cluster_id}: {e}")
