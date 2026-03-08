#!/usr/bin/env python3
"""
Get Browserless Live Session URL

Creates a live, viewable browser session via Browserless and returns the URL.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import asyncio
import httpx

BROWSERLESS_TOKEN = "2TcWyCwbfKt7UWCbec6a2ee3b613b579fb0edb5f7a52b0ace"
BROWSERLESS_ENDPOINT = "https://production-sfo.browserless.io"


async def create_live_session():
    """Create a live Browserless session and get the URL"""

    print("\n🌐 Creating live Browserless session...")

    # Create a session
    async with httpx.AsyncClient() as client:
        # Start a session with the /sessions API
        response = await client.post(
            f"{BROWSERLESS_ENDPOINT}/sessions",
            params={"token": BROWSERLESS_TOKEN},
            json={
                "url": "https://api.slack.com/apps",
                "gotoOptions": {
                    "waitUntil": "networkidle"
                }
            },
            timeout=30.0
        )

        if response.status_code == 200:
            data = response.json()
            session_id = data.get("id")

            if session_id:
                live_url = f"{BROWSERLESS_ENDPOINT}/sessions/{session_id}"

                print(f"\n✅ Live session created!")
                print(f"\n🔗 Open this URL in your browser:")
                print(f"\n   {live_url}")
                print(f"\nThis session will stay active for ~5 minutes of inactivity")
                print(f"You can interact with the browser directly through this URL")

                return live_url
            else:
                print(f"❌ No session ID returned: {data}")
                return None
        else:
            print(f"❌ Failed to create session: {response.status_code}")
            print(f"   Response: {response.text}")
            return None


async def main():
    """Main"""
    await create_live_session()


if __name__ == "__main__":
    asyncio.run(main())
