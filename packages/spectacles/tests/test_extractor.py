"""
Unit tests for Pattern Extraction Engine

Tests pattern classification, selector extraction, sequence building,
and success signal detection.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import pytest
from datetime import datetime
from core.memory.extractor import PatternExtractor


class TestPatternExtractor:
    """Test cases for pattern extraction."""

    @pytest.fixture
    def extractor(self):
        """Create pattern extractor instance."""
        return PatternExtractor()

    @pytest.fixture
    def login_task_data(self):
        """Sample login task data."""
        return {
            "task_id": "task-login-123",
            "goal": "login to example.com",
            "start_url": "https://example.com/login",
            "current_state": "COMPLETED",
            "metadata": {
                "final_url": "https://example.com/dashboard"
            }
        }

    @pytest.fixture
    def login_actions(self):
        """Sample login action sequence."""
        return [
            {
                "id": 1,
                "action_type": "NAVIGATE",
                "target_element": "https://example.com/login",
                "result_status": "SUCCESS"
            },
            {
                "id": 2,
                "action_type": "FILL",
                "target_element": "input#email",
                "action_params": {"field_name": "email", "value": "user@example.com"},
                "result_status": "SUCCESS"
            },
            {
                "id": 3,
                "action_type": "FILL",
                "target_element": "input#password",
                "action_params": {"field_name": "password", "value": "******"},
                "result_status": "SUCCESS"
            },
            {
                "id": 4,
                "action_type": "CLICK",
                "target_element": "button[type='submit']",
                "result_data": {"text": "Sign In"},
                "result_status": "SUCCESS"
            }
        ]

    @pytest.fixture
    def form_actions(self):
        """Sample form filling action sequence."""
        return [
            {
                "id": 1,
                "action_type": "FILL",
                "target_element": "input#name",
                "action_params": {"field_name": "name"},
                "result_status": "SUCCESS"
            },
            {
                "id": 2,
                "action_type": "FILL",
                "target_element": "input#address",
                "action_params": {"field_name": "address"},
                "result_status": "SUCCESS"
            },
            {
                "id": 3,
                "action_type": "FILL",
                "target_element": "input#phone",
                "action_params": {"field_name": "phone"},
                "result_status": "SUCCESS"
            },
            {
                "id": 4,
                "action_type": "CLICK",
                "target_element": "button#submit",
                "result_status": "SUCCESS"
            }
        ]

    @pytest.fixture
    def navigation_actions(self):
        """Sample navigation action sequence."""
        return [
            {
                "id": 1,
                "action_type": "CLICK",
                "target_element": "a.menu-item",
                "result_data": {"text": "Products"},
                "result_status": "SUCCESS"
            },
            {
                "id": 2,
                "action_type": "CLICK",
                "target_element": "a.category-link",
                "result_data": {"text": "Electronics"},
                "result_status": "SUCCESS"
            },
            {
                "id": 3,
                "action_type": "CLICK",
                "target_element": "div.product-card",
                "result_data": {"text": "Laptop"},
                "result_status": "SUCCESS"
            }
        ]

    @pytest.mark.asyncio
    async def test_classification_login(self, extractor, login_task_data, login_actions):
        """Test LOGIN_FLOW classification detection (>80% accuracy)."""
        # Extract pattern
        pattern = await extractor.extract_from_task(
            task_id="task-login-123",
            task_data=login_task_data,
            actions=login_actions
        )

        # Verify pattern extracted
        assert pattern is not None
        assert pattern.pattern_type == "LOGIN_FLOW"
        assert pattern.site_domain == "example.com"
        assert pattern.goal == "login to example.com"

    @pytest.mark.asyncio
    async def test_classification_form(self, extractor, form_actions):
        """Test FORM_STRUCTURE classification detection."""
        task_data = {
            "task_id": "task-form-123",
            "goal": "fill contact form",
            "start_url": "https://example.com/contact",
            "current_state": "COMPLETED"
        }

        # Extract pattern
        pattern = await extractor.extract_from_task(
            task_id="task-form-123",
            task_data=task_data,
            actions=form_actions
        )

        # Verify classification
        assert pattern is not None
        assert pattern.pattern_type == "FORM_STRUCTURE"

    @pytest.mark.asyncio
    async def test_classification_navigation(self, extractor, navigation_actions):
        """Test NAVIGATION classification detection."""
        task_data = {
            "task_id": "task-nav-123",
            "goal": "navigate to product page",
            "start_url": "https://example.com/",
            "current_state": "COMPLETED"
        }

        # Extract pattern
        pattern = await extractor.extract_from_task(
            task_id="task-nav-123",
            task_data=task_data,
            actions=navigation_actions
        )

        # Verify classification
        assert pattern is not None
        assert pattern.pattern_type == "NAVIGATION"

    @pytest.mark.asyncio
    async def test_selector_extraction(self, extractor, login_task_data, login_actions):
        """Test semantic selector naming."""
        # Extract pattern
        pattern = await extractor.extract_from_task(
            task_id="task-login-123",
            task_data=login_task_data,
            actions=login_actions
        )

        # Verify selectors extracted with semantic names
        assert pattern is not None
        selectors = pattern.pattern_data.get("selectors", {})

        # Should have semantic names for email, password, and button
        assert len(selectors) > 0

        # Check for semantic naming (email_field, password_field, etc.)
        selector_names = list(selectors.keys())
        has_field_naming = any('field' in name.lower() for name in selector_names)
        has_button_naming = any('button' in name.lower() for name in selector_names)

        assert has_field_naming or has_button_naming

    @pytest.mark.asyncio
    async def test_sequence_building(self, extractor, login_task_data, login_actions):
        """Test action sequence ordering is preserved."""
        # Extract pattern
        pattern = await extractor.extract_from_task(
            task_id="task-login-123",
            task_data=login_task_data,
            actions=login_actions
        )

        # Verify sequence built correctly
        assert pattern is not None
        sequence = pattern.pattern_data.get("sequence", [])

        # Should have same number of steps as actions
        assert len(sequence) == len(login_actions)

        # Verify order preserved (NAVIGATE -> FILL -> FILL -> CLICK)
        assert sequence[0]["action"] == "NAVIGATE"
        assert sequence[1]["action"] == "FILL"
        assert sequence[2]["action"] == "FILL"
        assert sequence[3]["action"] == "CLICK"

        # Verify FILL actions have field information
        assert "field" in sequence[1]
        assert "field" in sequence[2]

    @pytest.mark.asyncio
    async def test_success_signals(self, extractor, login_task_data, login_actions):
        """Test success indicator detection (URL/state changes)."""
        # Extract pattern
        pattern = await extractor.extract_from_task(
            task_id="task-login-123",
            task_data=login_task_data,
            actions=login_actions
        )

        # Verify success signals captured
        assert pattern is not None
        signals = pattern.pattern_data.get("success_indicators", {})

        # Should detect URL change as success signal
        assert "url_contains" in signals or "state" in signals

        # If URL signal present, should be the path from final URL
        if "url_contains" in signals:
            assert "/dashboard" in signals["url_contains"]

    @pytest.mark.asyncio
    async def test_extract_no_actions(self, extractor):
        """Test extraction returns None when no actions available."""
        task_data = {
            "task_id": "task-empty-123",
            "goal": "test task",
            "start_url": "https://example.com",
            "current_state": "COMPLETED"
        }

        # Extract with empty actions
        pattern = await extractor.extract_from_task(
            task_id="task-empty-123",
            task_data=task_data,
            actions=[]
        )

        # Should return None
        assert pattern is None

    @pytest.mark.asyncio
    async def test_extract_incomplete_task(self, extractor, login_actions):
        """Test extraction returns None for incomplete tasks."""
        task_data = {
            "task_id": "task-incomplete-123",
            "goal": "test task",
            "start_url": "https://example.com",
            "current_state": "FAILED"  # Not completed
        }

        # Extract from failed task
        pattern = await extractor.extract_from_task(
            task_id="task-incomplete-123",
            task_data=task_data,
            actions=login_actions
        )

        # Should return None
        assert pattern is None

    def test_classify_pattern_login(self, extractor, login_actions):
        """Test direct classification method for LOGIN_FLOW."""
        pattern_type = extractor._classify_pattern(login_actions)
        assert pattern_type == "LOGIN_FLOW"

    def test_classify_pattern_form(self, extractor, form_actions):
        """Test direct classification method for FORM_STRUCTURE."""
        pattern_type = extractor._classify_pattern(form_actions)
        assert pattern_type == "FORM_STRUCTURE"

    def test_classify_pattern_navigation(self, extractor, navigation_actions):
        """Test direct classification method for NAVIGATION."""
        pattern_type = extractor._classify_pattern(navigation_actions)
        assert pattern_type == "NAVIGATION"

    def test_semantic_name_generation(self, extractor):
        """Test semantic name generation for different action types."""
        # Test FILL action
        fill_action = {
            "action_type": "FILL",
            "target_element": "input#email",
            "action_params": {"field_name": "email"}
        }
        name = extractor._generate_semantic_name(fill_action)
        assert "email" in name.lower()
        assert "field" in name.lower()

        # Test CLICK action
        click_action = {
            "action_type": "CLICK",
            "target_element": "button",
            "result_data": {"text": "Submit"}
        }
        name = extractor._generate_semantic_name(click_action)
        assert "submit" in name.lower()
        assert "button" in name.lower()

    def test_field_name_extraction(self, extractor):
        """Test field name extraction from CSS selectors."""
        # Email field
        assert "email" in extractor._extract_field_name_from_selector("input#email")
        assert "email" in extractor._extract_field_name_from_selector("input[name='email']")

        # Password field
        assert "password" in extractor._extract_field_name_from_selector("input#password")

        # Username field
        assert "username" in extractor._extract_field_name_from_selector("input#username")

        # Generic field
        assert extractor._extract_field_name_from_selector("input.field") == "field"
