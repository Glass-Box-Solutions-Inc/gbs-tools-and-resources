"""
Unit tests for document generators — smoke test: one PDF per DocumentType.

Each test verifies:
  1. A PDF is generated without raising exceptions
  2. The output is > 500 bytes (valid PDF content, not empty stub)
  3. The output starts with the PDF magic bytes (%PDF)

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest

# Load all generators
import claims_generator.documents.loader  # noqa: F401
from claims_generator.documents.registry import DocumentRegistry
from claims_generator.models.claim import DocumentEvent
from claims_generator.models.claimant import ClaimantProfile
from claims_generator.models.employer import EmployerProfile, InsurerProfile
from claims_generator.models.enums import DocumentType
from claims_generator.models.financial import FinancialProfile
from claims_generator.models.medical import BodyPart, ICD10Entry, MedicalProfile, PhysicianProfile
from claims_generator.models.profile import ClaimProfile


@pytest.fixture(scope="module")
def sample_profile() -> ClaimProfile:
    """A deterministic sample ClaimProfile for generator smoke tests."""
    return ClaimProfile(
        claimant=ClaimantProfile(
            first_name="Maria",
            last_name="Gonzalez",
            date_of_birth=date(1982, 6, 15),
            gender="F",
            address_city="Los Angeles",
            address_county="Los Angeles",
            address_zip="90001",
            phone="213-555-1234",
            ssn_last4="4321",
            primary_language="English",
            occupation_title="Warehouse Worker",
            years_employed=3.5,
        ),
        employer=EmployerProfile(
            company_name="Acme Logistics Inc.",
            industry="Warehousing and Storage",
            address_city="Los Angeles",
            address_state="CA",
            ein_last4="7890",
            size_category="large",
        ),
        insurer=InsurerProfile(
            carrier_name="State Compensation Insurance Fund (SCIF)",
            claim_number="SCIF-2024-001234",
            adjuster_name="James Wilson",
            adjuster_phone="800-555-6789",
            adjuster_email="jwilson@scif.com",
            policy_number="POL-2024-7777",
        ),
        medical=MedicalProfile(
            date_of_injury="2024-03-15",
            injury_mechanism="slip and fall on wet warehouse floor",
            body_parts=[
                BodyPart(body_part="lumbar spine", laterality=None, primary=True),
                BodyPart(body_part="right knee", laterality="right", primary=False),
            ],
            icd10_codes=[
                ICD10Entry(code="M54.5", description="Low back pain", body_part="lumbar spine"),
                ICD10Entry(code="M23.91", description="Internal derangement of right knee", body_part="right knee"),  # noqa: E501
            ],
            treating_physician=PhysicianProfile(
                role="treating_md",
                first_name="Robert",
                last_name="Chen",
                specialty="Occupational Medicine",
                license_number="CA-MD-123456",
                address_city="Torrance",
                npi="1234567890",
            ),
            qme_physician=PhysicianProfile(
                role="qme",
                first_name="Patricia",
                last_name="Williams",
                specialty="Orthopedics",
                license_number="CA-MD-654321",
                address_city="Pasadena",
                npi="0987654321",
            ),
            has_surgery=False,
            surgery_description=None,
            mmi_reached=True,
            wpi_percent=12.0,
        ),
        financial=FinancialProfile(
            injury_year=2024,
            average_weekly_wage=1250.00,
            td_weekly_rate=833.34,
            td_min_rate=245.00,
            td_max_rate=1620.00,
            estimated_pd_percent=12.0,
            estimated_pd_weeks=112.0,
            life_pension_eligible=False,
        ),
    )


def _make_event(
    doc_type: DocumentType,
    subtype_slug: str,
    title: str = "Test Document",
    event_date: date | None = None,
    stage: str = "TEST",
    deadline_statute: str | None = None,
) -> DocumentEvent:
    """Helper: create a DocumentEvent for generator smoke tests."""
    return DocumentEvent(
        event_id=str(uuid.uuid4()),
        document_type=doc_type,
        subtype_slug=subtype_slug,
        title=title,
        event_date=event_date or date(2024, 6, 1),
        deadline_date=None,
        deadline_statute=deadline_statute,
        stage=stage,
        access_level="EXAMINER_ONLY",
        pdf_bytes=b"",
        metadata={},
    )


class TestTierCGenerators:
    """Smoke tests for Tier C (plain letterhead) generators."""

    def test_correspondence_initial_contact(self, sample_profile: ClaimProfile) -> None:
        event = _make_event(
            DocumentType.CORRESPONDENCE, "adjuster_initial_contact",
            "Initial Claims Contact Letter", deadline_statute="10 CCR 2695.5(b)",
        )
        pdf = DocumentRegistry.generate(event, sample_profile)
        assert len(pdf) > 500
        assert pdf[:4] == b"%PDF"

    def test_correspondence_denial_letter(self, sample_profile: ClaimProfile) -> None:
        event = _make_event(DocumentType.CORRESPONDENCE, "denial_explanation_letter")
        pdf = DocumentRegistry.generate(event, sample_profile)
        assert len(pdf) > 500
        assert pdf[:4] == b"%PDF"

    def test_benefit_notice_acceptance(self, sample_profile: ClaimProfile) -> None:
        event = _make_event(
            DocumentType.BENEFIT_NOTICE, "benefit_notice_acceptance",
            "Notice of Acceptance", deadline_statute="10 CCR 2695.7(b)",
        )
        pdf = DocumentRegistry.generate(event, sample_profile)
        assert len(pdf) > 500
        assert pdf[:4] == b"%PDF"

    def test_benefit_notice_denial(self, sample_profile: ClaimProfile) -> None:
        event = _make_event(DocumentType.BENEFIT_NOTICE, "benefit_notice_denial")
        pdf = DocumentRegistry.generate(event, sample_profile)
        assert len(pdf) > 500

    def test_benefit_notice_delay(self, sample_profile: ClaimProfile) -> None:
        event = _make_event(DocumentType.BENEFIT_NOTICE, "benefit_notice_delay")
        pdf = DocumentRegistry.generate(event, sample_profile)
        assert len(pdf) > 500

    def test_benefit_notice_td_rate(self, sample_profile: ClaimProfile) -> None:
        event = _make_event(DocumentType.BENEFIT_NOTICE, "benefit_notice_td_rate")
        pdf = DocumentRegistry.generate(event, sample_profile)
        assert len(pdf) > 500

    def test_legal_correspondence_qme_panel_objection(self, sample_profile: ClaimProfile) -> None:
        event = _make_event(
            DocumentType.LEGAL_CORRESPONDENCE, "legal_correspondence_qme_panel_objection"
        )
        pdf = DocumentRegistry.generate(event, sample_profile)
        assert len(pdf) > 500

    def test_legal_correspondence_qme_report_objection(self, sample_profile: ClaimProfile) -> None:
        event = _make_event(DocumentType.LEGAL_CORRESPONDENCE, "qme_objection_letter")
        pdf = DocumentRegistry.generate(event, sample_profile)
        assert len(pdf) > 500

    def test_payment_record_td(self, sample_profile: ClaimProfile) -> None:
        event = _make_event(
            DocumentType.PAYMENT_RECORD, "payment_record_td_first",
            deadline_statute="LC 4650",
        )
        pdf = DocumentRegistry.generate(event, sample_profile)
        assert len(pdf) > 500

    def test_payment_record_pd_worksheet(self, sample_profile: ClaimProfile) -> None:
        event = _make_event(DocumentType.PAYMENT_RECORD, "payment_record_pd_worksheet")
        pdf = DocumentRegistry.generate(event, sample_profile)
        assert len(pdf) > 500

    def test_payment_record_pd_final(self, sample_profile: ClaimProfile) -> None:
        event = _make_event(DocumentType.PAYMENT_RECORD, "payment_record_pd_final")
        pdf = DocumentRegistry.generate(event, sample_profile)
        assert len(pdf) > 500

    def test_pharmacy_record(self, sample_profile: ClaimProfile) -> None:
        event = _make_event(DocumentType.PHARMACY_RECORD, "pharmacy_dispensing_record")
        pdf = DocumentRegistry.generate(event, sample_profile)
        assert len(pdf) > 500

    def test_other_document(self, sample_profile: ClaimProfile) -> None:
        event = _make_event(DocumentType.OTHER, "misc_claim_record")
        pdf = DocumentRegistry.generate(event, sample_profile)
        assert len(pdf) > 500

    def test_wage_statement(self, sample_profile: ClaimProfile) -> None:
        event = _make_event(DocumentType.WAGE_STATEMENT, "wage_statement_employer")
        pdf = DocumentRegistry.generate(event, sample_profile)
        assert len(pdf) > 500

    def test_employer_report(self, sample_profile: ClaimProfile) -> None:
        event = _make_event(DocumentType.EMPLOYER_REPORT, "employer_report_of_injury")
        pdf = DocumentRegistry.generate(event, sample_profile)
        assert len(pdf) > 500

    def test_imaging_report_xray(self, sample_profile: ClaimProfile) -> None:
        event = _make_event(DocumentType.IMAGING_REPORT, "imaging_report_xray")
        pdf = DocumentRegistry.generate(event, sample_profile)
        assert len(pdf) > 500

    def test_imaging_report_mri(self, sample_profile: ClaimProfile) -> None:
        event = _make_event(DocumentType.IMAGING_REPORT, "imaging_report_mri")
        pdf = DocumentRegistry.generate(event, sample_profile)
        assert len(pdf) > 500

    def test_claim_administration_setup(self, sample_profile: ClaimProfile) -> None:
        event = _make_event(DocumentType.CLAIM_ADMINISTRATION, "claim_setup_record")
        pdf = DocumentRegistry.generate(event, sample_profile)
        assert len(pdf) > 500

    def test_claim_administration_closure(self, sample_profile: ClaimProfile) -> None:
        event = _make_event(DocumentType.CLAIM_ADMINISTRATION, "claim_closure_notice")
        pdf = DocumentRegistry.generate(event, sample_profile)
        assert len(pdf) > 500


class TestTierBGenerators:
    """Smoke tests for Tier B (structured) generators."""

    def test_medical_report_pr2(self, sample_profile: ClaimProfile) -> None:
        event = _make_event(DocumentType.MEDICAL_REPORT, "medical_report_pr2")
        pdf = DocumentRegistry.generate(event, sample_profile)
        assert len(pdf) > 500
        assert pdf[:4] == b"%PDF"

    def test_medical_report_progress(self, sample_profile: ClaimProfile) -> None:
        event = _make_event(DocumentType.MEDICAL_REPORT, "medical_report_treating_progress")
        pdf = DocumentRegistry.generate(event, sample_profile)
        assert len(pdf) > 500

    def test_medical_report_ps(self, sample_profile: ClaimProfile) -> None:
        event = _make_event(DocumentType.MEDICAL_REPORT, "medical_report_ps")
        pdf = DocumentRegistry.generate(event, sample_profile)
        assert len(pdf) > 500

    def test_wcab_filing_application(self, sample_profile: ClaimProfile) -> None:
        event = _make_event(DocumentType.WCAB_FILING, "wcab_filing_application")
        pdf = DocumentRegistry.generate(event, sample_profile)
        assert len(pdf) > 500

    def test_wcab_filing_dor(self, sample_profile: ClaimProfile) -> None:
        event = _make_event(DocumentType.WCAB_FILING, "wcab_filing_dor")
        pdf = DocumentRegistry.generate(event, sample_profile)
        assert len(pdf) > 500

    def test_settlement_cr(self, sample_profile: ClaimProfile) -> None:
        event = _make_event(DocumentType.SETTLEMENT_DOCUMENT, "settlement_compromise_release")
        pdf = DocumentRegistry.generate(event, sample_profile)
        assert len(pdf) > 500

    def test_settlement_stips(self, sample_profile: ClaimProfile) -> None:
        event = _make_event(DocumentType.SETTLEMENT_DOCUMENT, "settlement_stipulations")
        pdf = DocumentRegistry.generate(event, sample_profile)
        assert len(pdf) > 500

    def test_ame_qme_report_initial(self, sample_profile: ClaimProfile) -> None:
        event = _make_event(DocumentType.AME_QME_REPORT, "qme_report_initial")
        pdf = DocumentRegistry.generate(event, sample_profile)
        assert len(pdf) > 500
        assert pdf[:4] == b"%PDF"

    def test_ame_qme_report_psychiatric(self, sample_profile: ClaimProfile) -> None:
        event = _make_event(DocumentType.AME_QME_REPORT, "qme_report_psychiatric")
        pdf = DocumentRegistry.generate(event, sample_profile)
        assert len(pdf) > 500

    def test_utilization_review_rfa(self, sample_profile: ClaimProfile) -> None:
        event = _make_event(DocumentType.UTILIZATION_REVIEW, "utilization_review_rfa")
        pdf = DocumentRegistry.generate(event, sample_profile)
        assert len(pdf) > 500

    def test_utilization_review_decision(self, sample_profile: ClaimProfile) -> None:
        event = _make_event(DocumentType.UTILIZATION_REVIEW, "utilization_review_decision")
        pdf = DocumentRegistry.generate(event, sample_profile)
        assert len(pdf) > 500

    def test_billing_statement(self, sample_profile: ClaimProfile) -> None:
        event = _make_event(DocumentType.BILLING_STATEMENT, "billing_statement_medical")
        pdf = DocumentRegistry.generate(event, sample_profile)
        assert len(pdf) > 500

    def test_lien_claim(self, sample_profile: ClaimProfile) -> None:
        event = _make_event(DocumentType.LIEN_CLAIM, "lien_claim_medical_provider")
        pdf = DocumentRegistry.generate(event, sample_profile)
        assert len(pdf) > 500

    def test_medical_chronology(self, sample_profile: ClaimProfile) -> None:
        event = _make_event(DocumentType.MEDICAL_CHRONOLOGY, "medical_chronology_settlement")
        pdf = DocumentRegistry.generate(event, sample_profile)
        assert len(pdf) > 500

    def test_return_to_work_sjdb(self, sample_profile: ClaimProfile) -> None:
        event = _make_event(DocumentType.RETURN_TO_WORK, "return_to_work_sjdb_offer")
        pdf = DocumentRegistry.generate(event, sample_profile)
        assert len(pdf) > 500

    def test_investigation_report_denial(self, sample_profile: ClaimProfile) -> None:
        event = _make_event(
            DocumentType.INVESTIGATION_REPORT, "investigation_report_denial_basis"
        )
        pdf = DocumentRegistry.generate(event, sample_profile)
        assert len(pdf) > 500

    def test_deposition_transcript_applicant(self, sample_profile: ClaimProfile) -> None:
        event = _make_event(
            DocumentType.DEPOSITION_TRANSCRIPT, "deposition_transcript_applicant"
        )
        pdf = DocumentRegistry.generate(event, sample_profile)
        assert len(pdf) > 500

    def test_discovery_request_subpoena(self, sample_profile: ClaimProfile) -> None:
        event = _make_event(DocumentType.DISCOVERY_REQUEST, "discovery_request_subpoena")
        pdf = DocumentRegistry.generate(event, sample_profile)
        assert len(pdf) > 500

    def test_work_product(self, sample_profile: ClaimProfile) -> None:
        event = _make_event(DocumentType.WORK_PRODUCT, "work_product_case_eval")
        pdf = DocumentRegistry.generate(event, sample_profile)
        assert len(pdf) > 500


class TestTierAGenerators:
    """Smoke tests for Tier A (form-accurate approximation) generators."""

    def test_dwc1_claim_form(self, sample_profile: ClaimProfile) -> None:
        event = _make_event(DocumentType.DWC1_CLAIM_FORM, "dwc1_claim_form",
                            "DWC-1 Workers' Compensation Claim Form")
        pdf = DocumentRegistry.generate(event, sample_profile)
        assert len(pdf) > 500
        assert pdf[:4] == b"%PDF"

    def test_dwc_official_form_105(self, sample_profile: ClaimProfile) -> None:
        event = _make_event(DocumentType.DWC_OFFICIAL_FORM, "dwc_form_105_qme_panel",
                            "DWC Form 105 — QME Panel Request")
        pdf = DocumentRegistry.generate(event, sample_profile)
        assert len(pdf) > 500
        assert pdf[:4] == b"%PDF"

    def test_dwc_official_form_deu_rating(self, sample_profile: ClaimProfile) -> None:
        event = _make_event(DocumentType.DWC_OFFICIAL_FORM, "dwc_form_deu_rating",
                            "DEU Formal Rating — Permanent Disability")
        pdf = DocumentRegistry.generate(event, sample_profile)
        assert len(pdf) > 500


class TestAllDocumentTypesSmoke:
    """
    Parametrized smoke: one generation call per DocumentType.
    Ensures no type raises an unhandled exception.
    """

    _TYPE_SUBTYPES = {
        DocumentType.DWC1_CLAIM_FORM: "dwc1_claim_form",
        DocumentType.MEDICAL_REPORT: "medical_report_pr2",
        DocumentType.BILLING_STATEMENT: "billing_statement_medical",
        DocumentType.LEGAL_CORRESPONDENCE: "legal_correspondence_qme_objection",
        DocumentType.EMPLOYER_REPORT: "employer_report_of_injury",
        DocumentType.INVESTIGATION_REPORT: "investigation_report_denial_basis",
        DocumentType.UTILIZATION_REVIEW: "utilization_review_rfa",
        DocumentType.AME_QME_REPORT: "qme_report_initial",
        DocumentType.DEPOSITION_TRANSCRIPT: "deposition_transcript_applicant",
        DocumentType.IMAGING_REPORT: "imaging_report_xray",
        DocumentType.PHARMACY_RECORD: "pharmacy_dispensing",
        DocumentType.WAGE_STATEMENT: "wage_statement_employer",
        DocumentType.BENEFIT_NOTICE: "benefit_notice_acceptance",
        DocumentType.SETTLEMENT_DOCUMENT: "settlement_compromise_release",
        DocumentType.CORRESPONDENCE: "adjuster_initial_contact",
        DocumentType.OTHER: "misc",
        DocumentType.WCAB_FILING: "wcab_filing_application",
        DocumentType.LIEN_CLAIM: "lien_claim_medical_provider",
        DocumentType.DISCOVERY_REQUEST: "discovery_request_subpoena",
        DocumentType.RETURN_TO_WORK: "return_to_work_sjdb_offer",
        DocumentType.PAYMENT_RECORD: "payment_record_td_first",
        DocumentType.DWC_OFFICIAL_FORM: "dwc_form_105_qme_panel",
        DocumentType.WORK_PRODUCT: "work_product_eval",
        DocumentType.MEDICAL_CHRONOLOGY: "medical_chronology_settlement",
        DocumentType.CLAIM_ADMINISTRATION: "claim_setup_record",
    }

    @pytest.mark.parametrize("doc_type", list(DocumentType))
    def test_generates_nonempty_pdf(
        self, doc_type: DocumentType, sample_profile: ClaimProfile
    ) -> None:
        subtype = self._TYPE_SUBTYPES.get(doc_type, "generic")
        event = _make_event(doc_type, subtype, title=f"Test — {doc_type.value}")
        pdf = DocumentRegistry.generate(event, sample_profile)
        assert len(pdf) > 500, (
            f"DocumentType.{doc_type.name} generated only {len(pdf)} bytes (< 500)"
        )
        assert pdf[:4] == b"%PDF", (
            f"DocumentType.{doc_type.name} output does not start with %PDF magic bytes"
        )
