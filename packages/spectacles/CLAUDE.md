# Spectacles - CLAUDE.md

**AI-Powered Browser Automation Platform**

Spectacles is a production-grade browser automation platform that combines Playwright browser control, Gemini 2.5 Flash vision AI, Gemini 3.0 strategic reasoning, and human-in-the-loop coordination to deliver intelligent, reliable web automation for any application.

---

## What is Spectacles?

Spectacles is a general-purpose browser automation service that provides intelligent, autonomous web interaction capabilities with built-in visual perception and human oversight. Unlike traditional automation tools, Spectacles uses hybrid DOM + Vision AI perception to understand web pages like a human does, enabling it to handle dynamic UIs, SPAs, and complex workflows that break traditional selectors.

**Key Differentiators:**
- **Hybrid Perception**: 80% DOM-based (fast) + 20% Vision AI (handles edge cases)
- **Natural Language Goals**: "Log into MerusCase and download the December billing report"
- **Human-in-the-Loop**: Slack integration for approvals, uncertainty handling, browser takeover
- **State Persistence**: Checkpoint/resume for long-running tasks spanning hours or days
- **Production-Ready**: Live service on GCP Cloud Run, available to all Glass Box projects

---

## Production Service

**Spectacles is a LIVE SERVICE** - always running and available for integration.

| Property | Value |
|----------|-------|
| **URL (glassbox-spectacles)** | https://spectacles-gc2qovgs7q-uc.a.run.app |
| **URL (legacy — ousd-campaign)** | https://spectacles-378330630438.us-central1.run.app ⚠️ *migrate away* |
| **Health Check** | https://spectacles-gc2qovgs7q-uc.a.run.app/health |
| **API Docs** | https://spectacles-gc2qovgs7q-uc.a.run.app/docs |
| **Project** | `glassbox-spectacles` (GCP) |
| **Region** | us-central1 |
| **Browser Provider** | Browserless.io (PAID account) |
| **Status** | Production |

> ⚠️ **Infra Mismatch:** Spectacles is deployed in both `glassbox-spectacles` (correct) and `ousd-campaign` (personal — retire this). Update all callers to use the `glassbox-spectacles` URL. The main Desktop CLAUDE.md screenshot command still references the legacy URL.

---

## Use Cases

### Automated Testing & QA
**Visual regression testing, functional testing, cross-browser verification**

```python
# Test login flow across multiple scenarios
result = await spectacles.execute_task(
    goal="Test login with valid credentials, invalid password, and password reset flow",
    start_url="https://app.example.com/login",
    require_approval=False  # Automated test, no human needed
)
```

**Perfect for:**
- End-to-end testing of user flows
- Visual regression detection
- Cross-browser compatibility testing
- Accessibility verification
- Performance benchmarking

### Data Extraction & Web Scraping
**Intelligent data collection from dynamic websites**

```python
# Extract structured data from JavaScript-heavy sites
result = await spectacles.execute_task(
    goal="Navigate to competitor pricing page and extract all product prices",
    start_url="https://competitor.com/pricing",
    require_approval=False
)
```

**Perfect for:**
- Competitive intelligence gathering
- Market research automation
- Content aggregation
- Price monitoring
- Lead generation

### Form Automation & Data Entry
**Fill complex multi-step forms with validation handling**

```python
# Complete multi-page form with file uploads
result = await spectacles.execute_task(
    goal="Fill out the contact form with company details and submit",
    start_url="https://vendor.com/contact",
    credentials_key="company-info",
    require_approval=True  # Sensitive action
)
```

**Perfect for:**
- Bulk form submissions
- Account creation/registration
- Data migration between systems
- Report submission automation
- Application processing

### Authentication Testing
**Test OAuth flows, SSO, 2FA, and complex auth scenarios**

```python
# Test GitHub OAuth integration
result = await spectacles.execute_task(
    goal="Complete GitHub OAuth and verify callback with authorization code",
    start_url="https://github.com/login/oauth/authorize?client_id=...",
    credentials_key="github_test_user",
    require_approval=False
)
```

**Perfect for:**
- OAuth flow validation
- SSO integration testing
- 2FA workflow verification
- Session management testing
- Security audit automation

### Auth Capture (Interactive Credential Capture)
**Capture and persist authenticated browser state for any service**

