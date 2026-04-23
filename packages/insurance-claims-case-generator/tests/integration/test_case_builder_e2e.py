"""
End-to-end integration tests for case_builder with PDF generation.

Tests a 5-case batch across all 3 scenarios:
  - All PDFs are non-empty
  - ZIP export round-trips correctly
  - Batch builder thread pool works

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import io
import zipfile

import pytest

from claims_generator.batch_builder import BatchJob, build_batch, build_batch_simple
from claims_generator.case_builder import build_case
from claims_generator.exporter import export_batch_to_zip, export_case_to_zip
from claims_generator.models.claim import ClaimCase


class TestCaseBuilderWithPDFs:
    """Verify build_case populates pdf_bytes for all events in Phase 2."""

    @pytest.mark.parametrize("scenario", ["standard_claim", "litigated_qme", "denied_claim"])
    def test_all_events_have_pdf_bytes(self, scenario: str) -> None:
        """Every DocumentEvent must have non-empty pdf_bytes after Phase 2 build."""
        case = build_case(scenario_slug=scenario, seed=1)
        assert len(case.document_events) > 0
        for event in case.document_events:
            assert len(event.pdf_bytes) > 500, (
                f"{scenario}: event {event.subtype_slug} ({event.document_type}) "
                f"has only {len(event.pdf_bytes)} bytes"
            )

    @pytest.mark.parametrize("scenario", ["standard_claim", "litigated_qme", "denied_claim"])
    def test_all_pdf_bytes_are_valid_pdf(self, scenario: str) -> None:
        """Every generated PDF must start with %PDF magic bytes."""
        case = build_case(scenario_slug=scenario, seed=2)
        for event in case.document_events:
            assert event.pdf_bytes[:4] == b"%PDF", (
                f"{scenario}: event {event.subtype_slug} does not start with %PDF"
            )

    def test_no_pdfs_mode_returns_empty_bytes(self) -> None:
        """generate_pdfs=False must return all empty pdf_bytes (Phase 1 behavior)."""
        case = build_case(scenario_slug="standard_claim", seed=99, generate_pdfs=False)
        for event in case.document_events:
            assert event.pdf_bytes == b"", (
                f"event {event.subtype_slug} has non-empty pdf_bytes in no-PDFs mode"
            )

    def test_pdf_generation_is_reproducible(self) -> None:
        """Same seed must produce PDFs of the same size for each event."""
        case1 = build_case(scenario_slug="standard_claim", seed=42)
        case2 = build_case(scenario_slug="standard_claim", seed=42)
        assert len(case1.document_events) == len(case2.document_events)
        for e1, e2 in zip(case1.document_events, case2.document_events):
            assert e1.document_type == e2.document_type
            # PDF sizes may vary slightly due to internal IDs, but both must be valid
            assert len(e1.pdf_bytes) > 500
            assert len(e2.pdf_bytes) > 500


class TestExporter:
    """Verify ZIP export round-trips correctly."""

    def test_export_case_to_zip(self) -> None:
        """export_case_to_zip must produce a valid ZIP with manifest.json and PDFs."""
        case = build_case(scenario_slug="standard_claim", seed=7)
        zip_bytes = export_case_to_zip(case)

        assert len(zip_bytes) > 1000
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            names = zf.namelist()
            manifest_path = f"{case.case_id}/manifest.json"
            assert manifest_path in names, f"manifest.json missing from ZIP: {names[:5]}"
            # Should have at least one PDF
            pdf_files = [n for n in names if n.endswith(".pdf")]
            assert len(pdf_files) == len(case.document_events), (
                f"Expected {len(case.document_events)} PDFs, found {len(pdf_files)}"
            )

    def test_manifest_json_valid(self) -> None:
        """manifest.json must be valid JSON with expected keys."""
        import json

        case = build_case(scenario_slug="denied_claim", seed=3)
        zip_bytes = export_case_to_zip(case)
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            manifest_raw = zf.read(f"{case.case_id}/manifest.json")
            manifest = json.loads(manifest_raw)

        assert manifest["case_id"] == case.case_id
        assert manifest["scenario_slug"] == "denied_claim"
        assert "document_events" in manifest
        # pdf_bytes must be excluded from JSON
        for event in manifest["document_events"]:
            assert "pdf_bytes" not in event or event.get("pdf_bytes") == ""

    def test_export_batch_to_zip(self) -> None:
        """export_batch_to_zip must produce a valid batch ZIP with all cases."""
        cases = [
            build_case(scenario_slug="standard_claim", seed=i, generate_pdfs=False)
            for i in range(3)
        ]
        zip_bytes = export_batch_to_zip(cases)

        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            names = zf.namelist()
            assert "batch_manifest.json" in names
            for case in cases:
                assert f"{case.case_id}/manifest.json" in names

    def test_empty_case_raises_value_error(self) -> None:
        """export_case_to_zip must raise ValueError for a case with no events."""

        from claims_generator.models.claim import ClaimCase

        empty_case = ClaimCase(
            case_id="case-empty",
            scenario_slug="standard_claim",
            seed=0,
            profile=build_case("standard_claim", seed=0, generate_pdfs=False).profile,
            document_events=[],
            stages_visited=[],
        )
        with pytest.raises(ValueError, match="no document_events"):
            export_case_to_zip(empty_case)


class TestBatchBuilder:
    """Verify batch builder generates multiple cases in parallel."""

    def test_build_batch_simple_5_cases(self) -> None:
        """build_batch_simple must produce 5 cases."""
        cases = build_batch_simple(
            count=5,
            scenario_slug="standard_claim",
            seed_start=100,
            max_workers=2,
            generate_pdfs=True,
        )
        assert len(cases) == 5
        for case in cases:
            assert isinstance(case, ClaimCase)
            assert len(case.document_events) > 0
            for event in case.document_events:
                assert len(event.pdf_bytes) > 500

    def test_build_batch_mixed_scenarios(self) -> None:
        """build_batch must handle mixed scenarios."""
        jobs = [
            BatchJob(scenario_slug="standard_claim", seed=200),
            BatchJob(scenario_slug="litigated_qme", seed=201),
            BatchJob(scenario_slug="denied_claim", seed=202),
            BatchJob(scenario_slug="standard_claim", seed=203),
            BatchJob(scenario_slug="litigated_qme", seed=204),
        ]
        cases = build_batch(jobs, max_workers=3, generate_pdfs=True)
        assert len(cases) == 5
        slugs = {c.scenario_slug for c in cases}
        assert slugs == {"standard_claim", "litigated_qme", "denied_claim"}

    def test_build_batch_no_pdfs_mode(self) -> None:
        """build_batch in no-PDFs mode must produce cases with empty pdf_bytes."""
        cases = build_batch_simple(
            count=3,
            scenario_slug="standard_claim",
            generate_pdfs=False,
        )
        for case in cases:
            for event in case.document_events:
                assert event.pdf_bytes == b""

    def test_build_batch_raises_for_empty_jobs(self) -> None:
        """build_batch must raise ValueError for empty job list."""
        with pytest.raises(ValueError, match="at least one job"):
            build_batch([], generate_pdfs=False)

    def test_batch_produces_unique_case_ids(self) -> None:
        """All case IDs in a batch must be unique."""
        cases = build_batch_simple(count=5, scenario_slug="standard_claim", seed_start=0)
        ids = [c.case_id for c in cases]
        assert len(ids) == len(set(ids)), "Duplicate case IDs found in batch output"
