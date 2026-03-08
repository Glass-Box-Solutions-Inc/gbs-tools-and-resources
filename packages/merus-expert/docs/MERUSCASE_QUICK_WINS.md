# MerusCase API - Quick Wins

Found some undocumented endpoints that could speed up our integration.

## Document Downloads (Not in their docs!)

```
GET /uploads/index              → List all documents
GET /documents/download/{id}    → Download file (returns S3 URL)
```

This means we can pull documents via API instead of browser automation.

## Other Useful Endpoints

**Contacts:**
- `/contacts/index` - all contacts
- `/companies/index` - all companies

**Billing:**
- `/invoices/index` - invoices
- `/caseLedgers/index` - all ledger entries
- `/billingRates/index` - rate configs

**Reference data:**
- `/caseStatuses/index` - status options
- `/courts/index` - court listings (WCAB locations)
- `/peopleTypes/index` - party type definitions

## Gotchas

**Response format** - Data keyed by ID, not arrays:
```json
{"data": {"123": {...}, "456": {...}}}
```
Use `Object.values()` or similar.

**Errors in 200s** - Always check for `"errors"` key in response, even on HTTP 200.

**S3 URLs expire** - Document download URLs expire in minutes. Don't cache them.

**Rate limits** - Watch `X-RateLimit-Remaining` header.

---

## OAuth Endpoints

| Setting | Value |
|---------|-------|
| Auth URL | `https://api.meruscase.com/oauth/authorize` |
| Token URL | `https://api.meruscase.com/oauth/token` |
| Callback | `https://api.meruscase.com/oauth/authcodeCallback` |

Tokens last ~30 years, so refresh logic isn't critical.

---

Happy to walk through any of these if helpful.
