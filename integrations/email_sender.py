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
        date: Optional[str] = None
    ) -> bool:
        """
        Send a formatted meeting summary to a list of recipients
        
        Args:
            recipient_emails: List of email addresses
            summary: Markdown summary text
            action_items: List of action item dictionaries
            meeting_title: Title of the meeting
            date: Date string
            
        Returns:
            bool: True if sent successfully, False otherwise
        """
        if not self.enabled:
            print("❌ Cannot send email: SMTP not fully configured.")
            return False
            
        if not recipient_emails:
            print("⚠️  No recipient emails provided.")
            return False
            
        date_str = date or datetime.now().strftime("%B %d, %Y")
        
        # Create message container
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"Meeting Summary: {meeting_title} ({date_str})"
        msg["From"] = f"AI Meeting Assistant <{self.sender_email}>"
        msg["To"] = ", ".join(recipient_emails)
        
        # Create HTML content
        html_content = self._generate_html(meeting_title, date_str, summary, action_items)
        
        # Attach both plain text and HTML versions
        # (For plain text, we just use the summary and a simple list of actions)
        plain_text = f"MEETING SUMMARY: {meeting_title}\nDate: {date_str}\n\n{summary}\n\nACTION ITEMS:\n"
        for item in action_items:
            plain_text += f"- {item['task']} (Owner: {item['owner']}, Deadline: {item['deadline']})\n"
            
        msg.attach(MIMEText(plain_text, "plain"))
        msg.attach(MIMEText(html_content, "html"))
        
        try:
            # Connect and send
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls() # Secure the connection
                server.login(self.sender_email, self.sender_password)
                server.sendmail(self.sender_email, recipient_emails, msg.as_string())
            
            print(f"✓ Summary email sent successfully to {len(recipient_emails)} recipients")
            return True
        except Exception as e:
            print(f"❌ Failed to send email: {e}")
            return False
            
    def _generate_html(self, title: str, date: str, summary: str, action_items: List[Dict]) -> str:
        """Generate professional HTML meeting summary"""
        
        # Convert markdown summary to simple HTML (basic conversion for this assistant)
        import markdown
        summary_html = markdown.markdown(summary)
        
        # Action items rows
        action_rows = ""
        for item in action_items:
            priority_color = {
                "high": "#d93025",    # Red
                "medium": "#f9ab00",  # Yellow/Orange
                "low": "#188038"      # Green
            }.get(item.get('priority', 'medium'), "#5f6368")
            
            action_rows += f"""
            <tr>
                <td style="padding: 12px; border-bottom: 1px solid #e0e0e0;">
                    <div style="font-weight: bold; color: #202124;">{item['task']}</div>
                </td>
                <td style="padding: 12px; border-bottom: 1px solid #e0e0e0; color: #5f6368;">
                    {item.get('owner', 'Unassigned')}
                </td>
                <td style="padding: 12px; border-bottom: 1px solid #e0e0e0; color: #5f6368;">
                    {item.get('deadline', 'N/A')}
                </td>
                <td style="padding: 12px; border-bottom: 1px solid #e0e0e0;">
                    <span style="background-color: {priority_color}; color: white; padding: 2px 8px; border-radius: 12px; font-size: 11px; text-transform: uppercase;">
                        {item.get('priority', 'medium')}
                    </span>
                </td>
            </tr>
            """
            
        if not action_rows:
            action_rows = "<tr><td colspan='4' style='padding: 20px; text-align: center; color: #70757a;'>No action items identified.</td></tr>"

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
                    <div class="section-title">Summary</div>
                    <div style="margin-top: 15px;">
                        {summary_html}
                    </div>
                    
                    <div class="section-title">Action Items</div>
                    <table>
                        <thead>
                            <tr>
                                <th>Task</th>
                                <th>Owner</th>
                                <th>Deadline</th>
                                <th>Priority</th>
                            </tr>
                        </thead>
                        <tbody>
                            {action_rows}
                        </tbody>
                    </table>
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
