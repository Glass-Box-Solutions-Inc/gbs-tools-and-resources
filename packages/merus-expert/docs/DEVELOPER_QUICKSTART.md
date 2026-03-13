<!-- @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology -->

# MerusExpert Developer Quickstart

**Goal:** Get a fully working local environment — backend API, frontend UI, and AI agent — running in 15 minutes.

**Stack:** Python 3.12, FastAPI, Anthropic Claude SDK, React 18 + TypeScript, Vite, Tailwind CSS

---

## 1. Prerequisites

Install these before starting. Verify each with the version check commands.

| Tool | Minimum Version | Check |
|------|-----------------|-------|
| Python | 3.12 | `python --version` |
| Node.js | 20 | `node --version` |
| npm | 9+ | `npm --version` |
| Docker | 24+ | `docker --version` |
| git | any | `git --version` |

You also need credentials for three external services before you can run the agent:

- **Anthropic API key** — from [console.anthropic.com](https://console.anthropic.com)
- **MerusCase OAuth token** — from your firm's MerusCase OAuth flow, or contact your MerusCase admin
- **Browserless API token** — from [browserless.io](https://www.browserless.io) (required only for browser automation / matter creation; the REST API and AI agent work without it)

---

## 2. Clone and Setup

```bash
# Clone the repo
git clone https://github.com/Glass-Box-Solutions-Inc/merus-expert.git
cd merus-expert

# Create and activate a Python virtual environment
python3.12 -m venv .venv
source .venv/bin/activate       # macOS / Linux
# .venv\Scripts\activate        # Windows PowerShell

# Install the Python package in editable mode (includes all dependencies)
pip install -e ".[dev]"

# Install Playwright's Chromium browser (required for matter creation automation)
playwright install chromium

# Install frontend dependencies
cd frontend
npm install
cd ..
```

---

## 3. Environment Variables

Copy the example file and fill in your credentials.

```bash
cp .env.example .env
```

Open `.env` and set these values:

### Required

| Variable | Description | Where to Get It |
|----------|-------------|-----------------|
| `ANTHROPIC_API_KEY` | Claude API key | [console.anthropic.com](https://console.anthropic.com) |
| `MERUS_API_KEY` | Secret key that protects the service endpoints — generate any strong random string | `openssl rand -hex 32` |
| `MERUSCASE_ACCESS_TOKEN` | MerusCase OAuth Bearer token | MerusCase OAuth flow or your admin |

### Optional (with defaults)

| Variable | Default | Description |
|----------|---------|-------------|
| `MERUSCASE_TOKEN_FILE` | `.meruscase_token` | File path for token (fallback when `ACCESS_TOKEN` is unset) |
| `MERUSCASE_EMAIL` | — | MerusCase login email (browser automation only) |
| `MERUSCASE_PASSWORD` | — | MerusCase password (browser automation only) |
| `BROWSERLESS_API_TOKEN` | — | Browserless API token (browser automation only) |
| `LOG_LEVEL` | `INFO` | Python log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `PORT` | `8000` | Backend listen port |
| `CORS_ORIGINS` | `http://localhost:3000,http://localhost:3001` | Allowed CORS origins (comma-separated) |
| `CACHE_TTL_SECONDS` | `3600` | Reference data cache lifetime in seconds |
| `DB_PATH` | `./knowledge/db/merus_knowledge.db` | SQLite database path |

### Token file alternative

If you store the MerusCase token in a file instead of an env var:

```bash
echo "your_token_here" > .meruscase_token
# Then in .env, leave MERUSCASE_ACCESS_TOKEN unset and set:
# MERUSCASE_TOKEN_FILE=.meruscase_token
```

The service reads `MERUSCASE_ACCESS_TOKEN` first. If it is not set, it falls back to reading `MERUSCASE_TOKEN_FILE`.

### Minimal working `.env` example

```bash
# Required
ANTHROPIC_API_KEY=sk-ant-api03-...
MERUS_API_KEY=a1b2c3d4e5f6...        # generate with: openssl rand -hex 32
MERUSCASE_ACCESS_TOKEN=eyJhbGci...   # your MerusCase OAuth token

# Sensible defaults — override as needed
LOG_LEVEL=DEBUG
PORT=8000
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
```

---

## 4. Run Locally

Run the backend and frontend in two separate terminal tabs.

### Terminal 1 — Backend (FastAPI)

```bash
cd /path/to/merus-expert
source .venv/bin/activate

uvicorn service.main:app --host 0.0.0.0 --port 8000 --reload
```

Expected startup output:

```
INFO  Starting merus-expert service...
INFO  Database initialized at ./knowledge/db/merus_knowledge.db
INFO  MerusAgent initialized
INFO  ClaudeAgent initialized
INFO  Uvicorn running on http://0.0.0.0:8000
```

If `MerusAgent init deferred` appears instead of `MerusAgent initialized`, the token is missing or unreadable. Check the `MERUSCASE_ACCESS_TOKEN` value in `.env`.

### Terminal 2 — Frontend (Vite dev server)

```bash
cd /path/to/merus-expert/frontend
npm run dev
```

Expected output:

```
  VITE v5.x.x  ready in 300 ms
  Local:   http://localhost:5173/
```

Open [http://localhost:5173](http://localhost:5173) in your browser. The Vite dev server proxies all `/api/*` requests to `http://localhost:8000`, so the frontend talks to your local backend automatically — no CORS configuration needed during development.

---

## 5. Test the Agent

All REST endpoints require the `X-API-Key` header matching your `MERUS_API_KEY` value. The `/health` endpoint is public.

### Health check (no auth required)

```bash
curl http://localhost:8000/health
```

Expected response:

```json
{
  "status": "healthy",
  "timestamp": "2026-02-23T10:00:00.000000",
  "service": "merus-expert",
  "version": "2.0.0"
}
```

### Search a case

```bash
curl -H "X-API-Key: your_merus_api_key" \
  "http://localhost:8000/api/cases/search?query=Smith"
```

### List active cases

```bash
curl -H "X-API-Key: your_merus_api_key" \
  "http://localhost:8000/api/cases?status=Active&limit=10"
```

### Get billing entries for a case

```bash
curl -H "X-API-Key: your_merus_api_key" \
  "http://localhost:8000/api/cases/56171871/billing?date_gte=2024-01-01"
```

### Bill time to a case

```bash
curl -X POST http://localhost:8000/api/billing/time \
  -H "X-API-Key: your_merus_api_key" \
  -H "Content-Type: application/json" \
  -d '{
    "case_search": "Smith",
    "hours": 0.2,
    "description": "Reviewed QME report and drafted response letter"
  }'
```

### Start an AI agent chat (SSE streaming)

The agent endpoint returns a `text/event-stream` response. Use `curl -N` to stream output:

```bash
curl -N -X POST http://localhost:8000/api/agent/chat \
  -H "X-API-Key: your_merus_api_key" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "Find the Smith case and show me the billing summary"}
    ],
    "max_iterations": 10
  }'
```

Each line of the response is a Server-Sent Event:

```
data: {"type": "text", "content": "I'll look up the Smith case for you."}
data: {"type": "tool_call", "name": "find_case", "input": {"search": "Smith"}}
data: {"type": "tool_result", "name": "find_case", "result": {"id": "56171871", ...}}
data: {"type": "text", "content": "Found it. Here's the billing summary..."}
data: {"type": "done"}
```

The interactive UI in the frontend at [http://localhost:5173](http://localhost:5173) handles this SSE stream automatically — navigate to the AI Assistant page to use the chat interface.

---

## 6. Frontend Development

The frontend is a standard Vite + React + TypeScript project.

```bash
cd frontend

# Start dev server with hot module replacement
npm run dev        # http://localhost:5173

# Type-check without building
npx tsc --noEmit

# Lint
npm run lint

# Build for production (outputs to frontend/dist/)
npm run build
```

### How the proxy works

`frontend/vite.config.ts` forwards all `/api/*` requests from the Vite dev server to the FastAPI backend:

```
Browser (localhost:5173) --/api/--> Vite proxy --> FastAPI (localhost:8000)
```

This means the frontend code always uses relative paths like `/api/cases/search` — the same paths work in both development (proxied by Vite) and production (served from the same FastAPI process via the built static files in `static/`).

### Key frontend files to know

| File | Purpose |
|------|---------|
| `frontend/src/lib/api/client.ts` | Shared fetch client — injects `X-API-Key` header on every request |
| `frontend/src/lib/api/agent.ts` | `streamAgentChat()` — async generator that consumes the SSE stream |
| `frontend/src/hooks/useAgent.ts` | React hook — conversation state, streaming control, abort |
| `frontend/src/stores/settingsStore.ts` | Zustand store — persists `MERUS_API_KEY` in `localStorage` |
| `frontend/src/lib/types.ts` | All shared TypeScript types |

The `MERUS_API_KEY` is stored in `localStorage` via the Settings page — navigate to Settings in the UI to enter it the first time.

---

## 7. Docker Build and Run

The Dockerfile is a three-stage build: frontend assets, Python wheel, runtime image.

### Build the image

```bash
# From the repo root
docker build -t merus-expert:latest .
```

Build time is approximately 2-4 minutes on first run (npm install + pip wheel).

### Run locally with Docker

```bash
# Ensure your .env file is populated, then:
docker run --rm -p 8000:8000 \
  --env-file .env \
  -v "$(pwd)/.meruscase_token:/app/.auth/.meruscase_token:ro" \
  -v merus-data:/data \
  merus-expert:latest
```

The app serves both the API and the React frontend from the same port. Visit [http://localhost:8000](http://localhost:8000) to access the UI.

### Run with Docker Compose

```bash
# Requires .env populated and token file at /opt/merus-expert/.meruscase_token
docker compose up -d

# View logs
docker compose logs -f

# Stop
docker compose down
```

The Compose file mounts `/opt/merus-expert/.meruscase_token` into the container. Update the path in `docker-compose.yml` if your token lives elsewhere.

---

## 8. Deploy to Cloud Run

The target GCP project is `adjudica-internal`. Ensure you are authenticated:

```bash
gcloud auth login
gcloud config set project adjudica-internal
```

### Build and push to Artifact Registry

```bash
export IMAGE="us-central1-docker.pkg.dev/adjudica-internal/merus-expert/merus-expert:latest"

docker build -t "$IMAGE" .
docker push "$IMAGE"
```

### Deploy to Cloud Run

```bash
gcloud run deploy merus-expert \
  --image "$IMAGE" \
  --region us-central1 \
  --platform managed \
  --port 8000 \
  --memory 1Gi \
  --cpu 1 \
  --min-instances 0 \
  --max-instances 3 \
  --set-env-vars "LOG_LEVEL=INFO,CACHE_TTL_SECONDS=3600" \
  --set-secrets "ANTHROPIC_API_KEY=anthropic-api-key:latest,MERUS_API_KEY=merus-api-key:latest,MERUSCASE_ACCESS_TOKEN=meruscase-access-token:latest" \
  --no-allow-unauthenticated
```

Secrets must already exist in GCP Secret Manager. Create them if they do not exist:

```bash
echo -n "sk-ant-..." | gcloud secrets create anthropic-api-key --data-file=-
echo -n "your-key" | gcloud secrets create merus-api-key --data-file=-
echo -n "your-token" | gcloud secrets create meruscase-access-token --data-file=-
```

To check the deployed service:

```bash
gcloud run services describe merus-expert --region us-central1
```

---

## 9. Project Structure

```
merus-expert/
│
├── src/merus_expert/           # Core Python package (installed as a wheel)
│   ├── agent/
│   │   ├── claude_agent.py     # ClaudeAgent — Anthropic streaming tool-use loop
│   │   ├── tools.py            # 13 Anthropic tool definitions + dispatch_tool()
│   │   └── system_prompt.py    # System prompt builder (reads knowledge docs)
│   ├── core/
│   │   └── agent.py            # MerusAgent — business logic, fuzzy case search, caching
│   └── api_client/
│       ├── client.py           # MerusCaseAPIClient — httpx async HTTP client
│       └── models.py           # Pydantic models (Party, Activity, LedgerEntry, APIResponse)
│
├── service/                    # FastAPI application layer
│   ├── main.py                 # App factory, lifespan, CORS, exception handlers
│   ├── auth.py                 # X-API-Key header validation
│   ├── dependencies.py         # lru_cache singletons for MerusAgent + ClaudeAgent
│   ├── routes/
│   │   ├── agent.py            # POST /api/agent/chat — SSE streaming AI agent
│   │   ├── cases.py            # GET /api/cases, /api/cases/search, /api/cases/{id}/*
│   │   ├── billing.py          # POST /api/billing/time, /api/billing/cost
│   │   ├── activities.py       # Activity routes
│   │   ├── reference.py        # GET /api/reference/billing-codes, /activity-types
│   │   ├── health.py           # GET /health (no auth)
│   │   ├── chat.py             # Matter creation chat flow
│   │   └── matter.py           # Matter submission endpoint
│   ├── models/
│   │   ├── requests.py         # Pydantic request models
│   │   └── responses.py        # Pydantic response models
│   └── services/
│       ├── chat_store.py       # Chat session persistence
│       ├── billing_store.py    # Billing entry persistence
│       ├── conversation_flow.py # Matter creation conversation logic
│       └── intelligent_parser.py # Gemini-based NLP for matter field extraction
│
├── frontend/                   # React + TypeScript SPA
│   ├── src/
│   │   ├── lib/api/            # API client modules (cases, billing, agent SSE)
│   │   ├── hooks/              # React hooks (useAgent, useCases, useBilling)
│   │   ├── stores/             # Zustand stores (settings, navigation, UI)
│   │   └── components/pages/   # Page components (AIAssistant, Cases, Billing, etc.)
│   └── vite.config.ts          # Vite config — dev proxy /api → localhost:8000
│
├── knowledge/
│   ├── docs/                   # Markdown knowledge files (embedded in Claude system prompt)
│   ├── billing_codes.json      # Available billing codes (embedded in system prompt)
│   └── db/                     # SQLite database (auto-created on startup)
│
├── setup/
│   └── schema.sql              # SQLite schema — 11 tables, auto-applied on startup
│
├── persistence/                # Legacy browser automation persistence layer
├── browser/                    # Browserless WebSocket automation (matter creation)
├── automation/                 # Matter creation workflow (MatterBuilder, FormFiller)
├── docs/                       # Developer documentation
├── Dockerfile                  # Multi-stage build: frontend + Python wheel + runtime
├── docker-compose.yml          # Local compose config
├── pyproject.toml              # Package metadata + dependencies
└── .env.example                # Environment variable reference
```

---

## 10. Common Issues

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `MerusAgent init deferred (token not available)` on startup | `MERUSCASE_ACCESS_TOKEN` missing or empty in `.env` | Verify the value in `.env` — the token should be a long JWT or opaque string with no whitespace |
| `HTTP 401 Invalid API key` on API calls | `X-API-Key` header missing or wrong | Ensure the header value matches `MERUS_API_KEY` in `.env` exactly |
| `HTTP 401 Authentication failed` from MerusCase API | MerusCase OAuth token expired | Obtain a fresh token via the MerusCase OAuth flow and update `MERUSCASE_ACCESS_TOKEN` |
| `HTTP 429 Rate limit exceeded` | Too many MerusCase API calls | Wait for the `X-RateLimit-Reset` time shown in the error response, then retry |
| CORS errors in the browser console | Origin not in `CORS_ORIGINS` | Add `http://localhost:5173` to `CORS_ORIGINS` in `.env` and restart the backend |
| Frontend shows "Go to Settings" instead of chat | API key not configured in the UI | Go to the Settings page and enter your `MERUS_API_KEY` value |
| `ModuleNotFoundError: No module named 'merus_expert'` | Package not installed in the active venv | Run `pip install -e ".[dev]"` with the venv activated |
| Docker build fails at `npm install` | Node lockfile mismatch | Run `npm install` locally in `frontend/` to regenerate `package-lock.json`, then rebuild |
| `playwright install chromium` hangs | Network timeout | Set `PLAYWRIGHT_BROWSERS_PATH` to a local cache dir and retry on a better connection |
| SSE stream ends immediately with no events | `ANTHROPIC_API_KEY` invalid or missing | Confirm the key in `.env` starts with `sk-ant-` and is not truncated |
| SQLite database errors on startup | `DB_PATH` directory does not exist | The service creates the directory automatically; if it fails, check filesystem permissions on the path in `DB_PATH` |

---

## Quick Reference

### Start everything locally

```bash
# Terminal 1 — backend
source .venv/bin/activate && uvicorn service.main:app --port 8000 --reload

# Terminal 2 — frontend
cd frontend && npm run dev
```

### Run tests

```bash
# Python unit + integration tests
pytest

# Skip tests that require live MerusCase credentials
pytest -m "not live"

# TypeScript type check
cd frontend && npx tsc --noEmit
```

### API documentation

With the backend running, the auto-generated OpenAPI docs are at:

- Interactive: [http://localhost:8000/docs](http://localhost:8000/docs)
- JSON schema: [http://localhost:8000/openapi.json](http://localhost:8000/openapi.json)

---

*For the full technical reference including SSE event format, tool schemas, and error handling, see [`docs/AGENT_DOCUMENTATION.md`](AGENT_DOCUMENTATION.md).*

*For company-wide development standards, see the [Root CLAUDE.md](https://github.com/Glass-Box-Solutions-Inc/adjudica-documentation/blob/main/engineering/ROOT_CLAUDE.md).*