```python
# CLI: One-command auth capture for any service
# python tools/capture_auth.py --service google

# API: Start a capture session programmatically
POST /api/skills/auth-capture
{"service": "google", "credential_key": "google-auth"}
# Returns: {"session_id": "abc-123", "live_url": "https://..."}

# Python: Direct usage in scripts
from security.auth_capture import AuthCaptureSession
async with AuthCaptureSession(service="google") as session:
    live_url = await session.start()
    # User logs in via live_url...
    state = await session.capture()
    await session.save(local_dir=".auth", gcp_project="glassbox-spectacles")
```

**Perfect for:**
- Capturing login state for services without API access (Westlaw, MerusCase)
- Pre-authenticating Browserless sessions for automated tests
- Refreshing expired auth state across environments
- Onboarding new services with OAuth/SSO/2FA flows
- Built-in presets: Google, GitHub, MerusCase, Westlaw (extensible)

### Website Monitoring & Health Checks
**Continuous monitoring with visual and functional verification**

```python
# Monitor critical user journey
result = await spectacles.execute_task(
    goal="Check that the checkout flow completes without errors",
    start_url="https://shop.example.com",
    require_approval=False
)
```

**Perfect for:**
- Production health monitoring
- Critical path verification
- Uptime verification beyond simple pings
- User journey validation
- Error detection and alerting

### Integration with Other Applications

#### Glassy Platform Integration
```python
# From Glassy backend - delegate browser tasks to Spectacles
import httpx

SPECTACLES_URL = "https://spectacles-gc2qovgs7q-uc.a.run.app"

async def verify_deployment(url: str):
    """Verify a deployment visually after CI/CD"""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{SPECTACLES_URL}/api/tasks/",
            json={
                "goal": "Screenshot the dashboard and verify no error messages",
                "start_url": url,
                "require_approval": False
            }
        )
        return response.json()
```

#### Legal Research Dashboard
```python
# Verify Westlaw/Lexis login still works
async def test_legal_research_login():
    result = await spectacles.execute_task(
        goal="Test Westlaw login and verify search functionality",
        start_url="https://1.next.westlaw.com/",
        credentials_key="westlaw-test-account",
        require_approval=False
    )
```

#### MerusCase Integration
```python
# Automate report downloads from MerusCase
async def download_meruscase_report(report_type: str, month: str):
    result = await spectacles.execute_task(
        goal=f"Log into MerusCase and download {report_type} report for {month}",
        start_url="https://app.meruscase.com/login",
        credentials_key="meruscase-admin",
        require_approval=True  # Financial data - get approval
    )
```

### GSD Workflow Integration
**One of many use cases - automated visual verification in development workflows**

```python
# During phase execution, verify UI changes
result = await spectacles.execute_task(
    goal="Screenshot the new dark mode toggle and verify it renders correctly",
    start_url="http://localhost:3000?feature=dark-mode",
    require_approval=False  # Automated verification
)
```

**Used for:**
- Visual checkpoints in plan execution
- Deployment verification
- Feature flag testing
- Responsive layout validation

---

## Integration Methods

### REST API (Recommended)
**Direct HTTP API for maximum flexibility**

```python
import httpx

SPECTACLES_URL = "https://spectacles-gc2qovgs7q-uc.a.run.app"

async def automate_task(goal: str, url: str):
    async with httpx.AsyncClient() as client:
        # Submit task
        response = await client.post(
            f"{SPECTACLES_URL}/api/tasks/",
            json={
                "goal": goal,
                "start_url": url,
                "require_approval": True
            }
        )
        task = response.json()

        # Poll for completion
        while True:
            status = await client.get(f"{SPECTACLES_URL}/api/tasks/{task['task_id']}")
            if status.json()["status"] in ["completed", "failed"]:
                return status.json()
            await asyncio.sleep(2)
```

**Endpoints:**
- `POST /api/tasks/` - Submit automation task
- `GET /api/tasks/{id}` - Get task status
- `POST /api/tasks/{id}/resume` - Resume after HITL
- `POST /api/tasks/{id}/cancel` - Cancel task
- `GET /api/tasks/{id}/actions` - Get action history

### Skills API (Optimized for AI Agents)
**Task-specific endpoints for common automation patterns**

