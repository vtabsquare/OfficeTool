"""
Fix login account usernames to match Employee Master emails.

For each login account that doesn't match an employee by email,
try to match by name and update the username to the employee's email.

Usage:
  python3 fix_login_usernames.py              # dry-run
  python3 fix_login_usernames.py --confirm    # actually updates
"""

import os, sys, requests
from dotenv import load_dotenv
import msal

load_dotenv("id.env")
RESOURCE = os.getenv("RESOURCE")
TENANT_ID = os.getenv("TENANT_ID")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
API = f"{RESOURCE}/api/data/v9.2"

app = msal.ConfidentialClientApplication(CLIENT_ID, client_credential=CLIENT_SECRET,
    authority=f"https://login.microsoftonline.com/{TENANT_ID}")
token = app.acquire_token_for_client(scopes=[f"{RESOURCE}/.default"])["access_token"]
headers_read = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
headers_write = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json",
    "If-Match": "*"
}

dry_run = "--confirm" not in sys.argv

# 1. Fetch Employee Master
resp = requests.get(f"{API}/crc6f_table12s?$select=crc6f_employeeid,crc6f_email,crc6f_firstname,crc6f_lastname&$top=500", headers=headers_read, timeout=30)
employees = resp.json().get("value", [])
emp_by_email = {}
emp_by_name = {}
for e in employees:
    email = (e.get("crc6f_email") or "").strip().lower()
    eid = e.get("crc6f_employeeid", "")
    fname = (e.get("crc6f_firstname") or "").strip()
    lname = (e.get("crc6f_lastname") or "").strip()
    fullname = f"{fname} {lname}".strip().lower()
    if email:
        emp_by_email[email] = e
    if fullname:
        emp_by_name[fullname] = e

# 2. Fetch Login Accounts
login_table = None
for tbl in ["crc6f_hr_login_detailses", "crc6f_hr_logindetailses", "crc6f_hr_login_details"]:
    r = requests.get(f"{API}/{tbl}?$top=1", headers=headers_read, timeout=30)
    if r.status_code == 200:
        login_table = tbl
        break

if not login_table:
    print("ERROR: Could not find login accounts table")
    sys.exit(1)

resp2 = requests.get(f"{API}/{login_table}?$select=crc6f_hr_login_detailsid,crc6f_username,crc6f_employeename,crc6f_accesslevel,crc6f_user_status&$top=500", headers=headers_read, timeout=30)
logins = resp2.json().get("value", [])

print("=" * 80)
if dry_run:
    print("  DRY RUN — showing what would be updated. Run with --confirm to apply.")
else:
    print("  ⚠️  LIVE MODE — will update login usernames")
print("=" * 80)

updates = []
already_ok = []
no_match = []

for login in logins:
    login_id = login.get("crc6f_hr_login_detailsid")
    username = (login.get("crc6f_username") or "").strip().lower()
    emp_name = (login.get("crc6f_employeename") or "").strip()
    access = login.get("crc6f_accesslevel", "")
    status = login.get("crc6f_user_status", "")

    # Check if already matched
    if username in emp_by_email:
        already_ok.append((username, emp_by_email[username].get("crc6f_employeeid")))
        continue

    # Try match by name
    emp_name_lower = emp_name.lower().strip()
    matched_emp = emp_by_name.get(emp_name_lower)

    # Try partial match (first name)
    if not matched_emp:
        first_word = emp_name_lower.split()[0] if emp_name_lower else ""
        if first_word and len(first_word) > 2:
            candidates = [(k, v) for k, v in emp_by_name.items() if k.startswith(first_word)]
            if len(candidates) == 1:
                matched_emp = candidates[0][1]

    if matched_emp:
        new_email = (matched_emp.get("crc6f_email") or "").strip()
        eid = matched_emp.get("crc6f_employeeid", "")
        if new_email and new_email.lower() != username:
            updates.append({
                "login_id": login_id,
                "old_username": username,
                "new_username": new_email,
                "emp_id": eid,
                "emp_name": emp_name,
                "access": access,
            })
        else:
            already_ok.append((username, eid))
    else:
        no_match.append((username, emp_name, access, status))

# Report
print(f"\n  ✅ Already correctly matched: {len(already_ok)}")
for u, eid in already_ok:
    print(f"      {u:<35} → {eid}")

print(f"\n  🔄 To update ({len(updates)}):")
for u in updates:
    print(f"      {u['old_username']:<35} → {u['new_username']:<35}  ({u['emp_id']}, {u['emp_name']})")

print(f"\n  ❌ No employee match ({len(no_match)}):")
for u, name, access, status in no_match:
    print(f"      {u:<35}  name={name:<20}  access={access}  status={status}")

# Apply updates
if updates and not dry_run:
    print(f"\n  Applying {len(updates)} updates...")
    for u in updates:
        url = f"{API}/{login_table}({u['login_id']})"
        payload = {"crc6f_username": u["new_username"]}
        try:
            resp = requests.patch(url, headers=headers_write, json=payload, timeout=30)
            if resp.status_code in (200, 204):
                print(f"    ✅ {u['old_username']} → {u['new_username']}")
            else:
                print(f"    ❌ {u['old_username']} → {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            print(f"    ❌ {u['old_username']} → Error: {e}")

print(f"\n{'=' * 80}")
if dry_run:
    print("  Dry run complete. Run with --confirm to apply changes.")
else:
    print("  ✅ Done!")
print(f"{'=' * 80}")
