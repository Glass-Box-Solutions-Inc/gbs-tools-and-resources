"""
Session management for the MerusCase CLI.

Handles:
  - Bearer token lifecycle (load from GCP Secret Manager or ~/.meruscase_token)
  - Undo/redo stack (50 levels, deep-copy snapshots)
  - CLI state (current case context, modified flag)
"""
from __future__ import annotations

import copy
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

TOKEN_FILE = Path.home() / ".meruscase_token"
GCP_PROJECT = "adjudica-internal"
GCP_SECRET_NAME = "qmeprep-meruscase-access-token"
MAX_UNDO = 50

# In-process cache so we only hit GCP/disk once per process lifetime.
_token_cache: Optional[str] = None
_gcp_available: Optional[bool] = None


def load_token() -> Optional[str]:
    """Load the MerusCase OAuth Bearer token.

    Priority:
      1. GCP Secret Manager (project: adjudica-internal,
         secret: qmeprep-meruscase-access-token)
      2. Environment variable MERUSCASE_ACCESS_TOKEN
      3. File ~/.meruscase_token

    Returns:
        Token string, or None if not found.
    """
    global _token_cache, _gcp_available

    # Return cached value if already loaded this process.
    if _token_cache is not None:
        return _token_cache

    # 1. GCP Secret Manager
    if _gcp_available is not False:
        try:
            from google.cloud import secretmanager

            client = secretmanager.SecretManagerServiceClient()
            resource = (
                f"projects/{GCP_PROJECT}/secrets/{GCP_SECRET_NAME}/versions/latest"
            )
            response = client.access_secret_version(request={"name": resource})
            value = response.payload.data.decode("UTF-8").strip()
            if value:
                _gcp_available = True
                _token_cache = value
                logger.debug("load_token: loaded from GCP Secret Manager")
                return _token_cache
        except ImportError:
            _gcp_available = False
            logger.debug(
                "load_token: google-cloud-secret-manager not installed, "
                "falling back to env/file"
            )
        except Exception:
            if _gcp_available is None:
                _gcp_available = False
            logger.debug(
                "load_token: GCP Secret Manager unavailable, "
                "falling back to env/file"
            )

    # 2. Environment variable
    env_token = os.environ.get("MERUSCASE_ACCESS_TOKEN", "").strip()
    if env_token:
        _token_cache = env_token
        logger.debug("load_token: loaded from MERUSCASE_ACCESS_TOKEN env var")
        return _token_cache

    # 3. File ~/.meruscase_token
    if TOKEN_FILE.exists():
        try:
            value = TOKEN_FILE.read_text().strip()
            if value:
                _token_cache = value
                logger.debug("load_token: loaded from %s", TOKEN_FILE)
                return _token_cache
        except OSError as exc:
            logger.debug("load_token: could not read %s: %s", TOKEN_FILE, exc)

    return None


def save_token(token: str) -> None:
    """Save a Bearer token to ~/.meruscase_token.

    The file is written with mode 0o600 (owner read/write only) so the
    token is not world-readable.

    Args:
        token: OAuth Bearer token string.
    """
    TOKEN_FILE.write_text(token)
    TOKEN_FILE.chmod(0o600)
    logger.debug("save_token: token written to %s", TOKEN_FILE)

    # Invalidate the in-process cache so the next load_token() call picks
    # up the freshly saved value.
    global _token_cache
    _token_cache = token


