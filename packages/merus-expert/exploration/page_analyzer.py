"""
Page Analyzer - Extract form elements and page structure
"""

import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
from playwright.async_api import Page

logger = logging.getLogger(__name__)


@dataclass
class FormFieldInfo:
    """Information about a form field"""
    tag_name: str  # input, select, textarea
    field_type: str  # text, email, number, select, textarea
    name: str
    id: str
    label: str
    placeholder: str
    required: bool
    selector: str  # Best selector to use
    visible: bool
    value: Optional[str] = None
    options: List[Dict[str, str]] = field(default_factory=list)  # For select elements


@dataclass
class ButtonInfo:
    """Information about a button"""
    tag_name: str
    button_type: str  # submit, button, reset
    text: str
    selector: str
    visible: bool
    disabled: bool = False


@dataclass
class NavigationInfo:
    """Information about navigation element"""
    tag_name: str  # a, button, li
    text: str
    href: Optional[str]
    selector: str
    is_tab: bool = False
    is_menu_item: bool = False


@dataclass
class PageStructure:
    """Complete page structure analysis"""
    url: str
    title: str
    form_fields: List[FormFieldInfo]
    buttons: List[ButtonInfo]
    navigation: List[NavigationInfo]
    analyzed_at: datetime = field(default_factory=datetime.now)
    error: Optional[str] = None


