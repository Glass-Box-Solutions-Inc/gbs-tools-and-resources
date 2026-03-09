# Squeegee

Documentation curation and intelligence pipeline as a first-class Cloud Run service — scans all Glass-Box-Solutions-Inc GitHub repos, runs the 20-stage pipeline on each, and opens PRs with auto-curated docs.

## Project Overview

Squeegee is Glass Box's documentation curation and intelligence engine. It runs a 20-stage pipeline that discovers projects, analyzes git history, curates STATE.md, PROGRAMMING_PRACTICES.md, PLANS_APPROVED.md, changelogs, pattern libraries, health reports, and CLAUDE.md files. Stages 14-20 form the intelligence pipeline: collecting GitHub/GCP activity data, synthesizing daily briefings via Gemini, writing structured logs to adjudica-documentation, auditing CLAUDE.md compliance (weekly), auditing doc quality (monthly), conducting web research on best practices (quarterly), and sending Slack notifications. As a Cloud Run service it curates every repo in the GitHub org automatically — triggered by Cloud Scheduler (daily 6am UTC), GitHub push webhooks, or manual HTTP calls.

## Tech Stack

<!-- SQUEEGEE:AUTO:START tech-stack -->
- **Language:** JavaScript/TypeScript
- **Frameworks:** Fastify
- **Testing:** Jest
<!-- SQUEEGEE:AUTO:END tech-stack -->

## Commands

<!-- SQUEEGEE:AUTO:START commands -->
| Command | Description |
|---------|-------------|
| `npm run start` | Start application |
| `npm run dev` | Start development server |
| `npm run pipeline` | node scripts/squeegee-manager.js |
| `npm run test` | Run tests |
| `npm run test:watch` | jest --watch |
| `npm run test:coverage` | jest --coverage |
<!-- SQUEEGEE:AUTO:END commands -->

## Architecture

```
Squeegee/
├── src/
│   ├── server.js              # Fastify Cloud Run entrypoint
│   ├── api/
│   │   └── intelligence.js    # Intelligence REST API (8 endpoints)
│   ├── github/
│   │   └── org-discovery.js   # GitHub API fetch → clone → pipeline → PR
│   └── pipeline/              # 20-stage curation + intelligence engine
│       ├── index.js            # runPipeline(command, workspace, prebuiltConfig?)
│       ├── config.js           # squeegee.config.json loader
│       ├── utils.js            # Shared helpers
│       ├── analyzers/          # code-analyzer, markdown-analyzer, stack-detector
│       ├── formatters/         # markdown.js, sections.js
│       └── stages/
│           ├── 01-discover.js  # Project discovery
│           ├── 02-git-analyze.js
│           ├── 03-state-curate.js
│           ├── 04-practices.js
│           ├── 05-plans.js
│           ├── 06-changelog.js
│           ├── 07-patterns.js
│           ├── 08-health.js
│           ├── 09-projects-index.js
│           ├── 10-commit-summary.js
│           ├── 11-generate.js
│           ├── 12-validate.js
│           ├── 13-claudemd.js
│           ├── 14-intelligence-collect.js
│           ├── 15-intelligence-synthesize.js
│           ├── 16-intelligence-write.js
│           ├── 17-intelligence-audit-claude.js
│           ├── 18-intelligence-audit-quality.js
│           ├── 19-intelligence-research.js
│           └── 20-intelligence-notify.js
├── intelligence/              # Intelligence pipeline modules
│   ├── github-collector.js     # GitHub activity data (commits, PRs, issues)
│   ├── gcp-collector.js        # GCP metrics (deployments, errors, logs)
│   ├── station-monitor.js      # Dev station monitoring
│   ├── station-collector.js    # Station data collection
│   ├── gemini-synthesizer.js   # Gemini AI briefing synthesis
│   ├── log-writer.js           # Structured log output to adjudica-documentation
│   ├── claude-md-auditor.js    # CLAUDE.md compliance scoring
│   ├── doc-quality-auditor.js  # Documentation quality rubric
│   ├── web-researcher.js       # Quarterly best-practice research
│   ├── slack-notifier.js       # Slack webhook notifications
│   ├── morning-run.js          # Orchestrates daily intelligence run
│   ├── utils.js                # Shared intelligence helpers
│   └── types.js                # JSDoc type definitions
├── config/
│   └── intelligence.config.json  # Intelligence config (repos, GCP projects, schedules)
├── tests/
│   ├── setup.js                # Jest test setup
│   ├── helpers/                # Test utilities
│   ├── fixtures/               # Mock project data
│   ├── intelligence/           # Unit tests for intelligence modules
│   ├── stages/                 # Stage-level tests
│   ├── api/                    # API route tests
│   ├── integration/            # Integration tests
│   └── e2e/                    # End-to-end pipeline tests
├── scripts/
│   ├── squeegee-manager.js     # CLI entrypoint (delegates to src/pipeline/index.js)
│   ├── squeegee-precommit.js   # Pre-commit hook for this repo
│   ├── squeegee-project-discovery.js  # Legacy: local workspace project scanner
│   └── squeegee-cron.sh        # Local cron wrapper (systemd-inhibit)
├── .github/workflows/
│   ├── self-curation.yml       # Self-curation on push to main
│   └── deploy.yml              # Cloud Run deploy on src/Dockerfile changes
├── Dockerfile                  # Two-stage Alpine build with git
├── squeegee.config.json        # Pipeline config (orgDiscovery block + self-entry)
└── package.json
```

