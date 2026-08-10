#!/usr/bin/env python3
"""Record the default-path render baseline for the variant-content seam (AJC-66).

Writes ``tests/golden/render_baseline.json``. Run this ONLY when a rendering
change is deliberate and reviewed — the whole value of the baseline is that it
was recorded before the seam existed and has not been quietly refreshed since.

    python scripts/record_render_baseline.py            # record
    python scripts/record_render_baseline.py --check    # verify, exit 1 on drift
"""

from __future__ import annotations

import argparse
import json
import os
import sys

_PACKAGE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PACKAGE_ROOT not in sys.path:
    sys.path.insert(0, _PACKAGE_ROOT)

from tests.render_baseline import BASELINE_PATH, compute_baseline  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Compare against the recorded baseline instead of rewriting it.",
    )
    args = parser.parse_args()

    computed = compute_baseline()

    if args.check:
        with open(BASELINE_PATH, encoding="utf-8") as fh:
            recorded = json.load(fh)
        drift = sorted(
            label
            for label in set(recorded) | set(computed)
            if recorded.get(label) != computed.get(label)
        )
        if drift:
            print(f"DRIFT in {len(drift)} of {len(computed)} render cases:")
            for label in drift:
                print(f"  {label}: recorded={recorded.get(label)} computed={computed.get(label)}")
            return 1
        print(f"OK — {len(computed)} render cases byte-identical to the baseline.")
        return 0

    os.makedirs(os.path.dirname(BASELINE_PATH), exist_ok=True)
    with open(BASELINE_PATH, "w", encoding="utf-8") as fh:
        json.dump(computed, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print(f"Recorded {len(computed)} render cases to {BASELINE_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
