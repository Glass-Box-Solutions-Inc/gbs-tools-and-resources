# Spectacles Integration Guide

**For comprehensive Spectacles documentation, see:** `https://github.com/Glass-Box-Solutions-Inc/Spectacles (CLAUDE.md)`

This guide explains when and how to use Spectacles in concert with other Claude Code tools and workflows.

---

## 🤖 What is Spectacles?

**Production Service:** https://spectacles-383072931874.us-central1.run.app | **Status:** ✅ Live

Spectacles is Glass Box's production browser automation platform that combines:
- **Playwright** browser control
- **Gemini 2.5 Flash** vision AI
- **Gemini 3.0** strategic reasoning
- **Human-in-the-Loop** coordination via Slack
- **State persistence** for long-running tasks

**Key Differentiator:** Spectacles uses **hybrid DOM + Vision AI perception** (80% DOM / 20% VLM) to understand web pages like a human does - no selector maintenance required.

---

## When to Use Spectacles (MANDATORY)

**Default to Spectacles for ANY browser-related task:**

| Task Type | Use Spectacles? | Integration Pattern |
|-----------|----------------|---------------------|
| **E2E Testing** | ✅ MANDATORY | Replace Playwright with natural language tests |
| **Visual Verification** | ✅ MANDATORY | Use MCP tools in agents, `checkpoint:ai-verify` in plans |
| **Deployment Verification** | ✅ MANDATORY | Add to `cloudbuild.yaml`, integrate with CI/CD |
| **Auth Flow Testing** | ✅ MANDATORY | OAuth, SSO, 2FA with GCP Secret Manager credentials |
| **Auth State Capture** | ✅ MANDATORY | Capture browser state via CLI/API/Python for any service |
| **Data Extraction** | ✅ MANDATORY | Web scraping, report downloads, competitor intelligence |
| **Form Automation** | ✅ MANDATORY | Multi-step forms, account creation, data entry |
| **Monitoring** | ✅ MANDATORY | Health checks, critical path verification |

**Why Spectacles instead of Playwright:**
- 🧠 Vision AI finds elements (no selector maintenance)
- 💬 Natural language goals instead of code
- 🔄 Handles dynamic UIs and SPAs automatically
- 🤝 Human-in-the-loop via Slack for sensitive actions
- 💾 State persistence for long-running tasks
- 🔒 Security built-in (PII blur, audit logs, GCP Secret Manager)

---

## Integration with Claude Code Workflows

### 1. With Explore/Plan Agents

**Pattern:** Explore → Plan → Execute with Spectacles

```
1. Launch Explore agent → Understand codebase and test requirements
2. Launch Plan agent → Include Spectacles verification in PLAN.md
3. Execute plan with ai_supervision: true → Spectacles verifies automatically
```

**Example PLAN.md:**
```markdown
---
ai_supervision: true
confidence_threshold: 80
slack_channel: main
---

<task type="auto">
  <name>Deploy to Cloud Run</name>
  <action>Run gcloud run deploy, capture URL</action>
</task>

<task type="checkpoint:ai-verify" gate="non-blocking">
  <url>{{DEPLOY_URL}}</url>
  <criteria>
    <description>Dashboard loads without errors</description>
    <look-for>
      - Navigation menu visible
      - No error messages
      - Page loads successfully
    </look-for>
    <fail-if>
      - 404 or 500 error
      - Blank white screen
      - JavaScript errors
    </fail-if>
  </criteria>
</task>
```

### 2. With Testing Stack

**Pattern:** Unit → Integration → E2E (Spectacles) → Visual Regression (Spectacles)

```
1. Unit tests (Vitest, pytest) → Test individual functions
2. Integration tests (Fastify test client, FastAPI TestClient) → Test API contracts
3. E2E tests (Spectacles) → Test user flows with natural language
4. Visual regression (Spectacles) → Compare screenshots against baselines
```

**Example E2E Test:**
```javascript
// Attorney Dashboard - tests/e2e/cases.spectacles.spec.js
import { verifyWithSpectacles } from './spectacles-helper.js';

test('should display cases table', async () => {
  const result = await verifyWithSpectacles({
    goal: 'Navigate to /cases and verify cases table displays with headers',
    path: '/cases',
    credentials_key: 'attorney-dashboard-admin'
  });

  expect(result.status).toBe('completed');
  expect(result.confidence).toBeGreaterThan(80);
});
```

### 3. With CI/CD Deployment

**Pattern:** Build → Deploy → Spectacles Verify → Notify

