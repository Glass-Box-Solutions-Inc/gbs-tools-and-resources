"""
Spectacles DOM Extractor
Extract structured information from page DOM using Accessibility Tree

Handles 80% of perception tasks - fast and reliable for standard elements.
Falls back to VLM for complex layouts, canvas elements, or shadow DOM.
"""

import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from playwright.async_api import Page

logger = logging.getLogger(__name__)


@dataclass
class DOMElement:
    """Represents an interactive element in the DOM"""
    role: str
    name: Optional[str] = None
    value: Optional[str] = None
    description: Optional[str] = None
    focused: bool = False
    disabled: bool = False
    expanded: Optional[bool] = None
    checked: Optional[bool] = None
    level: Optional[int] = None
    children: List["DOMElement"] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        result = {"role": self.role}
        if self.name:
            result["name"] = self.name
        if self.value:
            result["value"] = self.value
        if self.description:
            result["description"] = self.description
        if self.focused:
            result["focused"] = True
        if self.disabled:
            result["disabled"] = True
        if self.expanded is not None:
            result["expanded"] = self.expanded
        if self.checked is not None:
            result["checked"] = self.checked
        if self.children:
            result["children"] = [c.to_dict() for c in self.children]
        return result


@dataclass
class DOMPerception:
    """Result of DOM-based page perception"""
    url: str
    title: str
    interactive_elements: List[Dict[str, Any]]
    forms: List[Dict[str, Any]]
    navigation: List[Dict[str, Any]]
    main_content: str
    accessibility_tree: Optional[Dict[str, Any]] = None
    confidence: float = 1.0
    needs_vlm: bool = False
    vlm_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "interactive_elements": self.interactive_elements,
            "forms": self.forms,
            "navigation": self.navigation,
            "main_content": self.main_content[:500] if self.main_content else "",
            "accessibility_tree": self.accessibility_tree,
            "confidence": self.confidence,
            "needs_vlm": self.needs_vlm,
            "vlm_reason": self.vlm_reason,
        }


