# MerusCase API Reference

**Last Updated:** 2026-01-13
**API Base URL:** `https://api.meruscase.com`
**Authentication:** OAuth 2.0 Bearer Token

---

## Quick Start

```python
import httpx

TOKEN = "your_access_token"
API_BASE = "https://api.meruscase.com"

async with httpx.AsyncClient(
    headers={"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"},
    timeout=30.0
) as client:
    resp = await client.get(f"{API_BASE}/caseFiles/index")
    data = resp.json()
```

---

## Endpoint Categories

### Case Management

| Endpoint | Method | Description | Status |
|----------|--------|-------------|--------|
| `caseFiles/index` | GET | List all cases | Documented |
| `caseFiles/view/{id}` | GET | View case details | Documented |
| `caseTypes/index` | GET | List case types | Documented |
| `caseStatuses/index` | GET | List case statuses | **Undocumented** |

### Activities & Events

| Endpoint | Method | Description | Status |
|----------|--------|-------------|--------|
| `activities/index/{case_id}` | GET | Activities for a case | Documented |
| `activityTypes/index` | GET | List activity types | Documented |
| `events/index` | GET | List all events | Documented |
| `eventTypes/index` | GET | List event types | Documented |
| `tasks/index` | GET | List all tasks | Documented |

### Documents & Uploads

| Endpoint | Method | Description | Status |
|----------|--------|-------------|--------|
| `uploads/index` | GET | List all uploads (9,419+ files) | **Undocumented** |
| `uploads/index?case_file_id={id}` | GET | Uploads for specific case | **Undocumented** |
| `documents/index` | GET | Document metadata list | **Undocumented** |
| `documents/download/{upload_id}` | GET | Download file (302 → S3) | **Undocumented** |

**Download Flow:**
```python
# documents/download returns 302 redirect to S3 signed URL
resp = await client.get(f"{API_BASE}/documents/download/{upload_id}", follow_redirects=False)
if resp.status_code == 302:
    s3_url = resp.headers["location"]
    file_resp = await client.get(s3_url)
    # file_resp.content contains the file bytes
```

### Parties & Contacts

| Endpoint | Method | Description | Status |
|----------|--------|-------------|--------|
| `parties/index` | GET | List all parties | **Undocumented** |
| `parties/view/{case_id}` | GET | Parties for a case | Documented |
| `partyGroups/index` | GET | List party groups | Documented |
| `contacts/index` | GET | List all contacts | **Undocumented** |
| `contacts/view/{id}` | GET | View contact details | **Undocumented** |
| `companies/index` | GET | List all companies | **Undocumented** |
| `peopleTypes/index` | GET | Party/people type definitions | **Undocumented** |

### Billing & Finance

| Endpoint | Method | Description | Status |
|----------|--------|-------------|--------|
| `billingCodes/index` | GET | List billing codes | Documented |
| `billingRates/index` | GET | Billing rate configuration | **Undocumented** |
| `caseLedgers/index` | GET | All case ledgers | **Undocumented** |
| `caseLedgersOpen/index` | GET | Open ledger entries | Documented |
| `caseLedgersReviewed/index` | GET | Reviewed ledger entries | Documented |
| `invoices/index` | GET | List all invoices | **Undocumented** |
| `receivables/index` | GET | List receivables | Documented |
| `trustAccounts/index` | GET | Trust account management | **Undocumented** |
| `paymentMethods/index` | GET | Payment method options | Documented |

### Case Detail Views (Practice-Specific)

| Endpoint | Method | Description | Status |
|----------|--------|-------------|--------|
| `injuries/view/{case_id}` | GET | Injury details for case | **Undocumented** |
| `arrests/view/{case_id}` | GET | Arrest details | **Undocumented** |
| `generalIncidents/view/{case_id}` | GET | General incident details | **Undocumented** |
| `malpractices/view/{case_id}` | GET | Malpractice details | **Undocumented** |
| `premiseLiabilities/view/{case_id}` | GET | Premise liability details | **Undocumented** |
| `productLiabilities/view/{case_id}` | GET | Product liability details | **Undocumented** |
| `vehicleAccidents/view/{case_id}` | GET | Vehicle accident details | **Undocumented** |

### Reference Data

| Endpoint | Method | Description | Status |
|----------|--------|-------------|--------|
| `statutes/index` | GET | List statutes of limitations | Documented |
| `courts/index` | GET | List courts | **Undocumented** |

### Firm & Users

| Endpoint | Method | Description | Status |
|----------|--------|-------------|--------|
| `users/index` | GET | List firm users | Documented |
| `messages/index` | GET | Internal messages | **Undocumented** |

### System & Configuration

| Endpoint | Method | Description | Status |
|----------|--------|-------------|--------|
| `reports/index` | GET | Report definitions | **Undocumented** |
| `workflows/index` | GET | Workflow configurations | **Undocumented** |
| `oauthApps/index` | GET | OAuth app management | **Undocumented** |
| `help` | GET | API help/documentation | **Undocumented** |

---

## Permission-Restricted Endpoints

These require elevated permissions (admin/owner level):

| Endpoint | Description |
|----------|-------------|
| `firms/index` | List all firms |
| `firms/view` | View firm details |
| `preferences/index` | User preferences |
| `damages/index` | Damages (PI cases) |
| `settlements/index` | Settlements (PI cases) |
| `pages/index` | CMS pages |

---

## Response Format

Most endpoints return JSON in this format:

```json
{
  "data": {
    "123": { "id": "123", "field": "value" },
    "456": { "id": "456", "field": "value" }
  },
  "lastQueryAt": "2026-01-13T09:38:18"
}
```

**Note:** Data is keyed by ID, not returned as an array.

---

## URL Patterns

MerusCase API supports multiple URL patterns (CakePHP conventions):

| Pattern | Example | Status |
|---------|---------|--------|
| camelCase | `caseFiles/index` | Primary |
| snake_case | `case_files` | Works |
| PascalCase | `CaseFiles` | Works |

---

## Query Parameters

Common query parameters across endpoints:

| Parameter | Description | Example |
|-----------|-------------|---------|
| `limit` | Max results to return | `?limit=100` |
| `case_file_id` | Filter by case | `?case_file_id=123` |
| `lastQueryAt` | Incremental sync timestamp | `?lastQueryAt=2026-01-01` |

---

## OAuth Configuration

| Setting | Value |
|---------|-------|
| Authorization URL | `https://api.meruscase.com/oauth/authorize` |
| Token URL | `https://api.meruscase.com/oauth/token` |
| Callback URL | `https://api.meruscase.com/oauth/authcodeCallback` |
| Grant Type | `authorization_code` |
| Token Lifetime | ~30 years (946080000 seconds) |

---

## Exploration Metadata

**Exploration Date:** 2026-01-13
**Endpoints Tested:** 162
**Working:** 34
**Permission Denied:** 6
**Not Found:** 111

Results saved to: `api_exploration_results.json`