```yaml
# cloudbuild.yaml
steps:
  # Build step
  - name: 'gcr.io/cloud-builders/docker'
    args: ['build', '-t', 'gcr.io/$PROJECT_ID/app', '.']

  # Deploy step
  - name: 'gcr.io/cloud-builders/gcloud'
    args: ['run', 'deploy', 'app', '--image', 'gcr.io/$PROJECT_ID/app']

  # Spectacles verification step
  - name: 'gcr.io/cloud-builders/curl'
    args:
      - '-X'
      - 'POST'
      - 'https://spectacles-383072931874.us-central1.run.app/api/verify'
      - '-H'
      - 'Content-Type: application/json'
      - '-d'
      - |
        {
          "url": "https://app-${_REGION}.run.app",
          "goal": "Verify dashboard loads without errors",
          "require_approval": false
        }
```

### 4. With MCP Servers

**Pattern:** n8n workflow → Spectacles task → Results back to n8n

```
1. n8n workflow triggers on schedule/webhook
2. n8n calls Spectacles REST API to start browser task
3. Spectacles executes task (Browserless + Gemini VLM)
4. Spectacles sends results back to n8n via webhook
5. n8n processes results (store in DB, send notifications, etc.)
```

**Example n8n Integration:**
```json
{
  "nodes": [
    {
      "type": "n8n-nodes-base.httpRequest",
      "name": "Start Spectacles Task",
      "parameters": {
        "url": "https://spectacles-383072931874.us-central1.run.app/api/tasks/",
        "method": "POST",
        "body": {
          "goal": "Log into MerusCase and download December report",
          "start_url": "https://app.meruscase.com/login",
          "credentials_key": "meruscase-admin",
          "webhook_url": "{{$node[\"Webhook\"].json[\"webhookUrl\"]}}"
        }
      }
    }
  ]
}
```

### 5. With Subagents

**Pattern:** Agents can use Spectacles MCP tools directly

```python
# From any agent (Explore, Plan, general-purpose, etc.)
spectacles_execute_task(
    goal="Screenshot the deployed app and verify no errors",
    start_url="https://myapp.vercel.app",
    require_approval=False
)

# Check status
spectacles_get_status(task_id="abc-123")

# Resume after human approval
spectacles_resume_task(task_id="abc-123", human_input="approved")
```

---

## Integration Methods

### Method 1: MCP Tools (Preferred for Claude Code)

**Best for:** Interactive Claude Code sessions, agent-driven automation

```python
# Available in Claude Code sessions and all agents
spectacles_execute_task(
    goal="Navigate to /login and verify form displays correctly",
    start_url="https://app.example.com",
    credentials_key="app-admin",  # From GCP Secret Manager
    require_approval=False  # True for sensitive actions
)

spectacles_get_status(task_id="abc-123")
spectacles_resume_task(task_id="abc-123", human_input="approved")
spectacles_cancel_task(task_id="abc-123")
spectacles_get_page_content(url="https://example.com")
spectacles_take_screenshot(url="https://example.com", blur_pii=True)
```

### Method 2: REST API (For Application Integration)

**Best for:** Backend services, scheduled tasks, custom integrations

```python
import httpx

SPECTACLES_URL = "https://spectacles-383072931874.us-central1.run.app"

async with httpx.AsyncClient() as client:
    # Submit task
    response = await client.post(
        f"{SPECTACLES_URL}/api/tasks/",
        json={
            "goal": "Log in and download report",
            "start_url": "https://app.example.com",
            "credentials_key": "app-admin"
        }
    )
    task = response.json()

    # Poll for completion
    while True:
        status = await client.get(f"{SPECTACLES_URL}/api/tasks/{task['task_id']}")
        if status.json()["status"] in ["completed", "failed"]:
            break
        await asyncio.sleep(2)
```

### Method 3: Skills API (Optimized for AI Agents)

**Best for:** Quick operations, optimized agent workflows

```bash
# Quick screenshot with PII blur
POST https://spectacles-383072931874.us-central1.run.app/api/skills/screenshot
{
  "url": "https://example.com",
  "full_page": true,
  "blur_pii": true
}

# Browser automation
POST https://spectacles-383072931874.us-central1.run.app/api/skills/browser
{
  "goal": "Log in and export report",
  "start_url": "https://app.example.com",
  "credentials_key": "app-admin"
}
```

### Method 4: Auth Capture (Interactive Credential Capture)

**Best for:** Capturing authenticated browser state for services without API access

