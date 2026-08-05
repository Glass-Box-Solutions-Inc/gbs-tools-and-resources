"""Shared field/value canonicalization used by ingestion and validation.

`dateOfInjury`, `DateOfInjury`, and `date_of_injury` must land in one vocabulary,
or facts from different extraction dialects never meet in the same conflict check.
"""

from __future__ import annotations

import json
import re
from typing import Any

_CAMEL_BOUNDARY_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_SEPARATOR_RE = re.compile(r"[^a-z0-9]+")


def split_words(value: str) -> str:
    """Insert separators at camelCase/PascalCase boundaries, preserving acronym runs."""
    return _CAMEL_BOUNDARY_RE.sub("_", value)


def canonical_field(field: str) -> str:
    """One canonical spelling per field: camelCase, PascalCase, and separators all merge."""
    return _SEPARATOR_RE.sub("_", split_words(field).lower()).strip("_")


def tokens(value: str) -> frozenset[str]:
    """Lowercased word set with camelCase boundaries split before separator splitting."""
    return frozenset(token for token in _SEPARATOR_RE.split(split_words(value).lower()) if token)


def stable_value(value: Any) -> str:
    """A deterministic string form for grouping and sorting arbitrary JSON scalars."""
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str, separators=(",", ":"))
