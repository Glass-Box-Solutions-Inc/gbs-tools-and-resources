# Merus Expert - CLAUDE.md

**MerusCase Integration Platform — REST API Client, AI Agent, Browser Automation**
Full-stack MerusCase integration: natural language AI agent (Claude), REST API client, React frontend, and browser automation for matter creation.

---

## Quick Reference

| Item | Value |
|------|-------|
| **Version** | 2.0.0 |
| **Status** | Production |
| **Stack** | Python 3.12, FastAPI, Anthropic Claude, httpx, React 18, Vite, Tailwind, Playwright, Browserless, SQLite |
| **Entry Point** | `uvicorn service.main:app` |
| **Database** | SQLite (`knowledge/db/merus_knowledge.db`) + MerusCase REST API |
| **Frontend** | `frontend/` — React 18 + Vite + Tailwind |

---

## Commands

```bash
# ── Setup ──
pip install -e ".[dev]"           # Install package + dev deps
playwright install chromium        # Browser automation engine
cd frontend && npm install         # Frontend deps

# ── Run (local dev) ──
uvicorn service.main:app --reload --port 8000   # Backend (terminal 1)
cd frontend && npm run dev                       # Frontend (terminal 2)

# ── Run (Docker) ──
docker compose up --build          # Full stack (backend + frontend)

# ── Tests ──
pytest                             # Unit + integration tests
pytest -m "not live"               # Skip tests requiring MerusCase credentials
pytest tests/unit/                 # Unit tests only

# ── OAuth token acquisition ──
python oauth_browser_flow.py       # Automated (recommended)
python manual_oauth.py             # Human-in-the-loop fallback

# ── Database ──
python main.py init-db             # Initialize SQLite schema

# ── Legacy CLI ──
python main.py test-browser        # Test Browserless connection
python main.py demo                # Matter creation dry-run
```

---

## Architecture

```
merus-expert/
├── src/merus_expert/              # Core Python package (pip-installable)
│   ├── agent/                     # Claude AI agent
│   │   ├── claude_agent.py        # ClaudeAgent — orchestrates tool-use loop
│   │   ├── system_prompt.py       # Agent system prompt
│   │   └── tools.py               # 13 tool definitions + dispatch
│   ├── api_client/                # MerusCase REST API client
│   │   ├── client.py              # MerusCaseAPIClient — httpx-based
│   │   └── models.py              # API data models (Party, Activity, Document, etc.)
│   ├── core/                      # Business logic layer
│   │   └── agent.py               # MerusAgent — high-level operations, caching, search
│   ├── automation/                # Browser automation for matter creation
│   │   ├── matter_builder.py      # MatterBuilder — form-based matter creation
│   │   ├── hybrid_matter_builder.py  # HybridMatterBuilder — browser + API
│   │   ├── form_filler.py         # Form field population
│   │   ├── billing_builder.py     # Billing entry automation
│   │   ├── billing_form_filler.py # Billing form population
│   │   └── document_uploader.py   # Document upload automation
│   ├── batch/                     # Batch import operations
│   │   ├── batch_importer.py      # Bulk case/document import
│   │   ├── folder_scanner.py      # File system scanner
│   │   └── import_tracker.py      # Import progress tracking
│   ├── browser/                   # Low-level browser interaction
│   │   ├── client.py              # Browserless WebSocket CDP client
│   │   ├── local_client.py        # Local Playwright client
│   │   ├── element_handler.py     # Element finding strategies
│   │   ├── dropdown_handler.py    # Dropdown interaction
│   │   ├── file_handler.py        # File upload handling
│   │   └── matter_finder.py       # Matter search in UI
│   ├── models/                    # Pydantic data models
│   │   ├── matter.py              # MatterDetails, CaseType, BillingInfo
│   │   └── session.py             # Session state
│   ├── persistence/               # SQLite persistence layer
│   │   ├── session_store.py       # Session management
│   │   ├── matter_store.py        # Matter tracking
│   │   ├── audit_store.py         # SOC2 audit logging
│   │   ├── constants.py           # Enums
│   │   └── utils.py               # DB utilities
│   └── security/                  # Security & compliance
│       ├── config.py              # SecurityConfig — all env var loading
│       └── audit.py               # Audit logger
│
├── service/                       # FastAPI HTTP service
│   ├── main.py                    # App factory, CORS, routers, static serving
│   ├── auth.py                    # X-API-Key authentication
│   ├── dependencies.py            # Singleton injection (MerusAgent, ClaudeAgent)
│   ├── routes/                    # 8 API routers
│   │   ├── health.py              # GET /health
│   │   ├── cases.py               # GET /api/cases/*
│   │   ├── billing.py             # POST /api/billing/*
│   │   ├── activities.py          # POST /api/activities/*
│   │   ├── reference.py           # GET /api/reference/*
│   │   ├── agent.py               # POST /api/agent/chat (SSE)
│   │   ├── chat.py                # /api/chat/* (matter wizard)
│   │   └── matter.py              # /api/matter/* (submit/preview)
│   ├── models/                    # Request/response Pydantic models
│   │   ├── requests.py
│   │   └── responses.py
│   └── services/                  # Service-layer logic
│       ├── conversation_flow.py   # Matter wizard state machine
│       ├── chat_store.py          # Chat session persistence
│       ├── billing_flow.py        # Billing workflow logic
│       ├── billing_store.py       # Billing persistence
│       └── intelligent_parser.py  # NLP parsing (Gemini)
│
├── frontend/                      # React 18 SPA
│   ├── src/
│   │   ├── App.tsx                # Root component
│   │   ├── router.tsx             # Route definitions
│   │   ├── components/            # UI components
│   │   ├── hooks/                 # Custom React hooks
│   │   ├── stores/                # Zustand state
│   │   └── lib/                   # Utilities, API client
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   └── package.json
│
├── integrations/                  # External service clients
│   └── specticles_client.py       # Spectacles visual analysis
│
├── knowledge/                     # Knowledge base & screenshots
│   └── db/                        # SQLite database files
│
├── setup/
│   └── schema.sql                 # SQLite schema
│
├── tests/                         # Test suite
│   ├── unit/                      # Unit tests
│   ├── integration/               # Integration tests
│   └── conftest.py                # Shared fixtures
│
├── docs/                          # Documentation
│   ├── AGENT_DOCUMENTATION.md     # Full agent + tool reference
│   ├── DEVELOPER_QUICKSTART.md    # Local dev setup guide
│   ├── OAUTH_GUIDE.md             # OAuth token lifecycle
│   └── MERUSCASE_API_DEVELOPER_GUIDE.md
│
├── *.py (root)                    # OAuth scripts, batch utilities, explorers
│   ├── oauth_browser_flow.py      # Automated OAuth acquisition
│   ├── complete_oauth.py          # OAuth with consent handling
│   ├── oauth_via_main.py          # OAuth via main site login
│   ├── manual_oauth.py            # Human-in-the-loop OAuth
│   ├── get_oauth_creds.py         # Retrieve OAuth app credentials
│   └── extract_oauth_creds.py     # Extract existing app credentials
│
├── Dockerfile                     # Multi-stage build (frontend + backend)
├── docker-compose.yml
├── pyproject.toml                 # Python package config (v2.0.0)
└── main.py                        # Legacy CLI entry point
```

