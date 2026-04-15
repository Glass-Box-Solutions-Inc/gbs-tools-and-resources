# MerusCase — SOP for cli-anything-meruscase

## Overview
MerusCase is a California Workers' Compensation case management SaaS.
API base: https://api.meruscase.com
Login URL: https://meruscase.com/users/login

## Authentication
- REST API: OAuth Bearer token (Authorization: Bearer {token})
- Token source: GCP Secret Manager `qmeprep-meruscase-access-token` (project: adjudica-internal)
- Fallback: env var MERUSCASE_ACCESS_TOKEN, then ~/.meruscase_token
- Browser operations: email/password from GCP secrets meruscase-email / meruscase-password

## API Endpoints
| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | /caseFiles/index | List cases |
| GET | /caseFiles/view/{id} | Get case details |
| POST | /caseFiles/edit/{id} | Update case |
| GET | /parties/index | List parties |
| POST | /parties/add | Add party |
| GET | /activities/index | List activities |
| POST | /activities/add | Add activity |
| GET | /activityTypes/index | Activity type reference |
| GET | /billingCodes/index | Billing code reference |
| GET | /caseLedgersOpen/index | Get ledger entries |
| POST | /caseLedgers/add | Add ledger entry |
| POST | /uploads/add | Upload document (multipart) |
| GET | /uploads/index | List documents |

## Known Quirks
- HTTP 200 responses can contain an `errors` field — always check it
- POST bodies use CakePHP model wrappers: {"Activity": {...}}, {"Party": {...}}, {"CaseLedger": {...}}
- New case creation has NO REST API — must use browser automation
- Rate limit tracked via X-RateLimit-Remaining header
- Time billing stored as duration_minutes = hours × 60

## Browser Automation (Case Creation Only)
1. Launch headless Chromium via Playwright
2. Navigate to https://meruscase.com/users/login
3. Fill email + password fields, click Sign In
4. Wait for networkidle
5. Navigate to /cms#/caseFiles/add?t=1&lpt=0&nr=1&lpa=0
6. Fill: Primary party name (LASTNAME, FIRSTNAME), case type, date opened
7. Submit and extract case ID from redirect URL pattern #/caseFiles/{ID}
