"""
Spectacles Secrets Vault
Secure credential management via GCP Secret Manager

CRITICAL: Credentials are NEVER passed to LLM context.
Only accessed at browser action execution time.

Supports:
- Username/password credential injection
- API key retrieval
- Browser storage state (cookies, localStorage) for pre-authenticated sessions
"""

import logging
import asyncio
import json
from typing import Optional, Dict, Any
from playwright.async_api import Page, BrowserContext

logger = logging.getLogger(__name__)

# Lazy import for Google Cloud
_secretmanager = None


def _get_secretmanager():
    global _secretmanager
    if _secretmanager is None:
        from google.cloud import secretmanager
        _secretmanager = secretmanager
    return _secretmanager


class SecretsVault:
    """
    Secure credential management for browser automation.

    CRITICAL SECURITY:
    - Credentials are NEVER passed to LLM context
    - Only accessed at execution time by browser specialist
    - Values are injected directly into browser, never logged
    - Short-lived cache to minimize exposure
    """

    def __init__(self, project_id: str):
        """
        Initialize secrets vault.

        Args:
            project_id: GCP project ID
        """
        self.project_id = project_id
        self._client = None
        self._cache: Dict[str, str] = {}
        self._cache_ttl_seconds = 300  # 5 minutes

    @property
    def client(self):
        """Lazy-load Secret Manager client"""
        if self._client is None:
            secretmanager = _get_secretmanager()
            self._client = secretmanager.SecretManagerServiceClient()
        return self._client

    async def get_credential(
        self,
        credential_key: str,
        use_cache: bool = True
    ) -> Optional[str]:
        """
        Retrieve credential from GCP Secret Manager.

        SECURITY: Never returns value to LLM - only used by action executor.

        Args:
            credential_key: Secret name in Secret Manager
            use_cache: Whether to use cached value if available

        Returns:
            Credential value or None if not found
        """
        if use_cache and credential_key in self._cache:
            logger.debug("Using cached credential: %s", credential_key)
            return self._cache[credential_key]

        try:
            secret_name = f"projects/{self.project_id}/secrets/{credential_key}/versions/latest"

            response = await asyncio.to_thread(
                self.client.access_secret_version,
                request={"name": secret_name}
            )

            value = response.payload.data.decode("UTF-8")

            if use_cache:
                self._cache[credential_key] = value

            logger.info("Retrieved credential: %s", credential_key)
            return value

        except Exception as e:
            logger.error("Failed to get credential %s: %s", credential_key, e)
            return None

    async def inject_credentials(
        self,
        page: Page,
        credential_key: str,
        username_selector: str = "input[type='email'], input[name='username'], input[name='email']",
        password_selector: str = "input[type='password']"
    ) -> bool:
        """
        Inject credentials directly into browser form.

        Credentials are retrieved and injected without passing through LLM.

        Args:
            page: Playwright page
            credential_key: Base secret name (will look for {key}-username and {key}-password)
            username_selector: CSS selector for username field
            password_selector: CSS selector for password field

        Returns:
            True if injection successful
        """
        try:
            # Get credentials
            username = await self.get_credential(f"{credential_key}-username")
            password = await self.get_credential(f"{credential_key}-password")

            if not username or not password:
                logger.error("Missing credentials for %s", credential_key)
                return False

            # Find and fill fields
            username_field = page.locator(username_selector).first
            password_field = page.locator(password_selector).first

            await username_field.fill(username)
            await password_field.fill(password)

            logger.info("Credentials injected for %s", credential_key)
            return True

        except Exception as e:
            logger.error("Failed to inject credentials: %s", e)
            return False

    async def get_api_key(self, service_name: str) -> Optional[str]:
        """
        Get API key for a service.

        Args:
            service_name: Service name (e.g., "openai", "anthropic")

        Returns:
            API key or None
        """
        return await self.get_credential(f"{service_name}-api-key")

    def clear_cache(self):
        """Clear cached credentials (call on session end)"""
        self._cache.clear()
        logger.info("Credential cache cleared")

    async def check_secret_exists(self, credential_key: str) -> bool:
        """
        Check if a secret exists in Secret Manager.

        Args:
            credential_key: Secret name

        Returns:
            True if secret exists
        """
        try:
            secret_name = f"projects/{self.project_id}/secrets/{credential_key}"
            await asyncio.to_thread(
                self.client.get_secret,
                request={"name": secret_name}
            )
            return True
        except Exception:
            return False

    async def save_storage_state(self, credential_key: str, state: Dict[str, Any]) -> bool:
        """
        Save browser storage state to GCP Secret Manager.

        Creates or updates a secret with the serialized storage state,
        enabling pre-authenticated browser sessions to be shared across
        environments (local dev, production Cloud Run).

        Args:
            credential_key: Base secret name (will save as {key}-storage-state)
            state: Playwright storage state dict from context.storage_state()

        Returns:
            True if saved successfully
        """
        secret_id = f"{credential_key}-storage-state"
        state_json = json.dumps(state)

        try:
            parent = f"projects/{self.project_id}"
            secret_path = f"{parent}/secrets/{secret_id}"

            # Create secret if it doesn't exist
            if not await self.check_secret_exists(secret_id):
                logger.info("Creating new secret: %s", secret_id)
                await asyncio.to_thread(
                    self.client.create_secret,
                    request={
                        "parent": parent,
                        "secret_id": secret_id,
                        "secret": {"replication": {"automatic": {}}},
                    }
                )

            # Add new version with the state data
            await asyncio.to_thread(
                self.client.add_secret_version,
                request={
                    "parent": secret_path,
                    "payload": {"data": state_json.encode("UTF-8")},
                }
            )

            # Invalidate cache so next read gets fresh data
            self._cache.pop(secret_id, None)

            logger.info("Saved storage state for %s (%d cookies, %d bytes)",
                        credential_key, len(state.get("cookies", [])), len(state_json))
            return True

        except Exception as e:
            logger.error("Failed to save storage state for %s: %s", credential_key, e)
            return False

    async def get_storage_state(self, credential_key: str) -> Optional[Dict[str, Any]]:
        """
        Get browser storage state (cookies, localStorage) from Secret Manager.

        This enables pre-authenticated browser sessions for services like Google
        that block automated password logins.

        Storage state is a JSON blob saved from Playwright's context.storage_state().

        Args:
            credential_key: Base secret name (will look for {key}-storage-state)

        Returns:
            Storage state dict or None if not found
        """
        secret_name = f"{credential_key}-storage-state"
        state_json = await self.get_credential(secret_name)

        if not state_json:
            logger.warning("No storage state found for %s", credential_key)
            return None

        try:
            state = json.loads(state_json)
            logger.info("Retrieved storage state for %s (%d cookies)",
                       credential_key, len(state.get("cookies", [])))
            return state
        except json.JSONDecodeError as e:
            logger.error("Invalid storage state JSON for %s: %s", credential_key, e)
            return None

    async def apply_storage_state(
        self,
        context: BrowserContext,
        credential_key: str
    ) -> bool:
        """
        Apply storage state to a browser context for pre-authenticated sessions.

        This injects cookies and localStorage from a previously saved session,
        enabling automation of services that block password-based logins.

        Args:
            context: Playwright browser context
            credential_key: Base secret name (will look for {key}-storage-state)

        Returns:
            True if storage state applied successfully
        """
        state = await self.get_storage_state(credential_key)

        if not state:
            return False

        try:
            # Add cookies to context
            cookies = state.get("cookies", [])
            if cookies:
                await context.add_cookies(cookies)
                logger.info("Injected %d cookies for %s", len(cookies), credential_key)

            # localStorage is applied per-origin when pages navigate
            # Store it for later injection by pages
            origins = state.get("origins", [])
            if origins:
                # Store origins data on context for page-level injection
                context._spectacles_storage_origins = origins
                logger.info("Stored %d origins for localStorage injection", len(origins))

            logger.info("Storage state applied for %s", credential_key)
            return True

        except Exception as e:
            logger.error("Failed to apply storage state for %s: %s", credential_key, e)
            return False

    async def inject_local_storage(self, page: Page) -> bool:
        """
        Inject localStorage data for the current page origin.

        Call this after navigating to a page to apply localStorage from storage state.

        Args:
            page: Playwright page

        Returns:
            True if localStorage injected successfully
        """
        context = page.context

        # Check if we have stored origins from apply_storage_state
        origins = getattr(context, "_spectacles_storage_origins", None)
        if not origins:
            return True  # No localStorage to inject

        try:
            current_url = page.url
            for origin_data in origins:
                origin = origin_data.get("origin", "")
                if current_url.startswith(origin):
                    local_storage = origin_data.get("localStorage", [])
                    for item in local_storage:
                        await page.evaluate(
                            """([key, value]) => localStorage.setItem(key, value)""",
                            [item["name"], item["value"]]
                        )
                    logger.info("Injected %d localStorage items for %s",
                               len(local_storage), origin)
                    return True

            return True  # No matching origin, which is fine

        except Exception as e:
            logger.error("Failed to inject localStorage: %s", e)
            return False


# Singleton instance
_secrets_vault: Optional[SecretsVault] = None


def get_secrets_vault() -> Optional[SecretsVault]:
    """Get singleton SecretsVault instance"""
    global _secrets_vault

    if _secrets_vault is None:
        from api.config import settings
        if settings.GCP_PROJECT_ID:
            _secrets_vault = SecretsVault(settings.GCP_PROJECT_ID)
        else:
            logger.warning("GCP_PROJECT_ID not set - SecretsVault unavailable")

    return _secrets_vault
