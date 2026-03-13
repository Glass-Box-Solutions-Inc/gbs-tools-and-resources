# Spectacles - CLAUDE.md

**AI-Powered Browser Automation Platform**

Spectacles combines Playwright browser control, Gemini 2.5 Flash vision, and human-in-the-loop coordination for intelligent web automation.

---

## ⚠️ CRITICAL GUARDRAILS (READ FIRST)

1. **NEVER push without permission** — Even small fixes require express user permission. No exceptions.
2. **NEVER expose secrets** — No API keys, tokens, credentials in git, logs, or conversation.
3. **NEVER force push or skip tests** — 100% passing tests required.
4. **ALWAYS read parent CLAUDE.md** — `~/CLAUDE.md` for org-wide standards.
5. **ALWAYS use Definition of Ready** — 100% clear requirements before implementation.

---

## Quick Reference

| Item | Value |
|------|-------|
| **Status** | Production (Live) |
| **Stack** | Python 3.12, FastAPI, Playwright, Browserless.io, Gemini 2.5 Flash |
| **Entry Point** | `api/main.py` |
| **Port** | 8080 (local), 3700 (registry) |
| **Database** | SQLite (local) / PostgreSQL (production) |

### Production URLs

| Environment | URL |
|-------------|-----|
| **Primary (glassbox-spectacles)** | https://spectacles-gc2qovgs7q-uc.a.run.app |
| **Legacy (ousd-campaign)** | https://spectacles-378330630438.us-central1.run.app ⚠️ *migrate away* |
| **Health Check** | https://spectacles-gc2qovgs7q-uc.a.run.app/health |
| **API Docs** | https://spectacles-gc2qovgs7q-uc.a.run.app/docs |

---

## Commands

```bash
# Setup
pip install -r requirements.txt
playwright install chromium

# Development
uvicorn api.main:app --reload --port 8080

# Tests
pytest tests/

# Type check
mypy api/ core/ browser/

# Deploy
gcloud run deploy spectacles --source . --region us-central1 --project glassbox-spectacles
```

---

## Directory Structure

```
spectacles/
├── api/                  # FastAPI application
│   ├── main.py           # Entry point
│   ├── config.py         # Pydantic Settings
│   └── routes/           # API endpoints (tasks, skills, webhooks, health)
├── core/                 # Agent logic
│   ├── orchestrator.py   # Task planning & delegation
│   ├── browser_specialist.py
│   ├── desktop_specialist.py
│   ├── file_specialist.py
│   ├── state_machine.py
│   └── perception/       # DOM + VLM perception
├── browser/              # Browserless CDP client
├── desktop/              # Desktop automation (VM only)
├── hitl/                 # Human-in-the-loop (Slack)
├── memory/               # Pinecone vector store
├── persistence/          # SQLite/PostgreSQL storage
├── security/             # Secrets, PII blur, audit
│   └── auth_capture.py   # Auth capture module
├── tools/                # CLI tools
│   └── capture_auth.py   # Auth capture CLI
└── mcp/                  # MCP server for agents
```

---

## Key Capabilities

| Capability | Description |
|------------|-------------|
| **Hybrid Perception** | 80% DOM-based + 20% Vision AI fallback |
| **Natural Language Goals** | "Log into MerusCase and download the December billing report" |
| **Human-in-the-Loop** | Slack approvals, browser takeover, uncertainty handling |
| **State Persistence** | Checkpoint/resume for long-running tasks |
| **Auth Capture** | Interactive credential capture for any service |
| **PII Protection** | Automatic blurring in screenshots |

---

## API Endpoints

### Core Task API
- `POST /api/tasks/` — Submit automation task
- `GET /api/tasks/{id}` — Get status/results
- `POST /api/tasks/{id}/resume` — Resume after HITL
- `POST /api/tasks/{id}/cancel` — Cancel task

### Skills API (AI Agent Optimized)
- `POST /api/skills/browser` — Browser automation
- `POST /api/skills/screenshot` — Quick screenshot with PII blur
- `POST /api/skills/auth-capture` — Start auth capture session
- `GET /api/skills/capabilities` — List capabilities

### MCP Tools
- `spectacles_execute_task` — Start browser automation
- `spectacles_get_status` — Check task status
- `spectacles_resume_task` — Resume paused task

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `BROWSERLESS_API_TOKEN` | Yes | Browserless API token |
| `GOOGLE_AI_API_KEY` | Yes | Gemini API key |
| `GCP_PROJECT_ID` | Yes | GCP project for Secret Manager |
| `SLACK_WEBHOOK_MAIN` | Recommended | Main channel webhook |
| `PINECONE_API_KEY` | Optional | Long-term memory |

See `.env.example` for full list.

---

## Slack Webhooks

| Name | GCP Secret | Use Case |
|------|------------|----------|
| `main` | `slack-webhook-main` | Default approvals |
| `alex` | `slack-webhook-alex` | Alex notifications |
| `brian` | `slack-webhook-brian` | Brian notifications |
| `social` | `slack-webhook-social` | Social automation |

---

## State Machine

```
PLANNING → NAVIGATING → OBSERVING ⟷ ACTING → EVALUATING
                                                ↓
                            COMPLETED | AWAITING_HUMAN | ERROR_RECOVERY
```

Tasks can pause at `AWAITING_HUMAN` and resume hours later with full state persistence.

---

## Security

- **Credentials**: GCP Secret Manager only — never in LLM context
- **PII**: Auto-detected and blurred in screenshots
- **Audit**: SOC2/HIPAA-compliant logging
- **Sessions**: Fernet encryption for browser state

---

## Documentation

| Document | Purpose |
|----------|---------|
| `README.md` | Full technical documentation |
| `docs/SPECTACLES_INTEGRATION_GUIDE.md` | Integration patterns |
| `docs/SPECTACLES_AUTH_FLOW_TESTING.md` | Auth testing guide |
| `BIDIRECTIONAL_SLACK.md` | Slack Bolt integration |
| `SLACK_SETUP.md` | Slack workspace setup |
| `.planning/STATE.md` | Current development state |
| `.planning/ROADMAP.md` | Feature roadmap |

---

## Related Projects

- `../merus-expert/` — Uses Spectacles for browser tasks
- `../mcp-servers/` — MCP server patterns
- `~/Desktop/adjudica-documentation/engineering/testing/SPECTACLES_TESTING_GUIDE.md` — Visual testing standard

---

## Context & Team Management

This project follows GBS Context & Team Management philosophy:
- **65% context = STOP** — Initiate handoff
- **>50% context = PM + Specialist teams**
- **Plan first, always**

See `~/Desktop/adjudica-documentation/engineering/CONTEXT_AND_TEAM_MANAGEMENT.md`.

---

## ⚠️ GUARDRAILS REMINDER

Before ANY action, verify:

- [ ] **Push permission?** — Required for every push, no exceptions
- [ ] **Definition of Ready?** — Requirements 100% clear
- [ ] **Tests passing?** — 100% required
- [ ] **Root cause understood?** — For fixes, understand WHY first

---

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
