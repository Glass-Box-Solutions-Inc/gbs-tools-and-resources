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
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import structlog

from wc_caseload_engine import __version__
from wc_caseload_engine.case_facts import (
    GOVERNED_LEDGER_FIELDS,
    MODALITIES,
    TREATMENT_STATUSES,
    CaseFacts,
    facts_manifest_block,
)
from wc_caseload_engine.money import (
    GOVERNED_MONEY_FIELDS,
    MoneyFacts,
)
from wc_caseload_engine.money import (
    money as quantized_money,
)
from wc_caseload_engine.planner import (
    CADENCE_ANCHOR_SUBTYPES,
    CasePlan,
    PlannedDocument,
    build_case_plan,
)
from wc_caseload_engine.renderer import FORMAT_EXTENSIONS, RenderResult, render_document
from wc_caseload_engine.seeds import AWW_METHODS, CaseSeed, write_case_seed
from wc_caseload_engine.substrate import check_substrate_pin, substrate_git_sha
from wc_caseload_engine.taxonomy import (
    EXPECTED_SUBTYPE_COUNT,
    SUBSTRATE_ONLY_SUBTYPES,
    effective_taxonomy,
)
from wc_caseload_engine.truth_manifest import (
    TRUTH_DIR,
    _write_json,
    write_case_truth_manifest,
    write_caseload_truth_manifest,
)

log = structlog.get_logger(__name__)

GENERATOR = f"wc-synthetic-caseload-engine@{__version__}"
"""Provenance string recorded on every manifest."""

CORPUS_FILENAME_RE = re.compile(r"^(TC-\d{3})_(\d{3})_(.+)_(\d{4}-\d{2}-\d{2})\.pdf$")
"""The classifier's corpus sampling regex — corpus-mode PDFs must match it."""

MANIFEST_NAME = "manifest.json"
CASELOAD_MANIFEST_NAME = "caseload_manifest.json"
SEED_NAME = "seed.yaml"

SUBPOENAED_RECORDS_SUBTYPES: frozenset[str] = frozenset(
    {
        "SUBPOENAED_RECORDS",
        "SUBPOENAED_RECORDS_MEDICAL",
        "SUBPOENAED_RECORDS_EMPLOYMENT",
        "SUBPOENAED_RECORDS_OTHER",
    }
)
"""The subtypes whose packets the provider round-robin advances over."""

ADJUSTER_LETTER_SUBTYPES: frozenset[str] = frozenset(
    {
        "ADJUSTER_LETTER",
        "ADJUSTER_LETTER_INFORMATIONAL",
        "ADJUSTER_LETTER_REQUEST",
        "ADJUSTER_DEMANDS_REQUESTS",
    }
)
"""The subtypes whose ordinal advances the adjuster-letter type sequence."""

TREATING_REPORT_SUBTYPES: frozenset[str] = frozenset(
    {
        "TREATING_PHYSICIAN_REPORT",
        "TREATING_PHYSICIAN_REPORT_PR2",
        "TREATING_PHYSICIAN_REPORT_PR4",
        "TREATING_PHYSICIAN_REPORT_FINAL",
    }
)
"""The subtypes whose ordinal advances the ledger's treatment trajectory."""

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
    truth_path: Path | None = None

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
        ordered["caseFacts"] = facts_manifest_block(plan.case_facts, plan.money_facts)
    return ordered


