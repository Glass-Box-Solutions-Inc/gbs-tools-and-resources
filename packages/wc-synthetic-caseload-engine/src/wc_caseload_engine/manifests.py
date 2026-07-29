"""Output writing and manifest validation.

Per-case output tree::

    <out>/<case_id>/
      seed.yaml          the surfaced contract — always materialized
      manifest.json      case facts + every document's checksum
      documents/<files>
    <out>/caseload_manifest.json

Two properties are load-bearing and deliberately engineered:

* **No wall-clock anywhere.** Manifests carry no generation timestamp, so two
  runs of the same spec produce byte-identical ``manifest.json`` files —
  including the MD5 of every rendered document. A timestamp field would have
  made the determinism guarantee unverifiable.
* **Nothing non-canonical escapes.** Every subtype written to a manifest is a
  classifier key with the classifier's parent type. ``validate --out`` re-checks
  that against the taxonomy, re-hashes every file, and exits nonzero on any
  drift — so a manifest can be trusted as classifier ground truth.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import structlog

from wc_caseload_engine import __version__
from wc_caseload_engine.case_facts import CaseFacts, facts_manifest_block
from wc_caseload_engine.planner import CasePlan, PlannedDocument, build_case_plan
from wc_caseload_engine.renderer import FORMAT_EXTENSIONS, RenderResult, render_document
from wc_caseload_engine.seeds import CaseSeed, write_case_seed
from wc_caseload_engine.substrate import check_substrate_pin, substrate_git_sha
from wc_caseload_engine.taxonomy import (
    EXPECTED_SUBTYPE_COUNT,
    SUBSTRATE_ONLY_SUBTYPES,
    effective_taxonomy,
)

log = structlog.get_logger(__name__)

GENERATOR = f"wc-synthetic-caseload-engine@{__version__}"
"""Provenance string recorded on every manifest."""

CORPUS_FILENAME_RE = re.compile(r"^(TC-\d{3})_(\d{3})_(.+)_(\d{4}-\d{2}-\d{2})\.pdf$")
"""The classifier's corpus sampling regex — corpus-mode PDFs must match it."""

MANIFEST_NAME = "manifest.json"
CASELOAD_MANIFEST_NAME = "caseload_manifest.json"
SEED_NAME = "seed.yaml"

CASE_FACTS_NAME = "case_facts.yaml"
"""The resolved clinical ledger, written beside the seed.

The seed states what was *asked for*; this states what was *decided*, including
every fact the seed left to derivation. Surfacing it makes the ledger reviewable
without rerunning the generator — the same reason auto-derived seeds are always
materialized rather than left implicit.
"""
DOCUMENTS_DIR = "documents"


def corpus_filename(case_number: int, document: PlannedDocument, extension: str) -> str:
    """``TC-###_###_<SUBTYPE>_<YYYY-MM-DD>.<ext>`` — the classifier corpus style."""
    return (
        f"TC-{case_number:03d}_{document.index + 1:03d}_{document.subtype}_"
        f"{document.doc_date.isoformat()}.{extension}"
    )


def neutral_filename(document: PlannedDocument, extension: str) -> str:
    """``###_<YYYY-MM-DD>.<ext>`` — sortable, and leaks no subtype.

    The default. A filename carrying the subtype would let a classifier score
    itself off the file name instead of the content, which makes accuracy
    measurement meaningless.
    """
    return f"{document.index + 1:03d}_{document.doc_date.isoformat()}.{extension}"


def filename_for(seed: CaseSeed, case_number: int, document: PlannedDocument) -> str:
    """Filename for a planned document, per the seed's ``output.filename_style``."""
    extension = FORMAT_EXTENSIONS[document.doc_format]
    if seed.output.filename_style == "corpus":
        return corpus_filename(case_number, document, extension)
    return neutral_filename(document, extension)


@dataclass(frozen=True, slots=True)
class CaseResult:
    """What one generated case produced."""

    case_id: str
    directory: Path
    plan: CasePlan
    renders: tuple[RenderResult, ...]
    manifest: dict[str, object]

    @property
    def document_count(self) -> int:
        """Number of rendered documents."""
        return len(self.renders)


