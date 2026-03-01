# MCP Servers

Unified MCP (Model Context Protocol) server collection for Glass Box Solutions development tools and integrations.

## Overview

This repository centralizes all MCP server configurations, custom server implementations, and documentation for Glass Box Solutions projects. It includes GBS custom servers (KB API, KB DB, WC Paralegal, Social Media) and third-party integrations (n8n, Prisma, PostgreSQL). The Spectacles MCP lives in the Spectacles repo itself. The system uses template-based configuration generation to maintain security by keeping secrets in environment variables rather than committed files.

## Tech Stack

| Component | Technology |
|-----------|-----------|
| **Custom Servers** | Node.js/TypeScript (KB API, KB DB, WC Paralegal, Social Media) |
| **External Servers** | NPM packages, Docker containers, Git repositories |
| **Config Generation** | Bash (Linux/macOS), PowerShell (Windows) |
| **Security Model** | Environment variables with ${PLACEHOLDER} templates |
| **Package Managers** | npm, uv (Python), Docker |

## Commands

### Configuration Generation

```bash
# Linux/macOS
cd /home/vncuser/Desktop/mcp-servers
./scripts/generate-mcp-config.sh /path/to/project/.mcp.json

# Windows (PowerShell)
.\scripts\generate-mcp-config.ps1 -OutputPath "C:\path\to\project\.mcp.json"
```

### Custom Server Setup

```bash
# Social Media MCP (Node.js)
cd /home/vncuser/Desktop/mcp-servers/servers/social-media-mcp
npm install
npm run build
npm start

# FreeCAD MCP (Python)
cd /home/vncuser/Desktop/mcp-servers/servers/freecad-mcp
uv sync                        # Install dependencies
uv run python -m freecad_mcp   # Start server

# Minimal Test MCP (Python)
cd /home/vncuser/Desktop/mcp-servers/servers/minimal-test
python server.py
```

### External Server Installation

```bash
# Penpot (NPM)
npx @penpot/mcp-server

# n8n (NPM CLI)
npx n8n-mcp

# Prisma (NPM built-in)
npx prisma mcp

# PostgreSQL (Docker)
docker run crystaldba/postgres-mcp
```

## Architecture

```
/home/vncuser/Desktop/mcp-servers/
├── .mcp.json.template         # Config template with ${PLACEHOLDERS}
│
├── scripts/                   # Config generation scripts
│   ├── generate-mcp-config.sh      # Linux/macOS generator
│   └── generate-mcp-config.ps1     # Windows PowerShell generator
│
├── servers/                   # Custom MCP server implementations
│   ├── kb-api-mcp/            # TypeScript MCP wrapping KB REST API
│   │   ├── src/index.ts
│   │   └── package.json
│   │
│   ├── kb-db-mcp/             # TypeScript MCP for read-only PostgreSQL access to KB
│   │   ├── src/index.ts
│   │   ├── ASSESSMENT.md
│   │   └── package.json
│   │
│   ├── wc-paralegal-mcp/      # TypeScript MCP wrapping WC Paralegal Backend API
│   │   ├── src/index.ts
│   │   └── package.json
│   │
│   ├── social-media-mcp/      # TypeScript MCP for LinkedIn/Twitter/Mastodon
│   │   ├── src/
│   │   └── package.json
│   │
│   └── minimal-test/          # Test MCP server
│       └── server.py
│
├── configs/                   # Per-server setup documentation
│   ├── spectacles.md
│   ├── penpot.md
│   ├── n8n-mcp.md
│   ├── freecad.md
│   ├── prisma.md
│   ├── better-auth.md
│   ├── postgres-mcp.md
│   ├── social-media.md
│   └── linear.md
│
└── README.md
```

## Environment Variables

### Required for External Servers

```bash
# Penpot Integration
PENPOT_TOKEN=your-penpot-access-token

# n8n Cloud
N8N_API_KEY=your-n8n-api-key

# Spectacles (Browser Automation)
BROWSERLESS_API_TOKEN=your-browserless-token
GOOGLE_AI_API_KEY=your-google-ai-key

# PostgreSQL MCP
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=your-username
POSTGRES_PASSWORD=your-password
POSTGRES_DATABASE=your-database
```

