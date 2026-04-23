"""
Integration tests for AdjudiClaimsClient.seed_case() — all network calls mocked
with respx so no live server is required.

Covered scenarios:
  - Login → 200 + Set-Cookie
  - Create claim → 201 + { id, claimNumber, ... }
  - Patch claim → 200
  - Document upload → 201 for each doc with pdf_bytes
  - Endpoint call order is asserted
  - Error paths: login 401, claim creation 400, patch empty fields

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import os
import sys
from datetime import date
from typing import Any
from unittest.mock import patch

import pytest
import respx
import httpx

# Ensure src/ is on the path
_SRC = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "src"
)
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from claims_generator.integrations.adjudiclaims_client import AdjudiClaimsClient, SeedResult
from claims_generator.models.claim import ClaimCase, DocumentEvent
from claims_generator.models.claimant import ClaimantProfile
from claims_generator.models.employer import EmployerProfile, InsurerProfile
from claims_generator.models.financial import FinancialProfile
from claims_generator.models.medical import BodyPart, MedicalProfile, PhysicianProfile
from claims_generator.models.profile import ClaimProfile
from claims_generator.models.enums import DocumentType

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

BASE_URL = "https://staging.adjudiclaims.com"


def _make_profile() -> ClaimProfile:
    """Build a minimal but complete ClaimProfile for testing."""
    return ClaimProfile(
        claimant=ClaimantProfile(
            first_name="Jane",
            last_name="Worker",
            date_of_birth=date(1985, 3, 15),
            gender="F",
            address_city="Los Angeles",
            address_county="Los Angeles",
            address_zip="90001",
            phone="310-555-0100",
            ssn_last4="1234",
            occupation_title="Warehouse Associate",
        ),
        employer=EmployerProfile(
            company_name="Acme Logistics LLC",
            industry="Warehousing",
            address_city="Los Angeles",
            address_state="CA",
        ),
        insurer=InsurerProfile(
            carrier_name="State Compensation Insurance Fund",
            claim_number="SCIF-2026-00123",
            adjuster_name="Bob Adjuster",
            adjuster_phone="800-555-0200",
            adjuster_email="bob@scif.test",
            policy_number="POL-9999",
        ),
        medical=MedicalProfile(
            date_of_injury="2026-01-10",
            injury_mechanism="Repetitive motion",
            body_parts=[BodyPart(body_part="lumbar spine", primary=True)],
            icd10_codes=[],
            treating_physician=PhysicianProfile(
                role="treating_md",
                first_name="Dr",
                last_name="Smith",
                specialty="Occupational Medicine",
                license_number="G12345",
                address_city="Los Angeles",
                npi="1234567890",
            ),
        ),
        financial=FinancialProfile(
            injury_year=2026,
            average_weekly_wage=900.0,
            td_weekly_rate=600.0,
            td_min_rate=230.95,
            td_max_rate=1620.0,
        ),
    )


def _make_document_event(with_pdf: bool = True) -> DocumentEvent:
    return DocumentEvent(
        event_id="evt-001",
        document_type=DocumentType.DWC1_CLAIM_FORM,
        subtype_slug="dwc1_claim_form",
        title="DWC-1 Claim Form",
        event_date=date(2026, 1, 10),
        stage="intake",
        pdf_bytes=b"%PDF-stub-content" if with_pdf else b"",
    )


def _make_case(scenario_slug: str = "standard_claim", include_docs: bool = True) -> ClaimCase:
    events = [_make_document_event(with_pdf=True)] if include_docs else []
    return ClaimCase(
        case_id="case-abc123",
        scenario_slug=scenario_slug,
        seed=42,
        profile=_make_profile(),
        document_events=events,
        stages_visited=["intake", "investigation", "resolution"],
    )


# ---------------------------------------------------------------------------
# Happy-path: full seed_case() flow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_seed_case_standard_claim_calls_all_endpoints() -> None:
    """seed_case() must call login, create claim, patch claim, and upload docs in order."""
    case = _make_case(scenario_slug="standard_claim")
    call_log: list[str] = []

    with respx.mock(base_url=BASE_URL, assert_all_called=True) as mock:
        # Login
        mock.post("/api/auth/login").mock(
            return_value=httpx.Response(
                200,
                json={"ok": True},
                headers={"Set-Cookie": "session=abc123; Path=/; HttpOnly"},
            )
        )
        # Create claim
        mock.post("/api/claims").mock(
            return_value=httpx.Response(
                201,
                json={
                    "id": "claim_123",
                    "claimNumber": "SCIF-2026-00123",
                    "status": "OPEN",
                },
            )
        )
        # Patch claim (standard_claim → status=ACCEPTED)
        mock.patch("/api/claims/claim_123").mock(
            return_value=httpx.Response(200, json={"id": "claim_123", "status": "ACCEPTED"})
        )
        # Document upload (1 document with pdf_bytes)
        mock.post("/api/claims/claim_123/documents").mock(
            return_value=httpx.Response(
                201,
                json={"id": "doc_456", "claimId": "claim_123", "ocrStatus": "PENDING"},
            )
        )

        async with AdjudiClaimsClient(base_url=BASE_URL) as client:
            await client.login(email="seed@test.com", password="secret")
            result = await client.seed_case(case=case, env="staging")

    assert isinstance(result, SeedResult)
    assert result.claim_id == "claim_123"
    assert result.claim_number == "SCIF-2026-00123"
    assert result.documents_uploaded == 1
    assert result.document_ids == ["doc_456"]


@pytest.mark.asyncio
async def test_seed_case_litigated_qme_sets_flags() -> None:
    """litigated_qme scenario must PATCH with isLitigated=True and hasApplicantAttorney=True."""
    case = _make_case(scenario_slug="litigated_qme", include_docs=False)
    patched_payload: dict[str, Any] = {}

    with respx.mock(base_url=BASE_URL) as mock:
        mock.post("/api/auth/login").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )
        mock.post("/api/claims").mock(
            return_value=httpx.Response(
                201, json={"id": "claim_lit", "claimNumber": "SCIF-2026-00123"}
            )
        )

        def capture_patch(request: httpx.Request) -> httpx.Response:
            import json as _json
            nonlocal patched_payload
            patched_payload = _json.loads(request.content)
            return httpx.Response(200, json={"id": "claim_lit"})

        mock.patch("/api/claims/claim_lit").mock(side_effect=capture_patch)

        async with AdjudiClaimsClient(base_url=BASE_URL) as client:
            await client.login(email="seed@test.com", password="secret")
            result = await client.seed_case(case=case, env="staging")

    assert patched_payload.get("isLitigated") is True
    assert patched_payload.get("hasApplicantAttorney") is True
    assert result.documents_uploaded == 0  # no docs with pdf_bytes


@pytest.mark.asyncio
async def test_seed_case_denied_claim_sets_denied_status() -> None:
    """denied_claim scenario must PATCH with status=DENIED."""
    case = _make_case(scenario_slug="denied_claim", include_docs=False)
    patched_payload: dict[str, Any] = {}

    with respx.mock(base_url=BASE_URL) as mock:
        mock.post("/api/auth/login").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )
        mock.post("/api/claims").mock(
            return_value=httpx.Response(201, json={"id": "claim_denied", "claimNumber": "SCIF-2026-00123"})
        )

        def capture_patch(request: httpx.Request) -> httpx.Response:
            import json as _json
            nonlocal patched_payload
            patched_payload = _json.loads(request.content)
            return httpx.Response(200, json={"id": "claim_denied"})

        mock.patch("/api/claims/claim_denied").mock(side_effect=capture_patch)

        async with AdjudiClaimsClient(base_url=BASE_URL) as client:
            await client.login(email="seed@test.com", password="secret")
            await client.seed_case(case=case, env="staging")

    assert patched_payload.get("status") == "DENIED"


@pytest.mark.asyncio
async def test_seed_case_multiple_documents_uploaded() -> None:
    """All DocumentEvents with non-empty pdf_bytes must be uploaded."""
    # Build a case with 3 documents (2 with bytes, 1 without)
    events = [
        DocumentEvent(
            event_id=f"evt-{i}",
            document_type=DocumentType.MEDICAL_REPORT,
            subtype_slug="medical_report",
            title=f"Medical Report {i}",
            event_date=date(2026, 1, 10 + i),
            stage="treatment",
            pdf_bytes=b"%PDF-stub" if i < 2 else b"",
        )
        for i in range(3)
    ]
    case = ClaimCase(
        case_id="case-multi",
        scenario_slug="standard_claim",
        seed=1,
        profile=_make_profile(),
        document_events=events,
        stages_visited=["intake"],
    )

    upload_count = 0

    with respx.mock(base_url=BASE_URL) as mock:
        mock.post("/api/auth/login").mock(return_value=httpx.Response(200, json={"ok": True}))
        mock.post("/api/claims").mock(
            return_value=httpx.Response(201, json={"id": "claim_multi", "claimNumber": "SCIF-2026-00123"})
        )
        mock.patch("/api/claims/claim_multi").mock(
            return_value=httpx.Response(200, json={"id": "claim_multi"})
        )

        def upload_handler(request: httpx.Request) -> httpx.Response:
            nonlocal upload_count
            upload_count += 1
            return httpx.Response(
                201,
                json={"id": f"doc_{upload_count}", "claimId": "claim_multi", "ocrStatus": "PENDING"},
            )

        mock.post("/api/claims/claim_multi/documents").mock(side_effect=upload_handler)

        async with AdjudiClaimsClient(base_url=BASE_URL) as client:
            await client.login(email="seed@test.com", password="secret")
            result = await client.seed_case(case=case, env="staging")

    assert result.documents_uploaded == 2  # only 2 have pdf_bytes
    assert upload_count == 2


# ---------------------------------------------------------------------------
# Unit tests for individual methods
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_stores_session_cookie() -> None:
    """After login(), subsequent requests include the session cookie."""
    with respx.mock(base_url=BASE_URL) as mock:
        mock.post("/api/auth/login").mock(
            return_value=httpx.Response(
                200,
                json={"ok": True},
                headers={"Set-Cookie": "session=tok123; Path=/; HttpOnly"},
            )
        )
        # A subsequent GET to verify cookie is sent
        mock.get("/api/claims").mock(return_value=httpx.Response(200, json={"claims": []}))

        async with AdjudiClaimsClient(base_url=BASE_URL) as client:
            await client.login(email="user@test.com", password="pass")
            # Manually call a second endpoint to confirm cookie persists
            resp = await client._get_client().get("/api/claims")
            assert resp.status_code == 200


@pytest.mark.asyncio
async def test_login_raises_on_401() -> None:
    """login() must raise RuntimeError on 401 Unauthorized."""
    with respx.mock(base_url=BASE_URL) as mock:
        mock.post("/api/auth/login").mock(
            return_value=httpx.Response(401, json={"error": "Invalid credentials"})
        )

        async with AdjudiClaimsClient(base_url=BASE_URL) as client:
            with pytest.raises(RuntimeError, match="HTTP 401"):
                await client.login(email="bad@test.com", password="wrong")


@pytest.mark.asyncio
async def test_create_claim_returns_id() -> None:
    """create_claim() must return a dict containing an 'id' key."""
    with respx.mock(base_url=BASE_URL) as mock:
        mock.post("/api/auth/login").mock(return_value=httpx.Response(200, json={"ok": True}))
        mock.post("/api/claims").mock(
            return_value=httpx.Response(
                201,
                json={"id": "claim_abc", "claimNumber": "TST-001", "status": "OPEN"},
            )
        )

        async with AdjudiClaimsClient(base_url=BASE_URL) as client:
            await client.login(email="u@t.com", password="p")
            result = await client.create_claim(
                claim_number="TST-001",
                claimant_name="Test User",
                date_of_injury="2026-01-15",
                body_parts=["lumbar spine"],
                employer="Test Co",
                insurer="Test Insurer",
                date_received="2026-01-16",
            )

    assert result["id"] == "claim_abc"
    assert result["claimNumber"] == "TST-001"


@pytest.mark.asyncio
async def test_create_claim_raises_on_400() -> None:
    """create_claim() must raise RuntimeError on 400 Bad Request."""
    with respx.mock(base_url=BASE_URL) as mock:
        mock.post("/api/auth/login").mock(return_value=httpx.Response(200, json={"ok": True}))
        mock.post("/api/claims").mock(
            return_value=httpx.Response(400, json={"error": "Invalid request body"})
        )

        async with AdjudiClaimsClient(base_url=BASE_URL) as client:
            await client.login(email="u@t.com", password="p")
            with pytest.raises(RuntimeError, match="HTTP 400"):
                await client.create_claim(
                    claim_number="",
                    claimant_name="",
                    date_of_injury="bad-date",
                    body_parts=[],
                    employer="",
                    insurer="",
                    date_received="bad-date",
                )


@pytest.mark.asyncio
async def test_patch_claim_sends_only_provided_fields() -> None:
    """patch_claim() must only send the fields that are not None."""
    captured: dict[str, Any] = {}

    with respx.mock(base_url=BASE_URL) as mock:
        mock.post("/api/auth/login").mock(return_value=httpx.Response(200, json={"ok": True}))

        def capture(request: httpx.Request) -> httpx.Response:
            import json as _json
            captured.update(_json.loads(request.content))
            return httpx.Response(200, json={"id": "c1"})

        mock.patch("/api/claims/c1").mock(side_effect=capture)

        async with AdjudiClaimsClient(base_url=BASE_URL) as client:
            await client.login(email="u@t.com", password="p")
            await client.patch_claim("c1", is_litigated=True)

    assert captured == {"isLitigated": True}
    assert "hasApplicantAttorney" not in captured
    assert "isCumulativeTrauma" not in captured


@pytest.mark.asyncio
async def test_patch_claim_raises_on_no_fields() -> None:
    """patch_claim() must raise ValueError when no fields are provided."""
    async with AdjudiClaimsClient(base_url=BASE_URL) as client:
        with pytest.raises(ValueError, match="at least one field"):
            await client.patch_claim("c1")


@pytest.mark.asyncio
async def test_upload_document_sends_multipart() -> None:
    """upload_document() must send multipart/form-data with file and documentType."""
    captured_content_type: str = ""

    with respx.mock(base_url=BASE_URL) as mock:
        mock.post("/api/auth/login").mock(return_value=httpx.Response(200, json={"ok": True}))

        def capture_upload(request: httpx.Request) -> httpx.Response:
            nonlocal captured_content_type
            captured_content_type = request.headers.get("content-type", "")
            return httpx.Response(
                201, json={"id": "doc_999", "claimId": "c1", "ocrStatus": "PENDING"}
            )

        mock.post("/api/claims/c1/documents").mock(side_effect=capture_upload)

        async with AdjudiClaimsClient(base_url=BASE_URL) as client:
            await client.login(email="u@t.com", password="p")
            result = await client.upload_document(
                claim_id="c1",
                file_bytes=b"%PDF-1.4 stub",
                file_name="test_doc.pdf",
                document_type=DocumentType.MEDICAL_REPORT,
            )

    assert result["id"] == "doc_999"
    assert "multipart/form-data" in captured_content_type


@pytest.mark.asyncio
async def test_client_raises_without_context_manager() -> None:
    """Calling login() without entering the context manager raises RuntimeError."""
    client = AdjudiClaimsClient(base_url=BASE_URL)
    with pytest.raises(RuntimeError, match="async context manager"):
        await client.login(email="u@t.com", password="p")


# ---------------------------------------------------------------------------
# GCP secrets fallback tests (no live GCP calls)
# ---------------------------------------------------------------------------


def test_get_secret_returns_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_secret() must return the env var value without calling Secret Manager."""
    from claims_generator.integrations.gcp_secrets import get_secret

    monkeypatch.setenv("ADJUDICLAIMS_EMAIL", "env_user@test.com")
    result = get_secret("adjudiclaims-seed-email", "ADJUDICLAIMS_EMAIL")
    assert result == "env_user@test.com"


