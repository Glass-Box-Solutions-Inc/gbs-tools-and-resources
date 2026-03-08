"""
MerusCase API Client
Handles OAuth authentication and API requests
"""

import logging
import httpx
from typing import Optional, Dict, Any, List
from datetime import datetime
from pathlib import Path

from .models import (
    Party,
    Activity,
    Document,
    CaseFile,
    APIResponse,
    OAuthToken,
    LedgerEntry,
)

logger = logging.getLogger(__name__)


class MerusCaseAPIClient:
    """
    MerusCase REST API Client.

    Provides direct API access for operations after case creation:
    - Adding parties to cases
    - Adding activities/notes
    - Uploading documents
    - Retrieving case details

    Note: Case creation still requires browser automation as
    MerusCase does not expose a case creation API endpoint.
    """

    BASE_URL = "https://api.meruscase.com"

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        access_token: Optional[str] = None,
        timeout: int = 30,
    ):
        """
        Initialize API client.

        Args:
            client_id: OAuth client ID (for token refresh)
            client_secret: OAuth client secret
            access_token: Pre-existing access token
            timeout: Request timeout in seconds
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self._token: Optional[OAuthToken] = None
        self.timeout = timeout

        if access_token:
            self._token = OAuthToken(access_token=access_token)

        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=timeout,
            headers={"Accept": "application/json"},
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def close(self):
        """Close HTTP client"""
        await self._client.aclose()

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with authentication"""
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token.access_token}"
        return headers

    def _parse_rate_limit(self, response: httpx.Response) -> Dict[str, Any]:
        """Parse rate limit headers from response"""
        return {
            "rate_limit_remaining": response.headers.get("X-RateLimit-Remaining"),
            "rate_limit_reset": response.headers.get("X-RateLimit-Reset"),
        }

    async def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
    ) -> APIResponse:
        """
        Make an API request.

        Args:
            method: HTTP method
            endpoint: API endpoint path
            data: Request body data
            params: Query parameters
            files: Files to upload

        Returns:
            APIResponse with result
        """
        try:
            headers = self._get_headers()

            # Remove Content-Type for file uploads
            if files:
                del headers["Content-Type"]

            response = await self._client.request(
                method=method,
                url=endpoint,
                headers=headers,
                json=data if (data and not files) else None,
                data=data if (data and files) else None,
                params=params,
                files=files,
            )

            rate_limit = self._parse_rate_limit(response)

            if response.status_code == 200:
                body = response.json()
                merus_errors = body.get("errors") if isinstance(body, dict) else None

                if merus_errors:
                    # Normalize: MerusCase can return errors as a list or a single dict
                    error_list = merus_errors if isinstance(merus_errors, list) else [merus_errors]
                    first = error_list[0] if error_list else {}
                    msg = first.get("errorMessage") or first.get("message") or str(first)
                    error_type = first.get("errorType", "api_error")
                    logger.warning(f"MerusCase API error in 200 response: [{error_type}] {msg}")
                    return APIResponse(
                        success=False,
                        data=body,
                        error=f"[{error_type}] {msg}",
                        errors=error_list,
                        rate_limit_remaining=rate_limit.get("rate_limit_remaining"),
                    )

                return APIResponse(
                    success=True,
                    data=body,
                    rate_limit_remaining=rate_limit.get("rate_limit_remaining"),
                )
            elif response.status_code == 401:
                return APIResponse(
                    success=False,
                    error="Authentication failed - invalid or expired token",
                    error_code=401,
                )
            elif response.status_code == 429:
                return APIResponse(
                    success=False,
                    error="Rate limit exceeded",
                    error_code=429,
                    rate_limit_remaining=0,
                    rate_limit_reset=rate_limit.get("rate_limit_reset"),
                )
            else:
                error_data = response.json() if response.content else {}
                return APIResponse(
                    success=False,
                    error=error_data.get("message", f"HTTP {response.status_code}"),
                    error_code=response.status_code,
                    data=error_data,
                )

        except httpx.TimeoutException:
            return APIResponse(
                success=False,
                error="Request timed out",
                error_code=408,
            )
        except Exception as e:
            logger.error(f"API request failed: {e}")
            return APIResponse(
                success=False,
                error=str(e),
            )

    # =========================================================================
    # Case Files
    # =========================================================================

    async def get_case(self, case_file_id: int) -> APIResponse:
        """
        Get case file details.

        Args:
            case_file_id: MerusCase case file ID

        Returns:
            APIResponse with case details
        """
        return await self._request("GET", f"/caseFiles/view/{case_file_id}")

    async def list_cases(
        self,
        case_status: Optional[str] = None,
        case_type: Optional[str] = None,
        open_date_gte: Optional[str] = None,
        open_date_lte: Optional[str] = None,
        limit: int = 100,
    ) -> APIResponse:
        """
        List case files with optional filters.

        Args:
            case_status: Filter by status
            case_type: Filter by type
            open_date_gte: Open date >= (YYYY-MM-DD)
            open_date_lte: Open date <= (YYYY-MM-DD)
            limit: Max results

        Returns:
            APIResponse with case list
        """
        params = {"limit": limit}
        if case_status:
            params["case_status"] = case_status
        if case_type:
            params["case_type"] = case_type
        if open_date_gte:
            params["open_date[gte]"] = open_date_gte
        if open_date_lte:
            params["open_date[lte]"] = open_date_lte

        return await self._request("GET", "/caseFiles/index", params=params)

    async def search_cases(self, file_number: str) -> APIResponse:
        """
        Search for case by file number.

        Args:
            file_number: Case file number to search

        Returns:
            APIResponse with matching cases
        """
        return await self._request(
            "GET",
            "/caseFiles/index",
            params={"file_number": file_number}
        )

    # =========================================================================
    # Parties
    # =========================================================================

    async def add_party(self, party: Party) -> APIResponse:
        """
        Add a party/contact to a case.

        Args:
            party: Party details

        Returns:
            APIResponse with created party ID
        """
        data = {
            "case_file_id": party.case_file_id,
            "party_type": party.party_type.value if hasattr(party.party_type, 'value') else party.party_type,
        }

        if party.first_name:
            data["first_name"] = party.first_name
        if party.last_name:
            data["last_name"] = party.last_name
        if party.company_name:
            data["company_name"] = party.company_name
        if party.email:
            data["email"] = party.email
        if party.phone:
            data["phone"] = party.phone
        if party.address:
            data["address"] = party.address
        if party.city:
            data["city"] = party.city
        if party.state:
            data["state"] = party.state
        if party.zip_code:
            data["zip"] = party.zip_code
        if party.notes:
            data["notes"] = party.notes

        logger.info(f"Adding party to case {party.case_file_id}: {party.first_name} {party.last_name}")
        return await self._request("POST", "/parties/add", data=data)

    async def get_parties(self, case_file_id: int) -> APIResponse:
        """
        Get all parties for a case.

        Args:
            case_file_id: Case file ID

        Returns:
            APIResponse with party list
        """
        return await self._request(
            "GET",
            "/parties/index",
            params={"case_file_id": case_file_id}
        )

    # =========================================================================
    # Activities
    # =========================================================================

    async def add_activity(self, activity: Activity) -> APIResponse:
        """
        Add an activity/note to a case.

        Args:
            activity: Activity details

        Returns:
            APIResponse with created activity ID
        """
        data = {
            "case_file_id": activity.case_file_id,
            "subject": activity.subject,
            "date": activity.date.strftime("%Y-%m-%d %H:%M:%S"),
        }

        if activity.activity_type_id:
            data["activity_type_id"] = activity.activity_type_id
        if activity.description:
            data["description"] = activity.description
        if activity.duration_minutes:
            data["duration"] = activity.duration_minutes
        if activity.billable:
            data["billable"] = 1
        if activity.billing_code_id:
            data["billing_code_id"] = activity.billing_code_id
        if activity.user_id:
            data["user_id"] = activity.user_id

        logger.info(f"Adding activity to case {activity.case_file_id}: {activity.subject}")
        return await self._request("POST", "/activities/add", data=data)

    async def get_activities(
        self,
        case_file_id: int,
        limit: int = 100,
    ) -> APIResponse:
        """
        Get activities for a case.

        Args:
            case_file_id: Case file ID
            limit: Max results

        Returns:
            APIResponse with activity list
        """
        return await self._request(
            "GET",
            "/activities/index",
            params={"case_file_id": case_file_id, "limit": limit}
        )

    async def get_activity_types(self) -> APIResponse:
        """
        Get available activity types.

        Returns:
            APIResponse with activity type list
        """
        return await self._request("GET", "/activityTypes/index")

    # =========================================================================
    # Documents
    # =========================================================================

    async def upload_document(self, document: Document) -> APIResponse:
        """
        Upload a document to a case.

        Args:
            document: Document details with file path

        Returns:
            APIResponse with uploaded document ID
        """
        file_path = Path(document.file_path)
        if not file_path.exists():
            return APIResponse(
                success=False,
                error=f"File not found: {document.file_path}"
            )

        with open(file_path, "rb") as f:
            files = {
                "file": (document.filename, f, "application/octet-stream")
            }
            data = {
                "case_file_id": document.case_file_id,
            }
            if document.description:
                data["description"] = document.description
            if document.folder_id:
                data["folder_id"] = document.folder_id

            logger.info(f"Uploading document to case {document.case_file_id}: {document.filename}")
            return await self._request("POST", "/uploads/add", data=data, files=files)

    # =========================================================================
    # Reference Data
    # =========================================================================

    async def get_billing_codes(self) -> APIResponse:
        """
        Get available billing codes.

        Returns:
            APIResponse with billing code list
        """
        return await self._request("GET", "/billingCodes/index")

    async def get_firm_users(self) -> APIResponse:
        """
        Get firm users (requires admin privileges).

        Returns:
            APIResponse with user list
        """
        return await self._request("GET", "/firmUsers/index")

    # =========================================================================
    # Ledger / Billing
    # =========================================================================

    async def get_open_ledgers(
        self,
        case_file_id: Optional[int] = None,
        date_gte: Optional[str] = None,
        date_lte: Optional[str] = None,
    ) -> APIResponse:
        """
        Get open ledger entries.

        Args:
            case_file_id: Filter by case
            date_gte: Date >= (YYYY-MM-DD)
            date_lte: Date <= (YYYY-MM-DD)

        Returns:
            APIResponse with ledger entries
        """
        params = {}
        if case_file_id:
            params["case_file_id"] = case_file_id
        if date_gte:
            params["date[gte]"] = date_gte
        if date_lte:
            params["date[lte]"] = date_lte

        return await self._request("GET", "/caseLedgersOpen/index", params=params)

    async def add_ledger_entry(self, entry: LedgerEntry) -> APIResponse:
        """
        Add a direct fee/cost ledger entry to a case.

        Use this for filing fees, court costs, expenses, etc.
        For time-based billing, use add_activity() with billable=True.

        Args:
            entry: LedgerEntry with case_file_id, amount, description, date, ledger_type_id

        Returns:
            APIResponse with created ledger entry ID

        Example:
            entry = LedgerEntry(
                case_file_id=56171871,
                amount=25.00,
                description="WCAB Filing Fee",
                ledger_type_id=LedgerType.COST,
            )
            result = await client.add_ledger_entry(entry)
            # Returns: {"success": 1, "data": {"CaseLedger": {"id": 110681047, ...}}}
        """
        payload = entry.to_api_payload()
        logger.info(f"Adding ledger entry to case {entry.case_file_id}: ${entry.amount:.2f} - {entry.description}")
        return await self._request("POST", "/caseLedgers/add", data=payload)

    async def add_billing_entry(
        self,
        case_file_id: int,
        amount: float,
        description: str,
        ledger_type: str = "fee",
    ) -> APIResponse:
        """
        Simplified helper to add a billing entry.

        Args:
            case_file_id: MerusCase case file ID
            amount: Dollar amount
            description: Entry description
            ledger_type: "fee", "cost", or "expense"

        Returns:
            APIResponse with created entry

        Example:
            result = await client.add_billing_entry(
                case_file_id=56171871,
                amount=25.00,
                description="WCAB Filing Fee",
                ledger_type="cost",
            )
        """
        from .models import LedgerType

        type_map = {
            "fee": LedgerType.FEE,
            "cost": LedgerType.COST,
            "expense": LedgerType.EXPENSE,
        }
        ledger_type_id = type_map.get(ledger_type.lower(), LedgerType.FEE)

        entry = LedgerEntry(
            case_file_id=case_file_id,
            amount=amount,
            description=description,
            ledger_type_id=ledger_type_id,
        )
        return await self.add_ledger_entry(entry)

    # =========================================================================
    # Tasks
    # =========================================================================

    async def get_tasks(
        self,
        case_file_id: Optional[int] = None,
        due_date_gte: Optional[str] = None,
        due_date_lte: Optional[str] = None,
    ) -> APIResponse:
        """
        Get tasks.

        Args:
            case_file_id: Filter by case
            due_date_gte: Due date >= (YYYY-MM-DD)
            due_date_lte: Due date <= (YYYY-MM-DD)

        Returns:
            APIResponse with task list
        """
        params = {}
        if case_file_id:
            params["case_file_id"] = case_file_id
        if due_date_gte:
            params["due_date[gte]"] = due_date_gte
        if due_date_lte:
            params["due_date[lte]"] = due_date_lte

        return await self._request("GET", "/tasks/index", params=params)
