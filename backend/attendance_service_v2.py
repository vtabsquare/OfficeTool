# attendance_service_v2.py - Backend-Authoritative Attendance Service
# Enterprise-grade implementation following Zoho People architecture
# ALL time calculations happen HERE - Frontend is stateless
# USES EXISTING Dataverse tables: crc6f_table13s (attendance) + crc6f_hr_loginactivitytbs (session tracking)

from flask import Blueprint, request, jsonify
from datetime import datetime, timezone, timedelta
from calendar import monthrange
import random
import string
import json
import os
import requests

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from pytz import timezone as ZoneInfo

from dataverse_helper import create_record, update_record, get_access_token
from time_tracking import stop_active_task_entries_for_user

# Blueprint for v2 attendance routes
attendance_v2_bp = Blueprint('attendance_v2', __name__, url_prefix='/api/v2/attendance')

@attendance_v2_bp.after_request
def add_cors_headers(response):
    """Add CORS headers to all responses from this blueprint"""
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, Cache-Control, Pragma'
    return response

@attendance_v2_bp.route('/<path:path>', methods=['OPTIONS'])
@attendance_v2_bp.route('/', methods=['OPTIONS'])
def handle_options(path=None):
    """Handle preflight OPTIONS requests"""
    response = jsonify({'status': 'ok'})
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, Cache-Control, Pragma'
    return response

# ================== CONFIGURATION ==================
HALF_DAY_SECONDS = 4 * 3600      # 4 hours = Half Day (HL)
FULL_DAY_SECONDS = 9 * 3600      # 9 hours = Present (P)
HALF_DAY_HOURS = 4.0
FULL_DAY_HOURS = 9.0

# ================== EXISTING Dataverse entity names ==================
ATTENDANCE_ENTITY = "crc6f_table13s"
LOGIN_ACTIVITY_ENTITY = "crc6f_hr_loginactivitytbs"
EMPLOYEE_ENTITY = "crc6f_table12s"

# ================== ATTENDANCE TABLE FIELDS (crc6f_table13s) ==================
FIELD_RECORD_ID = "crc6f_table13id"
FIELD_ATTENDANCE_ID = "crc6f_attendanceid"
FIELD_EMPLOYEE_ID = "crc6f_employeeid"
FIELD_DATE = "crc6f_date"
FIELD_CHECKIN = "crc6f_checkin"
FIELD_CHECKOUT = "crc6f_checkout"
FIELD_DURATION = "crc6f_duration"
FIELD_DURATION_INTEXT = "crc6f_duration_intext"
FIELD_STATUS = "crc6f_status"

# ================== LOGIN ACTIVITY TABLE FIELDS ==================
LA_PRIMARY_FIELD = "crc6f_hr_loginactivitytbid"
LA_FIELD_EMPLOYEE_ID = "crc6f_employeeid"
LA_FIELD_DATE = "crc6f_date"
LA_FIELD_CHECKIN_TIME = "crc6f_checkintime"
LA_FIELD_CHECKIN_LOCATION = "crc6f_checkinlocation"
LA_FIELD_CHECKOUT_TIME = "crc6f_checkouttime"
LA_FIELD_CHECKOUT_LOCATION = "crc6f_checkoutlocation"
LA_FIELD_CHECKIN_TS = "crc6f_checkin_timestamp"
LA_FIELD_CHECKOUT_TS = "crc6f_checkout_timestamp"
LA_FIELD_BASE_SECONDS = "crc6f_base_seconds"
LA_FIELD_TOTAL_SECONDS = "crc6f_total_seconds"

# Environment
RESOURCE = os.getenv("RESOURCE", "")
SOCKET_SERVER_URL = os.getenv("SOCKET_SERVER_URL", "http://localhost:4001")


# ================== UTILITY FUNCTIONS ==================

def generate_attendance_id():
    """Generate a random attendance ID like ATD-A1B2C3D"""
    chars = ''.join(random.choices(string.ascii_uppercase + string.digits, k=7))
    return f"ATD-{chars}"


def get_server_now_utc():
    """Get current server time in UTC - THE source of truth"""
    return datetime.now(timezone.utc)


def derive_status(total_seconds):
    """Derive attendance status from total seconds worked"""
    if total_seconds >= FULL_DAY_SECONDS:
        return "P"
    elif total_seconds >= HALF_DAY_SECONDS:
        return "HL"
    return "A"


def derive_status_label(status_code):
    """Get full label for status code"""
    labels = {"P": "Present", "HL": "Half Day", "A": "Absent"}
    return labels.get(status_code, "Absent")


