# MerusAgent - Implementation Summary

**Created:** 2026-01-28
**Status:** ✅ Ready to Use

---

## What Was Created

A complete **MerusAgent** system for pulling information from MerusCase and pushing billing entries via API.

### Files Created

| File | Purpose | Lines |
|------|---------|-------|
| `merus_agent.py` | Main agent implementation | 600+ |
| `MERUS_AGENT_GUIDE.md` | Complete documentation | 700+ |
| `example_merus_agent.py` | Comprehensive examples | 400+ |
| `test_merus_agent.py` | Test suite | 150+ |

### Updated Files

| File | Changes |
|------|---------|
| `CLAUDE.md` | Added MerusAgent section, updated commands |

---

## Quick Start

### 1. Test Read Operations

```bash
python test_merus_agent.py
```

This tests:
- ✓ Find case by name
- ✓ Get case details
- ✓ Get billing entries
- ✓ Get activities
- ✓ Get reference data

### 2. Test Write Operations (Creates Real Entries)

```bash
python test_merus_agent.py --write-test
```

⚠️ This creates actual billing entries in MerusCase!

### 3. Run All Examples

```bash
python example_merus_agent.py
```

---

## Basic Usage

### Pull Information

```python
from merus_agent import MerusAgent

async with MerusAgent() as agent:
    # Find case
    case = await agent.find_case("Smith")
    print(f"Found: {case['primary_party_name']}")

    # Get billing
    billing = await agent.get_case_billing(int(case['id']))
    print(f"Entries: {len(billing['data'])}")

    # Get activities
    activities = await agent.get_case_activities(int(case['id']))
    print(f"Activities: {len(activities)}")
```

### Push Billing Entries

```python
from merus_agent import MerusAgent

async with MerusAgent() as agent:
    # Bill time (natural language)
    result = await agent.bill_time(
        case_search="Smith",        # Case name or file number
        hours=0.2,                  # 0.2 hours = 12 minutes
        description="Review medical records"
    )
    print(f"Billed to case: {result['case_name']}")

    # Add cost/fee
    result = await agent.add_cost(
        case_search="Smith",
        amount=25.00,
        description="WCAB Filing Fee"
    )
    print(f"Added cost to case: {result['case_name']}")
```

### Quick Functions

```python
from merus_agent import quick_bill_time, quick_add_cost

# One-liners without instantiating agent
await quick_bill_time("Smith", 0.2, "Review records")
await quick_add_cost("Smith", 25.00, "Filing fee")
```

---

## Key Features

### ✅ Pull Operations (READ)

| Method | Example |
|--------|---------|
| Find case | `agent.find_case("Smith")` |
| Get case details | `agent.get_case_details(123456)` |
| Get billing | `agent.get_case_billing(123456)` |
| Get activities | `agent.get_case_activities(123456)` |
| Get parties | `agent.get_case_parties(123456)` |
| List cases | `agent.list_all_cases(case_status="Active")` |
| Billing summary | `agent.get_billing_summary("Smith")` |

### ✅ Push Operations (CREATE)

| Method | Example |
|--------|---------|
| Bill time | `agent.bill_time("Smith", 0.2, "Work description")` |
| Add cost | `agent.add_cost("Smith", 25.00, "Filing fee")` |
| Add note | `agent.add_note("Smith", "Subject", "Description")` |
| Batch bill | `agent.bulk_bill_time([{...}, {...}])` |

### ✅ Smart Features

- **Natural Language Search**: Find cases by name or file number
- **Reference Data Caching**: Billing codes cached for 1 hour
- **Error Handling**: CaseNotFoundError, BillingError
- **Batch Operations**: Bill multiple cases in one call
- **Type Safety**: Full Pydantic validation

---

## Architecture

```
MerusAgent (High-level intelligence)
    ↓
MerusCaseAPIClient (Low-level API)
    ↓
MerusCase REST API
```

### What Each Layer Does

| Layer | Responsibility |
|-------|----------------|
| **MerusAgent** | Natural language search, caching, error handling, convenience methods |
| **MerusCaseAPIClient** | Raw API calls, authentication, request/response handling |
| **REST API** | MerusCase backend |

---

## Common Use Cases

### 1. Daily Billing Routine

```python
async with MerusAgent() as agent:
    entries = [
        {"case_search": "Smith", "hours": 0.5, "description": "Review records"},
        {"case_search": "Jones", "hours": 1.0, "description": "MSC prep"},
        {"case_search": "Davis", "hours": 0.2, "description": "Client call"},
    ]

    results = await agent.bulk_bill_time(entries)
    print(f"Billed {len(results)} entries")
```

### 2. Case Status Report

```python
async with MerusAgent() as agent:
    case = await agent.find_case("Smith")
    billing = await agent.get_case_billing(int(case['id']))
    activities = await agent.get_case_activities(int(case['id']))

    print(f"Case: {case['primary_party_name']}")
    print(f"Billing: ${sum(float(e['amount']) for e in billing['data'].values()):.2f}")
    print(f"Activities: {len(activities)}")
```

### 3. Add Multiple Costs

