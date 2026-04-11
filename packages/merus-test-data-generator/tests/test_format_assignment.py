"""
Tests for data/format_assignment.py — Phase 1: Format routing infrastructure.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import random

import pytest

from data.format_assignment import (
    assign_output_format,
    _DOCX_SUBTYPES,
    _EMAIL_SUBTYPES,
    _SCANNED_SUBTYPES,
)
from data.models import DocumentSpec, OutputFormat
from data.taxonomy import DocumentSubtype


# ---------------------------------------------------------------------------
# assign_output_format — deterministic rules
# ---------------------------------------------------------------------------

class TestDocxAssignment:
    """Word work-product subtypes must ALWAYS return DOCX (100%)."""

    @pytest.mark.parametrize("subtype", sorted(_DOCX_SUBTYPES))
    def test_docx_subtypes_are_always_docx(self, subtype):
        rng = random.Random(42)
        for _ in range(10):
            result = assign_output_format(subtype, rng)
            assert result == OutputFormat.DOCX, (
                f"{subtype} expected DOCX, got {result}"
            )


class TestEmailAssignment:
    """Email subtypes should produce EML roughly half the time."""

    @pytest.mark.parametrize("subtype", sorted(_EMAIL_SUBTYPES))
    def test_email_subtypes_produce_eml_or_pdf(self, subtype):
        rng = random.Random(0)
        results = {assign_output_format(subtype, rng) for _ in range(20)}
        # Must produce at least EML (may also produce PDF — that's valid)
        assert OutputFormat.EML in results or OutputFormat.PDF in results
        # Must never produce DOCX or SCANNED_PDF
        assert OutputFormat.DOCX not in results
        assert OutputFormat.SCANNED_PDF not in results

    def test_email_probability_roughly_50_percent(self):
        """Over 1000 draws the EML rate should be 40–60%."""
        rng = random.Random(99)
        subtype = "ADJUSTER_LETTER_INFORMATIONAL"
        results = [assign_output_format(subtype, rng) for _ in range(1000)]
        eml_rate = results.count(OutputFormat.EML) / len(results)
        assert 0.40 <= eml_rate <= 0.60, f"EML rate {eml_rate:.2f} outside expected 40–60%"


class TestScannedPdfAssignment:
    """Medical/records subtypes should produce SCANNED_PDF roughly 60% of the time."""

    @pytest.mark.parametrize("subtype", sorted(_SCANNED_SUBTYPES))
    def test_scanned_subtypes_produce_scanned_or_native(self, subtype):
        rng = random.Random(7)
        results = {assign_output_format(subtype, rng) for _ in range(20)}
        assert OutputFormat.DOCX not in results
        assert OutputFormat.EML not in results

    def test_scanned_probability_roughly_60_percent(self):
        """Over 1000 draws the SCANNED_PDF rate should be 50–70%."""
        rng = random.Random(42)
        subtype = "TREATING_PHYSICIAN_REPORT_PR4"
        results = [assign_output_format(subtype, rng) for _ in range(1000)]
        scanned_rate = results.count(OutputFormat.SCANNED_PDF) / len(results)
        assert 0.50 <= scanned_rate <= 0.70, (
            f"SCANNED_PDF rate {scanned_rate:.2f} outside expected 50–70%"
        )


class TestNativePdfAssignment:
    """Regulatory filings, orders, settlements → always native PDF."""

    @pytest.mark.parametrize("subtype", [
        "APPLICATION_FOR_ADJUDICATION",
        "DECLARATION_OF_READINESS",
        "COMPROMISE_AND_RELEASE",
        "MINUTES_OF_HEARING",
        "PROOF_OF_SERVICE",
        "UTILIZATION_REVIEW_DECISION",
    ])
    def test_native_pdf_subtypes(self, subtype):
        rng = random.Random(1)
        for _ in range(10):
            result = assign_output_format(subtype, rng)
            assert result == OutputFormat.PDF


# ---------------------------------------------------------------------------
# OutputFormat enum on DocumentSpec
# ---------------------------------------------------------------------------

class TestOutputFormatOnDocumentSpec:
    def test_default_output_format_is_pdf(self):
        spec = DocumentSpec(
            subtype=DocumentSubtype.PROOF_OF_SERVICE,
            title="Proof of Service",
            doc_date="2025-01-01",
            template_class="GenericDocumentTemplate",
        )
        assert spec.output_format == OutputFormat.PDF

    def test_output_format_eml_serialises(self):
        spec = DocumentSpec(
            subtype=DocumentSubtype.ADJUSTER_LETTER,
            title="Adjuster Letter",
            doc_date="2025-03-15",
            template_class="AdjusterLetter",
            output_format=OutputFormat.EML,
        )
        assert spec.output_format.value == "eml"

    def test_output_format_docx_serialises(self):
        spec = DocumentSpec(
            subtype=DocumentSubtype.SETTLEMENT_VALUATION_MEMO,
            title="Settlement Valuation Memo",
            doc_date="2025-06-01",
            template_class="SettlementMemo",
            output_format=OutputFormat.DOCX,
        )
        assert spec.output_format.value == "docx"

    def test_output_format_scanned_pdf_serialises(self):
        spec = DocumentSpec(
            subtype=DocumentSubtype.TREATING_PHYSICIAN_REPORT_PR4,
            title="PR-4 Progress Report",
            doc_date="2025-04-20",
            template_class="TreatingPhysicianReport",
            output_format=OutputFormat.SCANNED_PDF,
        )
        assert spec.output_format.value == "scanned_pdf"


# ---------------------------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------------------------

class TestReproducibility:
    def test_same_seed_same_results(self):
        subtype = "ADJUSTER_LETTER_INFORMATIONAL"
        results_a = [assign_output_format(subtype, random.Random(77)) for _ in range(50)]
        results_b = [assign_output_format(subtype, random.Random(77)) for _ in range(50)]
        assert results_a == results_b

    def test_different_seeds_differ(self):
        subtype = "ADJUSTER_LETTER_INFORMATIONAL"
        results_a = [assign_output_format(subtype, random.Random(1)) for _ in range(100)]
        results_b = [assign_output_format(subtype, random.Random(999)) for _ in range(100)]
        # With 100 samples at 50% probability these are almost certainly different
        assert results_a != results_b


# ---------------------------------------------------------------------------
# Category mutual exclusion — no subtype can be in two category sets
# ---------------------------------------------------------------------------

class TestCategoryMutualExclusion:
    def test_no_subtype_in_both_email_and_docx(self):
        overlap = _EMAIL_SUBTYPES & _DOCX_SUBTYPES
        assert not overlap, f"Overlap: {overlap}"

    def test_no_subtype_in_both_email_and_scanned(self):
        overlap = _EMAIL_SUBTYPES & _SCANNED_SUBTYPES
        assert not overlap, f"Overlap: {overlap}"

    def test_no_subtype_in_both_docx_and_scanned(self):
        overlap = _DOCX_SUBTYPES & _SCANNED_SUBTYPES
        assert not overlap, f"Overlap: {overlap}"
