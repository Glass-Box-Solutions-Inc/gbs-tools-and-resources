# WC Paralegal MCP

**Source:** Custom GBS MCP server at `/home/vncuser/Desktop/mcp-servers/servers/wc-paralegal-mcp/`

Wraps the WC Paralegal Backend REST API (NestJS) for document extraction,
case management, and Gemini chat.

## Architecture

TypeScript MCP server calling the WC Paralegal Backend via HTTP (axios).
Follows the exact same pattern as kb-api-mcp.

**Backend:** NestJS at `WC_PARALEGAL_URL` (default: `http://localhost:3002`)

## Setup

```bash
cd /home/vncuser/Desktop/mcp-servers/servers/wc-paralegal-mcp
npm install
npm run build
```

## Config

```json
{
  "wc-paralegal": {
    "command": "node",
    "args": ["/home/vncuser/Desktop/mcp-servers/servers/wc-paralegal-mcp/build/index.js"],
    "env": {
      "WC_PARALEGAL_URL": "http://localhost:3002"
    }
  }
}
```

## Available Tools

### Public (No Auth Required)

| Tool | Description |
|------|-------------|
| `wc_health` | Check backend health + database connectivity |
| `wc_readiness` | Readiness probe |
| `wc_liveness` | Liveness probe |

### Cases (Requires Auth)

| Tool | Description |
|------|-------------|
| `wc_list_cases` | List cases, optionally filter by status |
| `wc_get_case` | Get case details by UUID |
| `wc_create_case` | Create a new WC case |
| `wc_start_case_session` | Start a case session for doc processing |
| `wc_get_active_session` | Get currently active case session |

### Document Processing (Requires Auth + Case Session)

| Tool | Description |
|------|-------------|
| `wc_process_document` | Process document via Document AI (V1 rules-based) |
| `wc_process_document_v2` | Process document via Document AI + Gemini (V2 hybrid) |
| `wc_process_documents_with_summary` | Batch process + generate case summary |
| `wc_get_job_status` | Check processing job status |
| `wc_get_processed_documents` | Get processed docs for a case |

### Chat (Requires Auth)

| Tool | Description |
|------|-------------|
| `wc_chat_message` | Send message to Gemini chat assistant |
| `wc_create_chat_session` | Create new chat session |
| `wc_get_chat_history` | Get chat history for a session |

## Notes

- Most endpoints require BetterAuth session authentication
- Document processing requires an active case session (start one first)
- The backend is currently localhost-only (not on Cloud Run yet)
- When deployed to Cloud Run, update `WC_PARALEGAL_URL` to the Cloud Run URL

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