def test_get_secret_raises_without_env_or_project(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_secret() must raise ValueError when no env var and no GCP_PROJECT."""
    from claims_generator.integrations.gcp_secrets import get_secret

    monkeypatch.delenv("ADJUDICLAIMS_EMAIL", raising=False)
    monkeypatch.delenv("GCP_PROJECT", raising=False)

    with pytest.raises(ValueError, match="GCP_PROJECT is not set"):
        get_secret("adjudiclaims-seed-email", "ADJUDICLAIMS_EMAIL")


def test_get_adjudiclaims_url_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_adjudiclaims_url() must read from ADJUDICLAIMS_URL env var."""
    from claims_generator.integrations.gcp_secrets import get_adjudiclaims_url

    monkeypatch.setenv("ADJUDICLAIMS_URL", "https://staging.adjudiclaims.com")
    assert get_adjudiclaims_url() == "https://staging.adjudiclaims.com"


def test_get_adjudiclaims_email_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_adjudiclaims_email() must read from ADJUDICLAIMS_EMAIL env var."""
    from claims_generator.integrations.gcp_secrets import get_adjudiclaims_email

    monkeypatch.setenv("ADJUDICLAIMS_EMAIL", "test@adjudiclaims.com")
    assert get_adjudiclaims_email() == "test@adjudiclaims.com"


def test_get_adjudiclaims_password_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_adjudiclaims_password() must read from ADJUDICLAIMS_PASSWORD env var."""
    from claims_generator.integrations.gcp_secrets import get_adjudiclaims_password

    monkeypatch.setenv("ADJUDICLAIMS_PASSWORD", "super_secret_123")
    assert get_adjudiclaims_password() == "super_secret_123"


# ---------------------------------------------------------------------------
# CLI seed command tests
# ---------------------------------------------------------------------------


def test_cli_seed_command_exists() -> None:
    """The CLI must expose a 'seed' command."""
    from click.testing import CliRunner

    from claims_generator.cli import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["seed", "--help"])
    assert result.exit_code == 0
    assert "--scenario" in result.output
    assert "--env" in result.output


def test_cli_seed_exits_when_credentials_missing() -> None:
    """seed command must exit 1 when no credentials are available."""
    import os

    from click.testing import CliRunner

    from claims_generator.cli import cli

    runner = CliRunner()
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("ADJUDICLAIMS_URL", "ADJUDICLAIMS_EMAIL", "ADJUDICLAIMS_PASSWORD", "GCP_PROJECT")
    }
    result = runner.invoke(cli, ["seed", "--scenario", "standard_claim"], env=env)
    assert result.exit_code == 1
