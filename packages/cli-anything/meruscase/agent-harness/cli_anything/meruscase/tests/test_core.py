"""
Unit tests for cli-anything-meruscase core modules.
Uses mocked API client — no real MerusCase connection required.
"""
import json
import pytest
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

from cli_anything.meruscase.core.session import (
    MerusCaseSession, load_token, save_token
)
from cli_anything.meruscase.core.cases import find_case, CaseNotFoundError
from cli_anything.meruscase.core.billing import bill_time, add_cost, get_billing_summary


# ── TestSessionTokenLoading ───────────────────────────────────────────────────


class TestSessionTokenLoading:
    """Tests for load_token() and save_token() logic."""

    def setup_method(self):
        """Reset the in-process token cache before each test."""
        import cli_anything.meruscase.core.session as _sm
        _sm._token_cache = None
        _sm._gcp_available = None

    def test_load_token_from_env_var(self, monkeypatch, tmp_path):
        """load_token returns env var when set (after GCP falls through)."""
        monkeypatch.setenv("MERUSCASE_ACCESS_TOKEN", "test-token-123")
        # Force GCP to be unavailable so it falls through to env var
        with patch("cli_anything.meruscase.core.session._gcp_available", False):
            import cli_anything.meruscase.core.session as _sm
            _sm._gcp_available = False
            token = load_token()
        assert token == "test-token-123"

    def test_load_token_from_file(self, monkeypatch, tmp_path):
        """load_token reads from file when env var absent and GCP unavailable."""
        monkeypatch.delenv("MERUSCASE_ACCESS_TOKEN", raising=False)
        token_file = tmp_path / ".meruscase_token"
        token_file.write_text("file-token-456\n")
        import cli_anything.meruscase.core.session as _sm
        _sm._gcp_available = False
        with patch("cli_anything.meruscase.core.session.TOKEN_FILE", token_file):
            token = load_token()
        assert token == "file-token-456"

    def test_load_token_returns_none_when_nothing(self, monkeypatch, tmp_path):
        """load_token returns None (not raise) when no sources available."""
        monkeypatch.delenv("MERUSCASE_ACCESS_TOKEN", raising=False)
        import cli_anything.meruscase.core.session as _sm
        _sm._gcp_available = False
        with patch("cli_anything.meruscase.core.session.TOKEN_FILE", tmp_path / "nofile"):
            token = load_token()
        assert token is None

    def test_save_token_writes_file(self, tmp_path):
        """save_token writes token to disk."""
        token_file = tmp_path / ".meruscase_token"
        with patch("cli_anything.meruscase.core.session.TOKEN_FILE", token_file):
            save_token("saved-token-789")
        assert token_file.read_text().strip() == "saved-token-789"


# ── TestMerusCaseSessionUndoRedo ──────────────────────────────────────────────


class TestMerusCaseSessionUndoRedo:
    """Tests for snapshot/undo/redo stack."""

    def test_snapshot_and_undo(self):
        """State is restored after undo."""
        sess = MerusCaseSession()
        sess._state = {"key": "original"}
        sess.snapshot("Set key")
        sess._state = {"key": "modified"}
        description = sess.undo()
        assert description == "Set key"
        assert sess._state["key"] == "original"

    def test_undo_empty_stack_returns_none(self):
        """undo() returns None gracefully when stack is empty."""
        sess = MerusCaseSession()
        assert sess.undo() is None

    def test_redo_after_undo(self):
        """redo() re-applies the undone state."""
        sess = MerusCaseSession()
        sess._state = {"v": 1}
        sess.snapshot("v=1")
        sess._state = {"v": 2}
        sess.undo()
        # After undo, state is {"v": 1}. Redo should put us back to {"v": 2}.
        description = sess.redo()
        assert description == "v=1"
        assert sess._state["v"] == 2

    def test_redo_empty_returns_none(self):
        """redo() returns None gracefully when redo stack is empty."""
        sess = MerusCaseSession()
        assert sess.redo() is None

    def test_snapshot_trims_to_max_50(self):
        """Undo stack never exceeds 50 entries."""
        sess = MerusCaseSession()
        for i in range(55):
            sess._state = {"i": i}
            sess.snapshot(f"step {i}")
        assert len(sess._undo_stack) == 50

    def test_snapshot_clears_redo(self):
        """A new snapshot invalidates the redo history."""
        sess = MerusCaseSession()
        sess._state = {"v": 1}
        sess.snapshot("v=1")
        sess._state = {"v": 2}
        sess.undo()  # redo stack now has one entry
        sess._state = {"v": 3}
        sess.snapshot("v=3")  # should clear redo
        assert len(sess._redo_stack) == 0

    def test_is_modified_after_snapshot(self):
        """is_modified becomes True after the first snapshot."""
        sess = MerusCaseSession()
        assert not sess.is_modified
        sess.snapshot("change")
        assert sess.is_modified


