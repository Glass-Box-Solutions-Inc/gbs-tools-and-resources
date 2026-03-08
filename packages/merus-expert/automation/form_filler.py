"""
Form Filler - Populate MerusCase forms with matter data
"""

import logging
from typing import Dict, Any, Optional
from playwright.async_api import Page
import asyncio

from browser.element_handler import ElementHandler
from browser.dropdown_handler import DropdownHandler
from models.matter import MatterDetails

logger = logging.getLogger(__name__)


class FormFiller:
    """
    Fills MerusCase matter creation forms.

    Handles different form types and field mappings based on case type.
    """

    def __init__(self, page: Page):
        """
        Initialize form filler.

        Args:
            page: Playwright page object
        """
        self.page = page
        self.element_handler = ElementHandler(page)
        self.dropdown_handler = DropdownHandler(page)

    async def fill_text_field(
        self,
        field_name: str,
        value: str,
        label: Optional[str] = None,
        required: bool = False
    ) -> bool:
        """
        Fill text input field.

        Args:
            field_name: Field name attribute
            value: Value to fill
            label: Associated label text
            required: Whether field is required

        Returns:
            True if successfully filled
        """
        try:
            # Find input field
            input_field = await self.element_handler.find_input(
                field_name=field_name,
                label=label
            )

            if not input_field:
                if required:
                    logger.error(f"Required field not found: {field_name}")
                    return False
                logger.warning(f"Optional field not found, skipping: {field_name}")
                return True

            # Fill field
            await input_field.fill(value)
            logger.info(f"Filled {field_name}: {value}")

            # Trigger any change events
            await input_field.dispatch_event("blur")

            return True

        except Exception as e:
            logger.error(f"Error filling {field_name}: {e}")
            return False

    async def select_dropdown_option(
        self,
        field_name: str,
        value: str,
        label: Optional[str] = None,
        required: bool = False,
        use_fuzzy: bool = True
    ) -> bool:
        """
        Select dropdown option.

        Args:
            field_name: Dropdown name attribute
            value: Value to select
            label: Associated label text
            required: Whether field is required
            use_fuzzy: Enable fuzzy matching

        Returns:
            True if successfully selected
        """
        try:
            # Find dropdown
            dropdown = await self.element_handler.find_dropdown(
                field_name=field_name,
                label=label
            )

            if not dropdown:
                if required:
                    logger.error(f"Required dropdown not found: {field_name}")
                    return False
                logger.warning(f"Optional dropdown not found, skipping: {field_name}")
                return True

            # Wait for options to load
            await self.dropdown_handler.wait_for_options_loaded(dropdown, min_options=1)

            # Select option
            success = await self.dropdown_handler.select_option(
                dropdown,
                value,
                use_fuzzy=use_fuzzy
            )

            if not success and required:
                logger.error(f"Failed to select required option: {field_name}={value}")
                return False

            return success

        except Exception as e:
            logger.error(f"Error selecting dropdown {field_name}: {e}")
            return False

    async def fill_primary_party(self, matter: MatterDetails) -> bool:
        """
        Fill primary party (Applicant) fields.

        MerusCase uses First Name and Last Name fields for the applicant.
        This often triggers conflict checking.

        Args:
            matter: Matter details

        Returns:
            True if successfully filled
        """
        logger.info("Filling primary party (applicant)...")

        # Parse name - expected format: "LASTNAME FIRSTNAME" or "FIRSTNAME LASTNAME"
        name_parts = matter.primary_party.strip().split()
        if len(name_parts) >= 2:
            # Assume format is "LASTNAME FIRSTNAME" (common in legal)
            last_name = name_parts[0]
            first_name = " ".join(name_parts[1:])
        else:
            # Single name - use as last name
            last_name = matter.primary_party
            first_name = ""

        logger.info(f"Parsed name: First='{first_name}', Last='{last_name}'")

        # MerusCase field names from form exploration
        # data[Contact][first_name] and data[Contact][last_name]

        # Fill Last Name first (often the primary field)
        last_name_field = await self.element_handler.find_input(
            field_name="data[Contact][last_name]",
            label="Last Name",
            css_selector="input[name='data[Contact][last_name]']"
        )
        if last_name_field:
            await last_name_field.fill(last_name)
            logger.info(f"Filled Last Name: {last_name}")
        else:
            logger.error("Could not find Last Name field")
            return False

        # Fill First Name
        first_name_field = await self.element_handler.find_input(
            field_name="data[Contact][first_name]",
            label="First Name",
            css_selector="input[name='data[Contact][first_name]']"
        )
        if first_name_field:
            await first_name_field.fill(first_name)
            logger.info(f"Filled First Name: {first_name}")
        else:
            logger.error("Could not find First Name field")
            return False

        # Wait for any conflict check to complete
        await self.wait_for_conflict_check()

        return True

    async def wait_for_conflict_check(self, timeout: int = 30000) -> bool:
        """
        Wait for MerusCase conflict check to complete.

        Args:
            timeout: Timeout in milliseconds

        Returns:
            True if check completed successfully
        """
        logger.info("Waiting for conflict check...")

        try:
            # Wait for loading indicator to disappear
            # Common patterns: .loading, .spinner, [data-loading]
            await self.page.wait_for_selector(
                ".loading, .spinner, [data-loading='true']",
                state="hidden",
                timeout=timeout
            )

            # Additional wait for stability
            await asyncio.sleep(1)

            logger.info("Conflict check completed")
            return True

        except Exception as e:
            logger.warning(f"Conflict check wait uncertain: {e}")
            # Not critical - continue anyway
            return True

    async def fill_case_details(self, matter: MatterDetails) -> bool:
        """
        Fill case type and related fields.

        MerusCase field names (from form exploration):
        - Case Type: data[CaseFile][case_type_id]
        - Case Status: data[CaseFile][case_status_id]
        - Attorney Responsible: data[CaseFile][attorney_responsible]
        - Office: data[CaseFile][firm_office_id]

        Args:
            matter: Matter details

        Returns:
            True if all required fields filled
        """
        logger.info("Filling case details...")

        # Case Type dropdown - usually pre-selected but we can set it
        if matter.case_type:
            case_type_select = self.page.locator("select[name='data[CaseFile][case_type_id]']")
            if await case_type_select.is_visible():
                await case_type_select.select_option(label=matter.case_type.value)
                logger.info(f"Selected Case Type: {matter.case_type.value}")

        # Case Status dropdown
        if matter.case_status:
            status_value = matter.case_status.value if hasattr(matter.case_status, 'value') else str(matter.case_status)
            status_select = self.page.locator("select[name='data[CaseFile][case_status_id]']")
            if await status_select.is_visible():
                await status_select.select_option(label=status_value)
                logger.info(f"Selected Case Status: {status_value}")

        # Attorney Responsible dropdown
        if matter.attorney_responsible:
            attorney_select = self.page.locator("select[name='data[CaseFile][attorney_responsible]']")
            if await attorney_select.is_visible():
                try:
                    await attorney_select.select_option(label=matter.attorney_responsible)
                    logger.info(f"Selected Attorney: {matter.attorney_responsible}")
                except Exception as e:
                    logger.warning(f"Could not select attorney: {e}")

        # Office dropdown
        if matter.office:
            office_select = self.page.locator("select[name='data[CaseFile][firm_office_id]']")
            if await office_select.is_visible():
                try:
                    await office_select.select_option(label=matter.office)
                    logger.info(f"Selected Office: {matter.office}")
                except Exception as e:
                    logger.warning(f"Could not select office: {e}")

        return True

    async def fill_billing_info(self, matter: MatterDetails) -> bool:
        """
        Fill billing information fields.

        Args:
            matter: Matter details

        Returns:
            True if billing fields filled successfully
        """
        if not matter.billing_info:
            logger.info("No billing info to fill")
            return True

        logger.info("Filling billing information...")

        billing = matter.billing_info
        success = True

        # Amount due
        if billing.amount_due is not None:
            success &= await self.fill_text_field(
                field_name="amount_due",
                value=str(billing.amount_due),
                label="Amount Due",
                required=False
            )

        # Description
        if billing.description:
            success &= await self.fill_text_field(
                field_name="billing_description",
                value=billing.description,
                label="Description",
                required=False
            )

        # Amount received
        if billing.amount_received is not None:
            success &= await self.fill_text_field(
                field_name="amount_received",
                value=str(billing.amount_received),
                label="Amount Received",
                required=False
            )

        # Check number
        if billing.check_number:
            success &= await self.fill_text_field(
                field_name="check_number",
                value=billing.check_number,
                label="Check Number",
                required=False
            )

        # Memo
        if billing.memo:
            success &= await self.fill_text_field(
                field_name="memo",
                value=billing.memo,
                label="Memo",
                required=False
            )

        return success

    async def fill_custom_fields(self, custom_fields: Dict[str, Any]) -> bool:
        """
        Fill custom/additional fields.

        Args:
            custom_fields: Dictionary of field_name: value

        Returns:
            True if all custom fields filled
        """
        if not custom_fields:
            return True

        logger.info(f"Filling {len(custom_fields)} custom fields...")

        success = True
        for field_name, value in custom_fields.items():
            # Convert value to string
            str_value = str(value) if value is not None else ""

            # Try as text field first
            filled = await self.fill_text_field(
                field_name=field_name,
                value=str_value,
                required=False
            )

            if not filled:
                # Try as dropdown
                filled = await self.select_dropdown_option(
                    field_name=field_name,
                    value=str_value,
                    required=False
                )

            success &= filled

        return success

    async def fill_complete_form(self, matter: MatterDetails) -> bool:
        """
        Fill entire matter creation form.

        Args:
            matter: Matter details

        Returns:
            True if form filled successfully
        """
        logger.info("Filling complete matter form...")

        # Step 1: Primary party (triggers conflict check)
        if not await self.fill_primary_party(matter):
            logger.error("Failed to fill primary party")
            return False

        # Step 2: Case details
        if not await self.fill_case_details(matter):
            logger.error("Failed to fill case details")
            return False

        # Step 3: Billing info
        if not await self.fill_billing_info(matter):
            logger.error("Failed to fill billing info")
            return False

        # Step 4: Custom fields
        if matter.custom_fields:
            if not await self.fill_custom_fields(matter.custom_fields):
                logger.warning("Some custom fields may not have been filled")

        logger.info("Form filling completed")
        return True

    async def extract_filled_values(self) -> Dict[str, Any]:
        """
        Extract all filled form values for validation.

        Returns:
            Dictionary of field values
        """
        logger.info("Extracting filled form values...")

        try:
            # Execute JavaScript to get all form values
            form_data = await self.page.evaluate("""
                () => {
                    const data = {};
                    const inputs = document.querySelectorAll('input, select, textarea');

                    inputs.forEach(el => {
                        const name = el.name || el.id;
                        if (name && el.value) {
                            if (el.type === 'checkbox' || el.type === 'radio') {
                                data[name] = el.checked;
                            } else {
                                data[name] = el.value;
                            }
                        }
                    });

                    return data;
                }
            """)

            logger.info(f"Extracted {len(form_data)} form fields")
            return form_data

        except Exception as e:
            logger.error(f"Error extracting form values: {e}")
            return {}