def build_manifest(
    plan: CasePlan,
    renders: Sequence[tuple[str, RenderResult]],
) -> dict[str, object]:
    """Assemble a case manifest from a plan and its rendered files."""
    seed = plan.seed
    documents: list[dict[str, object]] = []
    for filename, render in renders:
        entry: dict[str, object] = {
            "filename": filename,
            "subtype": render.subtype,
            "type": effective_taxonomy().parent_of(render.subtype),
            "format": render.doc_format,
            "documentDate": render.doc_date.isoformat(),
            "md5Checksum": render.md5,
            "fileSize": render.size,
            "mimeType": render.mime_type,
            "template": render.template,
            "fallback": render.fallback,
        }
        if render.content_flags:
            # Present only when non-empty, so a hook-free caseload's manifests
            # are byte-identical to the ones it produced before doctrine content
            # existed. An empty list would be a silent diff on every document of
            # every case that never asked for a doctrine.
            entry["contentFlags"] = list(render.content_flags)
        documents.append(entry)

    manifest: dict[str, object] = {
        "caseId": seed.case_id,
        "perspective": seed.perspective,
        "stage": seed.lifecycle.target_stage,
        "resolution": seed.lifecycle.resolution.type,
        "injuryType": seed.injury.type,
        "claimResponse": seed.lifecycle.claim_response,
        "evalType": seed.lifecycle.eval_type,
        "doctrineHooks": list(seed.lifecycle.doctrine_hooks),
        # Emitted counts, not proposed ones: these summaries sit beside the
        # documents[] array and are read as facts about the folder.
        "liens": [
            track.summary(
                emitted=plan.lien_document_counts[index]
                if index < len(plan.lien_document_counts)
                else None
            )
            for index, track in enumerate(plan.lien_tracks)
        ],
        "recon": plan.recon.summary(
            emitted=plan.recon_document_count,
            emitted_subtypes=plan.recon_emitted_subtypes,
        ),
        "documents": documents,
        "provenance": {
            "zeroRealPii": plan.cast.zero_real_pii,
            "castProvenance": dict(sorted(plan.cast.provenance.items())),
            "generator": GENERATOR,
            "substrateSha": substrate_git_sha(),
            "seedHash": seed.seed_hash(),
            "rngSeed": seed.rng_seed,
        },
    }
    # Cast facts (adjNumber, applicant, employer, ...) sit next to caseId.
    cast_fields = plan.cast.manifest_fields()
    ordered: dict[str, object] = {"caseId": manifest.pop("caseId")}
    ordered["adjNumber"] = cast_fields.pop("adjNumber")
    ordered["applicant"] = cast_fields.pop("applicant")
    ordered.update(cast_fields)
    ordered.update(manifest)
    if plan.warnings:
        ordered["warnings"] = list(plan.warnings)
    if plan.case_facts is not None:
        # Published so a reader can check every coherence claim this
        # package makes against the documents, from the output alone.
        ordered["caseFacts"] = facts_manifest_block(plan.case_facts)
    return ordered


def _write_json(path: Path, payload: dict[str, object]) -> None:
    """Write deterministic, human-diffable JSON."""
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def generate_case(seed: CaseSeed, out_dir: Path, case_number: int = 1) -> CaseResult:
    """Generate one complete case: seed, documents and manifest.

    Args:
        seed: the case seed.
        out_dir: caseload output root; the case writes to ``out_dir/<case_id>``.
        case_number: 1-based position, used for corpus filenames.

    Returns:
        A :class:`CaseResult`.
    """
    plan = build_case_plan(seed, case_number=case_number)
    case_dir = out_dir / seed.case_id
    documents_dir = case_dir / DOCUMENTS_DIR
    documents_dir.mkdir(parents=True, exist_ok=True)

    write_case_seed(seed, case_dir / SEED_NAME)
    if plan.case_facts is not None:
        _write_case_facts(plan.case_facts, case_dir / CASE_FACTS_NAME)

    renders: list[tuple[str, RenderResult]] = []
    for document in plan.documents:
        filename = filename_for(seed, case_number, document)
        result = render_document(
            seed=seed,
            cast=plan.cast,
            subtype=document.subtype,
            doc_date=document.doc_date,
            doc_format=document.doc_format,
            index=document.index,
            out_path=documents_dir / filename,
            title=document.title,
            author_role=document.author_role,
            recipient_role=document.recipient_role,
            content_flags=document.content_flags,
            case_facts=plan.case_facts,
        )
        # A format fallback can change the extension; trust the written path.
        renders.append((result.path.name, result))

    manifest = build_manifest(plan, renders)
    _write_json(case_dir / MANIFEST_NAME, manifest)

    log.info(
        "case.generated",
        case_id=seed.case_id,
        documents=len(renders),
        liens=len(plan.lien_tracks),
        recon=plan.recon.enabled,
    )
    return CaseResult(
        case_id=seed.case_id,
        directory=case_dir,
        plan=plan,
        renders=tuple(result for _name, result in renders),
        manifest=manifest,
    )


