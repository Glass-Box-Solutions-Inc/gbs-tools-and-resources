# BetterAuth MCP

**Package:** `@anthropic/mcp-remote` connecting to `https://mcp.chonkie.ai/better-auth/better-auth-builder/mcp`

Authentication flows and organization management via BetterAuth.

## Config

**Windows:**
```json
{
  "better-auth-win": {
    "command": "cmd",
    "args": ["/c", "npx", "-y", "@anthropic/mcp-remote", "https://mcp.chonkie.ai/better-auth/better-auth-builder/mcp"]
  }
}
```

**Linux:**
```json
{
  "better-auth": {
    "command": "npx",
    "args": ["-y", "@anthropic/mcp-remote", "https://mcp.chonkie.ai/better-auth/better-auth-builder/mcp"]
  }
}
```
