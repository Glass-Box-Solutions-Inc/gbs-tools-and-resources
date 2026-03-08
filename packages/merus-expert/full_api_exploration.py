"""
Full MerusCase API Exploration - Find all undocumented endpoints.
"""

import asyncio
import logging
import json
from pathlib import Path
from datetime import datetime
import httpx

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

API_BASE = "https://api.meruscase.com"
TOKEN = Path(".meruscase_token").read_text().strip()

# Track results
results = {
    "working": [],
    "needs_params": [],
    "permission_denied": [],
    "not_found": [],
    "other_errors": []
}


async def test_endpoint(client, method, endpoint, description=""):
    """Test a single endpoint and categorize result."""
    try:
        if method == "GET":
            resp = await client.get(f"{API_BASE}/{endpoint}")
        elif method == "POST":
            resp = await client.post(f"{API_BASE}/{endpoint}", json={})
        else:
            return None

        data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else None

        if resp.status_code == 200:
            if data and "errors" in data and data.get("errors"):
                error = data["errors"][0] if isinstance(data["errors"], list) else data["errors"]
                error_type = error.get("errorType", "") if isinstance(error, dict) else str(error)
                error_msg = error.get("errorMessage", "") if isinstance(error, dict) else str(error)

                if "not_allowed" in error_type or "privilege" in error_msg.lower():
                    results["permission_denied"].append((endpoint, description))
                    return "permission_denied"
                elif "required" in error_msg.lower() or "missing" in error_msg.lower():
                    results["needs_params"].append((endpoint, description, error_msg))
                    return "needs_params"
                else:
                    results["other_errors"].append((endpoint, description, error_msg))
                    return "other_error"
            else:
                # Success!
                item_count = "?"
                keys = []
                if isinstance(data, list):
                    item_count = len(data)
                    if data and isinstance(data[0], dict):
                        keys = list(data[0].keys())[:5]
                elif isinstance(data, dict):
                    item_count = "dict"
                    keys = list(data.keys())[:8]

                results["working"].append((endpoint, description, item_count, keys))
                return "working"

        elif resp.status_code == 404:
            results["not_found"].append((endpoint, description))
            return "not_found"
        else:
            results["other_errors"].append((endpoint, description, f"HTTP {resp.status_code}"))
            return "other_error"

    except Exception as e:
        results["other_errors"].append((endpoint, description, str(e)[:50]))
        return "error"


