#!/usr/bin/env python3
"""
Complete data wipe to fix employee ID mismatches.
Deletes all attendance, login activity, and employee records.
"""

import requests
import json
import os

# Config
BASE_URL = os.getenv("BASE_URL", "https://org5b2f0b0a.crm4.dynamics.com")
API_BASE = os.getenv("API_BASE", "http://localhost:5000")

def delete_all_records(entity_name, primary_field, description):
    """Delete all records from a Dataverse entity"""
    print(f"🗑️  Deleting all {description}...")
    
    # Get all records
    url = f"{BASE_URL}/api/data/v9.2/{entity_name}"
    headers = {"Authorization": f"Bearer {get_access_token()}"}
    
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        print(f"   ❌ Failed to fetch {description}: {resp.status_code}")
        return False
    
    records = resp.json().get("value", [])
    print(f"   Found {len(records)} {description} to delete")
    
    deleted = 0
    for rec in records:
        rec_id = rec.get(primary_field)
        if rec_id:
            del_url = f"{BASE_URL}/api/data/v9.2/{entity_name}({rec_id})"
            del_resp = requests.delete(del_url, headers=headers)
            if del_resp.status_code == 204:
                deleted += 1
            else:
                print(f"   ❌ Failed to delete {rec_id}: {del_resp.status_code}")
    
    print(f"   ✅ Deleted {deleted}/{len(records)} {description}")
    return True

def clear_server_memory():
    """Clear server-side sessions and caches"""
    print("🧹 Clearing server memory...")
    
    # Clear active sessions
    try:
        resp = requests.post(f"{API_BASE}/api/admin/clear-sessions")
        if resp.status_code == 200:
            print("   ✅ Cleared active_sessions")
    except:
        print("   ⚠️  Could not clear sessions (server not running?)")

def get_access_token():
    """Get Dataverse access token - replace with your actual token logic"""
    # This is a placeholder - replace with your actual token retrieval
    token = os.getenv("DATAVERSE_TOKEN")
    if not token:
        print("❌ DATAVERSE_TOKEN environment variable not set")
        print("   Set it: export DATAVERSE_TOKEN='your_token_here'")
        exit(1)
    return token

if __name__ == "__main__":
    print("=== COMPLETE DATA WIPE ===")
    print("⚠️  This will delete ALL data. Type 'WIPE' to confirm:")
    
    confirm = input().strip()
    if confirm != "WIPE":
        print("❌ Wipe cancelled")
        exit()
    
    print("\n🔥 Starting complete wipe...")
    
    # Delete in order to avoid foreign key issues
    delete_all_records("crc6f_loginactivities", "crc6f_loginactivityid", "login activities")
    delete_all_records("crc6f_attendances", "crc6f_attendanceid", "attendance records")
    delete_all_records("crc6f_leaves", "crc6f_leaveid", "leave records")
    delete_all_records("crc6f_leavebalances", "crc6f_leavebalanceid", "leave balances")
    delete_all_records("crc6f_compoffs", "crc6f_compoffid", "comp-off requests")
    delete_all_records("crc6f_employees", "crc6f_employeeid", "employee records")
    
    clear_server_memory()
    
    print("\n✅ Complete wipe finished!")
    print("📝 Next steps:")
    print("   1. Restart server: pm2 restart vtab-api")
    print("   2. Recreate employees with correct IDs")
    print("   3. Ask all users to re-login")
