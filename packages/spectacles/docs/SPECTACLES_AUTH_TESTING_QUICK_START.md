# Spectacles Auth Testing - Quick Start

**Fast track to automated authentication testing with Spectacles**

---

## 5-Minute Setup

### 1. Create a test account (1 min)

**Attorney Dashboard:**
```
Email: test-admin@glassboxsolutions.com
Password: SecureTestPass123!
Role: Admin
```

**Glassy Platform:**
```
Email: test-user@glassboxsolutions.com
Password: SecureTestPass123!
Username: glassytest
```

### 2. Store in GCP Secret Manager (2 min)

```bash
# Attorney Dashboard admin account
echo -n '{"email":"test-admin@glassboxsolutions.com","password":"SecureTestPass123!"}' | \
gcloud secrets create spectacles-attorney-dashboard-prod-admin \
  --data-file=- --project=ousd-campaign --replication-policy=automatic

# Glassy test account
echo -n '{"email":"test-user@glassboxsolutions.com","password":"SecureTestPass123!","username":"glassytest"}' | \
gcloud secrets create spectacles-glassy-prod-testuser \
  --data-file=- --project=ousd-campaign --replication-policy=automatic
```

### 3. Run your first test (2 min)

**Test Attorney Dashboard login:**

```python
from spectacles import execute_task

result = await execute_task(
    goal="Log into Attorney Dashboard and verify it loads",
    start_url="https://attorney-dashboard-web-5paunecalq-uc.a.run.app/login",
    credentials_key="spectacles-attorney-dashboard-prod-admin",
    require_approval=False
)

print(f"Status: {result['status']}")
print(f"Screenshot: {result.get('screenshot_url')}")
```

**Test Glassy login:**

```python
result = await execute_task(
    goal="Log into Glassy and verify dashboard loads",
    start_url="https://glassy.glassboxsolutions.com/login",
    credentials_key="spectacles-glassy-prod-testuser",
    require_approval=False
)

print(f"Status: {result['status']}")
```

---

## Copy-Paste Test Scripts

### Attorney Dashboard Admin Login

```python
import asyncio
from spectacles import execute_task

async def test_admin_login():
    result = await execute_task(
        goal="Log into Attorney Dashboard as admin and verify dashboard loads",
        start_url="https://attorney-dashboard-web-5paunecalq-uc.a.run.app/login",
        credentials_key="spectacles-attorney-dashboard-prod-admin",
        require_approval=False
    )

    obs = result["final_observation"].lower()
    passed = "dashboard" in obs or "cases" in obs

    print(f"✅ PASS" if passed else "❌ FAIL")
    print(f"Screenshot: {result.get('screenshot_url')}")
    return passed

asyncio.run(test_admin_login())
```

### Glassy GitHub OAuth

```python
import asyncio
from spectacles import execute_task

async def test_github_oauth():
    result = await execute_task(
        goal="Complete GitHub OAuth login and verify callback",
        start_url="https://glassy.glassboxsolutions.com/auth/github",
        credentials_key="spectacles-glassy-github-oauth",
        require_approval=False
    )

    final_url = result.get("final_url", "")
    passed = "glassy.glassboxsolutions.com" in final_url

    print(f"✅ PASS" if passed else "❌ FAIL")
    print(f"Final URL: {final_url}")
    return passed

asyncio.run(test_github_oauth())
```

### Legal Research Dashboard Access

```python
import asyncio
from spectacles import execute_task

async def test_dashboard_access():
    result = await execute_task(
        goal="Navigate to Legal Research Dashboard and verify it loads",
        start_url="https://legal-research-dashboard-816980776764.us-central1.run.app",
        credentials_key=None,  # No auth required
        require_approval=False
    )

    obs = result["final_observation"].lower()
    passed = "legal research" in obs or "cases" in obs

    print(f"✅ PASS" if passed else "❌ FAIL")
    print(f"Screenshot: {result.get('screenshot_url')}")
    return passed

asyncio.run(test_dashboard_access())
```

