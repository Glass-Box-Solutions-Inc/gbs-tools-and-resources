"""Keeping the schema's prose honest about what the schema does.

Three of the five findings in the PR #25 review were the same defect: the code
and the prose disagreed. A CHANGELOG claimed a threading fix that had not
happened, a test's name promised an assertion it did not make, and — the one
this module exists for — a schema field's docstring named a consumer that did
not exist.

The schema is what a seed author reads. A field documented as driving the
output, which drives nothing, is a half-wired knob in documentation: worse than
an undocumented field, because the reader has no reason to doubt it.

The rule this module enforces is deliberately mechanical, because "check the
prose against the code" is exactly the kind of review task that works until
someone is tired:

    A field whose docstring carries :data:`NOT_YET_HONOURED_MARKER` must be
    byte-inert — changing its value must change no output byte. A field that is
    not marked must actually do something.

The payoff is in the direction of the failure. When a Phase-3b field is wired
up, its byte-inertness test starts failing, and the only way to make the suite
green is to delete the marker from the docstring — which is precisely the edit
that was forgotten before. The guard does not check that documentation was
updated; it makes the documentation impossible to leave stale.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

#: The phrase a schema docstring uses to promise nothing.
#:
#: Matched case-insensitively and with flexible whitespace, because a docstring
#: wraps across lines and an author may write "Not yet honoured" at the start of
#: a sentence. A marker that only matches one spelling is a marker that can be
#: evaded by accident.
NOT_YET_HONOURED_MARKER = "not yet honoured"

_MARKER_RE = re.compile(r"not\s+yet\s+honou?red", re.IGNORECASE)


def carries_marker(text: str) -> bool:
    """Whether *text* claims the field it documents does nothing yet."""
    return bool(_MARKER_RE.search(text))


def field_docstrings(source: str, class_name: str) -> dict[str, str]:
    """Map ``field -> docstring`` for one class in *source*.

    Read from the syntax tree rather than from ``model_fields``, because these
    are PEP 257 attribute docstrings — a bare string expression following the
    assignment. Pydantic only surfaces them with ``use_attribute_docstrings``
    enabled, and relying on a model-config flag would make this guard silently
    stop seeing anything if that flag were ever turned off.
    """
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        found: dict[str, str] = {}
        pending: str | None = None
        for statement in node.body:
            if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
                pending = statement.target.id
                found.setdefault(pending, "")
            elif (
                pending is not None
                and isinstance(statement, ast.Expr)
                and isinstance(statement.value, ast.Constant)
                and isinstance(statement.value.value, str)
            ):
                found[pending] = statement.value.value
                pending = None
            else:
                pending = None
        return found
    raise LookupError(f"class {class_name!r} not found in the given source")


def marked_fields(source: str, class_names: tuple[str, ...]) -> dict[str, str]:
    """Every ``Class.field`` in *class_names* whose docstring carries the marker."""
    marked: dict[str, str] = {}
    for class_name in class_names:
        for field, doc in field_docstrings(source, class_name).items():
            if carries_marker(doc):
                marked[f"{class_name}.{field}"] = doc
    return marked


def scenario_source() -> str:
    """The seeds module's source, for the sweep to parse."""
    from wc_caseload_engine import seeds

    return Path(seeds.__file__).read_text(encoding="utf-8")


__all__ = [
    "NOT_YET_HONOURED_MARKER",
    "carries_marker",
    "field_docstrings",
    "marked_fields",
    "scenario_source",
]
