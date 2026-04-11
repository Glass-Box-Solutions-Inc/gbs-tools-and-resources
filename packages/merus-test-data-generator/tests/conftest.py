"""
Shared pytest fixtures for the merus-test-data-generator test suite.

Taxonomy: 15 types / 350 subtypes.
"""

from __future__ import annotations

import sys
import os

# Add the package root to sys.path so all imports resolve correctly.
_PACKAGE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PACKAGE_ROOT not in sys.path:
    sys.path.insert(0, _PACKAGE_ROOT)

import pytest

from data.fake_data_generator import FakeDataGenerator
from data.lifecycle_engine import CaseParameters
from data.models import DocumentSpec, DocumentSubtype, OutputFormat
from data.taxonomy import DocumentSubtype  # noqa: F811


@pytest.fixture(scope="session")
def fake_gen() -> FakeDataGenerator:
    """A seeded FakeDataGenerator instance shared across the session."""
    return FakeDataGenerator(seed=42)


@pytest.fixture(scope="session")
def all_subtypes() -> list[str]:
    """All DocumentSubtype enum values as strings."""
    return [s.value for s in DocumentSubtype]


@pytest.fixture(scope="session")
def sample_case():
    """A realistic GeneratedCase for template rendering tests."""
    gen = FakeDataGenerator(seed=123)
    params = CaseParameters(
        target_stage="settlement",
        injury_type="specific",
        body_part_category="spine",
        num_body_parts=2,
        has_surgery=False,
        has_attorney=True,
        has_psych_component=False,
        complexity="standard",
    )
    return gen.generate_case_from_params(case_number=1, params=params)


@pytest.fixture()
def make_document_spec(sample_case):
    """Factory that creates a DocumentSpec from a sample case.

    Usage:
        spec = make_document_spec(
            subtype=DocumentSubtype.ADJUSTER_LETTER_INFORMATIONAL,
            output_format=OutputFormat.EML,
        )
    """
    from datetime import date

    def _factory(
        subtype: DocumentSubtype = DocumentSubtype.PROOF_OF_SERVICE,
        output_format: OutputFormat = OutputFormat.PDF,
        title: str | None = None,
        doc_date: date | None = None,
        template_class: str | None = None,
    ) -> DocumentSpec:
        from pdf_templates.registry import get_template_for_subtype
        tc = template_class or get_template_for_subtype(subtype.value)[0]
        return DocumentSpec(
            subtype=subtype,
            title=title or subtype.value.replace("_", " ").title(),
            doc_date=doc_date or sample_case.timeline.date_of_injury,
            template_class=tc,
            output_format=output_format,
        )

    return _factory
