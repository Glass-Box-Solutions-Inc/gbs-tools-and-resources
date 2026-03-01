# Prisma MCP

**Package:** `prisma` (built-in MCP via `npx prisma mcp`)

Database migrations, schema management, and Prisma Studio.

## Config

**Windows:**
```json
{
  "prisma-local-win": {
    "command": "cmd",
    "args": ["/c", "npx", "prisma", "mcp"]
  }
}
```

**Linux:**
```json
{
  "prisma-local": {
    "command": "npx",
    "args": ["prisma", "mcp"]
  }
}
```

Both variants are included in the template. Use the one matching your OS.
