# MCP Servers

Unified collection of MCP (Model Context Protocol) server configurations, custom servers, and documentation for Glass Box Solutions.

## Overview

| MCP Server | Type | Source | Description |
|------------|------|--------|-------------|
| **Spectacles** | External repo | [Glass-Box-Solutions-Inc/Spectacles](https://github.com/Glass-Box-Solutions-Inc/Spectacles) | Browser automation + VLM verification |
| **Penpot** | NPM package | `@penpot/mcp-server` | Design tool integration |
| **n8n** | NPM CLI | `n8n-mcp` | Workflow automation |
| **FreeCAD** | Custom (Python) | `servers/freecad-mcp/` | Full CAD control with AI |
| **Minimal Test** | Custom (Python) | `servers/minimal-test/` | Test MCP server |
| **Prisma** | NPM built-in | `npx prisma mcp` | Database migrations & schema |
| **BetterAuth** | Remote MCP | `@anthropic/mcp-remote` | Authentication flows |
| **PostgreSQL** | Docker | `crystaldba/postgres-mcp` | Query optimization & health |
| **Social Media** | Custom (Node.js) | `servers/social-media-mcp/` | LinkedIn, Twitter/X, Mastodon |
| **Linear** | HTTP (OAuth) | `https://mcp.linear.app/mcp` | Project management & issue tracking |

## Quick Start

1. **Generate your `.mcp.json`** from the template:

   **Windows (PowerShell):**
   ```powershell
   .\scripts\generate-mcp-config.ps1 -OutputPath "C:\path\to\your\project\.mcp.json"
   ```

   **Linux/macOS:**
   ```bash
   ./scripts/generate-mcp-config.sh /path/to/your/project/.mcp.json
   ```

2. **Set required environment variables** (see individual config docs in `configs/`):
   - `PENPOT_TOKEN` - Penpot access token
   - `N8N_API_KEY` - n8n Cloud API key
   - `BROWSERLESS_API_TOKEN` - Browserless.io token
   - `GOOGLE_AI_API_KEY` - Google AI API key
   - Social media tokens (if using social-media-mcp)

3. **Build custom servers** (if using them):
   ```bash
   # Social Media MCP
   cd servers/social-media-mcp && npm install && npm run build

   # FreeCAD MCP
   cd servers/freecad-mcp && uv sync
   ```

## Structure

```
.mcp.json.template      # Template with ${PLACEHOLDERS} - no secrets
scripts/                 # Config generation scripts
servers/
  freecad-mcp/           # Custom Python MCP for FreeCAD
  social-media-mcp/      # Custom Node.js MCP for social media
  minimal-test/          # Minimal test MCP server
configs/                 # Per-server setup documentation
```

## Security

- **Never commit `.mcp.json`** — it may contain tokens. Only the `.template` is tracked.
- All secrets use `${VARIABLE}` placeholders in the template.
- Set secrets as environment variables, not in files.

---

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
