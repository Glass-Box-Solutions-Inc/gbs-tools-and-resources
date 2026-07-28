"""Shared fixtures. No network access, no wall-clock dependence.

The demo caseload is generated once per session and shared. It takes about
seventy seconds to produce 331 documents, and three separate probes need to
read them: the real-entity denylist sweep, the case-identity sweep, and the
manifest-provenance regression. Generating it per module would triple that for
no additional evidence.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import email
import json
import zipfile
from pathlib import Path
from typing import Any

import pytest

from wc_caseload_engine.manifests import MANIFEST_NAME, generate_caseload
from wc_caseload_engine.seeds import load_caseload_spec, resolve_caseload
from wc_caseload_engine.substrate import find_substrate
from wc_caseload_engine.taxonomy import find_classifier

DEMO_SPEC = Path(__file__).resolve().parents[1] / "examples" / "demo-caseload.yaml"
"""The committed demo caseload — the caseload every published claim is about."""

SHOWCASE_SPEC = Path(__file__).resolve().parents[1] / "examples" / "doctrine-showcase.yaml"
"""The committed doctrine showcase — every hook supported, zero warnings.

The counterpart to :data:`DEMO_SPEC`, which deliberately carries two hooks its
cases cannot support. The user guide publishes this spec as the warning-free
run, so its warning count is a documented claim and is pinned as one.
"""

requires_substrate = pytest.mark.skipif(
    find_substrate() is None,
    reason="merus-test-data-generator substrate not on disk",
)

requires_classifier = pytest.mark.skipif(
    find_classifier() is None,
    reason="Adjudica-classifier source tree not on disk",
)


@pytest.fixture
def minimal_case() -> dict[str, Any]:
    """Smallest valid CaseSeed mapping."""
    return {
        "case_id": "probe-001",
        "rng_seed": 42,
        "injury": {
            "type": "specific",
            "date_of_injury": "2023-04-12",
            "body_parts": [{"part": "lumbar_spine", "icd10": "M54.5"}],
        },
    }


@pytest.fixture
def minimal_caseload(minimal_case: dict[str, Any]) -> dict[str, Any]:
    """Smallest valid CaseloadSpec mapping."""
    return {"caseload_id": "probe-load", "cases": [minimal_case]}


@pytest.fixture(scope="session")
def demo_caseload(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Generate the committed demo caseload once; return its output root."""
    if find_substrate() is None:
        pytest.skip("merus-test-data-generator substrate not on disk")
    out = tmp_path_factory.mktemp("demo-caseload")
    spec = load_caseload_spec(DEMO_SPEC)
    generate_caseload(spec.caseload_id, resolve_caseload(spec), out)
    return out


@pytest.fixture(scope="session")
def demo_manifests(demo_caseload: Path) -> dict[str, dict[str, Any]]:
    """Every demo case manifest, keyed by case id."""
    manifests: dict[str, dict[str, Any]] = {}
    for path in sorted(demo_caseload.glob(f"*/{MANIFEST_NAME}")):
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["_directory"] = str(path.parent)
        manifests[manifest["caseId"]] = manifest
    return manifests


NON_TEXT_FORMATS = frozenset({"scanned_pdf"})
"""Formats that carry no extractable text.

A scanned PDF is a raster of a page, which is the whole point of it — the text
probes below cannot read one. They are rendered from the same template and the
same cast as their native counterparts, so the *content* is covered; the blind
spot is per-file, not per-class, and every probe that relies on this says so.
"""


def extract_text(path: Path, doc_format: str) -> str:
    """Best-effort plain text from a rendered document.

    Returns ``""`` for formats that genuinely carry none, so callers can tell
    "no text in this file" from "this file does not have text to give".
    """
    if doc_format in NON_TEXT_FORMATS:
        return ""

    suffix = path.suffix.lower()
    if suffix == ".pdf":
        fitz = pytest.importorskip("fitz")
        with fitz.open(path) as document:
            return "\n".join(page.get_text() for page in document)

    if suffix == ".eml":
        message = email.message_from_bytes(path.read_bytes())
        chunks = [str(message.get(header, "")) for header in ("From", "To", "Subject")]
        for part in message.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    chunks.append(payload.decode("utf-8", errors="replace"))
        return "\n".join(chunks)

    if suffix == ".docx":
        # Read the XML directly rather than through python-docx: headers,
        # footers and table cells all matter to a name probe, and the
        # paragraph API silently skips some of them.
        with zipfile.ZipFile(path) as archive:
            parts = [
                archive.read(name).decode("utf-8", errors="replace")
                for name in archive.namelist()
                if name.startswith("word/") and name.endswith(".xml")
            ]
        return "\n".join(parts)

    return ""


def iter_documents(manifest: dict[str, Any]) -> list[tuple[dict[str, Any], Path]]:
    """``(manifest entry, path on disk)`` for every document of one case."""
    documents_dir = Path(manifest["_directory"]) / "documents"
    return [(entry, documents_dir / entry["filename"]) for entry in manifest["documents"]]
