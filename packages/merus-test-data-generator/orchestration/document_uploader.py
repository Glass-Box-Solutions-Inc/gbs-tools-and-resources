"""
Wraps MerusCaseAPIClient for document uploads to MerusCase.
Handles rate limiting, retries, and progress tracking.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

import structlog

from config import (
    MERUS_EXPERT_PATH,
    MERUSCASE_ACCESS_TOKEN,
    MERUSCASE_CLIENT_ID,
    MERUSCASE_CLIENT_SECRET,
    UPLOAD_BACKOFF_BASE,
    UPLOAD_DELAY_SECONDS,
    UPLOAD_MAX_RETRIES,
)
from orchestration.audit import PipelineAuditLogger
from orchestration.progress_tracker import ProgressTracker

sys.path.insert(0, str(MERUS_EXPERT_PATH))

logger = structlog.get_logger()


class DocumentUploader:
    def __init__(self, tracker: ProgressTracker, audit: PipelineAuditLogger | None = None):
        self.tracker = tracker
        self.audit = audit
        self._client = None

    async def _get_client(self):
        if self._client is None:
            from meruscase_api.client import MerusCaseAPIClient
            if not MERUSCASE_ACCESS_TOKEN:
                raise RuntimeError(
                    "No MerusCase access token found. Set MERUSCASE_ACCESS_TOKEN env var "
                    "or place token in merus-expert/.meruscase_token"
                )
            self._client = MerusCaseAPIClient(
                client_id=MERUSCASE_CLIENT_ID,
                client_secret=MERUSCASE_CLIENT_SECRET,
                access_token=MERUSCASE_ACCESS_TOKEN,
            )
        return self._client

    async def upload_document(
        self,
        case_internal_id: str,
        meruscase_id: int,
        pdf_path: str,
        filename: str,
        title: str,
    ) -> bool:
        """Upload a single document. Returns True on success."""
        from meruscase_api.models import Document

        client = await self._get_client()

        doc = Document(
            case_file_id=meruscase_id,
            filename=filename,
            file_path=pdf_path,
            description=title,
        )

        for attempt in range(1, UPLOAD_MAX_RETRIES + 1):
            try:
                result = await client.upload_document(doc)

                if result.success:
                    doc_id = result.data.get("document_id", 0) if isinstance(result.data, dict) else 0
                    self.tracker.mark_doc_uploaded(case_internal_id, filename, doc_id)
                    if self.audit:
                        self.audit.log_document_uploaded(case_internal_id, filename, success=True, doc_id=doc_id)
                    logger.debug(
                        "doc_uploaded",
                        case=case_internal_id,
                        filename=filename,
                    )
                    return True

                logger.warning(
                    "upload_failed",
                    case=case_internal_id,
                    filename=filename,
                    error=result.error,
                    attempt=attempt,
                )

            except Exception as e:
                error_str = str(e)
                logger.error(
                    "upload_error",
                    case=case_internal_id,
                    filename=filename,
                    error=error_str,
                    attempt=attempt,
                )

                # Rate limit handling
                if "429" in error_str or "rate" in error_str.lower():
                    wait = UPLOAD_BACKOFF_BASE ** attempt
                    logger.info("rate_limited", wait_seconds=wait)
                    await asyncio.sleep(wait)
                    continue

            if attempt < UPLOAD_MAX_RETRIES:
                wait = UPLOAD_BACKOFF_BASE ** attempt
                await asyncio.sleep(wait)

        self.tracker.mark_doc_error(case_internal_id, filename, "Upload failed after retries")
        if self.audit:
            self.audit.log_document_uploaded(case_internal_id, filename, success=False)
        return False

    async def upload_case_documents(
        self,
        case_internal_id: str,
        meruscase_id: int,
    ) -> dict[str, int]:
        """Upload all pending documents for a case. Returns counts."""
        docs = self.tracker.get_unuploaded_docs(case_internal_id)
        uploaded = 0
        failed = 0

        for doc in docs:
            success = await self.upload_document(
                case_internal_id=case_internal_id,
                meruscase_id=meruscase_id,
                pdf_path=doc["pdf_path"],
                filename=doc["filename"],
                title=doc["title"],
            )
            if success:
                uploaded += 1
            else:
                failed += 1

            await asyncio.sleep(UPLOAD_DELAY_SECONDS)

        if uploaded > 0:
            total_uploaded = len(self.tracker.get_docs_for_case(case_internal_id)) - len(
                self.tracker.get_unuploaded_docs(case_internal_id)
            )
            self.tracker.mark_case_uploaded(case_internal_id, total_uploaded)

        return {"uploaded": uploaded, "failed": failed}

    async def upload_all(self) -> dict[str, Any]:
        """Upload documents for all cases that need it. Returns summary."""
        cases = self.tracker.get_cases_needing_upload()
        total_uploaded = 0
        total_failed = 0

        for case_row in cases:
            logger.info(
                "uploading_case_docs",
                case=case_row["internal_id"],
                meruscase_id=case_row["meruscase_id"],
            )
            result = await self.upload_case_documents(
                case_internal_id=case_row["internal_id"],
                meruscase_id=case_row["meruscase_id"],
            )
            total_uploaded += result["uploaded"]
            total_failed += result["failed"]

        return {
            "cases_processed": len(cases),
            "docs_uploaded": total_uploaded,
            "docs_failed": total_failed,
        }
