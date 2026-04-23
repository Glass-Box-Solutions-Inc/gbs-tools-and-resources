"""
Injury generator — ICD-10 codes, body parts, and injury mechanisms.

All codes are plausible CA WC injury diagnoses. Pools are realistic but synthetic.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import random
from datetime import date, timedelta

from claims_generator.models.medical import BodyPart, ICD10Entry

# ICD-10 pools for common CA WC body parts
# (icd10_code, description, body_part_slug)
ICD10_POOL: list[tuple[str, str, str]] = [
    # Lumbar spine
    ("M54.5", "Low back pain", "lumbar spine"),
    ("M51.16", "Intervertebral disc degeneration, lumbar region", "lumbar spine"),
    ("M54.4", "Lumbago with sciatica, right side", "lumbar spine"),
    ("S39.012A", "Strain of muscle, fascia and tendon of lower back", "lumbar spine"),
    # Cervical spine
    ("M54.2", "Cervicalgia", "cervical spine"),
    ("M50.12", "Cervical disc displacement, mid-cervical region", "cervical spine"),
    ("S13.4XXA", "Sprain of ligaments of cervical spine", "cervical spine"),
    # Shoulder
    ("M75.1", "Rotator cuff syndrome", "right shoulder"),
    ("M75.1", "Rotator cuff syndrome", "left shoulder"),
    ("S40.019A", "Contusion of shoulder", "right shoulder"),
    ("M75.5", "Bursitis of shoulder", "left shoulder"),
    # Knee
    ("M23.200", "Derangement of unspecified meniscus", "right knee"),
    ("M17.11", "Primary osteoarthritis, right knee", "right knee"),
    ("S83.009A", "Unspecified tear of unspecified meniscus", "left knee"),
    ("M23.200", "Derangement of unspecified meniscus", "left knee"),
    # Wrist / hand
    ("S62.001A", "Fracture of unspecified carpal bone", "right wrist"),
    ("G56.00", "Carpal tunnel syndrome, unspecified upper limb", "right wrist"),
    ("G56.02", "Carpal tunnel syndrome, left upper limb", "left wrist"),
    ("S62.90XA", "Unspecified fracture of unspecified wrist and hand", "right hand"),
    # Elbow
    ("M77.10", "Lateral epicondylitis, unspecified elbow", "right elbow"),
    ("M77.00", "Medial epicondylitis, unspecified elbow", "left elbow"),
    # Hip
    ("M16.11", "Unilateral primary osteoarthritis, right hip", "right hip"),
    ("S72.001A", "Fracture of unspecified part of neck of right femur", "right hip"),
    # Ankle / foot
    ("S93.401A", "Sprain of unspecified ligament of right ankle", "right ankle"),
    ("S93.402A", "Sprain of unspecified ligament of left ankle", "left ankle"),
    ("M79.671", "Pain in right foot", "right foot"),
    # Psychological
    ("F41.1", "Generalized anxiety disorder", "psyche"),
    ("F32.1", "Major depressive disorder, single episode, moderate", "psyche"),
    ("F43.10", "Post-traumatic stress disorder, unspecified", "psyche"),
    # Eye
    ("S05.91XA", "Unspecified injury of right eye and orbit", "right eye"),
    # Hearing
    ("H83.3X1", "Noise effects on right inner ear", "bilateral ears"),
]

INJURY_MECHANISMS: list[str] = [
    "slip and fall on wet floor",
    "lifting heavy object",
    "repetitive motion — assembly line work",
    "struck by falling object",
    "motor vehicle accident — work-related",
    "fall from ladder or scaffold",
    "overexertion while pushing/pulling",
    "cumulative trauma from keyboard/mouse use",
    "caught in/between machinery",
    "chemical exposure — skin/respiratory",
    "electrical shock",
    "repetitive reaching overhead",
    "trip and fall over equipment",
    "struck by vehicle in parking lot",
    "ergonomic injury — prolonged standing",
]

BODY_PART_DISPLAY: dict[str, str] = {
    "lumbar spine": "Lumbar Spine",
    "cervical spine": "Cervical Spine",
    "right shoulder": "Right Shoulder",
    "left shoulder": "Left Shoulder",
    "right knee": "Right Knee",
    "left knee": "Left Knee",
    "right wrist": "Right Wrist",
    "left wrist": "Left Wrist",
    "right hand": "Right Hand",
    "right elbow": "Right Elbow",
    "left elbow": "Left Elbow",
    "right hip": "Right Hip",
    "right ankle": "Right Ankle",
    "left ankle": "Left Ankle",
    "right foot": "Right Foot",
    "psyche": "Psyche",
    "right eye": "Right Eye",
    "bilateral ears": "Bilateral Ears",
}


def generate_injury(
    rng: random.Random, psych_overlay: bool = False
) -> tuple[list[BodyPart], list[ICD10Entry], str, date]:
    """
    Generate injury body parts, ICD-10 codes, mechanism, and date of injury.

    Returns:
        (body_parts, icd10_codes, mechanism, date_of_injury)
    """
    mechanism = rng.choice(INJURY_MECHANISMS)

    # Primary body part(s) — 1 to 3
    num_body_parts = rng.choices([1, 2, 3], weights=[60, 30, 10])[0]

    # Filter to non-psych entries for primary selection
    physical_pool = [(c, d, bp) for c, d, bp in ICD10_POOL if bp != "psyche"]
    # Choose distinct body parts
    selected_diagnoses: list[tuple[str, str, str]] = []
    chosen_body_parts: set[str] = set()
    attempts = 0
    while len(selected_diagnoses) < num_body_parts and attempts < 50:
        candidate = rng.choice(physical_pool)
        if candidate[2] not in chosen_body_parts:
            selected_diagnoses.append(candidate)
            chosen_body_parts.add(candidate[2])
        attempts += 1

    if psych_overlay:
        # Add a psychiatric diagnosis
        psych_entries = [(c, d, bp) for c, d, bp in ICD10_POOL if bp == "psyche"]
        selected_diagnoses.append(rng.choice(psych_entries))

    body_parts = [
        BodyPart(
            body_part=BODY_PART_DISPLAY.get(bp, bp),
            laterality=_laterality(bp),
            primary=(i == 0),
        )
        for i, (_, _, bp) in enumerate(selected_diagnoses)
    ]

    icd10_codes = [
        ICD10Entry(code=code, description=desc, body_part=BODY_PART_DISPLAY.get(bp, bp))
        for code, desc, bp in selected_diagnoses
    ]

    # Date of injury — 6 months to 3 years ago
    today = date.today()
    days_ago = rng.randint(180, 1095)
    doi = today - timedelta(days=days_ago)

    return body_parts, icd10_codes, mechanism, doi


def _laterality(body_part: str) -> str | None:
    """Extract laterality from body_part slug."""
    if body_part.startswith("right "):
        return "right"
    if body_part.startswith("left "):
        return "left"
    if "bilateral" in body_part:
        return "bilateral"
    return None
