"""
Hybrid Matter Builder
Combines browser automation (for case creation) with direct API (for details)
"""

import logging
import re
from typing import Optional, Dict, Any, List
from datetime import datetime

from automation.matter_builder import MatterBuilder
from meruscase_api.client import MerusCaseAPIClient
from meruscase_api.models import Party, Activity, PartyType
from models.matter import MatterDetails, BillingInfo
from security.config import SecurityConfig

logger = logging.getLogger(__name__)


class HybridMatterBuilder:
    """
    Hybrid approach to matter creation:

    1. Browser Automation (Browserless):
       - Login to MerusCase
       - Create new case (no API endpoint available)
       - Extract case ID from result

    2. Direct API:
       - Add parties/contacts
       - Add activities/notes
       - Upload documents
       - Update billing info

    Benefits:
    - Faster for adding multiple parties/activities
    - More reliable (no DOM parsing)
    - Better error handling
    - Reduced Browserless usage (cheaper)
    """

    def __init__(
        self,
        config: Optional[SecurityConfig] = None,
        dry_run: bool = False,
    ):
        """
        Initialize hybrid matter builder.

        Args:
            config: Security configuration
            dry_run: If True, preview only without creating
        """
        self.config = config or SecurityConfig.from_env()
        self.dry_run = dry_run

        # Browser-based builder for case creation
        self._browser_builder: Optional[MatterBuilder] = None

        # API client for post-creation operations
        self._api_client: Optional[MerusCaseAPIClient] = None

        self._case_file_id: Optional[int] = None

    async def __aenter__(self):
        """Async context manager entry"""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.disconnect()

    async def connect(self):
        """Initialize connections"""
        # Initialize browser builder
        self._browser_builder = MatterBuilder(
            config=self.config,
            dry_run=self.dry_run
        )
        await self._browser_builder.connect()

        # Initialize API client if token available
        if self.config.meruscase_api_token and self.config.use_hybrid_mode:
            self._api_client = MerusCaseAPIClient(
                access_token=self.config.meruscase_api_token,
                client_id=self.config.meruscase_api_client_id,
                client_secret=self.config.meruscase_api_client_secret,
            )
            logger.info("Hybrid mode enabled - API client initialized")
        else:
            logger.info("Hybrid mode disabled - using browser only")

    async def disconnect(self):
        """Close connections"""
        if self._browser_builder:
            await self._browser_builder.disconnect()
        if self._api_client:
            await self._api_client.close()

    async def create_matter(
        self,
        matter: MatterDetails,
        session_id: Optional[str] = None,
        additional_parties: Optional[List[Dict[str, Any]]] = None,
        initial_note: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a matter using hybrid approach.

        Args:
            matter: Core matter details
            session_id: Session identifier
            additional_parties: Extra parties to add via API
            initial_note: Initial activity note to add

        Returns:
            Result dictionary with matter details
        """
        if not session_id:
            session_id = f"hybrid_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        result = {
            "session_id": session_id,
            "matter_id": None,
            "case_file_id": None,
            "status": "pending",
            "browser_result": None,
            "api_results": [],
            "errors": [],
        }

        try:
            # Step 1: Create case via browser automation
            logger.info("Step 1: Creating case via browser automation...")
            browser_result = await self._browser_builder.create_matter(
                matter,
                session_id=session_id
            )
            result["browser_result"] = browser_result
            result["matter_id"] = browser_result.get("matter_id")

            if browser_result.get("status") not in ["success", "dry_run_success"]:
                result["status"] = "failed"
                result["errors"].append(f"Browser automation failed: {browser_result.get('error')}")
                return result

            # Extract case file ID from MerusCase URL
            meruscase_url = browser_result.get("meruscase_url")
            if meruscase_url:
                case_file_id = self._extract_case_id(meruscase_url)
                result["case_file_id"] = case_file_id
                self._case_file_id = case_file_id

            # If dry run or no API client, stop here
            if self.dry_run:
                result["status"] = "dry_run_success"
                result["message"] = "Case preview complete (dry-run mode)"
                return result

            if not self._api_client or not self._case_file_id:
                result["status"] = "success"
                result["message"] = "Case created via browser (API disabled or case ID not found)"
                return result

            # Step 2: Add additional parties via API
            if additional_parties:
                logger.info(f"Step 2: Adding {len(additional_parties)} parties via API...")
                for party_data in additional_parties:
                    api_result = await self._add_party(party_data)
                    result["api_results"].append({
                        "operation": "add_party",
                        "data": party_data,
                        "result": api_result,
                    })
                    if not api_result.get("success"):
                        result["errors"].append(f"Failed to add party: {api_result.get('error')}")

            # Step 3: Add initial note/activity via API
            if initial_note:
                logger.info("Step 3: Adding initial note via API...")
                note_result = await self._add_activity(
                    subject="Case Opened",
                    description=initial_note,
                )
                result["api_results"].append({
                    "operation": "add_activity",
                    "data": {"subject": "Case Opened", "description": initial_note},
                    "result": note_result,
                })

            # Step 4: Add case creation activity
            logger.info("Step 4: Logging case creation activity...")
            creation_note = await self._add_activity(
                subject="Case Created via Merus Expert",
                description=f"Case created automatically.\n\n"
                           f"Primary Party: {matter.primary_party}\n"
                           f"Case Type: {matter.case_type.value if matter.case_type else 'General'}\n"
                           f"Created at: {datetime.now().isoformat()}",
            )
            result["api_results"].append({
                "operation": "creation_log",
                "result": creation_note,
            })

            result["status"] = "success"
            result["message"] = "Case created with hybrid approach"
            result["meruscase_url"] = meruscase_url

            logger.info(f"Hybrid matter creation complete: {result['status']}")
            return result

        except Exception as e:
            logger.error(f"Hybrid matter creation failed: {e}")
            result["status"] = "failed"
            result["errors"].append(str(e))
            return result

    def _extract_case_id(self, url: str) -> Optional[int]:
        """Extract case file ID from MerusCase URL"""
        # URL patterns: /cases/123, /matters/123, /caseFiles/view/123
        patterns = [
            r'/cases?/(\d+)',
            r'/matters?/(\d+)',
            r'/caseFiles/view/(\d+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return int(match.group(1))
        return None

    async def _add_party(self, party_data: Dict[str, Any]) -> Dict[str, Any]:
        """Add a party via API"""
        if not self._api_client or not self._case_file_id:
            return {"success": False, "error": "API not available"}

        party = Party(
            case_file_id=self._case_file_id,
            party_type=PartyType(party_data.get("party_type", "Client")),
            first_name=party_data.get("first_name"),
            last_name=party_data.get("last_name"),
            company_name=party_data.get("company_name"),
            email=party_data.get("email"),
            phone=party_data.get("phone"),
            address=party_data.get("address"),
            city=party_data.get("city"),
            state=party_data.get("state"),
            zip_code=party_data.get("zip_code"),
            notes=party_data.get("notes"),
        )

        response = await self._api_client.add_party(party)
        return {
            "success": response.success,
            "data": response.data,
            "error": response.error,
        }

    async def _add_activity(
        self,
        subject: str,
        description: Optional[str] = None,
        billable: bool = False,
    ) -> Dict[str, Any]:
        """Add an activity/note via API"""
        if not self._api_client or not self._case_file_id:
            return {"success": False, "error": "API not available"}

        activity = Activity(
            case_file_id=self._case_file_id,
            subject=subject,
            description=description,
            billable=billable,
        )

        response = await self._api_client.add_activity(activity)
        return {
            "success": response.success,
            "data": response.data,
            "error": response.error,
        }

    async def add_party_to_case(
        self,
        case_file_id: int,
        party_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Add a party to an existing case via API.

        Args:
            case_file_id: MerusCase case file ID
            party_data: Party details

        Returns:
            Result dictionary
        """
        if not self._api_client:
            return {"success": False, "error": "API client not initialized"}

        self._case_file_id = case_file_id
        return await self._add_party(party_data)

    async def add_note_to_case(
        self,
        case_file_id: int,
        subject: str,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Add a note to an existing case via API.

        Args:
            case_file_id: MerusCase case file ID
            subject: Note subject
            description: Note content

        Returns:
            Result dictionary
        """
        if not self._api_client:
            return {"success": False, "error": "API client not initialized"}

        self._case_file_id = case_file_id
        return await self._add_activity(subject, description)

    async def get_case_details(self, case_file_id: int) -> Dict[str, Any]:
        """
        Get case details via API.

        Args:
            case_file_id: MerusCase case file ID

        Returns:
            Case details
        """
        if not self._api_client:
            return {"success": False, "error": "API client not initialized"}

        response = await self._api_client.get_case(case_file_id)
        return {
            "success": response.success,
            "data": response.data,
            "error": response.error,
        }
