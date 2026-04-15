"""
MerusAgent - Intelligent MerusCase API Agent

High-level agent for interacting with MerusCase API:
- Pull information (cases, billing, documents, parties)
- Push billing entries (time-based and direct costs)
- Natural language case search
- Reference data caching
- Intelligent error handling

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import logging
from typing import Optional, Dict, Any, List, Union
from datetime import datetime, timedelta
from pathlib import Path
import json

from merus_expert.api_client.client import MerusCaseAPIClient
from merus_expert.api_client.models import (
    Activity,
    LedgerEntry,
    LedgerType,
    APIResponse,
    Party,
    PartyType,
    Document,
)

logger = logging.getLogger(__name__)


class MerusAgentError(Exception):
    """Base exception for MerusAgent errors"""
    pass


class CaseNotFoundError(MerusAgentError):
    """Raised when case cannot be found"""
    pass


class BillingError(MerusAgentError):
    """Raised when billing operation fails"""
    pass


class MerusAgent:
    """
    Intelligent MerusCase API Agent.

    Provides high-level interface for common operations:
    - Natural language case search
    - Smart billing entry creation
    - Cached reference data
    - Error handling with retries

    Example:
        agent = MerusAgent(access_token="your_token")

        # Pull information
        case = await agent.find_case("Smith")
        billing = await agent.get_case_billing(case_id)

        # Push billing entries
        await agent.bill_time(
            case_search="Smith",
            hours=0.2,
            description="Review medical records"
        )

        await agent.add_cost(
            case_search="Smith",
            amount=25.00,
            description="WCAB Filing Fee"
        )
    """

    def __init__(
        self,
        access_token: Optional[str] = None,
        token_file: Optional[str] = ".meruscase_token",
        cache_ttl_seconds: int = 3600,
    ):
        """
        Initialize MerusAgent.

        Args:
            access_token: OAuth access token (or will read from token_file)
            token_file: Path to file containing token
            cache_ttl_seconds: How long to cache reference data (default: 1 hour)
        """
        # Load token
        if not access_token and token_file:
            token_path = Path(token_file)
            if token_path.exists():
                access_token = token_path.read_text().strip()
            else:
                raise MerusAgentError(f"Token file not found: {token_file}")

        if not access_token:
            raise MerusAgentError("No access token provided")

        # Initialize API client
        self.client = MerusCaseAPIClient(access_token=access_token)

        # Reference data cache
        self._cache: Dict[str, Any] = {}
        self._cache_timestamps: Dict[str, datetime] = {}
        self._cache_ttl = timedelta(seconds=cache_ttl_seconds)

        logger.info("MerusAgent initialized")

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def close(self):
        """Close API client"""
        await self.client.close()

    def _normalize_cases_response(self, cases_data: Union[Dict, List]) -> List[Dict[str, Any]]:
        """
        Normalize API cases response to a consistent list format.
        
        Handles both dict format {'case_id': {data}} and list format [{data}].
        
        Args:
            cases_data: Either dict or list from API response
            
        Returns:
            List of case dicts with 'id' field
        """
        if isinstance(cases_data, list):
            # List format: [{'id': '123', ...}, {'id': '456', ...}]
            # Ensure each case has 'id' field
            return [
                {**case, 'id': case.get('id', case.get('case_id'))} 
                for case in cases_data
            ]
        elif isinstance(cases_data, dict):
            # Dict format: {'123': {...}, '456': {...}}
            # Convert to list with id field
            return [
                {'id': case_id, **case_data} 
                for case_id, case_data in cases_data.items()
            ]
        else:
            # Unexpected format, return empty list
            logger.warning(f"Unexpected cases data type: {type(cases_data)}")
            return []


    # =========================================================================
    # PULL OPERATIONS (READ)
    # =========================================================================

    async def find_case(
        self,
        search: str,
        limit: int = 50,
    ) -> Optional[Dict[str, Any]]:
        """
        Find a case by file number or party name (fuzzy search).

        Args:
            search: File number or party name to search
            limit: Max cases to search through

        Returns:
            Case data dict if found, None otherwise

        Raises:
            CaseNotFoundError: If no matching case found

        Example:
            case = await agent.find_case("Smith")
            case = await agent.find_case("WC-2024-001")
        """
        search_lower = search.lower()

        # Search through cases
        response = await self.client.list_cases(limit=limit)

        if not response.success or not response.data:
            raise MerusAgentError(f"Failed to list cases: {response.error}")

        # Normalize response to list format (handles both dict and list)
        cases_data = response.data.get("data", {})
        cases_list = self._normalize_cases_response(cases_data)

        # Try exact file number match first
        for case in cases_list:
            file_number = str(case.get("file_number", "")).lower()
            if file_number == search_lower:
                logger.info(f"Found case by exact file number: {case.get('id')}")
                return case

        # Try fuzzy match on file number
        for case in cases_list:
            file_number = str(case.get("file_number", "")).lower()
            if search_lower in file_number:
                logger.info(f"Found case by file number match: {case.get('id')}")
                return case

        # Try fuzzy match on party name
        for case in cases_list:
            party_name = str(case.get("primary_party_name", "")).lower()
            if search_lower in party_name:
                logger.info(f"Found case by party name match: {case.get('id')}")
                return case

        raise CaseNotFoundError(f"No case found matching '{search}'")

    async def get_case_details(self, case_id: int) -> Dict[str, Any]:
        """
        Get full case details.

        Args:
            case_id: MerusCase case file ID

        Returns:
            Complete case details

        Example:
            details = await agent.get_case_details(123456)
        """
        response = await self.client.get_case(case_id)

        if not response.success:
            raise MerusAgentError(f"Failed to get case {case_id}: {response.error}")

        return response.data

    async def get_case_billing(
        self,
        case_id: int,
        date_gte: Optional[str] = None,
        date_lte: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get billing/ledger entries for a case.

        Args:
            case_id: MerusCase case file ID
            date_gte: Start date (YYYY-MM-DD)
            date_lte: End date (YYYY-MM-DD)

        Returns:
            Dict with ledger entries

        Example:
            billing = await agent.get_case_billing(123456)
            last_month = await agent.get_case_billing(
                123456,
                date_gte="2024-12-01",
                date_lte="2024-12-31"
            )
        """
        response = await self.client.get_open_ledgers(
            case_file_id=case_id,
            date_gte=date_gte,
            date_lte=date_lte,
        )

        if not response.success:
            raise MerusAgentError(f"Failed to get billing: {response.error}")

        return response.data

    async def get_case_activities(
        self,
        case_id: int,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Get activities/notes for a case.

        Args:
            case_id: MerusCase case file ID
            limit: Max results

        Returns:
            List of activity dicts

        Example:
            activities = await agent.get_case_activities(123456)
        """
        response = await self.client.get_activities(case_id, limit=limit)

        if not response.success:
            raise MerusAgentError(f"Failed to get activities: {response.error}")

        # Convert dict to list
        activities_dict = response.data.get("data", {})
        return list(activities_dict.values())

    async def get_case_parties(self, case_id: int) -> List[Dict[str, Any]]:
        """
        Get parties/contacts for a case.

        Args:
            case_id: MerusCase case file ID

        Returns:
            List of party dicts

        Example:
            parties = await agent.get_case_parties(123456)
        """
        response = await self.client.get_parties(case_id)

        if not response.success:
            raise MerusAgentError(f"Failed to get parties: {response.error}")

        return response.data

    async def list_all_cases(
        self,
        case_status: Optional[str] = None,
        case_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        List all cases with optional filters.

        Args:
            case_status: Filter by status (e.g., "Active", "Closed")
            case_type: Filter by type (e.g., "Workers Compensation")
            limit: Max results

        Returns:
            List of case dicts

        Example:
            active_cases = await agent.list_all_cases(case_status="Active")
            wc_cases = await agent.list_all_cases(case_type="Workers Compensation")
        """
        response = await self.client.list_cases(
            case_status=case_status,
            case_type=case_type,
            limit=limit,
        )

        if not response.success:
            raise MerusAgentError(f"Failed to list cases: {response.error}")

        # Normalize response to list format (handles both dict and list)
        cases_data = response.data.get("data", {})
        return self._normalize_cases_response(cases_data)

    # =========================================================================
    # PUSH OPERATIONS (CREATE)
    # =========================================================================

    async def bill_time(
        self,
        case_search: str,
        hours: float,
        description: str,
        subject: Optional[str] = None,
        activity_type_id: Optional[int] = None,
        billing_code_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Bill time to a case (natural language).

        Creates a billable activity entry. Finds case automatically.

        Args:
            case_search: Case file number or party name
            hours: Time in hours (e.g., 0.2 for 12 minutes)
            description: Detailed description of work
            subject: Short subject line (defaults to first 50 chars of description)
            activity_type_id: Activity type (optional)
            billing_code_id: Billing code (optional)

        Returns:
            Dict with success status and activity ID

        Raises:
            CaseNotFoundError: If case cannot be found
            BillingError: If billing entry fails

        Example:
            # Bill 0.2 hours (12 minutes)
            result = await agent.bill_time(
                case_search="Smith",
                hours=0.2,
                description="Review medical records and QME report"
            )

            # Result: {"success": True, "activity_id": "918183874", "case_id": "56171871"}
        """
        # Find the case
        case = await self.find_case(case_search)
        case_id = int(case["id"])

        # Convert hours to minutes
        minutes = int(hours * 60)

        # Default subject to first 50 chars of description
        if not subject:
            subject = description[:50]

        # Create activity
        activity = Activity(
            case_file_id=case_id,
            subject=subject,
            description=description,
            date=datetime.now(),
            duration_minutes=minutes,
            billable=True,
            activity_type_id=activity_type_id,
            billing_code_id=billing_code_id,
        )

        logger.info(f"Billing {hours} hours ({minutes} minutes) to case {case_id}: {subject}")

        response = await self.client.add_activity(activity)

        if not response.success:
            raise BillingError(f"Failed to bill time: {response.error}")

        activity_id = response.data.get("id")

        return {
            "success": True,
            "activity_id": activity_id,
            "case_id": case_id,
            "case_name": case.get("primary_party_name"),
            "hours": hours,
            "minutes": minutes,
            "description": description,
        }

    async def add_cost(
        self,
        case_search: str,
        amount: float,
        description: str,
        ledger_type: str = "cost",
    ) -> Dict[str, Any]:
        """
        Add a direct cost/fee to a case (natural language).

        Creates a ledger entry for filing fees, court costs, expenses, etc.
        For time-based billing, use bill_time() instead.

        Args:
            case_search: Case file number or party name
            amount: Dollar amount (e.g., 25.00)
            description: Entry description
            ledger_type: "fee", "cost", or "expense" (default: "cost")

        Returns:
            Dict with success status and ledger entry ID

        Raises:
            CaseNotFoundError: If case cannot be found
            BillingError: If ledger entry fails

        Example:
            # Add filing fee
            result = await agent.add_cost(
                case_search="Smith",
                amount=25.00,
                description="WCAB Filing Fee"
            )

            # Result: {"success": True, "ledger_id": 110681047, "case_id": "56171871"}
        """
        # Find the case
        case = await self.find_case(case_search)
        case_id = int(case["id"])

        # Map ledger type
        type_map = {
            "fee": LedgerType.FEE,
            "cost": LedgerType.COST,
            "expense": LedgerType.EXPENSE,
        }
        ledger_type_id = type_map.get(ledger_type.lower(), LedgerType.COST)

        # Create ledger entry
        entry = LedgerEntry(
            case_file_id=case_id,
            amount=amount,
            description=description,
            ledger_type_id=ledger_type_id,
        )

        logger.info(f"Adding ${amount:.2f} {ledger_type} to case {case_id}: {description}")

        response = await self.client.add_ledger_entry(entry)

        if not response.success:
            raise BillingError(f"Failed to add cost: {response.error}")

        # Extract ledger ID from response
        ledger_data = response.data.get("data", {}).get("CaseLedger", {})
        ledger_id = ledger_data.get("id")

        return {
            "success": True,
            "ledger_id": ledger_id,
            "case_id": case_id,
            "case_name": case.get("primary_party_name"),
            "amount": amount,
            "description": description,
            "type": ledger_type,
        }

    async def add_note(
        self,
        case_search: str,
        subject: str,
        description: Optional[str] = None,
        activity_type_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Add a non-billable note/activity to a case.

        Args:
            case_search: Case file number or party name
            subject: Note subject
            description: Note details (optional)
            activity_type_id: Activity type (optional)

        Returns:
            Dict with success status and activity ID

        Example:
            result = await agent.add_note(
                case_search="Smith",
                subject="Client called",
                description="Discussed upcoming MSC hearing"
            )
        """
        # Find the case
        case = await self.find_case(case_search)
        case_id = int(case["id"])

        # Create non-billable activity
        activity = Activity(
            case_file_id=case_id,
            subject=subject,
            description=description,
            date=datetime.now(),
            billable=False,
            activity_type_id=activity_type_id,
        )

        logger.info(f"Adding note to case {case_id}: {subject}")

        response = await self.client.add_activity(activity)

        if not response.success:
            raise MerusAgentError(f"Failed to add note: {response.error}")

        activity_id = response.data.get("id")

        return {
            "success": True,
            "activity_id": activity_id,
            "case_id": case_id,
            "case_name": case.get("primary_party_name"),
            "subject": subject,
        }

    # =========================================================================
    # REFERENCE DATA (with caching)
    # =========================================================================

    async def _get_cached(self, key: str, fetch_func) -> Any:
        """Get cached data or fetch if expired."""
        now = datetime.now()

        # Check if cached and not expired
        if key in self._cache:
            cached_time = self._cache_timestamps.get(key)
            if cached_time and (now - cached_time) < self._cache_ttl:
                logger.debug(f"Using cached {key}")
                return self._cache[key]

        # Fetch fresh data
        logger.debug(f"Fetching fresh {key}")
        data = await fetch_func()

        # Cache it
        self._cache[key] = data
        self._cache_timestamps[key] = now

        return data

    async def get_billing_codes(self) -> Dict[str, Any]:
        """
        Get billing codes (cached).

        Returns:
            Dict of billing codes keyed by ID
        """
        async def fetch():
            response = await self.client.get_billing_codes()
            if not response.success:
                raise MerusAgentError(f"Failed to get billing codes: {response.error}")
            return response.data.get("data", {})

        return await self._get_cached("billing_codes", fetch)

    async def get_activity_types(self) -> Dict[str, Any]:
        """
        Get activity types (cached).

        Returns:
            Dict of activity types keyed by ID
        """
        async def fetch():
            response = await self.client.get_activity_types()
            if not response.success:
                raise MerusAgentError(f"Failed to get activity types: {response.error}")
            return response.data.get("data", {})

        return await self._get_cached("activity_types", fetch)

    async def upload_document(
        self,
        case_search: str,
        file_path: str,
        description: Optional[str] = None,
        folder_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Upload document to a case using natural language case search.

        Args:
            case_search: Case file number or party name
            file_path: Local path to file
            description: Optional document description
            folder_id: Optional folder ID within case

        Returns:
            Dict with success status, case_id, filename, and upload data
        """
        case = await self.find_case(case_search)
        case_id = int(case["id"])
        p = Path(file_path)
        doc = Document(
            case_file_id=case_id,
            filename=p.name,
            file_path=str(p),
            description=description,
            folder_id=folder_id,
        )
        response = await self.client.upload_document(doc)
        if not response.success:
            raise MerusAgentError(f"Upload failed: {response.error}")
        return {
            "success": True,
            "case_id": case_id,
            "filename": p.name,
            "data": response.data,
        }

    async def create_case(
        self,
        party_name: str,
        case_type: str = "Workers Compensation",
        date_opened: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a new MerusCase case via Browserless browser automation.

        Uses HybridMatterBuilder which handles browser login, form fill, and
        submission via the Browserless cloud browser (bypasses reCAPTCHA).

        Args:
            party_name: Primary party name. Format: "LASTNAME, FIRSTNAME" or "FIRSTNAME LASTNAME".
            case_type: Case type string (default: "Workers Compensation").
            date_opened: Date opened in MM/DD/YYYY format. Defaults to today.

        Returns:
            dict: {success, meruscase_id, url, party_name, case_type}
        """
        try:
            from merus_expert.automation.hybrid_matter_builder import HybridMatterBuilder
            from merus_expert.models.matter import MatterDetails, CaseType
            from merus_expert.security.config import SecurityConfig

            # Default date_opened to today if not supplied
            if not date_opened:
                date_opened = datetime.now().strftime("%m/%d/%Y")

            # Parse party name: "LASTNAME, FIRSTNAME" → "FIRSTNAME LASTNAME" for primary_party
            # MatterDetails.primary_party stores as-is; keep original for return value
            primary_party = party_name

            # Map case_type string to CaseType enum (best-effort match)
            _case_type_map = {
                "workers compensation": CaseType.WORKERS_COMP,
                "workers' compensation": CaseType.WORKERS_COMP,
                "immigration": CaseType.IMMIGRATION,
                "family law": CaseType.FAMILY_LAW,
                "personal injury": CaseType.PERSONAL_INJURY,
                "general": CaseType.GENERAL,
            }
            resolved_case_type = _case_type_map.get(case_type.lower(), CaseType.WORKERS_COMP)

            matter = MatterDetails(
                primary_party=primary_party,
                case_type=resolved_case_type,
                date_opened=date_opened,
            )

            config = SecurityConfig.from_env()
            async with HybridMatterBuilder(config=config) as builder:
                result = await builder.create_matter(matter)

            if result.get("status") not in ("success", "dry_run_success"):
                errors = result.get("errors", [])
                return {"error": f"Case creation failed: {'; '.join(str(e) for e in errors)}"}

            meruscase_url = result.get("meruscase_url") or result.get("browser_result", {}).get("meruscase_url")
            meruscase_id = result.get("case_file_id") or result.get("matter_id")

            logger.info(f"Created case for '{party_name}': id={meruscase_id} url={meruscase_url}")

            return {
                "success": True,
                "meruscase_id": meruscase_id,
                "url": meruscase_url,
                "party_name": party_name,
                "case_type": case_type,
            }
        except Exception as e:
            logger.error(f"create_case failed: {e}")
            return {"error": str(e)}

    async def add_party(
        self,
        case_search: str,
        party_type: str,
        company_name: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Add a party (employer, insurance company, etc.) to an existing case.

        Args:
            case_search: Case file number or party name to find the case.
            party_type: Type of party. One of: "Employer", "Insurance Company",
                "Opposing Party", "Witness", "Expert", "Client", "Other".
            company_name: Company or organization name (for Employer, Insurance Company).
            first_name: Party first name (for individuals).
            last_name: Party last name (for individuals).
            notes: Optional notes about this party.

        Returns:
            dict: {success, case_id, case_name, party_type, party_id}
        """
        try:
            # Find the case
            case = await self.find_case(case_search)
            case_id = int(case["id"])
            case_name = case.get("primary_party_name")

            # Map party_type string to PartyType enum (best-effort match)
            _party_type_map = {
                "employer": PartyType.EMPLOYER,
                "insurance company": PartyType.INSURANCE,
                "opposing party": PartyType.OPPOSING_PARTY,
                "witness": PartyType.WITNESS,
                "expert": PartyType.EXPERT,
                "client": PartyType.CLIENT,
                "other": PartyType.OTHER,
            }
            resolved_party_type = _party_type_map.get(party_type.lower(), PartyType.OTHER)

            party = Party(
                case_file_id=case_id,
                party_type=resolved_party_type,
                first_name=first_name,
                last_name=last_name,
                company_name=company_name,
                notes=notes,
            )

            logger.info(f"Adding party '{party_type}' to case {case_id}")

            response = await self.client.add_party(party)

            if not response.success:
                raise MerusAgentError(f"Failed to add party: {response.error}")

            party_id = response.data.get("id") if response.data else None

            return {
                "success": True,
                "case_id": case_id,
                "case_name": case_name,
                "party_type": party_type,
                "party_id": party_id,
            }
        except Exception as e:
            logger.error(f"add_party failed: {e}")
            return {"error": str(e)}

    async def list_documents(
        self,
        case_search: str,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """
        List all documents attached to a case.

        Args:
            case_search: Case file number or party name to find the case.
            limit: Maximum number of documents to return (default 100).

        Returns:
            dict: {case_id, case_name, documents: [...], count}
        """
        try:
            # Find the case
            case = await self.find_case(case_search)
            case_id = int(case["id"])
            case_name = case.get("primary_party_name")

            response = await self.client.list_documents(case_file_id=case_id, limit=limit)

            if not response.success:
                raise MerusAgentError(f"Failed to list documents: {response.error}")

            # Normalize document list — API may return dict or list
            raw = response.data
            if isinstance(raw, dict):
                docs_raw = raw.get("data", raw)
                if isinstance(docs_raw, dict):
                    docs = list(docs_raw.values())
                elif isinstance(docs_raw, list):
                    docs = docs_raw
                else:
                    docs = []
            elif isinstance(raw, list):
                docs = raw
            else:
                docs = []

            logger.info(f"Listed {len(docs)} documents for case {case_id}")

            return {
                "case_id": case_id,
                "case_name": case_name,
                "documents": docs,
                "count": len(docs),
            }
        except Exception as e:
            logger.error(f"list_documents failed: {e}")
            return {"error": str(e)}

    # =========================================================================
    # BATCH OPERATIONS
    # =========================================================================

    async def bulk_bill_time(
        self,
        entries: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Bill time to multiple cases in batch.

        Args:
            entries: List of dicts with keys: case_search, hours, description

        Returns:
            List of result dicts (some may have failed)

        Example:
            results = await agent.bulk_bill_time([
                {"case_search": "Smith", "hours": 0.2, "description": "Review records"},
                {"case_search": "Jones", "hours": 0.5, "description": "Draft demand"},
            ])
        """
        results = []

        for entry in entries:
            try:
                result = await self.bill_time(
                    case_search=entry["case_search"],
                    hours=entry["hours"],
                    description=entry["description"],
                    subject=entry.get("subject"),
                )
                results.append(result)
            except Exception as e:
                logger.error(f"Failed to bill time for {entry['case_search']}: {e}")
                results.append({
                    "success": False,
                    "error": str(e),
                    "case_search": entry["case_search"],
                })

        return results

    # =========================================================================
    # SUMMARY & REPORTING
    # =========================================================================

    async def get_billing_summary(
        self,
        case_search: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get billing summary for a case.

        Args:
            case_search: Case file number or party name
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)

        Returns:
            Dict with totals and entries

        Example:
            summary = await agent.get_billing_summary("Smith", start_date="2024-01-01")
        """
        case = await self.find_case(case_search)
        case_id = int(case["id"])

        # Get ledger entries
        billing = await self.get_case_billing(
            case_id,
            date_gte=start_date,
            date_lte=end_date,
        )

        entries = billing.get("data", {})

        # Calculate totals
        total_amount = 0.0
        total_entries = len(entries)

        for entry in entries.values():
            amount = float(entry.get("amount", 0))
            total_amount += amount

        return {
            "case_id": case_id,
            "case_name": case.get("primary_party_name"),
            "total_amount": total_amount,
            "total_entries": total_entries,
            "entries": entries,
            "start_date": start_date,
            "end_date": end_date,
        }


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

async def quick_bill_time(
    case_search: str,
    hours: float,
    description: str,
    token_file: str = ".meruscase_token",
) -> Dict[str, Any]:
    """
    Quick function to bill time without instantiating agent.

    Example:
        from merus_agent import quick_bill_time

        result = await quick_bill_time("Smith", 0.2, "Review records")
    """
    async with MerusAgent(token_file=token_file) as agent:
        return await agent.bill_time(case_search, hours, description)


async def quick_add_cost(
    case_search: str,
    amount: float,
    description: str,
    token_file: str = ".meruscase_token",
) -> Dict[str, Any]:
    """
    Quick function to add cost without instantiating agent.

    Example:
        from merus_agent import quick_add_cost

        result = await quick_add_cost("Smith", 25.00, "WCAB Filing Fee")
    """
    async with MerusAgent(token_file=token_file) as agent:
        return await agent.add_cost(case_search, amount, description)
