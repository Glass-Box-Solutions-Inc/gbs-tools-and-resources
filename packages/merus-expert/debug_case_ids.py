"""Debug case IDs to understand the data structure"""
import asyncio
import httpx

TOKEN = "4d924c49dea266f7f1e363d9893983d2eb37ee20"
API_BASE = "https://api.meruscase.com"
KIRLEY_CASE_ID = 56171897

async def main():
    headers = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}

    async with httpx.AsyncClient(headers=headers, timeout=60.0) as client:
        # Get a sample of uploads
        resp = await client.get(f"{API_BASE}/uploads/index", params={"limit": 20})
        data = resp.json()
        uploads = data.get("data", data)

        print("Sample uploads - checking case_file_id values:")
        print("=" * 80)

        if isinstance(uploads, dict):
            items = list(uploads.items())[:20]
        else:
            items = [(u.get("id"), u) for u in uploads[:20]]

        case_ids_seen = set()
        for upload_id, u in items:
            cid = u.get("case_file_id")
            case_ids_seen.add(cid)
            print(f"Upload {upload_id}: case_file_id={cid} (type: {type(cid).__name__}), filename={u.get('filename', 'N/A')[:50]}")

        print(f"\nUnique case_file_ids in sample: {case_ids_seen}")
        print(f"\nKirley case ID: {KIRLEY_CASE_ID}")
        print(f"Is Kirley case in sample? {KIRLEY_CASE_ID in case_ids_seen or str(KIRLEY_CASE_ID) in case_ids_seen}")

        # Now search specifically for the Kirley file
        print("\n" + "=" * 80)
        print("Searching for 'kirley' in filenames...")
        resp2 = await client.get(f"{API_BASE}/uploads/index", params={"limit": 1000})
        data2 = resp2.json()
        uploads2 = data2.get("data", data2)

        if isinstance(uploads2, dict):
            items2 = list(uploads2.items())
        else:
            items2 = [(u.get("id"), u) for u in uploads2]

        for upload_id, u in items2:
            filename = u.get("filename", "") or ""
            if "kirley" in filename.lower():
                print(f"\nFOUND: Upload {upload_id}")
                print(f"  Filename: {filename}")
                print(f"  case_file_id: {u.get('case_file_id')}")
                print(f"  All keys: {list(u.keys())}")

asyncio.run(main())