```python
# Browser automation
POST /api/skills/browser
{
  "goal": "Log into app and export report",
  "start_url": "https://app.example.com",
  "require_approval": true,
  "credentials_key": "app-admin"
}

# Quick screenshot
POST /api/skills/screenshot
{
  "url": "https://example.com",
  "mode": "browser",
  "full_page": true,
  "blur_pii": true
}

# Desktop automation (VM deployments only)
POST /api/skills/desktop
{
  "goal": "Open Excel and export as PDF",
  "app_name": "Microsoft Excel",
  "require_approval": true
}

# File operations (sandboxed)
POST /api/skills/file
{
  "operation": "read",
  "path": "/tmp/spectacles/report.csv"
}
```

**Features:**
- Optimized request/response formats
- Built-in capability detection
- Webhook callbacks for async completion
- PII blurring for screenshots
- Audit logging

### MCP Server (AI Agent Integration)
**For Claude Code and other AI agents**

```python
# From Claude Code or other AI agents
spectacles_execute_task(
    goal="Take screenshot of the dashboard after deployment",
    start_url="https://myapp.vercel.app",
    credentials_key=None,
    require_approval=False
)

spectacles_get_status(task_id="abc-123")

spectacles_resume_task(task_id="abc-123", human_input="approved")
```

**MCP Tools:**
- `spectacles_execute_task` - Start browser automation
- `spectacles_get_status` - Check task status
- `spectacles_resume_task` - Resume paused task

### Direct Python Import
**For applications running on same infrastructure**

```python
from core.orchestrator import Orchestrator
from api.config import Settings

settings = Settings()
orchestrator = Orchestrator(settings)

# Submit and execute task
task_id = await orchestrator.submit_task(
    goal="Log in and download report",
    start_url="https://app.example.com",
    credentials_key="app-admin"
)

result = await orchestrator.execute_task(task_id)
```

---

## Architecture

### System Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                         SPECTACLES                                │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌─────────────┐      ┌──────────────┐      ┌───────────────┐   │
│  │  REST API   │      │ Skills API   │      │  MCP Server   │   │
│  │  (FastAPI)  │      │ (Optimized)  │      │  (AI Agents)  │   │
│  └──────┬──────┘      └──────┬───────┘      └───────┬───────┘   │
│         │                    │                      │            │
│         └────────────────────┼──────────────────────┘            │
│                              │                                   │
│                    ┌─────────▼─────────┐                         │
│                    │   ORCHESTRATOR    │                         │
│                    │  (Task Planning)  │                         │
│                    └─────────┬─────────┘                         │
│                              │                                   │
│              ┌───────────────┼───────────────┐                   │
│              │               │               │                   │
│     ┌────────▼────────┐  ┌──▼──────────┐  ┌─▼──────────────┐    │
│     │    BROWSER      │  │   DESKTOP   │  │  FILE SYSTEM   │    │
│     │   SPECIALIST    │  │  SPECIALIST │  │   SPECIALIST   │    │
│     └────────┬────────┘  └──┬──────────┘  └─┬──────────────┘    │
│              │              │               │                   │
│     ┌────────▼────────┐  ┌──▼──────────┐  ┌─▼──────────────┐    │
│     │   PERCEPTION    │  │  PERCEPTION │  │   SANDBOXED    │    │
│     │  DOM (80%) +    │  │   Vision +  │  │  FILE ACCESS   │    │
│     │  VLM (20%)      │  │  PyAutoGUI  │  │                │    │
│     └─────────────────┘  └─────────────┘  └────────────────┘    │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              HUMAN-IN-THE-LOOP (HITL)                     │   │
│  │  - Slack Webhooks (one-way notifications)                 │   │
│  │  - Slack Bolt (interactive buttons, browser takeover)     │   │
│  │  - Approval workflow for sensitive actions                │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                  STATE MANAGEMENT                          │   │
│  │  - SQLite/PostgreSQL persistence                           │   │
│  │  - Checkpoint/resume for long-running tasks                │   │
│  │  - Pinecone vector DB for long-term memory                 │   │
│  │  - Audit logging (SOC2/HIPAA compliant)                    │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                   SECURITY LAYER                           │   │
│  │  - GCP Secret Manager for credentials                      │   │
│  │  - PII detection and blurring                              │   │
│  │  - Session encryption                                      │   │
│  │  - Sandboxed execution                                     │   │
│  └──────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
           │                      │                      │
           ▼                      ▼                      ▼
   ┌──────────────┐      ┌──────────────┐      ┌──────────────┐
   │ Browserless  │      │ Gemini 2.0   │      │     Slack    │
   │  (Browser)   │      │ Flash (VLM)  │      │  (Webhooks)  │
   └──────────────┘      └──────────────┘      └──────────────┘
