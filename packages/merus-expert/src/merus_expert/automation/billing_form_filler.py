"""
Billing Form Filler - Populate MerusCase time entry forms
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import date
from pathlib import Path
import json
from playwright.async_api import Page
import asyncio

from merus_expert.browser.element_handler import ElementHandler
from merus_expert.browser.dropdown_handler import DropdownHandler
from merus_expert.models.billing import TimeEntry, BillingCategory

logger = logging.getLogger(__name__)


class BillingFormFiller:
    """
    Fills MerusCase time entry forms.

    Handles:
    - Hours input (numeric)
    - Description textarea
    - Category dropdown (with fuzzy matching)
    - Date picker
    - Timekeeper dropdown
    - Billable checkbox
    """

    # Default selectors (can be overridden by discoveries)
    DEFAULT_SELECTORS = {
        "hours_input": [
            "input[name*='hour']",
            "input[name*='time']",
            "input[name*='qty']",
            "input[name*='quantity']",
            "input[type='number']",
            "#hours",
            ".hours-input",
        ],
        "description_field": [
            "textarea[name*='description']",
            "textarea[name*='note']",
            "textarea[name*='narrative']",
            "input[name*='description']",
            "#description",
            ".description-field",
        ],
        "category_dropdown": [
            "select[name*='category']",
            "select[name*='type']",
            "select[name*='activity']",
            "select[name*='code']",
            "#category",
            ".category-select",
        ],
        "date_input": [
            "input[name*='date']",
            "input[type='date']",
            "#entry_date",
            ".date-picker",
        ],
        "timekeeper_dropdown": [
            "select[name*='timekeeper']",
            "select[name*='attorney']",
            "select[name*='user']",
            "#timekeeper",
            ".timekeeper-select",
        ],
        "billable_checkbox": [
            "input[name*='billable'][type='checkbox']",
            "#billable",
            ".billable-checkbox",
        ],
        "rate_input": [
            "input[name*='rate']",
            "input[name*='price']",
            "#rate",
            ".rate-input",
        ],
        "save_button": [
            "button[type='submit']",
            "button:has-text('Save')",
            "button:has-text('Create')",
            "button:has-text('Add')",
            "input[type='submit']",
            ".save-btn",
        ],
    }

    def __init__(
        self,
        page: Page,
        discoveries_path: Optional[str] = None
    ):
        """
        Initialize billing form filler.

        Args:
            page: Playwright page object
            discoveries_path: Path to discoveries JSON (optional)
        """
        self.page = page
        self.element_handler = ElementHandler(page)
        self.dropdown_handler = DropdownHandler(page)

        # Load discovered selectors if available
        self.selectors = self.DEFAULT_SELECTORS.copy()
        if discoveries_path:
            self._load_discoveries(discoveries_path)

    def _load_discoveries(self, path: str):
        """Load discovered selectors from JSON"""
        try:
            discoveries_file = Path(path)
            if discoveries_file.exists():
                data = json.loads(discoveries_file.read_text())
                for field in data.get("form_fields", []):
                    key = field.get("element_key")
                    selector = field.get("primary_selector")
                    if key and selector:
                        if key in self.selectors:
                            # Prepend discovered selector
                            self.selectors[key].insert(0, selector)
                        else:
                            self.selectors[key] = [selector]
                logger.info(f"Loaded discoveries from {path}")
        except Exception as e:
            logger.warning(f"Could not load discoveries: {e}")

    async def fill_hours(self, hours: float) -> bool:
        """
        Fill hours field.

        Args:
            hours: Hours to enter (e.g., 1.5)

        Returns:
            True if successfully filled
        """
        logger.info(f"Filling hours: {hours}")

        for selector in self.selectors["hours_input"]:
            try:
                element = self.page.locator(selector).first
                if await element.is_visible():
                    # Format hours with one decimal
                    hours_str = f"{hours:.1f}"
                    await element.fill(hours_str)
                    await element.dispatch_event("blur")
                    logger.info(f"Filled hours with {hours_str}")
                    return True
            except Exception:
                continue

        # Try using element handler as fallback
        input_field = await self.element_handler.find_input(
            field_name="hours",
            label="Hours",
            placeholder="Hours"
        )
        if input_field:
            await input_field.fill(f"{hours:.1f}")
            await input_field.dispatch_event("blur")
            return True

        logger.error("Could not find hours input field")
        return False

    async def fill_description(self, description: str) -> bool:
        """
        Fill description field.

        Args:
            description: Work description

        Returns:
            True if successfully filled
        """
        logger.info(f"Filling description: {description[:50]}...")

        for selector in self.selectors["description_field"]:
            try:
                element = self.page.locator(selector).first
                if await element.is_visible():
                    await element.fill(description)
                    await element.dispatch_event("blur")
                    logger.info("Filled description")
                    return True
            except Exception:
                continue

        # Try using element handler as fallback
        input_field = await self.element_handler.find_input(
            field_name="description",
            label="Description",
            placeholder="Description"
        )
        if input_field:
            await input_field.fill(description)
            await input_field.dispatch_event("blur")
            return True

        logger.error("Could not find description field")
        return False

    async def select_category(
        self,
        category: BillingCategory,
        use_fuzzy: bool = True
    ) -> bool:
        """
        Select billing category from dropdown.

        Args:
            category: BillingCategory to select
            use_fuzzy: Use fuzzy matching for dropdown

        Returns:
            True if successfully selected
        """
        logger.info(f"Selecting category: {category.value}")

        for selector in self.selectors["category_dropdown"]:
            try:
                dropdown = self.page.locator(selector).first
                if await dropdown.is_visible():
                    # Wait for options to load
                    await self.dropdown_handler.wait_for_options_loaded(
                        dropdown,
                        min_options=1
                    )

                    # Select with fuzzy matching
                    success = await self.dropdown_handler.select_option(
                        dropdown,
                        category.value,
                        use_fuzzy=use_fuzzy
                    )

                    if success:
                        logger.info(f"Selected category: {category.value}")
                        return True
            except Exception:
                continue

        # Try using element handler as fallback
        dropdown = await self.element_handler.find_dropdown(
            field_name="category",
            label="Category"
        )
        if dropdown:
            await self.dropdown_handler.wait_for_options_loaded(dropdown)
            return await self.dropdown_handler.select_option(
                dropdown,
                category.value,
                use_fuzzy=use_fuzzy
            )

        logger.warning("Category dropdown not found - may be optional")
        return True  # Not all systems have categories

    async def fill_date(self, entry_date: date) -> bool:
        """
        Fill date field.

        Args:
            entry_date: Date for the entry

        Returns:
            True if successfully filled
        """
        logger.info(f"Filling date: {entry_date}")

        date_str = entry_date.isoformat()  # YYYY-MM-DD

        for selector in self.selectors["date_input"]:
            try:
                element = self.page.locator(selector).first
                if await element.is_visible():
                    # Try different date formats
                    try:
                        await element.fill(date_str)
                    except Exception:
                        # Try MM/DD/YYYY format
                        us_date = entry_date.strftime("%m/%d/%Y")
                        await element.fill(us_date)

                    await element.dispatch_event("blur")
                    logger.info(f"Filled date: {date_str}")
                    return True
            except Exception:
                continue

        logger.warning("Date field not found - may default to today")
        return True  # Often defaults to today

    async def select_timekeeper(self, timekeeper: str) -> bool:
        """
        Select timekeeper/attorney from dropdown.

        Args:
            timekeeper: Timekeeper name

        Returns:
            True if successfully selected
        """
        logger.info(f"Selecting timekeeper: {timekeeper}")

        for selector in self.selectors["timekeeper_dropdown"]:
            try:
                dropdown = self.page.locator(selector).first
                if await dropdown.is_visible():
                    await self.dropdown_handler.wait_for_options_loaded(
                        dropdown,
                        min_options=1
                    )

                    success = await self.dropdown_handler.select_option(
                        dropdown,
                        timekeeper,
                        use_fuzzy=True
                    )

                    if success:
                        logger.info(f"Selected timekeeper: {timekeeper}")
                        return True
            except Exception:
                continue

        logger.warning("Timekeeper dropdown not found")
        return True  # May default to current user

    async def set_billable(self, billable: bool = True) -> bool:
        """
        Set billable checkbox.

        Args:
            billable: Whether entry is billable

        Returns:
            True if successfully set
        """
        logger.info(f"Setting billable: {billable}")

        for selector in self.selectors["billable_checkbox"]:
            try:
                checkbox = self.page.locator(selector).first
                if await checkbox.is_visible():
                    is_checked = await checkbox.is_checked()

                    if billable and not is_checked:
                        await checkbox.check()
                    elif not billable and is_checked:
                        await checkbox.uncheck()

                    logger.info(f"Billable set to: {billable}")
                    return True
            except Exception:
                continue

        logger.warning("Billable checkbox not found")
        return True  # Often defaults to billable

    async def fill_rate(self, rate: float) -> bool:
        """
        Fill rate override field.

        Args:
            rate: Hourly rate

        Returns:
            True if successfully filled
        """
        logger.info(f"Filling rate: {rate}")

        for selector in self.selectors["rate_input"]:
            try:
                element = self.page.locator(selector).first
                if await element.is_visible():
                    await element.fill(f"{rate:.2f}")
                    await element.dispatch_event("blur")
                    logger.info(f"Filled rate: {rate}")
                    return True
            except Exception:
                continue

        logger.warning("Rate field not found")
        return True  # Rate override is optional

    async def fill_complete_entry(self, entry: TimeEntry) -> bool:
        """
        Fill complete time entry form.

        Args:
            entry: TimeEntry with all data

        Returns:
            True if all required fields filled successfully
        """
        logger.info("Filling complete time entry form...")

        # Required: Hours
        if not await self.fill_hours(entry.hours):
            logger.error("Failed to fill hours")
            return False

        # Required: Description
        if not await self.fill_description(entry.description):
            logger.error("Failed to fill description")
            return False

        # Optional: Category
        if entry.category:
            await self.select_category(entry.category)

        # Optional: Date (if not today)
        if entry.entry_date != date.today():
            await self.fill_date(entry.entry_date)

        # Optional: Timekeeper
        if entry.timekeeper:
            await self.select_timekeeper(entry.timekeeper)

        # Optional: Billable
        await self.set_billable(entry.billable)

        # Optional: Rate override
        if entry.rate is not None:
            await self.fill_rate(entry.rate)

        logger.info("Time entry form filled successfully")
        return True

    async def click_save(self) -> bool:
        """
        Click save/submit button.

        Returns:
            True if button clicked
        """
        logger.info("Clicking save button...")

        for selector in self.selectors["save_button"]:
            try:
                button = self.page.locator(selector).first
                if await button.is_visible():
                    await button.click()
                    logger.info("Clicked save button")
                    return True
            except Exception:
                continue

        # Try using element handler
        button = await self.element_handler.find_button(
            text="Save",
            css_selector="button[type='submit']"
        )
        if button:
            await button.click()
            return True

        logger.error("Could not find save button")
        return False

    async def extract_filled_values(self) -> Dict[str, Any]:
        """
        Extract currently filled values from form.

        Returns:
            Dict with field values
        """
        values = {}

        try:
            # Extract hours
            for selector in self.selectors["hours_input"]:
                try:
                    el = self.page.locator(selector).first
                    if await el.is_visible():
                        values["hours"] = await el.input_value()
                        break
                except Exception:
                    continue

            # Extract description
            for selector in self.selectors["description_field"]:
                try:
                    el = self.page.locator(selector).first
                    if await el.is_visible():
                        values["description"] = await el.input_value()
                        break
                except Exception:
                    continue

            # Extract category
            for selector in self.selectors["category_dropdown"]:
                try:
                    el = self.page.locator(selector).first
                    if await el.is_visible():
                        values["category"] = await el.input_value()
                        break
                except Exception:
                    continue

        except Exception as e:
            logger.error(f"Error extracting values: {e}")

        return values

    async def get_available_categories(self) -> List[Dict[str, str]]:
        """
        Get list of available billing categories from dropdown.

        Returns:
            List of {value, text} dicts
        """
        categories = []

        for selector in self.selectors["category_dropdown"]:
            try:
                dropdown = self.page.locator(selector).first
                if await dropdown.is_visible():
                    options = await dropdown.locator("option").all()
                    for opt in options:
                        value = await opt.get_attribute("value") or ""
                        text = await opt.text_content() or ""
                        if value or text:
                            categories.append({
                                "value": value.strip(),
                                "text": text.strip()
                            })
                    break
            except Exception:
                continue

        return categories