def subtype_coverage(emitted: Collection[str]) -> dict[str, object]:
    """How much of the classifier taxonomy this caseload actually produced.

    The engine's taxonomy *is* the classifier's 353 subtypes, and it is easy to
    read "353-subtype taxonomy" as "emits all 353". It does not: a caseload emits
    what its seeds' lifecycles call for, which for a six-case demo is a few dozen.
    Stating the ratio in the manifest keeps anyone building a classifier accuracy
    corpus from mistaking vocabulary for coverage — the gap *is* the backlog of
    subtypes still needing targeted seeds.
    """
    total = EXPECTED_SUBTYPE_COUNT
    distinct = len(set(emitted))
    return {
        "distinctSubtypesEmitted": distinct,
        "totalCanonical": total,
        "percent": round(100.0 * distinct / total, 1) if total else 0.0,
    }


def build_caseload_manifest(caseload_id: str, results: Sequence[CaseResult]) -> dict[str, object]:
    """Aggregate case results into the caseload-level manifest."""
    formats: dict[str, int] = {}
    subtypes: set[str] = set()
    perspectives: dict[str, int] = {}
    templates: set[str] = set()
    fallbacks = 0
    total = 0
    cases: list[dict[str, object]] = []

    for result in results:
        total += result.document_count
        for render in result.renders:
            formats[render.doc_format] = formats.get(render.doc_format, 0) + 1
            subtypes.add(render.subtype)
            templates.add(render.template)
            fallbacks += int(render.fallback)
        plan = result.plan
        perspective = plan.seed.perspective
        perspectives[perspective] = perspectives.get(perspective, 0) + 1
        cases.append(
            {
                "caseId": result.case_id,
                "perspective": perspective,
                "adjNumber": plan.cast.adj_number,
                "applicant": plan.cast.applicant_name,
                "stage": plan.seed.lifecycle.target_stage,
                "resolution": plan.seed.lifecycle.resolution.type,
                "injuryType": plan.seed.injury.type,
                "documentCount": result.document_count,
                "lienCount": len(plan.lien_tracks),
                "lienResolution": plan.seed.lifecycle.liens.resolution,
                "reconEnabled": plan.recon.enabled,
                "reconOutcome": plan.recon.outcome,
                "postRecon": plan.recon.post_recon,
                "seedHash": plan.seed.seed_hash(),
            }
        )

    return {
        "caseloadId": caseload_id,
        "generator": GENERATOR,
        "caseCount": len(results),
        "documentCount": total,
        "formatCounts": dict(sorted(formats.items())),
        "perspectiveCounts": dict(sorted(perspectives.items())),
        "distinctSubtypes": len(subtypes),
        "subtypeCoverage": subtype_coverage(subtypes),
        "distinctTemplates": len(templates),
        "fallbackCount": fallbacks,
        "provenance": {
            "zeroRealPii": all(result.plan.cast.zero_real_pii for result in results),
            "generator": GENERATOR,
            "substrateSha": substrate_git_sha(),
        },
        "cases": cases,
    }


def generate_caseload(
    caseload_id: str, seeds: Iterable[CaseSeed], out_dir: Path
) -> list[CaseResult]:
    """Generate every case in a caseload and write the aggregate manifest."""
    check_substrate_pin()
    out_dir.mkdir(parents=True, exist_ok=True)
    results: list[CaseResult] = []
    for case_number, seed in enumerate(seeds, start=1):
        results.append(generate_case(seed, out_dir, case_number=case_number))
    _write_json(out_dir / CASELOAD_MANIFEST_NAME, build_caseload_manifest(caseload_id, results))
    return results


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ValidationReport:
    """Result of validating a generated output tree."""

    manifests: int = 0
    documents: int = 0
    fallbacks: int = 0
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """``True`` when nothing is wrong."""
        return not self.problems

    def render(self) -> str:
        """Human-readable validation report."""
        lines = [
            f"manifests : {self.manifests}",
            f"documents : {self.documents}",
            f"fallbacks : {self.fallbacks}",
        ]
        if self.ok:
            lines.append(
                "result    : OK — every subtype canonical, every checksum matches, "
                "every document rendered by its own template"
            )
        else:
            lines.append(f"result    : FAILED ({len(self.problems)} problem(s))")
            lines.extend(f"  {problem}" for problem in self.problems)
        return "\n".join(lines)