class PageAnalyzer:
    """
    Analyzes page structure to discover form elements.

    Extracts:
    - Input fields (text, number, email, etc.)
    - Select dropdowns with options
    - Textareas
    - Buttons (submit, regular)
    - Navigation elements (tabs, links, menus)
    """

    def __init__(self, page: Page):
        """
        Initialize page analyzer.

        Args:
            page: Playwright page object
        """
        self.page = page

    async def analyze_page(self) -> PageStructure:
        """
        Analyze current page structure.

        Returns:
            PageStructure with all discovered elements
        """
        try:
            url = self.page.url
            title = await self.page.title()

            form_fields = await self._extract_form_fields()
            buttons = await self._extract_buttons()
            navigation = await self._extract_navigation()

            structure = PageStructure(
                url=url,
                title=title,
                form_fields=form_fields,
                buttons=buttons,
                navigation=navigation,
            )

            logger.info(
                f"Page analyzed: {len(form_fields)} fields, "
                f"{len(buttons)} buttons, {len(navigation)} nav elements"
            )

            return structure

        except Exception as e:
            logger.error(f"Page analysis failed: {e}")
            return PageStructure(
                url=self.page.url,
                title="",
                form_fields=[],
                buttons=[],
                navigation=[],
                error=str(e),
            )

    async def _extract_form_fields(self) -> List[FormFieldInfo]:
        """Extract all form fields from page"""
        fields_data = await self.page.evaluate("""
            () => {
                const fields = [];
                const processed = new Set();

                // Process all form inputs
                document.querySelectorAll('input, select, textarea').forEach(el => {
                    // Skip hidden inputs (except date/time types)
                    if (el.type === 'hidden') return;

                    // Avoid duplicates
                    const key = el.name || el.id || Math.random().toString();
                    if (processed.has(key)) return;
                    processed.add(key);

                    // Find associated label
                    let labelText = '';
                    if (el.id) {
                        const label = document.querySelector(`label[for="${el.id}"]`);
                        if (label) labelText = label.textContent.trim();
                    }
                    if (!labelText) {
                        // Try parent label
                        const parentLabel = el.closest('label');
                        if (parentLabel) {
                            labelText = parentLabel.textContent.replace(el.value || '', '').trim();
                        }
                    }
                    if (!labelText) {
                        // Try aria-label
                        labelText = el.getAttribute('aria-label') || '';
                    }

                    // Build best selector
                    let selector = '';
                    if (el.id) {
                        selector = `#${el.id}`;
                    } else if (el.name) {
                        selector = `[name="${el.name}"]`;
                    } else if (el.className) {
                        selector = `.${el.className.split(' ')[0]}`;
                    }

                    // Get options for select elements
                    const options = [];
                    if (el.tagName.toLowerCase() === 'select') {
                        el.querySelectorAll('option').forEach(opt => {
                            options.push({
                                value: opt.value,
                                text: opt.textContent.trim()
                            });
                        });
                    }

                    fields.push({
                        tagName: el.tagName.toLowerCase(),
                        fieldType: el.type || el.tagName.toLowerCase(),
                        name: el.name || '',
                        id: el.id || '',
                        label: labelText,
                        placeholder: el.placeholder || '',
                        required: el.required || el.hasAttribute('aria-required'),
                        selector: selector,
                        visible: el.offsetParent !== null && el.offsetWidth > 0,
                        value: el.value || null,
                        options: options
                    });
                });

                return fields;
            }
        """)

        return [
            FormFieldInfo(
                tag_name=f['tagName'],
                field_type=f['fieldType'],
                name=f['name'],
                id=f['id'],
                label=f['label'],
                placeholder=f['placeholder'],
                required=f['required'],
                selector=f['selector'],
                visible=f['visible'],
                value=f['value'],
                options=f['options'],
            )
            for f in fields_data
            if f['visible']  # Only visible fields
        ]

    async def _extract_buttons(self) -> List[ButtonInfo]:
        """Extract all buttons from page"""
        buttons_data = await self.page.evaluate("""
            () => {
                const buttons = [];
                const processed = new Set();

                // All button elements
                document.querySelectorAll('button, input[type="submit"], input[type="button"]').forEach(el => {
                    const text = el.textContent?.trim() || el.value || '';
                    const key = text + (el.name || '') + (el.id || '');
                    if (processed.has(key)) return;
                    processed.add(key);

                    let selector = '';
                    if (el.id) {
                        selector = `#${el.id}`;
                    } else if (text) {
                        selector = `button:has-text("${text.substring(0, 30)}")`;
                    } else if (el.className) {
                        selector = `button.${el.className.split(' ')[0]}`;
                    }

                    buttons.push({
                        tagName: el.tagName.toLowerCase(),
                        buttonType: el.type || 'button',
                        text: text,
                        selector: selector,
                        visible: el.offsetParent !== null,
                        disabled: el.disabled
                    });
                });

                return buttons;
            }
        """)

        return [
            ButtonInfo(
                tag_name=b['tagName'],
                button_type=b['buttonType'],
                text=b['text'],
                selector=b['selector'],
                visible=b['visible'],
                disabled=b['disabled'],
            )
            for b in buttons_data
            if b['visible']
        ]

    async def _extract_navigation(self) -> List[NavigationInfo]:
        """Extract navigation elements (tabs, menu items, links)"""
        nav_data = await self.page.evaluate("""
            () => {
                const navItems = [];
                const processed = new Set();

                // Tab-like elements
                document.querySelectorAll('[role="tab"], .tab, .nav-tab, li.nav-item a').forEach(el => {
                    const text = el.textContent?.trim() || '';
                    if (!text || processed.has(text)) return;
                    processed.add(text);

                    navItems.push({
                        tagName: el.tagName.toLowerCase(),
                        text: text,
                        href: el.href || null,
                        selector: el.id ? `#${el.id}` : `[role="tab"]:has-text("${text.substring(0, 20)}")`,
                        isTab: true,
                        isMenuItem: false
                    });
                });

                // Sidebar/menu links
                document.querySelectorAll('.sidebar a, .menu a, nav a, .nav-link').forEach(el => {
                    const text = el.textContent?.trim() || '';
                    if (!text || processed.has(text)) return;
                    processed.add(text);

                    navItems.push({
                        tagName: el.tagName.toLowerCase(),
                        text: text,
                        href: el.href || null,
                        selector: el.href ? `a[href*="${new URL(el.href).pathname}"]` : `a:has-text("${text.substring(0, 20)}")`,
                        isTab: false,
                        isMenuItem: true
                    });
                });

                // General links with billing/time keywords
                document.querySelectorAll('a').forEach(el => {
                    const text = (el.textContent?.trim() || '').toLowerCase();
                    const href = (el.href || '').toLowerCase();

                    if (text.includes('billing') || text.includes('time') ||
                        text.includes('entry') || text.includes('hours') ||
                        href.includes('billing') || href.includes('time')) {

                        const displayText = el.textContent?.trim() || '';
                        if (processed.has(displayText)) return;
                        processed.add(displayText);

                        navItems.push({
                            tagName: 'a',
                            text: displayText,
                            href: el.href || null,
                            selector: el.href ? `a[href*="${new URL(el.href).pathname}"]` : `a:has-text("${displayText.substring(0, 20)}")`,
                            isTab: false,
                            isMenuItem: false
                        });
                    }
                });

                return navItems;
            }
        """)

        return [
            NavigationInfo(
                tag_name=n['tagName'],
                text=n['text'],
                href=n['href'],
                selector=n['selector'],
                is_tab=n['isTab'],
                is_menu_item=n['isMenuItem'],
            )
            for n in nav_data
        ]

    async def find_billing_related_elements(self) -> Dict[str, List[Any]]:
        """
        Find elements specifically related to billing/time entry.

        Returns:
            Dict with categorized billing-related elements
        """
        result = {
            "billing_tabs": [],
            "time_entry_buttons": [],
            "hours_inputs": [],
            "description_fields": [],
            "category_dropdowns": [],
            "save_buttons": [],
        }

        # Analyze page
        structure = await self.analyze_page()

        # Categorize billing-related elements
        billing_keywords = ['billing', 'time', 'entry', 'hours', 'fee']
        add_keywords = ['add', 'new', 'create', '+']
        save_keywords = ['save', 'submit', 'create', 'add']
        hours_keywords = ['hour', 'time', 'duration', 'qty', 'quantity']
        desc_keywords = ['description', 'note', 'detail', 'memo', 'narrative']
        category_keywords = ['category', 'type', 'activity', 'code', 'task']

        # Check navigation for billing tabs
        for nav in structure.navigation:
            text_lower = nav.text.lower()
            if any(kw in text_lower for kw in billing_keywords):
                result["billing_tabs"].append(nav)

        # Check buttons
        for btn in structure.buttons:
            text_lower = btn.text.lower()
            if any(kw in text_lower for kw in add_keywords) and \
               any(kw in text_lower for kw in billing_keywords + ['entry']):
                result["time_entry_buttons"].append(btn)
            elif any(kw in text_lower for kw in save_keywords):
                result["save_buttons"].append(btn)

        # Check form fields
        for field in structure.form_fields:
            name_lower = (field.name + field.label + field.placeholder).lower()

            if any(kw in name_lower for kw in hours_keywords):
                result["hours_inputs"].append(field)
            elif any(kw in name_lower for kw in desc_keywords):
                result["description_fields"].append(field)
            elif field.tag_name == 'select' and any(kw in name_lower for kw in category_keywords):
                result["category_dropdowns"].append(field)

        logger.info(
            f"Found billing elements: {len(result['billing_tabs'])} tabs, "
            f"{len(result['time_entry_buttons'])} add buttons, "
            f"{len(result['hours_inputs'])} hours inputs"
        )

        return result

    async def capture_annotated_screenshot(
        self,
        output_path: str,
        highlight_selectors: List[str] = None
    ) -> str:
        """
        Capture screenshot with highlighted elements.

        Args:
            output_path: Path to save screenshot
            highlight_selectors: Selectors to highlight (optional)

        Returns:
            Path to saved screenshot
        """
        if highlight_selectors:
            # Add highlight styles temporarily
            await self.page.evaluate("""
                (selectors) => {
                    selectors.forEach((sel, i) => {
                        const el = document.querySelector(sel);
                        if (el) {
                            el.style.outline = '3px solid red';
                            el.style.outlineOffset = '2px';
                            // Add label
                            const label = document.createElement('div');
                            label.textContent = i + 1;
                            label.style.cssText = 'position:absolute;background:red;color:white;padding:2px 6px;font-size:12px;z-index:9999;';
                            el.style.position = 'relative';
                            el.appendChild(label);
                        }
                    });
                }
            """, highlight_selectors)

        await self.page.screenshot(path=output_path, full_page=True)
        logger.info(f"Screenshot saved: {output_path}")

        # Remove highlights
        if highlight_selectors:
            await self.page.evaluate("""
                () => {
                    document.querySelectorAll('[style*="outline"]').forEach(el => {
                        el.style.outline = '';
                        el.style.outlineOffset = '';
                    });
                }
            """)

        return output_path
