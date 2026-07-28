"""Manifests record which template produced each document, and whether it fell back.

The registry answers ``GenericDocumentTemplate`` both for "render this
generically" and for "I have never heard of this subtype". Downstream, a
manifest that recorded only the subtype could not tell the two apart — a
caseload whose dispatch had silently degraded looked exactly like one that had
not. That is the shape of the audit finding this file closes: not a crash, not
a wrong answer, but an unaskable question.

Two fields make it askable. ``template`` names the class and variant that ran;
``fallback`` says whether the document rendered as dispatched. ``validate --out``
then treats a fallback as a failure by default, because the corpus these files
exist to build is classifier ground truth, and a document rendered by the wrong
template is mislabelled data.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from conftest import requires_substrate
from wc_caseload_engine.manifests import (
    CASELOAD_MANIFEST_NAME,
    generate_case,
    validate_output_tree,
)
from wc_caseload_engine.renderer import GENERIC_TEMPLATE_CLASS, template_label
from wc_caseload_engine.seeds import parse_case_seed

pytestmark = requires_substrate


def _seed(case_id: str, **overrides: Any) -> Any:
    raw: dict[str, Any] = {
        "case_id": case_id,
        "rng_seed": 5150,
        "injury": {
            "type": "specific",
            "date_of_injury": "2022-07-07",
            "body_parts": [{"part": "knee", "icd10": "M23.51"}],
        },
        "lifecycle": {"target_stage": "resolved", "resolution": {"type": "c_and_r"}},
        "documents": {"global_cap": 12},
    }
    raw.update(overrides)
    return parse_case_seed(raw)


@pytest.fixture(scope="module")
def provenance_case(tmp_path_factory: pytest.TempPathFactory) -> Any:
    return generate_case(_seed("provenance-001"), tmp_path_factory.mktemp("provenance"))


# ---------------------------------------------------------------------------
# The two new per-document fields
# ---------------------------------------------------------------------------


def test_every_document_entry_records_a_template(provenance_case: Any) -> None:
    for entry in provenance_case.manifest["documents"]:
        assert entry["template"], f"{entry['filename']} records no template"
        assert entry["template"] != GENERIC_TEMPLATE_CLASS


def test_every_document_entry_records_a_fallback_flag(provenance_case: Any) -> None:
    for entry in provenance_case.manifest["documents"]:
        assert isinstance(entry["fallback"], bool)
    assert not any(entry["fallback"] for entry in provenance_case.manifest["documents"])


def test_the_manifest_template_matches_the_render_result(provenance_case: Any) -> None:
    """The manifest is a transcription, and transcriptions drift."""
    by_name = {render.path.name: render for render in provenance_case.renders}
    for entry in provenance_case.manifest["documents"]:
        render = by_name[entry["filename"]]
        assert entry["template"] == render.template
        assert entry["fallback"] == render.fallback


def test_template_label_formats_class_and_variant() -> None:
    assert template_label("CourtNotice", "penalty_5814") == "CourtNotice/penalty_5814"
    assert template_label("CourtNotice", None) == "CourtNotice"
    assert template_label("CourtNotice", "") == "CourtNotice"


def test_variants_are_visible_in_the_recorded_provenance(provenance_case: Any) -> None:
    """Several subtypes share a class and differ only by variant.

    Recording the class alone would make a lien notice and a trial notice
    indistinguishable in the manifest, which defeats the point of the field.
    """
    templates = {entry["template"] for entry in provenance_case.manifest["documents"]}
    assert any("/" in template for template in templates), (
        f"no variant reached the manifest: {sorted(templates)}"
    )


def test_caseload_manifest_summarizes_templates_and_fallbacks(tmp_path: Path) -> None:
    from wc_caseload_engine.manifests import generate_caseload

    results = generate_caseload("provenance-load", [_seed("agg-prov-001")], tmp_path)
    manifest = json.loads((tmp_path / CASELOAD_MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest["fallbackCount"] == 0
    assert manifest["distinctTemplates"] >= 1
    assert manifest["distinctTemplates"] <= sum(r.document_count for r in results)


# ---------------------------------------------------------------------------
# validate --out gating
# ---------------------------------------------------------------------------


def test_validate_accepts_a_tree_with_no_fallbacks(provenance_case: Any) -> None:
    report = validate_output_tree(provenance_case.directory.parent)
    assert report.ok, report.render()
    assert report.fallbacks == 0
    assert "fallbacks : 0" in report.render()


def test_validate_fails_on_a_fallback_document(tmp_path: Path) -> None:
    """Hand-edit one manifest entry — the gate must refuse the tree."""
    result = generate_case(_seed("fallback-001"), tmp_path)
    manifest_path = result.directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["documents"][0]["fallback"] = True
    manifest["documents"][0]["template"] = GENERIC_TEMPLATE_CLASS
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    report = validate_output_tree(tmp_path)
    assert not report.ok
    assert report.fallbacks == 1
    assert any("fallback template" in problem for problem in report.problems)


def test_allow_fallback_downgrades_the_failure_but_still_counts_it(tmp_path: Path) -> None:
    result = generate_case(_seed("fallback-002"), tmp_path)
    manifest_path = result.directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["documents"][0]["fallback"] = True
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    report = validate_output_tree(tmp_path, allow_fallback=True)
    assert report.ok, report.render()
    assert report.fallbacks == 1


def test_validate_fails_when_template_provenance_is_missing(tmp_path: Path) -> None:
    """An older manifest without the field is not silently accepted."""
    result = generate_case(_seed("no-template-001"), tmp_path)
    manifest_path = result.directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    del manifest["documents"][0]["template"]
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    report = validate_output_tree(tmp_path)
    assert not report.ok
    assert any("no template provenance" in problem for problem in report.problems)


def test_validate_cli_exposes_allow_fallback(tmp_path: Path) -> None:
    """The flag has to exist on the command line, not only in the function."""
    spec = tmp_path / "spec.yaml"
    spec.write_text(
        yaml.safe_dump(
            {
                "caseload_id": "cli-fallback",
                "cases": [
                    {
                        "case_id": "cli-fb-001",
                        "rng_seed": 606,
                        "injury": {
                            "type": "specific",
                            "date_of_injury": "2022-07-07",
                            "body_parts": [{"part": "knee", "icd10": "M23.51"}],
                        },
                        "documents": {"global_cap": 5},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "out"
    generate = subprocess.run(
        [sys.executable, "-m", "wc_caseload_engine", "generate",
         "--spec", str(spec), "--out", str(out)],
        capture_output=True, text=True, check=False,
    )
    assert generate.returncode == 0, generate.stderr[-2000:]

    manifest_path = next(out.glob("*/manifest.json"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["documents"][0]["fallback"] = True
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    strict = subprocess.run(
        [sys.executable, "-m", "wc_caseload_engine", "validate", "--out", str(out)],
        capture_output=True, text=True, check=False,
    )
    assert strict.returncode != 0, strict.stdout

    permissive = subprocess.run(
        [sys.executable, "-m", "wc_caseload_engine", "validate",
         "--out", str(out), "--allow-fallback"],
        capture_output=True, text=True, check=False,
    )
    assert permissive.returncode == 0, permissive.stdout + permissive.stderr[-2000:]
    assert "fallbacks : 1" in permissive.stdout


# ---------------------------------------------------------------------------
# The demo caseload — the artefact every published claim is about
# ---------------------------------------------------------------------------


def test_the_demo_caseload_contains_no_fallback_documents(
    demo_manifests: dict[str, dict[str, Any]],
) -> None:
    """The regression guard for the headline finding."""
    offences = [
        f"{case_id}/{entry['filename']} ({entry['subtype']} -> {entry['template']})"
        for case_id, manifest in sorted(demo_manifests.items())
        for entry in manifest["documents"]
        if entry["fallback"]
    ]
    assert not offences, f"{len(offences)} fallback document(s) in the demo: {offences[:20]}"


def test_every_demo_document_names_a_real_template(
    demo_manifests: dict[str, dict[str, Any]],
) -> None:
    templates: set[str] = set()
    for manifest in demo_manifests.values():
        for entry in manifest["documents"]:
            assert entry["template"], f"{entry['filename']} has no template"
            templates.add(entry["template"].split("/")[0])
    assert GENERIC_TEMPLATE_CLASS not in templates
    assert len(templates) >= 10, f"only {len(templates)} template classes across the demo"


def test_demo_validates_with_zero_fallbacks(demo_caseload: Path) -> None:
    report = validate_output_tree(demo_caseload)
    assert report.ok, report.render()
    assert report.fallbacks == 0
    assert report.documents > 300
