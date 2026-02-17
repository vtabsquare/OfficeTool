# unified_server.py - Combined Attendance & Leave Tracker Backend
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from datetime import datetime
from calendar import monthrange
import random
import string
import traceback
import requests
import os
import hashlib
from dotenv import load_dotenv
from dataverse_helper import create_record, update_record, delete_record, get_access_token

app = Flask(__name__)
CORS(app)
app.config['DEBUG'] = True

# Load environment variables
load_dotenv("id.env")
RESOURCE = os.getenv("RESOURCE")
BASE_URL = RESOURCE.rstrip("/") + "/api/data/v9.2"

# ================== LOGIN CONFIGURATION ==================
LOGIN_TABLE = "crc6f_hr_login_detailses"

# ================== ATTENDANCE CONFIGURATION ==================
ATTENDANCE_ENTITY = "crc6f_table13s"
FIELD_EMPLOYEE_ID = "crc6f_employeeid"
FIELD_DATE = "crc6f_date"
FIELD_CHECKIN = "crc6f_checkin"
FIELD_CHECKOUT = "crc6f_checkout"
FIELD_DURATION = "crc6f_duration"
FIELD_DURATION_INTEXT = "crc6f_duration_intext"
FIELD_ATTENDANCE_ID_CUSTOM = "crc6f_attendanceid"
FIELD_RECORD_ID = "crc6f_table13id"

# ================== LEAVE TRACKER CONFIGURATION ==================
LEAVE_ENTITY = "crc6f_table14s"
# Common leave date fields
FIELD_START_DATE = "crc6f_startdate"
FIELD_END_DATE = "crc6f_enddate"

# ================== EMPLOYEE MASTER CONFIGURATION ==================
# Prefer ENV override if provided; otherwise we'll auto-resolve between common sets
EMPLOYEE_ENTITY_ENV = os.getenv("EMPLOYEE_ENTITY")
EMPLOYEE_ENTITY = EMPLOYEE_ENTITY_ENV or "crc6f_table12s"

# Field mappings for different employee tables
FIELD_MAPS = {
    "crc6f_employees": {  # VTAB Employees
        "id": "crc6f_employeeid1",
        "fullname": "crc6f_fullname",
        "firstname": None,
        "lastname": None,
        "email": "crc6f_email",
        "contact": "crc6f_mobilenumber",
        "address": "crc6f_address",
        "department": None,
        "designation": "crc6f_designation",
        "doj": "crc6f_joindate",
        "active": "crc6f_status"
    },
    "crc6f_table12s": {  # HR_Employee_master
        "id": "crc6f_employeeid",
        "fullname": None,
        "firstname": "crc6f_firstname",
        "lastname": "crc6f_lastname",
        "email": "crc6f_quotahours",  # Actual emails are in quotahours field due to misalignment
        "contact": "crc6f_contactnumber",
        "address": "crc6f_address",
        "department": "crc6f_department",
        "designation": "crc6f_designation",
        "doj": "crc6f_email",  # Actual DOJ dates are in email field due to misalignment
        "active": "crc6f_activeflag"
    }
}

# Cache for resolved entity set name (set after first successful call)
EMPLOYEE_ENTITY_RESOLVED = None

# Store active check-in sessions (in production, use Redis or database)
active_sessions = {}

# ================== SMALL HELPERS ==================
def _build_in_filter(field: str, values: list[str]) -> str:
    safe_vals = [v.replace("'", "''") for v in values if v]
    if not safe_vals:
        return ""
    ors = [f"{field} eq '{v}'" for v in safe_vals]
    return "(" + " or ".join(ors) + ")"


# ================== HELPER FUNCTIONS ==================
def generate_random_attendance_id():
    """Generate random Attendance ID: ATD-H35J6U9"""
    random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=7))
    return f"ATD-{random_part}"

def _probe_entity_set(token: str, entity_set: str) -> bool:
    try:
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "OData-MaxVersion": "4.0",
            "OData-Version": "4.0"
        }
        # Minimal safe query - just get one record without selecting specific fields
        url = f"{RESOURCE}/api/data/v9.2/{entity_set}?$top=1"
        r = requests.get(url, headers=headers, timeout=15)
        return r.status_code == 200
    except Exception:
        return False

def get_employee_entity_set(token: str) -> str:
    global EMPLOYEE_ENTITY_RESOLVED
    if EMPLOYEE_ENTITY_RESOLVED:
        return EMPLOYEE_ENTITY_RESOLVED
    # Candidate order: ENV override, known custom sets
    candidates = [c for c in [EMPLOYEE_ENTITY_ENV, "crc6f_table12s", "crc6f_employees"] if c]
    for cand in candidates:
        if _probe_entity_set(token, cand):
            EMPLOYEE_ENTITY_RESOLVED = cand
            print(f"✅ Resolved employee entity set: {cand}")
            return cand
    # If none succeed, fall back to the first candidate (likely wrong) so error surfaces with URL
    EMPLOYEE_ENTITY_RESOLVED = candidates[0]
    return EMPLOYEE_ENTITY_RESOLVED

def get_field_map(entity_set: str) -> dict:
    """Get field mapping for the given entity set"""
    return FIELD_MAPS.get(entity_set, FIELD_MAPS["crc6f_table12s"])


def generate_leave_id():
    """Generate Leave ID: LVE-XXXXXXX"""
    random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=7))
    leave_id = f"LVE-{random_part}"
    print(f"   🔑 Generated Leave ID: {leave_id}")
    return leave_id


def format_employee_id(emp_number):
    """Format employee ID as EMP0001, EMP0002, etc."""
    emp_id = f"EMP{emp_number:04d}"
    print(f"   👤 Formatted Employee ID: {emp_id}")
    return emp_id


def calculate_leave_days(start_date, end_date):
    """Calculate number of days between start and end date"""
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    days = (end - start).days + 1
    print(f"   📅 Calculated Leave Days: {days} (from {start_date} to {end_date})")
    return days

# ================== AUTH/LOGIN HELPERS ==================
def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def _fetch_login_by_username(username: str, token: str, headers: dict):
    # Escape single quotes for OData filter
    safe_user = (username or '').replace("'", "''")
    url = f"{BASE_URL}/{LOGIN_TABLE}?$top=1&$filter=crc6f_username eq '{safe_user}'"
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    records = resp.json().get("value", [])
    return records[0] if records else None

def _update_login_record(record_id: str, payload: dict, headers: dict):
    record_id = (record_id or '').strip("{}")
    url = f"{BASE_URL}/{LOGIN_TABLE}({record_id})"
    r = requests.patch(url, headers=headers, json=payload)
    r.raise_for_status()
    return True


