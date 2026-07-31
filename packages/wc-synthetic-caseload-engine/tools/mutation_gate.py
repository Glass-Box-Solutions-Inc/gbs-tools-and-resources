#!/usr/bin/env python3
"""Prove every registered guard still catches the defect it was written for.

A test that passes proves nothing on its own: it passes on the fixed code and
it may well pass on the broken code too. The only evidence that a guard is load
bearing is to put the defect back and watch that guard go red. This package did
that by hand for ten rounds, at the end of each round, from throwaway scripts —
and three separate rounds discovered that a guard written the round before had
never covered its own fix. Round 9 diagnosed it. Round 10 reproduced it
identically. A discipline that is remembered is a discipline that is
occasionally forgotten, so it is mechanized here and wired into CI.

The contract this enforces: **a fix may not be claimed until a mutation of that
exact fix has been shown to redden a test that names it.**

Each mutant in ``tests/mutants.toml`` names the edit that reintroduces one
defect and the test that must fail when it does. For every mutant this runner

1. checks the ``find`` text appears in the file **exactly once** — a mutation
   that matches twice is not the mutation it claims to be;
2. applies the edit;
3. runs the named test and requires it to **fail**;
4. restores the file.

Any mutant that no longer applies (PATCH-MISS) or that its test survives
(SURVIVED) is a hard failure naming the mutant. A PATCH-MISS is not
bookkeeping: it means the code under a guard moved and nobody re-checked that
the guard still reaches it.

Usage::

    python tools/mutation_gate.py                 # every mutant
    python tools/mutation_gate.py --list          # ids and titles only
    python tools/mutation_gate.py --only m11-3    # one mutant
    python tools/mutation_gate.py --shard 2/6     # CI slice, 1-based
"""

from __future__ import annotations

import argparse
import signal
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent
REGISTRY = PACKAGE / "tests" / "mutants.toml"


@dataclass(frozen=True)
class Mutant:
    """One reintroduced defect and the guard that has to notice."""

    id: str
    title: str
    path: Path
    find: str
    replace: str
    test: str

    @property
    def relative(self) -> str:
        return str(self.path.relative_to(PACKAGE))


def load(registry: Path = REGISTRY) -> list[Mutant]:
    """Read the registry, failing loudly on a duplicate id or a missing file."""
    data = tomllib.loads(registry.read_text())
    mutants: list[Mutant] = []
    seen: set[str] = set()
    for entry in data["mutant"]:
        identifier = entry["id"]
        if identifier in seen:
            raise SystemExit(f"duplicate mutant id in {registry.name}: {identifier}")
        seen.add(identifier)
        path = PACKAGE / entry["file"]
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
            )
        )
    return mutants


def _python() -> str:
    """The interpreter to run pytest with — the package venv when there is one."""
    local = PACKAGE / ".venv" / "bin" / "python"
    return str(local) if local.exists() else sys.executable


def run_one(mutant: Mutant, *, verbose: bool = False) -> tuple[str, str]:
    """Apply, run, restore. Returns a verdict and a one-line detail.

    The restore is in a ``finally`` and the original text is held in memory, so
    an interrupted run cannot leave a mutated file behind. ``SIGINT`` and
    ``SIGTERM`` are converted to exceptions for the same reason.
    """
    original = mutant.path.read_text()
    occurrences = original.count(mutant.find)
    if occurrences == 0:
        return "PATCH-MISS", "the text this mutant edits is no longer in the file"
    if occurrences > 1:
        return "AMBIGUOUS", f"the text this mutant edits appears {occurrences} times"
    try:
        mutant.path.write_text(original.replace(mutant.find, mutant.replace, 1))
        proc = subprocess.run(
            [
                _python(),
                "-m",
                "pytest",
                mutant.test,
                "-x",
                "-q",
                "--tb=no",
                "-p",
                "no:randomly",
            ],
            cwd=PACKAGE,
            capture_output=True,
            text=True,
        )
    finally:
        mutant.path.write_text(original)
    if verbose:
        print(proc.stdout[-2000:], file=sys.stderr)
    if proc.returncode == 0:
        return "SURVIVED", f"{mutant.test} passed with the defect back in"
    if "no tests ran" in proc.stdout or "ERROR" in proc.stdout.splitlines()[-1:]:
        return "NO-TEST", f"{mutant.test} did not select a test"
    return "RED", ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="print ids and exit")
    parser.add_argument("--only", action="append", default=[], help="run one id")
    parser.add_argument("--shard", default=None, help="I/N, 1-based")
    parser.add_argument("--verbose", action="store_true")
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
        index, count = (int(part) for part in args.shard.split("/"))
        mutants = [m for i, m in enumerate(mutants) if i % count == index - 1]
    if args.list:
        for mutant in mutants:
            print(f"{mutant.id:10} {mutant.relative:36} {mutant.title}")
        return 0

    failures: list[tuple[Mutant, str, str]] = []
    for mutant in mutants:
        verdict, detail = run_one(mutant, verbose=args.verbose)
        print(f"  {verdict:11} {mutant.id:10} {mutant.title}", flush=True)
        if verdict != "RED":
            failures.append((mutant, verdict, detail))

    print()
    print(f"{len(mutants) - len(failures)}/{len(mutants)} mutants reddened their guard")
    for mutant, verdict, detail in failures:
        print(f"  {verdict} {mutant.id} ({mutant.relative}): {detail}")
        print(f"    guard: {mutant.test}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