class MerusCaseSession:
    """Stateful session for the MerusCase CLI.

    Stores the current token, active case context, and undo/redo history.
    The session is serialised to a JSON file (default: ~/.meruscase_session.json).
    """

    DEFAULT_PATH = Path.home() / ".meruscase_session.json"

    def __init__(self):
        self._token: Optional[str] = None
        self._state: dict = {}
        self._undo_stack: list[dict] = []
        self._redo_stack: list[dict] = []
        self._modified: bool = False

    @classmethod
    def load(cls, path: Optional[str] = None) -> "MerusCaseSession":
        """Load session from JSON file, or return fresh session if file missing.

        Args:
            path: Path to session JSON. Defaults to ~/.meruscase_session.json.

        Returns:
            Populated MerusCaseSession, or a fresh one if the file is absent.
        """
        session_path = Path(path) if path else cls.DEFAULT_PATH

        session = cls()

        if not session_path.exists():
            logger.debug("load: session file not found at %s, using fresh session", session_path)
            return session

        try:
            data = json.loads(session_path.read_text())
            session._token = data.get("token") or None
            session._state = data.get("state", {})
            session._modified = False
            logger.debug("load: session loaded from %s", session_path)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(
                "load: could not read session file %s (%s), using fresh session",
                session_path,
                exc,
            )
            # Return a clean session rather than raising — the CLI should
            # continue even if the session file is corrupted.
            return cls()

        return session

    def save(self, path: Optional[str] = None) -> None:
        """Persist session state to JSON file.

        Args:
            path: Path to write. Defaults to ~/.meruscase_session.json.
        """
        session_path = Path(path) if path else self.DEFAULT_PATH

        # Ensure parent directory exists (e.g. custom paths under /tmp)
        session_path.parent.mkdir(parents=True, exist_ok=True)

        data: dict[str, Any] = {"state": self._state}
        if self._token is not None:
            data["token"] = self._token

        session_path.write_text(json.dumps(data, indent=2))
        session_path.chmod(0o600)
        self._modified = False
        logger.debug("save: session written to %s (mode 0o600)", session_path)

    def snapshot(self, description: str = "") -> None:
        """Push current state onto undo stack (max 50 levels).

        Call this BEFORE any mutating operation so the state can be restored.

        Args:
            description: Human-readable description of the operation (for undo message).
        """
        entry = {
            "state": copy.deepcopy(self._state),
            "description": description,
            "timestamp": datetime.now().isoformat(),
        }
        self._undo_stack.append(entry)

        # Trim to MAX_UNDO most recent entries
        if len(self._undo_stack) > MAX_UNDO:
            self._undo_stack = self._undo_stack[-MAX_UNDO:]

        # Any new operation clears the redo branch
        self._redo_stack.clear()
        self._modified = True
        logger.debug("snapshot: '%s' saved (%d on stack)", description, len(self._undo_stack))

    def undo(self) -> Optional[str]:
        """Pop the most recent snapshot and restore it.

        Returns:
            Description of the undone operation, or None if stack is empty.
        """
        if not self._undo_stack:
            logger.debug("undo: stack is empty")
            return None

        entry = self._undo_stack.pop()

        # Save current state onto the redo stack before overwriting
        self._redo_stack.append({
            "state": copy.deepcopy(self._state),
            "description": entry["description"],
            "timestamp": datetime.now().isoformat(),
        })

        self._state = entry["state"]
        self._modified = True
        logger.debug("undo: restored '%s'", entry["description"])
        return entry["description"]

    def redo(self) -> Optional[str]:
        """Re-apply the most recently undone operation.

        Returns:
            Description of the redone operation, or None if redo stack is empty.
        """
        if not self._redo_stack:
            logger.debug("redo: stack is empty")
            return None

        entry = self._redo_stack.pop()

        # Push current state back onto undo so the user can undo the redo
        self._undo_stack.append({
            "state": copy.deepcopy(self._state),
            "description": entry["description"],
            "timestamp": datetime.now().isoformat(),
        })
        if len(self._undo_stack) > MAX_UNDO:
            self._undo_stack = self._undo_stack[-MAX_UNDO:]

        self._state = entry["state"]
        self._modified = True
        logger.debug("redo: re-applied '%s'", entry["description"])
        return entry["description"]

    def get_token(self) -> str:
        """Return the current Bearer token, loading it if not already set.

        Raises:
            RuntimeError: If no token is available from any source.
        """
        if self._token:
            return self._token

        token = load_token()
        if not token:
            raise RuntimeError(
                "No MerusCase token found. Run: cli-anything-meruscase auth login"
            )

        self._token = token
        return self._token

    def set_token(self, token: str) -> None:
        """Set a new Bearer token in this session (does not persist to disk).

        Call save() afterwards if you want the token persisted to the session
        file, or use save_token() to write it to ~/.meruscase_token.

        Args:
            token: OAuth Bearer token string.
        """
        self._token = token
        self._modified = True

    @property
    def is_modified(self) -> bool:
        """True if there are unsaved changes."""
        return self._modified

    def get_client(self):
        """Return an initialised MerusCaseAPIClient for this session's token.

        Returns:
            MerusCaseAPIClient instance ready to make API calls.

        Raises:
            RuntimeError: If no token is available.
        """
        from cli_anything.meruscase.utils.api_client import MerusCaseAPIClient

        return MerusCaseAPIClient(access_token=self.get_token())
