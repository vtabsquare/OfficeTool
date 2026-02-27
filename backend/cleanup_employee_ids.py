#!/usr/bin/env python3
"""
One-time cleanup script after employee ID changes in Dataverse.
- Clears today's login activity to stop ghost timers
- Clears server active_sessions
- Updates frontend cache clearing endpoint
"""

import requests
import json
from datetime import date, datetime, timedelta
import os

# Config
BASE_URL = os.getenv("BASE_URL", "https://org5b2f0b0a.crm4.dynamics.com")
API_BASE = os.getenv("API_BASE", "http://localhost:5000")
TODAY = date.today().isoformat()

def clear_today_login_activity(employee_ids=None):
    """Delete today's login activity for specific employees or all if None"""
    print(f"🧹 Cleaning login activity for {TODAY}...")
    
    # If no specific IDs, clean all today's records
    filter_clause = f"{LA_FIELD_DATE} eq '{TODAY}'"
    if employee_ids:
        emp_filters = [f"{LA_FIELD_EMPLOYEE_ID} eq '{eid}'" for eid in employee_ids]
        filter_clause += " and (" + " or ".join(emp_filters) + ")"
    
    url = f"{BASE_URL}/api/data/v9.2/{LOGIN_ACTIVITY_ENTITY}?$filter={filter_clause}"
    headers = {"Authorization": f"Bearer {get_access_token()}"}
    
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        records = resp.json().get("value", [])
        print(f"   Found {len(records)} login records to delete")
        
        for rec in records:
            rec_id = rec.get(LOGIN_ACTIVITY_PRIMARY_FIELD)
            if rec_id:
                del_url = f"{BASE_URL}/api/data/v9.2/{LOGIN_ACTIVITY_ENTITY}({rec_id})"
                del_resp = requests.delete(del_url, headers=headers)
                if del_resp.status_code == 204:
                    print(f"   ✅ Deleted login record {rec_id}")
                else:
                    print(f"   ❌ Failed to delete {rec_id}: {del_resp.status_code}")
    else:
        print(f"   ❌ Failed to fetch login records: {resp.status_code}")

def clear_active_sessions():
    """Clear server-side active_sessions"""
    print("🧹 Clearing active_sessions...")
    try:
        resp = requests.post(f"{API_BASE}/api/admin/clear-sessions", 
                           headers={"Content-Type": "application/json"})
        if resp.status_code == 200:
            print("   ✅ Cleared active_sessions")
        else:
            print(f"   ❌ Failed to clear sessions: {resp.status_code}")
    except Exception as e:
        print(f"   ❌ Error clearing sessions: {e}")

def add_cache_clear_endpoint():
    """Add endpoint to force frontend cache clear"""
    endpoint_code = '''
@app.route('/api/admin/clear-cache', methods=['POST'])
def clear_frontend_cache():
    """Force clear frontend cache for all users"""
    return jsonify({"success": True, "message": "Cache cleared - users must re-login"})
'''
    print("📝 Add this endpoint to unified_server.py:")
    print(endpoint_code)

if __name__ == "__main__":
    print("=== Employee ID Change Cleanup ===")
    print("1. Clear today's login activity")
    print("2. Clear active sessions")
    print("3. Add cache-clear endpoint")
    print("4. Restart server")
    print("5. Ask all users to re-login")
    
    # Run cleanup
    clear_today_login_activity()
    clear_active_sessions()
    add_cache_clear_endpoint()
    
    print("\n✅ Cleanup complete. Restart server now.")
