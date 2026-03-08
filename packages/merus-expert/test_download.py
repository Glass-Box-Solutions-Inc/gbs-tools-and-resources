"""
Test document download using upload IDs from uploads/index.
"""

import asyncio
import logging
import json
from pathlib import Path
import httpx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_BASE = "https://api.meruscase.com"
TOKEN = Path(".meruscase_token").read_text().strip()


async def test_download():
    """Test downloading a document."""

    logger.info(f"\n{'='*70}")
    logger.info("TESTING DOCUMENT DOWNLOAD")
    logger.info(f"{'='*70}\n")

    async with httpx.AsyncClient(
        headers={"Authorization": f"Bearer {TOKEN}", "Accept": "*/*"},
        timeout=60.0,
        follow_redirects=True
    ) as client:

        # 1. Get uploads list
        logger.info("1. Getting upload list...")
        resp = await client.get(f"{API_BASE}/uploads/index")
        data = resp.json()

        uploads_data = data.get("data", {})
        logger.info(f"   Found {len(uploads_data)} uploads")

        # Get first upload ID
        if uploads_data:
            upload_id = list(uploads_data.keys())[0]
            upload_info = uploads_data[upload_id]
            filename = upload_info.get("filename", "unknown")
            case_id = upload_info.get("case_file_id")

            logger.info(f"\n2. Testing download for upload {upload_id}")
            logger.info(f"   Filename: {filename}")
            logger.info(f"   Case ID: {case_id}")

            # Try various download endpoints
            download_urls = [
                f"{API_BASE}/uploads/download/{upload_id}",
                f"{API_BASE}/uploads/{upload_id}",
                f"{API_BASE}/uploads/view/{upload_id}",
                f"{API_BASE}/documents/download/{upload_id}",
                f"{API_BASE}/files/{upload_id}",
                f"{API_BASE}/uploads/get/{upload_id}",
                # With case_file_id
                f"{API_BASE}/uploads/download/{upload_id}?case_file_id={case_id}",
            ]

            for url in download_urls:
                try:
                    logger.info(f"\n   Trying: {url.replace(API_BASE, '')}")

                    # Use a fresh client for each attempt to handle redirects properly
                    resp = await client.get(url)

                    status = resp.status_code
                    content_type = resp.headers.get("content-type", "unknown")
                    content_length = len(resp.content)
                    content_disp = resp.headers.get("content-disposition", "")

                    logger.info(f"   Status: {status}")
                    logger.info(f"   Content-Type: {content_type}")
                    logger.info(f"   Content-Length: {content_length}")

                    if content_disp:
                        logger.info(f"   Content-Disposition: {content_disp}")

                    if status == 200:
                        if "application/pdf" in content_type or "octet-stream" in content_type:
                            logger.info(f"   >>> SUCCESS! Got file data ({content_length} bytes)")

                            # Save it
                            out_path = Path(f"downloads/test_{upload_id}.pdf")
                            out_path.parent.mkdir(exist_ok=True)
                            out_path.write_bytes(resp.content)
                            logger.info(f"   >>> Saved to: {out_path}")
                            break

                        elif "application/json" in content_type:
                            json_data = resp.json()
                            logger.info(f"   JSON response: {json.dumps(json_data, indent=2)[:300]}")

                            # Check if JSON contains download URL
                            if isinstance(json_data, dict):
                                for key in ["url", "download_url", "file_url", "link", "path"]:
                                    if key in json_data:
                                        logger.info(f"   >>> Found {key}: {json_data[key]}")

                except Exception as e:
                    logger.info(f"   Error: {e}")

            # 3. Check if there's a signed URL pattern
            logger.info("\n3. Checking for signed URL or redirect pattern...")

            # Try without following redirects
            async with httpx.AsyncClient(
                headers={"Authorization": f"Bearer {TOKEN}"},
                timeout=30.0,
                follow_redirects=False
            ) as no_redirect_client:
                resp = await no_redirect_client.get(f"{API_BASE}/uploads/download/{upload_id}")
                logger.info(f"   Status (no redirect): {resp.status_code}")

                if resp.status_code in [301, 302, 303, 307, 308]:
                    location = resp.headers.get("location", "")
                    logger.info(f"   >>> Redirect to: {location[:100]}...")

                    if location:
                        # Try following the redirect
                        logger.info("   Fetching redirect URL...")
                        file_resp = await client.get(location)
                        logger.info(f"   Final status: {file_resp.status_code}")
                        logger.info(f"   Content-Type: {file_resp.headers.get('content-type')}")
                        logger.info(f"   Size: {len(file_resp.content)} bytes")

                        if file_resp.status_code == 200 and len(file_resp.content) > 100:
                            out_path = Path(f"downloads/test_{upload_id}.pdf")
                            out_path.parent.mkdir(exist_ok=True)
                            out_path.write_bytes(file_resp.content)
                            logger.info(f"   >>> Saved to: {out_path}")

        logger.info(f"\n{'='*70}")
        logger.info("DOWNLOAD TEST COMPLETE")
        logger.info(f"{'='*70}")


if __name__ == "__main__":
    asyncio.run(test_download())
