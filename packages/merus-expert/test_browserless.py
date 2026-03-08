"""Test browser connection (local or Browserless)"""
import sys
sys.path.insert(0, r"C:\Users\windo\OneDrive\Desktop\Claude_Code\projects\merus-expert")

import asyncio
from dotenv import load_dotenv
load_dotenv()

from browser.client import MerusCaseBrowserClient
from security.config import SecurityConfig

async def test_connection():
    config = SecurityConfig.from_env()
    print(f"USE_LOCAL_BROWSER: {config.use_local_browser}")
    print(f"USE_HEADLESS: {config.use_headless}")
    print(f"Browserless endpoint: {config.browserless_endpoint}")
    print(f"API token exists: {bool(config.browserless_api_token)}")

    client = MerusCaseBrowserClient(
        api_token=config.browserless_api_token,
        endpoint=config.browserless_endpoint,
        headless=config.use_headless,
        use_local=config.use_local_browser
    )

    try:
        print("\nConnecting to Browserless...")
        await client.connect()
        print("SUCCESS: Connected to Browserless!")

        # Quick navigation test
        print("\nNavigating to MerusCase login...")
        await client.navigate("https://meruscase.com/users/login")
        print("SUCCESS: Navigation complete!")

        # Take screenshot
        await client.page.screenshot(path="test_browserless_screenshot.png")
        print("Screenshot saved: test_browserless_screenshot.png")

    except Exception as e:
        print(f"ERROR: {e}")
        return False
    finally:
        await client.disconnect()
        print("\nDisconnected.")

    return True

if __name__ == "__main__":
    result = asyncio.run(test_connection())
    sys.exit(0 if result else 1)