---

## Key Components

### ClaudeAgent (`src/merus_expert/agent/claude_agent.py`)
Anthropic Claude-powered conversational agent with tool-use loop:
- Accepts natural language queries via SSE streaming
- Dispatches to 13 MerusCase tools (defined in `tools.py`)
- Returns structured results with intermediate tool-call events

### MerusAgent (`src/merus_expert/core/agent.py`)
High-level MerusCase operations layer:
- Natural language case search (fuzzy matching)
- Billing: `bill_time()`, `add_cost()`, `get_billing_summary()`
- Activities: `add_note()`, `get_case_activities()`
- Documents: `upload_document()`
- Reference data caching (billing codes, activity types) with configurable TTL
- Error handling with typed exceptions (`CaseNotFoundError`, `BillingError`)

### MerusCaseAPIClient (`src/merus_expert/api_client/client.py`)
Low-level httpx-based REST client for `api.meruscase.com`:
- OAuth token management
- CRUD for cases, parties, activities, documents, ledger entries
- Typed response models

### FastAPI Service Layer (`service/`)
HTTP API exposing MerusAgent and ClaudeAgent:
- 8 routers: health, cases, billing, activities, reference, agent, chat, matter
- API key authentication (`X-API-Key` header)
- SSE streaming for agent chat
- Static file serving for frontend SPA (in Docker builds)
- Swagger UI at `/docs`

### Browser Automation (Legacy)

#### MatterBuilder (`src/merus_expert/automation/matter_builder.py`)
Browser-based matter creation orchestrator:
1. LOGIN → Authenticate with MerusCase
2. NAVIGATE → Go to new matter form
3. FILL_FORM → Populate all fields
4. SUBMIT/PREVIEW → Submit or dry-run
5. VERIFY → Confirm success

#### HybridMatterBuilder (`src/merus_expert/automation/hybrid_matter_builder.py`)
Combined browser + API approach — uses browser for form submission, API for data enrichment.

#### BrowserClient (`src/merus_expert/browser/client.py`)
Browserless API connection via WebSocket CDP. Page navigation, screenshot capture, element location with fallback strategies.

---

## Configuration

