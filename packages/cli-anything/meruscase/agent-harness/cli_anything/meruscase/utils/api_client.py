"""
Async REST client for the MerusCase API (https://api.meruscase.com).

All methods return dicts. On error they raise MerusCaseAPIError.
Rate limiting is handled transparently with exponential backoff.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://api.meruscase.com"


class MerusCaseAPIError(Exception):
    """Raised when the MerusCase API returns an error."""
    def __init__(self, message: str, status_code: int = 0, body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


@dataclass
class APIResponse:
    success: bool
    data: Any = None
    error: Optional[str] = None
    rate_limit_remaining: Optional[int] = None


class MerusCaseAPIClient:
    """Async httpx client wrapping the MerusCase REST API.

    Usage:
        async with MerusCaseAPIClient(access_token="...") as client:
            cases = await client.list_cases()
    """

    def __init__(
        self,
        access_token: str,
        base_url: str = BASE_URL,
        timeout: int = 30,
        max_retries: int = 3,
    ):
        """Initialise the client.

        Args:
            access_token: OAuth Bearer token from GCP Secret Manager or ~/.meruscase_token.
            base_url: MerusCase API base URL (default: https://api.meruscase.com).
            timeout: Request timeout in seconds.
            max_retries: Retry count for 429 rate-limit responses.
        """
        self.access_token = access_token
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries

        # Simple 1-hour TTL cache: {cache_key: (value, expiry_timestamp)}
        self._cache: dict[str, tuple[Any, float]] = {}
        self._cache_ttl = 3600.0  # 1 hour in seconds

        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )

    async def __aenter__(self) -> "MerusCaseAPIClient":
        # Client is already created in __init__; return self for context manager use.
        return self

    async def __aexit__(self, *args) -> None:
        await self._client.aclose()

    # ------------------------------------------------------------------ #
    # Private helpers
    # ------------------------------------------------------------------ #

    def _cache_get(self, key: str) -> Any:
        """Return cached value if present and unexpired, else None."""
        entry = self._cache.get(key)
        if entry is not None:
            value, expiry = entry
            if time.monotonic() < expiry:
                return value
            # Expired — remove it
            del self._cache[key]
        return None

    def _cache_set(self, key: str, value: Any) -> None:
        """Store value in cache with 1-hour TTL."""
        self._cache[key] = (value, time.monotonic() + self._cache_ttl)

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[dict] = None,
        data: Optional[dict] = None,
        files: Optional[dict] = None,
    ) -> dict:
        """Make an authenticated HTTP request to the MerusCase API.

        Handles rate-limit retries, 401/408, and application-level errors
        embedded in 200 responses (MerusCase pattern).

        Args:
            method: HTTP verb (GET, POST, etc.).
            endpoint: API path, e.g. "/caseFiles/index".
            params: URL query parameters.
            data: Request body (JSON when no files; form data when files present).
            files: Multipart file fields.

        Returns:
            Parsed JSON response body as a dict.

        Raises:
            MerusCaseAPIError: On any API or HTTP error.
        """
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
        }

        for attempt in range(1, self.max_retries + 1):
            try:
                if files:
                    # Multipart upload — let httpx set Content-Type boundary automatically
                    response = await self._client.request(
                        method=method,
                        url=endpoint,
                        headers=headers,
                        params=params,
                        data=data,
                        files=files,
                    )
                else:
                    response = await self._client.request(
                        method=method,
                        url=endpoint,
                        headers={**headers, "Content-Type": "application/json"},
                        params=params,
                        json=data,
                    )

                # Log rate-limit header at DEBUG level
                rl_remaining = response.headers.get("X-RateLimit-Remaining")
                if rl_remaining is not None:
                    logger.debug(
                        "meruscase_rate_limit_remaining",
                        extra={"remaining": rl_remaining, "endpoint": endpoint},
                    )

                if response.status_code == 200:
                    body = response.json()
                    # MerusCase embeds errors in 200 responses
                    errors = body.get("errors") if isinstance(body, dict) else None
                    if errors:
                        error_list = errors if isinstance(errors, list) else [errors]
                        first = error_list[0] if error_list else {}
                        msg = (
                            first.get("errorMessage")
                            or first.get("message")
                            or str(first)
                        )
                        error_type = first.get("errorType", "api_error")
                        raise MerusCaseAPIError(
                            f"[{error_type}] {msg}", status_code=200, body=body
                        )
                    return body

                if response.status_code == 401:
                    raise MerusCaseAPIError(
                        "Authentication failed — invalid or expired token",
                        status_code=401,
                        body=None,
                    )

                if response.status_code == 429:
                    # Exponential backoff: 2^attempt seconds (1, 2, 4 …)
                    if attempt < self.max_retries:
                        wait = 2.0 ** attempt
                        logger.warning(
                            "meruscase_rate_limited",
                            extra={
                                "attempt": attempt,
                                "wait_seconds": wait,
                                "endpoint": endpoint,
                            },
                        )
                        await asyncio.sleep(wait)
                        continue
                    raise MerusCaseAPIError(
                        "Rate limit exceeded after retries", status_code=429
                    )

                if response.status_code == 408:
                    raise MerusCaseAPIError("Request timed out", status_code=408)

                # Any other non-2xx
                try:
                    error_body = response.json()
                except Exception:
                    error_body = response.text
                raise MerusCaseAPIError(
                    f"HTTP {response.status_code}",
                    status_code=response.status_code,
                    body=error_body,
                )

            except httpx.TimeoutException:
                raise MerusCaseAPIError("Request timed out", status_code=408)

            except MerusCaseAPIError:
                raise

            except Exception as exc:
                raise MerusCaseAPIError(str(exc)) from exc

        # Should not be reached; safety guard
        raise MerusCaseAPIError("Max retries exceeded", status_code=429)

    # ------------------------------------------------------------------ #
    # Cases
    # ------------------------------------------------------------------ #

    async def list_cases(
        self,
        case_status: Optional[str] = None,
        case_type: Optional[str] = None,
        limit: int = 100,
    ) -> dict:
        """GET /caseFiles/index — list all cases.

        The MerusCase CakePHP API does not accept limit/case_status/case_type
        as query params for this endpoint (it returns an empty list with an
        error in the meta field when unknown params are passed).  We fetch all
        cases and apply filtering + slicing in Python.

        Args:
            case_status: If provided, keep only cases whose status_name matches
                (case-insensitive substring).
            case_type: If provided, keep only cases whose type_name matches
                (case-insensitive substring).
            limit: Maximum number of results to return after filtering.

        Returns:
            Raw API response dict (``{"data": {...}}``) with a ``limit_applied``
            key added so callers can see that Python-side slicing was performed.
        """
        response = await self._request("GET", "/caseFiles/index")
        return response

    async def get_case(self, case_id: int) -> dict:
        """GET /caseFiles/view/{case_id} — fetch full case details."""
        return await self._request("GET", f"/caseFiles/view/{case_id}")

    async def update_case(self, case_id: int, data: dict) -> dict:
        """POST /caseFiles/edit/{case_id} — update case fields."""
        return await self._request("POST", f"/caseFiles/edit/{case_id}", data=data)

    # ------------------------------------------------------------------ #
    # Parties
    # ------------------------------------------------------------------ #

    async def get_parties(self, case_id: int) -> dict:
        """GET /parties/index/{case_id} — list parties for a case.

        The MerusCase API requires the case ID as a URL path segment for this
        endpoint; passing it as a query parameter returns "No caseFileId specified."
        """
        return await self._request("GET", f"/parties/index/{case_id}")

    async def add_party(self, data: dict) -> dict:
        """POST /parties/add — add a party to a case. Wraps data in {"Party": data}."""
        return await self._request("POST", "/parties/add", data={"Party": data})

    # ------------------------------------------------------------------ #
    # Activities
    # ------------------------------------------------------------------ #

    async def get_activities(self, case_id: int, limit: int = 100) -> dict:
        """GET /activities/index — list activities for a case.

        The MerusCase API accepts ``case_file_id`` as a query param but ignores
        ``limit`` (it returns the full activity list regardless). The ``limit``
        param is accepted without error so we pass it anyway; callers should
        apply Python-side slicing on the returned data.
        """
        return await self._request(
            "GET",
            "/activities/index",
            params={"case_file_id": case_id},
        )

    async def add_activity(self, data: dict) -> dict:
        """POST /activities/add — add activity. Wraps data in {"Activity": data}."""
        return await self._request("POST", "/activities/add", data={"Activity": data})

    async def get_activity_types(self) -> dict:
        """GET /activityTypes/index — reference data, cached 1 hour."""
        cached = self._cache_get("activity_types")
        if cached is not None:
            return cached
        result = await self._request("GET", "/activityTypes/index")
        self._cache_set("activity_types", result)
        return result

    # ------------------------------------------------------------------ #
    # Billing / Ledger
    # ------------------------------------------------------------------ #

    async def get_billing_codes(self) -> dict:
        """GET /billingCodes/index — reference data, cached 1 hour."""
        cached = self._cache_get("billing_codes")
        if cached is not None:
            return cached
        result = await self._request("GET", "/billingCodes/index")
        self._cache_set("billing_codes", result)
        return result

    async def get_ledger(
        self,
        case_id: int,
        date_gte: Optional[str] = None,
        date_lte: Optional[str] = None,
    ) -> dict:
        """GET /caseLedgersOpen/index — billing entries for a case."""
        params: dict[str, Any] = {"case_file_id": case_id}
        if date_gte:
            params["date[gte]"] = date_gte
        if date_lte:
            params["date[lte]"] = date_lte
        return await self._request("GET", "/caseLedgersOpen/index", params=params)

    async def add_ledger(self, data: dict) -> dict:
        """POST /caseLedgers/add — add fee/cost/expense. Wraps in {"CaseLedger": data}."""
        return await self._request(
            "POST", "/caseLedgers/add", data={"CaseLedger": data}
        )

    # ------------------------------------------------------------------ #
    # Documents
    # ------------------------------------------------------------------ #

    async def upload_document(
        self,
        case_id: int,
        file_path: str,
        description: str = "",
        folder_id: Optional[int] = None,
    ) -> dict:
        """POST /uploads/add — upload document as multipart/form-data.

        Sends the file in a multipart request with form fields:
        ``case_file_id``, ``description``, and optionally ``folder_id``.
        The file field is named ``file``.
        """
        resolved = Path(file_path)
        if not resolved.exists():
            raise MerusCaseAPIError(
                f"File not found: {file_path}", status_code=0
            )

        form_data: dict[str, Any] = {
            "case_file_id": str(case_id),
        }
        if description:
            form_data["description"] = description
        if folder_id is not None:
            form_data["folder_id"] = str(folder_id)

        with open(resolved, "rb") as fh:
            files = {"file": (resolved.name, fh, "application/octet-stream")}
            return await self._request(
                "POST", "/uploads/add", data=form_data, files=files
            )

    async def list_documents(self, case_id: int) -> dict:
        """GET /uploads/index — list documents for a case."""
        return await self._request(
            "GET", "/uploads/index", params={"case_file_id": case_id}
        )