```

### State Machine

All tasks flow through a deterministic state machine:

```
┌──────────┐
│ PLANNING │  Analyze goal, create action plan
└────┬─────┘
     │
     ▼
┌────────────┐
│ NAVIGATING │  Navigate to target URL
└─────┬──────┘
      │
      ▼
┌────────────┐
│ OBSERVING  │◄─┐  Perceive page state (DOM or Vision)
└─────┬──────┘  │
      │         │
      ▼         │
┌────────────┐  │
│   ACTING   │──┘  Execute browser action
└─────┬──────┘
      │
      ▼
┌──────────────┐
│  EVALUATING  │  Check if goal achieved
└──────┬───────┘
       │
       ├─────► ┌────────────────┐
       │       │   COMPLETED    │  Task finished successfully
       │       └────────────────┘
       │
       ├─────► ┌──────────────────┐
       │       │ AWAITING_HUMAN   │  Paused for Slack approval
       │       └──────────────────┘
       │
       └─────► ┌──────────────────┐
               │ ERROR_RECOVERY   │  Handle failures, retry logic
               └──────────────────┘
```

**Key Features:**
- **Checkpoint/Resume**: Tasks can pause at AWAITING_HUMAN and resume hours later
- **Error Recovery**: Automatic retry with exponential backoff
- **State Persistence**: All state saved to database for crash recovery

---

## Core Capabilities

### Browser Automation
**Powered by Playwright + Browserless.io**

- Navigate websites, click buttons, fill forms
- Handle multi-step workflows (login → navigate → extract data)
- Take screenshots and extract page content
- Handle OAuth flows and complex authentication
- Wait for dynamic content and AJAX requests
- Keyboard shortcuts, hover actions, drag-and-drop
- File uploads and downloads
- Multi-page workflows with session persistence

### Visual Perception
**Hybrid DOM + Gemini 2.5 Flash Vision AI**

- **80% DOM-based**: Fast element finding via selectors, XPath, text content
- **20% Vision AI**: Fallback for complex cases (canvas elements, dynamic UIs, SVGs)
- Understands page layout and visual hierarchy
- Handles dynamic UIs, SPAs, and JavaScript-heavy sites
- Can find elements by visual description ("the blue submit button")
- Screenshot analysis for verification and debugging

### Human-in-the-Loop (HITL)
**Slack integration for approvals and oversight**

- **Approval Workflow**: Request human approval before sensitive actions
- **Low-Confidence Escalation**: Ask human when AI is uncertain
- **Browser Takeover**: Get Browserless Live View URL to control browser manually
- **Slack Webhooks**: One-way notifications (primary mode)
- **Slack Bolt**: Interactive buttons and bidirectional communication (optional)
- **Multi-Channel**: Route notifications to different channels (main, alex, brian, social)

### State Management
**Persistence for long-running and complex workflows**

- **Checkpoint/Resume**: Pause tasks, resume hours/days later
- **Session Encryption**: Secure credential storage with Fernet
- **Vector Memory**: Pinecone for long-term context and learning
- **Audit Logging**: All actions logged for compliance (SOC2/HIPAA)
- **Database**: SQLite (local dev) / PostgreSQL (production)

### Desktop Automation (VM Deployments)
**Optional: PyAutoGUI + mss for native app control**

- Open applications (Excel, Word, etc.)
- Click, type, drag UI elements
- OCR-based element finding
- Screenshot capture and visual verification
- Only available on VM deployments with display access

### File Operations (Sandboxed)
**Secure file system access**

- Read, write, list, copy, move, delete files
- Sandboxed to allowed paths only
- Audit logging for all operations
- HIPAA-compliant PII handling

### Auth Capture (First-Class Capability)
**Interactive credential capture for any service**

- Open live Browserless session for manual login to any service
- Capture cookies + localStorage after authentication completes
- Save state locally and/or to GCP Secret Manager
- Verify authentication by navigating to protected URL after capture
- Built-in presets for Google, GitHub, MerusCase, Westlaw
- Custom service support with arbitrary login/verify URLs
- Available via **CLI tool**, **Skills API**, and **core Python module**
- Enables pre-authenticated browser sessions across environments

**Three access layers:**
- **CLI**: `python tools/capture_auth.py --service google`
- **API**: `POST /api/skills/auth-capture` → complete via `POST /api/skills/auth-capture/{id}/complete`
- **Python**: `async with AuthCaptureSession(service="google") as session: ...`

---

## API Endpoints

### Core Task API

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Service info and version |
| GET | `/health` | Health check endpoint |
| GET | `/docs` | OpenAPI documentation |
| POST | `/api/tasks/` | Submit automation task |
| GET | `/api/tasks/{id}` | Get task status and results |
| POST | `/api/tasks/{id}/resume` | Resume after HITL pause |
| POST | `/api/tasks/{id}/cancel` | Cancel running task |
| GET | `/api/tasks/{id}/actions` | Get action history |

### Skills API (AI Agent Optimized)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/skills/capabilities` | Get available capabilities |
| POST | `/api/skills/browser` | Submit browser task (optimized) |
| POST | `/api/skills/screenshot` | Take screenshot with PII blur |
| POST | `/api/skills/desktop` | Desktop automation (VM only) |
| POST | `/api/skills/file` | File operations (sandboxed) |
| POST | `/api/skills/callback` | Receive async callbacks |
| POST | `/api/skills/auth-capture` | Start auth capture session |
| POST | `/api/skills/auth-capture/{id}/complete` | Complete capture and save |
| GET | `/api/skills/auth-capture/{id}` | Check auth capture status |
| DELETE | `/api/skills/auth-capture/{id}` | Cancel auth capture session |

