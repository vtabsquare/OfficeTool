"""
Wipe all employee-scoped historical data from Dataverse tables.

Tables wiped:
  1. crc6f_table13s          (Attendance)
  2. crc6f_table14s          (Leaves)
  3. crc6f_hr_leavemangements (Leave Balance)
  4. crc6f_hr_loginactivitytbs (Login Activity)
  5. crc6f_hr_timesheetlogs   (Timesheet Logs)
  6. crc6f_compensatoryrequests (Comp-Off Requests) — best-effort

Does NOT touch:
  - crc6f_table12s           (Employee Master)
  - Login accounts table
  - Assets table
  - Projects / Tasks tables

Usage:
  python wipe_employee_data.py              # dry-run (shows what would be deleted)
  python wipe_employee_data.py --confirm    # actually deletes
"""

import os
import sys
import time
import requests
from dotenv import load_dotenv
import msal

load_dotenv("id.env")

TENANT_ID = os.getenv("TENANT_ID")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
RESOURCE = os.getenv("RESOURCE")
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPE = [f"{RESOURCE}/.default"]
API = f"{RESOURCE}/api/data/v9.2"


def get_token():
    app = msal.ConfidentialClientApplication(CLIENT_ID, client_credential=CLIENT_SECRET, authority=AUTHORITY)
    result = app.acquire_token_for_client(scopes=SCOPE)
    if "access_token" in result:
        return result["access_token"]
    raise Exception(f"Token error: {result}")


# (entity_set, primary_key_field, description)
TABLES = [
    ("crc6f_table13s", "crc6f_table13id", "Attendance"),
    ("crc6f_table14s", "crc6f_table14id", "Leaves"),
    ("crc6f_hr_leavemangements", "crc6f_hr_leavemangementid", "Leave Balance"),
    ("crc6f_hr_loginactivitytbs", "crc6f_hr_loginactivitytbid", "Login Activity"),
    ("crc6f_hr_timesheetlogs", "crc6f_hr_timesheetlogid", "Timesheet Logs"),
    ("crc6f_compensatoryrequests", "crc6f_compensatoryrequestid", "Comp-Off Requests"),
]


def fetch_all_ids(token, entity_set, pk_field):
    """Fetch all record IDs from a table, paging through @odata.nextLink."""
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    url = f"{API}/{entity_set}?$select={pk_field}&$top=5000"
    all_ids = []
    while url:
        resp = requests.get(url, headers=headers, timeout=60)
        if resp.status_code == 404:
            print(f"    [SKIP] Entity set '{entity_set}' not found (404)")
            return []
        if resp.status_code != 200:
            print(f"    [ERROR] GET {entity_set} → {resp.status_code}: {resp.text[:200]}")
            return []
        data = resp.json()
        for row in data.get("value", []):
            rid = row.get(pk_field)
            if rid:
                all_ids.append(rid)
        url = data.get("@odata.nextLink")
    return all_ids


def delete_records(token, entity_set, pk_field, record_ids, dry_run=True):
    headers = {"Authorization": f"Bearer {token}"}
    deleted = 0
    failed = 0
    for rid in record_ids:
        if dry_run:
            deleted += 1
            continue
        url = f"{API}/{entity_set}({rid})"
        try:
            resp = requests.delete(url, headers=headers, timeout=30)
            if resp.status_code in (200, 204):
                deleted += 1
            else:
                failed += 1
                if failed <= 3:
                    print(f"    [FAIL] DELETE {rid} → {resp.status_code}")
        except Exception as e:
            failed += 1
            if failed <= 3:
                print(f"    [FAIL] DELETE {rid} → {e}")
        # Throttle to avoid Dataverse 429s
        if not dry_run and deleted % 50 == 0:
            time.sleep(1)
    return deleted, failed


def main():
    dry_run = "--confirm" not in sys.argv

    if dry_run:
        print("=" * 60)
        print("  DRY RUN — no data will be deleted")
        print("  Run with --confirm to actually delete")
        print("=" * 60)
    else:
        print("=" * 60)
        print("  ⚠️  LIVE DELETE MODE — data will be permanently removed")
        print("=" * 60)
        ans = input("  Type 'YES' to proceed: ").strip()
        if ans != "YES":
            print("Aborted.")
            return

    token = get_token()
    print(f"\n✅ Dataverse token acquired\n")

    grand_total = 0
    for entity_set, pk_field, desc in TABLES:
        print(f"─── {desc} ({entity_set}) ───")
        ids = fetch_all_ids(token, entity_set, pk_field)
        count = len(ids)
        grand_total += count
        if count == 0:
            print(f"    No records found.\n")
            continue
        print(f"    Found {count} records")
        deleted, failed = delete_records(token, entity_set, pk_field, ids, dry_run=dry_run)
        action = "Would delete" if dry_run else "Deleted"
        print(f"    {action}: {deleted}  |  Failed: {failed}\n")
        # Refresh token between large tables
        if not dry_run and count > 200:
            token = get_token()

    print(f"{'=' * 60}")
    print(f"  Grand total records: {grand_total}")
    if dry_run:
        print(f"  (Dry run — nothing was deleted)")
    else:
        print(f"  ✅ Wipe complete")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
