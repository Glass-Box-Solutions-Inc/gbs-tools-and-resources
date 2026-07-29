"""ISC-129 — an actionable error message is a promise, and promises get checked.

The ``denied_by_ur`` validator once told authors to write ``decision: denied``,
which is not a value the enum accepts. Following the message verbatim produced a
*second* error. A message that sends the reader somewhere that also fails is
worse than a terse one, because it costs a round trip to find out. ``planner.py``
had the same defect in a different shape: it sent anyone with a bad control key
to a ``taxonomy --list`` subcommand of this CLI that has never existed.

Both were invisible for the same reason — **nothing executes the text of an
error message**. The CLI half of that class is already closed by a static sweep
(``test_every_cli_invocation_in_the_source_is_real``): every invocation of this
package's own console script named anywhere in the source is checked against the
real command surface. That sweep is live enough to have failed on the first
draft of *this* docstring, which quoted the dead invocation in full. This module
closes the seed half, which the sweep cannot reach, because
"add ``decision: upheld``" is prose, not a command line.

The rule:

    A seed-validation message that tells the author what to change must be
    registered with the edit that resolves it, and that edit must produce a
    seed that loads.

The registry lives in ``tests/test_message_registry.py``; this module is the
scanner that decides what belongs in it. The direction of the failure is the
point, exactly as in :mod:`wc_caseload_engine.schema_audit`: writing a new
actionable message turns the registry red until someone proves that following it
works. The guard does not check that the message is good advice — it makes
unproven advice impossible to leave behind.

Scope is :mod:`wc_caseload_engine.seeds` deliberately. That is where a seed
author's mistakes land, it is the module whose messages the two known defects
came from, and a package-wide sweep would drag in operator warnings whose
"resolving edit" is not a seed edit at all.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

#: The token a runtime interpolation collapses to in a message *template*.
#:
#: A template is what the registry pins, so it has to be the part of the message
#: that does not depend on the seed that tripped it.
PLACEHOLDER = "{}"

#: Clause-initial words that make a clause an instruction rather than a finding.
#:
#: Curated rather than inferred, because there is no part-of-speech tagger here
#: and a heuristic that guesses would either miss directives or flag every
#: sentence. The cost of the curation is stated plainly, and it has **two**
#: parts, because a reviewer found the second one after the first was written:
#:
#: 1. **An unknown verb is invisible.** "Nudge the value upwards" is a directive
#:    the sweep does not see. Adding an imperative to a seed message means adding
#:    its verb here.
#: 2. **A displaced verb is invisible too, and this is the wider hole.**
#:    Detection reads the clause's *first* word, so anything in front of the verb
#:    hides it — a pronoun, a politeness, a hedge. Measured: "You should set
#:    scenario.surgery to 'none'", "Please set scenario.surgery to 'none'" and
#:    "We suggest you remove the field" all evade, while the same sentences
#:    written imperatively are caught. **Write seed directives in the imperative,
#:    verb first.** Every one of the eleven registered messages already does.
#:
#: The limit is not merely written down —
#: ``test_the_vocabulary_is_the_limit_and_the_limit_is_stated`` asserts both
#: halves, so the boundary is discoverable by running the suite rather than by
#: reading this comment. Widening the detector to look past a leading pronoun is
#: deliberately *not* done here: it would change what counts as actionable and so
#: what the registry must contain, which is a change that deserves its own
#: red-first cycle rather than a quiet loosening.
DIRECTIVE_VERBS: frozenset[str] = frozenset(
    {
        "add",
        "change",
        "choose",
        "clear",
        "declare",
        "delete",
        "drop",
        "edit",
        "enable",
        "disable",
        "fix",
        "keep",
        "list",
        "lower",
        "move",
        "name",
        "omit",
        "pass",
        "pick",
        "prefer",
        "raise",
        "reduce",
        "remove",
        "rename",
        "replace",
        "run",
        "seed",
        "set",
        "split",
        "state",
        "supply",
        "swap",
        "unset",
        "use",
        "widen",
        "write",
    }
)

#: Where one clause ends and the next begins.
#:
#: Sentence punctuation *followed by whitespace*, or a spaced dash. The trailing
#: ``\s`` is what keeps ``lifecycle.ur_dispute.enabled`` and
#: ``scenario.surgery: 'recommended'`` in one piece — a field path has no space
#: after its dots, and a bare split on ``.`` would shred every message here.
#: The dashes are spelled as escapes so the pattern reads the same in every
#: editor: U+2014 em dash, U+2013 en dash, ASCII hyphen.
_CLAUSE_BOUNDARY = re.compile(r"(?<=[.;!?])\s+|\s+[\u2014\u2013-]{1,2}\s+")

#: Leading decoration to look past when reading a clause's first word.
_OPENING_NOISE = "\"'`([{*_ "


def normalize(text: str) -> str:
    """Collapse a message's whitespace so wrapping never changes its identity."""
    return re.sub(r"\s+", " ", text).strip()


