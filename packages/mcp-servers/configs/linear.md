# Linear MCP

**Type:** HTTP (Remote MCP with OAuth)
**URL:** `https://mcp.linear.app/mcp`

Project management and issue tracking via Linear's official MCP server.

## Setup

1. Add the Linear MCP server to Claude Code project settings (type: `http`)
2. Restart Claude Code — the OAuth flow will trigger in the browser
3. Authenticate with your Linear account and authorize Claude Code
4. Linear tools will load automatically on subsequent sessions

### Claude Code Configuration

The Linear MCP uses HTTP transport with OAuth (not stdio). Add it via `/mcp` in Claude Code or directly in `~/.claude.json` under the target project's `mcpServers`:

```json
{
  "linear": {
    "type": "http",
    "url": "https://mcp.linear.app/mcp"
  }
}
```

This is a **project-level** setting in `~/.claude.json`, not a `.mcp.json` entry — HTTP MCP servers with OAuth don't use the stdio template pattern.

## Capabilities

- Create, update, and search issues
- Manage projects, cycles, and labels
- Query team members and workflows
- Link issues and manage dependencies

## Troubleshooting

- **No tools loading:** OAuth token may have expired. Remove and re-add the server, then restart Claude Code to re-trigger the OAuth flow.
- **Connection timeout:** Verify outbound HTTPS access to `mcp.linear.app`:
  ```bash
  curl -I https://mcp.linear.app/mcp
  ```
- **Re-authenticate:** Remove the `linear` entry from `mcpServers` in `~/.claude.json`, restart Claude Code, re-add it, and restart again.

## Notes

- Unlike stdio-based MCP servers, Linear uses HTTP transport with built-in OAuth — no API keys or environment variables needed.
- The OAuth token is managed by Claude Code internally, not stored in project config files.
- This server is provided by Linear directly (first-party).
