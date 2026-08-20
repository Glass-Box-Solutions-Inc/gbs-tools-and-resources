"""AJC-64 item 1 — M5 baseline instruments (spec Section 8 row 1).

Three independent oracles, per the frozen spec (rev 13.2, docs commit
``0f9c62d``, §6 M5-R30/M5-R30a/M5-R30b, §8 row 1):

1. **The six golden dicts at S2, byte-level.** S2 is "the post-remediation
   baseline, captured by item 1 (committed goldens as they then stand)"
   (M5-R30). This test freezes a witness copy of the six goldens as they
   stand right now into ``tests/fixtures/ajc64_item1_s2/`` and proves the
   live ``tests/golden/*.json`` are byte-identical to that witness — so the
   capture is faithful, not merely asserted.

2. **S2 - S0-GOLDEN equals the union of the three pre-lane allowlists,
   computed by an executed scalar diff, never asserted by hand** (M5-R30a).
   S0-GOLDEN was captured by item 0a before its first edit, into the build
   ledger at
   ``adjudica-documentation-rollback/Plans/.../execution/ajc64/s0/*.json``
   (outside this repository). Those six files are mirrored byte-for-byte
   into ``tests/fixtures/ajc64_item1_s0/`` so the proof is self-contained
   and reproducible in CI without a second checkout (DEVIATION — see
   module docstring note below).

3. **Literal pre-M5 channel key sets, and v1.1/v1.2 dispatch witnesses.**
   ``MONEY_CHANNEL_VERSION``, ``SUPPORTED_MONEY_CHANNEL_VERSIONS`` and the
   ``MONEY_V1_2_*`` constants are pinned by literal equality (M5-R27.3) —
   the guard for m24-23 MONEY-V1_3-GLOBAL-UPGRADE, which reintroduces a
   "helpful" bump of ``MONEY_CHANNEL_VERSION`` that would silently upgrade
   every existing corpus. The dispatch witnesses build real cases (not
   version-string checks) and prove each legacy money-channel version lands
   on its own distinct published-key set.

DEVIATION (classified: necessary adaptation, not a shortcut). The spec's
S0-GOLDEN ledger directory lives in a *different* repository
(``adjudica-documentation-rollback``) than this package. The work contract
for this item restricts edits to this worktree and forbids depending on a
second checkout being present in CI. Mirroring the six S0 files here as
committed fixtures preserves the spec's evidentiary intent (immutable,
never re-recorded, byte-identical to the ledger capture) while making the
proof self-contained. The mirrored bytes are verified byte-identical to the
ledger source at authoring time (sha256 recorded below); they are not
independently re-derived.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from wc_caseload_engine.planner import build_case_plan
from wc_caseload_engine.seeds import load_caseload_spec, resolve_caseload
from wc_caseload_engine.truth_manifest import (
    MONEY_CHANNEL_V1_0_VERSION,
    MONEY_CHANNEL_V1_1_VERSION,
    MONEY_CHANNEL_V1_2_VERSION,
    MONEY_CHANNEL_VERSION,
    MONEY_V1_2_PUBLISHED_GROUP_KEYS,
    SUPPORTED_MONEY_CHANNEL_VERSIONS,
    build_case_truth_manifest,
)

PACKAGE = Path(__file__).resolve().parents[1]
GOLDEN_DIR = PACKAGE / "tests" / "golden"
S0_FIXTURE_DIR = PACKAGE / "tests" / "fixtures" / "ajc64_item1_s0"
S2_FIXTURE_DIR = PACKAGE / "tests" / "fixtures" / "ajc64_item1_s2"

# The six shipped goldens at the time item 0a captured S0-GOLDEN, per M5-R30.
# Item 11 adds the seventh (money-m5-showcase) later; it does not exist yet.
GOLDEN_NAMES = (
    "demo-caseload",
    "doctrine-showcase",
    "medical-story-showcase",
    "money-showcase",
    "money-w2-showcase",
    "personas-showcase",
)

# ---------------------------------------------------------------------------
# S2 capture — FINAL (sequencing caveat DISCHARGED).
#
# This capture was originally provisional: sol's round-1 findings F1-F5 were
# landing concurrently on ajc-64-m5-lane-a and F2 was known to move rendered
# settlement prose. Those fix commits merged (ccd4f12) and the capture was
# re-taken against the resulting tree on 08-19, so the table below is the
# post-remediation baseline M5-R30 describes rather than a mid-flight
# snapshot. `money-showcase` carries F2's re-recorded digest.
# ---------------------------------------------------------------------------
S2_IS_PROVISIONAL = False  # re-captured 08-19 after F1-F5 fix commits (ccd4f12) merged to lane A

# sha256 of each mirrored tests/fixtures/ajc64_item1_s0/*.json, recorded at
# authoring time against the ledger source
# (adjudica-documentation-rollback/Plans/research/wcce-medical-story/
#  execution/ajc64/s0/*.json). A mismatch means the mirror drifted from the
# immutable ledger capture, which must never happen.
S0_SHA256 = {
    "demo-caseload": "f56160aa08dd6e6660a593b4d2e463c6a630c24277f5a6a6135b48ac41dd0e66",
    "doctrine-showcase": "11c0b95f5f4659112eaff4a04acc6eba96b6c63647f99d270c1e83dcaeb03df9",
    "medical-story-showcase": "60dff418398a4849eb3023f418e2deecc0d04f03ee8ed5b738309886dc2ed639",
    "money-showcase": "a8db048b3ad7b23a4c85bdf4732628ccf04f3b3f47cae99e6f760bf59ecda2ea",
    "money-w2-showcase": "e00f11ac65a0384164538bed2859e5ebd6a792ba318e784a8d1d08af34c4189f",
    "personas-showcase": "f89280b194ef08877b81a9876e38c9752e8460ad3cd5d7441cd4e156c4dd8275",
}

# sha256 of each frozen tests/fixtures/ajc64_item1_s2/*.json witness, i.e.
# the FINAL S2 capture this item ships.
S2_SHA256 = {
    "demo-caseload": "f56160aa08dd6e6660a593b4d2e463c6a630c24277f5a6a6135b48ac41dd0e66",
    "doctrine-showcase": "11c0b95f5f4659112eaff4a04acc6eba96b6c63647f99d270c1e83dcaeb03df9",
    "medical-story-showcase": "60dff418398a4849eb3023f418e2deecc0d04f03ee8ed5b738309886dc2ed639",
    "money-showcase": "540571c2689d3fa031aaf4065660439f39a3dab2d3cc20e5cccca4c7953e633a",
    "money-w2-showcase": "20bd48bbf99748beb87c2dc3f93fde2da61c352da07481122bfd4327c982d6c6",
    "personas-showcase": "f89280b194ef08877b81a9876e38c9752e8460ad3cd5d7441cd4e156c4dd8275",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Oracle 1 — the six golden dicts at S2, byte-level.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", GOLDEN_NAMES)
def test_r30_s2_fixture_mirrors_the_ledger_sha256(name: str) -> None:
    """The frozen S2 witness matches its recorded sha256 exactly."""
    assert _sha256(S2_FIXTURE_DIR / f"{name}.json") == S2_SHA256[name]


@pytest.mark.parametrize("name", GOLDEN_NAMES)
def test_r30_s0_fixture_mirrors_the_ledger_sha256(name: str) -> None:
    """The mirrored S0-GOLDEN evidence matches its recorded sha256 exactly."""
    assert _sha256(S0_FIXTURE_DIR / f"{name}.json") == S0_SHA256[name]


@pytest.mark.parametrize("name", GOLDEN_NAMES)
def test_r30_live_goldens_are_byte_identical_to_the_s2_capture(name: str) -> None:
    """S2 is a faithful capture: the live committed goldens equal it exactly,
    byte for byte. The F1-F5 fix round has landed and the capture was re-taken
    against it, so this is no longer expected to go red on that account — a
    failure here now means an unrecorded golden movement."""
    live = (GOLDEN_DIR / f"{name}.json").read_bytes()
    captured = (S2_FIXTURE_DIR / f"{name}.json").read_bytes()
    assert live == captured


def test_r30_exactly_six_goldens_exist_at_s2() -> None:
    """Item 11 adds the seventh golden later (M5-R30); at S2 there are six."""
    assert {p.stem for p in GOLDEN_DIR.glob("*.json")} == set(GOLDEN_NAMES)


# ---------------------------------------------------------------------------
# Oracle 2 — S2 - S0-GOLDEN equals the union of the three pre-lane
# allowlists, computed by an executed scalar diff (M5-R30a).
# ---------------------------------------------------------------------------


def _path_child(path: str, key: str | int) -> str:
    return f"{path}[{key}]" if isinstance(key, int) else f"{path}.{key}"


def _scalar_differences(old: Any, current: Any, path: str = "$") -> dict[str, tuple[Any, Any]]:
    """Return every leaf that changed, rejecting an added/removed/reordered
    shape at any level (mirrors the W2 item-1 oracle's diff discipline)."""
    if isinstance(old, Mapping) and isinstance(current, Mapping):
        assert set(old) == set(current), f"{path}: key set changed"
        changes: dict[str, tuple[Any, Any]] = {}
        for key in old:
            changes.update(_scalar_differences(old[key], current[key], _path_child(path, key)))
        return changes
    if isinstance(old, list) and isinstance(current, list):
        assert len(old) == len(current), f"{path}: length changed"
        changes = {}
        for index, (old_item, current_item) in enumerate(zip(old, current, strict=True)):
            changes.update(_scalar_differences(old_item, current_item, _path_child(path, index)))
        return changes
    assert not isinstance(old, (Mapping, list)) and not isinstance(current, (Mapping, list)), path
    return {} if old == current else {path: (old, current)}


def _collapse_to_axis_paths(leaf_paths: set[str]) -> set[str]:
    """Collapse leaf JSONPaths to the M5-R30a comparison axes: either a bare
    top-level key ($.corpusTree, $.caseload, ...) or $.cases.<id>.<key>."""
    axes: set[str] = set()
    for leaf in leaf_paths:
        # strip the leading "$." and split on the first two dotted segments
        rest = leaf[2:]  # drop "$."
        first_dot = rest.find(".")
        if first_dot == -1:
            axes.add(f"$.{rest.split('[')[0]}")
            continue
        top_key = rest[:first_dot]
        if top_key != "cases":
            axes.add(f"$.{top_key.split('[')[0]}")
            continue
        remainder = rest[first_dot + 1 :]
        case_dot = remainder.find(".")
        case_id = remainder[:case_dot]
        case_remainder = remainder[case_dot + 1 :]
        case_key = case_remainder.split(".")[0].split("[")[0]
        axes.add(f"$.cases.{case_id}.{case_key}")
    return axes


# FIX ROUND (Opus supervision, F1-HIGH): the original cut of this module
# exempted the whole $.recordedWith block via a startswith prefix match. That
# was a comparator-loosening, not a documented exemption: it silently
# swallowed $.recordedWith.substratePin's REAL movement on money-showcase
# along with the one field tests/golden/README.md actually exempts
# ("provenance.substrateSha, and nothing else" — README.md:100-102), and it
# would also have swallowed a hypothetical $.recordedWithX key by prefix
# accident. Corrected to exact-leaf-path matching, with the surviving
# substratePin movement handled on its own merits below rather than filtered
# out.
#
# Exactly one leaf is exempt everywhere, by exact path (never startswith):
# $.recordedWith.substrateSha is checkout-dependent provenance (`git log`
# over the substrate directory), the identical field the golden README
# documents as the sole exemption from its byte contract at the
# per-document level, applied here at the golden-summary level for the
# same reason — it describes the checkout, not the corpus bytes M5-R30a
# governs.
_EXEMPT_LEAF_PATHS = frozenset({"$.recordedWith.substrateSha"})

# $.recordedWith.substratePin moving on money-showcase is a SEPARATE,
# EXPLICITLY AUTHORIZED movement, not an exemption: item 0d's golden
# re-record was executed from the ajc-61 worktree checkout (a different
# substrate checkout than S0-GOLDEN's), and commit e5e0874
# ("[AJC-64] M5 pre-lane 0c/0d goldens — authorized re-record (money-w2
# facts, money-showcase labels) + R109 allowlist recordedWith provenance",
# an ancestor of this branch, verified via `git merge-base --is-ancestor
# e5e0874 HEAD`) extended the R109 allowlist for exactly this
# checkout-describing pair. `git show e5e0874 -- .../money-showcase.json`
# confirms both substratePin and substrateSha moved together there and
# $.caseload did NOT move in that commit. Recorded here as data, not
# filtered out of the diff: any OTHER $.recordedWith leaf moving still
# fails (test_r30a_recorded_with_movement_is_exactly_authorized below).
_AUTHORIZED_RECORDED_WITH_LEAVES: dict[str, frozenset[str]] = {
    "money-showcase": frozenset({"$.recordedWith.substratePin"}),
}

# The union of the three pre-lane allowlists (M5-R30a), expressed as the
# axis-collapsed form this module computes:
#   0a (§4751 paragraph substitution): documents, manifest, tree per
#       affected case; corpusTree. facts and seed must NOT move.
#   0c (authority_status cascade, M5-R30b): manifest, documents, tree,
#       facts per affected case; corpusTree. seed must NOT move; caseload
#       must NOT move.
#   0d (settlement label tokens): documents, manifest, tree per affected
#       case; corpusTree. facts and seed must NOT move.
# Union of per-case keys across all three: documents, manifest, tree, facts.
# Union of top-level keys: corpusTree.
_ALLOWED_CASE_KEYS = frozenset({"documents", "manifest", "tree", "facts"})
_ALLOWED_TOP_LEVEL_KEYS = frozenset({"corpusTree"})
_FORBIDDEN_CASE_KEYS = frozenset({"seed"})
_FORBIDDEN_TOP_LEVEL_KEYS = frozenset({"caseload"})


@pytest.fixture(scope="module")
def s0_s2_leaf_diff() -> dict[str, dict[str, tuple[Any, Any]]]:
    """The raw, unfiltered scalar diff S2 - S0-GOLDEN, per golden name.
    Nothing is excluded here — filtering happens downstream, on the merits,
    in the fixtures/tests that consume it."""
    return {
        name: _scalar_differences(
            _load(S0_FIXTURE_DIR / f"{name}.json"), _load(S2_FIXTURE_DIR / f"{name}.json")
        )
        for name in GOLDEN_NAMES
    }


@pytest.fixture(scope="module")
def s0_s2_axis_diff(
    s0_s2_leaf_diff: dict[str, dict[str, tuple[Any, Any]]],
) -> dict[str, set[str]]:
    """Collapse the non-recordedWith leaves to the M5-R30a comparison axes,
    per golden name. $.recordedWith is handled separately (its own leaf-level
    exemption plus one explicitly authorized movement) — see
    test_r30a_recorded_with_movement_is_exactly_authorized."""
    result: dict[str, set[str]] = {}
    for name, leaves in s0_s2_leaf_diff.items():
        leaf_paths = {path for path in leaves if not path.startswith("$.recordedWith.")}
        result[name] = _collapse_to_axis_paths(leaf_paths)
    return result


def test_r30a_recorded_with_movement_is_exactly_authorized(
    s0_s2_leaf_diff: dict[str, dict[str, tuple[Any, Any]]],
) -> None:
    """Every $.recordedWith.* leaf that moved is EITHER the one documented
    exemption ($.recordedWith.substrateSha) OR an explicitly authorized,
    cited movement ($.recordedWith.substratePin on money-showcase, per
    commit e5e0874). No other $.recordedWith leaf may move on any golden —
    this is an exact-path allowlist, never a prefix match."""
    for name, leaves in s0_s2_leaf_diff.items():
        moved_recorded_with = {path for path in leaves if path.startswith("$.recordedWith.")}
        authorized = _EXEMPT_LEAF_PATHS | _AUTHORIZED_RECORDED_WITH_LEAVES.get(name, frozenset())
        assert moved_recorded_with <= authorized, (
            f"{name}: unauthorized $.recordedWith movement {moved_recorded_with - authorized}"
        )


def test_r30a_money_showcase_substrate_pin_movement_matches_e5e0874(
    s0_s2_leaf_diff: dict[str, dict[str, tuple[Any, Any]]],
) -> None:
    """Positive control for the authorization above: the actual before/after
    values on money-showcase's substratePin/substrateSha match what
    `git show e5e0874 -- tests/golden/money-showcase.json` records, so the
    citation is verified against real commit content, not merely asserted."""
    leaves = s0_s2_leaf_diff["money-showcase"]
    assert leaves["$.recordedWith.substratePin"] == (
        "cb485354f16164ca2d422804fe9d40f9a2250920",
        "2168d066120c57f7585a2f674629979432ef674a",
    )
    assert leaves["$.recordedWith.substrateSha"] == (
        "70c8f3bed4c8df9b352e557e4128460798c62bfb",
        "2168d066120c57f7585a2f674629979432ef674a",
    )


def test_r30a_moved_axes_never_exceed_the_allowlist_union(
    s0_s2_axis_diff: dict[str, set[str]],
) -> None:
    """No path moved outside {corpusTree} UNION {cases.<id>.{documents,manifest,
    tree,facts}} for any of the six goldens — a moved path outside that set
    means an item touched more than its own allowlist permits (M5-R30a
    bidirectional exactness, forward arm)."""
    for name, axes in s0_s2_axis_diff.items():
        for axis in axes:
            parts = axis.split(".")
            if parts[1] == "cases":
                case_key = parts[3]
                assert case_key in _ALLOWED_CASE_KEYS, f"{name}: {axis} outside allowlist union"
            else:
                top_key = parts[1]
                assert top_key in _ALLOWED_TOP_LEVEL_KEYS, (
                    f"{name}: {axis} outside allowlist union"
                )


def test_r30a_seed_never_moves(s0_s2_axis_diff: dict[str, set[str]]) -> None:
    """$.cases.<id>.seed must NOT move under any of 0a/0c/0d (M5-R30a)."""
    for name, axes in s0_s2_axis_diff.items():
        for axis in axes:
            parts = axis.split(".")
            if parts[1] == "cases":
                assert parts[3] not in _FORBIDDEN_CASE_KEYS, f"{name}: {axis} must not move"


def test_r30a_caseload_never_moves(s0_s2_axis_diff: dict[str, set[str]]) -> None:
    """$.caseload must NOT move under 0c (M5-R30b, B3-round-8)."""
    for name, axes in s0_s2_axis_diff.items():
        for axis in axes:
            parts = axis.split(".")
            assert parts[1] != "caseload", f"{name}: {axis} must not move"


def test_r30a_money_and_money_w2_showcase_moved_as_expected(
    s0_s2_axis_diff: dict[str, set[str]],
) -> None:
    """Positive control: the executed diff actually found the two goldens
    0d and 0c touched (settlement labels; authority_status cascade), and
    the untouched four goldens (0a landed with no corpus movement per its
    own build ledger) show zero movement. A diff that found nothing would
    make the allowlist assertions above vacuous."""
    assert s0_s2_axis_diff["money-showcase"] == {
        "$.cases.capped-executive.documents",
        "$.cases.capped-executive.manifest",
        "$.cases.capped-executive.tree",
        "$.cases.irregular-earner.documents",
        "$.cases.irregular-earner.manifest",
        "$.cases.irregular-earner.tree",
        "$.cases.neglected-file.documents",
        "$.cases.neglected-file.manifest",
        "$.cases.neglected-file.tree",
        "$.cases.steady-earner.documents",
        "$.cases.steady-earner.manifest",
        "$.cases.steady-earner.tree",
        "$.corpusTree",
    }
    assert s0_s2_axis_diff["money-w2-showcase"] == {
        "$.cases.w2-file-review.documents",
        "$.cases.w2-file-review.facts",
        "$.cases.w2-file-review.manifest",
        "$.cases.w2-file-review.tree",
        "$.cases.w2-joint-evaluation.documents",
        "$.cases.w2-joint-evaluation.facts",
        "$.cases.w2-joint-evaluation.manifest",
        "$.cases.w2-joint-evaluation.tree",
        "$.cases.w2-reserve-development.documents",
        "$.cases.w2-reserve-development.facts",
        "$.cases.w2-reserve-development.manifest",
        "$.cases.w2-reserve-development.tree",
        "$.cases.w2-reserve-neighbor.documents",
        "$.cases.w2-reserve-neighbor.facts",
        "$.cases.w2-reserve-neighbor.manifest",
        "$.cases.w2-reserve-neighbor.tree",
        "$.cases.w2-reserve-reassessment.documents",
        "$.cases.w2-reserve-reassessment.facts",
        "$.cases.w2-reserve-reassessment.manifest",
        "$.cases.w2-reserve-reassessment.tree",
        "$.cases.w2-reserve-sequence.documents",
        "$.cases.w2-reserve-sequence.facts",
        "$.cases.w2-reserve-sequence.manifest",
        "$.cases.w2-reserve-sequence.tree",
        "$.corpusTree",
    }
    untouched_names = (
        "demo-caseload",
        "doctrine-showcase",
        "medical-story-showcase",
        "personas-showcase",
    )
    for name in untouched_names:
        assert s0_s2_axis_diff[name] == set(), f"{name}: expected zero movement, got a diff"


def test_r30a_every_moved_case_key_is_within_the_per_item_form(
    s0_s2_axis_diff: dict[str, set[str]],
) -> None:
    """0d's own allowlist form (M5-R30a) is {documents, manifest, tree} —
    facts must NOT move on money-showcase, the corpus 0d touches. 0c's own
    allowlist form is {manifest, documents, tree, facts} — money-w2-showcase
    is the corpus 0c touches and facts moving there is REQUIRED (M5-R30b),
    not merely permitted."""
    money_case_keys = {
        axis.split(".")[3]
        for axis in s0_s2_axis_diff["money-showcase"]
        if axis.split(".")[1] == "cases"
    }
    assert money_case_keys == {"documents", "manifest", "tree"}, "0d must not move facts"

    money_w2_case_keys = {
        axis.split(".")[3]
        for axis in s0_s2_axis_diff["money-w2-showcase"]
        if axis.split(".")[1] == "cases"
    }
    assert money_w2_case_keys == {"documents", "manifest", "tree", "facts"}, (
        "0c must move facts on every affected case (M5-R30b cascade)"
    )


# ---------------------------------------------------------------------------
# Oracle 3 — literal pre-M5 channel key sets; v1.1/v1.2 dispatch witnesses.
# m24-23 MONEY-V1_3-GLOBAL-UPGRADE guard (M5-R27.3).
# ---------------------------------------------------------------------------

EXPECTED_MONEY_VERSIONS = ("1.0.0", "1.1.0", "1.2.0")
EXPECTED_V1_2_PUBLISHED_KEYS = (
    "wage",
    "rate",
    "benefits",
    "rating",
    "defense",
    "settlement",
    "penalties",
)


def test_r27_money_channel_constants_are_literal() -> None:
    """m24-23 guard: MONEY_CHANNEL_VERSION is pinned at the literal DEFAULT
    WRITER version "1.1.0" — never the maximum supported version. A
    "helpful" bump of this constant is the single edit that would silently
    upgrade every existing corpus (M5-R27.3)."""
    assert MONEY_CHANNEL_V1_0_VERSION == "1.0.0"
    assert MONEY_CHANNEL_V1_1_VERSION == "1.1.0"
    assert MONEY_CHANNEL_V1_2_VERSION == "1.2.0"
    assert MONEY_CHANNEL_VERSION == "1.1.0"
    assert SUPPORTED_MONEY_CHANNEL_VERSIONS == EXPECTED_MONEY_VERSIONS
    assert MONEY_V1_2_PUBLISHED_GROUP_KEYS == EXPECTED_V1_2_PUBLISHED_KEYS


@pytest.fixture(scope="module")
def money_showcase_channel() -> dict[str, Any]:
    """steady-earner (money-showcase.yaml): no rating, no defense lens ->
    the v1.1.0 dispatch path."""
    spec = load_caseload_spec(PACKAGE / "examples" / "money-showcase.yaml")
    seeds = {seed.case_id: seed for seed in resolve_caseload(spec)}
    seed = seeds["steady-earner"]
    plan = build_case_plan(seed, case_number=1)
    payload = build_case_truth_manifest(plan)
    return payload["channels"]["money"]


@pytest.fixture(scope="module")
def money_w2_showcase_channel() -> dict[str, Any]:
    """w2-reserve-sequence (money-w2-showcase.yaml): rating AND a defense
    lens present -> the v1.2.0 dispatch path, with both optional groups."""
    spec = load_caseload_spec(PACKAGE / "examples" / "money-w2-showcase.yaml")
    seeds = {seed.case_id: seed for seed in resolve_caseload(spec)}
    seed = seeds["w2-reserve-sequence"]
    plan = build_case_plan(seed, case_number=1)
    payload = build_case_truth_manifest(plan)
    return payload["channels"]["money"]


def test_r27_v1_1_and_v1_2_dispatch_to_distinct_paths(
    money_showcase_channel: dict[str, Any],
    money_w2_showcase_channel: dict[str, Any],
) -> None:
    """Each legacy channel version dispatches to ITS OWN path — a witness
    fixture, not a version-string check. The 1.1.0 case carries no
    'rating'/'defense' keys at all; the 1.2.0 case carries both, and its
    key set is exactly the literal V1_2 published-group allowlist filtered
    to what that case actually has."""
    assert money_showcase_channel["channelVersion"] == "1.1.0"
    assert "rating" not in money_showcase_channel
    assert "defense" not in money_showcase_channel

    assert money_w2_showcase_channel["channelVersion"] == "1.2.0"
    assert "rating" in money_w2_showcase_channel
    assert "defense" in money_w2_showcase_channel
    assert set(money_w2_showcase_channel) <= set(EXPECTED_V1_2_PUBLISHED_KEYS) | {
        "channelVersion",
        "published",
    }


def test_r27_v1_1_and_v1_2_key_sets_are_disjoint_beyond_the_shared_core(
    money_showcase_channel: dict[str, Any],
    money_w2_showcase_channel: dict[str, Any],
) -> None:
    """The v1.2.0 witness has keys the v1.1.0 witness structurally cannot
    carry (rating, defense) — proving these are genuinely different
    dispatch paths, not the same path with an incidentally-absent field."""
    v1_1_keys = set(money_showcase_channel) - {"channelVersion"}
    v1_2_only_keys = set(money_w2_showcase_channel) - v1_1_keys - {"channelVersion"}
    assert v1_2_only_keys >= {"rating", "defense"}
