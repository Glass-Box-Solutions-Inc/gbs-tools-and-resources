# Test Plan — cli-anything-meruscase

## Test Inventory

| File | Type | Count | Coverage |
|------|------|-------|---------|
| `test_core.py` | Unit | 18 | session token loading, undo/redo stack, case fuzzy search, billing math |
| `test_full_e2e.py` | E2E/subprocess | 14 (11 no-creds + 3 integration) | CLI invocation, auth status, JSON output, real API |

## Unit Test Plan (`test_core.py`)

### TestSessionTokenLoading (4 tests)

- `test_load_token_from_env_var` — env var returns token when GCP falls through
- `test_load_token_from_file` — file fallback when env var absent and GCP unavailable
- `test_load_token_returns_none_when_nothing` — graceful None return when no source has a token
- `test_save_token_writes_file` — token written to disk at the patched TOKEN_FILE path

### TestMerusCaseSessionUndoRedo (7 tests)

- `test_snapshot_and_undo` — state restored after undo
- `test_undo_empty_stack_returns_none` — safe on empty stack
- `test_redo_after_undo` — redo restores undone state
- `test_redo_empty_returns_none` — safe on empty redo stack
- `test_snapshot_trims_to_max_50` — stack never exceeds 50 entries
- `test_snapshot_clears_redo` — new change invalidates redo history
- `test_is_modified_after_snapshot` — modified flag set correctly

### TestCaseFuzzySearch (3 tests)

- `test_find_by_exact_file_number` — exact file number match
- `test_find_by_party_name_substring` — case-insensitive primary_party_name match
- `test_raises_case_not_found` — CaseNotFoundError on no match

### TestBillingCalculations (4 tests)

- `test_bill_time_converts_hours_to_minutes` — hours × 60 = minutes; payload carries duration_minutes
- `test_bill_time_auto_subject` — subject auto-truncated to ≤60 chars from description
- `test_add_cost_maps_ledger_type` — "fee" → ledger_type_id=1 in the add_ledger payload
- `test_billing_summary_totals` — total_amount sums all entry amounts; total_entries matches count

## E2E Test Plan (`test_full_e2e.py`)

### TestCLIInvocation (9 tests — no credentials required)

Tests all command groups respond to `--help` with exit code 0 and contain expected subcommand names.
Uses `_resolve_cli()` — works whether installed as a script or run via `python3 -m`.

- `test_help_exits_zero` — root `--help` exits 0 and mentions "MerusCase"
- `test_case_help` — `case --help` lists list/find/get/create
- `test_billing_help` — `billing --help` lists bill-time/add-cost
- `test_json_flag_on_help` — `--json --help` accepted without error
- `test_auth_help` — `auth --help` lists login/status
- `test_session_help` — `session --help` exits 0
- `test_document_help` — `document --help` lists upload/list
- `test_party_help` — `party --help` exits 0
- `test_resolve_cli_finds_command` — `_resolve_cli()` returns non-empty list

### TestCLIAuthStatus (2 tests — no credentials required)

- `test_auth_status_no_crash` — no Python traceback on missing/empty token
- `test_auth_status_json` — `--json auth status` with fake token emits valid JSON with `status` key

### TestIntegration (3 tests — marked `integration`, skip if no token)

- `test_case_list_returns_json` — real API call, list of cases is a JSON array
- `test_auth_status_with_token` — authenticated status confirmed against live API
- `test_session_status_json` — session status JSON includes `token_present` and `undo_stack_depth`

## Running Tests

```bash
# From agent-harness/ directory
cd packages/cli-anything/meruscase/agent-harness

# Install in editable mode
pip3 install -e .
pip3 install pytest pytest-asyncio httpx

# Unit tests only (no credentials needed)
python3 -m pytest cli_anything/meruscase/tests/test_core.py -v

# All tests except integration (no credentials needed)
python3 -m pytest cli_anything/meruscase/tests/ -v -m "not integration"

# All tests including real API (requires MERUSCASE_ACCESS_TOKEN)
MERUSCASE_ACCESS_TOKEN=<token> python3 -m pytest cli_anything/meruscase/tests/ -v

# Short traceback format
python3 -m pytest cli_anything/meruscase/tests/ -v --tb=short
```

## Test Results

### Unit tests — 2026-04-12

