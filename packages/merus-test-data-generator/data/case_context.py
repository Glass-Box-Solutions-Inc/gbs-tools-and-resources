"""
Interdocument coherence — CaseContextAccumulator.

As each document is generated for a case the accumulator collects key
clinical and legal facts so that later documents can reference them:

  • Settlement memos cite the actual QME WPI rating computed earlier
  • Adjuster letters mention specific medical reports that were generated
  • Defense counsel letters reference depositions by witness name/date
  • QME/AME reports list the treating-physician reports they reviewed

Templates opt in by checking doc_spec.context["_accumulator"]. If the
accumulator is absent, templates degrade gracefully with generic language
(see _get_accumulator() helper in BaseTemplate).

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class RecordedDocument:
    """Lightweight summary of a generated document stored in the accumulator."""
    title: str
    doc_date: date
    subtype: str
    # Optional clinical data harvested from medical documents
    wpi_rating: Optional[float] = None
    pd_percentage: Optional[float] = None


class CaseContextAccumulator:
    """Accumulates clinical and documentary facts as a case is generated.

    Pipeline creates one accumulator per case, stores it at
    ``doc_spec.context["_accumulator"]``, and calls ``record_document()``
    immediately after each successful generation call.
    """

    def __init__(self) -> None:
        # Clinical determinations (set by medical templates as they generate)
        self.wpi_rating: Optional[float] = None           # Whole-person impairment %
        self.pd_percentage: Optional[float] = None        # Permanent disability %
        self.mmi_date: Optional[date] = None              # Maximum medical improvement date
        self.settlement_range: Optional[tuple[int, int]] = None  # Low/high estimate ($)

        # All documents generated so far for this case
        self.generated_docs: list[RecordedDocument] = []

    # ------------------------------------------------------------------
    # Write interface (called by pipeline/templates during generation)
    # ------------------------------------------------------------------

    def record_document(
        self,
        title: str,
        doc_date: date,
        subtype: str,
        *,
        wpi_rating: Optional[float] = None,
        pd_percentage: Optional[float] = None,
    ) -> None:
        """Register a successfully generated document.

        Args:
            title: Human-readable document title.
            doc_date: Date on the document.
            subtype: DocumentSubtype value string.
            wpi_rating: If this is a medical-legal report, the WPI it assigns.
            pd_percentage: If this is a medical-legal report, the PD % it assigns.
        """
        rec = RecordedDocument(title=title, doc_date=doc_date, subtype=subtype)
        self.generated_docs.append(rec)

        # Harvest clinical data — last one wins (most recent report is authoritative)
        if wpi_rating is not None:
            self.wpi_rating = wpi_rating
            rec.wpi_rating = wpi_rating
        if pd_percentage is not None:
            self.pd_percentage = pd_percentage
            rec.pd_percentage = pd_percentage

    def set_mmi_date(self, d: date) -> None:
        self.mmi_date = d

    def set_settlement_range(self, low: int, high: int) -> None:
        self.settlement_range = (low, high)

    # ------------------------------------------------------------------
    # Read interface (called by templates to get cross-reference data)
    # ------------------------------------------------------------------

    def get_prior_docs(
        self,
        subtype_prefix: str | None = None,
        limit: int = 5,
    ) -> list[RecordedDocument]:
        """Return previously generated documents, optionally filtered by subtype prefix.

        Args:
            subtype_prefix: If given, only return docs whose subtype starts with this
                            (e.g. "TREATING_PHYSICIAN_REPORT", "QME_", "SUBPOENA").
            limit: Maximum number of results to return.

        Returns:
            Most recent matching documents up to ``limit``, in reverse chronological order.
        """
        docs = self.generated_docs
        if subtype_prefix:
            docs = [d for d in docs if d.subtype.startswith(subtype_prefix)]
        return list(reversed(docs))[:limit]

    def get_cross_reference(self, max_refs: int = 3) -> str:
        """Return a formatted string of prior document references for use in body text.

        Produces language like:
            "This evaluation was conducted after a thorough review of the following
             records: (1) PR-4 Progress Report dated 03/15/2024, (2) MRI Report dated
             01/10/2024."

        Returns empty string if no prior documents have been recorded.
        """
        if not self.generated_docs:
            return ""

        # Take up to max_refs recent records (favour medical reports)
        medical_subtypes = {
            "TREATING_PHYSICIAN_REPORT",
            "DIAGNOSTICS_IMAGING",
            "OPERATIVE_HOSPITAL_RECORDS",
            "DISCHARGE_SUMMARY",
            "QME_REPORT",
            "AME_REPORT",
        }
        candidates = [
            d for d in self.generated_docs
            if any(d.subtype.startswith(pfx) for pfx in medical_subtypes)
        ]
        if not candidates:
            candidates = self.generated_docs

        refs = list(reversed(candidates))[:max_refs]
        if not refs:
            return ""

        parts = []
        for i, ref in enumerate(refs, 1):
            parts.append(f"({i}) {ref.title} dated {ref.doc_date.strftime('%m/%d/%Y')}")

        if len(refs) == 1:
            return f"the following record: {parts[0]}"
        return "the following records: " + ", ".join(parts)

    def get_wpi_narrative(self) -> str:
        """Return a sentence citing the accumulated WPI/PD ratings.

        Returns generic language if no ratings have been recorded yet.
        """
        if self.wpi_rating is not None:
            wpi = self.wpi_rating
            pd = self.pd_percentage
            if pd is not None:
                return (
                    f"The Qualified Medical Evaluator assigned a {wpi:.0f}% whole-person "
                    f"impairment rating, which converts to a {pd:.0f}% permanent disability "
                    f"rating after application of the standard conversion formula."
                )
            return (
                f"The medical-legal evaluation assigned a {wpi:.0f}% whole-person "
                f"impairment rating per the AMA Guides, 5th Edition."
            )
        return (
            "The permanent disability rating has not yet been formally determined "
            "pending completion of the medical-legal evaluation."
        )

    def get_settlement_narrative(self) -> str:
        """Return a sentence about the settlement range, if set."""
        if self.settlement_range:
            lo, hi = self.settlement_range
            return (
                f"Based on the current medical evidence and permanent disability findings, "
                f"the estimated settlement value ranges from ${lo:,} to ${hi:,}."
            )
        return (
            "A settlement valuation will be provided upon completion of the "
            "medical-legal evaluation process."
        )
