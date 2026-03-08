# MerusExpert Agent — Capabilities Reference

**Last Updated:** 2026-02-19
**Model:** claude-sonnet-4-6
**Protocol:** Anthropic tool-use loop with SSE streaming
**Max Iterations per turn:** 10 tool calls before hard stop

> MerusExpert is a Claude-powered AI agent that speaks natural language and translates
> requests into MerusCase API operations. It is the interface layer between attorneys/staff
> and the raw MerusCase REST API.

---

## What the Agent Can Do

### Read Operations (Pull)

| Capability | Natural Language Examples | Tool Used |
|------------|--------------------------|-----------|
| **Find a case** by name or file number | "Find the Smith case" / "Look up WC-2024-001" | `find_case` |
| **Get full case details** | "Show me everything on case 56171871" | `get_case_details` |
| **Get billing/ledger entries** | "What's been billed to the Andrews case?" / "Show billing for December" | `get_case_billing` |
| **Get activities and notes** | "What activities are on the Smith case?" | `get_case_activities` |
| **Get parties** | "Who are the parties on the Jones matter?" | `get_case_parties` |
| **List all cases** | "List all open WC cases" / "Show me closed cases" | `list_cases` |
| **Billing summary with totals** | "Summarize billing for Smith case this month" | `get_billing_summary` |
| **Look up billing codes** | "What billing codes are available?" | `get_billing_codes` |
| **Look up activity types** | "What activity types can I use?" | `get_activity_types` |

### Write Operations (Push)

| Capability | Natural Language Examples | Tool Used |
|------------|--------------------------|-----------|
| **Bill time** | "Bill 0.2 hours to Smith for reviewing medical records" | `bill_time` |
| **Add a cost/fee** | "Add a $25 WCAB filing fee to Jones" | `add_cost` |
| **Add a note** | "Add a note to Andrews: client called about hearing date" | `add_note` |
| **Upload a document** | "Upload /path/to/report.pdf to the Smith case" | `upload_document` |

---

## Tool Definitions (13 total)

### 1. `find_case`
Fuzzy search for a case by file number or party name.
```
Inputs:
  search (required): case file number or party name
  limit (optional, default 50): how many cases to search through

Search priority:
  1. Exact file number match
  2. Partial file number match
  3. Partial party name match

Returns: first matching case dict, or CaseNotFoundError
```

### 2. `get_case_details`
Retrieve full CaseFile record by numeric ID.
```
Inputs:
  case_id (required): numeric MerusCase case file ID

Returns: full CaseFile object (all fields — see field reference)
```

### 3. `get_case_billing`
Retrieve open ledger entries for a case, optionally filtered by date.
```
Inputs:
  case_id (required): numeric case file ID
  date_gte (optional): start date filter (YYYY-MM-DD)
  date_lte (optional): end date filter (YYYY-MM-DD)

Returns: ledger entries dict keyed by ledger ID
Note: Uses /caseLedgersOpen/index (open, un-reviewed entries only)
```

### 4. `get_case_activities`
Retrieve activity log for a case.
```
Inputs:
  case_id (required): numeric case file ID
  limit (optional, default 100): max results

Returns: list of activity dicts
Note: Activities use numeric key names in raw API — agent normalizes these
```

### 5. `get_case_parties`
Retrieve all parties on a case.
```
Inputs:
  case_id (required): numeric case file ID

Returns: list of party dicts including insurance fields, contact info
```

### 6. `list_cases`
List all cases with optional status/type filters.
```
Inputs:
  case_status (optional): filter by status name, e.g. "Open", "Closed"
  case_type (optional): filter by type name, e.g. "Workers Compensation"
  limit (optional, default 100): max results

Returns: normalized list of case dicts with 'id' field guaranteed
```

