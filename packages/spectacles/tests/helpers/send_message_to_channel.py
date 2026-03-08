#!/usr/bin/env python3
"""
Send Message to Slack Channel via Bot Token

Sends messages directly to Slack channels using the bot token (not webhooks).

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import asyncio
import os
import sys
import httpx
from datetime import datetime


async def send_message(channel_id: str, message: str, message_type: str = "info"):
    """Send message to Slack channel via bot token"""

    bot_token = os.getenv("SLACK_BOT_TOKEN")
    if not bot_token:
        print("❌ Error: SLACK_BOT_TOKEN not set")
        return False

    # Build message blocks
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
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                }
            ]
        }
    ]

    payload = {
        "channel": channel_id,
        "text": f"[TEST] {message_type.upper()}: {message}",
        "blocks": blocks
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://slack.com/api/chat.postMessage",
                headers={
                    "Authorization": f"Bearer {bot_token}",
                    "Content-Type": "application/json"
                },
                json=payload,
                timeout=10.0
            )

            data = response.json()

            if data.get("ok"):
                print(f"✅ Message sent successfully")
                print(f"   Type: {message_type}")
                print(f"   Message: {message}")
                print(f"   Channel: {channel_id}")
                return True
            else:
                print(f"❌ Failed to send message")
                print(f"   Error: {data.get('error')}")
                return False

    except Exception as e:
        print(f"❌ Error: {e}")
        return False


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="Send message to Slack channel")
    parser.add_argument("--channel", required=True, help="Channel ID (e.g., C0AA5FKP35X)")
    parser.add_argument("--message", required=True, help="Message text")
    parser.add_argument("--type", default="test", choices=["info", "warning", "error", "success", "test"])

    args = parser.parse_args()

    success = await send_message(args.channel, args.message, args.type)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
