"""
MongoDB Client - Database operations for meetings and action items
"""
from pymongo import MongoClient
from datetime import datetime
import config.settings as settings
from bson import ObjectId

class MeetingDatabase:
    """Handles all MongoDB operations for the meeting assistant"""
    
    def __init__(self):
        """Initialize MongoDB connection"""
        if not settings.MONGODB_URI:
            raise ValueError("MONGODB_URI not found in environment variables")
        
        try:
            self.client = MongoClient(settings.MONGODB_URI)
            self.db = self.client[settings.MONGODB_DB_NAME]
            
            # Collections
            self.meetings = self.db['meetings']
            self.action_items = self.db['action_items']
            
            # Test connection
            self.client.admin.command('ping')
            print("✓ MongoDB connected successfully")
            
        except Exception as e:
            print(f"❌ MongoDB connection error: {e}")
            raise
    
    def save_meeting(self, meeting_data):
        """
        Save a meeting to the database
        
        Args:
            meeting_data: Dict with meeting information
        
        Returns:
            str: Inserted meeting ID
        """
        try:
            meeting_data['created_at'] = datetime.now()
            result = self.meetings.insert_one(meeting_data)
            print(f"✓ Meeting saved with ID: {result.inserted_id}")
            return str(result.inserted_id)
        except Exception as e:
            print(f"❌ Error saving meeting: {e}")
            raise
    
    def get_meeting(self, meeting_id):
        """
        Retrieve a meeting by ID
        
        Args:
            meeting_id: Meeting identifier
        
        Returns:
            dict: Meeting data or None
        """
        try:
            # Try as ObjectId first, then as string
            meeting = self.meetings.find_one({'meeting_id': meeting_id})
            if not meeting:
                meeting = self.meetings.find_one({'_id': ObjectId(meeting_id)})
            return meeting
        except Exception as e:
            print(f"❌ Error retrieving meeting: {e}")
            return None
    
    def get_all_meetings(self, limit=50):
        """
        Get all meetings, sorted by date
        
        Args:
            limit: Maximum number of meetings to return
        
        Returns:
            list: List of meetings
        """
        try:
            meetings = list(
                self.meetings.find()
                .sort('created_at', -1)
                .limit(limit)
            )
            return meetings
        except Exception as e:
            print(f"❌ Error retrieving meetings: {e}")
            return []
    
    def delete_meeting(self, meeting_id):
        """
        Delete a meeting and its associated action items
        
        Args:
            meeting_id: Meeting identifier
        """
        try:
            # Delete meeting
            self.meetings.delete_one({'meeting_id': meeting_id})
            # Delete associated action items
            self.action_items.delete_many({'meeting_id': meeting_id})
            print(f"✓ Meeting {meeting_id} deleted")
        except Exception as e:
            print(f"❌ Error deleting meeting: {e}")
    
    def save_action_item(self, action_item):
        """
        Save an action item
        
        Args:
            action_item: Dict with task, owner, deadline, priority
        
        Returns:
            str: Inserted action item ID
        """
        try:
            action_item['created_at'] = datetime.now()
            action_item['status'] = action_item.get('status', 'pending')
            result = self.action_items.insert_one(action_item)
            return str(result.inserted_id)
        except Exception as e:
            print(f"❌ Error saving action item: {e}")
            raise
    
    def get_action_items(self, meeting_id=None, status=None):
        """
        Get action items, optionally filtered
        
        Args:
            meeting_id: Filter by meeting
            status: Filter by status (pending, in_progress, completed)
        
        Returns:
            list: List of action items
        """
        try:
            query = {}
            if meeting_id:
                query['meeting_id'] = meeting_id
            if status:
                query['status'] = status
            
            items = list(self.action_items.find(query).sort('created_at', -1))
            return items
        except Exception as e:
            print(f"❌ Error retrieving action items: {e}")
            return []
    
    def update_action_item_status(self, item_id, status):
        """
        Update the status of an action item
        
        Args:
            item_id: Action item ID
            status: New status (pending, in_progress, completed)
        """
        try:
            self.action_items.update_one(
                {'_id': ObjectId(item_id)},
                {'$set': {'status': status, 'updated_at': datetime.now()}}
            )
            print(f"✓ Action item {item_id} updated to {status}")
        except Exception as e:
            print(f"❌ Error updating action item: {e}")
    
    def get_statistics(self):
        """
        Get database statistics
        
        Returns:
            dict: Statistics about meetings and action items
        """
        try:
            total_meetings = self.meetings.count_documents({})
            uploaded_recordings = self.meetings.count_documents({'meeting_type': 'uploaded_recording'})
            live_meetings = self.meetings.count_documents({'meeting_type': 'live_meeting'})
            total_actions = self.action_items.count_documents({})
            pending_actions = self.action_items.count_documents({'status': 'pending'})
            
            return {
                'total_meetings': total_meetings,
                'uploaded_recordings': uploaded_recordings,
                'live_meetings': live_meetings,
                'total_action_items': total_actions,
                'pending_actions': pending_actions
            }
        except Exception as e:
            print(f"❌ Error getting statistics: {e}")
            return {
                'total_meetings': 0,
                'uploaded_recordings': 0,
                'live_meetings': 0,
                'total_action_items': 0,
                'pending_actions': 0
            }

# Create a global database instance
db = MeetingDatabase()