def clauses(message: str) -> tuple[str, ...]:
    """*message* split into the clauses :func:`directives` classifies.

    Public so a test can ask questions about clause *shape* — the leading-pronoun
    blind spot in particular — without re-deriving the split and drifting from it.
    """
    return tuple(
        trimmed
        for clause in _CLAUSE_BOUNDARY.split(normalize(message))
        if (trimmed := clause.strip().rstrip("."))
    )


def first_word(clause: str) -> str:
    """The word a clause opens with, read past any quote or bracket."""
    return (
        clause.lstrip(_OPENING_NOISE)
        .split(" ", 1)[0]
        .strip(_OPENING_NOISE + ",:;")
        .casefold()
    )


def directives(message: str) -> tuple[str, ...]:
    """Every clause of *message* that tells the author what to change.

    A clause qualifies when its first word — read past any opening quote or
    bracket — is in :data:`DIRECTIVE_VERBS`. That is the whole definition, and it
    is deliberately syntactic: "what counts as advice" is not a judgement a
    guard can make twice the same way.

    The cost of reading only the *first* word is the second half of the limit
    documented on :data:`DIRECTIVE_VERBS`: "You should set …" hides its verb
    behind a pronoun and is not seen.
    """
    return tuple(
        clause for clause in clauses(message) if first_word(clause) in DIRECTIVE_VERBS
    )


def is_actionable(message: str) -> bool:
    """Whether *message* tells the author to do something."""
    return bool(directives(message))


def longest_literal_run(template: str) -> str:
    """The longest stretch of *template* that survives interpolation.

    What a test can substring-match against a real raised message, so a registry
    entry proves it tripped the message it claims rather than merely *some*
    error.
    """
    return max(template.split(PLACEHOLDER), key=len).strip()


@dataclass(frozen=True)
class RaisedMessage:
    """One message :mod:`wc_caseload_engine.seeds` can put in front of an author."""

    where: str
    """``Class.validator`` (or the bare function) that owns the text."""

    line: int
    """Where it lives today — for the failure message, never for identity."""

    template: str
    """The message with every interpolation collapsed to :data:`PLACEHOLDER`."""

    directives: tuple[str, ...]
    """The clauses that tell the author what to change; empty when it just reports."""

    @property
    def actionable(self) -> bool:
        return bool(self.directives)


def _static_text(node: ast.AST) -> str | None:
    """The literal skeleton of a string expression, or ``None`` if it is not one."""
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, str) else None
    if isinstance(node, ast.JoinedStr):
        parts = []
        for piece in node.values:
            if isinstance(piece, ast.Constant) and isinstance(piece.value, str):
                parts.append(piece.value)
            else:
                parts.append(PLACEHOLDER)
        return "".join(parts)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        # ``"prefix " + ", ".join(...)`` — the computed half is an interpolation
        # by another name, so it collapses the same way rather than defeating
        # the scan.
        left = _static_text(node.left)
        right = _static_text(node.right)
        if left is None and right is None:
            return None
        return (left or PLACEHOLDER) + (right or PLACEHOLDER)
    return None


def _qualified_names(tree: ast.Module) -> dict[int, str]:
    """Map every node to the dotted class/function path enclosing it."""
    owner: dict[int, str] = {}

    def walk(node: ast.AST, path: tuple[str, ...]) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
                here = (*path, child.name)
                owner[id(child)] = ".".join(here)
                walk(child, here)
            else:
                owner[id(child)] = ".".join(path)
                walk(child, path)

    walk(tree, ())
    return owner


def _module_functions(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
    }


