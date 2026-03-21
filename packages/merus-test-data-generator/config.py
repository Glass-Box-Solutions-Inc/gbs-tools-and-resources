"""
Configuration module — loads secrets from GCP Secret Manager with .env fallback.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import logging
import os
import warnings
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Paths
PROJECT_ROOT = Path(__file__).parent
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", PROJECT_ROOT / "output"))
LOG_DIR = Path(os.getenv("LOG_DIR", PROJECT_ROOT / "logs"))
DB_PATH = Path(os.getenv("DB_PATH", PROJECT_ROOT / "progress.db"))

# Audit config
AUDIT_DB_PATH = Path(os.getenv("AUDIT_DB_PATH", PROJECT_ROOT / "audit.db"))
AUDIT_HMAC_KEY = os.getenv("AUDIT_HMAC_KEY", "")

# --- GCP Secret Manager integration ---

_secret_cache: dict[str, str] = {}
_gcp_available: bool | None = None


def _get_secret(
    secret_name: str,
    project: str,
    fallback_env_var: str = "",
    fallback_default: str = "",
) -> str:
    """Retrieve a secret from GCP Secret Manager with env var fallback.

    Priority: GCP Secret Manager → env var → fallback_default.
    Results are cached in-memory for the process lifetime.
    """
    global _gcp_available

    cache_key = f"{project}/{secret_name}"
    if cache_key in _secret_cache:
        return _secret_cache[cache_key]

    # Try GCP Secret Manager
    if _gcp_available is not False:
        try:
            from google.cloud import secretmanager

            client = secretmanager.SecretManagerServiceClient()
            resource = f"projects/{project}/secrets/{secret_name}/versions/latest"
            response = client.access_secret_version(request={"name": resource})
            value = response.payload.data.decode("UTF-8")
            _secret_cache[cache_key] = value
            _gcp_available = True
            return value
        except ImportError:
            _gcp_available = False
            logging.getLogger(__name__).debug(
                "google-cloud-secret-manager not installed, using env fallback"
            )
        except Exception:
            if _gcp_available is None:
                _gcp_available = False
                logging.getLogger(__name__).debug(
                    "GCP Secret Manager unavailable, using env fallback"
                )

    # Fallback to env var
    value = os.getenv(fallback_env_var, fallback_default) if fallback_env_var else fallback_default
    _secret_cache[cache_key] = value
    return value


# MerusCase credentials (GCP Secret Manager → .env fallback)
MERUSCASE_EMAIL = _get_secret(
    "meruscase-email", "adjudica-production",
    fallback_env_var="MERUSCASE_EMAIL",
)
MERUSCASE_PASSWORD = _get_secret(
    "meruscase-password", "adjudica-production",
    fallback_env_var="MERUSCASE_PASSWORD",
)
BROWSERLESS_API_TOKEN = _get_secret(
    "spectacles-browserless-token", "ousd-campaign",
    fallback_env_var="BROWSERLESS_API_TOKEN",
)
MERUSCASE_CLIENT_ID = _get_secret(
    "MERUSCASE_CLIENT_ID", "adjudica-production",
    fallback_env_var="MERUSCASE_CLIENT_ID",
)
MERUSCASE_CLIENT_SECRET = _get_secret(
    "MERUSCASE_CLIENT_SECRET", "adjudica-production",
    fallback_env_var="MERUSCASE_CLIENT_SECRET",
)

# Merus-expert path (sibling project)
MERUS_EXPERT_PATH = PROJECT_ROOT.parent / "merus-expert"

# Access token — GCP first, env var, then legacy .meruscase_token file
MERUSCASE_ACCESS_TOKEN = _get_secret(
    "qmeprep-meruscase-access-token", "adjudica-production",
    fallback_env_var="MERUSCASE_ACCESS_TOKEN",
)
if not MERUSCASE_ACCESS_TOKEN:
    _token_file = MERUS_EXPERT_PATH / ".meruscase_token"
    if _token_file.exists():
        warnings.warn(
            "Reading access token from .meruscase_token is deprecated. "
            "Store it in GCP Secret Manager or MERUSCASE_ACCESS_TOKEN env var.",
            DeprecationWarning,
            stacklevel=1,
        )
        MERUSCASE_ACCESS_TOKEN = _token_file.read_text().strip()

# Generation settings
RANDOM_SEED = 42
TOTAL_CASES = 20
DEFAULT_CASE_COUNT = 20
MIN_CASE_COUNT = 1
MAX_CASE_COUNT = 500

# Default stage distribution (proportions, will be normalized)
DEFAULT_STAGE_DISTRIBUTION = {
    "intake": 0.15,
    "active_treatment": 0.25,
    "discovery": 0.20,
    "medical_legal": 0.15,
    "settlement": 0.15,
    "resolved": 0.10,
}

# Upload settings
UPLOAD_DELAY_SECONDS = 0.5
UPLOAD_MAX_RETRIES = 3
UPLOAD_BACKOFF_BASE = 2.0

# Browser automation settings
CASE_CREATION_MAX_RETRIES = 3
CASE_CREATION_TIMEOUT_SECONDS = 120

# Ensure output dirs exist
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)
