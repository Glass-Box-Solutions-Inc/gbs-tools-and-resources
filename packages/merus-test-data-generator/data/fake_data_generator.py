"""
Faker-based coherent case data generation. Produces internally-consistent
GeneratedCase objects with document manifests appropriate to each litigation stage.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from typing import Optional

from faker import Faker

from data.case_profiles import CaseProfile
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


class FakeDataGenerator:
    def __init__(self, seed: int = 42):
        self.fake = Faker("en_US")
        Faker.seed(seed)
        random.seed(seed)

    def generate_case(self, profile: CaseProfile) -> GeneratedCase:
        applicant = self._generate_applicant()
        employer = self._generate_employer(profile)
        insurance = self._generate_insurance()
        injuries = self._generate_injuries(profile)
        treating = self._generate_physician("treating", profile.body_part_category)
        qme = None
        if profile.stage.value in ("discovery", "medical_legal", "settlement", "resolved"):
            qme = self._generate_physician("qme", profile.body_part_category)

        timeline = self._generate_timeline(profile.stage, injuries[0].date_of_injury)
        venue = random.choice(WCAB_VENUES)
        judge = random.choice(JUDGE_NAMES)

        case = GeneratedCase(
            case_number=profile.case_number,
            internal_id=f"TC-{profile.case_number:03d}",
            litigation_stage=profile.stage,
            applicant=applicant,
            employer=employer,
            insurance=insurance,
            injuries=injuries,
            treating_physician=treating,
            qme_physician=qme,
            timeline=timeline,
            venue=venue,
            judge_name=judge,
        )

        case.document_specs = self._generate_document_manifest(case, profile)
        return case

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

    def _generate_employer(self, profile: CaseProfile) -> GeneratedEmployer:
        # Pick employer matching body part category for realism
        category_map = {
            "spine": ["warehouse_logistics", "construction", "manufacturing", "government"],
            "upper_extremity": ["construction", "manufacturing", "retail_service", "government"],
            "lower_extremity": ["government", "warehouse_logistics", "retail_service", "construction"],
            "psyche": ["government", "healthcare"],
            "internal": ["manufacturing", "government"],
            "head": ["construction", "government"],
        }
        preferred = category_map.get(profile.body_part_category, ["government"])
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
        injuries = []
        doi = self._calculate_doi(profile.stage)

        for i in range(profile.num_injuries):
            if i == 0:
                bp_category = profile.body_part_category
                injury_type = profile.injury_type
            else:
                # Secondary injury — psyche or different body region
                bp_category = random.choice(["psyche", "spine"])
                injury_type = profile.injury_type

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

    def _generate_document_manifest(
        self, case: GeneratedCase, profile: CaseProfile
    ) -> list[DocumentSpec]:
        stage = profile.stage
        docs: list[DocumentSpec] = []
        doi = case.timeline.date_of_injury

        # --- Distribution table from the plan ---
        distribution = self._get_distribution(stage, profile.has_surgery)
        target_total = random.randint(profile.min_docs, profile.max_docs)

        for subtype_str, (min_ct, max_ct) in distribution.items():
            subtype = DocumentSubtype(subtype_str)
            count = random.randint(min_ct, max_ct)
            for seq in range(1, count + 1):
                doc_date = self._calculate_doc_date(subtype, doi, stage, seq, count)
                template_class = self._subtype_to_template(subtype)
                title = self._generate_doc_title(subtype, case, seq, doc_date)
                docs.append(DocumentSpec(
                    subtype=subtype,
                    title=title,
                    doc_date=doc_date,
                    template_class=template_class,
                    sequence_number=seq,
                ))

        # Trim or pad to target
        if len(docs) > target_total:
            # Remove lower-priority docs
            priority_order = [
                DocumentSubtype.PERSONNEL_FILE,
                DocumentSubtype.JOB_DESCRIPTION,
                DocumentSubtype.COURT_NOTICE,
                DocumentSubtype.SUBPOENAED_RECORDS,
            ]
            for low_pri in priority_order:
                if len(docs) <= target_total:
                    break
                removable = [d for d in docs if d.subtype == low_pri]
                while removable and len(docs) > target_total:
                    docs.remove(removable.pop())

        docs.sort(key=lambda d: d.doc_date)
        return docs

    def _get_distribution(
        self, stage: LitigationStage, has_surgery: bool
    ) -> dict[str, tuple[int, int]]:
        # Base distributions from the plan
        base: dict[str, tuple[int, int]] = {}

        # Always present
        base["CLIENT_INTAKE_CORRESPONDENCE"] = (2, 2)
        base["CLAIM_FORM"] = (1, 1)
        base["EMPLOYER_REPORT"] = (1, 1)
        base["WAGE_STATEMENTS"] = (1, 1)

        if stage == LitigationStage.INTAKE:
            base["ADJUSTER_LETTER"] = (1, 2)
            base["TREATING_PHYSICIAN_REPORT"] = (2, 3)
            base["DIAGNOSTIC_REPORT"] = (1, 2)
            base["PHARMACY_RECORDS"] = (1, 1)
            base["BILLING_UB04_HCFA_SUPERBILLS"] = (1, 2)
            base["JOB_DESCRIPTION"] = (0, 1)
        elif stage == LitigationStage.ACTIVE_TREATMENT:
            base["ADJUSTER_LETTER"] = (2, 3)
            base["TREATING_PHYSICIAN_REPORT"] = (4, 6)
            base["DIAGNOSTIC_REPORT"] = (2, 4)
            base["PHARMACY_RECORDS"] = (1, 2)
            base["BILLING_UB04_HCFA_SUPERBILLS"] = (3, 4)
            base["APPLICATION_FOR_ADJUDICATION"] = (1, 1)
            base["JOB_DESCRIPTION"] = (1, 1)
            base["DEFENSE_COUNSEL_LETTER"] = (1, 2)
            base["COURT_NOTICE"] = (0, 1)
            base["UTILIZATION_REVIEW"] = (1, 2)
            if has_surgery:
                base["OPERATIVE_HOSPITAL_RECORDS"] = (1, 1)
        elif stage == LitigationStage.DISCOVERY:
            base["ADJUSTER_LETTER"] = (3, 4)
            base["TREATING_PHYSICIAN_REPORT"] = (5, 7)
            base["DIAGNOSTIC_REPORT"] = (3, 4)
            base["PHARMACY_RECORDS"] = (1, 2)
            base["BILLING_UB04_HCFA_SUPERBILLS"] = (3, 5)
            base["APPLICATION_FOR_ADJUDICATION"] = (1, 1)
            base["WAGE_STATEMENTS"] = (1, 2)
            base["JOB_DESCRIPTION"] = (1, 1)
            base["DEFENSE_COUNSEL_LETTER"] = (2, 3)
            base["COURT_NOTICE"] = (1, 2)
            base["SUBPOENA_SDT_ISSUED"] = (2, 3)
            base["SUBPOENAED_RECORDS"] = (1, 2)
            base["DEPOSITION_NOTICE"] = (1, 2)
            base["DEPOSITION_TRANSCRIPT"] = (0, 1)
            base["UTILIZATION_REVIEW"] = (1, 2)
            if has_surgery:
                base["OPERATIVE_HOSPITAL_RECORDS"] = (1, 1)
        elif stage == LitigationStage.MEDICAL_LEGAL:
            base["ADJUSTER_LETTER"] = (3, 4)
            base["TREATING_PHYSICIAN_REPORT"] = (5, 7)
            base["DIAGNOSTIC_REPORT"] = (3, 4)
            base["PHARMACY_RECORDS"] = (1, 2)
            base["BILLING_UB04_HCFA_SUPERBILLS"] = (3, 5)
            base["APPLICATION_FOR_ADJUDICATION"] = (1, 1)
            base["WAGE_STATEMENTS"] = (1, 2)
            base["JOB_DESCRIPTION"] = (1, 1)
            base["DEFENSE_COUNSEL_LETTER"] = (2, 3)
            base["COURT_NOTICE"] = (1, 2)
            base["SUBPOENA_SDT_ISSUED"] = (2, 3)
            base["SUBPOENAED_RECORDS"] = (1, 2)
            base["DEPOSITION_NOTICE"] = (1, 2)
            base["DEPOSITION_TRANSCRIPT"] = (1, 2)
            base["QME_AME_REPORT"] = (1, 2)
            base["UTILIZATION_REVIEW"] = (1, 2)
            base["DECLARATION_OF_READINESS"] = (0, 1)
            base["MEDICAL_CHRONOLOGY"] = (0, 1)
            if has_surgery:
                base["OPERATIVE_HOSPITAL_RECORDS"] = (1, 1)
        elif stage == LitigationStage.SETTLEMENT:
            base["ADJUSTER_LETTER"] = (4, 5)
            base["TREATING_PHYSICIAN_REPORT"] = (5, 7)
            base["DIAGNOSTIC_REPORT"] = (3, 4)
            base["PHARMACY_RECORDS"] = (1, 2)
            base["BILLING_UB04_HCFA_SUPERBILLS"] = (3, 5)
            base["APPLICATION_FOR_ADJUDICATION"] = (1, 1)
            base["WAGE_STATEMENTS"] = (1, 2)
            base["JOB_DESCRIPTION"] = (1, 1)
            base["DEFENSE_COUNSEL_LETTER"] = (3, 4)
            base["COURT_NOTICE"] = (2, 3)
            base["SUBPOENA_SDT_ISSUED"] = (2, 3)
            base["SUBPOENAED_RECORDS"] = (1, 2)
            base["DEPOSITION_NOTICE"] = (1, 2)
            base["DEPOSITION_TRANSCRIPT"] = (1, 2)
            base["QME_AME_REPORT"] = (1, 2)
            base["UTILIZATION_REVIEW"] = (1, 2)
            base["DECLARATION_OF_READINESS"] = (1, 1)
            base["MEDICAL_CHRONOLOGY"] = (1, 1)
            base["SETTLEMENT_MEMO"] = (1, 1)
            base["STIPULATIONS"] = (0, 1)
            if has_surgery:
                base["OPERATIVE_HOSPITAL_RECORDS"] = (1, 1)
        elif stage == LitigationStage.RESOLVED:
            base["ADJUSTER_LETTER"] = (5, 6)
            base["TREATING_PHYSICIAN_REPORT"] = (5, 7)
            base["DIAGNOSTIC_REPORT"] = (3, 4)
            base["PHARMACY_RECORDS"] = (1, 2)
            base["BILLING_UB04_HCFA_SUPERBILLS"] = (3, 5)
            base["APPLICATION_FOR_ADJUDICATION"] = (1, 1)
            base["WAGE_STATEMENTS"] = (1, 2)
            base["JOB_DESCRIPTION"] = (1, 1)
            base["DEFENSE_COUNSEL_LETTER"] = (3, 4)
            base["COURT_NOTICE"] = (2, 3)
            base["SUBPOENA_SDT_ISSUED"] = (2, 3)
            base["SUBPOENAED_RECORDS"] = (1, 2)
            base["DEPOSITION_NOTICE"] = (1, 2)
            base["DEPOSITION_TRANSCRIPT"] = (1, 2)
            base["QME_AME_REPORT"] = (1, 2)
            base["UTILIZATION_REVIEW"] = (1, 2)
            base["DECLARATION_OF_READINESS"] = (1, 1)
            base["MEDICAL_CHRONOLOGY"] = (1, 1)
            base["SETTLEMENT_MEMO"] = (1, 1)
            base["STIPULATIONS"] = (0, 1)
            base["MINUTES_ORDERS_FINDINGS"] = (1, 2)
            if has_surgery:
                base["OPERATIVE_HOSPITAL_RECORDS"] = (1, 1)

        return base

    def _calculate_doc_date(
        self,
        subtype: DocumentSubtype,
        doi: date,
        stage: LitigationStage,
        seq: int,
        total: int,
    ) -> date:
        today = date.today()
        days_since_doi = (today - doi).days

        # Spread documents across the case timeline
        if subtype in (DocumentSubtype.CLAIM_FORM, DocumentSubtype.EMPLOYER_REPORT):
            return doi + timedelta(days=random.randint(1, 14))
        elif subtype == DocumentSubtype.CLIENT_INTAKE_CORRESPONDENCE:
            return doi + timedelta(days=random.randint(7, 30))
        elif subtype == DocumentSubtype.APPLICATION_FOR_ADJUDICATION:
            return doi + timedelta(days=random.randint(60, 180))
        elif subtype == DocumentSubtype.WAGE_STATEMENTS:
            return doi + timedelta(days=random.randint(14, 60))
        elif subtype == DocumentSubtype.JOB_DESCRIPTION:
            return doi + timedelta(days=random.randint(14, 45))
        elif subtype in (DocumentSubtype.QME_AME_REPORT,):
            return doi + timedelta(days=random.randint(270, min(545, days_since_doi)))
        elif subtype == DocumentSubtype.SETTLEMENT_MEMO:
            return doi + timedelta(days=random.randint(
                int(days_since_doi * 0.7), max(int(days_since_doi * 0.9), int(days_since_doi * 0.7) + 1)
            ))
        elif subtype == DocumentSubtype.DECLARATION_OF_READINESS:
            return doi + timedelta(days=random.randint(
                int(days_since_doi * 0.6), max(int(days_since_doi * 0.8), int(days_since_doi * 0.6) + 1)
            ))
        else:
            # Spread evenly across timeline
            if total <= 1:
                offset_frac = 0.5
            else:
                offset_frac = (seq / (total + 1))
            base_offset = int(days_since_doi * 0.1 + days_since_doi * 0.8 * offset_frac)
            jitter = random.randint(-14, 14)
            offset = max(7, min(days_since_doi - 7, base_offset + jitter))
            return doi + timedelta(days=offset)

    def _subtype_to_template(self, subtype: DocumentSubtype) -> str:
        mapping = {
            DocumentSubtype.TREATING_PHYSICIAN_REPORT: "TreatingPhysicianReport",
            DocumentSubtype.DIAGNOSTIC_REPORT: "DiagnosticReport",
            DocumentSubtype.OPERATIVE_HOSPITAL_RECORDS: "OperativeRecord",
            DocumentSubtype.QME_AME_REPORT: "QmeAmeReport",
            DocumentSubtype.UTILIZATION_REVIEW: "UtilizationReview",
            DocumentSubtype.PHARMACY_RECORDS: "PharmacyRecords",
            DocumentSubtype.BILLING_UB04_HCFA_SUPERBILLS: "BillingRecords",
            DocumentSubtype.APPLICATION_FOR_ADJUDICATION: "ApplicationForAdjudication",
            DocumentSubtype.DECLARATION_OF_READINESS: "DeclarationOfReadiness",
            DocumentSubtype.MINUTES_ORDERS_FINDINGS: "MinutesOrders",
            DocumentSubtype.STIPULATIONS: "Stipulations",
            DocumentSubtype.COMPROMISE_AND_RELEASE: "CompromiseAndRelease",
            DocumentSubtype.ADJUSTER_LETTER: "AdjusterLetter",
            DocumentSubtype.DEFENSE_COUNSEL_LETTER: "DefenseCounselLetter",
            DocumentSubtype.COURT_NOTICE: "CourtNotice",
            DocumentSubtype.CLIENT_INTAKE_CORRESPONDENCE: "ClientIntake",
            DocumentSubtype.SUBPOENA_SDT_ISSUED: "Subpoena",
            DocumentSubtype.DEPOSITION_NOTICE: "DepositionNotice",
            DocumentSubtype.DEPOSITION_TRANSCRIPT: "DepositionTranscript",
            DocumentSubtype.SUBPOENAED_RECORDS: "SubpoenaedRecords",
            DocumentSubtype.WAGE_STATEMENTS: "WageStatement",
            DocumentSubtype.JOB_DESCRIPTION: "JobDescription",
            DocumentSubtype.PERSONNEL_FILE: "PersonnelFile",
            DocumentSubtype.CLAIM_FORM: "ClientIntake",
            DocumentSubtype.EMPLOYER_REPORT: "ClientIntake",
            DocumentSubtype.MEDICAL_CHRONOLOGY: "MedicalChronology",
            DocumentSubtype.SETTLEMENT_MEMO: "SettlementMemo",
        }
        return mapping.get(subtype, "ClientIntake")

    def _generate_doc_title(
        self,
        subtype: DocumentSubtype,
        case: GeneratedCase,
        seq: int,
        doc_date: date,
    ) -> str:
        date_str = doc_date.strftime("%Y-%m-%d")
        name = case.applicant.last_name

        titles = {
            DocumentSubtype.TREATING_PHYSICIAN_REPORT: f"PR-2 Report - Dr. {case.treating_physician.last_name} - {date_str}",
            DocumentSubtype.DIAGNOSTIC_REPORT: f"Diagnostic Imaging Report - {date_str}",
            DocumentSubtype.OPERATIVE_HOSPITAL_RECORDS: f"Operative Report - {date_str}",
            DocumentSubtype.QME_AME_REPORT: f"QME Report - {case.qme_physician.last_name if case.qme_physician else 'TBD'} - {date_str}",
            DocumentSubtype.UTILIZATION_REVIEW: f"Utilization Review Decision - {date_str}",
            DocumentSubtype.PHARMACY_RECORDS: f"Pharmacy Records - {name} - {date_str}",
            DocumentSubtype.BILLING_UB04_HCFA_SUPERBILLS: f"Medical Billing - {date_str}",
            DocumentSubtype.APPLICATION_FOR_ADJUDICATION: f"Application for Adjudication - {name} - {date_str}",
            DocumentSubtype.DECLARATION_OF_READINESS: f"Declaration of Readiness to Proceed - {date_str}",
            DocumentSubtype.MINUTES_ORDERS_FINDINGS: f"Minutes of Hearing - {date_str}",
            DocumentSubtype.STIPULATIONS: f"Stipulations with Request for Award - {date_str}",
            DocumentSubtype.COMPROMISE_AND_RELEASE: f"Compromise and Release - {date_str}",
            DocumentSubtype.ADJUSTER_LETTER: f"Correspondence from {case.insurance.carrier_name} - {date_str}",
            DocumentSubtype.DEFENSE_COUNSEL_LETTER: f"Letter from Defense Counsel - {date_str}",
            DocumentSubtype.COURT_NOTICE: f"WCAB Notice of Hearing - {date_str}",
            DocumentSubtype.CLIENT_INTAKE_CORRESPONDENCE: f"Client Intake - {name} - {date_str}",
            DocumentSubtype.SUBPOENA_SDT_ISSUED: f"Subpoena Duces Tecum - {date_str}",
            DocumentSubtype.DEPOSITION_NOTICE: f"Notice of Deposition - {date_str}",
            DocumentSubtype.DEPOSITION_TRANSCRIPT: f"Deposition Transcript - {name} - {date_str}",
            DocumentSubtype.SUBPOENAED_RECORDS: f"Subpoenaed Medical Records - {date_str}",
            DocumentSubtype.WAGE_STATEMENTS: f"Wage Statement - {case.employer.company_name} - {date_str}",
            DocumentSubtype.JOB_DESCRIPTION: f"Job Description - {case.employer.position} - {date_str}",
            DocumentSubtype.PERSONNEL_FILE: f"Personnel File Extract - {name} - {date_str}",
            DocumentSubtype.CLAIM_FORM: f"DWC-1 Claim Form - {name} - {date_str}",
            DocumentSubtype.EMPLOYER_REPORT: f"Employer Report of Injury - {date_str}",
            DocumentSubtype.MEDICAL_CHRONOLOGY: f"Medical Chronology - {name} - {date_str}",
            DocumentSubtype.SETTLEMENT_MEMO: f"Settlement Analysis Memo - {name} - {date_str}",
        }
        title = titles.get(subtype, f"{subtype.value} - {date_str}")
        if seq > 1:
            title = f"{title} ({seq})"
        return title
