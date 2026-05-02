import sys
import os
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(os.getcwd())))

from pymongo import MongoClient
import config.settings as settings

client = MongoClient(settings.MONGODB_URI)
print("Databases found:")
for db_name in client.list_database_names():
    print(f"- {db_name}")
    db = client[db_name]
    for coll_name in db.list_collection_names():
        if coll_name == 'action_items':
            count = db[coll_name].count_documents({})
            print(f"  * {coll_name} ({count} items)")
            # Peek at items
            if count > 0:
                item = db[coll_name].find_one()
                print(f"    Sample item: {item.get('task')}")
