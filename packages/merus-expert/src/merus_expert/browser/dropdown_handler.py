"""
Dropdown Handler - Intelligent dropdown selection with fuzzy matching
"""

import logging
from typing import Optional, List, Dict, Tuple
from difflib import SequenceMatcher
from playwright.async_api import Page, Locator

logger = logging.getLogger(__name__)


class DropdownHandler:
    """
    Handles dropdown interactions with fuzzy matching.

    Features:
    - Exact matching
    - Fuzzy text matching
    - Value vs. text matching
    - Search/filter support for searchable dropdowns
    """

    def __init__(self, page: Page, min_similarity: float = 0.8):
        """
        Initialize dropdown handler.

        Args:
            page: Playwright page object
            min_similarity: Minimum similarity score for fuzzy matching (0.0-1.0)
        """
        self.page = page
        self.min_similarity = min_similarity

    async def get_options(self, dropdown: Locator) -> List[Dict[str, str]]:
        """
        Get all options from dropdown.

        Args:
            dropdown: Dropdown locator

        Returns:
            List of options with value and text
        """
        try:
            options = await dropdown.locator("option").all()
            result = []

            for option in options:
                value = await option.get_attribute("value") or ""
                text = await option.text_content() or ""
                result.append({
                    "value": value.strip(),
                    "text": text.strip()
                })

            logger.info(f"Found {len(result)} options in dropdown")
            return result

        except Exception as e:
            logger.error(f"Failed to get dropdown options: {e}")
            return []

    def fuzzy_match(self, target: str, candidate: str) -> float:
        """
        Calculate similarity between two strings.

        Args:
            target: Target string
            candidate: Candidate string

        Returns:
            Similarity score (0.0-1.0)
        """
        if not target or not candidate:
            return 0.0

        # Normalize
        target_norm = target.lower().strip()
        candidate_norm = candidate.lower().strip()

        # Exact match
        if target_norm == candidate_norm:
            return 1.0

        # Contains match
        if target_norm in candidate_norm or candidate_norm in target_norm:
            return 0.95

        # Sequence matching
        return SequenceMatcher(None, target_norm, candidate_norm).ratio()

    def find_best_match(
        self,
        target: str,
        options: List[Dict[str, str]]
    ) -> Optional[Tuple[Dict[str, str], float]]:
        """
        Find best matching option using fuzzy matching.

        Args:
            target: Target value to match
            options: List of option dicts

        Returns:
            (best_option, score) tuple or None
        """
        if not target or not options:
            return None

        best_match = None
        best_score = 0.0

        for option in options:
            # Try matching against both value and text
            value_score = self.fuzzy_match(target, option["value"])
            text_score = self.fuzzy_match(target, option["text"])

            score = max(value_score, text_score)

            if score > best_score:
                best_score = score
                best_match = option

        if best_match and best_score >= self.min_similarity:
            logger.info(
                f"Best match for '{target}': '{best_match['text']}' "
                f"(score: {best_score:.2f})"
            )
            return (best_match, best_score)

        logger.warning(
            f"No good match found for '{target}' "
            f"(best score: {best_score:.2f}, threshold: {self.min_similarity})"
        )
        return None

    async def select_option(
        self,
        dropdown: Locator,
        value: str,
        use_fuzzy: bool = True
    ) -> bool:
        """
        Select option in dropdown with optional fuzzy matching.

        Args:
            dropdown: Dropdown locator
            value: Value or text to select
            use_fuzzy: Enable fuzzy matching

        Returns:
            True if selection successful
        """
        try:
            # Try exact value match first
            try:
                await dropdown.select_option(value=value, timeout=2000)
                logger.info(f"Selected option by exact value: {value}")
                return True
            except Exception:
                pass

            # Try exact label match
            try:
                await dropdown.select_option(label=value, timeout=2000)
                logger.info(f"Selected option by exact label: {value}")
                return True
            except Exception:
                pass

            # If fuzzy matching enabled, try that
            if use_fuzzy:
                options = await self.get_options(dropdown)
                match_result = self.find_best_match(value, options)

                if match_result:
                    best_option, score = match_result

                    # Select by value
                    await dropdown.select_option(value=best_option["value"])
                    logger.info(
                        f"Selected option '{best_option['text']}' via fuzzy match "
                        f"(score: {score:.2f})"
                    )
                    return True

            logger.warning(f"Could not select option: {value}")
            return False

        except Exception as e:
            logger.error(f"Error selecting dropdown option: {e}")
            return False

    async def select_by_index(self, dropdown: Locator, index: int) -> bool:
        """
        Select option by index.

        Args:
            dropdown: Dropdown locator
            index: Option index (0-based)

        Returns:
            True if selection successful
        """
        try:
            await dropdown.select_option(index=index)
            logger.info(f"Selected option at index {index}")
            return True
        except Exception as e:
            logger.error(f"Error selecting by index: {e}")
            return False

    async def get_selected_option(self, dropdown: Locator) -> Optional[Dict[str, str]]:
        """
        Get currently selected option.

        Args:
            dropdown: Dropdown locator

        Returns:
            Selected option dict or None
        """
        try:
            value = await dropdown.input_value()
            text = await dropdown.locator(f"option[value='{value}']").text_content()

            return {
                "value": value,
                "text": text.strip() if text else ""
            }

        except Exception as e:
            logger.debug(f"Could not get selected option: {e}")
            return None

    async def is_option_available(
        self,
        dropdown: Locator,
        value: str
    ) -> bool:
        """
        Check if option is available in dropdown.

        Args:
            dropdown: Dropdown locator
            value: Value or text to check

        Returns:
            True if option exists
        """
        try:
            options = await self.get_options(dropdown)
            match = self.find_best_match(value, options)
            return match is not None

        except Exception as e:
            logger.debug(f"Error checking option availability: {e}")
            return False

    async def wait_for_options_loaded(
        self,
        dropdown: Locator,
        min_options: int = 1,
        timeout: int = 10000
    ) -> bool:
        """
        Wait for dropdown to have options loaded.

        Useful for dynamically populated dropdowns.

        Args:
            dropdown: Dropdown locator
            min_options: Minimum number of options expected
            timeout: Timeout in milliseconds

        Returns:
            True if options loaded
        """
        import asyncio

        start_time = asyncio.get_event_loop().time()
        end_time = start_time + (timeout / 1000)

        while asyncio.get_event_loop().time() < end_time:
            try:
                options = await self.get_options(dropdown)
                if len(options) >= min_options:
                    logger.info(f"Dropdown loaded with {len(options)} options")
                    return True
            except Exception:
                pass

            await asyncio.sleep(0.5)

        logger.warning(f"Timeout waiting for dropdown options to load")
        return False

    async def search_and_select(
        self,
        search_input: Locator,
        dropdown: Locator,
        search_term: str,
        select_value: str
    ) -> bool:
        """
        Search in searchable dropdown and select option.

        For dropdowns with search/filter functionality.

        Args:
            search_input: Search input field locator
            dropdown: Dropdown or results container locator
            search_term: Text to search for
            select_value: Value to select from results

        Returns:
            True if selection successful
        """
        try:
            # Type in search field
            await search_input.fill(search_term)
            logger.info(f"Typed search term: {search_term}")

            # Wait for results to filter
            await self.page.wait_for_timeout(500)

            # Select from filtered results
            success = await self.select_option(dropdown, select_value)

            return success

        except Exception as e:
            logger.error(f"Error in search and select: {e}")
            return False
