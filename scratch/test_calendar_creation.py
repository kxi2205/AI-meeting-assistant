import sys
import os
from pathlib import Path
from datetime import datetime, timedelta

# Add project root to sys.path
sys.path.insert(0, str(Path(os.getcwd())))

from integrations.calendar_reminder import create_reminder_event

def test_creation():
    print("=== CALENDAR REMINDER CREATION TEST ===")
    import sys
    print(f"Python: {sys.executable}")
    from database.mongodb_client import db
    print(f"DB Name: {db.db.name}")
    
    # Check account exists
    account_email = "snehasrijaya2005@gmail.com"
    acc = db.connected_accounts.find_one({'email': account_email})
    
    if not acc:
        print(f"ERROR: Account {account_email} NOT FOUND in database!")
        print(f"Total connected accounts: {db.connected_accounts.count_documents({})}")
        return

    print(f"Account Found: {acc['email']}")
    print(f"Granted Scopes: {acc.get('granted_scopes')}")
    print(f"Has Access Token: {bool(acc.get('access_token'))}")
    print(f"Has Refresh Token: {bool(acc.get('refresh_token'))}")
    print("-" * 40 + "\n")
    
    # Setup test data
    action_item = {
        'task': 'Test calendar reminder integration',
        'assignee_name': 'Sneha',
        'evidence': 'This is a test event to verify Phase 3 backend logic.'
    }
    
    # Set deadline for 1 hour from now
    deadline = datetime.now() + timedelta(hours=1)
    
    print(f"Target Account: {account_email}")
    print(f"Task: {action_item['task']}")
    print(f"Deadline: {deadline.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Reminders: 10 minutes before")
    
    # Run creation
    result = create_reminder_event(
        account_email=account_email,
        action_item=action_item,
        deadline=deadline,
        reminder_minutes=[10],
        event_duration_minutes=30,
        attendee_email=account_email, # Invite self
        meeting_title="Phase 3 Integration Test",
        meeting_date=datetime.now().strftime("%Y-%m-%d"),
        meeting_id="test_id_123"
    )
    
    print("\n--- RESULTS ---")
    if result['success']:
        print("SUCCESS!")
        print(f"Event ID: {result['event_id']}")
        print("\nPlease check your Google Calendar to verify the event.")
    else:
        print("FAILED")
        print(f"Error: {result['error']}")

if __name__ == "__main__":
    test_creation()
