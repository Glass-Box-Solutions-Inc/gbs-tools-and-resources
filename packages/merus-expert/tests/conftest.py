"""
Shared test fixtures for merus-expert test suite.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import pytest
from unittest.mock import AsyncMock
from merus_expert.api_client.client import MerusCaseAPIClient
from merus_expert.api_client.models import APIResponse


@pytest.fixture
def api_client():
    """MerusCaseAPIClient initialized with dummy token — no network calls."""
    return MerusCaseAPIClient(access_token="test_token_dummy")


@pytest.fixture
def sample_case():
    """Sample case dict matching MerusCase API response format."""
    return {
        "id": "56171871",
        "file_number": "WC-2024-001",
        "primary_party_name": "John Smith",
        "case_status": "Active",
        "case_type": "Workers Compensation",
        "open_date": "2024-01-15",
    }


@pytest.fixture
def success_response():
    """Factory for successful APIResponse."""
    def _factory(data=None):
        return APIResponse(success=True, data=data or {})
    return _factory


@pytest.fixture
def error_response():
    """Factory for failed APIResponse."""
    def _factory(error="API error", error_code=500):
        return APIResponse(success=False, error=error, error_code=error_code)
    return _factory


@pytest.fixture
def mock_merus_agent(sample_case):
    """MerusAgent with all methods mocked — no API calls."""
    agent = AsyncMock()
    agent.find_case = AsyncMock(return_value=sample_case)
    agent.get_case_details = AsyncMock(return_value=sample_case)
    agent.get_case_billing = AsyncMock(return_value={"data": {}})
    agent.get_case_activities = AsyncMock(return_value=[])
    agent.get_case_parties = AsyncMock(return_value=[])
    agent.list_all_cases = AsyncMock(return_value=[sample_case])
    agent.get_billing_summary = AsyncMock(return_value={
        "case_id": "56171871",
        "case_name": "John Smith",
        "total_amount": 0.0,
        "total_entries": 0,
        "entries": {},
    })
    agent.bill_time = AsyncMock(return_value={
        "success": True,
        "activity_id": "918183874",
        "case_id": "56171871",
        "case_name": "John Smith",
        "hours": 0.2,
        "minutes": 12,
        "description": "Review records",
    })
    agent.add_cost = AsyncMock(return_value={
        "success": True,
        "ledger_id": 110681047,
        "case_id": "56171871",
        "case_name": "John Smith",
        "amount": 25.00,
        "description": "WCAB Filing Fee",
        "type": "cost",
    })
    agent.add_note = AsyncMock(return_value={
        "success": True,
        "activity_id": "918183875",
        "case_id": "56171871",
        "case_name": "John Smith",
        "subject": "Client called",
    })
    agent.get_billing_codes = AsyncMock(return_value={"1": {"name": "Code A"}})
    agent.get_activity_types = AsyncMock(return_value={"1": {"name": "Note"}})
    return agent
