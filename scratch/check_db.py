import sys
import os
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(os.getcwd())))

from database.mongodb_client import db
import config.settings as settings

print(f"--- MongoDB Diagnostic ---")
print(f"URI: {settings.MONGODB_URI[:25]}...")
print(f"DB Name: {settings.MONGODB_DB_NAME}")
print(f"Collection: {db.action_items.name}")

# Fetch all items
all_items = list(db.action_items.find())
print(f"Total items found: {len(all_items)}")

for i, item in enumerate(all_items):
    print(f"\nItem #{i}:")
    print(f"  ID: {item.get('_id')}")
    print(f"  Task: {item.get('task')}")
    print(f"  Status: {item.get('status')}")
    print(f"  Deadline: {item.get('deadline')}")
    print(f"  Assignee Name: {item.get('assignee_name')}")
    print(f"  Owner: {item.get('owner')}")
    print(f"  Meeting ID: {item.get('meeting_id')}")

print(f"\n--- End Diagnostic ---")