# ================== ATTENDANCE ROUTES ==================
@app.route('/api/checkin', methods=['POST'])
def checkin():
    """Check-in: Creates attendance record with random ID"""
    try:
        data = request.json
        employee_id = data.get('employee_id')
        
        if not employee_id:
            return jsonify({"success": False, "error": "Employee ID is required"}), 400
        
        if employee_id in active_sessions:
            return jsonify({
                "success": False, 
                "error": "Already checked in. Please check out first."
            }), 400
        
        now = datetime.now()
        formatted_date = now.date().isoformat()
        formatted_time = now.strftime("%H:%M:%S")
        random_attendance_id = generate_random_attendance_id()
        
        record_data = {
            FIELD_EMPLOYEE_ID: employee_id,
            FIELD_DATE: formatted_date,
            FIELD_CHECKIN: formatted_time,
            FIELD_ATTENDANCE_ID_CUSTOM: random_attendance_id
        }
        
        print(f"\n{'='*60}")
        print(f"CHECK-IN REQUEST")
        print(f"{'='*60}")
        print(f"Employee: {employee_id}")
        print(f"Attendance ID: {random_attendance_id}")
        print(f"Date: {formatted_date}")
        print(f"Time: {formatted_time}")
        print(f"Sending to Dataverse...")
        
        created = create_record(ATTENDANCE_ENTITY, record_data)
        
        record_id = (created.get(FIELD_RECORD_ID) or 
                     created.get("cr6f_table13id") or
                     created.get("id"))
        
        if record_id:
            active_sessions[employee_id] = {
                "record_id": record_id,
                "checkin_time": formatted_time,
                "checkin_datetime": now.isoformat(),
                "attendance_id": random_attendance_id
            }
            
            print(f"✅ SUCCESS! Record ID: {record_id}")
            print(f"{'='*60}\n")
            
            return jsonify({
                "success": True,
                "record_id": record_id,
                "attendance_id": random_attendance_id,
                "checkin_time": formatted_time
            })
        else:
            print(f"❌ FAILED: No record ID returned")
            print(f"{'='*60}\n")
            return jsonify({
                "success": False,
                "error": "Failed to create record"
            }), 500
    except Exception as e:
        print(f"\n❌ CHECK-IN ERROR: {str(e)}\n")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ================== AGGREGATED ENDPOINTS ==================