def validate_output_tree(out_dir: Path, allow_fallback: bool = False) -> ValidationReport:
    """Validate every manifest under *out_dir*.

    Checks, per document: the subtype is classifier vocabulary (and not a
    substrate-only realism subtype), the recorded parent type matches the
    taxonomy, the file exists, its MD5 and size match the manifest, and it was
    rendered by its own template rather than a fallback.

    Args:
        out_dir: a generated caseload root.
        allow_fallback: downgrade ``fallback: true`` documents from a failure to
            a counted observation. A corpus built for classifier training wants
            the failure; someone deliberately exercising the generic template
            wants the flag.
    """
    report = ValidationReport()
    taxonomy = effective_taxonomy()
    manifest_paths = sorted(out_dir.glob(f"*/{MANIFEST_NAME}"))

    if not manifest_paths:
        report.problems.append(f"{out_dir}: no case manifests found (expected */{MANIFEST_NAME})")
        return report

    for manifest_path in manifest_paths:
        report.manifests += 1
        case_label = manifest_path.parent.name
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            report.problems.append(f"{case_label}: manifest is not valid JSON — {exc}")
            continue

        provenance = manifest.get("provenance") or {}
        if provenance.get("zeroRealPii") is not True:
            report.problems.append(f"{case_label}: provenance.zeroRealPii is not true")
        if not provenance.get("generator"):
            report.problems.append(f"{case_label}: provenance.generator is missing")

        documents = manifest.get("documents")
        if not isinstance(documents, list):
            report.problems.append(f"{case_label}: manifest has no documents[] array")
            continue

        for entry in documents:
            report.documents += 1
            subtype = entry.get("subtype")
            filename = entry.get("filename", "<unnamed>")

            if entry.get("fallback") is True:
                report.fallbacks += 1
                if not allow_fallback:
                    report.problems.append(
                        f"{case_label}/{filename}: rendered by fallback template "
                        f"{entry.get('template')!r} instead of a template for {subtype!r} "
                        "(pass --allow-fallback to permit)"
                    )
            if not entry.get("template"):
                report.problems.append(
                    f"{case_label}/{filename}: manifest records no template provenance"
                )

            if not taxonomy.is_canonical(subtype):
                report.problems.append(
                    f"{case_label}/{filename}: subtype {subtype!r} is not a classifier key"
                )
            elif subtype in SUBSTRATE_ONLY_SUBTYPES:
                report.problems.append(
                    f"{case_label}/{filename}: subtype {subtype!r} is substrate-only vocabulary"
                )

            expected_parent = taxonomy.parent_of(subtype)
            if entry.get("type") != expected_parent:
                report.problems.append(
                    f"{case_label}/{filename}: type {entry.get('type')!r} does not match the "
                    f"taxonomy parent {expected_parent!r} for {subtype!r}"
                )

            document_path = manifest_path.parent / DOCUMENTS_DIR / filename
            if not document_path.is_file():
                report.problems.append(f"{case_label}/{filename}: file is missing")
                continue

            payload = document_path.read_bytes()
            actual_md5 = hashlib.md5(payload, usedforsecurity=False).hexdigest()
            if actual_md5 != entry.get("md5Checksum"):
                report.problems.append(
                    f"{case_label}/{filename}: md5 mismatch "
                    f"(manifest {entry.get('md5Checksum')}, file {actual_md5})"
                )
            if len(payload) != entry.get("fileSize"):
                report.problems.append(
                    f"{case_label}/{filename}: size mismatch "
                    f"(manifest {entry.get('fileSize')}, file {len(payload)})"
                )

    return report


__all__ = [
    "CASELOAD_MANIFEST_NAME",
    "CORPUS_FILENAME_RE",
    "DOCUMENTS_DIR",
    "GENERATOR",
    "MANIFEST_NAME",
    "SEED_NAME",
    "CaseResult",
    "ValidationReport",
    "build_caseload_manifest",
    "build_manifest",
    "corpus_filename",
    "filename_for",
    "generate_case",
    "generate_caseload",
    "neutral_filename",
    "subtype_coverage",
    "validate_output_tree",
]


def _write_case_facts(facts: CaseFacts, path: Path) -> None:
    """Write the resolved ledger beside the seed.

    YAML rather than JSON to match ``seed.yaml``: the two files are read
    together, and a reviewer should not have to change format between them.
    """
    import yaml

    header = (
        "# wc-caseload case facts \u2014 the resolved clinical ledger\n"
        "# Derived from the seed; every fact the seed did not state was decided here.\n"
        "# Documents render against this, and the manifest publishes it as 'caseFacts'.\n"
    )
    body = yaml.safe_dump(
        facts_manifest_block(facts), sort_keys=False, default_flow_style=False, allow_unicode=True
    )
    path.write_text(header + body, encoding="utf-8")
