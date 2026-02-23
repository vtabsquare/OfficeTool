# ai_dataverse_service.py - Dataverse data layer for AI assistant
import os
import requests
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from dataverse_helper import get_access_token

# Load from environment
RESOURCE = os.getenv("RESOURCE", "").rstrip("/")
BASE_URL = f"{RESOURCE}/api/data/v9.2" if RESOURCE else ""
TASKS_ENTITY = os.getenv("TASKS_ENTITY", "crc6f_hr_taskdetailses")
TIMESHEET_ENTITY = os.getenv("TIMESHEET_ENTITY", "crc6f_hr_timesheets")
LOGIN_ACTIVITY_ENTITY = os.getenv("LOGIN_ACTIVITY_ENTITY", "crc6f_hr_loginactivitytbs")

# Entity configurations (from unified_server.py)
ENTITIES = {
    "employees": "crc6f_table12s",
    "attendance": "crc6f_table13s",
    "leave": "crc6f_table14s",
    "leave_balance": "crc6f_hr_leavemangements",
    "assets": "crc6f_hr_assetdetailses",
    "holidays": "crc6f_hr_holidayses",
    "clients": "crc6f_hr_clients",
    "projects": "crc6f_hr_projectheaders",
    "interns": "crc6f_hr_interndetailses",
    "login": "crc6f_hr_login_detailses",
    "inbox": "crc6f_hr_inboxes",
    "tasks": TASKS_ENTITY,
    "timesheets": TIMESHEET_ENTITY,
    "login_activity": LOGIN_ACTIVITY_ENTITY,
}


def _normalize_access_level(value: Optional[str]) -> str:
    level = (value or "").strip().upper()
    if level in {"L1", "L2", "L3"}:
        return level
    if level in {"ADMIN", "SUPERADMIN"}:
        return "L3"
    if level in {"MANAGER"}:
        return "L2"
    return "L1"


def _derive_role_flags(user_meta: dict) -> Dict[str, bool]:
    access_level = _normalize_access_level(
        user_meta.get("access_level")
        or user_meta.get("role")
        or (user_meta.get("designation") or "")
    )
    is_admin = bool(user_meta.get("is_admin"))
    is_manager = bool(user_meta.get("is_manager")) or access_level == "L2"
    is_l3 = is_admin or access_level == "L3"
    is_l2 = is_l3 or is_manager
    return {
        "access_level": access_level,
        "is_admin": is_admin,
        "is_l3": is_l3,
        "is_l2": is_l2,
        "is_l1": True,
    }


def _get_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "OData-MaxVersion": "4.0",
        "OData-Version": "4.0",
    }


def _fetch_entity(entity: str, token: str, select: str = "", filter_query: str = "", top: int = 100) -> List[dict]:
    """Generic fetch from Dataverse entity."""
    try:
        url = f"{BASE_URL}/{entity}"
        params = []
        if select:
            params.append(f"$select={select}")
        if filter_query:
            params.append(f"$filter={filter_query}")
        params.append(f"$top={top}")
        
        if params:
            url += "?" + "&".join(params)
        
        resp = requests.get(url, headers=_get_headers(token), timeout=30)
        if resp.status_code == 200:
            return resp.json().get("value", [])
        return []
    except Exception as e:
        print(f"[AI Service] Error fetching {entity}: {e}")
        return []


def _safe_lower(val: Optional[str]) -> str:
    return str(val or "").strip().lower()


def get_employee_overview(token: str, emp_id: str) -> dict:
    """Get overview of a specific employee."""
    entity = ENTITIES["employees"]
    records = _fetch_entity(
        entity, token,
        select="crc6f_employeeid,crc6f_firstname,crc6f_lastname,crc6f_email,crc6f_department,crc6f_designation,crc6f_doj,crc6f_activeflag",
        filter_query=f"crc6f_employeeid eq '{emp_id}'",
        top=1
    )
    if records:
        r = records[0]
        return {
            "employee_id": r.get("crc6f_employeeid"),
            "name": f"{r.get('crc6f_firstname', '')} {r.get('crc6f_lastname', '')}".strip(),
            "email": r.get("crc6f_email"),
            "department": r.get("crc6f_department"),
            "designation": r.get("crc6f_designation"),
            "date_of_joining": r.get("crc6f_doj"),
            "active": r.get("crc6f_activeflag"),
        }
    return {}


