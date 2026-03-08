#!/usr/bin/env python3
"""
Live API + Field Mapping Test for merus-expert.

Two tests in one script:

1. ENDPOINT VERIFICATION — tests all 36 known-working endpoints against live API
2. FIELD MAPPING — creates a real test case, writes sentinel values to ALL known
   optional/unknown fields via POST, then launches a Playwright browser session
   so you can visually inspect where each field appears in the MerusCase UI.

Usage:
    python3 tests/live_field_mapping_test.py

Requirements:
    - .meruscase_token in /home/vncuser/Desktop/merus-expert/
    - MERUSCASE_EMAIL and MERUSCASE_PASSWORD in environment or hardcoded below
    - playwright install chromium

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import asyncio
import json
import os
import sys
import httpx
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

# ── Paths ────────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).parent.parent
TOKEN_FILE = Path("/home/vncuser/Desktop/merus-expert/.meruscase_token")
RESULTS_DIR = REPO_ROOT / "tests" / "live_results"
RESULTS_DIR.mkdir(exist_ok=True)

# ── Credentials ──────────────────────────────────────────────────────────────
TOKEN = TOKEN_FILE.read_text().strip()
EMAIL = "Alex@adjudica.ai"
PASSWORD = "MCBalcon!"
BASE_URL = "https://api.meruscase.com"
MERUS_WEB = "https://meruscase.com"

# ── Test case config ─────────────────────────────────────────────────────────
SENTINEL = "ZTEST"          # prefix for all sentinel values
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
TEST_CASE_NAME = f"ZTEST_FIELDMAP_{TIMESTAMP}"

# Sentinel values — distinctive enough to find in screenshots
S = {
    # Activity fields
    "activity_subject":     f"{SENTINEL}_SUBJECT_{TIMESTAMP}",
    "activity_description": f"{SENTINEL}_DESCRIPTION_{TIMESTAMP}",
    "activity_filename":    f"{SENTINEL}_FILENAME_{TIMESTAMP}",
    "activity_doc_author":  f"{SENTINEL}_DOC_AUTHOR_{TIMESTAMP}",
    # Party fields
    "party_notes":                      f"{SENTINEL}_PARTY_NOTES_{TIMESTAMP}",
    "party_testimony":                  f"{SENTINEL}_TESTIMONY_{TIMESTAMP}",
    "party_people_type_detail":         f"{SENTINEL}_PEOPLE_TYPE_DETAIL_{TIMESTAMP}",
    "party_insurance_policy_number":    f"{SENTINEL}_INS_POLICY_NUM_{TIMESTAMP}",
    "party_insurance_claim_number":     f"{SENTINEL}_INS_CLAIM_NUM_{TIMESTAMP}",
    "party_insurance_claim_status":     f"{SENTINEL}_INS_CLAIM_STATUS_{TIMESTAMP}",
    "party_insurance_policy_notes":     f"{SENTINEL}_INS_POLICY_NOTES_{TIMESTAMP}",
    "party_alt_policy_number":          f"{SENTINEL}_ALT_POLICY_NUM_{TIMESTAMP}",
    "party_alt_claim_number":           f"{SENTINEL}_ALT_CLAIM_NUM_{TIMESTAMP}",
    "party_alt_claim_status":           f"{SENTINEL}_ALT_CLAIM_STATUS_{TIMESTAMP}",
    "party_alt_policy_notes":           f"{SENTINEL}_ALT_POLICY_NOTES_{TIMESTAMP}",
    # Ledger fields
    "ledger_description":   f"{SENTINEL}_LEDGER_DESC_{TIMESTAMP}",
    "ledger_payee":         f"{SENTINEL}_PAYEE_{TIMESTAMP}",
    "ledger_payto":         f"{SENTINEL}_PAYTO_{TIMESTAMP}",
    "ledger_task_code":     f"{SENTINEL}_TASK_CODE",
    "ledger_activity_code": f"{SENTINEL}_ACTIVITY_CODE",
    "ledger_expense_code":  f"{SENTINEL}_EXPENSE_CODE",
}

# Reference data IDs (from /activityTypes, /users, /billingCodes)
USER_ID = 1973975           # Alex Brewsaugh
BILLING_CODE_ID = 107105    # "Test billing code"
NOTE_ACTIVITY_TYPE = 101    # Note (viewable=1)
MANUAL_ACTIVITY_TYPE = 100  # Manual Entry (viewable=1)


# ─────────────────────────────────────────────────────────────────────────────
# HTTP Helper
# ─────────────────────────────────────────────────────────────────────────────

def get_headers():
    return {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json",
            "Content-Type": "application/json"}


async def api(client: httpx.AsyncClient, method: str, endpoint: str, **kwargs):
    """Make API call, return (status, data, error)."""
    try:
        r = await client.request(method, endpoint, headers=get_headers(), **kwargs)
        body = r.json()
        return r.status_code, body, None
    except Exception as e:
        return 0, {}, str(e)


# ─────────────────────────────────────────────────────────────────────────────
# PART 1 — ENDPOINT VERIFICATION
# ─────────────────────────────────────────────────────────────────────────────

KNOWN_ENDPOINTS = [
    # (method, path, params_or_None, description)
    ("GET", "/caseFiles/index",              None,                    "List cases"),
    ("GET", "/caseTypes/index",              None,                    "Case types"),
    ("GET", "/caseStatuses/index",           None,                    "Case statuses"),
    ("GET", "/activities/index/56171871",    None,                    "Activities for case"),
    ("GET", "/activityTypes/index",          None,                    "Activity types"),
    ("GET", "/billingCodes/index",           None,                    "Billing codes"),
    ("GET", "/caseLedgersOpen/index",        None,                    "Open ledgers"),
    ("GET", "/caseLedgersReviewed/index",    None,                    "Reviewed ledgers"),
    ("GET", "/caseLedgers/index",            None,                    "All ledgers"),
    ("GET", "/partyGroups/index",            None,                    "Party groups"),
    ("GET", "/parties/view/56171871",        None,                    "Parties for case"),
    ("GET", "/parties/index",               {"case_file_id": 56171871}, "Parties index (filtered)"),
    ("GET", "/tasks/index",                  None,                    "Tasks"),
    ("GET", "/events/index",                 None,                    "Events"),
    ("GET", "/eventTypes/index",             None,                    "Event types"),
    ("GET", "/statutes/index",               None,                    "Statutes"),
    ("GET", "/paymentMethods/index",         None,                    "Payment methods"),
    ("GET", "/users/index",                  None,                    "Firm users"),
    ("GET", "/receivables/index",            None,                    "Receivables"),
    ("GET", "/uploads/index",               {"limit": 5},             "All uploads"),
    ("GET", "/uploads/index",               {"case_file_id": 56171871, "limit": 5}, "Uploads for case"),
    ("GET", "/documents/index",              None,                    "Documents list"),
    ("GET", "/contacts/index",              {"limit": 5},             "Contacts list"),
    ("GET", "/peopleTypes/index",            None,                    "People types"),
    ("GET", "/companies/index",             {"limit": 5},             "Companies"),
    ("GET", "/injuries/view/1",              None,                    "Injuries view (case 1)"),
    ("GET", "/courts/index",                 None,                    "Courts"),
    ("GET", "/invoices/index",              {"limit": 5},             "Invoices"),
    ("GET", "/billingRates/index",           None,                    "Billing rates"),
    ("GET", "/trustAccounts/index",          None,                    "Trust accounts"),
    ("GET", "/messages/index",              {"limit": 5},             "Messages"),
    ("GET", "/reports/index",               {"limit": 5},             "Reports"),
    ("GET", "/workflows/index",              None,                    "Workflows"),
    ("GET", "/oauthApps/index",              None,                    "OAuth apps"),
    ("GET", "/help",                         None,                    "Help"),
    # Case detail endpoints
    ("GET", "/caseFiles/view/56171871",      None,                    "Case file view"),
    ("GET", "/activities/index/56171905",    None,                    "Activities case 56171905"),
]

# Also test alternate URL patterns
URL_PATTERN_TESTS = [
    ("GET", "/case_files",   None, "snake_case alias"),
    ("GET", "/CaseFiles",    None, "PascalCase alias"),
]


async def run_endpoint_verification():
    """Test all known working endpoints and report results."""
    print("\n" + "="*70)
    print("PART 1: ENDPOINT VERIFICATION")
    print("="*70)

    results = []
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
        for method, path, params, desc in KNOWN_ENDPOINTS + URL_PATTERN_TESTS:
            kwargs = {"params": params} if params else {}
            status, body, err = await api(client, method, path, **kwargs)

            if isinstance(body, list):
                data = body
                meta = {}
            else:
                data = body.get("data", {})
                meta = body.get("meta", {})
            count = len(data) if isinstance(data, (dict, list)) else ("present" if data else "empty")
            meta_msg = meta.get("error_msg", "") if isinstance(meta, dict) else ""

            # Determine result
            ok = status == 200 and not err
            note = ""
            if meta_msg:
                note = f" [meta: {meta_msg}]"
            if err:
                note = f" [ERR: {err}]"

            symbol = "✓" if ok else "✗"
            print(f"  {symbol} {method} {path:<45} {status}  count={count}{note}")

            results.append({
                "endpoint": path, "method": method, "description": desc,
                "status": status, "ok": ok, "count": str(count),
                "meta_error": meta_msg, "error": err or "",
            })

    # Summary
    passed = sum(1 for r in results if r["ok"])
    print(f"\n  Result: {passed}/{len(results)} endpoints returned 200 OK")

    # Save results
    out = RESULTS_DIR / f"endpoint_verification_{TIMESTAMP}.json"
    out.write_text(json.dumps(results, indent=2))
    print(f"  Saved: {out}")
    return results


# ─────────────────────────────────────────────────────────────────────────────
# PART 2A — CREATE TEST CASE VIA PLAYWRIGHT
# ─────────────────────────────────────────────────────────────────────────────

async def create_test_case_via_browser() -> Optional[int]:
    """
    Log in to MerusCase and create a new test matter.
    Returns the case_file_id of the newly created case.
    """
    print("\n" + "="*70)
    print("PART 2A: CREATE TEST CASE VIA BROWSER")
    print("="*70)

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("  ! playwright not installed. Run: pip install playwright && playwright install chromium")
        return None

    case_id = None

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, slow_mo=300)
        ctx = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await ctx.new_page()

        try:
            # ── Login ─────────────────────────────────────────────────────
            print("  → Logging in to MerusCase...")
            await page.goto(f"{MERUS_WEB}/users/login")
            await page.wait_for_load_state("networkidle", timeout=15000)

            await page.fill('input[name="data[User][username]"]', EMAIL)
            await page.fill('input[name="data[User][password]"]', PASSWORD)
            await page.screenshot(path=str(RESULTS_DIR / "01_login.png"))
            # Try multiple login button selectors (MerusCase uses a button not input[submit])
            for login_sel in ['button:has-text("LOGIN")', 'button:has-text("Log In")',
                               'button[type="submit"]', 'input[type="submit"]']:
                try:
                    await page.click(login_sel, timeout=5000)
                    break
                except Exception:
                    continue
            await page.wait_for_load_state("networkidle", timeout=20000)
            print("  ✓ Logged in")
            await page.screenshot(path=str(RESULTS_DIR / "02_dashboard.png"))

            # ── Navigate to New Matter ─────────────────────────────────────
            print(f"  → Creating test case: {TEST_CASE_NAME}")
            await page.goto(f"{MERUS_WEB}/caseFiles/add")
            await page.wait_for_load_state("networkidle", timeout=15000)
            await page.screenshot(path=str(RESULTS_DIR / "03_new_case_form.png"))

            # Fill primary party (client name)
            selectors_to_try = [
                'input[name="data[CaseFile][primary_party]"]',
                'input[name="primary_party"]',
                '#CaseFilePrimaryParty',
                'input[placeholder*="party"]',
                'input[placeholder*="Party"]',
                'input[placeholder*="client"]',
                'input[placeholder*="Client"]',
            ]
            filled = False
            for sel in selectors_to_try:
                try:
                    await page.fill(sel, TEST_CASE_NAME, timeout=2000)
                    print(f"  ✓ Filled primary party with: {sel}")
                    filled = True
                    break
                except Exception:
                    continue

            if not filled:
                # Try to find any visible text input
                inputs = await page.query_selector_all('input[type="text"]')
                print(f"  ! Could not find primary party field. Found {len(inputs)} text inputs.")
                if inputs:
                    await inputs[0].fill(TEST_CASE_NAME)
                    print(f"  → Filled first text input")

            await page.screenshot(path=str(RESULTS_DIR / "04_case_form_filled.png"))

            # Submit
            submit_selectors = [
                'input[type="submit"]',
                'button[type="submit"]',
                'button:has-text("Save")',
                'button:has-text("Create")',
                'button:has-text("Add")',
            ]
            for sel in submit_selectors:
                try:
                    await page.click(sel, timeout=3000)
                    print(f"  ✓ Clicked submit: {sel}")
                    break
                except Exception:
                    continue

            await page.wait_for_load_state("networkidle", timeout=20000)
            await page.screenshot(path=str(RESULTS_DIR / "05_after_submit.png"))

            # Extract case ID from URL
            url = page.url
            print(f"  → Post-submit URL: {url}")
            import re
            match = re.search(r'/caseFiles/(?:view|edit)/(\d+)', url)
            if match:
                case_id = int(match.group(1))
                print(f"  ✓ New case_file_id: {case_id}")
            else:
                print("  ! Could not extract case_file_id from URL, checking activities...")
                # Try to get most recently created case from activities
                async with httpx.AsyncClient(base_url=BASE_URL, timeout=30,
                                              headers=get_headers()) as hc:
                    r = await hc.get('/caseLedgers/index', params={'limit': 1})
                    # This won't help but log what we got
                    print(f"  URL was: {url}")

        except Exception as e:
            print(f"  ! Browser error: {e}")
            await page.screenshot(path=str(RESULTS_DIR / "error_browser.png"))
        finally:
            await asyncio.sleep(2)
            await browser.close()

    return case_id


# ─────────────────────────────────────────────────────────────────────────────
# PART 2B — WRITE SENTINEL DATA TO ALL FIELDS VIA API
# ─────────────────────────────────────────────────────────────────────────────

async def write_sentinel_data(case_file_id: int) -> dict:
    """
    POST sentinel values to ALL optional/unknown fields on the test case.
    Returns dict of {field_group: {field_name: result}}.
    """
    print("\n" + "="*70)
    print(f"PART 2B: WRITE SENTINEL DATA TO ALL FIELDS (case {case_file_id})")
    print("="*70)

    field_map = {}

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:

        # ── Activity: ALL optional fields ────────────────────────────────
        print("\n  [ACTIVITY] Posting with ALL optional fields...")
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        activity_payload = {
            "Activity": {
                "case_file_id": case_file_id,
                "activity_type_id": NOTE_ACTIVITY_TYPE,
                "subject":          S["activity_subject"],
                "description":      S["activity_description"],
                "date":             date_str,
                "duration":         42,            # unknown: shows as time billed?
                "billable":         1,
                "billing_code_id":  BILLING_CODE_ID,
                "user_id":          USER_ID,
                # Discovered from GET response — testing if accepted on POST
                "document_author":  S["activity_doc_author"],
                "date_received":    datetime.now().strftime("%Y-%m-%d"),
                "date_of_service":  datetime.now().strftime("%Y-%m-%d"),
                "document_date":    datetime.now().strftime("%Y-%m-%d"),
            }
        }
        status, body, err = await api(client, "POST", "/activities/add", json=activity_payload)
        activity_id = body.get("data", {}).get("id") if isinstance(body.get("data"), dict) else body.get("id")
        field_map["activity"] = {
            "status": status, "body": body, "err": err, "created_id": activity_id,
            "fields_sent": list(activity_payload["Activity"].keys()),
        }
        print(f"  status={status} id={activity_id} err={err}")
        print(f"  response: {json.dumps(body, indent=2)[:300]}")

        # ── Activity: Telephone Call type ────────────────────────────────
        print("\n  [ACTIVITY-PHONE] Telephone Call type (111)...")
        phone_payload = {
            "Activity": {
                "case_file_id": case_file_id,
                "activity_type_id": 111,  # Telephone Call
                "subject":          f"{SENTINEL}_PHONE_CALL_{TIMESTAMP}",
                "description":      f"{SENTINEL}_PHONE_DESC_{TIMESTAMP}",
                "date":             date_str,
                "duration":         15,
                "billable":         1,
                "user_id":          USER_ID,
            }
        }
        status2, body2, _ = await api(client, "POST", "/activities/add", json=phone_payload)
        field_map["activity_phone"] = {"status": status2, "body": body2}
        print(f"  status={status2} response: {json.dumps(body2, indent=2)[:200]}")

        # ── Party: ALL known optional fields ─────────────────────────────
        print("\n  [PARTY] Posting with ALL optional/unknown fields...")
        party_payload = {
            "Party": {
                "case_file_id": case_file_id,
                "party_type":   "Other",
                "first_name":   f"{SENTINEL}_FIRSTNAME",
                "last_name":    f"{SENTINEL}_LASTNAME_{TIMESTAMP}",
                "company_name": f"{SENTINEL}_COMPANY_{TIMESTAMP}",
                "email":        "ztest@ztest.invalid",
                "phone":        "555-ZTEST-01",
                "address":      f"{SENTINEL}_ADDRESS_FIELD",
                "city":         f"{SENTINEL}_CITY",
                "state":        "CA",
                "zip":          "90210",
                # Unknown fields discovered from GET /parties/view response
                "middle_name":                       f"{SENTINEL}_MID",
                "notes":                             S["party_notes"],
                "testimony":                         S["party_testimony"],
                "people_type_detail":                S["party_people_type_detail"],
                "insurance_policy_number":           S["party_insurance_policy_number"],
                "insurance_claim_number":            S["party_insurance_claim_number"],
                "insurance_claim_status":            S["party_insurance_claim_status"],
                "insurance_policy_notes":            S["party_insurance_policy_notes"],
                "alternate_insurance_policy_number": S["party_alt_policy_number"],
                "alternate_insurance_claim_number":  S["party_alt_claim_number"],
                "alternate_insurance_claim_status":  S["party_alt_claim_status"],
                "alternate_insurance_policy_notes":  S["party_alt_policy_notes"],
            }
        }
        status3, body3, err3 = await api(client, "POST", "/parties/add", json=party_payload)
        field_map["party"] = {
            "status": status3, "body": body3, "err": err3,
            "fields_sent": list(party_payload["Party"].keys()),
        }
        print(f"  status={status3} err={err3}")
        print(f"  response: {json.dumps(body3, indent=2)[:400]}")

        # ── CaseLedger: ALL optional/unknown fields ───────────────────────
        print("\n  [LEDGER-FEE] Posting ledger entry with ALL optional fields...")
        # FEE type uses hours × hourly_rate. Do NOT send item_qty/unit_cost (COST-type
        # fields) in the same request — the API rejects mixed calculation sets.
        # IMPORTANT: MerusCase enforces 0.1-hour (6-minute) billing increments.
        # "0.25" is 2.5 × 0.1 (not a whole number of increments) and will be rejected.
        # Use multiples of 0.1 only: 0.1, 0.2, 0.3, …, 0.5, 1.0, 1.5, etc.
        ledger_payload = {
            "CaseLedger": {
                "case_file_id":         str(case_file_id),
                "amount":               "100.00",   # hours × hourly_rate = 0.5 × 200.00
                "description":          S["ledger_description"],
                "date":                 datetime.now().strftime("%Y-%m-%d"),
                "ledger_type_id":       1,  # FEE
                "hours":                "0.5",
                "hourly_rate":          "200.00",   # 0.5 × 200.00 = 100.00 ✓
                "payee":                S["ledger_payee"],
                "payto":                S["ledger_payto"],
                "task_code":            S["ledger_task_code"],
                "activity_code":        S["ledger_activity_code"],
                "expense_code":         S["ledger_expense_code"],
                "alternate_billing_code": "ZTEST_ALT_CODE",
                "billing_code_id":      str(BILLING_CODE_ID),
                "user_id":              str(USER_ID),
            }
        }
        status4, body4, err4 = await api(client, "POST", "/caseLedgers/add", json=ledger_payload)
        field_map["ledger_fee"] = {
            "status": status4, "body": body4, "err": err4,
            "fields_sent": list(ledger_payload["CaseLedger"].keys()),
        }
        print(f"  status={status4} err={err4}")
        print(f"  response: {json.dumps(body4, indent=2)[:400]}")

        # ── CaseLedger: COST type ─────────────────────────────────────────
        print("\n  [LEDGER-COST] Posting COST ledger entry...")
        cost_payload = {
            "CaseLedger": {
                "case_file_id":   str(case_file_id),
                "amount":         "25.00",
                "description":    f"{SENTINEL}_COST_WCAB_FILING_{TIMESTAMP}",
                "date":           datetime.now().strftime("%Y-%m-%d"),
                "ledger_type_id": 2,  # COST
                "payee":          f"{SENTINEL}_COST_PAYEE",
                "payto":          f"{SENTINEL}_COST_PAYTO",
            }
        }
        status5, body5, _ = await api(client, "POST", "/caseLedgers/add", json=cost_payload)
        field_map["ledger_cost"] = {"status": status5, "body": body5}
        print(f"  status={status5} response: {json.dumps(body5, indent=2)[:200]}")

        # ── Save full field map ───────────────────────────────────────────
        out = RESULTS_DIR / f"field_map_{TIMESTAMP}.json"
        out.write_text(json.dumps(field_map, indent=2, default=str))
        print(f"\n  ✓ Sentinel field map saved: {out}")

    return field_map


# ─────────────────────────────────────────────────────────────────────────────
# PART 2C — BROWSER VERIFICATION: SCREENSHOT ALL UI SECTIONS
# ─────────────────────────────────────────────────────────────────────────────

async def screenshot_case_in_browser(case_file_id: int):
    """
    Log in to MerusCase and screenshot every tab/section of the test case.
    This lets you visually inspect where each sentinel value appears.
    """
    print("\n" + "="*70)
    print(f"PART 2C: BROWSER VERIFICATION — SCREENSHOT ALL SECTIONS (case {case_file_id})")
    print("="*70)

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("  ! playwright not installed")
        return

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, slow_mo=200)
        ctx = await browser.new_context(viewport={"width": 1600, "height": 1000})
        page = await ctx.new_page()

        try:
            # ── Login ──────────────────────────────────────────────────────
            print("  → Logging in...")
            await page.goto(f"{MERUS_WEB}/users/login")
            await page.wait_for_load_state("networkidle", timeout=15000)
            await page.fill('input[name="data[User][username]"]', EMAIL)
            await page.fill('input[name="data[User][password]"]', PASSWORD)
            for login_sel in ['button:has-text("LOGIN")', 'button:has-text("Log In")',
                               'button[type="submit"]', 'input[type="submit"]']:
                try:
                    await page.click(login_sel, timeout=5000)
                    break
                except Exception:
                    continue
            await page.wait_for_load_state("networkidle", timeout=20000)
            print("  ✓ Logged in")

            # ── Navigate to case ───────────────────────────────────────────
            case_url = f"{MERUS_WEB}/caseFiles/view/{case_file_id}"
            print(f"  → Navigating to: {case_url}")
            await page.goto(case_url)
            await page.wait_for_load_state("networkidle", timeout=20000)

            # Screenshot 1: Main case view (overview)
            await page.screenshot(path=str(RESULTS_DIR / f"case_{case_file_id}_01_overview.png"),
                                   full_page=True)
            print("  ✓ Screenshot: 01_overview")

            # Find and click all visible tabs
            tab_selectors = [
                ('li a:has-text("Activities")',       "02_activities"),
                ('li a:has-text("Activity")',         "02_activities"),
                ('li a:has-text("Billing")',          "03_billing"),
                ('li a:has-text("Ledger")',           "03_billing"),
                ('li a:has-text("Parties")',          "04_parties"),
                ('li a:has-text("Contacts")',         "04_parties"),
                ('li a:has-text("Documents")',        "05_documents"),
                ('li a:has-text("Notes")',            "06_notes"),
                ('li a:has-text("Events")',           "07_events"),
                ('li a:has-text("Tasks")',            "08_tasks"),
                ('li a:has-text("Details")',          "09_details"),
                ('li a:has-text("Info")',             "10_info"),
            ]

            for selector, shot_name in tab_selectors:
                try:
                    tab = await page.query_selector(selector)
                    if tab:
                        await tab.click()
                        await page.wait_for_load_state("networkidle", timeout=10000)
                        await asyncio.sleep(0.5)
                        await page.screenshot(
                            path=str(RESULTS_DIR / f"case_{case_file_id}_{shot_name}.png"),
                            full_page=True)
                        print(f"  ✓ Screenshot: {shot_name}")
                except Exception as e:
                    print(f"  ! Tab '{shot_name}': {e}")

            # Also try direct URL patterns for each section
            sections = [
                ("activities", "10_activities_direct"),
                ("parties",    "11_parties_direct"),
                ("billing",    "12_billing_direct"),
                ("documents",  "13_documents_direct"),
            ]
            for section, shot_name in sections:
                try:
                    await page.goto(f"{MERUS_WEB}/caseFiles/view/{case_file_id}#{section}")
                    await page.wait_for_load_state("networkidle", timeout=10000)
                    await asyncio.sleep(0.5)
                    await page.screenshot(
                        path=str(RESULTS_DIR / f"case_{case_file_id}_{shot_name}.png"),
                        full_page=True)
                    print(f"  ✓ Screenshot: {shot_name}")
                except Exception as e:
                    print(f"  ! Section '{section}': {e}")

            # Search for sentinel text in page source
            print("\n  → Searching for sentinel values in page source...")
            content = await page.content()
            for field_name, sentinel_val in S.items():
                if SENTINEL in sentinel_val and sentinel_val in content:
                    print(f"  ✓ FOUND in page: {field_name} = {sentinel_val[:40]}")
                elif SENTINEL in sentinel_val:
                    print(f"  ✗ NOT in page:  {field_name} = {sentinel_val[:40]}")

            # Keep browser open 30s for manual inspection
            print("\n  → Browser will stay open 30s for manual inspection...")
            print(f"  → Case URL: {case_url}")
            print(f"  → Screenshots saved to: {RESULTS_DIR}")
            await asyncio.sleep(30)

        except Exception as e:
            print(f"  ! Browser error: {e}")
            import traceback
            traceback.print_exc()
            await page.screenshot(path=str(RESULTS_DIR / "error_verification.png"), full_page=True)
        finally:
            await browser.close()


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

async def main():
    print(f"\n{'='*70}")
    print("MERUS-EXPERT LIVE API + FIELD MAPPING TEST")
    print(f"Timestamp: {TIMESTAMP}")
    print(f"Screenshots: {RESULTS_DIR}")
    print(f"{'='*70}")

    # ── Part 1: Verify all known endpoints ───────────────────────────────
    endpoint_results = await run_endpoint_verification()

    # ── Part 2: Field mapping test ────────────────────────────────────────
    # Step A: Create new test case via browser
    print("\n  → Which case to use for field mapping?")
    print("     Option 1: Create NEW test case via browser (recommended)")
    print("     Option 2: Use existing case 56171871 (ANDREWS, DENNIS — has lots of data)")
    print()

    # Try to create new case first; fall back to existing case
    new_case_id = await create_test_case_via_browser()

    if new_case_id:
        target_case_id = new_case_id
        print(f"  ✓ Using newly created case: {target_case_id}")
    else:
        target_case_id = 56171871
        print(f"  → Using existing case: {target_case_id} (ANDREWS, DENNIS)")

    # Step B: Write sentinel data to all fields
    field_results = await write_sentinel_data(target_case_id)

    # Step C: Screenshot all sections in browser
    await screenshot_case_in_browser(target_case_id)

    # ── Final Summary ─────────────────────────────────────────────────────
    print("\n" + "="*70)
    print("COMPLETE — FIELD MAPPING SUMMARY")
    print("="*70)
    print(f"\nSentinel prefix: {SENTINEL}")
    print(f"Timestamp:       {TIMESTAMP}")
    print(f"Case used:       {target_case_id}")
    print(f"\nFields written:")
    for name, val in S.items():
        print(f"  {name:<45} = {val}")
    print(f"\nScreenshots in: {RESULTS_DIR}")
    print(f"\nLook for these sentinels in the MerusCase UI:")
    print(f"  Activities tab: {S['activity_subject'][:30]}...")
    print(f"  Parties tab:    {S['party_notes'][:30]}...")
    print(f"  Billing tab:    {S['ledger_description'][:30]}...")

    # Save complete summary
    summary = {
        "timestamp": TIMESTAMP,
        "case_file_id": target_case_id,
        "sentinels": S,
        "field_results": {k: {"status": v.get("status"), "err": v.get("err")}
                          for k, v in field_results.items()},
        "screenshots_dir": str(RESULTS_DIR),
    }
    (RESULTS_DIR / f"summary_{TIMESTAMP}.json").write_text(json.dumps(summary, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