### Required for Social Media MCP

```bash
# LinkedIn
LINKEDIN_ACCESS_TOKEN=your-linkedin-token

# Twitter/X
TWITTER_API_KEY=your-twitter-key
TWITTER_API_SECRET=your-twitter-secret
TWITTER_ACCESS_TOKEN=your-twitter-token
TWITTER_ACCESS_SECRET=your-twitter-secret

# Mastodon
MASTODON_ACCESS_TOKEN=your-mastodon-token
MASTODON_INSTANCE_URL=https://mastodon.social
```

## API Endpoints

Not applicable - MCP servers use the Model Context Protocol for communication, not REST APIs.

## Deployment

### Local Development

1. Generate `.mcp.json` from template using scripts
2. Set required environment variables in shell or `.env` files
3. Build and start custom servers as needed
4. Configure Claude Desktop or other MCP clients to use generated `.mcp.json`

### Security Best Practices

- **Never commit `.mcp.json`** - it contains secrets and tokens
- Only commit `.mcp.json.template` with `${PLACEHOLDER}` variables
- Store all secrets in environment variables
- Add `.mcp.json` to `.gitignore` in all projects
- Rotate tokens regularly
- Use minimal permission scopes for all API tokens

### MCP Server Registry

#### GBS Custom Servers (built in this repo or sibling repos)

| MCP Server | Type | Source | Purpose | Status |
|------------|------|--------|---------|--------|
| **Spectacles** | Python (FastMCP) | `/home/vncuser/Desktop/Spectacles/spectacles_mcp/` | Browser automation — thin HTTP client calling deployed Cloud Run service | Active |
| **KB API** | TypeScript | `/servers/kb-api-mcp/` | Legal research KB — search, AI Q&A, case graph, extraction pipeline | Active |
| **KB DB** | TypeScript | `/servers/kb-db-mcp/` | Read-only PostgreSQL access to KB database — DBA/debug tool only | Optional |
| **WC Paralegal** | TypeScript | `/servers/wc-paralegal-mcp/` | Document extraction (Document AI + Gemini), case management, chat | Active |
| **Social Media** | TypeScript | `/servers/social-media-mcp/` | LinkedIn, Twitter/X, Mastodon posting with AI content generation | Working (no active use case) |

#### Third-Party Servers

| MCP Server | Type | Source | Purpose | Status |
|------------|------|--------|---------|--------|
| **n8n** | NPM CLI | `n8n-mcp` | Workflow automation for KB pipelines | Active (needs API key) |
| **Linear** | HTTP (OAuth) | `https://mcp.linear.app/mcp` | Project management & issue tracking | Active |
| **Notion** | Built-in | Claude built-in integration | Workspace search, page management | Active |
| **Prisma** | NPM built-in | `npx prisma mcp` | Database migrations & schema | Available (project-specific) |
| **PostgreSQL** | Docker | `crystaldba/postgres-mcp` | Query optimization & health checks | Available |

#### Removed / Deprecated

| MCP Server | Reason | Date |
|------------|--------|------|
| **FreeCAD** | No GBS relevance | 2026-03-01 |
| **Penpot** | No active GBS use case | 2026-03-01 |
| **BetterAuth** | Third-party remote MCP from chonkie.ai — security risk | 2026-03-01 |

**Note**: For company-wide development standards, see the main CLAUDE.md at /home/vncuser/Desktop/CLAUDE.md.

---

For company-wide development standards, see the main CLAUDE.md at `~/Desktop/CLAUDE.md`.

For centralized business, legal, marketing, and product documentation, see the [Adjudica Documentation Hub](~/Desktop/adjudica-documentation/CLAUDE.md) and the [Quick Index](~/Desktop/adjudica-documentation/ADJUDICA_INDEX.md).

---

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
