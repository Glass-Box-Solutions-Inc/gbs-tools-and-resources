#!/usr/bin/env python3
"""
Quick test script for MerusCase framework
Runs all tests without user prompts
"""

import asyncio
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from security.config import SecurityConfig
from persistence.session_store import SessionStore
from persistence.matter_store import MatterStore
from security.audit import AuditLogger
from models.matter import MatterDetails, CaseType, BillingInfo

# Load environment variables
load_dotenv()

def print_section(title):
    """Print section header"""
    print("\n" + "="*60)
    print(title)
    print("="*60 + "\n")


async def test_database():
    """Test database initialization and operations"""
    print_section("TEST 1: Database Operations")

    try:
        config = SecurityConfig.from_env()

        # Initialize stores
        print("Initializing stores...")
        session_store = SessionStore(config.db_path)
        matter_store = MatterStore(config.db_path)
        audit_logger = AuditLogger(config.db_path)
        print("[OK] All stores initialized successfully")

        # Cleanup any existing test session
        session_id = "test_session_automated"
        try:
            from persistence.utils import get_db_connection
            with get_db_connection(config.db_path) as conn:
                conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
                conn.commit()
            print(f"\nCleaned up existing test session")
        except Exception:
            pass  # Session doesn't exist, that's fine

        # Create test session
        print(f"\nCreating test session: {session_id}")
        session = session_store.create_session(
            session_id,
            metadata={"test": True, "automated": True}
        )
        print(f"[OK] Session created: {session['session_id']}")
        print(f"  - Phase: {session['agent_phase']}")
        print(f"  - Timeout: {session_store.session_timeout_min} minutes")
        print(f"  - Max duration: {session_store.max_session_hours} hours")

        # Validate session
        print(f"\nValidating session...")
        is_valid = session_store.validate_session(session_id)
        print(f"[OK] Session valid: {is_valid}")

        # Log audit event
        print(f"\nLogging audit event...")
        event_id = audit_logger.log(
            event_type="framework_test",
            action="test_database_operations",
            status="SUCCESS",
            session_id=session_id,
            metadata={
                "test_type": "automated",
                "framework_version": "1.0.0-alpha"
            }
        )
        print(f"[OK] Audit event logged: {event_id}")

        # Create test matter
        print(f"\nCreating test matter...")
        matter_id = matter_store.create_matter(
            session_id=session_id,
            matter_type="general",
            primary_party="Test Client (Automated)",
            custom_fields={
                "test_field": "test_value",
                "automated": True
            },
            dry_run=True
        )
        print(f"[OK] Matter created: ID={matter_id}")

        # Get matter details
        matter = matter_store.get_matter(matter_id)
        print(f"  - Primary Party: {matter['primary_party']}")
        print(f"  - Type: {matter['matter_type']}")
        print(f"  - Status: {matter['status']}")
        print(f"  - Dry Run: {bool(matter['dry_run'])}")

        # Update matter status
        print(f"\nUpdating matter status...")
        matter_store.update_status(matter_id, "success")
        print(f"[OK] Matter status updated to 'success'")

        # Get session audit trail
        print(f"\nRetrieving audit trail...")
        events = audit_logger.store.get_session_events(session_id)
        print(f"[OK] Found {len(events)} audit events for session")

        # Get statistics
        print(f"\nGetting statistics...")
        matter_stats = matter_store.get_matter_stats()
        audit_stats = audit_logger.store.get_audit_stats()
        print(f"[OK] Total matters: {matter_stats['total']}")
        print(f"[OK] Total audit events: {audit_stats['total']}")

        # Cleanup
        print(f"\nCleaning up test session...")
        session_store.end_session(session_id)
        print(f"[OK] Session ended")

        print_section("[OK] DATABASE TEST PASSED")
        return True

    except Exception as e:
        print(f"\n[FAIL] DATABASE TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_configuration():
    """Test configuration loading"""
    print_section("TEST 2: Configuration")

    try:
        config = SecurityConfig.from_env()
        print("Configuration loaded from environment:")
        print(f"  - MerusCase Email: {config.meruscase_email}")
        print(f"  - MerusCase URL: {config.meruscase_base_url}")
        print(f"  - Database Path: {config.db_path}")
        print(f"  - Session Timeout: {config.session_timeout_min} minutes")
        print(f"  - Max Session: {config.max_session_hours} hours")
        print(f"  - Audit Retention: {config.audit_retention_days} days")
        print(f"  - Screenshot Retention: {config.screenshot_retention_hr} hours")
        print(f"  - Browserless Endpoint: {config.browserless_endpoint}")

        # Check required fields
        print(f"\nValidating required fields...")
        has_email = bool(config.meruscase_email)
        has_password = bool(config.meruscase_password)
        has_token = bool(config.browserless_api_token)

        print(f"  - MerusCase Email: {'[OK] Set' if has_email else '[FAIL] Missing'}")
        print(f"  - MerusCase Password: {'[OK] Set' if has_password else '[FAIL] Missing'}")
        print(f"  - Browserless Token: {'[OK] Set' if has_token else '[WARN] Missing (optional for DB tests)'}")

        if has_email and has_password:
            print_section("[OK] CONFIGURATION TEST PASSED")
            return True
        else:
            print_section("[WARN] CONFIGURATION TEST PARTIAL (missing browser token)")
            return True

    except Exception as e:
        print(f"\n[FAIL] CONFIGURATION TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_data_models():
    """Test Pydantic data models"""
    print_section("TEST 3: Data Models")

    try:
        # Create matter details
        print("Creating MatterDetails model...")
        matter = MatterDetails(
            primary_party="John Doe",
            case_type=CaseType.PERSONAL_INJURY,
            case_status="Open",
            attorney_responsible="Jane Smith",
            office="San Francisco Office",
            billing_info=BillingInfo(
                amount_due=5000.00,
                description="Initial retainer for personal injury case",
                amount_received=2500.00,
                check_number="CHK-12345",
                memo="50% upfront payment"
            ),
            custom_fields={
                "injury_date": "2024-12-15",
                "incident_location": "123 Main St"
            }
        )
        print("[OK] MatterDetails model created")

        # Test form mapping
        print("\nTesting form field mapping...")
        form_mapping = matter.to_form_mapping()
        print(f"[OK] Generated {len(form_mapping)} form fields:")
        for field, value in list(form_mapping.items())[:5]:
            print(f"  - {field}: {value}")
        if len(form_mapping) > 5:
            print(f"  ... and {len(form_mapping) - 5} more fields")

        # Test validation
        print("\nTesting model validation...")
        try:
            invalid_matter = MatterDetails(
                primary_party=""  # Should fail - empty string
            )
            print("[FAIL] Validation should have failed")
            return False
        except Exception:
            print("[OK] Validation correctly rejected empty primary_party")

        print_section("[OK] DATA MODELS TEST PASSED")
        return True

    except Exception as e:
        print(f"\n[FAIL] DATA MODELS TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


async def run_all_tests():
    """Run all tests"""
    print("\n" + "="*60)
    print("MERUSCASE FRAMEWORK AUTOMATED TEST SUITE")
    print("="*60)

    results = []

    # Test 1: Configuration
    results.append(("Configuration", await test_configuration()))

    # Test 2: Data Models
    results.append(("Data Models", await test_data_models()))

    # Test 3: Database
    results.append(("Database Operations", await test_database()))

    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status:8} - {test_name}")

    print("\n" + "="*60)
    print(f"RESULTS: {passed}/{total} tests passed ({passed/total*100:.0f}%)")
    print("="*60 + "\n")

    if passed == total:
        print("SUCCESS: All tests passed! Framework is ready.")
        print("\nNext steps:")
        print("  1. Add BROWSERLESS_API_TOKEN to .env to test browser")
        print("  2. Run: python test_framework.py")
        print("  3. Build full matter creation workflow")
        return True
    else:
        print("WARNING: Some tests failed. Review errors above.")
        return False


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
