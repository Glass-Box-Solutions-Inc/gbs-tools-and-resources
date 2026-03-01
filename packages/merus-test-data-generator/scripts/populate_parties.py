#!/usr/bin/env python3
"""
Populate comprehensive Workers' Comp parties on all MerusCase test cases.

Usage:
    python3 scripts/populate_parties.py [--case TC-001]

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import asyncio
import sqlite3
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import structlog
from config import DB_PATH, RANDOM_SEED
from data.case_profiles import CASE_PROFILES
from data.fake_data_generator import FakeDataGenerator
from data.models import GeneratedCase
from orchestration.party_populator import PartyPopulator


def regenerate_cases() -> list[GeneratedCase]:
    """Regenerate cases using the same seed for deterministic output."""
    generator = FakeDataGenerator(seed=RANDOM_SEED)
    cases = []
    for profile in CASE_PROFILES:
        case = generator.generate_case(profile)
        cases.append(case)
    return cases


def get_case_id_map() -> dict[str, int]:
    """Get mapping from internal_id to meruscase_id from progress DB."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT internal_id, meruscase_id FROM cases WHERE case_created = 1"
    ).fetchall()
    conn.close()
    return {r["internal_id"]: r["meruscase_id"] for r in rows}


async def main():
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
    )
    logger = structlog.get_logger()

    # Parse args
    single_case = None
    if len(sys.argv) > 2 and sys.argv[1] == "--case":
        single_case = sys.argv[2]

    logger.info("regenerating_cases", seed=RANDOM_SEED)
    cases = regenerate_cases()

    case_id_map = get_case_id_map()
    logger.info(
        "cases_ready",
        total_cases=len(cases),
        mapped_cases=len(case_id_map),
    )

    if single_case:
        cases = [c for c in cases if c.internal_id == single_case]
        if not cases:
            logger.error("case_not_found", case_id=single_case)
            sys.exit(1)
        logger.info("single_case_mode", case_id=single_case)

    populator = PartyPopulator()
    result = await populator.populate_all(cases, case_id_map)

    logger.info(
        "population_complete",
        cases_processed=result["cases_processed"],
        parties_added=result["parties_added"],
        parties_failed=result["parties_failed"],
    )


if __name__ == "__main__":
    asyncio.run(main())
