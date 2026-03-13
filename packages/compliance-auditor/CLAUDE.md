# Compliance Auditor

**SOC2 + HIPAA compliance scanning service for Glass Box Solutions repositories.**

---

## ⚠️ CRITICAL GUARDRAILS (READ FIRST)

1. **NEVER push without permission** — Even small fixes require express user permission. No exceptions.
2. **NEVER expose secrets** — No API keys, tokens, credentials in git, logs, or conversation.
3. **NEVER force push or skip tests** — 100% passing tests required.
4. **ALWAYS read parent CLAUDE.md** — `~/CLAUDE.md` for org-wide standards.
5. **ALWAYS use Definition of Ready** — 100% clear requirements before implementation.

---

SOC2 + HIPAA compliance scanning service for Glass Box Solutions repositories. Performs static analysis of source code across the GBS GitHub org to detect compliance violations, generates structured reports, and persists scan history for audit trail purposes.

## Project Overview

Compliance Auditor is a Fastify 5 Cloud Run service that clones GBS repositories, runs a suite of compliance analyzers against the source code, and produces findings with severity levels, remediation guidance, and code snippets. It supports both SOC2 and HIPAA frameworks and can scan individual repos or the entire org.

## Tech Stack

| Layer | Technology |
|-------|------------|
| **Runtime** | Node.js 20 (Alpine) |
| **Server** | Fastify 5 |
| **ORM** | Prisma 6 (PostgreSQL) |
| **GitHub API** | @octokit/rest |
| **Validation** | Zod |
| **AST Analysis** | TypeScript compiler API (runtime) |
| **Container** | Docker (multi-stage Alpine build) |
| **Hosting** | GCP Cloud Run |
| **Tests** | Vitest |

## Commands

```bash
# Development
npm run dev            # Start with tsx watch (hot reload)
npm run start          # Run production build
npm run build          # TypeScript compilation
npm run typecheck      # Type check without emitting

# Code quality
npm run lint           # ESLint
npm run format         # Prettier

# Tests
npm run test           # Vitest unit tests

# Database
npm run db:generate    # Prisma client generation
npm run db:migrate     # Apply migrations
npm run db:studio      # Prisma Studio GUI
```

## Architecture

```
compliance-auditor/
├── src/
│   ├── server.ts                      # Fastify Cloud Run entrypoint
│   ├── types/
│   │   └── index.ts                   # Shared TypeScript types
│   ├── lib/
│   │   ├── env.ts                     # Zod environment validation
│   │   └── db.ts                      # Prisma client singleton
│   ├── analyzers/                     # Compliance rule analyzers
│   │   ├── base.analyzer.ts           # Abstract base class
│   │   ├── parameterized-query.analyzer.ts  # SQL injection detection
│   │   ├── phi-leakage.analyzer.ts    # PHI in code/logs
│   │   ├── debug-logging.analyzer.ts  # Debug output in production
│   │   ├── field-encryption.analyzer.ts    # PHI encryption verification
│   │   ├── error-sanitization.analyzer.ts  # Stack trace leakage
│   │   ├── ssl-connection.analyzer.ts      # DB SSL/TLS verification
│   │   └── audit-completeness.analyzer.ts  # CRUD audit trail checks
│   ├── scanners/
│   │   ├── codebase-scanner.ts        # Git clone + file discovery + orchestration
│   │   └── pattern-matcher.ts         # Regex + TypeScript AST utilities
│   ├── reporters/
│   │   ├── json-reporter.ts           # Structured JSON reports
│   │   └── markdown-reporter.ts       # Human-readable Markdown reports
│   └── routes/
│       ├── health.ts                  # GET /health (no auth)
│       ├── status.ts                  # GET /api/status
│       ├── run.ts                     # POST /api/run (202 accepted)
│       └── reports.ts                 # GET /api/reports, /api/reports/:id
├── prisma/
│   └── schema.prisma                  # ComplianceScan + ComplianceFinding models
├── tests/
│   ├── analyzers/
│   │   └── phi-leakage.test.ts
│   └── scanners/
│       └── pattern-matcher.test.ts
├── .env.example
├── Dockerfile
├── CLAUDE.md
├── DEPLOYMENT.md
├── package.json
└── tsconfig.json
```

