"""Verify Employee Master email → employee_id mapping and Login Accounts."""
import os, requests, json
from dotenv import load_dotenv
import msal

load_dotenv("id.env")
RESOURCE = os.getenv("RESOURCE")
TENANT_ID = os.getenv("TENANT_ID")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")

app = msal.ConfidentialClientApplication(CLIENT_ID, client_credential=CLIENT_SECRET,
    authority=f"https://login.microsoftonline.com/{TENANT_ID}")
token = app.acquire_token_for_client(scopes=[f"{RESOURCE}/.default"])["access_token"]
headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

print("=" * 70)
print("  EMPLOYEE MASTER (crc6f_table12s) — email → employee_id mapping")
print("=" * 70)

url = f"{RESOURCE}/api/data/v9.2/crc6f_table12s?$select=crc6f_employeeid,crc6f_email,crc6f_firstname,crc6f_lastname&$top=200&$orderby=crc6f_employeeid asc"
resp = requests.get(url, headers=headers, timeout=30)
emp_rows = resp.json().get("value", []) if resp.status_code == 200 else []

for row in emp_rows:
    eid = row.get("crc6f_employeeid", "???")
    email = row.get("crc6f_email", "???")
    fname = row.get("crc6f_firstname", "")
    lname = row.get("crc6f_lastname", "")
    print(f"  {eid:<10}  {email:<35}  {fname} {lname}")

print(f"\n  Total employees: {len(emp_rows)}")

print("\n" + "=" * 70)
print("  LOGIN ACCOUNTS — username (email) → userId mapping")
print("=" * 70)

# Try common login table names
for tbl in ["crc6f_hr_login_detailses", "crc6f_hr_logindetailses", "crc6f_hr_login_details"]:
    url2 = f"{RESOURCE}/api/data/v9.2/{tbl}?$select=crc6f_username,crc6f_employeename,crc6f_userid,crc6f_accesslevel,crc6f_user_status&$top=200"
    resp2 = requests.get(url2, headers=headers, timeout=30)
    if resp2.status_code == 200:
        login_rows = resp2.json().get("value", [])
        print(f"  (Table: {tbl})")
        for row in login_rows:
            uname = row.get("crc6f_username", "???")
            ename = row.get("crc6f_employeename", "")
            uid = row.get("crc6f_userid", "")
            al = row.get("crc6f_accesslevel", "")
            st = row.get("crc6f_user_status", "")
            print(f"  {uname:<35}  name={ename:<20}  userId={uid:<10}  access={al}  status={st}")
        print(f"\n  Total login accounts: {len(login_rows)}")
        break
else:
    print("  Could not find login accounts table")

print("\n" + "=" * 70)
print("  CROSS-CHECK: Login username vs Employee email")
print("=" * 70)

emp_by_email = {row.get("crc6f_email", "").strip().lower(): row.get("crc6f_employeeid") for row in emp_rows if row.get("crc6f_email")}

try:
    for row in login_rows:
        uname = (row.get("crc6f_username") or "").strip().lower()
        matched_empid = emp_by_email.get(uname, "NO MATCH")
        status_icon = "✅" if matched_empid != "NO MATCH" else "❌"
        print(f"  {status_icon}  {uname:<35}  → Employee: {matched_empid}")
except:
    pass
