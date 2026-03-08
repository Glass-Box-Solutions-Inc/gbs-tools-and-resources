# @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""
Conversation Flow - Intelligent multi-entity matter data collection.
Upgraded from sequential state machine to non-sequential multi-field extraction.
"""

import re
from enum import Enum
from typing import Optional, Dict, Any, Tuple, List
from pydantic import BaseModel

from merus_expert.models.matter import MatterDetails, CaseType, CaseStatus, BillingInfo


class ConversationState(str, Enum):
    """States in the conversation flow"""
    GREETING = "greeting"
    COLLECT_PRIMARY_PARTY = "collect_primary_party"
    COLLECT_CLIENT_EMAIL = "collect_client_email"
    COLLECT_CLIENT_PHONE = "collect_client_phone"
    COLLECT_CASE_TYPE = "collect_case_type"
    COLLECT_ATTORNEY = "collect_attorney"
    COLLECT_OFFICE = "collect_office"
    COLLECT_VENUE = "collect_venue"
    COLLECT_BILLING = "collect_billing"
    COLLECT_BILLING_AMOUNT = "collect_billing_amount"
    COLLECT_BILLING_DESCRIPTION = "collect_billing_description"
    COLLECT_INITIAL_NOTE = "collect_initial_note"
    CONFIRMATION = "confirmation"
    SUBMIT_CHOICE = "submit_choice"
    COMPLETED = "completed"
    ERROR = "error"


class ConversationContext(BaseModel):
    """Tracks collected data and current state"""
    session_id: str
    state: ConversationState = ConversationState.GREETING
    collected_data: Dict[str, Any] = {}
    validation_errors: list = []
    retry_count: int = 0
    max_retries: int = 3

    class Config:
        use_enum_values = True


# Priority order for field collection
FIELD_PRIORITY = [
    "primary_party",
    "case_type",
    "attorney_responsible",
    "office",
    "venue_based_upon",
    "client_email",
    "client_phone",
    "has_billing",
    "billing_amount_due",    # Only asked if has_billing=True
    "billing_description",   # Only asked if has_billing=True
    "initial_note",
]

# Map field name -> conversation state
FIELD_TO_STATE = {
    "primary_party": ConversationState.COLLECT_PRIMARY_PARTY,
    "client_email": ConversationState.COLLECT_CLIENT_EMAIL,
    "client_phone": ConversationState.COLLECT_CLIENT_PHONE,
    "case_type": ConversationState.COLLECT_CASE_TYPE,
    "attorney_responsible": ConversationState.COLLECT_ATTORNEY,
    "office": ConversationState.COLLECT_OFFICE,
    "venue_based_upon": ConversationState.COLLECT_VENUE,
    "has_billing": ConversationState.COLLECT_BILLING,
    "billing_amount_due": ConversationState.COLLECT_BILLING_AMOUNT,
    "billing_description": ConversationState.COLLECT_BILLING_DESCRIPTION,
    "initial_note": ConversationState.COLLECT_INITIAL_NOTE,
}

# Map state -> field name
STATE_TO_FIELD = {v: k for k, v in FIELD_TO_STATE.items()}

# Friendly question prompts per field
FIELD_PROMPTS = {
    "primary_party": "What is the client or primary party's full name?",
    "case_type": (
        "What type of case is this?\n\n"
        "- Immigration\n"
        "- Workers' Compensation\n"
        "- Family Law\n"
        "- Personal Injury\n"
        "- General"
    ),
    "attorney_responsible": "Who is the responsible attorney? *(Type 'skip' if not applicable)*",
    "office": "Which office should this matter be assigned to? *(Type 'skip' if not applicable)*",
    "venue_based_upon": "What is the venue or jurisdiction? *(Type 'skip' if not applicable)*",
    "client_email": "What is the client's email address? *(Type 'skip' if not available)*",
    "client_phone": "What is the client's phone number? *(Type 'skip' if not available)*",
    "has_billing": "Would you like to add billing information?",
    "billing_amount_due": "What is the initial amount due? *(e.g., 5000 or 5000.00)*",
    "billing_description": "Please provide a billing description. *(Type 'skip' if not applicable)*",
    "initial_note": "Would you like to add an initial note for this case? *(Type your note or 'skip')*",
}

# Quick chips per state
STATE_CHIPS = {
    ConversationState.COLLECT_CASE_TYPE: [
        "Workers' Comp", "Personal Injury", "Family Law", "Immigration", "General"
    ],
    ConversationState.COLLECT_BILLING: ["Yes", "No"],
    ConversationState.COLLECT_CLIENT_EMAIL: ["Skip"],
    ConversationState.COLLECT_CLIENT_PHONE: ["Skip"],
    ConversationState.COLLECT_ATTORNEY: ["Skip"],
    ConversationState.COLLECT_OFFICE: ["Skip"],
    ConversationState.COLLECT_VENUE: ["Skip"],
    ConversationState.COLLECT_BILLING_DESCRIPTION: ["Skip"],
    ConversationState.COLLECT_INITIAL_NOTE: ["Skip"],
    ConversationState.SUBMIT_CHOICE: ["Submit", "Preview", "Edit", "Cancel"],
}


class ConversationFlow:
    """
    Intelligent conversational matter data collection.

    Non-sequential: extracts multiple entities from each message,
    then determines the next uncollected priority field to ask about.
    """

    def __init__(self):
        # IntelligentParser is initialized lazily on first async call
        self._parser = None

    def _get_parser(self):
        """Lazy-initialize the parser (avoids issues at import time)."""
        if self._parser is None:
            from service.services.intelligent_parser import IntelligentParser
            self._parser = IntelligentParser()
        return self._parser

    def get_initial_message(self) -> str:
        """Get the greeting message to start conversation."""
        return (
            "Hello! I'm here to help you create a new matter in MerusCase.\n\n"
            "You can provide multiple details at once - for example:\n"
            "*\"John Doe, Workers' Comp case, attorney Jane Smith\"*\n\n"
            "Let's get started. **What is the client's name?**"
        )

    async def process_input(
        self,
        context: ConversationContext,
        user_input: str
    ) -> Tuple[str, ConversationContext, List[str], Dict[str, Any]]:
        """
        Process user input and return (response, updated_context, quick_chips, collected_fields).

        Args:
            context: Current conversation context
            user_input: User's message

        Returns:
            Tuple of (assistant response, updated context, quick_chips, collected_fields)
        """
        import logging as _logging
        _logger = _logging.getLogger(__name__)

        text = user_input.strip()

        # Handle special restart commands
        if text.lower() in ["restart", "start over", "reset"]:
            new_context = ConversationContext(session_id=context.session_id)
            return self.get_initial_message(), new_context, [], {}

        # Handle submit choice state (explicit action handling)
        if context.state == ConversationState.SUBMIT_CHOICE:
            response, context = self._handle_submit_choice(context, text)
            chips = self._generate_quick_chips(context.state)
            return response, context, chips, self._serialize_collected_fields(context)

        # Extract entities from user message using intelligent parser
        parser = self._get_parser()
        try:
            entities = await parser.extract_entities(text, self._serialize_collected_fields(context))
        except Exception as e:
            _logger.warning(f"Entity extraction error: {e}")
            from service.services.intelligent_parser import ParsedEntities
            entities = ParsedEntities()

        # Import Intent for comparisons
        from service.services.intelligent_parser import Intent

        # Handle intent overrides
        if entities.intent == Intent.SUBMIT:
            context.collected_data["action"] = "submit"
            context.state = ConversationState.COMPLETED
            return (
                "Submitting your matter to MerusCase...\n\nPlease wait while I create the matter."
            ), context, [], self._serialize_collected_fields(context)

        if entities.intent == Intent.PREVIEW:
            context.collected_data["action"] = "preview"
            context.state = ConversationState.COMPLETED
            return (
                "Running a preview (dry-run) of your matter...\n\n"
                "This will show what would be created without actually submitting."
            ), context, [], self._serialize_collected_fields(context)

        if entities.intent == Intent.CANCEL:
            new_context = ConversationContext(session_id=context.session_id)
            return "Cancelled. Type anything to start a new matter.", new_context, [], {}

        # If in GREETING state, treat the entire message as primary party if no entities extracted
        if context.state == ConversationState.GREETING:
            if not entities.primary_party and entities.intent == Intent.DATA:
                if len(text) >= 2:
                    entities.primary_party = text

        # Also handle current state's expected field from raw text
        # This ensures single-field responses work even without Gemini
        if entities.intent in (Intent.DATA, Intent.SKIP):
            current_field = STATE_TO_FIELD.get(context.state)
            if current_field and not getattr(entities, current_field, None):
                if text.lower() == "skip":
                    # Mark field as explicitly skipped
                    context.collected_data[f"_skipped_{current_field}"] = True
                else:
                    validated = self._validate_field(current_field, text)
                    if validated is not None:
                        setattr(entities, current_field, validated)

        # Merge extracted entities into collected_data
        self._merge_entities(context, entities)

        # Determine next uncollected field
        next_field = self._compute_next_field(context)

        if next_field is None:
            # All fields collected - go to confirmation
            context.state = ConversationState.CONFIRMATION
            response = self._generate_summary(context)
            context.state = ConversationState.SUBMIT_CHOICE
            chips = self._generate_quick_chips(ConversationState.SUBMIT_CHOICE)
            return response, context, chips, self._serialize_collected_fields(context)

        # Move to next field state
        next_state = FIELD_TO_STATE[next_field]
        context.state = next_state

        # Build acknowledgment + next question
        ack = self._build_acknowledgment(entities, context)
        question = FIELD_PROMPTS[next_field]
        response = f"{ack}{question}" if ack else question

        chips = self._generate_quick_chips(next_state)
        return response, context, chips, self._serialize_collected_fields(context)

    def _validate_field(self, field: str, text: str):
        """
        Validate and normalize a raw text value for a specific field.

        Returns the validated value or None if invalid.
        """
        text = text.strip()

        if field == "primary_party":
            return text if len(text) >= 2 else None

        elif field == "case_type":
            parser = self._get_parser()
            ct, conf = parser.fuzzy_match_case_type(text)
            if ct:
                return ct
            return None

        elif field == "client_email":
            pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if re.match(pattern, text):
                return text.lower()
            return None

        elif field == "client_phone":
            digits = re.sub(r'\D', '', text)
            if len(digits) == 10:
                return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
            elif len(digits) == 11 and digits[0] == '1':
                return f"({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
            elif len(digits) >= 10:
                return digits
            return None

        elif field == "billing_amount_due":
            try:
                cleaned = text.replace(",", "").replace("$", "").strip()
                amount = float(cleaned)
                return amount if amount >= 0 else None
            except ValueError:
                return None

        elif field == "has_billing":
            affirmative = ["yes", "y", "yeah", "sure", "ok", "okay", "yep"]
            negative = ["no", "n", "nope"]
            lower = text.lower()
            if lower in affirmative:
                return True
            elif lower in negative:
                return False
            return None

        # For free-text fields, accept any non-empty text
        return text if text else None

    def _merge_entities(self, context: ConversationContext, entities) -> None:
        """
        Merge ParsedEntities into context.collected_data.

        Only sets fields that are not already collected and have a value.
        """
        field_map = {
            "primary_party": entities.primary_party,
            "case_type": entities.case_type,
            "attorney_responsible": entities.attorney_responsible,
            "office": entities.office,
            "venue_based_upon": entities.venue_based_upon,
            "client_email": entities.client_email,
            "client_phone": entities.client_phone,
            "has_billing": entities.has_billing,
            "billing_amount_due": entities.billing_amount_due,
            "billing_description": entities.billing_description,
            "initial_note": entities.initial_note,
        }

        for field, value in field_map.items():
            if value is not None and field not in context.collected_data:
                if field == "case_type":
                    # Normalize case type to CaseType enum
                    ct_map = {
                        "workers' compensation": CaseType.WORKERS_COMP,
                        "workers compensation": CaseType.WORKERS_COMP,
                        "personal injury": CaseType.PERSONAL_INJURY,
                        "family law": CaseType.FAMILY_LAW,
                        "immigration": CaseType.IMMIGRATION,
                        "general": CaseType.GENERAL,
                    }
                    normalized = value.lower() if isinstance(value, str) else ""
                    case_type = ct_map.get(normalized)
                    if case_type is None:
                        # Try partial match
                        for k, v in ct_map.items():
                            if k in normalized or normalized in k:
                                case_type = v
                                break
                    if case_type:
                        context.collected_data[field] = case_type
                else:
                    context.collected_data[field] = value

    def _compute_next_field(self, context: ConversationContext) -> Optional[str]:
        """
        Determine the highest-priority uncollected field.

        Returns:
            Field name to ask about next, or None if all collected.
        """
        has_billing = context.collected_data.get("has_billing")

        for field in FIELD_PRIORITY:
            # Skip billing sub-fields if user declined billing
            if field in ("billing_amount_due", "billing_description"):
                if has_billing is False:
                    continue
                # Only ask billing sub-fields if has_billing is explicitly True
                if has_billing is None:
                    continue

            # Check if explicitly skipped
            if f"_skipped_{field}" in context.collected_data:
                continue

            # Check if already collected
            if field in context.collected_data and context.collected_data[field] is not None:
                continue

            return field

        return None

    def _build_acknowledgment(self, entities, context: ConversationContext) -> str:
        """Build a brief acknowledgment of what was just extracted."""
        acks = []

        if entities.primary_party and "primary_party" in context.collected_data:
            acks.append(f"Got it - **{entities.primary_party}**.")
        if entities.case_type:
            ct_val = context.collected_data.get("case_type")
            ct_display = ct_val.value if hasattr(ct_val, "value") else str(ct_val) if ct_val else entities.case_type
            acks.append(f"Case type: **{ct_display}**.")
        if entities.attorney_responsible and "attorney_responsible" in context.collected_data:
            acks.append(f"Attorney: **{entities.attorney_responsible}**.")

        if acks:
            return " ".join(acks) + "\n\n"
        return ""

    def _generate_quick_chips(self, state: ConversationState) -> List[str]:
        """Return quick-reply chip suggestions for the given state."""
        return STATE_CHIPS.get(state, [])

    def _serialize_collected_fields(self, context: ConversationContext) -> Dict[str, Any]:
        """Serialize collected_data for API response (handles enum values)."""
        result = {}
        for key, value in context.collected_data.items():
            if key.startswith("_"):
                continue  # Skip internal keys
            if hasattr(value, "value"):
                result[key] = value.value
            else:
                result[key] = value
        return result

    def _generate_summary(self, context: ConversationContext) -> str:
        """Generate confirmation summary from collected data."""
        data = context.collected_data

        summary = "Great! Here's what I've collected:\n\n"
        summary += "---\n"
        summary += f"**Client Name:** {data.get('primary_party', 'Not specified')}\n"

        if data.get("client_email"):
            summary += f"**Email:** {data['client_email']}\n"
        if data.get("client_phone"):
            summary += f"**Phone:** {data['client_phone']}\n"

        case_type = data.get("case_type")
        if case_type:
            case_type_display = case_type.value if hasattr(case_type, "value") else str(case_type)
            summary += f"**Case Type:** {case_type_display}\n"

        if data.get("attorney_responsible"):
            summary += f"**Attorney:** {data['attorney_responsible']}\n"
        if data.get("office"):
            summary += f"**Office:** {data['office']}\n"
        if data.get("venue_based_upon"):
            summary += f"**Venue:** {data['venue_based_upon']}\n"

        if data.get("has_billing"):
            summary += "\n**Billing Information:**\n"
            amount = data.get("billing_amount_due", 0)
            summary += f"- Amount Due: ${amount:,.2f}\n"
            if data.get("billing_description"):
                summary += f"- Description: {data['billing_description']}\n"

        if data.get("initial_note"):
            summary += f"\n**Initial Note:**\n{data['initial_note']}\n"

        summary += "\n---\n\n"
        summary += (
            "Ready to proceed?\n\n"
            "- Type **Submit** to create the matter in MerusCase\n"
            "- Type **Preview** for a dry-run preview\n"
            "- Type **Edit** to make changes\n"
            "- Type **Cancel** to start over"
        )

        return summary

    def _handle_submit_choice(
        self,
        context: ConversationContext,
        text: str
    ) -> Tuple[str, ConversationContext]:
        """Handle user's choice at submit stage."""
        choice = text.lower().strip()

        if choice in ["submit", "yes", "create", "save"]:
            context.collected_data["action"] = "submit"
            context.state = ConversationState.COMPLETED
            return (
                "Submitting your matter to MerusCase...\n\nPlease wait while I create the matter."
            ), context

        elif choice in ["preview", "dry-run", "test", "dry run"]:
            context.collected_data["action"] = "preview"
            context.state = ConversationState.COMPLETED
            return (
                "Running a preview (dry-run) of your matter...\n\n"
                "This will show what would be created without actually submitting."
            ), context

        elif choice in ["edit", "change", "modify", "back"]:
            context.state = ConversationState.GREETING
            return "Let's start over. What is the client's name?", context

        elif choice in ["cancel", "quit", "exit", "stop"]:
            new_context = ConversationContext(session_id=context.session_id)
            return "Cancelled. Type anything to start a new matter.", new_context

        return (
            "I didn't understand that. Please type:\n"
            "- **Submit** to create the matter\n"
            "- **Preview** for a dry-run\n"
            "- **Edit** to make changes\n"
            "- **Cancel** to start over"
        ), context

    def build_matter_details(self, context: ConversationContext) -> MatterDetails:
        """Convert collected data to MatterDetails model."""
        data = context.collected_data

        billing_info = None
        if data.get("has_billing") and data.get("billing_amount_due"):
            billing_info = BillingInfo(
                amount_due=data.get("billing_amount_due"),
                description=data.get("billing_description")
            )

        return MatterDetails(
            primary_party=data["primary_party"],
            case_type=data.get("case_type"),
            attorney_responsible=data.get("attorney_responsible"),
            office=data.get("office"),
            venue_based_upon=data.get("venue_based_upon"),
            billing_info=billing_info
        )

    def get_action(self, context: ConversationContext) -> Optional[str]:
        """Get the action to perform (submit/preview) if conversation is complete."""
        if context.state == ConversationState.COMPLETED:
            return context.collected_data.get("action")
        return None
