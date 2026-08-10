"""Rendering, manifests and reproducibility.

These tests write real files, so they use small caps. They cover the three
promises a consumer relies on: every format actually opens in its own reader,
every manifest is honest classifier ground truth, and the same seed produces
the same bytes.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import email
import hashlib
import json
import subprocess
import sys
import zipfile
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml

from conftest import requires_substrate
from wc_caseload_engine.determinism import normalize_docx, normalize_pdf_id
from wc_caseload_engine.manifests import (
    CORPUS_FILENAME_RE,
    generate_case,
    generate_caseload,
    validate_output_tree,
)
from wc_caseload_engine.seeds import parse_case_seed
from wc_caseload_engine.taxonomy import SUBSTRATE_ONLY_SUBTYPES, effective_taxonomy

pytestmark = requires_substrate

MANIFEST_DOCUMENT_FIELDS = {
    "filename",
    "subtype",
    "type",
    "format",
    "documentDate",
    "md5Checksum",
    "fileSize",
    "mimeType",
    "template",
    "fallback",
}


def seed_dict(case_id: str = "render-001", **overrides: Any) -> dict[str, Any]:
    """A small, fast case that still exercises liens and reconsideration."""
    raw: dict[str, Any] = {
        "case_id": case_id,
        "rng_seed": 24680,
        "injury": {
            "type": "specific",
            "date_of_injury": "2022-02-02",
            "body_parts": [{"part": "lumbar_spine", "icd10": "M54.5"}],
        },
        "lifecycle": {
            "target_stage": "resolved",
            "resolution": {"type": "c_and_r"},
            "liens": {"count": 1, "resolution": "lien_resolution_agreement"},
        },
        "documents": {"global_cap": 10},
    }
    raw.update(overrides)
    return raw


@pytest.fixture(scope="module")
def rendered_case(tmp_path_factory: pytest.TempPathFactory) -> Any:
    """One fully rendered case, shared across the read-only assertions."""
    out = tmp_path_factory.mktemp("rendered")
    seed = parse_case_seed(
        seed_dict(
            documents={
                "global_cap": 16,
                "format_mix": {"pdf": 0.4, "scanned_pdf": 0.3, "eml": 0.2, "docx": 0.1},
            }
        )
    )
    return generate_case(seed, out, case_number=1)


# ---------------------------------------------------------------------------
# Output tree
# ---------------------------------------------------------------------------


def test_case_directory_contains_seed_manifest_and_documents(rendered_case: Any) -> None:
    directory = rendered_case.directory
    assert (directory / "seed.yaml").is_file()
    assert (directory / "manifest.json").is_file()
    assert (directory / "documents").is_dir()
    assert len(list((directory / "documents").iterdir())) == rendered_case.document_count


def test_seed_yaml_round_trips_back_into_an_identical_seed(rendered_case: Any) -> None:
    """The surfaced seed must actually regenerate the case."""
    written = yaml.safe_load((rendered_case.directory / "seed.yaml").read_text())
    assert parse_case_seed(written) == rendered_case.plan.seed


# ---------------------------------------------------------------------------
# Manifest schema and honesty
# ---------------------------------------------------------------------------


def test_manifest_carries_every_required_document_field(rendered_case: Any) -> None:
    manifest = rendered_case.manifest
    assert manifest["documents"]
    for entry in manifest["documents"]:
        assert set(entry) >= MANIFEST_DOCUMENT_FIELDS, (
            f"missing {MANIFEST_DOCUMENT_FIELDS - set(entry)}"
        )
        date.fromisoformat(entry["documentDate"])
        assert entry["fileSize"] > 0
        assert len(entry["md5Checksum"]) == 32


def test_manifest_carries_case_level_fields(rendered_case: Any) -> None:
    manifest = rendered_case.manifest
    for key in ("caseId", "adjNumber", "applicant", "stage", "resolution", "liens", "recon"):
        assert key in manifest, f"{key} missing from the manifest"
    assert manifest["adjNumber"].startswith("ADJ")
    assert len(manifest["adjNumber"]) == 11, "ADJ + 8 digits"


def test_manifest_provenance_asserts_zero_real_pii(rendered_case: Any) -> None:
    provenance = rendered_case.manifest["provenance"]
    assert provenance["zeroRealPii"] is True
    assert provenance["generator"].startswith("wc-synthetic-caseload-engine@")
    assert len(provenance["seedHash"]) == 64


def test_no_substrate_only_subtype_reaches_a_manifest(rendered_case: Any) -> None:
    """The 34 substrate realism subtypes are not classifier vocabulary."""
    taxonomy = effective_taxonomy()
    for entry in rendered_case.manifest["documents"]:
        assert entry["subtype"] not in SUBSTRATE_ONLY_SUBTYPES
        assert taxonomy.is_canonical(entry["subtype"])
        assert entry["type"] == taxonomy.parent_of(entry["subtype"])


def test_validate_accepts_a_freshly_generated_tree(rendered_case: Any) -> None:
    report = validate_output_tree(rendered_case.directory.parent)
    assert report.ok, report.render()
    assert report.documents == rendered_case.document_count


def test_validate_detects_a_tampered_document(tmp_path: Path) -> None:
    seed = parse_case_seed(seed_dict("tamper-001"))
    result = generate_case(seed, tmp_path, case_number=1)
    victim = next((result.directory / "documents").iterdir())
    victim.write_bytes(victim.read_bytes() + b"tampered")

    report = validate_output_tree(tmp_path)
    assert not report.ok
    assert any("md5 mismatch" in problem for problem in report.problems)


def test_validate_detects_a_missing_document(tmp_path: Path) -> None:
    seed = parse_case_seed(seed_dict("missing-001"))
    result = generate_case(seed, tmp_path, case_number=1)
    next((result.directory / "documents").iterdir()).unlink()

    report = validate_output_tree(tmp_path)
    assert not report.ok
    assert any("file is missing" in problem for problem in report.problems)


# ---------------------------------------------------------------------------
# Formats — each must open in its own reader
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def all_format_case(tmp_path_factory: pytest.TempPathFactory) -> Any:
    """A case seeded so all four formats certainly appear."""
    out = tmp_path_factory.mktemp("formats")
    seed = parse_case_seed(
        seed_dict(
            "formats-001",
            documents={
                "global_cap": 28,
                "format_mix": {"pdf": 0.25, "scanned_pdf": 0.25, "eml": 0.25, "docx": 0.25},
            },
        )
    )
    return generate_case(seed, out, case_number=1)


def test_all_four_formats_are_produced(all_format_case: Any) -> None:
    produced = {render.doc_format for render in all_format_case.renders}
    assert produced == {"pdf", "scanned_pdf", "eml", "docx"}, f"only got {produced}"


def test_every_pdf_is_a_real_pdf(all_format_case: Any) -> None:
    """Magic bytes, minimum size, and at least one page that actually parses."""
    fitz = pytest.importorskip("fitz")
    pdfs = [r for r in all_format_case.renders if r.doc_format in {"pdf", "scanned_pdf"}]
    assert pdfs
    for render in pdfs:
        payload = render.path.read_bytes()
        assert payload.startswith(b"%PDF-"), f"{render.path.name} is not a PDF"
        assert len(payload) > 500, f"{render.path.name} is only {len(payload)} bytes"
        with fitz.open(render.path) as document:
            assert document.page_count >= 1, f"{render.path.name} has no pages"


def test_every_eml_parses_as_a_message(all_format_case: Any) -> None:
    emls = [r for r in all_format_case.renders if r.doc_format == "eml"]
    assert emls
    for render in emls:
        message = email.message_from_bytes(render.path.read_bytes())
        assert message.get("From") and message.get("To") and message.get("Subject")
        assert message.get_payload(decode=True)


def test_every_docx_opens_as_a_document(all_format_case: Any) -> None:
    docx = pytest.importorskip("docx")
    files = [r for r in all_format_case.renders if r.doc_format == "docx"]
    assert files
    for render in files:
        document = docx.Document(str(render.path))
        assert document.paragraphs


def test_scanned_pdfs_differ_from_native_pdfs(all_format_case: Any) -> None:
    """Scan simulation must actually do something (rasterize + noise)."""
    native = [r for r in all_format_case.renders if r.doc_format == "pdf"]
    scanned = [r for r in all_format_case.renders if r.doc_format == "scanned_pdf"]
    assert native and scanned
    assert max(r.size for r in scanned) > max(r.size for r in native)


# ---------------------------------------------------------------------------
# Filenames
# ---------------------------------------------------------------------------


def test_neutral_filenames_do_not_leak_the_subtype(rendered_case: Any) -> None:
    """Default mode — a leaked subtype would let a classifier cheat."""
    for entry in rendered_case.manifest["documents"]:
        assert entry["subtype"] not in entry["filename"]


def test_corpus_filenames_match_the_classifier_regex(tmp_path: Path) -> None:
    seed = parse_case_seed(seed_dict("corpus-001", output={"filename_style": "corpus"}))
    result = generate_case(seed, tmp_path, case_number=7)
    pdfs = [
        entry["filename"]
        for entry in result.manifest["documents"]
        if entry["filename"].endswith(".pdf")
    ]
    assert pdfs
    for filename in pdfs:
        match = CORPUS_FILENAME_RE.match(filename)
        assert match, f"{filename} does not match the corpus regex"
        assert match.group(1) == "TC-007"


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_same_seed_produces_identical_manifests_in_process(tmp_path: Path) -> None:
    seed = parse_case_seed(seed_dict("det-001"))
    first = generate_case(seed, tmp_path / "a", case_number=1)
    second = generate_case(seed, tmp_path / "b", case_number=1)
    assert (first.directory / "manifest.json").read_bytes() == (
        second.directory / "manifest.json"
    ).read_bytes()


def test_same_seed_produces_identical_bytes_across_processes(tmp_path: Path) -> None:
    """The real guarantee: a fresh interpreter, and therefore a fresh hash salt.

    Without ``PYTHONHASHSEED`` pinning this fails, because the substrate orders
    content-pool items through a ``set`` of strings.
    """
    spec = tmp_path / "spec.yaml"
    spec.write_text(
        yaml.safe_dump({"caseload_id": "det-load", "cases": [seed_dict("det-002")]}),
        encoding="utf-8",
    )

    digests: list[dict[str, str]] = []
    for run in ("a", "b"):
        out = tmp_path / run
        completed = subprocess.run(
            [sys.executable, "-m", "wc_caseload_engine.cli", "generate",
             "--spec", str(spec), "--out", str(out)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr[-2000:]
        digests.append(
            {
                str(path.relative_to(out)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(out.rglob("*"))
                if path.is_file()
            }
        )

    first, second = digests
    assert set(first) == set(second), "the two runs wrote different files"
    drifted = sorted(name for name in first if first[name] != second[name])
    assert not drifted, f"{len(drifted)} file(s) drifted between runs: {drifted[:5]}"


def test_the_medical_layer_is_identical_across_processes(tmp_path: Path) -> None:
    """AJC-60. Fresh interpreters, and therefore fresh hash salts, with the layer on.

    The ledger is derived from a ``medical:`` rng namespace and from a memoised
    calibration solve. The memoisation is the reason this test exists as well as the
    in-process one: a cache is only ever an optimisation if two processes that filled
    it in different orders still agree, and ``lru_cache`` keyed on anything unstable —
    a set, a dict's iteration order — would not.
    """
    case = seed_dict("det-medical")
    case["profile"] = {"applicant": {"age": 47}}
    case["scenario"] = {
        "medical_history": {
            "conditions": [{"label": "essential hypertension", "key": "hypertension"}]
        }
    }
    spec = tmp_path / "spec.yaml"
    spec.write_text(
        yaml.safe_dump({"caseload_id": "det-medical-load", "cases": [case]}),
        encoding="utf-8",
    )

    digests: list[dict[str, str]] = []
    for run in ("a", "b"):
        out = tmp_path / run
        completed = subprocess.run(
            [sys.executable, "-m", "wc_caseload_engine.cli", "generate",
             "--spec", str(spec), "--out", str(out)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr[-2000:]
        digests.append(
            {
                str(path.relative_to(out)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(out.rglob("*"))
                if path.is_file()
            }
        )

    first, second = digests
    assert set(first) == set(second), "the two runs wrote different files"
    drifted = sorted(name for name in first if first[name] != second[name])
    assert not drifted, f"{len(drifted)} file(s) drifted with the medical layer on: {drifted}"


#: What the child interpreters below run. Inline rather than a scratch ``.py`` file
#: because a loose module in a working directory is how a stdlib name gets shadowed.
_LEDGER_PROBE = """
import hashlib, json, logging, sys
import structlog
from wc_caseload_engine.planner import build_case_plan
from wc_caseload_engine.seeds import parse_case_seed

