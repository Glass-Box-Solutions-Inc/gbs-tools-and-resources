# Invoice Reconciliation Tester

Generates synthetic PioneerDev CSV fixtures, Linear/GitHub data, validates matching algorithm accuracy (precision/recall/F1), and tests confidence scoring and variance classification. Owned by GBS, built following GBS engineering conventions.

## 1. Project Overview

The invoice reconciliation tester is a Fastify 5 Cloud Run service that validates the accuracy of the invoice-to-work-item matching algorithm used by `gbs-operations-audit`. It generates synthetic test data, runs matching and scoring algorithms against ground-truth datasets, and reports precision, recall, and F1 metrics. Results are persisted to PostgreSQL for trend tracking.

## 2. Tech Stack

| Layer | Technology |
|-------|-----------|
| Server | Fastify 5 (ESM TypeScript) |
| ORM | Prisma 6 (PostgreSQL) |
| Validation | Zod |
| Test Data | @faker-js/faker |
| CSV | PapaParse |
| Logging | Pino (via Fastify) |
| Unit Tests | Vitest |
| Hosting | GCP Cloud Run |

## 3. Commands

```bash
npm run dev            # Start dev server (tsx watch)
npm run build          # TypeScript compile
npm run start          # Run production build
npm run typecheck      # Type check without emit
npm run lint           # ESLint
npm run format         # Prettier
npm run test           # Vitest unit tests
npm run db:generate    # Prisma client generation
npm run db:migrate     # Apply migrations
npm run db:studio      # Prisma Studio
```

## 4. Architecture

```
invoice-reconciliation-tester/
├── src/
│   ├── server.ts                  # Fastify entry point
│   ├── runner.ts                  # Test suite orchestrator
│   ├── lib/
│   │   ├── env.ts                 # Zod env validation
│   │   └── db.ts                  # Prisma singleton
│   ├── types/
│   │   └── index.ts               # Shared type definitions
│   ├── generators/
│   │   ├── csv-fixture.generator.ts     # Synthetic CSV generation
│   │   ├── linear-fixture.generator.ts  # Synthetic Linear issues
│   │   └── github-fixture.generator.ts  # Synthetic GitHub PRs
│   ├── matchers/
│   │   ├── accuracy-scorer.ts           # Precision/recall/F1
│   │   ├── confidence-validator.ts      # Confidence score validation
│   │   └── variance-classifier.ts       # Variance type classification
│   ├── test-suites/
│   │   ├── known-good-matches.ts        # Ground truth correct matches
│   │   ├── known-bad-matches.ts         # Ground truth non-matches
│   │   └── edge-cases.ts               # Edge case scenarios
│   └── routes/
│       ├── health.ts              # GET /health
│       ├── status.ts              # GET /api/status
│       ├── run.ts                 # POST /api/run
│       ├── results.ts             # GET /api/results, GET /api/results/:id
│       └── generate.ts            # POST /api/generate
├── prisma/
│   └── schema.prisma              # TestRun + TestResult tables
├── tests/
│   ├── generators/
│   │   └── csv-fixture.test.ts
│   └── matchers/
│       └── accuracy-scorer.test.ts
├── Dockerfile                     # Multi-stage Alpine build
├── CLAUDE.md
├── DEPLOYMENT.md
├── package.json
├── tsconfig.json
└── vitest.config.ts
```

## 5. API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/health` | None | Cloud Run startup/liveness probe |
| `GET` | `/api/status` | OIDC | Last N run summaries from DB |
| `POST` | `/api/run` | OIDC | Trigger test suite (202 accepted, fire-and-forget) |
| `GET` | `/api/results` | OIDC | List recent test run summaries |
| `GET` | `/api/results/:id` | OIDC | Detailed results for a specific run |
| `POST` | `/api/generate` | OIDC | Generate fixtures only (no matching) |

## 6. Environment Variables

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `PORT` | No | `5520` | HTTP port |
| `DATABASE_URL` | Yes | - | PostgreSQL connection string |
| `GITHUB_TOKEN` | No | - | GitHub PAT for live validation |
| `LINEAR_API_KEY` | No | - | Linear API key for live validation |

## 7. Database Schema

Two tables in the `irt_dev` database:

- `test_runs` -- tracks each test execution (status, config, summary)
- `test_results` -- individual test case results with metrics and errors

## 8. Test Suites

| Suite | Cases | What It Tests |
|-------|-------|---------------|
| `csv-fixture-generation` | 8 | CSV generation across column variants, edge cases, unicode, BOM |
| `known-good-matches` | 20 | Confidence scoring for exact/near-exact matches |
| `known-bad-matches` | 15 | Confidence scoring for intentional non-matches |
| `edge-cases-confidence` | 15 | Confidence with empty/unicode/long/special inputs |
| `variance-classification` | 10 | Variance type (hours/rate/unmatched) classification |
| `accuracy-metrics-validation` | 10 | Precision/recall/F1 computation correctness |

## 9. Matching Algorithm Reference

Confidence scoring ranges:
- **Exact match** (normalized text identical): confidence >= 0.95
- **Containment match** (one text contains the other): confidence 0.85-0.99
- **Keyword match** (shared tokens): confidence 0.20-0.94
- **No match**: confidence < 0.20

Variance types:
- `hours_mismatch` -- invoice hours differ from tracked hours
- `rate_mismatch` -- invoice rate differs from expected rate
- `unmatched_invoice` -- invoice line with no matching work item
- `unmatched_work` -- tracked work with no corresponding invoice line

## 10. Dev Environment

| Service | Port | URL |
|---------|------|-----|
| API | 5520 | http://localhost:5520 |
| PostgreSQL | 5441 | localhost:5441 |

Port block: 5520-5529 (reserved for this service).

## 11. Security

- All endpoints except `/health` require OIDC authentication in production (Cloud Run `--no-allow-unauthenticated`)
- No secrets are stored in code or configuration files
- Database credentials are provided via environment variables
- GitHub/Linear tokens are optional and only used for live validation

## 12. Deployment

See `DEPLOYMENT.md` for GCP infrastructure setup and deployment commands.

| Resource | Value |
|----------|-------|
| GCP Project | `glassbox-irt` |
| Region | `us-central1` |
| Cloud Run service | `invoice-reconciliation-tester` |
| Container image | `gcr.io/glassbox-irt/invoice-reconciliation-tester` |

## 13. Related Services

- **gbs-operations-audit** -- the production audit tool whose reconciliation logic this service validates
- **Squeegee** -- documentation curation pipeline (shared Cloud Run patterns)

## 14. Development Notes

- ESM TypeScript throughout (`"type": "module"` in package.json)
- All imports use `.js` extension for Node.js ESM compatibility
- `import type` used for type-only imports
- Fire-and-forget pattern via `setImmediate()` for async test execution
- Prisma generates types at build time; run `npm run db:generate` after schema changes

---

## Root Standards Reference

For company-wide development standards, see the main CLAUDE.md at `~/Desktop/CLAUDE.md`.

For centralized business, legal, marketing, and product documentation, see the [Adjudica Documentation Hub](~/Desktop/adjudica-documentation/CLAUDE.md) and the [Quick Index](~/Desktop/adjudica-documentation/ADJUDICA_INDEX.md).

---

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