@app.route('/api/leaves/on-leave-today', methods=['GET'])
def on_leave_today():
    """Return active leaves for today, optionally limited to a set of employee IDs."""
    try:
        token = get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "OData-MaxVersion": "4.0",
            "OData-Version": "4.0"
        }
        today = datetime.now().date().isoformat()

        employee_ids = request.args.get('employee_ids', '')
        ids_list = [v.strip().upper() for v in employee_ids.split(',') if v.strip()]

        date_filter = (f"{FIELD_START_DATE} le '{today}' and "
                       f"{FIELD_END_DATE} ge '{today}' and "
                       f"crc6f_status eq 'Approved'")
        emp_filter = _build_in_filter("crc6f_employeeid", ids_list)
        filter_parts = [date_filter]
        if emp_filter:
            filter_parts.append(emp_filter)
        filter_query = "?$filter=" + " and ".join(filter_parts)

        url = f"{RESOURCE}/api/data/v9.2/{LEAVE_ENTITY}{filter_query}&$top=5000"
        resp = requests.get(url, headers=headers)
        if resp.status_code != 200:
            return jsonify({"success": False, "error": f"Failed to fetch: {resp.status_code}", "details": resp.text}), 500
        records = resp.json().get("value", [])
        leaves = []
        for r in records:
            leaves.append({
                "employee_id": r.get("crc6f_employeeid"),
                "leave_type": r.get("crc6f_leavetype"),
                "start_date": r.get("crc6f_startdate"),
                "end_date": r.get("crc6f_enddate"),
                "status": r.get("crc6f_status"),
                "total_days": r.get("crc6f_totaldays"),
            })
        return jsonify({"success": True, "leaves": leaves, "count": len(leaves)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/leaves/team', methods=['GET'])
def leaves_team():
    """Return all leaves for a batch of employee IDs."""
    try:
        token = get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "OData-MaxVersion": "4.0",
            "OData-Version": "4.0"
        }
        employee_ids = request.args.get('employee_ids', '')
        ids_list = [v.strip().upper() for v in employee_ids.split(',') if v.strip()]
        if not ids_list:
            return jsonify({"success": True, "leaves": [], "count": 0})

        emp_filter = _build_in_filter("crc6f_employeeid", ids_list)
        filter_query = "?$filter=" + emp_filter if emp_filter else ""
        url = f"{RESOURCE}/api/data/v9.2/{LEAVE_ENTITY}{filter_query}&$top=5000"
        resp = requests.get(url, headers=headers)
        if resp.status_code != 200:
            return jsonify({"success": False, "error": f"Failed to fetch: {resp.status_code}", "details": resp.text}), 500
        records = resp.json().get("value", [])
        leaves = []
        for r in records:
            leaves.append({
                "leave_id": r.get("crc6f_leaveid"),
                "leave_type": r.get("crc6f_leavetype"),
                "start_date": r.get("crc6f_startdate"),
                "end_date": r.get("crc6f_enddate"),
                "total_days": r.get("crc6f_totaldays"),
                "paid_unpaid": r.get("crc6f_paidunpaid"),
                "status": r.get("crc6f_status"),
                "approved_by": r.get("crc6f_approvedby"),
                "employee_id": r.get("crc6f_employeeid")
            })
        return jsonify({"success": True, "leaves": leaves, "count": len(leaves)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/attendance/team-month', methods=['GET'])
def attendance_team_month():
    """Batch attendance for multiple employees for a given month, including leave overlays."""
    try:
        year = int(request.args.get('year'))
        month = int(request.args.get('month'))
        employee_ids = request.args.get('employee_ids', '')
        ids_list = [v.strip().upper() for v in employee_ids.split(',') if v.strip()]
        if not ids_list:
            return jsonify({"success": True, "records": {}, "count": 0})

        token = get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "OData-MaxVersion": "4.0",
            "OData-Version": "4.0"
        }

        _, last_day = monthrange(year, month)
        start_date = f"{year}-{str(month).zfill(2)}-01"
        end_date = f"{year}-{str(month).zfill(2)}-{str(last_day).zfill(2)}"

        emp_filter = _build_in_filter(FIELD_EMPLOYEE_ID, ids_list)
        date_filter = (f"{FIELD_DATE} ge '{start_date}' and "
                       f"{FIELD_DATE} le '{end_date}'")
        filter_parts = [emp_filter, date_filter]
        filter_query = "?$filter=" + " and ".join([p for p in filter_parts if p])

        url = f"{RESOURCE}/api/data/v9.2/{ATTENDANCE_ENTITY}{filter_query}&$top=5000"
        resp = requests.get(url, headers=headers)
        if resp.status_code != 200:
            return jsonify({"success": False, "error": f"Failed to fetch: {resp.status_code}", "details": resp.text}), 500
        rows = resp.json().get("value", [])

        records = {}
        for r in rows:
            emp_id = (r.get(FIELD_EMPLOYEE_ID) or "").upper()
            if emp_id not in ids_list:
                continue
            date_str = r.get(FIELD_DATE)
            checkin = r.get(FIELD_CHECKIN)
            checkout = r.get(FIELD_CHECKOUT)
            duration_str = r.get(FIELD_DURATION) or "0"
            try:
                duration_hours = float(duration_str)
            except ValueError:
                duration_hours = 0

            if duration_hours >= 9:
                status = "P"
            elif 5 <= duration_hours < 9:
                status = "H"
            else:
                status = "A"

            day_num = None
            if date_str:
                try:
                    day_num = int(date_str.split("-")[-1])
                except Exception:
                    pass

            rec = {
                "date": date_str,
                "day": day_num,
                "checkIn": checkin,
                "checkOut": checkout,
                "duration": duration_hours,
                "duration_text": r.get(FIELD_DURATION_INTEXT),
                "status": status
            }
            records.setdefault(emp_id, []).append(rec)

        # Build day map for each employee for easier overlay work
        per_emp_day_map = {}
        for emp_id, recs in records.items():
            per_emp_day_map[emp_id] = {}
            for rec in recs:
                if rec.get("day"):
                    per_emp_day_map[emp_id][rec["day"]] = rec

        # Overlay leave data (approved -> affect status, pending -> metadata only)
        leave_filter = _build_in_filter("crc6f_employeeid", ids_list)
        leave_url = (
            f"{RESOURCE}/api/data/v9.2/{LEAVE_ENTITY}"
            f"?$filter={leave_filter}"
            f"&$select=crc6f_employeeid,crc6f_leavetype,crc6f_startdate,crc6f_enddate,"
            f"crc6f_status,crc6f_paidunpaid,crc6f_leaveid"
        )
        leaves_resp = requests.get(leave_url, headers=headers)
        if leaves_resp.status_code == 200:
            leaves = leaves_resp.json().get("value", [])
            month_start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            month_end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            for lv in leaves:
                emp_id = (lv.get("crc6f_employeeid") or "").upper()
                if emp_id not in per_emp_day_map:
                    per_emp_day_map[emp_id] = {}
                    records[emp_id] = records.get(emp_id, [])

                lt_raw = (lv.get("crc6f_leavetype") or "").strip()
                if not lt_raw:
                    continue
                status_raw = (lv.get("crc6f_status") or "").strip().lower()
                if status_raw not in ("approved", "pending"):
                    continue

                ltl = lt_raw.lower()
                if "casual" in ltl or ltl == "cl":
                    lt_code = "CL"
                elif "sick" in ltl or ltl == "sl":
                    lt_code = "SL"
                elif "comp" in ltl or ltl in ("co", "compoff", "comp off", "compensatory off"):
                    lt_code = "CO"
                else:
                    continue

                paid_unpaid = lv.get("crc6f_paidunpaid")
                sd = lv.get("crc6f_startdate")
                ed = lv.get("crc6f_enddate") or sd
                try:
                    sd_dt = datetime.strptime(sd, "%Y-%m-%d") if sd else None
                    ed_dt = datetime.strptime(ed, "%Y-%m-%d") if ed else None
                except Exception:
                    sd_dt, ed_dt = None, None
                if not sd_dt:
                    continue
                if not ed_dt:
                    ed_dt = sd_dt

                rng_start = max(sd_dt, month_start_dt)
                rng_end = min(ed_dt, month_end_dt)
                if rng_start > rng_end:
                    continue

                cur = rng_start
                while cur <= rng_end:
                    day_idx = cur.day
                    rec = per_emp_day_map[emp_id].get(day_idx)
                    if not rec:
                        rec = {
                            "date": cur.date().isoformat(),
                            "day": day_idx,
                            "attendance_id": None,
                            "checkIn": None,
                            "checkOut": None,
                            "duration": 0.0,
                            "duration_text": None,
                            "status": "" if status_raw == "pending" else "A",
                        }
                        per_emp_day_map[emp_id][day_idx] = rec
                        records.setdefault(emp_id, []).append(rec)

                    if status_raw == "approved":
                        rec["leaveType"] = lt_raw
                        rec["paid_unpaid"] = paid_unpaid
                        rec["leaveStart"] = sd
                        rec["leaveEnd"] = ed
                        rec["leaveStatus"] = lv.get("crc6f_status")
                        rec["status"] = lt_code
                    else:
                        pending_entry = {
                            "leaveType": lt_raw,
                            "status": lv.get("crc6f_status") or "Pending",
                            "paid_unpaid": paid_unpaid,
                            "start": sd,
                            "end": ed,
                            "leave_id": lv.get("crc6f_leaveid"),
                        }
                        existing = rec.get("pendingLeaves") or []
                        existing.append(pending_entry)
                        rec["pendingLeaves"] = existing
                    cur = cur + timedelta(days=1)

        return jsonify({"success": True, "records": records, "count": len(rows)})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

# ================== LOGIN ROUTE ==================
@app.route("/api/login", methods=["POST"])
def login():
    try:
        data = request.get_json(force=True)
        username = data.get("username")
        password = data.get("password")
        if not username or not password:
            return jsonify({"status": "error", "message": "Username and password required"}), 400

        token = get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "OData-MaxVersion": "4.0",
            "OData-Version": "4.0",
            "Accept": "application/json"
        }

        try:
            record = _fetch_login_by_username(username, token, headers)
        except Exception as e:
            return jsonify({"status": "error", "message": f"Failed to fetch record: {e}"}), 500

        if not record:
            return jsonify({"status": "failed", "message": "Invalid Username or Password"}), 401

        record_id = record.get("crc6f_hr_login_detailsid") or record.get("id")
        status = (record.get("crc6f_user_status") or "Active")
        attempts = int(record.get("crc6f_loginattempts") or 0)

        if status and str(status).lower() == "locked":
            return jsonify({"status": "locked", "message": "Account is locked due to too many failed attempts."}), 403

        hashed_input = _hash_password(password)
        stored_hash = record.get("crc6f_password")

        if hashed_input == stored_hash:
            # Success: reset attempts and set last login
            payload = {
                "crc6f_last_login": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "crc6f_loginattempts": "0",
                "crc6f_user_status": "Active"
            }
            try:
                _update_login_record(record_id, payload, headers)
            except Exception as e:
                return jsonify({"status": "error", "message": f"Failed to update last login: {e}"}), 500
            # Resolve canonical employee_id from Employee master using username/email
            employee_id_value = None
            try:
                entity_set = get_employee_entity_set(token)
                field_map = get_field_map(entity_set)
                email_field = field_map.get('email')
                id_field = field_map.get('id')
                if email_field and id_field:
                    # Escape single quotes in username for OData filter
                    safe_email = (username or '').replace("'", "''")
                    url_emp = f"{BASE_URL}/{entity_set}?$top=1&$select={id_field},{email_field}&$filter={email_field} eq '{safe_email}'"
                    resp_emp = requests.get(url_emp, headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/json",
                        "OData-MaxVersion": "4.0",
                        "OData-Version": "4.0"
                    })
                    if resp_emp.status_code == 200:
                        vals = resp_emp.json().get('value', [])
                        if vals:
                            employee_id_value = vals[0].get(id_field)
            except Exception:
                # Non-fatal; continue without employee_id
                employee_id_value = None
            return jsonify({
                "status": "success",
                "message": f"Welcome, {record.get('crc6f_employeename')}",
                "last_login": payload["crc6f_last_login"],
                "login_attempts": 0,
                "user_status": "Active",
                # Minimal user payload for frontend session
                "user": {
                    "email": record.get("crc6f_username"),
                    "name": record.get("crc6f_employeename"),
                    "employee_id": employee_id_value
                }
            }), 200
        else:
            attempts += 1
            payload = {"crc6f_loginattempts": str(attempts)}
            if attempts >= 3:
                payload["crc6f_user_status"] = "Locked"
            try:
                _update_login_record(record_id, payload, headers)
            except Exception as e:
                return jsonify({"status": "error", "message": f"Failed to update login attempts/status: {e}"}), 500
            if attempts >= 3:
                return jsonify({
                    "status": "locked",
                    "message": "Maximum attempts reached. Your account is now locked.",
                    "login_attempts": attempts
                }), 403
            else:
                return jsonify({
                    "status": "failed",
                    "message": "Invalid Username or Password",
                    "login_attempts": attempts
                }), 401
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/checkout', methods=['POST'])
def checkout():
    """Check-out: Updates record with end time and duration"""
    try:
        data = request.json
        employee_id = data.get('employee_id')
        
        if not employee_id:
            return jsonify({"success": False, "error": "Employee ID is required"}), 400
        
        session = active_sessions.get(employee_id)
        
        if not session:
            return jsonify({
                "success": False,
                "error": "No active check-in found. Please check in first."
            }), 400
        
        now = datetime.now()
        checkout_time_str = now.strftime("%H:%M:%S")
        
        # Calculate duration
        checkin_dt = datetime.fromisoformat(session["checkin_datetime"])
        total_seconds = int((now - checkin_dt).total_seconds())

        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        
        readable_duration = f"{hours} hour(s) {minutes} minute(s)"

        update_data = {
            FIELD_CHECKOUT: checkout_time_str,
            FIELD_DURATION: str(hours),
            FIELD_DURATION_INTEXT: readable_duration
        }

        print(f"\n{'='*60}")
        print(f"CHECK-OUT REQUEST")
        print(f"{'='*60}")
        print(f"Employee: {employee_id}")
        print(f"Record ID: {session['record_id']}")
        print(f"Check-out: {checkout_time_str}")
        print(f"Duration: {readable_duration}")
        print(f"Updating Dataverse...")

        update_record(ATTENDANCE_ENTITY, session["record_id"], update_data)
        
        del active_sessions[employee_id]
        
        print(f"✅ CHECK-OUT SUCCESS!")
        print(f"{'='*60}\n")
        
        return jsonify({
            "success": True,
            "checkout_time": checkout_time_str,
            "duration": readable_duration,
            "total_hours": hours
        })
        
    except Exception as e:
        print(f"\n❌ CHECK-OUT ERROR: {str(e)}\n")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/status/<employee_id>', methods=['GET'])
