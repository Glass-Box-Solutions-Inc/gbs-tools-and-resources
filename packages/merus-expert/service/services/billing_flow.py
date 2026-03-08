# @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""
Billing Flow - Minimal state machine for time entry creation
Hybrid flow with auto-detection and single-line entry parsing
"""

import re
from enum import Enum
from typing import Optional, Dict, Any, Tuple, List
from pydantic import BaseModel
from datetime import date

from models.billing import (
    TimeEntry,
    MatterReference,
    MatterSearchResult,
    MatterSelectionMethod,
    BillingCategory,
    parse_entry_from_text,
)


class BillingState(str, Enum):
    """Minimal states for hybrid billing flow"""
    INIT = "init"
    SELECT_MATTER = "select_matter"
    COLLECT_ENTRY = "collect_entry"
    CONFIRMATION = "confirmation"
    COMPLETED = "completed"
    ERROR = "error"


class BillingContext(BaseModel):
    """Tracks billing session state"""
    session_id: str
    state: BillingState = BillingState.INIT
    matter: Optional[Dict[str, Any]] = None  # Resolved matter info
    entry: Optional[Dict[str, Any]] = None   # Time entry data
    search_results: List[Dict[str, Any]] = []
    retry_count: int = 0
    max_retries: int = 3
    errors: List[str] = []

    class Config:
        use_enum_values = True


class BillingFlow:
    """
    Hybrid flow for time entry creation.

    Unlike full conversational flow (15+ states), this uses:
    - Quick form pattern (minimal questions)
    - Auto-detection of matter from URL/ID
    - Single-line entry collection
    - Natural language parsing

    States:
    1. INIT - Initial prompt, auto-detect input type
    2. SELECT_MATTER - Resolve matter (search results, URL, ID)
    3. COLLECT_ENTRY - Single-line time entry input
    4. CONFIRMATION - Review before submission
    5. COMPLETED - Done
    """

    # Prompts for each state
    PROMPTS = {
        BillingState.INIT: (
            "Time Entry Assistant\n"
            "====================\n\n"
            "How would you like to select the matter?\n\n"
            "- Paste a MerusCase URL\n"
            "- Enter a matter ID (numbers only)\n"
            "- Search by client or case name\n"
            "- Type 'recent' to see recent matters"
        ),
        BillingState.SELECT_MATTER: None,  # Dynamic based on context
        BillingState.COLLECT_ENTRY: (
            "Enter your time entry:\n\n"
            "Format: [hours] [category] [description]\n\n"
            "Examples:\n"
            "- 1.5 Consultation Phone call with client re: case status\n"
            "- 2 hours research Case law for motion to dismiss\n"
            "- 30 minutes correspondence Email to opposing counsel\n\n"
            "Categories: Consultation, Document Review, Research, "
            "Correspondence, Phone Conference, Meeting, Other"
        ),
        BillingState.CONFIRMATION: None,  # Dynamic summary
        BillingState.COMPLETED: (
            "Time entry created successfully!\n\n"
            "Would you like to add another entry? (yes/no)"
        ),
        BillingState.ERROR: (
            "An error occurred.\n"
            "Type 'restart' to begin again, or describe the issue."
        ),
    }

    # State transitions
    TRANSITIONS = {
        BillingState.INIT: BillingState.SELECT_MATTER,
        BillingState.SELECT_MATTER: BillingState.COLLECT_ENTRY,
        BillingState.COLLECT_ENTRY: BillingState.CONFIRMATION,
        BillingState.CONFIRMATION: BillingState.COMPLETED,
    }

    def get_initial_message(self) -> str:
        """Get greeting message"""
        return self.PROMPTS[BillingState.INIT]

    def process_input(
        self,
        context: BillingContext,
        user_input: str
    ) -> Tuple[str, BillingContext]:
        """
        Process user input and return response + updated context.

        Args:
            context: Current billing context
            user_input: User's input text

        Returns:
            Tuple of (response_message, updated_context)
        """
        text = user_input.strip()

        # Handle special commands
        if text.lower() in ["restart", "start over", "cancel", "reset"]:
            return self._reset_session(context)

        if text.lower() == "help":
            return self._show_help(context)

        # Route to state handler
        handlers = {
            BillingState.INIT: self._handle_init,
            BillingState.SELECT_MATTER: self._handle_matter_selection,
            BillingState.COLLECT_ENTRY: self._handle_entry_collection,
            BillingState.CONFIRMATION: self._handle_confirmation,
            BillingState.COMPLETED: self._handle_completed,
            BillingState.ERROR: self._handle_error,
        }

        handler = handlers.get(context.state, self._handle_error)
        return handler(context, text)

    def _reset_session(self, context: BillingContext) -> Tuple[str, BillingContext]:
        """Reset session to initial state"""
        new_context = BillingContext(session_id=context.session_id)
        return self.get_initial_message(), new_context

    def _show_help(self, context: BillingContext) -> Tuple[str, BillingContext]:
        """Show help message"""
        help_text = (
            "Time Entry Help\n"
            "===============\n\n"
            "Commands:\n"
            "- restart: Start over\n"
            "- recent: Show recent matters\n"
            "- back: Go to previous step\n\n"
            "Time formats:\n"
            "- 1.5 (hours)\n"
            "- 2 hours\n"
            "- 30 minutes\n"
            "- 1 hour 30 minutes\n\n"
            f"Current state: {context.state.value}"
        )
        return help_text, context

    def _handle_init(
        self,
        context: BillingContext,
        text: str
    ) -> Tuple[str, BillingContext]:
        """
        Handle initial input - auto-detect matter selection method.

        Supports:
        - MerusCase URLs
        - Numeric matter IDs
        - 'recent' keyword
        - Search queries
        """
        # Auto-detect URL
        if "meruscase.com" in text.lower() or "/matters/" in text or "/cases/" in text:
            context.matter = {
                "method": MatterSelectionMethod.URL.value,
                "value": text,
                "resolved": False,
            }
            context.state = BillingState.SELECT_MATTER
            return self._resolve_matter_prompt(context, "URL detected")

        # Check for 'recent' command
        if text.lower() in ["recent", "recent matters", "last"]:
            context.matter = {
                "method": MatterSelectionMethod.RECENT.value,
                "value": "",
                "resolved": False,
            }
            context.state = BillingState.SELECT_MATTER
            return (
                "Fetching recent matters...\n\n"
                "(This will be populated by the API with actual matters)\n\n"
                "Enter the number of the matter you want to select:",
                context
            )

        # Check for numeric ID
        if text.isdigit():
            context.matter = {
                "method": MatterSelectionMethod.DIRECT_ID.value,
                "value": text,
                "resolved": False,
            }
            context.state = BillingState.SELECT_MATTER
            return self._resolve_matter_prompt(context, f"Matter ID: {text}")

        # Default to search query
        context.matter = {
            "method": MatterSelectionMethod.SEARCH.value,
            "value": text,
            "resolved": False,
        }
        context.state = BillingState.SELECT_MATTER
        return (
            f"Searching for: {text}\n\n"
            "(Search results will be populated by the API)\n\n"
            "Enter the number of the matter you want to select,\n"
            "or type a new search query:",
            context
        )

    def _resolve_matter_prompt(
        self,
        context: BillingContext,
        detected: str
    ) -> Tuple[str, BillingContext]:
        """Generate prompt for matter resolution"""
        return (
            f"{detected}\n\n"
            "Resolving matter...\n\n"
            "(The API will resolve this and move to entry collection)",
            context
        )

    def _handle_matter_selection(
        self,
        context: BillingContext,
        text: str
    ) -> Tuple[str, BillingContext]:
        """Handle matter selection from search results or confirmation"""
        # If selecting from numbered list
        if text.isdigit() and context.search_results:
            idx = int(text) - 1
            if 0 <= idx < len(context.search_results):
                selected = context.search_results[idx]
                context.matter = {
                    "method": MatterSelectionMethod.SEARCH.value,
                    "value": selected.get("matter_name", ""),
                    "resolved": True,
                    "matter_id": selected.get("matter_id"),
                    "matter_name": selected.get("matter_name"),
                    "client_name": selected.get("client_name"),
                    "meruscase_url": selected.get("meruscase_url"),
                }
                context.state = BillingState.COLLECT_ENTRY
                return (
                    f"Selected: {selected.get('matter_name')}\n"
                    f"Client: {selected.get('client_name', 'N/A')}\n\n"
                    + self.PROMPTS[BillingState.COLLECT_ENTRY],
                    context
                )
            else:
                return (
                    f"Invalid selection. Enter a number between 1 and {len(context.search_results)}:",
                    context
                )

        # If matter was already resolved by API
        if context.matter and context.matter.get("resolved"):
            context.state = BillingState.COLLECT_ENTRY
            matter_name = context.matter.get("matter_name", "Unknown")
            return (
                f"Matter: {matter_name}\n\n" + self.PROMPTS[BillingState.COLLECT_ENTRY],
                context
            )

        # New search query
        context.matter = {
            "method": MatterSelectionMethod.SEARCH.value,
            "value": text,
            "resolved": False,
        }
        return (
            f"Searching for: {text}\n\n"
            "(Search results will be populated by the API)",
            context
        )

    def _handle_entry_collection(
        self,
        context: BillingContext,
        text: str
    ) -> Tuple[str, BillingContext]:
        """
        Handle time entry input.

        Parses natural language entry format:
        [hours] [category] [description]
        """
        # Try to parse entry from text
        parsed = parse_entry_from_text(text)

        if not parsed:
            context.retry_count += 1
            if context.retry_count >= context.max_retries:
                return (
                    "I'm having trouble understanding that.\n\n"
                    "Please use this format:\n"
                    "[hours] [category] [description]\n\n"
                    "Example: 1.5 Consultation Phone call with client",
                    context
                )
            return (
                "Could not parse time entry.\n\n"
                "Please provide hours and description:\n"
                "Example: 1.5 Consultation Phone call with client",
                context
            )

        # Validate hours
        hours = parsed.get("hours", 0)
        if hours <= 0 or hours > 24:
            return (
                f"Invalid hours: {hours}\n"
                "Hours must be between 0.1 and 24.",
                context
            )

        # Validate description
        description = parsed.get("description", "")
        if len(description) < 3:
            return (
                "Please provide a more detailed description.",
                context
            )

        # Store parsed entry
        context.entry = {
            "hours": hours,
            "category": parsed.get("category", BillingCategory.OTHER).value if isinstance(parsed.get("category"), BillingCategory) else parsed.get("category", "Other"),
            "description": description,
            "entry_date": date.today().isoformat(),
            "billable": True,
        }

        context.state = BillingState.CONFIRMATION
        context.retry_count = 0

        return self._generate_confirmation(context), context

    def _generate_confirmation(self, context: BillingContext) -> str:
        """Generate confirmation summary"""
        matter = context.matter or {}
        entry = context.entry or {}

        summary = (
            "Time Entry Summary\n"
            "==================\n\n"
            f"Matter: {matter.get('matter_name', 'Unknown')}\n"
            f"Client: {matter.get('client_name', 'N/A')}\n\n"
            f"Hours: {entry.get('hours', 0)}\n"
            f"Category: {entry.get('category', 'Other')}\n"
            f"Description: {entry.get('description', '')}\n"
            f"Date: {entry.get('entry_date', date.today().isoformat())}\n"
            f"Billable: {'Yes' if entry.get('billable', True) else 'No'}\n\n"
            "Type 'submit' to create this entry,\n"
            "'edit' to modify, or 'cancel' to start over."
        )

        return summary

    def _handle_confirmation(
        self,
        context: BillingContext,
        text: str
    ) -> Tuple[str, BillingContext]:
        """Handle confirmation response"""
        text_lower = text.lower().strip()

        if text_lower in ["submit", "yes", "confirm", "ok", "create"]:
            # Mark for submission
            context.state = BillingState.COMPLETED
            return (
                "Submitting time entry...\n\n"
                "(The API will handle actual submission)",
                context
            )

        if text_lower in ["edit", "change", "modify"]:
            context.state = BillingState.COLLECT_ENTRY
            context.retry_count = 0
            return (
                "Enter the corrected time entry:\n\n" +
                self.PROMPTS[BillingState.COLLECT_ENTRY],
                context
            )

        if text_lower in ["cancel", "no", "abort"]:
            return self._reset_session(context)

        # Try to parse as a field update
        # e.g., "hours: 2" or "description: updated text"
        field_update = self._parse_field_update(text)
        if field_update:
            field, value = field_update
            if context.entry:
                context.entry[field] = value
            return self._generate_confirmation(context), context

        return (
            "Please type 'submit' to confirm, 'edit' to change, or 'cancel' to start over.",
            context
        )

    def _parse_field_update(self, text: str) -> Optional[Tuple[str, Any]]:
        """
        Parse field update like "hours: 2" or "category: research"

        Returns:
            Tuple of (field_name, value) or None
        """
        patterns = [
            (r"hours?[:\s]+(\d+\.?\d*)", "hours", float),
            (r"category[:\s]+(\w+)", "category", str),
            (r"desc(?:ription)?[:\s]+(.+)", "description", str),
        ]

        for pattern, field, converter in patterns:
            match = re.match(pattern, text, re.IGNORECASE)
            if match:
                try:
                    value = converter(match.group(1).strip())
                    return (field, value)
                except ValueError:
                    pass

        return None

    def _handle_completed(
        self,
        context: BillingContext,
        text: str
    ) -> Tuple[str, BillingContext]:
        """Handle post-completion input (add another entry?)"""
        text_lower = text.lower().strip()

        if text_lower in ["yes", "y", "another", "add"]:
            # Keep matter, reset entry
            context.entry = None
            context.state = BillingState.COLLECT_ENTRY
            return (
                f"Adding another entry for: {context.matter.get('matter_name', 'matter')}\n\n" +
                self.PROMPTS[BillingState.COLLECT_ENTRY],
                context
            )

        if text_lower in ["no", "n", "done", "exit"]:
            return (
                "Session complete. Thank you!\n\n"
                "Type anything to start a new session.",
                context
            )

        # Treat as new matter selection
        return self._reset_session(context)

    def _handle_error(
        self,
        context: BillingContext,
        text: str
    ) -> Tuple[str, BillingContext]:
        """Handle error state"""
        if text.lower() == "restart":
            return self._reset_session(context)

        # Log the error description
        context.errors.append(text)

        return (
            "I've noted the issue. Type 'restart' to begin again.",
            context
        )

    def set_matter_resolved(
        self,
        context: BillingContext,
        matter_id: str,
        matter_name: str,
        client_name: str = "",
        meruscase_url: str = ""
    ) -> BillingContext:
        """
        API helper to set matter as resolved.

        Called by API after resolving matter from URL/ID/search.
        """
        if context.matter is None:
            context.matter = {}

        context.matter.update({
            "resolved": True,
            "matter_id": matter_id,
            "matter_name": matter_name,
            "client_name": client_name,
            "meruscase_url": meruscase_url,
        })

        return context

    def set_search_results(
        self,
        context: BillingContext,
        results: List[MatterSearchResult]
    ) -> BillingContext:
        """
        API helper to set search results.

        Called by API after searching for matters.
        """
        context.search_results = [
            {
                "matter_id": r.matter_id,
                "matter_name": r.matter_name,
                "client_name": r.client_name,
                "case_type": r.case_type,
                "meruscase_url": r.meruscase_url,
                "match_score": r.match_score,
            }
            for r in results
        ]

        return context

    def build_time_entry(self, context: BillingContext) -> Optional[TimeEntry]:
        """
        Build TimeEntry from collected data.

        Returns:
            TimeEntry object or None if data incomplete
        """
        if not context.entry:
            return None

        try:
            # Parse category
            category_str = context.entry.get("category", "Other")
            try:
                category = BillingCategory(category_str)
            except ValueError:
                category = BillingCategory.OTHER

            # Parse date
            date_str = context.entry.get("entry_date", date.today().isoformat())
            try:
                entry_date = date.fromisoformat(date_str)
            except ValueError:
                entry_date = date.today()

            return TimeEntry(
                hours=float(context.entry.get("hours", 0)),
                description=context.entry.get("description", ""),
                category=category,
                entry_date=entry_date,
                billable=context.entry.get("billable", True),
                timekeeper=context.entry.get("timekeeper"),
                rate=context.entry.get("rate"),
            )
        except Exception:
            return None

    def build_matter_reference(self, context: BillingContext) -> Optional[MatterReference]:
        """
        Build MatterReference from collected data.

        Returns:
            MatterReference object or None if data incomplete
        """
        if not context.matter:
            return None

        try:
            method_str = context.matter.get("method", "search")
            try:
                method = MatterSelectionMethod(method_str)
            except ValueError:
                method = MatterSelectionMethod.SEARCH

            return MatterReference(
                method=method,
                value=context.matter.get("value", ""),
                resolved_id=context.matter.get("matter_id"),
                resolved_name=context.matter.get("matter_name"),
                meruscase_url=context.matter.get("meruscase_url"),
                client_name=context.matter.get("client_name"),
            )
        except Exception:
            return None
