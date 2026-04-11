"""
Tests for Phase 7: Administrative noise document templates.

Verifies that FaxCoverSheet, FileNote, BlankPage, and CoverLetterEnclosure
generate valid output and that the format assignment and lifecycle wiring
are correct.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import random
import zipfile
from io import BytesIO
from pathlib import Path

import pytest

from data.models import DocumentSubtype, OutputFormat


# ---------------------------------------------------------------------------
# Taxonomy
# ---------------------------------------------------------------------------

class TestTaxonomyRegistration:
    """New subtypes are present in the taxonomy enum and labels."""

    def test_internal_file_note_in_enum(self):
        assert DocumentSubtype.INTERNAL_FILE_NOTE.value == "INTERNAL_FILE_NOTE"

    def test_blank_scanned_page_in_enum(self):
        assert DocumentSubtype.BLANK_SCANNED_PAGE.value == "BLANK_SCANNED_PAGE"

    def test_fax_cover_sheet_in_enum(self):
        assert DocumentSubtype.FAX_COVER_SHEET.value == "FAX_COVER_SHEET"

    def test_cover_letter_enclosure_in_enum(self):
        assert DocumentSubtype.COVER_LETTER_ENCLOSURE.value == "COVER_LETTER_ENCLOSURE"

    def test_new_subtypes_have_labels(self):
        from data.taxonomy import DOCUMENT_SUBTYPE_LABELS
        for subtype in [
            "INTERNAL_FILE_NOTE",
            "BLANK_SCANNED_PAGE",
            "FAX_COVER_SHEET",
            "COVER_LETTER_ENCLOSURE",
        ]:
            assert subtype in DOCUMENT_SUBTYPE_LABELS, f"Missing label for {subtype}"
            assert len(DOCUMENT_SUBTYPE_LABELS[subtype]) > 0

    def test_new_subtypes_in_correspondence_type(self):
        from data.taxonomy import DOCUMENT_TYPE_TO_SUBTYPES
        corr = DOCUMENT_TYPE_TO_SUBTYPES["CORRESPONDENCE"]
        for subtype in ["INTERNAL_FILE_NOTE", "BLANK_SCANNED_PAGE", "FAX_COVER_SHEET", "COVER_LETTER_ENCLOSURE"]:
            assert subtype in corr, f"{subtype} missing from CORRESPONDENCE type mapping"


# ---------------------------------------------------------------------------
# Format assignment
# ---------------------------------------------------------------------------

class TestFormatAssignment:
    """Administrative noise subtypes route to the correct formats."""

    def _assign(self, subtype: str, seed: int = 42) -> str:
        from data.format_assignment import assign_output_format
        rng = random.Random(seed)
        return assign_output_format(subtype, rng).value

    def test_fax_cover_sheet_always_scanned(self):
        for seed in range(20):
            assert self._assign("FAX_COVER_SHEET", seed) == "scanned_pdf"

    def test_fax_correspondence_always_scanned(self):
        for seed in range(20):
            assert self._assign("FAX_CORRESPONDENCE", seed) == "scanned_pdf"

    def test_blank_scanned_page_always_scanned(self):
        for seed in range(20):
            assert self._assign("BLANK_SCANNED_PAGE", seed) == "scanned_pdf"

    def test_internal_file_note_is_pdf(self):
        # No rule overrides this — should default to native PDF
        assert self._assign("INTERNAL_FILE_NOTE") == "pdf"

    def test_evaluation_cover_letter_is_pdf(self):
        assert self._assign("EVALUATION_COVER_LETTER") == "pdf"

    def test_cover_letter_enclosure_is_pdf(self):
        assert self._assign("COVER_LETTER_ENCLOSURE") == "pdf"


# ---------------------------------------------------------------------------
# Template registry
# ---------------------------------------------------------------------------

class TestRegistryEntries:
    """All new subtypes map to the administrative templates in the registry.

    get_template_for_subtype returns (class_name_str, variant) — compare strings.
    """

    def test_registry_has_fax_cover_sheet(self):
        from pdf_templates.registry import get_template_for_subtype
        class_name, _ = get_template_for_subtype("FAX_COVER_SHEET")
        assert class_name == "FaxCoverSheet"

    def test_registry_has_fax_correspondence(self):
        from pdf_templates.registry import get_template_for_subtype
        class_name, _ = get_template_for_subtype("FAX_CORRESPONDENCE")
        assert class_name == "FaxCoverSheet"

    def test_registry_has_internal_file_note(self):
        from pdf_templates.registry import get_template_for_subtype
        class_name, _ = get_template_for_subtype("INTERNAL_FILE_NOTE")
        assert class_name == "FileNote"

    def test_registry_has_blank_scanned_page(self):
        from pdf_templates.registry import get_template_for_subtype
        class_name, _ = get_template_for_subtype("BLANK_SCANNED_PAGE")
        assert class_name == "BlankPage"

    def test_registry_has_evaluation_cover_letter(self):
        from pdf_templates.registry import get_template_for_subtype
        class_name, _ = get_template_for_subtype("EVALUATION_COVER_LETTER")
        assert class_name == "CoverLetterEnclosure"

    def test_registry_has_cover_letter_enclosure(self):
        from pdf_templates.registry import get_template_for_subtype
        class_name, _ = get_template_for_subtype("COVER_LETTER_ENCLOSURE")
        assert class_name == "CoverLetterEnclosure"


# ---------------------------------------------------------------------------
# Template output
# ---------------------------------------------------------------------------

class TestFaxCoverSheetGeneration:
    """FaxCoverSheet produces a valid scanned PDF."""

    def test_generates_pdf_bytes(self, sample_case, make_document_spec, tmp_path):
        doc_spec = make_document_spec(DocumentSubtype.FAX_COVER_SHEET)
        from pdf_templates.administrative.fax_cover_sheet import FaxCoverSheet
        template = FaxCoverSheet(sample_case)
        out = tmp_path / "fax_cover.pdf"
        # Generate as native PDF (scanned_pdf goes through scan simulator — slow)
        template._generate_pdf(out, doc_spec)
        assert out.exists()
        assert out.stat().st_size > 1000

    def test_pdf_is_valid_pdf(self, sample_case, make_document_spec, tmp_path):
        doc_spec = make_document_spec(DocumentSubtype.FAX_COVER_SHEET)
        from pdf_templates.administrative.fax_cover_sheet import FaxCoverSheet
        template = FaxCoverSheet(sample_case)
        out = tmp_path / "fax_cover.pdf"
        template._generate_pdf(out, doc_spec)
        assert out.read_bytes()[:4] == b"%PDF"


class TestFileNoteGeneration:
    """FileNote produces a valid native PDF."""

    def test_generates_pdf(self, sample_case, make_document_spec, tmp_path):
        doc_spec = make_document_spec(DocumentSubtype.INTERNAL_FILE_NOTE)
        from pdf_templates.administrative.file_note import FileNote
        template = FileNote(sample_case)
        out = tmp_path / "file_note.pdf"
        template._generate_pdf(out, doc_spec)
        assert out.exists()
        assert out.stat().st_size > 500

    def test_is_valid_pdf(self, sample_case, make_document_spec, tmp_path):
        doc_spec = make_document_spec(DocumentSubtype.INTERNAL_FILE_NOTE)
        from pdf_templates.administrative.file_note import FileNote
        template = FileNote(sample_case)
        out = tmp_path / "file_note.pdf"
        template._generate_pdf(out, doc_spec)
        assert out.read_bytes()[:4] == b"%PDF"


class TestBlankPageGeneration:
    """BlankPage produces a valid (near-blank) PDF."""

    def test_generates_pdf(self, sample_case, make_document_spec, tmp_path):
        doc_spec = make_document_spec(DocumentSubtype.BLANK_SCANNED_PAGE)
        from pdf_templates.administrative.blank_page import BlankPage
        template = BlankPage(sample_case)
        out = tmp_path / "blank.pdf"
        template._generate_pdf(out, doc_spec)
        assert out.exists()
        assert out.stat().st_size > 0

    def test_is_valid_pdf(self, sample_case, make_document_spec, tmp_path):
        doc_spec = make_document_spec(DocumentSubtype.BLANK_SCANNED_PAGE)
        from pdf_templates.administrative.blank_page import BlankPage
        template = BlankPage(sample_case)
        out = tmp_path / "blank.pdf"
        template._generate_pdf(out, doc_spec)
        assert out.read_bytes()[:4] == b"%PDF"

    def test_multiple_variants_all_valid(self, sample_case, make_document_spec, tmp_path):
        """Run 5 different seeds to exercise all random variants."""
        from pdf_templates.administrative.blank_page import BlankPage
        import random as _random
        for seed in range(5):
            _random.seed(seed)
            doc_spec = make_document_spec(DocumentSubtype.BLANK_SCANNED_PAGE)
            template = BlankPage(sample_case)
            out = tmp_path / f"blank_{seed}.pdf"
            template._generate_pdf(out, doc_spec)
            assert out.read_bytes()[:4] == b"%PDF"


class TestCoverLetterEnclosureGeneration:
    """CoverLetterEnclosure produces a valid native PDF."""

    def test_generates_pdf(self, sample_case, make_document_spec, tmp_path):
        doc_spec = make_document_spec(DocumentSubtype.COVER_LETTER_ENCLOSURE)
        from pdf_templates.administrative.cover_letter_enclosure import CoverLetterEnclosure
        template = CoverLetterEnclosure(sample_case)
        out = tmp_path / "cover_letter.pdf"
        template._generate_pdf(out, doc_spec)
        assert out.exists()
        assert out.stat().st_size > 1000

    def test_is_valid_pdf(self, sample_case, make_document_spec, tmp_path):
        doc_spec = make_document_spec(DocumentSubtype.COVER_LETTER_ENCLOSURE)
        from pdf_templates.administrative.cover_letter_enclosure import CoverLetterEnclosure
        template = CoverLetterEnclosure(sample_case)
        out = tmp_path / "cover_letter.pdf"
        template._generate_pdf(out, doc_spec)
        assert out.read_bytes()[:4] == b"%PDF"

    def test_evaluation_cover_letter_variant(self, sample_case, make_document_spec, tmp_path):
        doc_spec = make_document_spec(DocumentSubtype.EVALUATION_COVER_LETTER)
        from pdf_templates.administrative.cover_letter_enclosure import CoverLetterEnclosure
        template = CoverLetterEnclosure(sample_case)
        out = tmp_path / "eval_cover.pdf"
        template._generate_pdf(out, doc_spec)
        assert out.read_bytes()[:4] == b"%PDF"


# ---------------------------------------------------------------------------
# Lifecycle wiring
# ---------------------------------------------------------------------------

class TestLifecycleWiring:
    """Noise rules are present in lifecycle stages."""

    def test_active_treatment_has_fax_rule(self):
        from data.lifecycle_engine import LIFECYCLE_DOCUMENT_RULES
        subtypes = {r.subtype for r in LIFECYCLE_DOCUMENT_RULES["active_treatment"]}
        assert "FAX_COVER_SHEET" in subtypes

    def test_active_treatment_has_file_note_rule(self):
        from data.lifecycle_engine import LIFECYCLE_DOCUMENT_RULES
        subtypes = {r.subtype for r in LIFECYCLE_DOCUMENT_RULES["active_treatment"]}
        assert "INTERNAL_FILE_NOTE" in subtypes

    def test_active_treatment_has_blank_page_rule(self):
        from data.lifecycle_engine import LIFECYCLE_DOCUMENT_RULES
        subtypes = {r.subtype for r in LIFECYCLE_DOCUMENT_RULES["active_treatment"]}
        assert "BLANK_SCANNED_PAGE" in subtypes

    def test_discovery_has_fax_rule(self):
        from data.lifecycle_engine import LIFECYCLE_DOCUMENT_RULES
        subtypes = {r.subtype for r in LIFECYCLE_DOCUMENT_RULES["discovery"]}
        assert "FAX_COVER_SHEET" in subtypes

    def test_qme_evaluation_has_cover_letter_rule(self):
        from data.lifecycle_engine import LIFECYCLE_DOCUMENT_RULES
        subtypes = {r.subtype for r in LIFECYCLE_DOCUMENT_RULES["qme_evaluation"]}
        assert "EVALUATION_COVER_LETTER" in subtypes

    def test_noise_rules_have_low_probability(self):
        """All noise rules must have probability ≤ 0.20 to avoid bloating case files."""
        from data.lifecycle_engine import LIFECYCLE_DOCUMENT_RULES
        noise_subtypes = {
            "FAX_COVER_SHEET", "FAX_CORRESPONDENCE",
            "INTERNAL_FILE_NOTE", "BLANK_SCANNED_PAGE",
            "COVER_LETTER_ENCLOSURE", "EVALUATION_COVER_LETTER",
        }
        for stage, rules in LIFECYCLE_DOCUMENT_RULES.items():
            for rule in rules:
                if rule.subtype in noise_subtypes:
                    assert rule.probability <= 0.20, (
                        f"{rule.subtype} in {stage} has probability {rule.probability} > 0.20"
                    )
