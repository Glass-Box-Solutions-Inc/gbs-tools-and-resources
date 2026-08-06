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


#: JSON-Pointer-style escaping for path segments: keys may legitimately contain
#: the characters the dotted-path grammar reserves ('.', '[', ']', '$'), so those
#: are escaped when a key becomes a path segment. '~0' must decode last.
_SEGMENT_ESCAPES = (("~", "~0"), (".", "~1"), ("[", "~2"), ("]", "~3"), ("$", "~4"))


#: Encoded form of the empty key. A literal "~5" key escapes to "~05", so the
#: sentinel can never be forged by input.
_EMPTY_SEGMENT = "~5"


def escape_segment(key: str) -> str:
    """Make a mapping key safe to embed as one dotted-path segment."""
    for char, escaped in _SEGMENT_ESCAPES:
        key = key.replace(char, escaped)
    return key or _EMPTY_SEGMENT


def unescape_segment(segment: str) -> str:
    """Recover the original mapping key from an escaped path segment."""
    if segment == _EMPTY_SEGMENT:
        return ""
    for char, escaped in reversed(_SEGMENT_ESCAPES):
        segment = segment.replace(escaped, char)
    return segment
