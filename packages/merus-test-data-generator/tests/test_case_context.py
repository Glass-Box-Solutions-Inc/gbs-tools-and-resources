"""
Tests for Phase 6: CaseContextAccumulator interdocument coherence.

Verifies that the accumulator stores documents, exposes cross-reference
helpers, and propagates WPI/settlement data correctly.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

from datetime import date

import pytest

from data.case_context import CaseContextAccumulator, RecordedDocument


# ---------------------------------------------------------------------------
# Basic accumulation
# ---------------------------------------------------------------------------

class TestRecordDocument:
    """record_document() adds entries to generated_docs."""

    def test_empty_on_init(self):
        acc = CaseContextAccumulator()
        assert acc.generated_docs == []
        assert acc.wpi_rating is None
        assert acc.pd_percentage is None
        assert acc.mmi_date is None
        assert acc.settlement_range is None

    def test_record_single_doc(self):
        acc = CaseContextAccumulator()
        acc.record_document("PR-4 Progress Report", date(2024, 3, 15), "TREATING_PHYSICIAN_REPORT_PR4")
        assert len(acc.generated_docs) == 1
        assert acc.generated_docs[0].title == "PR-4 Progress Report"
        assert acc.generated_docs[0].subtype == "TREATING_PHYSICIAN_REPORT_PR4"

    def test_record_multiple_docs(self):
        acc = CaseContextAccumulator()
        acc.record_document("Doc A", date(2024, 1, 1), "TREATING_PHYSICIAN_REPORT_PR2")
        acc.record_document("Doc B", date(2024, 3, 1), "DIAGNOSTICS_IMAGING")
        acc.record_document("Doc C", date(2024, 6, 1), "QME_REPORT_INITIAL")
        assert len(acc.generated_docs) == 3

    def test_wpi_rating_harvested(self):
        acc = CaseContextAccumulator()
        acc.record_document("QME Report", date(2024, 6, 1), "QME_REPORT_INITIAL", wpi_rating=15.0)
        assert acc.wpi_rating == 15.0
        assert acc.generated_docs[0].wpi_rating == 15.0

    def test_pd_percentage_harvested(self):
        acc = CaseContextAccumulator()
        acc.record_document("QME Report", date(2024, 6, 1), "QME_REPORT_INITIAL",
                            wpi_rating=15.0, pd_percentage=22.5)
        assert acc.pd_percentage == 22.5

    def test_last_wpi_wins(self):
        """Most recent WPI overrides earlier — authoritative report pattern."""
        acc = CaseContextAccumulator()
        acc.record_document("QME Initial", date(2024, 6, 1), "QME_REPORT_INITIAL", wpi_rating=12.0)
        acc.record_document("QME Supplemental", date(2024, 9, 1), "QME_REPORT_SUPPLEMENTAL", wpi_rating=18.0)
        assert acc.wpi_rating == 18.0

    def test_wpi_none_does_not_overwrite(self):
        """record_document without wpi_rating kwarg does not clear existing rating."""
        acc = CaseContextAccumulator()
        acc.record_document("QME Initial", date(2024, 6, 1), "QME_REPORT_INITIAL", wpi_rating=15.0)
        acc.record_document("Adjuster Letter", date(2024, 7, 1), "ADJUSTER_LETTER_INFORMATIONAL")
        assert acc.wpi_rating == 15.0


# ---------------------------------------------------------------------------
# set_mmi_date / set_settlement_range
# ---------------------------------------------------------------------------

class TestSetMethods:
    def test_set_mmi_date(self):
        acc = CaseContextAccumulator()
        d = date(2024, 8, 15)
        acc.set_mmi_date(d)
        assert acc.mmi_date == d

    def test_set_settlement_range(self):
        acc = CaseContextAccumulator()
        acc.set_settlement_range(50000, 120000)
        assert acc.settlement_range == (50000, 120000)


# ---------------------------------------------------------------------------
# get_prior_docs
# ---------------------------------------------------------------------------

class TestGetPriorDocs:
    def _populated_acc(self) -> CaseContextAccumulator:
        acc = CaseContextAccumulator()
        acc.record_document("PR-2 Report", date(2024, 1, 10), "TREATING_PHYSICIAN_REPORT_PR2")
        acc.record_document("MRI Scan", date(2024, 2, 5), "DIAGNOSTICS_IMAGING")
        acc.record_document("PR-4 Report", date(2024, 4, 20), "TREATING_PHYSICIAN_REPORT_PR4")
        acc.record_document("QME Report", date(2024, 7, 1), "QME_REPORT_INITIAL")
        return acc

    def test_returns_all_docs_unfiltered(self):
        acc = self._populated_acc()
        docs = acc.get_prior_docs()
        assert len(docs) == 4

    def test_respects_limit(self):
        acc = self._populated_acc()
        docs = acc.get_prior_docs(limit=2)
        assert len(docs) == 2

    def test_returns_most_recent_first(self):
        acc = self._populated_acc()
        docs = acc.get_prior_docs(limit=2)
        assert docs[0].subtype == "QME_REPORT_INITIAL"
        assert docs[1].subtype == "TREATING_PHYSICIAN_REPORT_PR4"

    def test_subtype_prefix_filter(self):
        acc = self._populated_acc()
        tp_docs = acc.get_prior_docs(subtype_prefix="TREATING_PHYSICIAN_REPORT")
        assert all(d.subtype.startswith("TREATING_PHYSICIAN_REPORT") for d in tp_docs)
        assert len(tp_docs) == 2

    def test_subtype_prefix_no_match(self):
        acc = self._populated_acc()
        docs = acc.get_prior_docs(subtype_prefix="NONEXISTENT_PREFIX")
        assert docs == []

    def test_empty_accumulator_returns_empty(self):
        acc = CaseContextAccumulator()
        assert acc.get_prior_docs() == []


# ---------------------------------------------------------------------------
# get_cross_reference
# ---------------------------------------------------------------------------

class TestGetCrossReference:
    def test_empty_returns_empty_string(self):
        acc = CaseContextAccumulator()
        assert acc.get_cross_reference() == ""

    def test_single_doc_reference(self):
        acc = CaseContextAccumulator()
        acc.record_document("MRI Report", date(2024, 1, 10), "DIAGNOSTICS_IMAGING")
        ref = acc.get_cross_reference()
        assert "MRI Report" in ref
        assert "01/10/2024" in ref

    def test_multiple_docs_numbered(self):
        acc = CaseContextAccumulator()
        acc.record_document("PR-2 Report", date(2024, 1, 10), "TREATING_PHYSICIAN_REPORT_PR2")
        acc.record_document("QME Report", date(2024, 7, 1), "QME_REPORT_INITIAL")
        ref = acc.get_cross_reference()
        assert "(1)" in ref
        assert "(2)" in ref

    def test_prefers_medical_subtypes(self):
        acc = CaseContextAccumulator()
        # Non-medical first
        acc.record_document("Adjuster Letter", date(2024, 1, 1), "ADJUSTER_LETTER_INFORMATIONAL")
        acc.record_document("MRI Report", date(2024, 2, 1), "DIAGNOSTICS_IMAGING")
        acc.record_document("QME Report", date(2024, 7, 1), "QME_REPORT_INITIAL")
        ref = acc.get_cross_reference(max_refs=2)
        # Medical docs should dominate
        assert "Adjuster Letter" not in ref


# ---------------------------------------------------------------------------
# Narrative helpers
# ---------------------------------------------------------------------------

class TestGetWpiNarrative:
    def test_no_wpi_returns_generic(self):
        acc = CaseContextAccumulator()
        narrative = acc.get_wpi_narrative()
        assert "not yet been formally determined" in narrative

    def test_wpi_only(self):
        acc = CaseContextAccumulator()
        acc.record_document("QME", date(2024, 7, 1), "QME_REPORT_INITIAL", wpi_rating=15.0)
        narrative = acc.get_wpi_narrative()
        assert "15%" in narrative
        assert "whole-person" in narrative

    def test_wpi_and_pd(self):
        acc = CaseContextAccumulator()
        acc.record_document("QME", date(2024, 7, 1), "QME_REPORT_INITIAL",
                            wpi_rating=15.0, pd_percentage=22.0)
        narrative = acc.get_wpi_narrative()
        assert "15%" in narrative
        assert "22%" in narrative
        assert "permanent disability" in narrative


class TestGetSettlementNarrative:
    def test_no_range_returns_generic(self):
        acc = CaseContextAccumulator()
        narrative = acc.get_settlement_narrative()
        assert "will be provided" in narrative

    def test_with_range(self):
        acc = CaseContextAccumulator()
        acc.set_settlement_range(50000, 125000)
        narrative = acc.get_settlement_narrative()
        assert "$50,000" in narrative
        assert "$125,000" in narrative
