# PostgreSQL MCP Pro

**Image:** `crystaldba/postgres-mcp` (Docker)

Query optimization, indexing, and health analysis for PostgreSQL databases.

## Requirements

- Docker installed and running
- `DATABASE_URL` environment variable set

## Config

```json
{
  "postgres-mcp": {
    "command": "docker",
    "args": ["run", "-i", "--rm", "-e", "DATABASE_URL", "crystaldba/postgres-mcp"]
  }
}
```

**Note:** Requires Docker, so only works on Linux/macOS or Windows with Docker Desktop.
