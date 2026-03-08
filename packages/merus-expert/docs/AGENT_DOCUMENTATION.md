<!-- @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology -->

# MerusExpert Claude AI Agent — Technical Reference

**Version:** 2.0.0
**Model:** `claude-sonnet-4-6`
**Stack:** Python 3.12, FastAPI, Anthropic SDK, React/TypeScript
**Domain:** California Workers' Compensation legal case management (MerusCase)

---

## Table of Contents

1. [Overview](#1-overview)
2. [Architecture](#2-architecture)
3. [Claude Agent](#3-claude-agent)
4. [Tools Reference](#4-tools-reference)
5. [MerusAgent](#5-merusagent)
6. [MerusCase API Client](#6-meruscase-api-client)
7. [API Models](#7-api-models)
8. [SSE Streaming](#8-sse-streaming)
9. [Service Layer](#9-service-layer)
10. [Frontend Integration](#10-frontend-integration)
11. [Configuration](#11-configuration)
12. [Error Handling](#12-error-handling)
13. [File Map](#13-file-map)

---

## 1. Overview

MerusExpert is an AI agent that gives California Workers' Compensation attorneys and staff a natural language interface to their MerusCase system. Users type plain English — "Bill 0.2 hours to the Smith case for reviewing medical records" — and the agent resolves the request through Claude's tool-use loop, calling the appropriate MerusCase API operations and streaming results back in real time.

The agent handles both read and write operations: searching cases, retrieving billing history and activities, adding time entries, posting costs, attaching notes, and uploading documents. Write operations are guarded by a confirmation step in the system prompt — the agent confirms details with the user before executing billable actions.

**Key design goals:**

- Natural language case references — "the Smith matter", "WC-2024-001", "the Jones hearing" all resolve correctly via fuzzy search
- Real-time streaming so users see Claude's reasoning as it happens, including live tool call status
- No exceptions leak into the SSE stream — every error layer converts failures to structured error events or typed exceptions, keeping the conversation loop alive
- Singleton dependency injection means the HTTP client and token are initialized once at startup, not on every request

---

## 2. Architecture

The agent spans three discrete layers. Each layer has a single responsibility and communicates through typed interfaces.

```
┌─────────────────────────────────────────────────────┐
│                    FRONTEND LAYER                   │
│           React/TypeScript (Vite + Tailwind)        │
│                                                     │
│  AIAssistantPage.tsx                                │
│    └── useAgent hook (state management)             │
│         └── streamAgentChat() (SSE async generator) │
└────────────────────┬────────────────────────────────┘
                     │  POST /api/agent/chat
                     │  text/event-stream (SSE)
┌────────────────────▼────────────────────────────────┐
│                   SERVICE LAYER                     │
│              FastAPI (service/)                     │
│                                                     │
│  service/main.py         — app factory, lifespan    │
│  service/routes/agent.py — POST /api/agent/chat     │
│  service/auth.py         — X-API-Key verification   │
│  service/dependencies.py — lru_cache singletons     │
└────────────────────┬────────────────────────────────┘
                     │  Python function calls
┌────────────────────▼────────────────────────────────┐
│                    CORE LAYER                       │
│           src/merus_expert/                         │
│                                                     │
│  agent/claude_agent.py   — Claude tool-use loop     │
│  agent/tools.py          — 13 tool definitions      │
│  agent/system_prompt.py  — prompt assembly          │
│  core/agent.py           — MerusAgent wrapper       │
│  api_client/client.py    — httpx HTTP client        │
│  api_client/models.py    — Pydantic models          │
└────────────────────┬────────────────────────────────┘
                     │  HTTPS REST
┌────────────────────▼────────────────────────────────┐
│              MERUSCASE API                          │
│         https://api.meruscase.com                   │
│         (CakePHP — Bearer token auth)               │
└─────────────────────────────────────────────────────┘
```

### Layer responsibilities

| Layer | Responsibility | Key files |
|-------|---------------|-----------|
| Frontend | UI rendering, SSE consumption, conversation state | `AIAssistantPage.tsx`, `useAgent.ts`, `agent.ts` |
| Service | HTTP routing, auth, singleton injection, SSE wrapping | `main.py`, `routes/agent.py`, `auth.py`, `dependencies.py` |
| Core | Claude orchestration, tool dispatch, MerusCase API calls | `claude_agent.py`, `tools.py`, `core/agent.py`, `api_client/client.py` |

---

## 3. Claude Agent

### 3.1 ClaudeAgent Class

**File:** `src/merus_expert/agent/claude_agent.py`

`ClaudeAgent` is the orchestrator. It holds references to the Anthropic async client and a `MerusAgent` instance. Its single public method, `chat_stream`, drives the tool-use loop and yields SSE-compatible dict events.

```python
class ClaudeAgent:
    def __init__(
        self,
        anthropic_client: anthropic.AsyncAnthropic,
        merus_agent: MerusAgent,
    ):
        self.client = anthropic_client
        self.merus_agent = merus_agent
        self._system_prompt = get_system_prompt()  # cached at init
```

### 3.2 Model Configuration

| Setting | Value |
|---------|-------|
| Model | `claude-sonnet-4-6` |
| `max_tokens` | `4096` per API call |
| Default `max_iterations` | `10` (configurable 1–20 via `ChatRequest`) |
| Streaming | Anthropic streaming SDK (`client.messages.stream()`) |

### 3.3 Tool-Use Loop

`chat_stream` runs a bounded iteration loop:

```
for iteration in range(max_iterations):
    1. Call client.messages.stream() with current conversation
    2. Yield text chunks from stream.text_stream → {"type": "text", "content": chunk}
    3. Await stream.get_final_message() → get stop_reason + full content blocks
    4. If stop_reason == "end_turn":
         yield {"type": "done"} → return
    5. If stop_reason != "tool_use":
         yield {"type": "done"} → return (unexpected stop handled cleanly)
    6. For each tool_use block in content:
         yield {"type": "tool_call", "name": ..., "input": ...}
         result = await dispatch_tool(merus_agent, tool_name, tool_input)
         yield {"type": "tool_result", "name": ..., "result": result}
    7. Append assistant content + tool results to conversation history
    8. Loop

If max_iterations exhausted:
    yield {"type": "error", "message": "Max iterations (N) reached"}
```

The loop never raises. `anthropic.APIError` is caught inside and converted to an error event. `dispatch_tool` is also guaranteed non-raising (see Section 4).

### 3.4 Conversation History Management

The agent maintains a local `conversation` list that starts as a copy of the incoming `messages` and grows with each iteration:

```python
conversation = list(messages)  # start with user's history

# After each tool round:
conversation.append({"role": "assistant", "content": assistant_content})
conversation.append({"role": "user", "content": tool_results})
```

This allows multi-turn tool use within a single `chat_stream` call (e.g., Claude calls `find_case`, gets the ID, then calls `get_case_billing` in the next iteration).

### 3.5 System Prompt

**File:** `src/merus_expert/agent/system_prompt.py`

The system prompt is assembled once at startup using `@lru_cache(maxsize=1)` and held for the process lifetime. It concatenates three knowledge documents:

| File | Purpose |
|------|---------|
| `knowledge/docs/MERUSCASE_API_REFERENCE.md` | MerusCase API field reference |
| `knowledge/docs/MERUS_AGENT_SUMMARY.md` | Agent operational summary |
| `knowledge/billing_codes.json` | Available billing codes (pretty-printed JSON) |

**Prompt persona and behavioral rules (verbatim from source):**

- Role: "MerusExpert, an intelligent AI assistant for MerusCase legal case management"
- Audience: California Workers' Compensation attorneys and staff
- Confirm before writing: Before calling `bill_time`, `add_cost`, or `add_note`, confirm details unless the user has already confirmed
- CakePHP is internal: Do not mention CakePHP or API internals to the user
- Natural language: Accept case references like "Smith case", "WC-2024-001", or "the Jones matter"
- Error recovery: If a tool returns an error, explain it clearly and suggest alternatives
- Date format: YYYY-MM-DD
- Currency format: $XX.XX

The knowledge files are read with a safe fallback (`_read_file_safe`) that logs a warning and returns an empty string on any read failure, ensuring startup never fails due to a missing knowledge file.

---

## 4. Tools Reference

**File:** `src/merus_expert/agent/tools.py`

All 13 tools are defined in Anthropic tool-use format and passed to every `client.messages.stream()` call via the `tools=TOOLS` parameter.

### 4.1 Tool Index

| # | Tool Name | Category | Required Params |
|---|-----------|----------|-----------------|
| 1 | `find_case` | Read | `search` |
| 2 | `get_case_details` | Read | `case_id` |
| 3 | `get_case_billing` | Read | `case_id` |
| 4 | `get_case_activities` | Read | `case_id` |
| 5 | `get_case_parties` | Read | `case_id` |
| 6 | `list_cases` | Read | _(none)_ |
| 7 | `get_billing_summary` | Read | `case_search` |
| 8 | `get_billing_codes` | Read (cached) | _(none)_ |
| 9 | `get_activity_types` | Read (cached) | _(none)_ |
| 10 | `bill_time` | Write | `case_search`, `hours`, `description` |
| 11 | `add_cost` | Write | `case_search`, `amount`, `description` |
| 12 | `add_note` | Write | `case_search`, `subject` |
| 13 | `upload_document` | Write | `case_search`, `file_path` |

### 4.2 Read Tools — Full Schemas

#### `find_case`

Fuzzy search for a case by file number or party name. Search order: exact file number match → substring file number match → substring party name match. Raises `CaseNotFoundError` if nothing matches.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `search` | string | Yes | — | Case file number or party name |
| `limit` | integer | No | `50` | Max cases to scan |

**Returns:** Case data dict with `id`, `file_number`, `primary_party_name`, `case_status`, `case_type` fields.

---

#### `get_case_details`

Retrieves full case details from `GET /caseFiles/view/{id}`.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `case_id` | integer | Yes | MerusCase numeric case file ID |

**Returns:** Full case data dict from MerusCase API.

---

#### `get_case_billing`

Retrieves open ledger entries for a case from `GET /caseLedgersOpen/index`. Supports optional date range filtering.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `case_id` | integer | Yes | — | MerusCase case file ID |
| `date_gte` | string | No | — | Start date filter (YYYY-MM-DD) |
| `date_lte` | string | No | — | End date filter (YYYY-MM-DD) |

**Returns:** Dict with ledger entry data.

---

#### `get_case_activities`

Retrieves activities and notes for a case from `GET /activities/index`.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `case_id` | integer | Yes | — | MerusCase case file ID |
| `limit` | integer | No | `100` | Max results to return |

**Returns:** List of activity dicts.

---

#### `get_case_parties`

Retrieves all parties and contacts associated with a case from `GET /parties/index`.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `case_id` | integer | Yes | MerusCase case file ID |

**Returns:** List of party dicts.

---

#### `list_cases`

Lists cases with optional status and type filters. Calls `GET /caseFiles/index`.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `case_status` | string | No | — | Filter by status (e.g., "Active", "Closed") |
| `case_type` | string | No | — | Filter by type (e.g., "Workers Compensation") |
| `limit` | integer | No | `100` | Max results |

**Returns:** List of case dicts.

---

#### `get_billing_summary`

Convenience tool that calls `find_case` internally to resolve the case, then fetches ledger entries and computes totals. Returns a summary dict with `total_amount` and `total_entries`.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `case_search` | string | Yes | Case file number or party name |
| `start_date` | string | No | Start date (YYYY-MM-DD) |
| `end_date` | string | No | End date (YYYY-MM-DD) |

**Returns:**
```json
{
  "case_id": 56171871,
  "case_name": "Smith, John",
  "total_amount": 1250.00,
  "total_entries": 4,
  "entries": { ... },
  "start_date": "2024-01-01",
  "end_date": null
}
```

---

#### `get_billing_codes`

Returns available billing codes. Results are cached for the TTL period (default 1 hour) — the underlying HTTP call is only made on cache miss.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| _(none)_ | — | — | — |

**Returns:** Dict of billing codes keyed by ID.

---

#### `get_activity_types`

Returns available activity types. Same 1-hour cache as `get_billing_codes`.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| _(none)_ | — | — | — |

**Returns:** Dict of activity types keyed by ID.

---

### 4.3 Write Tools — Full Schemas

#### `bill_time`

Creates a billable activity entry on a case. Internally calls `find_case` to resolve the case, converts hours to minutes, and posts to `POST /activities/add` with `{"Activity": {...}, "billable": 1}`.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `case_search` | string | Yes | — | Case file number or party name |
| `hours` | number | Yes | — | Time in hours (e.g., `0.2` = 12 minutes) |
| `description` | string | Yes | — | Detailed description of work performed |
| `subject` | string | No | First 50 chars of description | Short subject line |
| `activity_type_id` | integer | No | — | Activity type ID from `get_activity_types` |
| `billing_code_id` | integer | No | — | Billing code ID from `get_billing_codes` |

**Returns:**
```json
{
  "success": true,
  "activity_id": "918183874",
  "case_id": "56171871",
  "case_name": "Smith, John",
  "hours": 0.2,
  "minutes": 12,
  "description": "Review medical records and QME report"
}
```

**Raises:** `CaseNotFoundError`, `BillingError`

---

#### `add_cost`

Creates a direct ledger entry (not time-based) for filing fees, court costs, or expenses. Maps the `ledger_type` string to `LedgerType` enum and posts to `POST /caseLedgers/add`.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `case_search` | string | Yes | — | Case file number or party name |
| `amount` | number | Yes | — | Dollar amount (e.g., `25.00`) |
| `description` | string | Yes | — | Description of the cost |
| `ledger_type` | string | No | `"cost"` | `"fee"`, `"cost"`, or `"expense"` |

**Ledger type mapping:**

| String | `LedgerType` enum | Integer | Use for |
|--------|-------------------|---------|---------|
| `"fee"` | `FEE` | `1` | Attorney fees, service fees |
| `"cost"` | `COST` | `2` | Filing fees, court costs |
| `"expense"` | `EXPENSE` | `3` | Reimbursable expenses |

**Returns:**
```json
{
  "success": true,
  "ledger_id": 110681047,
  "case_id": "56171871",
  "case_name": "Smith, John",
  "amount": 25.00,
  "description": "WCAB Filing Fee",
  "type": "cost"
}
```

**Raises:** `CaseNotFoundError`, `BillingError`

---

#### `add_note`

Creates a non-billable activity (note) on a case. Posts to `POST /activities/add` with `billable=False`.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `case_search` | string | Yes | Case file number or party name |
| `subject` | string | Yes | Note subject line |
| `description` | string | No | Note body/details |
| `activity_type_id` | integer | No | Activity type ID |

**Returns:**
```json
{
  "success": true,
  "activity_id": "918183875",
  "case_id": "56171871",
  "case_name": "Smith, John",
  "subject": "Client called"
}
```

**Raises:** `CaseNotFoundError`, `MerusAgentError`

---

#### `upload_document`

Uploads a file from the local filesystem to a case. Sends a multipart POST to `POST /uploads/add`. The file must exist at the specified path on the server running the service.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `case_search` | string | Yes | Case file number or party name |
| `file_path` | string | Yes | Absolute local path to the file |
| `description` | string | No | Document description |
| `folder_id` | integer | No | Target folder ID within the case |

**Returns:**
```json
{
  "success": true,
  "case_id": 56171871,
  "filename": "medical_report.pdf",
  "data": { ... }
}
```

**Raises:** `CaseNotFoundError`, `MerusAgentError`

---

### 4.4 Tool Dispatch

```python
async def dispatch_tool(
    agent: MerusAgent,
    tool_name: str,
    tool_input: Dict[str, Any]
) -> Dict[str, Any]:
```

`dispatch_tool` is a plain `if/elif` chain that maps each of the 13 tool names to the corresponding `MerusAgent` method call. The entire function body is wrapped in a single `try/except Exception`:

```python
try:
    if tool_name == "find_case":
        return await agent.find_case(...)
    elif tool_name == "bill_time":
        return await agent.bill_time(...)
    # ... 11 more branches ...
    else:
        return {"error": f"Unknown tool: {tool_name}"}
except Exception as e:
    return {"error": str(e)}
```

This guarantee — `dispatch_tool` never raises — is what keeps the Claude tool-use loop alive. Even if a tool call hits a network error, auth failure, or unexpected exception, the loop continues with an error result that Claude can reason about and explain to the user.

---

## 5. MerusAgent

**File:** `src/merus_expert/core/agent.py`

`MerusAgent` is the high-level business logic layer. It wraps `MerusCaseAPIClient` with natural language case search, reference data caching, typed exceptions, and convenience methods.

### 5.1 Exception Hierarchy

```
MerusAgentError (base)
├── CaseNotFoundError  — raised when find_case() has no match
└── BillingError       — raised when bill_time() or add_cost() fails
```

These exceptions propagate up to the FastAPI global exception handlers (see Section 9.4), which map them to HTTP 404, 400, and 500 respectively. Within the tool-use loop, they are caught by `dispatch_tool`'s outer `except` and returned as `{"error": str(e)}`.

### 5.2 Initialization

```python
MerusAgent(
    access_token: Optional[str] = None,
    token_file: Optional[str] = ".meruscase_token",
    cache_ttl_seconds: int = 3600,
)
```

**Token resolution order:**
1. `access_token` argument (if provided)
2. Read from `token_file` path (if `access_token` is not set)
3. Raise `MerusAgentError` if neither source yields a token

**Internal state:**
- `self.client` — `MerusCaseAPIClient` instance
- `self._cache` — `Dict[str, Any]` for reference data
- `self._cache_timestamps` — `Dict[str, datetime]` for TTL tracking
- `self._cache_ttl` — `timedelta(seconds=cache_ttl_seconds)`

Supports async context manager (`async with MerusAgent(...) as agent:`).

### 5.3 All Methods

#### Read Operations

| Method | Signature | API Call | Returns |
|--------|-----------|----------|---------|
| `find_case` | `(search: str, limit: int = 50)` | `GET /caseFiles/index` + scan | `Dict` or raises `CaseNotFoundError` |
| `get_case_details` | `(case_id: int)` | `GET /caseFiles/view/{id}` | `Dict` |
| `get_case_billing` | `(case_id: int, date_gte?, date_lte?)` | `GET /caseLedgersOpen/index` | `Dict` with ledger entries |
| `get_case_activities` | `(case_id: int, limit: int = 100)` | `GET /activities/index` | `List[Dict]` |
| `get_case_parties` | `(case_id: int)` | `GET /parties/index` | `List[Dict]` |
| `list_all_cases` | `(case_status?, case_type?, limit: int = 100)` | `GET /caseFiles/index` | `List[Dict]` |
| `get_billing_summary` | `(case_search: str, start_date?, end_date?)` | `find_case` + `get_case_billing` | `Dict` with totals |

#### Write Operations

| Method | Signature | API Call | Returns |
|--------|-----------|----------|---------|
| `bill_time` | `(case_search, hours, description, subject?, activity_type_id?, billing_code_id?)` | `POST /activities/add` | `Dict` with activity_id |
| `add_cost` | `(case_search, amount, description, ledger_type?)` | `POST /caseLedgers/add` | `Dict` with ledger_id |
| `add_note` | `(case_search, subject, description?, activity_type_id?)` | `POST /activities/add` | `Dict` with activity_id |
| `upload_document` | `(case_search, file_path, description?, folder_id?)` | `POST /uploads/add` | `Dict` with filename |

#### Reference Data (Cached)

| Method | Cache Key | TTL | API Call |
|--------|-----------|-----|----------|
| `get_billing_codes()` | `"billing_codes"` | `cache_ttl_seconds` (default 1hr) | `GET /billingCodes/index` |
| `get_activity_types()` | `"activity_types"` | `cache_ttl_seconds` (default 1hr) | `GET /activityTypes/index` |

The cache uses `_get_cached(key, fetch_func)`: checks timestamp freshness, returns cached value if within TTL, otherwise calls `fetch_func()` and stores the result.

#### Batch Operations

| Method | Signature | Behavior |
|--------|-----------|----------|
| `bulk_bill_time` | `(entries: List[Dict])` | Iterates entries, calls `bill_time` for each. Errors are caught per-entry and included in results as `{"success": False, "error": "..."}`. Never raises. |

#### Lifecycle

| Method | Description |
|--------|-------------|
| `close()` | Calls `await self.client.close()` to shut down the httpx `AsyncClient` |

### 5.4 Response Normalization

MerusCase returns case lists in two formats depending on the endpoint and filters. `_normalize_cases_response` handles both:

- **List format:** `[{"id": "123", ...}, {"id": "456", ...}]` — used as-is, ensures `id` field exists
- **Dict format:** `{"123": {...}, "456": {...}}` — converted to list with `id` injected from key

### 5.5 Convenience Functions

Two module-level async convenience functions are available for scripting without instantiating the agent class:

```python
# Bill time without manual agent setup
result = await quick_bill_time("Smith", 0.2, "Review records")

# Add cost without manual agent setup
result = await quick_add_cost("Smith", 25.00, "WCAB Filing Fee")
```

Both use `async with MerusAgent(token_file=token_file) as agent:` to ensure the HTTP client is properly closed.

---

## 6. MerusCase API Client

**File:** `src/merus_expert/api_client/client.py`

`MerusCaseAPIClient` is the low-level HTTP layer. It makes no business decisions — it executes HTTP calls and returns `APIResponse` objects.

### 6.1 Configuration

| Setting | Value |
|---------|-------|
| Base URL | `https://api.meruscase.com` |
| Auth | `Authorization: Bearer {access_token}` on every request |
| HTTP client | `httpx.AsyncClient` |
| Timeout | `30` seconds (configurable via `timeout` init param) |
| Default headers | `Accept: application/json`, `Content-Type: application/json` |

### 6.2 All Endpoints

| Method | Endpoint | Client Method | Description |
|--------|----------|---------------|-------------|
| GET | `/caseFiles/view/{id}` | `get_case(case_file_id)` | Full case details |
| GET | `/caseFiles/index` | `list_cases(...)` | List/filter cases |
| GET | `/caseFiles/index?file_number=` | `search_cases(file_number)` | Search by file number |
| POST | `/parties/add` | `add_party(party)` | Add party to case |
| GET | `/parties/index?case_file_id=` | `get_parties(case_file_id)` | Get case parties |
| POST | `/activities/add` | `add_activity(activity)` | Add activity/note |
| GET | `/activities/index?case_file_id=&limit=` | `get_activities(case_file_id, limit)` | Get case activities |
| GET | `/activityTypes/index` | `get_activity_types()` | Reference: activity types |
| POST | `/uploads/add` | `upload_document(document)` | Upload file (multipart) |
| GET | `/uploads/index?case_file_id=&limit=` | `list_documents(case_file_id, limit)` | List uploaded documents |
| GET | `/documents/download/{id}` | `download_document(upload_id)` | Download (302 → S3) |
| GET | `/billingCodes/index` | `get_billing_codes()` | Reference: billing codes |
| GET | `/users/index` | `get_firm_users()` | Firm users (admin) |
| GET | `/caseLedgersOpen/index?case_file_id=` | `get_open_ledgers(...)` | Open ledger entries |
| POST | `/caseLedgers/add` | `add_ledger_entry(entry)` | Add ledger entry |
| GET | `/tasks/index?case_file_id=` | `get_tasks(...)` | Case tasks |

### 6.3 CakePHP POST Body Convention

MerusCase's API uses CakePHP conventions — POST request bodies must wrap the model data in the model name as a top-level key:

```python
# Activity (time entries and notes)
{"Activity": {"case_file_id": 123, "subject": "...", "billable": 1, ...}}

# Ledger entry (direct costs/fees)
{"CaseLedger": {"case_file_id": "123", "amount": "25.00", ...}}

# Party
{"Party": {"case_file_id": 123, "party_type": "Client", ...}}
```

This wrapping is handled internally by `add_activity`, `add_ledger_entry`, and `add_party`. The agent and tools never expose this detail.

### 6.4 `_request` — Core HTTP Method

All client methods call `_request(method, endpoint, data?, params?, files?)`. It handles:

**Success path (HTTP 200):**
- Parses response body as JSON
- Checks for `{"errors": [...]}` in body — MerusCase returns validation errors inside a 200 response (CakePHP pattern)
- If errors present: returns `APIResponse(success=False, error="[type] message", errors=[...])`
- If no errors: returns `APIResponse(success=True, data=body)`

**Error paths:**

| Condition | Response |
|-----------|----------|
| HTTP 401 | `APIResponse(success=False, error="Authentication failed...", error_code=401)` |
| HTTP 429 | `APIResponse(success=False, error="Rate limit exceeded", error_code=429)` — reads `X-RateLimit-Remaining` and `X-RateLimit-Reset` headers |
| Other HTTP errors | Parses body for `message` field, falls back to `"HTTP {status_code}"` |
| `httpx.TimeoutException` | `APIResponse(success=False, error="Request timed out", error_code=408)` |
| Any other exception | `APIResponse(success=False, error=str(e))` |

`_request` never raises. It always returns an `APIResponse`.

### 6.5 File Upload

Document upload uses multipart form data. When `files` is present, `Content-Type` is removed from headers (letting `httpx` set the correct `multipart/form-data` boundary automatically):

```python
if files:
    del headers["Content-Type"]

response = await self._client.request(
    ...,
    data=data if files else None,  # form fields as data
    files=files,                   # {"file": (filename, bytes, content_type)}
)
```

### 6.6 Document Download

`download_document(upload_id)` handles the MerusCase redirect pattern:

1. GET `/documents/download/{id}` with `follow_redirects=False`
2. Expects HTTP 302 with `Location` header pointing to S3
3. Fetches S3 URL with a separate `httpx.AsyncClient` (60s timeout)
4. Returns file bytes in `APIResponse.data`

---

## 7. API Models

**File:** `src/merus_expert/api_client/models.py`

All models use Pydantic `BaseModel`.

### 7.1 `Party`

Represents a party or contact on a case.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `party_id` | `Optional[int]` | `None` | Set by API on create |
| `case_file_id` | `int` | required | Case this party belongs to |
| `party_type` | `PartyType` | `CLIENT` | See enum below |
| `first_name` | `Optional[str]` | `None` | — |
| `last_name` | `Optional[str]` | `None` | — |
| `company_name` | `Optional[str]` | `None` | For organizations |
| `email` | `Optional[str]` | `None` | — |
| `phone` | `Optional[str]` | `None` | — |
| `address` | `Optional[str]` | `None` | — |
| `city` | `Optional[str]` | `None` | — |
| `state` | `Optional[str]` | `None` | — |
| `zip_code` | `Optional[str]` | `None` | — |
| `notes` | `Optional[str]` | `None` | — |

**`PartyType` enum:** `Client` | `Opposing Party` | `Witness` | `Expert` | `Insurance Company` | `Employer` | `Other`

### 7.2 `Activity`

Represents a time entry or note on a case.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `activity_id` | `Optional[int]` | `None` | Set by API on create |
| `case_file_id` | `int` | required | — |
| `activity_type` | `str` | `"Note"` | Activity type string |
| `activity_type_id` | `Optional[int]` | `None` | Numeric ID |
| `subject` | `str` | required | Subject line |
| `description` | `Optional[str]` | `None` | Body/details |
| `date` | `datetime` | `now()` | Activity date |
| `duration_minutes` | `Optional[int]` | `None` | For billable time |
| `billable` | `bool` | `False` | Set `True` for time entries |
| `billing_code_id` | `Optional[int]` | `None` | — |
| `user_id` | `Optional[int]` | `None` | Assigned user |

### 7.3 `LedgerEntry`

Represents a direct fee/cost entry (not time-based).

| Field | Type | Default | Validation | Description |
|-------|------|---------|------------|-------------|
| `ledger_id` | `Optional[int]` | `None` | — | Set by API on create |
| `case_file_id` | `int` | required | — | — |
| `amount` | `float` | required | `gt=0` | Dollar amount |
| `description` | `str` | required | `min_length=1` | — |
| `date` | `datetime` | `now()` | — | Entry date |
| `ledger_type_id` | `LedgerType` | `FEE` | — | See enum below |
| `billing_code_id` | `Optional[int]` | `None` | — | — |

**`LedgerType` enum:** `FEE=1` | `COST=2` | `EXPENSE=3`

`LedgerEntry.to_api_payload()` returns the CakePHP-wrapped dict ready for POST:

```python
{
    "CaseLedger": {
        "case_file_id": "56171871",
        "amount": "25.00",
        "description": "WCAB Filing Fee",
        "date": "2024-01-15",
        "ledger_type_id": 2,
    }
}
```

### 7.4 `Document`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `document_id` | `Optional[int]` | `None` | Set by API |
| `case_file_id` | `int` | required | — |
| `filename` | `str` | required | Filename for upload |
| `file_path` | `str` | required | Absolute local path |
| `description` | `Optional[str]` | `None` | — |
| `document_type` | `Optional[str]` | `None` | — |
| `folder_id` | `Optional[int]` | `None` | Case folder |

### 7.5 `CaseFile`

| Field | Type | Description |
|-------|------|-------------|
| `case_file_id` | `int` | Primary key |
| `file_number` | `Optional[str]` | Human-readable case ID |
| `case_type` | `Optional[str]` | e.g., "Workers Compensation" |
| `case_status` | `Optional[str]` | e.g., "Active" |
| `branch_office` | `Optional[str]` | — |
| `open_date` | `Optional[datetime]` | — |
| `close_date` | `Optional[datetime]` | — |
| `parties` | `List[Party]` | Embedded parties |
| `venue` | `Optional[str]` | Hearing venue |
| `statute_of_limitations` | `Optional[datetime]` | SOL date |
| `responsible_attorney` | `Optional[str]` | — |
| `originating_attorney` | `Optional[str]` | — |

### 7.6 `APIResponse`

Standard response wrapper returned by every `MerusCaseAPIClient` method.

| Field | Type | Description |
|-------|------|-------------|
| `success` | `bool` | Whether the operation succeeded |
| `data` | `Optional[Any]` | Response payload |
| `error` | `Optional[str]` | Human-readable error summary |
| `errors` | `Optional[List[Dict]]` | Raw MerusCase error list (errors-in-200 pattern) |
| `error_code` | `Optional[int]` | HTTP status code of the failure |
| `rate_limit_remaining` | `Optional[int]` | From `X-RateLimit-Remaining` header |
| `rate_limit_reset` | `Optional[datetime]` | From `X-RateLimit-Reset` header |

### 7.7 `OAuthToken`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `access_token` | `str` | required | Bearer token value |
| `token_type` | `str` | `"Bearer"` | — |
| `expires_in` | `Optional[int]` | `None` | Seconds until expiry |
| `refresh_token` | `Optional[str]` | `None` | For token refresh flows |
| `scope` | `Optional[str]` | `None` | — |
| `created_at` | `datetime` | `now()` | Used to compute expiry |

`is_expired()` returns `True` when `(now - created_at).total_seconds() >= expires_in`.

---

## 8. SSE Streaming

Server-Sent Events (SSE) is the transport for real-time agent output. The agent streams text as Claude generates it — users see Claude's reasoning character by character, and tool calls appear with live status indicators.

### 8.1 Full Pipeline

```
POST /api/agent/chat
  ↓ (HTTP request with JSON body)
FastAPI route: service/routes/agent.py
  ↓ verify_api_key (X-API-Key header)
  ↓ Depends(get_claude_agent) → ClaudeAgent singleton
  ↓
ClaudeAgent.chat_stream(messages, max_iterations)
  ↓
  anthropic.AsyncAnthropic.messages.stream()
    ↓ stream.text_stream → yields text chunks
    ↓ stream.get_final_message() → stop_reason + content blocks
    ↓ if stop_reason == "tool_use":
        dispatch_tool(merus_agent, name, input)
          ↓ MerusAgent method → MerusCaseAPIClient._request()
          ↓ https://api.meruscase.com (Bearer token)
        → yields tool_call, tool_result events
        → loop for next iteration
    ↓ if stop_reason == "end_turn":
        → yield done event → return
  ↓
event_stream() generator:
  for event in agent.chat_stream(...):
      yield f"data: {json.dumps(event)}\n\n"
  ↓
StreamingResponse(
    media_type="text/event-stream",
    headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    }
)
```

### 8.2 SSE Event Types

Every event is a JSON object on a `data:` line, followed by a blank line.

| Event Type | Fields | Trigger |
|------------|--------|---------|
| `text` | `content: string` | Each text chunk as Claude streams it |
| `tool_call` | `name: string`, `input: object` | Claude has decided to call a tool |
| `tool_result` | `name: string`, `result: object` | Tool execution complete (success or error in result) |
| `done` | _(no additional fields)_ | Conversation turn complete — `stop_reason == "end_turn"` |
| `error` | `message: string` | Any failure: API error, max iterations, route exception |

### 8.3 Wire Format

Each event is encoded as:

```
data: {"type": "text", "content": "I found the Smith case"}\n\n
data: {"type": "tool_call", "name": "get_case_billing", "input": {"case_id": 56171871}}\n\n
data: {"type": "tool_result", "name": "get_case_billing", "result": {"data": {...}}}\n\n
data: {"type": "done"}\n\n
```

The double newline (`\n\n`) after each event is required by the SSE specification to mark event boundaries.

### 8.4 Example Event Sequence

A complete "find case and bill time" turn produces events in this order:

```
data: {"type": "text", "content": "I'll look up the Smith case and "}
data: {"type": "text", "content": "bill the time for you."}
data: {"type": "tool_call", "name": "find_case", "input": {"search": "Smith"}}
data: {"type": "tool_result", "name": "find_case", "result": {"id": "56171871", ...}}
data: {"type": "text", "content": "Found the case. Billing 0.2 hours now."}
data: {"type": "tool_call", "name": "bill_time", "input": {"case_search": "Smith", "hours": 0.2, ...}}
data: {"type": "tool_result", "name": "bill_time", "result": {"success": true, "activity_id": "..."}}
data: {"type": "text", "content": "Done. I've billed 12 minutes (0.2 hours) to the Smith case."}
data: {"type": "done"}
```

---

## 9. Service Layer

### 9.1 FastAPI Application

**File:** `service/main.py`

The app is version `2.0.0` and uses a lifespan context manager for startup/shutdown logic.

**Startup sequence:**
1. `_init_database()` — initializes SQLite from `setup/schema.sql` if tables don't exist
2. `get_merus_agent()` — pre-warms the MerusAgent singleton (token read, HTTP client created)
3. `get_claude_agent()` — pre-warms the ClaudeAgent singleton (Anthropic client created)

Both pre-warming calls are wrapped in `try/except` with `logger.warning` on failure — the service starts even if the MerusCase token is not yet available.

**Shutdown:** Attempts to close the MerusAgent's HTTP client gracefully.

**CORS:** Origins from `CORS_ORIGINS` env var (comma-separated), defaults to `localhost:3000,localhost:3001`.

**Static frontend:** If a `static/` directory exists (created during Docker build), the service mounts it and serves `index.html` for all non-API routes (SPA catch-all).

### 9.2 Registered Routers

| Router | Prefix | Purpose |
|--------|--------|---------|
| `health` | `/health` | Health check endpoint |
| `cases` | `/api/cases` | Case lookup REST endpoints |
| `billing` | `/api/billing` | Billing REST endpoints |
| `activities` | `/api/activities` | Activity REST endpoints |
| `reference` | `/api/reference` | Billing codes, activity types |
| `agent` | `/api/agent` | Claude AI agent (SSE) |
| `chat` | `/api/chat` | Matter creation chat flow |
| `matter` | `/api/matter` | Matter submission |

### 9.3 Agent Route: POST /api/agent/chat

**File:** `service/routes/agent.py`

```python
@router.post("/chat")
async def agent_chat(
    request: ChatRequest,
    _: str = Depends(verify_api_key),
    agent: ClaudeAgent = Depends(get_claude_agent),
):
```

**Request body (`ChatRequest`):**

| Field | Type | Default | Validation | Description |
|-------|------|---------|------------|-------------|
| `messages` | `List[dict]` | required | — | Conversation history: `[{"role": "user"/"assistant", "content": "..."}]` |
| `max_iterations` | `int` | `10` | `ge=1, le=20` | Maximum tool-use cycles |

**Response:** `StreamingResponse` with `media_type="text/event-stream"`, `Cache-Control: no-cache`, `X-Accel-Buffering: no`.

The route wraps `agent.chat_stream` in an `event_stream` async generator and converts all events to SSE wire format. An outer `try/except` catches any route-level exception and emits a final error event before the stream closes.

### 9.4 Authentication

**File:** `service/auth.py`

Service-level auth uses the `X-API-Key` header checked against the `MERUS_API_KEY` environment variable. This is separate from MerusCase OAuth — it protects the service endpoints from unauthorized callers.

```
Request arrives
  ↓
verify_api_key(x_api_key: Optional[str] = Header(None))
  ↓ if missing → HTTP 401: "Missing API key. Include X-API-Key header."
  ↓ if wrong  → HTTP 401: "Invalid API key"
  ↓ if correct → returns key string (used as Depends return value)
```

The `/health` endpoint is the only unprotected route (it does not use `verify_api_key` as a dependency).

### 9.5 Dependency Injection

**File:** `service/dependencies.py`

Both agent classes are singletons managed via `@lru_cache(maxsize=1)`. FastAPI calls these functions on first request and returns the cached instance on all subsequent calls.

```python
@lru_cache(maxsize=1)
def get_merus_agent() -> MerusAgent:
    access_token = os.environ.get("MERUSCASE_ACCESS_TOKEN")
    token_file = os.environ.get("MERUSCASE_TOKEN_FILE", ".meruscase_token")
    return MerusAgent(
        access_token=access_token,
        token_file=token_file if not access_token else None,
        cache_ttl_seconds=int(os.environ.get("CACHE_TTL_SECONDS", 3600)),
    )

@lru_cache(maxsize=1)
def get_claude_agent() -> ClaudeAgent:
    client = anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return ClaudeAgent(anthropic_client=client, merus_agent=get_merus_agent())
```

`ClaudeAgent` calls `get_merus_agent()` internally — both share the same `MerusAgent` singleton.

### 9.6 Global Exception Handlers

These handlers convert `MerusAgent` exceptions into HTTP responses for the non-streaming REST endpoints. Within the SSE stream, these exceptions are caught earlier by `dispatch_tool`.

| Exception | HTTP Status | Response body |
|-----------|-------------|---------------|
| `CaseNotFoundError` | 404 | `{"error": "Case not found", "detail": "..."}` |
| `BillingError` | 400 | `{"error": "Billing error", "detail": "..."}` |
| `MerusAgentError` | 500 | `{"error": "MerusAgent error", "detail": "..."}` |

---

## 10. Frontend Integration

### 10.1 SSE Client

**File:** `frontend/src/lib/api/agent.ts`

`streamAgentChat` is an async generator function that wraps the SSE HTTP connection. It uses the Fetch API's `ReadableStream` directly — no `EventSource` (which doesn't support POST or custom headers).

```typescript
export async function* streamAgentChat(
  messages: AgentMessage[],
  maxIterations?: number
): AsyncGenerator<AgentStreamEvent>
```

**Internal behavior:**

1. `fetch('/api/agent/chat', {method: 'POST', headers: getHeaders(), body: JSON.stringify({...})})`
2. On non-2xx response: yields `{type: "error", message: err.detail || "HTTP N"}` and returns
3. Obtains `response.body.getReader()`
4. Reads chunks in a `while(true)` loop, decodes with `TextDecoder({stream: true})`
5. Buffers partial lines — splits on `\n`, keeps last partial chunk in `buffer`
6. For each complete line: checks `data: ` prefix, strips it, skips `[DONE]`, parses JSON
7. Yields the parsed `AgentStreamEvent` — malformed JSON lines are silently skipped
8. `finally` block releases the reader lock

### 10.2 `AgentStreamEvent` Type

**File:** `frontend/src/lib/types.ts`

```typescript
export type AgentStreamEvent =
  | { type: 'text'; content: string }
  | { type: 'tool_call'; name: string; input: Record<string, unknown> }
  | { type: 'tool_result'; name: string; result: Record<string, unknown> }
  | { type: 'done' }
  | { type: 'error'; message: string }
```

This is a TypeScript discriminated union — consumers use `event.type` to narrow to the correct variant.

### 10.3 `useAgent` Hook

**File:** `frontend/src/hooks/useAgent.ts`

The primary state management hook for the AI assistant. Exposes a clean API to the UI layer.

**State shape:**

| Field | Type | Description |
|-------|------|-------------|
| `messages` | `AgentMessage[]` | Completed conversation turns (user + assistant) |
| `events` | `AgentStreamEvent[]` | Live events for the current in-progress turn |
| `streaming` | `boolean` | True while a stream is in progress |
| `error` | `string \| null` | Last error message, if any |

**Exposed methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `sendMessage` | `(content: string) => Promise<void>` | Appends user message, starts streaming, accumulates text into assistant message on completion |
| `stop` | `() => void` | Sets abort flag — streaming loop breaks on next iteration |
| `reset` | `() => void` | Sets abort flag and clears all state |

**`sendMessage` flow:**

```
1. Set abortRef.current = false
2. Build userMsg = {role: "user", content}
3. setState: append userMsg, clear events, set streaming=true, clear error
4. for await (event of streamAgentChat(updatedMessages)):
     if abortRef.current: break
     events.push(event)
     if event.type == "text": assistantContent += event.content
     setState: events=[...events]
     if event.type == "done" or "error":
       if "error": setState({error: event.message})
       break
5. if assistantContent:
     setState: append assistantMsg to messages
6. catch: setState({error: err.message})
7. finally: setState({streaming: false})
```

The abort mechanism uses `useRef` (not state) to avoid stale closure issues — `stop()` and `reset()` set `abortRef.current = true` and the streaming loop checks it on every iteration.

### 10.4 UI Components

#### `AIAssistantPage`

**File:** `frontend/src/components/pages/AIAssistant/AIAssistantPage.tsx`

Top-level page component for the AI assistant.

**Guard:** Checks `useSettingsStore(s => s.isConfigured)()` — if the API key is not configured, renders a card with a "Go to Settings" button instead of the chat interface.

**Welcome screen:** Shown when `messages.length === 0 && !streaming`. Displays a Bot icon, description text, and three suggestion chips:
- "Find the Smith case"
- "Show my active cases"
- "Bill 0.5 hours to case WC-2024-001"

Clicking a chip copies the text into the input field.

**Message list:** Renders completed `messages` as `<AgentMessage>` components, then a live `<AgentMessage>` for the current streaming turn (accumulating `streamingText` from `text` events). A `<StreamingIndicator>` (animated dots) appears while waiting for the first event.

**Input bar:** Textarea with `Enter` to send, `Shift+Enter` for newline. Disabled during streaming. Reset button (RotateCcw icon) calls `reset()`.

**Auto-scroll:** `useEffect` on `[messages, events]` calls `bottomRef.current?.scrollIntoView({behavior: 'smooth'})`.

#### `ToolCallCard`

**File:** `frontend/src/components/pages/AIAssistant/ToolCallCard.tsx`

Collapsible card rendered for each `tool_call` event in the live events list.

**Props:**
- `toolCall`: `Extract<AgentStreamEvent, {type: 'tool_call'}>` — the call event
- `toolResult?`: `Extract<AgentStreamEvent, {type: 'tool_result'}>` — the result event (absent while pending)

**Status indicators:**
- No result yet: amber pulsing circle (pending)
- Result with `result.error` key: red XCircle
- Result without error: green CheckCircle

**Expanded view:** Shows `Input` and `Result` sections as formatted JSON (`JSON.stringify(x, null, 2)`) in `<pre>` blocks with max height and overflow scroll. Result block uses red background if there is an error.

---

## 11. Configuration

All configuration is via environment variables. The service does not use a config file — values are read at startup.

### 11.1 Required Variables

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Claude API key (from Anthropic console) |
| `MERUS_API_KEY` | Service endpoint API key — included in `X-API-Key` header by frontend |
| `MERUSCASE_ACCESS_TOKEN` | MerusCase OAuth Bearer token. Required unless a valid `.meruscase_token` file is present |

### 11.2 Optional Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MERUSCASE_TOKEN_FILE` | `.meruscase_token` | Path to file containing MerusCase token (fallback if `MERUSCASE_ACCESS_TOKEN` is not set) |
| `CACHE_TTL_SECONDS` | `3600` | TTL for reference data cache (billing codes, activity types) |
| `LOG_LEVEL` | `INFO` | Python logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `CORS_ORIGINS` | `http://localhost:3000,http://localhost:3001` | Comma-separated list of allowed CORS origins |
| `DB_PATH` | `./knowledge/db/merus_knowledge.db` | SQLite database path |
| `PORT` | `8000` | Server listen port |
| `GOOGLE_API_KEY` | _(unset)_ | Gemini API key — used by `IntelligentParser` service if enabled |

### 11.3 Token Priority

```
MerusAgent init:
  if MERUSCASE_ACCESS_TOKEN is set:
    use it directly (token_file is ignored)
  elif MERUSCASE_TOKEN_FILE exists:
    read token from file
  else:
    raise MerusAgentError("No access token provided")
```

### 11.4 Example `.env`

```bash
# Required
ANTHROPIC_API_KEY=sk-ant-...
MERUS_API_KEY=your-service-key-here
MERUSCASE_ACCESS_TOKEN=your-meruscase-oauth-token

# Optional overrides
CACHE_TTL_SECONDS=3600
LOG_LEVEL=INFO
CORS_ORIGINS=http://localhost:3000,https://your-domain.com
PORT=8000
```

---

## 12. Error Handling

The agent system uses a layered error strategy. Each layer has a defined behavior — errors never silently disappear and never crash the stream.

### 12.1 Layer-by-Layer Strategy

| Layer | File | Strategy |
|-------|------|----------|
| `MerusCaseAPIClient._request` | `api_client/client.py` | Always returns `APIResponse` — never raises. Network errors, timeouts, HTTP errors, and CakePHP validation errors all become `APIResponse(success=False, ...)`. |
| `MerusAgent` methods | `core/agent.py` | Checks `response.success`. On failure: raises typed exception (`CaseNotFoundError`, `BillingError`, or `MerusAgentError`). |
| `dispatch_tool` | `agent/tools.py` | `try/except Exception` wraps all `MerusAgent` calls. Returns `{"error": str(e)}` on any failure. Never raises. |
| `ClaudeAgent.chat_stream` | `agent/claude_agent.py` | Catches `anthropic.APIError` → yields `{"type": "error", "message": "API error: ..."}` and returns. |
| FastAPI route `event_stream` | `routes/agent.py` | Outer `try/except Exception` around `agent.chat_stream` iteration → yields error event. |
| FastAPI global handlers | `service/main.py` | Catches `CaseNotFoundError` (404), `BillingError` (400), `MerusAgentError` (500) for non-streaming REST endpoints. |
| Frontend `useAgent.sendMessage` | `hooks/useAgent.ts` | Sets `state.error` on `error` events from stream. `catch` block catches generator failures and sets error state. |

### 12.2 Error Flow for a Write Failure

Example: user asks to bill time, but the MerusCase API rejects it.

```
MerusCaseAPIClient._request()
  → HTTP 200 with {"errors": [{"errorMessage": "Invalid billing code"}]}
  → returns APIResponse(success=False, error="[api_error] Invalid billing code")

MerusAgent.bill_time()
  → checks response.success == False
  → raises BillingError("Failed to bill time: [api_error] Invalid billing code")

dispatch_tool("bill_time", ...)
  → except Exception as e:
  → returns {"error": "Failed to bill time: [api_error] Invalid billing code"}

ClaudeAgent.chat_stream (iteration N)
  → tool_result event: {"type": "tool_result", "name": "bill_time", "result": {"error": "..."}}
  → Claude receives this as tool result content
  → Claude generates text explaining the failure and suggesting correction
  → yields text events with Claude's explanation
  → yields done event

Frontend useAgent
  → renders ToolCallCard with red XCircle
  → renders Claude's error explanation as assistant message
  → state.error remains null (stream ended cleanly with "done")
```

### 12.3 Max Iterations Reached

If Claude requires more than `max_iterations` tool calls to answer a question:

```
ClaudeAgent.chat_stream
  → loop exhausted
  → yield {"type": "error", "message": "Max iterations (10) reached"}
  → return

Frontend useAgent
  → event.type == "error" → setState({error: "Max iterations (10) reached"})
  → break out of stream loop
  → displays error message below chat
```

---

## 13. File Map

All source files in the MerusExpert agent system, organized by layer.

### Core Package (`src/merus_expert/`)

| File | Description |
|------|-------------|
| `agent/claude_agent.py` | `ClaudeAgent` — Anthropic streaming API, tool-use loop, SSE event yielding |
| `agent/tools.py` | `TOOLS` list (13 Anthropic tool definitions), `dispatch_tool()` |
| `agent/system_prompt.py` | `get_system_prompt()` — assembles prompt from knowledge files, `@lru_cache` |
| `agent/__init__.py` | Package init |
| `core/agent.py` | `MerusAgent` — business logic, fuzzy search, caching, typed exceptions |
| `core/__init__.py` | Package init |
| `api_client/client.py` | `MerusCaseAPIClient` — httpx HTTP client, all endpoint methods, `_request()` |
| `api_client/models.py` | Pydantic models: `Party`, `Activity`, `LedgerEntry`, `Document`, `CaseFile`, `APIResponse`, `OAuthToken` |
| `api_client/__init__.py` | Package init |

### Service Layer (`service/`)

| File | Description |
|------|-------------|
| `main.py` | FastAPI app factory, lifespan, CORS, global exception handlers, static SPA serving |
| `auth.py` | `verify_api_key()` — `X-API-Key` header validation |
| `dependencies.py` | `get_merus_agent()`, `get_claude_agent()` — `@lru_cache` singletons |
| `routes/agent.py` | `POST /api/agent/chat` — SSE streaming route |
| `routes/cases.py` | Case lookup REST endpoints |
| `routes/billing.py` | Billing REST endpoints |
| `routes/activities.py` | Activity REST endpoints |
| `routes/reference.py` | Billing codes, activity types endpoints |
| `routes/health.py` | `GET /health` |
| `routes/chat.py` | Matter creation chat flow |
| `routes/matter.py` | Matter submission endpoint |
| `routes/__init__.py` | Package init |
| `models/requests.py` | `ChatRequest`, `BillTimeRequest`, `AddCostRequest`, `AddNoteRequest`, `BulkBillTimeRequest`, `CreateSessionRequest`, `ChatMessageRequest`, `SubmitMatterRequest` |
| `models/responses.py` | Response models |
| `models/__init__.py` | Package init |
| `services/chat_store.py` | Chat session persistence |
| `services/billing_store.py` | Billing entry persistence |
| `services/billing_flow.py` | Billing workflow logic |
| `services/conversation_flow.py` | Matter creation conversation logic |
| `services/intelligent_parser.py` | Gemini-based NLP for matter field extraction |
| `services/__init__.py` | Package init |

### Frontend (`frontend/src/`)

| File | Description |
|------|-------------|
| `lib/api/agent.ts` | `streamAgentChat()` — SSE async generator, Fetch API + ReadableStream |
| `lib/types.ts` | All TypeScript types including `AgentStreamEvent`, `AgentMessage`, case/billing/activity types |
| `hooks/useAgent.ts` | `useAgent()` — React state hook for conversation, streaming, abort control |
| `components/pages/AIAssistant/AIAssistantPage.tsx` | Full chat page — auth guard, welcome screen, message list, input bar |
| `components/pages/AIAssistant/AgentMessage.tsx` | Message bubble component — renders text and tool call cards |
| `components/pages/AIAssistant/ToolCallCard.tsx` | Collapsible tool call card — pending/success/error states, expandable JSON |
| `components/pages/AIAssistant/StreamingIndicator.tsx` | Animated dots shown while waiting for first stream event |

### Knowledge Base (`knowledge/`)

| File | Description |
|------|-------------|
| `docs/MERUSCASE_API_REFERENCE.md` | MerusCase API field reference embedded in system prompt |
| `docs/MERUS_AGENT_SUMMARY.md` | Agent operational summary embedded in system prompt |
| `billing_codes.json` | Available billing codes (JSON) embedded in system prompt |
| `db/merus_knowledge.db` | SQLite database (11 tables, initialized from `setup/schema.sql`) |

---

*For company-wide development standards, see the main CLAUDE.md at `~/Desktop/CLAUDE.md`.*

*For the MerusExpert browser automation framework documentation, see `CLAUDE.md` and `README.md` at the project root.*

---

<!-- @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology -->
