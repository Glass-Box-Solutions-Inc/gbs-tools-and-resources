"""
Faker-based coherent case data generation. Produces internally-consistent
GeneratedCase objects with document manifests appropriate to each litigation stage.

v2.0: Uses lifecycle engine for document generation with 188-subtype taxonomy.
Backward-compatible — legacy CaseProfile still works via adapter.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from typing import Optional

from faker import Faker

from data.case_profiles import CaseProfile
from data.lifecycle_engine import (
    CaseParameters,
    LifecycleStage,
    NodeDocumentRule,
    collect_documents_for_case,
    walk_lifecycle,
)
from data.models import (
    DocumentSpec,
    DocumentSubtype,
    GeneratedApplicant,
    GeneratedCase,
    GeneratedCaseTimeline,
    GeneratedEmployer,
    GeneratedInjury,
    GeneratedInsurance,
    GeneratedPhysician,
    InjuryType,
    LitigationStage,
)
from data.taxonomy import DOCUMENT_SUBTYPE_LABELS
from data.wc_constants import (
    ALL_BODY_PARTS,
    ALL_EMPLOYERS,
    BODY_PARTS,
    CA_CITIES,
    DEFAULT_ICD10,
    DEFENSE_FIRMS,
    ICD10_CODES,
    INJURY_MECHANISMS,
    INSURANCE_CARRIERS,
    JUDGE_NAMES,
    MEDICAL_FACILITIES,
    SPECIALTIES,
    WCAB_VENUES,
)

# Template class lookup for subtypes — maps taxonomy subtypes to template classes.
# Subtypes not listed here fall through to "GenericDocumentTemplate" (Phase 2).
SUBTYPE_TO_TEMPLATE: dict[str, str] = {
    # Medical — Treating Physician Reports
    "TREATING_PHYSICIAN_REPORT_PR2": "TreatingPhysicianReport",
    "TREATING_PHYSICIAN_REPORT_PR4": "TreatingPhysicianReport",
    "TREATING_PHYSICIAN_REPORT_FINAL": "TreatingPhysicianReport",
    "TREATING_PHYSICIAN_REPORT": "TreatingPhysicianReport",

    # Medical — Records by Specialty (reuse TreatingPhysicianReport layout)
    "ORTHOPEDIC_RECORDS": "TreatingPhysicianReport",
    "CHIROPRACTIC_RECORDS": "TreatingPhysicianReport",
    "PHYSICAL_THERAPY_RECORDS": "TreatingPhysicianReport",
    "PAIN_MANAGEMENT_RECORDS": "TreatingPhysicianReport",
    "PSYCHIATRIC_TREATMENT_RECORDS": "TreatingPhysicianReport",
    "ACUPUNCTURE_RECORDS": "TreatingPhysicianReport",
    "ONGOING_TREATMENT_RECORDS": "TreatingPhysicianReport",

    # Medical — Diagnostics
    "DIAGNOSTICS_IMAGING": "DiagnosticReport",
    "DIAGNOSTICS_LAB_RESULTS": "DiagnosticReport",
    "DIAGNOSTICS": "DiagnosticReport",

    # Medical — Surgery/Hospital
    "OPERATIVE_HOSPITAL_RECORDS": "OperativeRecord",
    "ACUTE_CARE_HOSPITAL_RECORDS": "OperativeRecord",
    "EMERGENCY_ROOM_RECORDS": "OperativeRecord",
    "DISCHARGE_SUMMARY": "OperativeRecord",

    # Medical — QME/AME
    "QME_REPORT_INITIAL": "QmeAmeReport",
    "QME_REPORT_SUPPLEMENTAL": "QmeAmeReport",
    "AME_REPORT": "QmeAmeReport",
    "IME_REPORT": "QmeAmeReport",
    "PSYCH_EVAL_REPORT_QME_AME": "QmeAmeReport",
    "APPORTIONMENT_REPORT": "QmeAmeReport",
    "MEDICAL_LEGAL_QME_AME_IME": "QmeAmeReport",

    # Medical — UR
    "UTILIZATION_REVIEW_DECISION_REGULAR": "UtilizationReview",
    "UTILIZATION_REVIEW_DECISION_EXPEDITED": "UtilizationReview",
    "UTILIZATION_REVIEW_DECISION": "UtilizationReview",
    "INDEPENDENT_MEDICAL_REVIEW_DECISION": "UtilizationReview",
    "MEDICAL_TREATMENT_AUTHORIZATION": "UtilizationReview",
    "MEDICAL_TREATMENT_DENIAL_UR": "UtilizationReview",

    # Medical — Billing
    "BILLING_UB04": "BillingRecords",
    "BILLING_CMS_1500": "BillingRecords",
    "BILLING_SUPERBILLS": "BillingRecords",
    "BILLING_UB04_HCFA_SUPERBILLS": "BillingRecords",
    "MEDICAL_BILL_INITIAL": "BillingRecords",
    "MEDICAL_BILL_SECOND_REQUEST": "BillingRecords",
    "MEDICAL_BILL_COLLECTION_NOTICE": "BillingRecords",
    "EXPLANATION_OF_REVIEW_EOR": "BillingRecords",
    "PHARMACY_RECORDS": "PharmacyRecords",

    # Legal — Applications
    "APPLICATION_FOR_ADJUDICATION_ORIGINAL": "ApplicationForAdjudication",
    "APPLICATION_FOR_ADJUDICATION_AMENDED": "ApplicationForAdjudication",
    "APPLICATION_FOR_ADJUDICATION_PACKAGE": "ApplicationForAdjudication",
    "APPLICATION_FOR_ADJUDICATION": "ApplicationForAdjudication",

    # Legal — DOR
    "DECLARATION_OF_READINESS_REGULAR": "DeclarationOfReadiness",
    "DECLARATION_OF_READINESS_EXPEDITED": "DeclarationOfReadiness",
    "DECLARATION_OF_READINESS_MSC": "DeclarationOfReadiness",
    "DECLARATION_OF_READINESS": "DeclarationOfReadiness",

    # Legal — Court Orders/Minutes
    "MINUTES_ORDERS_FINDINGS_AWARD": "MinutesOrders",
    "ORDER_APPOINTING_QME_PANEL": "MinutesOrders",
    "ORDER_ON_SANCTIONS": "MinutesOrders",
    "ORDER_ON_LIEN": "MinutesOrders",
    "ORDER_ON_RECONSIDERATION": "MinutesOrders",
    "ORDER_ON_MSC": "MinutesOrders",
    "ORDER_INTERLOCUTORY": "MinutesOrders",
    "ORDER_FINAL": "MinutesOrders",

    # Legal — Settlements
    "STIPULATIONS_WITH_REQUEST_FOR_AWARD_PARTIAL": "Stipulations",
    "STIPULATIONS_WITH_REQUEST_FOR_AWARD_FULL": "Stipulations",
    "STIPULATIONS_WITH_REQUEST_FOR_AWARD": "Stipulations",
    "COMPROMISE_AND_RELEASE_STANDARD": "CompromiseAndRelease",
    "COMPROMISE_AND_RELEASE_MSA": "CompromiseAndRelease",
    "COMPROMISE_AND_RELEASE": "CompromiseAndRelease",

    # Correspondence
    "ADJUSTER_LETTER_INFORMATIONAL": "AdjusterLetter",
    "ADJUSTER_LETTER_REQUEST": "AdjusterLetter",
    "ADJUSTER_LETTER": "AdjusterLetter",
    "DEFENSE_COUNSEL_LETTER_INFORMATIONAL": "DefenseCounselLetter",
    "DEFENSE_COUNSEL_LETTER_DEMAND": "DefenseCounselLetter",
    "DEFENSE_COUNSEL_LETTER": "DefenseCounselLetter",
    "NOTICE_OF_HEARING_COURT_ISSUED": "CourtNotice",
    "NOTICE_OF_HEARING_PARTY_SERVED": "CourtNotice",
    "NOTICE_OF_TRIAL": "CourtNotice",
    "NOTICE_OF_MSC": "CourtNotice",
    "NOTICE_OF_ORDER": "CourtNotice",
    "NOTICE_OF_LIEN_FILING": "CourtNotice",
    "NOTICE_OF_LIEN_CONFERENCE": "CourtNotice",
    "COURT_DISTRICT_NOTICE": "CourtNotice",
    "NOTICE_TO_APPEAR": "CourtNotice",
    "CLIENT_INTAKE_CORRESPONDENCE": "ClientIntake",
    "CLIENT_CORRESPONDENCE_INFORMATIONAL": "ClientIntake",
    "CLIENT_CORRESPONDENCE_REQUEST": "ClientIntake",

    # Discovery
    "SUBPOENA_SDT_ISSUED": "Subpoena",
    "SUBPOENA_SDT_RECEIVED": "Subpoena",
    "DEPOSITION_NOTICE_APPLICANT": "DepositionNotice",
    "DEPOSITION_NOTICE_DEFENDANT": "DepositionNotice",
    "DEPOSITION_NOTICE_MEDICAL_WITNESS": "DepositionNotice",
    "DEPOSITION_NOTICE": "DepositionNotice",
    "DEPOSITION_TRANSCRIPT": "DepositionTranscript",
    "SUBPOENAED_RECORDS_MEDICAL": "SubpoenaedRecords",
    "SUBPOENAED_RECORDS_EMPLOYMENT": "SubpoenaedRecords",
    "SUBPOENAED_RECORDS_OTHER": "SubpoenaedRecords",
    "SUBPOENAED_RECORDS": "SubpoenaedRecords",

    # Employment
    "WAGE_STATEMENTS_PRE_INJURY": "WageStatement",
    "WAGE_STATEMENTS_POST_INJURY": "WageStatement",
    "WAGE_STATEMENTS_EARNING_RECORDS": "WageStatement",
    "JOB_DESCRIPTION_PRE_INJURY": "JobDescription",
    "JOB_DESCRIPTIONS_ESSENTIAL_FUNCTIONS": "JobDescription",
    "WORK_RESTRICTIONS_POST_INJURY": "JobDescription",
    "PERSONNEL_FILES": "PersonnelFile",
    "TIMECARDS_SCHEDULES": "WageStatement",

    # Official Forms (reuse closest template)
    "CLAIM_FORM_DWC1": "ClientIntake",
    "CLAIM_FORM": "ClientIntake",
    "EMPLOYER_REPORT_INJURY": "ClientIntake",
    "EMPLOYER_REPORT": "ClientIntake",
    "FIRST_REPORT_OF_INJURY_PHYSICIAN": "TreatingPhysicianReport",
    "CLAIM_ACCEPTANCE_LETTER": "AdjusterLetter",
    "CLAIM_DENIAL_LETTER": "AdjusterLetter",
    "CLAIM_DELAY_NOTICE": "AdjusterLetter",
    "NOTICE_OF_BENEFITS": "AdjusterLetter",
    "MPN_AUTHORIZATION": "AdjusterLetter",
    "MEDICAL_TREATMENT_AUTHORIZATION_RFA": "UtilizationReview",
    "IMR_APPLICATION_FORM": "UtilizationReview",
    "IMR_DETERMINATION_FORM": "UtilizationReview",
    "QME_PANEL_REQUEST_FORM_105": "ClientIntake",
    "QME_PANEL_REQUEST_FORM_106": "ClientIntake",
    "DEU_RATING_REQUEST_FORM": "ClientIntake",

    # Summaries
    "MEDICAL_CHRONOLOGY_TIMELINE": "MedicalChronology",
    "SETTLEMENT_VALUATION_MEMO": "SettlementMemo",
    "QME_AME_SUMMARY_WITH_ISSUE_LIST": "SettlementMemo",
    "DEPOSITION_SUMMARY": "SettlementMemo",
    "TRIAL_BRIEF": "SettlementMemo",
    "PRETRIAL_CONFERENCE_STATEMENT": "SettlementMemo",
    "CASE_ANALYSIS_MEMO": "SettlementMemo",

    # Settlement process
    "SETTLEMENT_DEMAND_LETTER": "DefenseCounselLetter",
    "SETTLEMENT_CONFERENCE_STATEMENT": "SettlementMemo",
    "SETTLEMENT_AGREEMENT_DRAFT": "CompromiseAndRelease",
    "SETTLEMENT_AGREEMENT_EXECUTED": "CompromiseAndRelease",

    # Liens (reuse billing or court notice)
    "LIEN_MEDICAL_PROVIDER": "BillingRecords",
    "LIEN_HOSPITAL": "BillingRecords",
    "LIEN_PHARMACY": "BillingRecords",
    "LIEN_ATTORNEY_COSTS": "BillingRecords",
    "LIEN_AMBULANCE_TRANSPORT": "BillingRecords",
    "LIEN_SELF_PROCUREMENT_MEDICAL": "BillingRecords",
    "LIEN_EDD_OVERPAYMENT": "BillingRecords",
    "LIEN_RESOLUTION": "Stipulations",
    "LIEN_DISMISSAL": "CourtNotice",
    "NOTICE_OF_INTENT_TO_FILE_LIEN": "CourtNotice",

    # Rating/RTW
    "PD_RATING_CALCULATION_WORKSHEET": "SettlementMemo",
    "PD_RATING_CONVERSION": "SettlementMemo",
    "TD_PAYMENT_RECORD_ONGOING": "WageStatement",
    "TD_PAYMENT_RECORD_RETROACTIVE": "WageStatement",
    "PD_PAYMENT_RECORD_ADVANCE": "WageStatement",
    "PD_PAYMENT_RECORD_ONGOING": "WageStatement",
    "PD_PAYMENT_RECORD_FINAL": "WageStatement",
    "EXPENSE_REIMBURSEMENT": "BillingRecords",

    # Petitions
    "PETITION_RECONSIDERATION_FILED": "ApplicationForAdjudication",
    "PETITION_RECONSIDERATION_OPPOSITION": "DefenseCounselLetter",
    "PETITION_RECONSIDERATION_REPLY": "DefenseCounselLetter",
    "PETITION_REMOVAL_FILED": "ApplicationForAdjudication",
    "PETITION_REMOVAL_ANSWER": "DefenseCounselLetter",
    "PETITION_REOPENING": "ApplicationForAdjudication",
    "PETITION_SERIOUS_WILLFUL": "ApplicationForAdjudication",

    # Letters/Routine
    "CLIENT_STATUS_LETTERS": "ClientIntake",
    "ADJUSTER_DEMANDS_REQUESTS": "AdjusterLetter",
    "ADVOCACY_LETTERS_PTP": "DefenseCounselLetter",
    "ADVOCACY_LETTERS_QME": "DefenseCounselLetter",
    "ADVOCACY_LETTERS_AME": "DefenseCounselLetter",
    "ADVOCACY_LETTERS_PTP_QME_AME": "DefenseCounselLetter",
    "EMAIL_CORRESPONDENCE": "ClientIntake",
    "FAX_CORRESPONDENCE": "ClientIntake",
    "MAILED_CORRESPONDENCE": "ClientIntake",
    "DEMAND_LETTER_FORMAL": "DefenseCounselLetter",
    "REQUEST_FOR_INFORMATION_FORMAL": "AdjusterLetter",
    "STATUS_UPDATE_INFORMATIONAL": "ClientIntake",
    "COURTESY_COPY_FYI": "ClientIntake",

    # Surveillance
    "INVESTIGATOR_REPORT": "SettlementMemo",
    "WITNESS_STATEMENT": "DepositionTranscript",

    # Packages (reuse parent template)
    "DOR_STATUS_MSC_EXPEDITED": "DeclarationOfReadiness",
    "STIPS_WITH_REQUEST_FOR_AWARD_PACKAGE": "Stipulations",
    "CR_PACKAGE_WITH_ADDENDA": "CompromiseAndRelease",
    "APPLICATION_FOR_ADJUDICATION_PACKAGE": "ApplicationForAdjudication",

    # Vouchers/forms (reuse closest)
    "SJDB_VOUCHER_6000": "ClientIntake",
    "SJDB_VOUCHER_8000": "ClientIntake",
    "SJDB_VOUCHER_10000": "ClientIntake",
    "OFFER_OF_WORK_REGULAR_AD_10133_53": "AdjusterLetter",
    "OFFER_OF_WORK_MODIFIED_AD_10118": "AdjusterLetter",
    "FIRST_FILL_PHARMACY_FORM": "PharmacyRecords",
    "DISTRICT_SPECIFIC_FORM": "ClientIntake",
    "SAFETY_TRAINING_LOGS_INCIDENT_REPORTS": "PersonnelFile",
    "PRIOR_CLAIMS_EDD_SDI_INFO": "WageStatement",
    "VOCATIONAL_EVALUATION_REPORT": "QmeAmeReport",
    "TRAINING_COMPLETION_CERTIFICATE": "ClientIntake",
    "VOCATIONAL_EXPERT_REPORT": "QmeAmeReport",
    "ECONOMIST_REPORT": "SettlementMemo",
    "LIFE_CARE_PLANNER_REPORT": "QmeAmeReport",
    "ACCIDENT_RECONSTRUCTIONIST_REPORT": "SettlementMemo",
    "BIOMECHANICAL_EXPERT_REPORT": "QmeAmeReport",

    # Surveillance placeholders (text-based reports)
    "SURVEILLANCE_VIDEO": "ClientIntake",
    "SOCIAL_MEDIA_EVIDENCE": "ClientIntake",
    "ACTIVITY_DIARY_SELF_REPORTED": "ClientIntake",
}


class FakeDataGenerator:
    def __init__(self, seed: int = 42):
        self.fake = Faker("en_US")
        Faker.seed(seed)
        random.seed(seed)
        self._rng = random.Random(seed)

    # -----------------------------------------------------------------
    # v2: Generate from CaseParameters (lifecycle engine)
    # -----------------------------------------------------------------

    def generate_case_from_params(
        self, case_number: int, params: CaseParameters
    ) -> GeneratedCase:
        """Generate a case using lifecycle-aware parameters."""
        # Map target_stage to LitigationStage enum
        stage = LitigationStage(params.target_stage)

        # Map injury type
        injury_type = InjuryType(params.injury_type)

        applicant = self._generate_applicant()
        employer = self._generate_employer_for_category(params.body_part_category)
        insurance = self._generate_insurance()
        injuries = self._generate_injuries_from_params(params, injury_type)
        treating = self._generate_physician("treating", params.body_part_category)

        qme = None
        if params.eval_type in ("qme", "ame"):
            qme = self._generate_physician("qme", params.body_part_category)

        # Generate prior providers for cases with prior medical history
        prior_providers = self._generate_prior_providers(
            stage, params.body_part_category, treating,
            complexity=getattr(params, 'complexity', 'standard'),
        )

        doi = injuries[0].date_of_injury
        timeline = self._generate_timeline_from_params(stage, doi, params)
        venue = random.choice(WCAB_VENUES)
        judge = random.choice(JUDGE_NAMES)

        case = GeneratedCase(
            case_number=case_number,
            internal_id=f"TC-{case_number:03d}",
            litigation_stage=stage,
            applicant=applicant,
            employer=employer,
            insurance=insurance,
            injuries=injuries,
            treating_physician=treating,
            qme_physician=qme,
            prior_providers=prior_providers,
            timeline=timeline,
            venue=venue,
            judge_name=judge,
            case_parameters=params,
        )

        # Generate document manifest via lifecycle engine
        case.document_specs = self._generate_lifecycle_manifest(case, params)
        return case

    def _generate_lifecycle_manifest(
        self, case: GeneratedCase, params: CaseParameters
    ) -> list[DocumentSpec]:
        """Generate document specs using the lifecycle engine."""
        doi = case.timeline.date_of_injury
        today = date.today()
        days_since_doi = (today - doi).days

        # Collect documents from lifecycle walk
        doc_rules = collect_documents_for_case(params, self._rng)

        docs: list[DocumentSpec] = []
        seq_counters: dict[str, int] = {}
        # Track subpoenaed medical record index for round-robin provider assignment
        subpoenaed_medical_idx = 0

        for subtype_str, rule in doc_rules:
            # Track sequence per subtype
            seq_counters[subtype_str] = seq_counters.get(subtype_str, 0) + 1
            seq = seq_counters[subtype_str]

            # Calculate date from rule
            doc_date = self._calculate_date_from_rule(
                rule, doi, case.timeline, days_since_doi
            )

            # Get template class
            template_class = SUBTYPE_TO_TEMPLATE.get(subtype_str, "ClientIntake")

            # Get human-readable title
            subtype_enum = DocumentSubtype(subtype_str)
            title = self._generate_doc_title_v2(
                subtype_str, case, seq, doc_date
            )

            # Build context — wire provider_index for subpoenaed medical records
            context: dict = {}
            if subtype_str == "SUBPOENAED_RECORDS_MEDICAL" and case.prior_providers:
                context["provider_index"] = subpoenaed_medical_idx % len(case.prior_providers)
                subpoenaed_medical_idx += 1

            docs.append(DocumentSpec(
                subtype=subtype_enum,
                title=title,
                doc_date=doc_date,
                template_class=template_class,
                sequence_number=seq,
                context=context,
            ))

        docs.sort(key=lambda d: d.doc_date)
        return docs

    def _calculate_date_from_rule(
        self,
        rule: NodeDocumentRule,
        doi: date,
        timeline: GeneratedCaseTimeline,
        days_since_doi: int,
    ) -> date:
        """Calculate a document date from a rule's anchor and offset."""
        # Resolve anchor date
        anchor_map = {
            "doi": doi,
            "claim_filed": timeline.date_claim_filed,
            "application_filed": timeline.date_application_filed or doi + timedelta(days=120),
        }
        anchor = anchor_map.get(rule.date_anchor, doi)

        # Calculate offset
        min_off, max_off = rule.date_offset_days
        # Clamp max to days_since_doi to avoid future dates
        max_off = min(max_off, max(days_since_doi, min_off + 1))
        min_off = min(min_off, max_off)

        offset = self._rng.randint(min_off, max_off)
        result = anchor + timedelta(days=offset)

        # Ensure not in the future
        today = date.today()
        if result > today:
            result = today - timedelta(days=self._rng.randint(1, 30))

        return result

    def _generate_injuries_from_params(
        self, params: CaseParameters, injury_type: InjuryType
    ) -> list[GeneratedInjury]:
        """Generate injuries based on CaseParameters."""
        injuries = []
        doi = self._calculate_doi(LitigationStage(params.target_stage))

        for i in range(params.num_body_parts):
            if i == 0:
                bp_category = params.body_part_category
            elif params.has_psych_component and i == 1:
                bp_category = "psyche"
            else:
                bp_category = random.choice(["spine", "upper_extremity", "lower_extremity"])

            body_parts = self._pick_body_parts(bp_category)
            icd_codes = []
            for bp in body_parts:
                codes = ICD10_CODES.get(bp, DEFAULT_ICD10)
                icd_codes.extend([c[0] for c in codes[:1]])

            if injury_type == InjuryType.CUMULATIVE_TRAUMA:
                mechanisms = INJURY_MECHANISMS["cumulative_trauma"]
            else:
                mechanisms = INJURY_MECHANISMS["specific"]

            injuries.append(GeneratedInjury(
                date_of_injury=doi if i == 0 else doi - timedelta(days=random.randint(0, 30)),
                injury_type=injury_type,
                body_parts=body_parts,
                icd10_codes=icd_codes,
                adj_number=self.fake.numerify("ADJ#######"),
                description=f"Industrial injury to {', '.join(body_parts)}",
                mechanism=random.choice(mechanisms),
            ))
        return injuries

    def _generate_timeline_from_params(
        self, stage: LitigationStage, doi: date, params: CaseParameters
    ) -> GeneratedCaseTimeline:
        """Generate timeline with all lifecycle dates."""
        claim_filed = doi + timedelta(days=random.randint(1, 14))
        first_treatment = doi + timedelta(days=random.randint(0, 7))

        tl = GeneratedCaseTimeline(
            date_of_injury=doi,
            date_claim_filed=claim_filed,
            date_first_treatment=first_treatment,
        )

        # Claim response
        if params.claim_response == "accepted":
            tl.date_claim_response = claim_filed + timedelta(days=random.randint(14, 45))
        elif params.claim_response == "delayed":
            tl.date_claim_response = claim_filed + timedelta(days=random.randint(30, 90))
        elif params.claim_response == "denied":
            tl.date_claim_response = claim_filed + timedelta(days=random.randint(30, 90))

        # Application
        if params.has_attorney and stage not in (LitigationStage.INTAKE,):
            tl.date_application_filed = doi + timedelta(days=random.randint(60, 180))

        # UR dispute
        if params.has_ur_dispute:
            tl.date_ur_dispute = doi + timedelta(days=random.randint(60, 270))

        # IMR
        if params.imr_filed:
            tl.date_imr_decision = doi + timedelta(days=random.randint(150, 365))

        # Discovery
        if stage in (LitigationStage.DISCOVERY, LitigationStage.MEDICAL_LEGAL,
                     LitigationStage.SETTLEMENT, LitigationStage.RESOLVED):
            tl.date_discovery_start = doi + timedelta(days=random.randint(180, 365))

        # Medical-legal eval
        if params.eval_type in ("qme", "ame"):
            if params.eval_type == "qme":
                tl.date_qme_evaluation = doi + timedelta(days=random.randint(270, 545))
            else:
                tl.date_ame_evaluation = doi + timedelta(days=random.randint(270, 545))

        # Depositions
        if stage in (LitigationStage.MEDICAL_LEGAL, LitigationStage.SETTLEMENT,
                     LitigationStage.RESOLVED):
            tl.date_deposition = doi + timedelta(days=random.randint(365, 600))

        # Liens
        if params.has_liens:
            tl.date_lien_filed = doi + timedelta(days=random.randint(365, 730))
            tl.date_lien_conference = doi + timedelta(days=random.randint(500, 900))

        # Settlement/Resolution
        if stage in (LitigationStage.SETTLEMENT, LitigationStage.RESOLVED):
            tl.date_dor_filed = doi + timedelta(days=random.randint(500, 730))
            tl.date_settlement_conference = doi + timedelta(days=random.randint(600, 800))

        if stage == LitigationStage.RESOLVED:
            tl.date_resolved = doi + timedelta(days=random.randint(730, 1095))

        if params.resolution_type == "trial":
            tl.date_trial = doi + timedelta(days=random.randint(600, 1000))

        return tl

    def _generate_doc_title_v2(
        self,
        subtype_str: str,
        case: GeneratedCase,
        seq: int,
        doc_date: date,
    ) -> str:
        """Generate a human-readable title for a document using the 188-taxonomy labels."""
        date_str = doc_date.strftime("%Y-%m-%d")
        name = case.applicant.last_name
        label = DOCUMENT_SUBTYPE_LABELS.get(subtype_str, subtype_str.replace("_", " ").title())

        # Special titles for common types
        special = {
            "TREATING_PHYSICIAN_REPORT_PR2": f"PR-2 Initial Report - Dr. {case.treating_physician.last_name} - {date_str}",
            "TREATING_PHYSICIAN_REPORT_PR4": f"PR-4 Progress Report - Dr. {case.treating_physician.last_name} - {date_str}",
            "TREATING_PHYSICIAN_REPORT_FINAL": f"Final PR Report - Dr. {case.treating_physician.last_name} - {date_str}",
            "QME_REPORT_INITIAL": f"QME Report (Initial) - {case.qme_physician.last_name if case.qme_physician else 'TBD'} - {date_str}",
            "QME_REPORT_SUPPLEMENTAL": f"QME Report (Supplemental) - {case.qme_physician.last_name if case.qme_physician else 'TBD'} - {date_str}",
            "AME_REPORT": f"AME Report - {case.qme_physician.last_name if case.qme_physician else 'TBD'} - {date_str}",
            "APPLICATION_FOR_ADJUDICATION_ORIGINAL": f"Application for Adjudication - {name} - {date_str}",
            "CLAIM_FORM_DWC1": f"DWC-1 Claim Form - {name} - {date_str}",
            "EMPLOYER_REPORT_INJURY": f"Employer Report of Injury (5020) - {date_str}",
            "DEPOSITION_TRANSCRIPT": f"Deposition Transcript - {name} - {date_str}",
            "COMPROMISE_AND_RELEASE_STANDARD": f"Compromise and Release - {date_str}",
            "COMPROMISE_AND_RELEASE_MSA": f"Compromise and Release (MSA) - {date_str}",
            "SETTLEMENT_VALUATION_MEMO": f"Settlement Analysis Memo - {name} - {date_str}",
            "MEDICAL_CHRONOLOGY_TIMELINE": f"Medical Chronology - {name} - {date_str}",
        }

        title = special.get(subtype_str, f"{label} - {date_str}")
        if seq > 1:
            title = f"{title} ({seq})"
        return title

    # -----------------------------------------------------------------
    # v1: Legacy support — generate from CaseProfile
    # -----------------------------------------------------------------

    def generate_case(self, profile: CaseProfile) -> GeneratedCase:
        """Legacy: Generate from old CaseProfile. Converts to CaseParameters internally."""
        # Convert legacy profile to CaseParameters
        params = CaseParameters(
            target_stage=profile.stage.value,
            injury_type=profile.injury_type.value,
            body_part_category=profile.body_part_category,
            has_surgery=profile.has_surgery,
            has_attorney=True,
            num_body_parts=profile.num_injuries,
            has_psych_component=profile.body_part_category == "psyche" or profile.num_injuries > 1,
        )
        params = params.resolve_random(self._rng)
        return self.generate_case_from_params(profile.case_number, params)

    # -----------------------------------------------------------------
    # Shared helpers (used by both v1 and v2)
    # -----------------------------------------------------------------

    def _generate_prior_providers(
        self,
        stage: LitigationStage,
        body_part_category: str,
        treating_physician: GeneratedPhysician,
        complexity: str = "standard",
    ) -> list[GeneratedPhysician]:
        """Generate prior providers depending on litigation stage and complexity."""
        is_complex = complexity == "complex"
        if stage in (LitigationStage.DISCOVERY, LitigationStage.MEDICAL_LEGAL,
                     LitigationStage.SETTLEMENT, LitigationStage.RESOLVED):
            count = random.randint(5, 8) if is_complex else random.randint(2, 5)
        elif stage in (LitigationStage.INTAKE, LitigationStage.ACTIVE_TREATMENT):
            count = random.randint(2, 4) if is_complex else random.randint(0, 2)
        else:
            count = 0

        if count == 0:
            return []

        prior_specialty_pool = [
            "Internal Medicine", "Orthopedic Surgery", "Chiropractic",
            "Physical Therapy", "Pain Management",
            "Physical Medicine & Rehabilitation (PM&R)", "Neurology",
        ]
        # Avoid same specialty as treating physician
        available_specialties = [
            s for s in prior_specialty_pool if s != treating_physician.specialty
        ]
        if not available_specialties:
            available_specialties = prior_specialty_pool

        # Avoid same facility as treating physician
        available_facilities = [
            f for f in MEDICAL_FACILITIES if f != treating_physician.facility
        ]
        if len(available_facilities) < count:
            available_facilities = list(MEDICAL_FACILITIES)

        used_facilities = set()
        providers = []
        for _ in range(count):
            specialty = random.choice(available_specialties)
            # Pick a unique facility
            remaining = [f for f in available_facilities if f not in used_facilities]
            if not remaining:
                remaining = available_facilities
            facility = random.choice(remaining)
            used_facilities.add(facility)

            first = self.fake.first_name()
            last = self.fake.last_name()
            city, zipcode = random.choice(CA_CITIES)
            providers.append(GeneratedPhysician(
                first_name=first,
                last_name=last,
                specialty=specialty,
                facility=facility,
                address=f"{self.fake.street_address()}, {city}, CA {zipcode}",
                phone=self.fake.numerify("(###) ###-####"),
                license_number=self.fake.numerify("A######"),
                npi=self.fake.numerify("##########"),
            ))
        return providers

    def _generate_applicant(self) -> GeneratedApplicant:
        first = self.fake.first_name()
        last = self.fake.last_name()
        city, zipcode = random.choice(CA_CITIES)
        return GeneratedApplicant(
            first_name=first,
            last_name=last,
            date_of_birth=self.fake.date_of_birth(minimum_age=25, maximum_age=62),
            ssn_last_four=self.fake.numerify("####"),
            phone=self.fake.numerify("(###) ###-####"),
            email=f"{first.lower()}.{last.lower()}@{self.fake.free_email_domain()}",
            address_street=self.fake.street_address(),
            address_city=city,
            address_zip=zipcode,
        )

    def _generate_employer_for_category(self, body_part_category: str) -> GeneratedEmployer:
        category_map = {
            "spine": ["warehouse_logistics", "construction", "manufacturing", "government"],
            "upper_extremity": ["construction", "manufacturing", "retail_service", "government"],
            "lower_extremity": ["government", "warehouse_logistics", "retail_service", "construction"],
            "psyche": ["government", "healthcare"],
            "internal": ["manufacturing", "government"],
            "head": ["construction", "government"],
        }
        preferred = category_map.get(body_part_category, ["government"])
        matching = [e for e in ALL_EMPLOYERS if e[0] in preferred]
        if not matching:
            matching = ALL_EMPLOYERS
        industry, company, position = random.choice(matching)

        city, zipcode = random.choice(CA_CITIES)
        hire_years_ago = random.randint(2, 20)
        return GeneratedEmployer(
            company_name=company,
            address_street=self.fake.street_address(),
            address_city=city,
            address_zip=zipcode,
            phone=self.fake.numerify("(###) ###-####"),
            position=position,
            hire_date=date.today() - timedelta(days=hire_years_ago * 365),
            hourly_rate=round(random.uniform(18.0, 55.0), 2),
            weekly_hours=40.0,
            department=industry.replace("_", " ").title(),
        )

    def _generate_employer(self, profile: CaseProfile) -> GeneratedEmployer:
        """Legacy compatibility wrapper."""
        return self._generate_employer_for_category(profile.body_part_category)

    def _generate_insurance(self) -> GeneratedInsurance:
        carrier = random.choice(INSURANCE_CARRIERS)
        defense_firm = random.choice(DEFENSE_FIRMS)
        adj_first = self.fake.first_name()
        adj_last = self.fake.last_name()
        def_first = self.fake.first_name()
        def_last = self.fake.last_name()

        return GeneratedInsurance(
            carrier_name=carrier,
            claim_number=self.fake.numerify("######-######-WC-##"),
            policy_number=self.fake.numerify("WC-CA-########"),
            adjuster_name=f"{adj_first} {adj_last}",
            adjuster_phone=self.fake.numerify("(###) ###-####"),
            adjuster_email=f"{adj_first.lower()}.{adj_last.lower()}@{carrier.split()[0].lower()}.com",
            defense_firm=defense_firm,
            defense_attorney=f"{def_first} {def_last}, Esq.",
            defense_phone=self.fake.numerify("(###) ###-####"),
            defense_email=f"{def_first[0].lower()}{def_last.lower()}@{defense_firm.split()[0].lower()}.com",
        )

    def _generate_injuries(self, profile: CaseProfile) -> list[GeneratedInjury]:
        return self._generate_injuries_from_params(
            CaseParameters(
                target_stage=profile.stage.value,
                injury_type=profile.injury_type.value,
                body_part_category=profile.body_part_category,
                num_body_parts=profile.num_injuries,
            ),
            profile.injury_type,
        )

    def _pick_body_parts(self, category: str) -> list[str]:
        parts_pool = BODY_PARTS.get(category, BODY_PARTS["spine"])
        count = random.randint(1, min(3, len(parts_pool)))
        return random.sample(parts_pool, count)

    def _calculate_doi(self, stage: LitigationStage) -> date:
        today = date.today()
        ranges = {
            LitigationStage.INTAKE: (30, 90),
            LitigationStage.ACTIVE_TREATMENT: (180, 540),
            LitigationStage.DISCOVERY: (365, 730),
            LitigationStage.MEDICAL_LEGAL: (540, 900),
            LitigationStage.SETTLEMENT: (730, 1095),
            LitigationStage.RESOLVED: (900, 1460),
        }
        min_days, max_days = ranges[stage]
        return today - timedelta(days=random.randint(min_days, max_days))

    def _generate_timeline(self, stage: LitigationStage, doi: date) -> GeneratedCaseTimeline:
        """Legacy timeline generation."""
        claim_filed = doi + timedelta(days=random.randint(1, 14))
        first_treatment = doi + timedelta(days=random.randint(0, 7))

        tl = GeneratedCaseTimeline(
            date_of_injury=doi,
            date_claim_filed=claim_filed,
            date_first_treatment=first_treatment,
        )

        if stage in (LitigationStage.ACTIVE_TREATMENT, LitigationStage.DISCOVERY,
                     LitigationStage.MEDICAL_LEGAL, LitigationStage.SETTLEMENT,
                     LitigationStage.RESOLVED):
            tl.date_application_filed = doi + timedelta(days=random.randint(60, 180))

        if stage in (LitigationStage.DISCOVERY, LitigationStage.MEDICAL_LEGAL,
                     LitigationStage.SETTLEMENT, LitigationStage.RESOLVED):
            tl.date_discovery_start = doi + timedelta(days=random.randint(180, 365))

        if stage in (LitigationStage.MEDICAL_LEGAL, LitigationStage.SETTLEMENT,
                     LitigationStage.RESOLVED):
            tl.date_qme_evaluation = doi + timedelta(days=random.randint(270, 545))

        if stage in (LitigationStage.MEDICAL_LEGAL, LitigationStage.SETTLEMENT,
                     LitigationStage.RESOLVED):
            tl.date_deposition = doi + timedelta(days=random.randint(365, 600))

        if stage in (LitigationStage.SETTLEMENT, LitigationStage.RESOLVED):
            tl.date_dor_filed = doi + timedelta(days=random.randint(500, 730))
            tl.date_settlement_conference = doi + timedelta(days=random.randint(600, 800))

        if stage == LitigationStage.RESOLVED:
            tl.date_resolved = doi + timedelta(days=random.randint(730, 1095))

        return tl

    def _generate_physician(self, role: str, body_part_category: str) -> GeneratedPhysician:
        specialty_map = {
            "spine": ["Orthopedic Surgery", "Pain Management", "Neurosurgery", "Physical Medicine & Rehabilitation (PM&R)"],
            "upper_extremity": ["Orthopedic Surgery", "Hand Surgery", "Physical Medicine & Rehabilitation (PM&R)"],
            "lower_extremity": ["Orthopedic Surgery", "Physical Medicine & Rehabilitation (PM&R)"],
            "psyche": ["Psychiatry"],
            "internal": ["Internal Medicine"],
            "head": ["Neurology", "Neurosurgery"],
        }
        specialties = specialty_map.get(body_part_category, ["Orthopedic Surgery"])
        specialty = random.choice(specialties)
        facility = random.choice(MEDICAL_FACILITIES)
        first = self.fake.first_name()
        last = self.fake.last_name()
        city, zipcode = random.choice(CA_CITIES)

        return GeneratedPhysician(
            first_name=first,
            last_name=last,
            specialty=specialty,
            facility=facility,
            address=f"{self.fake.street_address()}, {city}, CA {zipcode}",
            phone=self.fake.numerify("(###) ###-####"),
            license_number=self.fake.numerify("A######"),
            npi=self.fake.numerify("##########"),
        )
