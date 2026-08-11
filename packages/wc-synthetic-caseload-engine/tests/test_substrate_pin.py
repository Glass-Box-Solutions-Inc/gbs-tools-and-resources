"""The substrate pin: the file's presence and shape, and the WARN path that reads it.

``substrate_pin.txt`` at the package root records the substrate commit the
determinism gates were last verified against (AJC-73). Its *presence and
shape* are enforced here; its *value* deliberately is not. A test asserting
``read_substrate_pin() == substrate_git_sha()`` would turn every
substrate-touching PR red for its whole life and force a rubber-stamp pin bump
into each one — the design is that a mismatch WARNs (here and as a CI
annotation) and never fails, because only the operator can tell a deliberate
newer-substrate run from an accidental one. See ``check_substrate_pin``.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from structlog.testing import capture_logs

from wc_caseload_engine import substrate as bridge

FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


def _pin_value_lines() -> list[str]:
    """The pin file's non-comment, non-blank lines — what the reader considers."""
    text = bridge.substrate_pin_path().read_text(encoding="utf-8")
    stripped = (line.strip() for line in text.splitlines())
    return [line for line in stripped if line and not line.startswith("#")]


def test_pin_file_is_committed_at_the_package_root() -> None:
    """A missing pin silently disables the drift WARN — absence must be loud."""
    path = bridge.substrate_pin_path()
    assert path.is_file(), (
        f"{path} is missing: check_substrate_pin() returns True with nothing to "
        "compare, so substrate drift would go entirely unreported. Restore the "
        "pin (see its header for the refresh procedure)."
    )


def test_pin_file_carries_exactly_one_full_lowercase_sha() -> None:
    """Exactly one value line, and that value a 40-hex commit — nothing else parses.

    ``read_substrate_pin()`` returns the *first* non-comment line, so a second
    value line would be silently ignored and a truncated or uppercase SHA would
    "mismatch" every real commit forever — a WARN that always fires is a WARN
    nobody reads.
    """
    assert bridge.substrate_pin_path().is_file(), "no pin file to check the shape of"
    values = _pin_value_lines()
    assert len(values) == 1, (
        f"expected exactly one non-comment line in {bridge.substrate_pin_path()}, "
        f"found {len(values)}: {values!r}"
    )
    assert FULL_SHA.fullmatch(values[0]), (
        f"pin value {values[0]!r} is not a full 40-hex lowercase commit SHA"
    )


def test_reader_returns_the_single_pinned_value() -> None:
    """Tie the shape test to the reader: what we validated is what the code reads."""
    assert bridge.read_substrate_pin() == _pin_value_lines()[0]


def test_pin_mismatch_warns_and_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    """A moved substrate must produce the WARN, with both SHAs named in it."""
    pinned = bridge.read_substrate_pin()
    assert pinned is not None, "precondition: the committed pin exists"
    moved = "0" * 40 if pinned != "0" * 40 else "1" * 40
    monkeypatch.setattr(bridge, "substrate_git_sha", lambda: moved)

    with capture_logs() as entries:
        result = bridge.check_substrate_pin()

    assert result is False, "a mismatch must be reported to the caller, not absorbed"
    warnings = [
        entry
        for entry in entries
        if entry.get("event") == "substrate.pin_mismatch"
        and entry.get("log_level") == "warning"
    ]
    assert warnings, (
        f"no pin-mismatch warning was emitted; got {[e.get('event') for e in entries]}"
    )
    assert warnings[0]["pinned"] == pinned
    assert warnings[0]["actual"] == moved
    assert "re-run the determinism gates" in warnings[0]["hint"]


def test_pin_match_is_silent_and_true(monkeypatch: pytest.MonkeyPatch) -> None:
    """The WARN must be a signal, not a constant — prove it can stay silent."""
    pinned = bridge.read_substrate_pin()
    assert pinned is not None, "precondition: the committed pin exists"
    monkeypatch.setattr(bridge, "substrate_git_sha", lambda: pinned)

    with capture_logs() as entries:
        assert bridge.check_substrate_pin() is True

    assert not [e for e in entries if e.get("event") == "substrate.pin_mismatch"]


def test_unknown_substrate_sha_is_silent_and_true(monkeypatch: pytest.MonkeyPatch) -> None:
    """Outside a git checkout there is nothing to compare, so nothing to say."""
    monkeypatch.setattr(bridge, "substrate_git_sha", lambda: bridge.UNKNOWN_SHA)

    with capture_logs() as entries:
        assert bridge.check_substrate_pin() is True

    assert not [e for e in entries if e.get("event") == "substrate.pin_mismatch"]


def test_missing_pin_file_is_silent_and_true(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """No pin means no claim: the checker has nothing to enforce and stays quiet.

    ``check_substrate_pin`` returns before ever computing the live SHA, so this
    holds even where git is unavailable.
    """
    monkeypatch.setattr(bridge, "substrate_pin_path", lambda: tmp_path / "substrate_pin.txt")

    with capture_logs() as entries:
        assert bridge.check_substrate_pin() is True

    assert not [e for e in entries if e.get("event") == "substrate.pin_mismatch"]
