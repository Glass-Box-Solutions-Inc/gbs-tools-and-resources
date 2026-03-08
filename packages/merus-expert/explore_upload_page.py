"""Explore the MerusCase upload page to find Upload Folder link."""
import sys
sys.path.insert(0, r"C:\Users\windo\OneDrive\Desktop\Claude_Code\projects\merus-expert")

import asyncio
import os
from dotenv import load_dotenv
load_dotenv()

from playwright.async_api import async_playwright

MERUSCASE_EMAIL = os.getenv("MERUSCASE_EMAIL")
MERUSCASE_PASSWORD = os.getenv("MERUSCASE_PASSWORD")
BASE_URL = "https://meruscase.com"
CASE_ID = 56171406  # ANDREWS JARED


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await context.new_page()

        # Login
        print("Logging in...")
        await page.goto(f"{BASE_URL}/users/login")
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(3)

        email_input = page.locator("input[type='text']").first
        await email_input.fill(MERUSCASE_EMAIL)

        password_input = page.locator("input[type='password']").first
        await password_input.fill(MERUSCASE_PASSWORD)

        login_btn = page.locator("button:has-text('LOGIN')").first
        await login_btn.click()

        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(3)
        print(f"Logged in: {page.url}")

        # Navigate to case
        case_url = f"{BASE_URL}/cms#/caseFiles/view/{CASE_ID}?t=case_details"
        await page.goto(case_url)
        await asyncio.sleep(3)
        print(f"On case page: {page.url}")

        # Take screenshot
        await page.screenshot(path="logs/explore_1_case_page.png")

        # Click Documents dropdown
        docs_link = page.locator("a:has-text('Documents')").first
        try:
            await docs_link.click(timeout=5000)
            await asyncio.sleep(2)
            await page.screenshot(path="logs/explore_2_docs_dropdown.png")
            print("Clicked Documents dropdown")
        except Exception as e:
            print(f"Could not click Documents: {e}")

        # Click Upload Tool
        upload_tool = page.locator("a:has-text('Upload Tool'), a:has-text('Upload')").first
        try:
            await upload_tool.click(timeout=5000)
            await asyncio.sleep(3)
            await page.screenshot(path="logs/explore_3_upload_tool.png")
            print(f"On upload page: {page.url}")
        except Exception as e:
            print(f"Could not click Upload Tool: {e}")
            # Try direct navigation
            upload_url = f"{BASE_URL}/cms#/uploads/add?case_file_id={CASE_ID}"
            await page.goto(upload_url)
            await asyncio.sleep(3)
            await page.screenshot(path="logs/explore_3_upload_direct.png")
            print(f"Navigated directly: {page.url}")

        # Find all links on the page
        print("\n=== All links on upload page ===")
        links = await page.locator("a").all()
        for link in links:
            try:
                text = await link.text_content()
                href = await link.get_attribute("href")
                if text and ("upload" in text.lower() or "folder" in text.lower()):
                    print(f"Link: '{text.strip()}' -> {href}")
            except:
                pass

        # Find all inputs (file inputs)
        print("\n=== All file inputs ===")
        file_inputs = await page.locator("input[type='file']").all()
        for inp in file_inputs:
            try:
                name = await inp.get_attribute("name")
                webkitdir = await inp.get_attribute("webkitdirectory")
                multiple = await inp.get_attribute("multiple")
                print(f"File input: name={name}, webkitdirectory={webkitdir}, multiple={multiple}")
            except:
                pass

        # Get page HTML content to analyze
        html = await page.content()
        with open("logs/upload_page.html", "w", encoding="utf-8") as f:
            f.write(html)
        print("\nPage HTML saved to logs/upload_page.html")

        # Keep browser open for manual inspection
        print("\nBrowser will stay open for 60 seconds for inspection...")
        await asyncio.sleep(60)

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
