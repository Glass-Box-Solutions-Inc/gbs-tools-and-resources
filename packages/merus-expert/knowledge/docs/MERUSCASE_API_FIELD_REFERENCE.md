# MerusCase API — Complete Field Reference

**Last Updated:** 2026-02-19 (live-tested)
**API Base URL:** `https://api.meruscase.com`
**Authentication:** OAuth 2.0 Bearer Token (~30-year expiry, no refresh needed)
**Test Case:** ANDREWS, DENNIS — case_file_id: `56171871`

> All field names, IDs, and validation rules in this document were confirmed against a live
> MerusCase environment. Fields marked ❓ were sent on POST but not reflected in the GET
> response and require further investigation.

---

## Table of Contents

1. [Endpoint Inventory](#endpoint-inventory)
2. [Response Format Rules](#response-format-rules)
3. [Entity: Case File](#entity-case-file)
4. [Entity: Activity](#entity-activity)
5. [Entity: Party](#entity-party)
6. [Entity: Case Ledger](#entity-case-ledger)
7. [Entity: Upload / Document](#entity-upload--document)
8. [Reference Data Tables](#reference-data-tables)
9. [Multiplicity Rules](#multiplicity-rules)
10. [Validation Rules & Gotchas](#validation-rules--gotchas)
11. [URL & Pattern Notes](#url--pattern-notes)

---

## Endpoint Inventory

All 39 endpoints tested on 2026-02-19. 37/39 returned HTTP 200.

### ✅ Fully Working (37/39)

#### Case Management
| Endpoint | Method | Description | Live Count |
|----------|--------|-------------|-----------|
| `GET /caseFiles/index` | GET | List all cases (keyed by ID) | 65 |
| `GET /caseFiles/view/{case_id}` | GET | Full case record + applicant contact | — |
| `GET /caseTypes/index` | GET | All case type definitions | 29 |
| `GET /caseStatuses/index` | GET | All case status definitions | 12 |
| `POST /caseFiles/add` | POST | Create new case (browser-only, see note) | — |

#### Activities & Notes
| Endpoint | Method | Description | Live Count |
|----------|--------|-------------|-----------|
| `GET /activities/index/{case_id}` | GET | All activities for a case | 243 |
| `GET /activityTypes/index` | GET | All activity type definitions | 56 |
| `POST /activities/add` | POST | Create activity/note | — |

#### Documents & Uploads
| Endpoint | Method | Description | Live Count |
|----------|--------|-------------|-----------|
| `GET /uploads/index` | GET | All uploads firm-wide | 334 |
| `GET /uploads/index?case_file_id={id}` | GET | Uploads for a specific case | 334 |
| `GET /documents/index` | GET | Document metadata | 0 (empty for WC) |
| `GET /documents/download/{upload_id}` | GET | 302 → S3 signed URL | — |

#### Parties & Contacts
| Endpoint | Method | Description | Live Count |
|----------|--------|-------------|-----------|
| `GET /parties/view/{case_id}` | GET | Parties for a case | 1 |
| `GET /partyGroups/index` | GET | Party groups | 0 (empty) |
| `GET /contacts/index` | GET | All contacts (name tuples) | 153 |
| `GET /companies/index` | GET | All companies | 39 |
| `GET /peopleTypes/index` | GET | Party/people type definitions | 102 |
| `POST /parties/add` | POST | Create party | — |

#### Billing & Finance
| Endpoint | Method | Description | Live Count |
|----------|--------|-------------|-----------|
| `GET /billingCodes/index` | GET | Billing codes | 1 |
| `GET /billingRates/index` | GET | Per-case rate config (keyed by case_id) | 65 |
| `GET /caseLedgers/index` | GET | All ledger entries | 7 |
| `GET /caseLedgersOpen/index` | GET | Open (un-reviewed) ledger entries | 7 |
| `GET /caseLedgersReviewed/index` | GET | Reviewed ledger entries | 0 |
| `GET /invoices/index` | GET | Invoices (requires valid filter) | — |
| `GET /receivables/index` | GET | Receivables | 0 |
| `GET /paymentMethods/index` | GET | Payment method options | 6 |
| `POST /caseLedgers/add` | POST | Create ledger entry | — |

#### Reference Data
| Endpoint | Method | Description | Live Count |
|----------|--------|-------------|-----------|
| `GET /statutes/index` | GET | Statutes of limitations | 1 |
| `GET /courts/index` | GET | Courts | 3,418 |
| `GET /users/index` | GET | Firm users | 5 |
| `GET /paymentMethods/index` | GET | Payment methods | 6 |
| `GET /eventTypes/index` | GET | Event types | 3 |
| `GET /tasks/index` | GET | Tasks | 0 |
| `GET /events/index` | GET | Events | 0 |
| `GET /messages/index` | GET | Internal messages | 0 |
| `GET /reports/index` | GET | Report definitions | 55 |
| `GET /workflows/index` | GET | Workflows | 0 |
| `GET /oauthApps/index` | GET | OAuth apps registered | 49 |
| `GET /help` | GET | API help docs (120 sections) | — |

#### URL Pattern Variants
| Endpoint | Result |
|----------|--------|
| `GET /case_files` | ✅ 200 (snake_case works) |
| `GET /CaseFiles` | ✅ 200 (PascalCase works) |

### ❌ Non-Working (2/39)
| Endpoint | Issue |
|----------|-------|
| `GET /trustAccounts/index` | Returns non-JSON (HTML or empty body) |
| `GET /activities/index/56171905` | Returns non-JSON for this specific case |

### 🔒 Permission-Restricted (not tested here)
`/firms/index`, `/firms/view`, `/damages/index`, `/settlements/index`, `/preferences/index`

---

## Response Format Rules

### Standard: dict-keyed by ID
```json
{
  "data": {
    "56171871": { "id": "56171871", "name": "...", ... },
    "56171872": { "id": "56171872", "name": "...", ... }
  },
  "lastQueryAt": "2026-02-19T07:23:54"
}
```

### List variant (some endpoints)
```json
{ "data": [ "Smith", "Joyce" ] }
```
`/contacts/index` returns contact names as `[last_name, first_name]` tuples.

### POST success
```json
{ "success": 1, "data": { "CaseLedger": { "id": 112349369, ... } } }
```
or just `{ "id": "931874402" }` for activities.

### POST failure (inside HTTP 200!)
```json
{ "success": 0, "errors": "Provided values do not calculate correctly" }
```
**Always check `success` field, not just HTTP status.**

### Incremental sync
Pass `?lastQueryAt=YYYY-MM-DDTHH:MM:SS` to get only records modified since that time.

---

## Entity: Case File

### GET `/caseFiles/view/{case_id}` — full record

```
CaseFile object (all confirmed fields):
```

| Field | Type | Description | UI Location |
|-------|------|-------------|-------------|
| `id` | int | Case file ID | — (internal) |
| `name` | str | Auto-generated: `"LAST, FIRST"` | Header of every case page |
| `caption` | str | Same as name unless customized | Legal documents |
| `case_type_id` | int | → caseTypes/index | Case Details tab |
| `case_status_id` | int | → caseStatuses/index | Case Details tab / status badge |
| `side_represented` | str | `"plaintiff"` / `"defense"` | Case Details tab |
| `case_jurisdiction` | str | Jurisdiction text | Case Details tab |
| `venue_id` | int | Court venue | Case Details tab |
| `file_number` | str | Firm's internal file number | Case list, header |
| `case_file_number` | int | Sequential number auto-assigned | — |
| `principal_claim_number` | str\|null | WC claim number | Case Details / WC tab |
| `file_location` | str | Physical file location | Case Details tab |
| `firm_office_id` | int | Office assignment | Case Details tab |
| `attorney_responsible` | int | user_id | Case Details tab — Staff section |
| `rate_attorney_responsible` | float | Override billing rate | Billing configuration |
| `senior_associate_handling` | int | user_id | Case Details tab — Staff section |
| `rate_senior_associate_handling` | float | Override rate | Billing configuration |
| `attorney_handling` | int | user_id | Case Details tab — Staff section |
| `rate_attorney_handling` | float | Override rate | Billing configuration |
| `paralegal_handling` | int | user_id | Case Details tab — Staff section |
| `rate_paralegal_handling` | float | Override rate | Billing configuration |
| `secretary_handling` | int | user_id | Case Details tab — Staff section |
| `rate_secretary_handling` | float | Override rate | Billing configuration |
| `hearing_rep` | int | user_id | Case Details tab — Staff section |
| `rate_hearing_rep` | float | Override rate | Billing configuration |
| `attorney_4` | int | user_id (spare slot) | Case Details tab |
| `rate_attorney_4` | float | Override rate | Billing configuration |
| `staff_4` | int | user_id (spare slot) | Case Details tab |
| `rate_staff_4` | float | Override rate | Billing configuration |
| `date_entered` | date | When case was added | Case Details tab |
| `date_opened` | date | Case open date | Case Details tab |
| `date_original_closed` | date\|null | First close date | Case history |
| `date_closed` | date\|null | Current close date | Case Details tab |
| `date_reopened` | date\|null | Reopen date | Case history |
| `reopened_reason` | str | Text reason for reopen | Case Details tab |
| `date_referred` | date\|null | Referral date | Case Details tab |
| `referred_by` | str\|null | Referral source | Case Details tab |
| `permanent_and_stationary_date` | date\|null | P&S date (WC) | WC Details tab |
| `date_mmi_hide_until` | date\|null | MMI hidden until | WC Details tab |
| `billing_increment_minutes` | int\|null | Override billing increment | Billing config |
| `billto_contact_id` | int | Contact for invoicing | Billing tab |
| `invoice_min` / `invoice_max` | str | Invoice min/max amounts | Billing configuration |
| `comments` | str | Case comments/notes | Case Details tab |
| `special_handling_comments` | str\|null | Special handling notes | Case Details tab |
| `is_protected` | bool | Protected case flag | Case list / access control |
| `is_master_file` | int | Master file indicator | Case list |
| `custom_data` | JSON\|null | Firm-specific custom fields | Varies |
| `deleted` | bool | Soft delete flag | — |
| `created` / `modified` | datetime | Timestamps | — |

### GET `/caseFiles/index` — list record (abbreviated)
```json
{
  "0": "85",           // case_file_number
  "1": "ANDREWS, DENNIS",  // name
  "3": 1,              // case_type_id
  "4": 229099,         // case_status_id
  "5": [],             // party_ids?
  "13": 0,             // ?
  "15": 16571,         // firm_office_id
  "16": 0,             // ?
  "case_jurisdiction": ""
}
```
List format uses numeric keys — use `caseFiles/view/{id}` for full named fields.

---

## Entity: Activity

### POST `/activities/add` — write fields

| Field | Type | Required | Description | UI Location |
|-------|------|----------|-------------|-------------|
| `case_file_id` | int | ✅ | Case to attach to | — |
| `activity_type_id` | int | ✅ | → activityTypes/index | Activities tab — type badge |
| `subject` | str | ✅ | Short subject line | Activities tab — list row title |
| `description` | str | — | Full body text | Activities tab — expanded view |
| `date` | datetime str | — | Activity date (`YYYY-MM-DD HH:MM:SS`) | Activities tab — date column |
| `duration` | int | — | Duration in **minutes** | Activities tab — duration field |
| `billable` | int | — | `1` = billable, `0` = non-billable | Billing tab (if billable) |
| `billing_code_id` | int | — | → billingCodes/index | Activities tab / billing |
| `user_id` | int | — | Responsible user | Activities tab — user column |
| `document_author` | str | — | Document author name | Activities tab — document metadata |
| `date_received` | date str | — | Date document was received | Activities tab — document dates |
| `date_of_service` | date str | — | Date of service | Activities tab — document dates |
| `document_date` | date str | — | Document date | Activities tab — document dates |

### GET `/activities/index/{case_id}` — response fields

The GET response uses numeric keys (CakePHP legacy format):

| Numeric Key | Named Field | Description |
|-------------|-------------|-------------|
| `"0"` | activity_type_id(s) | Array: `[13]` |
| `"1"` | subject | Subject line |
| `"2"` | description | Full text |
| `"3"` | user_id | Responsible user |
| `"4"` | date (unix) | Unix timestamp |
| `"6"` | ? | Unknown |
| `"7"` | billable | 0/1 |
| `"8"` | billing_code_id | nullable |
| `"9"` | ? | Unknown |
| `"10"` | ? | Array |
| `"created"` | created | Unix timestamp |
| `"group_uuid"` | group_uuid | nullable |
| `"filename"` | filename | Document filename |
| `"size"` | size | File size |
| `"case_file_id"` | case_file_id | Parent case |
| `"user_initials"` | user_initials | e.g., `"AB"` |
| `"document_date"` | document_date | false or date |
| `"date_received"` | date_received | false or date |
| `"date_of_service"` | date_of_service | false or date |
| `"document_author"` | document_author | str |

**POST response:** `{ "id": "931874402" }` — just the new activity ID.

### Activity Types (viewable=1 = user-created activities)

| ID | Name | UI Tab |
|----|------|--------|
| 100 | Manual Entry | Activities |
| 101 | Note | Activities |
| 102 | Letter Sent | Activities |
| 103 | Fax Sent | Activities |
| 104 | Email Sent | Activities |
| 105 | Letter Received | Activities |
| 106 | Fax Received | Activities |
| 107 | Email Received | Activities |
| 108 | Proof Sent | Activities |
| 109 | Fee | Activities / Billing |
| 110 | Payment | Activities / Billing |
| 111 | Telephone Call | Activities |
| 112 | Copy Service Request | Activities |
| 113 | Reviewed | Activities |
| 114 | Electronic Signature | Activities |
| 115 | Court Rules | Activities |
| 99047 | Indexable (firm-specific) | Activities |

**System types (viewable=0, auto-created):** Hidden (1), Automatic (2), Case Created (13), Status Changed (6), Event Created (12), Task Created (20), Document (9), Form Created/Edited/Completed (3,4,5), DWC Parcel types (30-37), etc.

---

## Entity: Party

### POST `/parties/add` — write fields

| Field | Type | Required | Description | UI Location |
|-------|------|----------|-------------|-------------|
| `case_file_id` | int | ✅ | Case to attach to | — |
| `party_type` | str | ✅ | e.g., `"Other"`, `"Client"`, `"Insurance Company"` | Parties tab — type badge |
| `first_name` | str | — | First name | Parties tab — contact card |
| `middle_name` | str | — | Middle name | Parties tab — contact card |
| `last_name` | str | — | Last name | Parties tab — contact card |
| `company_name` | str | — | Organization name | Parties tab — contact card |
| `email` | str | — | Email address | Parties tab — contact info |
| `phone` | str | — | Phone number | Parties tab — contact info |
| `address` | str | — | Street address | Parties tab — contact info |
| `city` | str | — | City | Parties tab — contact info |
| `state` | str | — | State (2-letter) | Parties tab — contact info |
| `zip` | str | — | ZIP code | Parties tab — contact info |
| `notes` | str | — | Free-form notes | Parties tab — Notes section |
| `testimony` | str | — | Testimony notes | Parties tab — Testimony section |
| `people_type_detail` | str | — | Sub-type detail | Parties tab — type details |
| `insurance_policy_number` | str | — | Primary insurance policy # | Parties tab — Insurance section |
| `insurance_claim_number` | str | — | Primary claim # | Parties tab — Insurance section |
| `insurance_claim_status` | str | — | Primary claim status | Parties tab — Insurance section |
| `insurance_policy_notes` | str | — | Primary policy notes | Parties tab — Insurance section |
| `alternate_insurance_policy_number` | str | — | Secondary policy # | Parties tab — Alternate Insurance |
| `alternate_insurance_claim_number` | str | — | Secondary claim # | Parties tab — Alternate Insurance |
| `alternate_insurance_claim_status` | str | — | Secondary claim status | Parties tab — Alternate Insurance |
| `alternate_insurance_policy_notes` | str | — | Secondary policy notes | Parties tab — Alternate Insurance |

### GET `/parties/view/{case_id}` — response fields

```json
{
  "data": {
    "32690995": {
      "0": 1906148,           // people_type_id (→ peopleTypes/index)
      "1": "DENNIS",          // first_name
      "2": "ANDREWS",         // last_name
      "3": "",                // ?
      "4": 0,                 // has_address
      "5": 29232639,          // contact_id (→ contacts)
      "middle_name": "",
      "has_address": 0,
      "parent_company_name": "",
      "is_hidden": 0,
      "notes": "",
      "testimony": "",
      "people_type_detail": "",
      "insurance_policy_number": "",
      "insurance_claim_number": "",
      "insurance_claim_status": "",
      "insurance_policy_notes": "",
      "alternate_insurance_policy_number": "",
      "alternate_insurance_claim_number": "",
      "alternate_insurance_claim_status": "",
      "alternate_insurance_policy_notes": "",
      "party_groups": [],     // array — can belong to multiple groups
      "is_primary": true,
      "is_archived": false
    }
  }
}
```

**POST response:**
```json
{
  "partiesId": "33018010",
  "parties": { "data": { ... existing parties on case ... } },
  "msg": "Party has been added successfully.",
  "contact": false
}
```

### Insurance field structure
The insurance design is a fixed **two-slot** system:
- **Primary:** `insurance_policy_number`, `insurance_claim_number`, `insurance_claim_status`, `insurance_policy_notes`
- **Alternate:** `alternate_insurance_policy_number`, `alternate_insurance_claim_number`, `alternate_insurance_claim_status`, `alternate_insurance_policy_notes`

For a 3rd+ carrier, add a separate **Party record** with `party_type: "Insurance Company"`.

---

## Entity: Case Ledger

### POST `/caseLedgers/add` — write fields

| Field | Type | Required | Description | UI Location |
|-------|------|----------|-------------|-------------|
| `case_file_id` | str\|int | ✅ | Case to attach to | — |
| `amount` | str | ✅ | Dollar amount (stored negative, see note) | Billing tab — Amount column |
| `description` | str | ✅ | Entry description | Billing tab — Description column |
| `date` | str | ✅ | Entry date (`YYYY-MM-DD`) | Billing tab — Date column |
| `ledger_type_id` | int | ✅ | Type (1=FEE, 2=COST, 3=EXPENSE, see table) | Billing tab — Type badge |
| `hours` | str | — | Hours (FEE type only, must be multiple of 0.1) | Billing tab — Hours column |
| `hourly_rate` | str | — | Rate per hour (FEE type only) | Billing tab — Rate |
| `item_qty` | str | — | Quantity (COST/EXPENSE types) | Billing tab — Qty |
| `unit_cost` | str | — | Unit cost (COST/EXPENSE types) | Billing tab — Unit cost |
| `payee` | str | — | Who is owed | Billing tab — Payee column |
| `payto` | str | — | Who to pay | Billing tab — Pay To column |
| `task_code` | str | — | UTBMS task code | Billing / LEDES export |
| `activity_code` | str | — | UTBMS activity code | Billing / LEDES export |
| `expense_code` | str | — | UTBMS expense code | Billing / LEDES export |
| `alternate_billing_code` | str | — | Custom billing code | Billing |
| `billing_code_id` | str | — | → billingCodes/index | Billing |
| `user_id` | str | — | Responsible user | Billing tab — User column |

### GET `/caseLedgers/index` — full response record

```json
{
  "id": 112349369,
  "user_id": 1973975,
  "firm_id": 30298,
  "case_file_id": 56171871,
  "account_id": 1,
  "ledger_type_id": 1,
  "status_id": 1,
  "date": "1771488000",        // Unix timestamp
  "description": "...",
  "hours": 0.5,                // null if not time-based
  "item_qty": null,
  "hourly_rate": 200,          // null if not time-based
  "unit_cost": null,
  "amount": -100,              // STORED AS NEGATIVE (charges are negative)
  "amount_received": 0,
  "payee": "...",
  "billto_contact_id": 0,
  "invoice_id": null,
  "bill_id": null,
  "settlement_id": null,
  "payto": "...",
  "payto_contact_id": null,
  "task_code": "...",
  "activity_code": "...",
  "expense_code": null,
  "alternate_billing_code": "...",
  "source_key": null,
  "created_by": 1973975,
  "activity_id": null,
  "export_upload_id": null,
  "is_rejected": false,
  "is_reviewed": false,
  "deleted": false,
  "created": "2026-02-18 23:23:55",
  "modified": "2026-02-18 23:23:55",
  // GET /caseLedgers/index only (not in POST response):
  "billto_contact_first_name": null,
  "billto_contact_last_name": null,
  "billto_contact_name": null,
  "billto_contact_parent_id": null
}
```

### Ledger Type IDs
| ID | Name | Hours field | qty/unit fields |
|----|------|-------------|-----------------|
| 1 | FEE | ✅ hours + hourly_rate | ❌ not used |
| 2 | COST | ❌ not used | ✅ item_qty + unit_cost (optional) |
| 3 | EXPENSE | ❌ not used | ✅ item_qty + unit_cost (optional) |

**Amount sign convention:** Submitted as positive (e.g., `"100.00"`), stored and returned as negative (`-100`). This is normal — MerusCase displays amounts correctly in the UI.

---

## Entity: Upload / Document

### GET `/uploads/index?case_file_id={id}`

```json
{
  "activity_id": "927438612",   // linked activity
  "filename": "...",             // original filename
  "case_file_id": 56171905,
  "chron": "1770327809",         // unix timestamp (chronological sort)
  "8": "application/pdf",        // MIME type
  "0": [9],                      // [activity_type_id]
  "2": "",                       // description?
  "staff": [0,0,0,0,0,0],        // staff access
  "group_uuid": null
}
```

### Document Download Flow
```
GET /documents/download/{upload_id}
→ HTTP 302
→ Location: https://s3.amazonaws.com/...?expires=...
→ GET s3_url → file bytes
```
**S3 signed URLs expire in minutes — never cache, always refetch.**

---

## Reference Data Tables

### Case Types (caseTypes/index)
| ID | Name |
|----|------|
| 1 | Workers' Compensation |
| 2 | Personal Injury - Motor Vehicle Accident |
| 3 | Americans with Disabilities Act |
| 4 | Lien Claim |
| 5 | Third-Party |
| 6 | Attorney |
| 7 | Social Security |
| 8 | Family Law |
| 9 | Civil |
| 10 | Veteran's Administration |
| 11 | Immigration |
| 12 | Bankruptcy |
| 14 | Employment |
| 15 | Criminal |
| 16 | Probate/Conservatorship |
| 17 | Consult Only |
| 18 | Estate Planning (Consult) |
| 19 | Personal Injury - Premise Liability (Slip and Fall) |
| 20 | Personal Injury - Product Liability |
| 21 | Personal Injury - Medical Malpractice |
| 22 | Personal Injury - General |
| 23 | Immigration With Removal |
| 24-26 | Real Estate (Buyer / Seller / Bank/Lender) |
| 27-30 | Family Law (Divorce / Custody / Spousal Support / General) |

### Case Statuses (caseStatuses/index)
| ID | Status | Slug | Billable |
|----|--------|------|---------|
| 229099 | Open | open | ✅ |
| 229100 | Pending | open | ✅ |
| 229101 | Stipulation | closed | ❌ |
| 229102 | Closed | closed | ❌ |
| 229103 | Declined | closed | ❌ |
| 229104 | Deceased | closed | ❌ |
| 229105 | Intake | open | ✅ |
| 229106 | Hold | closed | ❌ |
| 229107 | Dismissed | closed | ❌ |
| 229108 | Other | open | ✅ |
| 229109 | Destroyed | closed | ❌ |
| 229110 | Archived | archived | ❌ |

### Users (users/index)
| ID | Name | Initials | Email | Default Rate |
|----|------|----------|-------|-------------|
| 1973975 | Alex Brewsaugh | AB | alex@adjudica.ai | $400/hr |
| 1979835 | Robee Brightdock | RPD | robee@pioneerdev.ai | $400/hr |
| 1979836 | Steve Brightdock | SBD | steve@brightdock.com | $400/hr |
| 1979837 | Jay BrightDock | JBD | jay@brightdock.com | $400/hr |
| 1979840 | Sai Brightdock | SB | sai@pioneerdev.ai | $400/hr |

### Billing Codes (billingCodes/index)
| ID | Description | Task Code | Disposition |
|----|-------------|-----------|-------------|
| 107105 | Test billing code | None | BILLABLE |

### Payment Methods (paymentMethods/index)
| ID | Description | Account |
|----|-------------|---------|
| 112728 | Check | 1 |
| 112729 | Cash | 1 |
| 112730 | Credit Card | 1 |
| 112731 | Check | 2 |
| 112732 | Cash | 2 |
| 112733 | Credit Card | 2 |

### Event Types (eventTypes/index)
| ID | Name | Color | Slug |
|----|------|-------|------|
| 73286 | Default | #586F8B | default |
| 73287 | Statute | #FF0000 | statute |
| 73288 | Statute Satisfied | #F37F26 | statute-satisfied |

---

## Multiplicity Rules

### Entities that support multiple records per case
| Entity | Endpoint | Notes |
|--------|----------|-------|
| Activities | `POST /activities/add` | Unlimited; each call = new record |
| Parties | `POST /parties/add` | Unlimited; each call = new record |
| Ledger entries | `POST /caseLedgers/add` | Unlimited; each call = new record |
| Documents | `POST /uploads/add` | Unlimited; each call = new record |
| Tasks | `POST /tasks/add` | Unlimited |
| Events | `POST /events/add` | Unlimited |

### Fields that accept arrays within a single record
| Field | Entity | Notes |
|-------|--------|-------|
| `party_groups` | Party | A party can belong to multiple groups |

### Singleton fields (one value per record)
Everything else. To store multiple values (e.g., multiple phone numbers for one contact, 3+ insurance carriers), create separate party records.

---

## Validation Rules & Gotchas

### 🔴 CRITICAL: Ledger FEE hours must be multiples of 0.1

MerusCase enforces **6-minute (0.1-hour) billing increments** on ledger entries.

```
✅ Allowed: 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, ...
❌ Rejected: 0.25, 0.75, 0.33, 0.17 (not whole multiples of 0.1)
```

Sending `hours: "0.25"` returns:
```json
{ "success": 0, "errors": "Provided values do not calculate correctly" }
```

The calculation checked is: `amount == hours * hourly_rate` AND hours must be a multiple of 0.1.

### 🔴 Do NOT mix FEE and COST calculation fields

For `ledger_type_id: 1` (FEE):
- ✅ Send `hours` + `hourly_rate`
- ❌ Do NOT also send `item_qty` / `unit_cost`

For `ledger_type_id: 2/3` (COST/EXPENSE):
- ✅ Send `amount` alone (no calculation fields) — works
- ✅ Send `item_qty` + `unit_cost` — works
- ❌ Do NOT send `hours` / `hourly_rate`

### 🔴 Check `success` field, not HTTP status
API always returns HTTP 200. Read `body.get("success")` to know if POST worked.

### 🟡 Amount is stored as negative
Submit `"100.00"`, the ledger stores `-100`. This is by design — it's a debit in MerusCase's accounting system. Read the sign accordingly.

### 🟡 Activity dates use `"YYYY-MM-DD HH:MM:SS"` format
Ledger dates use `"YYYY-MM-DD"`. Don't mix these up.

### 🟡 GET activity responses use numeric keys
Field names in `activities/index` responses are numeric (`"0"`, `"1"`, `"2"` etc.). Cross-reference with the numeric key table above.

### 🟡 Incremental sync via lastQueryAt
```
GET /activities/index/{case_id}?lastQueryAt=2026-02-19T00:00:00
```
Returns only records modified since that timestamp. Save the returned `lastQueryAt` for the next call.

### 🟡 S3 signed URLs expire quickly
`GET /documents/download/{upload_id}` → 302 to S3. The S3 URL is single-use / short-lived. Always fetch fresh.

### 🟡 activities/add duration field is in minutes
`duration: 42` = 42 minutes. Not hours. Not seconds.

### 🟡 Party GET response uses numeric keys for core fields
`"0"` = people_type_id, `"1"` = first_name, `"2"` = last_name, `"4"` = has_address, `"5"` = contact_id.

---

## URL & Pattern Notes

MerusCase's CakePHP backend accepts three URL styles:

| Style | Example | Works |
|-------|---------|-------|
| camelCase (primary) | `/caseFiles/index` | ✅ |
| snake_case | `/case_files` | ✅ |
| PascalCase | `/CaseFiles` | ✅ |

Standard CRUD patterns:
```
GET  /{resource}/index          → List
GET  /{resource}/index?{filter} → Filtered list
GET  /{resource}/view/{id}      → Single record
POST /{resource}/add            → Create
POST /{resource}/edit/{id}      → Update (not tested)
POST /{resource}/delete/{id}    → Soft delete (not tested)
```

Payload format for POST: `{ "ModelName": { ...fields... } }` (CakePHP convention)

---

*@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology*
