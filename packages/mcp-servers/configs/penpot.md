# Penpot MCP

**Package:** `@penpot/mcp-server` (npm)

Design tool integration for Penpot.

## Setup

1. Log into Penpot
2. Go to Settings > Access Tokens
3. Generate a new token
4. Set as `PENPOT_TOKEN` environment variable

**Security note:** The Penpot JWT was previously hardcoded in `.mcp.json`. It has been removed and replaced with an environment variable reference. Regenerate your token if the old one was exposed.

## Config

```json
{
  "penpot": {
    "command": "npx",
    "args": ["-y", "@penpot/mcp-server"],
    "env": {
      "PENPOT_TOKEN": "${PENPOT_TOKEN}"
    }
  }
}
```
