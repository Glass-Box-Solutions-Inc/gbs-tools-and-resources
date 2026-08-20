"""AJC-64 item 0b — the rating lane can now prove what it already got right.

The audit's headline is that **the tables are clean** — an independent re-parse
matched FEC 800/800, impairment 215/215, occupational 808/808, age 1,000/1,000
and Section 4 5,085/5,085 — **but the repo could not prove it** (M5-R42). Three
defects, all of the same family:

* **(a) the pin chain compared a constant to itself.** `rating_sources.py`
  checked `PDRS_2005_PDF_SHA256` against `meta.json`'s copy of the same
  constant, which passes against a fabricated PDF exactly as well as against the
  real one. The chain now terminates in bytes on disk;
* **(b) four of five tables had tautological oracles, and the fifth had none.**
  `test_rating_coherence.py:216` compared the vendored JSON to production
  lookups that read the same JSON. Every table now has a genuine
  artifact-to-source oracle: cells parsed out of the pinned extracted text by
  `tests/pdrs_reparse.py` — an independently written parser, anchored on printed
  headings rather than on the audit script's hand-tuned line slices — and
  asserted cell for cell, with the **counts pinned as literals** so a parser
  that finds nothing fails rather than agreeing with an empty intersection;
* **(c) the post-2013 x1.4 branch had no citation.** `grep 4660` returned
  nothing in `rating.py` or `rating_sources.py`.

Per-table mutants rather than one shared mutant, because a shared one would
prove only that *some* table has a live oracle.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import ast
import hashlib
import json
import sys
import tempfile
from pathlib import Path

import pytest

import pdrs_reparse
from pdrs_reparse import EXPECTED_CELL_COUNTS
from wc_caseload_engine import rating, rating_sources

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import pdrs_extract

from wc_caseload_engine.rating_sources import (
    PDRS_2005_EXTRACTED_TEXT_SHA256,
    PDRS_2005_PDF_SHA256,
    PDRS_VENDORED_ARTIFACTS,
    pdrs_data_dir,
    verify_pdrs_artifact,
    verify_pdrs_pdf,
)


def _shipped_tables() -> dict[str, object]:
    return json.loads((pdrs_data_dir() / "pdrs_2005_tables.json").read_text("utf-8"))


def _shipped_section4() -> dict[str, dict[str, str]]:
    return json.loads(
        (pdrs_data_dir() / "pdrs_2005_section4_matrix.json").read_text("utf-8")
    )


class TestPinTerminatesInBytes:
    """(a) The chain ends at a file, not at another copy of a string."""

    @pytest.mark.parametrize("filename", sorted(PDRS_VENDORED_ARTIFACTS))
    def test_each_vendored_artifact_hashes_to_its_pin(self, filename: str) -> None:
        digest = verify_pdrs_artifact(filename)
        assert digest == PDRS_VENDORED_ARTIFACTS[filename]
        # Computed from the file, not read from the constant: asserted by
        # recomputing here from bytes this test opened itself.
        payload = (pdrs_data_dir() / filename).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == digest

    def test_every_artifact_the_oracles_read_is_pinned(self) -> None:
        """m24-204 — completeness, which the parametrized check cannot give.

        The per-artifact check above is parametrized *over* the pin set, so
        dropping an entry deletes the case that would have caught it: the guard
        and the thing guarded are the same list. That is the shape of the round-1
        defect one layer up — a chain checked against its own copy.

        So this asserts membership from the other end. The five per-table parity
        oracles parse the extracted text; ``pdrs_reparse`` names the file it
        opens, and every file any oracle opens out of the data directory must
        carry a pin. An unpinned artifact means the tables are compared
        cell-for-cell against a source nothing vouches for.
        """
        # ``pdrs_reparse`` is a rootdir module, imported at the top of this
        # file. It must NOT be reached as ``tests.pdrs_reparse``: the substrate
        # root is appended to ``sys.path``, and it ships its own ``tests``
        # package, so that spelling resolves to the substrate's and fails.
        read_by_oracles = {
            pdrs_reparse.extracted_text_path().name,
            "pdrs-2005-source.pdf",
        }
        unpinned = read_by_oracles - set(PDRS_VENDORED_ARTIFACTS)
        assert not unpinned, (
            f"artifacts read by the parity oracles but carrying no digest pin: "
            f"{sorted(unpinned)} — the provenance chain terminates one hop short "
            "of where the evidence is actually read"
        )

    def test_a_corrupted_artifact_fails_closed(self, tmp_path: Path) -> None:
        """m24-31: the self-comparison would pass this fixture happily."""
        forged = tmp_path / "forged.pdf"
        forged.write_bytes(b"not the schedule")
        with pytest.raises(ValueError, match="M5_PDRS_ARTIFACT_DIGEST_MISMATCH"):
            verify_pdrs_pdf(forged)

    def test_an_absent_artifact_is_reported_not_passed(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="M5_PDRS_ARTIFACT_PIN_MISSING"):
            verify_pdrs_pdf(tmp_path / "nothing.pdf")

    def test_the_source_pdf_is_in_tree_and_hashes_to_its_pin(self) -> None:
        """MANDATORY — no environment-dependent skip (round-1 finding F5).

        Round 1 pointed this at the documentation repository and skipped when it
        was absent. A skip is indistinguishable from a pass in a summary, so the
        strongest link in the chain was the one least likely to be exercised.
        The PDF is vendored now, so the check simply runs.
        """
        path = pdrs_data_dir() / "pdrs-2005-source.pdf"
        assert path.is_file(), (
            "the PDRS source PDF must be vendored in-tree; the provenance chain "
            "may not depend on a neighbouring checkout"
        )
        assert path.stat().st_size == 4_005_811
        assert verify_pdrs_pdf(path) == PDRS_2005_PDF_SHA256
        assert verify_pdrs_artifact("pdrs-2005-source.pdf") == PDRS_2005_PDF_SHA256

    def test_the_derivation_script_is_committed_and_pins_both_ends(self) -> None:
        """The derivation is executable and reproducible, not a claim in prose."""
        assert pdrs_extract.SOURCE_PDF.is_file()
        assert pdrs_extract.EXTRACTED_TEXT.is_file()
        assert pdrs_extract.SOURCE_PDF_SHA256 == PDRS_2005_PDF_SHA256
        assert pdrs_extract.EXTRACTED_TEXT_SHA256 == PDRS_2005_EXTRACTED_TEXT_SHA256
        # The arguments are part of the contract: the default reading-order mode
        # collapses the columns the parity oracles read positions out of.
        assert pdrs_extract.PDFTOTEXT_ARGS == ("-layout",)
        assert pdrs_extract.VERIFIED_POPPLER_VERSION == "22.02.0"
        assert pdrs_extract.sha256_of(pdrs_extract.SOURCE_PDF) == PDRS_2005_PDF_SHA256
        assert (
            pdrs_extract.sha256_of(pdrs_extract.EXTRACTED_TEXT)
            == PDRS_2005_EXTRACTED_TEXT_SHA256
        )

    def test_the_derivation_actually_reproduces_the_pinned_text(self) -> None:
        """Re-run the derivation and compare — the reproducibility claim itself.

        Skipped only when poppler is absent from the image, and that skip is
        about the TOOL rather than about the artifacts: every pin above is still
        asserted unconditionally, so an absent poppler cannot hide a bad digest.
        """
        version = pdrs_extract.pdftotext_version()
        if not version:
            pytest.skip("pdftotext (poppler-utils) is not installed on this host")
        with tempfile.TemporaryDirectory() as directory:
            derived = Path(directory) / "derived.txt"
            digest = pdrs_extract.derive(derived)
        assert digest == PDRS_2005_EXTRACTED_TEXT_SHA256, (
            f"pdftotext {version} did not reproduce the pinned extraction "
            f"(verified under {pdrs_extract.VERIFIED_POPPLER_VERSION})"
        )

    def test_the_extracted_text_is_the_artifact_the_oracles_parse(self) -> None:
        """The pinned bytes and the evidence source are the SAME bytes.

        The five parity oracles below parse this file. If the pin named one
        artifact and the oracles read another, the pin would be evidence about
        something nothing in the suite consumes.
        """
        path = pdrs_reparse.extracted_text_path()
        assert path.is_file()
        assert (
            hashlib.sha256(path.read_bytes()).hexdigest()
            == PDRS_2005_EXTRACTED_TEXT_SHA256
        )
        # Hashed again through the accessor the oracles actually call, so a
        # future accessor reading some other file cannot go unnoticed.
        assert (
            hashlib.sha256(pdrs_reparse.extracted_text().encode("utf-8")).hexdigest()
            == PDRS_2005_EXTRACTED_TEXT_SHA256
        )


class TestPerTableParity:
    """(b) Five genuine artifact-to-source oracles, one mutant each."""

    def test_the_fec_table_matches_the_source_cell_for_cell(self) -> None:
        """m24-30."""
        parsed = pdrs_reparse.parse_fec()
        assert len(parsed) == EXPECTED_CELL_COUNTS["fec"] == 800
        shipped = dict(_shipped_tables()["fec"])
        assert parsed == shipped

    def test_the_impairment_register_matches_the_source(self) -> None:
        """m24-45."""
        parsed = pdrs_reparse.parse_impairment()
        assert len(parsed) == EXPECTED_CELL_COUNTS["imp"] == 215
        shipped = {
            key: list(value) for key, value in _shipped_tables()["imp"].items()
        }
        assert parsed == shipped

    def test_the_occupational_table_matches_the_source(self) -> None:
        """m24-46."""
        parsed = pdrs_reparse.parse_occupational()
        cells = sum(len(row) for row in parsed.values())
        assert cells == EXPECTED_CELL_COUNTS["occ"] == 808
        shipped = {
            key: list(value) for key, value in _shipped_tables()["occ"].items()
        }
        assert parsed == shipped

    def test_the_age_table_matches_the_source(self) -> None:
        """m24-48."""
        parsed = pdrs_reparse.parse_age()
        cells = sum(len(row) for row in parsed.values())
        assert cells == EXPECTED_CELL_COUNTS["age"] == 1_000
        shipped = {
            key: list(value) for key, value in _shipped_tables()["age"].items()
        }
        assert parsed == shipped

    def test_the_section4_matrix_matches_the_source(self) -> None:
        """m24-47."""
        groups = tuple(_shipped_tables()["groups"])
        parsed = pdrs_reparse.parse_section4(groups)
        cells = sum(len(row) for row in parsed.values())
        assert len(parsed) == 113
        assert cells == EXPECTED_CELL_COUNTS["section4"] == 5_085
        assert parsed == _shipped_section4()

    def test_the_counts_are_pinned_so_an_empty_parse_fails(self) -> None:
        """A parser finding nothing must FAIL, not agree with nothing."""
        assert EXPECTED_CELL_COUNTS == {
            "fec": 800,
            "imp": 215,
            "occ": 808,
            "age": 1_000,
            "section4": 5_085,
        }

    def test_the_reparse_anchors_on_headings_not_line_numbers(self) -> None:
        """The independence claim, checked rather than asserted in prose.

        The audit script sliced `L[2910:2990]` and friends. A "second" parser
        carrying the same hand-tuned offsets is the first one wearing a
        different name, and it would agree with a JSON produced from those very
        offsets no matter what the source said.
        """
        source = Path(pdrs_reparse.__file__).read_text(encoding="utf-8")
        assert "_region(" in source
        # Checked on the syntax tree, not the file text: the module's own
        # docstring quotes `L[2910:2990]` to explain what it refuses to do, and
        # a substring scan cannot tell an explanation from an offset.
        offenders = [
            ast.unparse(node)
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Subscript)
            and isinstance(node.slice, ast.Slice)
            and any(
                isinstance(bound, ast.Constant) and isinstance(bound.value, int)
                and bound.value > 100
                for bound in (node.slice.lower, node.slice.upper)
                if bound is not None
            )
        ]
        assert offenders == [], (
            f"the re-parse slices the text by hand-tuned offset: {offenders}"
        )

    def test_the_section4_label_exception_is_closed_and_justified(self) -> None:
        """One named source discrepancy, not a widened pattern.

        The source prints `17.01.02.XX` on one column-half page and
        `17.01.02.00` on the other for a single logical row. Recorded as one
        entry rather than absorbed into the label regex — a pattern relaxed
        until the join succeeds is the failure mode M5-R47b names one layer up.
        """
        assert pdrs_reparse.SECTION4_SOURCE_LABEL_VARIANTS == {
            "17.01.02.00": "17.01.02.XX"
        }


class TestDfecCitation:
    """(c) The one legal proposition this function embodies names its source."""

    def test_the_citation_is_present(self) -> None:
        """m24-39: stripping it reddens here, so the attribution cannot rot."""
        doc = rating.dfec_adjusted_rating.__doc__ or ""
        for fragment in (
            "4660.1(b)",
            "SI-W2-001",
            "SI-W2-003",
            "LEGAL_BINDING",
            "ENGINE_POLICY",
        ):
            assert fragment in doc, f"{fragment!r} is missing from the citation"

    def test_the_citation_changed_no_behaviour(self) -> None:
        """Provenance only. The arithmetic is asserted against literals."""
        assert rating.dfec_adjusted_rating(0) == 0
        assert rating.dfec_adjusted_rating(1) == 1
        assert rating.dfec_adjusted_rating(5) == 7
        assert rating.dfec_adjusted_rating(50) == 70
        assert rating.dfec_adjusted_rating(71) == 99
        assert rating.dfec_adjusted_rating(72) == 100
        assert rating.dfec_adjusted_rating(100) == 100

    def test_the_module_now_names_the_section_it_relies_on(self) -> None:
        """`grep 4660` returned nothing across both modules before this item."""
        found = [
            module.__name__
            for module in (rating, rating_sources)
            if "4660" in Path(module.__file__).read_text(encoding="utf-8")
        ]
        assert "wc_caseload_engine.rating" in found
