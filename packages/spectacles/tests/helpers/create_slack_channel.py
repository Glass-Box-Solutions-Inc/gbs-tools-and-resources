#!/usr/bin/env python3
"""
Create Slack Channel via API

Creates a Slack channel using the Slack Bot Token.
This tests the channel creation functionality programmatically.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import asyncio
import os
import sys
import httpx


async def create_channel(channel_name: str, description: str = None):
    """Create a Slack channel via API"""

    bot_token = os.getenv("SLACK_BOT_TOKEN")
    if not bot_token:
        print("❌ Error: SLACK_BOT_TOKEN not set")
        print("   Run: source tests/helpers/setup_test_env.sh")
        return None

    print(f"Creating Slack channel: #{channel_name}")
    if description:
        print(f"Description: {description}")

    try:
        async with httpx.AsyncClient() as client:
            # Create channel
            response = await client.post(
                "https://slack.com/api/conversations.create",
                headers={
                    "Authorization": f"Bearer {bot_token}",
                    "Content-Type": "application/json"
                },
                json={
                    "name": channel_name,
                    "is_private": False
                },
                timeout=10.0
            )

            data = response.json()

            if data.get("ok"):
                channel_id = data["channel"]["id"]
                channel_name_created = data["channel"]["name"]

                print(f"\n✅ Channel created successfully!")
                print(f"   Channel ID: {channel_id}")
                print(f"   Channel Name: #{channel_name_created}")

                # Set description if provided
                if description:
                    await set_channel_description(channel_id, description, bot_token)

                return channel_id

            else:
                error = data.get("error", "unknown")

                if error == "name_taken":
                    print(f"\n⚠️  Channel #{channel_name} already exists")
                    print(f"   This is OK - we can use the existing channel for testing")

                    # Get channel ID
                    channel_id = await find_channel_id(channel_name, bot_token)
                    if channel_id:
                        print(f"   Channel ID: {channel_id}")
                        return channel_id

                else:
                    print(f"\n❌ Failed to create channel")
                    print(f"   Error: {error}")
                    print(f"   Response: {data}")
                    return None

    except Exception as e:
        print(f"\n❌ Error creating channel: {e}")
        return None


async def find_channel_id(channel_name: str, bot_token: str):
    """Find channel ID by name"""

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://slack.com/api/conversations.list",
                headers={
                    "Authorization": f"Bearer {bot_token}"
                },
                params={
                    "types": "public_channel",
                    "exclude_archived": True
                },
                timeout=10.0
            )

            data = response.json()

            if data.get("ok"):
                for channel in data.get("channels", []):
                    if channel["name"] == channel_name:
                        return channel["id"]

            return None

    except Exception as e:
        print(f"Error finding channel: {e}")
        return None


async def set_channel_description(channel_id: str, description: str, bot_token: str):
    """Set channel description (topic)"""

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://slack.com/api/conversations.setTopic",
                headers={
                    "Authorization": f"Bearer {bot_token}",
                    "Content-Type": "application/json"
                },
                json={
                    "channel": channel_id,
                    "topic": description
                },
                timeout=10.0
            )

            data = response.json()

            if data.get("ok"):
                print(f"   Description set: {description}")
            else:
                print(f"   Warning: Could not set description - {data.get('error')}")

    except Exception as e:
        print(f"   Warning: Could not set description - {e}")


async def main():
    """Create test channel"""

    channel_name = "spectacles-integration-testing"
    description = "Integration testing for Spectacles Slack - [TEST] messages only"

    channel_id = await create_channel(channel_name, description)

    if channel_id:
        print(f"\n✅ Test channel ready!")
        print(f"   Channel: #{channel_name}")
        print(f"   ID: {channel_id}")
        print(f"\nNext steps:")
        print(f"   1. Join the channel in Slack")
        print(f"   2. Verify the Spectacles bot is in the channel")
        print(f"   3. Post a test message: 'Test channel ready'")
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
