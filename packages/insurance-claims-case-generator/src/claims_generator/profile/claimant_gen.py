"""
Claimant profile generator — CA demographics with county distribution.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import random
from datetime import date, timedelta

from faker import Faker

from claims_generator.models.claimant import ClaimantProfile

# Weighted CA county distribution (approximate population weights)
CA_COUNTIES: list[tuple[str, str, float]] = [
    # (county, representative_city, weight)
    ("Los Angeles", "Los Angeles", 30.0),
    ("San Diego", "San Diego", 8.5),
    ("Orange", "Anaheim", 8.0),
    ("Riverside", "Riverside", 5.5),
    ("San Bernardino", "San Bernardino", 5.5),
    ("Santa Clara", "San Jose", 5.0),
    ("Alameda", "Oakland", 4.0),
    ("Sacramento", "Sacramento", 3.5),
    ("Contra Costa", "Concord", 3.0),
    ("Fresno", "Fresno", 2.5),
    ("Kern", "Bakersfield", 2.0),
    ("San Francisco", "San Francisco", 2.0),
    ("Ventura", "Oxnard", 2.0),
    ("San Mateo", "Redwood City", 1.8),
    ("Stanislaus", "Modesto", 1.5),
    ("Sonoma", "Santa Rosa", 1.3),
    ("Tulare", "Visalia", 1.2),
    ("Solano", "Fairfield", 1.1),
    ("Monterey", "Salinas", 1.0),
    ("Santa Barbara", "Santa Barbara", 1.0),
    ("Placer", "Roseville", 0.9),
    ("San Joaquin", "Stockton", 0.9),
    ("Shasta", "Redding", 0.6),
    ("Imperial", "El Centro", 0.5),
    ("Humboldt", "Eureka", 0.4),
]

CA_ZIP_PREFIXES: dict[str, str] = {
    "Los Angeles": "900",
    "San Diego": "921",
    "Orange": "926",
    "Riverside": "925",
    "San Bernardino": "924",
    "Santa Clara": "951",
    "Alameda": "946",
    "Sacramento": "958",
    "Contra Costa": "945",
    "Fresno": "937",
    "Kern": "932",
    "San Francisco": "941",
    "Ventura": "930",
    "San Mateo": "940",
    "Stanislaus": "953",
    "Sonoma": "954",
    "Tulare": "932",
    "Solano": "945",
    "Monterey": "939",
    "Santa Barbara": "931",
    "Placer": "956",
    "San Joaquin": "952",
    "Shasta": "960",
    "Imperial": "922",
    "Humboldt": "955",
}

OCCUPATIONS: list[str] = [
    "Warehouse Worker",
    "Construction Laborer",
    "Registered Nurse",
    "Delivery Driver",
    "Retail Associate",
    "Food Service Worker",
    "Janitor / Custodian",
    "Security Guard",
    "Administrative Assistant",
    "Truck Driver (CDL)",
    "Machine Operator",
    "Maintenance Technician",
    "Home Health Aide",
    "Landscaper",
    "Forklift Operator",
    "Teacher",
    "Police Officer",
    "Firefighter",
    "Cook / Chef",
    "Auto Mechanic",
]


def generate_claimant(rng: random.Random) -> ClaimantProfile:
    """Generate a realistic CA claimant profile."""
    fake = Faker("en_US")
    fake.seed_instance(rng.randint(0, 2**31))

    # Gender
    gender = rng.choice(["M", "F", "M", "M", "F"])  # slight male skew for WC

    if gender == "M":
        first_name = fake.first_name_male()
    else:
        first_name = fake.first_name_female()

    last_name = fake.last_name()

    # Age: 18–65 working age
    age_years = rng.randint(18, 65)
    today = date.today()
    dob = today - timedelta(days=365 * age_years + rng.randint(0, 364))

    # County weighted selection
    county_weights = [c[2] for c in CA_COUNTIES]
    total = sum(county_weights)
    r = rng.random() * total
    cumulative = 0.0
    selected_county = CA_COUNTIES[0]
    for county in CA_COUNTIES:
        cumulative += county[2]
        if r <= cumulative:
            selected_county = county
            break

    county_name, city, _ = selected_county
    zip_prefix = CA_ZIP_PREFIXES.get(county_name, "900")
    zip_code = f"{zip_prefix}{rng.randint(0, 99):02d}"

    # Generate phone
    phone = f"({rng.randint(200, 999)}) {rng.randint(200, 999)}-{rng.randint(1000, 9999)}"

    # SSN last 4 only
    ssn_last4 = f"{rng.randint(1000, 9999)}"

    occupation = rng.choice(OCCUPATIONS)
    years_employed = round(rng.uniform(0.5, 25.0), 1)

    return ClaimantProfile(
        first_name=first_name,
        last_name=last_name,
        date_of_birth=dob,
        gender=gender,
        address_city=city,
        address_county=county_name,
        address_zip=zip_code,
        phone=phone,
        ssn_last4=ssn_last4,
        primary_language=rng.choices(
            ["English", "Spanish", "Vietnamese", "Chinese"], weights=[70, 20, 5, 5]
        )[0],
        occupation_title=occupation,
        years_employed=years_employed,
    )
