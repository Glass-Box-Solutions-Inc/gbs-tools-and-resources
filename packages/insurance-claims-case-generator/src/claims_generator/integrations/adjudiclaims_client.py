"""
AdjudiCLAIMS async HTTP client — seeds a ClaimCase into a running AdjudiCLAIMS instance.

API contract (sourced from AdjudiCLAIMS-ai-app/server/routes/claims.ts + documents.ts):

  POST /api/auth/login
    body: { email, password }
    response: 200 + Set-Cookie session header

  POST /api/claims
    body: { claimNumber, claimantName, dateOfInjury, bodyParts[], employer, insurer, dateReceived }
    response: 201 { id, claimNumber, claimantName, ... }

  PATCH /api/claims/:id
    body: any subset of { isLitigated, hasApplicantAttorney, isCumulativeTrauma, status, ... }
    response: 200 { id, ... }

  POST /api/claims/:claimId/documents
    multipart/form-data: file=<bytes>, documentType=<DocumentType enum>
    response: 201 { id, claimId, fileName, mimeType, documentType, ocrStatus, ... }

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

from claims_generator.models.claim import ClaimCase
from claims_generator.models.enums import DocumentType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class SeedResult:
    """Result of seeding one ClaimCase into AdjudiCLAIMS."""

    claim_id: str
    claim_number: str
    documents_uploaded: int
    document_ids: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class AdjudiClaimsClient:
    """
    Async httpx client for AdjudiCLAIMS REST API.

    Usage::

        async with AdjudiClaimsClient(base_url="https://staging.adjudiclaims.com") as client:
            await client.login(email="seed@example.com", password="secret")
            result = await client.seed_case(case, env="staging")

    The client uses cookie-based session authentication.  After ``login()`` the
    session cookie is stored in the underlying ``httpx.AsyncClient`` cookie jar
    and sent automatically on every subsequent request.
    """

    def __init__(self, base_url: str, timeout: float = 30.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "AdjudiClaimsClient":
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._timeout,
            follow_redirects=True,
        )
        return self

    async def __aexit__(self, *_: Any) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError(
                "AdjudiClaimsClient must be used as an async context manager. "
                "Use: async with AdjudiClaimsClient(...) as client: ..."
            )
        return self._client

    def _raise_for_status(self, response: httpx.Response, context: str) -> None:
        """Raise a descriptive RuntimeError for non-2xx responses."""
        if not response.is_success:
            raise RuntimeError(
                f"AdjudiCLAIMS API error [{context}]: "
                f"HTTP {response.status_code} — {response.text[:500]}"
            )

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    async def login(self, email: str, password: str) -> None:
        """
        Authenticate with AdjudiCLAIMS and store the session cookie.

        POST /api/auth/login
          { "email": "...", "password": "..." }

        The session cookie returned in Set-Cookie is automatically stored
        in the httpx cookie jar for all subsequent requests.
        """
        client = self._get_client()
        response = await client.post(
            "/api/auth/login",
            json={"email": email, "password": password},
        )
        self._raise_for_status(response, "POST /api/auth/login")
        logger.info("AdjudiCLAIMS login successful for %s", email)

    # ------------------------------------------------------------------
    # Claims
    # ------------------------------------------------------------------

    async def create_claim(
        self,
        claim_number: str,
        claimant_name: str,
        date_of_injury: str,
        body_parts: list[str],
        employer: str,
        insurer: str,
        date_received: str,
    ) -> dict[str, Any]:
        """
        Create a new claim.

        POST /api/claims
          {
            claimNumber, claimantName, dateOfInjury,
            bodyParts, employer, insurer, dateReceived
          }

        Returns the created claim object (includes ``id``).
        """
        client = self._get_client()
        payload: dict[str, Any] = {
            "claimNumber": claim_number,
            "claimantName": claimant_name,
            "dateOfInjury": date_of_injury,
            "bodyParts": body_parts,
            "employer": employer,
            "insurer": insurer,
            "dateReceived": date_received,
        }
        response = await client.post("/api/claims", json=payload)
        self._raise_for_status(response, "POST /api/claims")
        data: dict[str, Any] = response.json()
        logger.info("Created claim id=%s claimNumber=%s", data.get("id"), claim_number)
        return data

    async def patch_claim(
        self,
        claim_id: str,
        is_litigated: Optional[bool] = None,
        has_applicant_attorney: Optional[bool] = None,
        is_cumulative_trauma: Optional[bool] = None,
        status: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Patch an existing claim with optional flag fields.

        PATCH /api/claims/:id
          { isLitigated?, hasApplicantAttorney?, isCumulativeTrauma?, status? }

        Only non-None fields are sent.  Raises RuntimeError if no fields are
        provided (the API requires at least one field).
        """
        client = self._get_client()
        payload: dict[str, Any] = {}

        if is_litigated is not None:
            payload["isLitigated"] = is_litigated
        if has_applicant_attorney is not None:
            payload["hasApplicantAttorney"] = has_applicant_attorney
        if is_cumulative_trauma is not None:
            payload["isCumulativeTrauma"] = is_cumulative_trauma
        if status is not None:
            payload["status"] = status

        if not payload:
            raise ValueError("patch_claim: at least one field must be provided")

        response = await client.patch(f"/api/claims/{claim_id}", json=payload)
        self._raise_for_status(response, f"PATCH /api/claims/{claim_id}")
        data: dict[str, Any] = response.json()
        logger.info("Patched claim id=%s fields=%s", claim_id, list(payload.keys()))
        return data

    # ------------------------------------------------------------------
    # Documents
    # ------------------------------------------------------------------

    async def upload_document(
        self,
        claim_id: str,
        file_bytes: bytes,
        file_name: str,
        document_type: DocumentType,
    ) -> dict[str, Any]:
        """
        Upload a document to an existing claim.

        POST /api/claims/:claimId/documents
          multipart/form-data:
            file=<bytes>  (field name: "file")
            documentType=<DocumentType string>

        Returns the created Document object (includes ``id``).
        """
        client = self._get_client()
        files = {
            "file": (file_name, file_bytes, "application/pdf"),
        }
        data = {"documentType": document_type.value}
        response = await client.post(
            f"/api/claims/{claim_id}/documents",
            files=files,
            data=data,
        )
        self._raise_for_status(response, f"POST /api/claims/{claim_id}/documents")
        result: dict[str, Any] = response.json()
        logger.info(
            "Uploaded document id=%s type=%s to claim=%s",
            result.get("id"),
            document_type.value,
            claim_id,
        )
        return result

    # ------------------------------------------------------------------
    # High-level seed operation
    # ------------------------------------------------------------------

    async def seed_case(self, case: ClaimCase, env: str = "staging") -> SeedResult:
        """
        Seed a complete ClaimCase into AdjudiCLAIMS.

        Steps:
          1. POST /api/claims — create the claim from the case profile
          2. PATCH /api/claims/:id — apply scenario flags (litigated, attorney, CT)
          3. For each DocumentEvent with pdf_bytes: POST /api/claims/:id/documents

        Args:
            case:  A fully-built ClaimCase (pdf_bytes must be populated for uploads)
            env:   Environment label for logging (e.g. "staging", "production")

        Returns:
            SeedResult with claim_id and count of documents uploaded
        """
        profile = case.profile
        claimant = profile.claimant
        employer = profile.employer
        insurer = profile.insurer
        medical = profile.medical

        # 1. Create the base claim
        claim = await self.create_claim(
            claim_number=insurer.claim_number,
            claimant_name=f"{claimant.first_name} {claimant.last_name}",
            date_of_injury=medical.date_of_injury,
            body_parts=[bp.body_part for bp in medical.body_parts],
            employer=employer.company_name,
            insurer=insurer.carrier_name,
            date_received=medical.date_of_injury,  # use DOI as received date
        )
        claim_id: str = claim["id"]

        # 2. Patch scenario-specific flags (infer from case scenario slug)
        scenario = case.scenario_slug
        patch_kwargs: dict[str, Any] = {}

        if "litigated" in scenario or "qme" in scenario:
            patch_kwargs["is_litigated"] = True
            patch_kwargs["has_applicant_attorney"] = True
        if "cumulative" in scenario or scenario == "sjdb_voucher":
            patch_kwargs["is_cumulative_trauma"] = True
        if "denied" in scenario:
            patch_kwargs["status"] = "DENIED"
        if "accepted" in scenario or scenario == "standard_claim":
            patch_kwargs["status"] = "ACCEPTED"

        if patch_kwargs:
            await self.patch_claim(claim_id, **patch_kwargs)

        # 3. Upload documents that have PDF bytes
        doc_ids: list[str] = []
        for event in case.document_events:
            if not event.pdf_bytes:
                continue
            doc_result = await self.upload_document(
                claim_id=claim_id,
                file_bytes=event.pdf_bytes,
                file_name=f"{event.subtype_slug}_{event.event_id}.pdf",
                document_type=event.document_type,
            )
            if doc_id := doc_result.get("id"):
                doc_ids.append(doc_id)

        logger.info(
            "Seeded case=%s env=%s claim_id=%s docs_uploaded=%d",
            case.case_id,
            env,
            claim_id,
            len(doc_ids),
        )

        return SeedResult(
            claim_id=claim_id,
            claim_number=insurer.claim_number,
            documents_uploaded=len(doc_ids),
            document_ids=doc_ids,
        )
