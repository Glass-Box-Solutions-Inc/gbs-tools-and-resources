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
import subprocess
import sys
from datetime import datetime, timezone

_PACKAGE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PACKAGE_ROOT not in sys.path:
    sys.path.insert(0, _PACKAGE_ROOT)

from tests.render_baseline import (  # noqa: E402
    ANCHOR_DATE,
    BASELINE_PATH,
    CASE_SEED,
    RENDER_SEED,
    compute_baseline,
    load_baseline_cases,
)

#: The ref a baseline may be recorded from. The seam does not exist there.
DEFAULT_BASE_REF = "origin/main"


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=_PACKAGE_ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()


def _refuse_unless_clean_base_checkout(base_ref: str) -> str:
    """Return the source commit, or exit non-zero explaining why not.

    Two conditions, both necessary. A dirty tree means the recorded bytes do not
    correspond to any commit anyone can check out again. A HEAD that is not the
    base ref means the recording came from a tree that may already contain the
    change the baseline is supposed to predate.
    """
    try:
        head = _git("rev-parse", "HEAD")
        base = _git("rev-parse", base_ref)
        # Tracked modifications only. Recording requires copying this script and
        # tests/render_baseline.py into the base checkout, where neither exists
        # yet, so untracked files are the normal state of a correct recording.
        # A tracked edit is the thing that would change what the substrate
        # renders, and that is what must block.
        dirty = _git("status", "--porcelain", "--untracked-files=no")
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        sys.exit(f"refusing to record: cannot interrogate git ({exc})")

    problems = []
    if dirty:
        changed = len(dirty.splitlines())
        problems.append(f"working tree is not clean ({changed} changed path(s))")
    if head != base:
        problems.append(f"HEAD is {head[:12]}, not {base_ref} ({base[:12]})")

    if problems:
        sys.exit(
            "refusing to record the baseline:\n  - "
            + "\n  - ".join(problems)
            + f"\n\nA baseline recorded here would describe this tree, not {base_ref}, "
            f"and a tree containing the change under test can bless itself.\n"
            f"Record from a clean detached checkout instead:\n"
            f"  git worktree add --detach /tmp/base {base_ref}\n"
            f"  # copy tests/render_baseline.py and this script into it, then run --record there"
        )
    return head


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="Verify against the recorded baseline.")
    group.add_argument("--record", action="store_true", help="Rewrite the baseline (gated).")
    parser.add_argument("--base-ref", default=DEFAULT_BASE_REF, help=f"default {DEFAULT_BASE_REF}")
    args = parser.parse_args()

    if args.check:
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

    source_commit = _refuse_unless_clean_base_checkout(args.base_ref)
    payload = {
        "_meta": {
            "source_commit": source_commit,
            "base_ref": args.base_ref,
            "anchor_date": ANCHOR_DATE.isoformat(),
            "render_seed": RENDER_SEED,
            "case_seed": CASE_SEED,
            "recorded_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "note": (
                "Recorded from a clean detached checkout at base_ref, before the "
                "AJC-66 variant-content seam existed. Re-recording requires the "
                "same conditions; see this script's docstring."
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
