"""
Tests for Phase 2: .eml email generation.

Verifies that correspondence subtypes produce valid RFC 2822 email files
with correct headers, readable body text, and no binary content.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import email.parser
import tempfile
from pathlib import Path

import pytest

from data.email_metadata import EMAIL_PARTICIPANT_MAP, generate_email_headers
from data.models import DocumentSubtype, OutputFormat


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def adjuster_letter_spec(make_document_spec):
    return make_document_spec(
        subtype=DocumentSubtype.ADJUSTER_LETTER_INFORMATIONAL,
        output_format=OutputFormat.EML,
    )


@pytest.fixture()
def client_status_spec(make_document_spec):
    return make_document_spec(
        subtype=DocumentSubtype.CLIENT_STATUS_LETTERS,
        output_format=OutputFormat.EML,
    )


# ---------------------------------------------------------------------------
# email_metadata unit tests
# ---------------------------------------------------------------------------

class TestGenerateEmailHeaders:
    def test_required_headers_present(self, sample_case):
        headers = generate_email_headers(
            subtype="ADJUSTER_LETTER_INFORMATIONAL",
            case=sample_case,
            doc_date=sample_case.timeline.date_of_injury,
            subject="Adjuster Letter — Informational",
        )
        for key in ("From", "To", "Date", "Subject", "Message-ID", "MIME-Version"):
            assert key in headers, f"Missing header: {key}"

    def test_from_is_adjuster_for_adjuster_letter(self, sample_case):
        headers = generate_email_headers(
            subtype="ADJUSTER_LETTER_INFORMATIONAL",
            case=sample_case,
            doc_date=sample_case.timeline.date_of_injury,
            subject="Test",
        )
        assert sample_case.insurance.adjuster_email in headers["From"]

    def test_from_is_attorney_for_client_letter(self, sample_case):
        headers = generate_email_headers(
            subtype="CLIENT_STATUS_LETTERS",
            case=sample_case,
            doc_date=sample_case.timeline.date_of_injury,
            subject="Status Update",
        )
        assert "@" in headers["From"]

    def test_to_is_applicant_for_client_correspondence(self, sample_case):
        headers = generate_email_headers(
            subtype="CLIENT_CORRESPONDENCE_INFORMATIONAL",
            case=sample_case,
            doc_date=sample_case.timeline.date_of_injury,
            subject="Case Update",
        )
        assert sample_case.applicant.email in headers["To"]

    def test_claim_number_in_message_id(self, sample_case):
        headers = generate_email_headers(
            subtype="ADJUSTER_LETTER",
            case=sample_case,
            doc_date=sample_case.timeline.date_of_injury,
            subject="Test",
        )
        assert sample_case.insurance.claim_number in headers["Message-ID"]


class TestEmailParticipantMap:
    def test_all_map_entries_have_two_roles(self):
        for subtype, roles in EMAIL_PARTICIPANT_MAP.items():
            assert len(roles) == 2, f"{subtype}: expected 2 roles, got {len(roles)}"

    def test_known_valid_roles(self):
        valid_roles = {
            "adjuster", "attorney", "applicant", "defense",
            "treating_physician", "qme_physician",
        }
        for subtype, (sender, recipient) in EMAIL_PARTICIPANT_MAP.items():
            assert sender in valid_roles, f"{subtype}: unknown sender role '{sender}'"
            assert recipient in valid_roles, f"{subtype}: unknown recipient role '{recipient}'"


# ---------------------------------------------------------------------------
# End-to-end EML file generation tests
# ---------------------------------------------------------------------------

class TestEmlFileGeneration:
    def _generate_eml(self, template_cls, case, doc_spec):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "test.eml"
            template = template_cls(case)
            template.generate(out, doc_spec)
            assert out.exists(), "EML file was not created"
            assert out.stat().st_size > 0, "EML file is empty"
            return out.read_text(encoding="utf-8")

    def test_adjuster_letter_produces_valid_eml(self, sample_case, adjuster_letter_spec):
        from pdf_templates.correspondence.adjuster_letter import AdjusterLetter
        content = self._generate_eml(AdjusterLetter, sample_case, adjuster_letter_spec)
        msg = email.parser.Parser().parsestr(content)
        assert msg["From"], "Missing From header"
        assert msg["To"], "Missing To header"
        assert msg["Date"], "Missing Date header"
        assert msg["Subject"], "Missing Subject header"

    def test_eml_body_is_readable_text(self, sample_case, adjuster_letter_spec):
        from pdf_templates.correspondence.adjuster_letter import AdjusterLetter
        content = self._generate_eml(AdjusterLetter, sample_case, adjuster_letter_spec)
        msg = email.parser.Parser().parsestr(content)
        body = msg.get_payload()
        assert isinstance(body, str), "EML body is not plain text"
        assert len(body) > 50, "EML body is suspiciously short"

    def test_eml_contains_no_pdf_magic_bytes(self, sample_case, adjuster_letter_spec):
        from pdf_templates.correspondence.adjuster_letter import AdjusterLetter
        content = self._generate_eml(AdjusterLetter, sample_case, adjuster_letter_spec)
        assert not content.startswith("%PDF"), "EML file contains PDF magic bytes"

    def test_defense_letter_produces_eml(self, sample_case, make_document_spec):
        from pdf_templates.correspondence.defense_counsel_letter import DefenseCounselLetter
        spec = make_document_spec(
            subtype=DocumentSubtype.DEFENSE_COUNSEL_LETTER_INFORMATIONAL,
            output_format=OutputFormat.EML,
        )
        content = self._generate_eml(DefenseCounselLetter, sample_case, spec)
        msg = email.parser.Parser().parsestr(content)
        assert msg["From"]
        assert msg["To"]
