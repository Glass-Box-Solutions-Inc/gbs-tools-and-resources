#!/usr/bin/env python3
"""Record or verify the default-path render baseline for AJC-66's seam.

The baseline's whole value is that it was recorded from code that predates the
seam. That is a property of *where it was recorded*, not of the file's contents,
and nothing in the file could show it — so recording is gated and the provenance
is written into the baseline itself.

    # verify (safe anywhere, this is what the test suite runs)
    python scripts/record_render_baseline.py --check

    # record — only from a clean checkout at the base ref
    git worktree add --detach /tmp/base origin/main
    cp tests/render_baseline.py scripts/record_render_baseline.py /tmp/base/...
    cd /tmp/base/packages/merus-test-data-generator
    python scripts/record_render_baseline.py --record

Recording from a feature branch is refused. Run unguarded, ``--record``
recomputes from whatever is checked out and overwrites the golden with it, which
means a tree containing the very change under test can bless itself — the
failure mode where a guard keeps passing and has stopped meaning anything.
"""

from __future__ import annotations

import argparse
import json
import os
import hashlib
import subprocess
import sys
from datetime import datetime, timezone

_PACKAGE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PACKAGE_ROOT not in sys.path:
    sys.path.insert(0, _PACKAGE_ROOT)


#: SHA-256 of the digest harness, as reviewed on this branch.
#:
#: Recording copies ``tests/render_baseline.py`` into the base checkout and then
#: imports ``compute_baseline`` **from that copy** to produce the trusted
#: baseline. Every other guard here — ancestry, tree cleanliness, provenance —
#: describes the *template sources*, and none of them looks at the harness doing
#: the hashing. A modified copy could drop cases or emit whatever digests it
#: liked and satisfy all of them.
#:
#: So the copy is verified byte-for-byte before it is imported, and the verified
#: hash is written into the baseline's provenance. Changing the harness is
#: legitimate and frequent; changing it *without updating this constant in a
#: reviewed diff* is what this refuses.
#:
#: Regenerate with:
#:   python -c "import hashlib,pathlib; print(hashlib.sha256(pathlib.Path('tests/render_baseline.py').read_bytes()).hexdigest())"
HARNESS_FILES: dict[str, str] = {
    "tests/render_baseline.py": "d9ff9bfc9ef212376070b4181dc453a538ec1624b61042e8bdd338fd67b002c7",
}


def _verify_harness() -> dict[str, str]:
    """Check the digest harness against its reviewed hash, before importing it."""
    verified: dict[str, str] = {}
    problems: list[str] = []
    for relative, expected in HARNESS_FILES.items():
        path = os.path.join(_PACKAGE_ROOT, relative)
        if not os.path.exists(path):
            problems.append(f"{relative} is missing from this checkout")
            continue
        with open(path, "rb") as fh:
            actual = hashlib.sha256(fh.read()).hexdigest()
        if actual != expected:
            problems.append(
                f"{relative} does not match its reviewed hash\n"
                f"      expected {expected}\n"
                f"      found    {actual}"
            )
        verified[relative] = actual
    if problems:
        sys.exit(
            "refusing to record: the digest harness is not the reviewed one:\n  - "
            + "\n  - ".join(problems)
            + "\n\nThe baseline is produced by importing this file, so an unverified "
            "copy could emit any digests it liked and still pass every other check. "
            "If the change is intended, update HARNESS_FILES in a reviewed diff."
        )
    return verified


#: The immutable post-#38 trunk commit this recorder contract is anchored to.
#:
#: ``--base-ref`` used to default to ``origin/main`` and accept anything, so
#: ``--record --base-ref HEAD`` on a clean feature branch satisfied every check
#: and blessed the tree under test. A guard whose subject is chosen by the
#: caller is not a guard.
BASE_COMMIT = "b0e77dd1b6fa949d2d5dc6a7f2d1a0c94ed6def3"

#: Files the recording procedure legitimately copies into the base checkout.
#: Nothing else may be untracked under the directories that determine what gets
#: rendered — an unexpected module there could be imported and change the
#: hashes, which is precisely what the baseline is supposed to rule out.
_ALLOWED_UNTRACKED = frozenset({
    "tests/render_baseline.py",
    "scripts/record_render_baseline.py",
    "tests/golden/render_baseline.json",
})

#: Directories whose contents can change a render.
_SOURCE_DIRS = ("data/", "pdf_templates/", "tests/", "scripts/", "orchestration/")


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=_PACKAGE_ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()


def _package_relative(path: str) -> str:
    """Strip git's repo-relative prefix so paths match the allowlists.

    ``git status`` reports from the repository root while every allowlist here
    is written package-relative. Without this, a path never matches an entry and
    the allowance silently never applies — the failure mode where a guard looks
    stricter than it is.
    """
    prefix = _git("rev-parse", "--show-prefix").strip()
    path = path.strip()
    if prefix and path.startswith(prefix):
        return path[len(prefix):]
    return path


def _resolve_base(base_ref: str | None) -> str:
    """The commit to record from, validating any caller-supplied override.

    An override must resolve to a commit that is an ancestor of ``origin/main``
    — a real point in the trunk's history — and must not be a symbolic alias for
    wherever the caller happens to be standing.
    """
    if base_ref is None:
        return BASE_COMMIT

    if base_ref.upper() in {"HEAD", "@"} or base_ref.startswith("HEAD"):
        sys.exit(
            f"refusing to record: --base-ref {base_ref!r} names the current checkout. "
            f"The baseline exists to describe a commit the change under test is not in."
        )
    try:
        resolved = _git("rev-parse", f"{base_ref}^{{commit}}")
    except subprocess.CalledProcessError:
        sys.exit(f"refusing to record: --base-ref {base_ref!r} does not resolve to a commit")

    try:
        _git("merge-base", "--is-ancestor", resolved, "origin/main")
    except subprocess.CalledProcessError:
        sys.exit(
            f"refusing to record: {base_ref} ({resolved[:12]}) is not an ancestor of "
            f"origin/main, so it is not a point in the trunk's history"
        )
    return resolved


