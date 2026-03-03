# gbs-tools-and-resources

**Unified tools & resources monorepo — agent memory, PII redaction, legal research, MCP servers, dev utilities, security wordlists, and skills catalogs.**

---

## Project Overview

This monorepo consolidates 7 previously standalone Glass Box utility/research repositories into a single discoverable location. Each package retains its own structure, language, and build tooling — there is no unified build system at the monorepo root.

**Consolidated from individual repos on:** 2026-03-01
**Pattern follows:** `internal-tools` (absorbed command-center, glass-box-board, glass-box-hub, Squeegee on 2026-03-01)

---

## Packages

| Package | Language/Stack | Purpose | Former Repo |
|---------|---------------|---------|-------------|
| [`packages/hindsight/`](packages/hindsight/) | Python, Next.js, Rust | Agent memory system — retain, recall, reflect. Top performer on LongMemEval benchmark. | `Glass-Box-Solutions-Inc/hindsight` |
| [`packages/yevrah_terminal/`](packages/yevrah_terminal/) | Python, Groq, Cohere | Terminal legal research tool — CourtListener API with dual search (keyword + semantic) | `Glass-Box-Solutions-Inc/yevrah_terminal` |
| [`packages/phileas/`](packages/phileas/) | Java, Maven | PII/PHI redaction library — 30+ entity types, conditional redaction, encryption | `Glass-Box-Solutions-Inc/phileas` |
| [`packages/awesome-agent-skills/`](packages/awesome-agent-skills/) | Documentation | Curated catalog of 180+ Agent Skills for AI coding assistants | `Glass-Box-Solutions-Inc/awesome-agent-skills` |
| [`packages/mcp-servers/`](packages/mcp-servers/) | Python, Node.js | Unified MCP server collection — configs, custom servers, templates | `Glass-Box-Solutions-Inc/mcp-servers` |
| [`packages/merus-test-data-generator/`](packages/merus-test-data-generator/) | Python 3.12, reportlab, Faker, Click | Generates 20 realistic WC test cases with ~700 templated PDFs, populates in MerusCase | `Glass-Box-Solutions-Inc/merus-test-data-generator` |
| [`packages/SecLists-GBS-Branch/`](packages/SecLists-GBS-Branch/) | Security wordlists | Fork of danielmiessler/SecLists (placeholder — repo too large to include directly) | `Glass-Box-Solutions-Inc/SecLists-GBS-Branch` |

---

## Tech Stack

| Package | Stack |
|---------|-------|
| **hindsight** | Python/FastAPI, Next.js, PostgreSQL/pgvector, Rust |
| **yevrah_terminal** | Python 3.x, Groq API, Cohere API, CourtListener API |
| **phileas** | Java 11+, Maven, JUnit |
| **awesome-agent-skills** | Markdown (no build) |
| **mcp-servers** | Python, Node.js/TypeScript, MCP SDK |
| **merus-test-data-generator** | Python 3.12, reportlab, Faker, Click, SQLite |
| **SecLists-GBS-Branch** | Text files (security wordlists) |

---

## Commands

Each package builds independently. See each package's own README.md or CLAUDE.md for build/run/test commands.

### Quick navigation

```bash
# Jump to a package
cd packages/hindsight/
cd packages/yevrah_terminal/
cd packages/phileas/
cd packages/mcp-servers/
cd packages/merus-test-data-generator/
```

### Package-specific tests

```bash
# hindsight (Python + Next.js)
cd packages/hindsight && pytest

# yevrah_terminal (Python)
cd packages/yevrah_terminal && pytest

# phileas (Java/Maven)
cd packages/phileas && mvn test

# mcp-servers (varies by server)
cd packages/mcp-servers/servers/[server-name] && npm test
```

---

## Architecture

```
gbs-tools-and-resources/
├── CLAUDE.md                         # This file
├── README.md                         # Human-facing overview
├── .gitignore                        # Root gitignore (node_modules, __pycache__, target/, etc.)
└── packages/
    ├── hindsight/                    # Agent memory system (Python/FastAPI + Next.js + Rust)
    ├── yevrah_terminal/              # Terminal legal research tool (Python)
    ├── phileas/                      # PII/PHI redaction library (Java/Maven)
    ├── awesome-agent-skills/         # Agent skills catalog (Markdown docs)
    ├── mcp-servers/                  # MCP server collection (Python + Node.js)
    │   ├── servers/
    │   │   ├── kb-api-mcp/          # Knowledge base API MCP server
    │   │   ├── kb-db-mcp/           # Knowledge base DB MCP server
    │   │   ├── social-media-mcp/    # Social media MCP server
    │   │   └── wc-paralegal-mcp/    # WC paralegal MCP server
    │   ├── configs/                  # MCP client configurations
    │   └── scripts/                  # Setup/utility scripts
    ├── merus-test-data-generator/    # WC test case PDF generator (Python 3.12)
    └── SecLists-GBS-Branch/          # Security wordlists reference (placeholder)
```

---

## Port Registry

| Package | Port Range | Notes |
|---------|-----------|-------|
| hindsight | 4600–4699 | FastAPI backend: 4600, Next.js frontend: 4601 |
| yevrah_terminal | 5200–5299 | Terminal app, no persistent server |
| mcp-servers | Varies by server | See mcp-servers/configs/ |

---

## Environment Variables

See each package's own `.env.example` or `CLAUDE.md` for required environment variables.

---

## Deployment

These packages are research tools, dev utilities, and internal infrastructure — not deployed as production Cloud Run services. See individual package READMEs for deployment notes.

---

## Migration History

| Date | Action |
|------|--------|
| 2026-03-01 | Consolidated 7 standalone repos into this monorepo |
| 2026-03-01 | All source repos archived on GitHub with redirect notices |

**Archived source repos:**
- `Glass-Box-Solutions-Inc/hindsight` → `packages/hindsight/`
- `Glass-Box-Solutions-Inc/yevrah_terminal` → `packages/yevrah_terminal/`
- `Glass-Box-Solutions-Inc/phileas` → `packages/phileas/`
- `Glass-Box-Solutions-Inc/awesome-agent-skills` → `packages/awesome-agent-skills/`
- `Glass-Box-Solutions-Inc/mcp-servers` → `packages/mcp-servers/`
- `Glass-Box-Solutions-Inc/merus-test-data-generator` → `packages/merus-test-data-generator/`
- `Glass-Box-Solutions-Inc/SecLists-GBS-Branch` → `packages/SecLists-GBS-Branch/` (placeholder only)

---

## Documentation Hub Reference

For centralized business, legal, marketing, and product documentation, see the [Adjudica Documentation Hub](~/Desktop/adjudica-documentation/CLAUDE.md) and the [Quick Index](~/Desktop/adjudica-documentation/ADJUDICA_INDEX.md).

For company-wide development standards, see the main CLAUDE.md at `~/Desktop/CLAUDE.md`.

---

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
