#!/usr/bin/env python3
"""Record or verify the default-path render baseline for AJC-72.

Modes:
- --check validates live renders against the recorded payload.
- --record refreshes the entire payload from the current worktree.
- --restamp-provenance replays the detached pinned trunk recorder at ``BASE_COMMIT`` and
  replaces the feature payload with the pinned-base recording after verifying byte-identical
  cases. This updates more than ``_meta.note``: ``recorded_utc`` is regenerated each run.

Recording recipes:
- Run ``--record --base-ref <sha>`` from a clean detached worktree checked out at
  ``<sha>``.
- Run ``--restamp-provenance --base-worktree <path>`` with a detached base worktree
  pinned at ``BASE_COMMIT``.
- Use ``--output <path>`` to direct the output payload for ``--record`` and
  ``--restamp-provenance``; omitted, it uses the canonical package path.

Environment:
- ``AJC72_BASE_WORKTREE`` can override the base worktree path for
  ``--restamp-provenance``. This does not affect ``--check``/``--record``.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone


_PACKAGE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PACKAGE_ROOT not in sys.path:
    sys.path.insert(0, _PACKAGE_ROOT)


#: SHA-256 of the digest harness, as reviewed on this branch.
HARNESS_FILES: dict[str, str] = {
    "tests/render_baseline.py": "d9ff9bfc9ef212376070b4181dc453a538ec1624b61042e8bdd338fd67b002c7",
}


#: The immutable post-#38 trunk commit this recorder contract is anchored to.
BASE_COMMIT = "b0e77dd1b6fa949d2d5dc6a7f2d1a0c94ed6def3"

_BASE_GOLDEN_PAYLOAD = os.path.join(
    "packages",
    "merus-test-data-generator",
    "tests",
    "golden",
    "render_baseline.json",
)

PROVENANCE_NOTE = (
    "Recorded from a detached checkout at base_commit, the trusted post-#38 "
    "trunk before AJC-72. base_patches lists the only tracked files the "
    "base checkout differs on. Re-recording requires the same conditions; "
    "see this script's docstring."
)


_ALLOWED_UNTRACKED = frozenset({
    "tests/render_baseline.py",
    "scripts/record_render_baseline.py",
    "tests/golden/render_baseline.json",
})


_SOURCE_DIRS = ("data/", "pdf_templates/", "tests/", "scripts/", "orchestration/")

#: Tracked files the base checkout may legitimately carry a patch for.
_ALLOWED_BASE_PATCHES = frozenset()


def _git(*args: str, cwd: str = _PACKAGE_ROOT, text: bool = True) -> str | bytes:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=text,
        check=True,
    )
    return result.stdout.strip() if text else result.stdout


def _package_relative(cwd: str, path: str) -> str:
    prefix = _git("rev-parse", "--show-prefix", cwd=cwd).strip()
    if prefix and path.startswith(prefix):
        return path[len(prefix):]
    return path.strip()


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _read_json(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _write_json_atomically(payload: object, destination: str) -> None:
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    handle, tmp_path = tempfile.mkstemp(dir=os.path.dirname(destination), suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp_path, destination)
    except Exception:
        os.unlink(tmp_path)
        raise


def _status_paths(cwd: str, include_untracked: bool = False) -> list[str]:
    args = ["status", "--porcelain"]
    if not include_untracked:
        args.append("--untracked-files=no")
    raw = _git(*args, cwd=cwd).splitlines()
    paths: list[str] = []
    for line in raw:
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[-1]
        path = _package_relative(cwd, path)
        paths.append(path)
    return sorted(set(paths))


def _git_common_dir(cwd: str) -> str:
    raw = _git("rev-parse", "--git-common-dir", cwd=cwd).strip()
    if not os.path.isabs(raw):
        raw = os.path.join(cwd, raw)
    return os.path.realpath(raw)


def _exit(msg: str) -> None:
    sys.exit(msg)


def _verify_harness() -> dict[str, str]:
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
        _exit(
            "refusing to record: the digest harness is not the reviewed one:\n  - "
            + "\n  - ".join(problems)
        )
    return verified


def _resolve_base(base_ref: str | None) -> str:
    if base_ref is None:
        return BASE_COMMIT

    if base_ref.upper() in {"HEAD", "@"} or base_ref.startswith("HEAD"):
        _exit(
            f"refusing to record: --base-ref {base_ref!r} names the current checkout. "
            "The baseline exists to describe a commit the change under test is not in."
        )

    try:
        resolved = _git("rev-parse", f"{base_ref}^{{commit}}")
    except subprocess.CalledProcessError:
        _exit(f"refusing to record: --base-ref {base_ref!r} does not resolve to a commit")

    try:
        _git("merge-base", "--is-ancestor", resolved, "origin/main")
    except subprocess.CalledProcessError:
        _exit(
            f"refusing to record: {base_ref} ({resolved[:12]}) is not an ancestor of "
            "origin/main, so it is not a point in the trunk's history"
        )

    return resolved


def _refuse_unless_clean_base_checkout(base_commit: str) -> tuple[str, list[str]]:
    try:
        head = _git("rev-parse", "HEAD")
        tracked = _git("status", "--porcelain", "--untracked-files=no")
        untracked = _git("ls-files", "--others", "--exclude-standard")
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        _exit(f"refusing to record: cannot interrogate git ({exc})")

    problems: list[str] = []
    if head != base_commit:
        problems.append(f"HEAD is {head[:12]}, not the base commit {base_commit[:12]}")

    modified = sorted(_package_relative(_PACKAGE_ROOT, line[2:].strip()) for line in tracked.splitlines() if line.strip())
    disallowed = [path for path in modified if path not in _ALLOWED_BASE_PATCHES]
    if disallowed:
        problems.append(
            f"{len(disallowed)} disallowed tracked modification(s): " + ", ".join(disallowed[:5])
        )

    unexpected = sorted(
        path
        for path in (_package_relative(_PACKAGE_ROOT, p) for p in untracked.splitlines() if p.strip())
        if path.startswith(_SOURCE_DIRS) and path not in _ALLOWED_UNTRACKED
    )
    if unexpected:
        problems.append(
            "unexpected untracked source that could change a render: " + ", ".join(unexpected[:5])
        )

    if problems:
        _exit(
            "refusing to record the baseline:\n  - "
            + "\n  - ".join(problems)
            + f"\n\nA baseline recorded here would describe this tree, not {base_commit[:12]}, "
            "and a tree containing the change under test can bless itself."
        )

    return head, sorted(set(modified) & _ALLOWED_BASE_PATCHES)


def _verify_file_vs_blob(repo_root: str, base_root: str, relative: str) -> None:
    package_rel = os.path.relpath(base_root, repo_root)
    blob_path = os.path.join(package_rel, relative)
    blob = _git("show", f"{BASE_COMMIT}:{blob_path}", cwd=repo_root, text=False)
    with open(os.path.join(base_root, relative), "rb") as fh:
        current = fh.read()
    if current != blob:
        _exit(
            f"refusing to restamp: {relative} in base worktree is not the committed file "
            f"at {BASE_COMMIT}"
        )


def _validate_base_worktree(base_worktree: str) -> tuple[str, str]:
    try:
        base_repo = _git("rev-parse", "--show-toplevel", cwd=base_worktree).strip()
        feature_repo = _git("rev-parse", "--show-toplevel", cwd=_PACKAGE_ROOT).strip()
        base_common = _git_common_dir(base_worktree)
        feature_common = _git_common_dir(_PACKAGE_ROOT)
    except subprocess.CalledProcessError as exc:
        _exit(f"refusing to restamp: invalid base worktree {base_worktree!r}: {exc}")

    if base_common != feature_common:
        _exit("refusing to restamp: base worktree is not in this repository")

    head_ref = _git("rev-parse", "--abbrev-ref", "HEAD", cwd=base_worktree).strip()
    if head_ref != "HEAD":
        _exit(
            "refusing to restamp: base worktree is not detached; this mode requires "
            f"HEAD == {BASE_COMMIT[:12]}"
        )

    head_sha = _git("rev-parse", "HEAD", cwd=base_worktree).strip()
    if head_sha != BASE_COMMIT:
        _exit(
            f"refusing to restamp: base HEAD is {head_sha[:12]}, expected {BASE_COMMIT[:12]}"
        )

    if _status_paths(base_worktree, include_untracked=True):
        _exit("refusing to restamp: base worktree is not clean")

    base_package_root = os.path.join(base_repo, os.path.relpath(_PACKAGE_ROOT, feature_repo))
    _verify_file_vs_blob(base_repo, base_package_root, "tests/render_baseline.py")
    _verify_file_vs_blob(base_repo, base_package_root, "scripts/record_render_baseline.py")

    return base_repo, base_package_root


def _run_base_recorder(base_package_root: str) -> dict:
    baseline_path = os.path.join(base_package_root, "tests", "golden", "render_baseline.json")
    before = _status_paths(base_package_root, include_untracked=False)

    result = subprocess.run(
        [
            sys.executable,
            os.path.join(base_package_root, "scripts", "record_render_baseline.py"),
            "--record",
            "--base-ref",
            BASE_COMMIT,
        ],
        cwd=base_package_root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        _exit("base recorder failed:\n" + (result.stdout + result.stderr))

    after = _status_paths(base_package_root, include_untracked=False)
    changed = [path for path in after if path not in before]
    if any(path != "tests/golden/render_baseline.json" for path in changed):
        _exit(
            "base recorder changed files beyond tests/golden/render_baseline.json: "
            + ", ".join(changed or ["(none)"])
        )

    return _read_json(baseline_path)


def _cleanup_base_worktree(base_worktree: str, base_repo: str, base_package_root: str) -> None:
    try:
        _git(
            "restore",
            "--source=HEAD",
            "--staged",
            "--worktree",
            "--",
            _BASE_GOLDEN_PAYLOAD,
            cwd=base_repo,
        )
    except subprocess.CalledProcessError as exc:
        _exit(f"refusing to restamp: restore failed during cleanup ({exc})")

    try:
        detached = _git("rev-parse", "--abbrev-ref", "HEAD", cwd=base_worktree).strip()
        if detached != "HEAD":
            _exit("refusing to restamp: base worktree is not detached after cleanup")

        head = _git("rev-parse", "HEAD", cwd=base_worktree).strip()
        if head != BASE_COMMIT:
            _exit(
                f"refusing to restamp: base HEAD is {head[:12]}, expected {BASE_COMMIT[:12]} "
                "after cleanup"
            )

        if _git("status", "--porcelain", cwd=base_worktree).strip():
            _exit("refusing to restamp: base worktree is not clean after cleanup")

        _verify_file_vs_blob(base_repo, base_package_root, "tests/golden/render_baseline.json")
    except subprocess.CalledProcessError as exc:
        _exit(f"refusing to restamp: post-cleanup validation failed ({exc})")


def _structural_diff(left: object, right: object, prefix: str = "") -> list[str]:
    if type(left) != type(right):
        return [prefix[:-1] if prefix else "root"]

    if isinstance(left, dict) and isinstance(right, dict):
        diffs: list[str] = []
        keys = set(left) | set(right)
        for key in sorted(keys):
            if key not in left:
                diffs.append(prefix + key)
                continue
            if key not in right:
                diffs.append(prefix + key)
                continue
            diffs.extend(_structural_diff(left[key], right[key], f"{prefix}{key}."))
        return diffs

    if isinstance(left, list) and isinstance(right, list):
        if len(left) != len(right):
            return [prefix[:-1] if prefix else "root"]
        diffs: list[str] = []
        for index, (left_item, right_item) in enumerate(zip(left, right)):
            diffs.extend(_structural_diff(left_item, right_item, f"{prefix}[{index}]."))
        return diffs

    if left != right:
        return [prefix[:-1] if prefix else "root"]
    return []


def _rebase_provenance_payload(
    fresh_feature_payload: dict,
    fresh_base_payload: dict,
) -> dict:
    if _canonical_json_bytes(fresh_base_payload.get("cases")) != _canonical_json_bytes(
        fresh_feature_payload.get("cases"),
    ):
        _exit("base recorder cases do not match feature baseline pre-restamp cases")

    candidate = copy.deepcopy(fresh_base_payload)
    candidate.setdefault("_meta", {})["note"] = PROVENANCE_NOTE

    _assert_restamp_payload_delta_is_meta_note_only(fresh_base_payload, candidate)

    return candidate


def _assert_restamp_payload_delta_is_meta_note_only(
    fresh_base_payload: dict,
    candidate_payload: dict,
) -> None:
    diffs = sorted(_structural_diff(fresh_base_payload, candidate_payload))
    if diffs != ["_meta.note"]:
        _exit("restamp would change more than _meta.note: " + ", ".join(diffs))


def _rewrite_restamped_provenance_payload(
    feature_baseline_path: str,
    fresh_base_payload: dict,
) -> None:
    fresh_feature_payload = _read_json(feature_baseline_path)
    candidate = _rebase_provenance_payload(fresh_feature_payload, fresh_base_payload)
    _write_json_atomically(candidate, feature_baseline_path)


def _run_check_mode() -> int:
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


def _run_record_mode(
    base_ref: str | None,
    harness: dict[str, str],
    output: str | None = None,
) -> int:
    base_commit = _resolve_base(base_ref)
    source_commit, base_patches = _refuse_unless_clean_base_checkout(base_commit)

    from tests.render_baseline import ANCHOR_DATE, BASELINE_PATH, CASE_SEED, RENDER_SEED, compute_baseline

    baseline_path = output or BASELINE_PATH
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
            "note": PROVENANCE_NOTE,
        },
        "cases": compute_baseline(),
    }
    _write_json_atomically(payload, baseline_path)
    print(f"Recorded {len(payload['cases'])} cases from {source_commit[:12]} to {baseline_path}")
    return 0


def _run_restamp_mode(base_worktree: str, output: str | None = None) -> int:
    if _status_paths(_PACKAGE_ROOT, include_untracked=True):
        _exit("refusing to restamp: feature worktree is not clean")

    base_repo, base_package_root = _validate_base_worktree(base_worktree)
    feature_baseline_path = output or os.path.join(
        _PACKAGE_ROOT, "tests", "golden", "render_baseline.json"
    )
    try:
        fresh_base_payload = _run_base_recorder(base_package_root)
        base_meta = fresh_base_payload.get("_meta", {})
        if base_meta.get("base_commit") != BASE_COMMIT:
            _exit("base payload base_commit is not pinned")
        if base_meta.get("source_commit") != BASE_COMMIT:
            _exit("base payload source_commit is not pinned")
        if base_meta.get("base_patches") != []:
            _exit("base payload reported base patches")
        if base_meta.get("harness_sha256") != HARNESS_FILES:
            _exit("base payload did not carry the expected harness hash map")
    finally:
        _cleanup_base_worktree(base_worktree, base_repo, base_package_root)

    _rewrite_restamped_provenance_payload(feature_baseline_path, fresh_base_payload)
    print("Restamped provenance note from the pinned base worktree.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--check", action="store_true", help="Verify against recorded baseline.")
    modes.add_argument("--record", action="store_true", help="Rewrite baseline (gated).")
    modes.add_argument(
        "--restamp-provenance",
        action="store_true",
        help="Replay the pinned base tree and replace provenance with the pinned tree payload.",
    )
    parser.add_argument("--base-ref", default=None, help="Override base commit for --record only.")
    parser.add_argument("--base-worktree", default=None, help="Detached base worktree.")
    parser.add_argument("--output", default=None, help="Destination payload path for --record and --restamp-provenance.")

    args = parser.parse_args(argv)

    harness = _verify_harness()

    if args.restamp_provenance and args.base_ref is not None:
        _exit("--base-ref is forbidden with --restamp-provenance")
    if args.base_worktree is not None and not args.restamp_provenance:
        _exit("--base-worktree is supported only with --restamp-provenance")

    if args.check:
        return _run_check_mode()
    if args.restamp_provenance:
        if not args.base_worktree:
            _exit("must pass --base-worktree with --restamp-provenance")
        return _run_restamp_mode(args.base_worktree, args.output)
    return _run_record_mode(args.base_ref, harness, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
