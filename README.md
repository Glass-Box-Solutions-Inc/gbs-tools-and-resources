# gbs-tools-and-resources

> **Unified tools, agents, and resources monorepo** for Glass Box Solutions. Consolidates 16 packages — agent services, operations audit tools, MCP servers, utilities, and reference libraries.

---

## Agent Services

| Package | Stack | Purpose | Status |
|---------|-------|---------|--------|
| [`packages/spectacles/`](packages/spectacles/) | Python 3.12, FastAPI, Playwright, Gemini | Browser automation + documentation intelligence curator | Production (Cloud Run) |
| [`packages/merus-expert/`](packages/merus-expert/) | Python 3.12, FastAPI, Claude, Gemini | MerusCase domain agent — 13 tools, SSE streaming | Production (Cloud Run) |
| [`packages/agent-swarm/`](packages/agent-swarm/) | NestJS 11, TypeScript, Socket.io | DAG-based multi-agent task orchestration | Standalone NestJS library module |
| [`packages/agentic-debugger/`](packages/agentic-debugger/) | Node.js, Claude Code, GitHub Actions | Automated CI test failure debugging agent | Standalone CI debugging agent |

## Operations & Audit

| Package | Stack | Purpose | Status |
|---------|-------|---------|--------|
| [`packages/compliance-auditor/`](packages/compliance-auditor/) | Node.js 20, Fastify 5, Prisma, Zod | SOC2 + HIPAA compliance code scanning across GBS repos | Cloud Run |
| [`packages/gbs-integration-validator/`](packages/gbs-integration-validator/) | Node.js 20, Fastify 5, Zod | API integration validation (GitHub, Linear, n8n, GCP, Stripe, KB, Slack) | Cloud Run |
| [`packages/invoice-reconciliation-tester/`](packages/invoice-reconciliation-tester/) | Node.js 20, Fastify 5, Prisma, Faker | Invoice-to-work-item matching algorithm validation (precision/recall/F1) | Cloud Run |

## Utilities & Libraries

| Package | Stack | Purpose | Status |
|---------|-------|---------|--------|
| [`packages/hindsight/`](packages/hindsight/) | Python/FastAPI, Next.js, pgvector, Rust | Agent memory system (retain/recall/reflect) | Active |
| [`packages/mcp-servers/`](packages/mcp-servers/) | Python, Node.js, MCP SDK | MCP server collection (kb-api, kb-db, wc-paralegal, social-media) | Production |
| [`packages/phileas/`](packages/phileas/) | Java 11+, Maven | PII/PHI redaction library (30+ entity types) | Production |
| [`packages/yevrah_terminal/`](packages/yevrah_terminal/) | Python 3.x, Groq, Cohere | Terminal legal research (keyword + semantic search) | Active |
| [`packages/merus-test-data-generator/`](packages/merus-test-data-generator/) | Python 3.12, reportlab, Faker | WC test case generator (10,000+ templated PDFs across 97+ subtypes; AMA Guides 5th Ed. impairment content, 30 edge case scenarios, Browserless MerusCase batch integration) | Active |

## Reference

| Package | Purpose |
|---------|---------|
| [`packages/awesome-agent-skills/`](packages/awesome-agent-skills/) | Curated catalog of 180+ AI agent skills |
| [`packages/awesome-claude-code/`](packages/awesome-claude-code/) | Curated list of skills, hooks, slash-commands, agents, and plugins for Claude Code |
| [`packages/ui-ux-pro-max-skill/`](packages/ui-ux-pro-max-skill/) | AI design intelligence skill for professional UI/UX across platforms |
| [`packages/SecLists-GBS-Branch/`](packages/SecLists-GBS-Branch/) | Security testing wordlists (placeholder) |

---

## Port Registry

| Package | Port Block | Notes |
|---------|-----------|-------|
| spectacles | 3700–3799 | FastAPI: 3700, Production: Cloud Run |
| merus-expert | 4300–4399 | FastAPI: 4300, Production: Cloud Run |
| hindsight | 4600–4699 | FastAPI: 4601, Next.js: 4600 |
| mcp-servers | 4900–4999 | Varies by server (MCP protocol) |
| yevrah_terminal | 5200–5299 | CLI tool, no persistent server |
| agent-swarm | — | Library (runs within Glassy on 3800–3899) |
| agentic-debugger | — | GitHub Actions only (no server) |
| gbs-integration-validator | 5500–5599 | Fastify: 5510, Production: Cloud Run |
| invoice-reconciliation-tester | 5500–5599 | Fastify: 5520, Production: Cloud Run |
| compliance-auditor | 5500–5599 | Fastify: 5530, Production: Cloud Run |