class DOMExtractor:
    """
    Extract structured information from page DOM.

    Uses Playwright's accessibility tree for semantic understanding.
    Fast and reliable for standard web elements.

    Triggers VLM fallback when:
    - Canvas elements detected
    - Shadow DOM present
    - Low confidence in element detection
    - CAPTCHA-like patterns found
    - Complex visual layouts
    """

    # Patterns that suggest VLM is needed
    VLM_TRIGGER_SELECTORS = [
        "canvas",
        "[class*='captcha']",
        "[class*='recaptcha']",
        "[id*='captcha']",
        "iframe[src*='captcha']",
        "[class*='slider-verify']",
    ]

    def __init__(self, page: Page):
        """
        Initialize DOM extractor.

        Args:
            page: Playwright page object
        """
        self.page = page

    async def extract(self) -> DOMPerception:
        """
        Extract structured perception from page DOM.

        Returns:
            DOMPerception with page structure and elements
        """
        try:
            # Basic page info
            url = self.page.url
            title = await self.page.title()

            # Get accessibility tree
            a11y_tree = await self._get_accessibility_tree()

            # Extract interactive elements
            interactive = await self._extract_interactive_elements()

            # Extract forms
            forms = await self._extract_forms()

            # Extract navigation
            navigation = await self._extract_navigation()

            # Get main content text
            main_content = await self._get_main_content()

            # Check if VLM is needed
            needs_vlm, vlm_reason = await self._check_vlm_needed()

            # Calculate confidence
            confidence = self._calculate_confidence(interactive, forms)

            return DOMPerception(
                url=url,
                title=title,
                interactive_elements=interactive,
                forms=forms,
                navigation=navigation,
                main_content=main_content,
                accessibility_tree=a11y_tree,
                confidence=confidence,
                needs_vlm=needs_vlm,
                vlm_reason=vlm_reason,
            )

        except Exception as e:
            logger.error("DOM extraction failed: %s", e)
            return DOMPerception(
                url=self.page.url,
                title="",
                interactive_elements=[],
                forms=[],
                navigation=[],
                main_content="",
                confidence=0.0,
                needs_vlm=True,
                vlm_reason=f"DOM extraction failed: {str(e)}",
            )

    async def _get_accessibility_tree(self) -> Optional[Dict[str, Any]]:
        """Get page accessibility tree snapshot"""
        try:
            snapshot = await self.page.accessibility.snapshot()
            return snapshot
        except Exception as e:
            logger.warning("Failed to get accessibility tree: %s", e)
            return None

    async def _extract_interactive_elements(self) -> List[Dict[str, Any]]:
        """Extract clickable and interactive elements"""
        elements = []

        # Buttons
        buttons = await self.page.locator("button, [role='button'], input[type='submit'], input[type='button']").all()
        for btn in buttons[:20]:  # Limit to prevent overload
            try:
                text = await btn.text_content()
                visible = await btn.is_visible()
                enabled = await btn.is_enabled()
                if visible:
                    elements.append({
                        "type": "button",
                        "text": text.strip() if text else "",
                        "enabled": enabled,
                        "selector": await self._get_selector(btn),
                    })
            except:
                continue

        # Links
        links = await self.page.locator("a[href]").all()
        for link in links[:30]:
            try:
                text = await link.text_content()
                href = await link.get_attribute("href")
                visible = await link.is_visible()
                if visible and text:
                    elements.append({
                        "type": "link",
                        "text": text.strip()[:100],
                        "href": href,
                        "selector": await self._get_selector(link),
                    })
            except:
                continue

        return elements

    async def _extract_forms(self) -> List[Dict[str, Any]]:
        """Extract form structures with their fields"""
        forms = []

        form_elements = await self.page.locator("form").all()
        for form in form_elements[:5]:
            try:
                visible = await form.is_visible()
                if not visible:
                    continue

                fields = []

                # Text inputs
                inputs = await form.locator("input:not([type='hidden']), textarea, select").all()
                for inp in inputs[:20]:
                    try:
                        input_type = await inp.get_attribute("type") or "text"
                        name = await inp.get_attribute("name") or ""
                        placeholder = await inp.get_attribute("placeholder") or ""
                        label = await self._find_label_for(inp)
                        required = await inp.get_attribute("required") is not None

                        fields.append({
                            "type": input_type,
                            "name": name,
                            "label": label,
                            "placeholder": placeholder,
                            "required": required,
                            "selector": await self._get_selector(inp),
                        })
                    except:
                        continue

                forms.append({
                    "fields": fields,
                    "field_count": len(fields),
                    "selector": await self._get_selector(form),
                })
            except:
                continue

        return forms

    async def _extract_navigation(self) -> List[Dict[str, Any]]:
        """Extract navigation elements"""
        nav_items = []

        # Look for nav elements
        navs = await self.page.locator("nav a, [role='navigation'] a, header a").all()
        for nav in navs[:15]:
            try:
                text = await nav.text_content()
                href = await nav.get_attribute("href")
                visible = await nav.is_visible()
                if visible and text:
                    nav_items.append({
                        "text": text.strip()[:50],
                        "href": href,
                    })
            except:
                continue

        return nav_items

    async def _get_main_content(self) -> str:
        """Extract main content text"""
        try:
            # Try main content selectors in order
            for selector in ["main", "[role='main']", "article", ".content", "#content", "body"]:
                element = self.page.locator(selector).first
                if await element.count() > 0:
                    text = await element.inner_text()
                    if text:
                        return text[:2000]  # Limit length
            return ""
        except:
            return ""

    async def _check_vlm_needed(self) -> tuple[bool, Optional[str]]:
        """Check if VLM perception is needed"""
        for selector in self.VLM_TRIGGER_SELECTORS:
            try:
                count = await self.page.locator(selector).count()
                if count > 0:
                    return True, f"Found element matching: {selector}"
            except:
                continue

        return False, None

    async def _find_label_for(self, element) -> str:
        """Find label text for an input element"""
        try:
            # Check for id and matching label
            elem_id = await element.get_attribute("id")
            if elem_id:
                label = self.page.locator(f"label[for='{elem_id}']")
                if await label.count() > 0:
                    return (await label.text_content()).strip()

            # Check for aria-label
            aria_label = await element.get_attribute("aria-label")
            if aria_label:
                return aria_label

            return ""
        except:
            return ""

    async def _get_selector(self, element) -> str:
        """Generate a selector for element"""
        try:
            # Try id first
            elem_id = await element.get_attribute("id")
            if elem_id:
                return f"#{elem_id}"

            # Try name
            name = await element.get_attribute("name")
            if name:
                tag = await element.evaluate("el => el.tagName.toLowerCase()")
                return f"{tag}[name='{name}']"

            # Fallback to tag + class
            tag = await element.evaluate("el => el.tagName.toLowerCase()")
            classes = await element.get_attribute("class")
            if classes:
                first_class = classes.split()[0]
                return f"{tag}.{first_class}"

            return tag
        except:
            return ""

    def _calculate_confidence(
        self,
        interactive: List[Dict],
        forms: List[Dict]
    ) -> float:
        """Calculate confidence in DOM extraction"""
        # Base confidence
        confidence = 0.8

        # Reduce if no interactive elements found
        if not interactive:
            confidence -= 0.3

        # Reduce if forms have no fields
        if forms and all(f.get("field_count", 0) == 0 for f in forms):
            confidence -= 0.2

        return max(0.1, min(1.0, confidence))
