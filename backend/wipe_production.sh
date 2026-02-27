#!/bin/bash
# Run this on DigitalOcean server to wipe all data

echo "=== PRODUCTION DATA WIPE ==="
echo "⚠️  This will delete ALL data in production"
echo "Type 'WIPE-PROD' to confirm:"

read confirm
if [ "$confirm" != "WIPE-PROD" ]; then
    echo "❌ Wipe cancelled"
    exit
fi

echo "🔥 Wiping production data..."

# Navigate to app directory
cd /var/www/vtab

# Stop the API service
pm2 stop vtab-api

# Create wipe script on server
cat > wipe_now.py << 'EOF'
import requests
import json
import os
import sys
from dotenv import load_dotenv

# Load environment
load_dotenv("id.env")

BASE_URL = os.getenv("RESOURCE")
TENANT_ID = os.getenv("TENANT_ID")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")

import msal

def get_token():
    app = msal.ConfidentialClientApplication(
        client_id=CLIENT_ID,
        client_credential=CLIENT_SECRET,
        authority=f"https://login.microsoftonline.com/{TENANT_ID}"
    )
    result = app.acquire_token_for_client(scopes=[f"{BASE_URL}/.default"])
    return result["access_token"]

def delete_all(entity, field, desc):
    print(f"🗑️ Deleting {desc}...")
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    # Get all
    resp = requests.get(f"{BASE_URL}/api/data/v9.2/{entity}", headers=headers)
    if resp.status_code != 200:
        print(f"❌ Failed to fetch {desc}")
        return
    
    records = resp.json().get("value", [])
    print(f"   Found {len(records)} {desc}")
    
    # Delete all
    for rec in records:
        rec_id = rec.get(field)
        if rec_id:
            del_resp = requests.delete(f"{BASE_URL}/api/data/v9.2/{entity}({rec_id})", headers=headers)
            if del_resp.status_code == 204:
                print(f"   ✅ Deleted {rec_id}")
            else:
                print(f"   ❌ Failed {rec_id}: {del_resp.status_code}")

# Wipe in order
delete_all("crc6f_loginactivities", "crc6f_loginactivityid", "login activities")
delete_all("crc6f_attendances", "crc6f_attendanceid", "attendance records")
delete_all("crc6f_leaves", "crc6f_leaveid", "leave records")
delete_all("crc6f_leavebalances", "crc6f_leavebalanceid", "leave balances")
delete_all("crc6f_compoffs", "crc6f_compoffid", "comp-off requests")
delete_all("crc6f_employees", "crc6f_employeeid", "employee records")

print("\n✅ Wipe complete!")
EOF

# Run the wipe
python3 wipe_now.py

# Clean up
rm wipe_now.py

# Restart API
pm2 restart vtab-api

echo "✅ Production wiped and restarted"
echo "📝 Next: Recreate employees with correct IDs"
