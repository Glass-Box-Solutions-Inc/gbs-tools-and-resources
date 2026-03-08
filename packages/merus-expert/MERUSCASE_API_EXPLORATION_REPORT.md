# MerusCase API Exploration Report

**Date:** January 13, 2026
**Author:** Claude Code (Automated Exploration)
**API Version:** Unknown (undocumented)
**Base URL:** `https://api.meruscase.com`

---

## Executive Summary

A comprehensive exploration of the MerusCase REST API was conducted to discover undocumented endpoints beyond the official documentation. The exploration tested **162 potential endpoints** based on:

- Official MerusCase API documentation
- CakePHP framework conventions (MerusCase's backend)
- Common legal practice management patterns
- REST API naming conventions

### Key Findings

| Metric | Count |
|--------|-------|
| **Total Endpoints Tested** | 162 |
| **Working Endpoints** | 34 |
| **Officially Documented** | 17 |
| **Undocumented (Discovered)** | 17 |
| **Permission Denied** | 6 |
| **Not Found** | 111 |
| **Other Errors** | 9 |

### Critical Discoveries

1. **Document Download API** - `GET /documents/download/{upload_id}` returns S3 signed URLs for file retrieval
2. **Uploads Index** - `GET /uploads/index` returns all firm documents (9,419+ files found)
3. **Extended Billing APIs** - Invoices, billing rates, trust accounts
4. **Contact Management** - Full contact and company CRUD operations
5. **Practice-Specific Views** - Injury details, vehicle accidents, malpractice data

---

## Authentication

### OAuth 2.0 Configuration

| Parameter | Value |
|-----------|-------|
| Grant Type | `authorization_code` |
| Authorization URL | `https://api.meruscase.com/oauth/authorize` |
| Token URL | `https://api.meruscase.com/oauth/token` |
| Callback URL | `https://api.meruscase.com/oauth/authcodeCallback` |
| Token Lifetime | ~30 years (946,080,000 seconds) |

### Request Headers

```http
Authorization: Bearer {access_token}
Accept: application/json
Content-Type: application/json
```

### Token Storage

```
.meruscase_token     # Plain access token
.env                 # Full OAuth configuration
```

---

## Working Endpoints (34 Total)

### 1. Case Management

#### `GET /caseFiles/index`
**Status:** Documented
**Description:** List all case files with optional filtering

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `limit` | int | Max results (default: 100) |
| `case_status` | string | Filter by status |
| `case_type` | string | Filter by type |
| `open_date[gte]` | string | Open date >= (YYYY-MM-DD) |
| `open_date[lte]` | string | Open date <= (YYYY-MM-DD) |
| `file_number` | string | Search by file number |

**Response:**
```json
{
  "data": {
    "123456": {
      "id": "123456",
      "file_number": "2024-001",
      "case_type_id": "5",
      "case_status_id": "1",
      "open_date": "2024-01-15",
      "primary_party_name": "John Doe",
      "attorney_responsible_id": "42"
    }
  }
}
```

---

#### `GET /caseFiles/view/{case_file_id}`
**Status:** Documented
**Description:** Get detailed case file information

**Response:** Full case object with all related data

**Note:** Returns error for invalid/deleted case IDs

---

#### `GET /caseTypes/index`
**Status:** Documented
**Description:** List all available case types

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

#### `GET /caseStatuses/index`
**Status:** **UNDOCUMENTED**
**Description:** List all case status options

**Response:**
```json
{
  "data": {
    "1": {"id": "1", "name": "Active"},
    "2": {"id": "2", "name": "Closed"},
    "3": {"id": "3", "name": "Pending"}
  }
}
```

---

### 2. Documents & Uploads

#### `GET /uploads/index`
**Status:** **UNDOCUMENTED**
**Description:** List all document uploads across the firm

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `limit` | int | Max results |
| `case_file_id` | int | Filter by case |
| `lastQueryAt` | string | Incremental sync timestamp |

**Response:**
```json
{
  "data": {
    "879517531": {
      "id": "879517531",
      "filename": "Medical_Records_2024.pdf",
      "case_file_id": "123456",
      "folder_id": "789",
      "file_size": "1048576",
      "mime_type": "application/pdf",
      "created": "2024-06-15 10:30:00",
      "modified": "2024-06-15 10:30:00",
      "user_id": "42"
    }
  },
  "lastQueryAt": "2026-01-13T09:38:18"
}
```

**Total Documents Found:** 9,419+

---

#### `GET /documents/download/{upload_id}`
**Status:** **UNDOCUMENTED** (Critical Discovery)
**Description:** Download a document file

**Behavior:**
1. Returns HTTP 302 redirect
2. `Location` header contains S3 signed URL
3. S3 URL expires after short period

**Response Headers:**
```http
HTTP/1.1 302 Found
Location: https://meruscase-prod.s3.amazonaws.com/uploads/...?AWSAccessKeyId=...&Expires=...&Signature=...
```

**Implementation:**
```python
import httpx

async def download_document(upload_id: int, token: str) -> bytes:
    async with httpx.AsyncClient() as client:
        # Get S3 signed URL
        resp = await client.get(
            f"https://api.meruscase.com/documents/download/{upload_id}",
            headers={"Authorization": f"Bearer {token}"},
            follow_redirects=False
        )

        if resp.status_code == 302:
            s3_url = resp.headers["location"]
            # Download from S3
            file_resp = await client.get(s3_url)
            return file_resp.content
```

---

#### `GET /documents/index`
**Status:** **UNDOCUMENTED**
**Description:** Document metadata list (appears to return empty for current account)

**Response:** `[]` or metadata list

---

### 3. Activities & Notes

#### `GET /activities/index/{case_file_id}`
**Status:** Documented
**Description:** Get activities/notes for a specific case

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
      "subject": "Client phone call",
      "description": "Discussed case status...",
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

#### `GET /activityTypes/index`
**Status:** Documented
**Description:** List activity type options

**Response:**
```json
{
  "data": {
    "1": {"id": "1", "name": "Phone Call"},
    "2": {"id": "2", "name": "Email"},
    "3": {"id": "3", "name": "Meeting"},
    "4": {"id": "4", "name": "Research"}
  }
}
```

---

### 4. Parties & Contacts

#### `GET /parties/index`
**Status:** **UNDOCUMENTED**
**Description:** List all parties across all cases

**Response:**
```json
{
  "success": true,
  "msg": "..."
}
```

**Note:** Returns success flag pattern, different from standard data wrapper

---

#### `GET /parties/view/{case_file_id}`
**Status:** Documented
**Description:** Get parties for a specific case

**Note:** Returns error "This Party has been deleted" for ID 1 (test ID)

---

#### `GET /partyGroups/index`
**Status:** Documented
**Description:** List party group definitions

**Response:**
```json
{
  "data": {
    "1": {"id": "1", "name": "Plaintiff"},
    "2": {"id": "2", "name": "Defendant"},
    "3": {"id": "3", "name": "Witness"}
  }
}
```

---

#### `GET /contacts/index`
**Status:** **UNDOCUMENTED**
**Description:** List all contacts

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
      "company_name": "Smith Law Firm",
      "email": "jane@smithlaw.com",
      "phone": "555-0100"
    }
  }
}
```

---

#### `GET /contacts/view/{contact_id}`
**Status:** **UNDOCUMENTED**
**Description:** Get contact details

**Note:** Returns error for deleted contacts

---

#### `GET /companies/index`
**Status:** **UNDOCUMENTED**
**Description:** List all companies

**Response:**
```json
{
  "data": {
    "500": {
      "id": "500",
      "name": "ABC Insurance Co",
      "address": "123 Main St",
      "city": "Los Angeles",
      "state": "CA",
      "phone": "555-0200"
    }
  }
}
```

---

#### `GET /peopleTypes/index`
**Status:** **UNDOCUMENTED**
**Description:** List people/party type definitions

**Response:**
```json
{
  "data": {
    "1": {"id": "1", "name": "Client"},
    "2": {"id": "2", "name": "Opposing Party"},
    "3": {"id": "3", "name": "Expert Witness"}
  }
}
```

---

### 5. Billing & Finance

#### `GET /billingCodes/index`
**Status:** Documented
**Description:** List billing code definitions

**Response:**
```json
{
  "data": {
    "10": {"id": "10", "code": "RESEARCH", "description": "Legal Research", "rate": "250.00"},
    "11": {"id": "11", "code": "COURT", "description": "Court Appearance", "rate": "350.00"}
  }
}
```

---

#### `GET /billingRates/index`
**Status:** **UNDOCUMENTED**
**Description:** Billing rate configuration

**Response:**
```json
{
  "data": {
    "1": {"id": "1", "name": "Partner Rate", "rate": "450.00"},
    "2": {"id": "2", "name": "Associate Rate", "rate": "275.00"}
  }
}
```

---

#### `GET /caseLedgers/index`
**Status:** **UNDOCUMENTED**
**Description:** All ledger entries (open + reviewed)

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `case_file_id` | int | Filter by case |
| `limit` | int | Max results |

**Response:**
```json
{
  "data": {
    "L001": {
      "id": "L001",
      "case_file_id": "123456",
      "amount": "500.00",
      "type": "fee",
      "status": "reviewed",
      "date": "2024-06-01"
    }
  }
}
```

---

#### `GET /caseLedgersOpen/index`
**Status:** Documented
**Description:** Open (unbilled) ledger entries

---

#### `GET /caseLedgersReviewed/index`
**Status:** Documented
**Description:** Reviewed (billed) ledger entries

---

#### `GET /invoices/index`
**Status:** **UNDOCUMENTED**
**Description:** List all invoices

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

#### `GET /receivables/index`
**Status:** Documented
**Description:** List receivables (outstanding payments)

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `case_file_id` | int | Filter by case |
| `limit` | int | Max results |

---

#### `GET /trustAccounts/index`
**Status:** **UNDOCUMENTED**
**Description:** Trust account management

**Response:** Trust account list (empty if none configured)

---

#### `GET /paymentMethods/index`
**Status:** Documented
**Description:** Available payment methods

---

### 6. Events & Calendar

#### `GET /events/index`
**Status:** Documented
**Description:** List all events

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
      "title": "Deposition",
      "start_date": "2024-07-01 09:00:00",
      "end_date": "2024-07-01 12:00:00",
      "location": "Smith Law Office"
    }
  },
  "lastQueryAt": "2026-01-13T09:38:18"
}
```

