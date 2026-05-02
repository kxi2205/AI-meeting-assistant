import sys
import os
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(os.getcwd())))

from utils.assignee_resolver import resolve_assignee_email
from database.mongodb_client import db

def test_resolver():
    print("=== ASSIGNEE RESOLVER HARDENING VALIDATION ===\n")

    # Case 1: Synthetic exact match
    meeting1 = {
        'invitees': [{'name': 'Sneha Srijaya', 'email': 'sneha@example.com'}],
        'resolved_recipients': []
    }
    print(f"Test 1 (Exact match): {resolve_assignee_email('Sneha Srijaya', meeting1)}")
    # Expected: ('sneha@example.com', 'calendar_invitee')

    # Case 2: Real email-prefix single match
    meeting2 = {
        'invitees': [{'name': 'snehasrijaya2005@gmail.com', 'email': 'snehasrijaya2005@gmail.com'}],
        'resolved_recipients': []
    }
    print(f"Test 2 (Email prefix match): {resolve_assignee_email('Sneha', meeting2)}")
    # Expected: ('snehasrijaya2005@gmail.com', 'calendar_invitee_email_prefix')

    # Case 3: Real email-subtoken match
    print(f"Test 3 (Subtoken match): {resolve_assignee_email('Srijaya', meeting2)}")
    # Expected: ('snehasrijaya2005@gmail.com', 'calendar_invitee_email_prefix')

    # Case 4: Ambiguous first-name match
    meeting4 = {
        'invitees': [
            {'name': 'snehasrijaya2005@gmail.com', 'email': 'snehasrijaya2005@gmail.com'},
            {'name': 'snehag123@gmail.com', 'email': 'snehag123@gmail.com'}
        ],
        'resolved_recipients': []
    }
    print(f"Test 4 (Ambiguous Sneha): {resolve_assignee_email('Sneha', meeting4)}")
    # Expected: (None, None)

    # Case 5: Unknown assignee
    print(f"Test 5 (Unknown): {resolve_assignee_email('Unknown Person', meeting4)}")
    # Expected: (None, None)

    print("\n=== REAL MONGODB VALIDATION (MEETING 1777639642) ===\n")
    try:
        meeting = db.get_meeting('1777639642')
        if meeting:
            print(f"Meeting 1777639642 found with {len(meeting.get('invitees', []))} invitees.")
            print(f"Resolving 'Sneha': {resolve_assignee_email('Sneha', meeting)}")
            print(f"Resolving 'Srijaya': {resolve_assignee_email('Srijaya', meeting)}")
        else:
            print("Meeting 1777639642 NOT FOUND in database.")
    except Exception as e:
        print(f"MongoDB validation error: {e}")

if __name__ == "__main__":
    test_resolver()
