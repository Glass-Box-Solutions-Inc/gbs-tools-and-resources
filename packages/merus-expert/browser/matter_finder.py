"""
Matter Finder - Search and select matters in MerusCase
"""

import logging
import re
import asyncio
from typing import Optional, List, Dict, Any
from datetime import datetime
from difflib import SequenceMatcher

from playwright.async_api import Page

from browser.element_handler import ElementHandler
from models.billing import (
    MatterReference,
    MatterSearchResult,
    MatterSelectionMethod,
)

logger = logging.getLogger(__name__)


class MatterFinder:
    """
    Find and navigate to matters in MerusCase.

    Supports multiple selection methods:
    - Search by client/matter name (fuzzy matching)
    - Direct URL navigation
    - Direct matter ID
    - Recent matters list
    """

    def __init__(self, page: Page, base_url: str = "https://meruscase.com"):
        """
        Initialize matter finder.

        Args:
            page: Playwright page object
            base_url: MerusCase base URL
        """
        self.page = page
        self.base_url = base_url.rstrip("/")
        self.element_handler = ElementHandler(page)

        # Cache for recent matters
        self._recent_matters: List[MatterSearchResult] = []
        self._last_search_results: List[MatterSearchResult] = []

    async def search_matters(
        self,
        query: str,
        limit: int = 10
    ) -> List[MatterSearchResult]:
        """
        Search matters by client/case name.

        Args:
            query: Search query
            limit: Maximum results to return

        Returns:
            List of matching matters with relevance scores
        """
        logger.info(f"Searching matters for: {query}")

        results = []

        try:
            # Navigate to matters list/search
            await self.page.goto(f"{self.base_url}/matters", wait_until="networkidle")
            await asyncio.sleep(1)

            # Find search input
            search_input = await self.element_handler.find_input(
                field_name="search",
                placeholder="Search",
                label="Search"
            )

            if search_input:
                # Clear and type search query
                await search_input.fill("")
                await search_input.fill(query)
                await asyncio.sleep(1)  # Wait for search results

                # Try pressing Enter or wait for auto-search
                try:
                    await search_input.press("Enter")
                    await asyncio.sleep(2)
                except Exception:
                    pass

            # Extract search results from page
            results = await self._extract_search_results(query, limit)

            # Cache results
            self._last_search_results = results

            logger.info(f"Found {len(results)} matters matching '{query}'")

        except Exception as e:
            logger.error(f"Matter search failed: {e}")

        return results

    async def _extract_search_results(
        self,
        query: str,
        limit: int
    ) -> List[MatterSearchResult]:
        """
        Extract matter search results from current page.

        Args:
            query: Original search query (for scoring)
            limit: Maximum results

        Returns:
            List of MatterSearchResult
        """
        results = []

        try:
            # Common patterns for matter list rows
            row_selectors = [
                "table tbody tr",
                ".matter-row",
                ".case-item",
                "[data-matter-id]",
                ".search-result",
            ]

            rows = None
            for selector in row_selectors:
                rows = self.page.locator(selector)
                count = await rows.count()
                if count > 0:
                    logger.debug(f"Found {count} rows with selector: {selector}")
                    break

            if not rows or await rows.count() == 0:
                logger.warning("No matter rows found on page")
                return results

            count = min(await rows.count(), limit)

            for i in range(count):
                try:
                    row = rows.nth(i)

                    # Extract matter info from row
                    matter_data = await self._extract_matter_from_row(row)

                    if matter_data:
                        # Calculate fuzzy match score
                        score = self._calculate_match_score(
                            query,
                            matter_data.get("matter_name", "") + " " +
                            matter_data.get("client_name", "")
                        )

                        result = MatterSearchResult(
                            matter_id=matter_data.get("matter_id", ""),
                            matter_name=matter_data.get("matter_name", ""),
                            client_name=matter_data.get("client_name", ""),
                            case_type=matter_data.get("case_type"),
                            status=matter_data.get("status"),
                            meruscase_url=matter_data.get("url", ""),
                            match_score=score,
                        )
                        results.append(result)

                except Exception as e:
                    logger.debug(f"Failed to extract row {i}: {e}")
                    continue

            # Sort by match score
            results.sort(key=lambda x: x.match_score, reverse=True)

        except Exception as e:
            logger.error(f"Failed to extract search results: {e}")

        return results

    async def _extract_matter_from_row(self, row) -> Optional[Dict[str, Any]]:
        """
        Extract matter information from a table row.

        Args:
            row: Playwright locator for row element

        Returns:
            Dict with matter info or None
        """
        try:
            # Try to find a link to matter details
            link = row.locator("a[href*='matter'], a[href*='case']").first
            href = await link.get_attribute("href") if await link.count() > 0 else None

            # Extract matter ID from URL or data attribute
            matter_id = ""
            if href:
                match = re.search(r'/(?:matters?|cases?)/(\d+)', href)
                if match:
                    matter_id = match.group(1)
            else:
                matter_id = await row.get_attribute("data-matter-id") or ""

            # Get text content - try columns first, then full row
            cells = row.locator("td")
            cell_count = await cells.count()

            if cell_count >= 2:
                # Table format: typically [matter_name, client_name, type, status, ...]
                matter_name = await cells.nth(0).text_content() or ""
                client_name = await cells.nth(1).text_content() or "" if cell_count > 1 else ""
                case_type = await cells.nth(2).text_content() or "" if cell_count > 2 else None
                status = await cells.nth(3).text_content() or "" if cell_count > 3 else None
            else:
                # Non-table format
                text = await row.text_content() or ""
                matter_name = text.strip()[:100]
                client_name = ""
                case_type = None
                status = None

            # Build full URL
            url = href if href and href.startswith("http") else f"{self.base_url}{href}" if href else ""

            return {
                "matter_id": matter_id.strip(),
                "matter_name": matter_name.strip(),
                "client_name": client_name.strip(),
                "case_type": case_type.strip() if case_type else None,
                "status": status.strip() if status else None,
                "url": url,
            }

        except Exception as e:
            logger.debug(f"Failed to extract matter from row: {e}")
            return None

    def _calculate_match_score(self, query: str, text: str) -> float:
        """
        Calculate fuzzy match score between query and text.

        Args:
            query: Search query
            text: Text to match against

        Returns:
            Score between 0.0 and 1.0
        """
        query_lower = query.lower().strip()
        text_lower = text.lower().strip()

        # Exact match
        if query_lower == text_lower:
            return 1.0

        # Contains match
        if query_lower in text_lower:
            return 0.95

        # Word match
        query_words = set(query_lower.split())
        text_words = set(text_lower.split())
        word_overlap = len(query_words & text_words) / max(len(query_words), 1)
        if word_overlap > 0:
            return 0.7 + (word_overlap * 0.25)

        # Sequence matching
        return SequenceMatcher(None, query_lower, text_lower).ratio()

    async def get_recent_matters(self, limit: int = 10) -> List[MatterSearchResult]:
        """
        Get list of recently accessed matters.

        Args:
            limit: Maximum results

        Returns:
            List of recent matters
        """
        logger.info("Fetching recent matters...")

        results = []

        try:
            # Navigate to matters/dashboard
            await self.page.goto(f"{self.base_url}/matters", wait_until="networkidle")
            await asyncio.sleep(1)

            # Try to click "Recent" tab/filter if available
            recent_tab = await self.element_handler.find_link(
                text="Recent",
                href="recent"
            )
            if recent_tab:
                await recent_tab.click()
                await asyncio.sleep(1)

            # Extract matters from list
            results = await self._extract_search_results("", limit)

            # Mark as recent (high score)
            for i, result in enumerate(results):
                result.match_score = 1.0 - (i * 0.05)  # Decreasing score for order

            self._recent_matters = results
            logger.info(f"Found {len(results)} recent matters")

        except Exception as e:
            logger.error(f"Failed to get recent matters: {e}")

        return results

    async def resolve_from_url(self, url: str) -> Optional[MatterReference]:
        """
        Resolve matter information from MerusCase URL.

        Args:
            url: MerusCase matter URL

        Returns:
            MatterReference with resolved info or None
        """
        logger.info(f"Resolving matter from URL: {url}")

        # Extract matter ID from URL
        match = re.search(r'/(?:matters?|cases?)/(\d+)', url)
        if not match:
            logger.error(f"Could not extract matter ID from URL: {url}")
            return None

        matter_id = match.group(1)

        try:
            # Navigate to the matter page
            await self.page.goto(url, wait_until="networkidle")
            await asyncio.sleep(1)

            # Extract matter info from page
            matter_name = await self._get_matter_name_from_page()
            client_name = await self._get_client_name_from_page()

            reference = MatterReference(
                method=MatterSelectionMethod.URL,
                value=url,
                resolved_id=matter_id,
                resolved_name=matter_name,
                meruscase_url=url,
                client_name=client_name,
            )

            logger.info(f"Resolved matter: {matter_name} (ID: {matter_id})")
            return reference

        except Exception as e:
            logger.error(f"Failed to resolve matter from URL: {e}")
            return None

    async def resolve_from_id(self, matter_id: str) -> Optional[MatterReference]:
        """
        Resolve matter information from ID.

        Args:
            matter_id: MerusCase matter ID

        Returns:
            MatterReference with resolved info or None
        """
        logger.info(f"Resolving matter from ID: {matter_id}")

        # Construct URL and resolve
        url = f"{self.base_url}/matters/{matter_id}"
        reference = await self.resolve_from_url(url)

        if reference:
            reference.method = MatterSelectionMethod.DIRECT_ID
            reference.value = matter_id

        return reference

    async def _get_matter_name_from_page(self) -> str:
        """Extract matter name from current page"""
        selectors = [
            "h1",
            ".matter-name",
            ".case-title",
            "[data-field='name']",
            ".page-header h1",
        ]

        for selector in selectors:
            try:
                element = self.page.locator(selector).first
                if await element.is_visible():
                    text = await element.text_content()
                    if text and len(text.strip()) > 0:
                        return text.strip()
            except Exception:
                continue

        # Fallback to page title
        title = await self.page.title()
        return title.split("|")[0].strip() if title else "Unknown Matter"

    async def _get_client_name_from_page(self) -> str:
        """Extract client name from current page"""
        selectors = [
            ".client-name",
            "[data-field='client']",
            ".primary-party",
            "dd:has-text('Client')",
        ]

        for selector in selectors:
            try:
                element = self.page.locator(selector).first
                if await element.is_visible():
                    text = await element.text_content()
                    if text and len(text.strip()) > 0:
                        return text.strip()
            except Exception:
                continue

        return ""

    async def navigate_to_matter(self, reference: MatterReference) -> bool:
        """
        Navigate to a matter page.

        Args:
            reference: MatterReference with matter info

        Returns:
            True if navigation successful
        """
        url = reference.meruscase_url
        if not url and reference.resolved_id:
            url = f"{self.base_url}/matters/{reference.resolved_id}"
        if not url:
            logger.error("No URL or ID available for navigation")
            return False

        try:
            await self.page.goto(url, wait_until="networkidle")
            await asyncio.sleep(1)

            # Verify we're on a matter page
            current_url = self.page.url
            if "/matters/" in current_url or "/cases/" in current_url:
                logger.info(f"Navigated to matter: {url}")
                return True

            logger.warning(f"Navigation may have failed - current URL: {current_url}")
            return True  # Continue anyway

        except Exception as e:
            logger.error(f"Navigation failed: {e}")
            return False

    def auto_detect_selection_method(self, user_input: str) -> MatterReference:
        """
        Auto-detect selection method from user input.

        Args:
            user_input: Raw user input

        Returns:
            MatterReference with detected method
        """
        text = user_input.strip()

        # Check for URL
        if "meruscase.com" in text.lower() or text.startswith("http"):
            return MatterReference(
                method=MatterSelectionMethod.URL,
                value=text
            )

        # Check for numeric ID
        if text.isdigit():
            return MatterReference(
                method=MatterSelectionMethod.DIRECT_ID,
                value=text
            )

        # Check for "recent" keyword
        if text.lower() in ["recent", "recent matters", "last"]:
            return MatterReference(
                method=MatterSelectionMethod.RECENT,
                value=""
            )

        # Default to search
        return MatterReference(
            method=MatterSelectionMethod.SEARCH,
            value=text
        )

    async def resolve_matter(self, reference: MatterReference) -> Optional[MatterReference]:
        """
        Resolve matter based on reference method.

        Args:
            reference: MatterReference with method and value

        Returns:
            Resolved MatterReference or None
        """
        if reference.method == MatterSelectionMethod.URL:
            return await self.resolve_from_url(reference.value)

        elif reference.method == MatterSelectionMethod.DIRECT_ID:
            return await self.resolve_from_id(reference.value)

        elif reference.method == MatterSelectionMethod.SEARCH:
            results = await self.search_matters(reference.value, limit=1)
            if results:
                best_match = results[0]
                return MatterReference(
                    method=MatterSelectionMethod.SEARCH,
                    value=reference.value,
                    resolved_id=best_match.matter_id,
                    resolved_name=best_match.matter_name,
                    meruscase_url=best_match.meruscase_url,
                    client_name=best_match.client_name,
                )
            return None

        elif reference.method == MatterSelectionMethod.RECENT:
            results = await self.get_recent_matters(limit=1)
            if results:
                recent = results[0]
                return MatterReference(
                    method=MatterSelectionMethod.RECENT,
                    value="",
                    resolved_id=recent.matter_id,
                    resolved_name=recent.matter_name,
                    meruscase_url=recent.meruscase_url,
                    client_name=recent.client_name,
                )
            return None

        return None