Spectacles now includes a first-class auth capture system for interactively logging into any service and persisting the browser state (cookies + localStorage) locally and/or to GCP Secret Manager.

**Three access layers:**

```bash
# CLI: Interactive terminal capture
python Glass-Box-Solutions-Inc/Spectacles → `tools/capture_auth.py` --service google
python Glass-Box-Solutions-Inc/Spectacles → `tools/capture_auth.py` --service meruscase
python Glass-Box-Solutions-Inc/Spectacles → `tools/capture_auth.py` --service myapp \
    --login-url https://myapp.com/login --verify-url https://myapp.com/dashboard
```

```python
# API: Programmatic two-step flow
import httpx

SPECTACLES_URL = "https://spectacles-383072931874.us-central1.run.app"

# Step 1: Start capture session
response = await client.post(f"{SPECTACLES_URL}/api/skills/auth-capture", json={
    "service": "google",
    "credential_key": "google-auth"
})
session = response.json()
# → {"session_id": "abc-123", "live_url": "https://...", "status": "awaiting_login"}

# Step 2: After user logs in via live_url, complete capture
response = await client.post(
    f"{SPECTACLES_URL}/api/skills/auth-capture/{session['session_id']}/complete"
)
result = response.json()
# → {"cookie_count": 44, "gcp_saved": true, "verified": true}
```

```python
# Python: Direct import for scripts/tests
from security.auth_capture import AuthCaptureSession

async with AuthCaptureSession(service="google") as session:
    live_url = await session.start()
    # ... user logs in via live_url ...
    state = await session.capture()
    await session.save(local_dir=".auth", gcp_project="ousd-campaign")
    verified = await session.verify()
```

**Built-in presets:** Google, GitHub, MerusCase, Westlaw (custom URLs also supported)

**Key endpoints:**
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/skills/auth-capture` | Start capture session |
| POST | `/api/skills/auth-capture/{id}/complete` | Capture and save state |
| GET | `/api/skills/auth-capture/{id}` | Check session status |
| DELETE | `/api/skills/auth-capture/{id}` | Cancel session |

### Method 5: GSD `checkpoint:ai-verify` (For Automated Execution)

**Best for:** Plan-driven development with AI supervision

```markdown
---
ai_supervision: true
confidence_threshold: 80
slack_channel: main
---

<task type="checkpoint:ai-verify" gate="non-blocking">
  <url>http://localhost:3000</url>
  <criteria>
    <description>Dashboard renders without errors</description>
    <look-for>
      - Navigation menu visible
      - No error messages
      - Page loads successfully
    </look-for>
    <fail-if>
      - 404 or 500 error
      - Blank white screen
      - JavaScript errors visible
    </fail-if>
  </criteria>
</task>
```

**How it works:**
1. Plan includes `ai_supervision: true` frontmatter
2. Claude executes tasks, reaches `checkpoint:ai-verify`
3. Spectacles navigates to URL, captures screenshot
4. Gemini VLM analyzes against criteria
5. If confidence ≥ 80%: Auto-approve, continue execution, notify Slack
6. If confidence < 80%: Escalate to human via Slack, wait for response

---

## Environment Variables

**Required for MCP tools and API access:**

```bash
BROWSERLESS_API_TOKEN=2TcWyCwbfKt7UWCbec6a2ee3b613b579fb0edb5f7a52b0ace
GOOGLE_AI_API_KEY=AIzaSyA688aK9wL24wdF0yN9OweOU81Zbmp1y3A
```

**✅ Already set in Windows user environment variables.**

---

## Quick Commands

```bash
# Health check
curl https://spectacles-383072931874.us-central1.run.app/health

# API documentation
open https://spectacles-383072931874.us-central1.run.app/docs

# Verify deployment (reusable script)
./scripts/verify-cloud-run-deployment.sh <URL> <type>

# Types: dashboard | table | homepage | generic
./scripts/verify-cloud-run-deployment.sh https://attorney-dashboard.run.app dashboard
./scripts/verify-cloud-run-deployment.sh https://glassy.com homepage
```

---

## Real-World Integration Examples

### Example 1: Attorney Dashboard E2E Testing

**Before (Playwright - 42 skipped tests):**
```javascript
test('should display cases table', async ({ page }) => {
  if (!await isAuthenticated(page)) {
    test.skip();  // ❌ Test skipped
    return;
  }
  // Complex selector logic...
});
```

**After (Spectacles - 0 skipped tests):**
```javascript
test('should display cases table', async () => {
  const result = await verifyWithSpectacles({
    goal: 'Navigate to /cases and verify cases table displays',
    path: '/cases'
  });
  expect(result.status).toBe('completed');
});
```

### Example 2: Glassy Platform Checkpoints

**Before (Manual human-verify):**
```markdown
<task type="checkpoint:human-verify" gate="blocking">
  <what-built>New project setup complete</what-built>
  <how-to-verify>Visit http://localhost:5173 and verify page loads</how-to-verify>
  <resume-signal>Type "approved" to continue</resume-signal>
