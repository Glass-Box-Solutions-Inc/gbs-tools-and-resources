"""AJC-44/AJC-45 Money W2 work-item-1 baseline instruments.

Every expected value here comes from the frozen pre-W2 fixture, never from the
production result under test.  The fixture contains the complete five golden
dictionaries and hashes of the exact seven ``money-showcase`` truth bytes.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from conftest import requires_substrate
from wc_caseload_engine.case_facts import derive_case_facts
from wc_caseload_engine.lifecycle_bridge import build_timeline
from wc_caseload_engine.planner import build_case_plan
from wc_caseload_engine.seeds import (
    load_caseload_spec,
    parse_case_seed,
    resolve_caseload,
)
from wc_caseload_engine.truth_manifest import (
    MONEY_CHANNEL_VERSION,
    build_case_truth_manifest,
)

PACKAGE = Path(__file__).resolve().parents[1]
BASELINE_PATH = PACKAGE / "tests" / "fixtures" / "money_w2_pre_w2_baseline.json"
MONEY_SHOWCASE_PATH = PACKAGE / "examples" / "money-showcase.yaml"

EXPECTED_GOLDEN_NAMES = (
    "demo-caseload",
    "doctrine-showcase",
    "medical-story-showcase",
    "money-showcase",
    "personas-showcase",
)

EXPECTED_MONEY_TRUTH_FILES = (
    "atypical-earner.truth.json",
    "capped-executive.truth.json",
    "irregular-earner.truth.json",
    "neglected-file.truth.json",
    "new-hire.truth.json",
    "steady-earner.truth.json",
    "two-jobs.truth.json",
)

EXPECTED_FACT_STREAMS = (
    "facts:adjuster",
    "facts:attorney",
    "facts:benefits",
    "facts:diagnostics",
    "facts:discovery",
    "facts:surgery",
    "facts:trajectory",
    "facts:treatment",
)

PRE_W2_UNRELATED_FACTS_SHA256 = "dfc884345df742c1729fa26faf54147c56954fcba91c0cce4b85ef103198c7bc"


def _baseline() -> dict[str, Any]:
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def _truth_bytes(payload: Mapping[str, Any]) -> bytes:
    """Mirror the writer's timeless JSON bytes without touching the filesystem."""
    return (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


@pytest.fixture(scope="module")
def money_showcase_truth() -> dict[str, tuple[bytes, dict[str, Any]]]:
    spec = load_caseload_spec(MONEY_SHOWCASE_PATH)
    observed: dict[str, tuple[bytes, dict[str, Any]]] = {}
    for case_number, seed in enumerate(resolve_caseload(spec), start=1):
        plan = build_case_plan(seed, case_number=case_number)
        payload = build_case_truth_manifest(plan)
        observed[f"{seed.case_id}.truth.json"] = (_truth_bytes(payload), payload)
    return {name: observed[name] for name in EXPECTED_MONEY_TRUTH_FILES}


def _defense_construction_paths(value: Any, path: str = "$") -> tuple[str, ...]:
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key == "defenseConstruction":
                found.append(child_path)
            found.extend(_defense_construction_paths(child, child_path))
    elif isinstance(value, list):
        for child in value:
            found.extend(_defense_construction_paths(child, f"{path}[]"))
    return tuple(found)


def _facts_stream_registry(source: str) -> set[str]:
    """Literal ``_rng(seed, <family>)`` calls are the production registry."""
    tree = ast.parse(source)
    return {
        f"facts:{node.args[1].value}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_rng"
        and len(node.args) > 1
        and isinstance(node.args[1], ast.Constant)
        and isinstance(node.args[1].value, str)
    }


def _rating_absent_seed(eval_type: str) -> Any:
    return parse_case_seed(
        {
            "case_id": f"money-w2-rating-absent-{eval_type}",
            "rng_seed": 44001,
            "injury": {
                "type": "specific",
                "date_of_injury": "2021-06-14",
                "body_parts": [{"part": "lumbar_spine"}],
            },
            "lifecycle": {
                "target_stage": "medical_legal",
                "eval_type": eval_type,
            },
            "scenario": {"treatment": {"status": "ongoing"}},
            "output": {"formats": ["pdf"]},
            "documents": {"format_mix": {"pdf": 1.0}},
        }
    )


def test_all_five_golden_dictionaries_equal_the_exact_pre_w2_capture() -> None:
    """R99 Form A: dictionary equality, not a digest read from production."""
    expected = _baseline()["goldenDictionaries"]
    assert tuple(expected) == EXPECTED_GOLDEN_NAMES

    actual = {
        name: json.loads(
            (PACKAGE / "tests" / "golden" / f"{name}.json").read_text(encoding="utf-8")
        )
        for name in EXPECTED_GOLDEN_NAMES
    }
    assert actual == expected


@requires_substrate
def test_rating_absence_registry_retirement_and_unrelated_stream_bytes() -> None:
    """R101/R111/m23-24 Forms B/C: one guard reports every restored defect."""
    source_path = PACKAGE / "src" / "wc_caseload_engine" / "case_facts.py"
    source = source_path.read_text(encoding="utf-8")
    actual_registry = _facts_stream_registry(source)
    expected_registry = set(EXPECTED_FACT_STREAMS)

    # Form B: compare the production registry to the literal first; every
    # subsequent stream check iterates that literal, never production output.
    problems: list[str] = []
    if actual_registry != expected_registry:
        problems.append(
            f"facts stream registry {sorted(actual_registry)!r}, not {sorted(expected_registry)!r}"
        )
    for stream in EXPECTED_FACT_STREAMS:
        if not stream.startswith("facts:") or stream == "facts:rating":
            problems.append(f"invalid retained literal stream {stream!r}")

    # Form C positive control: one added literal call must be observed as the
    # retired family and nothing else.  It parses only; no recursive call runs.
    planted = source.replace(
        "def _body_parts(seed: CaseSeed) -> list[str]:",
        '_rng(seed, "rating")\n\ndef _body_parts(seed: CaseSeed) -> list[str]:',
        1,
    )
    planted_registry = _facts_stream_registry(planted)
    if planted_registry != expected_registry | {"facts:rating"}:
        problems.append(f"rating-stream positive control missed: {sorted(planted_registry)!r}")

    for eval_type in ("qme", "ame", "none"):
        seed = _rating_absent_seed(eval_type)
        facts = derive_case_facts(seed, build_timeline(seed))
        rating = getattr(seed.scenario, "rating", None)
        if not ((rating is None) == (facts.wpi is None) == (facts.pd is None)):
            problems.append(f"{eval_type}: rating={rating!r}, wpi={facts.wpi!r}, pd={facts.pd!r}")
        if eval_type == "qme":
            unrelated = facts.model_dump(mode="json", exclude={"wpi", "pd"})
            unrelated["adjuster_letter_types_allowed"] = sorted(
                unrelated["adjuster_letter_types_allowed"]
            )
            raw = json.dumps(
                unrelated,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
            digest = hashlib.sha256(raw).hexdigest()
            if digest != PRE_W2_UNRELATED_FACTS_SHA256:
                problems.append(
                    f"unrelated fact bytes {digest}, not {PRE_W2_UNRELATED_FACTS_SHA256}"
                )

    # TODO(AJC-44 R111): add exactly one scenario.rating-present neighboring
    # row when that input exists; the current schema genuinely has no rating field.
    assert "rating" not in type(_rating_absent_seed("qme").scenario).model_fields
    assert not problems, "\n".join(problems)


@requires_substrate
def test_seven_money_truth_bytes_are_exactly_pre_w2_at_channel_1_1_0(
    money_showcase_truth: dict[str, tuple[bytes, dict[str, Any]]],
) -> None:
    """R99/R105: seven literal byte hashes, versions, and channel field sets."""
    expected = _baseline()["moneyTruthFiles"]
    assert tuple(expected) == EXPECTED_MONEY_TRUTH_FILES
    assert tuple(money_showcase_truth) == EXPECTED_MONEY_TRUTH_FILES
    assert MONEY_CHANNEL_VERSION == "1.1.0"

    problems: list[str] = []
    for filename in EXPECTED_MONEY_TRUTH_FILES:
        raw, payload = money_showcase_truth[filename]
        channel = payload["channels"]["money"]
        pinned = expected[filename]
        digest = hashlib.sha256(raw).hexdigest()
        if digest != pinned["sha256"]:
            problems.append(f"{filename}: {pinned['sha256']} pinned, {digest} observed")
        if channel["channelVersion"] != "1.1.0":
            problems.append(
                f"{filename}: channelVersion {channel['channelVersion']!r}, not '1.1.0'"
            )
        if tuple(channel) != tuple(pinned["channelKeys"]):
            problems.append(
                f"{filename}: fields {tuple(channel)!r}, not {tuple(pinned['channelKeys'])!r}"
            )
    assert not problems, "\n".join(problems)


@requires_substrate
def test_defense_absent_baseline_has_a_live_one_input_positive_neighbor(
    money_showcase_truth: dict[str, tuple[bytes, dict[str, Any]]],
) -> None:
    """R105/m23-25 Form C: absence plus a one-field planted neighbor."""
    baseline_filename = "new-hire.truth.json"
    _raw, payload = money_showcase_truth[baseline_filename]
    channel = payload["channels"]["money"]
    assert _defense_construction_paths(channel) == ()

    positive = copy.deepcopy(channel)
    positive["defenseConstruction"] = {"method": "fabricated"}
    assert _defense_construction_paths(positive) == ("$.defenseConstruction",)