---

## Deployment

> **All packages deploy from this monorepo** (canonical source). See [`DEPLOYMENT_MODEL.md`](DEPLOYMENT_MODEL.md) for full details.

| Package | Deploy Method | Notes |
|---------|--------------|-------|
| **spectacles** | Cloud Build → Cloud Run | `packages/spectacles/cloudbuild.yaml` |
| **merus-expert** | Cloud Build → Cloud Run | `packages/merus-expert/cloudbuild.yaml` |
| **agent-swarm** | `npm install @gbs/agent-swarm` | Standalone NestJS library module |
| **agentic-debugger** | Copy script + workflow into target repo | Config-driven via `.agentic-debugger.json` |
| **compliance-auditor** | Cloud Build → Cloud Run | `packages/compliance-auditor/cloudbuild.yaml` |
| **gbs-integration-validator** | Cloud Build → Cloud Run | `packages/gbs-integration-validator/cloudbuild.yaml` |
| **invoice-reconciliation-tester** | Cloud Build → Cloud Run | `packages/invoice-reconciliation-tester/cloudbuild.yaml` |
| **hindsight** | Docker / local | — |
| **mcp-servers** | Per-server (MCP protocol) | — |
| **phileas** | Maven JAR | — |

---

## Getting Started

Each package is independent — no monorepo-level build tool is required.

```bash
# Clone the monorepo
git clone https://github.com/Glass-Box-Solutions-Inc/gbs-tools-and-resources.git

# Navigate to a specific package
cd packages/spectacles
cd packages/merus-expert
cd packages/hindsight
cd packages/mcp-servers
```

See each package's own `README.md` for setup, install, and run instructions.

---

## Migration History

| Date | Action |
|------|--------|
| 2026-03-01 | Consolidated 7 standalone repos into this monorepo |
| 2026-03-08 | Added 4 agent packages (spectacles, merus-expert, agent-swarm, agentic-debugger) |
| 2026-03-08 | Made all 4 agent packages canonical standalone — monorepo is now the deployment source |
| 2026-03-09 | Added 3 operations audit packages (compliance-auditor, gbs-integration-validator, invoice-reconciliation-tester) |
| 2026-03-09 | Added 2 reference packages (awesome-claude-code, ui-ux-pro-max-skill) from personal repos |

**Archived source repos (2026-03-01):**

| Former Repo | Now At |
|------------|--------|
| `Glass-Box-Solutions-Inc/hindsight` | `packages/hindsight/` |
| `Glass-Box-Solutions-Inc/yevrah_terminal` | `packages/yevrah_terminal/` |
| `Glass-Box-Solutions-Inc/phileas` | `packages/phileas/` |
| `Glass-Box-Solutions-Inc/awesome-agent-skills` | `packages/awesome-agent-skills/` |
| `Glass-Box-Solutions-Inc/mcp-servers` | `packages/mcp-servers/` |
| `Glass-Box-Solutions-Inc/merus-test-data-generator` | `packages/merus-test-data-generator/` |
| `Glass-Box-Solutions-Inc/SecLists-GBS-Branch` | `packages/SecLists-GBS-Branch/` (placeholder) |

**Agent consolidation (2026-03-08):**

| Source | Now At | Type |
|--------|--------|------|
| `Glass-Box-Solutions-Inc/Spectacles` | `packages/spectacles/` | Canonical (standalone repo archived) |
| `Glass-Box-Solutions-Inc/merus-expert` | `packages/merus-expert/` | Canonical (standalone repo archived) |
| `glassy-app-production` agent-swarm module | `packages/agent-swarm/` | Fork — standalone GBS resource (Glassy copy stays canonical for Glassy) |
| `glassy-app-production` debug-agent script | `packages/agentic-debugger/` | Fork — standalone GBS resource (Glassy copy stays canonical for Glassy) |

---

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
