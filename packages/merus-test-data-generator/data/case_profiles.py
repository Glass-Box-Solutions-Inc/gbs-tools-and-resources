"""
20 case profile definitions — stage distribution, doc count ranges, injury types.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from data.models import InjuryType, LitigationStage


class CaseProfile:
    def __init__(
        self,
        case_number: int,
        stage: LitigationStage,
        min_docs: int,
        max_docs: int,
        injury_type: InjuryType,
        body_part_category: str,
        num_injuries: int = 1,
        has_surgery: bool = False,
        notes: str = "",
    ):
        self.case_number = case_number
        self.stage = stage
        self.min_docs = min_docs
        self.max_docs = max_docs
        self.injury_type = injury_type
        self.body_part_category = body_part_category
        self.num_injuries = num_injuries
        self.has_surgery = has_surgery
        self.notes = notes


# 20 cases: 3 intake, 5 active treatment, 4 discovery, 3 med-legal, 3 settlement, 2 resolved
CASE_PROFILES: list[CaseProfile] = [
    # --- Intake (3 cases, 18-22 docs) ---
    CaseProfile(1, LitigationStage.INTAKE, 18, 22, InjuryType.SPECIFIC, "spine",
                notes="New back injury, warehouse worker"),
    CaseProfile(2, LitigationStage.INTAKE, 18, 22, InjuryType.SPECIFIC, "upper_extremity",
                notes="Shoulder injury, construction"),
    CaseProfile(3, LitigationStage.INTAKE, 18, 22, InjuryType.CUMULATIVE_TRAUMA, "upper_extremity",
                notes="CT wrist/hand, office worker"),

    # --- Active Treatment (5 cases, 25-35 docs) ---
    CaseProfile(4, LitigationStage.ACTIVE_TREATMENT, 25, 35, InjuryType.SPECIFIC, "spine",
                notes="Cervical injury, firefighter"),
    CaseProfile(5, LitigationStage.ACTIVE_TREATMENT, 25, 35, InjuryType.SPECIFIC, "lower_extremity",
                has_surgery=True, notes="Knee surgery, police officer"),
    CaseProfile(6, LitigationStage.ACTIVE_TREATMENT, 25, 35, InjuryType.CUMULATIVE_TRAUMA, "spine",
                notes="CT lumbar, nurse"),
    CaseProfile(7, LitigationStage.ACTIVE_TREATMENT, 25, 35, InjuryType.SPECIFIC, "upper_extremity",
                notes="Shoulder injury, maintenance worker"),
    CaseProfile(8, LitigationStage.ACTIVE_TREATMENT, 25, 35, InjuryType.SPECIFIC, "lower_extremity",
                notes="Ankle injury, retail worker"),

    # --- Discovery (4 cases, 30-40 docs) ---
    CaseProfile(9, LitigationStage.DISCOVERY, 30, 40, InjuryType.SPECIFIC, "spine",
                has_surgery=True, notes="Post-surgery lumbar, laborer"),
    CaseProfile(10, LitigationStage.DISCOVERY, 30, 40, InjuryType.CUMULATIVE_TRAUMA, "upper_extremity",
                num_injuries=2, notes="Bilateral CTS, data entry"),
    CaseProfile(11, LitigationStage.DISCOVERY, 30, 40, InjuryType.SPECIFIC, "lower_extremity",
                notes="Hip injury, warehouse"),
    CaseProfile(12, LitigationStage.DISCOVERY, 30, 40, InjuryType.SPECIFIC, "psyche",
                notes="PTSD, first responder"),

    # --- Medical-Legal (3 cases, 30-40 docs) ---
    CaseProfile(13, LitigationStage.MEDICAL_LEGAL, 30, 40, InjuryType.CUMULATIVE_TRAUMA, "spine",
                num_injuries=2, notes="CT spine + psyche, teacher"),
    CaseProfile(14, LitigationStage.MEDICAL_LEGAL, 30, 40, InjuryType.SPECIFIC, "upper_extremity",
                has_surgery=True, notes="Post-surgery shoulder, ironworker"),
    CaseProfile(15, LitigationStage.MEDICAL_LEGAL, 30, 40, InjuryType.SPECIFIC, "lower_extremity",
                notes="Knee injury, electrician"),

    # --- Settlement (3 cases, 35-45 docs) ---
    CaseProfile(16, LitigationStage.SETTLEMENT, 35, 45, InjuryType.SPECIFIC, "spine",
                has_surgery=True, num_injuries=2, notes="Lumbar fusion + psyche"),
    CaseProfile(17, LitigationStage.SETTLEMENT, 35, 45, InjuryType.CUMULATIVE_TRAUMA, "upper_extremity",
                notes="CT bilateral shoulders, mechanic"),
    CaseProfile(18, LitigationStage.SETTLEMENT, 35, 45, InjuryType.SPECIFIC, "lower_extremity",
                has_surgery=True, notes="TKR, city worker"),

    # --- Resolved (2 cases, 45-50 docs) ---
    CaseProfile(19, LitigationStage.RESOLVED, 45, 50, InjuryType.SPECIFIC, "spine",
                has_surgery=True, num_injuries=2, notes="Multi-level fusion + depression"),
    CaseProfile(20, LitigationStage.RESOLVED, 45, 50, InjuryType.CUMULATIVE_TRAUMA, "lower_extremity",
                num_injuries=2, notes="CT bilateral knees, postal worker"),
]
