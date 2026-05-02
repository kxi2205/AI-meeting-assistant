import os
import json
from datetime import datetime, timedelta
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from database.mongodb_client import db
import config.settings as settings

class GoogleAuthManager:
    """Manages Google OAuth 2.0 flows and token management for connected accounts."""
    SCOPES = [
        'https://www.googleapis.com/auth/calendar.events', # read + write (verified minimum for events.insert)
        'https://www.googleapis.com/auth/userinfo.email',
        'openid'
    ]
    def __init__(self):
        self.client_id = settings.GOOGLE_CLIENT_ID
        self.client_secret = settings.GOOGLE_CLIENT_SECRET
        
    def _get_client_config(self):
        """Build the client config dictionary from settings."""
        if not self.client_id or not self.client_secret:
            raise ValueError("Google Client ID and Secret must be set in .env")
            
        return {
            "installed": {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "project_id": "ai-meeting-assistant",
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                "redirect_uris": ["http://localhost"]
            }
        }

    def connect_new_account(self):
        """
        Initiates the InstalledAppFlow to connect a new Google Account.
        This will open a browser window and block until complete.
        Returns the connected email or None on failure.
        """
        try:
            flow = InstalledAppFlow.from_client_config(
                self._get_client_config(), 
                scopes=self.SCOPES
            )
            
            # DEBUG OAuth scopes verification
            print(f"DEBUG OAuth scopes: {self.SCOPES}")
            if hasattr(flow, "oauth2session"):
                print(f"DEBUG Flow scopes: {getattr(flow, 'oauth2session', None).scope}")
            else:
                print("DEBUG Flow scopes: no oauth2session")
            
            # This opens a browser window
            creds = flow.run_local_server(port=0, access_type='offline', prompt='consent')
            
            # Now we need to get the user's email address to identify the account
            # Since we only requested calendar scopes, we don't have the userinfo scope.
            # However, we can often extract the email from the id_token if available, 
            # or we might need to ask the user to input it as a label.
            # Let's try to get it from the id_token.
            email = "Unknown"
            if creds.id_token:
                try:
                    import base64
                    # ID tokens are JWTs: [header].[payload].[signature]
                    _, payload_b64, _ = creds.id_token.split('.')
                    # Add padding to base64 string if needed
                    missing_padding = len(payload_b64) % 4
                    if missing_padding:
                        payload_b64 += '=' * (4 - missing_padding)
                    
                    payload_json = base64.b64decode(payload_b64).decode('utf-8')
                    decoded = json.loads(payload_json)
                    email = decoded.get('email', 'Unknown')
                except Exception as e:
                    print(f"Could not extract email from id_token: {e}")
            
            # If we still don't have an email, we could query the calendar API for 'primary' calendar ID
            if email == "Unknown":
                from googleapiclient.discovery import build
                service = build('calendar', 'v3', credentials=creds)
                try:
                    calendar = service.calendars().get(calendarId='primary').execute()
                    email = calendar.get('id', 'Unknown')
                except Exception as e:
                    print(f"Could not get primary calendar ID: {e}")

            if email == "Unknown":
                raise ValueError("Could not determine the email address for the connected account.")

            # Store the credentials securely
            account_data = {
                'email': email,
                'access_token': creds.token,
                'refresh_token': creds.refresh_token,
                'expiry': creds.expiry.isoformat() if creds.expiry else None,
                'granted_scopes': creds.scopes or self.SCOPES,
                # We do not store client_id or client_secret here!
            }
            
            success = db.save_connected_account(account_data)
            return email if success else None
            
        except Exception as e:
            print(f"❌ Error during OAuth flow: {e}")
            import traceback
            traceback.print_exc()
            return None

    def get_credentials(self, email):
        """
        Retrieves valid credentials for a given email.
        Refreshes the token automatically if expired.
        """
        account = db.get_connected_account(email)
        if not account:
            return None
            
        expiry = datetime.fromisoformat(account['expiry']) if account.get('expiry') else None
        
        creds = Credentials(
            token=account.get('access_token'),
            refresh_token=account.get('refresh_token'),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self.client_id,
            client_secret=self.client_secret,
            scopes=self.SCOPES,
            expiry=expiry
        )
        
        # Check if expired and refresh
        if creds.expired and creds.refresh_token:
            try:
                print(f"Refreshing token for {email}...")
                creds.refresh(Request())
                
                # Update DB with new tokens
                db.update_account_tokens(
                    email,
                    new_access_token=creds.token,
                    new_refresh_token=creds.refresh_token, # Might be unchanged
                    new_expiry=creds.expiry.isoformat() if creds.expiry else None
                )
            except Exception as e:
                print(f"❌ Failed to refresh token for {email}: {e}")
                return None
                
        return creds if creds.valid else None

    def check_write_scope(self, email):
        """
        Check if the connected account has the required write scope for calendar events.
        """
        account = db.get_connected_account(email)
        if not account:
            return False
            
        granted = account.get('granted_scopes', [])
        return 'https://www.googleapis.com/auth/calendar.events' in granted

    def get_upcoming_events(self, email):
        """
        Fetches upcoming events for the given email from their primary Google Calendar.
        Filters for a rolling 24-hour window and only returns events with a Meet link.
        """
        creds = self.get_credentials(email)
        if not creds:
            return []
            
        try:
            from googleapiclient.discovery import build
            service = build('calendar', 'v3', credentials=creds)
            
            # 24-hour rolling window
            now = datetime.utcnow()
            time_min = now.isoformat() + 'Z'  # 'Z' indicates UTC time
            time_max = (now + timedelta(hours=24)).isoformat() + 'Z'
            
            events_result = service.events().list(
                calendarId='primary', 
                timeMin=time_min,
                timeMax=time_max,
                maxResults=50, 
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            meet_events = []
            
            for event in events:
                # Find meet link
                meet_link = event.get('hangoutLink')
                
                # Check location or description as fallback
                if not meet_link:
                    location = event.get('location', '')
                    description = event.get('description', '')
                    for text in [location, description]:
                        if 'meet.google.com/' in text:
                            # Extract basic meet link
                            parts = text.split('meet.google.com/')
                            if len(parts) > 1:
                                code = parts[1].split()[0].split('"')[0].split('<')[0]
                                meet_link = f"https://meet.google.com/{code}"
                                break
                                
                if meet_link:
                    # Extract start time
                    start = event['start'].get('dateTime', event['start'].get('date'))
                    
                    # Extract attendees with structured data
                    attendees = []
                    for attendee in event.get('attendees', []):
                        if attendee.get('email'):
                            attendees.append({
                                'name': attendee.get('displayName', attendee.get('email')),
                                'email': attendee.get('email'),
                                'source': 'Google Calendar'
                            })
                            
                    meet_events.append({
                        'id': event['id'],
                        'title': event.get('summary', 'Untitled Meeting'),
                        'start_time': start,
                        'meet_link': meet_link,
                        'attendees': attendees
                    })
                    
            return meet_events
            
        except Exception as e:
            print(f"❌ Error fetching calendar events for {email}: {e}")
            return []

auth_manager = GoogleAuthManager()
