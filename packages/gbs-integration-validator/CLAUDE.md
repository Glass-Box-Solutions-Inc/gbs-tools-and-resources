# GBS Integration Validator

Stateless Fastify 5 Cloud Run service that validates connectivity, response schemas, and credential permissions for all GBS platform APIs.

## 1. Purpose

This service provides automated validation of all external integrations used by Glass Box Solutions. It checks that API credentials are valid, responses match expected schemas, permissions are sufficient, and latency is within acceptable bounds. Used by the operations team to catch integration regressions before they affect production workflows.

## 2. Tech Stack

| Layer | Technology |
|-------|-----------|
| Runtime | Node.js 20+ |
| Framework | Fastify 5 |
| Language | TypeScript (strict, ESM) |
| Validation | Zod |
| HTTP client | ky |
| GitHub SDK | @octokit/rest |
| Linear SDK | @linear/sdk |
| Stripe SDK | stripe |
| GCP SDK | @google-cloud/resource-manager, @google-cloud/billing |
| Slack SDK | @slack/web-api |
| Logging | Pino (via Fastify) |
| Testing | Vitest |
| Container | Docker (multi-stage Alpine) |
| Deployment | GCP Cloud Run |

## 3. Commands

```bash
npm run dev            # Start dev server with hot reload (tsx watch)
npm run start          # Run production build
npm run build          # Compile TypeScript
npm run typecheck      # Type check without emitting
npm run lint           # ESLint
npm run format         # Prettier
npm run test           # Vitest unit tests
```

## 4. Architecture

```
gbs-integration-validator/
├── src/
│   ├── server.ts                  # Fastify entry point
│   ├── types/
│   │   └── index.ts               # Shared types (SystemName, ValidationCheck, etc.)
│   ├── lib/
│   │   ├── env.ts                 # Zod env validation
│   │   └── store.ts               # In-memory circular buffer + /tmp persistence
│   ├── routes/
│   │   ├── health.ts              # GET /health (no auth)
│   │   ├── status.ts              # GET /api/status (latest per-system status)
│   │   ├── run.ts                 # POST /api/run (trigger validation, 202)
│   │   └── results.ts             # GET /api/results, GET /api/results/:id
│   ├── validators/
│   │   ├── base.validator.ts      # Abstract base class
│   │   ├── github.validator.ts    # GitHub (Octokit)
│   │   ├── linear.validator.ts    # Linear (@linear/sdk)
│   │   ├── n8n.validator.ts       # n8n (ky HTTP)
│   │   ├── gcp.validator.ts       # GCP (Resource Manager)
│   │   ├── stripe.validator.ts    # Stripe (stripe SDK)
│   │   ├── kb.validator.ts        # Knowledge Base (ky HTTP)
│   │   └── slack.validator.ts     # Slack (@slack/web-api)
│   ├── schemas/
│   │   ├── github.schema.ts       # Zod schemas for GitHub responses
│   │   ├── linear.schema.ts       # Zod schemas for Linear responses
│   │   ├── n8n.schema.ts          # Zod schemas for n8n responses
│   │   ├── gcp.schema.ts          # Zod schemas for GCP responses
│   │   ├── stripe.schema.ts       # Zod schemas for Stripe responses
│   │   ├── kb.schema.ts           # Zod schemas for Knowledge Base responses
│   │   └── slack.schema.ts        # Zod schemas for Slack responses
│   └── checks/
│       ├── permission-checker.ts  # Aggregated permission analysis
│       └── latency-recorder.ts    # Circular buffer latency tracking
├── tests/
│   ├── validators/
│   │   └── github.validator.test.ts
│   └── schemas/
│       └── github.schema.test.ts
├── .env.example
├── .gitignore
├── CLAUDE.md
├── DEPLOYMENT.md
├── Dockerfile
├── package.json
└── tsconfig.json
```