---

#### `GET /eventTypes/index`
**Status:** Documented
**Description:** Event type definitions

**Response:**
```json
{
  "data": {
    "1": {"id": "1", "name": "Hearing"},
    "2": {"id": "2", "name": "Deposition"},
    "3": {"id": "3", "name": "Trial"},
    "4": {"id": "4", "name": "Mediation"}
  }
}
```

---

### 7. Tasks

#### `GET /tasks/index`
**Status:** Documented
**Description:** List tasks

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
      "title": "File motion",
      "description": "File motion for summary judgment",
      "due_date": "2024-07-15",
      "assigned_to": "42",
      "status": "pending"
    }
  },
  "lastQueryAt": "2026-01-13T09:38:18"
}
```

---

### 8. Users & Firm

#### `GET /users/index`
**Status:** Documented
**Description:** List firm users

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

#### `GET /messages/index`
**Status:** **UNDOCUMENTED**
**Description:** Internal messaging system

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `limit` | int | Max results |

**Response:**
```json
{
  "data": {
    "M001": {
      "id": "M001",
      "from_user_id": "42",
      "to_user_id": "43",
      "subject": "Case Update",
      "body": "Please review...",
      "read": "0",
      "created": "2024-06-15 10:00:00"
    }
  }
}
```

---

### 9. Reference Data

#### `GET /statutes/index`
**Status:** Documented
**Description:** Statutes of limitations

---

#### `GET /courts/index`
**Status:** **UNDOCUMENTED**
**Description:** Court listings

**Response:**
```json
{
  "data": {
    "C001": {
      "id": "C001",
      "name": "Los Angeles Superior Court",
      "address": "111 N Hill St",
      "city": "Los Angeles",
      "state": "CA"
    }
  }
}
```

---

### 10. System & Configuration

#### `GET /reports/index`
**Status:** **UNDOCUMENTED**
**Description:** Report definitions

---

#### `GET /workflows/index`
**Status:** **UNDOCUMENTED**
**Description:** Workflow configurations

---

#### `GET /oauthApps/index`
**Status:** **UNDOCUMENTED**
**Description:** OAuth application management

---

#### `GET /help`
**Status:** **UNDOCUMENTED**
**Description:** API help/documentation endpoint

---

### 11. Practice-Specific Case Views

These endpoints return detailed practice-specific information for cases:

#### `GET /injuries/view/{case_file_id}`
**Status:** **UNDOCUMENTED**
**Description:** Injury details for personal injury cases

**Response:**
```json
{
  "body_parts": ["neck", "back", "shoulder"],
  "injury_date": "2024-01-15",
  "treatment_ongoing": true,
  "prognosis": "..."
}
```

---

#### `GET /vehicleAccidents/view/{case_file_id}`
**Status:** **UNDOCUMENTED**
**Description:** Vehicle accident details

---

#### `GET /generalIncidents/view/{case_file_id}`
**Status:** **UNDOCUMENTED**
**Description:** General incident details

---

#### `GET /malpractices/view/{case_file_id}`
**Status:** **UNDOCUMENTED**
**Description:** Medical malpractice details

---

#### `GET /premiseLiabilities/view/{case_file_id}`
**Status:** **UNDOCUMENTED**
**Description:** Premise liability details

---

#### `GET /productLiabilities/view/{case_file_id}`
**Status:** **UNDOCUMENTED**
**Description:** Product liability details

---

#### `GET /arrests/view/{case_file_id}`
**Status:** **UNDOCUMENTED**
**Description:** Arrest details for criminal cases

---

## Permission-Denied Endpoints (6)

These endpoints exist but require elevated permissions:

| Endpoint | Description | Required Permission |
|----------|-------------|---------------------|
| `GET /firms/index` | List all firms | Admin/Owner |
| `GET /firms/view` | Firm details | Admin/Owner |
| `GET /preferences/index` | User preferences | Admin |
| `GET /damages/index` | Damages (PI) | Special access |
| `GET /settlements/index` | Settlements | Special access |
| `GET /pages/index` | CMS pages | Admin |

---

## Not Found Endpoints (111)

The following endpoint patterns were tested but returned 404:

### Documents (Not Found)
- `folders/index`, `documentFolders/index`, `documentTypes/index`
- `fileTypes/index`, `attachments/index`

### Contacts (Not Found)
- `partyTypes/index`, `vendors/index`, `clients/index`
- `attorneys/index`, `experts/index`, `witnesses/index`
- `insuranceCompanies/index`, `employers/index`
- `doctors/index`, `medicalProviders/index`

### Case Details (Not Found)
- `caseStages/index`, `practiceAreas/index`
- `venues/index`, `judges/index`, `jurisdictions/index`

### Billing (Not Found)
- `payments/index`, `expenses/index`, `timeEntries/index`
- `retainers/index`, `fees/index`, `costs/index`, `disbursements/index`

### Calendar (Not Found)
- `appointments/index`, `deadlines/index`, `reminders/index`
- `courtDates/index`, `depositions/index`, `hearings/index`
- `trials/index`, `mediations/index`, `arbitrations/index`
- `limitationDates/index`

### Communications (Not Found)
- `emails/index`, `notes/index`, `phoneCalls/index`
- `letters/index`, `faxes/index`, `communications/index`

### Admin (Not Found)
- `offices/index`, `branches/index`, `departments/index`
- `teams/index`, `roles/index`, `permissions/index`
- `settings/index`

### Reports (Not Found)
- `dashboards/index`, `analytics/index`
- `statistics/index`, `metrics/index`

### Workflows (Not Found)
- `automations/index`, `templates/index`
- `documentTemplates/index`, `emailTemplates/index`
- `checklists/index`

### Integrations (Not Found)
- `integrations/index`, `webhooks/index`, `apiKeys/index`

### Practice-Specific (Not Found)
- `wcClaims/index`, `wcBenefits/index`, `wcInjuries/index`
- `bodyParts/index`, `injuryTypes/index`, `treatmentTypes/index`
- `qme/index`, `ame/index`, `pqme/index`
- `medicalRecords/index`, `medicalReports/index`
- `piCases/index`, `demands/index`, `liens/index`, `medicalBills/index`
- `immigrationCases/index`, `visaTypes/index`, `petitions/index`
- `familyCases/index`, `custodyOrders/index`, `supportOrders/index`
- `discovery/index`, `interrogatories/index`, `admissions/index`
- `productionRequests/index`, `subpoenas/index`, `motions/index`
- `pleadings/index`, `filings/index`, `orders/index`, `judgments/index`

### Misc (Not Found)
- `tags/index`, `categories/index`, `comments/index`
- `logs/index`, `auditLogs/index`, `activityLogs/index`
- `notifications/index`, `alerts/index`
- `api/version`, `version`, `status`, `health`
- `info`, `schema`, `endpoints`, `docs`

---

## URL Pattern Support

MerusCase API accepts multiple URL naming conventions:

| Pattern | Example | Status |
|---------|---------|--------|
| camelCase (primary) | `caseFiles/index` | Works |
| snake_case | `case_files` | Works |
| PascalCase | `CaseFiles` | Works |
| kebab-case | `case-files` | Not Found |

---

## Response Format Patterns

### Standard Data Wrapper
Most endpoints return data in this format:
```json
{
  "data": {
    "{id}": { "id": "{id}", "field": "value" },
    "{id2}": { "id": "{id2}", "field": "value" }
  }
}
```

**Note:** Data is keyed by ID (object), not an array.

### With Timestamp
Some endpoints include sync timestamps:
```json
{
  "data": { ... },
  "lastQueryAt": "2026-01-13T09:38:18"
}
```

### With Current Time
Events endpoint includes server time:
```json
{
  "now": "2026-01-13T09:38:18",
  "data": { ... },
  "lastQueryAt": "2026-01-13T09:38:18"
}
```

### Error Response
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

### Success Flag Pattern
Some endpoints use a different pattern:
```json
{
  "success": true,
  "msg": "Operation completed"
}
```

---

## Error Handling

### HTTP Status Codes

| Code | Meaning | Action |
|------|---------|--------|
| 200 | Success | Parse JSON response |
| 302 | Redirect | Follow Location header (document downloads) |
| 401 | Unauthorized | Refresh token or re-authenticate |
| 403 | Forbidden | Insufficient permissions |
| 404 | Not Found | Endpoint doesn't exist |
| 429 | Rate Limited | Wait and retry |
| 500 | Server Error | Retry with backoff |

### Application-Level Errors

Even with HTTP 200, check for errors in response:
```python
response = await client.get(endpoint)
data = response.json()

