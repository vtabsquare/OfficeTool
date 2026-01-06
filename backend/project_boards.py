# # ============================================================
# # 📁 boards_bp.py
# # Manage Boards inside Projects (Full CRUD + auto ID)
# # ============================================================
# from flask import Blueprint, request, jsonify, current_app
# import requests, os, re, traceback
# from dotenv import load_dotenv
# from dataverse_helper import get_access_token

# bp = Blueprint("project_boards", __name__, url_prefix="/api")

# load_dotenv()

# # ======================
# # Dataverse Config
# # ======================
# DATAVERSE_BASE = os.getenv("RESOURCE")
# DATAVERSE_API = os.getenv("DATAVERSE_API", "/api/data/v9.2")
# ENTITY_SET_BOARDS = "crc6f_hr_projectdetailses"  # your table for boards
# PROJECT_HEADER_ES = "crc6f_hr_projectheaders"

# # Field names
# F_BOARD_ID = "crc6f_boardid"
# F_BOARD_NAME = "crc6f_boardname"
# F_DESC = "crc6f_boarddescription"
# F_NO_TASKS = "crc6f_nooftasks"
# F_NO_MEMBERS = "crc6f_noofmembers"
# F_PROJECT_ID = "crc6f_projectid"
# F_GUID = "crc6f_hr_projectdetailsid"

# def dv_url(path):
#     return f"{DATAVERSE_BASE}{DATAVERSE_API}{path}"

# def headers():
#     token = get_access_token()
#     return {
#         "Authorization": f"Bearer {token}",
#         "Accept": "application/json",
#         "OData-Version": "4.0",
#         "Content-Type": "application/json"
#     }

# # ============================================================
# # Auto Generate Board ID (like BRD001, BRD002)
# # ============================================================
# def generate_board_id():
#     try:
#         token = get_access_token()
#         hdr = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

#         existing_ids = set()

#         # Get ALL board IDs (Dataverse filtering)
#         url = f"{DATAVERSE_BASE}{DATAVERSE_API}/{ENTITY_SET_BOARDS}?$select={F_BOARD_ID}&$top=5000"
#         res = requests.get(url, headers=hdr, timeout=20)

#         if res.ok:
#             for r in res.json().get("value", []):
#                 bid = r.get(F_BOARD_ID)
#                 if bid:
#                     existing_ids.add(bid)

#         # Auto generate
#         num = 1
#         while True:
#             new_id = f"BRD{num:03d}"
#             if new_id not in existing_ids:
#                 return new_id
#             num += 1

#     except Exception as e:
#         current_app.logger.error(f"⚠ Error generating board_id: {e}")
#         return "BRD001"

# # ============================================================
# # 1️⃣ GET ALL BOARDS FOR A PROJECT
# # ============================================================
# @bp.route("/projects/<project_code>/boards", methods=["GET"])
# def get_boards(project_code):
#     """Fetch all boards for a given project."""
#     try:
#         token = get_access_token()
#         hdr = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

#         url = (
#             f"{DATAVERSE_BASE}{DATAVERSE_API}/{ENTITY_SET_BOARDS}"
#             f"?$filter={F_PROJECT_ID} eq '{project_code}'"
#             f"&$select={F_GUID},{F_BOARD_ID},{F_BOARD_NAME},{F_DESC},{F_NO_TASKS},{F_NO_MEMBERS},{F_PROJECT_ID}"
#         )
#         res = requests.get(url, headers=hdr, timeout=20)
#         if not res.ok:
#             return jsonify({"success": False, "error": res.text}), 500

#         boards = []
#         for r in res.json().get("value", []):
#             boards.append({
#                 "guid": r.get(F_GUID),
#                 "board_id": r.get(F_BOARD_ID),
#                 "board_name": r.get(F_BOARD_NAME),
#                 "board_description": r.get(F_DESC),
#                 "no_of_tasks": r.get(F_NO_TASKS, 0),
#                 "no_of_members": r.get(F_NO_MEMBERS, 0),
#                 "project_id": r.get(F_PROJECT_ID),
#             })

#         return jsonify({"success": True, "boards": boards}), 200