def format_duration_text(seconds):
    """Format seconds as 'N hour(s) M minute(s)'"""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    return f"{hours} hour(s) {minutes} minute(s)"


def format_duration_short(seconds):
    """Format seconds as 'Xh Ym'"""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    return f"{hours}h {minutes}m"


def format_duration_hours(seconds):
    """Format seconds as decimal hours"""
    return round(seconds / 3600, 2)


def localize_time(utc_dt, tz_name):
    """Convert UTC datetime to local time string HH:MM:SS"""
    if not utc_dt:
        return None
    try:
        tz = ZoneInfo(tz_name)
        local_dt = utc_dt.astimezone(tz)
        return local_dt.strftime("%H:%M:%S")
    except Exception:
        if hasattr(utc_dt, 'strftime'):
            return utc_dt.strftime("%H:%M:%S")
        return str(utc_dt)


def location_to_string(location):
    """Convert location dict to string for storage"""
    if not location:
        return None
    if isinstance(location, dict):
        lat = location.get("lat")
        lng = location.get("lng")
        if lat and lng:
            return f"{lat},{lng}"
    return str(location) if location else None


def emit_attendance_changed(employee_id, event_type):
    """Broadcast attendance change event to socket server"""
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
    except Exception as e:
        print(f"[ATTENDANCE-V2] Socket emit failed: {e}")


# ================== DATAVERSE OPERATIONS ==================

def _get_base_url():
    """Get Dataverse API base URL"""
    return f"{RESOURCE}/api/data/v9.2"


def _get_headers(token):
    """Get standard headers for Dataverse API"""
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "OData-MaxVersion": "4.0",
        "OData-Version": "4.0"
    }


def fetch_attendance_record(employee_id, date_str):
    """Fetch attendance record for employee on specific date"""
    try:
        token = get_access_token()
        headers = _get_headers(token)
        
        emp = employee_id.strip().upper()
        filter_q = f"$filter={FIELD_EMPLOYEE_ID} eq '{emp}' and {FIELD_DATE} eq '{date_str}'"
        url = f"{_get_base_url()}/{ATTENDANCE_ENTITY}?{filter_q}"
        
        resp = requests.get(url, headers=headers, timeout=20)
        if resp.status_code == 200:
            records = resp.json().get("value", [])
            return records[0] if records else None
        return None
    except Exception as e:
        print(f"[ATTENDANCE-V2] fetch_attendance_record error: {e}")
        return None


def fetch_login_activity(employee_id, date_str):
    """Fetch login activity record for employee on specific date"""
    try:
        token = get_access_token()
        headers = _get_headers(token)
        
        emp = employee_id.strip().upper()
        filter_q = f"$filter={LA_FIELD_EMPLOYEE_ID} eq '{emp}' and {LA_FIELD_DATE} eq '{date_str}'"
        url = f"{_get_base_url()}/{LOGIN_ACTIVITY_ENTITY}?{filter_q}&$top=1"
        
        resp = requests.get(url, headers=headers, timeout=20)
        if resp.status_code == 200:
            records = resp.json().get("value", [])
            return records[0] if records else None
        return None
    except Exception as e:
        print(f"[ATTENDANCE-V2] fetch_login_activity error: {e}")
        return None


def upsert_login_activity(employee_id, date_str, payload):
    """Create or update login activity record"""
    try:
        token = get_access_token()
        headers = _get_headers(token)
        emp = employee_id.strip().upper()
        
        existing = fetch_login_activity(emp, date_str)
        
        if existing and existing.get(LA_PRIMARY_FIELD):
            # Update existing
            record_id = existing.get(LA_PRIMARY_FIELD)
            url = f"{_get_base_url()}/{LOGIN_ACTIVITY_ENTITY}({record_id})"
            resp = requests.patch(url, headers=headers, json=payload, timeout=20)
            return resp.status_code < 400
        else:
            # Create new
            create_payload = {
                LA_FIELD_EMPLOYEE_ID: emp,
                LA_FIELD_DATE: date_str,
                **payload
            }
            url = f"{_get_base_url()}/{LOGIN_ACTIVITY_ENTITY}"
            resp = requests.post(url, headers=headers, json=create_payload, timeout=20)
            return resp.status_code < 400
    except Exception as e:
        print(f"[ATTENDANCE-V2] upsert_login_activity error: {e}")
        return False


