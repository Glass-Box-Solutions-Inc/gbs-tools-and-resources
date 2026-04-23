"""
Exporter — converts a ClaimCase into a ZIP archive with manifest.json.

ZIP structure:
    <case_id>/
        manifest.json           # JSON metadata (no pdf_bytes)
        documents/
            <event_id>_<subtype_slug>.pdf  # one PDF per DocumentEvent

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import date
from typing import Any

from claims_generator.models.claim import ClaimCase


class CaseDateEncoder(json.JSONEncoder):
    """JSON encoder handling date objects."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, date):
            return obj.isoformat()
        if isinstance(obj, bytes):
            return ""
        return super().default(obj)


def export_case_to_zip(case: ClaimCase) -> bytes:
    """
    Export a ClaimCase to a ZIP archive containing manifest.json and PDFs.

    Args:
        case: ClaimCase with populated pdf_bytes on each DocumentEvent.

    Returns:
        ZIP file contents as bytes.

    Raises:
        ValueError: If case has no document_events.
    """
    if not case.document_events:
        raise ValueError(f"ClaimCase {case.case_id} has no document_events to export")

    buf = io.BytesIO()
    base = case.case_id

    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        # 1. Write manifest.json (no pdf_bytes)
        manifest = case.model_dump_json_safe()
        manifest_json = json.dumps(manifest, indent=2, cls=CaseDateEncoder)
        zf.writestr(f"{base}/manifest.json", manifest_json)

        # 2. Write individual PDFs
        for event in case.document_events:
            safe_slug = event.subtype_slug.replace("/", "_").replace(" ", "_")
            filename = f"{base}/documents/{event.event_id}_{safe_slug}.pdf"
            pdf_content = event.pdf_bytes if event.pdf_bytes else b""
            zf.writestr(filename, pdf_content)

    return buf.getvalue()


def export_batch_to_zip(cases: list[ClaimCase]) -> bytes:
    """
    Export multiple ClaimCases into a single ZIP archive.

    Each case occupies its own subdirectory: <case_id>/manifest.json and documents/.
    A top-level batch_manifest.json lists all cases.

    Args:
        cases: List of ClaimCase objects.

    Returns:
        ZIP file contents as bytes.
    """
    buf = io.BytesIO()

    batch_summary = [
        {
            "case_id": c.case_id,
            "scenario_slug": c.scenario_slug,
            "seed": c.seed,
            "document_count": len(c.document_events),
            "claimant": (
                f"{c.profile.claimant.first_name} {c.profile.claimant.last_name}"
                if c.profile else "N/A"
            ),
        }
        for c in cases
    ]

    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        # Top-level batch manifest
        zf.writestr(
            "batch_manifest.json",
            json.dumps(batch_summary, indent=2, cls=CaseDateEncoder),
        )

        for case in cases:
            base = case.case_id
            manifest = case.model_dump_json_safe()
            zf.writestr(
                f"{base}/manifest.json",
                json.dumps(manifest, indent=2, cls=CaseDateEncoder),
            )
            for event in case.document_events:
                safe_slug = event.subtype_slug.replace("/", "_").replace(" ", "_")
                filename = f"{base}/documents/{event.event_id}_{safe_slug}.pdf"
                zf.writestr(filename, event.pdf_bytes if event.pdf_bytes else b"")

    return buf.getvalue()
