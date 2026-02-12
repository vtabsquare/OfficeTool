"""
Test script to verify the attendance display fix
"""

import requests
import json

BASE_URL = "http://localhost:5000/api"

def test_attendance_display():
    print("=" * 80)
    print("TESTING ATTENDANCE DISPLAY FIX")
    print("=" * 80)
    
    # Test 1: Check if login-events endpoint works
    print("\n1. Testing login-events endpoint:")
    try:
        resp = requests.get(f"{BASE_URL}/login-events?employee_id=EMP019&from=2026-02-12&to=2026-02-12")
        print(f"   Status Code: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"   Success: {data.get('success')}")
            if data.get('daily_summary'):
                summary = data['daily_summary'][0] if data['daily_summary'] else {}
                print(f"   Date: {summary.get('date')}")
                print(f"   Check In: {summary.get('check_in_time')}")
                print(f"   Check Out: {summary.get('check_out_time')}")
        else:
            print(f"   Error: {resp.text[:200]}")
    except Exception as e:
        print(f"   Exception: {e}")
    
    # Test 2: Check monthly attendance
    print("\n2. Testing monthly attendance endpoint:")
    try:
        resp = requests.get(f"{BASE_URL}/attendance/EMP019/2026/2")
        if resp.status_code == 200:
            data = resp.json()
            records = data.get('records', [])
            today_record = None
            for rec in records:
                if rec.get('date') == '2026-02-12':
                    today_record = rec
                    break
            
            if today_record:
                print(f"   Today's record from attendance table:")
                print(f"   - CheckIn: {today_record.get('checkIn')}")
                print(f"   - CheckOut: {today_record.get('checkOut')}")
                print(f"   - Duration: {today_record.get('duration')}")
        else:
            print(f"   Error: {resp.status_code}")
    except Exception as e:
        print(f"   Exception: {e}")
    
    print("\n3. Expected behavior after fix:")
    print("   - Current Day: Shows correct data from login activity")
    print("   - Current Week/Month: Now also fetches from login activity for accurate checkout")
    print("   - Both should show the same checkout time: 14:50:08")

if __name__ == "__main__":
    test_attendance_display()