def _auto_close_stale_sessions(employee_id, tz_name="Asia/Calcutta"):
    """
    Auto-close any older open sessions (date < local today) at local 00:00:00.

    This keeps attendance totals bounded to the day and prevents cross-day
    running timers when checkout is forgotten.
    """
    try:
        emp = (employee_id or "").strip().upper()
        if not emp:
            return {"closed": 0}

        now_utc = get_server_now_utc()
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            try:
                tz = ZoneInfo("Asia/Calcutta")
            except Exception:
                tz = timezone.utc

        local_today = now_utc.astimezone(tz).date().isoformat()
        token = get_access_token()
        headers = _get_headers(token)

        safe_emp = emp.replace("'", "''")

        # Try two filter strategies because Dataverse may store crc6f_date
        # as plain Date (matches 'lt YYYY-MM-DD') OR as DateTime
        # (needs 'lt YYYY-MM-DDT00:00:00Z').  Also widen to include legacy
        # rows that only have time-string fields (no timestamp fields).
        today_dt_iso = f"{local_today}T00:00:00Z"
        open_session_cond = (
            f"({LA_FIELD_CHECKIN_TS} ne null or {LA_FIELD_CHECKIN_TIME} ne null) "
            f"and ({LA_FIELD_CHECKOUT_TS} eq null and {LA_FIELD_CHECKOUT_TIME} eq null)"
        )

        stale_rows = []
        seen_ids = set()

        for date_bound in [local_today, today_dt_iso]:
            filter_q = (
                f"$filter={LA_FIELD_EMPLOYEE_ID} eq '{safe_emp}' "
                f"and {open_session_cond} "
                f"and {LA_FIELD_DATE} lt '{date_bound}'"
            )
            url = f"{_get_base_url()}/{LOGIN_ACTIVITY_ENTITY}?{filter_q}&$orderby={LA_FIELD_DATE} asc"
            try:
                resp = requests.get(url, headers=headers, timeout=20)
                if resp.status_code == 200:
                    for r in resp.json().get("value", []):
                        rid = r.get(LA_PRIMARY_FIELD)
                        if rid and rid not in seen_ids:
                            seen_ids.add(rid)
                            stale_rows.append(r)
            except Exception:
                pass

        if not stale_rows:
            return {"closed": 0}
        closed = 0

        for row in stale_rows:
            try:
                la_id = row.get(LA_PRIMARY_FIELD)
                raw_date = str(row.get(LA_FIELD_DATE) or "")[:10]
                checkin_ts = int(row.get(LA_FIELD_CHECKIN_TS) or 0)
                if not checkin_ts:
                    try:
                        checkin_time_raw = str(row.get(LA_FIELD_CHECKIN_TIME) or "")
                        checkin_time_only = checkin_time_raw[:8] if len(checkin_time_raw) >= 8 else checkin_time_raw
                        local_checkin = datetime.strptime(
                            f"{raw_date} {checkin_time_only}",
                            "%Y-%m-%d %H:%M:%S",
                        ).replace(tzinfo=tz)
                        checkin_ts = int(local_checkin.astimezone(timezone.utc).timestamp())
                    except Exception:
                        checkin_ts = 0
                base_seconds = int(row.get(LA_FIELD_BASE_SECONDS) or 0)
                if not la_id or not raw_date or not checkin_ts:
                    continue

                day_obj = datetime.strptime(raw_date, "%Y-%m-%d").date()
                next_midnight_local = datetime(
                    day_obj.year, day_obj.month, day_obj.day, 0, 0, 0, tzinfo=tz
                ) + timedelta(days=1)
                cutoff_utc = next_midnight_local.astimezone(timezone.utc)
                cutoff_ts = int(cutoff_utc.timestamp())

                session_seconds = max(0, cutoff_ts - checkin_ts)
                total_seconds = base_seconds + session_seconds
                status = derive_status(total_seconds)
                hours = format_duration_hours(total_seconds)
                duration_text = format_duration_text(total_seconds)

                # Login activity close at local midnight.
                la_patch = {
                    LA_FIELD_CHECKOUT_TIME: next_midnight_local.strftime("%H:%M:%S"),
                    LA_FIELD_CHECKOUT_TS: cutoff_ts,
                    LA_FIELD_TOTAL_SECONDS: total_seconds,
                }
                la_url = f"{_get_base_url()}/{LOGIN_ACTIVITY_ENTITY}({la_id})"
                la_resp = requests.patch(la_url, headers=headers, json=la_patch, timeout=20)
                if la_resp.status_code >= 400:
                    continue

                # Attendance row close for that historical date.
                existing_att = fetch_attendance_record(emp, raw_date)
                if existing_att:
                    record_id = existing_att.get(FIELD_RECORD_ID) or existing_att.get("crc6f_table13id")
                    if record_id:
                        update_payload = {
                            FIELD_CHECKOUT: next_midnight_local.strftime("%H:%M:%S"),
                            FIELD_DURATION: str(hours),
                            FIELD_DURATION_INTEXT: duration_text,
                        }
                        if FIELD_STATUS:
                            update_payload[FIELD_STATUS] = status
                        try:
                            update_record(ATTENDANCE_ENTITY, record_id, update_payload)
                        except Exception:
                            pass

                # Keep task timer state aligned with auto checkout behavior.
                try:
                    stop_active_task_entries_for_user(emp, cutoff_utc.isoformat())
                except Exception as stop_err:
                    print(f"[ATTENDANCE-V2] Auto-close task stop failed for {emp}: {stop_err}")

                emit_attendance_changed(emp, "auto_checkout_midnight")
                closed += 1
            except Exception as row_err:
                print(f"[ATTENDANCE-V2] Failed stale auto-close row: {row_err}")

        if closed:
            print(f"[ATTENDANCE-V2] Auto-closed {closed} stale session(s) for {emp}")
        return {"closed": closed}
    except Exception as e:
        print(f"[ATTENDANCE-V2] auto-close stale sessions error: {e}")
        return {"closed": 0}


