"""The one and only bridge to the ``merus-test-data-generator`` substrate.

The substrate is a sibling package in this monorepo with no ``pyproject.toml``.
Its modules import each other as top-level packages (``from data.x import ...``,
``from pdf_templates.y import ...``), so the substrate **root** must be on
``sys.path`` for anything to resolve.

Rules encoded here (see ``BUILD_NOTES.md``):

* This module is the only place in the package that touches ``sys.path``.
* Substrate files are never copied — if an import breaks, fix the bridge.
* The path is appended (not prepended) so the substrate can never shadow this
  package's own modules or a test module of the same basename.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
from collections.abc import Iterator, Sequence
from functools import lru_cache
from pathlib import Path
from types import ModuleType

import structlog

log = structlog.get_logger(__name__)

SUBSTRATE_DIR_NAME = "merus-test-data-generator"
"""Directory name of the substrate package inside ``packages/``."""

SUBSTRATE_ENV_VAR = "WC_CASELOAD_SUBSTRATE"
"""Environment variable that overrides substrate discovery (absolute path)."""

REQUIRED_MODULES: tuple[str, ...] = (
    "data.taxonomy",
    "data.lifecycle_engine",
    "data.fake_data_generator",
    "data.models",
    "pdf_templates.registry",
    "pdf_templates.base_template",
)
"""Substrate modules this engine depends on; verified by :func:`require_substrate`."""

_SENTINEL_PATHS: tuple[str, ...] = (
    "data/taxonomy.py",
    "data/lifecycle_engine.py",
    "pdf_templates/registry.py",
)
"""Files that must exist for a directory to qualify as the substrate root."""


class SubstrateUnavailableError(RuntimeError):
    """Raised when the substrate cannot be located or imported."""


def _looks_like_substrate(candidate: Path) -> bool:
    """Return ``True`` when *candidate* contains the substrate's sentinel files."""
    return all((candidate / rel).is_file() for rel in _SENTINEL_PATHS)


def _candidate_roots() -> Iterator[Path]:
    """Yield candidate substrate roots in priority order."""
    override = os.environ.get(SUBSTRATE_ENV_VAR)
    if override:
        yield Path(override).expanduser().resolve()

    here = Path(__file__).resolve()
    # src/wc_caseload_engine/substrate.py -> packages/<pkg>/src/wc_caseload_engine
    # parents[3] is packages/, where the substrate lives as a sibling package.
    for parent in here.parents:
        yield parent / SUBSTRATE_DIR_NAME
        yield parent / "packages" / SUBSTRATE_DIR_NAME


@lru_cache(maxsize=1)
def find_substrate() -> Path | None:
    """Locate the substrate root, or ``None`` when it is not on disk."""
    seen: set[Path] = set()
    for candidate in _candidate_roots():
        if candidate in seen:
            continue
        seen.add(candidate)
        if _looks_like_substrate(candidate):
            return candidate
    return None


def _searched_locations() -> list[str]:
    """Human-readable list of the locations probed by :func:`find_substrate`."""
    out: list[str] = []
    for candidate in _candidate_roots():
        text = str(candidate)
        if text not in out:
            out.append(text)
    return out[:8]


def substrate_path() -> Path:
    """Return the substrate root, raising :class:`SubstrateUnavailableError` if absent."""
    found = find_substrate()
    if found is None:
        locations = "\n  ".join(_searched_locations())
        raise SubstrateUnavailableError(
            "merus-test-data-generator substrate not found.\n"
            f"  Set {SUBSTRATE_ENV_VAR}=/absolute/path/to/{SUBSTRATE_DIR_NAME} "
            "or check out the monorepo package alongside this one.\n"
            f"  Searched:\n  {locations}\n"
            "  A valid substrate root contains data/taxonomy.py, data/lifecycle_engine.py "
            "and pdf_templates/registry.py."
        )
    return found


def install_substrate_path() -> Path:
    """Append the substrate root to ``sys.path`` (idempotent) and return it."""
    root = substrate_path()
    text = str(root)
    if text not in sys.path:
        sys.path.append(text)
        log.debug("substrate.path_installed", path=text)
    return root


def import_substrate(module_name: str) -> ModuleType:
    """Import a substrate module (e.g. ``"data.taxonomy"``) through the bridge."""
    install_substrate_path()
    try:
        return importlib.import_module(module_name)
    except ImportError as exc:  # pragma: no cover - exercised via require_substrate
        raise SubstrateUnavailableError(
            f"Substrate module {module_name!r} failed to import from {substrate_path()}: {exc}\n"
            "  Fix the bridge (sys.path / dependencies) — never copy substrate files."
        ) from exc


