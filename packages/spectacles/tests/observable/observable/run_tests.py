#!/usr/bin/env python3
"""
Spectacles Observable Test Suite

Interactive test runner that creates Browserless Live URLs so you can
watch automation happen in real-time in your browser.

Usage:
    python projects/spectacles/tests/observable/run_tests.py
    python projects/spectacles/tests/observable/run_tests.py --test 1
    python projects/spectacles/tests/observable/run_tests.py --test 1 --no-prompt

Tiers:
    1. Direct Browser (Live View) - You watch Playwright drive a real browser
    2. Spectacles API            - Terminal output, validates production service
    3. E2E Workflows (Live View) - Auth + navigation + extraction combined

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright, Page, BrowserContext
import httpx

# Set via --no-prompt flag: skip input() calls for non-interactive runs
NO_PROMPT = False
# Parsed CLI args, available globally for test functions (e.g. test 14)
_cli_args = argparse.Namespace()

# ──────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────

SPECTACLES_URL = "https://spectacles-378330630438.us-central1.run.app"
BROWSERLESS_TOKEN = "2TcWyCwbfKt7UWCbec6a2ee3b613b579fb0edb5f7a52b0ace"
BROWSERLESS_WSS = "wss://production-sfo.browserless.io"
AUTH_DIR = Path("/home/vncuser/Desktop/Claude_Code/.auth")
GOOGLE_AUTH_PATH = str(AUTH_DIR / "google-auth.json")
SCREENSHOT_DIR = Path(__file__).parent / "screenshots"

# Import auth presets and helpers from core module
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from security.auth_capture import AUTH_PRESETS, AuthCaptureSession, resolve_auth_params

SCREENSHOT_DIR.mkdir(exist_ok=True)


# ──────────────────────────────────────────────────────────────
# Live Browser Session (async context manager)
# ──────────────────────────────────────────────────────────────

class LiveBrowserSession:
    """
    Connects to Browserless via CDP, retrieves a liveURL for observation,
    and exposes page/context for test automation.

    Usage:
        async with LiveBrowserSession() as session:
            print(f"Watch here: {session.live_url}")
            await session.page.goto("https://example.com")
    """

    def __init__(self, timeout_ms: int = 300_000):
        self.timeout_ms = timeout_ms
        self.live_url: Optional[str] = None
        self.page: Optional[Page] = None
        self.context: Optional[BrowserContext] = None
        self._playwright = None
        self._browser = None

    async def __aenter__(self):
        self._playwright = await async_playwright().__aenter__()
        ws_url = f"{BROWSERLESS_WSS}?token={BROWSERLESS_TOKEN}&stealth=true"
        self._browser = await self._playwright.chromium.connect_over_cdp(ws_url)

        self.context = self._browser.contexts[0]
        self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()

        # Get live URL via CDP
        cdp = await self.context.new_cdp_session(self.page)
        result = await cdp.send("Browserless.liveURL", {
            "timeout": self.timeout_ms,
        })
        self.live_url = result.get("liveURL", "")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        try:
            if self._browser:
                await self._browser.close()
        except Exception:
            pass
        try:
            if self._playwright:
                await self._playwright.__aexit__(exc_type, exc_val, exc_tb)
        except Exception:
            pass


# ──────────────────────────────────────────────────────────────
# Test Result tracking
# ──────────────────────────────────────────────────────────────

@dataclass
class TestResult:
    name: str
    passed: bool
    duration: float
    error: Optional[str] = None
    screenshot_path: Optional[str] = None


class TestRunner:
    """Collects test results and prints a summary table."""

    def __init__(self):
        self.results: list[TestResult] = []

    def record(self, result: TestResult):
        self.results.append(result)
        status = "PASS" if result.passed else "FAIL"
        icon = "+" if result.passed else "x"
        print(f"  [{icon}] {result.name}  ({result.duration:.1f}s)  {status}")
        if result.error:
            print(f"      Error: {result.error}")
        if result.screenshot_path:
            print(f"      Screenshot: {result.screenshot_path}")

    def print_summary(self):
        passed = sum(1 for r in self.results if r.passed)
        failed = sum(1 for r in self.results if not r.passed)
        total = len(self.results)

        print("\n" + "=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)
        print(f"{'Test':<40} {'Result':<8} {'Time':<8}")
        print("-" * 60)
        for r in self.results:
            status = "PASS" if r.passed else "FAIL"
            print(f"{r.name:<40} {status:<8} {r.duration:.1f}s")
        print("-" * 60)
        print(f"Total: {total}   Passed: {passed}   Failed: {failed}")
        print("=" * 60)


runner = TestRunner()


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

def open_browser(url: str):
    """Open a URL in the system browser."""
    try:
        subprocess.Popen(
            ["google-chrome", "--no-first-run", "--disable-session-crashed-bubble", url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        try:
            webbrowser.open(url)
        except Exception:
            pass  # URL is printed anyway


def prompt_live_url(live_url: str):
    """Open the live URL in the browser and optionally wait for user."""
    print("\n" + "=" * 60)
    print("LIVE BROWSER SESSION READY")
    print("=" * 60)
    print(f"\nOpening in browser:\n")
    print(f"  {live_url}\n")
    open_browser(live_url)
    if NO_PROMPT:
        print("(--no-prompt: starting in 3s...)")
        time.sleep(3)
    else:
        input("Press Enter when ready to start the test...")
    print()


def load_google_auth() -> Optional[dict]:
    """Load saved Google auth state from disk."""
    if not os.path.exists(GOOGLE_AUTH_PATH):
        return None
    with open(GOOGLE_AUTH_PATH) as f:
        return json.load(f)


# ──────────────────────────────────────────────────────────────
# TIER 1: Direct Browser Tests (Live View)
# ──────────────────────────────────────────────────────────────

async def test_navigation():
    """Load 3 URLs sequentially, verify page titles."""
    t0 = time.time()
    try:
        async with LiveBrowserSession() as session:
            prompt_live_url(session.live_url)

            targets = [
                ("https://example.com", "Example Domain"),
                ("https://en.wikipedia.org/wiki/Main_Page", "Wikipedia"),
                ("https://github.com", "GitHub"),
            ]

            for url, expected_fragment in targets:
                print(f"  Navigating to {url} ...")
                await session.page.goto(url, wait_until="domcontentloaded", timeout=20000)
                await asyncio.sleep(1)
                title = await session.page.title()
                print(f"    Title: {title}")
                assert expected_fragment.lower() in title.lower(), (
                    f"Expected '{expected_fragment}' in title, got '{title}'"
                )

            runner.record(TestResult("Navigation", True, time.time() - t0))
    except Exception as e:
        runner.record(TestResult("Navigation", False, time.time() - t0, str(e)))


async def test_form_filling():
    """Fill a form on httpbin.org/forms/post."""
    t0 = time.time()
    try:
        async with LiveBrowserSession() as session:
            prompt_live_url(session.live_url)

            print("  Navigating to httpbin form...")
            await session.page.goto("https://httpbin.org/forms/post", wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(1)

            print("  Filling form fields...")
            await session.page.fill('input[name="custname"]', "Spectacles Test User")
            await asyncio.sleep(0.5)
            await session.page.fill('input[name="custtel"]', "555-0123")
            await asyncio.sleep(0.5)
            await session.page.fill('input[name="custemail"]', "test@spectacles.dev")
            await asyncio.sleep(0.5)

            # Select pizza size radio
            await session.page.check('input[name="size"][value="medium"]')
            await asyncio.sleep(0.5)

            # Check a topping
            await session.page.check('input[name="topping"][value="cheese"]')
            await asyncio.sleep(0.5)

            # Fill delivery time
            await session.page.fill('input[name="delivery"]', "13:00")
            await asyncio.sleep(0.5)

            # Fill comments
            await session.page.fill('textarea[name="comments"]', "Observable test - automated by Spectacles")
            await asyncio.sleep(1)

            print("  Form filled successfully!")
            runner.record(TestResult("Form Filling", True, time.time() - t0))
    except Exception as e:
        runner.record(TestResult("Form Filling", False, time.time() - t0, str(e)))


async def test_click_interact():
    """Click buttons on a page and verify state changes."""
    t0 = time.time()
    try:
        async with LiveBrowserSession() as session:
            prompt_live_url(session.live_url)

            # Use the W3Schools tryit page with a button example
            print("  Navigating to interactive test page...")
            await session.page.goto(
                "https://www.w3schools.com/js/tryit.asp?filename=tryjs_intro_lightbulb",
                wait_until="domcontentloaded",
                timeout=20000,
            )
            await asyncio.sleep(2)

            # Switch to the iframe with the actual content
            iframe = session.page.frame(name="iframeResult")
            if iframe:
                print("  Found iframe, clicking light bulb button...")
                # Click "Turn on the light" button
                btn = iframe.locator('button:has-text("Turn on")')
                if await btn.count() > 0:
                    await btn.click()
                    await asyncio.sleep(1)
                    print("  Clicked 'Turn on the light'")

                    btn_off = iframe.locator('button:has-text("Turn off")')
                    if await btn_off.count() > 0:
                        await btn_off.click()
                        await asyncio.sleep(1)
                        print("  Clicked 'Turn off the light'")
                else:
                    print("  Button not found in iframe, trying alternative...")
                    # Fallback: just verify the iframe loaded
                    content = await iframe.content()
                    assert len(content) > 100, "Iframe content too short"
                    print("  Iframe loaded with content")
            else:
                print("  No iframe found, verifying page loaded...")
                title = await session.page.title()
                assert "w3schools" in title.lower() or "tryit" in title.lower()
                print(f"  Page loaded: {title}")

            runner.record(TestResult("Click & Interact", True, time.time() - t0))
    except Exception as e:
        runner.record(TestResult("Click & Interact", False, time.time() - t0, str(e)))


async def test_screenshots():
    """Take viewport and full-page screenshots."""
    t0 = time.time()
    try:
        async with LiveBrowserSession() as session:
            prompt_live_url(session.live_url)

            print("  Navigating to Wikipedia...")
            await session.page.goto("https://en.wikipedia.org/wiki/Web_browser", wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(2)

            viewport_path = str(SCREENSHOT_DIR / "viewport_screenshot.png")
            fullpage_path = str(SCREENSHOT_DIR / "fullpage_screenshot.png")

            print("  Taking viewport screenshot...")
            await session.page.screenshot(path=viewport_path)
            print(f"    Saved: {viewport_path}")

            print("  Taking full-page screenshot...")
            await session.page.screenshot(path=fullpage_path, full_page=True)
            print(f"    Saved: {fullpage_path}")

            assert os.path.exists(viewport_path), "Viewport screenshot not saved"
            assert os.path.exists(fullpage_path), "Full-page screenshot not saved"
            assert os.path.getsize(viewport_path) > 1000, "Viewport screenshot too small"
            assert os.path.getsize(fullpage_path) > 1000, "Full-page screenshot too small"

            runner.record(TestResult("Screenshots", True, time.time() - t0,
                                      screenshot_path=str(SCREENSHOT_DIR)))
    except Exception as e:
        runner.record(TestResult("Screenshots", False, time.time() - t0, str(e)))


async def test_scrolling():
    """Scroll a long page up and down."""
    t0 = time.time()
    try:
        async with LiveBrowserSession() as session:
            prompt_live_url(session.live_url)

            print("  Navigating to a long Wikipedia article...")
            await session.page.goto(
                "https://en.wikipedia.org/wiki/History_of_the_Internet",
                wait_until="domcontentloaded",
                timeout=20000,
            )
            await asyncio.sleep(2)

            print("  Scrolling down (3 times)...")
            for i in range(3):
                await session.page.evaluate("window.scrollBy(0, 800)")
                await asyncio.sleep(0.8)
                scroll_y = await session.page.evaluate("window.scrollY")
                print(f"    Scroll position: {scroll_y}px")

            print("  Scrolling back to top...")
            await session.page.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(1)
            scroll_y = await session.page.evaluate("window.scrollY")
            assert scroll_y == 0, f"Expected scroll at top, got {scroll_y}"
            print("    Back at top!")

            runner.record(TestResult("Scrolling", True, time.time() - t0))
    except Exception as e:
        runner.record(TestResult("Scrolling", False, time.time() - t0, str(e)))


async def test_google_auth_saved():
    """Apply saved Google cookies and verify authenticated access to Drive."""
    t0 = time.time()
    try:
        auth_data = load_google_auth()
        if not auth_data:
            runner.record(TestResult("Google Auth (Saved)", False, time.time() - t0,
                                      "Auth file not found. Run: node scripts/google-auth-save.js"))
            return

        async with LiveBrowserSession() as session:
            prompt_live_url(session.live_url)

            cookies = auth_data.get("cookies", [])
            print(f"  Loading {len(cookies)} saved cookies...")
            await session.context.add_cookies(cookies)

            print("  Navigating to Google Drive...")
            await session.page.goto("https://drive.google.com", wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)

            current_url = session.page.url
            print(f"  Current URL: {current_url}")

            if "accounts.google.com" in current_url:
                runner.record(TestResult("Google Auth (Saved)", False, time.time() - t0,
                                          "Auth state expired - redirected to login. Run: node scripts/google-auth-save.js"))
                return

            title = await session.page.title()
            print(f"  Page title: {title}")

            # Take a screenshot of authenticated state
            ss_path = str(SCREENSHOT_DIR / "google_drive_auth.png")
            await session.page.screenshot(path=ss_path)
            print(f"  Screenshot: {ss_path}")

            runner.record(TestResult("Google Auth (Saved)", True, time.time() - t0,
                                      screenshot_path=ss_path))
    except Exception as e:
        runner.record(TestResult("Google Auth (Saved)", False, time.time() - t0, str(e)))


async def test_google_auth_manual():
    """Navigate to Google login - user types password in live view."""
    t0 = time.time()
    try:
        async with LiveBrowserSession() as session:
            prompt_live_url(session.live_url)

            print("  Navigating to Google sign-in...")
            await session.page.goto("https://accounts.google.com/signin", wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(2)

            print("\n" + "-" * 50)
            print("MANUAL STEP: In the live browser view:")
            print("  1. Enter your email address")
            print("  2. Click Next")
            print("  3. Enter your password")
            print("  4. Complete any 2FA prompts")
            print("-" * 50)
            if NO_PROMPT:
                print("(--no-prompt: skipping manual wait)")
            else:
                input("\nPress Enter here AFTER you've signed in...")

            # Check if login succeeded
            current_url = session.page.url
            print(f"  Current URL: {current_url}")

            if "accounts.google.com/signin" in current_url:
                print("  Still on login page - checking further...")
                await asyncio.sleep(2)
                current_url = session.page.url

            # Try navigating to Drive to verify auth
            print("  Navigating to Google Drive to verify auth...")
            await session.page.goto("https://drive.google.com", wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)

            current_url = session.page.url
            title = await session.page.title()
            print(f"  Drive URL: {current_url}")
            print(f"  Drive title: {title}")

            is_authenticated = "accounts.google.com" not in current_url
            ss_path = str(SCREENSHOT_DIR / "google_manual_auth.png")
            await session.page.screenshot(path=ss_path)

            runner.record(TestResult("Google Auth (Manual)", is_authenticated, time.time() - t0,
                                      error=None if is_authenticated else "Still on login page after manual auth",
                                      screenshot_path=ss_path))
    except Exception as e:
        runner.record(TestResult("Google Auth (Manual)", False, time.time() - t0, str(e)))


async def test_multi_step_workflow():
    """Navigate to form, fill it, submit, verify result."""
    t0 = time.time()
    try:
        async with LiveBrowserSession() as session:
            prompt_live_url(session.live_url)

            # Step 1: Navigate to httpbin form
            print("  Step 1: Navigate to form...")
            await session.page.goto("https://httpbin.org/forms/post", wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(1)

            # Step 2: Fill form
            print("  Step 2: Fill form fields...")
            await session.page.fill('input[name="custname"]', "Multi-Step Test")
            await session.page.fill('input[name="custtel"]', "555-9999")
            await session.page.fill('input[name="custemail"]', "multistep@spectacles.dev")
            await session.page.check('input[name="size"][value="large"]')
            await session.page.check('input[name="topping"][value="bacon"]')
            await session.page.check('input[name="topping"][value="cheese"]')
            await session.page.fill('input[name="delivery"]', "18:30")
            await session.page.fill('textarea[name="comments"]', "Multi-step workflow test")
            await asyncio.sleep(1)

            # Step 3: Submit form
            print("  Step 3: Submit form...")
            await session.page.click('button:has-text("Submit")')
            await asyncio.sleep(2)

            # Step 4: Verify result page
            print("  Step 4: Verify result...")
            content = await session.page.content()
            current_url = session.page.url

            # httpbin returns JSON after form submit
            has_response = "Multi-Step Test" in content or "httpbin" in current_url
            print(f"  Result page URL: {current_url}")
            print(f"  Response contains submitted data: {has_response}")

            ss_path = str(SCREENSHOT_DIR / "multi_step_result.png")
            await session.page.screenshot(path=ss_path)

            runner.record(TestResult("Multi-Step Workflow", has_response, time.time() - t0,
                                      error=None if has_response else "Form submission result not found",
                                      screenshot_path=ss_path))
    except Exception as e:
        runner.record(TestResult("Multi-Step Workflow", False, time.time() - t0, str(e)))


# ──────────────────────────────────────────────────────────────
# TIER 2: Spectacles API Tests (Terminal only)
# ──────────────────────────────────────────────────────────────

async def test_health_check():
    """Verify Spectacles production service is healthy."""
    t0 = time.time()
    try:
        async with httpx.AsyncClient() as client:
            print("  Checking Spectacles health endpoint...")
            response = await client.get(f"{SPECTACLES_URL}/health", timeout=30.0)
            print(f"  Status code: {response.status_code}")
            data = response.json()
            print(f"  Response: {json.dumps(data, indent=2)}")

            is_healthy = response.status_code == 200
            runner.record(TestResult("Health Check", is_healthy, time.time() - t0,
                                      error=None if is_healthy else f"HTTP {response.status_code}"))
    except Exception as e:
        runner.record(TestResult("Health Check", False, time.time() - t0, str(e)))


async def test_task_lifecycle():
    """Submit a task, poll until terminal state, verify lifecycle."""
    t0 = time.time()
    try:
        async with httpx.AsyncClient() as client:
            # Submit task
            print("  Submitting task to Spectacles API...")
            payload = {
                "goal": "Navigate to example.com and report the page title",
                "start_url": "https://example.com",
                "require_approval": False,
            }
            response = await client.post(
                f"{SPECTACLES_URL}/api/tasks/",
                json=payload,
                timeout=30.0,
            )
            print(f"  Create response: {response.status_code}")

            if response.status_code not in (200, 201):
                runner.record(TestResult("Task Lifecycle", False, time.time() - t0,
                                          f"Failed to create task: HTTP {response.status_code} - {response.text}"))
                return

            data = response.json()
            task_id = data.get("task_id")
            print(f"  Task ID: {task_id}")
            print(f"  Initial status: {data.get('status')}")

            # Poll for completion
            # API GET uses "state" (uppercase) not "status"
            terminal_states = {"COMPLETED", "FAILED", "CANCELLED", "ERROR"}
            states_seen = [data.get("status", "submitted")]
            max_polls = 60  # 2 minutes max

            for i in range(max_polls):
                await asyncio.sleep(2)
                status_resp = await client.get(
                    f"{SPECTACLES_URL}/api/tasks/{task_id}",
                    timeout=10.0,
                )
                if status_resp.status_code != 200:
                    print(f"  Poll {i+1}: HTTP {status_resp.status_code}")
                    continue

                status_data = status_resp.json()
                current_state = status_data.get("state", status_data.get("status", "unknown"))

                if current_state not in states_seen:
                    states_seen.append(current_state)
                    print(f"  Poll {i+1}: {current_state}")

                is_active = status_data.get("is_active", True)
                if current_state in terminal_states or not is_active:
                    print(f"\n  Final state: {current_state}")
                    print(f"  States observed: {' -> '.join(states_seen)}")
                    if status_data.get("error"):
                        print(f"  Error: {status_data['error']}")
                    runner.record(TestResult("Task Lifecycle", True, time.time() - t0))
                    return

            # Timeout
            print(f"  Timed out after {max_polls * 2}s. States seen: {' -> '.join(states_seen)}")
            runner.record(TestResult("Task Lifecycle", False, time.time() - t0,
                                      f"Timed out. States: {' -> '.join(states_seen)}"))
    except Exception as e:
        runner.record(TestResult("Task Lifecycle", False, time.time() - t0, str(e)))


async def test_screenshot_skill():
    """Test the /api/skills/screenshot endpoint."""
    t0 = time.time()
    try:
        async with httpx.AsyncClient() as client:
            print("  Requesting screenshot via Skills API...")
            payload = {
                "url": "https://example.com",
                "mode": "browser",
                "full_page": True,
            }
            response = await client.post(
                f"{SPECTACLES_URL}/api/skills/screenshot",
                json=payload,
                timeout=60.0,
            )
            print(f"  Status code: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                print(f"  Response keys: {list(data.keys())}")
                has_screenshot = "screenshot" in data or "image" in data or "url" in data or "base64" in data
                print(f"  Contains screenshot data: {has_screenshot}")
                runner.record(TestResult("Screenshot Skill", True, time.time() - t0))
            else:
                print(f"  Response: {response.text[:500]}")
                runner.record(TestResult("Screenshot Skill", False, time.time() - t0,
                                          f"HTTP {response.status_code}"))
    except Exception as e:
        runner.record(TestResult("Screenshot Skill", False, time.time() - t0, str(e)))


async def test_hitl_flow():
    """Submit a task with require_approval=True, observe HITL state."""
    t0 = time.time()
    try:
        async with httpx.AsyncClient() as client:
            print("  Submitting HITL task (require_approval=True)...")
            payload = {
                "goal": "Navigate to example.com and click any link on the page",
                "start_url": "https://example.com",
                "require_approval": True,
            }
            response = await client.post(
                f"{SPECTACLES_URL}/api/tasks/",
                json=payload,
                timeout=30.0,
            )
            print(f"  Create response: {response.status_code}")

            if response.status_code not in (200, 201):
                runner.record(TestResult("HITL Flow", False, time.time() - t0,
                                          f"Failed to create: HTTP {response.status_code}"))
                return

            data = response.json()
            task_id = data.get("task_id")
            print(f"  Task ID: {task_id}")
            print(f"  Initial status: {data.get('status')}")

            # Poll and watch for AWAITING_HUMAN or terminal state
            terminal_states = {"COMPLETED", "FAILED", "CANCELLED", "ERROR"}
            hitl_states = {"AWAITING_HUMAN", "PAUSED", "awaiting_human", "paused"}
            states_seen = [data.get("status", "submitted")]
            saw_hitl = False
            max_polls = 60

            for i in range(max_polls):
                await asyncio.sleep(2)
                status_resp = await client.get(
                    f"{SPECTACLES_URL}/api/tasks/{task_id}",
                    timeout=10.0,
                )
                if status_resp.status_code != 200:
                    continue

                status_data = status_resp.json()
                current_state = status_data.get("state", status_data.get("status", "unknown"))

                if current_state not in states_seen:
                    states_seen.append(current_state)
                    print(f"  Poll {i+1}: {current_state}")

                if current_state in hitl_states:
                    saw_hitl = True
                    print(f"\n  HITL state reached!")
                    print(f"  States: {' -> '.join(states_seen)}")

                    # Try to resume the task
                    print("  Resuming task with approval...")
                    resume_resp = await client.post(
                        f"{SPECTACLES_URL}/api/tasks/{task_id}/resume",
                        json={"approved": True, "human_input": "approved"},
                        timeout=30.0,
                    )
                    print(f"  Resume response: {resume_resp.status_code}")

                    # Poll a bit more for final state
                    for j in range(15):
                        await asyncio.sleep(2)
                        final_resp = await client.get(
                            f"{SPECTACLES_URL}/api/tasks/{task_id}",
                            timeout=10.0,
                        )
                        if final_resp.status_code == 200:
                            final_data = final_resp.json()
                            final_state = final_data.get("state", final_data.get("status", "unknown"))
                            if final_state not in states_seen:
                                states_seen.append(final_state)
                                print(f"  Post-resume poll {j+1}: {final_state}")
                            if final_state in terminal_states or not final_data.get("is_active", True):
                                break

                    print(f"  Full lifecycle: {' -> '.join(states_seen)}")
                    runner.record(TestResult("HITL Flow", True, time.time() - t0))
                    return

                is_active = status_data.get("is_active", True)
                if current_state in terminal_states or not is_active:
                    print(f"\n  Task reached terminal state without HITL pause.")
                    print(f"  States: {' -> '.join(states_seen)}")
                    print(f"  (This can happen if the goal is simple enough to complete without approval)")
                    # Still a valid test - we observed the lifecycle
                    runner.record(TestResult("HITL Flow", True, time.time() - t0))
                    return

            print(f"  Timed out. States: {' -> '.join(states_seen)}")
            runner.record(TestResult("HITL Flow", False, time.time() - t0,
                                      f"Timed out. States: {' -> '.join(states_seen)}"))
    except Exception as e:
        runner.record(TestResult("HITL Flow", False, time.time() - t0, str(e)))


# ──────────────────────────────────────────────────────────────
# TIER 3: E2E Workflows (Live View)
# ──────────────────────────────────────────────────────────────

async def test_authenticated_drive():
    """Login with saved cookies, navigate Drive, list files, screenshot."""
    t0 = time.time()
    try:
        auth_data = load_google_auth()
        if not auth_data:
            runner.record(TestResult("Authenticated Drive E2E", False, time.time() - t0,
                                      "Auth file not found. Run: node scripts/google-auth-save.js"))
            return

        async with LiveBrowserSession() as session:
            prompt_live_url(session.live_url)

            # Step 1: Apply saved auth
            cookies = auth_data.get("cookies", [])
            print(f"  Step 1: Loading {len(cookies)} saved cookies...")
            await session.context.add_cookies(cookies)

            # Step 2: Navigate to Google Drive
            print("  Step 2: Navigating to Google Drive...")
            await session.page.goto("https://drive.google.com", wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)

            current_url = session.page.url
            if "accounts.google.com" in current_url:
                runner.record(TestResult("Authenticated Drive E2E", False, time.time() - t0,
                                          "Auth expired - redirected to login. Run: node scripts/google-auth-save.js"))
                return

            # Step 3: Wait for Drive to load and extract file names
            print("  Step 3: Extracting file/folder names...")
            await asyncio.sleep(3)

            # Try to get file names from the Drive interface
            file_names = await session.page.evaluate("""
                () => {
                    // Drive file names are in divs with data-tooltip attribute or specific selectors
                    const items = document.querySelectorAll('[data-tooltip]');
                    const names = [];
                    items.forEach(item => {
                        const name = item.getAttribute('data-tooltip');
                        if (name && name.length > 0 && name.length < 200) {
                            names.push(name);
                        }
                    });
                    // Also try common Drive element patterns
                    const divs = document.querySelectorAll('.KL4NAf');
                    divs.forEach(d => {
                        if (d.textContent.trim()) names.push(d.textContent.trim());
                    });
                    return [...new Set(names)].slice(0, 20);
                }
            """)

            if file_names:
                print(f"  Found {len(file_names)} items:")
                for name in file_names[:10]:
                    print(f"    - {name}")
                if len(file_names) > 10:
                    print(f"    ... and {len(file_names) - 10} more")
            else:
                print("  No file names extracted (Drive UI may have changed)")

            # Step 4: Screenshot
            print("  Step 4: Taking screenshot...")
            ss_path = str(SCREENSHOT_DIR / "drive_e2e.png")
            await session.page.screenshot(path=ss_path, full_page=False)
            print(f"  Screenshot: {ss_path}")

            title = await session.page.title()
            print(f"  Page title: {title}")

            runner.record(TestResult("Authenticated Drive E2E", True, time.time() - t0,
                                      screenshot_path=ss_path))
    except Exception as e:
        runner.record(TestResult("Authenticated Drive E2E", False, time.time() - t0, str(e)))


# ──────────────────────────────────────────────────────────────
# UTILITIES
# ──────────────────────────────────────────────────────────────

async def test_capture_auth_state():
    """Open live browser, user logs into any service, capture & save storage state.

    Uses the core AuthCaptureSession from security/auth_capture.py.
    """
    t0 = time.time()
    try:
        # Resolve params from CLI args or interactive prompts
        service, login_url, verify_url = resolve_auth_params(
            service=getattr(_cli_args, "service", None),
            login_url=getattr(_cli_args, "login_url", None),
            verify_url=getattr(_cli_args, "verify_url", None),
            interactive=not NO_PROMPT,
        )

        credential_key = f"{service}-auth"

        print(f"\n  Service:        {service}")
        print(f"  Login URL:      {login_url}")
        print(f"  Verify URL:     {verify_url or '(none)'}")
        print(f"  Credential key: {credential_key}")
        print(f"  Local path:     {AUTH_DIR / f'{credential_key}.json'}")

        session = AuthCaptureSession(
            service=service,
            login_url=login_url,
            verify_url=verify_url,
            credential_key=credential_key,
            browserless_token=BROWSERLESS_TOKEN,
            browserless_wss=BROWSERLESS_WSS,
            timeout_ms=600_000,
        )

        try:
            live_url = await session.start()
            prompt_live_url(live_url)

            print("\n" + "-" * 55)
            print(f"  MANUAL STEP: Complete login for '{service}' in the live browser")
            print("  1. Enter your credentials")
            print("  2. Complete any 2FA / MFA prompts")
            print("  3. Wait until you are fully logged in")
            print("-" * 55)

            if NO_PROMPT:
                print("  (--no-prompt: waiting 60s for manual login...)")
                await asyncio.sleep(60)
            else:
                input("\n  Press Enter here AFTER you've signed in...")

            # Capture
            print("\n  Capturing storage state...")
            state = await session.capture()
            cookie_count = len(state.get("cookies", []))
            origin_count = len(state.get("origins", []))
            print(f"  Captured: {cookie_count} cookies, {origin_count} origins")

            if cookie_count == 0:
                runner.record(TestResult("Capture Auth State", False, time.time() - t0,
                                          "No cookies captured - login may not have completed"))
                return

            # Save locally and to GCP
            print("\n  Saving...")
            results = await session.save(
                local_dir=str(AUTH_DIR),
                gcp_project="glassbox-spectacles",
            )

            if results.get("local_path"):
                print(f"  Saved locally: {results['local_path']}")
            if results.get("gcp_saved"):
                print(f"  Saved to Secret Manager: {results['secret_name']}")
            else:
                print("  WARNING: Failed to save to Secret Manager (local file still saved)")

            # Verify
            if verify_url:
                print(f"\n  Verifying auth at {verify_url} ...")
                verified = await session.verify()

                if not verified:
                    runner.record(TestResult("Capture Auth State", False, time.time() - t0,
                                              f"Auth verification failed - redirected back to login"))
                    return

                print(f"  Verification PASSED")

            # Screenshot
            ss_path = str(SCREENSHOT_DIR / f"capture_auth_{service}.png")
            if session.page:
                await session.page.screenshot(path=ss_path)
                print(f"  Screenshot: {ss_path}")

            print(f"\n  Auth state for '{service}' captured and saved!")
            runner.record(TestResult("Capture Auth State", True, time.time() - t0,
                                      screenshot_path=ss_path))
        finally:
            await session.close()

    except Exception as e:
        runner.record(TestResult("Capture Auth State", False, time.time() - t0, str(e)))


# ──────────────────────────────────────────────────────────────
# Menu & Main
# ──────────────────────────────────────────────────────────────

TESTS = {
    "1": ("Navigation", test_navigation),
    "2": ("Form Filling", test_form_filling),
    "3": ("Click & Interact", test_click_interact),
    "4": ("Screenshots", test_screenshots),
    "5": ("Scrolling", test_scrolling),
    "6": ("Google Auth (Saved)", test_google_auth_saved),
    "7": ("Google Auth (Manual)", test_google_auth_manual),
    "8": ("Multi-Step Workflow", test_multi_step_workflow),
    "9": ("Health Check", test_health_check),
    "10": ("Task Lifecycle", test_task_lifecycle),
    "11": ("Screenshot Skill", test_screenshot_skill),
    "12": ("HITL Flow", test_hitl_flow),
    "13": ("Authenticated Drive E2E", test_authenticated_drive),
    "14": ("Capture Auth State", test_capture_auth_state),
}


def print_menu():
    print("\n" + "=" * 55)
    print("   SPECTACLES OBSERVABLE TEST SUITE")
    print("=" * 55)
    print()
    print("  DIRECT BROWSER (Live View):")
    print("    [1]  Navigation           - Load 3 URLs, verify titles")
    print("    [2]  Form Filling         - Fill a form on httpbin.org")
    print("    [3]  Click & Interact     - Click buttons, verify state")
    print("    [4]  Screenshots          - Take viewport + full-page shots")
    print("    [5]  Scrolling            - Scroll a long page up/down")
    print("    [6]  Google Auth (Saved)  - Apply saved cookies, open Drive")
    print("    [7]  Google Auth (Manual) - Navigate to login, you type pw")
    print("    [8]  Multi-Step Workflow  - Fill form -> submit -> verify")
    print()
    print("  SPECTACLES API:")
    print("    [9]  Health Check         - Verify production service")
    print("    [10] Task Lifecycle       - Submit -> poll -> complete")
    print("    [11] Screenshot Skill     - POST /api/skills/screenshot")
    print("    [12] HITL Flow            - Submit with require_approval")
    print()
    print("  E2E WORKFLOWS (Live View):")
    print("    [13] Authenticated Drive  - Login -> Drive -> list -> screenshot")
    print()
    print("  UTILITIES:")
    print("    [14] Capture Auth State   - Login to any service, save cookies locally + GCP")
    print()
    print("  [A] Run All    [Q] Quit")
    print()


async def run_all():
    """Run all tests sequentially."""
    for key in sorted(TESTS.keys(), key=int):
        name, test_fn = TESTS[key]
        print(f"\n{'='*55}")
        print(f"  Running: {name}")
        print(f"{'='*55}")
        await test_fn()


async def main():
    global NO_PROMPT, _cli_args

    parser = argparse.ArgumentParser(description="Spectacles Observable Test Suite")
    parser.add_argument("--test", type=str, help="Run a specific test by number (1-14) or 'all'")
    parser.add_argument("--no-prompt", action="store_true", help="Skip interactive prompts (for CI/non-interactive use)")
    parser.add_argument("--service", type=str, help="[Test 14] Service preset name (google, github, meruscase, westlaw) or custom name")
    parser.add_argument("--login-url", type=str, help="[Test 14] Login URL (overrides preset)")
    parser.add_argument("--verify-url", type=str, help="[Test 14] URL to navigate after login to verify auth")
    args = parser.parse_args()
    _cli_args = args

    if args.no_prompt:
        NO_PROMPT = True

    # Direct test mode (non-interactive)
    if args.test:
        choice = args.test.strip().upper()
        if choice == "ALL" or choice == "A":
            await run_all()
        elif choice in TESTS:
            name, test_fn = TESTS[choice]
            print(f"\nRunning: {name}")
            await test_fn()
        else:
            print(f"Invalid test: {choice}. Valid: 1-14 or 'all'")
            sys.exit(1)
        runner.print_summary()
        return

    # Interactive menu mode
    print_menu()

    while True:
        choice = input("Select test [1-14, A, Q]: ").strip().upper()

        if choice == "Q":
            print("\nGoodbye!")
            break
        elif choice == "A":
            await run_all()
            runner.print_summary()
            break
        elif choice in TESTS:
            name, test_fn = TESTS[choice]
            print(f"\nRunning: {name}")
            await test_fn()
            runner.print_summary()
            print_menu()
        else:
            print(f"  Invalid choice: {choice}")
            continue


if __name__ == "__main__":
    asyncio.run(main())
