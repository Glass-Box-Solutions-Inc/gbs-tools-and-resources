#!/usr/bin/env python3
"""
Test Task Creator for Spectacles API

Creates test tasks via Spectacles API for integration testing.

Usage:
    python create_test_task.py --goal "Navigate to example.com" --url https://example.com
    python create_test_task.py --goal "Test approval flow" --url https://example.com --require-approval

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import asyncio
import argparse
import sys
import os
from datetime import datetime
import httpx
import json


SPECTACLES_URL = os.getenv(
    "SPECTACLES_URL",
    "https://spectacles-378330630438.us-central1.run.app"
)


async def create_task(
    goal: str,
    start_url: str,
    require_approval: bool = False,
    credentials_key: str = None
):
    """Create a test task via Spectacles API"""

    payload = {
        "goal": goal,
        "start_url": start_url,
        "require_approval": require_approval
    }

    if credentials_key:
        payload["credentials_key"] = credentials_key

    print(f"Creating test task...")
    print(f"  Goal: {goal}")
    print(f"  URL: {start_url}")
    print(f"  Require Approval: {require_approval}")
    if credentials_key:
        print(f"  Credentials: {credentials_key}")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{SPECTACLES_URL}/api/tasks/",
                json=payload,
                timeout=30.0
            )

            if response.status_code in [200, 201]:
                data = response.json()
                task_id = data.get("task_id")
                status = data.get("status")

                print(f"\n✅ Task created successfully")
                print(f"   Task ID: {task_id}")
                print(f"   Status: {status}")
                print(f"\nCheck status:")
                print(f"   curl {SPECTACLES_URL}/api/tasks/{task_id}")
                print(f"\nOr in Slack:")
                print(f"   status {task_id}")

                return task_id
            else:
                print(f"\n❌ Failed to create task")
                print(f"   Status: {response.status_code}")
                print(f"   Response: {response.text}")
                return None

    except Exception as e:
        print(f"\n❌ Error creating task: {e}")
        return None


async def check_task_status(task_id: str):
    """Check task status via API"""

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{SPECTACLES_URL}/api/tasks/{task_id}",
                timeout=10.0
            )

            if response.status_code == 200:
                data = response.json()
                print(f"\n📊 Task Status:")
                print(json.dumps(data, indent=2))
                return data
            else:
                print(f"\n❌ Failed to get task status")
                print(f"   Status: {response.status_code}")
                return None

    except Exception as e:
        print(f"\n❌ Error checking task: {e}")
        return None


async def main():
    parser = argparse.ArgumentParser(
        description="Create test tasks in Spectacles for integration testing"
    )
    parser.add_argument(
        "--goal",
        required=True,
        help="Task goal (what the browser should do)"
    )
    parser.add_argument(
        "--url",
        required=True,
        help="Starting URL for the task"
    )
    parser.add_argument(
        "--require-approval",
        action="store_true",
        help="Require human approval for sensitive actions"
    )
    parser.add_argument(
        "--credentials",
        help="Credentials key for authenticated tasks (e.g., 'github_test_user')"
    )
    parser.add_argument(
        "--check-status",
        metavar="TASK_ID",
        help="Check status of existing task instead of creating new one"
    )

    args = parser.parse_args()

    # Check status mode
    if args.check_status:
        await check_task_status(args.check_status)
        return

    # Create task mode
    task_id = await create_task(
        goal=args.goal,
        start_url=args.url,
        require_approval=args.require_approval,
        credentials_key=args.credentials
    )

    if task_id:
        print(f"\n⏳ Waiting 5 seconds before checking status...")
        await asyncio.sleep(5)
        await check_task_status(task_id)
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