def _strings_in(function: ast.FunctionDef) -> list[tuple[int, str]]:
    """Every message-shaped string expression in *function*, minus its docstring.

    One entry per literal rather than one joined blob: a helper that builds a
    report line by line holds several independent messages, and joining them
    would bury a directive in the middle of a sentence it does not belong to.

    Two filters keep the result honest. An f-string is taken whole and its own
    fragments are *not* revisited, or the same directive would be reported twice
    from one sentence. And a string with no whitespace in it is a dict key or a
    sentinel — ``"loc"``, ``"extra_forbidden"`` — never something an author
    reads; a message is at least two words long.
    """
    docstring = ast.get_docstring(function, clean=False)
    found: list[tuple[int, str]] = []
    pending: list[ast.AST] = list(ast.iter_child_nodes(function))
    while pending:
        node = pending.pop()
        text = _static_text(node) if isinstance(node, ast.Constant | ast.JoinedStr) else None
        if text is None:
            pending.extend(ast.iter_child_nodes(node))
            continue
        # Captured whole; descending would re-report its literal fragments.
        if text != docstring and " " in normalize(text):
            found.append((node.lineno, text))
    return found


def raised_messages(source: str) -> tuple[RaisedMessage, ...]:
    """Every message *source* raises, with one level of helper indirection resolved.

    A message built by a module-level helper — ``_repeated_part_message``,
    ``_format_errors`` — would otherwise be a blind spot, and both of those
    helpers really do carry directives. Resolving exactly one level keeps the
    scan honest without turning it into an interpreter;
    :func:`unresolved_raises` reports anything that stays opaque so the blind
    spot cannot grow back in silence.
    """
    tree = ast.parse(source)
    owner = _qualified_names(tree)
    helpers = _module_functions(tree)

    found: list[RaisedMessage] = []
    seen: set[tuple[str, str]] = set()

    def record(where: str, line: int, text: str) -> None:
        template = normalize(text)
        if not template or (where, template) in seen:
            return
        seen.add((where, template))
        found.append(
            RaisedMessage(
                where=where,
                line=line,
                template=template,
                directives=directives(template),
            )
        )

    for node in ast.walk(tree):
        if not isinstance(node, ast.Raise) or not isinstance(node.exc, ast.Call):
            continue
        if not node.exc.args:
            continue
        argument = node.exc.args[0]
        text = _static_text(argument)
        if text is not None:
            record(owner.get(id(node), "<module>"), node.lineno, text)
            continue
        if isinstance(argument, ast.Call) and isinstance(argument.func, ast.Name):
            helper = helpers.get(argument.func.id)
            if helper is not None:
                for line, literal in _strings_in(helper):
                    record(helper.name, line, literal)

    return tuple(sorted(found, key=lambda m: (m.where, m.template)))


def unresolved_raises(source: str) -> tuple[str, ...]:
    """Raise sites whose message text the scan cannot see at all.

    A message the sweep cannot read is a place an unproven directive can live,
    so this is asserted empty rather than assumed empty.
    """
    tree = ast.parse(source)
    owner = _qualified_names(tree)
    helpers = _module_functions(tree)

    opaque: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Raise) or not isinstance(node.exc, ast.Call):
            continue
        if not node.exc.args:
            continue
        argument = node.exc.args[0]
        if _static_text(argument) is not None:
            continue
        if (
            isinstance(argument, ast.Call)
            and isinstance(argument.func, ast.Name)
            and helpers.get(argument.func.id) is not None
            and _strings_in(helpers[argument.func.id])
        ):
            continue
        opaque.append(f"{owner.get(id(node), '<module>')}:{node.lineno}")
    return tuple(opaque)


def actionable_messages(source: str) -> tuple[RaisedMessage, ...]:
    """The subset of :func:`raised_messages` that instructs rather than reports."""
    return tuple(message for message in raised_messages(source) if message.actionable)


def seed_source() -> str:
    """The seed module's source, for the sweep to parse.

    Read from disk rather than ``inspect.getsource`` so the sweep sees the file
    an author edits, not an import-time artefact.
    """
    from wc_caseload_engine import seeds

    return Path(seeds.__file__).read_text(encoding="utf-8")


__all__ = [
    "DIRECTIVE_VERBS",
    "PLACEHOLDER",
    "RaisedMessage",
    "actionable_messages",
    "clauses",
    "directives",
    "first_word",
    "is_actionable",
    "longest_literal_run",
    "normalize",
    "raised_messages",
    "seed_source",
    "unresolved_raises",
]
