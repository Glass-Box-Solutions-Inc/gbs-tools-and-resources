"""
Unit tests for MerusAgent.

Tests normalize, find_case, bill_time with mocked API client.
No live API calls.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import pytest
from datetime import timedelta
from unittest.mock import AsyncMock, patch
from merus_expert.core.agent import MerusAgent, MerusAgentError, CaseNotFoundError, BillingError
from merus_expert.api_client.models import APIResponse


@pytest.fixture
def agent_with_mock_client():
    """MerusAgent with a mocked API client."""
    with patch("merus_expert.core.agent.MerusCaseAPIClient") as MockClient:
        mock_client = AsyncMock()
        MockClient.return_value = mock_client
        agent = MerusAgent(access_token="test_token")
        agent.client = mock_client
        yield agent, mock_client


class TestNormalizeCasesResponse:
    def _make_agent(self):
        """Build a bare MerusAgent instance without going through __init__."""
        agent = MerusAgent.__new__(MerusAgent)
        agent._cache = {}
        agent._cache_timestamps = {}
        agent._cache_ttl = timedelta(seconds=3600)
        return agent

    def test_normalize_dict_format(self):
        """Dict format {id: data} should be converted to a list with 'id' field on each item."""
        agent = self._make_agent()
        data = {
            "56171871": {"file_number": "WC-001", "primary_party_name": "Smith"},
            "56171872": {"file_number": "WC-002", "primary_party_name": "Jones"},
        }
        result = agent._normalize_cases_response(data)
        assert isinstance(result, list)
        assert len(result) == 2
        ids = {r["id"] for r in result}
        assert ids == {"56171871", "56171872"}

    def test_normalize_list_format(self):
        """List format should pass through with the 'id' field preserved."""
        agent = self._make_agent()
        data = [
            {"id": "56171871", "file_number": "WC-001"},
            {"id": "56171872", "file_number": "WC-002"},
        ]
        result = agent._normalize_cases_response(data)
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["id"] == "56171871"

    def test_normalize_unexpected_type(self):
        """Unexpected type (e.g. plain string) should return empty list without raising."""
        agent = self._make_agent()
        result = agent._normalize_cases_response("unexpected_string")
        assert result == []


class TestFindCase:
    @pytest.mark.asyncio
    async def test_find_case_exact_file_number_match(self, agent_with_mock_client):
        """Exact file number match should be returned before fuzzy or name matches."""
        agent, mock_client = agent_with_mock_client
        mock_client.list_cases = AsyncMock(return_value=APIResponse(
            success=True,
            data={"data": [
                {"id": "56171871", "file_number": "WC-2024-001", "primary_party_name": "Smith"},
                {"id": "56171872", "file_number": "WC-2024-002", "primary_party_name": "Jones"},
            ]}
        ))
        result = await agent.find_case("WC-2024-001")
        assert result["id"] == "56171871"
        assert result["file_number"] == "WC-2024-001"

    @pytest.mark.asyncio
    async def test_find_case_party_name_fuzzy(self, agent_with_mock_client):
        """Partial party name (case-insensitive) should match a case."""
        agent, mock_client = agent_with_mock_client
        mock_client.list_cases = AsyncMock(return_value=APIResponse(
            success=True,
            data={"data": [
                {"id": "56171871", "file_number": "WC-001", "primary_party_name": "John Smith"},
            ]}
        ))
        result = await agent.find_case("smith")
        assert result["id"] == "56171871"

    @pytest.mark.asyncio
    async def test_find_case_not_found_raises(self, agent_with_mock_client):
        """Search that matches no case should raise CaseNotFoundError."""
        agent, mock_client = agent_with_mock_client
        mock_client.list_cases = AsyncMock(return_value=APIResponse(
            success=True,
            data={"data": [
                {"id": "56171871", "file_number": "WC-001", "primary_party_name": "Smith"},
            ]}
        ))
        with pytest.raises(CaseNotFoundError):
            await agent.find_case("NoSuchCase_XYZ")

    @pytest.mark.asyncio
    async def test_find_case_api_error_raises(self, agent_with_mock_client):
        """API failure (success=False) should raise MerusAgentError."""
        agent, mock_client = agent_with_mock_client
        mock_client.list_cases = AsyncMock(return_value=APIResponse(
            success=False, error="Connection refused", error_code=503
        ))
        with pytest.raises(MerusAgentError):
            await agent.find_case("anything")


class TestBillTime:
    @pytest.mark.asyncio
    async def test_bill_time_returns_activity_id(self, agent_with_mock_client):
        """Successful bill_time should return dict with success=True and activity_id."""
        agent, mock_client = agent_with_mock_client
        mock_client.list_cases = AsyncMock(return_value=APIResponse(
            success=True,
            data={"data": [
                {"id": "56171871", "file_number": "WC-001", "primary_party_name": "Smith"}
            ]}
        ))
        mock_client.add_activity = AsyncMock(return_value=APIResponse(
            success=True,
            data={"id": "918183874"}
        ))
        result = await agent.bill_time(
            case_search="Smith",
            hours=0.2,
            description="Review medical records",
        )
        assert result["success"] is True
        assert result["activity_id"] == "918183874"
        assert result["hours"] == 0.2
        assert result["minutes"] == 12

    @pytest.mark.asyncio
    async def test_bill_time_hours_to_minutes_conversion(self, agent_with_mock_client):
        """Hours should be accurately converted to integer minutes in the return value."""
        agent, mock_client = agent_with_mock_client
        mock_client.list_cases = AsyncMock(return_value=APIResponse(
            success=True,
            data={"data": [
                {"id": "56171871", "file_number": "WC-001", "primary_party_name": "Smith"}
            ]}
        ))
        mock_client.add_activity = AsyncMock(return_value=APIResponse(
            success=True,
            data={"id": "918183875"}
        ))
        # 1.5 hours = 90 minutes
        result = await agent.bill_time(
            case_search="Smith",
            hours=1.5,
            description="Attend deposition",
        )
        assert result["minutes"] == 90

    @pytest.mark.asyncio
    async def test_bill_time_failure_raises_billing_error(self, agent_with_mock_client):
        """Failed activity creation (success=False) should raise BillingError."""
        agent, mock_client = agent_with_mock_client
        mock_client.list_cases = AsyncMock(return_value=APIResponse(
            success=True,
            data={"data": [
                {"id": "56171871", "file_number": "WC-001", "primary_party_name": "Smith"}
            ]}
        ))
        mock_client.add_activity = AsyncMock(return_value=APIResponse(
            success=False, error="Validation failed", error_code=400
        ))
        with pytest.raises(BillingError):
            await agent.bill_time(case_search="Smith", hours=0.2, description="Test")
