import re
import os
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import requests

class RecipientResolver:
    """
    Unified resolver for meeting recipients across platforms.
    Resolves emails from host-integrated sources (Google Calendar, Zoom API).
    """
    
    def __init__(self, google_creds_path=None, google_token_path=None):
        self.google_creds_path = google_creds_path or "credentials.json"
        self.google_token_path = google_token_path or "token.json"
        self.google_service = None
        
    def _get_google_service(self):
        """Lazy-load Google Calendar service with OAuth2 flow"""
        if self.google_service:
            return self.google_service
            
        scopes = ['https://www.googleapis.com/auth/calendar.events']
        creds = None
        
        if os.path.exists(self.google_token_path):
            creds = Credentials.from_authorized_user_file(self.google_token_path, scopes)
            
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            elif os.path.exists(self.google_creds_path):
                flow = InstalledAppFlow.from_client_secrets_file(self.google_creds_path, scopes)
                creds = flow.run_local_server(port=0)
            else:
                return None
                
            with open(self.google_token_path, 'w') as token:
                token.write(creds.to_json())
                
        self.google_service = build('calendar', 'v3', credentials=creds)
        return self.google_service

    def resolve_google_meet(self, url: str, start_time: Optional[float] = None) -> Dict:
        """
        Resolves recipients for a Google Meet session using Calendar API.
        Returns { 'resolved': [{name, email, source}], 'unresolved': [{name, source}] }
        """
        results = {'resolved': [], 'unresolved': []}
        
        # 1. Extract Meet code (abc-def-ghi)
        match = re.search(r'meet\.google\.com/([a-z0-9\-]+)', url)
        if not match:
            return results
        meet_code = match.group(1)
        
        service = self._get_google_service()
        if not service:
            return results
            
        try:
            # 2. Search for the event in a time window
            # Default window: +/- 2 hours around start_time (or now)
            pivot_time = datetime.fromtimestamp(start_time) if start_time else datetime.now()
            time_min = (pivot_time - timedelta(hours=2)).isoformat() + 'Z'
            time_max = (pivot_time + timedelta(hours=2)).isoformat() + 'Z'
            
            # Use 'q' as a best-effort search step
            events_result = service.events().list(
                calendarId='primary', 
                timeMin=time_min, 
                timeMax=time_max,
                q=meet_code,
                singleEvents=True
            ).execute()
            
            events = events_result.get('items', [])
            
            target_event = None
            for event in events:
                # Thorough check for meet_code in various metadata fields
                conf_data = event.get('conferenceData', {})
                entry_points = conf_data.get('entryPoints', [])
                
                # Check conference data
                found_in_conf = any(meet_code in ep.get('uri', '') for ep in entry_points)
                # Check location/description
                found_in_meta = meet_code in event.get('location', '') or meet_code in event.get('description', '')
                
                if found_in_conf or found_in_meta:
                    target_event = event
                    break
            
            if target_event:
                attendees = target_event.get('attendees', [])
                for attendee in attendees:
                    name = attendee.get('displayName', attendee.get('email', 'Unknown'))
                    email = attendee.get('email')
                    
                    if email:
                        results['resolved'].append({
                            'name': name,
                            'email': email,
                            'source': 'Google Calendar'
                        })
                    else:
                        results['unresolved'].append({
                            'name': name,
                            'source': 'Google Calendar'
                        })
                        
        except Exception as e:
            print(f"⚠️ Google Calendar resolution error: {e}")
            
        return results

    def resolve_zoom(self, url: str) -> Dict:
        """
        Placeholder for Zoom resolution using Zoom API (v2).
        Returns structured data similar to resolve_google_meet.
        """
        # Note: Actual implementation requires Zoom OAuth / Server-to-Server flow setup
        # For now, returning empty to maintain stability while indicating structure
        return {'resolved': [], 'unresolved': []}

    def resolve_all(self, url: str, participants: List[str] = None, start_time: Optional[float] = None) -> Dict:
        """
        Unified entry point for recipient resolution.
        Reconciles API results with detected participant names.
        """
        source_type = "None"
        if 'meet.google.com' in url:
            api_results = self.resolve_google_meet(url, start_time)
            source_type = "Google Calendar"
        elif 'zoom.us' in url:
            api_results = self.resolve_zoom(url)
            source_type = "Zoom API"
        else:
            api_results = {'resolved': [], 'unresolved': []}
            
        # Reconcile with detected participant names (from bot scraping/session detection)
        # We don't want to duplicate, so we cross-reference
        resolved_names = {r['name'].lower(): r for r in api_results['resolved']}
        unresolved_names = {u['name'].lower(): u for u in api_results['unresolved']}
        
        final_results = {
            'resolved': api_results['resolved'],
            'unresolved': api_results['unresolved'],
            'resolved_source': source_type
        }
        
        if participants:
            for p_name in participants:
                if p_name.lower() not in resolved_names and p_name.lower() not in unresolved_names:
                    # If name not found in API results, add to unresolved with Session source
                    final_results['unresolved'].append({
                        'name': p_name,
                        'source': 'Session Detection'
                    })
                    
        return final_results
