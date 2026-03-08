"""
Download ONLY Kirley case files from MerusCase (case_file_id: 56171897)
The API doesn't properly filter by case_file_id, so we filter client-side.
"""
import asyncio
import httpx
import os
import re
from pathlib import Path

# Configuration
TOKEN = "4d924c49dea266f7f1e363d9893983d2eb37ee20"
API_BASE = "https://api.meruscase.com"
KIRLEY_CASE_ID = 56171897
DOWNLOADS_FOLDER = Path(os.path.expanduser("~")) / "Downloads" / "Kirley_MerusCase"


async def main():
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Accept": "application/json"
    }

    async with httpx.AsyncClient(headers=headers, timeout=60.0) as client:
        print(f"Downloading files for KIRLEY, TERRENCE (Case ID: {KIRLEY_CASE_ID})")
        print("Fetching all uploads and filtering by case_file_id...")

        # Get all uploads - API doesn't filter properly so we get all and filter
        all_kirley_uploads = []
        offset = 0
        batch_size = 500

        while True:
            resp = await client.get(
                f"{API_BASE}/uploads/index",
                params={"limit": batch_size, "offset": offset}
            )

            if resp.status_code != 200:
                print(f"Error: {resp.status_code}")
                break

            data = resp.json()
            uploads = data.get("data", data)

            if isinstance(uploads, dict):
                items = list(uploads.items())
            elif isinstance(uploads, list):
                items = [(u.get("id"), u) for u in uploads]
            else:
                break

            if not items:
                break

            # Filter for Kirley case only
            for upload_id, upload_info in items:
                case_id = upload_info.get("case_file_id")
                if case_id == KIRLEY_CASE_ID or str(case_id) == str(KIRLEY_CASE_ID):
                    all_kirley_uploads.append((upload_id, upload_info))

            print(f"  Scanned {offset + len(items)} uploads, found {len(all_kirley_uploads)} for Kirley case...")

            if len(items) < batch_size:
                break  # Last batch
            offset += batch_size

        print(f"\nFound {len(all_kirley_uploads)} uploads for Kirley case (ID: {KIRLEY_CASE_ID})")

        if not all_kirley_uploads:
            print("No uploads found for this case!")
            return

        # Create downloads folder
        DOWNLOADS_FOLDER.mkdir(parents=True, exist_ok=True)
        print(f"Download folder: {DOWNLOADS_FOLDER}\n")

        # Download each file
        for i, (upload_id, upload_info) in enumerate(all_kirley_uploads, 1):
            filename = upload_info.get("filename", f"file_{upload_id}")
            print(f"[{i}/{len(all_kirley_uploads)}] Downloading: {filename}")
            await download_file(client, upload_id, filename)

        print(f"\nComplete! Downloaded {len(all_kirley_uploads)} files to {DOWNLOADS_FOLDER}")


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
                    print(f"  -> Saved: {safe_filename} ({len(file_resp.content):,} bytes)")
                else:
                    print(f"  -> Failed S3 download: HTTP {file_resp.status_code}")
        else:
            print(f"  -> Failed: HTTP {resp.status_code}")
    except Exception as e:
        print(f"  -> Error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