</task>
```

**After (Automated ai-verify):**
```markdown
<task type="checkpoint:ai-verify" gate="non-blocking">
  <url>http://localhost:5173</url>
  <criteria>
    <description>React Router 7 project builds and runs</description>
    <look-for>- Page loads successfully\n- No build errors</look-for>
    <fail-if>- Error page displayed</fail-if>
  </criteria>
</task>
```

### Example 3: Legal Research Dashboard Monitoring

**Pattern:** Scheduled n8n workflow + Spectacles verification

```
Schedule: Every 6 hours
1. n8n triggers Spectacles task
2. Spectacles tests Westlaw login + search functionality
3. If failures detected: PagerDuty alert
4. If success: Log to monitoring dashboard
```

---

## Best Practices

1. **Default to Spectacles** - Use for ANY browser task before considering Playwright
2. **Natural language goals** - Be specific: "Navigate to /login and verify email input field displays with placeholder text"
3. **Credentials in GCP Secret Manager** - Store test accounts securely, reference with `credentials_key`
4. **AI supervision in plans** - Add `ai_supervision: true` to plan frontmatter for automated execution
5. **Verify all deployments** - Add Spectacles verification step to every `cloudbuild.yaml`
6. **Monitor via Slack** - Watch `main` channel for verification results, escalations, and browser takeover requests
7. **Combine with agents** - Explore → Plan → Execute with Spectacles verification

---

## Documentation & Examples

| Resource | Location | Use For |
|----------|----------|---------|
| **Full Spectacles Docs** | `https://github.com/Glass-Box-Solutions-Inc/Spectacles (CLAUDE.md)` | Complete technical reference |
| **Auth Capture CLI** | `Glass-Box-Solutions-Inc/Spectacles → `tools/capture_auth.py`` | Interactive credential capture tool |
| **Auth Capture Core** | `Glass-Box-Solutions-Inc/Spectacles → `security/auth_capture.py`` | Reusable auth capture module |
| **Utilization Recommendations** | `SPECTACLES_UTILIZATION_RECOMMENDATIONS.md` | Best practices, ROI analysis |
| **Auth Flow Testing** | `SPECTACLES_AUTH_FLOW_TESTING.md` | OAuth, SSO, 2FA patterns |
| **Attorney Dashboard Migration** | `projects/attorney-dashboard/gavel/SPECTACLES_MIGRATION_GUIDE.md` | Playwright → Spectacles examples |
| **Glassy AI-Verify Conversion** | `GLASSY_AI_VERIFY_CONVERSION_REPORT.md` | GSD checkpoint examples |
| **Post-Deploy Pattern** | `docs-portal/POST_DEPLOY_VERIFICATION_PATTERN.md` | CI/CD integration template |
| **Testing Module** | `.claude/instructions/testing-visual.md` | When and how to use Spectacles |

---

## Troubleshooting

### Spectacles task stuck in "AWAITING_HUMAN"

**Cause:** Task requires human approval, waiting for Slack response

**Solution:**
1. Check Slack `main` channel for approval request
2. Click ✅ to approve or ❌ to reject
3. Or use MCP tool: `spectacles_resume_task(task_id="abc-123", human_input="approved")`

### "Credentials not found" error

**Cause:** `credentials_key` not in GCP Secret Manager

**Solution:**
```bash
# Create secret
echo -n '{"email": "test@example.com", "password": "secure-pass"}' | \
  gcloud secrets create spectacles-app-admin \
  --data-file=- \
  --project=ousd-campaign

# Test access
gcloud secrets versions access latest \
  --secret=spectacles-app-admin \
  --project=ousd-campaign
```

### Low confidence (< 80%), task escalated

**Cause:** VLM uncertain about verification criteria

**Solution:**
1. Check screenshot in Slack for visual issues
2. Refine `<look-for>` criteria to be more specific
3. Adjust `confidence_threshold` in plan frontmatter (70-90 range)

---

**Remember: Spectacles is a production service, always available. Use it liberally for any browser-related work.**

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
