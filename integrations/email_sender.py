"""
Email Sender - Sends meeting summaries and action items via SMTP
"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict, Optional
import config.settings as settings
from datetime import datetime

class EmailSender:
    """Handles sending professional meeting summary emails"""
    
    def __init__(self):
        """Initialize SMTP settings"""
        self.smtp_server = settings.SMTP_SERVER
        self.smtp_port = settings.SMTP_PORT
        self.sender_email = settings.SENDER_EMAIL
        self.sender_password = settings.SENDER_PASSWORD
        
        self.enabled = all([self.smtp_server, self.smtp_port, self.sender_email, self.sender_password])
        if not self.enabled:
            print("⚠️  Email sender is partially configured. SMTP features will be disabled.")
    
    def send_meeting_summary(
        self, 
        recipient_emails: List[str], 
        summary: str, 
        action_items: List[Dict], 
        meeting_title: str,
        date: Optional[str] = None,
        include_summary: bool = True,
        include_actions: bool = True,
        include_transcript: bool = False,
        transcript_text: Optional[str] = None
    ) -> Dict[str, List[str]]:
        """
        Send a formatted meeting summary iteratively to a list of recipients.
        
        Args:
            recipient_emails: List of email addresses
            summary: Markdown summary text
            action_items: List of action item dictionaries
            meeting_title: Title of the meeting
            date: Date string
            include_summary: Toggle to include summary
            include_actions: Toggle to include actions
            include_transcript: Toggle to include full transcript
            transcript_text: Transcript payload (if True)
            
        Returns:
            Dict: {"successes": [...], "failures": [...], "invalid_format": [...]}
        """
        results = {"successes": [], "failures": [], "invalid_format": []}
        
        if not self.enabled:
            print(f"❌ Cannot send email: SMTP not fully configured. Server: {self.smtp_server}, Port: {self.smtp_port}, User: {self.sender_email}")
            return results
            
        print(f"📧 Starting email dispatch for meeting: {meeting_title}")
        print(f"   Recipients to process: {recipient_emails}")
        
        import re
        email_regex = re.compile(r"^[^@]+@[^@]+\.[^@]+$")
        
        valid_emails = []
        for email in recipient_emails:
            clean_email = email.strip()
            if not clean_email:
                continue
            if email_regex.match(clean_email):
                valid_emails.append(clean_email)
            else:
                results["invalid_format"].append(clean_email)
                
        if not valid_emails:
            print(f"⚠️ No valid recipient emails found. Original list: {recipient_emails}")
            return results
            
        print(f"✅ Found {len(valid_emails)} valid recipients: {valid_emails}")
            
        date_str = date or datetime.now().strftime("%B %d, %Y")
        
        # Build conditionally
        plain_text = f"MEETING SUMMARY: {meeting_title}\nDate: {date_str}\n\n"
        if include_summary and summary:
            plain_text += f"{summary}\n\n"
        if include_actions:
            plain_text += "ACTION ITEMS:\n"
            for item in action_items:
                plain_text += f"- {item.get('task', '')} (Owner: {item.get('assignee_name', item.get('owner', 'Unassigned'))}, Deadline: {item.get('deadline', 'N/A')})\n"
            plain_text += "\n"
        if include_transcript and transcript_text:
            plain_text += f"TRANSCRIPT:\n{transcript_text}\n\n"
            
        html_content = self._generate_html(meeting_title, date_str, summary, action_items, include_summary, include_actions, include_transcript, transcript_text)
        
        try:
            print(f"🔌 Connecting to SMTP server: {self.smtp_server}:{self.smtp_port}...")
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                print(f"🔑 Attempting login for: {self.sender_email}...")
                server.login(self.sender_email, self.sender_password)
                print("🔓 SMTP Login successful!")
                
                # Send INDIVIDUALLY to prevent BCC exposure and handle specific failures
                for email in valid_emails:
                    msg = MIMEMultipart("alternative")
                    msg["Subject"] = f"Meeting Summary: {meeting_title} ({date_str})"
                    msg["From"] = f"MeetAI <{self.sender_email}>"
                    msg["To"] = email
                    
                    msg.attach(MIMEText(plain_text, "plain"))
                    msg.attach(MIMEText(html_content, "html"))
                    
                    try:
                        server.sendmail(self.sender_email, [email], msg.as_string())
                        results["successes"].append(email)
                        print(f"✓ Summary email sent successfully to {email}")
                    except Exception as e:
                        print(f"❌ Failed to send email to {email}: {e}")
                        results["failures"].append(email)
                        
            return results
        except Exception as e:
            print(f"❌ SMTP Connection failed: {e}")
            results["failures"].extend(valid_emails)
            return results
            
    def _generate_html(self, title: str, date: str, summary: str, action_items: List[Dict], include_summary: bool, include_actions: bool, include_transcript: bool, transcript_text: Optional[str]) -> str:
        """Generate professional HTML meeting summary with conditionals"""
        
        summary_section = ""
        if include_summary and summary:
            import markdown
            summary_html = markdown.markdown(summary)
            summary_section = f"""
            <div class="section-title">Summary</div>
            <div style="margin-top: 15px;">
                {summary_html}
            </div>
            """
            
        action_section = ""
        if include_actions:
            action_rows = ""
            for item in action_items:
                priority = item.get('confidence', item.get('priority', 'medium'))
                priority_color = {
                    "high": "#d93025",
                    "medium": "#f9ab00",
                    "low": "#188038"
                }.get(priority, "#5f6368")
                
                owner = item.get('assignee_name', item.get('owner', 'Unassigned'))
                
                action_rows += f"""
                <tr>
                    <td style="padding: 12px; border-bottom: 1px solid #e0e0e0;">
                        <div style="font-weight: bold; color: #202124;">{item.get('task', 'Unknown')}</div>
                    </td>
                    <td style="padding: 12px; border-bottom: 1px solid #e0e0e0; color: #5f6368;">
                        {owner}
                    </td>
                    <td style="padding: 12px; border-bottom: 1px solid #e0e0e0; color: #5f6368;">
                        {item.get('deadline', 'N/A')}
                    </td>
                    <td style="padding: 12px; border-bottom: 1px solid #e0e0e0;">
                        <span style="background-color: {priority_color}; color: white; padding: 2px 8px; border-radius: 12px; font-size: 11px; text-transform: uppercase;">
                            {priority}
                        </span>
                    </td>
                </tr>
                """
                
            if not action_rows:
                action_rows = "<tr><td colspan='4' style='padding: 20px; text-align: center; color: #70757a;'>No action items identified.</td></tr>"

            action_section = f"""
            <div class="section-title">Action Items</div>
            <table>
                <thead>
                    <tr>
                        <th>Task</th>
                        <th>Owner</th>
                        <th>Deadline</th>
                        <th>Confidence</th>
                    </tr>
                </thead>
                <tbody>
                    {action_rows}
                </tbody>
            </table>
            """
            
        transcript_section = ""
        if include_transcript and transcript_text:
            transcript_html = transcript_text.replace('\n', '<br>')
            transcript_section = f"""
            <div class="section-title">Cleaned Transcript</div>
            <div style="margin-top: 15px; font-family: monospace; font-size: 12px; color: #5f6368; background-color: #f8f9fa; padding: 15px; border-radius: 4px;">
                {transcript_html}
            </div>
            """

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; color: #3c4043; margin: 0; padding: 0; }}
                .container {{ max-width: 600px; margin: 20px auto; border: 1px solid #e0e0e0; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
                .header {{ background-color: #1a73e8; color: white; padding: 30px; text-align: center; }}
                .content {{ padding: 30px; background-color: white; }}
                .section-title {{ color: #1a73e8; border-bottom: 2px solid #f1f3f4; padding-bottom: 8px; margin-top: 25px; font-size: 18px; font-weight: bold; }}
                .footer {{ background-color: #f8f9fa; padding: 20px; text-align: center; color: #70757a; font-size: 12px; }}
                table {{ width: 100%; border-collapse: collapse; margin-top: 15px; }}
                th {{ text-align: left; background-color: #f8f9fa; padding: 12px; color: #5f6368; font-size: 12px; text-transform: uppercase; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1 style="margin: 0; font-size: 24px;">Meeting Assistant</h1>
                    <p style="margin: 5px 0 0 0; opacity: 0.9;">{title}</p>
                    <p style="margin: 2px 0 0 0; font-size: 13px; opacity: 0.8;">{date}</p>
                </div>
                <div class="content">
                    {summary_section}
                    {action_section}
                    {transcript_section}
                </div>
                <div class="footer">
                    <p>Generated by AI Meeting Assistant Bot</p>
                    <p>This is an automated notification. Please do not reply to this email.</p>
                </div>
            </div>
        </body>
        </html>
        """
        return html
