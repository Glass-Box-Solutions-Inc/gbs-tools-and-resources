"""
Physician profile generator — treating MD, QME panel, AME.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import random

from faker import Faker

from claims_generator.models.medical import PhysicianProfile

SPECIALTIES: list[tuple[str, str]] = [
    # (role, specialty)
    ("treating_md", "Occupational Medicine"),
    ("treating_md", "Orthopedic Surgery"),
    ("treating_md", "Family Medicine"),
    ("treating_md", "Physical Medicine and Rehabilitation"),
    ("qme", "Orthopedic Surgery"),
    ("qme", "Neurology"),
    ("qme", "Pain Management"),
    ("qme", "Occupational Medicine"),
    ("ame", "Orthopedic Surgery"),
    ("ame", "Internal Medicine"),
    ("ime", "Orthopedic Surgery"),
    ("psych", "Psychiatry"),
    ("psych", "Psychology"),
]

CA_MEDICAL_CITIES: list[str] = [
    "Los Angeles", "San Diego", "San Jose", "San Francisco",
    "Sacramento", "Fresno", "Oakland", "Long Beach",
    "Bakersfield", "Riverside",
]


def generate_physician(
    rng: random.Random,
    role: str = "treating_md",
    specialty: str | None = None,
) -> PhysicianProfile:
    """Generate a realistic physician profile for the given role."""
    fake = Faker("en_US")
    fake.seed_instance(rng.randint(0, 2**31))

    # Choose specialty if not provided
    if specialty is None:
        role_specialties = [s for r, s in SPECIALTIES if r == role]
        if not role_specialties:
            role_specialties = ["Occupational Medicine"]
        specialty = rng.choice(role_specialties)

    first_name = fake.first_name()
    last_name = fake.last_name()

    # CA medical license format: A12345 (letters + digits)
    license_number = f"G{rng.randint(10000, 99999)}"

    # NPI — 10-digit number
    npi = f"{rng.randint(1000000000, 1999999999)}"

    city = rng.choice(CA_MEDICAL_CITIES)

    return PhysicianProfile(
        role=role,
        first_name=first_name,
        last_name=last_name,
        specialty=specialty,
        license_number=license_number,
        address_city=city,
        npi=npi,
    )
