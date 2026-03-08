"""
Download Kirley case files from MerusCase to Downloads folder
"""
import asyncio
import httpx
import os
import re
from pathlib import Path

# Configuration
TOKEN = "4d924c49dea266f7f1e363d9893983d2eb37ee20"
API_BASE = "https://api.meruscase.com"
DOWNLOADS_FOLDER = Path(os.path.expanduser("~")) / "Downloads" / "Kirley_MerusCase"


async def main():
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Accept": "application/json"
    }

    async with httpx.AsyncClient(headers=headers, timeout=60.0) as client:
        # Step 1: Search for Kirley in case files
        print("Searching for Kirley case...")
        resp = await client.get(f"{API_BASE}/caseFiles/index", params={"limit": 500})

        if resp.status_code != 200:
            print(f"Error fetching cases: {resp.status_code}")
            print(resp.text)
            return

        cases_data = resp.json()
        data = cases_data.get("data", cases_data)

        # Handle both dict and list formats
        if isinstance(data, dict):
            items = list(data.items())
        elif isinstance(data, list):
            items = [(item.get("id", i), item) for i, item in enumerate(data)]
        else:
            print(f"Unexpected data format: {type(data)}")
            return

        # Find Kirley case(s)
        kirley_cases = []
        for case_id, case_info in items:
            # Check various fields for "Kirley"
            name = case_info.get("name", "") or ""
            file_number = case_info.get("file_number", "") or ""

            if "kirley" in name.lower() or "kirley" in file_number.lower():
                kirley_cases.append({
                    "id": case_id,
                    "name": name,
                    "file_number": file_number
                })
                print(f"  Found: {name} (ID: {case_id}, File #: {file_number})")

        if not kirley_cases:
            # Try searching uploads directly for "Kirley" in filename
            print("No case named Kirley found. Searching uploads...")
            resp = await client.get(f"{API_BASE}/uploads/index", params={"limit": 1000})

            if resp.status_code == 200:
                uploads_raw = resp.json()
                uploads_data = uploads_raw.get("data", uploads_raw)

                # Handle both dict and list formats
                if isinstance(uploads_data, dict):
                    upload_items = list(uploads_data.items())
                elif isinstance(uploads_data, list):
                    upload_items = [(item.get("id", i), item) for i, item in enumerate(uploads_data)]
                else:
                    upload_items = []

                for upload_id, upload_info in upload_items:
                    filename = upload_info.get("filename", "") or ""
                    if "kirley" in filename.lower():
                        case_file_id = upload_info.get("case_file_id")
                        print(f"  Found upload: {filename} (ID: {upload_id}, Case: {case_file_id})")
                        # Add the CASE, not just the single file - we want ALL files from this case
                        if case_file_id and not any(c.get("id") == case_file_id for c in kirley_cases):
                            kirley_cases.append({
                                "id": case_file_id,
                                "name": f"Case from Kirley upload",
                            })

        if not kirley_cases:
            print("No Kirley files found. Listing first 20 cases to help identify:")
            for case_id, case_info in items[:20]:
                print(f"  - {case_info.get('name', 'Unknown')} (ID: {case_id})")
            return

        # Create downloads folder
        DOWNLOADS_FOLDER.mkdir(parents=True, exist_ok=True)
        print(f"\nDownload folder: {DOWNLOADS_FOLDER}")

        # Step 2: For each Kirley case, get uploads and download
        for case in kirley_cases:
            case_id = case["id"]

            # If we found a specific upload, download just that
            if "upload_id" in case:
                await download_file(client, case["upload_id"], case["filename"])
                continue

            # Otherwise, get all uploads for the case
            print(f"\nFetching uploads for case: {case['name']} (ID: {case_id})")
            resp = await client.get(
                f"{API_BASE}/uploads/index",
                params={"case_file_id": case_id, "limit": 500}
            )

            if resp.status_code != 200:
                print(f"  Error fetching uploads: {resp.status_code}")
                continue

            uploads_raw = resp.json()
            uploads_data = uploads_raw.get("data", uploads_raw)

            # Handle both dict and list formats
            if isinstance(uploads_data, dict):
                upload_items = list(uploads_data.items())
            elif isinstance(uploads_data, list):
                upload_items = [(item.get("id", i), item) for i, item in enumerate(uploads_data)]
            else:
                upload_items = []

            print(f"  Found {len(upload_items)} uploads")

            for upload_id, upload_info in upload_items:
                filename = upload_info.get("filename", f"file_{upload_id}")
                await download_file(client, upload_id, filename)


async def download_file(client, upload_id, filename):
    """Download a single file from MerusCase"""
    try:
        # Get S3 signed URL
        resp = await client.get(
            f"https://api.meruscase.com/documents/download/{upload_id}",
            follow_redirects=False
        )

        if resp.status_code == 302:
            s3_url = resp.headers.get("location")

            # Download from S3
            async with httpx.AsyncClient(timeout=120.0) as s3_client:
                file_resp = await s3_client.get(s3_url)

                if file_resp.status_code == 200:
                    # Sanitize filename
                    safe_filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
                    file_path = DOWNLOADS_FOLDER / safe_filename

                    # Handle duplicate names
                    counter = 1
                    original_path = file_path
                    while file_path.exists():
                        stem = original_path.stem
                        suffix = original_path.suffix
                        file_path = DOWNLOADS_FOLDER / f"{stem}_{counter}{suffix}"
                        counter += 1

                    file_path.write_bytes(file_resp.content)
                    print(f"  Downloaded: {safe_filename} ({len(file_resp.content)} bytes)")
                else:
                    print(f"  Failed to download from S3: {file_resp.status_code}")
        else:
            print(f"  Download failed for {filename}: HTTP {resp.status_code}")
    except Exception as e:
        print(f"  Error downloading {filename}: {e}")


if __name__ == "__main__":
    asyncio.run(main())
