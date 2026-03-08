"""
Pattern Extraction Engine - Extract patterns from successful task executions

Automatically classifies and extracts reusable patterns from completed browser
automation tasks. Enables learning and pattern reuse.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import logging
from typing import List, Dict, Optional
from datetime import datetime
from urllib.parse import urlparse

from core.reasoner import Pattern
from persistence.utils import generate_task_id

logger = logging.getLogger(__name__)


class PatternExtractor:
    """
    Extract patterns from successful task executions.

    Capabilities:
    - Automatic pattern classification (LOGIN_FLOW, FORM_STRUCTURE, NAVIGATION, EXTRACTION)
    - Selector extraction with semantic naming
    - Action sequence building
    - Success signal detection
    """

    def __init__(self, db_store=None):
        """
        Initialize pattern extractor.

        Args:
            db_store: TaskStore instance for database access (optional for testing)
        """
        self.db_store = db_store
        logger.info("PatternExtractor initialized")

    async def extract_from_task(self, task_id: str, task_data: Optional[Dict] = None, actions: Optional[List[Dict]] = None) -> Optional[Pattern]:
        """
        Extract pattern from completed task.

        Args:
            task_id: Task ID to extract pattern from
            task_data: Task data dict (if not using db_store)
            actions: List of action dicts (if not using db_store)

        Returns:
            Pattern object or None if extraction failed
        """
        # Get task and actions data
        if task_data is None and self.db_store:
            task_data = self.db_store.get_task(task_id)
            if not task_data:
                logger.warning("Task %s not found", task_id)
                return None

        if actions is None and self.db_store:
            actions = self.db_store.get_task_actions(task_id)

        # Validate we have the data we need
        if not task_data or not actions:
            logger.warning("No task data or actions for task %s", task_id)
            return None

        # Check task completed successfully
        if task_data.get('current_state') not in ['COMPLETED', 'SUCCESS']:
            logger.debug("Task %s not completed successfully (state: %s)",
                        task_id, task_data.get('current_state'))
            return None

        if len(actions) == 0:
            logger.debug("Task %s has no actions to extract from", task_id)
            return None

        logger.info("Extracting pattern from task %s (%d actions)", task_id, len(actions))

        # 1. Classify pattern type
        pattern_type = self._classify_pattern(actions)

        # 2. Extract selectors and sequence
        selectors = self._extract_selectors(actions)
        sequence = self._build_action_sequence(actions)

        # 3. Extract success indicators
        success_indicators = self._extract_success_signals(task_data, actions)

        # 4. Create pattern object
        start_url = task_data.get('start_url', '')
        domain = urlparse(start_url).netloc

        pattern = Pattern(
            id=generate_task_id(),  # Generate unique pattern ID
            site_domain=domain,
            site_url=start_url,
            goal=task_data.get('goal', ''),
            pattern_type=pattern_type,
            pattern_data={
                "selectors": selectors,
                "sequence": sequence,
                "success_indicators": success_indicators
            },
            success_count=1,
            failure_count=0,
            created_at=datetime.utcnow(),
            last_used_at=datetime.utcnow()
        )

        logger.info("Extracted %s pattern for %s (confidence: %.2f)",
                   pattern_type, domain, pattern.confidence)

        return pattern

    def _classify_pattern(self, actions: List[Dict]) -> str:
        """
        Classify pattern type based on action sequence.

        Classification rules:
        - LOGIN_FLOW: Fill fields (email/username + password) + submit
        - FORM_STRUCTURE: Multiple fill actions + submit
        - NAVIGATION: Primarily click actions
        - EXTRACTION: Primarily observe actions
        - GENERIC: Fallback for other patterns

        Args:
            actions: List of action dictionaries

        Returns:
            Pattern type string
        """
        # Count action types
        fills = sum(1 for a in actions if a.get('action_type') == 'FILL')
        clicks = sum(1 for a in actions if a.get('action_type') in ['CLICK', 'DOUBLE_CLICK'])
        observes = sum(1 for a in actions if a.get('action_type') == 'OBSERVE')

        # Extract field names from fill actions
        field_names = []
        for action in actions:
            if action.get('action_type') == 'FILL':
                params = action.get('action_params', {})
                if isinstance(params, dict):
                    # Look for field identifiers in params
                    target = action.get('target_element', '').lower()
                    field_names.append(target)

        # Detect login patterns - require both identifier (email/username) AND password
        has_identifier = any(
            any(keyword in field.lower() for keyword in ['email', 'username', 'login', 'user'])
            for field in field_names
        )
        has_password = any(
            any(keyword in field.lower() for keyword in ['password', 'pass'])
            for field in field_names
        )

        is_login_flow = has_identifier and has_password and fills >= 2

        # Classification logic
        if is_login_flow:
            return "LOGIN_FLOW"
        elif fills > clicks and fills > 2:
            return "FORM_STRUCTURE"
        elif clicks > fills:
            return "NAVIGATION"
        elif observes > (clicks + fills):
            return "EXTRACTION"
        else:
            return "GENERIC"

    def _extract_selectors(self, actions: List[Dict]) -> Dict[str, str]:
        """
        Extract key selectors from actions with semantic naming.

        Args:
            actions: List of action dictionaries

        Returns:
            Dictionary mapping semantic names to CSS selectors
        """
        selectors = {}

        for action in actions:
            selector = action.get('target_element')
            if selector:
                semantic_name = self._generate_semantic_name(action)
                selectors[semantic_name] = selector

        return selectors

    def _build_action_sequence(self, actions: List[Dict]) -> List[Dict]:
        """
        Build ordered action sequence from action history.

        Args:
            actions: List of action dictionaries

        Returns:
            List of action step dictionaries
        """
        sequence = []

        for action in actions:
            action_type = action.get('action_type', 'UNKNOWN')
            target = action.get('target_element') or action.get('result_data', {}).get('text', '')

            step = {
                "action": action_type,
                "target": target
            }

            # Add field information for FILL actions
            if action_type == 'FILL':
                params = action.get('action_params', {})
                if isinstance(params, dict):
                    step["field"] = params.get('field_name', 'unknown_field')

            sequence.append(step)

        return sequence

    def _extract_success_signals(self, task_data: Dict, actions: List[Dict]) -> Dict:
        """
        Extract indicators that task succeeded.

        Args:
            task_data: Task data dictionary
            actions: List of action dictionaries

        Returns:
            Dictionary of success signals
        """
        signals = {}

        # Check for URL change (common success indicator)
        start_url = task_data.get('start_url', '')

        # Look for final URL in last action or task metadata
        final_url = None
        if actions:
            last_action = actions[-1]
            result_data = last_action.get('result_data', {})
            if isinstance(result_data, dict):
                final_url = result_data.get('url')

        if not final_url:
            metadata = task_data.get('metadata', {})
            if isinstance(metadata, dict):
                final_url = metadata.get('final_url')

        # Add URL signal if changed
        if final_url and final_url != start_url:
            signals["url_contains"] = urlparse(final_url).path

        # Check for successful state transition
        if task_data.get('current_state') == 'COMPLETED':
            signals["state"] = "COMPLETED"

        return signals

    def _generate_semantic_name(self, action: Dict) -> str:
        """
        Generate semantic name for selector based on action context.

        Args:
            action: Action dictionary

        Returns:
            Semantic name string
        """
        action_type = action.get('action_type', 'unknown')

        if action_type == 'FILL':
            # Try to extract field name from params or target
            params = action.get('action_params', {})
            if isinstance(params, dict):
                field_name = params.get('field_name', 'field')
            else:
                # Extract from target element selector
                target = action.get('target_element', '')
                field_name = self._extract_field_name_from_selector(target)

            return f"{field_name}_field"

        elif action_type in ['CLICK', 'DOUBLE_CLICK']:
            # Try to get button text or description
            result_data = action.get('result_data', {})
            if isinstance(result_data, dict):
                text = result_data.get('text', 'button')
            else:
                text = 'button'

            text = text.lower().replace(' ', '_')[:20]  # Limit length
            return f"{text}_button"

        else:
            # Generic name based on action type and ID
            action_id = action.get('id', 'unknown')
            if isinstance(action_id, int):
                action_id = str(action_id)[:8]
            return f"{action_type.lower()}_{action_id}"

    def _extract_field_name_from_selector(self, selector: str) -> str:
        """
        Extract field name hint from CSS selector.

        Args:
            selector: CSS selector string

        Returns:
            Field name string
        """
        if not selector:
            return "field"

        # Look for common field name indicators
        selector_lower = selector.lower()

        # Common field types
        if 'email' in selector_lower:
            return 'email'
        elif 'password' in selector_lower or 'pass' in selector_lower:
            return 'password'
        elif 'username' in selector_lower or 'user' in selector_lower:
            return 'username'
        elif 'name' in selector_lower:
            return 'name'
        elif 'phone' in selector_lower:
            return 'phone'
        elif 'address' in selector_lower:
            return 'address'

        # Extract from ID or name attribute if present
        if 'id=' in selector_lower or '#' in selector:
            parts = selector.split('#')
            if len(parts) > 1:
                field_name = parts[1].split('[')[0].split('.')[0]
                return field_name[:20]

        return "field"
