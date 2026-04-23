"""
GCP Secret Manager client with environment variable fallback.

In tests, set ADJUDICLAIMS_EMAIL and ADJUDICLAIMS_PASSWORD as env vars — no live
GCP calls are made.  In production (Cloud Run), secrets are fetched from
Secret Manager when the env vars are absent.

Secret names:
  adjudiclaims-seed-email     → ADJUDICLAIMS_EMAIL
  adjudiclaims-seed-password  → ADJUDICLAIMS_PASSWORD
  adjudiclaims-staging-url    → ADJUDICLAIMS_URL

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import os
from typing import Optional


def _fetch_from_secret_manager(secret_name: str, project_id: str) -> str:
    """
    Retrieve the latest version of a GCP secret.

    Raises RuntimeError if the google-cloud-secret-manager package is not
    installed or the secret cannot be accessed.
    """
    try:
        from google.cloud import secretmanager  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError(
            "google-cloud-secret-manager is not installed. "
            "Install it with: pip install google-cloud-secret-manager"
        ) from exc

    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("utf-8").strip()


def get_secret(
    secret_name: str,
    env_var: str,
    project_id: Optional[str] = None,
) -> str:
    """
    Return a secret value, preferring the environment variable.

    Resolution order:
      1. ``os.environ[env_var]`` — used in tests and local dev
      2. GCP Secret Manager (``secret_name``, ``project_id``)

    Args:
        secret_name: GCP secret resource name (e.g. ``adjudiclaims-seed-email``)
        env_var:     Environment variable to check first
        project_id:  GCP project ID — defaults to the ``GCP_PROJECT`` env var

    Returns:
        The secret string value

    Raises:
        RuntimeError: When no env var is set and Secret Manager lookup fails
        ValueError:   When project_id cannot be determined
    """
    value = os.environ.get(env_var)
    if value:
        return value

    resolved_project = project_id or os.environ.get("GCP_PROJECT")
    if not resolved_project:
        raise ValueError(
            f"Secret '{secret_name}' not in env var '{env_var}' and "
            "GCP_PROJECT is not set — cannot resolve from Secret Manager."
        )

    return _fetch_from_secret_manager(secret_name, resolved_project)


# ---------------------------------------------------------------------------
# Convenience accessors for AdjudiCLAIMS seed credentials
# ---------------------------------------------------------------------------


def get_adjudiclaims_email(project_id: Optional[str] = None) -> str:
    """Return the AdjudiCLAIMS seed account email."""
    return get_secret(
        secret_name="adjudiclaims-seed-email",
        env_var="ADJUDICLAIMS_EMAIL",
        project_id=project_id,
    )


def get_adjudiclaims_password(project_id: Optional[str] = None) -> str:
    """Return the AdjudiCLAIMS seed account password."""
    return get_secret(
        secret_name="adjudiclaims-seed-password",
        env_var="ADJUDICLAIMS_PASSWORD",
        project_id=project_id,
    )


def get_adjudiclaims_url(project_id: Optional[str] = None) -> str:
    """Return the AdjudiCLAIMS base URL (e.g. https://staging.adjudiclaims.com)."""
    return get_secret(
        secret_name="adjudiclaims-staging-url",
        env_var="ADJUDICLAIMS_URL",
        project_id=project_id,
    )
