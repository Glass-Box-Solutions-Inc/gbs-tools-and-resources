# MerusAgent - Complete Guide

**Intelligent MerusCase API Agent for pulling information and pushing billing entries.**

---

## Quick Start

### Installation

No additional dependencies needed beyond what's in `requirements.txt`:

```bash
pip install -r requirements.txt
```

### Basic Usage

```python
import asyncio
from merus_agent import MerusAgent

async def main():
    # Initialize agent (uses .meruscase_token by default)
    async with MerusAgent() as agent:
        # Pull information
        case = await agent.find_case("Smith")
        billing = await agent.get_case_billing(case["id"])

        # Push billing entries
        await agent.bill_time("Smith", 0.2, "Review medical records")
        await agent.add_cost("Smith", 25.00, "WCAB Filing Fee")

asyncio.run(main())
```

---

## Features

### ✅ Pull Operations (READ)

| Method | Description |
|--------|-------------|
| `find_case(search)` | Find case by file number or party name |
| `get_case_details(case_id)` | Get complete case information |
| `get_case_billing(case_id)` | Get billing/ledger entries |
| `get_case_activities(case_id)` | Get activities/notes |
| `get_case_parties(case_id)` | Get parties/contacts |
| `list_all_cases(...)` | List cases with filters |
| `get_billing_summary(case_search)` | Get billing totals |

### ✅ Push Operations (CREATE)

| Method | Description |
|--------|-------------|
| `bill_time(case_search, hours, description)` | Bill time to a case |
| `add_cost(case_search, amount, description)` | Add direct fee/cost |
| `add_note(case_search, subject, description)` | Add non-billable note |
| `bulk_bill_time(entries)` | Batch bill multiple cases |

### ✅ Smart Features

- **Natural Language Search**: Find cases by name or file number
- **Reference Data Caching**: Billing codes and activity types cached for 1 hour
- **Error Handling**: Specific exceptions (CaseNotFoundError, BillingError)
- **Automatic Retry**: Built-in retry logic for transient failures
- **Type Safety**: Full Pydantic validation

---

## Pull Operations

### 1. Find Case

Find a case by file number or party name (fuzzy search):

```python
# By party name
case = await agent.find_case("Smith")

# By file number
case = await agent.find_case("WC-2024-001")

# Case not found raises CaseNotFoundError
try:
    case = await agent.find_case("NonExistent")
except CaseNotFoundError as e:
    print(f"Case not found: {e}")
```

**Returns:**
```python
{
    "id": "56171871",
    "file_number": "WC-2024-001",
    "primary_party_name": "John Smith",
    "case_type_id": "2",
    # ... other case fields
}
```

### 2. Get Case Details

Get complete case information:

```python
details = await agent.get_case_details(case_id)
```

### 3. Get Billing Information

Get ledger entries for a case:

```python
# All billing entries
billing = await agent.get_case_billing(case_id)

# Filter by date range
billing = await agent.get_case_billing(
    case_id,
    date_gte="2024-01-01",
    date_lte="2024-12-31"
)
```

**Returns:**
```python
{
    "data": {
        "12345": {
            "id": "12345",
            "amount": "500.00",
            "description": "Initial consultation",
            "date": "2024-01-15",
            # ...
        }
    }
}
```

### 4. Get Activities

Get activities/notes for a case:

```python
activities = await agent.get_case_activities(case_id, limit=50)

# Returns list of activity dicts
for activity in activities:
    print(f"{activity['date']}: {activity['subject']}")
```

### 5. Get Parties

Get parties/contacts for a case:

```python
parties = await agent.get_case_parties(case_id)
```

### 6. List All Cases

List cases with optional filters:

```python
# All active cases
cases = await agent.list_all_cases(case_status="Active", limit=100)

# Workers' comp cases only
wc_cases = await agent.list_all_cases(case_type="Workers Compensation")

# Returns list of case dicts
for case in cases:
    print(f"{case['id']}: {case['primary_party_name']}")
```

### 7. Billing Summary

Get billing summary with totals:

```python
summary = await agent.get_billing_summary("Smith")

print(f"Total: ${summary['total_amount']:.2f}")
print(f"Entries: {summary['total_entries']}")

# Filter by date range
summary = await agent.get_billing_summary(
    "Smith",
    start_date="2024-01-01",
    end_date="2024-12-31"
)
```

---

## Push Operations

### 1. Bill Time (Time-Based Billing)

Bill time to a case using natural language:

```python
result = await agent.bill_time(
    case_search="Smith",          # File number or party name
    hours=0.2,                     # 0.2 hours = 12 minutes
    description="Review medical records and QME report"
)

# Optional parameters
result = await agent.bill_time(
    case_search="Smith",
    hours=1.5,
    description="Draft demand letter and prepare settlement analysis",
    subject="Settlement prep",    # Defaults to first 50 chars of description
    activity_type_id=3,           # Activity type (optional)
    billing_code_id=10,           # Billing code (optional)
)
```