# ================== API ROUTES ==================

@attendance_v2_bp.route('/checkin', methods=['POST'])
def checkin_v2():
    """
    Check-in: Creates or resumes attendance session.
    Backend is THE source of truth for all timestamps.
    """
    try:
        data = request.json or {}
        employee_id = (data.get('employee_id') or '').strip().upper()
        tz_name = data.get('timezone', 'UTC')
        location = data.get('location')
        
        if not employee_id:
            return jsonify({"success": False, "error": "MISSING_EMPLOYEE_ID"}), 400

        # Self-heal stale open sessions from previous local days.
        _auto_close_stale_sessions(employee_id, tz_name)
        
        # SERVER TIME IS TRUTH
        now_utc = get_server_now_utc()
        checkin_time = now_utc.strftime("%H:%M:%S")
        checkin_ts = int(now_utc.timestamp())
        
        # Use client's timezone to determine "today" (handles midnight correctly)
        try:
            client_tz = ZoneInfo(tz_name)
            client_now = now_utc.astimezone(client_tz)
            today_date = client_now.strftime("%Y-%m-%d")
        except Exception:
            today_date = now_utc.strftime("%Y-%m-%d")
        
        # Check for existing attendance record today
        existing_att = fetch_attendance_record(employee_id, today_date)
        existing_la = fetch_login_activity(employee_id, today_date)

        # Safety guard: discard stale login-activity from a prior day
        if existing_la:
            la_rec_date = str(existing_la.get(LA_FIELD_DATE) or "")[:10]
            if la_rec_date and la_rec_date != today_date:
                existing_la = None
        
        # Check if already checked in (has checkin but no checkout in login activity)
        if existing_la:
            has_checkin = existing_la.get(LA_FIELD_CHECKIN_TS) or existing_la.get(LA_FIELD_CHECKIN_TIME)
            has_checkout = existing_la.get(LA_FIELD_CHECKOUT_TS) or existing_la.get(LA_FIELD_CHECKOUT_TIME)
            
            if has_checkin and not has_checkout:
                # Already checked in - return current state
                checkin_ts_val = existing_la.get(LA_FIELD_CHECKIN_TS) or checkin_ts
                base_seconds = int(existing_la.get(LA_FIELD_BASE_SECONDS) or 0)
                elapsed = int(now_utc.timestamp()) - int(checkin_ts_val)
                total_seconds = base_seconds + max(0, elapsed)
                
                return jsonify({
                    "success": True,
                    "already_checked_in": True,
                    "attendance_id": existing_att.get(FIELD_ATTENDANCE_ID) if existing_att else None,
                    "checkin_utc": datetime.fromtimestamp(checkin_ts_val, tz=timezone.utc).isoformat(),
                    "server_now_utc": now_utc.isoformat(),
                    "elapsed_seconds": max(0, elapsed),
                    "total_seconds_today": total_seconds,
                    "is_active_session": True,
                    "status_code": derive_status(total_seconds),
                    "display": {
                        "checkin_local": localize_time(datetime.fromtimestamp(checkin_ts_val, tz=timezone.utc), tz_name),
                        "elapsed_text": format_duration_text(total_seconds),
                        "timezone": tz_name
                    }
                })
        
        # Get base seconds from previous sessions today
        base_seconds = 0
        if existing_la:
            base_seconds = int(existing_la.get(LA_FIELD_TOTAL_SECONDS) or existing_la.get(LA_FIELD_BASE_SECONDS) or 0)
        elif existing_att:
            try:
                base_seconds = int(float(existing_att.get(FIELD_DURATION) or 0) * 3600)
            except:
                base_seconds = 0
        
        attendance_id = None
        record_id = None
        
        if existing_att:
            # Reuse existing attendance record
            record_id = existing_att.get(FIELD_RECORD_ID) or existing_att.get("crc6f_table13id")
            attendance_id = existing_att.get(FIELD_ATTENDANCE_ID) or generate_attendance_id()
            
            # Clear checkout field for continuation.
            # IMPORTANT: preserve original check-in time for the day to avoid
            # rewriting historical first check-in when user resumes a session.
            try:
                update_payload = {FIELD_CHECKOUT: None}
                existing_checkin = existing_att.get(FIELD_CHECKIN)
                if not existing_checkin:
                    update_payload[FIELD_CHECKIN] = checkin_time
                update_record(ATTENDANCE_ENTITY, record_id, update_payload)
            except Exception as e:
                print(f"[ATTENDANCE-V2] Update attendance record error: {e}")
        else:
            # Create new attendance record
            attendance_id = generate_attendance_id()
            record_data = {
                FIELD_ATTENDANCE_ID: attendance_id,
                FIELD_EMPLOYEE_ID: employee_id,
                FIELD_DATE: today_date,
                FIELD_CHECKIN: checkin_time
            }
            try:
                created = create_record(ATTENDANCE_ENTITY, record_data)
                record_id = created.get(FIELD_RECORD_ID) or created.get("crc6f_table13id")
            except Exception as e:
                print(f"[ATTENDANCE-V2] Create attendance record error: {e}")
        
        # Update login activity with session info
        la_payload = {
            LA_FIELD_CHECKIN_TIME: checkin_time,
            LA_FIELD_CHECKIN_TS: checkin_ts,
            LA_FIELD_BASE_SECONDS: base_seconds,
            LA_FIELD_CHECKIN_LOCATION: location_to_string(location),
            LA_FIELD_CHECKOUT_TIME: None,
            LA_FIELD_CHECKOUT_TS: None
        }
        upsert_login_activity(employee_id, today_date, la_payload)
        
        # Emit socket event
        emit_attendance_changed(employee_id, "checkin")
        
        return jsonify({
            "success": True,
            "attendance_id": attendance_id,
            "checkin_utc": now_utc.isoformat(),
            "server_now_utc": now_utc.isoformat(),
            "total_seconds_today": base_seconds,
            "is_active_session": True,
            "session_count": 1,
            "status_code": derive_status(base_seconds),
            "display": {
                "checkin_local": localize_time(now_utc, tz_name),
                "date_local": today_date,
                "timezone": tz_name
            }
        })
        
    except Exception as e:
        print(f"[ATTENDANCE-V2] Check-in error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@attendance_v2_bp.route('/checkout', methods=['POST'])
def checkout_v2():
    """
    Check-out: Closes current session and accumulates duration.
    ALL calculations done on server.
    """
    try:
        data = request.json or {}
        employee_id = (data.get('employee_id') or '').strip().upper()
        tz_name = data.get('timezone', 'UTC')
        location = data.get('location')
        
        if not employee_id:
            return jsonify({"success": False, "error": "MISSING_EMPLOYEE_ID"}), 400
        
        # SERVER TIME IS TRUTH
        now_utc = get_server_now_utc()
        checkout_time = now_utc.strftime("%H:%M:%S")
        checkout_ts = int(now_utc.timestamp())
        
        # Use client's timezone to determine "today" (handles midnight correctly)
        try:
            client_tz = ZoneInfo(tz_name)
            client_now = now_utc.astimezone(client_tz)
            today_date = client_now.strftime("%Y-%m-%d")
        except Exception:
            today_date = now_utc.strftime("%Y-%m-%d")
        
        # Get login activity to find active session
        existing_la = fetch_login_activity(employee_id, today_date)
        
        if not existing_la:
            return jsonify({"success": False, "error": "NO_ACTIVE_SESSION"}), 400
        
        checkin_ts_val = existing_la.get(LA_FIELD_CHECKIN_TS)
        has_checkout = existing_la.get(LA_FIELD_CHECKOUT_TS) or existing_la.get(LA_FIELD_CHECKOUT_TIME)
        
        if not checkin_ts_val or has_checkout:
            return jsonify({"success": False, "error": "NO_ACTIVE_SESSION"}), 400
        
        # Calculate session duration
        base_seconds = int(existing_la.get(LA_FIELD_BASE_SECONDS) or 0)
        session_seconds = max(0, checkout_ts - int(checkin_ts_val))
        total_seconds = base_seconds + session_seconds
        
        # Derive status
        status = derive_status(total_seconds)
        hours = format_duration_hours(total_seconds)
        duration_text = format_duration_text(total_seconds)
        
        # Update login activity
        la_payload = {
            LA_FIELD_CHECKOUT_TIME: checkout_time,
            LA_FIELD_CHECKOUT_TS: checkout_ts,
            LA_FIELD_TOTAL_SECONDS: total_seconds,
            LA_FIELD_CHECKOUT_LOCATION: location_to_string(location)
        }
        upsert_login_activity(employee_id, today_date, la_payload)

        # Force-stop any active task timers for this user to avoid overnight carry-over.
        try:
            stop_active_task_entries_for_user(employee_id, now_utc.isoformat())
        except Exception as task_timer_err:
            print(f"[ATTENDANCE-V2] Failed to force-stop task timers on checkout: {task_timer_err}")
        
        # Update attendance record
        existing_att = fetch_attendance_record(employee_id, today_date)
        if existing_att:
            record_id = existing_att.get(FIELD_RECORD_ID) or existing_att.get("crc6f_table13id")
            if record_id:
                update_payload = {
                    FIELD_CHECKOUT: checkout_time,
                    FIELD_DURATION: str(hours),
                    FIELD_DURATION_INTEXT: duration_text
                }
                if FIELD_STATUS:
                    update_payload[FIELD_STATUS] = status
                try:
                    update_record(ATTENDANCE_ENTITY, record_id, update_payload)
                except Exception as e:
                    print(f"[ATTENDANCE-V2] Update attendance checkout error: {e}")
        
        # Emit socket event
        emit_attendance_changed(employee_id, "checkout")
        
        return jsonify({
            "success": True,
            "attendance_id": existing_att.get(FIELD_ATTENDANCE_ID) if existing_att else None,
            "checkout_utc": now_utc.isoformat(),
            "server_now_utc": now_utc.isoformat(),
            "session_seconds": session_seconds,
            "total_seconds_today": total_seconds,
            "is_active_session": False,
            "status_code": status,
            "display": {
                "checkout_local": localize_time(now_utc, tz_name),
                "session_text": format_duration_text(session_seconds),
                "duration_text": duration_text,
                "status_label": derive_status_label(status),
                "timezone": tz_name
            }
        })
        
    except Exception as e:
        print(f"[ATTENDANCE-V2] Check-out error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@attendance_v2_bp.route('/status/<employee_id>', methods=['GET'])
def get_status_v2(employee_id):
    """
    Get current attendance status - CRITICAL endpoint.
    Called on EVERY page load/refresh. Frontend derives ALL display from this.
    """
    try:
        employee_id = employee_id.strip().upper()
        tz_name = request.args.get('timezone', 'UTC')
        
        # SERVER TIME IS TRUTH
        now_utc = get_server_now_utc()
        
        # Use client's timezone to determine "today" (handles midnight correctly)
        # This ensures 12:01 AM IST is Jan 7 for IST users, not Jan 6 (which UTC would give)
        try:
            client_tz = ZoneInfo(tz_name)
            client_now = now_utc.astimezone(client_tz)
            today_date = client_now.strftime("%Y-%m-%d")
        except Exception:
            # Fallback to UTC if timezone parsing fails
            today_date = now_utc.strftime("%Y-%m-%d")

        # Ensure forgotten checkouts from prior days are auto-closed at midnight.
        _auto_close_stale_sessions(employee_id, tz_name)
        
        # Get both records
        existing_att = fetch_attendance_record(employee_id, today_date)
        existing_la = fetch_login_activity(employee_id, today_date)

        # Safety guard: if the fetched login-activity record belongs to a
        # prior day (Dataverse DateTime/Date ambiguity can cause this), close
        # it inline and discard it so the status response reflects today only.
        if existing_la:
            la_record_date = str(existing_la.get(LA_FIELD_DATE) or "")[:10]
            if la_record_date and la_record_date != today_date:
                # This is a stale record from a prior day — force-close it now.
                la_checkin_ts = int(existing_la.get(LA_FIELD_CHECKIN_TS) or 0)
                la_checkout_ts = existing_la.get(LA_FIELD_CHECKOUT_TS)
                if la_checkin_ts and not la_checkout_ts:
                    try:
                        day_obj = datetime.strptime(la_record_date, "%Y-%m-%d").date()
                        try:
                            close_tz = ZoneInfo(tz_name)
                        except Exception:
                            close_tz = ZoneInfo("Asia/Calcutta")
                        next_midnight = datetime(day_obj.year, day_obj.month, day_obj.day, 0, 0, 0, tzinfo=close_tz) + timedelta(days=1)
                        cutoff_utc = next_midnight.astimezone(timezone.utc)
                        cutoff_ts = int(cutoff_utc.timestamp())
                        la_base = int(existing_la.get(LA_FIELD_BASE_SECONDS) or 0)
                        sess_secs = max(0, cutoff_ts - la_checkin_ts)
                        total_secs = la_base + sess_secs
                        la_patch = {
                            LA_FIELD_CHECKOUT_TIME: next_midnight.strftime("%H:%M:%S"),
                            LA_FIELD_CHECKOUT_TS: cutoff_ts,
                            LA_FIELD_TOTAL_SECONDS: total_secs,
                        }
                        la_rid = existing_la.get(LA_PRIMARY_FIELD)
                        if la_rid:
                            token = get_access_token()
                            headers = _get_headers(token)
                            requests.patch(
                                f"{_get_base_url()}/{LOGIN_ACTIVITY_ENTITY}({la_rid})",
                                headers=headers, json=la_patch, timeout=20,
                            )
                            # Also update attendance record for that old date
                            old_att = fetch_attendance_record(employee_id, la_record_date)
                            if old_att:
                                att_rid = old_att.get(FIELD_RECORD_ID) or old_att.get("crc6f_table13id")
                                if att_rid:
                                    hours_val = round(total_secs / 3600.0, 2)
                                    att_patch = {
                                        FIELD_CHECKOUT: next_midnight.strftime("%H:%M:%S"),
                                        FIELD_DURATION: str(hours_val),
                                        FIELD_DURATION_INTEXT: format_duration_text(total_secs),
                                    }
                                    if FIELD_STATUS:
                                        att_patch[FIELD_STATUS] = derive_status(total_secs)
                                    try:
                                        update_record(ATTENDANCE_ENTITY, att_rid, att_patch)
                                    except Exception:
                                        pass
                            # Stop task timers
                            try:
                                stop_active_task_entries_for_user(employee_id, cutoff_utc.isoformat())
                            except Exception:
                                pass
                        print(f"[ATTENDANCE-V2] Inline force-closed stale LA record {la_rid} from {la_record_date} for {employee_id}")
                    except Exception as fc_err:
                        print(f"[ATTENDANCE-V2] Inline force-close failed: {fc_err}")
                # Discard stale record regardless of close success
                existing_la = None
        
        if not existing_la and not existing_att:
            # No record for today
            return jsonify({
                "success": True,
                "server_now_utc": now_utc.isoformat(),
                "attendance_date": today_date,
                "has_record": False,
                "is_active_session": False,
                "is_day_locked": False,
                "timing": {"total_seconds_today": 0},
                "status": {"code": None, "label": "Not Checked In"}
            })
        
        # Determine session state from login activity
        checkin_ts_val = None
        checkout_ts_val = None
        base_seconds = 0
        total_seconds_stored = 0
        is_active = False
        
        if existing_la:
            checkin_ts_val = existing_la.get(LA_FIELD_CHECKIN_TS)
            checkout_ts_val = existing_la.get(LA_FIELD_CHECKOUT_TS)
            base_seconds = int(existing_la.get(LA_FIELD_BASE_SECONDS) or 0)
            total_seconds_stored = int(existing_la.get(LA_FIELD_TOTAL_SECONDS) or 0)
            is_active = bool(checkin_ts_val and not checkout_ts_val)
        
        # Calculate current total
        elapsed_seconds = 0
        total_seconds = total_seconds_stored
        
        if is_active and checkin_ts_val:
            elapsed_seconds = max(0, int(now_utc.timestamp()) - int(checkin_ts_val))
            total_seconds = base_seconds + elapsed_seconds
        
        status = derive_status(total_seconds)
        
        # Build response
        response = {
            "success": True,
            "server_now_utc": now_utc.isoformat(),
            "attendance_date": today_date,
            "has_record": True,
            "is_active_session": is_active,
            "is_day_locked": False,
            "timing": {
                "checkin_utc": datetime.fromtimestamp(checkin_ts_val, tz=timezone.utc).isoformat() if checkin_ts_val else None,
                "checkout_utc": datetime.fromtimestamp(checkout_ts_val, tz=timezone.utc).isoformat() if checkout_ts_val else None,
                "last_session_start_utc": datetime.fromtimestamp(checkin_ts_val, tz=timezone.utc).isoformat() if (is_active and checkin_ts_val) else None,
                "elapsed_seconds": elapsed_seconds,
                "total_seconds_today": total_seconds
            },
            "status": {
                "code": status,
                "label": derive_status_label(status),
                "thresholds": {
                    "half_day_seconds": HALF_DAY_SECONDS,
                    "full_day_seconds": FULL_DAY_SECONDS
                }
            },
            "display": {
                "timezone": tz_name
            }
        }
        
        # Add display times
        if checkin_ts_val:
            response["display"]["checkin_local"] = localize_time(
                datetime.fromtimestamp(checkin_ts_val, tz=timezone.utc), tz_name
            )
        if checkout_ts_val:
            response["display"]["checkout_local"] = localize_time(
                datetime.fromtimestamp(checkout_ts_val, tz=timezone.utc), tz_name
            )
        
        if is_active:
            response["display"]["elapsed_text"] = format_duration_text(total_seconds)
        else:
            response["display"]["total_text"] = format_duration_text(total_seconds)
        
        return jsonify(response)
        
    except Exception as e:
        print(f"[ATTENDANCE-V2] Status error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@attendance_v2_bp.route('/<employee_id>/<int:year>/<int:month>', methods=['GET'])
def get_monthly_attendance_v2(employee_id, year, month):
    """Get monthly attendance with server-calculated totals"""
    try:
        employee_id = employee_id.strip().upper()
        tz_name = request.args.get('timezone', 'UTC')
        now_utc = get_server_now_utc()
        
        token = get_access_token()
        headers = _get_headers(token)
        
        _, last_day = monthrange(year, month)
        start_date = f"{year}-{month:02d}-01"
        end_date = f"{year}-{month:02d}-{last_day}"
        
        filter_q = (
            f"$filter={FIELD_EMPLOYEE_ID} eq '{employee_id}' "
            f"and {FIELD_DATE} ge '{start_date}' and {FIELD_DATE} le '{end_date}'"
        )
        url = f"{_get_base_url()}/{ATTENDANCE_ENTITY}?{filter_q}"
        
        resp = requests.get(url, headers=headers, timeout=30)
        records = []
        summary = {"total_present": 0, "total_half_day": 0, "total_absent": 0, "total_hours_worked": 0}
        
        if resp.status_code == 200:
            raw_records = resp.json().get("value", [])
            
            for rec in raw_records:
                date_str = rec.get(FIELD_DATE, "")
                day = int(date_str.split('-')[2]) if date_str and '-' in date_str else 0
                
                duration_hours = 0
                try:
                    duration_hours = float(rec.get(FIELD_DURATION) or 0)
                except:
                    pass
                
                total_seconds = int(duration_hours * 3600)
                status = rec.get(FIELD_STATUS) or derive_status(total_seconds)
                
                record_data = {
                    "day": day,
                    "date": date_str,
                    "status_code": status,
                    "status_label": derive_status_label(status),
                    "checkin": rec.get(FIELD_CHECKIN),
                    "checkout": rec.get(FIELD_CHECKOUT),
                    "total_seconds": total_seconds,
                    "total_text": format_duration_short(total_seconds),
                    "duration_hours": duration_hours
                }
                records.append(record_data)
                
                # Update summary
                if status == "P":
                    summary["total_present"] += 1
                elif status == "HL":
                    summary["total_half_day"] += 1
                else:
                    summary["total_absent"] += 1
                summary["total_hours_worked"] += duration_hours
        
        summary["total_hours_worked"] = round(summary["total_hours_worked"], 2)
        
        return jsonify({
            "success": True,
            "employee_id": employee_id,
            "year": year,
            "month": month,
            "server_now_utc": now_utc.isoformat(),
            "records": records,
            "summary": summary
        })
        
    except Exception as e:
        print(f"[ATTENDANCE-V2] Monthly fetch error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500