def get_all_employees_summary(token: str) -> dict:
    """Get summary of all employees."""
    entity = ENTITIES["employees"]
    records = _fetch_entity(
        entity, token,
        select="crc6f_employeeid,crc6f_firstname,crc6f_lastname,crc6f_department,crc6f_designation,crc6f_activeflag",
        top=500
    )
    
    total = len(records)
    active = sum(1 for r in records if r.get("crc6f_activeflag") in [True, "Active", "active", 1, "1"])
    
    # Group by department
    departments = {}
    for r in records:
        dept = r.get("crc6f_department") or "Unknown"
        departments[dept] = departments.get(dept, 0) + 1
    
    return {
        "total_employees": total,
        "active_employees": active,
        "inactive_employees": total - active,
        "by_department": departments,
        "sample_employees": [
            {
                "id": r.get("crc6f_employeeid"),
                "name": f"{r.get('crc6f_firstname', '')} {r.get('crc6f_lastname', '')}".strip(),
                "department": r.get("crc6f_department"),
            }
            for r in records[:10]
        ]
    }


def get_attendance_summary(token: str, emp_id: Optional[str] = None, days: int = 30) -> dict:
    """Get attendance summary for employee or org."""
    entity = ENTITIES["attendance"]
    
    # Date filter for recent records
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    filter_query = f"crc6f_date ge {start_date}"
    
    if emp_id:
        filter_query += f" and crc6f_employeeid eq '{emp_id}'"
    
    records = _fetch_entity(
        entity, token,
        select="crc6f_employeeid,crc6f_date,crc6f_checkin,crc6f_checkout,crc6f_duration",
        filter_query=filter_query,
        top=500
    )
    
    total_records = len(records)
    
    # Calculate stats
    total_hours = 0
    for r in records:
        duration = r.get("crc6f_duration")
        if duration:
            try:
                # Parse duration (could be in various formats)
                if isinstance(duration, (int, float)):
                    total_hours += float(duration)
                elif ":" in str(duration):
                    parts = str(duration).split(":")
                    total_hours += int(parts[0]) + int(parts[1]) / 60
            except:
                pass
    
    avg_hours = total_hours / total_records if total_records > 0 else 0
    
    return {
        "period_days": days,
        "total_attendance_records": total_records,
        "total_hours_logged": round(total_hours, 2),
        "average_hours_per_day": round(avg_hours, 2),
        "recent_entries": [
            {
                "employee_id": r.get("crc6f_employeeid"),
                "date": r.get("crc6f_date"),
                "check_in": r.get("crc6f_checkin"),
                "check_out": r.get("crc6f_checkout"),
                "duration": r.get("crc6f_duration"),
            }
            for r in records[:10]
        ]
    }


def get_leave_summary(token: str, emp_id: Optional[str] = None) -> dict:
    """Get leave requests summary."""
    entity = ENTITIES["leave"]
    
    filter_query = ""
    if emp_id:
        filter_query = f"crc6f_employeeid eq '{emp_id}'"
    
    records = _fetch_entity(
        entity, token,
        select="crc6f_employeeid,crc6f_leavetype,crc6f_startdate,crc6f_enddate,crc6f_status,crc6f_reason",
        filter_query=filter_query,
        top=200
    )
    
    # Count by status
    by_status = {}
    by_type = {}
    for r in records:
        status = r.get("crc6f_status") or "Unknown"
        leave_type = r.get("crc6f_leavetype") or "Unknown"
        by_status[status] = by_status.get(status, 0) + 1
        by_type[leave_type] = by_type.get(leave_type, 0) + 1
    
    return {
        "total_leave_requests": len(records),
        "by_status": by_status,
        "by_type": by_type,
        "recent_requests": [
            {
                "employee_id": r.get("crc6f_employeeid"),
                "type": r.get("crc6f_leavetype"),
                "start": r.get("crc6f_startdate"),
                "end": r.get("crc6f_enddate"),
                "status": r.get("crc6f_status"),
                "reason": r.get("crc6f_reason"),
            }
            for r in records[:10]
        ]
    }


def get_assets_summary(token: str) -> dict:
    """Get assets summary."""
    entity = ENTITIES["assets"]
    
    records = _fetch_entity(
        entity, token,
        top=200
    )
    
    return {
        "total_assets": len(records),
        "sample_assets": records[:5] if records else []
    }


def get_holidays_list(token: str) -> dict:
    """Get holidays list."""
    entity = ENTITIES["holidays"]
    
    records = _fetch_entity(
        entity, token,
        top=50
    )
    
    return {
        "total_holidays": len(records),
        "holidays": records[:20] if records else []
    }