def generate_case(
    seed: CaseSeed,
    out_dir: Path,
    case_number: int = 1,
    truth_dir: Path | None = None,
) -> CaseResult:
    """Generate one complete case: seed, documents and manifest.

    Args:
        seed: the case seed.
        out_dir: caseload output root; the case writes to ``out_dir/<case_id>``.
        case_number: 1-based position, used for corpus filenames.
        truth_dir: scorer-only output directory, or ``None`` to preserve the
            historical case tree exactly.

    Returns:
        A :class:`CaseResult`.
    """
    plan = build_case_plan(seed, case_number=case_number)
    case_dir = out_dir / seed.case_id
    documents_dir = case_dir / DOCUMENTS_DIR
    documents_dir.mkdir(parents=True, exist_ok=True)

    write_case_seed(seed, case_dir / SEED_NAME)
    if plan.case_facts is not None:
        _write_case_facts(plan.case_facts, case_dir / CASE_FACTS_NAME, plan.money_facts)

    renders: list[tuple[str, RenderResult]] = []
    # Packets are counted separately from documents so the provider round-robin
    # advances once per records packet rather than once per file in the case.
    packet_counter = 0
    # Treating reports are counted separately again, because a trajectory has to
    # advance per *report*, not per document: two PRs at document indices 4 and
    # 19 must read as the first and second visit in the arc, not the fifth and
    # twentieth.
    report_counter = 0
    letter_counter = 0
    # ISC-125. The events an event_driven client letter may refer back to, taken
    # from the finished plan so the letter cites a document that is genuinely in
    # the folder. Built once: it is the same list for every letter, and each
    # letter picks the most recent entry preceding its own date.
    cadence_anchors: tuple[tuple[str, date], ...] = tuple(
        sorted(
            {
                (doc.subtype, doc.doc_date)
                for doc in plan.documents
                if doc.subtype in CADENCE_ANCHOR_SUBTYPES
            },
            key=lambda item: (item[1], item[0]),
        )
    )
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
            money_facts=plan.money_facts,
            packet_index=packet_counter,
            report_ordinal=report_counter,
            letter_ordinal=letter_counter,
            cadence_anchors=cadence_anchors,
        )
        if document.subtype in SUBPOENAED_RECORDS_SUBTYPES:
            packet_counter += 1
        if document.subtype in TREATING_REPORT_SUBTYPES:
            report_counter += 1
        if document.subtype in ADJUSTER_LETTER_SUBTYPES:
            letter_counter += 1
        # A format fallback can change the extension; trust the written path.
        renders.append((result.path.name, result))

    manifest = build_manifest(plan, renders)
    _write_json(case_dir / MANIFEST_NAME, manifest)
    truth_path = write_case_truth_manifest(plan, truth_dir) if truth_dir is not None else None

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
        truth_path=truth_path,
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
    caseload_id: str,
    seeds: Iterable[CaseSeed],
    out_dir: Path,
    truth: bool = True,
) -> list[CaseResult]:
    """Generate every case in a caseload and write the aggregate manifest."""
    check_substrate_pin()
    out_dir.mkdir(parents=True, exist_ok=True)
    truth_dir = out_dir / TRUTH_DIR if truth else None
    results: list[CaseResult] = []
    for case_number, seed in enumerate(seeds, start=1):
        results.append(
            generate_case(
                seed,
                out_dir,
                case_number=case_number,
                truth_dir=truth_dir,
            )
        )
    _write_json(out_dir / CASELOAD_MANIFEST_NAME, build_caseload_manifest(caseload_id, results))
    if truth_dir is not None:
        write_caseload_truth_manifest(caseload_id, results, truth_dir)
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


#: Subtypes that constitute proof an operation happened.
OPERATIVE_SUBTYPES = frozenset({"OPERATIVE_HOSPITAL_RECORDS"})


#: Documents that carry the money spine, by the part of it they render.
#:
#: Used by the validator both ways: money published with none of these in the
#: folder is a claim nothing supports, and one of these in a folder with no
#: money block is a document rendering figures the ledger never decided.
MONEY_WAGE_DOCUMENTS = frozenset(
    {
        "WAGE_STATEMENTS_PRE_INJURY",
        "WAGE_STATEMENTS_POST_INJURY",
        "WAGE_STATEMENTS_EARNING_RECORDS",
    }
)
MONEY_BENEFIT_DOCUMENTS = frozenset(
    {
        "TD_PAYMENT_RECORD_ONGOING",
        "TD_PAYMENT_RECORD_RETROACTIVE",
        "PD_PAYMENT_RECORD_ADVANCE",
        "PD_PAYMENT_RECORD_ONGOING",
        "PD_PAYMENT_RECORD_FINAL",
    }
)

#: The compromise-and-release family: the parties' own agreement, which prints
#: the settlement type and gross.
#:
#: It does **not** carry the approval or funding date, and the first attempt at
#: this rule was wrong to let it. A release is signed and filed before the Board
#: approves it — this engine dates one at 2023-11-13 against an approval of
#: 2023-12-27 — so a release printing its approval asserts an event 44 days in
#: its own future. See :data:`SETTLEMENT_APPROVAL_DOCUMENTS`.
SETTLEMENT_DOCUMENTS = frozenset(
    {
        "COMPROMISE_AND_RELEASE",
        "COMPROMISE_AND_RELEASE_STANDARD",
        "COMPROMISE_AND_RELEASE_PD_ONLY",
        "COMPROMISE_AND_RELEASE_MSA",
        "COMPROMISE_AND_RELEASE_DEPENDENCY",
        "COMPROMISE_AND_RELEASE_THIRD_PARTY",
    }
)

#: The document that effects an approval, and therefore the one that can print
#: its date: the Board issues it *on* that date.
SETTLEMENT_APPROVAL_DOCUMENTS = frozenset({"ORDER_APPROVING_SETTLEMENT"})

#: The instruments an approval is granted *to*. The order recites that this
#: document was filed and considered, so an order dated before it is an order
#: approving something that did not exist yet.
SETTLEMENT_INSTRUMENT_DOCUMENTS = SETTLEMENT_DOCUMENTS | frozenset(
    {
        "STIPULATIONS_WITH_REQUEST_FOR_AWARD",
        "STIPULATIONS_WITH_REQUEST_FOR_AWARD_FULL",
        "STIPULATIONS_WITH_REQUEST_FOR_AWARD_PARTIAL",
        "STIPS_WITH_REQUEST_FOR_AWARD_PACKAGE",
    }
)

#: The document dated after the settlement draft clears. The order is issued
#: before funding, so it cannot report funding either; only a ledger written
#: afterwards can.
SETTLEMENT_FUNDING_DOCUMENTS = frozenset({"BENEFIT_PAYMENT_LEDGER"})

#: Every provenance the rate binding may record. Mirrors ``RateBasis.source``;
#: a published value outside it is a label no analyzer was trained on.
MONEY_BASIS_SOURCES = frozenset({"engine_default_table", "seed", "mixed"})