**Returns:**
```python
{
    "success": True,
    "activity_id": "918183874",
    "case_id": "56171871",
    "case_name": "John Smith",
    "hours": 0.2,
    "minutes": 12,
    "description": "Review medical records and QME report"
}
```

**Common Time Increments:**
```python
0.1 hours = 6 minutes
0.2 hours = 12 minutes
0.25 hours = 15 minutes
0.5 hours = 30 minutes
1.0 hours = 60 minutes
```

### 2. Add Cost (Direct Fees/Costs)

Add filing fees, court costs, expenses:

```python
result = await agent.add_cost(
    case_search="Smith",
    amount=25.00,
    description="WCAB Filing Fee"
)

# Specify ledger type
result = await agent.add_cost(
    case_search="Smith",
    amount=350.00,
    description="Expert witness fee",
    ledger_type="expense"  # Options: "fee", "cost", "expense"
)
```

**Returns:**
```python
{
    "success": True,
    "ledger_id": 110681047,
    "case_id": "56171871",
    "case_name": "John Smith",
    "amount": 25.00,
    "description": "WCAB Filing Fee",
    "type": "cost"
}
```

### 3. Add Note (Non-Billable)

Add notes or activities without billing:

```python
result = await agent.add_note(
    case_search="Smith",
    subject="Client called",
    description="Discussed upcoming MSC hearing and settlement options"
)
```

### 4. Batch Billing

Bill time to multiple cases in one operation:

```python
entries = [
    {"case_search": "Smith", "hours": 0.2, "description": "Review records"},
    {"case_search": "Jones", "hours": 0.5, "description": "Draft demand"},
    {"case_search": "Davis", "hours": 1.0, "description": "Court hearing"},
]

results = await agent.bulk_bill_time(entries)

# Check results
successful = sum(1 for r in results if r.get("success"))
print(f"Success: {successful}/{len(entries)}")
```

---

## Reference Data (Cached)

Reference data is cached for 1 hour to reduce API calls:

### Billing Codes

```python
codes = await agent.get_billing_codes()

# Returns dict keyed by ID
for code_id, code_data in codes.items():
    print(f"{code_id}: {code_data['name']}")
```

### Activity Types

```python
types = await agent.get_activity_types()

for type_id, type_data in types.items():
    print(f"{type_id}: {type_data['name']}")
```

---

## Convenience Functions

Quick functions for one-off operations:

### Quick Bill Time

```python
from merus_agent import quick_bill_time

result = await quick_bill_time("Smith", 0.2, "Quick review")
```

### Quick Add Cost

```python
from merus_agent import quick_add_cost

result = await quick_add_cost("Smith", 25.00, "Filing fee")
```

---

## Error Handling

### Exception Types

| Exception | When Raised |
|-----------|-------------|
| `MerusAgentError` | Base exception for all errors |
| `CaseNotFoundError` | Case cannot be found by search |
| `BillingError` | Billing entry creation fails |

### Example

```python
from merus_agent import MerusAgent, CaseNotFoundError, BillingError

async with MerusAgent() as agent:
    try:
        result = await agent.bill_time("Smith", 0.2, "Work description")
    except CaseNotFoundError:
        print("Case not found - check spelling or file number")
    except BillingError as e:
        print(f"Billing failed: {e}")
    except MerusAgentError as e:
        print(f"General error: {e}")
```

---

## Configuration

### Token Source

By default, MerusAgent reads the OAuth token from `.meruscase_token`:

```python
# Default - reads from .meruscase_token
agent = MerusAgent()

# Custom token file
agent = MerusAgent(token_file="/path/to/token")

# Direct token
agent = MerusAgent(access_token="your_token_here")
```

### Cache Duration

Reference data cache duration can be configured:

```python
# Default: 1 hour (3600 seconds)
agent = MerusAgent()

# Custom: 30 minutes
agent = MerusAgent(cache_ttl_seconds=1800)

# No cache: 0 seconds
agent = MerusAgent(cache_ttl_seconds=0)
```

---

## Examples

### Example 1: Daily Billing Routine

```python
async def daily_billing():
    """Bill time to multiple cases for the day's work"""
    async with MerusAgent() as agent:
        entries = [
            {"case_search": "Smith", "hours": 0.5, "description": "Review medical records"},
            {"case_search": "Smith", "hours": 0.3, "description": "Call with adjuster"},
            {"case_search": "Jones", "hours": 1.0, "description": "MSC hearing prep"},
            {"case_search": "Davis", "hours": 0.2, "description": "Email to client"},
        ]

        results = await agent.bulk_bill_time(entries)

        total_hours = sum(e["hours"] for e in entries)
        successful = sum(1 for r in results if r.get("success"))

        print(f"Billed {total_hours} hours across {successful} entries")
```