## API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/health` | None | Cloud Run startup/liveness probe |
| `GET` | `/api/status` | OIDC | Last scan summary from database |
| `POST` | `/api/run` | OIDC | Trigger compliance scan (202 accepted, fire-and-forget) |
| `GET` | `/api/reports` | OIDC | List all completed scans |
| `GET` | `/api/reports/:id` | OIDC | Full scan detail with findings (JSON) |
| `GET` | `/api/reports/:id/markdown` | OIDC | Markdown-formatted compliance report |

### POST /api/run Request Body

```json
{
  "repos": ["adjudica-ai-app", "squeegee"],
  "analyzers": ["parameterized-query", "phi-leakage"],
  "framework": "both"
}
```

All fields are optional. Omitting `repos` scans the entire org. Omitting `analyzers` runs all analyzers. Framework defaults to `"both"`.

## Environment Variables

| Variable | Source | Description |
|----------|--------|-------------|
| `PORT` | Cloud Run (auto) | HTTP port (default: 5530) |
| `DATABASE_URL` | Secret Manager | PostgreSQL connection string |
| `GITHUB_TOKEN` | Secret Manager | GitHub PAT for repo cloning |
| `GITHUB_ORG` | Cloud Run env var | Target org (default: Glass-Box-Solutions-Inc) |

## Analyzers

| Analyzer | Framework | Severity | What it detects |
|----------|-----------|----------|-----------------|
| `parameterized-query` | Both | CRITICAL | Raw SQL string concatenation / template interpolation |
| `phi-leakage` | HIPAA | CRITICAL/HIGH | SSNs, DOB, MRN, patient names in code/logs |
| `debug-logging` | SOC2 | MEDIUM/HIGH | console.log/debug in production, sensitive data in logs |
| `field-encryption` | HIPAA | HIGH | PHI fields stored without encryption |
| `error-sanitization` | SOC2 | HIGH/CRITICAL | Stack traces and raw errors in HTTP responses |
| `ssl-connection` | Both | HIGH/CRITICAL | Database connections without SSL/TLS |
| `audit-completeness` | SOC2 | MEDIUM | CRUD operations without audit trail logging |

## Database Schema

Two tables in the `compliance_scans` / `compliance_findings` namespace:

- **ComplianceScan** — scan metadata (status, framework, repos, summary)
- **ComplianceFinding** — individual findings (analyzer, severity, file, line, snippet, remediation)

## Security

- Git clone uses `stdio: "pipe"` to prevent token leakage in process output
- The GITHUB_TOKEN is never logged or included in error messages
- All secrets are injected via environment variables (Secret Manager in production)
- Cloud Run OIDC protects all `/api/*` endpoints
- Error responses are sanitized (no stack traces to clients)

## Dev Notes

- TypeScript is in `dependencies` (not just devDependencies) because the TypeScript compiler API (`ts.createSourceFile()`) is used at runtime for AST-level static analysis
- ESM throughout (`"type": "module"` in package.json, `.js` extensions in imports)
- Analyzers follow the abstract base class pattern from gbs-operations-audit's BaseAuditor
- Scans run as fire-and-forget background tasks (setImmediate) so the API responds 202 immediately
- Repos are cloned to `/tmp` with `--depth=1` and cleaned up after scanning
- Files larger than 256KB are skipped (likely minified/generated bundles)

---

## Root Standards Reference

For company-wide development standards, see the [Root CLAUDE.md](https://github.com/Glass-Box-Solutions-Inc/adjudica-documentation/blob/main/engineering/ROOT_CLAUDE.md).

For centralized business, legal, marketing, and product documentation, see the [Adjudica Documentation Hub](~/Desktop/adjudica-documentation/CLAUDE.md) and the [Quick Index](~/Desktop/adjudica-documentation/ADJUDICA_INDEX.md).

---

## ⚠️ GUARDRAILS REMINDER

Before ANY action, verify:

- [ ] **Push permission?** — Required for every push, no exceptions
- [ ] **Definition of Ready?** — Requirements 100% clear
- [ ] **Tests passing?** — 100% required
- [ ] **Root cause understood?** — For fixes, understand WHY first

---

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
