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

import hashlib
import json
import re
import subprocess
from pathlib import Path

import pytest
from structlog.testing import capture_logs

from conftest import requires_substrate
from wc_caseload_engine import substrate as bridge

FULL_SHA = re.compile(r"^[0-9a-f]{40}$")

AJC62_SUBSTRATE_BASELINE = Path(__file__).resolve().parent / "fixtures" / (
    "ajc62_substrate_baseline.json"
)
"""R67: every git-tracked substrate path and its SHA-256 at the merged M2
baseline ``eedad1093`` — the exact tree AJC-62 promises never to edit."""


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
    """The WARN must be a signal, not a constant — prove it can stay silent.

    Silent means *no events at all*, not merely no mismatch event: a quiet
    path that grew any chatter would erode the signal just as surely.
    """
    pinned = bridge.read_substrate_pin()
    assert pinned is not None, "precondition: the committed pin exists"
    monkeypatch.setattr(bridge, "substrate_git_sha", lambda: pinned)

    with capture_logs() as entries:
        assert bridge.check_substrate_pin() is True

    assert entries == []


def test_unknown_substrate_sha_is_silent_and_true(monkeypatch: pytest.MonkeyPatch) -> None:
    """Outside a git checkout there is nothing to compare, so nothing to say."""
    monkeypatch.setattr(bridge, "substrate_git_sha", lambda: bridge.UNKNOWN_SHA)

    with capture_logs() as entries:
        assert bridge.check_substrate_pin() is True

    assert entries == []


@requires_substrate
def test_ajc62_tracked_substrate_tree_matches_the_merged_m2_baseline() -> None:
    """AJC-62 R68: the substrate is read-only for the whole ticket, proved per file.

    The WARN-only pin above deliberately never fails on drift, because ordinary
    substrate evolution is legitimate. AJC-62 makes a stronger, ticket-scoped
    promise — R3 freezes ``../merus-test-data-generator/`` entirely, and a
    discovered defect becomes a separate ticket rather than an in-place repair
    — so this gate compares the live tracked tree byte-for-byte against the
    inventory frozen at the merged M2 baseline ``eedad1093``.

    The tracked set comes from ``git ls-files`` so an *added* tracked file is
    caught, not only an edited one; content comes from hashing the bytes on
    disk so an uncommitted edit is caught too. A git failure is a gate error,
    never a skip: an environment that cannot enumerate the tracked set cannot
    verify immutability, and reporting that as green would be the lie this
    test exists to prevent.
    """
    baseline = json.loads(AJC62_SUBSTRATE_BASELINE.read_text(encoding="utf-8"))
    frozen: dict[str, str] = baseline["tracked_sha256"]
    assert frozen, "the frozen substrate inventory is empty — the fixture is broken"

    substrate_root = bridge.substrate_path()
    listing = subprocess.run(
        ["git", "-C", str(substrate_root), "ls-files", "-z", "--", "."],
        capture_output=True,
        check=False,
    )
    if listing.returncode != 0:
        pytest.fail(
            "git could not enumerate the tracked substrate tree, so substrate "
            f"immutability cannot be verified (gate error, not a skip): "
            f"{listing.stderr.decode('utf-8', 'replace').strip()}"
        )
    tracked = sorted(
        path for path in listing.stdout.decode("utf-8").split("\0") if path
    )

    added = sorted(set(tracked) - set(frozen))
    removed = sorted(set(frozen) - set(tracked))
    assert not added and not removed, (
        "the tracked substrate file set moved off the merged M2 baseline — "
        f"added: {added[:10]}; removed: {removed[:10]}. AJC-62 may not touch "
        "the substrate; a substrate defect becomes its own ticket (R3)."
    )

    drifted: list[str] = []
    for path in tracked:
        on_disk = substrate_root / path
        if not on_disk.is_file():
            drifted.append(f"{path}: tracked but missing from disk")
            continue
        digest = hashlib.sha256(on_disk.read_bytes()).hexdigest()
        if digest != frozen[path]:
            drifted.append(f"{path}: bytes differ from the eedad1093 baseline")
    assert not drifted, (
        f"{len(drifted)} substrate file(s) differ from the merged M2 baseline:\n  "
        + "\n  ".join(drifted[:15])
        + "\nAJC-62 R3: the substrate is read-only; revert the edit and open a "
        "separate ticket for whatever motivated it."
    )


def _must_not_be_called() -> str:
    raise AssertionError("substrate_git_sha must not be called when no pin exists")


def test_missing_pin_file_is_silent_and_true(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """No pin means no claim: the checker has nothing to enforce and stays quiet.

    ``check_substrate_pin`` must return before ever computing the live SHA —
    enforced by making the computation itself raise — so the no-pin path
    holds even where git is unavailable.
    """
    monkeypatch.setattr(bridge, "substrate_pin_path", lambda: tmp_path / "substrate_pin.txt")
    monkeypatch.setattr(bridge, "substrate_git_sha", _must_not_be_called)

    with capture_logs() as entries:
        assert bridge.check_substrate_pin() is True

    assert entries == []
