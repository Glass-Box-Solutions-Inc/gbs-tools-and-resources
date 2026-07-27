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


__all__ = [
    "REQUIRED_MODULES",
    "SUBSTRATE_DIR_NAME",
    "SUBSTRATE_ENV_VAR",
    "SubstrateUnavailableError",
    "find_substrate",
    "import_substrate",
    "install_substrate_path",
    "require_substrate",
    "substrate_available",
    "substrate_path",
]
