from flask import Flask, Blueprint, jsonify, request
from flask_cors import CORS
from dataverse_helper import get_access_token, create_record, update_record, delete_record, get_dataverse_session
import requests
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv("id.env")

# Blueprint setup
# holidays_bp = Blueprint("holidays", __name__)
app = Flask(__name__)
CORS(app)
# Dataverse resource (from .env)
RESOURCE = os.getenv("RESOURCE")
ENTITY_NAME = "crc6f_hr_holidayses"  # ✅ your correct table name

print(f"✅ Loaded RESOURCE: {RESOURCE}")
print(f"✅ Using table: {ENTITY_NAME}")


# ---------------- GET All Holidays ----------------
# @holidays_bp.route("/api/holidays", methods=["GET"])
@app.route("/api/holidays", methods=["GET"])
def get_holidays():
    """Fetch all holidays from Dataverse"""
    try:
        print("📥 Fetching holidays from Dataverse...")
        token = get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "OData-MaxVersion": "4.0",
            "OData-Version": "4.0"
        }

        # Fetch all records with ordering by date
        url = f"{RESOURCE}/api/data/v9.2/{ENTITY_NAME}?$select=crc6f_date,crc6f_holidayname,crc6f_hr_holidaysid&$orderby=crc6f_date asc"
        print(f"🔗 Request URL: {url}")
        
        response = get_dataverse_session().get(url, headers=headers, timeout=15)
        print(f"📊 Response status: {response.status_code}")

        if response.status_code != 200:
            error_msg = f"Failed to fetch: {response.text}"
            print(f"❌ {error_msg}")
            return jsonify({"error": error_msg}), response.status_code

        data = response.json().get("value", [])
        print(f"✅ Fetched {len(data)} holidays from Dataverse")

        return jsonify(data), 200

    except Exception as e:
        print(f"❌ Error in GET holidays: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ---------------- CREATE New Holiday ----------------
# @holidays_bp.route("/api/holidays", methods=["POST"])
@app.route("/api/holidays", methods=["POST"])
def create_holiday():
    """Add a new holiday"""
    try:
        data = request.get_json()

        new_record = {
            "crc6f_date": data.get("crc6f_date"),
            "crc6f_holidayname": data.get("crc6f_holidayname"),
        }

        result = create_record(ENTITY_NAME, new_record)
        return jsonify(result), 201

    except Exception as e:
        print("❌ Error in CREATE holiday:", e)
        return jsonify({"error": str(e)}), 500


# ---------------- UPDATE Existing Holiday ----------------
# @holidays_bp.route("/api/holidays/<holiday_id>", methods=["PATCH"])
@app.route("/api/holidays/<holiday_id>", methods=["PATCH"])
def update_holiday(holiday_id):
    """Edit an existing holiday"""
    try:
        data = request.get_json()
        update_data = {
            "crc6f_date": data.get("crc6f_date"),
            "crc6f_holidayname": data.get("crc6f_holidayname"),
        }

        success = update_record(ENTITY_NAME, holiday_id, update_data)
        if success:
            return jsonify({"message": "Holiday updated successfully"}), 200
        else:
            return jsonify({"error": "Failed to update"}), 400

    except Exception as e:
        print("❌ Error in UPDATE holiday:", e)
        return jsonify({"error": str(e)}), 500


# ---------------- DELETE Holiday ----------------
# @holidays_bp.route("/api/holidays/<holiday_id>", methods=["DELETE"])
@app.route("/api/holidays/<holiday_id>", methods=["DELETE"])
def delete_holiday(holiday_id):
    """Delete a holiday record"""
    try:
        success = delete_record(ENTITY_NAME, holiday_id)
        if success:
            return jsonify({"message": "Holiday deleted successfully"}), 200
        else:
            return jsonify({"error": "Failed to delete"}), 400

    except Exception as e:
        print("❌ Error in DELETE holiday:", e)
        return jsonify({"error": str(e)}), 500


# -------------------- Run --------------------
if __name__ == "__main__":
    app.run(debug=True, port=5000)
