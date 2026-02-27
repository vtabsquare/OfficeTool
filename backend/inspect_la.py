"""Quick script to inspect Login Activity table primary key field."""
import os, requests
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
url = f"{RESOURCE}/api/data/v9.2/crc6f_hr_loginactivitytbs?$top=1"
resp = requests.get(url, headers=headers, timeout=30)
if resp.status_code == 200:
    rows = resp.json().get("value", [])
    if rows:
        # Print keys that contain 'id' to find primary key
        id_keys = [k for k in rows[0].keys() if 'id' in k.lower()]
        print("ID-related keys:", id_keys)
        # Print the first row's id values
        for k in id_keys:
            print(f"  {k} = {rows[0][k]}")
    else:
        print("Table exists but has 0 rows")
else:
    print(f"ERROR {resp.status_code}: {resp.text[:300]}")