# ── TestCaseFuzzySearch ───────────────────────────────────────────────────────


class TestCaseFuzzySearch:
    """Tests for find_case() fuzzy matching logic."""

    @pytest.mark.asyncio
    async def test_find_by_exact_file_number(self):
        """find_case returns the matching case on exact file number."""
        mock_client = AsyncMock()
        mock_client.list_cases.return_value = {
            "data": [
                {"id": 1, "file_number": "TC001", "primary_party_name": "Smith, John"},
                {"id": 2, "file_number": "TC002", "primary_party_name": "Doe, Jane"},
            ]
        }
        result = await find_case(mock_client, "TC001")
        assert result["id"] == 1

    @pytest.mark.asyncio
    async def test_find_by_party_name_substring(self):
        """find_case matches case-insensitively on primary_party_name."""
        mock_client = AsyncMock()
        mock_client.list_cases.return_value = {
            "data": [
                {"id": 1, "file_number": "TC001", "primary_party_name": "SMITH, JOHN"},
            ]
        }
        result = await find_case(mock_client, "smith")
        assert result is not None
        assert result["id"] == 1

    @pytest.mark.asyncio
    async def test_raises_case_not_found(self):
        """find_case raises CaseNotFoundError when nothing matches."""
        mock_client = AsyncMock()
        mock_client.list_cases.return_value = {"data": []}
        with pytest.raises(CaseNotFoundError):
            await find_case(mock_client, "nonexistent-xyz-999")


# ── TestBillingCalculations ───────────────────────────────────────────────────


class TestBillingCalculations:
    """Tests for billing math and field construction."""

    @pytest.mark.asyncio
    async def test_bill_time_converts_hours_to_minutes(self):
        """bill_time converts hours × 60 = minutes and returns both."""
        mock_client = AsyncMock()
        mock_client.add_activity.return_value = {"Activity": {"id": 42}}
        result = await bill_time(mock_client, case_id=1, hours=0.5, description="Review records")
        assert result["minutes"] == 30
        assert result["hours"] == 0.5
        # Confirm the client received duration_minutes=30 in the payload
        call_data = mock_client.add_activity.call_args[0][0]
        assert call_data.get("duration_minutes") == 30

    @pytest.mark.asyncio
    async def test_bill_time_auto_subject(self):
        """bill_time auto-truncates description to 60 chars for subject."""
        mock_client = AsyncMock()
        mock_client.add_activity.return_value = {"Activity": {"id": 1}}
        long_desc = "A" * 80
        await bill_time(mock_client, case_id=1, hours=1.0, description=long_desc)
        call_data = mock_client.add_activity.call_args[0][0]
        subject = call_data.get("subject", "")
        assert len(subject) <= 60

    @pytest.mark.asyncio
    async def test_add_cost_maps_ledger_type(self):
        """add_cost maps 'fee' → ledger_type_id=1 in the payload."""
        mock_client = AsyncMock()
        mock_client.add_ledger.return_value = {"CaseLedger": {"id": 7}}
        result = await add_cost(mock_client, case_id=1, amount=25.00, description="Filing fee", ledger_type="fee")
        assert result["type"] == "fee"
        call_data = mock_client.add_ledger.call_args[0][0]
        assert call_data.get("ledger_type_id") == 1  # fee=1

    @pytest.mark.asyncio
    async def test_billing_summary_totals(self):
        """get_billing_summary sums amounts across all ledger entries."""
        mock_client = AsyncMock()
        mock_client.get_ledger.return_value = {
            "data": [
                {"id": 1, "amount": "100.00"},
                {"id": 2, "amount": "50.50"},
            ]
        }
        result = await get_billing_summary(mock_client, case_id=1)
        assert abs(result["total_amount"] - 150.50) < 0.01
        assert result["total_entries"] == 2
