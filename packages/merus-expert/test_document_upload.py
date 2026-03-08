"""Test document upload to ANDREWS DENNIS case"""
import sys
sys.path.insert(0, r"C:\Users\windo\OneDrive\Desktop\Claude_Code\projects\merus-expert")

import asyncio
import logging
import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

from browser.client import MerusCaseBrowserClient
from browser.element_handler import ElementHandler
from security.config import SecurityConfig

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

SCREENSHOT_DIR = r"C:\Users\windo\OneDrive\Desktop\Claude_Code\projects\merus-expert\knowledge\screenshots"

# Test file to upload - use first file from ANDREWS DENNIS folder
TEST_FOLDER = r"C:\4850 Law\ANDREWS DENNIS_Case3608"


async def test_upload():
    """Test document upload to ANDREWS DENNIS case."""
    config = SecurityConfig.from_env()

    client = MerusCaseBrowserClient(
        api_token=config.browserless_api_token,
        endpoint=config.browserless_endpoint,
        headless=config.use_headless,
        use_local=config.use_local_browser
    )

    try:
        await client.connect()
        element_handler = ElementHandler(client.page)

        # Step 1: Login
        logger.info("Step 1: Logging in...")
        await client.navigate(config.meruscase_login_url)
        await client.page.wait_for_load_state("networkidle", timeout=60000)
        await asyncio.sleep(3)

        email_input = client.page.locator("input[type='text']:first-child").first
        await email_input.wait_for(state="visible", timeout=30000)
        password_input = client.page.locator("input[placeholder='Password'], input[type='password']").first

        await email_input.fill(config.meruscase_email)
        await password_input.fill(config.meruscase_password)

        login_button = client.page.locator("button:has-text('LOGIN')").first
        await login_button.click()
        await client.page.wait_for_load_state("networkidle", timeout=30000)
        await asyncio.sleep(2)

        logger.info(f"Logged in. URL: {client.page.url}")

        # Step 2: Navigate using the same flow as exploration (click Cases, search, click case)
        logger.info("Step 2: Opening Cases dropdown...")
        cases_menu = client.page.locator("a:has-text('Cases')").first
        await cases_menu.click()
        await asyncio.sleep(1)

        # Search for ANDREWS
        search_input = client.page.locator("input[placeholder*='Search'], input[type='search'], .search-input").first
        try:
            if await search_input.is_visible(timeout=3000):
                logger.info("Found search box, searching for ANDREWS...")
                await search_input.fill("ANDREWS")
                await asyncio.sleep(2)
        except:
            pass

        # Click on ANDREWS case
        logger.info("Step 2b: Clicking on ANDREWS case...")
        case_link = client.page.locator("a:has-text('ANDREWS')").first
        await case_link.click()
        await asyncio.sleep(3)

        await client.page.screenshot(path=f"{SCREENSHOT_DIR}/upload_test_01_case_page.png")
        logger.info(f"URL after clicking case: {client.page.url}")

        # Click Documents tab in the nav tabs
        logger.info("Step 2c: Clicking Documents tab...")
        docs_tab = client.page.locator(".nav-tabs a:has-text('Documents'), a[href*='document_search']").first
        try:
            if await docs_tab.is_visible(timeout=3000):
                await docs_tab.click()
                await asyncio.sleep(2)
        except:
            pass

        await client.page.screenshot(path=f"{SCREENSHOT_DIR}/upload_test_01_documents_page.png")
        logger.info(f"URL: {client.page.url}")

        # Step 2d: Try using Documents dropdown in main nav for Add Document
        logger.info("Step 2d: Looking for Add Document in main nav Documents dropdown...")
        docs_dropdown = client.page.locator("nav a:has-text('Documents'), header a:has-text('Documents')").first
        try:
            await docs_dropdown.click()
            await asyncio.sleep(1)
            await client.page.screenshot(path=f"{SCREENSHOT_DIR}/upload_test_01d_docs_dropdown.png")

            # Look for Upload Tool option
            add_options = [
                "a:has-text('Upload Tool')",
                "li:has-text('Upload Tool')",
                "a:has-text('Add Document')",
                "a:has-text('Upload Document')",
            ]
            for sel in add_options:
                try:
                    opt = client.page.locator(sel).first
                    if await opt.is_visible(timeout=2000):
                        logger.info(f"Found: {sel}")
                        await opt.click()
                        await asyncio.sleep(3)  # Wait longer for Upload Tool to load
                        await client.page.wait_for_load_state("networkidle", timeout=10000)
                        await client.page.screenshot(path=f"{SCREENSHOT_DIR}/upload_test_01e_add_dialog.png")

                        # Debug: Log page structure
                        html = await client.page.content()
                        if "drop" in html.lower() or "upload" in html.lower():
                            logger.info("Upload Tool page contains upload-related elements")

                        # Look for input[type=file] on Upload Tool page
                        file_inputs = client.page.locator("input[type='file']")
                        fi_count = await file_inputs.count()
                        logger.info(f"File inputs on Upload Tool page: {fi_count}")
                        for i in range(fi_count):
                            fi = file_inputs.nth(i)
                            accept = await fi.get_attribute("accept")
                            name = await fi.get_attribute("name")
                            logger.info(f"  File input {i}: name={name}, accept={accept}")

                        break
                except:
                    continue
        except Exception as e:
            logger.debug(f"Documents dropdown failed: {e}")

        # Step 3: On Upload Tool page - click folder icon to trigger file chooser
        logger.info("Step 3: Clicking folder icon to browse for files...")

        # Click on the folder/upload area to trigger file selection
        # The Upload Tool has a folder icon in the center that's clickable
        folder_selectors = [
            ".drop-folder",
            ".upload-zone",
            "div:has(> img)",  # Container with folder image
            "img",  # The folder image itself
            "[ng-click*='upload']",  # Angular click handler
            "[onclick*='upload']",
            ".file-drop-zone",
            "label[for*='file']",
        ]

        folder_icon = None
        for sel in folder_selectors:
            try:
                el = client.page.locator(sel).first
                if await el.is_visible(timeout=2000):
                    folder_icon = el
                    logger.info(f"Found clickable element: {sel}")
                    break
            except:
                continue

        if not folder_icon:
            # Try to get all visible images
            images = client.page.locator("img:visible")
            img_count = await images.count()
            logger.info(f"Found {img_count} visible images, looking for folder...")
            for i in range(img_count):
                img = images.nth(i)
                src = await img.get_attribute("src")
                if src and ("folder" in src.lower() or "upload" in src.lower() or "drop" in src.lower()):
                    folder_icon = img
                    logger.info(f"Found folder image: {src}")
                    break
        try:
            if await folder_icon.is_visible(timeout=5000):
                logger.info("Found folder icon, clicking to browse...")

                # Use file chooser handler
                async with client.page.expect_file_chooser(timeout=10000) as fc_info:
                    await folder_icon.click()

                file_chooser = await fc_info.value
                logger.info("File chooser opened!")

                # Get a test file
                test_file = None
                folder = Path(TEST_FOLDER)
                if folder.exists():
                    for f in sorted(folder.iterdir()):
                        if f.is_file():
                            test_file = str(f)
                            break

                if test_file:
                    logger.info(f"Uploading: {test_file}")
                    await file_chooser.set_files(test_file)
                    logger.info("File set via file chooser!")

                    await asyncio.sleep(5)
                    await client.page.screenshot(path=f"{SCREENSHOT_DIR}/upload_test_02_after_upload.png")

                    # Check status
                    status = await client.page.locator(":has-text('KB')").all_text_contents()
                    logger.info(f"Status after upload: {status}")

                    logger.info("=== Upload Test Complete ===")
                    return

        except Exception as e:
            logger.info(f"Folder icon click failed: {e}, trying file input fallback...")

        # Use the Upload Tool's proper file input (accepts any file type)
        logger.info("Step 3b: Using Upload Tool's file input...")

        # The Upload Tool has input name='data[Upload][submitted_files][]' which accepts any file
        file_input_selectors = [
            "input[name='data[Upload][submitted_files][]']",  # Upload Tool's main file input
            "input[name='data[Upload][folder]']",  # Folder upload input
            "input[type='file']:not([accept='image/*'])",  # Any file input without image restriction
            "input[type='file']",
        ]

        file_input = None
        count = 0

        for selector in file_input_selectors:
            try:
                el = client.page.locator(selector)
                cnt = await el.count()
                if cnt > 0:
                    file_input = el
                    count = cnt
                    logger.info(f"Found {cnt} file input(s) with: {selector}")
                    break
            except Exception as e:
                logger.debug(f"Selector {selector} failed: {e}")

        # If no file input found, use JavaScript to find ALL inputs in DOM
        if count == 0:
            logger.info("No file input found, scanning DOM with JavaScript...")

            # Use JavaScript to find all file inputs (including hidden ones)
            file_inputs_info = await client.page.evaluate("""
                () => {
                    const inputs = document.querySelectorAll('input[type="file"]');
                    return Array.from(inputs).map(input => ({
                        id: input.id,
                        name: input.name,
                        className: input.className,
                        hidden: input.hidden || input.style.display === 'none' || input.style.visibility === 'hidden',
                        accept: input.accept,
                        multiple: input.multiple,
                    }));
                }
            """)

            logger.info(f"JavaScript found {len(file_inputs_info)} file inputs in DOM:")
            for i, info in enumerate(file_inputs_info):
                logger.info(f"  Input {i}: {info}")

            if file_inputs_info:
                # Found hidden file inputs - try to use them
                file_input = client.page.locator("input[type='file']").first
                count = len(file_inputs_info)

        # Also try clicking on Documents in the main nav dropdown
        if count == 0:
            logger.info("Trying Documents dropdown in main nav...")
            try:
                docs_dropdown = client.page.locator("a:has-text('Documents')").first
                await docs_dropdown.click()
                await asyncio.sleep(1)

                # Look for Add Document option
                add_doc = client.page.locator("a:has-text('Add Document'), a:has-text('New Document')").first
                if await add_doc.is_visible():
                    logger.info("Found Add Document in dropdown")
                    await add_doc.click()
                    await asyncio.sleep(2)
                    await client.page.screenshot(path=f"{SCREENSHOT_DIR}/upload_test_01d_add_doc_dialog.png")

                    file_input = client.page.locator("input[type='file']")
                    count = await file_input.count()
                    logger.info(f"After Add Document: found {count} file inputs")
            except Exception as e:
                logger.debug(f"Documents dropdown failed: {e}")

        if count > 0:
            # Get attributes
            el = file_input.first
            attrs = {
                "id": await el.get_attribute("id"),
                "name": await el.get_attribute("name"),
                "accept": await el.get_attribute("accept"),
                "multiple": await el.get_attribute("multiple"),
            }
            logger.info(f"File input attributes: {attrs}")

            # Step 4: Find a test file to upload (Upload Tool accepts any document type!)
            logger.info("Step 4: Finding test file from case folder...")
            test_file = None
            folder = Path(TEST_FOLDER)

            if folder.exists():
                for f in sorted(folder.iterdir()):
                    if f.is_file():
                        test_file = str(f)
                        break

            if not test_file:
                logger.error("No test file found!")
                return

            logger.info(f"Test file: {test_file}")
            file_size = os.path.getsize(test_file) / 1024  # KB
            logger.info(f"File size: {file_size:.1f} KB")

            # Step 5: Upload the file
            logger.info("Step 5: Uploading file...")

            try:
                # Use set_input_files to directly set the file
                await file_input.first.set_input_files(test_file)
                logger.info("File set to input!")

                # Wait for file to be queued
                await asyncio.sleep(3)

                await client.page.screenshot(path=f"{SCREENSHOT_DIR}/upload_test_02_file_queued.png")
                logger.info("File queued - screenshot saved")

                # Click Upload button to finalize upload
                logger.info("Clicking Upload button to finalize...")
                upload_btn = client.page.locator("button:has-text('Upload'), .btn:has-text('Upload')").first
                try:
                    if await upload_btn.is_visible(timeout=5000):
                        await upload_btn.click()
                        logger.info("Upload button clicked!")

                        # Wait for upload to complete
                        await asyncio.sleep(10)

                        await client.page.screenshot(path=f"{SCREENSHOT_DIR}/upload_test_03_after_upload.png")
                        logger.info("Screenshot saved after upload")

                        # Check for success message
                        page_text = await client.page.inner_text("body")
                        if "complete" in page_text.lower() or "success" in page_text.lower():
                            logger.info("✓ Upload appears successful!")
                        elif "error" in page_text.lower() or "failed" in page_text.lower():
                            logger.warning("Upload may have failed - check screenshot")
                except Exception as e:
                    logger.warning(f"Upload button click issue: {e}")

                # Look for any errors
                error_text = await client.page.locator(".error, .alert-danger, [class*='error']").all_text_contents()
                if error_text:
                    logger.warning(f"Errors found: {error_text}")

            except Exception as e:
                logger.error(f"Upload failed: {e}")
                await client.page.screenshot(path=f"{SCREENSHOT_DIR}/upload_test_error.png")

        else:
            logger.error("No file input found!")

        # Final screenshot
        await asyncio.sleep(2)
        await client.page.screenshot(path=f"{SCREENSHOT_DIR}/upload_test_03_final.png", full_page=True)

        logger.info("\n=== Upload Test Complete ===")
        logger.info(f"Check screenshots in: {SCREENSHOT_DIR}")

    except Exception as e:
        logger.error(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
        try:
            await client.page.screenshot(path=f"{SCREENSHOT_DIR}/upload_test_error.png")
        except:
            pass
    finally:
        await client.disconnect()


if __name__ == "__main__":
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    asyncio.run(test_upload())