def get_projects_summary(token: str) -> dict:
    """Get projects summary."""
    entity = ENTITIES["projects"]
    
    records = _fetch_entity(
        entity, token,
        top=100
    )
    
    return {
        "total_projects": len(records),
        "projects": records[:10] if records else []
    }


def get_interns_summary(token: str) -> dict:
    """Get interns summary."""
    entity = ENTITIES["interns"]
    
    records = _fetch_entity(
        entity, token,
        top=100
    )
    
    return {
        "total_interns": len(records),
        "interns": records[:10] if records else []
    }


def get_tasks_summary(token: str, emp_id: Optional[str] = None, limit: int = 200) -> dict:
    """Summarize project tasks, optionally scoped to an employee."""
    entity = ENTITIES.get("tasks")
    if not entity:
        return {}

    select_fields = ",".join(
        [
            "crc6f_hr_taskdetailsid",
            "crc6f_taskid",
            "crc6f_taskname",
            "crc6f_taskstatus",
            "crc6f_taskpriority",
            "crc6f_duedate",
            "crc6f_assignedto",
            "crc6f_projectid",
        ]
    )

    records = _fetch_entity(entity, token, select=select_fields, top=limit)
    if not records:
        return {"total_tasks": 0}

    by_status = {}
    by_priority = {}
    my_tasks = []
    upcoming = []
    emp_id_lower = _safe_lower(emp_id)

    for rec in records:
        status = (rec.get("crc6f_taskstatus") or "Unknown").strip()
        priority = (rec.get("crc6f_taskpriority") or "Normal").strip()
        by_status[status] = by_status.get(status, 0) + 1
        by_priority[priority] = by_priority.get(priority, 0) + 1

        assigned = rec.get("crc6f_assignedto")
        if emp_id_lower and emp_id_lower in _safe_lower(assigned):
            my_tasks.append(
                {
                    "task_id": rec.get("crc6f_taskid"),
                    "task_name": rec.get("crc6f_taskname"),
                    "status": status,
                    "priority": priority,
                    "due_date": rec.get("crc6f_duedate"),
                }
            )

        due = rec.get("crc6f_duedate")
        if due:
            upcoming.append(
                {
                    "task_id": rec.get("crc6f_taskid"),
                    "task_name": rec.get("crc6f_taskname"),
                    "due_date": due,
                    "status": status,
                }
            )

    upcoming = sorted(upcoming, key=lambda r: r.get("due_date") or "")[:5]

    return {
        "total_tasks": len(records),
        "by_status": by_status,
        "by_priority": by_priority,
        "my_tasks": my_tasks[:10],
        "upcoming_due": upcoming,
    }


def get_timesheet_summary(token: str, emp_id: Optional[str] = None, days: int = 30) -> dict:
    """Summarize timesheet entries for org or individual."""
    entity = ENTITIES.get("timesheets")
    if not entity:
        return {}

    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    filter_query = f"crc6f_workdate ge {start_date}"
    if emp_id:
        filter_query += f" and crc6f_employeeid eq '{emp_id}'"

    select_fields = ",".join(
        [
            "crc6f_employeeid",
            "crc6f_projectid",
            "crc6f_taskid",
            "crc6f_taskname",
            "crc6f_workdate",
            "crc6f_hours",
            "crc6f_seconds",
        ]
    )

    records = _fetch_entity(entity, token, select=select_fields, filter_query=filter_query, top=500)
    if not records:
        return {"total_logs": 0, "period_days": days}

    total_hours = 0.0
    by_project = {}
    recent_entries = []

    for rec in records:
        hours = rec.get("crc6f_hours")
        seconds = rec.get("crc6f_seconds")
        try:
            if hours is not None:
                total_hours += float(hours)
            elif seconds is not None:
                total_hours += float(seconds) / 3600.0
        except Exception:
            pass

        project = rec.get("crc6f_projectid") or "Unknown"
        by_project[project] = by_project.get(project, 0) + 1

        recent_entries.append(
            {
                "date": rec.get("crc6f_workdate"),
                "task": rec.get("crc6f_taskname") or rec.get("crc6f_taskid"),
                "hours": rec.get("crc6f_hours") or rec.get("crc6f_seconds"),
            }
        )

    recent_entries = sorted(recent_entries, key=lambda e: e.get("date") or "", reverse=True)[:10]

    return {
        "period_days": days,
        "total_logs": len(records),
        "total_hours": round(total_hours, 2),
        "by_project": by_project,
        "recent_entries": recent_entries,
    }


