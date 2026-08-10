import ast
import json
import os
import random
from collections import Counter
import shutil
import subprocess
from pathlib import Path

import pytest

import data.content_pools as content_pools
from tests.test_qme_apportionment_seam import QME_UNGOVERNED_DIGESTS


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = PACKAGE_ROOT / "tests" / "golden" / "content_pool_inventory.json"
PROBE_SCRIPT = PACKAGE_ROOT / "tests" / "ajc72_cross_python_probe.py"

with INVENTORY_PATH.open("r", encoding="utf-8") as fp:
    CONTENT_POOL_INVENTORY = json.load(fp)


def _resolve_interpreter(version: str) -> str | None:
    env_key = "AJC72_PYTHON310" if version == "3.10" else "AJC72_PYTHON312"
    requested = os.environ.get(env_key)
    fallback = "python3.10" if version == "3.10" else "python3.12"
    fallback_venv = PACKAGE_ROOT / ".venv" / "bin" / "python"

    candidates = [requested, fallback]
    if version == "3.12" and not requested:
        candidates.append(str(fallback_venv))

    for candidate in candidates:
        if not candidate:
            continue
        if version == "3.10":
            if Path(candidate).exists():
                return str(candidate)
            resolved = shutil.which(candidate)
            if resolved:
                return resolved
            continue

        if not Path(candidate).exists():
            candidate = shutil.which(candidate) or ""
            if not candidate:
                continue

        dep_probe = subprocess.run(
            [candidate, "-c", "import reportlab"],
            capture_output=True,
            text=True,
            check=False,
        )
        if dep_probe.returncode == 0:
            return str(candidate)

    return None