### Webhooks

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/webhooks/slack/interactions` | Slack button callbacks |

---

## Quick Reference

| Item | Value |
|------|-------|
| **Status** | Production (Live) |
| **Stack** | Python 3.12, FastAPI, Playwright, Browserless, Slack, Gemini 2.5 Flash (vision), Gemini 3.0 (reasoning) |
| **Entry Point** | `api/main.py` |
| **Database** | SQLite (local) / PostgreSQL (production) |
| **Deployment** | GCP Cloud Run |
| **Browser** | Browserless.io (paid account) |
| **Vision** | Gemini 2.5 Flash |
| **Reasoning** | Gemini 3.0 |
| **Memory** | Pinecone vector DB |

---

## Commands

```bash
# Setup
pip install -r requirements.txt
playwright install chromium

# Development
uvicorn api.main:app --reload --port 8080

# Test components
python -m pytest tests/

# Docker build
docker build -t spectacles .
docker run -p 8080:8080 --env-file .env spectacles

# Deploy to Cloud Run
gcloud run deploy spectacles \
  --source . \
  --region us-central1 \
  --project glassbox-spectacles
```

---

## Directory Structure

```
spectacles/
├── api/                  # FastAPI application
│   ├── main.py           # App entry point
│   ├── config.py         # Pydantic Settings
│   └── routes/           # API endpoints
│       ├── tasks.py      # Core task API
│       ├── skills.py     # Skills API
│       ├── webhooks.py   # Slack webhooks
│       └── health.py     # Health checks
├── core/                 # Agent logic
│   ├── orchestrator.py   # Task planning & delegation
│   ├── browser_specialist.py  # Browser execution
│   ├── desktop_specialist.py  # Desktop automation
│   ├── file_specialist.py     # File operations
│   ├── state_machine.py  # State management
│   └── perception/       # DOM + VLM perception
├── browser/              # Browser automation
│   ├── client.py         # Browserless CDP client
│   └── element_handler.py # Element location
├── desktop/              # Desktop automation (VM only)
│   ├── perceiver.py      # OCR + visual perception
│   └── controller.py     # PyAutoGUI control
├── hitl/                 # Human-in-the-loop
│   ├── webhook_client.py # Webhook-based Slack (primary)
│   ├── slack_client.py   # Slack Bolt integration (optional)
│   └── message_builder.py # Block Kit messages
├── memory/               # Short & long-term memory
│   ├── vector_store.py   # Pinecone integration
│   └── context.py        # Context management
├── persistence/          # SQLite/PostgreSQL storage
│   ├── models.py         # Data models
│   └── store.py          # Task storage
├── security/             # Security layer
│   ├── secrets_vault.py  # GCP Secret Manager
│   ├── auth_capture.py   # Auth capture core module
│   ├── pii_blur.py       # PII detection & blur
│   └── audit_log.py      # Compliance logging
├── tools/                # CLI tools
│   └── capture_auth.py   # Auth capture CLI
└── mcp/                  # MCP server for agents
    └── server.py         # MCP protocol implementation