if "errors" in data and data["errors"]:
    error = data["errors"][0]
    error_type = error.get("errorType", "unknown")
    error_msg = error.get("errorMessage", "Unknown error")
    # Handle error
```

---

## Rate Limiting

MerusCase implements rate limiting. Check response headers:

```http
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1705142400
```

**Recommendations:**
- Implement exponential backoff on 429 responses
- Cache reference data (case types, statuses, etc.)
- Use `lastQueryAt` for incremental sync

---

## Incremental Sync

Many endpoints support incremental synchronization:

```
GET /uploads/index?lastQueryAt=2026-01-12T00:00:00
```

This returns only records modified since the specified timestamp.

---

## Recommendations

### High-Value Endpoints to Utilize

1. **`uploads/index` + `documents/download`** - Full document management capability
2. **`contacts/index` + `companies/index`** - CRM functionality
3. **`invoices/index` + `caseLedgers/index`** - Complete billing visibility
4. **Practice-specific views** - Rich case data for PI, WC, malpractice

### Endpoints Needing Further Investigation

1. **POST endpoints** - Exploration focused on GET; POST/PUT/DELETE untested
2. **Permission-denied endpoints** - May be accessible with different user roles
3. **Webhook integration** - No webhook endpoints found, may use different pattern

### Security Considerations

1. Token has ~30 year expiry - consider implementing rotation
2. S3 signed URLs expire - don't cache download URLs
3. Some endpoints return PII - implement appropriate data handling

---

## Appendix A: Exploration Methodology

### Test Script
```python
async def test_endpoint(client, method, endpoint):
    resp = await client.get(f"{API_BASE}/{endpoint}")
    data = resp.json()

    if resp.status_code == 200:
        if "errors" in data and data.get("errors"):
            # Categorize error type
            error = data["errors"][0]
            if "not_allowed" in error.get("errorType", ""):
                return "permission_denied"
            elif "required" in error.get("errorMessage", "").lower():
                return "needs_params"
            else:
                return "other_error"
        else:
            return "working"
    elif resp.status_code == 404:
        return "not_found"
    else:
        return "other_error"
