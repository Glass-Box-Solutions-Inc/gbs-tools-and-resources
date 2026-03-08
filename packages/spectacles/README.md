# Spectacles

**Your AI's Eyes - Dual-Use Visual Agent**

Spectacles is a Cloud Run-deployed visual agent that serves as "your AI's eyes" with two complementary modes:

**Mode 1: Direct Browser Automation** - See and interact with web pages
**Mode 2: Claude Code Coordination** - Remote control of Claude Code instances with visual verification

Both modes provide visual and interactive capabilities that AI agents lack.

---

## Dual-Use Architecture

### Mode 1: Direct Browser Automation

**Use for**: Visual verification, testing UIs, navigating websites, managing credentials

```
"Take a screenshot of the dashboard"
"Test the login flow end-to-end"
"Verify the mobile responsive layout"
```

**Features**:
- **Hybrid Perception**: 80% DOM-based (fast) + 20% Vision AI (when needed)
- **Human-in-the-Loop**: Slack integration for approvals, rejections, and browser takeover
- **State Checkpointing**: Pause and resume tasks even hours later
- **MCP Server**: Other agents can delegate browser tasks to Spectacles
- **Auth Capture**: Interactive credential capture for any service (CLI, API, Python)
- **Security First**: Credentials never touch LLM context, PII blurred in screenshots

### Mode 2: Claude Code Coordination

**Use for**: Remote code execution with visual verification, coordinating development across machines

```
/spectacles ask glassy "implement dark mode toggle"
/spectacles ask wc-paralegal "fix responsive layout bug"
/spectacles sessions
```

**Features**:
- **Remote Control**: Execute Claude Code on dev-workstation from Slack
- **Live Updates**: Real-time progress (📋 Planning → 🔨 Working → ✅ Complete)
- **Session Management**: List, monitor, and kill active sessions
- **Visual Integration**: Claude Code can call Mode 1 for screenshots/verification
- **Admin Authorization**: Control who can execute remote commands

### Integration: Best of Both Modes

Claude Code (Mode 2) can call Spectacles (Mode 1) for visual tasks:

```python
# In a Claude Code session
from mcp import spectacles_execute_task

# After implementing a feature, verify visually
result = spectacles_execute_task(
    goal="Screenshot homepage with dark mode enabled",
    start_url="http://localhost:3000?theme=dark"
)
```

**Result**: Code execution with visual verification in one workflow

---

## When to Use Each Mode

| Mode | Use Case | Example |
|------|----------|---------|
| **Mode 1** | Visual-only tasks | "Screenshot the dashboard", "Test login flow" |
| **Mode 2** | Code + Visual tasks | `/spectacles ask glassy "add search feature"` |
| **Integrated** | Code with verification | Claude Code implements → calls Mode 1 for screenshot |

**Decision Rule**: If the task involves code changes, use Mode 2. Otherwise, use Mode 1.

---

## Documentation

**For team members:**
- 📘 **[Team Guide](TEAM_GUIDE.md)** - Comprehensive guide for all team members (functionality, examples, best practices)
- 🔑 **[Access Guide](ACCESS_GUIDE.md)** - Quick start guide for getting access to Spectacles

**For developers:**
- 🏗️ **[Dual-Use Architecture](SPECTICLES_DUAL_USE_ARCHITECTURE.md)** - Deep dive into Mode 1 + Mode 2 architecture
- ⚙️ **[Claude Code Control](CLAUDE_CODE_CONTROL.md)** - Implementation details for Mode 2
- ⚡ **[Quick Reference](SPECTICLES_QUICK_REFERENCE.md)** - Command reference and decision tree

---

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt
playwright install chromium

# Configure environment
cp .env.example .env
# Edit .env with your credentials

# Run locally
uvicorn api.main:app --reload --port 8080
```

## Architecture

```
User/Agent → FastAPI → Orchestrator → Browser Specialist → Browserless.io
                ↓              ↓
            Slack HITL    Gemini Vision (fallback)
```

### State Machine

The agent operates through these states:

1. **PLANNING** - Analyzes goal, creates action plan
2. **NAVIGATING** - Navigates to target URL
3. **OBSERVING** - Perceives page state (DOM or Vision)
4. **ACTING** - Executes browser action
5. **EVALUATING** - Checks if goal achieved
6. **AWAITING_HUMAN** - Paused for Slack response
7. **ERROR_RECOVERY** - Handling failures
8. **COMPLETED** - Task finished

## API Usage

### Submit a Task

```bash
curl -X POST http://localhost:8080/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "goal": "Log into example.com and download the monthly report",
    "start_url": "https://example.com/login",
    "credentials_key": "example-com-login",
    "require_approval": true
  }'
