"""
Batch case creator — single Browserless session for all cases.
Creates cases in MerusCase, populates metadata via API, updates progress DB.
"""

import asyncio
import json
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import (
    BROWSERLESS_API_TOKEN,
    MERUSCASE_ACCESS_TOKEN,
    MERUSCASE_EMAIL,
    MERUSCASE_PASSWORD,
)

import httpx

MERUSCASE_BASE = "https://meruscase.com"
API_BASE = "https://api.meruscase.com"
NEW_CASE_URL = f"{MERUSCASE_BASE}/cms#/caseFiles/add?t=1&lpt=0&nr=1&lpa=0"
DB_PATH = "progress.db"


def get_pending_cases() -> list[dict]:
    """Get all cases that haven't been created in MerusCase yet."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM cases WHERE status IN ('pdfs_ready', 'data_generated') ORDER BY internal_id"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_case_created(internal_id: str, meruscase_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "UPDATE cases SET status='case_created', meruscase_id=?, case_created=1 WHERE internal_id=?",
        (meruscase_id, internal_id),
    )
    conn.commit()
    conn.close()


def mark_case_error(internal_id: str, error: str):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "UPDATE cases SET status='error', error_message=? WHERE internal_id=?",
        (error, internal_id),
    )
    conn.commit()
    conn.close()


async def update_case_metadata(meruscase_id: int, case_row: dict):
    """Update case metadata via MerusCase REST API."""
    if not MERUSCASE_ACCESS_TOKEN:
        return

    headers = {
        "Authorization": f"Bearer {MERUSCASE_ACCESS_TOKEN}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    applicant_name = case_row.get("applicant_name", "Unknown")
    stage = case_row.get("litigation_stage", "")

    case_update = {
        "CaseFile": {
            "comments": (
                f"Workers' Compensation Case\n"
                f"Applicant: {applicant_name}\n"
                f"Litigation Stage: {stage}\n"
                f"Internal ID: {case_row['internal_id']}\n"
                f"Total Documents: {case_row.get('total_docs', 0)}"
            ),
        }
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{API_BASE}/caseFiles/edit/{meruscase_id}",
            headers=headers,
            json=case_update,
        )
        if resp.status_code == 200:
            print(f"    Metadata updated for MC-{meruscase_id}")
        else:
            print(f"    Metadata update failed: {resp.status_code}")


async def find_case_by_name(last_name: str, first_name: str) -> int | None:
    """Search for a recently-created case by name via API."""
    if not MERUSCASE_ACCESS_TOKEN:
        return None

    headers = {
        "Authorization": f"Bearer {MERUSCASE_ACCESS_TOKEN}",
        "Accept": "application/json",
    }

    search_name = f"{last_name}, {first_name}".upper()

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(f"{API_BASE}/caseFiles/index", headers=headers)
        if resp.status_code == 200:
            data = resp.json().get("data", {})
            if isinstance(data, dict):
                # Search from most recent (highest ID) first
                for case_id in sorted(data.keys(), key=int, reverse=True):
                    info = data[case_id]
                    case_name = info.get("1", "").upper()
                    if last_name.upper() in case_name and first_name.upper() in case_name:
                        return int(case_id)
    return None


async def create_all_cases():
    from playwright.async_api import async_playwright

    cases = get_pending_cases()
    if not cases:
        print("No pending cases to create.")
        return

    print(f"Creating {len(cases)} cases in MerusCase via single Browserless session...\n")

    p = await async_playwright().__aenter__()

    ws_url = f"wss://production-sfo.browserless.io?token={BROWSERLESS_API_TOKEN}"
    print("Connecting to Browserless...")
    browser = await p.chromium.connect_over_cdp(ws_url, timeout=60000)
    page = await browser.new_page()

    # Login
    print("Logging in to MerusCase...")
    await page.goto(f"{MERUSCASE_BASE}/users/login", timeout=30000)
    await page.wait_for_load_state("networkidle")
    await page.fill("#email", MERUSCASE_EMAIL)
    await page.fill("#password", MERUSCASE_PASSWORD)

    submit = page.locator("button[type='submit'], input[type='submit']")
    await submit.first.click()
    await page.wait_for_load_state("networkidle", timeout=30000)

    # Verify login
    if "login" in page.url:
        print("ERROR: Login failed!")
        await browser.close()
        await p.stop()
        return

    print(f"Logged in successfully. URL: {page.url}\n")

    created = 0
    failed = 0

    for case_row in cases:
        internal_id = case_row["internal_id"]
        applicant = case_row["applicant_name"]

        # Split name into first/last
        parts = applicant.split()
        if len(parts) >= 2:
            first_name = " ".join(parts[:-1])
            last_name = parts[-1]
        else:
            first_name = applicant
            last_name = ""

        print(f"[{internal_id}] Creating: {last_name.upper()}, {first_name.upper()}...")

        try:
            # Navigate to new case form
            await page.goto(NEW_CASE_URL, timeout=30000)
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(3)  # Wait for Angular to fully render

            # Dismiss any popup/modal
            ok_btn = page.locator("button:has-text('OK'), button:has-text('Ok')")
            if await ok_btn.count() > 0:
                await ok_btn.first.click()
                await asyncio.sleep(1)

            # Case Type is already "Workers' Compensation" by default — verify
            case_type_select = page.locator("select[name='data[CaseFile][case_type_id]']")
            if await case_type_select.count() > 0:
                await case_type_select.first.select_option(value="1")

            # Fill Contact (applicant) first name and last name
            first_name_input = page.locator("input[name='data[Contact][first_name]']")
            last_name_input = page.locator("input[name='data[Contact][last_name]']")

            if await first_name_input.count() == 0 or await last_name_input.count() == 0:
                print(f"  ERROR: Cannot find name fields")
                await page.screenshot(path=f"/tmp/merus_form_{internal_id}.png")
                mark_case_error(internal_id, "Cannot find name fields")
                failed += 1
                continue

            # Check "allow duplicates" to avoid conflict check blocking us
            allow_dups = page.locator("#merus-contact-allow-duplicates-checkbox")
            if await allow_dups.count() > 0:
                is_checked = await allow_dups.is_checked()
                if not is_checked:
                    await allow_dups.check()
                    await asyncio.sleep(0.5)

            await first_name_input.first.fill(first_name)
            await asyncio.sleep(0.3)
            await last_name_input.first.fill(last_name)
            await asyncio.sleep(0.5)

            # Fill Date of Injury
            doi_input = page.locator("input[name='data[Injury][date_of_injury]']")
            if await doi_input.count() > 0:
                await doi_input.first.fill("01/15/2025")
                await asyncio.sleep(0.3)

            # Click Save button
            save_btn = page.locator("a.btn-primary:has-text('Save'), button:has-text('Save')")
            if await save_btn.count() == 0:
                # Broader search
                save_btn = page.locator("a:has-text('Save'), button[type='submit']")

            if await save_btn.count() == 0:
                print(f"  ERROR: Cannot find Save button")
                await page.screenshot(path=f"/tmp/merus_nosave_{internal_id}.png")
                mark_case_error(internal_id, "Cannot find Save button")
                failed += 1
                continue

            await save_btn.first.click()

            # Wait for save to complete and potential redirect
            await asyncio.sleep(5)
            await page.wait_for_load_state("networkidle", timeout=30000)

            # Extract case ID from URL
            current_url = page.url
            meruscase_id = None

            # MerusCase redirects to #/caseFiles/view/{id} after creation
            match = re.search(r"caseFiles/(?:view/)?(\d+)", current_url)
            if match:
                meruscase_id = int(match.group(1))

            # Fallback: search API by name
            if not meruscase_id:
                await asyncio.sleep(2)
                meruscase_id = await find_case_by_name(last_name, first_name)

            if meruscase_id:
                mark_case_created(internal_id, meruscase_id)
                await update_case_metadata(meruscase_id, case_row)
                print(f"  OK — MC ID: {meruscase_id}")
                created += 1
            else:
                # Take screenshot for debugging
                await page.screenshot(path=f"/tmp/merus_noid_{internal_id}.png")
                print(f"  WARNING: Could not extract case ID. URL: {current_url}")
                mark_case_error(internal_id, f"Could not extract case ID. URL: {current_url}")
                failed += 1

        except Exception as e:
            print(f"  ERROR: {e}")
            mark_case_error(internal_id, str(e)[:200])
            failed += 1

        # Brief pause between cases
        await asyncio.sleep(2)

    # Cleanup
    await browser.close()
    await p.stop()

    print(f"\n{'='*50}")
    print(f"CASE CREATION COMPLETE")
    print(f"{'='*50}")
    print(f"  Created: {created}/{len(cases)}")
    print(f"  Failed:  {failed}/{len(cases)}")


if __name__ == "__main__":
    asyncio.run(create_all_cases())
