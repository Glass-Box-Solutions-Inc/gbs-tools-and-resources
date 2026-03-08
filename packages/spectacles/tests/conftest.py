"""
Spectacles Test Configuration
Shared fixtures and configuration for all tests
"""

import os
import sys
import tempfile
import pytest
import asyncio
from pathlib import Path
from typing import Generator, AsyncGenerator
from unittest.mock import MagicMock, AsyncMock, patch

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Set test environment
os.environ['ENVIRONMENT'] = 'test'
os.environ['DEBUG'] = 'true'
os.environ['DB_PATH'] = ':memory:'
os.environ['SECRET_KEY'] = 'test-secret-key-12345678901234567890'


# =============================================================================
# Event Loop Fixture
# =============================================================================

@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# =============================================================================
# Database Fixtures
# =============================================================================

@pytest.fixture
def temp_db_path() -> Generator[str, None, None]:
    """Create a temporary database file"""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    yield db_path
    # Cleanup
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture
def initialized_db(temp_db_path: str) -> str:
    """Initialize database with schema"""
    from persistence.utils import initialize_database

    schema_path = project_root / 'setup' / 'schema.sql'
    if schema_path.exists():
        initialize_database(temp_db_path, str(schema_path))
    return temp_db_path


@pytest.fixture
def task_store(initialized_db: str):
    """Create TaskStore with test database"""
    from persistence.task_store import TaskStore
    return TaskStore(db_path=initialized_db)


# =============================================================================
# State Machine Fixtures
# =============================================================================

@pytest.fixture
def checkpoint_store():
    """Create mock checkpoint store"""
    store = MagicMock()
    store.save_checkpoint = AsyncMock(return_value=True)
    store.load_checkpoint = AsyncMock(return_value=None)
    return store


@pytest.fixture
def state_machine(checkpoint_store):
    """Create StateMachine with mock store"""
    from core.state_machine import StateMachine
    return StateMachine(checkpoint_store=checkpoint_store)


# =============================================================================
# API Test Fixtures
# =============================================================================

@pytest.fixture
def test_client():
    """Create FastAPI test client"""
    from fastapi.testclient import TestClient

    # Mock settings to avoid production checks
    with patch('api.config.settings') as mock_settings:
        mock_settings.ENVIRONMENT = 'test'
        mock_settings.DEBUG = True
        mock_settings.is_production = False
        mock_settings.is_development = True
        mock_settings.has_slack = False
        mock_settings.DB_PATH = ':memory:'
        mock_settings.validate_required_for_production.return_value = []

        from api.main import create_app
        app = create_app()

        with TestClient(app) as client:
            yield client


@pytest.fixture
async def async_client():
    """Create async FastAPI test client"""
    from httpx import AsyncClient, ASGITransport

    with patch('api.config.settings') as mock_settings:
        mock_settings.ENVIRONMENT = 'test'
        mock_settings.DEBUG = True
        mock_settings.is_production = False
        mock_settings.is_development = True
        mock_settings.has_slack = False
        mock_settings.DB_PATH = ':memory:'
        mock_settings.validate_required_for_production.return_value = []

        from api.main import create_app
        app = create_app()

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            yield client


# =============================================================================
# Mock Fixtures
# =============================================================================

@pytest.fixture
def mock_browser_client():
    """Create mock browser client"""
    client = MagicMock()
    client.connect = AsyncMock()
    client.disconnect = AsyncMock()
    client.navigate = AsyncMock(return_value=True)
    client.screenshot = AsyncMock(return_value=b'fake_screenshot_data')
    client.click = AsyncMock(return_value=True)
    client.fill = AsyncMock(return_value=True)
    return client


@pytest.fixture
def mock_slack_client():
    """Create mock Slack client"""
    client = MagicMock()
    client.send_notification = AsyncMock(return_value=True)
    client.request_approval = AsyncMock(return_value="msg_123")
    client.send_tunnel_link = AsyncMock(return_value=True)
    return client


@pytest.fixture
def mock_vlm_perceiver():
    """Create mock VLM perceiver"""
    perceiver = MagicMock()
    perceiver.perceive = AsyncMock(return_value={
        "elements": [
            {"type": "button", "text": "Submit", "selector": "#submit-btn"}
        ],
        "page_description": "A login form with username and password fields"
    })
    return perceiver


# =============================================================================
# Sample Data Fixtures
# =============================================================================

@pytest.fixture
def sample_task_data():
    """Sample task creation data"""
    return {
        "goal": "Log in to the application and navigate to settings",
        "start_url": "https://example.com/login",
        "require_approval": True,
        "credentials_key": "test-creds",
        "max_retries": 3,
        "metadata": {"user": "test_user"}
    }


@pytest.fixture
def sample_action_data():
    """Sample action data"""
    return {
        "action_type": "CLICK",
        "target_element": "#submit-button",
        "action_params": {"x": 100, "y": 200},
        "result_status": "SUCCESS",
        "confidence_score": 0.95,
        "duration_ms": 150
    }


@pytest.fixture
def sample_checkpoint_data():
    """Sample checkpoint data"""
    return {
        "browser_state": {
            "url": "https://example.com/dashboard",
            "cookies": [{"name": "session", "value": "abc123"}]
        },
        "action_history": [
            {"type": "NAVIGATE", "url": "https://example.com"},
            {"type": "CLICK", "element": "#login-btn"}
        ],
        "perception_context": {
            "elements": [{"type": "button", "text": "Continue"}]
        }
    }
