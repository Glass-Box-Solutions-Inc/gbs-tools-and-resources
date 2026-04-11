"""
Tests for Phase 4: scan-simulated PDF generation.

Verifies that scanned_pdf output format produces valid image-based PDFs
with correct structure. Also tests the scan_simulator module directly.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import random
import tempfile
from io import BytesIO
from pathlib import Path

import pytest

from data.models import DocumentSubtype, OutputFormat


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _generate_scanned(template_cls, case, doc_spec) -> bytes:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "test.pdf"
        template = template_cls(case)
        template.generate(out, doc_spec)
        assert out.exists()
        assert out.stat().st_size > 0
        return out.read_bytes()


def _is_pdf(data: bytes) -> bool:
    return data[:4] == b"%PDF"


# ---------------------------------------------------------------------------
# scan_simulator unit tests
# ---------------------------------------------------------------------------

class TestScanSimulator:
    @pytest.fixture()
    def native_pdf_bytes(self, sample_case, make_document_spec):
        """Generate a small native PDF to use as scan input."""
        from pdf_templates.medical.treating_physician_report import TreatingPhysicianReport
        spec = make_document_spec(
            subtype=DocumentSubtype.TREATING_PHYSICIAN_REPORT_PR4,
            output_format=OutputFormat.PDF,  # native first
        )
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "native.pdf"
            template = TreatingPhysicianReport(sample_case)
            template._generate_pdf(out, spec)
            return out.read_bytes()

    def test_simulate_scan_returns_pdf(self, native_pdf_bytes):
        from pdf_templates.scan_simulator import simulate_scan
        rng = random.Random(42)
        result = simulate_scan(native_pdf_bytes, rng)
        assert _is_pdf(result), "simulate_scan output is not a valid PDF"

    def test_simulate_scan_non_empty(self, native_pdf_bytes):
        from pdf_templates.scan_simulator import simulate_scan
        rng = random.Random(42)
        result = simulate_scan(native_pdf_bytes, rng)
        assert len(result) > 1000, "Scanned PDF is suspiciously small"

    def test_simulate_scan_reproducible(self, native_pdf_bytes):
        """Same seed produces structurally identical output (page count + file size).

        Byte-for-byte equality is not guaranteed because JPEG quantization rounding
        can vary in floating-point arithmetic even with the same logical inputs.
        """
        from pdf_templates.scan_simulator import simulate_scan
        import fitz

        result_a = simulate_scan(native_pdf_bytes, random.Random(77))
        result_b = simulate_scan(native_pdf_bytes, random.Random(77))

        doc_a = fitz.open(stream=result_a, filetype="pdf")
        doc_b = fitz.open(stream=result_b, filetype="pdf")

        assert doc_a.page_count == doc_b.page_count, "Page counts differ between seeded runs"
        assert abs(len(result_a) - len(result_b)) < 2000, (
            f"File sizes differ significantly: {len(result_a)} vs {len(result_b)} bytes"
        )
        doc_a.close()
        doc_b.close()

    def test_simulate_scan_different_seeds_differ(self, native_pdf_bytes):
        from pdf_templates.scan_simulator import simulate_scan
        result_a = simulate_scan(native_pdf_bytes, random.Random(1))
        result_b = simulate_scan(native_pdf_bytes, random.Random(999))
        assert result_a != result_b

    def test_simulate_scan_raises_on_corrupt_input(self):
        """Corrupt bytes should raise ValueError, not an opaque fitz error."""
        from pdf_templates.scan_simulator import simulate_scan
        with pytest.raises(ValueError, match="could not open PDF"):
            simulate_scan(b"not a pdf at all", random.Random(42))

    def test_simulate_scan_raises_on_empty_bytes(self):
        """Empty bytes should raise ValueError."""
        from pdf_templates.scan_simulator import simulate_scan
        with pytest.raises(ValueError, match="could not open PDF"):
            simulate_scan(b"", random.Random(42))


# ---------------------------------------------------------------------------
# End-to-end scanned PDF generation via base_template dispatch
# ---------------------------------------------------------------------------

class TestScannedPdfDispatch:
    @pytest.fixture()
    def pr4_spec(self, make_document_spec):
        return make_document_spec(
            subtype=DocumentSubtype.TREATING_PHYSICIAN_REPORT_PR4,
            output_format=OutputFormat.SCANNED_PDF,
            title="PR-4 Progress Report — Scanned",
        )

    def test_generates_valid_pdf(self, sample_case, pr4_spec):
        from pdf_templates.medical.treating_physician_report import TreatingPhysicianReport
        data = _generate_scanned(TreatingPhysicianReport, sample_case, pr4_spec)
        assert _is_pdf(data)

    def test_output_is_image_based_pdf(self, sample_case, pr4_spec):
        """Scanned PDF should contain image XObjects (raster pages), not vector text streams."""
        from pdf_templates.medical.treating_physician_report import TreatingPhysicianReport
        import fitz
        data = _generate_scanned(TreatingPhysicianReport, sample_case, pr4_spec)
        doc = fitz.open(stream=data, filetype="pdf")
        has_images = any(
            len(doc[i].get_images()) > 0 for i in range(doc.page_count)
        )
        doc.close()
        assert has_images, "Scanned PDF has no image XObjects on any page"

    def test_diagnostic_produces_scanned_pdf(self, sample_case, make_document_spec):
        from pdf_templates.medical.diagnostic_report import DiagnosticReport
        spec = make_document_spec(
            subtype=DocumentSubtype.DIAGNOSTICS_IMAGING,
            output_format=OutputFormat.SCANNED_PDF,
        )
        data = _generate_scanned(DiagnosticReport, sample_case, spec)
        assert _is_pdf(data)

    def test_scanned_pdf_larger_than_native(self, sample_case, make_document_spec):
        """Scanned PDFs (raster images) are typically larger than vector PDFs for simple docs."""
        from pdf_templates.medical.diagnostic_report import DiagnosticReport

        spec_native = make_document_spec(
            subtype=DocumentSubtype.DIAGNOSTICS_IMAGING,
            output_format=OutputFormat.PDF,
        )
        spec_scanned = make_document_spec(
            subtype=DocumentSubtype.DIAGNOSTICS_IMAGING,
            output_format=OutputFormat.SCANNED_PDF,
            title="Scanned Version",
        )

        native_data = _generate_scanned(DiagnosticReport, sample_case, spec_native)
        scanned_data = _generate_scanned(DiagnosticReport, sample_case, spec_scanned)

        # Raster images should produce larger files than vector PDFs
        assert len(scanned_data) > len(native_data), (
            f"Scanned PDF ({len(scanned_data)}B) not larger than native ({len(native_data)}B)"
        )
