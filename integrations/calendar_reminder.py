"""
Calendar Reminder - Backend helper for creating Google Calendar reminder events.
Handles API communication, error classification, and timezone formatting.
"""
from datetime import datetime, timedelta
from googleapiclient.discovery import build
from integrations.google_auth import auth_manager
from database.mongodb_client import db

DEFAULT_TIMEZONE = 'Asia/Kolkata'

def create_reminder_event(
    account_email: str,
    action_item: dict,
    deadline: datetime,
    reminder_minutes: list[int] = [1440, 60],  # Default: 1 day and 1 hour before
    event_duration_minutes: int = 30,
    attendee_email: str = None,
    meeting_title: str = "Meeting",
    meeting_date: str = "",
    meeting_id: str = None
) -> dict:
    """
    Creates a Google Calendar event for an action item with structured error handling.
    
    Returns:
        dict: {
            'success': bool,
            'event_id': str | None,
            'error': str | None
        }
    """
    try:
        # 1. Get credentials
        creds = auth_manager.get_credentials(account_email)
        if not creds:
            return {
                'success': False,
                'event_id': None,
                'error': 'Invalid or expired credentials. Please reconnect your account.'
            }
        
        # 2. Check for write scope
        if not auth_manager.check_write_scope(account_email):
            return {
                'success': False,
                'event_id': None,
                'error': 'Insufficient permissions. Please disconnect and reconnect your account to grant write access.'
            }
        
        # 3. Build service
        service = build('calendar', 'v3', credentials=creds)
        
        # 4. Prepare event details
        task_text = action_item.get('task', 'Action Item')
        task_short = task_text[:80] + ('...' if len(task_text) > 80 else '')
        
        description_parts = [
            f"📋 Task: {task_text}",
            f"👤 Assignee: {action_item.get('assignee_name', 'Unassigned')}",
            f"📅 Original Meeting: {meeting_title}",
            f"🗓️ Meeting Date: {meeting_date}",
        ]
        
        if action_item.get('evidence'):
            description_parts.append(f"📝 Context: \"{action_item['evidence']}\"")
        if meeting_id:
            description_parts.append(f"🔗 Archive Reference: Meeting ID {meeting_id}")
            
        # Event starts (duration) before the deadline and ends at the deadline
        event_end = deadline
        event_start = deadline - timedelta(minutes=event_duration_minutes)
        
        event_body = {
            'summary': f"Action Item: {task_short}",
            'description': '\n'.join(description_parts),
            'start': {
                'dateTime': event_start.isoformat(),
                'timeZone': DEFAULT_TIMEZONE,
            },
            'end': {
                'dateTime': event_end.isoformat(),
                'timeZone': DEFAULT_TIMEZONE,
            },
            'reminders': {
                'useDefault': False,
                'overrides': [
                    {'method': 'popup', 'minutes': m} for m in reminder_minutes
                ]
            }
        }
        
        if attendee_email:
            event_body['attendees'] = [{'email': attendee_email}]
            
        # 5. Insert event
        event = service.events().insert(
            calendarId='primary',
            body=event_body,
            sendUpdates='all' if attendee_email else 'none'
        ).execute()
        
        return {
            'success': True,
            'event_id': event.get('id'),
            'error': None
        }
        
    except Exception as e:
        error_msg = str(e)
        print(f"[ERROR] Calendar Event Creation Failed: {error_msg}")
        
        # Classify common Google API errors
        if '403' in error_msg or 'insufficientPermissions' in error_msg:
            error_msg = 'Insufficient permissions. Please reconnect your account with write access.'
        elif '429' in error_msg or 'rateLimitExceeded' in error_msg:
            error_msg = 'Google Calendar rate limit reached. Please try again later.'
        elif '401' in error_msg:
            error_msg = 'Authorization expired or revoked. Please reconnect your account.'
        elif 'ConnectionError' in error_msg or 'timeout' in error_msg.lower():
            error_msg = 'Network error. Please check your connection and try again.'
            
        return {
            'success': False,
            'event_id': None,
            'error': error_msg
        }