def get_login_activity_summary(token: str, emp_id: Optional[str] = None, days: int = 14) -> dict:
    """Summarize login activity for users."""
    entity = ENTITIES.get("login_activity")
    if not entity:
        return {}

    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    filter_query = f"crc6f_date ge {start_date}"
    if emp_id:
        filter_query += f" and crc6f_employeeid eq '{emp_id}'"

    select_fields = ",".join(
        [
            "crc6f_employeeid",
            "crc6f_date",
            "crc6f_checkintime",
            "crc6f_checkouttime",
            "crc6f_checkinlocation",
            "crc6f_checkoutlocation",
        ]
    )

    records = _fetch_entity(entity, token, select=select_fields, filter_query=filter_query, top=500)
    if not records:
        return {"total_events": 0}

    total_events = len(records)
    recent = sorted(records, key=lambda r: r.get("crc6f_date") or "", reverse=True)[:10]

    return {
        "period_days": days,
        "total_events": total_events,
        "recent_activity": [
            {
                "employee_id": r.get("crc6f_employeeid"),
                "date": r.get("crc6f_date"),
                "check_in": r.get("crc6f_checkintime"),
                "check_out": r.get("crc6f_checkouttime"),
            }
            for r in recent
        ],
    }


def build_ai_context(token: str, user_meta: dict, scope: str = "general") -> dict:
    """
    Build comprehensive context for AI based on user role and scope.
    
    Args:
        token: Dataverse access token
        user_meta: User info (employee_id, is_admin, is_l3, etc.)
        scope: Query scope ('general', 'attendance', 'leave', 'employee', etc.)
    
    Returns:
        Dict with relevant data summaries
    """
    role_flags = _derive_role_flags(user_meta)
    context = {
        "timestamp": datetime.now().isoformat(),
        "user_access": role_flags,
    }
    
    emp_id = user_meta.get("employee_id")
    is_admin = role_flags.get("is_admin")
    is_l3 = role_flags.get("is_l3")
    is_l2 = role_flags.get("is_l2")
    
    try:
        # Always include basic employee info for the current user
        if emp_id:
            context["current_user_profile"] = get_employee_overview(token, emp_id)
        
        # Scope-based data fetching with L3 permissions
        if scope in ["general", "employee", "all"]:
            if is_admin or is_l3:  # L3/Admin access
                context["employees_summary"] = get_all_employees_summary(token)
            elif emp_id:
                context["my_profile"] = get_employee_overview(token, emp_id)
        
        if scope in ["general", "attendance", "all"]:
            if is_admin or is_l3:
                context["attendance_summary"] = get_attendance_summary(token, days=30)
            elif emp_id:
                context["my_attendance"] = get_attendance_summary(token, emp_id=emp_id, days=30)
        
        if scope in ["general", "leave", "all"]:
            if is_admin or is_l3:
                context["leave_summary"] = get_leave_summary(token)
            elif emp_id:
                context["my_leaves"] = get_leave_summary(token, emp_id=emp_id)
        
        if scope in ["general", "assets", "all"]:
            if is_admin or is_l3:
                context["assets_summary"] = get_assets_summary(token)
            elif emp_id:
                context["my_assets"] = context.get("my_assets") or {"total_assets": 0}
        
        if scope in ["general", "holidays", "all"]:
            context["holidays"] = get_holidays_list(token)
        
        if scope in ["general", "projects", "all"]:
            if is_admin or is_l3:
                context["projects_summary"] = get_projects_summary(token)
        
        if scope in ["general", "interns", "all"]:
            if is_admin or is_l3:
                context["interns_summary"] = get_interns_summary(token)
        
        if scope in ["general", "tasks", "projects", "all"]:
            if is_admin or is_l3:
                context["tasks_summary"] = get_tasks_summary(token)
            elif emp_id:
                context["my_tasks_summary"] = get_tasks_summary(token, emp_id=emp_id)
        
        if scope in ["general", "timesheets", "time", "all"]:
            if is_admin or is_l3 or is_l2:
                context["timesheet_summary"] = get_timesheet_summary(token)
            elif emp_id:
                context["my_timesheets"] = get_timesheet_summary(token, emp_id=emp_id)
        
        if scope in ["general", "login", "attendance", "all"]:
            if is_admin or is_l3:
                context["login_activity_summary"] = get_login_activity_summary(token)
            elif emp_id:
                context["my_login_activity"] = get_login_activity_summary(token, emp_id=emp_id)
        
    except Exception as e:
        print(f"[AI Service] Error building context: {e}")
    
    return context
