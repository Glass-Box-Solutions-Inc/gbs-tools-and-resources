"""
End-to-end tests for cli-anything-meruscase.
Uses subprocess invocation of the CLI.

No-credentials tests (TestCLIInvocation, TestCLIAuthStatus) run in CI with zero setup.
Integration tests (TestIntegration) require MERUSCASE_ACCESS_TOKEN and are marked
`integration` so they can be excluded: pytest -m "not integration".
"""
import json
import os
import shutil
import subprocess
import sys
import pytest


def _resolve_cli(name: str) -> list[str]:
    """Resolve CLI command: installed binary → python -m fallback."""
    path = shutil.which(name)
    if path:
        return [path]
    if os.environ.get("CLI_ANYTHING_FORCE_INSTALLED", "").strip() == "1":
        raise RuntimeError(f"CLI not found. Install with: pip install -e .")
    module = name.replace("cli-anything-", "").replace("-", "_")
    return [sys.executable, "-m", f"cli_anything.{module}"]


CLI_BASE = _resolve_cli("cli-anything-meruscase")


# ── TestCLIInvocation ─────────────────────────────────────────────────────────


class TestCLIInvocation:
    """Tests that the CLI invokes cleanly — no credentials needed."""

    def test_help_exits_zero(self):
        """Root --help exits 0 and mentions MerusCase."""
        result = subprocess.run(CLI_BASE + ["--help"], capture_output=True, text=True)
        assert result.returncode == 0
        assert "MerusCase" in result.stdout or "meruscase" in result.stdout.lower()

    def test_case_help(self):
        """case --help exits 0 and lists expected subcommands."""
        result = subprocess.run(CLI_BASE + ["case", "--help"], capture_output=True, text=True)
        assert result.returncode == 0
        assert "list" in result.stdout
        assert "find" in result.stdout
        assert "get" in result.stdout
        assert "create" in result.stdout

    def test_billing_help(self):
        """billing --help exits 0 and lists expected subcommands."""
        result = subprocess.run(CLI_BASE + ["billing", "--help"], capture_output=True, text=True)
        assert result.returncode == 0
        assert "bill-time" in result.stdout
        assert "add-cost" in result.stdout

    def test_json_flag_on_help(self):
        """--json flag is accepted at root level without error."""
        result = subprocess.run(CLI_BASE + ["--json", "--help"], capture_output=True, text=True)
        assert result.returncode == 0

    def test_auth_help(self):
        """auth --help exits 0 and lists login and status."""
        result = subprocess.run(CLI_BASE + ["auth", "--help"], capture_output=True, text=True)
        assert result.returncode == 0
        assert "login" in result.stdout
        assert "status" in result.stdout

    def test_session_help(self):
        """session --help exits 0."""
        result = subprocess.run(CLI_BASE + ["session", "--help"], capture_output=True, text=True)
        assert result.returncode == 0

    def test_document_help(self):
        """document --help exits 0 and lists upload and list."""
        result = subprocess.run(CLI_BASE + ["document", "--help"], capture_output=True, text=True)
        assert result.returncode == 0
        assert "upload" in result.stdout
        assert "list" in result.stdout

    def test_party_help(self):
        """party --help exits 0."""
        result = subprocess.run(CLI_BASE + ["party", "--help"], capture_output=True, text=True)
        assert result.returncode == 0

    def test_resolve_cli_finds_command(self):
        """_resolve_cli returns a non-empty list."""
        cmd = _resolve_cli("cli-anything-meruscase")
        assert isinstance(cmd, list)
        assert len(cmd) >= 1


# ── TestCLIAuthStatus ─────────────────────────────────────────────────────────


class TestCLIAuthStatus:
    """Auth status can run even without credentials (reports unauthenticated)."""

    def test_auth_status_no_crash(self):
        """auth status exits cleanly with no Python traceback."""
        env = {**os.environ, "MERUSCASE_ACCESS_TOKEN": ""}
        result = subprocess.run(
            CLI_BASE + ["auth", "status"],
            capture_output=True, text=True, env=env
        )
        # Should not produce a Python traceback regardless of exit code
        assert "Traceback" not in result.stderr

    def test_auth_status_json(self):
        """--json auth status emits valid JSON with a 'status' key."""
        env = {**os.environ, "MERUSCASE_ACCESS_TOKEN": "fake-token-for-test"}
        result = subprocess.run(
            CLI_BASE + ["--json", "auth", "status"],
            capture_output=True, text=True, env=env
        )
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout)
            assert "status" in data


# ── TestIntegration ───────────────────────────────────────────────────────────


@pytest.mark.integration
class TestIntegration:
    """Real API tests — require MERUSCASE_ACCESS_TOKEN env var. Skip in CI."""

    def test_case_list_returns_json(self):
        """case list --json returns a list of cases from the real API."""
        token = os.environ.get("MERUSCASE_ACCESS_TOKEN")
        if not token:
            pytest.skip("MERUSCASE_ACCESS_TOKEN not set")
        result = subprocess.run(
            CLI_BASE + ["--json", "case", "list", "--limit", "5"],
            capture_output=True, text=True
        )
        assert result.returncode == 0, result.stderr
        data = json.loads(result.stdout)
        assert isinstance(data, list)

    def test_auth_status_with_token(self):
        """auth status --json returns authenticated status with a real token."""
        token = os.environ.get("MERUSCASE_ACCESS_TOKEN")
        if not token:
            pytest.skip("MERUSCASE_ACCESS_TOKEN not set")
        result = subprocess.run(
            CLI_BASE + ["--json", "auth", "status"],
            capture_output=True, text=True
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data.get("status") == "authenticated"

    def test_session_status_json(self):
        """session status --json returns a dict with expected keys."""
        token = os.environ.get("MERUSCASE_ACCESS_TOKEN")
        if not token:
            pytest.skip("MERUSCASE_ACCESS_TOKEN not set")
        result = subprocess.run(
            CLI_BASE + ["--json", "session", "status"],
            capture_output=True, text=True
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "token_present" in data
        assert "undo_stack_depth" in data
