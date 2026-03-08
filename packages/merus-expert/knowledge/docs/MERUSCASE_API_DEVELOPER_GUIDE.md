# MerusCase API - Complete Developer Guide

**For:** Adjudica Development Team (Workers' Compensation)
**Date:** January 13, 2026
**API Base URL:** `https://api.meruscase.com`

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Authentication](#authentication)
3. [Creating Billing Entries](#creating-billing-entries) ⭐ **NEW - Tested & Working**
4. [Document Management](#document-management) ⭐ Key Discovery
5. [Case Management](#case-management)
6. [Contacts & Companies](#contacts--companies)
7. [Billing & Finance (Read)](#billing--finance)
8. [Events & Tasks](#events--tasks)
9. [Reference Data](#reference-data)
10. [Users & Messages](#users--messages)
11. [Error Handling](#error-handling) ⚠️ Important
12. [Rate Limiting](#rate-limiting)
13. [Response Formats](#response-formats)
14. [Incremental Sync](#incremental-sync)
15. [Endpoints That Don't Exist](#endpoints-that-dont-exist)
16. [Python Client](#python-client)
17. [Quick Reference](#quick-reference)

---

## Executive Summary

A comprehensive exploration of the MerusCase API was conducted, testing **162 potential endpoints**. Key findings:

| Metric | Count |
|--------|-------|
| **Working Endpoints** | 34 |
| **Officially Documented** | 17 |
| **Undocumented (Discovered)** | 17 |
| **Permission Denied** | 6 |
| **Not Found** | 111 |

### Critical Discoveries

1. **Billing Entry Creation** - `POST /activities/add` and `POST /caseLedgers/add` both work for creating billable entries
2. **Document Download API** - Undocumented `GET /documents/download/{upload_id}` returns S3 signed URLs
3. **Uploads Index** - `GET /uploads/index` returns all firm documents (9,419+ files in test account)
4. **CakePHP Wrapper Required** - All POST data must be wrapped in model name (e.g., `{"Activity": {...}}`)
5. **Extended Billing Read** - Invoices, billing rates, trust accounts all accessible
6. **Contact Management** - Full contact and company CRUD operations
7. **No WC-Specific Endpoints** - Workers' comp data accessed via standard case endpoints

---

## Authentication

### OAuth 2.0 Configuration

| Parameter | Value |
|-----------|-------|
| Grant Type | `authorization_code` |
| Base URL | `https://api.meruscase.com` |
| Authorization URL | `https://api.meruscase.com/oauth/authorize` |
| Token URL | `https://api.meruscase.com/oauth/token` |
| Callback URL | `https://api.meruscase.com/oauth/authcodeCallback` |
| **Token Lifetime** | **~30 years** (946,080,000 seconds) |

### Authorization Flow

```
1. Redirect user to:
   https://api.meruscase.com/oauth/authorize?
     client_id={CLIENT_ID}&
     redirect_uri=https://api.meruscase.com/oauth/authcodeCallback&
     response_type=code

2. User logs in and authorizes

3. MerusCase redirects to callback with ?code={AUTH_CODE}

4. Exchange code for token:
   POST https://api.meruscase.com/oauth/token
   Content-Type: application/x-www-form-urlencoded

   grant_type=authorization_code&
   code={AUTH_CODE}&
   client_id={CLIENT_ID}&
   client_secret={CLIENT_SECRET}&
   redirect_uri=https://api.meruscase.com/oauth/authcodeCallback
```

### Request Headers

```http
Authorization: Bearer {access_token}
Accept: application/json
Content-Type: application/json
```

### Important Notes

- Tokens expire in ~30 years - refresh logic is not critical
- The authorization page has reCAPTCHA - cannot be fully automated
- Use MerusCase's managed callback URL, not localhost

---

## Creating Billing Entries

### ⭐ Key Discovery: Full Billing API Access Works

Both time-based billing and direct ledger entries can be created via API.

**Important:** MerusCase uses CakePHP conventions - data must be wrapped in a model name object.

---

### Time Entry (Billable Activity)

```
POST /activities/add
```

**Request Format:**
```json
{
  "Activity": {
    "case_file_id": "56171871",
    "subject": "Review medical records",
    "description": "Reviewed QME report and treatment records",
    "date": "2026-01-13 10:00:00",
    "duration": 12,
    "billable": 1,
    "activity_type_id": "3"
  }
}
```

**Fields:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `case_file_id` | string | Yes | Case ID |
| `subject` | string | Yes | Short description |
| `description` | string | No | Detailed notes |
| `date` | string | Yes | `YYYY-MM-DD HH:MM:SS` |
| `duration` | int | Yes | Time in **minutes** |
| `billable` | int | Yes | `1` = billable, `0` = non-billable |
| `activity_type_id` | string | No | Activity type (see `/activityTypes/index`) |
| `billing_code_id` | string | No | Billing code (see `/billingCodes/index`) |
| `user_id` | string | No | User performing work (defaults to token owner) |

**Success Response:**
```json
{"id": "918183874"}
```

**Example - Bill 0.2 hours:**
```python
async def bill_time(client, case_id: str, hours: float, description: str):
    """Create a billable time entry."""
    minutes = int(hours * 60)

    payload = {
        "Activity": {
            "case_file_id": case_id,
            "subject": description[:50],  # Short subject
            "description": description,
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "duration": minutes,
            "billable": 1,
        }
    }

    resp = await client.post("/activities/add", json=payload)
    result = resp.json()

    if "id" in result:
        return result["id"]
    else:
        raise Exception(f"Failed: {result}")

# Usage: bill_time(client, "56171871", 0.2, "Review medical records")
```

---

### Direct Ledger Entry (Fees/Costs)

```
POST /caseLedgers/add
```

**Request Format:**
```json
{
  "CaseLedger": {
    "case_file_id": "56171871",
    "amount": "25.00",
    "description": "WCAB Filing Fee",
    "date": "2026-01-13",
    "ledger_type_id": 1
  }
}
```

**Fields:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `case_file_id` | string | Yes | Case ID |
| `amount` | string | Yes | Dollar amount (e.g., `"25.00"`) |
| `description` | string | Yes | Entry description |
| `date` | string | Yes | `YYYY-MM-DD` |
| `ledger_type_id` | int | Yes | Type of entry (1, 2, or 3) |

**Success Response:**
```json
{
  "success": 1,
  "data": {
    "CaseLedger": {
      "id": 110681047,
      "case_file_id": 56171871,
      "amount": "25.00",
      "ledger_type_id": 1,
      "status_id": 1
    }
  }
}
```

**Example - Add filing fee:**
```python
async def add_cost(client, case_id: str, amount: float, description: str):
    """Add a direct cost/fee to a case."""
    payload = {
        "CaseLedger": {
            "case_file_id": case_id,
            "amount": f"{amount:.2f}",
            "description": description,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "ledger_type_id": 1,
        }
    }

    resp = await client.post("/caseLedgers/add", json=payload)
    result = resp.json()

    if result.get("success") == 1:
        return result["data"]["CaseLedger"]["id"]
    else:
        raise Exception(f"Failed: {result}")

# Usage: add_cost(client, "56171871", 25.00, "WCAB Filing Fee")
```

---

### Glassy Integration Example

Complete flow for "bill .2 on the Smith case":

```python
async def glassy_bill_time(
    client,
    hours: float,
    case_search: str,
    description: str = "Legal services"
):
    """
    Natural language billing: 'bill .2 on Smith case'

    Args:
        hours: Time in hours (0.2 = 12 minutes)
        case_search: Case name or number to search
        description: What the time was for
    """
    # 1. Find the case
    resp = await client.get("/caseFiles/index")
    cases = resp.json()["data"]

    matching_case = None
    for case_id, case_data in cases.items():
        # Check file number or party name
        file_num = case_data.get("file_number", case_data.get("1", ""))
        party = case_data.get("primary_party_name", case_data.get("1", ""))

        if case_search.lower() in str(file_num).lower() or \
           case_search.lower() in str(party).lower():
            matching_case = case_id
            break

    if not matching_case:
        raise ValueError(f"No case found matching '{case_search}'")

    # 2. Create billable activity
    minutes = int(hours * 60)

    payload = {
        "Activity": {
            "case_file_id": matching_case,
            "subject": description[:50],
            "description": description,
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "duration": minutes,
            "billable": 1,
        }
    }

    resp = await client.post("/activities/add", json=payload)
    result = resp.json()

    if "id" in result:
        return {
            "success": True,
            "activity_id": result["id"],
            "case_id": matching_case,
            "hours": hours,
            "minutes": minutes,
        }
    else:
        raise Exception(f"API error: {result}")

# Usage
result = await glassy_bill_time(client, 0.2, "Smith", "Review medical records")
print(f"Billed {result['hours']} hours to case {result['case_id']}")
```

---

### CakePHP Wrapper Requirement

**Critical:** All POST requests must wrap data in the model name:

```python
# WRONG - will fail
{"case_file_id": "123", "subject": "Test"}

# CORRECT - will work
{"Activity": {"case_file_id": "123", "subject": "Test"}}
```

This applies to all create/update endpoints:
- `Activity` for `/activities/add`
- `CaseLedger` for `/caseLedgers/add`
- `Party` for `/parties/add`
- `Upload` for `/uploads/add`

---

## Document Management

### ⭐ Key Discovery: Document Downloads Work via API

This is **not in their official documentation** but fully functional.

### List All Uploads

```
GET /uploads/index
```

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `limit` | int | No | Max results (default: 100) |
| `case_file_id` | int | No | Filter by case |
| `lastQueryAt` | string | No | ISO timestamp for incremental sync |

**Response:**
```json
{
  "data": {
    "879517531": {
      "id": "879517531",
      "filename": "Medical_Records_QME_Report.pdf",
      "case_file_id": "123456",
      "folder_id": "789",
      "file_size": "1048576",
      "mime_type": "application/pdf",
      "created": "2024-06-15 10:30:00",
      "modified": "2024-06-15 10:30:00",
      "user_id": "42",
      "description": "QME Report - Dr. Smith"
    }
  },
  "lastQueryAt": "2026-01-13T09:38:18"
}
```

**Note:** Data is keyed by upload ID (object), not an array.

---

### Download Document

```
GET /documents/download/{upload_id}
```

**Behavior:**
1. Returns HTTP **302 redirect**
2. `Location` header contains S3 signed URL
3. Follow redirect to download actual file

**⚠️ Critical:** S3 signed URLs expire in **minutes**. Never cache download URLs - always fetch fresh.

**Implementation:**
```python
import httpx

async def download_document(upload_id: int, token: str) -> bytes:
    """Download a document from MerusCase."""
    async with httpx.AsyncClient() as client:
        # Step 1: Get S3 signed URL (don't follow redirect)
        resp = await client.get(
            f"https://api.meruscase.com/documents/download/{upload_id}",
            headers={"Authorization": f"Bearer {token}"},
            follow_redirects=False
        )

        if resp.status_code != 302:
            raise Exception(f"Expected 302, got {resp.status_code}")

        s3_url = resp.headers["location"]

        # Step 2: Download from S3 (no auth needed, URL is signed)
        file_resp = await client.get(s3_url, timeout=60.0)
        return file_resp.content
```

**TypeScript/JavaScript:**
```typescript
async function downloadDocument(uploadId: number, token: string): Promise<ArrayBuffer> {
  // Step 1: Get S3 URL (don't follow redirect)
  const resp = await fetch(
    `https://api.meruscase.com/documents/download/${uploadId}`,
    {
      headers: { Authorization: `Bearer ${token}` },
      redirect: 'manual'
    }
  );

  const s3Url = resp.headers.get('location');
  if (!s3Url) throw new Error('No redirect URL');

  // Step 2: Download from S3
  const fileResp = await fetch(s3Url);
  return fileResp.arrayBuffer();
}
```

---

### Documents Index

```
GET /documents/index
```

Returns document metadata. May return empty array depending on account configuration.

---

## Case Management

### List Cases

```
GET /caseFiles/index
```

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `limit` | int | Max results (default: 100) |
| `case_status` | string | Filter by status |
| `case_type` | string | Filter by type |
| `open_date[gte]` | string | Open date >= (YYYY-MM-DD) |
| `open_date[lte]` | string | Open date <= (YYYY-MM-DD) |
| `file_number` | string | Search by file number |
| `lastQueryAt` | string | Incremental sync timestamp |

**Response:**
```json
{
  "data": {
    "123456": {
      "id": "123456",
      "file_number": "WC-2024-001",
      "case_type_id": "2",
      "case_status_id": "1",
      "open_date": "2024-01-15",
      "primary_party_name": "John Doe",
      "attorney_responsible_id": "42",
      "office_id": "1",
      "date_of_injury": "2023-12-01",
      "employer_name": "ABC Corporation",
      "insurance_company": "State Fund"
    }
  }
}
```

---

### View Case Details

```
GET /caseFiles/view/{case_file_id}
```

Returns complete case information including all related data for WC cases.

**Response includes:**
- Case details
- Parties
- Custom fields (WC-specific data)
- Related entities

---

### Case Types

```
GET /caseTypes/index
```

**Response:**
```json
{
  "data": {
    "1": {"id": "1", "name": "Personal Injury"},
    "2": {"id": "2", "name": "Workers Compensation"},
    "3": {"id": "3", "name": "Medical Malpractice"}
  }
}
```

---

### Case Statuses (Undocumented)

```
GET /caseStatuses/index
```

**Response:**
```json
{
  "data": {
    "1": {"id": "1", "name": "Active"},
    "2": {"id": "2", "name": "Closed"},
    "3": {"id": "3", "name": "Pending"},
    "4": {"id": "4", "name": "Settled"}
  }
}
```

---

## Contacts & Companies

### List All Contacts (Undocumented)

```
GET /contacts/index
```

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `limit` | int | Max results |

**Response:**
```json
{
  "data": {
    "1001": {
      "id": "1001",
      "first_name": "Jane",
      "last_name": "Smith",
      "company_name": "WCAB - Los Angeles",
      "email": "jane@example.com",
      "phone": "555-0100",
      "address": "123 Main St",
      "city": "Los Angeles",
      "state": "CA",
      "zip": "90001"
    }
  }
}
```

---

### View Contact (Undocumented)

```
GET /contacts/view/{contact_id}
```

---

### List Companies (Undocumented)

```
GET /companies/index
```

**Response:**
```json
{
  "data": {
    "500": {
      "id": "500",
      "name": "State Compensation Insurance Fund",
      "address": "1275 Market Street",
      "city": "San Francisco",
      "state": "CA",
      "phone": "888-782-8338",
      "type": "Insurance Carrier"
    }
  }
}
```

---

### List Parties

```
GET /parties/index
```

**Note:** Returns different response format:
```json
{
  "success": true,
  "msg": "..."
}
```

---

### Parties for Case

```
GET /parties/view/{case_file_id}
```

---

### Party Groups

```
GET /partyGroups/index
```

**Response:**
```json
{
  "data": {
    "1": {"id": "1", "name": "Applicant"},
    "2": {"id": "2", "name": "Defendant"},
    "3": {"id": "3", "name": "Lien Claimant"}
  }
}
```

---

### People Types (Undocumented)

```
GET /peopleTypes/index
```

**Response:**
```json
{
  "data": {
    "1": {"id": "1", "name": "Injured Worker"},
    "2": {"id": "2", "name": "Employer"},
    "3": {"id": "3", "name": "Insurance Adjuster"},
    "4": {"id": "4", "name": "QME Physician"},
    "5": {"id": "5", "name": "AME Physician"}
  }
}
```

---

## Billing & Finance

### Billing Codes

```
GET /billingCodes/index
```

**Response:**
```json
{
  "data": {
    "10": {
      "id": "10",
      "code": "CONSULT",
      "description": "Initial Consultation",
      "rate": "0.00"
    },
    "11": {
      "id": "11",
      "code": "HEARING",
      "description": "WCAB Hearing Appearance",
      "rate": "350.00"
    }
  }
}
```

---

### Billing Rates (Undocumented)

```
GET /billingRates/index
```

---

### All Ledger Entries (Undocumented)

```
GET /caseLedgers/index
```

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `case_file_id` | int | Filter by case |
| `limit` | int | Max results |

Returns all ledger entries (both open and reviewed).

---

### Open Ledgers

```
GET /caseLedgersOpen/index
```

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `case_file_id` | int | Filter by case |
| `date[gte]` | string | Date >= (YYYY-MM-DD) |
| `date[lte]` | string | Date <= (YYYY-MM-DD) |

---

### Reviewed Ledgers

```
GET /caseLedgersReviewed/index
```

Same parameters as open ledgers.

---

### Invoices (Undocumented)

```
GET /invoices/index
```

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `case_file_id` | int | Filter by case |
| `limit` | int | Max results |

**Response:**
```json
{
  "data": {
    "INV-001": {
      "id": "INV-001",
      "case_file_id": "123456",
      "amount": "2500.00",
      "status": "sent",
      "date": "2024-06-15",
      "due_date": "2024-07-15"
    }
  }
}
```

---

### Receivables

```
GET /receivables/index
```

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `case_file_id` | int | Filter by case |
| `limit` | int | Max results |

---

### Trust Accounts (Undocumented)

```
GET /trustAccounts/index
```

---

### Payment Methods

```
GET /paymentMethods/index
```

---

## Events & Tasks

### List Events

```
GET /events/index
```

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `case_file_id` | int | Filter by case |
| `limit` | int | Max results |

**Response:**
```json
{
  "now": "2026-01-13T09:38:18",
  "data": {
    "E001": {
      "id": "E001",
      "case_file_id": "123456",
      "event_type_id": "2",
      "title": "MSC - WCAB Oakland",
      "start_date": "2024-07-01 09:00:00",
      "end_date": "2024-07-01 10:00:00",
      "location": "1515 Clay Street, Oakland",
      "description": "Mandatory Settlement Conference"
    }
  },
  "lastQueryAt": "2026-01-13T09:38:18"
}
```

---

### Event Types

```
GET /eventTypes/index
```

**Response:**
```json
{
  "data": {
    "1": {"id": "1", "name": "MSC"},
    "2": {"id": "2", "name": "Trial"},
    "3": {"id": "3", "name": "Deposition"},
    "4": {"id": "4", "name": "QME Appointment"},
    "5": {"id": "5", "name": "AME Appointment"}
  }
}
```

---

### List Tasks

```
GET /tasks/index
```

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `case_file_id` | int | Filter by case |
| `due_date[gte]` | string | Due date >= |
| `due_date[lte]` | string | Due date <= |

**Response:**
```json
{
  "data": {
    "T001": {
      "id": "T001",
      "case_file_id": "123456",
      "title": "Request QME Panel",
      "description": "Submit DWC Form QME-105",
      "due_date": "2024-07-15",
      "assigned_to": "42",
      "status": "pending",
      "priority": "high"
    }
  },
  "lastQueryAt": "2026-01-13T09:38:18"
}
```

---

### Activities for Case

```
GET /activities/index/{case_file_id}
```

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `limit` | int | Max results |

**Response:**
```json
{
  "data": {
    "555": {
      "id": "555",
      "case_file_id": "123456",
      "subject": "Call with adjuster",
      "description": "Discussed settlement offer...",
      "activity_type_id": "3",
      "date": "2024-06-15 14:30:00",
      "duration": "30",
      "billable": "1",
      "user_id": "42"
    }
  }
}
```

---

### Activity Types

```
GET /activityTypes/index
```

---

## Reference Data

### Courts (Undocumented)

```
GET /courts/index
```

Includes WCAB district offices.

**Response:**
```json
{
  "data": {
    "C001": {
      "id": "C001",
      "name": "WCAB - Los Angeles",
      "address": "320 W 4th Street",
      "city": "Los Angeles",
      "state": "CA",
      "zip": "90013"
    },
    "C002": {
      "id": "C002",
      "name": "WCAB - San Francisco",
      "address": "455 Golden Gate Ave",
      "city": "San Francisco",
      "state": "CA"
    }
  }
}
```

---

### Statutes of Limitations

```
GET /statutes/index
```

---

## Users & Messages

### List Users

```
GET /users/index
```

**Response:**
```json
{
  "data": {
    "42": {
      "id": "42",
      "first_name": "John",
      "last_name": "Attorney",
      "email": "john@lawfirm.com",
      "role": "attorney",
      "active": "1"
    }
  }
}
```

---

### Messages (Undocumented)

```
GET /messages/index
```

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `limit` | int | Max results |

---

### Workflows (Undocumented)

```
GET /workflows/index
```

---

### Reports (Undocumented)

```
GET /reports/index
```

---

## Error Handling

### ⚠️ Critical: Errors Can Hide in 200 Responses

MerusCase returns application-level errors inside HTTP 200 responses. **Always check for the `errors` key:**

```python
response = requests.get(endpoint, headers=auth)
data = response.json()

# DON'T just check status code!
if response.status_code == 200:
    # Still need to check for errors
    if "errors" in data and data["errors"]:
        error = data["errors"][0]
        error_type = error.get("errorType", "unknown")
        error_msg = error.get("errorMessage", "Unknown error")
        raise MerusCaseError(f"{error_type}: {error_msg}")
    else:
        # Actually successful
        return data["data"]
```

### Error Response Format

```json
{
  "errors": [
    {
      "errorType": "not_allowed",
      "errorMessage": "You do not have privilege to access this resource"
    }
  ]
}
```

### Common Error Types

| errorType | Meaning |
|-----------|---------|
| `not_allowed` | Permission denied |
| `invalid_request` | Bad parameters |
| `not_found` | Resource doesn't exist |
| `validation_error` | Data validation failed |

### HTTP Status Codes

| Code | Meaning | Action |
|------|---------|--------|
| 200 | Success (maybe) | Check for `errors` key |
| 302 | Redirect | Follow `Location` header (document downloads) |
| 401 | Unauthorized | Token expired or invalid |
| 403 | Forbidden | Insufficient permissions |
| 404 | Not Found | Endpoint doesn't exist |
| 429 | Rate Limited | Wait and retry with backoff |
| 500 | Server Error | Retry with exponential backoff |

---

## Rate Limiting

### Headers to Monitor

```http
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1705142400
```

### Recommended Implementation

```python
import time
from functools import wraps

def rate_limit_handler(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        max_retries = 3
        base_delay = 1

        for attempt in range(max_retries):
            response = await func(*args, **kwargs)

            if response.status_code == 429:
                reset_time = int(response.headers.get('X-RateLimit-Reset', 0))
                wait_time = max(reset_time - time.time(), base_delay * (2 ** attempt))
                await asyncio.sleep(wait_time)
                continue

            return response

        raise RateLimitExceeded("Max retries exceeded")

    return wrapper
```

---

## Response Formats

### Standard Data Wrapper

Most endpoints return:
```json
{
  "data": {
    "{id}": { "id": "{id}", "field": "value" },
    "{id2}": { "id": "{id2}", "field": "value" }
  }
}
```

**Important:** Data is keyed by ID (object), NOT an array. To iterate:

```python
# Python
for id, item in data["data"].items():
    print(item["name"])

# Or get as list
items = list(data["data"].values())
```

```typescript
// TypeScript
const items = Object.values(data.data);
items.forEach(item => console.log(item.name));
```

### With Sync Timestamp

```json
{
  "data": { ... },
  "lastQueryAt": "2026-01-13T09:38:18"
}
```

### With Server Time (Events)

```json
{
  "now": "2026-01-13T09:38:18",
  "data": { ... },
  "lastQueryAt": "2026-01-13T09:38:18"
}
```

### Alternative Pattern (Parties)

```json
{
  "success": true,
  "msg": "Operation completed"
}
```

---

## Incremental Sync

Most list endpoints support delta updates via `lastQueryAt`:

```
GET /uploads/index?lastQueryAt=2026-01-12T00:00:00
```

**Flow:**
1. First request: No `lastQueryAt` parameter
2. Store returned `lastQueryAt` value
3. Subsequent requests: Pass stored timestamp
4. Only modified records returned

**Implementation:**
```python
class MerusCaseSync:
    def __init__(self):
        self.last_sync = {}

    async def sync_uploads(self, client):
        params = {}
        if "uploads" in self.last_sync:
            params["lastQueryAt"] = self.last_sync["uploads"]

        data = await client.get("/uploads/index", params=params)

        # Store new sync timestamp
        self.last_sync["uploads"] = data.get("lastQueryAt")

        return data["data"]
```

---

## Endpoints That Don't Exist

These were tested and return 404. **Don't waste time trying these:**

### WC-Specific (None Exist)
```
/wcClaims/index          ❌
/wcBenefits/index        ❌
/wcInjuries/index        ❌
/bodyParts/index         ❌
/injuryTypes/index       ❌
/treatmentTypes/index    ❌
/qme/index               ❌
/ame/index               ❌
/pqme/index              ❌
/medicalRecords/index    ❌
/medicalReports/index    ❌
```

WC-specific data is accessed through standard `caseFiles/view/{id}` endpoint.

### Documents
```
/folders/index           ❌
/documentFolders/index   ❌
/documentTypes/index     ❌
/fileTypes/index         ❌
/attachments/index       ❌
```

### Contacts
```
/partyTypes/index        ❌
/vendors/index           ❌
/clients/index           ❌
/attorneys/index         ❌
/experts/index           ❌
/witnesses/index         ❌
/insuranceCompanies/index ❌
/employers/index         ❌
/doctors/index           ❌
/medicalProviders/index  ❌
```

### Calendar
```
/appointments/index      ❌
/deadlines/index         ❌
/reminders/index         ❌
/courtDates/index        ❌
/depositions/index       ❌
/hearings/index          ❌
/mediations/index        ❌
/limitationDates/index   ❌
```

### Billing
```
/payments/index          ❌
/expenses/index          ❌
/timeEntries/index       ❌
/retainers/index         ❌
/fees/index              ❌
/costs/index             ❌
/disbursements/index     ❌
```

### Communications
```
/emails/index            ❌
/notes/index             ❌
/phoneCalls/index        ❌
/letters/index           ❌
/faxes/index             ❌
/communications/index    ❌
```

### Admin
```
/offices/index           ❌
/branches/index          ❌
/departments/index       ❌
/teams/index             ❌
/roles/index             ❌
/permissions/index       ❌
/settings/index          ❌
```

### System
```
/api/version             ❌
/version                 ❌
/status                  ❌
/health                  ❌
/schema                  ❌
/endpoints               ❌
/docs                    ❌
```

### Permission Denied (Exist but Restricted)
```
/firms/index             🔒 Admin only
/firms/view              🔒 Admin only
/preferences/index       🔒 Admin only
/damages/index           🔒 Special access
/settlements/index       🔒 Special access
/pages/index             🔒 Admin only
```

---

## Python Client

A ready-to-use async Python client is available at `meruscase_api/client.py`.

### Installation

```bash
pip install httpx pydantic
```

### Basic Usage

```python
from meruscase_api.client import MerusCaseAPIClient

async def main():
    async with MerusCaseAPIClient(access_token="your_token") as client:
        # List cases
        cases = await client.list_cases(limit=50)

        # Get case details
        case = await client.get_case(case_file_id=123456)

        # List uploads for a case
        uploads = await client.list_uploads(case_file_id=123456)

        # Download a document
        file_bytes = await client.download_document_bytes(upload_id=879517531)

        # List contacts
        contacts = await client.list_contacts()

        # Get invoices
        invoices = await client.list_invoices(case_file_id=123456)
```

### Available Methods

**Billing (Create):**
- `add_activity(activity)` → Create billable time entry
- `add_ledger_entry(case_file_id, amount, description, ledger_type_id)` → Direct fee/cost

**Case Management:**
- `list_cases(case_status?, case_type?, open_date_gte?, open_date_lte?, limit?)`
- `get_case(case_file_id)`
- `search_cases(file_number)`
- `get_case_types()`
- `get_case_statuses()`

**Documents:**
- `list_uploads(case_file_id?, limit?)`
- `download_document(upload_id)` → Returns S3 URL
- `download_document_bytes(upload_id)` → Returns file bytes
- `upload_document(document)` → Upload file to case

**Contacts:**
- `list_contacts(limit?)`
- `get_contact(contact_id)`
- `list_companies(limit?)`
- `get_parties(case_file_id)`
- `get_party_groups()`
- `get_people_types()`

**Billing:**
- `get_billing_codes()`
- `get_billing_rates()`
- `list_all_ledgers(case_file_id?, limit?)`
- `get_open_ledgers(case_file_id?, date_gte?, date_lte?)`
- `list_invoices(case_file_id?, limit?)`
- `list_receivables(case_file_id?, limit?)`
- `list_trust_accounts()`
- `get_payment_methods()`

**Events & Tasks:**
- `list_events(case_file_id?, limit?)`
- `get_event_types()`
- `get_tasks(case_file_id?, due_date_gte?, due_date_lte?)`
- `get_activities(case_file_id, limit?)`
- `get_activity_types()`

**Reference:**
- `get_courts()`
- `get_statutes()`

**Users:**
- `list_users()`
- `list_messages(limit?)`

---

## Quick Reference

### URL Patterns

MerusCase accepts multiple naming conventions:
```
caseFiles/index    ✓ camelCase (primary)
case_files         ✓ snake_case
CaseFiles          ✓ PascalCase
case-files         ❌ kebab-case
```

### Complete Endpoint List

#### POST Endpoints (Create)

| Endpoint | Status | Description |
|----------|--------|-------------|
| `POST /activities/add` | **Tested & Working** | Create billable time entry |
| `POST /caseLedgers/add` | **Tested & Working** | Create direct fee/cost entry |
| `POST /parties/add` | Documented | Add party to case |
| `POST /uploads/add` | Documented | Upload document |

#### GET Endpoints (Read)

| Endpoint | Status | Description |
|----------|--------|-------------|
| `GET /caseFiles/index` | Documented | List cases |
| `GET /caseFiles/view/{id}` | Documented | Case details |
| `GET /caseTypes/index` | Documented | Case types |
| `GET /caseStatuses/index` | **Undocumented** | Case statuses |
| `GET /uploads/index` | **Undocumented** | List documents |
| `GET /documents/download/{id}` | **Undocumented** | Download file |
| `GET /documents/index` | **Undocumented** | Document metadata |
| `GET /contacts/index` | **Undocumented** | List contacts |
| `GET /contacts/view/{id}` | **Undocumented** | Contact details |
| `GET /companies/index` | **Undocumented** | List companies |
| `GET /parties/index` | **Undocumented** | List parties |
| `GET /parties/view/{id}` | Documented | Parties for case |
| `GET /partyGroups/index` | Documented | Party groups |
| `GET /peopleTypes/index` | **Undocumented** | People types |
| `GET /billingCodes/index` | Documented | Billing codes |
| `GET /billingRates/index` | **Undocumented** | Billing rates |
| `GET /caseLedgers/index` | **Undocumented** | All ledgers |
| `GET /caseLedgersOpen/index` | Documented | Open ledgers |
| `GET /caseLedgersReviewed/index` | Documented | Reviewed ledgers |
| `GET /invoices/index` | **Undocumented** | Invoices |
| `GET /receivables/index` | Documented | Receivables |
| `GET /trustAccounts/index` | **Undocumented** | Trust accounts |
| `GET /paymentMethods/index` | Documented | Payment methods |
| `GET /events/index` | Documented | Events |
| `GET /eventTypes/index` | Documented | Event types |
| `GET /tasks/index` | Documented | Tasks |
| `GET /activities/index/{id}` | Documented | Activities |
| `GET /activityTypes/index` | Documented | Activity types |
| `GET /courts/index` | **Undocumented** | Courts/WCAB |
| `GET /statutes/index` | Documented | Statutes |
| `GET /users/index` | Documented | Users |
| `GET /messages/index` | **Undocumented** | Messages |
| `GET /workflows/index` | **Undocumented** | Workflows |
| `GET /reports/index` | **Undocumented** | Reports |

### Document Download Cheat Sheet

```python
# 1. Get upload ID
uploads = await client.list_uploads(case_file_id=123456)
upload_id = list(uploads.data["data"].keys())[0]

# 2. Download
file_bytes = await client.download_document_bytes(upload_id)

# 3. Save
with open(f"document_{upload_id}.pdf", "wb") as f:
    f.write(file_bytes)
```

### Billing Entry Cheat Sheet

```python
# Bill 0.2 hours (12 minutes) to a case
payload = {
    "Activity": {
        "case_file_id": "56171871",
        "subject": "Review medical records",
        "date": "2026-01-13 10:00:00",
        "duration": 12,  # minutes, not hours!
        "billable": 1,
    }
}
resp = await client.post("/activities/add", json=payload)
activity_id = resp.json()["id"]  # Returns: "918183874"

# Add $25 filing fee
payload = {
    "CaseLedger": {
        "case_file_id": "56171871",
        "amount": "25.00",
        "description": "WCAB Filing Fee",
        "date": "2026-01-13",
        "ledger_type_id": 1,
    }
}
resp = await client.post("/caseLedgers/add", json=payload)
ledger_id = resp.json()["data"]["CaseLedger"]["id"]  # Returns: 110681047
```

---

## Exploration Metadata

| Metric | Value |
|--------|-------|
| Exploration Date | January 13, 2026 |
| Total Endpoints Tested | 162 |
| Working | 34 (21%) |
| Not Found | 111 (69%) |
| Permission Denied | 6 (4%) |
| Other Errors | 9 (6%) |

Raw results: `api_exploration_results.json`

---

*Generated from systematic API exploration - January 2026*
