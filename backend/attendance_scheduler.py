# attendance_scheduler.py - Scheduled Jobs for Attendance System
# Uses EXISTING Dataverse tables: crc6f_table13s + crc6f_hr_loginactivitytbs
# Handles midnight auto-close and absent marking

from datetime import datetime, timezone, timedelta
import os
import requests

from dataverse_helper import get_access_token, update_record, create_record

# ================== CONFIGURATION ==================
RESOURCE = os.getenv("RESOURCE", "")
SOCKET_SERVER_URL = os.getenv("SOCKET_SERVER_URL", "http://localhost:4001")

HALF_DAY_SECONDS = 4 * 3600
FULL_DAY_SECONDS = 9 * 3600

# ================== EXISTING Dataverse tables ==================
ATTENDANCE_ENTITY = "crc6f_table13s"
LOGIN_ACTIVITY_ENTITY = "crc6f_hr_loginactivitytbs"
EMPLOYEE_ENTITY = "crc6f_table12s"

# Attendance table fields
FIELD_RECORD_ID = "crc6f_table13id"
FIELD_ATTENDANCE_ID = "crc6f_attendanceid"
FIELD_EMPLOYEE_ID = "crc6f_employeeid"
FIELD_DATE = "crc6f_date"
FIELD_CHECKIN = "crc6f_checkin"
FIELD_CHECKOUT = "crc6f_checkout"
FIELD_DURATION = "crc6f_duration"
FIELD_DURATION_INTEXT = "crc6f_duration_intext"
FIELD_STATUS = "crc6f_status"

# Login activity table fields
LA_PRIMARY_FIELD = "crc6f_hr_loginactivitytbid"
LA_FIELD_EMPLOYEE_ID = "crc6f_employeeid"
LA_FIELD_DATE = "crc6f_date"
LA_FIELD_CHECKIN_TS = "crc6f_checkin_timestamp"
LA_FIELD_CHECKOUT_TS = "crc6f_checkout_timestamp"
LA_FIELD_CHECKOUT_TIME = "crc6f_checkouttime"
LA_FIELD_BASE_SECONDS = "crc6f_base_seconds"
LA_FIELD_TOTAL_SECONDS = "crc6f_total_seconds"


def get_server_now_utc():
    return datetime.now(timezone.utc)


def derive_status(total_seconds):
    if total_seconds >= FULL_DAY_SECONDS:
        return "P"
    elif total_seconds >= HALF_DAY_SECONDS:
        return "HL"
    return "A"


def format_duration_text(seconds):
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    return f"{hours} hour(s) {minutes} minute(s)"


def format_duration_hours(seconds):
    return round(seconds / 3600, 2)


def generate_id(prefix):
    import random
    import string
    chars = ''.join(random.choices(string.ascii_uppercase + string.digits, k=7))
    return f"{prefix}-{chars}"


def emit_attendance_changed(employee_id, event_type):
    try:
        requests.post(
            f"{SOCKET_SERVER_URL}/emit",
            json={
                "event": "attendance:changed",
                "data": {
                    "employee_id": employee_id,
                    "event_type": event_type,
                    "server_now_utc": get_server_now_utc().isoformat()
                }
            },
            timeout=2
        )
    except Exception:
        pass


def _get_headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "OData-MaxVersion": "4.0",
        "OData-Version": "4.0"
    }


# ================== JOB 1: AUTO-CLOSE ACTIVE SESSIONS ==================

