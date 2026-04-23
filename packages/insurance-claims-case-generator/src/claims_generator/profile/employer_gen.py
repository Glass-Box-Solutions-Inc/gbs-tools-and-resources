"""
Employer and insurer profile generator.

15 real CA Workers' Compensation carriers + industry-specific employers.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import random

from faker import Faker

from claims_generator.models.employer import EmployerProfile, InsurerProfile

# 15 real CA WC carriers
CA_WC_CARRIERS: list[str] = [
    "State Compensation Insurance Fund (State Fund)",
    "Zenith National Insurance",
    "ICW Group Insurance Companies",
    "Republic Indemnity Company of America",
    "Employers Holdings, Inc.",
    "AmTrust Financial Services",
    "Berkshire Hathaway Homestate Companies",
    "Travelers Property Casualty Company",
    "Liberty Mutual Insurance",
    "Hartford Fire Insurance Company",
    "Zurich American Insurance Company",
    "Chubb Group of Insurance Companies",
    "AIG (American International Group)",
    "Markel Corporation",
    "Tokio Marine America Insurance Company",
]

# Industry pools — (industry_name, employer_name_templates)
INDUSTRY_EMPLOYERS: list[tuple[str, list[str]]] = [
    ("Construction", [
        "Pacific Coast Builders Inc.",
        "Golden State Contractors LLC",
        "Bay Area Construction Group",
        "Sierra Nevada Development Corp.",
        "SoCal Framing & Drywall Co.",
    ]),
    ("Healthcare", [
        "Cedars-Sinai Medical Center",
        "UCSF Health",
        "Providence Health & Services",
        "Kaiser Foundation Hospitals",
        "Dignity Health California",
    ]),
    ("Retail", [
        "California Warehouse Retail Co.",
        "Pacific Retail Partners LP",
        "Golden Gate Grocery Inc.",
        "SoCal Distribution Centers LLC",
        "Valley Logistics Corp.",
    ]),
    ("Transportation", [
        "Pacific Freight Services Inc.",
        "Golden State Trucking LLC",
        "Bay Area Transit Authority",
        "California Parcel Delivery Co.",
        "Western Express Transport Inc.",
    ]),
    ("Manufacturing", [
        "Pacific Manufacturing Group",
        "Golden State Fabricators Inc.",
        "SoCal Metalworks LLC",
        "Central Valley Processing Corp.",
        "California Assembly Partners",
    ]),
    ("Government / Public Sector", [
        "County of Los Angeles",
        "City and County of San Francisco",
        "State of California — Dept. of Transportation",
        "Los Angeles Unified School District",
        "City of San Diego",
    ]),
    ("Agriculture", [
        "Central Valley Farms LLC",
        "Golden State Agricultural Partners",
        "Pacific Coast Produce Inc.",
        "Fresno County Growers Association",
        "California Harvest Corp.",
    ]),
    ("Food Service / Hospitality", [
        "SoCal Restaurant Group LLC",
        "Pacific Hospitality Partners",
        "Golden State Hotels Corp.",
        "Bay Area Food Service Inc.",
        "California Catering Services LLC",
    ]),
]


def generate_employer(rng: random.Random) -> EmployerProfile:
    """Generate a realistic CA employer profile."""
    fake = Faker("en_US")
    fake.seed_instance(rng.randint(0, 2**31))

    industry_entry = rng.choice(INDUSTRY_EMPLOYERS)
    industry, employer_names = industry_entry
    company_name = rng.choice(employer_names)

    cities = ["Los Angeles", "San Diego", "San Jose", "San Francisco",
              "Fresno", "Sacramento", "Oakland", "Bakersfield", "Riverside", "Stockton"]
    city = rng.choice(cities)

    size_category = rng.choices(
        ["small", "medium", "large"],
        weights=[30, 50, 20]
    )[0]

    return EmployerProfile(
        company_name=company_name,
        industry=industry,
        address_city=city,
        address_state="CA",
        ein_last4=f"{rng.randint(1000, 9999)}",
        size_category=size_category,
    )


def generate_insurer(rng: random.Random, claim_year: int = 2025) -> InsurerProfile:
    """Generate a realistic CA WC insurer/adjuster profile."""
    fake = Faker("en_US")
    fake.seed_instance(rng.randint(0, 2**31))

    carrier_name = rng.choice(CA_WC_CARRIERS)

    # Claim number format: YYYYMMDD-XXXXXX
    claim_number = (
        f"{claim_year}{rng.randint(1, 12):02d}"
        f"{rng.randint(1, 28):02d}-{rng.randint(100000, 999999)}"
    )

    adjuster_first = fake.first_name()
    adjuster_last = fake.last_name()
    adjuster_name = f"{adjuster_first} {adjuster_last}"

    # Adjuster phone
    adjuster_phone = f"({rng.randint(200, 999)}) {rng.randint(200, 999)}-{rng.randint(1000, 9999)}"

    # Adjuster email — synthetic domain only
    carrier_slug = carrier_name.lower().split("(")[0].strip().replace(" ", "").replace(",", "")[:12]
    adjuster_email = f"{adjuster_first.lower()}.{adjuster_last.lower()}@{carrier_slug}-claims.com"

    policy_number = f"WC-{rng.randint(10000000, 99999999)}"

    return InsurerProfile(
        carrier_name=carrier_name,
        claim_number=claim_number,
        adjuster_name=adjuster_name,
        adjuster_phone=adjuster_phone,
        adjuster_email=adjuster_email,
        policy_number=policy_number,
    )
