"""
Visual verification of MerusCase data via browser automation.
Logs into MerusCase, navigates to case pages, and takes screenshots
to verify that test data was entered correctly.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import structlog
from playwright.async_api import async_playwright

from config import (
    MERUSCASE_EMAIL,
    MERUSCASE_PASSWORD,
    OUTPUT_DIR,
)

logger = structlog.get_logger()

MERUSCASE_BASE = "https://meruscase.com"
SCREENSHOTS_DIR = OUTPUT_DIR / "verification_screenshots"

# MerusCase uses Angular SPA at /cms# with hash-based routing
CASE_VIEW_URL = f"{MERUSCASE_BASE}/cms#/caseFiles/view/{{case_id}}?t={{tab}}"


class VisualVerifier:
    """Logs into MerusCase and takes screenshots of case pages for visual verification."""

    def __init__(self, screenshot_dir: Path | None = None):
        self.screenshot_dir = screenshot_dir or SCREENSHOTS_DIR
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        self._browser = None
        self._context = None
        self._page = None

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()

    async def connect(self):
        """Launch browser and log into MerusCase."""
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=True)
        self._context = await self._browser.new_context(
            viewport={"width": 1920, "height": 1080}
        )
        self._page = await self._context.new_page()
        await self._login()

    async def disconnect(self):
        """Close browser."""
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()

    async def _wait_for_angular(self, timeout: int = 15):
        """Wait for MerusCase Angular SPA to finish rendering."""
        # Wait for domcontentloaded first, then give Angular time to render
        try:
            await self._page.wait_for_load_state("domcontentloaded", timeout=timeout * 1000)
        except Exception:
            pass
        # Give Angular time to bootstrap and render the view
        await asyncio.sleep(4)
        # Dismiss any modal popups MerusCase may show
        await self._dismiss_modals()

    async def _dismiss_modals(self):
        """Dismiss any modal popups that MerusCase may display."""
        for selector in [
            "button:has-text('Ok')",
            "button:has-text('OK')",
            "button:has-text('Close')",
            ".modal button.btn-primary",
            ".modal button.btn-default",
        ]:
            try:
                btn = self._page.locator(selector).first
                if await btn.is_visible(timeout=1000):
                    await btn.click()
                    await asyncio.sleep(1)
                    logger.info("modal_dismissed", selector=selector)
            except Exception:
                continue

    async def _login(self):
        """Log into MerusCase."""
        logger.info("logging_into_meruscase")

        await self._page.goto(f"{MERUSCASE_BASE}/users/login")
        await self._page.wait_for_load_state("domcontentloaded", timeout=30000)
        await asyncio.sleep(3)

        # MerusCase login uses input[type='text'] for email, not input[type='email']
        email_input = self._page.locator("input[type='text']").first
        await email_input.wait_for(state="visible", timeout=15000)
        await email_input.fill(MERUSCASE_EMAIL)

        password_input = self._page.locator("input[type='password']").first
        await password_input.wait_for(state="visible", timeout=10000)
        await password_input.fill(MERUSCASE_PASSWORD)

        # Take screenshot of login page
        await self._page.screenshot(
            path=str(self.screenshot_dir / "00_login_page.png"),
            full_page=True,
        )

        # MerusCase login button says "LOGIN"
        login_btn = self._page.locator("button:has-text('LOGIN')").first
        await login_btn.click()

        # Wait for login redirect — MerusCase redirects to /cms#/... after login
        try:
            await self._page.wait_for_load_state("networkidle", timeout=30000)
        except Exception:
            # Angular SPA may not reach networkidle — fallback to time-based wait
            pass
        await asyncio.sleep(3)

        # Take screenshot after login
        await self._page.screenshot(
            path=str(self.screenshot_dir / "01_post_login.png"),
            full_page=True,
        )

        current_url = self._page.url
        login_success = "/cms" in current_url
        logger.info("login_complete", url=current_url, success=login_success)

        if not login_success:
            logger.warning("login_may_have_failed", url=current_url)

    async def _navigate_to_case_tab(self, meruscase_id: int, tab: str) -> bool:
        """Navigate to a specific tab of a case page using hash routing."""
        url = CASE_VIEW_URL.format(case_id=meruscase_id, tab=tab)
        logger.info("navigating_to_tab", meruscase_id=meruscase_id, tab=tab, url=url)

        await self._page.goto(url)
        await self._wait_for_angular()
        return True

    async def verify_case(self, meruscase_id: int, case_label: str) -> dict[str, Any]:
        """
        Navigate to a case page and take screenshots for verification.

        Args:
            meruscase_id: MerusCase platform case ID
            case_label: Label for screenshot filenames (e.g. "TC-001_Danielle_Johnson")

        Returns:
            Dict with verification results and screenshot paths
        """
        result = {
            "meruscase_id": meruscase_id,
            "case_label": case_label,
            "screenshots": [],
            "success": False,
            "error": None,
        }

        try:
            # Tab 1: Case Details (main overview with metadata)
            await self._navigate_to_case_tab(meruscase_id, "case_details")
            main_screenshot = self.screenshot_dir / f"{case_label}_01_case_details.png"
            await self._page.screenshot(path=str(main_screenshot), full_page=True)
            result["screenshots"].append(str(main_screenshot))
            logger.info("screenshot_captured", file=str(main_screenshot))

            # Tab 2: Parties (employer, carrier, applicant)
            await self._navigate_to_case_tab(meruscase_id, "parties")
            parties_screenshot = self.screenshot_dir / f"{case_label}_02_parties.png"
            await self._page.screenshot(path=str(parties_screenshot), full_page=True)
            result["screenshots"].append(str(parties_screenshot))
            logger.info("screenshot_captured", file=str(parties_screenshot))

            # Tab 3: Activities (notes with case creation details)
            await self._navigate_to_case_tab(meruscase_id, "activities")
            activities_screenshot = self.screenshot_dir / f"{case_label}_03_activities.png"
            await self._page.screenshot(path=str(activities_screenshot), full_page=True)
            result["screenshots"].append(str(activities_screenshot))
            logger.info("screenshot_captured", file=str(activities_screenshot))

            # Tab 4: Documents
            await self._navigate_to_case_tab(meruscase_id, "documents")
            docs_screenshot = self.screenshot_dir / f"{case_label}_04_documents.png"
            await self._page.screenshot(path=str(docs_screenshot), full_page=True)
            result["screenshots"].append(str(docs_screenshot))
            logger.info("screenshot_captured", file=str(docs_screenshot))

            result["success"] = True
            logger.info(
                "case_verified",
                meruscase_id=meruscase_id,
                label=case_label,
                screenshots=len(result["screenshots"]),
            )

        except Exception as e:
            result["error"] = str(e)
            logger.error("verification_error", meruscase_id=meruscase_id, error=str(e))

            # Capture error state
            try:
                error_screenshot = self.screenshot_dir / f"{case_label}_error.png"
                await self._page.screenshot(path=str(error_screenshot), full_page=True)
                result["screenshots"].append(str(error_screenshot))
            except Exception:
                pass

        return result

    async def verify_all_cases(self, cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Verify multiple cases.

        Args:
            cases: List of dicts with 'meruscase_id' and 'label' keys

        Returns:
            List of verification results
        """
        results = []
        for case_info in cases:
            result = await self.verify_case(
                meruscase_id=case_info["meruscase_id"],
                case_label=case_info["label"],
            )
            results.append(result)
            await asyncio.sleep(1)

        # Summary
        passed = sum(1 for r in results if r["success"])
        failed = sum(1 for r in results if not r["success"])
        total_screenshots = sum(len(r["screenshots"]) for r in results)

        logger.info(
            "verification_complete",
            total=len(results),
            passed=passed,
            failed=failed,
            total_screenshots=total_screenshots,
            screenshot_dir=str(self.screenshot_dir),
        )

        return results
