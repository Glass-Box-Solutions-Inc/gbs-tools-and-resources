"""
Unit tests for Claude AI agent tools and dispatch.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import pytest
from unittest.mock import AsyncMock
from merus_expert.agent.tools import TOOLS, dispatch_tool
from merus_expert.core.agent import MerusAgentError


class TestToolDefinitions:
    def test_tools_list_has_13_entries(self):
        """Must have exactly 13 tool definitions."""
        assert len(TOOLS) == 13

    def test_all_tools_have_required_fields(self):
        """Every tool must have name, description, and input_schema."""
        for tool in TOOLS:
            assert "name" in tool, f"Tool missing 'name': {tool}"
            assert "description" in tool, f"Tool {tool.get('name')} missing 'description'"
            assert "input_schema" in tool, f"Tool {tool.get('name')} missing 'input_schema'"
            assert isinstance(tool["input_schema"], dict)

    def test_write_tools_present(self):
        """Write tools (bill_time, add_cost, add_note, upload_document) must exist."""
        tool_names = {t["name"] for t in TOOLS}
        write_tools = {"bill_time", "add_cost", "add_note", "upload_document"}
        assert write_tools.issubset(tool_names), f"Missing write tools: {write_tools - tool_names}"


class TestDispatchTool:
    @pytest.mark.asyncio
    async def test_dispatch_unknown_tool_returns_error(self):
        """Unknown tool name should return error dict, not raise."""
        agent = AsyncMock()
        result = await dispatch_tool(agent, "nonexistent_tool", {})
        assert "error" in result
        assert "nonexistent_tool" in result["error"].lower() or "unknown" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_dispatch_find_case_calls_agent(self):
        """dispatch_tool('find_case') should call agent.find_case() with correct args."""
        agent = AsyncMock()
        agent.find_case = AsyncMock(return_value={"id": "56171871"})
        result = await dispatch_tool(agent, "find_case", {"search": "Smith"})
        agent.find_case.assert_called_once_with(search="Smith", limit=50)
        assert result == {"id": "56171871"}

    @pytest.mark.asyncio
    async def test_dispatch_handles_agent_exception(self):
        """dispatch_tool should catch MerusAgentError and return {'error': ...} without raising."""
        agent = AsyncMock()
        agent.find_case = AsyncMock(side_effect=MerusAgentError("Connection failed"))
        result = await dispatch_tool(agent, "find_case", {"search": "Smith"})
        assert "error" in result
        assert "Connection failed" in result["error"]

    @pytest.mark.asyncio
    async def test_dispatch_bill_time_calls_agent(self):
        """dispatch_tool('bill_time') should forward all fields to agent.bill_time()."""
        agent = AsyncMock()
        agent.bill_time = AsyncMock(return_value={"success": True, "activity_id": "999"})
        result = await dispatch_tool(
            agent,
            "bill_time",
            {"case_search": "Smith", "hours": 0.2, "description": "Review"},
        )
        agent.bill_time.assert_called_once()
        call_kwargs = agent.bill_time.call_args.kwargs
        assert call_kwargs["case_search"] == "Smith"
        assert call_kwargs["hours"] == pytest.approx(0.2)
        assert call_kwargs["description"] == "Review"

    @pytest.mark.asyncio
    async def test_dispatch_add_cost_calls_agent(self):
        """dispatch_tool('add_cost') should forward amount as float to agent.add_cost()."""
        agent = AsyncMock()
        agent.add_cost = AsyncMock(return_value={"success": True, "ledger_id": 123})
        result = await dispatch_tool(
            agent,
            "add_cost",
            {"case_search": "Smith", "amount": 25.00, "description": "WCAB Filing Fee"},
        )
        agent.add_cost.assert_called_once()
        call_kwargs = agent.add_cost.call_args.kwargs
        assert call_kwargs["amount"] == pytest.approx(25.00)

    @pytest.mark.asyncio
    async def test_dispatch_get_billing_codes_no_args(self):
        """dispatch_tool('get_billing_codes') should call agent.get_billing_codes() with no args."""
        agent = AsyncMock()
        agent.get_billing_codes = AsyncMock(return_value={"1": {"name": "Code A"}})
        result = await dispatch_tool(agent, "get_billing_codes", {})
        agent.get_billing_codes.assert_called_once_with()
        assert result == {"1": {"name": "Code A"}}