```python
async with MerusAgent() as agent:
    costs = [
        (25.00, "WCAB Filing Fee"),
        (15.00, "Medical record copies"),
        (10.00, "Postage"),
    ]

    for amount, description in costs:
        await agent.add_cost("Smith", amount, description)
```

---

## Integration Points

### For Glassy Voice Agent

```python
async def process_voice_command(utterance: str):
    """Process 'bill .2 on Smith' type commands"""
    async with MerusAgent() as agent:
        if "bill" in utterance:
            # Extract: hours, case, description
            result = await agent.bill_time(case_search, hours, description)
            return f"Billed {hours} hours to {result['case_name']}"

        elif "fee" in utterance or "cost" in utterance:
            # Extract: amount, case, description
            result = await agent.add_cost(case_search, amount, description)
            return f"Added ${amount} to {result['case_name']}"
```

### For Automated Workflows

```python
# n8n webhook → MerusAgent
async def handle_webhook(data: dict):
    async with MerusAgent() as agent:
        case_name = data['case_name']
        hours = data['hours']
        description = data['description']

        result = await agent.bill_time(case_name, hours, description)
        return {"success": True, "activity_id": result['activity_id']}
```

---

## Error Handling

### Exception Types

```python
from merus_agent import MerusAgentError, CaseNotFoundError, BillingError

try:
    result = await agent.bill_time("Smith", 0.2, "Work")
except CaseNotFoundError:
    print("Case not found - check spelling")
except BillingError as e:
    print(f"Billing failed: {e}")
except MerusAgentError as e:
    print(f"Agent error: {e}")
```

---

## Testing

### Read-Only Tests (Safe)

```bash
python test_merus_agent.py
```

Tests all pull operations without creating any data.

### Write Tests (Creates Real Entries)

```bash
python test_merus_agent.py --write-test
```

⚠️ Creates actual billing entries - you'll need to delete them manually.

### All Examples

```bash
python example_merus_agent.py
```

Demonstrates all features with detailed output.

---

## Configuration

### Token File

By default, reads OAuth token from `.meruscase_token`:

```python
# Default
agent = MerusAgent()

# Custom file
agent = MerusAgent(token_file="/path/to/token")

# Direct token
agent = MerusAgent(access_token="your_token")
```

### Cache Duration

```python
# Default: 1 hour
agent = MerusAgent()

# Custom: 30 minutes
agent = MerusAgent(cache_ttl_seconds=1800)

# No cache
agent = MerusAgent(cache_ttl_seconds=0)
```

---

## Documentation

| Document | Purpose |
|----------|---------|
| `MERUS_AGENT_GUIDE.md` | **Complete guide (READ THIS FIRST)** |
| `example_merus_agent.py` | Code examples |
| `test_merus_agent.py` | Test suite |
| `MERUSCASE_API_DEVELOPER_GUIDE.md` | Full API reference |
| `MERUSCASE_API_REFERENCE.md` | Quick API reference |

---

## What's Already Implemented

✅ **API Client** (`meruscase_api/client.py`)
✅ **Data Models** (`meruscase_api/models.py`)
✅ **OAuth Authentication**
✅ **Billing API** (POST /activities/add, POST /caseLedgers/add)
✅ **Document API** (GET /uploads/index, GET /documents/download)
✅ **Case Management API** (GET /caseFiles/*)
✅ **Contact/Party API**
✅ **Reference Data API** (billing codes, activity types)

✅ **MerusAgent** (High-level wrapper)
✅ **Natural Language Search**
✅ **Reference Data Caching**
✅ **Batch Operations**
✅ **Error Handling**
✅ **Type Safety**

---

## Next Steps

### 1. Try It Out

```bash
# Test read operations
python test_merus_agent.py

# Test write operations (careful - creates real entries)
python test_merus_agent.py --write-test
```

### 2. Read the Guide

Open `MERUS_AGENT_GUIDE.md` for:
- Complete API reference
- All methods documented
- Usage examples
- Integration patterns
- Troubleshooting

### 3. Integrate with Your System

```python
# In your code
from merus_agent import MerusAgent

async def your_function():
    async with MerusAgent() as agent:
        # Your logic here
        pass
```

---

## Support

### If Something Doesn't Work

1. **Check token**: Verify `.meruscase_token` exists and is valid
2. **Test API directly**: Run `python test_merus_agent.py`
3. **Check logs**: Enable DEBUG logging to see API calls
4. **Review docs**: See `MERUS_AGENT_GUIDE.md` for troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| Token expired | Run `python complete_oauth.py` to refresh |
| Case not found | Try with file number instead of name |
| Rate limited | Wait for rate limit to reset |
| Import error | Check `meruscase_api/` directory exists |

---

## Summary

You now have a **complete MerusAgent** that can:

1. ✅ **Pull information** from MerusCase (cases, billing, activities, parties)
2. ✅ **Push billing entries** to MerusCase (time-based and direct costs)
3. ✅ **Natural language search** (find cases by name or file number)
4. ✅ **Smart caching** (reference data cached to reduce API calls)
5. ✅ **Batch operations** (bill multiple cases at once)
6. ✅ **Error handling** (specific exceptions for different error types)

The agent wraps the existing MerusCase API client with intelligent features and a clean interface.

**Ready to use!** Start with `python test_merus_agent.py` to verify everything works.

---

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
