"""
MerusCase tool definitions for Claude AI agent.

13 tools matching MerusAgent methods, in Anthropic tool-use format.
dispatch_tool() routes tool calls and handles all exceptions safely.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from typing import Any, Dict
from merus_expert.core.agent import MerusAgent

# All 13 tool definitions in Anthropic format
TOOLS = [
    {
        "name": "find_case",
        "description": "Find a MerusCase case by file number or party name (fuzzy search). Returns the first matching case.",
        "input_schema": {
            "type": "object",
            "properties": {
                "search": {
                    "type": "string",
                    "description": "Case file number or party name to search for"
                },
                "limit": {
                    "type": "integer",
                    "description": "Max cases to search through (default: 50)",
                    "default": 50
                }
            },
            "required": ["search"]
        }
    },
    {
        "name": "get_case_details",
        "description": "Get full details for a case by its numeric ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "case_id": {
                    "type": "integer",
                    "description": "MerusCase case file ID"
                }
            },
            "required": ["case_id"]
        }
    },
    {
        "name": "get_case_billing",
        "description": "Get billing/ledger entries for a case. Optionally filter by date range.",
        "input_schema": {
            "type": "object",
            "properties": {
                "case_id": {"type": "integer", "description": "MerusCase case file ID"},
                "date_gte": {"type": "string", "description": "Start date filter (YYYY-MM-DD)"},
                "date_lte": {"type": "string", "description": "End date filter (YYYY-MM-DD)"}
            },
            "required": ["case_id"]
        }
    },
    {
        "name": "get_case_activities",
        "description": "Get activities and notes for a case.",
        "input_schema": {
            "type": "object",
            "properties": {
                "case_id": {"type": "integer", "description": "MerusCase case file ID"},
                "limit": {"type": "integer", "description": "Max results (default: 100)", "default": 100}
            },
            "required": ["case_id"]
        }
    },
    {
        "name": "get_case_parties",
        "description": "Get all parties and contacts associated with a case.",
        "input_schema": {
            "type": "object",
            "properties": {
                "case_id": {"type": "integer", "description": "MerusCase case file ID"}
            },
            "required": ["case_id"]
        }
    },
    {
        "name": "list_cases",
        "description": "List all cases with optional filters for status and type.",
        "input_schema": {
            "type": "object",
            "properties": {
                "case_status": {"type": "string", "description": "Filter by status (e.g., 'Active', 'Closed')"},
                "case_type": {"type": "string", "description": "Filter by type (e.g., 'Workers Compensation')"},
                "limit": {"type": "integer", "description": "Max results (default: 100)", "default": 100}
            }
        }
    },
    {
        "name": "get_billing_summary",
        "description": "Get a billing summary with totals for a case, found by name or file number.",
        "input_schema": {
            "type": "object",
            "properties": {
                "case_search": {"type": "string", "description": "Case file number or party name"},
                "start_date": {"type": "string", "description": "Start date (YYYY-MM-DD)"},
                "end_date": {"type": "string", "description": "End date (YYYY-MM-DD)"}
            },
            "required": ["case_search"]
        }
    },
    {
        "name": "bill_time",
        "description": "Bill time to a case. Creates a billable activity entry. Use for attorney time entries.",
        "input_schema": {
            "type": "object",
            "properties": {
                "case_search": {"type": "string", "description": "Case file number or party name"},
                "hours": {"type": "number", "description": "Time in hours (e.g., 0.2 for 12 minutes)"},
                "description": {"type": "string", "description": "Detailed description of work performed"},
                "subject": {"type": "string", "description": "Short subject line (optional)"},
                "activity_type_id": {"type": "integer", "description": "Activity type ID (optional)"},
                "billing_code_id": {"type": "integer", "description": "Billing code ID (optional)"}
            },
            "required": ["case_search", "hours", "description"]
        }
    },
    {
        "name": "add_cost",
        "description": "Add a direct cost or fee to a case. Use for filing fees, court costs, expenses — NOT for time billing.",
        "input_schema": {
            "type": "object",
            "properties": {
                "case_search": {"type": "string", "description": "Case file number or party name"},
                "amount": {"type": "number", "description": "Dollar amount (e.g., 25.00)"},
                "description": {"type": "string", "description": "Description of the cost"},
                "ledger_type": {"type": "string", "description": "Type: 'fee', 'cost', or 'expense' (default: 'cost')", "default": "cost"}
            },
            "required": ["case_search", "amount", "description"]
        }
    },
    {
        "name": "add_note",
        "description": "Add a non-billable note or activity to a case.",
        "input_schema": {
            "type": "object",
            "properties": {
                "case_search": {"type": "string", "description": "Case file number or party name"},
                "subject": {"type": "string", "description": "Note subject"},
                "description": {"type": "string", "description": "Note details (optional)"},
                "activity_type_id": {"type": "integer", "description": "Activity type ID (optional)"}
            },
            "required": ["case_search", "subject"]
        }
    },
    {
        "name": "upload_document",
        "description": "Upload a document file to a case.",
        "input_schema": {
            "type": "object",
            "properties": {
                "case_search": {"type": "string", "description": "Case file number or party name"},
                "file_path": {"type": "string", "description": "Absolute local path to the file"},
                "description": {"type": "string", "description": "Document description (optional)"},
                "folder_id": {"type": "integer", "description": "Target folder ID in case (optional)"}
            },
            "required": ["case_search", "file_path"]
        }
    },
    {
        "name": "get_billing_codes",
        "description": "Get available billing codes (cached). Use to look up billing code IDs.",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "get_activity_types",
        "description": "Get available activity types (cached). Use to look up activity type IDs.",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "create_case",
        "description": "Create a new Workers' Compensation case in MerusCase via browser automation. Use this when a new client needs a case opened. Returns the new case ID and URL. Requires Browserless credentials to be configured.",
        "input_schema": {
            "type": "object",
            "properties": {
                "party_name": {
                    "type": "string",
                    "description": "Primary party (applicant) name. Format: 'LASTNAME, FIRSTNAME' (e.g., 'SMITH, JOHN') or 'FIRSTNAME LASTNAME'."
                },
                "case_type": {
                    "type": "string",
                    "description": "Case type (default: 'Workers Compensation').",
                    "default": "Workers Compensation"
                },
                "date_opened": {
                    "type": "string",
                    "description": "Date case opened / date of injury in MM/DD/YYYY format. Defaults to today if not provided."
                }
            },
            "required": ["party_name"]
        }
    },
    {
        "name": "add_party",
        "description": "Add a party (employer, insurance company, opposing party, witness, expert, etc.) to an existing case. Use this after case creation to associate employers, carriers, and other parties.",
        "input_schema": {
            "type": "object",
            "properties": {
                "case_search": {
                    "type": "string",
                    "description": "Case file number or party name to identify the case."
                },
                "party_type": {
                    "type": "string",
                    "description": "Type of party. Must be one of: 'Employer', 'Insurance Company', 'Opposing Party', 'Witness', 'Expert', 'Client', 'Other'."
                },
                "company_name": {
                    "type": "string",
                    "description": "Company or organization name. Required for Employer and Insurance Company party types."
                },
                "first_name": {
                    "type": "string",
                    "description": "Party first name (for individual parties)."
                },
                "last_name": {
                    "type": "string",
                    "description": "Party last name (for individual parties)."
                },
                "notes": {
                    "type": "string",
                    "description": "Optional notes about this party (e.g., claim number, adjuster name, address)."
                }
            },
            "required": ["case_search", "party_type"]
        }
    },
    {
        "name": "list_documents",
        "description": "List all documents attached to a case. Returns filenames, upload dates, descriptions, and download IDs. Use this to see what documents are already uploaded before uploading duplicates.",
        "input_schema": {
            "type": "object",
            "properties": {
                "case_search": {
                    "type": "string",
                    "description": "Case file number or party name to identify the case."
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of documents to return (default: 100).",
                    "default": 100
                }
            },
            "required": ["case_search"]
        }
    },
]


async def dispatch_tool(agent: MerusAgent, tool_name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """
    Dispatch a tool call to the appropriate MerusAgent method.

    Catches all exceptions and returns {"error": str(e)} — never raises.
    This ensures the tool-use loop always continues cleanly.

    Args:
        agent: MerusAgent instance
        tool_name: Name of tool to invoke
        tool_input: Tool input parameters from Claude

    Returns:
        Dict result — always returns, never raises
    """
    try:
        if tool_name == "find_case":
            return await agent.find_case(
                search=tool_input["search"],
                limit=tool_input.get("limit", 50),
            )
        elif tool_name == "get_case_details":
            return await agent.get_case_details(case_id=int(tool_input["case_id"]))
        elif tool_name == "get_case_billing":
            return await agent.get_case_billing(
                case_id=int(tool_input["case_id"]),
                date_gte=tool_input.get("date_gte"),
                date_lte=tool_input.get("date_lte"),
            )
        elif tool_name == "get_case_activities":
            return await agent.get_case_activities(
                case_id=int(tool_input["case_id"]),
                limit=tool_input.get("limit", 100),
            )
        elif tool_name == "get_case_parties":
            return await agent.get_case_parties(case_id=int(tool_input["case_id"]))
        elif tool_name == "list_cases":
            return await agent.list_all_cases(
                case_status=tool_input.get("case_status"),
                case_type=tool_input.get("case_type"),
                limit=tool_input.get("limit", 100),
            )
        elif tool_name == "get_billing_summary":
            return await agent.get_billing_summary(
                case_search=tool_input["case_search"],
                start_date=tool_input.get("start_date"),
                end_date=tool_input.get("end_date"),
            )
        elif tool_name == "bill_time":
            return await agent.bill_time(
                case_search=tool_input["case_search"],
                hours=float(tool_input["hours"]),
                description=tool_input["description"],
                subject=tool_input.get("subject"),
                activity_type_id=tool_input.get("activity_type_id"),
                billing_code_id=tool_input.get("billing_code_id"),
            )
        elif tool_name == "add_cost":
            return await agent.add_cost(
                case_search=tool_input["case_search"],
                amount=float(tool_input["amount"]),
                description=tool_input["description"],
                ledger_type=tool_input.get("ledger_type", "cost"),
            )
        elif tool_name == "add_note":
            return await agent.add_note(
                case_search=tool_input["case_search"],
                subject=tool_input["subject"],
                description=tool_input.get("description"),
                activity_type_id=tool_input.get("activity_type_id"),
            )
        elif tool_name == "upload_document":
            return await agent.upload_document(
                case_search=tool_input["case_search"],
                file_path=tool_input["file_path"],
                description=tool_input.get("description"),
                folder_id=tool_input.get("folder_id"),
            )
        elif tool_name == "get_billing_codes":
            return await agent.get_billing_codes()
        elif tool_name == "get_activity_types":
            return await agent.get_activity_types()
        elif tool_name == "create_case":
            return await agent.create_case(
                party_name=tool_input["party_name"],
                case_type=tool_input.get("case_type", "Workers Compensation"),
                date_opened=tool_input.get("date_opened"),
            )
        elif tool_name == "add_party":
            return await agent.add_party(
                case_search=tool_input["case_search"],
                party_type=tool_input["party_type"],
                company_name=tool_input.get("company_name"),
                first_name=tool_input.get("first_name"),
                last_name=tool_input.get("last_name"),
                notes=tool_input.get("notes"),
            )
        elif tool_name == "list_documents":
            return await agent.list_documents(
                case_search=tool_input["case_search"],
                limit=tool_input.get("limit", 100),
            )
        else:
            return {"error": f"Unknown tool: {tool_name}"}
    except Exception as e:
        return {"error": str(e)}