```
============================= test session starts ==============================
platform linux -- Python 3.10.12, pytest-9.0.2, pluggy-1.6.0
configfile: pytest.ini
plugins: anyio-4.13.0, asyncio-1.3.0, Faker-34.0.2
asyncio: mode=auto
collected 18 items

cli_anything/meruscase/tests/test_core.py::TestSessionTokenLoading::test_load_token_from_env_var PASSED
cli_anything/meruscase/tests/test_core.py::TestSessionTokenLoading::test_load_token_from_file PASSED
cli_anything/meruscase/tests/test_core.py::TestSessionTokenLoading::test_load_token_returns_none_when_nothing PASSED
cli_anything/meruscase/tests/test_core.py::TestSessionTokenLoading::test_save_token_writes_file PASSED
cli_anything/meruscase/tests/test_core.py::TestMerusCaseSessionUndoRedo::test_snapshot_and_undo PASSED
cli_anything/meruscase/tests/test_core.py::TestMerusCaseSessionUndoRedo::test_undo_empty_stack_returns_none PASSED
cli_anything/meruscase/tests/test_core.py::TestMerusCaseSessionUndoRedo::test_redo_after_undo PASSED
cli_anything/meruscase/tests/test_core.py::TestMerusCaseSessionUndoRedo::test_redo_empty_returns_none PASSED
cli_anything/meruscase/tests/test_core.py::TestMerusCaseSessionUndoRedo::test_snapshot_trims_to_max_50 PASSED
cli_anything/meruscase/tests/test_core.py::TestMerusCaseSessionUndoRedo::test_snapshot_clears_redo PASSED
cli_anything/meruscase/tests/test_core.py::TestMerusCaseSessionUndoRedo::test_is_modified_after_snapshot PASSED
cli_anything/meruscase/tests/test_core.py::TestCaseFuzzySearch::test_find_by_exact_file_number PASSED
cli_anything/meruscase/tests/test_core.py::TestCaseFuzzySearch::test_find_by_party_name_substring PASSED
cli_anything/meruscase/tests/test_core.py::TestCaseFuzzySearch::test_raises_case_not_found PASSED
cli_anything/meruscase/tests/test_core.py::TestBillingCalculations::test_bill_time_converts_hours_to_minutes PASSED
cli_anything/meruscase/tests/test_core.py::TestBillingCalculations::test_bill_time_auto_subject PASSED
cli_anything/meruscase/tests/test_core.py::TestBillingCalculations::test_add_cost_maps_ledger_type PASSED
cli_anything/meruscase/tests/test_core.py::TestBillingCalculations::test_billing_summary_totals PASSED

============================== 18 passed in 0.24s ==============================
```

### E2E tests (no credentials) — 2026-04-12

```
============================= test session starts ==============================
platform linux -- Python 3.10.12, pytest-9.0.2, pluggy-1.6.0
configfile: pytest.ini
plugins: anyio-4.13.0, asyncio-1.3.0, Faker-34.0.2
asyncio: mode=auto
collected 14 items / 3 deselected / 11 selected

cli_anything/meruscase/tests/test_full_e2e.py::TestCLIInvocation::test_help_exits_zero PASSED
cli_anything/meruscase/tests/test_full_e2e.py::TestCLIInvocation::test_case_help PASSED
cli_anything/meruscase/tests/test_full_e2e.py::TestCLIInvocation::test_billing_help PASSED
cli_anything/meruscase/tests/test_full_e2e.py::TestCLIInvocation::test_json_flag_on_help PASSED
cli_anything/meruscase/tests/test_full_e2e.py::TestCLIInvocation::test_auth_help PASSED
cli_anything/meruscase/tests/test_full_e2e.py::TestCLIInvocation::test_session_help PASSED
cli_anything/meruscase/tests/test_full_e2e.py::TestCLIInvocation::test_document_help PASSED
cli_anything/meruscase/tests/test_full_e2e.py::TestCLIInvocation::test_party_help PASSED
cli_anything/meruscase/tests/test_full_e2e.py::TestCLIInvocation::test_resolve_cli_finds_command PASSED
cli_anything/meruscase/tests/test_full_e2e.py::TestCLIAuthStatus::test_auth_status_no_crash PASSED
cli_anything/meruscase/tests/test_full_e2e.py::TestCLIAuthStatus::test_auth_status_json PASSED

======================= 11 passed, 3 deselected in 4.77s =======================
```

**Total: 29 tests written. 29 runnable tests passed (18 unit + 11 E2E no-creds). 3 integration tests skipped pending real credentials.**

## Browser Automation

Case creation uses **Browserless** cloud browser (wss://production-sfo.browserless.io) instead of a local headless Chromium. Browserless bypasses MerusCase's reCAPTCHA protection that blocks standard headless sessions.

**Browserless token requirement:** Set `BROWSERLESS_API_TOKEN` env var, or ensure the GCP ADC identity has access to `adjudica-internal/merus-expert-browserless-token`.

**No `playwright install chromium` needed** for MerusCase operations — the browser runs remotely on Browserless. The `playwright` Python package (pip install) is still required for the async CDP connection API.

**Credentials source:** `adjudica-production` GCP project (`meruscase-email`, `meruscase-password`), or `adjudica-internal` as fallback (`merus-expert-meruscase-email`, `merus-expert-meruscase-password`), or `MERUSCASE_EMAIL`/`MERUSCASE_PASSWORD` env vars.