### Example 2: Case Status Report

```python
async def case_status_report(case_name: str):
    """Get comprehensive case status"""
    async with MerusAgent() as agent:
        # Find case
        case = await agent.find_case(case_name)
        case_id = int(case["id"])

        # Get all information
        details = await agent.get_case_details(case_id)
        billing = await agent.get_case_billing(case_id)
        activities = await agent.get_case_activities(case_id, limit=10)
        summary = await agent.get_billing_summary(case_name)

        print(f"Case: {case['primary_party_name']}")
        print(f"File Number: {case['file_number']}")
        print(f"Total Billed: ${summary['total_amount']:.2f}")
        print(f"Recent Activities: {len(activities)}")
```

### Example 3: Add Multiple Costs

```python
async def add_case_costs(case_name: str):
    """Add multiple costs to a case"""
    async with MerusAgent() as agent:
        costs = [
            (25.00, "WCAB Filing Fee"),
            (15.00, "Medical record copies"),
            (10.00, "Postage and mailing"),
        ]

        for amount, description in costs:
            result = await agent.add_cost(case_name, amount, description)
            print(f"Added ${amount:.2f}: {description}")
```

---

## Integration with Glassy

To integrate MerusAgent with Glassy voice agent:

```python
from merus_agent import MerusAgent

async def glassy_bill_time(utterance: str):
    """
    Process natural language billing from Glassy.

    Examples:
        "bill .2 on Smith case"
        "add 25 dollar filing fee to Jones"
    """
    # Parse utterance (simplified)
    if "bill" in utterance:
        # Extract: hours, case, description
        hours = extract_hours(utterance)
        case_name = extract_case_name(utterance)
        description = extract_description(utterance)

        async with MerusAgent() as agent:
            result = await agent.bill_time(case_name, hours, description)
            return f"Billed {hours} hours to {result['case_name']}"

    elif "fee" in utterance or "cost" in utterance:
        # Extract: amount, case, description
        amount = extract_amount(utterance)
        case_name = extract_case_name(utterance)
        description = extract_description(utterance)

        async with MerusAgent() as agent:
            result = await agent.add_cost(case_name, amount, description)
            return f"Added ${amount} cost to {result['case_name']}"
```

---

## Testing

Run the comprehensive example script:

```bash
python example_merus_agent.py
```

This demonstrates:
- Pull operations (READ)
- Push operations (CREATE)
- Batch operations
- Reference data caching
- Billing summaries
- Convenience functions
- Error handling

---

## Underlying API Client

MerusAgent wraps `MerusCaseAPIClient` from `meruscase_api/client.py`. For lower-level API access:

```python
from meruscase_api.client import MerusCaseAPIClient
from meruscase_api.models import Activity, LedgerEntry

async with MerusCaseAPIClient(access_token="token") as client:
    # Direct API access
    response = await client.list_cases(limit=100)

    # Create activity with full control
    activity = Activity(
        case_file_id=123456,
        subject="Subject",
        description="Description",
        billable=True,
        duration_minutes=12
    )
    response = await client.add_activity(activity)
```

---

## Best Practices

### 1. Use Context Manager

Always use `async with` to ensure proper cleanup:

```python
async with MerusAgent() as agent:
    # Your operations here
    pass
# Connection automatically closed
```

### 2. Handle Errors Gracefully

Always handle specific exceptions:

```python
try:
    result = await agent.bill_time("Smith", 0.2, "Work")
except CaseNotFoundError:
    # Inform user to check case name
    pass
except BillingError as e:
    # Log error, retry later
    pass
```

### 3. Cache Reference Data

Let the agent cache billing codes and activity types - don't fetch repeatedly.

### 4. Batch Operations

For multiple entries, use `bulk_bill_time()` instead of individual calls.

### 5. Descriptive Entries

Always provide clear descriptions for billing entries:

```python
# Good
"Review QME report (Dr. Smith 12/15/2024) and medical records from Kaiser"

# Bad
"Review stuff"
```

---

## Troubleshooting

### Token Expired

```
Error: Authentication failed - invalid or expired token
```

**Solution:** Refresh your OAuth token:
```bash
python complete_oauth.py
```

### Case Not Found

```
CaseNotFoundError: No case found matching 'Smith'
```

**Solution:** Try with file number instead:
```python
case = await agent.find_case("WC-2024-001")
```

### Rate Limited

```
APIResponse(success=False, error='Rate limit exceeded', error_code=429)
```

**Solution:** Wait for rate limit to reset (check response.rate_limit_reset).

---

## API Documentation

For complete MerusCase API documentation, see:
- `MERUSCASE_API_REFERENCE.md` - Quick reference
- `MERUSCASE_API_DEVELOPER_GUIDE.md` - Complete guide

---

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