#     except Exception as e:
#         current_app.logger.exception("Error fetching boards")
#         return jsonify({"success": False, "error": str(e)}), 500


# # ============================================================
# # 2️⃣ ADD BOARD
# # ============================================================
# @bp.route("/projects/<project_code>/boards", methods=["POST"])
# def add_board(project_code):
#     """Add a board under a specific project."""
#     try:
#         body = request.get_json(force=True) or {}
#         current_app.logger.info(f"Add board for {project_code}: {body}")

#         token = get_access_token()
#         hdr = {
#             "Authorization": f"Bearer {token}",
#             "Accept": "application/json",
#             "Content-Type": "application/json"
#         }

#         # Generate new board id
#         board_id = generate_board_id()

#         payload = {
#             F_BOARD_ID: board_id,
#             F_BOARD_NAME: body.get("board_name"),
#             F_DESC: body.get("board_description", ""),
#             F_NO_TASKS: str(body.get("no_of_tasks", 0)),
#             F_NO_MEMBERS: str(body.get("no_of_members", 0)),
#             F_PROJECT_ID: project_code
#         }

#         payload = {k: v for k, v in payload.items() if v not in (None, "", [])}

#         url = f"{DATAVERSE_BASE}{DATAVERSE_API}/{ENTITY_SET_BOARDS}"
#         res = requests.post(url, headers=hdr, json=payload, timeout=20)

#         if res.status_code in (200, 201, 204):
#             return jsonify({"success": True, "message": "Board added successfully"}), 201
#         else:
#             current_app.logger.error(f"Add board failed: {res.text}")
#             return jsonify({"success": False, "error": res.text}), 400

#     except Exception as e:
#         current_app.logger.exception("Error adding board")
#         return jsonify({"success": False, "error": str(e)}), 500


# # ============================================================
# # 3️⃣ UPDATE BOARD
# # ============================================================
# @bp.route("/boards/<guid>", methods=["PATCH"])
# def update_board(guid):
#     """Update board details by Dataverse GUID."""
#     try:
#         body = request.get_json(force=True)
#         token = get_access_token()
#         hdr = {
#             "Authorization": f"Bearer {token}",
#             "Accept": "application/json",
#             "Content-Type": "application/json"
#         }

#         data = {}
#         if "board_name" in body:
#             data[F_BOARD_NAME] = body["board_name"]
#         if "board_description" in body:
#             data[F_DESC] = body["board_description"]
#         if "no_of_tasks" in body:
#             data[F_NO_TASKS] = str(body["no_of_tasks"])
#         if "no_of_members" in body:
#             data[F_NO_MEMBERS] = str(body["no_of_members"])

#         url = f"{DATAVERSE_BASE}{DATAVERSE_API}/{ENTITY_SET_BOARDS}({guid})"
#         res = requests.patch(url, headers=hdr, json=data, timeout=20)

#         if res.status_code in (200, 204):
#             return jsonify({"success": True, "message": "Board updated"}), 200
#         else:
#             return jsonify({"success": False, "error": res.text}), 400

#     except Exception as e:
#         current_app.logger.exception("Error updating board")
#         return jsonify({"success": False, "error": str(e)}), 500


# # ============================================================
# # 4️⃣ DELETE BOARD
# # ============================================================
# @bp.route("/boards/<guid>", methods=["DELETE"])
# def delete_board(guid):
#     """Delete a board by Dataverse GUID."""
#     try:
#         token = get_access_token()
#         hdr = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

#         url = f"{DATAVERSE_BASE}{DATAVERSE_API}/{ENTITY_SET_BOARDS}({guid})"
#         res = requests.delete(url, headers=hdr, timeout=20)

#         if res.status_code in (200, 204):
#             return jsonify({"success": True, "message": "Board deleted"}), 200
#         else:
#             return jsonify({"success": False, "error": res.text}), 400

#     except Exception as e:
#         current_app.logger.exception("Error deleting board")
#         return jsonify({"success": False, "error": str(e)}), 500

# boards_bp.py
from flask import Blueprint, request, jsonify, current_app
import requests, os, re, traceback
from dotenv import load_dotenv
from dataverse_helper import get_access_token

