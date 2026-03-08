#!/usr/bin/env python3
"""
Database initializer for merus-expert.

Reads setup/schema.sql and initializes the SQLite database.

Usage:
    python scripts/init_db.py
    python scripts/init_db.py --db-path /data/merus_knowledge.db

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import sqlite3
import sys
import argparse
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Repo root — resolve relative to this script's location
REPO_ROOT = Path(__file__).parent.parent
SCHEMA_PATH = REPO_ROOT / "setup" / "schema.sql"
DEFAULT_DB_PATH = REPO_ROOT / "data" / "merus_knowledge.db"


def init_db(db_path: Path, schema_path: Path = SCHEMA_PATH) -> None:
    """
    Initialize SQLite database from schema.sql.

    Args:
        db_path: Path to SQLite database file
        schema_path: Path to SQL schema file
    """
    if not schema_path.exists():
        logger.error(f"Schema file not found: {schema_path}")
        sys.exit(1)

    # Create parent directory if needed
    db_path.parent.mkdir(parents=True, exist_ok=True)

    existed = db_path.exists()

    schema_sql = schema_path.read_text(encoding="utf-8")

    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.cursor()
        cursor.executescript(schema_sql)
        conn.commit()
        logger.info(f"{'Updated' if existed else 'Created'} database: {db_path}")

        # Report table count
        cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
        table_count = cursor.fetchone()[0]
        logger.info(f"Database has {table_count} tables")
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Initialize merus-expert SQLite database"
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"Path to SQLite database (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--schema-path",
        type=Path,
        default=SCHEMA_PATH,
        help=f"Path to schema.sql (default: {SCHEMA_PATH})",
    )
    args = parser.parse_args()

    logger.info(f"Initializing database at: {args.db_path}")
    logger.info(f"Using schema: {args.schema_path}")
    init_db(args.db_path, args.schema_path)
    logger.info("Done.")


if __name__ == "__main__":
    main()