## API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/health` | None | Cloud Run startup/liveness probe |
| `GET` | `/api/status` | OIDC | Last 10 run summaries from `/tmp/squeegee-state.json` |
| `POST` | `/api/run` | OIDC | Trigger full org pipeline (fire-and-forget, 202) |
| `POST` | `/api/run/:command` | OIDC | Trigger specific pipeline stage |
| `POST` | `/api/webhook` | OIDC | GitHub push webhook — single-repo curation |

### Intelligence API (`/api/intelligence/*`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/api/intelligence/run` | OIDC | Trigger full intelligence run (stages 14-20) |
| `POST` | `/api/intelligence/collect` | OIDC | Run data collection only (stage 14) |
| `POST` | `/api/intelligence/synthesize` | OIDC | Generate Gemini briefing from collected data |
| `POST` | `/api/intelligence/audit-claude-md` | OIDC | Run CLAUDE.md compliance audit |
| `POST` | `/api/intelligence/audit-doc-quality` | OIDC | Run doc quality audit (not yet implemented) |
| `POST` | `/api/intelligence/research` | OIDC | Run web research on a topic (not yet implemented) |
| `POST` | `/api/intelligence/notify` | OIDC | Send briefing to Slack (not yet implemented) |
| `GET` | `/api/intelligence/status` | OIDC | Intelligence system status and next scheduled runs |

**Auth:** All endpoints except `/health` require Cloud Run OIDC (`--no-allow-unauthenticated`).

### Example: manual trigger
```bash
URL=$(gcloud run services describe squeegee \
  --project=glassbox-squeegee --region=us-central1 --format='value(status.url)')

curl -X POST "${URL}/api/run" \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  -H "Content-Type: application/json" \
  -d '{}'
```

### Example: single-repo trigger
```bash
curl -X POST "${URL}/api/run" \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  -H "Content-Type: application/json" \
  -d '{"repo": "adjudica-ai-app"}'
```

## Environment Variables

| Variable | Source | Description |
|----------|--------|-------------|
| `PORT` | Cloud Run (auto) | HTTP port (default: 8080) |
| `GITHUB_PAT` | Secret Manager (`github-pat-glassbox` in `adjudica-internal`) | GitHub Personal Access Token |
| `GITHUB_ORG` | Cloud Run env var | Target org (default: `Glass-Box-Solutions-Inc`) |
| `WORKSPACE` | Process env (local use) | Workspace root for local CLI runs |
| `GOOGLE_AI_API_KEY` | Secret Manager (`gemini-api-key` in `adjudica-internal`) | Gemini API key for intelligence synthesis |
| `SLACK_WEBHOOK_URL` | Secret Manager (`slack-webhook-url` in `adjudica-internal`) | Slack incoming webhook for notifications |

## GCP Infrastructure