```

### Check Task Status

```bash
curl http://localhost:8080/tasks/{task_id}
```

### Resume After Human Approval

```bash
curl -X POST http://localhost:8080/tasks/{task_id}/resume \
  -H "Content-Type: application/json" \
  -d '{"approved": true, "human_input": "Continue with download"}'
```

## Slack Integration

When the agent needs human help, it sends a Slack message with:

- Screenshot of current page (PII blurred)
- Description of what it's trying to do
- Context about why it needs help
- Interactive buttons:
  - **Approve** - Continue with planned action
  - **Reject** - Cancel this action
  - **Take Control** - Get Browserless Live View URL to control browser

## MCP Server

Other Claude Code agents can use Spectacles as a tool:

```python
# From another agent
result = await spectacles_execute_task(
    goal="Fill out the contact form on example.com",
    start_url="https://example.com/contact",
    require_approval=True
)
```

Available MCP tools:
- `spectacles_execute_task` - Start a browser automation task
- `spectacles_get_status` - Check task status
- `spectacles_resume_task` - Resume paused task
- `spectacles_cancel_task` - Cancel running task

## Auth Capture

Capture authenticated browser state for any service interactively:

```bash
# CLI: Built-in presets for Google, GitHub, MerusCase, Westlaw
python tools/capture_auth.py --service google
python tools/capture_auth.py --service meruscase

# Custom service
python tools/capture_auth.py --service myapp \
    --login-url https://myapp.com/login \
    --verify-url https://myapp.com/dashboard
```

API endpoints:
- `POST /api/skills/auth-capture` - Start capture session (returns live browser URL)
- `POST /api/skills/auth-capture/{id}/complete` - Capture and save state
- `GET /api/skills/auth-capture/{id}` - Check session status
- `DELETE /api/skills/auth-capture/{id}` - Cancel session

## Security

### Credentials Management

Credentials are stored in GCP Secret Manager and only accessed at execution time:

```python
# Credentials are NEVER in LLM context
# Only the action executor accesses them directly
await secrets_vault.inject_credentials(page, "example-login")
```

### PII Protection

Screenshots are processed before sending to Slack:
- Credit card numbers → blurred
- SSN patterns → blurred
- Phone numbers → blurred

### Audit Logging

All actions are logged for compliance:
- AUTHENTICATION events
- BROWSER_AUTOMATION events
- HITL_INTERACTION events
- SECURITY_EVENTS

## Configuration

| Variable | Required | Description |
|----------|----------|-------------|
| `BROWSERLESS_API_TOKEN` | Yes | Browserless.io API token |
| `BROWSERLESS_ENDPOINT` | No | Custom endpoint (default: production-sfo) |
| `SLACK_BOT_TOKEN` | Yes | Slack bot OAuth token (xoxb-) |
| `SLACK_APP_TOKEN` | Yes | Slack app token for Socket Mode (xapp-) |
| `SLACK_APPROVAL_CHANNEL` | No | Channel for approvals (default: #spectacles-approvals) |
| `GOOGLE_AI_API_KEY` | Yes | Gemini API key (used for 2.5 Flash vision + 3.0 reasoning) |
| `PINECONE_API_KEY` | No | Pinecone for long-term memory |
| `PINECONE_INDEX` | No | Index name (default: spectacles-memory) |
| `GCP_PROJECT_ID` | Yes | GCP project for Secret Manager |
| `ENCRYPTION_KEY` | Yes | Fernet key for session encryption |

## Deployment

> **Canonical source: this monorepo** (`gbs-tools-and-resources`). Cloud Build trigger deploys from `packages/spectacles/` → Cloud Run. The standalone `Glass-Box-Solutions-Inc/Spectacles` repo is archived. See [`DEPLOYMENT_MODEL.md`](../../DEPLOYMENT_MODEL.md) for details.

### Docker

```bash
docker build -t spectacles .
docker run -p 8080:8080 --env-file .env spectacles
```

### Cloud Run

```bash
gcloud run deploy spectacles \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars "GCP_PROJECT_ID=your-project"
```

## Development

```bash
# Run tests
pytest tests/

# Type checking
mypy api/ core/ browser/

# Linting
ruff check .
```

## License

Proprietary - GlassBox Solutions
