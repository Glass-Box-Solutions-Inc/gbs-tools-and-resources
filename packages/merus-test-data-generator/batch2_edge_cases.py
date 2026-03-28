#!/usr/bin/env python3
"""
Batch 2: Custom edge-case generation for WC test data.

Generates 30 highly customized Workers' Compensation edge cases (B2-001 through
B2-030) spanning death claims, PTD, Kite, split carriers, pro per applicants,
S&W misconduct, lien-heavy cases, and more. Each case is hand-crafted with
realistic California WC data, ICD-10 codes, AMA Guides references, and detailed
injury narratives.

Usage:
    python batch2_edge_cases.py

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
# Scenario definitions — 30 cases
# ---------------------------------------------------------------------------

def define_scenarios() -> list[dict]:
    """Define all 30 case scenarios with full overrides.

    Each scenario dict contains:
        internal_id:   str  — e.g. "B2-001"
        case_params:   CaseParameters — lifecycle engine parameters
        applicant:     GeneratedApplicant
        employer:      GeneratedEmployer
        insurance:     GeneratedInsurance
        injuries:      list[GeneratedInjury]
        treating:      GeneratedPhysician
        qme:           GeneratedPhysician | None
        prior_providers: list[GeneratedPhysician]
        venue:         str
        judge:         str
        extra_context: dict — additional context hints for document templates
        second_insurance: GeneratedInsurance | None — for split-carrier cases
    """
    scenarios: list[dict] = []

    # =========================================================================
    # Category 1: CT + Multiple Specifics with Significant Treatment History
    # =========================================================================

    # --- B2-001: Sexual Assault by Supervisor ---
    scenarios.append({
        "internal_id": "B2-001",
        "case_params": CaseParameters(
            target_stage="settlement",
            injury_type="cumulative_trauma",
            body_part_category="psyche",
            has_attorney=True,
            has_surgery=False,
            has_psych_component=True,
            has_ur_dispute=True,
            ur_decision="denied",
            imr_filed=True,
            imr_outcome="overturned",
            eval_type="qme",
            resolution_type="c_and_r",
            has_liens=False,
            num_body_parts=3,
            complexity="complex",
            claim_response="accepted",
        ),
        "applicant": _make_applicant("Maria", "Delgado", date(1988, 3, 15), "Glendale", "91205"),
        "employer": _make_employer(
            "Pacific Coast Financial Services", "Administrative Assistant",
            "Los Angeles", "90017", hire_date=_date_ago(365 * 4), hourly_rate=24.50,
            department="Human Resources",
        ),
        "insurance": _make_insurance("Hartford Financial Services", "Manning & Kass, Ellrod, Ramirez, Trester LLP"),
        "injuries": [
            _make_injury(
                doi=_date_ago(900),
                injury_type=InjuryType.CUMULATIVE_TRAUMA,
                body_parts=["psyche (PTSD)", "psyche (anxiety)", "psyche (depression)", "psyche (sleep disorder)"],
                icd10_codes=["F43.12", "F41.1", "F32.1", "G47.00"],
                description=(
                    "Cumulative trauma — psyche: PTSD, generalized anxiety disorder, major depressive "
                    "disorder (moderate), and insomnia arising from 18 months of ongoing workplace "
                    "sexual harassment by direct supervisor, including unwanted physical contact, "
                    "sexual comments, threats of termination for non-compliance, and hostile work "
                    "environment. Applicant reported to HR on three occasions with no corrective action. "
                    "CRD complaint filed. Police report #2024-LA-04521 on file."
                ),
                mechanism="Chronic exposure to workplace harassment and hostile work environment",
            ),
            _make_injury(
                doi=_date_ago(730),
                injury_type=InjuryType.SPECIFIC,
                body_parts=["cervical spine", "right wrist"],
                icd10_codes=["M54.2", "S63.501A"],
                description=(
                    "Specific injury — physical assault by supervisor on 03/27/2024: supervisor "
                    "grabbed applicant by the arm and pushed her into a desk, causing cervical spine "
                    "strain and right wrist sprain. Witnessed by coworker. Police report filed."
                ),
                mechanism="Assault by supervisor — pushed into desk causing cervical strain and wrist sprain",
            ),
        ],
        "treating": _make_physician("Rebecca", "Tanaka", "Psychiatry", "Southern California Behavioral Health Center"),
        "qme": _make_physician("Alan", "Bernstein", "Psychiatry", "Forensic Psychiatric Associates"),
        "prior_providers": [
            _make_physician("Catherine", "Reeves", "Psychiatry", "Pasadena Counseling Center", "Pasadena", "91101"),
        ],
        "venue": "Los Angeles",
        "judge": "Hon. Maria L. Gonzalez",
        "extra_context": {
            "prior_treatment_note": "Pre-employment therapy for unrelated generalized anxiety (2018-2020) — creates apportionment issue under LC 4663",
            "gaf_score": 42,
            "police_report_ref": "LAPD Report #2024-LA-04521",
            "crd_complaint_ref": "CRD Case No. 202400-12345",
        },
        "second_insurance": None,
    })

    # --- B2-002: Firefighter with Everything ---
    scenarios.append({
        "internal_id": "B2-002",
        "case_params": CaseParameters(
            target_stage="settlement",
            injury_type="cumulative_trauma",
            body_part_category="spine",
            has_attorney=True,
            has_surgery=True,
            has_psych_component=True,
            has_ur_dispute=True,
            ur_decision="approved",
            imr_filed=False,
            eval_type="qme",
            resolution_type="c_and_r",
            has_liens=True,
            num_body_parts=5,
            complexity="complex",
            claim_response="accepted",
        ),
        "applicant": _make_applicant("Robert", "Callahan", date(1974, 1, 8), "Pasadena", "91101"),
        "employer": _make_employer(
            "City of Los Angeles Fire Department", "Firefighter/Engineer",
            "Los Angeles", "90012", hire_date=_date_ago(365 * 28), hourly_rate=62.50,
            department="Fire Suppression — Station 27",
        ),
        "insurance": _make_insurance("Sedgwick Claims Management", "Adelson, Testan, Brundo, Novell & Jimenez"),
        "injuries": [
            _make_injury(
                doi=_date_ago(1000),
                injury_type=InjuryType.CUMULATIVE_TRAUMA,
                body_parts=[
                    "lumbar spine", "cervical spine",
                    "right knee", "left knee",
                    "right hip", "left hip",
                    "right shoulder", "left shoulder",
                    "psyche (PTSD)",
                    "heart", "lungs",
                ],
                icd10_codes=[
                    "M51.16", "M50.12",
                    "M17.11", "M17.12",
                    "M16.11", "M16.12",
                    "M75.111", "M75.112",
                    "F43.12",
                    "I10", "I51.7",
                    "J45.30",
                    "C67.9",
                ],
                description=(
                    "Cumulative trauma spanning entire 28-year career as firefighter/engineer "
                    "through and including last day worked. Body parts: bilateral knees (bilateral "
                    "total knee arthroplasty performed), bilateral hips (right total hip arthroplasty "
                    "performed), bilateral shoulders (left shoulder arthroscopy, right rotator cuff "
                    "repair), cervical spine (multilevel DDD with radiculopathy C5-6/C6-7), lumbar "
                    "spine (L4-5 posterior lumbar interbody fusion), psyche (severe PTSD from "
                    "decades of traumatic exposures — house fires with fatalities, pediatric "
                    "drownings, mass casualty incidents — GAF 38), heart (hypertension with left "
                    "ventricular hypertrophy — LC 3212 presumption), lungs (occupational asthma "
                    "with FEV1 65% predicted from smoke/chemical exposure), and bladder cancer "
                    "(diagnosed 2023, now in remission — LC 3212.1 cancer presumption). "
                    "All statutory presumptions apply: cancer (3212.1), heart/hypertension (3212), "
                    "PTSD (3212.15). Pre-employment physicals document excellent health at hire."
                ),
                mechanism="28 years of cumulative occupational exposure as firefighter — heavy physical labor, toxic smoke/chemical exposure, and chronic psychological trauma",
            ),
        ],
        "treating": _make_physician("Jonathan", "Park", "Orthopedic Surgery", "Pacific Orthopedic & Spine Center"),
        "qme": _make_physician("Steven", "Goldberg", "Orthopedic Surgery", "Southern California QME Medical Group"),
        "prior_providers": [
            _make_physician("Lisa", "Chen", "Pain Management", "Harbor Pain Management Clinic"),
            _make_physician("Marcus", "Williams", "Psychiatry", "Glendale Psychiatric Associates", "Glendale", "91205"),
            _make_physician("Richard", "Patel", "Neurosurgery", "Sierra Neurosurgical Institute"),
            _make_physician("Anna", "Kim", "Internal Medicine", "Central Valley Medical Group"),
            _make_physician("David", "Morales", "Physical Medicine & Rehabilitation (PM&R)", "Golden Gate Rehabilitation Center"),
        ],
        "venue": "Los Angeles",
        "judge": "Hon. Robert K. Nakamura",
        "extra_context": {
            "gaf_score": 38,
            "ama_guides_dre_cervical": "DRE III — 15% WPI",
            "ama_guides_dre_lumbar": "DRE IV — 20% WPI",
            "bilateral_tka_wpi": "8% WPI each (16% bilateral)",
            "right_tha_wpi": "10% WPI",
            "shoulders_wpi": "6-8% WPI each",
            "psych_wpi": "35% WPI (GAF 38)",
            "cardiovascular_wpi": "Class 2 — 15% WPI (AMA Guides Ch.4)",
            "pulmonary_wpi": "Class 2 — 30% WPI (FEV1 65% predicted)",
            "cancer_presumption": "LC 3212.1 — bladder cancer, diagnosed during employment, now in remission",
            "combination_method": "Kite case — combined WPI exceeds 65% before age/occupation adjustments",
        },
        "second_insurance": None,
    })

    # =========================================================================
    # Category 2: Death Claims
    # =========================================================================

    # --- B2-003: Death with Dubious AOE/COE ---
    scenarios.append({
        "internal_id": "B2-003",
        "case_params": CaseParameters(
            target_stage="discovery",
            injury_type="death",
            body_part_category="internal",
            has_attorney=True,
            has_surgery=False,
            has_psych_component=False,
            has_ur_dispute=False,
            eval_type="qme",
            resolution_type="pending",
            has_liens=True,
            num_body_parts=2,
            complexity="standard",
            claim_response="denied",
        ),
        "applicant": _make_applicant("Gerald", "Thornton", date(1968, 7, 22), "Riverside", "92501"),
        "employer": _make_employer(
            "Central Valley Distribution LLC", "Warehouse Supervisor",
            "Riverside", "92501", hire_date=_date_ago(365 * 12), hourly_rate=32.00,
            department="Warehouse Operations",
        ),
        "insurance": _make_insurance("Zenith Insurance Company", "Shaw, Jacobsmeyer, Crain & Claffey"),
        "injuries": [
            _make_injury(
                doi=_date_ago(730),
                injury_type=InjuryType.SPECIFIC,
                body_parts=["lumbar spine"],
                icd10_codes=["M54.5", "M51.16"],
                description=(
                    "Original industrial injury (2023): lumbar disc herniation at L4-5 and L5-S1 "
                    "from heavy lifting. Treated with epidural injections and physical therapy. "
                    "Placed on chronic opioid pain management (Oxycodone 10mg Q6H). No surgical "
                    "intervention — UR denied fusion request."
                ),
                mechanism="Heavy lifting — 75 lb box, acute onset low back pain with radiculopathy",
            ),
            _make_injury(
                doi=_date_ago(180),
                injury_type=InjuryType.DEATH,
                body_parts=["heart"],
                icd10_codes=["I46.9", "I25.10"],
                description=(
                    "Death claim — applicant died of cardiac arrest at home on a non-work day. "
                    "Found unresponsive by spouse at 6:15 AM. Paramedics pronounced dead at scene. "
                    "Autopsy: acute myocardial infarction with underlying atherosclerotic coronary "
                    "artery disease. Family history of heart disease (father died at 55 of MI). "
                    "Applicant had been on chronic opioid therapy for industrial lumbar injury. "
                    "Estate argues: chronic pain from industrial injury caused chronic stress, "
                    "insomnia, deconditioning, and opioid-related cardiac risk. Defense argues: "
                    "pre-existing atherosclerotic disease and family history are non-industrial. "
                    "QME in cardiology needed to opine on causation. "
                    "Owed benefits at death: $45,000 in unpaid PD advances and $120,000 in "
                    "outstanding medical treatment liens."
                ),
                mechanism="Cardiac arrest at home — causation disputed (AOE/COE)",
            ),
        ],
        "treating": _make_physician("Andrew", "Marsh", "Pain Management", "Inland Empire Orthopedic Specialists", "Riverside", "92501"),
        "qme": _make_physician("Helen", "Strauss", "Internal Medicine", "Cardiology QME Associates", "Riverside", "92501"),
        "prior_providers": [
            _make_physician("Kevin", "Orozco", "Internal Medicine", "Riverside Community Health Center", "Riverside", "92501"),
        ],
        "venue": "Inland Empire (Riverside)",
        "judge": "Hon. Richard H. Vasquez",
        "extra_context": {
            "death_claim": True,
            "spouse_dependent": "Total dependent — Sandra Thornton, age 56",
            "adult_child_dependent": "Partial dependent — Brian Thornton, age 28",
            "unpaid_pd_advances": 45000,
            "outstanding_liens": 120000,
            "aoe_coe_disputed": True,
            "autopsy_report_ref": "Riverside County Coroner Case #2025-RC-1847",
        },
        "second_insurance": None,
    })

    # --- B2-004: Death with Disabled Minor Child ---
    scenarios.append({
        "internal_id": "B2-004",
        "case_params": CaseParameters(
            target_stage="discovery",
            injury_type="death",
            body_part_category="head",
            has_attorney=True,
            has_surgery=False,
            has_psych_component=False,
            has_ur_dispute=False,
            eval_type="none",
            resolution_type="pending",
            has_liens=False,
            num_body_parts=1,
            complexity="standard",
            claim_response="accepted",
        ),
        "applicant": _make_applicant("Jessica", "Ramirez", date(1992, 5, 10), "San Bernardino", "92401"),
        "employer": _make_employer(
            "Swinerton Incorporated", "Construction Laborer",
            "San Bernardino", "92401", hire_date=_date_ago(365 * 3), hourly_rate=26.00,
            department="Construction — Commercial Division",
        ),
        "insurance": _make_insurance("Republic Indemnity", "Laughlin, Falbo, Levy & Moresi LLP"),
        "injuries": [
            _make_injury(
                doi=_date_ago(270),
                injury_type=InjuryType.DEATH,
                body_parts=["head/brain (TBI)"],
                icd10_codes=["W12.XXXA", "S06.5X0A"],
                description=(
                    "Fatal specific injury — fall from scaffolding at commercial construction site. "
                    "Scaffolding lacked required guardrails and toeboards per Cal/OSHA Title 8 "
                    "Section 1635. Applicant fell approximately 22 feet to concrete surface below. "
                    "Sustained traumatic subdural hemorrhage. Transported to Loma Linda University "
                    "Medical Center, pronounced dead on arrival. Cal/OSHA investigation opened "
                    "(Inspection #1234567). Employer had prior Cal/OSHA citations for fall "
                    "protection violations within previous 12 months. "
                    "Dependents: spouse (Marco Ramirez, total dependent), disabled child (Sofia "
                    "Ramirez, age 8, Down syndrome — total dependent, incapacitated per LC 4703.5), "
                    "minor child (Diego Ramirez, age 12, total dependent). "
                    "Death benefit: $320,000 minimum (3+ total dependents). LC 4703.5 extended "
                    "benefits for incapacitated child beyond normal cap. "
                    "Potential LC 4553 Serious & Willful misconduct claim — employer had documented "
                    "safety violations."
                ),
                mechanism="Fall from scaffolding (22 feet) — employer safety violation, no guardrails",
            ),
        ],
        "treating": _make_physician("N/A", "N/A", "Emergency Medicine", "Loma Linda University Medical Center", "Loma Linda", "92354"),
        "qme": None,
        "prior_providers": [],
        "venue": "San Bernardino",
        "judge": "Hon. Steven P. Garcia",
        "extra_context": {
            "death_claim": True,
            "cal_osha_inspection": "Inspection #1234567",
            "lc_4553_petition": "Serious & Willful misconduct — scaffolding safety violations documented",
            "lc_132a": False,
            "death_benefit": 320000,
            "disabled_child": "Sofia Ramirez, age 8, Down syndrome — LC 4703.5 incapacitated child benefits",
            "spouse_dependent": "Marco Ramirez — total dependent",
            "minor_child_dependent": "Diego Ramirez, age 12 — total dependent",
        },
        "second_insurance": None,
    })

    # =========================================================================
    # Category 3: PTD with VR Experts
    # =========================================================================

    # --- B2-005: Strong 100% PTD Case ---
    scenarios.append({
        "internal_id": "B2-005",
        "case_params": CaseParameters(
            target_stage="medical_legal",
            injury_type="cumulative_trauma",
            body_part_category="spine",
            has_attorney=True,
            has_surgery=True,
            has_psych_component=True,
            has_ur_dispute=True,
            ur_decision="denied",
            imr_filed=True,
            imr_outcome="upheld",
            eval_type="qme",
            resolution_type="pending",
            has_liens=True,
            num_body_parts=4,
            complexity="complex",
            claim_response="accepted",
        ),
        "applicant": _make_applicant("Miguel", "Cervantes", date(1965, 9, 3), "Pomona", "91766"),
        "employer": _make_employer(
            "UPS Supply Chain Solutions", "Warehouse Laborer",
            "Ontario", "91761", hire_date=_date_ago(365 * 18), hourly_rate=18.50,
            department="Warehouse Operations",
        ),
        "insurance": _make_insurance("EMPLOYERS", "Hanna, Brophy, MacLean, McAleer & Jensen LLP"),
        "injuries": [
            _make_injury(
                doi=_date_ago(850),
                injury_type=InjuryType.CUMULATIVE_TRAUMA,
                body_parts=[
                    "lumbar spine", "cervical spine",
                    "right shoulder", "left shoulder",
                    "psyche (depression)",
                ],
                icd10_codes=["M51.16", "M50.12", "M75.111", "M75.112", "F32.1"],
                description=(
                    "Cumulative trauma — 18 years of heavy warehouse labor. Lumbar spine: multilevel "
                    "DDD at L3-4, L4-5, L5-S1 with two prior surgeries (L4-5 laminectomy 2020, L4-5 "
                    "posterior fusion with instrumentation 2022). Cervical spine: C5-6 radiculopathy "
                    "with EMG-confirmed right C6 nerve root compression. Bilateral shoulders: "
                    "bilateral rotator cuff tears (full-thickness right, partial-thickness left). "
                    "Psyche: major depressive disorder and chronic pain syndrome secondary to "
                    "industrial injuries. Combined WPI exceeds 65% before age/occupation adjustments. "
                    "Applicant: Spanish-speaking only, 8th grade education from Mexico, no computer "
                    "skills, no transferable skills outside manual labor. "
                    "Applicant VR Expert (Dr. Juanita Flores): applicant is 'not feasibly employable' "
                    "in open labor market — DFEC analysis shows pre-injury $18.50/hr warehouse work "
                    "vs. $0 post-injury earning capacity. "
                    "Defense VR Expert (Dr. Mark Henderson): identifies 3 sedentary jobs 'within "
                    "restrictions' — applicant expert rebuts each as infeasible given language "
                    "barrier, education level, and combined restrictions. "
                    "Ogilvie rebuttal of PDRS — vocational evidence demonstrates loss of earning "
                    "capacity exceeds scheduled rating."
                ),
                mechanism="18 years of repetitive heavy lifting, bending, twisting, and overhead work in warehouse environment",
            ),
        ],
        "treating": _make_physician("Ricardo", "Fuentes", "Orthopedic Surgery", "Inland Empire Orthopedic Specialists", "Pomona", "91766"),
        "qme": _make_physician("William", "Abramson", "Orthopedic Surgery", "Southern California QME Medical Group"),
        "prior_providers": [
            _make_physician("Elena", "Vasquez", "Pain Management", "Southern California Pain Institute"),
            _make_physician("Peter", "Chang", "Neurosurgery", "Sierra Neurosurgical Institute"),
            _make_physician("Diana", "Torres", "Psychiatry", "Glendale Psychiatric Associates", "Glendale", "91205"),
            _make_physician("Frank", "Nguyen", "Physical Medicine & Rehabilitation (PM&R)", "Golden Gate Rehabilitation Center"),
        ],
        "venue": "Pomona",
        "judge": "Hon. Christine R. Patel",
        "extra_context": {
            "ptd_claim": True,
            "combined_wpi": "65%+ before adjustments",
            "vr_expert_applicant": "Dr. Juanita Flores — not feasibly employable",
            "vr_expert_defense": "Dr. Mark Henderson — 3 sedentary jobs identified (all rebutted)",
            "ogilvie_rebuttal": True,
            "dfec_analysis": "Pre-injury $18.50/hr vs. $0 post-injury",
            "language_barrier": "Spanish-speaking only",
            "education": "8th grade (Mexico)",
            "surgical_history": "L4-5 laminectomy (2020), L4-5 posterior fusion (2022)",
        },
        "second_insurance": None,
    })

    # --- B2-006: Weak PTD Case ---
    scenarios.append({
        "internal_id": "B2-006",
        "case_params": CaseParameters(
            target_stage="discovery",
            injury_type="specific",
            body_part_category="spine",
            has_attorney=True,
            has_surgery=True,
            has_psych_component=False,
            has_ur_dispute=False,
            eval_type="qme",
            resolution_type="pending",
            has_liens=False,
            num_body_parts=3,
            complexity="standard",
            claim_response="accepted",
        ),
        "applicant": _make_applicant("Christine", "O'Brien", date(1982, 11, 28), "San Diego", "92101"),
        "employer": _make_employer(
            "Kaiser Permanente", "Registered Nurse (BSN)",
            "San Diego", "92101", hire_date=_date_ago(365 * 10), hourly_rate=52.00,
            department="Emergency Department",
        ),
        "insurance": _make_insurance("ICW Group", "LaFollette, Johnson, DeHaas, Fesler & Ames"),
        "injuries": [
            _make_injury(
                doi=_date_ago(540),
                injury_type=InjuryType.SPECIFIC,
                body_parts=["lumbar spine"],
                icd10_codes=["M51.16", "M54.41"],
                description=(
                    "Specific injury — lumbar disc herniation at L4-5 from lifting obese patient "
                    "during transfer. Had L4-5 microdiscectomy with good surgical outcome. "
                    "Post-surgical restrictions: no lifting over 25 lbs, no prolonged standing "
                    "over 30 minutes."
                ),
                mechanism="Patient lift — lifting 280 lb patient during bed-to-gurney transfer",
            ),
            _make_injury(
                doi=_date_ago(540),
                injury_type=InjuryType.CUMULATIVE_TRAUMA,
                body_parts=["right wrist", "left wrist"],
                icd10_codes=["G56.01", "G56.02"],
                description=(
                    "Cumulative trauma — bilateral carpal tunnel syndrome from years of charting, "
                    "IV starts, and repetitive hand/wrist motions in nursing. EMG confirms moderate "
                    "bilateral CTS. Conservative management with splinting and ergonomic adjustments."
                ),
                mechanism="Repetitive hand/wrist motions from nursing duties over 10-year career",
            ),
        ],
        "treating": _make_physician("Grace", "Kim", "Orthopedic Surgery", "SoCal Sports Medicine & Orthopedics", "San Diego", "92101"),
        "qme": _make_physician("Howard", "Feldman", "Orthopedic Surgery", "Pacific Orthopedic & Spine Center"),
        "prior_providers": [
            _make_physician("Natalie", "Santos", "Physical Therapy", "Bay Area Neurology Associates", "San Diego", "92101"),
        ],
        "venue": "San Diego",
        "judge": "Hon. Diane F. Johnson",
        "extra_context": {
            "ptd_claim": True,
            "weak_ptd": True,
            "combined_wpi": "~35%",
            "vr_expert_applicant": "Argues nursing career is over, limited transferable skills",
            "vr_expert_defense": "Identifies 5+ sedentary/light healthcare jobs: case management, UR nursing, health education, medical records, telehealth triage",
            "education": "BSN (Bachelor of Science in Nursing)",
            "language": "English fluent",
            "age": 44,
        },
        "second_insurance": None,
    })

    # =========================================================================
    # Category 4: Kite Cases
    # =========================================================================

    # --- B2-007: Kite — Spine + Psych Synergy ---
    scenarios.append({
        "internal_id": "B2-007",
        "case_params": CaseParameters(
            target_stage="settlement",
            injury_type="cumulative_trauma",
            body_part_category="spine",
            has_attorney=True,
            has_surgery=False,
            has_psych_component=True,
            has_ur_dispute=False,
            eval_type="qme",
            resolution_type="stipulations",
            has_liens=False,
            num_body_parts=3,
            complexity="standard",
            claim_response="accepted",
        ),
        "applicant": _make_applicant("Vincent", "Nguyen", date(1977, 6, 14), "Long Beach", "90802"),
        "employer": _make_employer(
            "FedEx Ground", "Delivery Driver",
            "Long Beach", "90810", hire_date=_date_ago(365 * 14), hourly_rate=27.50,
            department="Delivery Operations",
        ),
        "insurance": _make_insurance("Travelers Insurance", "Pollak, Vida & Barer LLP"),
        "injuries": [
            _make_injury(
                doi=_date_ago(800),
                injury_type=InjuryType.CUMULATIVE_TRAUMA,
                body_parts=["lumbar spine", "cervical spine", "psyche (depression)"],
                icd10_codes=["M51.16", "M50.12", "F32.1"],
                description=(
                    "CT: lumbar spine (DRE III, 10% WPI) + cervical spine (DRE II, 5% WPI) + "
                    "psyche (depression from chronic pain, GAF 55, 15% WPI). Standard CVC "
                    "combination yields ~27%. Applicant argues Kite rebuttal: spine pain amplifies "
                    "psychiatric symptoms (insomnia, inability to exercise, social isolation), and "
                    "psychiatric condition amplifies pain perception — synergistic overlap on ADLs "
                    "(sleep, social functioning, self-care). QME provides supplemental report with "
                    "ADL-by-ADL analysis per Vigil v. County of Kern. Additive combination yields "
                    "30% (spine 15% + psych 15%)."
                ),
                mechanism="14 years of delivery driving — repetitive loading/unloading, prolonged sitting, vibration exposure",
            ),
        ],
        "treating": _make_physician("Paul", "Ishikawa", "Pain Management", "Harbor Pain Management Clinic", "Long Beach", "90802"),
        "qme": _make_physician("Robert", "Silverstein", "Physical Medicine & Rehabilitation (PM&R)", "Golden Gate Rehabilitation Center"),
        "prior_providers": [
            _make_physician("Sandra", "Lee", "Psychiatry", "Glendale Psychiatric Associates", "Long Beach", "90802"),
            _make_physician("James", "Foster", "Physical Therapy", "Capitol Physical Therapy Associates"),
        ],
        "venue": "Long Beach",
        "judge": "Hon. Thomas E. Murphy",
        "extra_context": {
            "kite_case": True,
            "cvc_combined": "~27%",
            "additive_combined": "30%",
            "kite_argument": "Synergistic overlap — spine pain amplifies psych, psych amplifies pain perception",
            "vigil_adl_analysis": True,
            "gaf_score": 55,
            "lumbar_dre": "DRE III — 10% WPI",
            "cervical_dre": "DRE II — 5% WPI",
            "psych_wpi": "15% WPI (GAF 55)",
        },
        "second_insurance": None,
    })

    # --- B2-008: Kite — Multiple Extremities ---
    scenarios.append({
        "internal_id": "B2-008",
        "case_params": CaseParameters(
            target_stage="medical_legal",
            injury_type="cumulative_trauma",
            body_part_category="upper_extremity",
            has_attorney=True,
            has_surgery=True,
            has_psych_component=False,
            has_ur_dispute=False,
            eval_type="qme",
            resolution_type="pending",
            has_liens=False,
            num_body_parts=5,
            complexity="standard",
            claim_response="accepted",
        ),
        "applicant": _make_applicant("Dorothy", "Hansen", date(1971, 4, 20), "Anaheim", "92801"),
        "employer": _make_employer(
            "West Coast Assembly Corp.", "Assembly Line Worker",
            "Anaheim", "92801", hire_date=_date_ago(365 * 22), hourly_rate=21.00,
            department="Manufacturing Assembly",
        ),
        "insurance": _make_insurance("Applied Underwriters", "Downs, Ward, Bender & Dantonio"),
        "injuries": [
            _make_injury(
                doi=_date_ago(750),
                injury_type=InjuryType.CUMULATIVE_TRAUMA,
                body_parts=[
                    "right wrist", "left wrist",
                    "right shoulder", "left shoulder",
                    "lumbar spine",
                ],
                icd10_codes=["G56.01", "G56.02", "M75.111", "M75.112", "M51.16"],
                description=(
                    "CT: bilateral wrists (carpal tunnel, 5% WPI each after surgery), bilateral "
                    "shoulders (rotator cuff tears, 8% WPI each), lumbar spine (DRE II, 5% WPI). "
                    "5 body parts, CVC combined ~27%. Kite argument: bilateral upper extremity "
                    "impairments amplify each other — cannot compensate with one arm when both are "
                    "impaired. Combined with spine limitations, all manual labor occupations are "
                    "eliminated. Additive combination: 31%. VR Expert testimony supports that "
                    "combined bilateral impairments eliminate all manual occupations. "
                    "Bilateral CTS release surgeries performed with good outcomes."
                ),
                mechanism="22 years of repetitive assembly work — bilateral upper extremity and spinal strain",
            ),
        ],
        "treating": _make_physician("Teresa", "Yamada", "Orthopedic Surgery", "SoCal Sports Medicine & Orthopedics", "Anaheim", "92801"),
        "qme": _make_physician("Norman", "Roth", "Physical Medicine & Rehabilitation (PM&R)", "Pacific Orthopedic & Spine Center"),
        "prior_providers": [
            _make_physician("Gary", "Rivera", "Hand Surgery", "Bay Area Neurology Associates"),
            _make_physician("Monica", "Tran", "Physical Therapy", "Capitol Physical Therapy Associates"),
        ],
        "venue": "Anaheim",
        "judge": "Hon. Angela D. Kim",
        "extra_context": {
            "kite_case": True,
            "cvc_combined": "~27%",
            "additive_combined": "31%",
            "kite_argument": "Bilateral upper extremity impairments amplify each other — cannot compensate",
            "vr_expert_supports_kite": True,
        },
        "second_insurance": None,
    })

    # =========================================================================
    # Category 5: Multiple Injuries Same Upper Extremity
    # =========================================================================

    # --- B2-009: Serial Right Shoulder Injuries ---
    scenarios.append({
        "internal_id": "B2-009",
        "case_params": CaseParameters(
            target_stage="discovery",
            injury_type="specific",
            body_part_category="upper_extremity",
            has_attorney=True,
            has_surgery=True,
            has_psych_component=False,
            has_ur_dispute=False,
            eval_type="qme",
            resolution_type="pending",
            has_liens=False,
            num_body_parts=1,
            complexity="standard",
            claim_response="accepted",
        ),
        "applicant": _make_applicant("Derek", "Sullivan", date(1988, 2, 17), "Ventura", "93001"),
        "employer": _make_employer(
            "Swinerton Incorporated", "Electrician",
            "Ventura", "93001", hire_date=_date_ago(365 * 8), hourly_rate=42.00,
            department="Electrical — Commercial",
        ),
        "insurance": _make_insurance("Liberty Mutual", "Mitchell & Associates"),
        "injuries": [
            _make_injury(
                doi=_date_ago(1095),
                injury_type=InjuryType.SPECIFIC,
                body_parts=["right shoulder"],
                icd10_codes=["M75.111"],
                description=(
                    "First specific injury (2022): right shoulder rotator cuff tear from fall off "
                    "ladder. Had arthroscopic rotator cuff repair. Settled at 8% PD (prior award). "
                    "Case ADJ-2022-PRIOR, closed."
                ),
                mechanism="Fall from ladder — acute right rotator cuff tear",
            ),
            _make_injury(
                doi=_date_ago(365),
                injury_type=InjuryType.SPECIFIC,
                body_parts=["right shoulder"],
                icd10_codes=["M75.111", "S43.431A"],
                description=(
                    "Second specific injury (2024): re-tear of right rotator cuff plus labral tear "
                    "from another fall at worksite. Same body region (right upper extremity) — "
                    "LC 4664(c) applies. Prior 8% award must be deducted from current rating. "
                    "Current QME rates right shoulder at 14% WPI. Net additional PD: 14% - 8% = 6%. "
                    "QME must address: new and separate injury vs. aggravation of prior?"
                ),
                mechanism="Fall at worksite — re-tear of previously repaired right rotator cuff plus new labral tear",
            ),
        ],
        "treating": _make_physician("Brian", "McAllister", "Orthopedic Surgery", "SoCal Sports Medicine & Orthopedics", "Ventura", "93001"),
        "qme": _make_physician("Laura", "Hoffman", "Orthopedic Surgery", "Pacific Orthopedic & Spine Center"),
        "prior_providers": [],
        "venue": "Oxnard",
        "judge": "Hon. Karen M. Yamamoto",
        "extra_context": {
            "lc_4664c": True,
            "prior_award": "8% PD — right shoulder (2022, ADJ-2022-PRIOR)",
            "current_qme_rating": "14% WPI right shoulder",
            "net_additional_pd": "6% (14% - 8% prior)",
            "issue": "New and separate injury vs. aggravation of prior",
        },
        "second_insurance": None,
    })

    # --- B2-010: Right Arm — Shoulder + Elbow + Wrist ---
    scenarios.append({
        "internal_id": "B2-010",
        "case_params": CaseParameters(
            target_stage="medical_legal",
            injury_type="specific",
            body_part_category="upper_extremity",
            has_attorney=True,
            has_surgery=True,
            has_psych_component=False,
            has_ur_dispute=False,
            eval_type="qme",
            resolution_type="pending",
            has_liens=False,
            num_body_parts=1,
            complexity="standard",
            claim_response="accepted",
        ),
        "applicant": _make_applicant("Angela", "Petrov", date(1984, 8, 5), "Glendale", "91205"),
        "employer": _make_employer(
            "Salon Beverly Hills", "Hairdresser/Stylist",
            "Beverly Hills", "90210", hire_date=_date_ago(365 * 12), hourly_rate=22.00,
            department="Salon Operations",
        ),
        "insurance": _make_insurance("AmTrust Financial Services", "Bradford & Barthel LLP"),
        "injuries": [
            _make_injury(
                doi=_date_ago(1825),
                injury_type=InjuryType.SPECIFIC,
                body_parts=["right wrist"],
                icd10_codes=["G56.01"],
                description=(
                    "First injury (2020): right wrist carpal tunnel syndrome from repetitive "
                    "hairstyling motions. Had carpal tunnel release surgery. Settled at 5% PD "
                    "(prior award #1)."
                ),
                mechanism="Repetitive hairstyling — cutting, blow-drying, and styling motions",
            ),
            _make_injury(
                doi=_date_ago(1095),
                injury_type=InjuryType.SPECIFIC,
                body_parts=["right elbow"],
                icd10_codes=["M77.11"],
                description=(
                    "Second injury (2022): right lateral epicondylitis from continued repetitive "
                    "work. Conservative treatment with cortisone injections and PT. Settled at 3% PD "
                    "(prior award #2)."
                ),
                mechanism="Repetitive elbow motions — blow-drying and styling",
            ),
            _make_injury(
                doi=_date_ago(365),
                injury_type=InjuryType.SPECIFIC,
                body_parts=["right shoulder"],
                icd10_codes=["M75.111"],
                description=(
                    "Third injury (2024): right shoulder rotator cuff tear — current claim. "
                    "All three injuries in same body region (right upper extremity). "
                    "LC 4664(c) cumulative PD cap of 100% for the region. "
                    "Current QME rates shoulder at 12% WPI. Prior awards to deduct: 5% + 3% = 8%. "
                    "Net additional PD: 12% - 8% = 4%. But applicant argues the prior conditions "
                    "were worsened by the new injury — LC 4663 apportionment dispute."
                ),
                mechanism="Overhead reaching and repetitive arm motions during hairstyling",
            ),
        ],
        "treating": _make_physician("Samantha", "Lee", "Orthopedic Surgery", "SoCal Sports Medicine & Orthopedics", "Beverly Hills", "90210"),
        "qme": _make_physician("George", "Whitfield", "Orthopedic Surgery", "Pacific Orthopedic & Spine Center"),
        "prior_providers": [
            _make_physician("Nancy", "Cruz", "Hand Surgery", "Bay Area Neurology Associates"),
        ],
        "venue": "Los Angeles",
        "judge": "Hon. Sarah J. Chen",
        "extra_context": {
            "lc_4664c": True,
            "prior_award_1": "5% PD — right wrist CTS (2020)",
            "prior_award_2": "3% PD — right elbow epicondylitis (2022)",
            "current_qme_rating": "12% WPI right shoulder",
            "net_additional_pd": "4% (12% - 5% - 3%)",
            "lc_4663_dispute": "Applicant argues prior conditions worsened by new injury",
        },
        "second_insurance": None,
    })

    # =========================================================================
    # Category 6: Pro Per Applicants
    # =========================================================================

    # --- B2-011: Pro Per from Start ---
    scenarios.append({
        "internal_id": "B2-011",
        "case_params": CaseParameters(
            target_stage="active_treatment",
            injury_type="specific",
            body_part_category="lower_extremity",
            has_attorney=False,
            has_surgery=False,
            has_psych_component=False,
            has_ur_dispute=True,
            ur_decision="denied",
            imr_filed=False,
            eval_type="none",
            resolution_type="pending",
            has_liens=False,
            num_body_parts=1,
            complexity="standard",
            claim_response="delayed",
        ),
        "applicant": _make_applicant("Tyler", "Brooks", date(1997, 10, 12), "Stockton", "95202"),
        "employer": _make_employer(
            "Home Depot", "Retail Stock Clerk",
            "Stockton", "95202", hire_date=_date_ago(365 * 2), hourly_rate=17.50,
            department="Retail — Lumber",
        ),
        "insurance": _make_insurance("Kinsale Insurance Company", "Shaw, Jacobsmeyer, Crain & Claffey"),
        "injuries": [
            _make_injury(
                doi=_date_ago(180),
                injury_type=InjuryType.SPECIFIC,
                body_parts=["right ankle"],
                icd10_codes=["S93.401A"],
                description=(
                    "Simple specific injury — right ankle sprain from fall off stepladder in "
                    "lumber section. Conservative treatment only (splint, PT, NSAIDs). No surgery. "
                    "Applicant filed claim without attorney — attorneys declined representation "
                    "due to low case value. Missed IMR deadline on UR denial for PT continuation. "
                    "DWC Information & Assistance officer involved to help navigate system. "
                    "Procedurally messy — missed deadlines, incomplete paperwork."
                ),
                mechanism="Fall from stepladder in retail store — right ankle inversion sprain",
            ),
        ],
        "treating": _make_physician("Keith", "Donovan", "Physical Medicine & Rehabilitation (PM&R)", "Central Valley Medical Group", "Stockton", "95202"),
        "qme": None,
        "prior_providers": [],
        "venue": "Stockton",
        "judge": "Hon. James T. O'Brien",
        "extra_context": {
            "pro_per": True,
            "reason_no_attorney": "Low-value case — attorneys declined representation",
            "missed_imr_deadline": True,
            "dwc_ia_involved": True,
        },
        "second_insurance": None,
    })

    # --- B2-012: Fired Attorney Mid-Case ---
    scenarios.append({
        "internal_id": "B2-012",
        "case_params": CaseParameters(
            target_stage="medical_legal",
            injury_type="cumulative_trauma",
            body_part_category="spine",
            has_attorney=False,
            has_surgery=False,
            has_psych_component=False,
            has_ur_dispute=False,
            eval_type="qme",
            resolution_type="pending",
            has_liens=True,
            num_body_parts=3,
            complexity="standard",
            claim_response="accepted",
        ),
        "applicant": _make_applicant("Brenda", "Hawkins", date(1979, 3, 25), "Sacramento", "95814"),
        "employer": _make_employer(
            "Sacramento Unified School District", "School Bus Driver",
            "Sacramento", "95814", hire_date=_date_ago(365 * 15), hourly_rate=24.00,
            department="Transportation",
        ),
        "insurance": _make_insurance("Sedgwick Claims Management", "Laughlin, Falbo, Levy & Moresi LLP"),
        "injuries": [
            _make_injury(
                doi=_date_ago(720),
                injury_type=InjuryType.CUMULATIVE_TRAUMA,
                body_parts=["lumbar spine", "right knee", "left knee"],
                icd10_codes=["M51.16", "M23.211", "M23.212"],
                description=(
                    "CT: lumbar spine (DDD L4-5, L5-S1 from prolonged sitting/vibration) plus "
                    "bilateral knees (meniscal degeneration from repetitive bus pedal operation and "
                    "entry/exit from driver seat). Conservative treatment for all body parts. "
                    "Had attorney (Law Offices of Martin & Associates) for first 18 months, then "
                    "fired them over disagreement about settlement value — applicant felt attorney "
                    "was pushing for quick settlement below fair value. Attorney filed fee lien "
                    "against the case. Applicant now pro per and struggling with discovery deadlines. "
                    "Documents include substitution of attorney filing and attorney lien filing."
                ),
                mechanism="15 years of school bus driving — prolonged sitting, vibration, repetitive pedal operation",
            ),
        ],
        "treating": _make_physician("Harold", "Patterson", "Orthopedic Surgery", "Capitol Physical Therapy Associates", "Sacramento", "95814"),
        "qme": _make_physician("Janet", "Woo", "Orthopedic Surgery", "Pacific Orthopedic & Spine Center"),
        "prior_providers": [
            _make_physician("Ryan", "Mitchell", "Physical Therapy", "Golden Gate Rehabilitation Center", "Sacramento", "95814"),
        ],
        "venue": "Sacramento",
        "judge": "Hon. Linda S. Washington",
        "extra_context": {
            "pro_per": True,
            "fired_attorney": True,
            "former_attorney": "Law Offices of Martin & Associates",
            "attorney_fee_lien": True,
            "substitution_of_attorney_filed": True,
            "discovery_deadline_issues": True,
        },
        "second_insurance": None,
    })

    # --- B2-013: Pro Per CT with Complications ---
    scenarios.append({
        "internal_id": "B2-013",
        "case_params": CaseParameters(
            target_stage="active_treatment",
            injury_type="cumulative_trauma",
            body_part_category="upper_extremity",
            has_attorney=False,
            has_surgery=False,
            has_psych_component=False,
            has_ur_dispute=True,
            ur_decision="denied",
            imr_filed=False,
            eval_type="none",
            resolution_type="pending",
            has_liens=False,
            num_body_parts=3,
            complexity="standard",
            claim_response="delayed",
        ),
        "applicant": _make_applicant("Jose", "Mendoza", date(1971, 12, 8), "Fresno", "93721"),
        "employer": _make_employer(
            "Fresno Unified School District", "Janitor",
            "Fresno", "93721", hire_date=_date_ago(365 * 20), hourly_rate=18.00,
            department="Custodial Services",
        ),
        "insurance": _make_insurance("Gallagher Bassett Services", "Adelson, Testan, Brundo, Novell & Jimenez"),
        "injuries": [
            _make_injury(
                doi=_date_ago(365),
                injury_type=InjuryType.CUMULATIVE_TRAUMA,
                body_parts=["right shoulder", "left shoulder", "lumbar spine"],
                icd10_codes=["M75.111", "M75.112", "M51.16"],
                description=(
                    "CT: bilateral shoulders (rotator cuff impingement from years of mopping, "
                    "buffing, lifting trash bins overhead) plus lumbar spine (DDD from years of "
                    "bending, lifting, and physical labor). Never hired attorney — limited English "
                    "(Spanish primary), does not understand the WC system. UR denied shoulder MRI "
                    "and applicant missed IMR deadline because notice was sent in English only. "
                    "DWC I&A officer assisted with filing Application for Adjudication. Case is "
                    "stalled — treatment access is primary barrier."
                ),
                mechanism="20 years of custodial work — repetitive overhead cleaning, mopping, heavy lifting",
            ),
        ],
        "treating": _make_physician("Carlos", "Gutierrez", "Physical Medicine & Rehabilitation (PM&R)", "Central Valley Medical Group", "Fresno", "93721"),
        "qme": None,
        "prior_providers": [],
        "venue": "Fresno",
        "judge": "Hon. Michael A. Rodriguez",
        "extra_context": {
            "pro_per": True,
            "language_barrier": "Spanish primary, limited English",
            "missed_imr_deadline": True,
            "english_only_notices": True,
            "dwc_ia_involved": True,
            "case_stalled": True,
        },
        "second_insurance": None,
    })

    # =========================================================================
    # Category 7: CT with Split Carriers
    # =========================================================================

    # --- B2-014: Split Carrier — Government Employee ---
    scenarios.append({
        "internal_id": "B2-014",
        "case_params": CaseParameters(
            target_stage="settlement",
            injury_type="cumulative_trauma",
            body_part_category="upper_extremity",
            has_attorney=True,
            has_surgery=True,
            has_psych_component=True,
            has_ur_dispute=False,
            eval_type="qme",
            resolution_type="stipulations",
            has_liens=False,
            num_body_parts=3,
            complexity="standard",
            claim_response="accepted",
        ),
        "applicant": _make_applicant("Patricia", "Coleman", date(1976, 7, 30), "Sacramento", "95814"),
        "employer": _make_employer(
            "County of Sacramento", "Administrative Assistant",
            "Sacramento", "95814", hire_date=_date_ago(365 * 16), hourly_rate=28.00,
            department="Health and Human Services",
        ),
        "insurance": _make_insurance("Sedgwick Claims Management", "Shaw, Jacobsmeyer, Crain & Claffey"),
        "injuries": [
            _make_injury(
                doi=_date_ago(730),
                injury_type=InjuryType.CUMULATIVE_TRAUMA,
                body_parts=["cervical spine", "right wrist", "left wrist", "psyche (anxiety)"],
                icd10_codes=["M54.2", "G56.01", "G56.02", "F41.1"],
                description=(
                    "CT through and including 12/31/2025: cervical spine (DDD C5-6 from prolonged "
                    "computer use and poor ergonomics), bilateral wrists (bilateral carpal tunnel "
                    "from keyboard/mouse use — bilateral CTS release performed), and psyche "
                    "(generalized anxiety from workload and difficult supervisor). County of "
                    "Sacramento is self-insured and changed TPAs during the CT period: "
                    "Sedgwick (1/1/2024 - 6/30/2024) and Gallagher Bassett (7/1/2024 - 12/31/2025). "
                    "Both TPAs named as defendants. Separate defense counsel for each carrier. "
                    "Separate adjusters and claim numbers. LC 5500.5 joint and several liability applies."
                ),
                mechanism="16 years of keyboard-intensive administrative work with poor ergonomics and chronic workplace stress",
            ),
        ],
        "treating": _make_physician("Margaret", "Lin", "Orthopedic Surgery", "Capitol Physical Therapy Associates", "Sacramento", "95814"),
        "qme": _make_physician("Robert", "Chang", "Physical Medicine & Rehabilitation (PM&R)", "Golden Gate Rehabilitation Center"),
        "prior_providers": [
            _make_physician("Amy", "Walsh", "Physical Therapy", "Central Valley Medical Group", "Sacramento", "95814"),
            _make_physician("Thomas", "Reyes", "Psychiatry", "Glendale Psychiatric Associates", "Sacramento", "95814"),
        ],
        "venue": "Sacramento",
        "judge": "Hon. Patricia M. Torres",
        "extra_context": {
            "split_carrier": True,
            "carrier_1": "Sedgwick (1/1/2024 - 6/30/2024)",
            "carrier_2": "Gallagher Bassett (7/1/2024 - 12/31/2025)",
            "self_insured_employer": "County of Sacramento",
            "lc_5500_5": "Joint and several liability",
            "separate_defense_counsel": True,
        },
        "second_insurance": _make_insurance("Gallagher Bassett Services", "Hanna, Brophy, MacLean, McAleer & Jensen LLP"),
    })

    # --- B2-015: Split Carrier — Private Employer ---
    scenarios.append({
        "internal_id": "B2-015",
        "case_params": CaseParameters(
            target_stage="discovery",
            injury_type="cumulative_trauma",
            body_part_category="spine",
            has_attorney=True,
            has_surgery=False,
            has_psych_component=False,
            has_ur_dispute=False,
            eval_type="qme",
            resolution_type="pending",
            has_liens=False,
            num_body_parts=3,
            complexity="standard",
            claim_response="accepted",
        ),
        "applicant": _make_applicant("Raymond", "Burke", date(1981, 4, 12), "Fontana", "92335"),
        "employer": _make_employer(
            "Golden State Packaging Co.", "Machine Operator",
            "Fontana", "92335", hire_date=_date_ago(365 * 10), hourly_rate=23.50,
            department="Manufacturing — Packaging Line",
        ),
        "insurance": _make_insurance("State Compensation Insurance Fund (SCIF)", "Mitchell & Associates"),
        "injuries": [
            _make_injury(
                doi=_date_ago(600),
                injury_type=InjuryType.CUMULATIVE_TRAUMA,
                body_parts=["lumbar spine", "right knee", "left knee", "hearing (bilateral)"],
                icd10_codes=["M54.5", "M23.211", "M23.212", "H91.90"],
                description=(
                    "CT period 1/1/2024 through 12/31/2025: lumbar spine (mechanical low back pain "
                    "from standing/bending at machine), bilateral knees (degenerative meniscal tears "
                    "from prolonged standing on concrete), and bilateral hearing loss (noise-induced "
                    "from packaging machinery — audiogram shows 40 dB bilateral high-frequency loss). "
                    "Employer changed carriers during CT period: SCIF (through 6/30/2024) and "
                    "Zenith Insurance Company (7/1/2024 through 12/31/2025). Both carriers named. "
                    "Applicant elected to proceed against Zenith only per LC 5500.5 election. "
                    "Zenith seeking contribution from SCIF."
                ),
                mechanism="10 years of machine operation — prolonged standing on concrete, noise exposure, repetitive bending/lifting",
            ),
        ],
        "treating": _make_physician("Mark", "Fitzgerald", "Orthopedic Surgery", "Inland Empire Orthopedic Specialists", "Fontana", "92335"),
        "qme": _make_physician("Deborah", "Stone", "Physical Medicine & Rehabilitation (PM&R)", "Pacific Orthopedic & Spine Center"),
        "prior_providers": [
            _make_physician("Timothy", "Owens", "Internal Medicine", "Central Valley Medical Group", "Fontana", "92335"),
        ],
        "venue": "San Bernardino",
        "judge": "Hon. David W. Park",
        "extra_context": {
            "split_carrier": True,
            "carrier_1": "SCIF (through 6/30/2024)",
            "carrier_2": "Zenith Insurance Company (7/1/2024 through 12/31/2025)",
            "lc_5500_5_election": "Applicant elected to proceed against Zenith only",
            "zenith_seeking_contribution": True,
        },
        "second_insurance": _make_insurance("Zenith Insurance Company", "Bradford & Barthel LLP"),
    })

    # =========================================================================
    # Category 8: Additional Edge Cases from Research
    # =========================================================================

    # --- B2-016: Serious & Willful Misconduct (LC 4553) ---
    scenarios.append({
        "internal_id": "B2-016",
        "case_params": CaseParameters(
            target_stage="settlement",
            injury_type="specific",
            body_part_category="spine",
            has_attorney=True,
            has_surgery=True,
            has_psych_component=False,
            has_ur_dispute=False,
            eval_type="qme",
            resolution_type="c_and_r",
            has_liens=True,
            num_body_parts=2,
            complexity="standard",
            claim_response="accepted",
        ),
        "applicant": _make_applicant("Carlos", "Reyes", date(1993, 8, 20), "Moreno Valley", "92553"),
        "employer": _make_employer(
            "DPR Construction", "Construction Worker — Roofing",
            "Riverside", "92501", hire_date=_date_ago(365 * 4), hourly_rate=26.00,
            department="Construction — Roofing Division",
        ),
        "insurance": _make_insurance("Zenith Insurance Company", "Manning & Kass, Ellrod, Ramirez, Trester LLP"),
        "injuries": [
            _make_injury(
                doi=_date_ago(800),
                injury_type=InjuryType.SPECIFIC,
                body_parts=["lumbar spine", "right hip", "left hip"],
                icd10_codes=["S32.10XA", "S32.009A", "M16.11"],
                description=(
                    "Specific injury — fell from roof (approximately 18 feet) while installing "
                    "roofing materials. Employer had been cited by Cal/OSHA for fall protection "
                    "violations 6 months prior to this incident (Citation #1234-AB). Worker was "
                    "not provided required fall protection harness or tie-off points. Sustained "
                    "sacral fracture with lumbar compression fracture at L1, plus bilateral pelvic "
                    "fracture. Required ORIF surgery for pelvic fracture. "
                    "LC 4553 petition filed for 50% penalty increase on PD due to employer's "
                    "Serious & Willful safety misconduct. Also filed LC 132a discrimination claim — "
                    "applicant was terminated while on temporary disability."
                ),
                mechanism="Fall from roof (18 feet) — no fall protection equipment provided despite prior Cal/OSHA citation",
            ),
        ],
        "treating": _make_physician("Eduardo", "Vargas", "Orthopedic Surgery", "Inland Empire Orthopedic Specialists", "Riverside", "92501"),
        "qme": _make_physician("Martin", "Schwartz", "Orthopedic Surgery", "Southern California QME Medical Group"),
        "prior_providers": [
            _make_physician("Rachel", "Kim", "Physical Therapy", "Capitol Physical Therapy Associates", "Riverside", "92501"),
        ],
        "venue": "Inland Empire (Riverside)",
        "judge": "Hon. Michael A. Rodriguez",
        "extra_context": {
            "lc_4553": True,
            "penalty_increase": "50% on PD for S&W misconduct",
            "lc_132a": True,
            "cal_osha_citation": "Citation #1234-AB — fall protection violations, 6 months prior",
            "terminated_on_disability": True,
        },
        "second_insurance": None,
    })

    # --- B2-017: LC 5814 Penalties + Unreasonable Delay ---
    scenarios.append({
        "internal_id": "B2-017",
        "case_params": CaseParameters(
            target_stage="discovery",
            injury_type="specific",
            body_part_category="upper_extremity",
            has_attorney=True,
            has_surgery=True,
            has_psych_component=False,
            has_ur_dispute=True,
            ur_decision="denied",
            imr_filed=True,
            imr_outcome="overturned",
            eval_type="qme",
            resolution_type="pending",
            has_liens=False,
            num_body_parts=1,
            complexity="standard",
            claim_response="delayed",
        ),
        "applicant": _make_applicant("Laura", "Washington", date(1987, 1, 15), "Bakersfield", "93301"),
        "employer": _make_employer(
            "Dignity Health", "Certified Nursing Assistant",
            "Bakersfield", "93301", hire_date=_date_ago(365 * 8), hourly_rate=19.50,
            department="Medical-Surgical Unit",
        ),
        "insurance": _make_insurance("Broadspire Services", "Adelson, Testan, Brundo, Novell & Jimenez"),
        "injuries": [
            _make_injury(
                doi=_date_ago(540),
                injury_type=InjuryType.SPECIFIC,
                body_parts=["right shoulder"],
                icd10_codes=["M75.111"],
                description=(
                    "Specific injury — right shoulder rotator cuff tear from lifting patient. "
                    "Carrier unreasonably delayed TD payments for 4 months (beyond 14-day statutory "
                    "requirement under LC 4650). Carrier then denied authorized rotator cuff repair "
                    "surgery — denial eventually overturned on IMR. LC 5814 petition filed: 25% "
                    "penalty on delayed TD benefits + 25% penalty on delayed surgery authorization. "
                    "Also SJDB voucher dispute — carrier failed to issue voucher within 20 days of "
                    "P&S report as required. Had rotator cuff repair after IMR overturned denial. "
                    "Good surgical outcome."
                ),
                mechanism="Patient lift — right arm caught under patient during repositioning, acute rotator cuff tear",
            ),
        ],
        "treating": _make_physician("Stephanie", "Moore", "Orthopedic Surgery", "SoCal Sports Medicine & Orthopedics", "Bakersfield", "93301"),
        "qme": _make_physician("Jeffrey", "Brandt", "Orthopedic Surgery", "Pacific Orthopedic & Spine Center"),
        "prior_providers": [
            _make_physician("Daniel", "Gibson", "Physical Therapy", "Central Valley Medical Group", "Bakersfield", "93301"),
        ],
        "venue": "Bakersfield",
        "judge": "Hon. Linda S. Washington",
        "extra_context": {
            "lc_5814_petition": True,
            "td_delay_months": 4,
            "penalty_on_td": "25% penalty for unreasonable delay",
            "penalty_on_treatment": "25% penalty for unreasonable delay in authorizing surgery",
            "sjdb_voucher_dispute": True,
            "sjdb_late_issuance": "Failed to issue within 20 days of P&S report",
        },
        "second_insurance": None,
    })

    # --- B2-018: Complex Lien Case ---
    scenarios.append({
        "internal_id": "B2-018",
        "case_params": CaseParameters(
            target_stage="settlement",
            injury_type="cumulative_trauma",
            body_part_category="spine",
            has_attorney=True,
            has_surgery=True,
            has_psych_component=False,
            has_ur_dispute=False,
            eval_type="qme",
            resolution_type="c_and_r",
            has_liens=True,
            num_body_parts=3,
            complexity="complex",
            claim_response="accepted",
        ),
        "applicant": _make_applicant("Frank", "Dominguez", date(1975, 3, 18), "Bakersfield", "93301"),
        "employer": _make_employer(
            "Pacific Freight Lines", "Truck Driver (CDL-A)",
            "Bakersfield", "93301", hire_date=_date_ago(365 * 15), hourly_rate=30.00,
            department="Long-Haul Freight",
        ),
        "insurance": _make_insurance("Liberty Mutual", "Pollak, Vida & Barer LLP"),
        "injuries": [
            _make_injury(
                doi=_date_ago(900),
                injury_type=InjuryType.CUMULATIVE_TRAUMA,
                body_parts=["lumbar spine", "cervical spine", "right hip"],
                icd10_codes=["M51.16", "M50.12", "M16.11"],
                description=(
                    "CT: lumbar spine (multilevel DDD L3-S1, had L4-5 posterior fusion), cervical "
                    "spine (C5-6 disc protrusion with radiculopathy), and right hip (OA from "
                    "chronic sitting/vibration). Treatment from 6 different providers. "
                    "Total liens: ~$282,700. Hospital lien: $185,000 (spinal fusion surgery at "
                    "Cedar Medical Center). Pain management lien: $45,000 (12 months of injection "
                    "therapy). Compounding pharmacy lien: $28,000. PT lien: $12,000. EDD "
                    "overpayment lien: $8,500. Ambulance lien: $4,200. "
                    "Lien conference held — several liens disputed on reasonable value. IBR pending "
                    "on hospital lien. Settlement complicated by total lien exposure."
                ),
                mechanism="15 years of long-haul truck driving — whole-body vibration, prolonged sitting, loading/unloading",
            ),
        ],
        "treating": _make_physician("Victor", "Soto", "Orthopedic Surgery", "Inland Empire Orthopedic Specialists", "Bakersfield", "93301"),
        "qme": _make_physician("Diane", "Ashton", "Orthopedic Surgery", "Pacific Orthopedic & Spine Center"),
        "prior_providers": [
            _make_physician("Philip", "Tran", "Pain Management", "Southern California Pain Institute"),
            _make_physician("Carol", "Espinoza", "Neurosurgery", "Sierra Neurosurgical Institute"),
            _make_physician("Gregory", "Hall", "Physical Therapy", "Golden Gate Rehabilitation Center"),
            _make_physician("Maria", "Dominguez", "Chiropractic", "Coast Chiropractic & Wellness"),
        ],
        "venue": "Bakersfield",
        "judge": "Hon. Thomas E. Murphy",
        "extra_context": {
            "complex_lien_case": True,
            "total_liens": 282700,
            "hospital_lien": 185000,
            "pain_mgmt_lien": 45000,
            "compounding_pharmacy_lien": 28000,
            "pt_lien": 12000,
            "edd_overpayment_lien": 8500,
            "ambulance_lien": 4200,
            "ibr_pending": "Hospital lien — reasonable value disputed",
            "lien_conference_held": True,
        },
        "second_insurance": None,
    })

    # --- B2-019: UR/IMR Dispute Chain ---
    scenarios.append({
        "internal_id": "B2-019",
        "case_params": CaseParameters(
            target_stage="active_treatment",
            injury_type="cumulative_trauma",
            body_part_category="upper_extremity",
            has_attorney=True,
            has_surgery=True,
            has_psych_component=False,
            has_ur_dispute=True,
            ur_decision="denied",
            imr_filed=True,
            imr_outcome="upheld",
            eval_type="none",
            resolution_type="pending",
            has_liens=False,
            num_body_parts=2,
            complexity="standard",
            claim_response="accepted",
        ),
        "applicant": _make_applicant("Kimberly", "Ngo", date(1990, 6, 22), "Irvine", "92614"),
        "employer": _make_employer(
            "Bright Smiles Dental Group", "Dental Hygienist",
            "Irvine", "92614", hire_date=_date_ago(365 * 9), hourly_rate=45.00,
            department="Clinical — Hygiene",
        ),
        "insurance": _make_insurance("ICW Group", "LaFollette, Johnson, DeHaas, Fesler & Ames"),
        "injuries": [
            _make_injury(
                doi=_date_ago(450),
                injury_type=InjuryType.CUMULATIVE_TRAUMA,
                body_parts=["right wrist", "left wrist", "cervical spine"],
                icd10_codes=["G56.01", "G56.02", "M54.2"],
                description=(
                    "CT: bilateral wrists (carpal tunnel from 9 years of dental scaling instruments) "
                    "plus cervical spine (chronic cervical strain from sustained neck flexion during "
                    "dental procedures). Treating physician requested bilateral carpal tunnel release. "
                    "UR approved right wrist surgery but denied left wrist surgery (citing insufficient "
                    "conservative treatment). IMR upheld denial on left wrist. Applicant's attorney "
                    "filed petition to reopen IMR alleging new EMG evidence shows worsening of left "
                    "CTS. Meanwhile, right wrist CTS release was performed but developed CRPS "
                    "(Complex Regional Pain Syndrome) complication — revision surgery needed. UR "
                    "denied revision surgery. Second IMR pending. Treatment access is central dispute."
                ),
                mechanism="9 years of dental hygiene — repetitive gripping of scaling instruments and sustained neck flexion",
            ),
        ],
        "treating": _make_physician("Jennifer", "Park", "Hand Surgery", "SoCal Sports Medicine & Orthopedics", "Irvine", "92614"),
        "qme": None,
        "prior_providers": [
            _make_physician("Andrew", "Choi", "Pain Management", "Harbor Pain Management Clinic", "Irvine", "92614"),
        ],
        "venue": "Santa Ana",
        "judge": "Hon. Sarah J. Chen",
        "extra_context": {
            "ur_imr_chain": True,
            "right_wrist_ur": "Approved — surgery performed, CRPS complication",
            "left_wrist_ur": "Denied — IMR upheld denial",
            "petition_to_reopen_imr": "New EMG evidence — worsening left CTS",
            "revision_surgery_ur": "Denied — second IMR pending",
            "crps_complication": True,
        },
        "second_insurance": None,
    })

    # --- B2-020: Almaraz/Guzman Rating Rebuttal ---
    scenarios.append({
        "internal_id": "B2-020",
        "case_params": CaseParameters(
            target_stage="medical_legal",
            injury_type="cumulative_trauma",
            body_part_category="spine",
            has_attorney=True,
            has_surgery=False,
            has_psych_component=True,
            has_ur_dispute=False,
            eval_type="qme",
            resolution_type="pending",
            has_liens=False,
            num_body_parts=3,
            complexity="standard",
            claim_response="accepted",
        ),
        "applicant": _make_applicant("Kenneth", "Murphy", date(1966, 2, 5), "Pasadena", "91101"),
        "employer": _make_employer(
            "City of Pasadena Police Department", "Police Officer (Retired)",
            "Pasadena", "91101", hire_date=_date_ago(365 * 30), hourly_rate=55.00,
            department="Patrol Division",
        ),
        "insurance": _make_insurance("Sedgwick Claims Management", "Adelson, Testan, Brundo, Novell & Jimenez"),
        "injuries": [
            _make_injury(
                doi=_date_ago(700),
                injury_type=InjuryType.CUMULATIVE_TRAUMA,
                body_parts=["lumbar spine", "right knee", "left knee", "psyche (PTSD)"],
                icd10_codes=["M51.16", "M17.11", "M17.12", "F43.12"],
                description=(
                    "CT: lumbar spine (multilevel DDD L3-L5 with chronic radiculopathy — QME used "
                    "DRE method, rated DRE II at 5% WPI), bilateral knees (bilateral OA from years "
                    "of patrol duties — running, climbing, kneeling), and psyche (chronic PTSD from "
                    "30 years of law enforcement including multiple officer-involved shootings). "
                    "Applicant took industrial disability retirement. "
                    "Central dispute: rating methodology. Applicant's attorney argues Almaraz/Guzman "
                    "allows Range of Motion (ROM) method for multilevel disc disease per AMA Guides "
                    "5th Ed. Table 15-7 instead of DRE Table 15-3. ROM method yields 12% WPI for "
                    "lumbar spine vs. 5% under DRE. Attorney argues multilevel involvement and "
                    "documented radiculopathy make ROM more appropriate per Almaraz/Guzman holding. "
                    "QME deposition focused on rating methodology."
                ),
                mechanism="30 years of law enforcement — physical patrol duties, foot pursuits, suspect takedowns, and chronic psychological trauma",
            ),
        ],
        "treating": _make_physician("Steven", "Grant", "Pain Management", "Southern California Pain Institute"),
        "qme": _make_physician("Harold", "Weinstein", "Orthopedic Surgery", "Southern California QME Medical Group"),
        "prior_providers": [
            _make_physician("Barbara", "Fischer", "Psychiatry", "Glendale Psychiatric Associates", "Pasadena", "91101"),
            _make_physician("Donald", "Kim", "Physical Therapy", "Capitol Physical Therapy Associates"),
        ],
        "venue": "Los Angeles",
        "judge": "Hon. Robert K. Nakamura",
        "extra_context": {
            "almaraz_guzman": True,
            "dre_rating": "DRE II — 5% WPI (QME's original rating)",
            "rom_rating": "12% WPI (applicant argues ROM method per Table 15-7)",
            "rating_dispute": "DRE Table 15-3 vs. ROM Table 15-7 for multilevel disc disease",
            "industrial_disability_retirement": True,
        },
        "second_insurance": None,
    })

    # =========================================================================
    # Category 9: Simple to Medium Complexity Cases (B2-021 through B2-030)
    # =========================================================================

    # --- B2-021: Simple Ankle Sprain ---
    scenarios.append({
        "internal_id": "B2-021",
        "case_params": CaseParameters(
            target_stage="resolved",
            injury_type="specific",
            body_part_category="lower_extremity",
            has_attorney=True,
            has_surgery=False,
            has_psych_component=False,
            has_ur_dispute=False,
            eval_type="none",
            resolution_type="stipulations",
            has_liens=False,
            num_body_parts=1,
            complexity="standard",
            claim_response="accepted",
        ),
        "applicant": _make_applicant("Jason", "Taylor", date(2001, 5, 3), "Fresno", "93721"),
        "employer": _make_employer(
            "Olive Garden — Fresno", "Server",
            "Fresno", "93721", hire_date=_date_ago(365 * 2), hourly_rate=16.50,
            department="Restaurant — Front of House",
        ),
        "insurance": _make_insurance("Employers Holdings", "Mitchell & Associates"),
        "injuries": [
            _make_injury(
                doi=_date_ago(900),
                injury_type=InjuryType.SPECIFIC,
                body_parts=["right ankle"],
                icd10_codes=["S93.401A"],
                description=(
                    "Simple specific injury — right ankle sprain from slipping on wet kitchen floor. "
                    "Conservative treatment only: ankle brace, PT, NSAIDs. No surgery needed. Quick "
                    "recovery. Initially pro per, obtained attorney for PD settlement negotiation. "
                    "Stipulations at 5% PD. Minimal documents. Resolved."
                ),
                mechanism="Slip and fall on wet kitchen floor — right ankle inversion sprain",
            ),
        ],
        "treating": _make_physician("Eric", "Wallace", "Physical Medicine & Rehabilitation (PM&R)", "Central Valley Medical Group", "Fresno", "93721"),
        "qme": None,
        "prior_providers": [],
        "venue": "Fresno",
        "judge": "Hon. Michael A. Rodriguez",
        "extra_context": {"simple_case": True, "pd_rating": "5%", "resolution": "Stipulations"},
        "second_insurance": None,
    })

    # --- B2-022: Simple Back Strain ---
    scenarios.append({
        "internal_id": "B2-022",
        "case_params": CaseParameters(
            target_stage="resolved",
            injury_type="specific",
            body_part_category="spine",
            has_attorney=True,
            has_surgery=False,
            has_psych_component=False,
            has_ur_dispute=False,
            eval_type="none",
            resolution_type="c_and_r",
            has_liens=False,
            num_body_parts=1,
            complexity="standard",
            claim_response="accepted",
        ),
        "applicant": _make_applicant("Megan", "Foster", date(1995, 9, 17), "San Jose", "95112"),
        "employer": _make_employer(
            "TechFlow Solutions Inc.", "Office Administrator",
            "San Jose", "95112", hire_date=_date_ago(365 * 4), hourly_rate=26.00,
            department="Office Administration",
        ),
        "insurance": _make_insurance("Hartford Financial Services", "Bradford & Barthel LLP"),
        "injuries": [
            _make_injury(
                doi=_date_ago(1000),
                injury_type=InjuryType.SPECIFIC,
                body_parts=["lumbar spine"],
                icd10_codes=["M54.5"],
                description=(
                    "Specific injury — lumbar strain from lifting heavy boxes of supplies in supply "
                    "room. Conservative treatment: PT (12 sessions) + NSAIDs. 3 months temporary "
                    "disability, returned to modified duty, then full duty at month 4. "
                    "Settled via C&R at 8% PD. Resolved, minimal documents."
                ),
                mechanism="Lifting boxes — acute lumbar strain from lifting 40 lb supply box",
            ),
        ],
        "treating": _make_physician("Scott", "Peterson", "Physical Medicine & Rehabilitation (PM&R)", "Bay Area Neurology Associates", "San Jose", "95112"),
        "qme": None,
        "prior_providers": [],
        "venue": "San Jose",
        "judge": "Hon. Christine R. Patel",
        "extra_context": {"simple_case": True, "pd_rating": "8%", "resolution": "C&R"},
        "second_insurance": None,
    })

    # --- B2-023: Knee Meniscus Tear ---
    scenarios.append({
        "internal_id": "B2-023",
        "case_params": CaseParameters(
            target_stage="settlement",
            injury_type="specific",
            body_part_category="lower_extremity",
            has_attorney=True,
            has_surgery=True,
            has_psych_component=False,
            has_ur_dispute=False,
            eval_type="qme",
            resolution_type="stipulations",
            has_liens=False,
            num_body_parts=1,
            complexity="standard",
            claim_response="accepted",
        ),
        "applicant": _make_applicant("Marcus", "Davis", date(1986, 3, 28), "Oakland", "94607"),
        "employer": _make_employer(
            "City of Oakland Police Department", "Police Officer",
            "Oakland", "94607", hire_date=_date_ago(365 * 10), hourly_rate=50.00,
            department="Patrol Division",
        ),
        "insurance": _make_insurance("Sedgwick Claims Management", "Hanna, Brophy, MacLean, McAleer & Jensen LLP"),
        "injuries": [
            _make_injury(
                doi=_date_ago(800),
                injury_type=InjuryType.SPECIFIC,
                body_parts=["right knee"],
                icd10_codes=["M23.211", "S83.511A"],
                description=(
                    "Specific injury — right knee meniscus tear during foot pursuit of suspect. "
                    "Planted right foot and twisted while changing direction. Had arthroscopic "
                    "meniscectomy with good outcome. Returned to full duty after 4 months. "
                    "QME rated at 7% WPI. Settlement stage — stipulations pending."
                ),
                mechanism="Foot pursuit — planted right foot and twisted, acute meniscal tear",
            ),
        ],
        "treating": _make_physician("Allen", "Howard", "Orthopedic Surgery", "SoCal Sports Medicine & Orthopedics", "Oakland", "94607"),
        "qme": _make_physician("Russell", "Grant", "Orthopedic Surgery", "Pacific Orthopedic & Spine Center"),
        "prior_providers": [],
        "venue": "Oakland",
        "judge": "Hon. Karen M. Yamamoto",
        "extra_context": {"pd_rating": "7% WPI", "resolution": "Stipulations pending"},
        "second_insurance": None,
    })

    # --- B2-024: Carpal Tunnel — Single Wrist ---
    scenarios.append({
        "internal_id": "B2-024",
        "case_params": CaseParameters(
            target_stage="resolved",
            injury_type="cumulative_trauma",
            body_part_category="upper_extremity",
            has_attorney=True,
            has_surgery=True,
            has_psych_component=False,
            has_ur_dispute=False,
            eval_type="none",
            resolution_type="stipulations",
            has_liens=False,
            num_body_parts=1,
            complexity="standard",
            claim_response="accepted",
        ),
        "applicant": _make_applicant("Susan", "Clark", date(1978, 11, 1), "Chula Vista", "91910"),
        "employer": _make_employer(
            "DataCore Processing Inc.", "Data Entry Clerk",
            "Chula Vista", "91910", hire_date=_date_ago(365 * 12), hourly_rate=20.00,
            department="Data Processing",
        ),
        "insurance": _make_insurance("Republic Indemnity", "Shaw, Jacobsmeyer, Crain & Claffey"),
        "injuries": [
            _make_injury(
                doi=_date_ago(1000),
                injury_type=InjuryType.CUMULATIVE_TRAUMA,
                body_parts=["right wrist"],
                icd10_codes=["G56.01"],
                description=(
                    "CT — right wrist carpal tunnel syndrome from 12 years of data entry (8+ hours "
                    "daily keyboard/mouse use). EMG confirmed moderate right CTS. Had carpal tunnel "
                    "release surgery with good outcome. Returned to modified duty with ergonomic "
                    "keyboard and mouse, adjustable desk. Stipulations at 6% PD. Resolved."
                ),
                mechanism="12 years of data entry — repetitive keyboard and mouse use",
            ),
        ],
        "treating": _make_physician("Nina", "Patel", "Hand Surgery", "SoCal Sports Medicine & Orthopedics", "Chula Vista", "91910"),
        "qme": None,
        "prior_providers": [],
        "venue": "San Diego",
        "judge": "Hon. Diane F. Johnson",
        "extra_context": {"simple_case": True, "pd_rating": "6%", "resolution": "Stipulations"},
        "second_insurance": None,
    })

    # --- B2-025: Shoulder Strain — No Surgery ---
    scenarios.append({
        "internal_id": "B2-025",
        "case_params": CaseParameters(
            target_stage="resolved",
            injury_type="specific",
            body_part_category="upper_extremity",
            has_attorney=True,
            has_surgery=False,
            has_psych_component=False,
            has_ur_dispute=False,
            eval_type="none",
            resolution_type="c_and_r",
            has_liens=False,
            num_body_parts=1,
            complexity="standard",
            claim_response="accepted",
        ),
        "applicant": _make_applicant("Brian", "Henderson", date(1991, 7, 14), "Torrance", "90501"),
        "employer": _make_employer(
            "SoCal Plumbing Services", "Plumber — Journeyman",
            "Torrance", "90501", hire_date=_date_ago(365 * 6), hourly_rate=38.00,
            department="Residential Plumbing",
        ),
        "insurance": _make_insurance("Travelers Insurance", "Mitchell & Associates"),
        "injuries": [
            _make_injury(
                doi=_date_ago(950),
                injury_type=InjuryType.SPECIFIC,
                body_parts=["left shoulder"],
                icd10_codes=["M25.512"],
                description=(
                    "Specific injury — left shoulder strain from overhead pipe installation in "
                    "tight crawl space. Conservative treatment: subacromial corticosteroid injection "
                    "(x2) + PT (16 sessions). Returned to full duty with occasional discomfort. "
                    "C&R at 5% PD. Resolved."
                ),
                mechanism="Overhead work — left arm extended overhead while installing pipe in crawl space",
            ),
        ],
        "treating": _make_physician("Roger", "Hayes", "Orthopedic Surgery", "SoCal Sports Medicine & Orthopedics", "Torrance", "90501"),
        "qme": None,
        "prior_providers": [],
        "venue": "Long Beach",
        "judge": "Hon. Thomas E. Murphy",
        "extra_context": {"simple_case": True, "pd_rating": "5%", "resolution": "C&R"},
        "second_insurance": None,
    })

    # --- B2-026: Medium — CT Spine ---
    scenarios.append({
        "internal_id": "B2-026",
        "case_params": CaseParameters(
            target_stage="settlement",
            injury_type="cumulative_trauma",
            body_part_category="spine",
            has_attorney=True,
            has_surgery=False,
            has_psych_component=False,
            has_ur_dispute=True,
            ur_decision="denied",
            imr_filed=False,
            eval_type="qme",
            resolution_type="stipulations",
            has_liens=False,
            num_body_parts=2,
            complexity="standard",
            claim_response="accepted",
        ),
        "applicant": _make_applicant("Gloria", "Mendez", date(1974, 4, 22), "Escondido", "92025"),
        "employer": _make_employer(
            "Safeway Inc.", "Grocery Store Cashier",
            "Escondido", "92025", hire_date=_date_ago(365 * 18), hourly_rate=19.50,
            department="Front End — Checkout",
        ),
        "insurance": _make_insurance("ICW Group", "Downs, Ward, Bender & Dantonio"),
        "injuries": [
            _make_injury(
                doi=_date_ago(800),
                injury_type=InjuryType.CUMULATIVE_TRAUMA,
                body_parts=["cervical spine", "lumbar spine"],
                icd10_codes=["M54.2", "M51.16"],
                description=(
                    "CT: cervical spine (C5-6 DDD from years of repetitive scanning and bagging) "
                    "plus lumbar spine (L4-5, L5-S1 DDD from prolonged standing and lifting). "
                    "Conservative treatment. Some UR disputes on cervical injection frequency — "
                    "UR denied 4th epidural injection. QME rates cervical at 5% WPI + lumbar at "
                    "8% WPI (CVC combined 12.6%). Settlement stage — stipulations pending."
                ),
                mechanism="18 years of cashier work — repetitive scanning/bagging, prolonged standing, and intermittent heavy lifting",
            ),
        ],
        "treating": _make_physician("Maria", "Santos", "Pain Management", "Southern California Pain Institute", "Escondido", "92025"),
        "qme": _make_physician("Lawrence", "Wu", "Physical Medicine & Rehabilitation (PM&R)", "Pacific Orthopedic & Spine Center"),
        "prior_providers": [
            _make_physician("Dennis", "Palmer", "Physical Therapy", "Capitol Physical Therapy Associates", "Escondido", "92025"),
        ],
        "venue": "San Diego",
        "judge": "Hon. Diane F. Johnson",
        "extra_context": {"pd_rating": "CVC combined 12.6%", "cervical_wpi": "5%", "lumbar_wpi": "8%"},
        "second_insurance": None,
    })

    # --- B2-027: Medium — Specific with Surgery ---
    scenarios.append({
        "internal_id": "B2-027",
        "case_params": CaseParameters(
            target_stage="medical_legal",
            injury_type="specific",
            body_part_category="spine",
            has_attorney=True,
            has_surgery=True,
            has_psych_component=False,
            has_ur_dispute=False,
            eval_type="qme",
            resolution_type="pending",
            has_liens=False,
            num_body_parts=1,
            complexity="standard",
            claim_response="accepted",
        ),
        "applicant": _make_applicant("William", "Carter", date(1982, 6, 10), "Modesto", "95354"),
        "employer": _make_employer(
            "Amazon Fulfillment Center ONT8", "Warehouse Associate",
            "Ontario", "91761", hire_date=_date_ago(365 * 5), hourly_rate=21.00,
            department="Fulfillment — Outbound",
        ),
        "insurance": _make_insurance("Zenith Insurance Company", "Pollak, Vida & Barer LLP"),
        "injuries": [
            _make_injury(
                doi=_date_ago(540),
                injury_type=InjuryType.SPECIFIC,
                body_parts=["lumbar spine"],
                icd10_codes=["M51.16", "M54.41"],
                description=(
                    "Specific injury — lumbar disc herniation at L5-S1 from lifting heavy box "
                    "(60 lbs) overhead in fulfillment center. Had L5-S1 microdiscectomy with good "
                    "surgical outcome. 6 months TD. Returned to modified duty (no lifting over 25 lbs). "
                    "QME rates at 12% WPI (DRE III). Medical-legal stage — rating being finalized."
                ),
                mechanism="Heavy lifting — 60 lb box overhead, acute disc herniation with sciatica",
            ),
        ],
        "treating": _make_physician("David", "Sanchez", "Neurosurgery", "Sierra Neurosurgical Institute", "Ontario", "91761"),
        "qme": _make_physician("Catherine", "Brooks", "Orthopedic Surgery", "Pacific Orthopedic & Spine Center"),
        "prior_providers": [
            _make_physician("Lisa", "Turner", "Physical Therapy", "Golden Gate Rehabilitation Center", "Ontario", "91761"),
        ],
        "venue": "Pomona",
        "judge": "Hon. Christine R. Patel",
        "extra_context": {"pd_rating": "DRE III — 12% WPI", "surgery": "L5-S1 microdiscectomy"},
        "second_insurance": None,
    })

    # --- B2-028: Medium — Psych Claim ---
    scenarios.append({
        "internal_id": "B2-028",
        "case_params": CaseParameters(
            target_stage="discovery",
            injury_type="cumulative_trauma",
            body_part_category="psyche",
            has_attorney=True,
            has_surgery=False,
            has_psych_component=True,
            has_ur_dispute=False,
            eval_type="qme",
            resolution_type="pending",
            has_liens=False,
            num_body_parts=1,
            complexity="standard",
            claim_response="accepted",
        ),
        "applicant": _make_applicant("Amanda", "Reyes", date(1988, 12, 3), "Huntington Beach", "92648"),
        "employer": _make_employer(
            "City of Anaheim — 911 Communications", "911 Dispatcher",
            "Anaheim", "92801", hire_date=_date_ago(365 * 7), hourly_rate=35.00,
            department="Emergency Communications Center",
        ),
        "insurance": _make_insurance("Sedgwick Claims Management", "Adelson, Testan, Brundo, Novell & Jimenez"),
        "injuries": [
            _make_injury(
                doi=_date_ago(600),
                injury_type=InjuryType.CUMULATIVE_TRAUMA,
                body_parts=["psyche (PTSD)"],
                icd10_codes=["F43.12", "F32.1"],
                description=(
                    "CT psyche: PTSD from repeated exposure to traumatic 911 calls over 7 years — "
                    "child abuse calls, domestic violence fatalities, officer-involved shootings, "
                    "suicide calls. LC 3208.3 applies — employed over 6 months, greater than 50% "
                    "industrial causation established. Psychiatric treatment with good medication "
                    "response (sertraline + trazodone). QME rates GAF 58 (15% WPI). "
                    "LC 3212.15 PTSD presumption applies (dispatchers included)."
                ),
                mechanism="7 years of repeated exposure to traumatic 911 emergency calls",
            ),
        ],
        "treating": _make_physician("Michelle", "Young", "Psychiatry", "Southern California Behavioral Health Center", "Anaheim", "92801"),
        "qme": _make_physician("Arthur", "Kaplan", "Psychiatry", "Forensic Psychiatric Associates"),
        "prior_providers": [],
        "venue": "Anaheim",
        "judge": "Hon. Angela D. Kim",
        "extra_context": {
            "psych_claim": True,
            "gaf_score": 58,
            "lc_3208_3": "Employed >6 months, >50% industrial causation",
            "lc_3212_15": "PTSD presumption — dispatchers included",
            "pd_rating": "15% WPI",
        },
        "second_insurance": None,
    })

    # --- B2-029: Medium — Bilateral CTS with One Surgery ---
    scenarios.append({
        "internal_id": "B2-029",
        "case_params": CaseParameters(
            target_stage="settlement",
            injury_type="cumulative_trauma",
            body_part_category="upper_extremity",
            has_attorney=True,
            has_surgery=True,
            has_psych_component=False,
            has_ur_dispute=False,
            eval_type="qme",
            resolution_type="stipulations",
            has_liens=False,
            num_body_parts=2,
            complexity="standard",
            claim_response="accepted",
        ),
        "applicant": _make_applicant("Robert", "Castillo", date(1976, 8, 20), "San Bernardino", "92401"),
        "employer": _make_employer(
            "Precision Auto Repair", "Mechanic — ASE Certified",
            "San Bernardino", "92401", hire_date=_date_ago(365 * 20), hourly_rate=32.00,
            department="Automotive Repair",
        ),
        "insurance": _make_insurance("Applied Underwriters", "Mitchell & Associates"),
        "injuries": [
            _make_injury(
                doi=_date_ago(750),
                injury_type=InjuryType.CUMULATIVE_TRAUMA,
                body_parts=["right wrist", "left wrist"],
                icd10_codes=["G56.01", "G56.02"],
                description=(
                    "CT: bilateral carpal tunnel syndrome from 20 years of automotive repair — "
                    "repetitive wrench use, air tool vibration, and forceful gripping. Right wrist: "
                    "had CTS release surgery with good outcome (3% WPI post-surgical). Left wrist: "
                    "managed conservatively with splinting and activity modification (5% WPI, no "
                    "surgery). CVC combined 7.85%. Settlement stage — stipulations pending."
                ),
                mechanism="20 years of automotive repair — repetitive gripping, vibrating tools, and forceful hand/wrist motions",
            ),
        ],
        "treating": _make_physician("Anthony", "Flores", "Hand Surgery", "Inland Empire Orthopedic Specialists", "San Bernardino", "92401"),
        "qme": _make_physician("Edward", "Lam", "Physical Medicine & Rehabilitation (PM&R)", "Pacific Orthopedic & Spine Center"),
        "prior_providers": [],
        "venue": "San Bernardino",
        "judge": "Hon. David W. Park",
        "extra_context": {
            "right_wrist_wpi": "3% WPI (post-surgical)",
            "left_wrist_wpi": "5% WPI (conservative)",
            "cvc_combined": "7.85%",
        },
        "second_insurance": None,
    })

    # --- B2-030: Medium — Slip and Fall, Multiple Body Parts ---
    scenarios.append({
        "internal_id": "B2-030",
        "case_params": CaseParameters(
            target_stage="settlement",
            injury_type="specific",
            body_part_category="lower_extremity",
            has_attorney=True,
            has_surgery=True,
            has_psych_component=False,
            has_ur_dispute=True,
            ur_decision="approved",
            imr_filed=False,
            eval_type="qme",
            resolution_type="stipulations",
            has_liens=False,
            num_body_parts=3,
            complexity="standard",
            claim_response="accepted",
        ),
        "applicant": _make_applicant("Rosa", "Jimenez", date(1980, 10, 15), "Anaheim", "92801"),
        "employer": _make_employer(
            "Marriott Hotel — Anaheim", "Housekeeper",
            "Anaheim", "92801", hire_date=_date_ago(365 * 9), hourly_rate=18.50,
            department="Housekeeping",
        ),
        "insurance": _make_insurance("AmTrust Financial Services", "Downs, Ward, Bender & Dantonio"),
        "injuries": [
            _make_injury(
                doi=_date_ago(780),
                injury_type=InjuryType.SPECIFIC,
                body_parts=["right knee", "lumbar spine", "right wrist"],
                icd10_codes=["M23.211", "M54.5", "S63.501A"],
                description=(
                    "Specific injury — slipped on wet hallway floor while pushing housekeeping cart. "
                    "Fell onto right side, impacting right knee, low back, and bracing fall with "
                    "right hand. Right knee: required arthroscopic meniscectomy (5% WPI). Lumbar "
                    "spine: strain, conservative treatment (5% WPI). Right wrist: sprain, "
                    "conservative treatment (2% WPI). CVC combined ~11.5%. Some UR dispute on PT "
                    "frequency (requested 3x/week, UR approved 2x/week). Settlement stage."
                ),
                mechanism="Slip and fall on wet hallway floor — fell onto right side while pushing housekeeping cart",
            ),
        ],
        "treating": _make_physician("Irene", "Aguilar", "Orthopedic Surgery", "SoCal Sports Medicine & Orthopedics", "Anaheim", "92801"),
        "qme": _make_physician("Philip", "Jordan", "Physical Medicine & Rehabilitation (PM&R)", "Pacific Orthopedic & Spine Center"),
        "prior_providers": [
            _make_physician("Carmen", "Ruiz", "Physical Therapy", "Capitol Physical Therapy Associates", "Anaheim", "92801"),
        ],
        "venue": "Anaheim",
        "judge": "Hon. Angela D. Kim",
        "extra_context": {
            "right_knee_wpi": "5% WPI (arthroscopic meniscectomy)",
            "lumbar_wpi": "5% WPI (conservative)",
            "right_wrist_wpi": "2% WPI (conservative)",
            "cvc_combined": "~11.5%",
        },
        "second_insurance": None,
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

    # Use the scenario's hand-crafted applicant
    applicant: GeneratedApplicant = scenario["applicant"]

    # Employer
    employer: GeneratedEmployer = scenario["employer"]

    # Insurance
    insurance: GeneratedInsurance = scenario["insurance"]

    # Injuries
    injuries: list[GeneratedInjury] = scenario["injuries"]

    # Physicians
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
    print("  BATCH 2: Edge Case Generation — 30 Custom WC Cases")
    print("=" * 70)
    print()

    # Back up existing progress.db
    if DB_PATH.exists():
        backup_path = DB_PATH.with_suffix(".db.bak_pre_batch2")
        shutil.copy2(DB_PATH, backup_path)
        print(f"  Backed up progress.db -> {backup_path.name}")

    # Initialize
    tracker = ProgressTracker(DB_PATH)
    fake_gen = FakeDataGenerator(seed=2002)  # Different seed from batch 1

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
