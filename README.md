# gbs-tools-and-resources

> **Unified tools & resources monorepo** — agent memory, PII redaction, legal research, MCP servers, dev utilities, security wordlists, and skills catalogs.

A Glass Box Solutions, Inc. monorepo consolidating 7 standalone utility and research repositories into a single discoverable location. Follows the pattern established by [`gbs-internal-tools`](https://github.com/Glass-Box-Solutions-Inc/gbs-internal-tools) (consolidated 2026-03-01).

---

## Packages

| Package | Stack | Description |
|---------|-------|-------------|
| [`packages/hindsight/`](packages/hindsight/) | Python, Next.js, Rust | **Agent memory system** — retain, recall, reflect. Top performer on LongMemEval benchmark. |
| [`packages/yevrah_terminal/`](packages/yevrah_terminal/) | Python, Groq, Cohere | **Terminal legal research** — CourtListener API with dual search (keyword + semantic) |
| [`packages/phileas/`](packages/phileas/) | Java, Maven | **PII/PHI redaction library** — 30+ entity types, conditional redaction, encryption |
| [`packages/awesome-agent-skills/`](packages/awesome-agent-skills/) | Docs | **Agent skills catalog** — curated 180+ Agent Skills for AI coding assistants |
| [`packages/mcp-servers/`](packages/mcp-servers/) | Python, Node.js | **MCP server collection** — configs, custom servers (knowledge-base, social-media, WC paralegal), templates |
| [`packages/merus-test-data-generator/`](packages/merus-test-data-generator/) | Python 3.12 | **WC test data generator** — 20 realistic Workers' Comp cases with ~700 templated PDFs |
| [`packages/SecLists-GBS-Branch/`](packages/SecLists-GBS-Branch/) | Wordlists | **Security wordlists** — GBS fork of danielmiessler/SecLists (reference placeholder) |

---

## Getting Started

Each package is independent — no monorepo-level build tool is required.

```bash
# Clone the monorepo
git clone https://github.com/Glass-Box-Solutions-Inc/gbs-tools-and-resources.git

# Navigate to a specific package
cd packages/hindsight
cd packages/mcp-servers
cd packages/phileas
```

See each package's own `README.md` for setup, install, and run instructions.

---

## Migration History

These packages were consolidated from 7 standalone repositories on 2026-03-01. The source repos are archived on GitHub and redirect to their corresponding `packages/` directory here.

| Former Repo | Now At |
|------------|--------|
| `Glass-Box-Solutions-Inc/hindsight` | `packages/hindsight/` |
| `Glass-Box-Solutions-Inc/yevrah_terminal` | `packages/yevrah_terminal/` |
| `Glass-Box-Solutions-Inc/phileas` | `packages/phileas/` |
| `Glass-Box-Solutions-Inc/awesome-agent-skills` | `packages/awesome-agent-skills/` |
| `Glass-Box-Solutions-Inc/mcp-servers` | `packages/mcp-servers/` |
| `Glass-Box-Solutions-Inc/merus-test-data-generator` | `packages/merus-test-data-generator/` |
| `Glass-Box-Solutions-Inc/SecLists-GBS-Branch` | `packages/SecLists-GBS-Branch/` (placeholder) |

---

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
