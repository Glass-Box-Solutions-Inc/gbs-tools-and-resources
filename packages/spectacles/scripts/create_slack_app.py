"""
Automated Slack App Creation for Spectacles
Uses Browserless to navigate api.slack.com and create/configure the app.

Required environment variables:
  BROWSERLESS_API_TOKEN - Browserless API token
  GOOGLE_EMAIL - Google account email
  GOOGLE_PASSWORD - Google account password
"""
import asyncio
import os
import re
import json
from playwright.async_api import async_playwright

BROWSERLESS_TOKEN = os.environ.get("BROWSERLESS_API_TOKEN", "")
GOOGLE_EMAIL = os.environ.get("GOOGLE_EMAIL", "")
GOOGLE_PASSWORD = os.environ.get("GOOGLE_PASSWORD", "")
APP_NAME = "Spectacles"
WORKSPACE_NAME = "Adjudica"

SCOPES = [
    # Core messaging
    "chat:write",
    "chat:write.public",
    "chat:write.customize",

    # Channels & Conversations
    "channels:history",
    "channels:read",
    "channels:manage",
    "channels:join",
    "groups:history",
    "groups:read",
    "groups:write",
    "im:history",
    "im:read",
    "im:write",
    "mpim:history",
    "mpim:read",
    "mpim:write",

    # Messages & Reactions
    "reactions:read",
    "reactions:write",

    # Files
    "files:read",
    "files:write",

    # Users
    "users:read",
    "users:read.email",
    "users:write",
    "users.profile:read",
    "users.profile:write",

    # App functionality
    "app_mentions:read",
    "calls:read",
    "calls:write",

    # Workspace
    "team:read",
    "usergroups:read",
    "usergroups:write",

    # Search
    "search:read",

    # Bookmarks
    "bookmarks:read",
    "bookmarks:write",

    # Metadata
    "metadata.message:read",
]

if not BROWSERLESS_TOKEN or not GOOGLE_EMAIL or not GOOGLE_PASSWORD:
    raise ValueError("Missing required environment variables: BROWSERLESS_API_TOKEN, GOOGLE_EMAIL, GOOGLE_PASSWORD")


