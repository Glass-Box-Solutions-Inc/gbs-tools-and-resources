"""
Response models for the FastAPI service.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "merus-test-data-generator"
    version: str = "2.0.0"


class RunStatus(BaseModel):
    run_id: int
    status: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    total_cases: int = 0
    total_docs: int = 0
    cases_data_generated: int = 0
    cases_pdfs_generated: int = 0
    docs_pdf_generated: int = 0
    docs_uploaded: int = 0
    errors: int = 0


class GenerateResponse(BaseModel):
    run_id: int
    status: str = "generating"
    message: str = ""


class CasePreview(BaseModel):
    internal_id: str
    case_number: int
    applicant_name: str
    employer_name: str
    litigation_stage: str
    status: str
    total_docs: int
    docs_generated: int = 0


class DocumentPreview(BaseModel):
    filename: str
    subtype: str
    title: str
    doc_date: str
    pdf_generated: bool = False
    pdf_path: Optional[str] = None


class CaseDetail(BaseModel):
    case: CasePreview
    documents: list[DocumentPreview] = []
    timeline: dict[str, Any] = {}


class TaxonomyType(BaseModel):
    value: str
    label: str
    subtype_count: int


class TaxonomySubtype(BaseModel):
    value: str
    label: str
    parent_type: str