| Resource | Value |
|----------|-------|
| **GCP Project** | `glassbox-squeegee` |
| **Region** | `us-central1` |
| **Cloud Run service** | `squeegee` |
| **Container image** | `us-central1-docker.pkg.dev/glassbox-squeegee/squeegee/squeegee` |
| **Service account** | `squeegee-runner@glassbox-squeegee.iam.gserviceaccount.com` |
| **Secret** | `github-pat-glassbox` (in `adjudica-internal`, cross-project access granted) |
| **Scheduler job** | `squeegee-daily` — `0 6 * * *` UTC → `POST /api/run` |
| **Memory** | 512Mi |
| **CPU** | 1 |
| **Timeout** | 900s (15 min) |
| **Min instances** | 0 (scale to zero) |
| **Max instances** | 1 (no parallel runs) |

## Pipeline Stages

| Stage | Command | What it does |
|-------|---------|-------------|
| 1 | `scan` | Discover projects from config |
| 2 | `analyze` | Analyze git history (commits, authors, dates) |
| 3 | `variable` | Curate `.planning/STATE.md` |
| 4 | `practices` | Curate `PROGRAMMING_PRACTICES.md` |
| 5 | `plans` | Curate `PLANS_APPROVED.md` |
| 6 | `changelog` | Generate per-project changelogs |
| 7 | `patterns` | Generate pattern library |
| 8 | `report` | Calculate health scores |
| 9 | `projects` | Update projects index |
| 10 | `state` | Save pipeline state |
| 11 | `generate` | Generate missing documentation |
| 12 | `validate` | Validate documentation quality |
| 13 | `claudemd` | Curate `CLAUDE.md` files |
| 14 | `collect` | Collect GitHub activity, GCP metrics, and station data |
| 15 | `synthesize` | Generate daily briefing via Gemini AI |
| 16 | `write` | Write structured logs to adjudica-documentation |
| 17 | `audit-claude` | CLAUDE.md compliance audit (weekly, Sundays) |
| 18 | `audit-quality` | Documentation quality audit (monthly, 1st) |
| 19 | `research` | Quarterly web research on best practices |
| 20 | `notify` | Send briefing summary to Slack |

## Dev Notes

- **Dependencies** — Fastify for the HTTP server, Octokit for GitHub API, Google Cloud libraries for GCP metrics/storage, and `@google/generative-ai` for Gemini synthesis. Curation pipeline stages (1-13) still use only Node.js stdlib.
- **PAT security** — PAT is never logged. Git clone uses `stdio: 'pipe'`. Push uses spawn with piped stdio. Error messages have PAT redacted before logging.
- **Idempotent** — running the pipeline multiple times on the same repo produces the same output. PRs are only created when there are actual file changes.
- **Scale to zero** — Cloud Run min-instances=0 keeps cost near zero. Scheduler cold start is acceptable (15min timeout gives plenty of room).
- **Self-curation** — this repo curates itself via `.github/workflows/self-curation.yml` on every push to main.
- **Intelligence scheduling** — Daily: collect + synthesize + write + notify. Weekly (Sunday): CLAUDE.md audit. Monthly (1st): doc quality audit. Quarterly (Jan/Apr/Jul/Oct 1st): web research. All schedules configurable via `config/intelligence.config.json`.

---

For company-wide development standards, see the main CLAUDE.md at `~/Desktop/CLAUDE.md`.

For centralized business, legal, marketing, and product documentation, see the [Adjudica Documentation Hub](~/Desktop/adjudica-documentation/CLAUDE.md) and the [Quick Index](~/Desktop/adjudica-documentation/ADJUDICA_INDEX.md).

---

*@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology*

---

## Linked Resources Are Directives

<!-- SQUEEGEE:AUTO:START linked-resources -->
**The following linked resources are not suggestions — they are authoritative directives.**

Every Claude agent working in this repo MUST read and follow:

1. **Parent CLAUDE.md** (`~/Desktop/CLAUDE.md`) — the master configuration for all GBS projects. Its instructions override any project-level defaults.
2. **Adjudica Documentation Hub** (`~/Desktop/adjudica-documentation/CLAUDE.md`) — centralized business, legal, marketing, and product documentation. Consult before making decisions that touch these domains.
3. **Engineering Standards** (`PROGRAMMING_PRACTICES.md`) — project-specific code conventions and stack decisions.