#: Tracked files the base checkout may legitimately carry a patch for.
#:
#: Post-#38-trunk clock handling is now in place; this list is intentionally
#: empty unless a future exception is intentionally accepted.
_ALLOWED_BASE_PATCHES = frozenset()


def _refuse_unless_clean_base_checkout(base_commit: str) -> str:
    """Return the source commit, or exit non-zero explaining why not.

    Three conditions. HEAD must be the base commit, so the recording cannot come
    from a tree containing the change the baseline is supposed to predate. No
    tracked modifications, so the bytes correspond to a commit anyone can check
    out again. And no *unexpected* untracked source under the directories that
    determine a render — the previous revision ignored untracked files
    wholesale, which meant the very recorder implementation doing the hashing
    was exempt from the check it performs.
    """
    try:
        head = _git("rev-parse", "HEAD")
        tracked_dirty = _git("status", "--porcelain", "--untracked-files=no")
        untracked = _git("ls-files", "--others", "--exclude-standard")
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        sys.exit(f"refusing to record: cannot interrogate git ({exc})")

    problems = []
    if head != base_commit:
        problems.append(f"HEAD is {head[:12]}, not the base commit {base_commit[:12]}")

    modified = sorted(
        _package_relative(line[2:].strip())
        for line in tracked_dirty.splitlines()
        if line.strip()
    )
    disallowed = [path for path in modified if path not in _ALLOWED_BASE_PATCHES]
    if disallowed:
        problems.append(
            f"{len(disallowed)} disallowed tracked modification(s): " + ", ".join(disallowed[:5])
        )

    untracked_paths = [_package_relative(p) for p in untracked.splitlines() if p.strip()]
    unexpected = sorted(
        path for path in untracked_paths
        if path.startswith(_SOURCE_DIRS) and path not in _ALLOWED_UNTRACKED
    )
    if unexpected:
        problems.append(
            "unexpected untracked source that could change a render: " + ", ".join(unexpected[:5])
        )

    if problems:
        sys.exit(
            "refusing to record the baseline:\n  - "
            + "\n  - ".join(problems)
            + f"\n\nA baseline recorded here would describe this tree, not {base_commit[:12]}, "
            f"and a tree containing the change under test can bless itself.\n"
            f"Record from a clean detached checkout instead:\n"
            f"  git worktree add --detach /tmp/base {base_commit}\n"
            f"  # copy tests/render_baseline.py and this script into it, then run --record there"
        )
    return head, sorted(set(modified) & _ALLOWED_BASE_PATCHES)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="Verify against the recorded baseline.")
    group.add_argument("--record", action="store_true", help="Rewrite the baseline (gated).")
    parser.add_argument(
        "--base-ref",
        default=None,
        help="Override the pinned base commit. Must be an ancestor of origin/main "
             "and may not name HEAD.",
    )
    args = parser.parse_args()

    # Before either branch, and before any import of the harness. --check is not
    # the safe mode: it *is* the standalone gate, and it decides pass/fail by
    # asking the harness what the digests are. A harness whose compute_baseline
    # returned load_baseline_cases() would report every case identical forever,
    # so verifying only on the record path leaves the gate itself unguarded.
    #
    # It reads two local files and needs no git, no network and no arguments, so
    # running it first also means an environment problem can never mask a
    # tampered harness behind a message about something else.
    harness = _verify_harness()

    if args.check:
        from tests.render_baseline import compute_baseline, load_baseline_cases

        recorded = load_baseline_cases()
        computed = compute_baseline()
        drift = sorted(
            label
            for label in set(recorded) | set(computed)
            if recorded.get(label) != computed.get(label)
        )
        if drift:
            print(f"DRIFT in {len(drift)} of {len(computed)} render cases:")
            for label in drift:
                rec, cur = recorded.get(label, {}), computed.get(label, {})
                fields = sorted(k for k in set(rec) | set(cur) if rec.get(k) != cur.get(k))
                print(f"  {label}: differs on {fields}")
            return 1
        print(f"OK — {len(computed)} render cases byte-identical to the baseline.")
        return 0

    base_commit = _resolve_base(args.base_ref)
    source_commit, base_patches = _refuse_unless_clean_base_checkout(base_commit)

    # Imported only after the hash check above: this module is what computes the
    # digests the baseline is made of.
    from tests.render_baseline import ANCHOR_DATE, BASELINE_PATH, CASE_SEED, RENDER_SEED, compute_baseline
    payload = {
        "_meta": {
            "source_commit": source_commit,
            "base_commit": base_commit,
            "base_patches": base_patches,
            "harness_sha256": harness,
            "anchor_date": ANCHOR_DATE.isoformat(),
            "render_seed": RENDER_SEED,
            "case_seed": CASE_SEED,
            "recorded_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "note": (
                "Recorded from a detached checkout at base_commit, the trusted post-#38 "
                "trunk before AJC-72. base_patches lists the only tracked files the "
                "base checkout differs on. Re-recording requires the same conditions; "
                "see this script's docstring."
            ),
        },
        "cases": compute_baseline(),
    }
    os.makedirs(os.path.dirname(BASELINE_PATH), exist_ok=True)
    with open(BASELINE_PATH, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print(f"Recorded {len(payload['cases'])} cases from {source_commit[:12]} to {BASELINE_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