```

---

## Configuration

Environment variables (`.env`):

| Variable | Required | Description |
|----------|----------|-------------|
| `BROWSERLESS_API_TOKEN` | Yes | Browserless API token |
| `GOOGLE_AI_API_KEY` | Yes | Gemini API key (used for 2.5 Flash vision + 3.0 reasoning) |
| `GCP_PROJECT_ID` | Yes | GCP project for Secret Manager |
| `SLACK_WEBHOOK_MAIN` | Recommended | Main channel webhook |
| `SLACK_WEBHOOK_ALEX` | Optional | Alex's direct webhook |
| `SLACK_WEBHOOK_BRIAN` | Optional | Brian's direct webhook |
| `SLACK_WEBHOOK_SOCIAL` | Optional | Social channel webhook |
| `SLACK_APP_TOKEN` | Optional | Slack app token (Socket Mode) |
| `PINECONE_API_KEY` | Optional | Pinecone for long-term memory |
| `PINECONE_INDEX` | Optional | Pinecone index name |

**See `.env.example` for full configuration options.**

---

## Slack Integration

### Webhooks (Adjudica Workspace)

| Name | Channel | GCP Secret | Use Case |
|------|---------|------------|----------|
| `main` | Main channel | `slack-webhook-main` | Default approvals |
| `alex` | Alex DM | `slack-webhook-alex` | Alex-specific notifications |
| `brian` | Brian DM | `slack-webhook-brian` | Brian-specific notifications |
| `social` | Social channel | `slack-webhook-social` | Social media automation |

### Usage

```python
from hitl.webhook_client import create_webhook_client_from_env

client = create_webhook_client_from_env()

# Send approval request (default webhook)
await client.request_approval(
    task_id="task-123",
    action_description="Click the submit button on payment form",
    screenshot_url="https://...",
    context={"url": "https://example.com/checkout"}
)

# Send to specific webhook
await client.send_notification(
    "Task completed successfully",
    task_id="task-123",
    level="success",
    webhook_name="alex"  # Route to Alex's webhook
)

# Send browser control link
await client.send_tunnel_link(
    task_id="task-123",
    tunnel_url="https://production-sfo.browserless.io/live/..."
)
```

### Response Handling

Webhooks are one-way. Users respond via:
- **Emoji reactions**: ✅ (approve) or ❌ (reject)
- **Thread replies**: "approved" or "rejected"

---

## Security Features

### Secrets Management
**Credentials never touch LLM context**

- All credentials stored in GCP Secret Manager
- Credentials only accessed at execution time by action executor
- Never logged, never in screenshots, never in AI prompts

### PII Protection
**HIPAA-compliant data handling**

- Automatic PII detection in screenshots
- Credit card numbers, SSN, phone numbers blurred
- Configurable PII patterns
- Audit trail for compliance

### Audit Logging
**SOC2-compliant activity tracking**

- All actions logged with timestamps
- User attribution for HITL interactions
- Security events tracked separately
- Exportable for compliance reporting

### Session Encryption
**Secure browser session storage**

- Fernet encryption for session data
- Separate encryption keys per environment
- Automatic key rotation support

---

## GitHub OAuth Integration

Spectacles can automate GitHub OAuth flows for testing. Credentials shared across all Glass Box projects.

**Credential Location:** GCP Secret Manager (`glassbox-spectacles` project)
- `spectacles-github-client-id`
- `spectacles-github-client-secret`

**Registered Callback URL:**
```
https://spectacles-378330630438.us-central1.run.app/auth/github/callback
```

**Example Usage:**
```python
result = await spectacles.execute_task(
    goal="Complete GitHub OAuth and extract authorization code",
    start_url="https://github.com/login/oauth/authorize?client_id=...",
    credentials_key="github_test_user"
)
```

---

## Example Integrations

### Test Automation (Playwright Alternative)

```python
# Instead of writing Playwright test scripts
# Use natural language with Spectacles