## 5. API Endpoints

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| `GET` | `/health` | None | Health check for Cloud Run / LB |
| `GET` | `/api/status` | OIDC | Latest validation status per system |
| `POST` | `/api/run` | OIDC | Trigger validation run (202 Accepted) |
| `GET` | `/api/results` | OIDC | List all validation runs |
| `GET` | `/api/results/:id` | OIDC | Detailed results for a specific run |

### POST /api/run Body

```json
{
  "systems": ["github", "linear", "stripe"],
  "includeRateLimitTest": false
}
```

Both fields are optional. Omitting `systems` validates all 7 platforms.

## 6. Validated Systems

| System | Validator | SDK/Client | Checks |
|--------|-----------|-----------|--------|
| GitHub | `GitHubValidator` | Octokit | Org access, repos list, rate limits |
| Linear | `LinearValidator` | @linear/sdk | Workspace, teams, issues, viewer |
| n8n | `N8nValidator` | ky HTTP | Workflows, executions |
| GCP | `GcpValidator` | Resource Manager | Project access, IAM policy |
| Stripe | `StripeValidator` | stripe SDK | Account, charges, balance |
| Knowledge Base | `KbValidator` | ky HTTP | Health, cases |
| Slack | `SlackValidator` | @slack/web-api | auth.test, conversations, users |

## 7. Environment Variables

See `.env.example` for full list.

| Variable | Required | Purpose |
|----------|----------|---------|
| `PORT` | No (default: 5510) | Server port |
| `GITHUB_TOKEN` | No | GitHub PAT for org read access |
| `LINEAR_API_KEY` | No | Linear API key |
| `N8N_API_URL` | No | n8n instance URL |
| `N8N_API_KEY` | No | n8n API key |
| `GCP_PROJECT_ID` | No | GCP project to validate |
| `STRIPE_SECRET_KEY` | No | Stripe read-only key |
| `KB_API_URL` | No | Knowledge Base API URL |
| `KB_API_KEY` | No | Knowledge Base API key |
| `SLACK_BOT_TOKEN` | No | Slack bot token |

All credentials are optional. The validator reports which systems are configured vs not.

## 8. GCP Infrastructure

| Resource | Value |
|----------|-------|
| GCP Project | `adjudica-internal` |
| Cloud Run Service | `gbs-integration-validator` |
| Region | `us-west1` |
| Artifact Registry | `us-west1-docker.pkg.dev/adjudica-internal/cloud-run-images` |
| Cloud Scheduler | `integration-validator-daily` (every 6h) |

## 9. Security & Secrets

**CRITICAL: Never expose secrets in chat or commit them to git.**

- All credentials are injected via Cloud Run Secret Manager references
- The service is stateless; /tmp state is ephemeral and lost on cold starts
- No database connection required
- OIDC authentication protects all /api/* endpoints in production

## 10. Dev Environment

| Service | Port | URL |
|---------|------|-----|
| Validator API | 5510 | http://localhost:5510 |

Port block: 5510 (within the 5500-5599 range reserved for GBS ops tools).

## 11. Validator Pattern

Each validator extends `BaseValidator` and implements:
- `isConfigured()` — checks env vars
- `checkConnectivity()` — basic API call
- `validateSchemas()` — Zod schema validation of responses
- `checkPermissions()` — scope/permission enumeration

The base class provides `measureLatency()` and the composite `validate()` method.

## 12. State Management

In-memory circular buffer (max 100 runs) persisted to `/tmp/validation-state.json`. Latency samples persisted separately to `/tmp/validation-latency.json`. State is recovered on startup but considered ephemeral.

## 13. Testing

```bash
npm run test           # Run all unit tests
```

Tests mock external SDK calls and validate:
- Validator configuration detection
- Connectivity check behavior
- Schema validation (valid and invalid payloads)
- Permission result aggregation

## 14. Related Services

| Service | Purpose |
|---------|---------|
| gbs-operations-audit | Full operational audit tool (uses same integrations) |
| squeegee | Documentation curation (GitHub-focused) |
| glass-box-hub | Internal developer portal |

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