def _run_probe(interpreter: str) -> dict:
    env = os.environ.copy()
    env["PYTHONHASHSEED"] = "0"
    env["PYTHONPATH"] = str(PACKAGE_ROOT)
    result = subprocess.run(
        [interpreter, str(PROBE_SCRIPT)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.fail(
            f"interpreter probe failed for {interpreter}: {result.stderr or result.stdout}"
        )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        pytest.fail(f"interpreter probe for {interpreter} did not emit JSON: {result.stdout}")
        raise exc


def _inventory_entry(classifier: str, input_label: str) -> dict:
    for entry in CONTENT_POOL_INVENTORY[classifier]:
        if entry["input_label"] == input_label:
            return entry
    pytest.fail(f"missing inventory entry for {classifier}:{input_label}")


def _legacy_mtus_citations(body_parts: list[str], count: int) -> list[str]:
    categories: list[str] = []
    for bp in body_parts:
        bp_lower = bp.lower()
        if "spine" in bp_lower or "lumbar" in bp_lower or "cervical" in bp_lower:
            categories.extend(["spine_conservative", "spine_surgical"])
        elif any(kw in bp_lower for kw in ["shoulder", "elbow", "wrist", "hand"]):
            categories.append("upper_extremity")
        elif "psyche" in bp_lower:
            categories.append("opioid_guidelines")
        else:
            categories.append("physical_therapy")
    categories = list(set(categories))
    if not categories:
        categories = ["spine_conservative"]

    citations: list[str] = []
    for cat in categories:
        pool = content_pools.MTUS_GUIDELINE_CITATIONS.get(cat, [])
        if pool:
            citations.extend(random.sample(pool, min(2, len(pool))))
    random.shuffle(citations)
    return citations[:count]


def _expected_mtus_trace(body_parts: list[str]) -> list[tuple[str, int, int]]:
    categories: list[str] = []
    for bp in body_parts:
        bp_lower = bp.lower()
        if "spine" in bp_lower or "lumbar" in bp_lower or "cervical" in bp_lower:
            categories.extend(["spine_conservative", "spine_surgical"])
        elif any(kw in bp_lower for kw in ["shoulder", "elbow", "wrist", "hand"]):
            categories.append("upper_extremity")
        elif "psyche" in bp_lower:
            categories.append("opioid_guidelines")
        else:
            categories.append("physical_therapy")

    categories = sorted(set(categories))
    if not categories:
        categories = ["spine_conservative"]

    trace: list[tuple[str, int, int]] = []
    selected_count = 0
    for cat in categories:
        pool = content_pools.MTUS_GUIDELINE_CITATIONS.get(cat, [])
        if pool:
            k = min(2, len(pool))
            trace.append(("sample", len(pool), k))
            selected_count += k
    trace.append(("shuffle", selected_count, -1))
    return trace


def _trace_mtus_workload(
    callable_obj,
    body_parts: list[str],
    count: int,
) -> tuple[list[tuple[str, int, int]], list[str], list[list[str]]]:
    calls: list[tuple[str, int, int]] = []
    populations: list[list[str]] = []
    original_sample = random.sample
    original_shuffle = random.shuffle

    def patched_sample(population: list[str], k: int) -> list[str]:
        calls.append(("sample", len(population), k))
        populations.append(list(population))
        return original_sample(population, k)

    def patched_shuffle(population: list[str]) -> None:
        calls.append(("shuffle", len(population), -1))
        return original_shuffle(population)

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(random, "sample", patched_sample)
        monkeypatch.setattr(random, "shuffle", patched_shuffle)
        actual = callable_obj(body_parts=body_parts, count=count)

    return calls, actual, populations


def test_qme_text_and_pdf_digests_are_identical_on_python_310_and_312() -> None:
    py310 = _resolve_interpreter("3.10")
    py312 = _resolve_interpreter("3.12")

    if py310 is None:
        pytest.skip("python3.10 unavailable for probe cross-check")
    if py312 is None:
        pytest.fail("python3.12 unavailable for probe cross-check")

    probe_310 = _run_probe(py310)
    assert probe_310["python"] == [3, 10], (
        f"{py310} reported {probe_310['python']}; interpreter must be 3.10"
    )
    probe_312 = _run_probe(py312)
    assert probe_312["python"] == [3, 12], (
        f"{py312} reported {probe_312['python']}; interpreter must be 3.12"
    )

    assert probe_310["deps"]["reportlab"] == probe_312["deps"]["reportlab"], (
        "dependency drift is not AJC-72 drift"
    )

    digests_310 = probe_310["digests"]
    digests_312 = probe_312["digests"]
    assert set(digests_310) == set(digests_312)

    for variant in sorted(digests_310):
        m310 = digests_310[variant]
        m312 = digests_312[variant]
        assert m310["text"] == m312["text"], f"{variant} text mismatch across interpreters"
        assert m310["pdf"] == m312["pdf"], f"{variant} pdf mismatch across interpreters"
        assert m310["rng"] == m312["rng"], f"{variant} rng digest mismatch across interpreters"
        assert m310["story"] == m312["story"], f"{variant} story digest mismatch across interpreters"
        assert m310["rng"] == QME_UNGOVERNED_DIGESTS[variant]["rng"], (
            f"{variant} rng digest does not match the frozen seam constant"
        )
        assert m310["story"] == QME_UNGOVERNED_DIGESTS[variant]["story"], (
            f"{variant} story digest does not match the frozen seam constant"
        )
    assert probe_310["mtus_ordered_trace"] == probe_312["mtus_ordered_trace"]


def test_mtus_category_dedup_is_sorted_and_content_neutral() -> None:
    import inspect

    source = inspect.getsource(content_pools.get_mtus_citations)
    assert "categories = sorted(set(" in source, "categories should use sorted(set(...))"
    assert "categories = list(set(" not in source, "categories must avoid list(set(...))"

    cases = (
        ("fallback", []),
        ("single:spine", ["lumbar"]),
        ("single:upper_extremity", ["shoulder"]),
        ("single:psyche", ["depression"]),
        ("single:physical_therapy_default", ["ear"]),
        ("repeated:spine", ["lumbar", "lumbar"]),
        ("mixed:all_branches", ["lumbar", "shoulder", "depression", "ear"]),
    )

    for input_label, body_parts in cases:
        entry = _inventory_entry("mtus_citations_classifier", input_label)
        expected_items = entry["sorted_unique_items"]
        expected_count = entry["unique_count"]
        assert expected_count == len(expected_items)

        pre_calls, _, _ = _trace_mtus_workload(
            _legacy_mtus_citations,
            body_parts=body_parts,
            count=expected_count,
        )
        post_calls, post_actual, _ = _trace_mtus_workload(
            content_pools.get_mtus_citations,
            body_parts=body_parts,
            count=expected_count,
        )

        assert Counter(pre_calls) == Counter(post_calls)
        assert post_calls == _expected_mtus_trace(body_parts)
        captured_members = sorted(set(post_actual))
        assert len(captured_members) == expected_count
        assert captured_members == sorted(captured_members)


def test_future_medical_dedup_is_sorted_and_content_neutral() -> None:
    cases = (
        ("fallback", []),
        ("single:spine", ["lumbar"]),
        ("single:upper_extremity", ["shoulder"]),
        ("single:lower_extremity", ["knee"]),
        ("single:psyche", ["depression"]),
        ("repeated:spine", ["lumbar", "lumbar"]),
        ("mixed:all_branches", ["lumbar", "shoulder", "knee", "depression"]),
    )

    for input_label, body_parts in cases:
        entry = _inventory_entry("future_medical_classifier", input_label)
        expected_items = entry["sorted_unique_items"]
        expected_count = entry["unique_count"]

        captured: list[str] | None = None
        original_shuffle = random.shuffle

        def patched_shuffle(population: list[str]) -> None:
            nonlocal captured
            captured = list(population)
            return original_shuffle(population)

        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.setattr(random, "shuffle", patched_shuffle)
            content_pools.get_future_medical_items(body_parts=body_parts, count=expected_count)

        assert captured is not None
        assert captured == sorted(captured)
        captured_members = sorted({item for item in captured})
        assert captured_members == expected_items
        assert len(captured_members) == expected_count
        assert captured_members == sorted(captured_members)


def test_data_modules_contain_no_list_set_materialization() -> None:
    offenders: list[str] = []

    for file_path in (PACKAGE_ROOT / "data").rglob("*.py"):
        tree = ast.parse(file_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Name) or node.func.id != "list":
                continue
            if len(node.args) != 1:
                continue
            inner = node.args[0]
            if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name) and inner.func.id == "set":
                offenders.append(f"{file_path}:{node.lineno}")

    assert not offenders, "found list(set(...)) materialization sites:\n" + "\n".join(offenders)


def test_sorting_changes_only_pool_index_mapping_not_rng_schedule() -> None:
    seeds = (0, 1, 2, 3, 4)
    mtus_parts = ["lumbar", "shoulder", "depression"]
    future_parts = ["lumbar", "shoulder", "knee", "depression"]

    def trace_schedule(callable_obj, body_parts: list[str], count: int, seed: int):
        calls: list[tuple[str, int, int]] = []
        original_random = random.random
        original_sample = random.sample
        original_shuffle = random.shuffle

        def patched_random() -> float:
            calls.append(("random", -1, -1))
            return original_random()

        def patched_sample(population: list[str], k: int) -> list[str]:
            calls.append(("sample", len(population), k))
            return original_sample(population, k)

        def patched_shuffle(population: list[str]) -> None:
            calls.append(("shuffle", len(population), -1))
            return original_shuffle(population)

        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.setattr(random, "random", patched_random)
            monkeypatch.setattr(random, "sample", patched_sample)
            monkeypatch.setattr(random, "shuffle", patched_shuffle)
            random.seed(seed)
            callable_obj(body_parts=body_parts, count=count)
            return calls, random.getstate()

    # Frozen pre-change reference: this keeps today's list(set(...)) behavior.
    def frozen_mtus(body_parts: list[str], count: int) -> list[str]:
        categories: list[str] = []
        for bp in body_parts:
            bp_lower = bp.lower()
            if "spine" in bp_lower or "lumbar" in bp_lower or "cervical" in bp_lower:
                categories.extend(["spine_conservative", "spine_surgical"])
            elif any(kw in bp_lower for kw in ["shoulder", "elbow", "wrist", "hand"]):
                categories.append("upper_extremity")
            elif "psyche" in bp_lower:
                categories.append("opioid_guidelines")
            else:
                categories.append("physical_therapy")
        categories = list(set(categories))
        if not categories:
            categories = ["spine_conservative"]

        citations: list[str] = []
        for cat in categories:
            pool = content_pools.MTUS_GUIDELINE_CITATIONS.get(cat, [])
            if pool:
                citations.extend(random.sample(pool, min(2, len(pool))))
        random.shuffle(citations)
        return citations[:count]

    # Frozen pre-change reference: this keeps today's list(set(...)) behavior.
    def frozen_future_medical(body_parts: list[str], count: int) -> list[str]:
        items: list[str] = []
        for bp in body_parts:
            bp_lower = bp.lower()
            if "spine" in bp_lower or "lumbar" in bp_lower or "cervical" in bp_lower:
                items.extend(content_pools.FUTURE_MEDICAL_ITEMS.get("spine", []))
            elif any(kw in bp_lower for kw in ["shoulder", "elbow", "wrist", "hand"]):
                items.extend(content_pools.FUTURE_MEDICAL_ITEMS.get("upper_extremity", []))
            elif any(kw in bp_lower for kw in ["hip", "knee", "ankle", "foot"]):
                items.extend(content_pools.FUTURE_MEDICAL_ITEMS.get("lower_extremity", []))
            elif "psyche" in bp_lower:
                items.extend(content_pools.FUTURE_MEDICAL_ITEMS.get("psyche", []))

        if not items:
            items = content_pools.FUTURE_MEDICAL_ITEMS.get("spine", [])
        items = list(set(items))
        random.shuffle(items)
        return items[:count]

    for seed in seeds:
        mtus_ref_calls, _ = trace_schedule(frozen_mtus, mtus_parts, 8, seed)
        mtus_live_calls, _ = trace_schedule(
            content_pools.get_mtus_citations,
            mtus_parts,
            8,
            seed,
        )
        assert Counter(mtus_ref_calls) == Counter(mtus_live_calls)
        assert mtus_live_calls == _expected_mtus_trace(mtus_parts)
        assert len(mtus_ref_calls) == len(mtus_live_calls)

        future_ref_calls, future_ref_state = trace_schedule(
            frozen_future_medical,
            future_parts,
            8,
            seed,
        )
        future_live_calls, future_live_state = trace_schedule(
            content_pools.get_future_medical_items,
            future_parts,
            8,
            seed,
        )
        assert future_ref_calls == future_live_calls
        assert len(future_ref_calls) == len(future_live_calls)
        assert future_ref_state == future_live_state
