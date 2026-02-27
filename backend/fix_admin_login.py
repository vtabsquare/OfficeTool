"""Fix specific login account usernames that couldn't be auto-matched."""
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
headers_write = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "If-Match": "*"}

# Manual fix: old_username -> new_username
FIXES = {
    "bala.t@vtab.com": "balamuraleee@gmail.com",
}

dry_run = "--confirm" not in sys.argv

# Find login table
login_table = None
for tbl in ["crc6f_hr_login_detailses", "crc6f_hr_logindetailses", "crc6f_hr_login_details"]:
    r = requests.get(f"{API}/{tbl}?$top=1", headers=headers_read, timeout=30)
    if r.status_code == 200:
        login_table = tbl
        break

if not login_table:
    print("ERROR: Could not find login accounts table")
    sys.exit(1)

resp = requests.get(f"{API}/{login_table}?$select=crc6f_hr_login_detailsid,crc6f_username,crc6f_employeename,crc6f_password,crc6f_accesslevel,crc6f_user_status&$top=500", headers=headers_read, timeout=30)
logins = resp.json().get("value", [])

for login in logins:
    old_uname = (login.get("crc6f_username") or "").strip().lower()
    if old_uname in FIXES:
        new_uname = FIXES[old_uname]
        login_id = login.get("crc6f_hr_login_detailsid")
        print(f"  Found: {old_uname} (id={login_id})")
        print(f"  → Will update username to: {new_uname}")

        if not dry_run:
            url = f"{API}/{login_table}({login_id})"
            payload = {"crc6f_username": new_uname}
            resp2 = requests.patch(url, headers=headers_write, json=payload, timeout=30)
            if resp2.status_code in (200, 204):
                print(f"  ✅ Updated successfully!")
            else:
                print(f"  ❌ Failed: {resp2.status_code} {resp2.text[:300]}")
        else:
            print(f"  (dry run — no changes made)")

if dry_run:
    print("\nRun with --confirm to apply.")
else:
    print("\n✅ Done!")