async def test_checkout_flow():
    result = await spectacles.execute_task(
        goal="Add item to cart, proceed to checkout, verify total is correct",
        start_url="https://shop.example.com/products/widget",
        require_approval=False
    )

    assert result["status"] == "completed"
    assert "total: $49.99" in result["final_observation"]
```

### Data Pipeline Integration

```python
# Scrape data as part of data pipeline

async def collect_competitor_prices():
    result = await spectacles.execute_task(
        goal="Navigate to pricing page and extract all product prices",
        start_url="https://competitor.com/pricing",
        require_approval=False
    )

    prices = parse_prices(result["final_observation"])
    await save_to_database(prices)
```

### CI/CD Deployment Verification

```python
# In GitHub Actions or CI/CD pipeline

async def verify_deployment(deploy_url: str):
    result = await spectacles.execute_task(
        goal="Screenshot homepage and verify no error messages visible",
        start_url=deploy_url,
        require_approval=False
    )

    if "error" in result["final_observation"].lower():
        raise Exception("Deployment verification failed")
```

### Monitoring & Alerting

```python
# Periodic health check with visual verification

async def monitor_critical_path():
    result = await spectacles.execute_task(
        goal="Test full user journey: login → dashboard → create item",
        start_url="https://app.example.com",
        credentials_key="monitoring-account",
        require_approval=False
    )

    if result["status"] == "failed":
        await send_pagerduty_alert(result["error"])
```

---

## Trigger Table

When working in this project, these keywords load additional context:

| Keyword | Resources | Context |
|---------|-----------|---------|
| `api` | `**/API*.md`, `glassy-infra/docs/subsystems/BACKEND_GUIDE.md` | Global |
| `fastapi` | `glassy-infra/docs/subsystems/BACKEND_GUIDE.md`, `projects/wc-paralegal-agent/CLAUDE.md` | Global |

*Auto-generated by Squeegee. Edit squeegee.config.json to customize.*

---

## Related Documentation

- `README.md` - Full technical documentation
- `VariableForClMD.md` - Current session state
- `BIDIRECTIONAL_SLACK.md` - Slack Bolt integration guide
- `SLACK_SETUP.md` - Slack workspace setup
- `/tmp/GITHUB_OAUTH_INTEGRATION.md` - GitHub OAuth integration guide
- `../slack-integration/CLAUDE.md` - Shared Slack patterns
- `../merus-expert/CLAUDE.md` - Browser automation patterns
- `../glassbox-spectacles-platform/CLAUDE.md` - FastAPI patterns

---

For company-wide development standards, see the main CLAUDE.md at ~/Desktop/CLAUDE.md.

For centralized business, legal, marketing, and product documentation, see the [Adjudica Documentation Hub](~/Desktop/adjudica-documentation/CLAUDE.md) and the [Quick Index](~/Desktop/adjudica-documentation/ADJUDICA_INDEX.md).

---


---

## Context & Team Management

**CRITICAL**: This project follows Glass Box Solutions' Context & Team Management philosophy.

### Key Rules
- **65% Context Threshold**: When any agent reaches 65% context, initiate handoff protocol
- **Team Approach**: Tasks requiring >50% context use PM + Specialist teams
- **Plan First**: All tasks begin with planning phase

### Quick Reference
- **Main philosophy**: `~/Desktop/CLAUDE.md` - Critical Rules #8 + Context & Team Management Philosophy section
- **Comprehensive guide**: `~/Desktop/adjudica-documentation/engineering/CONTEXT_AND_TEAM_MANAGEMENT.md`
- **Development process**: `~/Desktop/adjudica-documentation/engineering/DEVELOPMENT_PROCESS.md`

### When to Use Teams
- <30% context → Solo agent
- 30-50% context → Solo with plan
- **50-70% context → PM + 1 Specialist**
- **70-90% context → PM + Multiple Specialists**
- 90%+ context → Break into multiple plans OR large team

### PM Handoff (when PM reaches 65%)
```bash
# PM creates structured handoff
cp ~/Desktop/adjudica-documentation/engineering/templates/PM_HANDOFF_TEMPLATE.md \
   .planning/handoffs/PM_HANDOFF_$(date -Iseconds).md

# Management resumes PM with automation
~/Desktop/adjudica-documentation/engineering/scripts/resume-pm-team.sh \
    .planning/handoffs/PM_HANDOFF_*.md --spawn
```

For complete details, see the comprehensive guide in adjudica-documentation.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