Environment variables in `.env` (see `.env.example` for all variables):

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | *(required)* | Anthropic Claude API key |
| `MERUS_API_KEY` | *(required)* | REST API authentication key |
| `MERUSCASE_ACCESS_TOKEN` | — | OAuth token (or use token file) |
| `MERUSCASE_TOKEN_FILE` | `.meruscase_token` | Path to OAuth token file |
| `MERUSCASE_API_CLIENT_ID` | — | OAuth app client ID |
| `MERUSCASE_API_CLIENT_SECRET` | — | OAuth app client secret |
| `MERUSCASE_API_BASE_URL` | `https://api.meruscase.com` | MerusCase API base |
| `MERUSCASE_EMAIL` | — | Browser automation login |
| `MERUSCASE_PASSWORD` | — | Browser automation password |
| `BROWSERLESS_API_TOKEN` | — | Browserless cloud token |
| `CACHE_TTL_SECONDS` | `3600` | Reference data cache TTL |
| `CORS_ORIGINS` | `http://localhost:3000,...` | Allowed CORS origins |
| `PORT` | `8000` | Service port |
| `GOOGLE_API_KEY` | — | Gemini API key (NLP parser) |
| `DB_PATH` | `./knowledge/db/merus_knowledge.db` | SQLite database path |
| `LOG_LEVEL` | `INFO` | Logging level |

---

## SOC2 Compliance

- **Audit Logging**: All operations logged with 90-day retention
- **Session Management**: 30-min timeout, 8-hour max duration
- **Screenshot Retention**: 24-hour auto-cleanup
- **Categories**: AUTHENTICATION, MATTER_OPERATIONS, CREDENTIAL_ACCESS, BROWSER_AUTOMATION, SECURITY_EVENTS

---

## Usage Example

### REST API

```bash
# Search for a case
curl -H "X-API-Key: $MERUS_API_KEY" \
  "http://localhost:8000/api/cases/search?query=Smith"

# Bill time
curl -X POST -H "X-API-Key: $MERUS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"case_search": "Smith", "hours": 0.5, "description": "Research"}' \
  http://localhost:8000/api/billing/time
```

### Python (MerusAgent)

```python
from merus_expert.core.agent import MerusAgent

agent = MerusAgent(access_token="your_token")
case = await agent.find_case("Smith v. Jones")
billing = await agent.get_billing_summary(case_search="Smith")
await agent.bill_time(case_search="Smith", hours=0.5, description="Research")
await agent.close()
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `401 Unauthorized` from API | OAuth token expired — re-run `python oauth_browser_flow.py` (see `docs/OAUTH_GUIDE.md`) |
| `ANTHROPIC_API_KEY` not set | Add key to `.env` — required for AI agent |
| Browser connection fails | Check `BROWSERLESS_API_TOKEN` in `.env` |
| Database errors | Run `python main.py init-db` |
| Frontend not loading | Run `cd frontend && npm install && npm run dev` |
| CORS errors | Check `CORS_ORIGINS` matches your frontend URL |
| Import errors | Run `pip install -e ".[dev]"` (editable install) |

## Trigger Table

When working in this project, these keywords load additional context:

| Keyword | Resources | Context |
|---------|-----------|---------|
| `api` | `**/API*.md`, `glassy-infra/docs/subsystems/BACKEND_GUIDE.md` | Global |
| `fastapi` | `glassy-infra/docs/subsystems/BACKEND_GUIDE.md`, `projects/wc-paralegal-agent/CLAUDE.md` | Global |

*Auto-generated by Squeegee. Edit squeegee.config.json to customize.*

---

## Related Docs

- `README.md` — Project overview and quick start
- `docs/AGENT_DOCUMENTATION.md` — Full AI agent and tool reference
- `docs/DEVELOPER_QUICKSTART.md` — Local development setup guide
- `docs/OAUTH_GUIDE.md` — OAuth token lifecycle and troubleshooting
- `docs/MERUSCASE_API_DEVELOPER_GUIDE.md` — MerusCase API reference
- `BUILD_COMPLETE.md` — Build summary and status

---

## Tech Stack

<!-- SQUEEGEE:AUTO:START tech-stack -->
- **Language:** Python 3.12, TypeScript
- **Frameworks:** FastAPI, React 18, Vite
- **AI:** Anthropic Claude (tool-use agent), Google Gemini (NLP parsing)
- **HTTP:** httpx, sse-starlette
- **Browser:** Playwright, Browserless
- **Styling:** Tailwind CSS
- **State:** Zustand
- **ORM/DB:** SQLite (direct), Pydantic models
- **Tools:** Pydantic, structlog, Click
- **Testing:** pytest, pytest-asyncio
- **Code Quality:** Black, Ruff, MyPy
<!-- SQUEEGEE:AUTO:END tech-stack -->

---

For company-wide development standards, see the main CLAUDE.md at ~/Desktop/CLAUDE.md.
