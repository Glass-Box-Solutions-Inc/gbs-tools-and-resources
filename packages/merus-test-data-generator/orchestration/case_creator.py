"""
Wraps MatterBuilder from merus-expert for case creation in MerusCase.
Handles session management, retries, progress tracking, and API-based metadata population.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import httpx
import structlog

from config import (
    CASE_CREATION_MAX_RETRIES,
    MERUS_EXPERT_PATH,
    MERUSCASE_ACCESS_TOKEN,
)
from data.models import GeneratedCase
from orchestration.audit import PipelineAuditLogger
from orchestration.progress_tracker import ProgressTracker

# Add merus-expert to sys.path for imports
sys.path.insert(0, str(MERUS_EXPERT_PATH))

logger = structlog.get_logger()

MERUSCASE_API_BASE = "https://api.meruscase.com"


class CaseCreator:
    def __init__(self, tracker: ProgressTracker, audit: PipelineAuditLogger | None = None, dry_run: bool = False):
        self.tracker = tracker
        self.audit = audit
        self.dry_run = dry_run
        self._api_token = MERUSCASE_ACCESS_TOKEN

    def _get_merus_config(self):
        """Build SecurityConfig with correct db_path for merus-expert."""
        from security.config import SecurityConfig
        config = SecurityConfig.from_env()
        # Override db_path: our .env sets DB_PATH=progress.db which conflicts
        config.db_path = str(MERUS_EXPERT_PATH / "knowledge" / "db" / "merus_knowledge.db")
        # Use Browserless cloud to bypass reCAPTCHA on login page
        config.use_local_browser = False
        config.use_headless = True
        return config

    async def _update_case_via_api(self, meruscase_id: int, case: GeneratedCase) -> bool:
        """Update case metadata in MerusCase via the REST API."""
        if not self._api_token:
            logger.warning("no_api_token", msg="Cannot update case metadata - no API token available")
            return False

        headers = {
            "Authorization": f"Bearer {self._api_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        custom_data = {
            "employer": case.employer.company_name,
            "date_of_injury": case.timeline.date_of_injury.strftime("%m/%d/%Y"),
            "body_parts": ", ".join(case.injuries[0].body_parts),
            "claim_number": case.insurance.claim_number,
            "adj_number": case.injuries[0].adj_number,
            "carrier": case.insurance.carrier_name,
        }

        case_update = {
            "CaseFile": {
                "date_opened": case.timeline.date_of_injury.strftime("%Y-%m-%d"),
                "custom_data": json.dumps(custom_data),
                "comments": (
                    f"Workers' Compensation Case\n"
                    f"Employer: {case.employer.company_name}\n"
                    f"Date of Injury: {case.timeline.date_of_injury.strftime('%m/%d/%Y')}\n"
                    f"Body Parts: {', '.join(case.injuries[0].body_parts)}\n"
                    f"Claim #: {case.insurance.claim_number}\n"
                    f"ADJ #: {case.injuries[0].adj_number}\n"
                    f"Carrier: {case.insurance.carrier_name}\n"
                    f"Litigation Stage: {case.litigation_stage.value}\n"
                    f"Internal ID: {case.internal_id}"
                ),
            }
        }

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                # Update case fields
                resp = await client.post(
                    f"{MERUSCASE_API_BASE}/caseFiles/edit/{meruscase_id}",
                    headers=headers,
                    json=case_update,
                )

                if resp.status_code == 200:
                    logger.info(
                        "case_metadata_updated",
                        meruscase_id=meruscase_id,
                        case_id=case.internal_id,
                    )
                else:
                    logger.warning(
                        "case_metadata_update_failed",
                        meruscase_id=meruscase_id,
                        status=resp.status_code,
                        response=resp.text[:200],
                    )
                    return False

                # Add employer as a party
                employer_party = {
                    "case_file_id": meruscase_id,
                    "party_type": "Employer",
                    "company_name": case.employer.company_name,
                    "notes": f"Employer at time of injury. Address: {case.employer.address_street}, {case.employer.address_city}, {case.employer.address_state} {case.employer.address_zip}",
                }
                resp2 = await client.post(
                    f"{MERUSCASE_API_BASE}/parties/add",
                    headers=headers,
                    json=employer_party,
                )
                if resp2.status_code == 200:
                    logger.info("employer_party_added", meruscase_id=meruscase_id)

                # Add insurance carrier as a party
                carrier_party = {
                    "case_file_id": meruscase_id,
                    "party_type": "Insurance Company",
                    "company_name": case.insurance.carrier_name,
                    "notes": f"Claim #: {case.insurance.claim_number}. Adjuster: {case.insurance.adjuster_name}",
                }
                resp3 = await client.post(
                    f"{MERUSCASE_API_BASE}/parties/add",
                    headers=headers,
                    json=carrier_party,
                )
                if resp3.status_code == 200:
                    logger.info("carrier_party_added", meruscase_id=meruscase_id)

                # Add an activity note with full case details
                from datetime import datetime
                applicant_addr = f"{case.applicant.address_street}, {case.applicant.address_city}, {case.applicant.address_state} {case.applicant.address_zip}"
                activity = {
                    "case_file_id": meruscase_id,
                    "subject": "Case Created via Test Data Generator",
                    "description": (
                        f"Applicant: {case.applicant.full_name}\n"
                        f"SSN (last 4): {case.applicant.ssn_last_four}\n"
                        f"DOB: {case.applicant.date_of_birth}\n"
                        f"Phone: {case.applicant.phone}\n"
                        f"Email: {case.applicant.email}\n"
                        f"Address: {applicant_addr}\n\n"
                        f"Employer: {case.employer.company_name}\n\n"
                        f"Date of Injury: {case.timeline.date_of_injury.strftime('%m/%d/%Y')}\n"
                        f"Body Parts: {', '.join(case.injuries[0].body_parts)}\n"
                        f"Injury Description: {case.injuries[0].description}\n\n"
                        f"Claim #: {case.insurance.claim_number}\n"
                        f"ADJ #: {case.injuries[0].adj_number}\n"
                        f"Carrier: {case.insurance.carrier_name}\n"
                        f"Adjuster: {case.insurance.adjuster_name}\n\n"
                        f"Litigation Stage: {case.litigation_stage.value}\n"
                        f"Total Documents: {len(case.document_specs)}"
                    ),
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
                resp4 = await client.post(
                    f"{MERUSCASE_API_BASE}/activities/add",
                    headers=headers,
                    json=activity,
                )
                if resp4.status_code == 200:
                    logger.info("case_activity_added", meruscase_id=meruscase_id)

            return True

        except Exception as e:
            logger.error("api_metadata_error", meruscase_id=meruscase_id, error=str(e))
            return False

    def _find_meruscase_id_from_api(self, case_name: str) -> int | None:
        """Look up the actual MerusCase ID by searching recent cases via API."""
        if not self._api_token:
            return None

        import httpx as _httpx

        try:
            with _httpx.Client(timeout=15) as client:
                resp = client.get(
                    f"{MERUSCASE_API_BASE}/caseFiles/index",
                    headers={
                        "Authorization": f"Bearer {self._api_token}",
                        "Accept": "application/json",
                    },
                )
                if resp.status_code == 200:
                    data = resp.json().get("data", {})
                    if isinstance(data, dict):
                        # Sort by ID descending to find most recent
                        for case_id in sorted(data.keys(), key=int, reverse=True):
                            info = data[case_id]
                            name = info.get("1", "")
                            if case_name.lower() in name.lower() or name.lower() in case_name.lower():
                                return int(case_id)
        except Exception as e:
            logger.debug("api_lookup_error", error=str(e))

        return None

    async def create_case(self, case: GeneratedCase) -> int | None:
        """Create a single case in MerusCase. Returns meruscase_id or None on failure."""
        from automation.matter_builder import MatterBuilder
        from models.matter import CaseType, MatterDetails

        # MerusCase expects "LASTNAME, FIRSTNAME" format
        name_parts = case.applicant.full_name.split()
        if len(name_parts) >= 2:
            formatted_name = f"{name_parts[-1].upper()}, {' '.join(name_parts[:-1]).upper()}"
        else:
            formatted_name = case.applicant.full_name.upper()

        matter = MatterDetails(
            primary_party=formatted_name,
            case_type=CaseType.WORKERS_COMP,
            date_opened=case.timeline.date_of_injury.strftime("%m/%d/%Y"),
            custom_fields={},  # Custom fields populated via API post-creation
        )

        for attempt in range(1, CASE_CREATION_MAX_RETRIES + 1):
            try:
                logger.info(
                    "creating_case",
                    case_id=case.internal_id,
                    applicant=formatted_name,
                    attempt=attempt,
                    dry_run=self.dry_run,
                )

                async with MatterBuilder(config=self._get_merus_config(), dry_run=self.dry_run) as builder:
                    result = await builder.create_matter(matter)

                if result.get("status") in ("success", "dry_run_success"):
                    # Extract MerusCase ID from URL (e.g. .../caseFiles/56171871 or #/caseFiles/56171871)
                    meruscase_id = None
                    meruscase_url = result.get("meruscase_url", "")
                    if meruscase_url and "caseFiles" in meruscase_url:
                        import re
                        match = re.search(r'caseFiles/(?:view/)?(\d+)', meruscase_url)
                        if match:
                            meruscase_id = int(match.group(1))

                    # Fallback: search API for recently created case
                    if not meruscase_id:
                        meruscase_id = self._find_meruscase_id_from_api(formatted_name)

                    # Last fallback: result dict
                    if not meruscase_id:
                        meruscase_id = result.get("case_file_id")

                    if meruscase_id:
                        self.tracker.mark_case_created(case.internal_id, int(meruscase_id))
                        if self.audit:
                            self.audit.log_case_created(case.internal_id, int(meruscase_id), success=True)
                        logger.info(
                            "case_created",
                            case_id=case.internal_id,
                            meruscase_id=meruscase_id,
                        )

                        # Populate metadata via API
                        await self._update_case_via_api(int(meruscase_id), case)

                        return int(meruscase_id)

                logger.warning(
                    "case_creation_no_id",
                    case_id=case.internal_id,
                    result=result,
                    attempt=attempt,
                )

            except Exception as e:
                logger.error(
                    "case_creation_error",
                    case_id=case.internal_id,
                    error=str(e),
                    attempt=attempt,
                )
                if attempt < CASE_CREATION_MAX_RETRIES:
                    wait = 10 * attempt
                    logger.info("retrying_case_creation", wait_seconds=wait)
                    await asyncio.sleep(wait)

        error_msg = f"Failed to create case after {CASE_CREATION_MAX_RETRIES} attempts"
        self.tracker.mark_case_error(case.internal_id, error_msg)
        if self.audit:
            self.audit.log_case_created(case.internal_id, None, success=False)
        return None

    async def create_all_cases(self, cases: list[GeneratedCase]) -> dict[str, Any]:
        """Create all cases sequentially. Returns summary dict."""
        created = 0
        failed = 0

        for case in cases:
            existing = self.tracker.get_case(case.internal_id)
            if existing and existing["case_created"]:
                logger.info("case_already_created", case_id=case.internal_id)
                created += 1
                continue

            result = await self.create_case(case)
            if result:
                created += 1
            else:
                failed += 1

            # Brief pause between cases
            await asyncio.sleep(2)

        return {
            "total": len(cases),
            "created": created,
            "failed": failed,
        }
