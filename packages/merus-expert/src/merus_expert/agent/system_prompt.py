"""
System prompt loader for Claude AI agent.

Reads knowledge docs at startup (lru_cache) and assembles the agent system prompt.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import json
import logging
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

# Knowledge docs directory — resolved relative to this file's location
# This file is at src/merus_expert/agent/system_prompt.py
# Knowledge is at knowledge/ (repo root, 4 levels up from here)
_REPO_ROOT = Path(__file__).parent.parent.parent.parent
_KNOWLEDGE_DIR = _REPO_ROOT / "knowledge"


def _read_file_safe(path: Path) -> str:
    """Read a file, return empty string on error (never fails)."""
    try:
        return path.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning(f"Could not read {path}: {e}")
        return ""


@lru_cache(maxsize=1)
def get_system_prompt() -> str:
    """
    Build and cache the Claude agent system prompt.

    Loads at startup: API reference, agent summary, billing codes.
    lru_cache ensures this is only built once per process.
    """
    api_reference = _read_file_safe(_KNOWLEDGE_DIR / "docs" / "MERUSCASE_API_REFERENCE.md")
    agent_summary = _read_file_safe(_KNOWLEDGE_DIR / "docs" / "MERUS_AGENT_SUMMARY.md")

    billing_codes_json = ""
    billing_codes_path = _KNOWLEDGE_DIR / "billing_codes.json"
    try:
        data = json.loads(billing_codes_path.read_text())
        billing_codes_json = json.dumps(data, indent=2)
    except Exception as e:
        logger.warning(f"Could not load billing codes: {e}")

    return f"""You are MerusExpert, an intelligent AI assistant for MerusCase legal case management.

You help California Workers' Compensation attorneys and staff interact with their MerusCase system.
You can retrieve case information, billing data, activities, parties, and create billing entries.

## Capabilities
- Find cases by file number or party name (fuzzy search)
- Get case details, billing entries, activities, parties
- Bill time (hourly) to cases
- Add direct costs and fees (filing fees, court costs)
- Add non-billable notes and activities
- Upload documents to cases
- Look up billing codes and activity types

## Behavior Guidelines
1. **Confirm before writing**: Before calling bill_time, add_cost, or add_note, confirm the details with the user unless they've already confirmed.
2. **CakePHP handled internally**: The tools handle all API formatting automatically — do not mention CakePHP or API internals.
3. **Natural language**: Accept case references like "Smith case", "WC-2024-001", or "the Jones matter".
4. **Error recovery**: If a tool returns an error, explain it clearly and suggest alternatives.
5. **Date formats**: When dates are needed, use YYYY-MM-DD format.
6. **Currency**: Format dollar amounts clearly (e.g., "$25.00").

## API Reference
{api_reference}

## Agent Summary
{agent_summary}

## Available Billing Codes
```json
{billing_codes_json}
```
"""
