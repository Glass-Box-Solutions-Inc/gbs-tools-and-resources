"""
Auth Capture Session - First-Class Spectacles Capability

Reusable module for capturing authenticated browser state from any service.
Connects to Browserless, opens a live browser session for manual login,
then captures cookies + localStorage and saves locally and/or to GCP Secret Manager.

Usage:
    async with AuthCaptureSession(service="google") as session:
        live_url = await session.start()
        # User logs in via live_url
        state = await session.capture()
        results = await session.save(local_dir=".auth", gcp_project="glassbox-spectacles")
        verified = await session.verify()

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from urllib.parse import urlparse

from playwright.async_api import async_playwright, Page, BrowserContext, Browser, Playwright

logger = logging.getLogger(__name__)

# Well-known service presets for auth capture.
# Each entry: (login_url, verify_url, description)
AUTH_PRESETS: Dict[str, Tuple[str, str, str]] = {
    "google": (
        "https://accounts.google.com/signin",
        "https://drive.google.com",
        "Google (Drive, Gmail, etc.)",
    ),
    "github": (
        "https://github.com/login",
        "https://github.com",
        "GitHub",
    ),
    "meruscase": (
        "https://app.meruscase.com/login",
        "https://app.meruscase.com",
        "MerusCase",
    ),
    "westlaw": (
        "https://1.next.westlaw.com/",
        "https://1.next.westlaw.com/",
        "Westlaw",
    ),
}

# Defaults
_DEFAULT_BROWSERLESS_WSS = "wss://production-sfo.browserless.io"
_DEFAULT_TIMEOUT_MS = 600_000


class AuthCaptureSession:
    """
    Interactive auth capture session.

    Opens a Browserless live browser session, navigates to a login page,
    and waits for the user to complete authentication. Once signaled,
    captures cookies + localStorage and saves locally and/or to GCP Secret Manager.
    """

    def __init__(
        self,
        service: str,
        login_url: Optional[str] = None,
        verify_url: Optional[str] = None,
        credential_key: Optional[str] = None,
        browserless_token: Optional[str] = None,
        browserless_wss: Optional[str] = None,
        timeout_ms: int = _DEFAULT_TIMEOUT_MS,
    ):
        """
        Initialize an auth capture session.

        Args:
            service: Service name or preset key (google, github, meruscase, westlaw).
            login_url: Login page URL. If service is a preset, defaults to preset URL.
            verify_url: URL to navigate after capture to verify auth succeeded.
            credential_key: Secret Manager key. Defaults to "{service}-auth".
            browserless_token: Browserless API token. Defaults to env var.
            browserless_wss: Browserless WebSocket URL. Defaults to production SFO.
            timeout_ms: Live session timeout in milliseconds.
        """
        # Resolve preset if applicable
        if service in AUTH_PRESETS and not login_url:
            preset_login, preset_verify, _ = AUTH_PRESETS[service]
            login_url = login_url or preset_login
            verify_url = verify_url or preset_verify

        if not login_url:
            raise ValueError(
                f"login_url is required (service '{service}' is not a known preset)"
            )

        self.service = service
        self.login_url = login_url
        self.verify_url = verify_url
        self.credential_key = credential_key or f"{service}-auth"
        self.browserless_token = browserless_token or os.environ.get(
            "BROWSERLESS_API_TOKEN", ""
        )
        self.browserless_wss = browserless_wss or _DEFAULT_BROWSERLESS_WSS
        self.timeout_ms = timeout_ms

        # Internal state
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._live_url: Optional[str] = None
        self._captured_state: Optional[Dict[str, Any]] = None
        self._status: str = "initialized"

    @property
    def live_url(self) -> Optional[str]:
        return self._live_url

    @property
    def status(self) -> str:
        return self._status

    @property
    def page(self) -> Optional[Page]:
        return self._page

    @property
    def context(self) -> Optional[BrowserContext]:
        return self._context

    async def start(self) -> str:
        """
        Connect to Browserless, navigate to login_url, return live_url.

        Returns:
            The Browserless live URL for observing/controlling the browser.

        Raises:
            RuntimeError: If connection fails.
        """
        if not self.browserless_token:
            raise RuntimeError(
                "No Browserless token provided. Set BROWSERLESS_API_TOKEN env var "
                "or pass browserless_token to constructor."
            )

        self._playwright = await async_playwright().__aenter__()
        ws_url = f"{self.browserless_wss}?token={self.browserless_token}&stealth=true"
        self._browser = await self._playwright.chromium.connect_over_cdp(ws_url)

        self._context = self._browser.contexts[0]
        self._page = (
            self._context.pages[0]
            if self._context.pages
            else await self._context.new_page()
        )

        # Get live URL via CDP
        cdp = await self._context.new_cdp_session(self._page)
        result = await cdp.send("Browserless.liveURL", {
            "timeout": self.timeout_ms,
        })
        self._live_url = result.get("liveURL", "")

        # Navigate to login page
        logger.info("Navigating to %s", self.login_url)
        await self._page.goto(
            self.login_url, wait_until="domcontentloaded", timeout=30000
        )

        self._status = "awaiting_login"
        logger.info("Auth capture session started for %s", self.service)
        return self._live_url

    async def capture(self) -> Dict[str, Any]:
        """
        Capture storage state (cookies + localStorage) from the browser context.

        Returns:
            Playwright storage state dict with 'cookies' and 'origins' keys.

        Raises:
            RuntimeError: If session not started.
        """
        if not self._context:
            raise RuntimeError("Session not started. Call start() first.")

        self._captured_state = await self._context.storage_state()
        cookie_count = len(self._captured_state.get("cookies", []))
        origin_count = len(self._captured_state.get("origins", []))
        logger.info(
            "Captured state for %s: %d cookies, %d origins",
            self.service,
            cookie_count,
            origin_count,
        )
        self._status = "captured"
        return self._captured_state

    async def save(
        self,
        local_dir: Optional[str] = None,
        gcp_project: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Save captured state locally and/or to GCP Secret Manager.

        Args:
            local_dir: Directory path to save JSON file. None to skip local save.
            gcp_project: GCP project ID for Secret Manager. None to skip GCP save.

        Returns:
            Dict with save results: local_path, gcp_saved, secret_name, cookie_count, origin_count.

        Raises:
            RuntimeError: If capture() hasn't been called.
        """
        if not self._captured_state:
            raise RuntimeError("No state captured. Call capture() first.")

        results: Dict[str, Any] = {
            "local_path": None,
            "gcp_saved": False,
            "secret_name": f"{self.credential_key}-storage-state",
            "cookie_count": len(self._captured_state.get("cookies", [])),
            "origin_count": len(self._captured_state.get("origins", [])),
        }

        # Save locally
        if local_dir:
            dir_path = Path(local_dir)
            dir_path.mkdir(parents=True, exist_ok=True)
            local_path = dir_path / f"{self.credential_key}.json"
            with open(local_path, "w") as f:
                json.dump(self._captured_state, f, indent=2)
            results["local_path"] = str(local_path)
            logger.info("Saved locally: %s", local_path)

        # Save to GCP Secret Manager
        if gcp_project:
            try:
                from security.secrets_vault import SecretsVault

                vault = SecretsVault(project_id=gcp_project)
                saved = await vault.save_storage_state(
                    self.credential_key, self._captured_state
                )
                results["gcp_saved"] = saved
                if saved:
                    logger.info(
                        "Saved to Secret Manager: %s",
                        results["secret_name"],
                    )
                else:
                    logger.warning("Failed to save to Secret Manager")
            except Exception as e:
                logger.error("Secret Manager save failed: %s", e)
                results["gcp_saved"] = False

        self._status = "saved"
        return results

    async def verify(self) -> bool:
        """
        Navigate to verify_url and confirm no redirect back to login.

        Returns:
            True if verification passed (stayed on verify domain),
            False if redirected to login or no verify_url set.
        """
        if not self.verify_url:
            logger.info("No verify_url set, skipping verification")
            return True

        if not self._page:
            raise RuntimeError("Session not started. Call start() first.")

        logger.info("Verifying auth by navigating to %s", self.verify_url)
        await self._page.goto(
            self.verify_url, wait_until="domcontentloaded", timeout=30000
        )
        # Allow page to settle
        await self._page.wait_for_timeout(3000)

        current_url = self._page.url
        login_host = urlparse(self.login_url).hostname
        current_host = urlparse(current_url).hostname
        verify_host = urlparse(self.verify_url).hostname

        if current_host == login_host and current_host != verify_host:
            logger.warning(
                "Auth verification failed: redirected to %s", current_url
            )
            self._status = "verification_failed"
            return False

        logger.info("Auth verification passed: %s", current_url)
        self._status = "verified"
        return True

    async def close(self):
        """Clean up browser and Playwright resources."""
        try:
            if self._browser:
                await self._browser.close()
        except Exception:
            pass
        try:
            if self._playwright:
                await self._playwright.__aexit__(None, None, None)
        except Exception:
            pass
        self._status = "closed"
        logger.info("Auth capture session closed for %s", self.service)

    # Context manager support
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


