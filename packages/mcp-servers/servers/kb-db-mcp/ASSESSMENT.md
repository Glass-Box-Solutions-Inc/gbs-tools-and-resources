# KB DB MCP — Assessment

## What It Does

The KB DB MCP server provides **direct read-only PostgreSQL access** to the Knowledge Base database. It connects to the database via `KB_DATABASE_URL` and exposes SQL tools with safety guardrails:

- **Read-only enforcement**: Blocks INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE, GRANT, REVOKE, and COPY statements
- **10-second query timeout**: Prevents long-running queries from locking resources
- **1000-row limit**: Caps result sets to prevent memory exhaustion
- **Full-text truncation**: Truncates `fullText`/`full_text` columns to 500 chars to keep responses manageable

### Available Tools

| Tool | Description |
|------|-------------|
| `db_query` | Execute arbitrary read-only SQL queries |
| `db_schema` | Get column schema for a specific table |
| `db_tables` | List all tables in the public schema |
| `db_count` | Get row counts with optional WHERE filter |
| `db_sample` | Get N sample rows from a table (max 50) |
| `db_case_lookup` | Find cases by name (ILIKE partial match) |
| `db_status_report` | Generate comprehensive status report (counts by status, verification, briefs, principles) |

## KB DB MCP vs KB API MCP

| Aspect | KB API MCP | KB DB MCP |
|--------|-----------|-----------|
| **Connection** | REST API via HTTP | Direct PostgreSQL |
| **Auth** | None (public API) | Database credentials |
| **Scope** | Curated API endpoints | Raw SQL access |
| **Use case** | Normal agent operations | DBA/debugging/investigation |
| **Safety** | API handles validation | Read-only + timeout + row limit |
| **Data freshness** | Through API cache | Real-time from database |
| **Requires** | Backend service running | Database connection string only |
| **Risk** | Low | Medium (direct DB access) |

## Recommendation

**Activate for local development and DBA tasks only. Not recommended for production agent use.**

### Rationale

1. **The KB API MCP covers 95% of agent needs** — searching cases, asking legal questions, checking pipeline status. Use that for normal workflows.

2. **KB DB MCP is invaluable for debugging** — when you need to run ad-hoc SQL to investigate data issues, check migration state, or diagnose pipeline problems. These are tasks the API MCP cannot support.

3. **Security concern for production** — providing raw SQL access to an agent in a production context is unnecessary risk. The read-only guardrails are good but not bulletproof (e.g., SQL injection in WHERE clauses could theoretically extract sensitive data from other tables).

4. **Requires database credentials** — the `KB_DATABASE_URL` connection string contains the database password, which should only be used in controlled environments.

### When to Activate

- **Local development**: Always useful. Set `KB_DATABASE_URL` from your local `.env`.
- **Debugging production**: Activate temporarily with the production Cloud SQL connection string (via Cloud SQL Auth Proxy).
- **Data investigation**: When you need to explore data patterns, check migration state, or audit records.
- **Never**: As a permanently active production agent tool.

### Configuration

```json
{
  "kb-db": {
    "command": "node",
    "args": ["${MCP_SERVERS_DIR}/servers/kb-db-mcp/build/index.js"],
    "env": {
      "KB_DATABASE_URL": "postgresql://user:pass@localhost:5432/legal_research"
    }
  }
}
```

**Note**: The `KB_DATABASE_URL` must be set to a valid PostgreSQL connection string. For production database access, use Cloud SQL Auth Proxy to create a local tunnel first.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
