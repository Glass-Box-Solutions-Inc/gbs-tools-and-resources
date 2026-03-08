#!/usr/bin/env python3
"""
Pattern Extraction Demo

Demonstrates how the PatternExtractor automatically learns from successful tasks.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import asyncio
from core.memory.extractor import PatternExtractor


async def demo_login_extraction():
    """Demonstrate extraction from a login task."""
    print("=" * 60)
    print("Pattern Extraction Demo: Login Flow")
    print("=" * 60)

    # Sample login task data
    task_data = {
        "task_id": "task-login-demo",
        "goal": "login to example.com",
        "start_url": "https://example.com/login",
        "current_state": "COMPLETED",
        "metadata": {
            "final_url": "https://example.com/dashboard"
        }
    }

    # Sample action sequence (what the browser did)
    actions = [
        {
            "id": 1,
            "action_type": "NAVIGATE",
            "target_element": "https://example.com/login",
            "result_status": "SUCCESS"
        },
        {
            "id": 2,
            "action_type": "FILL",
            "target_element": "input#email",
            "action_params": {"field_name": "email", "value": "user@example.com"},
            "result_status": "SUCCESS"
        },
        {
            "id": 3,
            "action_type": "FILL",
            "target_element": "input#password",
            "action_params": {"field_name": "password", "value": "******"},
            "result_status": "SUCCESS"
        },
        {
            "id": 4,
            "action_type": "CLICK",
            "target_element": "button[type='submit']",
            "result_data": {"text": "Sign In"},
            "result_status": "SUCCESS"
        }
    ]

    # Extract pattern
    extractor = PatternExtractor()
    pattern = await extractor.extract_from_task(
        task_id="task-login-demo",
        task_data=task_data,
        actions=actions
    )

    # Display results
    print("\n✓ Pattern Extracted Successfully!")
    print(f"\nPattern Type: {pattern.pattern_type}")
    print(f"Site Domain: {pattern.site_domain}")
    print(f"Goal: {pattern.goal}")
    print(f"Confidence: {pattern.confidence:.2f}")

    print("\nExtracted Selectors:")
    for name, selector in pattern.pattern_data["selectors"].items():
        print(f"  • {name}: {selector}")

    print("\nAction Sequence:")
    for i, step in enumerate(pattern.pattern_data["sequence"], 1):
        action = step["action"]
        target = step["target"]
        print(f"  {i}. {action}: {target}")

    print("\nSuccess Indicators:")
    for key, value in pattern.pattern_data["success_indicators"].items():
        print(f"  • {key}: {value}")

    print("\n" + "=" * 60)
    print("Next Steps:")
    print("  1. Store pattern in Qdrant (Phase 2)")
    print("  2. AIReasoner retrieves pattern for similar tasks (Phase 1)")
    print("  3. Execute pattern directly - 0 VLM calls, 3-5 seconds")
    print("=" * 60)


async def demo_form_extraction():
    """Demonstrate extraction from a form filling task."""
    print("\n" + "=" * 60)
    print("Pattern Extraction Demo: Form Structure")
    print("=" * 60)

    task_data = {
        "task_id": "task-form-demo",
        "goal": "fill contact form",
        "start_url": "https://example.com/contact",
        "current_state": "COMPLETED"
    }

    actions = [
        {
            "id": 1,
            "action_type": "FILL",
            "target_element": "input#name",
            "action_params": {"field_name": "name"},
            "result_status": "SUCCESS"
        },
        {
            "id": 2,
            "action_type": "FILL",
            "target_element": "input#email",
            "action_params": {"field_name": "email"},
            "result_status": "SUCCESS"
        },
        {
            "id": 3,
            "action_type": "FILL",
            "target_element": "textarea#message",
            "action_params": {"field_name": "message"},
            "result_status": "SUCCESS"
        },
        {
            "id": 4,
            "action_type": "CLICK",
            "target_element": "button#submit",
            "result_data": {"text": "Send Message"},
            "result_status": "SUCCESS"
        }
    ]

    extractor = PatternExtractor()
    pattern = await extractor.extract_from_task(
        task_id="task-form-demo",
        task_data=task_data,
        actions=actions
    )

    print(f"\n✓ Classified as: {pattern.pattern_type}")
    print(f"✓ {len(pattern.pattern_data['selectors'])} selectors extracted")
    print(f"✓ {len(pattern.pattern_data['sequence'])} action steps")


async def main():
    """Run all demos."""
    await demo_login_extraction()
    await demo_form_extraction()

    print("\n" + "=" * 60)
    print("Pattern Extraction Engine Demo Complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
