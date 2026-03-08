"""
Element Handler - Smart element location and interaction

Provides intelligent element finding with multiple fallback strategies.
Adapted from merus-expert/browser/element_handler.py
"""

import logging
from typing import Optional, List, Dict, Any
from playwright.async_api import Page, Locator, TimeoutError as PlaywrightTimeout

logger = logging.getLogger(__name__)


class ElementHandler:
    """
    Intelligent element finding with multiple fallback strategies.

    Tries multiple methods to locate elements:
    1. CSS selector
    2. XPath
    3. Text content matching
    4. Label association
    5. Placeholder text

    This is the "DOM perception" component (80% of interactions).
    Falls back to VLM perception for complex cases.
    """

    def __init__(self, page: Page):
        """
        Initialize element handler.

        Args:
            page: Playwright page object
        """
        self.page = page

    async def find_input(
        self,
        field_name: Optional[str] = None,
        label: Optional[str] = None,
        placeholder: Optional[str] = None,
        css_selector: Optional[str] = None,
        xpath: Optional[str] = None,
        timeout: int = 5000
    ) -> Optional[Locator]:
        """
        Find input field using multiple strategies.

        Args:
            field_name: Input name attribute
            label: Associated label text
            placeholder: Placeholder text
            css_selector: CSS selector
            xpath: XPath selector
            timeout: Timeout in milliseconds

        Returns:
            Locator object or None if not found
        """
        strategies = []

        # Strategy 1: CSS selector
        if css_selector:
            strategies.append(("CSS selector", lambda: self.page.locator(css_selector)))

        # Strategy 2: XPath
        if xpath:
            strategies.append(("XPath", lambda: self.page.locator(f"xpath={xpath}")))

        # Strategy 3: Name attribute
        if field_name:
            strategies.append((
                f"name={field_name}",
                lambda: self.page.locator(f"input[name='{field_name}'], textarea[name='{field_name}'], select[name='{field_name}']")
            ))

        # Strategy 4: Label association
        if label:
            strategies.append((
                f"label={label}",
                lambda: self.page.get_by_label(label, exact=False)
            ))

        # Strategy 5: Placeholder
        if placeholder:
            strategies.append((
                f"placeholder={placeholder}",
                lambda: self.page.get_by_placeholder(placeholder, exact=False)
            ))

        # Try each strategy
        for strategy_name, locator_func in strategies:
            try:
                locator = locator_func()
                await locator.wait_for(state="visible", timeout=timeout)
                logger.info(f"Found input using {strategy_name}")
                return locator
            except PlaywrightTimeout:
                logger.debug(f"Strategy {strategy_name} failed")
                continue
            except Exception as e:
                logger.debug(f"Strategy {strategy_name} error: {e}")
                continue

        logger.warning(f"Could not find input field (name={field_name}, label={label})")
        return None

    async def find_button(
        self,
        text: Optional[str] = None,
        css_selector: Optional[str] = None,
        role: str = "button",
        timeout: int = 5000
    ) -> Optional[Locator]:
        """
        Find button by text or selector.

        Args:
            text: Button text content
            css_selector: CSS selector
            role: ARIA role (default: button)
            timeout: Timeout in milliseconds

        Returns:
            Locator object or None
        """
        strategies = []

        # Strategy 1: CSS selector
        if css_selector:
            strategies.append(("CSS selector", lambda: self.page.locator(css_selector)))

        # Strategy 2: Role + text
        if text:
            strategies.append((
                f"role={role}, text={text}",
                lambda: self.page.get_by_role(role, name=text, exact=False)
            ))

        # Strategy 3: Button tag with text
        if text:
            strategies.append((
                f"button:has-text('{text}')",
                lambda: self.page.locator(f"button:has-text('{text}'), input[type='submit'][value*='{text}']")
            ))

        # Try each strategy
        for strategy_name, locator_func in strategies:
            try:
                locator = locator_func()
                await locator.wait_for(state="visible", timeout=timeout)
                logger.info(f"Found button using {strategy_name}")
                return locator
            except PlaywrightTimeout:
                logger.debug(f"Strategy {strategy_name} failed")
                continue
            except Exception as e:
                logger.debug(f"Strategy {strategy_name} error: {e}")
                continue

        logger.warning(f"Could not find button (text={text}, selector={css_selector})")
        return None

    async def find_dropdown(
        self,
        field_name: Optional[str] = None,
        label: Optional[str] = None,
        css_selector: Optional[str] = None,
        timeout: int = 5000
    ) -> Optional[Locator]:
        """
        Find dropdown/select element.

        Args:
            field_name: Select name attribute
            label: Associated label text
            css_selector: CSS selector
            timeout: Timeout in milliseconds

        Returns:
            Locator object or None
        """
        strategies = []

        # Strategy 1: CSS selector
        if css_selector:
            strategies.append(("CSS selector", lambda: self.page.locator(css_selector)))

        # Strategy 2: Name attribute
        if field_name:
            strategies.append((
                f"name={field_name}",
                lambda: self.page.locator(f"select[name='{field_name}']")
            ))

        # Strategy 3: Label association
        if label:
            strategies.append((
                f"label={label}",
                lambda: self.page.get_by_label(label, exact=False)
            ))

        # Try each strategy
        for strategy_name, locator_func in strategies:
            try:
                locator = locator_func()
                await locator.wait_for(state="visible", timeout=timeout)

                # Verify it's a select element
                tag_name = await locator.evaluate("el => el.tagName")
                if tag_name.lower() == "select":
                    logger.info(f"Found dropdown using {strategy_name}")
                    return locator
                else:
                    logger.debug(f"Found element but not a select tag: {tag_name}")
                    continue

            except PlaywrightTimeout:
                logger.debug(f"Strategy {strategy_name} failed")
                continue
            except Exception as e:
                logger.debug(f"Strategy {strategy_name} error: {e}")
                continue

        logger.warning(f"Could not find dropdown (name={field_name}, label={label})")
        return None

    async def find_link(
        self,
        text: Optional[str] = None,
        href: Optional[str] = None,
        css_selector: Optional[str] = None,
        timeout: int = 5000
    ) -> Optional[Locator]:
        """
        Find link by text or href.

        Args:
            text: Link text
            href: Href attribute (partial match)
            css_selector: CSS selector
            timeout: Timeout in milliseconds

        Returns:
            Locator object or None
        """
        strategies = []

        # Strategy 1: CSS selector
        if css_selector:
            strategies.append(("CSS selector", lambda: self.page.locator(css_selector)))

        # Strategy 2: Role + text
        if text:
            strategies.append((
                f"link text={text}",
                lambda: self.page.get_by_role("link", name=text, exact=False)
            ))

        # Strategy 3: Href partial match
        if href:
            strategies.append((
                f"href contains {href}",
                lambda: self.page.locator(f"a[href*='{href}']")
            ))

        # Try each strategy
        for strategy_name, locator_func in strategies:
            try:
                locator = locator_func()
                await locator.wait_for(state="visible", timeout=timeout)
                logger.info(f"Found link using {strategy_name}")
                return locator
            except PlaywrightTimeout:
                logger.debug(f"Strategy {strategy_name} failed")
                continue
            except Exception as e:
                logger.debug(f"Strategy {strategy_name} error: {e}")
                continue

        logger.warning(f"Could not find link (text={text}, href={href})")
        return None

    async def find_element(
        self,
        css_selector: Optional[str] = None,
        xpath: Optional[str] = None,
        text: Optional[str] = None,
        role: Optional[str] = None,
        timeout: int = 5000
    ) -> Optional[Locator]:
        """
        Generic element finder with multiple strategies.

        Args:
            css_selector: CSS selector
            xpath: XPath selector
            text: Text content to match
            role: ARIA role
            timeout: Timeout in milliseconds

        Returns:
            Locator object or None
        """
        strategies = []

        if css_selector:
            strategies.append(("CSS", lambda: self.page.locator(css_selector)))
        if xpath:
            strategies.append(("XPath", lambda: self.page.locator(f"xpath={xpath}")))
        if text and role:
            strategies.append((f"role={role}", lambda: self.page.get_by_role(role, name=text, exact=False)))
        if text:
            strategies.append(("text", lambda: self.page.get_by_text(text, exact=False)))

        for strategy_name, locator_func in strategies:
            try:
                locator = locator_func()
                await locator.wait_for(state="visible", timeout=timeout)
                logger.info(f"Found element using {strategy_name}")
                return locator
            except PlaywrightTimeout:
                logger.debug(f"Strategy {strategy_name} failed")
                continue
            except Exception as e:
                logger.debug(f"Strategy {strategy_name} error: {e}")
                continue

        logger.warning("Could not find element with provided criteria")
        return None

    async def wait_for_element(
        self,
        css_selector: str,
        state: str = "visible",
        timeout: int = 10000
    ) -> bool:
        """
        Wait for element to reach specified state.

        Args:
            css_selector: CSS selector
            state: Element state (visible, attached, hidden, detached)
            timeout: Timeout in milliseconds

        Returns:
            True if element reached state, False otherwise
        """
        try:
            locator = self.page.locator(css_selector)
            await locator.wait_for(state=state, timeout=timeout)
            logger.info(f"Element {css_selector} reached state: {state}")
            return True
        except PlaywrightTimeout:
            logger.warning(f"Timeout waiting for {css_selector} to be {state}")
            return False
        except Exception as e:
            logger.error(f"Error waiting for element: {e}")
            return False

    async def is_element_visible(self, css_selector: str) -> bool:
        """
        Check if element is visible.

        Args:
            css_selector: CSS selector

        Returns:
            True if visible, False otherwise
        """
        try:
            locator = self.page.locator(css_selector)
            return await locator.is_visible()
        except Exception:
            return False

    async def get_element_text(self, css_selector: str) -> Optional[str]:
        """
        Get text content of element.

        Args:
            css_selector: CSS selector

        Returns:
            Text content or None
        """
        try:
            locator = self.page.locator(css_selector)
            return await locator.text_content()
        except Exception as e:
            logger.debug(f"Could not get text for {css_selector}: {e}")
            return None

    async def get_element_attribute(
        self,
        css_selector: str,
        attribute: str
    ) -> Optional[str]:
        """
        Get attribute value of element.

        Args:
            css_selector: CSS selector
            attribute: Attribute name

        Returns:
            Attribute value or None
        """
        try:
            locator = self.page.locator(css_selector)
            return await locator.get_attribute(attribute)
        except Exception as e:
            logger.debug(f"Could not get attribute {attribute} for {css_selector}: {e}")
            return None

    async def fill_input(
        self,
        locator: Locator,
        value: str,
        clear_first: bool = True
    ) -> bool:
        """
        Fill input field with value.

        Args:
            locator: Playwright Locator
            value: Value to fill
            clear_first: Clear existing value first

        Returns:
            True if successful
        """
        try:
            if clear_first:
                await locator.clear()
            await locator.fill(value)
            # Trigger blur event for form validation
            await locator.evaluate("el => el.blur()")
            logger.info(f"Filled input with value: {value[:20]}...")
            return True
        except Exception as e:
            logger.error(f"Error filling input: {e}")
            return False

    async def click_element(
        self,
        locator: Locator,
        force: bool = False
    ) -> bool:
        """
        Click element.

        Args:
            locator: Playwright Locator
            force: Force click even if element is not visible

        Returns:
            True if successful
        """
        try:
            await locator.click(force=force)
            logger.info("Clicked element")
            return True
        except Exception as e:
            logger.error(f"Error clicking element: {e}")
            return False

    async def select_option(
        self,
        locator: Locator,
        value: Optional[str] = None,
        label: Optional[str] = None
    ) -> bool:
        """
        Select option from dropdown.

        Args:
            locator: Playwright Locator for select element
            value: Option value attribute
            label: Option visible text

        Returns:
            True if successful
        """
        try:
            if value:
                await locator.select_option(value=value)
            elif label:
                await locator.select_option(label=label)
            else:
                logger.warning("No value or label provided for select_option")
                return False
            logger.info(f"Selected option: value={value}, label={label}")
            return True
        except Exception as e:
            logger.error(f"Error selecting option: {e}")
            return False

    async def get_all_text_content(self) -> str:
        """
        Get all visible text content from page.
        Useful for accessibility tree extraction.

        Returns:
            Concatenated text content
        """
        try:
            # Get body text content
            body = self.page.locator("body")
            text = await body.inner_text()
            return text
        except Exception as e:
            logger.error(f"Error getting page text: {e}")
            return ""

    async def get_accessibility_tree(self) -> Dict[str, Any]:
        """
        Get accessibility tree snapshot for DOM perception.

        Returns:
            Accessibility tree as dict
        """
        try:
            snapshot = await self.page.accessibility.snapshot()
            return snapshot or {}
        except Exception as e:
            logger.error(f"Error getting accessibility tree: {e}")
            return {}
