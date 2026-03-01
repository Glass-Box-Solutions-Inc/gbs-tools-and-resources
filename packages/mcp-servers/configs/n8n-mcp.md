# n8n MCP

**Package:** `n8n-mcp` (npm CLI)

Workflow automation integration for n8n Cloud.

## Setup

1. Log into n8n Cloud at https://glassboxinc.app.n8n.cloud
2. Go to Settings > API
3. Generate a new API key
4. Set as `N8N_API_KEY` environment variable

**Security note:** The n8n API key was previously hardcoded in `.mcp.json`. It has been removed and replaced with an environment variable reference. Regenerate your API key if the old one was exposed.

## Config

```json
{
  "n8n-mcp": {
    "command": "n8n-mcp",
    "args": [],
    "env": {
      "MCP_MODE": "stdio",
      "LOG_LEVEL": "error",
      "DISABLE_CONSOLE_OUTPUT": "true",
      "N8N_API_URL": "https://glassboxinc.app.n8n.cloud/api/v1",
      "N8N_API_KEY": "${N8N_API_KEY}"
    }
  }
}
```