async def explore_all():
    """Comprehensive API exploration."""

    logger.info("=" * 80)
    logger.info("MERUSCASE API FULL EXPLORATION")
    logger.info(f"Started: {datetime.now().isoformat()}")
    logger.info("=" * 80)

    # Comprehensive list of potential endpoints based on:
    # - Known documentation
    # - Common REST patterns
    # - CakePHP conventions (MerusCase uses CakePHP)
    # - Legal practice management common entities

    endpoints_to_test = [
        # ============ DOCUMENTED ENDPOINTS ============
        ("GET", "caseFiles/index", "List cases"),
        ("GET", "caseFiles/view/1", "View case"),
        ("GET", "caseTypes/index", "Case types"),
        ("GET", "activities/index/1", "Activities for case"),
        ("GET", "activityTypes/index", "Activity types"),
        ("GET", "billingCodes/index", "Billing codes"),
        ("GET", "caseLedgersOpen/index", "Open ledgers"),
        ("GET", "caseLedgersReviewed/index", "Reviewed ledgers"),
        ("GET", "parties/view/1", "Parties for case"),
        ("GET", "partyGroups/index", "Party groups"),
        ("GET", "tasks/index", "Tasks"),
        ("GET", "events/index", "Events"),
        ("GET", "eventTypes/index", "Event types"),
        ("GET", "statutes/index", "Statutes"),
        ("GET", "paymentMethods/index", "Payment methods"),
        ("GET", "users/index", "Firm users"),
        ("GET", "receivables/index", "Receivables"),

        # ============ UPLOADS/DOCUMENTS ============
        ("GET", "uploads/index", "All uploads"),
        ("GET", "documents/index", "Documents list"),
        ("GET", "documents/download/1", "Download doc"),
        ("GET", "folders/index", "Folders"),
        ("GET", "documentFolders/index", "Doc folders"),
        ("GET", "documentTypes/index", "Doc types"),
        ("GET", "fileTypes/index", "File types"),
        ("GET", "attachments/index", "Attachments"),

        # ============ CONTACTS/PARTIES ============
        ("GET", "contacts/index", "Contacts list"),
        ("GET", "contacts/view/1", "View contact"),
        ("GET", "parties/index", "All parties"),
        ("GET", "partyTypes/index", "Party types"),
        ("GET", "peopleTypes/index", "People types"),
        ("GET", "companies/index", "Companies"),
        ("GET", "vendors/index", "Vendors"),
        ("GET", "clients/index", "Clients"),
        ("GET", "attorneys/index", "Attorneys"),
        ("GET", "experts/index", "Experts"),
        ("GET", "witnesses/index", "Witnesses"),
        ("GET", "insuranceCompanies/index", "Insurance cos"),
        ("GET", "employers/index", "Employers"),
        ("GET", "doctors/index", "Doctors"),
        ("GET", "medicalProviders/index", "Medical providers"),

        # ============ CASE DETAILS ============
        ("GET", "arrests/view/1", "Arrests"),
        ("GET", "injuries/view/1", "Injuries"),
        ("GET", "generalIncidents/view/1", "General incidents"),
        ("GET", "malpractices/view/1", "Malpractice"),
        ("GET", "premiseLiabilities/view/1", "Premise liability"),
        ("GET", "productLiabilities/view/1", "Product liability"),
        ("GET", "vehicleAccidents/view/1", "Vehicle accidents"),
        ("GET", "caseStatuses/index", "Case statuses"),
        ("GET", "caseStages/index", "Case stages"),
        ("GET", "practiceAreas/index", "Practice areas"),
        ("GET", "venues/index", "Venues"),
        ("GET", "courts/index", "Courts"),
        ("GET", "judges/index", "Judges"),
        ("GET", "jurisdictions/index", "Jurisdictions"),

        # ============ BILLING/FINANCE ============
        ("GET", "caseLedgers/index", "All ledgers"),
        ("GET", "invoices/index", "Invoices"),
        ("GET", "payments/index", "Payments"),
        ("GET", "expenses/index", "Expenses"),
        ("GET", "timeEntries/index", "Time entries"),
        ("GET", "billingRates/index", "Billing rates"),
        ("GET", "trustAccounts/index", "Trust accounts"),
        ("GET", "retainers/index", "Retainers"),
        ("GET", "fees/index", "Fees"),
        ("GET", "costs/index", "Costs"),
        ("GET", "disbursements/index", "Disbursements"),

        # ============ CALENDAR/SCHEDULING ============
        ("GET", "appointments/index", "Appointments"),
        ("GET", "deadlines/index", "Deadlines"),
        ("GET", "reminders/index", "Reminders"),
        ("GET", "courtDates/index", "Court dates"),
        ("GET", "depositions/index", "Depositions"),
        ("GET", "hearings/index", "Hearings"),
        ("GET", "trials/index", "Trials"),
        ("GET", "mediations/index", "Mediations"),
        ("GET", "arbitrations/index", "Arbitrations"),
        ("GET", "limitationDates/index", "Limitation dates"),

        # ============ COMMUNICATIONS ============
        ("GET", "emails/index", "Emails"),
        ("GET", "messages/index", "Messages"),
        ("GET", "notes/index", "Notes"),
        ("GET", "phoneCalls/index", "Phone calls"),
        ("GET", "letters/index", "Letters"),
        ("GET", "faxes/index", "Faxes"),
        ("GET", "communications/index", "Communications"),

        # ============ FIRM/ADMIN ============
        ("GET", "firmUsers/index", "Firm users"),
        ("GET", "firms/index", "Firms"),
        ("GET", "firms/view", "Firm details"),
        ("GET", "offices/index", "Offices"),
        ("GET", "branches/index", "Branches"),
        ("GET", "departments/index", "Departments"),
        ("GET", "teams/index", "Teams"),
        ("GET", "roles/index", "Roles"),
        ("GET", "permissions/index", "Permissions"),
        ("GET", "settings/index", "Settings"),
        ("GET", "preferences/index", "Preferences"),

        # ============ REPORTS ============
        ("GET", "reports/index", "Reports"),
        ("GET", "dashboards/index", "Dashboards"),
        ("GET", "analytics/index", "Analytics"),
        ("GET", "statistics/index", "Statistics"),
        ("GET", "metrics/index", "Metrics"),

        # ============ WORKFLOWS ============
        ("GET", "workflows/index", "Workflows"),
        ("GET", "automations/index", "Automations"),
        ("GET", "templates/index", "Templates"),
        ("GET", "documentTemplates/index", "Doc templates"),
        ("GET", "emailTemplates/index", "Email templates"),
        ("GET", "checklists/index", "Checklists"),

        # ============ INTEGRATIONS ============
        ("GET", "integrations/index", "Integrations"),
        ("GET", "webhooks/index", "Webhooks"),
        ("GET", "apiKeys/index", "API keys"),
        ("GET", "oauthApps/index", "OAuth apps"),

        # ============ WORKERS COMP SPECIFIC ============
        ("GET", "wcClaims/index", "WC claims"),
        ("GET", "wcBenefits/index", "WC benefits"),
        ("GET", "wcInjuries/index", "WC injuries"),
        ("GET", "bodyParts/index", "Body parts"),
        ("GET", "injuryTypes/index", "Injury types"),
        ("GET", "treatmentTypes/index", "Treatment types"),
        ("GET", "qme/index", "QME"),
        ("GET", "ame/index", "AME"),
        ("GET", "pqme/index", "PQME"),
        ("GET", "medicalRecords/index", "Medical records"),
        ("GET", "medicalReports/index", "Medical reports"),

        # ============ PERSONAL INJURY SPECIFIC ============
        ("GET", "piCases/index", "PI cases"),
        ("GET", "damages/index", "Damages"),
        ("GET", "settlements/index", "Settlements"),
        ("GET", "demands/index", "Demands"),
        ("GET", "liens/index", "Liens"),
        ("GET", "medicalBills/index", "Medical bills"),

        # ============ IMMIGRATION SPECIFIC ============
        ("GET", "immigrationCases/index", "Immigration cases"),
        ("GET", "visaTypes/index", "Visa types"),
        ("GET", "petitions/index", "Petitions"),

        # ============ FAMILY LAW SPECIFIC ============
        ("GET", "familyCases/index", "Family cases"),
        ("GET", "custodyOrders/index", "Custody orders"),
        ("GET", "supportOrders/index", "Support orders"),

        # ============ MISC LEGAL ============
        ("GET", "discovery/index", "Discovery"),
        ("GET", "interrogatories/index", "Interrogatories"),
        ("GET", "admissions/index", "Admissions"),
        ("GET", "productionRequests/index", "Production requests"),
        ("GET", "subpoenas/index", "Subpoenas"),
        ("GET", "motions/index", "Motions"),
        ("GET", "pleadings/index", "Pleadings"),
        ("GET", "filings/index", "Filings"),
        ("GET", "orders/index", "Orders"),
        ("GET", "judgments/index", "Judgments"),

        # ============ CAKEPHP COMMON PATTERNS ============
        ("GET", "pages/index", "Pages"),
        ("GET", "tags/index", "Tags"),
        ("GET", "categories/index", "Categories"),
        ("GET", "comments/index", "Comments"),
        ("GET", "logs/index", "Logs"),
        ("GET", "auditLogs/index", "Audit logs"),
        ("GET", "activityLogs/index", "Activity logs"),
        ("GET", "notifications/index", "Notifications"),
        ("GET", "alerts/index", "Alerts"),

        # ============ ALTERNATIVE PATTERNS ============
        ("GET", "case-files", "case-files hyphen"),
        ("GET", "case_files", "case_files underscore"),
        ("GET", "CaseFiles", "CaseFiles camel"),

        # ============ API INFO ============
        ("GET", "api/version", "API version"),
        ("GET", "version", "Version"),
        ("GET", "status", "Status"),
        ("GET", "health", "Health"),
        ("GET", "info", "Info"),
        ("GET", "schema", "Schema"),
        ("GET", "endpoints", "Endpoints list"),
        ("GET", "help", "Help"),
        ("GET", "docs", "Docs"),
    ]

    async with httpx.AsyncClient(
        headers={"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"},
        timeout=15.0
    ) as client:

        total = len(endpoints_to_test)
        logger.info(f"\nTesting {total} endpoints...\n")

        for i, (method, endpoint, desc) in enumerate(endpoints_to_test):
            result = await test_endpoint(client, method, endpoint, desc)

            # Progress indicator
            if (i + 1) % 20 == 0:
                logger.info(f"  Progress: {i+1}/{total} ({len(results['working'])} working)")

    # ============ PRINT RESULTS ============
    logger.info("\n" + "=" * 80)
    logger.info("RESULTS SUMMARY")
    logger.info("=" * 80)

    logger.info(f"\n✓ WORKING ENDPOINTS ({len(results['working'])}):")
    logger.info("-" * 60)
    for endpoint, desc, count, keys in sorted(results["working"]):
        logger.info(f"  {endpoint}")
        logger.info(f"      {desc} | Items: {count} | Keys: {keys[:5]}")

    logger.info(f"\n⚠ NEEDS PARAMETERS ({len(results['needs_params'])}):")
    logger.info("-" * 60)
    for endpoint, desc, msg in sorted(results["needs_params"])[:20]:
        logger.info(f"  {endpoint}: {msg[:50]}")

    logger.info(f"\n🔒 PERMISSION DENIED ({len(results['permission_denied'])}):")
    logger.info("-" * 60)
    for endpoint, desc in sorted(results["permission_denied"]):
        logger.info(f"  {endpoint} ({desc})")

    logger.info(f"\n❌ NOT FOUND ({len(results['not_found'])}):")
    # Don't print all not found, just count

    logger.info(f"\n📊 STATISTICS:")
    logger.info("-" * 60)
    logger.info(f"  Working:           {len(results['working'])}")
    logger.info(f"  Needs Parameters:  {len(results['needs_params'])}")
    logger.info(f"  Permission Denied: {len(results['permission_denied'])}")
    logger.info(f"  Not Found:         {len(results['not_found'])}")
    logger.info(f"  Other Errors:      {len(results['other_errors'])}")

    # Save results to file
    output = {
        "timestamp": datetime.now().isoformat(),
        "working": results["working"],
        "needs_params": results["needs_params"],
        "permission_denied": results["permission_denied"],
        "not_found_count": len(results["not_found"]),
        "other_errors": results["other_errors"][:20]
    }

    Path("api_exploration_results.json").write_text(json.dumps(output, indent=2))
    logger.info("\nResults saved to api_exploration_results.json")


if __name__ == "__main__":
    asyncio.run(explore_all())