def auto_close_active_sessions():
    """
    Close all active attendance sessions at end of workday.
    Finds sessions in login_activity that have checkin but no checkout.
    """
    print(f"[SCHEDULER] Running auto_close_active_sessions at {get_server_now_utc().isoformat()}")
    
    try:
        token = get_access_token()
        headers = _get_headers(token)
        now_utc = get_server_now_utc()
        today_date = now_utc.strftime("%Y-%m-%d")
        checkout_time = now_utc.strftime("%H:%M:%S")
        checkout_ts = int(now_utc.timestamp())
        
        # Find active sessions: has checkin_timestamp but no checkout_timestamp
        filter_query = (
            f"$filter={LA_FIELD_DATE} eq '{today_date}' "
            f"and {LA_FIELD_CHECKIN_TS} ne null "
            f"and {LA_FIELD_CHECKOUT_TS} eq null"
        )
        url = f"{RESOURCE}/api/data/v9.2/{LOGIN_ACTIVITY_ENTITY}?{filter_query}"
        
        response = requests.get(url, headers=headers, timeout=30)
        
        if response.status_code != 200:
            print(f"[SCHEDULER] Failed to fetch active sessions: {response.status_code}")
            return
        
        active_records = response.json().get("value", [])
        print(f"[SCHEDULER] Found {len(active_records)} active sessions to close")
        
        closed_count = 0
        for record in active_records:
            try:
                la_record_id = record.get(LA_PRIMARY_FIELD)
                employee_id = record.get(LA_FIELD_EMPLOYEE_ID)
                checkin_ts = record.get(LA_FIELD_CHECKIN_TS)
                base_seconds = int(record.get(LA_FIELD_BASE_SECONDS) or 0)
                
                if not la_record_id or not employee_id or not checkin_ts:
                    continue
                
                # Calculate session duration
                session_seconds = max(0, checkout_ts - int(checkin_ts))
                total_seconds = base_seconds + session_seconds
                status = derive_status(total_seconds)
                hours = format_duration_hours(total_seconds)
                duration_text = format_duration_text(total_seconds)
                
                # Update login activity
                la_update = {
                    LA_FIELD_CHECKOUT_TIME: checkout_time,
                    LA_FIELD_CHECKOUT_TS: checkout_ts,
                    LA_FIELD_TOTAL_SECONDS: total_seconds
                }
                
                la_url = f"{RESOURCE}/api/data/v9.2/{LOGIN_ACTIVITY_ENTITY}({la_record_id})"
                requests.patch(la_url, headers=headers, json=la_update, timeout=20)
                
                # Update attendance record
                att_filter = f"$filter={FIELD_EMPLOYEE_ID} eq '{employee_id}' and {FIELD_DATE} eq '{today_date}'"
                att_url = f"{RESOURCE}/api/data/v9.2/{ATTENDANCE_ENTITY}?{att_filter}"
                att_resp = requests.get(att_url, headers=headers, timeout=20)
                
                if att_resp.status_code == 200:
                    att_records = att_resp.json().get("value", [])
                    if att_records:
                        att_record_id = att_records[0].get(FIELD_RECORD_ID)
                        if att_record_id:
                            att_update = {
                                FIELD_CHECKOUT: checkout_time,
                                FIELD_DURATION: str(hours),
                                FIELD_DURATION_INTEXT: duration_text
                            }
                            if FIELD_STATUS:
                                att_update[FIELD_STATUS] = status
                            update_record(ATTENDANCE_ENTITY, att_record_id, att_update)
                
                emit_attendance_changed(employee_id, "auto_closed")
                closed_count += 1
                print(f"[SCHEDULER] Auto-closed session for {employee_id}, duration: {total_seconds}s, status: {status}")
                
            except Exception as e:
                print(f"[SCHEDULER] Error closing session: {e}")
                continue
        
        print(f"[SCHEDULER] Successfully closed {closed_count} sessions")
        
    except Exception as e:
        print(f"[SCHEDULER] auto_close_active_sessions failed: {e}")
        import traceback
        traceback.print_exc()


# ================== JOB 2: MARK ABSENT EMPLOYEES ==================