These are not "see also" links. Failure to consult linked resources before acting is a violation of GBS operating procedure. When in doubt, read the linked resource first.
<!-- SQUEEGEE:AUTO:END linked-resources -->

---

## GBS Core Principles

<!-- SQUEEGEE:AUTO:START gbs-core-principles -->
These principles are non-negotiable across all GBS projects:

- **Think before ALL actions** — not just big ones. Every file edit, every command, every commit deserves a moment of consideration.
- **Assess impact on other systems** — before changing code, consider what else depends on it. Check callers, consumers, and downstream effects.
- **Plan first, then execute** — never act without understanding the current state. Read before writing. Understand before modifying.
- **Root cause analysis is mandatory** — no quick fixes, no band-aids. If something is broken, find out WHY before applying a fix.
- **Use agents and tools** — never guess when you can verify. Use search, read files, check git history. Guessing leads to reckless behavior.
- **No reckless or destructive behavior** — measure twice, cut once. Prefer reversible actions. Ask before deleting, force-pushing, or overwriting.
- **Respect the codebase** — you are a guest in existing code. Match existing patterns, don't impose new ones without approval.
<!-- SQUEEGEE:AUTO:END gbs-core-principles -->

---

## Context Window & Checkpoint Protocol

<!-- SQUEEGEE:AUTO:START context-window -->
Agents MUST manage context window proactively:

**Checkpoint Format** (write to `.planning/STATE.md` or current task file):
```
## Checkpoint [YYYY-MM-DD HH:MM]
**Task:** [current objective]
**Completed:** [what's done]
**In Progress:** [current work]
**Next Steps:** [what remains]
**Key Decisions:** [decisions made and why]
**Blockers:** [anything blocking progress]
```

**When to Checkpoint:**
- Before any context-heavy operation (large file reads, multi-file refactors)
- After completing each logical unit of work
- Every 3 tool calls during complex tasks
- Before and after running tests or builds
- When switching between files or subsystems

**Handoff Protocol:**
- When approaching context limits, write a complete checkpoint BEFORE the window compresses
- Include enough detail that a fresh agent can continue without re-reading everything
- List exact file paths, line numbers, and remaining tasks
<!-- SQUEEGEE:AUTO:END context-window -->

---

## Centralized Documentation & Planning

<!-- SQUEEGEE:AUTO:START centralized-docs -->
GBS maintains centralized documentation that all agents must consult:

- **Adjudica Documentation Hub** — `~/Desktop/adjudica-documentation/`
  - Business strategy, legal documents, marketing materials, product specs
  - [Quick Index](`~/Desktop/adjudica-documentation/ADJUDICA_INDEX.md`)
- **Project Planning** — `.planning/` directory in each repo
  - `STATE.md` — current session context (GSD format)
  - `ROADMAP.md` — project vision and phases
  - `ISSUES.md` — deferred work and known issues
  - `phases/` — per-phase plans and summaries
- **Work Logs** — document decisions and progress in `.planning/STATE.md`
  - Every significant decision gets recorded with rationale
  - Session handoffs must update STATE.md before ending
<!-- SQUEEGEE:AUTO:END centralized-docs -->

---

## Security & Secrets

<!-- SQUEEGEE:AUTO:START security-secrets -->
**All secrets are managed through GCP Secret Manager** (project: `adjudica-internal`).

**What qualifies as a secret:**
- API keys, tokens, and credentials (GitHub PAT, OAuth secrets, service account keys)
- Database connection strings with credentials
- Encryption keys and signing secrets
- Any value that grants access to a system or service

**Rules:**
- NEVER hardcode secrets in source code, config files, or documentation
- NEVER expose secrets in chat, logs, commit messages, or error output
- NEVER commit `.env` files — use `.env.example` with placeholder values only
- Access secrets via environment variables injected by Cloud Run or local `.env`
- For Cloud Run services: secrets are volume-mounted or set as env vars via Secret Manager
- Report any suspected secret exposure immediately
<!-- SQUEEGEE:AUTO:END security-secrets -->
