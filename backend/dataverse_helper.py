import os
import requests
from dotenv import load_dotenv
import msal

# Load environment variables from id.env
load_dotenv("id.env")

TENANT_ID = os.getenv("TENANT_ID")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
RESOURCE = os.getenv("RESOURCE")  # e.g., https://<yourorg>.crm.dynamics.com

AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPE = [f"{RESOURCE}/.default"]
EMPLOYEE_ENTITY="crc6f_table12s"
def get_access_token():
    app = msal.ConfidentialClientApplication(
        client_id=CLIENT_ID,
        client_credential=CLIENT_SECRET,
        authority=AUTHORITY
    )

    result = app.acquire_token_for_client(scopes=SCOPE)

    if "access_token" in result:
        return result["access_token"]
    else:
        raise Exception(f"Failed to get token: {result}")

# -------------------- CRUD Functions --------------------

def create_record(entity_name, data):
    """Create a new record in Dataverse"""
    token = get_access_token()
    url = f"{RESOURCE}/api/data/v9.2/{entity_name}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "OData-MaxVersion": "4.0",
        "OData-Version": "4.0",
        "Prefer": "return=representation"
    }
    response = requests.post(url, headers=headers, json=data)
    if response.status_code in (200, 201):
        return response.json()
    else:
        raise Exception(f"Error creating record: {response.status_code} - {response.text}")


def get_record(entity_name, record_id):
    """Retrieve a single record by ID"""
    token = get_access_token()
    url = f"{RESOURCE}/api/data/v9.2/{entity_name}({record_id})"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"Error getting record: {response.status_code} - {response.text}")


def fetch_record_by_id(entity_name, leave_id, id_field="crc6f_leaveid"):
    """Fetch a record by alternate key (e.g., leave ID)"""
    token = get_access_token()
    # Use OData query to filter by the alternate key
    url = f"{RESOURCE}/api/data/v9.2/{entity_name}?$filter={id_field} eq '{leave_id}'"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        # Return the first record if found
        if data.get('value') and len(data['value']) > 0:
            return data['value'][0]
        return None
    else:
        raise Exception(f"Error fetching record by {id_field}: {response.status_code} - {response.text}")


def update_record(entity_name, record_id, data):
    """Update a record"""
    token = get_access_token()
    url = f"{RESOURCE}/api/data/v9.2/{entity_name}({record_id})"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "If-Match": "*"
    }
    response = requests.patch(url, headers=headers, json=data)
    if response.status_code in (204, 1223):
        return True
    else:
        raise Exception(f"Error updating record: {response.status_code} - {response.text}")


def update_record_by_alt_key(entity_name, alt_key_value, data, alt_key_field="crc6f_leaveid"):
    """Update a record using alternate key"""
    token = get_access_token()
    # Use alternate key syntax for update
    url = f"{RESOURCE}/api/data/v9.2/{entity_name}({alt_key_field}='{alt_key_value}')"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "If-Match": "*"
    }
    response = requests.patch(url, headers=headers, json=data)
    if response.status_code in (204, 1223):
        return True
    else:
        raise Exception(f"Error updating record by alt key: {response.status_code} - {response.text}")


def delete_record(entity_name, record_id):
    """Delete a record"""
    token = get_access_token()
    url = f"{RESOURCE}/api/data/v9.2/{entity_name}({record_id})"
    headers = {
        "Authorization": f"Bearer {token}",
    }
    response = requests.delete(url, headers=headers)
    if response.status_code == 204:
        return True
    else:
        raise Exception(f"Error deleting record: {response.status_code} - {response.text}")


def get_employee_name(employee_id):
    """Fetch employee name from master table."""
    try:
        token = get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json"
        }
        url = f"{RESOURCE}/api/data/v9.2/{EMPLOYEE_ENTITY}?$filter=crc6f_employeeid eq '{employee_id}'&$select=crc6f_firstname"
        response = requests.get(url, headers=headers)
        if response.status_code == 200 and response.json().get("value"):
            return response.json()["value"][0].get("crc6f_firstname")
        # else:
        #     return employee_id
    except Exception as e:
        print(f"⚠️ Could not fetch name for {employee_id}: {e}")
        return employee_id



def get_employee_email(employee_id):
    """Fetch employee email and name from Employee Master"""
    try:
        token = get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "OData-MaxVersion": "4.0",
            "OData-Version": "4.0"
        }

        url = f"{RESOURCE}/api/data/v9.2/{EMPLOYEE_ENTITY}?$filter=crc6f_employeeid eq '{employee_id}'"
        response = requests.get(url, headers=headers)
        response.raise_for_status()

        records = response.json().get("value", [])
        if not records:
            print(f"⚠️ No employee found for ID: {employee_id}")
            return None, employee_id

        emp = records[0]
        print(emp)
        email = emp.get("crc6f_email")     # ✅ Correct field
        name = emp.get("crc6f_name", employee_id)

        print(f"📧 Found employee email: {email} for {employee_id}")
        return email

    except Exception as e:
        print(f"❌ Error fetching email for {employee_id}: {e}")
        return None, employee_id