bp = Blueprint("project_boards",  __name__, url_prefix="/api")

load_dotenv()

# ======================
# Dataverse Config
# ======================
DATAVERSE_BASE = os.getenv("RESOURCE")
DATAVERSE_API = os.getenv("DATAVERSE_API", "/api/data/v9.2")
ENTITY_SET_BOARDS = "crc6f_hr_projectdetailses"  # your table for boards
PROJECT_HEADER_ES = "crc6f_hr_projectheaders"

# Field names
F_BOARD_ID = "crc6f_boardid"
F_BOARD_NAME = "crc6f_boardname"
F_DESC = "crc6f_boarddescription"
F_NO_TASKS = "crc6f_nooftasks"
F_NO_MEMBERS = "crc6f_noofmembers"
F_PROJECT_ID = "crc6f_projectid"
F_GUID = "crc6f_hr_projectdetailsid"

BOARD_RPT_MAP = {
    F_NO_TASKS: "crc6f_RPT_nooftasks",
    F_NO_MEMBERS: "crc6f_RPT_noofmembers",
}

def dv_url(path):
    return f"{DATAVERSE_BASE}{DATAVERSE_API}{path}"

def headers():
    token = get_access_token()
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "OData-Version": "4.0",
        "Content-Type": "application/json"
    }

# Auto Generate Board ID (BRD001...)
# ============================================================
def generate_board_id():
    try:
        token = get_access_token()
        hdr = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        url = f"{DATAVERSE_BASE}{DATAVERSE_API}/{ENTITY_SET_BOARDS}?$select={F_BOARD_ID}&$orderby=createdon desc&$top=1"
        res = requests.get(url, headers=hdr, timeout=20)

        last_id = None
        if res.ok:
            vals = res.json().get("value", [])
            if vals and vals[0].get(F_BOARD_ID):
                last_id = vals[0][F_BOARD_ID]

        if last_id and re.match(r"BRD\d+", last_id):
            num = int(last_id[3:])
        else:
            num = 0

        return f"BRD{num+1:03d}"

    except:
        return "BRD001"

# ============================================================
# 🔒 CHECK DUPLICATE BOARD
# ============================================================
def board_exists(project_code, board_name):
    try:
        token = get_access_token()
        hdr = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        url = (
            f"{DATAVERSE_BASE}{DATAVERSE_API}/{ENTITY_SET_BOARDS}"
            f"?$filter={F_PROJECT_ID} eq '{project_code}' and "
            f"{F_BOARD_NAME} eq '{board_name}'"
            f"&$select={F_GUID}"
        )
        res = requests.get(url, headers=hdr, timeout=20)

        items = res.json().get("value", [])
        return len(items) > 0
    except:
        return False
# ============================================================
# 1️⃣ GET ALL BOARDS FOR A PROJECT
# ============================================================
@bp.route("/projects/<project_code>/boards", methods=["GET"])
def get_boards(project_code):
    """Fetch all boards for a given project."""
    try:
        token = get_access_token()
        hdr = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

        url = (
            f"{DATAVERSE_BASE}{DATAVERSE_API}/{ENTITY_SET_BOARDS}"
            f"?$filter={F_PROJECT_ID} eq '{project_code}'"
            f"&$select={F_GUID},{F_BOARD_ID},{F_BOARD_NAME},{F_DESC},{F_NO_TASKS},{F_NO_MEMBERS},{F_PROJECT_ID}"
        )
        res = requests.get(url, headers=hdr, timeout=20)
        if not res.ok:
            return jsonify({"success": False, "error": res.text}), 500

        boards = []
        for r in res.json().get("value", []):
            boards.append({
                "guid": r.get(F_GUID),
                "board_id": r.get(F_BOARD_ID),
                "board_name": r.get(F_BOARD_NAME),
                "board_description": r.get(F_DESC),
                "no_of_tasks": r.get(F_NO_TASKS, 0),
                "no_of_members": r.get(F_NO_MEMBERS, 0),
                "project_id": r.get(F_PROJECT_ID),
            })

        return jsonify({"success": True, "boards": boards}), 200

    except Exception as e:
        current_app.logger.exception("Error fetching boards")
        return jsonify({"success": False, "error": str(e)}), 500


