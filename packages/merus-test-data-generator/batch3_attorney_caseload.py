#!/usr/bin/env python3
"""
Batch 3: Comprehensive CA WC Attorney Caseload — 47 Custom Cases.

Generates 47 highly customized Workers' Compensation cases spanning all 22 legal
categories, the Top 25 most litigated subcategories, and 12 landmark doctrines.
Designed from PRD: docs/PRD-WC-ATTORNEY-MOCK-CASELOAD.md

Groups:
    A (AC-01..AC-08): Causation & Liability — 8 cases
    B (BB-01..BB-07): Benefits & Compensation — 7 cases
    C (CM-01..CM-06): Medical Treatment — 6 cases
    D (DP-01..DP-03): Psychiatric Claims — 3 cases
    E (EP-01..EP-05): Procedure & Practice — 5 cases
    F (FP-01..FP-05): Penalties & Special Funds — 5 cases
    G (GR-01..GR-08): Routine/Baseline — 8 cases
    H (HG-01..HG-05): Gap-Fillers — 5 cases

Usage:
    python batch3_attorney_caseload.py

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import random
import shutil
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import DB_PATH, OUTPUT_DIR
from data.fake_data_generator import FakeDataGenerator
from data.lifecycle_engine import CaseParameters
from data.models import (
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
from orchestration.pipeline import Pipeline, _load_template_class, _sanitize_filename
from orchestration.progress_tracker import ProgressTracker

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _date_ago(days: int) -> date:
    """Return a date N days in the past."""
    return date.today() - timedelta(days=days)


def _make_applicant(
    first: str,
    last: str,
    dob: date,
    city: str = "Los Angeles",
    zipcode: str = "90001",
) -> GeneratedApplicant:
    ssn_last = f"{random.randint(1000, 9999)}"
    return GeneratedApplicant(
        first_name=first,
        last_name=last,
        date_of_birth=dob,
        ssn_last_four=ssn_last,
        phone=f"({random.randint(213,818)}) {random.randint(200,999)}-{random.randint(1000,9999)}",
        email=f"{first.lower()}.{last.lower()}@gmail.com",
        address_street=f"{random.randint(100,9999)} Main St",
        address_city=city,
        address_zip=zipcode,
    )


def _make_employer(
    company: str,
    position: str,
    city: str = "Los Angeles",
    zipcode: str = "90012",
    hire_date: date | None = None,
    hourly_rate: float = 28.50,
    department: str = "",
) -> GeneratedEmployer:
    if hire_date is None:
        hire_date = _date_ago(365 * 5)
    return GeneratedEmployer(
        company_name=company,
        address_street=f"{random.randint(100,9999)} Commerce Ave",
        address_city=city,
        address_zip=zipcode,
        phone=f"({random.randint(213,818)}) {random.randint(200,999)}-{random.randint(1000,9999)}",
        position=position,
        hire_date=hire_date,
        hourly_rate=hourly_rate,
        weekly_hours=40.0,
        department=department,
    )


def _make_insurance(
    carrier: str = "State Compensation Insurance Fund (SCIF)",
    defense_firm: str = "Bradford & Barthel LLP",
) -> GeneratedInsurance:
    adj_f, adj_l = _random_name()
    def_f, def_l = _random_name()
    return GeneratedInsurance(
        carrier_name=carrier,
        claim_number=f"{random.randint(100000,999999)}-{random.randint(100000,999999)}-WC-{random.randint(10,99)}",
        policy_number=f"WC-CA-{random.randint(10000000,99999999)}",
        adjuster_name=f"{adj_f} {adj_l}",
        adjuster_phone=f"(800) {random.randint(200,999)}-{random.randint(1000,9999)}",
        adjuster_email=f"{adj_f.lower()}.{adj_l.lower()}@{carrier.split()[0].lower()}.com",
        defense_firm=defense_firm,
        defense_attorney=f"{def_f} {def_l}, Esq.",
        defense_phone=f"(213) {random.randint(200,999)}-{random.randint(1000,9999)}",
        defense_email=f"{def_f[0].lower()}{def_l.lower()}@{defense_firm.split()[0].lower()}.com",
    )


def _make_injury(
    doi: date,
    injury_type: InjuryType,
    body_parts: list[str],
    icd10_codes: list[str],
    description: str,
    mechanism: str,
) -> GeneratedInjury:
    return GeneratedInjury(
        date_of_injury=doi,
        injury_type=injury_type,
        body_parts=body_parts,
        icd10_codes=icd10_codes,
        adj_number=f"ADJ{random.randint(1000000,9999999)}",
        description=description,
        mechanism=mechanism,
    )


def _make_physician(
    first: str,
    last: str,
    specialty: str,
    facility: str,
    city: str = "Los Angeles",
    zipcode: str = "90048",
) -> GeneratedPhysician:
    return GeneratedPhysician(
        first_name=first,
        last_name=last,
        specialty=specialty,
        facility=facility,
        address=f"{random.randint(100,9999)} Medical Dr, {city}, CA {zipcode}",
        phone=f"({random.randint(213,818)}) {random.randint(200,999)}-{random.randint(1000,9999)}",
        license_number=f"A{random.randint(100000,999999)}",
        npi=f"{random.randint(1000000000,9999999999)}",
    )


_NAME_POOL = [
    ("Michael", "Johnson"), ("Sarah", "Williams"), ("David", "Martinez"),
    ("Jennifer", "Garcia"), ("Robert", "Davis"), ("Maria", "Rodriguez"),
    ("James", "Wilson"), ("Linda", "Anderson"), ("Thomas", "Taylor"),
    ("Patricia", "Thomas"), ("Christopher", "Hernandez"), ("Elizabeth", "Moore"),
    ("Daniel", "Jackson"), ("Karen", "White"), ("Matthew", "Lopez"),
    ("Susan", "Harris"), ("Anthony", "Clark"), ("Nancy", "Lewis"),
    ("Mark", "Robinson"), ("Sandra", "Walker"),
]
_name_idx = 0


def _random_name() -> tuple[str, str]:
    global _name_idx
    name = _NAME_POOL[_name_idx % len(_NAME_POOL)]
    _name_idx += 1
    return name


# ---------------------------------------------------------------------------
# Scenario definitions — 47 cases
# ---------------------------------------------------------------------------

def define_scenarios() -> list[dict]:
    """Define all 47 attorney caseload scenarios from the PRD."""
    scenarios: list[dict] = []


    # --- Group A: Causation & Liability (AC-01 through AC-08) ---

    scenarios.append({
        "internal_id": "AC-01",
        "case_params": CaseParameters(
            target_stage="discovery",
            claim_response="delayed",
            has_attorney=True,
            eval_type="qme",
            has_surgery=False,
            has_psych_component=False,
            has_ur_dispute=False,
            has_liens=False,
            num_body_parts=1,
            complexity="standard",
            injury_type="specific",
            body_part_category="spine",
        ),
        "applicant": _make_applicant("Marco", "Delgado", date(1983, 1, 1), "Los Angeles", "90001"),
        "employer": _make_employer(
            "Pacific Coast Logistics, Inc.", "Warehouse Associate",
            "Los Angeles", "90012", hire_date=_date_ago(365 * 6), hourly_rate=22.00,
            department="Receiving & Shipping",
        ),
        "insurance": _make_insurance("State Compensation Insurance Fund (SCIF)", "Bradford & Barthel LLP"),
        "injuries": [
            _make_injury(
                doi=date(2025, 8, 14),
                injury_type=InjuryType.SPECIFIC,
                body_parts=["lumbar spine (L4-L5, L5-S1)"],
                icd10_codes=["M54.5", "M51.16"],
                description=(
                    "Specific injury — lumbar spine: L4-L5 and L5-S1 disc degeneration with low back pain. "
                    "Industrial event of lifting a 60-pound box from ground level to shoulder-height shelf. "
                    "Carrier initially accepted claim but now disputes whether industrial event caused a new "
                    "injury or merely aggravated pre-existing asymptomatic degenerative disc disease. Prior "
                    "non-industrial chiropractic treatment for low back pain 3 years prior is central to "
                    "the AOE/COE and apportionment dispute."
                ),
                mechanism="Lifting 60-lb box from ground level to shoulder-height shelf",
            ),
        ],
        "treating": _make_physician("Raul", "Fernandez", "Chiropractic", "Pacific Chiropractic Clinic", "Los Angeles", "90010"),
        "qme": _make_physician("Steven", "Cho", "Orthopedic Surgery", "LA Orthopedic QME Group", "Los Angeles", "90048"),
        "prior_providers": [],
        "venue": "Los Angeles",
        "judge": "Hon. David M. Torres",
        "extra_context": {
            "adj_number": "ADJ18234567",
            "wc_issues": ["aoe_coe", "medical", "benefits"],
            "top_25_subcategories": ["#4 AOE/COE (Industrial Causation)"],
            "landmark_doctrine": None,
            "educational_note": (
                "Classic AOE/COE dispute with pre-existing condition overlay. Tests the fundamental "
                "compensability question: did the industrial event cause a 'new and further' injury, "
                "or is the worker experiencing his pre-existing degenerative condition? The QME's "
                "causation opinion is the pivotal document. QME must address causation, pre-existing "
                "condition, and apportionment under LC 4663."
            ),
            "prior_non_industrial_treatment": "Chiropractic treatment for low back pain 3 years prior",
            "employment_duration_years": 6,
        },
        "second_insurance": None,
    })

    scenarios.append({
        "internal_id": "AC-02",
        "case_params": CaseParameters(
            target_stage="medical_legal",
            claim_response="denied",
            has_attorney=True,
            eval_type="qme",
            has_surgery=True,
            has_psych_component=False,
            has_ur_dispute=False,
            has_liens=False,
            num_body_parts=3,
            complexity="complex",
            injury_type="specific",
            body_part_category="spine",
        ),
        "applicant": _make_applicant("Jessica", "Tran", date(1990, 1, 1), "Irvine", "92614"),
        "employer": _make_employer(
            "MedTech Surgical Solutions, Inc.", "Territory Sales Representative",
            "Los Angeles", "90025", hire_date=_date_ago(365 * 4), hourly_rate=38.50,
            department="West Coast Sales",
        ),
        "insurance": _make_insurance("Zurich North America", "Hueston Hennigan LLP"),
        "injuries": [
            _make_injury(
                doi=date(2025, 6, 22),
                injury_type=InjuryType.SPECIFIC,
                body_parts=["cervical spine (C5-C6)", "lumbar spine (L4-L5)", "right shoulder"],
                icd10_codes=["M50.12", "M51.16", "M75.11"],
                description=(
                    "Specific injury — multi-level spine and right shoulder: C5-C6 disc herniation with "
                    "radiculopathy, L4-L5 disc bulge, and right rotator cuff tear sustained in high-speed "
                    "rear-end collision on I-405. Carrier denies under going-and-coming rule. Applicant "
                    "argues exceptions: required-vehicle exception (employer-required company decals and "
                    "product samples in vehicle), roving-employee exception (traveling between client sites "
                    "is the job itself), and employer-conveyance exception (mileage reimbursement and "
                    "required vehicle modifications). Surgical intervention: cervical discectomy and "
                    "right shoulder rotator cuff repair performed."
                ),
                mechanism="Rear-ended at 45 mph on I-405 while traveling between client meetings (Irvine to Pasadena)",
            ),
        ],
        "treating": _make_physician("Karen", "Liu", "Physical Medicine & Rehabilitation", "SoCal PM&R Associates", "Los Angeles", "90048"),
        "qme": _make_physician("Robert", "Vasquez", "Orthopedic Surgery", "West Coast Orthopedic QME", "Los Angeles", "90048"),
        "prior_providers": [],
        "venue": "Los Angeles",
        "judge": "Hon. Margaret R. Chu",
        "extra_context": {
            "adj_number": "ADJ18345678",
            "wc_issues": ["aoe_coe", "employer_defenses", "benefits"],
            "top_25_subcategories": ["#4 AOE/COE", "#14 Going-and-Coming Rule"],
            "landmark_doctrine": "Going-and-Coming Rule (Hinojosa v. WCAB, Bramall v. WCAB)",
            "educational_note": (
                "Tests the most commonly litigated AOE/COE defense in California WC. The going-and-coming "
                "rule has numerous exceptions (special mission, required vehicle, employer conveyance, "
                "dual-purpose trip), and this fact pattern implicates at least three simultaneously. "
                "Employer's vehicle-use requirements (company decals, product samples, mileage reimbursement) "
                "create strong exception arguments. QME must address all three body parts."
            ),
            "going_and_coming_exceptions": [
                "required-vehicle exception",
                "roving-employee/special-mission exception",
                "employer-conveyance exception",
            ],
            "vehicle_use_evidence": "Company decals on personal vehicle, product samples in trunk, mileage reimbursement policy",
            "employment_duration_years": 4,
        },
        "second_insurance": None,
    })

    scenarios.append({
        "internal_id": "AC-03",
        "case_params": CaseParameters(
            target_stage="settlement",
            claim_response="accepted",
            has_attorney=True,
            eval_type="ame",
            has_surgery=True,
            has_psych_component=False,
            has_ur_dispute=False,
            has_liens=True,
            num_body_parts=3,
            complexity="complex",
            injury_type="cumulative_trauma",
            body_part_category="spine",
        ),
        "applicant": _make_applicant("Roberto", "Alvarez", date(1969, 1, 1), "Los Angeles", "90001"),
        "employer": _make_employer(
            "Golden State Builders, Inc.", "Construction Laborer",
            "Los Angeles", "90021", hire_date=_date_ago(365 * 22), hourly_rate=32.00,
            department="Concrete & Framing",
        ),
        "insurance": _make_insurance("ICW Group Insurance Companies", "Adelson, Testan, Brundo, Novell & Jimenez"),
        "injuries": [
            _make_injury(
                doi=date(2025, 3, 15),
                injury_type=InjuryType.CUMULATIVE_TRAUMA,
                body_parts=["bilateral shoulders", "cervical spine (C4-C7)", "lumbar spine (L3-S1)"],
                icd10_codes=["M75.40", "M75.41", "M54.12", "M48.06"],
                description=(
                    "Cumulative trauma — bilateral shoulder impingement, cervical radiculopathy (C4-C7), "
                    "and lumbar stenosis (L3-S1) from 22 years of continuous heavy construction labor "
                    "including repetitive heavy lifting, overhead work, jackhammer use, and concrete "
                    "pouring. AME rates combined impairment at 58% WPI and apportions 40% to 'natural "
                    "aging and degenerative processes' under LC 4663. Applicant challenges apportionment "
                    "under Escobedo framework; defendant defends under Benson v. WCAB. Surgical records "
                    "include right shoulder arthroscopy and cervical fusion C5-C6."
                ),
                mechanism="22 years of repetitive heavy lifting, overhead work, jackhammer use, concrete pouring",
            ),
        ],
        "treating": _make_physician("Michael", "Torres", "Orthopedic Surgery", "SoCal Orthopedic Group", "Los Angeles", "90048"),
        "qme": _make_physician("Sarah", "Goldstein", "Orthopedic Surgery", "California AME Associates", "Los Angeles", "90048"),
        "prior_providers": [],
        "venue": "Los Angeles",
        "judge": "Hon. Patricia A. Burke",
        "extra_context": {
            "adj_number": "ADJ18456789",
            "wc_issues": ["apportionment", "medical", "benefits"],
            "top_25_subcategories": ["#2 Apportionment", "#1 PD Rating Disputes", "#8 CT Dating & Liability"],
            "landmark_doctrine": "Benson v. WCAB / Escobedo v. Marshalls (apportionment to natural aging)",
            "educational_note": (
                "The Benson/Escobedo apportionment framework is the single most litigated issue in "
                "California Workers' Compensation. Tests the central tension: Can an AME apportion to "
                "'aging' without identifying a specific non-industrial causative event? The answer "
                "determines whether the applicant receives 58% PD or 35% PD — a difference of tens of "
                "thousands of dollars. 22 years of employment records showing physical demands are "
                "the applicant's strongest counter-evidence."
            ),
            "ame_wpi": "58% combined WPI",
            "apportionment_percentage": "40% to natural aging/degenerative processes (LC 4663)",
            "rating_strings": "With apportionment: ~35% PD; without: ~58% PD",
            "surgical_history": "Right shoulder arthroscopy; cervical fusion C5-C6",
            "employment_duration_years": 22,
        },
        "second_insurance": None,
    })

    scenarios.append({
        "internal_id": "AC-04",
        "case_params": CaseParameters(
            target_stage="active_treatment",
            claim_response="accepted",
            has_attorney=True,
            eval_type="none",
            has_surgery=False,
            has_psych_component=True,
            has_ur_dispute=False,
            has_liens=False,
            num_body_parts=2,
            complexity="complex",
            injury_type="specific",
            body_part_category="head",
        ),
        "applicant": _make_applicant("Darius", "Washington", date(1996, 1, 1), "Los Angeles", "90001"),
        "employer": _make_employer(
            "Shield Security Services, LLC", "Security Guard",
            "Los Angeles", "90040", hire_date=_date_ago(365 * 2), hourly_rate=19.50,
            department="Graveyard Shift — Commercial Warehouse",
        ),
        "insurance": _make_insurance("State Compensation Insurance Fund (SCIF)", "Bradford & Barthel LLP"),
        "injuries": [
            _make_injury(
                doi=date(2025, 11, 3),
                injury_type=InjuryType.SPECIFIC,
                body_parts=["head/TBI (post-concussive syndrome)", "psyche (PTSD)"],
                icd10_codes=["S06.0X0A", "F43.10"],
                description=(
                    "Specific injury — traumatic brain injury with post-concussive syndrome and PTSD: "
                    "Blunt force assault by unknown trespasser during nighttime security patrol at 2:00 AM. "
                    "Applicant sustained concussion without loss of consciousness and developed severe PTSD "
                    "with persistent nightmares, hypervigilance, and inability to return to work. "
                    "Positional risk doctrine applies — injury arose because job placed applicant at location "
                    "where random assault occurred. Employer investigation confirmed no personal animus "
                    "between applicant and attacker. PTSD flows directly from physical trauma, avoiding "
                    "LC 3208.3 six-month employment bar applicable to primary psychiatric claims. "
                    "Dual treating physicians: neurologist for TBI, psychologist for PTSD."
                ),
                mechanism="Blunt force assault by unknown trespasser during nighttime security patrol",
            ),
        ],
        "treating": _make_physician("James", "Park", "Neurology", "LA Neurological Associates", "Los Angeles", "90048"),
        "qme": None,
        "prior_providers": [
            _make_physician("Lisa", "Moreno", "Clinical Psychology", "Westside Behavioral Health", "Los Angeles", "90025"),
        ],
        "venue": "Los Angeles",
        "judge": "Hon. Samuel K. Watkins",
        "extra_context": {
            "adj_number": "ADJ18567890",
            "wc_issues": ["aoe_coe", "psychiatric", "penalties"],
            "top_25_subcategories": ["#4 AOE/COE", "#7 Psychiatric Injury"],
            "landmark_doctrine": "Positional Risk Doctrine",
            "educational_note": (
                "Demonstrates the positional risk doctrine — a foundational AOE/COE principle. Also "
                "showcases a combined physical/psychiatric claim where the psych component (PTSD) flows "
                "directly from the physical trauma, avoiding the LC 3208.3 threshold requirements "
                "applicable to primary psychiatric claims. The dual treating physician setup "
                "(neurologist + psychologist) is realistic for this injury pattern."
            ),
            "psych_treating_physician": "Dr. Lisa Moreno, PsyD (Clinical Psychology) — for PTSD",
            "employer_investigation_finding": "No prior relationship between applicant and attacker confirmed",
            "employment_duration_years": 2,
        },
        "second_insurance": None,
    })

    scenarios.append({
        "internal_id": "AC-05",
        "case_params": CaseParameters(
            target_stage="discovery",
            claim_response="denied",
            has_attorney=True,
            eval_type="none",
            has_surgery=True,
            has_psych_component=False,
            has_ur_dispute=False,
            has_liens=False,
            num_body_parts=2,
            complexity="complex",
            injury_type="specific",
            body_part_category="lower_extremity",
        ),
        "applicant": _make_applicant("Tyler", "Nguyen", date(1994, 1, 1), "Los Angeles", "90015"),
        "employer": _make_employer(
            "QuickBite Delivery, Inc.", "Delivery Driver",
            "Los Angeles", "90012", hire_date=_date_ago(30 * 14), hourly_rate=18.00,
            department="Gig Platform — Independent Contractor (Disputed)",
        ),
        "insurance": _make_insurance("No Coverage Asserted (IC Status Disputed)", "Sheppard, Mullin, Richter & Hampton LLP"),
        "injuries": [
            _make_injury(
                doi=date(2025, 9, 18),
                injury_type=InjuryType.SPECIFIC,
                body_parts=["right knee (ACL tear)", "right ankle (trimalleolar fracture)"],
                icd10_codes=["S83.511A", "S82.891A"],
                description=(
                    "Specific injury — right knee ACL tear and right ankle trimalleolar fracture sustained "
                    "in vehicle rollover on rain-slicked road during delivery run. Platform company asserts "
                    "independent contractor status and denies WC coverage. Applicant argues statutory "
                    "employee status under ABC test (Dynamex/AB 5): company cannot satisfy Prong B because "
                    "delivery is the company's core business. Threshold employment question must be resolved "
                    "before any benefits issue can be addressed. Surgical intervention: ACL reconstruction "
                    "and ankle ORIF performed."
                ),
                mechanism="Vehicle rollover on rain-slicked road during active delivery run",
            ),
        ],
        "treating": _make_physician("Amanda", "Chen", "Orthopedic Surgery", "Pacific Orthopedic Center", "Los Angeles", "90048"),
        "qme": None,
        "prior_providers": [],
        "venue": "Los Angeles",
        "judge": "Hon. James R. Hoffman",
        "extra_context": {
            "adj_number": "ADJ18678901",
            "wc_issues": ["employer_defenses", "insurance_coverage", "aoe_coe"],
            "top_25_subcategories": ["#16 Employer Denial Defenses", "#4 AOE/COE"],
            "landmark_doctrine": "AB 5/Dynamex — ABC Test (Dynamex Operations West v. Superior Court)",
            "educational_note": (
                "Tests the increasingly common AB 5/Dynamex independent contractor defense. Gig economy "
                "companies routinely deny WC coverage by asserting IC status. This case forces resolution "
                "of the threshold employment question before any benefits issue can be addressed. High-stakes "
                "because if the applicant loses, he has zero WC coverage for serious surgical injuries. "
                "Company cannot satisfy ABC test Prong B (delivery IS the company's core business)."
            ),
            "ic_classification_duration_months": 14,
            "abc_test_analysis": "Prong B fails — delivery is the hiring entity's primary business",
            "surgical_history": "ACL reconstruction (right knee); ORIF (right ankle trimalleolar fracture)",
        },
        "second_insurance": None,
    })

    scenarios.append({
        "internal_id": "AC-06",
        "case_params": CaseParameters(
            target_stage="medical_legal",
            claim_response="denied",
            has_attorney=True,
            eval_type="qme",
            has_surgery=True,
            has_psych_component=False,
            has_ur_dispute=False,
            has_liens=False,
            num_body_parts=2,
            complexity="standard",
            injury_type="specific",
            body_part_category="lower_extremity",
        ),
        "applicant": _make_applicant("Brian", "Kowalski", date(1987, 1, 1), "Los Angeles", "90001"),
        "employer": _make_employer(
            "Summit Manufacturing Corp.", "Scaffolding Installer",
            "Los Angeles", "90058", hire_date=_date_ago(365 * 5), hourly_rate=29.00,
            department="Heavy Manufacturing — Scaffolding Division",
        ),
        "insurance": _make_insurance("Employers Compensation Insurance Company", "Carothers DiSante & Freudenberger LLP"),
        "injuries": [
            _make_injury(
                doi=date(2025, 7, 10),
                injury_type=InjuryType.SPECIFIC,
                body_parts=["left femur (shaft fracture)", "left knee (medial meniscus tear)"],
                icd10_codes=["S72.302A", "S83.212A"],
                description=(
                    "Specific injury — left femur shaft fracture and medial meniscus tear from 12-foot "
                    "scaffolding fall. Post-accident drug test revealed THC metabolites. Employer denies "
                    "under intoxication defense (LC 5401), asserting cannabis impairment was proximate "
                    "cause of the fall. Applicant holds valid medical cannabis card for chronic insomnia "
                    "(non-industrial); THC metabolites persist weeks after use. Coworker witnesses confirm "
                    "no signs of impairment at time of accident. Employer bears burden of proving intoxication "
                    "was proximate cause — positive urine test alone is insufficient. Surgical intervention: "
                    "femur ORIF and arthroscopic meniscus repair performed."
                ),
                mechanism="Fall from 12-foot scaffolding while installing support brackets",
            ),
        ],
        "treating": _make_physician("David", "Kim", "Orthopedic Surgery", "Southern California Orthopedic Institute", "Los Angeles", "90048"),
        "qme": _make_physician("Thomas", "Wright", "Occupational Medicine", "CalOccMed QME Group", "Los Angeles", "90010"),
        "prior_providers": [],
        "venue": "Los Angeles",
        "judge": "Hon. Linda M. Santos",
        "extra_context": {
            "adj_number": "ADJ18789012",
            "wc_issues": ["employer_defenses", "evidence_standards"],
            "top_25_subcategories": ["#16 Employer Denial Defenses"],
            "landmark_doctrine": "Intoxication Defense Burden (LC 5401) — Cannabis/THC Metabolite Persistence",
            "educational_note": (
                "The cannabis intoxication defense is an evolving area post-legalization. The employer "
                "bears the burden of proving that intoxication was the proximate cause of the injury "
                "(not merely that the employee tested positive). THC metabolite persistence makes urine "
                "testing unreliable for proving impairment at the time of injury. Coworker witness "
                "declarations are critical counter-evidence. QME must address both causation and the "
                "intoxication defense."
            ),
            "drug_test_result": "Urine THC positive post-accident",
            "medical_cannabis_card": True,
            "cannabis_use_purpose": "Chronic insomnia (non-industrial)",
            "coworker_witnesses": "Confirm no signs of impairment observed at time of accident",
            "surgical_history": "Left femur ORIF; arthroscopic medial meniscus repair",
            "employment_duration_years": 5,
        },
        "second_insurance": None,
    })

    scenarios.append({
        "internal_id": "AC-07",
        "case_params": CaseParameters(
            target_stage="settlement",
            claim_response="accepted",
            has_attorney=True,
            eval_type="qme",
            has_surgery=False,
            has_psych_component=False,
            has_ur_dispute=False,
            has_liens=False,
            num_body_parts=1,
            complexity="standard",
            injury_type="specific",
            body_part_category="spine",
        ),
        "applicant": _make_applicant("Patricia", "Hernandez", date(1977, 1, 1), "Los Angeles", "90010"),
        "employer": _make_employer(
            "Valley Healthcare Associates", "Administrative Assistant",
            "Burbank", "91502", hire_date=_date_ago(365 * 11), hourly_rate=24.00,
            department="Medical Administration",
        ),
        "insurance": _make_insurance("State Compensation Insurance Fund (SCIF)", "Bradford & Barthel LLP"),
        "injuries": [
            _make_injury(
                doi=date(2025, 4, 22),
                injury_type=InjuryType.SPECIFIC,
                body_parts=["lumbar spine (L3-L4)"],
                icd10_codes=["M51.16"],
                description=(
                    "Specific injury — lumbar spine L3-L4 disc herniation from slip-and-fall on wet break "
                    "room floor. Applicant has prior stipulated WC award (2019) of 15% PD to lumbar spine "
                    "(L5-S1 level). QME rates current impairment at 35% WPI. Carrier seeks LC 4664(b) "
                    "prior award credit, reducing new PD to 20% (35% minus 15%). Applicant argues prior "
                    "injury was to L5-S1 while new injury is to L3-L4 — different spinal levels — and "
                    "therefore overlap is not 'the same region of the body' under LC 4664. MRI comparison "
                    "shows distinct pathology at different levels."
                ),
                mechanism="Slipped on wet floor in break room, landing on back",
            ),
        ],
        "treating": _make_physician("Elena", "Rodriguez", "Physical Medicine & Rehabilitation", "Valley PM&R Center", "Burbank", "91502"),
        "qme": _make_physician("William", "Park", "Orthopedic Surgery", "San Fernando Valley Orthopedic QME", "Encino", "91436"),
        "prior_providers": [],
        "venue": "Van Nuys",
        "judge": "Hon. Robert A. Flemming",
        "extra_context": {
            "adj_number": "ADJ18890123",
            "wc_issues": ["apportionment", "benefits", "subsequent_injury"],
            "top_25_subcategories": ["#2 Apportionment", "#1 PD Rating Disputes"],
            "landmark_doctrine": "LC 4664 Prior Award Credit — 'Same Region of Body' Analysis",
            "educational_note": (
                "LC 4664 prior award credit is a bread-and-butter apportionment issue. Nearly every "
                "applicant with a prior award faces this credit dispute. The 'same region of the body' "
                "question (different spinal levels: L5-S1 prior vs. L3-L4 new) adds a layer of complexity "
                "that comes up frequently in practice. Outcome turns on whether the spine is treated as a "
                "single 'region' or whether distinct levels are distinct regions."
            ),
            "prior_award": "2019 Stipulated Award — 15% PD to lumbar spine (L5-S1)",
            "qme_current_wpi": "35% WPI lumbar spine",
            "lc_4664_credit_dispute": "Carrier claims 15% credit; applicant disputes 'same region' finding",
            "mri_comparison": "2019 MRI shows L5-S1 pathology; 2025 MRI shows L3-L4 herniation — distinct levels",
            "employment_duration_years": 11,
        },
        "second_insurance": None,
    })

    scenarios.append({
        "internal_id": "AC-08",
        "case_params": CaseParameters(
            target_stage="discovery",
            claim_response="delayed",
            has_attorney=True,
            eval_type="ame",
            has_surgery=True,
            has_psych_component=False,
            has_ur_dispute=False,
            has_liens=False,
            num_body_parts=4,
            complexity="complex",
            injury_type="cumulative_trauma",
            body_part_category="upper_extremity",
        ),
        "applicant": _make_applicant("Susan", "Martinez", date(1973, 1, 1), "Los Angeles", "90026"),
        "employer": _make_employer(
            "St. Catherine's Medical Center", "Registered Nurse",
            "Los Angeles", "90033", hire_date=_date_ago(365 * 6), hourly_rate=48.00,
            department="Med-Surg Floor",
        ),
        "insurance": _make_insurance("Sedgwick Claims Management Services", "Klinedinst PC"),
        "injuries": [
            _make_injury(
                doi=date(2025, 10, 1),
                injury_type=InjuryType.CUMULATIVE_TRAUMA,
                body_parts=["bilateral carpal tunnel", "cervical spine (C5-C7)", "bilateral shoulders"],
                icd10_codes=["G56.00", "G56.01", "M54.12", "M75.10", "M75.11"],
                description=(
                    "Cumulative trauma — bilateral carpal tunnel syndrome, cervical radiculopathy (C5-C7), "
                    "and bilateral shoulder impingement from 20 years of repetitive nursing work across four "
                    "employers (patient lifting, transferring, charting, pushing hospital beds). CT end date "
                    "is last date worked/last injurious exposure at St. Catherine's. Current carrier disputes "
                    "CT end date and argues predominant exposure occurred at prior employers. Three prior "
                    "employers/carriers joined as co-defendants under LC 5500.5 (last injurious exposure "
                    "rule). Discovery focused on allocating liability across 20-year exposure period. "
                    "AME to opine on causation, exposure allocation, and apportionment."
                ),
                mechanism="20 years of repetitive patient lifting, transferring, charting, pushing hospital beds across 4 employers",
            ),
        ],
        "treating": _make_physician("Michelle", "Wong", "Physical Medicine & Rehabilitation", "LA County PM&R Associates", "Los Angeles", "90048"),
        "qme": _make_physician("James", "Hartford", "Orthopedic Surgery", "Southern California AME Panel", "Los Angeles", "90048"),
        "prior_providers": [],
        "venue": "Los Angeles",
        "judge": "Hon. Catherine M. Lee",
        "extra_context": {
            "adj_number": "ADJ18901234",
            "wc_issues": ["aoe_coe", "apportionment", "jurisdiction_and_venue"],
            "top_25_subcategories": ["#8 Cumulative Trauma Dating & Liability", "#4 AOE/COE"],
            "landmark_doctrine": "LC 5500.5 Multi-Employer CT Allocation — Last Injurious Exposure Rule",
            "educational_note": (
                "Multi-employer CT allocation is one of the most complex scenarios in WC practice. Four "
                "carriers pointing fingers at each other, disputes over the CT end date, arguments about "
                "where 'predominant' exposure occurred, and the interplay between LC 5500.5 (last injurious "
                "exposure) and LC 4663 (apportionment). Case management nightmare — perfect stress test "
                "for the system."
            ),
            "prior_employers": [
                {"employer": "Bay Area Regional Hospital", "years": 5, "duties": "Med-surg nursing"},
                {"employer": "Valley General Hospital", "years": 5, "duties": "Med-surg nursing"},
                {"employer": "Community Health Clinic", "years": 4, "duties": "Outpatient nursing"},
            ],
            "total_employment_years": 20,
            "current_employer_years": 6,
            "co_defendants": 3,
            "lc_5500_5_note": "Last injurious exposure rule — current carrier potentially liable for full CT claim subject to equitable allocation",
        },
        "second_insurance": None,
    })


    # --- Group B: Benefits & Compensation (BB-01 through BB-07) ---

    scenarios.append({
        "internal_id": "BB-01",
        "case_params": CaseParameters(
            target_stage="active_treatment",
            claim_response="accepted",
            has_attorney=True,
            eval_type="none",
            has_surgery=True,
            has_psych_component=False,
            has_ur_dispute=False,
            has_liens=False,
            num_body_parts=1,
            complexity="standard",
            injury_type="specific",
            body_part_category="lower_extremity",
        ),
        "applicant": _make_applicant("Angela", "Rivera", date(1991, 1, 1), "Los Angeles", "90023"),
        "employer": _make_employer(
            "HomeStyle Furnishings, Inc.", "Retail Sales Associate",
            "Los Angeles", "90018", hire_date=_date_ago(365 * 3), hourly_rate=18.50,
            department="Sales Floor",
        ),
        "insurance": _make_insurance("State Compensation Insurance Fund (SCIF)", "Bradford & Barthel LLP"),
        "injuries": [
            _make_injury(
                doi=date(2025, 5, 10),
                injury_type=InjuryType.SPECIFIC,
                body_parts=["right knee (medial meniscus tear)"],
                icd10_codes=["S83.212A"],
                description=(
                    "Specific injury — right knee medial meniscus tear from twisting while carrying heavy "
                    "furniture display on sales floor. Arthroscopic knee surgery performed; applicant placed "
                    "on modified duty (seated cashier work) for 3 months. Employer subsequently eliminated "
                    "modified position as part of company-wide workforce reduction (30 employees affected). "
                    "Applicant seeks resumption of TD benefits. Carrier argues applicant was terminated for "
                    "non-industrial reasons and could theoretically perform modified work. Per Huston v. WCAB, "
                    "involuntary loss of modified work triggers TD reinstatement. LC 5814 penalty petition "
                    "filed for unreasonable TD delay."
                ),
                mechanism="Twisted right knee while carrying heavy furniture display on sales floor",
            ),
        ],
        "treating": _make_physician("Craig", "Johnson", "Orthopedic Surgery", "LA Knee & Sports Medicine", "Los Angeles", "90048"),
        "qme": None,
        "prior_providers": [],
        "venue": "Los Angeles",
        "judge": "Hon. Richard E. Perez",
        "extra_context": {
            "adj_number": "ADJ19012345",
            "wc_issues": ["benefits", "return_to_work", "penalties"],
            "top_25_subcategories": ["#5 TD Rate & Duration", "#12 Return to Work / Modified Duty", "#11 Penalties"],
            "landmark_doctrine": "Huston v. WCAB — TD Reinstatement After Involuntary Loss of Modified Work",
            "educational_note": (
                "Tests the interplay between modified work, employer layoffs, and TD entitlement — one of "
                "the most common disputes in active treatment. The Huston line of cases establishes that "
                "involuntary loss of modified work triggers TD reinstatement. Also tests penalty exposure "
                "under LC 5814 for unreasonable TD delay. Workforce reduction of 30 employees supports "
                "the non-fault/non-industrial nature of the termination."
            ),
            "modified_duty_offered": "Seated cashier work for 3 months post-surgery",
            "termination_reason": "Company-wide workforce reduction — 30 employees affected, non-industrial",
            "td_gap": "TD payments stopped at termination; applicant seeks reinstatement per Huston",
            "penalty_basis": "LC 5814 — unreasonable delay/refusal to resume TD benefits",
            "employment_duration_years": 3,
        },
        "second_insurance": None,
    })

    scenarios.append({
        "internal_id": "BB-02",
        "case_params": CaseParameters(
            target_stage="medical_legal",
            claim_response="accepted",
            has_attorney=True,
            eval_type="ame",
            has_surgery=True,
            has_psych_component=False,
            has_ur_dispute=False,
            has_liens=True,
            num_body_parts=4,
            complexity="complex",
            injury_type="cumulative_trauma",
            body_part_category="spine",
        ),
        "applicant": _make_applicant("Jose", "Guerrero", date(1967, 1, 1), "Los Angeles", "90011"),
        "employer": _make_employer(
            "Los Angeles Unified School District", "Custodian/Janitor",
            "Los Angeles", "90012", hire_date=_date_ago(365 * 30), hourly_rate=24.00,
            department="Facilities & Maintenance",
        ),
        "insurance": _make_insurance("LAUSD Self-Insured / Keenan & Associates", "Keenan & Associates Defense"),
        "injuries": [
            _make_injury(
                doi=date(2025, 1, 15),
                injury_type=InjuryType.CUMULATIVE_TRAUMA,
                body_parts=["lumbar spine (L3-S1 stenosis)", "right shoulder (rotator cuff)", "right knee", "left hip"],
                icd10_codes=["M48.06", "M75.11", "M17.11", "M25.551"],
                description=(
                    "Cumulative trauma — lumbar stenosis (L3-S1), right shoulder rotator cuff tear "
                    "(post-surgical), right knee tricompartmental osteoarthritis, and left hip labral tear "
                    "from 30 years of repetitive heavy custodial work (mopping, lifting, pushing heavy "
                    "equipment, climbing ladders). AME rates combined impairment at 65% WPI; PDRS "
                    "schedule produces 78% PD. Applicant retains vocational expert (Dr. Sandra Mitchell, "
                    "PhD) who opines applicant is not amenable to vocational rehabilitation — 8th grade "
                    "education, limited English proficiency, 30 years manual labor only, combined work "
                    "restrictions preclude all substantial gainful employment. Applicant seeks Ogilvie "
                    "rebuttal of PDRS to establish 100% permanent total disability. Right shoulder "
                    "arthroscopy performed (prior)."
                ),
                mechanism="30 years of repetitive custodial work — mopping, lifting, pushing heavy equipment, climbing ladders",
            ),
        ],
        "treating": _make_physician("Patricia", "Gomez", "Orthopedic Surgery", "East LA Orthopedics", "Los Angeles", "90022"),
        "qme": _make_physician("Richard", "Chen", "Orthopedic Surgery", "California AME Group", "Los Angeles", "90048"),
        "prior_providers": [],
        "venue": "Los Angeles",
        "judge": "Hon. Sylvia M. Reyes",
        "extra_context": {
            "adj_number": "ADJ19123456",
            "wc_issues": ["benefits", "vocational", "apportionment"],
            "top_25_subcategories": ["#1 PD Rating Disputes", "#2 Apportionment"],
            "landmark_doctrine": "Ogilvie v. WCAB — PDRS Rebuttal / 100% PTD via Vocational Evidence",
            "educational_note": (
                "Ogilvie v. WCAB is the landmark case for rebutting the PDRS to establish 100% PTD. "
                "This is one of the highest-stakes disputes in WC — the difference between 78% PD "
                "(~$140,000) and 100% PTD (lifetime indemnity potentially exceeding $500,000). Tests "
                "the vocational evidence standard, DFEC methodology, and the intersection of age, "
                "education, and work restrictions. 8th-grade education, limited English, 30 years "
                "manual labor only — textbook Ogilvie rebuttal fact pattern."
            ),
            "ame_wpi": "65% combined WPI",
            "pdrs_rating": "78% PD (scheduled)",
            "ogilvie_rebuttal_target": "100% PTD",
            "vocational_expert": "Dr. Sandra Mitchell, PhD (Vocational Rehabilitation)",
            "vocational_barriers": ["8th-grade education (Mexico)", "Limited English proficiency", "No computer skills", "30 years manual labor only", "Combined restrictions preclude all SGE"],
            "employment_duration_years": 30,
        },
        "second_insurance": None,
    })

    scenarios.append({
        "internal_id": "BB-03",
        "case_params": CaseParameters(
            target_stage="settlement",
            claim_response="accepted",
            has_attorney=True,
            eval_type="ame",
            has_surgery=True,
            has_psych_component=False,
            has_ur_dispute=False,
            has_liens=False,
            num_body_parts=1,
            complexity="complex",
            injury_type="specific",
            body_part_category="upper_extremity",
        ),
        "applicant": _make_applicant("Kevin", "O'Brien", date(1980, 1, 1), "Los Angeles", "90007"),
        "employer": _make_employer(
            "Pacific Power & Electric Services, Inc.", "Journeyman Electrician",
            "Los Angeles", "90058", hire_date=_date_ago(365 * 18), hourly_rate=52.00,
            department="Commercial Installation",
        ),
        "insurance": _make_insurance("Travelers Insurance Company", "Lewis Brisbois Bisgaard & Smith LLP"),
        "injuries": [
            _make_injury(
                doi=date(2024, 11, 8),
                injury_type=InjuryType.SPECIFIC,
                body_parts=["left hand/wrist (CRPS Type I)"],
                icd10_codes=["G90.511"],
                description=(
                    "Specific injury — Complex Regional Pain Syndrome (CRPS) Type I, left upper extremity, "
                    "Budapest criteria confirmed. Left hand crushed between conduit pipe and concrete wall "
                    "during installation. AMA Guides 5th Edition Chapter 16 (Upper Extremity) underrates CRPS "
                    "because it captures only range-of-motion loss and grip strength deficits, not the "
                    "chronic pain, allodynia, temperature changes, and swelling that define CRPS. AME "
                    "invokes Almaraz/Guzman to use analogous impairment from Chapter 18 (Pain) for chronic "
                    "pain component and Chapter 13 (Vascular) for vascular dysfunction, arriving at "
                    "significantly higher combined WPI than straight Chapter 16 rating. Triple-phase bone "
                    "scan confirms CRPS. Treatment includes stellate ganglion blocks and mirror therapy."
                ),
                mechanism="Left hand crushed between conduit pipe and concrete wall during electrical installation",
            ),
        ],
        "treating": _make_physician("Alan", "Park", "Hand Surgery", "Southern California Hand Surgery Center", "Los Angeles", "90048"),
        "qme": _make_physician("Christine", "Delgado", "Physical Medicine & Rehabilitation", "California Pain Medicine AME", "Los Angeles", "90048"),
        "prior_providers": [],
        "venue": "Los Angeles",
        "judge": "Hon. Michael A. Stern",
        "extra_context": {
            "adj_number": "ADJ19234567",
            "wc_issues": ["benefits", "medical", "evidence_standards"],
            "top_25_subcategories": ["#1 PD Rating Disputes", "#6 QME/AME Report Disputes"],
            "landmark_doctrine": "Almaraz/Guzman — Alternative Impairment Rating Outside AMA Guides Chapter",
            "educational_note": (
                "Almaraz/Guzman is the foundational PD rating doctrine allowing physicians to rate outside "
                "the 'four corners' of the AMA Guides chapter corresponding to the injured body part. CRPS "
                "is the classic Almaraz/Guzman scenario because its hallmark features (pain, vascular "
                "dysfunction, temperature changes) are systematically underrated by standard upper extremity "
                "tables. This case demonstrates the multi-chapter analog approach: Chapter 18 (Pain) + "
                "Chapter 13 (Vascular) combined with Chapter 16 (Upper Extremity)."
            ),
            "crps_diagnosis_method": "Budapest criteria confirmed; triple-phase bone scan positive",
            "ama_guides_chapters_used": ["Chapter 16 (Upper Extremity — standard)", "Chapter 18 (Pain — analog)", "Chapter 13 (Vascular — analog)"],
            "almaraz_guzman_basis": "Standard Chapter 16 rating fails to capture allodynia, temperature changes, swelling, and chronic pain component",
            "treatment_history": "Stellate ganglion blocks, mirror therapy",
            "employment_duration_years": 18,
        },
        "second_insurance": None,
    })

    scenarios.append({
        "internal_id": "BB-04",
        "case_params": CaseParameters(
            target_stage="settlement",
            claim_response="accepted",
            has_attorney=True,
            eval_type="qme",
            has_surgery=False,
            has_psych_component=False,
            has_ur_dispute=False,
            has_liens=False,
            num_body_parts=2,
            complexity="standard",
            injury_type="cumulative_trauma",
            body_part_category="head",
        ),
        "applicant": _make_applicant("Rebecca", "Foster", date(1984, 1, 1), "Riverside", "92501"),
        "employer": _make_employer(
            "Riverside Unified School District", "High School English Teacher",
            "Riverside", "92501", hire_date=_date_ago(365 * 15), hourly_rate=36.00,
            department="English Department — Riverside High School",
        ),
        "insurance": _make_insurance("JUAB / Schools Insurance Program", "Yrulegui & Roberts"),
        "injuries": [
            _make_injury(
                doi=date(2025, 6, 30),
                injury_type=InjuryType.CUMULATIVE_TRAUMA,
                body_parts=["throat/vocal cords (bilateral vocal cord nodules)", "cervical spine (C5-C6)"],
                icd10_codes=["J38.1", "M54.12"],
                description=(
                    "Cumulative trauma — bilateral vocal cord nodules and C5-C6 cervical disc bulge from "
                    "15 years of daily 6-hour classroom lecturing and drama club coaching. QME rates at "
                    "22% PD with work restrictions (limited speaking to 2 hours/day, no sustained "
                    "lecturing). Employer offers modified work as curriculum developer (administrative/"
                    "curriculum development role with limited speaking). Applicant objects: offered "
                    "position is not 'regular, customary, or modified' work under LC 4658.7 because "
                    "curriculum development bears no resemblance to classroom teaching. Applicant demands "
                    "$6,000 SJDB voucher instead. Non-industrial voice coaching treatment 2 years prior "
                    "creates minor apportionment issue."
                ),
                mechanism="15 years of daily 6-hour classroom lecturing, drama club coaching, and sustained neck flexion while grading",
            ),
        ],
        "treating": _make_physician("Samantha", "Lee", "Otolaryngology/ENT", "Riverside ENT Associates", "Riverside", "92501"),
        "qme": _make_physician("Michael", "Chen", "Otolaryngology", "Inland Empire QME Panel", "Riverside", "92507"),
        "prior_providers": [],
        "venue": "Riverside",
        "judge": "Hon. Thomas B. Crawford",
        "extra_context": {
            "adj_number": "ADJ19345678",
            "wc_issues": ["vocational", "benefits", "return_to_work"],
            "top_25_subcategories": ["#13 SJDB Voucher Entitlement", "#12 Return to Work / Modified Duty"],
            "landmark_doctrine": "LC 4658.7 — What Constitutes 'Regular, Customary, or Modified' Work for SJDB Voucher Purposes",
            "educational_note": (
                "SJDB voucher disputes are among the most common post-SB 863 issues. The central question "
                "— what constitutes 'regular, customary, or modified' work — is highly fact-specific and "
                "frequently litigated. This case tests the boundary between a legitimate modified position "
                "and an employer trying to avoid the $6,000 voucher by offering a fundamentally different "
                "job. Key argument: curriculum development bears no resemblance to classroom teaching."
            ),
            "pd_rating": "22% PD",
            "qme_restrictions": "Limited speaking to 2 hours/day; no sustained lecturing",
            "modified_work_offered": "Curriculum development/administrative role — limited speaking requirement",
            "applicant_objection": "Curriculum development is a fundamentally different job, not modified teaching",
            "sjdb_voucher_amount": 6000,
            "prior_non_industrial_treatment": "Voice coaching 2 years prior (non-industrial, self-pay)",
            "employment_duration_years": 15,
        },
        "second_insurance": None,
    })

    scenarios.append({
        "internal_id": "BB-05",
        "case_params": CaseParameters(
            target_stage="resolved",
            claim_response="accepted",
            has_attorney=True,
            eval_type="qme",
            resolution_type="stipulations",
            has_surgery=False,
            has_psych_component=False,
            has_ur_dispute=False,
            has_liens=False,
            num_body_parts=1,
            complexity="standard",
            injury_type="specific",
            body_part_category="upper_extremity",
        ),
        "applicant": _make_applicant("Daniel", "Park", date(1986, 1, 1), "Los Angeles", "90040"),
        "employer": _make_employer(
            "Precision Machining Solutions, LLC", "CNC Machine Operator",
            "City of Industry", "91748", hire_date=_date_ago(365 * 8), hourly_rate=28.00,
            department="CNC Production — Lathe Division",
        ),
        "insurance": _make_insurance("Zurich North America", "Carothers DiSante & Freudenberger LLP"),
        "injuries": [
            _make_injury(
                doi=date(2025, 3, 5),
                injury_type=InjuryType.SPECIFIC,
                body_parts=["right wrist (scapholunate ligament tear)"],
                icd10_codes=["S63.501A"],
                description=(
                    "Specific injury — right wrist scapholunate ligament tear from right wrist caught in "
                    "CNC lathe guard mechanism. Claim accepted; applicant returns to modified work at same "
                    "employer (no repetitive gripping, no lifting over 10 lbs with right hand) at full-time "
                    "hours but reduced duties. PD stipulated at 18%. Dispute centers on LC 4658.7 adjustment: "
                    "carrier argues 15% PD decrease applies (returned to same employer within 60 days); "
                    "applicant argues 15% PD increase applies because modified position pays $4/hour less "
                    "than pre-injury CNC operator rate due to reduced duties. Case resolved via Stipulations "
                    "with Request for Award; LC 4658.7 adjustment remains contested."
                ),
                mechanism="Right wrist caught in CNC lathe guard mechanism during operation",
            ),
        ],
        "treating": _make_physician("Lisa", "Wang", "Hand Surgery", "San Gabriel Valley Hand Surgery", "Alhambra", "91801"),
        "qme": _make_physician("Robert", "Martinez", "Orthopedic Surgery", "East LA QME Associates", "Monterey Park", "91754"),
        "prior_providers": [],
        "venue": "Los Angeles",
        "judge": "Hon. Nancy B. Chen",
        "extra_context": {
            "adj_number": "ADJ19456789",
            "wc_issues": ["return_to_work", "benefits", "vocational"],
            "top_25_subcategories": ["#12 Return to Work / Modified Duty", "#1 PD Rating Disputes", "#13 SJDB Voucher"],
            "landmark_doctrine": "LC 4658.7 — 15% PD Increase vs. Decrease (Returned to Work, Reduced Wages)",
            "educational_note": (
                "LC 4658.7 adjustments affect the PD award in every case where the applicant returns to "
                "work. The 15% increase/decrease is a significant modifier. This case tests the nuance: "
                "the applicant technically returned to work (triggering the potential decrease), but at "
                "reduced pay of $4/hour less (arguably triggering the increase). A common real-world "
                "dispute resolved here via Stipulations, with the adjustment issue preserved."
            ),
            "pd_stipulated": "18% PD",
            "pre_injury_rate": "$28.00/hour",
            "post_injury_modified_rate": "$24.00/hour (reduced duties)",
            "wage_reduction": "$4.00/hour",
            "lc_4658_7_dispute": "Carrier: 15% decrease (returned to same employer within 60 days); Applicant: 15% increase (reduced wages)",
            "resolution_type_detail": "Stipulations with Request for Award — 18% PD base, LC 4658.7 adjustment disputed",
            "employment_duration_years": 8,
        },
        "second_insurance": None,
    })

    scenarios.append({
        "internal_id": "BB-06",
        "case_params": CaseParameters(
            target_stage="settlement",
            claim_response="accepted",
            has_attorney=True,
            eval_type="none",
            resolution_type="pending",
            has_surgery=False,
            has_psych_component=False,
            has_ur_dispute=False,
            has_liens=True,
            num_body_parts=1,
            complexity="complex",
            injury_type="death",
            body_part_category="internal",
        ),
        "applicant": _make_applicant("Maria", "Mendoza", date(1982, 1, 1), "Los Angeles", "90023"),
        "employer": _make_employer(
            "Southwest Construction Group, Inc.", "Construction Foreman",
            "Los Angeles", "90021", hire_date=_date_ago(365 * 18), hourly_rate=42.00,
            department="Site Supervision",
        ),
        "insurance": _make_insurance("ICW Group Insurance Companies", "Baradat & Paboojian"),
        "injuries": [
            _make_injury(
                doi=date(2025, 7, 18),
                injury_type=InjuryType.SPECIFIC,
                body_parts=["internal — exertional heat stroke (fatal)"],
                icd10_codes=["T67.0XXA"],
                description=(
                    "Death claim — Carlos Mendoza, age 45, Construction Foreman. Deceased collapsed from "
                    "exertional heat stroke at outdoor construction site (ambient temperature 112F) at 2 PM "
                    "on 2025-07-18, pronounced dead at hospital. Multiple dependency claimants: (1) Maria "
                    "Mendoza (estranged wife, separated 2 years, no divorce decree) — claims total "
                    "dependency as surviving spouse under LC 4701; (2) Carlos Jr. (age 15), Sofia (age 12) "
                    "— children of marriage; (3) Diego (age 8, different mother/ex-girlfriend) — child from "
                    "separate relationship; (4) Rosa Mendoza (mother, age 72, lived with deceased, "
                    "financially supported by deceased) — claims partial dependency under LC 4703. "
                    "Carrier disputes mother's dependency status and allocation of death benefits among "
                    "multiple claimants. Hospital lien claims on file. Total death benefit at issue: $320,000+."
                ),
                mechanism="Exertional heat stroke — outdoor construction site, 112F ambient temperature, July 18, 2025",
            ),
        ],
        "treating": _make_physician("County", "Coroner", "Forensic Pathology", "Los Angeles County Department of Medical Examiner-Coroner", "Los Angeles", "90073"),
        "qme": None,
        "prior_providers": [],
        "venue": "Los Angeles",
        "judge": "Hon. Antonio R. Gutierrez",
        "extra_context": {
            "adj_number": "ADJ19567890",
            "wc_issues": ["death_benefits", "benefits", "settlements"],
            "top_25_subcategories": ["#23 Future Medical Care", "#10 Settlement Disputes"],
            "landmark_doctrine": "LC 4700-4707 — Death Benefits, Multiple Dependency Claimants, Total vs. Partial Dependency",
            "educational_note": (
                "Death benefits with dependency disputes are among the most complex and emotionally charged "
                "cases in WC. This fact pattern forces resolution of: (1) estranged-spouse total dependency "
                "under LC 4701 (separated but not divorced), (2) partial dependency of a parent under "
                "LC 4703 (financial support evidence required), (3) benefits for a child from a different "
                "relationship, and (4) allocation of the $320,000+ death benefit among competing claimants."
            ),
            "deceased": {
                "name": "Carlos Mendoza",
                "age": 45,
                "occupation": "Construction Foreman",
                "employer_tenure_years": 18,
            },
            "dependency_claimants": [
                {"name": "Maria Mendoza", "relationship": "Estranged wife (separated 2 years, no divorce)", "claim_type": "Total dependency — LC 4701"},
                {"name": "Carlos Jr.", "age": 15, "relationship": "Child of marriage"},
                {"name": "Sofia", "age": 12, "relationship": "Child of marriage"},
                {"name": "Diego", "age": 8, "relationship": "Child, different mother (ex-girlfriend)", "claim_type": "Benefits via biological mother"},
                {"name": "Rosa Mendoza", "age": 72, "relationship": "Mother (lived with deceased, financially supported)", "claim_type": "Partial dependency — LC 4703"},
            ],
            "death_benefit_at_issue": "$320,000+",
            "cal_osha_status": "Employer heat illness prevention plan compliance under investigation; potential Cal/OSHA citation",
            "hospital_lien": True,
            "burial_expense_claim": "LC 4701 burial expense claim included",
        },
        "second_insurance": None,
    })

    scenarios.append({
        "internal_id": "BB-07",
        "case_params": CaseParameters(
            target_stage="medical_legal",
            claim_response="accepted",
            has_attorney=True,
            eval_type="ame",
            has_surgery=False,
            has_psych_component=False,
            has_ur_dispute=False,
            has_liens=False,
            num_body_parts=2,
            complexity="complex",
            injury_type="specific",
            body_part_category="spine",
        ),
        "applicant": _make_applicant("Raymond", "Jackson", date(1975, 1, 1), "Los Angeles", "90011"),
        "employer": _make_employer(
            "National Distribution Centers, Inc.", "Warehouse Worker",
            "Commerce", "90040", hire_date=_date_ago(365 * 12), hourly_rate=21.50,
            department="Shipping & Receiving",
        ),
        "insurance": _make_insurance("Employers Holdings, Inc.", "Manning & Kass, Ellrod, Ramirez, Trester LLP"),
        "injuries": [
            _make_injury(
                doi=date(2025, 2, 20),
                injury_type=InjuryType.SPECIFIC,
                body_parts=["lumbar spine (L4-L5 herniation, L5-S1 broad-based bulge)"],
                icd10_codes=["M51.16", "M51.17", "Z89.512"],
                description=(
                    "Specific injury — lumbar spine L4-L5 disc herniation and L5-S1 broad-based bulge "
                    "from forklift collision (struck from behind in shipping lane). Pre-existing condition: "
                    "left below-knee amputation (Z89.512) from childhood pedestrian accident (age 7), "
                    "uses prosthetic, fully functional in warehouse setting for 12 years. AME (Dr. Barbara "
                    "Collins) rates industrial back injury at 25% WPI. Applicant files SIBTF application "
                    "under LC 4751 — combined disability from pre-existing amputation and industrial back "
                    "injury arguably exceeds 70% threshold. SIBTF contests: (1) insufficient documentation "
                    "of pre-existing disability, (2) combined disability does not meet 70% threshold, and "
                    "(3) employer had knowledge of amputation at time of hire (knowledge defense). "
                    "SIBTF Medical Evaluator Dr. Howard Stern, MD, assessing combined disability."
                ),
                mechanism="Struck from behind by forklift in shipping lane during active warehouse work",
            ),
        ],
        "treating": _make_physician("Gregory", "Tanaka", "Physical Medicine & Rehabilitation", "East LA PM&R Group", "Los Angeles", "90022"),
        "qme": _make_physician("Barbara", "Collins", "Orthopedic Surgery", "California SIBTF AME Panel", "Los Angeles", "90048"),
        "prior_providers": [
            _make_physician("Howard", "Stern", "Orthopedic Surgery", "SIBTF Medical Evaluator Panel", "Los Angeles", "90048"),
        ],
        "venue": "Los Angeles",
        "judge": "Hon. Elizabeth M. Park",
        "extra_context": {
            "adj_number": "ADJ19678901",
            "wc_issues": ["subsequent_injury", "benefits", "apportionment"],
            "top_25_subcategories": ["#2 Apportionment", "#1 PD Rating Disputes"],
            "landmark_doctrine": "SIBTF — LC 4751 Subsequent Injuries Benefits Trust Fund (70% Combined Threshold)",
            "educational_note": (
                "SIBTF claims are a specialty niche — most WC attorneys handle only a handful in their "
                "career. The fund provides additional benefits when a pre-existing disability combines "
                "with an industrial injury to create disproportionately greater disability. This case "
                "tests the 70% combined threshold, pre-existing documentation requirements, and SIBTF's "
                "knowledge defense. High educational value: a 12-year functional work history with "
                "prosthetic is strong evidence against SIBTF's knowledge defense."
            ),
            "pre_existing_condition": "Left below-knee amputation (age 7, pedestrian vs. auto accident)",
            "pre_existing_icd10": "Z89.512",
            "prosthetic_use": True,
            "industrial_wpi": "25% WPI (lumbar spine — AME Dr. Barbara Collins)",
            "combined_disability_threshold": "70% required under LC 4751",
            "sibtf_defenses": [
                "Insufficient documentation of pre-existing disability",
                "Combined disability does not meet 70% threshold",
                "Employer had knowledge of amputation at hire (knowledge defense)",
            ],
            "employer_knowledge_evidence": "Employment application and physical exam at hire — amputation visible/documented for 12 years",
            "sibtf_evaluator": "Dr. Howard Stern, MD (Orthopedic Surgery) — combined disability assessment",
            "employment_duration_years": 12,
        },
        "second_insurance": None,
    })


    # --- Group C: Medical Treatment (CM-01 through CM-06) ---

    scenarios.append({
        "internal_id": "CM-01",
        "case_params": CaseParameters(
            target_stage="active_treatment",
            claim_response="accepted",
            has_attorney=True,
            eval_type="none",
            has_surgery=False,
            has_psych_component=False,
            has_ur_dispute=True,
            has_liens=False,
            num_body_parts=1,
            complexity="standard",
            injury_type="specific",
            body_part_category="spine",
            resolution_type="random",
        ),
        "applicant": _make_applicant("Frank", "Morrison", date(1977, 6, 15), city="Los Angeles", zipcode="90001"),
        "employer": _make_employer(
            "Continental Freight Lines, Inc.",
            "Long-haul truck driver",
            city="Los Angeles",
            zipcode="90012",
            hire_date=_date_ago(14 * 365),
            hourly_rate=32.00,
            department="Transportation",
        ),
        "insurance": _make_insurance(),
        "injuries": [
            _make_injury(
                doi=date(2024, 6, 15),
                injury_type=InjuryType.SPECIFIC,
                body_parts=["Lumbar spine (L4-L5, L5-S1)"],
                icd10_codes=["M51.16", "M54.17"],
                description="L4-L5 disc herniation and L5-S1 herniation with left-sided radiculopathy after lifting heavy cargo strap",
                mechanism="Lifted heavy cargo strap, felt immediate low back pain with radiation to left leg",
            )
        ],
        "treating": _make_physician("Anthony", "Russo", "Orthopedic Spine Surgery", "Los Angeles Spine Center", city="Los Angeles", zipcode="90048"),
        "qme": None,
        "prior_providers": [],
        "venue": "Los Angeles",
        "judge": "Hon. Patricia Nguyen",
        "extra_context": {
            "wc_issues": ["utilization_review", "IMR_appeal", "UR_procedural_deficiency", "surgery_authorization", "LC_4610_timeline", "specialty_mismatch"],
            "educational_notes": (
                "Tests the complete UR to IMR to WCAB challenge chain — the most common medical dispute pathway in CA WC since SB 863. "
                "Two procedural deficiency arguments: (1) UR reviewer not competent in same specialty as requesting physician per LC 4610(e)(3); "
                "(2) UR decision issued beyond the statutory timeline."
            ),
        },
        "second_insurance": None,
    })

    scenarios.append({
        "internal_id": "CM-02",
        "case_params": CaseParameters(
            target_stage="active_treatment",
            claim_response="accepted",
            has_attorney=True,
            eval_type="none",
            has_surgery=False,
            has_psych_component=False,
            has_ur_dispute=True,
            has_liens=False,
            num_body_parts=2,
            complexity="standard",
            injury_type="cumulative_trauma",
            body_part_category="upper_extremity",
            resolution_type="random",
        ),
        "applicant": _make_applicant("Gloria", "Castillo", date(1969, 8, 1), city="Los Angeles", zipcode="90001"),
        "employer": _make_employer(
            "Grand Pacific Resort & Spa",
            "Hotel housekeeper",
            city="Los Angeles",
            zipcode="90012",
            hire_date=_date_ago(20 * 365),
            hourly_rate=22.50,
            department="Housekeeping",
        ),
        "insurance": _make_insurance(),
        "injuries": [
            _make_injury(
                doi=date(2023, 8, 1),
                injury_type=InjuryType.CUMULATIVE_TRAUMA,
                body_parts=["Bilateral shoulders"],
                icd10_codes=["M75.10", "M75.11"],
                description="Bilateral rotator cuff tendinopathy and bilateral shoulder impingement from 20 years of repetitive overhead hotel housekeeping work",
                mechanism="20 years of repetitive overhead work — making beds, cleaning bathrooms, lifting linens",
            )
        ],
        "treating": _make_physician("Priya", "Sharma", "PM&R/Pain Medicine", "Pacific Rehabilitation Medical Group", city="Los Angeles", zipcode="90048"),
        "qme": None,
        "prior_providers": [],
        "venue": "Los Angeles",
        "judge": "Hon. Michael Torres",
        "extra_context": {
            "wc_issues": ["utilization_review", "IMR_reversal", "carrier_non_compliance", "opioid_medication_authorization", "LC_5814_penalty"],
            "educational_notes": (
                "Demonstrates the IMR reversal pathway (UR wrong, IMR corrects it) combined with carrier non-compliance penalties. "
                "Even after IMR overturns the UR denial, carrier delayed implementation for 4 months."
            ),
        },
        "second_insurance": None,
    })

    scenarios.append({
        "internal_id": "CM-03",
        "case_params": CaseParameters(
            target_stage="medical_legal",
            claim_response="delayed",
            has_attorney=True,
            eval_type="qme",
            has_surgery=False,
            has_psych_component=False,
            has_ur_dispute=False,
            has_liens=False,
            num_body_parts=1,
            complexity="standard",
            injury_type="specific",
            body_part_category="upper_extremity",
            resolution_type="random",
        ),
        "applicant": _make_applicant("Travis", "Miller", date(1989, 8, 28), city="Bakersfield", zipcode="93301"),
        "employer": _make_employer(
            "Valley Plumbing & Heating, Inc.",
            "Journeyman plumber",
            city="Bakersfield",
            zipcode="93301",
            hire_date=_date_ago(9 * 365),
            hourly_rate=42.00,
            department="Field Operations",
        ),
        "insurance": _make_insurance(),
        "injuries": [
            _make_injury(
                doi=date(2025, 8, 28),
                injury_type=InjuryType.SPECIFIC,
                body_parts=["Right shoulder"],
                icd10_codes=["S43.431A"],
                description="Superior labral tear (SLAP lesion) of the right shoulder during overhead pipe installation",
                mechanism="Overhead pipe installation, felt right shoulder pop while torquing fitting",
            )
        ],
        "treating": _make_physician("Mark", "Jensen", "Orthopedic Surgery", "Bakersfield Orthopedic Group", city="Bakersfield", zipcode="93301"),
        "qme": _make_physician("Panel", "Disputed", "Orthopedic Surgery", "San Francisco Medical Group (disputed)", city="San Francisco", zipcode="94102"),
        "prior_providers": [],
        "venue": "Bakersfield",
        "judge": "Hon. Sandra Flores",
        "extra_context": {
            "wc_issues": ["QME_panel_dispute", "geographic_hardship", "CCR_31.3_replacement_panel", "LC_4062.2_panel_selection"],
            "educational_notes": (
                "QME panel disputes are the procedural backbone of the medical-legal phase. "
                "CCR 31.3 allows replacement panel requests for geographic hardship when all QMEs are located more than a specified distance from the applicant."
            ),
        },
        "second_insurance": None,
    })

    scenarios.append({
        "internal_id": "CM-04",
        "case_params": CaseParameters(
            target_stage="medical_legal",
            claim_response="accepted",
            has_attorney=True,
            eval_type="ame",
            has_surgery=False,
            has_psych_component=False,
            has_ur_dispute=False,
            has_liens=False,
            num_body_parts=2,
            complexity="complex",
            injury_type="cumulative_trauma",
            body_part_category="spine",
            resolution_type="random",
        ),
        "applicant": _make_applicant("Laura", "Bennett", date(1976, 5, 15), city="Los Angeles", zipcode="90025"),
        "employer": _make_employer(
            "Bright Smiles Dental Group",
            "Dental hygienist",
            city="Los Angeles",
            zipcode="90025",
            hire_date=_date_ago(17 * 365),
            hourly_rate=45.00,
            department="Clinical",
        ),
        "insurance": _make_insurance(),
        "injuries": [
            _make_injury(
                doi=date(2025, 5, 15),
                injury_type=InjuryType.CUMULATIVE_TRAUMA,
                body_parts=["Cervical spine (C4-C7)", "Thoracic spine (T6-T7)"],
                icd10_codes=["M50.12", "M51.14"],
                description="Multilevel cervical disc disease (C4-C7) and thoracic disc protrusion (T6-T7) from 17 years of sustained awkward posture over dental patients",
                mechanism="17 years of sustained awkward posture (leaning over patients), repetitive hand and arm motions during dental procedures",
            )
        ],
        "treating": _make_physician("Jennifer", "Kim", "PM&R", "Westside Physical Medicine & Rehabilitation", city="Los Angeles", zipcode="90025"),
        "qme": _make_physician("Harold", "Steinberg", "Orthopedic Surgery", "Southern California Medical Legal Group", city="Los Angeles", zipcode="90048"),
        "prior_providers": [],
        "venue": "Los Angeles",
        "judge": "Hon. Robert Alvarez",
        "extra_context": {
            "wc_issues": ["AME_ex_parte_violation", "LC_4062.3_ex_parte_prohibition", "motion_to_strike_AME_report", "evidence_standards"],
            "educational_notes": (
                "Ex parte communication with an AME is a serious procedural violation that can result in the entire AME report being stricken. "
                "LC 4062.3 strictly prohibits ex parte communication with the AME."
            ),
        },
        "second_insurance": None,
    })

    scenarios.append({
        "internal_id": "CM-05",
        "case_params": CaseParameters(
            target_stage="active_treatment",
            claim_response="accepted",
            has_attorney=True,
            eval_type="none",
            has_surgery=False,
            has_psych_component=False,
            has_ur_dispute=True,
            has_liens=False,
            num_body_parts=1,
            complexity="complex",
            injury_type="specific",
            body_part_category="upper_extremity",
            resolution_type="random",
        ),
        "applicant": _make_applicant("Stephanie", "Chang", date(1985, 4, 10), city="Los Angeles", zipcode="90034"),
        "employer": _make_employer(
            "Iron Valley Fitness, LLC",
            "CrossFit coach and personal trainer",
            city="Los Angeles",
            zipcode="90034",
            hire_date=_date_ago(7 * 365),
            hourly_rate=35.00,
            department="Training",
        ),
        "insurance": _make_insurance(),
        "injuries": [
            _make_injury(
                doi=date(2025, 4, 10),
                injury_type=InjuryType.SPECIFIC,
                body_parts=["Right shoulder"],
                icd10_codes=["M75.11"],
                description="Partial-thickness supraspinatus tear of the right shoulder while demonstrating overhead snatch movement",
                mechanism="Demonstrating overhead snatch movement during coaching session, felt right shoulder tear",
            )
        ],
        "treating": _make_physician("Andrew", "Patel", "Orthopedic Sports Medicine", "LA Sports Medicine & Orthopedics", city="Los Angeles", zipcode="90048"),
        "qme": None,
        "prior_providers": [],
        "venue": "Los Angeles",
        "judge": "Hon. Lisa Chen",
        "extra_context": {
            "wc_issues": ["utilization_review", "MTUS_guidelines_challenge", "evidence_based_medicine_exception", "PRP_therapy_authorization"],
            "educational_notes": (
                "Tests the boundary between MTUS guideline adherence and evidence-based medicine exceptions. "
                "LC 5307.27 and CCR 9792.21 establish MTUS as the standard of care; deviations require WCAB order."
            ),
        },
        "second_insurance": None,
    })

    scenarios.append({
        "internal_id": "CM-06",
        "case_params": CaseParameters(
            target_stage="active_treatment",
            claim_response="accepted",
            has_attorney=True,
            eval_type="none",
            has_surgery=False,
            has_psych_component=False,
            has_ur_dispute=False,
            has_liens=False,
            num_body_parts=1,
            complexity="standard",
            injury_type="specific",
            body_part_category="upper_extremity",
            resolution_type="random",
        ),
        "applicant": _make_applicant("Emily", "Nakamura", date(1992, 9, 1), city="Los Angeles", zipcode="90001"),
        "employer": _make_employer(
            "Pacific Claims Processing, Inc.",
            "Data entry clerk",
            city="Los Angeles",
            zipcode="90012",
            hire_date=_date_ago(4 * 365),
            hourly_rate=20.00,
            department="Data Operations",
        ),
        "insurance": _make_insurance(),
        "injuries": [
            _make_injury(
                doi=date(2025, 9, 1),
                injury_type=InjuryType.SPECIFIC,
                body_parts=["Right wrist/hand"],
                icd10_codes=["G56.01"],
                description="Right carpal tunnel syndrome from repetitive keyboard use 8 hours per day with minimal breaks",
                mechanism="Repetitive keyboard use, 8 hours/day, minimal breaks over 4 years of data entry work",
            )
        ],
        "treating": _make_physician("Rachel", "Torres", "Orthopedic Surgery/Hand", "Southern California Hand & Upper Extremity Center", city="Los Angeles", zipcode="90048"),
        "qme": None,
        "prior_providers": [],
        "venue": "Los Angeles",
        "judge": "Hon. James Park",
        "extra_context": {
            "wc_issues": ["routine_medical_treatment", "modified_duty", "conservative_care"],
            "educational_notes": (
                "Baseline routine case — no disputes, no complexity. Carpal tunnel syndrome (G56.01) is among the most common occupational injuries."
            ),
        },
        "second_insurance": None,
    })


    # --- Group D: Psychiatric Claims (DP-01 through DP-03) ---

    scenarios.append({
        "internal_id": "DP-01",
        "case_params": CaseParameters(
            target_stage="discovery",
            claim_response="denied",
            has_attorney=True,
            eval_type="qme",
            has_surgery=False,
            has_psych_component=True,
            has_ur_dispute=False,
            has_liens=False,
            num_body_parts=1,
            complexity="complex",
            injury_type="specific",
            body_part_category="psyche",
            resolution_type="random",
        ),
        "applicant": _make_applicant("Jordan", "Reeves", date(1999, 10, 5), city="Los Angeles", zipcode="90028"),
        "employer": _make_employer(
            "NovaTech Solutions, Inc.",
            "Software developer",
            city="Los Angeles",
            zipcode="90028",
            hire_date=_date_ago(4 * 30),
            hourly_rate=55.00,
            department="Engineering",
        ),
        "insurance": _make_insurance(),
        "injuries": [
            _make_injury(
                doi=date(2025, 10, 5),
                injury_type=InjuryType.SPECIFIC,
                body_parts=["Psyche"],
                icd10_codes=["F43.10", "F41.1"],
                description="PTSD and generalized anxiety disorder following credible workplace violence threat from coworker",
                mechanism="Coworker made credible direct threat to 'shoot up the office,' overheard by applicant and several other employees",
            )
        ],
        "treating": _make_physician("Maria", "Santos", "Clinical Psychology", "Westside Psychology Group", city="Los Angeles", zipcode="90025"),
        "qme": _make_physician("David", "Greenfield", "Psychiatry", "Southern California Psychiatric Medical Group", city="Los Angeles", zipcode="90048"),
        "prior_providers": [],
        "venue": "Los Angeles",
        "judge": "Hon. Angela Kim",
        "extra_context": {
            "wc_issues": ["LC_3208.3_psychiatric_threshold", "six_month_employment_bar", "sudden_extraordinary_employment_condition_exception", "workplace_violence"],
            "landmark_doctrines": ["LC 3208.3 — six-month employment bar and sudden/extraordinary exception"],
            "educational_notes": (
                "Tests the LC 3208.3(d) six-month employment bar — a threshold defense unique to psychiatric claims in CA WC. "
                "Employees with fewer than 6 months of service cannot file psychiatric claims UNLESS the injury arises from a 'sudden and extraordinary employment condition.'"
            ),
        },
        "second_insurance": None,
    })

    scenarios.append({
        "internal_id": "DP-02",
        "case_params": CaseParameters(
            target_stage="medical_legal",
            claim_response="denied",
            has_attorney=True,
            eval_type="qme",
            has_surgery=False,
            has_psych_component=True,
            has_ur_dispute=False,
            has_liens=False,
            num_body_parts=1,
            complexity="complex",
            injury_type="cumulative_trauma",
            body_part_category="psyche",
            resolution_type="random",
        ),
        "applicant": _make_applicant("Diane", "Crawford", date(1973, 9, 1), city="Los Angeles", zipcode="90017"),
        "employer": _make_employer(
            "Pacific Western Bank",
            "Bank branch manager",
            city="Los Angeles",
            zipcode="90017",
            hire_date=_date_ago(18 * 365),
            hourly_rate=48.00,
            department="Branch Management",
        ),
        "insurance": _make_insurance(),
        "injuries": [
            _make_injury(
                doi=date(2025, 9, 1),
                injury_type=InjuryType.CUMULATIVE_TRAUMA,
                body_parts=["Psyche"],
                icd10_codes=["F33.2"],
                description="Major depressive disorder, recurrent severe, from cumulative work stressors including PIP, denied promotion, and involuntary transfer",
                mechanism="Cumulative work stressors: PIP, denied promotion to regional manager, involuntary transfer, perceived retaliation",
            )
        ],
        "treating": _make_physician("Robert", "Chen", "Psychiatry", "Downtown LA Psychiatric Associates", city="Los Angeles", zipcode="90017"),
        "qme": _make_physician("Alison", "Grant", "Psychiatry", "Southern California Psychiatric Medical Legal Group", city="Los Angeles", zipcode="90048"),
        "prior_providers": [],
        "venue": "Los Angeles",
        "judge": "Hon. Thomas Washington",
        "extra_context": {
            "wc_issues": ["LC_3208.3_predominant_cause", "good_faith_personnel_action_defense", "psychiatric_injury", "cumulative_trauma"],
            "landmark_doctrines": ["LC 3208.3 — good faith personnel action defense"],
            "educational_notes": (
                "The good faith personnel action (GFPA) defense under LC 3208.3(h) is the most commonly raised defense in psychiatric claims."
            ),
        },
        "second_insurance": None,
    })

    scenarios.append({
        "internal_id": "DP-03",
        "case_params": CaseParameters(
            target_stage="settlement",
            claim_response="accepted",
            has_attorney=True,
            eval_type="ame",
            has_surgery=True,
            has_psych_component=True,
            has_ur_dispute=False,
            has_liens=True,
            num_body_parts=3,
            complexity="complex",
            injury_type="specific",
            body_part_category="spine",
            resolution_type="random",
        ),
        "applicant": _make_applicant("Victor", "Ramirez", date(1979, 3, 15), city="Los Angeles", zipcode="90001"),
        "employer": _make_employer(
            "Valley Auto Center, Inc.",
            "Auto mechanic",
            city="Los Angeles",
            zipcode="90012",
            hire_date=_date_ago(15 * 365),
            hourly_rate=30.00,
            department="Automotive Repair",
        ),
        "insurance": _make_insurance(),
        "injuries": [
            _make_injury(
                doi=date(2021, 3, 15),
                injury_type=InjuryType.SPECIFIC,
                body_parts=["Lumbar spine (L3-S1)", "Psyche", "Sleep"],
                icd10_codes=["M96.1", "F33.1", "F41.1", "G47.00"],
                description=(
                    "Post-laminectomy syndrome (L3-S1, 3 failed surgeries) with consequential major depressive disorder, "
                    "generalized anxiety disorder, and chronic insomnia secondary to 4 years of chronic unrelenting pain"
                ),
                mechanism=(
                    "Original: hydraulic lift failure dropped car onto mechanic bay, applicant struck by falling debris. "
                    "Consequential psychiatric: 4 years of chronic pain, 3 failed back surgeries, permanent disability"
                ),
            )
        ],
        "treating": _make_physician("James", "Sullivan", "Orthopedic Spine Surgery", "Valley Spine & Orthopedic Center", city="Los Angeles", zipcode="90048"),
        "qme": _make_physician("Lawrence", "Tan", "Orthopedic Surgery", "Southern California Medical Legal Group", city="Los Angeles", zipcode="90048"),
        "prior_providers": [
            _make_physician("Catherine", "Park", "Clinical Psychology", "Westside Psychology & Counseling", city="Los Angeles", zipcode="90025"),
        ],
        "venue": "Los Angeles",
        "judge": "Hon. Diana Morales",
        "extra_context": {
            "wc_issues": ["consequential_psychiatric_injury", "compensable_consequence_doctrine", "PD_rating_disputes", "apportionment", "medical_liens"],
            "landmark_doctrines": ["Compensable consequence doctrine", "LC 4664 prior award apportionment"],
            "educational_notes": (
                "Consequential psychiatric claims are extremely common in chronic pain cases. "
                "When psychiatric injury flows from an accepted physical injury (compensable consequence), "
                "LC 3208.3's 'predominant cause' standard does NOT apply."
            ),
        },
        "second_insurance": None,
    })


    # --- Group E: Procedure & Practice (EP-01 through EP-05) ---

    scenarios.append({
        "internal_id": "EP-01",
        "case_params": CaseParameters(
            target_stage="medical_legal",
            claim_response="delayed",
            has_attorney=True,
            eval_type="qme",
            has_surgery=False,
            has_psych_component=False,
            has_ur_dispute=False,
            has_liens=False,
            num_body_parts=2,
            complexity="standard",
            injury_type="specific",
            body_part_category="spine",
            resolution_type="random",
        ),
        "applicant": _make_applicant("Christopher", "Wells", date(1981, 3, 15), city="Los Angeles", zipcode="90001"),
        "employer": _make_employer(
            "American Supply Chain Corp.",
            "Warehouse Supervisor",
            city="Los Angeles",
            zipcode="90058",
            hire_date=_date_ago(365 * 10),
            hourly_rate=32.00,
            department="Warehouse Operations",
        ),
        "insurance": _make_insurance("Zurich American Insurance Company", "Bradford & Barthel LLP"),
        "injuries": [
            _make_injury(
                doi=date(2025, 5, 22),
                injury_type=InjuryType.SPECIFIC,
                body_parts=["Cervical Spine (C5-C6)", "Right Shoulder"],
                icd10_codes=["M50.12", "M75.11"],
                description="Overhead inventory shelf collapsed onto applicant's neck and right shoulder causing C5-C6 disc herniation and right shoulder impingement syndrome",
                mechanism="Overhead inventory shelf collapsed onto applicant",
            ),
        ],
        "treating": _make_physician("Paul", "Anderson", "Physical Medicine & Rehabilitation", "Los Angeles Rehabilitation Medicine Group", city="Los Angeles", zipcode="90048"),
        "qme": _make_physician("Nancy", "Schmidt", "Orthopedic Surgery", "Pacific QME Panel Associates", city="Los Angeles", zipcode="90017"),
        "prior_providers": [],
        "venue": "Los Angeles",
        "judge": "Hon. Patricia Hensley",
        "extra_context": {
            "wc_issues": ["evidence_standards", "medical_report_admissibility", "qme_ame_report_disputes", "telehealth_examination"],
            "educational_notes": (
                "Telehealth evidence standards emerged from COVID-era emergency orders. "
                "LC 4628 requires a meaningful physical examination for orthopedic evaluations."
            ),
        },
        "second_insurance": None,
    })

    scenarios.append({
        "internal_id": "EP-02",
        "case_params": CaseParameters(
            target_stage="resolved",
            claim_response="accepted",
            has_attorney=True,
            eval_type="ame",
            has_surgery=True,
            has_psych_component=False,
            has_ur_dispute=False,
            has_liens=False,
            num_body_parts=2,
            complexity="complex",
            injury_type="cumulative_trauma",
            body_part_category="spine",
            resolution_type="trial",
        ),
        "applicant": _make_applicant("William", "Thompson", date(1974, 6, 20), city="Los Angeles", zipcode="90001"),
        "employer": _make_employer(
            "Pacific Steel Erectors, Inc.",
            "Iron Worker",
            city="Los Angeles",
            zipcode="90021",
            hire_date=_date_ago(365 * 25),
            hourly_rate=52.00,
            department="Structural Steel",
        ),
        "insurance": _make_insurance("ICW Group Insurance Companies", "Laughlin, Falbo, Levy & Moresi LLP"),
        "injuries": [
            _make_injury(
                doi=date(2024, 12, 1),
                injury_type=InjuryType.CUMULATIVE_TRAUMA,
                body_parts=["Cervical Spine (C4-C7)", "Lumbar Spine (L3-S1)"],
                icd10_codes=["M47.12", "M48.06"],
                description="25 years of heavy structural steel work causing multilevel cervical spondylosis with myelopathy and lumbar stenosis with radiculopathy",
                mechanism="25 years of climbing, heavy lifting, and vibration exposure in structural steel construction",
            ),
        ],
        "treating": _make_physician("David", "Nakamura", "Orthopedic Surgery", "Los Angeles Spine & Orthopedic Center", city="Los Angeles", zipcode="90017"),
        "qme": _make_physician("George", "Palmer", "Orthopedic Surgery", "Southern California AME Group", city="Los Angeles", zipcode="90017"),
        "prior_providers": [],
        "venue": "Los Angeles",
        "judge": "Hon. Margaret Donovan",
        "extra_context": {
            "wc_issues": ["appeals_and_reconsideration", "wcab_panel_review", "substantial_evidence", "apportionment", "petition_for_reconsideration"],
            "educational_notes": (
                "Petitions for Reconsideration (LC 5900-5911) are the primary appellate mechanism within the WCAB. "
                "The WCJ rejected the AME's 25% apportionment to non-industrial factors (weekend softball) as speculation."
            ),
        },
        "second_insurance": None,
    })

    scenarios.append({
        "internal_id": "EP-03",
        "case_params": CaseParameters(
            target_stage="intake",
            claim_response="denied",
            has_attorney=True,
            eval_type="none",
            has_surgery=False,
            has_psych_component=False,
            has_ur_dispute=False,
            has_liens=False,
            num_body_parts=2,
            complexity="complex",
            injury_type="cumulative_trauma",
            body_part_category="upper_extremity",
            resolution_type="random",
        ),
        "applicant": _make_applicant("Sarah", "Kim", date(1988, 4, 10), city="San Diego", zipcode="92101"),
        "employer": _make_employer(
            "LoneStar Software, Inc.",
            "Senior UX Designer",
            city="Austin",
            zipcode="78701",
            hire_date=_date_ago(365 * 2),
            hourly_rate=62.00,
            department="Product Design",
        ),
        "insurance": _make_insurance("Texas Mutual Insurance Company", "Guilford Steiner Sarvas & Carbonara"),
        "injuries": [
            _make_injury(
                doi=date(2025, 11, 15),
                injury_type=InjuryType.CUMULATIVE_TRAUMA,
                body_parts=["Bilateral Carpal Tunnel", "Cervical Spine (C5-C6)"],
                icd10_codes=["G56.00", "G56.01", "M54.12"],
                description="2 years of intensive keyboard and mouse use in poorly ergonomic home office causing bilateral carpal tunnel syndrome and cervical radiculopathy",
                mechanism="2 years of repetitive keyboard/mouse use in home office with poor ergonomic setup",
            ),
        ],
        "treating": _make_physician("Amy", "Nguyen", "Physical Medicine & Rehabilitation", "San Diego Occupational Medicine Center", city="San Diego", zipcode="92103"),
        "qme": None,
        "prior_providers": [],
        "venue": "San Diego",
        "judge": "Hon. Robert Castillo",
        "extra_context": {
            "wc_issues": ["jurisdiction_and_venue", "extraterritorial_coverage", "remote_work_jurisdiction", "contract_of_hire"],
            "educational_notes": (
                "LC 3600.5 grants California jurisdiction when the contract of hire was made in California OR when the injury occurred in California. "
                "Remote workers hired via video interview and signing employment agreements from California present the strongest jurisdictional argument."
            ),
        },
        "second_insurance": None,
    })

    scenarios.append({
        "internal_id": "EP-04",
        "case_params": CaseParameters(
            target_stage="discovery",
            claim_response="accepted",
            has_attorney=True,
            eval_type="qme",
            has_surgery=False,
            has_psych_component=False,
            has_ur_dispute=False,
            has_liens=False,
            num_body_parts=1,
            complexity="standard",
            injury_type="specific",
            body_part_category="spine",
            resolution_type="random",
        ),
        "applicant": _make_applicant("James", "Cooper", date(1985, 9, 12), city="Los Angeles", zipcode="90011"),
        "employer": _make_employer(
            "Metro Wholesale Distribution, LLC",
            "Warehouse Associate",
            city="Los Angeles",
            zipcode="90058",
            hire_date=_date_ago(365 * 7),
            hourly_rate=22.00,
            department="Warehouse",
        ),
        "insurance": _make_insurance(),
        "injuries": [
            _make_injury(
                doi=date(2023, 4, 18),
                injury_type=InjuryType.SPECIFIC,
                body_parts=["Lumbar Spine (L5-S1)"],
                icd10_codes=["M51.16"],
                description="Lifting injury causing L5-S1 disc protrusion with low back pain and radiculopathy",
                mechanism="Lifting heavy boxes in warehouse causing acute low back injury",
            ),
        ],
        "treating": _make_physician("Maria", "Gonzalez", "Chiropractic / Physical Medicine & Rehabilitation", "Los Angeles Occupational Health Center", city="Los Angeles", zipcode="90007"),
        "qme": _make_physician("Stephen", "Lee", "Orthopedic Surgery", "Southern California QME Associates", city="Los Angeles", zipcode="90017"),
        "prior_providers": [],
        "venue": "Los Angeles",
        "judge": "Hon. Sandra Morales",
        "extra_context": {
            "wc_issues": ["wcab_practice_and_process", "discovery_disputes", "continuance_motions", "social_media_discovery", "lc_5502_5_timeline"],
            "educational_notes": (
                "LC 5502.5 mandates a 130-day maximum period between the DOR and the mandatory settlement conference. "
                "Social media discovery is an emerging tool for challenging claimed activity restrictions."
            ),
        },
        "second_insurance": None,
    })

    scenarios.append({
        "internal_id": "EP-05",
        "case_params": CaseParameters(
            target_stage="resolved",
            claim_response="accepted",
            has_attorney=True,
            eval_type="none",
            has_surgery=False,
            has_psych_component=False,
            has_ur_dispute=True,
            has_liens=False,
            num_body_parts=1,
            complexity="complex",
            injury_type="specific",
            body_part_category="spine",
            resolution_type="trial",
        ),
        "applicant": _make_applicant("Katherine", "Lawson", date(1968, 7, 4), city="Los Angeles", zipcode="91342"),
        "employer": _make_employer(
            "Valley Memorial Hospital",
            "Registered Nurse",
            city="Los Angeles",
            zipcode="91405",
            hire_date=_date_ago(365 * 28),
            hourly_rate=58.00,
            department="Medical-Surgical Unit",
        ),
        "insurance": _make_insurance("Keenan & Associates / SHARP", "Laughlin, Falbo, Levy & Moresi LLP"),
        "injuries": [
            _make_injury(
                doi=date(2022, 1, 15),
                injury_type=InjuryType.SPECIFIC,
                body_parts=["Lumbar Spine (L4-L5)"],
                icd10_codes=["M51.16", "G89.29"],
                description="Patient lifting injury causing L4-L5 herniation with chronic pain syndrome after years of failed conservative treatment and repeated IMR denials",
                mechanism="Patient transfer and lifting as registered nurse causing acute lumbar disc herniation",
            ),
        ],
        "treating": _make_physician("Robert", "Chang", "Physical Medicine & Rehabilitation / Pain Medicine", "Valley Pain Management Center", city="Los Angeles", zipcode="91405"),
        "qme": None,
        "prior_providers": [],
        "venue": "Van Nuys",
        "judge": "Hon. Michael Torres",
        "extra_context": {
            "wc_issues": ["constitutional_and_due_process", "imr_constitutionality", "utilization_review", "sb_863_framework", "writ_of_review"],
            "educational_notes": (
                "SB 863 (2012) created the IMR system, routing all medical treatment disputes to independent medical review. "
                "Applicants have challenged the system on due process grounds."
            ),
        },
        "second_insurance": None,
    })


    # --- Group F: Penalties & Special Funds (FP-01 through FP-05) ---

    scenarios.append({
        "internal_id": "FP-01",
        "case_params": CaseParameters(
            target_stage="settlement",
            claim_response="accepted",
            has_attorney=True,
            eval_type="qme",
            has_surgery=False,
            has_psych_component=False,
            has_ur_dispute=False,
            has_liens=False,
            num_body_parts=1,
            complexity="standard",
            injury_type="specific",
            body_part_category="upper_extremity",
            resolution_type="random",
        ),
        "applicant": _make_applicant("Michelle", "Santos", date(1982, 2, 14), city="Los Angeles", zipcode="90022"),
        "employer": _make_employer(
            "Pacific Electronics Manufacturing, Inc.",
            "Assembly Line Worker",
            city="Los Angeles",
            zipcode="90058",
            hire_date=_date_ago(365 * 12),
            hourly_rate=21.50,
            department="Assembly Production",
        ),
        "insurance": _make_insurance("Zurich American Insurance Company", "Bradford & Barthel LLP"),
        "injuries": [
            _make_injury(
                doi=date(2024, 9, 10),
                injury_type=InjuryType.SPECIFIC,
                body_parts=["Right Shoulder"],
                icd10_codes=["M75.11"],
                description="Repetitive overhead assembly motions causing subacromial impingement and partial rotator cuff tear of right shoulder",
                mechanism="Repetitive overhead assembly line work causing right shoulder impingement",
            ),
        ],
        "treating": _make_physician("Robert", "Vasquez", "Orthopedic Surgery", "Pacific Orthopedic Medical Group", city="Los Angeles", zipcode="90022"),
        "qme": _make_physician("Andrew", "Kim", "Orthopedic Surgery", "Los Angeles Orthopedic QME Group", city="Los Angeles", zipcode="90017"),
        "prior_providers": [],
        "venue": "Los Angeles",
        "judge": "Hon. Christine Nakamura",
        "extra_context": {
            "wc_issues": ["penalties", "lc_5814_unreasonable_delay", "lc_5814_5_attorney_fees", "pd_indemnity_payment", "carrier_bad_faith"],
            "educational_notes": (
                "LC 5814 imposes a penalty of up to 25% of the delayed compensation when payment is unreasonably delayed or refused. "
                "LC 5814.5 adds attorney fees where the carrier's conduct was unreasonable."
            ),
        },
        "second_insurance": None,
    })

    scenarios.append({
        "internal_id": "FP-02",
        "case_params": CaseParameters(
            target_stage="medical_legal",
            claim_response="delayed",
            has_attorney=True,
            eval_type="qme",
            has_surgery=False,
            has_psych_component=False,
            has_ur_dispute=False,
            has_liens=False,
            num_body_parts=1,
            complexity="standard",
            injury_type="specific",
            body_part_category="upper_extremity",
            resolution_type="random",
        ),
        "applicant": _make_applicant("Luis", "Garcia", date(1997, 11, 3), city="Los Angeles", zipcode="90033"),
        "employer": _make_employer(
            "Rosita's Kitchen",
            "Line Cook",
            city="Los Angeles",
            zipcode="90033",
            hire_date=_date_ago(365 * 2),
            hourly_rate=17.00,
            department="Kitchen",
        ),
        "insurance": _make_insurance("Uninsured Employers Benefits Trust Fund (UEBTF)", "State of California — DIR Legal Unit"),
        "injuries": [
            _make_injury(
                doi=date(2025, 8, 5),
                injury_type=InjuryType.SPECIFIC,
                body_parts=["Right Wrist"],
                icd10_codes=["S52.531A"],
                description="Colles fracture of right distal radius after slipping on kitchen grease spill and falling onto outstretched hand",
                mechanism="Slipped on grease spill near fryer, fell onto right outstretched hand",
            ),
        ],
        "treating": _make_physician("Carmen", "Reyes", "Orthopedic Surgery", "East Los Angeles Orthopedic Center", city="Los Angeles", zipcode="90022"),
        "qme": _make_physician("Kenneth", "Wong", "Orthopedic Surgery", "Southern California QME Associates", city="Los Angeles", zipcode="90017"),
        "prior_providers": [],
        "venue": "Los Angeles",
        "judge": "Hon. David Reyes",
        "extra_context": {
            "wc_issues": ["insurance_coverage", "uninsured_employer", "uebtf", "lc_3722_penalty", "employer_personal_liability"],
            "educational_notes": (
                "When an employer has no workers' compensation insurance, the UEBTF steps in to pay the injured worker's benefits "
                "and then seeks reimbursement from the employer. LC 3722 imposes a penalty of up to $10,000 per employee."
            ),
        },
        "second_insurance": None,
    })

    scenarios.append({
        "internal_id": "FP-03",
        "case_params": CaseParameters(
            target_stage="discovery",
            claim_response="denied",
            has_attorney=True,
            eval_type="qme",
            has_surgery=False,
            has_psych_component=False,
            has_ur_dispute=False,
            has_liens=False,
            num_body_parts=1,
            complexity="complex",
            injury_type="specific",
            body_part_category="spine",
            resolution_type="random",
        ),
        "applicant": _make_applicant("Anthony", "Russo", date(1980, 5, 8), city="Los Angeles", zipcode="90045"),
        "employer": _make_employer(
            "National Home Improvement Stores, Inc.",
            "Retail Store Manager",
            city="Los Angeles",
            zipcode="90045",
            hire_date=_date_ago(365 * 11),
            hourly_rate=38.50,
            department="Store Operations",
        ),
        "insurance": _make_insurance("Travelers Property Casualty Company of America", "Guilford Steiner Sarvas & Carbonara"),
        "injuries": [
            _make_injury(
                doi=date(2025, 1, 22),
                injury_type=InjuryType.SPECIFIC,
                body_parts=["Lumbar Spine (L4-L5)"],
                icd10_codes=["M51.16", "M54.17"],
                description="L4-L5 herniation with left-sided radiculopathy/sciatica after lifting 80-lb display case during store renovation",
                mechanism="Lifting 80-lb display case during store renovation",
            ),
        ],
        "treating": _make_physician("Maria", "Fernandez", "Physical Medicine & Rehabilitation", "Los Angeles PM&R Associates", city="Los Angeles", zipcode="90048"),
        "qme": _make_physician("Douglas", "Hart", "Orthopedic Surgery", "Westside Orthopedic QME Group", city="Los Angeles", zipcode="90025"),
        "prior_providers": [],
        "venue": "Los Angeles",
        "judge": "Hon. James Whitfield",
        "extra_context": {
            "wc_issues": ["employer_defenses", "fraud_lc_3820", "surveillance_evidence", "credibility", "td_termination"],
            "educational_notes": (
                "LC 3820 authorizes criminal fraud referrals when an applicant materially misrepresents their condition to obtain WC benefits. "
                "Surveillance footage is admissible at WCAB and is routinely used to impeach claimed activity restrictions."
            ),
        },
        "second_insurance": None,
    })

    scenarios.append({
        "internal_id": "FP-04",
        "case_params": CaseParameters(
            target_stage="resolved",
            claim_response="accepted",
            has_attorney=True,
            eval_type="qme",
            has_surgery=False,
            has_psych_component=False,
            has_ur_dispute=False,
            has_liens=True,
            num_body_parts=1,
            complexity="standard",
            injury_type="specific",
            body_part_category="spine",
            resolution_type="cr",
        ),
        "applicant": _make_applicant("Robert", "Taylor", date(1975, 8, 21), city="Santa Barbara", zipcode="93101"),
        "employer": _make_employer(
            "Central Coast Financial Services, Inc.",
            "Office Manager",
            city="Santa Barbara",
            zipcode="93101",
            hire_date=_date_ago(365 * 15),
            hourly_rate=34.00,
            department="Office Administration",
        ),
        "insurance": _make_insurance("Liberty Mutual Insurance", "Laughlin, Falbo, Levy & Moresi LLP"),
        "injuries": [
            _make_injury(
                doi=date(2023, 7, 12),
                injury_type=InjuryType.SPECIFIC,
                body_parts=["Lumbar Spine (L4-L5, L5-S1)"],
                icd10_codes=["M51.16"],
                description="Ergonomic injury from prolonged seated posture causing L4-L5 and L5-S1 disc bulges with low back pain",
                mechanism="Prolonged seated posture and repetitive computer use causing lumbar disc bulges",
            ),
        ],
        "treating": _make_physician("Thomas", "Green", "Chiropractic", "Central Coast Chiropractic Clinic", city="Santa Barbara", zipcode="93105"),
        "qme": _make_physician("Jonathan", "Park", "Orthopedic Surgery", "Santa Barbara Orthopedic QME Associates", city="Santa Barbara", zipcode="93101"),
        "prior_providers": [],
        "venue": "Santa Barbara",
        "judge": "Hon. Elizabeth Hartwell",
        "extra_context": {
            "wc_issues": ["liens", "medical_provider_lien", "lc_4903", "omfs_compliance", "mtus_frequency_guidelines", "lien_conference"],
            "educational_notes": (
                "Lien disputes are the highest-volume WCAB proceeding by raw count. Medical provider liens are filed under LC 4903."
            ),
        },
        "second_insurance": None,
    })

    scenarios.append({
        "internal_id": "FP-05",
        "case_params": CaseParameters(
            target_stage="settlement",
            claim_response="accepted",
            has_attorney=True,
            eval_type="ame",
            has_surgery=True,
            has_psych_component=False,
            has_ur_dispute=False,
            has_liens=True,
            num_body_parts=3,
            complexity="complex",
            injury_type="cumulative_trauma",
            body_part_category="spine",
            resolution_type="cr",
        ),
        "applicant": _make_applicant("Harold", "Jenkins", date(1962, 10, 17), city="Los Angeles", zipcode="90011"),
        "employer": _make_employer(
            "Metro Commercial Properties, LLC",
            "Building Maintenance Worker",
            city="Los Angeles",
            zipcode="90014",
            hire_date=_date_ago(365 * 30),
            hourly_rate=26.00,
            department="Facilities Maintenance",
        ),
        "insurance": _make_insurance("Employers Compensation Insurance Company", "Laughlin, Falbo, Levy & Moresi LLP"),
        "injuries": [
            _make_injury(
                doi=date(2024, 6, 1),
                injury_type=InjuryType.CUMULATIVE_TRAUMA,
                body_parts=["Lumbar Spine (L4-S1)", "Left Knee", "Right Knee"],
                icd10_codes=["M48.06", "M17.0"],
                description="30 years of physical maintenance work causing lumbar stenosis requiring L4-S1 fusion and bilateral primary osteoarthritis requiring total knee arthroplasty",
                mechanism="30 years of crawling, kneeling, heavy lifting, and ladder climbing in building maintenance",
            ),
        ],
        "treating": _make_physician("James", "Wilson", "Orthopedic Surgery", "Los Angeles Orthopedic Surgery Center", city="Los Angeles", zipcode="90048"),
        "qme": _make_physician("Sandra", "Martinez", "Orthopedic Surgery", "Southern California AME Group", city="Los Angeles", zipcode="90017"),
        "prior_providers": [],
        "venue": "Los Angeles",
        "judge": "Hon. Richard Flores",
        "extra_context": {
            "wc_issues": ["settlements", "medicare_set_aside", "future_medical_care", "cms_review", "liens", "c_and_r_medicare_eligible"],
            "educational_notes": (
                "Medicare Set-Asides (MSAs) are required when settling cases involving Medicare-eligible workers. "
                "CMS review can delay settlement 6-18 months."
            ),
        },
        "second_insurance": None,
    })


    # --- Group G: Routine/Baseline (GR-01 through GR-08) ---

    scenarios.append({
        "internal_id": "GR-01",
        "case_params": CaseParameters(
            target_stage="intake",
            claim_response="accepted",
            has_attorney=True,
            eval_type="none",
            has_surgery=False,
            has_psych_component=False,
            has_ur_dispute=False,
            has_liens=False,
            num_body_parts=1,
            complexity="standard",
            injury_type="specific",
            body_part_category="lower_extremity",
            resolution_type="random",
        ),
        "applicant": _make_applicant(
            first="Derek",
            last="Johnson",
            dob=date(1996, 1, 1),
            city="Los Angeles",
            zipcode="90001",
        ),
        "employer": _make_employer(
            company="West Coast Fulfillment, Inc.",
            position="Warehouse Worker",
            city="Los Angeles",
            zipcode="90012",
            hire_date=_date_ago(365 * 3),
            hourly_rate=19.00,
            department="Shipping & Receiving",
        ),
        "insurance": _make_insurance(
            carrier="State Compensation Insurance Fund (SCIF)",
            defense_firm="Bradford & Barthel LLP",
        ),
        "injuries": [
            _make_injury(
                doi=date(2026, 3, 20),
                injury_type=InjuryType.SPECIFIC,
                body_parts=["Right Knee"],
                icd10_codes=["S83.212A"],
                description="Suspected medial meniscus tear, right knee, pending MRI confirmation.",
                mechanism="Stepped off loading dock and twisted right knee on uneven ground.",
            )
        ],
        "treating": _make_physician(
            first="Cynthia",
            last="Park",
            specialty="Orthopedic Surgery",
            facility="Orthopedic Associates of Los Angeles",
            city="Los Angeles",
            zipcode="90048",
        ),
        "qme": None,
        "prior_providers": [],
        "venue": "Los Angeles WCAB",
        "judge": "Hon. Patricia Morales",
        "extra_context": {
            "adj_number": "ADJ21678901",
            "employment_duration_years": 3,
            "prior_injuries": "None",
            "key_documents": [
                "DWC-1 Claim Form",
                "Application for Adjudication of Claim",
                "Employer's Report of Occupational Injury (Form 5020)",
                "Initial medical report (ER visit, same day as injury)",
            ],
            "wc_issues": ["TD Rate & Duration"],
            "educational_notes": (
                "Clean intake baseline — the simplest possible case. "
                "Shows the starting point of the attorney-client relationship and the initial document set. "
                "Provides contrast to complex cases and demonstrates standard intake workflow."
            ),
            "scenario_group": "G — Routine/Baseline",
        },
        "second_insurance": None,
    })

    scenarios.append({
        "internal_id": "GR-02",
        "case_params": CaseParameters(
            target_stage="active_treatment",
            claim_response="accepted",
            has_attorney=True,
            eval_type="none",
            has_surgery=False,
            has_psych_component=False,
            has_ur_dispute=False,
            has_liens=False,
            num_body_parts=1,
            complexity="standard",
            injury_type="specific",
            body_part_category="upper_extremity",
            resolution_type="random",
        ),
        "applicant": _make_applicant(
            first="Ryan",
            last="Mitchell",
            dob=date(1987, 1, 1),
            city="Los Angeles",
            zipcode="90001",
        ),
        "employer": _make_employer(
            company="ProCoat Painting Services, LLC",
            position="House Painter",
            city="Los Angeles",
            zipcode="90012",
            hire_date=_date_ago(365 * 6),
            hourly_rate=28.00,
            department="Residential Painting",
        ),
        "insurance": _make_insurance(
            carrier="State Compensation Insurance Fund (SCIF)",
            defense_firm="Bradford & Barthel LLP",
        ),
        "injuries": [
            _make_injury(
                doi=date(2025, 10, 15),
                injury_type=InjuryType.SPECIFIC,
                body_parts=["Right Shoulder"],
                icd10_codes=["M75.11"],
                description="Full-thickness supraspinatus tear, right shoulder.",
                mechanism="Overhead painting on extension ladder; felt right shoulder pop during sustained overhead reach.",
            )
        ],
        "treating": _make_physician(
            first="Brian",
            last="Torres",
            specialty="Orthopedic Surgery / Sports Medicine",
            facility="Southern California Orthopedic Institute",
            city="Los Angeles",
            zipcode="90048",
        ),
        "qme": None,
        "prior_providers": [],
        "venue": "Los Angeles WCAB",
        "judge": "Hon. David Chen",
        "extra_context": {
            "adj_number": "ADJ21789012",
            "employment_duration_years": 6,
            "prior_injuries": "No prior shoulder problems",
            "td_status": "Currently receiving TD; no gaps",
            "surgery_decision_pending": True,
            "key_documents": [
                "PR-2 Reports (initial + follow-ups)",
                "MRI report (confirming full-thickness tear)",
                "Physical therapy treatment notes",
                "Surgical consultation note",
                "Work status reports (off work pending surgery decision)",
                "TD payment records (current, no gaps)",
            ],
            "wc_issues": ["TD Rate & Duration", "Medical Treatment Authorization"],
            "educational_notes": (
                "Standard treatment-phase case — no disputes. Demonstrates normal document flow: "
                "PR-2 reports, MRI, PT notes, surgical consultation. "
                "The surgery decision point is a natural progression marker in the treatment timeline."
            ),
            "scenario_group": "G — Routine/Baseline",
        },
        "second_insurance": None,
    })

    scenarios.append({
        "internal_id": "GR-03",
        "case_params": CaseParameters(
            target_stage="intake",
            claim_response="delayed",
            has_attorney=True,
            eval_type="none",
            has_surgery=False,
            has_psych_component=False,
            has_ur_dispute=False,
            has_liens=False,
            num_body_parts=1,
            complexity="standard",
            injury_type="specific",
            body_part_category="spine",
            resolution_type="random",
        ),
        "applicant": _make_applicant(
            first="Maria",
            last="Gonzalez",
            dob=date(1991, 1, 1),
            city="Los Angeles",
            zipcode="90001",
        ),
        "employer": _make_employer(
            company="Valley Fresh Market, Inc.",
            position="Grocery Store Clerk",
            city="Los Angeles",
            zipcode="90012",
            hire_date=_date_ago(365 * 5),
            hourly_rate=18.50,
            department="Grocery Stocking",
        ),
        "insurance": _make_insurance(
            carrier="Zenith Insurance Company",
            defense_firm="Laughlin, Falbo, Levy & Moresi LLP",
        ),
        "injuries": [
            _make_injury(
                doi=date(2026, 1, 10),
                injury_type=InjuryType.SPECIFIC,
                body_parts=["Lumbar Spine"],
                icd10_codes=["M51.26"],
                description="L5-S1 disc bulge, lumbar spine.",
                mechanism="Lifting cases of canned goods (40+ lbs each) from floor to overhead shelf.",
            )
        ],
        "treating": _make_physician(
            first="Carlos",
            last="Reyes",
            specialty="Family Medicine",
            facility="Valley Community Medical Clinic",
            city="Los Angeles",
            zipcode="90012",
        ),
        "qme": None,
        "prior_providers": [],
        "venue": "Los Angeles WCAB",
        "judge": "Hon. Susan Park",
        "extra_context": {
            "adj_number": "ADJ21890123",
            "employment_duration_years": 5,
            "prior_injuries": "No prior back injuries",
            "lc_5402b_auto_acceptance": True,
            "delay_letter_issued": True,
            "days_without_acceptance_or_denial": 70,
            "retroactive_td_demanded": True,
            "key_documents": [
                "DWC-1 Claim Form",
                "Carrier delay letter (within 14 days of filing)",
                "70-day timeline documentation (no acceptance/denial)",
                "LC 5402(b) auto-acceptance demand letter",
                "Retroactive TD demand",
                "Application for Adjudication",
            ],
            "wc_issues": ["TD Rate & Duration", "LC 5402(b) Auto-Acceptance", "Retroactive TD"],
            "educational_notes": (
                "LC 5402(b) auto-acceptance is a common intake scenario — carriers frequently miss the 90-day window, "
                "resulting in claims being accepted by operation of law even when they intended to deny. "
                "Tests the statutory timeline (14-day delay letter, 90-day decision window) and retroactive "
                "benefits entitlement from the date of disability."
            ),
            "scenario_group": "G — Routine/Baseline",
        },
        "second_insurance": None,
    })

    scenarios.append({
        "internal_id": "GR-04",
        "case_params": CaseParameters(
            target_stage="active_treatment",
            claim_response="accepted",
            has_attorney=True,
            eval_type="none",
            has_surgery=True,
            has_psych_component=False,
            has_ur_dispute=False,
            has_liens=False,
            num_body_parts=1,
            complexity="standard",
            injury_type="specific",
            body_part_category="upper_extremity",
            resolution_type="random",
        ),
        "applicant": _make_applicant(
            first="Jason",
            last="Pham",
            dob=date(1998, 1, 1),
            city="Los Angeles",
            zipcode="90001",
        ),
        "employer": _make_employer(
            company="The Coastal Grill Restaurant",
            position="Line Cook",
            city="Los Angeles",
            zipcode="90012",
            hire_date=_date_ago(365 * 2),
            hourly_rate=18.00,
            department="Kitchen",
        ),
        "insurance": _make_insurance(
            carrier="Employers Compensation Insurance Company",
            defense_firm="Hanna, Brophy, MacLean, McAleer & Jensen LLP",
        ),
        "injuries": [
            _make_injury(
                doi=date(2025, 12, 5),
                injury_type=InjuryType.SPECIFIC,
                body_parts=["Left Hand — Index Finger", "Left Hand — Middle Finger"],
                icd10_codes=["S66.321A", "S66.322A"],
                description=(
                    "Laceration of extensor tendon, left index finger (S66.321A) and "
                    "left middle finger (S66.322A); surgically repaired."
                ),
                mechanism="Left hand caught in commercial food processor with removed safety guard.",
            )
        ],
        "treating": _make_physician(
            first="Nina",
            last="Patel",
            specialty="Hand Surgery",
            facility="Los Angeles Hand Surgery Center",
            city="Los Angeles",
            zipcode="90048",
        ),
        "qme": None,
        "prior_providers": [],
        "venue": "Los Angeles WCAB",
        "judge": "Hon. Robert Kim",
        "extra_context": {
            "adj_number": "ADJ21901234",
            "employment_duration_years": 2,
            "prior_injuries": "No prior hand injuries",
            "initial_denial": True,
            "denial_basis": "Employee misuse of equipment (safety guard removed)",
            "denial_reversed": True,
            "reversal_basis": (
                "Witness statements established employer routinely removed guard to speed food prep, "
                "creating the unsafe condition — employer cannot assert employee fault defense."
            ),
            "surgery_performed": True,
            "surgery_type": "Extensor tendon repair, left index and middle fingers",
            "calosha_report": True,
            "key_documents": [
                "DWC-1 Claim Form",
                "Denial letter (citing employee misuse of equipment)",
                "Attorney demand letter with witness declarations",
                "Acceptance letter (reversing denial)",
                "Surgical operative report (tendon repair)",
                "Post-operative hand therapy notes",
                "Cal/OSHA equipment safety report",
            ],
            "wc_issues": ["TD Rate & Duration", "Employer Denial Defenses", "Denial Reversal"],
            "educational_notes": (
                "Denial reversal is a common early-stage outcome when an attorney gets involved. "
                "Initial denial based on employee fault is overcome by evidence that the employer created "
                "the unsafe condition (guard routinely removed by management). Demonstrates the value of "
                "attorney representation in contested claims and the limits of the employer-fault defense."
            ),
            "scenario_group": "G — Routine/Baseline",
        },
        "second_insurance": None,
    })

    scenarios.append({
        "internal_id": "GR-05",
        "case_params": CaseParameters(
            target_stage="resolved",
            claim_response="accepted",
            has_attorney=True,
            eval_type="qme",
            has_surgery=False,
            has_psych_component=False,
            has_ur_dispute=False,
            has_liens=False,
            num_body_parts=3,
            complexity="standard",
            injury_type="cumulative_trauma",
            body_part_category="upper_extremity",
            resolution_type="cr",
        ),
        "applicant": _make_applicant(
            first="Jennifer",
            last="Liu",
            dob=date(1984, 1, 1),
            city="Los Angeles",
            zipcode="90001",
        ),
        "employer": _make_employer(
            company="InfoTech Data Services, Inc.",
            position="Data Entry Clerk",
            city="Los Angeles",
            zipcode="90012",
            hire_date=_date_ago(365 * 10),
            hourly_rate=22.00,
            department="Data Processing",
        ),
        "insurance": _make_insurance(
            carrier="Zurich American Insurance Company",
            defense_firm="Defense Counsel Group LLP",
        ),
        "injuries": [
            _make_injury(
                doi=date(2024, 8, 15),
                injury_type=InjuryType.CUMULATIVE_TRAUMA,
                body_parts=["Bilateral Wrists / Carpal Tunnel", "Cervical Spine (C5-C6)"],
                icd10_codes=["G56.00", "G56.01", "M54.12"],
                description=(
                    "Bilateral carpal tunnel syndrome (G56.00 right, G56.01 left) and "
                    "cervical radiculopathy C5-C6 (M54.12) from cumulative keyboard and mouse use."
                ),
                mechanism="10 years of repetitive keyboard and mouse use, 8 hours per day.",
            )
        ],
        "treating": _make_physician(
            first="Sandra",
            last="Ortiz",
            specialty="Orthopedic Surgery",
            facility="Westside Hand & Upper Extremity Center",
            city="Los Angeles",
            zipcode="90025",
        ),
        "qme": _make_physician(
            first="Margaret",
            last="Chen",
            specialty="Physical Medicine & Rehabilitation (PM&R)",
            facility="Pacific Medical Evaluations",
            city="Los Angeles",
            zipcode="90048",
        ),
        "prior_providers": [],
        "venue": "Los Angeles WCAB",
        "judge": "Hon. Karen Holt",
        "extra_context": {
            "adj_number": "ADJ22012345",
            "employment_duration_years": 10,
            "prior_injuries": "None industrial; video gaming hobby (avid gamer) contributed to non-industrial apportionment",
            "resolution": {
                "type": "Compromise and Release (C&R)",
                "amount_usd": 95000,
                "pd_rating_percent": 30,
                "apportionment_nonindustrial_percent": 10,
                "apportionment_basis": "Non-industrial typing from video gaming hobby",
                "order_approving_cr": True,
                "case_closed": True,
            },
            "key_documents": [
                "C&R Agreement (executed, $95,000)",
                "Order Approving C&R",
                "QME Report (30% combined PD, 10% apportionment to non-industrial)",
                "Rating string",
                "Fee Disclosure Statement",
                "Final attorney fee calculation",
                "Case closure letter to client",
            ],
            "wc_issues": ["Settlement Disputes", "CT Dating & Liability", "Apportionment"],
            "educational_notes": (
                "Clean resolved case — demonstrates a fully concluded file with all documents in order. "
                "The 10% non-industrial apportionment (video gaming) adds a minor but realistic wrinkle. "
                "Shows what a 'done' case looks like in the attorney's caseload."
            ),
            "scenario_group": "G — Routine/Baseline",
        },
        "second_insurance": None,
    })

    scenarios.append({
        "internal_id": "GR-06",
        "case_params": CaseParameters(
            target_stage="intake",
            claim_response="denied",
            has_attorney=True,
            eval_type="none",
            has_surgery=False,
            has_psych_component=False,
            has_ur_dispute=False,
            has_liens=False,
            num_body_parts=2,
            complexity="standard",
            injury_type="cumulative_trauma",
            body_part_category="spine",
            resolution_type="random",
        ),
        "applicant": _make_applicant(
            first="Sandra",
            last="Williams",
            dob=date(1986, 1, 1),
            city="Los Angeles",
            zipcode="90001",
        ),
        "employer": _make_employer(
            company="California Investment Advisors, LLC",
            position="Office Administrator",
            city="Los Angeles",
            zipcode="90012",
            hire_date=_date_ago(365 * 5),
            hourly_rate=28.00,
            department="Administrative Services",
        ),
        "insurance": _make_insurance(
            carrier="ICW Group Insurance Companies",
            defense_firm="Mullen & Filippi LLP",
        ),
        "injuries": [
            _make_injury(
                doi=date(2026, 2, 1),
                injury_type=InjuryType.CUMULATIVE_TRAUMA,
                body_parts=["Cervical Spine (C5-C6)", "Right Elbow (Lateral Epicondylitis)"],
                icd10_codes=["M54.12", "M77.11"],
                description=(
                    "Cervical radiculopathy C5-C6 (M54.12) and lateral epicondylitis right elbow (M77.11) "
                    "from sustained computer use."
                ),
                mechanism="5 years of sustained computer use, poor ergonomics, minimal breaks.",
            )
        ],
        "treating": _make_physician(
            first="Alan",
            last="Foster",
            specialty="Physical Medicine & Rehabilitation (PM&R)",
            facility="LA Rehabilitation Medicine",
            city="Los Angeles",
            zipcode="90048",
        ),
        "qme": None,
        "prior_providers": [],
        "venue": "Los Angeles WCAB",
        "judge": "Hon. Michael Torres",
        "extra_context": {
            "adj_number": "ADJ22123456",
            "employment_duration_years": 5,
            "prior_injuries": "Auto accident 3 years ago (non-industrial, treated and resolved per medical records)",
            "denial_basis": [
                "No specific incident identified",
                "CT dates vague — no clear last date of injurious exposure",
                "Pre-existing non-industrial condition (prior auto accident)",
            ],
            "investigation_phase": True,
            "pending_actions": [
                "Application for Adjudication (pending filing)",
                "Initial medical records request (to treating physician)",
                "Employment records request (to employer)",
                "Prior auto accident medical records subpoena",
            ],
            "key_documents": [
                "DWC-1 Claim Form",
                "Denial letter (no specific incident, pre-existing condition)",
                "Application for Adjudication (pending filing)",
                "Initial medical records request (to treating physician)",
                "Employment records request (to employer)",
                "Prior auto accident medical records subpoena",
            ],
            "wc_issues": ["CT Dating & Liability", "Employer Denial Defenses", "AOE/COE"],
            "educational_notes": (
                "Common denied CT intake — the starting point for many attorney files. "
                "Carrier denial grounds (no specific incident, pre-existing condition) are the most common "
                "reasons for CT denials. Shows the initial investigation phase where the attorney gathers "
                "records to build the claim. Pre-existing auto accident adds an apportionment/causation layer."
            ),
            "scenario_group": "G — Routine/Baseline",
        },
        "second_insurance": None,
    })

    scenarios.append({
        "internal_id": "GR-07",
        "case_params": CaseParameters(
            target_stage="resolved",
            claim_response="accepted",
            has_attorney=True,
            eval_type="qme",
            has_surgery=True,
            has_psych_component=False,
            has_ur_dispute=False,
            has_liens=False,
            num_body_parts=1,
            complexity="standard",
            injury_type="specific",
            body_part_category="lower_extremity",
            resolution_type="stip",
        ),
        "applicant": _make_applicant(
            first="Michael",
            last="Torres",
            dob=date(1989, 1, 1),
            city="Los Angeles",
            zipcode="90001",
        ),
        "employer": _make_employer(
            company="Bright Spark Electrical, Inc.",
            position="Journeyman Electrician",
            city="Los Angeles",
            zipcode="90012",
            hire_date=_date_ago(365 * 10),
            hourly_rate=42.00,
            department="Field Installation",
        ),
        "insurance": _make_insurance(
            carrier="State Compensation Insurance Fund (SCIF)",
            defense_firm="Mullen & Filippi LLP",
        ),
        "injuries": [
            _make_injury(
                doi=date(2024, 11, 18),
                injury_type=InjuryType.SPECIFIC,
                body_parts=["Right Knee"],
                icd10_codes=["S83.212A"],
                description="Medial meniscus tear, right knee; post-arthroscopic repair.",
                mechanism="Kneeling to wire a low outlet, felt right knee pop while pivoting.",
            )
        ],
        "treating": _make_physician(
            first="Robert",
            last="Nguyen",
            specialty="Orthopedic Surgery",
            facility="Los Angeles Orthopedic Surgery Center",
            city="Los Angeles",
            zipcode="90048",
        ),
        "qme": _make_physician(
            first="Patricia",
            last="Lee",
            specialty="Orthopedic Surgery",
            facility="Pacific QME Medical Group",
            city="Los Angeles",
            zipcode="90048",
        ),
        "prior_providers": [],
        "venue": "Los Angeles WCAB",
        "judge": "Hon. James Rodriguez",
        "extra_context": {
            "adj_number": "ADJ22234567",
            "employment_duration_years": 10,
            "prior_injuries": "No prior knee injuries",
            "resolution": {
                "type": "Stipulations with Request for Award",
                "pd_rating_percent": 18,
                "future_medical_retained": True,
                "contested": False,
            },
            "surgery_performed": True,
            "surgery_type": "Arthroscopic meniscus repair, right knee",
            "ps_status": True,
            "key_documents": [
                "Stipulations with Request for Award (18% PD)",
                "QME Report (P&S, 18% WPI)",
                "Rating string",
                "Fee Disclosure Statement",
                "Surgical operative report (arthroscopic meniscus repair)",
                "Award issued by WCJ",
            ],
            "wc_issues": ["Settlement Disputes", "Future Medical Care", "PD Rating Disputes"],
            "educational_notes": (
                "The most common resolution outcome in WC — stipulations where both sides agree on PD "
                "and the applicant retains future medical. Clean, efficient, and representative of how "
                "most cases actually end. Provides contrast to contested settlement cases. "
                "The retained future medical right is a key benefit applicants must understand."
            ),
            "scenario_group": "G — Routine/Baseline",
        },
        "second_insurance": None,
    })

    scenarios.append({
        "internal_id": "GR-08",
        "case_params": CaseParameters(
            target_stage="active_treatment",
            claim_response="delayed",
            has_attorney=True,
            eval_type="none",
            has_surgery=True,
            has_psych_component=False,
            has_ur_dispute=False,
            has_liens=False,
            num_body_parts=1,
            complexity="complex",
            injury_type="specific",
            body_part_category="internal",
            resolution_type="random",
        ),
        "applicant": _make_applicant(
            first="Patrick",
            last="O'Malley",
            dob=date(1978, 1, 1),
            city="Los Angeles",
            zipcode="90001",
        ),
        "employer": _make_employer(
            company="City of Los Angeles Fire Department",
            position="Fire Captain",
            city="Los Angeles",
            zipcode="90012",
            hire_date=_date_ago(365 * 18),
            hourly_rate=65.00,
            department="Fire Suppression",
        ),
        "insurance": _make_insurance(
            carrier="City of Los Angeles (Self-Insured)",
            defense_firm="City Attorney — Workers' Compensation Division",
        ),
        "injuries": [
            _make_injury(
                doi=date(2025, 9, 22),
                injury_type=InjuryType.SPECIFIC,
                body_parts=["Internal — Colon (Stage II Adenocarcinoma)"],
                icd10_codes=["C18.9"],
                description="Malignant neoplasm of colon, unspecified (Stage II adenocarcinoma) — industrially caused under LC 3212.1 firefighter cancer presumption.",
                mechanism=(
                    "Occupational exposure to carcinogens during 18 years of active firefighting: "
                    "combustion byproducts, diesel exhaust, and PFAS in turnout gear."
                ),
            )
        ],
        "treating": _make_physician(
            first="Howard",
            last="Kim",
            specialty="Surgical Oncology",
            facility="Cedars-Sinai Medical Center",
            city="Los Angeles",
            zipcode="90048",
        ),
        "qme": None,
        "prior_providers": [
            _make_physician(
                first="Lisa",
                last="Cho",
                specialty="Medical Oncology",
                facility="Cedars-Sinai Cancer Center",
                city="Los Angeles",
                zipcode="90048",
            )
        ],
        "venue": "Los Angeles WCAB",
        "judge": "Hon. Elizabeth Barnes",
        "extra_context": {
            "adj_number": "ADJ22345678",
            "employment_duration_years": 18,
            "prior_injuries": (
                "Family history: father diagnosed with colon cancer at 55, paternal grandfather at 62. "
                "Genetic testing positive for Lynch syndrome mutation."
            ),
            "lc_3212_1_presumption": True,
            "presumption_invoked": True,
            "carrier_rebuttal_attempted": True,
            "carrier_rebuttal_grounds": [
                "Strong family history of colon cancer (father and grandfather both diagnosed)",
                "Dietary habits (high red meat consumption)",
                "Genetic testing showing Lynch syndrome mutation",
            ],
            "rebuttal_standard": "Preponderance of the evidence — heavy burden even with family history and genetic predisposition",
            "treatment_plan": "Surgery (colectomy) + adjuvant chemotherapy",
            "delay_reason": "Carrier investigating rebuttal evidence for LC 3212.1 presumption",
            "key_documents": [
                "Application for Adjudication",
                "LC 3212.1 presumption invocation letter",
                "Carrier's delay letter (investigating rebuttal evidence)",
                "Family cancer history documentation",
                "Genetic testing results (Lynch syndrome)",
                "Occupational exposure history (18 years of fire suppression records)",
                "Medical oncology treatment plan (surgery + chemotherapy)",
                "Carrier's rebuttal brief (non-industrial causation evidence)",
                "Applicant's response (presumption burden remains with employer)",
            ],
            "wc_issues": ["LC 3212.1 Firefighter Cancer Presumption", "AOE/COE", "Statutory Presumptions"],
            "educational_notes": (
                "The firefighter cancer presumption (LC 3212.1) is one of the most significant statutory "
                "presumptions in CA WC. The carrier must overcome the presumption by preponderance of the "
                "evidence — a heavy burden even with strong family history and genetic predisposition. "
                "Tests the rebuttal standard and the intersection of occupational cancer science with "
                "genetic risk factors (Lynch syndrome). PFAS exposure in turnout gear is an emerging issue."
            ),
            "scenario_group": "G — Routine/Baseline",
        },
        "second_insurance": None,
    })

    # ── Group H: High-Volume Subcategory Gap-Fillers ─────────────────────────────


    # --- Group H: Gap-Fillers (HG-01 through HG-05) ---

    scenarios.append({
        "internal_id": "HG-01",
        "case_params": CaseParameters(
            target_stage="settlement",
            claim_response="accepted",
            has_attorney=True,
            eval_type="qme",
            has_surgery=False,
            has_psych_component=False,
            has_ur_dispute=False,
            has_liens=True,
            num_body_parts=1,
            complexity="standard",
            injury_type="specific",
            body_part_category="spine",
            resolution_type="random",
        ),
        "applicant": _make_applicant(
            first="Thomas",
            last="Garcia",
            dob=date(1979, 1, 1),
            city="Los Angeles",
            zipcode="90001",
        ),
        "employer": _make_employer(
            company="Express Package Delivery, Inc.",
            position="Delivery Truck Driver",
            city="Los Angeles",
            zipcode="90012",
            hire_date=_date_ago(365 * 9),
            hourly_rate=24.00,
            department="Delivery Operations",
        ),
        "insurance": _make_insurance(
            carrier="Travelers Property Casualty Company",
            defense_firm="Adelson, Testan, Brundo, Novell & Jimenez",
        ),
        "injuries": [
            _make_injury(
                doi=date(2024, 4, 15),
                injury_type=InjuryType.SPECIFIC,
                body_parts=["Cervical Spine (C4-C5, C5-C6)"],
                icd10_codes=["M50.12"],
                description="Cervical disc disorder at C4-C5 and C5-C6 with disc bulges.",
                mechanism="Rear-end collision while stopped at traffic light in company delivery truck.",
            )
        ],
        "treating": _make_physician(
            first="George",
            last="Baker",
            specialty="Chiropractic",
            facility="Baker Chiropractic & Wellness",
            city="Los Angeles",
            zipcode="90012",
        ),
        "qme": _make_physician(
            first="Sarah",
            last="Foster",
            specialty="Orthopedic Surgery",
            facility="Pacific Orthopedic QME Group",
            city="Los Angeles",
            zipcode="90048",
        ),
        "prior_providers": [],
        "venue": "Los Angeles WCAB",
        "judge": "Hon. Thomas Nguyen",
        "extra_context": {
            "adj_number": "ADJ22456789",
            "employment_duration_years": 9,
            "prior_injuries": "Treated by chiropractor 3x/week for 18 months",
            "lien_dispute": {
                "lien_claimant": "Dr. George Baker, DC",
                "lien_amount_usd": 68000,
                "lien_activation_fee_paid_usd": 150,
                "treatment_duration_months": 18,
                "treatment_frequency": "3x/week",
                "defense_objections": [
                    "MTUS chiropractic visit frequency violated (guidelines limit to 24 visits in first 12 weeks)",
                    "Per-visit billing exceeds OMFS by 40%",
                    "No RFA ever filed for extended treatment course — treatment unauthorized",
                ],
                "lien_claimant_response": "MTUS is a guideline, not a hard cap; treatment was medically necessary",
                "lien_conference_pending": True,
            },
            "key_documents": [
                "Lien Claim Filing (LC 4903, $68,000)",
                "Lien activation fee receipt ($150)",
                "Chiropractic billing records (18 months, 3x/week)",
                "OMFS fee schedule comparison (showing 40% overbilling)",
                "MTUS chiropractic visit frequency guidelines",
                "Absence of RFA for extended treatment",
                "Lien conference notice",
                "Defense lien objection brief",
                "Applicant's position on lien (neutral — dispute between provider and carrier)",
            ],
            "wc_issues": ["Lien Disputes", "OMFS Compliance", "MTUS Treatment Frequency", "Lien Activation Fee"],
            "educational_notes": (
                "Lien disputes are the #9 most litigated subcategory and represent the largest raw volume "
                "of WCAB hearings. Chiropractic liens with extended treatment courses and OMFS overbilling "
                "are the archetype. Tests MTUS treatment frequency limits (chiropractic: 24-visit guideline), "
                "OMFS fee schedule compliance, and the lien conference/trial process. "
                "Key nuance: applicant is typically neutral — lien dispute is between the provider and the carrier."
            ),
            "scenario_group": "H — Gap-Fillers",
        },
        "second_insurance": None,
    })

    scenarios.append({
        "internal_id": "HG-02",
        "case_params": CaseParameters(
            target_stage="medical_legal",
            claim_response="accepted",
            has_attorney=True,
            eval_type="qme",
            has_surgery=False,
            has_psych_component=False,
            has_ur_dispute=False,
            has_liens=True,
            num_body_parts=3,
            complexity="standard",
            injury_type="cumulative_trauma",
            body_part_category="spine",
            resolution_type="random",
        ),
        "applicant": _make_applicant(
            first="Richard",
            last="Perez",
            dob=date(1973, 1, 1),
            city="Los Angeles",
            zipcode="90001",
        ),
        "employer": _make_employer(
            company="Premier Collision Repair, Inc.",
            position="Auto Body Technician",
            city="Los Angeles",
            zipcode="90012",
            hire_date=_date_ago(365 * 20),
            hourly_rate=32.00,
            department="Body Shop",
        ),
        "insurance": _make_insurance(
            carrier="Liberty Mutual Insurance Company",
            defense_firm="Kegel, Tobin & Truce",
        ),
        "injuries": [
            _make_injury(
                doi=date(2025, 7, 1),
                injury_type=InjuryType.CUMULATIVE_TRAUMA,
                body_parts=["Cervical Spine", "Lumbar Spine", "Bilateral Shoulders"],
                icd10_codes=["M54.12", "M54.5", "M75.10", "M75.11"],
                description=(
                    "Cervical radiculopathy (M54.12), chronic low back pain (M54.5), "
                    "and bilateral shoulder impingement (M75.10 left, M75.11 right) from 20 years of "
                    "physical auto body work."
                ),
                mechanism="20 years of physical auto body work — bending, grinding, painting, lifting.",
            )
        ],
        "treating": _make_physician(
            first="Michael",
            last="Tran",
            specialty="Orthopedic Surgery",
            facility="Premier Spine & Joint Medical Group",
            city="Los Angeles",
            zipcode="90012",
        ),
        "qme": _make_physician(
            first="Frank",
            last="Robinson",
            specialty="Orthopedic Surgery",
            facility="Robinson Orthopedic Medical-Legal Evaluations",
            city="Los Angeles",
            zipcode="90048",
        ),
        "prior_providers": [],
        "venue": "Los Angeles WCAB",
        "judge": "Hon. Angela Davis",
        "extra_context": {
            "adj_number": "ADJ22567890",
            "employment_duration_years": 20,
            "prior_injuries": "Complex CT claim; 2,800 pages of medical records spanning 20 years",
            "medical_legal_fee_dispute": {
                "qme_is_lien_claimant": True,
                "total_bill_usd": 12500,
                "bill_breakdown": {
                    "initial_evaluation_usd": 3500,
                    "record_review_pages": 2800,
                    "record_review_rate_per_page_usd": 2.00,
                    "record_review_total_usd": 5600,
                    "supplemental_report_usd": 2400,
                    "face_to_face_fee_usd": 1000,
                },
                "carrier_objections": [
                    "Record review charge exceeds MLFS cap",
                    "Supplemental report was unsolicited and not requested by either party — not compensable",
                    "Face-to-face fee is included in initial evaluation fee and cannot be billed separately",
                ],
                "qme_lien_for_unpaid_balance": True,
            },
            "key_documents": [
                "QME Report (initial evaluation)",
                "QME Supplemental Report (unsolicited)",
                "QME billing statement ($12,500)",
                "Carrier's objection to billing (MLFS fee schedule analysis)",
                "QME's lien filing for unpaid balance",
                "Medical-Legal Fee Schedule (MLFS) provisions",
                "Carrier's explanation of review (EOR) with partial payment",
                "QME's second billing with dispute",
            ],
            "wc_issues": ["Medical-Legal Fee Disputes", "MLFS Compliance", "Lien Disputes"],
            "educational_notes": (
                "Medical-legal fee disputes (#17) are high-volume but often overlooked in demonstrations. "
                "The QME billing structure — evaluation fee, record review per page, supplemental reports — "
                "is complex and frequently contested. Tests MLFS compliance, the compensability of "
                "unsolicited supplemental reports, and the QME-as-lien-claimant scenario. "
                "Record review billing at $2/page for 2,800 pages is a common source of MLFS disputes."
            ),
            "scenario_group": "H — Gap-Fillers",
        },
        "second_insurance": None,
    })

    scenarios.append({
        "internal_id": "HG-03",
        "case_params": CaseParameters(
            target_stage="active_treatment",
            claim_response="accepted",
            has_attorney=True,
            eval_type="none",
            has_surgery=False,
            has_psych_component=False,
            has_ur_dispute=True,
            has_liens=False,
            num_body_parts=1,
            complexity="standard",
            injury_type="specific",
            body_part_category="spine",
            resolution_type="random",
        ),
        "applicant": _make_applicant(
            first="Steven",
            last="Clark",
            dob=date(1975, 1, 1),
            city="Los Angeles",
            zipcode="90001",
        ),
        "employer": _make_employer(
            company="Interstate Trucking Corp.",
            position="Long-Haul Truck Driver",
            city="Los Angeles",
            zipcode="90012",
            hire_date=_date_ago(365 * 22),
            hourly_rate=28.00,
            department="Long-Haul Operations",
        ),
        "insurance": _make_insurance(
            carrier="Chubb Insurance Company",
            defense_firm="Jones, Clifford, Johnson & Johnson LLP",
        ),
        "injuries": [
            _make_injury(
                doi=date(2021, 6, 10),
                injury_type=InjuryType.SPECIFIC,
                body_parts=["Lumbar Spine (L4-L5)"],
                icd10_codes=["M96.1", "G89.29"],
                description=(
                    "Post-laminectomy syndrome (M96.1) and chronic pain syndrome (G89.29), "
                    "lumbar spine L4-L5; on stable opioid regimen for 3 years."
                ),
                mechanism="Fell from truck cab step, landed on back.",
            )
        ],
        "treating": _make_physician(
            first="Jennifer",
            last="Adams",
            specialty="Pain Medicine",
            facility="Pacific Pain Management Center",
            city="Los Angeles",
            zipcode="90048",
        ),
        "qme": None,
        "prior_providers": [],
        "venue": "Los Angeles WCAB",
        "judge": "Hon. William Foster",
        "extra_context": {
            "adj_number": "ADJ22678901",
            "employment_duration_years": 22,
            "prior_injuries": (
                "Stable opioid regimen for 3 years — oxycodone 20mg BID + gabapentin 600mg TID. "
                "No dose escalation. No substance abuse history. All urine drug screens compliant."
            ),
            "cdl_restrictions": True,
            "unable_to_work_since_injury": True,
            "ur_dispute": {
                "rfa_treatment": "Continued opioid medication at current dose (oxycodone 20mg BID + gabapentin 600mg TID)",
                "ur_decision": "Denied — mandating 30% dose reduction over 90 days (forced taper)",
                "ur_basis": "MTUS Chronic Pain Medical Treatment Guidelines — forced taper protocol",
                "imr_filed": True,
                "imr_outcome": "Upheld UR taper decision",
                "treating_physician_objections": [
                    "Patient stable on this regimen for 3 years with functional improvement",
                    "Forced tapering risks opioid withdrawal syndrome",
                    "MTUS guidelines recommend individualized assessment, not blanket tapering",
                    "2022 CDC guidance explicitly cautions against forced involuntary tapers",
                ],
                "wcab_petition_pending": True,
                "wcab_petition_basis": "Medical necessity challenge to IMR decision",
            },
            "key_documents": [
                "RFA for continued opioid medication at current dose",
                "UR Denial (mandating 30% taper)",
                "IMR Application",
                "IMR Decision (upholding taper)",
                "Treating physician declaration (opposing forced taper, citing CDC guidance)",
                "3 years of prescription records (showing stable doses, no escalation)",
                "Urine drug screen history (all compliant)",
                "MTUS Chronic Pain Guidelines excerpt",
                "CDC Clinical Practice Guideline (2022, cautioning against forced tapers)",
                "Petition to WCAB challenging IMR (medical necessity)",
            ],
            "wc_issues": ["Opioid/Medication Authorization", "Utilization Review", "IMR", "Chronic Pain Treatment"],
            "educational_notes": (
                "Opioid tapering disputes (#21) are among the most contentious UR issues in modern WC practice. "
                "The tension between MTUS guideline-driven tapering and individual patient needs is a major source "
                "of litigation. Tests the interplay between MTUS guidelines, CDC recommendations, and the treating "
                "physician's clinical judgment. The forced taper scenario has real patient safety implications — "
                "abrupt or involuntary tapering can cause withdrawal syndrome and patient harm. "
                "IMR uphold rate is high; WCAB review of IMR decisions is narrow (fraud, conflict of interest, "
                "or plain error — not de novo medical necessity review)."
            ),
            "scenario_group": "H — Gap-Fillers",
        },
        "second_insurance": None,
    })

    scenarios.append({
        "internal_id": "HG-04",
        "case_params": CaseParameters(
            target_stage="intake",
            claim_response="accepted",
            has_attorney=True,
            eval_type="none",
            has_surgery=False,
            has_psych_component=False,
            has_ur_dispute=False,
            has_liens=False,
            num_body_parts=1,
            complexity="standard",
            injury_type="specific",
            body_part_category="spine",
            resolution_type="random",
        ),
        "applicant": _make_applicant(
            first="Andre",
            last="Williams",
            dob=date(1994, 1, 1),
            city="Los Angeles",
            zipcode="90001",
        ),
        "employer": _make_employer(
            company="Mega Warehouse Corp.",
            position="Warehouse Associate",
            city="Los Angeles",
            zipcode="90012",
            hire_date=_date_ago(365 * 4),
            hourly_rate=22.00,
            department="Warehouse Operations",
        ),
        "insurance": _make_insurance(
            carrier="Accident Fund Insurance Company",
            defense_firm="Fraulob-Brown & Associates",
        ),
        "injuries": [
            _make_injury(
                doi=date(2026, 2, 15),
                injury_type=InjuryType.SPECIFIC,
                body_parts=["Lumbar Spine (L5-S1)"],
                icd10_codes=["M51.26"],
                description="L5-S1 disc protrusion, lumbar spine.",
                mechanism="Lifted pallet jack handle awkwardly, felt immediate low back pain.",
            )
        ],
        "treating": _make_physician(
            first="Mark",
            last="Johnson",
            specialty="Occupational Medicine",
            facility="WorkMed Occupational Health Clinic",
            city="Los Angeles",
            zipcode="90012",
        ),
        "qme": None,
        "prior_providers": [],
        "venue": "Los Angeles WCAB",
        "judge": "Hon. Sandra Lee",
        "extra_context": {
            "adj_number": "ADJ22789012",
            "employment_duration_years": 4,
            "concurrent_employment": {
                "secondary_employer": "Rideshare Platform (Uber/Lyft)",
                "secondary_role": "Rideshare Driver",
                "secondary_hours_per_week": 20,
                "secondary_weekly_earnings_usd": 400,
                "secondary_tax_form": "1099",
                "years_concurrent": 2,
            },
            "td_rate_dispute": {
                "td_rate_warehouse_only_usd_per_week": 633,
                "td_rate_combined_usd_per_week": 900,
                "wage_basis_current": "Warehouse W-2 only ($950/week)",
                "applicant_position": "Rideshare earnings ($400/week) must be included under LC 4453 concurrent employment",
                "carrier_objections": [
                    "Rideshare work is independent contractor work, not 'employment' under the WC code",
                    "Applicant failed to disclose concurrent employment within required timeframe",
                ],
                "lc_4453_concurrent_employment_issue": True,
                "ab5_ic_vs_employee_issue": True,
            },
            "key_documents": [
                "DWC-1 Claim Form",
                "Application for Adjudication",
                "Warehouse wage records (W-2, $950/week)",
                "Rideshare earnings records (1099, ~$400/week average)",
                "TD rate calculation (warehouse only: $633/week vs. combined: $900/week)",
                "LC 4453 concurrent employment brief",
                "Discovery request for rideshare platform classification evidence",
            ],
            "wc_issues": ["Wage/Earnings Calculation", "TD Rate & Duration", "Concurrent Employment", "Gig Economy / AB 5"],
            "educational_notes": (
                "Wage calculation disputes (#24) are present in a large percentage of indemnity cases but rarely "
                "get dedicated attention. Concurrent employment with gig-economy work creates a modern twist on "
                "the classic AWW calculation. LC 4453 requires inclusion of concurrent employment earnings in AWW "
                "when the injury prevents work at both jobs. The IC-vs-employee status of rideshare work intersects "
                "with AB 5 — if the rideshare platform classifies the worker as an employee under AB 5 / Prop 22, "
                "the concurrent employment argument is strengthened. Difference: $633 vs. $900/week TD is significant."
            ),
            "scenario_group": "H — Gap-Fillers",
        },
        "second_insurance": None,
    })

    scenarios.append({
        "internal_id": "HG-05",
        "case_params": CaseParameters(
            target_stage="discovery",
            claim_response="delayed",
            has_attorney=True,
            eval_type="ame",
            has_surgery=True,
            has_psych_component=False,
            has_ur_dispute=False,
            has_liens=False,
            num_body_parts=1,
            complexity="complex",
            injury_type="specific",
            body_part_category="spine",
            resolution_type="random",
        ),
        "applicant": _make_applicant(
            first="Marcus",
            last="Washington",
            dob=date(1980, 1, 1),
            city="Los Angeles",
            zipcode="90001",
        ),
        "employer": _make_employer(
            company="Community General Hospital",
            position="Hospital Orderly",
            city="Los Angeles",
            zipcode="90012",
            hire_date=_date_ago(365 * 12),
            hourly_rate=20.00,
            department="Patient Transport & Orderly Services",
        ),
        "insurance": _make_insurance(
            carrier="Carrier A — Specific Injury Insurer (2024)",
            defense_firm="Laughlin, Falbo, Levy & Moresi LLP",
        ),
        "injuries": [
            _make_injury(
                doi=date(2024, 3, 15),
                injury_type=InjuryType.SPECIFIC,
                body_parts=["Lumbar Spine (L4-L5 Herniation)"],
                icd10_codes=["M51.16"],
                description=(
                    "L4-L5 lumbar disc herniation (M51.16); specific injury claim. "
                    "Also overlapping CT claim ADJ22890124 for multilevel lumbar disease L3-S1 "
                    "(spondylosis M47.816) ending 2025-09-01 under separate carrier."
                ),
                mechanism="Patient lifting incident — felt pop in low back while transferring patient.",
            ),
            _make_injury(
                doi=date(2025, 9, 1),
                injury_type=InjuryType.CUMULATIVE_TRAUMA,
                body_parts=["Lumbar Spine (L3-S1 Multilevel Disease — Spondylosis)"],
                icd10_codes=["M47.816"],
                description=(
                    "Lumbar spondylosis L3-S1 multilevel disease (M47.816); cumulative trauma claim. "
                    "CT period ending 2025-09-01 after 12 years of repetitive patient handling. "
                    "Filed under ADJ22890124 against separate carrier."
                ),
                mechanism="12 years of repetitive patient handling, lifting, and transfers.",
            ),
        ],
        "treating": _make_physician(
            first="Laura",
            last="Kim",
            specialty="Orthopedic Surgery",
            facility="Community General Hospital Orthopedic Clinic",
            city="Los Angeles",
            zipcode="90048",
        ),
        "qme": None,
        "prior_providers": [],
        "venue": "Los Angeles WCAB",
        "judge": "Hon. Paul Hernandez",
        "extra_context": {
            "adj_numbers": {
                "specific_injury": "ADJ22890123",
                "ct_claim": "ADJ22890124",
            },
            "ame": _make_physician(
                first="Charles",
                last="Henderson",
                specialty="Orthopedic Surgery",
                facility="Henderson AME Medical Group",
                city="Los Angeles",
                zipcode="90048",
            ),
            "employment_duration_years": 12,
            "prior_injuries": "Two open claims — specific (2024) + CT (2025) to same lumbar spine body part",
            "multi_carrier_dispute": {
                "carrier_a": "Specific Injury Insurer (2024 policy)",
                "carrier_b": "CT Insurer (covering CT period ending 2025-09-01)",
                "carrier_a_position": (
                    "CT claim should absorb the specific injury — the specific event merely triggered "
                    "symptoms of the underlying CT condition; Carrier B should bear full liability."
                ),
                "carrier_b_position": (
                    "Specific injury was a distinct event with its own causation; CT claim limited to "
                    "period before specific injury; Carrier A should bear liability for the acute herniation."
                ),
                "applicant_situation": "Caught in middle — both carriers delayed benefits while finger-pointing",
                "consolidation_motion_filed": True,
            },
            "injury_dating_dispute": {
                "key_question": (
                    "Is the specific injury (L4-L5 herniation, 2024-03-15) subsumed within the CT "
                    "(L3-S1 multilevel disease), or is it a separate and distinct industrial injury?"
                ),
                "lc_5412_analysis": True,
                "last_injurious_exposure_issue": True,
                "ame_scope": "Evaluating both claims simultaneously — injury dating, causation apportionment between carriers",
            },
            "surgery_performed": True,
            "surgery_type": "Lumbar microdiscectomy (L4-L5)",
            "key_documents": [
                "Application for Adjudication (specific injury, ADJ22890123, naming Carrier A)",
                "Application for Adjudication (CT claim, ADJ22890124, naming Carrier B)",
                "Both carriers' delay letters",
                "AME Report — addressing both claims, injury dating, and subsumption question",
                "Discovery to both carriers (coverage periods, prior claims history)",
                "Consolidation motion (both claims before same WCJ)",
                "Surgical records (lumbar microdiscectomy)",
                "LC 5412 analysis (last injurious exposure, injury dating)",
            ],
            "wc_issues": [
                "Specific vs. CT Overlap / Injury Dating",
                "Apportionment",
                "AOE/COE",
                "Multi-Carrier Disputes",
                "LC 5412 Last Injurious Exposure",
            ],
            "educational_notes": (
                "Overlapping specific and CT claims to the same body part (#25) create the classic "
                "finger-pointing scenario between carriers. The injury dating question — is the specific "
                "injury subsumed within the CT, or is it a separate and distinct event — determines which "
                "carrier (or both) pays. This is one of the most common multi-claim tangles in WC practice, "
                "often requiring AME analysis of both claims simultaneously. "
                "LC 5412 governs the date of injury for CT claims (last date of injurious exposure). "
                "The applicant bears the practical burden of delayed benefits while carriers litigate each other."
            ),
            "scenario_group": "H — Gap-Fillers",
            "second_adj_number": "ADJ22890124",
        },
        "second_insurance": _make_insurance(
            carrier="Carrier B — Cumulative Trauma Insurer (CT period ending 2025-09-01)",
            defense_firm="Mullen & Filippi LLP",
        ),
    })
    return scenarios


# ---------------------------------------------------------------------------
# Case generation
# ---------------------------------------------------------------------------

def generate_case(
    scenario: dict,
    case_number: int,
    fake_gen: FakeDataGenerator,
) -> GeneratedCase:
    """Build a GeneratedCase from a scenario, using the lifecycle engine for document specs."""
    params: CaseParameters = scenario["case_params"]
    resolved_params = params.resolve_random(fake_gen._rng)

    stage = LitigationStage(resolved_params.target_stage)

    # Use the scenario's hand-crafted data
    applicant: GeneratedApplicant = scenario["applicant"]
    employer: GeneratedEmployer = scenario["employer"]
    insurance: GeneratedInsurance = scenario["insurance"]
    injuries: list[GeneratedInjury] = scenario["injuries"]
    treating: GeneratedPhysician = scenario["treating"]
    qme: GeneratedPhysician | None = scenario.get("qme")
    prior_providers: list[GeneratedPhysician] = scenario.get("prior_providers", [])

    # Timeline — build from the first injury's DOI using the lifecycle engine helper
    doi = injuries[0].date_of_injury
    timeline = fake_gen._generate_timeline_from_params(stage, doi, resolved_params)

    # Build the case
    internal_id = scenario["internal_id"]
    case = GeneratedCase(
        case_number=case_number,
        internal_id=internal_id,
        litigation_stage=stage,
        applicant=applicant,
        employer=employer,
        insurance=insurance,
        injuries=injuries,
        treating_physician=treating,
        qme_physician=qme,
        prior_providers=prior_providers,
        timeline=timeline,
        venue=scenario.get("venue", "Los Angeles"),
        judge_name=scenario.get("judge", "Hon. Patricia M. Torres"),
        case_parameters=resolved_params,
    )

    # Generate document specs via the lifecycle engine
    case.document_specs = fake_gen._generate_lifecycle_manifest(case, resolved_params)

    # Inject extra context into each document spec so templates can use it
    extra_ctx = scenario.get("extra_context", {})
    if extra_ctx:
        for doc_spec in case.document_specs:
            doc_spec.context.update(extra_ctx)

    return case


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 70)
    print("  BATCH 3: Attorney Caseload Generation — 47 Custom WC Cases")
    print("=" * 70)
    print()

    # Back up existing progress.db
    if DB_PATH.exists():
        backup_path = DB_PATH.with_suffix(".db.bak_pre_batch3")
        shutil.copy2(DB_PATH, backup_path)
        print(f"  Backed up progress.db -> {backup_path.name}")

    # Initialize
    tracker = ProgressTracker(DB_PATH)
    fake_gen = FakeDataGenerator(seed=2026)  # Batch 3 seed

    scenarios = define_scenarios()
    print(f"  Defined {len(scenarios)} scenarios")
    print()

    # Start a new run
    run_id = tracker.start_run(total_cases=len(scenarios))
    print(f"  Started run #{run_id} with {len(scenarios)} cases")
    print()

    # Generate cases
    cases: list[GeneratedCase] = []
    for i, scenario in enumerate(scenarios):
        case_number = i + 1
        internal_id = scenario["internal_id"]

        try:
            case = generate_case(scenario, case_number, fake_gen)
            cases.append(case)

            # Register in progress DB
            tracker.register_case(
                run_id=run_id,
                internal_id=case.internal_id,
                case_number=case.case_number,
                stage=case.litigation_stage.value,
                applicant_name=case.applicant.full_name,
                employer_name=case.employer.company_name,
                total_docs=len(case.document_specs),
            )
            tracker.mark_case_data_generated(case.internal_id)

            # Register each document
            for j, doc_spec in enumerate(case.document_specs):
                filename = _sanitize_filename(
                    f"{case.internal_id}_{j+1:03d}_{doc_spec.subtype.value}_{doc_spec.doc_date}"
                )
                tracker.register_document(
                    case_internal_id=case.internal_id,
                    filename=filename,
                    subtype=doc_spec.subtype.value,
                    title=doc_spec.title,
                    doc_date=doc_spec.doc_date.isoformat(),
                )

            print(f"  [{internal_id}] {case.applicant.full_name:30s} | {case.litigation_stage.value:18s} | {len(case.document_specs):3d} docs")

        except Exception as e:
            print(f"  [{internal_id}] ERROR generating case: {e}")
            import traceback
            traceback.print_exc()
            continue

    print()
    print(f"  Generated {len(cases)} cases with {sum(len(c.document_specs) for c in cases)} total document specs")
    print()

    # Generate PDFs
    print("  Generating PDFs...")
    print("-" * 70)

    generated = 0
    skipped = 0
    errors = 0

    for case in cases:
        case_dir = OUTPUT_DIR / case.internal_id
        case_dir.mkdir(parents=True, exist_ok=True)

        docs_in_tracker = tracker.get_docs_for_case(case.internal_id)
        doc_filenames = {d["filename"]: d for d in docs_in_tracker}

        for j, doc_spec in enumerate(case.document_specs):
            filename = _sanitize_filename(
                f"{case.internal_id}_{j+1:03d}_{doc_spec.subtype.value}_{doc_spec.doc_date}"
            )
            tracked_doc = doc_filenames.get(filename)

            if tracked_doc and tracked_doc["pdf_generated"]:
                skipped += 1
                continue

            output_path = case_dir / filename

            try:
                template_cls = _load_template_class(doc_spec.template_class)
                template = template_cls(case)
                template.generate(output_path, doc_spec)

                tracker.mark_pdf_generated(
                    case.internal_id, filename, str(output_path)
                )
                generated += 1

            except Exception as e:
                tracker.mark_doc_error(case.internal_id, filename, str(e))
                errors += 1

        # Update case-level tracking
        gen_count = len(case.document_specs) - len(
            tracker.get_ungenerated_docs(case.internal_id)
        )
        tracker.mark_case_pdfs_generated(case.internal_id, gen_count)

        print(f"  [{case.internal_id}] PDFs complete: {gen_count}/{len(case.document_specs)}")

    print()
    print("=" * 70)
    print(f"  PDF GENERATION COMPLETE")
    print(f"    Generated: {generated}")
    print(f"    Skipped:   {skipped}")
    print(f"    Errors:    {errors}")
    print("=" * 70)
    print()

    # Summary
    print("  CASE SUMMARY:")
    print("-" * 70)
    print(f"  {'ID':<8} {'Applicant':<28} {'Stage':<18} {'Docs':>5}")
    print("-" * 70)
    for case in cases:
        print(f"  {case.internal_id:<8} {case.applicant.full_name:<28} {case.litigation_stage.value:<18} {len(case.document_specs):>5}")
    print("-" * 70)
    print(f"  Total: {len(cases)} cases, {sum(len(c.document_specs) for c in cases)} documents")
    print()

    tracker.close()
    print("  Done. Output at:", OUTPUT_DIR)


if __name__ == "__main__":
    main()