def mark_absent_employees():
    """
    Create 'Absent' records for employees who didn't check in yesterday.
    Should run daily after midnight.
    """
    print(f"[SCHEDULER] Running mark_absent_employees at {get_server_now_utc().isoformat()}")
    
    try:
        token = get_access_token()
        headers = _get_headers(token)
        now_utc = get_server_now_utc()
        yesterday = (now_utc - timedelta(days=1)).strftime("%Y-%m-%d")
        
        # Check if yesterday was a weekend
        yesterday_date = now_utc - timedelta(days=1)
        if yesterday_date.weekday() >= 5:
            print(f"[SCHEDULER] {yesterday} is a weekend, skipping absent marking")
            return
        
        # Get all active employees
        emp_url = f"{RESOURCE}/api/data/v9.2/{EMPLOYEE_ENTITY}?$filter=crc6f_activeflag eq true&$select=crc6f_employeeid"
        emp_resp = requests.get(emp_url, headers=headers, timeout=30)
        
        if emp_resp.status_code != 200:
            print(f"[SCHEDULER] Failed to fetch employees: {emp_resp.status_code}")
            return
        
        employees = emp_resp.json().get("value", [])
        all_employee_ids = {emp.get("crc6f_employeeid", "").upper() for emp in employees if emp.get("crc6f_employeeid")}
        
        # Get employees who have attendance for yesterday
        att_url = f"{RESOURCE}/api/data/v9.2/{ATTENDANCE_ENTITY}?$filter={FIELD_DATE} eq '{yesterday}'&$select={FIELD_EMPLOYEE_ID}"
        att_resp = requests.get(att_url, headers=headers, timeout=30)
        
        if att_resp.status_code != 200:
            print(f"[SCHEDULER] Failed to fetch attendance: {att_resp.status_code}")
            return
        
        attendance_records = att_resp.json().get("value", [])
        employees_with_attendance = {rec.get(FIELD_EMPLOYEE_ID, "").upper() for rec in attendance_records}
        
        # Find employees without attendance
        absent_employees = all_employee_ids - employees_with_attendance
        print(f"[SCHEDULER] Found {len(absent_employees)} employees without attendance for {yesterday}")
        
        created_count = 0
        for employee_id in absent_employees:
            try:
                attendance_id = generate_id("ATD")
                create_record(ATTENDANCE_ENTITY, {
                    FIELD_ATTENDANCE_ID: attendance_id,
                    FIELD_EMPLOYEE_ID: employee_id,
                    FIELD_DATE: yesterday,
                    FIELD_DURATION: "0",
                    FIELD_DURATION_INTEXT: "0 hour(s) 0 minute(s)"
                })
                created_count += 1
                
            except Exception as e:
                print(f"[SCHEDULER] Error creating absent record for {employee_id}: {e}")
                continue
        
        print(f"[SCHEDULER] Successfully created {created_count} absent records")
        
    except Exception as e:
        print(f"[SCHEDULER] mark_absent_employees failed: {e}")
        import traceback
        traceback.print_exc()


# ================== SCHEDULER SETUP ==================

def setup_scheduler(app):
    """Setup APScheduler with attendance jobs."""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
        
        scheduler = BackgroundScheduler()
        
        # Auto-close at 23:59 UTC
        scheduler.add_job(
            auto_close_active_sessions,
            CronTrigger(hour=23, minute=59, timezone='UTC'),
            id='auto_close_sessions',
            replace_existing=True
        )
        
        # Mark absent at 00:10 UTC
        scheduler.add_job(
            mark_absent_employees,
            CronTrigger(hour=0, minute=10, timezone='UTC'),
            id='mark_absent_employees',
            replace_existing=True
        )
        
        scheduler.start()
        print("[SCHEDULER] APScheduler started with attendance jobs")
        app.attendance_scheduler = scheduler
        return scheduler
        
    except ImportError:
        print("[SCHEDULER] APScheduler not installed. Install with: pip install apscheduler")
        return None


def shutdown_scheduler(app):
    if hasattr(app, 'attendance_scheduler') and app.attendance_scheduler:
        app.attendance_scheduler.shutdown(wait=False)
        print("[SCHEDULER] APScheduler shutdown complete")


if __name__ == "__main__":
    print("Running scheduler jobs manually...")
    auto_close_active_sessions()
    mark_absent_employees()