# ADD BOARD (POST) — NOW DUPLICATE SAFE
# ============================================================
@bp.route("/projects/<project_code>/boards", methods=["POST"])
def add_board(project_code):
    try:
        body = request.get_json(force=True)
        name = body.get("board_name")

        # ---- DUPLICATE CHECK ----
        if board_exists(project_code, name):
            return jsonify({
                "success": False,
                "duplicate": True,
                "error": f"Board '{name}' already exists in this project."
            }), 409

        token = get_access_token()
        hdr = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

        board_id = generate_board_id()

        payload = {
            F_BOARD_ID: board_id,
            F_BOARD_NAME: name,
            F_DESC: body.get("board_description"),
            F_NO_TASKS: str(body.get("no_of_tasks", 0)),
            F_NO_MEMBERS: str(body.get("no_of_members", 0)),
            F_PROJECT_ID: project_code,
        }
        for base_key, rpt_key in BOARD_RPT_MAP.items():
            if base_key in payload and payload[base_key] not in ("", None):
                payload[rpt_key] = payload[base_key]
            elif base_key in body and body.get(base_key) not in ("", None):
                payload[rpt_key] = body.get(base_key)

        payload = {k: v for k, v in payload.items() if v not in ("", None)}

        url = f"{DATAVERSE_BASE}{DATAVERSE_API}/{ENTITY_SET_BOARDS}"
        res = requests.post(url, headers=hdr, json=payload)

        if res.status_code in (200, 201, 204):
            return jsonify({"success": True, "message": "Board added"}), 201
        else:
            return jsonify({"success": False, "error": res.text}), 400

    except Exception as e:
        current_app.logger.exception("Error adding board")
        return jsonify({"success": False, "error": str(e)}), 500

# ============================================================
# 3️⃣ UPDATE BOARD
# ============================================================
@bp.route("/boards/<guid>", methods=["PATCH"])
def update_board(guid):
    """Update board details by Dataverse GUID."""
    try:
        body = request.get_json(force=True)
        token = get_access_token()
        hdr = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

        data = {}
        if "board_name" in body:
            data[F_BOARD_NAME] = body["board_name"]
        if "board_description" in body:
            data[F_DESC] = body["board_description"]
        if "no_of_tasks" in body:
            data[F_NO_TASKS] = str(body["no_of_tasks"])
        if "no_of_members" in body:
            data[F_NO_MEMBERS] = str(body["no_of_members"])
        for base_key, rpt_key in BOARD_RPT_MAP.items():
            if base_key in data and data[base_key] not in ("", None):
                data[rpt_key] = data[base_key]
            elif base_key in body and body.get(base_key) not in ("", None):
                data[rpt_key] = body.get(base_key)

        url = f"{DATAVERSE_BASE}{DATAVERSE_API}/{ENTITY_SET_BOARDS}({guid})"
        res = requests.patch(url, headers=hdr, json=data, timeout=20)

        if res.status_code in (200, 204):
            return jsonify({"success": True, "message": "Board updated"}), 200
        else:
            return jsonify({"success": False, "error": res.text}), 400

    except Exception as e:
        current_app.logger.exception("Error updating board")
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================================
# 4️⃣ DELETE BOARD
# ============================================================
@bp.route("/boards/<guid>", methods=["DELETE"])
def delete_board(guid):
    """Delete a board by Dataverse GUID."""
    try:
        token = get_access_token()
        hdr = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

        url = f"{DATAVERSE_BASE}{DATAVERSE_API}/{ENTITY_SET_BOARDS}({guid})"
        res = requests.delete(url, headers=hdr, timeout=20)

        if res.status_code in (200, 204):
            return jsonify({"success": True, "message": "Board deleted"}), 200
        else:
            return jsonify({"success": False, "error": res.text}), 400

    except Exception as e:
        current_app.logger.exception("Error deleting board")
        return jsonify({"success": False, "error": str(e)}), 500