### 7. `get_billing_summary`
Compute billing totals for a case, found by name search.
```
Inputs:
  case_search (required): file number or party name
  start_date (optional): YYYY-MM-DD
  end_date (optional): YYYY-MM-DD

Returns: {
  case_id, case_name,
  total_amount (float — NOTE: negative per MerusCase convention),
  total_entries (int),
  entries (dict),
  start_date, end_date
}
```

### 8. `bill_time`
Create a billable activity entry (time billing).
```
Inputs:
  case_search (required): file number or party name
  hours (required): time in hours (MUST be multiple of 0.1, e.g. 0.2 for 12 min)
  description (required): detailed description of work
  subject (optional): short subject line (defaults to first 50 chars of description)
  activity_type_id (optional): defaults to Manual Entry (100)
  billing_code_id (optional): links to billing code

How it works:
  1. Calls find_case(case_search) to get case_id
  2. Converts hours → minutes (hours * 60)
  3. POSTs to /activities/add with billable=1
  4. Returns {success, activity_id, case_id, case_name, hours, minutes, description}

⚠️ hours must be a multiple of 0.1. 0.25 will fail API validation.
⚠️ This creates an ACTIVITY, not a ledger entry. Use add_cost for dollar amounts.
```

### 9. `add_cost`
Create a ledger entry for direct costs (not time-based).
```
Inputs:
  case_search (required): file number or party name
  amount (required): dollar amount (e.g. 25.00)
  description (required): entry description
  ledger_type (optional, default "cost"): "fee", "cost", or "expense"

Type mapping:
  "fee"     → ledger_type_id: 1 (FEE)
  "cost"    → ledger_type_id: 2 (COST)
  "expense" → ledger_type_id: 3 (EXPENSE)

How it works:
  1. Calls find_case(case_search) to get case_id
  2. POSTs to /caseLedgers/add with amount only (no hours/hourly_rate)
  3. Returns {success, ledger_id, case_id, case_name, amount, description, type}

⚠️ Use for filing fees, court costs, expenses — NOT for time billing.
⚠️ amount is stored as negative in MerusCase (e.g., "25.00" → -25).
```

### 10. `add_note`
Create a non-billable activity note.
```
Inputs:
  case_search (required): file number or party name
  subject (required): note subject / title
  description (optional): full note text
  activity_type_id (optional): defaults to Note (101)

How it works:
  1. Calls find_case(case_search) to get case_id
  2. POSTs to /activities/add with billable=0
  3. Returns {success, activity_id, case_id, case_name, subject}
```

### 11. `upload_document`
Upload a file to a case.
```
Inputs:
  case_search (required): file number or party name
  file_path (required): absolute local path to file
  description (optional): document description
  folder_id (optional): target folder within case

How it works:
  1. Calls find_case(case_search) to get case_id
  2. POSTs file to /uploads/add (multipart)
  3. Returns {success, case_id, filename, data}
```

### 12. `get_billing_codes`
List available billing codes. Cached for 1 hour.
```
Returns: dict of billing codes keyed by ID
{
  "107105": {
    "id": 107105,
    "description": "Test billing code",
    "ledger_disposition": "BILLABLE",
    "task_code": "None", ...
  }
}
```

### 13. `get_activity_types`
List available activity types. Cached for 1 hour.
```
Returns: dict of activity types keyed by ID
Use to look up IDs like 100 (Manual Entry), 101 (Note), 111 (Telephone Call), etc.
```

---

## Agent Behavior Rules

1. **Confirm before writing** — Before calling `bill_time`, `add_cost`, or `add_note`, the agent confirms details with the user unless they've already been confirmed in the conversation.

2. **Never exposes internals** — Does not mention CakePHP, API endpoints, or raw JSON to users. All errors are translated to plain English.

3. **Fuzzy case search** — Accepts case references like `"Smith"`, `"the Jones matter"`, `"WC-2024-001"`, or `"85"` (file number). The `find_case` tool handles all formats.

4. **Error recovery** — If any tool returns `{"error": "..."}`, the agent explains the error in plain language and suggests next steps.

