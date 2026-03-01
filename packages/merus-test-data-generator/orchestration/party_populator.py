"""
Populates MerusCase cases with comprehensive Workers' Comp parties.

Creates contacts and links them as parties for each case:
- Defendant/Employer
- Carrier (insurance)
- Claims Adjuster
- Applicant Attorney (firm)
- Defense Attorney
- Primary Treating Physician
- Qualified Medical Examiner (if applicable)
- Lien Claimant (medical facility)

Also assigns attorney/paralegal on case metadata.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import structlog

from config import MERUSCASE_ACCESS_TOKEN
from data.models import GeneratedCase

logger = structlog.get_logger()

MERUSCASE_API_BASE = "https://api.meruscase.com"

# MerusCase People Type IDs (Workers' Comp)
PEOPLE_TYPES = {
    "applicant": 1906148,
    "applicant_attorney": 1906158,
    "defense_attorney": 1906150,
    "carrier": 1906151,
    "claims_adjuster": 1906156,
    "employer": 1906237,
    "primary_treating_physician": 1906161,
    "qualified_medical_examiner": 1906153,
    "panel_qme": 1906154,
    "lien_claimant": 1906239,
    "nurse_case_manager": 1906166,
    "hearing_judge": 1906238,
    "third_party_administrator": 1906175,
    "doctor": 1906152,
    "chiropractor": 1906176,
}

# Firm user IDs
ATTORNEY_RESPONSIBLE_ID = 1973975  # Alex Brewsaugh


class PartyPopulator:
    def __init__(self):
        self._token = MERUSCASE_ACCESS_TOKEN
        self._headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        self._applicant_attorney_contact_id: int | None = None

    async def _create_contact(
        self,
        *,
        first_name: str = "",
        last_name: str = "",
        company_name: str = "",
        specialty: str = "",
        notes: str = "",
    ) -> int | None:
        """Create a contact in MerusCase. Returns contact_id or None."""
        contact_data: dict[str, Any] = {}
        if first_name:
            contact_data["first_name"] = first_name
        if last_name:
            contact_data["last_name"] = last_name
        if company_name:
            contact_data["name"] = company_name
        if specialty:
            contact_data["specialty"] = specialty

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"{MERUSCASE_API_BASE}/contacts/add",
                    headers=self._headers,
                    json={"Contact": contact_data},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    contact = data.get("Contact", {})
                    contact_id = contact.get("id")
                    if contact_id:
                        logger.debug(
                            "contact_created",
                            contact_id=contact_id,
                            name=f"{first_name} {last_name}".strip() or company_name,
                        )
                        return int(contact_id)
                logger.warning(
                    "contact_create_failed",
                    status=resp.status_code,
                    response=resp.text[:200],
                )
        except Exception as e:
            logger.error("contact_create_error", error=str(e))
        return None

    async def _add_party(
        self,
        case_file_id: int,
        contact_id: int,
        people_type_id: int,
        *,
        notes: str = "",
        insurance_claim_number: str = "",
        insurance_policy_number: str = "",
    ) -> bool:
        """Link a contact as a party on a case. Returns True on success."""
        party_data: dict[str, Any] = {
            "case_file_id": str(case_file_id),
            "contact_id": str(contact_id),
            "people_type_id": str(people_type_id),
        }
        if notes:
            party_data["notes"] = notes
        if insurance_claim_number:
            party_data["insurance_claim_number"] = insurance_claim_number
        if insurance_policy_number:
            party_data["insurance_policy_number"] = insurance_policy_number

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"{MERUSCASE_API_BASE}/parties/add",
                    headers=self._headers,
                    json={"Party": party_data},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("msg", "").startswith("Party has been added"):
                        parties = data.get("parties", {}).get("data", {})
                        if len(parties) > 1 or data.get("partiesId"):
                            return True
                    if "errors" in data.get("parties", {}):
                        logger.warning(
                            "party_add_error",
                            case_id=case_file_id,
                            errors=data["parties"]["errors"],
                        )
                        return False
                logger.warning(
                    "party_add_failed",
                    case_id=case_file_id,
                    status=resp.status_code,
                )
        except Exception as e:
            logger.error("party_add_error", case_id=case_file_id, error=str(e))
        return False

    async def _create_and_link_party(
        self,
        case_file_id: int,
        people_type_id: int,
        *,
        first_name: str = "",
        last_name: str = "",
        company_name: str = "",
        specialty: str = "",
        notes: str = "",
        insurance_claim_number: str = "",
        insurance_policy_number: str = "",
        contact_id: int | None = None,
    ) -> bool:
        """Create a contact and link as party in one flow."""
        if contact_id is None:
            contact_id = await self._create_contact(
                first_name=first_name,
                last_name=last_name,
                company_name=company_name,
                specialty=specialty,
            )
        if contact_id is None:
            return False

        await asyncio.sleep(0.3)

        return await self._add_party(
            case_file_id=case_file_id,
            contact_id=contact_id,
            people_type_id=people_type_id,
            notes=notes,
            insurance_claim_number=insurance_claim_number,
            insurance_policy_number=insurance_policy_number,
        )

    async def _get_or_create_applicant_attorney(self) -> int | None:
        """Get or create the Adjudica firm contact (shared across cases)."""
        if self._applicant_attorney_contact_id:
            return self._applicant_attorney_contact_id

        contact_id = await self._create_contact(
            first_name="Alex",
            last_name="Brewsaugh",
            company_name="Adjudica, AI",
        )
        if contact_id:
            self._applicant_attorney_contact_id = contact_id
        return contact_id

    async def _update_case_assignment(self, case_file_id: int) -> bool:
        """Assign attorney on the case metadata."""
        case_update = {
            "CaseFile": {
                "attorney_responsible": str(ATTORNEY_RESPONSIBLE_ID),
                "attorney_handling": str(ATTORNEY_RESPONSIBLE_ID),
            }
        }
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"{MERUSCASE_API_BASE}/caseFiles/edit/{case_file_id}",
                    headers=self._headers,
                    json=case_update,
                )
                if resp.status_code == 200:
                    logger.info("case_assignment_updated", case_id=case_file_id)
                    return True
                logger.warning(
                    "case_assignment_failed",
                    case_id=case_file_id,
                    status=resp.status_code,
                )
        except Exception as e:
            logger.error("case_assignment_error", case_id=case_file_id, error=str(e))
        return False

    async def _update_case_adjuster_info(
        self, case_file_id: int, case: GeneratedCase
    ) -> bool:
        """Add adjuster information to case custom_data and comments."""
        custom_data = {
            "employer": case.employer.company_name,
            "date_of_injury": case.timeline.date_of_injury.strftime("%m/%d/%Y"),
            "body_parts": ", ".join(case.injuries[0].body_parts),
            "claim_number": case.insurance.claim_number,
            "adj_number": case.injuries[0].adj_number,
            "carrier": case.insurance.carrier_name,
            "adjuster_name": case.insurance.adjuster_name,
            "adjuster_phone": case.insurance.adjuster_phone,
            "adjuster_email": case.insurance.adjuster_email,
            "defense_attorney": case.insurance.defense_attorney,
            "defense_firm": case.insurance.defense_firm,
            "attorney_responsible": "Alex Brewsaugh",
        }

        applicant_addr = (
            f"{case.applicant.address_street}, {case.applicant.address_city}, "
            f"{case.applicant.address_state} {case.applicant.address_zip}"
        )
        comments = (
            f"Workers' Compensation Case\n"
            f"Applicant: {case.applicant.full_name}\n"
            f"DOB: {case.applicant.date_of_birth}\n"
            f"Address: {applicant_addr}\n\n"
            f"Employer: {case.employer.company_name}\n"
            f"Position: {case.employer.position}\n\n"
            f"Date of Injury: {case.timeline.date_of_injury.strftime('%m/%d/%Y')}\n"
            f"Body Parts: {', '.join(case.injuries[0].body_parts)}\n"
            f"Claim #: {case.insurance.claim_number}\n"
            f"ADJ #: {case.injuries[0].adj_number}\n\n"
            f"Carrier: {case.insurance.carrier_name}\n"
            f"Adjuster: {case.insurance.adjuster_name}\n"
            f"Adjuster Phone: {case.insurance.adjuster_phone}\n"
            f"Adjuster Email: {case.insurance.adjuster_email}\n\n"
            f"Defense Firm: {case.insurance.defense_firm}\n"
            f"Defense Attorney: {case.insurance.defense_attorney}\n"
            f"Defense Phone: {case.insurance.defense_phone}\n\n"
            f"Attorney Responsible: Alex Brewsaugh\n"
            f"Litigation Stage: {case.litigation_stage.value}\n"
            f"Internal ID: {case.internal_id}"
        )

        case_update = {
            "CaseFile": {
                "custom_data": json.dumps(custom_data),
                "comments": comments,
            }
        }

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"{MERUSCASE_API_BASE}/caseFiles/edit/{case_file_id}",
                    headers=self._headers,
                    json=case_update,
                )
                if resp.status_code == 200:
                    logger.info("case_metadata_enriched", case_id=case_file_id)
                    return True
        except Exception as e:
            logger.error("case_metadata_error", case_id=case_file_id, error=str(e))
        return False

    async def populate_case_parties(
        self, case: GeneratedCase, meruscase_id: int
    ) -> dict[str, int]:
        """Add all WC parties to a single case. Returns counts."""
        added = 0
        failed = 0

        def _track(success: bool, label: str):
            nonlocal added, failed
            if success:
                added += 1
                logger.info("party_added", case=case.internal_id, party=label)
            else:
                failed += 1
                logger.warning("party_failed", case=case.internal_id, party=label)

        # 1. Defendant/Employer
        emp = case.employer
        emp_notes = (
            f"Position: {emp.position}\n"
            f"Hire Date: {emp.hire_date}\n"
            f"Address: {emp.address_street}, {emp.address_city}, "
            f"{emp.address_state} {emp.address_zip}\n"
            f"Phone: {emp.phone}"
        )
        ok = await self._create_and_link_party(
            meruscase_id,
            PEOPLE_TYPES["employer"],
            company_name=emp.company_name,
            notes=emp_notes,
        )
        _track(ok, f"Employer: {emp.company_name}")
        await asyncio.sleep(0.5)

        # 2. Insurance Carrier
        ins = case.insurance
        ok = await self._create_and_link_party(
            meruscase_id,
            PEOPLE_TYPES["carrier"],
            company_name=ins.carrier_name,
            notes=f"Adjuster: {ins.adjuster_name}\nPhone: {ins.adjuster_phone}",
            insurance_claim_number=ins.claim_number,
            insurance_policy_number=ins.policy_number,
        )
        _track(ok, f"Carrier: {ins.carrier_name}")
        await asyncio.sleep(0.5)

        # 3. Claims Adjuster
        adj_parts = ins.adjuster_name.split()
        adj_first = adj_parts[0] if adj_parts else ins.adjuster_name
        adj_last = " ".join(adj_parts[1:]) if len(adj_parts) > 1 else ""
        ok = await self._create_and_link_party(
            meruscase_id,
            PEOPLE_TYPES["claims_adjuster"],
            first_name=adj_first,
            last_name=adj_last,
            notes=(
                f"Carrier: {ins.carrier_name}\n"
                f"Phone: {ins.adjuster_phone}\n"
                f"Email: {ins.adjuster_email}\n"
                f"Claim #: {ins.claim_number}"
            ),
        )
        _track(ok, f"Claims Adjuster: {ins.adjuster_name}")
        await asyncio.sleep(0.5)

        # 4. Applicant Attorney (shared Adjudica contact)
        atty_contact_id = await self._get_or_create_applicant_attorney()
        if atty_contact_id:
            ok = await self._add_party(
                meruscase_id,
                atty_contact_id,
                PEOPLE_TYPES["applicant_attorney"],
                notes="Law Offices of Adjudica, AI\nalex@adjudica.ai",
            )
            _track(ok, "Applicant Attorney: Adjudica")
        else:
            _track(False, "Applicant Attorney: Adjudica")
        await asyncio.sleep(0.5)

        # 5. Defense Attorney
        def_parts = ins.defense_attorney.split()
        def_first = def_parts[0] if def_parts else ins.defense_attorney
        def_last = " ".join(def_parts[1:]) if len(def_parts) > 1 else ""
        ok = await self._create_and_link_party(
            meruscase_id,
            PEOPLE_TYPES["defense_attorney"],
            first_name=def_first,
            last_name=def_last,
            notes=(
                f"Firm: {ins.defense_firm}\n"
                f"Phone: {ins.defense_phone}\n"
                f"Email: {ins.defense_email}"
            ),
        )
        _track(ok, f"Defense Attorney: {ins.defense_attorney}")
        await asyncio.sleep(0.5)

        # 6. Primary Treating Physician
        ptp = case.treating_physician
        ok = await self._create_and_link_party(
            meruscase_id,
            PEOPLE_TYPES["primary_treating_physician"],
            first_name=ptp.first_name,
            last_name=ptp.last_name,
            specialty=ptp.specialty,
            notes=(
                f"Facility: {ptp.facility}\n"
                f"Specialty: {ptp.specialty}\n"
                f"License: {ptp.license_number}\n"
                f"NPI: {ptp.npi}\n"
                f"Phone: {ptp.phone}\n"
                f"Address: {ptp.address}"
            ),
        )
        _track(ok, f"PTP: {ptp.full_name}")
        await asyncio.sleep(0.5)

        # 7. QME (if applicable)
        if case.qme_physician:
            qme = case.qme_physician
            ok = await self._create_and_link_party(
                meruscase_id,
                PEOPLE_TYPES["qualified_medical_examiner"],
                first_name=qme.first_name,
                last_name=qme.last_name,
                specialty=qme.specialty,
                notes=(
                    f"Facility: {qme.facility}\n"
                    f"Specialty: {qme.specialty}\n"
                    f"License: {qme.license_number}\n"
                    f"NPI: {qme.npi}\n"
                    f"Phone: {qme.phone}\n"
                    f"Address: {qme.address}"
                ),
            )
            _track(ok, f"QME: {qme.full_name}")
            await asyncio.sleep(0.5)

        # 8. Lien Claimant (treating facility)
        ok = await self._create_and_link_party(
            meruscase_id,
            PEOPLE_TYPES["lien_claimant"],
            company_name=ptp.facility,
            notes=(
                f"Medical Lien - Treating Facility\n"
                f"Provider: {ptp.full_name}\n"
                f"Address: {ptp.address}\n"
                f"Phone: {ptp.phone}"
            ),
        )
        _track(ok, f"Lien Claimant: {ptp.facility}")
        await asyncio.sleep(0.5)

        # 9. Update case assignment (attorney_responsible)
        await self._update_case_assignment(meruscase_id)

        # 10. Update case metadata with adjuster info
        await self._update_case_adjuster_info(meruscase_id, case)

        return {"added": added, "failed": failed}

    async def populate_all(
        self,
        cases: list[GeneratedCase],
        case_id_map: dict[str, int],
    ) -> dict[str, Any]:
        """Populate parties for all cases. Returns summary."""
        total_added = 0
        total_failed = 0
        cases_processed = 0

        for case in cases:
            meruscase_id = case_id_map.get(case.internal_id)
            if not meruscase_id:
                logger.warning("no_meruscase_id", case=case.internal_id)
                continue

            logger.info(
                "populating_parties",
                case=case.internal_id,
                meruscase_id=meruscase_id,
            )
            result = await self.populate_case_parties(case, meruscase_id)
            total_added += result["added"]
            total_failed += result["failed"]
            cases_processed += 1

            # Brief pause between cases
            await asyncio.sleep(1)

        return {
            "cases_processed": cases_processed,
            "parties_added": total_added,
            "parties_failed": total_failed,
        }