---

## Add to Deployment Plan

**In your PLAN.md:**

```markdown
**Task X:** Run Auth Tests

<task type="auto">
  <name>Execute automated auth flow tests</name>
  <action>python .planning/testing/auth-flows.py</action>
  <verify>All auth tests pass</verify>
</task>
```

---

## Common Patterns

### Simple Login
```python
result = await execute_task(
    goal="Log in and verify success",
    start_url=LOGIN_URL,
    credentials_key="your-secret-name",
    require_approval=False
)
```

### OAuth Flow
```python
result = await execute_task(
    goal="Complete OAuth and verify callback",
    start_url=OAUTH_URL,
    credentials_key="oauth-account-secret",
    require_approval=False
)
```

### Role-Based UI Check
```python
# Login then check what's visible
result = await execute_task(
    goal="Log in as {role} and verify correct UI permissions",
    start_url=LOGIN_URL,
    credentials_key=f"your-{role}-secret",
    require_approval=False
)

# Verify expected elements present, forbidden elements absent
obs = result["final_observation"].lower()
assert "admin panel" in obs if role == "admin"
assert "admin panel" not in obs if role != "admin"
```

---

## Troubleshooting

**Test fails immediately:**
- Check credential exists: `gcloud secrets describe spectacles-{name} --project=ousd-campaign`
- Verify JSON format: `gcloud secrets versions access latest --secret=spectacles-{name}`

**Login doesn't complete:**
- Add `require_approval=True` to pause and get Live View link
- Check for CAPTCHA (will need manual solving)
- Verify test account credentials are correct

**Session doesn't persist:**
- Use single task for multi-step flows instead of separate tasks
- Spectacles creates fresh browser context per task

**OAuth callback fails:**
- Verify callback URL registered in OAuth app settings
- Check for CORS errors in browser console (use Live View)

---

## Auth State Capture (New)

For services that require manual login (Westlaw, MerusCase, etc.), use the **Auth Capture** feature to capture and persist browser state:

### CLI Tool

```bash
# Capture Google auth state interactively
python projects/spectacles/tools/capture_auth.py --service google

# Capture with custom service
python projects/spectacles/tools/capture_auth.py --service westlaw \
    --login-url https://1.next.westlaw.com/ \
    --verify-url https://1.next.westlaw.com/

# Available presets: google, github, meruscase, westlaw
python projects/spectacles/tools/capture_auth.py  # Interactive menu
```

### API

```bash
# Start auth capture session
curl -X POST https://spectacles-383072931874.us-central1.run.app/api/skills/auth-capture \
  -H "Content-Type: application/json" \
  -d '{"service": "google"}'
# Returns: {"session_id": "abc-123", "live_url": "https://...", "status": "awaiting_login"}

# After logging in via live_url, complete the capture
curl -X POST https://spectacles-383072931874.us-central1.run.app/api/skills/auth-capture/abc-123/complete
# Returns: {"cookie_count": 44, "gcp_saved": true, "verified": true}
```

### Python

```python
from security.auth_capture import AuthCaptureSession

async with AuthCaptureSession(service="meruscase") as session:
    live_url = await session.start()
    print(f"Log in at: {live_url}")
    input("Press Enter after login...")
    state = await session.capture()
    results = await session.save(local_dir=".auth", gcp_project="ousd-campaign")
    print(f"Saved {results['cookie_count']} cookies")
```

---

## Full Documentation

- **Complete Guide:** `SPECTACLES_AUTH_FLOW_TESTING.md`
- **Auth Capture Core:** `projects/spectacles/security/auth_capture.py`
- **Auth Capture CLI:** `projects/spectacles/tools/capture_auth.py`
- **Implementation Status:** `SPECTACLES_RECOMMENDATION_E_IMPLEMENTATION.md`
- **Spectacles Docs:** `projects/spectacles/CLAUDE.md`

---

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
