#!/usr/bin/env python3
"""
MerusCase Matter Automation Framework
Main entry point and CLI interface
"""

import asyncio
import sys
import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from security.config import SecurityConfig
from persistence.session_store import SessionStore
from persistence.matter_store import MatterStore
from persistence.audit_store import AuditStore
from security.audit import AuditLogger
from models.matter import MatterDetails, CaseType, BillingInfo
from browser.client import MerusCaseBrowserClient

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/merus_agent.log')
    ]
)

logger = logging.getLogger(__name__)


async def test_browser_connection():
    """Test Browserless connection"""
    print("\n" + "="*60)
    print("Testing Browserless Connection")
    print("="*60 + "\n")

    config = SecurityConfig.from_env()

    try:
        config.validate()
        print("[OK] Configuration validated")

        async with MerusCaseBrowserClient(
            api_token=config.browserless_api_token,
            endpoint=config.browserless_endpoint
        ) as browser:
            print("[OK] Connected to Browserless")

            # Navigate to MerusCase login
            await browser.navigate(config.meruscase_login_url)
            print(f"[OK] Navigated to {config.meruscase_login_url}")

            # Take screenshot
            screenshot_dir = Path("screenshots/test")
            screenshot_dir.mkdir(parents=True, exist_ok=True)
            screenshot_path = screenshot_dir / "login_page.png"

            await browser.screenshot(str(screenshot_path))
            print(f"[OK] Screenshot saved: {screenshot_path}")

            print("\n" + "="*60)
            print("[OK] Browser connection test PASSED")
            print("="*60 + "\n")

            return True

    except Exception as e:
        print(f"\n[FAIL] Browser connection test FAILED: {e}\n")
        logger.error("Browser test failed", exc_info=True)
        return False


async def test_database():
    """Test database initialization"""
    print("\n" + "="*60)
    print("Testing Database Initialization")
    print("="*60 + "\n")

    try:
        config = SecurityConfig.from_env()

        # Initialize stores
        session_store = SessionStore(config.db_path)
        print("[OK] SessionStore initialized")

        matter_store = MatterStore(config.db_path)
        print("[OK] MatterStore initialized")

        audit_logger = AuditLogger(config.db_path)
        print("[OK] AuditLogger initialized")

        # Create test session
        session_id = "test_session_001"
        session = session_store.create_session(session_id)
        print(f"[OK] Created test session: {session_id}")

        # Log audit event
        event_id = audit_logger.log(
            event_type="system_test",
            action="test_initialization",
            status="SUCCESS",
            session_id=session_id,
            metadata={"test": True}
        )
        print(f"[OK] Logged audit event: {event_id}")

        # Create test matter
        matter_id = matter_store.create_matter(
            session_id=session_id,
            matter_type="general",
            primary_party="Test Client",
            dry_run=True
        )
        print(f"[OK] Created test matter: {matter_id}")

        # Cleanup
        session_store.end_session(session_id)
        print("[OK] Ended test session")

        print("\n" + "="*60)
        print("[OK] Database test PASSED")
        print("="*60 + "\n")

        return True

    except Exception as e:
        print(f"\n[FAIL] Database test FAILED: {e}\n")
        logger.error("Database test failed", exc_info=True)
        return False


async def demo_matter_creation():
    """
    Demo: Create a matter in MerusCase (dry-run mode).

    This demonstrates the full workflow without actually submitting.
    """
    print("\n" + "="*60)
    print("Demo: Matter Creation (Dry-Run Mode)")
    print("="*60 + "\n")

    config = SecurityConfig.from_env()

    try:
        # Define matter
        matter = MatterDetails(
            primary_party="John Doe",
            case_type=CaseType.PERSONAL_INJURY,
            attorney_responsible="Jane Smith",
            office="San Francisco Office",
            billing_info=BillingInfo(
                amount_due=5000.00,
                description="Initial retainer for personal injury case"
            )
        )

        print("Matter details:")
        print(f"  Primary Party: {matter.primary_party}")
        print(f"  Case Type: {matter.case_type.value if matter.case_type else 'None'}")
        print(f"  Attorney: {matter.attorney_responsible}")
        print(f"  Office: {matter.office}")
        if matter.billing_info:
            print(f"  Amount Due: ${matter.billing_info.amount_due}")
        print()

        print("Note: Full automation workflow not yet implemented.")
        print("This demo shows data model and configuration working correctly.")
        print()

        print("=" * 60)
        print("[OK] Demo completed successfully")
        print("="*60 + "\n")

        return True

    except Exception as e:
        print(f"\n[FAILED] Demo FAILED: {e}\n")
        logger.error("Demo failed", exc_info=True)
        return False


async def init_database():
    """Initialize database with schema"""
    print("\n" + "="*60)
    print("Initializing Database")
    print("="*60 + "\n")

    config = SecurityConfig.from_env()
    db_path = Path(config.db_path)

    # Check if database already exists
    if db_path.exists():
        print(f"Database already exists at: {db_path}")
        response = input("Recreate database? This will delete all data. (yes/no): ")
        if response.lower() != 'yes':
            print("Database initialization cancelled.")
            return False

        # Backup existing database
        backup_path = db_path.with_suffix('.db.backup')
        import shutil
        shutil.copy(db_path, backup_path)
        print(f"✓ Backup created: {backup_path}")

        # Remove old database
        db_path.unlink()
        print("✓ Old database removed")

    # Initialize new database
    session_store = SessionStore(config.db_path)
    print(f"✓ Database initialized: {db_path}")
    print(f"✓ Schema version: 1.0.0")
    print()

    # Show database location
    print(f"Database path: {db_path.absolute()}")
    print()

    print("="*60)
    print("✓ Database initialization complete")
    print("="*60 + "\n")

    return True


def print_help():
    """Print help information"""
    print("""
MerusCase Matter Automation Framework
======================================

Available commands:

  init-db               Initialize/recreate database
  test-browser          Test Browserless connection
  test-database         Test database operations
  demo                  Run matter creation demo (dry-run)
  help                  Show this help message

Environment variables (set in .env file):
  MERUSCASE_EMAIL       - MerusCase login email
  MERUSCASE_PASSWORD    - MerusCase login password
  BROWSERLESS_API_TOKEN - Browserless API token
  DB_PATH               - Database file path (default: ./knowledge/db/merus_knowledge.db)

Examples:
  python main.py init-db
  python main.py test-browser
  python main.py test-database
  python main.py demo

For more information, see README.md
""")


async def main():
    """Main entry point"""
    # Ensure logs directory exists
    Path("logs").mkdir(exist_ok=True)

    # Parse command line arguments
    if len(sys.argv) < 2:
        print_help()
        return

    command = sys.argv[1].lower()

    if command == "init-db":
        await init_database()

    elif command == "test-browser":
        await test_browser_connection()

    elif command == "test-database":
        await test_database()

    elif command == "demo":
        await demo_matter_creation()

    elif command == "help":
        print_help()

    else:
        print(f"Unknown command: {command}\n")
        print_help()


if __name__ == "__main__":
    asyncio.run(main())
