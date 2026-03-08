# gbs-tools-and-resources

> **Unified tools, agents, and resources monorepo** for Glass Box Solutions. Consolidates 11 packages — agent services, MCP servers, utilities, and reference libraries.

---

## Agent Services

| Package | Stack | Purpose | Status |
|---------|-------|---------|--------|
| [`packages/spectacles/`](packages/spectacles/) | Python 3.12, FastAPI, Playwright, Gemini | Browser automation + documentation intelligence curator | Production (Cloud Run) |
| [`packages/merus-expert/`](packages/merus-expert/) | Python 3.12, FastAPI, Claude, Gemini | MerusCase domain agent — 13 tools, SSE streaming | Production (Cloud Run) |
| [`packages/agent-swarm/`](packages/agent-swarm/) | NestJS 11, TypeScript, Socket.io | DAG-based multi-agent task orchestration | Reference copy from Glassy PAI |
| [`packages/agentic-debugger/`](packages/agentic-debugger/) | Node.js, Claude Code, GitHub Actions | Automated CI test failure debugging agent | Template for adoption |

## Utilities & Libraries

| Package | Stack | Purpose | Status |
|---------|-------|---------|--------|
| [`packages/hindsight/`](packages/hindsight/) | Python/FastAPI, Next.js, pgvector, Rust | Agent memory system (retain/recall/reflect) | Active |
| [`packages/mcp-servers/`](packages/mcp-servers/) | Python, Node.js, MCP SDK | MCP server collection (kb-api, kb-db, wc-paralegal, social-media) | Production |
| [`packages/phileas/`](packages/phileas/) | Java 11+, Maven | PII/PHI redaction library (30+ entity types) | Production |
| [`packages/yevrah_terminal/`](packages/yevrah_terminal/) | Python 3.x, Groq, Cohere | Terminal legal research (keyword + semantic search) | Active |
| [`packages/merus-test-data-generator/`](packages/merus-test-data-generator/) | Python 3.12, reportlab, Faker | WC test case generator (~700 templated PDFs) | Active |

## Reference

| Package | Purpose |
|---------|---------|
| [`packages/awesome-agent-skills/`](packages/awesome-agent-skills/) | Curated catalog of 180+ AI agent skills |
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
| `Glass-Box-Solutions-Inc/Spectacles` | `packages/spectacles/` | Full copy |
| `Glass-Box-Solutions-Inc/merus-expert` | `packages/merus-expert/` | Full copy |
| `glassy-app-production` `backend/src/modules/agent-swarm/` | `packages/agent-swarm/` | Reference copy |
| `glassy-app-production` `scripts/debug-agent.mjs` | `packages/agentic-debugger/` | Template copy |

---

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
