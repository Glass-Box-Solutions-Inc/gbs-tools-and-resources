"""
Tests for MerusCaseAPIClient._request() error-in-200 handling.

MerusCase (CakePHP) returns HTTP 200 even for application-level errors,
embedding them in the body as {"errors": [{"errorType": "...", "errorMessage": "..."}]}.
These tests verify that _request() correctly treats such responses as failures.

No live network calls are made — httpx.AsyncClient.request is mocked throughout.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from meruscase_api.client import MerusCaseAPIClient


def _make_response(status_code: int, json_body=None, headers=None):
    """Build a mock httpx.Response."""
    response = MagicMock()
    response.status_code = status_code
    response.headers = headers or {}
    response.content = b"body" if json_body is not None else b""
    response.json = MagicMock(return_value=json_body)
    return response


@pytest.fixture
def client():
    """MerusCaseAPIClient with a pre-set dummy token (skips auth flow)."""
    return MerusCaseAPIClient(access_token="test-token")


# ---------------------------------------------------------------------------
# 1. HTTP 200, no errors → success
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_200_no_errors_is_success(client):
    """Clean 200 with data and no 'errors' key → success=True."""
    body = {"CaseFile": {"id": 42, "file_number": "2024-001"}}
    mock_resp = _make_response(200, body)

    with patch.object(client._client, "request", new=AsyncMock(return_value=mock_resp)):
        result = await client._request("GET", "/caseFiles/view/42")

    assert result.success is True
    assert result.data == body
    assert result.errors is None
    assert result.error is None


# ---------------------------------------------------------------------------
# 2. HTTP 200, errors list → failure
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_200_errors_list_is_failure(client):
    """200 with errors list → success=False, error message extracted from first item."""
    body = {
        "errors": [
            {"errorType": "not_allowed", "errorMessage": "You do not have privilege to perform this action"}
        ]
    }
    mock_resp = _make_response(200, body)

    with patch.object(client._client, "request", new=AsyncMock(return_value=mock_resp)):
        result = await client._request("POST", "/parties/add", data={})

    assert result.success is False
    assert result.errors == body["errors"]
    assert "not_allowed" in result.error
    assert "You do not have privilege" in result.error
    assert result.data == body


# ---------------------------------------------------------------------------
# 3. HTTP 200, errors as dict (not list) → normalized to list, failure
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_200_errors_dict_normalized_to_list(client):
    """200 with errors as a plain dict (not a list) is normalized to a single-item list."""
    body = {"errors": {"errorMessage": "Invalid request"}}
    mock_resp = _make_response(200, body)

    with patch.object(client._client, "request", new=AsyncMock(return_value=mock_resp)):
        result = await client._request("POST", "/caseLedgers/add", data={})

    assert result.success is False
    assert isinstance(result.errors, list)
    assert len(result.errors) == 1
    assert result.errors[0] == {"errorMessage": "Invalid request"}
    assert "Invalid request" in result.error


# ---------------------------------------------------------------------------
# 4. HTTP 200, empty errors list → success (empty list is not an error)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_200_empty_errors_list_is_success(client):
    """200 with errors=[] should be treated as success — falsy empty list, no errors."""
    body = {"errors": [], "CaseFile": {"id": 99}}
    mock_resp = _make_response(200, body)

    with patch.object(client._client, "request", new=AsyncMock(return_value=mock_resp)):
        result = await client._request("GET", "/caseFiles/view/99")

    assert result.success is True
    assert result.errors is None


# ---------------------------------------------------------------------------
# 5. HTTP 401 → failure with error_code
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_401_returns_failure(client):
    """HTTP 401 → success=False, error_code=401."""
    mock_resp = _make_response(401, {"message": "Unauthorized"})

    with patch.object(client._client, "request", new=AsyncMock(return_value=mock_resp)):
        result = await client._request("GET", "/caseFiles/view/1")

    assert result.success is False
    assert result.error_code == 401
    assert "Authentication" in result.error or "auth" in result.error.lower()


# ---------------------------------------------------------------------------
# 6. HTTP 429 → failure with rate limit info
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_429_returns_rate_limit_failure(client):
    """HTTP 429 → success=False, error_code=429, rate_limit_remaining=0."""
    mock_resp = _make_response(429, None, headers={"X-RateLimit-Reset": "1700000000"})
    mock_resp.content = b""

    with patch.object(client._client, "request", new=AsyncMock(return_value=mock_resp)):
        result = await client._request("POST", "/parties/add", data={})

    assert result.success is False
    assert result.error_code == 429
    assert result.rate_limit_remaining == 0


# ---------------------------------------------------------------------------
# 7. Timeout → failure with error_code 408
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_timeout_returns_408(client):
    """httpx.TimeoutException → success=False, error_code=408."""
    import httpx

    with patch.object(client._client, "request", new=AsyncMock(side_effect=httpx.TimeoutException("timed out"))):
        result = await client._request("GET", "/caseFiles/view/1")

    assert result.success is False
    assert result.error_code == 408
    assert "timed out" in result.error.lower() or "timeout" in result.error.lower()
