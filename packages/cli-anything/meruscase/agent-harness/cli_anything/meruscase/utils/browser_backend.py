"""
Playwright-based browser automation for MerusCase operations that have no REST API:
  - OAuth login (username + password form)
  - New case creation (form at /cms#/caseFiles/add)

Credentials are loaded from GCP Secret Manager first, env vars second.
Browserless cloud browser is used for case creation — no local `playwright install chromium`
required for MerusCase operations. Browserless bypasses MerusCase's reCAPTCHA protection
that blocks standard headless Chromium sessions.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import date
from typing import Optional

logger = logging.getLogger(__name__)

MERUSCASE_LOGIN_URL = "https://meruscase.com/users/login"
MERUSCASE_NEW_CASE_URL = "https://meruscase.com/cms#/caseFiles/add?t=1&lpt=0&nr=1&lpa=0"

# GCP project that holds MerusCase secrets
_GCP_PROJECT = "adjudica-internal"

# In-process secret cache to avoid repeated GCP calls within the same session.
_secret_cache: dict[str, str] = {}
_gcp_available: bool | None = None


def _get_secret(secret_name: str, fallback_env_var: str = "", project: str = "") -> str:
    """Retrieve a secret from GCP Secret Manager with env-var fallback.

    Priority: GCP Secret Manager → environment variable.
    Results are cached in-memory for the process lifetime.

    Args:
        secret_name: Name of the secret in GCP Secret Manager.
        fallback_env_var: Environment variable name to use when GCP is unavailable.
        project: GCP project ID. Defaults to _GCP_PROJECT if not provided.

    Returns:
        Secret value string, or empty string if neither source has it.
    """
    global _gcp_available

    gcp_project = project or _GCP_PROJECT
    cache_key = f"{gcp_project}/{secret_name}"
    if cache_key in _secret_cache:
        return _secret_cache[cache_key]

    if _gcp_available is not False:
        try:
            from google.cloud import secretmanager

            client = secretmanager.SecretManagerServiceClient()
            resource = f"projects/{gcp_project}/secrets/{secret_name}/versions/latest"
            response = client.access_secret_version(request={"name": resource})
            value = response.payload.data.decode("UTF-8")
            _secret_cache[cache_key] = value
            _gcp_available = True
            return value
        except ImportError:
            _gcp_available = False
            logger.debug("google-cloud-secret-manager not installed, using env fallback")
        except Exception:
            if _gcp_available is None:
                _gcp_available = False
                logger.debug("GCP Secret Manager unavailable, using env fallback")

    # Fallback: environment variable
    value = os.getenv(fallback_env_var, "") if fallback_env_var else ""
    _secret_cache[cache_key] = value
    return value


async def get_browserless_token() -> str:
    """Load Browserless API token from GCP Secret Manager or env var.

    Priority:
      1. GCP Secret Manager (project: adjudica-internal, secret: merus-expert-browserless-token)
      2. GCP Secret Manager (project: ousd-campaign, secret: spectacles-browserless-token)
      3. Environment variable BROWSERLESS_API_TOKEN

    The primary secret lives in adjudica-internal alongside the MerusCase credentials.
    The ousd-campaign fallback is shared with the spectacles service.

    Returns:
        Browserless API token string.

    Raises:
        RuntimeError: If token not found in any source.
    """
    # Primary: adjudica-internal (merus-expert project)
    token = _get_secret(
        "merus-expert-browserless-token",
        project="adjudica-internal",
        fallback_env_var="BROWSERLESS_API_TOKEN",
    )
    if token:
        return token

    # Fallback: spectacles-browserless-token in ousd-campaign (same Browserless account,
    # stored under a different project for the Spectacles service).
    token = _get_secret("spectacles-browserless-token", project="ousd-campaign")

    if not token:
        raise RuntimeError(
            "Browserless API token not found. "
            "Set BROWSERLESS_API_TOKEN or configure GCP Secret Manager "
            "(project: adjudica-internal, secret: merus-expert-browserless-token)."
        )

    return token


async def get_credentials() -> tuple[str, str]:
    """Load MerusCase email + password.

    Priority:
      1. GCP Secret Manager (project: adjudica-production,
         secrets: meruscase-email, meruscase-password)
      2. GCP Secret Manager (project: adjudica-internal,
         secrets: merus-expert-meruscase-email, merus-expert-meruscase-password)
      3. Environment variables MERUSCASE_EMAIL, MERUSCASE_PASSWORD

    The adjudica-production secrets are canonical (same project used by
    merus-test-data-generator). The adjudica-internal secrets are kept as a
    fallback for dev environments. The env var fallback is tried only when
    both GCP lookups fail.

    Returns:
        (email, password) tuple.

    Raises:
        RuntimeError: If credentials cannot be found.
    """
    # Primary: adjudica-production (canonical MerusCase credentials)
    email = _get_secret("meruscase-email", project="adjudica-production")
    password = _get_secret("meruscase-password", project="adjudica-production")

    # Fallback: adjudica-internal (merus-expert project credentials)
    if not email:
        email = _get_secret(
            "merus-expert-meruscase-email",
            project="adjudica-internal",
            fallback_env_var="MERUSCASE_EMAIL",
        )
    if not password:
        password = _get_secret(
            "merus-expert-meruscase-password",
            project="adjudica-internal",
            fallback_env_var="MERUSCASE_PASSWORD",
        )

    if not email or not password:
        raise RuntimeError(
            "MerusCase credentials not found. "
            "Set MERUSCASE_EMAIL/PASSWORD or configure GCP Secret Manager."
        )

    return email, password


async def login(page, email: str, password: str) -> bool:
    """Navigate to MerusCase login page and authenticate.

    Uses the form selectors confirmed to work from the merus-expert reference
    implementation (matter_builder.py / form_filler.py).

    Args:
        page: Playwright Page object.
        email: MerusCase account email.
        password: MerusCase account password.

    Returns:
        True if login succeeded.

    Raises:
        RuntimeError: If login fails.
    """
    logger.info("Navigating to MerusCase login page")
    await page.goto(MERUSCASE_LOGIN_URL)
    await page.wait_for_load_state("networkidle")

    # Fill username — MerusCase login form uses name="data[User][username]"
    # (confirmed from live page inspection: field type is "text", not "email",
    # and the name attr is "username" not "email")
    email_selector = "input[name='data[User][username]'], input[name='data[User][email]'], input[type='email']"
    email_field = page.locator(email_selector).first
    await email_field.fill(email)
    logger.debug("Email/username field populated")

    # Fill password
    password_field = page.locator("input[type='password']").first
    await password_field.fill(password)
    logger.debug("Password field populated")

    # Click "Sign In" button — try text first, fall back to submit
    sign_in_button = page.locator(
        "button[type='submit'], input[type='submit']"
    ).first
    await sign_in_button.click()

    # Wait for navigation to complete after login
    await page.wait_for_load_state("networkidle", timeout=30000)

    # Verify logged-in state: MerusCase redirects to /cms or /dashboard on
    # successful login.  If the URL still contains "/users/login" we failed.
    current_url = page.url
    if "/users/login" in current_url:
        # Check for CAPTCHA — headless browsers may be blocked by reCAPTCHA
        page_content = await page.content()
        if "recaptcha" in page_content.lower() or "g-recaptcha" in page_content.lower():
            raise RuntimeError(
                "MerusCase login blocked by reCAPTCHA even through Browserless. "
                "Verify that the Browserless token is valid and the account IP "
                "is not flagged. Check the BROWSERLESS_API_TOKEN / "
                "spectacles-browserless-token secret."
            )
        logger.error("Login verification failed. Current URL: %s", current_url)
        raise RuntimeError(
            f"MerusCase login failed — credentials rejected or form changed. "
            f"Current URL: {current_url}"
        )

    logger.info("MerusCase login successful. URL: %s", current_url)
    return True


async def create_case(
    party_name: str,
    case_type: str = "Workers Compensation",
    date_opened: Optional[str] = None,
) -> dict:
    """Create a new case in MerusCase via browser automation.

    Launches a headless Chromium browser, logs in, navigates to the new case
    form, fills it, submits, and extracts the new case ID from the redirect URL.

    Args:
        party_name: Primary party name in "LASTNAME, FIRSTNAME" format.
        case_type: Case type string (default "Workers Compensation").
        date_opened: Date opened in MM/DD/YYYY format. Defaults to today.

    Returns:
        dict with keys: meruscase_id (int), url (str), party_name (str).

    Raises:
        RuntimeError: If case creation fails.
    """
    from playwright.async_api import async_playwright

    if date_opened is None:
        date_opened = date.today().strftime("%m/%d/%Y")

    email, password = await get_credentials()
    browserless_token = await get_browserless_token()

    # Build the Browserless WebSocket URL — same format used across GBS projects
    # (merus-test-data-generator/batch_create_cases.py, merus-expert/browser/client.py).
    ws_url = f"wss://production-sfo.browserless.io?token={browserless_token}"

    async with async_playwright() as p:
        logger.info("Connecting to Browserless cloud browser...")
        # Token is passed in the WebSocket URL query string (?token=...).
        # Do NOT pass an Authorization header — Browserless ignores it and
        # Playwright's connect_over_cdp will strip the query string if headers
        # are supplied, causing the connection to route to the bare base URL
        # and receive a 401/500 from Browserless.
        browser = await p.chromium.connect_over_cdp(ws_url, timeout=60000)
        logger.info("Browserless connection established")

        # Use a realistic viewport and user-agent to avoid bot detection,
        # matching the pattern in merus-expert/browser/client.py.
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()

        try:
            # Step 1: Authenticate
            await login(page, email, password)

            # Step 2: Navigate to new case form
            logger.info("Navigating to new case form: %s", MERUSCASE_NEW_CASE_URL)
            await page.goto(MERUSCASE_NEW_CASE_URL)
            await page.wait_for_load_state("networkidle")

            # Give the Angular SPA a moment to render the form
            await asyncio.sleep(2)

            # Step 3: Fill party name fields.
            # MerusCase uses separate Last Name / First Name fields; the party_name
            # is expected in "LASTNAME, FIRSTNAME" format.
            if "," in party_name:
                last_name, _, first_name = party_name.partition(",")
                last_name = last_name.strip()
                first_name = first_name.strip()
            else:
                parts = party_name.strip().split()
                last_name = parts[0] if parts else party_name
                first_name = " ".join(parts[1:]) if len(parts) > 1 else ""

            last_name_field = page.locator("input[name='data[Contact][last_name]']")
            if await last_name_field.is_visible():
                await last_name_field.fill(last_name)
                await last_name_field.dispatch_event("blur")
                logger.debug("Filled Last Name: %s", last_name)
            else:
                raise RuntimeError("Could not find Last Name field on new case form")

            first_name_field = page.locator("input[name='data[Contact][first_name]']")
            if await first_name_field.is_visible():
                await first_name_field.fill(first_name)
                await first_name_field.dispatch_event("blur")
                logger.debug("Filled First Name: %s", first_name)
            else:
                logger.warning("First Name field not visible; skipping")

            # Wait for conflict-check spinner to clear (if any)
            try:
                await page.wait_for_selector(
                    ".loading, .spinner, [data-loading='true']",
                    state="hidden",
                    timeout=15000,
                )
            except Exception:
                pass  # Spinner may not appear; safe to continue
            await asyncio.sleep(1)

            # Step 4: Select case type dropdown
            case_type_select = page.locator("select[name='data[CaseFile][case_type_id]']")
            if await case_type_select.is_visible():
                try:
                    await case_type_select.select_option(label=case_type)
                    logger.debug("Selected case type: %s", case_type)
                except Exception as exc:
                    logger.warning("Could not select case type '%s': %s", case_type, exc)

            # Step 5: Fill date opened
            date_field = page.locator(
                "input[name='data[CaseFile][date_opened]'], "
                "input[placeholder*='Date'], input[id*='date']"
            ).first
            if await date_field.is_visible():
                await date_field.fill(date_opened)
                await date_field.dispatch_event("blur")
                logger.debug("Filled Date Opened: %s", date_opened)
            else:
                logger.warning("Date Opened field not visible; skipping")

            # Step 6: Submit the form
            submit_button = page.locator(
                "button:has-text('Save'), button[type='submit'], "
                "input[type='submit'], button:has-text('Create')"
            ).first
            await submit_button.click()

            # Wait for redirect after form submission
            await page.wait_for_load_state("networkidle", timeout=30000)
            await asyncio.sleep(2)

            # Step 7: Extract case ID from resulting URL
            final_url = page.url
            logger.info("Post-submit URL: %s", final_url)

            # MerusCase redirects to a hash-based Angular route like:
            # https://meruscase.com/cms#/caseFiles/56171871
            match = re.search(r"caseFiles/(?:view/)?(\d+)", final_url)
            if not match:
                raise RuntimeError(
                    f"Case creation: could not extract case ID from URL: {final_url}"
                )

            case_id = int(match.group(1))
            logger.info("Case created successfully. MerusCase ID: %d", case_id)

            return {
                "meruscase_id": case_id,
                "url": final_url,
                "party_name": party_name,
            }

        finally:
            await browser.close()
