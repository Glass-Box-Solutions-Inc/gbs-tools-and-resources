#!/usr/bin/env python3
"""Prove every registered guard still catches the defect it was written for.

A test that passes proves nothing on its own: it passes on the fixed code and
it may well pass on the broken code too. The only evidence that a guard is load
bearing is to put the defect back and watch that guard go red. This package did
that by hand for ten rounds, at the end of each round, from throwaway scripts —
and three separate rounds discovered that a guard written the round before had
never covered its own fix. So it is mechanized here and wired into CI.

The contract this enforces: **a fix may not be claimed until a mutation of that
exact fix has been shown to redden a test that names it.**

## What "red" is allowed to mean

The first version of this file treated any non-zero pytest exit as proof. That
was the same disease one level up — a gate built to stop unverified fixes,
shipped unverified, reporting clean. Ten registered mutants named node IDs for
classes that do not exist. pytest exited 4 (usage error, nothing collected) and
the gate scored all ten RED. The reported 100/100 was really 90/100.

RED is now a conjunction, and every part of it is checked:

1. **The guard is green before the mutation.** A test that is already failing
   cannot prove anything about a defect. Pristine runs first, cached per node.
2. **The mutated source compiles.** A mutation producing invalid Python proves
   the parser works and nothing else.
3. **The named test collects exactly once.** Not zero — that is the defect this
   rewrite exists for — and not many, which would make the verdict partly about
   some other test.
4. **Setup and teardown passed; the failure is in the call phase.** A fixture
   that exploded is not a guard that fired.
5. **The call-phase exception is an assertion.** ``AssertionError``, or
   pytest's ``Failed`` from :func:`pytest.fail`, which is how a guard that
   catches a crash reports one. A raw ``AttributeError`` from a broken mutation
   is not evidence about the defect.

Anything else gets its own verdict token so it surfaces as a finding rather
than disappearing into a pass. Exit codes 2-5 — interrupted, internal error,
usage error, nothing collected — are rejected outright.

Usage::

    python tools/mutation_gate.py                 # every mutant
    python tools/mutation_gate.py --list          # ids and titles only
    python tools/mutation_gate.py --only m11-3    # one mutant
    python tools/mutation_gate.py --shard 2/10    # CI slice, 1-based
    python tools/mutation_gate.py --preflight     # collection check only

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import tempfile
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent
TOOLS = Path(__file__).resolve().parent
REGISTRY = PACKAGE / "tests" / "mutants.toml"

#: Call-phase exception types that count as a guard firing. ``Failed`` is
#: ``pytest.fail()``, which is how a guard that catches a crash reports one —
#: the failure then originates in the guard rather than in the mutation.
ASSERTION_TYPES = frozenset({"AssertionError", "Failed"})

#: pytest exit codes that are never evidence about a defect: 2 interrupted,
#: 3 internal error, 4 usage error, 5 nothing collected.
REJECTED_EXIT_CODES = frozenset({2, 3, 4, 5})

#: The one verdict that counts as proof.
RED = "RED"


@dataclass(frozen=True)
class Mutant:
    """One reintroduced defect and the guard that has to notice."""

    id: str
    title: str
    path: Path
    find: str
    replace: str
    test: str
    root: Path = field(default=PACKAGE, compare=False)

    @property
    def relative(self) -> str:
        try:
            return str(self.path.relative_to(self.root))
        except ValueError:  # pragma: no cover - a mutant outside the package
            return str(self.path)


@dataclass(frozen=True)
class Verdict:
    """What a run proved, and why it did or did not prove it."""

    token: str
    detail: str = ""

    @property
    def proved(self) -> bool:
        return self.token == RED


def load(registry: Path = REGISTRY, root: Path = PACKAGE) -> list[Mutant]:
    """Read the registry, failing loudly on a duplicate id or a missing file."""
    data = tomllib.loads(registry.read_text())
    mutants: list[Mutant] = []
    seen: set[str] = set()
    for entry in data["mutant"]:
        identifier = entry["id"]
        if identifier in seen:
            raise SystemExit(f"duplicate mutant id in {registry.name}: {identifier}")
        seen.add(identifier)
        path = root / entry["file"]
        if not path.exists():
            raise SystemExit(f"{identifier}: {entry['file']} does not exist")
        mutants.append(
            Mutant(
                id=identifier,
                title=entry["title"],
                path=path,
                find=entry["find"],
                replace=entry["replace"],
                test=entry["test"],
                root=root,
            )
        )
    return mutants


def interpreter(root: Path = PACKAGE) -> str:
    """The interpreter to run pytest with — the package venv when there is one."""
    local = root / ".venv" / "bin" / "python"
    return str(local) if local.exists() else sys.executable


def _run_pytest(
    node: str, *, root: Path, python: str, collect_only: bool = False
) -> dict:
    """Run one test and return the reporting plugin's structured result.

    Read from a file rather than parsed out of stdout, because parsing stdout
    for "did the guard fire" is precisely what this rewrite removes.
    """
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as handle:
        report_path = Path(handle.name)
    environment = dict(os.environ)
    environment["GATE_REPORT"] = str(report_path)
    environment["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(TOOLS), environment.get("PYTHONPATH", "")) if part
    )
    # A mutation the interpreter never loads is a mutation that proves nothing.
    #
    # CPython invalidates a cached ``.pyc`` on (source mtime, source size). A
    # great many real mutants are same-length edits — a flipped comparison, a
    # changed digit, `1` for `2` — so patch-then-rerun inside one mtime tick
    # leaves size identical and mtime unchanged, and the subprocess imports the
    # PRE-mutation bytecode. The guard then passes on code that was never
    # mutated and the run scores SURVIVED.
    #
    # Measured on this gate's own probe (`VALUE = 1` → `VALUE = 2`, both 9
    # bytes): 7 spurious SURVIVED in 10 runs without this line, 0 in 10 with it.
    # The failure is loud rather than silent — a false SURVIVED is a false
    # alarm, not a hidden defect — but a gate that reds at random is a gate
    # somebody switches off, which costs the same as one that never fired.
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        proc = subprocess.run(
            [
                python,
                "-m",
                "pytest",
                node,
                "-x",
                "-q",
                "--tb=no",
                "-p",
                "no:randomly",
                "-p",
                "gate_report",
                *(["--collect-only"] if collect_only else []),
            ],
            cwd=root,
            capture_output=True,
            text=True,
        env=environment,
        )
        if report_path.exists() and report_path.stat().st_size:
            report = json.loads(report_path.read_text())
        else:
            # The session died before ``pytest_sessionfinish`` — a usage error,
            # an internal error, or a crash during collection.
            report = {
                "collected": 0,
                "nodeids": [],
                "phases": {},
                "call_exception": None,
                "exitstatus": proc.returncode,
                "internal_error": False,
            }
        report["returncode"] = proc.returncode
        return report
    finally:
        report_path.unlink(missing_ok=True)


def _selection_verdict(report: dict, node: str) -> Verdict | None:
    """Reject anything that is not "exactly this one test ran"."""
    if report.get("internal_error"):
        return Verdict("INTERNAL-ERROR", "pytest raised an internal error")
    code = report.get("returncode")
    collected = report.get("collected", 0)
    if collected == 0:
        return Verdict(
            "NO-TEST",
            f"{node} selected no test (pytest exit {code}) — the node id names a "
            "module, class or method that does not exist",
        )
    if collected > 1:
        return Verdict(
            "AMBIGUOUS-NODE",
            f"{node} selected {collected} tests, so a verdict would be about some "
            "other test as much as this one",
        )
    if code in REJECTED_EXIT_CODES:
        return Verdict(
            f"PYTEST-EXIT-{code}",
            f"pytest exited {code}, which is never evidence about a defect",
        )
    return None


def _phase_verdict(report: dict) -> Verdict:
    """Read a completed single-test run as proof, or as something else."""
    phases = report.get("phases", {})
    for phase in ("setup", "teardown"):
        outcome = phases.get(phase)
        if outcome not in (None, "passed"):
            return Verdict(
                f"{phase.upper()}-ERROR",
                f"the {phase} phase {outcome} — a fixture that broke is not a "
                "guard that fired",
            )
    call = phases.get("call")
    if call == "skipped":
        return Verdict("SKIPPED", "the guard was skipped, so it proved nothing")
    if call == "passed":
        return Verdict("SURVIVED", "the guard passed with the defect back in")
    if call is None:
        return Verdict("NO-CALL", "the test never reached its call phase")
    exception = report.get("call_exception")
    if exception not in ASSERTION_TYPES:
        return Verdict(
            f"ERROR-{exception}",
            f"the guard raised {exception} rather than failing an assertion, so "
            "the mutation proved an error and not a defect",
        )
    return Verdict(RED)


def pristine_verdict(
    node: str, *, root: Path = PACKAGE, python: str | None = None
) -> Verdict:
    """The guard must be green *before* the mutation, or it proves nothing.

    "Green" means what pytest means by it, in every phase. This predicate read
    only ``setup`` and ``call`` while :func:`_phase_verdict` rejected a failed
    ``teardown`` on the mutated side — the two halves of one comparison
    disagreeing about what passing is. A guard whose fixture teardown fails is
    reported by pytest as ``1 passed, 1 error`` with **exit 1**: red in CI, and
    cached GREEN here. Its mutant then scored RED and counted as evidence, which
    is the precise failure this gate exists to make impossible, reintroduced in
    the clause meant to prevent it.

    ``teardown`` is compared against a passed/absent set rather than ``==
    "passed"`` because pytest omits the phase entirely when there is nothing to
    tear down, and an absent teardown is not a failed one.
    """
    report = _run_pytest(node, root=root, python=python or interpreter(root))
    rejected = _selection_verdict(report, node)
    if rejected is not None:
        return rejected
    phases = report.get("phases", {})
    if (
        phases.get("setup") == "passed"
        and phases.get("call") == "passed"
        and phases.get("teardown", "passed") == "passed"
    ):
        return Verdict("GREEN")
    return Verdict(
        "GUARD-NOT-GREEN",
        f"{node} does not pass on unmutated source ({phases}), so reddening it "
        "proves nothing about the mutation",
    )


def run_one(
    mutant: Mutant,
    *,
    root: Path | None = None,
    python: str | None = None,
    pristine: dict[str, Verdict] | None = None,
) -> Verdict:
    """Apply, run, restore. Returns the verdict for this mutant.

    The restore is in a ``finally`` and the original text is held in memory, so
    an interrupted run cannot leave a mutated file behind.
    """
    root = root or mutant.root
    python = python or interpreter(root)

    cached = pristine.get(mutant.test) if pristine is not None else None
    if cached is None:
        cached = pristine_verdict(mutant.test, root=root, python=python)
        if pristine is not None:
            pristine[mutant.test] = cached
    if cached.token != "GREEN":
        return cached

    original = mutant.path.read_text()
    occurrences = original.count(mutant.find)
    if occurrences == 0:
        return Verdict(
            "PATCH-MISS", "the text this mutant edits is no longer in the file"
        )
    if occurrences > 1:
        return Verdict(
            "AMBIGUOUS", f"the text this mutant edits appears {occurrences} times"
        )

    mutated = original.replace(mutant.find, mutant.replace, 1)
    try:
        compile(mutated, str(mutant.path), "exec")
    except SyntaxError as exc:
        return Verdict(
            "INVALID-MUTATION",
            f"the mutated source does not compile ({exc.msg}, line {exc.lineno}); a "
            "mutation must be valid Python or it proves the parser works",
        )

    try:
        mutant.path.write_text(mutated)
        report = _run_pytest(mutant.test, root=root, python=python)
    finally:
        mutant.path.write_text(original)

    rejected = _selection_verdict(report, mutant.test)
    return rejected if rejected is not None else _phase_verdict(report)


def shard(mutants: list[Mutant], spec: str) -> list[Mutant]:
    """The ``I/N`` slice of *mutants*, rejecting a spec that would pass vacuously.

    ``--shard 11/10`` used to select nothing and exit 0. A shard that runs no
    mutant and reports success is a green tick for work that did not happen —
    the same failure as certifying a collection error.
    """
    try:
        index_text, count_text = spec.split("/")
        index, count = int(index_text), int(count_text)
    except ValueError:
        raise SystemExit(
            f"malformed --shard {spec!r}; expected I/N with 1 <= I <= N"
        ) from None
    if count < 1 or not 1 <= index <= count:
        raise SystemExit(f"--shard {spec} is out of range; expected 1 <= I <= N")
    selected = [m for position, m in enumerate(mutants) if position % count == index - 1]
    if not selected:
        raise SystemExit(
            f"--shard {spec} selects no mutant out of {len(mutants)}; a shard that "
            "runs nothing must not report success"
        )
    return selected


def partition(mutants: list[Mutant], count: int) -> list[list[Mutant]]:
    """Every shard for *count*, so a caller can prove they tile the registry."""
    return [shard(mutants, f"{index}/{count}") for index in range(1, count + 1)]


def preflight(
    mutants: list[Mutant], *, root: Path = PACKAGE, python: str | None = None
) -> list[str]:
    """Every distinct guard collects exactly one test. Cheap, and run first.

    One ``--collect-only`` per distinct node id rather than per mutant, because
    the ten broken node IDs that made the first version of this gate lie were
    shared across ten entries.
    """
    python = python or interpreter(root)
    problems: list[str] = []
    for node in sorted({mutant.test for mutant in mutants}):
        # Read from the plugin, not from stdout. ``-q`` is already in this
        # project's addopts, so ``--collect-only -q`` collapses to "file: 1" and
        # a stdout parse counting "::" lines finds nothing — which would have
        # reported every guard broken. Parsing stdout for a verdict is the exact
        # mistake this rewrite exists to remove; doing it in the preflight would
        # have been the same bug one level down.
        report = _run_pytest(node, root=root, python=python, collect_only=True)
        collected = report.get("collected", 0)
        code = report.get("returncode")
        if code != 0 or collected != 1:
            owners = sorted(m.id for m in mutants if m.test == node)
            problems.append(
                f"{node} collects {collected} tests (pytest exit {code})"
                f" — named by {', '.join(owners)}"
            )
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="print ids and exit")
    parser.add_argument("--only", action="append", default=[], help="run one id")
    parser.add_argument("--shard", default=None, help="I/N, 1-based")
    parser.add_argument(
        "--preflight", action="store_true", help="check guard collection and exit"
    )
    parser.add_argument("--skip-preflight", action="store_true")
    args = parser.parse_args()

    for received in (signal.SIGINT, signal.SIGTERM):
        signal.signal(received, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))

    mutants = load()
    if args.only:
        wanted = set(args.only)
        mutants = [m for m in mutants if m.id in wanted]
        missing = wanted - {m.id for m in mutants}
        if missing:
            raise SystemExit(f"no such mutant: {', '.join(sorted(missing))}")
    if args.shard:
        mutants = shard(mutants, args.shard)
    if args.list:
        for mutant in mutants:
            print(f"{mutant.id:10} {mutant.relative:36} {mutant.title}")
        return 0

    if args.preflight or not args.skip_preflight:
        problems = preflight(mutants)
        if problems:
            print("PREFLIGHT FAILED — these guards do not name exactly one test:")
            for problem in problems:
                print(f"  {problem}")
            return 1
        guards = len({m.test for m in mutants})
        print(f"preflight: {guards} guards each collect exactly one test")
        if args.preflight:
            return 0

    cache: dict[str, Verdict] = {}
    failures: list[tuple[Mutant, Verdict]] = []
    for mutant in mutants:
        verdict = run_one(mutant, pristine=cache)
        print(f"  {verdict.token:18} {mutant.id:10} {mutant.title}", flush=True)
        if not verdict.proved:
            failures.append((mutant, verdict))

    print()
    print(
        f"{len(mutants) - len(failures)}/{len(mutants)} mutants ran their named guard "
        "and failed it on an assertion"
    )
    for mutant, verdict in failures:
        print(f"  {verdict.token} {mutant.id} ({mutant.relative}): {verdict.detail}")
        print(f"    guard: {mutant.test}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
