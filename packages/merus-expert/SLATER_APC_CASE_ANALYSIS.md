# Slater APC MerusCase Analysis Report

**Generated:** 2026-02-20
**Account:** abrewsaugh@slaterapc.com
**OAuth App:** Slater & Associates (Client ID: 1439)
**OAuth Token:** `32a6bc768724db25666ee83abfb25408d2fc0e8f`

---

## Executive Summary

**Total Cases:** 3,633
**Open Cases:** 1,390 (38.3%)
**Closed Cases:** 2,243 (61.7%)

---

## Open Cases by Attorney (1,390 Total)

| Attorney | Open Cases | Percentage |
|----------|------------|------------|
| **Alexander Brewsaugh** | 166 | 11.9% |
| **Matthew Plust** | 153 | 11.0% |
| **Jack Pogosian** | 151 | 10.9% |
| **Charles Slater** | 146 | 10.5% |
| **Eren Lezama** | 140 | 10.1% |
| **Scott Draper** | 130 | 9.4% |
| **Johnny Kong** | 108 | 7.8% |
| **Julie Hall** | 102 | 7.3% |
| **Deborah Potter** | 86 | 6.2% |
| **Derek Davis** | 85 | 6.1% |
| **Teresa Bonillas** | 66 | 4.7% |
| **Arturo Suarez** | 3 | 0.2% |
| **Greg Habibi** | 2 | 0.1% |
| **FAI Admin** | 2 | 0.1% |
| **CS Staff** | 1 | 0.1% |
| **Ariel Harman-Holmes** | 1 | 0.1% |
| **Johnny Ejaz** | 1 | 0.1% |
| **[Unassigned]** | 47 | 3.4% |

### 📋 Detailed Case List with Names

**Complete breakdown:** See `OPEN_CASES_BY_ATTORNEY_DETAILED.md` for full list of all 1,390 open cases with case names, IDs, and numbers organized by attorney.

**Sample cases by attorney:**