def require_substrate(modules: Sequence[str] = REQUIRED_MODULES) -> Path:
    """Fail fast unless every required substrate module imports cleanly.

    Returns the substrate root on success. Raises
    :class:`SubstrateUnavailableError` with an actionable message otherwise.
    """
    root = install_substrate_path()
    failures: list[str] = []
    for name in modules:
        try:
            importlib.import_module(name)
        except Exception as exc:
            failures.append(f"    {name}: {type(exc).__name__}: {exc}")
    if failures:
        detail = "\n".join(failures)
        raise SubstrateUnavailableError(
            f"Substrate at {root} did not import cleanly:\n{detail}\n"
            "  Remedies: install this package's dependencies "
            "(pip install -e '.[dev]'), or adjust the bridge in substrate.py. "
            "Never copy substrate modules into this package."
        )
    log.debug("substrate.ready", path=str(root), modules=len(modules))
    return root


def substrate_available() -> bool:
    """Return ``True`` when the substrate is present and importable."""
    try:
        require_substrate()
    except SubstrateUnavailableError:
        return False
    return True


# ---------------------------------------------------------------------------
# Provenance: which substrate produced this caseload
# ---------------------------------------------------------------------------

UNKNOWN_SHA = "unknown"
"""Recorded when the substrate is not in a git checkout, or git is unavailable."""

SUBSTRATE_PIN_FILE = "substrate_pin.txt"
"""Package-root file recording the substrate commit this engine was verified against."""


@lru_cache(maxsize=1)
def substrate_git_sha() -> str:
    """The commit the substrate is at, or :data:`UNKNOWN_SHA`.

    Every rendered document's content ultimately comes from the substrate's
    templates and content pools, so "same seed, same version" is only half the
    provenance story — a manifest that does not name the substrate cannot be
    reproduced from itself. This is recorded as ``provenance.substrateSha``.

    Scoped to the substrate *directory* rather than plain ``rev-parse HEAD``:
    the substrate is a package inside a monorepo, so bare ``HEAD`` moves on
    every unrelated commit and a pin built on it would warn constantly — an
    alarm that always fires is an alarm nobody reads. The last commit that
    touched the substrate path is the value that actually answers "did the
    substrate change under me?".
    """
    root = find_substrate()
    if root is None:
        return UNKNOWN_SHA
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), "log", "-1", "--format=%H", "--", "."],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        log.debug("substrate.sha_unavailable", error=str(exc))
        return UNKNOWN_SHA
    sha = completed.stdout.strip()
    if completed.returncode != 0 or not sha:
        log.debug("substrate.sha_unavailable", returncode=completed.returncode)
        return UNKNOWN_SHA
    return sha


def substrate_pin_path() -> Path:
    """Location of :data:`SUBSTRATE_PIN_FILE` at this package's root."""
    # src/wc_caseload_engine/substrate.py -> <package root>
    return Path(__file__).resolve().parents[2] / SUBSTRATE_PIN_FILE


def read_substrate_pin() -> str | None:
    """The pinned substrate SHA, or ``None`` when the package carries no pin."""
    path = substrate_pin_path()
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped
    return None


def check_substrate_pin() -> bool:
    """Warn when the substrate has moved off the pinned commit.

    A warning, never a failure: generating against a newer substrate is a normal
    thing to do deliberately and an alarming thing to do by accident, and only
    the operator can tell those apart. Returns ``True`` when the pin matches (or
    there is nothing to compare).
    """
    pinned = read_substrate_pin()
    if pinned is None:
        return True
    actual = substrate_git_sha()
    if actual in (UNKNOWN_SHA, pinned):
        return True
    log.warning(
        "substrate.pin_mismatch",
        pinned=pinned,
        actual=actual,
        pin_file=str(substrate_pin_path()),
        hint=(
            "the substrate has changed since this engine was verified against it; "
            "re-run the determinism gates and update substrate_pin.txt if the new "
            "output is correct"
        ),
    )
    return False


__all__ = [
    "REQUIRED_MODULES",
    "SUBSTRATE_DIR_NAME",
    "SUBSTRATE_ENV_VAR",
    "SUBSTRATE_PIN_FILE",
    "UNKNOWN_SHA",
    "SubstrateUnavailableError",
    "check_substrate_pin",
    "find_substrate",
    "import_substrate",
    "install_substrate_path",
    "read_substrate_pin",
    "require_substrate",
    "substrate_available",
    "substrate_git_sha",
    "substrate_path",
    "substrate_pin_path",
]
