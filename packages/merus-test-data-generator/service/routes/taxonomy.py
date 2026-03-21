"""Taxonomy API routes — 12 types + 188 subtypes."""

from fastapi import APIRouter

from data.taxonomy import (
    DOCUMENT_SUBTYPE_LABELS,
    DOCUMENT_TYPE_LABELS,
    DOCUMENT_TYPE_TO_SUBTYPES,
    DocumentSubtype,
    DocumentType,
    get_subtypes_for_type,
)
from service.models.responses import TaxonomySubtype, TaxonomyType

router = APIRouter(prefix="/api/taxonomy", tags=["taxonomy"])


@router.get("/types", response_model=list[TaxonomyType])
async def get_types():
    """Return all 12 parent document types."""
    return [
        TaxonomyType(
            value=t.value,
            label=DOCUMENT_TYPE_LABELS.get(t.value, t.value),
            subtype_count=len(DOCUMENT_TYPE_TO_SUBTYPES.get(t.value, [])),
        )
        for t in DocumentType
    ]


@router.get("/subtypes", response_model=list[TaxonomySubtype])
async def get_subtypes():
    """Return all 188 document subtypes with labels and parent types."""
    from data.taxonomy import SUBTYPE_TO_TYPE
    return [
        TaxonomySubtype(
            value=s.value,
            label=DOCUMENT_SUBTYPE_LABELS.get(s.value, s.value),
            parent_type=SUBTYPE_TO_TYPE.get(s.value, "UNKNOWN"),
        )
        for s in DocumentSubtype
    ]


@router.get("/subtypes/{doc_type}", response_model=list[TaxonomySubtype])
async def get_subtypes_for_parent(doc_type: str):
    """Return subtypes for one parent type."""
    from data.taxonomy import SUBTYPE_TO_TYPE
    subtypes = get_subtypes_for_type(doc_type)
    return [
        TaxonomySubtype(
            value=s,
            label=DOCUMENT_SUBTYPE_LABELS.get(s, s),
            parent_type=doc_type,
        )
        for s in subtypes
    ]
