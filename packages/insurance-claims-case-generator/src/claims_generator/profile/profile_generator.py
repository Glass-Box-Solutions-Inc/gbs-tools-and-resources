"""
Profile generator orchestrator — produces a complete ClaimProfile.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import random

from claims_generator.models.medical import MedicalProfile
from claims_generator.models.profile import ClaimProfile
from claims_generator.profile.claimant_gen import generate_claimant
from claims_generator.profile.employer_gen import generate_employer, generate_insurer
from claims_generator.profile.financial_gen import generate_financial
from claims_generator.profile.injury_gen import generate_injury
from claims_generator.profile.physician_gen import generate_physician


def generate_profile(
    seed: int,
    psych_overlay: bool = False,
    ptd_claim: bool = False,
) -> ClaimProfile:
    """
    Generate a complete ClaimProfile from a seed.

    Args:
        seed: Random seed for reproducibility
        psych_overlay: If True, add a psychiatric diagnosis and QME physician
        ptd_claim: If True, generate higher-wage financial profile

    Returns:
        A fully populated ClaimProfile
    """
    rng = random.Random(seed)

    # Generate sub-profiles
    claimant = generate_claimant(rng)
    employer = generate_employer(rng)

    body_parts, icd10_codes, mechanism, doi = generate_injury(rng, psych_overlay=psych_overlay)

    injury_year = doi.year
    insurer = generate_insurer(rng, claim_year=injury_year)

    treating_physician = generate_physician(rng, role="treating_md")

    # QME physician — generated here, used conditionally based on scenario
    qme_physician = generate_physician(rng, role="qme")
    psych_qme = generate_physician(rng, role="psych") if psych_overlay else None

    financial = generate_financial(
        rng,
        injury_year=injury_year,
        occupation_title=claimant.occupation_title,
        ptd_claim=ptd_claim,
    )

    medical = MedicalProfile(
        date_of_injury=doi.isoformat(),
        injury_mechanism=mechanism,
        body_parts=body_parts,
        icd10_codes=icd10_codes,
        treating_physician=treating_physician,
        qme_physician=qme_physician,
        ame_physician=psych_qme,  # reuse for psych AME if needed
        has_surgery=rng.random() < 0.15,
        surgery_description="Arthroscopic surgery" if rng.random() < 0.15 else None,
        mmi_reached=False,
        wpi_percent=None,
    )

    return ClaimProfile(
        claimant=claimant,
        employer=employer,
        insurer=insurer,
        medical=medical,
        financial=financial,
    )
