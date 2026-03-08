"""Check case details for case 56171897"""
import asyncio
import httpx

TOKEN = "4d924c49dea266f7f1e363d9893983d2eb37ee20"
API_BASE = "https://api.meruscase.com"

async def main():
    headers = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}

    async with httpx.AsyncClient(headers=headers, timeout=60.0) as client:
        # Get case details
        resp = await client.get(f"{API_BASE}/caseFiles/view/56171897")
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            import json
            data = resp.json()
            print(json.dumps(data, indent=2, default=str)[:2000])
        else:
            print(resp.text[:500])

        # Also check uploads count specifically for this case
        print("\n\nChecking uploads for this case:")
        resp2 = await client.get(f"{API_BASE}/uploads/index", params={"case_file_id": 56171897, "limit": 10})
        if resp2.status_code == 200:
            data2 = resp2.json()
            uploads = data2.get("data", data2)
            if isinstance(uploads, dict):
                print(f"Uploads returned: {len(uploads)}")
            elif isinstance(uploads, list):
                print(f"Uploads returned: {len(uploads)}")
            print("First few filenames:")
            items = list(uploads.items())[:5] if isinstance(uploads, dict) else [(u.get("id"), u) for u in uploads[:5]]
            for uid, u in items:
                print(f"  - {u.get('filename', 'N/A')} (case_file_id: {u.get('case_file_id')})")

asyncio.run(main())