5. **Date format** — Uses `YYYY-MM-DD` internally. Accepts natural language from users ("last month", "December 2025") and converts.

6. **Currency display** — Always formats amounts with `$` and two decimal places.

7. **Max 10 tool calls per turn** — After 10 iterations, the agent returns an error. For bulk operations, use `bulk_bill_time` directly via the Python API.

---

## SSE Event Protocol

The agent streams events over Server-Sent Events (SSE):

```json
{ "type": "text",        "content": "Looking up the Smith case..." }
{ "type": "tool_call",   "name": "find_case", "input": {"search": "Smith"} }
{ "type": "tool_result", "name": "find_case", "result": {"id": 56171871, ...} }
{ "type": "text",        "content": "Found it! ANDREWS, DENNIS..." }
{ "type": "done" }
```

Error event:
```json
{ "type": "error", "message": "API error: 401 Unauthorized" }
```

---

## System Context (loaded at startup)

The agent's system prompt is assembled from:

| Source | Path | Content |
|--------|------|---------|
| API Reference | `knowledge/docs/MERUSCASE_API_REFERENCE.md` | Endpoint catalog |
| Agent Summary | `knowledge/docs/MERUS_AGENT_SUMMARY.md` | Business context |
| Billing Codes | `knowledge/billing_codes.json` | All billing code definitions |

All three are loaded once at process startup via `@lru_cache`.

---

## Bulk Operations (Python API only)

Not exposed via Claude tool-use, but available directly on `MerusAgent`:

```python
# Bill time to multiple cases in one call
results = await agent.bulk_bill_time([
    {"case_search": "Smith", "hours": 0.2, "description": "Review records"},
    {"case_search": "Jones", "hours": 0.5, "description": "Draft demand letter"},
    {"case_search": "Andrews", "hours": 1.0, "description": "MSC preparation"},
])
# Returns list of results; individual failures don't stop the batch
```

---

## Caching

| Data | TTL | Notes |
|------|-----|-------|
| Billing codes | 1 hour | `get_billing_codes()` |
| Activity types | 1 hour | `get_activity_types()` |
| System prompt | Process lifetime | `@lru_cache`, rebuilt on restart |
| Case/ledger/activity data | None | Always fetched live |

---

## Quick Start (Python)

```python
import anthropic
from merus_expert.core.agent import MerusAgent
from merus_expert.agent.claude_agent import ClaudeAgent

# Initialize
merus = MerusAgent(token_file=".meruscase_token")
claude = ClaudeAgent(
    anthropic_client=anthropic.AsyncAnthropic(api_key="..."),
    merus_agent=merus,
)

# Stream a conversation turn
messages = [{"role": "user", "content": "Bill 0.2 hours to Smith for reviewing records"}]
async for event in claude.chat_stream(messages):
    if event["type"] == "text":
        print(event["content"], end="", flush=True)
    elif event["type"] == "done":
        print()
```

### Quick convenience functions (no agent instantiation)
```python
from merus_expert.core.agent import quick_bill_time, quick_add_cost

# Bill time
result = await quick_bill_time("Smith", 0.2, "Review medical records")

# Add cost
result = await quick_add_cost("Andrews", 25.00, "WCAB Filing Fee")
```

---

## Known Limitations

| Limitation | Workaround |
|------------|------------|
| `hours` must be multiple of 0.1 | Round to nearest 0.1 before calling `bill_time` |
| No case creation via API | Use Playwright browser automation (`/caseFiles/add` is a JS SPA) |
| `find_case` searches first 50 cases by default | Increase `limit` parameter |
| `get_case_billing` only returns open ledgers | Use `caseLedgers/index` directly for all entries |
| No party update support | Add new party record; no PATCH endpoint confirmed |
| No event/task creation tools | Available in MerusCase API (`/events/add`, `/tasks/add`) but not wired to agent tools yet |
| `trustAccounts/index` returns non-JSON | Known MerusCase API bug; not usable |

---

*@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology*