#: Every method name the ledger may record. Mirrors ``seeds.AWW_METHODS``; a
#: published method outside it is a label no analyzer could have been trained
#: on, which makes the eval score meaningless rather than merely wrong.
MONEY_METHODS = frozenset(AWW_METHODS)


def _document_date(doc: dict[str, Any]) -> date | None:
    """A manifest entry's own date, or ``None`` when it has none to read.

    ``None`` fails the carrier check rather than passing it: a document that
    cannot say when it was written cannot vouch for when something happened.
    """
    raw = doc.get("documentDate")
    if not isinstance(raw, str):
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _validate_money(block: dict[str, Any], documents: list[Any], case_label: str) -> list[str]:
    """Check the money spine against itself and against the folder.

    Skipped entirely when there is no ``money`` key, because absence is the
    designed state for every case that did not ask for a money layer — the
    validator must not turn "this seed has no wages" into a problem.

    What it *does* refuse is a money claim with nothing behind it. The wage
    statement is where an average weekly wage is read from; publishing an AWW
    with no wage statement in the folder is the asserted-not-derived failure
    this whole layer exists to remove, and a validator that let it through would
    be certifying exactly what it was built to catch.
    """
    money = block.get("money")
    if money is None:
        return []

    problems: list[str] = []
    if not isinstance(money, dict):
        return [f"{case_label}: caseFacts.money is {type(money).__name__}, expected a mapping"]

    penalty_section = money.get("penalties")
    if isinstance(penalty_section, dict) and "counselConfirmed" not in penalty_section:
        problems.append(
            f"{case_label}: caseFacts.money.penalties.counselConfirmed is missing, while "
            "the statutory binding publishes no caveat — add counselConfirmed so a "
            "consumer can distinguish verified authority from an unconfirmed placeholder"
        )

    for key, fields in GOVERNED_MONEY_FIELDS.items():
        if key in ("settlement", "penalties") and money.get(key) is None:
            # Absent for a case that did not settle — see SettlementFact. Absent
            # is fine; *present* was being skipped along with it, so a settlement
            # was the one group whose shape and governance nothing checked. An
            # ungoverned field there is an extraction label the documents never
            # promised, which is exactly what this loop exists to refuse.
            continue
        section = money.get(key)
        if section is None:
            problems.append(f"{case_label}: caseFacts.money is missing {key!r}")
            continue
        if not isinstance(section, dict):
            problems.append(f"{case_label}: caseFacts.money.{key} is not a mapping")
            continue
        ungoverned = sorted(set(section) - set(fields))
        if ungoverned:
            problems.append(
                f"{case_label}: caseFacts.money.{key} publishes ungoverned field(s) "
                f"{', '.join(ungoverned)} — a published fact must be one a document renders"
            )
        # And the other direction, which this loop did not check for four review
        # rounds: the governance table is a promise in both directions. Every
        # field in it is emitted unconditionally by ``money_manifest_block`` —
        # nullable ones as ``None``, never absent — so a *missing* key is a
        # manifest that has lost a label the analyzer is scored on, and it was
        # being certified clean. Found by review, which reproduced it by
        # deleting ``settlement.grossAmount``, ``wage.averageWeeklyWage`` and
        # ``benefits.gaps`` from a valid manifest: all three passed.
        missing = sorted(set(fields) - set(section))
        if missing:
            problems.append(
                f"{case_label}: caseFacts.money.{key} is missing governed field(s) "
                f"{', '.join(missing)} — a governed field is published or the case has "
                "no such group at all"
            )
    if problems:
        return problems

    wage = money["wage"]
    rate = money["rate"]

    # ``basisSource`` is an extraction label like ``method`` and the bound
    # tokens, and was the one of the four nothing checked — ``"seed-ish"`` was
    # accepted so long as both artifacts agreed with each other. Two artifacts
    # agreeing on a value outside the vocabulary is not a check, it is a copy.
    basis_source = rate.get("basisSource")
    if basis_source not in MONEY_BASIS_SOURCES:
        problems.append(
            f"{case_label}: caseFacts.money.rate.basisSource is {basis_source!r}, "
            f"expected one of {', '.join(sorted(MONEY_BASIS_SOURCES))}"
        )

    method = wage.get("method")
    if method not in MONEY_METHODS:
        problems.append(
            f"{case_label}: caseFacts.money.wage.method is {method!r}, which is not one of "
            f"{', '.join(sorted(MONEY_METHODS))}"
        )
    if wage.get("methodSource") not in ("seed", "derived"):
        problems.append(
            f"{case_label}: caseFacts.money.wage.methodSource is "
            f"{wage.get('methodSource')!r}, expected 'seed' or 'derived'"
        )
    if not wage.get("methodReason"):
        problems.append(
            f"{case_label}: caseFacts.money.wage names method {method!r} with no reason — "
            "the method is ground truth, so how it was chosen is part of the label"
        )

    for bound_key in ("tdBound", "pdBound"):
        if rate.get(bound_key) not in ("max", "min", "unbounded"):
            problems.append(
                f"{case_label}: caseFacts.money.rate.{bound_key} is "
                f"{rate.get(bound_key)!r}, expected max, min or unbounded"
            )
    if "counselConfirmed" not in rate:
        problems.append(
            f"{case_label}: caseFacts.money.rate omits counselConfirmed — every statutory "
            "binding in this corpus is unverified until it says otherwise, and a consumer "
            "must not have to read the source to find that out"
        )

    subtypes = {d.get("subtype") for d in documents if isinstance(d, dict)}
    if not (subtypes & MONEY_WAGE_DOCUMENTS):
        problems.append(
            f"{case_label}: caseFacts publishes an average weekly wage but the case holds "
            "no wage statement — the figure is asserted rather than derivable"
        )
    benefits = money["benefits"]
    # Shape before arithmetic. A validator that trusts the types it was handed
    # crashes on the input it exists to reject: ``tdPeriodCount: "one"`` raised
    # ``TypeError`` out of the sum below rather than returning a problem, and a
    # crash is not a verdict.
    for count_key in ("tdPeriodCount", "pdAdvanceCount"):
        value = benefits.get(count_key)
        # ``type(...) is int`` rather than ``isinstance``: ``bool`` is a subclass
        # of ``int``, so ``tdPeriodCount: True`` passed an isinstance check and
        # then compared equal to a length of 1.
        if value is not None and (type(value) is not int or value < 0):
            problems.append(
                f"{case_label}: caseFacts.money.benefits.{count_key} is {value!r}, "
                "expected a count of zero or more"
            )
    for array_key in ("tdPeriods", "pdAdvances", "gaps"):
        value = benefits.get(array_key)
        if value is not None and not isinstance(value, list):
            problems.append(
                f"{case_label}: caseFacts.money.benefits.{array_key} is "
                f"{type(value).__name__}, expected a list of records"
            )
    if problems:
        return problems

    # Any paid or withheld event needs a record to be read from, not only a TD
    # one. A case publishing four permanent-disability advances and no payment
    # record at all used to pass: the rule was written for the half that had a
    # probe rather than for the class.
    event_count = (
        (benefits.get("tdPeriodCount") or 0)
        + (benefits.get("pdAdvanceCount") or 0)
        + len(benefits.get("gaps") or [])
    )
    if event_count and not (subtypes & MONEY_BENEFIT_DOCUMENTS):
        problems.append(
            f"{case_label}: caseFacts publishes {event_count} benefit event(s) but the "
            "case holds no payment record to read them from"
        )
    # The counts and the event arrays are two publications of one ledger, so a
    # disagreement between them means one of the two was assembled from
    # something other than the records — which is the drift the paired
    # publication exists to make visible.
    for count_key, array_key in (
        ("tdPeriodCount", "tdPeriods"),
        ("pdAdvanceCount", "pdAdvances"),
    ):
        events = benefits.get(array_key)
        if not isinstance(events, list):
            problems.append(
                f"{case_label}: caseFacts.money.benefits.{array_key} is not a list — the "
                "ledger publishes the events, not only how many there were"
            )
            continue
        if benefits.get(count_key) != len(events):
            problems.append(
                f"{case_label}: caseFacts.money.benefits.{count_key} is "
                f"{benefits.get(count_key)} but {array_key} holds {len(events)} record(s)"
            )
    # ``days_late`` is measured from ``dateDue``. A record that carries the
    # effect without the cause is the asserted number this layer removes, so the
    # two are checked against each other rather than taken on trust — on both
    # ledgers, because the first cut checked temporary disability only and a
    # permanent-disability advance marked 62 days late named nothing to be late
    # against.
    for array_key, what in (
        ("tdPeriods", "temporary disability period"),
        ("pdAdvances", "permanent disability advance"),
    ):
        for event in benefits.get(array_key) or []:
            if not isinstance(event, dict):
                # A non-mapping event used to pass straight through this loop.
                # The ledger is the eval label; a label that is a bare string is
                # not a lesser label, it is a broken one.
                problems.append(
                    f"{case_label}: caseFacts.money.benefits.{array_key} holds a "
                    f"{type(event).__name__} where a record was expected"
                )
                continue
            due, paid, late = event.get("dateDue"), event.get("datePaid"), event.get("daysLate")
            if due is None:
                problems.append(
                    f"{case_label}: a caseFacts.money.benefits.{array_key} record omits "
                    "dateDue — daysLate is measured against it and cannot be checked "
                    "without it"
                )
                continue
            if paid is None:
                if late:
                    # Never paid is an interruption, not a delay. A record with
                    # no payment date cannot also carry a number of days it was
                    # late, because there is no second date to have counted them
                    # to — and a penalty computed off that number in Wave 3
                    # would be computed off nothing.
                    problems.append(
                        f"{case_label}: a {what} was never paid but records daysLate "
                        f"{late} — an unpaid benefit is an interruption, not a delay"
                    )
                continue
            try:
                actual = (date.fromisoformat(paid) - date.fromisoformat(due)).days
            except (TypeError, ValueError):
                problems.append(
                    f"{case_label}: a {what} carries unreadable dates "
                    f"(dateDue {due!r}, datePaid {paid!r})"
                )
                continue
            if actual != late:
                problems.append(
                    f"{case_label}: a {what} was due {due} and paid {paid} "
                    f"({actual} day(s) apart) but records daysLate {late}"
                )

    # Gaps are events too, and were the one array nothing checked.
    for gap in benefits.get("gaps") or []:
        if not isinstance(gap, dict):
            problems.append(
                f"{case_label}: caseFacts.money.benefits.gaps holds a "
                f"{type(gap).__name__} where a record was expected"
            )
            continue
        start, end, days = gap.get("start"), gap.get("end"), gap.get("days")
        if start is None or end is None or days is None:
            problems.append(
                f"{case_label}: a caseFacts.money.benefits.gaps record omits start, end "
                "or days — a gap the eval cannot measure is a gap the corpus does not "
                "contain"
            )
            continue
        try:
            spanned = (date.fromisoformat(end) - date.fromisoformat(start)).days + 1
        except (TypeError, ValueError):
            problems.append(
                f"{case_label}: a benefit gap carries unreadable dates "
                f"(start {start!r}, end {end!r})"
            )
            continue
        if spanned != days or type(days) is not int or days < 1:
            # ``spanned == days`` alone agreed with a reversed gap carrying a
            # negative count: 2025-01-10 to 2025-01-01 spans -8 days and recorded
            # -8. Two wrongs cancelling is not a check.
            problems.append(
                f"{case_label}: a benefit gap runs {start} to {end} ({spanned} day(s)) "
                f"but records days {days!r} — a gap runs forwards and lasts at least a day"
            )

    penalties = money.get("penalties")
    if penalties is not None:
        assessments = penalties.get("assessments")
        assessment_count = penalties.get("assessmentCount")
        if not isinstance(assessments, list):
            problems.append(
                f"{case_label}: caseFacts.money.penalties.assessments is "
                f"{type(assessments).__name__}, expected a list of assessed late payments — "
                "publish the assessment records under the plural field"
            )
            assessments = []
        if assessment_count != len(assessments):
            problems.append(
                f"{case_label}: caseFacts.money.penalties.assessmentCount is "
                f"{assessment_count!r} but assessments holds {len(assessments)} record(s) — "
                "set the count to the number of published assessments"
            )
        if not (subtypes & MONEY_BENEFIT_DOCUMENTS):
            problems.append(
                f"{case_label}: caseFacts.money.penalties publishes {assessment_count!r} "
                "assessment(s) but the case holds 0 benefit-payment documents — add a "
                "benefit-payment surface or remove the penalties block"
            )

        assessed_amounts: list[Decimal] = []
        assessed_principals: list[Decimal] = []
        for index, assessment in enumerate(assessments, 1):
            if not isinstance(assessment, dict):
                problems.append(
                    f"{case_label}: caseFacts.money.penalties.assessments[{index}] is a "
                    f"{type(assessment).__name__}, expected a record — publish the late "
                    "payment operands and computed amount together"
                )
                continue
            days_late = assessment.get("daysLate")
            if type(days_late) is not int or days_late < 1:
                problems.append(
                    f"{case_label}: caseFacts.money.penalties.assessments[{index}].daysLate "
                    f"is {days_late!r}, but an assessed payment must be at least 1 day late — "
                    "remove the assessment or correct daysLate from its due and paid dates"
                )
            try:
                principal = Decimal(str(assessment.get("principal")))
                fraction = Decimal(str(assessment.get("increaseFraction")))
                published_amount = Decimal(str(assessment.get("amount")))
                computed_amount = quantized_money(principal * fraction)
            except (InvalidOperation, TypeError, ValueError):
                problems.append(
                    f"{case_label}: caseFacts.money.penalties.assessments[{index}] has "
                    f"principal {assessment.get('principal')!r}, increaseFraction "
                    f"{assessment.get('increaseFraction')!r} and amount "
                    f"{assessment.get('amount')!r}, which cannot be read as decimals — "
                    "publish exact decimal strings for all three fields"
                )
                continue
            assessed_principals.append(principal)
            assessed_amounts.append(published_amount)
            if published_amount != computed_amount:
                problems.append(
                    f"{case_label}: caseFacts.money.penalties.assessments[{index}].amount is "
                    f"{published_amount} but principal {principal} x increaseFraction "
                    f"{fraction} is {computed_amount} to cents — replace amount with the "
                    "cents-quantized product"
                )

        try:
            published_total = Decimal(str(penalties.get("totalIncrease")))
            computed_total = quantized_money(sum(assessed_amounts, Decimal("0.00")))
            if published_total != computed_total:
                problems.append(
                    f"{case_label}: caseFacts.money.penalties.totalIncrease is "
                    f"{published_total} but assessment amounts sum to {computed_total} — "
                    "replace totalIncrease with the cents-quantized assessment sum"
                )
        except (InvalidOperation, TypeError, ValueError):
            problems.append(
                f"{case_label}: caseFacts.money.penalties.totalIncrease is "
                f"{penalties.get('totalIncrease')!r}, while the assessment sum is decimal — "
                "publish totalIncrease as an exact decimal string"
            )
        try:
            published_principal = Decimal(str(penalties.get("principalAssessed")))
            computed_principal = quantized_money(sum(assessed_principals, Decimal("0.00")))
            if published_principal != computed_principal:
                problems.append(
                    f"{case_label}: caseFacts.money.penalties.principalAssessed is "
                    f"{published_principal} but assessment principals sum to "
                    f"{computed_principal} — replace principalAssessed with the "
                    "cents-quantized principal sum"
                )
        except (InvalidOperation, TypeError, ValueError):
            problems.append(
                f"{case_label}: caseFacts.money.penalties.principalAssessed is "
                f"{penalties.get('principalAssessed')!r}, while the principal sum is decimal — "
                "publish principalAssessed as an exact decimal string"
            )

    settlement = money.get("settlement")
    if settlement is not None:
        if settlement.get("kind") not in ("c_and_r", "stipulations"):
            problems.append(
                f"{case_label}: caseFacts.money.settlement.kind is "
                f"{settlement.get('kind')!r}, expected c_and_r or stipulations"
            )
        approval_raw = settlement.get("approvalDate")
        funding_raw = settlement.get("fundingDate")
        approval = funding = None
        for label, raw in (("approvalDate", approval_raw), ("fundingDate", funding_raw)):
            if raw is None:
                continue
            try:
                parsed = date.fromisoformat(raw)
            except (TypeError, ValueError):
                # ``fromisoformat`` on an int raises TypeError, which used to
                # escape this function: the comparison below reached a str and an
                # int and the validator crashed rather than reporting.
                problems.append(
                    f"{case_label}: caseFacts.money.settlement.{label} is {raw!r}, "
                    "which is not a date"
                )
                continue
            if label == "approvalDate":
                approval = parsed
            else:
                funding = parsed
        if approval is not None and funding is not None:
            if funding < approval:
                problems.append(
                    f"{case_label}: caseFacts.money.settlement was funded {funding_raw} "
                    f"but approved {approval_raw} — money does not move before the Board "
                    "approves"
                )
            # With both dates in hand the lag is derivable, so ``None`` is not a
            # permitted answer here — only a settlement that has not funded may
            # leave it unstated. Review found the null slipping through beside
            # two dates: the interval is the whole substance of a late-funding
            # argument, and a manifest that has both endpoints and declines to
            # state the span between them has dropped the fact, not deferred it.
            lag = settlement.get("fundingLagDays")
            if lag is not True and lag is not False and isinstance(lag, int):
                if lag != (funding - approval).days:
                    problems.append(
                        f"{case_label}: caseFacts.money.settlement records fundingLagDays "
                        f"{lag} but was approved {approval_raw} and funded {funding_raw} "
                        f"({(funding - approval).days} day(s) apart)"
                    )
            else:
                problems.append(
                    f"{case_label}: caseFacts.money.settlement.fundingLagDays is {lag!r}, "
                    f"but it was approved {approval_raw} and funded {funding_raw} — with "
                    "both dates the interval is a fact, not an option"
                )
        # A published date needs a document that could have printed it, and
        # "could have" is a claim about the document's own date as much as its
        # subtype. The first cut of this rule checked only the subtype and
        # accepted a release dated 44 days before the approval it would have had
        # to print, and a temporary-disability payment record dated two years
        # before it. An anachronism is worse evidence than a missing line,
        # because it reads as evidence.
        # An approval is granted to an instrument, so the instrument comes first.
        # Checking each carrier against its own event date is not enough: review
        # found an order correctly pinned to an authored approval of 2022-01-05
        # and therefore dated 677 days before the stipulations it recites as
        # "filed herein". A chain checked link by link still has to be a chain.
        if approval is not None:
            for doc in documents:
                if not isinstance(doc, dict):
                    continue
                if doc.get("subtype") not in SETTLEMENT_INSTRUMENT_DOCUMENTS:
                    continue
                filed = _document_date(doc)
                if filed is not None and filed > approval:
                    problems.append(
                        f"{case_label}: caseFacts.money.settlement was approved "
                        f"{approval_raw} but the case holds a "
                        f"{doc.get('subtype')} dated {filed} — an order cannot approve "
                        "an instrument that does not exist yet"
                    )

        # The approval carrier is dated *on* the approval; the funding carrier
        # on or after the funding. The difference is not fussiness: the order
        # constitutes the approval, so a different date is a different event,
        # while the ledger merely reports a payment and may be written any time
        # afterwards. Review found an order dated 721 days after the approval it
        # was vouching for, passing an on-or-after rule.
        for label, raw, when, carriers, exact in (
            ("approval", approval_raw, approval, SETTLEMENT_APPROVAL_DOCUMENTS, True),
            ("funding", funding_raw, funding, SETTLEMENT_FUNDING_DOCUMENTS, False),
        ):
            if raw is None or when is None:
                continue
            if not any(
                doc.get("subtype") in carriers
                and _document_date(doc) is not None
                and (_document_date(doc) == when if exact else _document_date(doc) >= when)
                for doc in documents
                if isinstance(doc, dict)
            ):
                problems.append(
                    f"{case_label}: caseFacts.money.settlement publishes a {label} date of "
                    f"{raw} but the case holds no {'/'.join(sorted(carriers))} dated "
                    + ("on it" if exact else "on or after it")
                    + " — a document cannot report its own future"
                )
    return problems