class SlackAppCreator:
    def __init__(self):
        self.browser = None
        self.context = None
        self.page = None
        self.bot_token = None
        self.app_token = None
        self.app_id = None

    async def connect(self):
        print("Connecting to Browserless...")
        p = await async_playwright().start()
        self.browser = await p.chromium.connect_over_cdp(
            f"wss://production-sfo.browserless.io?token={BROWSERLESS_TOKEN}&stealth=true&humanize=true",
            timeout=60000
        )
        self.context = await self.browser.new_context(
            viewport={"width": 1366, "height": 768},
            locale="en-US"
        )
        self.page = await self.context.new_page()
        print("Connected!")

    async def google_login(self):
        print("\n=== Step 1: Google Login ===")

        await self.page.goto("https://slack.com/get-started#/find", timeout=60000)
        await asyncio.sleep(3)

        await self.page.click("text=Google")
        await asyncio.sleep(5)

        print("Entering Google credentials...")
        await self.page.fill("input[type=email]", GOOGLE_EMAIL)
        await self.page.click("#identifierNext")
        await asyncio.sleep(5)

        await self.page.fill("input[type=password]", GOOGLE_PASSWORD)
        await self.page.click("#passwordNext")
        await asyncio.sleep(5)

        body = await self.page.query_selector("body")
        text = await body.inner_text() if body else ""

        match = re.search(r"tap (\d+)", text)
        if match:
            code = match.group(1)
            print(f"\n*** 2FA Required: Tap {code} on your phone! ***")
            print("Waiting for approval (90 seconds)...")

            for i in range(45):
                await asyncio.sleep(2)
                url = self.page.url
                if "challenge" not in url and "signin" not in url.split("/")[-1]:
                    print("2FA approved!")
                    break
                if i % 10 == 0:
                    print(f"  waiting... {i*2}s")

        await asyncio.sleep(5)
        print(f"Current URL: {self.page.url}")
        return "slack" in self.page.url.lower()

    async def navigate_to_api(self):
        print("\n=== Step 2: Navigate to Slack API ===")
        await self.page.goto("https://api.slack.com/apps", timeout=60000)
        await asyncio.sleep(5)

        body = await self.page.query_selector("body")
        text = await body.inner_text() if body else ""

        if "sign in" in text.lower() and "Your Apps" in text:
            print("Need to sign in to API portal...")
            signin = await self.page.query_selector("a:has-text('sign in')")
            if signin:
                await signin.click()
                await asyncio.sleep(5)
                return await self.google_login()

        return True

    async def create_app(self):
        print("\n=== Step 3: Create Slack App ===")

        await self.page.goto("https://api.slack.com/apps", timeout=60000)
        await asyncio.sleep(3)

        body = await self.page.query_selector("body")
        text = await body.inner_text() if body else ""

        if APP_NAME in text:
            print(f"App '{APP_NAME}' may already exist, looking for it...")
            app_link = await self.page.query_selector(f"a:has-text('{APP_NAME}')")
            if app_link:
                href = await app_link.get_attribute("href")
                if href and "/apps/" in href:
                    self.app_id = href.split("/apps/")[1].split("/")[0]
                    print(f"Found existing app: {self.app_id}")
                    await app_link.click()
                    await asyncio.sleep(3)
                    return True

        print("Creating new app...")
        create_btn = await self.page.query_selector("text=Create New App")
        if create_btn:
            await create_btn.click()
            await asyncio.sleep(2)

            scratch = await self.page.query_selector("text=From scratch")
            if scratch:
                await scratch.click()
                await asyncio.sleep(2)

            name_input = await self.page.query_selector("input[placeholder*='App Name']")
            if not name_input:
                name_input = await self.page.query_selector("input[name='name']")
            if name_input:
                await name_input.fill(APP_NAME)

            workspace_select = await self.page.query_selector("select")
            if workspace_select:
                options = await self.page.query_selector_all("select option")
                for opt in options:
                    opt_text = await opt.text_content()
                    if WORKSPACE_NAME.lower() in opt_text.lower():
                        value = await opt.get_attribute("value")
                        await workspace_select.select_option(value)
                        break

            await self.page.screenshot(path="/tmp/create_app_form.png")

            submit = await self.page.query_selector("button:has-text('Create App')")
            if submit:
                await submit.click()
                await asyncio.sleep(5)

                url = self.page.url
                if "/apps/" in url:
                    self.app_id = url.split("/apps/")[1].split("/")[0]
                    print(f"Created app: {self.app_id}")
                    return True

        return False

    async def configure_oauth(self):
        print("\n=== Step 4: Configure OAuth Scopes ===")

        if not self.app_id:
            print("ERROR: No app ID")
            return False

        await self.page.goto(f"https://api.slack.com/apps/{self.app_id}/oauth", timeout=60000)
        await asyncio.sleep(3)

        for scope in SCOPES:
            print(f"Adding scope: {scope}")
            add_scope = await self.page.query_selector("text=Add an OAuth Scope")
            if add_scope:
                await add_scope.click()
                await asyncio.sleep(1)

                scope_input = await self.page.query_selector("input[placeholder*='Search']")
                if scope_input:
                    await scope_input.fill(scope)
                    await asyncio.sleep(1)

                    scope_option = await self.page.query_selector(f"text={scope}")
                    if scope_option:
                        await scope_option.click()
                        await asyncio.sleep(1)

        print("Installing to workspace...")
        install_btn = await self.page.query_selector("text=Install to Workspace")
        if install_btn:
            await install_btn.click()
            await asyncio.sleep(3)

            allow_btn = await self.page.query_selector("text=Allow")
            if allow_btn:
                await allow_btn.click()
                await asyncio.sleep(5)

        await self.page.goto(f"https://api.slack.com/apps/{self.app_id}/oauth", timeout=60000)
        await asyncio.sleep(3)

        content = await self.page.content()
        match = re.search(r"xoxb-[a-zA-Z0-9-]+", content)
        if match:
            self.bot_token = match.group()
            print(f"Bot Token: {self.bot_token[:20]}...")
            return True

        print("Could not find bot token on page")
        await self.page.screenshot(path="/tmp/oauth_page.png")
        return False

    async def enable_socket_mode(self):
        print("\n=== Step 5: Enable Socket Mode ===")

        await self.page.goto(f"https://api.slack.com/apps/{self.app_id}/socket-mode", timeout=60000)
        await asyncio.sleep(3)

        toggle = await self.page.query_selector("input[type='checkbox']")
        if toggle:
            is_checked = await toggle.is_checked()
            if not is_checked:
                await toggle.click()
                await asyncio.sleep(2)

        generate_btn = await self.page.query_selector("text=Generate Token")
        if not generate_btn:
            generate_btn = await self.page.query_selector("text=Generate")

        if generate_btn:
            await generate_btn.click()
            await asyncio.sleep(2)

            name_input = await self.page.query_selector("input[placeholder*='name']")
            if name_input:
                await name_input.fill("spectacles-socket")

            scope_checkbox = await self.page.query_selector("text=connections:write")
            if scope_checkbox:
                await scope_checkbox.click()

            gen_btn = await self.page.query_selector("button:has-text('Generate')")
            if gen_btn:
                await gen_btn.click()
                await asyncio.sleep(3)

        content = await self.page.content()
        match = re.search(r"xapp-[a-zA-Z0-9-]+", content)
        if match:
            self.app_token = match.group()
            print(f"App Token: {self.app_token[:20]}...")
            return True

        await self.page.screenshot(path="/tmp/socket_mode.png")
        return False

    async def enable_interactivity(self):
        print("\n=== Step 6: Enable Interactivity ===")

        await self.page.goto(f"https://api.slack.com/apps/{self.app_id}/interactive-messages", timeout=60000)
        await asyncio.sleep(3)

        toggle = await self.page.query_selector("input[type='checkbox']")
        if toggle:
            is_checked = await toggle.is_checked()
            if not is_checked:
                await toggle.click()
                await asyncio.sleep(2)

        save_btn = await self.page.query_selector("text=Save Changes")
        if save_btn:
            await save_btn.click()
            await asyncio.sleep(2)

        print("Interactivity enabled")
        return True

    async def run(self):
        try:
            await self.connect()

            if not await self.google_login():
                print("Failed to login")
                return None

            if not await self.navigate_to_api():
                print("Failed to navigate to API")
                return None

            if not await self.create_app():
                print("Failed to create app")
                return None

            if not await self.configure_oauth():
                print("Failed to configure OAuth (will try to continue)")

            if not await self.enable_socket_mode():
                print("Failed to enable Socket Mode (will try to continue)")

            await self.enable_interactivity()

            print("\n" + "="*50)
            print("RESULTS")
            print("="*50)
            print(f"App ID: {self.app_id}")
            print(f"Bot Token: {self.bot_token}")
            print(f"App Token: {self.app_token}")

            return {
                "app_id": self.app_id,
                "bot_token": self.bot_token,
                "app_token": self.app_token
            }

        finally:
            if self.browser:
                await self.browser.close()


async def main():
    creator = SlackAppCreator()
    result = await creator.run()

    if result:
        with open("/tmp/slack_tokens.json", "w") as f:
            json.dump(result, f, indent=2)
        print(f"\nTokens saved to /tmp/slack_tokens.json")

    return result


if __name__ == "__main__":
    asyncio.run(main())