**Alexander Brewsaugh (166 cases)** — Sample:
- Acjuc, Maria v. CitiStaff Solutions Inc. (Case #4269)
- Adams, Lindy v. Whip Dessert & Cafe (Case #4235)
- Aguila, Juan Jose v. CitiStaff Solutions Inc. (Case #1942)
- Aka Selvin Torres, Selvin Villatoro Torres v. CitiStaff Solutions Inc. (Case #4298)
- Altamirano, Carlos v. CitiStaff Solutions Inc. (Case #4668)
- *...and 161 more*

**Matthew Plust (153 cases)** — Defense cases primarily

**Jack Pogosian (151 cases)** — Workers' compensation defense

**Charles Slater (146 cases)** — Mixed caseload

**Eren Lezama (140 cases)** — Workers' compensation defense

*Full case lists available in detailed breakdown document.*

---

## Case Status Breakdown (All 3,633 Cases)

### Open Cases (1,390 total)
- **Open:** 941 cases
- **Other:** 235 cases
- **Pending:** 214 cases

### Closed Cases (2,243 total)
- **Closed:** 2,242 cases
- **Deceased:** 1 case

---

## MerusCase API Access Instructions

### Authentication

**Token Location:** `/home/vncuser/Desktop/merus-expert/.meruscase_token`

**Current Token:**
```
32a6bc768724db25666ee83abfb25408d2fc0e8f
```

**Token Type:** OAuth 2.0 Bearer Token
**Expiration:** Check with MerusCase (tokens typically don't expire unless revoked)

---

### API Base URL

```
https://api.meruscase.com
```

---

### Authentication Header

All API requests require the `Authorization` header:

```http
Authorization: Bearer 32a6bc768724db25666ee83abfb25408d2fc0e8f
```

---

### Key API Endpoints

#### 1. List All Cases
```bash
curl -H "Authorization: Bearer 32a6bc768724db25666ee83abfb25408d2fc0e8f" \
     https://api.meruscase.com/caseFiles/index
```

**Response Structure:**
```json
{
  "data": {
    "4703360": {
      "0": "1",
      "1": "Case Name",
      "3": 1,
      "4": 163543,  // case_status_id
      "5": [1072646, 1534228],
      ...
    }
  }
}
```

**Field Mappings (Index Endpoint):**
- Field `0`: Case number
- Field `1`: Case title/name
- Field `3`: Case type ID
- Field `4`: Case status ID
- Field `5`: Staff assignments (paralegal, secretary IDs)

#### 2. Get Single Case Details
```bash
curl -H "Authorization: Bearer 32a6bc768724db25666ee83abfb25408d2fc0e8f" \
     https://api.meruscase.com/caseFiles/view/4703360
```

**Response Structure:**
```json
{
  "CaseFile": {
    "id": 4703360,
    "name": "Sample, John v. Sample Employer",
    "case_status_id": 163543,
    "attorney_handling": 600353,
    "attorney_responsible": 0,
    "paralegal_handling": 1072646,
    "case_type_id": 1,
    "date_opened": "2023-05-23",
    ...
  }
}
```

#### 3. List All Users (Attorneys/Staff)
```bash
curl -H "Authorization: Bearer 32a6bc768724db25666ee83abfb25408d2fc0e8f" \
     https://api.meruscase.com/users/index
```

**Response Structure:**
```json
{
  "data": {
    "600353": {
      "id": 600353,
      "1": "Julie",
      "2": "Hall",
      "email": "jhall@slaterapc.com",
      ...
    }
  }
}
```

**Field Mappings:**
- Field `1`: First name
- Field `2`: Last name
- `email`: Email address

#### 4. Get Case Statuses
```bash
curl -H "Authorization: Bearer 32a6bc768724db25666ee83abfb25408d2fc0e8f" \
     https://api.meruscase.com/caseStatuses/index
```

**Response:**
```json
{
  "data": {
    "163543": {
      "id": 163543,
      "status": "Open",
      "slug": "open",
      "is_billable": true
    },
    "163546": {
      "id": 163546,
      "status": "Closed",
      "slug": "closed",
      "is_billable": false
    }
  }
}
```

**Status Slugs:**
- `"open"` = Open cases (IDs: 163543, 163544, 163549, 163552)
- `"closed"` = Closed cases (IDs: 163545, 163546, 163547, 163548, 163550, 163551, 163553)
- `"archived"` = Archived (ID: 163554)

#### 5. Other Useful Endpoints
```bash
# Case types
GET https://api.meruscase.com/caseTypes/index

# Billing codes
GET https://api.meruscase.com/billingCodes/index

# Activity types
GET https://api.meruscase.com/activityTypes/index

# Tasks
GET https://api.meruscase.com/tasks/index?limit=100
```

---

### Python Example

```python
import httpx
import asyncio

async def get_open_cases():
    token = '32a6bc768724db25666ee83abfb25408d2fc0e8f'

    async with httpx.AsyncClient(
        headers={'Authorization': f'Bearer {token}'},
        timeout=30.0
    ) as client:
        # Get all cases
        resp = await client.get('https://api.meruscase.com/caseFiles/index')
        cases = resp.json().get('data', {})

        # Filter to open cases
        open_status_ids = {163543, 163544, 163549, 163552}
        open_cases = [
            (case_id, case_data)
            for case_id, case_data in cases.items()
            if case_data.get('4') in open_status_ids
        ]

        print(f"Found {len(open_cases)} open cases")

        # Get details for first open case
        if open_cases:
            case_id, _ = open_cases[0]
            detail_resp = await client.get(
                f'https://api.meruscase.com/caseFiles/view/{case_id}'
            )
            case_detail = detail_resp.json().get('CaseFile', {})
            print(f"\nSample case: {case_detail.get('name')}")
            print(f"Attorney: {case_detail.get('attorney_handling')}")

asyncio.run(get_open_cases())
```

---

### JavaScript/Node.js Example

```javascript
const fetch = require('node-fetch');

const token = '32a6bc768724db25666ee83abfb25408d2fc0e8f';
const headers = {
  'Authorization': `Bearer ${token}`,
  'Accept': 'application/json'
};

async function getOpenCases() {
  // Get all cases
  const response = await fetch('https://api.meruscase.com/caseFiles/index', { headers });
  const data = await response.json();

  // Filter to open cases (status IDs: 163543, 163544, 163549, 163552)
  const openStatusIds = new Set([163543, 163544, 163549, 163552]);
  const openCases = Object.entries(data.data).filter(
    ([id, caseData]) => openStatusIds.has(caseData['4'])
  );

  console.log(`Found ${openCases.length} open cases`);
}

getOpenCases();
```

---

### cURL Examples

**Get all cases:**
```bash
curl -H "Authorization: Bearer 32a6bc768724db25666ee83abfb25408d2fc0e8f" \
     https://api.meruscase.com/caseFiles/index | jq '.data | length'
```

**Get open cases count:**
```bash
curl -H "Authorization: Bearer 32a6bc768724db25666ee83abfb25408d2fc0e8f" \
     https://api.meruscase.com/caseFiles/index | \
  jq '[.data[] | select(.["4"] == 163543 or .["4"] == 163544 or .["4"] == 163549 or .["4"] == 163552)] | length'
```

**Get case details:**
```bash
curl -H "Authorization: Bearer 32a6bc768724db25666ee83abfb25408d2fc0e8f" \
     https://api.meruscase.com/caseFiles/view/4703360 | jq '.CaseFile'
```

---

## OAuth Token Renewal

If your token expires or you need a new one for a different account:

### Method 1: Manual OAuth Flow
```bash
cd /home/vncuser/Desktop/merus-expert
python3 manual_oauth.py
```

This will:
1. Open a browser
2. Navigate to MerusCase OAuth page
3. Wait for you to log in and authorize
4. Automatically capture and save the token

### Method 2: Environment Variables

Update `.env` file:
```bash
MERUSCASE_EMAIL=your_email@slaterapc.com
MERUSCASE_API_CLIENT_ID=1439  # Slater & Associates app
MERUSCASE_API_CLIENT_SECRET=your_client_secret  # If available
```

Then run:
```bash
python3 oauth_browser_flow.py
```

---

## Rate Limits & Best Practices

- **No documented rate limits** from MerusCase API (as of 2026-02-20)
- For bulk operations (>100 requests), add delays: `await asyncio.sleep(0.1)` between requests
- Use the index endpoints first, then fetch details only for needed cases
- Cache reference data (users, statuses, case types) - they rarely change

---

## Security Notes

⚠️ **Keep your OAuth token secure:**
- Never commit `.meruscase_token` to git
- Token is stored in: `/home/vncuser/Desktop/merus-expert/.meruscase_token`
- Token provides full API access to your MerusCase account
- Rotate token if compromised

---

## Related Documents

- **Detailed Case Breakdown:** `OPEN_CASES_BY_ATTORNEY_DETAILED.md` - Full list of all 1,390 open cases with names, organized by attorney
- **Analysis Tool:** `/home/vncuser/Desktop/merus-expert/`
- **OAuth Token:** `.meruscase_token`

---

## Support & Documentation

- **MerusCase Support:** support@meruscase.com
- **API Documentation:** Contact MerusCase for official API docs
- **Glass Box Solutions:** https://glassboxsolutions.com

---

@Generated by Glass Box Solutions, Inc. MerusExpert Agent
