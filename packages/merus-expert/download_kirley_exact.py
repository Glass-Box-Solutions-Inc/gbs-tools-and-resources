"""
Download ONLY files from KIRLEY, TERRENCE case (case_file_id: 56171897)
Uses exact integer comparison.
"""
import asyncio
import httpx
import os
import re
from pathlib import Path

TOKEN = "4d924c49dea266f7f1e363d9893983d2eb37ee20"
API_BASE = "https://api.meruscase.com"
KIRLEY_CASE_ID = 56171897  # Integer
DOWNLOADS_FOLDER = Path(os.path.expanduser("~")) / "Downloads" / "Kirley_MerusCase"


async def main():
    headers = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}

    async with httpx.AsyncClient(headers=headers, timeout=60.0) as client:
        print(f"Finding files for KIRLEY, TERRENCE (Case ID: {KIRLEY_CASE_ID})")

        # Scan ALL uploads and filter by exact case_file_id match
        kirley_uploads = []
        offset = 0
        batch_size = 500
        total_scanned = 0

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
                items = list(uploads.values())
            elif isinstance(uploads, list):
                items = uploads
            else:
                break

            if not items:
                break

            # Exact integer comparison
            for u in items:
                cid = u.get("case_file_id")
                # Exact match only - must be integer 56171897
                if cid == KIRLEY_CASE_ID:
                    upload_id = u.get("id") or list(u.keys())[0]
                    kirley_uploads.append((upload_id, u))

            total_scanned += len(items)
            if total_scanned % 5000 == 0:
                print(f"  Scanned {total_scanned:,} uploads, found {len(kirley_uploads)} for Kirley...")

            if len(items) < batch_size:
                break
            offset += batch_size

        print(f"\nTotal scanned: {total_scanned:,}")
        print(f"Files for Kirley case (ID {KIRLEY_CASE_ID}): {len(kirley_uploads)}")

        if not kirley_uploads:
            print("No files found!")
            return

        # Create folder and download
        DOWNLOADS_FOLDER.mkdir(parents=True, exist_ok=True)
        print(f"Downloading to: {DOWNLOADS_FOLDER}\n")

        for i, (upload_id, u) in enumerate(kirley_uploads, 1):
            filename = u.get("filename", f"file_{upload_id}")
            print(f"[{i}/{len(kirley_uploads)}] {filename}")
            await download_file(client, upload_id, filename)

        print(f"\nDone! Downloaded {len(kirley_uploads)} files.")


async def download_file(client, upload_id, filename):
    try:
        resp = await client.get(
            f"https://api.meruscase.com/documents/download/{upload_id}",
            follow_redirects=False
        )

        if resp.status_code == 302:
            s3_url = resp.headers.get("location")
            async with httpx.AsyncClient(timeout=120.0) as s3_client:
                file_resp = await s3_client.get(s3_url)
                if file_resp.status_code == 200:
                    safe_filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
                    file_path = DOWNLOADS_FOLDER / safe_filename

                    counter = 1
                    original_path = file_path
                    while file_path.exists():
                        stem = original_path.stem
                        suffix = original_path.suffix
                        file_path = DOWNLOADS_FOLDER / f"{stem}_{counter}{suffix}"
                        counter += 1

                    file_path.write_bytes(file_resp.content)
                    print(f"  -> {len(file_resp.content):,} bytes")
    except Exception as e:
        print(f"  -> Error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
