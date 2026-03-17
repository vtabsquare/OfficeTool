#!/usr/bin/env python3
"""
Temporary script to delete test leave records for EMP014 on specific dates.
This script directly deletes from Dataverse.
"""
import os
import sys
from dotenv import load_dotenv
from dataverse_helper import get_access_token, delete_record

# Load environment variables
load_dotenv()

# Test leave IDs to delete for EMP014
TEST_LEAVES = [
    "LVE-JBHFODK",  # 2026-03-14
    "LVE-U0CL22E",  # 2026-03-15
    "LVE-1HTLNYF",  # 2026-03-15
    "LVE-TWJGRFT",  # 2026-03-17
    "LVE-PQI8LA2",  # 2026-03-22
]

def delete_test_leaves():
    """Delete the specified test leave records."""
    print("Starting deletion of test leave records for EMP014...")
    
    # Get Dataverse access token
    try:
        token = get_access_token()
        if not token:
            print("ERROR: Failed to get Dataverse access token")
            return False
    except Exception as e:
        print(f"ERROR: Exception getting access token: {e}")
        return False
    
    # Delete each test leave
    success_count = 0
    for leave_id in TEST_LEAVES:
        try:
            print(f"Deleting leave {leave_id}...")
            
            # Delete from Dataverse
            result = delete_record("crc6f_table14s", leave_id, token)
            
            if result:
                print(f"✓ Successfully deleted leave {leave_id}")
                success_count += 1
            else:
                print(f"✗ Failed to delete leave {leave_id}")
                
        except Exception as e:
            print(f"✗ Error deleting leave {leave_id}: {e}")
    
    print(f"\nDeletion complete. Successfully deleted {success_count}/{len(TEST_LEAVES)} test leaves.")
    return success_count == len(TEST_LEAVES)

if __name__ == "__main__":
    if delete_test_leaves():
        print("All test leaves deleted successfully!")
        sys.exit(0)
    else:
        print("Some test leaves could not be deleted.")
        sys.exit(1)