# The engine logs the derivation at debug, timestamped. Left on, the wall clock
# would land in this probe's stdout and every run would "differ".
structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.CRITICAL)
)

plan = build_case_plan(parse_case_seed(json.loads(sys.argv[1])))
payload = plan.medical_history.model_dump(mode="json")
blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
print(_SENTINEL)
print(hashlib.sha256(blob.encode()).hexdigest())
print(blob)
""".replace("_SENTINEL", '"<<<LEDGER"')


def _canonical_digest(payload: object) -> str:
    """The child's digest function, reproduced so the parent can plant a control.

    ``sort_keys`` canonicalises *mapping* order — which is field-declaration order in
    a pydantic dump and carries no information — while leaving list order alone. That
    asymmetry is the point: sequence order in this ledger is a derivation fact, and a
    digest that sorted it away would agree across two processes that disagreed.
    """
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


def test_the_ledger_itself_is_identical_across_processes() -> None:
    """AJC-60 R2, finding 5. The tree comparison above cannot see this layer.

    Nothing about the ledger reaches any output file in M1 — deliberately, since M4
    owns the manifest channel — so comparing generated bytes across two interpreters
    proves the renderer is deterministic and says *nothing* about the object under
    test. The suite read as covering it while covering none of it.

    So each child builds the plan and prints a canonical digest of the ledger itself.
    The memoised calibration is the reason this needs separate processes rather than
    a loop: a cache is only an optimisation if two processes that filled it in
    different orders still agree, and one keyed on anything unstable would not.
    """
    case = seed_dict("det-ledger")
    case["profile"] = {"applicant": {"age": 47}}
    case["injury"]["body_parts"] = [
        {"part": "lumbar_spine"},
        {"part": "knee"},
    ]
    case["scenario"] = {
        "medical_history": {
            "conditions": [
                {"label": "essential hypertension", "key": "hypertension"},
                {"label": "type 2 diabetes mellitus", "key": "diabetes"},
            ]
        }
    }
    payload_arg = json.dumps(case)

    results: list[tuple[str, str]] = []
    for _ in range(2):
        completed = subprocess.run(
            [sys.executable, "-c", _LEDGER_PROBE, payload_arg],
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr[-2000:]
        assert "<<<LEDGER" in completed.stdout, completed.stdout[-2000:]
        digest, blob = completed.stdout.split("<<<LEDGER\n", 1)[1].strip().split("\n", 1)
        results.append((digest, blob))

    (first_digest, first_blob), (second_digest, _) = results
    assert first_digest == second_digest, (
        "the world-truth ledger differs between two fresh interpreters — the "
        "derivation is reading something the hash salt reorders"
    )

    ledger = json.loads(first_blob)
    assert len(ledger["conditions"]) >= 2, (
        "this probe needs at least two conditions or the order control below is "
        "vacuous; the seed has stopped producing them"
    )
    assert _canonical_digest(ledger) == first_digest, (
        "the parent's digest function has drifted from the child's, so the control "
        "below would be testing a different serialization than the comparison above"
    )


def test_the_ledger_digest_would_catch_a_reordering() -> None:
    """The planted control. A comparison that cannot fail proves nothing.

    Condition order in the ledger is a derivation fact — it follows the catalog's own
    iteration — so a future change that made it depend on set iteration or dict
    insertion would be a real determinism defect. This asserts the digest above is
    sensitive to exactly that, by reordering a ledger and watching it move.
    """
    ledger = {
        "archetype": "metabolic",
        "conditions": [
            {"key": "hypertension", "severity": "mild"},
            {"key": "diabetes", "severity": "moderate"},
        ],
        "prior_claims": [],
    }
    reordered = {**ledger, "conditions": list(reversed(ledger["conditions"]))}

    assert _canonical_digest(ledger) != _canonical_digest(reordered), (
        "reversing the condition list did not move the digest — the comparison in "
        "test_the_ledger_itself_is_identical_across_processes cannot see ordering, "
        "and would pass against a ledger whose order was nondeterministic"
    )
    assert _canonical_digest(ledger) == _canonical_digest(dict(reversed(list(ledger.items())))), (
        "reversing the ledger's own keys moved the digest, so the canonicalisation "
        "is not canonicalising mapping order after all"
    )


def test_normalize_docx_is_stable_and_uses_the_document_date(tmp_path: Path) -> None:
    """python-docx stamps wall-clock ZIP times; we repack them from the date."""
    docx = pytest.importorskip("docx")
    path = tmp_path / "sample.docx"
    document = docx.Document()
    document.add_paragraph("stable content")
    document.save(str(path))

    doc_date = date(2024, 3, 9)
    first = normalize_docx(path, doc_date)
    second = normalize_docx(path, doc_date)
    assert first == second

    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            assert info.date_time[:3] == (2024, 3, 9)


def test_normalize_pdf_id_is_deterministic() -> None:
    original = b"trailer\n<<\n/ID [<0123456789ABCDEF0123456789ABCDEF>"
    original += b"<FEDCBA9876543210FEDCBA9876543210>]\n>>"
    first = normalize_pdf_id(original, 42)
    second = normalize_pdf_id(original, 42)
    assert first == second
    assert first != original
    assert len(first) == len(original), "the hex form should be padded, not resized"
    assert normalize_pdf_id(original, 43) != first


def test_normalize_pdf_id_handles_a_literal_string_element() -> None:
    """PyMuPDF writes one element as a literal ``(...)`` when the bytes suit it.

    Matching only the hex form let roughly one scanned PDF in a hundred keep its
    random identifier, which broke byte-level reproducibility.
    """
    original = b'trailer\n<</Size 18/ID[<AABB0011AABB0011AABB0011AABB0011>(\\fYPv\x83hS"u)]>>'
    first = normalize_pdf_id(original, 7)
    assert first != original, "the literal-string form must still be normalized"
    assert first == normalize_pdf_id(original, 7)
    assert b"/ID[<" in first
    assert b'(\\fYPv\x83hS"u)' not in first


# ---------------------------------------------------------------------------
# Caseload level
# ---------------------------------------------------------------------------


def test_caseload_manifest_aggregates_every_case(tmp_path: Path) -> None:
    seeds = [
        parse_case_seed(seed_dict("agg-001")),
        parse_case_seed(
            seed_dict(
                "agg-002",
                lifecycle={
                    "target_stage": "post_recon",
                    "resolution": {"type": "findings_award"},
                    "reconsideration": {
                        "enabled": True,
                        "outcome": "denied",
                        "post_recon": "affirmed_final",
                    },
                },
            )
        ),
    ]
    results = generate_caseload("agg-load", seeds, tmp_path)
    manifest = json.loads((tmp_path / "caseload_manifest.json").read_text())

    assert manifest["caseloadId"] == "agg-load"
    assert manifest["caseCount"] == 2
    assert manifest["documentCount"] == sum(r.document_count for r in results)
    assert {case["caseId"] for case in manifest["cases"]} == {"agg-001", "agg-002"}
    recon_case = next(c for c in manifest["cases"] if c["caseId"] == "agg-002")
    assert recon_case["reconEnabled"] is True
    assert recon_case["reconOutcome"] == "denied"


def test_generation_writes_only_inside_the_output_directory(tmp_path: Path) -> None:
    """Anti-test: nothing may be written outside ``--out``."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    before = set(workspace.rglob("*"))

    out = tmp_path / "out"
    generate_caseload("scoped", [parse_case_seed(seed_dict("scoped-001"))], out)

    assert set(workspace.rglob("*")) == before
    assert out.exists()
