"""
Assignee Resolver - Maps action item assignee names to email addresses
using only the current meeting's data (calendar invitees and email recipients).

This module is additive and does NOT perform cross-meeting lookups or
modify existing features.
"""
from typing import Optional, Tuple, Dict, List


import re


def _normalize_email_local(email: str) -> str:
    """Normalize email local part by removing digits and common separators."""
    local = email.split('@')[0].lower()
    return re.sub(r'[\d\.\s_\-]', '', local)


def _normalize_assignee(name: str) -> str:
    """Normalize assignee name by removing spaces and common separators."""
    name = name.lower()
    return re.sub(r'[\s\.\d_\-]', '', name)


def resolve_assignee_email(assignee_name: str, meeting: Dict) -> Tuple[Optional[str], Optional[str]]:
    """
    Resolves an assignee name to an email address using current meeting context.
    
    Priority:
    1. Exact Name Match
    2. Normalized Subtoken Match (safe fallback)
    
    Args:
        assignee_name: The name extracted by the LLM
        meeting: The meeting document from MongoDB
        
    Returns:
        tuple: (resolved_email, source) or (None, None) if unresolved.
    """
    if not assignee_name or assignee_name.lower() in ['unassigned', 'unknown', 'none', 'tbd']:
        return None, None
    
    norm_name = assignee_name.strip().lower()
    invitees = meeting.get('invitees', [])
    recipients = meeting.get('resolved_recipients', [])

    # --- 1. Exact Name Matches (Highest Confidence) ---
    exact_candidates = {} # email -> source
    
    for inv in invitees:
        if inv.get('name', '').strip().lower() == norm_name:
            email = inv.get('email')
            if email: exact_candidates[email] = 'calendar_invitee'

    for rec in recipients:
        if rec.get('name', '').strip().lower() == norm_name:
            email = rec.get('email')
            if email: exact_candidates[email] = 'email_dispatch'

    # If exactly one exact match exists, return it
    if len(exact_candidates) == 1:
        return list(exact_candidates.items())[0]
    elif len(exact_candidates) > 1:
        return None, None # Ambiguous exact match

    # --- 2. Normalized Fallback (Lower Confidence) ---
    # Prepare normalized assignee
    target = _normalize_assignee(assignee_name)
    if len(target) < 2: # Prevent matching on single letters
        return None, None

    prefix_matches = {} # email -> source
    
    # Collect all unique email candidates from current meeting
    all_candidates = []
    for inv in invitees:
        email = inv.get('email')
        if email: all_candidates.append((email, 'calendar_invitee_email_prefix'))
    for rec in recipients:
        email = rec.get('email')
        if email: all_candidates.append((email, 'email_dispatch_prefix'))

    for email, source in all_candidates:
        local_norm = _normalize_email_local(email)
        
        # Match conditions:
        # 1. Local part starts with target
        # 2. Target starts with local part
        # 3. Target is a meaningful subtoken of local part
        if (target in local_norm or local_norm in target):
            prefix_matches[email] = source

    # Only return if exactly one unique email matches the criteria
    if len(prefix_matches) == 1:
        return list(prefix_matches.items())[0]

    return None, None


def resolve_all_for_meeting(meeting: Dict, action_items: List[Dict]) -> List[Dict]:
    """
    Batch resolve emails for all action items in a meeting.
    Does NOT save to DB; just returns the resolved mapping for UI display.
    
    Args:
        meeting: The meeting document
        action_items: List of action item documents
        
    Returns:
        list: List of action items with added 'resolved_email' and 'resolution_source' fields
    """
    resolved_items = []
    for item in action_items:
        # Use existing resolved data if available, otherwise try to resolve
        email = item.get('resolved_assignee_email')
        source = item.get('assignee_resolution_source')
        
        if not email:
            # Try both assignee_name (LLM) and owner (manual/legacy)
            name = item.get('assignee_name') or item.get('owner')
            if name:
                email, source = resolve_assignee_email(name, meeting)
        
        # Create a copy to avoid mutating the original until saved
        resolved_item = item.copy()
        resolved_item['resolved_email'] = email
        resolved_item['resolution_source'] = source
        resolved_items.append(resolved_item)
        
    return resolved_items
