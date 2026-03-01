"""
Main orchestration pipeline — 4-step flow:
  1. Generate case data
  2. Generate PDFs
  3. Create cases in MerusCase (browser automation)
  4. Upload documents to MerusCase (API)

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path
from typing import Any

import structlog

from config import OUTPUT_DIR, RANDOM_SEED
from data.case_profiles import CASE_PROFILES
from data.fake_data_generator import FakeDataGenerator
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
}


def _load_template_class(class_name: str):
    """Dynamically import and return a template class."""
    module_path = TEMPLATE_REGISTRY.get(class_name)
    if not module_path:
        raise ValueError(f"Unknown template class: {class_name}")
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def _sanitize_filename(name: str) -> str:
    """Make a safe filename from a document title. Prevents path traversal."""
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    name = re.sub(r'\s+', '_', name)
    name = name.replace('..', '_')
    name = Path(name).name  # Extract filename component only
    name = name[:80]  # Limit length
    if not name.endswith('.pdf'):
        name += '.pdf'
    return name


class Pipeline:
    def __init__(self, tracker: ProgressTracker, audit: PipelineAuditLogger | None = None):
        self.tracker = tracker
        self.audit = audit
        self.generator = FakeDataGenerator(seed=RANDOM_SEED)
        self.cases: list[GeneratedCase] = []

    # --- Step 1: Generate case data ---

    def generate_data(self) -> list[GeneratedCase]:
        """Generate all case data objects."""
        run = self.tracker.get_current_run()
        if not run:
            run_id = self.tracker.start_run(total_cases=len(CASE_PROFILES))
        else:
            run_id = run["id"]

        logger.info("generating_data", total_profiles=len(CASE_PROFILES))

        self.cases = []
        for profile in CASE_PROFILES:
            case = self.generator.generate_case(profile)
            self.cases.append(case)

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
                filename = _sanitize_filename(
                    f"{case.internal_id}_{i+1:03d}_{doc_spec.subtype.value}_{doc_spec.doc_date}"
                )
                self.tracker.register_document(
                    case_internal_id=case.internal_id,
                    filename=filename,
                    subtype=doc_spec.subtype.value,
                    title=doc_spec.title,
                    doc_date=doc_spec.doc_date.isoformat(),
                )

            logger.info(
                "case_data_generated",
                case_id=case.internal_id,
                applicant=case.applicant.full_name,
                stage=case.litigation_stage.value,
                doc_count=len(case.document_specs),
            )

        total_docs = sum(len(c.document_specs) for c in self.cases)
        logger.info("data_generation_complete", cases=len(self.cases), total_docs=total_docs)
        return self.cases

    # --- Step 2: Generate PDFs ---

    def generate_pdfs(self) -> dict[str, int]:
        """Generate PDF files for all cases."""
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

            for i, doc_spec in enumerate(case.document_specs):
                filename = _sanitize_filename(
                    f"{case.internal_id}_{i+1:03d}_{doc_spec.subtype.value}_{doc_spec.doc_date}"
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
                    template_cls = _load_template_class(doc_spec.template_class)
                    template = template_cls(case)
                    template.generate(output_path, doc_spec)

                    self.tracker.mark_pdf_generated(
                        case.internal_id, filename, str(output_path)
                    )
                    generated += 1

                except Exception as e:
                    logger.error(
                        "pdf_generation_error",
                        case=case.internal_id,
                        filename=filename,
                        template=doc_spec.template_class,
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
                "case_pdfs_complete",
                case_id=case.internal_id,
                generated_this_run=generated,
            )

        logger.info(
            "pdf_generation_complete",
            generated=generated,
            skipped=skipped,
            errors=errors,
        )
        return {"generated": generated, "skipped": skipped, "errors": errors}

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
            self.audit.log_pipeline_start(run_id, len(CASE_PROFILES))

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
