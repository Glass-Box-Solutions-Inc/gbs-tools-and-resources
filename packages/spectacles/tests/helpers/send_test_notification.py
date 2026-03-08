#!/usr/bin/env python3
"""
Test Notification Sender for Spectacles Slack Integration

Sends test notifications via webhooks to verify delivery and formatting.

Usage:
    python send_test_notification.py --type info --message "Test message"
    python send_test_notification.py --type warning --message "Warning!" --context "Additional info"
    python send_test_notification.py --webhook alex --message "Direct message to Alex"

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import asyncio
import argparse
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from hitl.webhook_client import WebhookClient
import httpx


WEBHOOK_URLS = {
    "test": None,  # Will be loaded from environment or GCP
    "main": None,
    "alex": None,
    "brian": None,
}


def build_blocks(message_type: str, message: str, context: str = None):
    """Build Block Kit blocks based on message type"""

    emoji_map = {
        "info": "ℹ️",
        "warning": "⚠️",
        "error": "🚨",
        "success": "✅",
        "test": "🧪"
    }

    emoji = emoji_map.get(message_type, "📢")

    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"{emoji} *{message_type.upper()}*\n\n{message}"
            }
        }
    ]

    if context:
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": context
                }
            ]
        })

    # Add timestamp
    blocks.append({
        "type": "context",
        "elements": [
            {
                "type": "mrkdwn",
                "text": f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            }
        ]
    })

    return blocks


async def send_notification(
    webhook_url: str,
    message_type: str,
    message: str,
    context: str = None
):
    """Send notification to Slack webhook"""

    blocks = build_blocks(message_type, message, context)

    payload = {
        "text": f"[TEST] {message_type.upper()}: {message}",
        "blocks": blocks
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                webhook_url,
                json=payload,
                timeout=10.0
            )

            if response.status_code == 200:
                print(f"✅ Notification sent successfully")
                print(f"   Type: {message_type}")
                print(f"   Message: {message}")
                if context:
                    print(f"   Context: {context}")
                return True
            else:
                print(f"❌ Failed to send notification")
                print(f"   Status: {response.status_code}")
                print(f"   Response: {response.text}")
                return False

    except Exception as e:
        print(f"❌ Error sending notification: {e}")
        return False


async def load_webhook_from_gcp(webhook_name: str) -> str:
    """Load webhook URL from GCP Secret Manager"""
    import subprocess

    secret_map = {
        "alex": "slack-webhook-alex",
        "brian": "slack-webhook-brian",
        "main": "slack-webhook-main",
        "social": "slack-webhook-social",
    }

    secret_name = secret_map.get(webhook_name)
    if not secret_name:
        raise ValueError(f"Unknown webhook name: {webhook_name}")

    try:
        result = subprocess.run(
            [
                "gcloud", "secrets", "versions", "access", "latest",
                "--secret", secret_name,
                "--project", "glassbox-spectacles"
            ],
            capture_output=True,
            text=True,
            check=True
        )

        webhook_url = result.stdout.strip()
        if webhook_url:
            print(f"✅ Loaded webhook '{webhook_name}' from GCP Secret Manager")
            return webhook_url
        else:
            raise ValueError(f"Empty webhook URL for {webhook_name}")

    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to load webhook from GCP: {e}")
        print(f"   stderr: {e.stderr}")
        raise


async def main():
    parser = argparse.ArgumentParser(
        description="Send test notifications to Slack via webhooks"
    )
    parser.add_argument(
        "--type",
        choices=["info", "warning", "error", "success", "test"],
        default="test",
        help="Notification type"
    )
    parser.add_argument(
        "--message",
        required=True,
        help="Notification message"
    )
    parser.add_argument(
        "--context",
        help="Additional context to include"
    )
    parser.add_argument(
        "--webhook",
        default="main",
        help="Webhook to use (main, alex, brian, social, or URL)"
    )
    parser.add_argument(
        "--url",
        help="Direct webhook URL (overrides --webhook)"
    )

    args = parser.parse_args()

    # Determine webhook URL
    if args.url:
        webhook_url = args.url
        print(f"Using direct URL: {webhook_url[:50]}...")
    else:
        print(f"Loading webhook '{args.webhook}' from GCP...")
        try:
            webhook_url = await load_webhook_from_gcp(args.webhook)
        except Exception as e:
            print(f"\n❌ Failed to load webhook: {e}")
            print("\nAlternative: Provide URL directly with --url flag")
            sys.exit(1)

    # Send notification
    print(f"\nSending {args.type} notification...")
    success = await send_notification(
        webhook_url,
        args.type,
        args.message,
        args.context
    )

    if success:
        print("\n✅ Test completed successfully")
        print("Check Slack for the notification")
        sys.exit(0)
    else:
        print("\n❌ Test failed")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