def get_status(employee_id):
    """Check if employee is currently checked in"""
    if employee_id in active_sessions:
        session = active_sessions[employee_id]
        checkin_dt = datetime.fromisoformat(session["checkin_datetime"])
        elapsed = int((datetime.now() - checkin_dt).total_seconds())
        
        return jsonify({
            "checked_in": True,
            "checkin_time": session["checkin_time"],
            "attendance_id": session.get("attendance_id"),
            "elapsed_seconds": elapsed
        })
    else:
        return jsonify({
            "checked_in": False
        })


@app.route('/api/attendance/<employee_id>/<int:year>/<int:month>', methods=['GET'])
def get_monthly_attendance(employee_id, year, month):
    """Get attendance records for a specific month with status classification"""
    try:
        print(f"\n{'='*70}")
        print(f"🔍 FETCHING ATTENDANCE FOR EMPLOYEE: {employee_id}, {year}-{month:02d}")
        print(f"{'='*70}")
        
        token = get_access_token()
        
        _, last_day = monthrange(year, month)
        start_date = f"{year}-{str(month).zfill(2)}-01"
        end_date = f"{year}-{str(month).zfill(2)}-{str(last_day).zfill(2)}"
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "OData-MaxVersion": "4.0",
            "OData-Version": "4.0"
        }
        
        # Normalize employee ID format
        normalized_emp_id = employee_id.upper().strip()
        if normalized_emp_id.isdigit():
            normalized_emp_id = format_employee_id(int(normalized_emp_id))
        
        print(f"   👤 Normalized Employee ID: {normalized_emp_id}")
        print(f"   📅 Date Range: {start_date} to {end_date}")
        
        filter_query = (f"?$filter={FIELD_EMPLOYEE_ID} eq '{normalized_emp_id}' "
                       f"and {FIELD_DATE} ge '{start_date}' "
                       f"and {FIELD_DATE} le '{end_date}'")
        
        url = f"{RESOURCE}/api/data/v9.2/{ATTENDANCE_ENTITY}{filter_query}"
        
        print(f"   🌐 Sending request to Dataverse: {url}")
        response = requests.get(url, headers=headers)
        
        if response.status_code != 200:
            print(f"❌ Dataverse fetch failed: {response.status_code} {response.text}")
            return jsonify({"success": False, "error": "Failed to fetch records"}), 500
        
        records = response.json().get("value", [])
        print(f"   📊 Found {len(records)} attendance records")
        
        # If no records found, try case-insensitive search
        if len(records) == 0:
            print(f"🔍 No attendance found for {normalized_emp_id}, trying case-insensitive search...")
            try:
                # Try different case variations
                variations = [
                    normalized_emp_id.lower(),
                    normalized_emp_id.title(),
                    employee_id  # original case
                ]
                
                for variation in variations:
                    if variation != normalized_emp_id:
                        filter_query = (f"?$filter={FIELD_EMPLOYEE_ID} eq '{variation}' "
                                       f"and {FIELD_DATE} ge '{start_date}' "
                                       f"and {FIELD_DATE} le '{end_date}'")
                        url = f"{RESOURCE}/api/data/v9.2/{ATTENDANCE_ENTITY}{filter_query}"
                        response = requests.get(url, headers=headers)
                        
                        if response.status_code == 200:
                            records = response.json().get("value", [])
                            if records:
                                print(f"✅ Found {len(records)} records with variation: {variation}")
                                break
            except Exception as e:
                print(f"⚠️ Case-insensitive search failed: {str(e)}")
        
        formatted_records = []
        
        for r in records:
            date_str = r.get(FIELD_DATE)
            checkin = r.get(FIELD_CHECKIN)
            checkout = r.get(FIELD_CHECKOUT)
            duration_str = r.get(FIELD_DURATION) or "0"
            
            try:
                duration_hours = float(duration_str)
            except ValueError:
                duration_hours = 0
            
            # 🟡 Attendance classification based on hours
            if duration_hours >= 9:
                status = "P"  # Present
            elif 5 <= duration_hours < 9:
                status = "H"  # Half Day
            else:
                status = "A"  # Absent (< 5 hours)
            
            # Extract day number for frontend mapping
            day_num = None
            if date_str:
                try:
                    day_num = int(date_str.split("-")[-1])
                except (ValueError, IndexError):
                    pass
            
            formatted_records.append({
                "date": date_str,
                "day": day_num,
                "attendance_id": r.get(FIELD_ATTENDANCE_ID_CUSTOM),
                "checkIn": checkin,
                "checkOut": checkout,
                "duration": duration_hours,
                "duration_text": r.get(FIELD_DURATION_INTEXT),
                "status": status
            })
        
        print(f"✅ Successfully formatted {len(formatted_records)} attendance records")
        print(f"{'='*70}\n")
        
        return jsonify({
            "success": True,
            "records": formatted_records,
            "count": len(formatted_records)
        })
            
    except Exception as e:
        print(f"❌ Error fetching monthly attendance: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ================== LEAVE TRACKER ROUTES ==================
@app.route('/')
def index():
    """Home page - can redirect to leave tracker"""
    print("📄 Serving index page")
    return render_template("my_leave.html")


@app.route('/apply_leave_page')
def apply_leave_page():
    """Apply leave page"""
    print("📄 Serving apply leave page")
    return render_template("apply_leave.html")


@app.route('/apply_leave', methods=['POST'])
def apply_leave():
    """Submit leave application"""
    print("\n" + "=" * 70)
    print("🚀 LEAVE APPLICATION REQUEST RECEIVED")
    print("=" * 70)

    try:
        print("\n📥 Step 1: Receiving request data...")

        if not request.is_json:
            print("   ❌ Request is not JSON!")
            return jsonify({"error": "Request must be JSON"}), 400

        data = request.get_json()
        print(f"   ✅ Received JSON data:\n   {data}")

        leave_type = data.get("leave_type")
        start_date = data.get("start_date")
        end_date = data.get("end_date")
        applied_by_raw = data.get("applied_by")
        paid_unpaid = data.get("paid_unpaid", "Paid")
        status = data.get("status", "Pending")
        reason = data.get("reason", "")

        # Format employee ID
        if applied_by_raw:
            if applied_by_raw.isdigit():
                applied_by = format_employee_id(int(applied_by_raw))
            elif applied_by_raw.upper().startswith("EMP"):
                applied_by = applied_by_raw.upper()
            else:
                applied_by = "EMP0001"
        else:
            applied_by = "EMP0001"

        # Validate required fields
        missing_fields = [f for f in ["leave_type", "start_date", "end_date", "applied_by"]
                          if not data.get(f)]
        if missing_fields:
            return jsonify({"error": f"Missing required fields: {', '.join(missing_fields)}"}), 400

        leave_id = generate_leave_id()
        leave_days = calculate_leave_days(start_date, end_date)

        record_data = {
            "crc6f_leaveid": leave_id,
            "crc6f_leavetype": leave_type,
            "crc6f_startdate": start_date,
            "crc6f_enddate": end_date,
            "crc6f_paidunpaid": paid_unpaid,
            "crc6f_status": status,
            "crc6f_totaldays": str(leave_days),
            "crc6f_employeeid": applied_by,
            "crc6f_approvedby": "",
        }

        print(f"📦 Dataverse Record Data: {record_data}")
        created_record = create_record(LEAVE_ENTITY, record_data)
        print(f"✅ Record Created: {created_record}")

        response_data = {
            "message": f"Leave applied successfully for {applied_by}",
            "leave_id": leave_id,
            "leave_days": leave_days,
            "leave_details": created_record
        }

        print("✅ LEAVE APPLICATION SUCCESSFUL!\n")
        return jsonify(response_data), 200

    except Exception as e:
        print("\n❌ ERROR OCCURRED IN LEAVE APPLICATION")
        traceback.print_exc()
        return jsonify({
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@app.route('/api/leaves/<employee_id>', methods=['GET'])
def get_employee_leaves(employee_id):
    """Get all leave records for a specific employee"""
    try:
        print(f"\n{'='*70}")
        print(f"🔍 FETCHING LEAVE HISTORY FOR EMPLOYEE: {employee_id}")
        print(f"{'='*70}")
        
        token = get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "OData-MaxVersion": "4.0",
            "OData-Version": "4.0"
        }
        
        # Normalize employee ID format
        normalized_emp_id = employee_id.upper().strip()
        if normalized_emp_id.isdigit():
            normalized_emp_id = format_employee_id(int(normalized_emp_id))
        
        print(f"   👤 Normalized Employee ID: {normalized_emp_id}")
        
        # Try fetching by employee_id first
        filter_query = f"?$filter=crc6f_employeeid eq '{normalized_emp_id}'"
        url = f"{RESOURCE}/api/data/v9.2/{LEAVE_ENTITY}{filter_query}"
        
        print(f"   🌐 Sending request to Dataverse: {url}")
        response = requests.get(url, headers=headers)
        
        if response.status_code != 200:
            print(f"❌ Failed to fetch leaves: {response.status_code} {response.text}")
            return jsonify({"success": False, "error": "Failed to fetch leave records"}), 500
        
        records = response.json().get("value", [])
        print(f"   📊 Found {len(records)} leave records")
        
        # If no records found, try case-insensitive search
        if len(records) == 0:
            print(f"🔍 No leaves found for {normalized_emp_id}, trying case-insensitive search...")
            try:
                # Try different case variations
                variations = [
                    normalized_emp_id.lower(),
                    normalized_emp_id.title(),
                    employee_id  # original case
                ]
                
                for variation in variations:
                    if variation != normalized_emp_id:
                        filter_query = f"?$filter=crc6f_employeeid eq '{variation}'"
                        url = f"{RESOURCE}/api/data/v9.2/{LEAVE_ENTITY}{filter_query}"
                        response = requests.get(url, headers=headers)
                        
                        if response.status_code == 200:
                            records = response.json().get("value", [])
                            if records:
                                print(f"✅ Found {len(records)} records with variation: {variation}")
                                break
            except Exception as e:
                print(f"⚠️ Case-insensitive search failed: {str(e)}")
        
        # If still no records and employee_id looks like an email, try to resolve it
        if len(records) == 0 and '@' in employee_id:
            print(f"🔍 No leaves found for {employee_id}, attempting email lookup...")
            try:
                # Fetch employee by email to get actual employee_id
                entity_set = get_employee_entity_set(token)
                field_map = get_field_map(entity_set)
                email_field = field_map.get('email')
                id_field = field_map.get('id')
                
                if email_field and id_field:
                    safe_email = employee_id.replace("'", "''")
                    emp_url = f"{RESOURCE}/api/data/v9.2/{entity_set}?$filter={email_field} eq '{safe_email}'&$select={id_field}"
                    emp_response = requests.get(emp_url, headers=headers)
                    
                    if emp_response.status_code == 200:
                        emp_records = emp_response.json().get("value", [])
                        if emp_records:
                            actual_emp_id = emp_records[0].get(id_field)
                            if actual_emp_id:
                                print(f"✅ Resolved email {employee_id} to employee ID {actual_emp_id}")
                                # Retry fetching leaves with actual employee_id
                                filter_query = f"?$filter=crc6f_employeeid eq '{actual_emp_id}'"
                                url = f"{RESOURCE}/api/data/v9.2/{LEAVE_ENTITY}{filter_query}"
                                response = requests.get(url, headers=headers)
                                if response.status_code == 200:
                                    records = response.json().get("value", [])
                                    print(f"📊 Found {len(records)} records after email resolution")
            except Exception as e:
                print(f"⚠️ Email lookup failed: {str(e)}")
        
        formatted_leaves = []
        
        for r in records:
            formatted_leaves.append({
                "leave_id": r.get("crc6f_leaveid"),
                "leave_type": r.get("crc6f_leavetype"),
                "start_date": r.get("crc6f_startdate"),
                "end_date": r.get("crc6f_enddate"),
                "total_days": r.get("crc6f_totaldays"),
                "paid_unpaid": r.get("crc6f_paidunpaid"),
                "status": r.get("crc6f_status"),
                "approved_by": r.get("crc6f_approvedby"),
                "employee_id": r.get("crc6f_employeeid")
            })
        
        print(f"✅ Successfully formatted {len(formatted_leaves)} leave records")
        print(f"{'='*70}\n")
        
        return jsonify({
            "success": True,
            "leaves": formatted_leaves,
            "count": len(formatted_leaves)
        })
        
    except Exception as e:
        print(f"❌ Error fetching leaves: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/test_connection', methods=['GET'])
def test_connection():
    """Test Dataverse connection"""
    try:
        test_record = {
            "crc6f_employeeid": format_employee_id(1),
            "crc6f_leavetype": "Test Leave",
            "crc6f_paidunpaid": "Paid",
            "crc6f_startdate": "2025-10-14",
            "crc6f_enddate": "2025-10-15",
            "crc6f_status": "Pending",
            "crc6f_totaldays": "2",
            "crc6f_leaveid": generate_leave_id(),
            "crc6f_approvedby": "System"
        }
        result = create_record(LEAVE_ENTITY, test_record)
        return jsonify({"success": True, "dataverse_result": result}), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


# ================== UTILITY ROUTES ==================
@app.route('/ping', methods=['GET'])
def ping():
    """Health check endpoint"""
    return jsonify({
        "message": "Unified Backend Server is running ✅",
        "services": ["attendance", "leave_tracker", "asset_management", "employee_master"],
        "timestamp": datetime.now().isoformat()
    }), 200


@app.route('/api/info', methods=['GET'])
def api_info():
    """API information endpoint"""
    return jsonify({
        "server": "Unified HR Management Backend",
        "version": "2.0.0",
        "endpoints": {
            "attendance": {
                "checkin": "POST /api/checkin",
                "checkout": "POST /api/checkout",
                "status": "GET /api/status/<employee_id>",
                "monthly": "GET /api/attendance/<employee_id>/<year>/<month>"
            },
            "leave": {
                "apply": "POST /apply_leave",
                "history": "GET /api/leaves/<employee_id>",
                "test": "GET /test_connection"
            },
            "employees": {
                "list": "GET /api/employees",
                "create": "POST /api/employees",
                "bulk_upload": "POST /api/employees/bulk"
            },
            "assets": {
                "list": "GET /assets",
                "create": "POST /assets",
                "update": "PATCH /assets/update/<asset_id>",
                "delete": "DELETE /assets/delete/<asset_id>"
            },
            "utility": {
                "ping": "GET /ping",
                "info": "GET /api/info"
            }
        }
    }), 200


# ================== EMPLOYEE MASTER ROUTES ==================
@app.route('/api/employees', methods=['GET'])
def list_employees():
    try:
        token = get_access_token()
        entity_set = get_employee_entity_set(token)
        field_map = get_field_map(entity_set)
        
        # pagination params
        page = int(request.args.get('page', 1))
        page_size = int(request.args.get('pageSize', 5))
        if page < 1:
            page = 1
        if page_size < 1:
            page_size = 5
        skip = (page - 1) * page_size
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "OData-MaxVersion": "4.0",
            "OData-Version": "4.0"
        }
        
        # Build $select from available fields in this entity
        select_list = [field_map[k] for k in ['id', 'fullname', 'firstname', 'lastname', 'email', 'contact', 'address', 'department', 'designation', 'doj', 'active'] if field_map.get(k)]
        select_fields = f"$select={','.join(select_list)}"
        # Fetch all records (or a large number) to support pagination
        # Using a high limit to get all records since Dataverse doesn't support $skip well
        fetch_count = 5000  # Fetch up to 5000 records (adjust if you have more employees)
        top = f"$top={fetch_count}"
        # Order by creation date descending to show newest first
        orderby = f"$orderby=createdon desc"
        url = f"{RESOURCE}/api/data/v9.2/{entity_set}?{select_fields}&{top}&{orderby}"
        resp = requests.get(url, headers=headers)
        if resp.status_code != 200:
            # If 400, try a simpler request without $count/$orderby which can fail on some orgs
            if resp.status_code == 400:
                simple_url = f"{RESOURCE}/api/data/v9.2/{entity_set}?{select_fields}&$top={fetch_count}"
                simple_headers = {
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                    "OData-MaxVersion": "4.0",
                    "OData-Version": "4.0"
                }
                simple_resp = requests.get(simple_url, headers=simple_headers)
                if simple_resp.status_code == 200:
                    body = simple_resp.json()
                    all_records = body.get("value", [])
                    # Slice for requested page
                    start_idx = skip
                    end_idx = start_idx + page_size
                    records = all_records[start_idx:end_idx]
                    items = []
                    for r in records:
                        # Extract name fields based on table structure
                        if field_map['fullname']:
                            fullname = r.get(field_map['fullname'], '')
                            parts = fullname.split(' ', 1)
                            first_name = parts[0] if parts else ''
                            last_name = parts[1] if len(parts) > 1 else ''
                        else:
                            first_name = r.get(field_map['firstname'], '')
                            last_name = r.get(field_map['lastname'], '')
                        
                        items.append({
                            "employee_id": r.get(field_map['id']),
                            "first_name": first_name,
                            "last_name": last_name,
                            "email": r.get(field_map['email']),
                            "contact_number": r.get(field_map['contact']),
                            "address": r.get(field_map['address']),
                            "department": r.get(field_map['department']),
                            "designation": r.get(field_map['designation']),
                            "doj": r.get(field_map['doj']),
                            "active": r.get(field_map['active'])
                        })
                    return jsonify({
                        "success": True,
                        "employees": items,
                        "count": len(items),
                        "total": len(all_records),
                        "page": page,
                        "pageSize": page_size,
                        "note": "Client-side pagination (no $skip support)",
                        "entitySet": entity_set
                    })
            # Bubble up Dataverse error details for debugging
            try:
                err_body = resp.json()
            except Exception:
                err_body = resp.text
            return jsonify({
                "success": False,
                "error": f"Failed to fetch employees: {resp.status_code}",
                "details": err_body,
                "requestUrl": url,
                "entitySet": entity_set
            }), 500
        body = resp.json()
        all_records = body.get("value", [])
        total_count = len(all_records)  # Total fetched so far
        
        # Slice records for the requested page (client-side pagination)
        start_idx = skip
        end_idx = start_idx + page_size
        records = all_records[start_idx:end_idx]
        
        items = []
        for r in records:
            # Extract name fields based on table structure
            if field_map['fullname']:
                fullname = r.get(field_map['fullname'], '')
                parts = fullname.split(' ', 1)
                first_name = parts[0] if parts else ''
                last_name = parts[1] if len(parts) > 1 else ''
            else:
                first_name = r.get(field_map['firstname'], '')
                last_name = r.get(field_map['lastname'], '')
            
            items.append({
                "employee_id": r.get(field_map['id']),
                "first_name": first_name,
                "last_name": last_name,
                "email": r.get(field_map['email']),
                "contact_number": r.get(field_map['contact']),
                "address": r.get(field_map['address']),
                "department": r.get(field_map['department']),
                "designation": r.get(field_map['designation']),
                "doj": r.get(field_map['doj']),
                "active": r.get(field_map['active'])
            })
        return jsonify({
            "success": True,
            "employees": items,
            "count": len(items),
            "total": total_count,
            "page": page,
            "pageSize": page_size,
            "entitySet": entity_set
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/employees', methods=['POST'])
def create_employee():
    try:
        token = get_access_token()
        entity_set = get_employee_entity_set(token)
        field_map = get_field_map(entity_set)
        data = request.get_json(force=True)
        
        # Build payload based on table structure
        payload = {}
        
        if field_map['id']:
            payload[field_map['id']] = data.get("employee_id")
        
        # Handle name fields
        if field_map['fullname']:
            # Combine first and last name into fullname
            first = data.get("first_name", "")
            last = data.get("last_name", "")
            payload[field_map['fullname']] = f"{first} {last}".strip()
        else:
            if field_map['firstname']:
                payload[field_map['firstname']] = data.get("first_name")
            if field_map['lastname']:
                payload[field_map['lastname']] = data.get("last_name")
        
        # Other fields
        if field_map['email']:
            payload[field_map['email']] = data.get("email")
        if field_map['contact']:
            payload[field_map['contact']] = data.get("contact_number")
        if field_map['address']:
            payload[field_map['address']] = data.get("address")
        if field_map['department']:
            payload[field_map['department']] = data.get("department")
        if field_map['designation']:
            payload[field_map['designation']] = data.get("designation")
        if field_map['doj']:
            payload[field_map['doj']] = data.get("doj")
        if field_map['active']:
            # Convert boolean to string format expected by Dataverse
            active_value = data.get("active")
            if isinstance(active_value, bool):
                payload[field_map['active']] = "Active" if active_value else "Inactive"
            else:
                # Handle string values
                payload[field_map['active']] = "Active" if str(active_value).lower() in ['true', '1', 'active'] else "Inactive"
        
        created = create_record(entity_set, payload)
        return jsonify({"success": True, "employee": created, "entitySet": entity_set}), 201
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


def _extract_record_id(record: dict, prefer_keys=None) -> str:
    """Best-effort extraction of Dataverse primary GUID field from a record."""
    if not record:
        return None
    prefer_keys = prefer_keys or []
    # Prefer known conventional primary key names
    for k in prefer_keys:
        if k in record and record[k]:
            return record[k]
    # Fallback: pick the first field name that ends with 'id' and looks like a GUID
    for k, v in record.items():
        if isinstance(k, str) and k.lower().endswith('id') and isinstance(v, str) and len(v) >= 30:
            return v
    # Last resort: None
    return None


@app.route('/api/employees/<employee_id>', methods=['PUT'])
def update_employee_api(employee_id):
    try:
        token = get_access_token()
        entity_set = get_employee_entity_set(token)
        field_map = get_field_map(entity_set)
        data = request.get_json(force=True)

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "OData-MaxVersion": "4.0",
            "OData-Version": "4.0"
        }
        # Find the record by business employee id field
        filter_q = f"?$filter={field_map['id']} eq '{employee_id}'&$top=1"
        url = f"{RESOURCE}/api/data/v9.2/{entity_set}{filter_q}"
        resp = requests.get(url, headers=headers)
        if resp.status_code != 200:
            return jsonify({"success": False, "error": "Failed to find employee for update", "details": resp.text}), 500
        values = resp.json().get('value', [])
        if not values:
            return jsonify({"success": False, "error": "Employee not found"}), 404
        record = values[0]

        # Build update payload using field map
        payload = {}
        if field_map['fullname']:
            first = data.get("first_name", "")
            last = data.get("last_name", "")
            payload[field_map['fullname']] = f"{first} {last}".strip()
        else:
            if field_map['firstname']:
                payload[field_map['firstname']] = data.get("first_name")
            if field_map['lastname']:
                payload[field_map['lastname']] = data.get("last_name")
        if field_map['email']:
            payload[field_map['email']] = data.get("email")
        if field_map['contact']:
            payload[field_map['contact']] = data.get("contact_number")
        if field_map['address']:
            payload[field_map['address']] = data.get("address")
        if field_map['department']:
            payload[field_map['department']] = data.get("department")
        if field_map['designation']:
            payload[field_map['designation']] = data.get("designation")
        if field_map['active']:
            active_value = data.get("active")
            if isinstance(active_value, bool):
                payload[field_map['active']] = "Active" if active_value else "Inactive"
            else:
                payload[field_map['active']] = "Active" if str(active_value).lower() in ['true', '1', 'active'] else "Inactive"

        # Try to extract the primary record id
        prefer_keys = [f"{entity_set[:-1]}id", f"{entity_set}id"]  # heuristic
        record_id = _extract_record_id(record, prefer_keys)
        if not record_id:
            return jsonify({"success": False, "error": "Unable to resolve record ID for update"}), 500

        update_record(entity_set, record_id, payload)
        return jsonify({"success": True, "employee": {"employee_id": employee_id}})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/employees/<employee_id>', methods=['DELETE'])
def delete_employee_api(employee_id):
    try:
        token = get_access_token()
        entity_set = get_employee_entity_set(token)
        field_map = get_field_map(entity_set)

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "OData-MaxVersion": "4.0",
            "OData-Version": "4.0"
        }
        # Find record by business id
        filter_q = f"?$filter={field_map['id']} eq '{employee_id}'&$top=1"
        url = f"{RESOURCE}/api/data/v9.2/{entity_set}{filter_q}"
        resp = requests.get(url, headers=headers)
        if resp.status_code != 200:
            return jsonify({"success": False, "error": "Failed to find employee for deletion", "details": resp.text}), 500
        values = resp.json().get('value', [])
        if not values:
            return jsonify({"success": False, "error": "Employee not found"}), 404
        record = values[0]

        prefer_keys = [f"{entity_set[:-1]}id", f"{entity_set}id"]
        record_id = _extract_record_id(record, prefer_keys)
        if not record_id:
            return jsonify({"success": False, "error": "Unable to resolve record ID for deletion"}), 500

        delete_record(entity_set, record_id)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/employees/bulk', methods=['POST'])
def bulk_create_employees():
    """Bulk upload employees from CSV data"""
    try:
        token = get_access_token()
        entity_set = get_employee_entity_set(token)
        field_map = get_field_map(entity_set)
        data = request.get_json(force=True)
        
        employees = data.get('employees', [])
        if not employees:
            return jsonify({"success": False, "error": "No employees provided"}), 400
        
        created_count = 0
        errors = []
        
        print(f"\n📤 Bulk upload: Processing {len(employees)} employees")
        print(f"Entity Set: {entity_set}")
        print(f"Field Map: {field_map}")
        
        for idx, emp_data in enumerate(employees):
            try:
                # Build payload based on table structure
                payload = {}
                
                if field_map['id']:
                    payload[field_map['id']] = emp_data.get("employee_id")
                
                # Handle name fields
                if field_map['fullname']:
                    first = emp_data.get("first_name", "")
                    last = emp_data.get("last_name", "")
                    payload[field_map['fullname']] = f"{first} {last}".strip()
                else:
                    if field_map['firstname']:
                        payload[field_map['firstname']] = emp_data.get("first_name")
                    if field_map['lastname']:
                        payload[field_map['lastname']] = emp_data.get("last_name")
                
                # Other fields
                if field_map['email']:
                    payload[field_map['email']] = emp_data.get("email")
                if field_map['contact']:
                    payload[field_map['contact']] = emp_data.get("contact_number")
                if field_map['address']:
                    payload[field_map['address']] = emp_data.get("address")
                if field_map['department']:
                    payload[field_map['department']] = emp_data.get("department")
                if field_map['designation']:
                    payload[field_map['designation']] = emp_data.get("designation")
                if field_map['doj']:
                    payload[field_map['doj']] = emp_data.get("doj")
                if field_map['active']:
                    # Convert boolean to string format expected by Dataverse
                    active_value = emp_data.get("active")
                    if isinstance(active_value, bool):
                        payload[field_map['active']] = "Active" if active_value else "Inactive"
                    else:
                        # Handle string values
                        payload[field_map['active']] = "Active" if str(active_value).lower() in ['true', '1', 'active'] else "Inactive"
                
                print(f"\n📝 Row {idx + 1}: {emp_data.get('employee_id')} - {emp_data.get('first_name')} {emp_data.get('last_name')}")
                print(f"   Payload: {payload}")
                
                create_record(entity_set, payload)
                print(f"   ✅ Success")
                created_count += 1
            except Exception as e:
                error_msg = f"Row {idx + 1} ({emp_data.get('employee_id')}): {str(e)}"
                print(f"   ❌ Error: {error_msg}")
                errors.append(error_msg)
        
        response = {
            "success": True,
            "count": created_count,
            "total": len(employees),
            "entitySet": entity_set
        }
        
        if errors:
            response["errors"] = errors
            response["message"] = f"Uploaded {created_count} out of {len(employees)} employees. Some records failed."
        else:
            response["message"] = f"Successfully uploaded all {created_count} employees to Dataverse!"
        
        return jsonify(response), 201
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# import os
# import requests
# from flask import Flask, request, jsonify
# from flask_cors import CORS
# from dotenv import load_dotenv
# from dataverse_helper import get_access_token

# # -------------------- Load Environment --------------------
# load_dotenv("id.env")

# # -------------------- Flask App --------------------
# app = Flask(__name__)
# CORS(app)

# # -------------------- Dataverse Configuration --------------------
# RESOURCE = os.getenv("RESOURCE")
API_BASE = f"{RESOURCE}/api/data/v9.2"
ENTITY_NAME = "crc6f_hr_assetdetailses"  # logical table name

# -------------------- CRUD Functions --------------------
def get_all_assets():
    token = get_access_token()
    url = f"{API_BASE}/{ENTITY_NAME}"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        return res.json().get("value", [])
    raise Exception(f"Error fetching assets: {res.status_code} - {res.text}")

def get_asset_by_empid(emp_id):
    token = get_access_token()
    url = f"{API_BASE}/{ENTITY_NAME}?$filter=crc6f_employeeid eq '{emp_id}'"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        data = res.json().get("value", [])
        return data[0] if data else None
    raise Exception(f"Error fetching asset by emp id: {res.status_code} - {res.text}")

def get_asset_by_assetid(asset_id):
    token = get_access_token()
    # Query by the UI-generated asset id field crc6f_assetid
    url = f"{API_BASE}/{ENTITY_NAME}?$filter=crc6f_assetid eq '{asset_id}'"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        data = res.json().get("value", [])
        return data[0] if data else None
    raise Exception(f"Error fetching asset by asset id: {res.status_code} - {res.text}")

def create_asset(data):
    # Basic validation server-side
    assigned_to = data.get("crc6f_assignedto", "").strip()
    emp_id = data.get("crc6f_employeeid", "").strip()
    asset_id = data.get("crc6f_assetid", "").strip()

    if not assigned_to or not emp_id:
        return {"error": "Assigned To (crc6f_assignedto) and Employee ID (crc6f_employeeid) are required."}, 400

    if not asset_id:
        return {"error": "Asset ID (crc6f_assetid) is required."}, 400

    # check duplicate asset id
    existing = get_asset_by_assetid(asset_id)
    if existing:
        return {"error": f"Asset with id {asset_id} already exists."}, 409

    token = get_access_token()
    url = f"{API_BASE}/{ENTITY_NAME}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }
    res = requests.post(url, headers=headers, json=data)
    if res.status_code in (200, 201):
        return res.json()
    raise Exception(f"Error creating asset: {res.status_code} - {res.text}")

def update_asset_by_assetid(asset_id, data):
    # FIXED: use the record GUID from Dataverse query and PATCH the correct record URL
    asset = get_asset_by_assetid(asset_id)
    if not asset:
        raise Exception("Asset not found for update.")
    # crc6f_hr_assetdetailsid should be the record GUID field - use it directly
    record_id = asset.get("crc6f_hr_assetdetailsid")
    if not record_id:
        raise Exception("Record id missing from Dataverse response; cannot update.")
    token = get_access_token()
    url = f"{API_BASE}/{ENTITY_NAME}({record_id})"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "If-Match": "*"
    }
    res = requests.patch(url, headers=headers, json=data)
    # Dataverse returns 204 (No Content) for successful patch
    if res.status_code in (204, 1223):
        return {"message": "Asset updated successfully"}
    # Some environments may return other statuses; include text for debugging
    raise Exception(f"Error updating asset: {res.status_code} - {res.text}")

def delete_asset_by_assetid(asset_id):
    # FIXED: use the record GUID from Dataverse query and DELETE the correct record URL
    asset = get_asset_by_assetid(asset_id)
    if not asset:
        raise Exception("Asset not found for deletion.")
    record_id = asset.get("crc6f_hr_assetdetailsid")
    if not record_id:
        raise Exception("Record id missing from Dataverse response; cannot delete.")
    token = get_access_token()
    url = f"{API_BASE}/{ENTITY_NAME}({record_id})"
    headers = {"Authorization": f"Bearer {token}", "If-Match": "*"}
    res = requests.delete(url, headers=headers)
    if res.status_code == 204:
        return {"message": "Asset deleted successfully"}
    raise Exception(f"Error deleting asset: {res.status_code} - {res.text}")

# -------------------- Flask Routes --------------------
@app.route("/assets", methods=["GET"])
def fetch_assets():
    try:
        data = get_all_assets()
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/assets", methods=["POST"])
def add_asset():
    try:
        data = request.json
        result = create_asset(data)
        # create_asset might return (dict, status) tuple for validation errors
        if isinstance(result, tuple):
            return jsonify(result[0]), result[1]
        return jsonify(result), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Update by asset id (crc6f_assetid)
@app.route("/assets/update/<asset_id>", methods=["PATCH"])
def edit_asset(asset_id):
    try:
        data = request.json
        result = update_asset_by_assetid(asset_id, data)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Delete by asset id
@app.route("/assets/delete/<asset_id>", methods=["DELETE"])
def remove_asset(asset_id):
    try:
        result = delete_asset_by_assetid(asset_id)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
# ================== MAIN ==================
if __name__ == '__main__':
    print("\n" + "🚀 " * 30)
    print("UNIFIED SERVER - HR MANAGEMENT SYSTEM")
    print("🚀 " * 30 + "\n")
    print("=" * 80)
    print("Server Configuration:")
    print("=" * 80)
    print(f"  Host: 0.0.0.0 (accessible from network)")
    print(f"  Port: 5000")
    print(f"  Debug Mode: ON")
    print("=" * 80)
    print("\nAvailable Services:")
    print("  ✅ Attendance Management (Check-in/Check-out)")
    print("  ✅ Leave Tracker (Apply Leave)")
    print("  ✅ Asset Management (CRUD Operations)")
    print("  ✅ Employee Master (CRUD & Bulk Upload)")
    print("=" * 80)
    print("\nEndpoints:")
    print("  📍 http://localhost:5000/ping - Health check")
    print("  📍 http://localhost:5000/api/info - API documentation")
    print("  📍 http://localhost:5000/api/checkin - Check-in")
    print("  📍 http://localhost:5000/api/checkout - Check-out")
    print("  📍 http://localhost:5000/apply_leave - Apply leave")
    print("=" * 80 + "\n")
    
    app.run(debug=True, host='0.0.0.0', port=5000)