def resolve_auth_params(
    service: Optional[str] = None,
    login_url: Optional[str] = None,
    verify_url: Optional[str] = None,
    interactive: bool = True,
) -> Tuple[str, str, Optional[str]]:
    """
    Resolve service name, login URL, and verify URL for auth capture.

    Sources (highest priority first):
      1. Explicit arguments (service, login_url, verify_url)
      2. Interactive prompts (shows presets + custom option) when interactive=True

    Args:
        service: Service preset name or custom name.
        login_url: Override login URL.
        verify_url: Override verify URL.
        interactive: If True, prompt user when params are missing.

    Returns:
        (service_name, login_url, verify_url_or_None)
    """
    # Resolve from preset if service given without explicit URLs
    if service and service in AUTH_PRESETS and not login_url:
        preset_login, preset_verify, _ = AUTH_PRESETS[service]
        login_url = login_url or preset_login
        verify_url = verify_url or preset_verify

    if login_url:
        service = service or "custom"
        return service, login_url, verify_url

    if not interactive:
        # Default to google when non-interactive
        login, verify, _ = AUTH_PRESETS["google"]
        return "google", login, verify

    # Interactive: show presets
    print("\n  Available service presets:")
    preset_keys = list(AUTH_PRESETS.keys())
    for i, key in enumerate(preset_keys, 1):
        _, _, desc = AUTH_PRESETS[key]
        print(f"    [{i}] {desc}  ({key})")
    print(f"    [C] Custom URL")

    choice = input(f"\n  Select service [1-{len(preset_keys)}, C]: ").strip().upper()

    if choice == "C":
        service = input("  Service name (e.g. myapp): ").strip() or "custom"
        login_url = input("  Login URL: ").strip()
        verify_url = input("  Verify URL (blank to skip): ").strip() or None
        return service, login_url, verify_url

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(preset_keys):
            key = preset_keys[idx]
            login, verify, _ = AUTH_PRESETS[key]
            return key, login, verify
    except ValueError:
        pass

    # Default to google on bad input
    print("  Invalid choice, defaulting to Google.")
    login, verify, _ = AUTH_PRESETS["google"]
    return "google", login, verify