```

### Endpoint Generation
Endpoints were generated based on:
1. Official MerusCase API documentation (17 endpoints)
2. CakePHP naming conventions (`{model}/index`, `{model}/view/{id}`)
3. Legal practice management domain knowledge
4. Common REST patterns

---

## Appendix B: Raw Results

Full exploration results are saved to:
- `api_exploration_results.json` - JSON format
- `full_api_exploration.py` - Test script

### Statistics Summary
```
Working:           34 (21%)
Permission Denied:  6 (4%)
Not Found:        111 (69%)
Other Errors:       9 (6%)
------------------------
Total Tested:     162
```

---

## Appendix C: Client Implementation

The `meruscase_api/client.py` module has been updated with methods for all discovered endpoints:

### New Methods Added (30+)

**Documents:**
- `list_uploads(case_file_id?, limit?)` → Upload list
- `download_document(upload_id)` → S3 signed URL
- `download_document_bytes(upload_id)` → Raw file bytes

**Contacts:**
- `list_contacts(limit?)` → Contact list
- `get_contact(contact_id)` → Contact details
- `list_companies(limit?)` → Company list

**Billing:**
- `list_all_ledgers(case_file_id?, limit?)` → All ledger entries
- `list_invoices(case_file_id?, limit?)` → Invoice list
- `get_billing_rates()` → Billing rate configuration
- `list_trust_accounts()` → Trust account list
- `list_receivables(case_file_id?, limit?)` → Receivables

**Reference Data:**
- `get_case_types()` → Case type list
- `get_case_statuses()` → Case status list
- `get_event_types()` → Event type list
- `get_party_groups()` → Party group definitions
- `get_people_types()` → People type definitions
- `get_courts()` → Court list
- `get_statutes()` → Statutes of limitations
- `get_payment_methods()` → Payment methods

**Events & Messages:**
- `list_events(case_file_id?, limit?)` → Event list
- `list_messages(limit?)` → Internal messages

**Practice-Specific:**
- `get_case_injuries(case_file_id)` → Injury details
- `get_case_vehicle_accident(case_file_id)` → Vehicle accident details
- `get_case_general_incident(case_file_id)` → General incident details
- `get_case_malpractice(case_file_id)` → Malpractice details
- `get_case_premise_liability(case_file_id)` → Premise liability details
- `get_case_product_liability(case_file_id)` → Product liability details
- `get_case_arrest(case_file_id)` → Arrest details

**Users:**
- `list_users()` → Firm user list

---

*Report generated by Claude Code automated API exploration*
*Last updated: January 13, 2026*