def _validate_case_facts(
    manifest: dict[str, Any],
    case_dir: Path,
    documents: list[Any],
    case_label: str,
) -> list[str]:
    """Check the published ledger against itself, its artifact, and the folder.

    The ledger is the case's claim about what happened. Publishing it and never
    checking it is worse than not publishing it: a reader is entitled to assume
    a stated fact was verified. This enforces the part a validator can see from
    the output alone — no substrate, no regeneration, just the manifest, the
    YAML beside it, and the filenames on disk.
    """
    problems: list[str] = []
    block = manifest.get("caseFacts")

    if block is None:
        return [f"{case_label}: manifest has no caseFacts block"]
    if not isinstance(block, dict):
        return [f"{case_label}: caseFacts is {type(block).__name__}, expected a mapping"]

    # Shape. A missing key here means a consumer reading the ledger would get
    # None and quietly conclude the case had no surgery, no imaging, no one.
    for key in GOVERNED_LEDGER_FIELDS:
        if key not in block:
            problems.append(f"{case_label}: caseFacts is missing {key!r}")
    if problems:
        return problems

    diagnostics = block.get("diagnostics")
    if not isinstance(diagnostics, list):
        return [f"{case_label}: caseFacts.diagnostics is not a list"]

    seen: dict[str, bool] = {}
    for entry in diagnostics:
        if not isinstance(entry, dict):
            problems.append(f"{case_label}: caseFacts.diagnostics holds a non-mapping entry")
            continue
        modality = entry.get("modality")
        if modality not in MODALITIES:
            problems.append(
                f"{case_label}: caseFacts names modality {modality!r}, which is not one of "
                f"{', '.join(MODALITIES)}"
            )
            continue
        extra = set(entry) - set(GOVERNED_LEDGER_FIELDS["diagnostics"])
        if extra:
            problems.append(
                f"{case_label}: caseFacts.diagnostics[{modality}] publishes ungoverned "
                f"field(s) {sorted(extra)} — no template renders them"
            )
        performed = entry.get("performed")
        if not isinstance(performed, bool):
            problems.append(
                f"{case_label}: caseFacts.diagnostics[{modality}].performed is "
                f"{performed!r}, expected a boolean"
            )
        elif modality in seen and seen[modality] != performed:
            problems.append(f"{case_label}: caseFacts calls {modality!r} both performed and absent")
        else:
            seen[modality] = performed

    adjuster = block.get("adjuster")
    if not isinstance(adjuster, dict):
        problems.append(f"{case_label}: caseFacts.adjuster is not a mapping")
    else:
        extra = set(adjuster) - set(GOVERNED_LEDGER_FIELDS["adjuster"])
        if extra:
            problems.append(
                f"{case_label}: caseFacts.adjuster publishes ungoverned field(s) {sorted(extra)}"
            )
        # No ``diligence`` check: it is resolved on the ledger but deliberately
        # unpublished, because no rendered document reflects it and a reader
        # could not check it against anything.
        #
        # The rule the penalty petition is gated on, checkable from the output
        # alone: a pleading alleging unreasonable delay needs a delay behind it.
        late = adjuster.get("lateBenefitEvents") or 0
        has_petition = any(
            isinstance(d, dict) and d.get("subtype") == "PETITION_FOR_PENALTIES" for d in documents
        )
        if has_petition and not late:
            problems.append(
                f"{case_label}: the case pleads LC 5814 penalties but caseFacts "
                "records no late benefit event to support it"
            )
        if bool(late) != bool(adjuster.get("maxDaysLate")):
            problems.append(
                f"{case_label}: caseFacts.adjuster has {late} late event(s) but "
                f"maxDaysLate {adjuster.get('maxDaysLate')!r}"
            )

    treatment = block.get("treatment")
    if not isinstance(treatment, dict):
        problems.append(f"{case_label}: caseFacts.treatment is not a mapping")
    else:
        extra = set(treatment) - set(GOVERNED_LEDGER_FIELDS["treatment"])
        if extra:
            problems.append(
                f"{case_label}: caseFacts.treatment publishes ungoverned field(s) {sorted(extra)}"
            )
        if treatment.get("status") not in TREATMENT_STATUSES:
            problems.append(
                f"{case_label}: caseFacts.treatment.status is "
                f"{treatment.get('status')!r}, not one of {', '.join(TREATMENT_STATUSES)}"
            )
        if (treatment.get("status") == "discharged") != bool(treatment.get("dischargeDate")):
            problems.append(
                f"{case_label}: caseFacts.treatment has status "
                f"{treatment.get('status')!r} and dischargeDate "
                f"{treatment.get('dischargeDate')!r} — a discharge date exists exactly "
                "when the file says care ended"
            )
        if (treatment.get("status") == "gap") != bool(treatment.get("gapStart")):
            problems.append(
                f"{case_label}: caseFacts.treatment has status "
                f"{treatment.get('status')!r} but gapStart "
                f"{treatment.get('gapStart')!r}"
            )

    # Whether the *seed* stated the surgery, which decides how strict the
    # operative-document rule below can honestly be.
    scenario_stated = False
    seed_path = case_dir / SEED_NAME
    if seed_path.is_file():
        import yaml as _yaml

        try:
            seed_body = _yaml.safe_load(seed_path.read_text(encoding="utf-8")) or {}
            scenario_stated = bool((seed_body.get("scenario") or {}).get("surgery"))
        except _yaml.YAMLError:
            pass

    surgery = block.get("surgery")
    if not isinstance(surgery, dict):
        problems.append(f"{case_label}: caseFacts.surgery is not a mapping")
    else:
        status = surgery.get("status")
        has_operative = any(
            isinstance(d, dict) and d.get("subtype") in OPERATIVE_SUBTYPES for d in documents
        )
        uncoded = surgery.get("uncoded", False)
        cpt = surgery.get("cptCode")
        description = surgery.get("cptDescription")
        if not isinstance(uncoded, bool):
            problems.append(
                f"{case_label}: caseFacts.surgery.uncoded is {uncoded!r}, not a boolean"
            )
            uncoded = bool(uncoded)
        # Each CPT field is exactly null or a non-empty string. An empty or
        # whitespace-only string is a third state the contract does not have —
        # and truthiness would silently read it as "no code" while consumers
        # see a non-null field (round-4 review). Every check below therefore
        # tests ``is None``, never truthiness.
        for field, value in (("cptCode", cpt), ("cptDescription", description)):
            if value is not None and (not isinstance(value, str) or not value.strip()):
                problems.append(
                    f"{case_label}: caseFacts.surgery.{field} is {value!r} — "
                    "must be null or a non-empty string"
                )
        if (cpt is None) != (description is None):
            missing = (
                "a CPT without a description"
                if description is None
                else "a description without a CPT"
            )
            problems.append(f"{case_label}: caseFacts.surgery names {missing}")
        if status in ("performed", "recommended", "denied_by_ur"):
            if uncoded and cpt is not None:
                problems.append(
                    f"{case_label}: caseFacts calls the surgery uncoded yet names CPT {cpt!r}"
                )
            if cpt is None and not uncoded:
                problems.append(
                    f"{case_label}: caseFacts says surgery was {status} but names no CPT "
                    "and does not declare the operation uncoded"
                )
        if status == "performed":
            if scenario_stated and not has_operative:
                problems.append(
                    f"{case_label}: the seed states surgery was performed but the case "
                    "holds no operative document to support it"
                )
        elif status in ("recommended", "denied_by_ur"):
            if has_operative:
                problems.append(
                    f"{case_label}: caseFacts says surgery was {status}, which means it did "
                    "not happen, but the case holds an operative document"
                )
        elif status == "none":
            if uncoded:
                problems.append(
                    f"{case_label}: caseFacts marks no-surgery as uncoded — the marker "
                    "belongs only on an asserted operation"
                )
            if cpt is not None:
                problems.append(
                    f"{case_label}: caseFacts says no surgery but still names CPT {cpt!r}"
                )
            if has_operative:
                problems.append(
                    f"{case_label}: the case holds an operative document but caseFacts "
                    "says no surgery was performed"
                )
        else:
            problems.append(f"{case_label}: caseFacts.surgery.status is {status!r}")

    problems.extend(_validate_money(block, documents, case_label))

    # The artifact and the manifest are two publications of one ledger. They are
    # written from the same call, so any drift means the folder was edited after
    # generation — which is exactly what a reader needs to be told.
    facts_path = case_dir / CASE_FACTS_NAME
    if not facts_path.is_file():
        problems.append(f"{case_label}: {CASE_FACTS_NAME} is missing")
        return problems

    import yaml

    try:
        artifact = yaml.safe_load(facts_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        problems.append(f"{case_label}: {CASE_FACTS_NAME} is not valid YAML — {exc}")
        return problems

    if artifact != block:
        problems.append(
            f"{case_label}: {CASE_FACTS_NAME} and manifest caseFacts disagree — "
            "the two published copies of the ledger have drifted"
        )

    return problems


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

        report.problems.extend(
            _validate_case_facts(manifest, manifest_path.parent, documents, case_label)
        )

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


def _write_case_facts(facts: CaseFacts, path: Path, money: MoneyFacts | None = None) -> None:
    """Write the resolved ledger beside the seed.

    YAML rather than JSON to match ``seed.yaml``: the two files are read
    together, and a reviewer should not have to change format between them.

    Built from the same call as the manifest's block, *money included*, because
    ``_validate_case_facts`` compares the two for byte equality. Writing them
    from two different expressions is how they would drift.
    """
    import yaml

    header = (
        "# wc-caseload case facts \u2014 the resolved clinical ledger\n"
        "# Derived from the seed; every fact the seed did not state was decided here.\n"
        "# Documents render against this, and the manifest publishes it as 'caseFacts'.\n"
    )
    body = yaml.safe_dump(
        facts_manifest_block(facts, money),
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
    )
    path.write_text(header + body, encoding="utf-8")
