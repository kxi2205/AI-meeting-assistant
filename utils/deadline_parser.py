"""
Deadline Parser - Parses LLM-generated deadline strings and computes
closest deadline warnings from stored action items.

This module is additive and does NOT modify any existing features.
It reads from MongoDB action items to provide deadline intelligence.
"""
from datetime import datetime
from typing import Optional, Dict
from dateutil import parser as dateutil_parser


# Strings that indicate no real deadline was specified by the LLM
_NO_DEADLINE_PHRASES = {
    'not specified', 'n/a', 'none', 'tbd', 'asap', 'unassigned',
    'no deadline', 'unknown', 'to be determined', 'to be decided',
    'not mentioned', 'not set', 'no date', 'no due date',
    'whenever possible', 'as soon as possible', 'ongoing',
    'continuous', 'no specific date', 'flexible', '',
}


def parse_deadline(deadline_str: str, reference_date: datetime = None) -> Optional[datetime]:
    """
    Best-effort parse of an LLM-generated deadline string into a datetime.

    Returns None if the string is empty, vague, or unparseable.
    This function intentionally does NOT hallucinate dates — if it
    can't confidently parse, it returns None.

    Args:
        deadline_str: Raw deadline string from action item extraction
        reference_date: Reference date for relative parsing (defaults to now)

    Returns:
        Parsed datetime or None if unparseable/vague
    """
    if not deadline_str:
        return None

    normalized = deadline_str.strip().lower()

    # Reject known vague/non-deadline phrases
    if normalized in _NO_DEADLINE_PHRASES:
        return None

    # Reject very short strings that are unlikely to be dates
    if len(normalized) < 3:
        return None

    try:
        ref = reference_date or datetime.now()
        parsed = dateutil_parser.parse(deadline_str, fuzzy=True, default=ref)
        return parsed
    except (ValueError, OverflowError, TypeError):
        return None


def get_closest_deadline_warning(db) -> Optional[Dict]:
    """
    Scan all pending action items in MongoDB, find the nearest real deadline,
    and return a warning dict.

    This function runs entirely from MongoDB — no Google Calendar API needed.

    Args:
        db: MeetingDatabase instance

    Returns:
        Dict with warning info, or None if no parseable deadlines exist.
        Dict keys: urgency, label, deadline_date, task, assignee, meeting_id
    """
    try:
        items = db.get_action_items(status='pending')
    except Exception as e:
        print(f"[WARNING] Deadline warning: could not fetch action items: {e}")
        return None

    if not items:
        return None
    
    now = datetime.now()
    closest_date = None
    closest_item = None

    for item in items:
        deadline_str = item.get('deadline', '')
        parsed = parse_deadline(deadline_str)
        
        if parsed is None:
            continue

        if closest_date is None or parsed < closest_date:
            closest_date = parsed
            closest_item = item

    if closest_date is None or closest_item is None:
        return None

    delta_days = (closest_date.date() - now.date()).days

    if delta_days < 0:
        urgency = 'overdue'
        label = f"OVERDUE by {abs(delta_days)} day(s)"
    elif delta_days == 0:
        urgency = 'due_today'
        label = "Due TODAY"
    elif delta_days == 1:
        urgency = 'due_tomorrow'
        label = "Due TOMORROW"
    else:
        urgency = 'upcoming'
        label = f"Due in {delta_days} day(s)"

    return {
        'urgency': urgency,
        'label': label,
        'deadline_date': closest_date,
        'task': closest_item.get('task', 'Unknown task'),
        'assignee': closest_item.get('assignee_name', 'Unassigned'),
        'meeting_id': closest_item.get('meeting_id'),
    }
