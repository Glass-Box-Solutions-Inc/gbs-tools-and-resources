"""
AMA Guides to the Evaluation of Permanent Impairment, 5th Edition — reference data
for generating realistic impairment rating narratives in QME/AME reports.

California uses the 5th Edition exclusively per LC §4660.1.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import random
from typing import Any

# ---------------------------------------------------------------------------
# DRE Categories by Spine Region (AMA Guides 5th Ed, Tables 15-3/4/5)
# ---------------------------------------------------------------------------

DRE_CATEGORIES: dict[str, dict[str, dict[str, Any]]] = {
    "lumbar": {
        # Table 15-3: DRE Lumbosacral Category
        "I": {
            "wpi_range": (0, 0),
            "description": "DRE Lumbosacral Category I — No Significant Clinical Findings",
            "criteria": [
                "No significant clinical findings",
                "No muscle guarding or spasm",
                "No documentable neurological impairment",
                "No loss of structural integrity on imaging",
            ],
        },
        "II": {
            "wpi_range": (5, 8),
            "description": "DRE Lumbosacral Category II — Minor Impairment",
            "criteria": [
                "Muscle guarding or spasm observed by physician",
                "Non-verifiable radicular complaints",
                "Loss of range of motion (flexion/extension) without structural compromise",
                "No objective radiculopathy on EMG or clinical testing",
            ],
        },
        "III": {
            "wpi_range": (10, 13),
            "description": "DRE Lumbosacral Category III — Radiculopathy",
            "criteria": [
                "Significant signs of radiculopathy (positive EMG/NCV)",
                "Loss of relevant reflexes or measurable unilateral atrophy",
                "Documented herniated disc or stenosis on imaging correlating with clinical findings",
                "Radicular symptoms with concordant clinical and electrodiagnostic findings",
            ],
        },
        "IV": {
            "wpi_range": (20, 23),
            "description": "DRE Lumbosacral Category IV — Loss of Motion Segment Integrity or Bilateral Radiculopathy",
            "criteria": [
                "Loss of motion segment integrity (>4.5mm translation or >15° angular motion on flexion-extension)",
                "Bilateral or multilevel radiculopathy",
                "Cauda equina syndrome (without bowel/bladder impairment)",
                "Loss of structural integrity verified on imaging",
            ],
        },
        "V": {
            "wpi_range": (25, 28),
            "description": "DRE Lumbosacral Category V — Severe Radiculopathy with Residual Findings",
            "criteria": [
                "Significant lower extremity impairment (bladder or bowel involvement)",
                "Cauda equina syndrome with residual objective findings",
                "Documented vertebral body compression fracture >50%",
                "Severe loss of structural integrity requiring surgical fusion",
            ],
        },
    },
    "cervical": {
        # Table 15-5: DRE Cervicothoracic Category
        "I": {
            "wpi_range": (0, 0),
            "description": "DRE Cervicothoracic Category I — No Significant Clinical Findings",
            "criteria": [
                "No significant clinical findings on examination",
                "No muscle guarding, spasm, or documentable neurological impairment",
            ],
        },
        "II": {
            "wpi_range": (5, 8),
            "description": "DRE Cervicothoracic Category II — Minor Impairment",
            "criteria": [
                "Muscle guarding or spasm observed by physician",
                "Non-verifiable radicular complaints in the upper extremity",
                "Loss of cervical range of motion without structural compromise",
            ],
        },
        "III": {
            "wpi_range": (15, 18),
            "description": "DRE Cervicothoracic Category III — Radiculopathy",
            "criteria": [
                "Significant signs of cervical radiculopathy (positive EMG/NCV)",
                "Documented disc herniation with concordant clinical findings",
                "Loss of relevant reflexes or measurable unilateral atrophy",
            ],
        },
        "IV": {
            "wpi_range": (25, 28),
            "description": "DRE Cervicothoracic Category IV — Loss of Motion Segment Integrity",
            "criteria": [
                "Loss of motion segment integrity on flexion-extension radiographs",
                "Bilateral or multilevel cervical radiculopathy",
                "Documented cervical fusion with residual impairment",
            ],
        },
        "V": {
            "wpi_range": (30, 35),
            "description": "DRE Cervicothoracic Category V — Severe Impairment",
            "criteria": [
                "Cervical spinal cord involvement with long tract signs",
                "Significant upper extremity impairment from cervical pathology",
                "Documented severe structural compromise",
            ],
        },
    },
    "thoracic": {
        # Table 15-4: DRE Thoracolumbar Category (abbreviated)
        "I": {
            "wpi_range": (0, 0),
            "description": "DRE Thoracolumbar Category I — No Significant Clinical Findings",
            "criteria": ["No significant clinical findings"],
        },
        "II": {
            "wpi_range": (5, 8),
            "description": "DRE Thoracolumbar Category II — Minor Impairment",
            "criteria": ["Muscle guarding or spasm", "Non-verifiable radicular complaints"],
        },
        "III": {
            "wpi_range": (10, 13),
            "description": "DRE Thoracolumbar Category III — Radiculopathy",
            "criteria": ["Documentable radiculopathy", "Imaging-concordant findings"],
        },
    },
}

# ---------------------------------------------------------------------------
# Upper Extremity Impairment (AMA Guides 5th Ed, Chapter 16)
# ---------------------------------------------------------------------------

UPPER_EXTREMITY_IMPAIRMENT: dict[str, dict[str, Any]] = {
    "shoulder": {
        "rom_wpi_ranges": {
            "mild": {"ue": (6, 10), "wpi": (4, 6), "description": "Mild loss of ROM — flexion 140-160°, abduction 140-160°"},
            "moderate": {"ue": (12, 20), "wpi": (7, 12), "description": "Moderate loss of ROM — flexion 100-140°, abduction 100-140°"},
            "severe": {"ue": (22, 30), "wpi": (13, 18), "description": "Severe loss of ROM — flexion <100°, abduction <100°"},
        },
        "diagnosis_based": {
            "rotator_cuff_tear_repaired": {"ue": (10, 14), "wpi": (6, 8)},
            "rotator_cuff_tear_unrepaired": {"ue": (16, 24), "wpi": (10, 14)},
            "labral_tear_repaired": {"ue": (6, 10), "wpi": (4, 6)},
            "acromioclavicular_separation": {"ue": (5, 10), "wpi": (3, 6)},
            "recurrent_dislocation": {"ue": (12, 20), "wpi": (7, 12)},
        },
    },
    "elbow": {
        "rom_wpi_ranges": {
            "mild": {"ue": (4, 8), "wpi": (2, 5), "description": "Mild loss of ROM — flexion 120-130°"},
            "moderate": {"ue": (10, 16), "wpi": (6, 10), "description": "Moderate loss of ROM — flexion 90-120°"},
        },
        "diagnosis_based": {
            "lateral_epicondylitis_chronic": {"ue": (3, 5), "wpi": (2, 3)},
            "ulnar_neuropathy_mild": {"ue": (5, 8), "wpi": (3, 5)},
            "ulnar_neuropathy_moderate": {"ue": (10, 15), "wpi": (6, 9)},
        },
    },
    "wrist": {
        "rom_wpi_ranges": {
            "mild": {"ue": (3, 6), "wpi": (2, 4), "description": "Mild loss of ROM — flexion 50-70°, extension 40-60°"},
            "moderate": {"ue": (8, 14), "wpi": (5, 8), "description": "Moderate loss of ROM — flexion 30-50°, extension 20-40°"},
        },
        "diagnosis_based": {
            "carpal_tunnel_residual_mild": {"ue": (5, 8), "wpi": (3, 5)},
            "carpal_tunnel_residual_moderate": {"ue": (10, 18), "wpi": (6, 11)},
            "scaphoid_fracture_healed": {"ue": (4, 8), "wpi": (2, 5)},
        },
    },
    "hand": {
        "diagnosis_based": {
            "finger_amputation_index_distal": {"ue": (5, 8), "wpi": (3, 5)},
            "grip_strength_deficit_mild": {"ue": (3, 5), "wpi": (2, 3)},
            "grip_strength_deficit_moderate": {"ue": (6, 10), "wpi": (4, 6)},
        },
    },
}

# ---------------------------------------------------------------------------
# Lower Extremity Impairment (AMA Guides 5th Ed, Chapter 17)
# ---------------------------------------------------------------------------

LOWER_EXTREMITY_IMPAIRMENT: dict[str, dict[str, Any]] = {
    "hip": {
        "rom_wpi_ranges": {
            "mild": {"le": (7, 12), "wpi": (3, 5), "description": "Mild loss of ROM — flexion 80-100°"},
            "moderate": {"le": (15, 25), "wpi": (6, 10), "description": "Moderate loss of ROM — flexion 60-80°"},
            "severe": {"le": (30, 40), "wpi": (12, 16), "description": "Severe loss of ROM — flexion <60°"},
        },
        "diagnosis_based": {
            "total_hip_arthroplasty_good": {"le": (25, 30), "wpi": (10, 12)},
            "avascular_necrosis": {"le": (20, 35), "wpi": (8, 14)},
        },
    },
    "knee": {
        "rom_wpi_ranges": {
            "mild": {"le": (5, 10), "wpi": (2, 4), "description": "Mild loss of ROM — flexion 110-125°"},
            "moderate": {"le": (12, 20), "wpi": (5, 8), "description": "Moderate loss of ROM — flexion 80-110°"},
            "severe": {"le": (25, 35), "wpi": (10, 14), "description": "Severe loss of ROM — flexion <80°"},
        },
        "diagnosis_based": {
            "meniscectomy_partial": {"le": (5, 7), "wpi": (2, 3)},
            "acl_reconstruction_good": {"le": (7, 10), "wpi": (3, 4)},
            "acl_reconstruction_residual_laxity": {"le": (10, 15), "wpi": (4, 6)},
            "total_knee_arthroplasty_good": {"le": (20, 25), "wpi": (8, 10)},
        },
    },
    "ankle": {
        "rom_wpi_ranges": {
            "mild": {"le": (5, 8), "wpi": (2, 3), "description": "Mild loss of ROM — dorsiflexion 10-15°"},
            "moderate": {"le": (10, 15), "wpi": (4, 6), "description": "Moderate loss of ROM — dorsiflexion 5-10°"},
        },
        "diagnosis_based": {
            "ankle_fracture_healed": {"le": (5, 10), "wpi": (2, 4)},
            "chronic_ankle_instability": {"le": (7, 12), "wpi": (3, 5)},
        },
    },
    "foot": {
        "diagnosis_based": {
            "plantar_fasciitis_chronic": {"le": (3, 5), "wpi": (1, 2)},
            "metatarsal_fracture_healed": {"le": (3, 7), "wpi": (1, 3)},
        },
    },
}

# ---------------------------------------------------------------------------
# Psychiatric Impairment (AMA Guides 5th Ed, Chapter 14)
# ---------------------------------------------------------------------------

PSYCHIATRIC_IMPAIRMENT: dict[str, Any] = {
    "functional_areas": [
        "Activities of Daily Living (ADL)",
        "Social Functioning",
        "Concentration, Persistence, and Pace",
        "Adaptation to Stressful Circumstances",
    ],
    "gaf_brackets": {
        # GAF range → (WPI range, impairment class, description)
        (61, 70): {
            "wpi_range": (5, 10),
            "class": "Mild",
            "description": "Some mild symptoms (e.g., depressed mood, mild insomnia) OR some difficulty in social, occupational, or school functioning, but generally functioning pretty well.",
        },
        (51, 60): {
            "wpi_range": (10, 20),
            "class": "Moderate",
            "description": "Moderate symptoms (e.g., flat affect, circumstantial speech, occasional panic attacks) OR moderate difficulty in social, occupational, or school functioning.",
        },
        (41, 50): {
            "wpi_range": (20, 30),
            "class": "Moderately Severe",
            "description": "Serious symptoms (e.g., suicidal ideation, severe obsessional rituals) OR any serious impairment in social, occupational, or school functioning.",
        },
        (31, 40): {
            "wpi_range": (30, 40),
            "class": "Severe",
            "description": "Some impairment in reality testing or communication OR major impairment in several areas such as work, family relations, judgment, thinking, or mood.",
        },
    },
}

# ---------------------------------------------------------------------------
# Pain Add-On (LC §4660.1)
# ---------------------------------------------------------------------------

PAIN_ADDON_WPI: dict[int, str] = {
    0: "No ratable pain-related impairment beyond that accounted for in the WPI rating. The patient's pain is proportionate to the documented pathology and has been fully accounted for in the standard impairment rating.",
    1: "1% WPI pain add-on. The patient demonstrates mild pain-related functional limitations not fully captured by the standard impairment rating. Per LC §4660.1(c)(1), a 1% increase is warranted based on the physician's clinical judgment.",
    2: "2% WPI pain add-on. The patient demonstrates moderate pain-related functional limitations exceeding what would be expected from the objective pathology. Per LC §4660.1(c)(2), a 2% increase is warranted.",
    3: "3% WPI pain add-on (maximum). The patient demonstrates significant pain-related functional limitations substantially exceeding the objective pathology. This represents the maximum additional impairment per LC §4660.1(c)(3). The chronic pain syndrome has an independent impact on the patient's functional capacity.",
}

# ---------------------------------------------------------------------------
# Apportionment Templates (LC §4663 / §4664)
# ---------------------------------------------------------------------------

APPORTIONMENT_TEMPLATES: dict[str, dict[str, str]] = {
    "no_apportionment": {
        "narrative": (
            "After thorough review of all available medical records and detailed consideration "
            "of the patient's pre-injury condition, there is no basis for apportionment under "
            "Labor Code §4663. The current impairment is entirely attributable to the industrial "
            "injury of {doi}. There is no credible evidence of pre-existing pathology, prior "
            "injury, or constitutional factors contributing to the current level of impairment. "
            "This opinion is rendered to a reasonable degree of medical probability."
        ),
        "lc_citation": "LC §4663(a) — physician must address causation of permanent disability",
    },
    "pre_existing_degenerative": {
        "narrative": (
            "Based on review of pre-injury imaging and medical records, the patient had "
            "pre-existing asymptomatic degenerative changes in the {body_parts}. Per Labor Code "
            "§4663, {apportionment_pct}% of the current permanent disability is apportioned to "
            "pre-existing degenerative changes that were asymptomatic but present prior to the "
            "industrial injury. This apportionment is based on the Escobedo v. Marshalls analysis, "
            "as the pre-existing condition was a contributing factor to the current level of "
            "impairment but was not disabling prior to the industrial injury. The remaining "
            "{industrial_pct}% is causally related to the industrial injury."
        ),
        "lc_citation": "LC §4663(a)-(c) — apportionment to pre-existing causes, Escobedo v. Marshalls (2005) 70 CCC 604",
    },
    "prior_injury": {
        "narrative": (
            "The patient has a documented prior industrial injury to the {body_parts} under "
            "ADJ #{prior_adj}. Per Labor Code §4664, {apportionment_pct}% of the current "
            "permanent disability is apportioned to the prior award/settlement as that injury "
            "previously resulted in a permanent disability award of {prior_pd_pct}% for the "
            "same body region. The overlap between the prior and current impairment must be "
            "accounted for to avoid pyramiding of awards per Brodie v. WCAB (2007) 72 CCC 565. "
            "The remaining {industrial_pct}% is attributable to the current industrial injury."
        ),
        "lc_citation": "LC §4664(a)-(b) — apportionment to prior disability awards, Brodie v. WCAB (2007)",
    },
    "constitutional": {
        "narrative": (
            "Per Labor Code §4663(a), {apportionment_pct}% of the current permanent disability "
            "is apportioned to the patient's constitutional predisposition, including factors "
            "such as {constitutional_factors}. This apportionment is supported by the patient's "
            "body habitus, age-related changes, and genetic predisposition as contributing factors "
            "to the current level of impairment. Per the Escobedo analysis, these constitutional "
            "factors existed prior to the industrial injury and are contributing to the current "
            "level of impairment independent of the industrial injury."
        ),
        "lc_citation": "LC §4663(a) — constitutional causes, Escobedo v. Marshalls (2005)",
    },
}

# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------


def calculate_combined_wpi(values: list[int]) -> int:
    """Calculate combined WPI using the Combined Values Chart formula.

    AMA Guides formula: A combined with B = A + B(1-A/100)
    """
    if not values:
        return 0
    if len(values) == 1:
        return values[0]

    sorted_values = sorted(values, reverse=True)
    combined = sorted_values[0]
    for v in sorted_values[1:]:
        combined = combined + v * (100 - combined) // 100

    return min(combined, 100)


def _get_spine_region(body_part: str) -> str | None:
    """Map body part to DRE spine region key."""
    bp = body_part.lower()
    if "cervical" in bp:
        return "cervical"
    if "thoracic" in bp:
        return "thoracic"
    if "lumbar" in bp or "sacrum" in bp or "coccyx" in bp:
        return "lumbar"
    return None


def _pick_dre_category(region: str) -> tuple[str, dict[str, Any]]:
    """Pick a realistic DRE category (weighted toward II-III)."""
    categories = DRE_CATEGORIES.get(region, DRE_CATEGORIES["lumbar"])
    # Weight toward moderate categories (II and III are most common in WC)
    keys = list(categories.keys())
    weights = [5, 35, 40, 15, 5] if len(keys) == 5 else [5, 40, 40, 15]
    weights = weights[:len(keys)]
    chosen_key = random.choices(keys, weights=weights)[0]
    return chosen_key, categories[chosen_key]


def _get_extremity_wpi(body_part: str, pool: dict) -> tuple[int, str]:
    """Get WPI for an extremity body part from ROM or diagnosis-based tables."""
    bp = body_part.lower()
    region = None
    for key in pool:
        if key in bp:
            region = key
            break
    if not region:
        # Check common aliases
        if "shoulder" in bp:
            region = "shoulder"
        elif "knee" in bp:
            region = "knee"
        elif "hip" in bp:
            region = "hip"
        elif "ankle" in bp:
            region = "ankle"
        elif "foot" in bp:
            region = "foot"
        elif "wrist" in bp or "hand" in bp:
            region = "wrist" if "wrist" in pool else "hand"
        elif "elbow" in bp:
            region = "elbow"

    if not region or region not in pool:
        return random.randint(3, 10), "Impairment rated per AMA Guides 5th Edition ROM method."

    entry = pool[region]
    # 60% ROM method, 40% diagnosis-based
    if "rom_wpi_ranges" in entry and random.random() < 0.6:
        severity = random.choice(list(entry["rom_wpi_ranges"].keys()))
        data = entry["rom_wpi_ranges"][severity]
        wpi = random.randint(data["wpi"][0], data["wpi"][1])
        desc = f"ROM method — {data.get('description', severity + ' loss of ROM')}. WPI: {wpi}%."
        return wpi, desc
    elif "diagnosis_based" in entry:
        diag_key = random.choice(list(entry["diagnosis_based"].keys()))
        data = entry["diagnosis_based"][diag_key]
        wpi = random.randint(data["wpi"][0], data["wpi"][1])
        desc = f"Diagnosis-based impairment — {diag_key.replace('_', ' ')}. WPI: {wpi}%."
        return wpi, desc

    return random.randint(3, 10), "Impairment rated per AMA Guides 5th Edition."


def generate_impairment_narrative(
    body_parts: list[str],
    specialty: str,
    apportionment_pct: int = 0,
) -> tuple[str, int, list[dict[str, Any]]]:
    """Generate a full AMA Guides 5th Ed impairment narrative.

    Returns:
        (narrative_text, total_wpi, individual_ratings)
    """
    ratings: list[dict[str, Any]] = []
    narrative_parts: list[str] = []

    narrative_parts.append(
        "Per Labor Code §4660.1, permanent disability is determined using the AMA Guides "
        "to the Evaluation of Permanent Impairment, Fifth Edition. The following impairment "
        "ratings are based on the evaluee's condition at maximum medical improvement."
    )

    # Rate each body part
    for bp in body_parts:
        spine_region = _get_spine_region(bp)

        if spine_region:
            # Spine — use DRE method
            cat_key, cat_data = _pick_dre_category(spine_region)
            wpi = random.randint(cat_data["wpi_range"][0], cat_data["wpi_range"][1])
            table_ref = {"lumbar": "Table 15-3", "cervical": "Table 15-5", "thoracic": "Table 15-4"}[spine_region]
            criteria_used = random.sample(cat_data["criteria"], min(2, len(cat_data["criteria"])))

            narrative_parts.append(
                f"\n<b>{bp.title()} — DRE Method ({table_ref})</b>\n"
                f"{cat_data['description']}\n"
                f"WPI: {wpi}%\n"
                f"Criteria met: {'; '.join(criteria_used)}."
            )
            ratings.append({"body_part": bp, "method": "DRE", "category": cat_key, "wpi": wpi})

        elif "psyche" in bp.lower():
            # Psychiatric — Chapter 14
            gaf = random.randint(41, 68)
            bracket = None
            for (lo, hi), data in PSYCHIATRIC_IMPAIRMENT["gaf_brackets"].items():
                if lo <= gaf <= hi:
                    bracket = data
                    break
            if not bracket:
                bracket = list(PSYCHIATRIC_IMPAIRMENT["gaf_brackets"].values())[1]

            wpi = random.randint(bracket["wpi_range"][0], bracket["wpi_range"][1])
            functional_impairments = random.sample(PSYCHIATRIC_IMPAIRMENT["functional_areas"], 3)

            narrative_parts.append(
                f"\n<b>Psychiatric Impairment — Chapter 14</b>\n"
                f"GAF Score: {gaf} — {bracket['class']} Impairment\n"
                f"{bracket['description']}\n"
                f"Functional areas impaired: {', '.join(functional_impairments)}.\n"
                f"WPI: {wpi}%"
            )
            ratings.append({"body_part": bp, "method": "Chapter 14", "gaf": gaf, "wpi": wpi})

        else:
            # Extremity — UE (Chapter 16) or LE (Chapter 17)
            if any(kw in bp.lower() for kw in ["shoulder", "elbow", "wrist", "hand"]):
                wpi, desc = _get_extremity_wpi(bp, UPPER_EXTREMITY_IMPAIRMENT)
                chapter = "Chapter 16 (Upper Extremity)"
            else:
                wpi, desc = _get_extremity_wpi(bp, LOWER_EXTREMITY_IMPAIRMENT)
                chapter = "Chapter 17 (Lower Extremity)"

            narrative_parts.append(
                f"\n<b>{bp.title()} — {chapter}</b>\n"
                f"{desc}"
            )
            ratings.append({"body_part": bp, "method": chapter, "wpi": wpi})

    # Pain add-on
    pain_addon = random.choices([0, 1, 2, 3], weights=[30, 35, 25, 10])[0]
    if pain_addon > 0:
        narrative_parts.append(
            f"\n<b>Pain Add-On (LC §4660.1(c))</b>\n{PAIN_ADDON_WPI[pain_addon]}"
        )

    # Combined WPI
    wpi_values = [r["wpi"] for r in ratings]
    if pain_addon > 0:
        wpi_values.append(pain_addon)

    total_wpi = calculate_combined_wpi(wpi_values)

    if len(wpi_values) > 1:
        individual_str = " + ".join([str(v) + "%" for v in wpi_values])
        narrative_parts.append(
            f"\n<b>Combined Values Chart</b>\n"
            f"Individual ratings: {individual_str}\n"
            f"Combined WPI per Combined Values Chart (AMA Guides 5th Ed, p. 604): <b>{total_wpi}% WPI</b>"
        )
    else:
        narrative_parts.append(f"\n<b>Total WPI: {total_wpi}%</b>")

    # Apportionment
    if apportionment_pct > 0:
        template_key = random.choice(["pre_existing_degenerative", "constitutional"])
        template = APPORTIONMENT_TEMPLATES[template_key]
        apportionment_text = template["narrative"].format(
            doi="the date of injury",
            body_parts=", ".join(body_parts[:2]),
            apportionment_pct=apportionment_pct,
            industrial_pct=100 - apportionment_pct,
            prior_adj=f"ADJ{random.randint(1000000, 9999999)}",
            prior_pd_pct=random.randint(5, 20),
            constitutional_factors="age-related degenerative changes, body habitus, and genetic predisposition",
        )
        narrative_parts.append(
            f"\n<b>Apportionment — {template['lc_citation']}</b>\n{apportionment_text}"
        )

    narrative = "\n".join(narrative_parts)
    return narrative, total_wpi, ratings
