# Spectacles Authentication Flow Testing Guide

**Implementation of Recommendation E from SPECTACLES_UTILIZATION_RECOMMENDATIONS.md**

**Status:** Complete - Ready for implementation
**Created:** 2026-01-27
**Projects Analyzed:** Attorney Dashboard, Legal Research Dashboard, Glassy Platform

---

## Executive Summary

This guide provides reusable authentication flow testing patterns using Spectacles for automated visual verification. All patterns use GCP Secret Manager for credential storage and support both automated testing and human-escalation workflows.

**Time Savings:** 10-20 minutes per auth flow test × 2-3 tests/month = 20-60 min/month
**Test Coverage:** Enables continuous auth validation, prevents regressions

---

## Table of Contents

1. [Authentication Flows Identified](#authentication-flows-identified)
2. [GCP Secret Manager Setup](#gcp-secret-manager-setup)
3. [Reusable Auth Testing Patterns](#reusable-auth-testing-patterns)
4. [Project-Specific Implementations](#project-specific-implementations)
5. [Integration with GSD Workflows](#integration-with-gsd-workflows)
6. [Troubleshooting](#troubleshooting)

---

## Authentication Flows Identified

### Attorney Dashboard

| Flow | Type | Complexity | Test Frequency |
|------|------|------------|----------------|
| **BetterAuth Login** | Email + Password | Simple | Every deploy |
| **Role-Based UI** | Admin vs Attorney vs Staff | Medium | Weekly |
| **Session Persistence** | Cookie validation | Simple | Weekly |

**URLs:**
- Production: https://attorney-dashboard-web-5paunecalq-uc.a.run.app
- Backend: https://attorney-dashboard-api-5paunecalq-uc.a.run.app

### Legal Research Dashboard

| Flow | Type | Complexity | Test Frequency |
|------|------|------------|----------------|
| **Backend API Auth** | Token-based | Simple | Every deploy |
| **Dashboard Access** | Read-only validation | Simple | Every deploy |

**URLs:**
- Frontend: https://legal-research-dashboard-816980776764.us-central1.run.app
- Backend: https://legal-research-backend-378330630438.us-central1.run.app

### Glassy Platform

| Flow | Type | Complexity | Test Frequency |
|------|------|------------|----------------|
| **BetterAuth Registration** | Email + Password | Simple | Weekly |
| **BetterAuth Login** | Email + Password | Simple | Every deploy |
| **OAuth (GitHub)** | OAuth 2.0 | Complex | Weekly |
| **OAuth (Google)** | OAuth 2.0 | Complex | Weekly |
| **Organization Setup** | Multi-step form | Medium | Weekly |
| **Session Persistence** | Cookie validation | Simple | Weekly |

**URLs:**
- Web: https://glassy.glassboxsolutions.com
- API: https://api.glassy.glassboxsolutions.com

---

## GCP Secret Manager Setup

### Secret Naming Convention

```
spectacles-{project}-{environment}-{role}
```

**Examples:**
- `spectacles-attorney-dashboard-prod-admin`
- `spectacles-attorney-dashboard-prod-attorney`
- `spectacles-glassy-prod-testuser`
- `spectacles-legal-research-prod-viewer`

### Secret Structure (JSON)

```json
{
  "email": "test-admin@example.com",
  "password": "secure-test-password",
  "username": "testadmin",
  "notes": "Admin account for automated testing"
}
```

### Creating Secrets

```bash
# Attorney Dashboard - Admin user
echo -n '{
  "email": "test-admin@glassboxsolutions.com",
  "password": "SecureTestPass123!",
  "notes": "Admin account for Attorney Dashboard testing"
}' | gcloud secrets create spectacles-attorney-dashboard-prod-admin \
  --data-file=- \
  --project=ousd-campaign \
  --replication-policy=automatic

# Attorney Dashboard - Attorney user
echo -n '{
  "email": "test-attorney@glassboxsolutions.com",
  "password": "SecureTestPass123!",
  "notes": "Attorney account for Attorney Dashboard testing"
}' | gcloud secrets create spectacles-attorney-dashboard-prod-attorney \
  --data-file=- \
  --project=ousd-campaign \
  --replication-policy=automatic

# Glassy - Test user
echo -n '{
  "email": "test-user@glassboxsolutions.com",
  "password": "SecureTestPass123!",
  "username": "glassytest",
  "notes": "Test user for Glassy platform"
}' | gcloud secrets create spectacles-glassy-prod-testuser \
  --data-file=- \
  --project=ousd-campaign \
  --replication-policy=automatic

# Glassy - GitHub OAuth test account
echo -n '{
  "username": "glassbox-test",
  "password": "SecureGitHubPass123!",
  "notes": "GitHub account for OAuth testing"
}' | gcloud secrets create spectacles-glassy-github-oauth \
  --data-file=- \
  --project=ousd-campaign \
  --replication-policy=automatic

# Legal Research - Viewer account
echo -n '{
  "token": "test-api-token-placeholder",
  "notes": "API token for Legal Research Dashboard"
}' | gcloud secrets create spectacles-legal-research-prod-viewer \
  --data-file=- \
  --project=ousd-campaign \
  --replication-policy=automatic
```

### Accessing Secrets (Spectacles)

Spectacles automatically fetches secrets from GCP Secret Manager:

```python
# In Spectacles code - already implemented
from security.secrets_vault import SecretsVault

vault = SecretsVault(project_id="ousd-campaign")
credentials = await vault.get_credentials("spectacles-attorney-dashboard-prod-admin")

# Returns parsed JSON:
# {
#   "email": "test-admin@glassboxsolutions.com",
#   "password": "SecureTestPass123!"
# }
```

---

## Reusable Auth Testing Patterns

### Pattern 1: Simple Login Flow

**Use for:** BetterAuth, standard email/password forms

```python
from spectacles import execute_task

async def test_login_flow(
    app_name: str,
    login_url: str,
    credentials_key: str,
    success_indicator: str
):
    """
    Generic login flow test.

    Args:
        app_name: Human-readable app name (e.g., "Attorney Dashboard")
        login_url: URL of login page
        credentials_key: GCP Secret Manager key
        success_indicator: Text/element that indicates successful login

    Returns:
        Test result with screenshots and status
    """
    result = await execute_task(
        goal=f"Log into {app_name} and verify successful authentication",
        start_url=login_url,
        credentials_key=credentials_key,
        require_approval=False  # Automated test
    )

    # Verify success
    if success_indicator.lower() in result["final_observation"].lower():
        return {
            "status": "passed",
            "message": f"{app_name} login successful",
            "screenshot": result.get("screenshot_url")
        }
    else:
        return {
            "status": "failed",
            "message": f"{app_name} login failed - success indicator not found",
            "screenshot": result.get("screenshot_url"),
            "observation": result["final_observation"]
        }
```

**Example Usage:**

```python
# Test Attorney Dashboard admin login
result = await test_login_flow(
    app_name="Attorney Dashboard",
    login_url="https://attorney-dashboard-web-5paunecalq-uc.a.run.app/login",
    credentials_key="spectacles-attorney-dashboard-prod-admin",
    success_indicator="dashboard"  # Redirect to /dashboard after login
)
```

### Pattern 2: OAuth Flow Testing

**Use for:** GitHub OAuth, Google OAuth, third-party SSO

```python
async def test_oauth_flow(
    provider: str,
    auth_url: str,
    credentials_key: str,
    callback_url_pattern: str
):
    """
    Test OAuth flow completion and callback.

    Args:
        provider: OAuth provider name (e.g., "GitHub", "Google")
        auth_url: OAuth authorization URL
        credentials_key: GCP Secret Manager key for OAuth account
        callback_url_pattern: Expected callback URL pattern (for verification)

    Returns:
        Test result with authorization details
    """
    result = await execute_task(
        goal=f"Complete {provider} OAuth flow and verify successful callback",
        start_url=auth_url,
        credentials_key=credentials_key,
        require_approval=False
    )

    final_url = result.get("final_url", "")

    if callback_url_pattern in final_url:
        return {
            "status": "passed",
            "message": f"{provider} OAuth flow completed successfully",
            "callback_url": final_url,
            "screenshot": result.get("screenshot_url")
        }
    else:
        return {
            "status": "failed",
            "message": f"{provider} OAuth callback URL mismatch",
            "expected_pattern": callback_url_pattern,
            "actual_url": final_url,
            "screenshot": result.get("screenshot_url")
        }
```

**Example Usage:**

```python
# Test Glassy GitHub OAuth
result = await test_oauth_flow(
    provider="GitHub",
    auth_url="https://glassy.glassboxsolutions.com/auth/github",
    credentials_key="spectacles-glassy-github-oauth",
    callback_url_pattern="glassy.glassboxsolutions.com/dashboard"
)
```

### Pattern 3: Role-Based UI Verification

**Use for:** Admin vs Attorney vs Staff, permission-based UIs

```python
async def test_role_based_ui(
    app_name: str,
    login_url: str,
    credentials_key: str,
    role: str,
    expected_elements: list[str],
    forbidden_elements: list[str]
):
    """
    Test role-based UI rendering and permissions.

    Args:
        app_name: Application name
        login_url: Login page URL
        credentials_key: GCP Secret Manager key for role account
        role: Role name (e.g., "admin", "attorney", "staff")
        expected_elements: Elements that SHOULD be visible
        forbidden_elements: Elements that SHOULD NOT be visible

    Returns:
        Test result with permission validation
    """
    result = await execute_task(
        goal=f"Log into {app_name} as {role} and verify UI permissions",
        start_url=login_url,
        credentials_key=credentials_key,
        require_approval=False
    )

    observation = result["final_observation"].lower()

    # Check expected elements are present
    missing_elements = [
        elem for elem in expected_elements
        if elem.lower() not in observation
    ]

    # Check forbidden elements are absent
    present_forbidden = [
        elem for elem in forbidden_elements
        if elem.lower() in observation
    ]

    if not missing_elements and not present_forbidden:
        return {
            "status": "passed",
            "message": f"{role} UI permissions correct",
            "role": role,
            "screenshot": result.get("screenshot_url")
        }
    else:
        return {
            "status": "failed",
            "message": f"{role} UI permissions incorrect",
            "missing_elements": missing_elements,
            "forbidden_elements_present": present_forbidden,
            "screenshot": result.get("screenshot_url")
        }
```

**Example Usage:**

```python
# Test Attorney Dashboard attorney role
result = await test_role_based_ui(
    app_name="Attorney Dashboard",
    login_url="https://attorney-dashboard-web-5paunecalq-uc.a.run.app/login",
    credentials_key="spectacles-attorney-dashboard-prod-attorney",
    role="attorney",
    expected_elements=["Cases", "Analytics", "Chat"],
    forbidden_elements=["User Management", "Delete All Cases"]
)
```

### Pattern 4: Auth State Capture (Interactive Login)

**Use for:** Capturing browser state for services without API access (Westlaw, MerusCase, etc.)

Spectacles provides a first-class auth capture system that opens a live Browserless session, lets the user log in manually, then captures and persists the browser state.

**CLI Tool:**
```bash
# Capture with built-in preset
python projects/spectacles/tools/capture_auth.py --service google
python projects/spectacles/tools/capture_auth.py --service meruscase
python projects/spectacles/tools/capture_auth.py --service westlaw

# Capture with custom service
python projects/spectacles/tools/capture_auth.py --service myapp \
    --login-url https://myapp.com/login \
    --verify-url https://myapp.com/dashboard
```

**API (Two-Step Flow):**
```python
import httpx

SPECTACLES_URL = "https://spectacles-383072931874.us-central1.run.app"

async with httpx.AsyncClient() as client:
    # Step 1: Start capture session
    response = await client.post(f"{SPECTACLES_URL}/api/skills/auth-capture", json={
        "service": "westlaw"
    })
    session = response.json()
    print(f"Open in browser: {session['live_url']}")
    # User logs in via live_url...

    # Step 2: Complete capture
    response = await client.post(
        f"{SPECTACLES_URL}/api/skills/auth-capture/{session['session_id']}/complete"
    )
    result = response.json()
    print(f"Captured {result['cookie_count']} cookies, verified: {result['verified']}")
```

**Python (Direct Import):**
```python
from security.auth_capture import AuthCaptureSession

async with AuthCaptureSession(
    service="westlaw",
    browserless_token="YOUR_TOKEN",
    browserless_wss="wss://production-sfo.browserless.io"
) as session:
    live_url = await session.start()
    print(f"Log in at: {live_url}")
    input("Press Enter after login...")
    state = await session.capture()
    results = await session.save(local_dir=".auth", gcp_project="ousd-campaign")
    verified = await session.verify()
    print(f"Saved: {results['cookie_count']} cookies, Verified: {verified}")
```

**Built-in Presets:** Google, GitHub, MerusCase, Westlaw

**Saved State Locations:**
- Local: `.auth/{credential_key}.json`
- GCP: Secret Manager → `{credential_key}-storage-state`

### Pattern 5: Session Persistence Test

**Use for:** Cookie validation, session expiry, remember me

```python
async def test_session_persistence(
    app_name: str,
    login_url: str,
    credentials_key: str,
    protected_url: str,
    wait_seconds: int = 60
):
    """
    Test session persistence and cookie validity.

    Args:
        app_name: Application name
        login_url: Login page URL
        credentials_key: GCP Secret Manager key
        protected_url: URL that requires authentication
        wait_seconds: Time to wait before checking persistence

    Returns:
        Test result with session validation
    """
    import asyncio

    # Step 1: Login
    login_result = await execute_task(
        goal=f"Log into {app_name}",
        start_url=login_url,
        credentials_key=credentials_key,
        require_approval=False
    )

    # Step 2: Wait (simulate time passing)
    await asyncio.sleep(wait_seconds)

    # Step 3: Navigate to protected page without credentials
    # (Spectacles will use saved session cookies)
    persist_result = await execute_task(
        goal=f"Navigate to {protected_url} and verify still authenticated",
        start_url=protected_url,
        credentials_key=None,  # Should use existing session
        require_approval=False
    )

    # If we see login form, session expired
    if "login" in persist_result["final_observation"].lower():
        return {
            "status": "failed",
            "message": f"Session expired after {wait_seconds}s",
            "screenshot": persist_result.get("screenshot_url")
        }
    else:
        return {
            "status": "passed",
            "message": f"Session persisted for {wait_seconds}s",
            "screenshot": persist_result.get("screenshot_url")
        }
```

**Example Usage:**

```python
# Test Glassy session persistence
result = await test_session_persistence(
    app_name="Glassy",
    login_url="https://glassy.glassboxsolutions.com/login",
    credentials_key="spectacles-glassy-prod-testuser",
    protected_url="https://glassy.glassboxsolutions.com/chat",
    wait_seconds=300  # 5 minutes
)
```

---

## Project-Specific Implementations

### Attorney Dashboard Auth Tests

**File:** `projects/attorney-dashboard/.planning/testing/auth-flows.py`

```python
"""
Attorney Dashboard - Authentication Flow Tests
Uses Spectacles for automated visual verification.
"""

import asyncio
from spectacles import execute_task

# Test credentials (stored in GCP Secret Manager)
ADMIN_CREDS = "spectacles-attorney-dashboard-prod-admin"
ATTORNEY_CREDS = "spectacles-attorney-dashboard-prod-attorney"
STAFF_CREDS = "spectacles-attorney-dashboard-prod-staff"

BASE_URL = "https://attorney-dashboard-web-5paunecalq-uc.a.run.app"


async def test_admin_login():
    """Test 1: Admin user login flow"""
    print("🔐 Testing admin login...")

    result = await execute_task(
        goal="Log into Attorney Dashboard as admin and verify dashboard loads",
        start_url=f"{BASE_URL}/login",
        credentials_key=ADMIN_CREDS,
        require_approval=False
    )

    # Verify admin-specific UI elements
    observation = result["final_observation"].lower()

    checks = {
        "Dashboard loads": "dashboard" in observation or "cases" in observation,
        "Admin menu visible": "user management" in observation or "settings" in observation,
        "No errors": "error" not in observation and "404" not in observation
    }

    passed = all(checks.values())

    return {
        "test": "Admin Login",
        "status": "✅ PASS" if passed else "❌ FAIL",
        "checks": checks,
        "screenshot": result.get("screenshot_url")
    }


async def test_attorney_permissions():
    """Test 2: Attorney role UI permissions"""
    print("👨‍⚖️ Testing attorney permissions...")

    result = await execute_task(
        goal="Log in as attorney and verify correct UI permissions",
        start_url=f"{BASE_URL}/login",
        credentials_key=ATTORNEY_CREDS,
        require_approval=False
    )

    observation = result["final_observation"].lower()

    # Attorney should see cases but not user management
    checks = {
        "Cases visible": "cases" in observation,
        "Analytics visible": "analytics" in observation or "dashboard" in observation,
        "Chat visible": "chat" in observation,
        "User management hidden": "user management" not in observation,
        "Delete hidden": "delete all" not in observation
    }

    passed = all(checks.values())

    return {
        "test": "Attorney Permissions",
        "status": "✅ PASS" if passed else "❌ FAIL",
        "checks": checks,
        "screenshot": result.get("screenshot_url")
    }


async def test_staff_permissions():
    """Test 3: Staff role UI permissions"""
    print("📋 Testing staff permissions...")

    result = await execute_task(
        goal="Log in as staff and verify limited permissions",
        start_url=f"{BASE_URL}/login",
        credentials_key=STAFF_CREDS,
        require_approval=False
    )

    observation = result["final_observation"].lower()

    # Staff should have limited access
    checks = {
        "Cases visible": "cases" in observation,
        "Update allowed": "update" in observation or "edit" in observation,
        "Financial data hidden": "settlement authority" not in observation,
        "Delete hidden": "delete" not in observation,
        "User management hidden": "user management" not in observation
    }

    passed = all(checks.values())

    return {
        "test": "Staff Permissions",
        "status": "✅ PASS" if passed else "❌ FAIL",
        "checks": checks,
        "screenshot": result.get("screenshot_url")
    }


async def test_session_persistence():
    """Test 4: Session cookie persistence"""
    print("🍪 Testing session persistence...")

    # Login
    login_result = await execute_task(
        goal="Log into Attorney Dashboard",
        start_url=f"{BASE_URL}/login",
        credentials_key=ADMIN_CREDS,
        require_approval=False
    )

    # Wait 2 minutes
    print("⏳ Waiting 2 minutes to test session...")
    await asyncio.sleep(120)

    # Try accessing protected page
    persist_result = await execute_task(
        goal="Navigate to cases page and verify still authenticated",
        start_url=f"{BASE_URL}/cases",
        credentials_key=None,  # Use existing session
        require_approval=False
    )

    # Should NOT see login form
    observation = persist_result["final_observation"].lower()
    session_valid = "login" not in observation and "sign in" not in observation

    return {
        "test": "Session Persistence",
        "status": "✅ PASS" if session_valid else "❌ FAIL",
        "checks": {
            "Session persisted 2min": session_valid,
            "Protected page accessible": "cases" in observation
        },
        "screenshot": persist_result.get("screenshot_url")
    }


async def run_all_tests():
    """Run all Attorney Dashboard auth tests"""
    print("=" * 60)
    print("Attorney Dashboard - Authentication Flow Tests")
    print("=" * 60)

    tests = [
        test_admin_login(),
        test_attorney_permissions(),
        test_staff_permissions(),
        test_session_persistence()
    ]

    results = await asyncio.gather(*tests, return_exceptions=True)

    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)

    for result in results:
        if isinstance(result, Exception):
            print(f"❌ Test failed with exception: {result}")
        else:
            print(f"\n{result['test']}: {result['status']}")
            for check, passed in result['checks'].items():
                icon = "✅" if passed else "❌"
                print(f"  {icon} {check}")

    # Summary
    passed_count = sum(1 for r in results if isinstance(r, dict) and "✅" in r['status'])
    total_count = len(results)

    print("\n" + "=" * 60)
    print(f"SUMMARY: {passed_count}/{total_count} tests passed")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_all_tests())
```

**Run tests:**
```bash
cd projects/attorney-dashboard
python .planning/testing/auth-flows.py
```

### Glassy Platform Auth Tests

**File:** `projects/glassy/.planning/testing/auth-flows.py`

```python
"""
Glassy Platform - Authentication Flow Tests
Covers BetterAuth, GitHub OAuth, Google OAuth, organization setup.
"""

import asyncio
from spectacles import execute_task

# Test credentials
TESTUSER_CREDS = "spectacles-glassy-prod-testuser"
GITHUB_CREDS = "spectacles-glassy-github-oauth"
GOOGLE_CREDS = "spectacles-glassy-google-oauth"

WEB_URL = "https://glassy.glassboxsolutions.com"


async def test_betterauth_registration():
    """Test 1: User registration flow"""
    print("📝 Testing BetterAuth registration...")

    # Generate unique email for this test
    import uuid
    test_email = f"test-{uuid.uuid4().hex[:8]}@glassboxsolutions.com"

    result = await execute_task(
        goal=f"Register new user with email {test_email} and password SecureTest123!",
        start_url=f"{WEB_URL}/register",
        credentials_key=None,  # No existing credentials
        require_approval=False
    )

    observation = result["final_observation"].lower()

    checks = {
        "Registration form loads": "register" in observation or "sign up" in observation,
        "No errors": "error" not in observation,
        "Success or redirect": "dashboard" in observation or "welcome" in observation
    }

    passed = all(checks.values())

    return {
        "test": "BetterAuth Registration",
        "status": "✅ PASS" if passed else "❌ FAIL",
        "checks": checks,
        "screenshot": result.get("screenshot_url"),
        "test_email": test_email
    }


async def test_betterauth_login():
    """Test 2: Standard login flow"""
    print("🔐 Testing BetterAuth login...")

    result = await execute_task(
        goal="Log into Glassy with test account credentials",
        start_url=f"{WEB_URL}/login",
        credentials_key=TESTUSER_CREDS,
        require_approval=False
    )

    observation = result["final_observation"].lower()

    checks = {
        "Login successful": "dashboard" in observation or "chat" in observation,
        "No errors": "error" not in observation and "invalid" not in observation,
        "User UI visible": "logout" in observation or "profile" in observation
    }

    passed = all(checks.values())

    return {
        "test": "BetterAuth Login",
        "status": "✅ PASS" if passed else "❌ FAIL",
        "checks": checks,
        "screenshot": result.get("screenshot_url")
    }


async def test_github_oauth():
    """Test 3: GitHub OAuth flow"""
    print("🔗 Testing GitHub OAuth...")

    result = await execute_task(
        goal="Complete GitHub OAuth login and verify callback",
        start_url=f"{WEB_URL}/auth/github",
        credentials_key=GITHUB_CREDS,
        require_approval=False
    )

    final_url = result.get("final_url", "")
    observation = result["final_observation"].lower()

    checks = {
        "OAuth flow completed": "glassy.glassboxsolutions.com" in final_url,
        "Callback successful": "dashboard" in observation or "chat" in observation,
        "No errors": "error" not in observation
    }

    passed = all(checks.values())

    return {
        "test": "GitHub OAuth",
        "status": "✅ PASS" if passed else "❌ FAIL",
        "checks": checks,
        "final_url": final_url,
        "screenshot": result.get("screenshot_url")
    }


async def test_organization_setup():
    """Test 4: Organization creation flow"""
    print("🏢 Testing organization setup...")

    # Login first
    await execute_task(
        goal="Log into Glassy",
        start_url=f"{WEB_URL}/login",
        credentials_key=TESTUSER_CREDS,
        require_approval=False
    )

    # Create organization
    result = await execute_task(
        goal="Navigate to organization settings and create new organization 'Test Org'",
        start_url=f"{WEB_URL}/settings/organizations",
        credentials_key=None,  # Use existing session
        require_approval=False
    )

    observation = result["final_observation"].lower()

    checks = {
        "Organization settings accessible": "organization" in observation,
        "Create form visible": "create" in observation or "new" in observation,
        "No errors": "error" not in observation
    }

    passed = all(checks.values())

    return {
        "test": "Organization Setup",
        "status": "✅ PASS" if passed else "❌ FAIL",
        "checks": checks,
        "screenshot": result.get("screenshot_url")
    }


async def test_session_persistence():
    """Test 5: Session cookie persistence (5 minutes)"""
    print("🍪 Testing session persistence...")

    # Login
    await execute_task(
        goal="Log into Glassy",
        start_url=f"{WEB_URL}/login",
        credentials_key=TESTUSER_CREDS,
        require_approval=False
    )

    # Wait 5 minutes
    print("⏳ Waiting 5 minutes to test session...")
    await asyncio.sleep(300)

    # Try accessing chat (protected route)
    result = await execute_task(
        goal="Navigate to chat and verify still authenticated",
        start_url=f"{WEB_URL}/chat",
        credentials_key=None,  # Use existing session
        require_approval=False
    )

    observation = result["final_observation"].lower()
    session_valid = "login" not in observation and "sign in" not in observation

    checks = {
        "Session persisted 5min": session_valid,
        "Chat accessible": "chat" in observation or "conversation" in observation
    }

    passed = all(checks.values())

    return {
        "test": "Session Persistence",
        "status": "✅ PASS" if passed else "❌ FAIL",
        "checks": checks,
        "screenshot": result.get("screenshot_url")
    }


async def run_all_tests():
    """Run all Glassy auth tests"""
    print("=" * 60)
    print("Glassy Platform - Authentication Flow Tests")
    print("=" * 60)

    tests = [
        test_betterauth_registration(),
        test_betterauth_login(),
        test_github_oauth(),
        test_organization_setup(),
        test_session_persistence()
    ]

    results = await asyncio.gather(*tests, return_exceptions=True)

    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)

    for result in results:
        if isinstance(result, Exception):
            print(f"❌ Test failed with exception: {result}")
        else:
            print(f"\n{result['test']}: {result['status']}")
            for check, passed in result['checks'].items():
                icon = "✅" if passed else "❌"
                print(f"  {icon} {check}")

    # Summary
    passed_count = sum(1 for r in results if isinstance(r, dict) and "✅" in r['status'])
    total_count = len(results)

    print("\n" + "=" * 60)
    print(f"SUMMARY: {passed_count}/{total_count} tests passed")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_all_tests())
```

**Run tests:**
```bash
cd projects/glassy
python .planning/testing/auth-flows.py
```

### Legal Research Dashboard Auth Tests

**File:** `projects/legal-research-dashboard/.planning/testing/auth-flows.py`

```python
"""
Legal Research Dashboard - Authentication Flow Tests
Tests backend API token validation and dashboard access.
"""

import asyncio
from spectacles import execute_task

# Test credentials
VIEWER_CREDS = "spectacles-legal-research-prod-viewer"

FRONTEND_URL = "https://legal-research-dashboard-816980776764.us-central1.run.app"
BACKEND_URL = "https://legal-research-backend-378330630438.us-central1.run.app"


async def test_dashboard_access():
    """Test 1: Dashboard loads without authentication (read-only)"""
    print("📊 Testing dashboard access...")

    result = await execute_task(
        goal="Navigate to Legal Research Dashboard and verify it loads",
        start_url=FRONTEND_URL,
        credentials_key=None,  # Dashboard is read-only
        require_approval=False
    )

    observation = result["final_observation"].lower()

    checks = {
        "Dashboard loads": "legal research" in observation or "cases" in observation,
        "No errors": "error" not in observation and "404" not in observation,
        "Data visible": "case" in observation or "research" in observation
    }

    passed = all(checks.values())

    return {
        "test": "Dashboard Access",
        "status": "✅ PASS" if passed else "❌ FAIL",
        "checks": checks,
        "screenshot": result.get("screenshot_url")
    }


async def test_backend_health():
    """Test 2: Backend API health check"""
    print("🏥 Testing backend health...")

    result = await execute_task(
        goal="Navigate to backend health endpoint and verify response",
        start_url=f"{BACKEND_URL}/health",
        credentials_key=None,
        require_approval=False
    )

    observation = result["final_observation"].lower()

    checks = {
        "Health endpoint responds": "ok" in observation or "healthy" in observation or "status" in observation,
        "No errors": "error" not in observation and "500" not in observation
    }

    passed = all(checks.values())

    return {
        "test": "Backend Health",
        "status": "✅ PASS" if passed else "❌ FAIL",
        "checks": checks,
        "screenshot": result.get("screenshot_url")
    }


async def test_cases_table():
    """Test 3: Cases table renders with data"""
    print("📋 Testing cases table...")

    result = await execute_task(
        goal="Navigate to cases page and verify table loads with data",
        start_url=f"{FRONTEND_URL}/cases",
        credentials_key=None,
        require_approval=False
    )

    observation = result["final_observation"].lower()

    checks = {
        "Cases page loads": "cases" in observation or "case" in observation,
        "Table visible": "table" in observation or "row" in observation or "column" in observation,
        "Data present": any(word in observation for word in ["plaintiff", "defendant", "injury", "research"]),
        "No errors": "error" not in observation
    }

    passed = all(checks.values())

    return {
        "test": "Cases Table",
        "status": "✅ PASS" if passed else "❌ FAIL",
        "checks": checks,
        "screenshot": result.get("screenshot_url")
    }


async def run_all_tests():
    """Run all Legal Research Dashboard auth tests"""
    print("=" * 60)
    print("Legal Research Dashboard - Authentication Flow Tests")
    print("=" * 60)

    tests = [
        test_dashboard_access(),
        test_backend_health(),
        test_cases_table()
    ]

    results = await asyncio.gather(*tests, return_exceptions=True)

    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)

    for result in results:
        if isinstance(result, Exception):
            print(f"❌ Test failed with exception: {result}")
        else:
            print(f"\n{result['test']}: {result['status']}")
            for check, passed in result['checks'].items():
                icon = "✅" if passed else "❌"
                print(f"  {icon} {check}")

    # Summary
    passed_count = sum(1 for r in results if isinstance(r, dict) and "✅" in r['status'])
    total_count = len(results)

    print("\n" + "=" * 60)
    print(f"SUMMARY: {passed_count}/{total_count} tests passed")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_all_tests())
```

**Run tests:**
```bash
cd projects/legal-research-dashboard
python .planning/testing/auth-flows.py
```

---

## Integration with GSD Workflows

### Adding Auth Tests to Deployment Plans

**Pattern for PLAN.md:**

```markdown
---
phase: XX-deployment
ai_supervision: true
confidence_threshold: 80
slack_channel: main
---

## Tasks

**Task 1:** Deploy to Cloud Run

<task type="auto">
  <name>Deploy backend to Cloud Run</name>
  <action>
    git add -A && \
    git commit -m "feat: deploy Phase XX changes" && \
    git push origin main
  </action>
  <verify>Cloud Build succeeds, service deployed</verify>
</task>

**Task 2:** Verify Deployment Health

<task type="checkpoint:ai-verify" gate="non-blocking">
  <url>https://attorney-dashboard-web-5paunecalq-uc.a.run.app/health</url>
  <criteria>
    <description>Health endpoint returns OK</description>
    <look-for>
      - "OK" or "healthy" status
      - No error messages
      - 200 HTTP status
    </look-for>
    <fail-if>
      - 500 or 404 error
      - "Error" message visible
    </fail-if>
  </criteria>
</task>

**Task 3:** Run Auth Flow Tests

<task type="auto">
  <name>Execute automated auth flow tests</name>
  <action>
    python .planning/testing/auth-flows.py
  </action>
  <verify>
    All auth tests pass, \
    Admin login works, \
    Role permissions correct, \
    Session persistence validated
  </verify>
</task>

**Task 4:** Visual Auth Verification

<task type="checkpoint:ai-verify" gate="non-blocking">
  <url>https://attorney-dashboard-web-5paunecalq-uc.a.run.app/login</url>
  <criteria>
    <description>Login form renders correctly after deployment</description>
    <look-for>
      - Email input field
      - Password input field
      - "Sign In" button
      - No console errors
    </look-for>
    <fail-if>
      - Blank white screen
      - Error message displayed
      - Missing form elements
    </fail-if>
  </criteria>
</task>
```

### n8n Workflow Integration

**Create n8n workflow for scheduled auth testing:**

```json
{
  "name": "Scheduled Auth Flow Tests",
  "nodes": [
    {
      "type": "n8n-nodes-base.schedule",
      "parameters": {
        "rule": {
          "interval": [{ "field": "hours", "hoursInterval": 6 }]
        }
      },
      "name": "Every 6 Hours"
    },
    {
      "type": "n8n-nodes-base.httpRequest",
      "parameters": {
        "url": "https://spectacles-383072931874.us-central1.run.app/api/skills/browser",
        "method": "POST",
        "jsonParameters": true,
        "options": {},
        "bodyParametersJson": {
          "goal": "Test Attorney Dashboard admin login",
          "start_url": "https://attorney-dashboard-web-5paunecalq-uc.a.run.app/login",
          "credentials_key": "spectacles-attorney-dashboard-prod-admin",
          "require_approval": false
        }
      },
      "name": "Test Admin Login"
    },
    {
      "type": "n8n-nodes-base.slack",
      "parameters": {
        "channel": "engineering",
        "text": "Auth flow test completed: {{ $json.status }}"
      },
      "name": "Notify Slack"
    }
  ]
}
```

---

## Troubleshooting

### Credential Access Issues

**Problem:** Spectacles can't access GCP Secret Manager

**Solution:**
```bash
# Verify service account has Secret Manager access
gcloud projects add-iam-policy-binding ousd-campaign \
  --member="serviceAccount:spectacles@ousd-campaign.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

# Test credential access
gcloud secrets versions access latest \
  --secret="spectacles-attorney-dashboard-prod-admin" \
  --project=ousd-campaign
```

### Login Flow Fails

**Problem:** Spectacles can't complete login

**Common causes:**
1. **Incorrect credentials** - Verify secret content
2. **CAPTCHA present** - Add `require_approval=True` for human CAPTCHA solving
3. **2FA enabled** - Use test account without 2FA or handle manually
4. **Rate limiting** - Space out tests, use different test accounts

**Debug:**
```python
result = await execute_task(
    goal="Log in (DEBUG MODE)",
    start_url=login_url,
    credentials_key=creds_key,
    require_approval=True  # Pause before submission for human review
)
```

### Session Persistence Fails

**Problem:** Session doesn't persist between tasks

**Cause:** Spectacles creates new browser context for each task

**Solution:** Use single task for multi-step flows:
```python
result = await execute_task(
    goal="Log in, navigate to dashboard, check settings, verify session throughout",
    start_url=login_url,
    credentials_key=creds_key,
    require_approval=False
)
```

### OAuth Callback Issues

**Problem:** OAuth callback doesn't complete

**Causes:**
1. **Callback URL mismatch** - Verify registered callback in OAuth app
2. **State parameter validation** - BetterAuth/OAuth provider issue
3. **CORS issues** - Check browser console in Browserless Live View

**Debug:**
```python
result = await execute_task(
    goal="Complete OAuth and capture final URL",
    start_url=oauth_url,
    credentials_key=oauth_creds,
    require_approval=True  # Get Live View link to inspect
)
```

---

## Summary

**Projects Analyzed:** 3 (Attorney Dashboard, Legal Research Dashboard, Glassy Platform)

**Auth Capture:** First-class interactive credential capture via CLI, API, and Python module
**Auth Flow Tests Defined:** 12 total
- Attorney Dashboard: 4 tests (admin login, attorney permissions, staff permissions, session persistence)
- Glassy Platform: 5 tests (registration, login, GitHub OAuth, organization setup, session persistence)
- Legal Research Dashboard: 3 tests (dashboard access, backend health, cases table)

**Example Test Goals:**
1. "Log into Attorney Dashboard as admin and verify dashboard loads"
2. "Complete GitHub OAuth and verify callback with authorization code"
3. "Log in as attorney and verify correct UI permissions"
4. "Navigate to Legal Research Dashboard and verify it loads without authentication"

**Verification Criteria Examples:**
- Login success: Dashboard URL redirect, no error messages, logout button visible
- OAuth completion: Callback URL matches pattern, user authenticated
- Role-based UI: Expected elements visible, forbidden elements hidden
- Session persistence: Protected page accessible without re-login after time delay

**Credential Setup:** All test accounts stored in GCP Secret Manager with naming convention `spectacles-{project}-{env}-{role}`

**Time Savings:** 10-20 min per auth test × 2-3 tests/month = 20-60 min/month per project

**Next Steps:**
1. Create test accounts for each project
2. Store credentials in GCP Secret Manager
3. Run initial auth flow tests to establish baselines
4. Integrate into deployment workflows
5. Schedule periodic auth validation (n8n or GitHub Actions)

---

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
