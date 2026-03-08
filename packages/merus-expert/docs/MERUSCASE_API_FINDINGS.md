# MerusCase API - Extended Endpoint Discovery

**For:** Adjudica Development Team
**Date:** January 2026

---

## Overview

While reviewing MerusCase integration options, I came across some additional API endpoints that aren't in their official documentation. Thought this might save you some time if you're working on the integration.

The official docs only cover about half of what's actually available. Here's what I found that could be useful.

---

## OAuth Setup

Their docs are light on OAuth details. Here's what you need:

| Setting | Value |
|---------|-------|
| Base URL | `https://api.meruscase.com` |
| Authorization URL | `https://api.meruscase.com/oauth/authorize` |
| Token URL | `https://api.meruscase.com/oauth/token` |
| Callback URL | `https://api.meruscase.com/oauth/authcodeCallback` |
| Grant Type | `authorization_code` |

**Note:** Tokens have a very long expiry (~30 years), so you won't need to handle refresh logic frequently.

---

## The Big Win: Document Downloads

Their docs don't mention it, but **you can download documents via API**:

```
GET /documents/download/{upload_id}
```

Returns a 302 redirect to an S3 signed URL. Just follow the redirect to get the file bytes.

To get upload IDs:
```
GET /uploads/index
GET /uploads/index?case_file_id={id}
```

This is huge - means we don't need to scrape the UI for document retrieval.

**Important:** The S3 signed URLs expire quickly (minutes, not hours). Don't cache the download URLs - always fetch a fresh one when you need to download.

---

## Additional Working Endpoints

### Contacts & Companies
| Endpoint | What it does |
|----------|--------------|
| `GET /contacts/index` | All contacts |
| `GET /contacts/view/{id}` | Contact details |
| `GET /companies/index` | All companies |

### Extended Billing
| Endpoint | What it does |
|----------|--------------|
| `GET /caseLedgers/index` | All ledgers (not just open/reviewed) |
| `GET /invoices/index` | Invoice list |
| `GET /billingRates/index` | Rate configuration |
| `GET /trustAccounts/index` | Trust accounts |

### Reference Data
| Endpoint | What it does |
|----------|--------------|
| `GET /caseStatuses/index` | Case status options |
| `GET /courts/index` | Court listings |
| `GET /peopleTypes/index` | Party type definitions |

### Other
| Endpoint | What it does |
|----------|--------------|
| `GET /messages/index` | Internal messages |
| `GET /workflows/index` | Workflow configs |
| `GET /reports/index` | Report definitions |

---

## Response Format Notes

Their API returns data keyed by ID, not as arrays:

```json
{
  "data": {
    "123": { "id": "123", "name": "..." },
    "456": { "id": "456", "name": "..." }
  }
}
```

Some endpoints include a sync timestamp:
```json
{
  "data": { ... },
  "lastQueryAt": "2026-01-13T09:38:18"
}
```

You can pass `?lastQueryAt=` to get incremental updates.

---

## Needs Elevated Permissions

These exist but our current token doesn't have access:
- `/firms/index` and `/firms/view`
- `/damages/index` and `/settlements/index`
- `/preferences/index`

Might be worth checking if we can get a higher-privilege token.

---

## URL Patterns

FYI, their API accepts multiple naming styles:
- `caseFiles/index` (camelCase) - primary
- `case_files` (snake_case) - works
- `CaseFiles` (PascalCase) - works

---

## Gotcha: Error Handling

**This one bit me:** Their API can return errors inside a 200 response. Always check for an `errors` key:

```python
response = requests.get(endpoint, headers=auth)
data = response.json()

# Don't just check status code!
if "errors" in data and data["errors"]:
    error = data["errors"][0]
    print(f"Error: {error.get('errorMessage')}")
else:
    # Actually successful
    process(data)
```

Error response inside 200:
```json
{
  "errors": [{
    "errorType": "not_allowed",
    "errorMessage": "You do not have privilege to access this resource"
  }]
}
```

---

## Rate Limiting

They have rate limits. Watch these response headers:

```
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1705142400
```

Recommend implementing exponential backoff if you hit 429 responses.

---

## Incremental Sync

Most list endpoints support a `lastQueryAt` parameter for delta updates:

```
GET /uploads/index?lastQueryAt=2026-01-12T00:00:00
```

Returns only records modified since that timestamp. The response includes a new `lastQueryAt` value to use for the next sync.

---

## Quick Reference

**Document download flow:**
```python
# 1. List uploads
resp = requests.get(f"{API}/uploads/index?case_file_id={case_id}", headers=auth)
uploads = resp.json()["data"]

# 2. Download a file
upload_id = list(uploads.keys())[0]
resp = requests.get(f"{API}/documents/download/{upload_id}", headers=auth, allow_redirects=False)
s3_url = resp.headers["Location"]

# 3. Get file bytes
file_bytes = requests.get(s3_url).content
```

---

Let me know if you want me to dig into any of these further or if there are other endpoints you're wondering about.
