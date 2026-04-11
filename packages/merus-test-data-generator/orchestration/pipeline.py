"""
Main orchestration pipeline — 4-step flow:
  1. Generate case data
  2. Generate PDFs
  3. Create cases in MerusCase (browser automation)
  4. Upload documents to MerusCase (API)

v2.0: Supports dynamic case count via lifecycle engine + CaseParameters.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path
from typing import Any, Optional

import structlog

from config import OUTPUT_DIR, RANDOM_SEED
from data.case_profiles import CASE_PROFILES
from data.case_profile_generator import CaseConstraints, CaseProfileGenerator
from data.fake_data_generator import FakeDataGenerator
from data.lifecycle_engine import CaseParameters
from data.models import GeneratedCase
from orchestration.audit import PipelineAuditLogger
from orchestration.progress_tracker import ProgressTracker

logger = structlog.get_logger()

# Template class registry — maps template_class strings to module paths
TEMPLATE_REGISTRY: dict[str, str] = {
    "TreatingPhysicianReport": "pdf_templates.medical.treating_physician_report",
    "DiagnosticReport": "pdf_templates.medical.diagnostic_report",
    "OperativeRecord": "pdf_templates.medical.operative_record",
    "QmeAmeReport": "pdf_templates.medical.qme_ame_report",
    "UtilizationReview": "pdf_templates.medical.utilization_review",
    "PharmacyRecords": "pdf_templates.medical.pharmacy_records",
    "BillingRecords": "pdf_templates.medical.billing_records",
    "ApplicationForAdjudication": "pdf_templates.legal.application_for_adjudication",
    "DeclarationOfReadiness": "pdf_templates.legal.declaration_of_readiness",
    "MinutesOrders": "pdf_templates.legal.minutes_orders",
    "Stipulations": "pdf_templates.legal.stipulations",
    "CompromiseAndRelease": "pdf_templates.legal.compromise_and_release",
    "AdjusterLetter": "pdf_templates.correspondence.adjuster_letter",
    "DefenseCounselLetter": "pdf_templates.correspondence.defense_counsel_letter",
    "CourtNotice": "pdf_templates.correspondence.court_notice",
    "ClientIntake": "pdf_templates.correspondence.client_intake",
    "Subpoena": "pdf_templates.discovery.subpoena",
    "DepositionNotice": "pdf_templates.discovery.deposition_notice",
    "DepositionTranscript": "pdf_templates.discovery.deposition_transcript",
    "SubpoenaedRecords": "pdf_templates.discovery.subpoenaed_records",
    "WageStatement": "pdf_templates.employment.wage_statement",
    "JobDescription": "pdf_templates.employment.job_description",
    "PersonnelFile": "pdf_templates.employment.personnel_file",
    "MedicalChronology": "pdf_templates.summaries.medical_chronology",
    "SettlementMemo": "pdf_templates.summaries.settlement_memo",
    # Administrative noise templates
    "FaxCoverSheet": "pdf_templates.administrative.fax_cover_sheet",
    "FileNote": "pdf_templates.administrative.file_note",
    "BlankPage": "pdf_templates.administrative.blank_page",
    "CoverLetterEnclosure": "pdf_templates.administrative.cover_letter_enclosure",
}


def _load_template_class(class_name: str):
    """Dynamically import and return a template class."""
    if class_name == "GenericDocumentTemplate":
        from pdf_templates.generic_template import GenericDocumentTemplate
        return GenericDocumentTemplate

    module_path = TEMPLATE_REGISTRY.get(class_name)
    if not module_path:
        raise ValueError(f"Unknown template class: {class_name}")
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


_FORMAT_EXT: dict[str, str] = {
    "pdf": ".pdf",
    "eml": ".eml",
    "docx": ".docx",
    "scanned_pdf": ".pdf",  # Scanned PDFs are still PDF files with image content
}


def _format_extension(output_format: Any) -> str:
    """Return the file extension for a given OutputFormat value."""
    val = output_format.value if hasattr(output_format, "value") else str(output_format)
    return _FORMAT_EXT.get(val, ".pdf")


def _sanitize_filename(name: str, ext: str = ".pdf") -> str:
    """Make a safe filename from a document title. Prevents path traversal.

    Args:
        name: Raw filename stem (no extension required).
        ext: File extension including dot, e.g. ".eml" or ".docx".
    """
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    name = re.sub(r'\s+', '_', name)
    name = name.replace('..', '_')
    name = Path(name).name  # Extract filename component only
    # Strip any existing extension before applying the canonical one
    name = re.sub(r'\.(pdf|eml|docx)$', '', name, flags=re.IGNORECASE)
    name = name[:80]  # Limit length
    return name + ext


class Pipeline:
    def __init__(self, tracker: ProgressTracker, audit: PipelineAuditLogger | None = None):
        self.tracker = tracker
        self.audit = audit
        self.generator = FakeDataGenerator(seed=RANDOM_SEED)
        self.cases: list[GeneratedCase] = []

    # --- Step 1: Generate case data ---

    def generate_data(
        self,
        count: int | None = None,
        seed: int | None = None,
        stage_distribution: dict[str, float] | None = None,
        constraints: CaseConstraints | None = None,
        progress_callback: Any = None,
        complexity: str = "standard",
    ) -> list[GeneratedCase]:
        """Generate all case data objects.

        Args:
            count: Number of cases to generate. None = use legacy 20 profiles.
            seed: Random seed for reproducibility.
            stage_distribution: Dict mapping stage names to proportions.
            constraints: CaseConstraints for dynamic generation.
            progress_callback: Optional callable(event, data) for SSE progress.
            complexity: "standard" or "complex" (Salerno-style mega-cases).
        """
        effective_seed = seed if seed is not None else RANDOM_SEED
        self.generator = FakeDataGenerator(seed=effective_seed)

        # Determine profiles
        if count is not None:
            # Dynamic generation via lifecycle engine
            profiles = CaseProfileGenerator.generate_profiles(
                count=count,
                seed=effective_seed,
                stage_distribution=stage_distribution,
                constraints=constraints,
                complexity=complexity,
            )
            use_lifecycle = True
        else:
            # Legacy: use hardcoded 20 profiles
            profiles = None
            use_lifecycle = False

        total = count if count is not None else len(CASE_PROFILES)

        run = self.tracker.get_current_run()
        if not run:
            run_id = self.tracker.start_run(total_cases=total)
        else:
            run_id = run["id"]

        logger.info("generating_data", total_profiles=total, mode="lifecycle" if use_lifecycle else "legacy")

        self.cases = []

        if use_lifecycle:
            for i, params in enumerate(profiles):
                case = self.generator.generate_case_from_params(i + 1, params)
                self.cases.append(case)
                self._register_case(run_id, case)

                if progress_callback:
                    progress_callback("case_complete", {
                        "case_number": i + 1,
                        "total": total,
                        "applicant": case.applicant.full_name,
                        "stage": case.litigation_stage.value,
                        "docs": len(case.document_specs),
                    })
        else:
            for profile in CASE_PROFILES:
                case = self.generator.generate_case(profile)
                self.cases.append(case)
                self._register_case(run_id, case)

        total_docs = sum(len(c.document_specs) for c in self.cases)
        logger.info("data_generation_complete", cases=len(self.cases), total_docs=total_docs)
        return self.cases

    def _register_case(self, run_id: int, case: GeneratedCase) -> None:
        """Register a case and its documents in the progress tracker."""
        self.tracker.register_case(
            run_id=run_id,
            internal_id=case.internal_id,
            case_number=case.case_number,
            stage=case.litigation_stage.value,
            applicant_name=case.applicant.full_name,
            employer_name=case.employer.company_name,
            total_docs=len(case.document_specs),
        )
        self.tracker.mark_case_data_generated(case.internal_id)

        # Register each document
        for i, doc_spec in enumerate(case.document_specs):
            ext = _format_extension(doc_spec.output_format)
            filename = _sanitize_filename(
                f"{case.internal_id}_{i+1:03d}_{doc_spec.subtype.value}_{doc_spec.doc_date}",
                ext=ext,
            )
            self.tracker.register_document(
                case_internal_id=case.internal_id,
                filename=filename,
                subtype=doc_spec.subtype.value,
                title=doc_spec.title,
                doc_date=doc_spec.doc_date.isoformat(),
                output_format=doc_spec.output_format.value,
            )

        logger.info(
            "case_data_generated",
            case_id=case.internal_id,
            applicant=case.applicant.full_name,
            stage=case.litigation_stage.value,
            doc_count=len(case.document_specs),
        )

    # --- Step 2: Generate documents (PDF / EML / DOCX / scanned PDF) ---

    def generate_documents(self, progress_callback: Any = None) -> dict[str, int]:
        """Generate output files for all cases across all formats.

        Dispatches each DocumentSpec to the appropriate generator based on
        output_format.  Phases 2–4 replace the format-specific stubs below
        with real EML / DOCX / scan-simulation logic; for now all non-PDF
        formats fall through to the standard PDF generator (shim).
        """
        if not self.cases:
            logger.warning("no_cases_loaded", hint="Run generate_data first")
            return {"generated": 0, "skipped": 0, "errors": 0}

        generated = 0
        skipped = 0
        errors = 0

        for case in self.cases:
            case_dir = OUTPUT_DIR / case.internal_id
            case_dir.mkdir(parents=True, exist_ok=True)

            docs_in_tracker = self.tracker.get_docs_for_case(case.internal_id)
            doc_filenames = {d["filename"]: d for d in docs_in_tracker}

            # Phase 6: Create a per-case accumulator for interdocument coherence
            from data.case_context import CaseContextAccumulator
            accumulator = CaseContextAccumulator()

            for i, doc_spec in enumerate(case.document_specs):
                # Inject accumulator into doc context so templates can cross-reference
                doc_spec.context["_accumulator"] = accumulator

                ext = _format_extension(doc_spec.output_format)
                filename = _sanitize_filename(
                    f"{case.internal_id}_{i+1:03d}_{doc_spec.subtype.value}_{doc_spec.doc_date}",
                    ext=ext,
                )
                tracked_doc = doc_filenames.get(filename)

                if tracked_doc and tracked_doc["pdf_generated"]:
                    skipped += 1
                    continue

                output_path = case_dir / filename

                # Validate output path stays within OUTPUT_DIR
                if not output_path.resolve().is_relative_to(OUTPUT_DIR.resolve()):
                    logger.error(
                        "path_traversal_blocked",
                        case=case.internal_id,
                        filename=filename,
                    )
                    errors += 1
                    continue

                try:
                    fmt = doc_spec.output_format.value
                    template_cls = _load_template_class(doc_spec.template_class)
                    template = template_cls(case)
                    # generate() dispatches internally by output_format
                    template.generate(output_path, doc_spec)

                    self.tracker.mark_pdf_generated(
                        case.internal_id, filename, str(output_path)
                    )
                    # Record to accumulator so subsequent docs can cross-reference
                    accumulator.record_document(
                        title=doc_spec.title,
                        doc_date=doc_spec.doc_date,
                        subtype=doc_spec.subtype.value,
                    )
                    generated += 1

                    if progress_callback:
                        progress_callback("doc_complete", {
                            "case_id": case.internal_id,
                            "filename": filename,
                            "format": doc_spec.output_format.value,
                            "generated": generated,
                            "total": sum(len(c.document_specs) for c in self.cases),
                        })

                except Exception as e:
                    logger.error(
                        "doc_generation_error",
                        case=case.internal_id,
                        filename=filename,
                        template=doc_spec.template_class,
                        format=doc_spec.output_format.value,
                        error=str(e),
                    )
                    self.tracker.mark_doc_error(case.internal_id, filename, str(e))
                    errors += 1

            # Update case-level tracking
            gen_count = len(case.document_specs) - len(
                self.tracker.get_ungenerated_docs(case.internal_id)
            )
            self.tracker.mark_case_pdfs_generated(case.internal_id, gen_count)

            logger.info(
                "case_docs_complete",
                case_id=case.internal_id,
                generated_this_run=generated,
            )

        logger.info(
            "doc_generation_complete",
            generated=generated,
            skipped=skipped,
            errors=errors,
        )
        return {"generated": generated, "skipped": skipped, "errors": errors}

    # Backward-compatible alias
    generate_pdfs = generate_documents

    # --- Step 3: Create cases in MerusCase ---

    async def create_cases(self, dry_run: bool = False) -> dict[str, Any]:
        """Create all cases in MerusCase via browser automation."""
        from orchestration.case_creator import CaseCreator

        if not self.cases:
            logger.warning("no_cases_loaded")
            return {"total": 0, "created": 0, "failed": 0}

        creator = CaseCreator(self.tracker, audit=self.audit, dry_run=dry_run)
        return await creator.create_all_cases(self.cases)

    # --- Step 4: Upload documents ---

    async def upload_documents(self) -> dict[str, Any]:
        """Upload all generated PDFs to MerusCase via API."""
        from orchestration.document_uploader import DocumentUploader

        uploader = DocumentUploader(self.tracker, audit=self.audit)
        return await uploader.upload_all()

    # --- Full pipeline ---

    async def run_all(self, dry_run: bool = False) -> dict[str, Any]:
        """Execute the full 4-step pipeline."""
        results: dict[str, Any] = {}

        run = self.tracker.get_current_run()
        run_id = run["id"] if run else 0
        if self.audit:
            self.audit.log_pipeline_start(run_id, len(self.cases) or len(CASE_PROFILES))

        # Step 1
        logger.info("pipeline_step", step=1, name="Generate Data")
        self.generate_data()
        results["data"] = {"cases": len(self.cases)}

        # Step 2
        logger.info("pipeline_step", step=2, name="Generate PDFs")
        results["pdfs"] = self.generate_pdfs()

        # Step 3
        logger.info("pipeline_step", step=3, name="Create Cases")
        results["cases"] = await self.create_cases(dry_run=dry_run)

        # Step 4
        logger.info("pipeline_step", step=4, name="Upload Documents")
        results["uploads"] = await self.upload_documents()

        # Finalize
        run = self.tracker.get_current_run()
        if run:
            self.tracker.complete_run(run["id"])

        if self.audit:
            self.audit.log_pipeline_complete(run_id, results)

        logger.info("pipeline_complete", results=results)
        return results
