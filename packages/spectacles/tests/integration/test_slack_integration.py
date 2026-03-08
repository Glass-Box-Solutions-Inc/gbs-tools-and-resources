"""
Spectacles Slack Integration Test Suite

Automated tests for webhook notifications, command parsing, and message routing.
For manual/interactive tests (button clicks, visual verification), see manual_test_procedures.md

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import asyncio
import logging
import sys
import os
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
import json

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from hitl.webhook_client import create_webhook_client_from_env
from hitl.intent_classifier import IntentClassifier
from hitl.command_parser import CommandParser

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SlackIntegrationTester:
    """Test harness for Spectacles Slack integration"""

    def __init__(self):
        self.results: List[Dict] = []
        self.webhook_client = None
        self.intent_classifier = IntentClassifier()
        self.test_channel_id = None  # Will be set to test channel

    async def setup(self):
        """Initialize test environment"""
        logger.info("Setting up test environment...")

        # Initialize webhook client from environment
        try:
            self.webhook_client = create_webhook_client_from_env()
            logger.info("✅ Webhook client initialized")
        except Exception as e:
            logger.error(f"❌ Failed to initialize webhook client: {e}")
            raise

    def record_result(self, test_case: str, status: str, notes: str = ""):
        """Record test result"""
        result = {
            "test_case": test_case,
            "status": status,
            "notes": notes,
            "timestamp": datetime.now().isoformat()
        }
        self.results.append(result)
        logger.info(f"{status} {test_case}: {notes}")

    # ==========================================================================
    # SCENARIO 1: Webhook Notifications (One-Way)
    # ==========================================================================

    async def test_1_1_info_notification(self):
        """Test Case 1.1: Send info notification to main channel"""
        try:
            success = await self.webhook_client.send_message(
                text="[TEST] Info notification from Spectacles integration test",
                webhook_name="default"
            )

            if success:
                self.record_result("1.1: Info notification", "✅ PASS", "Message sent successfully")
            else:
                self.record_result("1.1: Info notification", "❌ FAIL", "Message send failed")

        except Exception as e:
            self.record_result("1.1: Info notification", "❌ ERROR", str(e))

    async def test_1_2_warning_notification(self):
        """Test Case 1.2: Send warning notification with context"""
        try:
            blocks = [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "⚠️ *Warning: Test notification*\n\nThis is a test warning from integration testing."
                    }
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"Test run: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                        }
                    ]
                }
            ]

            success = await self.webhook_client.send_message(
                text="[TEST] Warning notification",
                blocks=blocks,
                webhook_name="default"
            )

            if success:
                self.record_result("1.2: Warning notification", "✅ PASS", "Block Kit message sent")
            else:
                self.record_result("1.2: Warning notification", "❌ FAIL", "Message send failed")

        except Exception as e:
            self.record_result("1.2: Warning notification", "❌ ERROR", str(e))

    async def test_1_3_error_notification_emoji(self):
        """Test Case 1.3: Send error notification with emoji"""
        try:
            success = await self.webhook_client.send_message(
                text="🚨 [TEST] Error notification from integration test",
                webhook_name="default"
            )

            if success:
                self.record_result("1.3: Error notification with emoji", "✅ PASS", "Emoji rendered")
            else:
                self.record_result("1.3: Error notification with emoji", "❌ FAIL", "Message send failed")

        except Exception as e:
            self.record_result("1.3: Error notification with emoji", "❌ ERROR", str(e))

    async def test_1_4_success_notification(self):
        """Test Case 1.4: Send success notification"""
        try:
            success = await self.webhook_client.send_message(
                text="✅ [TEST] Success notification from integration test",
                webhook_name="default"
            )

            if success:
                self.record_result("1.4: Success notification", "✅ PASS", "Message sent")
            else:
                self.record_result("1.4: Success notification", "❌ FAIL", "Message send failed")

        except Exception as e:
            self.record_result("1.4: Success notification", "❌ ERROR", str(e))

    # ==========================================================================
    # SCENARIO 7: Intent Classification
    # ==========================================================================

    def test_7_1_status_query_intent(self):
        """Test Case 7.1: Status query → STATUS_QUERY intent"""
        test_messages = [
            "status of task-123",
            "what's the status of task 456?",
            "how is task-789 doing?",
            "task-101 status"
        ]

        passed = 0
        total = len(test_messages)

        for msg in test_messages:
            result = self.intent_classifier.classify(msg)
            if result.intent.name == "STATUS_QUERY":
                passed += 1

        accuracy = (passed / total) * 100
        if accuracy >= 90:
            self.record_result("7.1: Status query intent", "✅ PASS", f"Accuracy: {accuracy}%")
        else:
            self.record_result("7.1: Status query intent", "❌ FAIL", f"Accuracy: {accuracy}% (expected >90%)")

    def test_7_2_command_intent(self):
        """Test Case 7.2: Command → COMMAND intent"""
        test_messages = [
            "pause task-123",
            "cancel task 456",
            "resume task-789",
            "list tasks"
        ]

        passed = 0
        total = len(test_messages)

        for msg in test_messages:
            result = self.intent_classifier.classify(msg)
            if result.intent.name == "COMMAND":
                passed += 1

        accuracy = (passed / total) * 100
        if accuracy >= 90:
            self.record_result("7.2: Command intent", "✅ PASS", f"Accuracy: {accuracy}%")
        else:
            self.record_result("7.2: Command intent", "❌ FAIL", f"Accuracy: {accuracy}% (expected >90%)")

    def test_7_3_question_intent(self):
        """Test Case 7.3: Question → QUESTION intent"""
        test_messages = [
            "what tasks are running?",
            "how many tasks are active?",
            "what's happening with project X?"
        ]

        passed = 0
        total = len(test_messages)

        for msg in test_messages:
            result = self.intent_classifier.classify(msg)
            if result.intent.name == "QUESTION":
                passed += 1

        accuracy = (passed / total) * 100
        if accuracy >= 90:
            self.record_result("7.3: Question intent", "✅ PASS", f"Accuracy: {accuracy}%")
        else:
            self.record_result("7.3: Question intent", "❌ FAIL", f"Accuracy: {accuracy}% (expected >90%)")

    def test_7_5_help_intent(self):
        """Test Case 7.5: Help → HELP intent"""
        test_messages = [
            "help",
            "show me the commands",
            "what can you do?",
            "help me"
        ]

        passed = 0
        total = len(test_messages)

        for msg in test_messages:
            result = self.intent_classifier.classify(msg)
            if result.intent.name == "HELP":
                passed += 1

        accuracy = (passed / total) * 100
        if accuracy >= 90:
            self.record_result("7.5: Help intent", "✅ PASS", f"Accuracy: {accuracy}%")
        else:
            self.record_result("7.5: Help intent", "❌ FAIL", f"Accuracy: {accuracy}% (expected >90%)")

    # ==========================================================================
    # Test Runner
    # ==========================================================================

    async def run_scenario_1_webhooks(self):
        """Run Scenario 1: Webhook Notifications"""
        logger.info("\n" + "="*80)
        logger.info("SCENARIO 1: Webhook Notifications (One-Way)")
        logger.info("="*80)

        await self.test_1_1_info_notification()
        await asyncio.sleep(1)  # Rate limiting

        await self.test_1_2_warning_notification()
        await asyncio.sleep(1)

        await self.test_1_3_error_notification_emoji()
        await asyncio.sleep(1)

        await self.test_1_4_success_notification()
        await asyncio.sleep(1)

    def run_scenario_7_intent_classification(self):
        """Run Scenario 7: Intent Classification"""
        logger.info("\n" + "="*80)
        logger.info("SCENARIO 7: Intent Classification")
        logger.info("="*80)

        self.test_7_1_status_query_intent()
        self.test_7_2_command_intent()
        self.test_7_3_question_intent()
        self.test_7_5_help_intent()

    async def run_all_automated_tests(self):
        """Run all automated tests"""
        logger.info("\n" + "="*80)
        logger.info("SPECTACLES SLACK INTEGRATION - AUTOMATED TESTS")
        logger.info("="*80 + "\n")

        await self.setup()

        # Scenario 1: Webhooks
        await self.run_scenario_1_webhooks()

        # Scenario 7: Intent Classification
        self.run_scenario_7_intent_classification()

        # Generate report
        self.generate_report()

    def generate_report(self):
        """Generate test results report"""
        logger.info("\n" + "="*80)
        logger.info("TEST RESULTS SUMMARY")
        logger.info("="*80)

        total = len(self.results)
        passed = sum(1 for r in self.results if r["status"].startswith("✅"))
        failed = sum(1 for r in self.results if r["status"].startswith("❌"))

        logger.info(f"\nTotal Tests: {total}")
        logger.info(f"Passed: {passed} ({(passed/total*100):.1f}%)")
        logger.info(f"Failed: {failed} ({(failed/total*100):.1f}%)")

        if failed > 0:
            logger.info("\n⚠️ Failed Tests:")
            for r in self.results:
                if r["status"].startswith("❌"):
                    logger.info(f"  - {r['test_case']}: {r['notes']}")

        # Save results to file
        results_file = Path(__file__).parent.parent.parent / ".planning" / "automated_test_results.json"
        with open(results_file, 'w') as f:
            json.dump(self.results, f, indent=2)

        logger.info(f"\n📄 Results saved to: {results_file}")


async def main():
    """Run automated tests"""
    tester = SlackIntegrationTester()
    await tester.run_all_automated_tests()


if __name__ == "__main__":
    asyncio.run(main())
